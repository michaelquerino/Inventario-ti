from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.legacy import Ativo
from app.schemas.asset import AssetCreate, AssetUpdate


LEGACY_STATUS_MAP = {
    "em uso": "active",
    "em estoque": "active",
    "em manutencao": "maintenance",
    "em manutenção": "maintenance",
    "baixado": "retired",
}


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
    """Importa ativos legados (tabela 'ativos') para a tabela da API sem
    duplicar registros. Usa a mesma sessão/conexão de 'assets' -- ambas as
    tabelas vivem no mesmo arquivo físico (inventario.db), então isso deixou
    de ser uma leitura cross-connection via sqlite3 cru."""
    ativos_legados = db.scalars(select(Ativo).order_by(Ativo.id)).all()

    for ativo in ativos_legados:
        legacy_id = ativo.id
        numero_serie = ativo.numero_serie
        status = ativo.status
        patrimonio = ativo.patrimonio
        usuario = ativo.usuario
        modelo_monitor = ativo.modelo_monitor
        patrimonio_monitor = ativo.patrimonio_monitor

        serial = (numero_serie or "").strip() or None
        owner = (usuario or "").strip() or (ativo.responsavel or "").strip() or None
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
                    name=ativo.nome or f"Ativo legado {legacy_id}",
                    category=(ativo.categoria or None),
                    status=_normalize_status(status),
                    serial_number=serial,
                    brand=None,
                    model=(modelo_monitor or None),
                    location=(ativo.localizacao or None),
                    owner=owner,
                    department=None,
                    notes=(ativo.observacoes or None),
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


def _delete_from_legacy_database(db: Session, asset: Asset) -> None:
    """Remove o registro correspondente na tabela 'ativos' -- sem isso, a
    próxima sync_assets_from_legacy_database() (chamada em todo
    list_assets()) recria o ativo excluído, porque ele ainda existe na
    origem legada."""
    if asset.serial_number:
        registros = db.scalars(select(Ativo).where(Ativo.numero_serie == asset.serial_number)).all()
    else:
        registros = db.scalars(select(Ativo).where(Ativo.patrimonio == asset.asset_tag)).all()
    for registro in registros:
        db.delete(registro)


def delete_asset(db: Session, asset: Asset) -> None:
    _delete_from_legacy_database(db, asset)
    db.delete(asset)
    db.commit()
