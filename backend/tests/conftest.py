from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import settings
from app.core.security import create_access_token
from app.crud.user import create_user, get_by_email
from app.db.base import Base
from app.main import create_app
from app.schemas.user import UserCreate


@pytest.fixture(scope="session", autouse=True)
def allow_public_register() -> Generator[None, None, None]:
    # Produção roda em modo single-admin (cadastro público desligado, veja
    # api/routes/auth.py) -- os testes de registro/RBAC abaixo precisam criar
    # usuários extras pelo endpoint público pra exercitar o fluxo real de
    # ponta a ponta, então ligamos só durante a suíte e devolvemos o valor
    # original depois, sem tocar no padrão de produção.
    original = settings.single_admin_mode
    settings.single_admin_mode = False
    yield
    settings.single_admin_mode = original


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session")
def session_factory(test_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def seed_admin_user(session_factory) -> None:
    db: Session = session_factory()
    try:
        existing = get_by_email(db, "ti@corpori.com.br")
        if existing is None:
            create_user(
                db,
                UserCreate(
                    email="ti@corpori.com.br",
                    full_name="Administrador Corpori",
                    role="admin",
                    is_active=True,
                    password="CorporiSST",
                ),
            )
    finally:
        db.close()


@pytest.fixture()
def db_session(session_factory) -> Generator[Session, None, None]:
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(session_factory) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture()
def admin_token() -> str:
    return create_access_token("ti@corpori.com.br")
