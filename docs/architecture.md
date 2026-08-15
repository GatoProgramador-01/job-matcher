# Job Matcher — Architecture

## Pipeline Overview

The pipeline is a five-node LangGraph `StateGraph`. Each node reads from and writes to `MatcherState`, a `TypedDict` shared across the entire run.

```mermaid
graph LR
    A[fetch_node] -->|list[dict]| B[filter_node]
    B -->|list[Job]| C[extract_node]
    C -->|list[ExtractedJob]| D[score_node]
    D -->|list[ScoredJob]| E[rank_node]
    E -->|list[ScoredJob] top 10| F[MatcherState.top_jobs]

    C <-->|cache hit/miss| G[(MongoDB extractions)]
    A -->|upsert| H[(MongoDB raw_jobs)]
    A --> I[(cache.json)]
```

Data type at each edge:

| Edge | Type | Description |
|---|---|---|
| fetch -> filter | `list[dict]` | Raw JSON from Remotive + RemoteOK APIs |
| filter -> extract | `list[Job]` | Validated Pydantic Job objects, all passed hard filters |
| extract -> score | `list[ExtractedJob]` | Jobs with required_skills, seniority, is_remote, latam_eligible |
| score -> rank | `list[ScoredJob]` | Jobs with score (float) and breakdown (per-component scores) |
| rank -> output | `list[ScoredJob]` | Top 10 by score, descending |

## Node Responsibilities

**fetch_node** — Fetches job listings in parallel from two sources: Remotive API (three tech categories: software-dev, devops-sysadmin, data) and RemoteOK API. Deduplicates by `apply_url`. Saves raw jobs to MongoDB `raw_jobs` collection and updates the local `cache.json` seen-IDs set.

**filter_node** — Applies three hard rules in sequence: (1) rejects clearly non-engineering titles (sales, marketing, medical, etc.), (2) rejects jobs containing any profile `reject_keyword`, (3) rejects jobs with no remote signal in title/description/location. No LLM calls. Fast, cheap, runs before extraction to minimize DeepSeek API usage.

**extract_node** — Calls DeepSeek Chat API to extract structured fields from each job posting: `required_skills`, `seniority`, `is_remote`, `latam_eligible`. Checks MongoDB `extractions` cache first — a cache hit returns instantly at zero token cost. Cache misses run in parallel threads (max 5). HTML is stripped and descriptions truncated to 1,200 chars before the LLM prompt is constructed.

**score_node** — Applies a deterministic scoring formula (no LLM). Produces a float score in `[-20, 100]` and a `ScoreBreakdown` showing each component. See Scoring Formula below.

**rank_node** — Sorts `scored_jobs` descending by score, takes the top 10, and returns `top_jobs`. Also prints results to stdout in table or JSON format for CLI usage.

## Scoring Formula

```
score = stack + seniority + ai_bonus + recency
score = clamp(score, min=-20.0, max=100.0)
```

**stack (0 to 40 pts):** Keyword match against `profile.preferred_keywords`. A keyword found in the job title scores 3 points; in the body or extracted skills scores 1 point. Raw points are scaled to a max of 40.

**seniority (-20 / 0 / +10 / +20):**
- `junior`, `trainee`, `intern`, `entry level`, `entry-level` -> **-20**
- `mid-level`, `mid level`, `semi-senior`, `ssr`, `semi senior`, `midlevel` -> **+20**
- `senior` (not `staff`, `principal`, `lead`, `architect`, `head of`) -> **+10**
- Anything else -> **0**

**ai_bonus (0 / +10 / +20):**
- Tier A terms in title or description (`langgraph`, `multi-agent`, `anthropic`, `rag`, `agentic`, `vector search`, `langchain`) -> **+20**
- Tier B terms (`openai`, `llm`, `machine learning`, `embedding`, ` ai `) -> **+10**
- None -> **0**

**recency (0 to 20 pts):**
- Posted today -> **+20**
- Posted 3 days ago or less -> **+15**
- Posted 7 days ago or less -> **+10**
- Posted 14 days ago or less -> **+5**
- Older or posted_at is null -> **0**

## Caching Strategy

The MongoDB `extractions` collection is an LLM result cache keyed by `job_id`. On a cache hit, `extract_node` returns the stored `required_skills`, `seniority`, `is_remote`, and `latam_eligible` fields with zero API tokens consumed and near-zero latency. On a cache miss, the LLM is called and the result is stored for future runs.

Why this matters: DeepSeek costs $0.14/1M input tokens and $1.10/1M completion tokens. A typical job description consumes roughly 400-600 prompt tokens. Without caching, extracting 100 jobs costs around $0.05-0.07 per run. With a warm cache (second run of the same job listing), cost drops to $0.

Cache key hygiene: job IDs from Remotive and RemoteOK are stable across API calls for the same listing. A job that reappears in next week's fetch hits the cache automatically.

## Eval Layer

The eval harness lives in `evals/` and measures two properties of the pipeline:

**Layer 1 — Extraction accuracy:** DeepSeek is evaluated against 25 hand-crafted golden examples covering common and edge-case job postings. Four metrics are computed per example:

| Metric | Formula | What it measures |
|---|---|---|
| `skill_overlap` | Jaccard(predicted, golden) | How well the LLM identifies the correct skill set |
| `seniority_match` | Exact match | Whether the LLM correctly labels seniority level |
| `remote_match` | Exact match | Whether the LLM correctly identifies remote eligibility |
| `latam_match` | Exact match | Whether the LLM correctly identifies LATAM eligibility |

**Layer 2 — Ranking quality:** Five profile+job-batch scenarios test whether the pipeline returns the expected jobs in its top 3. Metric: `precision@3 = hits_in_top3 / len(expected_top_ids)`.

**Running evals:**
```bash
# Upload datasets once (or after adding examples)
.venv\Scripts\python.exe evals/upload_datasets.py

# Layer 1 — extraction accuracy (~$0.003, ~3 min)
.venv\Scripts\python.exe evals/run_extraction_eval.py

# Layer 2 — ranking quality (~$0.002, ~3 min)
.venv\Scripts\python.exe evals/run_ranking_eval.py
```

## LangSmith Tracing

Every `ChatOpenAI.invoke()` call in `extract_node` is automatically traced to LangSmith when these three env vars are set (no code changes required):

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=job-matcher
```

A trace captures: the full prompt sent to DeepSeek, the raw completion, token counts, latency, and any errors. Traces from production pipeline runs appear under the `job-matcher` project in LangSmith. Eval runs create separate **Experiments** entries, allowing you to compare extraction quality across DeepSeek model versions or prompt changes over time.

To find your results: open smith.langchain.com, select project `job-matcher`, then click the Experiments tab.
