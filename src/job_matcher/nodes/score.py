from datetime import date
from ..models import ExtractedJob, ScoredJob, ProfileData, MatcherState

_TIER_A = ["langgraph", "multi-agent", "anthropic", "rag", "agentic", "vector search", "langchain"]
_TIER_B = ["openai", "llm", "machine learning", "embedding", " ai "]

_MID_SIGNALS = ["mid-level", "mid level", "semi-senior", "ssr", "semi senior", "midlevel"]
_SENIOR_SIGNALS = ["senior"]
_JUNIOR_SIGNALS = ["junior", "trainee", "intern", "entry level", "entry-level"]
_EXCLUDE_SENIOR = ["staff", "principal", "lead", "architect", "head of"]

_RECENCY = [(0, 20), (3, 15), (7, 10), (14, 5)]


def _stack_score(extracted: ExtractedJob, keywords: list[str]) -> float:
    title = extracted.job.title.lower()
    body = extracted.job.description.lower()
    skills = " ".join(extracted.required_skills).lower()
    raw = sum(
        3 if kw.lower() in title else (1 if kw.lower() in body or kw.lower() in skills else 0)
        for kw in keywords
    )
    max_possible = len(keywords) * 3
    return min(40.0, (raw / max(max_possible, 1)) * 40 * 2)


def _seniority_score(extracted: ExtractedJob) -> float:
    text = f"{extracted.job.title} {extracted.seniority or ''}".lower()
    if any(s in text for s in _JUNIOR_SIGNALS):
        return -20.0
    if any(s in text for s in _MID_SIGNALS):
        return 20.0
    if any(s in text for s in _SENIOR_SIGNALS) and not any(e in text for e in _EXCLUDE_SENIOR):
        return 10.0
    return 0.0


def _ai_bonus(extracted: ExtractedJob) -> float:
    text = f"{extracted.job.title} {extracted.job.description}".lower()
    if any(t in text for t in _TIER_A):
        return 20.0
    if any(t in text for t in _TIER_B):
        return 10.0
    return 0.0


def _recency_score(extracted: ExtractedJob, today: date) -> float:
    if extracted.job.posted_at is None:
        return 0.0
    age = (today - extracted.job.posted_at).days
    for threshold, points in _RECENCY:
        if age <= threshold:
            return float(points)
    return 0.0


def score_job(extracted: ExtractedJob, profile: ProfileData, today: date) -> float:
    total = (
        _stack_score(extracted, profile.preferred_keywords)
        + _seniority_score(extracted)
        + _ai_bonus(extracted)
        + _recency_score(extracted, today)
    )
    return max(-20.0, min(100.0, total))


def score_node(state: MatcherState) -> dict:
    profile = state["profile"]
    today = date.today()
    scored = [
        ScoredJob(
            job=e.job,
            extracted=e,
            score=score_job(e, profile, today),
        )
        for e in state["extracted_jobs"]
    ]
    return {"scored_jobs": scored}
