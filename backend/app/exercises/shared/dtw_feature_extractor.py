# 운동 feature 추출에 공통으로 사용되는 기하 유틸리티.
# 카메라로 얻은 관절 좌표를 바탕으로 각도, 중점, 기울기 등을 계산하는 함수를 제공한다.
# DTW 기반 유사도 비교나 자세 분석에서 원시 좌표를 의미 있는 수치로 변환할 때 사용한다.
import math
import numpy as np


# 세 관절 좌표(p1, p2, p3)로 이루어진 관절 각도를 계산한다.
# p2가 꼭짓점(중심 관절)이며, p1-p2-p3 사이의 각도를 도(degree) 단위로 반환한다.
# 두 벡터 중 하나라도 길이가 0에 가까우면 None을 반환한다.
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


# 두 좌표(p1, p2)의 중간 지점을 계산해 튜플로 반환한다.
# 2D (x, y)와 3D (x, y, z) 모두 처리한다.
# 양쪽 어깨 중앙이나 골반 중앙 등을 구할 때 사용한다.
def midpoint(p1, p2):
    a = np.array(p1, dtype=float)
    b = np.array(p2, dtype=float)
    return tuple((a + b) / 2)


# 두 좌표(p_top, p_bottom)를 잇는 선분이 수직축(위아래 방향)과 이루는 각도를 반환한다.
# 0도에 가까울수록 선분이 수직에 가깝고, 값이 클수록 기울어져 있다는 의미다.
# 두 점이 동일하면 None을 반환한다.
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


# 두 좌표(p1, p2)를 잇는 선분이 수평축(좌우 방향)과 이루는 절대 각도를 반환한다.
# 반환값은 0~180도 범위의 양수이며, 두 점이 동일하면 None을 반환한다.
def line_angle_from_horizontal(p1, p2):
    """
    두 점을 잇는 선분이 수평축과 이루는 절대 각도
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]

    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return None

    return float(abs(math.degrees(math.atan2(dy, dx))))


# 두 좌표(p1, p2)를 잇는 선분이 완전한 수평선에서 얼마나 벗어났는지를 각도로 반환한다.
# 0도이면 완전히 수평이고, 값이 클수록 기울어진 정도가 심하다.
# 두 점이 동일하면 None을 반환한다.
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
