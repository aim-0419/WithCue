# 목 회전 운동 feature 추출 (MediaPipe / YOLO)
import numpy as np
from app.exercises.shared.dtw_feature_extractor import (
    midpoint,
    line_angle_from_vertical,
    line_angle_from_horizontal,
)



def get_neck_rotation_features_mp(pts: dict):
    """
    목 좌우 회전 기준 feature 추출

    MediaPipe landmark 번호 기준
    0  : nose
    7  : left_ear
    8  : right_ear
    11 : left_shoulder
    12 : right_shoulder
    23 : left_hip
    24 : right_hip

    출력 feature (총 4개):
      [trunk_rotation, neck_turn_angle, head_tilt, shoulder_line_angle]
    """
    required = [0, 7, 8, 11, 12, 23, 24]
    if not all(i in pts for i in required):
        return None

    nose = pts[0]
    left_ear = pts[7]
    right_ear = pts[8]
    left_sh = pts[11]
    right_sh = pts[12]
    left_hip = pts[23]
    right_hip = pts[24]

    shoulder_mid = midpoint(left_sh, right_sh)
    hip_mid = midpoint(left_hip, right_hip)

    # 1) 몸통 회전/기울기 근사
    trunk_rotation = line_angle_from_vertical(shoulder_mid, hip_mid)
    if trunk_rotation is None:
        return None

    # 2) 목 좌우 회전 정도 근사
    ear_mid = midpoint(left_ear, right_ear)
    half_ear_dist = abs(right_ear[0] - left_ear[0]) / 2.0

    if half_ear_dist < 1e-6:
        return None

    neck_turn_ratio = (nose[0] - ear_mid[0]) / half_ear_dist
    neck_turn_ratio = float(np.clip(neck_turn_ratio, -1.5, 1.5))
    neck_turn_angle = neck_turn_ratio * 60.0

    # 3) 고개 숙임/기울기
    head_tilt = line_angle_from_vertical(nose, shoulder_mid)
    if head_tilt is None:
        return None

    # 4) 어깨선 기울기
    shoulder_line_angle = line_angle_from_horizontal(left_sh, right_sh)
    if shoulder_line_angle is None:
        return None

    return [
        round(float(trunk_rotation), 3),
        round(float(neck_turn_angle), 3),
        round(float(head_tilt), 3),
        round(float(shoulder_line_angle), 3),
    ]


def get_neck_rotation_features_yolo(pts: dict):
    """
    목 좌우 회전 기준 feature 추출 - YOLOv8 Pose COCO keypoint 기준

    YOLO 번호:
    0  : nose
    3  : left_ear    4  : right_ear  (MP는 7, 8)
    5  : left_shoulder   6  : right_shoulder  (MP는 11, 12)
    11 : left_hip        12 : right_hip  (MP는 23, 24)

    출력 feature (총 4개): MP 버전과 동일
    """
    required = [0, 3, 4, 5, 6, 11, 12]
    if not all(i in pts for i in required):
        return None

    nose = pts[0]
    left_ear = pts[3]
    right_ear = pts[4]
    left_sh = pts[5]
    right_sh = pts[6]
    left_hip = pts[11]
    right_hip = pts[12]

    shoulder_mid = midpoint(left_sh, right_sh)
    hip_mid = midpoint(left_hip, right_hip)

    trunk_rotation = line_angle_from_vertical(shoulder_mid, hip_mid)
    if trunk_rotation is None:
        return None

    ear_mid = midpoint(left_ear, right_ear)
    half_ear_dist = abs(right_ear[0] - left_ear[0]) / 2.0

    if half_ear_dist < 1e-6:
        return None

    neck_turn_ratio = (nose[0] - ear_mid[0]) / half_ear_dist
    neck_turn_ratio = float(np.clip(neck_turn_ratio, -1.5, 1.5))
    neck_turn_angle = neck_turn_ratio * 60.0

    head_tilt = line_angle_from_vertical(nose, shoulder_mid)
    if head_tilt is None:
        return None

    shoulder_line_angle = line_angle_from_horizontal(left_sh, right_sh)
    if shoulder_line_angle is None:
        return None

    return [
        round(float(trunk_rotation), 3),
        round(float(neck_turn_angle), 3),
        round(float(head_tilt), 3),
        round(float(shoulder_line_angle), 3),
    ]
