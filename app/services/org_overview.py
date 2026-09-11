"""Tablero de plataforma: el día de UNA organización y la tira "Atención hoy".

Adaptación de la spec 2026-09-09 §4 a Atlas ONE. En el repo de origen el
tablero era de "grupo" (todas las organizaciones de un mismo dueño, sumadas).
Aquí el SUPERADMIN atiende a clientes distintos entre sí, así que:

- `compute_org_overview` mira UNA organización a la vez. Cada consulta lleva
  `organization_id`: ningún KPI suma el dinero de dos clientes.
- `compute_attention_today` es la excepción documentada a la regla de
  multi-tenancy (CLAUDE.md §2.5): cruza TODAS las organizaciones porque quien
  atiende los pendientes del día es la misma persona. Aun así no suma dinero:
  devuelve renglones, cada uno con su monto y su organización.

Reglas:
- El día es el del negocio (`app/core/fechas.py`): cada ventana se arma en la
  zona local y se convierte a UTC para filtrar `created_at`/`ts`.
- Ventas = CASH_INCLUDED_STATUSES (la misma regla que caja), `total_amount` ya
  neto de devoluciones. El efectivo del mix va neto de `change_given`.
- Una consulta agregada por métrica, agrupada por `branch_id`. Nunca un bucle
  por sucursal contra la BD. Se parte de Branch (activas y que venden) para
  que una tienda sin ventas aparezca en ceros.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.fechas import ZONA_NEGOCIO
from app.models.cash import CashSession, CashSessionStatus
from app.models.cash_audit import CashAuditEvent, CashAuditLog
from app.models.organization import Branch, Organization
from app.models.returns import SaleReturn
from app.models.sales import DocumentStatus, Payment, SalesDocument
from app.services.cash_reconciliation import CASH_INCLUDED_STATUSES

NO_CUT_HOURS = 14
ATTENTION_LIMIT = 10

_ZERO = Decimal("0")
_MIX_KEYS = ("cash", "card", "transfer", "other")


@dataclass(frozen=True)
class Window:
    """Intervalo [start, end) en UTC aware."""
    start: datetime
    end: datetime


def day_window(day: date) -> Window:
    start = datetime(day.year, day.month, day.day, tzinfo=ZONA_NEGOCIO)
    end = start + timedelta(days=1)
    return Window(start.astimezone(timezone.utc), end.astimezone(timezone.utc))


def day_windows(day: date) -> dict[str, Window]:
    return {
        "today": day_window(day),
        "yesterday": day_window(day - timedelta(days=1)),
        "last_week": day_window(day - timedelta(days=7)),
    }


def _aware(value) -> Optional[datetime]:
    """SQLite devuelve naive (o str en agregados); PostgreSQL aware. Normaliza a UTC."""
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _dec(value) -> Decimal:
    return Decimal(str(value or 0))


def _f(value: Decimal | None) -> float:
    return float(value or 0)


def _pct_delta(current: Decimal, ref: Decimal) -> Optional[float]:
    if ref == 0:
        return None
    return round(float((current - ref) / ref * 100), 1)


# ── Consultas agregadas (una por métrica) ────────────────────────────────

def _scoped(query, org_id: Optional[int], columna):
    """Filtra por organización cuando hay una. `None` = la tira cross-org."""
    return query if org_id is None else query.filter(columna == org_id)


def _sales_by_branch(db: Session, w: Window, org_id: Optional[int]) -> dict[int, tuple[Decimal, int, Decimal]]:
    """branch_id → (venta neta, tickets, cambio entregado)."""
    q = (
        db.query(
            SalesDocument.branch_id,
            func.coalesce(func.sum(SalesDocument.total_amount), 0),
            func.count(SalesDocument.id),
            func.coalesce(func.sum(SalesDocument.change_given), 0),
        )
        .filter(
            SalesDocument.status.in_(CASH_INCLUDED_STATUSES),
            SalesDocument.created_at >= w.start,
            SalesDocument.created_at < w.end,
        )
    )
    rows = _scoped(q, org_id, SalesDocument.organization_id).group_by(SalesDocument.branch_id).all()
    return {r[0]: (_dec(r[1]), int(r[2]), _dec(r[3])) for r in rows}


def _payments_by_branch(db: Session, w: Window, org_id: Optional[int]) -> dict[int, dict[str, Decimal]]:
    """branch_id → {cash, card, transfer, other} BRUTO (el cambio se resta después)."""
    q = (
        db.query(SalesDocument.branch_id, Payment.method, func.coalesce(func.sum(Payment.amount), 0))
        .join(SalesDocument, Payment.sales_document_id == SalesDocument.id)
        .filter(
            SalesDocument.status.in_(CASH_INCLUDED_STATUSES),
            SalesDocument.created_at >= w.start,
            SalesDocument.created_at < w.end,
        )
    )
    rows = (
        _scoped(q, org_id, SalesDocument.organization_id)
        .group_by(SalesDocument.branch_id, Payment.method)
        .all()
    )
    out: dict[int, dict[str, Decimal]] = {}
    for branch_id, method, total in rows:
        key = (method.value if hasattr(method, "value") else str(method)).lower()
        if key not in _MIX_KEYS:
            key = "other"
        bucket = out.setdefault(branch_id, {k: _ZERO for k in _MIX_KEYS})
        bucket[key] += _dec(total)
    return out


def _cancellations_by_branch(db: Session, w: Window, org_id: Optional[int]) -> dict[int, tuple[int, Decimal]]:
    """branch_id → (canceladas, monto) de las ventas creadas hoy que quedaron CANCELLED.

    El repo de origen leía esto del audit log (`SALE_CANCELLED`); aquí ese
    evento no existe ni nadie lo escribe, así que la fuente es la venta misma.
    Se mide por `created_at` (cuándo nació el ticket), no por `updated_at`:
    cualquier UPDATE posterior movería la venta de día.
    """
    q = (
        db.query(
            SalesDocument.branch_id,
            func.count(SalesDocument.id),
            func.coalesce(func.sum(SalesDocument.total_amount), 0),
        )
        .filter(
            SalesDocument.status == DocumentStatus.CANCELLED,
            SalesDocument.created_at >= w.start,
            SalesDocument.created_at < w.end,
        )
    )
    rows = _scoped(q, org_id, SalesDocument.organization_id).group_by(SalesDocument.branch_id).all()
    return {r[0]: (int(r[1]), _dec(r[2])) for r in rows}


def _active_branches(db: Session, org_id: Optional[int]) -> list[tuple[int, str, int, str]]:
    q = (
        db.query(Branch.id, Branch.name, Branch.organization_id, Organization.name)
        .join(Organization, Branch.organization_id == Organization.id)
        .filter(Branch.is_active.is_(True), Branch.can_sell.is_(True))
    )
    return _scoped(q, org_id, Branch.organization_id).order_by(Organization.name, Branch.name).all()


def _open_sessions_by_branch(db: Session, org_id: Optional[int]) -> dict[int, tuple[int, datetime]]:
    """branch_id → (sesiones OPEN, opened_at más antiguo)."""
    q = (
        db.query(CashSession.branch_id, func.count(CashSession.id), func.min(CashSession.opened_at))
        .filter(CashSession.status == CashSessionStatus.OPEN)
    )
    rows = _scoped(q, org_id, CashSession.organization_id).group_by(CashSession.branch_id).all()
    return {r[0]: (int(r[1]), _aware(r[2])) for r in rows}


def _last_closed_by_branch(db: Session, org_id: Optional[int]) -> dict[int, tuple[datetime, Decimal, int]]:
    """branch_id → (closed_at, difference PERSISTIDO, session_id) de la última sesión CLOSED.
    Subconsulta max(closed_at) por sucursal + join: dos pasos SQL, cero bucles."""
    sub = (
        db.query(CashSession.branch_id.label("b"), func.max(CashSession.closed_at).label("c"))
        .filter(CashSession.status == CashSessionStatus.CLOSED)
    )
    latest = _scoped(sub, org_id, CashSession.organization_id).group_by(CashSession.branch_id).subquery()
    rows = (
        db.query(CashSession.branch_id, CashSession.closed_at, CashSession.difference, CashSession.id)
        .join(latest, (CashSession.branch_id == latest.c.b) & (CashSession.closed_at == latest.c.c))
        .all()
    )
    return {r[0]: (_aware(r[1]), _dec(r[2]), r[3]) for r in rows}


def _pending_returns_by_branch(db: Session, org_id: Optional[int]) -> dict[int, tuple[int, Decimal, datetime]]:
    q = (
        db.query(
            SaleReturn.branch_id, func.count(SaleReturn.id),
            func.coalesce(func.sum(SaleReturn.total_refunded), 0), func.min(SaleReturn.created_at),
        )
        .filter(SaleReturn.status == "PENDING")
    )
    rows = _scoped(q, org_id, SaleReturn.organization_id).group_by(SaleReturn.branch_id).all()
    return {r[0]: (int(r[1]), _dec(r[2]), _aware(r[3])) for r in rows}


def _approved_returns_by_branch(db: Session, w: Window, org_id: Optional[int]) -> dict[int, tuple[int, Decimal]]:
    """branch_id → (conteo, monto) de REFUND_APPROVED de hoy.
    Append-only: la hora del evento es la real, no un updated_at que otro UPDATE pueda pisar."""
    q = (
        db.query(
            CashAuditLog.branch_id,
            func.count(CashAuditLog.id),
            func.coalesce(func.sum(CashAuditLog.amount), 0),
        )
        .filter(
            CashAuditLog.event_type == CashAuditEvent.REFUND_APPROVED,
            CashAuditLog.branch_id.isnot(None),
            CashAuditLog.ts >= w.start,
            CashAuditLog.ts < w.end,
        )
    )
    rows = _scoped(q, org_id, CashAuditLog.organization_id).group_by(CashAuditLog.branch_id).all()
    return {r[0]: (int(r[1]), _dec(r[2])) for r in rows}


def _hours(since: Optional[datetime], now: datetime) -> Optional[float]:
    if since is None:
        return None
    return round((now - since).total_seconds() / 3600, 1)


def _days(since: Optional[datetime], now: datetime) -> Optional[int]:
    if since is None:
        return None
    return max(0, (now - since).days)


# ── Filas ───────────────────────────────────────────────────────────────

def _empty_cash() -> dict:
    return {"status": "NONE", "open_sessions": 0, "open_hours": None,
            "last_close_at": None, "last_difference": None, "last_session_id": None}


def _empty_returns() -> dict:
    return {"pending_count": 0, "pending_amount": 0.0, "oldest_pending_days": None,
            "approved_today_count": 0, "approved_today_amount": 0.0}


def _mix_dict(gross: dict[str, Decimal], change: Decimal) -> dict:
    net = dict(gross)
    net["cash"] = max(_ZERO, net["cash"] - change)
    total = sum(net.values(), _ZERO)
    out = {k: _f(net[k]) for k in _MIX_KEYS}
    for k in _MIX_KEYS:
        out[f"{k}_pct"] = round(float(net[k] / total * 100), 1) if total > 0 else None
    return out


def _cash_dict(open_info, closed_info, now: datetime) -> dict:
    d = _empty_cash()
    if open_info:
        count, oldest = open_info
        d.update(status="OPEN", open_sessions=count, open_hours=_hours(oldest, now))
    elif closed_info:
        d["status"] = "CLOSED"
    if closed_info:
        closed_at, diff, session_id = closed_info
        d.update(last_close_at=closed_at.isoformat(), last_difference=_f(diff), last_session_id=session_id)
    return d


def _returns_dict(pending_info, approved_info, now: datetime) -> dict:
    d = _empty_returns()
    if pending_info:
        count, amount, oldest = pending_info
        d.update(pending_count=count, pending_amount=_f(amount), oldest_pending_days=_days(oldest, now))
    if approved_info:
        d.update(approved_today_count=approved_info[0], approved_today_amount=_f(approved_info[1]))
    return d


def _branch_rows(db: Session, day: date, now: datetime, org_id: Optional[int]) -> list[dict]:
    ws = day_windows(day)
    today = _sales_by_branch(db, ws["today"], org_id)
    yesterday = _sales_by_branch(db, ws["yesterday"], org_id)
    last_week = _sales_by_branch(db, ws["last_week"], org_id)
    payments = _payments_by_branch(db, ws["today"], org_id)
    open_sessions = _open_sessions_by_branch(db, org_id)
    last_closed = _last_closed_by_branch(db, org_id)
    pending = _pending_returns_by_branch(db, org_id)
    approved = _approved_returns_by_branch(db, ws["today"], org_id)
    cancelled = _cancellations_by_branch(db, ws["today"], org_id)

    rows: list[dict] = []
    for branch_id, name, branch_org_id, org_name in _active_branches(db, org_id):
        t_sales, t_tickets, t_change = today.get(branch_id, (_ZERO, 0, _ZERO))
        y_sales = yesterday.get(branch_id, (_ZERO, 0, _ZERO))[0]
        w_sales = last_week.get(branch_id, (_ZERO, 0, _ZERO))[0]
        gross = payments.get(branch_id, {k: _ZERO for k in _MIX_KEYS})
        cancel_count, cancel_amount = cancelled.get(branch_id, (0, _ZERO))
        rows.append({
            "id": branch_id,
            "name": name,
            "org_id": branch_org_id,
            "org_name": org_name,
            "sales_today": _f(t_sales),
            "sales_yesterday": _f(y_sales),
            "sales_same_weekday_last_week": _f(w_sales),
            "delta_yesterday_pct": _pct_delta(t_sales, y_sales),
            "delta_last_week_pct": _pct_delta(t_sales, w_sales),
            "tickets_today": t_tickets,
            "avg_ticket": round(float(t_sales / t_tickets), 2) if t_tickets else None,
            "mix": _mix_dict(gross, t_change),
            "_mix_gross": gross,   # interno: para el mix del total
            "_change": t_change,   # interno
            "cash": _cash_dict(open_sessions.get(branch_id), last_closed.get(branch_id), now),
            "returns": _returns_dict(pending.get(branch_id), approved.get(branch_id), now),
            "cancellations_today_count": cancel_count,
            "cancellations_today_amount": _f(cancel_amount),
        })
    return rows


def _strip_internal(rows: list[dict]) -> list[dict]:
    for r in rows:
        r.pop("_mix_gross", None)
        r.pop("_change", None)
    return rows


def _totals(rows: list[dict]) -> dict:
    sales = sum((Decimal(str(r["sales_today"])) for r in rows), _ZERO)
    tickets = sum(r["tickets_today"] for r in rows)
    return {
        "units": len(rows),
        "sales_today": _f(sales),
        "tickets_today": tickets,
        "avg_ticket": round(float(sales / tickets), 2) if tickets else None,
        "open_sessions": sum(r["cash"]["open_sessions"] for r in rows),
        "units_with_open_session": sum(1 for r in rows if r["cash"]["status"] == "OPEN"),
        "returns_pending_count": sum(r["returns"]["pending_count"] for r in rows),
        "returns_pending_amount": round(sum(r["returns"]["pending_amount"] for r in rows), 2),
        "cancellations_today_count": sum(r["cancellations_today_count"] for r in rows),
        "mix": _mix_dict(
            {k: sum((r["_mix_gross"][k] for r in rows), _ZERO) for k in _MIX_KEYS},
            sum((r["_change"] for r in rows), _ZERO),
        ),
    }


def _item(r: dict, value, detail: str) -> dict:
    return {"id": r["id"], "name": r["name"], "org_id": r["org_id"],
            "org_name": r["org_name"], "value": value, "detail": detail}


def _attention(rows: list[dict]) -> dict:
    no_cut = [
        _item(r, r["cash"]["open_hours"], f"{r['cash']['open_sessions']} caja(s) abierta(s)")
        for r in rows if r["cash"]["status"] == "OPEN" and (r["cash"]["open_hours"] or 0) > NO_CUT_HOURS
    ]
    no_cut.sort(key=lambda i: -(i["value"] or 0))
    cut_diff = [
        _item(r, r["cash"]["last_difference"], r["cash"]["last_close_at"] or "")
        for r in rows if r["cash"]["last_difference"] not in (None, 0.0)
    ]
    cut_diff.sort(key=lambda i: -abs(i["value"]))
    oldest = [
        _item(r, r["returns"]["pending_amount"],
              f"{r['returns']['pending_count']} pendiente(s) · la más vieja {r['returns']['oldest_pending_days']} d")
        for r in rows if r["returns"]["pending_count"] > 0
    ]
    oldest.sort(key=lambda i: -i["value"])
    cancelled = [
        _item(r, r["cancellations_today_amount"], f"{r['cancellations_today_count']} cancelada(s)")
        for r in rows if r["cancellations_today_count"] > 0
    ]
    cancelled.sort(key=lambda i: -i["value"])
    return {
        "no_cut": no_cut[:ATTENTION_LIMIT],
        "cut_difference": cut_diff[:ATTENTION_LIMIT],
        "oldest_returns": oldest[:ATTENTION_LIMIT],
        "cancelled_today": cancelled[:ATTENTION_LIMIT],
    }


# ── API del servicio ────────────────────────────────────────────────────

def compute_org_overview(
    db: Session, *, organization_id: int, day: date, now: Optional[datetime] = None
) -> Optional[dict]:
    """El día de UNA organización, por sucursal. `None` si la organización no existe."""
    org = db.query(Organization.id, Organization.name).filter(
        Organization.id == organization_id
    ).first()
    if org is None:
        return None
    now = now or datetime.now(timezone.utc)
    rows = _branch_rows(db, day, now, organization_id)
    totals = _totals(rows)
    _strip_internal(rows)
    return {
        "organization_id": org[0],
        "organization_name": org[1],
        "date": day.isoformat(),
        "generated_at": now.isoformat(),
        "totals": totals,
        "rows": rows,
    }


def compute_attention_today(db: Session, *, day: date, now: Optional[datetime] = None) -> dict:
    """Los pendientes del día de TODAS las organizaciones. Sin sumas de dinero:
    cada renglón trae su monto y la organización a la que pertenece."""
    now = now or datetime.now(timezone.utc)
    rows = _branch_rows(db, day, now, None)
    return {"date": day.isoformat(), "generated_at": now.isoformat(), **_attention(rows)}
