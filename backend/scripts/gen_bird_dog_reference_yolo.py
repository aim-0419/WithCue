# 버드독 정상 영상에서 DTW 레퍼런스 JSON 생성
import os
import json
import cv2
from ultralytics import YOLO

from app.exercises.bird_dog.features import get_bird_dog_features_yolo


def main():
    video_path = "./app/assets/bird_dog_test.mp4"
    save_path = "./app/assets/reference/bird_dog_reference_yolo.json"
    model_path = "./app/assets/models/yolov8s-pose.pt"

    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"영상 열기 실패: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    fps = int(fps) if fps and fps > 0 else 30

    model = YOLO(model_path)
    model.to("cpu")

    sequence = []
    frame_idx = 0

    while True:
        ret, frame_bgr = cap.read()
        if not ret:
            break

        if frame_idx % 3 != 0:
            frame_idx += 1
            continue

        results = model(frame_bgr, verbose=False)
        if not results:
            frame_idx += 1
            continue

        r = results[0]
        if r.keypoints is None or r.keypoints.xy is None:
            frame_idx += 1
            continue

        xy = r.keypoints.xy
        conf = r.keypoints.conf

        if len(xy) == 0:
            frame_idx += 1
            continue

        pts = {}

        for i, p in enumerate(xy[0].cpu().numpy()):
            c = float(conf[0][i].cpu().numpy()) if conf is not None else 1.0
            if c < 0.3:
                continue

            pts[i] = (float(p[0]), float(p[1]))

        features = get_bird_dog_features_yolo(pts)

        if features is not None:
            current = tuple(round(v, 3) for v in features)
            prev = tuple(round(v, 3) for v in sequence[-1]) if sequence else None

            if current != prev:
                sequence.append(features)

        frame_idx += 1

    cap.release()

    if len(sequence) == 0:
        raise RuntimeError("유효한 feature가 하나도 추출되지 않았습니다.")

    payload = {
        "exercise": "BIRD_DOG",
        "pose_backend": "yolo",
        "model": model_path,
        "fps": fps,
        "sample_every_n": 3,
        "window_frames": min(30, len(sequence)),
        "sequence": sequence,
    }

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[완료] 저장 경로: {save_path}")
    print(f"[완료] sequence 길이: {len(sequence)}")


if __name__ == "__main__":
    main()