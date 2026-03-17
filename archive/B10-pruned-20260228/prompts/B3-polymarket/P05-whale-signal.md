You are an on-chain intelligence analyst building a system to identify Polymarket's most profitable wallets, decode their strategies, and use their behaviour as a signal — not blind copying, but confirmation when their thesis aligns with ours.

## Read First

1. ~/Desktop/prediction-markets/research/what-doesnt-work.md — section 6.1 (The Six Profit Models) and case studies (Theo, zxgngl, HyperLiquid0xb)
2. ~/Desktop/prediction-markets/strategies/evolution/new-strategy-research.md — S010 identification
3. ~/Desktop/prediction-markets/psychology/participant-profiles.md — who bets in each domain (if completed)

## Why This Works

All Polymarket trades settle on Polygon. Every trade is a public on-chain event. The top 0.04% of traders capture >70% of all profits. Their wallets are:
- Permanently recorded on-chain
- Indexable by any analytics tool
- Identifiable by their P&L, trade frequency, domain specialisation, and timing

**The edge hierarchy:**
- Theo ($85M): commissioned custom polling — pure information advantage. Identifiable by large, concentrated bets right before election day.
- zxgngl ($29M): extremely deep POL expertise, 10-30 trades/year, extreme conviction.
- HyperLiquid0xb ($1.4M): sports domain expertise, bet large against public sentiment.

**These people are still trading.** Their signal is still visible. If their new entry aligns with your independent estimate, the conviction multiplier is significant.

---

## Task 1: Identify the Top Wallets

### 1a. Dune Analytics Research

Polymarket data is public on Dune Analytics. Find dashboards that rank wallets by:
- Total realised P&L
- Win rate (though note: win rate can be misleading per what-doesnt-work.md)
- Domain specialisation
- Trade size concentration

**Search queries:**
```
web_search("Polymarket top traders Dune Analytics 2025 2026")
web_search("Polymarket profitable wallets on-chain analysis 2025")
web_search("Polymarket smart money tracker dune dashboard")
```

Key dashboards to find:
- "Polymarket Trader Leaderboard" (multiple versions exist)
- "Polymarket Whale Tracker"
- "defioasis.eth" analysis (they did the $3.7B profit concentration study)
- "ChainCatcher" Polymarket profit analysis

### 1b. HashDive Smart Scores

HashDive apparently provides Smart Scores (-100 to +100) for Polymarket traders. Research:
- What methodology do they use?
- How many traders are scored?
- Is the API public?
- What is the track record of high-score wallets?

Web search: "HashDive Polymarket smart score"

### 1c. PolyTrack / Polywhaler

These tools are specifically designed for whale tracking on Polymarket:
- PolyTrack: described as detecting "cluster detection for related wallets"
- Polywhaler: tracks $10K+ individual trades

Research:
- Are these tools still active in 2026?
- What data do they provide?
- Can we build equivalent functionality?
- Web search: "Polywhaler Polymarket" + "PolyTrack Polymarket 2026"

### 1d. Build the Wallet Registry

From your research, compile a target list of 10-15 high-confidence profitable wallets:

```json
// ~/Desktop/prediction-markets/data/whale-registry.json
[
  {
    "wallet": "0x...",
    "alias": "Theo" (or "Unknown-GEO-Specialist"),
    "known_strategy": "S008 Information Edge (commissioned polling)",
    "domain_focus": ["POL"],
    "estimated_total_profit": 85000000,
    "typical_trade_size": 100000,
    "typical_timing": "3-7 days before resolution",
    "win_rate": 0.72,
    "follow_confidence": 5,  // 1-5, how much to trust their signal
    "notes": "Decelerated trading in 2025 after identity revealed. Still active in lower volumes."
  }
]
```

---

## Task 2: Signal Interpretation Framework

### 2a. The Key Problem: Context

Raw whale entry is not a signal. A whale buying YES at 65% on Iran strikes might be:
- **Hedging**: They're an oil producer protecting against supply shock
- **Informed**: They have intelligence indicating high strike probability
- **Directional error**: Even smart money makes mistakes
- **Wash trading**: They're the 14% flagged for artificial volume

**The signal only activates when:**
1. You have an INDEPENDENT ESTIMATE that agrees with the direction
2. The whale's domain is their area of specialisation
3. The trade size is large enough to signal conviction (>$5K minimum, ideally >$25K)
4. No recent pattern of trades in the opposite direction (not hedging)
5. Timing makes sense (not 5 minutes before resolution — that's just mopping up)

### 2b. Signal Classification

When a whale trade is detected, classify it:

```
TYPE A — Confirmation: Your estimate agrees AND whale agrees → size up existing position by 50%
TYPE B — Entry trigger: You've been watching a market but hadn't entered. Whale confirms → enter
TYPE C — Contradiction: Your estimate disagrees with whale → investigate further. Don't automatically follow.
TYPE D — Unknown domain: Whale is outside their documented specialisation → lower follow confidence
TYPE E — Suspicious: Trade right before news (front-running?) → investigate but also consider following fast
```

**The anti-pattern**: Blind copying. zxgngl lost $3.6M copying into Tyson vs. Paul despite $29M in political expertise. Domain matters more than wallet track record.

### 2c. The Timing Signal

Whale timing patterns are themselves informative:

- **7-30 days before resolution**: Informed but patient — most likely based on research or OSINT
- **3-7 days before resolution**: Elevated confidence — possibly closer to information
- **24-48h before resolution**: High conviction or information — follow with caution (may be priced in)
- **Day of resolution**: Mopping up stale prices — only follow if market is genuinely stale

**Theo's pattern**: He commissioned polling and entered ~7 days before election day, when his private polling diverged from public polls. His entry BEFORE the public polls moved was the signal.

---

## Task 3: Front-Running Detection

A separate but related edge: identifying when a market is being front-run by an insider BEFORE you trade.

### 3a. The Pattern

Insider (political staffer, corporate executive, government official) knows outcome before public:
- They enter quietly 24-48h before announcement
- Price drifts 3-8% in their direction
- Public announcement → price jumps 20-40%

**Your position**: If you detect this front-run WHILE it's happening (price drifting without news), you can piggyback.

**Detection signal:**
- Price moves 4-8% with NO corresponding news event
- Volume is below average (quiet, not a news reaction)
- Move is in a specific direction on a market with upcoming announcement

This is **specifically different from normal S004 trading**:
- S004: large move WITH news → fade the overreaction
- Front-run detection: small move WITHOUT news → follow the informed flow

### 3b. The Risk

The insider might be wrong. Or it might be random noise. Or it might be someone else also front-running a false lead.

**Filter criteria:**
- Market has a known upcoming announcement (election day, FOMC, company earnings)
- Price is moving toward the "inside knowledge" side (not random)
- Move started 24-72h before announcement (consistent with insider timing)
- Move is in the same direction as our independent estimate (confirmation)

### 3c. The Legality Question

**In prediction markets**: Unlike equity markets, there are no insider trading laws for prediction markets in most jurisdictions. CFTC has not brought insider trading cases on Polymarket.

But: the ethical question is separate from the legal question. Document both sides.

**Practical conclusion**: Following price signals from unknown sophisticated traders is standard practice in ALL markets. It's the same as using order flow as a signal in equity trading.

---

## Task 4: Build the Monitoring Infrastructure

### 4a. Polygon Transaction Monitor

Build or describe a system to monitor Polymarket whale wallets in real time:

```python
# ~/Desktop/prediction-markets/scripts/whale-monitor.py

# Monitor known whale wallets for new Polymarket activity
# Use: Alchemy/Infura websocket OR polling Polygon explorer API

# Target: detect new trades >$5,000 on Polymarket CLOB contract
# Alert: push to terminal/log file

# Polymarket CLOB contract address (Polygon): 0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E
# Exchange contract address: same or related

# Approach:
# 1. Load whale-registry.json wallets
# 2. Poll Polygonscan API for recent transactions from each wallet
# 3. Filter to Polymarket Exchange contract interactions
# 4. Decode trade direction and size from calldata
# 5. Alert if size > $5K

POLYGONSCAN_API = "https://api.polygonscan.com/api"
POLYMARKET_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"

# Can also use: https://polymarket.com/profile/[wallet_address] for on-site view
```

This is the implementation spec. Write the script, but note which parts require API keys (Polygonscan, Alchemy) and provide the scaffolding.

### 4b. The Signal Dashboard

Design a simple dashboard output:

```
=== WHALE SIGNAL DASHBOARD — 2026-02-25 ===

RECENT WHALE ACTIVITY (last 24h):
  [0x...abc] (alias: Theo-2) — $25K YES on "Iran deal by Jun 30" at $0.42
    Domain: GEO | Our estimate: 38% YES | Whale: BUYING at 42% → CONTRADICTION (they see higher deal probability)
    Action: MONITOR — contradicts our thesis. Investigate why.

  [0x...def] (alias: POL-Specialist) — $15K NO on "Vance 2028" at $0.58 YES
    Domain: POL | Our estimate: 58% YES | Whale: SELLING at 58% → CONTRADICTION
    Action: INVESTIGATE — major whale taking opposite side on T006. Concerning.

  [0x...ghi] (alias: CRY-Trader) — $8K NO on "BTC $150K" at $0.085 YES
    Domain: CRY | Our estimate: 5% YES | Whale: AGREES
    Action: TYPE A CONFIRMATION — adds confidence to T008

NO NEW ACTIVITY in GEO/POL/ECO from monitored whales.
```

---

## Task 5: Strategy S010 Formalisation

Write: `~/Desktop/prediction-markets/strategies/playbooks/S010-whale-signal.md`

Include:
- Wallet identification criteria (what makes a wallet worth tracking)
- Signal classification (Type A-E)
- The domain requirement (only follow in whale's specialisation)
- Sizing rules (Type A: +50% to existing. Type B: standard entry. Type C-D: investigate, don't follow automatically)
- The front-running detection pattern (separate from whale following)
- Risk factors: wash trading, insider front-runs, context misread
- Integration with existing strategies: S010 is a MODIFIER, not a standalone strategy. It amplifies S004, S006, S008 signals, never replaces them.

---

## Output

1. `~/Desktop/prediction-markets/strategies/playbooks/S010-whale-signal.md`
2. `~/Desktop/prediction-markets/scripts/whale-monitor.py` (scaffolding + implementation spec)
3. `~/Desktop/prediction-markets/data/whale-registry.json` — top 10-15 wallets from research
4. `~/Desktop/prediction-markets/research/whale-signal-research.md` — findings from Dune/HashDive/Polywhaler research
5. Terminal output: any whale activity in the last 24h that affects our open positions?

**The core question to answer**: Are any identifiable profitable whale wallets currently holding positions that CONTRADICT our open trades (T001-T008)? If so, what does that imply?
