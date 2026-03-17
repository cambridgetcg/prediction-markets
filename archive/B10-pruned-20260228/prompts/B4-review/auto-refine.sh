#!/bin/bash
# Auto-refine a prompt based on its insight report
# Usage: ./auto-refine.sh <prompt-id>
# Example: ./auto-refine.sh D01-iran-strike
#
# Reads the insight report, applies suggested improvements to the prompt,
# and bumps the version in the tracking table.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROMPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PM_DIR="$(cd "$PROMPTS_DIR/.." && pwd)"

refine_prompt() {
  local prompt_id="$1"
  local insight_file="$SCRIPT_DIR/${prompt_id}.md"
  
  if [ ! -f "$insight_file" ]; then
    echo "Error: No insight report found for $prompt_id"
    echo "Run auto-assess.sh first."
    return 1
  fi
  
  # Find the original prompt file
  local prompt_file=$(find "$PROMPTS_DIR" -name "${prompt_id}.md" -not -path "*/insights/*" | head -1)
  
  if [ ! -f "$prompt_file" ]; then
    echo "Error: Original prompt not found: $prompt_id"
    return 1
  fi
  
  echo "═══════════════════════════════════════"
  echo "Refining: $prompt_id"
  echo "Insight: $insight_file"
  echo "Prompt:  $prompt_file"
  echo "═══════════════════════════════════════"
  
  cd "$PM_DIR"
  claude -p "You are a prompt engineer refining a research prompt based on quality assessment feedback.

## Task

1. Read the insight report at: $insight_file
2. Read the current prompt at: $prompt_file
3. Apply the suggested improvements from the insight report to the prompt
4. Focus on fixing the identified failure modes
5. Preserve what worked well (high-scoring dimensions)
6. Write the improved prompt back to: $prompt_file
7. Update the version tracking table in $SCRIPT_DIR/README.md — bump the version number and add change summary
8. Add a '## Changelog' section at the bottom of the prompt file noting what changed and why

## Rules

- Don't rewrite from scratch — surgical improvements based on specific feedback
- If the insight suggests adding 'must use web search' or 'cite sources' — add those as explicit constraints
- If depth was low — add more specific sub-questions to guide deeper research
- If format compliance was low — make output paths and structure more explicit
- If actionability was low — add explicit 'produce a specific estimate' or 'recommend exactly N items' instructions
- Keep the prompt roughly the same length (±20%) — don't bloat it

## Output

The refined prompt written to the same file, with changelog appended.
Updated version tracking in insights/README.md."
  
  echo ""
  echo "✓ Refined: $prompt_id"
  echo ""
}

case "$1" in
  --all-scored)
    # Refine all prompts that have insight reports with overall score < 4.0
    for f in "$SCRIPT_DIR"/*.md; do
      name=$(basename "$f" .md)
      [[ "$name" == "README" || "$name" == "review-template" || "$name" == "assess" ]] && continue
      score=$(grep -i "overall" "$f" | grep -oE '[0-9]\.[0-9]' | head -1)
      if [ -n "$score" ]; then
        needs_refine=$(echo "$score < 4.0" | bc -l 2>/dev/null)
        if [ "$needs_refine" = "1" ]; then
          echo "Score $score < 4.0 — refining $name"
          refine_prompt "$name"
        else
          echo "Score $score ≥ 4.0 — skipping $name"
        fi
      fi
    done
    ;;
  "")
    echo "Usage:"
    echo "  ./auto-refine.sh <prompt-id>       # Refine single prompt"
    echo "  ./auto-refine.sh --all-scored      # Refine all prompts scoring < 4.0"
    echo ""
    echo "Requires insight reports from auto-assess.sh first."
    ;;
  *)
    refine_prompt "$1"
    ;;
esac
