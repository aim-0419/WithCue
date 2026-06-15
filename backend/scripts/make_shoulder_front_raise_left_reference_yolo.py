# 정상 영상 읽어서 reference JSON 생성 (왼팔 전방 거상 기준)

import os
import json
import cv2
import numpy as np
import torch

torch.cuda.empty_cache()

from ultralytics import YOLO

from app.exercises.shoulder_front_raise.features import (
    get_shoulder_front_raise_left_features_yolo,
)


def moving_average(values, window=5):
    if len(values) == 0:
        return []
    if window <= 1:
        return list(values)
    kernel = np.ones(window, dtype=float) / window
    smoothed = np.convolve(values, kernel, mode="same")
    return smoothed.tolist()


def trim_outlier_tail(seq):
    cleaned = []
    for f in seq:
        trunk = f[0]
        shoulder_rise = f[1]
        left_arm_raise = f[2]
        left_elbow_angle = f[3]
        left_arm_h_err = f[4]
        support_dist = f[5]

        if trunk > 15:
            continue
        if shoulder_rise > 25:
            continue
        if left_elbow_angle < 80:
            continue
        if support_dist > 120:
            continue
        if left_arm_raise < 0 or left_arm_raise > 170:
            continue
        if left_arm_h_err > 100:
            continue

        cleaned.append(f)

    return cleaned


def main():
    video_path = "./app/assets/shoulder_front_raise_left_normal.mp4"
    save_path="./app/assets/reference/shoulder_front_raise_left_reference_yolo.json"

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

    model = YOLO(
        "./app/assets/models/yolov8s-pose.pt"
    )
    model.to("cpu") 
    
    sequence = []
    source_frame_indices = []

    frame_idx = 0
    
    while True:
        ret, frame_bgr = cap.read()
        if not ret:
            break

        if frame_idx % 3 != 0:
            frame_idx += 1
            continue


        infer_frame = cv2.resize(
            frame_bgr,
            (640,360)
        )

        results = model(
            infer_frame,
            verbose=False,
            device="cpu"
        )

        if (
            results
            and results[0].keypoints is not None
        ):

            kpts = results[0].keypoints

            xy = kpts.xy[0].cpu().numpy()

            conf = (
                kpts.conf[0].cpu().numpy()
                if kpts.conf is not None
                else None
            )

            pts = {}

            for i,p in enumerate(xy):

                if conf is not None and conf[i] < 0.3:
                    continue

                pts[i] = (
                    float(p[0]),
                    float(p[1])
                )

            features = (
                get_shoulder_front_raise_left_features_yolo(
                    pts
                )
            )

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

    # 0) 초반 이상치 제거
    cut = max(15, int(len(sequence) * 0.1))
    sequence = sequence[cut:]
    source_frame_indices = source_frame_indices[cut:]

    if len(sequence) < 10:
        raise RuntimeError("초반 구간 제거 후 sequence가 너무 짧습니다.")

        # 1) raise 값 + smoothing
    raise_idx = 2
    raw_raise_values = [f[raise_idx] for f in sequence]
    smooth_raise_values = moving_average(raw_raise_values, window=5)

    # -------------------------------------------------
    # 2) start
    # 너무 초반은 제외하고, 처음 의미 있게 올라가기 시작한 지점
    # -------------------------------------------------
    start_threshold = 35.0

    start_idx = None
    for i in range(len(smooth_raise_values)):
        if smooth_raise_values[i] >= start_threshold:
            start_idx = i
            break

    if start_idx is None:
        raise RuntimeError("시작 지점을 찾지 못했습니다.")

    # -------------------------------------------------
    # 3) peak
    # 첫 번째 rep의 local peak를 찾는다
    # -------------------------------------------------
    peak_idx = None
    peak_search_threshold = 80.0

    for i in range(start_idx + 2, len(smooth_raise_values) - 2):
        prev_v = smooth_raise_values[i - 1]
        curr_v = smooth_raise_values[i]
        next_v = smooth_raise_values[i + 1]

        # local maximum + 충분히 올라간 값
        if curr_v >= peak_search_threshold and curr_v >= prev_v and curr_v >= next_v:
            peak_idx = i
            break

    # fallback: start 이후 첫 60프레임 안에서 최대값
    if peak_idx is None:
        search_end = min(len(smooth_raise_values), start_idx + 60)
        rel_idx = int(np.argmax(smooth_raise_values[start_idx:search_end]))
        peak_idx = start_idx + rel_idx

    peak_val = float(smooth_raise_values[peak_idx])

    # -------------------------------------------------
    # 4) end
    # peak 이후 충분히 내려간 상태가 몇 프레임 연속 유지되면 종료
    # -------------------------------------------------
    end_threshold = peak_val * 0.3
    hold_n = 5
    end_idx = len(sequence) - 1

    for i in range(peak_idx + 1, len(sequence) - hold_n + 1):
        window_vals = smooth_raise_values[i:i + hold_n]
        if all(v <= end_threshold for v in window_vals):
            end_idx = i
            break

    if end_idx <= peak_idx:
        end_idx = min(len(sequence) - 1, peak_idx + 20)

    trimmed_sequence = sequence[start_idx:end_idx + 1]
    trimmed_source_frames = source_frame_indices[start_idx:end_idx + 1]

    # 6) 최종 meta
    peak_in_trim = int(np.argmax([f[2] for f in trimmed_sequence]))

    payload = {
        "exercise": "SHOULDER_FRONT_RAISE_LEFT",
        "fps": fps,
        "window_frames": min(30, len(trimmed_sequence)),
        "meta": {
            "cut_front_count": cut,
            "start_idx_in_cut_sequence": start_idx,
            "end_idx_in_cut_sequence": end_idx,
            "peak_idx_in_cut_sequence": peak_idx,
            "start_source_frame": int(trimmed_source_frames[0]) if trimmed_source_frames else None,
            "end_source_frame": int(trimmed_source_frames[-1]) if trimmed_source_frames else None,
            "peak_idx_in_trimmed_sequence": peak_in_trim,
            "sequence_length": len(trimmed_sequence),
        },
        "sequence": trimmed_sequence,
    }

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[완료] 저장 경로: {save_path}")
    print(f"[완료] fps: {fps}")
    print(f"[완료] 원본 sequence 길이(초반 제거 후): {len(sequence)}")
    print(f"[완료] start={start_idx}, peak={peak_idx}, end={end_idx}")
    print(f"[완료] 최종 sequence 길이: {len(trimmed_sequence)}")
    print(f"[완료] feature 차원: {len(trimmed_sequence[0]) if trimmed_sequence else 0}")


if __name__ == "__main__":
    main()