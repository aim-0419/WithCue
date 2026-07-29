# rehab_exercises 마스터 데이터를 시드하는 스크립트.
# target_part enum을 neck/core까지 확장(ALTER)한 뒤, WS 운동 문자열을 exercise_code로 하여 6종을 멱등 삽입한다.
# exercise_code == WS 경로의 exercise 문자열 이므로, 세션 저장 시 문자열로 바로 exercise_id를 조회할 수 있다.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.core.database import SessionLocal, engine, RehabExercise

# (exercise_code, 운동명, target_part) — 프론트 EXERCISE_OPTIONS 라벨과 일치
EXERCISES = [
    ("bird_dog",                    "버드독",              "core"),
    ("shoulder_front_raise_left",   "어깨 전방 거상(왼쪽)",  "left_arm"),
    ("shoulder_front_raise_right",  "어깨 전방 거상(오른쪽)", "right_arm"),
    ("straight_leg_raise_left",     "무릎 들어올리기(왼쪽)",  "left_leg"),
    ("straight_leg_raise_right",    "무릎 들어올리기(오른쪽)", "right_leg"),
    ("neck_rotation",               "목 좌우 돌리기",        "neck"),
]

# MySQL enum 컬럼을 neck/core 포함해 재정의 (빈 테이블이라 안전)
ALTER_SQL = (
    "ALTER TABLE rehab_exercises MODIFY COLUMN target_part "
    "ENUM('left_arm','right_arm','left_leg','right_leg','neck','core') NOT NULL"
)


def main():
    with engine.begin() as conn:
        conn.execute(text(ALTER_SQL))
        print("[seed] target_part enum 확장 완료 (neck/core 추가)")

    db = SessionLocal()
    try:
        inserted, skipped = 0, 0
        for code, name, part in EXERCISES:
            exists = db.query(RehabExercise).filter_by(exercise_code=code).first()
            if exists:
                skipped += 1
                continue
            db.add(RehabExercise(exercise_code=code, exercise_name=name, target_part=part))
            inserted += 1
        db.commit()
        print(f"[seed] 삽입 {inserted}건 / 기존 유지 {skipped}건")
        for r in db.query(RehabExercise).order_by(RehabExercise.exercise_id).all():
            print(f"  #{r.exercise_id}  {r.exercise_code:28s} {r.target_part:10s} {r.exercise_name}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
