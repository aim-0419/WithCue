# 무릎/하지 가동범위(ROM) 측정 프로세서.
# 오디오 스크립트가 phase를 주도하며, 백엔드는 phase별 최대값만 갱신한다.
# 세션 종료는 프론트의 DONE 신호(set_phase("DONE"))로만 이루어진다.
import logging
from datetime import datetime

from app.exercises.shared.base import BaseProcessor
from app.core.geometry import calculate_3d_angle

logger = logging.getLogger(__name__)


class KneeROMMeasurementProcessor(BaseProcessor):

    def __init__(self):
        self.check_tag = "check_knee"
        self._phase = "IDLE"
        self._finished = False
        self.seated_ext_left_max  = 0.0
        self.seated_ext_right_max = 0.0
        self.hip_raise_left_max   = 0.0
        self.hip_raise_right_max  = 0.0

    def set_phase(self, phase):
        if phase == "DONE":
            self._finished = True
        else:
            self._phase = phase
            logger.info("[KneeROM] phase → %s", phase)

    # 무릎 신전(hip-knee-ankle) + 고관절 굴곡(shoulder-hip-knee) 동시 계산
    def extract_mp_features(self, pts):
        result = {}
        if all(k in pts for k in [11, 13, 15]):
            result["left_knee"]  = calculate_3d_angle(pts[11], pts[13], pts[15])
        if all(k in pts for k in [12, 14, 16]):
            result["right_knee"] = calculate_3d_angle(pts[12], pts[14], pts[16])
        # 서서 무릎 들기: shoulder-hip-knee 각도 → 굴곡각(180-각도)으로 변환
        if all(k in pts for k in [5, 11, 13]):
            result["left_hip_flexion"]  = max(0.0, 180.0 - calculate_3d_angle(pts[5],  pts[11], pts[13]))
        if all(k in pts for k in [6, 12, 14]):
            result["right_hip_flexion"] = max(0.0, 180.0 - calculate_3d_angle(pts[6],  pts[12], pts[14]))
        return result if result else None

    def process(self, keypoints, frame, depth_frame=None, intrinsics=None, mp_features=None):
        if self._finished:
            return {
                "mode": "MEASURE",
                "stage": "KNEE_ROM",
                "status": "finished",
                "message": "무릎 검사가 완료되었습니다",
                "rom": {
                    "seated_knee_extension_left_max":  int(self.seated_ext_left_max),
                    "seated_knee_extension_right_max": int(self.seated_ext_right_max),
                    "straight_leg_raise_left_max":     int(self.hip_raise_left_max),
                    "straight_leg_raise_right_max":    int(self.hip_raise_right_max),
                },
                "measured_at": datetime.now().isoformat(timespec="seconds"),
            }

        if mp_features is None:
            return {"mode": "MEASURE", "stage": "KNEE_ROM", "status": "waiting", "message": "전신이 화면에 보이도록 서주세요."}

        # phase별 최대값 갱신
        if self._phase == "KNEE_LEFT_EXTEND":
            v = mp_features.get("left_knee") or 0
            if v > self.seated_ext_left_max:
                self.seated_ext_left_max = v
        elif self._phase == "KNEE_RIGHT_EXTEND":
            v = mp_features.get("right_knee") or 0
            if v > self.seated_ext_right_max:
                self.seated_ext_right_max = v
        elif self._phase == "KNEE_LEFT_RAISE":
            v = mp_features.get("left_hip_flexion") or 0
            if v > self.hip_raise_left_max:
                self.hip_raise_left_max = v
        elif self._phase == "KNEE_RIGHT_RAISE":
            v = mp_features.get("right_hip_flexion") or 0
            if v > self.hip_raise_right_max:
                self.hip_raise_right_max = v

        return {
            "mode": "MEASURE",
            "stage": "KNEE_ROM",
            "status": "measuring",
            "phase": self._phase,
        }
