# 어깨 전방 거상 운동 feature 추출 (MediaPipe / YOLO)
import numpy as np
from app.exercises.shared.dtw_feature_extractor import (
    calc_angle,
    midpoint,
    line_angle_from_vertical,
    horizontal_error_deg,
)



def get_shoulder_front_raise_left_features_mp(pts: dict):
    """
    왼팔 전방 거상(보조손으로 팔꿈치 지지) - 측면 기준

    MediaPipe landmark 번호 기준
    11,12: shoulder
    13,14: elbow
    15,16: wrist
    23,24: hip

    출력 feature (총 6개):
      [trunk, shoulder_rise, left_arm_raise, left_elbow_angle, left_arm_h_err, support_dist]
    """
    required = [11, 12, 13, 15, 16, 23, 24]
    if not all(i in pts for i in required):
        return None

    l_sh = pts[11]
    r_sh = pts[12]
    l_el = pts[13]
    l_wr = pts[15]
    r_wr = pts[16]
    l_hip = pts[23]
    r_hip = pts[24]

    shoulder_mid = midpoint(l_sh, r_sh)
    hip_mid = midpoint(l_hip, r_hip)

    # 1) 몸통 기울기
    trunk = line_angle_from_vertical(shoulder_mid, hip_mid)
    if trunk is None:
        return None

    # 2) 왼쪽 어깨 상승
    shoulder_rise = float(max(0.0, r_sh[1] - l_sh[1]))

    # 3) 왼팔 들어올림 각도
    left_arm_raise = calc_angle(hip_mid, l_sh, l_el)
    if left_arm_raise is None:
        return None

    # 4) 팔꿈치 각도
    left_elbow_angle = calc_angle(l_sh, l_el, l_wr)
    if left_elbow_angle is None:
        return None

    # 5) 팔 라인 오차
    left_arm_h_err = horizontal_error_deg(l_sh, l_el)
    if left_arm_h_err is None:
        return None

    # 6) 보조손 (오른손) - 왼팔꿈치 거리
    support_dist = float(np.linalg.norm(np.array(r_wr) - np.array(l_el)))

    return [
        round(trunk, 3),
        round(shoulder_rise, 3),
        round(left_arm_raise, 3),
        round(left_elbow_angle, 3),
        round(left_arm_h_err, 3),
        round(support_dist, 3),
    ]


def get_shoulder_front_raise_left_features_yolo(pts: dict):
    """
    왼팔 전방 거상 - YOLOv8 Pose COCO keypoint 기준

    YOLO 번호:
    5  : left_shoulder   6  : right_shoulder
    7  : left_elbow      9  : left_wrist
    11 : left_hip

    출력 feature (총 6개): MP 버전과 동일 구조
    trunk, shoulder_rise 는 픽셀 거리 사용 (MP 버전과 계산 방식 다름)
    """
    required = [5, 6, 7, 9, 11]
    if not all(i in pts for i in required):
        return None

    ls = pts[5]   # left shoulder
    rs = pts[6]   # right shoulder
    le = pts[7]   # left elbow
    lw = pts[9]   # left wrist
    lh = pts[11]  # left hip

    trunk = float(abs(ls[0] - lh[0]))
    shoulder_rise = float(abs(ls[1] - rs[1]))

    left_arm_raise = calc_angle(lh, ls, le)
    if left_arm_raise is None:
        return None

    left_elbow_angle = calc_angle(ls, le, lw)
    if left_elbow_angle is None:
        return None

    left_arm_h_err = horizontal_error_deg(ls, le)
    if left_arm_h_err is None:
        return None

    r_ref = pts.get(10, rs)  # right_wrist(10) 없으면 right_shoulder 대체
    support_dist = float(np.linalg.norm(np.array(r_ref) - np.array(le)))

    return [
        round(trunk, 3),
        round(shoulder_rise, 3),
        round(left_arm_raise, 3),
        round(left_elbow_angle, 3),
        round(left_arm_h_err, 3),
        round(support_dist, 3),
    ]
