import numpy as np
from ultralytics import YOLO
import torch

class YOLODetector:
    def __init__(self, model_path: str, device="cuda"):
        # 모델 로드
        self.device = device
        self.model = YOLO(model_path)
        
        # Jetson 최적화: PF16(Half Precision) 모드로 전환 확인
        # (Ultralytics는 자동 감지하지만, 명시적으로 확인하면 좋음)
        if device == "cuda" and torch.cuda.is_available():
            self.model.to("cuda")
            print(f"[YOLO] Running on {torch.cuda.get_device_name(0)}")
            
    def warmup(self):
        """
        [메모리 튀는 현상 방지]
        앱 켜질 때 가짜 데이터로 한 번 실행시켜서 메모리를 미리 확보해둡니다.
        """
        print("[AI] Warming up model...")
        dummy_frame = np.zeros((640, 640, 3), dtype=np.uint8)
        self.infer(dummy_frame)
        print("[AI] Warmup complete.")
    
    @torch.no_grad()
    def infer(self, frame: np.ndarray, conf: float = 0.5):
        """
        frame: BGR numpy image (OpenCV format)
        return: YOLO Result object
        """
        # stream=True는 메모리를 아끼지만, 여기선 즉시 결과를 원하므로 리스트의 첫 번째를 가져옴
        # verbose=False: 콘솔에 로그 도배 방지
        results = self.model.predict(
            frame,
            device=self.device,
            verbose=False,
            imgsz=640,
            half=True,
            conf=conf
        )
        return results[0]