"""Modelos SQLAlchemy para as tabelas legadas (ativos/monitoramento), que até
agora só existiam como SQL cru espalhado em vários módulos (veja o histórico
de app/core/legacy_db.py). Mapeiam exatamente o schema que já existe no banco
-- criado originalmente por database.py (agente/servidor.py) -- sem renomear
nem alterar nenhuma coluna, então não muda nada nos dados existentes.

'ativos_excluidos' continua de fora por enquanto (só usada pelo agente/
database.py, nunca pelo backend) -- fica pra uma etapa seguinte, escopo
separado.
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


class Comando(Base):
    __tablename__ = "comandos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    numero_serie: Mapped[str] = mapped_column(String, nullable=False)
    comando: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pendente")
    resultado: Mapped[str | None] = mapped_column(Text)
    codigo_saida: Mapped[int | None] = mapped_column(Integer)
    criado_por: Mapped[str | None] = mapped_column(String)
    # Guardado como texto ISO (datetime.now().isoformat()), mesmo padrão de
    # Monitoramento.ultima_atualizacao -- não converte os dados existentes.
    criado_em: Mapped[str] = mapped_column(String, nullable=False)
    executado_em: Mapped[str | None] = mapped_column(String)
    # Colunas adicionadas depois via ALTER TABLE (COLUNAS_COMANDOS_EXTRA em
    # database.py) -- 'modo' pode vir NULL em comandos antigos, tratado como
    # 'usuario' na leitura (mesma regra de _row_to_command, que existia
    # antes desta migração pra ORM).
    agendado_para: Mapped[str | None] = mapped_column(String)
    modo: Mapped[str | None] = mapped_column(String)


class ComandoTemplate(Base):
    __tablename__ = "comando_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    comando: Mapped[str] = mapped_column(Text, nullable=False)
    criado_por: Mapped[str | None] = mapped_column(String)
    criado_em: Mapped[str] = mapped_column(String, nullable=False)
