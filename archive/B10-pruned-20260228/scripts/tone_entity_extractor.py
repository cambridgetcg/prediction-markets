#!/usr/bin/env python3
"""
NB03: Tone & Entity Extraction — Stage 2 of the News Intelligence Pipeline.

Enriches Article objects with tone scores, named entities, and key claims.
Primary: LLM batch extraction (10 articles/call via Haiku).
Fallback: Heuristic tone + regex entity extraction (zero external deps).

Usage:
    # As library — called by pipeline orchestrator:
    from tone_entity_extractor import ToneEntityExtractor
    extractor = ToneEntityExtractor()
    extractor.enrich(articles)

    # CLI — enrich articles from a JSON file:
    python3 scripts/tone_entity_extractor.py data/articles.json
    python3 scripts/tone_entity_extractor.py data/articles.json --no-llm
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from brave_ingestor import Article  # noqa: E402

try:
    import anthropic
except ImportError:
    anthropic = None

# ---------------------------------------------------------------------------
# Heuristic fallback — zero-dependency tone & entity extraction
# ---------------------------------------------------------------------------

# Geopolitically-tuned word lists (weighted)
_POS = {
    # Diplomacy / progress
    'agreement': 2, 'deal': 2, 'peace': 3, 'ceasefire': 3, 'cooperation': 2,
    'alliance': 1, 'partnership': 1, 'growth': 1, 'recovery': 2, 'gains': 1,
    'boost': 1, 'rally': 1, 'surge': 1, 'approval': 1, 'support': 1,
    'progress': 1, 'breakthrough': 2, 'victory': 1, 'success': 1, 'easing': 1,
    'stabilize': 1, 'stabilise': 1, 'de-escalation': 2, 'truce': 2,
    'negotiate': 1, 'negotiations': 1, 'diplomacy': 1, 'reform': 1,
    'resolved': 1, 'optimism': 1, 'record high': 2, 'upgrade': 1,
}
_NEG = {
    # Conflict / crisis
    'war': -3, 'attack': -2, 'strikes': -2, 'bombing': -3, 'killed': -3,
    'dead': -3, 'death': -2, 'deaths': -2, 'casualties': -3, 'conflict': -2,
    'crisis': -2, 'sanctions': -1, 'tariffs': -1, 'threat': -2, 'threatens': -2,
    'collapse': -3, 'crash': -2, 'decline': -1, 'recession': -2, 'inflation': -1,
    'escalation': -2, 'invasion': -3, 'missile': -2, 'nuclear': -1,
    'explosion': -2, 'devastating': -2, 'catastrophe': -3, 'disaster': -2,
    'warned': -1, 'warning': -1, 'fears': -1, 'panic': -2, 'scandal': -2,
    'arrested': -1, 'indicted': -2, 'convicted': -2, 'fraud': -2,
    'shutdown': -1, 'default': -2, 'ban': -1, 'banned': -1, 'veto': -1,
    'retaliation': -2, 'tensions': -1, 'troops': -1, 'siege': -2,
}

# Countries and major geopolitical entities
_COUNTRIES = {
    'Afghanistan', 'Albania', 'Algeria', 'Argentina', 'Armenia', 'Australia',
    'Austria', 'Azerbaijan', 'Bahrain', 'Bangladesh', 'Belarus', 'Belgium',
    'Bolivia', 'Bosnia', 'Brazil', 'Bulgaria', 'Cambodia', 'Cameroon',
    'Canada', 'Chile', 'China', 'Colombia', 'Congo', 'Croatia', 'Cuba',
    'Cyprus', 'Czech Republic', 'Denmark', 'Ecuador', 'Egypt', 'Estonia',
    'Ethiopia', 'Finland', 'France', 'Georgia', 'Germany', 'Ghana', 'Greece',
    'Guatemala', 'Haiti', 'Honduras', 'Hungary', 'Iceland', 'India',
    'Indonesia', 'Iran', 'Iraq', 'Ireland', 'Israel', 'Italy', 'Jamaica',
    'Japan', 'Jordan', 'Kazakhstan', 'Kenya', 'Kosovo', 'Kuwait',
    'Kyrgyzstan', 'Latvia', 'Lebanon', 'Libya', 'Lithuania', 'Luxembourg',
    'Malaysia', 'Mali', 'Mexico', 'Moldova', 'Mongolia', 'Montenegro',
    'Morocco', 'Mozambique', 'Myanmar', 'Nepal', 'Netherlands', 'New Zealand',
    'Nicaragua', 'Niger', 'Nigeria', 'North Korea', 'Norway', 'Oman',
    'Pakistan', 'Palestine', 'Panama', 'Paraguay', 'Peru', 'Philippines',
    'Poland', 'Portugal', 'Qatar', 'Romania', 'Russia', 'Rwanda',
    'Saudi Arabia', 'Senegal', 'Serbia', 'Singapore', 'Slovakia', 'Slovenia',
    'Somalia', 'South Africa', 'South Korea', 'Spain', 'Sri Lanka', 'Sudan',
    'Sweden', 'Switzerland', 'Syria', 'Taiwan', 'Tanzania', 'Thailand',
    'Tunisia', 'Turkey', 'Turkmenistan', 'Uganda', 'Ukraine', 'United Arab Emirates',
    'United Kingdom', 'United States', 'Uruguay', 'Uzbekistan', 'Venezuela',
    'Vietnam', 'Yemen', 'Zimbabwe',
}

# Major organizations/institutions
_ORGS = {
    'NATO', 'UN', 'EU', 'OPEC', 'WHO', 'IMF', 'FBI', 'CIA', 'NSA', 'DOJ',
    'SEC', 'Fed', 'ECB', 'IAEA', 'WTO', 'BRICS', 'G7', 'G20', 'ASEAN',
    'Pentagon', 'Congress', 'Senate', 'Parliament', 'Kremlin', 'White House',
    'Supreme Court', 'Treasury', 'State Department', 'World Bank',
    'Federal Reserve', 'European Commission', 'European Council',
    'African Union', 'Arab League', 'Hezbollah', 'Hamas', 'Taliban',
    'SWIFT', 'Reuters', 'Associated Press', 'Bloomberg',
    'OpenAI', 'Anthropic', 'Google', 'Microsoft', 'Apple', 'Amazon', 'Meta',
    'Tesla', 'SpaceX', 'Nvidia', 'TSMC', 'Samsung',
    'Goldman Sachs', 'JPMorgan', 'BlackRock', 'Citadel',
}


def heuristic_tone(text: str) -> float:
    """Word-list sentiment scorer. Returns -5.0 to +5.0."""
    words = text.lower().split()
    score = 0.0
    count = 0
    for w in words:
        w_clean = re.sub(r'[^a-z\-]', '', w)
        if w_clean in _POS:
            score += _POS[w_clean]
            count += 1
        elif w_clean in _NEG:
            score += _NEG[w_clean]
            count += 1

    # Check multi-word terms
    text_lower = text.lower()
    for term, val in _POS.items():
        if ' ' in term and term in text_lower:
            score += val
            count += 1
    for term, val in _NEG.items():
        if ' ' in term and term in text_lower:
            score += val
            count += 1

    if count == 0:
        return 0.0
    # Normalize: raw score / sqrt(count) to dampen long articles, clamp to [-5, 5]
    normalized = score / (count ** 0.5)
    return max(-5.0, min(5.0, round(normalized, 2)))


def heuristic_entities(text: str) -> dict:
    """Regex-based entity extraction from article text.

    Returns {"persons": [...], "organizations": [...], "locations": [...]}.
    """
    persons = []
    organizations = []
    locations = []

    # Match known orgs
    for org in _ORGS:
        if org in text:
            organizations.append(org)

    # Match known countries → locations
    for country in _COUNTRIES:
        if country in text:
            locations.append(country)

    # Extract title-case multi-word sequences as candidate person names
    # Pattern: 2-3 consecutive capitalized words not at sentence start
    name_pattern = re.compile(
        r'(?<![.!?]\s)(?<!\A)'  # Not at sentence start
        r'\b([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,2})\b'
    )
    seen = set(w.lower() for w in organizations + locations)
    for match in name_pattern.finditer(text):
        candidate = match.group(1)
        if candidate.lower() not in seen:
            # Skip common non-name phrases
            skip = {'The', 'This', 'That', 'These', 'Those', 'Some', 'Many',
                    'Most', 'Last', 'Next', 'First', 'Second', 'Third',
                    'New York', 'San Francisco', 'Los Angeles', 'Hong Kong',
                    'North Korea', 'South Korea', 'South Africa', 'New Zealand',
                    'Saudi Arabia', 'United States', 'United Kingdom',
                    'United Arab Emirates', 'Czech Republic', 'North'}
            first_word = candidate.split()[0]
            if first_word in skip or candidate in skip:
                # Re-check: known locations go to locations
                if candidate in _COUNTRIES or candidate in {
                    'New York', 'San Francisco', 'Los Angeles', 'Hong Kong',
                }:
                    if candidate not in locations:
                        locations.append(candidate)
                continue
            persons.append(candidate)
            seen.add(candidate.lower())

    return {
        'persons': sorted(set(persons)),
        'organizations': sorted(set(organizations)),
        'locations': sorted(set(locations)),
    }


# ---------------------------------------------------------------------------
# LLM batch extraction
# ---------------------------------------------------------------------------

BATCH_PROMPT_TEMPLATE = """\
For each article below, extract the following as JSON:
- tone: float from -5.0 (very negative) to +5.0 (very positive). Consider geopolitical context.
- persons: list of named people mentioned
- organizations: list of organizations, countries, and institutions mentioned
- locations: list of specific places, cities, regions mentioned
- key_claim: single sentence — the main factual assertion of the article

Return ONLY a JSON array with one object per article, in the same order.
No commentary, no markdown fences — just the raw JSON array.

Articles:
{articles_block}"""

DEFAULT_MODEL = 'claude-haiku-4-5-20251001'


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


def _build_articles_block(articles: list[Article]) -> str:
    """Format articles for the LLM prompt."""
    parts = []
    for i, a in enumerate(articles, 1):
        snippets = ' '.join(a.extra_snippets or [])
        text = a.full_text[:500] if a.full_text else ''
        parts.append(
            f"[{i}] Title: {a.title}\n"
            f"    Description: {a.description}\n"
            f"    Source: {a.source_name} ({a.country_queried})\n"
            f"    Snippets: {snippets}\n"
            f"    Text: {text}"
        )
    return '\n\n'.join(parts)


def _parse_llm_response(raw: str, expected_count: int) -> list[dict] | None:
    """Parse the LLM JSON response. Returns None on failure."""
    # Strip markdown fences if present
    cleaned = raw.strip()
    if cleaned.startswith('```'):
        lines = cleaned.split('\n')
        lines = lines[1:]  # Remove opening fence
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        cleaned = '\n'.join(lines)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, list) or len(data) != expected_count:
        return None

    return data


# ---------------------------------------------------------------------------
# Main extractor class
# ---------------------------------------------------------------------------

class ToneEntityExtractor:
    """Enriches Article objects with tone, entities, and key_claim.

    Primary: LLM batch extraction (10 articles/call).
    Fallback: Heuristic word-list tone + regex entity extraction.
    """

    def __init__(self, use_llm: bool = True, model: str = DEFAULT_MODEL):
        self.model = model
        self.use_llm = use_llm and anthropic is not None
        self.client = None
        self._llm_calls = 0
        self._llm_articles = 0
        self._fallback_articles = 0

        if self.use_llm:
            key = _get_api_key()
            if key:
                self.client = anthropic.Anthropic(api_key=key)
            else:
                print("WARN: No API key found — falling back to heuristic extraction.")
                self.use_llm = False

    def enrich(self, articles: list[Article]) -> list[Article]:
        """Enrich articles with tone, entities, key_claim. Modifies in-place."""
        if not articles:
            return articles

        if self.use_llm and self.client:
            # Batch in groups of 10
            for i in range(0, len(articles), 10):
                batch = articles[i:i + 10]
                try:
                    self._llm_enrich(batch)
                except Exception as e:
                    print(f"WARN: LLM batch failed ({e}) — falling back to heuristic.")
                    self._fallback_enrich(batch)
        else:
            self._fallback_enrich(articles)

        return articles

    def _llm_enrich(self, batch: list[Article]) -> None:
        """Call LLM to extract tone/entities/key_claim for a batch."""
        prompt = BATCH_PROMPT_TEMPLATE.format(
            articles_block=_build_articles_block(batch)
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{'role': 'user', 'content': prompt}],
        )

        raw = response.content[0].text
        parsed = _parse_llm_response(raw, len(batch))

        if parsed is None:
            raise ValueError(f"LLM returned unparseable response: {raw[:200]}...")

        for article, extraction in zip(batch, parsed):
            article.tone = float(extraction.get('tone', 0.0))
            article.tone = max(-5.0, min(5.0, article.tone))

            persons = extraction.get('persons', [])
            orgs = extraction.get('organizations', [])
            locs = extraction.get('locations', [])
            article.entities = persons + orgs + locs

            article.key_claim = extraction.get('key_claim', '')

            # Store structured entities as private attr for downstream use
            article._structured_entities = {
                'persons': persons,
                'organizations': orgs,
                'locations': locs,
            }

        self._llm_calls += 1
        self._llm_articles += len(batch)

    def _fallback_enrich(self, articles: list[Article]) -> None:
        """Heuristic extraction — no external dependencies."""
        for a in articles:
            text = f"{a.title} {a.description} {' '.join(a.extra_snippets or [])}"
            if a.full_text:
                text += ' ' + a.full_text[:1000]

            a.tone = heuristic_tone(text)

            structured = heuristic_entities(text)
            a.entities = (
                structured['persons']
                + structured['organizations']
                + structured['locations']
            )
            a._structured_entities = structured
            a.key_claim = None

        self._fallback_articles += len(articles)

    @property
    def stats(self) -> dict:
        return {
            'llm_calls': self._llm_calls,
            'llm_articles': self._llm_articles,
            'fallback_articles': self._fallback_articles,
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _make_test_article(**overrides) -> Article:
    """Build a minimal Article for testing/demo."""
    from datetime import datetime, timezone
    defaults = dict(
        url='https://example.com/test',
        title='Test Article',
        description='A test article description.',
        extra_snippets=[],
        full_text='',
        source_name='Test Source',
        source_domain='example.com',
        country_queried='US',
        age_raw='1 hour ago',
        published_at=datetime.now(timezone.utc),
        query_name='test',
        fetched_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Article(**defaults)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='NB03: Tone & Entity Extraction')
    parser.add_argument('input', nargs='?', help='JSON file with articles (optional)')
    parser.add_argument('--no-llm', action='store_true', help='Force heuristic-only mode')
    parser.add_argument('--model', default=DEFAULT_MODEL, help=f'LLM model (default: {DEFAULT_MODEL})')
    parser.add_argument('--demo', action='store_true', help='Run with demo articles')
    args = parser.parse_args()

    extractor = ToneEntityExtractor(use_llm=not args.no_llm, model=args.model)
    mode = 'LLM + heuristic fallback' if extractor.use_llm else 'Heuristic only'
    print(f"NB03 Tone & Entity Extractor — mode: {mode}\n")

    if args.demo:
        articles = [
            _make_test_article(
                title='Iran and US reach breakthrough nuclear agreement',
                description='After months of negotiations, Iran and the United States '
                            'have reached a historic agreement on nuclear enrichment limits.',
                extra_snippets=['Secretary Blinken praised the deal as a diplomatic victory.'],
            ),
            _make_test_article(
                url='https://example.com/test2',
                title='Russian missiles strike Ukrainian power grid',
                description='A devastating barrage of Russian cruise missiles hit Ukrainian '
                            'energy infrastructure, causing widespread blackouts.',
                extra_snippets=['President Zelensky called for emergency NATO meeting.'],
                country_queried='GB',
            ),
            _make_test_article(
                url='https://example.com/test3',
                title='Federal Reserve holds rates steady amid mixed signals',
                description='The Federal Reserve kept interest rates unchanged, citing '
                            'balanced risks between inflation and employment.',
                extra_snippets=['Fed Chair Powell noted the economy remains resilient.'],
            ),
        ]
    elif args.input:
        path = Path(args.input)
        if not path.exists():
            print(f"ERROR: File not found: {path}")
            sys.exit(1)
        raw = json.loads(path.read_text())
        articles = []
        for item in raw:
            item['published_at'] = datetime.fromisoformat(item['published_at'])
            item['fetched_at'] = datetime.fromisoformat(item['fetched_at'])
            articles.append(Article(**item))
    else:
        print("Usage: provide a JSON file or use --demo")
        print("  python3 scripts/tone_entity_extractor.py data/articles.json")
        print("  python3 scripts/tone_entity_extractor.py --demo")
        print("  python3 scripts/tone_entity_extractor.py --demo --no-llm")
        sys.exit(0)

    extractor.enrich(articles)

    for a in articles:
        print(f"--- {a.title} ---")
        print(f"  Tone:     {a.tone:+.2f}")
        print(f"  Entities: {a.entities}")
        if a.key_claim:
            print(f"  Claim:    {a.key_claim}")
        if hasattr(a, '_structured_entities'):
            se = a._structured_entities
            print(f"  Persons:  {se['persons']}")
            print(f"  Orgs:     {se['organizations']}")
            print(f"  Locs:     {se['locations']}")
        print()

    stats = extractor.stats
    print(f"Stats: {stats['llm_calls']} LLM calls, "
          f"{stats['llm_articles']} LLM-enriched, "
          f"{stats['fallback_articles']} heuristic-enriched")


if __name__ == '__main__':
    main()
