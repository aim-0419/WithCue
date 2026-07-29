# WithCue 백엔드 서버의 진입점(Entry Point).
# FastAPI 앱을 생성하고, 시작/종료 시 카메라·GPU·YOLO 모델 자원을 안전하게 관리한다.
# CORS 허용, 정적 파일 서빙, API 라우터 등록까지 서버 전반 설정을 담당한다.

import uvicorn
import torch
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# 작성한 라우터 모듈 임포트
from app.api.api import router as api_router
from app.api.auth import router as auth_router
from app.api.session import router as session_router
from app.api.rom import router as rom_router
from app.hardware.camera import camera_manager
from app.core.database import init_db
from app.core.config import settings
from app.core.gpu_debug import log_gpu_snapshot


# 로그 레벨별로 색상을 다르게 출력해 터미널에서 한눈에 구분할 수 있게 해주는 포맷터
class ColorLogFormatter(logging.Formatter):
    RESET = "\033[0m"
    COLORS = {
        logging.DEBUG: "\033[36m",
        logging.INFO: "\033[32m",
        logging.WARNING: "\033[33m",
        logging.ERROR: "\033[31m",
        logging.CRITICAL: "\033[35m",
    }
    LABELS = {
        logging.DEBUG: "DEBUG",
        logging.INFO: "INFO ",
        logging.WARNING: "WARN ",
        logging.ERROR: "ERROR",
        logging.CRITICAL: "FATAL",
    }

    # 로그 레코드를 받아 색상 코드를 입힌 문자열로 변환해 반환한다.
    def format(self, record):
        color = self.COLORS.get(record.levelno, "")
        level = self.LABELS.get(record.levelno, record.levelname)
        record.levelname = f"{color}{level}{self.RESET}"
        return super().format(record)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
for handler in logging.getLogger().handlers:
    handler.setFormatter(
        ColorLogFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
# [핵심] 모듈별 logger를 사용해 운영 시 로그 레벨/출력을 제어하기 쉽게 구성
logger = logging.getLogger(__name__)

if torch.cuda.is_available():
    logger.info(f"CUDA available: {torch.cuda.get_device_name(0)}")
    # CUDA 캐시 관련 문제 방지
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    torch.backends.cudnn.enabled = False
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True

    # CUDA 메모리 할당 설정 최적화
    os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'max_split_size_mb:512'
else:
    logger.warning("CUDA not available. Server will run on CPU mode.")

# Ultralytics 텔레메트리·외부 연동을 모두 비활성화해 오프라인 환경에서도 안정 동작하도록 함.
# hub/sync 등이 켜진 채로 실행하면 추론 중 DNS 조회·HTTP 호출이 발생해 레이턴시에 영향을 줄 수 있다.
try:
    from ultralytics import settings as _ult_settings
    _ult_settings.update({
        "sync": False,
        "hub": False,
        "clearml": False,
        "comet": False,
        "mlflow": False,
        "neptune": False,
        "raytune": False,
        "wandb": False,
    })
    logger.info("Ultralytics 텔레메트리 비활성화 완료.")
except Exception as _e:
    logger.warning("Ultralytics 설정 변경 실패 (무시): %s", _e)

# 서버가 켜질 때(startup)와 꺼질 때(shutdown) 실행되는 생명주기 관리 함수.
# 시작 시 YOLO 모델을 GPU에 올리고, 종료 시 카메라·모델 메모리를 안전하게 해제한다.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ====== [Startup: 시스템 시작] ======
    logger.info("서버 시작 절차를 진행합니다.")
    # [조현석] YOLO 로드 실패 시에도 state 속성 자체는 항상 존재하게 만들어 WS 진입 시 AttributeError가 나지 않도록 합니다.
    app.state.yolo_model = None
    # [조현석] 일별 정확도 저장 테이블이 운영 DB에 없어서 기록이 누락되는 문제를 막기 위해 시작 시 스키마를 보장합니다.
    init_db()
    logger.info("데이터베이스 스키마 확인이 완료되었습니다.")

    # [2026-05-14] 현재 MediaPipe 사용 중, YOLO는 미사용 상태
    # 향후 YOLO 사용 시 아래를 주석 해제하면 됨
    #========== YOLO 로드 (주석 처리) ==========
    if settings.mock_pipeline_mode:
        logger.info("MOCK_PIPELINE_MODE=true 설정으로 YOLO 모델 로드를 건너뜁니다.")
    else:
        try:
            # 초기 CUDA 캐시 정리
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.reset_peak_memory_stats()
                logger.info("CUDA cache cleared before model loading")

            from app.services.ai_service import YOLODetector
            logger.info("YOLO 포즈 모델을 불러오는 중입니다.")
            model_path = settings.yolo_model_path

            if not os.path.exists(model_path):
                raise FileNotFoundError(f"YOLO model not found at {model_path}")
            logger.info(f"Model file confirmed at: {model_path}")

            detector = YOLODetector(model_path)
            logger.info("YOLO 모델 웜업 중...")
            detector.warmup()
            logger.info("YOLO 모델 웜업 완료")

            app.state.yolo_model = detector
            logger.info("✅ YOLO 모델 로드가 완료되었습니다.")

        except Exception as e:
            logger.exception(f"❌ YOLO 모델 로드에 실패했습니다: {e}")
            if torch.cuda.is_available():
                try:
                    torch.cuda.empty_cache()
                except:
                    pass
   # ========== 주석 처리 끝 ==========




    yield
    # ====== [Shutdown: 시스템 종료] ======
    logger.info("서버 종료 절차를 진행합니다.")

    # 2. 카메라 리소스 해제
    try:
        if camera_manager.active:
            camera_manager.stop()
        logger.info("카메라 리소스 정리가 완료되었습니다.")
    except Exception as e:
        logger.exception("카메라 리소스 정리 중 오류가 발생했습니다: %s", e)

    # 3. GPU 메모리 정리
    if hasattr(app.state, 'yolo_model'):
        del app.state.yolo_model
        logger.info("모델 메모리 해제가 완료되었습니다.")

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            log_gpu_snapshot("after_cuda_empty_cache")
            logger.info("CUDA 메모리 캐시 정리가 완료되었습니다.")

# 앱 초기화
app = FastAPI(
    title="WithCue Backend API",
    description="Jetson Orin Nano + RealSense를 활용한 재활 운동 코칭 서버",
    version="1.0.0",
    lifespan=lifespan
)

# Public static files (recordings/features)
public_dir = os.path.join(os.path.dirname(__file__), "public")
os.makedirs(public_dir, exist_ok=True)
app.mount("/public", StaticFiles(directory=public_dir), name="public")

# Exercise audio assets for frontend playback
assets_dir = os.path.join(os.path.dirname(__file__), "assets")
if os.path.isdir(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 실제 배포 시에는 구체적인 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
# 조현석API통신테스트: 프론트가 호출하는 주요 API/WS 라우터 등록 지점
app.include_router(api_router, prefix="/api/v1")
# 조현석API통신테스트: 프론트 회원가입/로그인 API 라우터 등록 지점
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Auth"])
# 조현석API통신테스트: 프론트 세션 이력 조회 API 라우터 등록 지점
app.include_router(session_router, prefix="/api/v1/sessions", tags=["Sessions"])
# 검사(ROM) 결과 조회 API 라우터 등록 지점
app.include_router(rom_router, prefix="/api/v1/rom", tags=["ROM"])

# 서버 동작 여부와 기본 정보를 확인하는 헬스체크 엔드포인트.
# 프론트엔드나 운영 모니터링 도구에서 서버가 살아있는지 확인할 때 사용한다.
@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "WithCue Backend Server is Running!",
        "device": "Jetson Orin Nano",
        "docs_url": settings.docs_url,
    }

# 개발·테스트용 HTML 페이지를 반환하는 엔드포인트.
# 프로젝트 루트의 test_client.html 파일을 브라우저에서 바로 열어볼 수 있다.
@app.get("/test")
async def get_test_page():
    # 현재 실행 위치에 있는 test_client.html 파일을 찾아서 반환
    file_path = "test_client.html"

    # 혹시 파일이 없다면 에러 방지
    if not os.path.exists(file_path):
        return {"error": "test_client.html 파일을 찾을 수 없습니다. 프로젝트 루트 폴더에 있는지 확인해주세요."}

    return FileResponse(file_path)
