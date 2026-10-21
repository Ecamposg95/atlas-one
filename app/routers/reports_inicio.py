# app/routers/reports_inicio.py
"""Atlas BOS routers/reports_inicio — "¿cómo voy?" del Inicio básico (modo básico, 2026-10).

`GET /api/reports/inicio-basico` junta en UNA respuesta lo que la dueña de una
tienda FREE mira al entrar: vendido hoy, ayer y en 7 días; cobros de hoy por
método; lo que más se vende; lo que se está acabando y el estado de la caja.
Una PC vieja de mostrador no debe hacer cinco llamadas para pintar el inicio.

Solo lectura. Reusa el criterio de los reportes: `SALES_REPORT_STATUSES` para
"esto ya es venta", `get_daily_summary` para los cobros (descuenta el vuelto
del efectivo) y `compute_expected_cash` para la caja. Ámbito como la valuación:
ADMIN/DUEÑO/SUPERADMIN ven la org o la sucursal que pidan; GERENTE, la suya.
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.models import (
    Branch, Product, ProductVariant, SalesDocument, SalesLineItem,
    StockOnHand, User,
)
from app.models.cash import CashSession, CashSessionStatus
from app.models.users import PlatformRole, Role
from app.routers.reports import _describe_name, _mx, _today_mx, get_daily_summary
from app.schemas.reports import (
    CorteInicio, InicioBasicoResponse, PeriodoVentas, PocaExistencia,
    ProductoPocaExistencia, ProductoTop,
)
from app.services.cash_reconciliation import SALES_REPORT_STATUSES, compute_expected_cash
from app.services.existencias import umbral_poca_existencia

router = APIRouter()

MAX_POCA_EXISTENCIA = 10
MAX_TOP = 5
DIAS_SEMANA = 7


def _sucursal_del_inicio(db: Session, current_user: User, org_id: int, branch_id: Optional[int]) -> Optional[int]:
    """Sucursal que mira el inicio; None = toda la organización.

    ADMIN/DUEÑO/SUPERADMIN: la org entera o la sucursal pedida (404 si no es de
    su org). GERENTE: siempre la suya, el parámetro se ignora (403 sin
    sucursal). Los demás roles: 403.
    """
    if current_user.platform_role == PlatformRole.SUPERADMIN or current_user.role in (Role.ADMINISTRADOR, Role.DUEÑO):
        if branch_id is None:
            return None
        existe = db.query(Branch.id).filter(Branch.id == branch_id, Branch.organization_id == org_id).first()
        if existe is None:
            raise HTTPException(status_code=404, detail="Sucursal no encontrada")
        return branch_id
    if current_user.role == Role.GERENTE:
        if not current_user.branch_id:
            raise HTTPException(status_code=403, detail="Tu usuario no tiene una sucursal asignada")
        return current_user.branch_id
    raise HTTPException(status_code=403, detail="Solo administrador, dueño o gerente pueden ver el inicio")


def _filtros_venta(org_id: int, sucursal: Optional[int], desde: date, hasta: date) -> list:
    filtros = [
        SalesDocument.organization_id == org_id,
        func.date(_mx(SalesDocument.created_at)) >= desde,
        func.date(_mx(SalesDocument.created_at)) <= hasta,
        SalesDocument.status.in_(SALES_REPORT_STATUSES),
    ]
    if sucursal is not None:
        filtros.append(SalesDocument.branch_id == sucursal)
    return filtros


def _periodo(db: Session, org_id: int, sucursal: Optional[int], desde: date, hasta: date) -> PeriodoVentas:
    fila = db.query(
        func.count(SalesDocument.id).label("tickets"),
        func.coalesce(func.sum(SalesDocument.total_amount), 0).label("total"),
    ).filter(*_filtros_venta(org_id, sucursal, desde, hasta)).one()
    return PeriodoVentas(desde=desde, hasta=hasta, total=round(float(fila.total or 0), 2),
                         tickets=int(fila.tickets or 0))


def _top(db: Session, org_id: int, sucursal: Optional[int], desde: date, hasta: date) -> List[ProductoTop]:
    filas = (
        db.query(
            SalesLineItem.description,
            func.sum(SalesLineItem.quantity).label("qty"),
            func.sum(SalesLineItem.total_line).label("importe"),
        )
        .join(SalesDocument, SalesDocument.id == SalesLineItem.document_id)
        .filter(*_filtros_venta(org_id, sucursal, desde, hasta))
        .group_by(SalesLineItem.description)
        .order_by(desc("qty"), SalesLineItem.description)
        .limit(MAX_TOP)
        .all()
    )
    return [
        ProductoTop(nombre=f.description or "", cantidad=round(float(f.qty or 0), 2),
                    total=round(float(f.importe or 0), 2))
        for f in filas
    ]


def _poca_existencia(db: Session, org_id: int, sucursal: Optional[int], umbral: int) -> List[ProductoPocaExistencia]:
    """Variantes activas cuya existencia (sumada entre sucursales) es ≤ umbral.

    Sin sucursal pedida solo cuentan las que venden y siguen activas: la bodega
    de una org multi-sucursal no es "la tienda" (mismo criterio que la valuación).
    """
    existencia = func.sum(StockOnHand.qty_on_hand)
    q = (
        db.query(ProductVariant.id, Product.name, ProductVariant.variant_name, ProductVariant.sku,
                 existencia.label("existencia"))
        .select_from(StockOnHand)
        .join(ProductVariant, ProductVariant.id == StockOnHand.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .join(Branch, Branch.id == StockOnHand.branch_id)
        .filter(
            StockOnHand.organization_id == org_id,
            Product.organization_id == org_id,
            Branch.organization_id == org_id,
            Product.is_active == True,  # noqa: E712
            Product.deleted_at.is_(None),
            ProductVariant.deleted_at.is_(None),
        )
    )
    if sucursal is not None:
        q = q.filter(Branch.id == sucursal)
    else:
        q = q.filter(Branch.can_sell == True, Branch.is_active.is_(True))  # noqa: E712
    filas = (
        q.group_by(ProductVariant.id, Product.name, ProductVariant.variant_name, ProductVariant.sku)
        .having(existencia <= umbral)
        .order_by(existencia.asc(), Product.name, ProductVariant.id)
        .limit(MAX_POCA_EXISTENCIA)
        .all()
    )
    return [
        ProductoPocaExistencia(variant_id=str(f[0]), nombre=_describe_name(f[1], f[2]), sku=f[3] or "",
                               existencia=round(float(f.existencia or 0), 2))
        for f in filas
    ]


def _nombre(user: Optional[User]) -> Optional[str]:
    return (user.full_name or user.username) if user else None


def _corte(db: Session, org_id: int, sucursal: Optional[int]) -> CorteInicio:
    """El turno abierto más reciente; si no hay, el último cerrado."""
    base = db.query(CashSession).join(Branch, Branch.id == CashSession.branch_id).filter(
        Branch.organization_id == org_id,
    )
    if sucursal is not None:
        base = base.filter(CashSession.branch_id == sucursal)
    abierta = (
        base.filter(CashSession.status == CashSessionStatus.OPEN)
        .order_by(CashSession.opened_at.desc(), CashSession.id.desc())
        .first()
    )
    if abierta is not None:
        return CorteInicio(
            estado="abierto", cajera=_nombre(abierta.user), abierto_en=abierta.opened_at,
            efectivo_esperado=round(float(compute_expected_cash(db, abierta).expected), 2),
        )
    cerrada = (
        base.filter(CashSession.status == CashSessionStatus.CLOSED)
        .order_by(CashSession.closed_at.desc(), CashSession.id.desc())
        .first()
    )
    if cerrada is not None:
        return CorteInicio(
            estado="cerrado", cajera=_nombre(cerrada.user), abierto_en=cerrada.opened_at,
            cerrado_en=cerrada.closed_at,
            efectivo_contado=round(float(cerrada.closing_balance or 0), 2),
        )
    return CorteInicio(estado="sin_turno")


@router.get("/inicio-basico", response_model=InicioBasicoResponse)
def inicio_basico(
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Resumen del Inicio básico: ventas, cobros, top, poca existencia y caja."""
    sucursal = _sucursal_del_inicio(db, current_user, org_id, branch_id)
    hoy = _today_mx()
    ayer = hoy - timedelta(days=1)
    inicio_semana = hoy - timedelta(days=DIAS_SEMANA - 1)

    # `branch_id=0` es "toda la organización" para los roles de oficina en
    # get_daily_summary; el gerente llega aquí ya fijado a su sucursal.
    resumen = get_daily_summary(
        target_date=hoy, branch_id=0 if sucursal is None else sucursal,
        db=db, current_user=current_user, org_id=org_id,
    )
    por_metodo = {str(getattr(m, "value", m)): round(float(v), 2) for m, v in resumen["payments"].items()}

    umbral = umbral_poca_existencia(db, org_id)

    return InicioBasicoResponse(
        branch_id=sucursal,
        hoy=_periodo(db, org_id, sucursal, hoy, hoy),
        ayer=_periodo(db, org_id, sucursal, ayer, ayer),
        semana=_periodo(db, org_id, sucursal, inicio_semana, hoy),
        por_metodo_hoy=por_metodo,
        top_semana=_top(db, org_id, sucursal, inicio_semana, hoy),
        poca_existencia=PocaExistencia(umbral=umbral, productos=_poca_existencia(db, org_id, sucursal, umbral)),
        corte=_corte(db, org_id, sucursal),
    )
