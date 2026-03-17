"""NB04: Perspective Matrix Builder

Tags articles with source bias (lean, reliability, geo_cluster) and builds
cross-perspective divergence matrices for event clusters.

Pipeline stage 4: runs after ToneEntityExtractor (NB03), before EventClusterer (NB05).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean

logger = logging.getLogger(__name__)

# --- Country → Cluster mapping ---

COUNTRY_TO_CLUSTER = {
    "US": "Western", "GB": "Western", "AU": "Western",
    "DE": "Western", "FR": "Western", "CA": "Western",
    "RU": "Russian", "BY": "Russian",
    "CN": "Chinese", "HK": "Chinese",
    "IR": "Iranian",
    "QA": "Gulf", "SA": "Gulf", "AE": "Gulf",
    "IL": "Israeli",
    "TR": "Turkish",
}

# Two-level TLDs for correct subdomain stripping
_TWO_LEVEL_TLDS = frozenset({
    "co.uk", "com.au", "co.jp", "co.kr", "com.br", "co.za",
    "com.cn", "co.in", "com.ar", "co.nz", "com.tr", "co.il",
    "com.mx", "com.ng", "com.pk", "net.au", "org.uk", "ac.uk",
})


# --- Data classes ---

@dataclass
class Article:
    """Minimal Article matching NB02 spec. Will be replaced by shared module."""
    url: str
    title: str
    description: str
    source_domain: str
    country_queried: str
    extra_snippets: list[str] = field(default_factory=list)
    source_name: str = ""
    query_name: str = ""
    full_text: str = ""
    tone: float | None = None
    entities: list[str] | None = None
    lean: float | None = None
    geo_cluster: str | None = None
    reliability: float | None = None


@dataclass
class ClusterView:
    cluster_name: str
    article_count: int
    mean_tone: float
    reliability_weighted_tone: float
    key_claims: list[str]
    sources: list[str]


@dataclass
class PerspectiveMatrix:
    clusters: dict[str, ClusterView]
    divergence_score: float         # max_tone - min_tone across clusters
    is_divergent: bool

    @classmethod
    def build(
        cls,
        articles: list[Article],
        tone_threshold: float = 0.6,
        min_articles_per_cluster: int = 2,
    ) -> PerspectiveMatrix:
        """Build perspective matrix from tagged articles.

        Args:
            articles: Articles already tagged by PerspectiveTagger (with tone set by NB03).
            tone_threshold: Tone divergence threshold (0.6 on VADER -1..+1 scale,
                           equivalent to 3.0 on LLM -5..+5 scale).
            min_articles_per_cluster: Minimum articles for a cluster to count in
                                      divergence calculation.
        """
        by_cluster: dict[str, list[Article]] = {}
        for a in articles:
            if a.geo_cluster:
                by_cluster.setdefault(a.geo_cluster, []).append(a)

        clusters: dict[str, ClusterView] = {}
        for name, arts in by_cluster.items():
            tones = [a.tone for a in arts if a.tone is not None]
            reliabilities = [a.reliability or 0.5 for a in arts]
            tones_with_rel = [
                (a.tone, a.reliability or 0.5)
                for a in arts if a.tone is not None
            ]

            mean_tone = mean(tones) if tones else 0.0

            if tones_with_rel:
                weighted = sum(t * r for t, r in tones_with_rel)
                weight_sum = sum(r for _, r in tones_with_rel)
                rw_tone = weighted / weight_sum if weight_sum else 0.0
            else:
                rw_tone = 0.0

            # Key claims: title + top entities
            claims: list[str] = []
            for a in arts:
                ents = ", ".join(a.entities[:3]) if a.entities else ""
                claim = f"{a.title[:80]}"
                if ents:
                    claim += f" [{ents}]"
                claims.append(claim)

            sources = sorted({a.source_domain for a in arts})

            clusters[name] = ClusterView(
                cluster_name=name,
                article_count=len(arts),
                mean_tone=round(mean_tone, 4),
                reliability_weighted_tone=round(rw_tone, 4),
                key_claims=claims[:5],
                sources=sources,
            )

        # --- Divergence detection ---
        eligible = [
            cv for cv in clusters.values()
            if cv.article_count >= min_articles_per_cluster
        ]

        if len(eligible) >= 2:
            tones = [cv.mean_tone for cv in eligible]
            div_score = max(tones) - min(tones)
        else:
            div_score = 0.0

        # Primary: tone divergence
        is_div = div_score >= tone_threshold

        # Secondary: claim entity divergence (non-overlapping key entities)
        if not is_div and len(eligible) >= 2:
            entity_sets: list[set[str]] = []
            for cv in eligible:
                entities: set[str] = set()
                for claim in cv.key_claims:
                    if "[" in claim and "]" in claim:
                        bracket_content = claim[claim.index("[") + 1:claim.index("]")]
                        entities.update(e.strip() for e in bracket_content.split(","))
                entity_sets.append(entities)
            # Count cluster pairs with zero entity overlap
            distinct_pairs = 0
            for i in range(len(entity_sets)):
                for j in range(i + 1, len(entity_sets)):
                    if entity_sets[i] and entity_sets[j] and not (entity_sets[i] & entity_sets[j]):
                        distinct_pairs += 1
            is_div = distinct_pairs >= 2

        return cls(
            clusters=clusters,
            divergence_score=round(div_score, 4),
            is_divergent=is_div,
        )


# --- Perspective Tagger ---

class PerspectiveTagger:
    """Tags articles with source bias (lean, reliability, geo_cluster).

    Two layers of perspective signal:
      1. source_domain → lookup in source_bias.json
      2. country_queried → COUNTRY_TO_CLUSTER fallback
    """

    def __init__(self, bias_path: str | Path | None = None):
        if bias_path is None:
            bias_path = Path(__file__).parent.parent / "sources" / "source_bias.json"
        self.bias_path = Path(bias_path)
        self._bias: dict[str, dict] = {}
        self._unknown_domains: set[str] = set()
        self._load()

    def _load(self) -> None:
        if self.bias_path.exists():
            with open(self.bias_path) as f:
                self._bias = json.load(f)
            logger.info("Loaded %d domains from %s", len(self._bias), self.bias_path)
        else:
            logger.warning("source_bias.json not found at %s", self.bias_path)

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        domain = domain.lower().strip()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain

    def _lookup(self, raw_domain: str) -> dict | None:
        domain = self._normalize_domain(raw_domain)
        if domain in self._bias:
            return self._bias[domain]
        # Try stripping one subdomain level
        parts = domain.split(".")
        suffix = ".".join(parts[-2:]) if len(parts) >= 2 else ""
        if suffix in _TWO_LEVEL_TLDS:
            if len(parts) > 3:
                parent = ".".join(parts[-3:])
                return self._bias.get(parent)
        elif len(parts) > 2:
            parent = ".".join(parts[-2:])
            return self._bias.get(parent)
        return None

    def tag(self, article: Article) -> Article:
        """Enrich a single article with lean, reliability, geo_cluster."""
        entry = self._lookup(article.source_domain)

        if entry:
            article.lean = entry.get("lean", 0.0)
            article.reliability = entry.get("reliability", 0.5)
            article.geo_cluster = entry.get("geo")
        else:
            self._unknown_domains.add(self._normalize_domain(article.source_domain))
            logger.debug("Unknown domain: %s — falling back to country_queried=%s",
                         article.source_domain, article.country_queried)
            article.lean = 0.0
            article.reliability = 0.5
            article.geo_cluster = COUNTRY_TO_CLUSTER.get(
                article.country_queried, "Western"
            )

        return article

    def tag_batch(self, articles: list[Article]) -> list[Article]:
        """Tag all articles in a batch."""
        return [self.tag(a) for a in articles]

    @property
    def unknown_domains(self) -> set[str]:
        """Domains encountered but not in source_bias.json."""
        return self._unknown_domains.copy()

    @property
    def domain_count(self) -> int:
        return len(self._bias)
