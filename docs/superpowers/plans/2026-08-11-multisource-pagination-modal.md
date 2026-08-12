# Multi-Source Aggregation + Pagination + Job Detail Modal — Implementation Plan

> **For agentic workers:** Use `parallel-executor` to implement this plan. Wave 1 (Tasks 1 + 2) fires in parallel. Tasks 3, 4, 5 are sequential. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add RemoteOK as a second job source (parallel fetch + deduplication), expose score breakdown in the SSE payload, and add client-side pagination with score filter and a slide-over job detail modal to the Next.js frontend.

**Architecture:** Backend: `fetch_node` uses `ThreadPoolExecutor(max_workers=2)` to fetch Remotive + RemoteOK simultaneously, merges and deduplicates by `apply_url`, then `score_node` returns `(float, ScoreBreakdown)` tuples stored on `ScoredJob`. Frontend: 3 new/modified components (`JobModal`, `ScoreFilter`, updated `JobCard`) and state additions to `page.tsx`; all filtering and pagination is client-side over the `jobs[]` array received via SSE.

**Tech Stack:** Python 3.12, FastAPI, LangGraph, pymongo, requests, pytest — Next.js 15, React 19, TypeScript strict, Tailwind CSS v4, Playwright.

## Global Constraints

- Venv: `.venv\Scripts\python.exe` (Python 3.12)
- Working dir: `C:\Users\lanitaEmperadora\Documents\github\job-matcher`
- All Python tests run offline (no real network, no real LLM calls)
- `DEEPSEEK_API_KEY` only from `os.environ`, never hardcoded
- TypeScript strict mode, no `any` unless unavoidable
- `JOBS_PER_PAGE = 8` (client-side constant)
- RemoteOK fetch is non-fatal: HTTP errors return `[]`, pipeline continues with Remotive only

---

## Pre-step: Open feature branch

```bash
cd /c/Users/lanitaEmperadora/Documents/github/job-matcher
git checkout -b feat/multisource-pagination-modal
```

Expected: `Switched to a new branch 'feat/multisource-pagination-modal'`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/job_matcher/models.py` | Modify | Add `ScoreBreakdown`; add `breakdown` field to `ScoredJob` |
| `src/job_matcher/nodes/score.py` | Modify | `score_job` returns `tuple[float, ScoreBreakdown]`; `score_node` unpacks |
| `tests/test_score.py` | Modify | Update 8 tests to unpack tuple; add breakdown-sum test |
| `src/job_matcher/fetcher.py` | Modify | Add `fetch_remoteok()` + `_normalize_remoteok()` |
| `src/job_matcher/nodes/fetch.py` | Modify | Parallel fetch with `ThreadPoolExecutor`; dedup by `apply_url` |
| `tests/test_pipeline.py` | Modify | Fix 3 broken tests; add 3 new tests for remoteok/parallel/dedup |
| `backend/routers/jobs.py` | Modify | Add `description` + `score_breakdown` to SSE rank payload |
| `web/src/types/job.ts` | Create | Shared `Job` + `ScoreBreakdown` TypeScript interfaces |
| `web/src/components/JobModal.tsx` | Create | Slide-over drawer: breakdown bars + description + Apply |
| `web/src/components/ScoreFilter.tsx` | Create | Toggle buttons: All / ≥70 / ≥40 |
| `web/src/components/JobCard.tsx` | Modify | Add `onSelect` prop; `e.stopPropagation()` on Apply link |
| `web/src/app/page.tsx` | Modify | Add `selectedJob`, `currentPage`, `scoreFilter` state; render new components |
| `web/tests/e2e/home.spec.ts` | Modify | Add 4 new specs: modal open/close, score filter, pagination |

---

## Task 1: ScoreBreakdown model + score_node refactor

**Wave: 1 (parallel with Task 2)**

**Files:**
- Modify: `src/job_matcher/models.py`
- Modify: `src/job_matcher/nodes/score.py`
- Modify: `tests/test_score.py`

**Interfaces:**
- Produces:
  - `ScoreBreakdown(stack: float, seniority: float, ai_bonus: float, recency: float)` — Pydantic BaseModel
  - `ScoredJob.breakdown: ScoreBreakdown` — new required field
  - `score_job(extracted, profile, today) -> tuple[float, ScoreBreakdown]` — signature change

---

- [ ] **Step 1: Write the new test for score breakdown sum**

Add at the end of `tests/test_score.py`:

```python
def test_score_breakdown_components_sum_to_total():
    e = _job(title="Mid-level Python Developer", description="LangGraph RAG", posted_at=TODAY)
    score, breakdown = score_job(e, PROFILE, TODAY)
    raw_sum = breakdown.stack + breakdown.seniority + breakdown.ai_bonus + breakdown.recency
    assert score == max(-20.0, min(100.0, raw_sum))
```

- [ ] **Step 2: Run new test to verify it fails**

```bash
.venv\Scripts\python.exe -m pytest tests/test_score.py::test_score_breakdown_components_sum_to_total -v
```

Expected: `FAILED` — `score_job` returns a float, cannot unpack.

- [ ] **Step 3: Update `src/job_matcher/models.py`**

Replace the full file content:

```python
from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class Job(BaseModel):
    id: str
    title: str
    company: str
    location: str | None = None
    remote: bool = False
    description: str = ""
    apply_url: str
    source: str = ""
    posted_at: date | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExtractedJob(BaseModel):
    job: Job
    required_skills: list[str] = Field(default_factory=list)
    seniority: str | None = None
    is_remote: bool = False
    latam_eligible: bool = False


class ScoreBreakdown(BaseModel):
    stack: float
    seniority: float
    ai_bonus: float
    recency: float


class ScoredJob(BaseModel):
    job: Job
    extracted: ExtractedJob
    score: float
    breakdown: ScoreBreakdown
    discard_reason: str | None = None


class ProfileData(BaseModel):
    preferred_keywords: list[str]
    reject_keywords: list[str]
    target_seniority: list[str]
    avoid_seniority: list[str]


class MatcherState(TypedDict):
    profile: ProfileData
    raw_jobs: list[dict[str, Any]]
    filtered_jobs: list[Job]
    extracted_jobs: list[ExtractedJob]
    scored_jobs: list[ScoredJob]
    top_jobs: list[ScoredJob]
    output_format: Literal["table", "json"]
    token_stats: dict[str, Any]
```

- [ ] **Step 4: Update `src/job_matcher/nodes/score.py`**

Replace the full file content:

```python
from datetime import date
from ..models import ExtractedJob, ScoredJob, ScoreBreakdown, ProfileData, MatcherState

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


def score_job(
    extracted: ExtractedJob, profile: ProfileData, today: date
) -> tuple[float, ScoreBreakdown]:
    stack = _stack_score(extracted, profile.preferred_keywords)
    seniority = _seniority_score(extracted)
    ai_bonus = _ai_bonus(extracted)
    recency = _recency_score(extracted, today)
    total = max(-20.0, min(100.0, stack + seniority + ai_bonus + recency))
    return total, ScoreBreakdown(stack=stack, seniority=seniority, ai_bonus=ai_bonus, recency=recency)


def score_node(state: MatcherState) -> dict:
    profile = state["profile"]
    today = date.today()
    scored = []
    for e in state["extracted_jobs"]:
        total, breakdown = score_job(e, profile, today)
        scored.append(ScoredJob(job=e.job, extracted=e, score=total, breakdown=breakdown))
    return {
        "scored_jobs": scored,
        "token_stats": state.get("token_stats", {}),
    }
```

- [ ] **Step 5: Update all 8 existing tests in `tests/test_score.py` to unpack tuple**

Replace the full file content:

```python
from datetime import date
from job_matcher.models import Job, ExtractedJob, ProfileData
from job_matcher.nodes.score import score_job

PROFILE = ProfileData(
    preferred_keywords=["Node.js", "Python", "TypeScript", "AWS", "Django", "LangGraph", "RAG"],
    reject_keywords=[],
    target_seniority=["mid-level", "semi-senior"],
    avoid_seniority=["junior"],
)
TODAY = date(2026, 8, 11)


def _job(job_id="j1", title="Dev", description="", posted_at=TODAY):
    j = Job(id=job_id, title=title, company="Co", apply_url="https://x.com",
            description=description, posted_at=posted_at, remote=True)
    return ExtractedJob(job=j, required_skills=[], seniority=None,
                        is_remote=True, latam_eligible=True)


def test_stack_overlap_title_weighs_more():
    e_title = _job(title="Node.js TypeScript Developer", description="some work")
    e_body = _job(title="Developer", description="Node.js TypeScript experience preferred")
    s1, _ = score_job(e_title, PROFILE, TODAY)
    s2, _ = score_job(e_body, PROFILE, TODAY)
    assert s1 > s2


def test_seniority_mid_level_max_bonus():
    e = _job(title="Mid-level Backend Developer")
    e2 = _job(title="Senior Backend Developer")
    s, _ = score_job(e, PROFILE, TODAY)
    s2, _ = score_job(e2, PROFILE, TODAY)
    assert s > s2


def test_seniority_junior_penalizes():
    e = _job(title="Junior Python Developer", description="Python Django")
    e2 = _job(title="Mid-level Python Developer", description="Python Django")
    s, _ = score_job(e, PROFILE, TODAY)
    s2, _ = score_job(e2, PROFILE, TODAY)
    assert s < s2


def test_ai_bonus_tier_a_langgraph():
    e = _job(description="Building multi-agent systems with LangGraph and RAG pipelines.")
    e2 = _job(description="Standard backend work.")
    s, _ = score_job(e, PROFILE, TODAY)
    s2, _ = score_job(e2, PROFILE, TODAY)
    assert s > s2 + 15


def test_ai_bonus_tier_b_openai():
    e = _job(description="Integration with OpenAI API and machine learning models.")
    e2 = _job(description="Standard backend work.")
    s, _ = score_job(e, PROFILE, TODAY)
    s2, _ = score_job(e2, PROFILE, TODAY)
    assert s > s2


def test_recency_today_max():
    from datetime import date
    e_today = _job(posted_at=TODAY)
    e_old = _job(posted_at=date(2026, 7, 20))
    s1, _ = score_job(e_today, PROFILE, TODAY)
    s2, _ = score_job(e_old, PROFILE, TODAY)
    assert s1 > s2


def test_score_capped_at_100():
    e = _job(
        title="Mid-level Node.js TypeScript Python AWS Django Developer",
        description="LangGraph RAG multi-agent systems. LatAm eligible.",
        posted_at=TODAY
    )
    score, _ = score_job(e, PROFILE, TODAY)
    assert score <= 100


def test_score_floor_at_minus_20():
    e = _job(title="Junior intern trainee entry level")
    score, _ = score_job(e, PROFILE, TODAY)
    assert score >= -20


def test_score_breakdown_components_sum_to_total():
    e = _job(title="Mid-level Python Developer", description="LangGraph RAG", posted_at=TODAY)
    score, breakdown = score_job(e, PROFILE, TODAY)
    raw_sum = breakdown.stack + breakdown.seniority + breakdown.ai_bonus + breakdown.recency
    assert score == max(-20.0, min(100.0, raw_sum))
```

- [ ] **Step 6: Run tests to verify all pass**

```bash
.venv\Scripts\python.exe -m pytest tests/test_score.py -v
```

Expected: `9 passed`

- [ ] **Step 7: Commit**

```bash
git add src/job_matcher/models.py src/job_matcher/nodes/score.py tests/test_score.py
git commit -m "feat: add ScoreBreakdown model and refactor score_job to return tuple"
```

---

## Task 2: RemoteOK fetcher + parallel fetch_node

**Wave: 1 (parallel with Task 1)**

**Files:**
- Modify: `src/job_matcher/fetcher.py`
- Modify: `src/job_matcher/nodes/fetch.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Produces:
  - `fetch_remoteok() -> list[dict]` — public function in `fetcher.py`
  - `_normalize_remoteok(raw: dict) -> dict` — private normalizer
  - Updated `fetch_node` pulls from both sources in parallel

**Note:** The current `tests/test_pipeline.py` imports `_normalize` (which does not exist — function is `_normalize_remotive`) and patches `requests.post` (actual code uses `requests.get`). These 3 broken tests are replaced in this task.

---

- [ ] **Step 1: Write failing tests for `fetch_remoteok` and parallel behavior**

Replace the full content of `tests/test_pipeline.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from job_matcher.fetcher import fetch_remoteok, _normalize_remoteok, load_cache, save_cache
from job_matcher.models import ProfileData

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sample_jobs.json").read_text()
)

REMOTEOK_SAMPLE = [
    {"legal": "RemoteOK.com"},  # first element is always metadata — must be skipped
    {
        "id": 12345,
        "position": "Backend Engineer",
        "company": "Acme Co",
        "url": "https://remoteok.com/jobs/12345",
        "description": "<p>Python FastAPI role.</p>",
        "tags": ["Python", "FastAPI", "Docker"],
        "date": "2026-08-11T00:00:00Z",
    },
    {
        "id": 12346,
        "position": "Frontend Developer",
        "company": "Beta Inc",
        "url": "https://remoteok.com/jobs/12346",
        "description": "<p>React TypeScript role.</p>",
        "tags": ["React", "TypeScript"],
        "date": "2026-08-10T00:00:00Z",
    },
]


# ── _normalize_remoteok ─────────────────────────────────────────────────────

def test_normalize_remoteok_maps_fields():
    raw = REMOTEOK_SAMPLE[1]
    result = _normalize_remoteok(raw)
    assert result["title"] == "Backend Engineer"
    assert result["company"] == "Acme Co"
    assert result["apply_url"] == "https://remoteok.com/jobs/12345"
    assert result["remote"] is True
    assert result["source"] == "remoteok"
    assert result["posted_at"] == "2026-08-11"


def test_normalize_remoteok_id_prefixed():
    raw = REMOTEOK_SAMPLE[1]
    result = _normalize_remoteok(raw)
    assert result["id"].startswith("rok_")


def test_normalize_remoteok_tags_in_description():
    raw = REMOTEOK_SAMPLE[1]
    result = _normalize_remoteok(raw)
    assert "Python" in result["description"]
    assert "FastAPI" in result["description"]


# ── fetch_remoteok ──────────────────────────────────────────────────────────

def test_fetch_remoteok_skips_metadata_element():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = REMOTEOK_SAMPLE
    mock_resp.raise_for_status = MagicMock()

    with patch("job_matcher.fetcher.requests.get", return_value=mock_resp):
        jobs = fetch_remoteok()

    assert len(jobs) == 2  # metadata dict skipped
    assert all(j["source"] == "remoteok" for j in jobs)


def test_fetch_remoteok_returns_empty_on_http_error():
    with patch("job_matcher.fetcher.requests.get", side_effect=Exception("timeout")):
        jobs = fetch_remoteok()
    assert jobs == []


# ── parallel fetch_node ─────────────────────────────────────────────────────

def test_fetch_node_merges_both_sources(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HIRING_CAFE_URL", "https://hiring.cafe")

    remotive_jobs = [{"id": "r1", "apply_url": "https://remotive.com/r1", "title": "Dev A",
                      "company": "Co", "location": "Remote", "remote": True,
                      "description": "", "source": "remotive", "posted_at": None}]
    remoteok_jobs = [{"id": "rok_2", "apply_url": "https://remoteok.com/rok2", "title": "Dev B",
                      "company": "Co", "location": "Remote", "remote": True,
                      "description": "", "source": "remoteok", "posted_at": None}]

    with patch("job_matcher.nodes.fetch.fetch_jobs", return_value=remotive_jobs), \
         patch("job_matcher.nodes.fetch.fetch_remoteok", return_value=remoteok_jobs), \
         patch("job_matcher.nodes.fetch.mongo_db.save_raw_jobs"):
        from job_matcher.nodes.fetch import fetch_node
        result = fetch_node({"token_stats": {}})

    assert len(result["raw_jobs"]) == 2
    ids = {j["id"] for j in result["raw_jobs"]}
    assert "r1" in ids
    assert "rok_2" in ids


def test_fetch_node_deduplicates_by_apply_url(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HIRING_CAFE_URL", "https://hiring.cafe")

    same_url = "https://example.com/job/42"
    remotive_jobs = [{"id": "r1", "apply_url": same_url, "title": "Dev",
                      "company": "Co", "location": "Remote", "remote": True,
                      "description": "", "source": "remotive", "posted_at": None}]
    remoteok_jobs = [{"id": "rok_1", "apply_url": same_url, "title": "Dev",
                      "company": "Co", "location": "Remote", "remote": True,
                      "description": "", "source": "remoteok", "posted_at": None}]

    with patch("job_matcher.nodes.fetch.fetch_jobs", return_value=remotive_jobs), \
         patch("job_matcher.nodes.fetch.fetch_remoteok", return_value=remoteok_jobs), \
         patch("job_matcher.nodes.fetch.mongo_db.save_raw_jobs"):
        from job_matcher.nodes.fetch import fetch_node
        result = fetch_node({"token_stats": {}})

    assert len(result["raw_jobs"]) == 1  # deduped — only first occurrence kept


# ── cache ───────────────────────────────────────────────────────────────────

def test_cache_roundtrip(tmp_path):
    cache_file = str(tmp_path / "cache.json")
    ids = {"abc", "def", "ghi"}
    save_cache(ids, cache_file)
    loaded = load_cache(cache_file)
    assert loaded == ids


def test_cache_empty_when_no_file(tmp_path):
    result = load_cache(str(tmp_path / "nonexistent.json"))
    assert result == set()


# ── extract node ────────────────────────────────────────────────────────────

def test_extract_node_uses_llm_structured_output(monkeypatch):
    from job_matcher.models import Job
    from job_matcher.nodes.extract import extract_node

    mock_result = MagicMock()
    mock_result.required_skills = ["Python", "FastAPI"]
    mock_result.seniority = "mid"
    mock_result.is_remote = True
    mock_result.latam_eligible = True

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_result

    job = Job(id="x", title="Backend Dev", company="Co",
              description="Python FastAPI role. Remote LatAm.", apply_url="https://x.com")

    state = {
        "profile": ProfileData(
            preferred_keywords=["Python"],
            reject_keywords=[],
            target_seniority=["mid-level"],
            avoid_seniority=["junior"],
        ),
        "raw_jobs": [],
        "filtered_jobs": [job],
        "extracted_jobs": [],
        "scored_jobs": [],
        "top_jobs": [],
        "output_format": "table",
        "token_stats": {},
    }

    with patch("job_matcher.nodes.extract._make_llm", return_value=mock_llm):
        result = extract_node(state)

    assert len(result["extracted_jobs"]) == 1
    assert result["extracted_jobs"][0].seniority == "mid"
    assert "Python" in result["extracted_jobs"][0].required_skills


# ── full pipeline (offline) ─────────────────────────────────────────────────

def test_full_pipeline_offline(tmp_path, monkeypatch):
    from job_matcher.pipeline import build_pipeline

    monkeypatch.setenv("HIRING_CAFE_URL", "https://hiring.cafe")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.chdir(tmp_path)

    mock_result = MagicMock()
    mock_result.required_skills = ["Python"]
    mock_result.seniority = "mid"
    mock_result.is_remote = True
    mock_result.latam_eligible = True
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_result

    with patch("job_matcher.nodes.fetch.fetch_jobs", return_value=FIXTURES[:5]), \
         patch("job_matcher.nodes.fetch.fetch_remoteok", return_value=[]), \
         patch("job_matcher.nodes.fetch.mongo_db.save_raw_jobs"), \
         patch("job_matcher.nodes.extract._make_llm", return_value=mock_llm):
        pipeline = build_pipeline()
        result = pipeline.invoke({
            "profile": ProfileData(
                preferred_keywords=["Python", "Node.js"],
                reject_keywords=["US only", "internship", "Salesforce"],
                target_seniority=["mid-level"],
                avoid_seniority=["junior"],
            ),
            "raw_jobs": [],
            "filtered_jobs": [],
            "extracted_jobs": [],
            "scored_jobs": [],
            "top_jobs": [],
            "output_format": "json",
            "token_stats": {},
        })

    assert len(result["top_jobs"]) <= 5
    for sj in result["top_jobs"]:
        assert sj.score >= -20
        assert sj.breakdown is not None
```

- [ ] **Step 2: Run tests to verify new ones fail (import errors expected)**

```bash
.venv\Scripts\python.exe -m pytest tests/test_pipeline.py -v 2>&1 | head -40
```

Expected: `ImportError: cannot import name 'fetch_remoteok'` and `ImportError: cannot import name '_normalize_remoteok'`

- [ ] **Step 3: Add `fetch_remoteok` and `_normalize_remoteok` to `src/job_matcher/fetcher.py`**

Add after the existing `fetch_jobs` public function (before `load_cache`):

```python
# ── RemoteOK ──────────────────────────────────────────────────────────────────

_REMOTEOK_API = "https://remoteok.com/api"


def _normalize_remoteok(raw: dict) -> dict:
    url = raw.get("url", "") or raw.get("apply_url", "")
    tags: list[str] = raw.get("tags") or []
    body = raw.get("description", "")
    description = ("Skills: " + ", ".join(tags) + "\n\n" + body) if tags else body
    return {
        "id": "rok_" + str(raw.get("id", _job_id(url))),
        "title": raw.get("position", ""),
        "company": raw.get("company", ""),
        "location": "Remote",
        "remote": True,
        "description": description,
        "apply_url": url,
        "source": "remoteok",
        "posted_at": (raw.get("date") or "")[:10] or None,
    }


def fetch_remoteok() -> list[dict]:
    """Fetch remote job listings from RemoteOK's public API (no auth required).

    Non-fatal: returns [] on any HTTP or parse error so the pipeline continues
    with Remotive results.
    """
    try:
        resp = requests.get(
            _REMOTEOK_API,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (job-matcher bot)"},
        )
        resp.raise_for_status()
        data = resp.json()
        # First element is {"legal": "..."} metadata — filter by presence of "position"
        jobs = [item for item in data if isinstance(item, dict) and "position" in item]
        return [_normalize_remoteok(j) for j in jobs]
    except Exception:
        return []
```

- [ ] **Step 4: Update `src/job_matcher/nodes/fetch.py`**

Replace the full file content:

```python
import os
from concurrent.futures import ThreadPoolExecutor
from ..fetcher import fetch_jobs, fetch_remoteok, load_cache, save_cache
from ..models import MatcherState
from ..mongo import mongo_db
from ..token_tracker import TokenTracker


def fetch_node(state: MatcherState) -> dict:
    base_url = os.environ.get("HIRING_CAFE_URL", "https://hiring.cafe")

    with ThreadPoolExecutor(max_workers=2) as pool:
        remotive_future = pool.submit(fetch_jobs, base_url, limit=100)
        remoteok_future = pool.submit(fetch_remoteok)
        remotive_jobs = remotive_future.result()
        remoteok_jobs = remoteok_future.result()

    raw = remotive_jobs + remoteok_jobs

    # Deduplicate by apply_url — first occurrence wins
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    for job in raw:
        url = job.get("apply_url", "")
        if not url or url not in seen_urls:
            if url:
                seen_urls.add(url)
            deduped.append(job)

    mongo_db.save_raw_jobs(deduped)

    seen = load_cache()
    seen.update(j["id"] for j in deduped)
    save_cache(seen)

    tracker = TokenTracker()
    return {
        "raw_jobs": deduped,
        "token_stats": tracker.to_dict(),
    }
```

- [ ] **Step 5: Run all tests to verify passing**

```bash
.venv\Scripts\python.exe -m pytest tests/test_pipeline.py tests/test_score.py tests/test_filter.py tests/test_models.py -v
```

Expected: all tests pass (no failures).

- [ ] **Step 6: Commit**

```bash
git add src/job_matcher/fetcher.py src/job_matcher/nodes/fetch.py tests/test_pipeline.py
git commit -m "feat: add RemoteOK source with parallel fetch and deduplication by apply_url"
```

---

## Task 3: SSE payload — add description + score_breakdown

**Wave: 2 (after Task 1)**

**Files:**
- Modify: `backend/routers/jobs.py:59-70` (the `jobs_payload` list comprehension in `_stream_pipeline`)

**Interfaces:**
- Consumes: `ScoredJob.breakdown: ScoreBreakdown` (from Task 1)
- Produces: SSE rank event includes `description` and `score_breakdown` per job

---

- [ ] **Step 1: Update `jobs_payload` in `backend/routers/jobs.py`**

Find the `jobs_payload` list comprehension (lines 59-70) and replace it:

```python
                jobs_payload = [
                    {
                        "score": round(j.score, 1),
                        "score_breakdown": {
                            "stack": round(j.breakdown.stack, 1),
                            "seniority": round(j.breakdown.seniority, 1),
                            "ai_bonus": round(j.breakdown.ai_bonus, 1),
                            "recency": round(j.breakdown.recency, 1),
                        },
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
```

- [ ] **Step 2: Verify backend imports cleanly**

```bash
.venv\Scripts\python.exe -c "from backend.main import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run full Python test suite to confirm no regressions**

```bash
.venv\Scripts\python.exe -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add backend/routers/jobs.py
git commit -m "feat: add description and score_breakdown to SSE rank payload"
```

---

## Task 4: Frontend — shared types + JobModal + ScoreFilter + updated JobCard + page.tsx

**Wave: 3 (after Task 3)**

**Files:**
- Create: `web/src/types/job.ts`
- Create: `web/src/components/JobModal.tsx`
- Create: `web/src/components/ScoreFilter.tsx`
- Modify: `web/src/components/JobCard.tsx`
- Modify: `web/src/app/page.tsx`

---

- [ ] **Step 1: Create `web/src/types/job.ts`**

```typescript
export interface ScoreBreakdown {
  stack: number
  seniority: number
  ai_bonus: number
  recency: number
}

export interface Job {
  score: number
  score_breakdown: ScoreBreakdown
  title: string
  company: string
  posted_at: string | null
  apply_url: string
  skills: string[]
  seniority: string | null
  description: string
}
```

- [ ] **Step 2: Create `web/src/components/ScoreFilter.tsx`**

```typescript
type FilterValue = 'all' | 70 | 40

interface Props {
  value: FilterValue
  onChange: (v: FilterValue) => void
}

const OPTIONS: { label: string; value: FilterValue }[] = [
  { label: 'All', value: 'all' },
  { label: '≥70', value: 70 },
  { label: '≥40', value: 40 },
]

export function ScoreFilter({ value, onChange }: Props) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-gray-500 text-sm">Score:</span>
      <div className="flex rounded-lg overflow-hidden border border-gray-700">
        {OPTIONS.map((opt) => (
          <button
            key={String(opt.value)}
            onClick={() => onChange(opt.value)}
            className={`px-3 py-1.5 text-sm font-medium transition-colors
              ${value === opt.value
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-900 text-gray-400 hover:bg-gray-800'
              }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Create `web/src/components/JobModal.tsx`**

```typescript
'use client'

import { useEffect } from 'react'
import type { Job } from '@/types/job'

interface Props {
  job: Job | null
  onClose: () => void
}

const BREAKDOWN_BARS = [
  { key: 'stack' as const, label: 'Stack match', max: 40, color: 'bg-indigo-500' },
  { key: 'seniority' as const, label: 'Seniority', max: 40, color: 'bg-purple-500' },
  { key: 'ai_bonus' as const, label: 'AI/GenAI bonus', max: 20, color: 'bg-emerald-500' },
  { key: 'recency' as const, label: 'Recency', max: 20, color: 'bg-sky-500' },
]

export function JobModal({ job, onClose }: Props) {
  useEffect(() => {
    if (!job) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [job, onClose])

  if (!job) return null

  const scoreColor =
    job.score >= 70 ? 'text-green-400' :
    job.score >= 40 ? 'text-yellow-400' : 'text-red-400'

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative z-10 w-full max-w-lg bg-gray-950 border-l border-gray-800 h-full overflow-y-auto flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 p-6 border-b border-gray-800">
          <div className="flex-1 min-w-0">
            <h2 id="modal-title" className="text-white font-semibold text-lg leading-tight">
              {job.title}
            </h2>
            <p className="text-gray-400 text-sm mt-0.5">{job.company}</p>
            {job.posted_at && (
              <p className="text-gray-600 text-xs mt-1">{job.posted_at}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-300 text-xl leading-none flex-shrink-0"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* Score */}
        <div className="px-6 pt-5">
          <div className="flex items-baseline gap-2 mb-4">
            <span className={`text-4xl font-bold font-mono ${scoreColor}`}>
              {job.score.toFixed(0)}
            </span>
            <span className="text-gray-500 text-sm">/ 100</span>
          </div>

          {/* Score breakdown bars */}
          <div className="space-y-3 mb-6">
            {BREAKDOWN_BARS.map(({ key, label, max, color }) => {
              const value = job.score_breakdown[key]
              // seniority range is -20..20, shift to 0..40 for bar display
              const displayValue = key === 'seniority' ? value + 20 : value
              const pct = Math.max(0, (displayValue / max) * 100)
              const isNeg = key === 'seniority' && value < 0
              return (
                <div key={key}>
                  <div className="flex justify-between text-xs text-gray-400 mb-1">
                    <span>{label}</span>
                    <span className={isNeg ? 'text-red-400' : 'text-gray-300'}>
                      {value > 0 ? '+' : ''}{value.toFixed(1)}
                    </span>
                  </div>
                  <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${isNeg ? 'bg-red-500' : color}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Skills */}
        {job.skills.length > 0 && (
          <div className="px-6 mb-5">
            <h3 className="text-gray-400 text-xs font-semibold uppercase tracking-wider mb-2">
              Skills
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {job.skills.map((s) => (
                <span key={s} className="bg-gray-800 text-gray-300 text-xs px-2 py-0.5 rounded-full">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Description */}
        {job.description && (
          <div className="px-6 mb-6 flex-1">
            <h3 className="text-gray-400 text-xs font-semibold uppercase tracking-wider mb-2">
              Description
            </h3>
            <div
              className="text-gray-300 text-sm leading-relaxed whitespace-pre-wrap max-h-96 overflow-y-auto pr-1"
              dangerouslySetInnerHTML={{ __html: job.description }}
            />
          </div>
        )}

        {/* Apply button */}
        <div className="p-6 border-t border-gray-800 mt-auto">
          <a
            href={job.apply_url}
            target="_blank"
            rel="noopener noreferrer"
            className="block w-full text-center bg-indigo-600 hover:bg-indigo-500 text-white font-semibold py-3 rounded-xl transition-colors"
          >
            Apply for this role
          </a>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Update `web/src/components/JobCard.tsx`**

Replace the full file content:

```typescript
import type { Job } from '@/types/job'

interface Props {
  job: Job
  rank: number
  onSelect: (job: Job) => void
}

export function JobCard({ job, rank, onSelect }: Props) {
  const scoreColor =
    job.score >= 70 ? 'text-green-400' :
    job.score >= 40 ? 'text-yellow-400' : 'text-red-400'

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(job)}
      onKeyDown={(e) => e.key === 'Enter' && onSelect(job)}
      className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex flex-col gap-3 hover:border-gray-600 transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 text-gray-500 text-sm font-mono">
          #{rank}
        </div>
        <span className={`text-2xl font-bold font-mono ${scoreColor}`}>
          {job.score.toFixed(0)}
        </span>
      </div>

      <div>
        <h3 className="font-semibold text-white text-base leading-tight">{job.title}</h3>
        <p className="text-gray-400 text-sm mt-0.5">{job.company}</p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {job.skills.slice(0, 5).map((s) => (
          <span key={s} className="bg-gray-800 text-gray-300 text-xs px-2 py-0.5 rounded-full">
            {s}
          </span>
        ))}
      </div>

      <div className="flex items-center justify-between mt-auto pt-2 border-t border-gray-800">
        <span className="text-gray-500 text-xs">{job.posted_at ?? 'unknown date'}</span>
        <a
          href={job.apply_url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="bg-indigo-600 hover:bg-indigo-500 text-white text-sm px-3 py-1.5 rounded-lg transition-colors"
        >
          Apply
        </a>
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Update `web/src/app/page.tsx`**

Replace the full file content:

```typescript
'use client'

import { useState } from 'react'
import { JobCard } from '@/components/JobCard'
import { JobModal } from '@/components/JobModal'
import { PipelineStatus } from '@/components/PipelineStatus'
import { ScoreFilter } from '@/components/ScoreFilter'
import type { Job } from '@/types/job'

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

export default function Home() {
  const [status, setStatus] = useState<Status>('idle')
  const [activeNode, setActiveNode] = useState<string | null>(null)
  const [doneNodes, setDoneNodes] = useState<string[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [error, setError] = useState<string | null>(null)
  const [tokenStats, setTokenStats] = useState<TokenStats | null>(null)
  const [selectedJob, setSelectedJob] = useState<Job | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [scoreFilter, setScoreFilter] = useState<FilterValue>('all')

  // Derived — no extra state
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
    setActiveNode(null)
    setDoneNodes([])
    setJobs([])
    setError(null)
    setTokenStats(null)
    setCurrentPage(1)
    setScoreFilter('all')

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
            return
          }
          if (data.token_stats && Object.keys(data.token_stats).length > 0) {
            setTokenStats(data.token_stats)
          }
          if (data.node) setActiveNode(data.node)
          if (data.done_node) setDoneNodes((prev) => [...prev, data.done_node])
          if (data.jobs) {
            setJobs(data.jobs)
            setStatus('done')
            setActiveNode(null)
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
      setStatus('error')
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
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed
            text-white font-semibold px-8 py-3 rounded-xl text-lg transition-colors"
        >
          {status === 'running' ? 'Running pipeline...' : 'Find matching jobs'}
        </button>

        {status === 'running' && (
          <PipelineStatus activeNode={activeNode} doneNodes={doneNodes} />
        )}

        {status === 'error' && (
          <p className="text-red-400 text-sm">Error: {error}</p>
        )}
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
                ← Previous
              </button>
              <span className="text-gray-400 text-sm">
                Page {currentPage} of {totalPages}
              </span>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="px-4 py-2 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed text-sm transition-colors"
              >
                Next →
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

- [ ] **Step 6: TypeScript check**

```powershell
cd web
node_modules\.bin\tsc --noEmit
```

Expected: `0 errors`

- [ ] **Step 7: Commit**

```bash
git add web/src/types/job.ts web/src/components/JobModal.tsx web/src/components/ScoreFilter.tsx web/src/components/JobCard.tsx web/src/app/page.tsx
git commit -m "feat: add JobModal, ScoreFilter, pagination, and onSelect to JobCard"
```

---

## Task 5: Playwright E2E tests for new features

**Wave: 4 (after Task 4)**

**Files:**
- Modify: `web/tests/e2e/home.spec.ts`

---

- [ ] **Step 1: Add 4 new specs to `web/tests/e2e/home.spec.ts`**

Append inside the `test.describe('Job Matcher home page', () => {` block, before the closing `})`:

```typescript
  test('clicking a job card opens the detail modal', async ({ page }) => {
    const job = {
      score: 87,
      score_breakdown: { stack: 30, seniority: 20, ai_bonus: 20, recency: 17 },
      title: 'Senior LangGraph Engineer',
      company: 'Acme AI',
      posted_at: '2026-08-10',
      apply_url: 'https://example.com/apply/1',
      skills: ['Python', 'LangGraph', 'FastAPI'],
      seniority: 'senior',
      description: 'Build LLM-powered multi-agent systems.',
    }

    await page.route('/api/run', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: `data: {"done_node":"rank","jobs":${JSON.stringify([job])}}\n\n`,
      })
    })

    await page.getByRole('button', { name: 'Find matching jobs' }).click()
    await expect(page.getByText('Senior LangGraph Engineer')).toBeVisible()

    // Click the card (it is now a role=button div)
    await page.getByRole('button', { name: /Senior LangGraph Engineer/ }).click()

    // Modal appears
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByText('Build LLM-powered multi-agent systems.')).toBeVisible()
    await expect(page.getByText('Stack match')).toBeVisible()
  })

  test('modal closes when backdrop is clicked', async ({ page }) => {
    const job = {
      score: 75,
      score_breakdown: { stack: 25, seniority: 20, ai_bonus: 10, recency: 20 },
      title: 'Backend Developer',
      company: 'Co',
      posted_at: null,
      apply_url: 'https://example.com/apply/2',
      skills: ['Python'],
      seniority: 'mid',
      description: 'Python backend role.',
    }

    await page.route('/api/run', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: `data: {"done_node":"rank","jobs":${JSON.stringify([job])}}\n\n`,
      })
    })

    await page.getByRole('button', { name: 'Find matching jobs' }).click()
    await page.getByRole('button', { name: /Backend Developer/ }).click()
    await expect(page.getByRole('dialog')).toBeVisible()

    // Click the backdrop (the fixed overlay behind the panel)
    await page.locator('.fixed.inset-0 > div.absolute').click({ force: true })
    await expect(page.getByRole('dialog')).not.toBeVisible()
  })

  test('score filter hides jobs below threshold', async ({ page }) => {
    const makeJob = (score: number, title: string, idx: number) => ({
      score,
      score_breakdown: { stack: score * 0.4, seniority: 10, ai_bonus: 5, recency: 5 },
      title,
      company: 'Co',
      posted_at: null,
      apply_url: `https://example.com/apply/${idx}`,
      skills: [],
      seniority: null,
      description: '',
    })

    const jobs = [makeJob(85, 'High Score Job', 1), makeJob(30, 'Low Score Job', 2)]

    await page.route('/api/run', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: `data: {"done_node":"rank","jobs":${JSON.stringify(jobs)}}\n\n`,
      })
    })

    await page.getByRole('button', { name: 'Find matching jobs' }).click()
    await expect(page.getByText('High Score Job')).toBeVisible()
    await expect(page.getByText('Low Score Job')).toBeVisible()

    // Apply ≥70 filter
    await page.getByRole('button', { name: '≥70' }).click()

    await expect(page.getByText('High Score Job')).toBeVisible()
    await expect(page.getByText('Low Score Job')).not.toBeVisible()
  })

  test('pagination shows next page', async ({ page }) => {
    // Generate 10 jobs so page 1 has 8, page 2 has 2
    const jobs = Array.from({ length: 10 }, (_, i) => ({
      score: 70 + i,
      score_breakdown: { stack: 20, seniority: 20, ai_bonus: 15, recency: 15 },
      title: `Job ${i + 1}`,
      company: 'Co',
      posted_at: null,
      apply_url: `https://example.com/apply/${i + 1}`,
      skills: [],
      seniority: null,
      description: '',
    }))

    await page.route('/api/run', async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: `data: {"done_node":"rank","jobs":${JSON.stringify(jobs)}}\n\n`,
      })
    })

    await page.getByRole('button', { name: 'Find matching jobs' }).click()

    // Page 1: Job 1 visible, Job 10 not visible
    await expect(page.getByText('Job 1')).toBeVisible()
    await expect(page.getByText('Job 10')).not.toBeVisible()
    await expect(page.getByText('Page 1 of 2')).toBeVisible()

    // Navigate to page 2
    await page.getByRole('button', { name: 'Next →' }).click()

    await expect(page.getByText('Job 10')).toBeVisible()
    await expect(page.getByText('Job 1')).not.toBeVisible()
    await expect(page.getByText('Page 2 of 2')).toBeVisible()

    // Previous button goes back
    await page.getByRole('button', { name: '← Previous' }).click()
    await expect(page.getByText('Page 1 of 2')).toBeVisible()
  })
```

- [ ] **Step 2: Run the full Playwright test suite**

```powershell
cd web
npx playwright test
```

Expected: `12 passed, 1 skipped` (8 original + 4 new)

- [ ] **Step 3: Commit**

```bash
git add web/tests/e2e/home.spec.ts
git commit -m "test: add E2E specs for modal, score filter, and pagination"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| RemoteOK parallel fetch | Task 2: `fetch_remoteok` + ThreadPoolExecutor in `fetch_node` |
| Deduplication by `apply_url` | Task 2: `fetch_node` dedup loop |
| `ScoreBreakdown` model | Task 1: `models.py` |
| `score_job` returns tuple | Task 1: `score.py` |
| `description` in SSE payload | Task 3: `jobs.py` |
| `score_breakdown` in SSE payload | Task 3: `jobs.py` |
| Shared Job TypeScript type | Task 4: `web/src/types/job.ts` |
| `JobModal` slide-over drawer | Task 4: `JobModal.tsx` |
| Score breakdown bars in modal | Task 4: `JobModal.tsx` `BREAKDOWN_BARS` |
| `ScoreFilter` toggle buttons | Task 4: `ScoreFilter.tsx` |
| `onSelect` on `JobCard` | Task 4: `JobCard.tsx` |
| Pagination 8 per page | Task 4: `page.tsx` `JOBS_PER_PAGE = 8` |
| Filter resets to page 1 | Task 4: `handleFilterChange` |
| Playwright: modal open | Task 5 |
| Playwright: modal close | Task 5 |
| Playwright: score filter | Task 5 |
| Playwright: pagination | Task 5 |

No gaps found. All spec requirements covered.
