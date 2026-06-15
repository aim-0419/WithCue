# 목 회전 운동 DTW 프로세서 및 DTW 엔진
import time
import logging
import numpy as np
from concurrent.futures import Future
from typing import Dict, Any, List

from app.exercises.shared.base import BaseProcessor, BaseDTW, AsyncLiveDtwRunner, DtwFrameCsvLogger, DTW_COMPUTE_EXECUTOR
from app.exercises.neck_rotation.features import get_neck_rotation_features_yolo
from app.services.feedback.realtime_feedback_router import RealTimeFeedbackRouter
from app.services.feedback.session_feedback_summary import SessionFeedbackSummary, format_top3_text

logger = logging.getLogger(__name__)


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
        self.live_runner = AsyncLiveDtwRunner(
            dtw_engine,
            live_min_frames=12,
            live_window=60,
            live_interval_sec=0.15,
            live_frame_interval=5,
            live_search_margin=14,
        )
        self.pending_rep_compares: list[tuple[Future, Dict[str, Any]]] = []

    def _reset_rep_state(self):
        self.rep_phase = "idle"
        self.first_side = None
        self.first_peak_angle = 0.0
        self.second_peak_angle = 0.0
        self.rep_score_sum = 0.0
        self.rep_score_count = 0
        self.rep_avg_similarity = None

    def extract_mp_features(self, pts):
        return get_neck_rotation_features_yolo(pts)

    def process(self, keypoints, frame, depth_frame=None, intrinsics=None, mp_features=None):
        pending_result = self._poll_pending_rep_compare()
        if pending_result is not None:
            self.csv_logger.log(pending_result)
            return pending_result
        display_rep_count = self.rep_count - len(self.pending_rep_compares)
        if self.session_finished:
            result = {
                "mode": "NECK_ROTATION_DTW",
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
                "mode": "NECK_ROTATION_DTW",
                "status": "waiting",
                "feedback": "자세를 인식 중입니다.",
                "similarity": self.last_live_similarity,
                "accuracy_pct": self.last_live_similarity,
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
                    logger.info(
                        "[NECK AVG] rep finished | rep=%s avg_similarity=%.2f first_peak=%.2f second_peak=%.2f samples=%s",
                        self.rep_count,
                        self.rep_avg_similarity,
                        self.first_peak_angle,
                        self.second_peak_angle,
                        self.rep_score_count,
                    )
                    buffer_snapshot = np.array(self.buffer, dtype=np.float32, copy=True)
                    self.pending_rep_compares.append(
                        (
                            DTW_COMPUTE_EXECUTOR.submit(self.dtw_engine.compare, buffer_snapshot),
                            {
                                "rep_count": self.rep_count,
                                "avg_similarity": self.rep_avg_similarity,
                                "accuracy_pct": self.last_live_similarity,
                                "similarity": self.last_live_similarity,
                            },
                        )
                    )
                    self.buffer = []
                    self.live_runner.reset()
                    self._reset_rep_state()
                    result = {
                        "mode": "NECK_ROTATION_DTW",
                        "status": "running",
                        "feedback": f"{self.rep_count}회 동작을 분석 중입니다.",
                        "similarity": self.last_live_similarity,
                        "accuracy_pct": self.last_live_similarity,
                        "rep_count": display_rep_count,
                        "buffer_len": 0,
                    }
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
            "rep_count": display_rep_count,
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
            logger.exception("목 회전 rep DTW 비교가 실패했습니다.")
            compare_result = {"score": 0, "dtw_score": 0, "cost": None}

        result = {
            "mode": "NECK_ROTATION_DTW",
            "status": "rep_finished",
            "feedback": f"{meta['rep_count']}회 수행 완료",
            "similarity": meta.get("similarity"),
            "accuracy_pct": meta.get("accuracy_pct"),
            "avg_similarity": meta.get("avg_similarity"),
            "score": compare_result.get("score"),
            "dtw_score": compare_result.get("dtw_score"),
            "final_score": compare_result.get("score"),
            "cost": compare_result.get("cost"),
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


class NeckRotationDTW(BaseDTW):
    FEATURE_NAMES = (
        "trunk_rotation",
        "neck_turn_angle",
        "head_tilt",
        "shoulder_line_angle",
    )
    MOTION_INDEXES = (1,)
    POSTURE_INDEXES = (0, 2, 3)
    FEATURE_WEIGHTS = (2.6, 2.2, 2.8, 1.4)
    MIN_BAND = 3

    def __init__(self, ref_path: str):
        self.ref_seq = self._load_reference(ref_path)
        self.feat_min, self.feat_max = self._get_minmax(self.ref_seq)
        self.ref_norm = self._normalize(self.ref_seq)

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

    def compare(self, user_seq):
        user_seq = np.array(user_seq, dtype=np.float32)
        user = self._normalize(user_seq)
        dtw_result = self._dtw(self.ref_norm, user)
        if dtw_result is None:
            return {"score": 0, "dtw_score": 0, "cost": None}
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
            "ref_window": {
                "start": best["start"],
                "end": best["end"],
            },
        }
