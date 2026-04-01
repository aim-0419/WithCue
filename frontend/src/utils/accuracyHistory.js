// 클라이언트 로컬 기록 관리 
import { STORAGE_KEYS } from "./authStorage";

const WEEKDAY_LABELS = ["월", "화", "수", "목", "금", "토", "일"];

function clampAccuracy(value) {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function toLocalDateKey(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseStoredHistory() {
  if (typeof window === "undefined") return {};

  try {
    const raw = window.localStorage.getItem(STORAGE_KEYS.accuracyHistory);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function getMonday(date = new Date()) {
  const current = new Date(date);
  const day = current.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  current.setHours(0, 0, 0, 0);
  current.setDate(current.getDate() + diff);
  return current;
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

// 정확도 로컬 저장
export function saveAccuracyHistory(accuracy) {
  if (typeof window === "undefined") return;

  const history = parseStoredHistory();
  const todayKey = toLocalDateKey(new Date());

  // 같은 날 여러 번 운동하면 그날의 마지막 운동 점수만 남깁니다. (마지막 정확도 읽기)
  // 날짜가 바뀌면 이전 날짜 값은 유지되고, 주간 차트는 월요일 시작 7칸으로 표시됩니다.
  history[todayKey] = {
    accuracy: clampAccuracy(accuracy),
    recordedAt: new Date().toISOString(),
  };

  window.localStorage.setItem(STORAGE_KEYS.accuracyHistory, JSON.stringify(history));
}

export function readLatestAccuracy() {
  const history = parseStoredHistory();
  const latestEntry = Object.values(history)
    .filter((item) => typeof item?.accuracy === "number" && typeof item?.recordedAt === "string")
    .sort((a, b) => new Date(a.recordedAt) - new Date(b.recordedAt))
    .at(-1);

  return latestEntry?.accuracy ?? null;
}

export function toWeeklyChartData(baseDate = new Date()) {
  const history = parseStoredHistory();
  const monday = getMonday(baseDate);

  // 월요일~일요일 7일을 고정으로 만들고, 운동 기록이 없는 날은 0점으로 채웁니다.
  return WEEKDAY_LABELS.map((label, index) => {
    const date = addDays(monday, index);
    const dateKey = toLocalDateKey(date);
    const entry = history[dateKey];

    return {
      name: label,
      score: typeof entry?.accuracy === "number" ? entry.accuracy : 0,
    };
  });
}
