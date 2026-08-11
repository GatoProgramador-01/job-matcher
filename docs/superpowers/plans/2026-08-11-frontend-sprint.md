# Frontend Sprint — Job Matcher Web UI

## Goal
Next.js 15 frontend + FastAPI SSE backend that exposes the existing LangGraph pipeline over HTTP with live progress streaming.

## Repo
`C:\Users\lanitaEmperadora\Documents\github\job-matcher`
Branch: `feat/job-matcher-frontend`
venv: `.venv\Scripts\` (Python 3.12, uv)

## Architecture
Browser → Next.js (web/) → API route → FastAPI (backend/) → LangGraph pipeline → SSE stream back

## Task A — frontend-expert: web/ directory

### Files to create

**`web/package.json`**
```json
{
  "name": "job-matcher-web",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev --port 3000",
    "build": "next build",
    "start": "next start --port 3000"
  },
  "dependencies": {
    "next": "15.3.3",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@types/node": "^22",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "typescript": "^5",
    "tailwindcss": "^4",
    "@tailwindcss/postcss": "^4"
  }
}
```

**`web/tsconfig.json`**
```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

**`web/next.config.ts`**
```ts
import type { NextConfig } from 'next'
const config: NextConfig = { reactStrictMode: true }
export default config
```

**`web/postcss.config.mjs`**
```js
const config = { plugins: { '@tailwindcss/postcss': {} } }
export default config
```

**`web/src/app/globals.css`**
```css
@import "tailwindcss";
```

**`web/src/app/layout.tsx`**
```tsx
import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Job Matcher',
  description: 'Personal job matcher powered by LangGraph + DeepSeek',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-gray-950 text-gray-100 min-h-screen">
        {children}
      </body>
    </html>
  )
}
```

**`web/src/components/JobCard.tsx`**
```tsx
interface Job {
  score: number
  title: string
  company: string
  posted_at: string
  apply_url: string
  skills: string[]
  seniority: string | null
}

export function JobCard({ job, rank }: { job: Job; rank: number }) {
  const scoreColor =
    job.score >= 70 ? 'text-green-400' :
    job.score >= 40 ? 'text-yellow-400' : 'text-red-400'

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex flex-col gap-3 hover:border-gray-600 transition-colors">
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
          className="bg-indigo-600 hover:bg-indigo-500 text-white text-sm px-3 py-1.5 rounded-lg transition-colors"
        >
          Apply →
        </a>
      </div>
    </div>
  )
}
```

**`web/src/components/PipelineStatus.tsx`**
```tsx
const NODES = ['fetch', 'filter', 'extract', 'score', 'rank'] as const
type NodeName = typeof NODES[number]

const NODE_LABELS: Record<NodeName, string> = {
  fetch: 'Fetching jobs',
  filter: 'Filtering',
  extract: 'AI extraction',
  score: 'Scoring',
  rank: 'Ranking',
}

interface Props {
  activeNode: string | null
  doneNodes: string[]
}

export function PipelineStatus({ activeNode, doneNodes }: Props) {
  return (
    <div className="flex items-center gap-2 py-4">
      {NODES.map((node, i) => {
        const done = doneNodes.includes(node)
        const active = activeNode === node
        return (
          <div key={node} className="flex items-center gap-2">
            <div className="flex flex-col items-center gap-1">
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all
                ${done ? 'bg-green-500 text-white' : active ? 'bg-indigo-500 text-white animate-pulse' : 'bg-gray-800 text-gray-500'}`}>
                {done ? '✓' : i + 1}
              </div>
              <span className="text-xs text-gray-500 whitespace-nowrap">{NODE_LABELS[node]}</span>
            </div>
            {i < NODES.length - 1 && (
              <div className={`h-0.5 w-8 mb-4 transition-colors ${done ? 'bg-green-500' : 'bg-gray-800'}`} />
            )}
          </div>
        )
      })}
    </div>
  )
}
```

**`web/src/app/page.tsx`**
```tsx
'use client'

import { useState } from 'react'
import { JobCard } from '@/components/JobCard'
import { PipelineStatus } from '@/components/PipelineStatus'

interface Job {
  score: number
  title: string
  company: string
  posted_at: string
  apply_url: string
  skills: string[]
  seniority: string | null
}

type Status = 'idle' | 'running' | 'done' | 'error'

export default function Home() {
  const [status, setStatus] = useState<Status>('idle')
  const [activeNode, setActiveNode] = useState<string | null>(null)
  const [doneNodes, setDoneNodes] = useState<string[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [error, setError] = useState<string | null>(null)

  async function runMatcher() {
    setStatus('running')
    setActiveNode(null)
    setDoneNodes([])
    setJobs([])
    setError(null)

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
          if (data.node) setActiveNode(data.node)
          if (data.done_node) setDoneNodes(prev => [...prev, data.done_node])
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
      <div className="mb-10">
        <h1 className="text-3xl font-bold text-white">Job Matcher</h1>
        <p className="text-gray-400 mt-1">
          LangGraph + DeepSeek · hiring.cafe · top 10 jobs ranked for your profile
        </p>
      </div>

      <div className="flex flex-col items-center gap-6 mb-10">
        <button
          onClick={runMatcher}
          disabled={status === 'running'}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed
            text-white font-semibold px-8 py-3 rounded-xl text-lg transition-colors"
        >
          {status === 'running' ? 'Running pipeline…' : 'Find matching jobs'}
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
          <h2 className="text-lg font-semibold text-gray-300 mb-4">
            Top {jobs.length} matches
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {jobs.map((job, i) => (
              <JobCard key={job.apply_url} job={job} rank={i + 1} />
            ))}
          </div>
        </div>
      )}
    </main>
  )
}
```

**`web/src/app/api/run/route.ts`**
```ts
import { NextRequest } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000'

export async function POST(_req: NextRequest) {
  const upstream = await fetch(`${BACKEND_URL}/api/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_path: 'profile.json' }),
  })

  if (!upstream.ok || !upstream.body) {
    return new Response('Backend error', { status: 502 })
  }

  return new Response(upstream.body, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'X-Accel-Buffering': 'no',
    },
  })
}
```

### Steps (frontend-expert)

1. Create all files above under `web/`.
2. `cd web && npm install`
3. `npm run build` — must succeed with 0 errors.
4. Commit:
   ```
   git add web/
   git commit -m "feat: add Next.js 15 frontend — JobCard, PipelineStatus, SSE consumer"
   git push
   ```

Report: build success/fail, commit SHA.

---

## Task B — backend-expert: backend/ directory

### Files to create

**`backend/__init__.py`** — empty

**`backend/main.py`**
```python
import sys
from pathlib import Path

# allow importing job_matcher from parent/src
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers.jobs import router

app = FastAPI(title="Job Matcher API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

**`backend/routers/__init__.py`** — empty

**`backend/routers/jobs.py`**
```python
import json
import os
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from job_matcher.pipeline import build_pipeline
from job_matcher.profile import load_profile

router = APIRouter()


class RunRequest(BaseModel):
    profile_path: str = "profile.json"


def _safe_profile_path(raw: str) -> Path:
    requested = Path(raw).resolve()
    base = Path(".").resolve()
    if not str(requested).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Invalid profile path")
    if not requested.exists():
        raise HTTPException(status_code=404, detail=f"Profile not found: {raw}")
    return requested


async def _stream_pipeline(profile_path: str) -> AsyncGenerator[str, None]:
    path = _safe_profile_path(profile_path)
    profile = load_profile(str(path))
    pipeline = build_pipeline()

    initial_state = {
        "profile": profile,
        "raw_jobs": [],
        "filtered_jobs": [],
        "extracted_jobs": [],
        "scored_jobs": [],
        "top_jobs": [],
        "output_format": "json",
    }

    node_order = ["fetch", "filter", "extract", "score", "rank"]

    for event in pipeline.stream(initial_state):
        node_name = next(iter(event))
        state = event[node_name]

        yield f"data: {json.dumps({'node': node_name})}\n\n"

        if node_name == "rank":
            top = state.get("top_jobs", [])
            jobs_payload = [
                {
                    "score": round(j.score, 1),
                    "title": j.job.title,
                    "company": j.job.company,
                    "posted_at": str(j.job.posted_at) if j.job.posted_at else None,
                    "apply_url": j.job.apply_url,
                    "skills": j.extracted.required_skills,
                    "seniority": j.extracted.seniority,
                }
                for j in top
            ]
            yield f"data: {json.dumps({'done_node': node_name, 'jobs': jobs_payload})}\n\n"
        else:
            yield f"data: {json.dumps({'done_node': node_name})}\n\n"


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

### Steps (backend-expert)

1. Create all files above.
2. Install fastapi + uvicorn into the project venv:
   ```
   .venv\Scripts\pip install "fastapi>=0.115" "uvicorn[standard]>=0.30"
   ```
3. Test the app can be imported (no import errors):
   ```
   .venv\Scripts\python -c "from backend.main import app; print('OK')"
   ```
4. Run existing tests still pass:
   ```
   .venv\Scripts\pytest tests/ -q
   ```
5. Commit:
   ```
   git add backend/ pyproject.toml
   git commit -m "feat: add FastAPI backend with SSE /api/run endpoint"
   git push
   ```

Report: import test result, pytest result, commit SHA.

---

## Task C — security-reviewer: read-only audit

Audit the job-matcher repo at `C:\Users\lanitaEmperadora\Documents\github\job-matcher`.

Check:
1. `.gitignore` covers `.env`, `profile.json`, `cache.json`
2. No real API keys in any committed file (`git log --all -S "sk-"`)
3. `backend/routers/jobs.py` has path traversal protection on `profile_path`
4. CORS allows only `localhost:3000`, not wildcard
5. `apply_url` in JobCard uses `rel="noopener noreferrer"` (XSS)
6. No `print()` or `logging` that leaks env vars
7. `DEEPSEEK_API_KEY` only loaded from `os.environ`, never from default string
8. Git history: `git log --all --oneline -- "*.env"` and `git log --all --oneline -- "profile.json"`

Produce a structured report:
```
PASS/FAIL per check
Overall: PASS or FAIL
Findings: list of specific file:line issues (if any)
Recommendations: prioritized (Critical/High/Medium/Low)
```

Do NOT modify any files. Read-only.
