import sys
from pathlib import Path

# config.py mora na raiz do repositório, não em backend/ (onde pythonpath já
# aponta via pytest.ini) -- adiciona explicitamente, sem depender de outro
# teste já ter feito isso como efeito colateral de chamar a API.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

API_HEADERS = {"X-API-Version": "v1"}


def test_agent_update_script_aponta_para_porta_do_backend(client, admin_token) -> None:
    response = client.get(
        "/api/v1/commands/agent-update-script",
        headers={**API_HEADERS, "Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    script = response.json()["script"]
    assert "/agente/download" in script
    # A porta do Flask (5000) não deve mais aparecer no script -- ele agora
    # baixa do backend FastAPI (porta padrão 8000, veja PORTA_BACKEND_WS).
    assert ":5000/agente/download" not in script
    assert ":8000/agente/download" in script


def test_agente_download_exige_api_key(client) -> None:
    response = client.get("/agente/download", headers=API_HEADERS)
    assert response.status_code == 401


def test_agente_download_com_api_key_valida(client) -> None:
    import config  # config.py na raiz do repositório

    response = client.get(
        "/agente/download",
        headers={**API_HEADERS, "X-API-Key": config.API_KEY_AGENTE},
    )

    # 200 se dist/agente_manual.exe existir neste checkout, 404 se não --
    # os dois são respostas válidas da rota (não deve dar erro 500/401).
    assert response.status_code in (200, 404)
