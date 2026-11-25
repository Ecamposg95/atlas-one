"""Vales de tienda: consulta en el mostrador, lista para la gerencia y
cancelación (solo administrador/dueño). La emisión vive en la devolución
(`app/crud/returns.py`) y el cobro en `create_sale` (`app/services/vales.py`)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.security.guards import require_admin_or_owner
from app.core.tenant_context import get_current_active_organization
from app.models.users import User
from app.models.vales import StoreVoucher, StoreVoucherMovement
from app.services import vales as svc
from app.services.ventas_cajero import es_cajero

router = APIRouter()


@router.get("/")
def listar_vales(
    estado: Optional[str] = Query(None),          # ACTIVO | AGOTADO | CANCELADO
    customer_id: Optional[int] = Query(None),
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Lista de vales. La caja no la ve: consulta un vale por su código."""
    if es_cajero(current_user):
        raise HTTPException(status_code=403, detail="La lista de vales es de la gerencia. Consulta el vale por su código.")
    q = db.query(StoreVoucher).filter(StoreVoucher.organization_id == org_id)
    if estado:
        q = q.filter(StoreVoucher.status == estado.upper())
    if customer_id is not None:
        q = q.filter(StoreVoucher.customer_id == customer_id)
    total = q.count()
    filas = q.order_by(StoreVoucher.created_at.desc()).offset(skip).limit(limit).all()
    return {"items": [svc.a_dict(v) for v in filas], "total": total}


@router.get("/{codigo}")
def consultar_vale(
    codigo: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Saldo de un vale por su código (lo teclea o escanea la caja)."""
    vale = svc.buscar_vale(db, org_id, codigo)
    if vale is None:
        raise HTTPException(status_code=404, detail="No hay un vale con ese código.")
    datos = svc.a_dict(vale)
    movs = db.query(StoreVoucherMovement).filter(
        StoreVoucherMovement.voucher_id == vale.id,
        StoreVoucherMovement.organization_id == org_id,
    ).order_by(StoreVoucherMovement.created_at).all()
    datos["movimientos"] = [
        {"kind": m.kind, "amount": m.amount, "created_at": m.created_at,
         "sales_document_id": m.sales_document_id}
        for m in movs
    ]
    return datos


@router.post("/{vale_id}/cancelar")
def cancelar_vale(
    vale_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_owner),
    org_id: int = Depends(get_current_active_organization),
):
    """Anula el saldo que le quede a un vale (extraviado, emitido por error)."""
    vale = db.query(StoreVoucher).filter(
        StoreVoucher.id == vale_id, StoreVoucher.organization_id == org_id,
    ).with_for_update().first()
    if vale is None:
        raise HTTPException(status_code=404, detail="Vale no encontrado.")
    svc.cancelar_vale(db, vale, current_user.id)
    db.commit()
    db.refresh(vale)
    return svc.a_dict(vale)
