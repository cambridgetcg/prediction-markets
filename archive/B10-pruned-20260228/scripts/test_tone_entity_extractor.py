#!/usr/bin/env python3
"""
Tests for NB03: Tone & Entity Extraction.

Run:  pytest scripts/test_tone_entity_extractor.py -v
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from brave_ingestor import Article
from tone_entity_extractor import (
    ToneEntityExtractor,
    heuristic_tone,
    heuristic_entities,
    _parse_llm_response,
    _build_articles_block,
    BATCH_PROMPT_TEMPLATE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_article(**overrides) -> Article:
    defaults = dict(
        url='https://example.com/test',
        title='Test Article',
        description='A test description.',
        extra_snippets=[],
        full_text='',
        source_name='Test',
        source_domain='example.com',
        country_queried='US',
        age_raw='1 hour ago',
        published_at=datetime.now(timezone.utc),
        query_name='test',
        fetched_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Article(**defaults)


# ---------------------------------------------------------------------------
# Heuristic tone tests
# ---------------------------------------------------------------------------

class TestHeuristicTone:
    def test_positive_article(self):
        text = ("Iran and US reach breakthrough nuclear agreement after months "
                "of cooperation and diplomacy. Peace deal praised as victory.")
        tone = heuristic_tone(text)
        assert tone > 0, f"Expected positive tone, got {tone}"

    def test_negative_article(self):
        text = ("Russian missiles strike Ukrainian power grid in devastating "
                "attack. Casualties reported. Crisis escalation threatens war.")
        tone = heuristic_tone(text)
        assert tone < 0, f"Expected negative tone, got {tone}"

    def test_neutral_article(self):
        text = "The committee met on Tuesday to discuss the quarterly report."
        tone = heuristic_tone(text)
        assert tone == 0.0, f"Expected neutral tone, got {tone}"

    def test_tone_clamped_to_range(self):
        # Extremely negative text
        text = ' '.join(['war attack killed dead casualties crisis collapse'] * 20)
        tone = heuristic_tone(text)
        assert -5.0 <= tone <= 5.0

    def test_empty_text(self):
        assert heuristic_tone('') == 0.0

    def test_mixed_sentiment(self):
        text = "Peace agreement reached despite earlier attack and casualties."
        tone = heuristic_tone(text)
        # Should be close to zero — mixed signals
        assert -3.0 <= tone <= 3.0


# ---------------------------------------------------------------------------
# Heuristic entity tests
# ---------------------------------------------------------------------------

class TestHeuristicEntities:
    def test_geopolitical_entities(self):
        text = ("Iran and the United States reached a deal. NATO praised the "
                "agreement. Secretary Blinken met with President Raisi in Geneva.")
        ent = heuristic_entities(text)
        assert 'Iran' in ent['locations']
        assert 'United States' in ent['locations']
        assert 'NATO' in ent['organizations']

    def test_persons_extracted(self):
        text = ("President Zelensky called for emergency meeting with "
                "Secretary Blinken and Chancellor Scholz at the summit.")
        ent = heuristic_entities(text)
        persons = ent['persons']
        # Should find multi-word capitalized names
        assert any('Zelensky' in p for p in persons) or any('Blinken' in p for p in persons)

    def test_countries_as_locations(self):
        text = "Tensions between Russia and Ukraine escalated. China issued a statement."
        ent = heuristic_entities(text)
        assert 'Russia' in ent['locations']
        assert 'Ukraine' in ent['locations']
        assert 'China' in ent['locations']

    def test_known_orgs(self):
        text = "The Federal Reserve held rates. IMF and ECB issued warnings."
        ent = heuristic_entities(text)
        assert 'IMF' in ent['organizations']
        assert 'ECB' in ent['organizations']
        assert 'Federal Reserve' in ent['organizations']

    def test_empty_text(self):
        ent = heuristic_entities('')
        assert ent == {'persons': [], 'organizations': [], 'locations': []}


# ---------------------------------------------------------------------------
# LLM response parsing
# ---------------------------------------------------------------------------

class TestLLMParsing:
    def test_valid_json_array(self):
        raw = json.dumps([
            {
                'tone': 2.5,
                'persons': ['John Doe'],
                'organizations': ['NATO'],
                'locations': ['Geneva'],
                'key_claim': 'A deal was reached.',
            }
        ])
        result = _parse_llm_response(raw, 1)
        assert result is not None
        assert len(result) == 1
        assert result[0]['tone'] == 2.5
        assert result[0]['key_claim'] == 'A deal was reached.'

    def test_markdown_fenced_json(self):
        raw = '```json\n[{"tone": 1.0, "persons": [], "organizations": [], "locations": [], "key_claim": "Test."}]\n```'
        result = _parse_llm_response(raw, 1)
        assert result is not None
        assert result[0]['tone'] == 1.0

    def test_wrong_count_returns_none(self):
        raw = json.dumps([{'tone': 1.0}])
        result = _parse_llm_response(raw, 3)
        assert result is None

    def test_invalid_json_returns_none(self):
        result = _parse_llm_response('not json at all', 1)
        assert result is None

    def test_non_array_returns_none(self):
        result = _parse_llm_response('{"tone": 1.0}', 1)
        assert result is None


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

class TestPromptBuilding:
    def test_articles_block_formatting(self):
        articles = [
            make_article(title='Article One', description='Desc one'),
            make_article(url='https://example.com/2', title='Article Two',
                         description='Desc two', extra_snippets=['Snippet A']),
        ]
        block = _build_articles_block(articles)
        assert '[1] Title: Article One' in block
        assert '[2] Title: Article Two' in block
        assert 'Snippet A' in block

    def test_prompt_template_renders(self):
        prompt = BATCH_PROMPT_TEMPLATE.format(articles_block='[1] Title: Test')
        assert 'For each article' in prompt
        assert '[1] Title: Test' in prompt


# ---------------------------------------------------------------------------
# ToneEntityExtractor — heuristic mode
# ---------------------------------------------------------------------------

class TestExtractorHeuristic:
    def test_enrich_positive(self):
        a = make_article(
            title='Peace agreement breakthrough in negotiations',
            description='Cooperation and diplomacy lead to historic deal.',
        )
        ext = ToneEntityExtractor(use_llm=False)
        ext.enrich([a])
        assert a.tone is not None
        assert a.tone > 0

    def test_enrich_negative(self):
        a = make_article(
            title='Devastating attack kills dozens in bombing',
            description='Casualties mounting as crisis escalates. War threatens region.',
        )
        ext = ToneEntityExtractor(use_llm=False)
        ext.enrich([a])
        assert a.tone is not None
        assert a.tone < 0

    def test_enrich_populates_entities(self):
        a = make_article(
            title='NATO responds to Russia Ukraine conflict',
            description='The UN called for ceasefire. President Zelensky spoke.',
        )
        ext = ToneEntityExtractor(use_llm=False)
        ext.enrich([a])
        assert a.entities is not None
        assert len(a.entities) > 0
        # Should contain at least one known org or location
        all_ent = ' '.join(a.entities)
        assert 'NATO' in all_ent or 'Russia' in all_ent or 'Ukraine' in all_ent

    def test_enrich_empty_list(self):
        ext = ToneEntityExtractor(use_llm=False)
        result = ext.enrich([])
        assert result == []

    def test_stats_tracked(self):
        articles = [make_article(), make_article(url='https://example.com/2')]
        ext = ToneEntityExtractor(use_llm=False)
        ext.enrich(articles)
        assert ext.stats['fallback_articles'] == 2
        assert ext.stats['llm_articles'] == 0

    def test_key_claim_none_in_heuristic(self):
        a = make_article()
        ext = ToneEntityExtractor(use_llm=False)
        ext.enrich([a])
        assert a.key_claim is None


# ---------------------------------------------------------------------------
# ToneEntityExtractor — mocked LLM mode
# ---------------------------------------------------------------------------

class TestExtractorLLM:
    def _mock_response(self, articles_data: list[dict]) -> MagicMock:
        """Build a mock Anthropic API response."""
        resp = MagicMock()
        content_block = MagicMock()
        content_block.text = json.dumps(articles_data)
        resp.content = [content_block]
        return resp

    @patch('tone_entity_extractor.anthropic')
    @patch('tone_entity_extractor._get_api_key', return_value='sk-test-key')
    def test_llm_batch_enrich(self, mock_key, mock_anthropic_mod):
        mock_client = MagicMock()
        mock_anthropic_mod.Anthropic.return_value = mock_client

        llm_output = [
            {
                'tone': 3.0,
                'persons': ['John Kerry'],
                'organizations': ['UN', 'IAEA'],
                'locations': ['Geneva', 'Iran'],
                'key_claim': 'Iran agrees to enrichment limits.',
            },
            {
                'tone': -4.0,
                'persons': ['Zelensky'],
                'organizations': ['NATO'],
                'locations': ['Kyiv', 'Ukraine'],
                'key_claim': 'Russian missiles hit Kyiv infrastructure.',
            },
        ]
        mock_client.messages.create.return_value = self._mock_response(llm_output)

        articles = [
            make_article(title='Iran deal'),
            make_article(url='https://example.com/2', title='Ukraine attack'),
        ]

        ext = ToneEntityExtractor(use_llm=True)
        ext.enrich(articles)

        assert articles[0].tone == 3.0
        assert articles[0].key_claim == 'Iran agrees to enrichment limits.'
        assert 'John Kerry' in articles[0].entities
        assert 'UN' in articles[0].entities

        assert articles[1].tone == -4.0
        assert 'Zelensky' in articles[1].entities
        assert ext.stats['llm_calls'] == 1
        assert ext.stats['llm_articles'] == 2

    @patch('tone_entity_extractor.anthropic')
    @patch('tone_entity_extractor._get_api_key', return_value='sk-test-key')
    def test_llm_fallback_on_failure(self, mock_key, mock_anthropic_mod):
        """If LLM call raises, should fall back to heuristic."""
        mock_client = MagicMock()
        mock_anthropic_mod.Anthropic.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API error")

        a = make_article(
            title='Peace agreement reached with cooperation',
            description='Historic breakthrough in diplomacy.',
        )
        ext = ToneEntityExtractor(use_llm=True)
        ext.enrich([a])

        # Should have fallen back to heuristic
        assert a.tone is not None
        assert a.tone > 0  # Positive heuristic
        assert ext.stats['fallback_articles'] == 1

    @patch('tone_entity_extractor.anthropic')
    @patch('tone_entity_extractor._get_api_key', return_value='sk-test-key')
    def test_llm_batching_groups_of_10(self, mock_key, mock_anthropic_mod):
        """12 articles should produce 2 LLM calls (10 + 2)."""
        mock_client = MagicMock()
        mock_anthropic_mod.Anthropic.return_value = mock_client

        def make_llm_output(n):
            return self._mock_response([
                {'tone': 0.0, 'persons': [], 'organizations': [],
                 'locations': [], 'key_claim': 'Test.'}
                for _ in range(n)
            ])

        mock_client.messages.create.side_effect = [
            make_llm_output(10),
            make_llm_output(2),
        ]

        articles = [
            make_article(url=f'https://example.com/{i}', title=f'Article {i}')
            for i in range(12)
        ]

        ext = ToneEntityExtractor(use_llm=True)
        ext.enrich(articles)

        assert mock_client.messages.create.call_count == 2
        assert ext.stats['llm_calls'] == 2
        assert ext.stats['llm_articles'] == 12

    @patch('tone_entity_extractor.anthropic')
    @patch('tone_entity_extractor._get_api_key', return_value='sk-test-key')
    def test_tone_clamped_from_llm(self, mock_key, mock_anthropic_mod):
        """LLM returning out-of-range tone should be clamped."""
        mock_client = MagicMock()
        mock_anthropic_mod.Anthropic.return_value = mock_client

        mock_client.messages.create.return_value = self._mock_response([
            {'tone': 99.0, 'persons': [], 'organizations': [],
             'locations': [], 'key_claim': 'Test.'}
        ])

        a = make_article()
        ext = ToneEntityExtractor(use_llm=True)
        ext.enrich([a])
        assert a.tone == 5.0  # Clamped

    @patch('tone_entity_extractor.anthropic', None)
    def test_no_anthropic_module_falls_back(self):
        """If anthropic not installed, should use heuristic."""
        ext = ToneEntityExtractor(use_llm=True)
        assert ext.use_llm is False


# ---------------------------------------------------------------------------
# Integration-style test — full pipeline simulation
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_heuristic_full_pipeline(self):
        """Simulate processing a batch of diverse articles in heuristic mode."""
        articles = [
            make_article(
                url='https://example.com/1',
                title='Iran and US reach breakthrough nuclear agreement',
                description='After months of negotiations, a historic deal was reached.',
                extra_snippets=['Secretary Blinken praised the cooperation.'],
            ),
            make_article(
                url='https://example.com/2',
                title='Russian missiles strike Ukrainian power grid',
                description='Devastating barrage causes widespread casualties and crisis.',
                extra_snippets=['NATO condemned the attack.'],
                country_queried='GB',
            ),
            make_article(
                url='https://example.com/3',
                title='Federal Reserve holds rates steady',
                description='The Fed kept interest rates unchanged amid mixed signals.',
                extra_snippets=['Fed Chair Powell noted resilience.'],
            ),
        ]

        ext = ToneEntityExtractor(use_llm=False)
        result = ext.enrich(articles)

        # Article 1: positive (peace, agreement, cooperation)
        assert result[0].tone > 0
        assert 'Iran' in ' '.join(result[0].entities)

        # Article 2: negative (missiles, strike, casualties, crisis)
        assert result[1].tone < 0
        assert 'NATO' in result[1].entities or 'Ukraine' in ' '.join(result[1].entities)

        # Article 3: roughly neutral (no strong positive/negative)
        assert -2.0 <= result[2].tone <= 2.0
        assert 'Federal Reserve' in result[2].entities or 'Fed' in result[2].entities

        # All should have entities populated
        for a in result:
            assert a.entities is not None
            assert len(a.entities) > 0
