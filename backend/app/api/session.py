from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_optional_current_user
from app.core.database import User, get_db
from app.schemas.session import (
    DailyAccuracyHistoryItem,
    DailyAccuracyUpsertRequest,
    WeeklyAccuracyResponse,
)
from app.services.session_service import SessionService

router = APIRouter()


@router.get("/recent")
def get_recent_sessions(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # [핵심] user_id 파라미터를 받지 않고 토큰의 사용자 기준으로만 조회
    # -> 타인 user_id를 넣어 데이터 열람하는 취약점을 차단합니다.
    items = SessionService.list_recent_sessions(db, user_id=current_user.user_id, limit=limit)
    return {"items": items}


@router.post("/accuracy-history")
def upsert_daily_accuracy(
    payload: DailyAccuracyUpsertRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    # [조현석] 운동 종료 시 프론트가 마지막 정확도를 서버에 남길 수 있게 별도 저장 엔드포인트를 둡니다.
    measured_on = payload.measured_on or date.today()
    entry = SessionService.save_daily_accuracy(
        db,
        accuracy_pct=payload.accuracy_pct,
        measured_on=measured_on,
        source_type=payload.source_type,
        source_key=payload.source_key,
        user_id=current_user.user_id if current_user else None,
    )
    return {
        "history_id": entry.history_id,
        "measured_on": str(entry.measured_on),
        "accuracy_pct": int(round(float(entry.accuracy_pct))),
    }


@router.get("/accuracy-history/weekly", response_model=WeeklyAccuracyResponse)
def get_weekly_accuracy(
    base_date: date | None = Query(None),
    source_type: str | None = Query(None),
    source_key: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    # [조현석] 메인 차트는 브라우저 로컬값이 아니라 DB 기준 주간 데이터로 그리기 위해 전용 조회 엔드포인트를 제공합니다.
    return SessionService.get_weekly_accuracy(
        db,
        base_date=base_date,
        user_id=current_user.user_id if current_user else None,
        source_type=source_type,
        source_key=source_key,
    )


@router.get("/accuracy-history", response_model=list[DailyAccuracyHistoryItem])
def list_accuracy_history(
    source_type: str | None = Query(None),
    source_key: str | None = Query(None),
    limit: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    return SessionService.list_accuracy_history(
        db,
        user_id=current_user.user_id if current_user else None,
        source_type=source_type,
        source_key=source_key,
        limit=limit,
    )
