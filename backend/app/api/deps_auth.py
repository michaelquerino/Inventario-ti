from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jwt import InvalidTokenError

from app.api.deps import get_db
from app.core.security import decode_access_token
from app.crud.user import get_by_email
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    try:
        payload = decode_access_token(token)
        email = payload.get("sub")
        if not email:
            raise ValueError("Token sem subject")
    except (InvalidTokenError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido") from exc

    user = get_by_email(db, email)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário inválido")
    return user


def require_roles(*roles: str):
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if roles and current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permissão negada")
        return current_user

    return dependency
