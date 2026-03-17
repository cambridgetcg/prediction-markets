#!/usr/bin/env python3
"""
Tests for NB06: Truth Extraction Engine.

Run:  pytest scripts/test_truth_extractor.py -v
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from brave_ingestor import Article
from event_clusterer import EventCluster
from perspective_matrix import PerspectiveMatrix, ClusterView
from truth_extractor import (
    TruthExtractor,
    TruthExtractionResult,
    _format_cluster_input,
    _parse_extraction_response,
    _select_model,
    MODEL_HIGH,
    MODEL_STANDARD,
    HIGH_DIVERGENCE_THRESHOLD,
    MAX_EXTRACTIONS_PER_HOUR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 2, 27, 12, 0, 0, tzinfo=timezone.utc)


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
        published_at=NOW,
        query_name='test',
        fetched_at=NOW,
        tone=0.0,
        entities=['Entity1'],
        key_claim='Test claim.',
        geo_cluster='Western',
        reliability=0.8,
    )
    defaults.update(overrides)
    return Article(**defaults)


def make_cluster(
    cluster_id: str = 'test_cluster_001',
    divergence_score: float = 4.0,
    is_divergent: bool = True,
    western_articles: int = 2,
    iranian_articles: int = 2,
) -> EventCluster:
    """Build a synthetic EventCluster for testing."""
    articles = []
    for i in range(western_articles):
        articles.append(make_article(
            url=f'https://reuters.com/{i}',
            title=f'Western article {i}',
            source_name='Reuters',
            source_domain='reuters.com',
            tone=-1.5,
            key_claim=f'Western claim {i}.',
            geo_cluster='Western',
        ))
    for i in range(iranian_articles):
        articles.append(make_article(
            url=f'https://presstv.ir/{i}',
            title=f'Iranian article {i}',
            source_name='Press TV',
            source_domain='presstv.ir',
            country_queried='IR',
            tone=2.0,
            key_claim=f'Iranian claim {i}.',
            geo_cluster='Iranian',
        ))

    pm = PerspectiveMatrix(
        clusters={
            'Western': ClusterView(
                cluster_name='Western',
                article_count=western_articles,
                mean_tone=-1.5,
                reliability_weighted_tone=-1.4,
                key_claims=[f'Western claim {i}' for i in range(western_articles)],
                sources=['reuters.com'],
            ),
            'Iranian': ClusterView(
                cluster_name='Iranian',
                article_count=iranian_articles,
                mean_tone=2.0,
                reliability_weighted_tone=2.0,
                key_claims=[f'Iranian claim {i}' for i in range(iranian_articles)],
                sources=['presstv.ir'],
            ),
        },
        divergence_score=divergence_score,
        is_divergent=is_divergent,
    )

    return EventCluster(
        cluster_id=cluster_id,
        event_summary='Test Event: Something happened',
        first_seen=NOW,
        last_updated=NOW,
        articles=articles,
        key_entities=['Entity1', 'Entity2'],
        perspective_matrix=pm,
        divergence_score=divergence_score,
        is_divergent=is_divergent,
        query_sources=['test'],
    )


def make_llm_output(confidence: float = 0.8) -> dict:
    """Build a valid LLM extraction response."""
    return {
        'consensus_facts': ['Both sides acknowledge talks occurred.'],
        'contested_claims': [
            {
                'claim': 'Who is responsible for stalemate',
                'western_view': 'Iran blocking inspections',
                'russian_view': None,
                'iranian_view': 'West making unreasonable demands',
                'resolution': 'uncertain',
            }
        ],
        'motivated_omissions': {
            'Western': 'Does not mention sanctions impact on civilians',
            'Iranian': 'Does not mention IAEA evidence',
        },
        'objective_kernel': 'Nuclear talks are stalled. Both sides assign blame to the other.',
        'market_relevance': [
            {
                'category': 'geopolitical',
                'description': 'Iran strikes by March 31 market affected',
                'direction': 'NO',
                'probability_shift': 0.05,
                'confidence': 0.7,
                'key_uncertainty': 'Whether talks resume before deadline',
            }
        ],
        'overall_confidence': confidence,
    }


def mock_api_response(output_dict: dict) -> MagicMock:
    """Build a mock Anthropic messages.create response."""
    resp = MagicMock()
    content_block = MagicMock()
    content_block.text = json.dumps(output_dict)
    resp.content = [content_block]
    return resp


# ---------------------------------------------------------------------------
# Prompt formatting tests
# ---------------------------------------------------------------------------

class TestFormatClusterInput:
    def test_event_header(self):
        cluster = make_cluster()
        output = _format_cluster_input(cluster)
        assert 'EVENT: Test Event: Something happened' in output
        assert 'DIVERGENCE: 4.0' in output

    def test_perspective_sections(self):
        cluster = make_cluster()
        output = _format_cluster_input(cluster)
        assert '=== WESTERN' in output
        assert '=== IRANIAN' in output

    def test_article_details_included(self):
        cluster = make_cluster()
        output = _format_cluster_input(cluster)
        assert 'Reuters' in output
        assert 'Press TV' in output

    def test_tone_scores_included(self):
        cluster = make_cluster()
        output = _format_cluster_input(cluster)
        # Western articles have tone=-1.5
        assert '-1.5' in output
        # Iranian articles have tone=+2.0
        assert '+2.0' in output

    def test_single_perspective_cluster(self):
        cluster = make_cluster(iranian_articles=0)
        # Remove Iranian from perspective matrix
        cluster.perspective_matrix.clusters.pop('Iranian', None)
        output = _format_cluster_input(cluster)
        assert '=== WESTERN' in output
        assert '=== IRANIAN' not in output


# ---------------------------------------------------------------------------
# Response parsing tests
# ---------------------------------------------------------------------------

class TestParseExtractionResponse:
    def test_valid_json(self):
        data = make_llm_output()
        raw = json.dumps(data)
        result = _parse_extraction_response(raw)
        assert result is not None
        assert result['overall_confidence'] == 0.8
        assert len(result['consensus_facts']) == 1

    def test_markdown_fenced_json(self):
        data = make_llm_output()
        raw = '```json\n' + json.dumps(data) + '\n```'
        result = _parse_extraction_response(raw)
        assert result is not None
        assert result['overall_confidence'] == 0.8

    def test_invalid_json_returns_none(self):
        result = _parse_extraction_response('not valid json')
        assert result is None

    def test_array_returns_none(self):
        result = _parse_extraction_response('[1, 2, 3]')
        assert result is None

    def test_missing_required_fields_returns_none(self):
        result = _parse_extraction_response('{"only_one_field": true}')
        assert result is None

    def test_partial_fields_returns_none(self):
        data = {'consensus_facts': [], 'contested_claims': []}
        result = _parse_extraction_response(json.dumps(data))
        assert result is None


# ---------------------------------------------------------------------------
# Model selection tests
# ---------------------------------------------------------------------------

class TestModelSelection:
    def test_high_divergence_uses_opus(self):
        assert _select_model(7.0) == MODEL_HIGH
        assert _select_model(6.1) == MODEL_HIGH

    def test_standard_divergence_uses_sonnet(self):
        assert _select_model(5.0) == MODEL_STANDARD
        assert _select_model(3.0) == MODEL_STANDARD

    def test_threshold_boundary(self):
        # At exactly 6.0, uses sonnet (> not >=)
        assert _select_model(HIGH_DIVERGENCE_THRESHOLD) == MODEL_STANDARD


# ---------------------------------------------------------------------------
# TruthExtractor — guard logic
# ---------------------------------------------------------------------------

class TestExtractorGuards:
    @patch('truth_extractor.anthropic')
    @patch('truth_extractor._get_api_key', return_value='sk-test')
    def test_skip_non_divergent(self, mock_key, mock_anthro):
        mock_anthro.Anthropic.return_value = MagicMock()
        ext = TruthExtractor()
        cluster = make_cluster(is_divergent=False)
        result = ext.extract(cluster)
        assert result is None

    @patch('truth_extractor.anthropic')
    @patch('truth_extractor._get_api_key', return_value='sk-test')
    def test_skip_recently_extracted(self, mock_key, mock_anthro):
        mock_anthro.Anthropic.return_value = MagicMock()
        ext = TruthExtractor()
        cluster = make_cluster()
        # Simulate recent extraction
        ext._extraction_cache[cluster.cluster_id] = datetime.now(timezone.utc)
        result = ext.extract(cluster)
        assert result is None

    @patch('truth_extractor.anthropic')
    @patch('truth_extractor._get_api_key', return_value='sk-test')
    def test_re_extract_if_cluster_updated(self, mock_key, mock_anthro):
        """If cluster.last_updated > last extraction, should re-extract."""
        mock_client = MagicMock()
        mock_anthro.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = mock_api_response(make_llm_output())

        ext = TruthExtractor()
        cluster = make_cluster()

        # Mark as extracted 30 min ago
        from datetime import timedelta
        past = datetime.now(timezone.utc) - timedelta(minutes=30)
        ext._extraction_cache[cluster.cluster_id] = past
        # But cluster was updated after that
        cluster.last_updated = datetime.now(timezone.utc)

        result = ext.extract(cluster)
        assert result is not None

    @patch('truth_extractor.anthropic')
    @patch('truth_extractor._get_api_key', return_value='sk-test')
    def test_rate_limit_blocks(self, mock_key, mock_anthro):
        mock_anthro.Anthropic.return_value = MagicMock()
        ext = TruthExtractor()
        # Fill up rate limit
        ext._extractions_this_hour = [time.time()] * MAX_EXTRACTIONS_PER_HOUR

        cluster = make_cluster()
        result = ext.extract(cluster)
        assert result is None

    @patch('truth_extractor.anthropic', None)
    def test_no_anthropic_module(self):
        ext = TruthExtractor()
        assert ext.client is None

    @patch('truth_extractor.anthropic')
    @patch('truth_extractor._get_api_key', return_value=None)
    def test_no_api_key(self, mock_key, mock_anthro):
        ext = TruthExtractor()
        assert ext.client is None


# ---------------------------------------------------------------------------
# TruthExtractor — extraction with mocked LLM
# ---------------------------------------------------------------------------

class TestExtractorLLM:
    @patch('truth_extractor.anthropic')
    @patch('truth_extractor._get_api_key', return_value='sk-test')
    def test_successful_extraction(self, mock_key, mock_anthro):
        mock_client = MagicMock()
        mock_anthro.Anthropic.return_value = mock_client

        llm_output = make_llm_output(confidence=0.85)
        mock_client.messages.create.return_value = mock_api_response(llm_output)

        ext = TruthExtractor()
        cluster = make_cluster()
        result = ext.extract(cluster)

        assert result is not None
        assert result.cluster_id == 'test_cluster_001'
        assert result.overall_confidence == 0.85
        assert result.requires_human_review is False
        assert result.model_used == MODEL_STANDARD
        assert len(result.consensus_facts) == 1
        assert 'talks occurred' in result.consensus_facts[0]
        assert len(result.market_relevance) == 1
        assert result.market_relevance[0]['direction'] == 'NO'

    @patch('truth_extractor.anthropic')
    @patch('truth_extractor._get_api_key', return_value='sk-test')
    def test_high_divergence_uses_opus(self, mock_key, mock_anthro):
        mock_client = MagicMock()
        mock_anthro.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = mock_api_response(make_llm_output())

        ext = TruthExtractor()
        cluster = make_cluster(divergence_score=7.5)
        result = ext.extract(cluster)

        assert result is not None
        assert result.model_used == MODEL_HIGH
        # Verify the API was called with opus
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs['model'] == MODEL_HIGH

    @patch('truth_extractor.anthropic')
    @patch('truth_extractor._get_api_key', return_value='sk-test')
    def test_low_confidence_triggers_review(self, mock_key, mock_anthro):
        mock_client = MagicMock()
        mock_anthro.Anthropic.return_value = mock_client

        llm_output = make_llm_output(confidence=0.4)
        mock_client.messages.create.return_value = mock_api_response(llm_output)

        ext = TruthExtractor()
        cluster = make_cluster()
        result = ext.extract(cluster)

        assert result is not None
        assert result.overall_confidence == 0.4
        assert result.requires_human_review is True

    @patch('truth_extractor.anthropic')
    @patch('truth_extractor._get_api_key', return_value='sk-test')
    def test_retry_on_parse_failure(self, mock_key, mock_anthro):
        mock_client = MagicMock()
        mock_anthro.Anthropic.return_value = mock_client

        # First call: bad JSON. Second call: valid JSON.
        bad_resp = MagicMock()
        bad_block = MagicMock()
        bad_block.text = 'not valid json'
        bad_resp.content = [bad_block]

        good_resp = mock_api_response(make_llm_output(confidence=0.75))

        mock_client.messages.create.side_effect = [bad_resp, good_resp]

        ext = TruthExtractor()
        cluster = make_cluster()
        result = ext.extract(cluster)

        assert result is not None
        assert result.overall_confidence == 0.75
        # Retries used → requires human review
        assert result.requires_human_review is True
        assert mock_client.messages.create.call_count == 2

    @patch('truth_extractor.anthropic')
    @patch('truth_extractor._get_api_key', return_value='sk-test')
    def test_all_retries_exhausted(self, mock_key, mock_anthro):
        mock_client = MagicMock()
        mock_anthro.Anthropic.return_value = mock_client

        bad_resp = MagicMock()
        bad_block = MagicMock()
        bad_block.text = 'garbage'
        bad_resp.content = [bad_block]

        mock_client.messages.create.return_value = bad_resp

        ext = TruthExtractor()
        cluster = make_cluster()
        result = ext.extract(cluster)

        assert result is not None
        assert result.overall_confidence == 0.0
        assert result.requires_human_review is True
        assert 'failed' in result.objective_kernel.lower()
        # 1 initial + 2 retries = 3 calls
        assert mock_client.messages.create.call_count == 3

    @patch('truth_extractor.anthropic')
    @patch('truth_extractor._get_api_key', return_value='sk-test')
    def test_api_exception_retries(self, mock_key, mock_anthro):
        mock_client = MagicMock()
        mock_anthro.Anthropic.return_value = mock_client

        # First call: exception. Second call: success.
        good_resp = mock_api_response(make_llm_output())
        mock_client.messages.create.side_effect = [
            Exception("API timeout"),
            good_resp,
        ]

        ext = TruthExtractor()
        cluster = make_cluster()
        result = ext.extract(cluster)

        assert result is not None
        assert result.requires_human_review is True  # retries used
        assert mock_client.messages.create.call_count == 2

    @patch('truth_extractor.anthropic')
    @patch('truth_extractor._get_api_key', return_value='sk-test')
    def test_extraction_tracked_in_rate_window(self, mock_key, mock_anthro):
        mock_client = MagicMock()
        mock_anthro.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = mock_api_response(make_llm_output())

        ext = TruthExtractor()
        cluster = make_cluster()
        ext.extract(cluster)

        assert len(ext._extractions_this_hour) == 1
        assert cluster.cluster_id in ext._extraction_cache


# ---------------------------------------------------------------------------
# Batch extraction
# ---------------------------------------------------------------------------

class TestExtractBatch:
    @patch('truth_extractor.anthropic')
    @patch('truth_extractor._get_api_key', return_value='sk-test')
    def test_batch_filters_non_divergent(self, mock_key, mock_anthro):
        mock_client = MagicMock()
        mock_anthro.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = mock_api_response(make_llm_output())

        ext = TruthExtractor()
        clusters = [
            make_cluster(cluster_id='div1', is_divergent=True),
            make_cluster(cluster_id='not_div', is_divergent=False),
            make_cluster(cluster_id='div2', is_divergent=True),
        ]
        results = ext.extract_batch(clusters)

        assert len(results) == 2
        ids = [r.cluster_id for r in results]
        assert 'div1' in ids
        assert 'div2' in ids
        assert 'not_div' not in ids


# ---------------------------------------------------------------------------
# Calibration logging
# ---------------------------------------------------------------------------

class TestCalibrationLogging:
    @patch('truth_extractor.anthropic')
    @patch('truth_extractor._get_api_key', return_value='sk-test')
    def test_logs_to_jsonl(self, mock_key, mock_anthro, tmp_path):
        mock_client = MagicMock()
        mock_anthro.Anthropic.return_value = mock_client
        mock_client.messages.create.return_value = mock_api_response(make_llm_output())

        import truth_extractor
        orig_path = truth_extractor.CALIBRATION_PATH
        truth_extractor.CALIBRATION_PATH = tmp_path / "test_extractions.jsonl"

        try:
            ext = TruthExtractor()
            cluster = make_cluster()
            ext.extract(cluster)

            log_path = truth_extractor.CALIBRATION_PATH
            assert log_path.exists()
            with open(log_path) as f:
                entry = json.loads(f.readline())
            assert entry['cluster_id'] == 'test_cluster_001'
            assert entry['model_used'] == MODEL_STANDARD
            assert 'extracted_at' in entry
        finally:
            truth_extractor.CALIBRATION_PATH = orig_path
