# 운동 중 자세 정확도를 계산하는 모듈.
# 허용 범위를 벗어난 각도에 따라 점수를 깎고(감점),
# 자세가 다시 정상 범위로 돌아오면 점수를 일부 회복합니다.
# 100점에서 시작해 실시간으로 정확도를 추적합니다.

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


# 0~100 범위를 벗어나지 않도록 값을 제한합니다.
# 매개변수: value - 제한할 실수값
# 반환값: 0.0 이상 100.0 이하로 제한된 값
def _clamp_0_100(value: float) -> float:
    return max(0.0, min(100.0, value))


# 운동 반복 1회 동안의 정확도 상태를 저장하는 변경 불가능한 데이터 구조.
# accuracy_pct는 현재 정확도이고, min_accuracy_pct는 해당 반복 중 기록된 최저 정확도입니다.
@dataclass(frozen=True)
class AccuracyState:
    """
    반복 1회 동안의 정확도 상태.
    정확도는 100에서 시작하고, 동작 중 감점/회복을 거친 뒤
    기본자세로 복귀한 시점의 accuracy_pct를 최종 정확도로 사용합니다.
    """

    accuracy_pct: float = 100.0
    min_accuracy_pct: float = 100.0


# 허용 범위를 초과한 각도만큼 감점 값을 계산합니다.
# 초과 각도가 없으면 감점하지 않습니다.
# 매개변수: excess_deg - 허용 범위 초과 각도 / unit_penalty - 1도당 감점 / max_penalty - 최대 감점 한도
# 반환값: 이번 프레임의 감점량 (0 이상)
def deviation_penalty(excess_deg: float, *, unit_penalty: float, max_penalty: float) -> float:
    """
    허용 범위를 벗어난 각도만큼 감점합니다.
    excess_deg가 0 이하이면 감점하지 않습니다.
    """
    if excess_deg <= 0:
        return 0.0
    return round(min(excess_deg * unit_penalty, max_penalty), 2)


# 자세가 정상 범위로 돌아왔을 때 정확도를 일부 회복합니다.
# 매개변수: posture_stable - 자세가 정상 범위 안에 있는지 여부 / bonus - 회복량 (기본 3.0)
# 반환값: 이번 프레임의 회복량 (0 또는 bonus)
def recovery_bonus(*, posture_stable: bool, bonus: float = 3.0) -> float:
    """
    잘못된 자세가 다시 정상 허용 범위로 들어오면 정확도를 일부 회복합니다.
    """
    return round(bonus, 2) if posture_stable else 0.0


# 프레임 하나를 기준으로 감점과 회복을 적용해 정확도 상태를 갱신합니다.
# 매개변수: state - 이전 프레임의 정확도 상태 / penalty_delta_pct - 이 프레임의 감점량 / recovery_delta_pct - 이 프레임의 회복량
# 반환값: 갱신된 AccuracyState 객체
def update_accuracy(state: AccuracyState, *, penalty_delta_pct: float, recovery_delta_pct: float) -> AccuracyState:
    """
    프레임 1개 기준 정확도 갱신.
    accuracy = accuracy - penalty + recovery
    """
    next_accuracy = _clamp_0_100(state.accuracy_pct - penalty_delta_pct + recovery_delta_pct)
    next_min_accuracy = min(state.min_accuracy_pct, next_accuracy)
    return AccuracyState(
        accuracy_pct=round(next_accuracy, 2),
        min_accuracy_pct=round(next_min_accuracy, 2),
    )


# 이번 프레임에서 어떤 자세 이탈이 얼마나 발생했는지를 딕셔너리로 정리합니다.
# 프론트엔드에서 어떤 부위가 틀렸는지 시각적으로 표시할 때 활용합니다.
# 매개변수:
#   trunk_sway_excess_deg - 몸통 흔들림 초과 각도
#   opposite_limb_excess_deg - 반대쪽 팔/다리 이탈 초과 각도
#   elbow_flex_excess_deg - 팔꿈치 구부림 초과 각도
# 반환값: 각 이탈 항목과 초과 각도를 담은 딕셔너리
def build_deviation_flags(
    *,
    trunk_sway_excess_deg: float = 0.0,
    opposite_limb_excess_deg: float = 0.0,
    elbow_flex_excess_deg: float = 0.0,
) -> Dict[str, float]:
    """
    프레임별 어떤 이탈이 있었는지 기록하기 위한 플래그 JSON.
    값은 '허용 범위를 얼마나 초과했는가'를 의미합니다.
    """
    return {
        "trunk_sway_excess_deg": round(max(0.0, trunk_sway_excess_deg), 2),
        "opposite_limb_excess_deg": round(max(0.0, opposite_limb_excess_deg), 2),
        "elbow_flex_excess_deg": round(max(0.0, elbow_flex_excess_deg), 2),
    }
