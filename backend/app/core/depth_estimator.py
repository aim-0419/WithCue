# 관절별 depth(z) 누락 시 시간/공간 보정을 수행하는 모듈.
# RealSense depth가 일시적으로 손실된 관절의 z 값을 추정해 3D 좌표 연속성을 유지한다.
# 보정 우선순위: 1) 시간 보간(이전 프레임) → 2) 공간 추정(대칭 관절) → 3) 실패 시 None
# 보정 후 is_coherent()로 전체 z 값의 물리적 일관성을 검증해 배경 혼입을 걸러낸다.

import logging
import numpy as np
import pyrealsense2 as rs

logger = logging.getLogger(__name__)

# YOLO COCO 17 keypoint 기준 좌우 대칭 쌍 {idx: mirror_idx}
_SYMMETRIC: dict[int, int] = {
    1: 2,  2: 1,   # eye
    3: 4,  4: 3,   # ear
    5: 6,  6: 5,   # shoulder
    7: 8,  8: 7,   # elbow
    9: 10, 10: 9,  # wrist
    11: 12, 12: 11, # hip
    13: 14, 14: 13, # knee
    15: 16, 16: 15, # ankle
}


# depth 누락 관절을 시간 보간 → 대칭 공간 추정 순으로 복원하는 클래스.
# MotionService 인스턴스당 하나씩 생성해 세션 동안 관절별 depth 이력을 유지한다.
class DepthEstimator:
    # 이전 값을 재사용할 최대 프레임 수. 30fps 기준 5프레임 ≈ 167ms.
    MAX_AGE = 5

    def __init__(self):
        # {joint_idx: {"z": float, "age": int}}
        self._history: dict[int, dict] = {}

    # keypoints를 인플레이스 수정: z가 None인 관절에 추정 z와 재계산된 x_m, y_m을 채운다.
    # intrinsics: RealSense color 스트림 내부 파라미터 (픽셀 → 미터 역투영에 사용).
    def estimate(self, keypoints: dict, intrinsics) -> None:
        # 현재 프레임의 유효 z 수집 및 이력 갱신
        current_valid_z: dict[int, float] = {}
        for idx, kp in keypoints.items():
            if kp.get("z") is not None:
                current_valid_z[idx] = kp["z"]
                self._history[idx] = {"z": kp["z"], "age": 0}
            elif idx in self._history:
                self._history[idx]["age"] += 1

        # z 누락 관절 순서대로 보정 시도
        for idx, kp in keypoints.items():
            if kp.get("z") is not None:
                continue

            estimated_z = (
                self._temporal(idx)
                or self._spatial(idx, current_valid_z)
            )
            if estimated_z is None:
                continue

            self._apply(kp, estimated_z, intrinsics)
            # 추정값도 이력에 등록 (age는 유지)
            age = self._history.get(idx, {}).get("age", 1)
            self._history[idx] = {"z": estimated_z, "age": age}

    # 이전 프레임 보간: MAX_AGE 이내의 마지막 유효 z 반환.
    def _temporal(self, idx: int) -> float | None:
        entry = self._history.get(idx)
        if entry and entry["age"] <= self.MAX_AGE:
            return entry["z"]
        return None

    # 공간 추정: 대칭 관절의 현재 프레임 z 반환.
    # 양측 관절(어깨, 힙 등)이 카메라와 비슷한 거리에 있다고 가정한다.
    def _spatial(self, idx: int, current_valid_z: dict) -> float | None:
        sym = _SYMMETRIC.get(idx)
        return current_valid_z.get(sym)

    # 추정된 z로 x_m, y_m을 카메라 내부 파라미터로 역투영해 keypoint에 채운다.
    # 픽셀 좌표는 STREAM(640×360) → CAMERA(1280×720)로 변환 후 사용한다.
    def _apply(self, kp: dict, z: float, intrinsics) -> None:
        kp["z"] = z
        if intrinsics is None:
            return
        u = kp["x"] * 2.0  # STREAM → CAMERA 해상도
        v = kp["y"] * 2.0
        try:
            point = rs.rs2_deproject_pixel_to_point(intrinsics, [u, v], z)
            kp["x_m"] = float(point[0])
            kp["y_m"] = float(point[1])
        except Exception as e:
            logger.debug("역투영 실패 (z=%.3f): %s", z, e)

    # 관절들의 z 값이 물리적으로 일관된지 검증한다.
    # 유효 관절이 3개 미만이거나, z 분산이 1m 초과이거나, 평균 거리가 재활 유효 범위 밖이면 False.
    # z_std > 1.0m: YOLO 감지 범위 안에 배경 객체가 혼입된 경우 (재활 동작 중 불가능한 차이).
    # valid_range: D435의 실용 정확도 범위(0.3~5.0m). 범위 밖에서는 depth 오차가 커진다.
    @staticmethod
    def is_coherent(
        keypoints: dict,
        max_z_std: float = 1.0,
        valid_range: tuple[float, float] = (0.3, 5.0),
    ) -> bool:
        z_vals = [v["z"] for v in keypoints.values() if v.get("z") is not None]
        if len(z_vals) < 3:
            return False
        z_mean = float(np.mean(z_vals))
        z_std  = float(np.std(z_vals))
        if z_std > max_z_std:
            return False
        if not (valid_range[0] <= z_mean <= valid_range[1]):
            return False
        return True

    def reset(self) -> None:
        self._history.clear()
