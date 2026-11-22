import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import now_luanda, settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, role: str, extra: Optional[dict[str, Any]] = None) -> str:
    now = now_luanda()
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[dict[str, Any]]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


def generate_qr_token(card_code: str) -> str:
    """
    Generate a signed server-verifiable QR access credential token.
    The QR token NEVER stores wallet balance; it acts strictly as an identity
    credential linked to the server-side wallet ledger.
    """
    nonce = secrets.token_hex(4).upper()
    body = f"DALALINK:{card_code}:{nonce}"
    sig = hmac.new(
        settings.QR_SIGNING_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:12].upper()
    return f"{body}:{sig}"


def verify_qr_token_signature(qr_token: str) -> Optional[str]:
    """Validate HMAC signature of a QR credential and return card_code if valid."""
    parts = qr_token.strip().split(":")
    if len(parts) != 4 or parts[0] != "DALALINK":
        return None
    body = ":".join(parts[:3])
    expected_sig = hmac.new(
        settings.QR_SIGNING_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:12].upper()
    if hmac.compare_digest(parts[3], expected_sig):
        return parts[1]
    return None
