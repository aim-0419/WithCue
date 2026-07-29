# YOLO 인공지능 모델을 불러오고 실행하는 모듈.
# 카메라 영상에서 사람의 관절 위치(키포인트)를 검출하며,
# GPU가 있으면 GPU를, 없거나 오류 발생 시 CPU로 자동 전환합니다.
# 앱 시작 시 워밍업을 통해 첫 추론 시 발생하는 메모리 급증을 방지합니다.

import numpy as np
from ultralytics import YOLO
import torch
import logging
from pathlib import Path
from app.core.gpu_debug import log_gpu_snapshot

logger = logging.getLogger(__name__)

# YOLO 포즈 추정 모델을 감싸는 클래스.
# 모델 로드, GPU/CPU 전환, 추론 실행을 담당합니다.
# .engine 파일(TensorRT)이 .pt와 같은 경로에 있으면 자동으로 TRT 모드로 실행합니다.
class YOLODetector:
    # 모델 파일 경로와 실행 장치(기본값: GPU)를 받아 모델을 초기화합니다.
    # .pt와 같은 디렉터리에 .engine이 존재하면 TRT 엔진을 우선 로드합니다.
    # GPU 메모리 부족 시 CPU 모드로 자동 전환되며, 모델 파일이 없으면 즉시 오류를 발생시킵니다.
    # 매개변수: model_path - YOLO .pt 모델 파일 경로 / device - 실행 장치 ("cuda" 또는 "cpu")
    def __init__(self, model_path: str, device="cuda"):
        # 초기 CUDA 메모리 정리 및 캐시 클리어
        if device == "cuda" and torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.empty_cache()
            logger.info("[YOLO] Clearing CUDA cache before model loading...")

        self.device = "cpu"
        self.use_half = False
        self.use_trt = False

        # .pt와 같은 경로에 .engine이 있으면 TRT 우선 사용
        pt_path = Path(model_path)
        engine_path = pt_path.with_suffix(".engine")

        if engine_path.exists() and device == "cuda" and torch.cuda.is_available():
            try:
                logger.info("[YOLO/TRT] TensorRT 엔진 발견: %s", engine_path)
                self.model = YOLO(str(engine_path), task="pose")
                self.device = "cuda"
                self.use_trt = True
                self.use_half = False  # FP16은 엔진에 이미 컴파일됨
                logger.info("[YOLO/TRT] TensorRT 모드로 실행합니다. (FP16 baked-in)")
                log_gpu_snapshot("yolo_detector_initialized_trt")
                return
            except Exception as e:
                logger.warning("[YOLO/TRT] TRT 로드 실패, .pt 모드로 전환합니다: %s", e)
                self.use_trt = False

        # TRT 없음 — 기존 .pt 로드 경로
        try:
            logger.info(f"[YOLO] Loading model from {model_path}...")
            self.model = YOLO(model_path)
            logger.info("[YOLO] Model loaded on CPU successfully.")

            # GPU 사용 가능 시 GPU로 이동 시도
            if device == "cuda" and torch.cuda.is_available():
                try:
                    # Jetson Orin(SM87) pip PyTorch의 cuDNN은 SM87 전용 알고리즘 미지원.
                    # 비활성화하면 CUDA implicit GEMM 폴백으로 전환되어 정상 작동함.
                    torch.backends.cudnn.enabled = False
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

    # GPU 추론 중 오류가 발생했을 때 CPU 모드로 전환합니다.
    # GPU 메모리를 비우고 모델을 CPU로 이동시킵니다.
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

    # 카메라에서 받은 이미지 한 장을 YOLO 모델로 분석하여 관절 위치를 반환합니다.
    # GPU 오류 발생 시 자동으로 CPU로 전환 후 재시도합니다.
    # TRT 모드일 때는 device=0(정수)을 사용해야 TensorRT 엔진이 올바르게 동작합니다.
    # 매개변수: frame - BGR 형식의 이미지 배열(OpenCV) / conf - 감지 신뢰도 임계값(기본 0.5)
    # 반환값: YOLO Result 객체 (관절 좌표 및 신뢰도 포함)
    @torch.no_grad()
    def infer(self, frame: np.ndarray, conf: float = 0.5):
        """
        frame: BGR numpy image (OpenCV format)
        return: YOLO Result object
        """
        infer_device = 0 if self.use_trt else self.device
        try:
            results = self.model.predict(
                frame,
                device=infer_device,
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
                    device=self.device,  # _switch_to_cpu() 이후 "cpu"로 변경됨
                    verbose=False,
                    imgsz=640,
                    half=self.use_half,
                    conf=conf
                )
            else:
                raise

        return results[0]
