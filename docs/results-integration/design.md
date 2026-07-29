# 결과 데이터 연동 설계 (자세분석 / 검사결과 / 운동기록)

> 작성 2026-07-16. 프론트 3개 결과 페이지를 서버 실데이터와 연결하기 위한 설계.
> 현재는 값이 하드코딩 또는 localStorage 기반이라 서버 결과와 매핑되어 있지 않음.

## 1. 현재 상태 진단

| 페이지 | 현재 데이터 출처 | 상태 |
|---|---|---|
| 자세 분석(대시보드) | DB `daily_accuracy_history` + localStorage | 주간 정확도만 실데이터, 나머지 하드코딩 |
| 검사 결과 | `romStorage` (localStorage) | 서버 아님, 브라우저 로컬 |
| 운동 기록(달력) | DB `daily_accuracy_history`(하루 1점) | 클릭 상세 없음 |

핵심 사실
- DB에 실제로 쓰이는 건 `daily_accuracy_history`뿐. `ExerciseSession / ExerciseSessionSummary / ExerciseRep / RealtimeMotionLog / UserMaxRom` 테이블은 **정의만 되어 있고 미사용**.
- MotionService는 결과를 파일(recordings, features, dtw csv, rom_results, metrics)로만 저장하고 **DB엔 안 씀**. user_id/exercise_id 연결 없음.
- ROM은 클라이언트 localStorage에만 존재.

## 2. 확정된 방향 (2026-07-16 사용자 결정)

- **저장 주체 = 서버(MotionService)가 세션 종료 시 직접 DB 기록** (신뢰성 우선)
- **ROM = UserMaxRom 테이블로 이전** (localStorage는 오프라인 폴백만)
- 프레임 원시 로그(RealtimeMotionLog)는 DB 제외 — 용량 부담. 파일 유지, 필요 시 세션ID로 경로만 연결.

## 3. 페이지별 표시 값 스펙

### 검사 결과 (ROM 측정 1건)
- 부위별 최대 각도 + 정상기준 대비 달성률(%)
- 좌우 비대칭 편차(°) + 임계 초과 여부
- 종합 등급(양호/주의/교정필요)
- 측정 일시
- (신규) 지난 검사 대비 변화 ↑↓
- 수집원: MeasurementProcessor `rom`, `_compute_bilateral_symmetry`
- ※ 현재 CheckResultPage가 이 스펙과 이미 거의 일치. 남은 건 데이터 소스 교체.

### 운동 기록 (운동 세션 1건)
- 운동명·날짜·소요시간
- 완료 반복 수(rep) / 목표 대비
- 종합 정확도 + rep 평균
- rep별 정확도 막대
- 주요 오류 유형 Top (예: 팔꿈치 벌어짐 ×3)
- 최대 각도 / 목표 각도
- 수집원: `rep_events`, rep별 `compare` 점수, `last_live_similarity`, `main_error_feature`, 보상자세 CSV

### 자세 분석 (대시보드, 누적)
- 주간/월간 정확도 추이 (기존 유지)
- 운동별 평균 정확도(필터)
- 부위별 ROM 추이
- 누적 통계(총 세션/총 rep/연속일 streak)
- 가장 개선된 / 취약 부위

## 4. 파이프라인

```
[세션 진행] processors가 rep·정확도·ROM 계산
   └ 세션 종료(finally)
[수집] SessionResult 집계 (total_reps, overall/rep 정확도, rep별 점수, 주요오류, ROM)
[저장] 기존 DB 테이블 적재
   ExerciseSession → Summary → ExerciseRep(N) / UserMaxRom(검사)
[전송] 신규 REST API
[수신] 프론트: getRomData()/하드코딩 → API fetch
```

### DB 매핑
| 테이블 | 채울 내용 |
|---|---|
| ExerciseSession | user_id, exercise_id, started/ended, status |
| ExerciseSessionSummary | total_reps, overall_accuracy_pct, rep_accuracy_avg_pct, (신규?) main_errors_json |
| ExerciseRep | rep_no, max_angle_deg, rep_accuracy_pct, start/end_similarity |
| UserMaxRom | 부위별 max_rom_deg, is_current |
| daily_accuracy_history | 기존 유지 |

### API 초안
```
GET /api/v1/sessions?from=&to=&exercise=   목록(요약) — 달력/대시보드
GET /api/v1/sessions/{id}                  상세(rep 포함) — 운동기록 클릭
GET /api/v1/rom/latest                      검사결과 현재 ROM 전체
GET /api/v1/rom/history?part=              ROM 부위별 추이
```
기존 `/recent`, `/accuracy-history/*` 재사용.

## 5. ⚠️ 선행 관문 — WebSocket 인증

- 현재 WS 엔드포인트(`/ws/measure`, `/ws/coach/{exercise}`, `/ws/dtw/{exercise}`)는 user_id/토큰을 받지 않음.
- 인증은 HTTP `Authorization: Bearer` 헤더 방식인데 **브라우저 WebSocket은 커스텀 헤더 불가**.
- 해법: WS URL에 `token` 쿼리 추가 → 서버가 `AuthService.verify_access_token`로 검증 → user_id 확보.
  - 예: `/api/v1/ws/dtw/straight_leg_raise_left?rom=...&token=<accessToken>`
- 이것이 서버 주도 저장의 **선행 필수 작업**.

## 6. 열린 질문

1. 주요 오류 유형 저장 — Summary에 `main_errors_json` 컬럼 추가 vs 보상자세 CSV를 세션ID로 연결.
2. exercise_id 매핑 — `rehab_exercises`에 운동 6종 시드 데이터 존재 여부 확인 필요.
3. 미로그인/토큰만료 세션 — DB 스킵(파일만) vs 익명 user_id.
4. ExerciseResultPage 방향 — 현재 ROM 신체부위 분석 구조 유지 후 라벨만 변경 vs 반복·정확도 중심으로 값·라벨 교체.
