# RealSense 카메라가 지원하는 스트림 해상도/FPS를 조회하고 목표 설정이 가능한지 확인하는 스크립트.

import pyrealsense2 as rs

TARGET_CONFIGS = [
    ("color",  rs.stream.color, rs.format.bgr8,  1280, 720, 30),
    ("color",  rs.stream.color, rs.format.bgr8,   848, 480, 30),
    ("depth",  rs.stream.depth, rs.format.z16,   1280, 720, 30),
    ("depth",  rs.stream.depth, rs.format.z16,    848, 480, 30),
]

def main():
    ctx = rs.context()
    devices = ctx.query_devices()
    if len(devices) == 0:
        print("카메라가 연결되어 있지 않습니다.")
        return

    dev = devices[0]
    print(f"장치: {dev.get_info(rs.camera_info.name)}")
    print(f"S/N : {dev.get_info(rs.camera_info.serial_number)}")
    print(f"FW  : {dev.get_info(rs.camera_info.firmware_version)}")
    print()

    # 지원 프로파일 수집
    supported = set()
    for sensor in dev.query_sensors():
        for profile in sensor.get_stream_profiles():
            vp = profile.as_video_stream_profile()
            supported.add((
                profile.stream_type(),
                profile.format(),
                vp.width(),
                vp.height(),
                vp.fps(),
            ))

    # 목표 설정 검증
    print("── 목표 설정 지원 여부 ──────────────────────")
    for label, stream_type, fmt, w, h, fps in TARGET_CONFIGS:
        key = (stream_type, fmt, w, h, fps)
        ok = key in supported
        mark = "✅" if ok else "❌"
        print(f"  {mark}  {label:6s} {w}×{h} @ {fps}fps")

    print()

    # 실제 스트림 개통 테스트
    print("── 1280×720 실제 스트림 개통 테스트 ─────────")
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.color, 1280, 720, rs.format.bgr8, 30)
    config.enable_stream(rs.stream.depth, 1280, 720, rs.format.z16, 30)
    try:
        profile = pipeline.start(config)
        c = profile.get_stream(rs.stream.color).as_video_stream_profile()
        d = profile.get_stream(rs.stream.depth).as_video_stream_profile()
        print(f"  Color: {c.width()}×{c.height()} @ {c.fps()}fps  ✅")
        print(f"  Depth: {d.width()}×{d.height()} @ {d.fps()}fps  ✅")
        pipeline.stop()
        print()
        print("  → 1280×720 30fps 설정 사용 가능합니다.")
    except Exception as e:
        print(f"  실패: {e}")
        print()
        print("  → 848×480으로 폴백을 권장합니다.")

if __name__ == "__main__":
    main()
