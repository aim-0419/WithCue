# 결과 데이터 연동 체크리스트

관련 설계: [design.md](./design.md)

## Phase 0 — 선행 관문 ✅ 완료(2026-07-16)
- [x] WS URL에 `token` 쿼리 추가 (프론트: ExercisePage/CheckPage) — WsCamera는 wsUrl만 수신하므로 무변경
- [x] WS 엔드포인트 3종(measure/coach/dtw)에서 token 검증 → user_id 확보 (`_resolve_ws_user_id` → `AuthService.verify_access_token`)
- [x] MotionService에 user_id/exercise_code 주입 + 시작 로그에 출력
- [x] `rehab_exercises` 6종 시드(`scripts/seed_exercises.py`) — exercise_code == WS 운동 문자열, target_part enum에 neck/core 추가
- [x] 검증: 토큰 왕복 테스트(유효→user_id, 무효/없음→None), 매핑(code→exercise_id) 확인
- [ ] 남은 검증: 서버 재시작 후 실제 세션 연결 시 로그에 user_id 출력 확인(런타임)

## Phase 1 — 서버 주도 저장 (거의 완료, 2026-07-16)
- [x] MotionService에 DB 세션 컨텍스트 + 세션 종료(finally) 집계 저장(`_persist_session_result`)
- [x] 운동 세션: ExerciseSession + Summary + ExerciseRep 기록 (`session_result_service.persist_exercise_session`)
- [x] 프로세서 보강: SLR·neck·shoulder rep-end 이벤트에 max_angle 추가 (bird_dog는 rep_events 없음 → Summary만)
- [x] per-rep 정확도 = MotionService가 rep 시간창 유사도 평균으로 집계 (프레임 스트림 + rep_events)
- [x] 검사(ROM): `user_rom_measurements` 신규 테이블에 rom_key별 저장 + is_current 플립
- [x] 검증(persist 레이어): DB 왕복 테스트 통과(세션/요약/rep 3행, ROM is_current 플립), 테스트 데이터 정리
- [x] **주요 오류 유형 저장 (열린질문 1 → a로 결정)** — ExerciseRep에 `label` 컬럼 추가(ALTER), persist가 rep별 라벨 저장. DB 왕복 검증 완료.
- [ ] **런타임 검증(보류: 카메라 미연결)** — 서버 재시작 후 실제 세션 1회로 MotionService 집계 경로(프레임창→rep 정확도) end-to-end 확인 필요.

## Phase 2 — 조회 API ✅ 완료(2026-07-16)
- [x] GET /api/v1/sessions?from=&to=&exercise= (목록) — session.py
- [x] GET /api/v1/sessions/{id} (상세, rep별 포함, 본인 세션만) — session.py
- [x] GET /api/v1/rom/latest — rom.py (신규 라우터)
- [x] GET /api/v1/rom/history?key= — rom.py
- [x] SessionService에 조회 메서드 추가(list_sessions/get_session_detail/get_rom_latest/get_rom_history)
- [x] 검증: 서비스 로직 실데이터 왕복(목록/상세/본인격리/ROM 최신·이력) 통과 + 라우트 등록 확인
- [ ] 남은 검증: 서버 기동 후 HTTP(curl/Swagger)로 토큰 헤더 포함 응답 확인(런타임)

## Phase 3 — 프론트 수신 연결 (핵심 완료, 2026-07-16)
- [x] API 서비스 레이어 `services/sessionApi.js` (fetchSessions/fetchSessionDetail/fetchRomLatest/fetchRomHistory)
- [x] 검사 결과: CheckResultView가 /rom/latest 우선 사용, 실패 시 localStorage 폴백
- [x] 운동 기록: RecordPage가 daily_accuracy → /sessions 실제 세션 목록으로 교체(달력+일별 상세)
- [x] 검증: 3개 파일 JSX 파싱 통과, orphan import 정리
- [ ] (후속) 자세 분석 대시보드에 /sessions 집계(운동별 평균·누적 통계) 추가
- [ ] (후속) 운동기록 세션 클릭 → /sessions/{id} rep별 상세 드릴다운(ExerciseResultView 연결)
- [ ] 검증(런타임): 서버 기동 + 로그인 상태로 실데이터 표시 확인

## 별도 — 프론트 라벨/값 정리 (레이아웃 유지)
- [ ] 검사결과: 이미 설계와 일치 — 변경 최소
- [ ] 운동결과: 방향 확정 후(열린질문 4) 라벨/값 정리
- [ ] 자세분석: 기존 라벨 점검
