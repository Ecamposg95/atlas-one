# app/routers/reports_inicio.py
"""Atlas BOS routers/reports_inicio — el Inicio del dueño (modo básico 2026-10, SP6 vista del dueño).

`GET /api/reports/inicio` junta en UNA respuesta lo que el dueño mira al entrar:
vendido hoy, ayer y en 7 días; cobros de hoy por método; lo que más se vende; lo
que se está acabando y el estado de la caja. Con `completo=true` (perfil
completo) suma lo que no se mueve, lo pendiente (devoluciones, turnos viejos,
diferencias de caja), las sucursales y la utilidad bruta de hoy. Una PC vieja
de mostrador no debe hacer cinco llamadas para pintar el inicio, y una FREE no
paga las consultas de las secciones que no pinta. `/inicio-basico` es el alias
del frontend anterior.

Solo lectura. Reusa el criterio de los reportes: `SALES_REPORT_STATUSES` para
"esto ya es venta", `get_daily_summary` para los cobros (descuenta el vuelto
del efectivo) y `compute_expected_cash` para la caja. Ámbito como la valuación:
ADMIN/DUEÑO/SUPERADMIN ven la org o la sucursal que pidan; GERENTE, la suya.
"""
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, exists, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.models import (
    Branch, Product, ProductVariant, SaleReturn, SalesDocument, SalesLineItem,
    StockOnHand, User,
)
from app.models.cash import CashSession, CashSessionStatus
from app.models.users import PlatformRole, Role
from app.routers.reports import _describe_name, _mx, _today_mx, get_daily_summary
from app.schemas.reports import (
    CorteInicio, DiferenciaCaja, InicioResponse, Pendientes, PeriodoVentas, PocaExistencia,
    ProductoPocaExistencia, ProductoSinMovimiento, ProductoTop, SinMovimiento, SucursalInicio,
)
from app.services.cash_reconciliation import SALES_REPORT_STATUSES, compute_expected_cash
from app.services.existencias import umbral_poca_existencia

router = APIRouter()

MAX_POCA_EXISTENCIA = 10
MAX_TOP = 5
DIAS_SEMANA = 7
MAX_SIN_MOVIMIENTO = 10
MAX_DIFERENCIAS = 10
DIAS_DIFERENCIAS = 7
HORAS_TURNO_VIEJO = 24


def _ve_costos(user: User) -> bool:
    return user.platform_role == PlatformRole.SUPERADMIN or user.role in (Role.ADMINISTRADOR, Role.DUEÑO)


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


def _existencias_del_ambito(db: Session, org_id: int, sucursal: Optional[int]):
    """Base de StockOnHand × variante × producto del ámbito (misma regla que `_poca_existencia`)."""
    q = (
        db.query(ProductVariant.id, Product.name, ProductVariant.variant_name, ProductVariant.sku,
                 ProductVariant.price, func.sum(StockOnHand.qty_on_hand).label("existencia"))
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
    return q.group_by(ProductVariant.id, Product.name, ProductVariant.variant_name, ProductVariant.sku,
                      ProductVariant.price)


def _sin_movimiento(db: Session, org_id: int, sucursal: Optional[int], dias: int) -> SinMovimiento:
    """Variantes con existencia > 0 y SIN renglón de venta válida en los últimos `dias` días.

    Solo cuentan ventas en `SALES_REPORT_STATUSES` (una cancelada no "mueve" el
    producto). Orden por importe a venta: lo que más dinero tiene parado, primero.
    """
    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    vendida = exists().where(
        SalesLineItem.variant_id == ProductVariant.id,
        SalesLineItem.document_id == SalesDocument.id,
        SalesDocument.organization_id == org_id,
        SalesDocument.status.in_(SALES_REPORT_STATUSES),
        SalesDocument.created_at >= desde,
    )
    existencia = func.sum(StockOnHand.qty_on_hand)
    importe = existencia * func.coalesce(ProductVariant.price, 0)
    filas = (
        _existencias_del_ambito(db, org_id, sucursal)
        .filter(~vendida)
        .having(existencia > 0)
        .order_by(importe.desc(), Product.name, ProductVariant.id)
        .limit(MAX_SIN_MOVIMIENTO)
        .all()
    )
    return SinMovimiento(dias=dias, productos=[
        ProductoSinMovimiento(
            variant_id=str(f[0]), nombre=_describe_name(f[1], f[2]), sku=f[3] or "",
            existencia=round(float(f.existencia or 0), 2),
            importe_venta=round(float(f.existencia or 0) * float(f[4] or 0), 2),
        )
        for f in filas
    ])


def _utilidad_bruta_hoy(db: Session, org_id: int, sucursal: Optional[int], hoy: date) -> float:
    """Venta − coalesce(costo, 0) × cantidad de hoy (mismo criterio que /daily-summary)."""
    valor = (
        db.query(func.sum(SalesLineItem.total_line
                          - func.coalesce(SalesLineItem.unit_cost, 0) * SalesLineItem.quantity))
        .join(SalesDocument, SalesDocument.id == SalesLineItem.document_id)
        .filter(*_filtros_venta(org_id, sucursal, hoy, hoy))
        .scalar()
    )
    return round(float(valor or 0), 2)


def _pendientes(db: Session, org_id: int, sucursal: Optional[int]) -> Pendientes:
    """Lo que el dueño tiene que atender: devoluciones por aprobar, turnos que
    nadie cerró y cortes recientes que no cuadraron (esperado recalculado,
    como /audit/discrepancies: el `difference` persistido puede venir de un
    conteo pre-llenado)."""
    ahora = datetime.now(timezone.utc)
    dev = db.query(func.count(SaleReturn.id)).filter(
        SaleReturn.organization_id == org_id, SaleReturn.status == "PENDING",
    )
    sesiones = db.query(CashSession).join(Branch, Branch.id == CashSession.branch_id).filter(
        Branch.organization_id == org_id,
    )
    if sucursal is not None:
        dev = dev.filter(SaleReturn.branch_id == sucursal)
        sesiones = sesiones.filter(CashSession.branch_id == sucursal)
    turnos_viejos = sesiones.filter(
        CashSession.status == CashSessionStatus.OPEN,
        CashSession.opened_at <= ahora - timedelta(hours=HORAS_TURNO_VIEJO),
    ).count()
    cerradas = (
        sesiones.filter(CashSession.status == CashSessionStatus.CLOSED,
                        CashSession.closed_at >= ahora - timedelta(days=DIAS_DIFERENCIAS))
        .order_by(CashSession.closed_at.desc(), CashSession.id.desc())
        .all()
    )
    diferencias: List[DiferenciaCaja] = []
    for s in cerradas:
        esperado = round(float(compute_expected_cash(db, s).expected), 2)
        contado = round(float(s.closing_balance or 0), 2)
        if abs(contado - esperado) < 0.005:
            continue
        diferencias.append(DiferenciaCaja(
            session_id=s.id, sucursal=s.branch.name if s.branch else "", cajera=_nombre(s.user),
            cerrado_en=s.closed_at, esperado=esperado, contado=contado,
            diferencia=round(contado - esperado, 2),
        ))
        if len(diferencias) >= MAX_DIFERENCIAS:
            break
    return Pendientes(devoluciones=int(dev.scalar() or 0), turnos_abiertos=int(turnos_viejos),
                      diferencias_caja=diferencias)


def _sucursales(db: Session, org_id: int, hoy: date, umbral: int) -> Optional[List[SucursalInicio]]:
    """Una fila por sucursal activa que vende; None si solo hay una (la sección no aporta)."""
    sucursales = (
        db.query(Branch).filter(Branch.organization_id == org_id, Branch.can_sell == True,  # noqa: E712
                                Branch.is_active.is_(True))
        .order_by(Branch.name, Branch.id).all()
    )
    if len(sucursales) < 2:
        return None
    ventas = {
        b: (int(t or 0), float(total or 0))
        for b, t, total in db.query(
            SalesDocument.branch_id, func.count(SalesDocument.id),
            func.coalesce(func.sum(SalesDocument.total_amount), 0),
        ).filter(*_filtros_venta(org_id, None, hoy, hoy)).group_by(SalesDocument.branch_id).all()
    }
    salida = []
    for b in sucursales:
        tickets, total = ventas.get(b.id, (0, 0))
        poca = (
            db.query(func.count(StockOnHand.id))
            .join(ProductVariant, ProductVariant.id == StockOnHand.variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .filter(StockOnHand.organization_id == org_id, StockOnHand.branch_id == b.id,
                    StockOnHand.qty_on_hand <= umbral,
                    Product.is_active == True, Product.deleted_at.is_(None),  # noqa: E712
                    ProductVariant.deleted_at.is_(None))
            .scalar()
        )
        salida.append(SucursalInicio(
            branch_id=b.id, nombre=b.name, ventas_hoy=round(float(total or 0), 2), tickets_hoy=int(tickets or 0),
            corte=_corte(db, org_id, b.id), poca_existencia=int(poca or 0),
        ))
    return salida


@router.get("/inicio", response_model=InicioResponse)
@router.get("/inicio-basico", response_model=InicioResponse, include_in_schema=False)
def inicio(
    branch_id: Optional[int] = None,
    completo: bool = False,
    dias_sin_movimiento: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Resumen del Inicio: ventas, cobros, top, poca existencia y caja; con
    `completo=true` también lo que no se mueve, lo pendiente, las sucursales y
    la utilidad bruta de hoy."""
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

    respuesta = InicioResponse(
        branch_id=sucursal,
        hoy=_periodo(db, org_id, sucursal, hoy, hoy),
        ayer=_periodo(db, org_id, sucursal, ayer, ayer),
        semana=_periodo(db, org_id, sucursal, inicio_semana, hoy),
        por_metodo_hoy=por_metodo,
        top_semana=_top(db, org_id, sucursal, inicio_semana, hoy),
        poca_existencia=PocaExistencia(umbral=umbral, productos=_poca_existencia(db, org_id, sucursal, umbral)),
        corte=_corte(db, org_id, sucursal),
    )
    if not completo:
        return respuesta
    respuesta.sin_movimiento = _sin_movimiento(db, org_id, sucursal, dias_sin_movimiento)
    respuesta.pendientes = _pendientes(db, org_id, sucursal)
    # El gerente ya viene fijado a su sucursal: la sección de sucursales no aplica.
    respuesta.sucursales = _sucursales(db, org_id, hoy, umbral) if sucursal is None else None
    respuesta.utilidad_bruta_hoy = _utilidad_bruta_hoy(db, org_id, sucursal, hoy) if _ve_costos(current_user) else None
    return respuesta
