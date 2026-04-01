import asyncio
import cv2
import base64
import logging
from fastapi import WebSocket, WebSocketDisconnect

from app.core.monitor import SystemMonitor
from app.hardware.camera import camera_manager
from app.core.utils import extract_keypoints
from app.services.processors import BaseProcessor

STREAM_FRAME_W = 1280
STREAM_FRAME_H = 720
CAMERA_INIT_TIMEOUT_SECONDS = 5.0
# [핵심] 스트리밍 해상도 상수화: 프론트 렌더링/성능 튜닝 시 한 곳에서 조절
logger = logging.getLogger(__name__)

class MotionService:
    def __init__(self, ws: WebSocket, yolo):
        self.ws = ws
        self.yolo = yolo
        self.running = False
        self.processor: BaseProcessor = None
        self.monitor = SystemMonitor()

    def set_processor(self, processor: BaseProcessor):
        self.processor = processor

    async def start(self):
        await self.ws.accept()
        try:
            camera_manager.start()
        except Exception as e:
            logger.warning("Camera start warning: %s", e)
            
        self.running = True
        logger.info("Service started: %s", self.processor.__class__.__name__)
        
        try:
            loop = asyncio.get_running_loop()
            
            # intrinsics 초기화 대기 루프
            wait_started = loop.time()
            while self.running and camera_manager.intrinsics is None:
                logger.debug("Waiting for camera intrinsics...")
                if loop.time() - wait_started > CAMERA_INIT_TIMEOUT_SECONDS:
                    logger.error("Camera initialization timed out.")
                    await self._send_status_only(
                        {
                            "mode": "ERROR",
                            "status": "camera_unavailable",
                            "message": "카메라를 초기화하지 못했습니다. RealSense 연결 상태를 확인해주세요.",
                            "feedback": "카메라를 초기화하지 못했습니다.",
                            "keypoints": {},
                        }
                    )
                    break
                await asyncio.sleep(0.1)
                            
            while self.running:
                # 1. 프레임 획득
                frame, depth_frame, intrinsics = camera_manager.get_frame()
                
                if frame is None:
                    logger.warning("Frame is None. Camera disconnected/loading.")
                    await self._send_status_only(
                        {
                            "mode": "ERROR",
                            "status": "camera_unavailable",
                            "message": "카메라 프레임을 받아오지 못하고 있습니다.",
                            "feedback": "카메라 프레임 수신 실패",
                            "keypoints": {},
                        }
                    )
                    await asyncio.sleep(0.05)
                    break

                # 2. YOLO 추론
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = await loop.run_in_executor(
                    None, 
                    lambda: self.yolo.infer(frame_rgb, conf=0.25)
                )
                keypoints = extract_keypoints(result)
                
                # print(f"[SERVICE] YOLO가 찾은 관절 데이터: {type(keypoints)} | 내용: {keypoints}")

                # 3. 로직 수행
                data = {}
                
                if self.processor:
                    process_result = self.processor.process(
                        keypoints=keypoints,
                        frame=frame,
                        depth_frame=depth_frame,
                        intrinsics=intrinsics
                    )
                
                    # 결과가 None이 아닐 때만 data 업데이트
                    if process_result is not None:
                        data = process_result
                    
                data["keypoints"] = keypoints
                    
                system_status = self.monitor.check_status(frame)
                data["system_status"] = system_status

                # 4. 전송
                if not await self._send_packet(frame, data):
                    logger.warning("Send failed. Breaking service loop.")
                    break 
                
                await asyncio.sleep(0.033)

        except WebSocketDisconnect:
            logger.info("Client disconnected.")
        except Exception as e:
            logger.exception("Critical service error: %s", e)
        finally:
            self.running = False
            camera_manager.stop()
            logger.info("Service stopped.")

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
            logger.exception("Status send error: %s", e)

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
            logger.exception("Frame send error: %s", e)
            return False
