"""
Filter node — hard rule-based job rejection before LLM extraction.

Reads:   state["raw_jobs"]       (list[dict] — raw job dicts from fetch_node)
         state["profile"]        (ProfileData — provides reject_keywords)
Writes:  state["filtered_jobs"]  (list[Job] — jobs that passed all filters)
         state["token_stats"]    (forwarded unchanged from fetch_node)

Filtering rules applied in order:
  1. Non-tech title signals (sales, marketing, medical, etc.) -> discard
  2. Profile reject_keywords found anywhere in title+description+location -> discard
  3. No remote signal in title+description+location -> discard
     (signals: remote, latam, latin america, chile, worldwide, anywhere)

Failure modes:
  - No side effects. Purely in-memory filtering.
  - A job with an empty description passes rule 3 only if its title/location
    contains a remote signal.
"""
from ..domain.models import Job, ScoredJob, ExtractedJob, ProfileData, MatcherState, ScoreBreakdown

_REMOTE_SIGNALS = ["remote", "latam", "latin america", "chile", "worldwide", "anywhere"]

# Non-tech title signals — reject roles that are clearly not engineering
_NON_TECH_TITLES = [
    "sales", "marketing", "copywriter", "graphic designer", " designer",
    "recruiter", "hr ", "human resource", "accountant", "finance",
    "customer success", "customer support", "jedi",
    "communications", "content writer", "content reviewer", "social media",
    "writer", "patient care", "medical", "office assistant",
    "bookkeeper", "billing", "paralegal", "legal assistant",
    "virtual assistant", "transcription", "data entry",
]


def _text(job: Job) -> str:
    return f"{job.title} {job.description} {job.location or ''}".lower()


def apply_hard_filters(
    jobs: list[Job], profile: ProfileData
) -> tuple[list[Job], list[ScoredJob]]:
    passed: list[Job] = []
    discarded: list[ScoredJob] = []

    for job in jobs:
        text = _text(job)
        reason = None

        # Reject clearly non-engineering titles
        title_lower = job.title.lower()
        if any(sig in title_lower for sig in _NON_TECH_TITLES):
            reason = "non_tech_title"

        if reason is None:
            for kw in profile.reject_keywords:
                if kw.lower() in text:
                    reason = f"reject_keyword:{kw}"
                    break

        if reason is None:
            if not any(sig in text for sig in _REMOTE_SIGNALS):
                reason = "not_remote_eligible"

        if reason:
            extracted = ExtractedJob(job=job)
            zero_breakdown = ScoreBreakdown(stack=0.0, seniority=0.0, ai_bonus=0.0, recency=0.0)
            discarded.append(ScoredJob(job=job, extracted=extracted, score=-999,
                                       breakdown=zero_breakdown, discard_reason=reason))
        else:
            passed.append(job)

    return passed, discarded


def filter_node(state: MatcherState) -> dict:
    jobs = [Job(**r) for r in state["raw_jobs"]]
    passed, _ = apply_hard_filters(jobs, state["profile"])
    return {
        "filtered_jobs": passed,
        "token_stats": state.get("token_stats", {}),
    }

