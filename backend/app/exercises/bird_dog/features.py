# 버드독 운동의 관절 각도와 신체 수치를 계산하는 모듈.
# 카메라로 촬영된 영상에서 어깨, 팔꿈치, 손목, 엉덩이, 무릎, 발목의 위치를 받아
# 몸통 기울기, 팔/다리 들어올림 각도, 수평 오차, 관절 펴짐 각도 등 총 14개의 수치를 계산한다.
# MediaPipe 방식(번호 체계 A)과 YOLO 방식(번호 체계 B) 두 가지를 모두 지원한다.
import math
import numpy as np
from app.exercises.shared.dtw_feature_extractor import (
    calc_angle,
    midpoint,
    line_angle_from_vertical,
    horizontal_error_deg,
)


# MediaPipe 방식의 관절 좌표를 받아 버드독 운동의 14개 feature 수치를 계산한다.
# pts: 관절 번호를 키, (x, y) 좌표를 값으로 갖는 딕셔너리
# 반환: [몸통기울기, 골반기울기, 오른팔각도, 왼다리각도, 왼팔각도, 오른다리각도,
#        오른팔수평오차, 왼다리수평오차, 왼팔수평오차, 오른다리수평오차,
#        오른팔꿈치각도, 왼팔꿈치각도, 왼무릎각도, 오른무릎각도] 총 14개 실수 리스트.
#        필요한 관절이 감지되지 않으면 None 반환.
def get_bird_dog_features_mp(pts: dict):
    """
    MediaPipe landmark 번호 기준
    11,12: shoulder
    13,14: elbow
    15,16: wrist
    23,24: hip
    25,26: knee
    27,28: ankle

    출력 feature (총 14개):
      [trunk, pelvic, right_arm, left_leg, left_arm, right_leg,
       right_arm_h_err, left_leg_h_err, left_arm_h_err, right_leg_h_err,
       right_elbow_angle, left_elbow_angle, left_knee_angle, right_knee_angle]
    """
    required = [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]
    if not all(i in pts for i in required):
        return None

    l_sh = pts[11]
    r_sh = pts[12]
    l_el = pts[13]
    r_el = pts[14]
    l_wr = pts[15]
    r_wr = pts[16]

    l_hip = pts[23]
    r_hip = pts[24]
    l_knee = pts[25]
    r_knee = pts[26]
    l_ank = pts[27]
    r_ank = pts[28]

    shoulder_mid = midpoint(l_sh, r_sh)
    hip_mid = midpoint(l_hip, r_hip)

    # 1) 몸통 기울기
    trunk = line_angle_from_vertical(shoulder_mid, hip_mid)
    if trunk is None:
        return None

    # 2) 골반 기울기
    pelvic = float(
        math.degrees(
            math.atan2(abs(l_hip[1] - r_hip[1]), abs(l_hip[0] - r_hip[0]) + 1e-6)
        )
    )

    # 3) 팔/다리 들어올림 각도
    right_arm = calc_angle(hip_mid, r_sh, r_el)
    left_leg = calc_angle(shoulder_mid, l_hip, l_knee)
    left_arm = calc_angle(hip_mid, l_sh, l_el)
    right_leg = calc_angle(shoulder_mid, r_hip, r_knee)

    motion_vals = [right_arm, left_leg, left_arm, right_leg]
    if any(v is None for v in motion_vals):
        return None

    # 4) 팔/다리 수평 오차
    right_arm_h_err = horizontal_error_deg(r_sh, r_el)
    left_leg_h_err = horizontal_error_deg(l_hip, l_knee)
    left_arm_h_err = horizontal_error_deg(l_sh, l_el)
    right_leg_h_err = horizontal_error_deg(r_hip, r_knee)

    horizontal_vals = [right_arm_h_err, left_leg_h_err, left_arm_h_err, right_leg_h_err]
    if any(v is None for v in horizontal_vals):
        return None

    # 5) 팔꿈치 / 무릎 펴짐 각도
    right_elbow_angle = calc_angle(r_sh, r_el, r_wr)
    left_elbow_angle = calc_angle(l_sh, l_el, l_wr)
    left_knee_angle = calc_angle(l_hip, l_knee, l_ank)
    right_knee_angle = calc_angle(r_hip, r_knee, r_ank)

    joint_vals = [right_elbow_angle, left_elbow_angle, left_knee_angle, right_knee_angle]
    if any(v is None for v in joint_vals):
        return None

    return [
        round(trunk, 3),
        round(pelvic, 3),
        round(right_arm, 3),
        round(left_leg, 3),
        round(left_arm, 3),
        round(right_leg, 3),
        round(right_arm_h_err, 3),
        round(left_leg_h_err, 3),
        round(left_arm_h_err, 3),
        round(right_leg_h_err, 3),
        round(right_elbow_angle, 3),
        round(left_elbow_angle, 3),
        round(left_knee_angle, 3),
        round(right_knee_angle, 3),
    ]


# YOLOv8 방식의 관절 좌표를 받아 버드독 운동의 14개 feature 수치를 계산한다.
# pts: YOLO COCO 기준 관절 번호를 키, (x, y) 좌표를 값으로 갖는 딕셔너리
# 반환: MediaPipe 버전과 동일한 구조의 14개 실수 리스트.
#        필요한 관절이 감지되지 않으면 None 반환.
def get_bird_dog_features_yolo(pts: dict):
    """
    YOLOv8 Pose COCO keypoint 기준

    YOLO 번호:
    5  : left_shoulder   6  : right_shoulder
    7  : left_elbow      8  : right_elbow
    9  : left_wrist      10 : right_wrist
    11 : left_hip        12 : right_hip
    13 : left_knee       14 : right_knee
    15 : left_ankle      16 : right_ankle

    출력 feature (총 14개): MP 버전과 동일 구조
    """
    required = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
    if not all(i in pts for i in required):
        return None

    l_sh = pts[5]
    r_sh = pts[6]
    l_el = pts[7]
    r_el = pts[8]
    l_wr = pts[9]
    r_wr = pts[10]

    l_hip = pts[11]
    r_hip = pts[12]
    l_knee = pts[13]
    r_knee = pts[14]
    l_ank = pts[15]
    r_ank = pts[16]

    shoulder_mid = midpoint(l_sh, r_sh)
    hip_mid = midpoint(l_hip, r_hip)

    trunk = line_angle_from_vertical(shoulder_mid, hip_mid)
    if trunk is None:
        return None

    pelvic = float(
        math.degrees(
            math.atan2(abs(l_hip[1] - r_hip[1]), abs(l_hip[0] - r_hip[0]) + 1e-6)
        )
    )

    right_arm = calc_angle(hip_mid, r_sh, r_el)
    left_leg = calc_angle(shoulder_mid, l_hip, l_knee)
    left_arm = calc_angle(hip_mid, l_sh, l_el)
    right_leg = calc_angle(shoulder_mid, r_hip, r_knee)

    motion_vals = [right_arm, left_leg, left_arm, right_leg]
    if any(v is None for v in motion_vals):
        return None

    right_arm_h_err = horizontal_error_deg(r_sh, r_el)
    left_leg_h_err = horizontal_error_deg(l_hip, l_knee)
    left_arm_h_err = horizontal_error_deg(l_sh, l_el)
    right_leg_h_err = horizontal_error_deg(r_hip, r_knee)

    horizontal_vals = [right_arm_h_err, left_leg_h_err, left_arm_h_err, right_leg_h_err]
    if any(v is None for v in horizontal_vals):
        return None

    right_elbow_angle = calc_angle(r_sh, r_el, r_wr)
    left_elbow_angle = calc_angle(l_sh, l_el, l_wr)
    left_knee_angle = calc_angle(l_hip, l_knee, l_ank)
    right_knee_angle = calc_angle(r_hip, r_knee, r_ank)

    joint_vals = [right_elbow_angle, left_elbow_angle, left_knee_angle, right_knee_angle]
    if any(v is None for v in joint_vals):
        return None

    return [
        round(trunk, 3),
        round(pelvic, 3),
        round(right_arm, 3),
        round(left_leg, 3),
        round(left_arm, 3),
        round(right_leg, 3),
        round(right_arm_h_err, 3),
        round(left_leg_h_err, 3),
        round(left_arm_h_err, 3),
        round(right_leg_h_err, 3),
        round(right_elbow_angle, 3),
        round(left_elbow_angle, 3),
        round(left_knee_angle, 3),
        round(right_knee_angle, 3),
    ]
