# Withcue Backend

FastAPI 기반 재활 운동 코칭 서버. MediaPipe / YOLO 포즈 추정 + DTW 유사도 점수 + WebSocket 실시간 스트리밍.

---

## 디렉토리 구조

```
backend/
├── app/
│   ├── main.py
│   ├── api/
│   ├── core/
│   ├── exercises/
│   ├── hardware/
│   ├── schemas/
│   ├── services/
│   └── assets/
│
└── scripts/
```

---

## 폴더 및 파일 설명

### `app/main.py`
FastAPI 앱 진입점. lifespan(시작/종료 훅), CORS 설정, 라우터 등록, YOLO 모델 초기화.

---

### `app/api/`
**역할:** HTTP REST + WebSocket 라우터 레이어. 입력 파싱과 오류 응답만 담당하고, 실제 로직은 services/로 위임.

| 파일 | 주요 내용 |
|---|---|
| `v1/api.py` | WebSocket 엔드포인트 3개 (`ws/measure`, `ws/coach/{exercise}`, `ws/dtw/{exercise}`), 운동 카탈로그 REST |
| `v1/auth.py` | 회원가입 (`POST /register`), 로그인 (`POST /login`) |
| `v1/session.py` | 세션 이력 조회, 일별 정확도 저장/조회, 주간 정확도 |
| `v1/deps.py` | `Authorization: Bearer <token>` 검증 의존성 (`get_current_user`, `get_optional_current_user`) |

---

### `app/core/`
**역할:** 앱 전반에서 공유하는 기반 모듈. 도메인 로직 없이 설정·DB·수학·하드웨어 추상화만 담당. 어느 레이어에서도 import 가능.

| 파일 | 주요 내용 |
|---|---|
| `config.py` | `.env` 파싱 → `Settings` dataclass. `DATABASE_URL`, `MOCK_PIPELINE_MODE`, `TTS_ENABLED` 등 |
| `database.py` | SQLAlchemy ORM 모델(`User`, `ExerciseSession`, `DailyAccuracyHistory` 등), `init_db()`, `get_db()` |
| `geometry.py` | **dict 기반** 3D 기하 유틸. `calculate_angle()`, `get_midpoint()`, `calculate_angle_2d()`. 입력은 `{'x_m': ..., 'y_m': ..., 'z_m': ...}` 형태. 코칭/측정 각도 계산에 사용. |
| `utils.py` | `AngleSmoother` (지수 이동 평균으로 각도 노이즈 제거), `extract_keypoints()` (YOLO 결과 → dict 변환) |
| `audio.py` | `TTSPlayer` — 별도 스레드에서 음성 파일을 큐 순서대로 재생. `tts_engine` 전역 싱글턴. |
| `monitor.py` | `SystemMonitor` — CPU/RAM 사용률 주기적 수집 및 로깅 |
| `gpu_debug.py` | Jetson 전용 tegrastats 기반 GPU 메모리 스냅샷 로깅 |
| `types.py` | `Stage` enum — 운동 종류 식별자 |

---

### `app/exercises/`
**역할:** 운동별 도메인 패키지. **새 운동을 추가할 때는 이 폴더 안에 운동명 폴더를 하나 추가**하면 된다. 각 운동 폴더는 `features.py` / `feedback.py` / `processor.py` 세 파일로 구성.

#### `exercises/shared/`
모든 운동 도메인이 공통으로 의존하는 기반 모듈.

| 파일 | 주요 내용 |
|---|---|
| `base.py` | `BaseProcessor` (ABC — 모든 프로세서가 상속), `BaseDTW` (모든 DTW 엔진이 상속), `AsyncLiveDtwRunner` (실시간 DTW 비동기 실행기), `DtwFrameCsvLogger` (프레임별 DTW 결과 CSV 기록) |
| `dtw_feature_extractor.py` | **tuple 기반** 공통 기하 유틸. `calc_angle()`, `midpoint()`, `line_angle_from_vertical()`, `line_angle_from_horizontal()`, `horizontal_error_deg()`. `core/geometry.py`와 입력 형식이 다르기 때문에 별도 유지. |
| `common.py` | 피드백 점수 계산 공통 유틸. `clamp01()`, `feature_error()`, `phase_is()`, `top_features()`, `similarity_gap()`, `build_issue()` |
| `posture.py` | `get_pose_angle()` (운동 종류 → 관절 각도 계산), `get_kpt()`, `is_all_joints_visible()`, `to_coords()`. 코칭/ROM 측정 모드에서 사용. |
| `measurement.py` | `MeasurementProcessor` (ROM 측정 — PREPARE→MEASURE→HOLD→DONE 상태 머신), `CoachingProcessor` (실시간 각도 코칭 — 어깨 외회전 등) |

#### `exercises/bird_dog/`
버드독 운동 도메인.

| 파일 | 주요 내용 |
|---|---|
| `features.py` | `get_bird_dog_features_mp(pts)` — MediaPipe landmarks → 14차원 feature 벡터 (몸통 기울기, 팔·다리 각도 등) |
| `feedback.py` | `extract_birddog_issues(live_result, summary)` — DTW 결과에서 교정 이슈 추출 |
| `processor.py` | `BirdDogDTWProcessor` (BaseProcessor 구현 — 반복 감지, 실시간 유사도 업데이트), `BirdDogDTW` (BaseDTW 구현 — 레퍼런스 JSON 로드, DTW 점수 계산) |

#### `exercises/knee_raise/`
무릎 들기 운동 도메인.

| 파일 | 주요 내용 |
|---|---|
| `features.py` | `get_knee_raise_right_features_yolo(pts)` — YOLO keypoints → 3차원 feature (고관절 굴곡각, 무릎각, 발목 높이), `flip_yolo_left_right(pts)` (왼다리 영상 처리용 좌우 반전) |
| `feedback.py` | `extract_knee_raise_right_issues(live_result, summary)` |
| `processor.py` | `KneeRaiseRightDTWProcessor`, `KneeRaiseRightDTW` |

#### `exercises/neck_rotation/`
목 회전 운동 도메인.

| 파일 | 주요 내용 |
|---|---|
| `features.py` | `get_neck_rotation_features_mp(pts)` — 4차원 feature (몸통 회전, 목 좌우 회전각, 고개 기울기, 어깨선 기울기) |
| `feedback.py` | `extract_neck_rotation_issues(live_result, summary)` |
| `measurement.py` | `NeckROMMeasurementProcessor` — 목 가동범위(ROM) 측정 전용 상태 머신 (READY→LEFT_HOLD→CENTER_RETURN→RIGHT_HOLD→DONE). 보상동작(몸통 회전·고개 기울기) 감지 포함. |
| `processor.py` | `NeckRotationDTWProcessor`, `NeckRotationDTW` |

#### `exercises/shoulder_front_raise/`
어깨 전방 거상 운동 도메인.

| 파일 | 주요 내용 |
|---|---|
| `features.py` | `get_shoulder_front_raise_left_features_mp(pts)` — 6차원 feature (몸통 기울기, 어깨 솟음, 팔 거상각, 팔꿈치각, 수평 오차, 반대팔 거리) |
| `feedback.py` | `extract_shoulder_front_raise_issues(live_result, summary)` |
| `processor.py` | `ShoulderFrontRaiseLeftDTWProcessor`, `ShoulderFrontRaiseLeftDTW` |

---

### `app/hardware/`
**역할:** 물리 장치 드라이버/관리 레이어. 카메라 하드웨어를 추상화해서 상위 레이어(services/)가 장치 종류에 무관하게 프레임을 받을 수 있도록 함.

| 파일 | 주요 내용 |
|---|---|
| `camera.py` | `CameraManager` — Intel RealSense 카메라 시작/정지, RGB + Depth 프레임 수신, `update_keypoints_3d()` (픽셀 좌표 + 깊이값 → 실제 3D 미터 좌표 변환). `camera_manager` 전역 싱글턴. |

---

### `app/schemas/`
**역할:** FastAPI 라우터의 요청/응답 Pydantic 모델. 입력 검증과 직렬화만 담당. 비즈니스 로직 없음.

| 파일 | 주요 내용 |
|---|---|
| `auth.py` | `RegisterRequest`, `LoginRequest`, `AuthResponse` |
| `session.py` | `RecentSessionItem`, `DailyAccuracyUpsertRequest`, `DailyAccuracyHistoryItem`, `WeeklyAccuracyResponse` |

---

### `app/services/`
**역할:** 특정 운동 도메인에 종속되지 않는 공통 비즈니스 로직. 운동별 피드백 추출은 `exercises/*/feedback.py`에 있고, 여기 `feedback/`은 그것들을 라우팅·집계하는 레이어.

| 파일 | 주요 내용 |
|---|---|
| `motion_service.py` | `MotionService` — WebSocket 루프 전체 관리. 카메라 초기화, MediaPipe/YOLO 포즈 추정, `processor.process()` 호출, 결과 직렬화 후 클라이언트 전송. |
| `ai_service.py` | `YOLODetector` — YOLO 모델 로드, 워밍업, 프레임 추론 래퍼 |
| `auth_service.py` | `AuthService` — bcrypt 비밀번호 해싱/검증, JWT 발급/검증 |
| `session_service.py` | `SessionService` — 세션 생성/조회, 일별 정확도 upsert, 주간 정확도 집계 |
| `exercise_catalog.py` | `EXERCISE_REGISTRY` (운동 ID → 내부 설정 매핑), `resolve_limit()`, `parse_measure_schedule()`, `list_exercises_for_client()` |
| `score_service.py` | `AccuracyState`, `deviation_penalty()`, `recovery_bonus()`, `update_accuracy()`, `build_deviation_flags()` — 프레임마다 자세 이탈 패널티/회복 보너스 계산 |
| `mock_ws_service.py` | `run_mock_measure_flow()`, `run_mock_coach_flow()` — 카메라/AI 없이 WebSocket 흐름만 검증하는 개발용 Mock |
| `feedback/realtime_feedback_router.py` | `RealTimeFeedbackRouter` — 운동 종류에 따라 `exercises/*/feedback.py`의 이슈 추출 함수로 라우팅 |
| `feedback/session_feedback_summary.py` | `SessionFeedbackSummary` — 세션 전체 이슈 누적 집계, `format_top3_text()` |

---

### `app/assets/`
**역할:** 런타임에 서버가 읽는 정적 파일. 코드가 아닌 데이터 파일.

| 경로 | 내용 |
|---|---|
| `assets/models/` | AI 모델 파일. `pose_landmarker_full.task` (MediaPipe), `yolov8n-pose.pt` (YOLO) |
| `assets/reference/` | DTW 레퍼런스 JSON. `scripts/gen_*.py`를 실행해서 생성. 운동별 정상 동작 feature 시퀀스 저장. |

---

### `scripts/`
**역할:** 레퍼런스 JSON 생성용 일회성 실행 스크립트. 정상 동작 영상(`.mp4`)을 AI로 분석해 `assets/reference/*.json`을 만들어낸다. 서버 코드가 아니므로 평소엔 실행할 일 없음.

| 파일 | 사용 모델 | 생성 파일 |
|---|---|---|
| `gen_bird_dog_reference.py` | MediaPipe | `bird_dog_reference_mp.json` |
| `gen_neck_rotation_reference_mp.py` | MediaPipe | `neck_rotation_reference_mp.json` |
| `gen_knee_raise_reference_yolo.py` | YOLO | `knee_raise_left_reference_yolo.json` |
| `gen_shoulder_front_raise_reference.py` | MediaPipe | `shoulder_front_raise_left_reference_mp.json` |
| `gen_knee_raise_left_reference_mp.py` | MediaPipe | ⚠️ TODO: `get_knee_raise_right_features_mp` 미구현 |
| `gen_neck_rotation_reference_yolo.py` | YOLO | ⚠️ TODO: `get_neck_rotation_features_yolo` 미구현 |

---

## 주요 흐름

### WebSocket 실시간 처리

```
클라이언트 WebSocket 연결
    └─ api/v1/api.py  (입력 파싱만)
        └─ MotionService.start()
            ├─ 카메라 프레임 수신  (hardware/camera.py)
            ├─ MediaPipe / YOLO 포즈 추정
            └─ processor.process(keypoints, frame)
                ├─ exercises/*/processor.py     → DTW 점수 모드
                ├─ exercises/shared/measurement.py → ROM 측정 / 코칭 모드
                └─ exercises/neck_rotation/measurement.py → 목 ROM 측정
```

### DTW 점수 모드 내부

```
processor.process()
    ├─ exercises/*/features.py        → 포즈 keypoints → feature 벡터
    ├─ BaseDTW.score()                → DTW 유사도 계산 (ThreadPoolExecutor 비동기)
    ├─ services/feedback/realtime_feedback_router.py → exercises/*/feedback.py 라우팅
    └─ services/feedback/session_feedback_summary.py → 세션 누적 피드백 집계
```

---

## 환경 변수 (.env)

| 키 | 기본값 | 설명 |
|---|---|---|
| `DATABASE_URL` | MySQL URL | SQLAlchemy 연결 문자열 |
| `AUTH_SECRET_KEY` | `dev-change-this-secret` | JWT 서명 키 |
| `MOCK_PIPELINE_MODE` | `false` | `true` 시 카메라/AI 없이 Mock 흐름으로 동작 |
| `TTS_ENABLED` | `true` | `false` 시 음성 안내 비활성화 |
| `YOLO_MODEL_PATH` | `app/assets/models/yolov8n-pose.pt` | YOLO 모델 경로 |

---

## 서버 실행

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8018 --reload
```

---

## API 엔드포인트

### REST

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| GET | `/` | 불필요 | 서버 상태 확인 |
| GET | `/api/v1/exercises` | 불필요 | 운동 카탈로그 목록 |
| POST | `/api/v1/auth/register` | 불필요 | 회원가입 |
| POST | `/api/v1/auth/login` | 불필요 | 로그인 (Bearer 토큰 발급) |
| GET | `/api/v1/sessions/recent` | Bearer | 최근 세션 이력 |
| GET | `/api/v1/sessions/weekly-accuracy` | Bearer (선택) | 주간 정확도 |

### WebSocket

| 경로 | 설명 |
|---|---|
| `/api/v1/ws/measure?parts=...` | ROM 측정 모드 (PREPARE→MEASURE→HOLD→DONE) |
| `/api/v1/ws/coach/{exercise}?limit=...` | 실시간 각도 코칭 모드 |
| `/api/v1/ws/dtw/{exercise}` | DTW 유사도 점수 모드 |

---

## 운동별 모델 조합

| 운동 | feature 모델 | feature 차원 | 비고 |
|---|---|---|---|
| `bird_dog` | MediaPipe | 14 | 몸통·팔·다리 전신 |
| `knee_raise` | YOLO | 3 | 고관절·무릎·발목 |
| `neck_rotation` | MediaPipe | 4 | 몸통·목·고개·어깨선 |
| `shoulder_front_raise` | MediaPipe | 6 | 몸통·어깨·팔 |
