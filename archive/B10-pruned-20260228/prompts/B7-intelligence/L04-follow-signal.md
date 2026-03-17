# L04 — Follow Signal: When to Follow, How to Size

You are a trading strategist. L01-L03 have built your intelligence foundation: you know which accounts have statistically significant, localised edge and what field they operate in. L04's job is the last-mile problem: **when one of these accounts opens a new position in their dominant field, how do you decide to follow, and how much to stake?**

Following blindly is as dangerous as ignoring the signal. This prompt builds the decision framework.

## Read First

1. `~/Desktop/prediction-markets/data/classified-insiders.json` — output from L03 (required)
2. `~/Desktop/prediction-markets/strategies/playbooks/S010-whale-signal.md` — existing whale signal framework (L04 extends and may supersede parts of this)
3. `~/Desktop/prediction-markets/strategies/BANKROLL.md` — sizing constraints (never violate these)
4. `~/Desktop/prediction-markets/prompts/intelligence/L02-insider-fingerprint.md` — confidence scores

---

## Task 1: The Follow Decision Framework

### 1a. Gate 1 — Field Match (binary)

The most important check. An insider's edge is ONLY valid in their dominant field.

```python
def field_match(new_bet_market_subdomain, insider_primary_subdomain):
    """
    Returns True ONLY if the new bet is in the insider's dominant sub-domain.

    Examples:
      POL-Insider-01 (primary: us-republican-primary) bets on:
        "Vance wins 2028 GOP" → MATCH (us-republican-primary)
        "UK general election" → NO MATCH (different POL sub-domain)
        "Bitcoin $150K" → NO MATCH (different category entirely)

    Edge is sub-domain specific. A TEC insider betting on GEO is just
    a random bettor outside their field. Ignore it.
    """
```

**If field doesn't match: DO NOT FOLLOW. End of decision tree.**

This is the single most important rule. zxgngl lost $3.6M ignoring it.

### 1b. Gate 2 — Direction Check

Does the insider's bet direction align or contradict our existing position (if we have one)?

```python
DIRECTION_OUTCOMES = {
    "AGREE_NO_POSITION":  "New entry opportunity. Proceed to sizing.",
    "AGREE_WITH_POSITION": "Confirmation. Consider adding to existing position.",
    "CONTRADICT_POSITION": "Do not blindly follow. Investigate. May need to reassess.",
    "CONTRADICT_STRONG": "Score >= 8.0, same field, opposite direction to our thesis → serious re-evaluation required."
}
```

**For CONTRADICT**: do NOT panic-exit. But do run L03-level analysis on the specific market. Reasons an insider might oppose your thesis:
1. They have information you don't → update toward their direction
2. They're hedging (they have real-world exposure in the opposite direction)
3. They made an error (even insiders are wrong outside their specialty — but this IS their specialty)
4. Your thesis was already wrong before this signal

Weight by: their insider score + how far outside consensus their bet is.

### 1c. Gate 3 — Timing Quality

When in the market lifecycle is their bet?

```python
TIMING_SIGNALS = {
    ">30 days before resolution": {
        "interpretation": "Patient research-based entry. Probably not day-of information.",
        "confidence_modifier": 0.85,  # Slight reduction — they may simply be early/wrong
        "follow": True
    },
    "8-30 days before resolution": {
        "interpretation": "Sweet spot. Informed but not exploiting knowledge of today's news.",
        "confidence_modifier": 1.0,   # Full confidence
        "follow": True
    },
    "2-7 days before resolution": {
        "interpretation": "High conviction. May be acting on specific pre-announcement knowledge.",
        "confidence_modifier": 1.15,  # Elevated — strong signal
        "follow": True  # But price may already have moved
    },
    "<48h before resolution": {
        "interpretation": "Mopping up stale prices OR day-before announcement insider.",
        "confidence_modifier": 0.5,   # Heavy discount — is the price already reflecting this?
        "follow": "check_price_first"  # Only follow if market hasn't moved to reflect the info
    }
}
```

### 1d. Gate 4 — Market Liquidity / Price Impact

Has the insider's bet already moved the price?

```python
def check_price_impact(market_id, insider_entry_time):
    """
    Compare:
      price_before = market price 1h before insider's trade
      price_now    = current market price

    If |price_now - price_before| > 5%:
      → The signal is partially priced in.
      → Reduce follow size by the proportion of move that's already occurred.

    If |price_now - price_before| < 1%:
      → Signal is not yet priced in. Full follow confidence.
    """
```

---

## Task 2: Sizing

### 2a. The Insider Conviction Multiplier (ICM)

The ICM is a multiplier on our standard position size (from bankroll management):

```python
def insider_conviction_multiplier(insider):
    """
    Returns a multiplier to apply to our standard size.

    Factors:
    1. Insider Score (from L02): higher score = more trust
    2. Follow Confidence (from L03 dossier): 1-5 rating
    3. N trades in their dominant category: more history = more trust
    4. Timing quality modifier (from Gate 3 above)
    5. Direction (agree = increase, contradict = this function shouldn't run)

    Output range: 0.5× to 2.0× standard position size
    """
    base = 1.0

    # Insider score adjustment (L02 score 0-10)
    score_adj = {(0,4): 0.5, (4,6): 0.8, (6,8): 1.0, (8,10): 1.25}

    # Follow confidence adjustment (L03 dossier 1-5)
    conf_adj = {1: 0.5, 2: 0.7, 3: 1.0, 4: 1.3, 5: 1.6}

    # Sample size adjustment
    n_adj = 0.8 if insider.top_category_n < 20 else 1.0 if insider.top_category_n < 50 else 1.1

    icm = base × score_adj × conf_adj × n_adj × timing_modifier
    return min(2.0, max(0.5, icm))  # Cap between 0.5× and 2.0×
```

### 2b. Bankroll Constraints Still Apply

The ICM multiplies our standard size — but the result still must pass bankroll rules:

```
Standard size (from BANKROLL.md) = quarter-Kelly × edge estimate
ICM-adjusted size = standard_size × ICM

But ALWAYS cap at:
  Max 10% of bankroll per single position (from BANKROLL.md)
  Max 30% per domain
  Max 40% per strategy

If ICM-adjusted size would breach any cap: use the cap, not the ICM size.
The ICM increases confidence in a trade; it doesn't override risk management.
```

### 2c. Agree vs. Adding to Existing Position

Two cases:

**Case 1: No existing position**
```
Enter at: current market price
Size: ICM-adjusted size (subject to bankroll caps)
Note in trade log: "L04 signal — [Insider Alias] — field: [subdomain]"
```

**Case 2: Already have a position, insider agrees**
```
Add to existing position: 25-50% of ICM-adjusted size
  (Don't double — you already have exposure. This is confirmation, not a new thesis)
New average entry = blended price
Cap: total position (original + addition) must still be <= 10% bankroll
Note in trade log: "L04 confirmation — adding to [existing position] — [Insider Alias]"
```

---

## Task 3: Monitoring and Alert Integration

### 3a. Trigger Script

Build a script that runs on schedule and alerts when a follow opportunity appears:

```python
# ~/Desktop/prediction-markets/scripts/l04-follow-monitor.py

"""
L04 Follow Monitor

Runs every 4 hours. Checks all classified insiders for new trades.
For each new trade, runs the 4-gate decision framework.
Outputs actionable alerts to terminal + data/follow-signals.jsonl.

Dependencies:
  - data/classified-insiders.json (L03 output)
  - data/catalyst-calendar.json (for timing context)
  - bankroll/state.json (for current exposure)
  - Gamma API / Polygon for new trade detection
"""

def check_new_trades(insider, since_timestamp):
    """
    Check if insider has made any new trades since last check.
    Return list of new trades with market context.
    """

def run_follow_gates(trade, insider):
    """
    Apply all 4 gates. Return decision object.
    """
    gate1 = field_match(trade.subdomain, insider.primary_subdomain)
    gate2 = direction_check(trade, current_portfolio)
    gate3 = timing_quality(trade, market.resolution_date)
    gate4 = price_impact_check(trade)

    if not gate1: return {"action": "IGNORE", "reason": "field mismatch"}
    # ... continue through gates

def generate_alert(decision, insider, trade):
    """
    Format actionable alert for terminal output and follow-signals.jsonl.
    """
```

### 3b. Alert Format

```
=== L04 FOLLOW SIGNAL — 2026-02-26 14:30 GMT ===

INSIDER: POL-Insider-01 (score: 8.4, conf: 4/5)
FIELD MATCH: ✓  us-republican-primary
MARKET: "Will J.D. Vance win the 2028 Republican presidential nomination?"
THEIR BET: NO at $0.42 — $3,200 deployed (14h ago)
OUR POSITION: YES at $0.58 (T006) — $125 deployed

GATE 1: ✓ Field match (us-republican-primary)
GATE 2: ✗ CONTRADICTION — they bought NO, we hold YES
GATE 3: ✓ Timing OK (>365 days to resolution)
GATE 4: ✓ Price unmoved (market at $0.58 YES — unchanged)

DECISION: INVESTIGATE — do not follow, do not exit yet
ACTION: Run L03 analysis on T006. Why does POL-Insider-01 hold NO
        while our thesis supports YES? Is their entry < $0.42 YES suggesting
        they think probability is materially below current market?
        If investigation confirms their reasoning: consider reducing T006 by 50%.

LOG: data/follow-signals.jsonl → { signal_type: "CONTRADICT", action: "INVESTIGATE" }
===
```

---

## Task 4: Strategy S012 — Insider Follow

The intelligence pipeline deserves its own strategy entry.

Write: `~/Desktop/prediction-markets/strategies/playbooks/S012-insider-follow.md`

Contents:
- Description: follow mathematically-identified insider accounts in their dominant sub-domain
- Entry criteria: all 4 gates pass + ICM >= 0.8
- Position sizing: ICM-adjusted quarter-Kelly, subject to bankroll caps
- Exit criteria: same as underlying thesis. This strategy is a modifier, not a standalone.
- Risk factors: signal already priced in, insider error, hedging behavior, false positive
- Evolution: track L04 signal performance separately in P&L dashboard. Does following insiders actually beat our base rate? Monthly calibration review.
- Anti-patterns: following outside field match (the cardinal sin), ignoring bankroll caps, acting on CONTRADICT signals without investigation

**This is S012 — a new strategy.** Add to strategies/evolution/new-strategy-research.md lineage.

---

## Output

1. `scripts/l04-follow-monitor.py` — monitoring script with 4-gate decision framework
2. `strategies/playbooks/S012-insider-follow.md` — new strategy playbook
3. `data/follow-signals.jsonl` — schema + initial entries from any historical insider bets affecting current open positions
4. Terminal output: run the monitor NOW against all classified insiders. Any follow signals or contradictions vs. our current positions (T001-T008 or current live positions)?
5. Review question: Does POL-Insider-01's NO bet on Vance require us to reassess T006?

**Done when**: The monitor script runs, a S012 playbook exists, and we have a clear verdict on whether any classified insiders are currently holding positions that support or contradict our live trades.
