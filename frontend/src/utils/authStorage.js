// 로컬 저장 + 인증 접근
export const STORAGE_KEYS = {
  // 키 정의
  accessToken: "withcue_access_token",
  tokenType: "withcue_token_type",
  userName: "withcue_user_name",
  userId: "withcue_user_id",
  userGender: "withcue_user_gender",
  accuracyHistory: "withcue_accuracy_history",
  romData: "withcue_rom_data",
};

export function setAuthSession({
  accessToken,
  tokenType = "bearer",
  userName,
  userId,
  userGender,
}) {
  if (typeof window === "undefined") return;

  window.localStorage.setItem(STORAGE_KEYS.accessToken, accessToken);
  window.localStorage.setItem(STORAGE_KEYS.tokenType, tokenType);
  if (userName) window.localStorage.setItem(STORAGE_KEYS.userName, userName);
  if (userId !== undefined && userId !== null) {
    window.localStorage.setItem(STORAGE_KEYS.userId, String(userId));
  }
  if (userGender) {
    window.localStorage.setItem(STORAGE_KEYS.userGender, userGender);
  }
}

export function clearAuthSession() {
  if (typeof window === "undefined") return;

  window.localStorage.removeItem(STORAGE_KEYS.accessToken);
  window.localStorage.removeItem(STORAGE_KEYS.tokenType);
  window.localStorage.removeItem(STORAGE_KEYS.userName);
  window.localStorage.removeItem(STORAGE_KEYS.userId);
  window.localStorage.removeItem(STORAGE_KEYS.userGender);
}

export function getAccessToken() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STORAGE_KEYS.accessToken);
}

export function getTokenType() {
  if (typeof window === "undefined") return "bearer";
  return window.localStorage.getItem(STORAGE_KEYS.tokenType) || "bearer";
}

export function getUserName() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STORAGE_KEYS.userName);
}

export function getUserId() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STORAGE_KEYS.userId);
}

export function getUserGender() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(STORAGE_KEYS.userGender);
}

export function getAuthHeaders() {
  const token = getAccessToken();
  const tokenType = getTokenType();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
