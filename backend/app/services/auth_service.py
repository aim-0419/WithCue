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


class AuthService:
    """회원가입/로그인 관련 도메인 로직."""

    PBKDF2_ITERATIONS = 120_000
    TOKEN_VERSION = "v1"

    @staticmethod
    def _normalize_phone(phone_number: str) -> str:
        # 숫자만 남겨 저장하면 하이픈 입력 여부와 무관하게 로그인 가능
        return "".join(ch for ch in phone_number if ch.isdigit())

    @staticmethod
    def _normalize_login_id(login_id: str) -> str:
        return login_id.strip().lower()

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

    @classmethod
    def register(
        cls,
        db: Session,
        *,
        login_id: str,
        user_name: str,
        phone_number: str,
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
            password_hash=cls._hash_password(password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @classmethod
    def login(cls, db: Session, *, login_id: str, password: str) -> Optional[User]:
        normalized_login_id = cls._normalize_login_id(login_id)
        user = db.query(User).filter(User.login_id == normalized_login_id).first()
        if not user:
            return None
        if not cls._verify_password(password, user.password_hash):
            return None
        return user

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
        return db.query(User).filter(User.user_id == user_id).first()

    @staticmethod
    def _b64url_encode(raw: bytes) -> str:
        return urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    @staticmethod
    def _b64url_decode(raw: str) -> bytes:
        padding = "=" * ((4 - len(raw) % 4) % 4)
        return urlsafe_b64decode((raw + padding).encode("ascii"))

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
