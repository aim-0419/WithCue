# YOLO 포즈 감지 결과를 가공하는 유틸리티 함수와 각도 스무딩 클래스 모음.
# 원시 YOLO 출력에서 키포인트 좌표를 추출해 프론트엔드 기준(1280x720 픽셀)으로 변환하고,
# 프레임 간 각도 떨림을 지수 이동 평균(EMA) 필터로 부드럽게 만들어준다.

import numpy as np

# [삭제] KEYPOINT_NAMES 딕셔너리는 이제 필요 없습니다.
# posture_rules.py가 숫자 인덱스(0~16)를 기준으로 작성되었기 때문입니다.

# YOLO infer() 반환값에서 첫 번째 감지된 사람의 키포인트를 딕셔너리로 변환하는 함수.
# 좌표계: YOLO 추론 입력 해상도(STREAM 640×360) 픽셀 좌표.
#   → camera.py의 update_keypoints_3d()가 ×2.0 스케일링으로 1280×720 depth 좌표로 변환한다.
# 신뢰도(conf)가 conf_threshold 미만인 관절은 제외한다.
# 매개변수: result - ai_service.YOLODetector.infer()의 반환값 (단일 이미지 Results 객체).
# 반환값: {관절인덱스: {"x": float, "y": float}}. 감지 실패 시 빈 딕셔너리 반환.
def extract_keypoints(result, conf_threshold: float = 0.3) -> dict:
    if result is None or len(result) == 0:
        return {}

    person = result[0]  # 첫 번째 감지된 사람
    if person.keypoints is None:
        return {}

    kpts = person.keypoints
    if kpts.xy is None or len(kpts.xy) == 0:
        return {}

    xy = kpts.xy[0].cpu().numpy()    # (17, 2) — STREAM 해상도 픽셀 좌표
    conf = kpts.conf[0].cpu().numpy() if kpts.conf is not None else None

    keypoints = {}
    for i, (x, y) in enumerate(xy):
        if conf is not None and conf[i] < conf_threshold:
            continue
        keypoints[i] = {"x": float(x), "y": float(y)}

    return keypoints

# 연속된 프레임의 각도 값에 지수 이동 평균(EMA) 필터를 적용해 떨림을 줄여주는 클래스.
# alpha 값이 작을수록 부드럽지만 반응이 느려지고, 클수록 빠르게 반응하지만 떨림이 생긴다.
class AngleSmoother:
    # EMA 필터를 초기화한다.
    # 매개변수: alpha - 평활화 계수(0.0~1.0, 권장값 0.4~0.6).
    def __init__(self, alpha=0.5):
        """
        지수 이동 평균(EMA) 필터
        :param alpha: 0.0 ~ 1.0 (값이 작을수록 부드럽지만 반응이 느림)
        - 추천값: 0.4 ~ 0.6
        """
        self.alpha = alpha
        self.prev_angle = None

    # 현재 프레임의 각도 값을 받아 이전 값과 가중 평균을 내어 부드러운 각도를 반환하는 메서드.
    # 매개변수: current_angle - 현재 프레임에서 계산된 각도(float 또는 None).
    # 반환값: 평활화된 각도(int). 입력이 None이면 0 반환.
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
