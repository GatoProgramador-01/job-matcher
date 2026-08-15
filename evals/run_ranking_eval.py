"""
Layer 2 eval -- end-to-end ranking quality.

Runs extract -> score -> rank against 5 golden profile+job-batch scenarios.
Measures whether the pipeline returns the expected top jobs in its top 3.

Usage:
    .venv\Scripts\python.exe evals/run_ranking_eval.py

Results appear in LangSmith under Experiments -> ranking-*
Estimated cost: ~$0.002 (5 scenarios x 8 jobs each x DeepSeek pricing)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from langsmith import evaluate
from job_matcher.domain.models import Job, ProfileData, MatcherState
from job_matcher.nodes.extract import extract_node
from job_matcher.nodes.score import score_node
from job_matcher.nodes.rank import rank_node
from evals.evaluators.ranking import precision_at_3


def ranking_target(inputs: dict) -> dict:
    profile = ProfileData(**inputs["profile"])
    jobs = [
        Job(**{**j, "apply_url": j.get("apply_url", "https://eval.local")})
        for j in inputs["jobs"]
    ]

    # Pre-populate filtered_jobs directly -- skips fetch and filter nodes
    # since the dataset already provides the curated job batch to evaluate against
    state: MatcherState = {
        "profile": profile,
        "raw_jobs": [],
        "filtered_jobs": jobs,
        "extracted_jobs": [],
        "scored_jobs": [],
        "top_jobs": [],
        "output_format": "json",
        "token_stats": {},
    }

    state.update(extract_node(state))
    state.update(score_node(state))
    state.update(rank_node(state))

    return {
        "top_jobs": [{"id": sj.job.id, "score": sj.score} for sj in state["top_jobs"]]
    }


if __name__ == "__main__":
    results = evaluate(
        ranking_target,
        data="job-matcher-ranking-v1",
        evaluators=[precision_at_3],
        experiment_prefix="ranking",
    )
    print("\nExperiment complete.")
    print("View results at: https://smith.langchain.com (Experiments tab)")
