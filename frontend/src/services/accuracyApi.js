import { getApiBase } from "./runtimeConfig";
import { getAuthHeaders } from "../utils/authStorage";

// 정확도 기록 저장 요청
export async function saveAccuracyToServer({ accuracyPct, sourceType, sourceKey }) {
  const res = await fetch(`${getApiBase()}/api/v1/sessions/accuracy-history`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify({
      accuracy_pct: accuracyPct,
      source_type: sourceType,
      source_key: sourceKey ?? null,
    }),
  });

  if (!res.ok) {
    throw new Error(`Failed to save accuracy history: ${res.status}`);
  }

  return res.json();
}

// 주간 정확도 조회 요청
export async function fetchWeeklyAccuracyFromServer({
  sourceType = null,
  sourceKey = null,
} = {}) {
  const url = new URL(`${getApiBase()}/api/v1/sessions/accuracy-history/weekly`);
  if (sourceType) {
    url.searchParams.set("source_type", sourceType);
  }
  if (sourceKey) {
    url.searchParams.set("source_key", sourceKey);
  }
  const res = await fetch(url, {
    cache: "no-store",
    headers: getAuthHeaders(),
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch weekly accuracy: ${res.status}`);
  }

  return res.json();
}

export async function fetchAccuracyHistory({
  sourceType = null,
  sourceKey = null,
  limit = 30,
} = {}) {
  const url = new URL(`${getApiBase()}/api/v1/sessions/accuracy-history`);
  if (sourceType) {
    url.searchParams.set("source_type", sourceType);
  }
  if (sourceKey) {
    url.searchParams.set("source_key", sourceKey);
  }
  if (limit) {
    url.searchParams.set("limit", String(limit));
  }

  const res = await fetch(url, {
    cache: "no-store",
    headers: getAuthHeaders(),
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch accuracy history: ${res.status}`);
  }

  return res.json();
}
