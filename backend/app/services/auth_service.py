# 회원가입, 로그인, 토큰 발급/검증 등 사용자 인증 관련 핵심 로직을 담당하는 모듈.
# 비밀번호는 절대 원문으로 저장하지 않고 PBKDF2 알고리즘으로 암호화해 보관합니다.
# 로그인 성공 시 발급되는 토큰은 DB 없이 서명만으로 사용자를 식별할 수 있는 구조입니다.

import hashlib
import hmac
import json
import os
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Optional

from sqlalchemy.orm import Session

from app.core.database import User
from app.core.config import settings


# 회원가입, 로그인, 토큰 관련 모든 인증 기능을 모아놓은 클래스.
# 외부에서 직접 인스턴스화하지 않고 클래스 메서드(@classmethod)로 사용합니다.
class AuthService:
    """회원가입/로그인 관련 도메인 로직."""

    PBKDF2_ITERATIONS = 120_000
    TOKEN_VERSION = "v1"

    # 전화번호에서 숫자만 추출하여 하이픈 입력 여부와 무관하게 저장/비교합니다.
    # 매개변수: phone_number - 사용자가 입력한 전화번호 문자열
    # 반환값: 숫자만 남긴 전화번호 문자열
    @staticmethod
    def _normalize_phone(phone_number: str) -> str:
        # 숫자만 남겨 저장하면 하이픈 입력 여부와 무관하게 로그인 가능
        return "".join(ch for ch in phone_number if ch.isdigit())

    # 로그인 아이디의 앞뒤 공백을 제거하고 소문자로 통일합니다.
    # 매개변수: login_id - 사용자가 입력한 아이디 문자열
    # 반환값: 공백 제거 및 소문자 변환된 아이디
    @staticmethod
    def _normalize_login_id(login_id: str) -> str:
        return login_id.strip().lower()

    # 비밀번호를 안전하게 암호화하여 저장 가능한 문자열로 변환합니다.
    # 무작위 salt와 12만 회 반복 해시를 적용해 공격을 어렵게 만듭니다.
    # 매개변수: raw_password - 사용자가 입력한 원문 비밀번호
    # 반환값: "pbkdf2_sha256$반복횟수$salt$해시값" 형태의 문자열
    @classmethod
    def _hash_password(cls, raw_password: str) -> str:
        # [핵심] 원문 비밀번호 저장 금지: salt + 반복 해시로 저장
        # 형식: pbkdf2_sha256$iterations$salt_hex$digest_hex
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            raw_password.encode("utf-8"),
            salt,
            cls.PBKDF2_ITERATIONS,
        )
        return (
            f"pbkdf2_sha256${cls.PBKDF2_ITERATIONS}$"
            f"{salt.hex()}${digest.hex()}"
        )

    # 사용자가 입력한 비밀번호와 저장된 암호화 비밀번호가 일치하는지 검증합니다.
    # 타이밍 공격을 막기 위해 hmac.compare_digest를 사용합니다.
    # 매개변수: raw_password - 입력된 원문 비밀번호 / encoded - DB에 저장된 암호화 문자열
    # 반환값: 일치 여부 (True/False)
    @classmethod
    def _verify_password(cls, raw_password: str, encoded: str) -> bool:
        try:
            algo, iter_str, salt_hex, digest_hex = encoded.split("$")
            if algo != "pbkdf2_sha256":
                return False
            iterations = int(iter_str)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
        except Exception:
            return False

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            raw_password.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(actual, expected)

    # 새 사용자를 등록합니다.
    # 아이디 또는 전화번호가 이미 존재하면 ValueError를 발생시킵니다.
    # 매개변수: db - 데이터베이스 세션 / login_id, user_name, phone_number, gender, password - 가입 정보
    # 반환값: 생성된 User 객체
    @classmethod
    def register(
        cls,
        db: Session,
        *,
        login_id: str,
        user_name: str,
        phone_number: str,
        gender: str,
        password: str,
    ) -> User:
        normalized_login_id = cls._normalize_login_id(login_id)
        normalized_phone = cls._normalize_phone(phone_number)
        login_exists = db.query(User).filter(User.login_id == normalized_login_id).first()
        if login_exists:
            raise ValueError("이미 사용 중인 로그인 아이디입니다.")
        exists = db.query(User).filter(User.phone_number == normalized_phone).first()
        if exists:
            raise ValueError("이미 등록된 전화번호입니다.")

        user = User(
            login_id=normalized_login_id,
            user_name=user_name.strip(),
            phone_number=normalized_phone,
            gender=gender,  # [성별 추가] 프론트에서 선택한 M/F를 그대로 저장
            password_hash=cls._hash_password(password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    # 아이디와 비밀번호로 로그인을 시도합니다.
    # 매개변수: db - 데이터베이스 세션 / login_id - 사용자 아이디 / password - 입력 비밀번호
    # 반환값: 로그인 성공 시 User 객체, 실패 시 None
    @classmethod
    def login(cls, db: Session, *, login_id: str, password: str) -> Optional[User]:
        normalized_login_id = cls._normalize_login_id(login_id)
        user = db.query(User).filter(User.login_id == normalized_login_id).first()
        if not user:
            return None
        if not cls._verify_password(password, user.password_hash):
            return None
        return user

    # 사용자 ID로 사용자 정보를 조회합니다.
    # 매개변수: db - 데이터베이스 세션 / user_id - 조회할 사용자의 고유 번호
    # 반환값: User 객체 또는 존재하지 않으면 None
    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
        return db.query(User).filter(User.user_id == user_id).first()

    # 바이트 데이터를 URL 안전 Base64 문자열로 인코딩합니다.
    @staticmethod
    def _b64url_encode(raw: bytes) -> str:
        return urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    # URL 안전 Base64 문자열을 바이트 데이터로 디코딩합니다.
    @staticmethod
    def _b64url_decode(raw: str) -> bytes:
        padding = "=" * ((4 - len(raw) % 4) % 4)
        return urlsafe_b64decode((raw + padding).encode("ascii"))

    # 로그인한 사용자에게 발급할 인증 토큰을 생성합니다.
    # 토큰에는 사용자 ID와 만료 시간이 포함되며, 서버 비밀키로 서명합니다.
    # 매개변수: user_id - 토큰에 포함할 사용자 고유 번호
    # 반환값: "버전.페이로드.서명" 형태의 인증 토큰 문자열
    @classmethod
    def create_access_token(cls, user_id: int) -> str:
        # [핵심] stateless 토큰: DB 조회 없이 서명 검증만으로 사용자 식별 가능
        payload = {
            "sub": user_id,
            "exp": int(time.time()) + settings.auth_token_ttl_seconds,
        }
        payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
        payload_b64 = cls._b64url_encode(payload_json)
        signature = hmac.new(
            settings.auth_secret_key.encode("utf-8"),
            payload_b64.encode("ascii"),
            hashlib.sha256,
        ).digest()
        sig_b64 = cls._b64url_encode(signature)
        return f"{cls.TOKEN_VERSION}.{payload_b64}.{sig_b64}"

    # 전달받은 인증 토큰의 버전, 서명, 만료 여부를 순서대로 검증합니다.
    # 모든 검증을 통과하면 토큰에 담긴 사용자 ID를 반환합니다.
    # 매개변수: token - 클라이언트에서 전달한 인증 토큰 문자열
    # 반환값: 유효한 토큰이면 사용자 ID(int), 그렇지 않으면 None
    @classmethod
    def verify_access_token(cls, token: str) -> Optional[int]:
        # [핵심] 버전/서명/만료 모두 검증 후 사용자 ID만 반환
        try:
            version, payload_b64, sig_b64 = token.split(".", 2)
            if version != cls.TOKEN_VERSION:
                return None

            expected_sig = hmac.new(
                settings.auth_secret_key.encode("utf-8"),
                payload_b64.encode("ascii"),
                hashlib.sha256,
            ).digest()
            actual_sig = cls._b64url_decode(sig_b64)
            if not hmac.compare_digest(expected_sig, actual_sig):
                return None

            payload_raw = cls._b64url_decode(payload_b64)
            payload = json.loads(payload_raw.decode("utf-8"))
            if int(payload.get("exp", 0)) < int(time.time()):
                return None
            return int(payload["sub"])
        except Exception:
            return None
