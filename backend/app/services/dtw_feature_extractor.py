import math
import numpy as np


def calc_angle(p1, p2, p3):
    """
    세 점(p1-p2-p3)으로 이루어진 관절 각도 계산
    반환값: degree
    """
    a = np.array(p1, dtype=float)
    b = np.array(p2, dtype=float)
    c = np.array(p3, dtype=float)

    ba = a - b
    bc = c - b

    norm_ba = np.linalg.norm(ba)
    norm_bc = np.linalg.norm(bc)

    if norm_ba < 1e-6 or norm_bc < 1e-6:
        return None

    cos_val = np.dot(ba, bc) / (norm_ba * norm_bc)
    cos_val = np.clip(cos_val, -1.0, 1.0)

    return float(np.degrees(np.arccos(cos_val)))


def midpoint(p1, p2):
    """
    두 점의 중점 계산
    """
    return (
        (p1[0] + p2[0]) / 2.0,
        (p1[1] + p2[1]) / 2.0,
    )


def line_angle_from_vertical(p_top, p_bottom):
    """
    두 점을 잇는 선분이 수직축과 이루는 각도
    0도에 가까울수록 수직
    """
    dx = p_top[0] - p_bottom[0]
    dy = p_top[1] - p_bottom[1]

    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return None

    return float(math.degrees(math.atan2(abs(dx), abs(dy))))


def line_angle_from_horizontal(p1, p2):
    """
    두 점을 잇는 선분이 수평축과 이루는 절대 각도
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]

    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return None

    return float(abs(math.degrees(math.atan2(dy, dx))))


def horizontal_error_deg(p1, p2):
    """
    두 점을 잇는 선분이 '수평선'에서 얼마나 벗어났는지 계산
    반환값:
      0도   -> 완전 수평
      값이 클수록 -> 수평에서 더 많이 벗어남
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]

    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return None

    angle = abs(math.degrees(math.atan2(dy, dx)))

    # 수평은 0도 또는 180도 방향
    return float(min(angle, abs(180.0 - angle)))


# -------버드독(허리운동)------------------------------------------------
def get_bird_dog_features_mp(pts: dict):
    """
    MediaPipe landmark 번호 기준
    11,12: shoulder
    13,14: elbow
    15,16: wrist
    23,24: hip
    25,26: knee
    27,28: ankle

    입력:
      pts = {
        11: (x, y),
        12: (x, y),
        ...
      }

    출력 feature (총 14개):
      [
        trunk,
        pelvic,
        right_arm,
        left_leg,
        left_arm,
        right_leg,
        right_arm_h_err,
        left_leg_h_err,
        left_arm_h_err,
        right_leg_h_err,
        right_elbow_angle,
        left_elbow_angle,
        left_knee_angle,
        right_knee_angle
      ]

    의미:
      trunk             : 몸통 기울기
      pelvic            : 골반 기울기
      right_arm         : 오른팔 들어올림 각도
      left_leg          : 왼다리 들어올림 각도
      left_arm          : 왼팔 들어올림 각도
      right_leg         : 오른다리 들어올림 각도
      right_arm_h_err   : 오른팔 수평 오차
      left_leg_h_err    : 왼다리 수평 오차
      left_arm_h_err    : 왼팔 수평 오차
      right_leg_h_err   : 오른다리 수평 오차
      right_elbow_angle : 오른팔 팔꿈치 펴짐 정도
      left_elbow_angle  : 왼팔 팔꿈치 펴짐 정도
      left_knee_angle   : 왼다리 무릎 펴짐 정도
      right_knee_angle  : 오른다리 무릎 펴짐 정도
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

# -------왼팔 전방 거상(어깨운동)------------------------------------------------    
# 왼팔 전방 거상(보조손 포함)
def get_shoulder_front_raise_left_features_mp(pts: dict):
    """
    왼팔 전방 거상(보조손으로 팔꿈치 지지) - 측면 기준

    MediaPipe landmark 번호 기준
    11,12: shoulder
    13,14: elbow
    15,16: wrist
    23,24: hip

    출력 feature (총 6개):
      [
        trunk,
        shoulder_rise,
        left_arm_raise,
        left_elbow_angle,
        left_arm_h_err,
        support_dist
      ]
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
    
# -------한쪽 무릎 들어올리기(무릎운동)------------------------------------------------    
def get_knee_raise_right_features_mp(pts: dict):
    """
    오른다리 Straight Leg Raise(SLR) / 무릎-다리 들어올리기 기준 feature 추출
    - 측면 촬영 기준
    - 오른다리 정상 reference 생성용
    - 왼다리 영상은 flip_mediapipe_left_right(pts) 후 이 함수를 그대로 사용 가능

    MediaPipe landmark 번호 기준
    11 : LEFT_SHOULDER
    12 : RIGHT_SHOULDER
    23 : LEFT_HIP
    24 : RIGHT_HIP
    26 : RIGHT_KNEE
    28 : RIGHT_ANKLE

    입력:
      pts = {
        11: (x, y),
        12: (x, y),
        23: (x, y),
        24: (x, y),
        26: (x, y),
        28: (x, y),
        ...
      }

    출력 feature (총 5개):
      [
        trunk,
        pelvic,
        right_hip_flexion,
        right_knee_angle,
        right_ankle_rel_y,
      ]

    각 feature 의미:
      1) trunk
         - 몸통 기울기
         - 오른쪽 어깨(12)와 오른쪽 골반(24)을 이은 선분이
           수직축에서 얼마나 기울어졌는지
         - 0도에 가까울수록 몸통이 안정적이고 수직에 가까움
         - 값이 커질수록 상체 들림 / 몸통 보상 가능성 증가

      2) pelvic
         - 골반 기울기
         - 왼쪽 골반(23)과 오른쪽 골반(24)을 이은 선분이
           수평축에서 얼마나 기울어졌는지
         - 0도에 가까울수록 골반이 수평
         - 값이 커질수록 골반 따라들림 / 비틀림 보상 가능성 증가

      3) right_hip_flexion
         - 오른다리 들어올림 각도(고관절 굴곡 관련)
         - 오른쪽 어깨(12) - 오른쪽 골반(24) - 오른쪽 무릎(26) 각도
         - 시작 자세와 최고점 사이의 변화가 커야 정상적인 다리 들기 동작으로 볼 수 있음
         - rep 시작/상승/최고점/하강 구간 파악에 도움

      4) right_knee_angle
         - 오른무릎 펴짐 정도
         - 오른쪽 골반(24) - 오른쪽 무릎(26) - 오른쪽 발목(28) 각도
         - 180도에 가까울수록 무릎이 잘 펴진 상태
         - 값이 작아질수록 무릎 굽힘 보상 가능성 증가
         - 이번 운동에서 가장 중요한 보상 feature 중 하나

      5) right_ankle_rel_y
         - 오른발목의 상대 높이
         - 계산식: right_hip.y - right_ankle.y
         - 이미지 좌표계에서 y는 아래로 갈수록 커지므로,
           이 값이 커질수록 발목이 골반보다 더 위로 올라간 것
         - 실제 다리 상승량을 잘 반영하는 feature
         - start / peak / end 구간 탐지용 핵심 feature

    참고:
      - trunk, pelvic 은 보상 확인용
      - right_hip_flexion, right_ankle_rel_y 는 동작 진행도 / rep 탐지용
      - right_knee_angle 은 무릎 굽힘 보상 확인용 핵심 feature
    """
    required = [12, 23, 24, 26, 28]
    if not all(i in pts for i in required):
        return None

    right_sh = pts[12]
    left_hip = pts[23]
    right_hip = pts[24]
    right_knee = pts[26]
    right_ankle = pts[28]

    # 1) 몸통 기울기
    # 오른쪽 어깨-오른쪽 골반 선이 수직축에서 얼마나 기울어졌는지
    trunk = line_angle_from_vertical(right_sh, right_hip)
    if trunk is None:
        return None

    # 2) 골반 기울기
    # 왼골반-오른골반 선이 수평축에서 얼마나 기울어졌는지
    pelvic = line_angle_from_horizontal(left_hip, right_hip)
    if pelvic is None:
        return None

    # 3) 오른다리 들어올림 각도(고관절 굴곡 관련)
    # 오른어깨 - 오른골반 - 오른무릎
    right_hip_flexion = calc_angle(right_sh, right_hip, right_knee)
    if right_hip_flexion is None:
        return None

    # 4) 오른무릎 펴짐 정도
    # 오른골반 - 오른무릎 - 오른발목
    right_knee_angle = calc_angle(right_hip, right_knee, right_ankle)
    if right_knee_angle is None:
        return None

    # 5) 오른발목 상대 높이
    # 값이 커질수록 발목이 더 위로 올라간 것
    right_ankle_rel_y = float(abs(right_hip[1] - right_ankle[1]))
    
    return [
        round(trunk, 3),
        round(pelvic, 3),
        round(right_hip_flexion, 3),
        round(right_knee_angle, 3),
        round(right_ankle_rel_y, 3),
    ]   
# -------한쪽 무릎 들어올리기(무릎운동)_yolo------------------------------------------------ 
def get_knee_raise_right_features_yolo(pts: dict):
    """
    YOLOv8 Pose COCO 기준 오른다리 SLR / 무릎운동 feature 추출

    YOLO 번호:
    5  : left_shoulder
    6  : right_shoulder
    11 : left_hip
    12 : right_hip
    14 : right_knee
    16 : right_ankle
    """
    required = [6, 11, 12, 14, 16]
    if not all(i in pts for i in required):
        return None

    right_sh = pts[6]
    left_hip = pts[11]
    right_hip = pts[12]
    right_knee = pts[14]
    right_ankle = pts[16]

    trunk = line_angle_from_vertical(right_sh, right_hip)
    if trunk is None:
        return None

    pelvic = line_angle_from_horizontal(left_hip, right_hip)
    if pelvic is None:
        return None

    right_hip_flexion = calc_angle(right_sh, right_hip, right_knee)
    if right_hip_flexion is None:
        return None

    right_knee_angle = calc_angle(right_hip, right_knee, right_ankle)
    if right_knee_angle is None:
        return None

    right_ankle_rel_y = float(abs(right_hip[1] - right_ankle[1]))

    return [
        round(right_hip_flexion, 3),
        round(right_knee_angle, 3),
        round(right_ankle_rel_y, 3),
    ]

# 좌우반전
def flip_yolo_left_right(pts: dict):
    """
    YOLOv8 Pose COCO keypoint 좌우 반전
    """
    swap_pairs = {
        5: 6, 6: 5,       # shoulder
        7: 8, 8: 7,       # elbow
        9: 10, 10: 9,     # wrist
        11: 12, 12: 11,   # hip
        13: 14, 14: 13,   # knee
        15: 16, 16: 15,   # ankle
    }

    flipped = {}
    for k, v in pts.items():
        flipped_key = swap_pairs.get(k, k)
        flipped[flipped_key] = v

    return flipped

# -------목 좌우 회전(목운동)------------------------------------------------
def get_neck_rotation_features_mp(pts: dict):
    """
    목 좌우 회전 기준 feature 추출
    - 정면 또는 약간 정면 기준 촬영 권장
    - 좌우 회전 1개 운동 메뉴용
    - reference는 정상적인 좌->우 또는 우->좌 회전 흐름을 포함하면 됨

    MediaPipe landmark 번호 기준
    0  : nose
    7  : left_ear
    8  : right_ear
    11 : left_shoulder
    12 : right_shoulder
    23 : left_hip
    24 : right_hip

    출력 feature (총 4개):
      [
        trunk_rotation,
        neck_turn_angle,
        head_tilt,
        shoulder_line_angle,
      ]

    각 feature 의미:
      1) trunk_rotation
         - 몸통이 같이 돌아가는지 보기 위한 값
         - 어깨중심-골반중심 선의 수직축 기준 기울기

      2) neck_turn_angle
         - 고개 좌우 회전 정도의 근사값
         - 코와 양쪽 귀의 상대 위치 비대칭으로 계산
         - 절대적인 yaw는 아니지만, 좌/우 회전 진행도 추적용으로 사용

      3) head_tilt
         - 고개가 숙여지거나 옆으로 기울어지는 보상
         - 코-어깨중심 선의 수직축 기준 기울기

      4) shoulder_line_angle
         - 어깨선 기울기
         - 몸통 안정성 보조 feature
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
    # 코가 양 귀 중심 대비 얼마나 좌우 비대칭인지 사용
    ear_mid = midpoint(left_ear, right_ear)
    half_ear_dist = abs(right_ear[0] - left_ear[0]) / 2.0

    if half_ear_dist < 1e-6:
        return None

    neck_turn_ratio = (nose[0] - ear_mid[0]) / half_ear_dist
    neck_turn_ratio = float(np.clip(neck_turn_ratio, -1.5, 1.5))

    # ratio를 각도처럼 보기 쉽게 스케일
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

# --------------------------------------------------------------------------------------------------------------------
# YOLO 기반 레퍼런스 추출 목운동
def get_neck_rotation_features_yolo(pts: dict):
    """
    YOLOv8 Pose COCO keypoint 기준 목 좌우 회전 feature 추출

    YOLO 번호:
    0  : nose
    3  : left_ear
    4  : right_ear
    5  : left_shoulder
    6  : right_shoulder
    11 : left_hip
    12 : right_hip
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

# -----------공용-------------------------------------------------------------------------------------------------------
# 좌우 반전용 함수
def flip_mediapipe_left_right(pts: dict):
    """
    MediaPipe landmark 좌우 반전
    - 이미지 자체를 뒤집는 게 아니라
    - landmark 의미를 좌우 교환해서
      left 운동도 right 기준 extractor로 처리할 수 있게 함
    """
    swap_pairs = {
        11: 12, 12: 11,   # shoulder
        13: 14, 14: 13,   # elbow
        15: 16, 16: 15,   # wrist
        23: 24, 24: 23,   # hip
        25: 26, 26: 25,   # knee
        27: 28, 28: 27,   # ankle
    }

    flipped = {}
    for k, v in pts.items():
        flipped_key = swap_pairs.get(k, k)
        flipped[flipped_key] = v

    return flipped