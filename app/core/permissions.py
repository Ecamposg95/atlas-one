"""Atlas BOS core/permissions — cross-cutting permission gates.

Owns `require_module` (feature-flag gate per organization). The legacy
role-template matrix lives in `app.core.role_permissions` and is re-exported
here as `role_permissions` for forward compatibility — eventual cleanup
moves the dual RBAC into a coherent module in a later phase.
"""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security.auth import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.models.modules import OrganizationModule
from app.models.users import Role, User, UserOrganization
from app.core import role_permissions  # noqa: F401  (legacy DAXPOS_ROLE_VIEWS lives here)


def require_module(module_key: str):
    """FastAPI dependency factory: ensure `module_key` is enabled for the active org."""

    async def _enforce(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        # Tenant owners/admins bypass module gating for their own org.
        if current_user.role in (Role.ADMINISTRADOR, Role.DUEÑO):
            return True

        try:
            org_id = get_current_active_organization(request, None, current_user, db)
        except Exception:
            assoc = db.query(UserOrganization).filter(
                UserOrganization.user_id == current_user.id
            ).first()
            org_id = assoc.organization_id if assoc else None

        if not org_id:
            raise HTTPException(status_code=403, detail="No organization context found")

        enabled = db.query(OrganizationModule).filter(
            OrganizationModule.organization_id == org_id,
            OrganizationModule.module_key == module_key,
            OrganizationModule.is_enabled == True,  # noqa: E712
        ).first()
        if not enabled:
            raise HTTPException(
                status_code=403,
                detail=f"El módulo '{module_key}' no está habilitado para esta organización.",
            )
        return True

    return _enforce


def tiene_capacidad(db: Session, org_id: int, clave: str) -> bool:
    """¿La organización puede usar esa función del catálogo?

    Lista blanca: una clave que no esté en el catálogo se considera siempre
    disponible. Así, agregar un candado nuevo exige declararlo primero.
    """
    from app.capacidades import modulo_de

    modulo = modulo_de(clave)
    if modulo is None:
        return True
    return db.query(
        db.query(OrganizationModule).filter(
            OrganizationModule.organization_id == org_id,
            OrganizationModule.module_key == modulo,
            OrganizationModule.is_enabled == True,  # noqa: E712
        ).exists()
    ).scalar()
