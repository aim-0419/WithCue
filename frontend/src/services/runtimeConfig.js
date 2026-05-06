const DEFAULT_BACKEND_PORT = "8018";

function getBrowserOrigin() {
  if (typeof window === "undefined" || !window.location) {
    return null;
  }
  return window.location.origin;
}

function getBackendOrigin() {
  const browserOrigin = getBrowserOrigin();
  if (!browserOrigin) {
    return `http://localhost:${DEFAULT_BACKEND_PORT}`;
  }

  const url = new URL(browserOrigin);
  const hostname = url.hostname || "localhost";
  return `${url.protocol}//${hostname}:${DEFAULT_BACKEND_PORT}`;
}

export function getApiBase() {
  // [조현석] 명시된 환경변수가 없으면 현재 접속 호스트 기준으로 백엔드 주소를 계산합니다.
  if (import.meta.env.VITE_API_BASE) {
    return import.meta.env.VITE_API_BASE;
  }
  return getBackendOrigin();
}

export function getWsBase() {
  // [조현석] WebSocket도 API와 동일하게 현재 접속 호스트 기준 주소를 기본값으로 사용합니다.
  if (import.meta.env.VITE_WS_BASE) {
    return import.meta.env.VITE_WS_BASE;
  }
  const apiBase = getApiBase();
  if (apiBase.startsWith("https://")) {
    return `wss://${apiBase.slice("https://".length)}`;
  }
  if (apiBase.startsWith("http://")) {
    return `ws://${apiBase.slice("http://".length)}`;
  }
  return apiBase;
}
