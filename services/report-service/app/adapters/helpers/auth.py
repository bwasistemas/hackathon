"""JWT verification helpers.

The report-service does not issue tokens — that responsibility belongs to the
upload-service. This module only validates incoming tokens using the shared
`JWT_SECRET_KEY`.
"""
from jose import JWTError, jwt

from app.adapters.inbound.schemas import TokenData
from app.config import load_settings

_settings = load_settings()
SECRET_KEY = _settings.jwt_secret_key
ALGORITHM = _settings.jwt_algorithm


def verify_token(token: str, credentials_exception):
    """Verify and decode a JWT token issued by the upload-service."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise credentials_exception
        return TokenData(username=username)
    except JWTError as exc:
        raise credentials_exception from exc
