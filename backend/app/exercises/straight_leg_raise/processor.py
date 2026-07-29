# Straight Leg Raise(다리 들기) 운동 DTW 프로세서 및 DTW 엔진.
# 카메라 프레임마다 관절 feature를 받아 기준 동작과 실시간 비교(DTW)하고,
# 반복 횟수(rep)를 카운트하며 피드백을 생성한다.
# StraightLegRaiseRightDTWProcessor: 프레임 단위로 동작을 처리하는 메인 프로세서.
# StraightLegRaiseRightDTW: DTW 알고리즘으로 사용자 동작과 기준 동작을 수치 비교하는 엔진.
import csv
import time
import logging
import numpy as np
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from app.exercises.shared.base import BaseProcessor, BaseDTW, AsyncLiveDtwRunner, DtwFrameCsvLogger, DTW_COMPUTE_EXECUTOR
from app.exercises.straight_leg_raise.features import get_straight_leg_raise_right_features_yolo, flip_yolo_left_right
from app.exercises.shared.rom_defaults import DEFAULT_ROM
from app.services.feedback.realtime_feedback_router import RealTimeFeedbackRouter
from app.services.feedback.session_feedback_summary import SessionFeedbackSummary, format_top3_text

_COMP_CSV_PATH   = Path(__file__).parent / "compensation_results.csv"
_COMP_CSV_HEADER = "timestamp,set,rep,side,detected\n"


def _append_comp_csv(set_num: int, rep_num: int, side: str, detected: str) -> None:
    need_header = not _COMP_CSV_PATH.exists()
    with _COMP_CSV_PATH.open("a", encoding="utf-8", newline="") as f:
        if need_header:
            f.write(_COMP_CSV_HEADER)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"{ts},{set_num},{rep_num},{side},{detected}\n")
        f.flush()


def _next_set_number() -> int:
    if not _COMP_CSV_PATH.exists():
        return 1
    last = 0
    with _COMP_CSV_PATH.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                last = max(last, int(row["set"]))
            except (ValueError, KeyError):
                pass
    return last + 1


logger = logging.getLogger(__name__)


# Straight Leg Raise 운동의 프레임별 처리를 담당하는 프로세서 클래스.
# 매 프레임마다 관절 좌표를 받아 feature를 추출하고, 실시간 DTW 유사도를 계산하며,
# 엉덩이 굽힘 각도 변화로 rep 완료를 판단한다. 왼쪽 다리 모드는 좌우 반전으로 처리한다.
class StraightLegRaiseRightDTWProcessor(BaseProcessor):
    # DTW 엔진, 왼쪽 다리 여부, 목표 반복 횟수를 받아 프로세서를 초기화한다.
    # dtw_engine: StraightLegRaiseRightDTW 인스턴스
    # use_left_flip: True이면 왼쪽 다리 동작으로 간주해 좌우 반전 처리
    # target_reps: 목표 반복 횟수 (기본값 3회)
    def __init__(self, dtw_engine, use_left_flip: bool = False, target_reps: int = 3, rom: dict = None):
        self.dtw_engine = dtw_engine
        self.buffer = []
        self.last_live_similarity = None
        self.use_left_flip = use_left_flip
        self.rep_count = 0
        self.rep_state = "down"
        self.rep_peak_angle = 0.0

        rom = rom or DEFAULT_ROM
        side = "left" if use_left_flip else "right"
        slr_key = f"straight_leg_raise_{side}_max"
        seated_key = f"seated_knee_extension_{side}_max"
        if slr_key in rom:
            hip_rom = float(rom[slr_key])
        elif seated_key in rom and float(rom[seated_key]) > 90:
            hip_rom = (float(rom[seated_key]) - 90) * 0.7
        else:
            hip_rom = float(DEFAULT_ROM[slr_key])
        self.hip_rom = hip_rom
        self.raise_threshold = hip_rom * 0.35
        self.min_peak_angle  = hip_rom * 0.60
        self.down_threshold  = 5.0
        logger.info(
            "[StraightLegRaise] hip_rom=%.1f raise=%.1f min_peak=%.1f down=%.1f",
            hip_rom, self.raise_threshold, self.min_peak_angle, self.down_threshold,
        )

        self.target_reps = int(target_reps)
        self.feedback_router = RealTimeFeedbackRouter()
        self.session_summary = SessionFeedbackSummary()
        self.exercise_type = "straight_leg_raise_right"
        self.active_side = "left" if use_left_flip else "right"
        self._set_num = _next_set_number()
        self._rep_events: list = []
        self.csv_logger = DtwFrameCsvLogger(self.exercise_type)
        self.session_finished = False
        self._last_obs_ts = time.time()
        self.live_runner = AsyncLiveDtwRunner(
            dtw_engine,
            live_min_frames=10,
            live_window=30,
            live_interval_sec=0.12,
            live_frame_interval=4,
            live_search_margin=10,
        )
        self.pending_rep_compares: list[tuple[Future, Dict[str, Any]]] = []
        self.ready = False
        self._debug_frame = 0
        self._pain_warned_this_rep = False

    # YOLO 관절 좌표를 받아 Straight Leg Raise feature 벡터를 추출해 반환한다.
    # 왼쪽 다리 모드(use_left_flip=True)이면 먼저 좌우를 반전한 뒤 feature를 계산한다.
    # pts: YOLO 관절 좌표 딕셔너리
    def extract_mp_features(self, pts):
        if self.use_left_flip:
            pts = flip_yolo_left_right(pts)
        return get_straight_leg_raise_right_features_yolo(pts)

    # 매 프레임마다 호출되는 메인 처리 함수.
    # 관절 좌표와 feature를 받아 실시간 유사도 계산, rep 카운트, 피드백 생성을 수행한다.
    # keypoints: 관절 좌표 딕셔너리 (누운 자세 감지에 사용)
    # frame: 현재 카메라 프레임 이미지
    # mp_features: 미리 추출된 feature 벡터 (없으면 None)
    # 반환: 현재 상태, 피드백, 유사도 등을 담은 딕셔너리
    def process(self, keypoints, frame, depth_frame=None, intrinsics=None, mp_features=None):
        pending_result = self._poll_pending_rep_compare()
        if pending_result is not None:
            self.csv_logger.log(pending_result)
            return pending_result
        display_rep_count = self.rep_count - len(self.pending_rep_compares)
        if self.session_finished:
            result = {
                "mode": "STRAIGHT_LEG_RAISE_DTW",
                "status": "session_finished",
                "feedback": "세트가 종료되었습니다.",
                "similarity": self.last_live_similarity,
                "accuracy_pct": self.last_live_similarity,
                "rep_count": display_rep_count,
                "buffer_len": len(self.buffer),
            }
            self.csv_logger.log(result)
            return result

        if mp_features is None:
            result = {
                "mode": "STRAIGHT_LEG_RAISE_DTW",
                "status": "waiting",
                "feedback": "자세를 인식 중입니다.",
                "similarity": self.last_live_similarity,
                "accuracy_pct": self.last_live_similarity,
                "rep_count": display_rep_count,
                "buffer_len": len(self.buffer),
            }
            self.csv_logger.log(result)
            return result

        # 아직 준비 자세(옆으로 누운 자세)가 확인되지 않은 경우 자세를 감지한다.
        if not self.ready:
            required = [6, 12, 14, 16]
            if all(i in keypoints for i in required):
                shoulder = keypoints[6]
                hip = keypoints[12]
                ankle = keypoints[16]
                torso_dx = abs(shoulder["x"] - hip["x"])
                torso_dy = abs(shoulder["y"] - hip["y"])
                leg_dx = abs(hip["x"] - ankle["x"])
                leg_dy = abs(hip["y"] - ankle["y"])
                is_lying = (
                    torso_dx > torso_dy * 1.5
                    and leg_dx > leg_dy * 1.5
                )
                if is_lying:
                    self.ready = True
                    return {
                        "mode": "STRAIGHT_LEG_RAISE_DTW",
                        "status": "ready",
                        "feedback": "누운 자세 확인 완료. 다리를 들어주세요.",
                        "similarity": 0,
                        "accuracy_pct": 0,
                        "rep_count": display_rep_count,
                        "buffer_len": 0,
                    }
            return {
                "mode": "STRAIGHT_LEG_RAISE_DTW",
                "status": "waiting_ready",
                "feedback": "옆으로 누운 자세를 먼저 잡아주세요.",
                "similarity": 0,
                "accuracy_pct": 0,
                "rep_count": display_rep_count,
                "buffer_len": 0,
            }

        # YOLO 진단 로그: 30프레임마다 관절 좌표 및 각도 출력
        self._debug_frame += 1
        if self._debug_frame % 30 == 0:
            _kp = {5:"L_sh", 6:"R_sh", 11:"L_hip", 12:"R_hip", 13:"L_kn", 14:"R_kn", 15:"L_ank", 16:"R_ank"}
            missing = [_kp[k] for k in _kp if k not in keypoints]
            coord_str = "  ".join(
                f"{_kp[k]}=({keypoints[k].get('x',0):.2f},{keypoints[k].get('y',0):.2f},{keypoints[k].get('z',0):.2f})"
                for k in _kp if k in keypoints
            )
            logger.info("[SLR DBG] frame=%d  flip=%s  missing=%s", self._debug_frame, self.use_left_flip, missing or "없음")
            logger.info("[SLR DBG] %s", coord_str)
            logger.info(
                "[SLR DBG] hip_flexion=%.1f  leg_angle=%.1f  knee=%.1f  state=%s  peak=%.1f",
                float(mp_features[0]), 180.0 - float(mp_features[0]), float(mp_features[1]),
                self.rep_state, self.rep_peak_angle,
            )

        current = tuple(round(v, 3) for v in mp_features)
        prev = tuple(round(v, 3) for v in self.buffer[-1]) if self.buffer else None

        if current != prev:
            self.buffer.append(mp_features)

        live_result = self.live_runner.tick(self.buffer)

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

        # leg_angle: 0° = 평평, 클수록 다리를 높이 든 것 (= 180 - hip_flexion)
        leg_angle = 180.0 - float(mp_features[0])
        rep_just_finished = False
        _not_counted_feedback = None
        _not_counted_rom_pct = None
        _completed_peak_angle = 0.0
        _pain_warn = False
        if self.rep_state == "down" and leg_angle >= self.raise_threshold:
            self.rep_state = "up"
            self.rep_peak_angle = leg_angle
            self._rep_events.append({"type": "start", "t": time.time(), "rep": self.rep_count + 1})
        elif self.rep_state == "up":
            if leg_angle > self.rep_peak_angle:
                self.rep_peak_angle = leg_angle
            if leg_angle > self.hip_rom and not self._pain_warned_this_rep:
                self._pain_warned_this_rep = True
                _pain_warn = True
            if leg_angle <= self.down_threshold:
                _completed_peak_angle = self.rep_peak_angle
                if self.rep_peak_angle >= self.min_peak_angle:
                    self.rep_count += 1
                    rep_just_finished = True
                    self._rep_events.append({"type": "end", "t": time.time(), "rep": self.rep_count, "label": "정상", "max_angle": round(self.rep_peak_angle, 2)})
                    try:
                        _append_comp_csv(self._set_num, self.rep_count, self.active_side, "정상")
                    except Exception as e:
                        logger.warning("[StraightLegRaise] CSV 저장 실패 (무시): %s", e)
                else:
                    _not_counted_rom_pct = round(self.rep_peak_angle / self.hip_rom * 100, 1)
                    _not_counted_feedback = "더 올려보세요"
                    logger.info(
                        "[ROM] rep 미카운팅 — peak=%.1f° (%.1f%% of %.1f°) → 더 올려보세요",
                        self.rep_peak_angle, _not_counted_rom_pct, self.hip_rom,
                    )
                self.rep_state = "down"
                self.rep_peak_angle = 0.0
                self._pain_warned_this_rep = False

        result = {
            "mode": "STRAIGHT_LEG_RAISE_DTW",
            "status": "running",
            "feedback": instant_feedback,
            "similarity": self.last_live_similarity,
            "accuracy_pct": self.last_live_similarity,
            "cost": live_result["cost"],
            "motion_similarity": live_result.get("motion_similarity"),
            "posture_similarity": live_result.get("posture_similarity"),
            "phase": live_result.get("phase"),
            "rep_count": display_rep_count,
            "main_error_feature": live_result.get("main_error_feature"),
            "feature_errors": live_result.get("feature_errors", {}),
            "buffer_len": len(self.buffer),
            "mp_features": list(mp_features) if mp_features is not None else None,
            "live_result": live_result,
            "compare_payload": compare_payload,
            "feedback_packet": feedback_packet,
        }
        if _not_counted_feedback:
            result["feedback"] = _not_counted_feedback
            result["rom_pct"] = _not_counted_rom_pct

        if _pain_warn:
            result["feedback"] = "통증이 느껴지면 여기서 멈추세요"

        if rep_just_finished:
            peak_pct = round(_completed_peak_angle / self.hip_rom * 100, 1)
            rom_feedback = "" if peak_pct >= 80 else "조금 더 올릴 수 있어요"
            logger.info(
                "[ROM] rep=%d peak=%.1f°(%.1f%% of %.1f°) → %s",
                self.rep_count, _completed_peak_angle, peak_pct, self.hip_rom, rom_feedback,
            )
            completed_rep = self.rep_count
            buffer_snapshot = np.array(self.buffer, dtype=np.float32, copy=True)
            self.pending_rep_compares.append(
                (
                    DTW_COMPUTE_EXECUTOR.submit(self.dtw_engine.compare, buffer_snapshot),
                    {
                        "rep_count": completed_rep,
                        "accuracy_pct": self.last_live_similarity,
                        "similarity": self.last_live_similarity,
                        "rom_feedback": rom_feedback,
                        "rom_pct": peak_pct,
                    },
                )
            )
            self.buffer = []
            self.live_runner.reset()
            result["feedback"] = f"{completed_rep}회 동작을 분석 중입니다."
            result["rep_count"] = display_rep_count
            result["buffer_len"] = 0
        self.csv_logger.log(result)
        return result

    # 백그라운드에서 처리 중인 rep DTW 비교 결과를 확인해 완료된 것을 반환한다.
    # 비교가 아직 진행 중이면 None을 반환하고, 완료되면 rep 결과 딕셔너리를 반환한다.
    # 목표 횟수를 채우면 세션 요약 정보도 함께 포함해 반환한다.
    def _poll_pending_rep_compare(self) -> Dict[str, Any] | None:
        if not self.pending_rep_compares:
            return None
        future, meta = self.pending_rep_compares[0]
        if not future.done():
            return None
        self.pending_rep_compares.pop(0)
        try:
            compare_result = future.result()
        except Exception:
            logger.exception("Straight Leg Raise rep DTW 비교가 실패했습니다.")
            compare_result = {"score": 0, "dtw_score": 0, "cost": None}

        result = {
            "mode": "STRAIGHT_LEG_RAISE_DTW",
            "status": "rep_finished",
            "rom_feedback": meta.get("rom_feedback"),
            "rom_pct": meta.get("rom_pct"),
            "feedback": f"{meta['rep_count']}회 수행 완료",
            "similarity": meta.get("similarity"),
            "accuracy_pct": meta.get("accuracy_pct"),
            "score": compare_result.get("score"),
            "dtw_score": compare_result.get("dtw_score"),
            "final_score": compare_result.get("score"),
            "cost": compare_result.get("cost"),
            "rep_count": meta["rep_count"],
            "buffer_len": len(self.buffer),
        }
        actual_rep_count = meta["rep_count"] - len(self.pending_rep_compares)

        if actual_rep_count >= self.target_reps:
            final_summary = self.session_summary.finalize(top_k=3)
            result["session_finished"] = True
            result["session_summary"] = final_summary
            result["session_summary_lines"] = format_top3_text(final_summary)
            self.session_finished = True
        return result

    def get_rep_events(self) -> list:
        return list(self._rep_events)


# Straight Leg Raise 운동의 DTW 비교 엔진 클래스.
# 미리 저장된 기준 동작(레퍼런스 시퀀스)과 사용자 동작을 DTW 알고리즘으로 비교해
# 유사도 점수와 관절별 오차를 계산한다. feature는 엉덩이굽힘, 무릎각도, 발목높이 3개를 사용한다.
class StraightLegRaiseRightDTW(BaseDTW):
    FEATURE_NAMES = (
        "hip_flexion",
        "knee_angle",
        "ankle_height",
    )
    MOTION_INDEXES = (2,)
    POSTURE_INDEXES = (0, 1)
    FEATURE_WEIGHTS = (1.8, 2.0, 2.2)
    MIN_BAND = 3

    # 기준 동작 파일 경로를 받아 DTW 엔진을 초기화한다.
    # ref_path: 기준 동작 feature 시퀀스가 저장된 파일 경로 (CSV 또는 npy)
    def __init__(self, ref_path: str):
        self.ref_seq = self._load_reference(ref_path)
        self.feat_min, self.feat_max = self._get_minmax(self.ref_seq)
        self.ref_norm = self._normalize(self.ref_seq)
        self.ref_motion = self.ref_seq[:, 2]
        self.ref_motion_min = float(np.min(self.ref_motion)) if len(self.ref_motion) else 0.0
        self.ref_motion_max = float(np.max(self.ref_motion)) if len(self.ref_motion) else 1.0

    # 최근 사용자 시퀀스를 분석해 현재 동작 단계(올리는 중, 정점, 내리는 중 등)를 판단한다.
    # user_seq: 사용자 feature 시퀀스 배열 (발목 높이 열로 단계를 추정)
    # 반환: 동작 단계를 나타내는 문자열 ("peak", "raising", "lowering", "ready", "transition")
    def _estimate_phase(self, user_seq: np.ndarray):
        if len(user_seq) == 0:
            return "unknown"

        motion = user_seq[:, 2]
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

    # 현재 동작 단계와 기준 동작 진행도에 따라 유사도 페널티 값을 반환한다.
    # phase: 현재 동작 단계 문자열
    # ref_progress: 기준 동작에서의 현재 진행 비율 (0.0~1.0)
    # 반환: 페널티 값 (0.0이면 페널티 없음)
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

    # DTW 경로를 따라 각 프레임별 오차를 누적해 feature별 평균 오차와 비용을 계산한다.
    # ref_seq: 정규화된 기준 동작 시퀀스
    # user_seq: 정규화된 사용자 동작 시퀀스
    # path: DTW 정렬 경로 (기준 인덱스, 사용자 인덱스) 쌍의 리스트
    # 반환: 관절별 오차, 동작/자세 비용, 주요 오차 항목, 진행도 등을 담은 딕셔너리
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

    # 동작 중 실시간으로 현재까지의 시퀀스와 기준 동작을 DTW로 비교해 유사도를 반환한다.
    # partial_user_seq: 현재까지 수집된 사용자 feature 시퀀스
    # min_frames: 비교를 시작하기 위한 최소 프레임 수
    # live_window: 가장 최근 몇 프레임을 슬라이딩 윈도우로 사용할지
    # 반환: 실시간 유사도, 동작/자세 유사도, 관절별 오차, 동작 단계 등을 담은 딕셔너리
    def get_live_similarity(
        self,
        partial_user_seq,
        min_frames: int = 10,
        live_window: int = 30,
        search_hint: Dict[str, Any] | None = None,
        search_margin: int | None = None,
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
        phase = self._estimate_phase(live_seq)
        ref_partial = self.ref_norm[: max(min_frames, min(len(self.ref_norm), len(user)))]
        dtw_result = self._dtw(ref_partial, user)
        if dtw_result is None:
            return {
                "live_similarity": None,
                "cost": None,
                "motion_similarity": None,
                "posture_similarity": None,
                "phase": phase,
                "feature_errors": {},
                "main_error_feature": None,
                "ref_progress": None,
                "ref_window": None,
            }
        best = {
            "phase": phase,
            "start": 0,
            "end": len(ref_partial),
            "norm_cost": dtw_result["norm_cost"],
            "total_cost": dtw_result["total_cost"],
            "path": dtw_result["path"],
            **self._compute_path_metrics(ref_partial, user, dtw_result["path"]),
        }
        best["ref_progress"] = best["local_ref_progress"]

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

    # 한 rep이 완료된 후 전체 사용자 시퀀스와 기준 동작을 DTW로 전체 비교해 최종 점수를 반환한다.
    # user_seq: 한 rep 동안 수집된 전체 사용자 feature 시퀀스
    # 반환: 최종 점수, 동작/자세 유사도, 관절별 오차 등을 담은 딕셔너리
    def compare(self, user_seq):
        user_seq = np.array(user_seq, dtype=np.float32)
        user = self._normalize(user_seq)
        dtw_result = self._dtw(self.ref_norm, user)
        if dtw_result is None:
            return {
                "score": 0,
                "dtw_score": 0,
                "cost": None,
                "penalty": 0,
            }
        best = {
            "phase": self._estimate_phase(user_seq),
            "start": 0,
            "end": len(self.ref_norm),
            "norm_cost": dtw_result["norm_cost"],
            "total_cost": dtw_result["total_cost"],
            "path": dtw_result["path"],
            **self._compute_path_metrics(self.ref_norm, user, dtw_result["path"]),
        }
        best["ref_progress"] = best["local_ref_progress"]
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
