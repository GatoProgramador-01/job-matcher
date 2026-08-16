# Job Matcher — Eval System

This document explains the two-layer evaluation harness: how the golden datasets are structured, how each metric is computed, how results are exported to LangSmith, and how to run and interpret experiments.

---

## Why Three Layers

The pipeline has three distinct failure modes requiring different measurement approaches:

| Layer | Failure caught | Method | Cost/run | When to run |
|---|---|---|---|---|
| 1 — Extraction accuracy | DeepSeek extracts wrong skills / seniority | Deterministic (Jaccard + exact match) | ~$0.003 | Every PR |
| 2 — Ranking quality | Scoring formula surfaces wrong jobs | Deterministic (precision@3) | ~$0.002 | Every PR |
| 3 — Semantic correctness | Right jobs ranked but wrong reasoning visible | LLM-as-judge (DeepSeek-chat) | ~$0.01 | Nightly / on demand |

Layer 1 catches model regressions (prompt drift, DeepSeek version changes). Layer 2 catches scoring formula bugs and weight calibration issues. Layer 3 catches failures that are numerically correct but semantically wrong — a case where `precision_at_3 = 1.0` but the model got lucky by coincidence. Layer 3 runs in LangSmith's **Evaluator Playground**, not in code.

---

## Directory Layout

```
evals/
├── datasets/
│   ├── extraction_golden.jsonl   # 25 hand-crafted extraction examples
│   └── ranking_golden.jsonl      # 5 end-to-end ranking scenarios (IDs prefixed s1-/s2-..)
├── evaluators/
│   ├── extraction.py             # skill_overlap, seniority_match, remote_match, latam_match
│   └── ranking.py                # precision_at_3
├── upload_datasets.py            # pushes both JSONL files to LangSmith as named Datasets
├── run_extraction_eval.py        # Layer 1 runner
├── run_ranking_eval.py           # Layer 2 runner
└── run_ranking_llm_eval.py       # Layer 3 runner (LLM-as-judge via DeepSeek-chat)
```

---

## Golden Datasets

Both datasets use the same JSONL format LangSmith expects:

```json
{"inputs": { ... }, "outputs": { ... }}
```

Each line is one example. `inputs` is what the target function receives; `outputs` is the ground-truth the evaluator compares against.

### extraction_golden.jsonl — 25 examples

Each example is a single job posting with its known-correct extraction result.

```json
{
  "inputs": {
    "id": "g001",
    "title": "Senior Python Backend Engineer",
    "description": "We need a Senior Python Backend Engineer with FastAPI, PostgreSQL, Docker. 5+ years experience. 100% remote worldwide. LATAM candidates welcome."
  },
  "outputs": {
    "required_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
    "seniority": "senior",
    "is_remote": true,
    "latam_eligible": true
  }
}
```

The 25 examples cover deliberate edge cases:

| Group | Examples | What is tested |
|---|---|---|
| Clear seniority signals | g001–g003 | senior/junior/mid from explicit phrases |
| Ambiguous seniority | g006 | "experienced developer" with no level keyword |
| LATAM explicit | g001, g008 | "LATAM candidates welcome" |
| LATAM implicit | g009 | timezone overlap language without naming LATAM |
| USA/Canada only | g004, g010 | remote=true but latam_eligible=false |
| Hybrid/on-site | g003, g011 | is_remote=false even though partial flexibility |
| Very short descriptions | g014 | 2-sentence posting, sparse signal |
| Staff/Principal | g005 | seniority="staff", not "senior" |
| LangGraph / AI-stack | g018 | AI bonus skills in description |
| Multi-skill role | g015 | 6+ required skills to test Jaccard breadth |
| Spanish SSR signal | g017 | "SSR" abbreviation for mid-level |

### ranking_golden.jsonl — 5 scenarios

Each scenario gives a `profile` (what the candidate wants) and a batch of 8 jobs, with the expected top job IDs.

```json
{
  "inputs": {
    "profile": {
      "preferred_keywords": ["Python", "LangChain", "FastAPI", "RAG"],
      "reject_keywords": [],
      "target_seniority": ["mid", "senior"],
      "avoid_seniority": ["junior", "staff"]
    },
    "jobs": [ ... 8 jobs ... ]
  },
  "outputs": {
    "expected_top_ids": ["s1-j1", "s1-j3"]
  }
}
```

The 5 scenarios each stress a different part of the scoring formula:

| Scenario | What it tests |
|---|---|
| 1 — Recency tie-break | Two identical-skill jobs; the one posted 10 days ago beats the 50-day-old one |
| 2 — Seniority penalties | junior and intern jobs score -20; staff/principal score -10 |
| 3 — AI-stack bonus | `preferred_keywords` matching LangChain/RAG triggers +10/+20 bonus |
| 4 — All-bad batch | No job is a strong match; system still ranks; score floor is meaningful |
| 5 — Mixed AI batch | LangChain/RAG jobs beat plain FastAPI even at the same seniority |

#### Job ID convention — why IDs are prefixed `s1-`, `s2-`, …

Every job ID in the ranking dataset is prefixed with its scenario number (e.g. `s2-j8`). This is a hard requirement, not a style choice.

**The bug that made this necessary:** the original dataset used plain IDs `j1`–`j8` across all five scenarios. The `extract_node` inside `ranking_target` writes extraction results to MongoDB keyed by job ID. When Scenario 1 ran first and cached `j8 → seniority=junior`, every subsequent scenario using ID `j8` received that wrong extraction from cache — even though Scenario 2's `j8` was a completely different job description ("Senior FastAPI Python Engineer"). The stale cache entry propagated a -20 seniority penalty into Scenario 2, pushing `j8` out of the top 3 and causing `precision_at_3 = 0.5` and a judge verdict of `false`.

The Layer 3 LLM judge caught this when the deterministic `precision_at_3` only flagged it as a score (0.5) without a reason. Inspecting the LangSmith trace showed `j8` with `seniority=junior` — clearly a cache hit from Scenario 1.

**Rule:** every job ID in `ranking_golden.jsonl` must be globally unique across all scenarios. The `sN-` prefix guarantees this. If you add a Scenario 6, use `s6-j1` through `s6-j8`.

---

## Evaluators

### Layer 1 — Extraction (`evals/evaluators/extraction.py`)

All four are deterministic — no LLM involved.

#### `skill_overlap` — Jaccard index

```
score = |predicted ∩ golden| / |predicted ∪ golden|
```

Both sets are lowercased before comparison. If both are empty, score = 1.0 (correct negative). A score of 0.5 means the model found half the right skills and/or hallucinated extras.

Example:
- Predicted: `{python, fastapi, redis}`
- Golden: `{python, fastapi, postgresql, docker}`
- Intersection: `{python, fastapi}` = 2
- Union: `{python, fastapi, redis, postgresql, docker}` = 5
- Score: `2/5 = 0.40`

#### `seniority_match` — exact match

```
score = 1.0 if predicted_seniority == golden_seniority else 0.0
```

Valid values: `"junior"`, `"mid"`, `"senior"`, `"staff"`, `None`. `None` means the description gives no seniority signal and the model should not hallucinate one.

#### `remote_match` — exact match

```
score = 1.0 if predicted_is_remote == golden_is_remote else 0.0
```

The tricky case is hybrid: "3 days in office" → `is_remote=False`, not `True`. The dataset includes several hybrid examples to catch this.

#### `latam_match` — exact match

```
score = 1.0 if predicted_latam_eligible == golden_latam_eligible else 0.0
```

`latam_eligible=True` requires either an explicit LATAM mention or a timezone range that covers South America. "Remote from USA or Canada only" → `latam_eligible=False` even though the job is remote.

---

### Layer 2 — Ranking (`evals/evaluators/ranking.py`)

#### `precision_at_3`

```
top_ids     = first 3 IDs from the ranked top_jobs list
expected    = set of expected_top_ids from the golden outputs
hits        = count of top_ids that appear in expected
score       = hits / len(expected)
```

The denominator is `len(expected)` (not 3), so the score reflects how many of the truly good jobs the pipeline surfaced, not just positional accuracy. If `expected = ["j1", "j3"]` and the pipeline returns `["j1", "j7", "j9"]`, score = 1/2 = 0.5.

---

## How Runs Work End to End

### 1 — Upload datasets (once per dataset version)

```bash
.venv/Scripts/python.exe evals/upload_datasets.py
```

This pushes both JSONL files to LangSmith as named Datasets:
- `job-matcher-extraction-v1` — 25 examples
- `job-matcher-ranking-v1` — 5 examples

Re-running skips datasets that already exist. To replace a dataset, delete it in the LangSmith UI first.

### 2 — Layer 1: extraction accuracy

```bash
.venv/Scripts/python.exe evals/run_extraction_eval.py
```

For each of the 25 examples, `extraction_target` runs:

```
inputs (id, title, description)
  → Job(...)
  → _extract_uncached_job(job, llm)   ← bypasses MongoDB cache, always calls DeepSeek
  → ExtractedJob
  → {"required_skills", "seniority", "is_remote", "latam_eligible"}
```

The four evaluators score each output against the golden `outputs`. LangSmith receives one trace per example with four metric columns.

`max_concurrency=3` means 3 examples run in parallel. Total time: ~12 seconds. Cost: ~$0.003 per full run.

### 3 — Layer 2: ranking quality

```bash
.venv/Scripts/python.exe evals/run_ranking_eval.py
```

For each of the 5 scenarios, `ranking_target` runs the three pipeline nodes:

```
inputs (profile, jobs[8])
  → MatcherState with filtered_jobs pre-populated
  → extract_node   ← calls DeepSeek for new jobs, MongoDB cache for seen ones
  → score_node     ← computes stack + seniority + ai_bonus + recency per job
  → rank_node      ← returns top_jobs sorted descending
  → {"top_jobs": [{"id", "score"}, ...]}
```

`precision_at_3` then compares the top 3 IDs against `expected_top_ids`.

The first scenario always pays LLM cost (8 jobs × extract). Subsequent scenarios hit the MongoDB extraction cache for jobs already seen in Scenario 1 — visible in the `[extract] 8 jobs → 8 cache hits, 0 LLM extractions needed` log lines.

---

## LangSmith Integration

Results appear automatically in LangSmith because:

1. `.env` sets `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT=job-matcher`
2. `langchain-openai` (used by DeepSeek via `base_url`) reads these env vars and auto-traces every LLM call
3. `langsmith.evaluate()` wraps each target function call in a traced run and attaches the evaluator scores

No code change is needed to enable tracing — it is purely env-var driven.

### Experiment naming

Each run creates a named Experiment:
- `extraction-<short-hash>` (e.g., `extraction-710c3d59`)
- `ranking-<short-hash>` (e.g., `ranking-c3d660b1`)

The prefix comes from `experiment_prefix=` in the `evaluate()` call; the hash is generated by LangSmith to make each run unique.

### What to look at in the UI

**Datasets view** — shows each golden example as a row with its `inputs` and `outputs`. You can click any row to see the raw JSON.

**Experiments view** — shows all runs of `evaluate()`. Each experiment row has:
- Average score per metric column
- Pass rate (scores ≥ threshold, configurable)
- Per-example breakdown: which examples failed and by how much

**Traces view** — every individual LLM call from `extract_node` is a traced span. You can see the exact prompt sent to DeepSeek, the raw response, token counts, and latency.

---

## Scoring Formula Reference (Layer 2)

The scoring formula `score_node` applies to each extracted job:

| Component | Range | Trigger |
|---|---|---|
| Stack score | 0 – 40 | Fraction of `preferred_keywords` found in extracted skills |
| Seniority bonus/penalty | -20 / 0 / +10 / +20 | `avoid_seniority` → -20, neutral → 0, `target_seniority` → +10, exact match → +20 |
| AI bonus | 0 / +10 / +20 | ≥1 AI keyword in skills → +10, ≥3 → +20 |
| Recency | 0 – 20 | `posted_at` within 7 days → +20, within 30 → +10, within 90 → +5, older → 0 |
| **Total** | **-20 – 100** | Clamped |

The recency component is why two identical-skill jobs posted on different dates rank differently — the formula is deterministic given the same extraction output and `posted_at` date.

---

## Running in CI

To add these evals to a CI gate, add a step after the test suite:

```yaml
- name: Run extraction eval
  env:
    LANGSMITH_TRACING: "true"
    LANGSMITH_API_KEY: ${{ secrets.LANGSMITH_API_KEY }}
    LANGSMITH_PROJECT: job-matcher-ci
    DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
    MONGODB_URI: ${{ secrets.MONGODB_URI }}
  run: .venv/Scripts/python.exe evals/run_extraction_eval.py
```

Layer 1 costs ~$0.003 and takes ~15 seconds — cheap enough for every PR. Layer 2 costs ~$0.002 and takes ~5 seconds.

A CI gate on average `skill_overlap ≥ 0.75` catches prompt drift before it reaches production. Set thresholds in the LangSmith Dataset settings under **Rules**.

---

## Layer 3 — LLM-as-Judge (LangSmith Evaluator Playground)

Layer 3 uses DeepSeek-chat as a judge inside the LangSmith UI. It evaluates ranking quality semantically — not just whether the right IDs appeared, but whether the pipeline's reasoning (scores, ordering) is defensible for the given profile.

### Where to configure it

1. Open LangSmith → **Datasets** → `job-matcher-ranking-v1`
2. Open any experiment (e.g. `ranking-c3d660b1`)
3. Click **Evaluator Playground** → **Add Evaluator**
4. Set **Model**: `ChatDeepSeek / deepseek-chat`
5. Set **Feedback key**: `ranking_correctness`
6. Set **Output type**: Boolean
7. Paste the prompt below into the **User** message field

### Evaluator prompt

Copy this entire block into the LangSmith **User** message field exactly as shown. The `{{input}}`, `{{output}}`, and `{{referenceOutput}}` placeholders are resolved automatically by LangSmith for each example.

```
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
- The top 3 contains a role in a fundamentally different tech stack than the profile requests (e.g., a Java role when the profile specifies Python).
</Rubric>

<Instructions>
1. Read input.profile: note preferred_keywords, target_seniority, and avoid_seniority.
2. Read referenceOutput.expected_top_ids — these are the gold-standard correct answers.
3. Extract the first 3 entries from output.top_jobs. Only these 3 positions matter.
4. For each expected ID: check if it appears in those 3 positions. If any is missing, the ranking is wrong.
5. For each top-3 job: check seniority against avoid_seniority and check skill overlap with preferred_keywords.
6. Return true only if all expected IDs are present AND no disqualifying seniority or skill mismatch exists in the top 3.
</Instructions>

<Reminder>
Focus on whether the right jobs surfaced at the top — not on exact score values or position within the top 3. A score of 75 vs 70 is irrelevant; what matters is whether the correct job IDs appear in the first 3 results. Do not penalize the pipeline for ranking two tied jobs in either order when both are expected.
</Reminder>

<input>
{{input}}
</input>

<output>
{{output}}
</output>

<referenceOutput>
{{referenceOutput}}
</referenceOutput>
```

### Why this prompt works

| Design choice | Reason |
|---|---|
| Boolean output (not 0–1 float) | Ranking correctness is binary for this use case — either the expected jobs are in the top 3 or they are not |
| `expected_top_ids` as the anchor | The Rubric ties directly to the golden dataset's `outputs` field — no ambiguity about what "correct" means |
| Seniority and skill checks as tiebreakers | Catches the case where `precision_at_3 = 1.0` but by coincidence — the judge verifies the reasons |
| "Do not penalize tied jobs" reminder | The scoring formula produces ties; the judge should not fail a run because `j1` ranked above `j5` when both are expected |
| DeepSeek-chat as judge | Same model used by the pipeline — catches cases where the judge and the pipeline agree on skill labels |

### What to do with results

After running the evaluator on an experiment, LangSmith shows a `ranking_correctness` column per example (true/false). Any `false` row is a ranking failure — click the row to see the full trace: which job was expected, what actually ranked in its place, and what scores each received. This gives you the exact input to fix in `score_node` or the extraction prompt.

---

## Adding New Examples

**To extend extraction_golden.jsonl:**

Add a line with `id`, `title`, and `description` as inputs, and the four extraction fields as outputs:

```json
{"inputs": {"id": "g026", "title": "...", "description": "..."}, "outputs": {"required_skills": [...], "seniority": "mid", "is_remote": true, "latam_eligible": false}}
```

Then re-upload (delete the old dataset in LangSmith UI first, or bump the dataset name to `v2`):

```bash
.venv/Scripts/python.exe evals/upload_datasets.py
```

**To extend ranking_golden.jsonl:**

Add a scenario with a `profile`, 8 jobs in `inputs.jobs`, and 1–3 expected top IDs in `outputs.expected_top_ids`. Keep `expected_top_ids` to ≤3 entries so `precision_at_3` can reach 1.0.

**ID rule (non-negotiable):** prefix every job ID with the scenario number — `s6-j1` through `s6-j8` for Scenario 6. Never reuse a bare `j1`–`j8` ID. The `extract_node` caches extractions by job ID in MongoDB; reusing IDs across scenarios causes the first scenario's extraction to poison all later ones that share the same ID, regardless of how different the job descriptions are. See the [Job ID convention](#job-id-convention----why-ids-are-prefixed-s1--s2-) section for the full incident.
