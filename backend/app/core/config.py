import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# 프로젝트 공통 설정은 이 파일에서만 읽도록 고정합니다.
# 나중에 환경값이 늘어나도 각 모듈에서 os.getenv를 직접 호출하지 않게 하기 위함입니다.
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(ENV_PATH)
BASE_DIR = ENV_PATH.parent


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


settings = _load_settings()
