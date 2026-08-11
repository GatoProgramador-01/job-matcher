from ..models import Job, ScoredJob, ExtractedJob, ProfileData, MatcherState

_REMOTE_SIGNALS = ["remote", "latam", "latin america", "chile", "worldwide", "anywhere"]


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

        for kw in profile.reject_keywords:
            if kw.lower() in text:
                reason = f"reject_keyword:{kw}"
                break

        if reason is None:
            if not any(sig in text for sig in _REMOTE_SIGNALS):
                reason = "not_remote_eligible"

        if reason:
            extracted = ExtractedJob(job=job)
            discarded.append(ScoredJob(job=job, extracted=extracted, score=-999, discard_reason=reason))
        else:
            passed.append(job)

    return passed, discarded


def filter_node(state: MatcherState) -> dict:
    jobs = [Job(**r) for r in state["raw_jobs"]]
    passed, _ = apply_hard_filters(jobs, state["profile"])
    return {"filtered_jobs": passed}
