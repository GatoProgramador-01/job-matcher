"""
Job fetcher — uses Remotive.com's free public API.

Remotive returns real remote jobs with no API key required.
hiring.cafe has no public API endpoint; we fall back to Remotive.
"""
import hashlib
import json
import time
from pathlib import Path

import requests

CACHE_PATH = "cache.json"


class FetchError(Exception):
    pass


def _job_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


# ── Remotive ──────────────────────────────────────────────────────────────────

_REMOTIVE_BASE = "https://remotive.com/api/remote-jobs"

_CATEGORIES = ["software-dev", "devops-sysadmin", "data"]


def _fetch_category(category: str) -> list[dict]:
    """Fetch one Remotive category page."""
    params = {"category": category}
    resp = requests.get(_REMOTIVE_BASE, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json().get("jobs", [])


def _fetch_remotive(query: str, limit: int) -> list[dict]:
    """Fetch from Remotive's free public API — category-filtered for tech roles."""
    seen_ids: set = set()
    results: list[dict] = []
    for category in _CATEGORIES:
        for raw in _fetch_category(category):
            jid = str(raw.get("id", ""))
            if jid not in seen_ids:
                seen_ids.add(jid)
                results.append(_normalize_remotive(raw))
    return results


def _normalize_remotive(raw: dict) -> dict:
    apply_url = raw.get("url", "")
    return {
        "id": str(raw.get("id", "")) or _job_id(apply_url),
        "title": raw.get("title", ""),
        "company": raw.get("company_name", ""),
        "location": raw.get("candidate_required_location", "Worldwide"),
        "remote": True,
        "description": raw.get("description", ""),
        "apply_url": apply_url,
        "source": "remotive",
        "posted_at": (raw.get("publication_date") or "")[:10] or None,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_jobs(
    base_url: str,                          # kept for signature compat, ignored
    query: str = "backend developer remote",
    limit: int = 50,
) -> list[dict]:
    """
    Fetch remote job listings.

    Tries Remotive's free public API. Retries once on transient failures.
    `base_url` is accepted for backward-compat but not used.
    """
    for attempt in range(2):
        try:
            return _fetch_remotive(query, limit)
        except requests.RequestException as exc:
            if attempt == 1:
                raise FetchError(str(exc)) from exc
            time.sleep(3)
    return []


def load_cache(path: str = CACHE_PATH) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    return set(json.loads(p.read_text(encoding="utf-8")))


def save_cache(ids: set[str], path: str = CACHE_PATH) -> None:
    Path(path).write_text(json.dumps(list(ids), indent=2), encoding="utf-8")
