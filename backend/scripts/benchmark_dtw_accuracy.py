# 라벨된 영상(normal/err)을 실제 DTW 프로세서에 통과시켜 유사도를 수집하고,
# 임계값을 훑어 '정상 vs 오류' 판정 정확도(혼동행렬/정밀도/재현율)를 계산하는 오프라인 벤치마크.
# 라이브 서버와 동일한 프로세서 경로를 그대로 재사용하므로, 판정 로직은 프로덕션과 일치한다.
# 결과는 콘솔 표 + app/public/metrics/benchmark_dtw_<타임스탬프>.csv 로 저장한다.
#
# 사용법:
#   python scripts/benchmark_dtw_accuracy.py                # 전체 운동
#   python scripts/benchmark_dtw_accuracy.py neck_rotation  # 특정 운동만
#
# ※ 영상은 RGB(2D)이므로 라이브의 3D(depth) 경로가 아닌 2D 픽셀 경로로 처리된다.
#    reference_yolo.json 이 2D로 생성됐으므로 좌표계는 서로 일치한다.

import sys
import csv
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import torch
# 서버가 GPU를 점유한 상태로도 돌릴 수 있게 CPU 사용 (test_compensation.py와 동일 정책).
torch.backends.cudnn.benchmark = False

from app.services.ai_service import YOLODetector
from app.core.config import settings
from app.core.utils import extract_keypoints

ASSETS_DIR = Path(__file__).resolve().parent.parent / "app" / "assets"
REF_DIR = ASSETS_DIR / "reference"
OUT_DIR = Path(__file__).resolve().parent.parent / "app" / "public" / "metrics"


# 운동별 (DTW 엔진 + 프로세서) 생성기와 영상 glob. 라벨은 파일명으로 판별한다.
def _build_registry():
    from app.exercises.bird_dog.processor import BirdDogDTWProcessor, BirdDogDTW
    from app.exercises.shoulder_front_raise.processor import (
        ShoulderFrontRaiseLeftDTWProcessor, ShoulderFrontRaiseLeftDTW,
    )
    from app.exercises.neck_rotation.processor import NeckRotationDTWProcessor, NeckRotationDTW
    from app.exercises.straight_leg_raise.processor import (
        StraightLegRaiseRightDTWProcessor, StraightLegRaiseRightDTW,
    )

    return {
        "bird_dog": lambda: BirdDogDTWProcessor(
            BirdDogDTW(str(REF_DIR / "bird_dog_reference_yolo.json"))
        ),
        "shoulder_front_raise_left": lambda: ShoulderFrontRaiseLeftDTWProcessor(
            ShoulderFrontRaiseLeftDTW(str(REF_DIR / "shoulder_front_raise_left_reference_yolo.json")),
            mirror_input=False, rom=None,
        ),
        "neck_rotation": lambda: NeckRotationDTWProcessor(
            NeckRotationDTW(ref_path=str(REF_DIR / "neck_rotation_reference_yolo.json")), rom=None,
        ),
        "straight_leg_raise_left": lambda: StraightLegRaiseRightDTWProcessor(
            StraightLegRaiseRightDTW(str(REF_DIR / "straight_leg_raise_left_reference_yolo.json")),
            use_left_flip=True, rom=None,
        ),
        "straight_leg_raise_right": lambda: StraightLegRaiseRightDTWProcessor(
            StraightLegRaiseRightDTW(str(REF_DIR / "straight_leg_raise_left_reference_yolo.json")),
            use_left_flip=False, rom=None,
        ),
    }


# 파일명으로 정답 라벨을 판별한다. normal→1(정상), err/error→0(오류), 그 외→None(제외).
def _label_of(name: str):
    low = name.lower()
    if "normal" in low:
        return 1
    if "err" in low:  # err1, error 모두 포함
        return 0
    return None  # test / live_similarity / similarity / mediapipe 등은 제외


# 영상 한 개를 프로세서에 통과시켜 대표 유사도(움직임 구간 평균/최대)를 반환한다.
def _run_video(video_path: Path, detector: YOLODetector, make_processor):
    processor = make_processor()
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None

    sims = []
    reps = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        result = detector.infer(frame)
        keypoints = extract_keypoints(result)
        pts = {k: (v["x"], v["y"]) for k, v in keypoints.items()} if keypoints else {}
        mp_features = processor.extract_mp_features(pts) if pts else None

        out = processor.process(keypoints=keypoints, frame=frame, mp_features=mp_features) or {}
        sim = out.get("similarity")
        if sim is None:
            sim = out.get("accuracy_pct")
        if isinstance(sim, (int, float)) and sim > 0:
            sims.append(float(sim))
        reps = max(reps, out.get("rep_count") or 0)
        time.sleep(0.003)  # 비동기 DTW 계산 스레드가 따라오도록 소폭 대기

    cap.release()
    if not sims:
        return {"mean_sim": 0.0, "max_sim": 0.0, "frames": 0, "reps": reps}
    return {
        "mean_sim": round(sum(sims) / len(sims), 2),
        "max_sim": round(max(sims), 2),
        "frames": len(sims),
        "reps": reps,
    }


# 대표 유사도와 라벨로 임계값을 훑어 최적 정확도와 그때의 혼동행렬을 구한다.
def _best_threshold(rows):
    labeled = [(r["mean_sim"], r["label"]) for r in rows if r["label"] is not None]
    if len(labeled) < 2 or len({l for _, l in labeled}) < 2:
        return None
    best = None
    for i in range(0, 101):
        t = i * 1.0
        tp = sum(1 for s, l in labeled if l == 1 and s >= t)
        tn = sum(1 for s, l in labeled if l == 0 and s < t)
        fp = sum(1 for s, l in labeled if l == 0 and s >= t)
        fn = sum(1 for s, l in labeled if l == 1 and s < t)
        acc = (tp + tn) / len(labeled)
        if best is None or acc > best["accuracy"]:
            best = {"threshold": t, "accuracy": round(acc, 3),
                    "tp": tp, "tn": tn, "fp": fp, "fn": fn}
    return best


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    # --gpu: GPU로 추론(서버를 내린 상태에서 권장). 기본은 CPU(서버와 동시 실행 안전).
    device = "cuda" if "--gpu" in sys.argv else "cpu"
    only = args[0] if args else None
    registry = _build_registry()
    if only and only not in registry:
        print(f"지원하지 않는 운동: {only}\n선택지: {', '.join(registry)}")
        return

    print(f"YOLO 모델 로딩 (device={device})...")
    detector = YOLODetector(settings.yolo_model_path, device=device)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUT_DIR / f"benchmark_dtw_{ts}.csv"
    all_rows = []

    targets = [only] if only else list(registry)
    for ex in targets:
        videos = sorted(ASSETS_DIR.glob(f"{ex}_*.mp4"))
        rows = []
        for vp in videos:
            label = _label_of(vp.name)
            if label is None:
                continue
            print(f"  [{ex}] {vp.name} 처리 중...")
            stat = _run_video(vp, detector, registry[ex])
            if stat is None:
                print(f"    (열기 실패, 건너뜀)")
                continue
            row = {"exercise": ex, "video": vp.name, "label": label, **stat}
            rows.append(row)
            all_rows.append(row)

        print(f"\n=== {ex} ===")
        for r in rows:
            tag = "정상" if r["label"] == 1 else "오류"
            print(f"  {tag:4s} | mean={r['mean_sim']:6.2f} max={r['max_sim']:6.2f} "
                  f"reps={r['reps']} | {r['video']}")
        best = _best_threshold(rows)
        if best:
            print(f"  → 최적 임계값 {best['threshold']:.0f} | 정확도 {best['accuracy']*100:.1f}% "
                  f"(TP={best['tp']} TN={best['tn']} FP={best['fp']} FN={best['fn']})")
        else:
            print("  → 정확도 계산 불가 (정상/오류 라벨 영상이 각각 1개 이상 필요)")

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["exercise", "video", "label", "mean_sim", "max_sim", "frames", "reps"])
        w.writeheader()
        w.writerows(all_rows)
    print(f"\n[저장] {csv_path}")


if __name__ == "__main__":
    main()
