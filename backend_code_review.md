# 백엔드 코드 리뷰

작성일: 2026-05-22 | 작성자: 김주형

---

## 1. 전체 구조

```
backend/app/
├── main.py                   ← FastAPI 앱 초기화, YOLO 모델 로드, 서버 생명주기
├── api/v1/
│   ├── api.py                ← WebSocket 라우터 (measure / coach / dtw)
│   ├── auth.py               ← 회원가입 / 로그인 REST API
│   ├── session.py            ← 세션 이력 조회 REST API
│   └── deps.py               ← JWT 토큰 검증 의존성
├── core/
│   ├── config.py             ← 환경변수 설정 (Settings)
│   ├── database.py           ← SQLite 연결 & 스키마 초기화
│   ├── audio.py              ← TTS 엔진
│   ├── geometry.py           ← 3D 좌표 계산
│   ├── utils.py              ← AngleSmoother 등 공용 유틸
│   └── store.py              ← 전역 상태 저장소
├── hardware/
│   ├── camera.py             ← RealSense 카메라 관리 (camera_manager)
│   └── scanner.py
├── schemas/
│   ├── auth.py               ← 로그인/회원가입 요청·응답 스키마
│   └── session.py            ← 세션 스키마
└── services/
    ├── motion_service.py         ← WebSocket 메인 루프
    ├── processors.py             ← 운동별 프로세서 + DTW 엔진 (핵심, 3300줄)
    ├── dtw_feature_extractor.py  ← keypoint → feature 벡터 변환
    ├── exercise_catalog.py       ← 운동 목록 & 라우팅 설정
    ├── ai_service.py             ← YOLODetector 래퍼
    ├── auth_service.py           ← 인증 비즈니스 로직
    ├── session_service.py        ← 세션 저장 / 조회
    ├── score_service.py          ← 정확도 / 패널티 / 보너스 계산
    ├── feedback/
    │   ├── realtime_feedback_router.py       ← 운동별 피드백 라우터
    │   ├── realtime_feedback_birddog.py      ← 버드독 피드백 룰
    │   ├── realtime_feedback_kneeraiseright.py
    │   ├── realtime_feedback_neckrotation.py
    │   ├── realtime_feedback_shoulderfrontraise.py
    │   ├── session_feedback_summary.py       ← 세션 전체 피드백 요약
    │   └── common.py
    └── rules/
        ├── posture.py    ← get_pose_angle() — 관절 각도 계산
        └── feedback.py   ← 룰 베이스 피드백 판단
```

---

## 2. API 명세

### REST API

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| POST | `/api/v1/auth/register` | 회원가입 | 불필요 |
| POST | `/api/v1/auth/login` | 로그인 → access_token 반환 | 불필요 |
| GET | `/api/v1/exercises` | 운동 카탈로그 목록 조회 | 불필요 |
| GET | `/api/v1/sessions` | 세션 이력 조회 | JWT Bearer 필요 |

**회원가입 요청 body**
```json
{ "login_id": "...", "user_name": "...", "phone_number": "...", "password": "..." }
```

**로그인 응답 body**
```json
{ "user_id": 1, "login_id": "...", "user_name": "...", "access_token": "..." }
```

---

### WebSocket API

| 경로 | 모드 | 설명 |
|------|------|------|
| `WS /api/v1/ws/measure` | MEASURE | 관절 가동범위(ROM) 측정 |
| `WS /api/v1/ws/coach/{exercise}` | COACH | 실시간 코칭 |
| `WS /api/v1/ws/dtw/{exercise}` | DTW | 동작 유사도 점수 |

**`{exercise}` 지원 값**

| 값 | 운동 |
|----|------|
| `bird_dog` | 버드독 (허리 안정화) |
| `shoulder_front_raise_left` | 어깨 전방 거상 (왼팔) |
| `shoulder_front_raise_right` | 어깨 전방 거상 (오른팔) |
| `knee_raise_right` | 무릎 거상 (오른다리) |
| `knee_raise_left` | 무릎 거상 (왼다리) |
| `neck_rotation` | 목 좌우 회전 |

**쿼리 파라미터**
- `/ws/measure?parts=neck` — 목 ROM만 측정
- `/ws/measure?parts=shoulder,knee` — 지정 부위 순서대로 측정
- `/ws/coach/{exercise}?limit=45` — 목표 각도 지정 (기본값은 운동별 설정값)

**WebSocket 공통 응답 포맷**
```json
{
  "type": "frame",
  "jpeg_b64": "...",
  "data": {
    "mode": "DTW",
    "status": "running",
    "rep_count": 1,
    "accuracy_pct": 82.5,
    "feedback": "골반을 수평으로 유지해주세요.",
    "keypoints": { "5": {"x": 320, "y": 180}, ... },
    "frame_w": 640,
    "frame_h": 360
  }
}
```

---

## 3. 메인 처리 흐름

```
[프론트 WebSocket 연결]
        ↓
  api.py 라우터
        ↓
  MotionService.start()
        ↓
  ┌─────────────────────── while loop ───────────────────────────┐
  │  1. camera_manager.get_frame()                               │
  │     → RealSense RGB 프레임 + 깊이 프레임 획득                 │
  │                                                              │
  │  2. yolo.infer(frame)                                        │
  │     → YOLO keypoint 추출 (COCO 17점 기준)                    │
  │                                                              │
  │  3. processor.extract_mp_features(keypoints)                 │
  │     → keypoint → feature 벡터 변환 (운동별 다름)              │
  │                                                              │
  │  4. processor.process(keypoints, frame, mp_features)         │
  │     → 운동 상태 판단 / DTW 점수 계산 / 피드백 생성            │
  │                                                              │
  │  5. _send_packet(frame, data)                                │
  │     → JPEG(base64) + JSON 데이터 프론트에 전송               │
  └──────────────────────────────────────────────────────────────┘
```

---

## 4. 운동별 프로세서

### 4-1. MeasurementProcessor (ROM 측정)

관절 가동범위를 측정하는 상태머신.

```
PREPARE (5초) → MEASURE (8초) → HOLD (3초) → stage_finished
```

- `PREPARE` — 전신이 화면 안에 들어올 때까지 대기
- `MEASURE` — 매 프레임 각도를 계산해 최대값(`max_angle`) 갱신
- `HOLD` — TTS "3초 유지" 후 결과 반환 (베스트 프레임 이미지 포함)
- 스케줄 (`target_schedule`) 에 따라 여러 부위 순차 측정 가능

### 4-2. NeckROMMeasurementProcessor (목 ROM 측정)

목 좌우 회전 가동범위를 상태머신으로 측정.

```
READY → LEFT_HOLD (3초 유지) → CENTER_RETURN → RIGHT_HOLD (3초 유지) → DONE
```

- `neck_turn_angle` feature 기반으로 상태 전환
- 몸통·골반·어깨 보상 감지 시 `invalid` 반환 후 리셋
- 완료 시 `neck_left_max`, `neck_right_max`, `neck_diff` 반환

### 4-3. CoachingProcessor (실시간 코칭)

각도 + 자세 체크 기반의 실시간 피드백.
현재 `SHOULDER_EXTERNAL_ROTATION`(어깨 외회전) 구현됨.

- 팔꿈치 벌어짐 (`elbow_dist > 0.15m`) 감지 → 피드백
- 승모근 상승 (`shoulder_rise > 0.05m`) 감지 → 피드백
- 정확도는 `score_service`의 패널티/보너스 누적 방식으로 계산

---

## 5. DTW 알고리즘

### 개요

레퍼런스(정상 동작 JSON)와 사용자 실시간 동작을 **DTW(Dynamic Time Warping)**로 비교해 유사도를 점수화한다.

```
레퍼런스 JSON (사전 녹화된 정상 동작 feature 시퀀스)
         ↓
  DTW Engine (BirdDogDTW 등)
         ↓
  get_live_similarity()   ← 실시간 부분 매칭 (0.12초 주기 비동기)
  compare()               ← 1회 완료 후 전체 매칭 (최종 점수)
```

### feature 벡터 (운동별)

| 운동 | feature 수 | 주요 feature |
|------|-----------|-------------|
| 버드독 | 14개 | trunk, pelvic, right_arm, left_leg, left_arm, right_leg + 수평오차 + 관절각 |
| 어깨 전방 거상 | 6개 | trunk, shoulder_rise, arm_raise, elbow_angle, arm_h_err, support_dist |
| 무릎 거상 (YOLO) | 3개 | hip_flexion, knee_angle, ankle_rel_y |
| 목 회전 | 4개 | trunk_rotation, neck_turn_angle, head_tilt, shoulder_line_angle |

### DTW 계산 방식

**1) 정규화**
```
normalized = (value - feat_min) / (feat_max - feat_min)
```
레퍼런스 시퀀스의 min/max로 사용자 feature를 정규화해 스케일 차이를 제거한다.

**2) 프레임 간 거리 계산**
```
dist(a, b) = ||( |a - b| * weight )|| (L2 norm)
```
feature마다 중요도 가중치를 다르게 설정한다. (예: 버드독에서 motion feature 가중치 1.3, posture feature 가중치 0.8~1.1)

**3) DTW DP (Sakoe-Chiba Band)**
```
dp[i][j] = dist(a[i], b[j]) + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
band = max(4, len * 0.3)
```
Sakoe-Chiba 밴드로 과도한 시간 왜곡을 제한한다.

**4) 점수 계산**
```
norm_cost = total_cost / path_length

motion_similarity    = max(0, 100 - 12.0 * motion_cost)
posture_similarity   = max(0, 100 - 14.0 * posture_cost)
final_score          = (motion_similarity * 0.5) + (posture_similarity * 0.5)
```

**5) 실시간 유사도 (get_live_similarity)**

매 프레임마다 전체 DTW를 돌리면 성능 문제가 생기므로 비동기로 처리.

```
AsyncLiveDtwRunner
  - 4프레임마다 또는 0.12초마다 비동기 Submit
  - 완료된 Future 결과를 다음 tick()에서 소비
  - 결과가 없으면 직전 결과 재사용
```

실시간에서는 레퍼런스 전체가 아닌 **부분 시퀀스 탐색**(`_find_best_subsequence`)으로 현재 구간을 찾는다.

**6) phase 추정**

동작 진행 단계를 추정해 phase penalty를 부과한다.

```
signal = max(right_arm + left_leg, left_arm + right_leg)  # 버드독 기준
slope  = mean(diff(signal[-4:]))

slope >= 0.75  → "raising"
slope <= -0.75 → "lowering"
progress >= 0.82 → "peak"
progress <= 0.20 → "ready"
```

peak 구간인데 레퍼런스 진행도가 70% 미만이면 penalty 추가.

---

## 6. 피드백 시스템

### RealTimeFeedbackRouter

매 프레임 feature_errors를 받아 운동별 이슈를 추출하고 쿨다운/심각도 필터로 피드백 1개를 선택해 반환한다.

```
feature_errors (각 feature의 오차값)
       ↓
extract_XXX_issues()  ← 운동별 룰 함수
       ↓
이슈 리스트 (severity 포함)
       ↓
쿨다운 2.5초 + severity 0.35 이상 필터
       ↓
instant_feedback 텍스트 1개 반환
```

### SessionFeedbackSummary

세션 동안 발생한 이슈를 누적해 종료 시 상위 3개 피드백을 요약 반환한다.

---

## 7. 리팩토링 포인트

| # | 위치 | 내용 |
|---|------|------|
| 1 | `processors.py` | DTW 엔진 4개(`BirdDogDTW`, `ShoulderFrontRaiseLeftDTW`, `KneeRaiseRightDTW`, `NeckRotationDTW`)에 `_dtw()`, `_normalize()`, `_compute_path_metrics()` 등 거의 동일한 코드 반복 |
| 2 | `processors.py` L2297 | `current = tuple(...)` 두 줄 연속 중복 (`KneeRaiseRightDTWProcessor`) |
| 3 | `api.py` `dtw_endpoint` | 운동 추가 시마다 if/elif 분기를 라우터에서 수정해야 함 |
| 4 | `motion_service.py` | `logger` 쓰다가 `print()` 섞여 있음 (`[DEBUG YOLO RESULT TYPE]`, `[DEBUG KPT]` 등) |
