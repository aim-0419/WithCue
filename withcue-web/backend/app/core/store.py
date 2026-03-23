from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class UserSessionData:
    # 1. 측정 결과 (Baseline)
    max_rom: int = 45
    pain_angle: int = None
    
    # 2. 신체 정보 (Calibration)
    init_shoulder_y: float = None
    active_side: str = None
    
    # 3. 오늘 운동 성과 (Log)
    success_count: int = 0
    bad_form_count: int = 0
    
# 메모리 저장소 (운동 이름 -> 데이터 객체)
# 예: {"SHOULDER_EXTERNAL_ROTATION": UserSessionData(...)}
SESSION_STORE: Dict[str, UserSessionData] = {}

def get_session(exercise_name: str) -> UserSessionData:
    """ 해당 운동의 세션 데이터를 가져오거나 새로 만듦 """
    if exercise_name not in SESSION_STORE:
        SESSION_STORE[exercise_name] = UserSessionData()
    return SESSION_STORE[exercise_name]

def update_calibration(exercise_name: str, shoulder_y: float, side: str):
    """ 측정 모드에서 잰 신체 정보를 저장 """
    data = get_session(exercise_name)
    data.init_shoulder_y = shoulder_y
    data.active_side = side
    print(f"[Store] {exercise_name} 캘리브레이션 완료: {side} / 높이 {shoulder_y:.2f}")
    
def log_result(exercise_name: str, is_success: bool):
    """ 코칭 중 성공/실패 카운트 증가 """
    data = get_session(exercise_name)
    if is_success:
        data.success_count += 1
    else:
        data.bad_form_count += 1
