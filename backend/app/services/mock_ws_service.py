import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from app.services.score_service import (
    AccuracyState,
    build_deviation_flags,
    deviation_penalty,
    recovery_bonus,
    update_accuracy,
)


async def run_mock_measure_flow(websocket: WebSocket, parts: str | None = None):
    """
    모델/카메라가 없는 개발 단계용 Mock 측정 스트림.
    실제 프레임 없이도 프론트의 WS 상태 전환 로직을 검증할 수 있습니다.
    """
    await websocket.accept()

    stage = "SHOULDER_ABDUCTION"
    if parts:
        stage = parts.split(",")[0].strip().upper() or stage

    timeline = [
        {"status": "preparing", "message": "MOCK: 자세를 준비해주세요", "timer": 3, "progress": "1/1"},
        {"status": "preparing", "message": "MOCK: 3초 후 시작", "timer": 2, "progress": "1/1"},
        {"status": "transition", "message": "MOCK: 측정을 시작합니다"},
        {
            "status": "measuring",
            "angle": 18,
            "max_angle": 18,
            "timer": 3,
            "progress": "1/1",
            "trunk_sway_excess_deg": 4,
            "opposite_limb_excess_deg": 0,
            "elbow_flex_excess_deg": 2,
        },
        {
            "status": "measuring",
            "angle": 31,
            "max_angle": 31,
            "timer": 2,
            "progress": "1/1",
            "trunk_sway_excess_deg": 8,
            "opposite_limb_excess_deg": 5,
            "elbow_flex_excess_deg": 4,
        },
        {
            "status": "holding",
            "angle": 34,
            "max_angle": 34,
            "timer": 2,
            "message": "MOCK: 자세 회복 중",
            "progress": "1/1",
            "trunk_sway_excess_deg": 0,
            "opposite_limb_excess_deg": 0,
            "elbow_flex_excess_deg": 0,
        },
        {"status": "stage_finished", "stage": stage, "max_angle": 34, "message": "MOCK: 부위 측정 완료"},
        {"status": "finished", "message": "MOCK: 전체 측정 완료"},
    ]

    accuracy_state = AccuracyState()

    last_payload = None

    try:
        for data in timeline:
            trunk_penalty = deviation_penalty(
                data.get("trunk_sway_excess_deg", 0.0),
                unit_penalty=1.2,
                max_penalty=12.0,
            )
            opposite_limb_penalty = deviation_penalty(
                data.get("opposite_limb_excess_deg", 0.0),
                unit_penalty=1.0,
                max_penalty=10.0,
            )
            elbow_penalty = deviation_penalty(
                data.get("elbow_flex_excess_deg", 0.0),
                unit_penalty=1.5,
                max_penalty=15.0,
            )
            penalty_delta_pct = round(trunk_penalty + opposite_limb_penalty + elbow_penalty, 2)
            recovery_delta_pct = recovery_bonus(posture_stable=penalty_delta_pct == 0.0, bonus=5.0)
            accuracy_state = update_accuracy(
                accuracy_state,
                penalty_delta_pct=penalty_delta_pct,
                recovery_delta_pct=recovery_delta_pct,
            )
            deviation_flags = build_deviation_flags(
                trunk_sway_excess_deg=data.get("trunk_sway_excess_deg", 0.0),
                opposite_limb_excess_deg=data.get("opposite_limb_excess_deg", 0.0),
                elbow_flex_excess_deg=data.get("elbow_flex_excess_deg", 0.0),
            )

            last_payload = {
                "type": "frame",
                "jpeg_b64": None,
                "data": {
                    "stage": stage,
                    "keypoints": {},
                    "frame_w": 1280,
                    "frame_h": 720,
                    "accuracy_pct": accuracy_state.accuracy_pct,
                    "min_accuracy_pct": accuracy_state.min_accuracy_pct,
                    "penalty_delta_pct": penalty_delta_pct,
                    "recovery_delta_pct": recovery_delta_pct,
                    "deviation_flags": deviation_flags,
                    **data,
                },
            }
            await websocket.send_json(last_payload)
            await asyncio.sleep(0.4)

        # 개발 모드에서는 연결을 유지해 프론트가 즉시 closed 상태로 떨어지지 않게 합니다.
        # 사용자가 화면을 나가면 그때 disconnect 예외로 자연 종료됩니다.
        while True:
            await asyncio.sleep(1.0)
            if last_payload is None:
                continue
            await websocket.send_json(last_payload)
    except WebSocketDisconnect:
        return


async def run_mock_coach_flow(websocket: WebSocket, exercise: str, limit: int):
    """
    모델/카메라가 없는 개발 단계용 Mock 코칭 스트림.
    프론트에서 실시간 피드백 텍스트/각도 갱신이 되는지만 확인합니다.
    """
    await websocket.accept()

    steps = [
        {"angle": 12, "feedback": "MOCK: 자세를 맞춰주세요", "accuracy_pct": 92},
        {"angle": 28, "feedback": "MOCK: 좋아요, 조금 더", "accuracy_pct": 85},
        {"angle": 41, "feedback": "MOCK: 매우 좋습니다", "accuracy_pct": 81},
        {"angle": limit, "feedback": "MOCK: 목표 각도 도달", "accuracy_pct": 88},
    ]

    last_payload = None

    try:
        for step in steps:
            last_payload = {
                "type": "frame",
                "jpeg_b64": None,
                "data": {
                    "mode": "COACH",
                    "exercise": exercise,
                    "target_angle": limit,
                    "keypoints": {},
                    "frame_w": 1280,
                    "frame_h": 720,
                    **step,
                },
            }
            await websocket.send_json(last_payload)
            await asyncio.sleep(0.5)

        while True:
            await asyncio.sleep(1.0)
            if last_payload is None:
                continue
            await websocket.send_json(last_payload)
    except WebSocketDisconnect:
        return
