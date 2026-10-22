# Conteo de inventario con escáner — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sesiones de conteo físico por departamento, escaneando con el teléfono, que al cerrar producen un reporte de faltantes/sobrantes/desconocidos sin tocar el kardex.

**Architecture:** Módulo nuevo `app/modules/conteos/` (modelos, schemas, servicios, router) montado en `/api/inventory/counts`; dos tablas creadas por `create_all`. En el frontend tres pantallas bajo `/inventory/conteos` que reutilizan el lector de `pages/scanner/barcodeReader.ts` y el kit `components/ui/`. La resolución del código copia la regla exacta de `pos/search?exact=true`.

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic v2 (pytest en SQLite); React 18 + TS + Vite (vitest); Tailwind con clases `dax-*`.

**Spec:** `docs/superpowers/specs/2026-10-22-conteo-inventario-design.md`

## Global Constraints

- `main` es producción: todo en la rama `feat/conteo-inventario`; **nunca push ni merge** sin permiso del usuario.
- FKs a UUID = `String(36)` (regla de oro #4). Tablas nuevas solo por `create_all` (regla #3); sin ALTER en `railway_init.py`.
- Toda consulta filtra `organization_id` (regla #5).
- Solo ADMINISTRADOR y DUEÑO (`_is_admin` de `app/crud/products.py`); módulo `inventory` (`require_module`).
- Nada toca `StockOnHand` ni `InventoryMovement`: el conteo solo lee y reporta.
- Frontend: kit `components/ui/` (`Modal`, `ConfirmDialog`, `CabeceraPagina`, `ListaTarjetas`, `TarjetaFila`); botones `dax-btn-*`; ningún `fixed inset-0` nuevo (`overlaysFueraDelKit.test.ts`); rutas lazy.
- Pruebas: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_conteos*.py` y `cd frontend && npx vitest run`; un solo pytest por worktree.
- Commits terminan con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf`.
- Español en comentarios, mensajes y nombres de usuario; sin `print()` de depuración.

## Review Focus

1. Código escaneado con espacios o SKU en otra mayúscula debe empatar (Task 2, `test_resolver_sku_mayusculas_y_espacios`).
2. Una línea cuyo producto se desactivó después de contarla no debe tirar el reporte: va a `fuera_de_alcance` (Task 2, `test_reporte_linea_de_producto_inactivo_va_a_fuera_de_alcance`).
3. `PATCH` con cantidad negativa es 422 y no toca la línea (Task 3, `test_patch_negativo_es_422`).
4. Dos conteos abiertos de la misma sucursal con departamentos distintos sí se permiten; el 409 es solo por el mismo par (Task 3, `test_crear_dos_departamentos_distintos_ok`).
5. Cerrar un conteo sin una sola línea debe reportar todas las esperadas como faltantes y no fallar (Task 2, `test_cerrar_sin_lineas_reporta_todo_faltante`).

---

### Task 1: Modelos, schemas y registro del módulo

**Files:**
- Create: `app/modules/conteos/__init__.py`, `app/modules/conteos/models.py`, `app/modules/conteos/schemas.py`
- Modify: `app/models/__init__.py` (al final, tras `ExchangeRate`)
- Test: `tests/test_conteos_models.py`

**Interfaces:**
- Produces: `InventoryCount`, `InventoryCountLine`, constantes `ABIERTO`/`CERRADO`; schemas `ProductoResumen`, `LineaRead`, `Avance`, `ConteoCreate`, `ConteoRead`, `ConteoDetalle`, `LineaCreate`, `LineaPatch`, `ScanRequest`, `ScanResult`, `FilaReporte`, `FilaDesconocido`, `Reporte`.

- [ ] **Step 1: Prueba que falla**

```python
# tests/test_conteos_models.py
"""Las tablas del conteo existen y aceptan una sesión con sus líneas."""
from decimal import Decimal


def test_tablas_del_conteo_se_crean_y_guardan(db, org, branch_a):
    from app.modules.conteos.models import ABIERTO, InventoryCount, InventoryCountLine

    c = InventoryCount(organization_id=org.id, branch_id=branch_a.id, status=ABIERTO)
    db.add(c)
    db.flush()
    db.add(InventoryCountLine(organization_id=org.id, count_id=c.id, codigo="XYZ",
                              qty_contada=Decimal("2")))
    db.commit()
    db.refresh(c)
    assert c.status == "ABIERTO"
    assert len(c.lineas) == 1 and c.lineas[0].codigo == "XYZ"
```

- [ ] **Step 2: Correr y ver que falla**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_conteos_models.py`
Expected: FAIL con `ModuleNotFoundError: app.modules.conteos`

- [ ] **Step 3: Modelos**

```python
# app/modules/conteos/__init__.py
"""Conteo físico de inventario con escáner (spec 2026-10-22)."""
```

```python
# app/modules/conteos/models.py
"""Sesiones de conteo físico y sus líneas.

Un conteo es UNA sucursal y, opcionalmente, UN departamento. Una línea por
variante por conteo (escanear la misma talla dos veces suma 1 a la misma
línea) y una línea por código desconocido. Nada de aquí toca `stock_on_hand`:
el conteo lee la existencia y la congela en `qty_sistema` al cerrar.

Diseño: docs/superpowers/specs/2026-10-22-conteo-inventario-design.md §2.
"""
from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.mixins import TenantMixin

# Estado como String + constantes (CLAUDE.md §5: evitar enums de Postgres).
ABIERTO = "ABIERTO"
CERRADO = "CERRADO"


class InventoryCount(Base, TenantMixin):
    __tablename__ = "inventory_counts"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    # NULL = toda la tienda. FK a UUID → String(36) (regla de oro #4).
    department_id = Column(String(36), ForeignKey("departments.id"), nullable=True)
    status = Column(String(10), nullable=False, default=ABIERTO)
    notes = Column(String, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)
    # JSON del reporte congelado al cerrar (services.cerrar).
    resumen = Column(Text, nullable=True)

    lineas = relationship(
        "InventoryCountLine", back_populates="conteo",
        cascade="all, delete-orphan", order_by="InventoryCountLine.updated_at.desc()",
    )
    branch = relationship("Branch")
    department = relationship("Department")
    created_by = relationship("User")


class InventoryCountLine(Base, TenantMixin):
    __tablename__ = "inventory_count_lines"

    id = Column(Integer, primary_key=True, index=True)
    count_id = Column(Integer, ForeignKey("inventory_counts.id"), nullable=False, index=True)
    # NULL = código desconocido; entonces `codigo` trae lo escaneado.
    variant_id = Column(String(36), ForeignKey("product_variants.id"), nullable=True)
    codigo = Column(String, nullable=True)
    qty_contada = Column(Numeric(10, 2), nullable=False, default=0)
    # Existencia al CERRAR; NULL mientras el conteo está abierto.
    qty_sistema = Column(Numeric(10, 2), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("count_id", "variant_id", name="uq_count_line_variant"),
        UniqueConstraint("count_id", "codigo", name="uq_count_line_codigo"),
    )

    conteo = relationship("InventoryCount", back_populates="lineas")
    variant = relationship("ProductVariant")
```

- [ ] **Step 4: Schemas**

```python
# app/modules/conteos/schemas.py
"""Contratos de `/api/inventory/counts` (Pydantic v2)."""
from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ProductoResumen(BaseModel):
    variant_id: str
    nombre: str
    marca: Optional[str] = None
    talla: Optional[str] = None
    color: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    foto: Optional[str] = None
    departamento: Optional[str] = None


class LineaRead(BaseModel):
    id: int
    variant_id: Optional[str] = None
    codigo: Optional[str] = None
    qty_contada: Decimal
    qty_sistema: Optional[Decimal] = None
    producto: Optional[ProductoResumen] = None
    updated_at: Optional[datetime] = None


class Avance(BaseModel):
    esperadas_variantes: int
    esperadas_piezas: Decimal
    contadas_variantes: int
    contadas_piezas: Decimal
    desconocidos: int


class ConteoCreate(BaseModel):
    branch_id: Optional[int] = None
    department_id: Optional[str] = None
    notes: Optional[str] = None


class ConteoRead(BaseModel):
    id: int
    branch_id: int
    branch_name: Optional[str] = None
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    status: str
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    avance: Avance


class ConteoDetalle(ConteoRead):
    lineas: List[LineaRead] = []


class LineaCreate(BaseModel):
    variant_id: str
    qty: Decimal = Field(default=Decimal("1"), gt=0)


class LineaPatch(BaseModel):
    qty_contada: Decimal = Field(ge=0)


class ScanRequest(BaseModel):
    code: str


class ScanResult(BaseModel):
    resultado: Literal["contado", "ambiguo", "desconocido"]
    linea: Optional[LineaRead] = None
    producto: Optional[ProductoResumen] = None
    qty_sistema: Optional[Decimal] = None
    fuera_de_alcance: bool = False
    candidatos: List[ProductoResumen] = []


class FilaReporte(BaseModel):
    variant_id: str
    sku: Optional[str] = None
    nombre: str
    marca: Optional[str] = None
    talla: Optional[str] = None
    color: Optional[str] = None
    departamento: Optional[str] = None
    sistema: Decimal
    contado: Decimal
    diferencia: Decimal


class FilaDesconocido(BaseModel):
    codigo: str
    contado: Decimal


class Reporte(BaseModel):
    estado: str
    generado_en: datetime
    alcance: dict
    totales: dict
    faltantes: List[FilaReporte] = []
    sobrantes: List[FilaReporte] = []
    fuera_de_alcance: List[FilaReporte] = []
    desconocidos: List[FilaDesconocido] = []
```

- [ ] **Step 5: Registrar los modelos**

Al final de `app/models/__init__.py`, después del bloque 15 (`ExchangeRate`):

```python
# 16. Conteo físico de inventario (2026-10-22) — tablas inventory_counts e
#     inventory_count_lines; las crea `create_all`.
from app.modules.conteos import models as _conteos_models  # noqa: F401
```

- [ ] **Step 6: Correr y ver que pasa**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_conteos_models.py`
Expected: `1 passed`

- [ ] **Step 7: Commit**

```bash
git add app/modules/conteos app/models/__init__.py tests/test_conteos_models.py
git commit -m "feat(conteos): modelos y schemas del conteo físico de inventario"
```

---

### Task 2: Servicios (resolver, escanear, líneas, reporte, cerrar)

**Files:**
- Create: `app/modules/conteos/services.py`
- Test: `tests/test_conteos_services.py`

**Interfaces:**
- Consumes: modelos y schemas de Task 1; `variant_sale_name` de `app/modules/products/sale_name.py`; `Product`, `ProductVariant`, `PackagingUnit`, `Department`, `Brand` de `app/modules/products/models.py`; `StockOnHand` de `app/models/inventory.py`.
- Produces (todas reciben `db: Session` primero):
  - `resolver_codigo(db, org_id: int, code: str) -> list[ProductVariant]`
  - `resumen_producto(v: ProductVariant) -> ProductoResumen`
  - `existencias(db, conteo) -> dict[str, Decimal]` (variant_id → qty en la sucursal)
  - `escanear(db, conteo, code: str, user_id: int | None) -> ScanResult`
  - `agregar_linea(db, conteo, variant_id: str, qty: Decimal, user_id) -> InventoryCountLine` (404 si la variante no es de la org)
  - `fijar_linea(db, conteo, linea, qty: Decimal) -> InventoryCountLine | None` (0 borra y devuelve None)
  - `avance(db, conteo) -> Avance`
  - `reporte(db, conteo) -> Reporte`
  - `cerrar(db, conteo, user_id) -> Reporte` (409 si ya estaba cerrado)
  - `a_linea_read(linea) -> LineaRead`, `a_conteo_read(db, conteo, con_lineas: bool) -> ConteoRead | ConteoDetalle`

- [ ] **Step 1: Pruebas que fallan**

```python
# tests/test_conteos_services.py
"""Reglas del conteo: resolución del código, suma, reporte y cierre."""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.inventory import StockOnHand
from app.models.products import Brand, Department, PackagingUnit, Product, ProductVariant
from app.modules.conteos import services
from app.modules.conteos.models import ABIERTO, CERRADO, InventoryCount


def _prenda(db, org, branch, *, name, sku, barcode, depto, stock="3", size="M",
            color="Negro", brand=None, activo=True):
    p = Product(name=name, organization_id=org.id, is_active=activo,
                department_id=depto.id, brand_id=brand.id if brand else None)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku=sku, barcode=barcode, organization_id=org.id,
                       price=Decimal("100"), cost=Decimal("50"), size=size, color=color)
    db.add(v)
    db.flush()
    if stock is not None:
        db.add(StockOnHand(variant_id=v.id, branch_id=branch.id, organization_id=org.id,
                           qty_on_hand=Decimal(stock), is_active=True))
    db.flush()
    return v


@pytest.fixture()
def tienda(db, org, branch_a):
    marca = Brand(name="Zegna", organization_id=org.id)
    playeras = Department(name="Playeras", organization_id=org.id)
    tenis = Department(name="Tenis", organization_id=org.id)
    db.add_all([marca, playeras, tenis])
    db.flush()
    roja = _prenda(db, org, branch_a, name="Playera", sku="ZEG-PLAY-ROJ-M",
                   barcode="2017000000013", depto=playeras, brand=marca, stock="3")
    azul = _prenda(db, org, branch_a, name="Playera", sku="zeg-play-azu-m",
                   barcode="2017000000020", depto=playeras, brand=marca, stock="2", color="Azul")
    sin_stock = _prenda(db, org, branch_a, name="Playera vieja", sku="PLAY-VIEJA",
                        barcode="2017000000037", depto=playeras, stock="0")
    tenis_v = _prenda(db, org, branch_a, name="Tenis", sku="ZEG-TENI-27",
                      barcode="2017000000044", depto=tenis, brand=marca, stock="1", size="27")
    db.add(PackagingUnit(variant_id=roja.id, organization_id=org.id, name="Caja",
                         barcode="CAJA-ROJA", units_per_package=Decimal("6"),
                         package_price=Decimal("500")))
    conteo = InventoryCount(organization_id=org.id, branch_id=branch_a.id,
                            department_id=playeras.id, status=ABIERTO)
    db.add(conteo)
    db.commit()
    return {"roja": roja, "azul": azul, "sin_stock": sin_stock, "tenis": tenis_v,
            "conteo": conteo, "playeras": playeras, "tenis_depto": tenis}


def test_resolver_por_barcode_sku_y_empaque(db, org, tienda):
    assert [v.id for v in services.resolver_codigo(db, org.id, "2017000000013")] == [tienda["roja"].id]
    assert [v.id for v in services.resolver_codigo(db, org.id, "CAJA-ROJA")] == [tienda["roja"].id]
    assert services.resolver_codigo(db, org.id, "no-existe") == []


def test_resolver_sku_mayusculas_y_espacios(db, org, tienda):
    hits = services.resolver_codigo(db, org.id, "  ZEG-PLAY-AZU-M ")
    assert [v.id for v in hits] == [tienda["azul"].id]


def test_resolver_no_cruza_organizaciones(db, org, tienda):
    assert services.resolver_codigo(db, org.id + 999, "2017000000013") == []


def test_escanear_dos_veces_suma_a_la_misma_linea(db, tienda):
    c = tienda["conteo"]
    r1 = services.escanear(db, c, "2017000000013", None)
    r2 = services.escanear(db, c, "2017000000013", None)
    assert r1.resultado == r2.resultado == "contado"
    assert r2.linea.qty_contada == Decimal("2")
    assert r2.qty_sistema == Decimal("3")
    assert r2.producto.nombre == "Zegna · Playera · Negro, Talla M"
    assert r2.fuera_de_alcance is False
    assert len(c.lineas) == 1


def test_escanear_de_otro_departamento_cuenta_y_avisa(db, tienda):
    r = services.escanear(db, tienda["conteo"], "2017000000044", None)
    assert r.resultado == "contado" and r.fuera_de_alcance is True


def test_escanear_desconocido_crea_linea_sin_variante(db, tienda):
    c = tienda["conteo"]
    r = services.escanear(db, c, "9999", None)
    r = services.escanear(db, c, "9999", None)
    assert r.resultado == "desconocido"
    assert r.linea.variant_id is None and r.linea.codigo == "9999"
    assert r.linea.qty_contada == Decimal("2")


def test_escanear_ambiguo_no_cuenta(db, org, tienda):
    # Un empaque cuyo código es el SKU de otra talla: dos variantes empatan.
    db.add(PackagingUnit(variant_id=tienda["azul"].id, organization_id=org.id, name="Caja",
                         barcode="ZEG-PLAY-ROJ-M", units_per_package=Decimal("6"),
                         package_price=Decimal("500")))
    db.commit()
    r = services.escanear(db, tienda["conteo"], "ZEG-PLAY-ROJ-M", None)
    assert r.resultado == "ambiguo"
    assert {p.variant_id for p in r.candidatos} == {tienda["roja"].id, tienda["azul"].id}
    assert tienda["conteo"].lineas == []


def test_escanear_en_cerrado_es_409(db, tienda):
    c = tienda["conteo"]
    c.status = CERRADO
    db.commit()
    with pytest.raises(HTTPException) as e:
        services.escanear(db, c, "2017000000013", None)
    assert e.value.status_code == 409


def test_agregar_y_fijar_linea(db, org, tienda):
    c = tienda["conteo"]
    l = services.agregar_linea(db, c, tienda["azul"].id, Decimal("2"), None)
    l = services.agregar_linea(db, c, tienda["azul"].id, Decimal("1"), None)
    assert l.qty_contada == Decimal("3")
    l = services.fijar_linea(db, c, l, Decimal("1"))
    assert l.qty_contada == Decimal("1")
    assert services.fijar_linea(db, c, l, Decimal("0")) is None
    assert c.lineas == []
    with pytest.raises(HTTPException) as e:
        services.agregar_linea(db, c, "no-existe", Decimal("1"), None)
    assert e.value.status_code == 404


def test_reporte_con_las_cuatro_secciones(db, tienda):
    c = tienda["conteo"]
    services.escanear(db, c, "2017000000013", None)          # roja: 1 de 3 → faltan 2
    services.escanear(db, c, "2017000000037", None)          # sin_stock: 1 de 0 → sobra 1
    services.escanear(db, c, "2017000000044", None)          # tenis: fuera de alcance
    services.escanear(db, c, "9999", None)                   # desconocido
    rep = services.reporte(db, c)
    assert rep.estado == ABIERTO
    faltantes = {f.sku: f for f in rep.faltantes}
    assert faltantes["ZEG-PLAY-ROJ-M"].diferencia == Decimal("-2")
    assert faltantes["zeg-play-azu-m"].contado == Decimal("0")   # nunca escaneada
    assert [s.sku for s in rep.sobrantes] == ["PLAY-VIEJA"]
    assert rep.sobrantes[0].diferencia == Decimal("1")
    assert [f.sku for f in rep.fuera_de_alcance] == ["ZEG-TENI-27"]
    assert rep.fuera_de_alcance[0].departamento == "Tenis"
    assert [d.codigo for d in rep.desconocidos] == ["9999"]
    assert rep.totales["esperadas_variantes"] == 2
    assert rep.totales["esperadas_piezas"] == Decimal("5")
    assert rep.totales["faltantes_piezas"] == Decimal("4")
    assert rep.totales["sobrantes_piezas"] == Decimal("1")
    assert rep.totales["fuera_de_alcance_piezas"] == Decimal("1")
    assert rep.totales["desconocidos"] == 1
    assert rep.alcance == {"sucursal": "Sucursal A", "departamento": "Playeras"}


def test_reporte_linea_de_producto_inactivo_va_a_fuera_de_alcance(db, tienda):
    c = tienda["conteo"]
    services.escanear(db, c, "2017000000013", None)
    tienda["roja"].product.is_active = False
    db.commit()
    rep = services.reporte(db, c)
    assert [f.sku for f in rep.fuera_de_alcance] == ["ZEG-PLAY-ROJ-M"]
    assert all(f.sku != "ZEG-PLAY-ROJ-M" for f in rep.faltantes)


def test_cerrar_sin_lineas_reporta_todo_faltante(db, tienda):
    rep = services.cerrar(db, tienda["conteo"], None)
    assert {f.sku for f in rep.faltantes} == {"ZEG-PLAY-ROJ-M", "zeg-play-azu-m"}
    assert rep.totales["contadas_piezas"] == Decimal("0")


def test_cerrar_congela_y_no_recalcula(db, tienda):
    c = tienda["conteo"]
    services.escanear(db, c, "2017000000013", None)
    rep = services.cerrar(db, c, None)
    assert c.status == CERRADO and c.closed_at is not None and c.resumen
    assert c.lineas[0].qty_sistema == Decimal("3")
    # El inventario cambia después: el reporte guardado no se mueve.
    soh = db.query(StockOnHand).filter_by(variant_id=tienda["roja"].id).first()
    soh.qty_on_hand = Decimal("10")
    db.commit()
    rep2 = services.reporte(db, c)
    assert rep2.faltantes[0].sistema == rep.faltantes[0].sistema == Decimal("3")
    with pytest.raises(HTTPException) as e:
        services.cerrar(db, c, None)
    assert e.value.status_code == 409


def test_avance(db, tienda):
    c = tienda["conteo"]
    services.escanear(db, c, "2017000000013", None)
    services.escanear(db, c, "9999", None)
    a = services.avance(db, c)
    assert (a.esperadas_variantes, a.esperadas_piezas) == (2, Decimal("5"))
    assert (a.contadas_variantes, a.contadas_piezas, a.desconocidos) == (1, Decimal("1"), 1)
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_conteos_services.py`
Expected: FAIL con `ImportError: cannot import name 'services'`

- [ ] **Step 3: Servicios**

```python
# app/modules/conteos/services.py
"""Reglas del conteo físico. El router solo valida permisos y delega aquí.

Diseño: docs/superpowers/specs/2026-10-22-conteo-inventario-design.md §4-§5.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.inventory import StockOnHand
from app.modules.conteos.models import ABIERTO, CERRADO, InventoryCount, InventoryCountLine
from app.modules.conteos.schemas import (
    Avance, ConteoDetalle, ConteoRead, FilaDesconocido, FilaReporte, LineaRead,
    ProductoResumen, Reporte, ScanResult,
)
from app.modules.products.models import PackagingUnit, Product, ProductVariant
from app.modules.products.sale_name import variant_sale_name

CERO = Decimal("0")


# ── Resolución del código ────────────────────────────────────────────────────
def resolver_codigo(db: Session, org_id: int, code: str) -> List[ProductVariant]:
    """Misma regla exacta que `pos/search?exact=true`: SKU sin importar
    mayúsculas, código de barras o código de empaque, dentro de la org, con
    producto activo y variante sin baja. Devuelve TODAS las que empatan: con
    más de una, el pasillo pregunta en vez de adivinar."""
    code = (code or "").strip()
    if not code:
        return []
    filas = (
        db.query(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .outerjoin(PackagingUnit, PackagingUnit.variant_id == ProductVariant.id)
        .options(joinedload(ProductVariant.product).joinedload(Product.brand),
                 joinedload(ProductVariant.product).joinedload(Product.department))
        .filter(
            Product.organization_id == org_id,
            Product.is_active.is_(True),
            ProductVariant.deleted_at.is_(None),
            or_(
                func.lower(ProductVariant.sku) == code.lower(),
                ProductVariant.barcode == code,
                PackagingUnit.barcode == code,
            ),
        )
        .all()
    )
    # El outerjoin a empaques puede repetir la variante: una por id.
    unicas: Dict[str, ProductVariant] = {}
    for v in filas:
        unicas.setdefault(v.id, v)
    return list(unicas.values())


def resumen_producto(v: ProductVariant) -> ProductoResumen:
    p = v.product
    marca = p.brand.name if getattr(p, "brand", None) else None
    return ProductoResumen(
        variant_id=v.id,
        nombre=variant_sale_name(marca, p.name, p.model, v.color, v.size, v.variant_name),
        marca=marca, talla=v.size, color=v.color, sku=v.sku, barcode=v.barcode,
        foto=p.image_url,
        departamento=p.department.name if getattr(p, "department", None) else None,
    )


def _variante_de_la_org(db: Session, org_id: int, variant_id: str) -> Optional[ProductVariant]:
    return (
        db.query(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .options(joinedload(ProductVariant.product).joinedload(Product.brand),
                 joinedload(ProductVariant.product).joinedload(Product.department))
        .filter(Product.organization_id == org_id, ProductVariant.id == variant_id,
                ProductVariant.deleted_at.is_(None))
        .first()
    )


# ── Existencias y alcance ────────────────────────────────────────────────────
def existencias(db: Session, conteo: InventoryCount) -> Dict[str, Decimal]:
    filas = (
        db.query(StockOnHand.variant_id, StockOnHand.qty_on_hand)
        .filter(StockOnHand.organization_id == conteo.organization_id,
                StockOnHand.branch_id == conteo.branch_id)
        .all()
    )
    return {vid: Decimal(q or 0) for vid, q in filas}


def _alcance(db: Session, conteo: InventoryCount) -> List[ProductVariant]:
    q = (
        db.query(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .options(joinedload(ProductVariant.product).joinedload(Product.brand),
                 joinedload(ProductVariant.product).joinedload(Product.department))
        .filter(Product.organization_id == conteo.organization_id,
                Product.is_active.is_(True), ProductVariant.deleted_at.is_(None))
    )
    if conteo.department_id:
        q = q.filter(Product.department_id == conteo.department_id)
    return q.all()


def _fuera_de_alcance(conteo: InventoryCount, v: ProductVariant) -> bool:
    return bool(conteo.department_id) and v.product.department_id != conteo.department_id


# ── Líneas ───────────────────────────────────────────────────────────────────
def _exigir_abierto(conteo: InventoryCount) -> None:
    if conteo.status != ABIERTO:
        raise HTTPException(409, "Este conteo ya está cerrado.")


def _sumar(db: Session, conteo: InventoryCount, v: ProductVariant, qty: Decimal,
           user_id: Optional[int]) -> InventoryCountLine:
    linea = next((l for l in conteo.lineas if l.variant_id == v.id), None)
    if linea is None:
        linea = InventoryCountLine(organization_id=conteo.organization_id, count_id=conteo.id,
                                   variant_id=v.id, qty_contada=CERO,
                                   created_by_user_id=user_id)
        conteo.lineas.append(linea)
    linea.qty_contada = Decimal(linea.qty_contada or 0) + qty
    db.commit()
    db.refresh(linea)
    return linea


def escanear(db: Session, conteo: InventoryCount, code: str, user_id: Optional[int]) -> ScanResult:
    _exigir_abierto(conteo)
    code = (code or "").strip()
    if not code:
        raise HTTPException(422, "Código vacío.")
    hits = resolver_codigo(db, conteo.organization_id, code)
    if len(hits) == 1:
        v = hits[0]
        linea = _sumar(db, conteo, v, Decimal("1"), user_id)
        return ScanResult(
            resultado="contado", linea=a_linea_read(linea), producto=resumen_producto(v),
            qty_sistema=existencias(db, conteo).get(v.id, CERO),
            fuera_de_alcance=_fuera_de_alcance(conteo, v),
        )
    if len(hits) > 1:
        return ScanResult(resultado="ambiguo", candidatos=[resumen_producto(v) for v in hits])
    linea = next((l for l in conteo.lineas if l.variant_id is None and l.codigo == code), None)
    if linea is None:
        linea = InventoryCountLine(organization_id=conteo.organization_id, count_id=conteo.id,
                                   codigo=code, qty_contada=CERO, created_by_user_id=user_id)
        conteo.lineas.append(linea)
    linea.qty_contada = Decimal(linea.qty_contada or 0) + 1
    db.commit()
    db.refresh(linea)
    return ScanResult(resultado="desconocido", linea=a_linea_read(linea))


def agregar_linea(db: Session, conteo: InventoryCount, variant_id: str, qty: Decimal,
                  user_id: Optional[int]) -> InventoryCountLine:
    _exigir_abierto(conteo)
    v = _variante_de_la_org(db, conteo.organization_id, variant_id)
    if v is None:
        raise HTTPException(404, "Producto no encontrado")
    return _sumar(db, conteo, v, Decimal(qty), user_id)


def fijar_linea(db: Session, conteo: InventoryCount, linea: InventoryCountLine,
                qty: Decimal) -> Optional[InventoryCountLine]:
    _exigir_abierto(conteo)
    if Decimal(qty) <= 0:
        conteo.lineas.remove(linea)
        db.delete(linea)
        db.commit()
        return None
    linea.qty_contada = Decimal(qty)
    db.commit()
    db.refresh(linea)
    return linea


# ── Reporte ──────────────────────────────────────────────────────────────────
def _fila(v: ProductVariant, sistema: Decimal, contado: Decimal) -> FilaReporte:
    r = resumen_producto(v)
    return FilaReporte(variant_id=v.id, sku=v.sku, nombre=r.nombre, marca=r.marca, talla=r.talla,
                       color=r.color, departamento=r.departamento, sistema=sistema,
                       contado=contado, diferencia=contado - sistema)


def _calcular(db: Session, conteo: InventoryCount) -> Reporte:
    stock = existencias(db, conteo)
    alcance = _alcance(db, conteo)
    ids_alcance = {v.id for v in alcance}
    contadas = {l.variant_id: Decimal(l.qty_contada or 0) for l in conteo.lineas if l.variant_id}

    faltantes: List[FilaReporte] = []
    sobrantes: List[FilaReporte] = []
    cuadradas = 0
    esperadas_variantes = 0
    esperadas_piezas = CERO
    for v in alcance:
        sistema = stock.get(v.id, CERO)
        contado = contadas.get(v.id, CERO)
        if sistema > 0:
            esperadas_variantes += 1
            esperadas_piezas += sistema
        if sistema > 0 and contado < sistema:
            faltantes.append(_fila(v, sistema, contado))
        elif contado > sistema:
            sobrantes.append(_fila(v, sistema, contado))
        elif sistema > 0 and contado == sistema:
            cuadradas += 1

    fuera: List[FilaReporte] = []
    for l in conteo.lineas:
        if l.variant_id and l.variant_id not in ids_alcance and l.variant is not None:
            fuera.append(_fila(l.variant, stock.get(l.variant_id, CERO), Decimal(l.qty_contada or 0)))
    desconocidos = [FilaDesconocido(codigo=l.codigo or "", contado=Decimal(l.qty_contada or 0))
                    for l in conteo.lineas if l.variant_id is None]

    por_diferencia = lambda f: -abs(f.diferencia)  # noqa: E731
    faltantes.sort(key=por_diferencia)
    sobrantes.sort(key=por_diferencia)
    fuera.sort(key=por_diferencia)

    contadas_en_alcance = [l for l in conteo.lineas if l.variant_id in ids_alcance]
    return Reporte(
        estado=conteo.status,
        generado_en=datetime.now(timezone.utc),
        alcance={
            "sucursal": conteo.branch.name if conteo.branch else None,
            "departamento": conteo.department.name if conteo.department else None,
        },
        totales={
            "esperadas_variantes": esperadas_variantes,
            "esperadas_piezas": esperadas_piezas,
            "contadas_variantes": len(contadas_en_alcance),
            "contadas_piezas": sum((Decimal(l.qty_contada or 0) for l in contadas_en_alcance), CERO),
            "cuadradas_variantes": cuadradas,
            "faltantes_piezas": sum((-f.diferencia for f in faltantes), CERO),
            "sobrantes_piezas": sum((s.diferencia for s in sobrantes), CERO),
            "fuera_de_alcance_piezas": sum((f.contado for f in fuera), CERO),
            "desconocidos": len(desconocidos),
        },
        faltantes=faltantes, sobrantes=sobrantes, fuera_de_alcance=fuera, desconocidos=desconocidos,
    )


def reporte(db: Session, conteo: InventoryCount) -> Reporte:
    """Abierto: se calcula en vivo. Cerrado: el JSON congelado, tal cual."""
    if conteo.status == CERRADO and conteo.resumen:
        return Reporte.model_validate(json.loads(conteo.resumen))
    return _calcular(db, conteo)


def cerrar(db: Session, conteo: InventoryCount, user_id: Optional[int]) -> Reporte:
    _exigir_abierto(conteo)
    rep = _calcular(db, conteo)
    stock = existencias(db, conteo)
    for l in conteo.lineas:
        l.qty_sistema = stock.get(l.variant_id, CERO) if l.variant_id else None
    conteo.status = CERRADO
    conteo.closed_at = datetime.now(timezone.utc)
    rep.estado = CERRADO
    conteo.resumen = json.dumps(rep.model_dump(mode="json"))
    db.commit()
    db.refresh(conteo)
    return rep


# ── Lecturas ─────────────────────────────────────────────────────────────────
def avance(db: Session, conteo: InventoryCount) -> Avance:
    stock = existencias(db, conteo)
    ids_alcance = {v.id for v in _alcance(db, conteo)}
    esperadas = [vid for vid in ids_alcance if stock.get(vid, CERO) > 0]
    contadas = [l for l in conteo.lineas if l.variant_id in ids_alcance]
    return Avance(
        esperadas_variantes=len(esperadas),
        esperadas_piezas=sum((stock[vid] for vid in esperadas), CERO),
        contadas_variantes=len(contadas),
        contadas_piezas=sum((Decimal(l.qty_contada or 0) for l in contadas), CERO),
        desconocidos=sum(1 for l in conteo.lineas if l.variant_id is None),
    )


def a_linea_read(linea: InventoryCountLine) -> LineaRead:
    return LineaRead(
        id=linea.id, variant_id=linea.variant_id, codigo=linea.codigo,
        qty_contada=Decimal(linea.qty_contada or 0), qty_sistema=linea.qty_sistema,
        producto=resumen_producto(linea.variant) if linea.variant is not None else None,
        updated_at=linea.updated_at,
    )


def a_conteo_read(db: Session, conteo: InventoryCount, con_lineas: bool = False):
    datos = dict(
        id=conteo.id, branch_id=conteo.branch_id,
        branch_name=conteo.branch.name if conteo.branch else None,
        department_id=conteo.department_id,
        department_name=conteo.department.name if conteo.department else None,
        status=conteo.status, notes=conteo.notes,
        created_by=conteo.created_by.username if conteo.created_by else None,
        created_at=conteo.created_at, closed_at=conteo.closed_at,
        avance=avance(db, conteo),
    )
    if con_lineas:
        return ConteoDetalle(**datos, lineas=[a_linea_read(l) for l in conteo.lineas])
    return ConteoRead(**datos)
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_conteos_services.py`
Expected: `13 passed`. Si `variant_sale_name` produce otro texto para "Zegna · Playera · Negro, Talla M", ajusta la aserción al valor real de la función (es la fuente de verdad del nombre de venta), no la función.

- [ ] **Step 5: Commit**

```bash
git add app/modules/conteos/services.py tests/test_conteos_services.py
git commit -m "feat(conteos): servicios de escaneo, líneas, reporte y cierre"
```

---

### Task 3: Router `/api/inventory/counts` y pruebas de API

**Files:**
- Create: `app/modules/conteos/router.py`
- Modify: `app/main.py` (import junto a `labels_router`; `include_router` tras el de etiquetas)
- Test: `tests/test_conteos_api.py`

**Interfaces:**
- Consumes: servicios de Task 2; `require_module` (`app/core/permissions.py`); `_is_admin` (`app/crud/products.py`); `get_current_active_organization`; `Branch` (`app/models/organization.py`); `Department` (`app/modules/products/models.py`).
- Produces: las rutas de la tabla del spec §3.

- [ ] **Step 1: Pruebas que fallan**

```python
# tests/test_conteos_api.py
"""`/api/inventory/counts`: permisos, alta, escaneo, líneas, cierre y reporte."""
from decimal import Decimal

import pytest

from app.models.inventory import StockOnHand
from app.models.modules import Module, OrganizationModule
from app.models.organization import Organization
from app.models.products import Department, Product, ProductVariant


def _habilitar(db, org, key):
    if db.query(Module).filter(Module.key == key).first() is None:
        db.add(Module(key=key, name=key))
        db.flush()
    if db.query(OrganizationModule).filter_by(organization_id=org.id, module_key=key).first() is None:
        db.add(OrganizationModule(organization_id=org.id, module_key=key, is_enabled=True))
    db.commit()


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


@pytest.fixture()
def tienda(db, org, branch_a):
    _habilitar(db, org, "inventory")
    playeras = Department(name="Playeras", organization_id=org.id)
    tenis = Department(name="Tenis", organization_id=org.id)
    db.add_all([playeras, tenis])
    db.flush()
    p = Product(name="Playera", organization_id=org.id, is_active=True, department_id=playeras.id)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku="PLAY-M", barcode="2017000000013",
                       organization_id=org.id, price=Decimal("100"), cost=Decimal("50"), size="M")
    db.add(v)
    db.flush()
    db.add(StockOnHand(variant_id=v.id, branch_id=branch_a.id, organization_id=org.id,
                       qty_on_hand=Decimal("3"), is_active=True))
    db.commit()
    return {"playeras": playeras, "tenis": tenis, "v": v}


def _crear(client, auth, org, branch, depto=None, notes=None):
    return client.post("/api/inventory/counts/", headers=_h(auth, org), json={
        "branch_id": branch.id, "department_id": depto.id if depto else None, "notes": notes,
    })


def test_crear_lista_y_ver(client, db, org, branch_a, auth_admin, tienda):
    r = _crear(client, auth_admin, org, branch_a, tienda["playeras"], "pared izquierda")
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["status"] == "ABIERTO" and c["department_name"] == "Playeras"
    assert c["avance"] == {"esperadas_variantes": 1, "esperadas_piezas": "3",
                           "contadas_variantes": 0, "contadas_piezas": "0", "desconocidos": 0}
    r = client.get("/api/inventory/counts/", headers=_h(auth_admin, org))
    assert [x["id"] for x in r.json()] == [c["id"]]
    r = client.get(f"/api/inventory/counts/{c['id']}", headers=_h(auth_admin, org))
    assert r.status_code == 200 and r.json()["lineas"] == []


def test_crear_duplicado_abierto_es_409(client, org, branch_a, auth_admin, tienda):
    assert _crear(client, auth_admin, org, branch_a, tienda["playeras"]).status_code == 201
    assert _crear(client, auth_admin, org, branch_a, tienda["playeras"]).status_code == 409


def test_crear_dos_departamentos_distintos_ok(client, org, branch_a, auth_admin, tienda):
    assert _crear(client, auth_admin, org, branch_a, tienda["playeras"]).status_code == 201
    assert _crear(client, auth_admin, org, branch_a, tienda["tenis"]).status_code == 201
    assert _crear(client, auth_admin, org, branch_a, None).status_code == 201


def test_sucursal_o_departamento_ajenos_son_404(client, db, org, branch_a, auth_admin, tienda):
    otra = Organization(name="Otra", status="ACTIVE")
    db.add(otra)
    db.flush()
    ajeno = Department(name="Ajeno", organization_id=otra.id)
    db.add(ajeno)
    db.commit()
    assert _crear(client, auth_admin, org, branch_a, ajeno).status_code == 404
    r = client.post("/api/inventory/counts/", headers=_h(auth_admin, org),
                    json={"branch_id": 999999})
    assert r.status_code == 404


def test_cajero_recibe_403(client, org, branch_a, auth_cajero_a, tienda):
    r = _crear(client, auth_cajero_a, org, branch_a, tienda["playeras"])
    assert r.status_code == 403
    r = client.get("/api/inventory/counts/", headers=_h(auth_cajero_a, org))
    assert r.status_code == 403


def test_escanear_lineas_cerrar_y_reporte(client, org, branch_a, auth_admin, tienda):
    cid = _crear(client, auth_admin, org, branch_a, tienda["playeras"]).json()["id"]
    h = _h(auth_admin, org)
    r = client.post(f"/api/inventory/counts/{cid}/scan", headers=h, json={"code": "2017000000013"})
    assert r.status_code == 200 and r.json()["resultado"] == "contado"
    assert r.json()["producto"]["sku"] == "PLAY-M" and r.json()["qty_sistema"] == "3"
    r = client.post(f"/api/inventory/counts/{cid}/scan", headers=h, json={"code": "nada"})
    assert r.json()["resultado"] == "desconocido"
    lid = r.json()["linea"]["id"]
    r = client.post(f"/api/inventory/counts/{cid}/lines", headers=h,
                    json={"variant_id": tienda["v"].id, "qty": "1"})
    assert r.status_code == 200 and r.json()["qty_contada"] == "2"
    vid_linea = r.json()["id"]
    r = client.patch(f"/api/inventory/counts/{cid}/lines/{vid_linea}", headers=h,
                     json={"qty_contada": "1"})
    assert r.status_code == 200 and r.json()["qty_contada"] == "1"
    r = client.delete(f"/api/inventory/counts/{cid}/lines/{lid}", headers=h)
    assert r.status_code == 204
    r = client.get(f"/api/inventory/counts/{cid}/report", headers=h)
    assert r.status_code == 200 and r.json()["estado"] == "ABIERTO"
    assert r.json()["faltantes"][0]["diferencia"] == "-2"
    r = client.post(f"/api/inventory/counts/{cid}/close", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "CERRADO"
    assert r.json()["lineas"][0]["qty_sistema"] == "3"
    assert client.post(f"/api/inventory/counts/{cid}/close", headers=h).status_code == 409
    assert client.post(f"/api/inventory/counts/{cid}/scan", headers=h,
                       json={"code": "2017000000013"}).status_code == 409
    r = client.get(f"/api/inventory/counts/{cid}/report", headers=h)
    assert r.json()["estado"] == "CERRADO" and r.json()["totales"]["desconocidos"] == 0


def test_patch_negativo_es_422(client, org, branch_a, auth_admin, tienda):
    cid = _crear(client, auth_admin, org, branch_a, tienda["playeras"]).json()["id"]
    h = _h(auth_admin, org)
    lid = client.post(f"/api/inventory/counts/{cid}/scan", headers=h,
                      json={"code": "2017000000013"}).json()["linea"]["id"]
    r = client.patch(f"/api/inventory/counts/{cid}/lines/{lid}", headers=h, json={"qty_contada": "-1"})
    assert r.status_code == 422
    r = client.patch(f"/api/inventory/counts/{cid}/lines/{lid}", headers=h, json={"qty_contada": "0"})
    assert r.status_code == 200 and r.json() is None


def test_conteo_de_otra_org_es_404(client, db, org, branch_a, auth_admin, tienda):
    cid = _crear(client, auth_admin, org, branch_a, tienda["playeras"]).json()["id"]
    otra = Organization(name="Otra", status="ACTIVE")
    db.add(otra)
    db.commit()
    r = client.get(f"/api/inventory/counts/{cid}", headers={**auth_admin, "X-Organization-ID": str(otra.id)})
    assert r.status_code in (403, 404)
    assert client.get("/api/inventory/counts/999999", headers=_h(auth_admin, org)).status_code == 404
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_conteos_api.py`
Expected: FAIL con 404 en `POST /api/inventory/counts/` (ruta no montada)

- [ ] **Step 3: Router**

```python
# app/modules/conteos/router.py
"""`/api/inventory/counts` — conteo físico con escáner.

Solo ADMINISTRADOR/DUEÑO con el módulo `inventory`. El router valida
permisos, sucursal y departamento; las reglas viven en `services`.
Diseño: docs/superpowers/specs/2026-10-22-conteo-inventario-design.md §3.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_module
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.crud.products import _is_admin
from app.models import User
from app.models.organization import Branch
from app.modules.conteos import services
from app.modules.conteos.models import ABIERTO, InventoryCount, InventoryCountLine
from app.modules.conteos.schemas import (
    ConteoCreate, ConteoDetalle, ConteoRead, LineaCreate, LineaPatch, LineaRead,
    Reporte, ScanRequest, ScanResult,
)
from app.modules.products.models import Department

router = APIRouter(dependencies=[Depends(require_module("inventory"))])


def _admin(current_user: User = Depends(get_current_user)) -> User:
    if not _is_admin(current_user):
        raise HTTPException(403, "Solo administradores y dueños pueden hacer conteos.")
    return current_user


def _conteo_o_404(db: Session, org_id: int, conteo_id: int) -> InventoryCount:
    c = (db.query(InventoryCount)
         .filter(InventoryCount.id == conteo_id, InventoryCount.organization_id == org_id)
         .first())
    if c is None:
        raise HTTPException(404, "Conteo no encontrado")
    return c


def _linea_o_404(conteo: InventoryCount, line_id: int) -> InventoryCountLine:
    l = next((x for x in conteo.lineas if x.id == line_id), None)
    if l is None:
        raise HTTPException(404, "Línea no encontrada")
    return l


def _sucursal(db: Session, org_id: int, user: User, pedida: Optional[int]) -> int:
    """Admin/dueño eligen la sucursal (recordada en el teléfono); si el usuario
    tiene sucursal propia y no manda ninguna, se usa la suya."""
    branch_id = pedida or user.branch_id
    if not branch_id:
        raise HTTPException(422, "Elige la sucursal que vas a contar.")
    b = db.query(Branch).filter(Branch.id == branch_id, Branch.organization_id == org_id).first()
    if b is None:
        raise HTTPException(404, "Sucursal no encontrada")
    return b.id


@router.post("/", response_model=ConteoRead, status_code=201)
def crear_conteo(
    body: ConteoCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_admin),
    org_id: int = Depends(get_current_active_organization),
):
    branch_id = _sucursal(db, org_id, user, body.branch_id)
    if body.department_id:
        d = (db.query(Department)
             .filter(Department.id == body.department_id, Department.organization_id == org_id)
             .first())
        if d is None:
            raise HTTPException(404, "Departamento no encontrado")
    abierto = (db.query(InventoryCount)
               .filter(InventoryCount.organization_id == org_id,
                       InventoryCount.branch_id == branch_id,
                       InventoryCount.department_id == body.department_id,
                       InventoryCount.status == ABIERTO)
               .first())
    if abierto is not None:
        raise HTTPException(409, f"Ya hay un conteo abierto (#{abierto.id}) de esa sucursal y departamento.")
    c = InventoryCount(organization_id=org_id, branch_id=branch_id,
                       department_id=body.department_id, status=ABIERTO,
                       notes=(body.notes or None), created_by_user_id=user.id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return services.a_conteo_read(db, c)


@router.get("/", response_model=List[ConteoRead])
def listar_conteos(
    status: Optional[str] = None,
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(_admin),
    org_id: int = Depends(get_current_active_organization),
):
    q = db.query(InventoryCount).filter(InventoryCount.organization_id == org_id)
    if status:
        q = q.filter(InventoryCount.status == status)
    if branch_id:
        q = q.filter(InventoryCount.branch_id == branch_id)
    return [services.a_conteo_read(db, c) for c in q.order_by(InventoryCount.created_at.desc(), InventoryCount.id.desc()).all()]


@router.get("/{conteo_id}", response_model=ConteoDetalle)
def ver_conteo(conteo_id: int, db: Session = Depends(get_db), _: User = Depends(_admin),
               org_id: int = Depends(get_current_active_organization)):
    return services.a_conteo_read(db, _conteo_o_404(db, org_id, conteo_id), con_lineas=True)


@router.post("/{conteo_id}/scan", response_model=ScanResult)
def escanear(conteo_id: int, body: ScanRequest, db: Session = Depends(get_db),
             user: User = Depends(_admin), org_id: int = Depends(get_current_active_organization)):
    return services.escanear(db, _conteo_o_404(db, org_id, conteo_id), body.code, user.id)


@router.post("/{conteo_id}/lines", response_model=LineaRead)
def agregar_linea(conteo_id: int, body: LineaCreate, db: Session = Depends(get_db),
                  user: User = Depends(_admin), org_id: int = Depends(get_current_active_organization)):
    c = _conteo_o_404(db, org_id, conteo_id)
    return services.a_linea_read(services.agregar_linea(db, c, body.variant_id, body.qty, user.id))


@router.patch("/{conteo_id}/lines/{line_id}", response_model=Optional[LineaRead])
def fijar_linea(conteo_id: int, line_id: int, body: LineaPatch, db: Session = Depends(get_db),
                _: User = Depends(_admin), org_id: int = Depends(get_current_active_organization)):
    c = _conteo_o_404(db, org_id, conteo_id)
    l = services.fijar_linea(db, c, _linea_o_404(c, line_id), body.qty_contada)
    return services.a_linea_read(l) if l is not None else None


@router.delete("/{conteo_id}/lines/{line_id}", status_code=204)
def borrar_linea(conteo_id: int, line_id: int, db: Session = Depends(get_db),
                 _: User = Depends(_admin), org_id: int = Depends(get_current_active_organization)):
    c = _conteo_o_404(db, org_id, conteo_id)
    services.fijar_linea(db, c, _linea_o_404(c, line_id), 0)
    return Response(status_code=204)


@router.post("/{conteo_id}/close", response_model=ConteoDetalle)
def cerrar_conteo(conteo_id: int, db: Session = Depends(get_db), user: User = Depends(_admin),
                  org_id: int = Depends(get_current_active_organization)):
    c = _conteo_o_404(db, org_id, conteo_id)
    services.cerrar(db, c, user.id)
    return services.a_conteo_read(db, c, con_lineas=True)


@router.get("/{conteo_id}/report", response_model=Reporte)
def reporte_conteo(conteo_id: int, db: Session = Depends(get_db), _: User = Depends(_admin),
                   org_id: int = Depends(get_current_active_organization)):
    return services.reporte(db, _conteo_o_404(db, org_id, conteo_id))
```

- [ ] **Step 4: Montar en `app/main.py`**

Junto al import de `labels_router`:

```python
# Conteo físico con escáner (2026-10-22) — sesiones por departamento, solo reporte
from app.modules.conteos.router      import router as conteos_router
```

Después de `app.include_router(labels_router, ...)`:

```python
app.include_router(conteos_router,      prefix="/api/inventory/counts", tags=["Conteos"])
```

Verifica que el montaje quede ANTES de cualquier catch-all y que `/api/inventory/counts/` no choque con `/api/inventory/kardex/{variant_id}` (prefijos distintos; FastAPI resuelve por orden de registro, y `inventory.router` no tiene ruta `counts`).

- [ ] **Step 5: Correr y ver que pasan**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_conteos_api.py tests/test_conteos_services.py tests/test_conteos_models.py`
Expected: `22 passed`. Si `get_current_active_organization` rechaza al admin en la org ajena con 403 en vez de 404, la prueba ya lo admite.

- [ ] **Step 6: Suite completa (baseline)**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py -p no:warnings 2>&1 | tail -3`
Expected: mismo conteo de `passed` que `main` + 22, `0 failed`.

- [ ] **Step 7: Commit**

```bash
git add app/modules/conteos/router.py app/main.py tests/test_conteos_api.py
git commit -m "feat(conteos): API /api/inventory/counts (crear, escanear, líneas, cerrar, reporte)"
```

---

### Task 4: Cliente API y helpers puros del frontend

**Files:**
- Create: `frontend/src/api/conteos.ts`, `frontend/src/pages/inventory/conteos/avance.ts`
- Test: `frontend/src/pages/inventory/conteos/__tests__/avance.test.ts`

**Interfaces:**
- Consumes: `client` de `frontend/src/api/client.ts`.
- Produces: tipos `ProductoResumen`, `Linea`, `Avance`, `Conteo`, `ConteoDetalle`, `ScanResult`, `FilaReporte`, `Reporte`; `conteosApi.{listar, crear, ver, escanear, agregarLinea, fijarLinea, borrarLinea, cerrar, reporte}`; helpers `porcentajeAvance(contadas, esperadas): number`, `textoDiferencia(diferencia): string`, `seccionesReporte(reporte): Seccion[]`, `num(v): number`.

- [ ] **Step 1: Prueba que falla**

```ts
// frontend/src/pages/inventory/conteos/__tests__/avance.test.ts
import { describe, it, expect } from 'vitest'

import { num, porcentajeAvance, seccionesReporte, textoDiferencia } from '../avance'
import type { Reporte } from '../../../../api/conteos'

describe('porcentajeAvance', () => {
  it('es 0 sin esperadas y se acota a 100', () => {
    expect(porcentajeAvance(0, 0)).toBe(0)
    expect(porcentajeAvance(3, 0)).toBe(0)
    expect(porcentajeAvance(5, 10)).toBe(50)
    expect(porcentajeAvance(12, 10)).toBe(100)
  })
})

describe('textoDiferencia', () => {
  it('redacta faltan/sobra/cuadra', () => {
    expect(textoDiferencia(-3)).toBe('faltan 3')
    expect(textoDiferencia(-1)).toBe('falta 1')
    expect(textoDiferencia(1)).toBe('sobra 1')
    expect(textoDiferencia(2)).toBe('sobran 2')
    expect(textoDiferencia(0)).toBe('cuadra')
  })
})

describe('seccionesReporte', () => {
  const fila = (sku: string, diferencia: string) => ({
    variant_id: sku, sku, nombre: sku, marca: null, talla: null, color: null, departamento: null,
    sistema: '3', contado: '1', diferencia,
  })
  const reporte: Reporte = {
    estado: 'ABIERTO', generado_en: '2026-10-22T10:00:00Z',
    alcance: { sucursal: 'Roma', departamento: 'Playeras' },
    totales: { faltantes_piezas: '5', sobrantes_piezas: '1', fuera_de_alcance_piezas: '1', desconocidos: 2 },
    faltantes: [fila('A', '-3'), fila('B', '-2')],
    sobrantes: [fila('C', '1')],
    fuera_de_alcance: [fila('D', '0')],
    desconocidos: [{ codigo: 'X', contado: '1' }, { codigo: 'Y', contado: '1' }],
  }

  it('devuelve las cuatro secciones con título, conteo de filas y piezas', () => {
    const s = seccionesReporte(reporte)
    expect(s.map((x) => x.clave)).toEqual(['faltantes', 'sobrantes', 'fuera_de_alcance', 'desconocidos'])
    expect(s[0]).toMatchObject({ titulo: 'Faltantes', filas: 2, piezas: 5 })
    expect(s[1]).toMatchObject({ titulo: 'Sobrantes', filas: 1, piezas: 1 })
    expect(s[2]).toMatchObject({ titulo: 'Fuera de departamento', filas: 1, piezas: 1 })
    expect(s[3]).toMatchObject({ titulo: 'Desconocidos', filas: 2, piezas: 2 })
  })
})

describe('num', () => {
  it('convierte el Decimal en cadena y tolera vacíos', () => {
    expect(num('3.00')).toBe(3)
    expect(num(null)).toBe(0)
    expect(num('x')).toBe(0)
  })
})
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/pages/inventory/conteos`
Expected: FAIL, no existe `../avance`

- [ ] **Step 3: Cliente API**

```ts
// frontend/src/api/conteos.ts
import client from './client'

/**
 * Conteo físico con escáner (`/api/inventory/counts`). Los Numeric del
 * backend llegan como cadena ("3.00"): convertir con `num()` de
 * pages/inventory/conteos/avance.ts, nunca con `Number()` a ciegas.
 */

export interface ProductoResumen {
  variant_id: string
  nombre: string
  marca: string | null
  talla: string | null
  color: string | null
  sku: string | null
  barcode: string | null
  foto: string | null
  departamento: string | null
}

export interface Linea {
  id: number
  variant_id: string | null
  codigo: string | null
  qty_contada: string
  qty_sistema: string | null
  producto: ProductoResumen | null
  updated_at: string | null
}

export interface Avance {
  esperadas_variantes: number
  esperadas_piezas: string
  contadas_variantes: number
  contadas_piezas: string
  desconocidos: number
}

export interface Conteo {
  id: number
  branch_id: number
  branch_name: string | null
  department_id: string | null
  department_name: string | null
  status: 'ABIERTO' | 'CERRADO'
  notes: string | null
  created_by: string | null
  created_at: string | null
  closed_at: string | null
  avance: Avance
}

export interface ConteoDetalle extends Conteo { lineas: Linea[] }

export interface ScanResult {
  resultado: 'contado' | 'ambiguo' | 'desconocido'
  linea: Linea | null
  producto: ProductoResumen | null
  qty_sistema: string | null
  fuera_de_alcance: boolean
  candidatos: ProductoResumen[]
}

export interface FilaReporte {
  variant_id: string
  sku: string | null
  nombre: string
  marca: string | null
  talla: string | null
  color: string | null
  departamento: string | null
  sistema: string
  contado: string
  diferencia: string
}

export interface Reporte {
  estado: 'ABIERTO' | 'CERRADO'
  generado_en: string
  alcance: { sucursal: string | null; departamento: string | null }
  totales: Record<string, string | number>
  faltantes: FilaReporte[]
  sobrantes: FilaReporte[]
  fuera_de_alcance: FilaReporte[]
  desconocidos: { codigo: string; contado: string }[]
}

export const conteosApi = {
  listar: async (params?: { status?: string; branch_id?: number }): Promise<Conteo[]> => {
    const { data } = await client.get<Conteo[]>('/inventory/counts/', { params })
    return data
  },
  crear: async (body: { branch_id: number | null; department_id: string | null; notes?: string }): Promise<Conteo> => {
    const { data } = await client.post<Conteo>('/inventory/counts/', body)
    return data
  },
  ver: async (id: number): Promise<ConteoDetalle> => {
    const { data } = await client.get<ConteoDetalle>(`/inventory/counts/${id}`)
    return data
  },
  escanear: async (id: number, code: string): Promise<ScanResult> => {
    const { data } = await client.post<ScanResult>(`/inventory/counts/${id}/scan`, { code })
    return data
  },
  agregarLinea: async (id: number, variantId: string, qty = 1): Promise<Linea> => {
    const { data } = await client.post<Linea>(`/inventory/counts/${id}/lines`, { variant_id: variantId, qty: String(qty) })
    return data
  },
  fijarLinea: async (id: number, lineId: number, qty: number): Promise<Linea | null> => {
    const { data } = await client.patch<Linea | null>(`/inventory/counts/${id}/lines/${lineId}`, { qty_contada: String(qty) })
    return data
  },
  borrarLinea: async (id: number, lineId: number): Promise<void> => {
    await client.delete(`/inventory/counts/${id}/lines/${lineId}`)
  },
  cerrar: async (id: number): Promise<ConteoDetalle> => {
    const { data } = await client.post<ConteoDetalle>(`/inventory/counts/${id}/close`)
    return data
  },
  reporte: async (id: number): Promise<Reporte> => {
    const { data } = await client.get<Reporte>(`/inventory/counts/${id}/report`)
    return data
  },
}
```

- [ ] **Step 4: Helpers puros**

```ts
// frontend/src/pages/inventory/conteos/avance.ts
import type { Reporte } from '../../../api/conteos'

/** Decimal del backend ("3.00") a número; vacío o basura = 0. */
export function num(v: string | number | null | undefined): number {
  if (v === null || v === undefined || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** Porcentaje entero 0-100 de variantes contadas sobre esperadas. */
export function porcentajeAvance(contadas: number, esperadas: number): number {
  if (esperadas <= 0) return 0
  return Math.min(100, Math.round((contadas / esperadas) * 100))
}

/** "faltan 3" / "falta 1" / "sobra 1" / "sobran 2" / "cuadra". */
export function textoDiferencia(diferencia: number): string {
  if (diferencia === 0) return 'cuadra'
  const n = Math.abs(diferencia)
  if (diferencia < 0) return n === 1 ? 'falta 1' : `faltan ${n}`
  return n === 1 ? 'sobra 1' : `sobran ${n}`
}

export interface Seccion {
  clave: 'faltantes' | 'sobrantes' | 'fuera_de_alcance' | 'desconocidos'
  titulo: string
  filas: number
  piezas: number
}

/** Las cuatro secciones del reporte en el orden en que se leen. */
export function seccionesReporte(r: Reporte): Seccion[] {
  return [
    { clave: 'faltantes', titulo: 'Faltantes', filas: r.faltantes.length, piezas: num(r.totales.faltantes_piezas) },
    { clave: 'sobrantes', titulo: 'Sobrantes', filas: r.sobrantes.length, piezas: num(r.totales.sobrantes_piezas) },
    { clave: 'fuera_de_alcance', titulo: 'Fuera de departamento', filas: r.fuera_de_alcance.length, piezas: num(r.totales.fuera_de_alcance_piezas) },
    { clave: 'desconocidos', titulo: 'Desconocidos', filas: r.desconocidos.length, piezas: r.desconocidos.reduce((s, d) => s + num(d.contado), 0) },
  ]
}
```

- [ ] **Step 5: Correr y ver que pasa**

Run: `cd frontend && npx vitest run src/pages/inventory/conteos`
Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/conteos.ts frontend/src/pages/inventory/conteos
git commit -m "feat(conteos): cliente API y helpers del avance y del reporte"
```

---

### Task 5: Lista de conteos, ruta, menú y modo básico

**Files:**
- Create: `frontend/src/pages/inventory/conteos/Conteos.tsx`
- Modify: `frontend/src/App.tsx` (lazy + rutas), `frontend/src/components/layout/navConfig.ts` (`HQ_NAV_GROUPS` Inventario, `ALL_NAV`, `ROLE_ROUTES` ADMINISTRADOR y DUEÑO), `frontend/src/components/layout/navPerfilBasico.ts` (`OCULTAS_BASICO_HQ`)
- Test: `frontend/src/components/layout/__tests__/navConfig.test.ts` (añadir casos), `frontend/src/components/layout/__tests__/navPerfilBasico.test.ts` (añadir caso)

**Interfaces:**
- Consumes: `conteosApi` (Task 4); `organizationApi.getBranches()` y `productsApi.getDepartments()` (verifica el nombre real en `frontend/src/api/products.ts`: si se llama distinto, usa ese); `useAuthStore`; `useEsTelefono`; kit `CabeceraPagina`, `ListaTarjetas`, `TarjetaFila`, `Modal`, `DaxCard`, `Spinner`; `toast`; `errorDetailText(detail, fallback)` recibe `e?.response?.data?.detail`, no el error entero (ver `pages/labels/Labels.tsx`).
- Produces: componente `Conteos`; rutas `/inventory/conteos`, `/inventory/conteos/:id`, `/inventory/conteos/:id/reporte` (las dos últimas apuntan a componentes de Task 6 y 7; en esta tarea se registran con `ConteoSesion`/`ConteoReporte` como stubs mínimos que solo pintan el título, para que `tsc` pase).

- [ ] **Step 1: Pruebas de navegación que fallan**

En `navConfig.test.ts`, dentro de `describe('el menú de la boutique')`:

```ts
  it('Conteo entra al menú del admin y del dueño con el módulo inventory, no al de la cajera', () => {
    expect(menu('ADMINISTRADOR', BOUTIQUE)).toContain('/inventory/conteos')
    expect(menu('DUEÑO', BOUTIQUE)).toContain('/inventory/conteos')
    expect(menu('CAJERO', BOUTIQUE)).not.toContain('/inventory/conteos')
    expect(menu('ADMINISTRADOR', BOUTIQUE.filter((m) => m !== 'inventory'))).not.toContain('/inventory/conteos')
    expect(HQ_NAV_GROUPS.find((g) => g.header === 'Inventario')?.urls).toContain('/inventory/conteos')
  })
```

En `navPerfilBasico.test.ts` (sigue el patrón de los casos existentes para `/scanner`):

```ts
  it('el conteo con escáner no aparece en el menú básico de la dueña', () => {
    expect(OCULTAS_BASICO_HQ).toContain('/inventory/conteos')
  })
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `cd frontend && npx vitest run src/components/layout`
Expected: 2 FAIL

- [ ] **Step 3: Menú y rutas**

`navConfig.ts`:
- `HQ_NAV_GROUPS` → `Inventario`: `urls: ['/inventory', '/hq/inventory', '/boxes', '/logistics', '/scanner', '/inventory/conteos']`.
- `ALL_NAV`, justo después del ítem Escáner (sort 13.5):
  ```ts
  { label: 'Conteo',            short: 'CNT', icon: 'fa-list-check',           url: '/inventory/conteos', group: 'hq',   sort: 13.6, module: 'inventory' },
  ```
- `ROLE_ROUTES.ADMINISTRADOR` y `ROLE_ROUTES.DUEÑO`: añade `'/inventory/conteos'` justo después de `'/scanner'`.

`navPerfilBasico.ts` → `OCULTAS_BASICO_HQ`: añade `'/inventory/conteos',` en la línea de `'/inventory', '/hq/inventory',`.

`App.tsx`, junto a `StoreScanner`:

```tsx
const Conteos       = lazy(() => import('./pages/inventory/conteos/Conteos').then(m => ({ default: m.Conteos })))
const ConteoSesion  = lazy(() => import('./pages/inventory/conteos/ConteoSesion').then(m => ({ default: m.ConteoSesion })))
const ConteoReporte = lazy(() => import('./pages/inventory/conteos/ConteoReporte').then(m => ({ default: m.ConteoReporte })))
```

Rutas, junto a la de `scanner` (misma sección de rutas planas):

```tsx
          {/* Conteo físico con escáner — sesiones por departamento, solo reporte
              (spec 2026-10-22). Admin/dueño; el módulo `inventory` gatea en el backend. */}
          <Route path="inventory/conteos" element={<RutaPorRol url="/inventory/conteos"><Suspense fallback={<PageLoader />}><Conteos /></Suspense></RutaPorRol>} />
          <Route path="inventory/conteos/:id" element={<RutaPorRol url="/inventory/conteos"><Suspense fallback={<PageLoader />}><ConteoSesion /></Suspense></RutaPorRol>} />
          <Route path="inventory/conteos/:id/reporte" element={<RutaPorRol url="/inventory/conteos"><Suspense fallback={<PageLoader />}><ConteoReporte /></Suspense></RutaPorRol>} />
```

Si `/inventory` ya tiene una `<Route path="inventory">` con hijos, coloca estas tres ANTES de ella como rutas planas para que el `:id` no choque.

Stubs (se reemplazan en Task 6 y 7):

```tsx
// frontend/src/pages/inventory/conteos/ConteoSesion.tsx
export function ConteoSesion() { return <h1 className="text-2xl font-black text-white">Conteo</h1> }
```

```tsx
// frontend/src/pages/inventory/conteos/ConteoReporte.tsx
export function ConteoReporte() { return <h1 className="text-2xl font-black text-white">Reporte del conteo</h1> }
```

- [ ] **Step 4: Pantalla de lista**

```tsx
// frontend/src/pages/inventory/conteos/Conteos.tsx
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { conteosApi, type Conteo } from '../../../api/conteos'
import { organizationApi } from '../../../api/organization'
import { productsApi } from '../../../api/products'
import { CabeceraPagina } from '../../../components/ui/CabeceraPagina'
import { DaxCard } from '../../../components/ui/DaxCard'
import { ListaTarjetas } from '../../../components/ui/ListaTarjetas'
import { Modal } from '../../../components/ui/Modal'
import { Spinner } from '../../../components/ui/Spinner'
import { TarjetaFila } from '../../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../../hooks/useIsMobile'
import { useAuthStore } from '../../../store/authStore'
import { toast } from '../../../store/toastStore'
import type { Branch } from '../../../types/auth'
import type { Department } from '../../../types/products'
import { errorDetailText } from '../../../utils/errorDetail'
import { num, porcentajeAvance } from './avance'

/**
 * Conteo de inventario — lista de sesiones y alta de una nueva.
 *
 * Una sesión es una sucursal y un departamento (o toda la tienda). Abierta
 * entra a la pantalla de escaneo; cerrada, al reporte. La sucursal se
 * recuerda en el dispositivo con la misma clave que el Escáner.
 * Diseño: docs/superpowers/specs/2026-10-22-conteo-inventario-design.md §6.
 */

const BRANCH_KEY = 'atlas_scanner_branch_id'
const TODA_LA_TIENDA = ''

function fecha(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })
}

export function Conteos() {
  const navigate = useNavigate()
  const esTelefono = useEsTelefono()
  const user = useAuthStore((s) => s.user)

  const [conteos, setConteos] = useState<Conteo[] | null>(null)
  const [branches, setBranches] = useState<Branch[]>([])
  const [departamentos, setDepartamentos] = useState<Department[]>([])
  const [abrir, setAbrir] = useState(false)
  const [branchId, setBranchId] = useState<number | null>(() => {
    const s = localStorage.getItem(BRANCH_KEY)
    return s ? Number(s) : null
  })
  const [departmentId, setDepartmentId] = useState<string>(TODA_LA_TIENDA)
  const [notes, setNotes] = useState('')
  const [guardando, setGuardando] = useState(false)

  const effectiveBranchId = user?.branch_id ?? branchId

  const cargar = useCallback(async () => {
    try {
      setConteos(await conteosApi.listar())
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudieron cargar los conteos'))
      setConteos([])
    }
  }, [])

  useEffect(() => { void cargar() }, [cargar])
  useEffect(() => {
    void productsApi.getDepartments().then(setDepartamentos).catch(() => setDepartamentos([]))
    if (!user?.branch_id) {
      void organizationApi.getBranches()
        .then((bs) => setBranches(bs.filter((b) => b.branch_type !== 'HQ')))
        .catch(() => setBranches([]))
    }
  }, [user?.branch_id])

  const crear = async () => {
    if (!effectiveBranchId) { toast.warning('Elige la sucursal que vas a contar'); return }
    setGuardando(true)
    try {
      if (!user?.branch_id && branchId) localStorage.setItem(BRANCH_KEY, String(branchId))
      const c = await conteosApi.crear({
        branch_id: effectiveBranchId, department_id: departmentId || null, notes: notes.trim() || undefined,
      })
      setAbrir(false)
      navigate(`/inventory/conteos/${c.id}`)
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo abrir el conteo'))
    } finally {
      setGuardando(false)
    }
  }

  const ir = (c: Conteo) => navigate(c.status === 'ABIERTO' ? `/inventory/conteos/${c.id}` : `/inventory/conteos/${c.id}/reporte`)

  const avanceTxt = (c: Conteo) =>
    `${num(c.avance.contadas_piezas)} / ${num(c.avance.esperadas_piezas)} piezas · ${porcentajeAvance(c.avance.contadas_variantes, c.avance.esperadas_variantes)}%`

  return (
    <div className="space-y-4 pb-24">
      <CabeceraPagina
        titulo={<div className="flex items-center gap-3">
          <i className="fa-solid fa-list-check text-indigo-400 text-xl" />
          <h1 className="text-2xl font-black text-white">Conteo de inventario</h1>
        </div>}
        descripcion="Escanea un departamento completo y compara contra el sistema. Nada se ajusta hasta que tú lo decidas."
        accionPrincipal={<button onClick={() => setAbrir(true)} className="dax-btn-primary text-xs">
          <i className="fa-solid fa-plus" /> Nuevo conteo
        </button>}
      />

      {conteos === null ? <Spinner /> : esTelefono ? (
        <ListaTarjetas vacio={conteos.length === 0} textoVacio="Todavía no hay conteos. Abre el primero.">
          {conteos.map((c) => (
            <TarjetaFila
              key={c.id}
              titulo={c.department_name ?? 'Toda la tienda'}
              subtitulo={`${c.branch_name ?? ''} · ${fecha(c.created_at)}${c.created_by ? ` · ${c.created_by}` : ''}`}
              estado={<span className={c.status === 'ABIERTO' ? 'text-emerald-400' : 'text-slate-400'}>{c.status === 'ABIERTO' ? 'Abierto' : 'Cerrado'}</span>}
              datos={[{ etiqueta: 'Avance', valor: avanceTxt(c) }]}
              onClick={() => ir(c)}
            />
          ))}
        </ListaTarjetas>
      ) : (
        <DaxCard padding={false}>
          <table className="w-full text-sm">
            <thead className="text-xs text-slate-400 uppercase">
              <tr><th className="text-left p-3">Departamento</th><th className="text-left p-3">Sucursal</th><th className="text-left p-3">Fecha</th><th className="text-left p-3">Avance</th><th className="text-left p-3">Estado</th><th className="p-3" /></tr>
            </thead>
            <tbody>
              {conteos.length === 0 && <tr><td colSpan={6} className="p-6 text-center text-slate-400">Todavía no hay conteos. Abre el primero.</td></tr>}
              {conteos.map((c) => (
                <tr key={c.id} className="border-t border-slate-800 hover:bg-slate-800/40 cursor-pointer" onClick={() => ir(c)}>
                  <td className="p-3 text-white font-semibold">{c.department_name ?? 'Toda la tienda'}</td>
                  <td className="p-3 text-slate-300">{c.branch_name}</td>
                  <td className="p-3 text-slate-300">{fecha(c.created_at)}{c.created_by ? ` · ${c.created_by}` : ''}</td>
                  <td className="p-3 text-slate-300">{avanceTxt(c)}</td>
                  <td className={`p-3 ${c.status === 'ABIERTO' ? 'text-emerald-400' : 'text-slate-400'}`}>{c.status === 'ABIERTO' ? 'Abierto' : 'Cerrado'}</td>
                  <td className="p-3 text-right"><i className="fa-solid fa-chevron-right text-slate-500" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </DaxCard>
      )}

      <Modal open={abrir} onClose={() => setAbrir(false)} title="Nuevo conteo" size="sm"
        footer={<>
          <button onClick={() => setAbrir(false)} className="dax-btn-secondary flex-1">Cancelar</button>
          <button onClick={crear} disabled={guardando} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
            {guardando ? <i className="fa-solid fa-spinner fa-spin" /> : 'Abrir conteo'}
          </button>
        </>}>
        <div className="space-y-3">
          {!user?.branch_id && (
            <label className="block">
              <span className="text-xs text-slate-400">Sucursal</span>
              <select className="dax-input w-full" value={branchId ?? ''} onChange={(e) => setBranchId(e.target.value ? Number(e.target.value) : null)}>
                <option value="">Elige…</option>
                {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </label>
          )}
          <label className="block">
            <span className="text-xs text-slate-400">Departamento</span>
            <select className="dax-input w-full" value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}>
              <option value={TODA_LA_TIENDA}>Toda la tienda</option>
              {departamentos.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-xs text-slate-400">Notas (opcional)</span>
            <input className="dax-input w-full" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Pared izquierda, estante 2…" />
          </label>
        </div>
      </Modal>
    </div>
  )
}
```

Si la clase `dax-input` no existe en `index.css`, usa la clase de input que usen los formularios del kit (busca `className="dax-` en `pages/inventory/Boxes.tsx` y copia la del `<input>`).

- [ ] **Step 5: Correr pruebas y tsc**

Run: `cd frontend && npx vitest run src/components/layout src/pages/inventory/conteos && npx tsc --noEmit -p .`
Expected: pruebas en verde y `tsc` sin errores.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/layout frontend/src/pages/inventory/conteos
git commit -m "feat(conteos): lista de conteos, rutas, menú Inventario y modo básico"
```

---

### Task 6: Pantalla de sesión (cámara, escaneo, lista, buscador, desconocidos)

**Files:**
- Create: `frontend/src/pages/inventory/conteos/useLectorCodigos.ts`, `frontend/src/pages/inventory/conteos/ConteoSesion.tsx` (reemplaza el stub), `frontend/src/pages/inventory/conteos/BuscadorVariante.tsx`
- Test: `frontend/src/pages/inventory/conteos/__tests__/sesion.test.ts`

**Interfaces:**
- Consumes: `createDetector`, `isNativeDetectorAvailable`, `normalizeCode`, `normalizeTyped` (`pages/scanner/barcodeReader.ts`); `conteosApi`; `productsApi.posSearch(q)` y `productsApi.updateVariant(id, {barcode})`; `confirm` de `ui/ConfirmDialog`; `Modal`; `toast`.
- Produces: hook `useLectorCodigos({ onCodigo, pausado }): { videoRef, canvasRef, camOn, camError, start, stop }`; componente `BuscadorVariante({ open, onClose, onElegir(producto: ProductoResumen) })`; helper puro `vibrar(tipo: 'ok' | 'aviso')` y `resumenDesdeProducto(p: Product, v: ProductVariant): ProductoResumen` en `sesion.ts`.

- [ ] **Step 1: Prueba del helper puro que falla**

```ts
// frontend/src/pages/inventory/conteos/__tests__/sesion.test.ts
import { describe, it, expect, vi, afterEach } from 'vitest'

import { resumenDesdeProducto, vibrar } from '../sesion'

describe('vibrar', () => {
  afterEach(() => { vi.unstubAllGlobals() })
  it('usa el patrón corto para ok y el triple para aviso, y no truena sin vibrate', () => {
    const vibrate = vi.fn()
    vi.stubGlobal('navigator', { vibrate })
    vibrar('ok'); vibrar('aviso')
    expect(vibrate).toHaveBeenNthCalledWith(1, 60)
    expect(vibrate).toHaveBeenNthCalledWith(2, [60, 60, 60])
    vi.stubGlobal('navigator', {})
    expect(() => vibrar('ok')).not.toThrow()
  })
})

describe('resumenDesdeProducto', () => {
  it('toma la talla elegida del buscador y el nombre de venta de la variante', () => {
    const r = resumenDesdeProducto(
      { id: 'p', name: 'Playera', brand_name: 'Zegna', image_url: null, department_name: 'Playeras' } as never,
      { id: 'v1', sku: 'ZEG-M', barcode: null, size: 'M', color: 'Rojo', sale_name: 'Zegna · Playera · Rojo, Talla M' } as never,
    )
    expect(r).toEqual({
      variant_id: 'v1', nombre: 'Zegna · Playera · Rojo, Talla M', marca: 'Zegna', talla: 'M', color: 'Rojo',
      sku: 'ZEG-M', barcode: null, foto: null, departamento: 'Playeras',
    })
  })
})
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/pages/inventory/conteos`
Expected: FAIL, no existe `../sesion`

- [ ] **Step 3: Helpers puros**

```ts
// frontend/src/pages/inventory/conteos/sesion.ts
import type { ProductoResumen } from '../../../api/conteos'
import type { Product, ProductVariant } from '../../../types/products'

/** Vibración corta al contar; triple cuando hay que mirar la pantalla. Sin API (PC) no hace nada. */
export function vibrar(tipo: 'ok' | 'aviso'): void {
  const v = (globalThis as { navigator?: { vibrate?: (p: number | number[]) => boolean } }).navigator?.vibrate
  if (typeof v !== 'function') return
  try { v.call(navigator, tipo === 'ok' ? 60 : [60, 60, 60]) } catch { /* Safari no vibra */ }
}

/** Lo que el buscador devuelve (producto + talla elegida) en la forma que usa la sesión. */
export function resumenDesdeProducto(p: Product, v: ProductVariant): ProductoResumen {
  return {
    variant_id: v.id,
    nombre: v.sale_name ?? p.sale_name ?? p.name,
    marca: p.brand_name ?? null,
    talla: v.size ?? null,
    color: v.color ?? null,
    sku: v.sku ?? null,
    barcode: v.barcode ?? null,
    foto: p.image_url ?? null,
    departamento: p.department_name ?? p.department?.name ?? null,
  }
}
```

- [ ] **Step 4: Hook de cámara**

```ts
// frontend/src/pages/inventory/conteos/useLectorCodigos.ts
import { useCallback, useEffect, useRef, useState } from 'react'

import { createDetector, normalizeCode } from '../../scanner/barcodeReader'

/**
 * Cámara + detector, portado de `pages/scanner/StoreScanner.tsx` con una
 * diferencia: `pausado`. En el conteo la misma pieza quieta frente a la
 * cámara NO debe contarse una vez por cuadro, así que tras cada lectura la
 * pantalla pausa la detección y el usuario reanuda con "Siguiente". Al
 * reanudar se olvida el último código para que la pieza idéntica siguiente
 * sí cuente.
 */
export function useLectorCodigos({ onCodigo, pausado }: { onCodigo: (code: string) => void; pausado: boolean }) {
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const loopRef = useRef<number | null>(null)
  const lastCodeRef = useRef('')
  const pausadoRef = useRef(pausado)
  const cancelledRef = useRef(false)
  const onCodigoRef = useRef(onCodigo)
  const [camOn, setCamOn] = useState(false)
  const [camError, setCamError] = useState<string | null>(null)

  useEffect(() => { onCodigoRef.current = onCodigo }, [onCodigo])
  useEffect(() => {
    pausadoRef.current = pausado
    if (!pausado) lastCodeRef.current = ''
  }, [pausado])

  const stop = useCallback(() => {
    if (loopRef.current) { window.clearInterval(loopRef.current); loopRef.current = null }
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    lastCodeRef.current = ''
    if (videoRef.current) videoRef.current.srcObject = null
    setCamOn(false)
  }, [])

  const start = useCallback(async () => {
    setCamError(null)
    cancelledRef.current = false
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } } })
      if (cancelledRef.current) { stream.getTracks().forEach((t) => t.stop()); return }
      streamRef.current = stream
      if (videoRef.current) { videoRef.current.srcObject = stream; await videoRef.current.play() }
      setCamOn(true)
      let detector
      try {
        detector = await createDetector()
      } catch (err) {
        stop()
        setCamError(err instanceof Error ? err.message : 'Este navegador no puede leer códigos de barras con la cámara.')
        return
      }
      if (cancelledRef.current) { stop(); return }
      loopRef.current = window.setInterval(async () => {
        if (pausadoRef.current) return
        const video = videoRef.current
        const canvas = canvasRef.current
        if (!video || !canvas || video.readyState < 2) return
        canvas.width = video.videoWidth
        canvas.height = video.videoHeight
        canvas.getContext('2d')?.drawImage(video, 0, 0)
        try {
          const hits = await detector.detect(canvas)
          const clean = normalizeCode(hits?.[0]?.rawValue)
          if (clean && clean !== lastCodeRef.current) {
            lastCodeRef.current = clean
            onCodigoRef.current(clean)
          }
        } catch { /* cuadro sin código: lo normal entre lecturas */ }
      }, 400)
    } catch {
      setCamError('No se pudo abrir la cámara. Revisa el permiso del navegador para este sitio, o teclea el código a mano.')
      setCamOn(false)
    }
  }, [stop])

  useEffect(() => () => { cancelledRef.current = true; stop() }, [stop])

  return { videoRef, canvasRef, camOn, camError, start, stop }
}
```

- [ ] **Step 5: Buscador de variante**

```tsx
// frontend/src/pages/inventory/conteos/BuscadorVariante.tsx
import { useEffect, useState } from 'react'

import type { ProductoResumen } from '../../../api/conteos'
import { productsApi } from '../../../api/products'
import { Modal } from '../../../components/ui/Modal'
import { Spinner } from '../../../components/ui/Spinner'
import type { Product } from '../../../types/products'
import { resumenDesdeProducto } from './sesion'

/** Busca por nombre/SKU (`posSearch`, parcial) y deja elegir la talla. */
export function BuscadorVariante({ open, onClose, onElegir, titulo = 'Buscar pieza' }: {
  open: boolean
  onClose: () => void
  onElegir: (p: ProductoResumen) => void
  titulo?: string
}) {
  const [q, setQ] = useState('')
  const [resultados, setResultados] = useState<Product[]>([])
  const [buscando, setBuscando] = useState(false)

  useEffect(() => {
    if (!open) { setQ(''); setResultados([]); return }
  }, [open])

  useEffect(() => {
    const texto = q.trim()
    if (texto.length < 2) { setResultados([]); return }
    const t = window.setTimeout(async () => {
      setBuscando(true)
      try { setResultados(await productsApi.posSearch(texto, 'name_asc')) } catch { setResultados([]) } finally { setBuscando(false) }
    }, 300)
    return () => window.clearTimeout(t)
  }, [q])

  return (
    <Modal open={open} onClose={onClose} title={titulo} size="md">
      <input autoFocus className="dax-input w-full" placeholder="Nombre, marca o SKU…" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="mt-3 space-y-2 max-h-[60vh] overflow-y-auto">
        {buscando && <Spinner />}
        {!buscando && q.trim().length >= 2 && resultados.length === 0 && <p className="text-sm text-slate-400">Sin resultados.</p>}
        {resultados.map((p) => (
          <div key={p.id} className="rounded-lg border border-slate-800 p-2">
            <div className="text-sm text-white font-semibold">{p.sale_name ?? p.name}</div>
            <div className="mt-1 flex flex-wrap gap-1">
              {(p.variants ?? []).map((v) => (
                <button key={v.id} type="button" className="dax-btn-secondary text-xs"
                  onClick={() => { onElegir(resumenDesdeProducto(p, v)); onClose() }}>
                  {[v.color, v.size].filter(Boolean).join(' / ') || v.sku}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Modal>
  )
}
```

- [ ] **Step 6: Pantalla de sesión**

```tsx
// frontend/src/pages/inventory/conteos/ConteoSesion.tsx
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { conteosApi, type ConteoDetalle, type Linea, type ProductoResumen, type ScanResult } from '../../../api/conteos'
import { productsApi } from '../../../api/products'
import { confirm } from '../../../components/ui/ConfirmDialog'
import { DaxCard } from '../../../components/ui/DaxCard'
import { Modal } from '../../../components/ui/Modal'
import { Spinner } from '../../../components/ui/Spinner'
import { toast } from '../../../store/toastStore'
import { errorDetailText } from '../../../utils/errorDetail'
import { isNativeDetectorAvailable, normalizeTyped } from '../../scanner/barcodeReader'
import { num, porcentajeAvance } from './avance'
import { BuscadorVariante } from './BuscadorVariante'
import { vibrar } from './sesion'
import { useLectorCodigos } from './useLectorCodigos'

/**
 * Sesión de conteo: escanear, ver la pieza, seguir. La lista siempre se
 * vuelve a leer del servidor, así que recargar o cambiar de teléfono no
 * pierde nada. Diseño: spec 2026-10-22 §6.
 */
export function ConteoSesion() {
  const { id } = useParams()
  const conteoId = Number(id)
  const navigate = useNavigate()

  const [conteo, setConteo] = useState<ConteoDetalle | null>(null)
  const [ultimo, setUltimo] = useState<ScanResult | null>(null)
  const [pausado, setPausado] = useState(false)
  const [tecleado, setTecleado] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [buscar, setBuscar] = useState(false)
  const [ligarCodigo, setLigarCodigo] = useState<string | null>(null)   // código desconocido que se va a ligar
  const [candidatos, setCandidatos] = useState<ProductoResumen[] | null>(null)

  const recargar = useCallback(async () => {
    try { setConteo(await conteosApi.ver(conteoId)) } catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo abrir el conteo')) }
  }, [conteoId])
  useEffect(() => { void recargar() }, [recargar])

  const procesar = useCallback(async (code: string) => {
    if (ocupado) return
    setOcupado(true)
    setPausado(true)
    try {
      const r = await conteosApi.escanear(conteoId, code)
      setUltimo(r)
      if (r.resultado === 'contado') vibrar('ok'); else vibrar('aviso')
      if (r.resultado === 'ambiguo') setCandidatos(r.candidatos)
      await recargar()
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se registró el escaneo; vuelve a intentarlo'))
      setPausado(false)
    } finally {
      setOcupado(false)
    }
  }, [conteoId, ocupado, recargar])

  const lector = useLectorCodigos({ onCodigo: procesar, pausado })

  const siguiente = () => { setUltimo(null); setCandidatos(null); setPausado(false) }

  const masUno = async () => {
    const vid = ultimo?.producto?.variant_id
    if (!vid) return
    try { await conteosApi.agregarLinea(conteoId, vid, 1); vibrar('ok'); await recargar()
      setUltimo((u) => u && u.linea ? { ...u, linea: { ...u.linea, qty_contada: String(num(u.linea.qty_contada) + 1) } } : u)
    } catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo sumar')) }
  }

  const elegido = async (p: ProductoResumen) => {
    try {
      if (ligarCodigo) {
        // Reemplaza el código interno por el de la pieza (igual que el Escáner) y
        // quita la línea de desconocido: la próxima lectura ya empata.
        await productsApi.updateVariant(p.variant_id, { barcode: ligarCodigo })
        const desconocida = conteo?.lineas.find((l) => l.variant_id === null && l.codigo === ligarCodigo)
        if (desconocida) await conteosApi.borrarLinea(conteoId, desconocida.id)
        setLigarCodigo(null)
      }
      await conteosApi.agregarLinea(conteoId, p.variant_id, 1)
      vibrar('ok')
      setUltimo({ resultado: 'contado', linea: null, producto: p, qty_sistema: null, fuera_de_alcance: false, candidatos: [] })
      setCandidatos(null)
      await recargar()
    } catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo registrar la pieza')) }
  }

  const fijar = async (l: Linea, qty: number) => {
    try { await conteosApi.fijarLinea(conteoId, l.id, qty); await recargar() } catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo corregir')) }
  }

  const cerrar = async () => {
    if (!conteo) return
    const faltan = conteo.avance.esperadas_variantes - conteo.avance.contadas_variantes
    const ok = await confirm({
      title: 'Cerrar el conteo',
      message: faltan > 0 ? `Hay ${faltan} tallas con existencia que no se escanearon; quedarán como faltantes en el reporte.` : 'Se congela el reporte con lo contado.',
      confirmText: 'Cerrar y ver reporte', variant: 'warning',
    })
    if (!ok) return
    try { lector.stop(); await conteosApi.cerrar(conteoId); navigate(`/inventory/conteos/${conteoId}/reporte`) } catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo cerrar')) }
  }

  if (!conteo) return <Spinner />
  if (conteo.status === 'CERRADO') { navigate(`/inventory/conteos/${conteoId}/reporte`, { replace: true }); return null }

  const pct = porcentajeAvance(conteo.avance.contadas_variantes, conteo.avance.esperadas_variantes)
  const ultimaLinea = ultimo?.linea ?? conteo.lineas.find((l) => l.variant_id === ultimo?.producto?.variant_id) ?? null

  return (
    <div className="space-y-4 max-w-lg mx-auto pb-24">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-black text-white">{conteo.department_name ?? 'Toda la tienda'}</h1>
          <p className="text-xs text-slate-400">{conteo.branch_name}{conteo.notes ? ` · ${conteo.notes}` : ''}</p>
        </div>
        <button onClick={cerrar} className="dax-btn-secondary text-xs">Cerrar conteo</button>
      </div>

      <DaxCard>
        <div className="flex justify-between text-xs text-slate-400">
          <span>{conteo.avance.contadas_variantes} de {conteo.avance.esperadas_variantes} tallas · {num(conteo.avance.contadas_piezas)} de {num(conteo.avance.esperadas_piezas)} piezas</span>
          <span>{pct}%</span>
        </div>
        <div className="mt-1 h-2 rounded bg-slate-800"><div className="h-2 rounded bg-indigo-500" style={{ width: `${pct}%` }} /></div>
      </DaxCard>

      <DaxCard>
        <div className="relative rounded-lg overflow-hidden bg-black aspect-[4/3]">
          <video ref={lector.videoRef} className="w-full h-full object-cover" muted playsInline />
          <canvas ref={lector.canvasRef} className="hidden" />
          {!lector.camOn && (
            <button onClick={() => void lector.start()} className="dax-btn-primary absolute inset-0 m-auto h-12 w-48">
              <i className="fa-solid fa-camera" /> Encender cámara
            </button>
          )}
          {lector.camOn && pausado && <div className="absolute inset-0 bg-black/60 flex items-center justify-center text-white text-sm">Pausado · toca Siguiente</div>}
        </div>
        {lector.camError && <p className="mt-2 text-xs text-amber-400">{lector.camError}</p>}
        {!isNativeDetectorAvailable() && !lector.camOn && <p className="mt-2 text-xs text-slate-500">En este navegador se carga un lector adicional al encender la cámara.</p>}
        <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); const c = normalizeTyped(tecleado); if (c) { setTecleado(''); void procesar(c) } }}>
          <input className="dax-input flex-1" placeholder="O teclea / pega el código" value={tecleado} onChange={(e) => setTecleado(e.target.value)} />
          <button type="submit" className="dax-btn-secondary">Buscar</button>
        </form>
        <button type="button" onClick={() => { setLigarCodigo(null); setBuscar(true) }} className="dax-btn-ghost mt-2 text-xs"><i className="fa-solid fa-magnifying-glass" /> Sin código: buscar por nombre</button>
      </DaxCard>

      {ultimo && (
        <DaxCard className={ultimo.resultado === 'contado' ? 'border border-emerald-700' : 'border border-amber-700'}>
          {ultimo.resultado === 'contado' && ultimo.producto && (
            <div className="flex gap-3">
              {ultimo.producto.foto && <img src={ultimo.producto.foto} alt="" className="h-20 w-20 rounded object-cover" />}
              <div className="flex-1">
                <div className="text-white font-bold">{ultimo.producto.nombre}</div>
                <div className="text-xs text-slate-400">{ultimo.producto.sku}{ultimo.producto.departamento ? ` · ${ultimo.producto.departamento}` : ''}</div>
                <div className="mt-1 text-sm text-emerald-300">
                  Contadas <b>{num(ultimaLinea?.qty_contada)}</b>{ultimo.qty_sistema != null && <> · sistema <b>{num(ultimo.qty_sistema)}</b></>}
                </div>
                {ultimo.fuera_de_alcance && <div className="text-xs text-amber-400">Esta pieza no es de este departamento; se cuenta y el reporte la separa.</div>}
              </div>
            </div>
          )}
          {ultimo.resultado === 'desconocido' && ultimo.linea && (
            <div>
              <div className="text-white font-bold">Código desconocido: {ultimo.linea.codigo}</div>
              <p className="text-xs text-slate-400 mt-1">No existe en el sistema. Puedes buscar la pieza y ligarle este código, o dejarla como desconocida en el reporte.</p>
              <button onClick={() => { setLigarCodigo(ultimo.linea?.codigo ?? null); setBuscar(true) }} className="dax-btn-secondary mt-2 text-xs"><i className="fa-solid fa-link" /> Buscar y ligar código</button>
            </div>
          )}
          {ultimo.resultado === 'ambiguo' && <div className="text-white font-bold">Varias tallas comparten ese código: elige una.</div>}
          <div className="mt-3 flex gap-2">
            <button onClick={siguiente} className="dax-btn-primary flex-1 justify-center"><i className="fa-solid fa-forward" /> Siguiente</button>
            {ultimo.resultado === 'contado' && <button onClick={masUno} className="dax-btn-secondary flex-1 justify-center">+1 igual</button>}
          </div>
        </DaxCard>
      )}

      <DaxCard>
        <h2 className="text-sm font-bold text-white mb-2">Contado en esta sesión ({conteo.lineas.length})</h2>
        {conteo.lineas.length === 0 && <p className="text-xs text-slate-500">Todavía nada. Escanea la primera pieza.</p>}
        <ul className="divide-y divide-slate-800">
          {conteo.lineas.map((l) => (
            <li key={l.id} className="py-2 flex items-center gap-2">
              <div className="flex-1 min-w-0">
                <div className="text-sm text-white truncate">{l.producto?.nombre ?? `Desconocido · ${l.codigo}`}</div>
                <div className="text-xs text-slate-500">{l.producto?.sku}</div>
              </div>
              <input type="number" min={0} inputMode="numeric" className="dax-input w-16 text-center"
                defaultValue={num(l.qty_contada)} key={`${l.id}-${l.qty_contada}`}
                onBlur={(e) => { const n = Number(e.target.value); if (Number.isFinite(n) && n >= 0 && n !== num(l.qty_contada)) void fijar(l, n) }} />
              <button aria-label="Quitar" onClick={() => void fijar(l, 0)} className="dax-btn-icon dax-btn-ghost"><i className="fa-solid fa-trash" /></button>
            </li>
          ))}
        </ul>
      </DaxCard>

      <BuscadorVariante open={buscar} onClose={() => setBuscar(false)} onElegir={elegido}
        titulo={ligarCodigo ? `Ligar el código ${ligarCodigo} a…` : 'Buscar pieza'} />

      <Modal open={candidatos !== null} onClose={() => setCandidatos(null)} title="¿Cuál es?" size="sm">
        <div className="space-y-2">
          {(candidatos ?? []).map((p) => (
            <button key={p.variant_id} className="dax-btn-secondary w-full justify-start text-left" onClick={() => void elegido(p)}>
              {p.nombre} <span className="text-xs text-slate-400">· {p.sku}</span>
            </button>
          ))}
        </div>
      </Modal>
    </div>
  )
}
```

- [ ] **Step 7: Pruebas, tsc y guardias del kit**

Run: `cd frontend && npx vitest run src/pages/inventory/conteos src/__tests__ && npx tsc --noEmit -p .`
Expected: verde; `overlaysFueraDelKit` y `botonesDelKit` sin quejas (solo `Modal` y clases `dax-btn-*`; el botón de basura lleva `dax-btn-icon`).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/inventory/conteos
git commit -m "feat(conteos): sesión de conteo con cámara, +1 igual, buscador y ligar código"
```

---

### Task 7: Pantalla del reporte

**Files:**
- Create: `frontend/src/pages/inventory/conteos/ConteoReporte.tsx` (reemplaza el stub)

**Interfaces:**
- Consumes: `conteosApi.reporte`, `conteosApi.ver`, `conteosApi.cerrar`; `seccionesReporte`, `textoDiferencia`, `num`; kit `CabeceraPagina`, `DaxCard`, `ListaTarjetas`, `TarjetaFila`, `confirm`; `useEsTelefono`.

- [ ] **Step 1: Pantalla**

```tsx
// frontend/src/pages/inventory/conteos/ConteoReporte.tsx
import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { conteosApi, type Conteo, type FilaReporte, type Reporte } from '../../../api/conteos'
import { CabeceraPagina } from '../../../components/ui/CabeceraPagina'
import { confirm } from '../../../components/ui/ConfirmDialog'
import { DaxCard } from '../../../components/ui/DaxCard'
import { ListaTarjetas } from '../../../components/ui/ListaTarjetas'
import { Spinner } from '../../../components/ui/Spinner'
import { TarjetaFila } from '../../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../../hooks/useIsMobile'
import { toast } from '../../../store/toastStore'
import { errorDetailText } from '../../../utils/errorDetail'
import { num, seccionesReporte, textoDiferencia, type Seccion } from './avance'

/** Reporte del conteo: abierto = avance en vivo; cerrado = congelado. Spec 2026-10-22 §5-§6. */
export function ConteoReporte() {
  const { id } = useParams()
  const conteoId = Number(id)
  const navigate = useNavigate()
  const esTelefono = useEsTelefono()
  const [conteo, setConteo] = useState<Conteo | null>(null)
  const [reporte, setReporte] = useState<Reporte | null>(null)
  const [abiertas, setAbiertas] = useState<Record<string, boolean>>({ faltantes: true })

  const cargar = useCallback(async () => {
    try {
      const [c, r] = await Promise.all([conteosApi.ver(conteoId), conteosApi.reporte(conteoId)])
      setConteo(c); setReporte(r)
    } catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo cargar el reporte')) }
  }, [conteoId])
  useEffect(() => { void cargar() }, [cargar])

  const cerrar = async () => {
    const ok = await confirm({ title: 'Cerrar el conteo', message: 'Se congela el reporte con lo contado hasta ahora.', confirmText: 'Cerrar', variant: 'warning' })
    if (!ok) return
    try { await conteosApi.cerrar(conteoId); await cargar() } catch (e: any) { toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo cerrar')) }
  }

  if (!conteo || !reporte) return <Spinner />
  const secciones = seccionesReporte(reporte)
  const t = reporte.totales

  const filas = (s: Seccion): FilaReporte[] =>
    s.clave === 'desconocidos'
      ? reporte.desconocidos.map((d) => ({ variant_id: d.codigo, sku: d.codigo, nombre: `Código ${d.codigo}`, marca: null, talla: null, color: null, departamento: null, sistema: '0', contado: d.contado, diferencia: d.contado }))
      : reporte[s.clave]

  return (
    <div className="space-y-4 pb-24">
      <CabeceraPagina
        titulo={<div>
          <h1 className="text-2xl font-black text-white">{reporte.alcance.departamento ?? 'Toda la tienda'}</h1>
          <p className="text-xs text-slate-400">{reporte.alcance.sucursal} · {conteo.status === 'CERRADO' ? `cerrado ${conteo.closed_at ? new Date(conteo.closed_at).toLocaleString('es-MX') : ''}` : 'avance en vivo'}{conteo.created_by ? ` · ${conteo.created_by}` : ''}</p>
        </div>}
        acciones={<Link to="/inventory/conteos" className="dax-btn-ghost text-xs">Todos los conteos</Link>}
        accionPrincipal={conteo.status === 'ABIERTO'
          ? <div className="flex gap-2"><button onClick={() => navigate(`/inventory/conteos/${conteoId}`)} className="dax-btn-secondary text-xs">Seguir contando</button><button onClick={cerrar} className="dax-btn-primary text-xs">Cerrar conteo</button></div>
          : undefined}
      />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {[
          ['Esperadas', `${t.esperadas_variantes} tallas · ${num(t.esperadas_piezas)} pzas`],
          ['Contadas', `${t.contadas_variantes} tallas · ${num(t.contadas_piezas)} pzas`],
          ['Cuadradas', `${t.cuadradas_variantes} tallas`],
          ['Diferencia', `−${num(t.faltantes_piezas)} / +${num(t.sobrantes_piezas)} pzas`],
        ].map(([k, v]) => <DaxCard key={k}><div className="text-xs text-slate-400">{k}</div><div className="text-sm text-white font-bold">{v}</div></DaxCard>)}
      </div>

      {secciones.map((s) => (
        <DaxCard key={s.clave} padding={false}>
          <button className="w-full flex items-center justify-between p-3 text-left" onClick={() => setAbiertas((a) => ({ ...a, [s.clave]: !a[s.clave] }))}>
            <span className="text-white font-bold">{s.titulo} <span className="text-slate-400 font-normal text-xs">· {s.filas} {s.clave === 'desconocidos' ? 'códigos' : 'tallas'} · {s.piezas} pzas</span></span>
            <i className={`fa-solid ${abiertas[s.clave] ? 'fa-chevron-up' : 'fa-chevron-down'} text-slate-500`} />
          </button>
          {abiertas[s.clave] && (filas(s).length === 0 ? <p className="px-3 pb-3 text-xs text-slate-500">Nada aquí.</p> : esTelefono ? (
            <div className="px-3 pb-3"><ListaTarjetas>
              {filas(s).map((f) => (
                <TarjetaFila key={f.variant_id} titulo={f.nombre} subtitulo={[f.sku, f.departamento].filter(Boolean).join(' · ')}
                  importe={<span className={num(f.diferencia) < 0 ? 'text-rose-400' : num(f.diferencia) > 0 ? 'text-amber-400' : 'text-slate-300'}>{textoDiferencia(num(f.diferencia))}</span>}
                  datos={[{ etiqueta: 'Sistema', valor: num(f.sistema) }, { etiqueta: 'Contado', valor: num(f.contado) }]} />
              ))}
            </ListaTarjetas></div>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-xs text-slate-400 uppercase"><tr><th className="text-left px-3 py-2">Pieza</th><th className="text-left px-3 py-2">SKU</th><th className="text-right px-3 py-2">Sistema</th><th className="text-right px-3 py-2">Contado</th><th className="text-right px-3 py-2">Diferencia</th></tr></thead>
              <tbody>
                {filas(s).map((f) => (
                  <tr key={f.variant_id} className="border-t border-slate-800">
                    <td className="px-3 py-2 text-white">{f.nombre}{f.departamento && s.clave === 'fuera_de_alcance' ? <span className="text-xs text-slate-400"> · {f.departamento}</span> : null}</td>
                    <td className="px-3 py-2 text-slate-400">{f.sku}</td>
                    <td className="px-3 py-2 text-right text-slate-300">{num(f.sistema)}</td>
                    <td className="px-3 py-2 text-right text-slate-300">{num(f.contado)}</td>
                    <td className={`px-3 py-2 text-right ${num(f.diferencia) < 0 ? 'text-rose-400' : num(f.diferencia) > 0 ? 'text-amber-400' : 'text-slate-300'}`}>{textoDiferencia(num(f.diferencia))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ))}
        </DaxCard>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: tsc, vitest completo y build con presupuesto**

Run: `cd frontend && npx tsc --noEmit -p . && npx vitest run && npm run build && cd .. && python3 scripts/presupuesto_bundle.py`
Expected: todo verde; la ruta crítica no crece (las tres pantallas son lazy). Si `presupuesto_bundle.py` espera otro invocador, usa el comando que documenta `docs/DEPLOY.md`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/inventory/conteos/ConteoReporte.tsx
git commit -m "feat(conteos): reporte en pantalla con faltantes, sobrantes, fuera de departamento y desconocidos"
```

---

### Task 8: Documentación y verificación final

**Files:**
- Modify: `docs/FRONTEND_VIEWS.md` (tres vistas nuevas bajo Inventario, con ruta → archivo → API), `docs/API_REFERENCE.md` (sección "Conteos — `/api/inventory/counts`" con la tabla del spec §3), `docs/DATA_MODEL.md` (las dos tablas, con la nota de `qty_sistema` congelada y las dos `UniqueConstraint`), `docs/modo-basico.md` (fila: Conteo oculto en básico), `CLAUDE.md` §4 (línea `conteos` en `app/modules/`).

- [ ] **Step 1: Documentar**

En cada doc sigue el formato de las entradas vecinas (Etiquetas es el precedente más parecido). En `docs/FRONTEND_VIEWS.md` marca las tres vistas con 📱 y nombra `useLectorCodigos` como reutilización de `pages/scanner/barcodeReader.ts`.

- [ ] **Step 2: Verificación completa**

Run:
```bash
python3 -m pytest -q --ignore=tests/test_cash_complete.py -p no:warnings 2>&1 | tail -2
cd frontend && npx vitest run 2>&1 | tail -4 && npm run build 2>&1 | tail -3
```
Expected: pytest `0 failed`; vitest todo verde; build OK.

- [ ] **Step 3: Commit**

```bash
git add docs CLAUDE.md
git commit -m "docs(conteos): vistas, API, modelo de datos y modo básico del conteo con escáner"
```

- [ ] **Step 4: Reporte al usuario (sin push)**

Una tabla: rama, HEAD, qué cambia, cómo probarlo en el teléfono (abrir `/inventory/conteos`, elegir Playeras, encender cámara), y lo que el usuario decide después: fusionar y desplegar, y con el primer reporte de Eleven en mano la limpieza del catálogo (`scratchpad/eleven-diagnostico-2026-10-22.md`).

---

## Ajuste del 2026-10-22 (proceso real de la tienda): lista primero

El usuario aclaró el proceso: **se lista el departamento completo, se escanea con pistola USB producto por producto, cada lectura palomea la fila (existe en físico) y ahí mismo se verifica y corrige la descripción**. Decisiones confirmadas: lista con palomas y la cámara como alternativa; la lista trae **todo el catálogo del departamento** (también existencia 0); al palomear se ve la ficha y se corrige ahí mismo (nombre, marca, modelo, descripción) y la fila queda marcada como corregida en el reporte. Lo construido en las Tareas 1-8 se conserva; las Tareas 9-11 lo extienden.

### Task 9: Lista del departamento y marca de ficha corregida (backend)

**Files:**
- Modify: `app/modules/conteos/models.py` (columna `corregida` en `InventoryCountLine`), `app/modules/conteos/schemas.py`, `app/modules/conteos/services.py`, `app/modules/conteos/router.py`
- Test: `tests/test_conteos_lista.py`

**Interfaces:**
- Consumes: `_alcance`, `existencias`, `resumen_producto`, `a_linea_read` de services (Task 2).
- Produces: `ProductoResumen` gana `product_id: str`, `marca_id: Optional[str]`, `modelo: Optional[str]`, `descripcion: Optional[str]`, `precio: Optional[Decimal]`; `LineaRead.corregida: bool`; `LineaPatch` pasa a `{qty_contada?: Decimal ≥ 0, corregida?: bool}` (al menos uno); `FilaLista`, `Lista`; `services.lista(db, conteo) -> Lista`; `services.marcar_corregida(db, conteo, linea, valor: bool) -> InventoryCountLine`; `GET /{id}/lista`; `FilaReporte.corregida: bool` y `totales["corregidas"]`.

- [ ] **Step 1: Pruebas que fallan**

```python
# tests/test_conteos_lista.py
"""Lista del departamento con palomas y marca de ficha corregida."""
from decimal import Decimal

import pytest

from app.models.inventory import StockOnHand
from app.models.products import Brand, Department, Product, ProductVariant
from app.modules.conteos import services
from app.modules.conteos.models import ABIERTO, InventoryCount


def _prenda(db, org, branch, *, name, sku, barcode, depto, stock, size="M", brand=None,
            model=None, description=None):
    p = Product(name=name, organization_id=org.id, is_active=True, department_id=depto.id,
                brand_id=brand.id if brand else None, model=model, description=description)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku=sku, barcode=barcode, organization_id=org.id,
                       price=Decimal("1800"), cost=Decimal("900"), size=size, color="Negro")
    db.add(v)
    db.flush()
    if stock is not None:
        db.add(StockOnHand(variant_id=v.id, branch_id=branch.id, organization_id=org.id,
                           qty_on_hand=Decimal(stock), is_active=True))
    db.flush()
    return v


@pytest.fixture()
def tienda(db, org, branch_a):
    marca = Brand(name="Zegna", organization_id=org.id)
    playeras = Department(name="Playeras", organization_id=org.id)
    db.add_all([marca, playeras])
    db.flush()
    a = _prenda(db, org, branch_a, name="Playera", sku="A", barcode="1", depto=playeras,
                stock="2", brand=marca, model="Slim", description="Algodón pima")
    b = _prenda(db, org, branch_a, name="Camisa", sku="B", barcode="2", depto=playeras, stock="1")
    c = _prenda(db, org, branch_a, name="Vieja", sku="C", barcode="3", depto=playeras, stock="0")
    d = _prenda(db, org, branch_a, name="Sin fila", sku="D", barcode="4", depto=playeras, stock=None)
    conteo = InventoryCount(organization_id=org.id, branch_id=branch_a.id,
                            department_id=playeras.id, status=ABIERTO)
    db.add(conteo)
    db.commit()
    return {"a": a, "b": b, "c": c, "d": d, "conteo": conteo}


def test_lista_trae_todo_el_departamento_con_estado(db, tienda):
    c = tienda["conteo"]
    services.escanear(db, c, "1", None)            # a: 1 de 2 → diferencia
    services.escanear(db, c, "2", None)            # b: 1 de 1 → revisado
    lista = services.lista(db, c)
    por_sku = {f.producto.sku: f for f in lista.filas}
    assert set(por_sku) == {"A", "B", "C", "D"}    # también existencia 0 y sin fila de stock
    assert por_sku["A"].estado == "diferencia" and por_sku["A"].contado == Decimal("1")
    assert por_sku["B"].estado == "revisado" and por_sku["B"].line_id is not None
    assert por_sku["C"].estado == "pendiente" and por_sku["C"].sistema == Decimal("0")
    assert por_sku["D"].estado == "pendiente" and por_sku["D"].line_id is None
    assert por_sku["A"].producto.product_id == tienda["a"].product_id
    assert por_sku["A"].producto.modelo == "Slim"
    assert por_sku["A"].producto.descripcion == "Algodón pima"
    assert por_sku["A"].producto.precio == Decimal("1800")
    assert por_sku["A"].producto.marca_id is not None
    assert lista.totales == {"total": 4, "revisados": 1, "pendientes": 2, "con_diferencia": 1, "corregidas": 0}
    # Orden: por nombre de producto y luego talla.
    assert [f.producto.sku for f in lista.filas] == ["B", "A", "D", "C"]


def test_marcar_corregida_y_reporte(db, tienda):
    c = tienda["conteo"]
    r = services.escanear(db, c, "1", None)
    linea = next(l for l in c.lineas if l.id == r.linea.id)
    linea = services.marcar_corregida(db, c, linea, True)
    assert linea.corregida is True
    assert services.a_linea_read(linea).corregida is True
    lista = services.lista(db, c)
    assert next(f for f in lista.filas if f.producto.sku == "A").corregida is True
    assert lista.totales["corregidas"] == 1
    rep = services.reporte(db, c)
    assert next(f for f in rep.faltantes if f.sku == "A").corregida is True
    assert rep.totales["corregidas"] == 1
    assert services.marcar_corregida(db, c, linea, False).corregida is False


def test_lista_api_y_patch_corregida(client, db, org, branch_a, auth_admin, tienda):
    h = {**auth_admin, "X-Organization-ID": str(org.id)}
    cid = tienda["conteo"].id
    r = client.post(f"/api/inventory/counts/{cid}/scan", headers=h, json={"code": "2"})
    lid = r.json()["linea"]["id"]
    assert r.json()["linea"]["corregida"] is False
    r = client.patch(f"/api/inventory/counts/{cid}/lines/{lid}", headers=h, json={"corregida": True})
    assert r.status_code == 200 and r.json()["corregida"] is True and r.json()["qty_contada"] == "1"
    r = client.patch(f"/api/inventory/counts/{cid}/lines/{lid}", headers=h, json={})
    assert r.status_code == 422
    r = client.get(f"/api/inventory/counts/{cid}/lista", headers=h)
    assert r.status_code == 200
    assert r.json()["totales"]["total"] == 4 and r.json()["totales"]["corregidas"] == 1
    fila_b = next(f for f in r.json()["filas"] if f["producto"]["sku"] == "B")
    assert fila_b["estado"] == "revisado" and fila_b["corregida"] is True
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_conteos_lista.py`
Expected: FAIL (`AttributeError: module ... has no attribute 'lista'`, `corregida` inexistente).

- [ ] **Step 3: Modelo**

En `InventoryCountLine` (models.py), después de `qty_sistema`:

```python
    # La ficha del producto se corrigió desde el conteo (nombre/marca/modelo/
    # descripción): el reporte lo lista para saber qué se tocó.
    corregida = Column(Boolean, nullable=False, default=False, server_default="false")
```

(importa `Boolean` de sqlalchemy). La tabla aún no existe en producción: `create_all` la crea con la columna; no hace falta ALTER.

- [ ] **Step 4: Schemas**

```python
class ProductoResumen(BaseModel):
    variant_id: str
    product_id: str
    nombre: str
    marca: Optional[str] = None
    marca_id: Optional[str] = None
    modelo: Optional[str] = None
    descripcion: Optional[str] = None
    precio: Optional[Cant] = None
    talla: Optional[str] = None
    color: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    foto: Optional[str] = None
    departamento: Optional[str] = None
```

`LineaRead`: añade `corregida: bool = False`. `FilaReporte`: añade `corregida: bool = False`.

```python
class LineaPatch(BaseModel):
    """Al menos uno de los dos: cantidad (0 borra) o la marca de ficha corregida."""
    qty_contada: Optional[Decimal] = Field(default=None, ge=0)
    corregida: Optional[bool] = None

    @model_validator(mode="after")
    def _algo_que_cambiar(self):
        if self.qty_contada is None and self.corregida is None:
            raise ValueError("Manda qty_contada o corregida")
        return self


EstadoFila = Literal["pendiente", "revisado", "diferencia"]


class FilaLista(BaseModel):
    producto: ProductoResumen
    sistema: Cant
    contado: Cant
    estado: EstadoFila
    corregida: bool = False
    line_id: Optional[int] = None


class Lista(BaseModel):
    filas: List[FilaLista]
    totales: dict
```

(`from pydantic import model_validator`; `Cant` es el tipo que ya existe en el archivo.)

- [ ] **Step 5: Servicios**

`resumen_producto` devuelve los campos nuevos:

```python
    return ProductoResumen(
        variant_id=v.id, product_id=p.id,
        nombre=variant_sale_name(marca, p.name, p.model, v.color, v.size, v.variant_name),
        marca=marca, marca_id=p.brand_id, modelo=p.model, descripcion=p.description,
        precio=v.price, talla=v.size, color=v.color, sku=v.sku, barcode=v.barcode,
        foto=p.image_url,
        departamento=p.department.name if getattr(p, "department", None) else None,
    )
```

`a_linea_read` incluye `corregida=bool(linea.corregida)`. En `_fila(v, sistema, contado, corregida=False)` añade el parámetro y pásalo en `_calcular`: `corregidas = {l.variant_id: bool(l.corregida) for l in conteo.lineas if l.variant_id}` y `_fila(v, sistema, contado, corregidas.get(v.id, False))` en faltantes/sobrantes/fuera; `totales["corregidas"] = sum(1 for l in conteo.lineas if l.corregida)`.

```python
def marcar_corregida(db: Session, conteo: InventoryCount, linea: InventoryCountLine,
                     valor: bool) -> InventoryCountLine:
    _exigir_abierto(conteo)
    if linea.count_id != conteo.id or linea.organization_id != conteo.organization_id:
        raise HTTPException(404, "Línea no encontrada")
    linea.corregida = bool(valor)
    db.commit()
    db.refresh(linea)
    return linea


def lista(db: Session, conteo: InventoryCount) -> Lista:
    """Todo el catálogo del departamento (también existencia 0) con su estado:
    pendiente (nada contado), revisado (contado == sistema), diferencia."""
    stock = existencias(db, conteo)
    lineas = {l.variant_id: l for l in conteo.lineas if l.variant_id}
    filas: List[FilaLista] = []
    for v in sorted(_alcance(db, conteo), key=lambda x: ((x.product.name or "").lower(), x.size or "", x.color or "")):
        sistema = stock.get(v.id, CERO)
        l = lineas.get(v.id)
        contado = Decimal(l.qty_contada or 0) if l else CERO
        if contado == 0 and l is None:
            estado = "pendiente"
        elif contado == sistema:
            estado = "revisado"
        else:
            estado = "diferencia"
        filas.append(FilaLista(producto=resumen_producto(v), sistema=sistema, contado=contado,
                               estado=estado, corregida=bool(l.corregida) if l else False,
                               line_id=l.id if l else None))
    return Lista(filas=filas, totales={
        "total": len(filas),
        "revisados": sum(1 for f in filas if f.estado == "revisado"),
        "pendientes": sum(1 for f in filas if f.estado == "pendiente"),
        "con_diferencia": sum(1 for f in filas if f.estado == "diferencia"),
        "corregidas": sum(1 for f in filas if f.corregida),
    })
```

Nota: una variante con existencia 0 escaneada una vez queda en `diferencia` (sobrante), como en el reporte. Una línea con qty 0 no existe (PATCH 0 la borra), así que `contado == 0 and l is None` equivale a "nunca escaneada".

- [ ] **Step 6: Router**

```python
@router.patch("/{conteo_id}/lines/{line_id}", response_model=Optional[LineaRead])
def fijar_linea(conteo_id: int, line_id: int, body: LineaPatch, db: Session = Depends(get_db),
                _: User = Depends(_admin), org_id: int = Depends(get_current_active_organization)):
    c = _conteo_o_404(db, org_id, conteo_id)
    l = _linea_o_404(c, line_id)
    if body.corregida is not None:
        l = services.marcar_corregida(db, c, l, body.corregida)
    if body.qty_contada is not None:
        l = services.fijar_linea(db, c, l, body.qty_contada)
    return services.a_linea_read(l) if l is not None else None


@router.get("/{conteo_id}/lista", response_model=Lista)
def lista_conteo(conteo_id: int, db: Session = Depends(get_db), _: User = Depends(_admin),
                 org_id: int = Depends(get_current_active_organization)):
    return services.lista(db, _conteo_o_404(db, org_id, conteo_id))
```

- [ ] **Step 7: Correr pruebas (nuevas + las del módulo) y suite**

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py tests/test_conteos_lista.py tests/test_conteos_api.py tests/test_conteos_services.py tests/test_conteos_models.py`
Expected: todas en verde (las pruebas viejas de PATCH siguen mandando solo `qty_contada`). Luego la suite completa con los dos `--ignore` de integración: `0 failed`.

- [ ] **Step 8: Commit**

```bash
git add app/modules/conteos tests/test_conteos_lista.py
git commit -m "feat(conteos): lista del departamento con estado por fila y marca de ficha corregida"
```

### Task 10: Componentes de la lista con palomas y de la ficha corregible (frontend)

**Files:**
- Modify: `frontend/src/api/conteos.ts` (tipos nuevos, `lista`, `patchLinea`)
- Create: `frontend/src/pages/inventory/conteos/lista.ts`, `frontend/src/pages/inventory/conteos/ListaDepartamento.tsx`, `frontend/src/pages/inventory/conteos/FichaProducto.tsx`
- Test: `frontend/src/pages/inventory/conteos/__tests__/lista.test.ts`

**Interfaces:**
- Consumes: `GET /{id}/lista` y `PATCH /{id}/lines/{line_id}` con `{qty_contada?, corregida?}` (Task 9); `productsApi.update(id, {name, brand_id, model, description})` y `productsApi.getBrands()`; kit `Modal`, `ListaTarjetas`, `TarjetaFila`; `useEsTelefono`; `num`.
- Produces: tipos `FilaLista`, `Lista`, `EstadoFila`; `conteosApi.lista(id)`, `conteosApi.patchLinea(id, lineId, body)`; helpers `filtrarLista(filas, filtro, busqueda)`, `contarPorEstado(filas)`, `iconoEstado(estado)`; componentes `ListaDepartamento` y `FichaProducto` (Task 11 los monta en `ConteoSesion`).

- [ ] **Step 1: Prueba del helper que falla**

```ts
// frontend/src/pages/inventory/conteos/__tests__/lista.test.ts
import { describe, it, expect } from 'vitest'

import { contarPorEstado, filtrarLista, iconoEstado } from '../lista'
import type { FilaLista } from '../../../../api/conteos'

const fila = (sku: string, nombre: string, estado: FilaLista['estado'], marca: string | null = null): FilaLista => ({
  producto: { variant_id: sku, product_id: 'p-' + sku, nombre, marca, marca_id: null, modelo: null, descripcion: null,
    precio: '100', talla: 'M', color: null, sku, barcode: sku, foto: null, departamento: 'Playeras' },
  sistema: '1', contado: estado === 'pendiente' ? '0' : '1', estado, corregida: false, line_id: estado === 'pendiente' ? null : 1,
})
const filas = [fila('A', 'Zegna · Playera', 'revisado', 'Zegna'), fila('B', 'Camisa', 'pendiente'), fila('C', 'Gorra', 'diferencia')]

describe('filtrarLista', () => {
  it('filtra por estado y "todos" deja todo', () => {
    expect(filtrarLista(filas, 'pendientes', '').map((f) => f.producto.sku)).toEqual(['B'])
    expect(filtrarLista(filas, 'revisados', '').map((f) => f.producto.sku)).toEqual(['A', 'C'])
    expect(filtrarLista(filas, 'todos', '')).toHaveLength(3)
  })
  it('busca por nombre, marca, SKU o código sin importar mayúsculas ni acentos', () => {
    expect(filtrarLista(filas, 'todos', 'zegna').map((f) => f.producto.sku)).toEqual(['A'])
    expect(filtrarLista(filas, 'todos', 'c').map((f) => f.producto.sku)).toEqual(['B', 'C'])
    expect(filtrarLista(filas, 'pendientes', 'gorra')).toEqual([])
  })
})

describe('contarPorEstado', () => {
  it('cuenta pendientes, revisados (incluye diferencia) y total', () => {
    expect(contarPorEstado(filas)).toEqual({ pendientes: 1, revisados: 2, total: 3 })
  })
})

describe('iconoEstado', () => {
  it('da paloma verde, alerta ámbar o círculo gris', () => {
    expect(iconoEstado('revisado')).toEqual({ icono: 'fa-circle-check', clase: 'text-emerald-400', texto: 'Revisado' })
    expect(iconoEstado('diferencia')).toEqual({ icono: 'fa-triangle-exclamation', clase: 'text-amber-400', texto: 'Con diferencia' })
    expect(iconoEstado('pendiente')).toEqual({ icono: 'fa-circle', clase: 'text-slate-500', texto: 'Pendiente' })
  })
})
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/pages/inventory/conteos/__tests__/lista.test.ts`
Expected: FAIL, no existe `../lista`

- [ ] **Step 3: Tipos y cliente**

En `frontend/src/api/conteos.ts`: `ProductoResumen` gana `product_id: string`, `marca_id: string | null`, `modelo: string | null`, `descripcion: string | null`, `precio: string | null`; `Linea` y `FilaReporte` ganan `corregida: boolean`. Añade:

```ts
export type EstadoFila = 'pendiente' | 'revisado' | 'diferencia'

export interface FilaLista {
  producto: ProductoResumen
  sistema: string
  contado: string
  estado: EstadoFila
  corregida: boolean
  line_id: number | null
}

export interface Lista {
  filas: FilaLista[]
  totales: { total: number; revisados: number; pendientes: number; con_diferencia: number; corregidas: number }
}
```

y en `conteosApi`:

```ts
  lista: async (id: number): Promise<Lista> => {
    const { data } = await client.get<Lista>(`/inventory/counts/${id}/lista`)
    return data
  },
  patchLinea: async (id: number, lineId: number, body: { qty_contada?: number; corregida?: boolean }): Promise<Linea | null> => {
    const { data } = await client.patch<Linea | null>(`/inventory/counts/${id}/lines/${lineId}`, {
      ...(body.qty_contada !== undefined ? { qty_contada: String(body.qty_contada) } : {}),
      ...(body.corregida !== undefined ? { corregida: body.corregida } : {}),
    })
    return data
  },
```

`fijarLinea` se queda como envoltura: `fijarLinea: (id, lineId, qty) => conteosApi.patchLinea(id, lineId, { qty_contada: qty })`.

- [ ] **Step 4: Helpers puros**

```ts
// frontend/src/pages/inventory/conteos/lista.ts
import type { EstadoFila, FilaLista } from '../../../api/conteos'

export type FiltroLista = 'pendientes' | 'revisados' | 'todos'

const plano = (s: string | null | undefined) =>
  (s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

/** "Revisados" incluye las filas con diferencia: ya se escanearon, solo no cuadran. */
export function filtrarLista(filas: FilaLista[], filtro: FiltroLista, busqueda: string): FilaLista[] {
  const q = plano(busqueda.trim())
  return filas.filter((f) => {
    if (filtro === 'pendientes' && f.estado !== 'pendiente') return false
    if (filtro === 'revisados' && f.estado === 'pendiente') return false
    if (!q) return true
    const p = f.producto
    return [p.nombre, p.marca, p.sku, p.barcode, p.modelo].some((c) => plano(c).includes(q))
  })
}

export function contarPorEstado(filas: FilaLista[]): { pendientes: number; revisados: number; total: number } {
  const pendientes = filas.filter((f) => f.estado === 'pendiente').length
  return { pendientes, revisados: filas.length - pendientes, total: filas.length }
}

export function iconoEstado(estado: EstadoFila): { icono: string; clase: string; texto: string } {
  if (estado === 'revisado') return { icono: 'fa-circle-check', clase: 'text-emerald-400', texto: 'Revisado' }
  if (estado === 'diferencia') return { icono: 'fa-triangle-exclamation', clase: 'text-amber-400', texto: 'Con diferencia' }
  return { icono: 'fa-circle', clase: 'text-slate-500', texto: 'Pendiente' }
}
```

- [ ] **Step 5: Lista del departamento**

```tsx
// frontend/src/pages/inventory/conteos/ListaDepartamento.tsx
import { useEffect, useMemo, useState } from 'react'

import type { FilaLista } from '../../../api/conteos'
import { ListaTarjetas } from '../../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../../hooks/useIsMobile'
import { num } from './avance'
import { contarPorEstado, filtrarLista, iconoEstado, type FiltroLista } from './lista'

/**
 * Checklist del departamento: todas las tallas del catálogo con su paloma.
 * La pistola palomea desde la pantalla (ConteoSesion); aquí solo se muestra,
 * se filtra y se deja corregir la cantidad de las filas ya escaneadas. La
 * fila recién leída se resalta y se trae a la vista.
 */
export function ListaDepartamento({ filas, resaltada, onCantidad, onFicha }: {
  filas: FilaLista[]
  /** variant_id de la última lectura, para resaltar y hacer scroll. */
  resaltada: string | null
  onCantidad: (fila: FilaLista, qty: number) => void
  onFicha: (fila: FilaLista) => void
}) {
  const esTelefono = useEsTelefono()
  const [filtro, setFiltro] = useState<FiltroLista>('pendientes')
  const [busqueda, setBusqueda] = useState('')
  const visibles = useMemo(() => filtrarLista(filas, filtro, busqueda), [filas, filtro, busqueda])
  const n = contarPorEstado(filas)

  useEffect(() => {
    if (!resaltada) return
    document.getElementById(`fila-${resaltada}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [resaltada, filtro])

  const chip = (valor: FiltroLista, etiqueta: string, cuenta: number) => (
    <button type="button" onClick={() => setFiltro(valor)}
      className={filtro === valor ? 'dax-btn-primary text-xs' : 'dax-btn-secondary text-xs'}>
      {etiqueta} <span className="opacity-70">{cuenta}</span>
    </button>
  )

  const cantidad = (f: FilaLista) => f.line_id === null ? (
    <span className="text-slate-500">{num(f.contado)}</span>
  ) : (
    <input type="number" min={0} inputMode="numeric" className="dax-input w-16 text-center"
      defaultValue={num(f.contado)} key={`${f.line_id}-${f.contado}`}
      onBlur={(e) => {
        if (e.target.value.trim() === '') { e.target.value = String(num(f.contado)); return }
        const v = Number(e.target.value)
        if (Number.isFinite(v) && v >= 0 && v !== num(f.contado)) onCantidad(f, v)
      }} />
  )

  const estadoDe = (f: FilaLista) => {
    const e = iconoEstado(f.estado)
    return <span className={e.clase} title={e.texto}><i className={`fa-solid ${e.icono}`} /> {f.corregida && <i className="fa-solid fa-pen text-indigo-400" title="Ficha corregida" />}</span>
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {chip('pendientes', 'Pendientes', n.pendientes)}
        {chip('revisados', 'Revisados', n.revisados)}
        {chip('todos', 'Todos', n.total)}
      </div>
      <input className="dax-input w-full" placeholder="Buscar en el departamento…" value={busqueda} onChange={(e) => setBusqueda(e.target.value)} />

      {esTelefono ? (
        <ListaTarjetas vacio={visibles.length === 0} textoVacio={filtro === 'pendientes' ? 'No queda nada pendiente.' : 'Sin filas.'}>
          {visibles.map((f) => (
            <div key={f.producto.variant_id} id={`fila-${f.producto.variant_id}`}
              className={f.producto.variant_id === resaltada ? 'ring-2 ring-indigo-400 rounded-md' : ''}>
              <TarjetaFila
                titulo={f.producto.nombre}
                subtitulo={[f.producto.sku, f.producto.talla, f.producto.color].filter(Boolean).join(' · ')}
                estado={estadoDe(f)}
                datos={[{ etiqueta: 'Sistema', valor: num(f.sistema) }, { etiqueta: 'Contado', valor: cantidad(f) }]}
                acciones={<button type="button" className="dax-btn-ghost text-xs" onClick={() => onFicha(f)}><i className="fa-solid fa-id-card" /> Ficha</button>}
              />
            </div>
          ))}
        </ListaTarjetas>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-400 uppercase">
            <tr><th className="p-2" /><th className="text-left p-2">Pieza</th><th className="text-left p-2">SKU</th><th className="text-right p-2">Sistema</th><th className="text-right p-2">Contado</th><th className="p-2" /></tr>
          </thead>
          <tbody>
            {visibles.length === 0 && <tr><td colSpan={6} className="p-4 text-center text-slate-500">{filtro === 'pendientes' ? 'No queda nada pendiente.' : 'Sin filas.'}</td></tr>}
            {visibles.map((f) => (
              <tr key={f.producto.variant_id} id={`fila-${f.producto.variant_id}`}
                className={`border-t border-slate-800 ${f.producto.variant_id === resaltada ? 'bg-indigo-500/10' : ''}`}>
                <td className="p-2 text-center">{estadoDe(f)}</td>
                <td className="p-2 text-white">{f.producto.nombre}</td>
                <td className="p-2 text-slate-400">{[f.producto.sku, f.producto.talla].filter(Boolean).join(' · ')}</td>
                <td className="p-2 text-right text-slate-300">{num(f.sistema)}</td>
                <td className="p-2 text-right">{cantidad(f)}</td>
                <td className="p-2 text-right"><button type="button" className="dax-btn-ghost text-xs" onClick={() => onFicha(f)}><i className="fa-solid fa-id-card" /> Ficha</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
```

Si `TarjetaFila` no admite un nodo en `valor` de `datos` (revisa `DatoTarjeta.valor: ReactNode` en `components/ui/TarjetaFila.tsx`; sí lo admite), mantenlo; si no, pon el input en `acciones`.

- [ ] **Step 6: Ficha corregible**

```tsx
// frontend/src/pages/inventory/conteos/FichaProducto.tsx
import { useEffect, useState } from 'react'

import type { ProductoResumen } from '../../../api/conteos'
import { productsApi } from '../../../api/products'
import { Modal } from '../../../components/ui/Modal'
import { toast } from '../../../store/toastStore'
import type { Brand } from '../../../types/products'
import { errorDetailText } from '../../../utils/errorDetail'
import { num } from './avance'

/**
 * Ficha de la pieza recién palomeada, para verificar que la descripción es la
 * correcta, y un formulario corto para corregirla ahí mismo (nombre, marca,
 * modelo, descripción: lo que se lee en la etiqueta y el ticket). Guarda con
 * `PUT /products/{id}` y avisa al conteo para marcar la fila como corregida.
 */
export function FichaProducto({ producto, open, onClose, onCorregida }: {
  producto: ProductoResumen | null
  open: boolean
  onClose: () => void
  /** Se llama tras guardar; el padre marca la línea como corregida y recarga. */
  onCorregida: (producto: ProductoResumen) => Promise<void> | void
}) {
  const [editando, setEditando] = useState(false)
  const [marcas, setMarcas] = useState<Brand[]>([])
  const [form, setForm] = useState({ name: '', brand_id: '', model: '', description: '' })
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    if (!open || !producto) return
    setEditando(false)
    setForm({
      name: producto.nombre.includes(' · ') ? '' : producto.nombre,   // se rellena abajo con el nombre base
      brand_id: producto.marca_id ?? '', model: producto.modelo ?? '', description: producto.descripcion ?? '',
    })
    // El nombre base del producto no viaja en el resumen (viene el nombre de venta);
    // se lee del catálogo al abrir el editor para no adivinarlo.
  }, [open, producto])

  const abrirEditor = async () => {
    if (!producto) return
    try {
      const [p, bs] = await Promise.all([productsApi.getById(producto.product_id), productsApi.getBrands()])
      setMarcas(bs)
      setForm({ name: p.name ?? '', brand_id: p.brand_id ?? '', model: p.model ?? '', description: p.description ?? '' })
      setEditando(true)
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo abrir la ficha'))
    }
  }

  const guardar = async () => {
    if (!producto || !form.name.trim()) { toast.warning('El nombre no puede quedar vacío'); return }
    setGuardando(true)
    try {
      await productsApi.update(producto.product_id, {
        name: form.name.trim(), brand_id: form.brand_id || null, model: form.model.trim() || null,
        description: form.description.trim() || null,
      })
      await onCorregida(producto)
      toast.success('Ficha corregida')
      onClose()
    } catch (e: any) {
      toast.error(errorDetailText(e?.response?.data?.detail, 'No se pudo guardar la ficha'))
    } finally {
      setGuardando(false)
    }
  }

  if (!producto) return null
  return (
    <Modal open={open} onClose={onClose} title={editando ? 'Corregir ficha' : 'Ficha de la pieza'} size="md"
      footer={editando ? (<>
        <button type="button" onClick={() => setEditando(false)} className="dax-btn-secondary flex-1">Cancelar</button>
        <button type="button" onClick={guardar} disabled={guardando} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
          {guardando ? <i className="fa-solid fa-spinner fa-spin" /> : 'Guardar'}
        </button>
      </>) : (<>
        <button type="button" onClick={onClose} className="dax-btn-secondary flex-1">Está bien</button>
        <button type="button" onClick={abrirEditor} className="dax-btn-primary flex-1 justify-center"><i className="fa-solid fa-pen" /> Corregir</button>
      </>)}>
      {!editando ? (
        <div className="flex gap-3">
          {producto.foto && <img src={producto.foto} alt="" className="h-24 w-24 rounded object-cover" />}
          <dl className="text-sm space-y-1 flex-1">
            <div><dt className="text-xs text-slate-400">Nombre de venta</dt><dd className="text-white font-bold">{producto.nombre}</dd></div>
            <div><dt className="text-xs text-slate-400">Marca · modelo</dt><dd className="text-slate-200">{[producto.marca, producto.modelo].filter(Boolean).join(' · ') || '—'}</dd></div>
            <div><dt className="text-xs text-slate-400">Talla · color</dt><dd className="text-slate-200">{[producto.talla, producto.color].filter(Boolean).join(' · ') || '—'}</dd></div>
            <div><dt className="text-xs text-slate-400">Descripción</dt><dd className="text-slate-200 whitespace-pre-wrap">{producto.descripcion || '—'}</dd></div>
            <div><dt className="text-xs text-slate-400">SKU · código · precio</dt><dd className="text-slate-200">{producto.sku} · {producto.barcode ?? 'sin código'} · ${num(producto.precio).toLocaleString('es-MX')}</dd></div>
          </dl>
        </div>
      ) : (
        <div className="space-y-3">
          <label className="block"><span className="text-xs text-slate-400">Nombre</span>
            <input className="dax-input w-full" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label className="block"><span className="text-xs text-slate-400">Marca</span>
            <select className="dax-input w-full" value={form.brand_id} onChange={(e) => setForm({ ...form, brand_id: e.target.value })}>
              <option value="">Sin marca</option>
              {marcas.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select></label>
          <label className="block"><span className="text-xs text-slate-400">Modelo</span>
            <input className="dax-input w-full" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} /></label>
          <label className="block"><span className="text-xs text-slate-400">Descripción</span>
            <textarea className="dax-input w-full" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
        </div>
      )}
    </Modal>
  )
}
```

Verifica el nombre real del método que lee un producto por id en `frontend/src/api/products.ts` (`getById`, `get` o `getProduct`) y úsalo; si `ProductUpdate` no admite `null` en `brand_id`/`model`/`description`, manda `undefined` en su lugar y anota la diferencia en el reporte.

- [ ] **Step 7: Correr pruebas y tsc**

Run: `cd frontend && npx vitest run src/pages/inventory/conteos src/__tests__ && npx tsc --noEmit -p .`
Expected: verde (los componentes nuevos aún no se montan; `tsc` los compila igual).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/conteos.ts frontend/src/pages/inventory/conteos
git commit -m "feat(conteos): lista del departamento con palomas y ficha corregible (componentes)"
```
