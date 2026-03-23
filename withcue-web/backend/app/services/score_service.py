from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


def _clamp_0_100(value: float) -> float:
    return max(0.0, min(100.0, value))


@dataclass(frozen=True)
class AccuracyState:
    """
    반복 1회 동안의 정확도 상태.
    정확도는 100에서 시작하고, 동작 중 감점/회복을 거친 뒤
    기본자세로 복귀한 시점의 accuracy_pct를 최종 정확도로 사용합니다.
    """

    accuracy_pct: float = 100.0
    min_accuracy_pct: float = 100.0


def deviation_penalty(excess_deg: float, *, unit_penalty: float, max_penalty: float) -> float:
    """
    허용 범위를 벗어난 각도만큼 감점합니다.
    excess_deg가 0 이하이면 감점하지 않습니다.
    """
    if excess_deg <= 0:
        return 0.0
    return round(min(excess_deg * unit_penalty, max_penalty), 2)


def recovery_bonus(*, posture_stable: bool, bonus: float = 3.0) -> float:
    """
    잘못된 자세가 다시 정상 허용 범위로 들어오면 정확도를 일부 회복합니다.
    """
    return round(bonus, 2) if posture_stable else 0.0


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

