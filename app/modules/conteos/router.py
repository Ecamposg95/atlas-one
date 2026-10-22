# app/modules/conteos/router.py
"""`/api/inventory/counts` — conteo físico con escáner.

Solo ADMINISTRADOR/DUEÑO con el módulo `inventory`. El router valida
permisos, sucursal y departamento; las reglas viven en `services`.
Diseño: docs/superpowers/specs/2026-10-22-conteo-inventario-design.md §3.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_module
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.crud.products import _is_admin
from app.models import User
from app.models.organization import Branch
from app.modules.conteos import services
from app.modules.conteos.models import ABIERTO, InventoryCount, InventoryCountLine
from app.modules.conteos.schemas import (
    ConteoCreate, ConteoDetalle, ConteoRead, LineaCreate, LineaPatch, LineaRead,
    Reporte, ScanRequest, ScanResult,
)
from app.modules.products.models import Department

router = APIRouter(dependencies=[Depends(require_module("inventory"))])


def _admin(current_user: User = Depends(get_current_user)) -> User:
    if not _is_admin(current_user):
        raise HTTPException(403, "Solo administradores y dueños pueden hacer conteos.")
    return current_user


def _conteo_o_404(db: Session, org_id: int, conteo_id: int) -> InventoryCount:
    c = (db.query(InventoryCount)
         .filter(InventoryCount.id == conteo_id, InventoryCount.organization_id == org_id)
         .first())
    if c is None:
        raise HTTPException(404, "Conteo no encontrado")
    return c


def _linea_o_404(conteo: InventoryCount, line_id: int) -> InventoryCountLine:
    l = next((x for x in conteo.lineas if x.id == line_id), None)
    if l is None:
        raise HTTPException(404, "Línea no encontrada")
    return l


def _sucursal(db: Session, org_id: int, user: User, pedida: Optional[int]) -> int:
    """Admin/dueño eligen la sucursal (recordada en el teléfono); si el usuario
    tiene sucursal propia y no manda ninguna, se usa la suya."""
    branch_id = pedida or user.branch_id
    if not branch_id:
        raise HTTPException(422, "Elige la sucursal que vas a contar.")
    b = db.query(Branch).filter(Branch.id == branch_id, Branch.organization_id == org_id).first()
    if b is None:
        raise HTTPException(404, "Sucursal no encontrada")
    return b.id


@router.post("/", response_model=ConteoRead, status_code=201)
def crear_conteo(
    body: ConteoCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_admin),
    org_id: int = Depends(get_current_active_organization),
):
    branch_id = _sucursal(db, org_id, user, body.branch_id)
    if body.department_id:
        d = (db.query(Department)
             .filter(Department.id == body.department_id, Department.organization_id == org_id)
             .first())
        if d is None:
            raise HTTPException(404, "Departamento no encontrado")
    abierto = (db.query(InventoryCount)
               .filter(InventoryCount.organization_id == org_id,
                       InventoryCount.branch_id == branch_id,
                       InventoryCount.department_id == body.department_id,
                       InventoryCount.status == ABIERTO)
               .first())
    if abierto is not None:
        raise HTTPException(409, f"Ya hay un conteo abierto (#{abierto.id}) de esa sucursal y departamento.")
    c = InventoryCount(organization_id=org_id, branch_id=branch_id,
                       department_id=body.department_id, status=ABIERTO,
                       notes=(body.notes or None), created_by_user_id=user.id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return services.a_conteo_read(db, c)


@router.get("/", response_model=List[ConteoRead])
def listar_conteos(
    status: Optional[str] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(_admin),
    org_id: int = Depends(get_current_active_organization),
):
    q = db.query(InventoryCount).filter(InventoryCount.organization_id == org_id)
    if status:
        q = q.filter(InventoryCount.status == status)
    if branch_id:
        q = q.filter(InventoryCount.branch_id == branch_id)
    return [services.a_conteo_read(db, c) for c in q.order_by(InventoryCount.created_at.desc(), InventoryCount.id.desc()).all()]


@router.get("/{conteo_id}", response_model=ConteoDetalle)
def ver_conteo(conteo_id: int, db: Session = Depends(get_db), _: User = Depends(_admin),
               org_id: int = Depends(get_current_active_organization)):
    return services.a_conteo_read(db, _conteo_o_404(db, org_id, conteo_id), con_lineas=True)


@router.post("/{conteo_id}/scan", response_model=ScanResult)
def escanear(conteo_id: int, body: ScanRequest, db: Session = Depends(get_db),
             user: User = Depends(_admin), org_id: int = Depends(get_current_active_organization)):
    return services.escanear(db, _conteo_o_404(db, org_id, conteo_id), body.code, user.id)


@router.post("/{conteo_id}/lines", response_model=LineaRead)
def agregar_linea(conteo_id: int, body: LineaCreate, db: Session = Depends(get_db),
                  user: User = Depends(_admin), org_id: int = Depends(get_current_active_organization)):
    c = _conteo_o_404(db, org_id, conteo_id)
    return services.a_linea_read(services.agregar_linea(db, c, body.variant_id, body.qty, user.id))


@router.patch("/{conteo_id}/lines/{line_id}", response_model=Optional[LineaRead])
def fijar_linea(conteo_id: int, line_id: int, body: LineaPatch, db: Session = Depends(get_db),
                _: User = Depends(_admin), org_id: int = Depends(get_current_active_organization)):
    c = _conteo_o_404(db, org_id, conteo_id)
    l = services.fijar_linea(db, c, _linea_o_404(c, line_id), body.qty_contada)
    return services.a_linea_read(l) if l is not None else None


@router.delete("/{conteo_id}/lines/{line_id}", status_code=204)
def borrar_linea(conteo_id: int, line_id: int, db: Session = Depends(get_db),
                 _: User = Depends(_admin), org_id: int = Depends(get_current_active_organization)):
    c = _conteo_o_404(db, org_id, conteo_id)
    services.fijar_linea(db, c, _linea_o_404(c, line_id), 0)
    return Response(status_code=204)


@router.post("/{conteo_id}/close", response_model=ConteoDetalle)
def cerrar_conteo(conteo_id: int, db: Session = Depends(get_db), user: User = Depends(_admin),
                  org_id: int = Depends(get_current_active_organization)):
    c = _conteo_o_404(db, org_id, conteo_id)
    services.cerrar(db, c, user.id)
    return services.a_conteo_read(db, c, con_lineas=True)


@router.get("/{conteo_id}/report", response_model=Reporte)
def reporte_conteo(conteo_id: int, db: Session = Depends(get_db), _: User = Depends(_admin),
                   org_id: int = Depends(get_current_active_organization)):
    return services.reporte(db, _conteo_o_404(db, org_id, conteo_id))
