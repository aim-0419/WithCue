from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.database import DailyAccuracyHistory, ExerciseSession, ExerciseSessionSummary, RehabExercise
from app.schemas.session import DailyAccuracyItem, RecentSessionItem, WeeklyAccuracyResponse


class SessionService:
    """세션 기록 조회 관련 도메인 로직."""

    WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"]

    @staticmethod
    def list_recent_sessions(db: Session, *, user_id: int, limit: int = 10) -> List[RecentSessionItem]:
        # [핵심] 화면 렌더링에 필요한 필드를 join 1회로 조회해 N+1 쿼리를 방지
        # 세션 + 운동명 + 요약점수를 한 번에 가져와 프론트에서 바로 사용 가능한 형태로 변환
        rows = (
            db.query(
                ExerciseSession,
                RehabExercise.exercise_name,
                ExerciseSessionSummary.total_reps,
                ExerciseSessionSummary.overall_accuracy_pct,
            )
            .join(RehabExercise, RehabExercise.exercise_id == ExerciseSession.exercise_id)
            .outerjoin(
                ExerciseSessionSummary,
                ExerciseSessionSummary.session_id == ExerciseSession.session_id,
            )
            .filter(ExerciseSession.user_id == user_id)
            .order_by(ExerciseSession.started_at.desc())
            .limit(limit)
            .all()
        )

        items: List[RecentSessionItem] = []
        for session, exercise_name, total_reps, overall_accuracy_pct in rows:
            items.append(
                RecentSessionItem(
                    session_id=session.session_id,
                    exercise_id=session.exercise_id,
                    exercise_name=exercise_name,
                    started_at=session.started_at,
                    ended_at=session.ended_at,
                    status=session.status,
                    total_reps=total_reps,
                    overall_accuracy_pct=float(overall_accuracy_pct) if overall_accuracy_pct is not None else None,
                )
            )
        return items

    @staticmethod
    def save_daily_accuracy(
        db: Session,
        *,
        accuracy_pct: float,
        measured_on: date,
        source_type: str,
        source_key: Optional[str],
        user_id: Optional[int],
    ) -> DailyAccuracyHistory:
        # [조현석] 같은 날 여러 번 운동해도 메인 주간 점수는 "그날 마지막 결과 1건"만 보이도록 upsert 방식으로 저장합니다.
        clamped = max(0, min(100, round(accuracy_pct)))

        query = db.query(DailyAccuracyHistory).filter(DailyAccuracyHistory.measured_on == measured_on)
        if user_id is None:
            query = query.filter(DailyAccuracyHistory.user_id.is_(None))
        else:
            query = query.filter(DailyAccuracyHistory.user_id == user_id)

        entry = query.one_or_none()
        if entry is None:
            entry = DailyAccuracyHistory(
                user_id=user_id,
                measured_on=measured_on,
                accuracy_pct=clamped,
                source_type=source_type,
                source_key=source_key,
                recorded_at=datetime.now(),
            )
            db.add(entry)
        else:
            entry.accuracy_pct = clamped
            entry.source_type = source_type
            entry.source_key = source_key
            entry.recorded_at = datetime.now()

        db.commit()
        db.refresh(entry)
        return entry

    @classmethod
    def get_weekly_accuracy(
        cls,
        db: Session,
        *,
        base_date: Optional[date],
        user_id: Optional[int],
    ) -> WeeklyAccuracyResponse:
        # [조현석] 차트 UI가 월~일 7칸 고정이라 DB 조회 결과도 같은 형태로 맞추고, 빈 날은 0점으로 채웁니다.
        current = base_date or date.today()
        monday = current - timedelta(days=(current.weekday()))
        sunday = monday + timedelta(days=6)

        query = db.query(DailyAccuracyHistory).filter(
            DailyAccuracyHistory.measured_on >= monday,
            DailyAccuracyHistory.measured_on <= sunday,
        )
        if user_id is None:
            query = query.filter(DailyAccuracyHistory.user_id.is_(None))
        else:
            query = query.filter(DailyAccuracyHistory.user_id == user_id)

        rows = query.all()
        score_by_day = {
            row.measured_on: max(0, min(100, round(float(row.accuracy_pct))))
            for row in rows
        }

        items: List[DailyAccuracyItem] = []
        for index, label in enumerate(cls.WEEKDAY_LABELS):
            target_date = monday + timedelta(days=index)
            items.append(
                DailyAccuracyItem(
                    name=label,
                    date=target_date,
                    score=score_by_day.get(target_date, 0),
                )
            )

        latest_query = db.query(DailyAccuracyHistory)
        if user_id is None:
            latest_query = latest_query.filter(DailyAccuracyHistory.user_id.is_(None))
        else:
            latest_query = latest_query.filter(DailyAccuracyHistory.user_id == user_id)

        latest_row = latest_query.order_by(DailyAccuracyHistory.recorded_at.desc()).first()
        latest_accuracy = None
        if latest_row and latest_row.accuracy_pct is not None:
            latest_accuracy = max(0, min(100, round(float(latest_row.accuracy_pct))))

        return WeeklyAccuracyResponse(items=items, latest_accuracy=latest_accuracy)
