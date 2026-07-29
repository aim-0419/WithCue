# public/recordings/*/clips/ 의 rep 단위 라벨 영상으로 DTW 유사도 정확도를 측정한다.
# 기존 benchmark_dtw_accuracy.py 가 assets/ 의 세션 단위 영상을 사용하는 것과 달리,
# 이미 rep별로 잘린 clips를 사용하므로 샘플이 풍부하고 평가 정밀도가 높다.
#
# 라벨 규칙 (파일명 suffix):
#   _normal  → 정상 (label=1)
#   _elbow   → 팔꿈치 굽힘 오류 (label=0)
#   _shoulder → 어깨 올라감 오류 (label=0)
#   _err     → 기타 오류 (label=0)
#
# 사용법:
#   python scripts/benchmark_clips.py          # 전체
#   python scripts/benchmark_clips.py shoulder_front_raise
#
# ※ 기본은 GPU. 서버 실행 중이면 종료 후 실행할 것.

import sys
import csv
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import torch
torch.backends.cudnn.benchmark = False

from app.services.ai_service import YOLODetector
from app.core.config import settings
from app.core.utils import extract_keypoints

CLIPS_ROOT = Path(__file__).resolve().parent.parent / "app" / "public" / "recordings"
REF_DIR    = Path(__file__).resolve().parent.parent / "app" / "assets" / "reference"
OUT_DIR    = Path(__file__).resolve().parent.parent / "app" / "public" / "metrics"


def _build_registry():
    from app.exercises.shoulder_front_raise.processor import (
        ShoulderFrontRaiseLeftDTWProcessor, ShoulderFrontRaiseLeftDTW,
    )
    from app.exercises.neck_rotation.processor import NeckRotationDTWProcessor, NeckRotationDTW
    from app.exercises.straight_leg_raise.processor import (
        StraightLegRaiseRightDTWProcessor, StraightLegRaiseRightDTW,
    )
    from app.exercises.bird_dog.processor import BirdDogDTWProcessor, BirdDogDTW

    return {
        "shoulder_front_raise": lambda: ShoulderFrontRaiseLeftDTWProcessor(
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
        "bird_dog": lambda: BirdDogDTWProcessor(
            BirdDogDTW(str(REF_DIR / "bird_dog_reference_yolo.json"))
        ),
    }


def _label_of(stem: str):
    """파일명 끝 suffix로 라벨 판별. None이면 평가 제외."""
    s = stem.lower()
    if s.endswith("_normal"):
        return 1
    if s.endswith("_elbow") or s.endswith("_shoulder") or s.endswith("_err"):
        return 0
    return None


def _run_clip(video_path: Path, detector: YOLODetector, make_processor):
    """영상 한 개(rep 단위)를 프로세서에 통과시켜 대표 유사도를 반환한다."""
    processor = make_processor()
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None

    sims = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        result   = detector.infer(frame)
        keypoints = extract_keypoints(result)
        pts = {k: (v["x"], v["y"]) for k, v in keypoints.items()} if keypoints else {}
        mp_features = processor.extract_mp_features(pts) if pts else None
        out = processor.process(keypoints=keypoints, frame=frame, mp_features=mp_features) or {}
        sim = out.get("similarity") or out.get("accuracy_pct")
        if isinstance(sim, (int, float)) and sim > 0:
            sims.append(float(sim))
        time.sleep(0.003)

    cap.release()
    if not sims:
        return {"mean_sim": 0.0, "max_sim": 0.0, "frames": 0}
    return {
        "mean_sim": round(sum(sims) / len(sims), 2),
        "max_sim":  round(max(sims), 2),
        "frames":   len(sims),
    }


def _best_threshold(rows):
    labeled = [(r["mean_sim"], r["label"]) for r in rows if r["label"] is not None]
    if len(labeled) < 2 or len({l for _, l in labeled}) < 2:
        return None
    best = None
    for t in range(0, 101):
        tp = sum(1 for s, l in labeled if l == 1 and s >= t)
        tn = sum(1 for s, l in labeled if l == 0 and s  < t)
        fp = sum(1 for s, l in labeled if l == 0 and s >= t)
        fn = sum(1 for s, l in labeled if l == 1 and s  < t)
        acc = (tp + tn) / len(labeled)
        if best is None or acc > best["acc"]:
            best = {"threshold": t, "acc": round(acc, 4),
                    "tp": tp, "tn": tn, "fp": fp, "fn": fn}
    return best


def main():
    args   = [a for a in sys.argv[1:] if not a.startswith("-")]
    device = "cpu" if "--cpu" in sys.argv else "cuda"
    only   = args[0] if args else None

    registry = _build_registry()
    if only and only not in registry:
        print(f"지원하지 않는 운동: {only}\n선택지: {', '.join(registry)}")
        return

    print(f"YOLO 모델 로딩 (device={device})...")
    detector = YOLODetector(settings.yolo_model_path, device=device)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUT_DIR / f"benchmark_clips_{ts}.csv"
    all_rows = []

    targets = [only] if only else list(registry)
    for ex in targets:
        clips_dir = CLIPS_ROOT / ex / "clips"
        if not clips_dir.exists():
            print(f"\n[{ex}] clips 폴더 없음, 건너뜀")
            continue

        clips = sorted(clips_dir.glob("*.mp4"))
        rows  = []
        for vp in clips:
            label = _label_of(vp.stem)
            if label is None:
                print(f"  [skip] {vp.name}")
                continue
            tag = "정상" if label == 1 else "오류"
            print(f"  [{ex}] {vp.name} ({tag}) 처리 중...")
            stat = _run_clip(vp, detector, registry[ex])
            if stat is None:
                print(f"    (열기 실패, 건너뜀)")
                continue
            row = {"exercise": ex, "video": vp.name, "label": label, **stat}
            rows.append(row)
            all_rows.append(row)
            print(f"    mean_sim={stat['mean_sim']}  max_sim={stat['max_sim']}  frames={stat['frames']}")

        # 운동별 결과 요약
        print(f"\n{'='*60}")
        print(f"  {ex} 결과")
        print(f"{'='*60}")
        normals = [r for r in rows if r["label"] == 1]
        errors  = [r for r in rows if r["label"] == 0]
        print(f"  정상 {len(normals)}개  |  오류 {len(errors)}개  |  합계 {len(rows)}개")
        if normals:
            sims = [r["mean_sim"] for r in normals]
            print(f"  정상 mean_sim: {min(sims):.1f} ~ {max(sims):.1f}  (avg {sum(sims)/len(sims):.1f})")
        if errors:
            sims = [r["mean_sim"] for r in errors]
            print(f"  오류 mean_sim: {min(sims):.1f} ~ {max(sims):.1f}  (avg {sum(sims)/len(sims):.1f})")

        best = _best_threshold(rows)
        if best:
            prec = best["tp"] / (best["tp"] + best["fp"]) if (best["tp"] + best["fp"]) > 0 else 0
            rec  = best["tp"] / (best["tp"] + best["fn"]) if (best["tp"] + best["fn"]) > 0 else 0
            print(f"  최적 임계값: {best['threshold']}  →  정확도 {best['acc']*100:.1f}%")
            print(f"  TP={best['tp']} TN={best['tn']} FP={best['fp']} FN={best['fn']}")
            print(f"  정밀도(Precision)={prec*100:.1f}%  재현율(Recall)={rec*100:.1f}%")
        else:
            print("  → 정상/오류 라벨이 각각 1개 이상 있어야 정확도 계산 가능")

    # CSV 저장
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["exercise", "video", "label", "mean_sim", "max_sim", "frames"])
        w.writeheader()
        w.writerows(all_rows)
    print(f"\n[저장] {csv_path}")


if __name__ == "__main__":
    main()
