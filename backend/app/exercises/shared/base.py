# 프로세서 패키지의 공유 기반 클래스 및 모듈 수준 리소스.
# 카메라로 받은 자세 데이터를 매 프레임 처리하는 '프로세서'의 공통 인터페이스(BaseProcessor),
# DTW(동적 시간 왜곡) 알고리즘을 비동기로 실행하는 러너(AsyncLiveDtwRunner),
# DTW 계산 결과를 CSV 파일로 기록하는 로거(DtwFrameCsvLogger)를 정의한다.
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

# 로그 경로를 현재 프로젝트(backend/logs) 기준으로 계산한다. (구버전 v1.0 절대경로 하드코딩 제거)
NECK_ROM_LOG_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "logs")
)
DTW_FRAME_LOG_PATH = os.path.join(NECK_ROM_LOG_DIR, "dtw_frame_feedback_log.csv")
# DTW 계산 전용 스레드 풀 (CPU 집약 작업)
DTW_COMPUTE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="dtw_compute")
# DTW 결과 파일 기록 전용 스레드 풀 (I/O 작업)
DTW_IO_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dtw_io")

logger = logging.getLogger(__name__)


# DTW 결과가 아직 없을 때 반환하는 빈 결과 딕셔너리를 만든다.
# 각 필드의 기본값은 None 또는 "unknown"으로 설정된다.
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


# DTW 계산을 별도 스레드에서 비동기로 실행하고, 매 프레임마다 최신 결과를 반환하는 클래스.
# 계산이 끝나기 전에는 이전 결과를 그대로 유지해 화면이 멈추지 않도록 한다.
class AsyncLiveDtwRunner:
    # dtw_engine: 실제 DTW 계산을 담당하는 객체.
    # live_min_frames: DTW 계산을 시작하기 위한 최소 프레임 수.
    # live_window: DTW 슬라이딩 윈도우 크기.
    # live_interval_sec: 새 계산을 제출할 최소 시간 간격(초).
    # live_frame_interval: 몇 프레임마다 계산을 제출할지 결정하는 간격.
    # live_search_margin: DTW 탐색 여유 범위.
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

    # 이전에 제출한 비동기 계산이 완료됐으면 결과를 가져와 _last_result에 저장한다.
    # 완료되지 않았거나 아직 제출하지 않은 경우에는 아무것도 하지 않는다.
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

    # 매 프레임마다 호출되어 DTW 계산 제출 여부를 결정하고 최신 결과를 반환한다.
    # sequence: 지금까지 누적된 자세 특징값 리스트.
    # 반환값: 최신 DTW 결과 딕셔너리 (계산 중이면 이전 결과를 그대로 반환).
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

    # 러너의 모든 내부 상태를 초기화한다.
    # 운동 세션을 새로 시작할 때 호출한다.
    def reset(self) -> None:
        self._future = None
        self._last_result = _empty_live_result()
        self._last_submitted_at = 0.0
        self._frame_counter = 0


# 매 프레임의 DTW 계산 결과를 CSV 파일에 기록하는 로거 클래스.
# 모든 프레임을 기록하면 용량이 커지므로, 중요한 상태 변화나 일정 간격 프레임만 샘플링해 저장한다.
# 파일 쓰기는 별도 스레드에서 비동기로 처리해 메인 처리 루프가 느려지지 않도록 한다.
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

    # exercise_type: 운동 종류 이름 (예: "squat").
    # path: CSV 로그 파일 경로.
    # sample_every: 몇 프레임마다 한 번씩 기록할지 결정하는 샘플링 간격.
    # async_enabled: True이면 파일 쓰기를 별도 스레드에서 비동기로 처리한다.
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

    # 기존 CSV 파일의 헤더(컬럼 구조)가 현재 정의와 다르면, 파일을 백업하고 새로 시작한다.
    # 컬럼 구조가 변경됐을 때 데이터 불일치가 발생하는 것을 방지한다.
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

    # 하나의 프레임 데이터를 받아 CSV에 기록할지 여부를 판단하고 기록한다.
    # payload: 기록할 프레임 정보 딕셔너리 (유사도, 피드백, 상태 등 포함).
    # 중요한 상태(rep_finished, session_finished, error 등)는 반드시 기록하고,
    # 그 외에는 sample_every 간격이나 상태 변화 시에만 기록한다.
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

    # 실제로 CSV 파일에 한 행을 추가한다.
    # 파일이 없거나 비어 있으면 헤더를 먼저 쓴 뒤 데이터를 추가한다.
    # 여러 스레드가 동시에 쓰지 않도록 WRITE_LOCK으로 보호한다.
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


# 측정 프로세서(MeasurementProcessor)와 코칭 프로세서(CoachingProcessor)가
# 반드시 구현해야 하는 공통 인터페이스를 정의하는 추상 기반 클래스.
class BaseProcessor(ABC):
    @abstractmethod
    def process(self, keypoints: Dict, frame: np.ndarray, depth_frame=None, intrinsics=None, mp_features=None) -> Dict[str, Any]:
        # [핵심] Measurement/Coaching 프로세서 공통 인터페이스
        pass

    def extract_mp_features(self, pts):
        # DTW 프로세서만 실제 feature를 추출하며, 나머지는 None 반환으로 건너뜀
        return None


# DTW 알고리즘 구현에 필요한 공통 메서드(참조 동작 로드, 정규화, 거리 계산, DTW 경로 탐색)를
# 묶어 둔 기반 클래스. 실제 운동별 DTW 클래스는 이 클래스를 상속해 사용한다.
class BaseDTW:
    # JSON 파일에서 참조 동작 시퀀스를 불러와 numpy 배열로 반환한다.
    # path: 참조 동작이 저장된 JSON 파일 경로.
    def _load_reference(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return np.array(data["sequence"], dtype=np.float32)

    # 시퀀스 전체의 최솟값과 최댓값을 계산해 반환한다.
    # 반환값: (최솟값 배열, 최댓값 배열).
    def _get_minmax(self, seq: np.ndarray):
        return seq.min(axis=0), seq.max(axis=0)

    # 시퀀스 값을 0~1 범위로 정규화한다.
    # feat_min, feat_max는 미리 계산된 참조 동작의 최솟값/최댓값이다.
    def _normalize(self, seq: np.ndarray):
        denom = np.maximum(self.feat_max - self.feat_min, 1e-6)
        return (seq - self.feat_min) / denom

    # 두 프레임 사이의 특징별 오차 벡터를 계산한다.
    # 각 특징에 FEATURE_WEIGHTS를 곱해 중요도를 반영한다.
    # a, b: 비교할 두 프레임의 특징값 배열.
    def _frame_error_vector(self, a: np.ndarray, b: np.ndarray):
        weights = np.array(self.FEATURE_WEIGHTS, dtype=np.float32)
        return np.abs(a - b) * weights

    # 두 프레임 사이의 가중 유클리드 거리를 계산한다.
    # 반환값: 두 프레임의 유사도 차이를 나타내는 스칼라 값.
    def _frame_dist(self, a: np.ndarray, b: np.ndarray):
        return float(np.linalg.norm(self._frame_error_vector(a, b)))

    # DTW(동적 시간 왜곡) 알고리즘으로 두 시퀀스의 최적 정렬 경로와 비용을 계산한다.
    # seq1, seq2: 비교할 두 자세 시퀀스.
    # band_ratio: 탐색 범위를 전체 시퀀스 길이의 몇 분의 1로 제한할지 결정하는 비율.
    # 반환값: 총 비용, 정규화 비용, 정렬 경로를 담은 딕셔너리. 경로를 찾지 못하면 None.
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
