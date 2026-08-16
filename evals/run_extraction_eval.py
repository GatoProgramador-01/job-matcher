"""
Layer 1 eval -- extraction accuracy.

Runs DeepSeek against the 25 golden job postings and scores results
with four deterministic metrics (Jaccard skill overlap + 3 exact-match).

Usage:
    .venv/Scripts/python.exe evals/run_extraction_eval.py

Results appear in LangSmith under Experiments -> extraction-*
Estimated cost: ~$0.003 (25 jobs x DeepSeek pricing)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from langsmith import evaluate
from job_matcher.domain.models import Job
from job_matcher.nodes.extract import _extract_uncached_job
from job_matcher.infrastructure.deepseek import make_llm
from evals.evaluators.extraction import skill_overlap, seniority_match, remote_match, latam_match


def extraction_target(inputs: dict) -> dict:
    job = Job(
        id=inputs["id"],
        title=inputs["title"],
        company=inputs.get("company", "eval"),
        description=inputs["description"],
        apply_url="https://eval.local",
    )
    # Bypasses MongoDB cache -- eval measures live model behavior, not cached results
    llm = make_llm()
    extracted, _, _ = _extract_uncached_job(job, llm)
    return {
        "required_skills": extracted.required_skills,
        "seniority": extracted.seniority,
        "is_remote": extracted.is_remote,
        "latam_eligible": extracted.latam_eligible,
    }


THRESHOLDS = {
    "skill_overlap":    0.75,
    "seniority_match":  0.80,
    "remote_match":     0.90,
    "latam_match":      0.90,
}


def _check_thresholds(results) -> bool:
    scores: dict[str, list[float]] = {}
    for ex in results._results:
        for r in ex["evaluation_results"]["results"]:
            if r.score is not None:
                scores.setdefault(r.key, []).append(r.score)

    print("\nResults:")
    failed = False
    for key, threshold in THRESHOLDS.items():
        vals = scores.get(key, [])
        avg = sum(vals) / len(vals) if vals else 0.0
        status = "PASS" if avg >= threshold else "FAIL"
        if avg < threshold:
            failed = True
        print(f"  {status}  {key}: {avg:.2f}  (threshold >= {threshold:.2f})")
    return failed


if __name__ == "__main__":
    results = evaluate(
        extraction_target,
        data="job-matcher-extraction-v1",
        evaluators=[skill_overlap, seniority_match, remote_match, latam_match],
        experiment_prefix="extraction",
        max_concurrency=3,
    )
    failed = _check_thresholds(results)
    print("\nView results at: https://smith.langchain.com (Experiments tab)")
    if failed:
        print("REGRESSION DETECTED — one or more metrics below threshold")
        sys.exit(1)
