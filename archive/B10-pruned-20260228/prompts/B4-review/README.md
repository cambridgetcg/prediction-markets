# Prompt Insights

A feedback loop for the prompts themselves. Every prompt is a hypothesis about how to instruct a research agent. The output reveals whether the hypothesis was right.

```
PROMPT (instruction hypothesis)
    │
    ├── RUN (agent executes)
    │       │
    │       ├── OUTPUT (what we got)
    │       │       │
    │       │       ├── ASSESSMENT (what worked, what didn't)
    │       │       │       │
    │       │       │       └── REFINEMENT (better prompt)
    │       │       │               │
    │       │       │               └── RUN (test refinement)
    │       │       │                       └── ...
    │       │       │
    │       │       └── CROSS-POLLINATION (lessons that apply to other prompts)
    │       │
    │       └── FAILURE MODES (what went wrong and why)
    │
    └── META-PATTERNS (how to write better prompts generally)
```

## Workflow

After running any prompt:

1. **Log the output quality** in `insights/{prompt-id}.md`
2. **Score** across dimensions (see rubric below)
3. **Identify** what to fix
4. **Update** the prompt (version it — old version stays in git history)
5. **Track** whether the fix worked on re-run

## Output Rubric

Score each dimension 1-5 after a prompt run:

| Dimension | 1 (Bad) | 3 (Okay) | 5 (Excellent) |
|-----------|---------|----------|---------------|
| **Completeness** | Skipped major tasks | Hit most tasks, missed some | All tasks addressed thoroughly |
| **Accuracy** | Wrong claims, no citations | Mostly right, some unsourced | Well-sourced, verified claims |
| **Depth** | Surface-level, generic | Adequate detail | Deep, insightful, non-obvious |
| **Actionability** | Vague conclusions | Some concrete recommendations | Clear estimates, specific next steps |
| **Format compliance** | Wrote to wrong places | Mostly correct structure | All files written exactly as specified |
| **Research quality** | No web search, hallucinated | Some search, patchy sourcing | Extensive search, good sources |
| **Integration** | Standalone, doesn't connect | Some cross-references | Updates context.md, active.md, links to other domains |

**Overall**: Average of 7 dimensions. Target: ≥4.0

## Insight File Template

For each prompt that has been run, create `insights/{prompt-id}.md`:

```markdown
# {Prompt ID} — Insight Log

## Run 1 — {date}
**Model**: {which model ran it}
**Duration**: {rough time}

### Scores
| Dimension | Score | Notes |
|-----------|-------|-------|
| Completeness | X/5 | |
| Accuracy | X/5 | |
| Depth | X/5 | |
| Actionability | X/5 | |
| Format compliance | X/5 | |
| Research quality | X/5 | |
| Integration | X/5 | |
| **Overall** | X.X/5 | |

### What Worked
- ...

### What Didn't
- ...

### Failure Modes
- [ ] Hallucinated facts
- [ ] Skipped web search
- [ ] Wrong output location
- [ ] Too shallow
- [ ] Missed the point
- [ ] Overly verbose / padded
- [ ] Didn't update related files
- [ ] Bad structure
- [ ] Other: ...

### Prompt Changes Made
- v1 → v2: {what changed and why}

### Cross-Pollination
Lessons that apply to other prompts:
- ...
```

## Common Failure Modes (update as we learn)

| Failure | Cause | Fix |
|---------|-------|-----|
| *To be populated after first runs* | | |

## Meta-Patterns (update as we learn)

General lessons about writing effective research prompts:

| Pattern | Description |
|---------|-------------|
| *To be populated* | |

## Version Tracking

Prompts evolve. Track major revisions:

| Prompt | Current Version | Last Changed | Change Summary |
|--------|----------------|-------------|----------------|
| D01 | v1 | 2026-02-23 | Initial |
| D02 | v1 | 2026-02-23 | Initial |
| D03 | v1 | 2026-02-23 | Initial |
| D04 | v1 | 2026-02-23 | Initial |
| D05 | v1 | 2026-02-23 | Initial |
| D06 | v1 | 2026-02-23 | Initial |
| D07 | v1 | 2026-02-23 | Initial |
| D08 | v1 | 2026-02-23 | Initial |
| D09 | v1 | 2026-02-23 | Initial |
| S01 | v1 | 2026-02-23 | Initial |
| S02 | v1 | 2026-02-23 | Initial |
| S03 | v1 | 2026-02-23 | Initial |
| S04 | v1 | 2026-02-23 | Initial |
| S05 | v1 | 2026-02-23 | Initial |
| I01 | v1 | 2026-02-23 | Initial |
| I02 | v1 | 2026-02-23 | Initial |
| I03 | v1 | 2026-02-23 | Initial |
