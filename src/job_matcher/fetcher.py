# Backward-compat re-export — canonical location: infrastructure.hiring_cafe
from .infrastructure.hiring_cafe import (
    FetchError,
    fetch_jobs,
    fetch_remoteok,
    load_cache,
    save_cache,
    _normalize_remoteok,
    _job_id,
)

__all__ = [
    "FetchError",
    "fetch_jobs",
    "fetch_remoteok",
    "load_cache",
    "save_cache",
    "_normalize_remoteok",
    "_job_id",
]
