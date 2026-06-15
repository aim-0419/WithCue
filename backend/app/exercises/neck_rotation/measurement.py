# 목 회전 ROM 측정 프로세서
import time
import logging
import os
import numpy as np

from app.exercises.shared.base import BaseProcessor, NECK_ROM_LOG_DIR
from app.exercises.neck_rotation.features import get_neck_rotation_features_yolo

NECK_ROM_LOG_PATH = os.path.join(
    NECK_ROM_LOG_DIR,
    f"neck_rom_{time.strftime('%Y%m%d_%H%M%S')}.log",
)
_neck_rom_logger = logging.getLogger("neck_rom")
if not _neck_rom_logger.handlers:
    os.makedirs(NECK_ROM_LOG_DIR, exist_ok=True)
    _neck_rom_logger.setLevel(logging.INFO)
    _neck_rom_handler = logging.FileHandler(NECK_ROM_LOG_PATH, mode="a", encoding="utf-8")
    _neck_rom_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    _neck_rom_handler.setFormatter(_neck_rom_formatter)
    _neck_rom_logger.addHandler(_neck_rom_handler)
    _neck_rom_logger.propagate = False


class NeckROMMeasurementProcessor(BaseProcessor):
    def __init__(self, fps=30):
        self.state = "READY"
        self.fps = fps

        self.hold_frames_required = int(3 * fps)
        self.hold_count = 0
        self.miss_count = 0
        self.hold_start_time = None
        self.left_hold_completed = False

        self.left_values = []
        self.right_values = []

        self.compensation_detected = False

        # threshold(상수분리)
        self.TRUNK_THRESH = 8.0
        self.TILT_THRESH = 30.0
        self.SHOULDER_THRESH = 6.0
        self.LEFT_ENTER_THRESHOLD = -20.0
        self.LEFT_HOLD_MIN_THRESHOLD = -10.0
        self.RIGHT_ENTER_THRESHOLD = 20.0
        self.RIGHT_HOLD_MAX_THRESHOLD = 15.0
        self.CENTER_THRESHOLD = 5.0
        self.MAX_MISS_FRAMES = 5

    def extract_mp_features(self, pts):
        return get_neck_rotation_features_yolo(pts)

    def reset(self):
        self.__init__(self.fps)

    def _is_valid(self, feat):
        trunk, neck, tilt, shoulder = feat
        if abs(trunk) > self.TRUNK_THRESH:
            return False
        if abs(tilt) > self.TILT_THRESH:
            return False
        # shoulder_line_angle는 수평 기준으로 180 근처가 정상
        if abs(shoulder - 180.0) > self.SHOULDER_THRESH:
            return False
        return True

    def process(self, keypoints, frame, depth_frame=None, intrinsics=None, mp_features=None):
        transition_log = None

        if mp_features is None:
            self.hold_count = 0
            self.miss_count = 0
            self.hold_start_time = None
            self.left_hold_completed = False
            return {
                "status": "waiting",
                "message": "자세를 인식 중입니다.",
            }

        feat = mp_features
        trunk, neck_angle, tilt, shoulder = feat

        valid = self._is_valid(feat)
        if not valid:
            self.compensation_detected = True
            self.hold_count = 0
            self.miss_count = 0
            self.hold_start_time = None
            self.left_hold_completed = False
            _neck_rom_logger.info(
                "[NECK_ROM] state=%s hold=%s neck=%.2f trunk=%.2f tilt=%.2f shoulder=%.2f valid=False",
                self.state, self.hold_count, neck_angle, trunk, tilt, shoulder,
            )
            return {
                "status": "invalid",
                "message": "몸통을 고정해주세요",
            }
        else:
            _neck_rom_logger.info(
                "[NECK_ROM] state=%s hold=%s neck=%.2f trunk=%.2f tilt=%.2f shoulder=%.2f valid=True",
                self.state, self.hold_count, neck_angle, trunk, tilt, shoulder,
            )

        # ---------------- READY ----------------
        if self.state == "READY":
            if abs(neck_angle) < self.CENTER_THRESHOLD:
                return {
                    "mode": "MEASURE",
                    "stage": "NECK_ROM",
                    "status": "ready",
                    "message": "정면을 보고 준비하세요",
                }
            if neck_angle <= self.LEFT_ENTER_THRESHOLD:
                transition_log = "READY -> LEFT_HOLD"
                self.state = "LEFT_HOLD"
                self.hold_count = 0
                self.miss_count = 0
                self.hold_start_time = time.monotonic()
                self.left_hold_completed = False

        # ---------------- LEFT ----------------
        elif self.state == "LEFT_HOLD":
            if self.left_hold_completed:
                if abs(neck_angle) <= self.CENTER_THRESHOLD:
                    transition_log = "LEFT_HOLD -> CENTER_RETURN"
                    self.state = "CENTER_RETURN"
                    self.hold_count = 0
                    self.miss_count = 0
                    self.hold_start_time = None
                    return {
                        "status": "center_return",
                        "message": "정면으로 돌아오세요",
                    }
                return {
                    "status": "left_hold",
                    "message": "정면으로 돌아오세요",
                }

            if neck_angle <= self.LEFT_HOLD_MIN_THRESHOLD:
                self.hold_count += 1
                self.miss_count = 0
                self.left_values.append(abs(neck_angle))
                if self.hold_start_time is None:
                    self.hold_start_time = time.monotonic()
                elapsed = time.monotonic() - self.hold_start_time
                if elapsed >= 3.0:
                    self.left_hold_completed = True
                    return {
                        "status": "left_done",
                        "message": "정면으로 돌아오세요",
                    }
            else:
                self.miss_count += 1
                if self.miss_count > self.MAX_MISS_FRAMES:
                    self.hold_count = 0
                    self.miss_count = 0
                    self.left_values = []
                    self.hold_start_time = None

            return {
                "status": "left_hold",
                "message": "고개를 왼쪽으로 돌리고 유지하세요",
            }

        # ---------------- CENTER RETURN ----------------
        elif self.state == "CENTER_RETURN":
            if neck_angle >= self.RIGHT_ENTER_THRESHOLD:
                transition_log = "CENTER_RETURN -> RIGHT_HOLD"
                self.state = "RIGHT_HOLD"
                self.hold_count = 0
                self.miss_count = 0
                self.hold_start_time = None
                return {
                    "status": "center_return",
                    "message": "고개를 오른쪽으로 돌리고 유지하세요",
                }
            return {
                "status": "center_return",
                "message": "정면으로 돌아오세요",
            }

        # ---------------- RIGHT ----------------
        elif self.state == "RIGHT_HOLD":
            if neck_angle >= self.RIGHT_HOLD_MAX_THRESHOLD:
                self.hold_count += 1
                self.miss_count = 0
                self.right_values.append(abs(neck_angle))
                if self.hold_start_time is None:
                    self.hold_start_time = time.monotonic()
                elapsed = time.monotonic() - self.hold_start_time
                if elapsed >= 3.0:
                    transition_log = "RIGHT_HOLD -> DONE"
                    self.state = "DONE"
            else:
                self.miss_count += 1
                if self.miss_count > self.MAX_MISS_FRAMES:
                    self.hold_count = 0
                    self.miss_count = 0
                    self.right_values = []
                    self.hold_start_time = None

            return {
                "status": "right_hold",
                "message": "고개를 오른쪽으로 돌리고 유지하세요",
            }

        # ---------------- DONE ----------------
        if self.state == "DONE":
            if transition_log:
                _neck_rom_logger.info("[NECK_ROM] transition %s", transition_log)
            left_max = float(np.mean(self.left_values)) if self.left_values else 0
            right_max = float(np.mean(self.right_values)) if self.right_values else 0
            return {
                "mode": "MEASURE",
                "stage": "NECK_ROM",
                "status": "finished",
                "message": "목 가동범위 검사가 완료되었습니다",
                "neck_left_max": float(left_max),
                "neck_right_max": float(right_max),
                "neck_diff": float(abs(left_max - right_max)),
                "compensation_detected": bool(self.compensation_detected),
            }

        if transition_log:
            _neck_rom_logger.info("[NECK_ROM] transition %s", transition_log)

        return {"status": "unknown", "neck_angle": round(neck_angle, 1)}
