from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import get_current_user
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security import create_access_token
from app.crud import audit_log, user as user_crud
from app.schemas.auth import LoginRequest, RegisterRequest, Token
from app.schemas.user import UserCreate, UserRead

router = APIRouter()


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def register(request: Request, payload: RegisterRequest, db: Session = Depends(get_db)) -> UserRead:
    if settings.single_admin_mode:
        audit_log.create_event(
            db,
            actor_email=payload.email,
            action="auth.register.blocked",
            entity_type="user",
            entity_id=payload.email,
            details="Tentativa de cadastro bloqueada em modo single-admin.",
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cadastro publico desabilitado neste ambiente (modo single-admin).",
        )

    existing_user = user_crud.get_by_email(db, payload.email)
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="E-mail ja cadastrado")

    created_user = user_crud.create_user(
        db,
        UserCreate(
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password,
            role="viewer",
            is_active=True,
        ),
    )
    audit_log.create_event(
        db,
        actor_email=created_user.email,
        action="auth.register",
        entity_type="user",
        entity_id=str(created_user.id),
    )
    return created_user


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)) -> Token:
    user = user_crud.authenticate(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")

    token = create_access_token(user.email)
    audit_log.create_event(db, actor_email=user.email, action="auth.login", entity_type="user", entity_id=str(user.id))
    return Token(access_token=token)


@router.get("/me", response_model=UserRead)
@limiter.limit("60/minute")
def me(request: Request, current_user=Depends(get_current_user)):
    return current_user
