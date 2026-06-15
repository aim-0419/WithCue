import os
import json
import cv2
import numpy as np
from ultralytics import YOLO

from app.exercises.neck_rotation.features import get_neck_rotation_features_yolo


def moving_average(values, window=5):
    if len(values) == 0:
        return []
    if window <= 1:
        return list(values)

    kernel = np.ones(window, dtype=float) / window
    smoothed = np.convolve(values, kernel, mode="same")
    return smoothed.tolist()


def main():
    video_path = "./app/assets/neck_rotation_normal.mp4"
    save_path = "./app/assets/reference/neck_rotation_reference_yolo.json"
    model_path = "./app/assets/models/yolov8n-pose.pt"

    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"영상 열기 실패: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0 or fps < 10 or fps > 120:
        fps = 30
    fps = int(round(fps))

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    model = YOLO(model_path)

    sequence = []
    source_frame_indices = []

    frame_idx = 0

    while True:
        ret, frame_bgr = cap.read()
        if not ret:
            break

        if frame_idx % 2 != 0:
            frame_idx += 1
            continue

        results = model(
            frame_bgr,
            verbose=False,
            device="cpu",
            imgsz=320,
        )

        if results and results[0].keypoints is not None:
            kpts = results[0].keypoints

            if kpts.xy is not None and len(kpts.xy) > 0:
                xy = kpts.xy[0].cpu().numpy()
                conf = kpts.conf[0].cpu().numpy() if kpts.conf is not None else None

                pts = {}
                for i, p in enumerate(xy):
                    if conf is not None and conf[i] < 0.3:
                        continue

                    x, y = float(p[0]), float(p[1])
                    if x <= 0 and y <= 0:
                        continue

                    pts[i] = (x, y)

                features = get_neck_rotation_features_yolo(pts)

                if features is not None:
                    current = tuple(round(v, 3) for v in features)
                    prev = tuple(round(v, 3) for v in sequence[-1]) if sequence else None

                    if current != prev:
                        sequence.append(features)
                        source_frame_indices.append(frame_idx)

        frame_idx += 1

    cap.release()

    if len(sequence) == 0:
        raise RuntimeError("유효한 feature가 하나도 추출되지 않았습니다.")

    if len(sequence) < 10:
        raise RuntimeError("추출된 sequence가 너무 짧습니다.")
    
    # 초반 안정화 구간 제거 (필수)
    warmup_skip = min(20, len(sequence) // 10)

    sequence = sequence[warmup_skip:]
    source_frame_indices = source_frame_indices[warmup_skip:]
    
    # 정면 구간부터 reference 시작
    neck_values = [abs(f[1]) for f in sequence]
    center_threshold = 8.0
    center_sustain = 8

    center_start_idx = None

    for i in range(0, len(neck_values) - center_sustain + 1):
        if all(v <= center_threshold for v in neck_values[i:i + center_sustain]):
            center_start_idx = i
            break

    if center_start_idx is None:
        raise RuntimeError("정면 시작 구간을 찾지 못했습니다.")

    sequence = sequence[center_start_idx:]
    source_frame_indices = source_frame_indices[center_start_idx:]

    # 목 회전은 정면 → 왼쪽 → 정면 → 오른쪽 → 정면 전체 흐름을 reference로 사용
    trimmed_sequence = sequence
    trimmed_source_frames = source_frame_indices

    turn_values = [abs(f[1]) for f in trimmed_sequence]
    peak_val = float(np.max(turn_values))
    peak_idx = int(np.argmax(turn_values))

    start_idx = 0
    end_idx = len(trimmed_sequence) - 1

    payload = {
        "exercise": "NECK_ROTATION",
        "fps": fps,
        "window_frames": min(30, len(trimmed_sequence)),
        "meta": {
            "start_idx_in_filtered_sequence": start_idx,
            "end_idx_in_filtered_sequence": end_idx,
            "peak_idx_in_filtered_sequence": peak_idx,
            "start_source_frame": int(trimmed_source_frames[0]) if trimmed_source_frames else None,
            "end_source_frame": int(trimmed_source_frames[-1]) if trimmed_source_frames else None,
            "sequence_length_before_trim": len(sequence),
            "sequence_length": len(trimmed_sequence),
            "peak_val": peak_val,
            
        },
        "sequence": trimmed_sequence,
    }

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[완료] 저장 경로: {save_path}")
    print(f"[완료] fps: {fps}")
    print(f"[완료] 필터 후 sequence 길이: {len(sequence)}")
    print(f"[완료] start={start_idx}, peak={peak_idx}, end={end_idx}")
    print(f"[완료] 최종 sequence 길이: {len(trimmed_sequence)}")
    print(f"[완료] feature 차원: {len(trimmed_sequence[0]) if trimmed_sequence else 0}")


if __name__ == "__main__":
    main()