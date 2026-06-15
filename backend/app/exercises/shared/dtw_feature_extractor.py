# 운동 feature 추출에 공통으로 사용되는 기하 유틸리티
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
    두 점을 잇는 선분이 수평선에서 얼마나 벗어났는지 계산
    0도 = 완전 수평, 값이 클수록 수평에서 더 많이 벗어남
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]

    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return None

    angle = abs(math.degrees(math.atan2(dy, dx)))

    return float(min(angle, abs(180.0 - angle)))
