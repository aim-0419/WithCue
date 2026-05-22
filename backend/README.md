# README
이 문서는 backend 디렉노피의 전체 구조와 각 모듈의 역할, 함수/클래스 목록, 의존 관계, 실행 흐름 및 실행 방법을 정리합니다. 코드에 명시된 내용만을 문서화하며, 추측 정보는 포함되지 않습니다.

---
## 목차
- 프로젝트 구조 개요
- 모듈별 요약 (파일별 클래스/함수, 시그니처, 책임, 실행 흐름)
- 의존성 및 임포트 매핑
- 실행 및 요청 처리 흐름
- 아키텍처 패턴 요약
- 환경 및 설정
- 실행 방법

---
## Project Structure Overview
backend 루트의 계층 트리(중요 코드/파일 중심):

backend/
├─ requirements.txt
├─ test_client.html
├─ test_measure.py
├─ check_structure.py
└─ app/
   ├─ main.py
   ├─ check_ws.py
   ├─ api/
   │  └─ v1/
   │     ├─ api.py
   │     └─ system.py
   ├─ assets/
   │  └─ models/
   │     ├─ yolov8s-pose.pt
   │     └─ yolo11n-pose.pt
   ├─ core/
   │  ├─ audio.py
   │  ├─ database.py
   │  ├─ geometry.py
   │  ├─ monitor.py
   │  ├─ store.py
   │  ├─ types.py
   │  └─ utils.py
   ├─ hardware/
   │  ├─ camera.py
   │  └─ scanner.py
   └─ services/
      ├─ ai_service.py
      ├─ motion_service.py
      ├─ processors.py
      └─ rules/
         ├─ feedback.py
         └─ posture.py

간단한 목적 요약:
- main.py   : FastAPI 앱 초기화 및 수명(lifespan)관리(모델로드, 종료 시 리소스 해제).
- api.py    : 웹소켓 엔드포인트 __측정(ws/measure)과 코칭(ws/coach/{exercise}).
- system.py : 시스템 상태(health/status) 확인 API
- services/ : 도메인 서비스(모션 서비스, AI 래퍼, 처리기 등)
    - ai_services.py : YOLO 모델 래퍼(YOLODetector).
    - motion_services.py : WebSocket 기반 스트리밍 서비스(MotionService) __ 카메라, 추론, 프로세서 연동.
    - processors.py : 측정/코칭 로직(MeasurementProcessor, CoachingProcessor, BaseProcessor) 및 공통 처리
    - rules/ : 코칭 및 피드백 관련 로직(FeedbackManager, posture.get_pose_angle).
- hardware/ : 파드웨어 접근 추상화(RealSense 카메라 등).
- core/ : 공통 유틸리티(geometry, audio, monitor, DB, 임시 세션 스토어 등).
- 루트 파일들: 테스트 클라이언트와 간단한 테스트 스크립트

---
## Module-Level Documentation
아래는 각 Python ㅣ모듈에 정의된 클래스/함수 목록과 시그니처, 핵심 책임 등 실행 흐름 요약임. (매 항목은 코드에 직접 존재하는 내용을 근거로 기술합니다.)

### check_structure.py
- 함수
    - print_tree(startpath)
        - 파라미터 : startpath (str)
        - 반환 : 없음
        - 책임 : 지정한 경로를 트리 형태로 출력(일부 확장자나/디렉토리 무시).
        - 실행흐름 : os.walk 순회, 무시 목록 필터링 하여 트리 출력.
- 실행 : 파일이 메인으로 실행되면 print_tree('.') 호출.

### requirements.txt
- 런타임/빌드 의존성 목록(텍스트), 주요 항목 : fastapi, uvicorn, numpy, opencv-python, ultralytics, pyrealsense2, websockets, jinja2, python-multipart, torch, torchvision.

### test_client.html
- 목적 : WebSocket 클라이언트(브라우저)로 테스트 스트리밍/데이터 확인용 UI(프론트 개발, 테스트용)

### test_measure.py
- 스크립트 : get_pose_angle, calculate_angle 등을 독립적으로 테스트하는 콘솔 스크립트

---
### main.py
- 외부/내부 입포트 : uvicorn, torch, FastAPI, CORSMiddleware, FileResponse, app.api.v1.api.router, app.services.ai_service.YOLODetector, app.hardware.camera.camera_manager
- 비동기 수명 관리 : lifespan(app: FastAPI) (asynccontextmanager)
    - Startup : YOLO 모델 로드(YOLODetector(moel_path)) 및 warmup() 호출
    - Shutdown : 카메라 자원 해제(camera_manager.stop()), 모델 삭제 및 CUDA 캐시 비움(조건부).
- 라우터 등록 : 
    - /api/v1 -> api_router 웹소켓 엔드포인트 포함
- 단순 라우트 :
    - read_root() : 상태 JSON 반환.
    - get_test_page() : 
        test_client.html 파일 반환(존재시).
- 책임 : 서버 진입점, 모델 선로딩(앱.state에 모델),라우터 결합, 수명관리

---
### api.py
- 임포트 : APIRouter, WebSocket, Query, Optional, MotionService, MeasurementProcessor, CoachingProcessor.
- 라우트 :
    - @router.websocket("/ws/measure")
        - 시그니처 : async def measure_endpoint(websocket: WebSocket, parts: Optional[str]=Query(None))
        - 책임 : WebSocket 연결 수립 -> MotionService 인스턴스 생성(웹소켓, websocket.app.state.yolo_model) -> MeasurementProcessor 생성(요청된 parts 기반 스케줄) -> service.set_processor(processor) 후 await service.start().
        - 처리 : parts 파라미터로 원하는 부위 매핑(PART_MAPPING). 기본값 없으면 target_list=None 으로 두어 프로세서의 기본 스케줄 사용.
    - @router.websocket("/ws/coach/{exercise})
        - 시그니처 : async def coach_endpoint(websocket: WebSocket, exercise: str)
        - 책임 : WebSocket 연결 수립 -> MotionService 생성 -> CoachingProcessor(exercise_name=exercise) 설정 -> await service.start().

---
### system.py
- 임포트 : APIRouter, HardwareScanner
- 엔드 포인트 : 
    - health_check() : 간단한 {"status": "ok"} 반환.
    - check_system_status() : HardwareScanner.check_camera() 및 HardwareScanner.check_audio() 호출하여 system_status 반환.

---
### audio.py
- 클래스 : TTSPlayer
    - __init__(self) : assets/tts 디렉토리 경로 설정
    - play(self, filename: str) : 파일명으로 비동기(데몬 스레드)로 ffplay 실행.
        - 내부 : 환경 변수 세팅 (SDL_AUDIODRIVER, AUDIODEV, XDG_RUNTIME_DIR 보정), subprocess.run(["ffplay", ...]).
- 전역 인스턴스 : tts_engine = TTSPlayer()
- 책임 : 로컬 TTS 오디오 재생 호출(파일 기반).

---
### database.py
- SQLAlchemy 설정 : 
    - SQLALCHEMY_DATABASE_URL = "sqlite:///./withcue.db"
    - engine = create_engine(..., connect_args={"check_same_thread": False})
    - SessionLocal = sessionmaker(...)
    - Base = declarative_base()
- 모델 :
    - class User(Base) : id, username, hashed_password 컬럼 정의.
- 책임 : 간단한 SQLite ORM 설정 및 User 모델 정의.

---
### geometry.py
- 함수 : 
    - _get_coordse(p) -> tuple : 다양한 포맷(dict/list/None) 에서 좌표 추출.
    - calculate_angle(p1, p2, p3) -> float : 2D 각도(0~180) 계산.
    - calculate_distance(p1, p2) -> float : 유클리드 거리.
    - get_midpoint(p1, p2) -> dict : 중점 반환.
    - calculate_3d_angle(p1, p2, p3) -> float : 3D 각도 계산 (z 포함).
    - _get_coords_3d(p) -> tuple : 3D 좌표 추출.
    - calculate_angle_2d(p1, center, p2) -> float : 2D 각도 계산 (특정 구현).
- 책임 : 좌표 변환 및 각도/거리 계산 유틸리티.
- 실행 흐름 : 점 입력을 받아 수학적 계산(벡터, 내적, acos) 수행.

---
### monitor.py
- 클래스 : SystemMonitor
    - __init__(self) : last_frame_time 초기화.
    - check_status(self, frame: np.ndarray) -> dict : 카메라(프레임 존재 및 프리징 검사) 및 오디오(cards 파일 검사) 상태를 판단하여 {"camera": "...", "audio": "..."} 반환.
- 책임 : 간단한 시스템 상태 점검(프레임 수신 유무, 오디오 장치 유무).

---
### store.py
- @dataclass UserSessionData : 
    - 속성 : max_rom(int), pain_angle, init_shoulder_y, active_side, success_count, bad_form_count.
- 전역 SESSION_STORE : Dict[str, UserSessionData]
- 함수 :
    - get_session(exercise_name: str) -> UserSessionData
    - update_calibration(exercise_name: str, shoulder_y: float, side: str) : 세션에 캘리브레이션 저장.
    - log_result(exercise_name: str, is_success: bool) : 성공/실패 카운트 기록
- 책임 : 런타임 메모리 기반 세션 저장소(영구 DB 아님).

참고: types.py에 from dataclasses import dataclass, failed 와 같이 존재하는 부분이 있으나, 이는 코드 그대로 문서에 반영함.

---
### types.py
- 함수 :
    - extract_keypoints(result) -> dict : YOLO result 에서 keypoints를 540x960 픽셀 기준 딕셔너리로 반환.
    - extract_2d_center(result) : 가장 큰 바운딩 박스 중심 반환.
- 클래스 :
    - AngleSmoother
        - __init__(self, alpha=0.5) : EMA 필터 초기화.
        - smooth(self, current_angle) : 현재 각도 입력에 대한 EMA 스무딩 반환(정수).
- 책임 : YOLO 결과 파싱 + 각도 스무딩.

---
### utils.py
- 임포트: numpy 등
- 함수/클래스 :
    - CameraManager 는 hardware/camera에 있으므로 여긴 유틸리티 함수들 중심.
    - (코드기준) types.py와 유사한 유틸리티가 존재함

---
### camera.py
- 클래스 : CameraManager
    - 속성 : pipeline, config, active, intrinsics
    - 메서드 : 
        - start(self) : RealSense 파이프라인 초기화 및 스트림 시작, intrinsics 저장.
        - stop(self) : 파이프라인 정지 및 상태 초기화.
        - get_frame(self) -> (color_image, depth_frame, intrinsics) : 프레임 수집, numpy로 변환(타임아웃 처리).
        - get_3d_point(self, u, v, depth_frame, intrinsics) -> 3D 좌표 또는 None : 픽셀 좌표에서 깊이 확인, 주변 탐색, rs2_deproject_pixel_to_point 호출.
        - update_keypoints_3d(self, keypoints, depth_frame, intrinsics) -> keypoints : 각 키포인트에 x_m, y_m, z 필드 추가(가능한 경우).
- 전역 싱글톤 : camera_manager = CameraManager()
- 책임 : RealSense 관련 하드웨어 제어 및 2D -> 3D 변환.

---
### scanner.py
- 클래스 : HardwareScanner
    - 정적메서드 :
        - check_camera() -> "ok"/"bad" : rs.context().query_devices()로 연결 여부 확인.
        - check_audio() -> "ok"/"bad" : cards 파일 존재 및 내용으로 판단.
- 책임 : 장치 연결(하드웨어) 검사용 유틸리티.

---
### ai_service.py
- 클래스 : YOLODetector
    - __init__(self, model_path: str, device="cuda") : ultralytics.YOLO(model_path) 로드, CUDA 사용 시 모델을 CUDA로 이동.
    - warmup(self) : 더미 프레임으로 한 번 추론하여 메모리 선점.
    - infer(self, frame: np.ndarray, conf: float = 0.5) -> YOLO 결과 객체 : self.model.predict(...) 호출.(@torch.no_grad() 어노테이션 적용)
- 책임 : YOLO 모델 로드 및 추론 래퍼.

---
### motion_service.py
- 클래스 : MotionService
    - __init__(self, ws:WebSocket, yolo) : 웹소켓과 YOLO 인스턴스 주입, monitor 객체 생성.
    - set_processor(self, processor: BaseProcoessor) : 동작 처리기 설정.
    - start(self) (async) : WebSocket 수락 -> 카메라 시작 -> 루프에서 프레임을 가져와 YOLO 추론(스레드풀에서 실행) -> extract_keypoints -> processor.process(...) 호출 -> 모니터 점검 -> 패킷 인코딩 및 ws.send_json
    - _send_packet(self, frame, data) (async) : 프레임을 JPEG Base64로 인코딩하고 JSON으로 전송.
- 책임 : WebSocket 연결의 실제 스트리밍 루프, 추론 및 처리기 연계, 전송.
- 실행 흐름 : 
    - start()는 비동기 루프로 동작. 내부에서 loop.run_in_executor로 CPU/GPU 바운드 추론을 오프로드.

---
### processors.py
- 임포트 : AngleSmoother, FeedbackManager, get_pose_angle, camera_manager, tts_engine.
- 클래스 : 
    - BaseProcessor(ABC) : process(...) 추상 메서드 선언.
    - MeasurementProcessor(BaseProcessor) :
        - 생성자 인자 : target_schedcule: List[str] = None
        - 주요 속성 : schedule, current_idx, state (PREPARE/MEASURE/HOLD 등), PREPARE_DURATION, MEASURE_DURATION, max_angle, best_frame, smoother, tts_assets, played_audio.
        - 메서드 : process(self, keypoints, frame, depth_frame=None, intrinsics=None) -> dict
            - 책임 : 측정 단계 관리(준비 -> 측정 -> 유지 -> 완료), 각도계산(get_pose_angle), 베스트샷 캡처, TTS 재생 호출, next_stage()로 다음 스테이지 전환.
        - 보조 : _complete_stage() -> 결과 패키징 및 next_stage() 호출.
    - CoachingProcessor(BaseProcessor) :
        - 생성자 인자 : exercise_name: str, limit_angle: int = 45
        - 주요 속성 : exercise_name, limit_angle, smoother, last_feedback_time, feedback_interval, init_shoulder_y, active_side, tts_assets.
        - 메서드 : _play_coaching(key) (내부 TTS 제어), process(keypoints, frame, depth_frame=None, intrinsics=None) -> dict
            - 책임 : 코칭 모드의 각도 계산, 좌/우 자동 탐지, 피드백 메시지 생성 및 (간단한)TTS 로직 트리거
- 책임 : 측정/코칭 도메인 로직 구현.

---
### feedback.py
- 클래스 : FeedbackManager
    - 속성 : last_feedback_time, cooldown, prev_angle.
    - 메서드 :
        - get_feedback(self, exercise_name: str, keypoints: Dict, current_angle: float, personal_limit: float = None) -> Optional[str]
            - 책임 : 주기적 쿨다운 확인, 안전 검사(팔꿈치 플레어/숄더 슈러그 등), 가동 범위 성과 코칭 메시지 결정.
        - 내부 : _is_elbow_flaring(kp), _is_shrugging(kp) : 헬스 체크 로직.
- 책임 : 피드백 문구 및 타이밍 제어

---
### posture.py
- 함수/유틸 : 
    - get_kpt(keypoints, idx) -> Any : 안전하게 인덱스 키포인트 반환.
    - is_all_joints_visible(keypoints, required_joints) -> bool
    - to_coords(point) -> list : 2D/3D 포맷 정리
    - auto_calc(p1_raw, p2_raw, p3_raw) -> float : 2D/3D 자동 선택 후 각도 계산
    - get_pose_angle(stage_name: str, keypoints: Dict) -> float :
        - 책임 : 다양한 운동 단계(SHOULDER_ABDUCTION, SIDE_LEG_RAISE, LEFT_KNEE_FLEXION, RIGHT_KNEE_FLEXION, SHOULDER_EXTERNAL_ROTATION 등)에 대한 각도 계산 로직을 통합 제공.
        - 실행 흐름 : 입력 키포인트의 가시성 검사 -> 적절한 좌표 선택 -> calculate_angle / calculate_3d_angle / calculate_angle_2d 호출 -> 각도 반환.

---
## Dependency & Import Mapping
아래는 모듈 간 주요 내부 임포트와 외부 라이브러리 의존 관계임.
- 핵심 외부 라이브러리(요약) :
    - FastAPI/uvicorn (fastapi, uvicorn)
    - PyTorch / Ultralytics YOLO (torch, ultralytics)
    - RealSense SDK (pyrealsense2)
    - OpenCV (cv2 / opencv-python)
    - NumPy (numpy)
    - SQLAlchemy (sqlalchemy)
    - websockets (클라이언트 테스트)
    - ffplay (외부 바이너리, audio.py에서 subprocess로 호출)
- 주요 내부 임포트 (모듈 간 관계) :
    - main.py ->
        app.api.v1.api.router,
        app.api.v1.system.router,
        app.services.ai_service.YOLODetector,
        app.hardware.camera.camera_manager
    - api.py ->
        app.services.motion_service.MotionService,
        app.services.processors.MeasurementProcessor,
        CoachingProcessor
    - motion_service.py ->
        app.hardware.camera.camera_mananger,
        app.core.monitor.SystemMonitor,
        app.core.utils.extract_keypoints,
        processor.process
    - processors.py ->
        app.core.utils.AngleSmoother,
        app.services.rules.feedback.FeedbackManager,
        app.services.rules.posture.get_pose_angle, camera_manager, tts_ingine
    - ai_service.py ->
        ultralytics.YOLO, torch
    - camera.py ->
        pyrealsense2 as rs, numpy
    - system.py ->
        app.hardware.scanner.HardwareScanner
    - database.py ->
        sqlalchemy 관련 모듈
    - store.py ->
        런타임 세션 저장(독립적)
의존성 흐름(대표) :
API -> MotionService -> Processor(Measurement/Coaching) -> Rules(Feedback/Posture) -> Core(Hardware, Geometry, Audio)
또는 요약하면 : API -> Service -> Processor -> Rules/Utils -> Hardware/IO

---
## Execution Flow Dexcription
애플리케이션 시작
- 진입점 : main.py에서 FastAPI 앱이 생성되고 lifespan 컨텍스트 관리자에 의해 Startup/Shutdown 작업이 관리됨.
- Startup 시 :
    - YOLODetector(model_path) 생성으로 모델을 로드하고 warmup() 호출하여 추론 관련 메모리를 확보함.
    - app.state.yolo_model에 모델 인스턴스 저장.
- Shutdown 시 : 
    - camera_manager.stop() 호출로 카메라를 안전하게 종료.
    - app.state.yolo_model 삭제 및 CUDA 캐시 비움.

요청(웹소켓) 라이프사이클 (측정/코칭)
    1. 클라이언트가 ws://.../api/v1/ws/measure 또는 ws://.../api/v1/ws/coach/{exercise}로 WebSocket 연결을 시도함(api.py).
    2. 각 엔드포인트는 MotionService(websocket, websocket.app.state.yolo_model)를 생성하고 적절한 Processor를 set_processor 함.
    3. MotionService.start()(비동기)
        - ws.accept() 후 카메라(camera_manager.start()) 시작.
        - 카메라 intrinsics 준비될 때까지 대기.
        - 루프 :
            - camera_manager.get_frame()으로 컬러프레임과 depth_frame 획득.
            - 스레드풀(loop.run_in_executor)에서 yolo.infer(frame_rgb) 호출(동기형 YOLO 래퍼를 비동기에서 실행).
            - 추출된 YOLO 결과를 extract_keypoints(result)로 변환.
            - processor.process(keypoints, frame, depth_frame, intrinsics)를 호출하여 도메인 로직 실행.
            - 시스템 모니터 (SystemMonitor.check_status)로 상태 검사.
            - _send_packet로 프레임(1280x720으로 리사이즈된 JPEG base64) 및 데이터 JSON 전송.
        - 연결 끊김 또는 에러 시 종료 루틴 (카메라 stop 등) 실행.
- 비동기 사용 : FastAPI의 비동기 엔드포인트와 asyncio.get_running_loop().run_in_executor를 병행하여 CPu/GPU 바운드 추론을 블로킹 없이 수행.

---
## Key Architectural Patterns
프로젝트에서 관찰되는 주요 패턴 :
- Layered / Service-oriented :
    - API 레이어 (api/*.py) -> 서비스 레이어(motion_Service.py, ai_service.py) -> 처리기/비즈니스 로직(processors.py, rules/) -> 하드웨어/유틸(core, hardware)
- 책임 분리 :
    - 하드웨어 접근 (hardware/*)과 비즈니스 로직(services/*)이 분리되어 있으며, 공통 유틸(geometry, monitor, audio)은 core/에 모여 있음.
- Processor 패턴 : BaseProcessor를 ㅌ오해 측정과 코칭의 공통 인터페이스(process)를 정의하고, 구체 구현 (Measurement/Coaching)이 이를 구현.
- 단일 인스턴스/싱글톤 사용 : camera_manager와 tts_engine같은 전역 인스턴스 사용으로 리소스 관리.

---
## Environment & Configuration
코드에서 직접 참조되는 환경, 외부요소 :
- 의존성 : requirements.txt에 명시된 패키지 참조.
- 하드웨어/시스템 : 
    - RealSense SDK : pyrealsense2(카메라 연결 및 3D 포인트 계산).
    - GPU(CUDA) : main.py에서 torch.cuda.is_available() 체크 후 일부 설정 변경.
    - 오디오 재생 : 시스템에 ffplay(FFmpeg) 바이너리 필요(audio.py에서 호출).
    - SQLite DB : database.py는 sqlite:///./withcue.db 연결 문자열 사용.
- 환경 변수(코드에서 사용) : 
    - audio.py에서 SDL_AUDIODRIVER, AUDIODEV, XDG_RUNTIME_DIR/XDG_RUNTIME_DIR보정(사용자 ID 기반) 등을 설정.
- 설정 로딩 : 별도의 구성 파일/환경 변수 로더(예: pydantic 설정)는 없음 __ 설정은 코드에 하드코딩되어 있음(예: 모델 경로 "app/assets/models/yolov8s-pose.py", DB URL 등).

---
## How to Run
아래는 코드 기반으로 직접 실행 가능한 최소 단계. (코드에 정의된 경로/명령을 따른 예시).

1. python 가상환경(권장)
python -m venv .venv
source .venv/bin/activate

2. 의존성 설치
pip install -r backend/requirements.txt

3. (하드웨어 전체) RealSense 장치 및 오디오 환경 준비
    - pyrealsense2가 필요하며, 시스템에 맞는 설치가 필요함.
    - 오디오 재생은 ffplay(FFmpeg)가 필요함.

4. 서버 실행(개발/테스트)
uvicorn app.main:app --host 0.0.0.0 --port 8018 --reoad

- app.main의 lifespan에서 YOLO 모델을 앱 시작 시 로드합니다. 모델 파일 경로는 main.py에서 "app/assets/models/yolov8s-pose.py"로 지정되어 있음.

5. 테스트 클라이언트 열기
    - 브라우저로 http://localhost:8018/test 접근 -> test_client.html이 반환되면 UI 통해 WebSocket 테스트 가능.
    - 직접 WebSocket 연결 예: ws://localhost:8018/api/v1/ws/measure 또는 ws://localhost:8018/api/v1/ws/coach/<exercise>.

개발 vs 프로덕션 : 
- 코드에는 uvicorn 실행 방식만 명시 되어 있지 않으며, main.py는 앱 수명 주기에서 모델을 선로드함. 프로덕션에서는 프로세스 관리 및 GPU/메모리 고려(복수 프로세스/워크로드 등)를 별도로 설계해야 함.

---
## 기타 참고 사항(코드 기반)
- 세션/임시 저장 : store.py는 메모리 기반 세션 저장소(영구 저장소 아님).
- DB 모델 : database.py에 기본 User 모델 정의가 있으나, 어플리케이션 내 다른 코드에서 사용되는 흔적은 제한적임.
- TTS : audio.py는 로컬 파일 기반 재생을 수행하며, 실제 TTS 생성은 포함되어 있지 않음.(파일명으로 재생).
- 예외/로킹 : 여러 곳에서 print() 기반 로그/디버그 출력 사용. 상세 로깅 구성은 별도 구현 필요.

---
## 결론 및 다음 권장 작업 (옵션)
- 문서화 완료 : 현재 코드베이스의 구조와 함구/클래스별 책임을 문서화.
- 다음으로 권장되는 작업 :
    - requirements.txt에 Python 최소 버전 추가 또는 pyproject.toml 구성.
    - 프로덕션 배포용 설정(로그, 프로세스 관리, GPU 리소스 관리) 추가.
    - store.py를 DB-backend 저장으로 전환.
    - 코드 품질 : types.py 및 일부 오타 점검.
     