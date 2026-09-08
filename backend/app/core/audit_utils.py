"""Utilitários de Auditoria"""

from fastapi import Request


def get_client_ip(request: Request) -> str | None:
    """Extrair IP do cliente (suporta proxies com X-Forwarded-For)"""
    if request.client:
        return request.client.host

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    return None


def get_user_agent(request: Request) -> str | None:
    """Extrair User-Agent do cliente"""
    return request.headers.get("User-Agent")


def compute_diff(old_dict: dict, new_dict: dict) -> tuple[dict, dict]:
    """
    Computar diff entre dois dicionários.
    Retorna apenas os campos que mudaram.

    Exemplo:
        old = {"name": "Asset1", "status": "active", "location": "Room1"}
        new = {"name": "Asset1", "status": "inactive", "location": "Room2"}
        old_diff, new_diff = compute_diff(old, new)
        # old_diff = {"status": "active", "location": "Room1"}
        # new_diff = {"status": "inactive", "location": "Room2"}
    """
    old_diff = {}
    new_diff = {}

    # Campos que foram alterados
    for key in new_dict:
        if key not in old_dict or old_dict[key] != new_dict[key]:
            old_diff[key] = old_dict.get(key)
            new_diff[key] = new_dict[key]

    # Campos que foram removidos
    for key in old_dict:
        if key not in new_dict:
            old_diff[key] = old_dict[key]
            new_diff[key] = None

    return old_diff, new_diff
