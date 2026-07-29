# 운동 세션 기록 및 정확도 통계에 사용되는 데이터 구조(스키마)를 정의하는 모듈.
# 최근 운동 이력 조회, 일별 정확도 저장 요청, 주간 차트 응답 등
# 세션 관련 API에서 주고받는 데이터 형식을 고정합니다.

from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel


# 최근 운동 세션 목록에서 각 항목 하나를 표현하는 구조.
# 화면에서 '최근 운동 기록' 카드 하나에 해당합니다.
class RecentSessionItem(BaseModel):
    session_id: int
    exercise_id: int
    exercise_name: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    status: str
    total_reps: Optional[int] = None
    overall_accuracy_pct: Optional[float] = None


# 특정 날짜의 정확도를 저장(또는 덮어쓰기)하는 요청 구조.
# 운동 또는 측정 결과를 일별 기록으로 남길 때 사용합니다.
class DailyAccuracyUpsertRequest(BaseModel):
    accuracy_pct: float
    source_type: str = "exercise"
    source_key: Optional[str] = None
    measured_on: Optional[date] = None


# 주간 차트에서 요일별 점수 하나를 표현하는 구조.
# name은 '월', '화' 같은 요일 레이블이고 score는 0~100 정수입니다.
class DailyAccuracyItem(BaseModel):
    name: str
    date: date
    score: int


# 정확도 기록 이력 목록에서 항목 하나를 표현하는 구조.
# 언제, 어떤 출처(운동/측정)로 기록된 점수인지를 담습니다.
class DailyAccuracyHistoryItem(BaseModel):
    measured_on: date
    accuracy_pct: int
    source_type: str
    source_key: Optional[str] = None
    recorded_at: datetime


# 주간 정확도 차트 API의 응답 구조.
# 월~일 7개 항목 리스트와 가장 최근 정확도 값을 함께 반환합니다.
class WeeklyAccuracyResponse(BaseModel):
    items: List[DailyAccuracyItem]
    latest_accuracy: Optional[int] = None
