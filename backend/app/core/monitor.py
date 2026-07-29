# 카메라 프레임 수신 상태와 오디오 장치 연결 상태를 실시간으로 점검하는 모니터 모듈.
# 운동 코칭 세션 중 하드웨어 이상(카메라 끊김·프리징, 오디오 미감지)을 빠르게 탐지한다.

import time
import numpy as np
import os

# 카메라와 오디오 장치의 현재 상태를 주기적으로 점검하는 시스템 모니터 클래스.
class SystemMonitor:
    # 마지막 프레임 수신 시각을 현재 시각으로 초기화한다.
    def __init__(self):
        self.last_frame_time = time.time()

    # 카메라 프레임 수신 상태와 오디오 장치 존재 여부를 확인해 상태 딕셔너리를 반환하는 메서드.
    # 매개변수: frame - 카메라에서 받은 이미지 프레임(numpy 배열). None이면 카메라 연결 끊김으로 판단.
    # 반환값: {"camera": "ok"/"warn"/"bad", "audio": "ok"/"bad"} 딕셔너리.
    def check_status(self, frame: np.ndarray):
        """
        카메라와 오디오 상태만 체크하여 반환
        """
        current_time = time.time()

        # 1. 카메라 상태
        camera_status = "ok"

        if frame is None:
            # 아예 프레임이 안들어옴 (연결 끊김)
            camera_status = "bad"
        else:
            # 프레임은 오는데, 0.5초 이상 멈춰있음 (프리징/렉)
            if current_time - self.last_frame_time > 0.5:
                camera_status = "warn"

            self.last_frame_time = current_time

        # 2. 오디오 상태
        audio_status = "bad"
        try:
            if os.path.exists("/proc/asound/cards"):
                with open("/proc/asound/cards", "r") as f:
                    content = f.read().lower()
                    valid_keywords = ["tegra", "nvidia", "hdmi", "usb", "device"]

                    if any(keyword in content for keyword in valid_keywords):
                        audio_status = "ok"
            else:
                print("[Monitor] Audio card file not found.")
        except Exception as e:
            print(f"[Monitor] Audio check error: {e}")

        return {
            "camera": camera_status,
            "audio": audio_status
        }
