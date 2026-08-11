import json
from pathlib import Path
from job_matcher.models import Job, ProfileData
from job_matcher.nodes.filter_ import apply_hard_filters

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sample_jobs.json").read_text()
)
JOBS = [Job(**f) for f in FIXTURES]

PROFILE = ProfileData(
    preferred_keywords=["Node.js", "Python", "TypeScript", "AWS", "Django"],
    reject_keywords=["US only", "must reside in the United States", "Salesforce", "internship", "Java only"],
    target_seniority=["mid-level", "semi-senior"],
    avoid_seniority=["junior", "trainee"],
)


def _get(job_id: str) -> Job:
    return next(j for j in JOBS if j.id == job_id)


def test_reject_keyword_us_only():
    passed, discarded = apply_hard_filters([_get("j004")], PROFILE)
    assert len(passed) == 0
    assert discarded[0].discard_reason.startswith("reject_keyword:")


def test_reject_keyword_salesforce():
    passed, discarded = apply_hard_filters([_get("j005")], PROFILE)
    assert len(passed) == 0
    assert "salesforce" in discarded[0].discard_reason.lower()


def test_reject_keyword_internship():
    passed, discarded = apply_hard_filters([_get("j010")], PROFILE)
    assert len(passed) == 0


def test_not_remote_eligible_discards():
    job = Job(
        id="z1", title="Dev", company="Co", apply_url="https://x.com",
        description="Great role", location="San Francisco, CA", remote=False
    )
    passed, discarded = apply_hard_filters([job], PROFILE)
    assert len(passed) == 0
    assert discarded[0].discard_reason == "not_remote_eligible"


def test_latam_in_location_passes():
    passed, _ = apply_hard_filters([_get("j001")], PROFILE)
    assert len(passed) == 1


def test_remote_worldwide_passes():
    passed, _ = apply_hard_filters([_get("j003")], PROFILE)
    assert len(passed) == 1


def test_multiple_mixed_jobs():
    passed, discarded = apply_hard_filters(JOBS, PROFILE)
    passing_ids = {j.id for j in passed}
    assert "j004" not in passing_ids
    assert "j005" not in passing_ids
    assert "j010" not in passing_ids
    assert "j001" in passing_ids
    assert "j003" in passing_ids
