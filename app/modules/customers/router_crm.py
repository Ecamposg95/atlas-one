"""CRM: campos propios, seguimiento y ficha 360 del cliente (2026-11-24).

Se monta en `/api/customers` ANTES del router de clientes: `/campos` y
`/seguimiento` son rutas fijas que no deben caer en `/{customer_id}`."""
from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_module
from app.core.security import get_current_user
from app.core.security.guards import require_admin_or_owner
from app.core.tenant_context import get_current_active_organization
from app.models import User
from app.modules.customers import crm
from app.modules.customers.models import Customer, CustomerFieldDef, CustomerFollowUp
from app.modules.customers.schemas import (
    CampoPropioIn, CampoPropioOut, CustomerRead, SeguimientoHecho, SeguimientoIn,
)
from app.services.ventas_cajero import es_cajero

router = APIRouter(dependencies=[Depends(require_module("crm"))])


# ── Campos propios ────────────────────────────────────────────────────────
@router.get("/campos", response_model=List[CampoPropioOut])
def listar_campos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    return crm.campos_activos(db, org_id)


@router.post("/campos", response_model=CampoPropioOut)
def crear_campo(
    datos: CampoPropioIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner),
    org_id: int = Depends(get_current_active_organization),
):
    campo = crm.crear_campo(db, org_id, label=datos.label, tipo=datos.tipo,
                            opciones=datos.opciones, orden=datos.orden)
    db.commit()
    db.refresh(campo)
    return campo


def _campo(db: Session, org_id: int, campo_id: int) -> CustomerFieldDef:
    campo = db.query(CustomerFieldDef).filter(
        CustomerFieldDef.id == campo_id, CustomerFieldDef.organization_id == org_id,
        CustomerFieldDef.is_active == True,  # noqa: E712
    ).first()
    if campo is None:
        raise HTTPException(status_code=404, detail="Campo no encontrado")
    return campo


@router.put("/campos/{campo_id}", response_model=CampoPropioOut)
def editar_campo(
    campo_id: int,
    datos: CampoPropioIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner),
    org_id: int = Depends(get_current_active_organization),
):
    campo = _campo(db, org_id, campo_id)
    crm.editar_campo(db, campo, label=datos.label, tipo=datos.tipo, opciones=datos.opciones, orden=datos.orden)
    db.commit()
    db.refresh(campo)
    return campo


@router.delete("/campos/{campo_id}")
def quitar_campo(
    campo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner),
    org_id: int = Depends(get_current_active_organization),
):
    """Retira el campo de la ficha. Lo ya capturado se conserva en cada
    cliente (deja de mostrarse), por si se retiró por error."""
    campo = _campo(db, org_id, campo_id)
    campo.is_active = False
    db.commit()
    return {"ok": True}


# ── Seguimiento ───────────────────────────────────────────────────────────
@router.get("/seguimiento")
def listar_seguimiento(
    estado: str = Query("PENDIENTE"),              # PENDIENTE | HECHO | TODOS
    customer_id: Optional[int] = Query(None),
    hasta: Optional[date] = Query(None),           # pendientes con fecha <= hasta
    limit: int = Query(100, le=300),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Tareas con clientes. La caja ve las de su sucursal y las asignadas a
    ella; gerente, administrador y dueño ven todas."""
    from sqlalchemy import or_
    q = db.query(CustomerFollowUp).filter(CustomerFollowUp.organization_id == org_id)
    if estado.upper() != "TODOS":
        q = q.filter(CustomerFollowUp.status == estado.upper())
    if customer_id is not None:
        q = q.filter(CustomerFollowUp.customer_id == customer_id)
    if hasta is not None:
        q = q.filter(CustomerFollowUp.due_date <= hasta)
    if es_cajero(current_user):
        q = q.filter(or_(
            CustomerFollowUp.assigned_user_id == current_user.id,
            CustomerFollowUp.created_by_user_id == current_user.id,
            CustomerFollowUp.branch_id == current_user.branch_id,
        ))
    filas = q.order_by(CustomerFollowUp.due_date, CustomerFollowUp.id).limit(limit).all()
    nombres = crm.nombres_de_usuarios(db, [s.assigned_user_id for s in filas])
    return {"items": [crm.seguimiento_a_dict(s, nombres) for s in filas], "hoy": date.today()}


@router.post("/seguimiento")
def crear_seguimiento(
    datos: SeguimientoIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    cliente = db.query(Customer).filter(
        Customer.id == datos.customer_id, Customer.organization_id == org_id,
    ).first()
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    tipo = (datos.tipo or "LLAMADA").upper()
    if tipo not in crm.TIPOS_SEGUIMIENTO:
        raise HTTPException(status_code=400, detail="Tipo de seguimiento desconocido.")
    asignado = datos.assigned_user_id or current_user.id
    if asignado != current_user.id:
        from app.models.users import UserOrganization
        miembro = db.query(UserOrganization).filter(
            UserOrganization.user_id == asignado, UserOrganization.organization_id == org_id,
        ).first()
        if miembro is None:
            raise HTTPException(status_code=400, detail="Esa persona no es de esta tienda.")
    tarea = CustomerFollowUp(
        organization_id=org_id, customer_id=cliente.id, branch_id=current_user.branch_id,
        tipo=tipo, nota=(datos.nota or "").strip() or None, due_date=datos.due_date,
        assigned_user_id=asignado, created_by_user_id=current_user.id,
    )
    db.add(tarea)
    db.commit()
    db.refresh(tarea)
    return crm.seguimiento_a_dict(tarea, crm.nombres_de_usuarios(db, [asignado]))


def _tarea(db: Session, org_id: int, tarea_id: int, user: User) -> CustomerFollowUp:
    tarea = db.query(CustomerFollowUp).filter(
        CustomerFollowUp.id == tarea_id, CustomerFollowUp.organization_id == org_id,
    ).first()
    if tarea is None:
        raise HTTPException(status_code=404, detail="Seguimiento no encontrado")
    if es_cajero(user) and user.id not in (tarea.assigned_user_id, tarea.created_by_user_id) \
            and tarea.branch_id != user.branch_id:
        raise HTTPException(status_code=403, detail="Ese seguimiento es de otra sucursal.")
    return tarea


@router.post("/seguimiento/{tarea_id}/hecho")
def marcar_hecho(
    tarea_id: int,
    datos: SeguimientoHecho,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    tarea = _tarea(db, org_id, tarea_id, current_user)
    if tarea.status != "HECHO":
        tarea.status = "HECHO"
        tarea.resultado = (datos.resultado or "").strip() or None
        tarea.done_by_user_id = current_user.id
        tarea.done_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(tarea)
    return crm.seguimiento_a_dict(tarea, crm.nombres_de_usuarios(db, [tarea.assigned_user_id]))


@router.delete("/seguimiento/{tarea_id}")
def borrar_seguimiento(
    tarea_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    tarea = _tarea(db, org_id, tarea_id, current_user)
    if es_cajero(current_user) and tarea.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Solo quien lo creó o la gerencia puede borrarlo.")
    db.delete(tarea)
    db.commit()
    return {"ok": True}


# ── Ficha 360 ─────────────────────────────────────────────────────────────
@router.get("/{customer_id}/ficha")
def ficha_del_cliente(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    cliente = db.query(Customer).filter(
        Customer.id == customer_id, Customer.organization_id == org_id,
    ).first()
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    datos = crm.ficha(db, org_id, cliente, user=current_user, de_caja=es_cajero(current_user))
    datos["customer"] = CustomerRead.model_validate(cliente)
    return datos
