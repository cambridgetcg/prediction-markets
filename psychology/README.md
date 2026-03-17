# Psychological Layer

**The thesis**: Prediction market prices are not pure probability estimates. They are the output of a pipeline: news → emotional response → betting behaviour → market price. Understanding the psychology at each stage reveals where the price diverges from reality. That gap is the edge.

```
NEWS EVENT
    ↓ [What emotion does this trigger?]
EMOTIONAL RESPONSE
    ↓ [Which biases amplify it?]
BETTING BEHAVIOUR
    ↓ [How does that behaviour move the price?]
MARKET PRICE  ←——————— REALITY (base rate probability)
    ↓                          ↑
    └──────── GAP = EDGE ───────┘
```

## Files

| File | Purpose |
|------|---------|
| `behavioral-foundations.md` | Bias inventory, ECI scoring system, Tetlock framework, Reality Check protocol |
| `news-emotion-price-taxonomy.md` | Maps each news category → emotion → distortion → strategy |
| `participant-profiles.md` | Who bets in each domain, and what biases they carry |
| `discrepancy-database.jsonl` | Live log of cases where emotion diverged from reality |
| `pattern-library.md` | Named, reusable patterns (e.g. "War Panic Premium") |
| `emotional-market-scanner-spec.md` | Design for a tool that detects emotional premiums in real time |
| `hypothesis-tests.md` | Quantitative validation of the framework's predictions |
| `alpha-attribution.md` | For each position: how much edge is psychological vs informational vs structural |
| `anti-patterns.md` | Cases where following psychology would be a trap |

## The Prompts

- **B01**: Build the foundations — run first
- **B02**: Build the taxonomy and database — run after B01  
- **B03**: Use live — run whenever significant news breaks or a market moves ≥8%
- **B04**: Calibrate the models quantitatively — run when 15+ predictions have resolved

## The Five Patterns We Already Know

From our own trading experience, before B01-B04 are even run:

1. **War Panic Premium** — Military headlines → fear → YES overpriced by 5-15pp → S004 NO
2. **Rally-vs-Formal Address Confusion** — Retail prices rally language into formal speeches (SOTU, press conferences) → 30-50pp overpricing of rally words → S003 NO
3. **Deadline Inflation** — Political ultimatums treated as military triggers → YES overpriced → decays as deadline passes without action → S006 + S004
4. **Constitutional Impossibility Premium** — Tribalism keeps impossible candidates at 2-5% → slow decay → S007 arb
5. **Convergence Direction Surprise** — When two markets diverge (CME vs Polymarket), don't assume the less sophisticated market is wrong — sometimes it's more accurate on tail probabilities → caution on automatic S003 entries
