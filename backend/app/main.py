import uvicorn
import torch
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# 작성한 라우터 모듈 임포트
from app.api.v1.api import router as api_router
from app.api.v1.system import router as system_router
from app.api.v1.auth import router as auth_router
from app.api.v1.session import router as session_router
from app.hardware.camera import camera_manager
from app.core.database import init_db
from app.core.config import settings
from app.core.gpu_debug import log_gpu_snapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# [핵심] 모듈별 logger를 사용해 운영 시 로그 레벨/출력을 제어하기 쉽게 구성
logger = logging.getLogger(__name__)

if torch.cuda.is_available():
    torch.backends.cudnn.enabled = False
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True

# 서버 종료 시 카메라를 확실하게 끄기 위함
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ====== [Startup: 시스템 시작] ======
    logger.info("Startup sequence initiated.")
    # [조현석] YOLO 로드 실패 시에도 state 속성 자체는 항상 존재하게 만들어 WS 진입 시 AttributeError가 나지 않도록 합니다.
    app.state.yolo_model = None
    # [조현석] 일별 정확도 저장 테이블이 운영 DB에 없어서 기록이 누락되는 문제를 막기 위해 시작 시 스키마를 보장합니다.
    init_db()
    logger.info("Database schema ensured.")

    # [임시 테스트 모드] 모델이 아직 없을 때도 서버/WS 통신 검증이 가능하도록 분기
    # .env의 MOCK_PIPELINE_MODE=true면 YOLO를 로드하지 않습니다.
    if settings.mock_pipeline_mode:
        logger.info("MOCK_PIPELINE_MODE=true -> YOLO load skipped.")
    else:
        # [실제 운영 모드] YOLO 모델 로드
        # 앱 시작 시 한 번만 실행되며, GPU 메모리에 상주합니다.
        try:
            # [중요] mock 모드에서 불필요한 의존성 로딩을 피하기 위해 여기서 지연 import
            from app.services.ai_service import YOLODetector
            logger.info("Loading YOLO Pose model...")
            log_gpu_snapshot("before_model_load")
            model_path = settings.yolo_model_path

            # 모델 로드
            detector = YOLODetector(model_path)
            log_gpu_snapshot("after_model_load")

            # [추가] 미리 한 번 실행해서 메모리 공간 확보
            # 이거 안하면 첫 접속자가 들어올 때 렉이 걸리거나 메모리가 터질 수 있습니다.
            detector.warmup()
            log_gpu_snapshot("after_model_warmup")

            app.state.yolo_model = detector
            logger.info("YOLO model ready.")

        except Exception as e:
            logger.exception("Failed to load YOLO model: %s", e)
            # 모델 로드 실패 시 서버를 띄울지 말지 결정해야 하지만, 일단 로그만 남김
        
    yield
    # ====== [Shutdown: 시스템 종료] ======
    logger.info("Shutdown sequence initiated.")
    
    # 2. 카메라 리소스 해제
    try:
        if camera_manager.active:
            camera_manager.stop()
        logger.info("Camera resource released.")
    except Exception as e:
        logger.exception("Error releasing camera: %s", e)
        
    # 3. GPU 메모리 정리 
    if hasattr(app.state, 'yolo_model'):
        del app.state.yolo_model
        logger.info("Model unloaded.")
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            log_gpu_snapshot("after_cuda_empty_cache")
            logger.info("CUDA memory cache cleared.")
        
# 앱 초기화
app = FastAPI(
    title="WithCue Backend API",
    description="Jetson Orin Nano + RealSense를 활용한 재활 운동 코칭 서버",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 실제 배포 시에는 구체적인 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(system_router, prefix="/api/v1/system", tags=["System"])
# 조현석API통신테스트: 프론트가 호출하는 주요 API/WS 라우터 등록 지점
app.include_router(api_router, prefix="/api/v1")
# 조현석API통신테스트: 프론트 회원가입/로그인 API 라우터 등록 지점
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Auth"])
# 조현석API통신테스트: 프론트 세션 이력 조회 API 라우터 등록 지점
app.include_router(session_router, prefix="/api/v1/sessions", tags=["Sessions"])

@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "WithCue Backend Server is Running!",
        "device": "Jetson Orin Nano",
        "docs_url": settings.docs_url,
    }
    
@app.get("/test")
async def get_test_page():
    # 현재 실행 위치에 있는 test_client.html 파일을 찾아서 반환
    file_path = "test_client.html"
    
    # 혹시 파일이 없다면 에러 방지
    if not os.path.exists(file_path):
        return {"error": "test_client.html 파일을 찾을 수 없습니다. 프로젝트 루트 폴더에 있는지 확인해주세요."}
        
    return FileResponse(file_path)
