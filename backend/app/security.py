from datetime import datetime, timedelta
from jose import JWTError, jwt
from cryptography.fernet import Fernet
import base64
import hashlib
from app.config import settings


def create_jwt(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_jwt(token: str) -> str:
    """Returns user_id (sub) or raises JWTError."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    user_id = payload.get("sub")
    if not user_id:
        raise JWTError("Missing sub")
    return user_id


def _fernet() -> Fernet:
    # Derive a 32-byte Fernet key from SECRET_KEY
    key = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()
