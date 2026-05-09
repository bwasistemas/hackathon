"""JWT issuance and verification helpers.

The upload-service is the SINGLE source of token issuance for the platform.
Other services (`ai-service`, `report-service`) only verify tokens against the
same `JWT_SECRET_KEY`.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

from app.adapters.inbound.schemas import TokenData
from app.config import load_settings

_settings = load_settings()
SECRET_KEY = _settings.jwt_secret_key
ALGORITHM = _settings.jwt_algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = _settings.jwt_access_token_expire_minutes


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT with `iat`/`exp` claims."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"iat": now, "exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str, credentials_exception) -> TokenData:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise credentials_exception
        return TokenData(username=username)
    except JWTError as exc:
        raise credentials_exception from exc
