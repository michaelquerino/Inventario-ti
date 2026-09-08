import sqlite3
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.core.legacy_db import repo_root as _repo_root
from app.db.backup_session import BackupSessionLocal
from app.db.session import engine
from app.models.backup_log import BackupLog

LEGACY_DB_FILES = ("ativos.db", "inventario.db")


def _backup_dir() -> Path:
    backup_dir = _repo_root() / "backups"
    backup_dir.mkdir(exist_ok=True)
    return backup_dir


def _sqlite_snapshot(origem: Path, destino: Path, tentativas: int = 3) -> None:
    """Usa a Online Backup API do sqlite3 pra copiar o banco de forma consistente
    mesmo enquanto ele está sendo escrito por outro processo (servidor.py/backend).
    Também serve para restaurar: quando 'origem' é o backup e 'destino' é o banco
    ao vivo, a API sobrescreve o conteúdo do destino com o do backup."""
    for tentativa in range(1, tentativas + 1):
        origem_conn = sqlite3.connect(str(origem))
        destino_conn = sqlite3.connect(str(destino))
        try:
            origem_conn.backup(destino_conn)
            return
        except sqlite3.OperationalError:
            if tentativa == tentativas:
                raise
            time.sleep(0.5 * tentativa)
        finally:
            destino_conn.close()
            origem_conn.close()


def _prune_old_backups(retention_count: int) -> None:
    with BackupSessionLocal() as db:
        logs_sucesso = list(
            db.scalars(
                select(BackupLog)
                .where(BackupLog.status == "sucesso")
                .order_by(BackupLog.started_at.desc())
            ).all()
        )
        repo_root = _repo_root()
        for log in logs_sucesso[retention_count:]:
            if log.file_path:
                caminho = repo_root / log.file_path
                caminho.unlink(missing_ok=True)
            db.delete(log)
        db.commit()


def run_backup(
    *,
    triggered_by: str,
    triggered_by_email: str | None = None,
    retention_count: int = 30,
) -> BackupLog:
    repo_root = _repo_root()
    started_at = datetime.now()

    with BackupSessionLocal() as db:
        log = BackupLog(
            started_at=started_at,
            status="em_andamento",
            triggered_by=triggered_by,
            triggered_by_email=triggered_by_email,
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        stamp = started_at.strftime("%Y%m%d_%H%M%S")
        zip_path = _backup_dir() / f"backup_{stamp}.zip"

        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                incluidos = []
                for nome in LEGACY_DB_FILES:
                    origem = repo_root / nome
                    if not origem.exists():
                        continue
                    destino = tmp_path / nome
                    _sqlite_snapshot(origem, destino)
                    incluidos.append(destino)

                if not incluidos:
                    raise RuntimeError("Nenhum banco de dados encontrado para backup")

                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for arquivo in incluidos:
                        zf.write(arquivo, arquivo.name)

            log.status = "sucesso"
            log.file_path = str(zip_path.relative_to(repo_root))
            log.size_bytes = zip_path.stat().st_size
            log.message = f"{len(incluidos)} banco(s) incluído(s): {', '.join(a.name for a in incluidos)}"
        except Exception as exc:
            log.status = "erro"
            log.message = str(exc)[:2000]
            zip_path.unlink(missing_ok=True)
        finally:
            log.finished_at = datetime.now()
            db.commit()
            db.refresh(log)

        # captura os valores antes de sair do "with" (fechar a sessão expira os
        # atributos do objeto, e o chamador só precisa dos dados, não do ORM object)
        db.expunge(log)

    _prune_old_backups(retention_count)
    return log


def list_backups(limit: int = 100) -> list[BackupLog]:
    with BackupSessionLocal() as db:
        statement = select(BackupLog).order_by(BackupLog.started_at.desc()).limit(limit)
        logs = list(db.scalars(statement).all())
        db.expunge_all()
        return logs


def get_backup(backup_id: int) -> BackupLog | None:
    with BackupSessionLocal() as db:
        log = db.get(BackupLog, backup_id)
        if log is not None:
            db.expunge(log)
        return log


def restore_from_zip(
    zip_path: Path,
    *,
    triggered_by_email: str | None,
    retention_count: int = 30,
) -> dict:
    """Restaura ativos.db e/ou inventario.db a partir de um zip de backup exportado
    por esta mesma tela. Sempre tira um backup de segurança do estado atual antes
    de sobrescrever qualquer coisa, para dar pra desfazer em caso de engano.

    O histórico de backups (BackupLog) mora num banco separado (backup_meta.db)
    justamente para sobreviver a essa restauração: se ele estivesse dentro de
    inventario.db, restaurar inventario.db apagaria o próprio registro do
    backup de segurança que acabou de ser criado para proteger a operação."""
    repo_root = _repo_root()

    if not zipfile.is_zipfile(zip_path):
        raise ValueError("Arquivo enviado não é um .zip válido")

    with zipfile.ZipFile(zip_path) as zf:
        nomes_no_zip = {Path(nome).name for nome in zf.namelist()}
        presentes = [nome for nome in LEGACY_DB_FILES if nome in nomes_no_zip]
        if not presentes:
            raise ValueError("O arquivo não contém ativos.db nem inventario.db")

        backup_seguranca = run_backup(
            triggered_by="seguranca_pre_importacao",
            triggered_by_email=triggered_by_email,
            retention_count=retention_count,
        )

        restaurados: list[str] = []
        falhas: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for nome in presentes:
                extraido = Path(zf.extract(nome, tmp_path))
                destino = repo_root / nome
                try:
                    if nome == "inventario.db":
                        # fecha as conexões em pool do backend antes de sobrescrever
                        # o arquivo, senão a restauração pode ficar travada esperando lock
                        engine.dispose()
                    _sqlite_snapshot(extraido, destino)
                    restaurados.append(nome)
                except Exception as exc:
                    falhas.append(f"{nome}: {exc}")

    return {
        "safety_backup_id": backup_seguranca.id,
        "restored": restaurados,
        "failed": falhas,
    }
