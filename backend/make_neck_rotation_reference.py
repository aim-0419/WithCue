import os
import json
import cv2
import mediapipe as mp
import numpy as np

from app.services.dtw_feature_extractor import get_neck_rotation_features_mp


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
    save_path = "./app/assets/reference/neck_rotation_reference_mp.json"

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

            if frame_idx % 2 != 0:
                frame_idx += 1
                timestamp_ms += int(1000 / fps)
                continue

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB,
                data=frame_rgb
            )

            result = landmarker.detect_for_video(mp_image, timestamp_ms)

            if result.pose_landmarks:
                lms = result.pose_landmarks[0]

                pts = {}
                for i, lm in enumerate(lms):
                    vis = getattr(lm, "visibility", 1.0)
                    if vis < 0.3:
                        continue

                    x = lm.x * width
                    y = lm.y * height
                    pts[i] = (x, y)

                features = get_neck_rotation_features_mp(pts)

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

    if len(sequence) < 10:
        raise RuntimeError("추출된 sequence가 너무 짧습니다.")
    
    # 초반 안정화 구간 제거 (필수)
    warmup_skip = min(20, len(sequence) // 10)

    sequence = sequence[warmup_skip:]
    source_frame_indices = source_frame_indices[warmup_skip:]

    # neck_turn_angle(index=1) 기준으로 "활성 구간(start~end)" 추출
    turn_values = [abs(f[1]) for f in sequence]
    smooth_turn = moving_average(turn_values, window=7)
    arr = np.array(smooth_turn, dtype=np.float32)

    n = len(arr)
    if n < 10:
        raise RuntimeError("sequence가 너무 짧아서 구간을 추출할 수 없습니다.")

    # 초반/후반 중립 구간 기준값 추정
    head_n = min(20, max(5, n // 10))
    tail_n = min(20, max(5, n // 10))

    neutral_candidates = np.concatenate([
        arr[:head_n],
        arr[-tail_n:]
    ])
    neutral_baseline = float(np.median(neutral_candidates))

    peak_val = float(np.max(arr))
    peak_idx = int(np.argmax(arr))

    if peak_val < neutral_baseline + 8:
        raise RuntimeError(
            f"회전 변화가 너무 작습니다. baseline={neutral_baseline:.3f}, peak={peak_val:.3f}"
        )

    # 시작 threshold
    active_threshold = max(neutral_baseline + 12.0, peak_val * 0.35)

    # 시작 찾기: threshold 넘는 첫 안정 구간
    start_idx = None
    sustain = 6
    for i in range(0, n - sustain + 1):
        if np.all(arr[i:i+sustain] >= active_threshold):
            start_idx = i
            break

    if start_idx is None:
        raise RuntimeError(
            f"시작 구간을 찾지 못했습니다. threshold={active_threshold:.3f}"
        )

    # 왕복 1세트용:
    # neutral 구간을 2번 만나야 종료로 판단
    end_idx = None
    return_threshold = neutral_baseline + 4.0
    return_sustain = 8

    neutral_runs = []

    i = peak_idx + 1
    while i <= n - return_sustain:
        if np.all(arr[i:i+return_sustain] <= return_threshold):
            run_start = i
            j = i + return_sustain

            while j < n and arr[j] <= return_threshold:
                j += 1

            run_end = j - 1
            neutral_runs.append((run_start, run_end))
            i = j
        else:
            i += 1

    # 첫 번째 neutral = 가운데 정면
    # 두 번째 neutral = 마지막 정면
    if len(neutral_runs) >= 2:
        end_idx = neutral_runs[1][1]
    elif len(neutral_runs) == 1:
        end_idx = neutral_runs[0][1]
    else:
        end_idx = n - 1

    if end_idx <= start_idx:
        raise RuntimeError(
            f"구간이 비정상입니다. start_idx={start_idx}, peak_idx={peak_idx}, end_idx={end_idx}"
        )

    start_margin = 5
    end_margin = 5

    start_idx = max(0, start_idx - start_margin)
    end_idx = min(len(sequence) - 1, end_idx + end_margin)

    trimmed_sequence = sequence[start_idx:end_idx + 1]
    trimmed_source_frames = source_frame_indices[start_idx:end_idx + 1]

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