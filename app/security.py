from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User

password_hash = PasswordHash.recommended()
dummy_hash = password_hash.hash("senha-ficticia-para-comparacao")
bearer = HTTPBearer(auto_error=False)


def create_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    return jwt.encode({"sub": str(user_id), "exp": expires}, get_settings().secret_key, algorithm="HS256")


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    error = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticação necessária", headers={"WWW-Authenticate": "Bearer"})
    if not credentials:
        raise error
    try:
        payload = jwt.decode(credentials.credentials, get_settings().secret_key, algorithms=["HS256"], options={"require": ["exp", "sub"]})
        user_id = int(payload["sub"])
    except (InvalidTokenError, ValueError, TypeError):
        raise error
    user = db.get(User, user_id)
    if not user:
        raise error
    return user
