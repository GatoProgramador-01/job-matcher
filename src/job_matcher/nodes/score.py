from datetime import date
from ..domain.models import ExtractedJob, ScoredJob, ProfileData, MatcherState
from ..domain.scoring import score_job


def score_node(state: MatcherState) -> dict:
    profile = state["profile"]
    today = date.today()
    scored = []
    for e in state["extracted_jobs"]:
        total, breakdown = score_job(e, profile, today)
        scored.append(ScoredJob(job=e.job, extracted=e, score=total, breakdown=breakdown))
    return {
        "scored_jobs": scored,
        "token_stats": state.get("token_stats", {}),
    }
