# 회원가입, 로그인, 인증 응답에 사용되는 데이터 구조(스키마)를 정의하는 모듈.
# 프론트엔드에서 보내는 요청 데이터의 형식을 검증하고,
# 서버에서 내보내는 응답 데이터의 형태를 고정합니다.

from typing import Literal, Optional

from pydantic import BaseModel, Field


# 회원가입 요청 시 프론트엔드에서 서버로 전달하는 데이터 구조.
# 아이디, 이름, 전화번호, 비밀번호 각각의 최소/최대 길이를 강제합니다.
class RegisterRequest(BaseModel):
    # 프론트 입력값과 1:1 매핑되는 회원가입 요청 스키마
    login_id: str = Field(..., min_length=4, max_length=50)
    user_name: str = Field(..., min_length=1, max_length=100)
    phone_number: str = Field(..., min_length=4, max_length=20)
    # [성별 추가] 남(M)/여(F)만 허용하며, 값이 없으면 기본값 M으로 처리
    gender: Literal["M", "F"] = "M"
    password: str = Field(..., min_length=4, max_length=128)


# 로그인 요청 시 프론트엔드에서 서버로 전달하는 데이터 구조.
# 아이디와 비밀번호만으로 로그인을 시도합니다.
class LoginRequest(BaseModel):
    # 로그인은 login_id + 비밀번호 조합을 기본으로 사용
    login_id: str = Field(..., min_length=4, max_length=50)
    password: str = Field(..., min_length=4, max_length=128)


# 로그인 또는 회원가입 성공 후 서버가 프론트엔드로 반환하는 응답 구조.
# 사용자 기본 정보와 함께 이후 요청에 사용할 인증 토큰을 포함합니다.
class AuthResponse(BaseModel):
    # 프론트 연동을 위해 사용자 정보 + 액세스 토큰을 함께 반환
    user_id: int
    login_id: str
    user_name: str
    phone_number: str
    # [성별 추가] 저장된 성별(M/F)을 응답에 함께 반환
    gender: Optional[str] = None
    access_token: str
    token_type: str = "bearer"
