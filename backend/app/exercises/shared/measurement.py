# 측정/코칭 프로세서: ROM 측정, 실시간 코칭.
# 카메라 영상에서 관절 좌표를 받아 관절 가동 범위(ROM)를 자동으로 측정하거나,
# 운동 중 자세를 실시간으로 분석해 음성 피드백을 제공하는 두 가지 프로세서를 정의한다.
# MeasurementProcessor: 정해진 순서대로 여러 부위를 측정하고 최대 각도를 기록한다.
# CoachingProcessor: 운동 중 팔꿈치 위치, 어깨 높이 등을 모니터링해 교정 안내를 제공한다.
import time
import cv2
import base64
import logging
import os
import numpy as np
from datetime import datetime
from typing import Dict, Any, List

from .base import BaseProcessor
from app.core.utils import AngleSmoother
from app.exercises.shared.posture import get_pose_angle
from app.core.audio import tts_engine
from app.services.score_service import (
    AccuracyState,
    build_deviation_flags,
    deviation_penalty,
    recovery_bonus,
    update_accuracy,
)

logger = logging.getLogger(__name__)


# 측정 stage명 → P2-9 rom 변수명 매핑 (팀 공용 계약).
# 변수명 단일 출처는 rom_defaults.DEFAULT_ROM 이며, 무릎은 신규 플로우 확정 후 추가한다.
STAGE_TO_ROM_KEY = {
    "LEFT_SHOULDER_ABDUCTION":  "shoulder_left_flexion_max",
    "RIGHT_SHOULDER_ABDUCTION": "shoulder_right_flexion_max",
}


# ----------------------------------------------------------------------------------------------------------------------------------------
# 기본 -> 측정 프로세서
# ----------------------------------------------------------------------------------------------------------------------------------------
# 정해진 운동 목록(schedule)을 순서대로 측정하는 프로세서.
# 준비(PREPARE) → 측정(MEASURE) → 유지(HOLD) 단계를 거치며 각 부위의 최대 각도를 기록하고,
# 측정이 끝나면 최대 각도와 가장 좋은 자세 이미지를 반환한다.
class MeasurementProcessor(BaseProcessor):
    # target_schedule: 측정할 운동 부위 이름 목록
    #                  (예: ["SHOULDER_ABDUCTION", "SIDE_LEG_RAISE", "KNEE_FLEXION"]).
    #                  지정하지 않으면 기본 3가지 부위를 순서대로 측정한다.
    def __init__(self, target_schedule: List[str] = None):
        super().__init__()
        self.check_tag = "check_shoulder"
        self.schedule = target_schedule if target_schedule else ["BILATERAL_SHOULDER_ABDUCTION", "LEFT_KNEE_FLEXION", "RIGHT_KNEE_FLEXION"]

        self.current_idx = 0
        self.finished = False

        if len(self.schedule) > 0:
            self.target_stage = self.schedule[self.current_idx]
        else:
            self.target_stage = None
            self.finished = True

        self.PREPARE_DURATION = 5.0
        self.MEASURE_DURATION = 8.0

        self._force_done = False  # signal_done() 호출 시 즉시 완료
        self.state = "PREPARE"
        self.start_time = time.time()
        self.max_angle = 0.0
        self._bilateral_left_max = 0.0
        self._bilateral_right_max = 0.0
        self.best_frame = None
        self.best_keypoints = None
        self.stage_max_results = {}
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

    # 프론트 오디오 스크립트 종료 시 호출: 현재까지의 최대값으로 즉시 완료 처리한다.
    def signal_done(self):
        if self.target_stage == "BILATERAL_SHOULDER_ABDUCTION":
            self.stage_max_results["LEFT_SHOULDER_ABDUCTION"] = self._bilateral_left_max
            self.stage_max_results["RIGHT_SHOULDER_ABDUCTION"] = self._bilateral_right_max
        elif self.target_stage and self.max_angle > 0:
            self.stage_max_results[self.target_stage] = self.max_angle
        self._force_done = True
        self.finished = True

    # 카메라에서 받은 관절 좌표(keypoints)와 프레임 이미지를 분석해 현재 측정 상태를 반환한다.
    # keypoints: YOLO 등에서 추출한 관절 좌표 딕셔너리.
    # frame: 현재 카메라 프레임 이미지 (최고 자세 캡처에 사용).
    # depth_frame / intrinsics: 시그니처 유지용 (3D 좌표는 motion_service에서 이미 주입됨).
    # 반환값: 현재 상태(status), 각도, 남은 시간, 피드백 메시지 등을 담은 딕셔너리.
    def process(self, keypoints: Dict, frame: np.ndarray, depth_frame=None, intrinsics=None, mp_features=None,) -> Dict[str, Any]:
        # 0. 종료 체크
        # ROM 파일 저장은 motion_service에서 중앙 처리한다(어깨·목·무릎·전체 공통, 세션당 1회).
        if self.finished:
            return {
                "status": "finished",
                "message": "모든 측정이 완료되었습니다.",
                "rom": self._build_rom(),
                "measured_at": datetime.now().isoformat(timespec="seconds"),
            }

        # 1. 각도 계산 + 전체 구간 최대값 추적 (phase 무관)
        if self.target_stage == "BILATERAL_SHOULDER_ABDUCTION" and keypoints:
            try:
                la = get_pose_angle("LEFT_SHOULDER_ABDUCTION", keypoints) or 0
                ra = get_pose_angle("RIGHT_SHOULDER_ABDUCTION", keypoints) or 0
                raw_angle = max(la, ra)
                if la > self._bilateral_left_max:
                    self._bilateral_left_max = la
                if ra > self._bilateral_right_max:
                    self._bilateral_right_max = ra
            except Exception as e:
                logger.warning("Measurement angle calc skipped: %s", e)
                la = ra = raw_angle = 0
        else:
            la = ra = 0
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

            if self.target_stage in ("KNEE_FLEXION", "LEFT_KNEE_FLEXION"):
                is_visible = any(i in keypoints for i in [11, 13, 15])
            elif self.target_stage == "RIGHT_KNEE_FLEXION":
                is_visible = any(i in keypoints for i in [12, 14, 16])
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
                self.best_keypoints = keypoints
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
        # 자동 완료 없음 — signal_done()이 올 때까지 최대값만 계속 갱신한다.
        elif self.state == "HOLD":
            pass

        return {
            "status": "measuring",
            "stage": self.target_stage,
            "angle": int(angle),
            "max_angle": int(self.max_angle),
            "progress": f"{self.current_idx + 1}/{len(self.schedule)}"
        }

    # 한 부위의 측정이 완료됐을 때 결과를 패키징해 반환하고 다음 부위로 넘어간다.
    # 반환값: 완료된 부위 이름, 최대 각도, 최고 자세 이미지(Base64)를 담은 딕셔너리.
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

        if self.target_stage == "BILATERAL_SHOULDER_ABDUCTION":
            self.stage_max_results["LEFT_SHOULDER_ABDUCTION"] = self._bilateral_left_max
            self.stage_max_results["RIGHT_SHOULDER_ABDUCTION"] = self._bilateral_right_max
        else:
            self.stage_max_results[self.target_stage] = self.max_angle
        symmetry = self._compute_bilateral_symmetry()

        result_packet = {
            "status": "stage_finished",
            "stage": self.target_stage,
            "max_angle": int(self.max_angle),
            "best_image": best_image_b64,
            "message": f"{self.target_stage} 측정 완료!"
        }
        if symmetry:
            result_packet["symmetry"] = symmetry

        self.next_stage()
        return result_packet

    # LEFT_/RIGHT_ 쌍이 모두 완료됐을 때 좌우 대칭 편차를 계산한다.
    def _compute_bilateral_symmetry(self):
        pairs = [
            ("LEFT_SHOULDER_ABDUCTION", "RIGHT_SHOULDER_ABDUCTION"),
            ("LEFT_KNEE_FLEXION", "RIGHT_KNEE_FLEXION"),
        ]
        for left_stage, right_stage in pairs:
            if left_stage in self.stage_max_results and right_stage in self.stage_max_results:
                left = self.stage_max_results[left_stage]
                right = self.stage_max_results[right_stage]
                if left > 0 and right > 0:
                    dev = abs(left - right) / max(left, right) * 100
                    return {
                        "left_max": int(left),
                        "right_max": int(right),
                        "deviation_pct": round(dev, 1),
                        "within_threshold": dev <= 8.0,
                    }
        return None

    # 측정된 stage별 최대 각도를 P2-9 rom 변수명으로 변환해 반환한다.
    # STAGE_TO_ROM_KEY에 없는 stage(예: 재설계 전 무릎)는 제외한다.
    def _build_rom(self) -> Dict[str, Any]:
        rom = {}
        for stage, angle in self.stage_max_results.items():
            key = STAGE_TO_ROM_KEY.get(stage)
            if key:
                rom[key] = int(angle)
        return rom

    # 다음 측정 부위로 전환하고 내부 상태를 초기화한다.
    # 모든 부위가 끝나면 finished를 True로 설정한다.
    def next_stage(self):
        """ 다음 운동으로 넘어가기 & 변수 초기화 """
        self.current_idx += 1
        if self.current_idx < len(self.schedule):
            self.target_stage = self.schedule[self.current_idx]
            self.state = "PREPARE"
            self.start_time = time.time()
            self.max_angle = 0.0
            self._bilateral_left_max = 0.0
            self._bilateral_right_max = 0.0
            self.best_frame = None
            self.best_keypoints = None
            self.played_audio = {key: False for key in self.tts_assets.keys()}
        else:
            self.finished = True

# -------------------------------------------------------------------------------------------------
# 기본 -> 코칭 프로세서
# -------------------------------------------------------------------------------------------------
# 지정된 운동을 수행하는 동안 자세를 실시간으로 분석하고 음성 피드백을 제공하는 프로세서.
# 팔꿈치 위치, 어깨 높이 등의 자세 이탈 여부를 감지해 교정 안내를 하며,
# 자세 정확도(accuracy_pct)를 지속적으로 추적한다.
class CoachingProcessor(BaseProcessor):
    # exercise_name: 코칭할 운동 이름 (예: 'SHOULDER_EXTERNAL_ROTATION').
    # limit_angle: 해당 운동의 목표 각도 (기본값 45도).
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

    # 음성 피드백을 재생한다. 마지막 재생 이후 feedback_interval초가 지나지 않으면 무시한다.
    # key: tts_assets 딕셔너리의 키 (예: "ELBOW_AWAY").
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

    # 카메라에서 받은 관절 좌표를 분석해 자세 피드백과 정확도를 반환한다.
    # keypoints: YOLO 등에서 추출한 관절 좌표 딕셔너리 (x_m, y_m, z는 motion_service에서 이미 주입됨).
    # frame: 현재 카메라 프레임 (이 프로세서에서는 직접 사용하지 않음).
    # depth_frame / intrinsics: 시그니처 유지용.
    # 반환값: 운동 각도, 피드백 메시지, 정확도 등을 담은 딕셔너리.
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


# ----------------------------------------------------------------------------------------------------------------------------------------
# 전체(전신) 통합 측정 프로세서
# ----------------------------------------------------------------------------------------------------------------------------------------
# 어깨·목·무릎 세 서브 프로세서를 매 프레임 동시 실행한다.
# 프론트 오디오 스크립트가 끝나면 DONE 신호 하나로 전부 완료 처리하고 ROM을 통합한다.
class FullBodyMeasurementProcessor(BaseProcessor):
    def __init__(self):
        # 지연 import로 순환 참조 방지
        from app.exercises.neck_rotation.measurement import NeckROMMeasurementProcessor
        from app.exercises.straight_leg_raise.measurement import KneeROMMeasurementProcessor
        self.check_tag = "check_full"
        self.shoulder_sub = MeasurementProcessor(target_schedule=["BILATERAL_SHOULDER_ABDUCTION"])
        self.neck_sub = NeckROMMeasurementProcessor()
        self.knee_sub = KneeROMMeasurementProcessor()
        self.rom: Dict[str, Any] = {}
        self.finished = False

    def signal_done(self):
        self._collect_and_finish()

    def set_phase(self, phase: str):
        _KNEE_PHASES = {"KNEE_LEFT_EXTEND", "KNEE_RIGHT_EXTEND", "KNEE_LEFT_RAISE", "KNEE_RIGHT_RAISE"}
        if phase == "DONE":
            self._collect_and_finish()
        elif phase in _KNEE_PHASES:
            self.knee_sub.set_phase(phase)

    def _collect_and_finish(self):
        """세 서브 프로세서를 모두 완료 처리하고 ROM을 수집한다."""
        self.shoulder_sub.signal_done()
        self.neck_sub.signal_done()
        self.knee_sub.set_phase("DONE")
        for sub in [self.shoulder_sub, self.neck_sub, self.knee_sub]:
            res = sub.process({}, None)
            if res and res.get("rom"):
                self.rom.update(res["rom"])
        self.finished = True

    def extract_mp_features(self, pts):
        """목·무릎 features를 한 번에 추출해 반환한다 (어깨는 keypoints 직접 사용)."""
        if not pts:
            return None
        neck_mp = self.neck_sub.extract_mp_features(pts)
        knee_mp = self.knee_sub.extract_mp_features(pts)
        if neck_mp is None and knee_mp is None:
            return None
        return {"neck": neck_mp, "knee": knee_mp}

    def _finished_packet(self) -> Dict[str, Any]:
        return {
            "mode": "MEASURE",
            "stage": "FULL_BODY",
            "status": "finished",
            "message": "전체 측정이 완료되었습니다.",
            "rom": self.rom,
            "measured_at": datetime.now().isoformat(timespec="seconds"),
        }

    def process(self, keypoints: Dict, frame: np.ndarray, depth_frame=None, intrinsics=None, mp_features=None) -> Dict[str, Any]:
        if self.finished:
            return self._finished_packet()

        # 세 서브 프로세서를 매 프레임 동시 실행
        combined = mp_features if isinstance(mp_features, dict) else {}
        neck_mp = combined.get("neck")
        knee_mp = combined.get("knee")

        self.shoulder_sub.process(keypoints, frame, depth_frame=depth_frame, intrinsics=intrinsics)
        self.neck_sub.process(keypoints, frame, mp_features=neck_mp)
        self.knee_sub.process(keypoints, frame, mp_features=knee_mp)

        return {"mode": "MEASURE", "stage": "FULL_BODY", "status": "measuring"}
