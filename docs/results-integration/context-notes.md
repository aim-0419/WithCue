# 결과 데이터 연동 — 컨텍스트 노트

작업 중 내린 결정과 근거를 계속 덧붙이는 문서. 관련: [design.md](./design.md)

## 2026-07-16

- **저장 주체를 서버로 결정한 이유** — 클라이언트 POST(기존 daily-accuracy 패턴)보다 신뢰성이 높고, 결과 계산 주체(processor)가 서버에 있어 집계가 자연스럽다. 대가로 WS에 인증 컨텍스트를 연결해야 함.
- **RealtimeMotionLog를 DB에서 제외** — 세션당 수백~수천 행. 프레임 원시는 이미 파일(features json / dtw csv / metrics json)로 남으므로 DB엔 집계만.
- **WS 인증이 선행 관문** — 브라우저 WebSocket은 Authorization 헤더를 못 실어서 token을 쿼리로 전달해야 함. 이걸 먼저 안 뚫으면 서버가 user_id를 몰라 저장 자체가 불가.
- **CheckResultPage는 이미 설계와 일치** — 부위별 ROM, 달성률%, 좌우 비대칭, 종합등급을 이미 표시. 데이터 소스만 localStorage→서버로 교체하면 됨. 라벨 변경 거의 불필요.
- **ExerciseResultPage 구조 불일치 → (b) 운동 수행 중심으로 결정(2026-07-16)** — 레이아웃(점수 라디얼 / 요약 타일 2 / BodyFigure / 액션)은 그대로 두고 값·라벨만 교체.
  - 적용: scoreLabel "운동 수행 점수"→"종합 정확도", primaryMetric "운동 시간/00:00"→"완료 반복/0회", secondaryMetric "ROM 달성률"→"평균 정확도", 패널 제목 "신체 부위별 관절 분석"→"신체 부위별 수행 분석".
  - MOCK_REGION_DATA: 운동 5종이 쓰는 부위(neck·torso·right_arm·left_arm·pelvis·right_leg·left_leg)의 지표를 [반복 정확도 / 최대 각도 / 주요 오류]로 relabel. thigh·calf(현재 미사용)는 유지.
  - **미처리(백엔드 배선 시 마무리)**: `buildBodyMetricsFromRom`·`derivedScore`는 여전히 ROM 파생. localStorage에 ROM이 있으면 모달이 ROM 라벨을 보일 수 있음. 실데이터(exerciseResult.bodyMetrics/score)가 들어오면 우선 적용되어 해소됨. 값·이름만 바꾸라는 요청 범위상 데이터 경로 자체는 유지.
- **CheckResultPage·AnalysisPage는 무변경** — Check는 이미 부위별 ROM·달성률·비대칭·등급을 표시(설계와 일치), Analysis는 정확도 대시보드로 이미 정합. 라벨 변경 불필요, 향후 데이터 소스만 교체.

## 2026-07-16 — Phase 0 완료

- **WS 인증 채널** — 브라우저 WS가 헤더를 못 실으므로 `token`을 쿼리로 전달. 백엔드 `_resolve_ws_user_id(token)`(api.py)가 `AuthService.verify_access_token`으로 검증해 user_id 반환(무효/없음→None). measure/coach/dtw 3종 모두 적용. MotionService 생성 시 `user_id`, `exercise_code` 주입, 시작 로그에 출력.
- **프론트** — ExercisePage(dtw/coach), CheckPage(measure)의 wsUrl에 `&token=`/`?token=` 추가(`getAccessToken()`). WsCamera는 wsUrl만 받으므로 무변경. 다른 WS URL 생성부 없음.
- **exercise_code 규약** — `exercise_code == WS 경로의 exercise 문자열`(예: "neck_rotation"). 세션 저장 시 문자열로 `RehabExercise.exercise_code` 조회 → exercise_id. 별도 매핑 함수는 소비처(Phase 1)에서 추가.
- **target_part enum 확장** — left_arm/right_arm/left_leg/right_leg + **neck, core** 추가(사용자 결정). 모델(database.py) 수정 + `scripts/seed_exercises.py`가 MySQL ALTER 후 6종 멱등 삽입. bird_dog→core, neck_rotation→neck.
- **비로그인/토큰만료 → 세션 차단으로 결정(2026-07-16, 열린질문 3 종료)** — user_id=None이면 WS 세션 자체를 거부. api.py `_reject_unauthorized`가 메시지 후 전용 코드 **4401**로 종료. measure/coach/dtw 3종 모두 mock 경로 뒤(실세션 경로)에 게이트. mock_pipeline_mode는 현재 off라 mock 게이트는 미적용(필요 시 추가).
  - 프론트 WsCamera: onclose에서 `e.code === 4401`이면 **재연결 중단** + "로그인이 필요합니다" 표시(무한 재연결 방지). 로그인 화면 리다이렉트는 후속(콜백 prop 필요).
- **런타임 검증 남음** — 코드/토큰 왕복은 검증했으나, 실제 브라우저 세션→서버 로그 user_id 출력은 **서버 재시작 후** 확인 필요.

## 2026-07-16 — Phase 1 착수 결정

- **운동 세션 범위 = 프로세서 보강 후 Rep까지 전부(사용자 결정)** — DTW 프로세서들이 per-rep 정확도·최대각을 안 남기므로, 각 프로세서가 rep 종료 시 `{rep_no, started_at, ended_at, label, accuracy_pct, max_angle_deg}`를 리스트로 보존하도록 보강. BaseProcessor에 공용 rep-tracking 헬퍼(_rep_track_start/frame/end, get_rep_results) 추가해 중복 최소화. accuracy는 rep 구간 live_similarity 평균, max_angle은 구간 피크.
- **검사 ROM = 전용 테이블 신규(사용자 결정)** — `user_rom_measurements`(user_id, rom_key, angle_deg, measured_at, is_current). rom_key별 1행, 새 측정 시 이전 is_current=0 후 삽입. 프론트 flat ROM dict와 무손실 일치. create_all로 생성(ALTER 불필요).
- **세션 유형 구분** — exercise_code가 "check_"로 시작하면 검사(ROM) → user_rom_measurements. 그 외(6종 운동)는 ExerciseSession+Summary+Rep. 코칭(/ws/coach)은 rep 없음 → Summary는 total_reps=0 + 연속 정확도.
- **저장 위치** — session_service에 persist 함수 추가, MotionService finally에서 호출.

## 2026-07-16 — Phase 1 마무리

- **열린질문 1 → (a) ExerciseRep.label 컬럼 추가로 결정.** 모델 수정 + MySQL ALTER(`ADD COLUMN label VARCHAR(50) NULL AFTER rep_accuracy_pct`). persist_exercise_session이 rep별 label 저장. rep_events의 label(정상/무릎 굽힘 등)이 그대로 들어감. DB 왕복 검증 완료.
- **런타임 검증 보류** — 카메라 미연결로 실제 세션 end-to-end(프레임창→rep 정확도 집계)는 미확인. persist 레이어(DB 왕복)는 검증됨. 서버 재시작 후 세션 1회로 확인 예정. 확인 포인트: 로그 `[SessionResult] 운동 세션 저장…`, exercise_sessions/summary/reps/user_rom_measurements 행 생성.
- **Phase 1 산출물** — 신규: `app/services/session_result_service.py`, 테이블 `user_rom_measurements`, 컬럼 `exercise_reps.label`. 수정: database.py(모델2), motion_service.py(_persist_session_result 등), SLR/neck/shoulder processor(rep-end max_angle).

## 관련 파일

- 백엔드: `app/services/motion_service.py`(세션 종료 finally), `app/api/api.py`(WS 엔드포인트), `app/api/deps.py`(인증), `app/core/database.py`(테이블), `app/services/session_service.py`
- 프론트: `src/components/camera/WsCamera.jsx`(WS URL), `src/features/exercise/pages/ExercisePage.jsx`, `src/features/check/pages/CheckPage.jsx`, `src/features/*/results/*.jsx`, `src/utils/romStorage.js`, `src/services/accuracyApi.js`
