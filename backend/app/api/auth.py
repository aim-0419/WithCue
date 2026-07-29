# 회원가입과 로그인 기능을 제공하는 인증 API 라우터.
# 클라이언트로부터 아이디·비밀번호 등을 받아 사용자를 생성하거나 인증하고,
# 이후 보호된 API를 사용할 수 있는 Bearer 토큰을 발급해 반환한다.

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest
from app.services.auth_service import AuthService

router = APIRouter()


# 새로운 사용자를 등록(회원가입)하는 엔드포인트.
# 매개변수: payload - 아이디, 이름, 전화번호, 비밀번호를 담은 요청 바디. db - 데이터베이스 세션.
# 반환값: 생성된 사용자 정보와 즉시 사용 가능한 액세스 토큰.
@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    # API 레이어는 입력 검증/오류코드 변환만 담당하고 실제 로직은 서비스로 위임
    try:
        user = AuthService.register(
            db,
            login_id=payload.login_id,
            user_name=payload.user_name,
            phone_number=payload.phone_number,
            gender=payload.gender,  # [성별 추가] 요청 바디의 성별을 서비스로 전달
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
        gender=user.gender,  # [성별 추가] 저장된 성별을 응답에 포함
        access_token=access_token,
    )


# 기존 사용자를 인증(로그인)하는 엔드포인트.
# 매개변수: payload - 로그인 아이디와 비밀번호. db - 데이터베이스 세션.
# 반환값: 사용자 정보와 API 호출에 사용할 Bearer 액세스 토큰.
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
        gender=user.gender,  # [성별 추가] 저장된 성별을 응답에 포함
        access_token=access_token,
    )
