"""
conftest.py -- test configuration and fixtures.

The fetch_node in nodes/fetch.py uses `from ..fetcher import fetch_jobs` which
creates a local binding in the nodes.fetch module namespace.  Tests that patch
`job_matcher.fetcher.fetch_jobs` (the canonical module location) would not
normally intercept that local binding.

The `sync_fetch_patch` autouse fixture installs a transparent proxy on
`job_matcher.nodes.fetch.fetch_jobs` that always delegates to whatever
`job_matcher.fetcher.fetch_jobs` resolves to at call time.  This means a
`patch("job_matcher.fetcher.fetch_jobs", mock)` inside a test correctly
intercepts calls made through fetch_node without modifying any source file.
"""
import importlib
import pytest


@pytest.fixture(autouse=True)
def sync_fetch_patch():
    """Make nodes.fetch.fetch_jobs delegate through fetcher module at call time."""
    import job_matcher.fetcher as _fetcher_mod
    import job_matcher.nodes.fetch as _fetch_node_mod

    def _proxy(*args, **kwargs):
        return _fetcher_mod.fetch_jobs(*args, **kwargs)

    original = _fetch_node_mod.fetch_jobs
    _fetch_node_mod.fetch_jobs = _proxy
    yield
    _fetch_node_mod.fetch_jobs = original
