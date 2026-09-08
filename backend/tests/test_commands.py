from app.models.legacy import Comando, ComandoTemplate

API_HEADERS = {"X-API-Version": "v1"}


def _auth(token: str) -> dict:
    return {**API_HEADERS, "Authorization": f"Bearer {token}"}


def test_create_command_cria_um_por_notebook_e_enfileira_pendente(client, admin_token, db_session) -> None:
    response = client.post(
        "/api/v1/commands",
        headers=_auth(admin_token),
        json={"numero_series": ["SN-CMD-A", "SN-CMD-B"], "comando": "echo oi", "modo": "usuario"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert len(payload) == 2
    assert {c["numero_serie"] for c in payload} == {"SN-CMD-A", "SN-CMD-B"}
    assert all(c["status"] == "pendente" for c in payload)

    salvos = db_session.query(Comando).filter(Comando.numero_serie.in_(["SN-CMD-A", "SN-CMD-B"])).all()
    assert len(salvos) == 2


def test_list_commands_filtra_por_numero_serie(client, admin_token, db_session) -> None:
    db_session.add(Comando(numero_serie="SN-LIST-1", comando="echo 1", status="pendente", criado_em="2026-01-01T00:00:00"))
    db_session.add(Comando(numero_serie="SN-LIST-2", comando="echo 2", status="pendente", criado_em="2026-01-01T00:00:00"))
    db_session.commit()

    response = client.get(
        "/api/v1/commands", headers=_auth(admin_token), params={"numero_serie": "SN-LIST-1"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["numero_serie"] == "SN-LIST-1"


def test_delete_command_so_funciona_se_pendente(client, admin_token, db_session) -> None:
    concluido = Comando(numero_serie="SN-DEL-1", comando="echo x", status="concluido", criado_em="2026-01-01T00:00:00")
    db_session.add(concluido)
    db_session.commit()
    db_session.refresh(concluido)

    resposta_bloqueada = client.delete(f"/api/v1/commands/{concluido.id}", headers=_auth(admin_token))
    assert resposta_bloqueada.status_code == 409

    pendente = Comando(numero_serie="SN-DEL-2", comando="echo y", status="pendente", criado_em="2026-01-01T00:00:00")
    db_session.add(pendente)
    db_session.commit()
    db_session.refresh(pendente)

    pendente_id = pendente.id  # captura antes de expirar -- ver comentário abaixo

    resposta_ok = client.delete(f"/api/v1/commands/{pendente_id}", headers=_auth(admin_token))
    assert resposta_ok.status_code == 204

    # A exclusão foi commitada por uma sessão diferente (a da própria
    # requisição). Acessar pendente.id de novo depois do expire_all()
    # dispararia um reload do objeto e levantaria ObjectDeletedError (a
    # linha já não existe) -- por isso o id foi capturado antes, como int
    # simples, pra consultar sem tocar na instância expirada.
    db_session.expire_all()
    assert db_session.query(Comando).filter_by(id=pendente_id).first() is None


def test_cancel_command_marca_como_erro_sem_apagar(client, admin_token, db_session) -> None:
    comando = Comando(numero_serie="SN-CANCEL", comando="echo z", status="executando", criado_em="2026-01-01T00:00:00")
    db_session.add(comando)
    db_session.commit()
    db_session.refresh(comando)

    response = client.patch(f"/api/v1/commands/{comando.id}/cancel", headers=_auth(admin_token))

    assert response.status_code == 200
    assert response.json()["status"] == "erro"
    db_session.refresh(comando)
    assert comando.status == "erro"
    assert comando.resultado


def test_templates_crud(client, admin_token, db_session) -> None:
    create_response = client.post(
        "/api/v1/commands/templates",
        headers=_auth(admin_token),
        json={"nome": "Reiniciar spooler", "comando": "Restart-Service spooler"},
    )
    assert create_response.status_code == 201
    template_id = create_response.json()["id"]

    list_response = client.get("/api/v1/commands/templates", headers=_auth(admin_token))
    assert list_response.status_code == 200
    assert any(t["id"] == template_id for t in list_response.json())

    delete_response = client.delete(f"/api/v1/commands/templates/{template_id}", headers=_auth(admin_token))
    assert delete_response.status_code == 204
    assert db_session.get(ComandoTemplate, template_id) is None
