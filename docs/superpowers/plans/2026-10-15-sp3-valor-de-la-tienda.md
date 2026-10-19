# SP3 · Valor de la tienda — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el dueño de cualquier organización vea cuánto vale su existencia hoy, a precio de venta y a costo, con el hueco de costos visible (piezas y SKUs sin costo), desglosado por sucursal, departamento o marca, y lo exporte a CSV.

**Architecture:** Un endpoint nuevo `GET /api/reports/valor-inventario` en un archivo propio (`app/routers/reports_valuacion.py`, montado bajo el mismo prefijo `/api/reports`) que corre una sola consulta agregada sobre `stock_on_hand × product_variants × products × branches`, filtrada por organización, sin borrados y solo sucursales que venden. El frontend consume el endpoint desde `reportsApi.valorInventario`, pinta una tarjeta en el inicio del dueño (`HQOperations`) y una página de desglose `/hq/valor-inventario` construida con el kit (`CabeceraPagina`, `BarraFiltros`, `TarjetaFila`, `ListaTarjetas`); el CSV se arma en el cliente con una función pura probada en vitest.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 (backend, Postgres en prod, SQLite en pytest); React 18 + Vite + TypeScript + vitest + @testing-library/react (frontend).

**Spec:** `docs/superpowers/specs/2026-10-14-mega-plan-altas-docs-responsivo-agente-design.md`, sección "SP3 · Valor de la tienda" (en la copia previa de la spec figura como "SP6"; es el mismo alcance), decisión 8 de "3. Decisiones de diseño" y decisiones abiertas 8 y 9 (tomadas como decididas: sin instantánea diaria en v1; el valor a costo solo lo ven ADMIN/DUEÑO; el GERENTE ve piezas y valor a venta de su sucursal).

## Global Constraints

- Toda query de negocio filtra `organization_id` (CLAUDE.md regla 5). Aquí se filtra explícitamente con el `org_id` de `get_current_active_organization`, igual que `app/routers/reports.py` (no con `scoped_query`, porque la consulta es de agregados sobre varias tablas).
- FKs a IDs UUID son `String(36)` (CLAUDE.md regla 4). No se crean tablas ni columnas nuevas en este plan (la decisión abierta 8 quedó en "sin instantánea diaria en v1"), así que no se toca `scripts/railway_init.py`.
- `valor_venta` = Σ existencia × precio, siempre completo. `valor_costo` = Σ existencia × costo **solo de las variantes con costo > 0**; costo NULL o 0 cuenta como "sin costo" y suma a `piezas_sin_costo`/`skus_sin_costo`. Sin margen inventado: si falta costo, se dice.
- Sin instantánea diaria, sin costo promedio ponderado, sin PEPS, sin insumos de gastro (fuera de alcance).
- Guard de rol: ADMIN/DUEÑO (y SUPERADMIN de plataforma) ven todo; GERENTE recibe solo su sucursal y `valor_costo: null`; CAJERO, VENDEDOR, SOPORTE_OPERATIVO y CLIENTE reciben 403.
- Sin `branch_id` solo cuentan las sucursales con `can_sell=True`; con `branch_id` cuenta esa sucursal aunque no venda (una bodega se puede inspeccionar a propósito).
- Precio y costo viven **solo en `ProductVariant`** (`price`, `cost`); `Product` no tiene precio ni costo, así que no hay herencia que resolver (ver "Hallazgos" al final).
- Borrado = `deleted_at IS NOT NULL` tanto en `products` como en `product_variants` (soft delete de `app/modules/products/router/core.py`). Un producto archivado (`is_active=False` sin `deleted_at`) sigue contando: su existencia física existe.
- La entrada de menú lleva `module: 'reports'` (módulo base: lo ven FREE y ULTRA+). El backend no usa `require_module` en reportes (ningún endpoint de `reports.py` lo usa); el gating es solo por rol.
- Pytest siempre con `--ignore=tests/test_cash_complete.py`. Un solo proceso de pytest por worktree (la "DB en memoria" es un archivo compartido).
- Frontend: `npm run build` corre `tsc && vite build`; cualquier error de tipos rompe el CI. Componentes de kit en `frontend/src/components/ui/` (`CabeceraPagina`, `BarraFiltros`, `TarjetaFila`, `ListaTarjetas`), no en `atlas-one/` (ver "Hallazgos").
- Comentarios y textos de UI en español; Pydantic v2; type hints en firmas nuevas. Sin `print()` de depuración.
- Commit solo al final de cada tarea; nunca push a `main`. Trabajar en rama `feat/valor-de-la-tienda` creada desde `main`.

## Review Focus

1. **Existencia negativa** (`qty_on_hand < 0`, una venta sin stock): el dueño espera que no reste valor a la tienda; la consulta debe excluir esas filas, no sumarlas. → Test en Task 1 (`test_existencia_negativa_no_resta`).
2. **Organización sin existencias** (org recién dada de alta): el endpoint debe devolver ceros y `grupos: []`, no un 500 por `None` en los agregados. → Test en Task 1 (`test_org_sin_existencias_devuelve_ceros`).
3. **Producto sin departamento ni marca** (el importador de rmazh deja ambos NULL): al agrupar debe aparecer una fila "Sin departamento"/"Sin marca" con `clave: ""`, no desaparecer de la suma. → Test en Task 2 (`test_agrupar_departamento_incluye_sin_departamento`, `test_agrupar_marca_incluye_sin_marca`).
4. **Gerente sin sucursal asignada** (`users.branch_id` es nullable): no debe ver la organización entera ni recibir un 500; espera un 403 con mensaje claro. → Test en Task 3 (`test_gerente_sin_sucursal_403`).
5. **Nombre de grupo con coma o comillas en el CSV** (marca "Dolce, Gabbana"): la fila no debe partirse en dos columnas al abrirla en Excel. → Test en Task 6 (`entrecomilla nombres con coma o comillas`).

---

## Mapa de archivos

| Archivo | Responsabilidad |
|---|---|
| Crear `app/routers/reports_valuacion.py` | Endpoint `GET /valor-inventario`: guard de rol, resolución de ámbito, consulta agregada, armado de la respuesta. Archivo aparte porque `app/routers/reports.py` tiene 1,129 líneas y todo su contenido es de ventas; la valuación solo lee existencias y no comparte helpers con él. |
| Modificar `app/schemas/reports.py` | Pydantic de respuesta: `ValuacionTotales`, `ValuacionGrupo`, `ValuacionInventarioResponse`. |
| Modificar `app/routers/__init__.py`, `app/main.py` | Registrar y montar el router nuevo bajo `/api/reports`. |
| Crear `tests/test_reports_valor_inventario.py` | Pruebas del endpoint (totales, agrupación, roles, aislamiento por org). |
| Modificar `frontend/src/api/reports.ts` | Tipos `ValuacionInventario` + `reportsApi.valorInventario`. |
| Crear `frontend/src/components/reports/ValorTiendaCard.tsx` + test | Tarjeta "Valor de la tienda" (dos cifras + aviso de piezas sin costo). |
| Modificar `frontend/src/pages/hq/HQOperations.tsx` | Cargar la valuación y pintar la tarjeta. |
| Crear `frontend/src/utils/valuacionCsv.ts` + test | CSV del desglose generado en el cliente (función pura). |
| Crear `frontend/src/pages/hq/HQValorInventario.tsx` | Página `/hq/valor-inventario`: agrupación, filtro por sucursal, tabla/tarjetas con totales, exportar CSV. |
| Modificar `frontend/src/components/layout/navConfig.ts` + test, `frontend/src/App.tsx` | Entrada de menú (`module: 'reports'`), `ROLE_ROUTES`, ruta lazy. |
| Modificar `docs/API_REFERENCE.md`, `docs/FRONTEND_VIEWS.md` | Documentar endpoint y vista. |

---

### Task 0: Rama de trabajo

**Files:** ninguno (git).

- [ ] **Step 1: Crear la rama desde `main`**

```bash
cd /mnt/d/Devs/atlas-one
git checkout main
git pull --ff-only
git checkout -b feat/valor-de-la-tienda
```

Expected: `Switched to a new branch 'feat/valor-de-la-tienda'`.

---

### Task 1: Endpoint `GET /api/reports/valor-inventario` — totales

**Files:**
- Modify: `app/schemas/reports.py` (al final del archivo)
- Create: `app/routers/reports_valuacion.py`
- Modify: `app/routers/__init__.py` (después de `from . import reports`)
- Modify: `app/main.py:211` (después de `app.include_router(reports.router, …)`)
- Test: `tests/test_reports_valor_inventario.py`

**Interfaces:**
- Consumes: `app.models` (`StockOnHand`, `ProductVariant`, `Product`, `Branch`, `Department`, `Brand`, `User`), `app.models.users.Role/PlatformRole`, `get_db`, `get_current_user`, `get_current_active_organization`.
- Produces: `GET /api/reports/valor-inventario?branch_id=&agrupar=` → `ValuacionInventarioResponse` con `agrupar: str`, `branch_id: Optional[int]`, `ve_costo: bool`, `totales: ValuacionTotales {piezas: float, skus: int, valor_venta: float, valor_costo: Optional[float], piezas_sin_costo: float, skus_sin_costo: int}`, `grupos: list[ValuacionGrupo {clave: str, nombre: str, piezas: float, skus: int, valor_venta: float, valor_costo: Optional[float], piezas_sin_costo: float}]`. En esta tarea `grupos` ya se calcula agrupando por sucursal (único criterio hasta Task 2). Funciones internas que Task 2 y 3 reutilizan: `_consulta(db, org_id, branch_id, columnas_grupo=())`, `_ambito(current_user) -> tuple[bool, bool]`, `_dinero(valor) -> float`.

- [ ] **Step 1: Escribir las pruebas de totales (fallan: el endpoint no existe → 404)**

Crear `tests/test_reports_valor_inventario.py`:

```python
"""`GET /api/reports/valor-inventario` -- cuanto vale la existencia hoy.

Dos cifras que siempre van juntas: valor a precio de venta (completo: toda
variante tiene precio) y valor a costo (solo variantes con costo > 0), mas el
conteo de piezas y SKUs sin costo. Caso guia: Eleven (zapatos cargados con
costo 0) e Imaltzin (el importador de rmazh deja `cost` NULL). Sin este
conteo, "valor a costo = $0" se lee como "mi tienda no vale nada".
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.inventory import StockOnHand
from app.models.organization import Branch, BranchType, Organization
from app.models.products import Brand, Department, Product, ProductVariant
from app.models.users import Role
from conftest import _auth_header, _make_user

URL = "/api/reports/valor-inventario"


def _producto(db, org, nombre, sku, precio, costo, existencias,
              department_id=None, brand_id=None):
    """Producto de una sola variante con existencias `{branch_id: qty}`.

    `costo=None` deja la columna en NULL (como el importador de rmazh);
    `costo=0` es el caso de los zapatos de Eleven.
    """
    p = Product(name=nombre, organization_id=org.id, is_active=True,
                department_id=department_id, brand_id=brand_id)
    db.add(p)
    db.flush()
    v = ProductVariant(
        product_id=p.id, sku=sku, organization_id=org.id,
        price=Decimal(str(precio)),
        cost=None if costo is None else Decimal(str(costo)),
    )
    db.add(v)
    db.flush()
    for branch_id, qty in existencias.items():
        db.add(StockOnHand(
            variant_id=v.id, branch_id=branch_id, organization_id=org.id,
            qty_on_hand=Decimal(str(qty)), is_active=True,
        ))
    db.flush()
    return p, v


@pytest.fixture()
def tienda(db, org, branch_a, branch_b):
    """Tres SKUs en dos sucursales que venden.

    Bolsa   $1000 costo $400 : 3 en A, 2 en B  -> venta 5000, costo 2000
    Zapato  $800  costo 0    : 4 en A          -> venta 3200, sin costo (4 pz)
    Playera $200  costo NULL : 10 en B         -> venta 2000, sin costo (10 pz)
    Totales: 19 piezas, 3 SKUs, venta 10200, costo 2000, 14 pz / 2 SKUs sin costo.
    Sucursal A: 7 pz, 2 SKUs, venta 6200, costo 1200, 4 pz sin costo.
    Sucursal B: 12 pz, 2 SKUs, venta 4000, costo 800, 10 pz sin costo.
    """
    bolsas = Department(name="Bolsas", organization_id=org.id)
    zapatos = Department(name="Zapatos", organization_id=org.id)
    gucci = Brand(name="Gucci", organization_id=org.id)
    db.add_all([bolsas, zapatos, gucci])
    db.flush()
    bolsa = _producto(db, org, "Bolsa", "BOL-1", 1000, 400,
                      {branch_a.id: 3, branch_b.id: 2},
                      department_id=bolsas.id, brand_id=gucci.id)
    zapato = _producto(db, org, "Zapato", "ZAP-1", 800, 0, {branch_a.id: 4},
                       department_id=zapatos.id)
    playera = _producto(db, org, "Playera", "PLA-1", 200, None, {branch_b.id: 10})
    return {
        "bolsa": bolsa, "zapato": zapato, "playera": playera,
        "dept_bolsas": bolsas, "dept_zapatos": zapatos, "marca_gucci": gucci,
    }


# ---------------------------------------------------------------- totales

def test_admin_ve_totales_de_la_organizacion(client, auth_admin, tienda):
    r = client.get(URL, headers=auth_admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ve_costo"] is True
    assert body["branch_id"] is None
    assert body["totales"] == {
        "piezas": 19.0, "skus": 3,
        "valor_venta": 10200.0, "valor_costo": 2000.0,
        "piezas_sin_costo": 14.0, "skus_sin_costo": 2,
    }


def test_costo_cero_cuenta_en_venta_pero_no_en_costo(client, auth_admin, db, org, branch_a):
    _producto(db, org, "Zapato", "ZAP-1", 800, 0, {branch_a.id: 4})
    t = client.get(URL, headers=auth_admin).json()["totales"]
    assert t["valor_venta"] == 3200.0
    assert t["valor_costo"] == 0.0
    assert t["piezas_sin_costo"] == 4.0
    assert t["skus_sin_costo"] == 1


def test_costo_null_cuenta_en_venta_pero_no_en_costo(client, auth_admin, db, org, branch_a):
    _producto(db, org, "Playera", "PLA-1", 200, None, {branch_a.id: 10})
    t = client.get(URL, headers=auth_admin).json()["totales"]
    assert t["valor_venta"] == 2000.0
    assert t["valor_costo"] == 0.0
    assert t["piezas_sin_costo"] == 10.0
    assert t["skus_sin_costo"] == 1


def test_sucursal_que_no_vende_queda_fuera_salvo_que_se_pida(client, auth_admin, db, org, tienda):
    bodega = Branch(name="Bodega", branch_type=BranchType.WAREHOUSE,
                    can_sell=False, is_active=True, organization_id=org.id)
    db.add(bodega)
    db.flush()
    _, v = tienda["bolsa"]
    db.add(StockOnHand(variant_id=v.id, branch_id=bodega.id, organization_id=org.id,
                       qty_on_hand=Decimal("100"), is_active=True))
    db.flush()

    sin_filtro = client.get(URL, headers=auth_admin).json()["totales"]
    assert sin_filtro["valor_venta"] == 10200.0
    assert sin_filtro["piezas"] == 19.0

    solo_bodega = client.get(URL, params={"branch_id": bodega.id}, headers=auth_admin).json()
    assert solo_bodega["branch_id"] == bodega.id
    assert solo_bodega["totales"]["piezas"] == 100.0
    assert solo_bodega["totales"]["valor_venta"] == 100000.0
    assert solo_bodega["totales"]["valor_costo"] == 40000.0


def test_filtro_por_sucursal(client, auth_admin, branch_a, tienda):
    t = client.get(URL, params={"branch_id": branch_a.id}, headers=auth_admin).json()["totales"]
    assert t == {
        "piezas": 7.0, "skus": 2,
        "valor_venta": 6200.0, "valor_costo": 1200.0,
        "piezas_sin_costo": 4.0, "skus_sin_costo": 1,
    }


def test_producto_borrado_queda_fuera(client, auth_admin, db, tienda):
    p, v = tienda["zapato"]
    p.deleted_at = datetime.now(timezone.utc)
    p.is_active = False
    v.deleted_at = datetime.now(timezone.utc)
    db.flush()
    t = client.get(URL, headers=auth_admin).json()["totales"]
    assert t["piezas"] == 15.0
    assert t["valor_venta"] == 7000.0
    assert t["skus"] == 2


def test_variante_borrada_queda_fuera_aunque_el_producto_siga(client, auth_admin, db, tienda):
    _, v = tienda["playera"]
    v.deleted_at = datetime.now(timezone.utc)
    db.flush()
    t = client.get(URL, headers=auth_admin).json()["totales"]
    assert t["piezas"] == 9.0
    assert t["valor_venta"] == 8200.0
    assert t["piezas_sin_costo"] == 4.0


def test_existencia_negativa_no_resta(client, auth_admin, db, org, branch_a, tienda):
    """Una venta sin stock deja la existencia en negativo; eso es un error de
    inventario, no valor negativo de la tienda."""
    _producto(db, org, "Fantasma", "FAN-1", 5000, 2500, {branch_a.id: -3})
    t = client.get(URL, headers=auth_admin).json()["totales"]
    assert t["piezas"] == 19.0
    assert t["valor_venta"] == 10200.0
    assert t["valor_costo"] == 2000.0


def test_org_sin_existencias_devuelve_ceros(client, auth_admin, org):
    r = client.get(URL, headers=auth_admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["totales"] == {
        "piezas": 0.0, "skus": 0, "valor_venta": 0.0, "valor_costo": 0.0,
        "piezas_sin_costo": 0.0, "skus_sin_costo": 0,
    }
    assert body["grupos"] == []


def test_otra_organizacion_no_se_mezcla(client, auth_admin, db, tienda):
    otra = Organization(name="Otra Org", status="ACTIVE")
    db.add(otra)
    db.flush()
    suc = Branch(name="Suc Otra", branch_type=BranchType.STORE,
                 can_sell=True, is_active=True, organization_id=otra.id)
    db.add(suc)
    db.flush()
    _producto(db, otra, "Ajeno", "AJ-1", 9999, 5000, {suc.id: 50})

    t = client.get(URL, headers=auth_admin).json()["totales"]
    assert t["piezas"] == 19.0
    assert t["valor_venta"] == 10200.0

    r = client.get(URL, params={"branch_id": suc.id}, headers=auth_admin)
    assert r.status_code == 404, r.text
```

- [ ] **Step 2: Correr las pruebas para verificar que fallan**

Run: `.venv/bin/python -m pytest -q -p no:warnings tests/test_reports_valor_inventario.py`
Expected: todas FAIL con `assert 404 == 200` (la ruta no existe todavía) o `KeyError: 'totales'`.

- [ ] **Step 3: Añadir los schemas de respuesta**

Al final de `app/schemas/reports.py` (el archivo ya importa `BaseModel`, `List`, `Decimal`; añadir `Optional`):

```python
from typing import Optional


# --- Valor de la tienda (valuacion de inventario) ---------------------------
# Dinero y piezas viajan como float (JSON numerico, como /dashboard); Decimal se
# serializaria como cadena en Pydantic v2 y la tarjeta tendria que parsear.

class ValuacionTotales(BaseModel):
    piezas: float
    skus: int
    valor_venta: float
    valor_costo: Optional[float]  # None cuando el rol no ve costos (gerente)
    piezas_sin_costo: float
    skus_sin_costo: int


class ValuacionGrupo(BaseModel):
    clave: str   # id de sucursal/departamento/marca; "" = sin asignar
    nombre: str
    piezas: float
    skus: int
    valor_venta: float
    valor_costo: Optional[float]
    piezas_sin_costo: float


class ValuacionInventarioResponse(BaseModel):
    agrupar: str
    branch_id: Optional[int]
    ve_costo: bool
    totales: ValuacionTotales
    grupos: List[ValuacionGrupo]
```

- [ ] **Step 4: Crear el router de valuación**

Crear `app/routers/reports_valuacion.py`:

```python
"""Atlas BOS routers/reports_valuacion — valor de la tienda (valuacion de inventario).

`GET /api/reports/valor-inventario` responde "¿cuanto vale mi existencia hoy?"
con dos cifras que SIEMPRE van juntas:

* `valor_venta` = Σ existencia × precio. Completa: toda variante tiene precio.
* `valor_costo` = Σ existencia × costo, solo de las variantes con costo > 0.
  Los catalogos importados (rmazh deja `cost` NULL; los zapatos de Eleven
  llegan con costo 0) harian que un "valor a costo" a secas se leyera como
  "mi tienda vale $0"; por eso viaja con `piezas_sin_costo` / `skus_sin_costo`.

Vive aparte de `reports.py` (1,100+ lineas, todo ventas): aqui solo se lee
`stock_on_hand`. Se monta bajo el mismo prefijo `/api/reports` (app/main.py).

Sin instantanea diaria (decision abierta 8 del mega plan 2026-10): v1 calcula
en vivo. Sin costo promedio ni PEPS: el costo es el de la variante, hoy.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, desc, func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.models import (
    Branch, Brand, Department, Product, ProductVariant, StockOnHand, User,
)
from app.models.users import PlatformRole, Role
from app.schemas.reports import (
    ValuacionGrupo, ValuacionInventarioResponse, ValuacionTotales,
)

router = APIRouter()

Agrupar = Literal["sucursal", "departamento", "marca"]

# Variante "sin costo": NULL, 0 o negativo (captura mal hecha). Sus piezas
# cuentan en `valor_venta` y en `piezas_sin_costo`, nunca en `valor_costo`.
_SIN_COSTO = or_(ProductVariant.cost.is_(None), ProductVariant.cost <= 0)
_QTY = StockOnHand.qty_on_hand
_VALOR_VENTA = func.sum(_QTY * func.coalesce(ProductVariant.price, 0))

# Los seis agregados; `_fila_a_dict` los lee por etiqueta.
_AGREGADOS = (
    func.coalesce(func.sum(_QTY), 0).label("piezas"),
    func.count(func.distinct(StockOnHand.variant_id)).label("skus"),
    func.coalesce(_VALOR_VENTA, 0).label("valor_venta"),
    func.coalesce(
        func.sum(case((_SIN_COSTO, 0), else_=_QTY * ProductVariant.cost)), 0,
    ).label("valor_costo"),
    func.coalesce(func.sum(case((_SIN_COSTO, _QTY), else_=0)), 0).label("piezas_sin_costo"),
    func.count(func.distinct(
        case((_SIN_COSTO, StockOnHand.variant_id), else_=None),
    )).label("skus_sin_costo"),
)

# Criterio de agrupacion -> (columna id, columna nombre, outerjoin extra, nombre
# para los productos sin ese dato). La sucursal ya viene unida en `_consulta`.
_GRUPOS = {
    "sucursal": (Branch.id, Branch.name, None, "Sin sucursal"),
    "departamento": (
        Department.id, Department.name,
        (Department, Department.id == Product.department_id), "Sin departamento",
    ),
    "marca": (Brand.id, Brand.name, (Brand, Brand.id == Product.brand_id), "Sin marca"),
}


def _dinero(valor) -> float:
    """Decimal/float/None de la DB -> float a 2 decimales."""
    return float(Decimal(str(valor or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _ambito(current_user: User) -> tuple[bool, bool]:
    """`(ve_costo, solo_su_sucursal)` segun el rol; 403 si el rol no ve valuacion.

    Decision abierta 9 del mega plan: el valor a costo es de ADMIN/DUEÑO; el
    gerente ve piezas y valor a venta de SU sucursal. El cajero no ve nada.
    """
    if current_user.platform_role == PlatformRole.SUPERADMIN:
        return True, False
    if current_user.role in (Role.ADMINISTRADOR, Role.DUEÑO):
        return True, False
    if current_user.role == Role.GERENTE:
        return False, True
    raise HTTPException(
        status_code=403,
        detail="Solo administrador, dueño o gerente pueden ver el valor de la tienda",
    )


def _consulta(db: Session, org_id: int, branch_id: Optional[int], columnas_grupo=()):
    """Existencias positivas de la org × variante × producto × sucursal.

    Sin productos ni variantes borrados (soft delete = `deleted_at`). Una
    existencia negativa (venta sin stock) es un error de inventario, no valor
    negativo: se excluye. Si no se pide sucursal, solo cuentan las que venden
    (`can_sell`): la bodega de una org multi-sucursal no es "la tienda"; con
    `branch_id` explicito se puede mirar cualquiera.
    """
    q = (
        db.query(*columnas_grupo, *_AGREGADOS)
        .select_from(StockOnHand)
        .join(ProductVariant, ProductVariant.id == StockOnHand.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .join(Branch, Branch.id == StockOnHand.branch_id)
        .filter(
            StockOnHand.organization_id == org_id,
            Product.organization_id == org_id,
            Branch.organization_id == org_id,
            StockOnHand.qty_on_hand > 0,
            ProductVariant.deleted_at.is_(None),
            Product.deleted_at.is_(None),
        )
    )
    if branch_id is not None:
        return q.filter(Branch.id == branch_id)
    return q.filter(Branch.can_sell == True)  # noqa: E712


def _fila_a_dict(fila, ve_costo: bool) -> dict:
    return {
        "piezas": _dinero(fila.piezas),
        "skus": int(fila.skus or 0),
        "valor_venta": _dinero(fila.valor_venta),
        "valor_costo": _dinero(fila.valor_costo) if ve_costo else None,
        "piezas_sin_costo": _dinero(fila.piezas_sin_costo),
    }


@router.get("/valor-inventario", response_model=ValuacionInventarioResponse)
def valor_inventario(
    agrupar: Agrupar = "sucursal",
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Valor de la tienda: totales de la organizacion (o de una sucursal) y
    desglose por sucursal, departamento o marca."""
    ve_costo, solo_su_sucursal = _ambito(current_user)
    if solo_su_sucursal:
        if not current_user.branch_id:
            raise HTTPException(status_code=403, detail="Tu usuario no tiene una sucursal asignada")
        # El parametro se ignora: el gerente no mira otras tiendas.
        branch_id = current_user.branch_id
    elif branch_id is not None:
        existe = db.query(Branch.id).filter(
            Branch.id == branch_id, Branch.organization_id == org_id,
        ).first()
        if existe is None:
            raise HTTPException(status_code=404, detail="Sucursal no encontrada")

    fila = _consulta(db, org_id, branch_id).one()
    totales = ValuacionTotales(
        **_fila_a_dict(fila, ve_costo), skus_sin_costo=int(fila.skus_sin_costo or 0),
    )

    col_id, col_nombre, union, sin_nombre = _GRUPOS[agrupar]
    q = _consulta(db, org_id, branch_id, (col_id, col_nombre))
    if union is not None:
        q = q.outerjoin(*union)
    filas = q.group_by(col_id, col_nombre).order_by(desc("valor_venta")).all()
    grupos = [
        ValuacionGrupo(
            clave="" if f[0] is None else str(f[0]),
            nombre=f[1] or sin_nombre,
            **_fila_a_dict(f, ve_costo),
        )
        for f in filas
    ]

    return ValuacionInventarioResponse(
        agrupar=agrupar, branch_id=branch_id, ve_costo=ve_costo,
        totales=totales, grupos=grupos,
    )
```

- [ ] **Step 5: Registrar y montar el router**

En `app/routers/__init__.py`, después de `from . import reports`:

```python
from . import reports_valuacion
```

En `app/main.py`, en el bloque de imports (línea 15, la tupla `from app.routers import (...)`) añadir `reports_valuacion` después de `reports,`:

```python
    inventory, sales, cash, customers, reports, reports_valuacion,
```

Y justo después de la línea `app.include_router(reports.router, prefix="/api/reports", tags=["Reportes"])`:

```python
app.include_router(reports_valuacion.router, prefix="/api/reports", tags=["Reportes"])
```

- [ ] **Step 6: Correr las pruebas de totales**

Run: `.venv/bin/python -m pytest -q -p no:warnings tests/test_reports_valor_inventario.py`
Expected: 10 passed.

Si `test_costo_null_*` falla con `TypeError` en el `case`: SQLite devuelve `Numeric` como `Decimal` o `float` según la fila; `_dinero` ya normaliza con `str()`. Si `desc("valor_venta")` falla con "Can't resolve label reference", sustituir por `.order_by(_AGREGADOS[2].desc())`.

- [ ] **Step 7: Correr la suite completa para confirmar que no rompe nada**

Run: `.venv/bin/python -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py`
Expected: mismo conteo de `failed` que `main` (0 según la memoria del 2026-09-28: "baseline rojo ya no existe"); los 10 tests nuevos en `passed`.

- [ ] **Step 8: Commit**

```bash
git add app/routers/reports_valuacion.py app/schemas/reports.py app/routers/__init__.py app/main.py tests/test_reports_valor_inventario.py
git commit -m "feat(reportes): valor de la tienda — GET /api/reports/valor-inventario con totales a venta y a costo

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 2: Agrupación por sucursal, departamento y marca

**Files:**
- Modify: `app/routers/reports_valuacion.py` (solo si algún test de esta tarea falla; el código de agrupación ya quedó en Task 1)
- Test: `tests/test_reports_valor_inventario.py` (añadir al final)

**Interfaces:**
- Consumes: el endpoint de Task 1 con `agrupar=sucursal|departamento|marca`.
- Produces: contrato de `grupos` que usa el frontend (Task 6): orden descendente por `valor_venta`; `clave` = id como texto (`"12"` para sucursal, UUID para departamento/marca) o `""` cuando el producto no tiene ese dato; `nombre` = `"Sin departamento"` / `"Sin marca"` en ese caso; `agrupar` inválido → 422.

- [ ] **Step 1: Escribir las pruebas de agrupación**

Añadir al final de `tests/test_reports_valor_inventario.py`:

```python
# ---------------------------------------------------------------- agrupacion

def _grupo(body, nombre):
    return next(g for g in body["grupos"] if g["nombre"] == nombre)


def test_agrupar_por_sucursal_es_el_default_y_ordena_por_valor_venta(client, auth_admin, branch_a, branch_b, tienda):
    body = client.get(URL, headers=auth_admin).json()
    assert body["agrupar"] == "sucursal"
    assert [g["nombre"] for g in body["grupos"]] == ["Sucursal A", "Sucursal B"]
    a = _grupo(body, "Sucursal A")
    assert a["clave"] == str(branch_a.id)
    assert a == {
        "clave": str(branch_a.id), "nombre": "Sucursal A",
        "piezas": 7.0, "skus": 2, "valor_venta": 6200.0, "valor_costo": 1200.0,
        "piezas_sin_costo": 4.0,
    }
    b = _grupo(body, "Sucursal B")
    assert b["clave"] == str(branch_b.id)
    assert (b["piezas"], b["valor_venta"], b["valor_costo"], b["piezas_sin_costo"]) == (12.0, 4000.0, 800.0, 10.0)


def test_agrupar_departamento_incluye_sin_departamento(client, auth_admin, tienda):
    body = client.get(URL, params={"agrupar": "departamento"}, headers=auth_admin).json()
    assert body["agrupar"] == "departamento"
    assert [g["nombre"] for g in body["grupos"]] == ["Bolsas", "Zapatos", "Sin departamento"]
    assert _grupo(body, "Bolsas")["clave"] == tienda["dept_bolsas"].id
    assert _grupo(body, "Bolsas")["valor_venta"] == 5000.0
    assert _grupo(body, "Bolsas")["valor_costo"] == 2000.0
    assert _grupo(body, "Zapatos")["piezas_sin_costo"] == 4.0
    sin = _grupo(body, "Sin departamento")
    assert sin["clave"] == ""
    assert sin["piezas"] == 10.0
    assert sin["valor_venta"] == 2000.0
    # La suma de los grupos cuadra con los totales: nada se pierde por faltar el dato.
    assert sum(g["valor_venta"] for g in body["grupos"]) == body["totales"]["valor_venta"]


def test_agrupar_marca_incluye_sin_marca(client, auth_admin, tienda):
    body = client.get(URL, params={"agrupar": "marca"}, headers=auth_admin).json()
    assert [g["nombre"] for g in body["grupos"]] == ["Sin marca", "Gucci"]
    gucci = _grupo(body, "Gucci")
    assert gucci["clave"] == tienda["marca_gucci"].id
    assert (gucci["piezas"], gucci["valor_venta"]) == (5.0, 5000.0)
    sin = _grupo(body, "Sin marca")
    assert sin["clave"] == ""
    assert (sin["piezas"], sin["valor_venta"], sin["piezas_sin_costo"]) == (14.0, 5200.0, 14.0)


def test_agrupar_con_filtro_de_sucursal(client, auth_admin, branch_a, tienda):
    body = client.get(URL, params={"agrupar": "departamento", "branch_id": branch_a.id}, headers=auth_admin).json()
    assert [g["nombre"] for g in body["grupos"]] == ["Zapatos", "Bolsas"]
    assert _grupo(body, "Bolsas")["piezas"] == 3.0


def test_agrupar_invalido_es_422(client, auth_admin, tienda):
    r = client.get(URL, params={"agrupar": "color"}, headers=auth_admin)
    assert r.status_code == 422, r.text
```

- [ ] **Step 2: Correr las pruebas de agrupación**

Run: `.venv/bin/python -m pytest -q -p no:warnings tests/test_reports_valor_inventario.py -k agrupar`
Expected: 5 passed (la agrupación quedó implementada en Task 1; esta tarea la fija con pruebas). Si `test_agrupar_marca_*` falla por el orden (`["Gucci", "Sin marca"]`): "Sin marca" suma 5200 > 5000 de Gucci, el orden esperado es correcto; revisar que `order_by(desc("valor_venta"))` esté aplicado en la consulta de grupos.

- [ ] **Step 3: Commit**

```bash
git add tests/test_reports_valor_inventario.py app/routers/reports_valuacion.py
git commit -m "test(reportes): valor de la tienda agrupado por sucursal, departamento y marca

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 3: Guard de roles — gerente limitado, cajero 403

**Files:**
- Modify: `app/routers/reports_valuacion.py` (solo si algún test falla; `_ambito` quedó en Task 1)
- Test: `tests/test_reports_valor_inventario.py` (añadir al final)

**Interfaces:**
- Consumes: `_ambito(current_user)` de Task 1; fixtures `auth_gerente_a`, `auth_cajero_a`, `auth_vendedor_sin_sucursal`, `auth_superadmin` de `tests/conftest.py`; `_make_user`/`_auth_header` importados de `conftest`.
- Produces: contrato de roles que el frontend asume (Task 5 y 6): `ve_costo=false` y `valor_costo=null` para el gerente; `branch_id` en la respuesta es la sucursal del gerente aunque mande otra; 403 para cajero/vendedor.

- [ ] **Step 1: Escribir las pruebas de roles**

Añadir al final de `tests/test_reports_valor_inventario.py`:

```python
# ---------------------------------------------------------------- roles

def test_gerente_ve_su_sucursal_sin_costos(client, auth_gerente_a, branch_a, tienda):
    body = client.get(URL, params={"agrupar": "departamento"}, headers=auth_gerente_a).json()
    assert body["ve_costo"] is False
    assert body["branch_id"] == branch_a.id
    t = body["totales"]
    assert (t["piezas"], t["skus"], t["valor_venta"]) == (7.0, 2, 6200.0)
    assert t["valor_costo"] is None
    # El hueco de costos si lo ve: es "que falta capturar", no dinero.
    assert t["piezas_sin_costo"] == 4.0
    assert all(g["valor_costo"] is None for g in body["grupos"])
    assert [g["nombre"] for g in body["grupos"]] == ["Zapatos", "Bolsas"]


def test_gerente_no_puede_mirar_otra_sucursal(client, auth_gerente_a, branch_a, branch_b, tienda):
    body = client.get(URL, params={"branch_id": branch_b.id}, headers=auth_gerente_a).json()
    assert body["branch_id"] == branch_a.id
    assert body["totales"]["valor_venta"] == 6200.0


def test_gerente_sin_sucursal_403(client, db, org, tienda):
    gerente = _make_user(db, org, None, "gerente_sin_sucursal", Role.GERENTE)
    r = client.get(URL, headers=_auth_header(gerente))
    assert r.status_code == 403, r.text
    assert "sucursal" in r.json()["detail"].lower()


def test_cajero_403(client, auth_cajero_a, tienda):
    r = client.get(URL, headers=auth_cajero_a)
    assert r.status_code == 403, r.text


def test_vendedor_sin_sucursal_403(client, auth_vendedor_sin_sucursal, tienda):
    r = client.get(URL, headers=auth_vendedor_sin_sucursal)
    assert r.status_code == 403, r.text


def test_dueno_ve_costos(client, db, org, hq_branch, tienda):
    dueno = _make_user(db, org, hq_branch, "dueno_test", Role.DUEÑO)
    body = client.get(URL, headers=_auth_header(dueno)).json()
    assert body["ve_costo"] is True
    assert body["totales"]["valor_costo"] == 2000.0


def test_superadmin_ve_costos_con_header_de_org(client, auth_superadmin, org, tienda):
    r = client.get(URL, headers={**auth_superadmin, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    assert r.json()["totales"]["valor_costo"] == 2000.0
```

- [ ] **Step 2: Correr las pruebas de roles**

Run: `.venv/bin/python -m pytest -q -p no:warnings tests/test_reports_valor_inventario.py -k "gerente or cajero or vendedor or dueno or superadmin"`
Expected: 7 passed. Si `test_superadmin_*` responde 400 "No active organization": el superadmin de `conftest` tiene membresía en `org`, pero `get_current_active_organization` exige header explícito para SUPERADMIN; el header ya va en la prueba — revisar que no se haya omitido.

- [ ] **Step 3: Correr el archivo completo**

Run: `.venv/bin/python -m pytest -q -p no:warnings tests/test_reports_valor_inventario.py`
Expected: 22 passed.

- [ ] **Step 4: Commit**

```bash
git add tests/test_reports_valor_inventario.py app/routers/reports_valuacion.py
git commit -m "test(reportes): valor de la tienda — gerente solo su sucursal sin costos, cajero 403

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 4: Llamada tipada en `frontend/src/api/reports.ts`

**Files:**
- Modify: `frontend/src/api/reports.ts` (tipos después de `AuditDiscrepancy`; método al final de `reportsApi`, después de `exportCsv`)

**Interfaces:**
- Consumes: `client` (axios con `/api` y headers de sesión).
- Produces: tipos `AgruparValuacion`, `ValuacionTotales`, `ValuacionGrupo`, `ValuacionInventario` y `reportsApi.valorInventario(params?: { agrupar?: AgruparValuacion; branch_id?: number }): Promise<ValuacionInventario>`. Los usan Task 5 (tarjeta), Task 6 (página y CSV).

- [ ] **Step 1: Añadir los tipos**

En `frontend/src/api/reports.ts`, después de la interfaz `AuditDiscrepancy`:

```ts
// --- Valor de la tienda (GET /reports/valor-inventario) ---------------------
export type AgruparValuacion = 'sucursal' | 'departamento' | 'marca'

export interface ValuacionTotales {
  piezas: number
  skus: number
  valor_venta: number
  /** null cuando el rol no ve costos (gerente). */
  valor_costo: number | null
  piezas_sin_costo: number
  skus_sin_costo: number
}

export interface ValuacionGrupo {
  /** id de sucursal/departamento/marca como texto; '' = sin asignar. */
  clave: string
  nombre: string
  piezas: number
  skus: number
  valor_venta: number
  valor_costo: number | null
  piezas_sin_costo: number
}

export interface ValuacionInventario {
  agrupar: AgruparValuacion
  /** Sucursal consultada; null = todas las que venden. El gerente siempre recibe la suya. */
  branch_id: number | null
  ve_costo: boolean
  totales: ValuacionTotales
  grupos: ValuacionGrupo[]
}
```

- [ ] **Step 2: Añadir la llamada**

Dentro de `reportsApi`, después del método `exportCsv`:

```ts
  valorInventario: async (
    params: { agrupar?: AgruparValuacion; branch_id?: number } = {},
  ): Promise<ValuacionInventario> => {
    const { data } = await client.get<ValuacionInventario>('/reports/valor-inventario', { params })
    return data
  },
```

- [ ] **Step 3: Verificar que compila**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: sin errores (salida vacía).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/reports.ts
git commit -m "feat(frontend): reportsApi.valorInventario tipado

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 5: Tarjeta "Valor de la tienda" en el inicio del dueño

**Files:**
- Create: `frontend/src/components/reports/ValorTiendaCard.tsx`
- Create: `frontend/src/components/reports/__tests__/ValorTiendaCard.test.tsx`
- Modify: `frontend/src/pages/hq/HQOperations.tsx` (imports líneas 9-10; estado junto a `const [stats, …]`; render después del cierre de la rejilla KPI, línea ~543, antes del comentario `{/* Charts + Branch Matrix */}`)

**Interfaces:**
- Consumes: `reportsApi.valorInventario` y `ValuacionInventario` (Task 4); `formatCurrency` de `utils/currency`; `errorDetailText` de `utils/errorDetail`.
- Produces: `ValorTiendaCard(props: ValorTiendaCardProps)` con `{ valorVenta: number; valorCosto: number | null; piezas: number; piezasSinCosto: number; skusSinCosto: number; cargando?: boolean; error?: string | null }`. Regla: si `valorCosto` es `null` o hay `piezasSinCosto > 0`, la cifra grande es la de venta y el costo (si se ve) baja a secundaria con el aviso; si el costo está completo, la cifra grande es el costo y la venta queda al lado. `data-testid="valor-principal"` lleva la cifra grande.

- [ ] **Step 1: Escribir el test del componente (falla: el módulo no existe)**

Crear `frontend/src/components/reports/__tests__/ValorTiendaCard.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ValorTiendaCard, type ValorTiendaCardProps } from '../ValorTiendaCard'

afterEach(cleanup)

const base: ValorTiendaCardProps = {
  valorVenta: 10200, valorCosto: 2000, piezas: 19, piezasSinCosto: 14, skusSinCosto: 2,
}
const pinta = (props: Partial<ValorTiendaCardProps> = {}) =>
  render(<MemoryRouter><ValorTiendaCard {...base} {...props} /></MemoryRouter>)

describe('ValorTiendaCard', () => {
  it('con piezas sin costo la cifra grande es la de venta y avisa cuántas faltan', () => {
    pinta()
    expect(screen.getByTestId('valor-principal').textContent).toBe('$10,200.00')
    expect(screen.getByText('Valor a precio de venta')).toBeTruthy()
    expect(screen.getByTestId('valor-costo').textContent).toBe('$2,000.00')
    expect(screen.getByRole('status').textContent).toContain('14 piezas sin costo')
    expect(screen.getByRole('status').textContent).toContain('2 SKUs')
  })

  it('con costo completo la cifra grande es el costo y la venta queda al lado', () => {
    pinta({ piezasSinCosto: 0, skusSinCosto: 0 })
    expect(screen.getByTestId('valor-principal').textContent).toBe('$2,000.00')
    expect(screen.getByText('Valor a costo')).toBeTruthy()
    expect(screen.getByTestId('valor-venta').textContent).toBe('$10,200.00')
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('sin costo visible (gerente) solo muestra venta y piezas, sin aviso', () => {
    pinta({ valorCosto: null })
    expect(screen.getByTestId('valor-principal').textContent).toBe('$10,200.00')
    expect(screen.queryByTestId('valor-costo')).toBeNull()
    expect(screen.queryByRole('status')).toBeNull()
    expect(screen.getByText('19 piezas')).toBeTruthy()
  })

  it('una sola pieza va en singular', () => {
    pinta({ piezas: 1, piezasSinCosto: 1, skusSinCosto: 1 })
    expect(screen.getByText('1 pieza')).toBeTruthy()
    expect(screen.getByRole('status').textContent).toContain('1 pieza sin costo (1 SKU)')
  })

  it('enlaza al desglose', () => {
    pinta()
    const link = screen.getByRole('link', { name: /ver desglose/i })
    expect(link.getAttribute('href')).toBe('/hq/valor-inventario')
  })

  it('el error gana a los números y cargando no pinta cifras', () => {
    pinta({ error: 'No se pudo calcular el valor de la tienda.' })
    expect(screen.getByText('No se pudo calcular el valor de la tienda.')).toBeTruthy()
    expect(screen.queryByTestId('valor-principal')).toBeNull()
    cleanup()
    pinta({ cargando: true })
    expect(screen.getByText('Calculando…')).toBeTruthy()
    expect(screen.queryByTestId('valor-principal')).toBeNull()
  })
})
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `cd frontend && npx vitest run src/components/reports/__tests__/ValorTiendaCard.test.tsx`
Expected: FAIL — `Failed to resolve import "../ValorTiendaCard"`.

- [ ] **Step 3: Crear el componente**

Crear `frontend/src/components/reports/ValorTiendaCard.tsx`:

```tsx
import { Link } from 'react-router-dom'
import { formatCurrency } from '../../utils/currency'

/**
 * ValorTiendaCard — "¿cuánto vale mi tienda hoy?" en el inicio del dueño.
 *
 * Dos cifras que SIEMPRE van juntas: valor a precio de venta (completo) y
 * valor a costo (solo SKUs con costo > 0). Si hay piezas sin costo, el costo
 * está incompleto: la cifra grande es la de venta y el costo baja a
 * secundaria con el aviso "N piezas sin costo", para que un catálogo
 * importado sin costos nunca se lea como "mi tienda vale $0". Con el costo
 * completo, la cifra grande es el costo (lo invertido) y la venta queda al
 * lado. `valorCosto === null` = el rol no ve costos (gerente): venta y piezas.
 */
export interface ValorTiendaCardProps {
  valorVenta: number
  valorCosto: number | null
  piezas: number
  piezasSinCosto: number
  skusSinCosto: number
  cargando?: boolean
  error?: string | null
}

const piezasTxt = (n: number) => {
  const r = Math.round(n)
  return `${r.toLocaleString('es-MX')} ${r === 1 ? 'pieza' : 'piezas'}`
}

export function ValorTiendaCard({
  valorVenta, valorCosto, piezas, piezasSinCosto, skusSinCosto, cargando = false, error = null,
}: ValorTiendaCardProps) {
  const costoIncompleto = piezasSinCosto > 0
  const costoPrincipal = valorCosto !== null && !costoIncompleto
  const principal = costoPrincipal ? (valorCosto as number) : valorVenta
  const etiquetaPrincipal = costoPrincipal ? 'Valor a costo' : 'Valor a precio de venta'

  return (
    <section
      className="dax-card p-5 rounded-2xl border-t-2 border-t-amber-500/50 relative overflow-hidden"
      aria-label="Valor de la tienda"
      data-testid="valor-tienda"
    >
      <div className="flex justify-between items-start gap-2 mb-1">
        <p className="text-[10px] font-black uppercase text-slate-500 tracking-widest">Valor de la tienda</p>
        <Link to="/hq/valor-inventario" className="text-[10px] font-bold text-amber-400 hover:underline whitespace-nowrap">
          Ver desglose →
        </Link>
      </div>
      {error ? (
        <p className="text-sm text-rose-300">{error}</p>
      ) : cargando ? (
        <p className="text-sm text-slate-500">Calculando…</p>
      ) : (
        <>
          <p className="text-[9px] uppercase tracking-wider text-slate-500">{etiquetaPrincipal}</p>
          <h2 className="text-2xl md:text-3xl font-bold text-white tabular-nums" data-testid="valor-principal">
            {formatCurrency(principal)}
          </h2>
          <div className="mt-1 flex flex-wrap justify-between gap-x-3 gap-y-1 text-xs font-mono">
            <span className="text-slate-400">{piezasTxt(piezas)}</span>
            {valorCosto !== null && !costoPrincipal && (
              <span className="text-slate-400">
                A costo: <span className="text-white font-bold tabular-nums" data-testid="valor-costo">{formatCurrency(valorCosto)}</span>
              </span>
            )}
            {costoPrincipal && (
              <span className="text-slate-400">
                A venta: <span className="text-white font-bold tabular-nums" data-testid="valor-venta">{formatCurrency(valorVenta)}</span>
              </span>
            )}
          </div>
          {costoIncompleto && valorCosto !== null && (
            <p className="mt-1 text-[10px] font-bold text-amber-400" role="status">
              {piezasTxt(piezasSinCosto)} sin costo ({skusSinCosto} {skusSinCosto === 1 ? 'SKU' : 'SKUs'}): el valor a costo está incompleto.
            </p>
          )}
        </>
      )}
    </section>
  )
}

export default ValorTiendaCard
```

- [ ] **Step 4: Correr el test del componente**

Run: `cd frontend && npx vitest run src/components/reports/__tests__/ValorTiendaCard.test.tsx`
Expected: 6 passed.

- [ ] **Step 5: Cargar la valuación en `HQOperations` y pintar la tarjeta**

En `frontend/src/pages/hq/HQOperations.tsx`:

Reemplazar la línea 9:
```ts
import { reportsApi, type CommandCenterStats } from '../../api/reports'
```
por:
```ts
import { reportsApi, type CommandCenterStats, type ValuacionInventario } from '../../api/reports'
```

Después de la línea 10 (`import { KPICard } …`) añadir:
```ts
import { ValorTiendaCard } from '../../components/reports/ValorTiendaCard'
```

Junto a los demás `useState` del componente (donde está `const [branchSearch, setBranchSearch] = useState('')`), añadir:
```ts
  // Valor de la tienda: se calcula aparte del command center y una sola vez
  // por visita (la existencia no cambia cada 60 s como las ventas).
  const [valuacion, setValuacion] = useState<ValuacionInventario | null>(null)
  const [valuacionError, setValuacionError] = useState<string | null>(null)
```

Después del `useEffect` que registra `visibilitychange` (el que termina en `}, [load])`), añadir:
```ts
  useEffect(() => {
    reportsApi.valorInventario({ agrupar: 'sucursal' })
      .then((v) => { setValuacion(v); setValuacionError(null) })
      .catch((e: any) => setValuacionError(errorDetailText(
        e?.response?.data?.detail,
        'No se pudo calcular el valor de la tienda. Vuelve a intentar en unos segundos.',
      )))
  }, [])
```

En el JSX, localizar el cierre de la rejilla KPI (el `</div>` que sigue al `</Link>` de "Alertas Críticas", justo antes de `{/* Charts + Branch Matrix */}`) e insertar entre ambos:
```tsx
          {/* Valor de la tienda (SP3): dos cifras + hueco de costos. Media
              anchura en escritorio; SP7 decidirá su lugar definitivo. */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <ValorTiendaCard
              valorVenta={valuacion?.totales.valor_venta ?? 0}
              valorCosto={valuacion ? valuacion.totales.valor_costo : null}
              piezas={valuacion?.totales.piezas ?? 0}
              piezasSinCosto={valuacion?.totales.piezas_sin_costo ?? 0}
              skusSinCosto={valuacion?.totales.skus_sin_costo ?? 0}
              cargando={!valuacion && !valuacionError}
              error={valuacionError}
            />
          </div>
```

- [ ] **Step 6: Verificar tipos y suite de vitest**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json && npx vitest run`
Expected: `tsc` sin errores; vitest con todos los archivos en verde (los 6 nuevos incluidos).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/reports/ValorTiendaCard.tsx frontend/src/components/reports/__tests__/ValorTiendaCard.test.tsx frontend/src/pages/hq/HQOperations.tsx
git commit -m "feat(frontend): tarjeta Valor de la tienda en el inicio del dueño

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 6: Página `/hq/valor-inventario` con desglose, filtro y CSV

**Files:**
- Create: `frontend/src/utils/valuacionCsv.ts`
- Create: `frontend/src/utils/valuacionCsv.test.ts`
- Create: `frontend/src/pages/hq/HQValorInventario.tsx`
- Modify: `frontend/src/components/layout/navConfig.ts` (`HQ_NAV_GROUPS` línea 38, `BRANCH_NAV_GROUPS` línea 25, `ALL_NAV` después de la línea 82, `ROLE_ROUTES` líneas 149-151)
- Modify: `frontend/src/components/layout/__tests__/navConfig.test.ts` (añadir un `describe` al final)
- Modify: `frontend/src/App.tsx` (lazy después de la línea 31; ruta después de la línea 276)

**Interfaces:**
- Consumes: `reportsApi.valorInventario`, tipos de Task 4; `organizationApi.getBranches(): Promise<Branch[]>` (`Branch { id, name, can_sell?, is_active }` de `api/organization.ts`); `useAuthStore((s) => s.user)` (`user.role: Role`); `useEsTelefono()` de `hooks/useIsMobile`; kit `ui/`: `CabeceraPagina`, `BarraFiltros`, `TarjetaFila`, `ListaTarjetas`, `Spinner`.
- Produces: `csvValuacion(d: ValuacionInventario): string`, `descargarCsv(csv: string, nombre: string): void`, `ETIQUETA_GRUPO: Record<AgruparValuacion, string>`; componente `HQValorInventario`; ruta `/hq/valor-inventario` visible para ADMINISTRADOR, DUEÑO y GERENTE con módulo `reports`.

- [ ] **Step 1: Escribir el test de la función CSV (falla: el módulo no existe)**

Crear `frontend/src/utils/valuacionCsv.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { csvValuacion } from './valuacionCsv'
import type { ValuacionInventario } from '../api/reports'

const base: ValuacionInventario = {
  agrupar: 'marca', branch_id: null, ve_costo: true,
  totales: { piezas: 19, skus: 3, valor_venta: 10200, valor_costo: 2000, piezas_sin_costo: 14, skus_sin_costo: 2 },
  grupos: [
    { clave: '', nombre: 'Sin marca', piezas: 14, skus: 2, valor_venta: 5200, valor_costo: 0, piezas_sin_costo: 14 },
    { clave: 'abc', nombre: 'Dolce, Gabbana', piezas: 5, skus: 1, valor_venta: 5000, valor_costo: 2000, piezas_sin_costo: 0 },
  ],
}

const lineas = (csv: string) => csv.replace(/^﻿/, '').split('\r\n')

describe('csvValuacion', () => {
  it('empieza con BOM para que Excel lea UTF-8', () => {
    expect(csvValuacion(base).charCodeAt(0)).toBe(0xfeff)
  })

  it('cabecera según el criterio, una fila por grupo y TOTAL al final', () => {
    const l = lineas(csvValuacion(base))
    expect(l[0]).toBe('Marca,Piezas,SKUs,Valor a venta,Valor a costo,Piezas sin costo')
    expect(l[1]).toBe('Sin marca,14,2,5200.00,0.00,14')
    expect(l[3]).toBe('TOTAL,19,3,10200.00,2000.00,14')
    expect(l).toHaveLength(4)
  })

  it('entrecomilla nombres con coma o comillas', () => {
    const l = lineas(csvValuacion(base))
    expect(l[2]).toBe('"Dolce, Gabbana",5,1,5000.00,2000.00,0')
    const conComillas = { ...base, grupos: [{ ...base.grupos[1], nombre: 'Bolsa "XL"' }] }
    expect(lineas(csvValuacion(conComillas))[1]).toBe('"Bolsa ""XL""",5,1,5000.00,2000.00,0')
  })

  it('sin ve_costo no hay columna de costo (el gerente no exporta lo que no ve)', () => {
    const gerente: ValuacionInventario = {
      ...base, agrupar: 'departamento', ve_costo: false,
      totales: { ...base.totales, valor_costo: null },
      grupos: base.grupos.map((g) => ({ ...g, valor_costo: null })),
    }
    const l = lineas(csvValuacion(gerente))
    expect(l[0]).toBe('Departamento,Piezas,SKUs,Valor a venta,Piezas sin costo')
    expect(l[1]).toBe('Sin marca,14,2,5200.00,14')
    expect(l[3]).toBe('TOTAL,19,3,10200.00,14')
  })
})
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `cd frontend && npx vitest run src/utils/valuacionCsv.test.ts`
Expected: FAIL — `Failed to resolve import "./valuacionCsv"`.

- [ ] **Step 3: Crear la utilería CSV**

Crear `frontend/src/utils/valuacionCsv.ts`:

```ts
import type { AgruparValuacion, ValuacionInventario } from '../api/reports'

export const ETIQUETA_GRUPO: Record<AgruparValuacion, string> = {
  sucursal: 'Sucursal',
  departamento: 'Departamento',
  marca: 'Marca',
}

/** Celda CSV: comillas si trae coma, comilla o salto de línea (RFC 4180). */
function celda(v: string | number): string {
  const s = typeof v === 'number' ? String(v) : v
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

/**
 * CSV del desglose + fila TOTAL. Números crudos (sin "$" ni separador de
 * miles) para que Excel los sume. Sin la columna de costo cuando el rol no
 * la ve (`ve_costo=false`): un gerente no exporta lo que no ve en pantalla.
 * Empieza con BOM: sin él Excel en Windows lee los acentos como basura.
 */
export function csvValuacion(d: ValuacionInventario): string {
  const cabecera = [ETIQUETA_GRUPO[d.agrupar], 'Piezas', 'SKUs', 'Valor a venta']
  if (d.ve_costo) cabecera.push('Valor a costo')
  cabecera.push('Piezas sin costo')

  const fila = (nombre: string, piezas: number, skus: number, venta: number, costo: number | null, sinCosto: number) => {
    const cols: (string | number)[] = [nombre, piezas, skus, venta.toFixed(2)]
    if (d.ve_costo) cols.push((costo ?? 0).toFixed(2))
    cols.push(sinCosto)
    return cols.map(celda).join(',')
  }

  const lineas = [cabecera.map(celda).join(',')]
  for (const g of d.grupos) {
    lineas.push(fila(g.nombre, g.piezas, g.skus, g.valor_venta, g.valor_costo, g.piezas_sin_costo))
  }
  const t = d.totales
  lineas.push(fila('TOTAL', t.piezas, t.skus, t.valor_venta, t.valor_costo, t.piezas_sin_costo))
  return '﻿' + lineas.join('\r\n')
}

/** Descarga `csv` como archivo (mismo mecanismo que `reportsApi.exportCsv`). */
export function descargarCsv(csv: string, nombre: string): void {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = nombre
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
```

- [ ] **Step 4: Correr el test del CSV**

Run: `cd frontend && npx vitest run src/utils/valuacionCsv.test.ts`
Expected: 4 passed.

- [ ] **Step 5: Escribir el test de navegación (falla: la ruta no está en `ROLE_ROUTES`)**

Añadir al final de `frontend/src/components/layout/__tests__/navConfig.test.ts` (reutiliza `menu`, `BOUTIQUE` y `rolesConAcceso` ya definidos arriba en ese archivo):

```ts
describe('Valor de la tienda (/hq/valor-inventario)', () => {
  it('lo ven administrador, dueño y gerente con el módulo reports', () => {
    expect(menu('ADMINISTRADOR', BOUTIQUE)).toContain('/hq/valor-inventario')
    expect(menu('DUEÑO', BOUTIQUE)).toContain('/hq/valor-inventario')
    expect(menu('GERENTE', BOUTIQUE)).toContain('/hq/valor-inventario')
    expect(rolesConAcceso('/hq/valor-inventario')).toEqual(
      expect.arrayContaining(['ADMINISTRADOR', 'DUEÑO', 'GERENTE']),
    )
  })

  it('la cajera no lo ve ni lo abre por URL', () => {
    expect(menu('CAJERO', BOUTIQUE)).not.toContain('/hq/valor-inventario')
    expect(rolesConAcceso('/hq/valor-inventario')).not.toContain('CAJERO')
  })

  it('depende del módulo reports (módulo base: lo tienen FREE y ULTRA+)', () => {
    const sinReports = BOUTIQUE.filter((m) => m !== 'reports')
    expect(menu('ADMINISTRADOR', sinReports)).not.toContain('/hq/valor-inventario')
  })

  it('tiene título para la barra superior y cae en el grupo Operación del menú HQ', () => {
    expect(ROUTE_TITLES['/hq/valor-inventario']).toBe('Valor de la tienda')
    const operacion = HQ_NAV_GROUPS.find((g) => g.header === 'Operación')
    expect(operacion?.urls).toContain('/hq/valor-inventario')
  })
})
```

- [ ] **Step 6: Correr el test de navegación para verificar que falla**

Run: `cd frontend && npx vitest run src/components/layout/__tests__/navConfig.test.ts`
Expected: los 4 tests nuevos FAIL (`expected [...] to include '/hq/valor-inventario'`); los anteriores siguen en verde.

- [ ] **Step 7: Declarar la entrada de menú, los grupos y las rutas por rol**

En `frontend/src/components/layout/navConfig.ts`:

Línea 25 (`BRANCH_NAV_GROUPS`, grupo Reportes — el menú del gerente), reemplazar:
```ts
  { header: 'Reportes',      urls: ['/reports', '/meseros'] },
```
por:
```ts
  { header: 'Reportes',      urls: ['/reports', '/hq/valor-inventario', '/meseros'] },
```

Línea 38 (`HQ_NAV_GROUPS`, grupo Operación), reemplazar:
```ts
  { header: 'Operación',    urls: ['/hq/operations', '/hq/reports-hub', '/hq/control'] },
```
por:
```ts
  { header: 'Operación',    urls: ['/hq/operations', '/hq/reports-hub', '/hq/valor-inventario', '/hq/control'] },
```

En `ALL_NAV`, después de la línea de `Reportes` (`url: '/hq/reports-hub'`), añadir:
```ts
  { label: 'Valor de la tienda', short: 'VAL', icon: 'fa-sack-dollar',       url: '/hq/valor-inventario', group: 'hq', sort: 1.5, module: 'reports' },
```

En `ROLE_ROUTES`:
- `ADMINISTRADOR`: insertar `'/hq/valor-inventario'` justo después de `'/hq/reports-hub'`.
- `DUEÑO`: insertar `'/hq/valor-inventario'` justo después de `'/hq/reports-hub'`.
- `GERENTE`: insertar `'/hq/valor-inventario'` justo después de `'/reports'`.

Resultado esperado de las tres líneas (solo cambia la inserción):
```ts
  ADMINISTRADOR:    ['/sales','/products','/printer-settings','/labels','/mobile/owner','/cash-history','/hq/operations','/hq/reports-hub','/hq/valor-inventario','/hq/control', …resto igual…],
  DUEÑO:            ['/pos','/sales','/products','/printer-settings','/labels','/mobile/owner','/cash-history','/hq/operations','/hq/reports-hub','/hq/valor-inventario','/hq/control', …resto igual…],
  GERENTE:          ['/labels','/cash-history','/reports','/hq/valor-inventario','/hr/me', …resto igual…],
```

- [ ] **Step 8: Correr el test de navegación**

Run: `cd frontend && npx vitest run src/components/layout/__tests__/navConfig.test.ts`
Expected: todos passed (4 nuevos incluidos).

- [ ] **Step 9: Crear la página**

Crear `frontend/src/pages/hq/HQValorInventario.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react'
import { reportsApi, type AgruparValuacion, type ValuacionInventario } from '../../api/reports'
import { organizationApi, type Branch } from '../../api/organization'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { BarraFiltros } from '../../components/ui/BarraFiltros'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { Spinner } from '../../components/ui/Spinner'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { useAuthStore } from '../../store/authStore'
import { toast } from '../../store/toastStore'
import { formatCurrency } from '../../utils/currency'
import { errorDetailText } from '../../utils/errorDetail'
import { csvValuacion, descargarCsv, ETIQUETA_GRUPO } from '../../utils/valuacionCsv'

/**
 * /hq/valor-inventario — ¿cuánto vale mi existencia hoy, y dónde?
 *
 * Desglose del mismo dato que la tarjeta del inicio: por sucursal,
 * departamento o marca, con filtro de sucursal y exportación CSV armada en
 * el cliente (`utils/valuacionCsv`). El backend decide qué ve cada rol:
 * `ve_costo=false` (gerente) llega sin la columna de costo y ya limitado a su
 * sucursal, así que aquí ni se le ofrece el selector.
 */
const piezasTxt = (n: number) => Math.round(n).toLocaleString('es-MX')

export function HQValorInventario() {
  const user = useAuthStore((s) => s.user)
  const esGerente = user?.role === 'GERENTE'
  const telefono = useEsTelefono()

  const [agrupar, setAgrupar] = useState<AgruparValuacion>('sucursal')
  const [branchId, setBranchId] = useState<number | ''>('')
  const [branches, setBranches] = useState<Branch[]>([])
  const [data, setData] = useState<ValuacionInventario | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (esGerente) return // el gerente solo ve su sucursal: sin selector
    organizationApi.getBranches().then(setBranches).catch(() => {})
  }, [esGerente])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await reportsApi.valorInventario({
        agrupar,
        ...(branchId !== '' ? { branch_id: branchId } : {}),
      })
      setData(res)
      setError(null)
    } catch (e: any) {
      setError(errorDetailText(
        e?.response?.data?.detail,
        'No se pudo calcular el valor de la tienda. Vuelve a intentar en unos segundos.',
      ))
    } finally {
      setLoading(false)
    }
  }, [agrupar, branchId])

  useEffect(() => { load() }, [load])

  const exportar = () => {
    if (!data) { toast.warning('Todavía no hay datos que exportar.'); return }
    const fecha = new Date().toISOString().slice(0, 10)
    descargarCsv(csvValuacion(data), `valor-tienda-${agrupar}-${fecha}.csv`)
  }

  const veCosto = data?.ve_costo ?? false
  const t = data?.totales
  const grupos = data?.grupos ?? []
  const costoIncompleto = (t?.piezas_sin_costo ?? 0) > 0

  return (
    <div className="space-y-4">
      <CabeceraPagina
        titulo={<h1 className="text-2xl font-bold">Valor de la tienda</h1>}
        descripcion="Existencia de hoy a precio de venta y a costo. Sin instantáneas: lo que ves es lo que hay ahora."
        acciones={
          <button type="button" onClick={exportar} disabled={!data || loading} className="dax-btn-secondary">
            <i className="fa-solid fa-file-csv mr-1" aria-hidden="true" /> Exportar CSV
          </button>
        }
      />

      <BarraFiltros accion={<button type="button" onClick={load} className="dax-btn-primary">Actualizar</button>}>
        <label className="flex flex-col text-xs" style={{ color: 'var(--dax-text-muted)' }}>
          Agrupar por
          <select className="dax-input w-44" value={agrupar} onChange={(e) => setAgrupar(e.target.value as AgruparValuacion)}>
            <option value="sucursal">Sucursal</option>
            <option value="departamento">Departamento</option>
            <option value="marca">Marca</option>
          </select>
        </label>
        {!esGerente && (
          <label className="flex flex-col text-xs" style={{ color: 'var(--dax-text-muted)' }}>
            Sucursal
            <select
              className="dax-input w-52"
              value={branchId}
              onChange={(e) => setBranchId(e.target.value === '' ? '' : Number(e.target.value))}
            >
              <option value="">Todas las que venden</option>
              {branches.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}{b.can_sell === false ? ' (no vende)' : ''}
                </option>
              ))}
            </select>
          </label>
        )}
      </BarraFiltros>

      {error && (
        <div className="dax-card rounded-xl border border-rose-500/30 bg-rose-500/5 p-4 flex items-start gap-3">
          <i className="fas fa-triangle-exclamation text-rose-400 mt-0.5" aria-hidden="true" />
          <p className="text-sm text-rose-200 flex-1">{error}</p>
          <button type="button" onClick={load} className="dax-btn-secondary text-xs">Reintentar</button>
        </div>
      )}

      {t && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="dax-card p-4">
            <p className="text-[10px] font-black uppercase tracking-widest" style={{ color: 'var(--dax-text-muted)' }}>Valor a precio de venta</p>
            <p className="text-xl font-bold tabular-nums">{formatCurrency(t.valor_venta)}</p>
          </div>
          {veCosto && (
            <div className="dax-card p-4">
              <p className="text-[10px] font-black uppercase tracking-widest" style={{ color: 'var(--dax-text-muted)' }}>Valor a costo</p>
              <p className="text-xl font-bold tabular-nums">{formatCurrency(t.valor_costo ?? 0)}</p>
              {costoIncompleto && (
                <p className="text-[10px] font-bold text-amber-400">incompleto: faltan costos</p>
              )}
            </div>
          )}
          <div className="dax-card p-4">
            <p className="text-[10px] font-black uppercase tracking-widest" style={{ color: 'var(--dax-text-muted)' }}>Piezas · SKUs</p>
            <p className="text-xl font-bold tabular-nums">{piezasTxt(t.piezas)} · {t.skus}</p>
          </div>
          <div className="dax-card p-4">
            <p className="text-[10px] font-black uppercase tracking-widest" style={{ color: 'var(--dax-text-muted)' }}>Sin costo</p>
            <p className={`text-xl font-bold tabular-nums ${costoIncompleto ? 'text-amber-400' : ''}`}>
              {piezasTxt(t.piezas_sin_costo)} pz · {t.skus_sin_costo} SKU{t.skus_sin_costo === 1 ? '' : 's'}
            </p>
          </div>
        </div>
      )}

      {telefono ? (
        <ListaTarjetas cargando={loading && !data} vacio={grupos.length === 0} textoVacio="Sin existencias que valuar">
          {grupos.map((g) => (
            <TarjetaFila
              key={g.clave || 'sin'}
              titulo={g.nombre}
              subtitulo={`${piezasTxt(g.piezas)} piezas · ${g.skus} SKUs`}
              importe={formatCurrency(g.valor_venta)}
              datos={[
                ...(veCosto ? [{ etiqueta: 'A costo', valor: formatCurrency(g.valor_costo ?? 0) }] : []),
                { etiqueta: 'Sin costo', valor: `${piezasTxt(g.piezas_sin_costo)} pz` },
              ]}
            />
          ))}
        </ListaTarjetas>
      ) : (
        <div className="dax-card overflow-x-auto">
          {loading && !data ? (
            <Spinner text="Calculando…" />
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider" style={{ color: 'var(--dax-text-muted)' }}>
                  <th className="p-3">{ETIQUETA_GRUPO[agrupar]}</th>
                  <th className="p-3 text-right">Piezas</th>
                  <th className="p-3 text-right">SKUs</th>
                  <th className="p-3 text-right">Valor a venta</th>
                  {veCosto && <th className="p-3 text-right">Valor a costo</th>}
                  <th className="p-3 text-right">Piezas sin costo</th>
                </tr>
              </thead>
              <tbody>
                {grupos.length === 0 && (
                  <tr><td colSpan={veCosto ? 6 : 5} className="p-8 text-center" style={{ color: 'var(--dax-text-muted)' }}>Sin existencias que valuar</td></tr>
                )}
                {grupos.map((g) => (
                  <tr key={g.clave || 'sin'} style={{ borderTop: '1px solid var(--dax-border-dim)' }}>
                    <td className="p-3 font-medium">{g.nombre}</td>
                    <td className="p-3 text-right tabular-nums">{piezasTxt(g.piezas)}</td>
                    <td className="p-3 text-right tabular-nums">{g.skus}</td>
                    <td className="p-3 text-right tabular-nums">{formatCurrency(g.valor_venta)}</td>
                    {veCosto && <td className="p-3 text-right tabular-nums">{formatCurrency(g.valor_costo ?? 0)}</td>}
                    <td className={`p-3 text-right tabular-nums ${g.piezas_sin_costo > 0 ? 'text-amber-400' : ''}`}>{piezasTxt(g.piezas_sin_costo)}</td>
                  </tr>
                ))}
              </tbody>
              {t && grupos.length > 0 && (
                <tfoot>
                  <tr className="font-bold" style={{ borderTop: '2px solid var(--dax-border-dim)' }}>
                    <td className="p-3">Total</td>
                    <td className="p-3 text-right tabular-nums">{piezasTxt(t.piezas)}</td>
                    <td className="p-3 text-right tabular-nums">{t.skus}</td>
                    <td className="p-3 text-right tabular-nums">{formatCurrency(t.valor_venta)}</td>
                    {veCosto && <td className="p-3 text-right tabular-nums">{formatCurrency(t.valor_costo ?? 0)}</td>}
                    <td className="p-3 text-right tabular-nums">{piezasTxt(t.piezas_sin_costo)}</td>
                  </tr>
                </tfoot>
              )}
            </table>
          )}
        </div>
      )}
    </div>
  )
}

export default HQValorInventario
```

- [ ] **Step 10: Registrar la ruta lazy en `App.tsx`**

Después de la línea 31 (`const HQBranchDetail = lazy(…)`) añadir:
```ts
const HQValorInventario = lazy(() => import('./pages/hq/HQValorInventario').then(m => ({ default: m.HQValorInventario })))
```

Después de la línea 276 (`<Route path="inventory" …HQInventory… />`) añadir:
```tsx
            <Route path="valor-inventario" element={<RutaPorRol url="/hq/valor-inventario"><Suspense fallback={<PageLoader />}><HQValorInventario /></Suspense></RutaPorRol>} />
```

`RutaPorRol` deriva los roles permitidos de `ROLE_ROUTES` (Step 7), así que el gerente entra y la cajera es redirigida a `/`.

- [ ] **Step 11: Verificar tipos, suite de vitest y build**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json && npx vitest run && npm run build`
Expected: `tsc` sin errores; vitest en verde; `vite build` termina con la lista de chunks (incluye uno nuevo `HQValorInventario-*.js`).

- [ ] **Step 12: Prueba manual en el navegador**

Con el backend corriendo (`uvicorn app.main:app --reload`) y `npm run dev`:
1. Entrar como administrador → `/hq/operations`: la tarjeta "Valor de la tienda" muestra una cifra grande y el enlace "Ver desglose →".
2. Abrir `/hq/valor-inventario`: cambiar "Agrupar por" recarga la tabla; elegir una sucursal recalcula; "Exportar CSV" descarga `valor-tienda-<criterio>-<fecha>.csv` que abre en Excel con columnas separadas.
3. Entrar como gerente: la entrada "Valor de la tienda" aparece en el grupo Reportes; la página no muestra selector de sucursal ni columna de costo.
4. Entrar como cajera: la URL `/hq/valor-inventario` redirige a `/`.

- [ ] **Step 13: Commit**

```bash
git add frontend/src/utils/valuacionCsv.ts frontend/src/utils/valuacionCsv.test.ts frontend/src/pages/hq/HQValorInventario.tsx frontend/src/components/layout/navConfig.ts frontend/src/components/layout/__tests__/navConfig.test.ts frontend/src/App.tsx
git commit -m "feat(frontend): página /hq/valor-inventario con desglose, filtro por sucursal y CSV

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 7: Documentación

**Files:**
- Modify: `docs/API_REFERENCE.md` (tabla de `## Reportes · /api/reports`, líneas 141-146)
- Modify: `docs/FRONTEND_VIEWS.md` (tabla de rutas, después de la fila `/hq/inventory` línea 61; sección `### /hq/inventory`, después de su bloque, línea ~278)

**Interfaces:**
- Consumes: el contrato final de Task 1-3 y la vista de Task 6.
- Produces: documentación consistente con el código (CLAUDE.md: "si algo contradice al código, gana el código").

- [ ] **Step 1: Documentar el endpoint**

En `docs/API_REFERENCE.md`, añadir una fila a la tabla de Reportes, después de la fila de `/audit/discrepancies · /aging-report · /product/{id} · /export/csv`:

```markdown
| **/valor-inventario** `?branch_id=&agrupar=sucursal\|departamento\|marca` | Valor de la tienda (2026-10): `totales {piezas, skus, valor_venta, valor_costo, piezas_sin_costo, skus_sin_costo}` + `grupos[]` ordenados por `valor_venta`. Σ existencia × precio (completo) y Σ existencia × costo **solo de variantes con costo > 0**; costo NULL/0 cuenta como "sin costo". Sin borrados (`deleted_at`), sin existencias ≤ 0; sin `branch_id` solo sucursales `can_sell`. ADMIN/DUEÑO ven todo; GERENTE recibe su sucursal con `valor_costo: null` (`ve_costo: false`); CAJERO 403. Vive en `app/routers/reports_valuacion.py`. Sin instantánea diaria (v1 calcula en vivo). |
```

- [ ] **Step 2: Documentar la vista**

En `docs/FRONTEND_VIEWS.md`, tabla de rutas, después de la fila `| /hq/inventory | hq/HQInventory | Admin | inventory |`:

```markdown
| `/hq/valor-inventario` | `hq/HQValorInventario` | Admin, Dueño, Gerente | reports |
```

Y después de la sección `### /hq/inventory — Inventario por sucursal` (antes de `### /hq/branches — Sucursales (grid)`):

```markdown
### `/hq/valor-inventario` — Valor de la tienda
- **Archivo:** `pages/hq/HQValorInventario.tsx`
- **Propósito:** ¿Cuánto vale la existencia de hoy? Valor a precio de venta y a costo con el conteo de piezas/SKUs sin costo, desglosado por sucursal, departamento o marca; filtro por sucursal; CSV generado en el cliente (`utils/valuacionCsv.ts`).
- **Quién la ve:** Admin, Dueño y Gerente — módulo `reports` (base). El gerente llega limitado a su sucursal por el backend (`ve_costo=false`): la página no le ofrece selector de sucursal ni columna de costo.
- **Datos/API:** `reportsApi.valorInventario`, `organizationApi.getBranches`.
- **Notas:** La tarjeta `components/reports/ValorTiendaCard.tsx` en `HQOperations` muestra el mismo dato; cuando hay piezas sin costo la cifra grande es la de venta y el costo baja a secundaria con el aviso "N piezas sin costo" (riesgo documentado en el mega plan 2026-10: un catálogo importado sin costos no debe leerse como "mi tienda vale $0"). Kit `ui/` (`CabeceraPagina`, `BarraFiltros`, `TarjetaFila`, `ListaTarjetas`); tabla en escritorio, tarjetas bajo `md`.
```

También actualizar la entrada de `/hq/operations` en la sección `### /hq/operations — Operaciones (command center)`, añadiendo a **Datos/API**: `reportsApi.valorInventario` (tarjeta "Valor de la tienda").

- [ ] **Step 3: Revisar el render**

Run: `grep -n "valor-inventario" docs/API_REFERENCE.md docs/FRONTEND_VIEWS.md`
Expected: 1 coincidencia en `API_REFERENCE.md`, 3 en `FRONTEND_VIEWS.md` (fila de tabla, encabezado de sección, nota de Operations).

- [ ] **Step 4: Commit**

```bash
git add docs/API_REFERENCE.md docs/FRONTEND_VIEWS.md
git commit -m "docs: valor de la tienda — endpoint /api/reports/valor-inventario y vista /hq/valor-inventario

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

## Criterio de salida (spec §5, fila SP3/SP6)

- Eleven (org 17) ve su valor a venta y a costo con el conteo de piezas sin costo, en la tarjeta del inicio y en `/hq/valor-inventario`.
- Pruebas con costo 0 y costo NULL en verde (`tests/test_reports_valor_inventario.py`, 22 tests).
- Suite de pytest sin nuevos `failed`; `tsc`, vitest y `vite build` en verde.
- Rama `feat/valor-de-la-tienda` lista para revisión; fusión a `main` solo con permiso explícito (regla de oro #1).

## Hallazgos del código que matizan la spec

1. **La tabla de existencias es `stock_on_hand` (`StockOnHand` en `app/models/inventory.py`), no `branch_stock`.** Columnas: `branch_id` (Integer FK), `variant_id` (String(36) FK), `qty_on_hand` (Numeric(10,2)), `is_active`, `organization_id`. Hay una fila por sucursal × variante.
2. **`price` y `cost` viven solo en `ProductVariant`.** `Product` no tiene precio ni costo, así que la regla "la variante hereda del producto cuando los trae vacíos" no aplica: no hay nada que heredar. `price` NULL se trata como 0 en `valor_venta` (`coalesce`); `cost` NULL o ≤ 0 es "sin costo".
3. **Soft delete:** `deleted_at` (de `AuditMixin`) en `products` y `product_variants`; el borrado desde la API (`app/modules/products/router/core.py:681-686`) marca ambos y pone `is_active=False`. El plan excluye por `deleted_at`, no por `is_active` (un producto archivado sigue teniendo existencia física).
4. **El kit pedido (`CabeceraPagina`, `BarraFiltros`, `TarjetaFila`, `ListaTarjetas`) vive en `frontend/src/components/ui/`, no en `frontend/src/components/atlas-one/`.** `atlas-one/` tiene `Kpi`, `Card`, `Badge`, `Sidebar`… y hoy solo lo usan `Login`, `GastroHomeDay`, `Meseros` y una vista de preview. `HQOperations` ya importa las cuatro piezas desde `ui/`; la página nueva hace lo mismo.
5. **`reports.py` no usa `require_module`** (ningún endpoint de reportes lo usa); el gating del endpoint nuevo es solo por rol, y el del menú por `module: 'reports'` en `navConfig.ts`.
6. **`get_current_active_organization` resuelve la org por membresía** en las pruebas (sin header), salvo SUPERADMIN, que exige `X-Organization-ID`. Por eso `test_superadmin_*` manda el header.
7. **Decisión de archivo:** el endpoint va en `app/routers/reports_valuacion.py` (nuevo) montado bajo `/api/reports`, porque `reports.py` tiene 1,129 líneas, todas de ventas, y no hay helper que compartir; la spec lo permite ("`app/routers/reports.py` o …").
8. **Existencias negativas y sucursales inactivas:** la spec no las menciona. El plan excluye `qty_on_hand <= 0` (una venta sin stock no resta valor) y NO filtra `Branch.is_active` (una sucursal cerrada con `can_sell=True` sigue contando; si molesta, se ajusta en SP7 con el dueño).
