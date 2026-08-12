from datetime import date
from job_matcher.models import Job, ExtractedJob, ScoredJob, ProfileData, ScoreBreakdown, MatcherState


def test_job_defaults():
    j = Job(id="x", title="Dev", company="Co", apply_url="https://x.com")
    assert j.remote is False
    assert j.description == ""
    assert j.posted_at is None


def test_extracted_job_wraps_job():
    j = Job(id="x", title="Dev", company="Co", apply_url="https://x.com")
    e = ExtractedJob(job=j, required_skills=["Python"], seniority="mid", is_remote=True, latam_eligible=True)
    assert e.job.id == "x"
    assert "Python" in e.required_skills


def test_profile_data_loads():
    p = ProfileData(
        preferred_keywords=["Python", "Node.js"],
        reject_keywords=["US only"],
        target_seniority=["mid-level"],
        avoid_seniority=["junior"],
    )
    assert "Python" in p.preferred_keywords


def test_scored_job_discard_reason_optional():
    j = Job(id="x", title="Dev", company="Co", apply_url="https://x.com")
    e = ExtractedJob(job=j)
    bd = ScoreBreakdown(stack=0.0, seniority=0.0, ai_bonus=0.0, recency=0.0)
    s = ScoredJob(job=j, extracted=e, score=75.0, breakdown=bd)
    assert s.discard_reason is None


def test_matcher_state_accepts_progress_queue():
    state: MatcherState = {
        "profile": ProfileData(
            preferred_keywords=[], reject_keywords=[],
            target_seniority=[], avoid_seniority=[],
        ),
        "raw_jobs": [],
        "filtered_jobs": [],
        "extracted_jobs": [],
        "scored_jobs": [],
        "top_jobs": [],
        "output_format": "json",
        "token_stats": {},
        "progress_queue": None,
    }
    assert state.get("progress_queue") is None


def test_matcher_state_without_progress_queue_still_works():
    state: MatcherState = {
        "profile": ProfileData(
            preferred_keywords=[], reject_keywords=[],
            target_seniority=[], avoid_seniority=[],
        ),
        "raw_jobs": [],
        "filtered_jobs": [],
        "extracted_jobs": [],
        "scored_jobs": [],
        "top_jobs": [],
        "output_format": "json",
        "token_stats": {},
    }
    # .get() on a TypedDict (which is a dict at runtime) returns None for absent keys
    assert state.get("progress_queue") is None
