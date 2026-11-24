"""Atlas BOS core/tenant_context — active organization resolver.

`get_current_active_organization` is the canonical FastAPI dependency for
multi-tenant requests. Resolves org_id from X-Organization-ID header, support
cookie override, user membership, or single-org fallback. Raises 403 if the
user has no access. Used by ~31 routers.
"""
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security.auth import get_current_user
from app.models.users import PlatformRole, User, UserOrganization


def membresia_principal(db: Session, user_id: int) -> Optional[UserOrganization]:
    """La organización "por omisión" de un usuario: su membresía ACTIVA de menor
    `organization_id`. Una sola regla para el login y para el contexto sin
    cabecera; antes cada uno tomaba "la primera" sin orden (y el login, sin
    mirar `is_active`), así que con dos membresías el resultado dependía del
    plan de la consulta."""
    return db.query(UserOrganization).filter(
        UserOrganization.user_id == user_id,
        UserOrganization.is_active == True,  # noqa: E712
    ).order_by(UserOrganization.organization_id.asc()).first()


def get_current_active_organization(
    request: Request,
    x_organization_id: Optional[int] = Header(None, alias="X-Organization-ID"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> int:
    """Resolve the active organization for the request.

    Order of precedence:
      1. X-Organization-ID header (or `support_org_id` cookie for support staff).
      2. User's first active organization membership.
      3. Single-org fallback (only when exactly one org exists in the system).

    SUPERADMIN must always provide an explicit context header.
    """
    from app.models.organization import Organization

    # La cookie de soporte solo cuenta para el personal de plataforma; en
    # cualquier otro usuario se ignora (no se confía en quién la puso).
    es_plataforma = current_user.platform_role in (PlatformRole.SUPERADMIN, PlatformRole.SUPPORT)
    cookie_soporte = request.cookies.get("support_org_id") if es_plataforma else None
    resolved_org_id = x_organization_id or cookie_soporte

    if resolved_org_id:
        try:
            resolved_org_id = int(resolved_org_id)
        except (TypeError, ValueError):
            resolved_org_id = None

    if resolved_org_id:
        if current_user.platform_role == PlatformRole.SUPERADMIN:
            return resolved_org_id

        assoc = db.query(UserOrganization).filter(
            UserOrganization.user_id == current_user.id,
            UserOrganization.organization_id == resolved_org_id,
            UserOrganization.is_active == True,  # noqa: E712
        ).first()
        if not assoc:
            raise HTTPException(status_code=403, detail="No access to this organization")
        return resolved_org_id

    assoc = membresia_principal(db, current_user.id)
    if assoc:
        return assoc.organization_id

    if current_user.platform_role == PlatformRole.SUPERADMIN:
        raise HTTPException(
            status_code=403,
            detail="Superadmin requires X-Organization-ID header for tenant context",
        )

    org_count = db.query(Organization).count()
    if org_count == 1:
        default_org = db.query(Organization).first()
        is_linked = db.query(UserOrganization).filter(
            UserOrganization.user_id == current_user.id,
            UserOrganization.organization_id == default_org.id,
        ).first()
        if is_linked and is_linked.is_active:
            return default_org.id

    raise HTTPException(status_code=403, detail="User belongs to no active organizations")
