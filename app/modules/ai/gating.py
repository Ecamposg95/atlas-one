"""Gate estricto del asistente IA: sin el bypass de ADMIN/DUEÑO de `require_module`."""
from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_context import get_current_active_organization
from app.models.modules import OrganizationModule
from app.services.plans import plan_minimo_para


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
        minimo = plan_minimo_para("ai")
        nombre = minimo.nombre if minimo else "superior"
        raise HTTPException(
            status_code=403,
            detail=f"El asistente IA no está incluido en tu plan (mínimo {nombre}). La plataforma puede activarlo.",
        )
    return org_id
