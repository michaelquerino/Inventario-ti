import time

API_HEADERS = {"X-API-Version": "v1"}


def test_health_endpoint(client) -> None:
    response = client.get("/api/v1/health", headers=API_HEADERS)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_register_login_and_me_flow(client) -> None:
    unique_suffix = int(time.time() * 1000)
    email = f"usuario{unique_suffix}@corpori.com.br"
    password = "SenhaTeste123"

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": "Usuário Teste",
            "password": password,
        },
        headers=API_HEADERS,
    )
    assert register_response.status_code == 201
    register_payload = register_response.json()
    assert register_payload["email"] == email
    assert register_payload["role"] == "viewer"
    assert register_payload["is_active"] is True

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=API_HEADERS,
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    assert token

    me_response = client.get(
        "/api/v1/auth/me",
        headers={**API_HEADERS, "Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    me_payload = me_response.json()
    assert me_payload["email"] == email
    assert me_payload["role"] == "viewer"


def test_assets_crud_flow_with_admin_and_viewer_restriction(client, admin_token) -> None:
    unique_suffix = int(time.time() * 1000)
    asset_tag = f"ASSET-{unique_suffix}"
    serial = f"SER-{unique_suffix}"

    create_response = client.post(
        "/api/v1/assets",
        headers={**API_HEADERS, "Authorization": f"Bearer {admin_token}"},
        json={
            "asset_tag": asset_tag,
            "name": "Notebook Teste",
            "category": "Computador",
            "status": "active",
            "serial_number": serial,
            "location": "Sala 101",
            "owner": "Equipe TI",
        },
    )
    assert create_response.status_code == 201
    created_asset = create_response.json()
    assert created_asset["asset_tag"] == asset_tag
    asset_id = created_asset["id"]

    list_response = client.get(
        "/api/v1/assets",
        headers={**API_HEADERS, "Authorization": f"Bearer {admin_token}"},
    )
    assert list_response.status_code == 200
    assert any(asset["id"] == asset_id for asset in list_response.json())

    update_response = client.put(
        f"/api/v1/assets/{asset_id}",
        headers={**API_HEADERS, "Authorization": f"Bearer {admin_token}"},
        json={"status": "maintenance", "location": "Sala 102"},
    )
    assert update_response.status_code == 200
    updated_asset = update_response.json()
    assert updated_asset["status"] == "maintenance"
    assert updated_asset["location"] == "Sala 102"

    viewer_email = f"viewer{unique_suffix}@corpori.com.br"
    viewer_password = "SenhaViewer123"
    register_viewer = client.post(
        "/api/v1/auth/register",
        json={
            "email": viewer_email,
            "full_name": "Usuário Viewer",
            "password": viewer_password,
        },
        headers=API_HEADERS,
    )
    assert register_viewer.status_code == 201

    viewer_login = client.post(
        "/api/v1/auth/login",
        json={"email": viewer_email, "password": viewer_password},
        headers=API_HEADERS,
    )
    assert viewer_login.status_code == 200
    viewer_token = viewer_login.json()["access_token"]

    forbidden_create = client.post(
        "/api/v1/assets",
        headers={**API_HEADERS, "Authorization": f"Bearer {viewer_token}"},
        json={"asset_tag": f"ASSET-FORB-{unique_suffix}", "name": "Sem Permissão"},
    )
    assert forbidden_create.status_code == 403
    assert forbidden_create.json()["detail"] == "Permissão negada"

    delete_response = client.delete(
        f"/api/v1/assets/{asset_id}",
        headers={**API_HEADERS, "Authorization": f"Bearer {admin_token}"},
    )
    assert delete_response.status_code == 204
