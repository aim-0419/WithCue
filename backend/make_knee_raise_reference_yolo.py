# 정상 영상 읽어서 reference JSON 생성 (오른다리 Straight Leg Raise 기준)
# - 시작/끝 노이즈 제거
# - 핵심 동작 구간만 잘라서 저장
# - right 기준 reference 1개 생성용
# - left 영상은 나중에 flip_mediapipe_left_right() 후 right extractor 재사용

import os 
import json
import cv2
import numpy as np

from ultralytics import YOLO

from app.services.dtw_feature_extractor import (
    get_knee_raise_right_features_yolo,
    flip_yolo_left_right,
)

def moving_average(values, window=5):
    if len(values) == 0:
        return []
    if window <= 1:
        return list(values)

    kernel = np.ones(window, dtype=float) / window
    smoothed = np.convolve(values, kernel, mode="same")
    return smoothed.tolist()

# def trim_outlier_tail(seq):
#     """
#     SLR 오른다리 기준 약한 이상치 제거
#     feature:
#       [trunk, pelvic, right_hip_flexion, right_knee_angle, right_ankle_rel_y]
#     """
#     cleaned = []

#     for f in seq:
#         trunk = f[0]
#         pelvic = f[1]
#         right_hip_flexion = f[2]
#         right_knee_angle = f[3]
#         right_ankle_rel_y = f[4]

#         # 몸통 / 골반만 아주 큰 이상치만 제거
#         if trunk > 35:
#             continue
#         if pelvic > 35:
#             continue

#         # 무릎각도는 너무 심하게 접힌 경우만 제거
#         if right_knee_angle < 140:
#             continue

#         # 발목 높이도 극단값만 제거
#         if right_ankle_rel_y < -200 or right_ankle_rel_y > 600:
#             continue

#         cleaned.append(f)

#     return cleaned

def main():
    video_path = "./app/assets/knee_raise_left_normal.mp4"
    save_path = "./app/assets/reference/knee_raise_left_reference_yolo.json"
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
    
    debug_dir = "./app/assets/debug/knee_yolo"
    os.makedirs(debug_dir, exist_ok=True)

    sequence = []
    source_frame_indices = []

    frame_idx = 0

    while True:
        ret, frame_bgr = cap.read()
        if not ret:
            break

        # 기존 3프레임 샘플링 유지
        if frame_idx % 3 != 0:
            frame_idx += 1
            continue

        results = model(
            frame_bgr,
            verbose=False,
            device="cpu",
            imgsz=640,
        )
        
        if frame_idx % 24 == 0 and results:
            annotated = results[0].plot()
            cv2.imwrite(
                os.path.join(debug_dir, f"frame_{frame_idx:05d}.jpg"),
                annotated
            )

        if results and results[0].keypoints is not None:

            kpts = results[0].keypoints

            if kpts.xy is not None and len(kpts.xy) > 0:

                xy = kpts.xy[0].cpu().numpy()
                conf = (
                    kpts.conf[0].cpu().numpy()
                    if kpts.conf is not None
                    else None
                )

                pts = {}

                for i, p in enumerate(xy):

                    if conf is not None and conf[i] < 0.3:
                        continue

                    x, y = float(p[0]), float(p[1])

                    if x <= 0 and y <= 0:
                        continue

                    pts[i] = (x, y)

                pts = flip_yolo_left_right(pts)

                features = get_knee_raise_right_features_yolo(pts)

                if features is not None:

                    current = tuple(round(v, 3) for v in features)
                    prev = (
                        tuple(round(v, 3) for v in sequence[-1])
                        if sequence
                        else None
                    )

                    if current != prev:
                        sequence.append(features)
                        source_frame_indices.append(frame_idx)

        frame_idx += 1

    cap.release()

    if len(sequence) == 0:
        raise RuntimeError("유효한 feature가 하나도 추출되지 않았습니다.")

    # 0) 초기 버전에서는 이상치 하드 제거를 하지 않고 그대로 사용
    #    먼저 start / peak / end를 안정적으로 자른 뒤 필요하면 후처리로 제거
    if len(sequence) < 10:
        raise RuntimeError("추출된 sequence가 너무 짧습니다.")

    # 1) 핵심 기준 feature = left_ankle_rel_y(index=4)
    lift_idx = 2
    raw_lift_values = [f[lift_idx] for f in sequence]
    smooth_lift_values = moving_average(raw_lift_values, window=7)

    arr = np.array(smooth_lift_values, dtype=np.float32)
    n = len(arr)

    if n < 10:
        raise RuntimeError("sequence가 너무 짧아서 rep를 찾을 수 없습니다.")

    # -------------------------------------------------
    # 2) 가장 큰 peak 찾기
    # -------------------------------------------------
    peak_idx = None

    for i in range(2, len(arr) - 2):
        prev_v = arr[i - 1]
        curr_v = arr[i]
        next_v = arr[i + 1]

        if curr_v > 50 and curr_v >= prev_v and curr_v >= next_v:
            peak_idx = i
            break

    print("[DEBUG] sequence len:", len(sequence))
    print("[DEBUG] lift min:", float(np.min(arr)))
    print("[DEBUG] lift max:", float(np.max(arr)))
    print("[DEBUG] lift first10:", [round(float(v), 3) for v in arr[:10]])
    print("[DEBUG] lift last10:", [round(float(v), 3) for v in arr[-10:]])

    for idx in [0, len(sequence)//2, len(sequence)-1]:
        if 0 <= idx < len(sequence):
            print(f"[DEBUG] seq[{idx}]:", sequence[idx])
            
    # fallback
    if peak_idx is None:
        peak_idx = int(np.argmax(arr))
    peak_val = float(arr[peak_idx])

    if peak_val < 10:
        raise RuntimeError(f"peak 값이 너무 작습니다. peak_val={peak_val:.3f}")

    # -------------------------------------------------
    # 3) peak 이전 최저점 = start
    # -------------------------------------------------
    if peak_idx <= 2:
        start_idx = 0
    else:
        start_idx = int(np.argmin(arr[:peak_idx]))

    # -------------------------------------------------
    # 4) peak 이후 최저점 = end
    # -------------------------------------------------
    if peak_idx >= n - 3:
        end_idx = n - 1
    else:
        rel_end = int(np.argmin(arr[peak_idx:]))
        end_idx = peak_idx + rel_end

    if end_idx <= start_idx:
        raise RuntimeError(
            f"rep 구간이 비정상입니다. start_idx={start_idx}, peak_idx={peak_idx}, end_idx={end_idx}"
        )

    # -------------------------------------------------
    # 5) margin
    # -------------------------------------------------
    start_margin = 3
    end_margin = 3

    start_idx = max(0, start_idx - start_margin)
    end_idx = min(len(sequence) - 1, end_idx + end_margin)

    trimmed_sequence = sequence[start_idx:end_idx + 1]
    trimmed_source_frames = source_frame_indices[start_idx:end_idx + 1]

    if len(trimmed_sequence) < 5:
        raise RuntimeError("trimmed_sequence가 너무 짧습니다.")

    peak_in_trim = int(np.argmax([f[lift_idx] for f in trimmed_sequence]))

    payload = {
        "exercise": "KNEE_RAISE_LEFT",
        "fps": fps,
        "window_frames": min(30, len(trimmed_sequence)),
        "meta": {
            "start_idx_in_filtered_sequence": start_idx,
            "end_idx_in_filtered_sequence": end_idx,
            "peak_idx_in_filtered_sequence": peak_idx,
            "start_source_frame": int(trimmed_source_frames[0]) if trimmed_source_frames else None,
            "end_source_frame": int(trimmed_source_frames[-1]) if trimmed_source_frames else None,
            "peak_idx_in_trimmed_sequence": peak_in_trim,
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
    