# 무릎 들기 운동 YOLO feature 추출
from app.exercises.shared.dtw_feature_extractor import (
    calc_angle,
    line_angle_from_vertical,
    line_angle_from_horizontal,
)


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
