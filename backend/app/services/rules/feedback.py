import time
from typing import Dict, Optional
from app.core.geometry import calculate_distance

class FeedbackManager:
    def __init__(self):
        self.last_feedback_time = 0
        self.cooldown = 1.5  # 피드백 간격 (초)
        
        # [스무딩 & 방향 감지 변수]
        self.prev_angle = 0.0  # 이전 프레임의 보정된 각도

    # [수정] 인자 이름을 raw_angle로 통일하여 내부 변수명과 일치시킴
    def get_feedback(self, exercise_name: str, keypoints: Dict, current_angle: float, personal_limit: float = None) -> Optional[str]:

        # 운동 방향 감지 (is_pushing)
        # 보정된 각도가 이전보다 0.5도 이상 커져야 "수축 중"으로 인정
        is_pushing = current_angle > (self.prev_angle + 0.5)

        # 상태 업데이트
        self.prev_angle = current_angle

        # ---------------------------------------------------------
        # [Step 1] 쿨다운 체크
        # ---------------------------------------------------------
        if time.time() - self.last_feedback_time < self.cooldown:
            return None

        message = None

        # ---------------------------------------------------------
        # [Step 2] 안전 제일 (Safety Check)
        # ---------------------------------------------------------
        if exercise_name == "SHOULDER_EXTERNAL_ROTATION":
            
            if self._is_elbow_flaring(keypoints):
                message = "팔꿈치가 옆구리에서 떨어졌어요! 딱 붙여주세요."
            
            elif self._is_shrugging(keypoints):
                message = "어깨에 힘을 빼고 툭 떨어뜨리세요."

        # ---------------------------------------------------------
        # [Step 3] 가동범위 코칭 (Performance Check)
        # ---------------------------------------------------------
        if not message and is_pushing:
            
            if not personal_limit:
                return None 

            target = personal_limit
            gap = target - current_angle

            if gap <= 5: 
                message = "좋습니다! 통증이 느껴지지 않는 범위까지만 하세요."
            elif gap <= 20:
                message = "조금만 더! 목표 각도에 거의 도달했어요."
            else:
                if current_angle > 10:
                    percent = int((current_angle / target) * 100)
                    message = f"조금 더 움직여보세요. ({percent}%)"

        # ---------------------------------------------------------
        # [Step 4] 전송
        # ---------------------------------------------------------
        if message:
            self.last_feedback_time = time.time()
            return message
        
        return None

    # --- [내부 감지 로직] ---

    def _is_elbow_flaring(self, kp) -> bool:
        threshold = 60.0 
        if 7 in kp and 11 in kp: 
            if calculate_distance(kp[7], kp[11]) > threshold: return True
        if 8 in kp and 12 in kp: 
            if calculate_distance(kp[8], kp[12]) > threshold: return True
        return False

    def _is_shrugging(self, kp) -> bool:
        threshold = 30.0
        if 3 in kp and 5 in kp:
            if abs(kp[3]['y'] - kp[5]['y']) < threshold: return True
        if 4 in kp and 6 in kp:
            if abs(kp[4]['y'] - kp[6]['y']) < threshold: return True
        return False