# 미사용 Frontend 파일 목록

확인 일자: 2026-07-14

아래 파일들은 현재 어디서도 import되지 않거나 정의된 클래스가 실제로 사용되지 않아 삭제 후보입니다.

## 삭제 가능 파일

| 파일 경로 | 미사용 이유 |
|-----------|-------------|
| `frontend/src/App.css` | 어디서도 import되지 않음 |
| `frontend/src/features/exercise/results/components/bodyOverlayShared.js` | 어디서도 import되지 않음 |

## 클래스 미사용 파일 (import는 되어 있으나 내용이 적용 안 됨)

| 파일 경로 | 미사용 이유 |
|-----------|-------------|
| `frontend/src/features/main/pages/MainPage.css` | `MainPage.jsx`에서 import되지만 내부 `.mp-*` 클래스를 실제로 사용하는 컴포넌트가 없음 |
