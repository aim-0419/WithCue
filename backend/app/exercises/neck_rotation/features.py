# 목 회전 운동의 특징값(feature)을 추출하는 모듈.
# 카메라로 촬영한 사용자의 관절 좌표를 받아,
# 목 회전 각도·몸통 기울기·고개 기울기·어깨선 기울기 등 4가지 수치를 계산한다.
# MediaPipe와 YOLO 두 가지 관절 인식 방식을 모두 지원한다.
import numpy as np
from app.exercises.shared.dtw_feature_extractor import (
    midpoint,
    line_angle_from_vertical,
    line_angle_from_horizontal,
)



# MediaPipe 관절 번호를 기반으로 목 회전 특징값 4개를 계산해 반환한다.
# pts: 관절 번호를 키, (x, y) 좌표를 값으로 갖는 딕셔너리.
# 필수 관절(코, 양쪽 귀, 양쪽 어깨, 양쪽 엉덩이)이 없으면 None을 반환한다.
# 반환값: [몸통_회전, 목_회전_각도, 고개_기울기, 어깨선_기울기] (소수점 3자리 float 리스트)
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


# P2-9: 코와 어깨중심의 X·Z(수평) 평면 편차로 목 좌우 회전각을 3D로 계산한다.
# nose·left_shoulder·right_shoulder의 (x, z)만 사용한다. 좌회전=음수, 우회전=양수.
# 세 점 중 하나라도 depth(z)가 없으면(2D 좌표) None을 반환해 호출부에서 2D로 폴백한다.
def neck_turn_angle_3d(nose, left_sh, right_sh):
    if len(nose) < 3 or len(left_sh) < 3 or len(right_sh) < 3:
        return None
    cx = (left_sh[0] + right_sh[0]) / 2.0
    cz = (left_sh[2] + right_sh[2]) / 2.0
    # 어깨선 방향(좌→우) 단위벡터, X·Z 평면
    rx = right_sh[0] - left_sh[0]
    rz = right_sh[2] - left_sh[2]
    r_norm = float(np.hypot(rx, rz))
    if r_norm < 1e-6:
        return None
    rx, rz = rx / r_norm, rz / r_norm
    # 코 벡터(어깨중심 기준)를 어깨선 성분(lateral)과 정면 성분(forward)으로 분해
    vx = nose[0] - cx
    vz = nose[2] - cz
    lateral = vx * rx + vz * rz
    forward = float(np.sqrt(max(0.0, vx * vx + vz * vz - lateral * lateral)))
    return float(np.degrees(np.arctan2(lateral, forward)))


# YOLO 관절 번호를 기반으로 목 회전 특징값 4개를 계산해 반환한다.
# 목_회전_각도는 P2-9에 따라 3D(X·Z 평면)로 계산하며, depth가 없으면 2D 비율로 폴백한다.
# pts: 관절 번호를 키, (x, y[, z]) 좌표를 값으로 갖는 딕셔너리.
# 필수 관절(코·양쪽 귀·양쪽 어깨·양쪽 엉덩이)이 없으면 None을 반환한다.
# 반환값: [몸통_회전, 목_회전_각도, 고개_기울기, 어깨선_기울기] (소수점 3자리 float 리스트)
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

    neck_turn_angle = neck_turn_angle_3d(nose, left_sh, right_sh)
    if neck_turn_angle is None:
        # depth(z) 미제공 시 2D 폴백 (코·귀 x좌표 비율)
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
