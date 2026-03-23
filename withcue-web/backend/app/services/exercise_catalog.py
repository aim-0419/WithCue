from dataclasses import dataclass
from typing import Dict, List, Optional, Any


# 프론트의 part 쿼리값 -> 내부 측정 스테이지명 매핑
# 이 파일에 매핑을 모아두면, 라우터 코드(api.py)를 수정하지 않고도 확장이 쉽습니다.
PART_TO_MEASURE_STAGE: Dict[str, str] = {
    "shoulder": "SHOULDER_ABDUCTION",
    "hip": "SIDE_LEG_RAISE",
    "knee_left": "LEFT_KNEE_FLEXION",
    "knee_right": "RIGHT_KNEE_FLEXION",
}


@dataclass(frozen=True)
class ExerciseRuntimeConfig:
    """
    운동 ID별 런타임 설정.
    - stage: 현재 코칭 로직에서 사용할 내부 스테이지명
    - model_key: 추후 모델별 후처리/임계치 분기 시 사용할 키
    - default_limit: 프론트가 limit을 안 보낼 때 기본 목표각
    - enabled: 운영 중 노출/차단을 빠르게 제어하기 위한 플래그
    """

    exercise_id: str
    stage: str
    model_key: str
    default_limit: int
    enabled: bool = True


# 프론트 운동 ID별 실행 설정 레지스트리
# 이후 실제 모델이 추가되면 여기서 model_key, stage를 운동별로 분리하면 됩니다.
EXERCISE_REGISTRY: Dict[str, ExerciseRuntimeConfig] = {
    "sh-001": ExerciseRuntimeConfig(
        exercise_id="sh-001",
        stage="SHOULDER_EXTERNAL_ROTATION",
        model_key="shoulder_v1",
        default_limit=45,
    ),
    "sh-002": ExerciseRuntimeConfig(
        exercise_id="sh-002",
        stage="SHOULDER_EXTERNAL_ROTATION",
        model_key="shoulder_v1",
        default_limit=45,
    ),
    "hip-001": ExerciseRuntimeConfig(
        exercise_id="hip-001",
        stage="SHOULDER_EXTERNAL_ROTATION",
        model_key="hip_v1_placeholder",
        default_limit=45,
    ),
    "kn-001": ExerciseRuntimeConfig(
        exercise_id="kn-001",
        stage="SHOULDER_EXTERNAL_ROTATION",
        model_key="knee_v1_placeholder",
        default_limit=45,
    ),
}


def parse_measure_schedule(parts_query: Optional[str]) -> Optional[List[str]]:
    """
    측정 요청(parts=a,b,c)을 내부 스테이지 리스트로 변환합니다.
    - 유효한 값이 하나도 없으면 None 반환 (프로세서 기본 스케줄 사용)
    - 중복 파트 입력은 첫 1회만 반영
    """
    if not parts_query:
        return None

    parsed: List[str] = []
    seen = set()

    for raw in parts_query.split(","):
        key = raw.strip().lower()
        stage = PART_TO_MEASURE_STAGE.get(key)
        if not stage:
            continue
        if stage in seen:
            continue
        seen.add(stage)
        parsed.append(stage)

    return parsed or None


def resolve_coaching_stage(exercise_id_or_name: str) -> Optional[str]:
    """
    코칭 경로 파라미터를 내부 스테이지명으로 해석합니다.
    1) 프론트 exerciseId(sh-001 등) 매핑 우선
    2) 내부 스테이지명을 직접 보냈을 때도 허용
    """
    if not exercise_id_or_name:
        return None

    key = exercise_id_or_name.strip().lower()
    config = EXERCISE_REGISTRY.get(key)
    if config and config.enabled:
        return config.stage

    # 운영/디버그 편의: 내부 스테이지명 직접 입력도 허용
    normalized = exercise_id_or_name.strip().upper()
    if normalized in {cfg.stage for cfg in EXERCISE_REGISTRY.values()}:
        return normalized

    return None


def resolve_limit(exercise_id_or_name: str, requested_limit: Optional[int]) -> int:
    """
    코칭 목표각 우선순위:
    1) 프론트 쿼리 limit
    2) 운동별 default_limit
    3) 시스템 기본값 45
    """
    if requested_limit is not None:
        return requested_limit

    key = exercise_id_or_name.strip().lower() if exercise_id_or_name else ""
    config = EXERCISE_REGISTRY.get(key)
    if config:
        return config.default_limit
    return 45


def list_exercises_for_client() -> List[Dict[str, Any]]:
    """
    프론트가 운동 목록을 API로 받아 쓸 수 있도록 최소 메타를 제공합니다.
    (현재 프론트는 하드코딩이지만, 추후 교체를 쉽게 하려는 목적입니다.)
    """
    items: List[Dict[str, Any]] = []
    for cfg in EXERCISE_REGISTRY.values():
        items.append(
            {
                "exercise_id": cfg.exercise_id,
                "stage": cfg.stage,
                "model_key": cfg.model_key,
                "default_limit": cfg.default_limit,
                "enabled": cfg.enabled,
            }
        )
    return items
