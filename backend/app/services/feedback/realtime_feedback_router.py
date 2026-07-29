# 운동 중 실시간으로 자세 문제를 감지하고 피드백 메시지를 결정하는 모듈.
# 운동 종류에 맞는 문제 감지 함수를 호출하고,
# 같은 오류가 너무 자주 반복되지 않도록 쿨다운(재발송 대기 시간)을 적용합니다.
# 심각도가 가장 높은 오류만 선택해 사용자에게 전달합니다.

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.exercises.bird_dog.feedback import extract_birddog_issues
from app.exercises.straight_leg_raise.feedback import extract_straight_leg_raise_right_issues
from app.exercises.neck_rotation.feedback import extract_neck_rotation_issues
from app.exercises.shoulder_front_raise.feedback import extract_shoulder_front_raise_issues


# 운동 종류별로 자세 문제 감지 함수를 연결하는 매핑표.
# 새 운동을 추가할 때 이 딕셔너리에 항목을 추가합니다.
Extractor = {
    "bird_dog": extract_birddog_issues,
    "straight_leg_raise_right": extract_straight_leg_raise_right_issues,
    "neck_rotation": extract_neck_rotation_issues,
    "shoulder_front_raise": extract_shoulder_front_raise_issues,
}


# 운동별 자세 문제를 분석하고 실시간 피드백 메시지를 선택하는 클래스.
# 동일한 오류가 쿨다운 시간 안에 반복 발생해도 한 번만 피드백을 전달합니다.
class RealTimeFeedbackRouter:
    # 쿨다운 시간(초)과 피드백 발송 심각도 최소 기준을 설정합니다.
    # 매개변수: cooldown_sec - 같은 오류 재발송까지 대기 시간(초) / emit_threshold - 발송 최소 심각도(0~1)
    def __init__(self, cooldown_sec: float = 2.5, emit_threshold: float = 0.35):
        self.cooldown_sec = float(cooldown_sec)
        self.emit_threshold = float(emit_threshold)
        self._last_emit_at: Dict[str, float] = {}

    # 특정 오류 유형의 쿨다운이 지났는지 확인합니다.
    # 매개변수: key - "운동종류:오류유형" 형태의 문자열 / now_sec - 현재 시각(초)
    # 반환값: 쿨다운이 지났으면 True, 아직 대기 중이면 False
    def _cooldown_ok(self, key: str, now_sec: float) -> bool:
        last = self._last_emit_at.get(key, -1e9)
        return (now_sec - last) >= self.cooldown_sec

    # 감지된 자세 문제 목록 중 사용자에게 실제로 전달할 문제 하나를 선택합니다.
    # 심각도가 높은 것부터 검사하고, 최소 기준 이상이며 쿨다운이 지난 첫 번째 항목을 반환합니다.
    # 매개변수: exercise_type - 운동 종류 / issues - 감지된 문제 목록 / timestamp_sec - 현재 시각(초)
    # 반환값: 발송할 문제 딕셔너리, 없으면 None
    def _pick_issue_for_emit(
        self, exercise_type: str, issues: List[Dict[str, Any]], timestamp_sec: float
    ) -> Optional[Dict[str, Any]]:
        if not issues:
            return None
        ordered = sorted(issues, key=lambda x: float(x.get("severity", 0.0)), reverse=True)
        for issue in ordered:
            sev = float(issue.get("severity", 0.0))
            if sev < self.emit_threshold:
                continue
            key = f"{exercise_type}:{issue.get('error_type', 'unknown')}"
            if not self._cooldown_ok(key, timestamp_sec):
                continue
            self._last_emit_at[key] = timestamp_sec
            return issue
        return None

    # 프레임 하나의 비교 결과를 받아 자세 문제를 분석하고 피드백을 결정합니다.
    # 매개변수: exercise_type - 운동 종류 / compare_result - 자세 비교 결과 딕셔너리 / timestamp_sec - 현재 시각(초)
    # 반환값: 운동 종류, 발송할 피드백 메시지, 선택된 문제, 전체 문제 목록을 담은 딕셔너리
    def process(
        self, exercise_type: str, compare_result: Dict[str, Any], timestamp_sec: float
    ) -> Dict[str, Any]:
        if exercise_type not in Extractor:
            return {"exercise_type": exercise_type, "feedback": None, "issue": None, "all_issues": []}

        issues = Extractor[exercise_type](compare_result)
        emit_issue = self._pick_issue_for_emit(exercise_type, issues, float(timestamp_sec))
        feedback = emit_issue["instant_feedback"] if emit_issue else None
        return {
            "exercise_type": exercise_type,
            "feedback": feedback,
            "issue": emit_issue,
            "all_issues": issues,
        }
