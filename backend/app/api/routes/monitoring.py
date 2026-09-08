from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import require_roles
from app.core.agent_connections import agent_connections
from app.core.audit_utils import compute_diff, get_client_ip, get_user_agent
from app.core.config import settings
from app.core.rate_limit import limiter
from app.crud import asset as asset_crud
from app.crud import audit_log
from app.models.asset import Asset
from app.models.legacy import Ativo, Monitoramento
from app.schemas.monitoring import MonitoringVinculoUpdate

router = APIRouter()


def _primeiro_nao_vazio(*valores: str | None) -> str:
    for valor in valores:
        if valor and valor.strip():
            return valor.strip()
    return ""


@router.get("")
@limiter.limit("120/minute")
def list_monitoring(
    request: Request,
    db: Session = Depends(get_db),
    _current_user=Depends(require_roles("admin", "manager", "viewer")),
) -> list[dict]:
    monitorados = db.scalars(select(Monitoramento).order_by(Monitoramento.ultima_atualizacao.desc())).all()

    # Complementa usuario/responsavel a partir de 'ativos' (mapa em memória em
    # vez de um JOIN em SQL: numero_serie não tem constraint de unicidade
    # nessa tabela, então um JOIN duplicaria a linha do notebook na lista se
    # existissem dois ativos com o mesmo serial -- aqui fica só com o último
    # encontrado).
    ativos_por_serial: dict[str, Ativo] = {}
    for ativo in db.scalars(select(Ativo).where(Ativo.numero_serie.is_not(None))).all():
        if ativo.numero_serie:
            ativos_por_serial[ativo.numero_serie] = ativo

    # A localização e o apelido de usuário vêm da mesma tabela 'assets' usada
    # pela tela de Ativos, para que os dois lugares sempre mostrem o mesmo
    # valor -- e pra não depender do navegador de quem está olhando (antes
    # ficava salvo só no localStorage, então "Fulano" podia aparecer diferente
    # dependendo de qual computador/navegador acessava o painel). sync garante
    # que notebooks recém-descobertos pelo agente já tenham uma linha em
    # 'assets'; edições feitas por aqui nunca são sobrescritas pelo sync.
    asset_crud.sync_assets_from_legacy_database(db)
    location_by_serial: dict[str, str] = {}
    owner_by_serial: dict[str, str] = {}
    for serial, location, owner in db.execute(
        select(Asset.serial_number, Asset.location, Asset.owner).where(Asset.serial_number.is_not(None))
    ).all():
        if location:
            location_by_serial[serial] = location
        if owner:
            owner_by_serial[serial] = owner

    result = []
    for m in monitorados:
        numero_serie = m.numero_serie
        modelo = m.modelo
        ativo = ativos_por_serial.get(numero_serie)
        usuario = _primeiro_nao_vazio(m.usuario, ativo.usuario if ativo else None, ativo.responsavel if ativo else None)
        uso_cpu_percent = m.uso_cpu_percent
        uso_memoria_percent = m.uso_memoria_percent
        uso_disco_percent = m.uso_disco_percent
        armazenamento_total_gb = m.armazenamento_total_gb
        armazenamento_usado_gb = m.armazenamento_usado_gb
        armazenamento_livre_gb = m.armazenamento_livre_gb
        ultima_atualizacao = m.ultima_atualizacao or ""
        fila_pendente_local = m.fila_pendente_local
        memoria_total_gb = m.memoria_total_gb
        memoria_usada_gb = m.memoria_usada_gb

        localizacao = location_by_serial.get(numero_serie) or ""
        # Apelido definido manualmente (assets.owner) tem prioridade sobre o que
        # o agente reportar -- senão o agente reescreveria por cima no próximo
        # relatório periódico, poucos minutos depois de alguém corrigir o nome.
        usuario = owner_by_serial.get(numero_serie) or usuario

        if agent_connections.is_online(numero_serie):
            # Conexão WebSocket aberta agora: fonte de verdade em tempo real,
            # não depende de estimar pela idade do último relatório recebido.
            online_status = "online"
        else:
            # Fallback pra notebooks que ainda não migraram do polling antigo
            # pro WebSocket (ou que estão momentaneamente desconectados).
            online_status = "offline"
            if ultima_atualizacao:
                parsed = None
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
                    try:
                        parsed = datetime.strptime(ultima_atualizacao[:26], fmt)
                        break
                    except ValueError:
                        continue

                if parsed is not None:
                    minutes_since = (datetime.now() - parsed).total_seconds() / 60
                    online_status = "online" if minutes_since <= settings.monitoring_online_window_minutes else "offline"

        result.append(
            {
                "numero_serie": numero_serie,
                "modelo": modelo,
                "usuario": usuario,
                "localizacao": localizacao,
                "uso_cpu_percent": float(uso_cpu_percent or 0),
                "uso_memoria_percent": float(uso_memoria_percent or 0),
                "memoria_total_gb": float(memoria_total_gb or 0),
                "memoria_usada_gb": float(memoria_usada_gb or 0),
                "uso_disco_percent": float(uso_disco_percent or 0),
                "armazenamento_total_gb": float(armazenamento_total_gb or 0),
                "armazenamento_usado_gb": float(armazenamento_usado_gb or 0),
                "armazenamento_livre_gb": float(armazenamento_livre_gb or 0),
                "ultima_atualizacao": ultima_atualizacao,
                "online_status": online_status,
                "fila_pendente_local": int(fila_pendente_local or 0),
            }
        )

    return result


@router.put("/{numero_serie}")
@limiter.limit("30/minute")
def update_monitoring_vinculo(
    request: Request,
    numero_serie: str,
    payload: MonitoringVinculoUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager")),
) -> dict:
    """Atualiza os campos de vínculo (usuário, patrimônio, monitor) de um notebook
    monitorado no banco legado (ativos.db), e a localização na tabela 'assets'
    (a mesma usada pela tela de Ativos, para os dois lugares ficarem sempre iguais)."""
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    legacy_fields = {k: v for k, v in updates.items() if k != "localizacao"}
    old_values: dict[str, str | None] = {}

    if legacy_fields:
        # numero_serie não tem constraint de unicidade em 'ativos' -- se
        # existir mais de um registro com o mesmo serial (dado sujo antigo),
        # o valor "antigo" pro diff vem do primeiro encontrado, mas a
        # atualização é aplicada a todos eles, replicando o comportamento do
        # UPDATE ... WHERE numero_serie = ? de antes (sem LIMIT, afetava
        # todas as linhas correspondentes).
        ativos_rows = list(db.scalars(select(Ativo).where(Ativo.numero_serie == numero_serie)).all())
        ativo_principal = ativos_rows[0] if ativos_rows else None
        monitoramento_row = db.get(Monitoramento, numero_serie)

        if ativo_principal is None and monitoramento_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitoring record not found")

        current_values = {
            "usuario": (ativo_principal.usuario if ativo_principal else None)
            or (monitoramento_row.usuario if monitoramento_row else None),
            "patrimonio": ativo_principal.patrimonio if ativo_principal else None,
            "modelo_monitor": ativo_principal.modelo_monitor if ativo_principal else None,
            "patrimonio_monitor": ativo_principal.patrimonio_monitor if ativo_principal else None,
        }
        old_values.update({key: current_values[key] for key in legacy_fields})

        for ativo in ativos_rows:
            for campo, valor in legacy_fields.items():
                setattr(ativo, campo, valor)
            db.add(ativo)

        if monitoramento_row is not None:
            for campo, valor in legacy_fields.items():
                setattr(monitoramento_row, campo, valor)
            db.add(monitoramento_row)

        db.commit()

    if "localizacao" in updates or "usuario" in updates:
        asset = db.scalars(select(Asset).where(Asset.serial_number == numero_serie)).first()
        if asset is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ativo correspondente não encontrado em Ativos (cadastre-o lá primeiro)",
            )
        if "localizacao" in updates:
            old_values["localizacao"] = asset.location
            asset.location = updates["localizacao"]
        if "usuario" in updates:
            old_values["usuario"] = asset.owner
            asset.owner = updates["usuario"]
        db.add(asset)
        db.commit()

    old_diff, new_diff = compute_diff(old_values, updates)
    audit_log.create_event(
        db,
        actor_email=current_user.email,
        action="monitoring.update",
        entity_type="monitoring",
        entity_id=numero_serie,
        details=numero_serie,
        old_values=old_diff if old_diff else None,
        new_values=new_diff if new_diff else None,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )

    return {"status": "ok"}