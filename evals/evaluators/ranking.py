"""Ranking evaluators for job matcher — precision@3 and hit metrics."""


def precision_at_3(outputs: dict, reference_outputs: dict) -> dict:
    """
    Score job ranking quality using precision at k=3.

    Counts how many of the top 3 ranked jobs appear in the expected top IDs,
    divided by the size of the expected set. Caps results at 3 positions.

    Args:
        outputs: Model output dict with optional "top_jobs" list of dicts with "id" keys
        reference_outputs: Golden reference dict with "expected_top_ids" list of job IDs

    Returns:
        {"key": "precision_at_3", "score": float in [0.0, 1.0]}

    Examples:
        >>> precision_at_3(
        ...     {"top_jobs": [{"id": "j1"}, {"id": "j7"}, {"id": "j3"}]},
        ...     {"expected_top_ids": ["j1", "j7", "j3"]}
        ... )
        {"key": "precision_at_3", "score": 1.0}

        >>> precision_at_3(
        ...     {"top_jobs": [{"id": "j1"}, {"id": "j2"}, {"id": "j5"}]},
        ...     {"expected_top_ids": ["j1", "j3"]}
        ... )
        {"key": "precision_at_3", "score": 0.5}
    """
    top_ids = [j["id"] for j in (outputs.get("top_jobs") or [])][:3]
    expected = set(reference_outputs.get("expected_top_ids") or [])
    hits = sum(1 for jid in top_ids if jid in expected)
    score = hits / len(expected) if expected else 0.0
    return {"key": "precision_at_3", "score": score}
