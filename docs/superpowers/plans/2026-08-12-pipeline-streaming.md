# Pipeline Streaming (Sprint 2A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emit per-job SSE events from `extract_node` via a `SimpleQueue` side channel, replace the spinner with a visual progress card, and persist token breakdown in `pipeline_runs`.

**Architecture:** `extract_node` puts `job_progress` events into a `queue.SimpleQueue` stored in `MatcherState.progress_queue`. `_stream_pipeline` in `jobs.py` runs the LangGraph pipeline in a thread via `run_in_executor`, drains the queue asynchronously, and yields SSE events. The frontend replaces `PipelineStatus` with a new `PipelineProgress` card component.

**Tech Stack:** Python 3.11, FastAPI SSE, LangGraph, DeepSeek (response_metadata token tracking), React 19, Next.js 15 App Router, TypeScript strict, Tailwind CSS, Playwright.

## Global Constraints

- Token tracking must use `result.response_metadata` (DeepSeek-specific) — NOT `get_openai_callback()` (OpenAI-only, won't work with DeepSeek).
- Keep existing SSE event fields (`node`, `done_node`, `jobs`, `token_stats`) — new events are additive.
- `progress_queue: None` (absent key) must never raise in any node — always use `state.get("progress_queue")`.
- TypeScript strict mode — no `any` casts, no unused variables.
- Working dir: `C:\Users\lanitaEmperadora\Documents\github\job-matcher`
- Backend venv: `.venv\Scripts\python` (Windows)
- Frontend: `web\` subdirectory, `npm` commands run from `web\`

---

### Task 1: Add `progress_queue` to `MatcherState`

**Files:**
- Modify: `src/job_matcher/models.py`

**Interfaces:**
- Produces: `MatcherState.progress_queue: NotRequired[Any]` — consumed by Task 2 (`extract_node`) and Task 3 (`jobs.py`)

- [ ] **Step 1: Write the failing type-check test**

Create `tests/test_models.py`:

```python
from job_matcher.models import MatcherState, ProfileData


def test_matcher_state_accepts_progress_queue():
    state: MatcherState = {
        "profile": ProfileData(
            preferred_keywords=[], reject_keywords=[],
            target_seniority=[], avoid_seniority=[],
        ),
        "raw_jobs": [],
        "filtered_jobs": [],
        "extracted_jobs": [],
        "scored_jobs": [],
        "top_jobs": [],
        "output_format": "json",
        "token_stats": {},
        "progress_queue": None,
    }
    assert state.get("progress_queue") is None


def test_matcher_state_without_progress_queue_still_works():
    state: MatcherState = {
        "profile": ProfileData(
            preferred_keywords=[], reject_keywords=[],
            target_seniority=[], avoid_seniority=[],
        ),
        "raw_jobs": [],
        "filtered_jobs": [],
        "extracted_jobs": [],
        "scored_jobs": [],
        "top_jobs": [],
        "output_format": "json",
        "token_stats": {},
    }
    # .get() on a TypedDict (which is a dict at runtime) returns None for absent keys
    assert state.get("progress_queue") is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd C:\Users\lanitaEmperadora\Documents\github\job-matcher
.venv\Scripts\python -m pytest tests/test_models.py -v
```

Expected: `KeyError` or import error — `progress_queue` not in `MatcherState`.

- [ ] **Step 3: Add `progress_queue` to `MatcherState`**

In `src/job_matcher/models.py`, replace the import line and add the field:

```python
# Change this line:
from typing_extensions import TypedDict
# To this:
from typing_extensions import TypedDict, NotRequired
```

And in `MatcherState`, add after `token_stats`:

```python
class MatcherState(TypedDict):
    profile: ProfileData
    raw_jobs: list[dict[str, Any]]
    filtered_jobs: list[Job]
    extracted_jobs: list[ExtractedJob]
    scored_jobs: list[ScoredJob]
    top_jobs: list[ScoredJob]
    output_format: Literal["table", "json"]
    token_stats: dict[str, Any]
    progress_queue: NotRequired[Any]  # queue.SimpleQueue | None — absent = no progress streaming
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv\Scripts\python -m pytest tests/test_models.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Run full test suite to verify no regressions**

```bash
.venv\Scripts\python -m pytest tests/ -v --tb=short
```

Expected: all existing tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/job_matcher/models.py tests/test_models.py
git commit -m "feat(models): add NotRequired progress_queue to MatcherState"
```

---

### Task 2: Update `extract_node` to emit per-job progress events

**Files:**
- Modify: `src/job_matcher/nodes/extract.py`
- Modify: `tests/test_pipeline.py` (add 4 tests)

**Interfaces:**
- Consumes: `MatcherState.progress_queue: NotRequired[Any]` from Task 1
- Produces: queue events `{"_type": "node_start", "_node": "extract", "total": int}` and `{"_type": "job_progress", "index": int, "total": int, "title": str, "skills": list[str], "tokens": int, "cost": float, "cached": bool}` — consumed by Task 3 (`jobs.py` drain loop)

- [ ] **Step 1: Write 4 failing tests**

Add to `tests/test_pipeline.py` (after existing tests):

```python
import queue as q_module


# ── extract_node progress events ────────────────────────────────────────────

def test_extract_node_emits_node_start_event(monkeypatch):
    """First event in queue must be node_start with total count."""
    from job_matcher.models import Job
    from job_matcher.nodes.extract import extract_node

    mock_result = MagicMock()
    mock_result.content = '{"required_skills":["Go"],"seniority":"senior","is_remote":true,"latam_eligible":false}'
    mock_result.response_metadata = {}
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_result

    jobs = [
        Job(id=f"j{i}", title=f"Dev {i}", company="Co",
            description="Go role.", apply_url=f"https://x.com/{i}")
        for i in range(3)
    ]
    q = q_module.SimpleQueue()
    state = {
        "profile": ProfileData(preferred_keywords=["Go"], reject_keywords=[],
                               target_seniority=[], avoid_seniority=[]),
        "raw_jobs": [], "filtered_jobs": jobs, "extracted_jobs": [],
        "scored_jobs": [], "top_jobs": [], "output_format": "json",
        "token_stats": {}, "progress_queue": q,
    }

    with patch("job_matcher.nodes.extract._make_llm", return_value=mock_llm), \
         patch("job_matcher.nodes.extract.mongo_db.get_extraction", return_value=None), \
         patch("job_matcher.nodes.extract.mongo_db.save_extraction"):
        extract_node(state)

    first = q.get_nowait()
    assert first["_type"] == "node_start"
    assert first["_node"] == "extract"
    assert first["total"] == 3


def test_extract_node_emits_job_progress_per_job(monkeypatch):
    """Queue receives one job_progress event per job (cached or LLM)."""
    from job_matcher.models import Job
    from job_matcher.nodes.extract import extract_node

    mock_result = MagicMock()
    mock_result.content = '{"required_skills":["Python"],"seniority":"mid","is_remote":true,"latam_eligible":false}'
    mock_result.response_metadata = {}
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_result

    jobs = [
        Job(id=f"j{i}", title=f"Dev {i}", company="Co",
            description="Python role.", apply_url=f"https://x.com/{i}")
        for i in range(4)
    ]
    q = q_module.SimpleQueue()
    state = {
        "profile": ProfileData(preferred_keywords=["Python"], reject_keywords=[],
                               target_seniority=[], avoid_seniority=[]),
        "raw_jobs": [], "filtered_jobs": jobs, "extracted_jobs": [],
        "scored_jobs": [], "top_jobs": [], "output_format": "json",
        "token_stats": {}, "progress_queue": q,
    }

    with patch("job_matcher.nodes.extract._make_llm", return_value=mock_llm), \
         patch("job_matcher.nodes.extract.mongo_db.get_extraction", return_value=None), \
         patch("job_matcher.nodes.extract.mongo_db.save_extraction"):
        extract_node(state)

    events = []
    while not q.empty():
        events.append(q.get_nowait())

    progress_events = [e for e in events if e["_type"] == "job_progress"]
    assert len(progress_events) == 4  # one per job


def test_progress_event_has_required_fields(monkeypatch):
    """Each job_progress event must have index, total, title, skills, tokens, cost, cached."""
    from job_matcher.models import Job
    from job_matcher.nodes.extract import extract_node

    mock_result = MagicMock()
    mock_result.content = '{"required_skills":["Rust"],"seniority":"senior","is_remote":true,"latam_eligible":false}'
    mock_result.response_metadata = {}
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_result

    job = Job(id="r1", title="Rust Dev", company="Co",
              description="Rust role.", apply_url="https://x.com/1")
    q = q_module.SimpleQueue()
    state = {
        "profile": ProfileData(preferred_keywords=["Rust"], reject_keywords=[],
                               target_seniority=[], avoid_seniority=[]),
        "raw_jobs": [], "filtered_jobs": [job], "extracted_jobs": [],
        "scored_jobs": [], "top_jobs": [], "output_format": "json",
        "token_stats": {}, "progress_queue": q,
    }

    with patch("job_matcher.nodes.extract._make_llm", return_value=mock_llm), \
         patch("job_matcher.nodes.extract.mongo_db.get_extraction", return_value=None), \
         patch("job_matcher.nodes.extract.mongo_db.save_extraction"):
        extract_node(state)

    events = [q.get_nowait() for _ in range(q.qsize() + 2) if not q.empty()]
    progress = next(e for e in events if e["_type"] == "job_progress")
    assert "index" in progress
    assert "total" in progress
    assert "title" in progress
    assert "skills" in progress
    assert "tokens" in progress
    assert "cost" in progress
    assert "cached" in progress
    assert progress["title"] == "Rust Dev"


def test_extract_node_works_without_queue(monkeypatch):
    """progress_queue absent from state must not raise."""
    from job_matcher.models import Job
    from job_matcher.nodes.extract import extract_node

    mock_result = MagicMock()
    mock_result.content = '{"required_skills":["Java"],"seniority":"mid","is_remote":true,"latam_eligible":false}'
    mock_result.response_metadata = {}
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_result

    job = Job(id="j1", title="Java Dev", company="Co",
              description="Java role.", apply_url="https://x.com/1")
    state = {
        "profile": ProfileData(preferred_keywords=["Java"], reject_keywords=[],
                               target_seniority=[], avoid_seniority=[]),
        "raw_jobs": [], "filtered_jobs": [job], "extracted_jobs": [],
        "scored_jobs": [], "top_jobs": [], "output_format": "json",
        "token_stats": {},
        # progress_queue intentionally absent
    }

    with patch("job_matcher.nodes.extract._make_llm", return_value=mock_llm), \
         patch("job_matcher.nodes.extract.mongo_db.get_extraction", return_value=None), \
         patch("job_matcher.nodes.extract.mongo_db.save_extraction"):
        result = extract_node(state)  # must not raise

    assert len(result["extracted_jobs"]) == 1
```

- [ ] **Step 2: Run to verify 4 tests fail**

```bash
.venv\Scripts\python -m pytest tests/test_pipeline.py::test_extract_node_emits_node_start_event tests/test_pipeline.py::test_extract_node_emits_job_progress_per_job tests/test_pipeline.py::test_progress_event_has_required_fields tests/test_pipeline.py::test_extract_node_works_without_queue -v
```

Expected: 4 FAIL (queue events not emitted yet).

- [ ] **Step 3: Update `extract_node` to emit queue events**

Replace `src/job_matcher/nodes/extract.py` with this complete file:

```python
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
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Tuple

from bs4 import BeautifulSoup
from langchain_openai import ChatOpenAI

from ..models import Job, ExtractedJob, MatcherState
from ..mongo import mongo_db
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

# DeepSeek pricing (matches token_tracker.py constants)
_PRICE_PROMPT = 0.14 / 1_000_000
_PRICE_COMPLETION = 1.10 / 1_000_000


def _clean_text(html_or_text: str) -> str:
    if not html_or_text:
        return ""
    try:
        soup = BeautifulSoup(html_or_text, "html.parser")
        text = soup.get_text(separator=" ")
    except Exception:
        text = re.sub(r'<[^>]+>', ' ', html_or_text)
    return " ".join(text.split())


def _make_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        temperature=0,
    )


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
```

- [ ] **Step 4: Run the 4 new tests**

```bash
.venv\Scripts\python -m pytest tests/test_pipeline.py::test_extract_node_emits_node_start_event tests/test_pipeline.py::test_extract_node_emits_job_progress_per_job tests/test_pipeline.py::test_progress_event_has_required_fields tests/test_pipeline.py::test_extract_node_works_without_queue -v
```

Expected: 4 PASS.

- [ ] **Step 5: Run full test suite**

```bash
.venv\Scripts\python -m pytest tests/ -v --tb=short
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/job_matcher/nodes/extract.py tests/test_pipeline.py
git commit -m "feat(extract): emit per-job progress events via SimpleQueue side channel"
```

---

### Task 3: Restructure `_stream_pipeline` to drain queue asynchronously

**Files:**
- Modify: `backend/routers/jobs.py`

**Interfaces:**
- Consumes: `queue.SimpleQueue` events from Task 2 (`_type`: `node_start`, `job_progress`, and `node_done` signal from pipeline thread)
- Produces: SSE events — existing format preserved + new `{"type": "job_progress", ...}` events

- [ ] **Step 1: No new tests needed for this task** (integration tested via E2E in Task 6; the restructure is observable behavior, not unit-testable without spinning up FastAPI)

- [ ] **Step 2: Rewrite `backend/routers/jobs.py`**

Full replacement:

```python
import asyncio
import json
import os
import queue as q_module
import uuid
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from job_matcher.mongo import mongo_db
from job_matcher.pipeline import build_pipeline
from job_matcher.profile import load_profile

router = APIRouter()


class RunRequest(BaseModel):
    profile_path: str = Field(default="profile.json", max_length=500)


def _safe_profile_path(raw: str) -> Path:
    requested = Path(raw).resolve()
    base = Path(".").resolve()
    if not str(requested).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Invalid profile path")
    if not requested.exists():
        raise HTTPException(status_code=404, detail="Profile not found")
    return requested


async def _stream_pipeline(profile_path: str) -> AsyncGenerator[str, None]:
    path = _safe_profile_path(profile_path)
    profile = load_profile(str(path))
    pipeline = build_pipeline()
    run_id = f"run_{uuid.uuid4().hex[:8]}"

    progress_q: q_module.SimpleQueue = q_module.SimpleQueue()
    pipeline_states: dict = {}
    error_holder: list[str] = []

    initial_state = {
        "profile": profile,
        "raw_jobs": [],
        "filtered_jobs": [],
        "extracted_jobs": [],
        "scored_jobs": [],
        "top_jobs": [],
        "output_format": "json",
        "token_stats": {},
        "progress_queue": progress_q,
    }

    def _run_pipeline() -> None:
        try:
            for event in pipeline.stream(initial_state):
                node_name = next(iter(event))
                state = event[node_name]
                pipeline_states[node_name] = state
                progress_q.put({"_type": "node_done", "_node": node_name})
        except Exception as exc:
            error_holder.append(str(exc))
        finally:
            progress_q.put({"_type": "__sentinel__"})

    loop = asyncio.get_event_loop()
    pipeline_task = loop.run_in_executor(None, _run_pipeline)

    try:
        while True:
            # Drain queue without blocking the event loop
            msg = await loop.run_in_executor(None, progress_q.get)

            if msg["_type"] == "job_progress":
                yield f"data: {json.dumps({'type': 'job_progress', 'index': msg['index'], 'total': msg['total'], 'title': msg['title'], 'skills': msg['skills'], 'tokens': msg['tokens'], 'cost': msg['cost'], 'cached': msg['cached']})}\n\n"

            elif msg["_type"] == "node_start":
                yield f"data: {json.dumps({'node': msg['_node'], 'total': msg.get('total', 0)})}\n\n"

            elif msg["_type"] == "node_done":
                node_name = msg["_node"]
                state = pipeline_states.get(node_name, {})
                token_stats = state.get("token_stats") or {}

                # Emit done_node event (existing format)
                if node_name == "rank":
                    top = state.get("top_jobs", [])
                    jobs_payload = [
                        {
                            "score": round(j.score, 1),
                            "score_breakdown": {
                                "stack": round(j.breakdown.stack, 1),
                                "seniority": round(j.breakdown.seniority, 1),
                                "ai_bonus": round(j.breakdown.ai_bonus, 1),
                                "recency": round(j.breakdown.recency, 1),
                            } if j.breakdown else None,
                            "title": j.job.title,
                            "company": j.job.company,
                            "posted_at": str(j.job.posted_at) if j.job.posted_at else None,
                            "apply_url": j.job.apply_url,
                            "skills": j.extracted.required_skills,
                            "seniority": j.extracted.seniority,
                            "description": j.job.description,
                        }
                        for j in top
                    ]

                    mongo_db.record_pipeline_run(
                        run_id=run_id,
                        profile_name=path.name,
                        jobs_fetched=len(state.get("raw_jobs", [])),
                        jobs_filtered=len(state.get("filtered_jobs", [])),
                        jobs_extracted_new=token_stats.get("cache_misses", 0),
                        jobs_cached_hits=token_stats.get("cache_hits", 0),
                        token_stats=token_stats,
                    )

                    yield f"data: {json.dumps({'done_node': node_name, 'jobs': jobs_payload, 'token_stats': token_stats})}\n\n"
                else:
                    yield f"data: {json.dumps({'done_node': node_name, 'token_stats': token_stats})}\n\n"

            elif msg["_type"] == "__sentinel__":
                if error_holder:
                    yield f"data: {json.dumps({'error': error_holder[0]})}\n\n"
                break

    finally:
        await pipeline_task


@router.post("/run")
async def run_matcher(req: RunRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_pipeline(req.profile_path),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/profile")
def get_profile(profile_path: str = "profile.json") -> dict:
    path = _safe_profile_path(profile_path)
    profile = load_profile(str(path))
    return {
        "preferred_keywords": profile.preferred_keywords,
        "reject_keywords": profile.reject_keywords,
        "target_seniority": profile.target_seniority,
    }
```

- [ ] **Step 3: Run backend tests to verify no regressions**

```bash
.venv\Scripts\python -m pytest tests/ -v --tb=short
```

Expected: all tests PASS (backend restructure is not unit-tested — covered by E2E).

- [ ] **Step 4: Commit**

```bash
git add backend/routers/jobs.py
git commit -m "feat(jobs): run pipeline in executor thread, drain progress queue via SSE"
```

---

### Task 4: Add `pipeline.ts` types and `PipelineProgress` component

**Files:**
- Create: `web/src/types/pipeline.ts`
- Create: `web/src/components/PipelineProgress.tsx`

**Interfaces:**
- Produces: `PipelineRun` type and `<PipelineProgress run={...} />` component — consumed by Task 5 (`page.tsx`)

- [ ] **Step 1: Write the failing E2E test for progress card visibility** (will be expanded in Task 6; write one test now to drive the component)

Add to `web/tests/e2e/home.spec.ts` (find the last test and add after it):

```typescript
test('pipeline shows progress card when node_start received', async ({ page }) => {
  await page.route('/api/run', async (route) => {
    const body = [
      'data: {"node":"fetch","total":0}\n\n',
      'data: {"done_node":"fetch","token_stats":{}}\n\n',
    ].join('')
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body,
    })
  })

  await page.click('button:has-text("Find matching jobs")')
  await expect(page.locator('[data-testid="pipeline-progress"]')).toBeVisible()
})
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd web
npx playwright test tests/e2e/home.spec.ts --grep "progress card" -x
```

Expected: FAIL — `pipeline-progress` not found.

- [ ] **Step 3: Create `web/src/types/pipeline.ts`**

Node IDs must match LangGraph node names from `pipeline.py`: `'fetch'`, `'filter'`, `'extract'`, `'score'`, `'rank'`.

```typescript
export type NodeStatus = 'pending' | 'running' | 'done' | 'error'

export interface PipelineNode {
  id: string
  label: string
  status: NodeStatus
  summary: string | null
}

export interface ExtractProgress {
  done: number
  total: number
}

export interface PipelineRun {
  nodes: PipelineNode[]
  currentJobTitle: string | null
  currentJobSkills: string[]
  extractProgress: ExtractProgress
  totalTokens: number
  totalCost: number
}

export function makePipelineRun(): PipelineRun {
  return {
    nodes: [
      { id: 'fetch',   label: 'Fetch',   status: 'pending', summary: null },
      { id: 'filter',  label: 'Filter',  status: 'pending', summary: null },
      { id: 'extract', label: 'Extract', status: 'pending', summary: null },
      { id: 'score',   label: 'Score',   status: 'pending', summary: null },
      { id: 'rank',    label: 'Rank',    status: 'pending', summary: null },
    ],
    currentJobTitle: null,
    currentJobSkills: [],
    extractProgress: { done: 0, total: 0 },
    totalTokens: 0,
    totalCost: 0,
  }
}
```

- [ ] **Step 4: Create `web/src/components/PipelineProgress.tsx`**

```tsx
import type { PipelineRun } from '@/types/pipeline'

interface Props {
  run: PipelineRun
}

function NodeIcon({ status }: { status: string }) {
  if (status === 'done') {
    return (
      <span className="w-6 h-6 rounded-full bg-green-500 flex items-center justify-center text-white text-xs font-bold shrink-0">
        ✓
      </span>
    )
  }
  if (status === 'running') {
    return (
      <span className="w-6 h-6 rounded-full bg-indigo-500 flex items-center justify-center shrink-0 animate-pulse">
        <span className="w-2 h-2 rounded-full bg-white" />
      </span>
    )
  }
  return (
    <span className="w-6 h-6 rounded-full bg-gray-800 border border-gray-700 flex items-center justify-center shrink-0" />
  )
}

export function PipelineProgress({ run }: Props) {
  const { nodes, currentJobTitle, currentJobSkills, extractProgress, totalTokens, totalCost } = run
  const extractNode = nodes.find((n) => n.id === 'extract')
  const showBar = extractNode?.status === 'running' && extractProgress.total > 0
  const barPct = showBar
    ? Math.round((extractProgress.done / extractProgress.total) * 100)
    : 0

  return (
    <div
      data-testid="pipeline-progress"
      className="w-full max-w-lg mx-auto bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-4"
    >
      <p className="text-sm font-semibold text-gray-300 tracking-wide">Pipeline en progreso</p>

      <div className="space-y-3">
        {nodes.map((node) => (
          <div key={node.id}>
            <div className="flex items-center gap-3">
              <NodeIcon status={node.status} />
              <span
                className={`text-sm font-medium ${
                  node.status === 'done'
                    ? 'text-green-400'
                    : node.status === 'running'
                    ? 'text-indigo-300'
                    : 'text-gray-600'
                }`}
              >
                {node.label}
              </span>
              {node.summary && (
                <span className="text-xs text-gray-500 ml-auto truncate max-w-[200px]">
                  {node.summary}
                </span>
              )}
              {node.id === 'extract' && node.status === 'running' && extractProgress.total > 0 && (
                <span className="text-xs text-gray-500 ml-auto">
                  {extractProgress.done}/{extractProgress.total}
                </span>
              )}
            </div>

            {/* Progress bar — only for extract_node while running */}
            {node.id === 'extract' && showBar && (
              <div className="ml-9 mt-2 space-y-1">
                <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 rounded-full transition-all duration-300"
                    style={{ width: `${barPct}%` }}
                  />
                </div>
                {currentJobTitle && (
                  <p className="text-xs text-gray-500 truncate">{currentJobTitle}</p>
                )}
                {currentJobSkills.length > 0 && (
                  <p className="text-xs text-gray-600 truncate">
                    {currentJobSkills.slice(0, 4).join(' · ')}
                  </p>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Token metrics bar */}
      <div className="border-t border-gray-800 pt-3 flex gap-5 text-xs text-gray-500">
        <span>
          Tokens: <span className="text-gray-300 font-medium">{totalTokens.toLocaleString()}</span>
        </span>
        <span>
          Costo: <span className="text-green-400 font-medium">${totalCost.toFixed(5)}</span>
        </span>
        {extractProgress.total > 0 && (
          <span>
            Jobs:{' '}
            <span className="text-indigo-300 font-medium">
              {extractProgress.done}/{extractProgress.total}
            </span>
          </span>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Run the E2E test**

```bash
cd web
npx playwright test tests/e2e/home.spec.ts --grep "progress card" -x
```

Expected: PASS — `pipeline-progress` visible after `node_start` event.

- [ ] **Step 6: TypeScript check**

```bash
cd web
npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add web/src/types/pipeline.ts web/src/components/PipelineProgress.tsx web/tests/e2e/home.spec.ts
git commit -m "feat(frontend): add PipelineProgress component and pipeline types"
```

---

### Task 5: Wire `PipelineProgress` into `page.tsx`

**Files:**
- Modify: `web/src/app/page.tsx`

**Interfaces:**
- Consumes: `PipelineRun`, `makePipelineRun()` from `@/types/pipeline`; `PipelineProgress` from `@/components/PipelineProgress`
- Produces: updated `page.tsx` that handles `job_progress` SSE events and shows `PipelineProgress` instead of the old spinner

- [ ] **Step 1: Rewrite `web/src/app/page.tsx`**

Full replacement:

```tsx
'use client'

import { useState } from 'react'
import { JobCard } from '@/components/JobCard'
import { JobModal } from '@/components/JobModal'
import { PipelineProgress } from '@/components/PipelineProgress'
import { ScoreFilter } from '@/components/ScoreFilter'
import type { Job } from '@/types/job'
import { type PipelineRun, makePipelineRun } from '@/types/pipeline'

const JOBS_PER_PAGE = 8

interface TokenStats {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cache_hits: number
  cache_misses: number
  saved_tokens: number
  estimated_cost_usd: number
  estimated_saved_cost_usd: number
}

type Status = 'idle' | 'running' | 'done' | 'error'
type FilterValue = 'all' | 70 | 40

function updateNodeStatus(
  run: PipelineRun,
  nodeId: string,
  status: 'running' | 'done',
  summary: string | null,
): PipelineRun {
  return {
    ...run,
    nodes: run.nodes.map((n) =>
      n.id === nodeId ? { ...n, status, summary } : n
    ),
  }
}

export default function Home() {
  const [status, setStatus] = useState<Status>('idle')
  const [jobs, setJobs] = useState<Job[]>([])
  const [error, setError] = useState<string | null>(null)
  const [tokenStats, setTokenStats] = useState<TokenStats | null>(null)
  const [selectedJob, setSelectedJob] = useState<Job | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [scoreFilter, setScoreFilter] = useState<FilterValue>('all')
  const [pipelineRun, setPipelineRun] = useState<PipelineRun | null>(null)

  const filteredJobs = scoreFilter === 'all' ? jobs : jobs.filter((j) => j.score >= scoreFilter)
  const totalPages = Math.max(1, Math.ceil(filteredJobs.length / JOBS_PER_PAGE))
  const visibleJobs = filteredJobs.slice(
    (currentPage - 1) * JOBS_PER_PAGE,
    currentPage * JOBS_PER_PAGE
  )

  function handleFilterChange(v: FilterValue) {
    setScoreFilter(v)
    setCurrentPage(1)
  }

  async function runMatcher() {
    setStatus('running')
    setJobs([])
    setError(null)
    setTokenStats(null)
    setCurrentPage(1)
    setScoreFilter('all')
    setPipelineRun(makePipelineRun())

    try {
      const resp = await fetch('/api/run', { method: 'POST' })
      if (!resp.ok || !resp.body) throw new Error('Backend unreachable')

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = JSON.parse(line.slice(6))

          if (data.error) {
            setError(data.error)
            setStatus('error')
            setPipelineRun(null)
            return
          }

          // node_start — emitted by extract_node via queue, or any node when it begins
          if (data.node) {
            setPipelineRun((prev) =>
              prev ? updateNodeStatus(prev, data.node, 'running', null) : prev
            )
            if (data.node === 'extract' && data.total) {
              setPipelineRun((prev) =>
                prev
                  ? { ...prev, extractProgress: { done: 0, total: data.total } }
                  : prev
              )
            }
          }

          // node_done
          if (data.done_node) {
            setPipelineRun((prev) =>
              prev ? updateNodeStatus(prev, data.done_node, 'done', null) : prev
            )
            if (data.token_stats && Object.keys(data.token_stats).length > 0) {
              setTokenStats(data.token_stats)
            }
          }

          // per-job progress from extract_node
          if (data.type === 'job_progress') {
            setPipelineRun((prev) => {
              if (!prev) return prev
              return {
                ...prev,
                currentJobTitle: data.title as string,
                currentJobSkills: (data.skills as string[]) ?? [],
                extractProgress: { done: data.index as number, total: data.total as number },
                totalTokens: prev.totalTokens + (data.tokens as number),
                totalCost: prev.totalCost + (data.cost as number),
              }
            })
          }

          // final results
          if (data.jobs) {
            setJobs(data.jobs as Job[])
            setStatus('done')
            setPipelineRun(null)
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
      setStatus('error')
      setPipelineRun(null)
    }
  }

  return (
    <main className="max-w-5xl mx-auto px-4 py-12">
      <div className="mb-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white">Job Matcher</h1>
          <p className="text-gray-400 mt-1">
            LangGraph + DeepSeek · MongoDB Storage & Cache · Top matches ranked for your profile
          </p>
        </div>
        {tokenStats && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-3 text-xs text-gray-300 flex flex-wrap gap-4">
            <div>
              <span className="text-gray-500 block">LLM Cost</span>
              <span className="font-semibold text-green-400">${tokenStats.estimated_cost_usd.toFixed(5)}</span>
            </div>
            <div>
              <span className="text-gray-500 block">Tokens Used</span>
              <span className="font-semibold text-white">{tokenStats.total_tokens.toLocaleString()}</span>
            </div>
            <div>
              <span className="text-gray-500 block">Mongo Cache Hits</span>
              <span className="font-semibold text-indigo-400">{tokenStats.cache_hits} jobs</span>
            </div>
            <div>
              <span className="text-gray-500 block">Saved Tokens</span>
              <span className="font-semibold text-purple-400">{tokenStats.saved_tokens.toLocaleString()}</span>
            </div>
          </div>
        )}
      </div>

      <div className="flex flex-col items-center gap-6 mb-10">
        <button
          onClick={runMatcher}
          disabled={status === 'running'}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold px-8 py-3 rounded-xl text-lg transition-colors"
        >
          {status === 'running' ? 'Running pipeline...' : 'Find matching jobs'}
        </button>

        {pipelineRun && <PipelineProgress run={pipelineRun} />}
        {status === 'error' && <p className="text-red-400 text-sm">Error: {error}</p>}
      </div>

      {jobs.length > 0 && (
        <div>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
            <h2 className="text-lg font-semibold text-gray-300">
              {filteredJobs.length} of {jobs.length} matches
            </h2>
            <ScoreFilter value={scoreFilter} onChange={handleFilterChange} />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {visibleJobs.map((job, i) => (
              <JobCard
                key={job.apply_url}
                job={job}
                rank={(currentPage - 1) * JOBS_PER_PAGE + i + 1}
                onSelect={setSelectedJob}
              />
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-4 mt-6">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="px-4 py-2 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed text-sm transition-colors"
              >
                Previous
              </button>
              <span className="text-gray-400 text-sm">Page {currentPage} of {totalPages}</span>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="px-4 py-2 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed text-sm transition-colors"
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}

      <JobModal job={selectedJob} onClose={() => setSelectedJob(null)} />
    </main>
  )
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd web
npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/app/page.tsx
git commit -m "feat(page): replace PipelineStatus spinner with PipelineProgress card"
```

---

### Task 6: Playwright E2E tests for progress streaming

**Files:**
- Modify: `web/tests/e2e/home.spec.ts` (add 3 more tests; 1 already added in Task 4)

**Interfaces:**
- Consumes: `PipelineProgress` component (`data-testid="pipeline-progress"`) from Task 4; SSE mock events

- [ ] **Step 1: Add 3 remaining E2E tests to `web/tests/e2e/home.spec.ts`**

Append after the test added in Task 4:

```typescript
test('extract progress bar advances on job_progress events', async ({ page }) => {
  const events = [
    'data: {"node":"extract","total":10}\n\n',
    'data: {"type":"job_progress","index":1,"total":10,"title":"Senior Dev @ Acme","skills":["Python","FastAPI"],"tokens":300,"cost":0.0003,"cached":false}\n\n',
    'data: {"type":"job_progress","index":2,"total":10,"title":"Mid Dev @ Beta","skills":["Go"],"tokens":280,"cost":0.00028,"cached":false}\n\n',
    'data: {"type":"job_progress","index":3,"total":10,"title":"Junior Dev @ Gamma","skills":["Java"],"tokens":270,"cost":0.00027,"cached":false}\n\n',
  ].join('')

  await page.route('/api/run', async (route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body: events,
    })
  })

  await page.click('button:has-text("Find matching jobs")')
  await expect(page.locator('[data-testid="pipeline-progress"]')).toBeVisible()
  await expect(page.locator('text=3/10')).toBeVisible()
  await expect(page.locator('text=Senior Dev @ Acme')).toBeVisible()
})

test('token counter updates on job_progress events', async ({ page }) => {
  const events = [
    'data: {"node":"extract","total":5}\n\n',
    'data: {"type":"job_progress","index":1,"total":5,"title":"Dev A","skills":[],"tokens":200,"cost":0.0002,"cached":false}\n\n',
    'data: {"type":"job_progress","index":2,"total":5,"title":"Dev B","skills":[],"tokens":200,"cost":0.0002,"cached":false}\n\n',
  ].join('')

  await page.route('/api/run', async (route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body: events,
    })
  })

  await page.click('button:has-text("Find matching jobs")')
  await expect(page.locator('[data-testid="pipeline-progress"]')).toBeVisible()
  // 200 + 200 = 400 tokens
  await expect(page.locator('text=400')).toBeVisible()
})

test('progress card disappears and job cards appear on done', async ({ page }) => {
  const mockJob = {
    score: 82.5,
    score_breakdown: { stack: 40, seniority: 15, ai_bonus: 20, recency: 7.5 },
    title: 'Senior Engineer',
    company: 'TechCorp',
    posted_at: '2026-08-10',
    apply_url: 'https://techcorp.com/jobs/1',
    skills: ['Python', 'FastAPI'],
    seniority: 'senior',
    description: 'A great role.',
  }

  const events = [
    'data: {"node":"rank","total":0}\n\n',
    `data: {"done_node":"rank","jobs":[${JSON.stringify(mockJob)}],"token_stats":{"total_tokens":1200,"cache_hits":2,"cache_misses":3,"estimated_cost_usd":0.00145,"prompt_tokens":900,"completion_tokens":300,"saved_tokens":1100,"estimated_saved_cost_usd":0.00040}}\n\n`,
  ].join('')

  await page.route('/api/run', async (route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body: events,
    })
  })

  await page.click('button:has-text("Find matching jobs")')
  await expect(page.locator('[data-testid="pipeline-progress"]')).not.toBeVisible()
  await expect(page.locator('text=Senior Engineer')).toBeVisible()
})
```

- [ ] **Step 2: Run all E2E tests**

```bash
cd web
npx playwright test tests/e2e/home.spec.ts -v
```

Expected: all tests PASS (including the 4 new ones + all existing ones).

- [ ] **Step 3: Full TypeScript check**

```bash
cd web
npx tsc --noEmit
```

Expected: 0 errors.

- [ ] **Step 4: Run all backend tests one final time**

```bash
cd C:\Users\lanitaEmperadora\Documents\github\job-matcher
.venv\Scripts\python -m pytest tests/ -v --tb=short
```

Expected: all tests PASS.

- [ ] **Step 5: Final commit**

```bash
git add web/tests/e2e/home.spec.ts
git commit -m "test(e2e): add pipeline streaming Playwright tests"
```
