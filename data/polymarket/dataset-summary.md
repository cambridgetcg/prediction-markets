# Polymarket Resolved Markets Dataset

Generated: 2026-02-24 09:55 UTC

## Overview
- **Total resolved markets**: 10968
- **Resolved YES**: 2318 (21.1%)
- **Resolved NO**: 8639 (78.8%)
- **Ambiguous**: 11
- **Avg duration**: 64 days
- **Median duration**: 17 days

> **Finding**: YES is systematically overpriced. 78.8% of markets resolve NO.

## "By Date" Markets (Time Decay Subset)
- Total: 741
- Resolved YES: 214
- Resolved NO: 527 (71.1% NO rate)

## Distribution by Domain

| Domain | Markets | YES | NO | NO Rate | Total Volume |
|--------|---------|-----|-----|---------|-------------|
| POL    |    3368 | 404 | 2964 |  88.0% | $11,316,594,437 |
| OTHER  |    3318 | 638 | 2671 |  80.5% | $5,639,166,015 |
| CRY    |    2908 | 967 | 1939 |  66.7% | $2,632,070,537 |
| GEO    |     669 | 189 | 480 |  71.7% | $1,279,990,785 |
| TEC    |     305 |  35 | 270 |  88.5% | $ 395,243,317 |
| ECO    |     108 |  25 |  83 |  76.9% | $2,601,559,644 |
| SOC    |     101 |   8 |  93 |  92.1% | $  89,011,257 |
| FIN    |      81 |  15 |  66 |  81.5% | $ 289,648,893 |
| LAW    |      68 |  29 |  39 |  57.4% | $  36,823,728 |
| ENV    |      33 |   7 |  26 |  78.8% | $  24,564,970 |
| SCI    |       9 |   1 |   8 |  88.9% | $  21,949,133 |

## Distribution by Volume

| Bucket | Markets | YES | NO | NO Rate |
|--------|---------|-----|-----|---------|
| <$50K       |     971 | 191 | 775 |  79.8% |
| $50K-$250K  |    3211 | 580 | 2630 |  81.9% |
| $250K-$1M   |    4015 | 842 | 3171 |  79.0% |
| $1M+        |    2771 | 705 | 2063 |  74.4% |

## Quick Analysis

### 1. Is YES systematically overpriced?
**YES.** 78.8% of all resolved markets resolve NO. This confirms systematic overpricing of YES outcomes.

### 2. Do high-volume markets resolve differently?
- $1M+ markets NO rate: 74.5%
- <$50K markets NO rate: 80.2%
- High-volume markets are **more efficient** (lower NO rate = less overpricing)

### 3. Domain-level differences
Domains with enough data for statistical significance (n>20):
- **POL**: 3368 markets, 88.0% NO rate
- **OTHER**: 3318 markets, 80.5% NO rate
- **CRY**: 2908 markets, 66.7% NO rate
- **GEO**: 669 markets, 71.7% NO rate
- **TEC**: 305 markets, 88.5% NO rate
- **ECO**: 108 markets, 76.9% NO rate
- **SOC**: 101 markets, 92.1% NO rate
- **FIN**: 81 markets, 81.5% NO rate
- **LAW**: 68 markets, 57.4% NO rate
- **ENV**: 33 markets, 78.8% NO rate
