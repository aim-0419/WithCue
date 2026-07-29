# 카메라에서 왼쪽 어깨 외전 각도를 실시간으로 화면과 터미널에 출력하는 ROM 검증 스크립트.
# 사용법: python scripts/measure_shoulder_rom.py
# q 또는 ESC: 종료 / s: 현재 각도 터미널에 스냅샷 출력

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
import pyrealsense2 as rs

from app.services.ai_service import YOLODetector
from app.core.config import settings
from app.exercises.shared.posture import get_pose_angle

# 3D 변환이 필요한 COCO 인덱스
REQUIRED_IDXS = [5, 9, 11]  # L_shoulder, L_wrist, L_hip


def _build_keypoints_3d(kps_xy, depth_frame, intrinsics) -> dict:
    """YOLO 2D 픽셀 좌표 + RealSense depth → 앱과 동일한 keypoints dict 생성."""
    kps = {}
    for idx in range(min(17, len(kps_xy))):
        px, py = float(kps_xy[idx][0]), float(kps_xy[idx][1])
        if px == 0 and py == 0:
            continue

        # depth 프레임에서 z값 추출 (미터) — 범위 초과 좌표 건너뜀
        ix, iy = int(px), int(py)
        if depth_frame and 0 <= ix < depth_frame.width and 0 <= iy < depth_frame.height:
            z = depth_frame.get_distance(ix, iy)
        else:
            z = 0.0

        entry = {"x": px / 2.0, "y": py / 2.0, "z": z or None}

        # z가 유효하면 3D 미터 좌표 역투영
        if z and z > 0.1 and intrinsics:
            try:
                pt = rs.rs2_deproject_pixel_to_point(intrinsics, [px, py], z)
                entry["x_m"] = float(pt[0])
                entry["y_m"] = float(pt[1])
            except Exception:
                pass

        kps[idx] = entry
    return kps


def main():
    from datetime import datetime

    print("YOLO 로딩 중...")
    detector = YOLODetector(settings.yolo_model_path, device="cuda")

    print("RealSense 카메라 초기화 중...")
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.color, 1280, 720, rs.format.bgr8, 30)
    config.enable_stream(rs.stream.depth, 1280, 720, rs.format.z16, 30)
    profile = pipeline.start(config)
    align = rs.align(rs.stream.color)

    intrinsics = profile.get_stream(rs.stream.color).as_video_stream_profile().get_intrinsics()

    out_dir = Path(__file__).resolve().parent.parent / "app" / "public" / "metrics"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"shoulder_rom_{ts}.mp4"
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), 15, (1280, 720))

    print(f"녹화 시작 → {out_path}")
    print("Ctrl+C 로 종료")

    angle = None

    try:
        while True:
            frames = pipeline.wait_for_frames()
            aligned = align.process(frames)
            color_frame = aligned.get_color_frame()
            depth_frame = aligned.get_depth_frame()
            if not color_frame:
                continue

            frame = np.asanyarray(color_frame.get_data())
            result = detector.infer(frame)

            if result and result.keypoints is not None and len(result.keypoints.xy) > 0:
                kps_xy = result.keypoints.xy[0].cpu().numpy()
                keypoints = _build_keypoints_3d(kps_xy, depth_frame, intrinsics)

                raw = get_pose_angle("LEFT_SHOULDER_ABDUCTION", keypoints)
                if raw:
                    angle = float(raw)
                    print(f"\r각도: {angle:.1f}°  ", end="", flush=True)

                # 관절 시각화
                for idx in REQUIRED_IDXS:
                    if idx < len(kps_xy):
                        px, py = int(kps_xy[idx][0]), int(kps_xy[idx][1])
                        cv2.circle(frame, (px, py), 8, (0, 255, 0), -1)
                if all(i < len(kps_xy) for i in REQUIRED_IDXS):
                    pts = [(int(kps_xy[i][0]), int(kps_xy[i][1])) for i in REQUIRED_IDXS]
                    cv2.line(frame, pts[2], pts[0], (0, 200, 255), 2)  # hip → shoulder
                    cv2.line(frame, pts[0], pts[1], (0, 200, 255), 2)  # shoulder → wrist

            label = f"L Shoulder (3D): {angle:.1f} deg" if angle is not None else "L Shoulder (3D): --"
            cv2.putText(frame, label, (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 255, 255), 3)

            writer.write(frame)

    except KeyboardInterrupt:
        pass
    finally:
        pipeline.stop()
        writer.release()
        print(f"\n[저장 완료] {out_path}")


if __name__ == "__main__":
    main()
