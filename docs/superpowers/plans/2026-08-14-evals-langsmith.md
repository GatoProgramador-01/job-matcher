# Evals + LangSmith Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a two-layer LangSmith eval harness (extraction accuracy + ranking quality), golden JSONL datasets, node docstrings, and an architecture doc to the job-matcher project.

**Architecture:** All evaluators are deterministic Python metrics (Jaccard, exact-match, precision@k) — no LLM-as-judge, no OpenAI. The only LLM cost is running `extract_node` against the 25 golden examples (~$0.003/run). LangSmith tracing activates automatically via env vars because `langchain-openai` reads them natively.

**Tech Stack:** Python 3.12, LangSmith SDK (`langsmith>=0.1`), LangGraph, LangChain-OpenAI (DeepSeek backend), pytest, uv

## Global Constraints

- Python executable: `.venv\Scripts\python.exe` (Windows, uv-managed)
- Run tests from project root: `.venv\Scripts\python.exe -m pytest tests/ -v`
- Package is installed as editable via `pyproject.toml` (`where = ["src"]`); `import job_matcher` works
- DeepSeek key in `.env` as `DEEPSEEK_API_KEY`; LangSmith vars: `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT=job-matcher`
- All terminal output uses ASCII-only (no box-drawing characters)
- `evals/` lives at project root alongside `src/`, `tests/`, `docs/`

---

### Task 1: Setup — deps, env, scaffold

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Create: `evals/__init__.py`
- Create: `evals/datasets/.gitkeep`
- Create: `evals/evaluators/__init__.py`

**Interfaces:**
- Produces: `langsmith` importable in all subsequent tasks

- [ ] **Step 1: Add langsmith to pyproject.toml**

Open `pyproject.toml`. In the `[project]` `dependencies` list, add `"langsmith>=0.1"` after the last existing dep:

```toml
dependencies = [
    "langgraph>=0.2",
    "langchain-openai>=0.2",
    "pydantic>=2.0",
    "requests>=2.31",
    "python-dotenv>=1.0",
    "beautifulsoup4>=4.12",
    "pymongo>=4.6",
    "fastapi>=0.110",
    "uvicorn>=0.27",
    "langsmith>=0.1",
]
```

- [ ] **Step 2: Update .env.example**

Add three lines to the end of `.env.example`:

```env
# LangSmith tracing — get your key at https://smith.langchain.com/settings
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_...
LANGSMITH_PROJECT=job-matcher
```

- [ ] **Step 3: Create evals scaffold**

```bash
mkdir -p evals/datasets evals/evaluators
touch evals/__init__.py evals/evaluators/__init__.py
```

- [ ] **Step 4: Install the new dependency**

```bash
.venv\Scripts\python.exe -m uv pip install langsmith
```

Expected: `Successfully installed langsmith-...`

Verify:
```bash
.venv\Scripts\python.exe -c "import langsmith; print(langsmith.__version__)"
```

Expected: prints a version string like `0.1.x`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example evals/
git commit -m "feat(evals): scaffold evals/ directory + add langsmith dep"
```

---

### Task 2: Extraction golden dataset

**Files:**
- Create: `evals/datasets/extraction_golden.jsonl`

**Interfaces:**
- Produces: 25-example JSONL consumed by Task 6 (uploader) and Task 7 (L1 runner)

- [ ] **Step 1: Create extraction_golden.jsonl**

Create `evals/datasets/extraction_golden.jsonl` with exactly these 25 lines (one JSON object per line):

```jsonl
{"inputs": {"id": "g001", "title": "Senior Python Backend Engineer", "description": "We need a Senior Python Backend Engineer with FastAPI, PostgreSQL, Docker. 5+ years experience. 100% remote worldwide. LATAM candidates welcome."}, "outputs": {"required_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"], "seniority": "senior", "is_remote": true, "latam_eligible": true}}
{"inputs": {"id": "g002", "title": "Junior React Frontend Developer", "description": "Entry-level React developer position. Work with React, TypeScript, and CSS. 0-2 years experience. Remote work from USA only."}, "outputs": {"required_skills": ["React", "TypeScript", "CSS"], "seniority": "junior", "is_remote": true, "latam_eligible": false}}
{"inputs": {"id": "g003", "title": "Mid-level Node.js Developer", "description": "Mid-level Node.js developer for our NYC team. Must know Express, MongoDB, TypeScript. Hybrid schedule: 3 days in office. NYC office required."}, "outputs": {"required_skills": ["Node.js", "Express", "MongoDB", "TypeScript"], "seniority": "mid", "is_remote": false, "latam_eligible": false}}
{"inputs": {"id": "g004", "title": "Senior Data Engineer", "description": "Senior Data Engineer to build scalable pipelines. Required: Python, Apache Spark, Airflow, BigQuery. Remote from USA or Canada only."}, "outputs": {"required_skills": ["Python", "Apache Spark", "Airflow", "BigQuery"], "seniority": "senior", "is_remote": true, "latam_eligible": false}}
{"inputs": {"id": "g005", "title": "Staff Principal Software Engineer", "description": "Staff level engineering role leading architecture across multiple teams. 10+ years required. Python, distributed systems, Kubernetes. Remote friendly."}, "outputs": {"required_skills": ["Python", "Kubernetes"], "seniority": "staff", "is_remote": true, "latam_eligible": false}}
{"inputs": {"id": "g006", "title": "Python Trainee Developer", "description": "Entry-level trainee position for new Python developers. Learn Django, REST APIs, and SQL. No experience required. Fully remote."}, "outputs": {"required_skills": ["Python", "Django", "SQL"], "seniority": "junior", "is_remote": true, "latam_eligible": false}}
{"inputs": {"id": "g007", "title": "Senior LangChain RAG Engineer", "description": "Build retrieval-augmented generation systems with LangChain, Python, and Pinecone vector database. LlamaIndex experience a plus. Fully remote. LATAM candidates welcome."}, "outputs": {"required_skills": ["LangChain", "Python", "Pinecone", "LlamaIndex"], "seniority": "senior", "is_remote": true, "latam_eligible": true}}
{"inputs": {"id": "g008", "title": "Software Engineer (5+ years)", "description": "Experienced software engineer with Python and AWS expertise. 5 or more years of professional software development experience. Fully remote."}, "outputs": {"required_skills": ["Python", "AWS"], "seniority": "senior", "is_remote": true, "latam_eligible": false}}
{"inputs": {"id": "g009", "title": "Backend Developer", "description": "Python developer needed. Remote OK."}, "outputs": {"required_skills": ["Python"], "seniority": null, "is_remote": true, "latam_eligible": false}}
{"inputs": {"id": "g010", "title": "Senior Site Reliability Engineer", "description": "Senior SRE to manage cloud infrastructure. Required: Docker, Kubernetes, Terraform, AWS, Python scripting. Prometheus and Grafana a plus. 100% remote."}, "outputs": {"required_skills": ["Docker", "Kubernetes", "Terraform", "AWS", "Python"], "seniority": "senior", "is_remote": true, "latam_eligible": false}}
{"inputs": {"id": "g011", "title": "Mid-Level Full Stack Developer", "description": "Mid-level engineer for Python backend (Django/FastAPI) and React frontend. PostgreSQL required. Remote-first, open to candidates from Latin America."}, "outputs": {"required_skills": ["Python", "Django", "FastAPI", "React", "PostgreSQL"], "seniority": "mid", "is_remote": true, "latam_eligible": true}}
{"inputs": {"id": "g012", "title": "Senior Golang Backend Engineer", "description": "Senior Go developer for high-performance API services. Required: Go, gRPC, PostgreSQL, Redis, Docker. Remote from Europe or North America only."}, "outputs": {"required_skills": ["Go", "gRPC", "PostgreSQL", "Redis", "Docker"], "seniority": "senior", "is_remote": true, "latam_eligible": false}}
{"inputs": {"id": "g013", "title": "Python Developer (LatAm Candidates Welcome)", "description": "Python developer with FastAPI and SQLAlchemy experience. Mid-level position. Fully remote. Latin American applicants strongly encouraged. Salary in USD."}, "outputs": {"required_skills": ["Python", "FastAPI", "SQLAlchemy"], "seniority": "mid", "is_remote": true, "latam_eligible": true}}
{"inputs": {"id": "g014", "title": "Backend Engineer (Hybrid NYC)", "description": "Backend engineer for our New York team. Django, Python, MySQL expertise required. Hybrid position: 3 days in office (Manhattan), 2 days remote. NYC metro area required."}, "outputs": {"required_skills": ["Django", "Python", "MySQL"], "seniority": null, "is_remote": false, "latam_eligible": false}}
{"inputs": {"id": "g015", "title": "Senior Python Engineer", "description": "Senior Python engineer for our microservices platform. Required: Python, Docker, Kubernetes, PostgreSQL, Redis, RabbitMQ, FastAPI. CI/CD and GitHub Actions a plus. Fully remote globally."}, "outputs": {"required_skills": ["Python", "Docker", "Kubernetes", "PostgreSQL", "Redis", "RabbitMQ", "FastAPI"], "seniority": "senior", "is_remote": true, "latam_eligible": false}}
{"inputs": {"id": "g016", "title": "Entry Level Python Developer", "description": "Entry-level developer role for recent graduates. Python fundamentals required. We will train you on Flask and SQL. US only, remote."}, "outputs": {"required_skills": ["Python", "Flask", "SQL"], "seniority": "junior", "is_remote": true, "latam_eligible": false}}
{"inputs": {"id": "g017", "title": "Desarrollador Python Semi-Senior (SSR)", "description": "Buscamos desarrollador Python Semi-Senior (SSR). Experiencia con FastAPI, Docker, y PostgreSQL. Trabajo 100% remoto. Candidatos de LATAM bienvenidos."}, "outputs": {"required_skills": ["Python", "FastAPI", "Docker", "PostgreSQL"], "seniority": "mid", "is_remote": true, "latam_eligible": true}}
{"inputs": {"id": "g018", "title": "Senior LangGraph Multi-Agent Systems Engineer", "description": "Build multi-agent AI systems with LangGraph and Anthropic Claude API. Python expertise required. RAG, vector search, and agent orchestration experience needed. Remote worldwide."}, "outputs": {"required_skills": ["LangGraph", "Python", "Anthropic", "RAG"], "seniority": "senior", "is_remote": true, "latam_eligible": false}}
{"inputs": {"id": "g019", "title": "Lead Software Engineer", "description": "Lead Software Engineer to guide our backend team. Python, microservices, Kafka, PostgreSQL required. Engineering leadership experience expected. Remote globally."}, "outputs": {"required_skills": ["Python", "Kafka", "PostgreSQL"], "seniority": "senior", "is_remote": true, "latam_eligible": false}}
{"inputs": {"id": "g020", "title": "Mid-Level Data Scientist", "description": "Mid-level data scientist for ML model development. Python, scikit-learn, pandas, TensorFlow, and Jupyter notebooks required. Remote."}, "outputs": {"required_skills": ["Python", "scikit-learn", "pandas", "TensorFlow"], "seniority": "mid", "is_remote": true, "latam_eligible": false}}
{"inputs": {"id": "g021", "title": "Senior iOS/Android Developer", "description": "Senior mobile developer with Swift (iOS) and Kotlin (Android) experience. Cross-platform knowledge a bonus. Fully remote globally. 5+ years mobile experience."}, "outputs": {"required_skills": ["Swift", "Kotlin"], "seniority": "senior", "is_remote": true, "latam_eligible": false}}
{"inputs": {"id": "g022", "title": "Python Backend Engineer", "description": "We need a Python engineer with Flask and MySQL knowledge. Database design experience helpful. Remote work available."}, "outputs": {"required_skills": ["Python", "Flask", "MySQL"], "seniority": null, "is_remote": true, "latam_eligible": false}}
{"inputs": {"id": "g023", "title": "Senior Cloud Infrastructure Engineer", "description": "Senior cloud infrastructure engineer to manage AWS resources. Terraform, CloudFormation, Docker required. Ansible a plus. Remote from North America and Europe only."}, "outputs": {"required_skills": ["AWS", "Terraform", "CloudFormation", "Docker"], "seniority": "senior", "is_remote": true, "latam_eligible": false}}
{"inputs": {"id": "g024", "title": "Mid-Level Python Developer (Remote Americas)", "description": "Mid-level Python developer, FastAPI and REST API design. Open to candidates anywhere in the Americas. Salary $60-80K USD. Fully remote."}, "outputs": {"required_skills": ["Python", "FastAPI"], "seniority": "mid", "is_remote": true, "latam_eligible": true}}
{"inputs": {"id": "g025", "title": "Software Engineer II", "description": "Software Engineer II (mid-level, 3-5 years experience). Python, Java, Kubernetes, and CI/CD required. Remote position, worldwide."}, "outputs": {"required_skills": ["Python", "Java", "Kubernetes"], "seniority": "mid", "is_remote": true, "latam_eligible": false}}
```

- [ ] **Step 2: Validate JSONL structure**

```bash
.venv\Scripts\python.exe -c "
import json
from pathlib import Path
lines = Path('evals/datasets/extraction_golden.jsonl').read_text().splitlines()
for i, line in enumerate(lines, 1):
    obj = json.loads(line)
    assert 'inputs' in obj and 'outputs' in obj, f'Line {i} missing inputs/outputs'
    assert {'id','title','description'} <= obj['inputs'].keys(), f'Line {i} bad inputs'
    assert {'required_skills','seniority','is_remote','latam_eligible'} <= obj['outputs'].keys(), f'Line {i} bad outputs'
print(f'All {len(lines)} examples valid')
"
```

Expected: `All 25 examples valid`

- [ ] **Step 3: Commit**

```bash
git add evals/datasets/extraction_golden.jsonl
git commit -m "feat(evals): add 25-example extraction golden dataset"
```

---

### Task 3: Extraction evaluators + unit tests

**Files:**
- Create: `evals/evaluators/extraction.py`
- Create: `tests/test_evaluators_extraction.py`

**Interfaces:**
- Produces: `skill_overlap(outputs, reference_outputs) -> dict`, `seniority_match`, `remote_match`, `latam_match` — consumed by Task 7 (L1 runner)
- Each evaluator returns `{"key": str, "score": float}` where score is in [0.0, 1.0]

- [ ] **Step 1: Write the failing tests**

Create `tests/test_evaluators_extraction.py`:

```python
import pytest
from evals.evaluators.extraction import skill_overlap, seniority_match, remote_match, latam_match


class TestSkillOverlap:
    def test_perfect_match(self):
        out = {"required_skills": ["Python", "FastAPI"]}
        ref = {"required_skills": ["Python", "FastAPI"]}
        result = skill_overlap(out, ref)
        assert result["key"] == "skill_overlap"
        assert result["score"] == pytest.approx(1.0)

    def test_partial_match(self):
        # intersection: {python, fastapi} = 2, union: {python, fastapi, docker, postgresql} = 4
        out = {"required_skills": ["Python", "FastAPI", "Docker"]}
        ref = {"required_skills": ["Python", "FastAPI", "PostgreSQL"]}
        result = skill_overlap(out, ref)
        assert result["score"] == pytest.approx(0.5)

    def test_no_match(self):
        out = {"required_skills": ["Go", "Rust"]}
        ref = {"required_skills": ["Python", "FastAPI"]}
        result = skill_overlap(out, ref)
        assert result["score"] == pytest.approx(0.0)

    def test_empty_predicted(self):
        out = {"required_skills": []}
        ref = {"required_skills": ["Python"]}
        result = skill_overlap(out, ref)
        assert result["score"] == pytest.approx(0.0)

    def test_both_empty(self):
        out = {"required_skills": []}
        ref = {"required_skills": []}
        result = skill_overlap(out, ref)
        assert result["score"] == pytest.approx(1.0)

    def test_case_insensitive(self):
        out = {"required_skills": ["python", "fastapi"]}
        ref = {"required_skills": ["Python", "FastAPI"]}
        result = skill_overlap(out, ref)
        assert result["score"] == pytest.approx(1.0)

    def test_missing_key_returns_zero(self):
        result = skill_overlap({}, {"required_skills": ["Python"]})
        assert result["score"] == pytest.approx(0.0)


class TestSeniorityMatch:
    def test_correct_senior(self):
        assert seniority_match({"seniority": "senior"}, {"seniority": "senior"})["score"] == 1.0

    def test_wrong_seniority(self):
        assert seniority_match({"seniority": "junior"}, {"seniority": "senior"})["score"] == 0.0

    def test_both_null(self):
        assert seniority_match({"seniority": None}, {"seniority": None})["score"] == 1.0

    def test_key_name(self):
        result = seniority_match({"seniority": "mid"}, {"seniority": "mid"})
        assert result["key"] == "seniority_match"

    def test_missing_key_counts_as_none(self):
        # missing key treated as None; if reference is also None => match
        assert seniority_match({}, {"seniority": None})["score"] == 1.0


class TestRemoteMatch:
    def test_both_true(self):
        assert remote_match({"is_remote": True}, {"is_remote": True})["score"] == 1.0

    def test_mismatch(self):
        assert remote_match({"is_remote": False}, {"is_remote": True})["score"] == 0.0

    def test_key_name(self):
        assert remote_match({"is_remote": True}, {"is_remote": True})["key"] == "remote_match"


class TestLatamMatch:
    def test_both_true(self):
        assert latam_match({"latam_eligible": True}, {"latam_eligible": True})["score"] == 1.0

    def test_mismatch(self):
        assert latam_match({"latam_eligible": False}, {"latam_eligible": True})["score"] == 0.0

    def test_key_name(self):
        assert latam_match({"latam_eligible": False}, {"latam_eligible": False})["key"] == "latam_match"
```

- [ ] **Step 2: Run tests — expect FAIL (module not found)**

```bash
.venv\Scripts\python.exe -m pytest tests/test_evaluators_extraction.py -v
```

Expected: `ModuleNotFoundError: No module named 'evals'`

- [ ] **Step 3: Implement the evaluators**

Create `evals/evaluators/extraction.py`:

```python
def skill_overlap(outputs: dict, reference_outputs: dict) -> dict:
    predicted = {s.lower() for s in outputs.get("required_skills") or []}
    golden = {s.lower() for s in reference_outputs.get("required_skills") or []}
    union = predicted | golden
    score = len(predicted & golden) / len(union) if union else 1.0
    return {"key": "skill_overlap", "score": score}


def seniority_match(outputs: dict, reference_outputs: dict) -> dict:
    score = float(outputs.get("seniority") == reference_outputs.get("seniority"))
    return {"key": "seniority_match", "score": score}


def remote_match(outputs: dict, reference_outputs: dict) -> dict:
    score = float(outputs.get("is_remote") == reference_outputs.get("is_remote"))
    return {"key": "remote_match", "score": score}


def latam_match(outputs: dict, reference_outputs: dict) -> dict:
    score = float(outputs.get("latam_eligible") == reference_outputs.get("latam_eligible"))
    return {"key": "latam_match", "score": score}
```

- [ ] **Step 4: Add evals to sys.path in conftest so pytest can find it**

Open `tests/conftest.py` and add these lines at the very top (before existing imports):

```python
import sys
from pathlib import Path
# Allow `import evals.evaluators.*` from tests/ without installing evals as a package
sys.path.insert(0, str(Path(__file__).parent.parent))
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
.venv\Scripts\python.exe -m pytest tests/test_evaluators_extraction.py -v
```

Expected: `17 passed`

- [ ] **Step 6: Commit**

```bash
git add evals/evaluators/extraction.py tests/test_evaluators_extraction.py tests/conftest.py
git commit -m "feat(evals): extraction evaluators — skill Jaccard + exact-match metrics"
```

---

### Task 4: Ranking golden dataset

**Files:**
- Create: `evals/datasets/ranking_golden.jsonl`

**Interfaces:**
- Produces: 5-scenario JSONL consumed by Task 6 (uploader) and Task 8 (L2 runner)
- Each scenario: `inputs = {profile, jobs}`, `outputs = {expected_top_ids}`

- [ ] **Step 1: Create ranking_golden.jsonl**

Create `evals/datasets/ranking_golden.jsonl` with exactly these 5 lines:

```jsonl
{"inputs": {"profile": {"preferred_keywords": ["Python", "LangChain", "FastAPI", "RAG"], "reject_keywords": [], "target_seniority": ["mid", "senior"], "avoid_seniority": ["junior", "staff"]}, "jobs": [{"id": "j1", "title": "Senior Python LangChain Engineer", "company": "AI Corp", "description": "Senior Python developer building LangChain-based AI pipelines. FastAPI, Python 3.11+, LangChain, vector databases required. 5+ years. Remote.", "apply_url": "https://eval.local/j1"}, {"id": "j2", "title": "Junior PHP Developer", "company": "Web Co", "description": "Junior PHP developer for WordPress plugins. PHP, MySQL, JavaScript. 0-1 years. Remote.", "apply_url": "https://eval.local/j2"}, {"id": "j3", "title": "Mid-Level FastAPI Python Developer", "company": "Tech Corp", "description": "Mid-level Python developer with FastAPI expertise. PostgreSQL, Docker, Python. 3+ years. Remote.", "apply_url": "https://eval.local/j3"}, {"id": "j4", "title": "Senior RAG Pipeline Engineer", "company": "AI Labs", "description": "Senior engineer building retrieval-augmented generation systems. RAG, Python, LangChain, Pinecone. Remote.", "apply_url": "https://eval.local/j4"}, {"id": "j5", "title": "Senior Java Backend Engineer", "company": "Enterprise Inc", "description": "Senior Java developer for enterprise systems. Java, Spring Boot, PostgreSQL, Microservices. Remote.", "apply_url": "https://eval.local/j5"}, {"id": "j6", "title": "Staff Principal Python Architect", "company": "Platform Co", "description": "Staff-level principal architect leading Python platform. Python, AWS, Kubernetes, system design. Remote.", "apply_url": "https://eval.local/j6"}, {"id": "j7", "title": "Senior LangGraph Multi-Agent Engineer", "company": "Agent AI", "description": "Senior engineer building multi-agent systems with LangGraph and Python. RAG, agentic AI, vector search. Remote.", "apply_url": "https://eval.local/j7"}, {"id": "j8", "title": "Entry Level Python Developer", "company": "Learn Corp", "description": "Entry-level Python developer for training program. Python basics, Django intro. 0-1 years. Remote.", "apply_url": "https://eval.local/j8"}]}, "outputs": {"expected_top_ids": ["j1", "j3"]}}
{"inputs": {"profile": {"preferred_keywords": ["Python", "FastAPI", "PostgreSQL"], "reject_keywords": [], "target_seniority": ["mid", "senior"], "avoid_seniority": ["junior", "staff"]}, "jobs": [{"id": "j1", "title": "Mid-Level Python FastAPI Engineer", "company": "Tech A", "description": "Mid-level Python engineer with FastAPI, PostgreSQL, Docker. 3+ years. Remote.", "apply_url": "https://eval.local/j1"}, {"id": "j2", "title": "Intern Python Developer", "company": "Tech B", "description": "Python intern for summer program. Python basics. Remote.", "apply_url": "https://eval.local/j2"}, {"id": "j3", "title": "Senior Python Developer", "company": "Tech C", "description": "Senior Python developer with PostgreSQL and AWS. Remote.", "apply_url": "https://eval.local/j3"}, {"id": "j4", "title": "Junior Python Developer", "company": "Tech D", "description": "Junior Python developer, 1-2 years experience. Django, Python. Remote.", "apply_url": "https://eval.local/j4"}, {"id": "j5", "title": "Staff Python Architect", "company": "Tech E", "description": "Staff-level principal Python architect. 10+ years. Python, AWS. Remote.", "apply_url": "https://eval.local/j5"}, {"id": "j6", "title": "Entry Level Python Engineer", "company": "Tech F", "description": "Entry level Python engineering role for new grads. Python, Flask. Remote.", "apply_url": "https://eval.local/j6"}, {"id": "j7", "title": "Mid-Level FastAPI Developer", "company": "Tech G", "description": "Mid-level FastAPI and Python developer. PostgreSQL, Docker. Remote.", "apply_url": "https://eval.local/j7"}, {"id": "j8", "title": "Senior FastAPI Python Engineer", "company": "Tech H", "description": "Senior FastAPI engineer with Python, PostgreSQL, and Docker. 5+ years. Remote.", "apply_url": "https://eval.local/j8"}]}, "outputs": {"expected_top_ids": ["j1", "j8"]}}
{"inputs": {"profile": {"preferred_keywords": ["Python", "LangChain", "RAG", "vector search", "FastAPI"], "reject_keywords": [], "target_seniority": ["mid", "senior"], "avoid_seniority": ["junior", "staff"]}, "jobs": [{"id": "j1", "title": "Senior Python LangChain Engineer with RAG", "company": "AI A", "description": "Senior Python engineer building LangChain RAG pipelines with vector search. FastAPI, Python, Pinecone. Remote.", "apply_url": "https://eval.local/j1"}, {"id": "j2", "title": "Senior Python Engineer", "company": "AI B", "description": "Senior Python engineer for backend systems. Python, AWS, PostgreSQL. Remote.", "apply_url": "https://eval.local/j2"}, {"id": "j3", "title": "Mid-Level RAG Vector Search Developer", "company": "AI C", "description": "Mid-level engineer specializing in RAG and vector search systems. Python, LangChain, Weaviate. Remote.", "apply_url": "https://eval.local/j3"}, {"id": "j4", "title": "Senior FastAPI Python Developer", "company": "AI D", "description": "Senior FastAPI developer. Python, PostgreSQL, Docker. Remote.", "apply_url": "https://eval.local/j4"}, {"id": "j5", "title": "Junior Data Entry Developer", "company": "AI E", "description": "Junior data entry developer. Python scripting, Excel. Remote.", "apply_url": "https://eval.local/j5"}, {"id": "j6", "title": "Mid-Level Python Developer", "company": "AI F", "description": "Mid-level Python developer for web applications. Python, Django. Remote.", "apply_url": "https://eval.local/j6"}, {"id": "j7", "title": "Senior AI/ML Python Engineer", "company": "AI G", "description": "Senior AI and machine learning engineer. Python, TensorFlow, LLM integration. Remote.", "apply_url": "https://eval.local/j7"}, {"id": "j8", "title": "Staff Principal Architect", "company": "AI H", "description": "Staff principal architect for cloud platform. Python, AWS, Kubernetes. Remote.", "apply_url": "https://eval.local/j8"}]}, "outputs": {"expected_top_ids": ["j1", "j3"]}}
{"inputs": {"profile": {"preferred_keywords": ["Python", "FastAPI"], "reject_keywords": [], "target_seniority": ["mid", "senior"], "avoid_seniority": ["junior", "staff"]}, "jobs": [{"id": "j1", "title": "Mid-Level Python FastAPI Developer", "company": "Rec A", "description": "Mid-level Python FastAPI developer. PostgreSQL, Docker. Remote.", "apply_url": "https://eval.local/j1", "posted_at": "2026-08-14"}, {"id": "j2", "title": "Mid-Level Python FastAPI Developer", "company": "Rec B", "description": "Mid-level Python FastAPI developer. PostgreSQL, Docker. Remote.", "apply_url": "https://eval.local/j2", "posted_at": "2026-08-04"}, {"id": "j3", "title": "Mid-Level Python FastAPI Developer", "company": "Rec C", "description": "Mid-level Python FastAPI developer. PostgreSQL, Docker. Remote.", "apply_url": "https://eval.local/j3", "posted_at": "2026-07-25"}, {"id": "j4", "title": "Mid-Level Python FastAPI Developer", "company": "Rec D", "description": "Mid-level Python FastAPI developer. PostgreSQL, Docker. Remote.", "apply_url": "https://eval.local/j4", "posted_at": "2026-06-15"}, {"id": "j5", "title": "Mid-Level FastAPI Developer", "company": "Rec E", "description": "Mid-level FastAPI developer. Python, Docker. Remote.", "apply_url": "https://eval.local/j5", "posted_at": "2026-08-14"}, {"id": "j6", "title": "Python Developer", "company": "Rec F", "description": "Python developer for backend systems. Flask, MySQL. Remote.", "apply_url": "https://eval.local/j6", "posted_at": "2026-08-14"}, {"id": "j7", "title": "Senior Python FastAPI Engineer", "company": "Rec G", "description": "Senior Python FastAPI engineer. PostgreSQL, Docker. Remote.", "apply_url": "https://eval.local/j7", "posted_at": "2026-08-14"}, {"id": "j8", "title": "Junior Python Developer", "company": "Rec H", "description": "Junior Python developer, 1 year experience. Remote.", "apply_url": "https://eval.local/j8", "posted_at": "2026-08-14"}]}, "outputs": {"expected_top_ids": ["j1"]}}
{"inputs": {"profile": {"preferred_keywords": ["Python", "LangChain", "RAG"], "reject_keywords": [], "target_seniority": ["mid", "senior"], "avoid_seniority": ["junior", "staff"]}, "jobs": [{"id": "j1", "title": "Java Developer", "company": "Bad A", "description": "Java developer for enterprise systems. Java, Spring Boot. Remote.", "apply_url": "https://eval.local/j1"}, {"id": "j2", "title": "Ruby on Rails Developer", "company": "Bad B", "description": "Ruby on Rails developer. Ruby, PostgreSQL. Remote.", "apply_url": "https://eval.local/j2"}, {"id": "j3", "title": "PHP Developer", "company": "Bad C", "description": "PHP developer for web applications. PHP, MySQL. Remote.", "apply_url": "https://eval.local/j3"}, {"id": "j4", "title": "JavaScript Frontend Developer", "company": "Bad D", "description": "Frontend JavaScript developer. React, CSS, HTML. Remote.", "apply_url": "https://eval.local/j4"}, {"id": "j5", "title": "C++ Game Developer", "company": "Bad E", "description": "C++ game developer for mobile games. C++, OpenGL. Remote.", "apply_url": "https://eval.local/j5"}, {"id": "j6", "title": "Python Developer", "company": "Bad F", "description": "Python developer for scripting. Python, Bash. Remote.", "apply_url": "https://eval.local/j6"}, {"id": "j7", "title": "Senior Python Developer", "company": "Bad G", "description": "Senior Python developer for backend systems. Python, Django, PostgreSQL. Remote.", "apply_url": "https://eval.local/j7"}, {"id": "j8", "title": "Java Backend Senior Engineer", "company": "Bad H", "description": "Senior Java backend engineer. Java, microservices. Remote.", "apply_url": "https://eval.local/j8"}]}, "outputs": {"expected_top_ids": ["j7"]}}
```

- [ ] **Step 2: Validate JSONL structure**

```bash
.venv\Scripts\python.exe -c "
import json
from pathlib import Path
lines = Path('evals/datasets/ranking_golden.jsonl').read_text().splitlines()
for i, line in enumerate(lines, 1):
    obj = json.loads(line)
    assert 'inputs' in obj and 'outputs' in obj
    assert 'profile' in obj['inputs'] and 'jobs' in obj['inputs']
    assert 'expected_top_ids' in obj['outputs']
    assert len(obj['inputs']['jobs']) == 8, f'Scenario {i} should have 8 jobs'
print(f'All {len(lines)} ranking scenarios valid')
"
```

Expected: `All 5 ranking scenarios valid`

- [ ] **Step 3: Commit**

```bash
git add evals/datasets/ranking_golden.jsonl
git commit -m "feat(evals): add 5-scenario ranking golden dataset"
```

---

### Task 5: Ranking evaluator + unit tests

**Files:**
- Create: `evals/evaluators/ranking.py`
- Create: `tests/test_evaluators_ranking.py`

**Interfaces:**
- Produces: `precision_at_3(outputs, reference_outputs) -> dict` — consumed by Task 8 (L2 runner)
- `outputs` must have key `top_jobs: list[dict]` where each dict has `"id": str`
- `reference_outputs` must have key `expected_top_ids: list[str]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_evaluators_ranking.py`:

```python
from evals.evaluators.ranking import precision_at_3


class TestPrecisionAt3:
    def test_perfect_all_three_expected_in_top3(self):
        out = {"top_jobs": [{"id": "j1"}, {"id": "j7"}, {"id": "j3"}]}
        ref = {"expected_top_ids": ["j1", "j7", "j3"]}
        result = precision_at_3(out, ref)
        assert result["key"] == "precision_at_3"
        assert result["score"] == 1.0

    def test_perfect_two_expected_both_in_top3(self):
        out = {"top_jobs": [{"id": "j1"}, {"id": "j3"}, {"id": "j5"}]}
        ref = {"expected_top_ids": ["j1", "j3"]}
        result = precision_at_3(out, ref)
        assert result["score"] == 1.0

    def test_partial_one_of_two_expected_in_top3(self):
        out = {"top_jobs": [{"id": "j1"}, {"id": "j2"}, {"id": "j5"}]}
        ref = {"expected_top_ids": ["j1", "j3"]}
        result = precision_at_3(out, ref)
        assert result["score"] == 0.5

    def test_zero_none_in_top3(self):
        out = {"top_jobs": [{"id": "j4"}, {"id": "j5"}, {"id": "j6"}]}
        ref = {"expected_top_ids": ["j1", "j3"]}
        result = precision_at_3(out, ref)
        assert result["score"] == 0.0

    def test_only_checks_first_3_results(self):
        # j3 is in position 4 (index 3) — should NOT count as a hit
        out = {"top_jobs": [{"id": "j1"}, {"id": "j5"}, {"id": "j6"}, {"id": "j3"}]}
        ref = {"expected_top_ids": ["j1", "j3"]}
        result = precision_at_3(out, ref)
        assert result["score"] == 0.5  # only j1 hits in top-3

    def test_empty_expected_returns_zero(self):
        out = {"top_jobs": [{"id": "j1"}]}
        ref = {"expected_top_ids": []}
        result = precision_at_3(out, ref)
        assert result["score"] == 0.0

    def test_empty_top_jobs_returns_zero(self):
        out = {"top_jobs": []}
        ref = {"expected_top_ids": ["j1"]}
        result = precision_at_3(out, ref)
        assert result["score"] == 0.0

    def test_single_expected_hit(self):
        out = {"top_jobs": [{"id": "j7"}, {"id": "j2"}, {"id": "j3"}]}
        ref = {"expected_top_ids": ["j7"]}
        result = precision_at_3(out, ref)
        assert result["score"] == 1.0
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
.venv\Scripts\python.exe -m pytest tests/test_evaluators_ranking.py -v
```

Expected: `ModuleNotFoundError: No module named 'evals.evaluators.ranking'`

- [ ] **Step 3: Implement precision_at_3**

Create `evals/evaluators/ranking.py`:

```python
def precision_at_3(outputs: dict, reference_outputs: dict) -> dict:
    top_ids = [j["id"] for j in (outputs.get("top_jobs") or [])][:3]
    expected = set(reference_outputs.get("expected_top_ids") or [])
    hits = sum(1 for jid in top_ids if jid in expected)
    score = hits / len(expected) if expected else 0.0
    return {"key": "precision_at_3", "score": score}
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
.venv\Scripts\python.exe -m pytest tests/test_evaluators_ranking.py -v
```

Expected: `8 passed`

- [ ] **Step 5: Run full test suite — confirm no regressions**

```bash
.venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: all existing tests + 25 new ones pass

- [ ] **Step 6: Commit**

```bash
git add evals/evaluators/ranking.py tests/test_evaluators_ranking.py
git commit -m "feat(evals): ranking evaluator precision@3 + unit tests"
```

---

### Task 6: Dataset uploader

**Files:**
- Create: `evals/upload_datasets.py`

**Interfaces:**
- Consumes: `evals/datasets/extraction_golden.jsonl`, `evals/datasets/ranking_golden.jsonl`
- Produces: Two LangSmith datasets named `"job-matcher-extraction-v1"` and `"job-matcher-ranking-v1"` — consumed by Tasks 7 and 8

- [ ] **Step 1: Create upload_datasets.py**

Create `evals/upload_datasets.py`:

```python
"""
Upload golden JSONL datasets to LangSmith.

Run once per dataset version:
    .venv\Scripts\python.exe evals/upload_datasets.py

Re-run after adding or correcting examples.
Requires LANGSMITH_API_KEY and LANGSMITH_TRACING=true in .env
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from langsmith import Client

DATASETS = {
    "job-matcher-extraction-v1": Path("evals/datasets/extraction_golden.jsonl"),
    "job-matcher-ranking-v1":    Path("evals/datasets/ranking_golden.jsonl"),
}


def upload() -> None:
    client = Client()
    existing = {d.name: d for d in client.list_datasets()}

    for name, path in DATASETS.items():
        lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        examples = [json.loads(l) for l in lines]

        if name in existing:
            print(f"Dataset '{name}' already exists ({len(examples)} examples) — skipping creation")
            print(f"  To replace, delete it in LangSmith UI first, then re-run this script")
            continue

        dataset = client.create_dataset(name)
        client.create_examples(
            inputs=[e["inputs"] for e in examples],
            outputs=[e["outputs"] for e in examples],
            dataset_id=dataset.id,
        )
        print(f"Created dataset '{name}' with {len(examples)} examples")
        print(f"  View at: https://smith.langchain.com/datasets/{dataset.id}")


if __name__ == "__main__":
    upload()
```

- [ ] **Step 2: Run the uploader**

```bash
.venv\Scripts\python.exe evals/upload_datasets.py
```

Expected output (first run):
```
Created dataset 'job-matcher-extraction-v1' with 25 examples
  View at: https://smith.langchain.com/datasets/...
Created dataset 'job-matcher-ranking-v1' with 5 examples
  View at: https://smith.langchain.com/datasets/...
```

Verify: open LangSmith UI → Datasets tab → confirm both datasets appear with correct example counts.

- [ ] **Step 3: Commit**

```bash
git add evals/upload_datasets.py
git commit -m "feat(evals): dataset uploader for LangSmith"
```

---

### Task 7: Layer 1 eval runner — extraction

**Files:**
- Create: `evals/run_extraction_eval.py`

**Interfaces:**
- Consumes: `_extract_uncached_job` from `job_matcher.nodes.extract`, `make_llm` from `job_matcher.infrastructure.deepseek`, all four evaluators from Task 3, dataset `"job-matcher-extraction-v1"` in LangSmith
- Produces: LangSmith Experiment named `"extraction-YYYY-MM-DD-HHmmss"` with per-example scores for all four metrics

- [ ] **Step 1: Create run_extraction_eval.py**

Create `evals/run_extraction_eval.py`:

```python
"""
Layer 1 eval — extraction accuracy.

Runs DeepSeek against the 25 golden job postings and scores results
with four deterministic metrics (Jaccard skill overlap + 3 exact-match).

Usage:
    .venv\Scripts\python.exe evals/run_extraction_eval.py

Results appear in LangSmith under Experiments -> extraction-*
Estimated cost: ~$0.003 (25 jobs x DeepSeek pricing)
"""
import sys
from pathlib import Path

# Allow `import evals.*` and `import job_matcher` from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from langsmith import evaluate
from job_matcher.domain.models import Job
from job_matcher.nodes.extract import _extract_uncached_job
from job_matcher.infrastructure.deepseek import make_llm
from evals.evaluators.extraction import skill_overlap, seniority_match, remote_match, latam_match


def extraction_target(inputs: dict) -> dict:
    job = Job(
        id=inputs["id"],
        title=inputs["title"],
        description=inputs["description"],
        apply_url="https://eval.local",
    )
    # Bypasses MongoDB cache — eval measures live model behavior, not cached results
    llm = make_llm()
    extracted, _, _ = _extract_uncached_job(job, llm)
    return {
        "required_skills": extracted.required_skills,
        "seniority": extracted.seniority,
        "is_remote": extracted.is_remote,
        "latam_eligible": extracted.latam_eligible,
    }


if __name__ == "__main__":
    results = evaluate(
        extraction_target,
        data="job-matcher-extraction-v1",
        evaluators=[skill_overlap, seniority_match, remote_match, latam_match],
        experiment_prefix="extraction",
        max_concurrency=3,
    )
    print(f"\nExperiment complete.")
    print(f"View results at: https://smith.langchain.com (Experiments tab)")
```

- [ ] **Step 2: Run the eval**

```bash
.venv\Scripts\python.exe evals/run_extraction_eval.py
```

Expected: LangSmith streams progress (25 rows), then prints `Experiment complete.`
Duration: ~2-4 minutes (25 LLM calls, max_concurrency=3)

Verify in LangSmith UI:
- Experiments tab → find `extraction-YYYY-MM-DD-...`
- Should show 25 rows, 4 metric columns
- `remote_match` and `latam_match` should score ≥ 0.80 avg
- `seniority_match` should score ≥ 0.70 avg (some ambiguous cases expected)
- `skill_overlap` should score ≥ 0.50 avg (Jaccard varies by LLM verbosity)

- [ ] **Step 3: Commit**

```bash
git add evals/run_extraction_eval.py
git commit -m "feat(evals): Layer 1 runner — extraction accuracy via langsmith.evaluate()"
```

---

### Task 8: Layer 2 eval runner — ranking

**Files:**
- Create: `evals/run_ranking_eval.py`

**Interfaces:**
- Consumes: `extract_node`, `score_node`, `rank_node` from `job_matcher.nodes.*`, `ProfileData`, `Job`, `MatcherState` from `job_matcher.domain.models`, `precision_at_3` from Task 5, dataset `"job-matcher-ranking-v1"` in LangSmith
- Produces: LangSmith Experiment named `"ranking-YYYY-MM-DD-HHmmss"` with `precision_at_3` scores

- [ ] **Step 1: Create run_ranking_eval.py**

Create `evals/run_ranking_eval.py`:

```python
"""
Layer 2 eval — end-to-end ranking quality.

Runs extract -> score -> rank against 5 golden profile+job-batch scenarios.
Measures whether the pipeline returns the expected top jobs in its top 3.

Usage:
    .venv\Scripts\python.exe evals/run_ranking_eval.py

Results appear in LangSmith under Experiments -> ranking-*
Estimated cost: ~$0.002 (5 scenarios x 8 jobs each x DeepSeek pricing)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from langsmith import evaluate
from job_matcher.domain.models import Job, ProfileData, MatcherState
from job_matcher.nodes.extract import extract_node
from job_matcher.nodes.score import score_node
from job_matcher.nodes.rank import rank_node
from evals.evaluators.ranking import precision_at_3


def ranking_target(inputs: dict) -> dict:
    profile = ProfileData(**inputs["profile"])
    jobs = [
        Job(**{**j, "apply_url": j.get("apply_url", "https://eval.local")})
        for j in inputs["jobs"]
    ]

    # Pre-populate filtered_jobs directly — skips fetch and filter nodes
    # since the dataset already provides the curated job batch to evaluate against
    state: MatcherState = {
        "profile": profile,
        "raw_jobs": [],
        "filtered_jobs": jobs,
        "extracted_jobs": [],
        "scored_jobs": [],
        "top_jobs": [],
        "output_format": "json",
        "token_stats": {},
    }

    state.update(extract_node(state))
    state.update(score_node(state))
    state.update(rank_node(state))

    return {
        "top_jobs": [{"id": sj.job.id, "score": sj.score} for sj in state["top_jobs"]]
    }


if __name__ == "__main__":
    results = evaluate(
        ranking_target,
        data="job-matcher-ranking-v1",
        evaluators=[precision_at_3],
        experiment_prefix="ranking",
    )
    print(f"\nExperiment complete.")
    print(f"View results at: https://smith.langchain.com (Experiments tab)")
```

- [ ] **Step 2: Run the eval**

```bash
.venv\Scripts\python.exe evals/run_ranking_eval.py
```

Expected: LangSmith streams progress (5 rows), then prints `Experiment complete.`
Duration: ~2-3 minutes (5 scenarios x 8 LLM calls each = 40 calls)

Verify in LangSmith UI:
- Experiments tab → find `ranking-YYYY-MM-DD-...`
- Should show 5 rows, 1 metric column (`precision_at_3`)
- Scenarios 1, 2, 3, 5 should score ≥ 0.5 (expected jobs clearly outscored by margin)
- Scenario 4 (recency tie-breaking) may score lower depending on extraction variance

- [ ] **Step 3: Commit**

```bash
git add evals/run_ranking_eval.py
git commit -m "feat(evals): Layer 2 runner — ranking quality via langsmith.evaluate()"
```

---

### Task 9: Node docstrings

**Files:**
- Modify: `src/job_matcher/nodes/fetch.py`
- Modify: `src/job_matcher/nodes/filter_.py`
- Modify: `src/job_matcher/nodes/extract.py`
- Modify: `src/job_matcher/nodes/score.py`
- Modify: `src/job_matcher/nodes/rank.py`

**Interfaces:**
- No code changes — pure documentation. Existing tests must still pass.

- [ ] **Step 1: Add docstring to fetch.py**

Insert this module docstring at the top of `src/job_matcher/nodes/fetch.py`, before the imports:

```python
"""
Fetch node — multi-source job listing retrieval.

Reads:   state["profile"]  (not used — fetch is profile-agnostic)
Writes:  state["raw_jobs"]    (list[dict] — raw job dicts from all sources)
         state["token_stats"] (empty TokenTracker — no LLM calls here)

Side effects:
  - HTTP GET to Remotive API (software-dev, devops-sysadmin, data categories)
  - HTTP GET to RemoteOK API
  - Writes MongoDB `raw_jobs` collection (upsert by `id`)
  - Updates local `cache.json` with seen job IDs (deduplication across runs)

Failure modes:
  - API unreachable: returns partial or empty list (no exception raised)
  - MongoDB down: save_raw_jobs() silently skips (MongoStorage.enabled=False)
"""
```

- [ ] **Step 2: Add docstring to filter_.py**

Insert at the top of `src/job_matcher/nodes/filter_.py`, before the imports:

```python
"""
Filter node — hard rule-based job rejection before LLM extraction.

Reads:   state["raw_jobs"]       (list[dict] — raw job dicts from fetch_node)
         state["profile"]        (ProfileData — provides reject_keywords)
Writes:  state["filtered_jobs"]  (list[Job] — jobs that passed all filters)
         state["token_stats"]    (forwarded unchanged from fetch_node)

Filtering rules applied in order:
  1. Non-tech title signals (sales, marketing, medical, etc.) -> discard
  2. Profile reject_keywords found anywhere in title+description+location -> discard
  3. No remote signal in title+description+location -> discard
     (signals: "remote", "latam", "latin america", "chile", "worldwide", "anywhere")

Failure modes:
  - No side effects. Purely in-memory filtering.
  - A job with an empty description passes rule 3 only if its title/location contains
    a remote signal.
"""
```

- [ ] **Step 3: Upgrade docstring in extract.py**

Replace the existing module docstring (lines 1-11 in `src/job_matcher/nodes/extract.py`) with this upgraded version:

```python
"""
Extract node — LLM-powered skill and seniority extraction.

Reads:   state["filtered_jobs"]  (list[Job])
Writes:  state["extracted_jobs"] (list[ExtractedJob] — with required_skills,
                                   seniority, is_remote, latam_eligible)
         state["token_stats"]    (prompt/completion tokens, cache hits, USD cost)

Side effects:
  - Reads  MongoDB `extractions` collection for each job_id (cache check)
  - Writes MongoDB `extractions` on every new LLM call (save result)
  - Emits per-job events into state["progress_queue"] if present (SSE streaming)

Performance:
  - Cache hits: 0 API tokens, near-zero latency
  - Cache misses: parallel ThreadPoolExecutor (max 5 workers)
  - Job description truncated to 1200 chars + HTML stripped before LLM call

Failure modes:
  - LLM returns malformed JSON: falls back to ExtractedJob with empty fields (logged)
  - DEEPSEEK_API_KEY missing: raises KeyError at make_llm() before any jobs processed
  - MongoDB down: cache check returns None (all jobs go to LLM), save is skipped silently
"""
```

- [ ] **Step 4: Add docstring to score.py**

Insert at the top of `src/job_matcher/nodes/score.py`, before the imports:

```python
"""
Score node — deterministic scoring of extracted jobs against the user profile.

Reads:   state["extracted_jobs"] (list[ExtractedJob])
         state["profile"]        (ProfileData — preferred_keywords drive stack score)
Writes:  state["scored_jobs"]    (list[ScoredJob] with score and breakdown)
         state["token_stats"]    (forwarded unchanged)

Scoring formula (see domain/scoring.py):
  score = stack(0-40) + seniority(-20/0/+10/+20) + ai_bonus(0/+10/+20) + recency(0-20)
  clamped to [-20.0, 100.0]

  stack:    keyword match against preferred_keywords; title match = 3x body match
  seniority: junior/intern/entry-level = -20; mid/ssr/semi-senior = +20;
             senior (not staff/principal/lead/architect) = +10; unknown = 0
  ai_bonus: Tier A (langgraph, multi-agent, rag, langchain, etc.) = +20;
            Tier B (openai, llm, machine learning, embedding) = +10
  recency:  today = +20; <=3 days = +15; <=7 = +10; <=14 = +5; older/unknown = 0

Failure modes:
  - No LLM calls, no I/O. All failures are logic bugs, not runtime errors.
"""
```

- [ ] **Step 5: Add docstring to rank.py**

Insert at the top of `src/job_matcher/nodes/rank.py`, before the imports:

```python
"""
Rank node — sort scored jobs and emit final top-N results.

Reads:   state["scored_jobs"]   (list[ScoredJob])
         state["output_format"] ("table" | "json")
Writes:  state["top_jobs"]      (list[ScoredJob] — top 10 by score, desc)
         state["token_stats"]   (forwarded unchanged)

Side effects:
  - Prints results to stdout in table or JSON format (for CLI use)
  - No MongoDB writes, no LLM calls

Failure modes:
  - Empty scored_jobs: returns empty top_jobs (no crash)
  - output_format not "json": falls through to table format
"""
```

- [ ] **Step 6: Run tests to confirm no regressions**

```bash
.venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: all tests pass (docstrings are additive — no logic changed)

- [ ] **Step 7: Commit**

```bash
git add src/job_matcher/nodes/
git commit -m "docs(nodes): add module docstrings to all 5 pipeline nodes"
```

---

### Task 10: Architecture doc

**Files:**
- Create: `docs/architecture.md`

**Interfaces:**
- No code changes — pure documentation.

- [ ] **Step 1: Create docs/architecture.md**

Create `docs/architecture.md` with this content:

```markdown
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
| extract -> score | `list[ExtractedJob]` | Jobs with `required_skills`, `seniority`, `is_remote`, `latam_eligible` |
| score -> rank | `list[ScoredJob]` | Jobs with `score` (float) and `breakdown` (per-component scores) |
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

**stack (0 – 40 pts):** Keyword match against `profile.preferred_keywords`. A keyword found in the job title scores 3 points; in the body or extracted skills scores 1 point. Raw points are scaled to a max of 40.

**seniority (-20 / 0 / +10 / +20):**
- `junior`, `trainee`, `intern`, `entry level`, `entry-level` → **-20**
- `mid-level`, `mid level`, `semi-senior`, `ssr`, `semi senior`, `midlevel` → **+20**
- `senior` (not `staff`, `principal`, `lead`, `architect`, `head of`) → **+10**
- Anything else → **0**

**ai_bonus (0 / +10 / +20):**
- Tier A terms in title or description (`langgraph`, `multi-agent`, `anthropic`, `rag`, `agentic`, `vector search`, `langchain`) → **+20**
- Tier B terms (`openai`, `llm`, `machine learning`, `embedding`, ` ai `) → **+10**
- None → **0**

**recency (0 – 20 pts):**
- Posted today → **+20**
- Posted ≤ 3 days ago → **+15**
- Posted ≤ 7 days ago → **+10**
- Posted ≤ 14 days ago → **+5**
- Older or `posted_at` is null → **0**

## Caching Strategy

The MongoDB `extractions` collection is an LLM result cache keyed by `job_id`. On a cache hit, `extract_node` returns the stored `required_skills`, `seniority`, `is_remote`, and `latam_eligible` fields with zero API tokens consumed and near-zero latency. On a cache miss, the LLM is called and the result is stored for future runs.

Why this matters: DeepSeek costs $0.14/1M input tokens and $1.10/1M completion tokens. A typical job description consumes ~400-600 prompt tokens. Without caching, extracting 100 jobs costs ~$0.05-0.07 per run. With a warm cache (second run of the same job listing), cost drops to $0.

Cache key hygiene: job IDs from Remotive and RemoteOK are stable across API calls for the same listing. A job that reappears in next week's fetch hits the cache automatically.

## Eval Layer

The eval harness lives in `evals/` and measures two properties of the pipeline:

**Layer 1 — Extraction accuracy:** DeepSeek is evaluated against 25 hand-crafted golden examples covering common and edge-case job postings. Four metrics are computed per example:

| Metric | Formula | What it measures |
|---|---|---|
| `skill_overlap` | Jaccard(predicted_skills, golden_skills) | How well the LLM identifies the correct skill set |
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

To find your results: open [smith.langchain.com](https://smith.langchain.com) → select project `job-matcher` → Experiments tab.
```

- [ ] **Step 2: Verify the Mermaid diagram renders (optional)**

If you have a Markdown preview available (VS Code with Mermaid plugin), open `docs/architecture.md` and confirm the diagram renders without errors.

- [ ] **Step 3: Commit**

```bash
git add docs/architecture.md
git commit -m "docs: architecture doc — pipeline, scoring formula, caching, eval layer, LangSmith"
```

---

## Self-Review Checklist

**Spec coverage check:**
- [x] `langsmith>=0.1` added → Task 1
- [x] `.env.example` LangSmith vars → Task 1
- [x] `evals/datasets/extraction_golden.jsonl` (25 examples) → Task 2
- [x] `evals/datasets/ranking_golden.jsonl` (5 scenarios) → Task 4
- [x] `evals/evaluators/extraction.py` (4 evaluators) → Task 3
- [x] `evals/evaluators/ranking.py` (precision_at_3) → Task 5
- [x] `evals/upload_datasets.py` → Task 6
- [x] `evals/run_extraction_eval.py` → Task 7
- [x] `evals/run_ranking_eval.py` → Task 8
- [x] Node docstrings (all 5) → Task 9
- [x] `docs/architecture.md` → Task 10
- [x] LangSmith tracing via env vars (zero production code change) → documented in Task 1 + Task 10
- [x] DeepSeek used throughout (no OpenAI) → make_llm() in Task 7+8

**Type consistency:**
- `skill_overlap`, `seniority_match`, `remote_match`, `latam_match` — defined in Task 3, used in Task 7 ✓
- `precision_at_3` — defined in Task 5, used in Task 8 ✓
- `extraction_target` returns `{required_skills, seniority, is_remote, latam_eligible}` — matches evaluator `outputs` key expectations ✓
- `ranking_target` returns `{top_jobs: [{id, score}]}` — matches `precision_at_3` expectation of `outputs.get("top_jobs")` ✓
- `MatcherState` requires `output_format` field — set to `"json"` in ranking_target ✓

**Parallel execution guidance:**
- Tasks 2, 3, 4, 9, 10 are all independent — can run in parallel
- Task 5 depends on understanding Task 4 schema (already included inline)
- Tasks 6, 7, 8 depend on Tasks 2+3+4+5 completing first
- Recommended wave order: [1] → [2,3,4,9,10 parallel] → [5,6 parallel] → [7,8 parallel]
