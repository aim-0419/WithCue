# FastAPI 엔드포인트에서 현재 로그인한 사용자를 확인하는 의존성 함수 모음.
# Authorization 헤더의 Bearer 토큰을 검증하고, 유효하면 해당 사용자 객체를 반환한다.
# 로그인이 필수인 API와 선택적인 API 두 가지 경우를 모두 지원한다.

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.database import User, get_db
from app.services.auth_service import AuthService


# 요청 헤더의 Bearer 토큰을 검증하고 인증된 사용자 객체를 반환하는 필수 인증 의존성.
# 토큰이 없거나 유효하지 않으면 즉시 401 오류를 반환한다.
# 매개변수: authorization - "Bearer <토큰>" 형식의 Authorization 헤더 값. db - 데이터베이스 세션.
# 반환값: 인증된 User 객체.
def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """
    간단한 Bearer 토큰 인증 의존성.
    Authorization: Bearer <token> 형식만 허용합니다.
    """
    # [핵심] 보호된 API는 Bearer 토큰 없으면 즉시 401 반환
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 필요합니다.")

    token = authorization.split(" ", 1)[1].strip()
    # [핵심] 토큰 서명/만료를 검증하고 사용자 식별자를 추출
    user_id = AuthService.verify_access_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

    user = AuthService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")

    return user


# 토큰이 있으면 사용자를 검증하고, 없으면 None을 반환하는 선택적 인증 의존성.
# 로그인 사용자와 비로그인 사용자를 모두 허용하는 API에서 사용한다.
# 매개변수: authorization - Authorization 헤더 값 (없어도 됨). db - 데이터베이스 세션.
# 반환값: 인증된 User 객체 또는 None.
def get_optional_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    """
    인증 헤더가 있으면 사용자 검증을 수행하고,
    없으면 None을 반환하는 선택적 인증 의존성.
    """
    # [조현석] 주간 점수 저장/조회는 로그인 사용자와 비로그인 시연 환경을 모두 지원해야 해서 optional 인증 경로를 추가합니다.
    if not authorization:
        return None

    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authorization 헤더 형식이 올바르지 않습니다.")

    token = authorization.split(" ", 1)[1].strip()
    user_id = AuthService.verify_access_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

    user = AuthService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")

    return user
