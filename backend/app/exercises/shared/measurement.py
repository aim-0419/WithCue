# 측정/코칭 프로세서: ROM 측정, 실시간 코칭
import time
import cv2
import base64
import logging
import os
import numpy as np
from typing import Dict, Any, List

from .base import BaseProcessor
from app.core.utils import AngleSmoother
from app.exercises.shared.posture import get_pose_angle
from app.hardware.camera import camera_manager
from app.core.audio import tts_engine
from app.services.score_service import (
    AccuracyState,
    build_deviation_flags,
    deviation_penalty,
    recovery_bonus,
    update_accuracy,
)

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------------------------------------------------------------------
# 기본 -> 측정 프로세서
# ----------------------------------------------------------------------------------------------------------------------------------------
class MeasurementProcessor(BaseProcessor):
    def __init__(self, target_schedule: List[str] = None):
        super().__init__()
        self.schedule = target_schedule if target_schedule else ["SHOULDER_ABDUCTION", "SIDE_LEG_RAISE", "KNEE_FLEXION"]

        self.current_idx = 0
        self.finished = False

        if len(self.schedule) > 0:
            self.target_stage = self.schedule[self.current_idx]
        else:
            self.target_stage = None
            self.finished = True

        self.PREPARE_DURATION = 5.0
        self.MEASURE_DURATION = 8.0

        self.state = "PREPARE"
        self.start_time = time.time()
        self.max_angle = 0.0
        self.best_frame = None
        self.smoother = AngleSmoother(alpha=0.5)

        # TTS 파일 매핑 및 재생 플래그
        self.tts_assets = {
            "START_INFO": "화면_좌측에_보이는_영상을_따라_자세를_취해주세요.mp3",
            "START_MEASURE": "측정을_시작합니다.mp3",
            "INSTRUCTION": "해당_부위를_올리실_수_있는_만큼_올려주세요.mp3",
            "HOLD": "좋습니다_3초간_유지하세요.mp3",
            "FINISH": "수고하셨습니다_측정이_완료되었습니다.mp3"
        }
        self.played_audio = {key: False for key in self.tts_assets.keys()}

    def process(self, keypoints: Dict, frame: np.ndarray, depth_frame=None, intrinsics=None, mp_features=None,) -> Dict[str, Any]:
        # 0. 종료 체크
        if self.finished:
            return {"status": "finished", "message": "모든 측정이 완료되었습니다."}

        keypoints = camera_manager.update_keypoints_3d(keypoints, depth_frame, intrinsics)

        # 1. 각도 계산
        try:
            raw_angle = get_pose_angle(self.target_stage, keypoints) if keypoints else 0
            if raw_angle is None:
                raw_angle = 0
        except Exception as e:
            logger.warning("Measurement angle calc skipped: %s", e)
            raw_angle = 0
        angle = self.smoother.smooth(raw_angle)
        elapsed = time.time() - self.start_time

        # === [상태 1] 준비단계 (PREPARE) ===
        if self.state == "PREPARE":
            remaining = max(0.0, self.PREPARE_DURATION - elapsed)

            if self.target_stage == "KNEE_FLEXION":
                is_visible = any(i in keypoints for i in [5, 11, 13, 15]) or any(i in keypoints for i in [6, 12, 14, 16])
            else:
                is_visible = all(i in keypoints for i in [5, 6, 11, 12])

            if not self.played_audio["START_INFO"]:
                tts_engine.play(self.tts_assets["START_INFO"])
                self.played_audio["START_INFO"] = True

            if not is_visible:
                self.start_time = time.time()
                return {
                    "status": "preparing", "stage": self.target_stage, "angle": int(angle),
                    "timer": int(self.PREPARE_DURATION), "message": "전신이 화면에 다 들어와야 시작합니다.",
                    "progress": f"{self.current_idx + 1}/{len(self.schedule)}"
                }

            # 시간이 다 되면 -> 측정 모드로 전환
            if remaining <= 0:
                self.state = "MEASURE"
                self.start_time = time.time()
                self.max_angle = 0.0
                tts_engine.play(self.tts_assets["START_MEASURE"])
                return {
                    "status": "transition",
                    "message": "측정을 시작합니다!"
                }

            return {
                "status": "preparing",
                "stage": self.target_stage,
                "angle": int(angle),
                "timer": int(remaining),
                "message": f"자세를 취해주세요... ({int(remaining)}초)",
                "progress": f"{self.current_idx + 1}/{len(self.schedule)}"
            }

        # === [상태 2] 측정 단계 (MEASURE) ===
        elif self.state == "MEASURE":
            remaining = max(0.0, self.MEASURE_DURATION - elapsed)

            if elapsed > 5.0 and not self.played_audio["HOLD"]:
                tts_engine.play(self.tts_assets["HOLD"])
                self.played_audio["HOLD"] = True

                self.start_time = time.time() + 3.5
                self.state = "HOLD"

            # [핵심] 신기록 갱신 로직 (Best Shot Capture)
            if angle > self.max_angle:
                self.max_angle = angle
                if frame is not None:
                    self.best_frame = frame.copy()
                    logger.info(
                        "[Best Shot] max angle updated to %.1f and frame captured",
                        self.max_angle,
                    )

            return {
                "status": "measuring",
                "stage": self.target_stage,
                "angle": int(angle),
                "max_angle": int(self.max_angle),
                "timer": int(max(0, 5.0 - elapsed)),
                "progress": f"{self.current_idx + 1}/{len(self.schedule)}"
            }

        # === [상태 3] 유지 단계 (HOLD) ===
        elif self.state == "HOLD":
            wait_time = time.time() - self.start_time

            if wait_time < 0:
                display_timer = 3
                message = "안내에 따라 자세를 유지하세요..."
            else:
                remaining_hold = max(0.0, 3.0 - wait_time)
                display_timer = int(remaining_hold)
                message = f"그대로 멈추세요! 유지! ({display_timer + 1}초)"

                if remaining_hold <= 0:
                    tts_engine.play(self.tts_assets["FINISH"])
                    return self._complete_stage()

        return {
            "status": "holding",
            "stage": self.target_stage,
            "angle": int(angle),
            "max_angle": int(self.max_angle),
            "timer": display_timer,
            "message": message,
            "progress": f"{self.current_idx + 1}/{len(self.schedule)}"
        }

    def _complete_stage(self) -> Dict[str, Any]:
        """ 한 부위 측정이 끝났을 때 데이터 패키징 """
        logger.info(
            "[Measure Complete] stage=%s max_angle=%.1f best_frame=%s progress=%s/%s",
            self.target_stage,
            self.max_angle,
            "yes" if self.best_frame is not None else "no",
            self.current_idx + 1,
            len(self.schedule),
        )

        # 이미지 Base64 인코딩
        best_image_b64 = None
        if self.best_frame is not None:
            try:
                small_frame = cv2.resize(self.best_frame, (1280, 720))
                _, buffer = cv2.imencode('.jpg', small_frame)
                best_image_b64 = base64.b64encode(buffer).decode('utf-8')
            except Exception as e:
                logger.exception("Best image encode error: %s", e)

        result_packet = {
            "status": "stage_finished",
            "stage": self.target_stage,
            "max_angle": int(self.max_angle),
            "best_image": best_image_b64,
            "message": f"{self.target_stage} 측정 완료!"
        }

        self.next_stage()
        return result_packet

    def next_stage(self):
        """ 다음 운동으로 넘어가기 & 변수 초기화 """
        self.current_idx += 1
        if self.current_idx < len(self.schedule):
            self.target_stage = self.schedule[self.current_idx]
            self.state = "PREPARE"
            self.start_time = time.time()
            self.max_angle = 0.0
            self.best_frame = None
            self.played_audio = {key: False for key in self.tts_assets.keys()}
        else:
            self.finished = True

# -------------------------------------------------------------------------------------------------
# 기본 -> 코칭 프로세서
# -------------------------------------------------------------------------------------------------
class CoachingProcessor(BaseProcessor):
    def __init__(self, exercise_name: str, limit_angle: int = 45):
        """
        Args:
            exercise_name (str): api.py에서 변환된 실제 운동 이름 (예: 'SHOULDER_EXTERNAL_ROTATION')
            limit_angle (int): 목표 각도 (기본값 45도 설정으로 에러 방지)
        """
        self.exercise_name = exercise_name
        self.limit_angle = limit_angle if limit_angle is not None else 45

        self.smoother = AngleSmoother(alpha=0.5)

        # [핵심] 실시간 코칭에서 과도한 음성 반복을 막기 위해 마지막 피드백 시각을 관리
        self.last_feeedback = None
        self.last_feedback_time = 0
        self.feedback_interval = 4.0
        self.init_shoulder_y = None
        self.active_side = None

        self.tts_assets = {
            "ELBOW_AWAY": "팔꿈치를_옆구리에_붙여주세요.mp3",
            "SHOULDER_DOWN": "어깨에_힘을_빼고_내려주세요.mp3",
            "ENCOURAGE": "조금만_더_돌려볼까요.mp3",
            "GOOD": "잘하고_계세요_천천히_돌아올까요.mp3",
            "LIMIT": "통증이_느껴지시면_돌아오겠습니다.mp3"
        }
        self.accuracy_state = AccuracyState()

    def _play_coaching(self, key: str):
        curr = time.time()
        if curr - self.last_feedback_time < self.feedback_interval:
            return
        filename = self.tts_assets.get(key)
        if not filename:
            return
        tts_engine.play(filename)
        logger.info("Play coaching audio: key=%s file=%s", key, filename)
        self.last_feedback_time = curr

    def process(self, keypoints: Dict, frame: np.ndarray, depth_frame=None, intrinsics=None, mp_features=None) -> Dict[str, Any]:
        logger.debug("Coaching process called. keypoints=%s", len(keypoints) if keypoints else 0)
        if not keypoints:
            self.init_shoulder_y = None
            self.active_side = None
            return {
                "mode": "COACH",
                "feedback": "화면 안으로 들어오세요.",
                "accuracy_pct": round(self.accuracy_state.accuracy_pct, 2),
                "min_accuracy_pct": round(self.accuracy_state.min_accuracy_pct, 2),
                "penalty_delta_pct": 0.0,
                "recovery_delta_pct": 0.0,
                "deviation_flags": build_deviation_flags(),
            }

        try:
            keypoints = {int(k): v for k, v in keypoints.items()}
        except Exception as e:
            logger.exception("Keypoint key conversion failed: %s | keys=%s", e, list(keypoints.keys()))
            return {"mode": "COACH", "feedback": "데이터 오류 발생"}

        keypoints = camera_manager.update_keypoints_3d(keypoints, depth_frame, intrinsics)

        sh, el = None, None
        if 6 in keypoints and 8 in keypoints:
            sh, el = 6, 8
            self.active_side = "Right"
            logger.debug("Detected right side (6, 8).")
        elif 5 in keypoints and 7 in keypoints:
            sh, el = 5, 7
            self.active_side = "Left"
            logger.debug("Detected left side (5, 7).")
        else:
            logger.warning("Side detection failed. keypoints=%s", list(keypoints.keys()))
            return {"mode": "COACH", "feedback": "상반신이 잘 보이게 서주세요."}

        for idx in [sh, el]:
            if keypoints[idx].get('x_m') is None or keypoints[idx].get('y_m') is None:
                logger.debug("Skip angle calc due to missing 3D point.")
                return {
                    "mode": "COACH",
                    "exercise": self.exercise_name,
                    "side": self.active_side,
                    "feedback": "자세를 유지해주세요.",
                    "accuracy_pct": round(self.accuracy_state.accuracy_pct, 2),
                    "min_accuracy_pct": round(self.accuracy_state.min_accuracy_pct, 2),
                    "penalty_delta_pct": 0.0,
                    "recovery_delta_pct": 0.0,
                    "deviation_flags": build_deviation_flags(),
                }

        try:
            raw_angle = get_pose_angle(self.exercise_name, keypoints)
            if raw_angle is None:
                logger.debug("raw_angle is None.")
                return {
                    "mode": "COACH",
                    "exercise": self.exercise_name,
                    "side": self.active_side,
                    "feedback": "자세를 유지해주세요.",
                    "accuracy_pct": round(self.accuracy_state.accuracy_pct, 2),
                    "min_accuracy_pct": round(self.accuracy_state.min_accuracy_pct, 2),
                    "penalty_delta_pct": 0.0,
                    "recovery_delta_pct": 0.0,
                    "deviation_flags": build_deviation_flags(),
                }
            smooth_angle = self.smoother.smooth(raw_angle)
            if smooth_angle is None:
                logger.debug("smooth_angle is None.")
                return {
                    "mode": "COACH",
                    "exercise": self.exercise_name,
                    "side": self.active_side,
                    "feedback": "자세를 유지해주세요.",
                    "accuracy_pct": round(self.accuracy_state.accuracy_pct, 2),
                    "min_accuracy_pct": round(self.accuracy_state.min_accuracy_pct, 2),
                    "penalty_delta_pct": 0.0,
                    "recovery_delta_pct": 0.0,
                    "deviation_flags": build_deviation_flags(),
                }
            smooth_angle = float(smooth_angle)
            logger.debug("raw_angle=%s", raw_angle)
        except Exception as e:
            logger.exception("Angle calculation failed: %s", e)
            return {
                "mode": "COACH",
                "exercise": self.exercise_name,
                "side": self.active_side,
                "feedback": "자세를 확인해주세요.",
                "accuracy_pct": round(self.accuracy_state.accuracy_pct, 2),
                "min_accuracy_pct": round(self.accuracy_state.min_accuracy_pct, 2),
                "penalty_delta_pct": 0.0,
                "recovery_delta_pct": 0.0,
                "deviation_flags": build_deviation_flags(),
            }

        logger.debug("[%s] angle=%s stage=%s", self.active_side, int(smooth_angle), self.exercise_name)

        feedback_msg = "자세 좋습니다!"
        elbow_excess_deg = 0.0
        shoulder_excess_deg = 0.0

        if self.exercise_name == "SHOULDER_EXTERNAL_ROTATION":
            if self.init_shoulder_y is None:
                self.init_shoulder_y = keypoints[sh]['y_m']
            elbow_dist = abs(keypoints[el]['x_m'] - keypoints[sh]['x_m'])
            elbow_excess_deg = max(0.0, (elbow_dist - 0.15) * 100.0)
            sh_rise = self.init_shoulder_y - keypoints[sh]['y_m']
            shoulder_excess_deg = max(0.0, (sh_rise - 0.05) * 200.0)

            if elbow_dist > 0.15:
                feedback_msg = "팔꿈치를 붙여주세요!"
                self._play_coaching("ELBOW_AWAY")
            elif sh_rise > 0.05:
                feedback_msg = "어깨에 힘을 빼세요!"
                self._play_coaching("SHOULDER_DOWN")
            else:
                if smooth_angle < self.limit_angle * 0.5:
                    feedback_msg = "조금만 더 돌려볼까요 ?"
                    self._play_coaching("ENCOURAGE")
                elif smooth_angle < self.limit_angle * 0.9:
                    feedback_msg = "아주 잘하고 계세요!"
                    self._play_coaching("GOOD")
                else:
                    feedback_msg = "충분합니다. 천천히 돌아오세요."
                    self._play_coaching("LIMIT")

        penalty_delta_pct = round(
            deviation_penalty(elbow_excess_deg, unit_penalty=0.8, max_penalty=16.0)
            + deviation_penalty(shoulder_excess_deg, unit_penalty=0.7, max_penalty=14.0),
            2,
        )
        recovery_delta_pct = recovery_bonus(
            posture_stable=penalty_delta_pct == 0.0,
            bonus=2.5,
        )
        self.accuracy_state = update_accuracy(
            self.accuracy_state,
            penalty_delta_pct=penalty_delta_pct,
            recovery_delta_pct=recovery_delta_pct,
        )
        deviation_flags = build_deviation_flags(
            opposite_limb_excess_deg=elbow_excess_deg,
            trunk_sway_excess_deg=shoulder_excess_deg,
        )

        return {
            "mode": "COACH",
            "exercise": self.exercise_name,
            "side": self.active_side,
            "angle": int(smooth_angle),
            "feedback": feedback_msg,
            "target_angle": self.limit_angle,
            "accuracy_pct": round(self.accuracy_state.accuracy_pct, 2),
            "min_accuracy_pct": round(self.accuracy_state.min_accuracy_pct, 2),
            "penalty_delta_pct": penalty_delta_pct,
            "recovery_delta_pct": recovery_delta_pct,
            "deviation_flags": deviation_flags,
        }
