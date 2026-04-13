# 정상 영상 읽어서 json저장하는 실행 스크립트
# 정상 영상 읽어서 json저장하는 실행 스크립트
import os
import json
import cv2
import mediapipe as mp

from app.services.dtw_feature_extractor import get_bird_dog_features_mp


def main():
    video_path = "./app/assets/bird_dog_normal.mp4"
    save_path = "./app/assets/reference/bird_dog_reference_mp.json"

    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"영상 열기 실패: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    fps = int(fps) if fps and fps > 0 else 30

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
    frame_idx = 0
    timestamp_ms = 0

    with PoseLandmarker.create_from_options(options) as landmarker:
        while True:
            ret, frame_bgr = cap.read()
            if not ret:
                break

            # 3프레임 중 1프레임만 사용
            if frame_idx % 3 != 0:
                frame_idx += 1
                timestamp_ms += 1
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

                    x = lm.x * width
                    y = lm.y * height
                    pts[i] = (x, y)

                # ✅ 한 프레임에서 landmarks 다 모은 뒤 1번만 계산
                features = get_bird_dog_features_mp(pts)
                if features is not None:
                    current = tuple(round(v, 3) for v in features)
                    prev = tuple(round(v, 3) for v in sequence[-1]) if sequence else None

                    # ✅ 직전 값과 다를 때만 저장
                    if current != prev:
                        sequence.append(features)

            frame_idx += 1
            timestamp_ms += 1

    cap.release()

    if len(sequence) == 0:
        raise RuntimeError("유효한 feature가 하나도 추출되지 않았습니다.")

    payload = {
        "exercise": "BIRD_DOG",
        "fps": fps,
        "window_frames": min(30, len(sequence)),
        "sequence": sequence,
    }

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[완료] 저장 경로: {save_path}")
    print(f"[완료] sequence 길이: {len(sequence)}")


if __name__ == "__main__":
    main()