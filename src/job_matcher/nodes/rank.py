"""
Rank node — sort scored jobs and emit final top-N results.

Reads:   state["scored_jobs"]   (list[ScoredJob])
         state["output_format"] ("table" | "json")
Writes:  state["top_jobs"]      (list[ScoredJob] — top 10 by score, desc)
         state["token_stats"]   (forwarded unchanged)

Side effects:
  - Prints results to stdout in table or JSON format (for CLI use)
  - No MongoDB writes, no LLM calls

Failure modes:
  - Empty scored_jobs: returns empty top_jobs (no crash)
  - output_format not json: falls through to table format
"""
import json

from ..domain.models import MatcherState, ScoredJob

TOP_N = 10


def rank_node(state: MatcherState) -> dict:
    sorted_jobs = sorted(state["scored_jobs"], key=lambda j: j.score, reverse=True)
    top = sorted_jobs[:TOP_N]
    _print_results(top, state["output_format"])
    return {
        "top_jobs": top,
        "token_stats": state.get("token_stats", {}),
    }



def _print_results(jobs: list[ScoredJob], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps([_to_dict(j) for j in jobs], indent=2, ensure_ascii=False))
        return

    print(f"\n{'#':<3} {'Score':<7} {'Title':<45} {'Company':<20} {'Posted':<12} URL")
    print("-" * 120)
    for i, sj in enumerate(jobs, 1):
        posted = str(sj.job.posted_at) if sj.job.posted_at else "unknown"
        title = sj.job.title[:44]
        company = sj.job.company[:19]
        print(f"{i:<3} {sj.score:<7.1f} {title:<45} {company:<20} {posted:<12} {sj.job.apply_url}")
    print()


def _to_dict(sj: ScoredJob) -> dict:
    return {
        "score": sj.score,
        "title": sj.job.title,
        "company": sj.job.company,
        "posted_at": str(sj.job.posted_at),
        "apply_url": sj.job.apply_url,
        "skills": sj.extracted.required_skills,
        "seniority": sj.extracted.seniority,
    }
