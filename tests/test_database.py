"""Testes da camada legada (database.py), usada pelo agente e pelo servidor
Flask -- historicamente sem nenhuma cobertura automatizada. Cada teste roda
contra um SQLite temporário isolado (veja o fixture `banco_isolado` em
conftest.py), nunca contra o inventario.db real.
"""
import sqlite3

import database


def _valor_coluna(numero_serie, tabela, coluna):
    """Lê uma coluna específica direto via SQL, em vez de depender da ordem
    posicional de `SELECT *` (frágil e some de vista quando o schema ganha
    colunas novas via ALTER TABLE, que é como database.py evolui o schema)."""
    conexao = sqlite3.connect(database.NOME_BANCO)
    cursor = conexao.cursor()
    cursor.execute(f"SELECT {coluna} FROM {tabela} WHERE numero_serie = ?", (numero_serie,))
    linha = cursor.fetchone()
    conexao.close()
    return linha[0] if linha else None


def test_adicionar_e_listar_ativo():
    database.criar_tabela()
    database.adicionar_ativo(
        nome="Notebook Teste",
        categoria="Notebook",
        numero_serie="SN-TESTE-1",
        status="Em uso",
        responsavel="Fulano",
        localizacao="Sala 1",
        observacoes="",
    )

    ativos = database.listar_ativos()

    assert len(ativos) == 1
    assert _valor_coluna("SN-TESTE-1", "ativos", "nome") == "Notebook Teste"


def test_atualizar_ativo():
    database.criar_tabela()
    database.adicionar_ativo("Nome Antigo", "Notebook", "SN-1", "Em uso", "Resp", "Loc", "")
    id_ativo = database.listar_ativos()[0][0]

    database.atualizar_ativo(id_ativo, "Nome Novo", "Notebook", "SN-1", "Em uso", "Resp", "Loc", "")

    assert _valor_coluna("SN-1", "ativos", "nome") == "Nome Novo"


def test_excluir_ativo_impede_recriacao_automatica_pelo_monitoramento():
    """Regressão direta do caso do notebook "Desconhecido" resolvido nesta
    sessão: um ativo excluído manualmente não pode voltar sozinho só porque
    o monitoramento reportou de novo a mesma numero_serie -- é exatamente
    esse mecanismo (ativos_excluidos) que faltou funcionar direito antes."""
    database.criar_tabela()
    database.criar_tabela_monitoramento()
    database.adicionar_ativo("Notebook X", "Notebook", "SN-EXCLUIR", "Em uso", "", "", "")
    assert len(database.listar_ativos()) == 1

    id_ativo = database.listar_ativos()[0][0]
    database.excluir_ativo(id_ativo)
    assert database.listar_ativos() == []

    database.salvar_monitoramento(
        {
            "numero_serie": "SN-EXCLUIR",
            "modelo": "Notebook X",
            "sistema_operacional": "Windows 11",
        }
    )

    assert database.listar_ativos() == []


def test_salvar_monitoramento_cria_ativo_correspondente_automaticamente():
    database.criar_tabela()
    database.criar_tabela_monitoramento()

    database.salvar_monitoramento(
        {
            "numero_serie": "SN-NOVO",
            "modelo": "Notebook Novo",
            "sistema_operacional": "Windows 11",
        }
    )

    ativos = database.listar_ativos()
    assert len(ativos) == 1
    assert _valor_coluna("SN-NOVO", "ativos", "nome") == "Notebook Novo"


def test_salvar_monitoramento_e_upsert_nao_duplica_registro():
    database.criar_tabela()
    database.criar_tabela_monitoramento()

    for _ in range(2):
        database.salvar_monitoramento(
            {
                "numero_serie": "SN-UPSERT",
                "modelo": "Notebook",
                "sistema_operacional": "Windows 11",
                "uso_cpu_percentual": 50,
            }
        )

    monitorados = database.listar_numeros_serie_monitorados()
    assert monitorados.count("SN-UPSERT") == 1


def test_sincronizar_vinculo_propaga_para_ativos_e_monitoramento():
    database.criar_tabela()
    database.criar_tabela_monitoramento()
    database.salvar_monitoramento(
        {"numero_serie": "SN-VINC", "modelo": "M", "sistema_operacional": "Windows 11"}
    )

    database.sincronizar_vinculo(
        "SN-VINC",
        patrimonio="0099",
        usuario="Fulano de Tal",
        modelo_monitor="Modelo X",
        patrimonio_monitor="MON-1",
    )

    assert _valor_coluna("SN-VINC", "ativos", "patrimonio") == "0099"
    assert _valor_coluna("SN-VINC", "ativos", "usuario") == "Fulano de Tal"
    assert _valor_coluna("SN-VINC", "monitoramento", "patrimonio") == "0099"
    assert _valor_coluna("SN-VINC", "monitoramento", "usuario") == "Fulano de Tal"


def test_fila_de_comandos_respeita_agendamento_futuro():
    database.criar_tabela_comandos()

    id_imediato = database.enfileirar_comando("SN-CMD", "echo imediato")
    id_futuro = database.enfileirar_comando(
        "SN-CMD", "echo futuro", agendado_para="2099-01-01T00:00:00"
    )

    pendentes = database.listar_comandos_pendentes("SN-CMD")
    ids_pendentes = [comando[0] for comando in pendentes]

    assert id_imediato in ids_pendentes
    assert id_futuro not in ids_pendentes  # agendado bem no futuro, não deve aparecer ainda


def test_ciclo_de_vida_de_um_comando():
    database.criar_tabela_comandos()
    comando_id = database.enfileirar_comando("SN-CMD-2", "echo ok")

    database.marcar_comando_executando(comando_id)
    database.salvar_resultado_comando(comando_id, sucesso=True, codigo_saida=0, resultado="ok")

    historico = database.listar_comandos(numero_serie="SN-CMD-2")
    assert historico[0][3] == "concluido"  # status
    assert historico[0][4] == "ok"  # resultado
