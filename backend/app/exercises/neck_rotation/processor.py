# 목 회전 운동의 실시간 DTW 분석 프로세서와 DTW 엔진을 정의하는 모듈.
# 사용자의 목 회전 동작을 프레임 단위로 수집하고, 전문가 기준 동작과 비교해
# 유사도·자세 오차·반복 횟수를 실시간으로 계산한다.
# 한 세트(목표 횟수)가 끝나면 세션 요약 피드백을 생성해 반환한다.
import csv
import time
import logging
import numpy as np
from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from app.exercises.shared.base import BaseProcessor, BaseDTW, AsyncLiveDtwRunner, DtwFrameCsvLogger, DTW_COMPUTE_EXECUTOR
from app.exercises.neck_rotation.features import get_neck_rotation_features_yolo
from app.services.feedback.realtime_feedback_router import RealTimeFeedbackRouter
from app.services.feedback.session_feedback_summary import SessionFeedbackSummary, format_top3_text
from app.exercises.shared.rom_defaults import DEFAULT_ROM

_COMP_CSV_PATH   = Path(__file__).parent / "compensation_results.csv"
_COMP_CSV_HEADER = "timestamp,set,rep,detected\n"


def _append_comp_csv(set_num: int, rep_num: int, detected: str) -> None:
    need_header = not _COMP_CSV_PATH.exists()
    with _COMP_CSV_PATH.open("a", encoding="utf-8", newline="") as f:
        if need_header:
            f.write(_COMP_CSV_HEADER)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"{ts},{set_num},{rep_num},{detected}\n")
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


# 목 회전 운동의 실시간 DTW 분석을 수행하는 프로세서 클래스.
# 프레임마다 특징값을 버퍼에 쌓고, 라이브 DTW로 유사도를 계산하며,
# 좌우 각 방향으로 회전했다가 정면으로 돌아올 때마다 1회로 카운트한다.
class NeckRotationDTWProcessor(BaseProcessor):
    # dtw_engine: 기준 동작과 비교하는 NeckRotationDTW 인스턴스.
    # target_reps: 목표 반복 횟수. 이 횟수에 도달하면 세션이 종료된다.
    def __init__(self, dtw_engine, target_reps: int = 3, rom: dict = None):
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
        self.max_trunk_rotation = 20.0

        rom = rom or DEFAULT_ROM
        self.left_max  = float(rom.get("neck_rotation_left_max",  DEFAULT_ROM["neck_rotation_left_max"]))
        self.right_max = float(rom.get("neck_rotation_right_max", DEFAULT_ROM["neck_rotation_right_max"]))
        self.turn_threshold   = 9.0
        self.center_threshold = 6.0
        # 카운팅 기준: 좌/우 각 ROM의 20% (기존 15°와 유사 수준, 어르신도 카운팅 가능)
        # 피드백 기준은 60%/80%/100%로 rep 완료 후 별도 판단
        logger.info("[NeckRotation] left_max=%.1f right_max=%.1f count_min_left=%.1f count_min_right=%.1f",
                    self.left_max, self.right_max,
                    self.left_max * 0.20, self.right_max * 0.20)
        self.target_reps = int(target_reps)
        self.feedback_router = RealTimeFeedbackRouter()
        self.session_summary = SessionFeedbackSummary()
        self.exercise_type = "neck_rotation"
        self._set_num = _next_set_number()
        self.csv_logger = DtwFrameCsvLogger(self.exercise_type)
        self.session_finished = False
        self._rep_events: list = []
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
        self.rep_left_peaks: list[float] = []
        self.rep_right_peaks: list[float] = []
        self.rep_trunk_maxes: list[float] = []
        self._current_rep_trunk_max: float = 0.0
        self._pain_warned_this_rep = False

    # 1회 동작 추적에 사용하는 내부 상태를 초기값으로 되돌린다.
    def _reset_rep_state(self):
        self.rep_phase = "idle"
        self.first_side = None
        self.first_peak_angle = 0.0
        self.second_peak_angle = 0.0
        self.rep_score_sum = 0.0
        self.rep_score_count = 0
        self.rep_avg_similarity = None
        self._current_rep_trunk_max = 0.0
        self._pain_warned_this_rep = False

    # YOLO 관절 좌표로부터 목 회전 특징값을 추출해 반환한다.
    # pts: 관절 번호 → (x, y) 좌표 딕셔너리.
    def extract_mp_features(self, pts):
        return get_neck_rotation_features_yolo(pts)

    # 매 프레임마다 호출되어 동작을 분석하고 현재 상태를 반환한다.
    # keypoints: 관절 좌표 원본 (현재 미사용, 하위 호환용).
    # frame: 영상 프레임 (현재 미사용).
    # mp_features: 이미 추출된 특징값 리스트. None이면 관절 인식 실패로 간주한다.
    # 반환값: mode·status·feedback·similarity·rep_count 등을 담은 딕셔너리.
    #         status가 'rep_finished'이면 한 회가 완료된 것이고,
    #         'session_finished'이면 전체 세트가 끝난 것이다.
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
        if self.rep_phase != "idle":
            self._current_rep_trunk_max = max(self._current_rep_trunk_max, abs(trunk_rotation))
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
            # logger.info(
            #     "[NECK AVG] accumulating | rep=%s phase=%s turn=%.2f trunk=%.2f count=%s running_avg=%.2f",
            #     self.rep_count + 1, self.rep_phase, neck_turn_angle, trunk_rotation,
            #     self.rep_score_count, self.rep_score_sum / self.rep_score_count,
            # )

        _pain_warn = False
        if self.rep_phase == "idle":
            if current_side in {"left", "right"}:
                self.first_side = current_side
                self.rep_phase = "first_turn"
                self.first_peak_angle = abs_turn_angle
                self.rep_score_sum = live_similarity or 0.0
                self.rep_score_count = 1 if live_similarity is not None else 0
                self._rep_events.append({"type": "start", "t": time.time(), "rep": self.rep_count + 1})
                logger.info(
                    "[NECK AVG] rep started | rep=%s first_side=%s turn=%.2f",
                    self.rep_count + 1,
                    self.first_side,
                    neck_turn_angle,
                )

        elif self.rep_phase == "first_turn":
            self.first_peak_angle = max(self.first_peak_angle, abs_turn_angle)
            _first_max = self.left_max if self.first_side == "left" else self.right_max
            if abs_turn_angle > _first_max and not self._pain_warned_this_rep:
                self._pain_warned_this_rep = True
                _pain_warn = True
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
            _second_max = self.right_max if self.first_side == "left" else self.left_max
            if abs_turn_angle > _second_max and not self._pain_warned_this_rep:
                self._pain_warned_this_rep = True
                _pain_warn = True
            if is_centered:
                # 좌/우 side 확인 후 각 방향 ROM 기준으로 카운팅 및 피드백 판단
                if self.first_side == "left":
                    first_max, second_max = self.left_max, self.right_max
                    first_label, second_label = "왼쪽", "오른쪽"
                else:
                    first_max, second_max = self.right_max, self.left_max
                    first_label, second_label = "오른쪽", "왼쪽"

                first_min  = first_max  * 0.20
                second_min = second_max * 0.20

                if (
                    self.first_peak_angle >= first_min
                    and self.second_peak_angle >= second_min
                ):
                    self.rep_avg_similarity = round(
                        self.rep_score_sum / self.rep_score_count, 2
                    ) if self.rep_score_count > 0 else None
                    self.rep_count += 1
                    self._rep_events.append({"type": "end", "t": time.time(), "rep": self.rep_count, "label": "정상", "max_angle": round(max(self.first_peak_angle, self.second_peak_angle), 2)})
                    try:
                        _append_comp_csv(self._set_num, self.rep_count, "정상")
                    except Exception as e:
                        logger.warning("[NeckRotation] CSV 저장 실패 (무시): %s", e)

                    first_pct  = round(self.first_peak_angle  / first_max  * 100, 1)
                    second_pct = round(self.second_peak_angle / second_max * 100, 1)

                    if first_pct >= 80 and second_pct >= 80:
                        rom_feedback = ""
                    elif first_pct < 60 and second_pct < 60:
                        rom_feedback = "양쪽 다 조금 더 돌려보세요"
                    elif first_pct < second_pct:
                        rom_feedback = f"{first_label}을 조금 더 돌려보세요"
                    else:
                        rom_feedback = f"{second_label}을 조금 더 돌려보세요"

                    logger.info("[ROM] rep=%d %s=%.1f°(%.1f%%) %s=%.1f°(%.1f%%) → %s",
                                self.rep_count,
                                first_label,  self.first_peak_angle,  first_pct,
                                second_label, self.second_peak_angle, second_pct,
                                rom_feedback if rom_feedback else "피드백 없음")

                    logger.info(
                        "[NECK AVG] rep finished | rep=%s avg_similarity=%.2f first_peak=%.2f second_peak=%.2f samples=%s",
                        self.rep_count,
                        self.rep_avg_similarity,
                        self.first_peak_angle,
                        self.second_peak_angle,
                        self.rep_score_count,
                    )
                    buffer_snapshot = np.array(self.buffer, dtype=np.float32, copy=True)
                    if self.first_side == "left":
                        _meta_peak_left = self.first_peak_angle
                        _meta_peak_right = self.second_peak_angle
                    else:
                        _meta_peak_left = self.second_peak_angle
                        _meta_peak_right = self.first_peak_angle
                    self.pending_rep_compares.append(
                        (
                            DTW_COMPUTE_EXECUTOR.submit(self.dtw_engine.compare, buffer_snapshot),
                            {
                                "rep_count": self.rep_count,
                                "avg_similarity": self.rep_avg_similarity,
                                "accuracy_pct": self.last_live_similarity,
                                "similarity": self.last_live_similarity,
                                "rom_feedback": rom_feedback,
                                "rom_pct_first": first_pct,
                                "rom_pct_second": second_pct,
                                "peak_left": round(_meta_peak_left, 1),
                                "peak_right": round(_meta_peak_right, 1),
                                "trunk_max": round(self._current_rep_trunk_max, 1),
                            },
                        )
                    )
                    self.buffer = []
                    self.live_runner.reset()
                    self._reset_rep_state()
                else:
                    first_pct  = round(self.first_peak_angle  / first_max  * 100, 1)
                    second_pct = round(self.second_peak_angle / second_max * 100, 1)
                    logger.info("[ROM] rep 미카운팅 — %s=%.1f°(%.1f%%) %s=%.1f°(%.1f%%) 카운팅 기준미달",
                                first_label,  self.first_peak_angle,  first_pct,
                                second_label, self.second_peak_angle, second_pct)
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
        if _pain_warn:
            result["feedback"] = "통증이 느껴지면 여기서 멈추세요"

        self.csv_logger.log(result)
        return result

    # 백그라운드에서 처리 중인 DTW 비교 작업이 완료됐는지 확인하고,
    # 완료된 경우 결과를 꺼내 반환한다. 아직 완료되지 않았으면 None을 반환한다.
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

        self.rep_left_peaks.append(meta.get("peak_left", 0.0))
        self.rep_right_peaks.append(meta.get("peak_right", 0.0))
        self.rep_trunk_maxes.append(meta.get("trunk_max", 0.0))

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
            avg_left = round(sum(self.rep_left_peaks) / len(self.rep_left_peaks), 1) if self.rep_left_peaks else None
            avg_right = round(sum(self.rep_right_peaks) / len(self.rep_right_peaks), 1) if self.rep_right_peaks else None
            final_summary = self.session_summary.finalize(top_k=3)
            result["session_finished"] = True
            result["session_summary"] = final_summary
            result["session_summary_lines"] = format_top3_text(final_summary)
            avg_trunk = round(sum(self.rep_trunk_maxes) / len(self.rep_trunk_maxes), 1) if self.rep_trunk_maxes else None
            result["rom"] = {
                "neck_rotation_left_max": avg_left,
                "neck_rotation_right_max": avg_right,
                "neck_rotation_left_rep_peaks": self.rep_left_peaks.copy(),
                "neck_rotation_right_rep_peaks": self.rep_right_peaks.copy(),
                "trunk_rotation_max_avg": avg_trunk,
                "trunk_rotation_rep_maxes": self.rep_trunk_maxes.copy(),
            }
            self.session_finished = True
        return result

    def get_rep_events(self) -> list:
        return list(self._rep_events)


# 목 회전 운동의 DTW 비교 엔진 클래스.
# 전문가 기준 동작 시퀀스를 불러와 정규화하고,
# 사용자 동작과 DTW 알고리즘으로 비교해 유사도 점수와 특징별 오차를 계산한다.
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

    # ref_path: 전문가 기준 동작이 저장된 CSV 파일 경로.
    def __init__(self, ref_path: str):
        self.ref_seq = self._load_reference(ref_path)
        self.feat_min, self.feat_max = self._get_minmax(self.ref_seq)
        self.ref_norm = self._normalize(self.ref_seq)

    # 사용자 동작 시퀀스를 분석해 현재 동작 단계를 추정한다.
    # user_seq: 프레임별 특징값 배열 (shape: [프레임 수, 4]).
    # 반환값: 'peak'·'center'·'turning_right'·'turning_left'·'transition' 중 하나.
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

    # 동작 단계와 기준 시퀀스 진행률에 따라 DTW 비용에 더할 패널티를 계산한다.
    # phase: 현재 추정된 동작 단계.
    # ref_progress: 기준 시퀀스에서 현재 매칭된 위치 비율 (0~1).
    # 반환값: 패널티 값 (0.0 이상의 float).
    def _phase_penalty(self, phase: str, ref_progress: float):
        if phase == "peak":
            return 0.0 if ref_progress >= 0.55 else 0.14
        if phase in {"turning_right", "turning_left"}:
            return 0.18 if ref_progress > 0.92 else 0.0
        if phase == "center":
            return 0.08 if ref_progress > 0.22 else 0.0
        return 0.0

    # DTW 매칭 경로를 따라 프레임별 오차를 집계해 특징별 평균 오차와
    # 동작·자세 비용을 계산한다.
    # ref_seq: 정규화된 기준 시퀀스 배열.
    # user_seq: 정규화된 사용자 시퀀스 배열.
    # path: DTW 매칭 경로 [(기준_인덱스, 사용자_인덱스), ...].
    # 반환값: feature_errors·motion_cost·posture_cost·main_error_feature·local_ref_progress를 담은 딕셔너리.
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

    # 1회 동작 전체 시퀀스를 기준 동작과 비교해 최종 점수를 계산한다.
    # user_seq: 한 회 동작의 프레임별 특징값 배열 또는 리스트.
    # 반환값: score·dtw_score·cost·motion_similarity·posture_similarity·
    #         phase·feature_errors·main_error_feature·ref_progress를 담은 딕셔너리.
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

    # 동작 진행 중인 부분 시퀀스로 실시간 유사도를 계산한다.
    # partial_user_seq: 현재까지 수집된 프레임별 특징값 배열 또는 리스트.
    # min_frames: 계산을 시작하기 위한 최소 프레임 수.
    # live_window: 계산에 사용할 최근 프레임 수 (오래된 프레임 제외).
    # 반환값: live_similarity·cost·motion_similarity·posture_similarity·
    #         phase·feature_errors·main_error_feature·ref_progress·ref_window를 담은 딕셔너리.
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
