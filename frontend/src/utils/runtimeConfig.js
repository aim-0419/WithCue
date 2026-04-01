// 서버 주소 설정
const DEFAULT_BACKEND_HOST = "192.168.0.25";
const DEFAULT_BACKEND_PORT = "8018";

export function getApiBase() {
  // [조현석] 명시된 환경변수가 없으면 개발 장비(Jetson) 고정 IP로 붙습니다.
  if (import.meta.env.VITE_API_BASE) {
    return import.meta.env.VITE_API_BASE;
  }
  return `http://${DEFAULT_BACKEND_HOST}:${DEFAULT_BACKEND_PORT}`;
}

export function getWsBase() {
  // [조현석] WebSocket도 API와 동일하게 환경변수 우선, 없으면 Jetson 고정 IP를 사용합니다.
  if (import.meta.env.VITE_WS_BASE) {
    return import.meta.env.VITE_WS_BASE;
  }
  return `ws://${DEFAULT_BACKEND_HOST}:${DEFAULT_BACKEND_PORT}`;
}
