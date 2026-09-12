"""Reportes de dinero de plataforma (spec 2026-09-09 §5.2).

Cuatro pivotes que `reports.py` no cubría: cortes de caja, devoluciones,
cancelaciones y el quincenal por método de pago. Viven aparte para no seguir
engordando `reports.py` (1,300 LOC); reusan sus helpers de fechas, filtros,
formato y CSV.

Cross-org por diseño y de solo lectura: el guard `require_platform_admin` lo
aplica el paquete (SUPERADMIN o SUPPORT).

Fuentes por pivote — cada uno mira donde vive la verdad, no donde es cómodo:
- Cortes: `CashSession` cerradas, `difference` PERSISTIDO (el que firmó la
  cajera), ubicadas por `closed_at`.
- Devoluciones: `SaleReturn` por `created_at`; la hora de aprobación sale del
  `cash_audit_log`.
- Cancelaciones: `cash_audit_log` (`SALE_CANCELLED`), append-only — nunca
  `updated_at`, que cualquier UPDATE masivo puede pisar.
- Quincenal: `SalesDocument` con `CASH_INCLUDED_STATUSES` y el efectivo neto
  de `change_given`.
"""
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.cash import CashSession, CashSessionStatus
from app.models.cash_audit import CashAuditEvent, CashAuditLog
from app.models.organization import Branch, Organization
from app.models.returns import SaleReturn
from app.models.sales import Payment, SalesDocument
from app.models.users import User
from app.services.cash_reconciliation import CASH_INCLUDED_STATUSES
from app.routers.platform.reports import (
    MX_TZ,
    _cached,
    _csv_stream,
    _dec_str,
    _parse_dates,
    _today_stamp,
    _validate_branch_in_org,
    _validate_filters,
)

router = APIRouter()

_ZERO = Decimal("0")


def _paginate(items: list[dict], offset: int, limit: int) -> dict:
    return {"items": items[offset : offset + limit], "total": len(items), "offset": offset, "limit": limit}


def _cashier_name(user: Optional[User]) -> str:
    if user is None:
        return "—"
    return user.full_name or user.username


# ================================================================== #
# 1. CORTES DE CAJA                                                  #
# ================================================================== #

def _cash_cut_rows(db: Session, s: datetime, e: datetime, org_id: Optional[int],
                   branch_id: Optional[int]) -> list[dict]:
    """Una fila por sucursal con cortes en la ventana.

    El corte pertenece al periodo por su `closed_at` (cuando se contó el
    dinero), no por su apertura: un turno que abre el 31 y cierra el 1 es del
    día 1. Faltante y sobrante se suman por separado — compensarlos escondería
    justamente lo que el reporte busca.
    """
    diff = CashSession.difference
    closed = (
        db.query(
            CashSession.branch_id.label("branch_id"),
            func.count(CashSession.id).label("sessions_closed"),
            func.sum(case((diff != 0, 1), else_=0)).label("with_difference"),
            func.sum(case((diff < 0, -diff), else_=0)).label("shortage_total"),
            func.sum(case((diff > 0, diff), else_=0)).label("overage_total"),
            func.sum(func.abs(diff)).label("abs_total"),
        )
        .filter(
            CashSession.status == CashSessionStatus.CLOSED,
            CashSession.closed_at >= s,
            CashSession.closed_at <= e,
        )
        .group_by(CashSession.branch_id)
    )
    # "as of now", no ventaneado: un turno abierto hace 45 días y nunca
    # cerrado es precisamente lo que este contador existe para encontrar —
    # filtrar por `opened_at` dentro de [s, e] lo hacía invisible en
    # cualquier reporte que no cubriera esa apertura.
    opened = (
        db.query(CashSession.branch_id, func.count(CashSession.id))
        .filter(CashSession.status == CashSessionStatus.OPEN)
        .group_by(CashSession.branch_id)
    )
    if org_id is not None:
        closed = closed.filter(CashSession.organization_id == org_id)
        opened = opened.filter(CashSession.organization_id == org_id)
    if branch_id is not None:
        closed = closed.filter(CashSession.branch_id == branch_id)
        opened = opened.filter(CashSession.branch_id == branch_id)

    closed_map = {r.branch_id: r for r in closed.all()}
    open_map = {r[0]: int(r[1]) for r in opened.all()}

    branch_ids = set(closed_map) | set(open_map)
    if not branch_ids:
        return []
    names = {
        r[0]: (r[1], r[2], r[3])
        for r in db.query(Branch.id, Branch.name, Branch.organization_id, Organization.name)
        .join(Organization, Branch.organization_id == Organization.id)
        .filter(Branch.id.in_(branch_ids))
        .all()
    }

    rows: list[dict] = []
    for bid in branch_ids:
        name, oid, org_name = names.get(bid, (f"Sucursal {bid}", None, "—"))
        c = closed_map.get(bid)
        n_closed = int(c.sessions_closed) if c else 0
        abs_total = Decimal(str(c.abs_total or 0)) if c else _ZERO
        rows.append({
            "branch_id": bid,
            "name": name,
            "org_id": oid,
            "org_name": org_name,
            "sessions_closed": n_closed,
            "sessions_with_difference": int(c.with_difference or 0) if c else 0,
            "shortage_total": _dec_str(c.shortage_total if c else 0),
            "overage_total": _dec_str(c.overage_total if c else 0),
            "avg_abs_difference": _dec_str(abs_total / n_closed if n_closed else 0),
            "sessions_open_unclosed": open_map.get(bid, 0),
        })
    # Mayor faltante primero: es lo que un SUPERADMIN abriendo este reporte
    # quiere ver arriba, no el orden alfabético.
    rows.sort(key=lambda r: (-Decimal(r["shortage_total"]), r["name"]))
    return rows


@router.get("/reports/cash-cuts")
def report_cash_cuts(
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, limit)
    key = f"cash-cuts:{s.isoformat()}:{e.isoformat()}:{org_id}:{branch_id}:{limit}:{offset}"
    return _cached(key, lambda: _paginate(_cash_cut_rows(db, s, e, org_id, branch_id), offset, limit))


@router.get("/reports/cash-cuts/{branch_id}/detail")
def report_cash_cuts_detail(
    branch_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, limit)
    # Con `org_id` en el filtro, una sucursal de OTRA organización es un 404,
    # no un detalle servido de más: el drawer manda los mismos filtros que la
    # tabla y debe respetar el mismo recorte.
    branch = _validate_branch_in_org(db, branch_id, org_id)

    sessions = (
        db.query(CashSession, User)
        .outerjoin(User, CashSession.user_id == User.id)
        .filter(
            CashSession.branch_id == branch_id,
            CashSession.status == CashSessionStatus.CLOSED,
            CashSession.closed_at >= s,
            CashSession.closed_at <= e,
        )
        .order_by(CashSession.closed_at.desc())
        .all()
    )

    by_cashier: dict[int, dict] = {}
    items: list[dict] = []
    for cs, user in sessions:
        diff = Decimal(str(cs.difference or 0))
        agg = by_cashier.setdefault(cs.user_id, {
            "user_id": cs.user_id, "full_name": _cashier_name(user),
            "sessions": 0, "_shortage": _ZERO, "_overage": _ZERO,
        })
        agg["sessions"] += 1
        if diff < 0:
            agg["_shortage"] += -diff
        elif diff > 0:
            agg["_overage"] += diff
        # `expected` NO es `total_cash_sales`: ese campo persiste solo el
        # efectivo neto de la venta (`app/routers/cash.py` lo llena con
        # `breakdown.net_cash`), sin fondo de apertura ni movimientos
        # manuales. El expected real es
        # `opening + net_cash + inflows - outflows - refund_cash_outflows`
        # (`app/services/cash_reconciliation.py:compute_expected_cash`), y
        # `_apply_close_to_session` ya lo persiste indirecto como
        # `difference = closing_balance - expected` — despejamos en vez de
        # replicar la fórmula.
        reported = Decimal(str(cs.closing_balance or 0))
        items.append({
            "session_id": cs.id,
            "cashier": _cashier_name(user),
            "opened_at": cs.opened_at.isoformat() if cs.opened_at else None,
            "closed_at": cs.closed_at.isoformat() if cs.closed_at else None,
            "expected": _dec_str(reported - diff),
            "reported": _dec_str(reported),
            "difference": _dec_str(diff),
        })

    cashiers = []
    for agg in by_cashier.values():
        cashiers.append({
            "user_id": agg["user_id"], "full_name": agg["full_name"], "sessions": agg["sessions"],
            "shortage_total": _dec_str(agg["_shortage"]), "overage_total": _dec_str(agg["_overage"]),
        })
    cashiers.sort(key=lambda c: -Decimal(c["shortage_total"]))

    page = _paginate(items, offset, limit)
    return {
        "branch_id": branch.id,
        "branch_name": branch.name,
        "by_cashier": cashiers,
        "sessions": page["items"],
        "total": page["total"],
        "offset": page["offset"],
        "limit": page["limit"],
    }


_CASH_CUT_CSV_HEADERS = [
    "branch_id", "name", "org_name", "sessions_closed", "sessions_with_difference",
    "shortage_total", "overage_total", "avg_abs_difference", "sessions_open_unclosed",
]


@router.get("/reports/cash-cuts.csv")
def export_cash_cuts_csv(
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, 500)
    rows = _cash_cut_rows(db, s, e, org_id, branch_id)

    def _iter():
        for r in rows:
            yield [r[h] for h in _CASH_CUT_CSV_HEADERS]

    filename = f"report_cash_cuts_{_today_stamp()}.csv"
    return StreamingResponse(
        _csv_stream(_iter(), _CASH_CUT_CSV_HEADERS),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _folio(sale: Optional[SalesDocument]) -> str:
    if sale is None or not sale.folio:
        return "—"
    serie = (sale.series or "").strip()
    return f"{serie}-{sale.folio}" if serie else str(sale.folio)


def _branch_labels(db: Session, branch_ids: set[int]) -> dict[int, tuple[str, Optional[int], str]]:
    if not branch_ids:
        return {}
    return {
        r[0]: (r[1], r[2], r[3])
        for r in db.query(Branch.id, Branch.name, Branch.organization_id, Organization.name)
        .join(Organization, Branch.organization_id == Organization.id)
        .filter(Branch.id.in_(branch_ids))
        .all()
    }


# ================================================================== #
# 2. DEVOLUCIONES                                                    #
# ================================================================== #

_METHOD_KEYS = ("cash", "card", "transfer", "other")


def _approval_ts_by_return(db: Session, org_id: Optional[int] = None,
                           branch_id: Optional[int] = None) -> dict[str, datetime]:
    """`return_id` → hora del evento REFUND_APPROVED (append-only).

    `SaleReturn.updated_at` NO sirve: un UPDATE masivo (borrar un usuario
    platform limpia `supervisor_id`) lo pisa con la hora del borrado.

    Sin filtro de ventana a propósito: una devolución creada dentro de
    [s, e] puede aprobarse después de `e` (o incluso después de que corra
    este reporte con una `e` de "hoy"), y seguimos necesitando su hora de
    aprobación para `avg_hours_to_approve`. Filtrar por `s`/`e` aquí
    perdería esas aprobaciones tardías sin ninguna ganancia — ya se filtra
    por devolución al construir `returns`/`rows` en el caller.
    """
    q = (
        db.query(CashAuditLog.related_id, func.min(CashAuditLog.ts))
        .filter(
            CashAuditLog.event_type == CashAuditEvent.REFUND_APPROVED,
            CashAuditLog.related_table == "sale_returns",
            CashAuditLog.related_id.isnot(None),
        )
    )
    # Los mismos filtros de tenencia que el caller aplicó a las devoluciones:
    # sin ventana, pero sin barrer el audit log de las demás organizaciones.
    if org_id is not None:
        q = q.filter(CashAuditLog.organization_id == org_id)
    if branch_id is not None:
        q = q.filter(CashAuditLog.branch_id == branch_id)
    rows = q.group_by(CashAuditLog.related_id).all()
    out: dict[str, datetime] = {}
    for rid, ts in rows:
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        out[str(rid)] = ts
    return out


def _returns_rows(db: Session, s: datetime, e: datetime, org_id: Optional[int],
                  branch_id: Optional[int]) -> list[dict]:
    q = db.query(SaleReturn).filter(SaleReturn.created_at >= s, SaleReturn.created_at <= e)
    if org_id is not None:
        q = q.filter(SaleReturn.organization_id == org_id)
    if branch_id is not None:
        q = q.filter(SaleReturn.branch_id == branch_id)
    returns = q.all()
    if not returns:
        return []

    approvals = _approval_ts_by_return(db, org_id, branch_id)
    labels = _branch_labels(db, {r.branch_id for r in returns})

    acc: dict[int, dict] = {}
    reasons: dict[int, Counter] = {}
    hours: dict[int, list[float]] = {}
    for r in returns:
        bid = r.branch_id
        name, oid, org_name = labels.get(bid, (f"Sucursal {bid}", None, "—"))
        row = acc.setdefault(bid, {
            "branch_id": bid, "name": name, "org_id": oid, "org_name": org_name,
            "pending_count": 0, "_pending": _ZERO,
            "approved_count": 0, "_approved": _ZERO,
            "rejected_count": 0,
            "_by_method": {k: _ZERO for k in _METHOD_KEYS},
        })
        amount = Decimal(str(r.total_refunded or 0))
        status = (r.status or "").upper()
        if status == "PENDING":
            row["pending_count"] += 1
            row["_pending"] += amount
        elif status == "APPROVED":
            row["approved_count"] += 1
            row["_approved"] += amount
            method = (r.refund_method.value if hasattr(r.refund_method, "value") else str(r.refund_method or "CASH")).lower()
            row["_by_method"][method if method in _METHOD_KEYS else "other"] += amount
            approved_at = approvals.get(str(r.id))
            created = r.created_at
            if approved_at is not None and created is not None:
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                hours.setdefault(bid, []).append((approved_at - created).total_seconds() / 3600)
        elif status == "REJECTED":
            row["rejected_count"] += 1
        if r.reason:
            reasons.setdefault(bid, Counter())[r.reason] += 1

    rows: list[dict] = []
    for bid, row in acc.items():
        hs = hours.get(bid) or []
        rows.append({
            "branch_id": row["branch_id"], "name": row["name"],
            "org_id": row["org_id"], "org_name": row["org_name"],
            "pending_count": row["pending_count"], "pending_amount": _dec_str(row["_pending"]),
            "approved_count": row["approved_count"], "approved_amount": _dec_str(row["_approved"]),
            "rejected_count": row["rejected_count"],
            "by_method": {k: _dec_str(row["_by_method"][k]) for k in _METHOD_KEYS},
            "avg_hours_to_approve": _dec_str(sum(hs) / len(hs)) if hs else None,
            "top_reasons": [reason for reason, _ in reasons.get(bid, Counter()).most_common(3)],
        })
    rows.sort(key=lambda r: (-Decimal(r["pending_amount"]), r["name"]))
    return rows


@router.get("/reports/returns")
def report_returns(
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, limit)
    key = f"returns:{s.isoformat()}:{e.isoformat()}:{org_id}:{branch_id}:{limit}:{offset}"
    return _cached(key, lambda: _paginate(_returns_rows(db, s, e, org_id, branch_id), offset, limit))


@router.get("/reports/returns/{branch_id}/detail")
def report_returns_detail(
    branch_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, limit)
    # Con `org_id` en el filtro, una sucursal de OTRA organización es un 404,
    # no un detalle servido de más: el drawer manda los mismos filtros que la
    # tabla y debe respetar el mismo recorte.
    branch = _validate_branch_in_org(db, branch_id, org_id)

    rows = (
        db.query(SaleReturn, SalesDocument, User)
        .outerjoin(SalesDocument, SaleReturn.sale_id == SalesDocument.id)
        .outerjoin(User, SaleReturn.user_id == User.id)
        .filter(
            SaleReturn.branch_id == branch_id,
            SaleReturn.created_at >= s,
            SaleReturn.created_at <= e,
        )
        .order_by(SaleReturn.created_at.desc())
        .all()
    )
    approvals = _approval_ts_by_return(db, org_id, branch_id)
    items = []
    for r, sale, user in rows:
        approved_at = approvals.get(str(r.id))
        method = (r.refund_method.value if hasattr(r.refund_method, "value") else str(r.refund_method or "CASH"))
        items.append({
            "return_id": r.id,
            "folio": _folio(sale),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "approved_at": approved_at.isoformat() if approved_at else None,
            "status": (r.status or "").upper(),
            "method": method,
            "amount": _dec_str(r.total_refunded),
            "reason": r.reason or "",
            "cashier": _cashier_name(user),
        })
    page = _paginate(items, offset, limit)
    return {"branch_id": branch.id, "branch_name": branch.name, **page}


_RETURNS_CSV_HEADERS = [
    "branch_id", "name", "org_name", "pending_count", "pending_amount",
    "approved_count", "approved_amount", "rejected_count",
    "cash", "card", "transfer", "other", "avg_hours_to_approve",
]


@router.get("/reports/returns.csv")
def export_returns_csv(
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, 500)
    rows = _returns_rows(db, s, e, org_id, branch_id)

    def _iter():
        for r in rows:
            yield [
                r["branch_id"], r["name"], r["org_name"],
                r["pending_count"], r["pending_amount"],
                r["approved_count"], r["approved_amount"], r["rejected_count"],
                r["by_method"]["cash"], r["by_method"]["card"],
                r["by_method"]["transfer"], r["by_method"]["other"],
                r["avg_hours_to_approve"] or "",
            ]

    filename = f"report_returns_{_today_stamp()}.csv"
    return StreamingResponse(
        _csv_stream(_iter(), _RETURNS_CSV_HEADERS),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ================================================================== #
# 3. CANCELACIONES                                                   #
# ================================================================== #

def _cancellation_events(db: Session, s: datetime, e: datetime, org_id: Optional[int],
                         branch_id: Optional[int]):
    q = (
        db.query(CashAuditLog, User)
        .outerjoin(User, CashAuditLog.user_id == User.id)
        .filter(
            CashAuditLog.event_type == CashAuditEvent.SALE_CANCELLED,
            CashAuditLog.ts >= s,
            CashAuditLog.ts <= e,
            CashAuditLog.branch_id.isnot(None),
        )
    )
    if org_id is not None:
        q = q.filter(CashAuditLog.organization_id == org_id)
    if branch_id is not None:
        q = q.filter(CashAuditLog.branch_id == branch_id)
    return q.order_by(CashAuditLog.ts.desc()).all()


def _payload_field(log: CashAuditLog, field: str) -> Optional[str]:
    payload = log.payload_json or {}
    value = payload.get(field) if isinstance(payload, dict) else None
    return str(value) if value is not None else None


def _cancellations_rows(db: Session, s: datetime, e: datetime, org_id: Optional[int],
                        branch_id: Optional[int]) -> list[dict]:
    events = _cancellation_events(db, s, e, org_id, branch_id)
    if not events:
        return []
    labels = _branch_labels(db, {log.branch_id for log, _ in events})

    acc: dict[int, dict] = {}
    by_user: dict[int, dict] = {}
    reasons: dict[int, Counter] = {}
    for log, user in events:
        bid = log.branch_id
        name, oid, org_name = labels.get(bid, (f"Sucursal {bid}", None, "—"))
        row = acc.setdefault(bid, {
            "branch_id": bid, "name": name, "org_id": oid, "org_name": org_name,
            "count": 0, "_amount": _ZERO,
        })
        amount = Decimal(str(log.amount or 0))
        row["count"] += 1
        row["_amount"] += amount
        users = by_user.setdefault(bid, {})
        u = users.setdefault(log.user_id, {
            "user_id": log.user_id, "full_name": _cashier_name(user), "count": 0, "_amount": _ZERO,
        })
        u["count"] += 1
        u["_amount"] += amount
        reason = _payload_field(log, "reason")
        if reason:
            reasons.setdefault(bid, Counter())[reason] += 1

    rows: list[dict] = []
    for bid, row in acc.items():
        users = sorted(by_user.get(bid, {}).values(), key=lambda u: -u["_amount"])
        rows.append({
            "branch_id": row["branch_id"], "name": row["name"],
            "org_id": row["org_id"], "org_name": row["org_name"],
            "count": row["count"], "amount": _dec_str(row["_amount"]),
            "by_user": [
                {"user_id": u["user_id"], "full_name": u["full_name"],
                 "count": u["count"], "amount": _dec_str(u["_amount"])}
                for u in users
            ],
            "top_reasons": [reason for reason, _ in reasons.get(bid, Counter()).most_common(3)],
        })
    rows.sort(key=lambda r: (-Decimal(r["amount"]), r["name"]))
    return rows


@router.get("/reports/cancellations")
def report_cancellations(
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, limit)
    key = f"cancellations:{s.isoformat()}:{e.isoformat()}:{org_id}:{branch_id}:{limit}:{offset}"
    return _cached(key, lambda: _paginate(_cancellations_rows(db, s, e, org_id, branch_id), offset, limit))


@router.get("/reports/cancellations/{branch_id}/detail")
def report_cancellations_detail(
    branch_id: int,
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, limit)
    # Con `org_id` en el filtro, una sucursal de OTRA organización es un 404,
    # no un detalle servido de más: el drawer manda los mismos filtros que la
    # tabla y debe respetar el mismo recorte.
    branch = _validate_branch_in_org(db, branch_id, org_id)

    events = _cancellation_events(db, s, e, None, branch_id)
    sale_ids = {str(log.related_id) for log, _ in events if log.related_id}
    sales = {
        sale.id: sale
        for sale in db.query(SalesDocument).filter(SalesDocument.id.in_(sale_ids)).all()
    } if sale_ids else {}

    items = []
    for log, user in events:
        sale = sales.get(str(log.related_id)) if log.related_id else None
        items.append({
            "event_id": log.id,
            "ts": log.ts.isoformat() if log.ts else None,
            "sale_id": str(log.related_id) if log.related_id else None,
            "folio": _folio(sale),
            "amount": _dec_str(log.amount),
            "user": _cashier_name(user),
            "reason": _payload_field(log, "reason") or "",
            "prev_status": _payload_field(log, "prev_status") or "",
        })
    page = _paginate(items, offset, limit)
    return {"branch_id": branch.id, "branch_name": branch.name, **page}


_CANCELLATIONS_CSV_HEADERS = ["branch_id", "name", "org_name", "count", "amount"]


@router.get("/reports/cancellations.csv")
def export_cancellations_csv(
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, 500)
    rows = _cancellations_rows(db, s, e, org_id, branch_id)

    def _iter():
        for r in rows:
            yield [r[h] for h in _CANCELLATIONS_CSV_HEADERS]

    filename = f"report_cancellations_{_today_stamp()}.csv"
    return StreamingResponse(
        _csv_stream(_iter(), _CANCELLATIONS_CSV_HEADERS),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ================================================================== #
# 4. QUINCENAL POR MÉTODO DE PAGO                                    #
# ================================================================== #

_MESES_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _biweekly_periods(s: datetime, e: datetime) -> list[tuple[str, str, datetime, datetime]]:
    """Quincenas que tocan [s, e]: (clave, etiqueta, inicio UTC, fin UTC).

    Q1 = días 1–15, Q2 = 16 a fin de mes, en día de México. La quincena entra
    completa aunque el rango la corte: el negocio compara quincenas enteras.
    """
    start_mx = s.astimezone(MX_TZ).date()
    end_mx = e.astimezone(MX_TZ).date()
    out: list[tuple[str, str, datetime, datetime]] = []
    cursor = date(start_mx.year, start_mx.month, 1)
    while cursor <= end_mx:
        year, month = cursor.year, cursor.month
        last_day = (date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)).day
        for q, (d1, d2) in enumerate(((1, 15), (16, last_day)), start=1):
            q_start = date(year, month, d1)
            q_end = date(year, month, d2)
            if q_end < start_mx or q_start > end_mx:
                continue
            begin_utc = datetime(year, month, d1, tzinfo=MX_TZ).astimezone(timezone.utc)
            end_utc = (datetime(year, month, d2, tzinfo=MX_TZ) + timedelta(days=1)).astimezone(timezone.utc)
            label = f"{d1}–{d2} {_MESES_ES[month - 1]} {year}"
            out.append((f"{year}-{month:02d}-Q{q}", label, begin_utc, end_utc))
        cursor = date(year + (month == 12), (month % 12) + 1, 1)
    return out


def _biweekly_rows(db: Session, s: datetime, e: datetime, org_id: Optional[int],
                   branch_id: Optional[int], unit: str) -> list[dict]:
    periods = _biweekly_periods(s, e)
    if not periods:
        return []

    label_q = (
        db.query(Branch.id, Branch.name, Branch.organization_id, Organization.name)
        .join(Organization, Branch.organization_id == Organization.id)
    )
    if org_id is not None:
        label_q = label_q.filter(Branch.organization_id == org_id)
    if branch_id is not None:
        label_q = label_q.filter(Branch.id == branch_id)
    labels = {r[0]: (r[1], r[2], r[3]) for r in label_q.all()}

    rows: list[dict] = []
    for key, label, begin, end in periods:
        pay_q = (
            db.query(
                SalesDocument.branch_id, Payment.method,
                func.coalesce(func.sum(Payment.amount), 0),
            )
            .join(SalesDocument, Payment.sales_document_id == SalesDocument.id)
            .filter(
                SalesDocument.status.in_(CASH_INCLUDED_STATUSES),
                SalesDocument.created_at >= begin,
                SalesDocument.created_at < end,
            )
            .group_by(SalesDocument.branch_id, Payment.method)
        )
        doc_q = (
            db.query(
                SalesDocument.branch_id,
                func.count(SalesDocument.id),
                func.coalesce(func.sum(SalesDocument.change_given), 0),
            )
            .filter(
                SalesDocument.status.in_(CASH_INCLUDED_STATUSES),
                SalesDocument.created_at >= begin,
                SalesDocument.created_at < end,
            )
            .group_by(SalesDocument.branch_id)
        )
        if org_id is not None:
            pay_q = pay_q.filter(SalesDocument.organization_id == org_id)
            doc_q = doc_q.filter(SalesDocument.organization_id == org_id)
        if branch_id is not None:
            pay_q = pay_q.filter(SalesDocument.branch_id == branch_id)
            doc_q = doc_q.filter(SalesDocument.branch_id == branch_id)

        per_branch: dict[int, dict] = {}
        for bid, method, total in pay_q.all():
            bucket = per_branch.setdefault(bid, {k: _ZERO for k in _METHOD_KEYS} | {"tickets": 0, "change": _ZERO})
            m = (method.value if hasattr(method, "value") else str(method)).lower()
            bucket[m if m in _METHOD_KEYS else "other"] += Decimal(str(total or 0))
        for bid, tickets, change in doc_q.all():
            bucket = per_branch.setdefault(bid, {k: _ZERO for k in _METHOD_KEYS} | {"tickets": 0, "change": _ZERO})
            bucket["tickets"] = int(tickets or 0)
            bucket["change"] = Decimal(str(change or 0))

        grouped: dict[int | str, dict] = {}
        for bid, bucket in per_branch.items():
            name, oid, org_name = labels.get(bid, (f"Sucursal {bid}", None, "—"))
            # `organization_id` es nullable (app/models/mixins.py) y `labels`
            # hace inner join con Organization: una sucursal huérfana llega
            # aquí con `oid = None`. Agrupar por None juntaría en UNA fila a
            # huérfanas de orgs distintas — dinero de nadie sumado como si
            # fuera de alguien. Cada huérfana se queda sola, con su nombre.
            if unit == "org":
                unit_id = oid if oid is not None else f"orphan-{bid}"
                unit_name = org_name if oid is not None else f"{name} (sin organización)"
            else:
                unit_id = bid
                unit_name = name
            g = grouped.setdefault(unit_id, {
                "period": key, "period_label": label, "unit_id": unit_id,
                "name": unit_name, "org_name": org_name,
                **{k: _ZERO for k in _METHOD_KEYS}, "tickets": 0, "_change": _ZERO,
            })
            for k in _METHOD_KEYS:
                g[k] += bucket[k]
            g["tickets"] += bucket["tickets"]
            g["_change"] += bucket["change"]

        for g in grouped.values():
            cash_net = max(_ZERO, g["cash"] - g["_change"])
            total = cash_net + g["card"] + g["transfer"] + g["other"]
            rows.append({
                "period": g["period"], "period_label": g["period_label"],
                "unit_id": g["unit_id"], "name": g["name"], "org_name": g["org_name"],
                "cash_net": _dec_str(cash_net),
                "card": _dec_str(g["card"]), "transfer": _dec_str(g["transfer"]),
                "other": _dec_str(g["other"]), "total": _dec_str(total),
                "tickets": g["tickets"],
            })
    rows.sort(key=lambda r: (r["period"], r["name"]))
    return rows


@router.get("/reports/payment-methods-biweekly")
def report_payment_methods_biweekly(
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    unit: str = Query("branch", pattern="^(branch|org)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, limit)
    key = f"biweekly:{s.isoformat()}:{e.isoformat()}:{org_id}:{branch_id}:{unit}:{limit}:{offset}"
    return _cached(key, lambda: _paginate(_biweekly_rows(db, s, e, org_id, branch_id, unit), offset, limit))


_BIWEEKLY_CSV_HEADERS = [
    "period", "period_label", "unit_id", "name", "org_name",
    "cash_net", "card", "transfer", "other", "total", "tickets",
]


@router.get("/reports/payment-methods-biweekly.csv")
def export_biweekly_csv(
    start: Optional[str] = None,
    end: Optional[str] = None,
    org_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    unit: str = Query("branch", pattern="^(branch|org)$"),
    db: Session = Depends(get_db),
):
    s, e = _parse_dates(start, end)
    _validate_filters(s, e, org_id, 500)
    rows = _biweekly_rows(db, s, e, org_id, branch_id, unit)

    def _iter():
        for r in rows:
            yield [r[h] for h in _BIWEEKLY_CSV_HEADERS]

    filename = f"report_biweekly_{_today_stamp()}.csv"
    return StreamingResponse(
        _csv_stream(_iter(), _BIWEEKLY_CSV_HEADERS),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
