import math
from typing import Union, Dict, List, Any

def _get_coords(p:Any) -> tuple:
    """
    {'x':100, 'y': 200} -> (100, 200)
    [100, 200]          -> (100, 200)
    None                -> (0, 0)
    """
    if p is None:
        return 0.0, 0.0
   
    if isinstance(p, dict):
        return p.get('x', 0.0), p.get('y', 0.0)
   
    if isinstance(p, (list, tuple)):
        if len(p) >= 2:
            return p[0], p[1]

    return 0.0, 0.0
    
def calculate_angle(p1: Union[Dict, List], p2: Union[Dict, List], p3: Union[Dict, List]) -> float:
    """
    세 점(p1-p2-p3) 사이의 각도를 계산 (p2가 중심점 Vertex)
    반환값: 0 ~ 180도
    """
    x1, y1 = _get_coords(p1)
    x2, y2 = _get_coords(p2)
    x3, y3 = _get_coords(p3)

    # 벡터 계산
    v1_x = x1 - x2
    v1_y = y1 - y2
    v2_x = x3 - x2
    v2_y = y3 - y2

    # 내적 (Dot Product)
    dot_product = v1_x * v2_x + v1_y * v2_y
    
    # 벡터 크기 (Magnitude)
    mag1 = math.sqrt(v1_x**2 + v1_y**2)
    mag2 = math.sqrt(v2_x**2 + v2_y**2)

    if mag1 * mag2 == 0:
        return 0.0

    # 아크코사인 (Clamp 처리로 오차 방지)
    cos_theta = max(-1.0, min(1.0, dot_product / (mag1 * mag2)))
    
    angle_rad = math.acos(cos_theta)
    
    return math.degrees(angle_rad)

def calculate_3d_angle(p1: Any, p2: Any, p3: Any) -> float:
    """
    3D 공간상의 세 점(p1-p2-p3) 사이의 각도를 계산 (p2가 중심점)
    Z축 깊이 값을 포함하여 계산하므로 더 정확한 분석 가능
    반환값: 0 ~ 180도
    """
    x1, y1, z1 = _get_coords_3d(p1)
    x2, y2, z2 = _get_coords_3d(p2)
    x3, y3, z3 = _get_coords_3d(p3)
    
    # 벡터 BA (p1 - p2)
    v1_x, v1_y, v1_z = x1 - x2, y1 - y2, z1 - z2
    # 벡터 BC (p3 - p2)
    v2_x, v2_y, v2_z = x3 - x2, y3 - y2, z3 - z2
    
    # 3D 내적 (Dot Product)
    dot_product = v1_x * v2_x + v1_y * v2_y + v1_z * v2_z
    
    # 3D 벡터 크기 (Magnitude)
    mag1 = math.sqrt(v1_x**2 + v1_y**2 + v1_z**2)
    mag2 = math.sqrt(v2_x**2 + v2_y**2 + v2_z**2)
    
    if mag1 * mag2 == 0:
        return 0.0
    
    cos_theta = max(-1.0, min(1.0, dot_product / (mag1 * mag2)))
    
    return math.degrees(math.acos(cos_theta))

def _get_coords_3d(p:Any) -> tuple:
    """
    {'x':100, 'y': 200} -> (100, 200)
    [100, 200]          -> (100, 200)
    None                -> (0, 0)
    """
    if p is None:
        return 0.0, 0.0, 0.0
    
    if isinstance(p, dict):
        return p.get('x', 0.0), p.get('y', 0.0), p.get('z', 0.0)
    
    if isinstance(p, (list, tuple)):
        if len(p) >= 3:
            return p[0], p[1], p[2]
        elif len(p) == 2:
            return p[0], p[1], 0.0

    return 0.0, 0.0, 0.0

def calculate_angle_2d(p1, center, p2):
    """
    3개의 점(p1, center, p2) 사이의 2D 평면(x, y) 각도를 계산함.
    Z축(깊이)는 무시하며, 0도 ~ 180도 사이의 값을 반환함.
    
    Args:
        p1 (dict): 첫 번째 점 (예: 골반)
        center (dict): 두 번째 점 (예: 무릎)
        p2 (dict): 세 번째 점 (예: 발목)
        
    Returns:
        float: 각도 (도, degree)
    """
    # 1. 벡터 생성 (중심점 기준)
    v1_x = p1['x_m'] - center['x_m']
    v1_y = p1['y_m'] - center['y_m']

    v2_x = p2['x_m'] - center['x_m']
    v2_y = p2['y_m'] - center['y_m']
    
    # 2. 내적(Dot Product)과 벡터의 크기(Magnitude) 계산
    dot_product = v1_x * v2_x + v1_y * v2_y
    mag1 = math.sqrt(v1_x**2 + v1_y**2)
    mag2 = math.sqrt(v2_x**2 + v2_y**2)
    
    # 3. 예외 처리 (벡터 길이가 0인 경우)
    if mag1 * mag2 == 0:
        return 180.0
    
    # 4. 아크코사인 (acos)으로 각도 추출
    # 부동소수점 오차로 인해 -1.0 ~ 1.0 범위를 벗어나는 것을 방지
    cos_val = max(-1.0, min(1.0, dot_product / (mag1 * mag2)))
    angle_rad = math.acos(cos_val)
    
    return math.degrees(angle_rad)