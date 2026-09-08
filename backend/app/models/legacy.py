"""Modelos SQLAlchemy para as tabelas legadas (ativos/monitoramento), que até
agora só existiam como SQL cru espalhado em vários módulos (veja o histórico
de app/core/legacy_db.py). Mapeiam exatamente o schema que já existe no banco
-- criado originalmente por database.py (agente/servidor.py) -- sem renomear
nem alterar nenhuma coluna, então não muda nada nos dados existentes.

'comandos'/'comando_templates' (fila de comandos remotos) e
'ativos_excluidos' continuam de fora por enquanto -- ficam pra uma etapa
seguinte, escopo separado.
"""

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Ativo(Base):
    __tablename__ = "ativos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    categoria: Mapped[str | None] = mapped_column(String)
    numero_serie: Mapped[str | None] = mapped_column(String)
    status: Mapped[str | None] = mapped_column(String)
    responsavel: Mapped[str | None] = mapped_column(String)
    localizacao: Mapped[str | None] = mapped_column(String)
    observacoes: Mapped[str | None] = mapped_column(Text)
    # Campos de vínculo (COLUNAS_VINCULO em database.py) -- adicionados numa
    # migração manual (ALTER TABLE) depois da criação original da tabela.
    patrimonio: Mapped[str | None] = mapped_column(String)
    usuario: Mapped[str | None] = mapped_column(String)
    modelo_monitor: Mapped[str | None] = mapped_column(String)
    patrimonio_monitor: Mapped[str | None] = mapped_column(String)


class Monitoramento(Base):
    __tablename__ = "monitoramento"

    # numero_serie é a chave primária de verdade nesta tabela (upsert por
    # ON CONFLICT em database.py::salvar_monitoramento) -- não tem coluna id.
    numero_serie: Mapped[str] = mapped_column(String, primary_key=True)
    modelo: Mapped[str | None] = mapped_column(String)
    sistema_operacional: Mapped[str | None] = mapped_column(String)
    armazenamento_total_gb: Mapped[float | None] = mapped_column(Float)
    armazenamento_usado_gb: Mapped[float | None] = mapped_column(Float)
    armazenamento_livre_gb: Mapped[float | None] = mapped_column(Float)
    uso_cpu_percent: Mapped[float | None] = mapped_column(Float)
    uso_memoria_percent: Mapped[float | None] = mapped_column(Float)
    uso_disco_percent: Mapped[float | None] = mapped_column(Float)
    rede_enviado_mb: Mapped[float | None] = mapped_column(Float)
    rede_recebido_mb: Mapped[float | None] = mapped_column(Float)
    # Guardado como texto ISO (datetime.now().isoformat()), não como
    # DATETIME de verdade -- mantém o mesmo formato que o agente já grava,
    # pra não precisar converter nada dos dados existentes.
    ultima_atualizacao: Mapped[str | None] = mapped_column(String)
    patrimonio: Mapped[str | None] = mapped_column(String)
    usuario: Mapped[str | None] = mapped_column(String)
    modelo_monitor: Mapped[str | None] = mapped_column(String)
    patrimonio_monitor: Mapped[str | None] = mapped_column(String)
    fila_pendente_local: Mapped[int | None] = mapped_column(Integer, default=0)
    memoria_total_gb: Mapped[float | None] = mapped_column(Float)
    memoria_usada_gb: Mapped[float | None] = mapped_column(Float)
