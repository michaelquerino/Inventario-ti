from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import require_roles
from app.core.audit_utils import get_client_ip, get_user_agent
from app.core.rate_limit import limiter
from app.crud import audit_log
from app.crud import ticket as ticket_crud
from app.schemas.ticket import TicketCreate, TicketRead, TicketUpdate

router = APIRouter()


# Sem autenticação de propósito: qualquer funcionário deve conseguir abrir um
# chamado só acessando a página, sem login. A identificação de qual notebook
# está abrindo (numero_serie/usuario/patrimonio) vem do agente local rodando
# na própria máquina, não de uma sessão autenticada -- ver o endpoint local
# de identidade exposto pelo agente.
@router.post("", response_model=TicketRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def create_ticket(
    request: Request,
    payload: TicketCreate,
    db: Session = Depends(get_db),
) -> TicketRead:
    ticket = ticket_crud.create_ticket(db, payload)

    audit_log.create_event(
        db,
        actor_email=payload.usuario or payload.numero_serie or "chamado-anonimo",
        action="ticket.create",
        entity_type="ticket",
        entity_id=str(ticket.id),
        details=payload.titulo,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    return ticket


@router.get("", response_model=list[TicketRead])
@limiter.limit("60/minute")
def list_tickets(
    request: Request,
    status_filtro: str | None = None,
    db: Session = Depends(get_db),
    _current_user=Depends(require_roles("admin", "manager", "viewer")),
) -> list[TicketRead]:
    return ticket_crud.list_tickets(db, status=status_filtro)


@router.get("/{ticket_id}", response_model=TicketRead)
@limiter.limit("60/minute")
def get_ticket(
    request: Request,
    ticket_id: int,
    db: Session = Depends(get_db),
    _current_user=Depends(require_roles("admin", "manager", "viewer")),
) -> TicketRead:
    ticket = ticket_crud.get_ticket(db, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chamado não encontrado")
    return ticket


@router.patch("/{ticket_id}", response_model=TicketRead)
@limiter.limit("30/minute")
def update_ticket(
    request: Request,
    ticket_id: int,
    payload: TicketUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager")),
) -> TicketRead:
    ticket = ticket_crud.get_ticket(db, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chamado não encontrado")

    updated = ticket_crud.update_ticket(db, ticket, payload, respondido_por=current_user.email)

    audit_log.create_event(
        db,
        actor_email=current_user.email,
        action="ticket.update",
        entity_type="ticket",
        entity_id=str(updated.id),
        details=f"status={updated.status}",
        new_values=payload.model_dump(exclude_unset=True),
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    return updated
