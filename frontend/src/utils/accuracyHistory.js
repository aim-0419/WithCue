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
    const parsed = raw ? JSON.parse(raw) : [];
    if (Array.isArray(parsed)) {
      return parsed;
    }
    if (parsed && typeof parsed === "object") {
      return Object.entries(parsed).map(([dateKey, value]) => ({
        dateKey,
        accuracy: typeof value?.accuracy === "number" ? value.accuracy : 0,
        recordedAt: value?.recordedAt ?? `${dateKey}T00:00:00`,
        sourceType: value?.sourceType ?? null,
      }));
    }
    return [];
  } catch {
    return [];
  }
}

export function readAccuracyHistoryEntries(filterSourceType = null) {
  const history = parseStoredHistory();

  return history
    .filter((entry) =>
      filterSourceType ? entry.sourceType === filterSourceType : true
    )
    .sort((a, b) => new Date(b.recordedAt) - new Date(a.recordedAt));
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
export function saveAccuracyHistory(accuracy, sourceType = null) {
  if (typeof window === "undefined") return;

  const history = parseStoredHistory();
  const todayKey = toLocalDateKey(new Date());

  history.push({
    dateKey: todayKey,
    accuracy: clampAccuracy(accuracy),
    recordedAt: new Date().toISOString(),
    sourceType,
  });

  window.localStorage.setItem(
    STORAGE_KEYS.accuracyHistory,
    JSON.stringify(history)
  );
}

export function clearAccuracyHistory() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEYS.accuracyHistory);
}

export function readLatestAccuracy(filterSourceType = null) {
  const history = parseStoredHistory();
  const latestEntry = history
    .filter(
      (item) =>
        typeof item?.accuracy === "number" &&
        typeof item?.recordedAt === "string" &&
        (filterSourceType ? item?.sourceType === filterSourceType : true)
    )
    .sort((a, b) => new Date(a.recordedAt) - new Date(b.recordedAt))
    .at(-1);

  return latestEntry?.accuracy ?? null;
}

export function toWeeklyChartData(baseDate = new Date(), filterSourceType = null) {
  const history = parseStoredHistory();
  const monday = getMonday(baseDate);
  const latestByDate = new Map();

  history.forEach((entry) => {
    if (filterSourceType && entry.sourceType !== filterSourceType) return;
    const recordedAt = new Date(entry.recordedAt);
    const prev = latestByDate.get(entry.dateKey);
    if (!prev || recordedAt > prev.recordedAt) {
      latestByDate.set(entry.dateKey, {
        recordedAt,
        accuracy: entry.accuracy,
      });
    }
  });

  // 월요일~일요일 7일을 고정으로 만들고, 운동 기록이 없는 날은 0점으로 채웁니다.
  return WEEKDAY_LABELS.map((label, index) => {
    const date = addDays(monday, index);
    const dateKey = toLocalDateKey(date);
    const entry = latestByDate.get(dateKey);

    return {
      name: label,
      score: typeof entry?.accuracy === "number" ? entry.accuracy : 0,
    };
  });
}
