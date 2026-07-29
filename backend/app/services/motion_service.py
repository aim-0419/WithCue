# 카메라 영상에서 YOLO로 관절을 감지하고, 운동 판단 로직을 실행한 뒤
# 결과를 WebSocket으로 프론트엔드에 실시간 전송하는 핵심 서비스 모듈.
# 운동 중 영상과 관절 특징값을 파일로 녹화하는 기능도 함께 담당합니다.

import asyncio
import base64
import copy
import cv2
import json
import logging
import math
import os
import queue
import threading
import time
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.core.monitor import SystemMonitor
from app.hardware.camera import camera_manager
from app.core.utils import extract_keypoints
from app.core.depth_estimator import DepthEstimator
from app.exercises.shared.base import BaseProcessor
from app.exercises.shared.common import KalmanKeypointSmoother

STREAM_FRAME_W = 640    # WebSocket 전송 및 YOLO 추론 해상도
STREAM_FRAME_H = 360
CAMERA_FRAME_W = 1280   # 카메라 캡처 및 영상 녹화 해상도
CAMERA_FRAME_H = 720
CAMERA_INIT_TIMEOUT_SECONDS = 15.0
EMPTY_FRAME_RETRY_LIMIT = 15
# [핵심] 스트리밍 해상도 상수화: 프론트 렌더링/성능 튜닝 시 한 곳에서 조절
logger = logging.getLogger(__name__)

# - 카메라 프레임 받기
# - YOLO 추론
# - MediaPipe feature 추출
# - processor 호출 + 전송

# WebSocket 연결 하나를 담당하는 모션 처리 서비스 클래스.
# 카메라 시작부터 프레임 처리, 운동 판단, 전송, 녹화, 종료까지 전 과정을 관리합니다.
class MotionService:
    # WebSocket 연결과 YOLO 모델 인스턴스를 받아 서비스를 초기화합니다.
    # 녹화 파일은 public/recordings, 관절 특징값은 public/features 디렉토리에 저장됩니다.
    # 매개변수: ws - 클라이언트 WebSocket 연결 / yolo - 초기화된 YOLODetector 인스턴스
    #           user_id - WS 토큰으로 확인된 사용자 ID(비로그인/토큰무효 시 None)
    #           exercise_code - 운동/검사 식별 문자열(세션 결과 DB 적재 시 사용, Phase 1)
    def __init__(self, ws: WebSocket, yolo, user_id: int | None = None, exercise_code: str | None = None):
        self.ws = ws
        self.yolo = yolo
        self.user_id = user_id
        self.exercise_code = exercise_code
        self.running = False
        self.processor: BaseProcessor = None
        self.monitor = SystemMonitor()
        self.conn_id = id(ws)
        self.recording_active = False
        self.record_video_path = None
        self.record_features_path = None
        self.record_features = []
        self.video_writer = None
        self.record_queue = None
        self.record_worker = None
        self.record_drop_count = 0
        self.depth_estimator = DepthEstimator()
        self.kalman = KalmanKeypointSmoother()
        self._last_pts_3d: dict | None = None
        self.public_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "public"))
        self.recordings_dir = os.path.join(self.public_dir, "recordings")
        self.features_dir = os.path.join(self.public_dir, "features")
        self.metrics_dir = os.path.join(self.public_dir, "metrics")
        os.makedirs(self.recordings_dir, exist_ok=True)
        os.makedirs(self.features_dir, exist_ok=True)
        os.makedirs(self.metrics_dir, exist_ok=True)
        # 세션 성능/유사도 계측 버퍼: 프레임마다 처리시간·추론시간·유사도를 쌓아 종료 시 통계로 저장한다.
        self._frame_metrics: list[dict] = []
        self._session_start_time: float | None = None
        self._recording_start_time: float | None = None
        self._session_finished_at: float | None = None  # session_finished 감지 시각
        self._CLIP_TAIL_SEC = 2.0                        # 마지막 rep 후 추가 녹화 시간
        self._rom_saved = False                          # ROM 측정 결과 파일 저장 여부 (세션당 1회)
        self._last_rom: dict | None = None               # 검사 세션에서 측정된 rom dict (세션 종료 시 DB 적재용)
        self._pending_phase: str | None = None           # 프론트에서 수신한 phase 신호 (메인 루프에서 처리)

    # 운동별 처리 로직(프로세서)을 주입합니다.
    # 매개변수: processor - BaseProcessor를 상속한 운동별 처리 객체
    def set_processor(self, processor: BaseProcessor):
        self.processor = processor

    # 프론트에서 보내는 WebSocket 텍스트 메시지(phase 신호)를 백그라운드에서 수신한다.
    async def _recv_client_messages(self):
        try:
            while True:
                raw = await self.ws.receive_text()
                try:
                    msg = json.loads(raw)
                    if msg.get("type") == "phase":
                        self._pending_phase = msg.get("phase", "")
                        logger.info("[Phase] 수신: %s", self._pending_phase)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

    # WebSocket을 수락하고 카메라를 켠 뒤 메인 처리 루프를 시작합니다.
    # 카메라 초기화 실패 또는 연결 종료 시 자원을 정리하고 종료합니다.
    async def start(self):
        await self.ws.accept()
        try:
            logger.info("카메라 시작을 요청했습니다. conn=%s", self.conn_id)
            camera_manager.start()
        except Exception as e:
            logger.warning("카메라 시작에 실패했습니다: %s conn=%s", e, self.conn_id)
            await self._send_status_only(
                {
                    "mode": "ERROR",
                    "status": "camera_unavailable",
                    "message": str(e),
                    "feedback": "카메라를 시작하지 못했습니다.",
                    "keypoints": {},
                }
            )
            await self.ws.close(code=1011, reason="camera_start_failed")
            return

        self.running = True
        logger.info(
            "모션 서비스가 시작되었습니다: %s | user_id=%s exercise=%s conn=%s",
            self.processor.__class__.__name__, self.user_id, self.exercise_code, self.conn_id,
        )

        recv_task = asyncio.create_task(self._recv_client_messages())

        try:
            loop = asyncio.get_running_loop()
            empty_frame_count = 0

            # intrinsics 초기화 대기 루프
            wait_started = loop.time()
            while self.running and camera_manager.intrinsics is None:
                logger.debug("Waiting for camera intrinsics...")
                if loop.time() - wait_started > CAMERA_INIT_TIMEOUT_SECONDS:
                    logger.error("카메라 초기화 시간이 초과되었습니다.")
                    await self._send_status_only(
                        {
                            "mode": "ERROR",
                            "status": "camera_unavailable",
                            "message": "카메라를 초기화하지 못했습니다. RealSense 연결 상태를 확인해주세요.",
                            "feedback": "카메라를 초기화하지 못했습니다.",
                            "keypoints": {},
                        }
                    )
                    await self.ws.close(code=1011, reason="camera_init_timeout")
                    return
                await asyncio.sleep(0.1)

            while self.running:
                frame_start = loop.time()
                if self.ws.client_state != WebSocketState.CONNECTED:
                    logger.info("WebSocket 연결이 종료되어 서비스 루프를 중단합니다. conn=%s", self.conn_id)
                    break
                # 1. 프레임 획득
                frame, depth_frame, intrinsics = camera_manager.get_frame()

                if frame is None:
                    empty_frame_count += 1
                    logger.warning(
                        "카메라 프레임을 가져오지 못했습니다. retry=%s/%s conn=%s",
                        empty_frame_count,
                        EMPTY_FRAME_RETRY_LIMIT,
                        self.conn_id,
                    )
                    if empty_frame_count >= EMPTY_FRAME_RETRY_LIMIT:
                        await self._send_status_only(
                            {
                                "mode": "ERROR",
                                "status": "camera_unavailable",
                                "message": "카메라 프레임을 연속으로 받아오지 못했습니다.",
                                "feedback": "카메라 프레임 수신 실패",
                                "keypoints": {},
                            }
                        )
                        break
                    await asyncio.sleep(0.05)
                    continue
                empty_frame_count = 0

                # 기본값 초기화
                keypoints = {}
                mp_features = None
                infer_t0 = time.perf_counter()

                # 2. YOLO 추론 → 2D 키포인트 추출 → depth로 3D 좌표 주입
                # keypoints: {idx: {"x","y"[,"x_m","y_m","z"]}}
                # pts: feature 추출용 튜플.
                #   전체 관절에 depth 있으면 (x_m, y_m, z) 3D,
                #   하나라도 depth 없으면 (x, y) 2D — z=0 근사는 각도 오류를 유발하므로 금지.
                try:
                    infer_frame = cv2.resize(frame, (STREAM_FRAME_W, STREAM_FRAME_H))
                    result = self.yolo.infer(infer_frame)
                    keypoints = extract_keypoints(result)

                    if keypoints:
                        camera_manager.update_keypoints_3d(keypoints, depth_frame, intrinsics)
                        self.depth_estimator.estimate(keypoints, intrinsics)

                    all_have_depth = bool(keypoints) and all(
                        v.get("x_m") is not None and
                        v.get("y_m") is not None and
                        v.get("z") is not None
                        for v in keypoints.values()
                    )

                    if all_have_depth:
                        pts = {k: (v["x_m"], v["y_m"], v["z"]) for k, v in keypoints.items()}
                        self._last_pts_3d = pts
                    elif self._last_pts_3d is not None:
                        # 일부 누락 시 — 유효한 관절은 현재 값, 누락된 관절은 이전 프레임 유지
                        pts = {}
                        for k, v in keypoints.items():
                            if v.get("x_m") is not None and v.get("y_m") is not None and v.get("z") is not None:
                                pts[k] = (v["x_m"], v["y_m"], v["z"])
                            elif k in self._last_pts_3d:
                                pts[k] = self._last_pts_3d[k]
                    else:
                        pts = {k: (v["x"], v["y"]) for k, v in keypoints.items()}

                    # 임시 확인용 — 칼만 필터 전 원시 좌표 출력
                    # elbow = pts.get(7)
                    # if elbow:
                    #     print(f"[RAW] elbow: {tuple(round(v,4) for v in elbow)}", flush=True)

                    pts = self.kalman.smooth(pts)

                    # 스무딩된 3D 좌표를 keypoints에 반영 → 보상 감지도 필터링된 값 사용
                    for idx, coords in pts.items():
                        if idx in keypoints and len(coords) == 3:
                            keypoints[idx]["x_m"] = coords[0]
                            keypoints[idx]["y_m"] = coords[1]
                            keypoints[idx]["z"]   = coords[2]

                    mp_features = self.processor.extract_mp_features(pts)

                except Exception as e:
                    logger.exception("YOLO 추론 실패: %s", e)

                # YOLO 추론~feature 추출까지 걸린 시간(ms) — 지연시간 계측용
                infer_ms = (time.perf_counter() - infer_t0) * 1000.0

                # 3. 로직 수행
                data = {}

                # 운동판단/점수화
                # - 운동별 상태 관리
                # - feature buffer 누적
                # - 1회 완료 판정 + DTW 판정 + 점수 반환
                # 프론트 phase 신호 처리
                if self._pending_phase:
                    phase = self._pending_phase
                    self._pending_phase = None
                    if hasattr(self.processor, "set_phase"):
                        self.processor.set_phase(phase)
                        logger.info("[Phase] set_phase(%s) 호출", phase)
                    elif phase == "DONE" and hasattr(self.processor, "signal_done"):
                        self.processor.signal_done()
                        logger.info("[Phase] DONE → signal_done() 호출")

                if self.processor:
                    process_result = self.processor.process(
                        keypoints=keypoints,
                        frame=frame,
                        depth_frame=depth_frame,
                        intrinsics=intrinsics,
                        mp_features=mp_features,
                    )

                    # session_finished 감지 → tail 타이머 시작 (즉시 종료 안 함)
                    is_finished = (
                        process_result.get("session_finished")
                        or process_result.get("status") == "finished"
                    ) if process_result else False
                    if is_finished and self._session_finished_at is None:
                        self._session_finished_at = time.time()

                    # tail 시간 경과 후 녹화 중단 + 후처리 백그라운드 실행
                    if (self._session_finished_at is not None
                            and time.time() - self._session_finished_at >= self._CLIP_TAIL_SEC
                            and self.recording_active):
                        session_end_t = self._session_finished_at + self._CLIP_TAIL_SEC
                        video_path    = self.record_video_path
                        rec_start     = self._recording_start_time
                        features_snap = list(self.record_features)
                        self._stop_recording(reason="session_finished")
                        self._session_finished_at = None
                        if hasattr(self.processor, "get_rep_events") and video_path and rec_start:
                            rep_events = self.processor.get_rep_events()
                            set_num    = getattr(self.processor, "_set_num", 1)
                            logger.info("[RepClip] rep_events: %s", rep_events)
                            threading.Thread(
                                target=self._postprocess_and_cut,
                                args=(video_path, rec_start, rep_events, session_end_t, set_num, features_snap),
                                daemon=True,
                            ).start()
                        break  # tail 완료 → 루프 종료

                    # 결과가 None이 아닐 때만 data 업데이트
                    if process_result is not None:
                        data = process_result

                        # 측정 완료 시 rom을 파일로 1회 저장 (프론트 미저장 상태에서 값 검증용)
                        rom = process_result.get("rom")
                        if rom and not self._rom_saved:
                            self._rom_saved = True
                            self._last_rom = rom
                            self._save_rom(rom, process_result.get("stage"))

                # 전송용 스켈레톤 keypoints는 항상 좌우 반전 (사용자가 거울처럼 보이도록)
                # 처리용 keypoints(processor.process에 전달된 것)는 건드리지 않음
                if isinstance(keypoints, dict) and keypoints:
                    display_keypoints = {}
                    for k, pt in keypoints.items():
                        if isinstance(pt, dict):
                            x = pt.get("x")
                            y = pt.get("y")
                            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                                display_keypoints[k] = {**pt, "x": float(STREAM_FRAME_W - x)}
                    data["keypoints"] = display_keypoints if display_keypoints else keypoints
                else:
                    data["keypoints"] = keypoints
                accuracy_pct = data.get("accuracy_pct")
                # status == "running" 또는 자세분석 상태에서 녹화 시작
                _RECORD_START_STATUSES = {"running", "preparing", "measuring", "ready", "waiting_ready"}
                if not self.recording_active and data.get("status") in _RECORD_START_STATUSES:
                    self._start_recording()
                if self.recording_active:
                    self._record_frame(frame, mp_features, accuracy_pct)

                system_status = self.monitor.check_status(frame)
                data["system_status"] = system_status

                # 4. 전송
                # tail 구간 중 연결 끊겨도 녹화는 계속 (전송만 스킵)
                if not await self._send_packet(cv2.flip(frame, 1), data):
                    if self._session_finished_at is None:
                        logger.warning("프레임 전송에 실패하여 서비스 루프를 중단합니다. conn=%s", self.conn_id)
                        break
                    # tail 기간 중 연결 끊김 → 전송만 스킵하고 계속 녹화

                # 30FPS 유지: 처리에 걸린 시간을 빼고 남은 만큼만 대기
                elapsed = loop.time() - frame_start

                # 프레임별 계측 기록 (실제 대기 전 처리시간 = 지연시간, 유사도 시계열)
                if self._session_start_time is None:
                    self._session_start_time = time.time()
                self._frame_metrics.append({
                    "ts": time.time(),
                    "loop_ms": round(elapsed * 1000.0, 2),
                    "infer_ms": round(infer_ms, 2),
                    "similarity": data.get("similarity"),
                    "accuracy_pct": data.get("accuracy_pct"),
                    "rep": data.get("rep_count"),
                })

                await asyncio.sleep(max(0.0, (1.0 / 30.0) - elapsed))

        except WebSocketDisconnect:
            logger.info("클라이언트 연결이 종료되었습니다. conn=%s", self.conn_id)
        except Exception as e:
            logger.exception("모션 서비스 처리 중 치명적인 오류가 발생했습니다: %s | conn=%s", e, self.conn_id)
        finally:
            recv_task.cancel()
            self.running = False
            # session_finished 흐름이 아닌 수동 종료 시에도 rep이 있으면 클립 저장
            manual_cut_args = None
            if (self._session_finished_at is None
                    and self.recording_active
                    and hasattr(self.processor, "get_rep_events")):
                rep_events = self.processor.get_rep_events()
                if rep_events:
                    manual_cut_args = (
                        self.record_video_path,
                        self._recording_start_time,
                        rep_events,
                        time.time(),
                        getattr(self.processor, "_set_num", 1),
                        list(self.record_features),
                    )
            self._stop_recording(reason="service_stop")
            if manual_cut_args:
                threading.Thread(
                    target=self._postprocess_and_cut,
                    args=manual_cut_args,
                    daemon=True,
                ).start()
            self._persist_session_result()
            self._save_metrics()
            logger.info("카메라 종료를 요청했습니다. conn=%s", self.conn_id)
            camera_manager.stop()
            logger.info("모션 서비스가 종료되었습니다. conn=%s", self.conn_id)

    # 측정된 ROM을 파일로 저장한다. 프론트가 localStorage에 저장하기 전이라도 측정값을 검증할 수 있게 남긴다.
    # rom: 측정 완료 시 프로세서가 반환한 rom 딕셔너리. stage: 부위 식별용 태그(있으면 파일명에 포함).
    def _save_rom(self, rom: dict, stage=None):
        try:
            save_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "rom_results")
            os.makedirs(save_dir, exist_ok=True)
            _PREFIX = {
                "FULL_BODY": "full_body_rom",
                "NECK_ROM":  "neck_rom",
                "KNEE_ROM":  "knee_rom",
            }
            prefix = _PREFIX.get((stage or "").upper(), "shoulder_rom")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(save_dir, f"{prefix}_{ts}.json")
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"rom": rom, "measured_at": datetime.now().isoformat(timespec="seconds")},
                    f, ensure_ascii=False, indent=2,
                )
            logger.info("[ROM] 측정 결과 저장: %s | %s", save_path, rom)
        except Exception as e:
            logger.warning("[ROM] 저장 실패: %s", e)

    # 세션 종료 시 결과를 DB에 적재한다. (Phase 1 — 서버 주도 저장)
    # 검사(check_*) 세션은 ROM을, 운동 세션은 ExerciseSession+Summary+Rep를 기록한다.
    # user_id가 없으면(비로그인) 저장하지 않는다.
    def _persist_session_result(self):
        if self.user_id is None:
            return
        try:
            from app.core.database import SessionLocal
            from app.services.session_result_service import (
                persist_exercise_session,
                persist_rom_measurements,
            )
            code = self.exercise_code or ""
            db = SessionLocal()
            try:
                if code.startswith("check_"):
                    if self._last_rom:
                        persist_rom_measurements(
                            db, user_id=self.user_id, rom_dict=self._last_rom, measured_at=datetime.now()
                        )
                    return
                reps = self._build_rep_results()
                if not reps and not self._frame_metrics:
                    return
                started = (
                    datetime.fromtimestamp(self._session_start_time)
                    if self._session_start_time else datetime.now()
                )
                overall = self._overall_accuracy()
                rep_avg = (
                    round(sum(r["accuracy_pct"] for r in reps if r["accuracy_pct"] is not None)
                          / max(1, sum(1 for r in reps if r["accuracy_pct"] is not None)), 2)
                    if reps else overall
                )
                finished = (
                    getattr(self.processor, "session_finished", False)
                    or getattr(self.processor, "finished", False)
                )
                persist_exercise_session(
                    db,
                    user_id=self.user_id,
                    exercise_code=code,
                    started_at=started,
                    ended_at=datetime.now(),
                    status="completed" if finished else "aborted",
                    reps=reps,
                    overall_accuracy_pct=overall,
                    rep_accuracy_avg_pct=rep_avg,
                    rom_dict=self._last_rom,
                )
            finally:
                db.close()
        except Exception as e:
            logger.warning("[SessionResult] DB 저장 실패: %s", e)

    # rep_events(프로세서) + 프레임 계측을 결합해 rep별 결과 리스트를 만든다.
    # accuracy는 rep 시간창 내 유사도 평균, max_angle은 rep-end 이벤트가 실어 보낸 피크각.
    def _build_rep_results(self) -> list:
        if not hasattr(self.processor, "get_rep_events"):
            return []
        events = self.processor.get_rep_events() or []
        starts = {e["rep"]: e for e in events if e.get("type") == "start"}
        ends = {e["rep"]: e for e in events if e.get("type") == "end"}
        reps = []
        for rep_no in sorted(ends.keys()):
            end = ends[rep_no]
            start = starts.get(rep_no)
            start_t = start["t"] if start else None
            end_t = end["t"]
            acc, mn = self._rep_accuracy(start_t, end_t)
            reps.append({
                "rep_no": rep_no,
                "started_at": datetime.fromtimestamp(start_t) if start_t else None,
                "ended_at": datetime.fromtimestamp(end_t),
                "label": end.get("label"),
                "accuracy_pct": acc,
                "min_accuracy_pct": mn if mn is not None else acc,
                "max_angle_deg": end.get("max_angle", 0.0),
            })
        return reps

    # 지정한 시간창 [start_t, end_t] 안의 프레임 유사도 평균/최소를 구한다.
    def _rep_accuracy(self, start_t, end_t):
        if start_t is None:
            return None, None
        sims = []
        for m in self._frame_metrics:
            if start_t <= m["ts"] <= end_t:
                s = m["similarity"] if m["similarity"] is not None else m["accuracy_pct"]
                if isinstance(s, (int, float)) and s > 0:
                    sims.append(float(s))
        if not sims:
            return None, None
        return round(sum(sims) / len(sims), 2), round(min(sims), 2)

    # 세션 전체 프레임의 유사도 평균(종합 정확도).
    def _overall_accuracy(self) -> float:
        sims = []
        for m in self._frame_metrics:
            s = m["similarity"] if m["similarity"] is not None else m["accuracy_pct"]
            if isinstance(s, (int, float)) and s > 0:
                sims.append(float(s))
        return round(sum(sims) / len(sims), 2) if sims else 0.0

    # 프레임별 계측 버퍼를 세션 요약 통계로 집계해 JSON으로 저장한다.
    # 실측 FPS, 프레임당 지연시간(전체 루프/YOLO 추론) 백분위수, 유사도 분포를 담는다.
    # 저장 위치: public/metrics/<운동태그>/session_<타임스탬프>.json
    def _save_metrics(self):
        if not self._frame_metrics:
            return
        try:
            def _stats(vals):
                vals = [v for v in vals if v is not None]
                if not vals:
                    return None
                s = sorted(vals)
                n = len(s)
                return {
                    "count": n,
                    "min": round(s[0], 2),
                    "max": round(s[-1], 2),
                    "mean": round(sum(s) / n, 2),
                    "p50": round(s[int((n - 1) * 0.50)], 2),
                    "p95": round(s[int((n - 1) * 0.95)], 2),
                }

            ts_list = [m["ts"] for m in self._frame_metrics]
            duration = max(ts_list[-1] - ts_list[0], 1e-6)
            fps_actual = (len(ts_list) - 1) / duration if len(ts_list) > 1 else 0.0
            sim_vals = [
                m["similarity"] if m["similarity"] is not None else m["accuracy_pct"]
                for m in self._frame_metrics
            ]

            exercise_tag = self._get_exercise_tag()
            save_dir = os.path.join(self.metrics_dir, exercise_tag)
            os.makedirs(save_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(save_dir, f"session_{ts}.json")

            t0 = ts_list[0]
            payload = {
                "exercise": exercise_tag,
                "conn_id": self.conn_id,
                "session_start": datetime.fromtimestamp(t0).isoformat(timespec="seconds"),
                "duration_sec": round(duration, 2),
                "frame_count": len(self._frame_metrics),
                "fps_actual": round(fps_actual, 2),
                "latency_ms": {
                    "loop": _stats([m["loop_ms"] for m in self._frame_metrics]),
                    "infer": _stats([m["infer_ms"] for m in self._frame_metrics]),
                },
                "similarity": _stats(sim_vals),
                "frames": [
                    {
                        "t": round(m["ts"] - t0, 3),
                        "loop_ms": m["loop_ms"],
                        "infer_ms": m["infer_ms"],
                        "similarity": m["similarity"],
                        "accuracy_pct": m["accuracy_pct"],
                        "rep": m["rep"],
                    }
                    for m in self._frame_metrics
                ],
            }
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.info(
                "[Metrics] 세션 계측 저장: %s | fps=%.1f frames=%d",
                save_path, fps_actual, len(self._frame_metrics),
            )
        except Exception as e:
            logger.warning("[Metrics] 저장 실패: %s", e)
        finally:
            self._frame_metrics = []

    # 이미지 없이 상태 정보만 담은 JSON 패킷을 프론트로 전송합니다.
    # 카메라 오류 등 예외 상황을 알릴 때 사용합니다.
    # 매개변수: data - 전송할 상태 정보 딕셔너리
    async def _send_status_only(self, data):
        try:
            payload_data = dict(data or {})
            payload_data["frame_w"] = STREAM_FRAME_W
            payload_data["frame_h"] = STREAM_FRAME_H
            await self.ws.send_json(
                {
                    "type": "frame",
                    "jpeg_b64": None,
                    "data": payload_data,
                }
            )
        except (WebSocketDisconnect, RuntimeError):
            return
        except Exception as e:
            logger.exception("상태 전송 중 오류가 발생했습니다: %s", e)

    # 카메라 프레임 이미지를 JPEG로 압축하고 Base64로 인코딩해 데이터와 함께 전송합니다.
    # 매개변수: frame - 원본 카메라 이미지 배열 / data - 함께 전송할 운동 분석 결과 딕셔너리
    # 반환값: 전송 성공이면 True, 연결 끊김 또는 오류면 False
    async def _send_packet(self, frame, data):
        """ 화면과 데이터를 합쳐서 전송 """
        try:
            # 이미지 인코딩
            small = cv2.resize(frame, (STREAM_FRAME_W, STREAM_FRAME_H))
            _, jpg = cv2.imencode(".jpg", small)
            b64 = base64.b64encode(jpg.tobytes()).decode('ascii')
            payload_data = dict(data or {})
            payload_data["frame_w"] = STREAM_FRAME_W
            payload_data["frame_h"] = STREAM_FRAME_H

            payload = {
                "type": "frame",
                "jpeg_b64": b64,
                "data": payload_data,
            }

            await self.ws.send_json(payload)
            return True

        except (WebSocketDisconnect, RuntimeError) as e:
            return False
        except Exception as e:
            logger.exception("프레임 전송 중 오류가 발생했습니다: %s", e)
            return False

    # 녹화를 시작해야 할지 판단합니다.
    # 이미 녹화 중이거나 정확도 값이 없으면 False를 반환합니다.
    # 매개변수: accuracy_pct - 현재 프레임의 정확도 값 (없으면 None)
    # 반환값: 녹화를 시작해야 하면 True, 아니면 False
    def _should_start_recording(self, accuracy_pct):
        if self.recording_active:
            return False
        if accuracy_pct is None:
            return False
        if isinstance(accuracy_pct, (int, float)) and not math.isnan(accuracy_pct):
            return True
        return False

    # 운동 영상 녹화를 시작합니다.
    # 타임스탬프와 운동명으로 파일 이름을 만들고 별도 스레드에서 파일 쓰기를 처리합니다.
    # 녹화 해상도는 카메라 캡처 해상도(1280×720)를 그대로 사용합니다. WebSocket 전송(640×360)과 무관합니다.
    def _start_recording(self):
        if self.recording_active:
            return
        self._recording_start_time = time.time()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        exercise_tag = self._get_exercise_tag()
        base_name = f"record_{timestamp}_{exercise_tag}"
        exercise_recordings_dir = os.path.join(self.recordings_dir, exercise_tag, "originals")
        exercise_features_dir = os.path.join(self.features_dir, exercise_tag)
        os.makedirs(exercise_recordings_dir, exist_ok=True)
        os.makedirs(exercise_features_dir, exist_ok=True)
        self.record_video_path = os.path.join(exercise_recordings_dir, f"{base_name}.mp4")
        self.record_features_path = os.path.join(exercise_features_dir, f"{base_name}.json")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.video_writer = cv2.VideoWriter(
            self.record_video_path,
            fourcc,
            30.0,
            (CAMERA_FRAME_W, CAMERA_FRAME_H),
        )
        self.record_features = []
        self.recording_active = True
        self.record_drop_count = 0
        self.record_queue = queue.Queue(maxsize=24)
        self.record_worker = threading.Thread(
            target=self._record_worker_loop,
            name=f"record_writer_{self.conn_id}",
            daemon=True,
        )
        self.record_worker.start()
        logger.info(
            "녹화를 시작했습니다. video=%s features=%s conn=%s",
            self.record_video_path,
            self.record_features_path,
            self.conn_id,
        )

    # 현재 프레임과 관절 특징값을 녹화 큐에 넣습니다.
    # 큐가 가득 찬 경우 해당 프레임은 건너뛰고 경고 로그를 남깁니다.
    # 매개변수: frame - 카메라 프레임 이미지 / mp_features - 관절 특징값 / accuracy_pct - 현재 정확도
    def _record_frame(self, frame, mp_features, accuracy_pct):
        if not self.recording_active:
            return
        try:
            if self.record_queue is None:
                return
            self.record_queue.put_nowait(
                {
                    "frame": frame.copy(),
                    "ts": time.time(),
                    "accuracy_pct": accuracy_pct,
                    "mp_features": copy.deepcopy(mp_features),
                }
            )
        except queue.Full:
            self.record_drop_count += 1
            if self.record_drop_count == 1 or self.record_drop_count % 30 == 0:
                logger.warning(
                    "녹화 큐가 가득 차 프레임을 건너뜁니다. dropped=%s conn=%s",
                    self.record_drop_count,
                    self.conn_id,
                )
        except Exception as e:
            logger.exception("녹화 프레임 저장 중 오류가 발생했습니다: %s", e)

    # 별도 스레드에서 실행되며 녹화 큐에서 항목을 꺼내 영상 파일에 씁니다.
    # None 항목을 받으면 루프를 종료합니다.
    def _record_worker_loop(self):
        while True:
            item = None
            try:
                if self.record_queue is None:
                    return
                item = self.record_queue.get()
                if item is None:
                    return
                frame = item.get("frame")
                if frame is not None and self.video_writer is not None:
                    # 카메라 원본(1280×720) 그대로 저장 — YOLO 처리용 리사이즈와 분리
                    self.video_writer.write(frame)
                self.record_features.append(
                    {
                        "ts": item.get("ts"),
                        "accuracy_pct": item.get("accuracy_pct"),
                        "mp_features": item.get("mp_features"),
                    }
                )
            except Exception as e:
                logger.exception("녹화 worker 처리 중 오류가 발생했습니다: %s", e)
            finally:
                if item is not None and self.record_queue is not None:
                    self.record_queue.task_done()

    # 녹화를 종료하고 영상 파일과 관절 특징값 JSON을 저장합니다.
    # 워커 스레드에 종료 신호를 보내고, 파일을 닫은 뒤 내부 상태를 초기화합니다.
    # 매개변수: reason - 녹화 종료 이유 문자열 (로그 및 JSON에 기록됨)
    def _stop_recording(self, reason):
        if not self.recording_active:
            return
        try:
            if self.record_queue is not None:
                self.record_queue.put(None)
        except Exception:
            pass
        try:
            if self.record_worker is not None:
                self.record_worker.join(timeout=2.0)
        except Exception as e:
            logger.exception("녹화 worker 종료 중 오류가 발생했습니다: %s", e)
        try:
            if self.video_writer is not None:
                self.video_writer.release()
        except Exception as e:
            logger.exception("영상 파일 마무리 중 오류가 발생했습니다: %s", e)
        try:
            with open(self.record_features_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "conn_id": self.conn_id,
                        "reason": reason,
                        "frames": self.record_features,
                    },
                    f,
                    ensure_ascii=False,
                )
        except Exception as e:
            logger.exception("feature json 저장 중 오류가 발생했습니다: %s", e)
        logger.info(
            "녹화를 종료했습니다. video=%s features=%s conn=%s",
            self.record_video_path,
            self.record_features_path,
            self.conn_id,
        )
        self.recording_active = False
        self.video_writer = None
        self.record_features = []
        self.record_queue = None
        self.record_worker = None

    def _postprocess_and_cut(self, video_path, rec_start, rep_events, session_end_t, set_num, features_snap):
        """fps 보정 후 rep 클립 절단. 백그라운드 스레드에서 실행된다."""
        import subprocess
        fixed_path = video_path
        try:
            ts_list = [f["ts"] for f in features_snap if f.get("ts") is not None]
            if len(ts_list) > 1:
                actual_fps   = (len(ts_list) - 1) / (ts_list[-1] - ts_list[0])
                declared_fps = 30.0
                setpts       = declared_fps / actual_fps  # PTS 스트레치 비율
                tmp_path     = video_path + ".tmp.mp4"
                ret = subprocess.run(
                    ["ffmpeg", "-y",
                     "-i", video_path,
                     "-vf", f"setpts={setpts:.6f}*PTS",
                     "-r", f"{actual_fps:.4f}",
                     "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                     tmp_path],
                    capture_output=True, timeout=120,
                )
                if ret.returncode == 0:
                    os.replace(tmp_path, video_path)
                    logger.info("[RepClip] fps 보정 완료: %.2f fps (%d frames)", actual_fps, len(ts_list))
                else:
                    logger.warning("[RepClip] ffmpeg 실패: %s", ret.stderr.decode()[-200:])
        except Exception as e:
            logger.warning("[RepClip] fps 보정 오류 (무시): %s", e)

        self._cut_rep_clips(fixed_path, rec_start, rep_events, session_end_t, set_num)

    def _cut_rep_clips(
        self,
        video_path: str,
        rec_start: float,
        rep_events: list,
        session_end_t: float,
        set_num: int,
    ):
        """원본 영상을 rep별로 절단해 clips 디렉토리에 저장한다."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.warning("[RepClip] 원본 영상을 열 수 없습니다: %s", video_path)
            return
        fps          = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        # 드랍된 프레임을 고려해 실제 기록 fps로 재계산
        session_dur = max(session_end_t - rec_start, 1.0)
        fps_actual  = total_frames / session_dur
        logger.info("[RepClip] 영상 정보: fps_actual=%.2f total_frames=%d size=%dx%d session_dur=%.1fs",
                    fps_actual, total_frames, w, h, session_dur)

        starts = {e["rep"]: e["t"] for e in rep_events if e["type"] == "start"}
        ends   = {e["rep"]: (e["t"], e["label"]) for e in rep_events if e["type"] == "end"}
        reps   = sorted(ends.keys())
        if not reps:
            cap.release()
            return

        exercise_tag = self._get_exercise_tag()
        clips_dir = os.path.join(self.recordings_dir, exercise_tag, "clips")
        os.makedirs(clips_dir, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        clip_fps = fps_actual  # 실제 기록 fps로 저장해야 재생 속도 정상

        for i, rep_num in enumerate(reps):
            t_end, label = ends[rep_num]

            # 클립 시작: 첫 rep은 녹화 시작, 나머지는 직전 rep end~현재 rep start 중간점
            if i == 0:
                clip_t_start = rec_start
            else:
                prev_t_end = ends[reps[i - 1]][0]
                curr_t_start = starts.get(rep_num, t_end)
                clip_t_start = (prev_t_end + curr_t_start) / 2.0

            # 클립 끝: 마지막 rep은 세션 종료 시각, 나머지는 현재 rep end~다음 rep start 중간점
            if i < len(reps) - 1:
                next_t_start = starts.get(reps[i + 1], t_end)
                clip_t_end = (t_end + next_t_start) / 2.0
            else:
                clip_t_end = session_end_t

            frame_start = max(0, int((clip_t_start - rec_start) * fps_actual))
            frame_end   = min(total_frames, int((clip_t_end   - rec_start) * fps_actual))
            logger.info("[RepClip] rep%d: clip_t=[%.3f~%.3f] frames=[%d~%d]",
                        rep_num, clip_t_start - rec_start, clip_t_end - rec_start, frame_start, frame_end)
            if frame_end <= frame_start:
                logger.warning("[RepClip] rep%d: frame_end(%d) <= frame_start(%d), 건너뜀", rep_num, frame_end, frame_start)
                continue

            label_map = {"정상": "normal"}
            short = label_map.get(label)
            if short is None:
                if "팔꿈치" in label:    short = "elbow"
                elif "어깨" in label:    short = "shoulder"
                elif "상체" in label:    short = "trunk"
                else:                    short = "unknown"

            filename = f"set{set_num:02d}_rep{rep_num:02d}_{ts}_{short}.mp4"
            out_path  = os.path.join(clips_dir, filename)
            writer    = cv2.VideoWriter(out_path, fourcc, clip_fps, (w, h))

            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_start)
            for _ in range(frame_end - frame_start):
                ret, frm = cap.read()
                if not ret:
                    break
                writer.write(frm)
            writer.release()
            logger.info("[RepClip] 저장: %s", filename)

        cap.release()

    # 현재 실행 중인 운동 프로세서 정보를 바탕으로 파일 저장에 쓸 태그 이름을 결정합니다.
    # 반환값: 운동명과 좌우 구분이 포함된 소문자 문자열 (예: "shoulder_front_raise_left")
    def _get_exercise_tag(self):
        if self.processor is None:
            return "exercise"
        check_tag = getattr(self.processor, "check_tag", None)
        if check_tag:
            return check_tag
        exercise_name = getattr(self.processor, "exercise_name", None)
        side = getattr(self.processor, "active_side", None)
        side_tag = None
        if isinstance(side, str) and side.strip():
            side_tag = side.strip().lower()
        if isinstance(exercise_name, str) and exercise_name.strip():
            base = exercise_name.strip().lower().replace(" ", "_")
            return f"{base}_{side_tag}" if side_tag else base
        name = self.processor.__class__.__name__.lower()
        if "birddog" in name or "bird_dog" in name:
            return "bird_dog"
        if "shoulder" in name and "front" in name:
            return f"shoulder_front_raise_{side_tag}" if side_tag else "shoulder_front_raise"
        if "straight" in name and "leg" in name:
            return f"straight_leg_raise_{side_tag}" if side_tag else "straight_leg_raise"
        if "neck" in name and "rotation" in name:
            return "neck_rotation"
        return "exercise"
