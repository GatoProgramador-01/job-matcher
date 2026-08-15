# Evals + LangSmith Integration — Design Spec
**Date:** 2026-08-14  
**Project:** job-matcher  
**Status:** Approved

---

## 1. Goals

1. Add a two-layer evaluation harness (extraction accuracy + end-to-end ranking quality) exportable to LangSmith Experiments.
2. Enrich all node docstrings so each node is self-documenting.
3. Write `docs/architecture.md` explaining pipeline design, scoring formula, caching strategy, and the eval layer — serves as course reference and portfolio artifact.

---

## 2. Scope Boundaries

**In scope:**
- `evals/` directory with datasets, evaluators, and runner scripts
- LangSmith tracing wired via env vars (no production code changes)
- Docstrings for all 5 nodes (`fetch`, `filter_`, `extract`, `score`, `rank`)
- `docs/architecture.md`
- `langsmith` added to `pyproject.toml` dependencies

**Out of scope:**
- LLM-as-judge evaluators (all evaluators are deterministic metrics)
- CI integration of evals (they run manually for now)
- Changing any production pipeline logic

---

## 3. Architecture Overview

### 3.1 Eval harness structure

```
evals/
  datasets/
    extraction_golden.jsonl     # 25 hand-crafted extraction examples
    ranking_golden.jsonl        # 5 profile+batch ranking scenarios
  evaluators/
    __init__.py
    extraction.py               # skill_overlap, seniority_match, remote_match, latam_match
    ranking.py                  # precision_at_3
  upload_datasets.py            # uploads JSONL to LangSmith Datasets API (run once)
  run_extraction_eval.py        # Layer 1 — langsmith.evaluate() on extract_node target
  run_ranking_eval.py           # Layer 2 — langsmith.evaluate() on full pipeline target
```

### 3.2 LangSmith tracing — zero production code changes

`langchain-openai` reads three env vars automatically:

```env
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=job-matcher
```

Once set, every `ChatOpenAI.invoke()` call in `extract_node` traces to LangSmith — prompt, completion, token counts, latency — with no decorator or wrapper needed. This covers both production pipeline runs and eval harness runs.

---

## 4. Dataset Schema

### 4.1 Layer 1 — Extraction (`evals/datasets/extraction_golden.jsonl`)

LangSmith JSONL convention: one JSON object per line with `inputs` and `outputs` keys.

```jsonl
{
  "inputs": {
    "id": "golden_001",
    "title": "Senior Python Backend Engineer",
    "description": "We are looking for a Senior Backend Engineer with Python, FastAPI, PostgreSQL. Fully remote. LATAM candidates welcome."
  },
  "outputs": {
    "required_skills": ["Python", "FastAPI", "PostgreSQL"],
    "seniority": "senior",
    "is_remote": true,
    "latam_eligible": true
  }
}
```

**25 examples covering:**
- Clean clear postings (baseline)
- Junior titles with `-20` seniority penalty trigger
- Ambiguous seniority ("experienced developer", no explicit label)
- LATAM-explicit ("LATAM candidates welcome") vs implicit (no mention)
- Skills buried in boilerplate / legal / footer text
- Non-remote with flexible-sounding language ("hybrid optional")
- AI-stack jobs (LangChain, RAG, LangGraph) for bonus coverage
- Multi-skill roles (10+ skills)
- Minimal descriptions (under 200 chars)

### 4.2 Layer 2 — Ranking (`evals/datasets/ranking_golden.jsonl`)

```jsonl
{
  "inputs": {
    "profile": {
      "preferred_keywords": ["Python", "LangChain", "FastAPI"],
      "reject_keywords": ["PHP", "Ruby"],
      "target_seniority": ["mid", "senior"],
      "avoid_seniority": ["junior", "staff"]
    },
    "jobs": [
      {"id": "j1", "title": "Senior Python LangChain Engineer", "description": "..."},
      {"id": "j2", "title": "Junior PHP Developer", "description": "..."},
      {"id": "j3", "title": "Mid-level FastAPI + PostgreSQL", "description": "..."},
      {"id": "j4", "title": "Staff Principal Architect", "description": "..."},
      {"id": "j5", "title": "Python Data Engineer", "description": "..."},
      {"id": "j6", "title": "Ruby on Rails Developer", "description": "..."},
      {"id": "j7", "title": "Senior LangGraph + RAG Engineer", "description": "..."},
      {"id": "j8", "title": "Entry Level Python Dev", "description": "..."}
    ]
  },
  "outputs": {
    "expected_top_ids": ["j1", "j7", "j3"]
  }
}
```

**5 scenarios covering:**
- AI-stack bonus triggers correctly rank LangChain/RAG jobs higher
- Junior and Staff seniority penalties correctly suppress bad fits
- Reject keywords (PHP, Ruby) drop those jobs regardless of other signals
- Recency tie-breaking (two equally-scored jobs, newer one wins)
- All-bad-batch (no good fit exists — top should be the least-bad, not crash)

---

## 5. Evaluator Logic

### 5.1 Layer 1 — `evals/evaluators/extraction.py`

All evaluators use the LangSmith `(outputs, reference_outputs) -> dict` signature.

| Evaluator | Metric | Formula |
|---|---|---|
| `skill_overlap` | Jaccard similarity | `|predicted ∩ golden| / |predicted ∪ golden|` (case-insensitive) |
| `seniority_match` | Exact match | `1.0` if equal, `0.0` otherwise |
| `remote_match` | Exact match | `1.0` if equal, `0.0` otherwise |
| `latam_match` | Exact match | `1.0` if equal, `0.0` otherwise |

Thresholds for passing (informational, not enforced as hard gates):
- `skill_overlap` ≥ 0.5 — Jaccard of 0.5 means half the union is correct
- `seniority_match` = 1.0 — seniority is binary: right or wrong
- `remote_match` = 1.0
- `latam_match` ≥ 0.8 — slight tolerance since LATAM inference is harder

### 5.2 Layer 2 — `evals/evaluators/ranking.py`

| Evaluator | Metric | Formula |
|---|---|---|
| `precision_at_3` | Precision@k | `hits in top-3 / len(expected_top_ids)` |

A score of `1.0` means every expected job appeared in the pipeline's top 3 results.

---

## 6. Runner Scripts

### 6.1 `evals/upload_datasets.py` — run once per dataset version

```python
from langsmith import Client
# Reads JSONL files → creates/updates LangSmith datasets
# Dataset names: "job-matcher-extraction-v1", "job-matcher-ranking-v1"
# Re-run whenever examples are added or corrected.
```

### 6.2 `evals/run_extraction_eval.py`

```python
from langsmith import evaluate
from job_matcher.nodes.extract import _extract_uncached_job
from job_matcher.infrastructure.deepseek import make_llm

def extraction_target(inputs: dict) -> dict:
    job = Job(id=inputs["id"], title=inputs["title"],
              description=inputs["description"], apply_url="https://eval.local")
    # _extract_uncached_job intentionally bypasses MongoDB cache so the LLM
    # always runs — eval measures live model behavior, not cached results.
    extracted, _, _ = _extract_uncached_job(job, make_llm())
    return {
        "required_skills": extracted.required_skills,
        "seniority": extracted.seniority,
        "is_remote": extracted.is_remote,
        "latam_eligible": extracted.latam_eligible,
    }

results = evaluate(
    extraction_target,
    data="job-matcher-extraction-v1",
    evaluators=[skill_overlap, seniority_match, remote_match, latam_match],
    experiment_prefix="extraction",
    max_concurrency=3,
)
```

### 6.3 `evals/run_ranking_eval.py`

```python
def ranking_target(inputs: dict) -> dict:
    # Builds MatcherState from inputs["profile"] + inputs["jobs"]
    # Pre-populates state["filtered_jobs"] directly — skips fetch and filter nodes
    # since the dataset already provides the curated job batch to evaluate against.
    # Runs extract_node → score_node → rank_node.
    # Returns {"top_jobs": [{"id": ..., "score": ...}, ...]}
    ...

results = evaluate(
    ranking_target,
    data="job-matcher-ranking-v1",
    evaluators=[precision_at_3],
    experiment_prefix="ranking",
)
```

---

## 7. Documentation Plan

### 7.1 Node docstrings — `src/job_matcher/nodes/*.py`

Each node gets a module-level docstring with:
- What it does (one sentence)
- `Reads:` — which `MatcherState` keys it consumes
- `Writes:` — which keys it produces
- `Side effects:` — MongoDB reads/writes, LLM calls, HTTP calls
- `Failure modes:` — what breaks and how it fails gracefully

Nodes to update: `fetch.py`, `filter_.py`, `extract.py` (upgrade existing), `score.py`, `rank.py`

### 7.2 Architecture doc — `docs/architecture.md`

Six sections:

| Section | Purpose |
|---|---|
| Pipeline overview | Mermaid diagram: `fetch → filter → extract → score → rank` with data types at each edge |
| Node responsibilities | One paragraph per node explaining what it does and why it is a separate step |
| Scoring formula | `score = stack(0–40) + seniority(−20/0/10/20) + ai_bonus(0/10/20) + recency(0/5/10/15/20)`, capped [−20, 100] |
| Caching strategy | MongoDB extraction cache keyed by `job_id`; why it matters (DeepSeek cost + 0ms latency on hit) |
| Eval layer | Two-layer eval, golden dataset structure, metrics, how to run, how to read LangSmith Experiments |
| LangSmith tracing | How auto-tracing works via env vars, what a trace contains, how to find experiments in the UI |

---

## 8. Dependencies

Add to `pyproject.toml`:

```toml
dependencies = [
    ...
    "langsmith>=0.1",
]
```

No other new dependencies. All evaluators are pure Python — no deepeval, no RAGAS.

---

## 9. File Checklist

| File | Action |
|---|---|
| `pyproject.toml` | Add `langsmith>=0.1` |
| `.env.example` | Add `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` |
| `evals/__init__.py` | Create (empty) |
| `evals/datasets/extraction_golden.jsonl` | Create — 25 golden examples |
| `evals/datasets/ranking_golden.jsonl` | Create — 5 scenarios |
| `evals/evaluators/__init__.py` | Create (empty) |
| `evals/evaluators/extraction.py` | Create — 4 evaluator functions |
| `evals/evaluators/ranking.py` | Create — precision_at_3 |
| `evals/upload_datasets.py` | Create — dataset uploader |
| `evals/run_extraction_eval.py` | Create — Layer 1 runner |
| `evals/run_ranking_eval.py` | Create — Layer 2 runner |
| `src/job_matcher/nodes/fetch.py` | Add module docstring |
| `src/job_matcher/nodes/filter_.py` | Add module docstring |
| `src/job_matcher/nodes/extract.py` | Upgrade module docstring |
| `src/job_matcher/nodes/score.py` | Add module docstring |
| `src/job_matcher/nodes/rank.py` | Add module docstring |
| `docs/architecture.md` | Create — 6-section architecture doc |
