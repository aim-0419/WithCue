# 어깨 전방 거상 정상 영상에서 DTW 레퍼런스 JSON 생성 (MediaPipe)
import os
import json
import cv2
import mediapipe as mp
import numpy as np

from app.exercises.shoulder_front_raise.features import get_shoulder_front_raise_left_features_mp


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
    save_path = "./app/assets/reference/shoulder_front_raise_left_reference_mp.json"

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

    BaseOptions = mp.tasks.BaseOptions
    PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
    VisionRunningMode = mp.tasks.vision.RunningMode
    PoseLandmarker = mp.tasks.vision.PoseLandmarker

    model_path = "./app/assets/models/pose_landmarker_full.task"

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=VisionRunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.3,
        min_pose_presence_confidence=0.3,
        min_tracking_confidence=0.3,
        output_segmentation_masks=False,
    )

    sequence = []
    source_frame_indices = []
    frame_idx = 0
    timestamp_ms = 0

    with PoseLandmarker.create_from_options(options) as landmarker:
        while True:
            ret, frame_bgr = cap.read()
            if not ret:
                break

            if frame_idx % 3 != 0:
                frame_idx += 1
                timestamp_ms += int(1000 / fps)
                continue

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

            result = landmarker.detect_for_video(mp_image, timestamp_ms)

            if result.pose_landmarks:
                lms = result.pose_landmarks[0]

                pts = {}
                for i, lm in enumerate(lms):
                    vis = getattr(lm, "visibility", 1.0)
                    if vis < 0.3:
                        continue
                    pts[i] = (lm.x * width, lm.y * height)

                features = get_shoulder_front_raise_left_features_mp(pts)
                if features is not None:
                    current = tuple(round(v, 3) for v in features)
                    prev = tuple(round(v, 3) for v in sequence[-1]) if sequence else None
                    if current != prev:
                        sequence.append(features)
                        source_frame_indices.append(frame_idx)

            frame_idx += 1
            timestamp_ms += int(1000 / fps)

    cap.release()

    if len(sequence) == 0:
        raise RuntimeError("유효한 feature가 하나도 추출되지 않았습니다.")

    cut = max(15, int(len(sequence) * 0.1))
    sequence = sequence[cut:]
    source_frame_indices = source_frame_indices[cut:]

    if len(sequence) < 10:
        raise RuntimeError("초반 구간 제거 후 sequence가 너무 짧습니다.")

    raise_idx = 2
    smooth_raise_values = moving_average([f[raise_idx] for f in sequence], window=5)

    start_threshold = 35.0
    start_idx = None
    for i, v in enumerate(smooth_raise_values):
        if v >= start_threshold:
            start_idx = i
            break
    if start_idx is None:
        raise RuntimeError("시작 지점을 찾지 못했습니다.")

    peak_idx = None
    for i in range(start_idx + 2, len(smooth_raise_values) - 2):
        prev_v = smooth_raise_values[i - 1]
        curr_v = smooth_raise_values[i]
        next_v = smooth_raise_values[i + 1]
        if curr_v >= 80.0 and curr_v >= prev_v and curr_v >= next_v:
            peak_idx = i
            break
    if peak_idx is None:
        search_end = min(len(smooth_raise_values), start_idx + 60)
        peak_idx = start_idx + int(np.argmax(smooth_raise_values[start_idx:search_end]))

    peak_val = float(smooth_raise_values[peak_idx])
    end_threshold = peak_val * 0.3
    end_idx = len(sequence) - 1

    for i in range(peak_idx + 1, len(sequence) - 4):
        if all(v <= end_threshold for v in smooth_raise_values[i:i + 5]):
            end_idx = i
            break

    if end_idx <= peak_idx:
        end_idx = min(len(sequence) - 1, peak_idx + 20)

    trimmed_sequence = sequence[start_idx:end_idx + 1]
    trimmed_source_frames = source_frame_indices[start_idx:end_idx + 1]
    peak_in_trim = int(np.argmax([f[2] for f in trimmed_sequence]))

    payload = {
        "exercise": "SHOULDER_FRONT_RAISE_LEFT",
        "fps": fps,
        "window_frames": min(30, len(trimmed_sequence)),
        "meta": {
            "cut_front_count": cut,
            "start_idx": start_idx,
            "end_idx": end_idx,
            "peak_idx": peak_idx,
            "start_source_frame": int(trimmed_source_frames[0]) if trimmed_source_frames else None,
            "end_source_frame": int(trimmed_source_frames[-1]) if trimmed_source_frames else None,
            "peak_idx_in_trimmed": peak_in_trim,
            "sequence_length": len(trimmed_sequence),
        },
        "sequence": trimmed_sequence,
    }

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[완료] 저장 경로: {save_path}")
    print(f"[완료] 최종 sequence 길이: {len(trimmed_sequence)}")


if __name__ == "__main__":
    main()
