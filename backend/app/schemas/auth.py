from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    # 프론트 입력값과 1:1 매핑되는 회원가입 요청 스키마
    login_id: str = Field(..., min_length=4, max_length=50)
    user_name: str = Field(..., min_length=1, max_length=100)
    phone_number: str = Field(..., min_length=4, max_length=20)
    password: str = Field(..., min_length=4, max_length=128)


class LoginRequest(BaseModel):
    # 로그인은 login_id + 비밀번호 조합을 기본으로 사용
    login_id: str = Field(..., min_length=4, max_length=50)
    password: str = Field(..., min_length=4, max_length=128)


class AuthResponse(BaseModel):
    # 프론트 연동을 위해 사용자 정보 + 액세스 토큰을 함께 반환
    user_id: int
    login_id: str
    user_name: str
    phone_number: str
    access_token: str
    token_type: str = "bearer"
