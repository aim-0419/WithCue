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


def extract_knee_raise_right_issues(compare_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    phase = str(compare_result.get("phase", "unknown"))
    motion_similarity = compare_result.get("motion_similarity")
    posture_similarity = compare_result.get("posture_similarity")
    leaders = top_features(compare_result, limit=3)

    trunk_error = feature_error(compare_result, "trunk")
    pelvic_error = feature_error(compare_result, "pelvic")
    knee_error = feature_error(compare_result, "knee_angle")
    ankle_error = feature_error(compare_result, "ankle_height")
    hip_error = feature_error(compare_result, "hip_flexion")

    if trunk_error > 0.22 and "trunk" in leaders[:2]:
        severity = max(
            clamp01((trunk_error - 0.22) / 0.8),
            similarity_gap(posture_similarity, 82.0),
        )
        issues.append(
            build_issue(
                error_type="trunk_sway",
                body_part="몸통",
                severity=severity,
                instant_feedback="다리를 들 때 몸통이 같이 흔들립니다. 상체를 세운 상태로 고정해 주세요.",
                metric_name="trunk_error",
                metric_value=trunk_error,
            )
        )

    if pelvic_error > 0.20 and "pelvic" in leaders[:2]:
        severity = max(
            clamp01((pelvic_error - 0.20) / 0.7),
            similarity_gap(posture_similarity, 82.0),
        )
        issues.append(
            build_issue(
                error_type="pelvic_instability",
                body_part="골반",
                severity=severity,
                instant_feedback="골반 흔들림이 큽니다. 골반을 수평으로 유지해 주세요.",
                metric_name="pelvic_error",
                metric_value=pelvic_error,
            )
        )

    if knee_error > 0.18 and "knee_angle" in leaders[:2]:
        severity = clamp01((knee_error - 0.18) / 0.75)
        issues.append(
            build_issue(
                error_type="knee_flexion",
                body_part="무릎",
                severity=severity,
                instant_feedback="무릎이 굽혀집니다. 허벅지를 들어 올리되 다리는 조금 더 곧게 유지해 주세요.",
                metric_name="knee_error",
                metric_value=knee_error,
            )
        )

    if (
        phase_is(compare_result, {"raising", "peak", "lowering", "transition"})
        and max(ankle_error, hip_error) > 0.18
        and ("ankle_height" in leaders[:2] or "hip_flexion" in leaders[:2])
    ):
        severity = max(
            clamp01((max(ankle_error, hip_error) - 0.18) / 0.75),
            similarity_gap(motion_similarity, 86.0),
        )
        issues.append(
            build_issue(
                error_type="leg_rom_low",
                body_part="다리",
                severity=severity,
                instant_feedback="다리 높이가 기준보다 낮습니다. 통증 없는 범위에서 무릎을 조금 더 높게 들어 주세요.",
                metric_name="leg_rom_error",
                metric_value=max(ankle_error, hip_error),
            )
        )

    if phase == "lowering" and ankle_error > 0.16 and "ankle_height" in leaders:
        severity = clamp01((ankle_error - 0.16) / 0.65)
        issues.append(
            build_issue(
                error_type="lowering_control",
                body_part="다리",
                severity=severity,
                instant_feedback="다리를 내릴 때도 힘을 풀지 말고 천천히 제어해 주세요.",
                metric_name="lowering_error",
                metric_value=ankle_error,
            )
        )

    if posture_similarity is not None and float(posture_similarity) < 78.0 and not issues:
        severity = clamp01((78.0 - float(posture_similarity)) / 30.0)
        issues.append(
            build_issue(
                error_type="posture_quality_low",
                body_part="자세",
                severity=severity,
                instant_feedback="다리를 드는 동안 자세가 흐트러집니다. 상체와 골반 정렬을 유지해 주세요.",
                metric_name="posture_similarity",
                metric_value=float(posture_similarity),
            )
        )

    return issues
