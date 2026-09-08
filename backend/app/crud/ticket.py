from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ticket import Ticket
from app.schemas.ticket import TicketCreate, TicketUpdate


def create_ticket(db: Session, payload: TicketCreate) -> Ticket:
    ticket = Ticket(**payload.model_dump())
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def list_tickets(db: Session, status: str | None = None) -> list[Ticket]:
    statement = select(Ticket).order_by(Ticket.criado_em.desc())
    if status:
        statement = statement.where(Ticket.status == status)
    return list(db.scalars(statement).all())


def get_ticket(db: Session, ticket_id: int) -> Ticket | None:
    return db.get(Ticket, ticket_id)


def update_ticket(db: Session, ticket: Ticket, payload: TicketUpdate, respondido_por: str | None = None) -> Ticket:
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(ticket, field, value)
    if "resposta" in data and respondido_por:
        ticket.respondido_por = respondido_por
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket
