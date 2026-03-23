import pyrealsense2 as rs
import os

class HardwareScanner:
    @staticmethod
    def check_camera():
        """
        영상을 켜지 않고, RealSense 기기가 USB에 꽂혀 있는지만 확인
        """
        try:
            ctx = rs.context()
            devices = ctx.query_devices()
            # 장치 목록 개수가 0보다 크면 연결된 것
            if len(devices) > 0:
                return "ok"
            else:
                return "bad"
        except Exception as e:
            print(f"Camera Scan Error: {e}")
            return "bad"
    
    @staticmethod
    def check_audio():
        """
        리눅스 사운드 카드가 잡히는지 확인
        """
        try:
            # 리눅스 명령어 aplay -l로 사운드 카드 목록 확인
            if os.path.exists("/proc/asound/cards"):
                with open("/proc/asound/cards", "r") as f:
                    content = f.read()
                    if "no soundcards" not in content and len(content.strip()) > 0:
                        return "ok"
            return "bad"
        except:
            return "ok"
        