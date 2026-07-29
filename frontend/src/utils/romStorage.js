// ROM 측정 결과를 localStorage에 저장·조회하는 유틸리티
import { STORAGE_KEYS } from "./authStorage";

// 기존 ROM에 새 측정값을 병합해 저장한다. 부위별로 따로 측정해도 누락 없이 누적된다.
export function saveRomData(rom) {
  if (!rom || typeof window === "undefined") return;
  try {
    const existing = getRomData();
    const merged = {
      ...existing,
      ...rom,
      updated_at: new Date().toISOString(),
    };
    window.localStorage.setItem(STORAGE_KEYS.romData, JSON.stringify(merged));
  } catch (e) {
    console.error("[ROM] localStorage 저장 실패:", e);
  }
}

export function getRomData() {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(STORAGE_KEYS.romData);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function clearRomData() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEYS.romData);
}
