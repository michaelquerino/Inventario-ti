from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import UserCreate


def get_by_email(db: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    return db.scalars(statement).first()


def list_users(db: Session) -> list[User]:
    statement = select(User).order_by(User.created_at.desc())
    return list(db.scalars(statement).all())


def create_user(db: Session, payload: UserCreate) -> User:
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
        is_active=payload.is_active,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = get_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def enforce_single_admin(db: Session, admin_email: str) -> None:
    users = list_users(db)
    dirty = False

    for user in users:
        should_be_admin = user.email.lower() == admin_email.lower()

        if should_be_admin:
            if user.role != "admin":
                user.role = "admin"
                dirty = True
            if not user.is_active:
                user.is_active = True
                dirty = True
            continue

        if user.is_active:
            user.is_active = False
            dirty = True

    if dirty:
        db.commit()

