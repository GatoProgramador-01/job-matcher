import pytest
from evals.evaluators.ranking import precision_at_3


class TestPrecisionAt3:
    def test_perfect_all_three_expected_in_top3(self):
        out = {"top_jobs": [{"id": "j1"}, {"id": "j7"}, {"id": "j3"}]}
        ref = {"expected_top_ids": ["j1", "j7", "j3"]}
        result = precision_at_3(out, ref)
        assert result["key"] == "precision_at_3"
        assert result["score"] == 1.0

    def test_perfect_two_expected_both_in_top3(self):
        out = {"top_jobs": [{"id": "j1"}, {"id": "j3"}, {"id": "j5"}]}
        ref = {"expected_top_ids": ["j1", "j3"]}
        result = precision_at_3(out, ref)
        assert result["score"] == 1.0

    def test_partial_one_of_two_expected_in_top3(self):
        out = {"top_jobs": [{"id": "j1"}, {"id": "j2"}, {"id": "j5"}]}
        ref = {"expected_top_ids": ["j1", "j3"]}
        result = precision_at_3(out, ref)
        assert result["score"] == 0.5

    def test_zero_none_in_top3(self):
        out = {"top_jobs": [{"id": "j4"}, {"id": "j5"}, {"id": "j6"}]}
        ref = {"expected_top_ids": ["j1", "j3"]}
        result = precision_at_3(out, ref)
        assert result["score"] == 0.0

    def test_only_checks_first_3_results(self):
        # j3 is in position 4 (index 3) — should NOT count as a hit
        out = {"top_jobs": [{"id": "j1"}, {"id": "j5"}, {"id": "j6"}, {"id": "j3"}]}
        ref = {"expected_top_ids": ["j1", "j3"]}
        result = precision_at_3(out, ref)
        assert result["score"] == 0.5  # only j1 hits in top-3

    def test_empty_expected_returns_zero(self):
        out = {"top_jobs": [{"id": "j1"}]}
        ref = {"expected_top_ids": []}
        result = precision_at_3(out, ref)
        assert result["score"] == 0.0

    def test_empty_top_jobs_returns_zero(self):
        out = {"top_jobs": []}
        ref = {"expected_top_ids": ["j1"]}
        result = precision_at_3(out, ref)
        assert result["score"] == 0.0

    def test_single_expected_hit(self):
        out = {"top_jobs": [{"id": "j7"}, {"id": "j2"}, {"id": "j3"}]}
        ref = {"expected_top_ids": ["j7"]}
        result = precision_at_3(out, ref)
        assert result["score"] == 1.0
