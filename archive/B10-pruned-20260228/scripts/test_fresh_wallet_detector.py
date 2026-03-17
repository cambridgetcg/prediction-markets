#!/usr/bin/env python3
"""Tests for B9-02 Fresh Wallet Detector."""

import importlib
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import TestCase, main

# Add scripts dir to path and import hyphenated module name
sys.path.insert(0, str(Path(__file__).parent))
fwd = importlib.import_module("fresh-wallet-detector")

score_fresh_wallet_anomaly = fwd.score_fresh_wallet_anomaly
nearest_catalyst = fwd.nearest_catalyst
detect_clusters = fwd.detect_clusters
classify_domain = fwd.classify_domain
assess_portfolio_impact = fwd.assess_portfolio_impact
assess_cluster_impact = fwd.assess_cluster_impact
create_preliminary_profile = fwd.create_preliminary_profile
save_profile = fwd.save_profile


# ── Test Fixtures ─────────────────────────────────────────────────────

def make_wallet_info(total_txns=3, age_days=5, funded_from_exchange=True,
                     first_deposit_hours_ago=36, funding_source="Coinbase"):
    return {
        "total_txns": total_txns,
        "first_txn_time": (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat(),
        "age_days": age_days,
        "funding_source": funding_source,
        "funded_from_exchange": funded_from_exchange,
        "first_deposit_hours_ago": first_deposit_hours_ago,
    }


def make_catalysts():
    now = datetime.now(timezone.utc)
    return [
        {
            "event": "Iran nuclear talks",
            "date": (now + timedelta(days=2)).strftime("%Y-%m-%d"),
            "domain": "GEO",
            "related_markets": ["US strikes Iran by June 30"],
            "frontrun_window_hours": 48,
            "our_position": "T001 NO"
        },
        {
            "event": "FOMC March meeting",
            "date": (now + timedelta(days=20)).strftime("%Y-%m-%d"),
            "domain": "ECO",
            "related_markets": ["Fed rate decision March 2026"],
            "frontrun_window_hours": 72,
            "our_position": None
        },
        {
            "event": "Expired event",
            "date": (now - timedelta(days=5)).strftime("%Y-%m-%d"),
            "domain": "POL",
            "related_markets": ["Some past event"],
            "frontrun_window_hours": 48,
            "our_position": None
        },
    ]


def make_position(direction="NO", market="US strikes Iran by June 30, 2026"):
    return {
        "trade_id": "T001",
        "strategy": "S004",
        "domain": "GEO",
        "market": market,
        "direction": direction,
        "entry_price": 0.335,
        "shares": 895.52,
        "size_usd": 300.00,
        "status": "open",
    }


def make_anomaly(wallet="0xABCD1234", direction="YES", score=7,
                 market="US strikes Iran by June 30, 2026", size=25000):
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "wallet": wallet,
        "market_question": market,
        "direction": direction,
        "trade_size_usd": size,
        "entry_price": 0.65,
        "market_volume": 150000,
        "wallet_info": make_wallet_info(),
        "anomaly_score": score,
    }


# ── Test Classes ──────────────────────────────────────────────────────

class TestWalletHistoryCheck(TestCase):
    """Test wallet freshness classification."""

    def test_fresh_wallet_detected(self):
        """Wallet with <5 txns scores max freshness points (3)."""
        wi = make_wallet_info(total_txns=3, age_days=5)
        score = score_fresh_wallet_anomaly(wi, 25000, 150000, "some market", [])
        # 3 (txns) + 2 (age) + 1 (size>10K) = 6 minimum
        self.assertGreaterEqual(score, 6)

    def test_established_wallet_ignored(self):
        """Wallet with >20 txns gets 0 freshness points."""
        wi = make_wallet_info(total_txns=150, age_days=400,
                              funded_from_exchange=False)
        score = score_fresh_wallet_anomaly(wi, 6000, 500000, "some market", [])
        # 0 (txns) + 0 (age) + 0 (size<10K, <2% of vol) + 0 (not exchange) = 0
        self.assertEqual(score, 0)

    def test_wallet_age_calculation(self):
        """Wallet age < 7 days gets 2 points; < 30 gets 1."""
        wi_new = make_wallet_info(total_txns=15, age_days=3)
        wi_month = make_wallet_info(total_txns=15, age_days=20)
        wi_old = make_wallet_info(total_txns=15, age_days=60)

        # 15 txns = 1 point for freshness; only age varies
        score_new = score_fresh_wallet_anomaly(wi_new, 6000, 500000, "x", [])
        score_month = score_fresh_wallet_anomaly(wi_month, 6000, 500000, "x", [])
        score_old = score_fresh_wallet_anomaly(wi_old, 6000, 500000, "x", [])

        self.assertGreater(score_new, score_month)
        self.assertGreater(score_month, score_old)

    def test_medium_fresh_wallet(self):
        """Wallet with 6-10 txns gets 2 freshness points."""
        wi = make_wallet_info(total_txns=8, age_days=45,
                              funded_from_exchange=False)
        score = score_fresh_wallet_anomaly(wi, 6000, 500000, "x", [])
        # 2 (txns 6-10) + 0 (age >30) + 0 (size) + 0 (not exchange) = 2
        self.assertEqual(score, 2)


class TestAnomalyScoring(TestCase):
    """Test the composite anomaly scoring function."""

    def test_max_score_fresh_large_catalyst(self):
        """Fresh wallet + large trade + near catalyst = high score."""
        wi = make_wallet_info(total_txns=2, age_days=3,
                              funded_from_exchange=True, first_deposit_hours_ago=12)
        catalysts = make_catalysts()
        # Market matches the Iran catalyst (2 days away)
        score = score_fresh_wallet_anomaly(
            wi, 50000, 30000, "US strikes Iran by June 30", catalysts
        )
        # 3 (txns<=5) + 2 (age<=7) + 2 (size>2%vol) + 1 (niche<50K) + 2 (catalyst<=3d) + 1 (exchange<48h) = 11 → capped at 10
        self.assertEqual(score, 10)

    def test_min_score_established_small(self):
        """Established wallet + small trade = 0."""
        wi = make_wallet_info(total_txns=200, age_days=500,
                              funded_from_exchange=False)
        score = score_fresh_wallet_anomaly(wi, 5000, 1000000, "some market", [])
        self.assertEqual(score, 0)

    def test_niche_market_bonus(self):
        """Market volume < $50K adds 1 point."""
        # Use small trade ($500) to avoid triggering size-relative bonus
        wi = make_wallet_info(total_txns=8, age_days=15,
                              funded_from_exchange=False)
        score_niche = score_fresh_wallet_anomaly(wi, 500, 30000, "x", [])
        score_big = score_fresh_wallet_anomaly(wi, 500, 500000, "x", [])
        self.assertEqual(score_niche - score_big, 1)

    def test_catalyst_proximity_bonus(self):
        """Catalyst within 3 days adds 2; within 7 adds 1."""
        wi = make_wallet_info(total_txns=8, age_days=15)
        catalysts = make_catalysts()

        # Iran catalyst is 2 days out; matching market
        score_near = score_fresh_wallet_anomaly(
            wi, 6000, 500000, "US strikes Iran by June 30", catalysts
        )
        # No matching catalyst
        score_far = score_fresh_wallet_anomaly(
            wi, 6000, 500000, "Bitcoin 150K", catalysts
        )
        self.assertGreater(score_near, score_far)

    def test_score_capped_at_10(self):
        """Score never exceeds 10."""
        wi = make_wallet_info(total_txns=1, age_days=1,
                              funded_from_exchange=True, first_deposit_hours_ago=1)
        catalysts = make_catalysts()
        score = score_fresh_wallet_anomaly(
            wi, 100000, 10000, "US strikes Iran by June 30", catalysts
        )
        self.assertLessEqual(score, 10)

    def test_exchange_funding_bonus(self):
        """Funded from exchange within 48h adds 1 point."""
        wi_exchange = make_wallet_info(total_txns=8, age_days=15,
                                       funded_from_exchange=True, first_deposit_hours_ago=24)
        wi_other = make_wallet_info(total_txns=8, age_days=15,
                                     funded_from_exchange=False)
        score_ex = score_fresh_wallet_anomaly(wi_exchange, 6000, 500000, "x", [])
        score_oth = score_fresh_wallet_anomaly(wi_other, 6000, 500000, "x", [])
        self.assertEqual(score_ex - score_oth, 1)


class TestCatalystCalendar(TestCase):
    """Test catalyst proximity matching."""

    def test_nearest_catalyst_found(self):
        """Matching market finds nearest catalyst days."""
        catalysts = make_catalysts()
        days = nearest_catalyst("US strikes Iran by June 30", catalysts)
        self.assertIsNotNone(days)
        self.assertLessEqual(days, 3)  # Iran talks 2 days out

    def test_no_catalyst_returns_none(self):
        """Non-matching market returns None."""
        catalysts = make_catalysts()
        days = nearest_catalyst("Will it rain in Tokyo tomorrow", catalysts)
        self.assertIsNone(days)

    def test_expired_catalyst_ignored(self):
        """Past catalysts (negative days) are not returned."""
        catalysts = make_catalysts()
        # "Some past event" is 5 days ago
        days = nearest_catalyst("Some past event", catalysts)
        self.assertIsNone(days)

    def test_empty_catalysts(self):
        """Empty catalyst list returns None."""
        days = nearest_catalyst("anything", [])
        self.assertIsNone(days)

    def test_empty_market(self):
        """Empty market question returns None."""
        catalysts = make_catalysts()
        days = nearest_catalyst("", catalysts)
        self.assertIsNone(days)


class TestClusterDetection(TestCase):
    """Test cluster detection across multiple fresh wallets."""

    def test_three_fresh_wallets_same_market(self):
        """3+ fresh wallets on same market + direction = cluster."""
        anomalies = [
            make_anomaly(wallet=f"0xWALLET{i}", direction="YES",
                         market="US strikes Iran by June 30, 2026")
            for i in range(3)
        ]
        clusters = detect_clusters(anomalies)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["count"], 3)
        self.assertEqual(clusters[0]["direction"], "YES")

    def test_one_fresh_wallet(self):
        """Single wallet is not a cluster."""
        anomalies = [make_anomaly(wallet="0xSINGLE")]
        clusters = detect_clusters(anomalies)
        self.assertEqual(len(clusters), 0)

    def test_fresh_wallets_different_markets(self):
        """Fresh wallets on different markets are not a cluster."""
        anomalies = [
            make_anomaly(wallet="0xW1", market="Iran market"),
            make_anomaly(wallet="0xW2", market="Bitcoin market"),
            make_anomaly(wallet="0xW3", market="Election market"),
        ]
        clusters = detect_clusters(anomalies)
        self.assertEqual(len(clusters), 0)

    def test_different_directions_not_cluster(self):
        """Same market but different directions = separate groups, no cluster."""
        anomalies = [
            make_anomaly(wallet="0xW1", direction="YES", market="Iran"),
            make_anomaly(wallet="0xW2", direction="NO", market="Iran"),
            make_anomaly(wallet="0xW3", direction="YES", market="Iran"),
        ]
        clusters = detect_clusters(anomalies)
        # Only 2 YES wallets, not enough for cluster
        self.assertEqual(len(clusters), 0)

    def test_cluster_total_usd(self):
        """Cluster aggregates total USD correctly."""
        anomalies = [
            make_anomaly(wallet=f"0xW{i}", size=10000 * (i + 1), market="Same")
            for i in range(4)
        ]
        clusters = detect_clusters(anomalies)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["total_usd"], 10000 + 20000 + 30000 + 40000)


class TestPortfolioIntegration(TestCase):
    """Test portfolio impact assessment."""

    def test_agrees_with_position(self):
        """Anomaly direction matches our position = CONFIRMATION."""
        anomaly = make_anomaly(direction="NO")
        position = make_position(direction="NO")
        action, detail = assess_portfolio_impact(anomaly, position)
        self.assertEqual(action, "CONFIRMATION")
        self.assertIn("AGREES", detail)

    def test_contradicts_position(self):
        """Anomaly direction opposes our position = CONTRADICTION."""
        anomaly = make_anomaly(direction="YES")
        position = make_position(direction="NO")
        action, detail = assess_portfolio_impact(anomaly, position)
        self.assertEqual(action, "CONTRADICTION")
        self.assertIn("CONTRADICTS", detail)

    def test_no_position_on_market(self):
        """No position = NEW_INTEL."""
        anomaly = make_anomaly()
        action, detail = assess_portfolio_impact(anomaly, None)
        self.assertEqual(action, "NEW_INTEL")

    def test_unknown_direction(self):
        """Unknown anomaly direction = MONITOR."""
        anomaly = make_anomaly(direction="UNKNOWN")
        position = make_position(direction="NO")
        action, detail = assess_portfolio_impact(anomaly, position)
        self.assertEqual(action, "MONITOR")

    def test_cluster_contradicts_position(self):
        """Cluster contradiction = strongest signal, reduce 50%."""
        cluster = {
            "market": "US strikes Iran by June 30, 2026",
            "direction": "YES",
            "count": 4,
            "wallets": ["0xW1", "0xW2", "0xW3", "0xW4"],
            "total_usd": 80000,
            "avg_score": 8.5,
        }
        position = make_position(direction="NO")
        action, detail = assess_cluster_impact(cluster, position)
        self.assertEqual(action, "CLUSTER_CONTRADICT")
        self.assertIn("REDUCE POSITION BY 50%", detail)

    def test_cluster_confirms_position(self):
        """Cluster confirmation = high confidence."""
        cluster = {
            "market": "US strikes Iran",
            "direction": "NO",
            "count": 3,
            "wallets": ["0xW1", "0xW2", "0xW3"],
            "total_usd": 60000,
            "avg_score": 7.0,
        }
        position = make_position(direction="NO")
        action, detail = assess_cluster_impact(cluster, position)
        self.assertEqual(action, "CLUSTER_CONFIRM")

    def test_cluster_no_position(self):
        """Cluster with no existing position = new entry signal."""
        cluster = {
            "market": "Some new market",
            "direction": "YES",
            "count": 3,
            "wallets": ["0xW1", "0xW2", "0xW3"],
            "total_usd": 45000,
            "avg_score": 7.5,
        }
        action, detail = assess_cluster_impact(cluster, None)
        self.assertEqual(action, "CLUSTER_NEW")


class TestDomainClassification(TestCase):
    """Test domain classification matches l04 conventions."""

    def test_geo_iran(self):
        self.assertEqual(classify_domain("US strikes Iran by June 30"), "GEO")

    def test_pol_trump(self):
        self.assertEqual(classify_domain("Will Trump win the 2028 nomination?"), "POL")

    def test_eco_fed(self):
        self.assertEqual(classify_domain("Fed rate cut March 2026"), "ECO")

    def test_cry_bitcoin(self):
        self.assertEqual(classify_domain("Bitcoin reach $150,000"), "CRY")

    def test_other_unknown(self):
        self.assertEqual(classify_domain("Will it rain in Topeka"), "OTHER")


class TestPreliminaryProfile(TestCase):
    """Test unknown insider profile creation."""

    def test_profile_has_required_fields(self):
        wi = make_wallet_info()
        trade = make_anomaly()
        profile = create_preliminary_profile("0xABCD", wi, trade, 8)
        self.assertIn("wallet", profile)
        self.assertIn("alias", profile)
        self.assertIn("detection_method", profile)
        self.assertEqual(profile["detection_method"], "fresh-wallet-detector")
        self.assertEqual(profile["anomaly_score"], 8)
        self.assertEqual(profile["status"], "monitoring")
        self.assertEqual(len(profile["trades"]), 1)

    def test_alias_includes_domain(self):
        trade = make_anomaly(market="US strikes Iran by June 30")
        profile = create_preliminary_profile("0xABCD", make_wallet_info(), trade, 9)
        self.assertIn("GEO", profile["alias"])

    def test_save_and_merge(self):
        """Saving same-day profile merges trades."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily override DETECTED_DIR
            original_dir = fwd.DETECTED_DIR
            fwd.DETECTED_DIR = Path(tmpdir)
            try:
                trade1 = make_anomaly(market="Iran strike")
                p1 = create_preliminary_profile("0xW1", make_wallet_info(), trade1, 7)
                save_profile(p1)

                trade2 = make_anomaly(market="Another Iran bet")
                p2 = create_preliminary_profile("0xW2", make_wallet_info(), trade2, 8)
                p2["alias"] = p1["alias"]  # Same alias = same file
                save_profile(p2)

                filepath = Path(tmpdir) / f"{p1['alias']}.json"
                with open(filepath) as f:
                    merged = json.load(f)
                self.assertEqual(len(merged["trades"]), 2)
                self.assertEqual(merged["anomaly_score"], 8)  # Max of 7, 8
            finally:
                fwd.DETECTED_DIR = original_dir


if __name__ == "__main__":
    main()
