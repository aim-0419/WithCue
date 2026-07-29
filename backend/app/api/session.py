# 운동 세션 이력과 일별/주간 정확도 데이터를 조회·저장하는 API 라우터.
# 로그인한 사용자의 최근 운동 기록과 주간 점수 차트 데이터를 제공한다.
# 일부 엔드포인트는 비로그인 상태에서도 접근할 수 있도록 선택적 인증을 사용한다.

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
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


# 현재 로그인한 사용자의 최근 운동 세션 목록을 반환하는 엔드포인트.
# 매개변수: limit - 조회할 최대 세션 수(기본 10, 최대 50).
# 반환값: 최근 운동 세션 목록.
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


# 특정 날짜의 운동 정확도를 저장하거나 이미 있으면 업데이트(upsert)하는 엔드포인트.
# 매개변수: payload - 정확도(%), 측정 날짜, 운동 종류 정보를 담은 요청 바디.
# 반환값: 저장된 기록의 ID, 날짜, 정확도.
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


# 특정 주(週)의 일별 정확도를 7일 단위로 집계해 반환하는 엔드포인트.
# 프론트엔드 주간 점수 차트에서 사용한다.
# 매개변수: base_date - 기준 날짜(없으면 오늘). source_type·source_key - 운동 종류 필터.
# 반환값: 7일간 날짜별 정확도 목록.
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


# 일별 정확도 전체 이력을 목록 형태로 반환하는 엔드포인트.
# 매개변수: source_type·source_key - 운동 종류 필터. limit - 최대 조회 개수(기본 30, 최대 200).
# 반환값: 날짜별 정확도 기록 목록.
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


# 현재 사용자의 운동 세션 목록을 기간/운동 종류로 필터링해 반환한다. (운동기록 달력/대시보드)
# 매개변수: from/to - 기간(날짜), exercise - 운동 코드 필터, limit - 최대 건수.
@router.get("")
def list_sessions(
    from_date: date | None = Query(None, alias="from"),
    to_date: date | None = Query(None, alias="to"),
    exercise: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = SessionService.list_sessions(
        db,
        user_id=current_user.user_id,
        from_date=from_date,
        to_date=to_date,
        exercise_code=exercise,
        limit=limit,
    )
    return {"items": items}


# 세션 1건의 상세(요약 + rep별 정확도/각도/라벨)를 반환한다. 본인 세션만 접근 가능.
@router.get("/{session_id}")
def get_session_detail(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    detail = SessionService.get_session_detail(db, user_id=current_user.user_id, session_id=session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return detail
