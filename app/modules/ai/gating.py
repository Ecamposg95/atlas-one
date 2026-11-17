"""Gate estricto del asistente IA: sin el bypass de ADMIN/DUEÑO de `require_module`."""
from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_context import get_current_active_organization
from app.models.modules import OrganizationModule


def exigir_modulo_ai(
    org_id: int = Depends(get_current_active_organization),
    db: Session = Depends(get_db),
) -> int:
    habilitado = db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org_id,
        OrganizationModule.module_key == "ai",
        OrganizationModule.is_enabled == True,  # noqa: E712
    ).first()
    if not habilitado:
        raise HTTPException(
            status_code=403,
            detail="La IA es un complemento aparte de tu plan y no está activa en tu negocio. "
                   "Pídela a Atlas ONE para activarla.",
        )
    return org_id
