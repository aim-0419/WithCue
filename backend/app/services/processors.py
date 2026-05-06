import time
import cv2
import base64
import logging
import os
import csv
import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, Any, List

from app.core.utils import AngleSmoother
from app.services.rules.posture import get_pose_angle
from app.hardware.camera import camera_manager
from app.core.audio import tts_engine
from app.services.score_service import (
    AccuracyState,
    build_deviation_flags,
    deviation_penalty,
    recovery_bonus,
    update_accuracy,
)
import json

# Neck ROM 전용 로그 설정
NECK_ROM_LOG_DIR = "/home/aim0419/withcue_v1.0/backend/logs"
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

# 운동별 DTW 기준이 되는 feature import
from app.services.dtw_feature_extractor import (
    get_bird_dog_features_mp,
    get_shoulder_front_raise_left_features_mp,
    get_knee_raise_right_features_mp,
    flip_mediapipe_left_right,
    get_neck_rotation_features_mp,
)
from app.services.feedback.realtime_feedback_router import RealTimeFeedbackRouter
from app.services.feedback.session_feedback_summary import SessionFeedbackSummary, format_top3_text

logger = logging.getLogger(__name__)

DTW_FRAME_LOG_PATH = os.path.join(NECK_ROM_LOG_DIR, "dtw_frame_feedback_log.csv")


class DtwFrameCsvLogger:
    FIELDNAMES = [
        "logged_at",
        "session_id",
        "exercise_type",
        "frame_index",
        "mode",
        "status",
        "rep_count",
        "accuracy_pct",
        "similarity",
        "avg_similarity",
        "motion_similarity",
        "posture_similarity",
        "cost",
        "score",
        "final_score",
        "session_finished",
        "buffer_len",
        "phase",
        "main_error_feature",
        "feedback",
        "mp_features_json",
        "live_result_json",
        "compare_payload_json",
        "feedback_packet_json",
        "all_issues_json",
        "feature_errors_json",
        "session_summary_json",
        "payload_json",
    ]

    def __init__(self, exercise_type: str, path: str = DTW_FRAME_LOG_PATH):
        self.exercise_type = str(exercise_type)
        self.path = path
        self.session_id = (
            f"{self.exercise_type}_{time.strftime('%Y%m%d_%H%M%S')}_"
            f"{int((time.time() % 1) * 1000):03d}"
        )
        self.frame_index = 0
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        if not os.path.exists(self.path) or os.path.getsize(self.path) == 0:
            return
        try:
            with open(self.path, "r", encoding="utf-8-sig", newline="") as fp:
                reader = csv.reader(fp)
                header = next(reader, [])
        except OSError:
            return

        if header == self.FIELDNAMES:
            return

        backup_path = (
            f"{self.path}.bak_{time.strftime('%Y%m%d_%H%M%S')}"
        )
        os.replace(self.path, backup_path)

    def log(self, payload: Dict[str, Any]) -> None:
        self.frame_index += 1
        feature_errors = payload.get("feature_errors", {})
        feedback_packet = payload.get("feedback_packet", {}) or {}
        row = {
            "logged_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "session_id": self.session_id,
            "exercise_type": self.exercise_type,
            "frame_index": self.frame_index,
            "mode": payload.get("mode"),
            "status": payload.get("status"),
            "rep_count": payload.get("rep_count"),
            "accuracy_pct": payload.get("accuracy_pct"),
            "similarity": payload.get("similarity"),
            "avg_similarity": payload.get("avg_similarity"),
            "motion_similarity": payload.get("motion_similarity"),
            "posture_similarity": payload.get("posture_similarity"),
            "cost": payload.get("cost"),
            "score": payload.get("score"),
            "final_score": payload.get("final_score"),
            "session_finished": payload.get("session_finished"),
            "buffer_len": payload.get("buffer_len"),
            "phase": payload.get("phase"),
            "main_error_feature": payload.get("main_error_feature"),
            "feedback": payload.get("feedback"),
            "mp_features_json": json.dumps(payload.get("mp_features"), ensure_ascii=False) if payload.get("mp_features") is not None else "",
            "live_result_json": json.dumps(payload.get("live_result"), ensure_ascii=False) if payload.get("live_result") is not None else "",
            "compare_payload_json": json.dumps(payload.get("compare_payload"), ensure_ascii=False) if payload.get("compare_payload") is not None else "",
            "feedback_packet_json": json.dumps(feedback_packet, ensure_ascii=False) if feedback_packet else "",
            "all_issues_json": json.dumps(feedback_packet.get("all_issues"), ensure_ascii=False) if feedback_packet.get("all_issues") else "",
            "feature_errors_json": json.dumps(feature_errors, ensure_ascii=False) if feature_errors else "",
            "session_summary_json": json.dumps(payload.get("session_summary"), ensure_ascii=False) if payload.get("session_summary") is not None else "",
            "payload_json": json.dumps(payload, ensure_ascii=False),
        }
        file_exists = os.path.exists(self.path)
        needs_header = (not file_exists) or os.path.getsize(self.path) == 0
        with open(self.path, "a", newline="", encoding="utf-8-sig") as fp:
            writer = csv.DictWriter(fp, fieldnames=self.FIELDNAMES)
            if needs_header:
                writer.writeheader()
            writer.writerow(row)

class BaseProcessor(ABC):
    @abstractmethod
    def process(self, keypoints: Dict, frame: np.ndarray, depth_frame=None, intrinsics=None, mp_features=None) -> Dict[str, Any]:
        # [핵심] Measurement/Coaching 프로세서 공통 인터페이스
        pass

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
        
        keypoints =  camera_manager.update_keypoints_3d(keypoints, depth_frame, intrinsics)
   
            
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
            # 현재 각도가 지금까지의 최고 기록보다 높으면 -> 이미지와 각도를 갱신
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
            
        # === [상태 3] 유지 단계 (HOLD) - 새로 추가 ===
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
        
        # --- 🚀 [터미널 결과 리포트 출력] ---
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
        
        # --- 🚀 [터미널 결과 리포트 출력] ---
        
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
        
        # 기존 방식 유지 시 사용
        self.smoother = AngleSmoother(alpha=0.5)
        
        # 상태 관리를 위한 변수
        # [핵심] 실시간 코칭에서 과도한 음성 반복을 막기 위해 마지막 피드백 시각을 관리
        self.last_feeedback = None
        self.last_feedback_time = 0
        self.feedback_interval = 4.0
        # 초기 어깨 높이 저장을 위한 플래그
        self.init_shoulder_y = None
        
        # 현재 코칭 중인 팔 방향 ('Left' or 'Right')
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
        
        # 쿨타임 체크
        if curr - self.last_feedback_time < self.feedback_interval:
            return
        
        filename = self.tts_assets.get(key)
        if not filename:
            return
        
        # 실제 음성 재생
        tts_engine.play(filename)
        
        # 로그는 디버깅용으로 유지해도 좋음
        logger.info("Play coaching audio: key=%s file=%s", key, filename)
        
        self.last_feedback_time = curr
        
    def process(self, keypoints: Dict, frame: np.ndarray, depth_frame = None, intrinsics=None, mp_features=None) -> Dict[str, Any]:
        
        logger.debug("Coaching process called. keypoints=%s", len(keypoints) if keypoints else 0)
        # 코칭 모드는 이미지가 필요 없지만, 부모 클래스 규칙 때문에 인자 받음
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
            return { "mode": "COACH", "feedback": "데이터 오류 발생"}
                
        # 1. 3D 좌표 변환 (이미 되어있을 수 있음)
        keypoints = camera_manager.update_keypoints_3d(
            keypoints, 
            depth_frame, 
            intrinsics
        )
        
        # 2. 좌/우 자동 감지 로직 (Auto-Detect Side)
        # 무조건 5, 7만 보는 게 아니라, 데이터가 살아있는 쪽을 선택함
        sh, el = None, None
        
        # 오른쪽 (어깨6, 팔꿈치8) 데이터가 있으면 우선 선택
        if 6 in keypoints and 8 in keypoints:
            sh, el = 6, 8
            self.active_side = "Right"
            logger.debug("Detected right side (6, 8).")
        
        # 오른쪽이 없으면 왼쪽(어깨5, 팔꿈치7) 체크
        elif 5 in keypoints and 7 in keypoints:
            sh, el = 5, 7
            self.active_side = "Left"
            logger.debug("Detected left side (5, 7).")
            
        else:
            logger.warning("Side detection failed. keypoints=%s", list(keypoints.keys()))
            return { "mode": "COACH", "feedback": "상반신이 잘 보이게 서주세요." }
        
        # 3D 유효성 체크
        required_indices = [sh, el]
        
        for idx in required_indices:
            if (
                keypoints[idx].get('x_m') is None or
                keypoints[idx].get('y_m') is None
            ):
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
            
        # 3. 각도 계산
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
        
        # 계산된 각도와 방향 찍어보기
        logger.debug("[%s] angle=%s stage=%s", self.active_side, int(smooth_angle), self.exercise_name)
        
        feedback_msg = "자세 좋습니다!"
        elbow_excess_deg = 0.0
        shoulder_excess_deg = 0.0
        
        # 4. 운동별 상세 코칭 (어깨 외회전)
        if self.exercise_name == "SHOULDER_EXTERNAL_ROTATION":
            
            # (1) 초기 어깨 높이 잡기 (sh 변수 사용)
            if self.init_shoulder_y is None:
                self.init_shoulder_y = keypoints[sh]['y_m']
                
            # (2) 팔꿈치 벌어짐 체크 (sh, el 변수 사용)  
            elbow_dist = abs(keypoints[el]['x_m'] - keypoints[sh]['x_m'])
            elbow_excess_deg = max(0.0, (elbow_dist - 0.15) * 100.0)
            
            # (3) 승모근 상승 체크
            sh_rise = self.init_shoulder_y - keypoints[sh]['y_m']
            shoulder_excess_deg = max(0.0, (sh_rise - 0.05) * 200.0)
            
            # --- 피드백 로직 ---
            if elbow_dist > 0.15:
                feedback_msg = "팔꿈치를 붙여주세요!"
                self._play_coaching("ELBOW_AWAY")
                
            elif sh_rise > 0.05:
                feedback_msg = "어깨에 힘을 빼세요!"
                self._play_coaching("SHOULDER_DOWN")
                
            else:
                # 자세가 좋을 때 각도 피드백
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
# 부위별 측정 프로세서
# ----------------------------------------------------------------------------------------------------------------------------------------

# 목 부위
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
        return get_neck_rotation_features_mp(pts)
        
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
        
        # feature 없으면 리셋
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
                self.state,
                self.hold_count,
                neck_angle,
                trunk,
                tilt,
                shoulder,
            )
            return {
                "status": "invalid",
                "message": "몸통을 고정해주세요",
            }
        else:
            _neck_rom_logger.info(
                "[NECK_ROM] state=%s hold=%s neck=%.2f trunk=%.2f tilt=%.2f shoulder=%.2f valid=True",
                self.state,
                self.hold_count,
                neck_angle,
                trunk,
                tilt,
                shoulder,
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

            # 왼쪽 시작
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
            
            
            
            
            
            
# ----------------------------------------------------------------------------------------------------------------------------------------
# 운동별 코칭 프로세서
# 프레임마다 들어오는 feature를 모아서 → 1회 수행 감지 → DTW → 점수 반환
# ----------------------------------------------------------------------------------------------------------------------------------------

# ----------버드독 프로세서---------------------------------------------------------------
class BirdDogDTWProcessor(BaseProcessor):
    def __init__(self, dtw_engine, target_reps: int = 3):
        self.dtw_engine = dtw_engine # reference JSON + DTW 알고리즘 포함된 객체 -> compare() -> 점수도출
        self.buffer = [] # 프레임마다 feature 저장
        self.prev_signal = None # 이전 프레임의 움직임 값 저장
        self.state = "idle" # idel/up/down
        self.peak_count = 0 # 버드독 1회 -> 상승+하강
        self.rep_index = 0 # 몇회 카운트    
        self.last_live_similarity = None
        self.rep_score_sum = 0.0
        self.rep_score_count = 0
        self.rep_avg_similarity = None
        self.motion_started = False
        self.target_reps = int(target_reps)
        self.feedback_router = RealTimeFeedbackRouter()
        self.session_summary = SessionFeedbackSummary()
        self.exercise_type = "bird_dog"
        self.csv_logger = DtwFrameCsvLogger(self.exercise_type)
        self.session_finished = False
        self._last_obs_ts = time.time()
        
    def extract_mp_features(self, pts):
        return get_bird_dog_features_mp(pts)
    
    def _get_signal(self, feat): # 움직임 감지용
        right_arm = feat[2]
        left_leg = feat[3]
        left_arm = feat[4]
        right_leg = feat[5]
        return max(right_arm + left_leg, left_arm + right_leg) # 둘 중 하나가 올라가면 동작 발생 
    
    def process(self, keypoints, frame, depth_frame=None, intrinsics=None, mp_features=None):
        if self.session_finished:
            result = {
                "mode": "BIRD_DOG_DTW",
                "status": "session_finished",
                "rep_count": self.rep_index,
                "feedback": "세트가 종료되었습니다.",
                "accuracy_pct": self.last_live_similarity,
                "buffer_len": len(self.buffer),
            }
            self.csv_logger.log(result)
            return result
        logger.debug("[BIRD_DOG PROCESS] entered | mp_features=%s", mp_features)
        if mp_features is None:
            result = {
                "mode": "BIRD_DOG_DTW",
                "status": "waiting",
                "feedback": "자세를 인식 중입니다.",
                "rep_count": self.rep_index,
                "accuracy_pct": self.last_live_similarity,
                "buffer_len": len(self.buffer),
            }
            self.csv_logger.log(result)
            return result

        current = tuple(round(v, 3) for v in mp_features)
        prev = tuple(round(v, 3) for v in self.buffer[-1]) if self.buffer else None

        if current != prev:
            self.buffer.append(mp_features)

        # 실시간 similarity 계산
        live_result = self.dtw_engine.get_live_similarity(
            self.buffer,
            min_frames=12,
            live_window=30,
        )
        live_similarity = live_result["live_similarity"]
        if live_similarity is not None:
            self.last_live_similarity = live_similarity

        now_ts = time.time()
        dt_sec = max(0.0, now_ts - self._last_obs_ts)
        self._last_obs_ts = now_ts
        motion_a = float(mp_features[2] + mp_features[3])
        motion_b = float(mp_features[4] + mp_features[5])
        denom = max(abs(motion_a) + abs(motion_b), 1e-6)
        if live_similarity is not None:
            compare_payload = {
                "phase": live_result.get("phase", "unknown"),
                "motion_similarity": live_result.get("motion_similarity"),
                "posture_similarity": live_result.get("posture_similarity"),
                "feature_errors": live_result.get("feature_errors", {}),
                "main_error_feature": live_result.get("main_error_feature"),
                "ref_progress": live_result.get("ref_progress"),
                "pair_a_error": live_result.get("pair_a_error"),
                "pair_b_error": live_result.get("pair_b_error"),
                "movement_direction": live_result.get("movement_direction"),
            }
            feedback_packet = self.feedback_router.process(
                self.exercise_type, compare_payload, now_ts
            )
            self.session_summary.observe(
                self.exercise_type, feedback_packet["all_issues"], dt_sec
            )
        else:
            feedback_packet = {
                "exercise_type": self.exercise_type,
                "feedback": None,
                "issue": None,
                "all_issues": [],
            }
        instant_feedback = feedback_packet["feedback"] or "동작 분석 중입니다."

        signal = self._get_signal(mp_features)

        if self.prev_signal is None:
            self.prev_signal = signal
            result = {
                "mode": "BIRD_DOG_DTW",
                "status": "running",
                "rep_count": self.rep_index,
                "feedback": instant_feedback if instant_feedback else "버드독 동작을 수행해주세요.",
                "accuracy_pct": self.last_live_similarity,
                "similarity": self.last_live_similarity,
                "buffer_len": len(self.buffer),
                "mp_features": list(mp_features) if mp_features is not None else None,
                "live_result": live_result,
                "compare_payload": compare_payload if live_similarity is not None else None,
                "feedback_packet": feedback_packet,
                "motion_similarity": live_result.get("motion_similarity"),
                "posture_similarity": live_result.get("posture_similarity"),
                "phase": live_result.get("phase"),
                "main_error_feature": live_result.get("main_error_feature"),
                "feature_errors": live_result.get("feature_errors", {}),
            }
            self.csv_logger.log(result)
            return result

        if signal > self.prev_signal + 3:
            self.state = "up"
            self.motion_started = True
            logger.info(
                "[BIRD_DOG AVG] motion started | rep=%s signal=%.3f",
                self.rep_index + 1,
                signal,
            )

        if self.motion_started and live_similarity is not None:
            self.rep_score_sum += live_similarity
            self.rep_score_count += 1
            logger.info(
                "[BIRD_DOG AVG] accumulating | rep=%s frame_count=%s live_similarity=%.2f running_avg=%.2f",
                self.rep_index + 1,
                self.rep_score_count,
                live_similarity,
                self.rep_score_sum / self.rep_score_count,
            )

        if self.state == "up" and signal < self.prev_signal - 3:
            self.peak_count += 1
            self.state = "down"

        self.prev_signal = signal

        # 나중에 최종 정확도도 쓸 수 있게 rep 완료 로직은 남겨둠
        if self.peak_count >= 2 and len(self.buffer) > 15:
            compare_result = self.dtw_engine.compare(self.buffer)
            avg_similarity = None
            if self.rep_score_count > 0:
                avg_similarity = round(self.rep_score_sum / self.rep_score_count, 2)
                self.rep_avg_similarity = avg_similarity
                logger.info(
                    "[BIRD_DOG AVG] rep finished | rep=%s avg_similarity=%.2f sample_count=%s",
                    self.rep_index + 1,
                    self.rep_avg_similarity,
                    self.rep_score_count,
                )
            else:
                logger.warning(
                    "[BIRD_DOG AVG] rep finished without samples | rep=%s",
                    self.rep_index + 1,
                )

            result = {
                "mode": "BIRD_DOG_DTW",
                "status": "rep_finished",
                "rep_count": self.rep_index + 1,
                "score": compare_result["score"],
                "accuracy_pct": self.last_live_similarity,   # 화면용 실시간 similarity 유지
                "similarity": self.last_live_similarity,
                "avg_similarity": self.rep_avg_similarity,
                "final_score": compare_result["score"],      # 나중에 필요하면 사용
                "cost": compare_result["cost"],
                "feedback": f"{self.rep_index + 1}회 수행 완료",
                "buffer_len": len(self.buffer),
                "mp_features": list(mp_features) if mp_features is not None else None,
                "live_result": live_result,
                "compare_payload": compare_payload if live_similarity is not None else None,
                "feedback_packet": feedback_packet,
                "motion_similarity": live_result.get("motion_similarity"),
                "posture_similarity": live_result.get("posture_similarity"),
                "phase": live_result.get("phase"),
                "main_error_feature": live_result.get("main_error_feature"),
                "feature_errors": live_result.get("feature_errors", {}),
            }

            if (self.rep_index + 1) >= self.target_reps:
                final_summary = self.session_summary.finalize(top_k=3)
                result["session_finished"] = True
                result["session_summary"] = final_summary
                result["session_summary_lines"] = format_top3_text(final_summary)
                self.session_finished = True

            self.rep_index += 1
            self.buffer = []
            self.prev_signal = None
            self.state = "idle"
            self.peak_count = 0
            self.rep_score_sum = 0.0
            self.rep_score_count = 0
            self.motion_started = False
            self.csv_logger.log(result)
            return result

        result = {
            "mode": "BIRD_DOG_DTW",
            "status": "running",
            "rep_count": self.rep_index,
            "feedback": instant_feedback,
            "accuracy_pct": self.last_live_similarity,
            "similarity": self.last_live_similarity,
            "buffer_len": len(self.buffer),
            "mp_features": list(mp_features) if mp_features is not None else None,
            "live_result": live_result,
            "compare_payload": compare_payload if live_similarity is not None else None,
            "feedback_packet": feedback_packet,
            "motion_similarity": live_result.get("motion_similarity"),
            "posture_similarity": live_result.get("posture_similarity"),
            "phase": live_result.get("phase"),
            "main_error_feature": live_result.get("main_error_feature"),
            "feature_errors": live_result.get("feature_errors", {}),
        }
        self.csv_logger.log(result)
        return result

# ----------버드독DTW---------------------------------------------------------------
class BirdDogDTW:
    FEATURE_NAMES = (
        "trunk",
        "pelvic",
        "right_arm",
        "left_leg",
        "left_arm",
        "right_leg",
        "right_arm_h_err",
        "left_leg_h_err",
        "left_arm_h_err",
        "right_leg_h_err",
        "right_elbow_angle",
        "left_elbow_angle",
        "left_knee_angle",
        "right_knee_angle",
    )
    MOTION_INDEXES = (2, 3, 4, 5)
    POSTURE_INDEXES = (0, 1, 6, 7, 8, 9, 10, 11, 12, 13)

    def __init__(self, ref_path: str):
        self.ref_seq = self._load_reference(ref_path)
        self.feat_min, self.feat_max = self._get_minmax(self.ref_seq)
        self.ref_norm = self._normalize(self.ref_seq)
        self.ref_signal = self._motion_signal(self.ref_seq)

    def _load_reference(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return np.array(data["sequence"], dtype=np.float32)

    def _get_minmax(self, seq: np.ndarray):
        return seq.min(axis=0), seq.max(axis=0)

    def _normalize(self, seq: np.ndarray):
        denom = np.maximum(self.feat_max - self.feat_min, 1e-6)
        return (seq - self.feat_min) / denom

    def _frame_error_vector(self, a: np.ndarray, b: np.ndarray):
        weights = np.array([
            0.8, 0.8,
            1.3, 1.3, 1.3, 1.3,
            1.1, 1.1, 1.1, 1.1,
            1.3, 1.3, 1.3, 1.3,
        ], dtype=np.float32)
        return np.abs(a - b) * weights

    def _frame_dist(self, a: np.ndarray, b: np.ndarray):
        return float(np.linalg.norm(self._frame_error_vector(a, b)))

    def _motion_signal(self, seq: np.ndarray):
        if len(seq) == 0:
            return np.array([], dtype=np.float32)
        return np.maximum(seq[:, 2] + seq[:, 3], seq[:, 4] + seq[:, 5])

    def _estimate_phase(self, user_seq: np.ndarray):
        signal = self._motion_signal(user_seq)
        if len(signal) == 0:
            return "unknown"
        current = float(signal[-1])
        sig_min = float(np.min(signal))
        sig_max = float(np.max(signal))
        span = max(sig_max - sig_min, 1e-6)
        progress = float(np.clip((current - sig_min) / span, 0.0, 1.0))
        if len(signal) >= 4:
            slope = float(np.mean(np.diff(signal[-4:])))
        elif len(signal) >= 2:
            slope = float(signal[-1] - signal[0]) / max(len(signal) - 1, 1)
        else:
            slope = 0.0

        active_a = float(user_seq[-1, 2] + user_seq[-1, 3])
        active_b = float(user_seq[-1, 4] + user_seq[-1, 5])
        phase = "transition"
        if progress >= 0.82:
            phase = "peak"
        elif progress <= 0.20 and slope <= 0.5:
            phase = "ready"
        elif slope >= 0.75:
            phase = "raising"
        elif slope <= -0.75:
            phase = "lowering"

        if abs(active_a - active_b) <= 6.0:
            direction = "balanced"
        else:
            direction = "pair_a" if active_a > active_b else "pair_b"
        return phase, direction

    def _phase_penalty(self, phase: str, ref_progress: float):
        if phase == "peak":
            return 0.0 if ref_progress >= 0.70 else 0.12
        if phase == "raising":
            return 0.18 if ref_progress > 0.90 else 0.0
        if phase == "lowering":
            return 0.12 if ref_progress < 0.12 or ref_progress > 0.95 else 0.0
        if phase == "ready":
            return 0.08 if ref_progress > 0.30 else 0.0
        return 0.0

    def _dtw(self, seq1: np.ndarray, seq2: np.ndarray, band_ratio: float = 0.3):
        n, m = len(seq1), len(seq2)
        dp = np.full((n + 1, m + 1), np.inf, dtype=np.float32)
        dp[0, 0] = 0.0
        band = max(4, int(max(n, m) * band_ratio))

        for i in range(1, n + 1):
            j_start = max(1, i - band)
            j_end = min(m, i + band)
            for j in range(j_start, j_end + 1):
                cost = self._frame_dist(seq1[i - 1], seq2[j - 1])
                dp[i, j] = cost + min(
                    dp[i - 1, j],
                    dp[i, j - 1],
                    dp[i - 1, j - 1],
                )

        i, j = n, m
        if not np.isfinite(dp[i, j]):
            return None
        path = []
        path_len = 0
        while i > 0 and j > 0:
            path_len += 1
            path.append((i - 1, j - 1))
            candidates = [
                (dp[i - 1, j], i - 1, j),
                (dp[i, j - 1], i, j - 1),
                (dp[i - 1, j - 1], i - 1, j - 1),
            ]
            _, i, j = min(candidates, key=lambda x: x[0])

        path.reverse()
        path_len = max(path_len, 1)
        total_cost = float(dp[n, m])
        norm_cost = total_cost / path_len
        return {
            "total_cost": total_cost,
            "norm_cost": norm_cost,
            "path": path,
        }

    def _flip_left_right(self, seq: np.ndarray):
        flipped = seq.copy()

        # motion
        flipped[:, 2], flipped[:, 4] = seq[:, 4], seq[:, 2]
        flipped[:, 3], flipped[:, 5] = seq[:, 5], seq[:, 3]

        # horizontal
        flipped[:, 6], flipped[:, 8] = seq[:, 8], seq[:, 6]
        flipped[:, 7], flipped[:, 9] = seq[:, 9], seq[:, 7]

        # joint
        flipped[:, 10], flipped[:, 11] = seq[:, 11], seq[:, 10]
        flipped[:, 12], flipped[:, 13] = seq[:, 13], seq[:, 12]

        return flipped

    def _compute_path_metrics(self, ref_seq: np.ndarray, user_seq: np.ndarray, path):
        feature_sums = np.zeros(len(self.FEATURE_NAMES), dtype=np.float32)
        motion_sum = 0.0
        posture_sum = 0.0
        for ref_idx, user_idx in path:
            err_vec = self._frame_error_vector(ref_seq[ref_idx], user_seq[user_idx])
            feature_sums += err_vec
            motion_sum += float(np.mean(err_vec[list(self.MOTION_INDEXES)]))
            posture_sum += float(np.mean(err_vec[list(self.POSTURE_INDEXES)]))

        steps = max(len(path), 1)
        feature_mean = feature_sums / steps
        feature_errors = {
            name: float(feature_mean[idx])
            for idx, name in enumerate(self.FEATURE_NAMES)
        }
        candidate_indexes = (0, 1, 6, 7, 8, 9, 10, 11, 12, 13)
        main_idx = max(candidate_indexes, key=lambda idx: feature_errors[self.FEATURE_NAMES[idx]])
        local_ref_idx = path[-1][0] if path else 0
        local_ref_progress = float(local_ref_idx / max(len(ref_seq) - 1, 1))
        pair_a_error = float(np.mean([feature_errors["right_arm"], feature_errors["left_leg"]]))
        pair_b_error = float(np.mean([feature_errors["left_arm"], feature_errors["right_leg"]]))
        return {
            "feature_errors": feature_errors,
            "motion_cost": float(motion_sum / steps),
            "posture_cost": float(posture_sum / steps),
            "main_error_feature": self.FEATURE_NAMES[main_idx],
            "local_ref_progress": local_ref_progress,
            "pair_a_error": pair_a_error,
            "pair_b_error": pair_b_error,
        }

    def _find_best_subsequence(self, user_seq: np.ndarray):
        user_len = len(user_seq)
        ref_len = len(self.ref_norm)
        if user_len == 0 or ref_len == 0:
            return None
        min_len = max(10, user_len - 8)
        max_len = min(ref_len, user_len + 8)
        phase, direction = self._estimate_phase(user_seq)
        best = None
        for direction_used, ref_raw in (
            ("original", self.ref_seq),
            ("flipped", self._flip_left_right(self.ref_seq)),
        ):
            ref_norm = self._normalize(ref_raw)
            for cand_len in range(min_len, max_len + 1):
                for start in range(0, ref_len - cand_len + 1):
                    end = start + cand_len
                    ref_slice = ref_norm[start:end]
                    dtw_result = self._dtw(ref_slice, user_seq)
                    if dtw_result is None:
                        continue
                    metrics = self._compute_path_metrics(ref_slice, user_seq, dtw_result["path"])
                    penalized_cost = dtw_result["norm_cost"] + self._phase_penalty(phase, metrics["local_ref_progress"])
                    global_ref_idx = start + (dtw_result["path"][-1][0] if dtw_result["path"] else 0)
                    candidate = {
                        "phase": phase,
                        "direction": direction,
                        "direction_used": direction_used,
                        "start": start,
                        "end": end,
                        "norm_cost": dtw_result["norm_cost"],
                        "total_cost": dtw_result["total_cost"],
                        "penalized_cost": penalized_cost,
                        "path": dtw_result["path"],
                        "ref_progress": float(global_ref_idx / max(ref_len - 1, 1)),
                        **metrics,
                    }
                    if best is None or candidate["penalized_cost"] < best["penalized_cost"]:
                        best = candidate
        return best

    def get_live_similarity(self, partial_user_seq, min_frames: int = 12, live_window: int = 30):
        user_seq = np.array(partial_user_seq, dtype=np.float32)

        if len(user_seq) < min_frames:
            return {
                "live_similarity": None,
                "cost": None,
                "direction_used": None,
                "motion_similarity": None,
                "posture_similarity": None,
                "phase": "unknown",
                "feature_errors": {},
                "main_error_feature": None,
                "ref_progress": None,
            }

        live_seq = user_seq[-live_window:] if len(user_seq) > live_window else user_seq
        user = self._normalize(live_seq)
        best = self._find_best_subsequence(user)
        if best is None:
            return {
                "live_similarity": None,
                "cost": None,
                "direction_used": None,
                "motion_similarity": None,
                "posture_similarity": None,
                "phase": "unknown",
                "feature_errors": {},
                "main_error_feature": None,
                "ref_progress": None,
            }

        motion_similarity = max(0, min(100, round(100 - 12.0 * best["motion_cost"], 2)))
        posture_similarity = max(0, min(100, round(100 - 14.0 * best["posture_cost"], 2)))
        live_similarity = round((motion_similarity * 0.5) + (posture_similarity * 0.5), 2)

        return {
            "live_similarity": live_similarity,
            "cost": float(best["norm_cost"]),
            "direction_used": best["direction_used"],
            "motion_similarity": motion_similarity,
            "posture_similarity": posture_similarity,
            "phase": best["phase"],
            "feature_errors": best["feature_errors"],
            "main_error_feature": best["main_error_feature"],
            "ref_progress": best["ref_progress"],
            "pair_a_error": best["pair_a_error"],
            "pair_b_error": best["pair_b_error"],
            "movement_direction": best["direction"],
        }

    # 나중에 최종 정확도용으로 남겨둘 compare
    def compare(self, user_seq):
        user_seq = np.array(user_seq, dtype=np.float32)
        user = self._normalize(user_seq)
        best = self._find_best_subsequence(user)
        if best is None:
            return {"score": 0, "cost": None}
        motion_similarity = max(0, min(100, round(100 - 12.0 * best["motion_cost"], 2)))
        posture_similarity = max(0, min(100, round(100 - 14.0 * best["posture_cost"], 2)))
        score = round((motion_similarity * 0.5) + (posture_similarity * 0.5), 2)

        return {
            "score": score,
            "cost": float(best["norm_cost"]),
            "motion_similarity": motion_similarity,
            "posture_similarity": posture_similarity,
            "phase": best["phase"],
            "feature_errors": best["feature_errors"],
            "main_error_feature": best["main_error_feature"],
            "ref_progress": best["ref_progress"],
            "pair_a_error": best["pair_a_error"],
            "pair_b_error": best["pair_b_error"],
        }
        
# ----------어깨거상운동(왼쪽)DTWProcessor---------------------------------------------------------------
from app.services.dtw_feature_extractor import get_shoulder_front_raise_left_features_mp
class ShoulderFrontRaiseLeftDTWProcessor(BaseProcessor):
    def __init__(self, dtw_engine, mirror_input: bool = False, target_reps: int = 3):
        self.dtw_engine = dtw_engine
        self.buffer = []
        self.last_live_similarity = None
        self.mirror_input = mirror_input   # 오른팔이면 True
        self.rep_count = 0
        self.rep_state = "down"
        self.rep_peak_angle = 0.0
        self.raise_threshold = 110.0
        self.down_threshold = 90.0
        self.min_peak_angle = 110.0
        self.target_reps = int(target_reps)
        self.feedback_router = RealTimeFeedbackRouter()
        self.session_summary = SessionFeedbackSummary()
        self.exercise_type = "shoulder_front_raise"
        self.csv_logger = DtwFrameCsvLogger(self.exercise_type)
        self.session_finished = False
        self._last_obs_ts = time.time()

    def extract_mp_features(self, pts):
        # 오른팔도 mirror_input=True로 frame을 뒤집어서
        # 왼팔 feature extractor를 그대로 재사용
        return get_shoulder_front_raise_left_features_mp(pts)

    def process(self, keypoints, frame, depth_frame=None, intrinsics=None, mp_features=None):
        if self.session_finished:
            result = {
                "mode": "SHOULDER_FRONT_RAISE_DTW",
                "status": "session_finished",
                "feedback": "세트가 종료되었습니다.",
                "similarity": self.last_live_similarity,
                "rep_count": self.rep_count,
                "buffer_len": len(self.buffer),
            }
            self.csv_logger.log(result)
            return result
        if mp_features is None:
            result = {
                "mode": "SHOULDER_FRONT_RAISE_DTW",
                "status": "waiting",
                "feedback": "자세를 인식 중입니다.",
                "similarity": self.last_live_similarity,
                "rep_count": self.rep_count,
                "buffer_len": len(self.buffer),
            }
            self.csv_logger.log(result)
            return result

        current = tuple(round(v, 3) for v in mp_features)
        prev = tuple(round(v, 3) for v in self.buffer[-1]) if self.buffer else None

        if current != prev:
            self.buffer.append(mp_features)

        live_result = self.dtw_engine.get_live_similarity(
            self.buffer,
            min_frames=10,
            live_window=30,
        )

        live_similarity = live_result["live_similarity"]
        if live_similarity is not None:
            self.last_live_similarity = live_similarity

        now_ts = time.time()
        dt_sec = max(0.0, now_ts - self._last_obs_ts)
        self._last_obs_ts = now_ts
        compare_payload = {
            "phase": live_result.get("phase", "unknown"),
            "motion_similarity": live_result.get("motion_similarity"),
            "posture_similarity": live_result.get("posture_similarity"),
            "feature_errors": live_result.get("feature_errors", {}),
            "main_error_feature": live_result.get("main_error_feature"),
            "ref_progress": live_result.get("ref_progress"),
        }
        feedback_packet = self.feedback_router.process(self.exercise_type, compare_payload, now_ts)
        self.session_summary.observe(self.exercise_type, feedback_packet["all_issues"], dt_sec)
        instant_feedback = feedback_packet["feedback"] or "동작 분석 중입니다."

        left_arm_raise = float(mp_features[2])
        rep_just_finished = False
        if self.rep_state == "down" and left_arm_raise >= self.raise_threshold:
            self.rep_state = "up"
            self.rep_peak_angle = left_arm_raise
        elif self.rep_state == "up":
            if left_arm_raise > self.rep_peak_angle:
                self.rep_peak_angle = left_arm_raise
            if left_arm_raise <= self.down_threshold:
                if self.rep_peak_angle >= self.min_peak_angle:
                    self.rep_count += 1
                    rep_just_finished = True
                self.rep_state = "down"
                self.rep_peak_angle = 0.0

        result = {
            "mode": "SHOULDER_FRONT_RAISE_DTW",
            "status": "rep_finished" if rep_just_finished else "running",
            "feedback": f"{self.rep_count}회 수행 완료" if rep_just_finished else instant_feedback,
            "similarity": self.last_live_similarity,
            "cost": live_result["cost"],
            "rep_count": self.rep_count,
            "buffer_len": len(self.buffer),
            "mp_features": list(mp_features) if mp_features is not None else None,
            "live_result": live_result,
            "compare_payload": compare_payload,
            "feedback_packet": feedback_packet,
            "motion_similarity": live_result.get("motion_similarity"),
            "posture_similarity": live_result.get("posture_similarity"),
            "phase": live_result.get("phase"),
            "main_error_feature": live_result.get("main_error_feature"),
            "feature_errors": live_result.get("feature_errors", {}),
        }
        if rep_just_finished and self.rep_count >= self.target_reps:
            final_summary = self.session_summary.finalize(top_k=3)
            result["session_finished"] = True
            result["session_summary"] = final_summary
            result["session_summary_lines"] = format_top3_text(final_summary)
            self.session_finished = True
        self.csv_logger.log(result)
        return result

        
# ---------- 어깨거상운동(왼쪽) DTW -----------------------------------
class ShoulderFrontRaiseLeftDTW:
    FEATURE_NAMES = (
        "trunk",
        "shoulder_rise",
        "arm_raise",
        "elbow_angle",
        "arm_horizontal_error",
        "support_dist",
    )
    MOTION_INDEXES = (2, 4, 5)
    POSTURE_INDEXES = (0, 1, 3)

    def __init__(self, ref_path: str):
        self.ref_seq = self._load_reference(ref_path)
        self.feat_min, self.feat_max = self._get_minmax(self.ref_seq)
        self.ref_norm = self._normalize(self.ref_seq)

    def _load_reference(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return np.array(data["sequence"], dtype=np.float32)

    def _get_minmax(self, seq: np.ndarray):
        return seq.min(axis=0), seq.max(axis=0)

    def _normalize(self, seq: np.ndarray):
        denom = np.maximum(self.feat_max - self.feat_min, 1e-6)
        return (seq - self.feat_min) / denom

    def _frame_error_vector(self, a: np.ndarray, b: np.ndarray):
        weights = np.array([
            1.2,
            1.5,
            1.8,
            1.2,
            1.4,
            1.8,
        ], dtype=np.float32)
        err = np.abs(a - b) * weights
        err[5] *= 1.8
        return err

    def _frame_dist(self, a: np.ndarray, b: np.ndarray):
        return float(np.linalg.norm(self._frame_error_vector(a, b)))

    def _estimate_phase(self, user_seq: np.ndarray):
        if len(user_seq) == 0:
            return "unknown"
        raise_vals = user_seq[:, 2]
        current = float(raise_vals[-1])
        vmin = float(np.min(raise_vals))
        vmax = float(np.max(raise_vals))
        progress = float(np.clip((current - vmin) / max(vmax - vmin, 1e-6), 0.0, 1.0))
        if len(raise_vals) >= 4:
            slope = float(np.mean(np.diff(raise_vals[-4:])))
        elif len(raise_vals) >= 2:
            slope = float(raise_vals[-1] - raise_vals[0]) / max(len(raise_vals) - 1, 1)
        else:
            slope = 0.0

        if progress >= 0.84:
            return "peak"
        if progress <= 0.18 and slope <= 0.5:
            return "ready"
        if slope >= 1.0:
            return "raising"
        if slope <= -1.0:
            return "lowering"
        return "transition"

    def _phase_penalty(self, phase: str, ref_progress: float):
        if phase == "peak":
            return 0.0 if ref_progress >= 0.72 else 0.15
        if phase == "raising":
            return 0.18 if ref_progress > 0.90 else 0.0
        if phase == "lowering":
            return 0.12 if ref_progress < 0.15 or ref_progress > 0.92 else 0.0
        if phase == "ready":
            return 0.08 if ref_progress > 0.28 else 0.0
        return 0.0

    def _dtw(self, seq1: np.ndarray, seq2: np.ndarray, band_ratio: float = 0.3):
        n, m = len(seq1), len(seq2)
        dp = np.full((n + 1, m + 1), np.inf, dtype=np.float32)
        dp[0, 0] = 0.0
        band = max(3, int(max(n, m) * band_ratio))

        for i in range(1, n + 1):
            j_start = max(1, i - band)
            j_end = min(m, i + band)
            for j in range(j_start, j_end + 1):
                cost = self._frame_dist(seq1[i - 1], seq2[j - 1])
                dp[i, j] = cost + min(
                    dp[i - 1, j],
                    dp[i, j - 1],
                    dp[i - 1, j - 1],
                )

        i, j = n, m
        if not np.isfinite(dp[i, j]):
            return None
        path = []
        path_len = 0
        while i > 0 and j > 0:
            path_len += 1
            path.append((i - 1, j - 1))
            candidates = [
                (dp[i - 1, j], i - 1, j),
                (dp[i, j - 1], i, j - 1),
                (dp[i - 1, j - 1], i - 1, j - 1),
            ]
            _, i, j = min(candidates, key=lambda x: x[0])

        path.reverse()
        path_len = max(path_len, 1)
        total_cost = float(dp[n, m])
        norm_cost = total_cost / path_len
        return {
            "total_cost": total_cost,
            "norm_cost": norm_cost,
            "path": path,
        }

    def _compute_path_metrics(self, ref_seq: np.ndarray, user_seq: np.ndarray, path):
        feature_sums = np.zeros(len(self.FEATURE_NAMES), dtype=np.float32)
        motion_sum = 0.0
        posture_sum = 0.0
        for ref_idx, user_idx in path:
            err_vec = self._frame_error_vector(ref_seq[ref_idx], user_seq[user_idx])
            feature_sums += err_vec
            motion_sum += float(np.mean(err_vec[list(self.MOTION_INDEXES)]))
            posture_sum += float(np.mean(err_vec[list(self.POSTURE_INDEXES)]))

        steps = max(len(path), 1)
        feature_mean = feature_sums / steps
        feature_errors = {
            name: float(feature_mean[idx])
            for idx, name in enumerate(self.FEATURE_NAMES)
        }
        main_idx = max(self.POSTURE_INDEXES, key=lambda idx: feature_errors[self.FEATURE_NAMES[idx]])
        local_ref_idx = path[-1][0] if path else 0
        local_ref_progress = float(local_ref_idx / max(len(ref_seq) - 1, 1))
        return {
            "feature_errors": feature_errors,
            "motion_cost": float(motion_sum / steps),
            "posture_cost": float(posture_sum / steps),
            "main_error_feature": self.FEATURE_NAMES[main_idx],
            "local_ref_progress": local_ref_progress,
        }

    def _find_best_subsequence(self, user_seq: np.ndarray):
        user_len = len(user_seq)
        ref_len = len(self.ref_norm)
        if user_len == 0 or ref_len == 0:
            return None
        min_len = max(8, user_len - 6)
        max_len = min(ref_len, user_len + 6)
        phase = self._estimate_phase(user_seq)
        best = None
        for cand_len in range(min_len, max_len + 1):
            for start in range(0, ref_len - cand_len + 1):
                end = start + cand_len
                ref_slice = self.ref_norm[start:end]
                dtw_result = self._dtw(ref_slice, user_seq)
                if dtw_result is None:
                    continue
                metrics = self._compute_path_metrics(ref_slice, user_seq, dtw_result["path"])
                penalized_cost = dtw_result["norm_cost"] + self._phase_penalty(phase, metrics["local_ref_progress"])
                global_ref_idx = start + (dtw_result["path"][-1][0] if dtw_result["path"] else 0)
                candidate = {
                    "phase": phase,
                    "start": start,
                    "end": end,
                    "norm_cost": dtw_result["norm_cost"],
                    "total_cost": dtw_result["total_cost"],
                    "penalized_cost": penalized_cost,
                    "ref_progress": float(global_ref_idx / max(ref_len - 1, 1)),
                    **metrics,
                }
                if best is None or candidate["penalized_cost"] < best["penalized_cost"]:
                    best = candidate
        return best

    def get_live_similarity(self, partial_user_seq, min_frames: int = 10, live_window: int = 30):
        user_seq = np.array(partial_user_seq, dtype=np.float32)

        if len(user_seq) < min_frames:
            return {
                "live_similarity": None,
                "cost": None,
                "motion_similarity": None,
                "posture_similarity": None,
                "phase": "unknown",
                "feature_errors": {},
                "main_error_feature": None,
                "ref_progress": None,
            }

        live_seq = user_seq[-live_window:] if len(user_seq) > live_window else user_seq
        user = self._normalize(live_seq)
        best = self._find_best_subsequence(user)
        if best is None:
            return {
                "live_similarity": None,
                "cost": None,
                "motion_similarity": None,
                "posture_similarity": None,
                "phase": self._estimate_phase(live_seq),
                "feature_errors": {},
                "main_error_feature": None,
                "ref_progress": None,
            }

        motion_similarity = max(0, min(100, round(100 - 14.0 * best["motion_cost"], 2)))
        posture_similarity = max(0, min(100, round(100 - 18.0 * best["posture_cost"], 2)))
        live_similarity = round((motion_similarity * 0.5) + (posture_similarity * 0.5), 2)

        return {
            "live_similarity": live_similarity,
            "cost": float(best["norm_cost"]),
            "motion_similarity": motion_similarity,
            "posture_similarity": posture_similarity,
            "phase": best["phase"],
            "feature_errors": best["feature_errors"],
            "main_error_feature": best["main_error_feature"],
            "ref_progress": best["ref_progress"],
        }

    def compare(self, user_seq):
        user_seq = np.array(user_seq, dtype=np.float32)
        user = self._normalize(user_seq)
        best = self._find_best_subsequence(user)
        if best is None:
            return {"score": 0, "cost": None}
        motion_similarity = max(0, min(100, round(100 - 14.0 * best["motion_cost"], 2)))
        posture_similarity = max(0, min(100, round(100 - 18.0 * best["posture_cost"], 2)))
        score = round((motion_similarity * 0.5) + (posture_similarity * 0.5), 2)
        return {
            "score": score,
            "cost": float(best["norm_cost"]),
            "motion_similarity": motion_similarity,
            "posture_similarity": posture_similarity,
            "phase": best["phase"],
            "feature_errors": best["feature_errors"],
            "main_error_feature": best["main_error_feature"],
            "ref_progress": best["ref_progress"],
        }

# ----------무릎운동(오른쪽)DTWProcessor---------------------------------------------------------------
class KneeRaiseRightDTWProcessor(BaseProcessor):
    def __init__(self, dtw_engine, use_left_flip: bool = False, target_reps: int = 3):
        self.dtw_engine = dtw_engine
        self.buffer = []
        self.last_live_similarity = None
        self.use_left_flip = use_left_flip
        self.rep_count = 0
        self.rep_state = "down"
        self.rep_peak_flexion = 180.0
        self.raise_threshold = 150.0
        self.down_threshold = 160.0
        self.min_peak_flexion = 150.0
        self.target_reps = int(target_reps)
        self.feedback_router = RealTimeFeedbackRouter()
        self.session_summary = SessionFeedbackSummary()
        self.exercise_type = "knee_raise_right"
        self.csv_logger = DtwFrameCsvLogger(self.exercise_type)
        self.session_finished = False
        self._last_obs_ts = time.time()

    def extract_mp_features(self, pts):
        if self.use_left_flip:
            pts = flip_mediapipe_left_right(pts)
        return get_knee_raise_right_features_mp(pts)

    def process(self, keypoints, frame, depth_frame=None, intrinsics=None, mp_features=None):
        if self.session_finished:
            result = {
                "mode": "KNEE_RAISE_DTW",
                "status": "session_finished",
                "feedback": "세트가 종료되었습니다.",
                "similarity": self.last_live_similarity,
                "accuracy_pct": self.last_live_similarity,
                "rep_count": self.rep_count,
                "buffer_len": len(self.buffer),
            }
            self.csv_logger.log(result)
            return result
        if mp_features is None:
            result = {
                "mode": "KNEE_RAISE_DTW",
                "status": "waiting",
                "feedback": "자세를 인식 중입니다.",
                "similarity": self.last_live_similarity,
                "accuracy_pct": self.last_live_similarity,
                "rep_count": self.rep_count,
                "buffer_len": len(self.buffer),
            }
            self.csv_logger.log(result)
            return result

        current = tuple(round(v, 3) for v in mp_features)
        prev = tuple(round(v, 3) for v in self.buffer[-1]) if self.buffer else None

        if current != prev:
            self.buffer.append(mp_features)

        live_result = self.dtw_engine.get_live_similarity(
            self.buffer,
            min_frames=10,
            live_window=30,
        )

        live_similarity = live_result["live_similarity"]
        if live_similarity is not None:
            self.last_live_similarity = live_similarity

        now_ts = time.time()
        dt_sec = max(0.0, now_ts - self._last_obs_ts)
        self._last_obs_ts = now_ts
        compare_payload = {
            "phase": live_result.get("phase", "unknown"),
            "motion_similarity": live_result.get("motion_similarity"),
            "posture_similarity": live_result.get("posture_similarity"),
            "feature_errors": live_result.get("feature_errors", {}),
            "main_error_feature": live_result.get("main_error_feature"),
            "ref_progress": live_result.get("ref_progress"),
        }
        feedback_packet = self.feedback_router.process(self.exercise_type, compare_payload, now_ts)
        self.session_summary.observe(self.exercise_type, feedback_packet["all_issues"], dt_sec)
        instant_feedback = feedback_packet["feedback"] or "동작 분석 중입니다."

        hip_flexion = float(mp_features[2])
        rep_just_finished = False
        if self.rep_state == "down" and hip_flexion <= self.raise_threshold:
            self.rep_state = "up"
            self.rep_peak_flexion = hip_flexion
        elif self.rep_state == "up":
            if hip_flexion < self.rep_peak_flexion:
                self.rep_peak_flexion = hip_flexion
            if hip_flexion >= self.down_threshold:
                if self.rep_peak_flexion <= self.min_peak_flexion:
                    self.rep_count += 1
                    rep_just_finished = True
                self.rep_state = "down"
                self.rep_peak_flexion = 180.0

        result = {
            "mode": "KNEE_RAISE_DTW",
            "status": "rep_finished" if rep_just_finished else "running",
            "feedback": f"{self.rep_count}회 수행 완료" if rep_just_finished else instant_feedback,
            "similarity": self.last_live_similarity,
            "accuracy_pct": self.last_live_similarity,
            "cost": live_result["cost"],
            "motion_similarity": live_result.get("motion_similarity"),
            "posture_similarity": live_result.get("posture_similarity"),
            "phase": live_result.get("phase"),
            "rep_count": self.rep_count,
            "main_error_feature": live_result.get("main_error_feature"),
            "feature_errors": live_result.get("feature_errors", {}),
            "buffer_len": len(self.buffer),
            "mp_features": list(mp_features) if mp_features is not None else None,
            "live_result": live_result,
            "compare_payload": compare_payload,
            "feedback_packet": feedback_packet,
        }
        if rep_just_finished and self.rep_count >= self.target_reps:
            final_summary = self.session_summary.finalize(top_k=3)
            result["session_finished"] = True
            result["session_summary"] = final_summary
            result["session_summary_lines"] = format_top3_text(final_summary)
            self.session_finished = True
        self.csv_logger.log(result)
        return result
        
# ----------무릎운동(오른쪽)DTW -----------------------------------
class KneeRaiseRightDTW:
    FEATURE_NAMES = (
        "trunk",
        "pelvic",
        "hip_flexion",
        "knee_angle",
        "ankle_height",
    )
    MOTION_INDEXES = (2, 4)
    POSTURE_INDEXES = (0, 1, 3)

    def __init__(self, ref_path: str):
        self.ref_seq = self._load_reference(ref_path)
        self.feat_min, self.feat_max = self._get_minmax(self.ref_seq)
        self.ref_norm = self._normalize(self.ref_seq)
        self.ref_motion = self.ref_seq[:, 4]
        self.ref_motion_min = float(np.min(self.ref_motion)) if len(self.ref_motion) else 0.0
        self.ref_motion_max = float(np.max(self.ref_motion)) if len(self.ref_motion) else 1.0

    def _load_reference(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return np.array(data["sequence"], dtype=np.float32)

    def _get_minmax(self, seq: np.ndarray):
        return seq.min(axis=0), seq.max(axis=0)

    def _normalize(self, seq: np.ndarray):
        denom = np.maximum(self.feat_max - self.feat_min, 1e-6)
        return (seq - self.feat_min) / denom

    def _frame_error_vector(self, a: np.ndarray, b: np.ndarray):
        weights = np.array([
            2.4,   # trunk
            1.8,   # pelvic
            1.8,   # hip_flexion
            2.2,   # knee_angle
            1.8,   # ankle_rel_y
        ], dtype=np.float32)
        return np.abs(a - b) * weights

    def _frame_dist(self, a: np.ndarray, b: np.ndarray):
        return float(np.linalg.norm(self._frame_error_vector(a, b)))

    def _estimate_phase(self, user_seq: np.ndarray):
        if len(user_seq) == 0:
            return "unknown"

        motion = user_seq[:, 4]
        current = float(motion[-1])
        user_min = float(np.min(motion))
        user_max = float(np.max(motion))
        motion_floor = min(user_min, self.ref_motion_min)
        motion_span = max(max(user_max, self.ref_motion_max) - motion_floor, 1e-6)
        progress = float(np.clip((current - motion_floor) / motion_span, 0.0, 1.0))

        if len(motion) >= 4:
            slope = float(np.mean(np.diff(motion[-4:])))
        elif len(motion) >= 2:
            slope = float(motion[-1] - motion[0]) / max(len(motion) - 1, 1)
        else:
            slope = 0.0

        if progress >= 0.82:
            phase = "peak"
        elif progress <= 0.18 and slope <= 0.5:
            phase = "ready"
        elif slope >= 1.0:
            phase = "raising"
        elif slope <= -1.0:
            phase = "lowering"
        else:
            phase = "transition"

        return phase

    def _phase_penalty(self, phase: str, ref_progress: float):
        if phase == "peak":
            return 0.0 if ref_progress >= 0.72 else 0.18
        if phase == "raising":
            if ref_progress > 0.88:
                return 0.20
            return 0.0
        if phase == "lowering":
            if ref_progress < 0.18 or ref_progress > 0.92:
                return 0.12
            return 0.0
        if phase == "ready":
            return 0.0 if ref_progress <= 0.28 else 0.10
        return 0.0

    def _dtw(self, seq1: np.ndarray, seq2: np.ndarray, band_ratio: float = 0.3):
        n, m = len(seq1), len(seq2)
        dp = np.full((n + 1, m + 1), np.inf, dtype=np.float32)
        dp[0, 0] = 0.0
        band = max(3, int(max(n, m) * band_ratio))

        for i in range(1, n + 1):
            j_start = max(1, i - band)
            j_end = min(m, i + band)
            for j in range(j_start, j_end + 1):
                cost = self._frame_dist(seq1[i - 1], seq2[j - 1])
                dp[i, j] = cost + min(
                    dp[i - 1, j],
                    dp[i, j - 1],
                    dp[i - 1, j - 1],
                )

        i, j = n, m
        if not np.isfinite(dp[i, j]):
            return None

        path = []
        path_len = 0
        while i > 0 and j > 0:
            path_len += 1
            path.append((i - 1, j - 1))
            candidates = [
                (dp[i - 1, j], i - 1, j),
                (dp[i, j - 1], i, j - 1),
                (dp[i - 1, j - 1], i - 1, j - 1),
            ]
            _, i, j = min(candidates, key=lambda x: x[0])

        path.reverse()
        path_len = max(path_len, 1)
        total_cost = float(dp[n, m])
        norm_cost = total_cost / path_len
        return {
            "total_cost": total_cost,
            "norm_cost": norm_cost,
            "path": path,
        }

    def _compute_path_metrics(self, ref_seq: np.ndarray, user_seq: np.ndarray, path):
        feature_sums = np.zeros(len(self.FEATURE_NAMES), dtype=np.float32)
        motion_sum = 0.0
        posture_sum = 0.0
        for ref_idx, user_idx in path:
            err_vec = self._frame_error_vector(ref_seq[ref_idx], user_seq[user_idx])
            feature_sums += err_vec
            motion_sum += float(np.mean(err_vec[list(self.MOTION_INDEXES)]))
            posture_sum += float(np.mean(err_vec[list(self.POSTURE_INDEXES)]))

        steps = max(len(path), 1)
        feature_mean = feature_sums / steps
        feature_errors = {
            name: float(feature_mean[idx])
            for idx, name in enumerate(self.FEATURE_NAMES)
        }
        main_idx = max(self.POSTURE_INDEXES, key=lambda idx: feature_errors[self.FEATURE_NAMES[idx]])
        ref_end_idx = path[-1][0] if path else 0
        ref_progress = float(ref_end_idx / max(len(ref_seq) - 1, 1))
        return {
            "feature_errors": feature_errors,
            "motion_cost": float(motion_sum / steps),
            "posture_cost": float(posture_sum / steps),
            "main_error_feature": self.FEATURE_NAMES[main_idx],
            "local_ref_progress": ref_progress,
        }

    def _find_best_subsequence(self, user_seq: np.ndarray):
        user_len = len(user_seq)
        ref_len = len(self.ref_norm)
        if user_len == 0 or ref_len == 0:
            return None

        min_len = max(8, user_len - 6)
        max_len = min(ref_len, user_len + 6)
        best = None
        phase = self._estimate_phase(user_seq)

        for cand_len in range(min_len, max_len + 1):
            for start in range(0, ref_len - cand_len + 1):
                end = start + cand_len
                ref_slice = self.ref_norm[start:end]
                dtw_result = self._dtw(ref_slice, user_seq)
                if dtw_result is None:
                    continue
                metrics = self._compute_path_metrics(ref_slice, user_seq, dtw_result["path"])
                penalized_cost = dtw_result["norm_cost"] + self._phase_penalty(phase, metrics["local_ref_progress"])
                global_ref_idx = start + (dtw_result["path"][-1][0] if dtw_result["path"] else 0)
                candidate = {
                    "phase": phase,
                    "start": start,
                    "end": end,
                    "total_cost": dtw_result["total_cost"],
                    "norm_cost": dtw_result["norm_cost"],
                    "penalized_cost": penalized_cost,
                    "path": dtw_result["path"],
                    "ref_progress": float(global_ref_idx / max(ref_len - 1, 1)),
                    **metrics,
                }
                if best is None or candidate["penalized_cost"] < best["penalized_cost"]:
                    best = candidate
        return best

    def get_live_similarity(
        self,
        partial_user_seq,
        min_frames: int = 10,
        live_window: int = 30,
    ):
        user_seq = np.array(partial_user_seq, dtype=np.float32)

        if len(user_seq) < min_frames:
            return {
                "live_similarity": None,
                "cost": None,
                "motion_similarity": None,
                "posture_similarity": None,
                "phase": "unknown",
                "feature_errors": {},
                "main_error_feature": None,
                "ref_progress": None,
            }

        live_seq = user_seq[-live_window:] if len(user_seq) > live_window else user_seq
        user = self._normalize(live_seq)
        best = self._find_best_subsequence(user)
        if best is None:
            return {
                "live_similarity": None,
                "cost": None,
                "motion_similarity": None,
                "posture_similarity": None,
                "phase": self._estimate_phase(live_seq),
                "feature_errors": {},
                "main_error_feature": None,
                "ref_progress": None,
            }

        motion_similarity = max(0, min(100, round(100 - 16.0 * best["motion_cost"], 2)))
        posture_similarity = max(0, min(100, round(100 - 18.0 * best["posture_cost"], 2)))
        live_similarity = round((motion_similarity * 0.45) + (posture_similarity * 0.55), 2)

        return {
            "live_similarity": live_similarity,
            "cost": float(best["norm_cost"]),
            "motion_similarity": motion_similarity,
            "posture_similarity": posture_similarity,
            "phase": best["phase"],
            "feature_errors": best["feature_errors"],
            "main_error_feature": best["main_error_feature"],
            "ref_progress": best["ref_progress"],
            "ref_window": {
                "start": best["start"],
                "end": best["end"],
            },
        }

    def compare(self, user_seq):
        user_seq = np.array(user_seq, dtype=np.float32)

        user = self._normalize(user_seq)
        best = self._find_best_subsequence(user)
        if best is None:
            return {
                "score": 0,
                "dtw_score": 0,
                "cost": None,
                "penalty": 0,
            }
        motion_similarity = max(0, min(100, round(100 - 16.0 * best["motion_cost"], 2)))
        posture_similarity = max(0, min(100, round(100 - 18.0 * best["posture_cost"], 2)))
        dtw_score = round((motion_similarity * 0.45) + (posture_similarity * 0.55), 2)

        return {
            "score": dtw_score,
            "dtw_score": dtw_score,
            "cost": float(best["norm_cost"]),
            "penalty": 0,
            "motion_similarity": motion_similarity,
            "posture_similarity": posture_similarity,
            "phase": best["phase"],
            "feature_errors": best["feature_errors"],
            "main_error_feature": best["main_error_feature"],
            "ref_progress": best["ref_progress"],
        }
        
# ----------목 좌우돌리기 프로세서---------------------------------------------------------------
class NeckRotationDTWProcessor(BaseProcessor):
    def __init__(self, dtw_engine, target_reps: int = 3):
        self.dtw_engine = dtw_engine
        self.buffer = []
        self.last_live_similarity = None
        self.rep_count = 0
        self.rep_phase = "idle"
        self.first_side = None
        self.first_peak_angle = 0.0
        self.second_peak_angle = 0.0
        self.rep_score_sum = 0.0
        self.rep_score_count = 0
        self.rep_avg_similarity = None
        self.turn_threshold = 9.0
        self.center_threshold = 6.0
        self.min_peak_angle = 15.0
        self.max_trunk_rotation = 20.0
        self.target_reps = int(target_reps)
        self.feedback_router = RealTimeFeedbackRouter()
        self.session_summary = SessionFeedbackSummary()
        self.exercise_type = "neck_rotation"
        self.csv_logger = DtwFrameCsvLogger(self.exercise_type)
        self.session_finished = False
        self._last_obs_ts = time.time()
        

    def _reset_rep_state(self):
        self.rep_phase = "idle"
        self.first_side = None
        self.first_peak_angle = 0.0
        self.second_peak_angle = 0.0
        self.rep_score_sum = 0.0
        self.rep_score_count = 0
        self.rep_avg_similarity = None

    def extract_mp_features(self, pts):
        return get_neck_rotation_features_mp(pts)

    def process(self, keypoints, frame, depth_frame=None, intrinsics=None, mp_features=None):
        if self.session_finished:
            result = {
                "mode": "NECK_ROTATION_DTW",
                "status": "session_finished",
                "feedback": "세트가 종료되었습니다.",
                "similarity": self.last_live_similarity,
                "accuracy_pct": self.last_live_similarity,
                "rep_count": self.rep_count,
                "buffer_len": len(self.buffer),
            }
            self.csv_logger.log(result)
            return result
        if mp_features is None:
            result = {
                "mode": "NECK_ROTATION_DTW",
                "status": "waiting",
                "feedback": "자세를 인식 중입니다.",
                "similarity": self.last_live_similarity,
                "accuracy_pct": self.last_live_similarity,
                "rep_count": self.rep_count,
                "buffer_len": len(self.buffer),
            }
            self.csv_logger.log(result)
            return result

        current = tuple(round(v, 3) for v in mp_features)
        prev = tuple(round(v, 3) for v in self.buffer[-1]) if self.buffer else None

        if current != prev:
            self.buffer.append(mp_features)

        live_result = self.dtw_engine.get_live_similarity(
            self.buffer,
            min_frames=12,
            live_window=60,
        )

        live_similarity = live_result["live_similarity"]
        if live_similarity is not None:
            self.last_live_similarity = live_similarity

        now_ts = time.time()
        dt_sec = max(0.0, now_ts - self._last_obs_ts)
        self._last_obs_ts = now_ts
        compare_payload = {
            "phase": live_result.get("phase", "unknown"),
            "motion_similarity": live_result.get("motion_similarity"),
            "posture_similarity": live_result.get("posture_similarity"),
            "feature_errors": live_result.get("feature_errors", {}),
            "main_error_feature": live_result.get("main_error_feature"),
            "ref_progress": live_result.get("ref_progress"),
        }
        feedback_packet = self.feedback_router.process(self.exercise_type, compare_payload, now_ts)
        self.session_summary.observe(self.exercise_type, feedback_packet["all_issues"], dt_sec)
        instant_feedback = feedback_packet["feedback"] or "동작 분석 중입니다."

        trunk_rotation = float(mp_features[0])
        neck_turn_angle = float(mp_features[1])
        abs_turn_angle = abs(neck_turn_angle)
        is_centered = abs_turn_angle <= self.center_threshold
        current_side = None
        if neck_turn_angle <= -self.turn_threshold:
            current_side = "left"
        elif neck_turn_angle >= self.turn_threshold:
            current_side = "right"

        if self.rep_phase != "idle" and live_similarity is not None:
            self.rep_score_sum += live_similarity
            self.rep_score_count += 1
            logger.info(
                "[NECK AVG] accumulating | rep=%s phase=%s turn=%.2f trunk=%.2f count=%s running_avg=%.2f",
                self.rep_count + 1,
                self.rep_phase,
                neck_turn_angle,
                trunk_rotation,
                self.rep_score_count,
                self.rep_score_sum / self.rep_score_count,
            )

        if trunk_rotation > self.max_trunk_rotation and self.rep_phase != "idle":
            logger.warning(
                "[NECK AVG] rep reset due to trunk compensation | rep=%s trunk=%.2f phase=%s",
                self.rep_count + 1,
                trunk_rotation,
                self.rep_phase,
            )
            self._reset_rep_state()

        if self.rep_phase == "idle":
            if current_side in {"left", "right"}:
                self.first_side = current_side
                self.rep_phase = "first_turn"
                self.first_peak_angle = abs_turn_angle
                self.rep_score_sum = live_similarity or 0.0
                self.rep_score_count = 1 if live_similarity is not None else 0
                logger.info(
                    "[NECK AVG] rep started | rep=%s first_side=%s turn=%.2f",
                    self.rep_count + 1,
                    self.first_side,
                    neck_turn_angle,
                )

        elif self.rep_phase == "first_turn":
            self.first_peak_angle = max(self.first_peak_angle, abs_turn_angle)
            if is_centered:
                self.rep_phase = "center_return_1"
                logger.info(
                    "[NECK AVG] first side returned to center | rep=%s first_side=%s first_peak=%.2f",
                    self.rep_count + 1,
                    self.first_side,
                    self.first_peak_angle,
                )

        elif self.rep_phase == "center_return_1":
            expected_second_side = "right" if self.first_side == "left" else "left"
            if current_side == expected_second_side:
                self.rep_phase = "second_turn"
                self.second_peak_angle = abs_turn_angle
                logger.info(
                    "[NECK AVG] second side started | rep=%s second_side=%s turn=%.2f",
                    self.rep_count + 1,
                    expected_second_side,
                    neck_turn_angle,
                )

        elif self.rep_phase == "second_turn":
            self.second_peak_angle = max(self.second_peak_angle, abs_turn_angle)
            if is_centered:
                if (
                    self.first_peak_angle >= self.min_peak_angle
                    and self.second_peak_angle >= self.min_peak_angle
                    and self.rep_score_count > 0
                ):
                    self.rep_avg_similarity = round(
                        self.rep_score_sum / self.rep_score_count,
                        2,
                    )
                    self.rep_count += 1
                    result = {
                        "mode": "NECK_ROTATION_DTW",
                        "status": "rep_finished",
                        "feedback": f"{self.rep_count}회 수행 완료",
                        "similarity": self.last_live_similarity,
                        "accuracy_pct": self.last_live_similarity,
                        "avg_similarity": self.rep_avg_similarity,
                        "rep_count": self.rep_count,
                        "cost": live_result["cost"],
                        "buffer_len": len(self.buffer),
                        "mp_features": list(mp_features) if mp_features is not None else None,
                        "live_result": live_result,
                        "compare_payload": compare_payload,
                        "feedback_packet": feedback_packet,
                        "motion_similarity": live_result.get("motion_similarity"),
                        "posture_similarity": live_result.get("posture_similarity"),
                        "phase": live_result.get("phase"),
                        "main_error_feature": live_result.get("main_error_feature"),
                        "feature_errors": live_result.get("feature_errors", {}),
                    }
                    if self.rep_count >= self.target_reps:
                        final_summary = self.session_summary.finalize(top_k=3)
                        result["session_finished"] = True
                        result["session_summary"] = final_summary
                        result["session_summary_lines"] = format_top3_text(final_summary)
                        self.session_finished = True
                    logger.info(
                        "[NECK AVG] rep finished | rep=%s avg_similarity=%.2f first_peak=%.2f second_peak=%.2f samples=%s",
                        self.rep_count,
                        self.rep_avg_similarity,
                        self.first_peak_angle,
                        self.second_peak_angle,
                        self.rep_score_count,
                    )
                    self._reset_rep_state()
                    self.csv_logger.log(result)
                    return result

                logger.warning(
                    "[NECK AVG] rep rejected | rep=%s first_peak=%.2f second_peak=%.2f samples=%s",
                    self.rep_count + 1,
                    self.first_peak_angle,
                    self.second_peak_angle,
                    self.rep_score_count,
                )
                self._reset_rep_state()

        result = {
            "mode": "NECK_ROTATION_DTW",
            "status": "running",
            "feedback": instant_feedback,
            "similarity": self.last_live_similarity,
            "accuracy_pct": self.last_live_similarity,
            "rep_count": self.rep_count,
            "cost": live_result["cost"],
            "buffer_len": len(self.buffer),
            "mp_features": list(mp_features) if mp_features is not None else None,
            "live_result": live_result,
            "compare_payload": compare_payload,
            "feedback_packet": feedback_packet,
            "motion_similarity": live_result.get("motion_similarity"),
            "posture_similarity": live_result.get("posture_similarity"),
            "phase": live_result.get("phase"),
            "main_error_feature": live_result.get("main_error_feature"),
            "feature_errors": live_result.get("feature_errors", {}),
        }
        self.csv_logger.log(result)
        return result
        
# ----------목 좌우돌리기 DTW---------------------------------------------------------------
class NeckRotationDTW:
    FEATURE_NAMES = (
        "trunk_rotation",
        "neck_turn_angle",
        "head_tilt",
        "shoulder_line_angle",
    )
    MOTION_INDEXES = (1,)
    POSTURE_INDEXES = (0, 2, 3)

    def __init__(self, ref_path: str):
        self.ref_seq = self._load_reference(ref_path)
        self.feat_min, self.feat_max = self._get_minmax(self.ref_seq)
        self.ref_norm = self._normalize(self.ref_seq)

    def _load_reference(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return np.array(data["sequence"], dtype=np.float32)

    def _get_minmax(self, seq: np.ndarray):
        return seq.min(axis=0), seq.max(axis=0)

    def _normalize(self, seq: np.ndarray):
        denom = np.maximum(self.feat_max - self.feat_min, 1e-6)
        return (seq - self.feat_min) / denom

    def _frame_error_vector(self, a: np.ndarray, b: np.ndarray):
        weights = np.array([
            2.6,
            2.2,
            2.8,
            1.4,
        ], dtype=np.float32)
        return np.abs(a - b) * weights

    def _frame_dist(self, a: np.ndarray, b: np.ndarray):
        return float(np.linalg.norm(self._frame_error_vector(a, b)))

    def _estimate_phase(self, user_seq: np.ndarray):
        if len(user_seq) == 0:
            return "unknown"
        turns = user_seq[:, 1]
        abs_turns = np.abs(turns)
        current = float(abs_turns[-1])
        tmin = float(np.min(abs_turns))
        tmax = float(np.max(abs_turns))
        progress = float(np.clip((current - tmin) / max(tmax - tmin, 1e-6), 0.0, 1.0))
        if len(turns) >= 4:
            slope = float(np.mean(np.diff(turns[-4:])))
        elif len(turns) >= 2:
            slope = float(turns[-1] - turns[0]) / max(len(turns) - 1, 1)
        else:
            slope = 0.0
        if progress >= 0.82:
            return "peak"
        if progress <= 0.18 and abs(slope) <= 1.0:
            return "center"
        if slope > 1.0:
            return "turning_right"
        if slope < -1.0:
            return "turning_left"
        return "transition"

    def _phase_penalty(self, phase: str, ref_progress: float):
        if phase == "peak":
            return 0.0 if ref_progress >= 0.55 else 0.14
        if phase in {"turning_right", "turning_left"}:
            return 0.18 if ref_progress > 0.92 else 0.0
        if phase == "center":
            return 0.08 if ref_progress > 0.22 else 0.0
        return 0.0

    def _dtw(self, seq1: np.ndarray, seq2: np.ndarray, band_ratio: float = 0.3):
        n, m = len(seq1), len(seq2)
        dp = np.full((n + 1, m + 1), np.inf, dtype=np.float32)
        dp[0, 0] = 0.0
        band = max(3, int(max(n, m) * band_ratio))

        for i in range(1, n + 1):
            j_start = max(1, i - band)
            j_end = min(m, i + band)
            for j in range(j_start, j_end + 1):
                cost = self._frame_dist(seq1[i - 1], seq2[j - 1])
                dp[i, j] = cost + min(
                    dp[i - 1, j],
                    dp[i, j - 1],
                    dp[i - 1, j - 1],
                )

        i, j = n, m
        if not np.isfinite(dp[i, j]):
            return None
        path = []
        path_len = 0
        while i > 0 and j > 0:
            path_len += 1
            path.append((i - 1, j - 1))
            candidates = [
                (dp[i - 1, j], i - 1, j),
                (dp[i, j - 1], i, j - 1),
                (dp[i - 1, j - 1], i - 1, j - 1),
            ]
            _, i, j = min(candidates, key=lambda x: x[0])

        path.reverse()
        path_len = max(path_len, 1)
        total_cost = float(dp[n, m])
        norm_cost = total_cost / path_len
        return {
            "total_cost": total_cost,
            "norm_cost": norm_cost,
            "path": path,
        }

    def _compute_path_metrics(self, ref_seq: np.ndarray, user_seq: np.ndarray, path):
        feature_sums = np.zeros(len(self.FEATURE_NAMES), dtype=np.float32)
        motion_sum = 0.0
        posture_sum = 0.0
        for ref_idx, user_idx in path:
            err_vec = self._frame_error_vector(ref_seq[ref_idx], user_seq[user_idx])
            feature_sums += err_vec
            motion_sum += float(np.mean(err_vec[list(self.MOTION_INDEXES)]))
            posture_sum += float(np.mean(err_vec[list(self.POSTURE_INDEXES)]))

        steps = max(len(path), 1)
        feature_mean = feature_sums / steps
        feature_errors = {
            name: float(feature_mean[idx])
            for idx, name in enumerate(self.FEATURE_NAMES)
        }
        main_idx = max(self.POSTURE_INDEXES, key=lambda idx: feature_errors[self.FEATURE_NAMES[idx]])
        local_ref_idx = path[-1][0] if path else 0
        local_ref_progress = float(local_ref_idx / max(len(ref_seq) - 1, 1))
        return {
            "feature_errors": feature_errors,
            "motion_cost": float(motion_sum / steps),
            "posture_cost": float(posture_sum / steps),
            "main_error_feature": self.FEATURE_NAMES[main_idx],
            "local_ref_progress": local_ref_progress,
        }

    def _find_best_subsequence(self, user_seq: np.ndarray):
        user_len = len(user_seq)
        ref_len = len(self.ref_norm)
        if user_len == 0 or ref_len == 0:
            return None
        min_len = max(10, user_len - 8)
        max_len = min(ref_len, user_len + 8)
        phase = self._estimate_phase(user_seq)
        best = None
        for cand_len in range(min_len, max_len + 1):
            for start in range(0, ref_len - cand_len + 1):
                end = start + cand_len
                ref_slice = self.ref_norm[start:end]
                dtw_result = self._dtw(ref_slice, user_seq)
                if dtw_result is None:
                    continue
                metrics = self._compute_path_metrics(ref_slice, user_seq, dtw_result["path"])
                penalized_cost = dtw_result["norm_cost"] + self._phase_penalty(phase, metrics["local_ref_progress"])
                global_ref_idx = start + (dtw_result["path"][-1][0] if dtw_result["path"] else 0)
                candidate = {
                    "phase": phase,
                    "start": start,
                    "end": end,
                    "norm_cost": dtw_result["norm_cost"],
                    "total_cost": dtw_result["total_cost"],
                    "penalized_cost": penalized_cost,
                    "ref_progress": float(global_ref_idx / max(ref_len - 1, 1)),
                    **metrics,
                }
                if best is None or candidate["penalized_cost"] < best["penalized_cost"]:
                    best = candidate
        return best

    def compare(self, user_seq):
        user_seq = np.array(user_seq, dtype=np.float32)
        user = self._normalize(user_seq)
        best = self._find_best_subsequence(user)
        if best is None:
            return {"score": 0, "dtw_score": 0, "cost": None}
        motion_similarity = max(0, min(100, round(100 - 18.0 * best["motion_cost"], 2)))
        posture_similarity = max(0, min(100, round(100 - 18.0 * best["posture_cost"], 2)))
        dtw_score = round((motion_similarity * 0.55) + (posture_similarity * 0.45), 2)

        return {
            "score": dtw_score,
            "dtw_score": dtw_score,
            "cost": float(best["norm_cost"]),
            "motion_similarity": motion_similarity,
            "posture_similarity": posture_similarity,
            "phase": best["phase"],
            "feature_errors": best["feature_errors"],
            "main_error_feature": best["main_error_feature"],
            "ref_progress": best["ref_progress"],
        }

    def get_live_similarity(
        self,
        partial_user_seq,
        min_frames: int = 12,
        live_window: int = 60,
    ):
        user_seq = np.array(partial_user_seq, dtype=np.float32)

        if len(user_seq) < min_frames:
            return {
                "live_similarity": None,
                "cost": None,
                "motion_similarity": None,
                "posture_similarity": None,
                "phase": "unknown",
                "feature_errors": {},
                "main_error_feature": None,
                "ref_progress": None,
            }

        live_seq = user_seq[-live_window:] if len(user_seq) > live_window else user_seq
        user = self._normalize(live_seq)
        best = self._find_best_subsequence(user)
        if best is None:
            return {
                "live_similarity": None,
                "cost": None,
                "motion_similarity": None,
                "posture_similarity": None,
                "phase": self._estimate_phase(live_seq),
                "feature_errors": {},
                "main_error_feature": None,
                "ref_progress": None,
            }

        motion_similarity = max(0, min(100, round(100 - 18.0 * best["motion_cost"], 2)))
        posture_similarity = max(0, min(100, round(100 - 18.0 * best["posture_cost"], 2)))
        live_similarity = round((motion_similarity * 0.55) + (posture_similarity * 0.45), 2)

        return {
            "live_similarity": live_similarity,
            "cost": float(best["norm_cost"]),
            "motion_similarity": motion_similarity,
            "posture_similarity": posture_similarity,
            "phase": best["phase"],
            "feature_errors": best["feature_errors"],
            "main_error_feature": best["main_error_feature"],
            "ref_progress": best["ref_progress"],
        }
