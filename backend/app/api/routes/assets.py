from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.deps_auth import require_roles
from app.core.audit_utils import compute_diff, get_client_ip, get_user_agent
from app.core.rate_limit import limiter
from app.crud import asset as asset_crud
from app.crud import audit_log
from app.schemas.asset import AssetCreate, AssetRead, AssetUpdate

router = APIRouter()


@router.get("/summary")
@limiter.limit("60/minute")
def assets_summary(
    request: Request,
    db: Session = Depends(get_db),
    _current_user=Depends(require_roles("admin", "manager", "viewer")),
) -> dict[str, int]:
    assets = asset_crud.list_assets(db)

    total_assets = len(assets)
    cloud_assets = sum(1 for item in assets if (item.category or "").strip().lower() == "cloud")
    maintenance_assets = sum(
        1
        for item in assets
        if (item.status or "").strip().lower() in {"maintenance", "em manutenção", "em manutencao"}
    )

    pending_audit = audit_log.count_pending_events(db)

    return {
        "total_assets": total_assets,
        "cloud_assets": cloud_assets,
        "maintenance_assets": maintenance_assets,
        "pending_audit": pending_audit,
    }


@router.get("", response_model=list[AssetRead])
@limiter.limit("100/minute")
def list_assets(
    request: Request,
    db: Session = Depends(get_db),
    _current_user=Depends(require_roles("admin", "manager", "viewer")),
) -> list[AssetRead]:
    return asset_crud.list_assets(db)


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_asset(
    request: Request,
    payload: AssetCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager")),
) -> AssetRead:
    existing = asset_crud.get_by_asset_tag(db, payload.asset_tag)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset tag already exists")
    try:
        asset = asset_crud.create_asset(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # Registrar auditoria com IP e User-Agent
    audit_log.create_event(
        db,
        actor_email=current_user.email,
        action="asset.create",
        entity_type="asset",
        entity_id=str(asset.id),
        details=asset.asset_tag,
        new_values=payload.model_dump(),
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    return asset


@router.get("/{asset_id}", response_model=AssetRead)
@limiter.limit("100/minute")
def get_asset(
    request: Request,
    asset_id: int,
    db: Session = Depends(get_db),
    _current_user=Depends(require_roles("admin", "manager", "viewer")),
) -> AssetRead:
    asset = asset_crud.get_asset(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return asset


@router.put("/{asset_id}", response_model=AssetRead)
@limiter.limit("30/minute")
def update_asset(
    request: Request,
    asset_id: int,
    payload: AssetUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin", "manager")),
) -> AssetRead:
    asset = asset_crud.get_asset(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    if payload.asset_tag and payload.asset_tag != asset.asset_tag:
        existing = asset_crud.get_by_asset_tag(db, payload.asset_tag)
        if existing is not None and existing.id != asset.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset tag already exists")

    try:
        updated = asset_crud.update_asset(db, asset, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # Capturar valores antes/depois (diff)
    old_values = {
        "asset_tag": asset.asset_tag,
        "name": asset.name,
        "category": asset.category,
        "status": asset.status,
        "location": asset.location,
        "owner": asset.owner,
    }
    new_values_dict = payload.model_dump(exclude_unset=True)

    old_diff, new_diff = compute_diff(old_values, new_values_dict)

    # Registrar auditoria com diff
    audit_log.create_event(
        db,
        actor_email=current_user.email,
        action="asset.update",
        entity_type="asset",
        entity_id=str(updated.id),
        details=updated.asset_tag,
        old_values=old_diff if old_diff else None,
        new_values=new_diff if new_diff else None,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    return updated


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
def delete_asset(
    request: Request,
    asset_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("admin")),
) -> None:
    asset = asset_crud.get_asset(db, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    # Registrar valores antigos (para auditoria)
    old_values = {
        "asset_tag": asset.asset_tag,
        "name": asset.name,
        "category": asset.category,
        "status": asset.status,
        "location": asset.location,
        "owner": asset.owner,
    }

    audit_log.create_event(
        db,
        actor_email=current_user.email,
        action="asset.delete",
        entity_type="asset",
        entity_id=str(asset.id),
        details=asset.asset_tag,
        old_values=old_values,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    asset_crud.delete_asset(db, asset)
