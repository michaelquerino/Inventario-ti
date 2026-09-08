import sqlite3
import os
import sys
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def _candidatos_banco():
    """Retorna diretórios para procurar o banco de dados, priorizando o projeto atual."""
    candidatos = []
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cwd = os.getcwd()

    if getattr(sys, "frozen", False):
        candidatos.extend([
            cwd,
            os.path.dirname(os.path.abspath(sys.executable)),
            script_dir,
        ])
    else:
        candidatos.extend([cwd, script_dir])

    return [c for c in candidatos if c]


def _resolver_nome_banco():
    """Escolhe o banco existente no projeto, ou cria um novo próximo ao diretório preferido."""
    nomes_prioridade = ["ativos.db", "inventario.db"]
    for base in _candidatos_banco():
        for nome in nomes_prioridade:
            caminho = os.path.join(base, nome)
            if os.path.exists(caminho):
                logger.info("Usando banco de dados existente em %s", caminho)
                return caminho

    base_preferido = _candidatos_banco()[0] if _candidatos_banco() else os.path.dirname(os.path.abspath(__file__))
    os.makedirs(base_preferido, exist_ok=True)
    caminho = os.path.join(base_preferido, "ativos.db")
    logger.info("Criando banco de dados em %s", caminho)
    return caminho


def _resolver_nome_banco_auditoria():
    """Localiza o banco principal da API, onde os logs de auditoria são gravados."""
    for base in _candidatos_banco():
        caminho = os.path.join(base, "inventario.db")
        if os.path.exists(caminho):
            logger.info("Usando banco de auditoria em %s", caminho)
            return caminho

    base_preferido = _candidatos_banco()[0] if _candidatos_banco() else os.path.dirname(os.path.abspath(__file__))
    os.makedirs(base_preferido, exist_ok=True)
    caminho = os.path.join(base_preferido, "inventario.db")
    logger.info("Criando banco de auditoria em %s", caminho)
    return caminho


NOME_BANCO = _resolver_nome_banco()
NOME_BANCO_AUDITORIA = _resolver_nome_banco_auditoria()

def connectar():
    """Conecta ao banco de dados SQLite e retorna a conexão."""
    try:
        return sqlite3.connect(NOME_BANCO)
    except sqlite3.Error as e:
        logger.error(f"Erro ao conectar ao banco de dados: {e}")
        raise


def conectar_auditoria():
    """Conecta ao banco principal que armazena os logs de auditoria."""
    try:
        return sqlite3.connect(NOME_BANCO_AUDITORIA)
    except sqlite3.Error as e:
        logger.error(f"Erro ao conectar ao banco de auditoria: {e}")
        raise

# Campos de vínculo (preenchidos manualmente) presentes em 'ativos' e 'monitoramento'
COLUNAS_VINCULO = [
    ("patrimonio", "TEXT"),
    ("usuario", "TEXT"),
    ("modelo_monitor", "TEXT"),
    ("patrimonio_monitor", "TEXT"),
]

COLUNAS_MONITORAMENTO_EXTRA = [
    ("fila_pendente_local", "INTEGER DEFAULT 0"),
    ("memoria_total_gb", "REAL"),
    ("memoria_usada_gb", "REAL"),
]

ACOES_AUDITORIA_PENDENTE = ("auth.login_failed", "asset.delete")


def criar_tabela_exclusoes():
    """Registra números de série removidos manualmente do inventário."""
    conexao = connectar()
    cursor = conexao.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ativos_excluidos (
            numero_serie TEXT PRIMARY KEY,
            excluido_em TEXT NOT NULL
        )
    """)
    conexao.commit()
    conexao.close()


def remover_exclusao_numero_serie(cursor, numero_serie):
    numero_serie = (numero_serie or "").strip()
    if not numero_serie:
        return
    cursor.execute("DELETE FROM ativos_excluidos WHERE numero_serie = ?", (numero_serie,))


def criar_tabela_resolucoes_auditoria():
    """Registra quais eventos de auditoria pendente ja foram tratados."""
    conexao = conectar_auditoria()
    cursor = conexao.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log_resolutions (
            audit_log_id INTEGER PRIMARY KEY,
            resolved_at TEXT NOT NULL,
            resolved_by TEXT,
            notes TEXT
        )
    """)
    conexao.commit()
    conexao.close()


def _tabela_existe(conexao, nome_tabela):
    cursor = conexao.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (nome_tabela,))
    return cursor.fetchone() is not None


def listar_auditorias_pendentes(limite=100):
    """Retorna eventos de auditoria ainda nao resolvidos."""
    criar_tabela_resolucoes_auditoria()
    conexao = conectar_auditoria()
    if not _tabela_existe(conexao, "audit_logs"):
        conexao.close()
        return []
    cursor = conexao.cursor()
    marcadores = ", ".join("?" for _ in ACOES_AUDITORIA_PENDENTE)
    cursor.execute(
        f"""
        SELECT
            al.id,
            al.created_at,
            al.action,
            al.entity_type,
            al.entity_id,
            al.details,
            al.actor_email,
            al.ip_address
        FROM audit_logs al
        LEFT JOIN audit_log_resolutions ar ON ar.audit_log_id = al.id
        WHERE al.action IN ({marcadores})
          AND ar.audit_log_id IS NULL
        ORDER BY al.created_at DESC
        LIMIT ?
        """,
        (*ACOES_AUDITORIA_PENDENTE, limite),
    )
    resultado = cursor.fetchall()
    conexao.close()
    return resultado


def contar_auditorias_pendentes():
    """Conta eventos de auditoria ainda nao resolvidos."""
    criar_tabela_resolucoes_auditoria()
    conexao = conectar_auditoria()
    if not _tabela_existe(conexao, "audit_logs"):
        conexao.close()
        return 0
    cursor = conexao.cursor()
    marcadores = ", ".join("?" for _ in ACOES_AUDITORIA_PENDENTE)
    cursor.execute(
        f"""
        SELECT COUNT(*)
        FROM audit_logs al
        LEFT JOIN audit_log_resolutions ar ON ar.audit_log_id = al.id
        WHERE al.action IN ({marcadores})
          AND ar.audit_log_id IS NULL
        """,
        ACOES_AUDITORIA_PENDENTE,
    )
    resultado = cursor.fetchone()
    conexao.close()
    return int(resultado[0] if resultado else 0)


def resolver_auditoria_pendente(audit_log_id, resolvido_por="desktop", observacoes=""):
    """Marca um evento de auditoria como tratado sem apagar o historico."""
    criar_tabela_resolucoes_auditoria()
    conexao = conectar_auditoria()
    cursor = conexao.cursor()
    cursor.execute(
        """
        INSERT INTO audit_log_resolutions (audit_log_id, resolved_at, resolved_by, notes)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(audit_log_id) DO UPDATE SET
            resolved_at = excluded.resolved_at,
            resolved_by = excluded.resolved_by,
            notes = excluded.notes
        """,
        (audit_log_id, datetime.now().isoformat(), resolvido_por, observacoes),
    )
    conexao.commit()
    conexao.close()


def resolver_todas_auditorias_pendentes(resolvido_por="desktop", observacoes=""):
    """Marca todas as auditorias pendentes como tratadas."""
    criar_tabela_resolucoes_auditoria()
    pendentes = listar_auditorias_pendentes(limite=10000)
    if not pendentes:
        return 0

    conexao = conectar_auditoria()
    cursor = conexao.cursor()
    timestamp = datetime.now().isoformat()
    for audit_log_id, *_restante in pendentes:
        cursor.execute(
            """
            INSERT INTO audit_log_resolutions (audit_log_id, resolved_at, resolved_by, notes)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(audit_log_id) DO UPDATE SET
                resolved_at = excluded.resolved_at,
                resolved_by = excluded.resolved_by,
                notes = excluded.notes
            """,
            (audit_log_id, timestamp, resolvido_por, observacoes),
        )
    conexao.commit()
    conexao.close()
    return len(pendentes)

def _coluna_existe(cursor, tabela, coluna):
    cursor.execute(f"PRAGMA table_info({tabela})")
    return any(info[1] == coluna for info in cursor.fetchall())

def _garantir_colunas(cursor, tabela, colunas):
    """Migração simples: adiciona colunas que ainda não existem na tabela."""
    for nome_coluna, tipo in colunas:
        if not _coluna_existe(cursor, tabela, nome_coluna):
            cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome_coluna} {tipo}")

def criar_tabela():
    """Cria a tabela 'ativos' no banco de dados, se não existir."""
    conn = connectar()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ativos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            categoria TEXT,
            numero_serie TEXT,
            status TEXT,
            responsavel TEXT,
            localizacao TEXT,
            observacoes TEXT
        )
    ''')
    _garantir_colunas(cursor, "ativos", COLUNAS_VINCULO)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ativos_excluidos (
            numero_serie TEXT PRIMARY KEY,
            excluido_em TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    
def adicionar_ativo(nome, categoria, numero_serie, status, responsavel, localizacao, observacoes,
                     patrimonio="", usuario="", modelo_monitor="", patrimonio_monitor=""):
    criar_tabela_exclusoes()
    conexao = connectar()
    cursor = conexao.cursor()
    remover_exclusao_numero_serie(cursor, numero_serie)
    cursor.execute("""
        INSERT INTO ativos (nome, categoria, numero_serie, status, responsavel, localizacao, observacoes,
                             patrimonio, usuario, modelo_monitor, patrimonio_monitor)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (nome, categoria, numero_serie, status, responsavel, localizacao, observacoes,
          patrimonio, usuario, modelo_monitor, patrimonio_monitor))
    conexao.commit()
    conexao.close()
    
def listar_ativos(filtro="", categoria=None):
    """Retorna os ativos cadastrados, podendo filtrar por texto livre e/ou por categoria exata."""
    conexao = connectar()
    cursor = conexao.cursor()

    condicoes = []
    parametros = []

    if filtro:
        termo = f"%{filtro}%"
        condicoes.append("(nome LIKE ? OR categoria LIKE ? OR responsavel LIKE ? OR numero_serie LIKE ?)")
        parametros.extend([termo, termo, termo, termo])

    if categoria and categoria != "Todos":
        condicoes.append("categoria = ?")
        parametros.append(categoria)

    consulta = "SELECT * FROM ativos"
    if condicoes:
        consulta += " WHERE " + " AND ".join(condicoes)
    consulta += " ORDER BY id DESC"

    cursor.execute(consulta, parametros)
    resultado = cursor.fetchall()
    conexao.close()
    return resultado

def atualizar_ativo(id_ativo, nome, categoria, numero_serie, status, responsavel, localizacao, observacoes,
                     patrimonio="", usuario="", modelo_monitor="", patrimonio_monitor=""):
    """Atualiza os dados de um ativo específico no banco de dados."""
    criar_tabela_exclusoes()
    conexao = connectar()
    cursor = conexao.cursor()
    remover_exclusao_numero_serie(cursor, numero_serie)
    cursor.execute("""
        UPDATE ativos
        SET nome = ?, categoria = ?, numero_serie = ?, status = ?, responsavel = ?, localizacao = ?, observacoes = ?,
            patrimonio = ?, usuario = ?, modelo_monitor = ?, patrimonio_monitor = ?
        WHERE id = ?
    """, (nome, categoria, numero_serie, status, responsavel, localizacao, observacoes,
          patrimonio, usuario, modelo_monitor, patrimonio_monitor, id_ativo))
    conexao.commit()
    conexao.close()

def excluir_ativo(id_ativo):
    """Exclui um ativo específico do banco de dados."""
    criar_tabela_exclusoes()
    conexao = connectar()
    cursor = conexao.cursor()
    cursor.execute("SELECT numero_serie FROM ativos WHERE id = ?", (id_ativo,))
    resultado = cursor.fetchone()
    numero_serie = (resultado[0] if resultado else "") or ""

    if str(numero_serie).strip():
        cursor.execute(
            """
            INSERT INTO ativos_excluidos (numero_serie, excluido_em)
            VALUES (?, ?)
            ON CONFLICT(numero_serie) DO UPDATE SET excluido_em = excluded.excluido_em
            """,
            (numero_serie.strip(), datetime.now().isoformat()),
        )

    cursor.execute("DELETE FROM ativos WHERE id = ?", (id_ativo,))
    conexao.commit()
    conexao.close()
    
def criar_tabela_monitoramento():
    """Cria a tabela de monitoramento, que guarda o último relatório recebido de cada notebook."""
    conexao = connectar()
    cursor = conexao.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitoramento (
            numero_serie TEXT PRIMARY KEY,
            modelo TEXT,
            sistema_operacional TEXT,
            armazenamento_total_gb REAL,
            armazenamento_usado_gb REAL,
            armazenamento_livre_gb REAL,
            uso_cpu_percent REAL,
            uso_memoria_percent REAL,
            uso_disco_percent REAL,
            rede_enviado_mb REAL,
            rede_recebido_mb REAL,
            ultima_atualizacao TEXT
        )
    """)
    _garantir_colunas(cursor, "monitoramento", COLUNAS_VINCULO)
    _garantir_colunas(cursor, "monitoramento", COLUNAS_MONITORAMENTO_EXTRA)
    conexao.commit()
    conexao.close()
    
from datetime import datetime


def salvar_monitoramento(dados):
    """Salva ou atualiza (upsert) o relatório de monitoramento de um notebook."""
    conexao = connectar()
    cursor = conexao.cursor()
    cursor.execute("""
        INSERT INTO monitoramento (
            numero_serie, modelo, sistema_operacional,
            armazenamento_total_gb, armazenamento_usado_gb, armazenamento_livre_gb,
            uso_cpu_percent, uso_memoria_percent, uso_disco_percent,
            rede_enviado_mb, rede_recebido_mb, ultima_atualizacao,
            patrimonio, usuario, patrimonio_monitor, fila_pendente_local,
            memoria_total_gb, memoria_usada_gb
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(numero_serie) DO UPDATE SET
            modelo = excluded.modelo,
            sistema_operacional = excluded.sistema_operacional,
            armazenamento_total_gb = excluded.armazenamento_total_gb,
            armazenamento_usado_gb = excluded.armazenamento_usado_gb,
            armazenamento_livre_gb = excluded.armazenamento_livre_gb,
            uso_cpu_percent = excluded.uso_cpu_percent,
            uso_memoria_percent = excluded.uso_memoria_percent,
            uso_disco_percent = excluded.uso_disco_percent,
            rede_enviado_mb = excluded.rede_enviado_mb,
            rede_recebido_mb = excluded.rede_recebido_mb,
            ultima_atualizacao = excluded.ultima_atualizacao,
            patrimonio = COALESCE(NULLIF(excluded.patrimonio, ''), monitoramento.patrimonio),
            usuario = COALESCE(NULLIF(excluded.usuario, ''), monitoramento.usuario),
                patrimonio_monitor = COALESCE(NULLIF(excluded.patrimonio_monitor, ''), monitoramento.patrimonio_monitor),
                fila_pendente_local = COALESCE(excluded.fila_pendente_local, monitoramento.fila_pendente_local, 0),
                memoria_total_gb = excluded.memoria_total_gb,
                memoria_usada_gb = excluded.memoria_usada_gb
    """, (
        dados.get("numero_serie"),
        dados.get("modelo"),
        dados.get("sistema_operacional"),
        dados.get("disco_total_gb"),
        dados.get("disco_usado_gb"),
        dados.get("disco_livre_gb"),
        dados.get("uso_cpu_percentual"),
        dados.get("uso_memoria_percentual"),
        dados.get("uso_disco_percentual"),
        dados.get("rede_enviado_mb"),
        dados.get("rede_recebido_mb"),
        dados.get("ultima_atualizacao", datetime.now().isoformat()),
        (dados.get("patrimonio") or "").strip(),
        (dados.get("usuario") or "").strip(),
        (dados.get("patrimonio_monitor") or "").strip(),
        int(dados.get("fila_pendente_local") or 0),
        dados.get("memoria_total_gb"),
        dados.get("memoria_usada_gb"),
    ))

    numero_serie = (dados.get("numero_serie") or "").strip()
    patrimonio = (dados.get("patrimonio") or "").strip()
    usuario = (dados.get("usuario") or "").strip()
    patrimonio_monitor = (dados.get("patrimonio_monitor") or "").strip()

    if numero_serie and (patrimonio or usuario or patrimonio_monitor):
        cursor.execute(
            """
            UPDATE ativos
            SET
                patrimonio = COALESCE(NULLIF(?, ''), patrimonio),
                usuario = COALESCE(NULLIF(?, ''), usuario),
                patrimonio_monitor = COALESCE(NULLIF(?, ''), patrimonio_monitor)
            WHERE numero_serie = ?
            """,
            (patrimonio, usuario, patrimonio_monitor, numero_serie),
        )

    conexao.commit()
    conexao.close()
    sincronizar_todos_do_monitoramento()
    sincronizar_vinculos_ativos_para_monitoramento()


def sincronizar_vinculos_ativos_para_monitoramento():
    """Propaga os campos fixos de vínculo cadastrados em 'ativos' para 'monitoramento'."""
    conexao = connectar()
    cursor = conexao.cursor()
    cursor.execute("""
        UPDATE monitoramento
        SET
            patrimonio = COALESCE(
                NULLIF((SELECT a.patrimonio FROM ativos a WHERE a.numero_serie = monitoramento.numero_serie LIMIT 1), ''),
                patrimonio
            ),
            usuario = COALESCE(
                NULLIF((SELECT a.usuario FROM ativos a WHERE a.numero_serie = monitoramento.numero_serie LIMIT 1), ''),
                usuario
            ),
            modelo_monitor = COALESCE(
                NULLIF((SELECT a.modelo_monitor FROM ativos a WHERE a.numero_serie = monitoramento.numero_serie LIMIT 1), ''),
                modelo_monitor
            ),
            patrimonio_monitor = COALESCE(
                NULLIF((SELECT a.patrimonio_monitor FROM ativos a WHERE a.numero_serie = monitoramento.numero_serie LIMIT 1), ''),
                patrimonio_monitor
            )
        WHERE numero_serie IN (
            SELECT numero_serie
            FROM ativos
            WHERE numero_serie IS NOT NULL
              AND TRIM(numero_serie) <> ''
        )
    """)
    conexao.commit()
    conexao.close()


def listar_monitoramento():
    """Retorna todos os registros de monitoramento (um por notebook)."""
    sincronizar_todos_do_monitoramento()
    sincronizar_vinculos_ativos_para_monitoramento()
    conexao = connectar()
    cursor = conexao.cursor()
    cursor.execute("SELECT * FROM monitoramento ORDER BY ultima_atualizacao DESC")
    resultado = cursor.fetchall()
    conexao.close()
    return resultado


def atualizar_vinculo_monitoramento(numero_serie, patrimonio, usuario, modelo_monitor, patrimonio_monitor):
    """Atualiza apenas os dados de vínculo (preenchidos manualmente) de um registro de monitoramento."""
    conexao = connectar()
    cursor = conexao.cursor()
    cursor.execute("""
        UPDATE monitoramento
        SET patrimonio = ?, usuario = ?, modelo_monitor = ?, patrimonio_monitor = ?
        WHERE numero_serie = ?
    """, (patrimonio, usuario, modelo_monitor, patrimonio_monitor, numero_serie))
    conexao.commit()
    conexao.close()


def sincronizar_vinculo(numero_serie, patrimonio, usuario, modelo_monitor, patrimonio_monitor):
    """Atualiza os campos de vínculo (patrimônio, usuário, monitor) tanto em 'ativos' quanto em
    'monitoramento' para o mesmo número de série, mantendo as duas telas sempre iguais."""
    if not numero_serie:
        return
    conexao = connectar()
    cursor = conexao.cursor()
    cursor.execute("""
        UPDATE ativos
        SET patrimonio = ?, usuario = ?, modelo_monitor = ?, patrimonio_monitor = ?
        WHERE numero_serie = ?
    """, (patrimonio, usuario, modelo_monitor, patrimonio_monitor, numero_serie))
    cursor.execute("""
        UPDATE monitoramento
        SET patrimonio = ?, usuario = ?, modelo_monitor = ?, patrimonio_monitor = ?
        WHERE numero_serie = ?
    """, (patrimonio, usuario, modelo_monitor, patrimonio_monitor, numero_serie))
    conexao.commit()
    conexao.close()


def sincronizar_todos_do_monitoramento():
    """Garante que todo computador presente no monitoramento tenha um registro correspondente em 'ativos'.
    Assim, todo item monitorado aparece automaticamente vinculado no inventário."""
    criar_tabela_exclusoes()
    conexao = connectar()
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT numero_serie, modelo, patrimonio, usuario, modelo_monitor, patrimonio_monitor
        FROM monitoramento
    """)
    monitorados = cursor.fetchall()
    for numero_serie, modelo, patrimonio, usuario, modelo_monitor, patrimonio_monitor in monitorados:
        numero_serie_normalizado = (numero_serie or "").strip()
        if not numero_serie_normalizado:
            continue
        cursor.execute("SELECT 1 FROM ativos_excluidos WHERE TRIM(numero_serie) = ?", (numero_serie_normalizado,))
        if cursor.fetchone() is not None:
            continue
        cursor.execute("SELECT id FROM ativos WHERE TRIM(numero_serie) = ?", (numero_serie_normalizado,))
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO ativos (nome, categoria, numero_serie, status, responsavel, localizacao, observacoes,
                                     patrimonio, usuario, modelo_monitor, patrimonio_monitor)
                VALUES (?, 'Notebook', ?, 'Em uso', '', '', '', ?, ?, ?, ?)
            """, (modelo or f"Notebook {numero_serie}", numero_serie,
                  patrimonio, usuario, modelo_monitor, patrimonio_monitor))
    conexao.commit()
    conexao.close()


def listar_numeros_serie_monitorados():
    """Retorna os números de série já registrados no monitoramento, para vincular no inventário."""
    conexao = connectar()
    cursor = conexao.cursor()
    cursor.execute("SELECT numero_serie FROM monitoramento ORDER BY numero_serie")
    resultado = [linha[0] for linha in cursor.fetchall()]
    conexao.close()
    return resultado


# ---------------------------------------------------------------------------
# Comandos remotos: fila de execução no notebook, alimentada pelo painel web
# (somente admin) e consumida pelo agente no checkin periódico.
# ---------------------------------------------------------------------------

COLUNAS_COMANDOS_EXTRA = [
    ("agendado_para", "TEXT"),
    ("modo", "TEXT"),
]


def criar_tabela_comandos():
    """Cria a tabela de comandos remotos, se ainda não existir."""
    conexao = connectar()
    cursor = conexao.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comandos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_serie TEXT NOT NULL,
            comando TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pendente',
            resultado TEXT,
            codigo_saida INTEGER,
            criado_por TEXT,
            criado_em TEXT NOT NULL,
            executado_em TEXT
        )
    """)
    _garantir_colunas(cursor, "comandos", COLUNAS_COMANDOS_EXTRA)
    conexao.commit()
    conexao.close()


def enfileirar_comando(numero_serie, comando, criado_por=None, agendado_para=None, modo="usuario"):
    """Adiciona um comando à fila de um notebook. Retorna o id do comando criado.
    Se agendado_para for informado (ISO datetime), o comando só fica elegível
    para execução a partir desse horário. 'modo' é 'usuario' (padrão, roda como
    o usuário logado) ou 'admin' (roda com privilégio total via tarefa elevada
    registrada no onboarding)."""
    conexao = connectar()
    cursor = conexao.cursor()
    cursor.execute("""
        INSERT INTO comandos (numero_serie, comando, status, criado_por, criado_em, agendado_para, modo)
        VALUES (?, ?, 'pendente', ?, ?, ?, ?)
    """, (numero_serie, comando, criado_por, datetime.now().isoformat(), agendado_para, modo))
    novo_id = cursor.lastrowid
    conexao.commit()
    conexao.close()
    return novo_id


def listar_comandos_pendentes(numero_serie):
    """Retorna os comandos elegíveis para execução agora de um notebook
    (pendentes, sem agendamento ou com horário agendado já alcançado)."""
    conexao = connectar()
    cursor = conexao.cursor()
    cursor.execute("""
        SELECT id, comando, modo FROM comandos
        WHERE numero_serie = ? AND status = 'pendente'
          AND (agendado_para IS NULL OR agendado_para <= ?)
        ORDER BY id ASC
    """, (numero_serie, datetime.now().isoformat()))
    resultado = cursor.fetchall()
    conexao.close()
    return resultado


def marcar_comando_executando(comando_id):
    conexao = connectar()
    cursor = conexao.cursor()
    cursor.execute("UPDATE comandos SET status = 'executando' WHERE id = ?", (comando_id,))
    conexao.commit()
    conexao.close()


def salvar_resultado_comando(comando_id, sucesso, codigo_saida, resultado):
    """Registra o resultado de execução de um comando (sucesso define status concluido/erro)."""
    conexao = connectar()
    cursor = conexao.cursor()
    cursor.execute("""
        UPDATE comandos
        SET status = ?, codigo_saida = ?, resultado = ?, executado_em = ?
        WHERE id = ?
    """, ('concluido' if sucesso else 'erro', codigo_saida, resultado, datetime.now().isoformat(), comando_id))
    conexao.commit()
    conexao.close()


def listar_comandos(numero_serie=None, limite=100):
    """Lista o histórico de comandos, do mais recente para o mais antigo."""
    conexao = connectar()
    cursor = conexao.cursor()
    if numero_serie:
        cursor.execute("""
            SELECT id, numero_serie, comando, status, resultado, codigo_saida, criado_por, criado_em, executado_em, agendado_para, modo
            FROM comandos WHERE numero_serie = ? ORDER BY id DESC LIMIT ?
        """, (numero_serie, limite))
    else:
        cursor.execute("""
            SELECT id, numero_serie, comando, status, resultado, codigo_saida, criado_por, criado_em, executado_em, agendado_para, modo
            FROM comandos ORDER BY id DESC LIMIT ?
        """, (limite,))
    resultado = cursor.fetchall()
    conexao.close()
    return resultado