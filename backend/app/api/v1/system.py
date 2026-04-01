from fastapi import APIRouter
from app.hardware.scanner import HardwareScanner

router = APIRouter()

@router.get("/health")
def health_check():
    # 서버 프로세스가 살아있기만 하면 OK
    return {
        "status": "ok"
    }

@router.get("/status")
def check_system_status():
    # 1. 카메라 uSB 연결 확인
    cam_status = HardwareScanner.check_camera()
    
    # 2. 오디오 장치 확인
    audio_status = HardwareScanner.check_audio()
    
    # 3. 결과 반환
    return {
        "system_status": {
            "camera": cam_status,
            "audio": audio_status
        }
    }