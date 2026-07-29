# 어깨 전방 거상 운동의 자세 문제를 감지하고 피드백 메시지를 생성하는 모듈.
# DTW 비교 결과를 받아 어깨 상승·몸통 보상·팔꿈치 굽힘·팔 경로 이탈·
# 팔 높이 부족·지지 불안정 등의 잘못된 패턴을 판별하고,
# 각 문제에 맞는 즉각 피드백 문구와 심각도를 반환한다.
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


# DTW 비교 결과를 분석해 어깨 전방 거상 운동의 자세 문제 목록을 반환한다.
# compare_result: DTW 엔진이 계산한 유사도·특징 오차·동작 단계 등을 담은 딕셔너리.
# 반환값: 감지된 문제(error_type, body_part, severity, instant_feedback 등)를 담은 딕셔너리 리스트.
#         문제가 없으면 빈 리스트를 반환한다.
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

    # 팔을 들 때 어깨가 함께 올라가는 보상 동작이 감지될 때
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

    # 팔을 들 때 몸통이 함께 앞뒤로 움직이는 보상 동작이 감지될 때
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

    # 팔꿈치가 과하게 굽혀질 때
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

    # 팔이 정면 직선 궤적을 벗어나 옆으로 흔들릴 때
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

    # 팔을 드는 동작 중 목표 높이보다 낮게 올라갈 때
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

    # 보조손과 팔꿈치 사이의 거리 오차가 커서 지지 자세가 불안정할 때
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

    # 팔을 내리는 구간에서 힘을 빼고 빠르게 내릴 때
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

    # 개별 문제가 없지만 전반적인 자세 유사도가 낮을 때
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
