import hashlib
import json
import time
from pathlib import Path

import requests

CACHE_PATH = "cache.json"
_REMOTE_SIGNALS_QUERY = "remote LatAm"


class FetchError(Exception):
    pass


def _job_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def fetch_jobs(base_url: str, query: str = "backend developer remote", limit: int = 50) -> list[dict]:
    url = f"{base_url.rstrip('/')}/api/jobs/search"
    payload = {
        "query": f"{query} {_REMOTE_SIGNALS_QUERY}",
        "filters": {"remote": True},
        "page": 1,
        "limit": limit,
    }
    for attempt in range(2):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 429 and attempt == 0:
                time.sleep(5)
                continue
            resp.raise_for_status()
            data = resp.json()
            jobs = data.get("jobs") or data.get("results") or []
            return [_normalize(j) for j in jobs]
        except requests.RequestException as exc:
            if attempt == 1:
                raise FetchError(str(exc)) from exc
            time.sleep(5)
    return []


def _normalize(raw: dict) -> dict:
    apply_url = raw.get("applyUrl") or raw.get("apply_url") or raw.get("url", "")
    return {
        "id": raw.get("id") or _job_id(apply_url),
        "title": raw.get("title", ""),
        "company": raw.get("company", ""),
        "location": raw.get("location"),
        "remote": bool(raw.get("remote", False)),
        "description": raw.get("description") or raw.get("body") or "",
        "apply_url": apply_url,
        "source": raw.get("source") or raw.get("ats", ""),
        "posted_at": (raw.get("postedAt") or raw.get("posted_at") or "")[:10] or None,
    }


def load_cache(path: str = CACHE_PATH) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    return set(json.loads(p.read_text(encoding="utf-8")))


def save_cache(ids: set[str], path: str = CACHE_PATH) -> None:
    Path(path).write_text(json.dumps(list(ids), indent=2), encoding="utf-8")
