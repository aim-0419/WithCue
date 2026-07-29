# 기존에 저장된 원본 운동 영상을 rep별로 절단해 clips 폴더에 저장하는 스크립트.
# 사용법: python scripts/cut_recordings.py [영상경로 또는 폴더경로]
#   인자 없음 → recordings/shoulder_front_raise/originals/ 전체 처리
#   파일 지정 → 해당 파일 하나만 처리
#   폴더 지정 → 폴더 안의 모든 .mp4 처리

import sys
import cv2
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import torch
torch.backends.cudnn.benchmark = False

from ultralytics import YOLO
from app.exercises.shoulder_front_raise.features import get_shoulder_front_raise_left_features_yolo
from app.exercises.shoulder_front_raise.compensation import detect_compensations

# ── 경로 ──────────────────────────────────────────────────────────────────────
BACKEND_DIR   = Path(__file__).resolve().parents[1]
YOLO_PATH     = BACKEND_DIR / "app/assets/models/yolov8n-pose.pt"
ORIGINALS_DIR = BACKEND_DIR / "app/public/recordings/shoulder_front_raise/originals"
CLIPS_DIR     = BACKEND_DIR / "app/public/recordings/shoulder_front_raise/clips"

# ── rep 감지 임계값 (processor.py와 동일) ─────────────────────────────────────
RAISE_THRESHOLD = 110.0
DOWN_THRESHOLD  = 90.0
MIN_PEAK_ANGLE  = 110.0

LABEL_MAP = {"정상": "normal"}


def _label_short(label: str) -> str:
    if label in LABEL_MAP:
        return LABEL_MAP[label]
    if "팔꿈치" in label:
        return "elbow"
    if "어깨" in label:
        return "shoulder"
    if "상체" in label:
        return "trunk"
    return "unknown"


def _keypoints_to_fake3d(kps_xy: np.ndarray) -> dict:
    """YOLO 2D 픽셀 → compensation이 요구하는 keypoints dict (Z=0)."""
    kps = {}
    for idx in range(len(kps_xy)):
        x, y = float(kps_xy[idx][0]), float(kps_xy[idx][1])
        kps[idx] = {"x_m": x, "y_m": y, "z": 0.0, "x": x, "y": y}
    return kps


def _detect_reps(video_path: Path, model: YOLO) -> list[dict]:
    """
    영상에서 rep 경계 프레임과 보상 라벨을 추출한다.
    반환값: [{"rep": int, "start_f": int, "end_f": int, "label": str}, ...]
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"  [오류] 열기 실패: {video_path.name}")
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    rep_count  = 0
    rep_state  = "down"
    rep_peak   = 0.0
    comp_buf   = []
    frame_idx  = 0
    start_frames: dict[int, int] = {}  # rep_num → start frame
    end_frames:   dict[int, int] = {}  # rep_num → end frame
    labels:       dict[int, str] = {}

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model(frame, verbose=False)
        if results[0].keypoints is None or len(results[0].keypoints.xy) == 0:
            frame_idx += 1
            continue

        kps_xy  = results[0].keypoints.xy[0].cpu().numpy()
        kps_pts = {i: (float(kps_xy[i][0]), float(kps_xy[i][1])) for i in range(len(kps_xy))}

        mp_features = get_shoulder_front_raise_left_features_yolo(kps_pts)
        if mp_features is None:
            frame_idx += 1
            continue

        arm_raise = float(mp_features[2])

        if rep_state == "down" and arm_raise >= RAISE_THRESHOLD:
            rep_state = "up"
            rep_peak  = arm_raise
            start_frames[rep_count + 1] = frame_idx

        elif rep_state == "up":
            rep_peak = max(rep_peak, arm_raise)
            if arm_raise <= DOWN_THRESHOLD:
                if rep_peak >= MIN_PEAK_ANGLE:
                    rep_count += 1
                    end_frames[rep_count] = frame_idx
                    _, reasons = detect_compensations(comp_buf, arm_side='L')
                    labels[rep_count] = reasons[0] if reasons else "정상"
                rep_state = "down"
                rep_peak  = 0.0
                comp_buf  = []

        if rep_state == "up":
            comp_buf.append(_keypoints_to_fake3d(kps_xy))

        frame_idx += 1

    cap.release()

    reps = sorted(end_frames.keys())
    rep_events = []
    for rep_num in reps:
        rep_events.append({
            "rep":     rep_num,
            "start_f": start_frames.get(rep_num, 0),
            "end_f":   end_frames[rep_num],
            "label":   labels[rep_num],
        })
    return rep_events, total_frames


def cut_video(video_path: Path, model: YOLO, out_dir: Path) -> int:
    """
    영상 한 개를 rep별로 절단해 out_dir에 저장한다.
    반환값: 저장된 클립 수
    """
    print(f"처리 중: {video_path.name}")
    result = _detect_reps(video_path, model)
    if isinstance(result, tuple):
        rep_events, total_frames = result
    else:
        print("  rep 없음")
        return 0

    if not rep_events:
        print("  rep 없음")
        return 0

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")

    # 타임스탬프: 파일명에서 추출 (record_20260617_104656_*)
    parts = video_path.stem.split("_")
    ts = f"{parts[1]}_{parts[2]}" if len(parts) >= 3 else video_path.stem

    saved = 0
    for i, ev in enumerate(rep_events):
        rep_num = ev["rep"]

        # 클립 시작: 첫 rep은 영상 처음, 나머지는 직전 end ~ 현재 start 중간점
        if i == 0:
            clip_start = 0
        else:
            prev_end  = rep_events[i - 1]["end_f"]
            curr_start = ev["start_f"]
            clip_start = (prev_end + curr_start) // 2

        # 클립 끝: 마지막 rep은 영상 끝, 나머지는 현재 end ~ 다음 start 중간점
        if i < len(rep_events) - 1:
            next_start = rep_events[i + 1]["start_f"]
            clip_end   = (ev["end_f"] + next_start) // 2
        else:
            clip_end = total_frames

        if clip_end <= clip_start:
            continue

        short   = _label_short(ev["label"])
        out_path = out_dir / f"rep{rep_num:02d}_{ts}_{short}.mp4"
        writer   = cv2.VideoWriter(str(out_path), fourcc, fps, (w, h))

        cap.set(cv2.CAP_PROP_POS_FRAMES, clip_start)
        for _ in range(clip_end - clip_start):
            ret, frame = cap.read()
            if not ret:
                break
            writer.write(frame)
        writer.release()

        print(f"  rep{rep_num:02d} [{clip_start}~{clip_end}프레임] {ev['label']} → {out_path.name}")
        saved += 1

    cap.release()
    return saved


def main():
    if not YOLO_PATH.exists():
        print(f"YOLO 모델 없음: {YOLO_PATH}")
        sys.exit(1)

    # 처리 대상 결정
    if len(sys.argv) >= 2:
        target = Path(sys.argv[1])
        if target.is_file():
            video_files = [target]
            out_dir = CLIPS_DIR
        elif target.is_dir():
            video_files = sorted(target.glob("*.mp4"))
            out_dir = CLIPS_DIR
        else:
            print(f"경로가 없습니다: {target}")
            sys.exit(1)
    else:
        video_files = sorted(ORIGINALS_DIR.glob("*.mp4"))
        out_dir = CLIPS_DIR

    if not video_files:
        print("처리할 영상이 없습니다.")
        sys.exit(0)

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"YOLO 로드 중 (CPU)...")
    model = YOLO(str(YOLO_PATH))
    model.to("cpu")

    total_saved = 0
    for vpath in video_files:
        total_saved += cut_video(vpath, model, out_dir)

    print(f"\n완료: 총 {total_saved}개 클립 저장 → {out_dir}")


if __name__ == "__main__":
    main()
