# 데이터베이스 연결 설정과 ORM 모델(테이블 구조)을 정의하는 모듈.
# 사용자, 운동 세션, 반복(rep) 기록, 정확도 이력 등 서비스 전반의 데이터 구조를 담당한다.
# SQLAlchemy를 사용하며, 서버 시작 시 init_db()를 호출해 테이블을 자동 생성한다.

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    TIMESTAMP,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from app.core.config import settings


# 설정값은 core/config.py에서 일괄 로드합니다.
DATABASE_URL = settings.database_url

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# 회원 계정 정보를 저장하는 테이블 모델.
# 로그인 아이디, 이름, 전화번호, 비밀번호 해시 등 사용자 식별에 필요한 정보를 보관한다.
class User(Base):
    """회원 계정 정보."""

    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    login_id = Column(String(50), nullable=False, unique=True, index=True)
    user_name = Column(String(100), nullable=False)
    phone_number = Column(String(20), nullable=False, unique=True, index=True)
    # [성별 추가] 회원가입 시 남(M)/여(F) 중 하나를 저장. 기본값은 M.
    gender = Column(
        Enum("M", "F", name="gender_enum"),
        nullable=False,
        server_default=text("'M'"),
    )
    password_hash = Column(String(255), nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(TIMESTAMP, nullable=True)
    deleted_at = Column(TIMESTAMP, nullable=True)

    sessions = relationship("ExerciseSession", back_populates="user")
    max_rom_records = relationship("UserMaxRom", back_populates="user")


# 제공되는 재활 운동의 종류와 기본 정보를 저장하는 마스터 테이블 모델.
# 운동 코드(exercise_code)를 기준으로 세션 기록과 연결된다.
class RehabExercise(Base):
    """재활 운동 마스터 데이터."""

    __tablename__ = "rehab_exercises"

    exercise_id = Column(Integer, primary_key=True, autoincrement=True)
    exercise_code = Column(String(30), nullable=False, unique=True, index=True)
    exercise_name = Column(String(100), nullable=False)
    target_part = Column(
        Enum("left_arm", "right_arm", "left_leg", "right_leg", "neck", "core", name="target_part_enum"),
        nullable=False,
        index=True,
    )
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default=text("1"))
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    sessions = relationship("ExerciseSession", back_populates="exercise")
    max_rom_records = relationship("UserMaxRom", back_populates="exercise")


# 사용자가 운동을 시작해서 끝낼 때까지 1회 세션 정보를 저장하는 테이블 모델.
# 진행 중(in_progress), 완료(completed), 중단(aborted) 상태를 추적한다.
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


# 세션별 동작 판정 기준값을 저장하는 테이블 모델(세션:규칙 = 1:1).
# 기준 자세와 시작/종료 유사도 임계값을 보관해 코칭 판정에 활용한다.
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


# 세션이 끝난 후 전체 반복 횟수와 평균 정확도 등을 요약해 저장하는 테이블 모델(세션:요약 = 1:1).
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
    rom_json = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    session = relationship("ExerciseSession", back_populates="summary")


# 운동 세션 내 개별 반복(rep) 1회의 기록을 저장하는 테이블 모델.
# 반복 번호, 시작/종료 시각, 최대 각도, 정확도 등을 보관한다.
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
    label = Column(String(50), nullable=True)  # rep 판정 라벨(정상/오류 유형, 예: "무릎 굽힘")
    start_pose_similarity = Column(Numeric(10, 6), nullable=True)
    end_pose_similarity = Column(Numeric(10, 6), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    session = relationship("ExerciseSession", back_populates="reps")
    logs = relationship("RealtimeMotionLog", back_populates="rep")


# 운동 중 매 프레임마다 감지된 관절 각도, 정확도, 키포인트 좌표 등을 기록하는 테이블 모델.
# 나중에 CSV로 내보내거나 상세 분석에 활용할 수 있는 원시 데이터다.
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


# 세션별로 생성된 CSV 파일의 경로와 행 수 등 메타 정보를 저장하는 테이블 모델.
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


# 사용자별·운동별 최대 관절 가동 범위(ROM) 기준값을 저장하는 테이블 모델.
# 코칭 목표각 설정 등에 활용된다.
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


# 메인 화면의 주간 점수 차트를 위해 날짜별 최종 정확도를 별도 저장하는 테이블 모델.
# 여러 기기나 브라우저에서 동일한 주간 점수를 볼 수 있도록 DB에 보관한다.
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


# 검사(ROM) 측정값을 rom_key 단위로 저장하는 테이블 모델.
# rom dict가 다중 키(shoulder_left_flexion_max 등)라 UserMaxRom(운동당 스칼라)로는 담기 어려워 별도 테이블로 무손실 저장한다.
# 새 측정 시 같은 (user, rom_key)의 이전 행 is_current=0으로 내리고 새 행을 is_current=1로 넣어 최신값+이력을 함께 유지한다.
class UserRomMeasurement(Base):
    """검사(ROM) 측정값 — rom_key별 최신값 + 이력."""

    __tablename__ = "user_rom_measurements"
    __table_args__ = (
        Index("ix_rom_user_current", "user_id", "is_current"),
    )

    rom_measurement_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False, index=True)
    rom_key = Column(String(50), nullable=False, index=True)
    angle_deg = Column(Numeric(10, 4), nullable=False)
    measured_at = Column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    is_current = Column(Boolean, nullable=False, server_default=text("1"))


# FastAPI 의존성 주입으로 HTTP 요청마다 DB 세션을 열고 응답 후 반드시 닫아주는 생성기 함수.
# 반환값: SQLAlchemy 세션 객체 (요청 처리 중에만 유효).
def get_db():
    """FastAPI 의존성 주입용 DB 세션 생성기."""
    # [핵심] 요청 단위로 세션을 열고/닫아 커넥션 누수를 방지합니다.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ORM 모델에 정의된 모든 테이블을 데이터베이스에 생성하는 함수.
# 이미 테이블이 존재하면 건너뛰므로 서버 시작 시 안전하게 반복 호출할 수 있다.
def init_db():
    """현재 선언된 ORM 모델 기준으로 테이블 생성."""
    Base.metadata.create_all(bind=engine)
