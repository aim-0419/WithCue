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


def extract_neck_rotation_issues(compare_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    motion_similarity = compare_result.get("motion_similarity")
    posture_similarity = compare_result.get("posture_similarity")
    phase = str(compare_result.get("phase", "unknown"))
    leaders = top_features(compare_result, limit=3)

    neck_turn_error = feature_error(compare_result, "neck_turn_angle")
    trunk_error = feature_error(compare_result, "trunk_rotation")
    shoulder_error = feature_error(compare_result, "shoulder_line_angle")
    head_tilt_error = feature_error(compare_result, "head_tilt")

    if (
        phase_is(compare_result, {"turning_left", "turning_right", "peak", "transition"})
        and neck_turn_error > 0.16
        and "neck_turn_angle" in leaders[:2]
    ):
        severity = max(
            similarity_gap(motion_similarity, 86.0),
            clamp01((neck_turn_error - 0.16) / 0.75),
        )
        issues.append(
            build_issue(
                error_type="rotation_rom_low",
                body_part="목",
                severity=severity,
                instant_feedback="회전 범위가 작습니다. 통증 없는 범위에서 조금 더 돌려 주세요.",
                metric_name="neck_turn_error",
                metric_value=neck_turn_error,
            )
        )

    if trunk_error > 0.15 and "trunk_rotation" in leaders[:2]:
        severity = max(
            clamp01((trunk_error - 0.15) / 0.7),
            similarity_gap(posture_similarity, 82.0),
        )
        issues.append(
            build_issue(
                error_type="trunk_compensation",
                body_part="몸통",
                severity=severity,
                instant_feedback="몸통이 같이 회전합니다. 시선은 유지한 채 목만 분리해서 돌려 주세요.",
                metric_name="trunk_rotation_error",
                metric_value=trunk_error,
            )
        )

    if shoulder_error > 0.15 and "shoulder_line_angle" in leaders[:2]:
        severity = max(
            clamp01((shoulder_error - 0.15) / 0.7),
            similarity_gap(posture_similarity, 82.0),
        )
        issues.append(
            build_issue(
                error_type="shoulder_compensation",
                body_part="어깨",
                severity=severity,
                instant_feedback="어깨가 함께 돌아갑니다. 어깨는 정면에 둔 채 목만 움직여 주세요.",
                metric_name="shoulder_line_error",
                metric_value=shoulder_error,
            )
        )

    if head_tilt_error > 0.16 and "head_tilt" in leaders[:2]:
        severity = clamp01((head_tilt_error - 0.16) / 0.75)
        issues.append(
            build_issue(
                error_type="head_tilt_compensation",
                body_part="목",
                severity=severity,
                instant_feedback="고개가 기울어집니다. 턱과 정수리를 곧게 유지한 채 회전해 주세요.",
                metric_name="head_tilt_error",
                metric_value=head_tilt_error,
            )
        )

    if phase == "center" and neck_turn_error > 0.14 and "neck_turn_angle" in leaders:
        severity = clamp01((neck_turn_error - 0.14) / 0.6)
        issues.append(
            build_issue(
                error_type="center_return_control",
                body_part="목",
                severity=severity,
                instant_feedback="정면으로 돌아올 때도 천천히 제어하면서 가운데 정렬을 맞춰 주세요.",
                metric_name="center_return_error",
                metric_value=neck_turn_error,
            )
        )

    if posture_similarity is not None and float(posture_similarity) < 80.0 and not issues:
        severity = clamp01((80.0 - float(posture_similarity)) / 30.0)
        issues.append(
            build_issue(
                error_type="posture_quality_low",
                body_part="자세",
                severity=severity,
                instant_feedback="목을 돌리는 동안 자세가 흐트러집니다. 고개와 어깨 정렬을 유지해 주세요.",
                metric_name="posture_similarity",
                metric_value=float(posture_similarity),
            )
        )

    return issues
