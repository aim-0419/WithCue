# 세션 종료 시 결과를 DB에 적재하는 쓰기 전용 서비스 모듈.
# MotionService가 세션 종료(finally)에서 호출한다. 운동 세션은 ExerciseSession+Summary+Rep,
# 검사 세션은 user_rom_measurements(rom_key별 이력)에 저장한다.

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.database import (
    ExerciseRep,
    ExerciseSession,
    ExerciseSessionSummary,
    RehabExercise,
    UserRomMeasurement,
)

logger = logging.getLogger(__name__)


def _clamp_pct(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(100.0, round(float(value), 2)))


# exercise_code(WS 운동 문자열)로 rehab_exercises.exercise_id를 조회한다. 없으면 None.
def resolve_exercise_id(db: Session, exercise_code: Optional[str]) -> Optional[int]:
    if not exercise_code:
        return None
    row = db.query(RehabExercise).filter_by(exercise_code=exercise_code).first()
    return row.exercise_id if row else None


# 운동 세션 결과를 ExerciseSession + Summary + Rep(N)로 저장한다.
# reps: [{rep_no, started_at(datetime), ended_at(datetime|None), label, accuracy_pct, max_angle_deg}]
# 반환: 생성된 session_id (exercise_code 미매핑이면 None으로 스킵).
def persist_exercise_session(
    db: Session,
    *,
    user_id: int,
    exercise_code: str,
    started_at: datetime,
    ended_at: datetime,
    status: str,
    reps: List[Dict[str, Any]],
    overall_accuracy_pct: Optional[float],
    rep_accuracy_avg_pct: Optional[float],
    rom_dict: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    exercise_id = resolve_exercise_id(db, exercise_code)
    if exercise_id is None:
        logger.warning("[SessionResult] exercise_code 매핑 실패로 저장 스킵: %s", exercise_code)
        return None

    session = ExerciseSession(
        user_id=user_id,
        exercise_id=exercise_id,
        started_at=started_at,
        ended_at=ended_at,
        status=status,
    )
    db.add(session)
    db.flush()  # session_id 확보

    # rom_dict에서 숫자 값만 추려 JSON으로 저장 (리스트·None 제외)
    rom_to_save = {k: v for k, v in (rom_dict or {}).items() if isinstance(v, (int, float))}
    db.add(
        ExerciseSessionSummary(
            session_id=session.session_id,
            total_reps=len(reps),
            overall_accuracy_pct=_clamp_pct(overall_accuracy_pct),
            rep_accuracy_avg_pct=_clamp_pct(rep_accuracy_avg_pct),
            rom_json=json.dumps(rom_to_save) if rom_to_save else None,
        )
    )

    for rep in reps:
        acc = _clamp_pct(rep.get("accuracy_pct"))
        db.add(
            ExerciseRep(
                session_id=session.session_id,
                rep_no=int(rep["rep_no"]),
                rep_started_at=rep.get("started_at") or started_at,
                rep_ended_at=rep.get("ended_at"),
                max_angle_deg=round(float(rep.get("max_angle_deg") or 0.0), 4),
                rep_accuracy_pct=acc,
                label=rep.get("label"),
                min_accuracy_pct=_clamp_pct(rep.get("min_accuracy_pct", acc)),
                start_accuracy_pct=_clamp_pct(rep.get("start_accuracy_pct", acc)),
            )
        )

    db.commit()
    logger.info(
        "[SessionResult] 운동 세션 저장: session_id=%s user=%s exercise=%s reps=%d acc=%.1f",
        session.session_id, user_id, exercise_code, len(reps), _clamp_pct(overall_accuracy_pct),
    )
    return session.session_id


# 검사(ROM) 결과를 rom_key별로 저장한다. 같은 (user, rom_key)의 이전 최신값은 is_current=0으로 내린다.
# rom_dict: {rom_key: angle} (예: {"neck_rotation_left_max": 62, ...})
def persist_rom_measurements(
    db: Session,
    *,
    user_id: int,
    rom_dict: Dict[str, Any],
    measured_at: datetime,
) -> int:
    saved = 0
    for rom_key, angle in (rom_dict or {}).items():
        if angle is None or not isinstance(angle, (int, float)):
            continue
        db.query(UserRomMeasurement).filter(
            UserRomMeasurement.user_id == user_id,
            UserRomMeasurement.rom_key == rom_key,
            UserRomMeasurement.is_current.is_(True),
        ).update({"is_current": False})
        db.add(
            UserRomMeasurement(
                user_id=user_id,
                rom_key=str(rom_key),
                angle_deg=round(float(angle), 4),
                measured_at=measured_at,
                is_current=True,
            )
        )
        saved += 1
    db.commit()
    logger.info("[SessionResult] ROM 저장: user=%s keys=%d", user_id, saved)
    return saved
