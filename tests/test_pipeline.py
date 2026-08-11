import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from job_matcher.fetcher import _normalize, load_cache, save_cache
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


def test_fetch_jobs_calls_post():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"jobs": FIXTURES[:3]}
    mock_resp.raise_for_status = MagicMock()

    with patch("job_matcher.fetcher.requests.post", return_value=mock_resp) as mock_post:
        from job_matcher.fetcher import fetch_jobs
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


def test_extract_node_uses_llm_structured_output(monkeypatch):
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


def test_full_pipeline_offline(tmp_path, monkeypatch):
    from unittest.mock import patch, MagicMock
    from job_matcher.pipeline import build_pipeline

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
