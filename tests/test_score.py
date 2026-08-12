from datetime import date
from job_matcher.models import Job, ExtractedJob, ProfileData
from job_matcher.nodes.score import score_job

PROFILE = ProfileData(
    preferred_keywords=["Node.js", "Python", "TypeScript", "AWS", "Django", "LangGraph", "RAG"],
    reject_keywords=[],
    target_seniority=["mid-level", "semi-senior"],
    avoid_seniority=["junior"],
)
TODAY = date(2026, 8, 11)


def _job(job_id="j1", title="Dev", description="", posted_at=TODAY):
    j = Job(id=job_id, title=title, company="Co", apply_url="https://x.com",
            description=description, posted_at=posted_at, remote=True)
    return ExtractedJob(job=j, required_skills=[], seniority=None,
                        is_remote=True, latam_eligible=True)


def test_stack_overlap_title_weighs_more():
    e_title = _job(title="Node.js TypeScript Developer", description="some work")
    e_body = _job(title="Developer", description="Node.js TypeScript experience preferred")
    s1, _ = score_job(e_title, PROFILE, TODAY)
    s2, _ = score_job(e_body, PROFILE, TODAY)
    assert s1 > s2


def test_seniority_mid_level_max_bonus():
    e = _job(title="Mid-level Backend Developer")
    e2 = _job(title="Senior Backend Developer")
    s, _ = score_job(e, PROFILE, TODAY)
    s2, _ = score_job(e2, PROFILE, TODAY)
    assert s > s2


def test_seniority_junior_penalizes():
    e = _job(title="Junior Python Developer", description="Python Django")
    e2 = _job(title="Mid-level Python Developer", description="Python Django")
    s, _ = score_job(e, PROFILE, TODAY)
    s2, _ = score_job(e2, PROFILE, TODAY)
    assert s < s2


def test_ai_bonus_tier_a_langgraph():
    e = _job(description="Building multi-agent systems with LangGraph and RAG pipelines.")
    e2 = _job(description="Standard backend work.")
    s, _ = score_job(e, PROFILE, TODAY)
    s2, _ = score_job(e2, PROFILE, TODAY)
    assert s > s2 + 15


def test_ai_bonus_tier_b_openai():
    e = _job(description="Integration with OpenAI API and machine learning models.")
    e2 = _job(description="Standard backend work.")
    s, _ = score_job(e, PROFILE, TODAY)
    s2, _ = score_job(e2, PROFILE, TODAY)
    assert s > s2


def test_recency_today_max():
    from datetime import date
    e_today = _job(posted_at=TODAY)
    e_old = _job(posted_at=date(2026, 7, 20))
    s1, _ = score_job(e_today, PROFILE, TODAY)
    s2, _ = score_job(e_old, PROFILE, TODAY)
    assert s1 > s2


def test_score_capped_at_100():
    e = _job(
        title="Mid-level Node.js TypeScript Python AWS Django Developer",
        description="LangGraph RAG multi-agent systems. LatAm eligible.",
        posted_at=TODAY
    )
    score, _ = score_job(e, PROFILE, TODAY)
    assert score <= 100


def test_score_floor_at_minus_20():
    e = _job(title="Junior intern trainee entry level")
    score, _ = score_job(e, PROFILE, TODAY)
    assert score >= -20


def test_score_breakdown_components_sum_to_total():
    e = _job(title="Mid-level Python Developer", description="LangGraph RAG", posted_at=TODAY)
    score, breakdown = score_job(e, PROFILE, TODAY)
    raw_sum = breakdown.stack + breakdown.seniority + breakdown.ai_bonus + breakdown.recency
    assert score == max(-20.0, min(100.0, raw_sum))
