// 키오스크 미러 모드 여부를 앱 전체에서 일관되게 읽어주는 유틸

const KEY = "mirror_mode";

const fromUrl = new URLSearchParams(window.location.search).get("mirror") === "true";
if (fromUrl) {
  sessionStorage.setItem(KEY, "true");
}

export function isMirrorMode() {
  return sessionStorage.getItem(KEY) === "true";
}
