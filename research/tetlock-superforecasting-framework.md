# Tetlock Superforecasting Framework: Research Summary

*Research date: 2026-02-25*
*Primary source: Tetlock & Gardner, "Superforecasting: The Art and Science of Prediction" (2015)*
*Supporting: Mellers et al. (2015), Atanasov et al. (2020), Kahneman (2011), Flyvbjerg (2004)*

---

## 1. What Separates Superforecasters from Experts

### The Expert Political Judgment Backdrop (Tetlock 2005)

Between 1984–2004, Tetlock tracked 28,000+ predictions from 284 political experts. The devastating finding: **the average expert was roughly as accurate as a dart-throwing chimpanzee**. Hedgehogs (one-big-idea thinkers) were *worse* than chance on their specialty topics. Foxes (eclectic, multi-source thinkers) performed modestly better, but not by much.

This finding motivated the IARPA ACE tournament (2011–2015) — could *anyone* forecast geopolitics well?

### The IARPA Tournament: Hard Numbers

The Good Judgment Project (GJP), led by Tetlock and Barbara Mellers at UPenn, competed against four other university research teams in the IARPA-sponsored forecasting tournament.

**Performance metrics:**
- GJP beat the control group by **60% in Year 1** and **~80% in Year 2**
- Beat all competing research teams by **35–72%**
- Superforecasters (top 2% of GJP) beat **intelligence analysts with classified information by 30%**
- Superforecasters at 300 days out were **more accurate than regular forecasters at 100 days** (Steyvers analysis: 400-day SF accuracy ≈ 150-day regular accuracy)
- Beat prediction markets in head-to-head (66% more accurate on Fed policy; 25–30% more accurate than IC prediction markets)
- 100 superforecasters defeated hybrid ML + 1,000-person crowd systems

**Brier score benchmarks:**
| Group | Brier Score | Notes |
|-------|-------------|-------|
| Random guessing | 0.50 | Assigning 50/50 to everything |
| Regular forecasters | ~0.35 | Untrained participants |
| Intelligence analysts (classified) | ~0.25–0.30 | Professional analysts with access |
| Superforecasters (aggregate) | ~0.15–0.16 | Top 2% of GJP participants |
| Best individual superforecaster | ~0.14 | Near theoretical limit for these questions |
| Perfect calibration at 93% confidence | 0.132 | Benchmark comparison |

### BEYOND Foxes vs. Hedgehogs: Specific Cognitive Habits

The fox/hedgehog distinction was Tetlock's starting point, not his conclusion. The *specific* traits that define superforecasters:

**1. Active Open-Mindedness (AOM)**
Not just "being open-minded" — actively seeking disconfirming evidence. Beliefs are hypotheses to test, not treasures to protect. Superforecasters score exceptionally high on Baron's AOM scale. They *enjoy* being proven wrong because it means they learned something.

**2. Need for Cognition (NFC)**
Intellectual curiosity as a trait, not just a habit. They enjoy puzzles, seek complexity rather than simplifying prematurely. They score high on the NFC-18 scale (Cacioppo & Petty).

**3. Perpetual Beta**
The **single strongest predictor** of becoming a superforecaster — roughly **3x more powerful than intelligence** as a predictor. "Perpetual beta" means commitment to continuous self-improvement and belief updating. They never consider their forecasting "done" or their methods "proven."

**4. Granular Probability Discrimination**
Where experts use maybe 3–5 probability buckets (likely, unlikely, toss-up), superforecasters routinely distinguish **10–15 degrees of uncertainty**. They think in 1–2 percentage point increments (e.g., 73% vs 71%), and this granularity correlates directly with accuracy.

**5. Dragonfly Eye Perspective**
Named after the dragonfly's compound eye that synthesizes thousands of lenses into one image. Superforecasters aggregate multiple perspectives, frameworks, and information sources into a single coherent probability estimate. Not averaging — *synthesizing*.

**6. Growth Mindset (Dweck)**
Fixed mindset: "I'm not good at predicting X." Growth mindset: "I haven't found the right approach to X yet." Superforecasters treat forecasting as a trainable skill, not an innate talent.

**7. Scope Sensitivity**
Regular forecasters show little variance when timeframes change (3 months vs. 6 months). Superforecasters appropriately differentiate — a 3-month probability of 20% becomes, say, 35% at 6 months, not staying flat at "about 25%."

**8. Metacognition**
Thinking about their own thinking. Superforecasters monitor their reasoning processes, catch themselves applying heuristics inappropriately, and maintain "decision journals" that enable genuine learning from outcomes.

### What Training Does (The 1-Hour Effect)

A single 1-hour training module covering probabilistic reasoning, bias avoidance, and outside-view thinking produced measurable accuracy improvements **that persisted for at least one year**. The training covered:
- Base-rate anchoring
- Probability estimation techniques
- Common cognitive biases to watch for
- The outside view

This is remarkably cost-effective — suggesting the core skills are *teachable*, not innate. Training also caused forecasters to update beliefs in smaller increments, which independently boosted accuracy.

---

## 2. The Ten Commandments of Superforecasting

From *Superforecasting* Chapter 12, plus analysis of which commandments prediction market traders systematically violate.

### Commandment 1: TRIAGE
**"Focus on questions where your hard work is likely to pay off."**

Avoid "clocklike" questions (deterministic, easy to look up) and "cloud-like" questions (inherently unpredictable). Concentrate on the Goldilocks zone — tractable uncertainty.

**Prediction market violation: SEVERE.** Retail traders systematically bet on cloud-like questions (Will there be nuclear war? Will aliens be confirmed?) where no amount of analysis can produce edge. They also bet on clocklike questions (Will Biden be the 2024 nominee?) where the odds already reflect near-certainty, leaving no edge. The Goldilocks zone — where effort matters — is where superforecasters live and retail traders rarely venture.

### Commandment 2: BREAK DOWN INTRACTABLE PROBLEMS
**"Channel the playful but disciplined spirit of Enrico Fermi."**

Decompose questions into knowable and unknowable components. "Flush ignorance into the open." Instead of "Will Russia invade Ukraine?" decompose into: What are Putin's objectives? What are the military indicators? What's the historical base rate for massed-troops-leading-to-invasion? What signals would disconfirm?

**Prediction market violation: SEVERE.** Most traders operate on holistic gut feeling — "this feels like it'll happen" — rather than decomposed analysis. The market price reflects the *aggregate* of many undecomposed estimates, which is why it can be beaten by systematic decomposition.

### Commandment 3: BALANCE INSIDE AND OUTSIDE VIEWS
**"How often do things of this sort happen in situations of this sort?"**

Start with the outside view (base rate from reference class), then adjust with inside-view specifics. Never skip the outside view.

**Prediction market violation: SEVERE.** This is the single most violated commandment. Our S006 research showed 73.5% of "by date" markets resolve NO, yet most traders price YES at 40–60% because they focus on the specific narrative (inside view) rather than the base rate (outside view). The narrative-driven pricing of markets is a direct consequence of skipping this commandment.

### Commandment 4: UPDATE YOUR BELIEFS
**"Belief updating is to good forecasting as brushing and flossing are to good dental hygiene."**

Tease subtle signals from noisy news flows. Resist wishful thinking. Update incrementally — many small updates, not rare large ones.

**Prediction market violation: MODERATE-SEVERE.** Polymarket data shows two failure modes: (a) traders who anchor to their entry price and never update (conservatism), and (b) traders who overreact to every headline (overreaction). Very few exhibit the superforecaster pattern of frequent small updates. Our S004 research found ~40% reversion after 5pp spikes — evidence that markets routinely overreact, then partially correct.

### Commandment 5: LOOK FOR CLASHING CAUSAL FORCES
**"For every good argument, there is typically a counterargument."**

Acknowledge legitimate counterarguments. If you're bullish, steelman the bearish case. Create "dove-hawk" hybrid views.

**Prediction market violation: MODERATE.** Traders tend to be directionally committed. Once they buy YES, they actively seek confirming information and dismiss disconfirming evidence (confirmation bias). The comment sections on Polymarket markets show extreme monoculture — almost no steelmanning of opposing views.

### Commandment 6: DISTINGUISH DEGREES OF DOUBT PRECISELY
**"Translating vague-verbiage hunches into numeric probabilities feels unnatural at first, but it can be done."**

Practice separating 60/40 from 40/60 bets. Use fine-grained probability estimates.

**Prediction market violation: LOW.** Prediction markets force this by design — you must put a number on it. However, many traders still operate with effective 3-bucket thinking (gonna happen, might happen, won't happen) and only grudgingly assign specific prices. The *mechanism* forces precision; the *thinking* often doesn't follow.

### Commandment 7: BALANCE CONFIDENCE AND PRUDENCE
**"Manage the trade-off between the need to take decisive stands and the need to qualify those stands."**

Don't rush to judgment but don't dawdle near "maybe." Commit to positions while remaining qualified.

**Prediction market violation: SEVERE.** The dominant pattern is premature commitment. Traders buy at market open, then hold rather than adjusting as new information arrives. The "disposition effect" (holding losers, selling winners) directly contradicts this commandment. Rarely do traders sit at 50% waiting for clarity — they feel the need to "have a position."

### Commandment 8: EXAMINE FAILURES WITHOUT HINDSIGHT BIAS
**"Own them! Conduct unflinching postmortems."**

Analyze what went wrong without overlearning from failure or overcrediting success from offsetting errors.

**Prediction market violation: SEVERE.** Almost no retail prediction market traders conduct formal postmortems. Winning feels like skill; losing feels like bad luck. Without scorecards or calibration tracking, there is no learning loop. The 70% of Polymarket traders who lose money are, by definition, not learning from failures at sufficient rates.

### Commandment 9: LEVERAGE TEAM DYNAMICS
**"Master perspective-taking, precision questioning, and constructive disagreement."**

Teams of superforecasters beat individual superforecasters. Diverse perspectives, properly aggregated, improve accuracy.

**Prediction market violation: MODERATE.** Some traders participate in Discord/Telegram groups that approximate team forecasting, but these tend toward echo chambers rather than constructive disagreement. The market itself is a form of aggregation, but individual traders within it rarely benefit from the team dynamics Tetlock describes.

### Commandment 10: MASTER THE ERROR-BALANCING BICYCLE
**"You can't become a superforecaster by reading training manuals."**

Every commandment requires balancing opposing errors. Too much outside view → ignoring genuine uniqueness. Too much updating → instability. The balance is learned through deliberate practice with unambiguous feedback.

**Prediction market violation: MODERATE.** The market provides unambiguous feedback (you win or lose money), but traders rarely engage in *deliberate* practice. They repeat the same patterns without systematic reflection. The feedback loop exists but isn't utilized.

### The 11th Commandment
**"Don't treat commandments as commandments."**

Helmuth von Moltke: "It is impossible to lay down binding rules because two cases will never be exactly the same." These are guidelines, not laws. Flexibility and contextual judgment remain paramount.

---

## 3. Calibration Frameworks

### The Brier Score

Developed by Glenn Brier (1950) for weather forecasting. For binary outcomes:

```
Brier Score = (probability_assigned - outcome)²
```

Where outcome = 1 if event happened, 0 if not. Averaged across all forecasts.

**Score interpretation:**
- **0.0** = Perfect (assigned 100% to everything that happened, 0% to everything that didn't)
- **0.25** = Random guessing (always saying 50%)
- **0.50** = Maximum *possible* score using random assignment
- **1.0** = Perfectly wrong (100% on everything that didn't happen)
- **2.0** = Maximum score (for multi-outcome version)

Note: Some sources define Brier score as the mean squared error where the max is 1.0 (binary version). The IARPA tournament used the binary version.

### Brier Score Decomposition (Murphy 1973)

The Brier score can be decomposed into three components:

```
Brier Score = Calibration - Resolution + Uncertainty
```

- **Calibration** (reliability): When you say 70%, does it happen 70% of the time? Lower = better. Perfect calibration = 0.
- **Resolution** (discrimination): Do your probability estimates vary appropriately with actual outcomes? Higher = better. Can you separate likely events from unlikely ones?
- **Uncertainty**: Base rate variability of the events being forecast. Not under forecaster control.

**For superforecasters:**
- Calibration: ~0.01 (their probabilities deviate from outcomes by just ~1 percentage point)
- Resolution: High (they appropriately give extreme probabilities to extreme outcomes)
- Overall Brier: 0.15–0.16

### Calibration Curves (Reliability Diagrams)

The visual tool for assessing calibration:
- X-axis: Predicted probability (binned: 0-10%, 10-20%, etc.)
- Y-axis: Observed frequency of outcome
- Perfect calibration = diagonal line (45°)
- Points above the line = underconfidence (events happen more than predicted)
- Points below the line = overconfidence (events happen less than predicted)

**Typical prediction market pattern**: S-curve rather than diagonal. Overconfident in the extremes (90% events happen ~85% of the time) and slightly underconfident in the middle. This IS the favorite-longshot bias, visible in the calibration curve.

### What CHAMP Is

Note: "CHAMP" does not appear to be a specific Tetlock calibration framework. The term may be confused with other forecasting mnemonics. Tetlock's actual calibration recommendations are:

1. **Track every prediction** with a timestamp and probability
2. **Score with Brier scores** after resolution
3. **Plot calibration curves** to find systematic biases
4. **Decompose** into calibration + resolution components
5. **Compare to baselines** (random = 0.25, outside-view-only, market price)

### Performance Benchmarks for Prediction Market Context

| Performance Level | Brier Score | Description |
|-------------------|-------------|-------------|
| Superforecaster | 0.14–0.17 | Top 2% of GJP |
| Trained forecaster | 0.20–0.25 | 1-hour training intervention |
| Average forecaster | 0.30–0.35 | Untrained but engaged |
| Intelligence analysts | 0.25–0.30 | Classified information access |
| Random guessing | 0.25 (binary) | Always 50% |
| Prediction market prices | 0.20–0.30 | Varies by market maturity |

---

## 4. Base Rate Anchoring

### The Core Problem: Inside View Dominance

Kahneman (*Thinking, Fast and Slow*, 2011, Ch. 23–24) describes the **planning fallacy**: people generate optimistic forecasts by extrapolating from an "inside view" — a detailed, scenario-based simulation of the focal case — while neglecting the "outside view" derived from distributions of outcomes in analogous reference classes.

**System 1** (fast, intuitive) generates narrative-driven inside views automatically.
**System 2** (slow, deliberate) is needed to override with statistical outside views, but it's lazy and rarely intervenes unless explicitly activated.

### Reference Class Forecasting: The Three Steps

Developed theoretically by Kahneman & Tversky (1977, 1979). Operationalized by Flyvbjerg & COWI (2004). Adopted by the UK Department for Transport (2004) and later mandated for major projects.

**Step 1: Identify the reference class**
Find a class of similar past situations. Must be broad enough for statistical significance, narrow enough for genuine similarity. E.g., "international trade negotiations with tariff deadlines" or "markets asking 'will X happen by date Y?'"

**Step 2: Establish probability distribution**
What fraction of the reference class had each outcome? This gives the base rate. E.g., our S006 finding: 73.5% of "by date" markets resolve NO.

**Step 3: Position the specific case within the distribution**
Compare the focal case to the reference class. Are there genuine reasons to think this case is above or below average? Adjust from the base rate, but modestly — anchoring bias means you'll under-adjust, and that's usually still better than ignoring the base rate entirely.

### Why Base Rates Protect Against Biases

| Bias | How base rate anchoring counters it |
|------|--------------------------------------|
| **Availability** | "I can easily recall X happening" → base rate shows X is actually rare |
| **Representativeness** | "This looks like X" → base rate shows matching cases usually resolve differently |
| **Narrative** | "The story for X is compelling" → base rate: compelling narratives are wrong Y% of the time |
| **Anchoring on market price** | "The market says 55%" → base rate: events like this happen only 27% of the time |
| **Optimism bias** | "This time is different" → base rate: it almost never is |
| **Confirmation bias** | "I found 3 reasons for YES" → base rate: 73.5% of similar markets resolve NO |

### Flyvbjerg's Findings on Optimism Bias

From analysis of major infrastructure projects worldwide:
- **Cost overruns**: 9 out of 10 projects exceed budget (average overrun: 28% for roads, 45% for rail, 20% for bridges)
- **The cause**: Inside-view planning ("our project is different") vs. outside-view reality (almost no projects come in under budget)
- **The fix**: Reference class forecasting reduces overruns significantly

Kahneman called Flyvbjerg's work "the single most important piece of advice regarding how to increase accuracy in forecasting."

### Application to Prediction Markets

Our reference class data already shows:
- **73.5% of "by date" markets resolve NO** (S006 base rate)
- **58% of markets show negative serial correlation** (S004 base rate)
- **Markets in ENV domain: 82.4% NO rate** for deadline markets
- **Markets in ECO domain: most efficient** (sophisticated participants)

The trader who starts from these base rates and adjusts modestly based on specifics will systematically outperform the trader who starts from "what does this market feel like?"

---

## 5. The Updating Problem

### The Bayesian Ideal

Bayes' theorem prescribes exactly how beliefs should update on new evidence:

```
P(H|E) = P(E|H) × P(H) / P(E)
```

Where:
- P(H) = prior probability of hypothesis
- P(E|H) = likelihood of evidence given hypothesis is true
- P(E) = total probability of evidence
- P(H|E) = posterior probability after seeing evidence

**The ideal updater:**
- Starts with a calibrated prior (base rate)
- Weighs evidence by its *diagnosticity* (how much it distinguishes between hypotheses)
- Updates incrementally as each piece of evidence arrives
- Ends at the same posterior regardless of the *order* evidence was received

### Human Reality: Two Opposing Errors

**Error 1: Conservatism (Under-Reaction)**

Edwards (1968) established that humans are "conservative Bayesians" — they update in the correct direction but with insufficient magnitude. Typical under-reaction: people update at **50–75% of the Bayesian-optimal rate** in controlled experiments.

Evidence for conservatism dominance:
- Anchoring heuristic (Tversky & Kahneman, 1974): Initial estimates serve as anchors from which adjustment is insufficient
- Endowment effect applied to beliefs: Once held, beliefs feel like possessions
- In financial markets: investors systematically under-react to earnings announcements, dividend changes, stock splits (post-event drift)
- In the IARPA tournament: **underreaction was a larger threat to accuracy than overreaction** (Atanasov et al., 2020)

**Error 2: Base-Rate Neglect / Over-Reaction**

Representativeness heuristic (Kahneman & Tversky, 1972): When new information is vivid, salient, or narrative-fitting, people overweight it relative to base rates. They jump to new conclusions too quickly.

Evidence for overreaction:
- Availability heuristic amplifies vivid evidence
- In prediction markets: 5pp+ price spikes show ~40% reversion within 7 days (our S004 finding)
- Financial markets: overreaction to news, momentum followed by reversal
- The "surprise effect": extremely surprising information causes *overweighting* rather than underweighting (Bayesian conservatism flips when evidence is shocking)

### The Critical Insight: It Depends on the Evidence Type

Edwards' (1968) finding and our prediction market data are *both* right because different evidence types trigger different errors:

| Evidence Type | Typical Error | Example |
|---------------|---------------|---------|
| Statistical / abstract | Conservatism (under-react) | Gradual shift in polling averages |
| Vivid / narrative / shocking | Overreaction | War declaration, scandal, dramatic statement |
| Confirmatory of current belief | Conservatism (anchor harder) | More evidence for what you already think |
| Disconfirmatory | Either: dismiss (conservatism) or panic-flip (overreaction) | Evidence against your position |
| Incremental / drip-feed | Conservatism | Slow accumulation of small signals |
| Sudden / discontinuous | Overreaction | Binary event: deal/no-deal, invade/don't |

### What Superforecasters Actually Do

From "Small Steps to Accuracy" (Atanasov, Witkowski, Ungar, Mellers & Tetlock, 2020, *Organizational Behavior and Human Decision Processes*):

**Key finding: Incremental updaters are ~30% more accurate (lower Brier) than large-jump updaters.**

Data: 515 forecasters, 80,000+ forecasts, 487 geopolitical questions.

The three dimensions of updating:
1. **Frequency**: More frequent updaters are more accurate
2. **Magnitude**: Smaller average update size → better accuracy (strongest predictor)
3. **Confirmation propensity**: Lower tendency to update only in confirming direction → better accuracy

**The superforecaster updating pattern:**
- Many small updates (1–3 percentage points)
- Occasional larger updates when evidence is genuinely diagnostic
- Updates in both directions (not just confirming)
- Updates triggered by *evidence*, not *emotion*
- Typical update frequency: multiple times per question per week

**Contrast with typical prediction market behaviour:**
- Infrequent, large position changes (buy/sell, not adjust)
- Anchored to entry price rather than current evidence
- Updates triggered by price movement (herding) rather than information
- Asymmetric updating: quick to update toward desired outcome, slow to update away

### The Right Mental Model: The Bayesian Dial

Tetlock uses the metaphor of a dial rather than a switch. Instead of being "for" or "against" a proposition (switch thinking), superforecasters have a dial they turn gradually.

**Practical rules from the research:**

1. **Start at the base rate.** (Outside view / Commandment 3)
2. **For each piece of evidence, ask: How diagnostic is this?** A diagnostic piece of evidence should move the dial. A piece that's equally likely under both hypotheses shouldn't move it at all.
3. **Default to small moves** (1–5 percentage points). Large moves (10+ pp) require genuinely surprising, highly diagnostic evidence.
4. **Update on absence too.** If something would have happened by now if the hypothesis were true, and it hasn't, that's evidence. Adjust down.
5. **Track the direction.** If you've only been moving the dial in one direction, you're probably exhibiting confirmation bias. Actively seek disconfirming evidence.
6. **The "crowd within" technique**: Make your estimate, wait, then re-estimate from scratch. Average the two. This mimics the benefit of aggregation.

### Conservatism vs. Overreaction: The Balancing Act

This IS Commandment 10 (the error-balancing bicycle) applied to updating.

**Signs you're being too conservative:**
- You haven't updated in a week despite new information
- You can articulate the new evidence but your number hasn't changed
- Your number has changed by less than 2pp on genuinely surprising news
- You're thinking "this doesn't change anything" about evidence that changes things for others

**Signs you're overreacting:**
- Your estimate moved 10+ pp on a single data point
- You're updating based on price movement rather than information
- You changed your estimate in the same direction as the crowd on the same day
- You can't articulate *what specifically* the new evidence is (you're updating on vibes)

**The sweet spot:**
- Edwards (1968): Optimal Bayesian update on moderate evidence ≈ 5–15% shift
- Actual human update on same evidence ≈ 2–8% (conservative)
- Ideal for prediction markets: aim for 3–10% updates on genuinely diagnostic evidence
- Reserve 15%+ moves for binary revelations (deal signed, war declared, resignation announced)

---

## Summary: What This Means for Our Trading

### The Superforecasting Edge Applied to Prediction Markets

1. **Base rate first, always** — Before entering any market, find the reference class and its resolution rate. Our S006 data (73.5% NO for "by date" markets) is exactly this.

2. **Decompose before pricing** — Fermi-ize every trade thesis into component questions. "Will Russia-Ukraine ceasefire by March?" becomes: What % of similar negotiations succeed? What's the timeline pressure? What are the indicators of progress? What would disconfirm?

3. **Update in small steps** — Position sizing should allow for gradual adjustment rather than binary buy/sell. The superforecaster pattern (many small updates) maps to active position management rather than set-and-forget.

4. **Track calibration** — Our `calibration/resolutions.jsonl` with 12 entries is a start. Need 50+ resolved predictions with Brier scoring to detect our systematic biases.

5. **The 70% finding** — 70% of Polymarket traders lose money. This is the population that provides our edge. They violate every commandment: no triage, no decomposition, no base rates, infrequent updating, no postmortems. Our job is to be on the other side of their systematic errors.

### Commandment Violation Severity (for our strategy prioritization)

| Commandment | Market Violation Severity | Our Strategy Exploiting It |
|-------------|--------------------------|---------------------------|
| 3. Outside view / base rates | SEVERE | S006 (time decay), all strategies |
| 2. Decomposition | SEVERE | All strategies (structural advantage) |
| 1. Triage | SEVERE | Strategy selection discipline |
| 4. Belief updating | MODERATE-SEVERE | S004 (overreaction), S006 (decay) |
| 8. Postmortems | SEVERE | Calibration system |
| 7. Confidence/prudence | SEVERE | S004 (premature commitment) |
| 5. Clashing forces | MODERATE | S007 (arb = clashing views) |
| 10. Error-balancing | MODERATE | Meta-strategy |
| 9. Teams | MODERATE | N/A (solo trader) |
| 6. Numeric precision | LOW | Forced by market mechanism |

---

## Sources

### Books
- Tetlock, P.E. (2005). *Expert Political Judgment: How Good Is It? How Can We Know?* Princeton University Press.
- Tetlock, P.E. & Gardner, D. (2015). *Superforecasting: The Art and Science of Prediction.* Crown.
- Kahneman, D. (2011). *Thinking, Fast and Slow.* Farrar, Straus and Giroux.

### Key Academic Papers
- Mellers, B., Stone, E., Atanasov, P., et al. (2015). "The Psychology of Intelligence Analysis: Drivers of Prediction Accuracy in World Politics." *Journal of Experimental Psychology: Applied.*
- Mellers, B., Tetlock, P., et al. (2015). "Identifying and Cultivating Superforecasters as a Method of Improving Probabilistic Predictions." *Perspectives on Psychological Science.*
- Atanasov, P., Witkowski, J., Ungar, L., Mellers, B. & Tetlock, P. (2020). "Small Steps to Accuracy: Incremental Belief Updaters Are Better Forecasters." *Organizational Behavior and Human Decision Processes*, 160, 19-35.
- Edwards, W. (1968). "Conservatism in Human Information Processing." In Kleinmuntz (Ed.), *Formal Representation of Human Judgment.*
- Kahneman, D. & Tversky, A. (1979). "Intuitive Prediction: Biases and Corrective Procedures." *TIMS Studies in Management Science*, 12, 313-327.
- Flyvbjerg, B. & COWI (2004). "Procedures for Dealing with Optimism Bias in Transport Planning." UK Department for Transport.
- Flyvbjerg, B. (2006). "From Nobel Prize to Project Management: Getting Risks Right." *Project Management Journal*, 37(3), 5-15.

### Web Sources
- [Good Judgment: Ten Commandments for Aspiring Superforecasters](https://goodjudgment.com/philip-tetlocks-10-commandments-of-superforecasting/)
- [Good Judgment: The Superforecasters' Track Record](https://goodjudgment.com/resources/the-superforecasters-track-record/)
- [Farnam Street: Ten Commandments for Superforecasters](https://fs.blog/ten-commandments-for-superforecasters/)
- [AI Impacts: Evidence on Good Forecasting Practices from the GJP](https://aiimpacts.org/evidence-on-good-forecasting-practices-from-the-good-judgment-project/)
- [LessWrong: Ten Commandments for Aspiring Superforecasters](https://www.lesswrong.com/posts/dvYeSKDRd68GcrWoe/ten-commandments-for-aspiring-superforecasters)
- [Commoncog: How the Superforecasters Do It](https://commoncog.com/how-the-superforecasters-do-it/)
- [Wikipedia: The Good Judgment Project](https://en.wikipedia.org/wiki/The_Good_Judgment_Project)
- [Wikipedia: Conservatism (belief revision)](https://en.wikipedia.org/wiki/Conservatism_(belief_revision))
- [Kalshi: The 10 Commandments of Superforecasting](https://news.kalshi.com/p/10-commandments-of-superforecasting)
- [Ipsos: How Overconfidence Fuels Risk in Prediction Markets](https://www.ipsos.com/en-us/future/how-overconfidence-fuels-indulgence-risk-prediction-markets)
- [QuantPedia: Systematic Edges in Prediction Markets](https://quantpedia.com/systematic-edges-in-prediction-markets/)
- [Superforecasting Reality Check (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC7333631/)
