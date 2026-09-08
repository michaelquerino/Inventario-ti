from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


def _default_database_url() -> str:
    # backend/app/core/config.py -> repo root
    repo_root = Path(__file__).resolve().parents[3]
    db_path = (repo_root / "inventario.db").resolve()
    return f"sqlite:///{db_path.as_posix()}"


class Settings(BaseSettings):
    app_name: str = "IT Manager"
    api_v1_prefix: str = "/api/v1"
    database_url: str = _default_database_url()
    cors_origins: str = "http://localhost:3000"
    # Cobre acesso pela LAN (192.168.x.x), pelo Tailscale (100.64.0.0/10,
    # faixa CGNAT reservada pra ele) e pelo nome amigável "infradesk"
    # (resolvido via hosts file nos notebooks, sem precisar de DNS próprio),
    # na porta 3000 -- o firewall (restringir-rede-servidor.ps1) já limita
    # quem alcança essa porta às sub-redes/faixa confiáveis.
    cors_origin_regex: str = (
        r"^https?://(192\.168\.\d{1,3}\.\d{1,3}|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}|infradesk):3000$"
    )
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    api_version: str = "v1"
    supported_api_versions: str = "v1"
    admin_email: str = "ti@corpori.com.br"
    admin_password: str = "CorporiSST"
    admin_full_name: str = "Administrador Corpori"
    single_admin_mode: bool = True
    # Usada só como fallback pra notebooks que ainda não migraram pro
    # WebSocket -- enquanto conectados por WS, o status vem da conexão em si.
    monitoring_online_window_minutes: int = 360
    backup_interval_hours: float = 24
    backup_retention_count: int = 30
    # Mesma chave usada pelo agente e por servidor.py (config.py na raiz do
    # repo, API_KEY_AGENTE) -- precisa ficar igual nos dois lugares.
    agent_api_key: str = "fmH5kwsA-HcfqcaKqbqRAPiBQNHn03296nGNPwUHA_k"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
