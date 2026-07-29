# YOLOv8 포즈 모델을 TensorRT 엔진으로 변환하는 1회성 스크립트.
# 생성된 .engine 파일은 .pt와 같은 디렉터리에 저장되며,
# 서버 시작 시 YOLODetector가 자동으로 감지해 TRT 모드로 실행한다.
# Jetson Orin Nano(SM87) 전용 — 다른 기기에서 생성한 엔진은 사용 불가.
#
# 사용법:
#   cd /home/aim0419/withcue_v2.0/backend
#   python scripts/export_trt.py
#
# 변환 시간: yolov8s-pose 기준 약 5~10분 소요.
# 완료 후 .engine 파일이 생성되면 이후 서버 기동 시 TRT 모드로 자동 전환된다.

import sys
import time
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 프로젝트 루트를 sys.path에 추가해 app.core.config를 임포트할 수 있게 함
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings


def export():
    pt_path = Path(settings.yolo_model_path)
    engine_path = pt_path.with_suffix(".engine")

    if not pt_path.exists():
        logger.error("모델 파일을 찾을 수 없습니다: %s", pt_path)
        sys.exit(1)

    if engine_path.exists():
        logger.info("이미 TRT 엔진이 존재합니다: %s", engine_path)
        logger.info("재변환이 필요하면 해당 파일을 삭제 후 다시 실행하세요.")
        return

    logger.info("변환 시작: %s → %s", pt_path.name, engine_path.name)
    logger.info("Jetson Orin Nano(SM87) 기준 약 5~10분 소요됩니다.")

    from ultralytics import YOLO
    model = YOLO(str(pt_path))

    t0 = time.time()
    model.export(
        format="engine",
        imgsz=640,
        device=0,       # GPU 0번(Jetson 통합 GPU)
        half=True,      # FP16 — Jetson Ampere에서 2배 처리량
        simplify=True,  # ONNX 중간 그래프 단순화
        workspace=4,    # TRT 빌더 메모리 한도(GiB). Jetson 통합 메모리 고려해 4로 제한
    )
    elapsed = time.time() - t0

    if engine_path.exists():
        size_mb = engine_path.stat().st_size / (1024 * 1024)
        logger.info("변환 완료. 소요 시간: %.1f초 / 엔진 크기: %.1fMB", elapsed, size_mb)
        logger.info("엔진 위치: %s", engine_path)
        logger.info("다음 서버 기동 시 TRT 모드로 자동 실행됩니다.")
    else:
        logger.error("변환 후 .engine 파일을 찾을 수 없습니다. 출력 로그를 확인하세요.")
        sys.exit(1)


if __name__ == "__main__":
    export()
