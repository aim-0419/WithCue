import numpy as np

# [삭제] KEYPOINT_NAMES 딕셔너리는 이제 필요 없습니다.
# posture_rules.py가 숫자 인덱스(0~16)를 기준으로 작성되었기 때문입니다.

def extract_keypoints(result) -> dict:
    """
    YOLO 결과를 처리하기 쉬운 딕셔너리 형태로 변환
    프론트 요청대로 '1280x720 기준 픽셀 좌표'로 변환해서 반환
    """
    if result.keypoints is None:
        return {}
    
    # data shape: (Num_People, 17, 3) -> (x, y, conf)
    kpts_data = result.keypoints.data
    
    if len(kpts_data) == 0:
        return {}
    
    img_h, img_w = result.orig_shape    
    
    TARGET_W = 1280
    TARGET_H = 720
    
    # 가장 신뢰도 높은(또는 첫 번째) 사람 한 명만 추출
    person_kpts = kpts_data[0].cpu().numpy()
    
    keypoints_dict = {}
    CONF_THRESHOLD = 0.5
    
    for idx, (x, y, conf) in enumerate(person_kpts):
        if conf < CONF_THRESHOLD:
            continue
        
        norm_x = x / img_w if img_w > 0 else 0.0
        norm_y = y / img_h if img_h > 0 else 0.0
        
        final_x = int(norm_x * TARGET_W)
        final_y = int(norm_y * TARGET_H)
        
        keypoints_dict[idx] = {
            "x": final_x,
            "y": final_y,
        }
        
    return keypoints_dict

class AngleSmoother:
    def __init__(self, alpha=0.5):
        """
        지수 이동 평균(EMA) 필터
        :param alpha: 0.0 ~ 1.0 (값이 작을수록 부드럽지만 반응이 느림)
        - 추천값: 0.4 ~ 0.6
        """
        self.alpha = alpha
        self.prev_angle = None
        
    def smooth(self, current_angle):
        # 값이 없거나 0이면 그대로 반환 (혹은 무시)
        if current_angle is None:
            return 0
        
        if self.prev_angle is None:
            self.prev_angle = current_angle
            return int(current_angle)
        
        # EMA 공식: 새로운 값 = (현재값 * α) + (이전값 * (1 - α))
        smoothed = (current_angle * self.alpha) + (self.prev_angle * (1 - self.alpha))
        
        self.prev_angle = smoothed
        return int(smoothed)
        
