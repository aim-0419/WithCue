from __future__ import annotations

from typing import Any, Dict, List


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _get_first(result: Dict[str, Any], keys, default=0.0) -> float:
    for k in keys:
        if k in result:
            return float(result[k])
    return float(default)


def extract_neck_rotation_issues(compare_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    feature_errors = compare_result.get("feature_errors", {}) or {}
    motion_similarity = compare_result.get("motion_similarity")
    posture_similarity = compare_result.get("posture_similarity")

    neck_turn_error = float(feature_errors.get("neck_turn_angle", 0.0))
    if motion_similarity is not None and float(motion_similarity) < 84.0 and neck_turn_error > 0.18:
        severity = _clamp01(max((84.0 - float(motion_similarity)) / 30.0, (neck_turn_error - 0.18) / 0.9))
        issues.append(
            {
                "error_type": "rotation_rom_low",
                "body_part": "목",
                "severity": severity,
                "instant_feedback": "회전 범위가 작습니다. 통증 없는 범위에서 조금 더 돌려 주세요.",
                "metric_name": "neck_turn_error",
                "metric_value": neck_turn_error,
            }
        )

    trunk_error = float(feature_errors.get("trunk_rotation", 0.0))
    shoulder_error = float(feature_errors.get("shoulder_line_angle", 0.0))
    comp_error = max(trunk_error, shoulder_error)
    if comp_error > 0.18:
        severity = _clamp01((comp_error - 0.18) / 0.8)
        issues.append(
            {
                "error_type": "neck_compensation",
                "body_part": "어깨/몸통",
                "severity": severity,
                "instant_feedback": "목 회전 시 어깨나 몸통이 같이 따라갑니다. 목만 분리해서 움직여 주세요.",
                "metric_name": "compensation_error",
                "metric_value": comp_error,
            }
        )

    head_tilt_error = float(feature_errors.get("head_tilt", 0.0))
    if head_tilt_error > 0.18:
        severity = _clamp01((head_tilt_error - 0.18) / 0.8)
        issues.append(
            {
                "error_type": "rotation_asymmetry",
                "body_part": "목",
                "severity": severity,
                "instant_feedback": "고개가 기울어집니다. 턱과 정수리를 곧게 유지한 채 회전해 주세요.",
                "metric_name": "head_tilt_error",
                "metric_value": head_tilt_error,
            }
        )

    if posture_similarity is not None and float(posture_similarity) < 80.0 and not issues:
        severity = _clamp01((80.0 - float(posture_similarity)) / 30.0)
        issues.append(
            {
                "error_type": "posture_quality_low",
                "body_part": "자세",
                "severity": severity,
                "instant_feedback": "목을 돌리는 동안 자세가 흐트러집니다. 고개와 어깨 정렬을 유지해 주세요.",
                "metric_name": "posture_similarity",
                "metric_value": float(posture_similarity),
            }
        )

    return issues
