# 어깨 전방 거상 운동의 보상자세를 의학적 기준 임계값으로 감지하는 모듈.
# 감지 대상: 팔꿈치 굽힘 / 어깨 상승 / 체간 과신전(허리 꺽임).

import numpy as np

# ── 관절 인덱스 (YOLO COCO 17 → 8관절 배열 내 위치) ──────────────────────────
_IDX_SHOULDER_L = 0
_IDX_ELBOW_L    = 1
_IDX_WRIST_L    = 2
_IDX_SHOULDER_R = 3
_IDX_ELBOW_R    = 4
_IDX_WRIST_R    = 5
_IDX_HIP_L      = 6
_IDX_HIP_R      = 7

_COCO_TO_8 = [5, 7, 9, 6, 8, 10, 11, 12]
# ShoulderL ElbowL WristL ShoulderR ElbowR WristR HipL HipR

MIN_REP_FRAMES = 15   # 감지를 시도할 최소 프레임 수

# ── 의학적 기준 임계값 ─────────────────────────────────────────────────────────
# 팔꿈치 굽힘: rep 시작 대비 증가량(delta) 기준. Kalman 필터링된 3D 좌표 사용.
# 받쳐주는 자세로 인해 시작 시 이미 굽혀져 있으므로 절대값이 아닌 delta로 판단.
ELBOW_WARN_DEG   = 30.0
ELBOW_DANGER_DEG = 50.0

# 어깨 상승: Kalman 필터링된 3D 좌표 기반 절대 상승량.
# 정상: 팔 거상 시 어깨 상승 < 8cm. 보상: 10cm 이상 상승.
# (타이밍 기반은 지속적 으쓱 패턴을 early_ratio ~0.27로 놓쳐서 폐기)
SHOULDER_WARN   = 0.08
SHOULDER_DANGER = 0.14

# 체간 과신전: >10° 체간 신전 시 보상 (어깨 재활 가이드라인).
TRUNK_WARN_DEG   = 10.0
TRUNK_DANGER_DEG = 20.0

_BASE_N = 5   # rep 시작 구간 기준 프레임 수 (delta 기준선)


def _warn_or_higher(value, warn, danger):
    return value >= warn


def _extract_8(keypoints: dict) -> np.ndarray | None:
    """keypoints dict → (8,3) float32. 3D 좌표 누락 시 None. RealSense Y 반전 적용."""
    joints = []
    for coco_idx in _COCO_TO_8:
        kp = keypoints.get(coco_idx)
        if kp is None:
            return None
        x_m = kp.get("x_m")
        y_m = kp.get("y_m")
        z   = kp.get("z")
        if x_m is None or y_m is None or z is None:
            return None
        joints.append([float(x_m), -float(y_m), float(z)])
    return np.array(joints, dtype=np.float32)


def _detect_arm(raw_frames: list) -> str:
    """팔꿈치 최대 거상으로 주동작 팔 판단."""
    f     = np.array(raw_frames)
    hip_y = (f[:, _IDX_HIP_L, 1] + f[:, _IDX_HIP_R, 1]) / 2.0
    el_l  = np.max(f[:, _IDX_ELBOW_L, 1] - hip_y)
    el_r  = np.max(f[:, _IDX_ELBOW_R, 1] - hip_y)
    return 'L' if el_l >= el_r else 'R'


def _check_elbow_flexion(raw_frames: list, arm_side: str) -> list[str]:
    """
    팔꿈치 굽힘 감지.
    XY 평면만 사용해 Z 깊이 노이즈를 제거하고, 절대 피크 각도로 판단.
    delta 방식은 baseline에 이미 굽힘이 있으면 놓치고, Z 노이즈에도 민감해 오탐 많음.
    """
    f  = np.array(raw_frames)
    sh = f[:, _IDX_SHOULDER_L] if arm_side == 'L' else f[:, _IDX_SHOULDER_R]
    el = f[:, _IDX_ELBOW_L]    if arm_side == 'L' else f[:, _IDX_ELBOW_R]
    wr = f[:, _IDX_WRIST_L]    if arm_side == 'L' else f[:, _IDX_WRIST_R]

    ua = el - sh
    fa = wr - el
    ua = ua / (np.linalg.norm(ua, axis=1, keepdims=True) + 1e-6)
    fa = fa / (np.linalg.norm(fa, axis=1, keepdims=True) + 1e-6)

    elbow_deg = np.degrees(np.arccos(np.clip(np.sum(ua * fa, axis=1), -1.0, 1.0)))
    base_n    = min(_BASE_N, len(elbow_deg) // 4)
    delta     = max(0.0, float(np.max(elbow_deg)) - float(np.mean(elbow_deg[:base_n])))

    if _warn_or_higher(delta, ELBOW_WARN_DEG, ELBOW_DANGER_DEG):
        side = "왼쪽" if arm_side == 'L' else "오른쪽"
        return [f"{side} 팔꿈치가 구부러졌어요. 팔을 곧게 펴세요."]
    return []


def _check_shoulder_elevation(raw_frames: list, arm_side: str) -> list[str]:
    """
    어깨 상승 감지. Kalman 필터링된 3D 좌표 기반 절대 상승량.
    운동 팔 어깨-엉덩이 상대 높이의 rep 시작 대비 최대 증가량으로 판단.
    타이밍 기반은 지속적 으쓱 패턴(early_ratio ~0.27)을 놓쳐서 절대값으로 복귀.
    """
    f      = np.array(raw_frames, dtype=np.float64)
    sh_idx = _IDX_SHOULDER_L if arm_side == 'L' else _IDX_SHOULDER_R
    hp_idx = _IDX_HIP_L      if arm_side == 'L' else _IDX_HIP_R

    height = f[:, sh_idx, 1] - f[:, hp_idx, 1]

    base_n = min(_BASE_N, len(height) // 4)
    delta  = max(0.0, float(np.max(height)) - float(np.mean(height[:base_n])))

    if delta >= SHOULDER_WARN:
        side = "왼쪽" if arm_side == 'L' else "오른쪽"
        return [f"{side} 어깨가 위로 올라갔어요. 어깨 힘을 빼고 내리세요."]
    return []


def _check_trunk_lean(raw_frames: list) -> list[str]:
    """
    체간 과신전 감지. 척추 벡터의 전후 기울기 각도를 수직 기준으로 측정.
    측면 촬영(카메라가 사람 옆에서 촬영): 전후 기울기가 Z(깊이)가 아닌 X(수평)에 반영됨.
    """
    f     = np.array(raw_frames, dtype=np.float64)
    hip_c = (f[:, _IDX_HIP_L] + f[:, _IDX_HIP_R]) / 2.0
    sh_c  = (f[:, _IDX_SHOULDER_L] + f[:, _IDX_SHOULDER_R]) / 2.0
    spine = sh_c - hip_c

    trunk_deg = np.degrees(np.arctan2(np.abs(spine[:, 0]), np.maximum(spine[:, 1], 1e-6)))
    base_n    = min(_BASE_N, len(trunk_deg) // 4)
    delta     = max(0.0, float(np.max(trunk_deg)) - float(np.mean(trunk_deg[:base_n])))

    if _warn_or_higher(delta, TRUNK_WARN_DEG, TRUNK_DANGER_DEG):
        return ["상체가 뒤로 젖혀졌어요. 허리를 곧게 유지하세요."]
    return []


def detect_compensations(keypoints_list: list, arm_side: str = 'L') -> tuple[str, list[str]]:
    """
    keypoints dict 리스트 → (팔 방향, 보상자세 메시지 목록).
    arm_side: 'L' 또는 'R'. processor에서 mirror_input 기반으로 명시적으로 전달.
    동적 감지(_detect_arm)는 지지 팔 오감지 문제가 있으므로 사용하지 않음.
    """
    raw_frames = [f for kp in keypoints_list if (f := _extract_8(kp)) is not None]
    if len(raw_frames) < MIN_REP_FRAMES:
        return arm_side, []

    reasons  = _check_elbow_flexion(raw_frames, arm_side)
    reasons += _check_shoulder_elevation(raw_frames, arm_side)
    reasons += _check_trunk_lean(raw_frames)
    return arm_side, reasons
