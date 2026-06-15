# 리펙토링 검증: 같은 좌표값 → MP 버전과 YOLO 버전이 동일한 결과를 내는지 확인
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.exercises.bird_dog.features import (
    get_bird_dog_features_mp,
    get_bird_dog_features_yolo,
)
from app.exercises.shoulder_front_raise.features import (
    get_shoulder_front_raise_left_features_mp,
    get_shoulder_front_raise_left_features_yolo,
)
from app.exercises.neck_rotation.features import (
    get_neck_rotation_features_mp,
    get_neck_rotation_features_yolo,
)
from app.exercises.knee_raise.features import get_knee_raise_right_features_yolo

# ─────────────────────────────────────────────
# 더미 신체 좌표 (픽셀 단위, 720×1280 화면 기준 가상 값)
# ─────────────────────────────────────────────
nose       = (320, 80)
left_ear   = (295, 95)
right_ear  = (345, 95)

left_sh    = (260, 210)   # 왼쪽 어깨
right_sh   = (380, 210)   # 오른쪽 어깨
left_el    = (240, 320)   # 왼쪽 팔꿈치
right_el   = (400, 320)   # 오른쪽 팔꿈치
left_wr    = (230, 430)   # 왼쪽 손목
right_wr   = (410, 430)   # 오른쪽 손목

left_hip   = (275, 440)   # 왼쪽 골반
right_hip  = (365, 440)   # 오른쪽 골반
left_knee  = (270, 570)   # 왼쪽 무릎
right_knee = (370, 570)   # 오른쪽 무릎
left_ank   = (265, 700)   # 왼쪽 발목
right_ank  = (375, 700)   # 오른쪽 발목

# ─────────────────────────────────────────────
# MP pts (MediaPipe 인덱스)
# ─────────────────────────────────────────────
mp_pts = {
    0:  nose,
    7:  left_ear,   8:  right_ear,
    11: left_sh,    12: right_sh,
    13: left_el,    14: right_el,
    15: left_wr,    16: right_wr,
    23: left_hip,   24: right_hip,
    25: left_knee,  26: right_knee,
    27: left_ank,   28: right_ank,
}

# ─────────────────────────────────────────────
# YOLO pts (COCO 인덱스)
# ─────────────────────────────────────────────
yolo_pts = {
    0:  nose,
    3:  left_ear,   4:  right_ear,
    5:  left_sh,    6:  right_sh,
    7:  left_el,    8:  right_el,
    9:  left_wr,    10: right_wr,
    11: left_hip,   12: right_hip,
    13: left_knee,  14: right_knee,
    15: left_ank,   16: right_ank,
}

PASS = "[PASS]"
FAIL = "[FAIL]"

def compare(name, a, b, ignore_indices=None):
    if a is None or b is None:
        print(f"  {FAIL}  {name} — None 반환 (a={a}, b={b})")
        return False
    if len(a) != len(b):
        print(f"  {FAIL}  {name} — 길이 다름 ({len(a)} vs {len(b)})")
        return False
    all_ok = True
    for i, (va, vb) in enumerate(zip(a, b)):
        if ignore_indices and i in ignore_indices:
            print(f"  [SKIP] {name}[{i}]  MP={va:.4f}  YOLO={vb:.4f}  (계산 방식 다름, 스킵)")
            continue
        ok = abs(va - vb) < 1e-9
        tag = PASS if ok else FAIL
        print(f"  {tag}  {name}[{i}]  MP={va:.4f}  YOLO={vb:.4f}  diff={abs(va-vb):.2e}")
        if not ok:
            all_ok = False
    return all_ok


print("=" * 60)
print("리펙토링 검증: MP 버전 vs YOLO 버전 (동일 좌표)")
print("=" * 60)

# ─────────────────────────────────────────────
# 1. bird_dog
# ─────────────────────────────────────────────
print("\n[1] BirdDog  (14차원)")
a = get_bird_dog_features_mp(mp_pts)
b = get_bird_dog_features_yolo(yolo_pts)
print(f"  MP  결과: {a}")
print(f"  YOLO결과: {b}")
ok1 = compare("bird_dog", a, b)
print(f"  → {'전체 PASS' if ok1 else '일부 FAIL'}")

# ─────────────────────────────────────────────
# 2. neck_rotation
# ─────────────────────────────────────────────
print("\n[2] NeckRotation  (4차원)")
a = get_neck_rotation_features_mp(mp_pts)
b = get_neck_rotation_features_yolo(yolo_pts)
print(f"  MP  결과: {a}")
print(f"  YOLO결과: {b}")
ok2 = compare("neck_rotation", a, b)
print(f"  → {'전체 PASS' if ok2 else '일부 FAIL'}")

# ─────────────────────────────────────────────
# 3. shoulder_front_raise
#    trunk[0], shoulder_rise[1]: 계산 방식이 달라서 스킵
#    나머지 [2] arm_raise, [3] elbow_angle, [4] h_err 는 동일해야 함
#    [5] support_dist: YOLO는 r_wr(10)로 계산, MP도 r_wr(16)로 동일 → 같아야 함
# ─────────────────────────────────────────────
print("\n[3] ShoulderFrontRaiseLeft  (6차원)")
print("    * [0]trunk, [1]shoulder_rise: 계산 방식 다름 (YOLO=픽셀거리, MP=각도) → 스킵")
a = get_shoulder_front_raise_left_features_mp(mp_pts)
b = get_shoulder_front_raise_left_features_yolo(yolo_pts)
print(f"  MP  결과: {a}")
print(f"  YOLO결과: {b}")
ok3 = compare("shoulder", a, b, ignore_indices={0, 1})
print(f"  → {'전체 PASS' if ok3 else '일부 FAIL'}")

# ─────────────────────────────────────────────
# 4. knee_raise (YOLO only — MP 버전 없음)
#    기본 동작 확인만
# ─────────────────────────────────────────────
print("\n[4] KneeRaiseRight YOLO (3차원) — MP 대조 없음, 값 유효성만 확인")
r = get_knee_raise_right_features_yolo(yolo_pts)
print(f"  YOLO결과: {r}")
if r is not None and len(r) == 3 and all(isinstance(v, float) for v in r):
    print(f"  {PASS}  3차원 float 반환")
else:
    print(f"  {FAIL}  예상 외 반환값")

# ─────────────────────────────────────────────
# 5. 종합
# ─────────────────────────────────────────────
print("\n" + "=" * 60)
if ok1 and ok2 and ok3:
    print("최종 결과: ✅ 모두 PASS — 리펙토링 전후 동일한 출력")
else:
    print("최종 결과: ❌ 일부 FAIL — 확인 필요")
print("=" * 60)
