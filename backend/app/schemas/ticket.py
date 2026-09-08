from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

TICKET_STATUSES = {"aberto", "em_andamento", "concluido"}


class TicketCreate(BaseModel):
    numero_serie: str | None = None
    usuario: str | None = None
    patrimonio: str | None = None
    titulo: str
    descricao: str
    categoria: str | None = None

    @field_validator("titulo", "descricao")
    @classmethod
    def _nao_vazio(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("não pode ser vazio")
        return value


class TicketUpdate(BaseModel):
    status: str | None = None
    resposta: str | None = None

    @field_validator("status")
    @classmethod
    def _status_valido(cls, value: str | None) -> str | None:
        if value is not None and value not in TICKET_STATUSES:
            raise ValueError(f"status deve ser um de: {', '.join(sorted(TICKET_STATUSES))}")
        return value


class TicketRead(BaseModel):
    id: int
    numero_serie: str | None = None
    usuario: str | None = None
    patrimonio: str | None = None
    titulo: str
    descricao: str
    categoria: str | None = None
    status: str
    resposta: str | None = None
    respondido_por: str | None = None
    criado_em: datetime
    atualizado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
