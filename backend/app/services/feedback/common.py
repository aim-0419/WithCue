from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def feature_error(compare_result: Dict[str, Any], name: str, default: float = 0.0) -> float:
    feature_errors = compare_result.get("feature_errors", {}) or {}
    return float(feature_errors.get(name, default))


def phase_is(compare_result: Dict[str, Any], phases: Iterable[str]) -> bool:
    phase = str(compare_result.get("phase", "unknown"))
    return phase in set(phases)


def top_features(compare_result: Dict[str, Any], limit: int = 3) -> List[str]:
    feature_errors = compare_result.get("feature_errors", {}) or {}
    ordered = sorted(
        feature_errors.items(),
        key=lambda item: float(item[1]),
        reverse=True,
    )
    return [name for name, _ in ordered[: max(1, int(limit))]]


def is_top_feature(compare_result: Dict[str, Any], feature_names: Sequence[str], *, top_n: int = 2) -> bool:
    leaders = set(top_features(compare_result, limit=top_n))
    return any(name in leaders for name in feature_names)


def similarity_gap(similarity: Any, threshold: float, scale: float = 30.0) -> float:
    if similarity is None:
        return 0.0
    return max(0.0, (float(threshold) - float(similarity)) / float(scale))


def build_issue(
    *,
    error_type: str,
    body_part: str,
    severity: float,
    instant_feedback: str,
    metric_name: str,
    metric_value: float,
) -> Dict[str, Any]:
    return {
        "error_type": error_type,
        "body_part": body_part,
        "severity": clamp01(severity),
        "instant_feedback": instant_feedback,
        "metric_name": metric_name,
        "metric_value": float(metric_value),
    }
