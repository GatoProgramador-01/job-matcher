"""
Extract node — uses DeepSeek chat + MongoDB cache + parallel worker threads.

Optimizations:
1. MongoDB LLM Cache: Returns cached extractions instantly (0 API tokens used).
2. HTML Sanitization: Strips HTML tags so prompt is clean plain text.
3. Compact Truncation: Caps description payload to 1,200 chars (removes legal/boilerplate footer).
4. Token Tracking: Accounts for prompt/completion tokens and estimated DeepSeek USD cost.
5. Parallel Execution: Runs uncached extractions concurrently in a ThreadPool.
6. Progress Queue: Emits per-job events into MatcherState.progress_queue when present.
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Tuple

from bs4 import BeautifulSoup
from langchain_openai import ChatOpenAI

from ..domain.models import Job, ExtractedJob, MatcherState
from ..infrastructure.deepseek import make_llm as _make_llm, PRICE_PROMPT as _PRICE_PROMPT, PRICE_COMPLETION as _PRICE_COMPLETION
from ..infrastructure.mongo import mongo_db
from ..token_tracker import TokenTracker

_SYSTEM = (
    "You are a job posting analyzer. Given a job title and description, "
    "extract information and respond with ONLY a valid JSON object — no markdown, "
    "no explanation, just raw JSON.\n\n"
    "Required fields:\n"
    '  "required_skills": list[str]  — technical skills explicitly mentioned\n'
    '  "seniority": "junior"|"mid"|"senior"|"staff"|null\n'
    '  "is_remote": bool\n'
    '  "latam_eligible": bool  — true if Latin American candidates are mentioned/welcomed\n\n'
    "Example output:\n"
    '{"required_skills":["Python","FastAPI","PostgreSQL"],"seniority":"senior",'
    '"is_remote":true,"latam_eligible":false}'
)

_JSON_RE = re.compile(r'\{.*\}', re.DOTALL)


def _clean_text(html_or_text: str) -> str:
    if not html_or_text:
        return ""
    try:
        soup = BeautifulSoup(html_or_text, "html.parser")
        text = soup.get_text(separator=" ")
    except Exception:
        text = re.sub(r'<[^>]+>', ' ', html_or_text)
    return " ".join(text.split())


def _parse_response(text: str) -> dict:
    m = _JSON_RE.search(text)
    if not m:
        raise ValueError(f"No JSON found in response: {text[:200]}")
    return json.loads(m.group())


def _extract_uncached_job(job: Job, llm: ChatOpenAI) -> Tuple[ExtractedJob, int, int]:
    clean_desc = _clean_text(job.description)[:1200]
    prompt = f"Title: {job.title}\n\nDescription: {clean_desc}"

    prompt_tokens = 0
    completion_tokens = 0

    try:
        result = llm.invoke([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ])

        if hasattr(result, "response_metadata") and isinstance(result.response_metadata, dict):
            usage = result.response_metadata.get("token_usage") or result.response_metadata.get("tokenUsage") or {}
            prompt_tokens = usage.get("prompt_tokens") or usage.get("promptTokens") or 0
            completion_tokens = usage.get("completion_tokens") or usage.get("completionTokens") or 0

        if prompt_tokens == 0:
            prompt_tokens = len(_SYSTEM) // 4 + len(prompt) // 4
        if completion_tokens == 0:
            completion_tokens = len(result.content) // 4

        data = _parse_response(result.content)
        extracted = ExtractedJob(
            job=job,
            required_skills=data.get("required_skills") or [],
            seniority=data.get("seniority"),
            is_remote=bool(data.get("is_remote", True)),
            latam_eligible=bool(data.get("latam_eligible", False)),
        )

        mongo_db.save_extraction(
            job_id=job.id,
            required_skills=extracted.required_skills,
            seniority=extracted.seniority,
            is_remote=extracted.is_remote,
            latam_eligible=extracted.latam_eligible,
            tokens_used=(prompt_tokens + completion_tokens),
        )

        return extracted, prompt_tokens, completion_tokens

    except Exception as exc:
        print(f"[extract] WARN: LLM extraction failed for '{job.title}': {exc}", file=sys.stderr)
        return ExtractedJob(job=job), prompt_tokens, completion_tokens


def _emit_progress(
    queue: Any,
    index: int,
    total: int,
    job: Job,
    skills: list[str],
    prompt_tokens: int,
    completion_tokens: int,
    cached: bool,
) -> None:
    if queue is None:
        return
    tokens = prompt_tokens + completion_tokens
    cost = round((prompt_tokens * _PRICE_PROMPT) + (completion_tokens * _PRICE_COMPLETION), 6)
    queue.put({
        "_type": "job_progress",
        "index": index,
        "total": total,
        "title": job.title,
        "skills": skills,
        "tokens": tokens,
        "cost": cost,
        "cached": cached,
    })


def extract_node(state: MatcherState) -> dict:
    tracker = TokenTracker()

    existing_stats = state.get("token_stats") or {}
    if existing_stats:
        tracker.prompt_tokens = existing_stats.get("prompt_tokens", 0)
        tracker.completion_tokens = existing_stats.get("completion_tokens", 0)
        tracker.total_tokens = existing_stats.get("total_tokens", 0)
        tracker.cache_hits = existing_stats.get("cache_hits", 0)
        tracker.cache_misses = existing_stats.get("cache_misses", 0)
        tracker.saved_tokens = existing_stats.get("saved_tokens", 0)

    queue = state.get("progress_queue")
    filtered_jobs = state["filtered_jobs"]
    total = len(filtered_jobs)

    if queue is not None:
        queue.put({"_type": "node_start", "_node": "extract", "total": total})

    extracted_results: dict[str, ExtractedJob] = {}
    jobs_to_fetch_llm: list[Job] = []
    progress_index = 0

    # Step 1: MongoDB cache check
    for job in filtered_jobs:
        cached = mongo_db.get_extraction(job.id)
        if cached:
            tracker.add_cache_hit()
            extracted_results[job.id] = ExtractedJob(
                job=job,
                required_skills=cached.get("required_skills") or [],
                seniority=cached.get("seniority"),
                is_remote=cached.get("is_remote", True),
                latam_eligible=cached.get("latam_eligible", False),
            )
            progress_index += 1
            # Emit progress for cache hits: 0 tokens (already paid for)
            _emit_progress(queue, progress_index, total, job,
                           cached.get("required_skills") or [], 0, 0, cached=True)
        else:
            jobs_to_fetch_llm.append(job)

    print(
        f"[extract] {total} jobs — "
        f"{len(extracted_results)} cache hits, "
        f"{len(jobs_to_fetch_llm)} LLM extractions needed",
        file=sys.stderr,
    )

    # Step 2: Parallel LLM extractions
    if jobs_to_fetch_llm:
        llm = _make_llm()
        max_threads = min(5, len(jobs_to_fetch_llm))
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            future_to_job = {
                executor.submit(_extract_uncached_job, j, llm): j for j in jobs_to_fetch_llm
            }
            for future in as_completed(future_to_job):
                job = future_to_job[future]
                try:
                    extracted_job, p_tokens, c_tokens = future.result()
                    extracted_results[job.id] = extracted_job
                    tracker.add_llm_usage(p_tokens, c_tokens)
                    progress_index += 1
                    _emit_progress(queue, progress_index, total, job,
                                   extracted_job.required_skills, p_tokens, c_tokens, cached=False)
                except Exception as exc:
                    print(f"[extract] Thread error for '{job.title}': {exc}", file=sys.stderr)
                    extracted_results[job.id] = ExtractedJob(job=job)
                    progress_index += 1
                    _emit_progress(queue, progress_index, total, job, [], 0, 0, cached=False)

    final_extracted = [extracted_results[j.id] for j in filtered_jobs if j.id in extracted_results]

    return {
        "extracted_jobs": final_extracted,
        "token_stats": tracker.to_dict(),
    }
