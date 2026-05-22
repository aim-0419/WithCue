from __future__ import annotations

from typing import Any, Dict, List

from app.services.feedback.common import (
    build_issue,
    clamp01,
    feature_error,
    similarity_gap,
    top_features,
)


def extract_birddog_issues(compare_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    motion_similarity = compare_result.get("motion_similarity")
    posture_similarity = compare_result.get("posture_similarity")
    pair_a_error = float(compare_result.get("pair_a_error", 0.0))
    pair_b_error = float(compare_result.get("pair_b_error", 0.0))
    movement_direction = str(compare_result.get("movement_direction", "balanced"))
    leaders = top_features(compare_result, limit=4)

    motion_group_error = max(
        pair_a_error,
        pair_b_error,
        feature_error(compare_result, "right_arm"),
        feature_error(compare_result, "left_leg"),
        feature_error(compare_result, "left_arm"),
        feature_error(compare_result, "right_leg"),
    )

    if motion_group_error > 0.16 and any(name in leaders[:3] for name in ("right_arm", "left_leg", "left_arm", "right_leg")):
        pair_hint = "오른팔-왼다리" if movement_direction == "pair_a" else "왼팔-오른다리"
        severity = max(
            clamp01((motion_group_error - 0.16) / 0.75),
            similarity_gap(motion_similarity, 84.0),
        )
        issues.append(
            build_issue(
                error_type="rom_low",
                body_part="팔/다리",
                severity=severity,
                instant_feedback=f"{pair_hint} 대각선 쌍의 가동범위를 조금 더 길게 뻗어 주세요.",
                metric_name="motion_group_error",
                metric_value=motion_group_error,
            )
        )

    pair_delta = abs(pair_a_error - pair_b_error)
    if pair_delta > 0.08:
        weaker_pair = "오른팔-왼다리" if pair_a_error > pair_b_error else "왼팔-오른다리"
        severity = clamp01((pair_delta - 0.08) / 0.35)
        issues.append(
            build_issue(
                error_type="diagonal_sync_gap",
                body_part="대각선 협응",
                severity=severity,
                instant_feedback=f"{weaker_pair} 쌍이 늦거나 짧습니다. 팔과 다리를 동시에 뻗어 주세요.",
                metric_name="pair_delta",
                metric_value=pair_delta,
            )
        )

    trunk_error = feature_error(compare_result, "trunk")
    pelvic_error = feature_error(compare_result, "pelvic")
    if max(trunk_error, pelvic_error) > 0.15 and any(name in leaders[:3] for name in ("trunk", "pelvic")):
        severity = max(
            clamp01((max(trunk_error, pelvic_error) - 0.15) / 0.65),
            similarity_gap(posture_similarity, 82.0),
        )
        issues.append(
            build_issue(
                error_type="balance_gap",
                body_part="몸통",
                severity=severity,
                instant_feedback="몸통과 골반이 흔들립니다. 허리와 골반 라인을 고정해 주세요.",
                metric_name="trunk_pelvic_error",
                metric_value=max(trunk_error, pelvic_error),
            )
        )

    arm_joint_error = max(
        feature_error(compare_result, "right_elbow_angle"),
        feature_error(compare_result, "left_elbow_angle"),
        feature_error(compare_result, "right_arm_h_err"),
        feature_error(compare_result, "left_arm_h_err"),
    )
    leg_joint_error = max(
        feature_error(compare_result, "left_knee_angle"),
        feature_error(compare_result, "right_knee_angle"),
        feature_error(compare_result, "left_leg_h_err"),
        feature_error(compare_result, "right_leg_h_err"),
    )
    if arm_joint_error > 0.18 and any(name in leaders[:3] for name in ("right_elbow_angle", "left_elbow_angle", "right_arm_h_err", "left_arm_h_err")):
        severity = clamp01((arm_joint_error - 0.18) / 0.7)
        issues.append(
            build_issue(
                error_type="arm_alignment",
                body_part="팔",
                severity=severity,
                instant_feedback="팔이 짧아지거나 굽습니다. 어깨 높이까지 길게 뻗어 주세요.",
                metric_name="arm_joint_error",
                metric_value=arm_joint_error,
            )
        )

    if leg_joint_error > 0.18 and any(name in leaders[:3] for name in ("left_knee_angle", "right_knee_angle", "left_leg_h_err", "right_leg_h_err")):
        severity = clamp01((leg_joint_error - 0.18) / 0.7)
        issues.append(
            build_issue(
                error_type="leg_alignment",
                body_part="다리",
                severity=severity,
                instant_feedback="다리가 접히거나 낮아집니다. 무릎을 펴고 뒤로 길게 뻗어 주세요.",
                metric_name="leg_joint_error",
                metric_value=leg_joint_error,
            )
        )

    if posture_similarity is not None and float(posture_similarity) < 80.0 and not issues:
        severity = clamp01((80.0 - float(posture_similarity)) / 30.0)
        issues.append(
            build_issue(
                error_type="posture_quality_low",
                body_part="자세",
                severity=severity,
                instant_feedback="버드독 자세가 흐트러집니다. 허리와 어깨 라인을 안정적으로 유지해 주세요.",
                metric_name="posture_similarity",
                metric_value=float(posture_similarity),
            )
        )

    return issues
