"""Extraction evaluators for job matcher — Jaccard skill overlap + exact-match metrics."""


def skill_overlap(outputs: dict, reference_outputs: dict) -> dict:
    """
    Score skill extraction quality using Jaccard index (intersection/union).

    Args:
        outputs: Model output dict with optional "required_skills" list
        reference_outputs: Golden reference dict with "required_skills" list

    Returns:
        {"key": "skill_overlap", "score": float in [0.0, 1.0]}
    """
    predicted = {s.lower() for s in outputs.get("required_skills") or []}
    golden = {s.lower() for s in reference_outputs.get("required_skills") or []}
    union = predicted | golden
    score = len(predicted & golden) / len(union) if union else 1.0
    return {"key": "skill_overlap", "score": score}


def seniority_match(outputs: dict, reference_outputs: dict) -> dict:
    """
    Score seniority extraction — exact match only (junior/mid/senior/lead).

    Args:
        outputs: Model output dict with optional "seniority" string
        reference_outputs: Golden reference dict with "seniority" string

    Returns:
        {"key": "seniority_match", "score": 1.0 if match else 0.0}
    """
    score = float(outputs.get("seniority") == reference_outputs.get("seniority"))
    return {"key": "seniority_match", "score": score}


def remote_match(outputs: dict, reference_outputs: dict) -> dict:
    """
    Score remote eligibility extraction — exact match.

    Args:
        outputs: Model output dict with optional "is_remote" bool
        reference_outputs: Golden reference dict with "is_remote" bool

    Returns:
        {"key": "remote_match", "score": 1.0 if match else 0.0}
    """
    score = float(outputs.get("is_remote") == reference_outputs.get("is_remote"))
    return {"key": "remote_match", "score": score}


def latam_match(outputs: dict, reference_outputs: dict) -> dict:
    """
    Score LATAM eligibility extraction — exact match.

    Args:
        outputs: Model output dict with optional "latam_eligible" bool
        reference_outputs: Golden reference dict with "latam_eligible" bool

    Returns:
        {"key": "latam_match", "score": 1.0 if match else 0.0}
    """
    score = float(outputs.get("latam_eligible") == reference_outputs.get("latam_eligible"))
    return {"key": "latam_match", "score": score}
