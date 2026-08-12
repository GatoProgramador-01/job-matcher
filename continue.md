# Job Matcher — Sprint Handover & Continuation Guide (`continue.md`)

This document provides a comprehensive technical overview of the work completed, system architecture, active services, and suggested next steps for **Claude Code** or any agent taking over this workspace.

---

## 📍 Project Overview & Working Environment

* **Directory**: `C:\Users\lanitaEmperadora\Documents\github\job-matcher`
* **Repository**: `https://github.com/GatoProgramador-01/job-matcher`
* **Active Branch**: `master` (All features merged and pushed)
* **Python Environment**: `.venv\Scripts\python.exe` (Python 3.12)
* **Node Environment**: `web/` directory (Next.js 15, React 19, TypeScript, Tailwind CSS)
* **Database**: MongoDB running locally at `mongodb://localhost:27017` (Database: `job_matcher`)

---

## ✅ Completed Tasks & Achievements

### 1. **Next.js 15 Frontend & Real-time SSE Stream**
* **SSE Proxy Route**: `web/src/app/api/run/route.ts` pipes backend SSE event streams (`text/event-stream`) using an explicit `ReadableStream` reader loop.
* **UI Components**:
  * `web/src/app/page.tsx`: Main page with animated pipeline status, job list, and **real-time Token Usage & MongoDB Cache Hits Dashboard**.
  * `web/src/components/JobCard.tsx`: Displays job rank, score (green $\ge 70$, yellow $\ge 40$, red $< 40$), company, title, extracted skills, and secure `rel="noopener noreferrer"` Apply links.
  * `web/src/components/PipelineStatus.tsx`: Animated step progress indicators (`fetch` $\rightarrow$ `filter` $\rightarrow$ `extract` $\rightarrow$ `score` $\rightarrow$ `rank`).

### 2. **FastAPI Backend & LangGraph Pipeline**
* **FastAPI Server**: `backend/main.py` with CORS middleware allowed for `http://localhost:3000` and startup warnings for missing `DEEPSEEK_API_KEY`.
* **Jobs Router**: `backend/routers/jobs.py` exposes `POST /api/run` (SSE streaming) and `GET /api/profile`.
* **LangGraph Nodes**:
  * `fetch_node`: Pulls listings across 3 Remotive tech categories (`software-dev`, `devops-sysadmin`, `data`). Saves raw jobs to MongoDB.
  * `filter_node`: Rejects non-engineering titles (sales, marketing, copywriter, designer, patient care, medical, etc.) and non-remote roles.
  * `extract_node`: Extracts technical skills, seniority, and remote eligibility using DeepSeek Chat API.
  * `score_node`: Evaluates jobs against profile preferred keywords, seniority targets, AI/GenAI stack bonuses, and posting recency.
  * `rank_node`: Sorts and truncates to top N matches.

### 3. **MongoDB Storage & Caching Layer (`src/job_matcher/mongo.py`)**
* **Connection**: Connects via `pymongo` to `mongodb://localhost:27017` (DB: `job_matcher`).
* **Collections**:
  * `raw_jobs`: Stores raw scraped job documents indexed by `id`.
  * `extractions`: Caches LLM extraction results indexed by `job_id`.
  * `pipeline_runs`: Analytics database recording every run: timestamp, profile name, jobs count, prompt tokens, completion tokens, USD cost, and cache savings.

### 4. **Token Optimization & Tracking (`src/job_matcher/token_tracker.py`)**
* **HTML Cleaning**: `BeautifulSoup` strips HTML tags to plain text before constructing prompts.
* **Payload Truncation**: Truncates job descriptions to **1,200 characters max**, eliminating footer boilerplate and saving ~60% of prompt tokens.
* **MongoDB LLM Cache Hits**: Checks MongoDB before calling DeepSeek. Cached jobs return instantly (**0 API tokens, 0ms latency**).
* **Parallel Execution**: Uses `concurrent.futures.ThreadPoolExecutor(max_workers=5)` for parallel uncached LLM calls.
* **Cost Accounting**: Calculates exact DeepSeek USD pricing ($0.14/1M input tokens, $1.10/1M output tokens) and estimates saved USD per cache hit.

### 5. **Playwright E2E Test Suite (`web/tests/e2e/home.spec.ts`)**
* **Config**: `web/playwright.config.ts` configured with `channel: 'chromium'` to avoid Windows headless-shell ICU crash.
* **Test Results**: **8 passed, 1 skipped** (100% green build).
  * Unit E2E specs mock SSE events to test idle button, pipeline animation, step progression, error handling, job card rendering, security attributes, and score color thresholds.

---

## 🛠️ Essential Developer Commands

### Start Backend (FastAPI - Port 8000)
```powershell
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### Start Frontend (Next.js - Port 3000)
```powershell
cd web
npm run dev
```

### Run Playwright E2E Tests
```powershell
cd web
npx playwright test
```

### Verify TypeScript Types
```powershell
cd web
node_modules\.bin\tsc --noEmit
```

### Inspect MongoDB Collections (Python)
```powershell
.venv\Scripts\python.exe -c "import pymongo; client=pymongo.MongoClient('mongodb://localhost:27017'); db=client['job_matcher']; print('raw_jobs:', db.raw_jobs.count_documents({})); print('extractions:', db.extractions.count_documents({})); print('runs:', db.pipeline_runs.count_documents({}))"
```

---

## 📋 Suggested Future Backlog / Next Steps

1. **Multi-Source Job Aggregation**:
   * Add support for additional free job APIs (e.g. RemoteOK, Jobspipe, GitHub Jobs mirrors, or HackerNews Who is Hiring API) alongside Remotive.
2. **Profile Editor UI**:
   * Add a visual profile manager page in Next.js (`/profile`) allowing users to edit `profile.json` keywords, target seniority, and rejection rules directly from the browser.
3. **Automated Alerts / Webhooks**:
   * Integrate Discord / Slack / Email webhooks to notify the user whenever a new job scores $\ge 70$.
4. **Pagination & Detailed Job Modal**:
   * Support pagination / filter by score range on the frontend, and add a slide-over drawer modal showing full job descriptions and match score breakdown explanations.
