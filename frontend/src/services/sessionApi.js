// 운동 세션 기록과 검사(ROM) 결과를 서버에서 조회하는 API 클라이언트.
// Phase 2에서 추가된 /sessions, /rom 엔드포인트를 호출한다. 인증 토큰은 getAuthHeaders로 전달한다.

import { getApiBase } from "./runtimeConfig";
import { getAuthHeaders } from "../utils/authStorage";

// 운동 세션 목록 조회. from/to(YYYY-MM-DD), exercise(운동코드)로 필터링 가능.
export async function fetchSessions({ from = null, to = null, exercise = null, limit = 100 } = {}) {
  const url = new URL(`${getApiBase()}/api/v1/sessions`);
  if (from) url.searchParams.set("from", from);
  if (to) url.searchParams.set("to", to);
  if (exercise) url.searchParams.set("exercise", exercise);
  if (limit) url.searchParams.set("limit", String(limit));
  const res = await fetch(url, { cache: "no-store", headers: getAuthHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch sessions: ${res.status}`);
  return res.json(); // { items: [...] }
}

// 세션 1건 상세 조회 (요약 + rep별).
export async function fetchSessionDetail(sessionId) {
  const res = await fetch(`${getApiBase()}/api/v1/sessions/${sessionId}`, {
    cache: "no-store",
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to fetch session detail: ${res.status}`);
  return res.json();
}

// 현재 사용자의 최신 ROM 값 조회. { rom: {rom_key: angle}, measured_at }.
export async function fetchRomLatest() {
  const res = await fetch(`${getApiBase()}/api/v1/rom/latest`, {
    cache: "no-store",
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to fetch ROM latest: ${res.status}`);
  return res.json();
}

// 특정 rom_key의 측정 이력 조회. { key, items: [{angle_deg, measured_at, is_current}] }.
export async function fetchRomHistory(key) {
  const url = new URL(`${getApiBase()}/api/v1/rom/history`);
  url.searchParams.set("key", key);
  const res = await fetch(url, { cache: "no-store", headers: getAuthHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch ROM history: ${res.status}`);
  return res.json();
}

// ROM 측정 기록이 있는 날짜 목록 조회. { dates: ["YYYY-MM-DD", ...] }.
export async function fetchRomDates() {
  const res = await fetch(`${getApiBase()}/api/v1/rom/dates`, {
    cache: "no-store",
    headers: getAuthHeaders(),
  });
  if (!res.ok) throw new Error(`Failed to fetch ROM dates: ${res.status}`);
  return res.json();
}

// 특정 날짜의 ROM 스냅샷 조회. { date: "YYYY-MM-DD", rom: {rom_key: angle} }.
export async function fetchRomSnapshot(date) {
  const url = new URL(`${getApiBase()}/api/v1/rom/snapshot`);
  url.searchParams.set("date", date);
  const res = await fetch(url, { cache: "no-store", headers: getAuthHeaders() });
  if (!res.ok) throw new Error(`Failed to fetch ROM snapshot: ${res.status}`);
  return res.json();
}
