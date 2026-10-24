# Fase 1 · Precisión de ventas — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un solo criterio de "venta" (cobradas menos devoluciones aprobadas, día de México, ámbito explícito) que alimente Inicio, dashboard, resumen diario, ventas por hora, centro de mando, estadísticas de ventas y devoluciones; más dos bugs de paso.

**Architecture:** Servicio puro `app/services/metricas_ventas.py` (dataclasses `Periodo`, `Ambito`, `Resumen` y funciones sobre `Session`) que concentra filtros y agregados. Los routers de reportes se vuelven delgados: resuelven ámbito y periodo, llaman al servicio y arman la respuesta con las mismas claves que hoy más campos nuevos. Solo backend; el frontend no cambia en esta fase.

**Tech Stack:** FastAPI, SQLAlchemy 2 (`func.timezone`/`func.to_char` de Postgres con shims SQLite en `tests/conftest.py`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-23-admin-precision-inicio-fusiones-design.md` (§2 y §2.3).

## Global Constraints

- Venta = `SalesDocument.status in SALES_REPORT_STATUSES` (`PAID`, `REFUNDED_PARTIAL`, `REFUNDED_TOTAL` de `app/services/cash_reconciliation.py`), a `total_amount` original; sin filtro de `doc_type` (los reportes de hoy no lo filtran y las pruebas crean `ORDER`). `PENDING`, `DRAFT`, `CANCELLED` nunca cuentan.
- Devolución = `SaleReturn.status == "APPROVED"` por `SaleReturn.created_at` (día de México), importe `total_refunded`.
- Toda comparación de fecha usa `func.date(func.timezone("America/Mexico_City", col))`; las series agrupan por la misma expresión que filtra.
- Ámbito: roles en `HQ_ROLES = ("ADMINISTRADOR", "GERENTE", "DUEÑO")` o `PlatformRole.SUPERADMIN`: `branch_id` ausente o `0` = toda la organización, número = esa sucursal. Otros roles: siempre `current_user.branch_id` (sin sucursal → cero filas, como hoy).
- Presets: `hoy`, `ayer`, `7d` (hoy y 6 anteriores), `30d` (hoy y 29 anteriores), `mes` (del 1 a hoy). Comparativo = `Periodo.anterior()` (mismo largo, termina el día anterior al inicio).
- `por_hora` devuelve 24 renglones (0..23); ningún endpoint recorta a 8..21.
- Claves de respuesta existentes se conservan; lo nuevo se suma. La caja (`/cash/*`) no se toca.
- Pruebas: `python3 -m pytest -q --ignore=tests/test_cash_complete.py --ignore=tests/test_branch_dashboard.py --ignore=tests/test_cash_close_guided.py` (los dos últimos fallan en esta máquina por un uvicorn ajeno en :8000; en CI corren). Un solo pytest por worktree.
- Comentarios y nombres en español, como el código circundante. Sin `print()`.
- Commits con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf`. Nunca push ni merge a `main`.

## Review Focus

1. Una devolución aprobada **de una venta de otro periodo** resta en el periodo de la devolución, no en el de la venta (Tarea 1, `test_devolucion_resta_en_su_propio_dia`).
2. Venta con pago en efectivo mayor al total: el cambio no es ingreso ni efectivo (Tarea 2, `test_por_metodo_resta_el_cambio_del_efectivo`).
3. Devolución reembolsada por tarjeta de una venta en efectivo: resta a TARJETA, no a efectivo (Tarea 2, `test_por_metodo_resta_la_devolucion_a_su_metodo`).
4. Gerente con `branch_id` de otra sucursal en el query: los reportes de hoy lo honran (está en `HQ_ROLES`); conservar sin ampliar (Tarea 1, `test_resolver_ambito_gerente_puede_pedir_otra_sucursal`).
5. Cajera sin sucursal asignada: cero filas, nunca la organización entera (Tarea 1, `test_resolver_ambito_sin_sucursal_no_ve_la_org`).

---

### Task 1: Servicio `metricas_ventas` — periodo, ámbito y resumen

**Files:**
- Create: `app/services/metricas_ventas.py`
- Test: `tests/test_metricas_ventas.py`

**Interfaces:**
- Consumes: `SALES_REPORT_STATUSES` (`app/services/cash_reconciliation.py`), modelos `SalesDocument`, `SaleReturn`, `User`, `PlatformRole`.
- Produces:
  - `ZONA = "America/Mexico_City"`, `hoy_mx() -> date`, `mx(col)`, `dia_mx(col)`, `HQ_ROLES`.
  - `Periodo(inicio: date, fin: date)` con `.dias -> int`, `.anterior() -> Periodo`, `.fechas() -> list[date]`.
  - `periodo_preset(clave: str, hoy: date | None = None) -> Periodo`.
  - `Ambito(organization_id: int, branch_id: int | None, toda_la_org: bool)`.
  - `resolver_ambito(current_user, org_id: int, branch_id: int | None) -> Ambito`.
  - `filtros_documentos(ambito, periodo) -> list`, `filtros_devoluciones(ambito, periodo) -> list`.
  - `Resumen(bruta, devuelto, neta: float, tickets, devoluciones: int, ticket_promedio: float)`.
  - `resumen(db, ambito, periodo) -> Resumen`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_metricas_ventas.py
"""`app/services/metricas_ventas.py` — la única regla de "venta" de los reportes.

Venta neta = documentos cobrados (SALES_REPORT_STATUSES) a su importe original
menos devoluciones APROBADAS en el periodo, todo en día de México.
"""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from itertools import count
from zoneinfo import ZoneInfo

import pytest

from app.models.returns import SaleReturn
from app.models.sales import DocumentStatus, Payment, PaymentMethod, SalesDocument, SalesLineItem
from app.services import metricas_ventas as mv

_MX = ZoneInfo("America/Mexico_City")
_folios = count(1)


def _instante(dia: date, hora: int = 12) -> datetime:
    """`hora` de México del día `dia`, como instante UTC (así se guarda)."""
    return datetime.combine(dia, time(hora), tzinfo=_MX).astimezone(timezone.utc)


def _venta(db, org, branch, user, variante, total, *, dia=None, hora=12, status=DocumentStatus.PAID,
           metodo=PaymentMethod.CASH, entregado=None, costo="40"):
    dia = dia or mv.hoy_mx()
    doc = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id, folio=next(_folios),
        series="A", subtotal=Decimal(total), tax_amount=Decimal("0"), total_amount=Decimal(total),
        status=status, doc_type="ORDER",
        change_given=(Decimal(entregado) - Decimal(total)) if entregado else None,
    )
    doc.created_at = _instante(dia, hora)
    db.add(doc)
    db.flush()
    db.add(SalesLineItem(organization_id=org.id, document_id=doc.id, variant_id=variante.id,
                         description=f"Producto {doc.folio}", quantity=1, unit_price=Decimal(total),
                         total_line=Decimal(total), unit_cost=Decimal(costo)))
    pago = Payment(organization_id=org.id, sales_document_id=doc.id, method=metodo,
                   amount=Decimal(entregado or total))
    pago.created_at = doc.created_at
    db.add(pago)
    db.commit()
    return doc


def _devolucion(db, org, branch, user, venta, importe, *, dia=None, hora=13, status="APPROVED",
                metodo=PaymentMethod.CASH):
    dia = dia or mv.hoy_mx()
    dev = SaleReturn(organization_id=org.id, sale_id=venta.id, user_id=user.id, branch_id=branch.id,
                     total_refunded=Decimal(importe), refund_method=metodo, reason="Prueba", status=status)
    dev.created_at = _instante(dia, hora)
    db.add(dev)
    db.commit()
    return dev


def _v(products_setup):
    return products_setup["product_a"][1]


# --- Periodo -----------------------------------------------------------------

def test_periodo_anterior_mismo_largo():
    p = mv.Periodo(date(2026, 10, 17), date(2026, 10, 23))
    assert p.dias == 7
    assert p.anterior() == mv.Periodo(date(2026, 10, 10), date(2026, 10, 16))


def test_periodo_preset_7d_y_mes():
    hoy = date(2026, 10, 23)
    assert mv.periodo_preset("hoy", hoy) == mv.Periodo(hoy, hoy)
    assert mv.periodo_preset("ayer", hoy) == mv.Periodo(date(2026, 10, 22), date(2026, 10, 22))
    assert mv.periodo_preset("7d", hoy) == mv.Periodo(date(2026, 10, 17), hoy)
    assert mv.periodo_preset("30d", hoy) == mv.Periodo(date(2026, 9, 24), hoy)
    assert mv.periodo_preset("mes", hoy) == mv.Periodo(date(2026, 10, 1), hoy)
    with pytest.raises(ValueError):
        mv.periodo_preset("trimestre", hoy)


def test_periodo_invertido_revienta():
    with pytest.raises(ValueError):
        mv.Periodo(date(2026, 10, 23), date(2026, 10, 22))


# --- Ámbito ------------------------------------------------------------------

def test_resolver_ambito_admin_sin_parametro_es_toda_la_org(admin_a, org):
    a = mv.resolver_ambito(admin_a, org.id, None)
    assert a.toda_la_org is True and a.branch_id is None
    assert mv.resolver_ambito(admin_a, org.id, 0).toda_la_org is True


def test_resolver_ambito_admin_con_sucursal(admin_a, org, branch_b):
    a = mv.resolver_ambito(admin_a, org.id, branch_b.id)
    assert a == mv.Ambito(org.id, branch_b.id, False)


def test_resolver_ambito_cajera_siempre_la_suya(cajero_a, org, branch_a, branch_b):
    a = mv.resolver_ambito(cajero_a, org.id, branch_b.id)
    assert a == mv.Ambito(org.id, branch_a.id, False)


def test_resolver_ambito_gerente_puede_pedir_otra_sucursal(gerente_a, org, branch_b):
    # GERENTE está en HQ_ROLES de los reportes desde antes; se conserva.
    assert mv.resolver_ambito(gerente_a, org.id, branch_b.id).branch_id == branch_b.id


def test_resolver_ambito_sin_sucursal_no_ve_la_org(vendedor_sin_sucursal, org):
    a = mv.resolver_ambito(vendedor_sin_sucursal, org.id, 0)
    assert a.toda_la_org is False and a.branch_id is None


# --- Resumen -----------------------------------------------------------------

def test_resumen_neta_resta_devoluciones_aprobadas(db, org, branch_a, cajero_a, products_setup):
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "50")
    _devolucion(db, org, branch_a, cajero_a, v, "30")
    _devolucion(db, org, branch_a, cajero_a, v, "20", status="PENDING")
    r = mv.resumen(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"))
    assert (r.bruta, r.devuelto, r.neta, r.tickets, r.devoluciones) == (150.0, 30.0, 120.0, 2, 1)
    assert r.ticket_promedio == 60.0


def test_resumen_excluye_pendientes_borradores_y_canceladas(db, org, branch_a, cajero_a, products_setup):
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    for st in (DocumentStatus.PENDING, DocumentStatus.DRAFT, DocumentStatus.CANCELLED):
        _venta(db, org, branch_a, cajero_a, _v(products_setup), "999", status=st)
    r = mv.resumen(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"))
    assert (r.bruta, r.tickets) == (100.0, 1)


def test_resumen_venta_de_las_7pm_cae_en_su_dia_de_mexico(db, org, branch_a, cajero_a, products_setup):
    hoy = mv.hoy_mx()
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", dia=hoy, hora=19)   # 01:00 UTC de mañana
    assert mv.resumen(db, mv.Ambito(org.id, None, True), mv.Periodo(hoy, hoy)).neta == 100.0
    manana = mv.Periodo(hoy + timedelta(days=1), hoy + timedelta(days=1))
    assert mv.resumen(db, mv.Ambito(org.id, None, True), manana).neta == 0.0


def test_devolucion_resta_en_su_propio_dia(db, org, branch_a, cajero_a, products_setup):
    hoy = mv.hoy_mx()
    ayer = hoy - timedelta(days=1)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", dia=ayer)
    _devolucion(db, org, branch_a, cajero_a, v, "100", dia=hoy)
    assert mv.resumen(db, mv.Ambito(org.id, None, True), mv.Periodo(ayer, ayer)).neta == 100.0
    assert mv.resumen(db, mv.Ambito(org.id, None, True), mv.Periodo(hoy, hoy)).neta == -100.0


def test_resumen_respeta_el_ambito(db, org, branch_a, branch_b, cajero_a, products_setup):
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "200")
    hoy = mv.periodo_preset("hoy")
    assert mv.resumen(db, mv.Ambito(org.id, branch_a.id, False), hoy).neta == 100.0
    assert mv.resumen(db, mv.Ambito(org.id, None, True), hoy).neta == 300.0
    assert mv.resumen(db, mv.Ambito(org.id, None, False), hoy).tickets == 0
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd .worktrees/admin-fase1 && python3 -m pytest -q tests/test_metricas_ventas.py`
Expected: FAIL en la importación (`ModuleNotFoundError: app.services.metricas_ventas`).

- [ ] **Step 3: Escribir el servicio (periodo, ámbito, resumen)**

```python
# app/services/metricas_ventas.py
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
```

- [ ] **Step 4: Correr y ver que pasa**

Run: `cd .worktrees/admin-fase1 && python3 -m pytest -q tests/test_metricas_ventas.py`
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
cd .worktrees/admin-fase1
git add app/services/metricas_ventas.py tests/test_metricas_ventas.py
git commit -m "feat(reportes): servicio metricas_ventas con periodo, ámbito y venta neta

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 2: Servicio — series, métodos, sucursales, top y utilidad

**Files:**
- Modify: `app/services/metricas_ventas.py` (añadir al final)
- Test: `tests/test_metricas_ventas.py` (añadir al final)

**Interfaces:**
- Consumes: Tarea 1 (`Ambito`, `Periodo`, `filtros_documentos`, `filtros_devoluciones`, `_f`, `_armar_resumen`).
- Produces:
  - `DiaVentas(fecha: date, bruta, devuelto, neta: float, tickets: int)`; `por_dia(db, ambito, periodo) -> list[DiaVentas]` (un renglón por fecha, con ceros).
  - `HoraVentas(hora: int, neta: float, tickets: int)`; `por_hora(db, ambito, periodo) -> list[HoraVentas]` (24 renglones).
  - `MetodoVentas(total: float, tickets: int)`; `por_metodo(db, ambito, periodo) -> dict[str, MetodoVentas]` (claves `"CASH"`, `"CARD"`, …; efectivo neto de cambio; cada método neto de sus devoluciones).
  - `por_sucursal(db, org_id: int, periodo) -> dict[int, Resumen]` (solo sucursales con algo; el router rellena las demás con `Resumen` en ceros vía `RESUMEN_VACIO`).
  - `RESUMEN_VACIO: Resumen`.
  - `ProductoTop(nombre: str, cantidad: float, total: float)`; `top_productos(db, ambito, periodo, limite=5) -> list[ProductoTop]` (por `SalesLineItem.description`, orden piezas desc y nombre).
  - `utilidad_bruta(db, ambito, periodo) -> tuple[float, float]` = (utilidad sobre renglones con costo, menos lo devuelto que reingresó con costo; venta sin costo).

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# añadir al final de tests/test_metricas_ventas.py
from app.models.returns import SaleReturnItem  # noqa: E402


def test_por_dia_rellena_ceros_y_agrupa_en_dia_de_mexico(db, org, branch_a, cajero_a, products_setup):
    hoy = mv.hoy_mx()
    p = mv.Periodo(hoy - timedelta(days=2), hoy)
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", dia=hoy - timedelta(days=2), hora=19)
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "50", dia=hoy)
    _devolucion(db, org, branch_a, cajero_a, v, "10", dia=hoy)
    dias = mv.por_dia(db, mv.Ambito(org.id, None, True), p)
    assert [d.fecha for d in dias] == p.fechas()
    assert [(d.bruta, d.devuelto, d.neta, d.tickets) for d in dias] == [
        (100.0, 0.0, 100.0, 1), (0.0, 0.0, 0.0, 0), (50.0, 10.0, 40.0, 1),
    ]


def test_por_hora_trae_24_horas_y_no_recorta(db, org, branch_a, cajero_a, products_setup):
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", hora=7)
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "200", hora=22)
    horas = mv.por_hora(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"))
    assert [h.hora for h in horas] == list(range(24))
    assert horas[7].neta == 100.0 and horas[7].tickets == 1
    assert horas[22].neta == 200.0
    assert sum(h.tickets for h in horas) == 2


def test_por_metodo_resta_el_cambio_del_efectivo(db, org, branch_a, cajero_a, products_setup):
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "80", entregado="100")
    m = mv.por_metodo(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"))
    assert m["CASH"].total == 80.0 and m["CASH"].tickets == 1


def test_por_metodo_resta_la_devolucion_a_su_metodo(db, org, branch_a, cajero_a, products_setup):
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", metodo=PaymentMethod.CASH)
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "300", metodo=PaymentMethod.CARD)
    _devolucion(db, org, branch_a, cajero_a, v, "40", metodo=PaymentMethod.CARD)
    m = mv.por_metodo(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"))
    assert m["CASH"].total == 100.0
    assert m["CARD"].total == 260.0
    assert "TRANSFER" not in m


def test_por_sucursal_devuelve_resumen_neto_por_sucursal(db, org, branch_a, branch_b, cajero_a, products_setup):
    va = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "200")
    _devolucion(db, org, branch_a, cajero_a, va, "25")
    s = mv.por_sucursal(db, org.id, mv.periodo_preset("hoy"))
    assert s[branch_a.id].neta == 75.0 and s[branch_a.id].tickets == 1
    assert s[branch_b.id].neta == 200.0


def test_top_productos_por_piezas(db, org, branch_a, cajero_a, products_setup):
    for _ in range(3):
        _venta(db, org, branch_a, cajero_a, _v(products_setup), "10")
    docs = db.query(SalesDocument).all()
    for d in docs:
        for li in db.query(SalesLineItem).filter(SalesLineItem.document_id == d.id):
            li.description = "Gorra"
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "500")
    db.commit()
    top = mv.top_productos(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"), limite=5)
    assert top[0].nombre == "Gorra" and top[0].cantidad == 3.0 and top[0].total == 30.0
    assert len(top) == 2


def test_utilidad_bruta_solo_con_costo_y_resta_reingresos(db, org, branch_a, cajero_a, products_setup):
    variante = _v(products_setup)          # cost = 60 (conftest: precio 100 × 0.6)
    v = _venta(db, org, branch_a, cajero_a, variante, "100", costo="60")
    _venta(db, org, branch_a, cajero_a, variante, "70", costo="0")      # sin costo: fuera de la utilidad
    dev = _devolucion(db, org, branch_a, cajero_a, v, "100")
    db.add(SaleReturnItem(organization_id=org.id, return_id=dev.id, variant_id=variante.id,
                          quantity=Decimal("1"), refund_amount=Decimal("100"), is_inventory_reentry=True))
    db.commit()
    utilidad, sin_costo = mv.utilidad_bruta(db, mv.Ambito(org.id, None, True), mv.periodo_preset("hoy"))
    # (100 − 60) de la venta − (100 − 60) de la devolución que volvió al stock = 0
    assert utilidad == 0.0
    assert sin_costo == 70.0
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd .worktrees/admin-fase1 && python3 -m pytest -q tests/test_metricas_ventas.py`
Expected: 7 nuevas fallan con `AttributeError: module ... has no attribute 'por_dia'` (y similares); las 13 anteriores pasan.

- [ ] **Step 3: Implementar**

```python
# añadir al final de app/services/metricas_ventas.py

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
    """(utilidad SOLO sobre renglones con costo, menos lo devuelto que reingresó
    con costo; venta del periodo en renglones sin costo). Con `coalesce(costo, 0)`
    una pieza sin costo parecía 100 % de utilidad."""
    con_costo = SalesLineItem.unit_cost > 0
    fila = (
        db.query(
            func.coalesce(func.sum(case((con_costo, SalesLineItem.total_line - SalesLineItem.unit_cost * SalesLineItem.quantity), else_=0)), 0),
            func.coalesce(func.sum(case((con_costo, 0), else_=SalesLineItem.total_line)), 0),
        )
        .join(SalesDocument, SalesDocument.id == SalesLineItem.document_id)
        .filter(*filtros_documentos(ambito, periodo)).one()
    )
    reingresado = (
        db.query(func.coalesce(func.sum(SaleReturnItem.refund_amount - ProductVariant.cost * SaleReturnItem.quantity), 0))
        .select_from(SaleReturnItem)
        .join(SaleReturn, SaleReturn.id == SaleReturnItem.return_id)
        .join(ProductVariant, ProductVariant.id == SaleReturnItem.variant_id)
        .filter(*filtros_devoluciones(ambito, periodo), SaleReturnItem.is_inventory_reentry.is_(True),
                ProductVariant.cost > 0)
        .scalar()
    )
    return round(_f(fila[0]) - _f(reingresado), 2), _f(fila[1])
```

- [ ] **Step 4: Correr y ver que pasa**

Run: `cd .worktrees/admin-fase1 && python3 -m pytest -q tests/test_metricas_ventas.py`
Expected: 20 passed.

- [ ] **Step 5: Commit**

```bash
cd .worktrees/admin-fase1
git add app/services/metricas_ventas.py tests/test_metricas_ventas.py
git commit -m "feat(reportes): series por día y hora, métodos netos, sucursales, top y utilidad en metricas_ventas

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 3: `/reports/daily-summary` e `/reports/inicio` sobre el servicio

**Files:**
- Modify: `app/routers/reports.py:76-169` (`get_daily_summary`)
- Modify: `app/routers/reports_inicio.py:78-117,320-353,384-392` (`_filtros_venta`, `_periodo`, `_top`, `_sucursales`, `inicio`)
- Modify: `app/schemas/reports.py:56-60` (`PeriodoVentas`), `:140-145` (`SucursalInicio`)
- Modify: `docs/API_REFERENCE.md:140-148` (fila `/daily-summary` y fila `/inicio`)
- Test: `tests/test_reports_daily_summary.py`, `tests/test_reports_inicio.py` (añadir casos)

**Interfaces:**
- Consumes: `mv.resolver_ambito`, `mv.Periodo`, `mv.periodo_preset`, `mv.resumen`, `mv.por_metodo`, `mv.por_sucursal`, `mv.RESUMEN_VACIO`, `mv.top_productos`, `mv.utilidad_bruta`, `mv.hoy_mx`.
- Produces: `daily-summary` con claves nuevas `gross_revenue`, `returns_total`, `returns_count`; `PeriodoVentas.devuelto`; `SucursalInicio.devuelto_hoy`. `reports_inicio._filtros_venta` se elimina (usar `mv.filtros_documentos`); `reports._mx`/`_today_mx` se conservan como alias de `mv.mx`/`mv.hoy_mx` porque los importan `reports_inicio.py` y `reports_valuacion.py`.

- [ ] **Step 1: Pruebas que fallan**

```python
# añadir al final de tests/test_reports_daily_summary.py
from app.models.returns import SaleReturn  # noqa: E402


def test_daily_summary_resta_devoluciones_aprobadas(client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup):
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "R-10", "100", DocumentStatus.PAID)
    db.add(SaleReturn(organization_id=org.id, sale_id=v.id, user_id=cajero_a.id, branch_id=branch_a.id,
                      total_refunded=Decimal("30"), refund_method=PaymentMethod.CASH, reason="Prueba",
                      status="APPROVED"))
    db.commit()
    d = client.get("/api/reports/daily-summary", headers=auth_cajero_a).json()
    assert d["gross_revenue"] == 100.0
    assert d["returns_total"] == 30.0 and d["returns_count"] == 1
    assert d["total_revenue"] == 70.0
    assert d["payments"]["CASH"] == 70.0


def test_daily_summary_admin_sin_parametro_ve_toda_la_org(client, db, org, branch_a, branch_b, cajero_a, auth_admin_a, products_setup):
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "R-11", "100", DocumentStatus.PAID)
    doc_b = _venta(db, org, branch_b, cajero_a, _v(products_setup), "R-12", "200", DocumentStatus.PAID)
    assert doc_b.branch_id == branch_b.id
    d = client.get("/api/reports/daily-summary", headers=auth_admin_a).json()
    assert d["total_revenue"] == 300.0
    solo_a = client.get(f"/api/reports/daily-summary?branch_id={branch_a.id}", headers=auth_admin_a).json()
    assert solo_a["total_revenue"] == 100.0
```

```python
# añadir al final de tests/test_reports_inicio.py (usa los helpers _venta/_variante del archivo)
from app.models.returns import SaleReturn  # noqa: E402


def test_inicio_hoy_es_neto_y_trae_devuelto(client, db, org, branch_a, cajero_a, auth_admin_a):
    var = _variante(db, org, branch_a, "Gorra", "GOR-1", 5)
    v = _venta(db, org, branch_a, cajero_a, var, "100")
    db.add(SaleReturn(organization_id=org.id, sale_id=v.id, user_id=cajero_a.id, branch_id=branch_a.id,
                      total_refunded=Decimal("40"), refund_method=PaymentMethod.CASH, reason="Prueba",
                      status="APPROVED"))
    db.commit()
    d = client.get("/api/reports/inicio?completo=true", headers=auth_admin_a).json()
    assert d["hoy"]["total"] == 60.0 and d["hoy"]["devuelto"] == 40.0 and d["hoy"]["tickets"] == 1
    assert d["semana"]["total"] == 60.0
    assert d["por_metodo_hoy"]["CASH"] == 60.0
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd .worktrees/admin-fase1 && python3 -m pytest -q tests/test_reports_daily_summary.py tests/test_reports_inicio.py`
Expected: los 3 nuevos fallan (`KeyError: 'gross_revenue'`, `total_revenue == 300.0` falla porque el admin de `branch_a` hoy ve solo su sucursal, `KeyError: 'devuelto'`).

- [ ] **Step 3: Reescribir `get_daily_summary`**

Sustituir el cuerpo de `get_daily_summary` (`app/routers/reports.py:76-169`) por:

```python
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
    utilidad, _sin_costo = mv.utilidad_bruta(db, ambito, periodo)
    return {
        "date": periodo.inicio,
        "transactions_count": r.tickets,
        "total_revenue": r.neta,
        "gross_revenue": r.bruta,
        "returns_total": r.devuelto,
        "returns_count": r.devoluciones,
        "gross_profit": utilidad,
        "payments": {k: m.total for k, m in mv.por_metodo(db, ambito, periodo).items()},
        "top_selling_items": [{"name": p.nombre, "quantity": p.cantidad}
                              for p in mv.top_productos(db, ambito, periodo, limite=5)],
    }
```

Y en la cabecera de `app/routers/reports.py` (líneas 13-21) dejar los alias para quien aún importa de aquí:

```python
from app.services import metricas_ventas as mv

_MX = mv._MX
_today_mx = mv.hoy_mx
_mx = mv.mx
```

(`_resolver_sucursal` y `HQ_ROLES` se quedan en `reports.py` hasta la Tarea 4, que los retira cuando ya nadie los use.)

- [ ] **Step 4: Schemas y `reports_inicio.py`**

En `app/schemas/reports.py`:

```python
class PeriodoVentas(BaseModel):
    desde: date
    hasta: date
    total: float        # venta NETA: cobradas menos devoluciones aprobadas del periodo
    devuelto: float = 0.0
    tickets: int
```

```python
class SucursalInicio(BaseModel):
    branch_id: int
    nombre: str
    ventas_hoy: float        # neta
    devuelto_hoy: float = 0.0
    tickets_hoy: int
    corte: CorteInicio
    poca_existencia: int     # variantes ≤ umbral en esa sucursal
```

En `app/routers/reports_inicio.py`:

- Importar `from app.services import metricas_ventas as mv` y quitar `get_daily_summary` y `SALES_REPORT_STATUSES` de los imports si quedan sin uso (`_sin_movimiento` sigue usando `SALES_REPORT_STATUSES`: conservarlo).
- Sustituir `_filtros_venta`, `_periodo` y `_top` por:

```python
def _ambito(org_id: int, sucursal: Optional[int]) -> mv.Ambito:
    return mv.Ambito(org_id, sucursal, sucursal is None)


def _periodo(db: Session, org_id: int, sucursal: Optional[int], desde: date, hasta: date) -> PeriodoVentas:
    r = mv.resumen(db, _ambito(org_id, sucursal), mv.Periodo(desde, hasta))
    return PeriodoVentas(desde=desde, hasta=hasta, total=r.neta, devuelto=r.devuelto, tickets=r.tickets)


def _top(db: Session, org_id: int, sucursal: Optional[int], desde: date, hasta: date) -> List[ProductoTop]:
    return [ProductoTop(nombre=p.nombre, cantidad=p.cantidad, total=p.total)
            for p in mv.top_productos(db, _ambito(org_id, sucursal), mv.Periodo(desde, hasta), limite=MAX_TOP)]
```

- En `_utilidad_bruta_hoy` sustituir el cuerpo por `return mv.utilidad_bruta(db, _ambito(org_id, sucursal), mv.Periodo(hoy, hoy))`.
- En `_sucursales`, sustituir el diccionario `ventas = {...}` y el `tickets, total = ventas.get(b.id, (0, 0))` por:

```python
    por_sucursal = mv.por_sucursal(db, org_id, mv.Periodo(hoy, hoy))
    salida = []
    for b in sucursales:
        r = por_sucursal.get(b.id, mv.RESUMEN_VACIO)
        poca = (  # esta consulta queda exactamente como está hoy (líneas 339-348)
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
            branch_id=b.id, nombre=b.name, ventas_hoy=r.neta, devuelto_hoy=r.devuelto, tickets_hoy=r.tickets,
            corte=_corte(db, org_id, b.id), poca_existencia=int(poca or 0),
        ))
```

- En `inicio()`, sustituir la llamada a `get_daily_summary` y `por_metodo = ...` por:

```python
    por_metodo = {k: m.total for k, m in mv.por_metodo(db, _ambito(org_id, sucursal), mv.Periodo(hoy, hoy)).items()}
```

`_sucursal_del_inicio` no cambia (ya valida que la sucursal sea de la org y fija al gerente).

- [ ] **Step 5: Correr las pruebas de reportes**

Run: `cd .worktrees/admin-fase1 && python3 -m pytest -q tests/test_reports_daily_summary.py tests/test_reports_inicio.py tests/test_regresion_reportes.py tests/test_metricas_ventas.py`
Expected: todo en verde. Si una prueba vieja de `test_reports_inicio.py` asume que una venta `REFUNDED_TOTAL` suma bruto sin devolución registrada, sigue pasando (sin `SaleReturn` aprobada no se resta nada).

- [ ] **Step 6: Documentar**

En `docs/API_REFERENCE.md`, fila `/daily-summary · /dashboard · /sales-by-hour`, añadir al texto: "`/daily-summary`: `total_revenue` es venta **neta** (cobradas − devoluciones aprobadas del día, `app/services/metricas_ventas.py`); trae `gross_revenue`, `returns_total`, `returns_count`; `payments` resta el vuelto y lo devuelto por método. Ámbito: roles de oficina sin `branch_id` = toda la org." En la fila `/inicio`, cambiar "`{desde, hasta, total, tickets}` (7 días incluido hoy, `SALES_REPORT_STATUSES`)" por "`{desde, hasta, total, devuelto, tickets}` (`total` neto de devoluciones aprobadas; 7 días incluido hoy)" y añadir `devuelto_hoy` a `sucursales[]`.

- [ ] **Step 7: Commit**

```bash
cd .worktrees/admin-fase1
git add app/routers/reports.py app/routers/reports_inicio.py app/schemas/reports.py docs/API_REFERENCE.md tests/test_reports_daily_summary.py tests/test_reports_inicio.py
git commit -m "feat(reportes): daily-summary e inicio con venta neta y ámbito explícito

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 4: `/reports/dashboard`, `/reports/sales-by-hour` y `/reports/command-center/stats`

**Files:**
- Modify: `app/routers/reports.py:305-578` (`get_dashboard_stats`), `:580-638` (`get_sales_by_hour`), `:717-943` (`get_command_center_stats`), `:46-75` (retirar `HQ_ROLES`/`_resolver_sucursal` si ya nadie los usa: `grep -rn "_resolver_sucursal\|reports import.*HQ_ROLES" app/`)
- Modify: `docs/API_REFERENCE.md:143-144`
- Test: `tests/test_reports_dashboard.py` (nuevo)

**Interfaces:**
- Consumes: `mv.*` de Tareas 1-2.
- Produces: `dashboard.kpis` suma `returns`, `returns_count`, `prev_returns`; `kpis.sales` neta; `charts.trend/trend_previous` por día de México; `charts.hourly` 24 etiquetas `"0:00".."23:00"`; `charts.payments` = `{método: {total, count}}`. `sales-by-hour.hourly` 24 renglones. `command-center.global.total_sales` neta, `returns_total` = devuelto, `branches[].total_sales` neta, `hourly_distribution` 24.

- [ ] **Step 1: Pruebas que fallan**

```python
# tests/test_reports_dashboard.py
"""`/reports/dashboard`, `/reports/sales-by-hour` y `/reports/command-center/stats`
sobre `metricas_ventas`: neto, día de México, 24 horas y ámbito explícito."""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from itertools import count
from zoneinfo import ZoneInfo

from app.models.returns import SaleReturn
from app.models.sales import DocumentStatus, Payment, PaymentMethod, SalesDocument, SalesLineItem
from app.services import metricas_ventas as mv

_MX = ZoneInfo("America/Mexico_City")
_folios = count(1)


def _instante(dia, hora=12):
    return datetime.combine(dia, time(hora), tzinfo=_MX).astimezone(timezone.utc)


def _venta(db, org, branch, user, variante, total, *, dia=None, hora=12, status=DocumentStatus.PAID):
    dia = dia or mv.hoy_mx()
    doc = SalesDocument(organization_id=org.id, branch_id=branch.id, seller_id=user.id, folio=next(_folios),
                        series="A", subtotal=Decimal(total), tax_amount=Decimal("0"),
                        total_amount=Decimal(total), status=status, doc_type="ORDER")
    doc.created_at = _instante(dia, hora)
    db.add(doc)
    db.flush()
    db.add(SalesLineItem(organization_id=org.id, document_id=doc.id, variant_id=variante.id,
                         description=f"Producto {doc.folio}", quantity=1, unit_price=Decimal(total),
                         total_line=Decimal(total), unit_cost=Decimal("10")))
    pago = Payment(organization_id=org.id, sales_document_id=doc.id, method=PaymentMethod.CASH, amount=Decimal(total))
    pago.created_at = doc.created_at
    db.add(pago)
    db.commit()
    return doc


def _devolucion(db, org, branch, user, venta, importe):
    dev = SaleReturn(organization_id=org.id, sale_id=venta.id, user_id=user.id, branch_id=branch.id,
                     total_refunded=Decimal(importe), refund_method=PaymentMethod.CASH, reason="Prueba",
                     status="APPROVED")
    db.add(dev)
    db.commit()
    return dev


def _v(products_setup):
    return products_setup["product_a"][1]


def test_dashboard_tendencia_agrupa_por_dia_de_mexico(client, db, org, branch_a, cajero_a, auth_admin_a, products_setup):
    hoy = mv.hoy_mx()
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", dia=hoy, hora=19)   # 01:00 UTC de mañana
    d = client.get(f"/api/reports/dashboard?start_date={hoy - timedelta(days=1)}&end_date={hoy}&branch_id=0",
                   headers=auth_admin_a).json()
    assert d["charts"]["trend"]["data"] == [0.0, 100.0]
    assert d["kpis"]["sales"] == 100.0


def test_dashboard_kpis_netos_y_comparativo(client, db, org, branch_a, cajero_a, auth_admin_a, products_setup):
    hoy = mv.hoy_mx()
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", dia=hoy)
    _devolucion(db, org, branch_a, cajero_a, v, "25")
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "60", dia=hoy - timedelta(days=1))
    d = client.get(f"/api/reports/dashboard?start_date={hoy}&end_date={hoy}&branch_id=0", headers=auth_admin_a).json()
    k = d["kpis"]
    assert (k["sales"], k["orders"], k["returns"], k["returns_count"]) == (75.0, 1, 25.0, 1)
    assert k["avg_ticket"] == 75.0
    assert (k["prev_sales"], k["prev_orders"], k["prev_returns"]) == (60.0, 1, 0.0)
    assert d["charts"]["trend_previous"]["data"] == [60.0]
    assert d["charts"]["payments"]["CASH"] == {"total": 75.0, "count": 1}


def test_dashboard_admin_sin_sucursal_en_query_ve_toda_la_org(client, db, org, branch_a, branch_b, cajero_a, auth_admin_a, products_setup):
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "200")
    hoy = mv.hoy_mx()
    d = client.get(f"/api/reports/dashboard?start_date={hoy}&end_date={hoy}", headers=auth_admin_a).json()
    assert d["kpis"]["sales"] == 300.0


def test_dashboard_y_sales_by_hour_traen_24_horas(client, db, org, branch_a, cajero_a, auth_admin_a, products_setup):
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", hora=7)
    hoy = mv.hoy_mx()
    d = client.get(f"/api/reports/dashboard?start_date={hoy}&end_date={hoy}&branch_id=0", headers=auth_admin_a).json()
    assert len(d["charts"]["hourly"]["labels"]) == 24 and d["charts"]["hourly"]["data"][7] == 100.0
    h = client.get("/api/reports/sales-by-hour?branch_id=0", headers=auth_admin_a).json()
    assert [x["hour"] for x in h["hourly"]] == list(range(24))
    assert h["hourly"][7] == {"hour": 7, "amount": 100.0, "tickets": 1}


def test_command_center_global_y_sucursales_netos(client, db, org, branch_a, branch_b, cajero_a, auth_admin_a, products_setup):
    va = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "200")
    _devolucion(db, org, branch_a, cajero_a, va, "30")
    d = client.get("/api/reports/command-center/stats", headers=auth_admin_a).json()
    assert d["global"]["total_sales"] == 270.0 and d["global"]["returns_total"] == 30.0
    por_sucursal = {b["id"]: b["total_sales"] for b in d["branches"]}
    assert por_sucursal[branch_a.id] == 70.0 and por_sucursal[branch_b.id] == 200.0
    assert len(d["hourly_distribution"]) == 24
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd .worktrees/admin-fase1 && python3 -m pytest -q tests/test_reports_dashboard.py`
Expected: 5 failed (tendencia `[100.0, 0.0]` o `[0.0, 0.0]` según la hora UTC, `KeyError: 'returns'`, `sales == 100.0` en vez de 300, 14 horas, `270.0 != 300.0`).

- [ ] **Step 3: Reescribir `get_dashboard_stats`**

Sustituir desde `if not start_date:` hasta `return {...}` (`reports.py:319-578`) por:

```python
    hoy = mv.hoy_mx()
    periodo = mv.Periodo(start_date or hoy, end_date or hoy)
    ambito = mv.resolver_ambito(current_user, org_id, branch_id)
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

    # 2. Tendencia por día de México (antes agrupaba por día UTC)
    dias = mv.por_dia(db, ambito, periodo)
    dias_prev = mv.por_dia(db, ambito, periodo.anterior())
    etiquetas = [d.fecha.strftime("%a %d") for d in dias]

    # 3. Por hora: las 24 (quien pinta recorta)
    horas = mv.por_hora(db, ambito, periodo)

    # 4. Cobros por método, netos de vuelto y devoluciones
    metodos = {k: {"total": m.total, "count": m.tickets} for k, m in mv.por_metodo(db, ambito, periodo).items()}

    # 5. Top productos del periodo
    top = mv.top_productos(db, ambito, periodo, limite=5)

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

    # 10. SKUs distintos vendidos
    unique_skus_sold = db.query(func.count(func.distinct(SalesLineItem.variant_id)))\
        .join(SalesDocument).filter(*filtros).scalar() or 0

    # 11. Mapa día-de-semana × hora
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
        },
        "charts": {
            "trend": {"labels": etiquetas, "data": [d.neta for d in dias]},
            "trend_previous": {"labels": etiquetas, "data": [d.neta for d in dias_prev]},
            "hourly": {"labels": [f"{h.hora}:00" for h in horas], "data": [h.neta for h in horas]},
            "payments": metodos,
            "heatmap": heatmap_list,
        },
        "top_products": [
            {"name": p.nombre, "qty": p.cantidad, "trend": top_product_trends.get(p.nombre, [])} for p in top
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
```

La docstring del endpoint pasa a: `"""KPIs, tendencias y alertas del periodo. Venta neta y día de México por `app/services/metricas_ventas.py`; roles de oficina sin `branch_id` ven toda la organización."""`. Los parámetros de la firma no cambian.

- [ ] **Step 4: Reescribir `get_sales_by_hour`**

Sustituir desde `if not date:` hasta el `return` (`reports.py:600-638`) por:

```python
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
```

Actualizar la docstring: `# 0-23 hrs` en lugar de `# 8-21 hrs`.

- [ ] **Step 5: Reescribir la parte de ventas de `get_command_center_stats`**

Sustituir desde `if not start_date: start_date = _today_mx()` hasta `hourly_map = {...}` (`reports.py:729-813`) por:

```python
    hoy = mv.hoy_mx()
    periodo = mv.Periodo(start_date or hoy, end_date or hoy)
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
    items_per_ticket = float(total_items) / total_tickets if total_tickets > 0 else 0

    payment_map = {k: m.total for k, m in mv.por_metodo(db, ambito, periodo).items()}
    horas = mv.por_hora(db, ambito, periodo)
```

Más abajo, en el desglose por sucursal, sustituir `sales_by_branch = dict(...)` por `por_sucursal = mv.por_sucursal(db, org_id, periodo)` y `b_sales = float(sales_by_branch.get(b.id, 0) or 0)` por `b_sales = por_sucursal.get(b.id, mv.RESUMEN_VACIO).neta`. En el `return`, `"hourly_distribution": [{"hour": h.hora, "amount": h.neta} for h in horas]`. Lo demás (alertas, top por producto) no cambia: `sales_filters` sigue existiendo con el mismo nombre.

- [ ] **Step 6: Retirar lo que quedó sin uso**

Run: `cd .worktrees/admin-fase1 && grep -rn "_resolver_sucursal\|HQ_ROLES" app/ | grep -v metricas_ventas`
Si solo aparece en `reports.py` (definición y `by-waiter`), dejar `by-waiter` como está (fuera del alcance) y borrar `_resolver_sucursal` y `HQ_ROLES` de `reports.py`; si otro archivo los importa, dejarlos.

- [ ] **Step 7: Correr**

Run: `cd .worktrees/admin-fase1 && python3 -m pytest -q tests/test_reports_dashboard.py tests/test_reports_umbral.py tests/test_variant_traceability.py tests/test_reports_inicio.py tests/test_reports_daily_summary.py tests/test_metricas_ventas.py`
Expected: todo en verde. `test_reports_umbral.py::test_dashboard_respeta_la_sucursal_pedida_tambien_para_la_duena` sigue pasando (`branch_id` explícito → esa sucursal; `0` → toda).

- [ ] **Step 8: Documentar**

En `docs/API_REFERENCE.md`, filas `/daily-summary · /dashboard · /sales-by-hour` y `/command-center/stats`, añadir: "Desde 2026-10-23 todos usan `app/services/metricas_ventas.py`: `kpis.sales`/`global.total_sales`/`branches[].total_sales` son venta **neta** (cobradas − devoluciones aprobadas), `kpis.returns`/`returns_count`/`prev_returns` y `kpis.gross_sales` nuevos; `charts.trend` agrupa por día de México; `charts.hourly`, `sales-by-hour.hourly` y `hourly_distribution` traen las 24 horas; `charts.payments` es `{método: {total, count}}` neto de vuelto y devoluciones. Ámbito de `/dashboard` y `/sales-by-hour`: roles de oficina sin `branch_id` = toda la org (antes, la del usuario)."

- [ ] **Step 9: Commit**

```bash
cd .worktrees/admin-fase1
git add app/routers/reports.py docs/API_REFERENCE.md tests/test_reports_dashboard.py
git commit -m "fix(reportes): dashboard, ventas por hora y centro de mando netos, por día de México y con 24 horas

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 5: `/sales/stats` y `/returns/` sobre el servicio

**Files:**
- Modify: `app/routers/sales.py:148-270` (`get_sales_stats`)
- Modify: `app/routers/returns.py:118-191` (`list_returns`)
- Modify: `docs/API_REFERENCE.md:128-129` (Devoluciones) y la sección de Ventas donde describe `/stats` (`grep -n "/stats" docs/API_REFERENCE.md`)
- Test: `tests/test_sales_stats_y_returns.py` (nuevo)

**Interfaces:**
- Consumes: `mv.*`.
- Produces: `/sales/stats` con las mismas claves (`total_sales` neta, `total_transactions`, `average_ticket`, `payment_methods`, `refund_count`, `refund_total`, `peak_hour`) más `gross_sales`; `start_date`/`end_date` como `date` (`YYYY-MM-DD`, que es lo que manda el frontend). `/returns/`: `start_date`/`end_date` como `date` en día de México; sin fechas y sin `status=PENDING`, los últimos 30 días; `branch_id` por `resolver_ambito`.

- [ ] **Step 1: Pruebas que fallan**

```python
# tests/test_sales_stats_y_returns.py
"""`/sales/stats` y `/returns/` con el criterio único de `metricas_ventas`."""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from itertools import count
from zoneinfo import ZoneInfo

from app.models.returns import SaleReturn
from app.models.sales import DocumentStatus, Payment, PaymentMethod, SalesDocument, SalesLineItem
from app.services import metricas_ventas as mv

_MX = ZoneInfo("America/Mexico_City")
_folios = count(1)


def _instante(dia, hora=12):
    return datetime.combine(dia, time(hora), tzinfo=_MX).astimezone(timezone.utc)


def _venta(db, org, branch, user, variante, total, *, dia=None, hora=12, status=DocumentStatus.PAID, doc_type="INVOICE"):
    dia = dia or mv.hoy_mx()
    doc = SalesDocument(organization_id=org.id, branch_id=branch.id, seller_id=user.id, folio=next(_folios),
                        series="A", subtotal=Decimal(total), tax_amount=Decimal("0"),
                        total_amount=Decimal(total), status=status, doc_type=doc_type)
    doc.created_at = _instante(dia, hora)
    db.add(doc)
    db.flush()
    db.add(SalesLineItem(organization_id=org.id, document_id=doc.id, variant_id=variante.id,
                         description="Producto", quantity=1, unit_price=Decimal(total),
                         total_line=Decimal(total), unit_cost=Decimal("10")))
    pago = Payment(organization_id=org.id, sales_document_id=doc.id, method=PaymentMethod.CASH, amount=Decimal(total))
    pago.created_at = doc.created_at
    db.add(pago)
    db.commit()
    return doc


def _devolucion(db, org, branch, user, venta, importe, *, dia=None, status="APPROVED"):
    dev = SaleReturn(organization_id=org.id, sale_id=venta.id, user_id=user.id, branch_id=branch.id,
                     total_refunded=Decimal(importe), refund_method=PaymentMethod.CASH, reason="Prueba",
                     status=status)
    dev.created_at = _instante(dia or mv.hoy_mx())
    db.add(dev)
    db.commit()
    return dev


def _v(products_setup):
    return products_setup["product_a"][1]


def test_sales_stats_neto_sin_pendientes_y_con_hora_pico(client, db, org, branch_a, cajero_a, auth_admin_a, products_setup):
    hoy = mv.hoy_mx()
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", hora=17)
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "50", hora=17)
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "999", status=DocumentStatus.PENDING)
    _devolucion(db, org, branch_a, cajero_a, v, "30")
    s = client.get(f"/api/sales/stats?start_date={hoy}&end_date={hoy}", headers=auth_admin_a).json()
    assert (s["total_sales"], s["gross_sales"], s["total_transactions"]) == (120.0, 150.0, 2)
    assert s["average_ticket"] == 60.0
    assert (s["refund_count"], s["refund_total"]) == (1, 30.0)
    assert s["payment_methods"]["CASH"] == 120.0
    assert s["peak_hour"] == "17:00"


def test_sales_stats_cajera_solo_su_sucursal(client, db, org, branch_a, branch_b, cajero_a, auth_cajero_a, products_setup):
    _venta(db, org, branch_a, cajero_a, _v(products_setup), "100")
    _venta(db, org, branch_b, cajero_a, _v(products_setup), "200")
    s = client.get("/api/sales/stats", headers=auth_cajero_a).json()
    assert s["total_sales"] == 100.0


def test_returns_lista_por_dia_de_mexico_y_30_dias_por_defecto(client, db, org, branch_a, cajero_a, auth_admin_a, products_setup):
    hoy = mv.hoy_mx()
    v = _venta(db, org, branch_a, cajero_a, _v(products_setup), "100", dia=hoy - timedelta(days=40))
    vieja = _devolucion(db, org, branch_a, cajero_a, v, "10", dia=hoy - timedelta(days=40))
    reciente = _devolucion(db, org, branch_a, cajero_a, v, "20", dia=hoy)
    pendiente_vieja = _devolucion(db, org, branch_a, cajero_a, v, "5", dia=hoy - timedelta(days=40), status="PENDING")

    ids = {r["id"] for r in client.get("/api/returns/", headers=auth_admin_a).json()}
    assert reciente.id in ids and vieja.id not in ids

    ids = {r["id"] for r in client.get("/api/returns/?status=PENDING", headers=auth_admin_a).json()}
    assert ids == {pendiente_vieja.id}

    desde = hoy - timedelta(days=45)
    ids = {r["id"] for r in client.get(f"/api/returns/?start_date={desde}&end_date={hoy}", headers=auth_admin_a).json()}
    assert {vieja.id, reciente.id, pendiente_vieja.id} <= ids

    ids = {r["id"] for r in client.get(f"/api/returns/?start_date={hoy}&end_date={hoy}", headers=auth_admin_a).json()}
    assert ids == {reciente.id}
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd .worktrees/admin-fase1 && python3 -m pytest -q tests/test_sales_stats_y_returns.py`
Expected: 3 failed (`KeyError: 'gross_sales'`; `total_sales` incluye la PENDING; la devolución vieja aparece sin fechas).

- [ ] **Step 3: Reescribir `get_sales_stats`**

Sustituir la firma y el cuerpo (`sales.py:148-270`) por:

```python
@router.get("/stats")
def get_sales_stats(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """KPIs del listado de ventas: total neto, tickets, ticket promedio, métodos,
    devoluciones y hora pico. Criterio único en `app/services/metricas_ventas.py`
    (antes aquí sumaban pendientes y borradores)."""
    hoy = mv.hoy_mx()
    periodo = mv.Periodo(start_date or hoy, end_date or hoy)
    ambito = mv.resolver_ambito(current_user, org_id, branch_id)
    r = mv.resumen(db, ambito, periodo)
    horas = mv.por_hora(db, ambito, periodo)
    pico = max(horas, key=lambda h: (h.tickets, -h.hora))
    return {
        "total_sales": r.neta,
        "gross_sales": r.bruta,
        "total_transactions": r.tickets,
        "average_ticket": r.ticket_promedio,
        "payment_methods": {k: m.total for k, m in mv.por_metodo(db, ambito, periodo).items()},
        "refund_count": r.devoluciones,
        "refund_total": r.devuelto,
        "peak_hour": f"{pico.hora:02d}:00" if pico.tickets > 0 else None,
    }
```

Añadir `from datetime import date` a los imports de `sales.py` si no está, y `from app.services import metricas_ventas as mv`. El `SaleReturn` que importaba el endpoint sigue usándose en otros puntos del archivo (`grep -n SaleReturn app/routers/sales.py`); no retirar el import si queda algún uso.

- [ ] **Step 4: Reescribir `list_returns`**

Sustituir la firma y el cuerpo (`returns.py:118-191`) por:

```python
@router.get("/")
def list_returns(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    branch_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    paginate: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Lista devoluciones de la organización. Fechas en día de México; sin
    fechas, los últimos 30 días, salvo `status=PENDING` (lo pendiente no caduca).
    Ámbito: roles de oficina ven toda la org o la sucursal pedida; los demás la suya."""
    from app.models.returns import SaleReturn, SaleReturnItem
    from sqlalchemy.orm import joinedload, selectinload
    from app.services import metricas_ventas as mv

    query = db.query(SaleReturn).options(
        joinedload(SaleReturn.sale),
        joinedload(SaleReturn.user),
        joinedload(SaleReturn.branch),
        joinedload(SaleReturn.supervisor),
        selectinload(SaleReturn.items).joinedload(SaleReturnItem.variant)
    ).filter(SaleReturn.organization_id == org_id)

    ambito = mv.resolver_ambito(current_user, org_id, branch_id)
    if not ambito.toda_la_org:
        query = query.filter(SaleReturn.branch_id == ambito.branch_id)

    if status:
        query = query.filter(SaleReturn.status == status)

    if start_date is None and end_date is None and status != "PENDING":
        periodo = mv.periodo_preset("30d")
        start_date, end_date = periodo.inicio, periodo.fin
    if start_date:
        query = query.filter(mv.dia_mx(SaleReturn.created_at) >= start_date)
    if end_date:
        query = query.filter(mv.dia_mx(SaleReturn.created_at) <= end_date)

    from app.schemas.returns import SaleReturn as SaleReturnSchema
    ordered = query.order_by(SaleReturn.created_at.desc())
    if paginate:
        total = ordered.count()
        raw = ordered.offset(skip).limit(limit).all()
        return {"items": [SaleReturnSchema.model_validate(r) for r in raw], "total": total, "skip": skip, "limit": limit}
    return [SaleReturnSchema.model_validate(r) for r in ordered.offset(skip).limit(limit).all()]
```

Añadir `from datetime import date` y `from typing import Optional` a los imports de `returns.py` si faltan. Nota: con `resolver_ambito`, un GERENTE puede pedir otra sucursal en `/returns/` (antes solo ADMIN/DUEÑO); es el mismo criterio que ya tenían todos los reportes y queda documentado.

- [ ] **Step 5: Correr**

Run: `cd .worktrees/admin-fase1 && python3 -m pytest -q tests/test_sales_stats_y_returns.py tests/test_returns*.py tests/test_sales*.py -p no:warnings`
Expected: verde. Si alguna prueba de devoluciones existente lista sin fechas una devolución creada hace más de 30 días, ajustarla pasando `start_date`.

- [ ] **Step 6: Documentar**

`docs/API_REFERENCE.md`, sección Devoluciones: tras `GET /sale/{id} · / · /{id}` añadir "(`/` acepta `start_date`/`end_date` `YYYY-MM-DD` en día de México, `branch_id` para roles de oficina y `status`; sin fechas, últimos 30 días salvo `status=PENDING`)". En la sección Ventas, donde describe `/stats`, añadir "neto de devoluciones aprobadas, sin pendientes ni borradores; trae `gross_sales` (`app/services/metricas_ventas.py`)".

- [ ] **Step 7: Commit**

```bash
cd .worktrees/admin-fase1
git add app/routers/sales.py app/routers/returns.py docs/API_REFERENCE.md tests/test_sales_stats_y_returns.py
git commit -m "fix(ventas): /sales/stats neto y sin pendientes; /returns/ por día de México con 30 días por defecto

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 6: Bugs de paso — `POST /api/sales` sin barra y el redirect muerto de `/hq/sales`

**Files:**
- Modify: `app/routers/sales.py:368` (mover el decorador) y `:464` (`create_sale`)
- Modify: `app/main.py:325-330` (borrar el redirect)
- Test: `tests/test_sales_rutas.py` (nuevo)

**Interfaces:**
- Produces: `POST /api/sales` y `POST /api/sales/` llegan los dos a `create_sale`; `GET /hq/sales` lo sirve la SPA (`index.html`).

- [ ] **Step 1: Pruebas que fallan**

```python
# tests/test_sales_rutas.py
"""Dos rutas rotas por accidente: `POST /api/sales` sin barra caía en una función
auxiliar (422 "query.variant required") y `GET /hq/sales` redirigía a una ruta
de React que ya no existe ("Página no encontrada" al refrescar)."""


def test_post_sales_sin_barra_llega_a_create_sale(client, org, auth_admin_a):
    # ADMINISTRADOR salta el gating de módulo (app/core/permissions.py), así no hace falta habilitar `pos`.
    r = client.post("/api/sales", json={"items": [], "payments": []},
                    headers={**auth_admin_a, "X-Organization-ID": str(org.id)})
    # create_sale responde 400 "El ticket está vacío"; antes era 422 por un query param inexistente.
    assert r.status_code == 400, r.text
    assert "vacío" in r.json()["detail"]


def test_hq_sales_no_redirige_a_ruta_muerta(client):
    r = client.get("/hq/sales", follow_redirects=False)
    assert r.status_code != 302 or r.headers.get("location") != "/hq/sales-log"
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd .worktrees/admin-fase1 && python3 -m pytest -q tests/test_sales_rutas.py`
Expected: 2 failed (422 y 302 a `/hq/sales-log`).

- [ ] **Step 3: Arreglar**

En `app/routers/sales.py`, quitar la línea `@router.post("", response_model=Dict[str, Any], include_in_schema=False)` de encima de `_line_description` (línea 368) y ponerla justo encima de `@router.post("/", response_model=Dict[str, Any])` de `create_sale` (línea 464), quedando:

```python
@router.post("", response_model=Dict[str, Any], include_in_schema=False)
@router.post("/", response_model=Dict[str, Any])
def create_sale(
```

En `app/main.py`, borrar el bloque:

```python
# /hq/sales mantiene compat con bookmarks viejos; la ruta React es /hq/sales-log.
@app.get("/hq/sales", include_in_schema=False)
async def hq_sales_redirect():
    return RedirectResponse(url="/hq/sales-log", status_code=302)
```

y dejar el comentario del Sprint 3 solo sobre `/boxes`.

- [ ] **Step 4: Correr**

Run: `cd .worktrees/admin-fase1 && python3 -m pytest -q tests/test_sales_rutas.py tests/test_sales*.py -p no:warnings`
Expected: verde.

- [ ] **Step 5: Commit**

```bash
cd .worktrees/admin-fase1
git add app/routers/sales.py app/main.py tests/test_sales_rutas.py
git commit -m "fix(ventas): POST /api/sales sin barra llega a create_sale; /hq/sales ya no redirige a una ruta muerta

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 7: Suite completa, build del frontend y cierre de docs

**Files:**
- Modify: `docs/superpowers/specs/2026-10-23-admin-precision-inicio-fusiones-design.md` (línea 3: `**Estado:**` → "fase 1 implementada en `feat/admin-metricas-ventas`, pendiente de fusión")
- Modify: `CLAUDE.md` §6 (una viñeta nueva)

- [ ] **Step 1: Suite de backend**

Run: `cd .worktrees/admin-fase1 && python3 -m pytest -q --ignore=tests/test_cash_complete.py --ignore=tests/test_branch_dashboard.py --ignore=tests/test_cash_close_guided.py -p no:warnings 2>&1 | tail -5`
Expected: 0 failed (los dos archivos ignorados fallan en esta máquina por el uvicorn ajeno en :8000; en CI corren). Si falla algo que no tocaron las tareas 1-6, anotarlo y compararlo con `main` antes de tocarlo.

- [ ] **Step 2: Frontend intacto**

Run: `cd .worktrees/admin-fase1/frontend && npx tsc --noEmit -p tsconfig.json && npx vitest run --reporter=dot 2>&1 | tail -3`
Expected: tsc sin errores; vitest verde salvo el timeout conocido de `rutasPerezosas` bajo carga (pasa solo). No se tocó `frontend/`: cualquier otro fallo es ajeno.

- [ ] **Step 3: Docs**

En `CLAUDE.md` §6 añadir la viñeta: "**Una sola regla de venta en reportes.** `app/services/metricas_ventas.py` define qué cuenta como venta (cobradas − devoluciones aprobadas, día de México) y el ámbito por rol. Un reporte nuevo lo consume; no escribas otro `status.in_(...)` a mano." Actualizar el `**Estado:**` del spec.

- [ ] **Step 4: Commit**

```bash
cd .worktrees/admin-fase1
git add CLAUDE.md docs/superpowers/specs/2026-10-23-admin-precision-inicio-fusiones-design.md
git commit -m "docs: regla única de venta en CLAUDE.md y estado del spec de la vista del admin

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

La fusión a `main` y el despliegue los autoriza el usuario (spec §7: antes de desplegar, avisarle que las cifras de Eleven bajarán lo devuelto).
