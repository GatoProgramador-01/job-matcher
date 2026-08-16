"""Tests for MongoStorage.cache_stats() and the cache-stats CLI command."""
import json
from io import StringIO
from unittest.mock import MagicMock, patch

from job_matcher.infrastructure.mongo import MongoStorage


class TestCacheStatsDisabled:
    def test_returns_enabled_false_when_mongo_disabled(self):
        storage = MongoStorage.__new__(MongoStorage)
        storage.enabled = False
        storage.db = None
        result = storage.cache_stats()
        assert result == {"enabled": False}


class TestCacheStatsEnabled:
    def _storage_with_db(self, extractions=5, raw_jobs=12, pipeline_runs=3, last_run=None):
        storage = MongoStorage.__new__(MongoStorage)
        storage.enabled = True

        extractions_coll = MagicMock()
        extractions_coll.count_documents.return_value = extractions

        raw_jobs_coll = MagicMock()
        raw_jobs_coll.count_documents.return_value = raw_jobs

        pipeline_runs_coll = MagicMock()
        pipeline_runs_coll.count_documents.return_value = pipeline_runs
        pipeline_runs_coll.find_one.return_value = last_run

        db = MagicMock()
        db.__getitem__ = lambda _, key: {
            "extractions": extractions_coll,
            "raw_jobs": raw_jobs_coll,
            "pipeline_runs": pipeline_runs_coll,
        }[key]
        storage.db = db
        return storage

    def test_returns_correct_counts(self):
        storage = self._storage_with_db(extractions=40, raw_jobs=100, pipeline_runs=7)
        stats = storage.cache_stats()
        assert stats["enabled"] is True
        assert stats["extractions_cached"] == 40
        assert stats["raw_jobs_stored"] == 100
        assert stats["pipeline_runs"] == 7

    def test_last_run_tokens_present_when_run_exists(self):
        last_run = {"token_stats": {"total_tokens": 1500, "cost_usd": 0.003}}
        storage = self._storage_with_db(last_run=last_run)
        stats = storage.cache_stats()
        assert stats["last_run_tokens"] == {"total_tokens": 1500, "cost_usd": 0.003}

    def test_last_run_tokens_empty_when_no_runs(self):
        storage = self._storage_with_db(last_run=None)
        stats = storage.cache_stats()
        assert stats["last_run_tokens"] == {}

    def test_error_key_on_exception(self):
        storage = MongoStorage.__new__(MongoStorage)
        storage.enabled = True
        db = MagicMock()
        db["extractions"].count_documents.side_effect = RuntimeError("connection lost")
        storage.db = db
        stats = storage.cache_stats()
        assert "error" in stats
        assert "connection lost" in stats["error"]


class TestCacheStatsCLI:
    def test_prints_counts(self, capsys):
        fake_stats = {
            "enabled": True,
            "extractions_cached": 40,
            "raw_jobs_stored": 100,
            "pipeline_runs": 3,
            "last_run_tokens": {},
        }
        with patch("job_matcher.cli.mongo_db") as mock_db:
            mock_db.cache_stats.return_value = fake_stats
            from job_matcher.cli import _cache_stats
            _cache_stats()

        out = capsys.readouterr().out
        assert "40" in out
        assert "100" in out
        assert "3" in out

    def test_prints_token_stats_when_present(self, capsys):
        fake_stats = {
            "enabled": True,
            "extractions_cached": 5,
            "raw_jobs_stored": 8,
            "pipeline_runs": 1,
            "last_run_tokens": {"total_tokens": 500, "cost_usd": 0.001},
        }
        with patch("job_matcher.cli.mongo_db") as mock_db:
            mock_db.cache_stats.return_value = fake_stats
            from job_matcher.cli import _cache_stats
            _cache_stats()

        out = capsys.readouterr().out
        assert "500" in out
        assert "0.001" in out

    def test_prints_disabled_message_when_mongo_off(self, capsys):
        with patch("job_matcher.cli.mongo_db") as mock_db:
            mock_db.cache_stats.return_value = {"enabled": False}
            from job_matcher.cli import _cache_stats
            _cache_stats()

        out = capsys.readouterr().out
        assert "disabled" in out.lower()
