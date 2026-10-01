"""Planes de plataforma: catalogo y uso por organizacion.

Solo lectura. El cambio de plan va por el PUT de organizations (valida la
clave); encender modulos va por el PATCH de modules (valida el plan).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.organization import Organization
from app.modules.platform.dependencies import require_platform_admin
from app.schemas.plans import PlanRead, PlanUsoRead
from app.services import plans

# El paquete ya exige plataforma; se repite aqui para documentar la intencion.
router = APIRouter(dependencies=[Depends(require_platform_admin)])


def _a_read(p: plans.Plan) -> PlanRead:
    return PlanRead(
        clave=p.clave, nombre=p.nombre, lema=p.lema, precio_mxn=p.precio_mxn,
        precio_desde=p.precio_desde, max_usuarios=p.max_usuarios,
        max_sucursales_venta=p.max_sucursales_venta,
        modulos_crecimiento=sorted(p.modulos_crecimiento), permite_todo=p.permite_todo,
    )


@router.get("/plans", response_model=list[PlanRead])
def listar_planes():
    return [_a_read(p) for p in plans.PLANES]


@router.get("/organizations/{org_id}/plan-uso", response_model=PlanUsoRead)
def plan_uso(org_id: int, db: Session = Depends(get_db)):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    u = plans.uso(db, org.id)
    return PlanUsoRead(
        plan=_a_read(plans.obtener_plan(org.plan)),
        usuarios_activos=u.usuarios_activos,
        sucursales_venta=u.sucursales_venta,
        modulos_fuera_de_plan=plans.modulos_fuera_de_plan(db, org),
    )
