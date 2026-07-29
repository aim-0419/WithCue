# clips 폴더의 rep 단위 영상에 rule-based 보상동작 탐지(detect_compensations)를 돌려
# 팔꿈치 굽힘·어깨 상승 탐지 정확도를 측정한다.
# 2D 영상이므로 어깨 상승(3D 깊이 필요)은 평가 제외 — 팔꿈치 굽힘만 유효.
#
# 사용법:
#   python scripts/eval_compensation.py          # GPU (기본)
#   python scripts/eval_compensation.py --cpu

import sys
import csv
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import torch
torch.backends.cudnn.benchmark = False

from app.services.ai_service import YOLODetector
from app.core.config import settings
from app.exercises.shoulder_front_raise.compensation import detect_compensations

CLIPS_DIR = (
    Path(__file__).resolve().parent.parent
    / "app" / "public" / "recordings" / "shoulder_front_raise" / "clips"
)
OUT_DIR = Path(__file__).resolve().parent.parent / "app" / "public" / "metrics"

COCO_TO_8 = [5, 7, 9, 6, 8, 10, 11, 12]


def _label_of(stem: str):
    s = stem.lower()
    if s.endswith("_normal"):  return "normal"
    if s.endswith("_elbow"):   return "elbow"
    if s.endswith("_shoulder"): return "shoulder"
    return None


def _compute_scale(kps_xy_list):
    """첫 N 프레임의 어깨-엉덩이 픽셀 거리 평균으로 스케일 계산 (한 번만 호출)."""
    torso_vals = []
    for kps_xy in kps_xy_list:
        if len(kps_xy) < 13:
            continue
        sh_y = (float(kps_xy[5][1]) + float(kps_xy[6][1])) / 2.0
        hp_y = (float(kps_xy[11][1]) + float(kps_xy[12][1])) / 2.0
        torso_px = abs(hp_y - sh_y)
        if torso_px > 10:
            torso_vals.append(torso_px)
    if not torso_vals:
        return 1.0 / 1000.0
    return 0.5 / (sum(torso_vals) / len(torso_vals))  # 어깨-엉덩이 ≈ 0.5m 기준


def _kps_to_fake3d(kps_xy, scale):
    """YOLO 2D 픽셀 좌표 → detect_compensations 형식. 고정 스케일 적용."""
    kps = {}
    for coco_idx in range(17):
        if coco_idx < len(kps_xy):
            x, y = float(kps_xy[coco_idx][0]), float(kps_xy[coco_idx][1])
            kps[coco_idx] = {"x_m": x * scale, "y_m": y * scale, "z": 0.0}
    return kps


def run_clip(video_path: Path, detector: YOLODetector):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None

    all_kps_xy = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        result = detector.infer(frame)
        if result and result.keypoints is not None and len(result.keypoints.xy) > 0:
            all_kps_xy.append(result.keypoints.xy[0].cpu().numpy())
    cap.release()

    if not all_kps_xy:
        return None

    # 스케일은 초기 안정 구간(첫 5 프레임)에서 한 번만 계산
    scale = _compute_scale(all_kps_xy[:5])
    frames = [_kps_to_fake3d(kps_xy, scale) for kps_xy in all_kps_xy]

    _, reasons = detect_compensations(frames, arm_side='L')
    return reasons


def main():
    device = "cpu" if "--cpu" in sys.argv else "cuda"
    print(f"YOLO 로딩 (device={device})...")
    detector = YOLODetector(settings.yolo_model_path, device=device)

    clips = sorted(CLIPS_DIR.glob("*.mp4"))
    rows = []

    print(f"\n총 {len(clips)}개 클립 처리\n")
    for vp in clips:
        label = _label_of(vp.stem)
        if label is None:
            continue

        reasons = run_clip(vp, detector)
        if reasons is None:
            print(f"  [skip] {vp.name} (열기 실패)")
            continue

        detected_elbow    = any("팔꿈치" in r for r in reasons)
        detected_shoulder = any("어깨" in r for r in reasons)

        if label == "elbow":
            correct = detected_elbow
            tag = "오류(elbow)"
        elif label == "shoulder":
            correct = detected_shoulder
            tag = "오류(shoulder)"
        else:
            correct = not (detected_elbow or detected_shoulder)
            tag = "정상"

        mark = "✓" if correct else "✗"
        detected_str = " / ".join(reasons) if reasons else "정상"
        print(f"  {mark} [{tag}] {vp.name}")
        print(f"      탐지: {detected_str}")

        rows.append({
            "video":    vp.name,
            "label":    label,
            "detected": detected_str,
            "correct":  correct,
        })

    # 요약
    elbow_rows    = [r for r in rows if r["label"] == "elbow"]
    shoulder_rows = [r for r in rows if r["label"] == "shoulder"]
    normal_rows   = [r for r in rows if r["label"] == "normal"]

    print(f"\n{'='*60}")
    print("  결과 요약")
    print(f"{'='*60}")

    def _acc(subset):
        if not subset: return 0, 0
        ok = sum(1 for r in subset if r["correct"])
        return ok, len(subset)

    e_ok, e_tot = _acc(elbow_rows)
    s_ok, s_tot = _acc(shoulder_rows)
    n_ok, n_tot = _acc(normal_rows)
    total_ok  = e_ok + s_ok + n_ok
    total_tot = e_tot + s_tot + n_tot

    print(f"  팔꿈치 탐지:  {e_ok}/{e_tot}  ({e_ok/e_tot*100:.1f}%)" if e_tot else "  팔꿈치 탐지: 샘플 없음")
    print(f"  어깨 탐지:   {s_ok}/{s_tot}  ({s_ok/s_tot*100:.1f}%)" if s_tot else "  어깨 탐지: 샘플 없음")
    print(f"  정상 유지:   {n_ok}/{n_tot}  ({n_ok/n_tot*100:.1f}%)" if n_tot else "  정상 유지: 샘플 없음")
    print(f"  ─────────────────────────")
    print(f"  전체 정확도: {total_ok}/{total_tot}  ({total_ok/total_tot*100:.1f}%)" if total_tot else "")

    # CSV 저장
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUT_DIR / f"eval_compensation_{ts}.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["video", "label", "detected", "correct"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n[저장] {csv_path}")


if __name__ == "__main__":
    main()
