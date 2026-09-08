from typing import Literal

from pydantic import BaseModel


class CommandCreate(BaseModel):
    numero_series: list[str]
    comando: str
    agendado_para: str | None = None
    modo: Literal["usuario", "admin"] = "usuario"


class CommandRead(BaseModel):
    id: int
    numero_serie: str
    comando: str
    status: str
    resultado: str | None = None
    codigo_saida: int | None = None
    criado_por: str | None = None
    criado_em: str
    executado_em: str | None = None
    agendado_para: str | None = None
    modo: str = "usuario"


class CommandTemplateCreate(BaseModel):
    nome: str
    comando: str


class CommandTemplateRead(BaseModel):
    id: int
    nome: str
    comando: str
    criado_por: str | None = None
    criado_em: str
