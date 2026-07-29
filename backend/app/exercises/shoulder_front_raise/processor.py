# 어깨 전방 거상 운동의 실시간 DTW 분석과 보상자세 감지를 담당하는 모듈.
# 사용자의 왼팔 들어올리기 동작을 프레임 단위로 수집하고, 전문가 기준 동작과 비교해
# 유사도·반복 횟수를 계산하며, rep 완료 시 rule-based 보상자세 피드백을 생성한다.
import csv
import time
import logging
import numpy as np
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from app.exercises.shared.base import BaseProcessor, BaseDTW, AsyncLiveDtwRunner, DtwFrameCsvLogger, DTW_COMPUTE_EXECUTOR
from app.exercises.shoulder_front_raise.features import get_shoulder_front_raise_left_features_yolo
from app.exercises.shoulder_front_raise.compensation import detect_compensations
from app.exercises.shared.rom_defaults import DEFAULT_ROM

_COMP_CSV_PATH   = Path(__file__).parent / "compensation_results.csv"
_COMP_CSV_HEADER = "timestamp,set,rep,arm,detected\n"


def _append_comp_csv(set_num: int, rep_num: int, arm: str, detected: str) -> None:
    need_header = not _COMP_CSV_PATH.exists()
    with _COMP_CSV_PATH.open("a", encoding="utf-8", newline="") as f:
        if need_header:
            f.write(_COMP_CSV_HEADER)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"{ts},{set_num},{rep_num},{arm},{detected}\n")
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


# 어깨 전방 거상 운동의 실시간 DTW 분석과 보상자세 감지를 수행하는 프로세서 클래스.
# 팔을 들어올리기 시작해 내려올 때까지를 1회로 카운트하며,
# 각 회가 끝날 때마다 DTW 비교(비동기)와 보상자세 감지(동기)를 실행한다.
class ShoulderFrontRaiseLeftDTWProcessor(BaseProcessor):
    def __init__(self, dtw_engine, mirror_input: bool = False, target_reps: int = 3, rom: dict = None):
        self.dtw_engine = dtw_engine
        self.buffer = []
        self._comp_buffer: list = []   # rep 중 keypoints 누적 (보상자세 감지용)
        self._rep_events: list = []    # rep별 start/end 타임스탬프 (클립 절단용)
        self._set_num = _next_set_number()
        self.last_live_similarity = None
        self.mirror_input = mirror_input
        self.rep_count = 0
        self.rep_state = "down"
        self.rep_peak_angle = 0.0
        self.target_reps = int(target_reps)
        self.rep_peaks = []  # rep별 최고 각도 누적

        rom = rom or DEFAULT_ROM
        side = "right" if mirror_input else "left"
        self.side = side
        self.rom_max = float(rom.get(f"shoulder_{side}_flexion_max",
                                     DEFAULT_ROM[f"shoulder_{side}_flexion_max"]))
        self.raise_threshold = self.rom_max * 0.35  # up 전환 기준 (들기 시작)
        self.down_threshold  = self.rom_max * 0.25  # down 복귀 기준
        self.min_peak_angle  = self.rom_max * 0.60  # rep 인정 최소 높이
        logger.info("[ShoulderFrontRaise] rom_max=%.1f raise=%.1f down=%.1f min_peak=%.1f",
                    self.rom_max, self.raise_threshold, self.down_threshold, self.min_peak_angle)
        self.exercise_type = "shoulder_front_raise"
        self.csv_logger = DtwFrameCsvLogger(self.exercise_type)
        self.session_finished = False
        self.ready_count = 0
        self.ready_required_frames = 5
        self.is_ready = False
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
        self._pain_warned_this_rep = False

    def extract_mp_features(self, pts):
        return get_shoulder_front_raise_left_features_yolo(pts)

    def process(self, keypoints, frame, depth_frame=None, intrinsics=None, mp_features=None):
        pending_result = self._poll_pending_rep_compare()
        if pending_result is not None:
            self.csv_logger.log(pending_result)
            return pending_result

        display_rep_count = self.rep_count

        if self.session_finished:
            result = {
                "mode": "SHOULDER_FRONT_RAISE_DTW",
                "status": "session_finished",
                "feedback": "세트가 종료되었습니다.",
                "similarity": self.last_live_similarity,
                "rep_count": display_rep_count,
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
                "rep_count": display_rep_count,
                "buffer_len": len(self.buffer),
            }
            self.csv_logger.log(result)
            return result

        required_left_keys = [5, 7, 9]
        left_visible = all(
            k in keypoints
            and keypoints[k].get("x") is not None
            and keypoints[k].get("y") is not None
            for k in required_left_keys
        )
        if not left_visible:
            result = {
                "mode": "SHOULDER_FRONT_RAISE_DTW",
                "status": "waiting",
                "feedback": "왼쪽 팔이 화면에 보이도록 서주세요.",
                "similarity": self.last_live_similarity,
                "rep_count": self.rep_count,
                "buffer_len": len(self.buffer),
            }
            self.csv_logger.log(result)
            return result

        left_arm_raise = float(mp_features[2])

        # 준비 자세 체크 — is_ready 이전에는 preparing 상태 반환
        if not self.is_ready:
            if left_arm_raise <= self.down_threshold:
                self.ready_count += 1
            else:
                self.ready_count = 0

            if self.ready_count < self.ready_required_frames:
                result = {
                    "mode": "SHOULDER_FRONT_RAISE_DTW",
                    "status": "preparing",
                    "feedback": "왼팔을 내린 상태로 준비해주세요.",
                    "similarity": self.last_live_similarity,
                    "rep_count": self.rep_count,
                    "buffer_len": len(self.buffer),
                }
                self.csv_logger.log(result)
                return result
            else:
                self.is_ready = True

        # is_ready 이후: 버퍼 누적 + live DTW 유사도 계산 (매 프레임)
        current = tuple(round(v, 3) for v in mp_features)
        prev = tuple(round(v, 3) for v in self.buffer[-1]) if self.buffer else None
        if current != prev:
            self.buffer.append(mp_features)
        self._comp_buffer.append(keypoints)

        live_result = self.live_runner.tick(self.buffer)
        live_similarity = live_result["live_similarity"]
        if live_similarity is not None:
            self.last_live_similarity = live_similarity

        # DTW 피드백 생성 주석 처리 — rehab 모델이 담당
        # now_ts = time.time()
        # dt_sec = max(0.0, now_ts - self._last_obs_ts)
        # self._last_obs_ts = now_ts
        # compare_payload = {
        #     "phase": live_result.get("phase", "unknown"),
        #     "motion_similarity": live_result.get("motion_similarity"),
        #     "posture_similarity": live_result.get("posture_similarity"),
        #     "feature_errors": live_result.get("feature_errors", {}),
        #     "main_error_feature": live_result.get("main_error_feature"),
        #     "ref_progress": live_result.get("ref_progress"),
        # }
        # feedback_packet = self.feedback_router.process(self.exercise_type, compare_payload, now_ts)
        # self.session_summary.observe(self.exercise_type, feedback_packet["all_issues"], dt_sec)
        # instant_feedback = feedback_packet["feedback"] or ""

        # rep 상태 전이: down → up → down 완료 시 1회 카운트
        rep_just_finished = False
        _not_counted_feedback = None
        _not_counted_rom_pct = None
        _completed_peak_angle = 0.0
        _pain_warn = False
        if self.rep_state == "down" and left_arm_raise >= self.raise_threshold:
            self.rep_state = "up"
            self.rep_peak_angle = left_arm_raise
            self._rep_events.append({"type": "start", "t": time.time(), "rep": self.rep_count + 1})
        elif self.rep_state == "up":
            if left_arm_raise > self.rep_peak_angle:
                self.rep_peak_angle = left_arm_raise
            if left_arm_raise > self.rom_max and not self._pain_warned_this_rep:
                self._pain_warned_this_rep = True
                _pain_warn = True
            if left_arm_raise <= self.down_threshold:
                if self.rep_peak_angle >= self.min_peak_angle:
                    self.rep_count += 1
                    rep_just_finished = True
                    _completed_peak_angle = self.rep_peak_angle
                else:
                    _not_counted_rom_pct = round(self.rep_peak_angle / self.rom_max * 100, 1)
                    _not_counted_feedback = "더 올려보세요"
                    logger.info("[ROM] rep 미카운팅 — peak=%.1f° (%.1f%% of %.1f°) → 더 올려보세요",
                                self.rep_peak_angle, _not_counted_rom_pct, self.rom_max)
                self.rep_state = "down"
                self.rep_peak_angle = 0.0
                self._pain_warned_this_rep = False

        result = {
            "mode": "SHOULDER_FRONT_RAISE_DTW",
            "status": "running",
            "feedback": "",  # rehab 모델이 motion_service에서 rep 완료 시 채움
            "similarity": self.last_live_similarity,
            "cost": live_result["cost"],
            "rep_count": display_rep_count,
            "buffer_len": len(self.buffer),
            "motion_similarity": live_result.get("motion_similarity"),
            "posture_similarity": live_result.get("posture_similarity"),
            "phase": live_result.get("phase"),
        }

        if _not_counted_feedback:
            result["feedback"] = _not_counted_feedback
            result["rom_pct"] = _not_counted_rom_pct

        if _pain_warn:
            result["feedback"] = "통증이 느껴지면 여기서 멈추세요"

        if rep_just_finished:
            completed_rep = self.rep_count
            buffer_snapshot = np.array(self.buffer, dtype=np.float32, copy=True)

            arm_side = 'R' if self.mirror_input else 'L'
            _, comp_reasons = detect_compensations(self._comp_buffer, arm_side=arm_side)
            comp_feedback   = comp_reasons[0] if comp_reasons else ""
            self._comp_buffer = []

            arm_kor  = "왼팔" if not self.mirror_input else "오른팔"
            detected = comp_feedback if comp_feedback else "정상"
            try:
                _append_comp_csv(self._set_num, completed_rep, arm_kor, detected)
            except Exception as e:
                logger.warning("[Compensation] CSV 저장 실패 (무시): %s", e)
            self._rep_events.append({"type": "end", "t": time.time(), "rep": completed_rep, "label": detected, "max_angle": round(_completed_peak_angle, 2)})

            peak_pct = round(_completed_peak_angle / self.rom_max * 100, 1)
            rom_feedback = "" if peak_pct >= 80 else "조금 더 올릴 수 있어요"
            logger.info("[ROM] rep=%d peak=%.1f° (%.1f%% of %.1f°) → %s",
                        completed_rep, _completed_peak_angle, peak_pct, self.rom_max,
                        rom_feedback if rom_feedback else "피드백 없음")

            self.pending_rep_compares.append(
                (
                    DTW_COMPUTE_EXECUTOR.submit(self.dtw_engine.compare, buffer_snapshot),
                    {
                        "rep_count": completed_rep,
                        "accuracy_pct": self.last_live_similarity,
                        "similarity": self.last_live_similarity,
                        "feedback": comp_feedback,
                        "rom_feedback": rom_feedback,
                        "rom_pct": peak_pct,
                        "peak_angle": _completed_peak_angle,
                    },
                )
            )
            self.buffer = []
            self.live_runner.reset()
            result["rep_count"] = display_rep_count
            result["buffer_len"] = 0

        self.csv_logger.log(result)
        return result

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
            logger.exception("어깨 거상 rep DTW 비교가 실패했습니다.")
            compare_result = {"score": 0, "cost": None}

        self.rep_peaks.append(round(meta.get("peak_angle", 0.0), 1))

        result = {
            "mode": "SHOULDER_FRONT_RAISE_DTW",
            "status": "rep_finished",
            "feedback": meta.get("feedback", ""),
            "rom_feedback": meta.get("rom_feedback", ""),
            "rom_pct": meta.get("rom_pct"),
            "similarity": meta.get("similarity"),
            "accuracy_pct": meta.get("accuracy_pct"),
            "score": compare_result["score"],
            "final_score": compare_result["score"],
            "cost": compare_result["cost"],
            "rep_count": meta["rep_count"],
            "buffer_len": len(self.buffer),
        }
        if meta["rep_count"] >= self.target_reps:
            avg = round(sum(self.rep_peaks) / len(self.rep_peaks), 1) if self.rep_peaks else None
            result["session_finished"] = True
            result["rom"] = {
                f"shoulder_{self.side}_flexion_max": avg,
                f"shoulder_{self.side}_flexion_rep_peaks": self.rep_peaks.copy(),
            }
            self.session_finished = True
        return result

    def get_rep_events(self) -> list:
        return list(self._rep_events)


# 어깨 전방 거상 운동의 DTW 비교 엔진 클래스.
# 전문가 기준 동작 시퀀스를 불러와 정규화하고,
# 사용자 동작과 DTW 알고리즘으로 비교해 유사도 점수와 특징별 오차를 계산한다.
class ShoulderFrontRaiseLeftDTW(BaseDTW):
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
    FEATURE_WEIGHTS = (1.2, 1.5, 1.8, 1.2, 1.4, 3.24)
    MIN_BAND = 3

    def __init__(self, ref_path: str):
        self.ref_seq = self._load_reference(ref_path)
        self.feat_min, self.feat_max = self._get_minmax(self.ref_seq)
        self.ref_norm = self._normalize(self.ref_seq)

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
            "ref_window": {
                "start": best["start"],
                "end": best["end"],
            },
        }

    def compare(self, user_seq):
        user_seq = np.array(user_seq, dtype=np.float32)
        user = self._normalize(user_seq)
        dtw_result = self._dtw(self.ref_norm, user)
        if dtw_result is None:
            return {"score": 0, "cost": None}
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
