# 서버 전체에서 사용하는 환경 설정값을 .env 파일에서 읽어 제공하는 모듈.
# 데이터베이스 주소, 인증 키, YOLO 모델 경로, TTS 활성화 여부 등을 한 곳에서 관리한다.
# 각 모듈에서 직접 os.getenv를 호출하는 대신 이 파일의 settings 객체를 사용한다.

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# 프로젝트 공통 설정은 이 파일에서만 읽도록 고정합니다.
# 나중에 환경값이 늘어나도 각 모듈에서 os.getenv를 직접 호출하지 않게 하기 위함입니다.
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(ENV_PATH)
BASE_DIR = ENV_PATH.parent


# 서버 전체 설정값을 담는 불변(frozen) 데이터 클래스.
# 인스턴스 생성 후에는 값을 변경할 수 없어 런타임 중 의도치 않은 설정 변경을 방지한다.
@dataclass(frozen=True)
class Settings:
    # [핵심] 설정 타입을 고정해 오타/누락으로 인한 런타임 오류를 줄입니다.
    database_url: str
    auth_secret_key: str
    auth_token_ttl_seconds: int
    yolo_model_path: str
    docs_url: str
    mock_pipeline_mode: bool
    # [조현석] 시연/개발 중 백엔드 장비 스피커 소음 이슈가 있어 TTS를 환경변수로 즉시 차단할 수 있게 분리합니다.
    tts_enabled: bool


# .env 파일 또는 환경 변수를 읽어 Settings 객체를 생성해 반환하는 함수.
# .env에 값이 없으면 코드에 정의된 기본값을 사용한다.
# 반환값: 모든 설정이 채워진 Settings 인스턴스.
def _load_settings() -> Settings:
    # [핵심] 기본값을 코드에 두되, 운영에서는 .env 값으로 오버라이드 가능
    raw_yolo_model_path = os.getenv("YOLO_MODEL_PATH", "app/assets/models/yolov8n-pose.pt")
    yolo_model_path = Path(raw_yolo_model_path)
    if not yolo_model_path.is_absolute():
        yolo_model_path = (BASE_DIR / yolo_model_path).resolve()

    return Settings(
        database_url=os.getenv(
            "DATABASE_URL",
            "mysql+pymysql://root:password@localhost:3306/withcue?charset=utf8mb4",
        ),
        auth_secret_key=os.getenv("AUTH_SECRET_KEY", "dev-change-this-secret"),
        auth_token_ttl_seconds=int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "86400")),
        yolo_model_path=str(yolo_model_path),
        docs_url=os.getenv("DOCS_URL", "http://localhost:8018/docs"),
        mock_pipeline_mode=os.getenv("MOCK_PIPELINE_MODE", "false").lower() == "true",
        tts_enabled=os.getenv("TTS_ENABLED", "true").lower() == "true",
    )


# 애플리케이션 전역에서 사용하는 설정 싱글턴 인스턴스.
# 다른 모듈에서 from app.core.config import settings 로 가져다 쓴다.
settings = _load_settings()
