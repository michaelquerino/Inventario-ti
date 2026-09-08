from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def _repo_root() -> Path:
    # backend/app/db/backup_session.py -> repo root
    return Path(__file__).resolve().parents[3]


# O histórico de backups vive num banco próprio (backup_meta.db), separado de
# ativos.db/inventario.db, justamente porque esses dois são o alvo de
# importação/restauração: se o histórico morasse dentro de inventario.db, um
# restore apagaria (ou corromperia, em pleno voo) o próprio registro do
# backup de segurança que protege essa operação.
BACKUP_DB_PATH = _repo_root() / "backup_meta.db"
backup_engine = create_engine(
    f"sqlite:///{BACKUP_DB_PATH.as_posix()}",
    future=True,
    connect_args={"check_same_thread": False},
)
BackupSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=backup_engine)
BackupBase = declarative_base()
