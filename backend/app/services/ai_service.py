import numpy as np
from ultralytics import YOLO
import torch
import logging
from app.core.gpu_debug import log_gpu_snapshot

logger = logging.getLogger(__name__)

class YOLODetector:
    def __init__(self, model_path: str, device="cuda"):
        # 모델 로드
        self.device = device if device == "cuda" and torch.cuda.is_available() else "cpu"
        self.use_half = self.device == "cuda"
        self.model = YOLO(model_path)
        
        # Jetson 최적화: PF16(Half Precision) 모드로 전환 확인
        # (Ultralytics는 자동 감지하지만, 명시적으로 확인하면 좋음)
        if self.device == "cuda":
            self.model.to("cuda")
            print(f"[YOLO] Running on {torch.cuda.get_device_name(0)}")
            # log_gpu_snapshot("yolo_detector_initialized_cuda")
        else:
            self.model.to("cpu")
            print("[YOLO] Running on CPU")
            # log_gpu_snapshot("yolo_detector_initialized_cpu")

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
        # stream=True는 메모리를 아끼지만, 여기선 즉시 결과를 원하므로 리스트의 첫 번째를 가져옴
        # verbose=False: 콘솔에 로그 도배 방지
        # if self.device == "cuda":
        #     log_gpu_snapshot("before_infer")
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
            if self.device == "cuda" and (
                "CUBLAS_STATUS_ALLOC_FAILED" in message
                or "CUDA error" in message
                or "out of memory" in message.lower()
            ):
                log_gpu_snapshot("cuda_infer_failure", level=logging.ERROR)
                logger.exception("CUDA inference error. Retrying on CPU: %s", e)
                self._switch_to_cpu()
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
