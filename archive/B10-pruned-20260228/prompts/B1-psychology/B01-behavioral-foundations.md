You are a behavioral economist and prediction market researcher establishing the psychological foundation for a trading system.

## Objective

Build a comprehensive map of how human psychology systematically distorts prediction market prices away from true probabilities. This is the theoretical infrastructure that every subsequent behavioral prompt will build on.

## Read First

1. ~/Desktop/prediction-markets/research/what-doesnt-work.md — existing failure analysis (already catalogues several biases)
2. ~/Desktop/prediction-markets/strategies/playbooks/S004-contrarian-overreaction.md — current overreaction strategy (mentions biases but doesn't model them deeply)
3. ~/Desktop/prediction-markets/strategies/evolution/strategy-domain-matrix.md — understand the domain participant profiles

## Research Tasks

### Task 1: The Bias Inventory

For each cognitive bias below, research and document:
- **Definition** (crisp, 1-2 sentences)
- **Mechanism in prediction markets** (how exactly does it distort prices?)
- **Directional effect** (does it push prices UP or DOWN, and when?)
- **Academic evidence** (at minimum one study showing it exists in forecasting/prediction markets)
- **Detection signal** (how do you *see* it in a price chart or news feed without inside knowledge?)
- **Exploitation method** (which strategy exploits it: S004, S006, S008, or a new approach?)
- **Our own track record** (have we already observed this in our T001-T008 positions?)

**Biases to cover:**

*Availability & Vividness*
- Availability heuristic (Tversky & Kahneman 1973) — vivid recent events inflate probability estimates
- Salience bias — dramatic/emotional events dominate over base rates
- Scope insensitivity — "100 deaths" feels similar to "10,000 deaths" in emotional processing

*Narrative & Pattern*
- Narrative fallacy (Taleb) — coherent stories override base-rate reasoning
- Representativeness heuristic — "this situation looks like X, so probability ≈ P(X)"
- Cluster illusion — people see patterns in random noise, creating false trend narratives

*Social & Identity*
- Motivated reasoning / partisan bias — people assess probability through ideological lens
- Identity-protective cognition — beliefs that threaten group identity are resisted regardless of evidence
- Social proof / herding — others buying = event is likely (especially in low-information environments)
- FOMO (Fear of Missing Out) — fear of missing a move drives premature entry

*Loss & Risk*
- Loss aversion (Kahneman & Tversky) — losses feel ~2x more painful than equivalent gains; creates asymmetric betting
- Fear premium — negative outcomes (war, crash, disaster) are systematically OVERPRICED
- Hope premium — positive, exciting outcomes sometimes OVERPRICED; sometimes underpriced (depends on domain)
- Probability weighting (Prospect Theory) — small probabilities overweighted, large probabilities underweighted
- Pseudocertainty effect — when an outcome seems "nearly certain," people anchor hard and resist new evidence

*Temporal*
- Recency bias — recent events dominate; historical base rates forgotten
- Present bias — imminent events feel more certain than equivalent future events
- Deadline panic — as deadlines approach without event, probability should drop; retail BUYS instead

*Updating*
- Conservatism bias — people update too SLOWLY on new evidence (opposite of overreaction, but common in long-duration markets)
- Confirmation bias — people seek evidence that confirms existing price view
- Anchoring — initial prices anchor all subsequent estimates, even when information changes dramatically
- Belief perseverance — people maintain prior beliefs even in the face of contradicting evidence

*Market-Specific*
- YES bias (documented on Polymarket) — retail systematically overprices YES outcomes
- Favorite-longshot bias — high-probability outcomes underpriced; low-probability outcomes overpriced (or reversed, depending on domain)
- "Action bias" — buying YES feels active; buying NO feels passive, so YES is systematically preferred
- Compound probability neglect — "A then B then C" chains are priced as if probability = P(A) alone

### Task 2: The Bias Interaction Map

Some biases reinforce each other; some cancel. Document the five most important interactions:

Example: Availability heuristic + YES bias + narrative fallacy = **War panic premium** in GEO markets. The vivid news (availability) + coherent story (narrative) + desire to be on the "real" side (YES) combine to systematically overprice strike probability.

Find and document five such compound patterns. Each should be:
- Named (give it a memorable name)
- Mechanistically explained (which biases compound how)
- Domain-specific (which domains is this most dangerous in?)
- Our empirical evidence from T001-T008 or the SOTU retrospective

### Task 3: The Tetlock Calibration Framework

Philip Tetlock's superforecaster research is the most important empirical work on forecasting accuracy. Research and document:

1. **What separates superforecasters from experts?** (Beyond "foxes vs. hedgehogs" — what specific cognitive habits?)
2. **The 10 commandments of superforecasting** — and which ones prediction market traders systematically violate
3. **The CHAMP framework** (or equivalent) for calibration
4. **Base rate first** — how does anchoring on base rates protect against the biases above?
5. **The updating problem** — how should beliefs update on new information? What's the Bayesian ideal vs. the human reality?

**Application**: For each of T001-T009 (our predictions), apply Tetlock's framework:
- Did we anchor on base rates first?
- Did we actively seek disconfirming evidence?
- Did we distinguish "inside view" (specific case) from "outside view" (base rate)?

### Task 4: The Emotional Valence Scale

Design a simple scoring system (1-10 scale or similar) to measure how much "emotional charge" a piece of news carries. The hypothesis: higher emotional charge → bigger deviation from true probability → bigger exploitable gap.

**Dimensions to score:**
- **Fear factor** (1-10): Does this news trigger threat/danger response?
- **Vividness** (1-10): Is the imagery concrete, specific, and dramatic?
- **Narrative coherence** (1-10): Does it fit a compelling story (invasion is coming, market is crashing)?
- **Identity activation** (1-10): Does it activate partisan/in-group identity?
- **Recency shock** (1-10): Is this a sudden departure from prior expectations?
- **Media amplification** (1-10): Is this dominating news coverage?

**Composite score**: Sum or weighted average → the "Emotional Charge Index" (ECI)

**Hypothesis to test**: High ECI news events → prices deviate from fundamentals more → S004 opportunities emerge ~24-72h after ECI spike.

**Calibration using known data**: Score the news events that preceded our T001-T005 entries. Retrospectively, how closely does ECI predict the magnitude of overreaction?

### Task 5: The Reality Check Framework

The opposite of the bias inventory: what would a fully de-biased probability estimate look like?

Design a "Reality Check Protocol" — a set of questions that strips out psychological noise and returns to fundamental probability:

1. **Base rate query**: "How often has this type of event happened in similar historical circumstances?"
2. **Scope check**: "Am I distinguishing adequately between the near-term and long-term window?"
3. **Independence check**: "Am I being influenced by the current price, or forming an independent estimate?"
4. **Inside/Outside view**: "Am I using specific case detail (inside view) or historical base rates (outside view)? Am I combining them appropriately (reference class forecasting)?"
5. **Compound probability check**: "If this requires multiple steps, have I multiplied the probabilities of each?"
6. **Emotional audit**: "What is my emotional reaction to this outcome? Am I correcting for that reaction?"
7. **Devil's advocate**: "What's the strongest argument that the market is RIGHT and I'm wrong?"
8. **The 'Empty Wallet' test**: "If I had to bet my last $100 on this estimate, would I change my probability?"

**Output**: A 1-page "Reality Check" template that can be applied to any market before entry.

---

## Output

Write all findings to: `~/Desktop/prediction-markets/psychology/behavioral-foundations.md`

Structure:
1. **The Bias Inventory** (full table + narrative for each bias)
2. **The Five Compound Patterns** (named, mechanistic, domain-specific)
3. **Tetlock's Framework** (applied to our predictions)
4. **The Emotional Charge Index** (ECI scoring system)
5. **The Reality Check Protocol** (1-page template)
6. **Integration with existing strategies** (how B01 upgrades S004, S006, S008 specifically)

Also update `~/Desktop/prediction-markets/strategies/playbooks/S004-contrarian-overreaction.md` with the ECI trigger condition: "When ECI > 7 AND market moves ≥10%, classify as emotional overreaction."

Use web_search extensively: look for academic papers on prediction market psychology, behavioral finance in forecasting, and Tetlock's superforecasting research. Cite everything.
