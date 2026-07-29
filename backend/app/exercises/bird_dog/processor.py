# 버드독 운동 DTW 프로세서 및 DTW 엔진.
# 카메라 프레임마다 관절 feature를 받아 기준 동작과 실시간 비교(DTW)하고,
# 반복 횟수(rep)를 카운트하며 피드백을 생성한다.
# BirdDogDTWProcessor: 프레임 단위로 동작을 처리하는 메인 프로세서.
# BirdDogDTW: DTW 알고리즘으로 사용자 동작과 기준 동작을 수치 비교하는 엔진.
import time
import logging
import numpy as np
from concurrent.futures import Future
from typing import Dict, Any, List

from app.exercises.shared.base import BaseProcessor, BaseDTW, AsyncLiveDtwRunner, DtwFrameCsvLogger, DTW_COMPUTE_EXECUTOR
from app.exercises.bird_dog.features import get_bird_dog_features_yolo
from app.services.feedback.realtime_feedback_router import RealTimeFeedbackRouter
from app.services.feedback.session_feedback_summary import SessionFeedbackSummary, format_top3_text

logger = logging.getLogger(__name__)


# 버드독 운동의 프레임별 처리를 담당하는 프로세서 클래스.
# 매 프레임마다 관절 좌표를 받아 feature를 추출하고, 실시간 DTW 유사도를 계산하며,
# 동작 신호를 감지해 rep 완료를 판단한다. 세션이 끝나면 전체 요약 피드백을 생성한다.
class BirdDogDTWProcessor(BaseProcessor):
    # DTW 엔진과 목표 반복 횟수를 받아 프로세서를 초기화한다.
    # dtw_engine: BirdDogDTW 인스턴스
    # target_reps: 목표 반복 횟수 (기본값 3회)
    def __init__(self, dtw_engine, target_reps: int = 3):
        self.dtw_engine = dtw_engine
        self.buffer = []
        self.prev_signal = None
        self.state = "idle"
        self.peak_count = 0
        self.rep_index = 0
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
        self.live_runner = AsyncLiveDtwRunner(
            dtw_engine,
            live_min_frames=12,
            live_window=30,
            live_interval_sec=0.12,
            live_frame_interval=4,
            live_search_margin=12,
        )
        self.pending_rep_compares: list[tuple[Future, Dict[str, Any]]] = []

    # YOLO 관절 좌표를 받아 버드독 feature 벡터를 추출해 반환한다.
    # pts: YOLO 관절 좌표 딕셔너리
    def extract_mp_features(self, pts):
        return get_bird_dog_features_yolo(pts)

    # feature 벡터에서 동작 강도를 나타내는 단일 신호값을 계산한다.
    # feat: feature 리스트 (index 2~5가 팔/다리 각도)
    # 반환: 오른팔-왼다리 합 또는 왼팔-오른다리 합 중 더 큰 값
    def _get_signal(self, feat):
        right_arm = feat[2]
        left_leg = feat[3]
        left_arm = feat[4]
        right_leg = feat[5]
        return max(right_arm + left_leg, left_arm + right_leg)

    # 매 프레임마다 호출되는 메인 처리 함수.
    # 관절 좌표와 feature를 받아 실시간 유사도 계산, rep 카운트, 피드백 생성을 수행한다.
    # keypoints: 관절 좌표 딕셔너리
    # frame: 현재 카메라 프레임 이미지
    # mp_features: 미리 추출된 feature 벡터 (없으면 None)
    # 반환: 현재 상태, 피드백, 유사도 등을 담은 딕셔너리
    def process(self, keypoints, frame, depth_frame=None, intrinsics=None, mp_features=None):
        pending_result = self._poll_pending_rep_compare()
        if pending_result is not None:
            self.csv_logger.log(pending_result)
            return pending_result
        display_rep_count = self.rep_index - len(self.pending_rep_compares)
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

        live_result = self.live_runner.tick(self.buffer)
        live_similarity = live_result["live_similarity"]
        if live_similarity is not None:
            self.last_live_similarity = live_similarity

        now_ts = time.time()
        dt_sec = max(0.0, now_ts - self._last_obs_ts)
        self._last_obs_ts = now_ts
        compare_payload = None
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

        if self.peak_count >= 2 and len(self.buffer) > 15:
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
            buffer_snapshot = np.array(self.buffer, dtype=np.float32, copy=True)
            self.pending_rep_compares.append(
                (
                    DTW_COMPUTE_EXECUTOR.submit(self.dtw_engine.compare, buffer_snapshot),
                    {
                        "rep_count": self.rep_index + 1,
                        "avg_similarity": self.rep_avg_similarity,
                        "accuracy_pct": self.last_live_similarity,
                        "similarity": self.last_live_similarity,
                    },
                )
            )

            self.buffer = []
            self.prev_signal = None
            self.state = "idle"
            self.peak_count = 0
            self.rep_score_sum = 0.0
            self.rep_score_count = 0
            self.motion_started = False
            self.live_runner.reset()
            result = {
                "mode": "BIRD_DOG_DTW",
                "status": "running",
                "rep_count": self.rep_index,
                "feedback": f"{self.rep_index + 1}회 동작을 분석 중입니다.",
                "accuracy_pct": self.last_live_similarity,
                "similarity": self.last_live_similarity,
                "buffer_len": 0,
            }
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
            logger.exception("버드독 rep DTW 비교가 실패했습니다.")
            compare_result = {"score": 0, "cost": None}

        self.rep_index += 1
        result = {
            "mode": "BIRD_DOG_DTW",
            "status": "rep_finished",
            "rep_count": self.rep_index,
            "score": compare_result["score"],
            "accuracy_pct": meta.get("accuracy_pct"),
            "similarity": meta.get("similarity"),
            "avg_similarity": meta.get("avg_similarity"),
            "final_score": compare_result["score"],
            "cost": compare_result["cost"],
            "feedback": f"{self.rep_index}회 수행 완료",
            "buffer_len": len(self.buffer),
        }
        if self.rep_index >= self.target_reps:
            final_summary = self.session_summary.finalize(top_k=3)
            result["session_finished"] = True
            result["session_summary"] = final_summary
            result["session_summary_lines"] = format_top3_text(final_summary)
            self.session_finished = True
        return result


# 버드독 운동의 DTW 비교 엔진 클래스.
# 미리 저장된 기준 동작(레퍼런스 시퀀스)과 사용자 동작을 DTW 알고리즘으로 비교해
# 유사도 점수와 관절별 오차를 계산한다. 좌우 방향 자동 대칭 처리도 지원한다.
class BirdDogDTW(BaseDTW):
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
    FEATURE_WEIGHTS = (0.8, 0.8, 1.3, 1.3, 1.3, 1.3, 1.1, 1.1, 1.1, 1.1, 1.3, 1.3, 1.3, 1.3)
    MIN_BAND = 4

    # 기준 동작 파일 경로를 받아 DTW 엔진을 초기화한다.
    # ref_path: 기준 동작 feature 시퀀스가 저장된 파일 경로 (CSV 또는 npy)
    def __init__(self, ref_path: str):
        self.ref_seq = self._load_reference(ref_path)
        self.feat_min, self.feat_max = self._get_minmax(self.ref_seq)
        self.ref_norm = self._normalize(self.ref_seq)
        self.ref_signal = self._motion_signal(self.ref_seq)

    # feature 시퀀스에서 각 프레임의 팔/다리 동작 강도 신호를 계산한다.
    # seq: feature 시퀀스 배열 (N x 14)
    # 반환: 각 프레임의 동작 강도를 나타내는 1차원 배열
    def _motion_signal(self, seq: np.ndarray):
        if len(seq) == 0:
            return np.array([], dtype=np.float32)
        return np.maximum(seq[:, 2] + seq[:, 3], seq[:, 4] + seq[:, 5])

    # 최근 사용자 시퀀스를 분석해 현재 동작 단계(올리는 중, 정점, 내리는 중 등)와
    # 어느 쌍(오른팔-왼다리 또는 왼팔-오른다리)을 사용 중인지 판단한다.
    # user_seq: 사용자 feature 시퀀스 배열
    # 반환: (phase 문자열, direction 문자열) 튜플
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

    # 현재 동작 단계와 기준 동작 진행도에 따라 유사도 페널티 값을 반환한다.
    # phase: 현재 동작 단계 문자열 ("peak", "raising", "lowering", "ready" 등)
    # ref_progress: 기준 동작에서의 현재 진행 비율 (0.0~1.0)
    # 반환: 페널티 값 (0.0이면 페널티 없음)
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

    # feature 시퀀스의 팔/다리 좌우를 반전시킨 복사본을 반환한다.
    # 좌우 반전은 "오른팔-왼다리" 패턴과 "왼팔-오른다리" 패턴 중 더 유사한 것을 선택하기 위해 사용된다.
    # seq: 원본 feature 시퀀스 배열
    # 반환: 좌우가 교환된 feature 시퀀스 배열
    def _flip_left_right(self, seq: np.ndarray):
        flipped = seq.copy()
        flipped[:, 2], flipped[:, 4] = seq[:, 4], seq[:, 2]
        flipped[:, 3], flipped[:, 5] = seq[:, 5], seq[:, 3]
        flipped[:, 6], flipped[:, 8] = seq[:, 8], seq[:, 6]
        flipped[:, 7], flipped[:, 9] = seq[:, 9], seq[:, 7]
        flipped[:, 10], flipped[:, 11] = seq[:, 11], seq[:, 10]
        flipped[:, 12], flipped[:, 13] = seq[:, 13], seq[:, 12]
        return flipped

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

    # 동작 중 실시간으로 현재까지의 시퀀스와 기준 동작을 DTW로 비교해 유사도를 반환한다.
    # partial_user_seq: 현재까지 수집된 사용자 feature 시퀀스
    # min_frames: 비교를 시작하기 위한 최소 프레임 수
    # live_window: 가장 최근 몇 프레임을 슬라이딩 윈도우로 사용할지
    # 반환: 실시간 유사도, 동작/자세 유사도, 관절별 오차, 동작 단계 등을 담은 딕셔너리
    def get_live_similarity(
        self,
        partial_user_seq,
        min_frames: int = 12,
        live_window: int = 30,
        search_hint: Dict[str, Any] | None = None,
        search_margin: int | None = None,
    ):
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
        phase, direction = self._estimate_phase(live_seq)
        best = None
        for direction_used, ref_raw in (
            ("original", self.ref_seq),
            ("flipped", self._flip_left_right(self.ref_seq)),
        ):
            ref_norm = self._normalize(ref_raw)
            ref_partial = ref_norm[: max(min_frames, min(len(ref_norm), len(user)))]
            dtw_result = self._dtw(ref_partial, user)
            if dtw_result is None:
                continue
            metrics = self._compute_path_metrics(ref_partial, user, dtw_result["path"])
            candidate = {
                "phase": phase,
                "direction": direction,
                "direction_used": direction_used,
                "start": 0,
                "end": len(ref_partial),
                "norm_cost": dtw_result["norm_cost"],
                "total_cost": dtw_result["total_cost"],
                "path": dtw_result["path"],
                "ref_progress": metrics["local_ref_progress"],
                **metrics,
            }
            if best is None or candidate["norm_cost"] < best["norm_cost"]:
                best = candidate
        if best is None:
            return {
                "live_similarity": None,
                "cost": None,
                "direction_used": None,
                "motion_similarity": None,
                "posture_similarity": None,
                "phase": phase,
                "feature_errors": {},
                "main_error_feature": None,
                "ref_progress": None,
                "ref_window": None,
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
        phase, direction = self._estimate_phase(user_seq)
        best = None
        for direction_used, ref_raw in (
            ("original", self.ref_seq),
            ("flipped", self._flip_left_right(self.ref_seq)),
        ):
            ref_norm = self._normalize(ref_raw)
            dtw_result = self._dtw(ref_norm, user)
            if dtw_result is None:
                continue
            metrics = self._compute_path_metrics(ref_norm, user, dtw_result["path"])
            candidate = {
                "phase": phase,
                "direction": direction,
                "direction_used": direction_used,
                "start": 0,
                "end": len(ref_norm),
                "norm_cost": dtw_result["norm_cost"],
                "total_cost": dtw_result["total_cost"],
                "path": dtw_result["path"],
                "ref_progress": metrics["local_ref_progress"],
                **metrics,
            }
            if best is None or candidate["norm_cost"] < best["norm_cost"]:
                best = candidate
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
