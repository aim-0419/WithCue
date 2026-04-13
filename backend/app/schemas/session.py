from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel


class RecentSessionItem(BaseModel):
    session_id: int
    exercise_id: int
    exercise_name: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    status: str
    total_reps: Optional[int] = None
    overall_accuracy_pct: Optional[float] = None


class DailyAccuracyUpsertRequest(BaseModel):
    accuracy_pct: float
    source_type: str = "exercise"
    source_key: Optional[str] = None
    measured_on: Optional[date] = None


class DailyAccuracyItem(BaseModel):
    name: str
    date: date
    score: int


class DailyAccuracyHistoryItem(BaseModel):
    measured_on: date
    accuracy_pct: int
    source_type: str
    source_key: Optional[str] = None
    recorded_at: datetime


class WeeklyAccuracyResponse(BaseModel):
    items: List[DailyAccuracyItem]
    latest_accuracy: Optional[int] = None
