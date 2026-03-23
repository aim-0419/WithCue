import os
import threading
import subprocess

from app.core.config import settings

class TTSPlayer:
    def __init__(self):
        # 프로젝트 구조에 맞춰 TTS 파일 절대 경로 설정
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_path = os.path.abspath(os.path.join(current_dir, "..", "assets", "tts"))
        
    def play(self, filename: str):
        """ 파일명만 받아서 즉시 비동기 실행 """
        # [조현석] 운동 로직은 유지한 채 음성 출력만 끌 수 있어야 하므로, 재생 직전에 환경설정으로 최종 차단합니다.
        if not settings.tts_enabled:
            return
        if not filename:
            return
        
        audio_path = os.path.join(self.base_path, filename)
        
        def _run():
            if os.path.exists(audio_path):
                try:
                    env = os.environ.copy()
                    env["SDL_AUDIODRIVER"] = "alsa"
                    env["AUDIODEV"] = "hw:0,3"
                    
                    if "SDG_RUNTIME_DIR" not in env:
                        env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
                    
                    subprocess.run([
                        "ffplay", "-nodisp", "-autoexit", "-hide_banner", audio_path
                    ], env=env)
                except Exception as e:
                    print(f"[Audio Core Error] {e}")
            else:
                print(f"[Audio Core Error] 파일을 찾을 수 없음: {audio_path}")
        
        threading.Thread(target=_run, daemon=True).start()
            
# 전역 인스턴스
tts_engine = TTSPlayer()
