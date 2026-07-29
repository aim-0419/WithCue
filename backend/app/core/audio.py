# 운동 코칭 중 음성 안내(TTS) 파일을 비동기로 재생하는 오디오 모듈.
# ffplay를 사용해 백그라운드 스레드에서 mp3/wav 파일을 재생하며,
# TTS_ENABLED 환경변수로 음성 출력을 즉시 켜고 끌 수 있다.

import os
import threading
import subprocess

from app.core.config import settings

# TTS(음성 안내) 파일을 비동기로 재생하는 클래스.
# assets/tts 디렉터리에 있는 오디오 파일을 파일명만으로 간편하게 재생할 수 있다.
class TTSPlayer:
    # TTS 파일이 저장된 디렉터리 절대 경로를 설정한다.
    def __init__(self):
        # 프로젝트 구조에 맞춰 TTS 파일 절대 경로 설정
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_path = os.path.abspath(os.path.join(current_dir, "..", "assets", "tts"))

    # 지정한 오디오 파일을 백그라운드 스레드에서 즉시 재생하는 메서드.
    # TTS가 비활성화된 경우이거나 파일명이 비어있으면 아무 동작도 하지 않는다.
    # 매개변수: filename - assets/tts 디렉터리 기준 파일명(예: "start.mp3").
    def play(self, filename: str):
        """ 파일명만 받아서 즉시 비동기 실행 """
        # [조현석] 운동 로직은 유지한 채 음성 출력만 끌 수 있어야 하므로, 재생 직전에 환경설정으로 최종 차단합니다.
        if not settings.tts_enabled:
            return
        if not filename:
            return

        audio_path = os.path.join(self.base_path, filename)

        # 실제 ffplay 호출을 별도 스레드에서 실행하는 내부 함수.
        # ALSA 오디오 드라이버와 Jetson 하드웨어 장치를 직접 지정해 재생한다.
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

# 전역 인스턴스. 다른 모듈에서 from app.core.audio import tts_engine 으로 가져다 쓴다.
tts_engine = TTSPlayer()
