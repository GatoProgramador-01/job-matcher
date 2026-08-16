import pytest
from evals.evaluators.extraction import skill_overlap, seniority_match, remote_match, latam_match


class TestSkillOverlap:
    def test_perfect_match(self):
        out = {"required_skills": ["Python", "FastAPI"]}
        ref = {"required_skills": ["Python", "FastAPI"]}
        result = skill_overlap(out, ref)
        assert result["key"] == "skill_overlap"
        assert result["score"] == pytest.approx(1.0)

    def test_partial_match(self):
        out = {"required_skills": ["Python", "FastAPI", "Docker"]}
        ref = {"required_skills": ["Python", "FastAPI", "PostgreSQL"]}
        result = skill_overlap(out, ref)
        assert result["score"] == pytest.approx(0.5)

    def test_no_match(self):
        out = {"required_skills": ["Go", "Rust"]}
        ref = {"required_skills": ["Python", "FastAPI"]}
        result = skill_overlap(out, ref)
        assert result["score"] == pytest.approx(0.0)

    def test_empty_predicted(self):
        out = {"required_skills": []}
        ref = {"required_skills": ["Python"]}
        result = skill_overlap(out, ref)
        assert result["score"] == pytest.approx(0.0)

    def test_both_empty(self):
        out = {"required_skills": []}
        ref = {"required_skills": []}
        result = skill_overlap(out, ref)
        assert result["score"] == pytest.approx(1.0)

    def test_case_insensitive(self):
        out = {"required_skills": ["python", "fastapi"]}
        ref = {"required_skills": ["Python", "FastAPI"]}
        result = skill_overlap(out, ref)
        assert result["score"] == pytest.approx(1.0)

    def test_missing_key_returns_zero(self):
        result = skill_overlap({}, {"required_skills": ["Python"]})
        assert result["score"] == pytest.approx(0.0)


class TestSeniorityMatch:
    def test_correct_senior(self):
        assert seniority_match({"seniority": "senior"}, {"seniority": "senior"})["score"] == 1.0

    def test_wrong_seniority(self):
        assert seniority_match({"seniority": "junior"}, {"seniority": "senior"})["score"] == 0.0

    def test_both_null(self):
        assert seniority_match({"seniority": None}, {"seniority": None})["score"] == 1.0

    def test_key_name(self):
        result = seniority_match({"seniority": "mid"}, {"seniority": "mid"})
        assert result["key"] == "seniority_match"

    def test_missing_key_counts_as_none(self):
        assert seniority_match({}, {"seniority": None})["score"] == 1.0


class TestRemoteMatch:
    def test_both_true(self):
        assert remote_match({"is_remote": True}, {"is_remote": True})["score"] == 1.0

    def test_mismatch(self):
        assert remote_match({"is_remote": False}, {"is_remote": True})["score"] == 0.0

    def test_key_name(self):
        assert remote_match({"is_remote": True}, {"is_remote": True})["key"] == "remote_match"


class TestLatamMatch:
    def test_both_true(self):
        assert latam_match({"latam_eligible": True}, {"latam_eligible": True})["score"] == 1.0

    def test_mismatch(self):
        assert latam_match({"latam_eligible": False}, {"latam_eligible": True})["score"] == 0.0

    def test_key_name(self):
        assert latam_match({"latam_eligible": False}, {"latam_eligible": False})["key"] == "latam_match"
