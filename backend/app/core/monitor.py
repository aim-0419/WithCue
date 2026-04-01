import time
import numpy as np
import os

class SystemMonitor:
    def __init__(self):
        self.last_frame_time = time.time()
        
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