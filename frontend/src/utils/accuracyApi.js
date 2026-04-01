import { getApiBase } from "./runtimeConfig";
import { getAuthHeaders } from "./authStorage";

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
export async function fetchWeeklyAccuracyFromServer() {
  const res = await fetch(`${getApiBase()}/api/v1/sessions/accuracy-history/weekly`, {
    cache: "no-store",
    headers: getAuthHeaders(),
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch weekly accuracy: ${res.status}`);
  }

  return res.json();
}
