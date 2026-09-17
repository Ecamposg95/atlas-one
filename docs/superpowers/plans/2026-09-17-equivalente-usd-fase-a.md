# Equivalente en dólares (USD) — Fase A — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que cualquier organización pueda encender un tipo de cambio USD (FIX de Banxico + margen, o un tipo fijo capturado a mano) y que a partir de ese momento el POS muestre el total del carrito y el precio de cada producto en dólares, y el ticket imprima el equivalente con el tipo de cambio usado, congelado en la venta. Si nadie lo enciende, nada cambia en ninguna pantalla.

**Architecture:** Una tabla global `exchange_rates` (una fila por moneda y día) que llena un job diario contra el SIE de Banxico; tres columnas de política en `organization` (`usd_rate_mode`, `usd_rate_manual`, `usd_rate_margin`); un servicio puro `app/services/exchange_rate.py` que es la **única** fuente del tipo efectivo y de la conversión —igual que `app/services/tax.py` lo es del IVA—; un snapshot `sales_documents.usd_rate` que `create_sale` asigna de forma defensiva sin tocar ningún cálculo de cobro; y en el frontend un store de Zustand más funciones puras en `src/utils/usd.ts` que solo pintan.

**Tech Stack:** FastAPI · SQLAlchemy 2.0 · Pydantic v2 · httpx · pytest (SQLite en memoria) · React 18 + TypeScript · Zustand · vitest · PostgreSQL

**Spec:** `docs/superpowers/specs/2026-09-17-equivalente-usd-design.md`

## Global Constraints

- **`main` es producción con clientes vivos** (Kaory en Railway; Ginebra, Imaltzin y Eleven en el VPS). Trabajar en rama `feat/equivalente-usd`; no pushear `main` sin permiso del usuario.
- **Neutralidad absoluta por default.** `usd_rate_mode = 'off'` para toda organización existente. Ninguna pantalla, ningún ticket y ninguna respuesta de API cambia visiblemente hasta que un dueño encienda la función. Cualquier paso que rompa esto está mal implementado.
- **`app/routers/sales.py::create_sale` es el motor ATS-crítico** (regla de oro #8). En este plan se le agrega **una sola asignación de columna**, envuelta en un servicio que nunca lanza. No se toca la validación de pagos, ni los totales, ni el folio, ni el stock, ni la caja.
- **Sin Alembic.** Columnas nuevas = `ALTER TABLE … ADD COLUMN` idempotente en la lista `migrations` de `scripts/railway_init.py` (tuplas `(tabla, columna, ddl)`), **más** el atributo en el modelo para que `create_all` la cree en bases nuevas.
- **La tabla `exchange_rates` es global a propósito** (dato público de Banxico, uno por día). No lleva `organization_id` ni `TenantMixin`; la regla de oro #5 no aplica porque no hay dato de negocio de ningún inquilino ahí.
- **Nunca se toca la red en pruebas.** `app/services/banxico.py::fetch_fix` y `httpx.get` se parchean con `monkeypatch`. Ni una sola prueba depende de que Banxico responda.
- **El job de fondo va gateado dos veces:** apagado en SQLite (igual que el worker del outbox, `app/core/outbox.py:154`) y apagado si no hay `BANXICO_TOKEN`.
- **Suite verde antes de cada commit:** `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py` (hoy **652 pasan, 2 se saltan, 3 xfail**). Frontend, desde `frontend/`: `npx vitest run` (**261 pasan**), `npx tsc --noEmit` y `npm run build`.
- **Las pruebas de frontend son solo de funciones puras** (`vitest` con `environment: 'node'`, patrón `src/**/*.test.ts`). Toda lógica nueva que valga la pena probar se extrae a un `.ts` sin React.
- **`tests/test_cash_complete.py` hace `sys.exit(1)` al importar**: siempre correr la suite con `--ignore=tests/test_cash_complete.py`.
- **Estilo:** comentarios en español, Pydantic v2, type hints en firmas nuevas, `HTTPException` con `detail` accionable. Sin `print()` de depuración.
- Mensajes de commit terminan con las líneas `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb`.

## Mapa de archivos

| Archivo | Responsabilidad en este plan |
|---|---|
| `app/models/exchange_rate.py` (nuevo) | tabla global `exchange_rates` (FIX diario) |
| `app/models/__init__.py` | registrar `ExchangeRate` para `create_all` |
| `app/modules/tenants/models.py` | columnas `usd_rate_mode` / `usd_rate_manual` / `usd_rate_margin` en `Organization` |
| `app/modules/tenants/schemas.py` | `OrganizationUpdate`/`OrganizationRead` con los tres campos; `ExchangeRateRead` |
| `app/services/exchange_rate.py` (nuevo) | fuente única: `resolve_usd_rate`, `to_usd`, `validar_config_usd`, helpers de DB |
| `app/services/banxico.py` (nuevo) | cliente del SIE (serie `SF43718`), `fetch_fix` |
| `app/core/exchange_rate_job.py` (nuevo) | job diario gateado (SQLite + token) |
| `app/main.py` | arrancar/parar el job en startup/shutdown |
| `app/modules/tenants/router.py` | `GET /exchange-rate`, `POST /exchange-rate/refresh`, validación en `PUT /` |
| `app/models/sales.py` | `sales_documents.usd_rate` |
| `app/routers/sales.py` | snapshot del tipo de cambio en `create_sale` (una asignación) |
| `app/pos_printer.py` | `_usd_line` en el ticket y en el reemitido |
| `scripts/railway_init.py` | cuatro `ALTER TABLE` idempotentes |
| `tests/test_pos_printer.py` | `_make_sale` declara `usd_rate` (MagicMock truthy) |
| `frontend/src/utils/usd.ts` (nuevo) | `usdEquivalent`, `formatUsd`, `usdSummary` (puras) |
| `frontend/src/store/exchangeRateStore.ts` (nuevo) | caché del tipo de cambio para el POS |
| `frontend/src/api/organization.ts` | tipos y clientes de los endpoints nuevos |
| `frontend/src/pages/pos/POS.tsx` | carga del tipo de cambio al entrar y refresco cada 30 min |
| `frontend/src/components/pos/CartPanel.tsx` | línea `≈ USD … · T.C. …` bajo el total |
| `frontend/src/components/pos/ProductSearch.tsx` | precio USD bajo el precio base de cada tarjeta |
| `frontend/src/pages/core/Organization.tsx` | sección "Tipo de cambio USD" |

---

## Fase A — Equivalente informativo

### Task 1: Tabla `exchange_rates`, columnas de `organization` y servicio puro

**Files:**
- Create: `app/models/exchange_rate.py`
- Modify: `app/models/__init__.py` (final del archivo, después del bloque `# 14. Gastro modules`)
- Modify: `app/modules/tenants/models.py` (clase `Organization`, después de `price_includes_tax` — línea 188)
- Modify: `app/modules/tenants/schemas.py` (`OrganizationUpdate` línea 41-69, `OrganizationRead` línea 72-78)
- Create: `app/services/exchange_rate.py`
- Modify: `scripts/railway_init.py` (lista `migrations`, después de la entrada `("organization", "price_includes_tax", …)` de la línea 101)
- Test: `tests/test_exchange_rate_service.py`, `tests/test_exchange_rate_model.py`

**Interfaces:**
- Produces: `ExchangeRate` (tabla `exchange_rates`: `id`, `currency`, `rate_date`, `rate`, `source`, `fetched_at`, único por `(currency, rate_date)`).
- Produces: `Organization.usd_rate_mode` (`'off'|'auto'|'manual'`, default `'off'`), `.usd_rate_manual`, `.usd_rate_margin`.
- Produces (puras): `resolve_usd_rate(org, latest_fix) -> ResolvedRate | None`, `to_usd(amount_mxn, rate) -> Decimal`, `validar_config_usd(mode, manual, margin) -> None`, constantes `MODO_OFF/MODO_AUTO/MODO_MANUAL`, `FUENTE_BANXICO/FUENTE_MANUAL`, `MONEDA_USD`.
- Produces (con DB): `ultimo_fix(db, currency='USD')`, `tipo_vigente(db, org)`, `guardar_fix(db, dia, tipo, source, currency)`, `snapshot_usd_rate(db, org_id)`.
- Las tareas 2, 3 y 4 consumen exactamente estos nombres.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_exchange_rate_service.py
"""Servicio puro del tipo de cambio USD: resolucion por modo y conversion.

Sin base de datos: `resolve_usd_rate` recibe la organizacion y la fila del FIX
duck-typed, asi que un SimpleNamespace basta (mismo patron que
tests/test_ticket_layout.py)."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.exchange_rate import (
    MODO_AUTO,
    MODO_MANUAL,
    MODO_OFF,
    ResolvedRate,
    resolve_usd_rate,
    to_usd,
    validar_config_usd,
)


def _org(mode=MODO_OFF, manual=None, margin=0):
    return SimpleNamespace(usd_rate_mode=mode, usd_rate_manual=manual, usd_rate_margin=margin)


def _fix(rate="18.2000", dia=date(2026, 9, 17)):
    return SimpleNamespace(rate=Decimal(rate), rate_date=dia, currency="USD", source="banxico")


class TestResolveUsdRate:
    def test_modo_off_no_devuelve_nada(self):
        assert resolve_usd_rate(_org(), _fix()) is None

    def test_organizacion_sin_las_columnas_es_off(self):
        # Organizacion legada leida antes del ALTER: no debe reventar.
        assert resolve_usd_rate(SimpleNamespace(), _fix()) is None

    def test_auto_suma_el_margen_al_fix(self):
        r = resolve_usd_rate(_org(MODO_AUTO, margin=Decimal("0.30")), _fix("18.2000"))
        assert r == ResolvedRate(
            rate=Decimal("18.5000"), source="banxico",
            fix_rate=Decimal("18.2000"), fix_date=date(2026, 9, 17),
        )

    def test_auto_sin_fix_no_devuelve_nada(self):
        assert resolve_usd_rate(_org(MODO_AUTO, margin=Decimal("0.30")), None) is None

    def test_auto_con_margen_que_anula_el_tipo_no_devuelve_nada(self):
        assert resolve_usd_rate(_org(MODO_AUTO, margin=Decimal("-20")), _fix("18.2000")) is None

    def test_manual_manda_sobre_el_fix(self):
        r = resolve_usd_rate(
            _org(MODO_MANUAL, manual=Decimal("19.5000"), margin=Decimal("0.30")), _fix()
        )
        assert r.rate == Decimal("19.5000")
        assert r.source == "manual"
        # El FIX viaja igual, informativo, para que el panel lo muestre.
        assert r.fix_rate == Decimal("18.2000")

    def test_manual_sin_tipo_capturado_no_devuelve_nada(self):
        assert resolve_usd_rate(_org(MODO_MANUAL, manual=None), _fix()) is None
        assert resolve_usd_rate(_org(MODO_MANUAL, manual=Decimal("0")), _fix()) is None

    def test_el_float_de_sqlite_no_rompe_la_precision(self):
        r = resolve_usd_rate(_org(MODO_AUTO, margin=0.3), _fix("18.2"))
        assert r.rate == Decimal("18.5000")

    def test_el_modo_no_distingue_mayusculas(self):
        assert resolve_usd_rate(_org(" AUTO "), _fix()).rate == Decimal("18.2000")


class TestToUsd:
    @pytest.mark.parametrize("mxn,tasa,esperado", [
        ("185.00", "18.5000", "10.00"),
        ("100.00", "18.5000", "5.41"),    # 5.4054... -> HALF_UP
        ("0", "18.5000", "0.00"),
        ("18.50", "18.5", "1.00"),
    ])
    def test_convierte_y_redondea_a_centavos(self, mxn, tasa, esperado):
        assert to_usd(Decimal(mxn), Decimal(tasa)) == Decimal(esperado)

    def test_tasa_invalida_devuelve_cero(self):
        assert to_usd(Decimal("100"), Decimal("0")) == Decimal("0.00")
        assert to_usd(Decimal("100"), None) == Decimal("0.00")

    def test_acepta_float_y_none(self):
        assert to_usd(None, Decimal("18.5")) == Decimal("0.00")
        assert to_usd(185.0, 18.5) == Decimal("10.00")


class TestValidarConfig:
    def test_modo_desconocido(self):
        with pytest.raises(ValueError):
            validar_config_usd("dolares", None, 0)

    def test_manual_sin_tipo(self):
        with pytest.raises(ValueError):
            validar_config_usd(MODO_MANUAL, None, 0)
        with pytest.raises(ValueError):
            validar_config_usd(MODO_MANUAL, Decimal("0"), 0)

    def test_margen_absurdo(self):
        with pytest.raises(ValueError):
            validar_config_usd(MODO_AUTO, None, Decimal("80"))

    def test_configuraciones_validas(self):
        validar_config_usd(MODO_OFF, None, 0)
        validar_config_usd(MODO_AUTO, None, Decimal("0.30"))
        validar_config_usd(MODO_AUTO, None, Decimal("-0.10"))
        validar_config_usd(MODO_MANUAL, Decimal("19.5"), 0)
```

```python
# tests/test_exchange_rate_model.py
"""`exchange_rates` es global (sin organization_id) y admite una sola fila por
moneda y dia; la politica por inquilino vive en columnas de `organization`."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.exchange_rate import ExchangeRate
from app.models.organization import Organization


def test_la_tabla_no_tiene_organization_id():
    # Es un dato publico compartido por todos los inquilinos. Si alguien le
    # cuelga organization_id, la tabla deja de ser lo que el diseño dice y
    # habria que filtrar por org en cada lectura.
    assert "organization_id" not in ExchangeRate.__table__.columns


def test_guarda_el_fix_del_dia(db):
    db.add(ExchangeRate(currency="USD", rate_date=date(2026, 9, 17),
                        rate=Decimal("18.2345"), source="banxico"))
    db.flush()
    fila = db.query(ExchangeRate).filter(ExchangeRate.rate_date == date(2026, 9, 17)).one()
    assert fila.rate == Decimal("18.2345")
    assert fila.currency == "USD"
    assert fila.source == "banxico"


def test_un_solo_renglon_por_moneda_y_dia(db):
    db.add(ExchangeRate(currency="USD", rate_date=date(2026, 9, 17), rate=Decimal("18.20")))
    db.flush()
    db.add(ExchangeRate(currency="USD", rate_date=date(2026, 9, 17), rate=Decimal("18.90")))
    with pytest.raises(IntegrityError):
        db.flush()


def test_la_organizacion_arranca_apagada(db):
    # Neutralidad: ninguna de las organizaciones vivas ve nada nuevo.
    o = Organization(name="Sin dolares", status="ACTIVE")
    db.add(o)
    db.flush()
    db.refresh(o)
    assert o.usd_rate_mode == "off"
    assert o.usd_rate_manual is None
    assert Decimal(str(o.usd_rate_margin)) == Decimal("0")
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_exchange_rate_service.py tests/test_exchange_rate_model.py`
Expected: `ModuleNotFoundError: No module named 'app.services.exchange_rate'` y `No module named 'app.models.exchange_rate'` (error de colección en los dos archivos).

- [ ] **Step 3: Implementar**

`app/models/exchange_rate.py` (nuevo):

```python
"""Tipo de cambio diario (FIX de Banxico, serie SF43718).

Tabla GLOBAL a proposito: el FIX es un dato publico, uno por dia, compartido
por todos los inquilinos — NO lleva `organization_id` ni `TenantMixin`, igual
que `modules`. La politica por organizacion (modo, margen, tipo manual) vive en
columnas de `organization`; aqui solo esta el numero publicado.

La llena `app/core/exchange_rate_job.py` (job diario) y el endpoint de refresco
manual. La lee `app/services/exchange_rate.py::ultimo_fix`.
"""
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.core.database import Base


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (
        # Una fila por moneda y dia. El job es idempotente y puede correr N
        # veces (N replicas del backend, refresco manual del dueño); esta
        # restriccion es la red que lo garantiza en la base.
        UniqueConstraint("currency", "rate_date", name="uq_exchange_rate_day"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, index=True)
    currency = Column(String(3), nullable=False, default="USD", index=True)
    # Dia AL QUE CORRESPONDE el tipo segun Banxico, no el dia en que se bajo:
    # en fin de semana y feriados el dato mas reciente es el del ultimo habil.
    rate_date = Column(Date, nullable=False, index=True)
    rate = Column(Numeric(10, 4), nullable=False)  # pesos por unidad de `currency`
    source = Column(String(16), nullable=False, default="banxico")  # banxico | manual
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
```

`app/models/__init__.py`, al final del archivo (después del bloque `# 14. Gastro modules`):

```python
# 15. Tipo de cambio USD (tabla GLOBAL, sin organization_id — ver el docstring
#     de app/models/exchange_rate.py). Registrada aqui para `create_all`.
from .exchange_rate import ExchangeRate  # noqa: F401
```

`app/modules/tenants/models.py`, en `Organization`, justo después de `price_includes_tax` (línea 188):

```python
    # Equivalente en dolares (2026-09-17). `usd_rate_mode`:
    #   'off'    -> apagado: el POS y el ticket no muestran nada (DEFAULT, y es
    #               lo que queda para todas las organizaciones ya existentes)
    #   'auto'   -> FIX de Banxico del dia + `usd_rate_margin`
    #   'manual' -> `usd_rate_manual`, capturado por el administrador
    # VARCHAR con constantes en app/services/exchange_rate.py, NO enum de DB
    # (CLAUDE.md §5: un enum nuevo obliga a ALTER TYPE por cada modo).
    usd_rate_mode = Column(String(10), default="off", server_default="off", nullable=False)
    usd_rate_manual = Column(Numeric(10, 4), nullable=True)
    # Pesos que se suman al FIX en modo 'auto' (el spread de ventanilla del
    # negocio). Puede ser negativo.
    usd_rate_margin = Column(Numeric(10, 4), default=0, server_default="0", nullable=False)
```

`app/modules/tenants/schemas.py` — agregar los imports al inicio del archivo:

```python
# app/schemas/organization.py
from datetime import date
from decimal import Decimal

from pydantic import BaseModel
from typing import Optional
from app.models.organization import IndustryType
```

en `OrganizationUpdate`, después de `is_active` (línea 67):

```python
    # Equivalente en dolares (2026-09-17). Los tres caen FUERA de la whitelist
    # de no-admins del router (linea 67 de router.py), asi que solo
    # ADMINISTRADOR/DUEÑO pueden cambiarlos: no hace falta guardia nueva.
    usd_rate_mode: Optional[str] = None
    usd_rate_manual: Optional[Decimal] = None
    usd_rate_margin: Optional[Decimal] = None
```

y `OrganizationRead` completo:

```python
class OrganizationRead(OrganizationBase):
    id: int
    is_active: Optional[bool] = True
    industry_type: Optional[str] = None

    # Equivalente en dolares. Se exponen en la lectura para que el panel de
    # Empresa arme el formulario sin un GET extra.
    usd_rate_mode: str = "off"
    usd_rate_manual: Optional[Decimal] = None
    usd_rate_margin: Decimal = Decimal("0")

    class Config:
        from_attributes = True


class ExchangeRateRead(BaseModel):
    """Lo que el POS necesita para pintar el equivalente en dolares.

    `rate is None` significa "no mostrar nada": pasa en modo 'off' y tambien en
    modo 'auto' cuando todavia no hay FIX descargado. El POS NO debe distinguir
    esos dos casos.
    """
    mode: str
    rate: Optional[Decimal] = None        # tipo efectivo, ya con el margen
    source: Optional[str] = None          # 'banxico' | 'manual'
    fix_rate: Optional[Decimal] = None    # FIX crudo del dia (informativo)
    fix_date: Optional[date] = None
    margin: Decimal = Decimal("0")
    manual_rate: Optional[Decimal] = None
```

`app/services/exchange_rate.py` (nuevo):

```python
"""Tipo de cambio USD: resolucion por organizacion y conversion.

Fuente UNICA del equivalente en dolares, igual que `app/services/tax.py` lo es
del IVA. La consumen el endpoint de configuracion, el snapshot de la venta
(`app/routers/sales.py::create_sale`) y el ticket (`app/pos_printer.py`). Si
cada uno redondeara por su cuenta, el ticket y la pantalla discreparian en
centavos y el cliente lo veria.

Las funciones de la primera mitad son PURAS (sin DB ni FastAPI) y se prueban
solas en tests/test_exchange_rate_service.py. La segunda mitad son ayudantes
que SI tocan la base; estan marcados.

Redondeo: HALF_UP, el mismo redondeo fiscal mexicano de tax.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

logger = logging.getLogger(__name__)

CENTAVOS = Decimal("0.01")
DIEZMILESIMAS = Decimal("0.0001")  # el FIX se publica con 4 decimales

# Modos de `organization.usd_rate_mode`.
MODO_OFF = "off"
MODO_AUTO = "auto"
MODO_MANUAL = "manual"
MODOS_VALIDOS = (MODO_OFF, MODO_AUTO, MODO_MANUAL)

FUENTE_BANXICO = "banxico"
FUENTE_MANUAL = "manual"

MONEDA_USD = "USD"

# Tope del ajuste manual sobre el FIX. No es una regla fiscal, es un guardaraíl
# contra el dedo gordo: 80 en vez de 0.80 convertiria un total de $1,000 en
# USD 10 en lugar de USD 53.
MARGEN_MAXIMO = Decimal("50")


@dataclass(frozen=True)
class ResolvedRate:
    """Tipo de cambio efectivo y de donde salio."""
    rate: Decimal                        # pesos por dolar, ya con el margen
    source: str                          # 'banxico' | 'manual'
    fix_rate: Optional[Decimal] = None   # FIX crudo del dia (informativo)
    fix_date: Optional[date] = None      # dia del FIX segun Banxico


def _dec(valor) -> Optional[Decimal]:
    """Decimal tolerante con None, float y str (columnas nullable y SQLite)."""
    if valor is None:
        return None
    try:
        return Decimal(str(valor))
    except Exception:  # noqa: BLE001 — basura en la columna != error de cobro
        return None


def _modo(org) -> str:
    """Modo normalizado. Una organizacion sin la columna todavia es 'off'."""
    return (getattr(org, "usd_rate_mode", None) or MODO_OFF).strip().lower()


def resolve_usd_rate(org, latest_fix) -> Optional[ResolvedRate]:
    """Tipo de cambio efectivo de la organizacion, o None si no hay que mostrar nada.

    `org` solo necesita `usd_rate_mode`, `usd_rate_manual` y `usd_rate_margin`;
    `latest_fix` solo necesita `rate` y `rate_date` (o None). Ambos van
    duck-typed para que la funcion sea probable sin base de datos.

    Devuelve None —y NO lanza— en todos los casos en los que no hay un tipo
    utilizable: modo apagado, modo manual sin tipo capturado, modo automatico
    sin FIX, o un resultado que quedaria en cero o negativo.
    """
    modo = _modo(org)

    if modo == MODO_MANUAL:
        manual = _dec(getattr(org, "usd_rate_manual", None))
        if manual is None or manual <= 0:
            return None
        fix = _dec(getattr(latest_fix, "rate", None)) if latest_fix is not None else None
        return ResolvedRate(
            rate=manual.quantize(DIEZMILESIMAS, rounding=ROUND_HALF_UP),
            source=FUENTE_MANUAL,
            fix_rate=fix,
            fix_date=getattr(latest_fix, "rate_date", None) if latest_fix is not None else None,
        )

    if modo == MODO_AUTO:
        if latest_fix is None:
            return None
        fix = _dec(getattr(latest_fix, "rate", None))
        if fix is None or fix <= 0:
            return None
        margen = _dec(getattr(org, "usd_rate_margin", None)) or Decimal("0")
        efectivo = (fix + margen).quantize(DIEZMILESIMAS, rounding=ROUND_HALF_UP)
        if efectivo <= 0:
            return None
        return ResolvedRate(
            rate=efectivo,
            source=FUENTE_BANXICO,
            fix_rate=fix,
            fix_date=getattr(latest_fix, "rate_date", None),
        )

    return None


def to_usd(amount_mxn, rate) -> Decimal:
    """Pesos -> dolares, redondeado a centavos HALF_UP.

    Tipo de cambio ausente, cero o negativo devuelve `Decimal("0.00")` en vez de
    lanzar: quien llama esta pintando un numero informativo, no cobrando.
    """
    monto = _dec(amount_mxn) or Decimal("0")
    tasa = _dec(rate)
    if tasa is None or tasa <= 0:
        return Decimal("0.00")
    return (monto / tasa).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def validar_config_usd(mode, manual, margin) -> None:
    """Valida la configuracion RESULTANTE de una organizacion. Lanza ValueError.

    El caller (el PUT de organizacion) la convierte en 422 con el mensaje tal
    cual, en español y accionable.
    """
    m = (mode or MODO_OFF).strip().lower()
    if m not in MODOS_VALIDOS:
        raise ValueError(
            f"Modo de tipo de cambio inválido: '{mode}'. Usa 'off', 'auto' o 'manual'."
        )

    manual_dec = _dec(manual)
    if m == MODO_MANUAL and (manual_dec is None or manual_dec <= 0):
        raise ValueError(
            "En modo manual hay que capturar un tipo de cambio mayor que cero."
        )

    margen_dec = _dec(margin) or Decimal("0")
    if margen_dec.copy_abs() > MARGEN_MAXIMO:
        raise ValueError(
            f"El ajuste sobre el FIX no puede pasar de {MARGEN_MAXIMO} pesos por dólar."
        )


# ── Ayudantes CON base de datos (no puros) ───────────────────────────────────

def ultimo_fix(db, currency: str = MONEDA_USD):
    """Fila mas reciente de `exchange_rates` para la moneda. None si no hay ninguna."""
    from app.models.exchange_rate import ExchangeRate

    return (
        db.query(ExchangeRate)
        .filter(ExchangeRate.currency == currency)
        .order_by(ExchangeRate.rate_date.desc())
        .first()
    )


def tipo_vigente(db, org) -> Optional[ResolvedRate]:
    """`resolve_usd_rate` resolviendo el FIX contra la base."""
    if _modo(org) == MODO_OFF:
        return None  # apagado: ni siquiera se consulta la tabla
    return resolve_usd_rate(org, ultimo_fix(db))


def guardar_fix(db, dia: date, tipo: Decimal,
                source: str = FUENTE_BANXICO, currency: str = MONEDA_USD):
    """Inserta o actualiza la fila del dia. Idempotente. NO hace commit.

    El job puede correr varias veces (N replicas del backend, refresco manual
    del dueño): la clave (currency, rate_date) es una sola fila, siempre.
    """
    from app.models.exchange_rate import ExchangeRate

    fila = (
        db.query(ExchangeRate)
        .filter(ExchangeRate.currency == currency, ExchangeRate.rate_date == dia)
        .first()
    )
    if fila is None:
        fila = ExchangeRate(currency=currency, rate_date=dia, rate=tipo, source=source)
        db.add(fila)
    else:
        fila.rate = tipo
        fila.source = source
        fila.fetched_at = datetime.now(timezone.utc)
    db.flush()
    return fila


def snapshot_usd_rate(db, org_id: int) -> Optional[Decimal]:
    """Tipo efectivo para congelar en una venta. NUNCA lanza.

    La llama `app/routers/sales.py::create_sale`, el motor ATS-critico: si
    Banxico, la tabla o esta misma funcion fallan, la venta TIENE que cobrarse
    igual. Por eso cualquier excepcion se traga con un warning y devuelve None
    (= la venta queda sin equivalente en dolares, que es exactamente el estado
    de todas las ventas anteriores a esta funcion).
    """
    try:
        from app.models.organization import Organization

        org = db.query(Organization).filter(Organization.id == org_id).first()
        if org is None:
            return None
        resuelto = tipo_vigente(db, org)
        return resuelto.rate if resuelto else None
    except Exception:  # noqa: BLE001 — jamas impedir un cobro
        logger.warning("USD_SNAPSHOT_FAILED org=%s", org_id, exc_info=True)
        return None
```

`scripts/railway_init.py`, en la lista `migrations`, después de la entrada `("organization", "price_includes_tax", …)` (línea 101):

```python
        # Equivalente en dolares 2026-09-17. Modo 'off' por DEFAULT a proposito:
        # ninguna organizacion viva ve nada hasta que su dueño lo encienda.
        # La tabla `exchange_rates` la crea `create_all` (modelo registrado en
        # app/models/__init__.py); aqui solo van las columnas de tablas ya vivas.
        ("organization", "usd_rate_mode",   "ALTER TABLE organization ADD COLUMN usd_rate_mode VARCHAR(10) NOT NULL DEFAULT 'off';"),
        ("organization", "usd_rate_manual", "ALTER TABLE organization ADD COLUMN usd_rate_manual NUMERIC(10,4);"),
        ("organization", "usd_rate_margin", "ALTER TABLE organization ADD COLUMN usd_rate_margin NUMERIC(10,4) NOT NULL DEFAULT 0;"),
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `python3 -m pytest -q -p no:warnings tests/test_exchange_rate_service.py tests/test_exchange_rate_model.py`
Expected: todas PASSED (23 pruebas: 19 del servicio contando los 4 casos parametrizados, 4 del modelo).

Luego la suite completa:
Run: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py`
Expected: `652 passed, 2 skipped, 3 xfailed` — el conteo de `failed` **no sube**.

- [ ] **Step 5: Commit**

```bash
git add app/models/exchange_rate.py app/models/__init__.py app/modules/tenants/models.py app/modules/tenants/schemas.py app/services/exchange_rate.py scripts/railway_init.py tests/test_exchange_rate_service.py tests/test_exchange_rate_model.py
git commit -m "feat(usd): tabla exchange_rates, configuracion por organizacion y servicio de tipo de cambio

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb"
```

---

### Task 2: Cliente de Banxico, job diario y endpoints

**Files:**
- Create: `app/services/banxico.py`
- Create: `app/core/exchange_rate_job.py`
- Modify: `app/main.py:78-97` (`startup_event` y `shutdown_event`)
- Modify: `app/modules/tenants/router.py` (imports línea 16; cuerpo de `update_organization` líneas 61-84; endpoints nuevos después de la línea 84)
- Test: `tests/test_banxico_client.py`, `tests/test_exchange_rate_job.py`, `tests/test_exchange_rate_endpoints.py`

**Interfaces:**
- Consumes: `guardar_fix`, `ultimo_fix`, `resolve_usd_rate`, `validar_config_usd`, `MODO_OFF`, `MONEDA_USD` (Task 1); `ExchangeRateRead` (Task 1).
- Produces: `fetch_fix(token) -> (date, Decimal)` y `token_configurado() -> str | None` en `app/services/banxico.py`; `BanxicoError`.
- Produces: `actualizar_fix_ahora(db, token) -> (bool, str)`, `hay_fix_de_hoy(db) -> bool`, `segundos_hasta_la_proxima_corrida(ahora) -> float`, `start_exchange_rate_job()`, `stop_exchange_rate_job()`.
- Produces: `GET /api/organization/exchange-rate` → `ExchangeRateRead`; `POST /api/organization/exchange-rate/refresh` → `{ok, rate_date, rate, source}`; `PUT /api/organization/` valida la configuración resultante. La Task 4 consume el `GET` y el `POST`.

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_banxico_client.py
"""Cliente del SIE de Banxico. NUNCA sale a la red: `httpx.get` va parcheado."""
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.services import banxico
from app.services.banxico import BanxicoError, fetch_fix, token_configurado


class _Respuesta:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _payload(fecha="17/09/2026", dato="18.2345"):
    return {"bmx": {"series": [{
        "idSerie": "SF43718",
        "titulo": "Tipo de cambio pesos por dólar E.U.A.",
        "datos": [{"fecha": fecha, "dato": dato}],
    }]}}


def _parchear(monkeypatch, respuesta):
    """Sustituye httpx.get y devuelve un dict con lo que se llamo."""
    llamada = {}

    def _fake_get(url, params=None, headers=None, timeout=None):
        llamada["url"] = url
        llamada["params"] = params
        llamada["timeout"] = timeout
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    monkeypatch.setattr(banxico.httpx, "get", _fake_get)
    return llamada


def test_devuelve_fecha_y_tipo(monkeypatch):
    llamada = _parchear(monkeypatch, _Respuesta(_payload()))
    dia, tipo = fetch_fix("tok")
    assert dia == date(2026, 9, 17)
    assert tipo == Decimal("18.2345")
    assert "SF43718" in llamada["url"]
    assert llamada["params"] == {"token": "tok"}
    assert llamada["timeout"] == 10.0


def test_dia_inhabil_devuelve_ne_y_es_error(monkeypatch):
    # Banxico responde 'N/E' en sabados, domingos y feriados.
    _parchear(monkeypatch, _Respuesta(_payload(dato="N/E")))
    with pytest.raises(BanxicoError):
        fetch_fix("tok")


def test_http_distinto_de_200(monkeypatch):
    _parchear(monkeypatch, _Respuesta(_payload(), status_code=401))
    with pytest.raises(BanxicoError):
        fetch_fix("tok")


def test_json_con_otra_forma(monkeypatch):
    _parchear(monkeypatch, _Respuesta({"bmx": {"series": []}}))
    with pytest.raises(BanxicoError):
        fetch_fix("tok")


def test_fecha_con_otro_formato(monkeypatch):
    _parchear(monkeypatch, _Respuesta(_payload(fecha="2026-09-17")))
    with pytest.raises(BanxicoError):
        fetch_fix("tok")


def test_error_de_red(monkeypatch):
    _parchear(monkeypatch, httpx.ConnectError("sin red"))
    with pytest.raises(BanxicoError):
        fetch_fix("tok")


def test_sin_token_no_toca_la_red(monkeypatch):
    def _explota(*a, **k):
        raise AssertionError("no debe llamar a Banxico sin token")

    monkeypatch.setattr(banxico.httpx, "get", _explota)
    with pytest.raises(BanxicoError):
        fetch_fix("")


def test_token_configurado_lee_el_entorno(monkeypatch):
    monkeypatch.delenv("BANXICO_TOKEN", raising=False)
    assert token_configurado() is None
    monkeypatch.setenv("BANXICO_TOKEN", "   ")
    assert token_configurado() is None
    monkeypatch.setenv("BANXICO_TOKEN", "abc123")
    assert token_configurado() == "abc123"
```

```python
# tests/test_exchange_rate_job.py
"""Job diario del FIX: idempotencia, horario y doble apagado. HTTP parcheado."""
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.core import exchange_rate_job as job
from app.models.exchange_rate import ExchangeRate
from app.services.banxico import BanxicoError

TZ_MX = ZoneInfo("America/Mexico_City")


def test_guarda_el_fix_una_sola_vez_por_dia(db, monkeypatch):
    monkeypatch.setattr(job, "fetch_fix", lambda token: (date(2026, 9, 17), Decimal("18.2345")))
    assert job.actualizar_fix_ahora(db, "tok")[0] is True
    monkeypatch.setattr(job, "fetch_fix", lambda token: (date(2026, 9, 17), Decimal("18.9999")))
    assert job.actualizar_fix_ahora(db, "tok")[0] is True

    filas = db.query(ExchangeRate).filter(ExchangeRate.rate_date == date(2026, 9, 17)).all()
    assert len(filas) == 1
    assert filas[0].rate == Decimal("18.9999")  # la segunda corrida actualiza


def test_banxico_caido_no_lanza_y_no_escribe(db, monkeypatch):
    def _revienta(token):
        raise BanxicoError("SIE caido")

    monkeypatch.setattr(job, "fetch_fix", _revienta)
    ok, mensaje = job.actualizar_fix_ahora(db, "tok")
    assert ok is False
    assert "SIE caido" in mensaje
    assert db.query(ExchangeRate).count() == 0


def test_hay_fix_de_hoy(db):
    assert job.hay_fix_de_hoy(db) is False
    db.add(ExchangeRate(currency="USD", rate_date=datetime.now(TZ_MX).date(),
                        rate=Decimal("18.20")))
    db.flush()
    assert job.hay_fix_de_hoy(db) is True


class TestHorario:
    def test_antes_de_las_1230_espera_hoy(self):
        assert job.segundos_hasta_la_proxima_corrida(
            datetime(2026, 9, 17, 9, 0, tzinfo=TZ_MX)
        ) == 3.5 * 3600

    def test_despues_de_las_1230_espera_mañana(self):
        assert job.segundos_hasta_la_proxima_corrida(
            datetime(2026, 9, 17, 13, 0, tzinfo=TZ_MX)
        ) == 23.5 * 3600

    def test_nunca_duerme_cero(self):
        # Justo en la hora: el siguiente tick es el de mañana, no un bucle
        # apretado quemando CPU.
        assert job.segundos_hasta_la_proxima_corrida(
            datetime(2026, 9, 17, 12, 30, tzinfo=TZ_MX)
        ) == 24 * 3600


def test_apagado_en_sqlite(monkeypatch):
    # La suite corre en SQLite: arrancar el job aqui dejaria un task de fondo
    # tocando la base entre pruebas (mismo motivo que el worker del outbox).
    monkeypatch.setenv("BANXICO_TOKEN", "abc123")
    assert job.start_exchange_rate_job() is None


def test_apagado_sin_token(monkeypatch):
    monkeypatch.setattr(job, "_IS_SQLITE", False)
    monkeypatch.delenv("BANXICO_TOKEN", raising=False)
    assert job.start_exchange_rate_job() is None
```

```python
# tests/test_exchange_rate_endpoints.py
"""Endpoints del tipo de cambio: lectura para cualquiera de la org, escritura
solo ADMINISTRADOR/DUEÑO, refresco manual con Banxico parcheado."""
from datetime import date
from decimal import Decimal

import pytest

from app.models.exchange_rate import ExchangeRate


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


@pytest.fixture()
def fix_de_hoy(db):
    db.add(ExchangeRate(currency="USD", rate_date=date(2026, 9, 17),
                        rate=Decimal("18.2000"), source="banxico"))
    db.flush()


class TestLectura:
    def test_organizacion_apagada_no_devuelve_tipo(self, client, org, fix_de_hoy, auth_cajero_a):
        r = client.get("/api/organization/exchange-rate", headers=_h(auth_cajero_a, org))
        assert r.status_code == 200, r.text
        assert r.json()["mode"] == "off"
        assert r.json()["rate"] is None

    def test_modo_auto_suma_el_margen(self, client, db, org, fix_de_hoy, auth_cajero_a):
        org.usd_rate_mode = "auto"
        org.usd_rate_margin = Decimal("0.30")
        db.flush()
        data = client.get("/api/organization/exchange-rate", headers=_h(auth_cajero_a, org)).json()
        assert Decimal(str(data["rate"])) == Decimal("18.5000")
        assert data["source"] == "banxico"
        assert Decimal(str(data["fix_rate"])) == Decimal("18.2000")
        assert data["fix_date"] == "2026-09-17"

    def test_modo_manual(self, client, db, org, fix_de_hoy, auth_cajero_a):
        org.usd_rate_mode = "manual"
        org.usd_rate_manual = Decimal("19.5000")
        db.flush()
        data = client.get("/api/organization/exchange-rate", headers=_h(auth_cajero_a, org)).json()
        assert Decimal(str(data["rate"])) == Decimal("19.5000")
        assert data["source"] == "manual"
        assert Decimal(str(data["manual_rate"])) == Decimal("19.5000")

    def test_auto_sin_fix_no_revienta(self, client, db, org, auth_cajero_a):
        org.usd_rate_mode = "auto"
        db.flush()
        r = client.get("/api/organization/exchange-rate", headers=_h(auth_cajero_a, org))
        assert r.status_code == 200, r.text
        assert r.json()["rate"] is None


class TestEscritura:
    def test_admin_configura_modo_auto(self, client, db, org, auth_admin):
        r = client.put("/api/organization/",
                       json={"usd_rate_mode": "auto", "usd_rate_margin": "0.30"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        db.refresh(org)
        assert org.usd_rate_mode == "auto"
        assert Decimal(str(org.usd_rate_margin)) == Decimal("0.30")

    def test_el_modo_se_guarda_en_minusculas(self, client, db, org, auth_admin):
        r = client.put("/api/organization/", json={"usd_rate_mode": "AUTO"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        db.refresh(org)
        assert org.usd_rate_mode == "auto"

    def test_manual_sin_tipo_es_422(self, client, org, auth_admin):
        r = client.put("/api/organization/", json={"usd_rate_mode": "manual"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 422, r.text

    def test_modo_desconocido_es_422(self, client, org, auth_admin):
        r = client.put("/api/organization/", json={"usd_rate_mode": "euros"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 422

    def test_margen_absurdo_es_422(self, client, org, auth_admin):
        r = client.put("/api/organization/",
                       json={"usd_rate_mode": "auto", "usd_rate_margin": "80"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 422

    def test_cajero_no_puede_configurar(self, client, org, auth_cajero_a):
        r = client.put("/api/organization/",
                       json={"usd_rate_mode": "manual", "usd_rate_manual": "19.5"},
                       headers=_h(auth_cajero_a, org))
        assert r.status_code == 403

    def test_guardar_otro_campo_no_toca_el_tipo_de_cambio(self, client, db, org, auth_admin):
        # Neutralidad: el panel manda el objeto completo al guardar la razon
        # social, y eso NO debe disparar la validacion ni cambiar el modo.
        r = client.put("/api/organization/", json={"name": "Otra Razon"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        db.refresh(org)
        assert org.usd_rate_mode == "off"


class TestRefrescoManual:
    def test_sin_token_es_503(self, client, org, auth_admin, monkeypatch):
        monkeypatch.delenv("BANXICO_TOKEN", raising=False)
        r = client.post("/api/organization/exchange-rate/refresh", headers=_h(auth_admin, org))
        assert r.status_code == 503

    def test_admin_refresca_y_guarda(self, client, db, org, auth_admin, monkeypatch):
        monkeypatch.setenv("BANXICO_TOKEN", "abc123")
        from app.core import exchange_rate_job as job
        monkeypatch.setattr(job, "fetch_fix",
                            lambda token: (date(2026, 9, 17), Decimal("18.4321")))
        r = client.post("/api/organization/exchange-rate/refresh", headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        assert r.json()["rate_date"] == "2026-09-17"
        assert db.query(ExchangeRate).filter(
            ExchangeRate.rate_date == date(2026, 9, 17)
        ).count() == 1

    def test_banxico_caido_es_503(self, client, org, auth_admin, monkeypatch):
        monkeypatch.setenv("BANXICO_TOKEN", "abc123")
        from app.core import exchange_rate_job as job
        from app.services.banxico import BanxicoError

        def _revienta(token):
            raise BanxicoError("SIE caido")

        monkeypatch.setattr(job, "fetch_fix", _revienta)
        r = client.post("/api/organization/exchange-rate/refresh", headers=_h(auth_admin, org))
        assert r.status_code == 503

    def test_cajero_no_puede_refrescar(self, client, org, auth_cajero_a, monkeypatch):
        monkeypatch.setenv("BANXICO_TOKEN", "abc123")
        r = client.post("/api/organization/exchange-rate/refresh", headers=_h(auth_cajero_a, org))
        assert r.status_code == 403
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_banxico_client.py tests/test_exchange_rate_job.py tests/test_exchange_rate_endpoints.py`
Expected: error de colección en los dos primeros (`No module named 'app.services.banxico'`, `'app.core.exchange_rate_job'`) y 404 en todas las rutas nuevas del tercero; las pruebas de `PUT` de escritura devuelven 200 sin validar.

- [ ] **Step 3: Implementar**

`app/services/banxico.py` (nuevo):

```python
"""Cliente del SIE de Banxico: tipo de cambio FIX (serie SF43718).

El FIX es el tipo de cambio para solventar obligaciones en dolares que Banxico
publica cada dia habil alrededor del mediodia. Se usa como referencia publica y
auditable; el margen de ventanilla lo pone cada organizacion.

Una sola funcion, sincrona y con timeout corto. La llaman el job diario
(`app/core/exchange_rate_job.py`) y el endpoint de refresco manual. NUNCA se
llama desde el camino de una venta.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

SERIE_FIX = "SF43718"
URL_SIE = (
    f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/{SERIE_FIX}/datos/oportuno"
)
TIMEOUT_SEGUNDOS = 10.0


class BanxicoError(RuntimeError):
    """El SIE no respondio, o respondio algo que no es un tipo de cambio."""


def token_configurado() -> Optional[str]:
    """Token del SIE desde el entorno. None = la funcion queda apagada."""
    valor = (os.getenv("BANXICO_TOKEN") or "").strip()
    return valor or None


def fetch_fix(token: str) -> Tuple[date, Decimal]:
    """Descarga el FIX mas reciente. Devuelve (dia publicado, tipo de cambio).

    Lanza `BanxicoError` ante cualquier problema: sin token, red caida, HTTP
    distinto de 200, JSON con otra forma, o el 'N/E' que el SIE devuelve en
    dias inhabiles. El caller loguea y sigue; nada de esto debe tumbar el
    arranque del backend ni una venta.
    """
    if not token:
        raise BanxicoError("Falta BANXICO_TOKEN")

    try:
        respuesta = httpx.get(
            URL_SIE,
            params={"token": token},
            headers={"Accept": "application/json"},
            timeout=TIMEOUT_SEGUNDOS,
        )
    except httpx.HTTPError as e:
        raise BanxicoError(f"No se pudo consultar Banxico: {e}") from e

    if respuesta.status_code != 200:
        raise BanxicoError(f"Banxico respondió HTTP {respuesta.status_code}")

    try:
        cuerpo = respuesta.json()
        dato = cuerpo["bmx"]["series"][0]["datos"][0]
        crudo_fecha = dato["fecha"]
        crudo_valor = dato["dato"]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise BanxicoError(f"Respuesta de Banxico con formato inesperado: {e}") from e

    try:
        dia = datetime.strptime(str(crudo_fecha), "%d/%m/%Y").date()
    except (ValueError, TypeError) as e:
        raise BanxicoError(f"Fecha inesperada de Banxico: {crudo_fecha!r}") from e

    try:
        # En dias inhabiles el dato es 'N/E'; tambien puede traer separador de miles.
        tipo = Decimal(str(crudo_valor).replace(",", "").strip())
    except (InvalidOperation, AttributeError) as e:
        raise BanxicoError(f"Dato no numérico de Banxico: {crudo_valor!r}") from e

    if tipo <= 0:
        raise BanxicoError(f"Tipo de cambio inválido de Banxico: {tipo}")

    return dia, tipo
```

`app/core/exchange_rate_job.py` (nuevo):

```python
"""Job diario que baja el FIX de Banxico a la tabla `exchange_rates`.

Mismo patron que el worker del outbox (`app/core/outbox.py:151-160`): un
`asyncio.Task` lanzado en el startup de `app/main.py`. Doble apagado:

* **SQLite** — tests y dev local. Igual que el outbox, no queremos un task de
  fondo tocando la base de una suite de pruebas.
* **Sin `BANXICO_TOKEN`** — la funcion es opcional; una instalacion que no la
  use no debe ver un error cada 24 horas en el log.

Ritmo: al arrancar, si falta la fila de hoy la trae; luego duerme hasta las
12:30 de America/Mexico_City. El FIX se publica alrededor del mediodia, asi que
12:30 da margen; mientras tanto se usa la fila del dia anterior, que es lo que
Banxico mismo considera vigente hasta la publicacion.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Tuple
from zoneinfo import ZoneInfo

from app.core.database import SQLALCHEMY_DATABASE_URL, SessionLocal
from app.services.banxico import BanxicoError, fetch_fix, token_configurado
from app.services.exchange_rate import MONEDA_USD, guardar_fix

logger = logging.getLogger(__name__)

_IS_SQLITE = "sqlite" in (SQLALCHEMY_DATABASE_URL or "")
TZ_MX = ZoneInfo("America/Mexico_City")
HORA_CORRIDA = time(12, 30)

_job_task: "asyncio.Task | None" = None


def hay_fix_de_hoy(db) -> bool:
    """¿Ya esta la fila del dia (hora de Mexico) en la tabla?"""
    from app.models.exchange_rate import ExchangeRate

    hoy = datetime.now(TZ_MX).date()
    consulta = db.query(ExchangeRate).filter(
        ExchangeRate.currency == MONEDA_USD,
        ExchangeRate.rate_date == hoy,
    )
    return bool(db.query(consulta.exists()).scalar())


def segundos_hasta_la_proxima_corrida(ahora: datetime) -> float:
    """Segundos hasta las 12:30 de Mexico. Si ya paso (o es exactamente esa
    hora), hasta las de mañana: el bucle nunca duerme cero."""
    local = ahora.astimezone(TZ_MX)
    objetivo = local.replace(
        hour=HORA_CORRIDA.hour, minute=HORA_CORRIDA.minute, second=0, microsecond=0
    )
    if objetivo <= local:
        objetivo += timedelta(days=1)
    return (objetivo - local).total_seconds()


def actualizar_fix_ahora(db, token: str) -> Tuple[bool, str]:
    """Baja el FIX y lo guarda. Devuelve (exito, mensaje). NO lanza."""
    try:
        dia, tipo = fetch_fix(token)
    except BanxicoError as e:
        logger.warning("BANXICO_FETCH_FAILED %s", e)
        return False, str(e)

    guardar_fix(db, dia, tipo)
    db.commit()
    logger.info("BANXICO_FIX_OK fecha=%s tipo=%s", dia, tipo)
    return True, f"FIX {dia.isoformat()} = {tipo}"


async def _job_loop():
    logger.info("Exchange rate job started (FIX de Banxico)")
    while True:
        try:
            token = token_configurado()
            if token:
                db = SessionLocal()
                try:
                    if not hay_fix_de_hoy(db):
                        actualizar_fix_ahora(db, token)
                finally:
                    db.close()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Exchange rate job tick failed")
        await asyncio.sleep(segundos_hasta_la_proxima_corrida(datetime.now(TZ_MX)))


def start_exchange_rate_job():
    """Lanza el job. No-op en SQLite o sin BANXICO_TOKEN."""
    global _job_task
    if _IS_SQLITE:
        logger.info("Exchange rate job disabled (SQLite backend)")
        return None
    if not token_configurado():
        logger.info("Exchange rate job disabled (sin BANXICO_TOKEN)")
        return None
    if _job_task and not _job_task.done():
        return _job_task
    _job_task = asyncio.create_task(_job_loop())
    return _job_task


async def stop_exchange_rate_job():
    global _job_task
    if _job_task and not _job_task.done():
        _job_task.cancel()
        try:
            await _job_task
        except asyncio.CancelledError:
            pass
    _job_task = None
```

`app/main.py`, en `startup_event`, después de `start_outbox_worker()` (línea 91):

```python
    # FIX de Banxico para el equivalente en dolares del POS. No-op en SQLite y
    # sin BANXICO_TOKEN (ver el docstring del modulo).
    from app.core.exchange_rate_job import start_exchange_rate_job
    start_exchange_rate_job()
```

y en `shutdown_event`, después de `await stop_outbox_worker()` (línea 97):

```python
    from app.core.exchange_rate_job import stop_exchange_rate_job
    await stop_exchange_rate_job()
```

`app/modules/tenants/router.py`, línea 16, agregar `ExchangeRateRead` al import existente:

```python
from app.schemas.organization import (
    ExchangeRateRead,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
)
```

sustituir el cuerpo de `update_organization` desde la línea 61 (`org = db.query(...)`) hasta el `return org` de la línea 84:

```python
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # `exclude_unset` una sola vez: el bloque de permisos y el de escritura
    # tienen que mirar exactamente el mismo diccionario.
    data_to_update = org_in.dict(exclude_unset=True)

    # [HARDENING] Refined Logic: Check what is ACTUALLY changing
    if current_user.role not in ADMIN_ROLES:
        allowed_subset = {"printer_name", "ticket_header", "ticket_footer", "paper_width_mm"}

        for key, new_val in data_to_update.items():
            current_val = getattr(org, key)
            # If value is changing...
            if new_val != current_val:
                # ...and it's not in the whitelist, BLOCK IT.
                if key not in allowed_subset:
                     print(f"[AUTH BLOCK] User {current_user.username} tried to change restricted field '{key}' from '{current_val}' to '{new_val}'")
                     require_admin(current_user)

    # Equivalente en dolares: se valida la configuracion RESULTANTE (la que
    # quedaria guardada), no el payload parcial. Asi un PUT que solo cambia el
    # margen no puede dejar la organizacion en modo manual sin tipo capturado,
    # y un PUT que no toca nada de USD ni siquiera entra aqui.
    if any(k.startswith("usd_rate_") for k in data_to_update):
        from app.services.exchange_rate import MODO_OFF, validar_config_usd

        modo = (data_to_update.get("usd_rate_mode", org.usd_rate_mode) or MODO_OFF).strip().lower()
        manual = data_to_update.get("usd_rate_manual", org.usd_rate_manual)
        margen = data_to_update.get("usd_rate_margin", org.usd_rate_margin)
        try:
            validar_config_usd(modo, manual, margen)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        if "usd_rate_mode" in data_to_update:
            data_to_update["usd_rate_mode"] = modo  # normalizado a minusculas

    for key, value in data_to_update.items():
        setattr(org, key, value)

    db.commit()
    db.refresh(org)
    return org
```

y agregar los dos endpoints nuevos justo después (antes del comentario `# [DEPRECATED] Creation handled via Platform Router`):

```python
# ═════════════════════════════════════════════════════════════════════════════
# TIPO DE CAMBIO USD (2026-09-17)
# Endpoint propio y barato para el POS: lo consume la cajera, que NO es admin y
# no tiene por que leer RFC ni configuracion fiscal solo para pintar un numero.
# Dos SELECT y cero llamadas de red.
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/exchange-rate", response_model=ExchangeRateRead)
def get_exchange_rate(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Tipo de cambio vigente de la organización. `rate = null` = no mostrar nada."""
    from app.services.exchange_rate import MODO_OFF, resolve_usd_rate, ultimo_fix

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization context not found")

    modo = (org.usd_rate_mode or MODO_OFF).strip().lower()
    fix = ultimo_fix(db) if modo != MODO_OFF else None
    resuelto = resolve_usd_rate(org, fix)

    return ExchangeRateRead(
        mode=modo,
        rate=resuelto.rate if resuelto else None,
        source=resuelto.source if resuelto else None,
        # El FIX se expone aunque no haya tipo efectivo: el panel de Empresa lo
        # muestra para que el dueño vea que el job SI esta bajando datos.
        fix_rate=(resuelto.fix_rate if resuelto else None) or (fix.rate if fix else None),
        fix_date=(resuelto.fix_date if resuelto else None) or (fix.rate_date if fix else None),
        margin=org.usd_rate_margin or 0,
        manual_rate=org.usd_rate_manual,
    )


@router.post("/exchange-rate/refresh")
def refresh_exchange_rate(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Baja el FIX de Banxico a demanda, para no esperar al job de mañana."""
    require_admin(current_user)

    from app.core.exchange_rate_job import actualizar_fix_ahora
    from app.services.banxico import token_configurado
    from app.services.exchange_rate import ultimo_fix

    token = token_configurado()
    if not token:
        raise HTTPException(
            status_code=503,
            detail="El servidor no tiene BANXICO_TOKEN configurado. Usa el modo manual.",
        )

    ok, mensaje = actualizar_fix_ahora(db, token)
    if not ok:
        raise HTTPException(status_code=503, detail=f"Banxico no respondió: {mensaje}")

    fila = ultimo_fix(db)
    return {
        "ok": True,
        "rate_date": fila.rate_date.isoformat() if fila else None,
        "rate": float(fila.rate) if fila else None,
        "source": fila.source if fila else None,
    }
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `python3 -m pytest -q -p no:warnings tests/test_banxico_client.py tests/test_exchange_rate_job.py tests/test_exchange_rate_endpoints.py`
Expected: todas PASSED (31 pruebas: 8 del cliente, 8 del job, 15 de los endpoints).

Comprobar además que no se rompió el `PUT` de organización ni el aislamiento por inquilino:
Run: `python3 -m pytest -q -p no:warnings -k "organization or tenant"`
Expected: sin `failed` nuevos respecto al baseline.

Y la suite completa:
Run: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py`
Expected: `652 passed` + las 54 nuevas de las Tasks 1 y 2, `2 skipped, 3 xfailed`, cero `failed`.

- [ ] **Step 5: Commit**

```bash
git add app/services/banxico.py app/core/exchange_rate_job.py app/main.py app/modules/tenants/router.py tests/test_banxico_client.py tests/test_exchange_rate_job.py tests/test_exchange_rate_endpoints.py
git commit -m "feat(usd): cliente de Banxico, job diario del FIX y endpoints de tipo de cambio

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb"
```

---

### Task 3: Snapshot del tipo de cambio en la venta y línea del ticket

**Files:**
- Modify: `app/models/sales.py:69` (`SalesDocument`, después de `change_given`)
- Modify: `scripts/railway_init.py` (lista `migrations`, junto a las tres entradas de la Task 1)
- Modify: `app/routers/sales.py:851-853` (antes del `db.flush()`), `:379-398` (`_respuesta_de_venta_existente`), `:966-974` (respuesta del alta)
- Modify: `app/pos_printer.py:192-196` (`build_ticket_bytes`), `:313-325` (nuevo `_usd_line` junto a `_total_line`), `:428` (`build_reissued_ticket_bytes`)
- Modify: `tests/test_pos_printer.py:51-74` (`_make_sale` declara `usd_rate`)
- Test: `tests/test_venta_usd_snapshot.py`, `tests/test_ticket_usd.py`

**Interfaces:**
- Consumes: `snapshot_usd_rate(db, org_id)` y `to_usd(amount_mxn, rate)` (Task 1).
- Produces: `SalesDocument.usd_rate: Decimal | None`; `PosPrinter._usd_line(usd_rate, total_mxn) -> bytes`; la respuesta de `POST /api/sales/` incluye `"usd_rate"` (`float | None`).

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
# tests/test_venta_usd_snapshot.py
"""La venta congela el tipo de cambio efectivo, y jamas se cae por eso.

`create_sale` es el motor ATS-critico: el equivalente en dolares es
informativo y no puede impedir un cobro ni mover un centavo del total."""
from datetime import date
from decimal import Decimal

from app.models.exchange_rate import ExchangeRate
from app.models.sales import SalesDocument
from conftest import _make_product
from tests.test_sale_variant_name_null import _abrir_caja, _habilitar_pos


def _preparar(db, org, branch, cajero, precio="185.00"):
    _habilitar_pos(db, org)
    _make_product(db, org, "Playera USD", "USD-01", Decimal(precio), [(branch.id, True)])
    _abrir_caja(db, org, branch, cajero)
    db.commit()


def _vender(client, org, auth, monto="185.00"):
    return client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "USD-01", "quantity": 1}],
        "payments": [{"method": "CASH", "amount": monto}],
    }, headers={**auth, "X-Organization-ID": str(org.id)})


def test_organizacion_sin_tipo_de_cambio_deja_null(client, db, org, branch_a, cajero_a, auth_cajero_a):
    _preparar(db, org, branch_a, cajero_a)
    r = _vender(client, org, auth_cajero_a)
    assert r.status_code in (200, 201), r.text
    assert r.json()["usd_rate"] is None
    venta = db.query(SalesDocument).filter(SalesDocument.id == r.json()["sale_id"]).one()
    assert venta.usd_rate is None


def test_modo_auto_congela_fix_mas_margen(client, db, org, branch_a, cajero_a, auth_cajero_a):
    _preparar(db, org, branch_a, cajero_a)
    db.add(ExchangeRate(currency="USD", rate_date=date(2026, 9, 17), rate=Decimal("18.2000")))
    org.usd_rate_mode = "auto"
    org.usd_rate_margin = Decimal("0.30")
    db.commit()

    r = _vender(client, org, auth_cajero_a)
    assert r.status_code in (200, 201), r.text
    assert Decimal(str(r.json()["usd_rate"])) == Decimal("18.5000")
    venta = db.query(SalesDocument).filter(SalesDocument.id == r.json()["sale_id"]).one()
    assert venta.usd_rate == Decimal("18.5000")


def test_el_snapshot_no_mueve_el_total_cobrado(client, db, org, branch_a, cajero_a, auth_cajero_a):
    _preparar(db, org, branch_a, cajero_a)
    org.usd_rate_mode = "manual"
    org.usd_rate_manual = Decimal("19.5000")
    db.commit()

    cuerpo = _vender(client, org, auth_cajero_a).json()
    assert cuerpo["total"] == 185.0
    assert cuerpo["paid"] == 185.0
    assert cuerpo["change"] == 0.0
    assert Decimal(str(cuerpo["usd_rate"])) == Decimal("19.5000")


def test_si_el_servicio_revienta_la_venta_se_cobra_igual(
    client, db, org, branch_a, cajero_a, auth_cajero_a, monkeypatch
):
    """Banxico caido, tabla ausente o bug del servicio: se cobra igual y el
    equivalente queda en NULL. Es la unica forma aceptable de tocar create_sale."""
    _preparar(db, org, branch_a, cajero_a)
    org.usd_rate_mode = "manual"
    org.usd_rate_manual = Decimal("19.5000")
    db.commit()

    from app.services import exchange_rate as servicio

    def _revienta(db_, org_):
        raise RuntimeError("tabla exchange_rates caída")

    monkeypatch.setattr(servicio, "tipo_vigente", _revienta)

    r = _vender(client, org, auth_cajero_a)
    assert r.status_code in (200, 201), r.text
    assert r.json()["usd_rate"] is None
    assert r.json()["total"] == 185.0
```

```python
# tests/test_ticket_usd.py
"""Linea de equivalente en dolares en el ticket y en el reemitido.

SimpleNamespace en vez de MagicMock a proposito: con MagicMock cualquier
atributo no declarado sale truthy y la prueba de "no imprime nada" mentiria."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.pos_printer import PosPrinter


def _org():
    return SimpleNamespace(
        name="Tienda Demo", legal_name=None, tax_id=None, tax_regime=None,
        address=None, phone=None, logo_url=None,
        ticket_header=None, ticket_footer=None, price_includes_tax=False,
    )


def _line(description, quantity, unit_price):
    qty = Decimal(str(quantity))
    unit = Decimal(str(unit_price))
    return SimpleNamespace(description=description, quantity=qty, unit_price=unit,
                           total_line=qty * unit, variant_id="v1")


def _sale(usd_rate=None, total="185.00"):
    total_dec = Decimal(total)
    return SimpleNamespace(
        lines=[_line("Playera", 1, total_dec)],
        series="A", folio=123,
        subtotal=total_dec, tax_amount=Decimal("0"), total_amount=total_dec,
        customer_name="Cliente Test", customer=None,
        created_at=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
        notes=None, requires_invoice=False,
        usd_rate=Decimal(usd_rate) if usd_rate is not None else None,
    )


def _build(sale, ancho=80):
    p = PosPrinter(paper_width_mm=ancho)
    raw = p.build_ticket_bytes(
        sale, paid=Decimal("0"), change=Decimal("0"), method="CASH",
        cashier="Cajero Test", is_reprint=False, organization=_org(),
        branch=None, returns=None, payments_detail=None,
    )
    return raw.decode("latin-1", "replace")


def test_sin_tipo_de_cambio_no_imprime_nada():
    # Neutralidad: una organizacion sin la funcion encendida imprime el mismo
    # ticket de siempre, byte por byte.
    assert "USD" not in _build(_sale())


def test_imprime_el_equivalente_y_el_tipo():
    texto = _build(_sale(usd_rate="18.5000"))
    assert "USD (T.C. 18.5000):" in texto
    assert "10.00" in texto  # 185.00 / 18.50


def test_la_linea_cabe_en_papel_de_58mm():
    texto = _build(_sale(usd_rate="18.5000"), ancho=58)
    renglones = [l.rstrip() for l in texto.split("\n") if "USD" in l]
    assert renglones, "debe imprimirse la línea USD"
    for l in renglones:
        assert len(l) <= 32, f"línea de {len(l)} columnas: {l!r}"


def test_la_linea_cabe_en_papel_de_80mm():
    texto = _build(_sale(usd_rate="18.5000"), ancho=80)
    for l in texto.split("\n"):
        assert len(l.rstrip()) <= 56, f"línea de {len(l.rstrip())} columnas: {l!r}"


def test_tipo_invalido_se_ignora():
    assert "USD" not in _build(_sale(usd_rate="0"))


def test_el_reemitido_usa_el_mismo_tipo():
    p = PosPrinter(paper_width_mm=80)
    raw = p.build_reissued_ticket_bytes(
        sale=_sale(usd_rate="18.5000"), cashier="Cajero Test",
        organization=_org(), branch=None, returns=[],
    )
    assert "USD (T.C. 18.5000):" in raw.decode("latin-1", "replace")
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_venta_usd_snapshot.py tests/test_ticket_usd.py`
Expected: en `test_venta_usd_snapshot.py`, `KeyError: 'usd_rate'` en la respuesta y `AttributeError: 'SalesDocument' object has no attribute 'usd_rate'`; en `test_ticket_usd.py`, fallan los cuatro casos que esperan la línea `USD (T.C. …)`.

- [ ] **Step 3: Implementar**

`app/models/sales.py`, en `SalesDocument` justo después de `change_given` (línea 69):

```python
    # Equivalente en dolares (2026-09-17): tipo de cambio efectivo CONGELADO al
    # cobrar, para que el ticket y su reimpresion muestren siempre el mismo
    # numero aunque el FIX de mañana sea otro. NULL = venta anterior a la
    # funcion, o organizacion en modo 'off'. NO participa de ningun calculo de
    # cobro; es informativo (ver app/services/exchange_rate.py).
    usd_rate = Column(Numeric(10, 4), nullable=True)
```

`scripts/railway_init.py`, en la lista `migrations`, junto a las tres entradas de la Task 1:

```python
        ("sales_documents", "usd_rate", "ALTER TABLE sales_documents ADD COLUMN usd_rate NUMERIC(10,4);"),
```

`app/routers/sales.py`, entre `db.add(sales_doc)` (fin del bloque `else`, línea 851) y el `db.flush()` de la línea 853:

```python
        db.add(sales_doc)

    # Equivalente en dolares (informativo). Se congela el tipo de cambio
    # efectivo del momento para que el ticket y su reimpresion muestren el
    # mismo numero. `snapshot_usd_rate` NUNCA lanza: si Banxico, la tabla o el
    # servicio fallan devuelve None y la venta se cobra igual. NO participa de
    # ningun calculo de totales, pagos, stock ni caja.
    if getattr(sales_doc, "usd_rate", None) is None:
        from app.services.exchange_rate import snapshot_usd_rate
        sales_doc.usd_rate = snapshot_usd_rate(db, org_id)

    db.flush()
```

en `_respuesta_de_venta_existente` (el `return` de las líneas 389-398), agregar la clave al dict devuelto para que el reenvío idempotente tenga la misma forma que el alta:

```python
        "credit_debt": 0.0,
        # Misma forma que el alta normal: el POS no distingue.
        "usd_rate": float(sale.usd_rate) if sale.usd_rate is not None else None,
        "duplicate_ignored": True,
    }
```

y en la respuesta del alta (línea 966-974), agregar la coma faltante y la clave:

```python
    return {
        "status": "success",
        "sale_id": sales_doc.id,
        "folio": f"{sales_doc.series}-{sales_doc.folio}",
        "total": float(sales_doc.total_amount.quantize(Decimal("0.01")) if sales_doc.total_amount is not None else Decimal("0.00")),
        "paid": float(total_paid.quantize(Decimal("0.01"))),
        "change": float(change_response),
        "credit_debt": float(remaining_debt.quantize(Decimal("0.01"))),
        # Tipo de cambio congelado en la venta. None = la organizacion no tiene
        # equivalente en dolares configurado.
        "usd_rate": float(sales_doc.usd_rate) if sales_doc.usd_rate is not None else None,
    }
```

`app/pos_printer.py`, en `build_ticket_bytes` justo después del `BOLD_OFF` del TOTAL (línea 193) y antes del bloque de pago (línea 196):

```python
        raw += self.CMD["BOLD_ON"]
        raw += self._total_line("TOTAL", net_total)
        raw += self.CMD["BOLD_OFF"]

        # Equivalente en dolares. Solo si la venta trae el tipo congelado
        # (`sales_documents.usd_rate`); una organizacion sin tipo de cambio ve
        # el ticket de siempre.
        raw += self._usd_line(getattr(sale, "usd_rate", None), net_total)
```

el helper nuevo, inmediatamente después de `_total_line` (línea 325):

```python
    def _usd_line(self, usd_rate, total_mxn: float) -> bytes:
        """'USD (T.C. 18.5000):            12.34'. Vacio si la venta no trae tipo.

        El tipo de cambio viaja EN LA ETIQUETA, no en una linea aparte con el
        simbolo '≈': el ticket se codifica en latin-1 (`_total_line`) y '≈'
        saldria impreso como '?'. La etiqueta mide 19 caracteres, asi que cabe
        en el `label_w` de 20 del papel de 58 mm.

        La conversion la hace `app/services/exchange_rate.py::to_usd`, unica
        fuente del redondeo (el mismo que usa la pantalla del POS).
        """
        if usd_rate is None:
            return b""
        from app.services.exchange_rate import to_usd

        tasa = Decimal(str(usd_rate))
        if tasa <= 0:
            return b""
        equivalente = to_usd(Decimal(str(total_mxn)), tasa)
        return self._total_line(f"USD (T.C. {tasa:.4f})", float(equivalente))
```

y en `build_reissued_ticket_bytes`, después del `BOLD_OFF` del TOTAL recomputado (línea 429):

```python
        raw += self.CMD["BOLD_ON"]
        raw += self._total_line("TOTAL", new_final)
        raw += self.CMD["BOLD_OFF"]

        # Mismo tipo de cambio que el ticket original: viene congelado en la
        # venta, no se vuelve a resolver.
        raw += self._usd_line(getattr(sale, "usd_rate", None), new_final)
```

`tests/test_pos_printer.py`, en `_make_sale` después de `sale.payments = []` (línea 62):

```python
    # Equivalente en dolares: EXPLICITO porque en un MagicMock cualquier
    # atributo no declarado sale truthy, y eso imprimiria una linea USD con un
    # MagicMock como tipo de cambio en TODAS las pruebas de ticket (mismo
    # motivo documentado arriba para org.price_includes_tax).
    sale.usd_rate = kwargs.get("usd_rate", None)
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `python3 -m pytest -q -p no:warnings tests/test_venta_usd_snapshot.py tests/test_ticket_usd.py tests/test_pos_printer.py tests/test_ticket_layout.py tests/test_sale_variant_name_null.py`
Expected: todas PASSED. `test_ticket_layout.py` usa `SimpleNamespace` sin `usd_rate`, así que `getattr(..., None)` lo deja intacto.

Run: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py`
Expected: cero `failed`; `652` + las nuevas de las Tasks 1-3.

- [ ] **Step 5: Commit**

```bash
git add app/models/sales.py app/routers/sales.py app/pos_printer.py scripts/railway_init.py tests/test_pos_printer.py tests/test_venta_usd_snapshot.py tests/test_ticket_usd.py
git commit -m "feat(usd): la venta congela el tipo de cambio y el ticket imprime el equivalente

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb"
```

---

### Task 4: El POS muestra el equivalente y el panel de Empresa lo configura

**Files:**
- Create: `frontend/src/utils/usd.ts`, `frontend/src/utils/usd.test.ts`
- Create: `frontend/src/store/exchangeRateStore.ts`
- Modify: `frontend/src/api/organization.ts:3-14` (interfaz `Organization`), `:36-45` (`organizationApi`)
- Modify: `frontend/src/pages/pos/POS.tsx` (imports línea 1-27; `useEffect` nuevo junto al de la línea 85)
- Modify: `frontend/src/components/pos/CartPanel.tsx:1-45` (imports y hooks), `:879-884` (bloque del Total)
- Modify: `frontend/src/components/pos/ProductSearch.tsx:1-7` (imports), `:283` (hooks del componente), `:336-356` (tarjeta)
- Modify: `frontend/src/pages/core/Organization.tsx:1-46` (imports, estado, handlers), `:206` (sección nueva después de la tarjeta de Logo)
- Test: `frontend/src/utils/usd.test.ts`

**Interfaces:**
- Consumes: `GET /api/organization/exchange-rate` y `POST /api/organization/exchange-rate/refresh` (Task 2).
- Produces: `usdEquivalent(amountMxn, rate) -> number`, `formatUsd(value) -> string`, `usdSummary(amountMxn, rate) -> string | null` en `frontend/src/utils/usd.ts`.
- Produces: `useExchangeRateStore` con `{ rate: number | null, info, loadedAt, loading, load(force?), reset() }`.
- Produces: `ExchangeRateInfo` y `organizationApi.getExchangeRate/refreshExchangeRate` en `frontend/src/api/organization.ts`.

- [ ] **Step 1: Escribir la prueba que falla**

```ts
// frontend/src/utils/usd.test.ts
import { describe, it, expect } from 'vitest'

import { formatUsd, usdEquivalent, usdSummary } from './usd'

// El equivalente en dólares es informativo: nunca debe producir NaN, "$NaN"
// ni un número con más de dos decimales en pantalla. Cuando no hay tipo de
// cambio, la UI no pinta nada — de ahí el `null` de `usdSummary`.

describe('usdEquivalent', () => {
  it('convierte y redondea a centavos', () => {
    expect(usdEquivalent(185, 18.5)).toBe(10)
    expect(usdEquivalent(100, 18.5)).toBe(5.41)   // 5.4054... half up
  })

  it('acepta los strings decimales que manda el backend', () => {
    expect(usdEquivalent('185.00', '18.5000')).toBe(10)
  })

  it('devuelve 0 con tipo de cambio inválido', () => {
    expect(usdEquivalent(185, 0)).toBe(0)
    expect(usdEquivalent(185, null)).toBe(0)
    expect(usdEquivalent(185, -1)).toBe(0)
    expect(usdEquivalent(185, 'abc')).toBe(0)
  })

  it('devuelve 0 con monto inválido', () => {
    expect(usdEquivalent(null, 18.5)).toBe(0)
    expect(usdEquivalent(undefined, 18.5)).toBe(0)
  })
})

describe('formatUsd', () => {
  it('no deja espacios duros en el string', () => {
    // `Intl` en es-MX separa "USD" del monto con U+00A0; se normaliza para que
    // el string sea comparable y no rompa un split/includes.
    expect(formatUsd(12.34)).toBe('USD 12.34')
    expect(formatUsd(12.34)).not.toContain(' ')
  })

  it('nunca devuelve NaN', () => {
    expect(formatUsd(null)).toBe('USD 0.00')
    expect(formatUsd('abc')).toBe('USD 0.00')
  })
})

describe('usdSummary', () => {
  it('arma la línea del carrito', () => {
    expect(usdSummary(185, 18.5)).toBe('≈ USD 10.00 · T.C. 18.50')
  })

  it('sin tipo de cambio devuelve null (no se pinta nada)', () => {
    expect(usdSummary(185, null)).toBeNull()
    expect(usdSummary(185, 0)).toBeNull()
  })
})
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/utils/usd.test.ts`
Expected: FAIL — `Failed to resolve import "./usd"`.

- [ ] **Step 3: Implementar**

`frontend/src/utils/usd.ts` (nuevo):

```ts
/**
 * Equivalente en dólares del POS.
 *
 * Funciones puras (sin React ni axios) para que `vitest` las pruebe: el
 * proyecto solo corre `src/**\/*.test.ts` con `environment: 'node'`.
 *
 * El número que se PERSISTE (`sales_documents.usd_rate`) y el que se IMPRIME
 * los calcula el backend con `Decimal` (`app/services/exchange_rate.py`); esto
 * es solo para pintar en pantalla. Ambos redondean a centavos, así que el
 * ticket y la pantalla coinciden.
 */
import { formatCurrency } from './currency'

/** Pesos → dólares, redondeado a centavos. Tipo de cambio inválido → 0. */
export function usdEquivalent(
  amountMxn: number | string | null | undefined,
  rate: number | string | null | undefined,
): number {
  const monto = Number(amountMxn)
  const tasa = Number(rate)
  if (!Number.isFinite(monto) || !Number.isFinite(tasa) || tasa <= 0) return 0
  return Math.round((monto / tasa) * 100) / 100
}

/** `"USD 12.34"`. Entrada inválida → `"USD 0.00"`, nunca `"$NaN"`. */
export function formatUsd(value: number | string | null | undefined): string {
  // `Intl` en es-MX separa "USD" del monto con un espacio duro (U+00A0). Se
  // normaliza a un espacio normal para que el string sea comparable.
  return formatCurrency(value, { currency: 'USD', fallback: 'USD 0.00' }).replace(/ /g, ' ')
}

/** `"≈ USD 10.00 · T.C. 18.50"` para el pie del carrito. Sin tasa → `null`. */
export function usdSummary(
  amountMxn: number | string | null | undefined,
  rate: number | string | null | undefined,
): string | null {
  const tasa = Number(rate)
  if (!Number.isFinite(tasa) || tasa <= 0) return null
  return `≈ ${formatUsd(usdEquivalent(amountMxn, tasa))} · T.C. ${tasa.toFixed(2)}`
}
```

`frontend/src/api/organization.ts`, en la interfaz `Organization` después de `industry_type` (línea 13):

```ts
  // Equivalente en dólares (2026-09-17). 'off' = la función está apagada y no
  // se muestra nada en el POS ni en el ticket.
  usd_rate_mode?: 'off' | 'auto' | 'manual'
  usd_rate_manual?: number | string | null
  usd_rate_margin?: number | string
}

/** Respuesta de GET /api/organization/exchange-rate. */
export interface ExchangeRateInfo {
  mode: 'off' | 'auto' | 'manual'
  /** Tipo efectivo (ya con el margen). `null` = no mostrar nada. */
  rate: number | string | null
  source: 'banxico' | 'manual' | null
  fix_rate: number | string | null
  fix_date: string | null
  margin: number | string
  manual_rate: number | string | null
```

y en `organizationApi`, después de `updateOrg` (línea 45):

```ts
  getExchangeRate: async (): Promise<ExchangeRateInfo> => {
    const { data } = await client.get<ExchangeRateInfo>('/organization/exchange-rate')
    return data
  },

  refreshExchangeRate: async (): Promise<{ ok: boolean; rate_date: string | null; rate: number | null }> => {
    const { data } = await client.post('/organization/exchange-rate/refresh')
    return data
  },
```

`frontend/src/store/exchangeRateStore.ts` (nuevo):

```ts
import { create } from 'zustand'

import { organizationApi, type ExchangeRateInfo } from '../api/organization'

/**
 * Caché del tipo de cambio USD de la organización activa.
 *
 * Lo llena `GET /api/organization/exchange-rate` — endpoint propio y barato
 * porque quien lo consume es la cajera, que no es admin y no debe leer la
 * configuración fiscal completa solo para pintar un número.
 *
 * `rate === null` significa "no mostrar nada": es el estado de toda
 * organización que no configuró tipo de cambio (modo `off`) y también el de
 * una en modo `auto` que todavía no tiene FIX descargado. El POS no distingue
 * los dos casos, y ante un error de red se queda igual — sin equivalente y sin
 * mensaje de error.
 */
const REFRESCO_MS = 30 * 60 * 1000 // el FIX cambia una vez al día

interface ExchangeRateStore {
  rate: number | null
  info: ExchangeRateInfo | null
  loadedAt: number | null
  loading: boolean
  load: (force?: boolean) => Promise<void>
  reset: () => void
}

export const useExchangeRateStore = create<ExchangeRateStore>((set, get) => ({
  rate: null,
  info: null,
  loadedAt: null,
  loading: false,

  load: async (force = false) => {
    const { loading, loadedAt } = get()
    if (loading) return
    if (!force && loadedAt !== null && Date.now() - loadedAt < REFRESCO_MS) return
    set({ loading: true })
    try {
      const info = await organizationApi.getExchangeRate()
      const tasa = info?.rate == null ? NaN : Number(info.rate)
      set({
        rate: Number.isFinite(tasa) && tasa > 0 ? tasa : null,
        info: info ?? null,
        loadedAt: Date.now(),
        loading: false,
      })
    } catch {
      // Sin tipo de cambio simplemente no se muestra el equivalente. Nunca un
      // error en pantalla ni un cobro bloqueado.
      set({ rate: null, info: null, loadedAt: Date.now(), loading: false })
    }
  },

  reset: () => set({ rate: null, info: null, loadedAt: null, loading: false }),
}))
```

`frontend/src/pages/pos/POS.tsx`, agregar el import junto a los demás stores (después de la línea 10):

```ts
import { useExchangeRateStore } from '../../store/exchangeRateStore'
```

y un `useEffect` junto al de `checkSession` (después de la línea 85):

```ts
  // Tipo de cambio USD: se carga al entrar al POS y se refresca cada 30 min.
  // El store es neutro si la organización no lo configuró (`rate = null`), así
  // que el carrito y las tarjetas simplemente no pintan nada.
  const loadUsdRate = useExchangeRateStore((s) => s.load)
  useEffect(() => {
    loadUsdRate()
    const id = setInterval(() => loadUsdRate(true), 30 * 60 * 1000)
    return () => clearInterval(id)
  }, [loadUsdRate])
```

`frontend/src/components/pos/CartPanel.tsx`, imports (después de la línea 11):

```ts
import { useExchangeRateStore } from '../../store/exchangeRateStore'
import { usdSummary } from '../../utils/usd'
```

hooks, después de `const discountedSubtotal = ...` (línea 43):

```ts
  // Equivalente en dólares del total. La carga la dispara POS.tsx; aquí solo
  // se lee. `null` (organización sin tipo de cambio) ⇒ no se pinta nada.
  const usdRate = useExchangeRateStore((s) => s.rate)
  const usdLine = usdSummary(total, usdRate)
```

y en el bloque de totales, inmediatamente después del `div` del Total (línea 884, el que termina con `{formatCurrency(total)}</span>` y su `</div>`):

```tsx
        {usdLine && (
          <div
            className="flex justify-end text-xs font-semibold tabular-nums pt-0.5"
            style={{ color: 'var(--dax-text-muted)' }}
            title="Equivalente informativo — el cobro es en pesos"
          >
            {usdLine}
          </div>
        )}
```

`frontend/src/components/pos/ProductSearch.tsx`, imports (después de la línea 7):

```ts
import { useExchangeRateStore } from '../../store/exchangeRateStore'
import { formatUsd, usdEquivalent } from '../../utils/usd'
```

dentro del componente, junto a los demás hooks de store:

```ts
  // Precio en dólares por tarjeta. Solo lectura: POS.tsx dispara la carga.
  const usdRate = useExchangeRateStore((s) => s.rate)
```

y en la tarjeta, justo después del `</div>` que cierra el bloque del precio base y antes del comentario `{/* Tiers extra (Mayoreo, Caja, …) — fila compacta debajo */}` (línea ~355):

```tsx
                      {usdRate !== null && (
                        <p
                          className="text-[10px] font-semibold tabular-nums text-right"
                          style={{ color: 'var(--dax-text-faint)' }}
                        >
                          ≈ {formatUsd(usdEquivalent(tiers[0].value, usdRate))}
                        </p>
                      )}
```

`frontend/src/pages/core/Organization.tsx`:

imports (línea 2 y 8):

```ts
import { organizationApi, type Organization, type Branch, type BranchCreate, type ExchangeRateInfo } from '../../api/organization'
```
```ts
import { errorDetailText } from '../../utils/errorDetail'
```

estado nuevo, después de `const [logoError, setLogoError] = useState<string | null>(null)` (línea 29):

```ts
  const [fxInfo, setFxInfo] = useState<ExchangeRateInfo | null>(null)
  const [fxRefreshing, setFxRefreshing] = useState(false)
```

en el `useEffect` inicial, agregar la tercera promesa al `Promise.all` (línea 33-38):

```ts
    Promise.all([
      organizationApi.getOrg().then((o) => { setOrg(o); setOrgForm(o) }),
      organizationApi.getBranches().then(setBranches),
      organizationApi.getExchangeRate().then(setFxInfo).catch(() => {}),
    ]).catch(() => {}).finally(() => setLoading(false))
```

`saveOrg` (líneas 40-46) pasa a mostrar el `detail` del backend —es donde aterriza el 422 de una configuración de tipo de cambio incoherente— y refresca el estado del FIX:

```ts
  const cargarFx = () => organizationApi.getExchangeRate().then(setFxInfo).catch(() => {})

  const saveOrg = async () => {
    setSaving(true)
    try {
      const updated = await organizationApi.updateOrg(orgForm)
      setOrg(updated); setOrgForm(updated)
      await cargarFx()
    } catch (e: any) {
      // El 422 del PUT trae el motivo en español ("En modo manual hay que
      // capturar un tipo de cambio mayor que cero.").
      toast.error(errorDetailText(e?.response?.data?.detail, 'Error al guardar la organización'))
    } finally { setSaving(false) }
  }

  const refreshFx = async () => {
    setFxRefreshing(true)
    try {
      await organizationApi.refreshExchangeRate()
      await cargarFx()
      toast.success('Tipo de cambio actualizado')
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo bajar el tipo de cambio de Banxico'))
    } finally { setFxRefreshing(false) }
  }
```

y la sección nueva, después de la `DaxCard` del logo y antes de la de "Encabezado y Pie de Ticket" (línea ~206):

```tsx
          {/* Tipo de cambio USD */}
          <DaxCard>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">
              <i className="fa-solid fa-dollar-sign mr-1.5" />Tipo de cambio USD
            </p>
            <p className="text-xs text-slate-400 mb-4">
              Muestra el equivalente en dólares en el punto de venta y en el ticket.
              El cobro sigue siendo en pesos. Con <b>Apagado</b> no se muestra nada.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="dax-label">Modo</label>
                <select
                  value={orgForm.usd_rate_mode ?? 'off'}
                  onChange={(e) => setOrgForm((p) => ({ ...p, usd_rate_mode: e.target.value as Organization['usd_rate_mode'] }))}
                  className="dax-input w-full"
                >
                  <option value="off">Apagado</option>
                  <option value="auto">Automático (FIX de Banxico + ajuste)</option>
                  <option value="manual">Manual (tipo fijo)</option>
                </select>
              </div>
              <div>
                <label className="dax-label">Ajuste sobre el FIX</label>
                <input
                  type="number" step="0.01"
                  value={orgForm.usd_rate_margin ?? '0'}
                  onChange={(e) => setOrgForm((p) => ({ ...p, usd_rate_margin: e.target.value }))}
                  disabled={(orgForm.usd_rate_mode ?? 'off') !== 'auto'}
                  className="dax-input w-full tabular-nums disabled:opacity-40"
                  placeholder="0.30"
                />
                <p className="text-[10px] mt-1 text-slate-600">Pesos que se suman al FIX. Puede ser negativo.</p>
              </div>
              <div>
                <label className="dax-label">Tipo de cambio manual</label>
                <input
                  type="number" step="0.0001"
                  value={orgForm.usd_rate_manual ?? ''}
                  onChange={(e) => setOrgForm((p) => ({ ...p, usd_rate_manual: e.target.value || null }))}
                  disabled={(orgForm.usd_rate_mode ?? 'off') !== 'manual'}
                  className="dax-input w-full tabular-nums disabled:opacity-40"
                  placeholder="19.5000"
                />
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 mt-4">
              <div className="text-xs text-slate-400">
                {fxInfo?.fix_rate != null ? (
                  <>FIX del {fxInfo.fix_date ?? '—'}: <b className="tabular-nums text-slate-200">{Number(fxInfo.fix_rate).toFixed(4)}</b></>
                ) : (
                  <>Sin FIX descargado todavía.</>
                )}
                {fxInfo?.rate != null && (
                  <> · Vigente: <b className="tabular-nums text-emerald-400">{Number(fxInfo.rate).toFixed(4)}</b></>
                )}
              </div>
              <div className="flex gap-2">
                <button onClick={refreshFx} disabled={fxRefreshing} className="dax-btn-secondary text-xs disabled:opacity-40">
                  {fxRefreshing ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-rotate" /> Actualizar ahora</>}
                </button>
                <button onClick={saveOrg} disabled={saving} className="dax-btn-primary text-xs disabled:opacity-40">
                  {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar</>}
                </button>
              </div>
            </div>
          </DaxCard>
```

- [ ] **Step 4: Correr y ver que pasa**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npm run build`
Expected: vitest en verde (**261 + 8 = 269**), `tsc` sin errores, build ok.

Verificación manual mínima (con el backend corriendo y `BANXICO_TOKEN` vacío):
1. Entrar al POS con una organización en modo `off` → el carrito y las tarjetas se ven exactamente como antes.
2. En **Empresa → Tipo de cambio USD**, elegir `Manual`, escribir `19.5000` y Guardar.
3. Volver al POS (recarga): bajo el total aparece `≈ USD … · T.C. 19.50` y cada tarjeta trae su precio en dólares.
4. Cobrar una venta de prueba e imprimir: el ticket trae `USD (T.C. 19.5000):` con el equivalente. Cancelar la venta después.
5. Elegir `Manual` y dejar el tipo vacío → el Guardar muestra el mensaje en español del 422, no un error genérico.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/usd.ts frontend/src/utils/usd.test.ts frontend/src/store/exchangeRateStore.ts frontend/src/api/organization.ts frontend/src/pages/pos/POS.tsx frontend/src/components/pos/CartPanel.tsx frontend/src/components/pos/ProductSearch.tsx frontend/src/pages/core/Organization.tsx
git commit -m "feat(usd): el POS muestra el equivalente en dolares y Empresa configura el tipo de cambio

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb"
```

---

## Despliegue de la Fase A

1. Suite backend y frontend en verde (ver Global Constraints).
2. Configurar `BANXICO_TOKEN` en el entorno **antes** de desplegar el código. Sin token todo sigue funcionando (el job queda apagado y solo sirve el modo manual), pero el modo `auto` no tendría FIX. El token se obtiene gratis en `https://www.banxico.org.mx/SieAPIRest/service/v1/token`.
3. Fusionar la rama a `main` **con permiso del usuario**; el push a `main` redespliega Railway (Kaory). `railway_init` aplica los cuatro `ALTER` y `create_all` crea `exchange_rates`.
4. VPS: `git archive --format=tar HEAD | ssh ionos 'tar -x -C /srv/apps/atlas-one-prod/src'` y `ssh ionos 'cd /srv/apps/atlas-one-prod && docker compose build && docker compose up -d'`.
5. Verificar que la función sigue **apagada** en todas las organizaciones: `GET /api/organization/exchange-rate` con cualquier sesión devuelve `{"mode":"off","rate":null,…}` y el POS se ve idéntico. Esa es la prueba de que el despliegue fue neutro.
6. En la organización que lo pidió: **Empresa → Tipo de cambio USD**, elegir modo, "Actualizar ahora" para traer el FIX del día, y validar en el POS con una venta de prueba que después se cancela.
7. A las 12:30 del día siguiente, revisar en el log la línea `BANXICO_FIX_OK fecha=… tipo=…`. Recordar que los registros de Railway son efímeros: si hay que confirmar que el job corrió, consultar la tabla (`SELECT * FROM exchange_rates ORDER BY rate_date DESC LIMIT 5`), no el log de ayer.

## Auto-revisión del plan

- **Cobertura del diseño.** Decisión 1 (modos) → Tasks 1, 2 y 4; 2 (tabla global sin `organization_id`) → Task 1 con prueba explícita; 3 (columnas en `organization`) → Task 1; 4 (`VARCHAR`, no enum de DB) → Task 1; 5 (servicio como fuente única) → Task 1, consumido por las Tasks 2, 3 y 4; 6 (snapshot en la venta) → Task 3; 7 (el snapshot no participa de cálculos) → Task 3, prueba `test_si_el_servicio_revienta_la_venta_se_cobra_igual`; 8 (`USD (T.C. …)` y no `≈` en el ticket) → Task 3, pruebas de ancho a 58 y 80 mm; 9 (job como el del outbox, doble apagado) → Task 2, pruebas `test_apagado_en_sqlite` y `test_apagado_sin_token`; 10 (escritura idempotente) → Task 2, `test_guarda_el_fix_una_sola_vez_por_dia`; 11 (nunca red en pruebas) → Task 2, todo con `monkeypatch`; 12 (endpoint propio para el POS) → Task 2 y store de la Task 4; 13 (conversión pura en el frontend) → Task 4 con `vitest`.
  El alcance "dentro" de la Fase A queda cubierto entero: tabla y columnas (1), servicio (1), cliente y job (2), tres endpoints (2), snapshot (3), ticket y reemitido (3), total del carrito y precio por tarjeta (4), panel de Empresa (4).
- **Consistencia de nombres entre tareas.** `resolve_usd_rate`, `to_usd`, `validar_config_usd`, `ResolvedRate`, `MODO_OFF/AUTO/MANUAL`, `FUENTE_BANXICO/FUENTE_MANUAL`, `MONEDA_USD` (Task 1 → 2, 3); `ultimo_fix` y `guardar_fix` (Task 1 → 2); `snapshot_usd_rate` (Task 1 → 3); `fetch_fix` y `token_configurado` (Task 2, parcheados por nombre en las pruebas de la Task 2); `actualizar_fix_ahora` (Task 2, usado por el endpoint de refresco y por la prueba del job); `SalesDocument.usd_rate` (Task 3 → `_usd_line` y respuesta del checkout); `ExchangeRateRead` en el backend ↔ `ExchangeRateInfo` en el frontend, con los mismos siete campos (`mode`, `rate`, `source`, `fix_rate`, `fix_date`, `margin`, `manual_rate`); `usdEquivalent`/`formatUsd`/`usdSummary` (Task 4, consumidos por `CartPanel` y `ProductSearch`); `useExchangeRateStore.rate` es la única bandera de "mostrar o no" en las tres vistas del POS.
- **Correcciones aplicadas tras la revisión.**
  - El ticket usa `USD (T.C. …)` en vez de `≈ USD`: `_total_line` codifica en latin-1 y `"≈"` se imprimiría como `"?"` (`app/pos_printer.py:325`). El `≈` sí se usa en pantalla, que es UTF-8.
  - `tests/test_pos_printer.py::_make_sale` tiene que declarar `usd_rate = None`: es `MagicMock` y cualquier atributo no declarado sale truthy — sin esa línea, las 12 pruebas de ticket existentes empezarían a imprimir una línea USD con un `MagicMock` como tipo de cambio. `tests/test_ticket_layout.py` usa `SimpleNamespace` y no necesita cambio.
  - `formatUsd` normaliza U+00A0: `Intl` en `es-MX` separa `"USD"` del monto con espacio duro, y la prueba con espacio normal fallaría.
  - La validación del `PUT` se hace sobre los valores **resultantes** y antes del `setattr`, no después: así un `PUT` que solo cambia el margen no puede dejar la organización en modo `manual` sin tipo, y no hace falta un `db.rollback()` a media petición.
  - No se agrega guardia de rol nueva en el `PUT`: los tres campos caen fuera de la whitelist de no-admins que ya existe (`app/modules/tenants/router.py:67`), y la prueba `test_cajero_no_puede_configurar` fija ese contrato.
- **Fuera de alcance explícito de este plan:** cobrar en dólares (`USD_CASH`, `Payment.amount_foreign`, corte de caja bimonetario) — está diseñado en §7 del spec y se planea aparte; monedas distintas del dólar; precios de catálogo en USD; equivalente en cotizaciones, devoluciones y estado de cuenta; CFDI en moneda extranjera.
