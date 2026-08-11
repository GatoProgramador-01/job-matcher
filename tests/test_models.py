from datetime import date
from job_matcher.models import Job, ExtractedJob, ScoredJob, ProfileData


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
    s = ScoredJob(job=j, extracted=e, score=75.0)
    assert s.discard_reason is None
