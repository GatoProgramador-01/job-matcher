"""
Score node — deterministic scoring of extracted jobs against the user profile.

Reads:   state["extracted_jobs"] (list[ExtractedJob])
         state["profile"]        (ProfileData — preferred_keywords drive stack score)
Writes:  state["scored_jobs"]    (list[ScoredJob] with score and breakdown)
         state["token_stats"]    (forwarded unchanged)

Scoring formula (see domain/scoring.py):
  score = stack(0-40) + seniority(-20/0/+10/+20) + ai_bonus(0/+10/+20) + recency(0-20)
  clamped to [-20.0, 100.0]

  stack:    keyword match vs preferred_keywords; title match = 3x body match
  seniority: junior/intern/entry-level = -20; mid/ssr/semi-senior = +20;
             senior (not staff/principal/lead/architect) = +10; unknown = 0
  ai_bonus: Tier A (langgraph, multi-agent, rag, langchain, etc.) = +20;
            Tier B (openai, llm, machine learning, embedding) = +10
  recency:  today = +20; <=3 days = +15; <=7 = +10; <=14 = +5; older/unknown = 0

Failure modes:
  - No LLM calls, no I/O. All failures are logic bugs, not runtime errors.
"""
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
