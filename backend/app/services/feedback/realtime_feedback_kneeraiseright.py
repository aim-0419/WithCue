from __future__ import annotations

from typing import Any, Dict, List


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def extract_knee_raise_right_issues(compare_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    feature_errors = compare_result.get("feature_errors", {}) or {}
    phase = str(compare_result.get("phase", "unknown"))
    motion_similarity = compare_result.get("motion_similarity")
    posture_similarity = compare_result.get("posture_similarity")

    trunk_error = float(feature_errors.get("trunk", 0.0))
    if trunk_error > 0.28:
        severity = _clamp01((trunk_error - 0.28) / 0.9)
        issues.append(
            {
                "error_type": "trunk_sway",
                "body_part": "몸통",
                "severity": severity,
                "instant_feedback": "다리를 들 때 몸통이 같이 흔들립니다. 상체를 고정해 주세요.",
                "metric_name": "trunk_error",
                "metric_value": trunk_error,
            }
        )

    pelvic_error = float(feature_errors.get("pelvic", 0.0))
    if pelvic_error > 0.24:
        severity = _clamp01((pelvic_error - 0.24) / 0.75)
        issues.append(
            {
                "error_type": "pelvic_instability",
                "body_part": "골반",
                "severity": severity,
                "instant_feedback": "골반 흔들림이 큽니다. 골반을 수평으로 유지해 주세요.",
                "metric_name": "pelvic_error",
                "metric_value": pelvic_error,
            }
        )

    knee_error = float(feature_errors.get("knee_angle", 0.0))
    if knee_error > 0.22:
        severity = _clamp01((knee_error - 0.22) / 0.85)
        issues.append(
            {
                "error_type": "knee_flexion",
                "body_part": "무릎",
                "severity": severity,
                "instant_feedback": "무릎이 굽혀집니다. 다리를 더 곧게 유지해 주세요.",
                "metric_name": "knee_error",
                "metric_value": knee_error,
            }
        )

    ankle_error = float(feature_errors.get("ankle_height", 0.0))
    if (
        phase in {"peak", "lowering", "transition"}
        and ankle_error > 0.20
        and motion_similarity is not None
        and float(motion_similarity) < 85.0
    ):
        severity = _clamp01((ankle_error - 0.20) / 0.9)
        issues.append(
            {
                "error_type": "ankle_height_rom",
                "body_part": "다리",
                "severity": severity,
                "instant_feedback": "다리 높이가 기준보다 낮습니다. 통증 없는 범위에서 조금 더 올려 주세요.",
                "metric_name": "ankle_height_error",
                "metric_value": ankle_error,
            }
        )

    if posture_similarity is not None and float(posture_similarity) < 78.0 and not issues:
        severity = _clamp01((78.0 - float(posture_similarity)) / 30.0)
        issues.append(
            {
                "error_type": "posture_quality_low",
                "body_part": "자세",
                "severity": severity,
                "instant_feedback": "다리를 드는 동안 자세가 흐트러집니다. 상체와 골반 정렬을 유지해 주세요.",
                "metric_name": "posture_similarity",
                "metric_value": float(posture_similarity),
            }
        )

    return issues
