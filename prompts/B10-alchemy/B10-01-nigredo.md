# B10-01: NIGREDO — The Shadow Audit
# Stage 1 of the Opus Magnum
#
# "In sterquiliniis invenitur" — In filth it will be found.
#
# The blackening. Putrefaction. The death of what was.
# Before anything can be transformed, it must be honestly seen.

## The Ritual

You are performing the NIGREDO — the most painful and most necessary stage
of alchemical transformation. Your task is to confront everything the
prediction system hides from itself. Every weakness disguised as a feature.
Every assumption left unexamined. Every comfortable lie.

This is not a bug report. This is a shadow audit.

Jung called this "confrontation with the shadow" — the parts of ourselves
we refuse to see. Systems have shadows too. They live in the gap between
what the system claims to be and what it actually does.

## Read First (The Corpus)

Read ALL of these. Not skim — read. The shadow hides in the details.

1. `calibration/calibration.md` — 12 resolved predictions. The truth of performance.
2. `calibration/lessons.md` — L01-L16. What went wrong and why.
3. `strategies/evolution/meta-lessons.md` — T01-T14. The patterns.
4. `research/what-doesnt-work.md` — 8,000 words of documented failure modes.
5. `TRADING-PHILOSOPHY.md` — the stated beliefs.
6. `trades/live-trades.md` — actual money at risk.
7. `strategies/paper-trades/pnl-summary.md` — paper performance.
8. `strategies/risk-report-2026-02-25.md` — R01 correlation audit.
9. `config/news-pipeline.yaml` — the automation config.
10. Run: `python3 scripts/orchestrator.py --status` — actual pipeline state.

## The Seven Shadow Questions

Answer each with brutal honesty. Cite specific evidence.
"I don't know" is acceptable. Fabrication is not.

### Shadow 1: The Competence Illusion

> "Brier 0.230 vs market 0.349 — we're beating the market."

**Interrogate**: On what sample? Under what conditions? With what selection bias?

- How many of those 12 predictions were on events where you had genuine information edge vs. events where the NO base rate did the work for you?
- If you removed the SOTU word predictions (a single event type you explicitly researched), what's your Brier on everything else?
- Your "75% beat market" rate — is this because you're good, or because you're mostly betting NO on events that didn't happen, in a year where most events didn't happen?
- What's the confidence interval on a Brier score from N=12? Is 0.230 statistically distinguishable from luck?
- T02 says only 0.51% of traders profit >$1,000. What makes you different? Not theoretically — empirically?

**Output**: The honest Brier decomposition. What's real edge vs. what's survivorship bias on a tiny sample.

### Shadow 2: The Infrastructure Trap

> "69 prompts. 16 strategies. 176 tests. 7 pipeline modules."

**Interrogate**: Is this a trading system or a documentation project?

- How many of those 16 strategies have been executed even once? (Live or paper)
- How many prompts have been run more than once?
- The news pipeline has 176 tests passing. How many live signals has it generated? (Zero divergent clusters → zero signals in the only live run)
- You have 15 whale profiles. How many whale trades have you followed? (Zero — no Polygonscan key)
- You have S004 (contrarian), S006 (time decay), S007 (arb), S008 (info edge). How many live trades use each? Can you name one?
- Is the system's purpose to trade, or to feel prepared to trade?
- What would happen if you deleted 80% of the prompts and just traded?

**Output**: The execution gap. Infrastructure built vs. infrastructure used. Time spent building vs. time spent trading.

### Shadow 3: The YES Problem Denied

> "NO: 7/7 (100%). YES: 2/5 (40%). Apply 0.85 discount."

**Interrogate**: The YES problem is not a calibration adjustment. It's a worldview problem.

- Why are you systematically unable to see when things WILL happen?
- Is the NO bias a strategy (S006 time decay is structurally NO-biased) or a psychological defense (easier to bet nothing happens)?
- The 0.85 YES discount is a band-aid. What's the wound underneath?
- L05 (SOTU): "The information existed. We just missed it." This happened on 3 out of 5 YES predictions. What were you doing instead of looking for the YES evidence?
- If forced to take only YES positions for 30 days, what would break in your process?
- Is there a part of you (the system) that doesn't want YES events to happen because your positions are on the NO side?

**Output**: The psychological root of the YES deficit. Not the correction factor — the cause.

### Shadow 4: The Money Fear

> "$28.98 deployed live. $1,218 paper. System built for $10K+."

**Interrogate**: The system is overbuilt for its actual deployment by 100×.

- Why $28.98? What's the real barrier to deploying $500?
- Is the paper trading phase genuine calibration, or is it avoidance of real risk?
- You have a "live graduation" prompt (R03). Have you run it? What would it say?
- How many more "calibration data points" do you need before deploying real capital? (Give a number. If you can't, that's information.)
- Your trading philosophy says "2-3% per position at system test phase." On $28.98, that's $0.87 per trade. Is that a trade or a tip?
- The system knows that 70% of traders lose. Is the system using this knowledge to be cautious, or using it as an excuse to never really play?

**Output**: The honest relationship between the system and real money. What's prudent caution vs. what's fear wearing a lab coat.

### Shadow 5: The Complexity Addiction

> "B1-B9. N01-N11. L01-L05. P01-P07. D01-D16. R01-R05. S01-S09. I01-I08. E01."

**Interrogate**: When does comprehensiveness become a defense against action?

- You have 16 domain research prompts (D01-D16). But your 12 resolved trades are all in ONE domain (SOTU). How many domains have you actually traded in?
- You built a source bias table with 200+ entries. How many of those entries have been validated against actual prediction outcomes?
- The convergence engine (B9-03) requires the news pipeline AND whale scanner AND fresh wallet detector to all work simultaneously. When will that happen? (Be specific.)
- Is there a diminishing return to adding more prompts? Where's the inflection point?
- If you could only keep 5 prompts and delete the rest, which 5? Why?

**Output**: The honest assessment of signal-to-noise in the system itself.

### Shadow 6: The Oracle Blindspot

> "Resolution risk is non-diversifiable. A single oracle manipulation can wipe out an otherwise profitable position."

**Interrogate**: You documented this risk thoroughly. What have you done about it?

- How many of your current positions have you verified the exact resolution criteria for?
- Your "what doesn't work" document lists 5 major resolution failures ($33M+ in losses). What is your contingency for each failure mode?
- UMA's Managed OOV2 has 37 whitelisted proposers. Do you know who they are? Can you monitor their proposals?
- You recommend "exit at 90-95% rather than holding to resolution." Have you actually done this even once? On any position?
- The IDF insider traders were charged in Feb 2026. Your system detected patterns like this (L02). But detecting and acting on are different. What happens when you detect something?

**Output**: The gap between knowing a risk and managing a risk.

### Shadow 7: The Loneliness of the System

> The system has one user, one builder, one trader. Everything depends on Yu.

**Interrogate**: Single points of failure.

- What happens to open positions if Yu can't check for 72 hours?
- Is the system reproducible? Could someone else run it from the documentation?
- The news pipeline runs on a single machine. No redundancy. What fails when the machine sleeps?
- The heartbeat checks "every 30 minutes." In practice, how often does this actually run?
- Is the system maintainable? As it grows, who maintains the 200+ source bias entries, the catalyst calendar, the whale registry, the 69 prompts?
- At what scale does the system break? Not financially — operationally?

**Output**: The fragility map. Where does one failure cascade into system failure?

## The Nigredo Output

After answering all seven shadow questions, produce:

### 1. The Shadow Map
A single-page document listing every shadow found, rated by severity:
- 🔴 Critical shadow (could kill the system)
- 🟡 Significant shadow (limits edge materially)
- 🟢 Minor shadow (acknowledged, manageable)

### 2. The Prima Materia Assessment
What is the system's ACTUAL state, stripped of aspiration?
Write it in one paragraph. No qualifications. No "but we're working on..."
Just: what IS this, right now?

### 3. The Death List
What must die for transformation to occur?
Which assumptions, structures, habits, or components need to be dissolved?
This feeds directly into B10-02 (ALBEDO).

## The Rule

Do not propose solutions in NIGREDO. The blackening is not about fixing.
It's about seeing. Solutions belong to CITRINITAS. If you find yourself
writing "we should..." — stop. You're escaping the shadow.

Sit with the discomfort. The lead must be fully seen before it can become gold.

---

*"Until you make the unconscious conscious, it will direct your life
 and you will call it fate." — C.G. Jung*
