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


if __name__ == "__main__":
    results = evaluate(
        extraction_target,
        data="job-matcher-extraction-v1",
        evaluators=[skill_overlap, seniority_match, remote_match, latam_match],
        experiment_prefix="extraction",
        max_concurrency=3,
    )
    print("\nExperiment complete.")
    print("View results at: https://smith.langchain.com (Experiments tab)")
