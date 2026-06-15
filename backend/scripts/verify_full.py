# 리팩토링 종합 검증 스크립트
# 범위: geometry / feature / feedback / DTW engine / DTW processor / NeckROM / catalog / server import
import sys, os, json, math, time, tempfile
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"
results = []

def ok(label):
    results.append((PASS, label))
    print(f"  {PASS}  {label}")

def fail(label, detail=""):
    results.append((FAIL, label))
    print(f"  {FAIL}  {label}  {detail}")

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ─────────────────────────────────────────────────────────
# 1. 모듈 import
# ─────────────────────────────────────────────────────────
section("1. 모듈 import")

modules = [
    ("geometry utils",        "app.exercises.shared.dtw_feature_extractor"),
    ("shared base",           "app.exercises.shared.base"),
    ("shared common",         "app.exercises.shared.common"),
    ("shared posture",        "app.exercises.shared.posture"),
    ("bird_dog features",     "app.exercises.bird_dog.features"),
    ("bird_dog feedback",     "app.exercises.bird_dog.feedback"),
    ("bird_dog processor",    "app.exercises.bird_dog.processor"),
    ("shoulder features",     "app.exercises.shoulder_front_raise.features"),
    ("shoulder feedback",     "app.exercises.shoulder_front_raise.feedback"),
    ("shoulder processor",    "app.exercises.shoulder_front_raise.processor"),
    ("knee_raise features",   "app.exercises.knee_raise.features"),
    ("knee_raise feedback",   "app.exercises.knee_raise.feedback"),
    ("knee_raise processor",  "app.exercises.knee_raise.processor"),
    ("neck_rotation features","app.exercises.neck_rotation.features"),
    ("neck_rotation feedback","app.exercises.neck_rotation.feedback"),
    ("neck_rotation processor","app.exercises.neck_rotation.processor"),
    ("neck_rotation measurement","app.exercises.neck_rotation.measurement"),
    ("shared measurement",    "app.exercises.shared.measurement"),
    ("feedback router",       "app.services.feedback.realtime_feedback_router"),
    ("session feedback summary","app.services.feedback.session_feedback_summary"),
    ("score service",         "app.services.score_service"),
    ("exercise catalog",      "app.services.exercise_catalog"),
    ("mock ws service",       "app.services.mock_ws_service"),
]

for label, mod in modules:
    try:
        __import__(mod)
        ok(label)
    except Exception as e:
        fail(label, str(e))

# ─────────────────────────────────────────────────────────
# 2. geometry 유틸리티 수치 검증
# ─────────────────────────────────────────────────────────
section("2. Geometry utils 수치 검증")

from app.exercises.shared.dtw_feature_extractor import (
    calc_angle, midpoint, line_angle_from_vertical,
    line_angle_from_horizontal, horizontal_error_deg,
)

try:
    # 정삼각형 (직각) — 꼭 90도 나와야 함
    a = calc_angle((0,0), (1,0), (1,1))
    assert abs(a - 90.0) < 1e-6, f"expected 90, got {a}"
    ok("calc_angle 직각")
except Exception as e:
    fail("calc_angle 직각", str(e))

try:
    # 일직선 — 180도
    a = calc_angle((0,0), (1,0), (2,0))
    assert abs(a - 180.0) < 1e-6, f"expected 180, got {a}"
    ok("calc_angle 일직선 180")
except Exception as e:
    fail("calc_angle 일직선", str(e))

try:
    m = midpoint((0,0), (4,4))
    assert m == (2.0, 2.0), f"got {m}"
    ok("midpoint")
except Exception as e:
    fail("midpoint", str(e))

try:
    # 수직선 → 0도
    a = line_angle_from_vertical((0,0), (0,10))
    assert abs(a - 0.0) < 1e-6, f"got {a}"
    ok("line_angle_from_vertical 수직=0")
except Exception as e:
    fail("line_angle_from_vertical", str(e))

try:
    # 수평선 → 90도
    a = line_angle_from_vertical((0,5), (10,5))
    assert abs(a - 90.0) < 1e-6, f"got {a}"
    ok("line_angle_from_vertical 수평=90")
except Exception as e:
    fail("line_angle_from_vertical 수평", str(e))

try:
    # 수평 두 점 → 수평 오차 0
    a = horizontal_error_deg((0,0), (10,0))
    assert abs(a - 0.0) < 1e-6, f"got {a}"
    ok("horizontal_error_deg 수평=0")
except Exception as e:
    fail("horizontal_error_deg", str(e))

# ─────────────────────────────────────────────────────────
# 3. feature 함수: MP == YOLO (동일 좌표, 다른 인덱스)
# ─────────────────────────────────────────────────────────
section("3. feature 함수 MP vs YOLO 일치 검증")

from app.exercises.bird_dog.features import get_bird_dog_features_mp, get_bird_dog_features_yolo
from app.exercises.shoulder_front_raise.features import (
    get_shoulder_front_raise_left_features_mp,
    get_shoulder_front_raise_left_features_yolo,
)
from app.exercises.neck_rotation.features import (
    get_neck_rotation_features_mp,
    get_neck_rotation_features_yolo,
)
from app.exercises.knee_raise.features import get_knee_raise_right_features_yolo

# 공통 좌표
nose=(320,80); left_ear=(295,95); right_ear=(345,95)
left_sh=(260,210); right_sh=(380,210)
left_el=(240,320); right_el=(400,320)
left_wr=(230,430); right_wr=(410,430)
left_hip=(275,440); right_hip=(365,440)
left_knee=(270,570); right_knee=(370,570)
left_ank=(265,700); right_ank=(375,700)

mp_pts = {
    0:nose, 7:left_ear, 8:right_ear,
    11:left_sh, 12:right_sh, 13:left_el, 14:right_el,
    15:left_wr, 16:right_wr, 23:left_hip, 24:right_hip,
    25:left_knee, 26:right_knee, 27:left_ank, 28:right_ank,
}
yolo_pts = {
    0:nose, 3:left_ear, 4:right_ear,
    5:left_sh, 6:right_sh, 7:left_el, 8:right_el,
    9:left_wr, 10:right_wr, 11:left_hip, 12:right_hip,
    13:left_knee, 14:right_knee, 15:left_ank, 16:right_ank,
}

def feats_equal(a, b, skip=()):
    if a is None or b is None:
        return False
    return all(abs(va-vb)<1e-9 for i,(va,vb) in enumerate(zip(a,b)) if i not in skip)

try:
    a = get_bird_dog_features_mp(mp_pts)
    b = get_bird_dog_features_yolo(yolo_pts)
    assert a is not None and b is not None
    assert len(a) == 14 and len(b) == 14
    assert feats_equal(a, b), f"\nMP  ={a}\nYOLO={b}"
    ok("bird_dog MP == YOLO (14-dim)")
except Exception as e:
    fail("bird_dog feature 일치", str(e))

try:
    a = get_neck_rotation_features_mp(mp_pts)
    b = get_neck_rotation_features_yolo(yolo_pts)
    assert a is not None and b is not None
    assert len(a) == 4 and len(b) == 4
    assert feats_equal(a, b), f"\nMP  ={a}\nYOLO={b}"
    ok("neck_rotation MP == YOLO (4-dim)")
except Exception as e:
    fail("neck_rotation feature 일치", str(e))

try:
    a = get_shoulder_front_raise_left_features_mp(mp_pts)
    b = get_shoulder_front_raise_left_features_yolo(yolo_pts)
    assert a is not None and b is not None
    assert len(a) == 6 and len(b) == 6
    # [0]trunk, [1]shoulder_rise: 계산 방식 다름 → 스킵
    # [0]trunk / [1]shoulder_rise / [2]arm_raise: Jetson 설계 변경 (스킵)
    # [3][4][5] 는 동일해야 함
    assert feats_equal(a, b, skip=(0,1,2)), f"[3~5]\nMP  ={a[3:]}\nYOLO={b[3:]}"
    ok("shoulder_front_raise MP == YOLO (dim 3~5)")
    print(f"         [SKIP] [0]trunk    MP={a[0]:.3f} YOLO={b[0]:.3f} (픽셀거리 vs 각도)")
    print(f"         [SKIP] [1]sh_rise  MP={a[1]:.3f} YOLO={b[1]:.3f}")
    print(f"         [SKIP] [2]arm_raise MP={a[2]:.3f} YOLO={b[2]:.3f} (hip_mid vs left_hip)")
except Exception as e:
    fail("shoulder_front_raise feature", str(e))

try:
    r = get_knee_raise_right_features_yolo(yolo_pts)
    assert r is not None and len(r) == 3
    ok(f"knee_raise YOLO (3-dim) = {r}")
except Exception as e:
    fail("knee_raise YOLO feature", str(e))

# ─────────────────────────────────────────────────────────
# 4. feedback extractor 함수
# ─────────────────────────────────────────────────────────
section("4. feedback extractor 함수")

from app.exercises.bird_dog.feedback import extract_birddog_issues
from app.exercises.shoulder_front_raise.feedback import extract_shoulder_front_raise_issues
from app.exercises.knee_raise.feedback import extract_knee_raise_right_issues
from app.exercises.neck_rotation.feedback import extract_neck_rotation_issues

dummy_compare = {
    "motion_similarity": 60.0,
    "posture_similarity": 55.0,
    "feature_errors": {
        "trunk": 0.3, "pelvic": 0.05,
        "right_arm": 0.4, "left_leg": 0.35,
        "left_arm": 0.2, "right_leg": 0.15,
        "right_arm_h_err": 0.25, "left_leg_h_err": 0.2,
        "left_arm_h_err": 0.1, "right_leg_h_err": 0.1,
        "right_elbow_angle": 0.1, "left_elbow_angle": 0.1,
        "left_knee_angle": 0.1, "right_knee_angle": 0.1,
    },
    "pair_a_error": 0.38,
    "pair_b_error": 0.18,
    "movement_direction": "pair_a",
    "phase": "raising",
    "main_error_feature": "right_arm",
}

shoulder_compare = {
    "motion_similarity": 55.0,
    "posture_similarity": 60.0,
    "feature_errors": {
        "trunk": 0.3, "shoulder_rise": 0.4,
        "arm_raise": 0.5, "elbow_angle": 0.2,
        "arm_horizontal_error": 0.3, "support_dist": 0.1,
    },
    "phase": "raising",
    "main_error_feature": "arm_raise",
}

knee_compare = {
    "motion_similarity": 65.0,
    "posture_similarity": 70.0,
    "feature_errors": {
        "hip_flexion": 0.3, "knee_angle": 0.2, "ankle_height": 0.4
    },
    "phase": "raising",
    "main_error_feature": "ankle_height",
}

neck_compare = {
    "motion_similarity": 70.0,
    "posture_similarity": 65.0,
    "feature_errors": {
        "trunk_rotation": 0.35, "neck_turn_angle": 0.5,
        "head_tilt": 0.2, "shoulder_line_angle": 0.1,
    },
    "phase": "turning_right",
    "main_error_feature": "neck_turn_angle",
}

for label, fn, arg in [
    ("bird_dog feedback",    extract_birddog_issues,             dummy_compare),
    ("shoulder feedback",    extract_shoulder_front_raise_issues, shoulder_compare),
    ("knee_raise feedback",  extract_knee_raise_right_issues,    knee_compare),
    ("neck_rotation feedback",extract_neck_rotation_issues,      neck_compare),
]:
    try:
        issues = fn(arg)
        assert isinstance(issues, list), f"expected list, got {type(issues)}"
        ok(f"{label}: {len(issues)} issue(s) 반환")
    except Exception as e:
        fail(label, str(e))

# ─────────────────────────────────────────────────────────
# 5. RealTimeFeedbackRouter + SessionFeedbackSummary
# ─────────────────────────────────────────────────────────
section("5. RealTimeFeedbackRouter + SessionFeedbackSummary")

from app.services.feedback.realtime_feedback_router import RealTimeFeedbackRouter
from app.services.feedback.session_feedback_summary import SessionFeedbackSummary, format_top3_text

for ex_type, compare_result in [
    ("bird_dog",           dummy_compare),
    ("shoulder_front_raise", shoulder_compare),
    ("knee_raise_right",   knee_compare),
    ("neck_rotation",      neck_compare),
]:
    try:
        router = RealTimeFeedbackRouter()
        pkt = router.process(ex_type, compare_result, time.time())
        assert "feedback" in pkt and "all_issues" in pkt
        ok(f"RealTimeFeedbackRouter [{ex_type}]")
    except Exception as e:
        fail(f"RealTimeFeedbackRouter [{ex_type}]", str(e))

try:
    summary = SessionFeedbackSummary()
    issues = extract_birddog_issues(dummy_compare)
    summary.observe("bird_dog", issues, 0.1)
    result = summary.finalize(top_k=3)
    # finalize()는 dict{"top_issues":[], "all_issues":[]} 반환
    assert isinstance(result, dict) and "top_issues" in result
    text = format_top3_text(result)
    assert isinstance(text, list)
    ok(f"SessionFeedbackSummary.finalize() — {len(result['top_issues'])} top issue(s)")
except Exception as e:
    fail("SessionFeedbackSummary", str(e))

# ─────────────────────────────────────────────────────────
# 6. DTW 엔진 (임시 reference JSON 생성 후 compute)
# ─────────────────────────────────────────────────────────
section("6. DTW 엔진 compute/live_similarity")

from app.exercises.bird_dog.processor import BirdDogDTW
from app.exercises.shoulder_front_raise.processor import ShoulderFrontRaiseLeftDTW
from app.exercises.knee_raise.processor import KneeRaiseRightDTW
from app.exercises.neck_rotation.processor import NeckRotationDTW

def make_ref_json(exercise, n_feats, n_frames=40):
    t = np.linspace(0, 2*np.pi, n_frames)
    seq = []
    for i in range(n_frames):
        base = [30.0] * n_feats
        # motion feature에 sinusoidal 추가 (BirdDog: idx 2~5, 나머지: idx 2)
        if n_feats >= 6:
            base[2] = 30.0 + 50.0 * abs(math.sin(t[i]))
            base[3] = 160.0 + 10.0 * math.cos(t[i])
        elif n_feats >= 3:
            base[2] = 100.0 + 80.0 * abs(math.sin(t[i]))
        if n_feats == 14:
            base[3] = 160.0 + 10.0 * math.cos(t[i])
            base[4] = 30.0 + 50.0 * abs(math.sin(t[i]))
            base[5] = 160.0 + 10.0 * math.cos(t[i])
        if n_feats == 4:   # neck_rotation
            base[1] = 50.0 * math.sin(t[i])
        seq.append([round(v, 3) for v in base])
    return {"exercise": exercise, "fps": 30, "sequence": seq}

def test_dtw_engine(label, DTWClass, n_feats, exercise_name):
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(make_ref_json(exercise_name, n_feats), f)
            tmp_path = f.name

        engine = DTWClass(tmp_path)

        # compare() 테스트
        user_seq = np.array(make_ref_json(exercise_name, n_feats, 35)["sequence"])
        result = engine.compare(user_seq)
        assert "score" in result and isinstance(result["score"], (int, float))

        # get_live_similarity() 테스트
        live_result = engine.get_live_similarity(user_seq[:20])
        assert "live_similarity" in live_result

        os.unlink(tmp_path)
        ok(f"{label} compare()={result['score']:.1f}  live_sim={live_result.get('live_similarity')}")
    except Exception as e:
        fail(label, str(e))

test_dtw_engine("BirdDogDTW",              BirdDogDTW,              14, "BIRD_DOG")
test_dtw_engine("ShoulderFrontRaiseLeftDTW", ShoulderFrontRaiseLeftDTW, 6, "SHOULDER_FRONT_RAISE_LEFT")
test_dtw_engine("KneeRaiseRightDTW",        KneeRaiseRightDTW,       3, "KNEE_RAISE_LEFT")
test_dtw_engine("NeckRotationDTW",          NeckRotationDTW,         4, "NECK_ROTATION")

# ─────────────────────────────────────────────────────────
# 7. DTW Processor — extract_mp_features + process() 기본 흐름
# ─────────────────────────────────────────────────────────
section("7. DTW Processor extract_mp_features + process()")

from app.exercises.bird_dog.processor import BirdDogDTWProcessor
from app.exercises.shoulder_front_raise.processor import ShoulderFrontRaiseLeftDTWProcessor
from app.exercises.knee_raise.processor import KneeRaiseRightDTWProcessor
from app.exercises.neck_rotation.processor import NeckRotationDTWProcessor

def build_engine(DTWClass, n_feats, name):
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(make_ref_json(name, n_feats), f)
        tmp_path = f.name
    # with 블록 밖에서 생성 (Windows 파일 잠금 회피)
    return DTWClass(tmp_path), tmp_path

try:
    # Bird Dog
    engine, tmp = build_engine(BirdDogDTW, 14, "BIRD_DOG")
    proc = BirdDogDTWProcessor(engine, target_reps=1)

    # extract_mp_features
    feats = proc.extract_mp_features(yolo_pts)
    assert feats is not None and len(feats) == 14
    ok(f"BirdDogDTWProcessor.extract_mp_features -> 14-dim")

    # process() 호출 (대기 상태)
    r = proc.process(keypoints={}, frame=None, mp_features=feats)
    assert r.get("mode") == "BIRD_DOG_DTW"
    ok(f"BirdDogDTWProcessor.process() status={r['status']}")
    os.unlink(tmp)
except Exception as e:
    fail("BirdDogDTWProcessor", str(e))

try:
    # ShoulderFrontRaise
    engine, tmp = build_engine(ShoulderFrontRaiseLeftDTW, 6, "SHOULDER_FRONT_RAISE_LEFT")
    proc = ShoulderFrontRaiseLeftDTWProcessor(engine, target_reps=1)
    feats = proc.extract_mp_features(yolo_pts)
    assert feats is not None and len(feats) == 6
    ok(f"ShoulderFrontRaiseLeftDTWProcessor.extract_mp_features -> 6-dim")
    r = proc.process(keypoints={}, frame=None, mp_features=feats)
    assert r.get("mode") == "SHOULDER_FRONT_RAISE_DTW"
    ok(f"ShoulderFrontRaiseLeftDTWProcessor.process() status={r['status']}")
    os.unlink(tmp)
except Exception as e:
    fail("ShoulderFrontRaiseLeftDTWProcessor", str(e))

try:
    # KneeRaise
    engine, tmp = build_engine(KneeRaiseRightDTW, 3, "KNEE_RAISE_LEFT")
    proc = KneeRaiseRightDTWProcessor(engine, target_reps=1)
    feats = proc.extract_mp_features(yolo_pts)
    assert feats is not None and len(feats) == 3
    ok(f"KneeRaiseRightDTWProcessor.extract_mp_features -> 3-dim")
    r = proc.process(keypoints={}, frame=None, mp_features=feats)
    assert r.get("mode") == "KNEE_RAISE_DTW"
    ok(f"KneeRaiseRightDTWProcessor.process() status={r['status']}")
    os.unlink(tmp)
except Exception as e:
    fail("KneeRaiseRightDTWProcessor", str(e))

try:
    # NeckRotation
    engine, tmp = build_engine(NeckRotationDTW, 4, "NECK_ROTATION")
    proc = NeckRotationDTWProcessor(engine, target_reps=1)
    feats = proc.extract_mp_features(yolo_pts)
    assert feats is not None and len(feats) == 4
    ok(f"NeckRotationDTWProcessor.extract_mp_features -> 4-dim")
    r = proc.process(keypoints={}, frame=None, mp_features=feats)
    assert r.get("mode") == "NECK_ROTATION_DTW"
    ok(f"NeckRotationDTWProcessor.process() status={r['status']}")
    os.unlink(tmp)
except Exception as e:
    fail("NeckRotationDTWProcessor", str(e))

# ─────────────────────────────────────────────────────────
# 8. NeckROMMeasurementProcessor 상태 기계
# ─────────────────────────────────────────────────────────
section("8. NeckROMMeasurementProcessor 상태 기계")

from app.exercises.neck_rotation.measurement import NeckROMMeasurementProcessor

try:
    proc = NeckROMMeasurementProcessor(fps=30)
    assert proc.state == "READY"
    ok("NeckROMMeasurementProcessor 초기화 state=READY")
except Exception as e:
    fail("NeckROMMeasurementProcessor 초기화", str(e))

try:
    # extract_mp_features — YOLO pts로 neck rotation 4-dim
    feats = proc.extract_mp_features(yolo_pts)
    assert feats is not None and len(feats) == 4
    ok(f"NeckROMMeasurementProcessor.extract_mp_features -> 4-dim = {feats}")
except Exception as e:
    fail("NeckROMMeasurementProcessor.extract_mp_features", str(e))

try:
    # process() 기본 호출 (mp_features None → waiting 상태)
    r = proc.process(keypoints={}, frame=None, mp_features=None)
    assert isinstance(r, dict)
    ok(f"NeckROMMeasurementProcessor.process(None) -> {r.get('status','?')}")
except Exception as e:
    fail("NeckROMMeasurementProcessor.process()", str(e))

# ─────────────────────────────────────────────────────────
# 9. exercise catalog
# ─────────────────────────────────────────────────────────
section("9. Exercise catalog")

try:
    from app.services.exercise_catalog import list_exercises_for_client
    items = list_exercises_for_client()
    assert isinstance(items, list) and len(items) > 0
    ok(f"list_exercises_for_client() -> {len(items)} items")
    for item in items:
        print(f"         {item.get('exercise_id', '?')} stage={item.get('stage', '?')}")
except Exception as e:
    fail("exercise_catalog", str(e))

# ─────────────────────────────────────────────────────────
# 10. 서버 app.main import
# ─────────────────────────────────────────────────────────
section("10. 서버 app.main import")

try:
    import app.main
    ok("app.main import 성공")
except Exception as e:
    fail("app.main import", str(e))

# ─────────────────────────────────────────────────────────
# 최종 결과
# ─────────────────────────────────────────────────────────
section("최종 결과")
total = len(results)
passed = sum(1 for s,_ in results if s == PASS)
failed = sum(1 for s,_ in results if s == FAIL)
print(f"  총 {total}개 항목  |  PASS {passed}  |  FAIL {failed}")
if failed > 0:
    print("\n  실패 목록:")
    for s, label in results:
        if s == FAIL:
            print(f"    - {label}")
print()
