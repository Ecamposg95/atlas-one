#app/routers/reports.py
import csv
import io
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from decimal import Decimal
from datetime import datetime, date, timedelta, timezone
from typing import Dict, Optional

from app.services import metricas_ventas as mv

# Alias para quien aún importa de aquí (reports_inicio, reports_valuacion).
_MX = mv.MX
_today_mx = mv.hoy_mx
_mx = mv.mx

from app.core.database import get_db
from app.models import (
    SalesDocument, SalesLineItem,
    ProductVariant, Customer, CashSession, DocumentStatus, CustomerLedgerEntry,
    InboundShipment, Product, StockOnHand, Branch
)
from app.core.security import get_current_user
from app.models import User
from app.models.users import Role
from app.models.cash import CashSessionStatus
from app.models.organization import BranchType
from app.schemas.reports import AgingReportResponse
from app.core.tenant_context import get_current_active_organization
from app.crud.products import _is_admin
from app.services.existencias import umbral_poca_existencia


def _describe_name(name: str, variant_name: Optional[str]) -> str:
    """"Playera (Rojo / M)" o solo el nombre del producto para la variante estandar."""
    etiqueta = (variant_name or "").strip()
    return f"{name} ({etiqueta})" if etiqueta and etiqueta != "Estándar" else name


router = APIRouter()

@router.get("/daily-summary")
def get_daily_summary(
    target_date: date = None,
    branch_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """Resumen del día: venta neta (cobradas menos devoluciones aprobadas),
    cobros por método (sin vuelto, netos de devoluciones), utilidad bruta y lo
    más vendido. Criterio único en `app/services/metricas_ventas.py`."""
    periodo = mv.Periodo(target_date, target_date) if target_date else mv.periodo_preset("hoy")
    ambito = mv.resolver_ambito(current_user, org_id, branch_id)
    r = mv.resumen(db, ambito, periodo)
    # Contrato A-8 de este endpoint: la línea sin costo suma su ingreso entero
    # (costo 0). `utilidad_bruta` separa lo que tiene costo de lo que no; juntas
    # dan `total_line - coalesce(costo, 0) * cantidad` solo sin devoluciones
    # aprobadas; con devoluciones la cifra también netea el margen devuelto,
    # igual que el ingreso.
    utilidad, sin_costo = mv.utilidad_bruta(db, ambito, periodo)
    return {
        "date": periodo.inicio,
        "transactions_count": r.tickets,
        "total_revenue": r.neta,
        "gross_revenue": r.bruta,
        "returns_total": r.devuelto,
        "returns_count": r.devoluciones,
        # `gross_profit` de este endpoint es el contrato A-8 (suma lo sin costo con costo 0);
        # el de `/dashboard` es solo sobre renglones con costo. No son comparables entre sí.
        "gross_profit": round(utilidad + sin_costo, 2),
        "payments": {k: m.total for k, m in mv.por_metodo(db, ambito, periodo).items()},
        "top_selling_items": [{"name": p.nombre, "quantity": p.cantidad}
                              for p in mv.top_productos(db, ambito, periodo, limite=5)],
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
    # `created_at` es TIMESTAMPTZ: en Postgres vuelve con tzinfo y restarle un
    # `datetime.now()` naive revienta con TypeError (500). En SQLite vuelve
    # naive, por eso la suite no lo veía. Se normalizan ambos lados a UTC.
    # Auditoría A-9.
    now = datetime.now(timezone.utc)
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
            creado = entry.created_at
            if creado is None:
                continue
            if creado.tzinfo is None:
                creado = creado.replace(tzinfo=timezone.utc)
            days_old = (now - creado).days

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
    """KPIs, tendencias y alertas del periodo. Venta neta y día de México por `app/services/metricas_ventas.py`; roles de oficina sin `branch_id` ven toda la organización, salvo GERENTE (siempre su sucursal)."""
    periodo = mv.periodo_de_query(start_date, end_date)      # una sola fecha = ese día; invertido = 422
    ambito = mv.resolver_ambito(current_user, org_id, branch_id)
    if current_user.role == Role.GERENTE:   # branch-scoped como read_sales: la lista de abajo es de su sucursal
        ambito = mv.Ambito(org_id, current_user.branch_id, False)
    filtros = mv.filtros_documentos(ambito, periodo)

    # 1. KPIs del periodo (neto) y comparativo del periodo anterior
    actual = mv.resumen(db, ambito, periodo)
    anterior = mv.resumen(db, ambito, periodo.anterior())
    pendientes = {
        st: db.query(func.count(SalesDocument.id)).filter(
            SalesDocument.organization_id == org_id, SalesDocument.status == st,
            mv.dia_mx(SalesDocument.created_at) >= periodo.inicio,
            mv.dia_mx(SalesDocument.created_at) <= periodo.fin,
            *([] if ambito.toda_la_org else [SalesDocument.branch_id == ambito.branch_id]),
        ).scalar() or 0
        for st in (DocumentStatus.PENDING, DocumentStatus.DRAFT)
    }

    # 1b. Utilidad bruta del periodo y del anterior: solo renglones con costo, menos lo
    # devuelto por el costo de su variante (metricas_ventas.utilidad_bruta). Quien no ve
    # costos (gerente) recibe None en los cuatro.
    utilidad = utilidad_prev = sin_costo = con_costo = None
    if mv.ve_costos(current_user):
        utilidad, sin_costo = mv.utilidad_bruta(db, ambito, periodo)
        con_costo = mv.venta_con_costo(db, ambito, periodo)
        utilidad_prev, _ = mv.utilidad_bruta(db, ambito, periodo.anterior())

    # 2. Tendencia por día de México (antes agrupaba por día UTC)
    dias = mv.por_dia(db, ambito, periodo)
    dias_prev = mv.por_dia(db, ambito, periodo.anterior())
    etiquetas = [d.fecha.strftime("%a %d") for d in dias]

    # 3. Por hora: las 24 (quien pinta recorta)
    horas = mv.por_hora(db, ambito, periodo)

    # 4. Cobros por método, netos de vuelto y devoluciones
    metodos = {k: {"total": m.total, "count": m.tickets} for k, m in mv.por_metodo(db, ambito, periodo).items()}

    # 5. Top productos del periodo, por piezas, con su importe (Reportes pinta hasta 10)
    top = mv.top_productos(db, ambito, periodo, limite=10)

    # 6. Alertas de inventario — el tope es el de la empresa (SP6, umbral único).
    umbral = umbral_poca_existencia(db, org_id)
    _low_stock_q = db.query(
        Product.name, ProductVariant.sku, ProductVariant.variant_name, StockOnHand.qty_on_hand,
    ).join(ProductVariant, Product.id == ProductVariant.product_id)\
     .join(StockOnHand, ProductVariant.id == StockOnHand.variant_id)\
     .filter(
        Product.organization_id == org_id,
        StockOnHand.organization_id == org_id,
        StockOnHand.qty_on_hand <= umbral,
        StockOnHand.is_active.is_(True),
        Product.is_active == True,
        Product.deleted_at.is_(None),
        ProductVariant.deleted_at.is_(None),
    )
    if not ambito.toda_la_org:
        _low_stock_q = _low_stock_q.filter(StockOnHand.branch_id == ambito.branch_id)
    low_stock_query = _low_stock_q.order_by(StockOnHand.qty_on_hand.asc()).limit(10).all()

    # 7. Ventas recientes
    recent_sales = db.query(SalesDocument).filter(*filtros).order_by(desc(SalesDocument.created_at)).limit(10).all()

    # 8. Productos activos y 9. entradas en tránsito
    total_products = db.query(func.count(Product.id)).filter(
        Product.organization_id == org_id, Product.is_active == True).scalar() or 0
    transit_shipments = db.query(func.count(InboundShipment.id)).filter(
        InboundShipment.organization_id == org_id, InboundShipment.status != "RECEIVED").scalar() or 0

    # 10. SKUs distintos vendidos (bruto: base mixta, Fase 2 decide)
    unique_skus_sold = db.query(func.count(func.distinct(SalesLineItem.variant_id)))\
        .join(SalesDocument).filter(*filtros).scalar() or 0

    # 11. Mapa día-de-semana × hora (bruto: base mixta, Fase 2 decide)
    heatmap_raw = db.query(
        func.extract('dow', mv.mx(SalesDocument.created_at)).label("dow"),
        func.to_char(mv.mx(SalesDocument.created_at), 'HH24').label("hour"),
        func.sum(SalesDocument.total_amount).label("amount"),
        func.count(SalesDocument.id).label("tickets"),
    ).filter(*filtros).group_by("dow", "hour").all()
    heatmap_list = [
        {"day": int(r.dow or 0), "hour": int(r.hour), "amount": float(r.amount or 0), "tickets": int(r.tickets or 0)}
        for r in heatmap_raw
    ]

    # 12. Serie diaria de cada top (para la gráfica de proporción)
    top_product_trends: dict[str, list[float]] = {}
    if top:
        nombres = [p.nombre for p in top]
        filas = db.query(
            SalesLineItem.description,
            mv.dia_mx(SalesDocument.created_at).label("day"),
            func.sum(SalesLineItem.quantity).label("qty"),
        ).join(SalesDocument).filter(*filtros, SalesLineItem.description.in_(nombres))\
         .group_by(SalesLineItem.description, "day").all()
        indice = {str(f): i for i, f in enumerate(periodo.fechas())}
        for n in nombres:
            top_product_trends[n] = [0.0] * periodo.dias
        for r in filas:
            i = indice.get(str(r.day))
            if i is not None and r.description in top_product_trends:
                top_product_trends[r.description][i] = float(r.qty or 0)

    return {
        "kpis": {
            "sales": actual.neta,
            "gross_sales": actual.bruta,
            "returns": actual.devuelto,
            "returns_count": actual.devoluciones,
            "orders": actual.tickets,
            "avg_ticket": actual.ticket_promedio,
            "pending": int(pendientes[DocumentStatus.PENDING]),
            "draft": int(pendientes[DocumentStatus.DRAFT]),
            "total_products": total_products,
            "transit_shipments": transit_shipments,
            "unique_skus_sold": int(unique_skus_sold),
            "prev_sales": anterior.neta,
            "prev_orders": anterior.tickets,
            "prev_avg_ticket": anterior.ticket_promedio,
            "prev_returns": anterior.devuelto,
            # OJO: aquí `gross_profit` es SOLO sobre renglones con costo (los sin costo van
            # en `sales_without_cost`); en `/daily-summary` es el contrato A-8, que suma
            # la línea sin costo con costo 0. Mismo nombre, dos significados.
            "gross_profit": utilidad,
            "prev_gross_profit": utilidad_prev,
            "sales_without_cost": sin_costo,
            "sales_with_cost": con_costo,
        },
        "charts": {
            "trend": {"labels": etiquetas, "data": [d.neta for d in dias]},
            "trend_previous": {"labels": etiquetas, "data": [d.neta for d in dias_prev]},
            "hourly": {"labels": [f"{h.hora}:00" for h in horas], "data": [h.neta for h in horas]},
            "payments": metodos,
            "heatmap": heatmap_list,
        },
        "top_products": [
            {"name": p.nombre, "qty": p.cantidad, "total": p.total, "trend": top_product_trends.get(p.nombre, [])} for p in top
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
                "customer": s.customer_name or "General",
            }
            for s in recent_sales
        ],
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
        "hourly": [{"hour": 0, "amount": 0.0, "tickets": 0}, ...]  # 0-23 hrs
    }
    """
    dia = date or mv.hoy_mx()
    ambito = mv.resolver_ambito(current_user, org_id, branch_id)
    horas = mv.por_hora(db, ambito, mv.Periodo(dia, dia))
    hora_actual = datetime.now(_MX).hour
    actual = horas[hora_actual] if dia == mv.hoy_mx() else None
    return {
        "date": str(dia),
        "current_hour": hora_actual,
        "current_hour_amount": actual.neta if actual else 0.0,
        "current_hour_tickets": actual.tickets if actual else 0,
        "hourly": [{"hour": h.hora, "amount": h.neta, "tickets": h.tickets} for h in horas],
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
    periodo = mv.periodo_de_query(start_date, end_date)      # una sola fecha = ese día; invertido = 422
    ambito = mv.Ambito(org_id, None, True)          # el centro de mando siempre es de toda la org
    sales_filters = mv.filtros_documentos(ambito, periodo)

    actual = mv.resumen(db, ambito, periodo)
    anterior = mv.resumen(db, ambito, periodo.anterior())
    total_sales = actual.neta
    total_tickets = actual.tickets
    avg_ticket = actual.ticket_promedio
    if anterior.neta > 0:
        sales_growth = ((total_sales - anterior.neta) / anterior.neta) * 100
    elif total_sales > 0:
        sales_growth = 100.0
    else:
        sales_growth = 0.0

    # Canceladas del periodo (informativo)
    cancel_stats = db.query(
        func.count(SalesDocument.id).label("count"),
        func.sum(SalesDocument.total_amount).label("total")
    ).filter(
        SalesDocument.organization_id == org_id,
        mv.dia_mx(SalesDocument.created_at) >= periodo.inicio,
        mv.dia_mx(SalesDocument.created_at) <= periodo.fin,
        SalesDocument.status == DocumentStatus.CANCELLED,
    ).first()
    cancel_count = cancel_stats.count or 0
    cancel_total = float(cancel_stats.total or 0)

    returns_total = actual.devuelto

    total_items = db.query(func.sum(SalesLineItem.quantity)).join(SalesDocument)\
        .filter(*sales_filters).scalar() or 0
    items_per_ticket = float(total_items) / total_tickets if total_tickets > 0 else 0   # bruto: base mixta, Fase 2 decide

    payment_map = {k: m.total for k, m in mv.por_metodo(db, ambito, periodo).items()}
    horas = mv.por_hora(db, ambito, periodo)

    # --- 2. BRANCH BREAKDOWN ---
    # Aggregate queries (no N+1): sales-per-branch, open-sessions, critical-stock.
    branches_db = db.query(Branch).filter(Branch.organization_id == org_id).all()

    por_sucursal = mv.por_sucursal(db, org_id, periodo)

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

    umbral = umbral_poca_existencia(db, org_id)   # SP6: el tope de la empresa, no 5 fijo
    critical_by_branch = dict(
        db.query(
            StockOnHand.branch_id,
            func.count(StockOnHand.id),
        ).filter(
            StockOnHand.organization_id == org_id,
            StockOnHand.qty_on_hand <= umbral,
            StockOnHand.is_active == True,
        ).group_by(StockOnHand.branch_id).all()
    )

    branches_data = []
    for b in branches_db:
        b_sales = por_sucursal.get(b.id, mv.RESUMEN_VACIO).neta
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
        StockOnHand.qty_on_hand <= umbral,
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
        "hourly_distribution": [{"hour": h.hora, "amount": h.neta} for h in horas],
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

    # --- Low stock (tope de la empresa, SP6) ---
    _low_q = db.query(
        Product.name, ProductVariant.sku, ProductVariant.variant_name, StockOnHand.qty_on_hand
    ).join(ProductVariant, Product.id == ProductVariant.product_id)\
     .join(StockOnHand, ProductVariant.id == StockOnHand.variant_id)\
     .filter(
        Product.organization_id == org_id,
        StockOnHand.qty_on_hand <= umbral_poca_existencia(db, org_id),
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