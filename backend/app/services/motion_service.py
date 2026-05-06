import asyncio
import base64
import cv2
import json
import logging
import math
import os
import time
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.core.monitor import SystemMonitor
from app.hardware.camera import camera_manager
from app.core.utils import extract_keypoints
from app.services.processors import BaseProcessor
from app.services.dtw_feature_extractor import get_bird_dog_features_mp
import mediapipe as mp

STREAM_FRAME_W = 640
STREAM_FRAME_H = 360
CAMERA_INIT_TIMEOUT_SECONDS = 15.0
EMPTY_FRAME_RETRY_LIMIT = 15
# [핵심] 스트리밍 해상도 상수화: 프론트 렌더링/성능 튜닝 시 한 곳에서 조절
logger = logging.getLogger(__name__)

# - 카메라 프레임 받기
# - YOLO 추론
# - MediaPipe feature 추출
# - processor 호출 + 전송
class MotionService:
    def __init__(self, ws: WebSocket, yolo):
        self.ws = ws
        self.yolo = yolo
        self.running = False
        self.processor: BaseProcessor = None
        self.monitor = SystemMonitor()
        self.conn_id = id(ws)
        self.recording_active = False
        self.record_video_path = None
        self.record_features_path = None
        self.record_features = []
        self.video_writer = None
        
        BaseOptions = mp.tasks.BaseOptions
        PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
        VisionRunningMode = mp.tasks.vision.RunningMode
        PoseLandmarker = mp.tasks.vision.PoseLandmarker

        model_path = "./app/assets/models/pose_landmarker_full.task"

        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=VisionRunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.6,
            min_pose_presence_confidence=0.6,
            min_tracking_confidence=0.6,
            output_segmentation_masks=False,
        )

        self.mp_landmarker = PoseLandmarker.create_from_options(options)
        self.mp_timestamp_ms = 0       
        self.public_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "public"))
        self.recordings_dir = os.path.join(self.public_dir, "recordings")
        self.features_dir = os.path.join(self.public_dir, "features")
        os.makedirs(self.recordings_dir, exist_ok=True)
        os.makedirs(self.features_dir, exist_ok=True)

    def set_processor(self, processor: BaseProcessor):
        self.processor = processor

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
        logger.info("모션 서비스가 시작되었습니다: %s | conn=%s", self.processor.__class__.__name__, self.conn_id)
        
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

                # 2. MediaPipe feature 추출 (YOLO 비활성화)
                keypoints = {}
                mp_features = None
                try:
                    h, w = frame.shape[:2]
                    mp_frame_bgr = frame # 오른팔용 mirror
                    if self.processor and getattr(self.processor, "mirror_input", False):
                        mp_frame_bgr = cv2.flip(frame, 1)

                    mp_frame_rgb = cv2.cvtColor(mp_frame_bgr, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=mp_frame_rgb)
                    mp_result = self.mp_landmarker.detect_for_video(mp_image, self.mp_timestamp_ms)
                    self.mp_timestamp_ms += 33  # 대략 30fps 기준

                    if mp_result.pose_landmarks:
                        lms = mp_result.pose_landmarks[0]
                        pts = {}

                        for i, lm in enumerate(lms):
                            vis = getattr(lm, "visibility", 1.0)
                            if vis < 0.5:
                                continue

                            x = lm.x * STREAM_FRAME_W
                            y = lm.y * STREAM_FRAME_H
                            pts[i] = (x, y)
                        logger.debug("[MP] pts_count=%s conn=%s", len(pts), self.conn_id)

                        # MediaPipe -> COCO17 매핑 (프론트 스켈레톤/기존 규칙용)
                        mp_to_coco = {
                            0: 0,   # nose
                            2: 1,   # left_eye
                            5: 2,   # right_eye
                            7: 3,   # left_ear
                            8: 4,   # right_ear
                            11: 5,  # left_shoulder
                            12: 6,  # right_shoulder
                            13: 7,  # left_elbow
                            14: 8,  # right_elbow
                            15: 9,  # left_wrist
                            16: 10, # right_wrist
                            23: 11, # left_hip
                            24: 12, # right_hip
                            25: 13, # left_knee
                            26: 14, # right_knee
                            27: 15, # left_ankle
                            28: 16, # right_ankle
                        }

                        coco_keypoints = {}
                        for mp_idx, coco_idx in mp_to_coco.items():
                            if mp_idx not in pts:
                                continue
                            px, py = pts[mp_idx]
                            coco_keypoints[coco_idx] = {
                                "x": float(px),
                                "y": float(py),
                            }
                        if coco_keypoints:
                            keypoints = coco_keypoints

                        if self.processor and hasattr(self.processor, "extract_mp_features"):
                            mp_features = self.processor.extract_mp_features(pts)
                            logger.debug("[MP] extracted features=%s conn=%s", mp_features, self.conn_id)
                        else:
                            mp_features = None

                except Exception as e:
                    logger.exception("MediaPipe feature 추출 중 오류가 발생했습니다: %s", e)
                    mp_features = None
                    
                # 3. 로직 수행
                data = {}
                
                # 운동판단/점수화
                # - 운동별 상태 관리
                # - feature buffer 누적
                # - 1회 완료 판정 + DTW 판정 + 점수 반환
                if self.processor:
                    process_result = self.processor.process( 
                        keypoints=keypoints,
                        frame=frame,
                        depth_frame=depth_frame,
                        intrinsics=intrinsics,
                        mp_features=mp_features, # feature만들어서 넘기기
                    )
                
                    # 결과가 None이 아닐 때만 data 업데이트
                    if process_result is not None:
                        data = process_result
                    
                display_keypoints = keypoints
                if self.processor and getattr(self.processor, "mirror_input", False):
                    if isinstance(keypoints, dict) and keypoints:
                        flipped = {}
                        for k, pt in keypoints.items():
                            if not isinstance(pt, dict):
                                continue
                            x = pt.get("x")
                            y = pt.get("y")
                            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                                flipped[k] = {"x": float(STREAM_FRAME_W - x), "y": float(y)}
                        if flipped:
                            display_keypoints = flipped
                data["keypoints"] = display_keypoints
                accuracy_pct = data.get("accuracy_pct")
                if self._should_start_recording(accuracy_pct):
                    self._start_recording()
                if self.recording_active:
                    self._record_frame(frame, mp_features, accuracy_pct)
                    
                system_status = self.monitor.check_status(frame)
                data["system_status"] = system_status

                # 4. 전송
                if not await self._send_packet(frame, data):
                    logger.warning("프레임 전송에 실패하여 서비스 루프를 중단합니다. conn=%s", self.conn_id)
                    break 
                
                await asyncio.sleep(0.033)

        except WebSocketDisconnect:
            logger.info("클라이언트 연결이 종료되었습니다. conn=%s", self.conn_id)
        except Exception as e:
            logger.exception("모션 서비스 처리 중 치명적인 오류가 발생했습니다: %s | conn=%s", e, self.conn_id)
        finally:
            self.running = False
            self._stop_recording(reason="service_stop")
            logger.info("카메라 종료를 요청했습니다. conn=%s", self.conn_id)
            camera_manager.stop()
            logger.info("모션 서비스가 종료되었습니다. conn=%s", self.conn_id)

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

    def _should_start_recording(self, accuracy_pct):
        if self.recording_active:
            return False
        if accuracy_pct is None:
            return False
        if isinstance(accuracy_pct, (int, float)) and not math.isnan(accuracy_pct):
            return True
        return False

    def _start_recording(self):
        if self.recording_active:
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        exercise_tag = self._get_exercise_tag()
        base_name = f"record_{timestamp}_{exercise_tag}"
        exercise_recordings_dir = os.path.join(self.recordings_dir, exercise_tag)
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
            (STREAM_FRAME_W, STREAM_FRAME_H),
        )
        self.record_features = []
        self.recording_active = True
        logger.info(
            "녹화를 시작했습니다. video=%s features=%s conn=%s",
            self.record_video_path,
            self.record_features_path,
            self.conn_id,
        )

    def _record_frame(self, frame, mp_features, accuracy_pct):
        if not self.recording_active:
            return
        try:
            resized = cv2.resize(frame, (STREAM_FRAME_W, STREAM_FRAME_H))
            if self.video_writer is not None:
                self.video_writer.write(resized)
            self.record_features.append(
                {
                    "ts": time.time(),
                    "accuracy_pct": accuracy_pct,
                    "mp_features": mp_features,
                }
            )
        except Exception as e:
            logger.exception("녹화 프레임 저장 중 오류가 발생했습니다: %s", e)

    def _stop_recording(self, reason):
        if not self.recording_active:
            return
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

    def _get_exercise_tag(self):
        if self.processor is None:
            return "exercise"
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
        if "knee" in name and "raise" in name:
            return f"knee_raise_{side_tag}" if side_tag else "knee_raise"
        if "neck" in name and "rotation" in name:
            return "neck_rotation"
        return "exercise"
