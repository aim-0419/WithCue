from typing import Dict, List, Any, Optional, Union
import numpy as np
import math
from app.core.geometry import calculate_angle, calculate_3d_angle, calculate_angle_2d

def get_kpt(keypoints: Dict, idx: int) -> Any:
    """
    안전하게 키포인트 가져오기
    - int 키(5)와 str 키('5') 모두 처리
    """
    if idx in keypoints: return keypoints[idx]
    if str(idx) in keypoints: return keypoints[str(idx)]
    return None

def is_all_joints_visible(keypoints: Dict, required_joints: List[int]) -> bool:
    """ 지정된 모든 관절(인덱스)이 화면에 보이는지 확인 """
    for joint in required_joints:
        if get_kpt(keypoints, joint) is None:
            return False
    return True

def to_coords(point: Optional[Dict]) -> List[float]:
    """
    {'x': 100, 'y': 200, 'z': 0.5} -> [100.0, 200.0, 0.5]
    z값이 없으면 [x, y]만 반환하여 2D/3D를 구분합니다.
    """
    if point is None:
        return [0.0, 0.0]
    
    if 'z' in point and 'x_m' in point:
        return [float(point['x_m']), float(point['y_m']), float(point['z'])]
    
    return [float(point['x']), float(point['y'])]

def auto_calc(p1_raw: Any, p2_raw: Any, p3_raw: Any) -> float:
    """ 데이터의 차원(2D/3D)에 따라 적절한 계산기 선택 """
    p1 = to_coords(p1_raw)
    p2 = to_coords(p2_raw)
    p3 = to_coords(p3_raw)
    
    # 세 점 모두에 z값이 들어있는 경우에만 3D 계산 수행
    if len(p1) == 3 and len(p2) == 3 and len(p3) == 3:
        return calculate_3d_angle(p1, p2, p3)
    return calculate_angle(p1, p2, p3)

def get_pose_angle(stage_name: str, keypoints: Dict) -> float:
    """
    [WithCue 통합 재활 각도 계산기]
    1. SHOULDER_ABDUCTION: 환측(낮은 각도) 우선 측정
    2. SIDE_LEG_RAISE: 상체-골반-무릎ㅍ 사이의 가동성 측정
    3. KNEE_FLEXTION: 측면 뒷무릎 굴곡 측정 (180-사이각)
    """    
    if not keypoints:
        return 0.0
    
    clean_stage = str(stage_name).strip().upper()
    
    # ----------------------------------------------------
    # [Group A] 측정 모드 (Diagnosis)
    # ----------------------------------------------------
    
    # 1. 어깨 외전 (Abduction)
    # 목적: 가동 범위가 더 제한된(각도가 낮은) 팔을 기준으로 측정
    if clean_stage == "SHOULDER_ABDUCTION":
        l_angle = 0.0
        r_angle = 0.0
        
        # 왼쪽: 골반(11) - 어깨(5) - 팔꿈치(7)
        if is_all_joints_visible(keypoints, [11, 5, 7]):
            l_angle = auto_calc(get_kpt(keypoints, 11), get_kpt(keypoints, 5), get_kpt(keypoints, 7))

        # 오른쪽: 골반(12) - 어깨(6) - 팔꿈치(8)
        if is_all_joints_visible(keypoints, [12, 6, 8]):
            r_angle = auto_calc(get_kpt(keypoints, 12), get_kpt(keypoints, 6), get_kpt(keypoints, 8))
            
        if l_angle > 0 and r_angle > 0:
            return min(l_angle, r_angle)
        return max(l_angle, r_angle)

    # 2. 고관절 외전 (Side Leg Raise)
    # 목적: 다리를 올릴 때 상체의 보상 작용(기울임)을 포함한 중심축 각도 확인
    # 어깨 중간 - 골반 중간 - 무릎 기준
    elif stage_name == "SIDE_LEG_RAISE":
        # 1. 필수 관절 확인 (어깨는 상체 기울임용, 다리는 각도용)
        # Z값은 '앞으로 차기' 감지용으로 챙겨둡니다.
        if all(idx in keypoints and 'x_m' in keypoints[idx] for idx in [5, 6, 11, 12, 13, 14]):
            
            # --- [A] 각도 계산 (2D 평면 - Z값 무시) ---
            # 1. 골반 중앙 (2D)
            hip_mid_x = (keypoints[11]['x_m'] + keypoints[12]['x_m']) / 2
            hip_mid_y = (keypoints[11]['y_m'] + keypoints[12]['y_m']) / 2
            
            l_knee = keypoints[13]
            r_knee = keypoints[14]

            # 2. 왼쪽 다리 각도 (atan2)
            dx_l = l_knee['x_m'] - hip_mid_x
            dy_l = l_knee['y_m'] - hip_mid_y
            l_deg = math.degrees(math.atan2(dx_l, dy_l)) # 수직(Y) 기준 각도

            # 3. 오른쪽 다리 각도 (atan2)
            dx_r = r_knee['x_m'] - hip_mid_x
            dy_r = r_knee['y_m'] - hip_mid_y
            r_deg = math.degrees(math.atan2(dx_r, dy_r))

            # 4. 최종 각도 (0도 기준)
            active_leg_angle = max(abs(l_deg), abs(r_deg))


            # --- [B] (옵션) 3D 깊이 체크: 다리가 앞으로 튀어나오나? ---
            # 엉덩이 깊이와 무릎 깊이를 비교
            hip_z = (keypoints[11]['z'] + keypoints[12]['z']) / 2
            
            # 움직이는 다리의 무릎 깊이
            active_knee_z = l_knee['z'] if abs(l_deg) > abs(r_deg) else r_knee['z']
            
            # 무릎이 엉덩이보다 20cm 이상 앞으로 튀어나오면 (카메라 쪽으로)
            # if (hip_z - active_knee_z) > 0.2:
            #     print("⚠️ 경고: 다리를 앞으로 차지 말고 옆으로 차세요!")

            return active_leg_angle

        return 0.0

    # 3-1. 왼쪽 무릎 굴곡 (Left Knee Flexion)
    elif stage_name == "LEFT_KNEE_FLEXION":
        # 필수 관절: 왼쪽 골반(11), 무릎(13), 발목(15)
        if is_all_joints_visible(keypoints, [11, 13, 15]):
            raw_angle = calculate_angle_2d(keypoints[11], keypoints[13], keypoints[15])
            
            return abs(180 - raw_angle)
        
        return 0.0
    
    # 3-2. 오른쪽 무릎 굴곡 (Right Knee Flexion)
    elif stage_name == "RIGHT_KNEE_FLEXION":
        # 필수 관절: 오른쪽 골반(12), 무릎(14), 발목(16)
        if is_all_joints_visible(keypoints, [12, 14, 16]):
            raw_angle = calculate_angle_2d(keypoints[12], keypoints[14], keypoints[16])
            
            return abs(180 - raw_angle)
        
        return 0.0
        

    # ----------------------------------------------------
    # [Group B] 코칭 모드 (Training)
    # ----------------------------------------------------
    elif stage_name == "SHOULDER_EXTERNAL_ROTATION":

        l_angle = 0.0
        r_angle = 0.0

        # 왼쪽
        if is_all_joints_visible(keypoints, [11, 7, 9]):
            p1 = get_kpt(keypoints, 11)
            p2 = get_kpt(keypoints, 7)
            p3 = get_kpt(keypoints, 9)

            if None not in (p1, p2, p3):
                try:
                    l_angle = auto_calc(p1, p2, p3)
                except:
                    l_angle = 0.0

        # 오른쪽
        if is_all_joints_visible(keypoints, [12, 8, 10]):
            p1 = get_kpt(keypoints, 12)
            p2 = get_kpt(keypoints, 8)
            p3 = get_kpt(keypoints, 10)

            if None not in (p1, p2, p3):
                try:
                    r_angle = auto_calc(p1, p2, p3)
                except:
                    r_angle = 0.0

        if l_angle == 0.0 and r_angle == 0.0:
            return None   # ← 중요

        return max(l_angle, r_angle)
        
    return 0.0