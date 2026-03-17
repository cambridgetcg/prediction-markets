#!/bin/bash
# Run a research prompt in Claude Code
# Usage: ./run.sh <prompt-file>
# Example: ./run.sh domains/D01-iran-strike.md
#
# Or run all Tier 1 prompts:
#   ./run.sh --tier1
#
# Or run all:
#   ./run.sh --all

PROMPTS_DIR="$(dirname "$0")"
PM_DIR="$(dirname "$PROMPTS_DIR")"

run_prompt() {
  local file="$1"
  local name=$(basename "$file" .md)
  echo "═══════════════════════════════════════"
  echo "Running: $name"
  echo "File: $file"
  echo "═══════════════════════════════════════"
  cd "$PM_DIR"
  claude -p "$(cat "$file")"
  echo ""
  echo "✓ Completed: $name"
  echo ""
  echo "📝 Review output and log insights:"
  echo "   cp prompts/insights/review-template.md prompts/insights/${name}.md"
  echo "   Then fill in scores and observations."
  echo ""
}

if [ "$1" = "--pipeline" ]; then
  # Full pipeline: run prompt → assess → refine (if needed) → re-run
  shift
  if [ -z "$1" ]; then
    echo "Usage: ./run.sh --pipeline <prompt-file>"
    exit 1
  fi
  prompt_file="$1"
  [ -f "$prompt_file" ] || prompt_file="$PROMPTS_DIR/$1"
  name=$(basename "$prompt_file" .md)
  
  echo "══════════════════════════════════════════"
  echo "PIPELINE: $name"
  echo "  Step 1: Run prompt"
  echo "  Step 2: Assess output"
  echo "  Step 3: Refine if score < 4.0"
  echo "  Step 4: Re-run if refined"
  echo "══════════════════════════════════════════"
  
  # Step 1: Run
  run_prompt "$prompt_file"
  
  # Step 2: Assess
  echo "── Step 2: Assessing output ──"
  "$PROMPTS_DIR/insights/auto-assess.sh" "$prompt_file"
  
  # Step 3: Check score and refine if needed
  insight="$PROMPTS_DIR/insights/${name}.md"
  if [ -f "$insight" ]; then
    score=$(grep -i "overall" "$insight" | grep -oE '[0-9]\.[0-9]' | head -1)
    if [ -n "$score" ]; then
      needs_refine=$(echo "$score < 4.0" | bc -l 2>/dev/null)
      if [ "$needs_refine" = "1" ]; then
        echo "── Step 3: Score $score < 4.0 — Refining prompt ──"
        "$PROMPTS_DIR/insights/auto-refine.sh" "$name"
        
        echo "── Step 4: Re-running refined prompt ──"
        run_prompt "$prompt_file"
        
        echo "── Re-assessing ──"
        "$PROMPTS_DIR/insights/auto-assess.sh" "$prompt_file"
      else
        echo "── Score $score ≥ 4.0 — No refinement needed ──"
      fi
    fi
  fi
  
  echo "✓ Pipeline complete: $name"
  exit 0
elif [ "$1" = "--tier1" ]; then
  echo "Running Tier 1 prompts (highest value)..."
  for f in \
    "$PROMPTS_DIR/domains/D01-iran-strike.md" \
    "$PROMPTS_DIR/domains/D02-fed-policy.md" \
    "$PROMPTS_DIR/domains/D03-2028-presidential.md" \
    "$PROMPTS_DIR/strategies/S01-time-decay-math.md" \
    "$PROMPTS_DIR/strategies/S02-strategy-domain-fit.md"; do
    run_prompt "$f"
  done
elif [ "$1" = "--tier2" ]; then
  echo "Running Tier 2 prompts..."
  for f in \
    "$PROMPTS_DIR/domains/D04-crypto-landscape.md" \
    "$PROMPTS_DIR/domains/D05-ai-landscape.md" \
    "$PROMPTS_DIR/domains/D06-european-politics.md" \
    "$PROMPTS_DIR/strategies/S03-overreaction-patterns.md" \
    "$PROMPTS_DIR/infrastructure/I01-calibration-pipeline.md"; do
    run_prompt "$f"
  done
elif [ "$1" = "--tier2.5" ]; then
  echo "Running Tier 2.5 (time-sensitive + first trades)..."
  for f in \
    "$PROMPTS_DIR/strategies/S06-first-trades.md" \
    "$PROMPTS_DIR/domains/D10-iran-feb26-update.md"; do
    run_prompt "$f"
  done
elif [ "$1" = "--tier3" ]; then
  echo "Running Tier 3 prompts (updated with Tier 1+2 context)..."
  for f in \
    "$PROMPTS_DIR/domains/D07-venezuela.md" \
    "$PROMPTS_DIR/domains/D08-climate-energy.md" \
    "$PROMPTS_DIR/domains/D09-legal-regulatory.md" \
    "$PROMPTS_DIR/strategies/S04-new-strategy-exploration.md" \
    "$PROMPTS_DIR/strategies/S05-arb-scanner.md" \
    "$PROMPTS_DIR/infrastructure/I02-backtest-data.md" \
    "$PROMPTS_DIR/infrastructure/I03-multi-platform.md"; do
    run_prompt "$f"
  done
elif [ "$1" = "--all" ]; then
  echo "Running ALL prompts (this will take a while)..."
  find "$PROMPTS_DIR" -name "*.md" -not -name "README.md" | sort | while read f; do
    run_prompt "$f"
  done
else
  if [ -z "$1" ]; then
    echo "Usage:"
    echo "  ./run.sh <prompt-file>        # Run single prompt"
    echo "  ./run.sh --pipeline <file>    # Run → Assess → Refine → Re-run"
    echo "  ./run.sh --tier1              # Run Tier 1 (5 prompts)"
    echo "  ./run.sh --tier2              # Run Tier 2 (5 prompts)"
    echo "  ./run.sh --tier3              # Run Tier 3 (7 prompts)"
    echo "  ./run.sh --all                # Run all 17 prompts"
    echo ""
    echo "Post-run:"
    echo "  ./prompts/insights/auto-assess.sh --tier1    # Assess outputs"
    echo "  ./prompts/insights/auto-refine.sh --all-scored  # Refine <4.0"
    echo "  ./prompts/insights/auto-assess.sh --summary  # Score table"
    echo ""
    echo "Prompts:"
    find "$PROMPTS_DIR" -name "*.md" -not -name "README.md" | sort | sed "s|$PROMPTS_DIR/||"
    exit 1
  fi
  
  # Resolve the file path
  if [ -f "$1" ]; then
    run_prompt "$1"
  elif [ -f "$PROMPTS_DIR/$1" ]; then
    run_prompt "$PROMPTS_DIR/$1"
  else
    echo "Error: Prompt not found: $1"
    exit 1
  fi
fi
