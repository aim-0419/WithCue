# 운동 세션 기록 조회 및 일별/주간 정확도 통계를 처리하는 서비스 모듈.
# 최근 운동 이력 목록 조회, 정확도 기록 저장, 주간 차트 데이터 제공 등
# 세션 관련 데이터베이스 작업을 캡슐화합니다.

import json
from datetime import date, datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.database import (
    DailyAccuracyHistory,
    ExerciseRep,
    ExerciseSession,
    ExerciseSessionSummary,
    RehabExercise,
    UserRomMeasurement,
)
from app.schemas.session import (
    DailyAccuracyItem,
    DailyAccuracyHistoryItem,
    RecentSessionItem,
    WeeklyAccuracyResponse,
)


# 세션 기록 조회 및 정확도 통계 관련 모든 기능을 모아놓은 클래스.
# 외부에서 직접 인스턴스화하지 않고 정적/클래스 메서드로 사용합니다.
class SessionService:
    """세션 기록 조회 관련 도메인 로직."""

    WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"]

    # 특정 사용자의 최근 운동 세션 목록을 조회합니다.
    # 세션, 운동명, 요약 점수를 한 번의 쿼리로 가져옵니다.
    # 매개변수: db - 데이터베이스 세션 / user_id - 조회할 사용자 ID / limit - 최대 반환 건수 (기본 10)
    # 반환값: RecentSessionItem 객체 리스트
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

    # 특정 날짜의 운동 또는 측정 정확도를 데이터베이스에 저장합니다.
    # 정확도는 0~100으로 제한하여 저장합니다.
    # 매개변수: db - 데이터베이스 세션 / accuracy_pct - 저장할 정확도 / measured_on - 측정 날짜
    #           source_type - 출처 유형(exercise/measure 등) / source_key - 세부 출처 식별자 / user_id - 사용자 ID
    # 반환값: 저장된 DailyAccuracyHistory 객체
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
        # [조현석] 측정/운동 결과를 누적 기록으로 저장합니다.
        clamped = max(0, min(100, round(accuracy_pct)))
        entry = DailyAccuracyHistory(
            user_id=user_id,
            measured_on=measured_on,
            accuracy_pct=clamped,
            source_type=source_type,
            source_key=source_key,
            recorded_at=datetime.now(),
        )
        db.add(entry)

        db.commit()
        db.refresh(entry)
        return entry

    # 기준 날짜가 포함된 주의 월~일 정확도 데이터를 조회합니다.
    # 기록이 없는 날은 0점으로 채워 항상 7개 항목을 반환합니다.
    # 매개변수: db - 데이터베이스 세션 / base_date - 기준 날짜 (없으면 오늘) / user_id - 사용자 ID
    #           source_type - 필터할 출처 유형 / source_key - 필터할 세부 출처
    # 반환값: 요일별 점수 7개와 가장 최근 정확도를 담은 WeeklyAccuracyResponse
    @classmethod
    def get_weekly_accuracy(
        cls,
        db: Session,
        *,
        base_date: Optional[date],
        user_id: Optional[int],
        source_type: Optional[str] = None,
        source_key: Optional[str] = None,
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
        if source_type:
            query = query.filter(DailyAccuracyHistory.source_type == source_type)
        if source_key:
            query = query.filter(DailyAccuracyHistory.source_key == source_key)

        rows = query.all()
        score_by_day: dict[date, int] = {}
        latest_by_day: dict[date, datetime] = {}
        for row in rows:
            measured_on = row.measured_on
            recorded_at = row.recorded_at
            score = max(0, min(100, round(float(row.accuracy_pct))))
            if measured_on not in latest_by_day or recorded_at > latest_by_day[measured_on]:
                latest_by_day[measured_on] = recorded_at
                score_by_day[measured_on] = score

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
        if source_type:
            latest_query = latest_query.filter(DailyAccuracyHistory.source_type == source_type)
        if source_key:
            latest_query = latest_query.filter(DailyAccuracyHistory.source_key == source_key)

        latest_row = latest_query.order_by(DailyAccuracyHistory.recorded_at.desc()).first()
        latest_accuracy = None
        if latest_row and latest_row.accuracy_pct is not None:
            latest_accuracy = max(0, min(100, round(float(latest_row.accuracy_pct))))

        return WeeklyAccuracyResponse(items=items, latest_accuracy=latest_accuracy)

    # 특정 사용자의 정확도 기록 이력을 최신순으로 조회합니다.
    # 출처 유형과 세부 출처로 필터링할 수 있습니다.
    # 매개변수: db - 데이터베이스 세션 / user_id - 사용자 ID / source_type - 출처 유형 필터
    #           source_key - 세부 출처 필터 / limit - 최대 반환 건수
    # 반환값: DailyAccuracyHistoryItem 객체 리스트
    @staticmethod
    def list_accuracy_history(
        db: Session,
        *,
        user_id: Optional[int],
        source_type: Optional[str],
        source_key: Optional[str],
        limit: int,
    ) -> list[DailyAccuracyHistoryItem]:
        query = db.query(DailyAccuracyHistory)
        if user_id is None:
            query = query.filter(DailyAccuracyHistory.user_id.is_(None))
        else:
            query = query.filter(DailyAccuracyHistory.user_id == user_id)
        if source_type:
            query = query.filter(DailyAccuracyHistory.source_type == source_type)
        if source_key:
            query = query.filter(DailyAccuracyHistory.source_key == source_key)

        rows = query.order_by(DailyAccuracyHistory.recorded_at.desc()).limit(limit).all()
        items: list[DailyAccuracyHistoryItem] = []
        for row in rows:
            items.append(
                DailyAccuracyHistoryItem(
                    measured_on=row.measured_on,
                    accuracy_pct=int(round(float(row.accuracy_pct))),
                    source_type=row.source_type,
                    source_key=row.source_key,
                    recorded_at=row.recorded_at,
                )
            )
        return items

    # 사용자의 운동 세션 목록을 요약과 함께 조회한다. (운동기록 달력/대시보드용)
    # from_date/to_date로 기간, exercise_code로 운동 종류를 필터링할 수 있다.
    @staticmethod
    def list_sessions(
        db: Session,
        *,
        user_id: int,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        exercise_code: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        q = (
            db.query(ExerciseSession, RehabExercise, ExerciseSessionSummary)
            .join(RehabExercise, ExerciseSession.exercise_id == RehabExercise.exercise_id)
            .outerjoin(ExerciseSessionSummary, ExerciseSessionSummary.session_id == ExerciseSession.session_id)
            .filter(ExerciseSession.user_id == user_id)
        )
        if from_date:
            q = q.filter(ExerciseSession.started_at >= datetime.combine(from_date, datetime.min.time()))
        if to_date:
            q = q.filter(ExerciseSession.started_at <= datetime.combine(to_date, datetime.max.time()))
        if exercise_code:
            q = q.filter(RehabExercise.exercise_code == exercise_code)

        rows = q.order_by(ExerciseSession.started_at.desc()).limit(limit).all()
        result = []
        for session, exercise, summary in rows:
            result.append({
                "session_id": session.session_id,
                "exercise_code": exercise.exercise_code,
                "exercise_name": exercise.exercise_name,
                "started_at": session.started_at,
                "ended_at": session.ended_at,
                "status": session.status,
                "total_reps": summary.total_reps if summary else 0,
                "overall_accuracy_pct": float(summary.overall_accuracy_pct) if summary else None,
            })
        return result

    # 세션 1건의 상세(요약 + rep별)를 조회한다. 본인 세션만 접근 가능(아니면 None).
    @staticmethod
    def get_session_detail(db: Session, *, user_id: int, session_id: int) -> Optional[dict]:
        session = (
            db.query(ExerciseSession)
            .filter(ExerciseSession.session_id == session_id, ExerciseSession.user_id == user_id)
            .first()
        )
        if session is None:
            return None
        exercise = db.query(RehabExercise).get(session.exercise_id)
        summary = db.query(ExerciseSessionSummary).get(session_id)
        reps = (
            db.query(ExerciseRep)
            .filter(ExerciseRep.session_id == session_id)
            .order_by(ExerciseRep.rep_no)
            .all()
        )
        rom = {}
        if summary and summary.rom_json:
            try:
                rom = json.loads(summary.rom_json)
            except (ValueError, TypeError):
                rom = {}

        return {
            "session_id": session.session_id,
            "exercise_code": exercise.exercise_code if exercise else None,
            "exercise_name": exercise.exercise_name if exercise else None,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "status": session.status,
            "total_reps": summary.total_reps if summary else 0,
            "overall_accuracy_pct": float(summary.overall_accuracy_pct) if summary else None,
            "rep_accuracy_avg_pct": float(summary.rep_accuracy_avg_pct) if summary else None,
            "rom": rom,
            "reps": [
                {
                    "rep_no": r.rep_no,
                    "label": r.label,
                    "rep_accuracy_pct": float(r.rep_accuracy_pct),
                    "min_accuracy_pct": float(r.min_accuracy_pct),
                    "max_angle_deg": float(r.max_angle_deg),
                    "started_at": r.rep_started_at,
                    "ended_at": r.rep_ended_at,
                }
                for r in reps
            ],
        }

    # 사용자의 현재(is_current) ROM 측정값을 rom_key: angle 딕셔너리로 반환한다. (검사결과용)
    @staticmethod
    def get_rom_latest(db: Session, *, user_id: int) -> dict:
        rows = (
            db.query(UserRomMeasurement)
            .filter(UserRomMeasurement.user_id == user_id, UserRomMeasurement.is_current.is_(True))
            .all()
        )
        rom = {r.rom_key: float(r.angle_deg) for r in rows}
        measured_at = max((r.measured_at for r in rows), default=None)
        return {"rom": rom, "measured_at": measured_at}

    # 특정 rom_key의 측정 이력을 시간순으로 반환한다. (ROM 추이용)
    @staticmethod
    def get_rom_history(db: Session, *, user_id: int, rom_key: str, limit: int = 100) -> list[dict]:
        rows = (
            db.query(UserRomMeasurement)
            .filter(UserRomMeasurement.user_id == user_id, UserRomMeasurement.rom_key == rom_key)
            .order_by(UserRomMeasurement.measured_at.asc())
            .limit(limit)
            .all()
        )
        return [
            {"angle_deg": float(r.angle_deg), "measured_at": r.measured_at, "is_current": bool(r.is_current)}
            for r in rows
        ]

    # 사용자의 ROM 측정 기록이 있는 날짜 목록을 YYYY-MM-DD 문자열로 반환한다. (기록 달력용)
    @staticmethod
    def get_rom_dates(db: Session, *, user_id: int) -> list[str]:
        from sqlalchemy import func
        rows = (
            db.query(func.date(UserRomMeasurement.measured_at))
            .filter(UserRomMeasurement.user_id == user_id)
            .distinct()
            .order_by(func.date(UserRomMeasurement.measured_at).desc())
            .all()
        )
        return [str(row[0]) for row in rows]

    # 특정 날짜의 rom_key별 최신 측정값을 반환한다. (기록 달력 상세용)
    @staticmethod
    def get_rom_snapshot(db: Session, *, user_id: int, date_str: str) -> dict:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
        start = datetime(target.year, target.month, target.day)
        end = start + timedelta(days=1)
        rows = (
            db.query(UserRomMeasurement)
            .filter(
                UserRomMeasurement.user_id == user_id,
                UserRomMeasurement.measured_at >= start,
                UserRomMeasurement.measured_at < end,
            )
            .order_by(UserRomMeasurement.measured_at.desc())
            .all()
        )
        seen: set[str] = set()
        rom: dict[str, float] = {}
        for r in rows:
            if r.rom_key not in seen:
                seen.add(r.rom_key)
                rom[r.rom_key] = float(r.angle_deg)
        return {"date": date_str, "rom": rom}
