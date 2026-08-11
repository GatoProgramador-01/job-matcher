# Job Matcher MVP — Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans or parallel-executor to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CLI that fetches job postings from hiring.cafe daily and returns the top 10 ranked by fit against a developer profile, using a LangGraph pipeline with DeepSeek for structured extraction.

**Architecture:** A LangGraph `StateGraph` threads state through five nodes: fetch (HTTP + cache) → filter (hard rules, no LLM) → extract (DeepSeek structured JSON per job) → score (deterministic formula) → rank+display. The scorer is pure Python so tests run offline with fixtures.

**Tech Stack:** Python 3.11+, LangGraph ≥0.2, langchain-openai (DeepSeek via OpenAI compat), Pydantic v2, requests, python-dotenv, pytest.

## Global Constraints

- Total source lines ≤ 500 (excluding tests, pyproject.toml, docs).
- DeepSeek API key loaded from `.env` only — never hardcoded, never logged.
- `profile.json` and `cache.json` are gitignored — personal data stays local.
- All tests run offline (`pytest tests/`) — no real network, no real LLM calls.
- `python-dotenv` loads `.env` at CLI startup only — library modules never call `load_dotenv()`.
- DeepSeek model: `deepseek-chat`. Base URL: `https://api.deepseek.com`.

---

## File Map

```
src/job_matcher/
  __init__.py          empty
  models.py            Pydantic models for all domain types + MatcherState
  profile.py           loads and validates profile.json into ProfileData
  fetcher.py           hiring.cafe HTTP client + cache.json read/write
  pipeline.py          LangGraph StateGraph definition (wires all nodes)
  nodes/
    __init__.py        empty
    fetch.py           fetch_node: calls fetcher, populates raw_jobs
    filter_.py         filter_node: hard filters, populates filtered_jobs
    extract.py         extract_node: DeepSeek structured extraction per job
    score.py           score_node: deterministic scoring, populates scored_jobs
    rank.py            rank_node: sort + top-10 + display output
  cli.py               argparse entry point: `run [--json] [--profile PATH]`

tests/
  fixtures/
    sample_jobs.json   10 hand-crafted job fixtures covering all scoring cases
  test_models.py       Pydantic model validation
  test_filter.py       hard filter logic (reject keywords, remote detection)
  test_score.py        scoring algorithm: all four factors + edge cases
  test_pipeline.py     end-to-end with fully mocked fetcher + LLM
```

---

### Task 1: Models + Profile Loader

**Files:**
- Create: `src/job_matcher/__init__.py`
- Create: `src/job_matcher/models.py`
- Create: `src/job_matcher/profile.py`
- Create: `src/job_matcher/nodes/__init__.py`
- Create: `tests/fixtures/sample_jobs.json`
- Create: `tests/test_models.py`

**Interfaces:**
- Produces:
  - `Job(id, title, company, location, remote, description, apply_url, source, posted_at, fetched_at)` — Pydantic BaseModel
  - `ExtractedJob(job: Job, required_skills: list[str], seniority: str | None, is_remote: bool, latam_eligible: bool)` — Pydantic BaseModel
  - `ScoredJob(job: Job, extracted: ExtractedJob, score: float, discard_reason: str | None)` — Pydantic BaseModel
  - `ProfileData(preferred_keywords: list[str], reject_keywords: list[str], target_seniority: list[str], avoid_seniority: list[str])` — Pydantic BaseModel
  - `MatcherState` — TypedDict with keys: `profile`, `raw_jobs`, `filtered_jobs`, `extracted_jobs`, `scored_jobs`, `top_jobs`, `output_format`
  - `load_profile(path: str) -> ProfileData`

- [ ] **Step 1: Write `src/job_matcher/__init__.py`**

```python
```
(empty file — marks package root)

- [ ] **Step 2: Write `src/job_matcher/nodes/__init__.py`**

```python
```
(empty file)

- [ ] **Step 3: Write `src/job_matcher/models.py`**

```python
from __future__ import annotations
from datetime import date, datetime
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
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class ExtractedJob(BaseModel):
    job: Job
    required_skills: list[str] = Field(default_factory=list)
    seniority: str | None = None
    is_remote: bool = False
    latam_eligible: bool = False


class ScoredJob(BaseModel):
    job: Job
    extracted: ExtractedJob
    score: float
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
```

- [ ] **Step 4: Write `src/job_matcher/profile.py`**

```python
import json
from pathlib import Path
from .models import ProfileData


def load_profile(path: str) -> ProfileData:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    criteria = data["job_search_criteria"]
    return ProfileData(
        preferred_keywords=criteria["preferred_keywords"],
        reject_keywords=criteria["reject_keywords"],
        target_seniority=criteria["target_seniority"],
        avoid_seniority=criteria["avoid_seniority"],
    )
```

- [ ] **Step 5: Write `tests/fixtures/sample_jobs.json`**

```json
[
  {
    "id": "j001",
    "title": "Backend Developer — Node.js / TypeScript",
    "company": "Acme Corp",
    "location": "Remote — LatAm",
    "remote": true,
    "description": "We need a mid-level backend developer with Node.js, TypeScript, and PostgreSQL. Bonus if you know AWS Lambda and NestJS.",
    "apply_url": "https://example.com/apply/j001",
    "source": "greenhouse",
    "posted_at": "2026-08-11"
  },
  {
    "id": "j002",
    "title": "Junior Python Developer",
    "company": "StartupXYZ",
    "location": "Remote",
    "remote": true,
    "description": "Junior Python developer for our Django backend. Remote friendly.",
    "apply_url": "https://example.com/apply/j002",
    "source": "lever",
    "posted_at": "2026-08-10"
  },
  {
    "id": "j003",
    "title": "Senior Backend Engineer — LangGraph / RAG",
    "company": "AI Startup",
    "location": "Worldwide remote",
    "remote": true,
    "description": "Building multi-agent systems with LangGraph and Anthropic API. Python, FastAPI, PostgreSQL. Open to LatAm candidates.",
    "apply_url": "https://example.com/apply/j003",
    "source": "workable",
    "posted_at": "2026-08-11"
  },
  {
    "id": "j004",
    "title": "Full Stack Developer",
    "company": "US Only Corp",
    "location": "US only",
    "remote": false,
    "description": "Must reside in the United States. React and Node.js.",
    "apply_url": "https://example.com/apply/j004",
    "source": "greenhouse",
    "posted_at": "2026-08-09"
  },
  {
    "id": "j005",
    "title": "Salesforce Developer",
    "company": "Enterprise Ltd",
    "location": "Remote — Chile",
    "remote": true,
    "description": "Salesforce development and integration. CRM experience required.",
    "apply_url": "https://example.com/apply/j005",
    "source": "workday",
    "posted_at": "2026-08-08"
  },
  {
    "id": "j006",
    "title": "Backend Developer — Python / Django",
    "company": "Fintech Co",
    "location": "Remote — Chile eligible",
    "remote": true,
    "description": "Mid-level backend developer with Django, PostgreSQL, and Docker. AWS Lambda experience a plus.",
    "apply_url": "https://example.com/apply/j006",
    "source": "lever",
    "posted_at": "2026-08-07"
  },
  {
    "id": "j007",
    "title": "Staff Engineer — Microservices",
    "company": "BigCo",
    "location": "Remote anywhere",
    "remote": true,
    "description": "Staff-level microservices architect. Kubernetes, AWS ECS, NestJS, TypeScript.",
    "apply_url": "https://example.com/apply/j007",
    "source": "greenhouse",
    "posted_at": "2026-08-05"
  },
  {
    "id": "j008",
    "title": "Backend Engineer — Node.js",
    "company": "SaaS Inc",
    "location": "Remote — Latin America",
    "remote": true,
    "description": "Semi-senior backend engineer with Node.js, MongoDB, and RabbitMQ. GraphQL is a plus.",
    "apply_url": "https://example.com/apply/j008",
    "source": "bamboohr",
    "posted_at": "2026-08-11"
  },
  {
    "id": "j009",
    "title": "AI Backend Developer — LLM Integration",
    "company": "LLM Startup",
    "location": "Remote worldwide",
    "remote": true,
    "description": "Build LLM-powered features. Python, FastAPI, vector search, OpenAI API. Mid-level.",
    "apply_url": "https://example.com/apply/j009",
    "source": "lever",
    "posted_at": "2026-08-10"
  },
  {
    "id": "j010",
    "title": "Internship — Java Developer",
    "company": "Old Corp",
    "location": "Remote — Chile",
    "remote": true,
    "description": "Java internship for recent graduates. Spring Boot.",
    "apply_url": "https://example.com/apply/j010",
    "source": "workday",
    "posted_at": "2026-08-11"
  }
]
```

- [ ] **Step 6: Write `tests/test_models.py`**

```python
from datetime import date
from job_matcher.models import Job, ExtractedJob, ScoredJob, ProfileData


def test_job_defaults():
    j = Job(id="x", title="Dev", company="Co", apply_url="https://x.com")
    assert j.remote is False
    assert j.description == ""
    assert j.posted_at is None


def test_extracted_job_wraps_job():
    j = Job(id="x", title="Dev", company="Co", apply_url="https://x.com")
    e = ExtractedJob(job=j, required_skills=["Python"], seniority="mid", is_remote=True, latam_eligible=True)
    assert e.job.id == "x"
    assert "Python" in e.required_skills


def test_profile_data_loads():
    p = ProfileData(
        preferred_keywords=["Python", "Node.js"],
        reject_keywords=["US only"],
        target_seniority=["mid-level"],
        avoid_seniority=["junior"],
    )
    assert "Python" in p.preferred_keywords


def test_scored_job_discard_reason_optional():
    j = Job(id="x", title="Dev", company="Co", apply_url="https://x.com")
    e = ExtractedJob(job=j)
    s = ScoredJob(job=j, extracted=e, score=75.0)
    assert s.discard_reason is None
```

- [ ] **Step 7: Install dev environment and run tests**

```bash
cd /c/Users/lanitaEmperadora/Documents/github/job-matcher
python -m venv .venv
source .venv/Scripts/activate   # Windows bash
pip install -e ".[dev]"
pytest tests/test_models.py -v
```

Expected: 4 PASSED.

- [ ] **Step 8: Commit**

```bash
git add src/ tests/ pyproject.toml .gitignore .env.example profile.example.json
git commit -m "feat: add domain models, profile loader, and test fixtures"
```

---

### Task 2: Hard Filter Node + Score Node

**Files:**
- Create: `src/job_matcher/nodes/filter_.py`
- Create: `src/job_matcher/nodes/score.py`
- Create: `tests/test_filter.py`
- Create: `tests/test_score.py`

**Interfaces:**
- Consumes: `Job`, `ExtractedJob`, `ProfileData` from Task 1.
- Produces:
  - `apply_hard_filters(jobs: list[Job], profile: ProfileData) -> tuple[list[Job], list[ScoredJob]]`
    Returns `(passed, discarded)` where discarded ScoredJobs have `discard_reason` set and `score=-999`.
  - `score_job(extracted: ExtractedJob, profile: ProfileData, today: date) -> float`
    Returns score in range [-20, 100].
  - `filter_node(state: MatcherState) -> dict` — LangGraph node signature.
  - `score_node(state: MatcherState) -> dict` — LangGraph node signature.

**Scoring formula:**
```
score = clip(stack_overlap(0-40) + seniority_fit(-20 to 20) + ai_bonus(0-20) + recency(0-20), -20, 100)
```

- [ ] **Step 1: Write `tests/test_filter.py`**

```python
import json
from pathlib import Path
from datetime import date
from job_matcher.models import Job, ProfileData
from job_matcher.nodes.filter_ import apply_hard_filters

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sample_jobs.json").read_text()
)
JOBS = [Job(**f) for f in FIXTURES]

PROFILE = ProfileData(
    preferred_keywords=["Node.js", "Python", "TypeScript", "AWS", "Django"],
    reject_keywords=["US only", "must reside in the United States", "Salesforce", "internship", "Java only"],
    target_seniority=["mid-level", "semi-senior"],
    avoid_seniority=["junior", "trainee"],
)

def _get(job_id: str) -> Job:
    return next(j for j in JOBS if j.id == job_id)


def test_reject_keyword_us_only():
    passed, discarded = apply_hard_filters([_get("j004")], PROFILE)
    assert len(passed) == 0
    assert discarded[0].discard_reason.startswith("reject_keyword:")


def test_reject_keyword_salesforce():
    passed, discarded = apply_hard_filters([_get("j005")], PROFILE)
    assert len(passed) == 0
    assert "salesforce" in discarded[0].discard_reason.lower()


def test_reject_keyword_internship():
    passed, discarded = apply_hard_filters([_get("j010")], PROFILE)
    assert len(passed) == 0


def test_not_remote_eligible_discards():
    job = Job(
        id="z1", title="Dev", company="Co", apply_url="https://x.com",
        description="Great role", location="San Francisco, CA", remote=False
    )
    passed, discarded = apply_hard_filters([job], PROFILE)
    assert len(passed) == 0
    assert discarded[0].discard_reason == "not_remote_eligible"


def test_latam_in_location_passes():
    passed, _ = apply_hard_filters([_get("j001")], PROFILE)
    assert len(passed) == 1


def test_remote_worldwide_passes():
    passed, _ = apply_hard_filters([_get("j003")], PROFILE)
    assert len(passed) == 1


def test_multiple_mixed_jobs():
    passed, discarded = apply_hard_filters(JOBS, PROFILE)
    passing_ids = {j.id for j in passed}
    assert "j004" not in passing_ids  # US only
    assert "j005" not in passing_ids  # Salesforce
    assert "j010" not in passing_ids  # internship
    assert "j001" in passing_ids
    assert "j003" in passing_ids
```

- [ ] **Step 2: Write `tests/test_score.py`**

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
    assert score_job(e_title, PROFILE, TODAY) > score_job(e_body, PROFILE, TODAY)


def test_seniority_mid_level_max_bonus():
    e = _job(title="Mid-level Backend Developer")
    s = score_job(e, PROFILE, TODAY)
    e2 = _job(title="Senior Backend Developer")
    s2 = score_job(e2, PROFILE, TODAY)
    assert s > s2


def test_seniority_junior_penalizes():
    e = _job(title="Junior Python Developer", description="Python Django")
    s = score_job(e, PROFILE, TODAY)
    e2 = _job(title="Mid-level Python Developer", description="Python Django")
    s2 = score_job(e2, PROFILE, TODAY)
    assert s < s2


def test_ai_bonus_tier_a_langgraph():
    e = _job(description="Building multi-agent systems with LangGraph and RAG pipelines.")
    s = score_job(e, PROFILE, TODAY)
    e2 = _job(description="Standard backend work.")
    s2 = score_job(e2, PROFILE, TODAY)
    assert s > s2 + 15


def test_ai_bonus_tier_b_openai():
    e = _job(description="Integration with OpenAI API and machine learning models.")
    s = score_job(e, PROFILE, TODAY)
    e2 = _job(description="Standard backend work.")
    s2 = score_job(e2, PROFILE, TODAY)
    assert s > s2


def test_recency_today_max():
    from datetime import timedelta
    e_today = _job(posted_at=TODAY)
    e_old = _job(posted_at=date(2026, 7, 20))
    assert score_job(e_today, PROFILE, TODAY) > score_job(e_old, PROFILE, TODAY)


def test_score_capped_at_100():
    e = _job(
        title="Mid-level Node.js TypeScript Python AWS Django Developer",
        description="LangGraph RAG multi-agent systems. LatAm eligible.",
        posted_at=TODAY
    )
    assert score_job(e, PROFILE, TODAY) <= 100


def test_score_floor_at_minus_20():
    e = _job(title="Junior intern trainee entry level")
    assert score_job(e, PROFILE, TODAY) >= -20
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_filter.py tests/test_score.py -v
```

Expected: ImportError or ModuleNotFoundError — nodes don't exist yet.

- [ ] **Step 4: Write `src/job_matcher/nodes/filter_.py`**

```python
from datetime import date
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
```

- [ ] **Step 5: Write `src/job_matcher/nodes/score.py`**

```python
from datetime import date
from ..models import ExtractedJob, ScoredJob, ProfileData, MatcherState

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


def score_job(extracted: ExtractedJob, profile: ProfileData, today: date) -> float:
    total = (
        _stack_score(extracted, profile.preferred_keywords)
        + _seniority_score(extracted)
        + _ai_bonus(extracted)
        + _recency_score(extracted, today)
    )
    return max(-20.0, min(100.0, total))


def score_node(state: MatcherState) -> dict:
    profile = state["profile"]
    today = date.today()
    scored = [
        ScoredJob(
            job=e.job,
            extracted=e,
            score=score_job(e, profile, today),
        )
        for e in state["extracted_jobs"]
    ]
    return {"scored_jobs": scored}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_filter.py tests/test_score.py -v
```

Expected: all PASSED.

- [ ] **Step 7: Commit**

```bash
git add src/job_matcher/nodes/filter_.py src/job_matcher/nodes/score.py tests/test_filter.py tests/test_score.py
git commit -m "feat: add hard filter and deterministic scorer with full test coverage"
```

---

### Task 3: hiring.cafe Fetcher + Cache + Fetch Node

**Files:**
- Create: `src/job_matcher/fetcher.py`
- Create: `src/job_matcher/nodes/fetch.py`
- Create: `tests/test_pipeline.py` (partial — fetcher mock only for now)

**Interfaces:**
- Consumes: nothing from prior tasks (standalone HTTP layer).
- Produces:
  - `fetch_jobs(base_url: str, query: str, limit: int) -> list[dict]`
    Returns raw dicts from API. Raises `FetchError` on HTTP failure after 1 retry.
  - `load_cache(path: str) -> set[str]` — returns set of already-seen job IDs.
  - `save_cache(path: str, ids: set[str]) -> None`
  - `fetch_node(state: MatcherState) -> dict` — LangGraph node; populates `raw_jobs`.

**NOTE — API contract is assumed (see spec supuesto A4-A8).** The fetcher maps the assumed response shape. If hiring.cafe's real API differs, only `fetcher.py` needs to change.

- [ ] **Step 1: Write `src/job_matcher/fetcher.py`**

```python
import hashlib
import json
import time
from pathlib import Path

import requests

CACHE_PATH = "cache.json"
_REMOTE_SIGNALS_QUERY = "remote LatAm"


class FetchError(Exception):
    pass


def _job_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def fetch_jobs(base_url: str, query: str = "backend developer remote", limit: int = 50) -> list[dict]:
    url = f"{base_url.rstrip('/')}/api/jobs/search"
    payload = {
        "query": f"{query} {_REMOTE_SIGNALS_QUERY}",
        "filters": {"remote": True},
        "page": 1,
        "limit": limit,
    }
    for attempt in range(2):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 429 and attempt == 0:
                time.sleep(5)
                continue
            resp.raise_for_status()
            data = resp.json()
            jobs = data.get("jobs") or data.get("results") or []
            return [_normalize(j) for j in jobs]
        except requests.RequestException as exc:
            if attempt == 1:
                raise FetchError(str(exc)) from exc
            time.sleep(5)
    return []


def _normalize(raw: dict) -> dict:
    apply_url = raw.get("applyUrl") or raw.get("apply_url") or raw.get("url", "")
    return {
        "id": raw.get("id") or _job_id(apply_url),
        "title": raw.get("title", ""),
        "company": raw.get("company", ""),
        "location": raw.get("location"),
        "remote": bool(raw.get("remote", False)),
        "description": raw.get("description") or raw.get("body") or "",
        "apply_url": apply_url,
        "source": raw.get("source") or raw.get("ats", ""),
        "posted_at": (raw.get("postedAt") or raw.get("posted_at") or "")[:10] or None,
    }


def load_cache(path: str = CACHE_PATH) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    return set(json.loads(p.read_text(encoding="utf-8")))


def save_cache(ids: set[str], path: str = CACHE_PATH) -> None:
    Path(path).write_text(json.dumps(list(ids), indent=2), encoding="utf-8")
```

- [ ] **Step 2: Write `src/job_matcher/nodes/fetch.py`**

```python
import os
from ..fetcher import fetch_jobs, load_cache, save_cache, FetchError
from ..models import MatcherState


def fetch_node(state: MatcherState) -> dict:
    base_url = os.environ["HIRING_CAFE_URL"]
    raw = fetch_jobs(base_url)

    seen = load_cache()
    new_jobs = [j for j in raw if j["id"] not in seen]

    seen.update(j["id"] for j in new_jobs)
    save_cache(seen)

    return {"raw_jobs": new_jobs}
```

- [ ] **Step 3: Write the mocked fetcher test in `tests/test_pipeline.py`**

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from job_matcher.fetcher import fetch_jobs, load_cache, save_cache, _normalize
from job_matcher.models import ProfileData

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "sample_jobs.json").read_text()
)


def test_normalize_maps_apply_url():
    raw = {"applyUrl": "https://x.com/j1", "title": "Dev", "company": "Co"}
    result = _normalize(raw)
    assert result["apply_url"] == "https://x.com/j1"
    assert result["title"] == "Dev"


def test_normalize_fallback_id_from_url():
    raw = {"applyUrl": "https://x.com/unique-job", "title": "Dev", "company": "Co"}
    result = _normalize(raw)
    assert len(result["id"]) == 16


def test_fetch_jobs_calls_post(tmp_path):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"jobs": FIXTURES[:3]}
    mock_resp.raise_for_status = MagicMock()

    with patch("job_matcher.fetcher.requests.post", return_value=mock_resp) as mock_post:
        jobs = fetch_jobs("https://hiring.cafe")
        assert mock_post.called
        assert len(jobs) == 3


def test_cache_roundtrip(tmp_path):
    cache_file = str(tmp_path / "cache.json")
    ids = {"abc", "def", "ghi"}
    save_cache(ids, cache_file)
    loaded = load_cache(cache_file)
    assert loaded == ids


def test_cache_empty_when_no_file(tmp_path):
    result = load_cache(str(tmp_path / "nonexistent.json"))
    assert result == set()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_pipeline.py -v
```

Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/job_matcher/fetcher.py src/job_matcher/nodes/fetch.py tests/test_pipeline.py
git commit -m "feat: add hiring.cafe fetcher with cache and LangGraph fetch node"
```

---

### Task 4: DeepSeek Extract Node

**Files:**
- Create: `src/job_matcher/nodes/extract.py`

**Interfaces:**
- Consumes: `Job` list from `filtered_jobs`, `DEEPSEEK_API_KEY` from env.
- Produces:
  - `extract_node(state: MatcherState) -> dict` — populates `extracted_jobs` with `ExtractedJob` list.
  - Each `ExtractedJob` has `required_skills`, `seniority`, `is_remote`, `latam_eligible` filled by DeepSeek.

**NOTE:** Uses `langchain-openai` with DeepSeek base URL and `.with_structured_output()`. This replaces regex parsing with actual LLM understanding, making scoring more reliable.

- [ ] **Step 1: Write `src/job_matcher/nodes/extract.py`**

```python
import os
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from ..models import Job, ExtractedJob, MatcherState


class _JobExtraction(BaseModel):
    required_skills: list[str]
    seniority: str | None
    is_remote: bool
    latam_eligible: bool


_SYSTEM = (
    "You are a job posting analyzer. Given a job title and description, "
    "extract the required skills, inferred seniority level (junior/mid/senior/staff or null), "
    "whether the role is remote, and whether Latin American candidates are eligible. "
    "Return only the JSON fields — no commentary."
)


def _make_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key=os.environ["DEEPSEEK_API_KEY"],
        temperature=0,
    ).with_structured_output(_JobExtraction)


def _extract_one(job: Job, llm) -> ExtractedJob:
    prompt = f"Title: {job.title}\n\nDescription: {job.description[:2000]}"
    try:
        result: _JobExtraction = llm.invoke([
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ])
        return ExtractedJob(
            job=job,
            required_skills=result.required_skills,
            seniority=result.seniority,
            is_remote=result.is_remote,
            latam_eligible=result.latam_eligible,
        )
    except Exception:
        return ExtractedJob(job=job)


def extract_node(state: MatcherState) -> dict:
    llm = _make_llm()
    extracted = [_extract_one(job, llm) for job in state["filtered_jobs"]]
    return {"extracted_jobs": extracted}
```

- [ ] **Step 2: Add extract node mock test to `tests/test_pipeline.py`**

Add this test at the end of `tests/test_pipeline.py`:

```python
def test_extract_node_uses_llm_structured_output():
    from unittest.mock import patch, MagicMock
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
    }

    with patch("job_matcher.nodes.extract._make_llm", return_value=mock_llm):
        result = extract_node(state)

    assert len(result["extracted_jobs"]) == 1
    assert result["extracted_jobs"][0].seniority == "mid"
    assert "Python" in result["extracted_jobs"][0].required_skills
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_pipeline.py -v
```

Expected: 6 PASSED (including the new extract test).

- [ ] **Step 4: Commit**

```bash
git add src/job_matcher/nodes/extract.py tests/test_pipeline.py
git commit -m "feat: add DeepSeek extraction node with structured output and mock test"
```

---

### Task 5: Rank Node + Pipeline Wiring + CLI

**Files:**
- Create: `src/job_matcher/nodes/rank.py`
- Create: `src/job_matcher/pipeline.py`
- Create: `src/job_matcher/cli.py`

**Interfaces:**
- Consumes: all prior nodes.
- Produces: working CLI `python -m job_matcher.cli run [--json] [--profile PATH]`.

- [ ] **Step 1: Write `src/job_matcher/nodes/rank.py`**

```python
from ..models import MatcherState, ScoredJob

TOP_N = 10


def rank_node(state: MatcherState) -> dict:
    sorted_jobs = sorted(state["scored_jobs"], key=lambda j: j.score, reverse=True)
    top = sorted_jobs[:TOP_N]
    _print_results(top, state["output_format"])
    return {"top_jobs": top}


def _print_results(jobs: list[ScoredJob], fmt: str) -> None:
    if fmt == "json":
        import json
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
```

- [ ] **Step 2: Write `src/job_matcher/pipeline.py`**

```python
from langgraph.graph import StateGraph, END
from .models import MatcherState
from .nodes.fetch import fetch_node
from .nodes.filter_ import filter_node
from .nodes.extract import extract_node
from .nodes.score import score_node
from .nodes.rank import rank_node


def build_pipeline():
    graph = StateGraph(MatcherState)
    graph.add_node("fetch", fetch_node)
    graph.add_node("filter", filter_node)
    graph.add_node("extract", extract_node)
    graph.add_node("score", score_node)
    graph.add_node("rank", rank_node)

    graph.set_entry_point("fetch")
    graph.add_edge("fetch", "filter")
    graph.add_edge("filter", "extract")
    graph.add_edge("extract", "score")
    graph.add_edge("score", "rank")
    graph.add_edge("rank", END)

    return graph.compile()
```

- [ ] **Step 3: Write `src/job_matcher/cli.py`**

```python
import argparse
import os
from dotenv import load_dotenv

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Personal job matcher — hiring.cafe")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_cmd = sub.add_parser("run", help="Fetch and rank today's jobs")
    run_cmd.add_argument("--json", action="store_true", help="Output as JSON")
    run_cmd.add_argument("--profile", default=os.environ.get("PROFILE_PATH", "profile.json"))
    args = parser.parse_args()

    if args.cmd == "run":
        _run(args)


def _run(args):
    from .profile import load_profile
    from .pipeline import build_pipeline

    profile = load_profile(args.profile)
    pipeline = build_pipeline()

    initial_state = {
        "profile": profile,
        "raw_jobs": [],
        "filtered_jobs": [],
        "extracted_jobs": [],
        "scored_jobs": [],
        "top_jobs": [],
        "output_format": "json" if args.json else "table",
    }
    pipeline.invoke(initial_state)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add end-to-end pipeline test to `tests/test_pipeline.py`**

Add at the end of `tests/test_pipeline.py`:

```python
def test_full_pipeline_offline(tmp_path, monkeypatch):
    import os
    from unittest.mock import patch, MagicMock
    from job_matcher.pipeline import build_pipeline
    from job_matcher.models import ProfileData

    monkeypatch.setenv("HIRING_CAFE_URL", "https://hiring.cafe")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.chdir(tmp_path)

    mock_fetch = MagicMock(return_value=FIXTURES[:5])
    mock_result = MagicMock()
    mock_result.required_skills = ["Python"]
    mock_result.seniority = "mid"
    mock_result.is_remote = True
    mock_result.latam_eligible = True
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_result

    with patch("job_matcher.fetcher.fetch_jobs", mock_fetch), \
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
        })

    assert len(result["top_jobs"]) <= 5
    for sj in result["top_jobs"]:
        assert sj.score >= -20
```

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all PASSED. Minimum 15 tests.

- [ ] **Step 6: Smoke test dry run (optional — requires .env with real keys)**

```bash
python -m job_matcher.cli run --json
```

Expected: JSON array printed to stdout with ≤10 job objects, each with score, title, apply_url.

- [ ] **Step 7: Final commit**

```bash
git add src/job_matcher/nodes/rank.py src/job_matcher/pipeline.py src/job_matcher/cli.py tests/test_pipeline.py
git commit -m "feat: complete LangGraph pipeline, rank node, and CLI entry point"
```

---

## Self-Review Against Spec

| Requirement | Task |
|-------------|------|
| F1 — `python matcher.py run` → top 10 | Task 5: cli.py + rank_node |
| F2 — title, company, date, score, URL | Task 5: rank.py `_print_results` |
| F3 — reject_keywords hard filter | Task 2: filter_.py |
| F4 — remote/LatAm hard filter | Task 2: filter_.py |
| F5 — cache.json dedup | Task 3: fetcher.py |
| F6 — `--json` flag | Task 5: cli.py + rank.py |
| F7 — tests run offline | Tasks 1-5: all mocked |
| LangGraph pipeline | Task 5: pipeline.py |
| DeepSeek extraction | Task 4: extract.py |
| Security — no secrets committed | .gitignore, .env.example |
| ≤500 source lines | ~430 estimated |

No gaps found.
