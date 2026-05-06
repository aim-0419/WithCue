from __future__ import annotations

from typing import Any, Dict, List


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def extract_shoulder_front_raise_issues(compare_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    feature_errors = compare_result.get("feature_errors", {}) or {}
    motion_similarity = compare_result.get("motion_similarity")
    posture_similarity = compare_result.get("posture_similarity")
    phase = str(compare_result.get("phase", "unknown"))

    shoulder_error = float(feature_errors.get("shoulder_rise", 0.0))
    if shoulder_error > 0.20:
        severity = _clamp01((shoulder_error - 0.20) / 0.8)
        issues.append(
            {
                "error_type": "shoulder_elevation",
                "body_part": "어깨",
                "severity": severity,
                "instant_feedback": "팔을 들 때 어깨가 같이 올라갑니다. 승모근 힘을 줄이고 들어 주세요.",
                "metric_name": "shoulder_rise_error",
                "metric_value": shoulder_error,
            }
        )

    trunk_error = float(feature_errors.get("trunk", 0.0))
    if trunk_error > 0.18:
        severity = _clamp01((trunk_error - 0.18) / 0.75)
        issues.append(
            {
                "error_type": "trunk_compensation",
                "body_part": "몸통",
                "severity": severity,
                "instant_feedback": "몸통이 함께 움직입니다. 상체를 세운 상태를 유지해 주세요.",
                "metric_name": "trunk_error",
                "metric_value": trunk_error,
            }
        )

    elbow_error = float(feature_errors.get("elbow_angle", 0.0))
    if elbow_error > 0.16:
        severity = _clamp01((elbow_error - 0.16) / 0.7)
        issues.append(
            {
                "error_type": "elbow_flexion",
                "body_part": "팔꿈치",
                "severity": severity,
                "instant_feedback": "팔꿈치가 과하게 굽혀집니다. 팔을 조금 더 편 상태로 올려 주세요.",
                "metric_name": "elbow_error",
                "metric_value": elbow_error,
            }
        )

    arm_raise_error = float(feature_errors.get("arm_raise", 0.0))
    if (
        phase in {"peak", "lowering", "transition"}
        and motion_similarity is not None
        and float(motion_similarity) < 84.0
        and arm_raise_error > 0.18
    ):
        severity = _clamp01(max((84.0 - float(motion_similarity)) / 30.0, (arm_raise_error - 0.18) / 0.8))
        issues.append(
            {
                "error_type": "arm_raise_low",
                "body_part": "팔",
                "severity": severity,
                "instant_feedback": "팔 높이가 기준보다 낮습니다. 가능한 범위에서 조금 더 들어 올려 주세요.",
                "metric_name": "arm_raise_error",
                "metric_value": arm_raise_error,
            }
        )

    if posture_similarity is not None and float(posture_similarity) < 78.0 and not issues:
        severity = _clamp01((78.0 - float(posture_similarity)) / 30.0)
        issues.append(
            {
                "error_type": "posture_quality_low",
                "body_part": "자세",
                "severity": severity,
                "instant_feedback": "팔을 드는 동안 자세가 흐트러집니다. 상체와 어깨 정렬을 유지해 주세요.",
                "metric_name": "posture_similarity",
                "metric_value": float(posture_similarity),
            }
        )

    return issues
