from pydantic import BaseModel


class MonitoringVinculoUpdate(BaseModel):
    usuario: str | None = None
    localizacao: str | None = None
    patrimonio: str | None = None
    modelo_monitor: str | None = None
    patrimonio_monitor: str | None = None
