from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    TIMESTAMP,
    UniqueConstraint,
    create_engine,
    text,
    inspect,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from app.core.config import settings


# 설정값은 core/config.py에서 일괄 로드합니다.
DATABASE_URL = settings.database_url

# SQLite는 스레드 옵션이 필요하고, MySQL은 일반 풀 옵션만 사용
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}, pool_pre_ping=True
    )
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    """회원 계정 정보."""

    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    login_id = Column(String(50), nullable=False, unique=True, index=True)
    user_name = Column(String(100), nullable=False)
    phone_number = Column(String(20), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(TIMESTAMP, nullable=True)
    deleted_at = Column(TIMESTAMP, nullable=True)

    sessions = relationship("ExerciseSession", back_populates="user")
    max_rom_records = relationship("UserMaxRom", back_populates="user")


class RehabExercise(Base):
    """재활 운동 마스터 데이터."""

    __tablename__ = "rehab_exercises"

    exercise_id = Column(Integer, primary_key=True, autoincrement=True)
    exercise_code = Column(String(30), nullable=False, unique=True, index=True)
    exercise_name = Column(String(100), nullable=False)
    target_part = Column(
        Enum("left_arm", "right_arm", "left_leg", "right_leg", name="target_part_enum"),
        nullable=False,
        index=True,
    )
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=text("1"))
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    sessions = relationship("ExerciseSession", back_populates="exercise")
    max_rom_records = relationship("UserMaxRom", back_populates="exercise")


class ExerciseSession(Base):
    """사용자 운동 1회(시작~종료) 세션."""

    __tablename__ = "exercise_sessions"

    session_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False, index=True)
    exercise_id = Column(Integer, ForeignKey("rehab_exercises.exercise_id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    status = Column(
        Enum("in_progress", "completed", "aborted", name="session_status_enum"),
        nullable=False,
    )
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    user = relationship("User", back_populates="sessions")
    exercise = relationship("RehabExercise", back_populates="sessions")
    rules = relationship("ExerciseSessionRule", back_populates="session", uselist=False)
    summary = relationship("ExerciseSessionSummary", back_populates="session", uselist=False)
    reps = relationship("ExerciseRep", back_populates="session")
    realtime_logs = relationship("RealtimeMotionLog", back_populates="session")
    csv_export = relationship("SessionCsvExport", back_populates="session", uselist=False)


class ExerciseSessionRule(Base):
    """세션별 시작/종료 판정 기준(1:1)."""

    __tablename__ = "exercise_session_rules"

    session_id = Column(
        Integer,
        ForeignKey("exercise_sessions.session_id", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True,
    )
    baseline_pose_json = Column(JSON, nullable=False)
    start_similarity_threshold = Column(Numeric(10, 6), nullable=False)
    end_similarity_threshold = Column(Numeric(10, 6), nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    session = relationship("ExerciseSession", back_populates="rules")


class ExerciseSessionSummary(Base):
    """세션별 요약 결과(1:1)."""

    __tablename__ = "exercise_session_summary"

    session_id = Column(
        Integer,
        ForeignKey("exercise_sessions.session_id", ondelete="CASCADE", onupdate="CASCADE"),
        primary_key=True,
    )
    total_reps = Column(Integer, nullable=False, server_default=text("0"))
    overall_accuracy_pct = Column(Numeric(5, 2), nullable=False)
    rep_accuracy_avg_pct = Column(Numeric(5, 2), nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    session = relationship("ExerciseSession", back_populates="summary")


class ExerciseRep(Base):
    """세션 내 반복(1회) 단위 기록."""

    __tablename__ = "exercise_reps"
    __table_args__ = (UniqueConstraint("session_id", "rep_no", name="uq_reps_session_rep_no"),)

    rep_id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer,
        ForeignKey("exercise_sessions.session_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    rep_no = Column(Integer, nullable=False)
    rep_started_at = Column(DateTime, nullable=False)
    rep_ended_at = Column(DateTime, nullable=True)
    max_angle_deg = Column(Numeric(10, 4), nullable=False)
    start_accuracy_pct = Column(Numeric(5, 2), nullable=False, server_default=text("100.00"))
    min_accuracy_pct = Column(Numeric(5, 2), nullable=False, server_default=text("100.00"))
    rep_accuracy_pct = Column(Numeric(5, 2), nullable=False)
    start_pose_similarity = Column(Numeric(10, 6), nullable=True)
    end_pose_similarity = Column(Numeric(10, 6), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    session = relationship("ExerciseSession", back_populates="reps")
    logs = relationship("RealtimeMotionLog", back_populates="rep")


class RealtimeMotionLog(Base):
    """실시간 모션 로그 및 CSV 원본 데이터."""

    __tablename__ = "realtime_motion_logs"

    log_id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer,
        ForeignKey("exercise_sessions.session_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    rep_id = Column(
        Integer,
        ForeignKey("exercise_reps.rep_id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
        index=True,
    )
    ts = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), index=True)
    left_arm_angle = Column(Numeric(10, 4), nullable=True)
    right_arm_angle = Column(Numeric(10, 4), nullable=True)
    left_leg_angle = Column(Numeric(10, 4), nullable=True)
    right_leg_angle = Column(Numeric(10, 4), nullable=True)
    pose_similarity = Column(Numeric(10, 6), nullable=True)
    accuracy_pct = Column(Numeric(5, 2), nullable=False)
    penalty_delta_pct = Column(Numeric(5, 2), nullable=False, server_default=text("0.00"))
    recovery_delta_pct = Column(Numeric(5, 2), nullable=False, server_default=text("0.00"))
    deviation_flags_json = Column(JSON, nullable=True)
    keypoints_json = Column(JSON, nullable=True)

    session = relationship("ExerciseSession", back_populates="realtime_logs")
    rep = relationship("ExerciseRep", back_populates="logs")


class SessionCsvExport(Base):
    """세션별 CSV 파일 메타 정보."""

    __tablename__ = "session_csv_exports"

    csv_export_id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer,
        ForeignKey("exercise_sessions.session_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    file_path = Column(String(255), nullable=False)
    row_count = Column(Integer, nullable=False, server_default=text("0"))
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    session = relationship("ExerciseSession", back_populates="csv_export")


class UserMaxRom(Base):
    """사용자별 운동 최대가동범위 기준값."""

    __tablename__ = "user_max_rom"

    user_max_rom_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False, index=True)
    exercise_id = Column(Integer, ForeignKey("rehab_exercises.exercise_id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False, index=True)
    max_rom_deg = Column(Numeric(10, 4), nullable=False)
    measured_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    is_current = Column(Boolean, nullable=False, server_default=text("1"))

    user = relationship("User", back_populates="max_rom_records")
    exercise = relationship("RehabExercise", back_populates="max_rom_records")


class DailyAccuracyHistory(Base):
    """메인 주간 점수 표기용 일별 최종 정확도."""

    __tablename__ = "daily_accuracy_history"

    # [조현석] 기존 localStorage 기반 주간 점수를 여러 장비/브라우저에서도 동일하게 보이게 하려면 일별 최종 점수를 DB에 별도 보관해야 합니다.

    history_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE", onupdate="CASCADE"), nullable=True, index=True)
    measured_on = Column(Date, nullable=False, index=True)
    accuracy_pct = Column(Numeric(5, 2), nullable=False)
    source_type = Column(String(30), nullable=False, server_default=text("'exercise'"))
    source_key = Column(String(50), nullable=True)
    recorded_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))


def get_db():
    """FastAPI 의존성 주입용 DB 세션 생성기."""
    # [핵심] 요청 단위로 세션을 열고/닫아 커넥션 누수를 방지합니다.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """현재 선언된 ORM 모델 기준으로 테이블 생성."""
    Base.metadata.create_all(bind=engine)
    _ensure_users_login_id_column()


def _ensure_users_login_id_column():
    """
    기존 운영 DB에 login_id 컬럼이 없을 수 있어 시작 시 보정합니다.
    """
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "login_id" in columns:
        return

    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            conn.execute(text("ALTER TABLE users ADD COLUMN login_id VARCHAR(50)"))
            conn.execute(text("UPDATE users SET login_id = phone_number WHERE login_id IS NULL"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_login_id ON users (login_id)"))
        else:
            conn.execute(text("ALTER TABLE users ADD COLUMN login_id VARCHAR(50) NULL"))
            conn.execute(text("UPDATE users SET login_id = phone_number WHERE login_id IS NULL"))
            conn.execute(text("ALTER TABLE users MODIFY COLUMN login_id VARCHAR(50) NOT NULL"))
            conn.execute(text("CREATE UNIQUE INDEX ix_users_login_id ON users (login_id)"))
    
