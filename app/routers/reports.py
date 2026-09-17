#app/routers/reports.py
import csv
import io
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from decimal import Decimal
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo

_MX = ZoneInfo("America/Mexico_City")

def _today_mx() -> date:
    """Fecha actual en timezone Mexico/Ciudad de Mexico."""
    return datetime.now(_MX).date()

def _mx(col):
    """Convierte una columna TIMESTAMPTZ de UTC a America/Mexico_City en SQL."""
    return func.timezone("America/Mexico_City", col)

from app.core.database import get_db
from app.services.cash_reconciliation import SALES_REPORT_STATUSES
from app.models import (
    SalesDocument, SalesLineItem, Payment, 
    ProductVariant, Customer, CashSession, DocumentStatus, CustomerLedgerEntry,
    InboundShipment, Product, StockOnHand, Branch, SaleReturn
)
from app.core.security import get_current_user
from app.models import User
from app.models.cash import CashSessionStatus
from app.models.sales import PaymentMethod
from app.models.organization import BranchType
from app.schemas.reports import AgingReportResponse
from app.core.tenant_context import get_current_active_organization
from app.crud.products import _is_admin

CRITICAL_STOCK_THRESHOLD = 5


def _describe_name(name: str, variant_name: Optional[str]) -> str:
    """"Playera (Rojo / M)" o solo el nombre del producto para la variante estandar."""
    etiqueta = (variant_name or "").strip()
    return f"{name} ({etiqueta})" if etiqueta and etiqueta != "Estándar" else name

# Roles de oficina central: los unicos que pueden mirar una sucursal que no es
# la suya, o la organizacion entera.
HQ_ROLES = ("ADMINISTRADOR", "GERENTE", "DUEÑO")


def _resolver_sucursal(current_user: User, branch_id):
    """Ambito de un reporte por sucursal: `(sucursal, toda_la_organizacion)`.

    `branch_id=0` significa "toda la organizacion" y solo lo honra un rol de
    oficina central; para cualquier otro rol el parametro se ignora y se queda
    en su propia sucursal.

    El segundo valor es explicito a proposito. Antes el guard era
    `if target_branch_id`, que trata `None` --"este usuario no tiene sucursal
    asignada", `User.branch_id` es nullable-- igual que el `0` de "toda la
    organizacion": un VENDEDOR sin sucursal pasaba de no ver nada a ver la
    venta, la utilidad y el desglose de pagos del negocio completo. Con la
    bandera aparte, `None` sigue filtrando `branch_id IS NULL` (cero filas) y
    solo el `0` de un rol de oficina central levanta el filtro.
    """
    if current_user.role in HQ_ROLES:
        if branch_id == 0:
            return None, True
        if branch_id:
            return branch_id, False
    return current_user.branch_id, False


router = APIRouter()

@router.get("/daily-summary")
def get_daily_summary(
    target_date: date = None,
    branch_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """Resumen de ventas, métodos de pago y utilidad del día."""
    if not target_date:
        target_date = _today_mx()

    target_branch_id, toda_la_org = _resolver_sucursal(current_user, branch_id)
    filtros_sucursal = (
        [] if toda_la_org else [SalesDocument.branch_id == target_branch_id]
    )

    # 1. Ventas Totales por Estatus
    sales_query = db.query(
        func.count(SalesDocument.id).label("count"),
        func.sum(SalesDocument.total_amount).label("total")
    ).filter(
        SalesDocument.organization_id == org_id,
        func.date(_mx(SalesDocument.created_at)) == target_date,
        *filtros_sucursal,
        SalesDocument.status.in_(SALES_REPORT_STATUSES)
    ).first()

    # 2. Desglose por Métodos de Pago
    payments_breakdown = db.query(
        Payment.method,
        func.sum(Payment.amount).label("total")
    ).join(SalesDocument).filter(
        SalesDocument.organization_id == org_id,
        func.date(_mx(Payment.created_at)) == target_date,
        *filtros_sucursal,
        SalesDocument.status.in_(SALES_REPORT_STATUSES)
    ).group_by(Payment.method).all()

    # 3. Top 5 Productos más vendidos
    top_products = db.query(
        SalesLineItem.description,
        func.sum(SalesLineItem.quantity).label("qty")
    ).join(SalesDocument).filter(
        SalesDocument.organization_id == org_id,
        func.date(_mx(SalesDocument.created_at)) == target_date,
        *filtros_sucursal,
        SalesDocument.status.in_(SALES_REPORT_STATUSES)
    ).group_by(SalesLineItem.description).order_by(desc("qty")).limit(5).all()

    # 2.b El vuelto no es ingreso. `Payment.amount` guarda lo que el cliente
    # ENTREGO, no lo que se quedó en el cajón, así que el efectivo del día salía
    # inflado y no cuadraba contra la venta. El corte de caja ya aplica este
    # criterio (`net_cash = gross_cash - change_given`, en
    # app/services/cash_reconciliation.py); aquí se replica el criterio, no la
    # fórmula, porque el resumen agrupa por día y el corte por sesión.
    vuelto_del_dia = db.query(
        func.coalesce(func.sum(SalesDocument.change_given), 0)
    ).filter(
        SalesDocument.organization_id == org_id,
        func.date(_mx(SalesDocument.created_at)) == target_date,
        *filtros_sucursal,
        SalesDocument.status.in_(SALES_REPORT_STATUSES)
    ).scalar() or Decimal(0)

    pagos = {p.method: Decimal(str(p.total or 0)) for p in payments_breakdown}
    if PaymentMethod.CASH in pagos:
        pagos[PaymentMethod.CASH] -= Decimal(str(vuelto_del_dia))

    # 4. Cálculo de Utilidad Bruta (Venta - Costo)
    profit_data = db.query(
        func.sum(SalesLineItem.total_line - (SalesLineItem.unit_cost * SalesLineItem.quantity))
    ).join(SalesDocument).filter(
        SalesDocument.organization_id == org_id,
        func.date(_mx(SalesDocument.created_at)) == target_date,
        *filtros_sucursal,
        SalesDocument.status.in_(SALES_REPORT_STATUSES)
    ).scalar() or Decimal(0)

    return {
        "date": target_date,
        "transactions_count": sales_query.count or 0,
        "total_revenue": float(sales_query.total or 0),
        "gross_profit": float(profit_data),
        "payments": {m: float(v) for m, v in pagos.items()},
        "top_selling_items": [{"name": p.description, "quantity": float(p.qty)} for p in top_products]
    }

@router.get("/audit/discrepancies")
def get_cash_discrepancies(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """Últimos cortes cerrados con su arqueo, recalculado.

    Antes esto filtraba por `CashSession.difference != 0` sobre el valor
    PERSISTIDO y devolvía `total_cash_sales` bajo la etiqueta `expected_cash`.
    Dos problemas encadenados:

    - `total_cash_sales` es el efectivo NETO de ventas, no el esperado
      (`apertura + neto + entradas − salidas − reembolsos`), así que la fila
      mostraba Esperado/Contado/Diferencia sin que la resta cuadrara.
    - Filtrar por la diferencia persistida ocultaba los cortes cuadrados en
      0.00, que es exactamente lo que producía el auto-cuadre del conteo
      pre-llenado: la pantalla decía "sin diferencias" cuando nadie había
      contado nada.

    Ahora se listan TODOS los cortes cerrados recientes con el esperado
    recalculado por la fuente canónica, y se marca cuáles cuadran exacto para
    que un 0.00 deje de leerse como tranquilidad automática.
    """
    from sqlalchemy.orm import joinedload

    from app.services.cash_reconciliation import compute_expected_cash

    sesiones = db.query(CashSession).options(
        joinedload(CashSession.user),
        joinedload(CashSession.branch),
    ).join(CashSession.branch).filter(
        Branch.organization_id == org_id,
        CashSession.closed_at.isnot(None),
    ).order_by(desc(CashSession.closed_at)).limit(limit).all()

    salida = []
    for s in sesiones:
        esperado = Decimal(str(compute_expected_cash(db, s).expected))
        contado = Decimal(str(s.closing_balance or 0))
        diferencia = contado - esperado
        salida.append({
            "session_id": s.id,
            "branch_name": s.branch.name if s.branch else "—",
            "opened_by": s.user.full_name or s.user.username if s.user else "—",
            "opening_amount": float(s.opening_balance or 0),
            "cash_sales": float(s.total_cash_sales or 0),
            "expected_cash": float(esperado),
            "closing_amount": float(contado),
            "difference": float(diferencia),
            "exact_match": diferencia == 0,
            "closed_at": s.closed_at.isoformat() if s.closed_at else None,
        })
    return salida

@router.get("/aging-report", response_model=AgingReportResponse)
def get_aging_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Calcula la antigüedad de saldos: Clasifica la deuda de los clientes 
    en periodos de 30, 60, 90 y +90 días.
    """
    now = datetime.now()
    # 1. Obtener solo clientes que tengan saldo deudor actual
    debtor_customers = db.query(Customer).filter(
        Customer.organization_id == org_id,
        Customer.current_balance > 0
    ).all()
    
    report_list = []
    total_receivable = Decimal("0.00")

    for customer in debtor_customers:
        # Inicializamos los acumuladores para este cliente
        buckets = {
            "current": Decimal("0.00"),  # 0-30 días
            "31_60": Decimal("0.00"),
            "61_90": Decimal("0.00"),
            "91_plus": Decimal("0.00")
        }

        # 2. Analizar cargos pendientes (donde amount > 0)
        # Nota: En un sistema real, aquí podrías filtrar facturas específicas no pagadas
        ledger_entries = db.query(CustomerLedgerEntry).filter(
            CustomerLedgerEntry.organization_id == org_id,
            CustomerLedgerEntry.customer_id == customer.id,
            CustomerLedgerEntry.amount > 0 
        ).all()

        for entry in ledger_entries:
            days_old = (now - entry.created_at).days

            if days_old <= 30:
                buckets["current"] += entry.amount
            elif days_old <= 60:
                buckets["31_60"] += entry.amount
            elif days_old <= 90:
                buckets["61_90"] += entry.amount
            else:
                buckets["91_plus"] += entry.amount

        # 3. Construir objeto de respuesta para el cliente
        report_list.append({
            "customer_id": customer.id,
            "customer_name": customer.name,
            "total_balance": customer.current_balance,
            "current_0_30": buckets["current"],
            "overdue_31_60": buckets["31_60"],
            "overdue_61_90": buckets["61_90"],
            "overdue_91_plus": buckets["91_plus"]
        })
        total_receivable += customer.current_balance

    return {
        "report_date": now.date(),
        "total_receivable": total_receivable,
        "customers": report_list
    }



@router.get("/dashboard")
def get_dashboard_stats(
    start_date: date = None,
    end_date: date = None,
    branch_id: int = None, # [NEW]
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Endpoint robusto para el Dashboard y Reportes.
    Retorna KPIs, Tendencias y Alertas.
    Si no se envían fechas, usa 'hoy'.
    """
    if not start_date:
        start_date = _today_mx()
    if not end_date:
        end_date = _today_mx()

    # Determine Scope
    # Bug fix: user.role es Enum Role — `role in [strings]` siempre False.
    # Usar _is_admin() que compara contra Role enum directo.
    is_hq_user = _is_admin(current_user)

    # Determine Target Branch — default: user's own branch
    target_branch_id = current_user.branch_id

    if is_hq_user:
        if branch_id == 0:
            # 0 = ALL BRANCHES (Global View)
            target_branch_id = None
        elif branch_id:
            target_branch_id = branch_id
        # else: admin sin param → target queda como user.branch_id
        # (si admin tiene branch_id=None → global view automática)
    
    # Base Filters
    filters = [
        SalesDocument.organization_id == org_id,
        func.date(_mx(SalesDocument.created_at)) >= start_date,
        func.date(_mx(SalesDocument.created_at)) <= end_date
    ]
    
    # Apply Branch Filter if target exists
    if target_branch_id:
        filters.append(SalesDocument.branch_id == target_branch_id)


    # 1. KPIs de HOY
    # Ventas pagadas hoy
    sales_filters = filters + [SalesDocument.status == DocumentStatus.PAID]
    
    today_sales_stats = db.query(
        func.count(SalesDocument.id).label("count"),
        func.sum(SalesDocument.total_amount).label("total")
    ).filter(*sales_filters).first()
    
    today_total = float(today_sales_stats.total or 0)
    today_count = today_sales_stats.count or 0
    today_avg = today_total / today_count if today_count > 0 else 0.0

    # Estado de Piso (Tickets abiertos)
    pending_filters = filters + [SalesDocument.status == DocumentStatus.PENDING]
    pending_count = db.query(func.count(SalesDocument.id)).filter(*pending_filters).scalar() or 0
    
    draft_filters = filters + [SalesDocument.status == DocumentStatus.DRAFT]
    draft_count = db.query(func.count(SalesDocument.id)).filter(*draft_filters).scalar() or 0

    # 2. Tendencia (Rango Seleccionado)
    # 2. Tendencia (Rango Seleccionado)
    trend_data = db.query(
        func.date(SalesDocument.created_at).label("day"),
        func.sum(SalesDocument.total_amount).label("total")
    ).filter(*sales_filters).group_by("day").order_by("day").all()
    
    # Rellenar días vacíos
    trend_map = {str(r.day): float(r.total) for r in trend_data}
    chart_trend_labels = []
    chart_trend_data = []
    
    delta = end_date - start_date
    for i in range(delta.days + 1):
        d = start_date + timedelta(days=i)
        d_str = str(d)
        chart_trend_labels.append(d.strftime("%a %d")) # Mon 05
        chart_trend_data.append(trend_map.get(d_str, 0.0))

    # 3. Ventas por Hora (Hoy, en timezone México)
    hourly_data = db.query(
        func.to_char(_mx(SalesDocument.created_at), 'HH24').label("hour"),
        func.sum(SalesDocument.total_amount).label("total")
    ).filter(*sales_filters).group_by("hour").all()
    
    hourly_map = {int(r.hour): float(r.total) for r in hourly_data}
    chart_hourly_labels = []
    chart_hourly_data = []
    for h in range(8, 22): 
        chart_hourly_labels.append(f"{h}:00")
        chart_hourly_data.append(hourly_map.get(h, 0.0))

    # 4. Métodos de Pago (Hoy)
    # 4. Métodos de Pago (Hoy)
    payments_data = db.query(
        Payment.method,
        func.sum(Payment.amount).label("total")
    ).join(SalesDocument).filter(*sales_filters).group_by(Payment.method).all()
    
    payment_map = {p.method: float(p.total) for p in payments_data}
    
    # 5. Top Productos (Hoy)
    # 5. Top Productos (Hoy)
    top_products = db.query(
        SalesLineItem.description,
        func.sum(SalesLineItem.quantity).label("qty")
    ).join(SalesDocument).filter(*sales_filters).group_by(SalesLineItem.description).order_by(desc(func.sum(SalesLineItem.quantity))).limit(5).all()

    # 6. Alertas de Inventario
    # Non-admins (CAJERO/GERENTE) see only their branch's low-stock alerts (A2-17).
    _low_stock_q = db.query(
        Product.name,
        ProductVariant.sku,
        ProductVariant.variant_name,
        StockOnHand.qty_on_hand
    ).join(ProductVariant, Product.id == ProductVariant.product_id)\
     .join(StockOnHand, ProductVariant.id == StockOnHand.variant_id)\
     .filter(
        Product.organization_id == org_id,
        StockOnHand.qty_on_hand <= 5,
        Product.is_active == True
    )
    if not _is_admin(current_user) and current_user.branch_id:
        _low_stock_q = _low_stock_q.filter(StockOnHand.branch_id == current_user.branch_id)
    low_stock_query = _low_stock_q.order_by(StockOnHand.qty_on_hand.asc()).limit(10).all()

    # 7. Ventas Recientes (Limit 10)
    # 7. Ventas Recientes (Limit 10)
    recent_sales = db.query(SalesDocument).filter(*sales_filters).order_by(desc(SalesDocument.created_at)).limit(10).all()

    # 8. Total Products count
    total_products = db.query(func.count(Product.id)).filter(
        Product.organization_id == org_id,
        Product.is_active == True
    ).scalar() or 0

    # 9. Logística: Entradas Activas
    transit_shipments = db.query(func.count(InboundShipment.id)).filter(
        InboundShipment.organization_id == org_id,
        InboundShipment.status != "RECEIVED"
    ).scalar() or 0

    # 10. SKUs únicos vendidos en el rango (para KPI "Productos Vendidos")
    unique_skus_sold = db.query(func.count(func.distinct(SalesLineItem.variant_id)))\
        .join(SalesDocument).filter(*sales_filters).scalar() or 0

    # 11. Tendencia del período inmediatamente anterior (mismo largo) para comparativa
    delta_days = (end_date - start_date).days
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - timedelta(days=delta_days)

    prev_filters = [
        SalesDocument.organization_id == org_id,
        func.date(_mx(SalesDocument.created_at)) >= prev_start,
        func.date(_mx(SalesDocument.created_at)) <= prev_end,
        SalesDocument.status == DocumentStatus.PAID,
    ]
    if target_branch_id:
        prev_filters.append(SalesDocument.branch_id == target_branch_id)

    prev_trend_data = db.query(
        func.date(_mx(SalesDocument.created_at)).label("day"),
        func.sum(SalesDocument.total_amount).label("total"),
    ).filter(*prev_filters).group_by("day").order_by("day").all()
    prev_trend_map = {str(r.day): float(r.total) for r in prev_trend_data}
    chart_trend_previous = []
    for i in range(delta_days + 1):
        d = prev_start + timedelta(days=i)
        chart_trend_previous.append(prev_trend_map.get(str(d), 0.0))

    prev_total_sales = sum(chart_trend_previous)
    prev_count = db.query(func.count(SalesDocument.id)).filter(*prev_filters).scalar() or 0
    prev_avg = (prev_total_sales / prev_count) if prev_count else 0.0

    # 12. Heatmap día-de-semana × hora (0-6 dom-sab, 8-21 hrs)
    heatmap_raw = db.query(
        func.extract('dow', _mx(SalesDocument.created_at)).label("dow"),
        func.to_char(_mx(SalesDocument.created_at), 'HH24').label("hour"),
        func.sum(SalesDocument.total_amount).label("amount"),
        func.count(SalesDocument.id).label("tickets"),
    ).filter(*sales_filters).group_by("dow", "hour").all()

    heatmap_list = [
        {
            "day": int(r.dow or 0),
            "hour": int(r.hour),
            "amount": float(r.amount or 0),
            "tickets": int(r.tickets or 0),
        }
        for r in heatmap_raw
    ]

    # 13. Top products with per-day trend array (trend over the range)
    # For each of the top products (by qty), fetch daily qty so frontend can render sparklines.
    top_product_trends: dict[str, list[float]] = {}
    if top_products:
        top_names = [p.description for p in top_products]
        tp_trend_rows = db.query(
            SalesLineItem.description,
            func.date(_mx(SalesDocument.created_at)).label("day"),
            func.sum(SalesLineItem.quantity).label("qty"),
        ).join(SalesDocument).filter(
            *sales_filters,
            SalesLineItem.description.in_(top_names),
        ).group_by(SalesLineItem.description, "day").all()

        # Initialize zero-filled series per product
        for name in top_names:
            top_product_trends[name] = [0.0] * (delta_days + 1)

        for r in tp_trend_rows:
            idx = (r.day - start_date).days
            if 0 <= idx <= delta_days and r.description in top_product_trends:
                top_product_trends[r.description][idx] = float(r.qty or 0)

    return {
        "kpis": {
            "sales": today_total,
            "orders": today_count,
            "avg_ticket": today_avg,
            "pending": pending_count,
            "draft": draft_count,
            "total_products": total_products,
            "transit_shipments": transit_shipments,
            "unique_skus_sold": int(unique_skus_sold),
            "prev_sales": prev_total_sales,
            "prev_orders": int(prev_count),
            "prev_avg_ticket": prev_avg,
        },
        "charts": {
            "trend": {"labels": chart_trend_labels, "data": chart_trend_data},
            "trend_previous": {"labels": chart_trend_labels, "data": chart_trend_previous},
            "hourly": {"labels": chart_hourly_labels, "data": chart_hourly_data},
            "payments": payment_map,
            "heatmap": heatmap_list,
        },
        "top_products": [
            {
                "name": p.description,
                "qty": float(p.qty),
                "trend": top_product_trends.get(p.description, []),
            }
            for p in top_products
        ],
        "low_stock": [
            {"name": _describe_name(p.name, p.variant_name), "sku": p.sku or "", "stock": float(p.qty_on_hand)}
            for p in low_stock_query
        ],
        "recent_sales": [
            {
                "folio": f"{s.series or ''}-{s.folio}",
                "total": float(s.total_amount),
                "time": s.created_at.astimezone(_MX).strftime("%H:%M"),
                "customer": s.customer_name or "General"
            }
            for s in recent_sales
        ]
    }

@router.get("/sales-by-hour")
def get_sales_by_hour(
    date: date = None,
    branch_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """
    Ventas por hora del día indicado (default: hoy en zona MX).

    Respuesta:
    {
        "date": "2026-04-17",
        "current_hour": 15,
        "current_hour_amount": 4321.0,
        "current_hour_tickets": 12,
        "hourly": [{"hour": 8, "amount": 0.0, "tickets": 0}, ...]  # 8-21 hrs
    }
    """
    if not date:
        date = _today_mx()

    target_branch_id, toda_la_org = _resolver_sucursal(current_user, branch_id)

    filters = [
        SalesDocument.organization_id == org_id,
        func.date(_mx(SalesDocument.created_at)) == date,
        SalesDocument.status == DocumentStatus.PAID,
    ]
    if not toda_la_org:
        filters.append(SalesDocument.branch_id == target_branch_id)

    rows = db.query(
        func.to_char(_mx(SalesDocument.created_at), 'HH24').label("hour"),
        func.sum(SalesDocument.total_amount).label("amount"),
        func.count(SalesDocument.id).label("tickets"),
    ).filter(*filters).group_by("hour").all()

    by_hour = {int(r.hour): (float(r.amount or 0), int(r.tickets or 0)) for r in rows}
    hourly = [
        {"hour": h, "amount": by_hour.get(h, (0.0, 0))[0], "tickets": by_hour.get(h, (0.0, 0))[1]}
        for h in range(8, 22)
    ]

    now_mx = datetime.now(_MX)
    current_hour = now_mx.hour
    current_amount = 0.0
    current_tickets = 0
    if date == _today_mx() and current_hour in by_hour:
        current_amount, current_tickets = by_hour[current_hour]

    return {
        "date": str(date),
        "current_hour": current_hour,
        "current_hour_amount": current_amount,
        "current_hour_tickets": current_tickets,
        "hourly": hourly,
    }


@router.get("/by-waiter")
def get_sales_by_waiter(
    start_date: date = None,
    end_date: date = None,
    branch_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """
    Ventas por mesero en el rango [start_date, end_date] (default: hoy MX).

    Atribuye cada venta al mesero de la mesa (SalesDocument.server_user_id);
    si la venta no vino de una mesa (mostrador), cae al cajero (seller_id).
    Incluye propinas acumuladas por mesero.
    """
    if not start_date:
        start_date = _today_mx()
    if not end_date:
        end_date = start_date

    is_hq_user = current_user.role in ["ADMINISTRADOR", "GERENTE", "DUEÑO"]
    target_branch_id = current_user.branch_id
    if is_hq_user:
        if branch_id == 0:
            target_branch_id = None
        elif branch_id:
            target_branch_id = branch_id

    key = func.coalesce(SalesDocument.server_user_id, SalesDocument.seller_id)
    filters = [
        SalesDocument.organization_id == org_id,
        func.date(_mx(SalesDocument.created_at)) >= start_date,
        func.date(_mx(SalesDocument.created_at)) <= end_date,
        SalesDocument.status == DocumentStatus.PAID,
    ]
    if target_branch_id:
        filters.append(SalesDocument.branch_id == target_branch_id)

    rows = db.query(
        key.label("uid"),
        func.count(SalesDocument.id).label("tickets"),
        func.sum(SalesDocument.total_amount).label("revenue"),
        func.coalesce(func.sum(SalesDocument.tip_amount), 0).label("tips"),
    ).filter(*filters).group_by(key).all()

    uids = [int(r.uid) for r in rows if r.uid is not None]
    names: Dict[int, str] = {}
    if uids:
        for u in db.query(User).filter(User.id.in_(uids)).all():
            names[u.id] = getattr(u, "full_name", None) or u.username

    waiters = []
    for r in rows:
        if r.uid is None:
            continue
        uid = int(r.uid)
        tickets = int(r.tickets or 0)
        revenue = float(r.revenue or 0)
        waiters.append({
            "user_id": uid,
            "name": names.get(uid, f"Usuario {uid}"),
            "tickets": tickets,
            "revenue": revenue,
            "tips": float(r.tips or 0),
            "avg_ticket": revenue / tickets if tickets else 0.0,
        })
    waiters.sort(key=lambda w: w["revenue"], reverse=True)

    return {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "waiters": waiters,
    }


@router.get("/command-center/stats")
def get_command_center_stats(
    start_date: date = None, 
    end_date: date = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Mission Control Data Aggregation.
    Provides deep insights for multi-branch management.
    """
    if not start_date: start_date = _today_mx()
    if not end_date: end_date = _today_mx()

    # --- 1. GLOBAL KPIS (Aggregated) ---
    # Sales Filter
    sales_filters = [
        SalesDocument.organization_id == org_id,
        func.date(_mx(SalesDocument.created_at)) >= start_date,
        func.date(_mx(SalesDocument.created_at)) <= end_date,
        SalesDocument.status == DocumentStatus.PAID
    ]

    # Total Sales & Tickets
    global_kpis = db.query(
        func.sum(SalesDocument.total_amount).label("sales"),
        func.count(SalesDocument.id).label("tickets"),
        func.sum(func.coalesce(SalesDocument.total_amount,0) - func.coalesce(SalesDocument.tax_amount,0)).label("net_sales") # Net
    ).filter(*sales_filters).first()

    total_sales = float(global_kpis.sales or 0)
    total_tickets = global_kpis.tickets or 0
    avg_ticket = total_sales / total_tickets if total_tickets > 0 else 0

    # 1a. Growth Calculation
    delta = end_date - start_date
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - delta
    
    prev_sales_filters = [
        SalesDocument.organization_id == org_id,
        func.date(_mx(SalesDocument.created_at)) >= prev_start,
        func.date(_mx(SalesDocument.created_at)) <= prev_end,
        SalesDocument.status == DocumentStatus.PAID
    ]
    prev_total = db.query(func.sum(SalesDocument.total_amount)).filter(*prev_sales_filters).scalar() or 0
    prev_total = float(prev_total)
    
    sales_growth = 0.0
    if prev_total > 0:
        sales_growth = ((total_sales - prev_total) / prev_total) * 100
    elif total_sales > 0:
        sales_growth = 100.0 # From zero to hero

    # Cancellations (Global)
    cancel_filters = [
         SalesDocument.organization_id == org_id,
         func.date(_mx(SalesDocument.created_at)) >= start_date,
         func.date(_mx(SalesDocument.created_at)) <= end_date,
         SalesDocument.status == DocumentStatus.CANCELLED
    ]
    cancel_stats = db.query(
        func.count(SalesDocument.id).label("count"),
        func.sum(SalesDocument.total_amount).label("total")
    ).filter(*cancel_filters).first()
    cancel_count = cancel_stats.count or 0
    cancel_total = float(cancel_stats.total or 0)

    # Returns (Global)
    return_filters = [
        SaleReturn.organization_id == org_id,
        func.date(_mx(SaleReturn.created_at)) >= start_date,
        func.date(_mx(SaleReturn.created_at)) <= end_date,
        SaleReturn.status == "APPROVED"
    ]
    returns_total = db.query(func.sum(SaleReturn.total_refunded)).filter(*return_filters).scalar() or 0
    returns_total = float(returns_total)

    # Items Per Ticket
    total_items = db.query(func.sum(SalesLineItem.quantity)).join(SalesDocument)\
        .filter(*sales_filters).scalar() or 0
    items_per_ticket = float(total_items) / total_tickets if total_tickets > 0 else 0

    # Payment Methods Global
    payments = db.query(
        Payment.method,
        func.sum(Payment.amount).label("total")
    ).join(SalesDocument).filter(*sales_filters).group_by(Payment.method).all()
    payment_map = {p.method: float(p.total) for p in payments}

    # Hourly Sales Global (en timezone México)
    hourly_data = db.query(
        func.to_char(_mx(SalesDocument.created_at), 'HH24').label("hour"),
        func.sum(SalesDocument.total_amount).label("total")
    ).filter(*sales_filters).group_by("hour").all()
    hourly_map = {int(r.hour): float(r.total) for r in hourly_data}

    # --- 2. BRANCH BREAKDOWN ---
    # Aggregate queries (no N+1): sales-per-branch, open-sessions, critical-stock.
    branches_db = db.query(Branch).filter(Branch.organization_id == org_id).all()

    sales_by_branch = dict(
        db.query(
            SalesDocument.branch_id,
            func.coalesce(func.sum(SalesDocument.total_amount), 0),
        ).filter(*sales_filters).group_by(SalesDocument.branch_id).all()
    )

    branch_ids = [b.id for b in branches_db]
    sessions_by_branch: Dict[int, list] = {}
    if branch_ids:
        open_sessions_rows = db.query(
            CashSession.branch_id,
            CashSession.id,
            CashSession.opened_at,
            User.username,
        ).join(User, CashSession.user_id == User.id).filter(
            CashSession.status == CashSessionStatus.OPEN,
            CashSession.branch_id.in_(branch_ids),
        ).all()
        for row in open_sessions_rows:
            sessions_by_branch.setdefault(row.branch_id, []).append(row)

    critical_by_branch = dict(
        db.query(
            StockOnHand.branch_id,
            func.count(StockOnHand.id),
        ).filter(
            StockOnHand.organization_id == org_id,
            StockOnHand.qty_on_hand <= CRITICAL_STOCK_THRESHOLD,
            StockOnHand.is_active == True,
        ).group_by(StockOnHand.branch_id).all()
    )

    branches_data = []
    for b in branches_db:
        b_sales = float(sales_by_branch.get(b.id, 0) or 0)
        b_sessions = sessions_by_branch.get(b.id, [])
        open_sessions = len(b_sessions)
        status = "ONLINE" if open_sessions > 0 or b_sales > 0 else "OFFLINE"
        branches_data.append({
            "id": b.id,
            "name": b.name,
            "status": status,
            "total_sales": b_sales,
            "pending_cuts": open_sessions,
            "pending_users": [
                {"session_id": s.id, "user": s.username, "opened": s.opened_at.isoformat() if s.opened_at else None}
                for s in b_sessions
            ],
            "critical_stock": int(critical_by_branch.get(b.id, 0) or 0),
            "is_hq": b.branch_type == BranchType.HQ,
        })

    # --- 3. ALERTS & NOTIFICATIONS ---
    alerts = []
    # Inventory Alerts — same threshold as the branch counter so both numbers agree.
    # Non-admins (CAJERO/GERENTE) see only their branch's critical stock (A2-16).
    _alerts_q = db.query(
        Product.name, ProductVariant.variant_name, StockOnHand.qty_on_hand, Branch.name.label("branch_name")
    ).select_from(StockOnHand)\
     .join(ProductVariant)\
     .join(Product)\
     .join(Branch)\
     .filter(
        StockOnHand.organization_id == org_id,
        StockOnHand.qty_on_hand <= CRITICAL_STOCK_THRESHOLD,
        Product.is_active == True,
        StockOnHand.is_active == True
    )
    if not _is_admin(current_user) and current_user.branch_id:
        _alerts_q = _alerts_q.filter(StockOnHand.branch_id == current_user.branch_id)
    low_stock = _alerts_q.limit(10).all()

    _now_iso = datetime.now(_MX).isoformat()
    for ls in low_stock:
        alerts.append({
            "type": "CRITICAL",
            "msg": f"Stock crítico ({float(ls.qty_on_hand)}) en {_describe_name(ls.name, ls.variant_name)}",
            "source": ls.branch_name,
            "time": _now_iso,
        })

    # --- 4. TOP PRODUCTS (by product_id so variants of the same product roll up,
    # and rename-safe instead of grouping by free-text description) ---
    top_revenue = db.query(
        Product.id.label("product_id"),
        Product.name.label("name"),
        func.sum(SalesLineItem.quantity).label("qty"),
        func.sum(SalesLineItem.total_line).label("revenue"),
    ).join(SalesDocument, SalesDocument.id == SalesLineItem.document_id)\
     .join(ProductVariant, ProductVariant.id == SalesLineItem.variant_id)\
     .join(Product, Product.id == ProductVariant.product_id)\
     .filter(*sales_filters)\
     .group_by(Product.id, Product.name).order_by(desc("revenue")).limit(8).all()

    return {
        "global": {
            "total_sales": total_sales,
            "total_tickets": total_tickets,
            "ticket_average": avg_ticket,
            "items_per_ticket": items_per_ticket,
            "canceled_tickets": cancel_count,
            "overrides_total": cancel_total, # Mapped to Cancellations for now
            "returns_total": returns_total,
            "sales_growth": sales_growth
        },
        "payment_methods": payment_map,
        "hourly_distribution": [{"hour": h, "amount": hourly_map.get(h, 0)} for h in range(8, 22)],
        "branches": branches_data,
        # IDs of branches that contributed to the aggregation — helps debug
        # claims that a branch is missing from the HQ totals.
        "branches_included": [b["id"] for b in branches_data],
        "alerts": alerts,
        "top_products": [
            {
                "name": p.name,
                "qty": float(p.qty or 0),
                "value": float(p.revenue),
                "metric": "Venta",
            }
            for p in top_revenue
        ]
    }

@router.get("/product/{product_id}")
def get_product_analytics(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Analítica profunda de un producto específico.
    """
    # 1. Validar producto (tenant + branch visibility para no-admins) — A2-15.
    from app.crud.products import get_product_if_visible
    product = get_product_if_visible(db, current_user, org_id, product_id)
    if not product:
        return {}

    # 2. Total Histórico (Quantity & Revenue)
    stats = db.query(
        func.sum(SalesLineItem.quantity).label("total_qty"),
        func.sum(SalesLineItem.total_line).label("total_revenue"),
        func.max(SalesDocument.created_at).label("last_sale")
    ).join(ProductVariant, ProductVariant.id == SalesLineItem.variant_id)\
     .join(SalesDocument, SalesDocument.id == SalesLineItem.document_id)\
     .filter(
         SalesDocument.organization_id == org_id,
         ProductVariant.product_id == product_id,
         SalesDocument.status == DocumentStatus.PAID
     ).first()

    # 3. Tendencia Mensual (Últimos 12 meses)
    one_year_ago = _today_mx() - timedelta(days=365)
    monthly_trend = db.query(
        func.to_char(SalesDocument.created_at, 'YYYY-MM').label("month"),
        func.sum(SalesLineItem.quantity).label("qty")
    ).join(ProductVariant, ProductVariant.id == SalesLineItem.variant_id)\
     .join(SalesDocument, SalesDocument.id == SalesLineItem.document_id)\
     .filter(
         SalesDocument.organization_id == org_id,
         ProductVariant.product_id == product_id,
         SalesDocument.status == DocumentStatus.PAID,
         SalesDocument.created_at >= one_year_ago
     ).group_by("month").order_by("month").all()

    # Formatear tendencia
    trend_labels = [r.month for r in monthly_trend]
    trend_data = [float(r.qty) for r in monthly_trend]

    return {
        "product_name": product.name,
        "total_sold": float(stats.total_qty or 0),
        "total_revenue": float(stats.total_revenue or 0),
        "last_sale": stats.last_sale,
        "trend": {
            "labels": trend_labels,
            "data": trend_data
        }
    }


@router.get("/export/csv")
def export_dashboard_csv(
    start_date: date = None,
    end_date: date = None,
    branch_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    CSV export for the HQ Reports Hub dashboard.
    Sections: KPIs, Top Products, Hourly Distribution, Low Stock Alerts.
    Filename: reports_{start_date}_{end_date}.csv
    """
    if not start_date:
        start_date = _today_mx()
    if not end_date:
        end_date = _today_mx()

    # --- Scope resolution (mirrors /dashboard) ---
    is_hq_user = current_user.role in ["ADMINISTRADOR", "GERENTE", "DUEÑO"]
    target_branch_id = current_user.branch_id
    if is_hq_user:
        if branch_id == 0:
            target_branch_id = None
        elif branch_id:
            target_branch_id = branch_id

    base_filters = [
        SalesDocument.organization_id == org_id,
        func.date(_mx(SalesDocument.created_at)) >= start_date,
        func.date(_mx(SalesDocument.created_at)) <= end_date,
    ]
    if target_branch_id:
        base_filters.append(SalesDocument.branch_id == target_branch_id)

    sales_filters = base_filters + [SalesDocument.status == DocumentStatus.PAID]

    # --- KPIs ---
    sales_stats = db.query(
        func.count(SalesDocument.id).label("count"),
        func.sum(SalesDocument.total_amount).label("total"),
    ).filter(*sales_filters).first()

    total_sales = float(sales_stats.total or 0)
    total_orders = sales_stats.count or 0
    avg_ticket = (total_sales / total_orders) if total_orders else 0.0

    total_products = db.query(func.count(Product.id)).filter(
        Product.organization_id == org_id,
        Product.is_active == True,
    ).scalar() or 0

    transit_shipments = db.query(func.count(InboundShipment.id)).filter(
        InboundShipment.organization_id == org_id,
        InboundShipment.status != "RECEIVED",
    ).scalar() or 0

    # Unique SKUs sold in range
    unique_skus = db.query(func.count(func.distinct(SalesLineItem.variant_id)))\
        .join(SalesDocument).filter(*sales_filters).scalar() or 0

    # --- Top products ---
    top_products = db.query(
        SalesLineItem.description,
        func.sum(SalesLineItem.quantity).label("qty"),
    ).join(SalesDocument).filter(*sales_filters)\
     .group_by(SalesLineItem.description)\
     .order_by(desc(func.sum(SalesLineItem.quantity)))\
     .limit(10).all()

    # --- Hourly distribution ---
    hourly_data = db.query(
        func.to_char(_mx(SalesDocument.created_at), 'HH24').label("hour"),
        func.sum(SalesDocument.total_amount).label("total"),
    ).filter(*sales_filters).group_by("hour").all()
    hourly_map = {int(r.hour): float(r.total) for r in hourly_data}

    # --- Low stock ---
    _low_q = db.query(
        Product.name, ProductVariant.sku, ProductVariant.variant_name, StockOnHand.qty_on_hand
    ).join(ProductVariant, Product.id == ProductVariant.product_id)\
     .join(StockOnHand, ProductVariant.id == StockOnHand.variant_id)\
     .filter(
        Product.organization_id == org_id,
        StockOnHand.qty_on_hand <= 5,
        Product.is_active == True,
    )
    if not _is_admin(current_user) and current_user.branch_id:
        _low_q = _low_q.filter(StockOnHand.branch_id == current_user.branch_id)
    low_stock = _low_q.order_by(StockOnHand.qty_on_hand.asc()).limit(10).all()

    # --- Build CSV ---
    output = io.StringIO()
    output.write(u"\ufeff")  # BOM for Excel UTF-8
    writer = csv.writer(output)

    writer.writerow(["Reporte Atlas HQ"])
    writer.writerow(["Rango", f"{start_date}", f"{end_date}"])
    writer.writerow(["Generado", datetime.now(_MX).strftime("%Y-%m-%d %H:%M:%S")])
    writer.writerow([])

    writer.writerow(["KPIs"])
    writer.writerow(["Métrica", "Valor"])
    writer.writerow(["Ventas Totales", f"{total_sales:.2f}"])
    writer.writerow(["Transacciones", total_orders])
    writer.writerow(["Ticket Promedio", f"{avg_ticket:.2f}"])
    writer.writerow(["Productos Vendidos (SKUs únicos)", int(unique_skus)])
    writer.writerow(["Catálogo Activo", total_products])
    writer.writerow(["En Tránsito", transit_shipments])
    writer.writerow([])

    writer.writerow(["Top 10 Productos"])
    writer.writerow(["#", "Producto", "Unidades Vendidas"])
    for i, p in enumerate(top_products, start=1):
        writer.writerow([i, p.description or "", f"{float(p.qty or 0):.2f}"])
    writer.writerow([])

    writer.writerow(["Distribución Horaria"])
    writer.writerow(["Hora", "Ventas ($)"])
    for h in range(8, 22):
        writer.writerow([f"{h:02d}:00", f"{hourly_map.get(h, 0.0):.2f}"])
    writer.writerow([])

    writer.writerow(["Alertas Stock Bajo"])
    writer.writerow(["SKU", "Producto", "Existencia"])
    for r in low_stock:
        writer.writerow([r.sku or "", _describe_name(r.name, r.variant_name) or "", f"{float(r.qty_on_hand or 0):.2f}"])

    output.seek(0)
    filename = f"reports_{start_date}_{end_date}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )