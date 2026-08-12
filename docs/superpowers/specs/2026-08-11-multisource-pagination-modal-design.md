# Design Spec: Multi-Source Aggregation + Pagination & Job Detail Modal

**Date:** 2026-08-11  
**Status:** Approved  
**Branch:** master → feat/multisource-pagination-modal

---

## Goals

1. **Multi-Source Aggregation**: Add RemoteOK alongside Remotive. Both fetched in parallel. Results merged and deduplicated before the filter node.
2. **Score Breakdown**: Expose the 4 score components (stack, seniority, ai_bonus, recency) in the model and SSE payload.
3. **Pagination + Score Filter**: Client-side. 8 jobs per page. Filter buttons: All / ≥70 / ≥40.
4. **Job Detail Modal**: Slide-over drawer showing full description, complete skills list, score breakdown bars, and Apply button.

---

## Architecture

```
fetch_node
  ├── ThreadPoolExecutor(max_workers=2)
  │     ├── fetch_jobs()        → Remotive (existing)
  │     └── fetch_remoteok()    → RemoteOK (new)
  ├── merge lists
  ├── deduplicate by apply_url
  └── filter by cache.json → raw_jobs

score_node → ScoredJob(score: float, breakdown: ScoreBreakdown)

rank_node → SSE payload: { score, score_breakdown: {stack, seniority, ai_bonus, recency}, ... }

Frontend (all client-side, no new API routes):
  jobs[]
  ├── ScoreFilter → filteredJobs[]
  ├── Pagination  → visibleJobs[] (8-item slice)
  ├── JobCard click → selectedJob
  └── JobModal → breakdown bars + full description + Apply
```

---

## Backend Changes

### `src/job_matcher/fetcher.py`

Add `fetch_remoteok() -> list[dict]`:
- URL: `https://remoteok.com/api`
- Response: JSON array; first element is `{"legal": "..."}` metadata — skip it.
- Field mapping:
  - `position` → `title`
  - `url` → `apply_url`
  - `company` → `company`
  - `tags` (list[str]) → joined into `description` prefix; `description` HTML field appended after
  - `date` (ISO string) → `posted_at` (first 10 chars)
  - `id` (int) → cast to str → `id`
  - `remote: True` always (RemoteOK is remote-only)
- On HTTP error or timeout (15s): log warning, return `[]` (non-fatal — Remotive still runs).

Existing `fetch_jobs()` (Remotive) is unchanged.

### `src/job_matcher/nodes/fetch.py`

Replace sequential Remotive-only call with parallel fetch:

```python
with ThreadPoolExecutor(max_workers=2) as pool:
    remotive_future = pool.submit(fetch_jobs, base_url)
    remoteok_future = pool.submit(fetch_remoteok)
    remotive_jobs = remotive_future.result()
    remoteok_jobs = remoteok_future.result()

raw = remotive_jobs + remoteok_jobs

# Deduplicate by apply_url (preserves first occurrence)
seen_urls: set[str] = set()
deduped = []
for job in raw:
    url = job.get("apply_url", "")
    if url and url not in seen_urls:
        seen_urls.add(url)
        deduped.append(job)

# Existing cache.json dedup by id
seen_ids = load_cache()
new_jobs = [j for j in deduped if j["id"] not in seen_ids]
seen_ids.update(j["id"] for j in new_jobs)
save_cache(seen_ids)
return {"raw_jobs": new_jobs}
```

### `src/job_matcher/models.py`

Add `ScoreBreakdown` model and update `ScoredJob`:

```python
class ScoreBreakdown(BaseModel):
    stack: float      # 0–40
    seniority: float  # -20–20
    ai_bonus: float   # 0–20
    recency: float    # 0–20

class ScoredJob(BaseModel):
    job: Job
    extracted: ExtractedJob
    score: float
    breakdown: ScoreBreakdown
    discard_reason: str | None = None
```

`breakdown` is always populated (never None). Discarded jobs from filter_node do not go through score_node so they never get a breakdown.

### `src/job_matcher/nodes/score.py`

`score_job()` signature change:

```python
def score_job(
    extracted: ExtractedJob, profile: ProfileData, today: date
) -> tuple[float, ScoreBreakdown]:
    stack = _stack_score(extracted, profile.preferred_keywords)
    seniority = _seniority_score(extracted)
    ai_bonus = _ai_bonus(extracted)
    recency = _recency_score(extracted, today)
    total = max(-20.0, min(100.0, stack + seniority + ai_bonus + recency))
    return total, ScoreBreakdown(stack=stack, seniority=seniority, ai_bonus=ai_bonus, recency=recency)
```

The four `_*_score` helper functions are unchanged.

`score_node` unpacks the tuple and builds `ScoredJob` with `breakdown`.

### `backend/routers/jobs.py`

In the rank node SSE payload, add `score_breakdown` and `description` (currently missing from the payload):

```python
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
    "description": j.job.description,   # NEW — required by JobModal
}
```

Both additions are additive — existing SSE consumers that ignore these fields continue working.

---

## Frontend Changes

### `web/src/components/JobModal.tsx` (new)

Slide-over drawer from the right. Structure:
- Overlay backdrop (semi-transparent, closes modal on click)
- Panel: fixed right, full height, width `max-w-lg`, scrollable
- Header: title, company, date, close button (×)
- Score: large colored number + label
- **Score breakdown**: 4 horizontal bars labeled Stack / Seniority / AI Bonus / Recency
  - Each bar: label left, value right, filled bar proportional to max (40/40/20/20)
  - Seniority bar: can be negative (shown in red if < 0)
- Skills: flex-wrap chip list (all skills, not truncated to 5)
- Description: `whitespace-pre-wrap`, scrollable, `max-h-96 overflow-y-auto`
- Apply button: full-width at bottom, `rel="noopener noreferrer" target="_blank"`
- Accessibility: `role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing to title id
- Keyboard: Escape closes modal (useEffect event listener)

Props: `job: Job | null`, `onClose: () => void`

### `web/src/components/ScoreFilter.tsx` (new)

Three toggle buttons: **All** | **≥70** | **≥40**

Props: `value: 'all' | 70 | 40`, `onChange: (v: 'all' | 70 | 40) => void`

Changing filter resets page to 1 (handled in parent).

### `web/src/components/JobCard.tsx` (modified)

Add `onSelect: (job: Job) => void` prop. Wrap card content in `<button>` with `onClick={() => onSelect(job)}`. Visual appearance unchanged. Add `cursor-pointer` and `focus:ring-2 focus:ring-indigo-500` for accessibility.

### `web/src/app/page.tsx` (modified)

New state:
```typescript
const [selectedJob, setSelectedJob] = useState<Job | null>(null)
const [currentPage, setCurrentPage] = useState(1)
const [scoreFilter, setScoreFilter] = useState<'all' | 70 | 40>('all')
const JOBS_PER_PAGE = 8
```

Derived values (not state):
```typescript
const filteredJobs = scoreFilter === 'all' ? jobs : jobs.filter(j => j.score >= scoreFilter)
const totalPages = Math.ceil(filteredJobs.length / JOBS_PER_PAGE)
const visibleJobs = filteredJobs.slice((currentPage - 1) * JOBS_PER_PAGE, currentPage * JOBS_PER_PAGE)
```

Changing `scoreFilter` resets `currentPage` to 1.

Render order below results heading:
1. `<ScoreFilter value={scoreFilter} onChange={(v) => { setScoreFilter(v); setCurrentPage(1) }} />`
2. Job grid (uses `visibleJobs`)
3. Pagination controls: "← Anterior" / "Página N de M" / "Siguiente →" — hidden when `totalPages <= 1`
4. `<JobModal job={selectedJob} onClose={() => setSelectedJob(null)} />`

---

## Job Type Extension

The `Job` interface in the frontend gains `score_breakdown`:

```typescript
interface ScoreBreakdown {
  stack: number
  seniority: number
  ai_bonus: number
  recency: number
}

interface Job {
  score: number
  score_breakdown: ScoreBreakdown
  title: string
  company: string
  posted_at: string
  apply_url: string
  skills: string[]
  seniority: string | null
  description: string   // added — already in SSE but not previously used in UI
}
```

`description` is NOT currently in the SSE payload — it must be added to `jobs.py` (see Backend Changes above) and to the frontend Job type.

---

## Testing

### Backend

**`tests/test_pipeline.py`** — add:
- `test_fetch_remoteok_normalizes_fields`: mock `requests.get` returning sample RemoteOK JSON, assert `title`, `apply_url`, `remote=True`, `id` mapped correctly.
- `test_fetch_node_parallel_merge`: mock both `fetch_jobs` and `fetch_remoteok`, assert results merged and deduplicated.
- `test_fetch_node_deduplicates_by_url`: two jobs with same `apply_url` from different sources → only one survives.
- `test_extract_node_uses_llm_structured_output`: update to unpack `(score, breakdown)` tuple (existing test).

**`tests/test_score.py`** — all 8 existing tests: update calls to `score_job()` to unpack tuple `score, breakdown = score_job(...)`. Add:
- `test_score_breakdown_components_sum_to_total`: verify `breakdown.stack + breakdown.seniority + breakdown.ai_bonus + breakdown.recency` clipped to [-20, 100] equals `score`.

### Frontend (Playwright E2E)

Add to `web/tests/e2e/home.spec.ts`:
- `test_job_card_click_opens_modal`: mock SSE with 1 job, click card, assert modal visible with title.
- `test_modal_closes_on_backdrop_click`: open modal, click backdrop, assert modal gone.
- `test_score_filter_hides_low_jobs`: mock SSE with jobs of score 80 and 30, select ≥70 filter, assert only 1 card visible.
- `test_pagination_shows_next_page`: mock SSE with 10 jobs, assert page 1 shows 8, click Siguiente, assert page 2 shows 2.

---

## Non-Goals

- No server-side pagination (all jobs already in client memory after SSE completes).
- No filter by source platform (Remotive vs RemoteOK) — score filter covers the useful case.
- No HackerNews integration (deferred — needs scraping, higher complexity).
- No changes to MongoDB schema — `pipeline_runs` analytics continue unchanged.
- No authentication on RemoteOK API (public endpoint, no key needed).
