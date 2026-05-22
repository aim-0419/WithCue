import numpy as np
from ultralytics import YOLO
import torch
import logging
from pathlib import Path
from app.core.gpu_debug import log_gpu_snapshot

logger = logging.getLogger(__name__)

class YOLODetector:
    def __init__(self, model_path: str, device="cuda"):
        # 초기 CUDA 메모리 정리 및 캐시 클리어
        if device == "cuda" and torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.empty_cache()
            logger.info("[YOLO] Clearing CUDA cache before model loading...")
        
        # 모델 로드: CPU에서 먼저 로드 후 GPU로 이동하여 메모리 할당 오류 방지
        self.device = "cpu"  # 초기에는 CPU에서 로드
        self.use_half = False
        
        try:
            logger.info(f"[YOLO] Loading model from {model_path}...")
            self.model = YOLO(model_path)
            logger.info("[YOLO] Model loaded on CPU successfully.")
            
            # GPU 사용 가능 시 GPU로 이동 시도
            if device == "cuda" and torch.cuda.is_available():
                try:
                    logger.info("[YOLO] Attempting to move model to CUDA...")
                    self.model.to("cuda")
                    self.device = "cuda"
                    self.use_half = True
                    logger.info(f"[YOLO] Successfully running on GPU: {torch.cuda.get_device_name(0)}")
                    log_gpu_snapshot("yolo_detector_initialized_cuda")
                except RuntimeError as e:
                    logger.warning(f"[YOLO] Failed to load on CUDA (will use CPU): {e}")
                    torch.cuda.empty_cache()
                    self.device = "cpu"
                    self.use_half = False
                    logger.info("[YOLO] Falling back to CPU mode.")
            else:
                logger.info("[YOLO] CUDA not available. Running on CPU.")
                
        except Exception as e:
            logger.error(f"[YOLO] Critical error loading model: {e}", exc_info=True)
            logger.error(f"[YOLO] Checking file exists: {Path(model_path).exists()}")
            raise

    def _switch_to_cpu(self):
        if self.device == "cpu":
            return

        logger.warning("CUDA inference failed. Falling back to CPU mode.")
        # log_gpu_snapshot("before_cpu_fallback", level=logging.WARNING)
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

        self.device = "cpu"
        self.use_half = False
        self.model.to("cpu")
        print("[YOLO] Fallback to CPU mode complete.")
        log_gpu_snapshot("after_cpu_fallback", level=logging.WARNING)
            
    def warmup(self):
        """
        [메모리 튀는 현상 방지]
        앱 켜질 때 가짜 데이터로 한 번 실행시켜서 메모리를 미리 확보해둡니다.
        """
        print("[AI] Warming up model...")
        # log_gpu_snapshot("before_warmup")
        dummy_frame = np.zeros((640, 640, 3), dtype=np.uint8)
        self.infer(dummy_frame)
        print("[AI] Warmup complete.")
        # log_gpu_snapshot("after_warmup")
    
    @torch.no_grad()
    def infer(self, frame: np.ndarray, conf: float = 0.5):
        """
        frame: BGR numpy image (OpenCV format)
        return: YOLO Result object
        """
        try:
            results = self.model.predict(
                frame,
                device=self.device,
                verbose=False,
                imgsz=640,
                half=self.use_half,
                conf=conf
            )
        except RuntimeError as e:
            message = str(e)
            cuda_errors = (
                "CUBLAS_STATUS_ALLOC_FAILED",
                "CUDA error",
                "out of memory",
                "NVML_SUCCESS",
                "INTERNAL ASSERT FAILED",
                "CUDACachingAllocator"
            )
            
            if self.device == "cuda" and any(err in message for err in cuda_errors):
                logger.error(f"[YOLO] CUDA memory allocation error: {e}", exc_info=True)
                log_gpu_snapshot("cuda_infer_failure", level=logging.ERROR)
                
                # GPU 메모리 응급 정리
                self._switch_to_cpu()
                
                # CPU에서 재시도
                logger.info("[YOLO] Retrying inference on CPU...")
                results = self.model.predict(
                    frame,
                    device=self.device,
                    verbose=False,
                    imgsz=640,
                    half=self.use_half,
                    conf=conf
                )
            else:
                raise
        
        return results[0]
