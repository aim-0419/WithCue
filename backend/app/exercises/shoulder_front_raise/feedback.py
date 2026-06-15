from __future__ import annotations

from typing import Any, Dict, List

from app.exercises.shared.common import (
    build_issue,
    clamp01,
    feature_error,
    phase_is,
    similarity_gap,
    top_features,
)


def extract_shoulder_front_raise_issues(compare_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    motion_similarity = compare_result.get("motion_similarity")
    posture_similarity = compare_result.get("posture_similarity")
    phase = str(compare_result.get("phase", "unknown"))
    leaders = top_features(compare_result, limit=3)

    shoulder_error = feature_error(compare_result, "shoulder_rise")
    trunk_error = feature_error(compare_result, "trunk")
    elbow_error = feature_error(compare_result, "elbow_angle")
    arm_raise_error = feature_error(compare_result, "arm_raise")
    horizontal_error = feature_error(compare_result, "arm_horizontal_error")
    support_error = feature_error(compare_result, "support_dist")

    if shoulder_error > 0.17 and "shoulder_rise" in leaders[:2]:
        severity = max(
            clamp01((shoulder_error - 0.17) / 0.7),
            similarity_gap(posture_similarity, 82.0),
        )
        issues.append(
            build_issue(
                error_type="shoulder_elevation",
                body_part="어깨",
                severity=severity,
                instant_feedback="팔을 들 때 어깨가 같이 올라갑니다. 승모근 힘을 줄이고 들어 주세요.",
                metric_name="shoulder_rise_error",
                metric_value=shoulder_error,
            )
        )

    if trunk_error > 0.16 and "trunk" in leaders[:2]:
        severity = max(
            clamp01((trunk_error - 0.16) / 0.7),
            similarity_gap(posture_similarity, 82.0),
        )
        issues.append(
            build_issue(
                error_type="trunk_compensation",
                body_part="몸통",
                severity=severity,
                instant_feedback="몸통이 함께 움직입니다. 상체를 세운 상태를 유지해 주세요.",
                metric_name="trunk_error",
                metric_value=trunk_error,
            )
        )

    if elbow_error > 0.14 and "elbow_angle" in leaders[:2]:
        severity = clamp01((elbow_error - 0.14) / 0.65)
        issues.append(
            build_issue(
                error_type="elbow_flexion",
                body_part="팔꿈치",
                severity=severity,
                instant_feedback="팔꿈치가 과하게 굽혀집니다. 팔을 조금 더 편 상태로 올려 주세요.",
                metric_name="elbow_error",
                metric_value=elbow_error,
            )
        )

    if horizontal_error > 0.16 and "arm_horizontal_error" in leaders[:2]:
        severity = clamp01((horizontal_error - 0.16) / 0.65)
        issues.append(
            build_issue(
                error_type="arm_path_drift",
                body_part="팔",
                severity=severity,
                instant_feedback="팔 경로가 흔들립니다. 정면 라인을 따라 같은 궤적으로 들어 주세요.",
                metric_name="arm_horizontal_error",
                metric_value=horizontal_error,
            )
        )

    if (
        phase_is(compare_result, {"raising", "peak", "lowering", "transition"})
        and arm_raise_error > 0.16
        and "arm_raise" in leaders[:2]
    ):
        severity = max(
            clamp01((arm_raise_error - 0.16) / 0.7),
            similarity_gap(motion_similarity, 86.0),
        )
        issues.append(
            build_issue(
                error_type="arm_raise_low",
                body_part="팔",
                severity=severity,
                instant_feedback="팔 높이가 기준보다 낮습니다. 가능한 범위에서 조금 더 들어 올려 주세요.",
                metric_name="arm_raise_error",
                metric_value=arm_raise_error,
            )
        )

    if support_error > 0.16 and "support_dist" in leaders[:2]:
        severity = clamp01((support_error - 0.16) / 0.65)
        issues.append(
            build_issue(
                error_type="support_instability",
                body_part="자세",
                severity=severity,
                instant_feedback="중심이 흔들립니다. 몸통과 하체 지지를 안정적으로 유지해 주세요.",
                metric_name="support_dist_error",
                metric_value=support_error,
            )
        )

    if phase == "lowering" and arm_raise_error > 0.14 and "arm_raise" in leaders:
        severity = clamp01((arm_raise_error - 0.14) / 0.6)
        issues.append(
            build_issue(
                error_type="lowering_control",
                body_part="팔",
                severity=severity,
                instant_feedback="팔을 내릴 때도 힘을 풀지 말고 천천히 제어해 주세요.",
                metric_name="lowering_error",
                metric_value=arm_raise_error,
            )
        )

    if posture_similarity is not None and float(posture_similarity) < 78.0 and not issues:
        severity = clamp01((78.0 - float(posture_similarity)) / 30.0)
        issues.append(
            build_issue(
                error_type="posture_quality_low",
                body_part="자세",
                severity=severity,
                instant_feedback="팔을 드는 동안 자세가 흐트러집니다. 상체와 어깨 정렬을 유지해 주세요.",
                metric_name="posture_similarity",
                metric_value=float(posture_similarity),
            )
        )

    return issues
