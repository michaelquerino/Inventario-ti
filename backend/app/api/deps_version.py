from fastapi import Header, HTTPException, status

from app.core.config import settings


def require_supported_api_version(x_api_version: str = Header(alias="X-API-Version")) -> str:
    supported_versions = {item.strip() for item in settings.supported_api_versions.split(",") if item.strip()}

    if x_api_version not in supported_versions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Versão de API inválida. Use uma das versões: {', '.join(sorted(supported_versions))}",
        )

    return x_api_version

