from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    # API 레이어는 입력 검증/오류코드 변환만 담당하고 실제 로직은 서비스로 위임
    try:
        user = AuthService.register(
            db,
            login_id=payload.login_id,
            user_name=payload.user_name,
            phone_number=payload.phone_number,
            password=payload.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # [핵심] 회원가입 직후 바로 인증 상태를 만들 수 있도록 access token을 함께 발급
    access_token = AuthService.create_access_token(user.user_id)
    return AuthResponse(
        user_id=user.user_id,
        login_id=user.login_id,
        user_name=user.user_name,
        phone_number=user.phone_number,
        access_token=access_token,
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = AuthService.login(
        db,
        login_id=payload.login_id,
        password=payload.password,
    )
    if not user:
        raise HTTPException(status_code=401, detail="로그인 아이디 또는 비밀번호가 올바르지 않습니다.")

    # [핵심] 로그인 성공 시 보호된 API 접근용 Bearer 토큰 발급
    access_token = AuthService.create_access_token(user.user_id)
    return AuthResponse(
        user_id=user.user_id,
        login_id=user.login_id,
        user_name=user.user_name,
        phone_number=user.phone_number,
        access_token=access_token,
    )
