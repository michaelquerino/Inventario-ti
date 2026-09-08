import sqlite3
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.schemas.asset import AssetCreate, AssetUpdate


LEGACY_STATUS_MAP = {
    "em uso": "active",
    "em estoque": "active",
    "em manutencao": "maintenance",
    "em manutenção": "maintenance",
    "baixado": "retired",
}


def _legacy_db_path() -> Path:
    # backend/app/crud/asset.py -> repo root
    # ativos.db e inventario.db foram unificados num arquivo só -- a tabela
    # 'ativos' (legada) agora mora dentro de inventario.db junto com 'assets'.
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "inventario.db"


def _normalize_status(status: str | None) -> str:
    if not status:
        return "active"
    normalized = status.strip().lower()
    return LEGACY_STATUS_MAP.get(normalized, normalized or "active")


def _build_asset_tag(legacy_id: int, patrimonio: str | None, serial_number: str | None) -> str:
    if patrimonio and patrimonio.strip():
        return patrimonio.strip()
    if serial_number and serial_number.strip():
        return f"SN-{serial_number.strip()}"
    return f"LEGACY-{legacy_id}"


def sync_assets_from_legacy_database(db: Session) -> None:
    """Importa ativos legados (ativos.db) para a tabela da API sem duplicar registros."""
    legacy_db = _legacy_db_path()
    if not legacy_db.exists():
        return

    with sqlite3.connect(legacy_db) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, nome, categoria, numero_serie, status, responsavel, localizacao,
                   observacoes, patrimonio, usuario, modelo_monitor, patrimonio_monitor
            FROM ativos
            ORDER BY id ASC
            """
        )
        rows = cursor.fetchall()

    for row in rows:
        (
            legacy_id,
            nome,
            categoria,
            numero_serie,
            status,
            responsavel,
            localizacao,
            observacoes,
            patrimonio,
            usuario,
            modelo_monitor,
            patrimonio_monitor,
        ) = row

        serial = (numero_serie or "").strip() or None
        owner = (usuario or "").strip() or (responsavel or "").strip() or None
        asset_tag = _build_asset_tag(legacy_id, patrimonio, serial)

        existing = None
        if serial:
            existing = get_by_serial_number(db, serial)
        if existing is None:
            tag_match = get_by_asset_tag(db, asset_tag)
            # Patrimônio duplicado/reaproveitado na base legada pode apontar pra dois
            # notebooks físicos diferentes com o mesmo patrimônio. Se o serial deste
            # registro diverge do serial já vinculado a essa tag, não é o mesmo ativo —
            # tratar como o mesmo aqui faria o segundo dispositivo nunca ganhar linha
            # própria em "assets", deixando o monitoramento dele órfão (numero_serie
            # sem nenhum ativo correspondente na tela). Cria um registro à parte com
            # uma tag temporária baseada no serial, que se autocorrige quando o
            # patrimônio duplicado for corrigido na origem (mesma lógica de placeholder
            # tratada mais abaixo).
            tag_conflita_serial = (
                tag_match is not None
                and serial
                and (tag_match.serial_number or "").strip()
                and tag_match.serial_number != serial
            )
            if tag_conflita_serial:
                asset_tag = _build_asset_tag(legacy_id, None, serial)
            else:
                existing = tag_match

        if existing is None:
            db.add(
                Asset(
                    asset_tag=asset_tag,
                    screen_asset_tag=(patrimonio_monitor or None),
                    name=nome or f"Ativo legado {legacy_id}",
                    category=(categoria or None),
                    status=_normalize_status(status),
                    serial_number=serial,
                    brand=None,
                    model=(modelo_monitor or None),
                    location=(localizacao or None),
                    owner=owner,
                    department=None,
                    notes=(observacoes or None),
                )
            )
            # A sessão roda com autoflush=False (veja app/db/session.py), então sem
            # este flush explícito o SELECT de get_by_asset_tag/get_by_serial_number
            # na próxima iteração não enxerga este INSERT ainda pendente -- dois
            # ativos legados novos com o mesmo patrimônio (dado sujo comum na base
            # legada) então tentam ser inseridos com a mesma asset_tag e o commit no
            # fim da função quebra com IntegrityError, derrubando list_assets() com
            # 500 pra todo mundo.
            db.flush()
        else:
            # Ativos já existentes não são sobrescritos aqui (edições feitas pela API/web
            # são a fonte da verdade) — exceto para preencher campos que ainda estão em
            # branco/no valor gerado automaticamente, para o patrimônio informado depois
            # no agente (ou no cadastro legado) chegar sozinho até a tela de Ativos.
            patrimonio_monitor_normalizado = (patrimonio_monitor or "").strip()
            if patrimonio_monitor_normalizado and not (existing.screen_asset_tag or "").strip():
                existing.screen_asset_tag = patrimonio_monitor_normalizado
                db.add(existing)

            # Patrimônio e número de série são coisas diferentes: a tag nunca deveria
            # ficar igual ao serial (isso só acontece quando foi gerada automaticamente
            # por falta de patrimônio na época). Corrige assim que o patrimônio chegar.
            patrimonio_normalizado = (patrimonio or "").strip()
            tag_e_placeholder = serial and existing.asset_tag in (f"SN-{serial}", serial)
            if patrimonio_normalizado and tag_e_placeholder:
                colisao = get_by_asset_tag(db, patrimonio_normalizado)
                if colisao is None or colisao.id == existing.id:
                    existing.asset_tag = patrimonio_normalizado
                    db.add(existing)

    db.commit()


def list_assets(db: Session) -> list[Asset]:
    sync_assets_from_legacy_database(db)
    statement = select(Asset).order_by(Asset.created_at.desc())
    return list(db.scalars(statement).all())


def get_by_asset_tag(db: Session, asset_tag: str) -> Asset | None:
    statement = select(Asset).where(Asset.asset_tag == asset_tag)
    return db.scalars(statement).first()


def get_by_serial_number(db: Session, serial_number: str) -> Asset | None:
    statement = select(Asset).where(Asset.serial_number == serial_number)
    return db.scalars(statement).first()


def create_asset(db: Session, payload: AssetCreate) -> Asset:
    if payload.serial_number:
        existing = get_by_serial_number(db, payload.serial_number)
        if existing is not None:
            raise ValueError("serial_number already exists")
    asset = Asset(**payload.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def get_asset(db: Session, asset_id: int) -> Asset | None:
    return db.get(Asset, asset_id)


def update_asset(db: Session, asset: Asset, payload: AssetUpdate) -> Asset:
    data = payload.model_dump(exclude_unset=True)
    if "serial_number" in data and data["serial_number"]:
        existing = get_by_serial_number(db, data["serial_number"])
        if existing is not None and existing.id != asset.id:
            raise ValueError("serial_number already exists")
    for field, value in data.items():
        setattr(asset, field, value)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _delete_from_legacy_database(asset: Asset) -> None:
    """Remove o registro correspondente em ativos.db -- sem isso, a próxima
    sync_assets_from_legacy_database() (chamada em todo list_assets()) recria
    o ativo excluído, porque ele ainda existe na origem legada."""
    legacy_db = _legacy_db_path()
    if not legacy_db.exists():
        return

    with sqlite3.connect(legacy_db) as conn:
        if asset.serial_number:
            conn.execute("DELETE FROM ativos WHERE numero_serie = ?", (asset.serial_number,))
        else:
            conn.execute("DELETE FROM ativos WHERE patrimonio = ?", (asset.asset_tag,))
        conn.commit()


def delete_asset(db: Session, asset: Asset) -> None:
    _delete_from_legacy_database(asset)
    db.delete(asset)
    db.commit()
