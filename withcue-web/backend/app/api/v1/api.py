from fastapi import APIRouter, WebSocket, Query
from typing import Optional
from app.core.config import settings
from app.services.mock_ws_service import run_mock_measure_flow, run_mock_coach_flow
from app.services.exercise_catalog import (
    parse_measure_schedule,
    resolve_coaching_stage,
    resolve_limit,
    list_exercises_for_client,
)

router = APIRouter()


async def _send_model_unavailable(websocket: WebSocket, *, mode: str, message: str):
    await websocket.accept()
    await websocket.send_json(
        {
            "type": "frame",
            "jpeg_b64": None,
            "data": {
                "mode": mode,
                "status": "error",
                "message": message,
                "feedback": message,
                "keypoints": {},
                "frame_w": 1280,
                "frame_h": 720,
            },
        }
    )
    await websocket.close(code=1011, reason="model_unavailable")

@router.get("/exercises")
def get_exercise_catalog():
    # 조현석API통신테스트: 프론트 운동 선택 화면과 백엔드 목록 API 연동 지점
    # [핵심] 프론트 하드코딩 의존을 줄이기 위한 운동 카탈로그 조회 API
    # 프론트가 운동 ID를 하드코딩하지 않도록, 추후 API 기반으로 전환할 때 사용하는 목록.
    return {"items": list_exercises_for_client()}

# -----------------------------------------------------------
# [신규] 새로운 주소 (나중에 프론트엔드 수정하면 이걸 쓰라고 하세요)
# -----------------------------------------------------------
@router.websocket("/ws/measure")
async def measure_endpoint(
    websocket: WebSocket, 
    parts: Optional[str] = Query(None)
):
    # 조현석API통신테스트: 프론트 측정 모드 WebSocket 연동 지점
    # [임시 테스트 모드] 모델/카메라 없이 프론트 WS 통신부터 확인할 때 사용
    # .env의 MOCK_PIPELINE_MODE=true 이면 아래 mock 경로로 진입합니다.
    if settings.mock_pipeline_mode:
        await run_mock_measure_flow(websocket, parts=parts)
        return

    yolo_model = getattr(websocket.app.state, "yolo_model", None)
    if yolo_model is None:
        await _send_model_unavailable(
            websocket,
            mode="MEASURE",
            message="서버에서 YOLO 모델을 로드하지 못했습니다. 백엔드 로그를 확인해주세요.",
        )
        return

    # [실제 운영 모드] 실시간 측정 WS 진입점: 라우터는 입력 파싱만 하고 로직은 서비스/프로세서로 위임
    # [중요] mock 모드에서는 필요 없는 무거운 모듈을 지연 import로 분리
    from app.services.motion_service import MotionService
    from app.services.processors import MeasurementProcessor

    # 1. 연결 서비스 생성
    service = MotionService(websocket, yolo_model)
    
    # 2. 쿼리(parts=...)를 내부 측정 스케줄로 변환
    # 유효한 값이 없으면 None -> MeasurementProcessor 기본 스케줄 사용
    target_list = parse_measure_schedule(parts)
        
    # 3. 프로세서에 '할 일 목록' 전달
    processor = MeasurementProcessor(target_schedule=target_list)
    service.set_processor(processor)
    await service.start()

@router.websocket("/ws/coach/{exercise}")
async def coach_endpoint(
    websocket: WebSocket,
    exercise: str,
    limit: Optional[int] = Query(None, ge=1, le=180),
):
    # 조현석API통신테스트: 프론트 코칭 모드 WebSocket 연동 지점
    # [임시 테스트 모드] 모델/카메라 없이 코칭 WS 통신 확인
    # mock 모드에서는 exercise, limit만 echo 하며 프론트 실시간 렌더링 동작을 검증합니다.
    if settings.mock_pipeline_mode:
        target_limit = resolve_limit(exercise, limit)
        await run_mock_coach_flow(websocket, exercise=exercise, limit=target_limit)
        return

    yolo_model = getattr(websocket.app.state, "yolo_model", None)
    if yolo_model is None:
        await _send_model_unavailable(
            websocket,
            mode="COACH",
            message="서버에서 YOLO 모델을 로드하지 못했습니다. 백엔드 로그를 확인해주세요.",
        )
        return

    # [실제 운영 모드] 실시간 코칭 WS 진입점: 운동 ID와 목표각(limit)을 내부 실행 설정으로 변환
    # [중요] mock 모드에서는 필요 없는 무거운 모듈을 지연 import로 분리
    from app.services.motion_service import MotionService
    from app.services.processors import CoachingProcessor

    # 1. 연결 서비스 생성
    service = MotionService(websocket, yolo_model)
    
    # 2. URL path exerciseId를 내부 스테이지명으로 변환
    exercise_name = resolve_coaching_stage(exercise)
    
    if not exercise_name:
        await websocket.send_json({ "mode": "ERROR", "feedback": f"알 수 없는 운동: {exercise}" })
        return
    
    # 3. 목표각은 "요청값 > 운동 기본값 > 시스템 기본값" 우선순위로 결정
    # 모델/운동별 설정이 늘어나도 라우터 코드를 바꾸지 않기 위한 구조입니다.
    target_limit = resolve_limit(exercise, limit)
    processor = CoachingProcessor(exercise_name=exercise_name, limit_angle=target_limit)
    service.set_processor(processor)
    await service.start()
