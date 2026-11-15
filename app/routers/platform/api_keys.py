"""Per-org API keys management (Sprint 2 · H1)."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, field_validator
import json as _json
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.security.channel_keys import CHANNEL_SCOPES
from app.models.organization import Organization
from app.models.users import User
from app.modules.platform.dependencies import require_platform_admin, require_superadmin

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# 17. API KEYS per-org · Sprint 2 · H1
# Tokens server-to-server gestionados por el SUPERADMIN. El secreto se
# muestra UNA sola vez al crear; después solo guardamos hash SHA-256
# + prefijo para display. Revoke = soft; Delete = hard (superadmin).
# ─────────────────────────────────────────────────────────────────────────────

# Los scopes de la llave son los del canal "Tienda en línea" (los viejos
# read:all/write:* eran informativos y nadie los leía).
_ALLOWED_SCOPES = set(CHANNEL_SCOPES)


class ApiKeyCreate(BaseModel):
    organization_id: int
    name: str
    scopes: Optional[List[str]] = None

    @field_validator("name")
    @classmethod
    def _name_check(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("name requerido")
        if len(v) > 120:
            raise ValueError("name máx 120 chars")
        return v

    @field_validator("scopes")
    @classmethod
    def _scopes_check(cls, v):
        if v is None:
            return v
        cleaned = [s.strip() for s in v if isinstance(s, str) and s.strip()]
        bad = [s for s in cleaned if s not in _ALLOWED_SCOPES]
        if bad:
            raise ValueError(f"scopes inválidos: {', '.join(bad)}")
        # Dedup while preserving order.
        seen: set[str] = set()
        out: List[str] = []
        for s in cleaned:
            if s not in seen:
                seen.add(s)
                out.append(s)
        return out


def _api_key_to_dict(row, org_name: Optional[str] = None) -> dict:
    """Safe serialization — NEVER returns `hashed_key`."""
    scopes: Optional[List[str]] = None
    if row.scopes:
        try:
            parsed = _json.loads(row.scopes)
            if isinstance(parsed, list):
                scopes = [str(s) for s in parsed]
        except Exception:
            scopes = None
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "org_name": org_name,
        "name": row.name,
        "prefix": row.prefix,
        "scopes": scopes,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "last_used_ip": row.last_used_ip,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "created_by": row.created_by,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "revoked_by": row.revoked_by,
    }


@router.get("/api-keys")
def list_api_keys(
    organization_id: Optional[int] = Query(None),
    active: Optional[bool] = Query(None, description="true=only non-revoked, false=only revoked"),
    q: Optional[str] = Query(None, description="search name/prefix"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
):
    """List API keys across all orgs with optional filters.
    Never returns `hashed_key`. Safe for display in the SUPERADMIN panel."""
    from app.models.platform import ApiKey

    query = db.query(ApiKey, Organization.name).outerjoin(
        Organization, Organization.id == ApiKey.organization_id
    )

    if organization_id is not None:
        query = query.filter(ApiKey.organization_id == organization_id)
    if active is True:
        query = query.filter(ApiKey.revoked_at.is_(None))
    elif active is False:
        query = query.filter(ApiKey.revoked_at.isnot(None))

    if q:
        from sqlalchemy import func as sqlfunc, or_
        needle = f"%{q.strip().lower()}%"
        query = query.filter(or_(
            sqlfunc.lower(ApiKey.name).like(needle),
            sqlfunc.lower(ApiKey.prefix).like(needle),
        ))

    rows = query.order_by(ApiKey.created_at.desc()).all()
    return [_api_key_to_dict(row, org_name) for row, org_name in rows]


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
def create_api_key(
    body: ApiKeyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
):
    """Generate a new API key. Returns the full key ONCE — it cannot be
    retrieved afterwards. Only SHA-256 hash + prefix are persisted."""
    from app.models.platform import ApiKey
    from app.modules.platform.api_keys import generate_api_key
    from app.services.audit_service import write_audit

    org = db.query(Organization).filter(Organization.id == body.organization_id).first()
    if not org:
        raise HTTPException(404, "Organization no encontrada")

    full_key, prefix, hashed = generate_api_key()
    scopes_json = _json.dumps(body.scopes) if body.scopes else None

    row = ApiKey(
        organization_id=org.id,
        name=body.name,
        prefix=prefix,
        hashed_key=hashed,
        scopes=scopes_json,
        created_by=current_user.id,
    )
    db.add(row)
    db.flush()

    # Audit: do NOT include the full key in the payload.
    write_audit(
        db, actor_user_id=current_user.id, action="CREATE_API_KEY",
        entity_type="API_KEY", entity_id=str(row.id),
        organization_id=org.id,
        meta={"name": row.name, "prefix": row.prefix, "scopes": body.scopes or []},
    )
    db.commit()
    db.refresh(row)

    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "org_name": org.name,
        "name": row.name,
        "prefix": row.prefix,
        "scopes": body.scopes or [],
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "full_key": full_key,  # shown ONLY on creation
    }


@router.get("/api-keys/for-org/{org_id}")
def list_api_keys_for_org(
    org_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
):
    """List all API keys belonging to a specific org (used by OrgDetail)."""
    from app.models.platform import ApiKey

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(404, "Organization no encontrada")

    rows = (
        db.query(ApiKey)
        .filter(ApiKey.organization_id == org_id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )
    return [_api_key_to_dict(row, org.name) for row in rows]


@router.get("/api-keys/{key_id}")
def get_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
):
    """Detail view (no full_key, no hash)."""
    from app.models.platform import ApiKey

    row = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not row:
        raise HTTPException(404, "API key no encontrada")
    org = db.query(Organization).filter(Organization.id == row.organization_id).first()
    return _api_key_to_dict(row, org.name if org else None)


@router.post("/api-keys/{key_id}/revoke")
def revoke_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
):
    """Soft-revoke: sets `revoked_at = now()`. Row kept for audit."""
    from app.models.platform import ApiKey
    from app.services.audit_service import write_audit

    row = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not row:
        raise HTTPException(404, "API key no encontrada")

    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        row.revoked_by = current_user.id
        write_audit(
            db, actor_user_id=current_user.id, action="REVOKE_API_KEY",
            entity_type="API_KEY", entity_id=str(row.id),
            organization_id=row.organization_id,
            meta={"name": row.name, "prefix": row.prefix},
        )
    db.commit()
    db.refresh(row)

    org = db.query(Organization).filter(Organization.id == row.organization_id).first()
    return _api_key_to_dict(row, org.name if org else None)


@router.delete("/api-keys/{key_id}")
def delete_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_superadmin),
):
    """Hard-delete an API key. SUPERADMIN-only (stricter than other endpoints)."""
    from app.models.platform import ApiKey
    from app.services.audit_service import write_audit

    row = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not row:
        raise HTTPException(404, "API key no encontrada")

    snapshot = {
        "name": row.name,
        "prefix": row.prefix,
        "organization_id": row.organization_id,
    }
    db.delete(row)
    write_audit(
        db, actor_user_id=current_user.id, action="DELETE_API_KEY",
        entity_type="API_KEY", entity_id=str(key_id),
        organization_id=snapshot["organization_id"],
        meta=snapshot,
    )
    db.commit()
    return {"deleted": True, "id": key_id}
