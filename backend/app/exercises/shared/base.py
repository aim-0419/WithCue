# 프로세서 패키지의 공유 기반 클래스 및 모듈 수준 리소스
import time
import logging
import os
import csv
import threading
import json
import numpy as np
from abc import ABC, abstractmethod
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Dict, Any, List

NECK_ROM_LOG_DIR = "/home/aim0419/withcue_v1.0/backend/logs"
DTW_FRAME_LOG_PATH = os.path.join(NECK_ROM_LOG_DIR, "dtw_frame_feedback_log.csv")
DTW_COMPUTE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dtw_compute")
DTW_IO_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dtw_io")

logger = logging.getLogger(__name__)


def _empty_live_result() -> Dict[str, Any]:
    return {
        "live_similarity": None,
        "cost": None,
        "motion_similarity": None,
        "posture_similarity": None,
        "phase": "unknown",
        "feature_errors": {},
        "main_error_feature": None,
        "ref_progress": None,
        "ref_window": None,
    }


class AsyncLiveDtwRunner:
    def __init__(
        self,
        dtw_engine,
        *,
        live_min_frames: int,
        live_window: int,
        live_interval_sec: float = 0.12,
        live_frame_interval: int = 4,
        live_search_margin: int = 12,
    ):
        self.dtw_engine = dtw_engine
        self.live_min_frames = int(live_min_frames)
        self.live_window = int(live_window)
        self.live_interval_sec = float(live_interval_sec)
        self.live_frame_interval = max(1, int(live_frame_interval))
        self.live_search_margin = max(4, int(live_search_margin))
        self._future: Future | None = None
        self._last_result: Dict[str, Any] = _empty_live_result()
        self._last_submitted_at = 0.0
        self._frame_counter = 0

    def _consume_future(self) -> None:
        if self._future is None or not self._future.done():
            return
        try:
            result = self._future.result()
            if isinstance(result, dict):
                self._last_result = result
        except Exception:
            logger.exception("비동기 live DTW 계산이 실패했습니다.")
        finally:
            self._future = None

    def tick(self, sequence: List[Any]) -> Dict[str, Any]:
        self._consume_future()
        self._frame_counter += 1
        seq_len = len(sequence)
        if seq_len < self.live_min_frames:
            self._last_result = _empty_live_result()
            return self._last_result

        now = time.monotonic()
        should_submit = (
            self._future is None
            and (
                self._frame_counter % self.live_frame_interval == 0
                or (now - self._last_submitted_at) >= self.live_interval_sec
            )
        )
        if should_submit:
            seq_snapshot = np.array(sequence, dtype=np.float32, copy=True)
            hint = self._last_result.get("ref_window") if isinstance(self._last_result, dict) else None
            self._future = DTW_COMPUTE_EXECUTOR.submit(
                self.dtw_engine.get_live_similarity,
                seq_snapshot,
                self.live_min_frames,
                self.live_window,
                hint,
                self.live_search_margin,
            )
            self._last_submitted_at = now
        return self._last_result

    def reset(self) -> None:
        self._future = None
        self._last_result = _empty_live_result()
        self._last_submitted_at = 0.0
        self._frame_counter = 0


class DtwFrameCsvLogger:
    WRITE_LOCK = threading.Lock()
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

    def __init__(
        self,
        exercise_type: str,
        path: str = DTW_FRAME_LOG_PATH,
        *,
        sample_every: int = 15,
        async_enabled: bool = True,
    ):
        self.exercise_type = str(exercise_type)
        self.path = path
        self.sample_every = max(1, int(sample_every))
        self.async_enabled = bool(async_enabled)
        self.session_id = (
            f"{self.exercise_type}_{time.strftime('%Y%m%d_%H%M%S')}_"
            f"{int((time.time() % 1) * 1000):03d}"
        )
        self.frame_index = 0
        self._last_status = None
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

        backup_path = f"{self.path}.bak_{time.strftime('%Y%m%d_%H%M%S')}"
        os.replace(self.path, backup_path)

    def log(self, payload: Dict[str, Any]) -> None:
        self.frame_index += 1
        status = str(payload.get("status") or "")
        is_important = status in {
            "rep_finished",
            "session_finished",
            "finished",
            "error",
            "camera_unavailable",
        }
        should_sample = (
            self.frame_index % self.sample_every == 0
            or status != self._last_status
            or is_important
        )
        self._last_status = status
        if not should_sample:
            return

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
        if self.async_enabled:
            DTW_IO_EXECUTOR.submit(self._write_row, row)
        else:
            self._write_row(row)

    def _write_row(self, row: Dict[str, Any]) -> None:
        try:
            with self.WRITE_LOCK:
                file_exists = os.path.exists(self.path)
                needs_header = (not file_exists) or os.path.getsize(self.path) == 0
                with open(self.path, "a", newline="", encoding="utf-8-sig") as fp:
                    writer = csv.DictWriter(fp, fieldnames=self.FIELDNAMES)
                    if needs_header:
                        writer.writeheader()
                    writer.writerow(row)
        except Exception:
            logger.exception("DTW CSV 로그 쓰기에 실패했습니다.")


class BaseProcessor(ABC):
    @abstractmethod
    def process(self, keypoints: Dict, frame: np.ndarray, depth_frame=None, intrinsics=None, mp_features=None) -> Dict[str, Any]:
        # [핵심] Measurement/Coaching 프로세서 공통 인터페이스
        pass


class BaseDTW:
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
        weights = np.array(self.FEATURE_WEIGHTS, dtype=np.float32)
        return np.abs(a - b) * weights

    def _frame_dist(self, a: np.ndarray, b: np.ndarray):
        return float(np.linalg.norm(self._frame_error_vector(a, b)))

    def _dtw(self, seq1: np.ndarray, seq2: np.ndarray, band_ratio: float = 0.3):
        n, m = len(seq1), len(seq2)
        dp = np.full((n + 1, m + 1), np.inf, dtype=np.float32)
        dp[0, 0] = 0.0
        band = max(self.MIN_BAND, int(max(n, m) * band_ratio))

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
