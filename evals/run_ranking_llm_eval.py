"""
Layer 3 eval -- LLM-as-judge ranking correctness.

Uses DeepSeek-chat to judge whether the pipeline's top-3 jobs are
semantically correct for the given profile. Mirrors the LangSmith
Evaluator Playground prompt exactly so results are comparable.

Usage:
    .venv/Scripts/python.exe evals/run_ranking_llm_eval.py

Results appear in LangSmith under Experiments -> ranking-llm-*
Estimated cost: ~$0.01 (5 scenarios x judge call x DeepSeek pricing)
"""
import json
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
from job_matcher.infrastructure.deepseek import make_llm

_JUDGE_PROMPT = """\
You are an expert technical recruiter and LLM evaluator. You assess whether an AI-powered job ranking pipeline correctly prioritized roles for a candidate's profile.

<Rubric>
A correct ranking (return true):
- Every job ID listed in referenceOutput.expected_top_ids appears in the first 3 entries of output.top_jobs.
- The top 3 jobs have titles or extracted skills that directly overlap with the candidate's preferred_keywords.
- The seniority level of each top-3 job falls within the candidate's target_seniority list, not in avoid_seniority.

Return false when any of the following is true:
- One or more expected_top_ids are absent from the top 3 of output.top_jobs.
- A job in the top 3 belongs to a seniority level listed in avoid_seniority (e.g., junior, intern, staff, principal) and a better-matched job was available in the batch.
- A job in the top 3 has no meaningful skill overlap with preferred_keywords while expected jobs with clear overlap were ranked lower.
- The top 3 contains a role in a fundamentally different tech stack than the profile requests.
</Rubric>

<Instructions>
1. Read input.profile: note preferred_keywords, target_seniority, and avoid_seniority.
2. Read referenceOutput.expected_top_ids — these are the gold-standard correct answers.
3. Extract the first 3 entries from output.top_jobs. Only these 3 positions matter.
4. For each expected ID: check if it appears in those 3 positions. If any is missing, the ranking is wrong.
5. For each top-3 job: check seniority against avoid_seniority and check skill overlap with preferred_keywords.
6. Return true only if all expected IDs are present AND no disqualifying seniority or skill mismatch exists.
</Instructions>

<Reminder>
Focus on whether the right jobs surfaced at the top — not on exact score values or position within the top 3. Do not penalize the pipeline for ranking two tied jobs in either order when both are expected.
</Reminder>

<input>
{input}
</input>

<output>
{output}
</output>

<referenceOutput>
{reference_output}
</referenceOutput>

Reply with exactly one word: true or false."""


def ranking_target(inputs: dict) -> dict:
    profile = ProfileData(**inputs["profile"])
    jobs = [
        Job(**{"company": "eval", **j, "apply_url": j.get("apply_url", "https://eval.local")})
        for j in inputs["jobs"]
    ]
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


def ranking_correctness(outputs: dict, reference_outputs: dict, inputs: dict) -> dict:
    """LLM-as-judge: asks DeepSeek-chat whether the top-3 matches the expected IDs."""
    llm = make_llm()
    prompt = _JUDGE_PROMPT.format(
        input=json.dumps(inputs, indent=2),
        output=json.dumps(outputs, indent=2),
        reference_output=json.dumps(reference_outputs, indent=2),
    )
    response = llm.invoke(prompt)
    verdict = response.content.strip().lower()
    score = 1.0 if verdict == "true" else 0.0

    # Print per-scenario verdict for immediate feedback
    top3 = [j["id"] for j in (outputs.get("top_jobs") or [])][:3]
    expected = reference_outputs.get("expected_top_ids", [])
    print(f"  judge={verdict!r}  top3={top3}  expected={expected}")

    return {"key": "ranking_correctness", "score": score}


if __name__ == "__main__":
    results = evaluate(
        ranking_target,
        data="job-matcher-ranking-v1",
        evaluators=[ranking_correctness],
        experiment_prefix="ranking-llm",
    )
    print("\nExperiment complete.")
    print("View results at: https://smith.langchain.com (Experiments tab)")
