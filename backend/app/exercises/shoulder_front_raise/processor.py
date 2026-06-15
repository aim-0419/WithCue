# 어깨 전방 거상 운동 DTW 프로세서 및 DTW 엔진
import time
import logging
import numpy as np
from concurrent.futures import Future
from typing import Dict, Any, List

from app.exercises.shared.base import BaseProcessor, BaseDTW, AsyncLiveDtwRunner, DtwFrameCsvLogger, DTW_COMPUTE_EXECUTOR
from app.exercises.shoulder_front_raise.features import get_shoulder_front_raise_left_features_yolo
from app.services.feedback.realtime_feedback_router import RealTimeFeedbackRouter
from app.services.feedback.session_feedback_summary import SessionFeedbackSummary, format_top3_text

logger = logging.getLogger(__name__)


class ShoulderFrontRaiseLeftDTWProcessor(BaseProcessor):
    def __init__(self, dtw_engine, mirror_input: bool = False, target_reps: int = 3):
        self.dtw_engine = dtw_engine
        self.buffer = []
        self.last_live_similarity = None
        self.mirror_input = mirror_input
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
        self.live_runner = AsyncLiveDtwRunner(
            dtw_engine,
            live_min_frames=10,
            live_window=30,
            live_interval_sec=0.12,
            live_frame_interval=4,
            live_search_margin=10,
        )
        self.pending_rep_compares: list[tuple[Future, Dict[str, Any]]] = []

    def extract_mp_features(self, pts):
        return get_shoulder_front_raise_left_features_yolo(pts)

    def process(self, keypoints, frame, depth_frame=None, intrinsics=None, mp_features=None):
        pending_result = self._poll_pending_rep_compare()
        if pending_result is not None:
            self.csv_logger.log(pending_result)
            return pending_result
        display_rep_count = self.rep_count - len(self.pending_rep_compares)
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
            "status": "running",
            "feedback": instant_feedback,
            "similarity": self.last_live_similarity,
            "cost": live_result["cost"],
            "rep_count": display_rep_count,
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
        if rep_just_finished:
            completed_rep = self.rep_count
            buffer_snapshot = np.array(self.buffer, dtype=np.float32, copy=True)
            self.pending_rep_compares.append(
                (
                    DTW_COMPUTE_EXECUTOR.submit(self.dtw_engine.compare, buffer_snapshot),
                    {
                        "rep_count": completed_rep,
                        "accuracy_pct": self.last_live_similarity,
                        "similarity": self.last_live_similarity,
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

        result = {
            "mode": "SHOULDER_FRONT_RAISE_DTW",
            "status": "rep_finished",
            "feedback": f"{meta['rep_count']}회 수행 완료",
            "similarity": meta.get("similarity"),
            "accuracy_pct": meta.get("accuracy_pct"),
            "score": compare_result["score"],
            "final_score": compare_result["score"],
            "cost": compare_result["cost"],
            "rep_count": meta["rep_count"],
            "buffer_len": len(self.buffer),
        }
        if meta["rep_count"] >= self.target_reps:
            final_summary = self.session_summary.finalize(top_k=3)
            result["session_finished"] = True
            result["session_summary"] = final_summary
            result["session_summary_lines"] = format_top3_text(final_summary)
            self.session_finished = True
        return result


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
    FEATURE_WEIGHTS = (1.2, 1.5, 1.8, 1.2, 1.4, 3.24)  # 마지막 값은 1.8 * 1.8
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
