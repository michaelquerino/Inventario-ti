from app.models.asset import Asset
from app.models.legacy import Ativo, Monitoramento

API_HEADERS = {"X-API-Version": "v1"}


def test_list_monitoring_combina_ativos_e_monitoramento(client, admin_token, db_session) -> None:
    db_session.add(
        Monitoramento(numero_serie="SN-MON-1", modelo="Notebook X", usuario="", uso_cpu_percent=42.0)
    )
    db_session.add(Ativo(nome="Notebook X", numero_serie="SN-MON-1", usuario="", responsavel="Fulano"))
    db_session.commit()

    response = client.get(
        "/api/v1/monitoring", headers={**API_HEADERS, "Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    item = next(i for i in response.json() if i["numero_serie"] == "SN-MON-1")
    # monitoramento.usuario está vazio -- deve cair pro fallback (ativos.responsavel)
    assert item["usuario"] == "Fulano"
    assert item["uso_cpu_percent"] == 42.0


def test_update_monitoring_vinculo_atualiza_ativos_e_monitoramento(client, admin_token, db_session) -> None:
    db_session.add(Monitoramento(numero_serie="SN-MON-2", modelo="Notebook Y"))
    db_session.add(Ativo(nome="Notebook Y", numero_serie="SN-MON-2"))
    db_session.add(Asset(asset_tag="SN-MON-2", name="Notebook Y", serial_number="SN-MON-2"))
    db_session.commit()

    response = client.put(
        "/api/v1/monitoring/SN-MON-2",
        headers={**API_HEADERS, "Authorization": f"Bearer {admin_token}"},
        json={"usuario": "Ciclana", "patrimonio": "0088"},
    )

    assert response.status_code == 200

    ativo = db_session.query(Ativo).filter_by(numero_serie="SN-MON-2").one()
    monitoramento = db_session.get(Monitoramento, "SN-MON-2")
    asset = db_session.query(Asset).filter_by(serial_number="SN-MON-2").one()

    assert ativo.usuario == "Ciclana"
    assert ativo.patrimonio == "0088"
    assert monitoramento.usuario == "Ciclana"
    # "usuario" também propaga pro apelido em Ativos (assets.owner)
    assert asset.owner == "Ciclana"


def test_update_monitoring_vinculo_sem_registro_correspondente_da_404(client, admin_token) -> None:
    response = client.put(
        "/api/v1/monitoring/SN-INEXISTENTE",
        headers={**API_HEADERS, "Authorization": f"Bearer {admin_token}"},
        json={"patrimonio": "0099"},
    )

    assert response.status_code == 404
