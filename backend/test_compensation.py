# 어깨 전방 거상 보상자세 감지 오프라인 테스트 스크립트.
# assets 폴더의 shoulder_front_raise_*.mp4 영상에서 YOLO로 2D 관절 추출 후
# detect_compensations()를 실행하고 결과를 CSV로 저장한다.
# ※ 2D 영상이므로 Z=0 처리: trunk_lean은 감지 불가, 팔꿈치/어깨 감지만 유효.

import sys
import csv
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

import torch
# 서버 프로세스가 GPU를 점유한 상태에서 실행되므로 CPU 사용.
# Jetson 통합 메모리 구조상 CUDA 컨텍스트를 두 개 동시에 열면 cuDNN 플랜 할당이 실패함.
torch.backends.cudnn.benchmark = False

from ultralytics import YOLO
from app.exercises.shoulder_front_raise.features import get_shoulder_front_raise_left_features_yolo
from app.exercises.shoulder_front_raise.compensation import detect_compensations

# ── 경로 설정 ─────────────────────────────────────────────────────────────────
ASSETS_DIR  = Path(__file__).parent / "app/assets"
YOLO_PATH   = ASSETS_DIR / "models/yolov8n-pose.pt"
OUTPUT_CSV  = Path(__file__).parent / "compensation_test_results.csv"

VIDEO_FILES = sorted(ASSETS_DIR.glob("shoulder_front_raise_left_*.mp4"))

# ── rep 감지 파라미터 (processor.py와 동일) ───────────────────────────────────
RAISE_THRESHOLD = 110.0
DOWN_THRESHOLD  = 90.0
MIN_PEAK_ANGLE  = 110.0

# YOLO COCO 관절 번호
COCO_TO_8 = [5, 7, 9, 6, 8, 10, 11, 12]


def keypoints_to_fake3d(kps_xy: np.ndarray) -> dict:
    """
    YOLO 2D 픽셀 좌표 → compensation에서 요구하는 keypoints dict.
    x_m = pixel_x, y_m = pixel_y, z = 0.0
    (compensation 내부에서 y_m이 반전되어 Y위 convention으로 처리됨)
    """
    kps = {}
    for coco_idx in range(17):
        if coco_idx < len(kps_xy):
            x, y = float(kps_xy[coco_idx][0]), float(kps_xy[coco_idx][1])
            kps[coco_idx] = {"x_m": x, "y_m": y, "z": 0.0, "x": x, "y": y}
    return kps


def process_video(video_path: Path, model: YOLO) -> list[dict]:
    """영상 한 개 처리 → rep별 결과 목록 반환."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"  [오류] 열기 실패: {video_path.name}")
        return []

    rep_count   = 0
    rep_state   = "down"
    rep_peak    = 0.0
    comp_buffer = []   # 현재 rep의 keypoints dict 목록
    results_out = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        yolo_results = model(frame, verbose=False)
        if (yolo_results[0].keypoints is None
                or len(yolo_results[0].keypoints.xy) == 0):
            continue

        kps_xy  = yolo_results[0].keypoints.xy[0].cpu().numpy()
        kps_pts = {i: (float(kps_xy[i][0]), float(kps_xy[i][1]))
                   for i in range(len(kps_xy))}

        mp_features = get_shoulder_front_raise_left_features_yolo(kps_pts)
        if mp_features is None:
            continue

        arm_raise = float(mp_features[2])

        # rep 상태 전이
        if rep_state == "down" and arm_raise >= RAISE_THRESHOLD:
            rep_state = "up"
            rep_peak  = arm_raise

        elif rep_state == "up":
            rep_peak = max(rep_peak, arm_raise)
            if arm_raise <= DOWN_THRESHOLD:
                if rep_peak >= MIN_PEAK_ANGLE:
                    rep_count += 1
                    # 보상자세 감지
                    kps_dict = keypoints_to_fake3d(kps_xy)
                    comp_buffer.append(kps_dict)
                    arm_side, reasons = detect_compensations(comp_buffer)
                    results_out.append({
                        "video":    video_path.name,
                        "rep":      rep_count,
                        "frames":   len(comp_buffer),
                        "arm":      "왼팔" if arm_side == 'L' else "오른팔",
                        "detected": " / ".join(reasons) if reasons else "정상",
                    })
                rep_state   = "down"
                rep_peak    = 0.0
                comp_buffer = []

        # rep 진행 중 프레임 누적
        if rep_state == "up":
            comp_buffer.append(keypoints_to_fake3d(kps_xy))

    cap.release()
    return results_out


def main():
    if not YOLO_PATH.exists():
        print(f"YOLO 모델 없음: {YOLO_PATH}")
        sys.exit(1)

    model = YOLO(str(YOLO_PATH))
    model.to("cpu")

    all_results = []
    for vpath in VIDEO_FILES:
        print(f"처리 중: {vpath.name}")
        reps = process_video(vpath, model)
        if reps:
            for r in reps:
                print(f"  rep{r['rep']} ({r['frames']}f): {r['detected']}")
        else:
            print("  rep 없음")
        all_results.extend(reps)

    # CSV 저장
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["video", "rep", "frames", "arm", "detected"])
        writer.writeheader()
        writer.writerows(all_results)

    print(f"\n결과 저장 완료: {OUTPUT_CSV}")
    print(f"총 {len(all_results)}개 rep 처리")


if __name__ == "__main__":
    main()
