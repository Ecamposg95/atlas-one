"""La única regla de "venta" de los reportes (spec 2026-10-23 §2.1).

Antes cada endpoint escribía su propio criterio: el Inicio sumaba ventas
reembolsadas a importe bruto, el dashboard solo PAID (una devolución parcial
borraba la venta entera), `/sales/stats` sumaba pendientes y borradores, y
nadie restaba devoluciones. "Ventas hoy" daba tres números. Aquí vive el
criterio y los routers solo arman la respuesta.

Venta neta = documentos en `SALES_REPORT_STATUSES` a su `total_amount` original
menos devoluciones APROBADAS en el periodo (por la fecha de la devolución).
Toda fecha se compara en día de México.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session

from app.models import Payment, SaleReturn, SalesDocument, SalesLineItem, User
from app.models.products import ProductVariant
from app.models.returns import SaleReturnItem
from app.models.sales import PaymentMethod
from app.models.users import PlatformRole
from app.services.cash_reconciliation import SALES_REPORT_STATUSES

ZONA = "America/Mexico_City"
_MX = ZoneInfo(ZONA)

# Roles de oficina: pueden mirar otra sucursal o la organización entera.
# GERENTE está aquí desde `app/routers/reports.py` de siempre; no se amplía.
HQ_ROLES = ("ADMINISTRADOR", "GERENTE", "DUEÑO")

PRESETS = ("hoy", "ayer", "7d", "30d", "mes")


def hoy_mx() -> date:
    return datetime.now(_MX).date()


def mx(col):
    """TIMESTAMPTZ (UTC) → hora local de México, en SQL (shim en pruebas)."""
    return func.timezone(ZONA, col)


def dia_mx(col):
    return func.date(mx(col))


@dataclass(frozen=True)
class Periodo:
    inicio: date
    fin: date

    def __post_init__(self):
        if self.fin < self.inicio:
            raise ValueError("El periodo termina antes de empezar")

    @property
    def dias(self) -> int:
        return (self.fin - self.inicio).days + 1

    def anterior(self) -> "Periodo":
        fin = self.inicio - timedelta(days=1)
        return Periodo(fin - timedelta(days=self.dias - 1), fin)

    def fechas(self) -> List[date]:
        return [self.inicio + timedelta(days=i) for i in range(self.dias)]


def periodo_preset(clave: str, hoy: Optional[date] = None) -> Periodo:
    hoy = hoy or hoy_mx()
    if clave == "hoy":
        return Periodo(hoy, hoy)
    if clave == "ayer":
        return Periodo(hoy - timedelta(days=1), hoy - timedelta(days=1))
    if clave == "7d":
        return Periodo(hoy - timedelta(days=6), hoy)
    if clave == "30d":
        return Periodo(hoy - timedelta(days=29), hoy)
    if clave == "mes":
        return Periodo(hoy.replace(day=1), hoy)
    raise ValueError(f"Periodo desconocido: {clave!r} (válidos: {', '.join(PRESETS)})")


@dataclass(frozen=True)
class Ambito:
    organization_id: int
    branch_id: Optional[int]
    toda_la_org: bool


def _rol(user: User) -> str:
    return str(getattr(user.role, "value", user.role))


def resolver_ambito(current_user: User, org_id: int, branch_id: Optional[int]) -> Ambito:
    """Roles de oficina: sin `branch_id` (o 0) = toda la organización; número =
    esa sucursal. Los demás: siempre la suya; sin sucursal asignada,
    `branch_id IS NULL` (cero filas), nunca la organización entera."""
    es_hq = _rol(current_user) in HQ_ROLES or getattr(current_user, "platform_role", None) == PlatformRole.SUPERADMIN
    if es_hq:
        if branch_id:
            return Ambito(org_id, int(branch_id), False)
        return Ambito(org_id, None, True)
    return Ambito(org_id, current_user.branch_id, False)


def filtros_documentos(ambito: Ambito, periodo: Periodo) -> list:
    f = [
        SalesDocument.organization_id == ambito.organization_id,
        SalesDocument.status.in_(SALES_REPORT_STATUSES),
        dia_mx(SalesDocument.created_at) >= periodo.inicio,
        dia_mx(SalesDocument.created_at) <= periodo.fin,
    ]
    if not ambito.toda_la_org:
        f.append(SalesDocument.branch_id == ambito.branch_id)
    return f


def filtros_devoluciones(ambito: Ambito, periodo: Periodo) -> list:
    f = [
        SaleReturn.organization_id == ambito.organization_id,
        SaleReturn.status == "APPROVED",
        dia_mx(SaleReturn.created_at) >= periodo.inicio,
        dia_mx(SaleReturn.created_at) <= periodo.fin,
    ]
    if not ambito.toda_la_org:
        f.append(SaleReturn.branch_id == ambito.branch_id)
    return f


def _f(x) -> float:
    return round(float(x or 0), 2)


@dataclass(frozen=True)
class Resumen:
    bruta: float
    devuelto: float
    neta: float
    tickets: int
    devoluciones: int
    ticket_promedio: float


def _armar_resumen(bruta, devuelto, tickets, devoluciones) -> Resumen:
    bruta, devuelto, tickets, devoluciones = _f(bruta), _f(devuelto), int(tickets or 0), int(devoluciones or 0)
    neta = round(bruta - devuelto, 2)
    return Resumen(bruta=bruta, devuelto=devuelto, neta=neta, tickets=tickets, devoluciones=devoluciones,
                   ticket_promedio=round(neta / tickets, 2) if tickets else 0.0)


def resumen(db: Session, ambito: Ambito, periodo: Periodo) -> Resumen:
    docs = db.query(
        func.coalesce(func.sum(SalesDocument.total_amount), 0), func.count(SalesDocument.id),
    ).filter(*filtros_documentos(ambito, periodo)).one()
    devs = db.query(
        func.coalesce(func.sum(SaleReturn.total_refunded), 0), func.count(SaleReturn.id),
    ).filter(*filtros_devoluciones(ambito, periodo)).one()
    return _armar_resumen(docs[0], devs[0], docs[1], devs[1])
