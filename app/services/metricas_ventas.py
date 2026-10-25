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

from fastapi import HTTPException
from sqlalchemy import case, desc, func, or_
from sqlalchemy.orm import Session

from app.models import Payment, SaleReturn, SalesDocument, SalesLineItem, User
from app.models.products import ProductVariant
from app.models.returns import SaleReturnItem
from app.models.sales import PaymentMethod
from app.models.users import PlatformRole
from app.services.cash_reconciliation import SALES_REPORT_STATUSES

ZONA = "America/Mexico_City"
MX = ZoneInfo(ZONA)

# Roles de oficina: pueden mirar otra sucursal o la organización entera.
# GERENTE está aquí desde `app/routers/reports.py` de siempre; no se amplía.
HQ_ROLES = ("ADMINISTRADOR", "GERENTE", "DUEÑO")

PRESETS = ("hoy", "ayer", "7d", "30d", "mes")


def hoy_mx() -> date:
    return datetime.now(MX).date()


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


def periodo_de_query(start_date: Optional[date], end_date: Optional[date], hoy: Optional[date] = None) -> Periodo:
    """Periodo a partir de los query params de un endpoint: la fecha que falte
    copia a la otra (una sola fecha = ese día; ninguna = hoy); fin < inicio → 422."""
    hoy = hoy or hoy_mx()
    inicio = start_date or end_date or hoy
    fin = end_date or start_date or hoy
    if fin < inicio:
        raise HTTPException(status_code=422, detail="end_date no puede ser anterior a start_date")
    return Periodo(inicio, fin)


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


def ve_costos(user: User) -> bool:
    """Quién ve costos y utilidad: dueño, administrador y superadmin. El gerente no
    (misma regla que la valuación y el Inicio)."""
    if getattr(user, "platform_role", None) == PlatformRole.SUPERADMIN:
        return True
    return _rol(user) in ("ADMINISTRADOR", "DUEÑO")


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


RESUMEN_VACIO = Resumen(bruta=0.0, devuelto=0.0, neta=0.0, tickets=0, devoluciones=0, ticket_promedio=0.0)


@dataclass(frozen=True)
class DiaVentas:
    fecha: date
    bruta: float
    devuelto: float
    neta: float
    tickets: int


def por_dia(db: Session, ambito: Ambito, periodo: Periodo) -> List[DiaVentas]:
    """Un renglón por día del periodo (con ceros), agrupado por el mismo día de
    México con el que se filtra. Antes el dashboard agrupaba por día UTC y las
    ventas de después de las 18:00 caían al día siguiente."""
    dia_doc = dia_mx(SalesDocument.created_at).label("dia")
    docs = {
        str(r.dia): (r.total, r.n)
        for r in db.query(dia_doc, func.coalesce(func.sum(SalesDocument.total_amount), 0).label("total"),
                          func.count(SalesDocument.id).label("n"))
        .filter(*filtros_documentos(ambito, periodo)).group_by("dia").all()
    }
    dia_dev = dia_mx(SaleReturn.created_at).label("dia")
    devs = {
        str(r.dia): r.total
        for r in db.query(dia_dev, func.coalesce(func.sum(SaleReturn.total_refunded), 0).label("total"))
        .filter(*filtros_devoluciones(ambito, periodo)).group_by("dia").all()
    }
    salida = []
    for f in periodo.fechas():
        bruta, n = docs.get(str(f), (0, 0))
        devuelto = devs.get(str(f), 0)
        salida.append(DiaVentas(fecha=f, bruta=_f(bruta), devuelto=_f(devuelto),
                                neta=round(_f(bruta) - _f(devuelto), 2), tickets=int(n or 0)))
    return salida


@dataclass(frozen=True)
class HoraVentas:
    hora: int
    neta: float
    tickets: int


def por_hora(db: Session, ambito: Ambito, periodo: Periodo) -> List[HoraVentas]:
    """Las 24 horas (0..23); quien pinta decide cuántas enseña. Antes se
    tiraba lo vendido fuera de 8 a 21."""
    hora_doc = func.to_char(mx(SalesDocument.created_at), "HH24").label("hora")
    docs = {
        int(r.hora): (r.total, r.n)
        for r in db.query(hora_doc, func.coalesce(func.sum(SalesDocument.total_amount), 0).label("total"),
                          func.count(SalesDocument.id).label("n"))
        .filter(*filtros_documentos(ambito, periodo)).group_by("hora").all()
    }
    hora_dev = func.to_char(mx(SaleReturn.created_at), "HH24").label("hora")
    devs = {
        int(r.hora): r.total
        for r in db.query(hora_dev, func.coalesce(func.sum(SaleReturn.total_refunded), 0).label("total"))
        .filter(*filtros_devoluciones(ambito, periodo)).group_by("hora").all()
    }
    salida = []
    for h in range(24):
        bruta, n = docs.get(h, (0, 0))
        salida.append(HoraVentas(hora=h, neta=round(_f(bruta) - _f(devs.get(h, 0)), 2), tickets=int(n or 0)))
    return salida


@dataclass(frozen=True)
class MetodoVentas:
    total: float
    tickets: int


def _clave_metodo(m) -> str:
    return str(getattr(m, "value", m))


def por_metodo(db: Session, ambito: Ambito, periodo: Periodo) -> Dict[str, MetodoVentas]:
    """Cobros por método: lo entregado menos el cambio (efectivo) y menos lo
    devuelto por ese método. Los pagos se fechan por su venta."""
    pagos = (
        db.query(Payment.method, func.coalesce(func.sum(Payment.amount), 0), func.count(Payment.id))
        .join(SalesDocument, SalesDocument.id == Payment.sales_document_id)
        .filter(*filtros_documentos(ambito, periodo)).group_by(Payment.method).all()
    )
    totales: Dict[str, Decimal] = {}
    tickets: Dict[str, int] = {}
    for metodo, total, n in pagos:
        k = _clave_metodo(metodo)
        totales[k] = Decimal(str(total or 0))
        tickets[k] = int(n or 0)
    cambio = db.query(func.coalesce(func.sum(SalesDocument.change_given), 0)).filter(
        *filtros_documentos(ambito, periodo)).scalar()
    efectivo = _clave_metodo(PaymentMethod.CASH)
    if efectivo in totales:
        totales[efectivo] -= Decimal(str(cambio or 0))
    devs = (
        db.query(SaleReturn.refund_method, func.coalesce(func.sum(SaleReturn.total_refunded), 0))
        .filter(*filtros_devoluciones(ambito, periodo)).group_by(SaleReturn.refund_method).all()
    )
    for metodo, total in devs:
        k = _clave_metodo(metodo)
        totales[k] = totales.get(k, Decimal(0)) - Decimal(str(total or 0))
        tickets.setdefault(k, 0)
    return {k: MetodoVentas(total=_f(v), tickets=tickets.get(k, 0)) for k, v in totales.items()}


def por_sucursal(db: Session, org_id: int, periodo: Periodo) -> Dict[int, Resumen]:
    """Resumen neto por sucursal; las sucursales sin movimiento no aparecen
    (el que pinta usa `RESUMEN_VACIO`)."""
    ambito = Ambito(org_id, None, True)
    docs = {
        r.branch_id: (r.total, r.n)
        for r in db.query(SalesDocument.branch_id, func.coalesce(func.sum(SalesDocument.total_amount), 0).label("total"),
                          func.count(SalesDocument.id).label("n"))
        .filter(*filtros_documentos(ambito, periodo)).group_by(SalesDocument.branch_id).all()
    }
    devs = {
        r.branch_id: (r.total, r.n)
        for r in db.query(SaleReturn.branch_id, func.coalesce(func.sum(SaleReturn.total_refunded), 0).label("total"),
                          func.count(SaleReturn.id).label("n"))
        .filter(*filtros_devoluciones(ambito, periodo)).group_by(SaleReturn.branch_id).all()
    }
    salida = {}
    for b in set(docs) | set(devs):
        bruta, n = docs.get(b, (0, 0))
        devuelto, nd = devs.get(b, (0, 0))
        salida[b] = _armar_resumen(bruta, devuelto, n, nd)
    return salida


@dataclass(frozen=True)
class ProductoTop:
    nombre: str
    cantidad: float
    total: float


def top_productos(db: Session, ambito: Ambito, periodo: Periodo, limite: int = 5) -> List[ProductoTop]:
    filas = (
        db.query(SalesLineItem.description, func.sum(SalesLineItem.quantity).label("qty"),
                 func.sum(SalesLineItem.total_line).label("importe"))
        .join(SalesDocument, SalesDocument.id == SalesLineItem.document_id)
        .filter(*filtros_documentos(ambito, periodo))
        .group_by(SalesLineItem.description)
        .order_by(desc("qty"), SalesLineItem.description)
        .limit(limite).all()
    )
    return [ProductoTop(nombre=f.description or "", cantidad=_f(f.qty), total=_f(f.importe)) for f in filas]


def utilidad_bruta(db: Session, ambito: Ambito, periodo: Periodo) -> tuple:
    """(utilidad SOLO sobre renglones con costo; venta del periodo en renglones
    sin costo). Con `coalesce(costo, 0)` una pieza sin costo parecía 100 % de
    utilidad. Las devoluciones aprobadas del periodo se descuentan por el costo
    de su variante, en tres ramas:
    - con costo y con reingreso: utilidad -= reembolso - costo x cantidad
      (la pieza volvió al stock, solo se pierde el margen);
    - con costo y SIN reingreso (False o NULL): utilidad -= reembolso
      (ingreso fuera y costo hundido: la pieza se perdió);
    - variante sin costo (NULL o <= 0), con o sin reingreso: venta_sin_costo -=
      reembolso (su venta vivía en venta_sin_costo y no toca la utilidad)."""
    con_costo = SalesLineItem.unit_cost > 0
    fila = (
        db.query(
            func.coalesce(func.sum(case((con_costo, SalesLineItem.total_line - SalesLineItem.unit_cost * SalesLineItem.quantity), else_=0)), 0),
            func.coalesce(func.sum(case((con_costo, 0), else_=SalesLineItem.total_line)), 0),
        )
        .join(SalesDocument, SalesDocument.id == SalesLineItem.document_id)
        .filter(*filtros_documentos(ambito, periodo)).one()
    )
    variante_con_costo = ProductVariant.cost > 0
    con_reingreso = SaleReturnItem.is_inventory_reentry.is_(True)
    sin_reingreso = or_(SaleReturnItem.is_inventory_reentry.is_(None), SaleReturnItem.is_inventory_reentry.is_(False))
    margen_reingresado = SaleReturnItem.refund_amount - ProductVariant.cost * SaleReturnItem.quantity
    devoluciones = (
        db.query(
            func.coalesce(func.sum(case(
                (variante_con_costo & con_reingreso, margen_reingresado),
                (variante_con_costo & sin_reingreso, SaleReturnItem.refund_amount),
                else_=0)), 0),
            func.coalesce(func.sum(case((variante_con_costo, 0), else_=SaleReturnItem.refund_amount)), 0),
        )
        .select_from(SaleReturnItem)
        .join(SaleReturn, SaleReturn.id == SaleReturnItem.return_id)
        .join(ProductVariant, ProductVariant.id == SaleReturnItem.variant_id)
        .filter(*filtros_devoluciones(ambito, periodo))
        .one()
    )
    return round(_f(fila[0]) - _f(devoluciones[0]), 2), round(_f(fila[1]) - _f(devoluciones[1]), 2)
