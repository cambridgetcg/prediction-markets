#!/usr/bin/env python3
"""NB06: Truth Extraction Engine — Stage 6 of the News Intelligence Pipeline.

Triangulates perspectives from divergent EventClusters to extract consensus facts,
contested claims, motivated omissions, and prediction-market-relevant signals.

Primary: LLM extraction (Sonnet for standard divergence, Opus for high divergence).
Requires at least 2 perspective clusters with is_divergent=True.

Usage:
    # As library — called by pipeline orchestrator:
    from truth_extractor import TruthExtractor
    extractor = TruthExtractor()
    result = extractor.extract(cluster)

    # CLI — extract from active divergent clusters:
    python3 scripts/truth_extractor.py
    python3 scripts/truth_extractor.py --demo
    python3 scripts/truth_extractor.py --show          # Show recent extractions
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from event_clusterer import EventCluster  # noqa: E402
from perspective_matrix import ClusterView  # noqa: E402

try:
    import anthropic
except ImportError:
    anthropic = None

logger = logging.getLogger(__name__)

PROJECT_ROOT = SCRIPT_DIR.parent
PROMPT_PATH = PROJECT_ROOT / "prompts" / "truth_extraction_brave.txt"
CALIBRATION_PATH = PROJECT_ROOT / "data" / "truth_extractions.jsonl"

# --- Model selection ---
MODEL_HIGH = 'claude-opus-4-6'       # divergence > 6.0
MODEL_STANDARD = 'claude-sonnet-4-6'  # divergence 3.0–6.0
HIGH_DIVERGENCE_THRESHOLD = 6.0

# --- Rate limiting ---
MAX_EXTRACTIONS_PER_HOUR = 20
EXTRACTION_COOLDOWN_SECONDS = 3600  # 60 min re-extraction window
MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TruthExtractionResult:
    cluster_id: str
    consensus_facts: list[str]
    contested_claims: list[dict]
    motivated_omissions: dict[str, str]
    objective_kernel: str
    market_relevance: list[dict]
    overall_confidence: float
    requires_human_review: bool
    model_used: str
    extracted_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_api_key() -> str | None:
    """Get Anthropic API key from env or macOS Keychain."""
    key = os.environ.get('ANTHROPIC_API_KEY')
    if key:
        return key
    try:
        result = subprocess.run(
            ['security', 'find-generic-password', '-a', 'prediction-markets',
             '-s', 'anthropic_api_key', '-w'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _load_prompt_template() -> str:
    """Load the truth extraction prompt from file."""
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text()
    raise FileNotFoundError(f"Prompt template not found: {PROMPT_PATH}")


def _format_cluster_input(cluster: EventCluster) -> str:
    """Format an EventCluster into the prompt input block.

    Groups articles by perspective cluster with tone scores and key claims.
    """
    lines = [
        f"EVENT: {cluster.event_summary}",
        f"DIVERGENCE: {cluster.divergence_score:.1f}",
        "",
    ]

    pm = cluster.perspective_matrix
    for cluster_name, cv in sorted(pm.clusters.items()):
        lines.append(
            f"=== {cluster_name.upper()} "
            f"({cv.article_count} articles, tone: {cv.mean_tone:+.1f}) ==="
        )

        # Find articles belonging to this geo_cluster
        cluster_articles = [
            a for a in cluster.articles
            if getattr(a, 'geo_cluster', None) == cluster_name
        ]

        for i, a in enumerate(cluster_articles, 1):
            tone_str = f"{a.tone:+.1f}" if a.tone is not None else "?"
            key_claim = getattr(a, 'key_claim', None) or a.title
            snippets = ' '.join(a.extra_snippets[:2]) if a.extra_snippets else ''
            lines.append(
                f"[{i}] {a.source_name or a.source_domain} | {tone_str} | {key_claim}"
            )
            desc_snippet = a.description[:200] if a.description else ''
            if desc_snippet or snippets:
                lines.append(f"    {desc_snippet} {snippets}".rstrip())

        lines.append("")

    return '\n'.join(lines)


def _parse_extraction_response(raw: str) -> dict | None:
    """Parse the LLM JSON response. Returns None on failure."""
    cleaned = raw.strip()
    # Strip markdown fences if present
    if cleaned.startswith('```'):
        fence_lines = cleaned.split('\n')
        fence_lines = fence_lines[1:]  # Remove opening fence
        if fence_lines and fence_lines[-1].strip() == '```':
            fence_lines = fence_lines[:-1]
        cleaned = '\n'.join(fence_lines)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    # Validate required fields
    required = ['consensus_facts', 'contested_claims', 'objective_kernel',
                'market_relevance', 'overall_confidence']
    if not all(k in data for k in required):
        return None

    return data


def _select_model(divergence_score: float) -> str:
    """Select model based on divergence score."""
    if divergence_score > HIGH_DIVERGENCE_THRESHOLD:
        return MODEL_HIGH
    return MODEL_STANDARD


# ---------------------------------------------------------------------------
# Main extractor class
# ---------------------------------------------------------------------------

class TruthExtractor:
    """Extracts truth kernels from divergent EventClusters via LLM triangulation.

    Model selection:
      - divergence > 6.0 → Opus (complex disagreement, high stakes)
      - divergence 3.0–6.0 → Sonnet (standard)

    Guards:
      - Only processes is_divergent=True clusters
      - Skips re-extraction within 60 min (unless new articles)
      - Max 20 extractions/hour
      - Retry × 2 on JSON parse failure
      - requires_human_review=True if confidence < 0.6 or retries exhausted
    """

    def __init__(self):
        self.client = None
        self._prompt_template: str | None = None
        self._extractions_this_hour: list[float] = []  # timestamps
        self._extraction_cache: dict[str, datetime] = {}  # cluster_id → last extracted

        if anthropic is not None:
            key = _get_api_key()
            if key:
                self.client = anthropic.Anthropic(api_key=key)
            else:
                logger.warning("No API key found — TruthExtractor disabled.")

    @property
    def prompt_template(self) -> str:
        if self._prompt_template is None:
            self._prompt_template = _load_prompt_template()
        return self._prompt_template

    def _prune_rate_window(self) -> None:
        """Remove extraction timestamps older than 1 hour."""
        cutoff = time.time() - 3600
        self._extractions_this_hour = [
            t for t in self._extractions_this_hour if t > cutoff
        ]

    def _can_extract(self) -> bool:
        """Check if we're under the hourly rate limit."""
        self._prune_rate_window()
        return len(self._extractions_this_hour) < MAX_EXTRACTIONS_PER_HOUR

    def _should_skip(self, cluster: EventCluster) -> bool:
        """Check if cluster was recently extracted and hasn't changed."""
        last = self._extraction_cache.get(cluster.cluster_id)
        if last is None:
            return False

        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        if elapsed < EXTRACTION_COOLDOWN_SECONDS:
            # Skip unless cluster has been updated since last extraction
            if cluster.last_updated <= last:
                return True
        return False

    def extract(self, cluster: EventCluster) -> TruthExtractionResult | None:
        """Extract truth kernel from a divergent EventCluster.

        Returns None if:
          - Cluster is not divergent
          - Recently extracted (within 60 min, no new articles)
          - Rate limit exceeded
          - No API client available
        """
        if not cluster.is_divergent:
            logger.debug("Skipping non-divergent cluster: %s", cluster.cluster_id)
            return None

        if self._should_skip(cluster):
            logger.debug("Skipping recently extracted cluster: %s", cluster.cluster_id)
            return None

        if not self._can_extract():
            logger.warning("Rate limit reached (%d/hr). Skipping: %s",
                           MAX_EXTRACTIONS_PER_HOUR, cluster.cluster_id)
            return None

        if not self.client:
            logger.error("No Anthropic client available.")
            return None

        # Format input
        cluster_input = _format_cluster_input(cluster)
        prompt = self.prompt_template.replace('{cluster_input}', cluster_input)

        # Select model
        model = _select_model(cluster.divergence_score)

        # Call LLM with retry
        parsed = None
        retries_used = 0

        for attempt in range(1 + MAX_RETRIES):
            try:
                response = self.client.messages.create(
                    model=model,
                    max_tokens=4096,
                    messages=[{'role': 'user', 'content': prompt}],
                )
                raw = response.content[0].text
                parsed = _parse_extraction_response(raw)
                if parsed is not None:
                    break
                retries_used = attempt + 1
                logger.warning("JSON parse failed (attempt %d/%d) for cluster %s",
                               attempt + 1, 1 + MAX_RETRIES, cluster.cluster_id)
            except Exception as e:
                retries_used = attempt + 1
                logger.error("API call failed (attempt %d/%d) for cluster %s: %s",
                             attempt + 1, 1 + MAX_RETRIES, cluster.cluster_id, e)

        # Record extraction
        now = datetime.now(timezone.utc)
        self._extractions_this_hour.append(time.time())
        self._extraction_cache[cluster.cluster_id] = now

        # Build result
        if parsed is None:
            # All retries exhausted — return minimal result flagged for human review
            return TruthExtractionResult(
                cluster_id=cluster.cluster_id,
                consensus_facts=[],
                contested_claims=[],
                motivated_omissions={},
                objective_kernel=f"Extraction failed after {retries_used} attempts.",
                market_relevance=[],
                overall_confidence=0.0,
                requires_human_review=True,
                model_used=model,
                extracted_at=now,
            )

        confidence = parsed.get('overall_confidence', 0.0)
        requires_review = confidence < 0.6 or retries_used > 0

        result = TruthExtractionResult(
            cluster_id=cluster.cluster_id,
            consensus_facts=parsed.get('consensus_facts', []),
            contested_claims=parsed.get('contested_claims', []),
            motivated_omissions=parsed.get('motivated_omissions', {}),
            objective_kernel=parsed.get('objective_kernel', ''),
            market_relevance=parsed.get('market_relevance', []),
            overall_confidence=confidence,
            requires_human_review=requires_review,
            model_used=model,
            extracted_at=now,
        )

        # Calibration logging
        self._log_extraction(cluster, result)

        return result

    def extract_batch(self, clusters: list[EventCluster]) -> list[TruthExtractionResult]:
        """Extract from multiple clusters, respecting rate limits."""
        results = []
        for cluster in clusters:
            result = self.extract(cluster)
            if result is not None:
                results.append(result)
        return results

    def _log_extraction(self, cluster: EventCluster, result: TruthExtractionResult) -> None:
        """Append extraction to calibration log for later labeling."""
        try:
            CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                'cluster_id': result.cluster_id,
                'event_summary': cluster.event_summary,
                'divergence_score': cluster.divergence_score,
                'article_count': len(cluster.articles),
                'perspective_count': len(cluster.perspective_matrix.clusters),
                'model_used': result.model_used,
                'overall_confidence': result.overall_confidence,
                'requires_human_review': result.requires_human_review,
                'market_relevance_count': len(result.market_relevance),
                'extracted_at': result.extracted_at.isoformat(),
                # Later: add 'profitable_trade' label
            }
            with open(CALIBRATION_PATH, 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception as e:
            logger.warning("Failed to log extraction: %s", e)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _demo():
    """Run a demo extraction with synthetic data."""
    from brave_ingestor import Article  # noqa: E402
    from perspective_matrix import PerspectiveMatrix, ClusterView  # noqa: E402

    now = datetime.now(timezone.utc)

    # Build synthetic articles
    western_articles = [
        Article(
            url='https://reuters.com/iran-talks',
            title='Iran nuclear talks stall as Western diplomats push for inspections',
            description='IAEA demands access to undeclared sites. Tehran resists.',
            extra_snippets=['US threatens new sanctions if no progress by March.'],
            full_text='',
            source_name='Reuters',
            source_domain='reuters.com',
            country_queried='US',
            age_raw='2 hours ago',
            published_at=now,
            query_name='iran',
            fetched_at=now,
            tone=-1.5,
            entities=['Iran', 'IAEA', 'United States'],
            key_claim='Iran nuclear talks stall over inspection demands.',
            geo_cluster='Western',
            reliability=0.9,
        ),
        Article(
            url='https://bbc.co.uk/iran-analysis',
            title='Analysis: Why Iran talks face collapse',
            description='Hardliners in Tehran resist concessions as deadline looms.',
            extra_snippets=[],
            full_text='',
            source_name='BBC',
            source_domain='bbc.co.uk',
            country_queried='GB',
            age_raw='3 hours ago',
            published_at=now,
            query_name='iran',
            fetched_at=now,
            tone=-2.0,
            entities=['Iran', 'IAEA'],
            key_claim='Iran talks face collapse due to hardliner resistance.',
            geo_cluster='Western',
            reliability=0.85,
        ),
    ]

    iranian_articles = [
        Article(
            url='https://presstv.ir/iran-sovereignty',
            title='Iran rejects illegal IAEA demands, asserts nuclear sovereignty',
            description='Foreign Ministry says inspections violate NPT rights.',
            extra_snippets=['Iran says West uses IAEA as political tool.'],
            full_text='',
            source_name='Press TV',
            source_domain='presstv.ir',
            country_queried='IR',
            age_raw='1 hour ago',
            published_at=now,
            query_name='iran',
            fetched_at=now,
            tone=1.5,
            entities=['Iran', 'IAEA', 'NPT'],
            key_claim='Iran asserts nuclear sovereignty against Western pressure.',
            geo_cluster='Iranian',
            reliability=0.3,
        ),
        Article(
            url='https://presstv.ir/iran-progress',
            title='Iran making peaceful nuclear progress despite Western obstruction',
            description='Tehran emphasizes civilian nuclear program achievements.',
            extra_snippets=[],
            full_text='',
            source_name='Press TV',
            source_domain='presstv.ir',
            country_queried='IR',
            age_raw='4 hours ago',
            published_at=now,
            query_name='iran',
            fetched_at=now,
            tone=2.5,
            entities=['Iran'],
            key_claim='Iran advancing peaceful nuclear program.',
            geo_cluster='Iranian',
            reliability=0.3,
        ),
    ]

    all_articles = western_articles + iranian_articles

    pm = PerspectiveMatrix(
        clusters={
            'Western': ClusterView(
                cluster_name='Western',
                article_count=2,
                mean_tone=-1.75,
                reliability_weighted_tone=-1.7,
                key_claims=['Talks stall over inspections', 'Talks face collapse'],
                sources=['reuters.com', 'bbc.co.uk'],
            ),
            'Iranian': ClusterView(
                cluster_name='Iranian',
                article_count=2,
                mean_tone=2.0,
                reliability_weighted_tone=2.0,
                key_claims=['Iran asserts sovereignty', 'Peaceful progress'],
                sources=['presstv.ir'],
            ),
        },
        divergence_score=3.75,
        is_divergent=True,
    )

    cluster = EventCluster(
        cluster_id='demo_iran_nuclear',
        event_summary='Iran: Nuclear talks stall over IAEA inspection demands',
        first_seen=now,
        last_updated=now,
        articles=all_articles,
        key_entities=['Iran', 'IAEA', 'United States'],
        perspective_matrix=pm,
        divergence_score=3.75,
        is_divergent=True,
        query_sources=['iran'],
    )

    # Show formatted input
    cluster_input = _format_cluster_input(cluster)
    print("=" * 70)
    print("FORMATTED CLUSTER INPUT:")
    print("=" * 70)
    print(cluster_input)
    print()

    # Attempt extraction
    extractor = TruthExtractor()
    if extractor.client:
        print("=" * 70)
        print("CALLING LLM...")
        print("=" * 70)
        result = extractor.extract(cluster)
        if result:
            print(f"\nModel: {result.model_used}")
            print(f"Confidence: {result.overall_confidence}")
            print(f"Human review: {result.requires_human_review}")
            print(f"\nConsensus facts:")
            for f in result.consensus_facts:
                print(f"  - {f}")
            print(f"\nObjective kernel: {result.objective_kernel}")
            print(f"\nMarket relevance:")
            for mr in result.market_relevance:
                print(f"  - {mr.get('description', '?')} → {mr.get('direction', '?')} "
                      f"(shift: {mr.get('probability_shift', '?')}, "
                      f"conf: {mr.get('confidence', '?')})")
        else:
            print("Extraction returned None (check logs).")
    else:
        print("No API client — showing formatted input only.")
        print("Set ANTHROPIC_API_KEY to enable extraction.")


def _show_recent():
    """Show recent extraction log entries."""
    if not CALIBRATION_PATH.exists():
        print("No extractions logged yet.")
        return

    entries = []
    with open(CALIBRATION_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    if not entries:
        print("No extractions logged yet.")
        return

    print(f"{'Time':<22} {'Event':<45} {'Model':<18} {'Conf':>5} {'Review':>7}")
    print("-" * 100)
    for e in entries[-20:]:
        ts = e.get('extracted_at', '?')[:19]
        summary = e.get('event_summary', '?')[:43]
        model = e.get('model_used', '?')
        conf = e.get('overall_confidence', 0)
        review = 'YES' if e.get('requires_human_review') else 'no'
        print(f"{ts:<22} {summary:<45} {model:<18} {conf:>5.2f} {review:>7}")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    if '--demo' in sys.argv:
        _demo()
    elif '--show' in sys.argv:
        _show_recent()
    else:
        # Default: load active divergent clusters and extract
        from event_clusterer import EventClusterer  # noqa: E402

        clusterer = EventClusterer()
        clusters = clusterer.load_clusters()
        divergent = [c for c in clusters if c.is_divergent]

        if not divergent:
            print("No divergent clusters found.")
            sys.exit(0)

        print(f"Found {len(divergent)} divergent cluster(s).")
        extractor = TruthExtractor()
        results = extractor.extract_batch(divergent)
        print(f"Extracted {len(results)} truth kernel(s).")

        for r in results:
            flag = " [REVIEW]" if r.requires_human_review else ""
            print(f"  {r.cluster_id}: conf={r.overall_confidence:.2f} "
                  f"model={r.model_used}{flag}")
            print(f"    Kernel: {r.objective_kernel[:100]}")
