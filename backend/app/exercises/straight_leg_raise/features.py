# Straight Leg Raise(다리 들기) 운동의 관절 각도와 신체 수치를 계산하는 모듈.
# 옆으로 누운 자세에서 다리를 곧게 편 채 들어올리는 동작(SLR)에 필요한
# 엉덩이 굽힘 각도, 무릎 각도, 발목 높이 등 3개의 feature 수치를 추출한다.
# YOLO 방식의 관절 좌표를 기반으로 하며, 왼쪽 다리 운동 시 좌우 반전 함수를 제공한다.
from app.exercises.shared.dtw_feature_extractor import (
    calc_angle,
    line_angle_from_vertical,
    line_angle_from_horizontal,
)


# YOLOv8 관절 좌표를 받아 오른쪽 다리 Straight Leg Raise 운동의 3개 feature 수치를 계산한다.
# pts: YOLO COCO 기준 관절 번호를 키, (x, y) 좌표를 값으로 갖는 딕셔너리
# 반환: [엉덩이굽힘각도, 무릎각도, 발목높이] 3개 실수 리스트.
#        필요한 관절(오른어깨/양쪽엉덩이/오른무릎/오른발목)이 감지되지 않으면 None 반환.
def get_straight_leg_raise_right_features_yolo(pts: dict):
    """
    YOLOv8 Pose COCO 기준 오른다리 Straight Leg Raise feature 추출

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


# YOLO COCO 관절 번호 기준으로 좌우 쌍을 교환해 반전된 좌표 딕셔너리를 반환한다.
# 왼쪽 다리 Straight Leg Raise 동작을 오른쪽 기준 feature 함수로 처리할 때 사용한다.
# pts: 원본 YOLO 관절 좌표 딕셔너리
# 반환: 좌우가 교환된 관절 좌표 딕셔너리
def flip_yolo_left_right(pts: dict):
    """
    YOLOv8 Pose COCO keypoint 좌우 반전
    """
    swap_pairs = {
        5: 6, 6: 5,
        7: 8, 8: 7,
        9: 10, 10: 9,
        11: 12, 12: 11,
        13: 14, 14: 13,
        15: 16, 16: 15,
    }

    flipped = {}
    for k, v in pts.items():
        flipped_key = swap_pairs.get(k, k)
        flipped[flipped_key] = v

    return flipped
