# 검사(ROM) 측정 결과를 조회하는 API 라우터.
# 현재 ROM 값(검사결과 화면)과 rom_key별 추이(대시보드)를 로그인 사용자 기준으로 제공한다.

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import User, get_db
from app.services.session_service import SessionService

router = APIRouter()


# 현재 사용자의 최신(is_current) ROM 값을 rom_key: angle 딕셔너리로 반환한다. (검사결과 화면)
@router.get("/latest")
def get_rom_latest(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SessionService.get_rom_latest(db, user_id=current_user.user_id)


# 특정 rom_key의 측정 이력을 시간순으로 반환한다. (ROM 추이)
@router.get("/history")
def get_rom_history(
    key: str = Query(..., description="rom_key (예: neck_rotation_left_max)"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = SessionService.get_rom_history(db, user_id=current_user.user_id, rom_key=key, limit=limit)
    return {"key": key, "items": items}


# ROM 측정 기록이 있는 날짜 목록을 반환한다. (기록 달력 색점 표시용)
@router.get("/dates")
def get_rom_dates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dates = SessionService.get_rom_dates(db, user_id=current_user.user_id)
    return {"dates": dates}


# 특정 날짜의 ROM 스냅샷을 반환한다. (기록 달력 상세 패널용)
@router.get("/snapshot")
def get_rom_snapshot(
    date: str = Query(..., description="날짜 (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SessionService.get_rom_snapshot(db, user_id=current_user.user_id, date_str=date)
