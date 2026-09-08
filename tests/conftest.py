import sys
from pathlib import Path

# Permite `import database` a partir de tests/, já que database.py mora na
# raiz do repositório (não é um pacote instalado).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import database


@pytest.fixture(autouse=True)
def banco_isolado(tmp_path, monkeypatch):
    """Isola cada teste num SQLite temporário e descartável.

    Sem isso, o simples `import database` já escolhe o inventario.db real do
    projeto como NOME_BANCO (é assim que _resolver_nome_banco() funciona --
    ele acha qualquer banco que já exista no diretório atual), e os testes
    acabariam lendo/escrevendo em cima dos dados reais de produção. As
    funções de database.py leem NOME_BANCO/NOME_BANCO_AUDITORIA como
    variável de módulo a cada chamada, então sobrescrever aqui é suficiente
    -- não precisa recarregar o módulo.
    """
    banco_temp = tmp_path / "teste.db"
    auditoria_temp = tmp_path / "auditoria_teste.db"
    monkeypatch.setattr(database, "NOME_BANCO", str(banco_temp))
    monkeypatch.setattr(database, "NOME_BANCO_AUDITORIA", str(auditoria_temp))
    yield
