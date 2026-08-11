# job-matcher

Personal job matcher CLI — fetches jobs from [hiring.cafe](https://hiring.cafe) and ranks the top 10 by fit against your developer profile.

**Stack:** Python 3.11 · LangGraph · DeepSeek (`deepseek-chat`) · requests · Pydantic v2

## Pipeline

```
fetch_node  →  filter_node  →  extract_node  →  score_node  →  rank_node
hiring.cafe    hard filters    DeepSeek LLM     deterministic    top 10
+ cache                        structured        formula          output
                               extraction
```

## Setup

```bash
# 1. Clone and install
git clone https://github.com/GatoProgramador-01/job-matcher.git
cd job-matcher
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 2. Configure secrets
cp .env.example .env
# Edit .env and add your DEEPSEEK_API_KEY

# 3. Configure your profile
cp profile.example.json profile.json
# Edit profile.json with your experience and search criteria
```

## Usage

```bash
# Ranked table output
python -m job_matcher.cli run

# JSON output (for piping)
python -m job_matcher.cli run --json

# Custom profile path
python -m job_matcher.cli run --profile /path/to/your/profile.json
```

## Tests (no network required)

```bash
pytest tests/ -v
```

## Scoring

| Factor | Max pts | Description |
|--------|---------|-------------|
| Stack overlap | 40 | Keywords in title (3×) and description (1×) vs. your preferred stack |
| Seniority fit | 20 | mid/semi-senior = +20, senior = +10, junior/intern = −20 |
| AI/LLM bonus | 20 | Tier A (LangGraph, RAG, multi-agent) or Tier B (OpenAI, LLM) |
| Recency | 20 | Today = 20 pts, older posts decay to 0 |

Hard filters: `reject_keywords` from your profile + no remote/LatAm signal = immediate discard.

## Security

- `.env` is gitignored — never commit API keys
- `profile.json` is gitignored — personal data stays local
- `cache.json` is gitignored — daily state stays local
