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
    mock_result.content = '{"required_skills":["Python","FastAPI"],"seniority":"mid","is_remote":true,"latam_eligible":true}'
    mock_result.response_metadata = {}

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

    with patch("job_matcher.nodes.extract._make_llm", return_value=mock_llm), \
         patch("job_matcher.nodes.extract.mongo_db.get_extraction", return_value=None), \
         patch("job_matcher.nodes.extract.mongo_db.save_extraction"):
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
