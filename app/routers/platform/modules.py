"""Modules catalog + CRUD + counts + dependencies + legacy presets endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.models.organization import Organization
from app.models.users import User, PlatformRole
from app.modules.platform.dependencies import require_platform_admin
from app.services.estado_modulos import estado_de

router = APIRouter()


# --- 8. MODULE CATALOG ---
@router.get("/modules/catalog")
def get_module_catalog(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
):
    """Catálogo global de módulos. Serializa enums a .value explícitamente para
    evitar que jsonable_encoder devuelva el repr (e.g. 'ModuleScope.GLOBAL')."""
    from app.models.modules import Module
    mods = db.query(Module).order_by(Module.key).all()
    return [
        {
            "key": m.key,
            "name": m.name,
            "description": m.description,
            "scope": (m.scope.value if hasattr(m.scope, "value") else (m.scope or "GLOBAL")),
            "status": (m.status.value if hasattr(m.status, "value") else (m.status or "STABLE")),
            "estado": estado_de(m.key),
        }
        for m in mods
    ]


# Legacy endpoint for backward compatibility
@router.get("/modules/presets")
def get_industry_presets_legacy(db: Session = Depends(get_db)):
    """Legacy endpoint that returns presets in the old format for backward compatibility."""
    from app.models.modules import IndustryPreset

    presets = db.query(IndustryPreset).all()

    # Convert to old format: {industry_type: [modules]}
    result = {}
    for preset in presets:
        result[preset.industry_type] = preset.modules

    return result


# --- 11. MODULES CRUD ---

class ModuleCreate(BaseModel):
    key: str
    name: str
    description: Optional[str] = None
    scope: str = "GLOBAL"
    status: str = "STABLE"


class ModuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    scope: Optional[str] = None
    status: Optional[str] = None


@router.post("/modules")
def create_module(
    body: ModuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
):
    """Create a new module in the global catalog. SUPERADMIN only."""
    from app.models.modules import Module
    from app.services.audit_service import write_audit
    if current_user.platform_role != PlatformRole.SUPERADMIN:
        raise HTTPException(403, "Solo SUPERADMIN puede crear módulos")
    if db.query(Module).filter(Module.key == body.key).first():
        raise HTTPException(400, f"Module key '{body.key}' ya existe")
    mod = Module(key=body.key, name=body.name, description=body.description, scope=body.scope, status=body.status)
    db.add(mod)
    write_audit(db, actor_user_id=current_user.id, action="CREATE_MODULE",
                entity_type="MODULE", entity_id=body.key, meta=body.model_dump())
    db.commit()
    return {"key": mod.key, "name": mod.name, "scope": mod.scope, "status": mod.status}


@router.put("/modules/{module_key}")
def update_module(
    module_key: str,
    body: ModuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
):
    """Update an existing module (key is immutable)."""
    from app.models.modules import Module
    from app.services.audit_service import write_audit
    if current_user.platform_role != PlatformRole.SUPERADMIN:
        raise HTTPException(403, "Solo SUPERADMIN puede editar módulos")
    mod = db.query(Module).filter(Module.key == module_key).first()
    if not mod:
        raise HTTPException(404, "Módulo no encontrado")
    payload = body.model_dump(exclude_unset=True)
    for k, v in payload.items():
        setattr(mod, k, v)
    write_audit(db, actor_user_id=current_user.id, action="UPDATE_MODULE",
                entity_type="MODULE", entity_id=module_key, meta=payload)
    db.commit()
    return {"key": mod.key, "name": mod.name, "scope": mod.scope, "status": mod.status}


@router.delete("/modules/{module_key}")
def delete_module(
    module_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
):
    """Delete a module. Rejects if any organization currently has it enabled."""
    from app.models.modules import Module, OrganizationModule
    from app.services.audit_service import write_audit
    if current_user.platform_role != PlatformRole.SUPERADMIN:
        raise HTTPException(403, "Solo SUPERADMIN puede eliminar módulos")
    mod = db.query(Module).filter(Module.key == module_key).first()
    if not mod:
        raise HTTPException(404, "Módulo no encontrado")
    active = db.query(OrganizationModule).filter(
        OrganizationModule.module_key == module_key,
        OrganizationModule.is_enabled == True,
    ).count()
    if active > 0:
        raise HTTPException(400, f"No se puede eliminar: {active} organización(es) lo tienen activo")
    db.delete(mod)
    write_audit(db, actor_user_id=current_user.id, action="DELETE_MODULE",
                entity_type="MODULE", entity_id=module_key)
    db.commit()
    return {"status": "deleted", "key": module_key}


@router.get("/modules/counts")
def get_modules_counts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
):
    """Conteos agregados de presets/orgs por módulo en UNA sola query.
    Reemplaza N llamadas paralelas a /modules/{key}/dependencies — evitaba
    agotar el pool de conexiones cuando el catálogo tiene muchos módulos."""
    from app.models.modules import Module, OrganizationModule, IndustryPreset
    from sqlalchemy import func

    # Orgs activas por module_key (1 query)
    org_counts_rows = (
        db.query(OrganizationModule.module_key, func.count(OrganizationModule.organization_id))
        .filter(OrganizationModule.is_enabled == True)
        .group_by(OrganizationModule.module_key)
        .all()
    )
    org_counts = {k: int(c) for k, c in org_counts_rows}

    # Presets por module_key (1 query, filtrado en Python — JSON column)
    presets = db.query(IndustryPreset).all()
    preset_counts: dict[str, int] = {}
    for p in presets:
        for mk in (p.modules or []):
            preset_counts[mk] = preset_counts.get(mk, 0) + 1

    # Asegurar entry por cada módulo del catálogo (incluso con 0 deps)
    keys = [m.key for m in db.query(Module.key).all()]
    out: dict[str, dict[str, int]] = {}
    for k in keys:
        out[k] = {"presets": preset_counts.get(k, 0), "orgs": org_counts.get(k, 0)}
    return out


@router.get("/modules/{module_key}/dependencies")
def get_module_dependencies(
    module_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_admin),
):
    """List presets and orgs depending on a module."""
    from app.models.modules import Module, OrganizationModule, IndustryPreset
    if not db.query(Module).filter(Module.key == module_key).first():
        raise HTTPException(404, "Módulo no encontrado")
    presets = db.query(IndustryPreset).all()
    presets_using = [{"id": p.id, "industry_type": p.industry_type, "display_name": p.display_name}
                     for p in presets if module_key in (p.modules or [])]
    org_rows = (
        db.query(OrganizationModule, Organization)
        .join(Organization, Organization.id == OrganizationModule.organization_id)
        .filter(OrganizationModule.module_key == module_key,
                OrganizationModule.is_enabled == True)
        .all()
    )
    orgs = [{"id": org.id, "name": org.name} for _, org in org_rows]
    return {"module_key": module_key, "presets": presets_using, "orgs": orgs}
