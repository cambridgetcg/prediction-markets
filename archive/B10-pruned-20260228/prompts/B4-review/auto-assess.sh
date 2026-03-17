#!/bin/bash
# Auto-assess a prompt's output using Claude Code
# Usage: ./auto-assess.sh <prompt-file>
# Example: ./auto-assess.sh domains/D01-iran-strike.md
#
# Runs after a prompt has been executed. Reads the original prompt,
# checks all specified output files, scores the result, and writes
# an insight report.
#
# Batch mode:
#   ./auto-assess.sh --tier1    # Assess all Tier 1 outputs
#   ./auto-assess.sh --all      # Assess all prompt outputs

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROMPTS_DIR="$(dirname "$SCRIPT_DIR")"  # This is prompts/ not insights/
# Fix: insights/ is inside prompts/, so PROMPTS_DIR should be the prompts dir
PROMPTS_DIR="$SCRIPT_DIR/.."
PM_DIR="$(cd "$PROMPTS_DIR/.." && pwd)"

ASSESS_TEMPLATE="$SCRIPT_DIR/assess.md"

assess_prompt() {
  local prompt_file="$1"
  local prompt_id=$(basename "$prompt_file" .md)
  
  # Check if the prompt exists
  if [ ! -f "$prompt_file" ]; then
    # Try resolving relative to prompts dir
    prompt_file="$PROMPTS_DIR/$1"
    if [ ! -f "$prompt_file" ]; then
      echo "Error: Prompt not found: $1"
      return 1
    fi
  fi
  
  prompt_id=$(basename "$prompt_file" .md)
  
  echo "═══════════════════════════════════════"
  echo "Assessing: $prompt_id"
  echo "═══════════════════════════════════════"
  
  # Build the assessment prompt by injecting the specific prompt path and ID
  local assess_prompt=$(cat "$ASSESS_TEMPLATE")
  assess_prompt="${assess_prompt//\{PROMPT_PATH\}/$prompt_file}"
  assess_prompt="${assess_prompt//\{PROMPT_ID\}/$prompt_id}"
  
  cd "$PM_DIR"
  claude -p "$assess_prompt"
  
  echo ""
  if [ -f "$SCRIPT_DIR/${prompt_id}.md" ]; then
    echo "✓ Insight report written: prompts/insights/${prompt_id}.md"
    # Extract and display the overall score
    score=$(grep -i "overall" "$SCRIPT_DIR/${prompt_id}.md" | grep -oE '[0-9]\.[0-9]' | head -1)
    if [ -n "$score" ]; then
      echo "  Overall score: $score/5"
    fi
  else
    echo "⚠ No insight report found — assessor may have written to wrong location"
  fi
  echo ""
}

TIER1=(
  "domains/D01-iran-strike.md"
  "domains/D02-fed-policy.md"
  "domains/D03-2028-presidential.md"
  "strategies/S01-time-decay-math.md"
  "strategies/S02-strategy-domain-fit.md"
)

TIER2=(
  "domains/D04-crypto-landscape.md"
  "domains/D05-ai-landscape.md"
  "domains/D06-european-politics.md"
  "strategies/S03-overreaction-patterns.md"
  "infrastructure/I01-calibration-pipeline.md"
)

TIER3=(
  "domains/D07-venezuela.md"
  "domains/D08-climate-energy.md"
  "domains/D09-legal-regulatory.md"
  "strategies/S04-new-strategy-exploration.md"
  "strategies/S05-arb-scanner.md"
  "infrastructure/I02-backtest-data.md"
  "infrastructure/I03-multi-platform.md"
)

case "$1" in
  --tier1)
    for f in "${TIER1[@]}"; do assess_prompt "$PROMPTS_DIR/$f"; done
    ;;
  --tier2)
    for f in "${TIER2[@]}"; do assess_prompt "$PROMPTS_DIR/$f"; done
    ;;
  --tier3)
    for f in "${TIER3[@]}"; do assess_prompt "$PROMPTS_DIR/$f"; done
    ;;
  --all)
    find "$PROMPTS_DIR" -name "*.md" -not -path "*/insights/*" -not -name "README.md" | sort | while read f; do
      assess_prompt "$f"
    done
    ;;
  --summary)
    echo "═══════════════════════════════════════"
    echo "Assessment Summary"
    echo "═══════════════════════════════════════"
    echo ""
    printf "%-12s %-6s %-6s %-6s %-6s %-6s %-6s %-6s %-8s\n" \
      "Prompt" "Compl" "Accur" "Depth" "Actn" "Fmt" "Rsrch" "Integ" "Overall"
    echo "────────────────────────────────────────────────────────────────────────"
    for f in "$SCRIPT_DIR"/*.md; do
      name=$(basename "$f" .md)
      # Skip non-prompt files
      [[ "$name" == "README" || "$name" == "review-template" || "$name" == "assess" ]] && continue
      # Extract scores from the table
      scores=$(grep "|" "$f" 2>/dev/null | grep -E "^\|.*/5" | head -8)
      if [ -n "$scores" ]; then
        # Try to extract overall
        overall=$(grep -i "overall" "$f" | grep -oE '[0-9]\.[0-9]' | head -1)
        printf "%-12s %s\n" "$name" "${overall:-?}/5"
      fi
    done
    ;;
  "")
    echo "Usage:"
    echo "  ./auto-assess.sh <prompt-file>     # Assess single prompt output"
    echo "  ./auto-assess.sh --tier1           # Assess Tier 1 outputs"
    echo "  ./auto-assess.sh --tier2           # Assess Tier 2 outputs"
    echo "  ./auto-assess.sh --tier3           # Assess Tier 3 outputs"
    echo "  ./auto-assess.sh --all             # Assess all"
    echo "  ./auto-assess.sh --summary         # Show scores summary"
    ;;
  *)
    assess_prompt "$1"
    ;;
esac
