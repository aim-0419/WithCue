from __future__ import annotations

from typing import Any, Dict, List


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def extract_birddog_issues(compare_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    feature_errors = compare_result.get("feature_errors", {}) or {}
    motion_similarity = compare_result.get("motion_similarity")
    posture_similarity = compare_result.get("posture_similarity")
    pair_a_error = float(compare_result.get("pair_a_error", 0.0))
    pair_b_error = float(compare_result.get("pair_b_error", 0.0))

    motion_group_error = max(
        pair_a_error,
        pair_b_error,
        float(feature_errors.get("right_arm", 0.0)),
        float(feature_errors.get("left_leg", 0.0)),
        float(feature_errors.get("left_arm", 0.0)),
        float(feature_errors.get("right_leg", 0.0)),
    )
    if motion_similarity is not None and float(motion_similarity) < 82.0 and motion_group_error > 0.18:
        severity = _clamp01(max((82.0 - float(motion_similarity)) / 30.0, (motion_group_error - 0.18) / 0.8))
        issues.append(
            {
                "error_type": "rom_low",
                "body_part": "팔/다리",
                "severity": severity,
                "instant_feedback": "팔과 다리의 가동범위를 기준보다 조금 더 확보해 주세요.",
                "metric_name": "motion_group_error",
                "metric_value": motion_group_error,
            }
        )

    trunk_error = float(feature_errors.get("trunk", 0.0))
    pelvic_error = float(feature_errors.get("pelvic", 0.0))
    if max(trunk_error, pelvic_error) > 0.16:
        severity = _clamp01((max(trunk_error, pelvic_error) - 0.16) / 0.7)
        issues.append(
            {
                "error_type": "balance_gap",
                "body_part": "몸통",
                "severity": severity,
                "instant_feedback": "좌우 균형이 흔들립니다. 몸통 중심을 고정해 주세요.",
                "metric_name": "trunk_pelvic_error",
                "metric_value": max(trunk_error, pelvic_error),
            }
        )

    joint_error = max(
        float(feature_errors.get("right_elbow_angle", 0.0)),
        float(feature_errors.get("left_elbow_angle", 0.0)),
        float(feature_errors.get("left_knee_angle", 0.0)),
        float(feature_errors.get("right_knee_angle", 0.0)),
        float(feature_errors.get("right_arm_h_err", 0.0)),
        float(feature_errors.get("left_leg_h_err", 0.0)),
        float(feature_errors.get("left_arm_h_err", 0.0)),
        float(feature_errors.get("right_leg_h_err", 0.0)),
    )
    if joint_error > 0.22 or (posture_similarity is not None and float(posture_similarity) < 80.0):
        severity = _clamp01(max((joint_error - 0.22) / 0.8, (80.0 - float(posture_similarity or 100.0)) / 30.0))
        issues.append(
            {
                "error_type": "joint_compensation",
                "body_part": "관절 정렬",
                "severity": severity,
                "instant_feedback": "관절 정렬이 무너집니다. 허리/어깨 라인을 유지해 주세요.",
                "metric_name": "joint_error",
                "metric_value": joint_error,
            }
        )

    return issues
