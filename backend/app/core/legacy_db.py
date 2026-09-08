"""Ponto único de resolução do caminho do banco de dados legado
(ativos/monitoramento/comandos), usado pelo agente/servidor Flask
(database.py na raiz do repositório) e por vários módulos do backend.

Antes desta consolidação, cada arquivo que precisava desse caminho tinha sua
própria cópia de `Path(__file__).resolve().parents[N])`, com um N diferente
dependendo da profundidade do arquivo dentro de backend/ -- fácil de quebrar
silenciosamente ao mover um arquivo de pasta, e pior: incompleta. Só
considerava 'inventario.db', enquanto database.py::_resolver_nome_banco()
prioriza 'ativos.db' quando ele existe. Um ambiente novo que começasse com
'ativos.db' (é o nome padrão que database.py cria quando nenhum banco ainda
existe) faria o backend silenciosamente usar um 'inventario.db' vazio e
separado, sem nenhum aviso -- a mesma classe de bug (dois bancos
divergentes) que já causou um quase-incidente real neste projeto (a senha de
admin foi atualizada por engano num backend/inventario.db órfão que nunca
tinha sido lido por ninguém). Esta função replica a mesma prioridade de
database.py pros dois lados nunca discordarem sobre qual arquivo é o real.
"""

from pathlib import Path

NOMES_PRIORIDADE = ("ativos.db", "inventario.db")


def repo_root() -> Path:
    # backend/app/core/legacy_db.py -> backend/app/core -> backend/app -> backend -> repo root
    return Path(__file__).resolve().parents[3]


def legacy_db_path() -> Path:
    """Caminho do banco legado, priorizando 'ativos.db' se existir (mesma
    regra de database.py::_resolver_nome_banco) e caindo para
    'inventario.db' -- exista ele ainda ou não -- como padrão."""
    raiz = repo_root()
    for nome in NOMES_PRIORIDADE:
        caminho = raiz / nome
        if caminho.exists():
            return caminho
    return raiz / "inventario.db"
