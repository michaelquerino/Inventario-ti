from fastapi import APIRouter, Depends

from app.api.deps_version import require_supported_api_version
from app.api.routes import assets, audit, auth, backups, commands, health, monitoring, tickets

api_router = APIRouter()
api_router.include_router(
    health.router,
    tags=["health"],
    dependencies=[Depends(require_supported_api_version)],
)
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["auth"],
    dependencies=[Depends(require_supported_api_version)],
)
api_router.include_router(
    assets.router,
    prefix="/assets",
    tags=["assets"],
    dependencies=[Depends(require_supported_api_version)],
)
api_router.include_router(
    monitoring.router,
    prefix="/monitoring",
    tags=["monitoring"],
    dependencies=[Depends(require_supported_api_version)],
)
api_router.include_router(
    audit.router,
    prefix="/audit",
    tags=["audit"],
    dependencies=[Depends(require_supported_api_version)],
)
api_router.include_router(
    commands.router,
    prefix="/commands",
    tags=["commands"],
    dependencies=[Depends(require_supported_api_version)],
)
api_router.include_router(
    backups.router,
    prefix="/backups",
    tags=["backups"],
    dependencies=[Depends(require_supported_api_version)],
)
api_router.include_router(
    tickets.router,
    prefix="/tickets",
    tags=["tickets"],
    dependencies=[Depends(require_supported_api_version)],
)
