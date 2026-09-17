# Variantes de color y talla (preset boutique) — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que una boutique con el preset `ATLAS_POS_BOUTIQUE` capture una prenda con N variantes de color y talla, cada una con su código y su existencia, y que el POS, el Scanner, el inventario y el ticket operen sobre la variante correcta.

**Architecture:** El motor transaccional ya es por `variant_id`; no se toca. El trabajo es (a) agregar `color`/`size` a `product_variants` y un módulo `variants` que gobierna la UI, (b) dejar de aplanar la lectura a `variants[0]` y exponer nombre y existencia por variante, (c) hacer que carrito y venta viajen con `variant_id`, (d) abrir CRUD de variantes y una matriz color×talla en el alta, (e) un selector de variante en el POS y vistas de inventario por variante, y (f) trazabilidad en ticket, reportes e importador.

**Tech Stack:** FastAPI · SQLAlchemy · Pydantic v2 · pytest (SQLite en memoria) · React 18 + TypeScript · Zustand · vitest · PostgreSQL

**Spec:** `docs/superpowers/specs/2026-09-17-variantes-color-talla-design.md`

## Global Constraints

- **`main` es producción con clientes vivos** (Kaory en Railway; Ginebra, Imaltzin y Eleven en el VPS). Trabajar en rama `feat/variantes-color-talla`; no pushear `main` sin permiso.
- **Toda consulta filtra `organization_id`.** Los productos y variantes de otra organización devuelven 404, nunca 403 con datos.
- **Sin Alembic.** Columnas nuevas = `ALTER TABLE … ADD COLUMN` idempotente en `scripts/railway_init.py` (lista `migrations`, tuplas `(tabla, columna, ddl)`), más el atributo en el modelo para que `create_all` la cree en bases nuevas.
- **FKs a `product_variants.id` son `String(36)`.**
- **Nada nuevo visible para las tiendas `ATLAS_POS`.** La UI de variantes y el selector del POS se muestran solo si `enabledModules` incluye `variants`. Las correcciones de lectura deben ser neutras con datos 1:1 (un producto = una variante).
- **Suite verde antes de cada commit:** `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py` (hoy 648 pasan, 2 se saltan, 3 xfail). Frontend: `npx vitest run` (261 pasan), `npx tsc --noEmit` y `npm run build`, desde `frontend/`.
- **Las pruebas de frontend son solo de funciones puras** (`vitest` con `environment: 'node'`, patrón `src/**/*.test.ts`). Toda lógica nueva que valga la pena probar se extrae a un `.ts` sin React.
- **Estilo:** comentarios en español, Pydantic v2, type hints. `HTTPException` con `detail` accionable.
- **`require_module` deja pasar a ADMINISTRADOR/DUEÑO** (`app/core/permissions.py:26`). Es aceptado; la UI es la que gobierna para admins.
- Mensajes de commit terminan con las líneas `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb`.

## Mapa de archivos

| Archivo | Responsabilidad en este plan |
|---|---|
| `scripts/init_presets_v2.py` | catálogo de módulos y presets: módulo `variants`, preset boutique |
| `app/services/capabilities_service.py` | catálogo de arranque y fallback de presets |
| `app/modules/products/models.py` | columnas `color`/`size`, `order_by` de `Product.variants` |
| `app/modules/products/variant_label.py` (nuevo) | etiqueta derivada "Rojo / M" y validación color/talla (puro, sin DB) |
| `scripts/railway_init.py` | ALTERs idempotentes |
| `app/modules/products/schemas.py` | `ProductVariantRead` con nombre/color/talla/stock; `ProductRead.matched_variant_id`; schemas de variantes |
| `app/modules/products/router/_shared.py` | `_compute_product_read` con `primary_variant_id` y stock por variante |
| `app/modules/products/router/search.py` | POS search: variante empatada, caches con todas las variantes |
| `app/modules/products/router/variants.py` (nuevo) | `POST /{product_id}/variants`, `PUT /variants/{id}`, `DELETE /variants/{id}` |
| `app/modules/products/router/core.py` | `create_product` honra `extra_variants`; `read_products` cachea todas las variantes |
| `app/schemas/sales.py` | `SaleItemCreate.variant_id` |
| `app/pos_printer.py`, `app/routers/reports.py` | variante en devoluciones y reportes |
| `scripts/import_products.py`, `router/import_export.py` | color/talla en importación y exportación |
| `frontend/src/types/products.ts`, `types/sales.ts` | tipos con `variant_id`, `color`, `size`, `stock_total` |
| `frontend/src/pages/pos/saleItems.ts` (nuevo) | construcción pura de los renglones de venta (con `variant_id`) |
| `frontend/src/components/pos/ProductSearch.tsx`, `pages/pos/POS.tsx`, `store/posStore.ts` | carrito por variante |
| `frontend/src/components/pos/modals/VariantPickerModal.tsx` (nuevo) | selector de talla/color |
| `frontend/src/components/products/variantMatrix.ts` (nuevo) | generador puro de la matriz color×talla |
| `frontend/src/components/products/ProductVariantsSection.tsx` (nuevo) | sección de variantes del alta/edición |
| `frontend/src/pages/scanner/StoreScanner.tsx`, `pages/scanner/productStock.ts` | Scanner sobre la variante empatada |
| `frontend/src/pages/inventory/variantRows.ts` (nuevo) | expansión pura producto → renglones por variante |
| `frontend/src/api/products.ts` | cliente de los endpoints de variantes |

---

## Fase 0 — Cimientos

### Task 1: Módulo `variants` en el catálogo y en el preset boutique

**Files:**
- Modify: `scripts/init_presets_v2.py` (lista `MODULES_CATALOG` cerca de la línea 31; `PRESETS`, entrada `ATLAS_POS_BOUTIQUE`)
- Modify: `app/services/capabilities_service.py` (constantes `MOD_*` línea 9-31; `INDUSTRY_PRESETS` entrada `ATLAS_POS_BOUTIQUE`; `seed_global_modules` catálogo)
- Test: `tests/test_variants_module.py`

**Interfaces:**
- Produces: clave de módulo `"variants"`, constante `MOD_VARIANTS = "variants"`. Las tareas 8 y siguientes la usan con `require_module("variants")` y en el frontend con `enabledModules.includes('variants')`.

- [ ] **Step 1: Escribir la prueba que falla**

```python
# tests/test_variants_module.py
"""El modulo `variants` gobierna la UI de color/talla. Debe existir en el
catalogo, venir en el preset boutique y NO en ATLAS_POS."""
from app.models.modules import IndustryPreset, Module
from app.modules.tenants.models import IndustryType
from app.services.capabilities_service import (
    apply_industry_preset, get_organization_capabilities, seed_global_modules,
)
from scripts.init_presets_v2 import seed_modules_and_presets


def _preset(db, industry):
    row = db.query(IndustryPreset).filter(IndustryPreset.industry_type == industry).first()
    assert row is not None, industry
    return row


def test_catalogo_v2_tiene_variants(db):
    seed_modules_and_presets(db)
    assert db.query(Module).filter(Module.key == "variants").first() is not None


def test_boutique_trae_variants_y_atlas_pos_no(db):
    seed_modules_and_presets(db)
    assert "variants" in _preset(db, "ATLAS_POS_BOUTIQUE").modules
    assert "variants" not in _preset(db, "ATLAS_POS").modules


def test_aplicar_boutique_activa_variants(db, org):
    seed_modules_and_presets(db)
    apply_industry_preset(db, org.id, IndustryType.ATLAS_POS_BOUTIQUE)
    assert "variants" in get_organization_capabilities(db, org.id)


def test_catalogo_de_arranque_tiene_variants(db):
    seed_global_modules(db)
    assert db.query(Module).filter(Module.key == "variants").first() is not None
```

- [ ] **Step 2: Correr y ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_variants_module.py`
Expected: 4 FAILED (`variants` no existe en catálogo ni presets).

- [ ] **Step 3: Implementar**

En `scripts/init_presets_v2.py`, en `MODULES_CATALOG` justo después de la tupla `("scanner", ...)`:

```python
    ("variants", "Variantes color/talla", "Prendas con varias tallas y colores: matriz de variantes, selector en el POS y existencia por variante", ModuleScope.GLOBAL, ModuleStatus.STABLE),
```

En el mismo archivo, entrada `ATLAS_POS_BOUTIQUE` de `PRESETS`:

```python
        "mods": ATLAS_POS_MODS + ["scanner", "variants"],
```

En `app/services/capabilities_service.py`:

```python
MOD_SCANNER = "scanner"
MOD_VARIANTS = "variants"
```

```python
    IndustryType.ATLAS_POS_BOUTIQUE: [
        MOD_CORE, MOD_POS, MOD_CASH, MOD_CATALOG, MOD_INVENTORY,
        MOD_RETURNS, MOD_PRICING, MOD_PAYMENTS, MOD_REPORTS, MOD_SCANNER, MOD_VARIANTS
    ],
```

y en el `catalog` de `seed_global_modules`, después de la entrada `MOD_SCANNER`:

```python
        {"key": MOD_VARIANTS, "name": "Variantes color/talla", "scope": ModuleScope.GLOBAL, "status": ModuleStatus.STABLE},
```

- [ ] **Step 4: Correr y ver que pasa**

Run: `python3 -m pytest -q -p no:warnings tests/test_variants_module.py tests/test_boutique_preset.py tests/test_seed_presets.py`
Expected: todas PASSED.

- [ ] **Step 5: Commit**

```bash
git add scripts/init_presets_v2.py app/services/capabilities_service.py tests/test_variants_module.py
git commit -m "feat(variants): modulo variants en el catalogo y en el preset boutique"
```

---

### Task 2: Columnas `color` y `size`, etiqueta derivada y orden determinista

**Files:**
- Create: `app/modules/products/variant_label.py`
- Modify: `app/modules/products/models.py:62` (relación `variants`) y `:84-86` (columnas)
- Modify: `scripts/railway_init.py` (lista `migrations`, junto a la entrada `("product_variants", "has_iva", ...)` de la línea 54)
- Test: `tests/test_variant_label.py`, `tests/test_variant_columns.py`

**Interfaces:**
- Produces: `variant_label(color: str | None, size: str | None) -> str` (devuelve `"Rojo / M"`, `"Rojo"`, `"M"` o `"Estándar"`), `clean_attr(value: str | None, max_len: int) -> str | None` (recorta, colapsa espacios, vacío → `None`). `ProductVariant.color`, `ProductVariant.size`. `Product.variants` ordenado por `created_at, id`.

- [ ] **Step 1: Pruebas que fallan**

```python
# tests/test_variant_label.py
"""Etiqueta derivada de color/talla. Es lo que se guarda en `variant_name` y
lo que imprime el ticket entre parentesis."""
import pytest

from app.modules.products.variant_label import clean_attr, variant_label


@pytest.mark.parametrize("color,size,esperado", [
    ("Rojo", "M", "Rojo / M"),
    ("Rojo", None, "Rojo"),
    (None, "M", "M"),
    (None, None, "Estándar"),
    ("  ", "", "Estándar"),
])
def test_variant_label(color, size, esperado):
    assert variant_label(color, size) == esperado


def test_clean_attr_recorta_y_colapsa():
    assert clean_attr("  Azul   marino ", 60) == "Azul marino"
    assert clean_attr("", 60) is None
    assert clean_attr(None, 60) is None


def test_clean_attr_respeta_el_largo():
    with pytest.raises(ValueError):
        clean_attr("x" * 61, 60)
```

```python
# tests/test_variant_columns.py
"""`product_variants.color` y `.size` existen y `Product.variants` sale en
orden de creacion: `variants[0]` deja de ser aleatorio."""
from decimal import Decimal

from app.models.products import Product, ProductVariant


def test_columnas_color_y_size(db, org):
    p = Product(name="Playera", organization_id=org.id, is_active=True)
    db.add(p); db.flush()
    v = ProductVariant(product_id=p.id, sku="PLY-ROJO-M", price=Decimal("10"), cost=Decimal("5"),
                       color="Rojo", size="M", variant_name="Rojo / M", organization_id=org.id)
    db.add(v); db.flush()
    db.refresh(v)
    assert (v.color, v.size) == ("Rojo", "M")


def test_variants_en_orden_de_creacion(db, org):
    p = Product(name="Playera", organization_id=org.id, is_active=True)
    db.add(p); db.flush()
    for i, talla in enumerate(["S", "M", "L"]):
        db.add(ProductVariant(product_id=p.id, sku=f"PLY-{talla}", price=Decimal("10"),
                              cost=Decimal("5"), size=talla, organization_id=org.id))
        db.flush()
    db.expire(p)
    assert [v.size for v in p.variants] == ["S", "M", "L"]
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_variant_label.py tests/test_variant_columns.py`
Expected: ImportError en `variant_label`; `TypeError: 'color' is an invalid keyword argument`.

- [ ] **Step 3: Implementar**

`app/modules/products/variant_label.py`:

```python
"""Etiqueta y limpieza de los atributos color/talla de una variante.

Sin base de datos ni FastAPI a proposito: es la unica fuente de la etiqueta
que se guarda en `ProductVariant.variant_name` y que el ticket imprime entre
parentesis (`app/routers/sales.py::_line_description`).
"""
from __future__ import annotations

import re
from typing import Optional

COLOR_MAX = 60
SIZE_MAX = 30
DEFAULT_LABEL = "Estándar"

_ESPACIOS = re.compile(r"\s+")


def clean_attr(value: Optional[str], max_len: int) -> Optional[str]:
    """Recorta extremos, colapsa espacios internos y convierte vacio en None.

    Lanza ValueError si excede `max_len`: el caller lo convierte en 422 con el
    campo señalado, en vez de dejar que Postgres truncue o reviente.
    """
    if value is None:
        return None
    limpio = _ESPACIOS.sub(" ", value).strip()
    if not limpio:
        return None
    if len(limpio) > max_len:
        raise ValueError(f"máximo {max_len} caracteres")
    return limpio


def variant_label(color: Optional[str], size: Optional[str]) -> str:
    """"Rojo / M", "Rojo", "M" o "Estándar" cuando no hay atributos."""
    partes = [p for p in (clean_attr(color, COLOR_MAX), clean_attr(size, SIZE_MAX)) if p]
    return " / ".join(partes) if partes else DEFAULT_LABEL
```

`app/modules/products/models.py`, relación en `Product` (línea 62):

```python
    # Orden determinista: sin `order_by`, `variants[0]` cambiaba entre requests
    # en cuanto un producto tenia mas de una variante.
    variants = relationship(
        "ProductVariant", back_populates="product", cascade="all, delete-orphan",
        order_by="[ProductVariant.created_at, ProductVariant.id]",
    )
```

y en `ProductVariant`, después de `variant_name`:

```python
    variant_name = Column(String) # Etiqueta derivada: "Estándar", "Rojo / M" (ver variant_label.py)
    # Atributos de boutique (preset ATLAS_POS_BOUTIQUE). Opcionales: el resto de
    # los giros sigue con una sola variante sin color ni talla.
    color = Column(String(60), nullable=True)
    size = Column(String(30), nullable=True)
```

`scripts/railway_init.py`, en la lista `migrations` junto a `has_iva`:

```python
        # Variantes color/talla (2026-09-17, preset boutique). Opcionales.
        ("product_variants", "color", "ALTER TABLE product_variants ADD COLUMN color VARCHAR(60);"),
        ("product_variants", "size",  "ALTER TABLE product_variants ADD COLUMN size VARCHAR(30);"),
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `python3 -m pytest -q -p no:warnings tests/test_variant_label.py tests/test_variant_columns.py`
Expected: PASSED. Luego la suite completa: el conteo de `failed` no debe subir.

- [ ] **Step 5: Commit**

```bash
git add app/modules/products/variant_label.py app/modules/products/models.py scripts/railway_init.py tests/test_variant_label.py tests/test_variant_columns.py
git commit -m "feat(variants): columnas color/size, etiqueta derivada y orden determinista"
```

---

### Task 3: La API expone cada variante con nombre, atributos y existencia, y deja de aplanar a ciegas

**Files:**
- Modify: `app/modules/products/schemas.py:53-64` (`ProductVariantRead`), `:143-160` (`ProductRead`)
- Modify: `app/modules/products/router/_shared.py:70-192` (`_compute_product_read`)
- Modify: `app/modules/products/router/core.py:125-150` (`read_products`: caches con todas las variantes)
- Test: `tests/test_variant_read.py`

**Interfaces:**
- Consumes: `ProductVariant.color/size` (Task 2).
- Produces: `ProductVariantRead.variant_name: Optional[str]`, `.color`, `.size`, `.stock_total: Decimal`; `ProductRead.matched_variant_id: Optional[str]`; `_compute_product_read(..., primary_variant_id: Optional[str] = None)`. Los campos aplanados (`sku`, `price`, `stock_total`…) representan la variante `primary_variant_id` si se pasa, si no la primera.

- [ ] **Step 1: Prueba que falla**

```python
# tests/test_variant_read.py
"""Con dos variantes, GET /api/products/{id} devuelve las dos con nombre,
atributos y existencia propia, y los campos aplanados siguen siendo los de la
primera (compatibilidad con las 76 vistas)."""
from decimal import Decimal

import pytest

from app.models.inventory import StockOnHand
from app.models.products import ProductBranchStatus, ProductVariant
from conftest import _make_product


@pytest.fixture()
def playera(db, org, branch_a):
    p, v_s = _make_product(db, org, "Playera", "PLY-S", 100, [(branch_a.id, True)])
    v_s.color, v_s.size, v_s.variant_name = "Rojo", "S", "Rojo / S"
    v_m = ProductVariant(product_id=p.id, sku="PLY-M", barcode="7500000000002",
                         price=Decimal("120"), cost=Decimal("60"),
                         color="Rojo", size="M", variant_name="Rojo / M", organization_id=org.id)
    db.add(v_m); db.flush()
    db.add(ProductBranchStatus(variant_id=v_m.id, branch_id=branch_a.id, organization_id=org.id,
                               is_active_pos=True, is_visible=True))
    db.add(StockOnHand(variant_id=v_m.id, branch_id=branch_a.id, organization_id=org.id,
                       qty_on_hand=Decimal("7"), is_active=True))
    db.flush()
    return p, v_s, v_m


def test_detalle_trae_las_dos_variantes_con_stock(client, db, org, playera, auth_cajero_a):
    p, v_s, v_m = playera
    r = client.get(f"/api/products/{p.id}", headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    data = r.json()
    por_sku = {v["sku"]: v for v in data["variants"]}
    assert por_sku["PLY-S"]["variant_name"] == "Rojo / S"
    assert por_sku["PLY-M"]["color"] == "Rojo" and por_sku["PLY-M"]["size"] == "M"
    assert Decimal(str(por_sku["PLY-S"]["stock_total"])) == Decimal("100")
    assert Decimal(str(por_sku["PLY-M"]["stock_total"])) == Decimal("7")
    # Aplanado = primera variante (orden de creacion), y se dice cual fue.
    assert data["sku"] == "PLY-S"
    assert data["matched_variant_id"] == v_s.id


def test_listado_trae_stock_de_todas_las_variantes(client, db, org, playera, auth_cajero_a):
    p, v_s, v_m = playera
    r = client.get("/api/products/", params={"search": "Playera"},
                   headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["items"] if i["id"] == p.id)
    stocks = {v["sku"]: Decimal(str(v["stock_total"])) for v in item["variants"]}
    assert stocks == {"PLY-S": Decimal("100"), "PLY-M": Decimal("7")}
```

- [ ] **Step 2: Correr y ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_variant_read.py`
Expected: KeyError `variant_name` / `matched_variant_id`.

- [ ] **Step 3: Implementar**

`schemas.py`, `ProductVariantRead`:

```python
class ProductVariantRead(BaseModel):
    id: str # UUID
    sku: str
    barcode: Optional[str] = None
    # Etiqueta y atributos (boutique). Antes no viajaban y el frontend no podia
    # distinguir dos variantes del mismo producto.
    variant_name: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    price: Decimal
    cost: Decimal
    has_iva: bool = False
    tax_rate: Decimal = 16.0
    # Existencia de ESTA variante en la sucursal objetivo. La llena
    # `_compute_product_read`; no existe en el ORM.
    stock_total: Decimal = Decimal(0)
    prices: List[ProductPriceRead] = []
    packaging_units: List[PackagingUnitRead] = []
    class Config:
        from_attributes = True
```

`ProductRead`, junto a `variants`:

```python
    variants: List[ProductVariantRead] = []
    # Que variante representan los campos aplanados (sku/price/stock_total).
    # En una busqueda por codigo es la que empato; si no, la primera.
    matched_variant_id: Optional[str] = None
```

`_shared.py`, firma y cuerpo de `_compute_product_read`:

```python
def _compute_product_read(
    p: Product,
    db: Session,
    current_user: User,
    stock_cache: dict[str, Decimal] = None,
    target_branch_id: int = None,
    branch_statuses_cache: dict[str, list] = None,
    primary_variant_id: Optional[str] = None,
) -> ProductRead:
```

Reemplazar `v = p.variants[0]` por:

```python
    if p.variants:
        # La variante "principal" es la pedida (p. ej. la que empato un
        # escaneo) o, si no, la primera en orden de creacion.
        v = next((x for x in p.variants if x.id == primary_variant_id), p.variants[0])
        p_read.matched_variant_id = v.id
```

y al final del bloque `if p.variants:` (antes del `return p_read`), llenar el stock por variante:

```python
        # Existencia por variante en la sucursal objetivo. Con una sola
        # variante coincide con stock_total; con varias es lo que permite al
        # POS mostrar cuantas piezas hay de cada talla.
        def _qty(val):
            if isinstance(val, tuple):
                return val[0] or Decimal(0)
            return val or Decimal(0)

        faltantes = [vr.id for vr in p_read.variants if stock_cache is None or vr.id not in stock_cache]
        directo: dict[str, Decimal] = {}
        if faltantes and real_branch_id:
            for row in (
                db.query(StockOnHand.variant_id, StockOnHand.qty_on_hand)
                .filter(StockOnHand.variant_id.in_(faltantes), StockOnHand.branch_id == real_branch_id)
                .all()
            ):
                directo[row.variant_id] = row.qty_on_hand
        for vr in p_read.variants:
            if stock_cache is not None and vr.id in stock_cache:
                vr.stock_total = _qty(stock_cache[vr.id])
            else:
                vr.stock_total = directo.get(vr.id, Decimal(0))
```

`core.py`, `read_products` (línea ~127): cachear todas las variantes, no solo la primera:

```python
    variant_ids = [v.id for p in products_db for v in p.variants]
```

- [ ] **Step 4: Correr y ver que pasa**

Run: `python3 -m pytest -q -p no:warnings tests/test_variant_read.py tests/test_product_visibility.py tests/test_scanner_exact_search.py`
Expected: PASSED. Suite completa sin nuevos `failed`.

- [ ] **Step 5: Commit**

```bash
git add app/modules/products/schemas.py app/modules/products/router/_shared.py app/modules/products/router/core.py tests/test_variant_read.py
git commit -m "feat(variants): la API expone nombre, atributos y existencia por variante"
```

---
## Fase 1 — Venta correcta por variante

### Task 4: La búsqueda del POS devuelve la variante que empató el código

**Files:**
- Modify: `app/modules/products/router/search.py:308-451` (`search_products_pos`)
- Test: `tests/test_pos_search_variant_match.py`

**Interfaces:**
- Consumes: `_compute_product_read(..., primary_variant_id=)` y `ProductRead.matched_variant_id` (Task 3).
- Produces: en `GET /api/products/pos/search?exact=true`, `sku`, `barcode`, `price`, `stock_total` y `matched_variant_id` corresponden a la variante cuyo SKU o código empató. `variants[]` viene completo (no solo la fila que empató).

- [ ] **Step 1: Prueba que falla**

```python
# tests/test_pos_search_variant_match.py
"""Escanear el codigo de la talla M debe devolver la talla M, no la S.

`contains_eager` sobre `Product.variants` carga solo las filas que empataron
el WHERE, asi que hoy `variants[0]` PUEDE ser la correcta por accidente. Esta
prueba fija el contrato para que no dependa de ese efecto colateral: campos
aplanados de la variante empatada, `matched_variant_id` explicito y
`variants[]` completo para el selector del POS."""
from decimal import Decimal

import pytest

from app.models.inventory import StockOnHand
from app.models.products import ProductBranchStatus, ProductVariant
from conftest import _make_product


@pytest.fixture()
def playera(db, org, branch_a):
    p, v_s = _make_product(db, org, "Playera Lisa", "PLY-S", 100, [(branch_a.id, True)])
    v_s.barcode, v_s.color, v_s.size, v_s.variant_name = "7500000000001", "Rojo", "S", "Rojo / S"
    v_m = ProductVariant(product_id=p.id, sku="PLY-M", barcode="7500000000002",
                         price=Decimal("120"), cost=Decimal("60"),
                         color="Rojo", size="M", variant_name="Rojo / M", organization_id=org.id)
    db.add(v_m); db.flush()
    db.add(ProductBranchStatus(variant_id=v_m.id, branch_id=branch_a.id, organization_id=org.id,
                               is_active_pos=True, is_visible=True))
    db.add(StockOnHand(variant_id=v_m.id, branch_id=branch_a.id, organization_id=org.id,
                       qty_on_hand=Decimal("7"), is_active=True))
    db.flush()
    return p, v_s, v_m


def _buscar(client, org, auth, **params):
    r = client.get("/api/products/pos/search", params=params,
                   headers={**auth, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    return r.json()


def test_escanear_la_talla_m_devuelve_la_talla_m(client, org, playera, auth_cajero_a):
    p, v_s, v_m = playera
    res = _buscar(client, org, auth_cajero_a, q="7500000000002", exact="true")
    assert len(res) == 1
    hit = res[0]
    assert hit["id"] == p.id
    assert hit["matched_variant_id"] == v_m.id
    assert hit["sku"] == "PLY-M"
    assert Decimal(str(hit["price"])) == Decimal("120")
    assert Decimal(str(hit["stock_total"])) == Decimal("7")


def test_teclear_el_sku_de_la_s_devuelve_la_s(client, org, playera, auth_cajero_a):
    p, v_s, v_m = playera
    hit = _buscar(client, org, auth_cajero_a, q="ply-s", exact="true")[0]
    assert hit["matched_variant_id"] == v_s.id
    assert hit["sku"] == "PLY-S"


def test_variants_viene_completo_aunque_empate_una_sola(client, org, playera, auth_cajero_a):
    p, v_s, v_m = playera
    hit = _buscar(client, org, auth_cajero_a, q="7500000000002", exact="true")[0]
    assert {v["sku"] for v in hit["variants"]} == {"PLY-S", "PLY-M"}
    stocks = {v["sku"]: Decimal(str(v["stock_total"])) for v in hit["variants"]}
    assert stocks["PLY-S"] == Decimal("100") and stocks["PLY-M"] == Decimal("7")


def test_buscar_por_nombre_no_duplica_el_producto(client, org, playera, auth_cajero_a):
    res = _buscar(client, org, auth_cajero_a, q="Playera")
    assert [r["id"] for r in res].count(playera[0].id) == 1
```

- [ ] **Step 2: Correr y ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_pos_search_variant_match.py`
Expected: al menos `test_variants_viene_completo_aunque_empate_una_sola` FAILED (la colección viene parcial por `contains_eager`); anotar cuáles pasaron ya.

- [ ] **Step 3: Implementar**

En `search.py`, después de `products_db = query.distinct(Product.id).limit(20).all()` y del bloque de ordenamiento, sustituir el cálculo de `variant_ids` y la construcción de la respuesta:

```python
        # `contains_eager` dejo en `p.variants` SOLO las filas que empataron el
        # WHERE. Para el selector de tallas del POS hace falta la coleccion
        # completa, asi que se recargan las variantes de los productos hallados
        # en una sola consulta (no N+1) y se sustituye la coleccion parcial.
        product_ids = [p.id for p in products_db]
        if product_ids:
            todas = (
                db.query(ProductVariant)
                .options(
                    joinedload(ProductVariant.prices),
                    joinedload(ProductVariant.packaging_units),
                )
                .filter(ProductVariant.product_id.in_(product_ids), ProductVariant.deleted_at.is_(None))
                .order_by(ProductVariant.created_at, ProductVariant.id)
                .all()
            )
            por_producto: dict[str, list] = {}
            for v in todas:
                por_producto.setdefault(v.product_id, []).append(v)
            for p in products_db:
                set_committed_value(p, "variants", por_producto.get(p.id, []))

        # Que variante empato el codigo (solo tiene sentido en modo exacto).
        def _matched_variant_id(p) -> Optional[str]:
            if not exact:
                return None
            ql = q.lower()
            for v in p.variants:
                if (v.sku or "").lower() == ql or v.barcode == q:
                    return v.id
                if any(pk.barcode == q for pk in (v.packaging_units or [])):
                    return v.id
            return None

        # --- Batch: Stock + BranchStatus caches (avoid N+1) ---
        variant_ids = [v.id for p in products_db for v in p.variants]
```

y en el `return`:

```python
        return [
            _compute_product_read(
                p, db, current_user, stock_cache, target_branch_id,
                branch_statuses_cache=branch_statuses_cache,
                primary_variant_id=_matched_variant_id(p),
            )
            for p in products_db
        ]
```

Agregar el import al inicio de `search.py`:

```python
from sqlalchemy.orm.attributes import set_committed_value
```

(`Optional` ya viene de `._shared`; si no, `from typing import Optional`.)

- [ ] **Step 4: Correr y ver que pasa**

Run: `python3 -m pytest -q -p no:warnings tests/test_pos_search_variant_match.py tests/test_scanner_exact_search.py tests/test_pos_search_consulta_vacia.py tests/test_product_visibility.py`
Expected: PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/modules/products/router/search.py tests/test_pos_search_variant_match.py
git commit -m "fix(pos): la busqueda por codigo devuelve la variante que empato y la coleccion completa"
```

---

### Task 5: El checkout acepta `variant_id` por renglón

**Files:**
- Modify: `app/schemas/sales.py:16-21` (`SaleItemCreate`)
- Test: `tests/test_sale_by_variant_id.py`

**Interfaces:**
- Consumes: la resolución por `variant_id` que ya existe en `app/routers/sales.py:522-587` (`getattr(item, "variant_id", None)`).
- Produces: `SaleItemCreate.variant_id: Optional[str]`. Cuando viene, manda sobre `sku`.

- [ ] **Step 1: Prueba que falla**

```python
# tests/test_sale_by_variant_id.py
"""Vender la talla M debe descontar la talla M aunque el SKU del renglon sea
otro. Hoy `SaleItemCreate` no declara `variant_id` y Pydantic v2 lo descarta,
asi que el checkout resolvia siempre por SKU."""
from decimal import Decimal

from app.models.inventory import StockOnHand
from app.models.products import ProductBranchStatus, ProductVariant
from app.models.sales import SalesLineItem
from conftest import _make_product
from tests.test_sale_variant_name_null import _abrir_caja, _habilitar_pos


def _playera(db, org, branch):
    _habilitar_pos(db, org)
    p, v_s = _make_product(db, org, "Playera", "PLY-S", 100, [(branch.id, True)])
    v_s.variant_name = "Rojo / S"
    v_m = ProductVariant(product_id=p.id, sku="PLY-M", price=Decimal("120"), cost=Decimal("60"),
                         color="Rojo", size="M", variant_name="Rojo / M", organization_id=org.id)
    db.add(v_m); db.flush()
    db.add(ProductBranchStatus(variant_id=v_m.id, branch_id=branch.id, organization_id=org.id,
                               is_active_pos=True, is_visible=True))
    db.add(StockOnHand(variant_id=v_m.id, branch_id=branch.id, organization_id=org.id,
                       qty_on_hand=Decimal("7"), is_active=True))
    db.commit()
    return p, v_s, v_m


def test_variant_id_manda_sobre_el_sku(client, db, org, branch_a, cajero_a, auth_cajero_a):
    p, v_s, v_m = _playera(db, org, branch_a)
    _abrir_caja(db, org, branch_a, cajero_a)
    r = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "PLY-S", "variant_id": v_m.id, "quantity": 2}],
        "payments": [{"method": "CARD", "amount": "240.00"}],
    }, headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert r.status_code in (200, 201), r.text

    stock_m = db.query(StockOnHand).filter(StockOnHand.variant_id == v_m.id, StockOnHand.branch_id == branch_a.id).one()
    stock_s = db.query(StockOnHand).filter(StockOnHand.variant_id == v_s.id, StockOnHand.branch_id == branch_a.id).one()
    assert stock_m.qty_on_hand == Decimal("5")
    assert stock_s.qty_on_hand == Decimal("100")

    linea = db.query(SalesLineItem).filter(SalesLineItem.variant_id == v_m.id).one()
    assert linea.description == "Playera (Rojo / M)"


def test_variant_id_de_otra_org_es_404(client, db, org, branch_a, cajero_a, auth_cajero_a):
    from app.models.organization import Organization
    otra = Organization(name="Otra", status="ACTIVE"); db.add(otra); db.flush()
    p_ajeno, v_ajeno = _make_product(db, otra, "Ajena", "AJ-1", 10)
    _playera(db, org, branch_a)
    _abrir_caja(db, org, branch_a, cajero_a)
    r = client.post("/api/sales/", json={
        "doc_type": "ORDER",
        "items": [{"sku": "AJ-1", "variant_id": v_ajeno.id, "quantity": 1}],
        "payments": [{"method": "CARD", "amount": "10.00"}],
    }, headers={**auth_cajero_a, "X-Organization-ID": str(org.id)})
    assert r.status_code == 404
```

- [ ] **Step 2: Correr y ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_sale_by_variant_id.py`
Expected: `test_variant_id_manda_sobre_el_sku` FAILED (descontó `PLY-S`).

- [ ] **Step 3: Implementar**

`app/schemas/sales.py`:

```python
class SaleItemCreate(BaseModel):
    sku: str
    # Variante exacta (boutique: la talla/color elegida). Si viene, manda sobre
    # `sku`, que se conserva como respaldo y para los mensajes de error.
    variant_id: Optional[str] = None
    quantity: float = 1.0
    unit_price: Optional[Decimal] = None
    discount: Optional[float] = Field(default=0.0, ge=0.0, le=100.0)   # porcentaje 0-100
    notes: Optional[str] = None
```

- [ ] **Step 4: Correr y ver que pasa**

Run: `python3 -m pytest -q -p no:warnings tests/test_sale_by_variant_id.py tests/test_sale_variant_name_null.py`
Expected: PASSED. Luego toda la suite.

- [ ] **Step 5: Commit**

```bash
git add app/schemas/sales.py tests/test_sale_by_variant_id.py
git commit -m "feat(sales): el checkout acepta variant_id por renglon"
```

---

### Task 6: El carrito y la venta del POS viajan con `variant_id`

**Files:**
- Create: `frontend/src/pages/pos/saleItems.ts`
- Modify: `frontend/src/types/sales.ts:66-82` (`CartItem`), `frontend/src/types/products.ts:40-53` y `:85-86` (`ProductVariant`, `Product.matched_variant_id`)
- Modify: `frontend/src/components/pos/ProductSearch.tsx:165-215` (`cartQtyUnits`, `addToCart`)
- Modify: `frontend/src/pages/pos/POS.tsx:137-171` (`buildSaleItems` → `saleItems.ts`)
- Test: `frontend/src/pages/pos/__tests__/saleItems.test.ts`

**Interfaces:**
- Consumes: `Product.matched_variant_id`, `Product.variants[].stock_total` (Task 3/4); `SaleItemCreate.variant_id` (Task 5).
- Produces: `CartItem.variant_id?: string`, `CartItem.variant_label?: string`; `buildSaleItems(cart: CartItem[], globalDiscount: number): SaleItemPayload[]` puro; `cartQtyUnits` cuenta por `variant_id` cuando existe.

- [ ] **Step 1: Prueba que falla**

```ts
// frontend/src/pages/pos/__tests__/saleItems.test.ts
import { describe, it, expect } from 'vitest'

import { buildSaleItems } from '../saleItems'
import type { CartItem } from '../../../types/sales'

// El renglon de venta debe llevar la variante elegida: sin `variant_id` el
// backend resuelve por SKU y una boutique vende la talla equivocada.

const pieza = (over: Partial<CartItem> = {}): CartItem => ({
  product_id: 'p1', sku: 'PLY-M', name: 'Playera', price: 120, quantity: 2, discount: 0, subtotal: 240,
  variant_id: 'v-m', variant_label: 'Rojo / M', cart_key: 'v-m', ...over,
})

describe('buildSaleItems', () => {
  it('manda variant_id y sku por pieza', () => {
    const [it] = buildSaleItems([pieza()], 0)
    expect(it.variant_id).toBe('v-m')
    expect(it.sku).toBe('PLY-M')
    expect(it.quantity).toBe(2)
    expect(it.unit_price).toBe(120)
  })

  it('aplica el descuento global al precio unitario', () => {
    const [it] = buildSaleItems([pieza()], 10)
    expect(it.unit_price).toBeCloseTo(108)
    expect(it.subtotal).toBeCloseTo(216)
  })

  it('expande una caja a piezas y conserva la variante', () => {
    const caja = pieza({
      cart_key: 'p1::caja::t9', quantity: 1, price: 1000,
      prices: [{ id: 't9', price_name: 'Caja', min_quantity: 12, unit_price: 100, linked_package_id: null }],
    })
    const [it] = buildSaleItems([caja], 0)
    expect(it.quantity).toBe(12)
    expect(it.unit_price).toBe(100)
    expect(it.variant_id).toBe('v-m')
  })

  it('sin variant_id sigue funcionando por sku (tiendas sin variantes)', () => {
    const [it] = buildSaleItems([pieza({ variant_id: undefined, cart_key: undefined })], 0)
    expect(it.variant_id).toBeUndefined()
    expect(it.sku).toBe('PLY-M')
  })
})
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/pages/pos`
Expected: FAIL, módulo `../saleItems` no existe.

- [ ] **Step 3: Implementar**

`frontend/src/types/sales.ts`, dentro de `CartItem` después de `product_id`:

```ts
  variant_id?: string     // variante exacta (talla/color); el backend la prioriza sobre sku
  variant_label?: string  // "Rojo / M" para el carrito y el ticket en pantalla
```

`frontend/src/types/products.ts`, `ProductVariant`:

```ts
export interface ProductVariant {
  id: string
  product_id: string
  sku: string
  variant_name?: string | null   // "Rojo / M" o "Estándar"
  color?: string | null
  size?: string | null
  price: number
  cost: number
  barcode?: string | null
  has_iva?: boolean
  tax_rate?: number
  stock_total?: number | string  // Decimal del backend; usar Number()
  prices?: ProductPrice[]
  packaging_units?: PackagingUnit[]
}
```

y en `Product`, junto a `variants`:

```ts
  // Variantes completas (orden de creación)
  variants?: ProductVariant[]
  // Qué variante representan sku/price/stock_total: la que empató un escaneo o la primera
  matched_variant_id?: string | null
```

(Se eliminan los campos fantasma `name` y `stock` de `ProductVariant`; `tsc` señalará si algo los usaba. En este repo no hay usos.)

`frontend/src/pages/pos/saleItems.ts`:

```ts
import type { CartItem } from '../../types/sales'

export interface SaleItemPayload {
  product_id: string
  variant_id?: string
  sku: string
  name: string
  unit_price: number
  price: number
  quantity: number
  discount: number
  subtotal: number
}

/**
 * Renglones que se mandan a POST /api/sales.
 *
 * Los ítems de caja (cart_key con '::caja::') se expanden a piezas al precio
 * unitario del escalón. El descuento global se multiplica en cada precio
 * unitario (el guard server-side evalúa sobre el precio final). `variant_id`
 * viaja siempre que se conozca: es lo que hace que una boutique cobre y
 * descuente la talla elegida y no la primera del producto.
 */
export function buildSaleItems(cart: CartItem[], globalDiscount: number): SaleItemPayload[] {
  const gdFactor = 1 - (globalDiscount || 0) / 100
  return cart.map((c) => {
    const base = {
      product_id: c.product_id,
      ...(c.variant_id ? { variant_id: c.variant_id } : {}),
      sku: c.sku,
      name: c.name,
      discount: c.discount,
    }
    if (c.cart_key?.includes('::caja::')) {
      const tierId = c.cart_key.split('::caja::')[1]
      const cajaTier = c.prices?.find((p) => p.id === tierId)
      if (cajaTier && cajaTier.min_quantity > 0) {
        const totalPiezas = c.quantity * cajaTier.min_quantity
        const unitPrice = cajaTier.unit_price * gdFactor
        return { ...base, unit_price: unitPrice, price: unitPrice, quantity: totalPiezas,
                 subtotal: totalPiezas * unitPrice * (1 - c.discount / 100) }
      }
    }
    const unitPrice = c.price * gdFactor
    return { ...base, unit_price: unitPrice, price: unitPrice, quantity: c.quantity,
             subtotal: c.quantity * unitPrice * (1 - c.discount / 100) }
  })
}
```

`POS.tsx`: borrar la función local `buildSaleItems` (líneas 137-171) e importar:

```ts
import { buildSaleItems } from './saleItems'
```

y donde se llamaba `buildSaleItems()` usar `buildSaleItems(store.cart, store.globalDiscount)`.

`ProductSearch.tsx`, `cartQtyUnits` y `addToCart`:

```ts
  // Cuenta por variante cuando la hay: dos tallas del mismo producto no
  // comparten existencia, y sumarlas bloqueaba la segunda talla al llegar al
  // stock de la primera.
  const cartQtyUnits = (productId: string, variantId?: string | null): number => {
    let total = 0
    for (const c of cart) {
      if (c.product_id !== productId) continue
      if (variantId && c.variant_id && c.variant_id !== variantId) continue
      if (c.cart_key?.includes('::caja::')) {
        const cajaTier = c.prices?.find(p => p.price_name.toLowerCase().includes('caja'))
        total += c.quantity * (cajaTier?.min_quantity ?? 1)
      } else {
        total += c.quantity
      }
    }
    return total
  }

  const addToCart = (p: Product) => {
    const variantId = p.matched_variant_id ?? p.variants?.[0]?.id ?? undefined
    const variant = p.variants?.find((v) => v.id === variantId)
    const label = variant?.variant_name && variant.variant_name !== 'Estándar' ? variant.variant_name : undefined
    const stock = Number(p.stock_total ?? 0)
    if (stock > 0 && cartQtyUnits(p.id, variantId) >= stock) {
      setLimitId(p.id)
      setTimeout(() => setLimitId(null), 2000)
      return
    }
    addItem({
      product_id: p.id,
      ...(variantId ? { variant_id: variantId, cart_key: variantId } : {}),
      ...(label ? { variant_label: label } : {}),
      base_price: Number(p.price),
      sku: p.sku ?? '',
      name: label ? `${p.name} (${label})` : p.name,
      price: Number(p.price),
      quantity: 1,
      discount: 0,
      subtotal: Number(p.price),
      stock,
      prices: p.prices?.map(pr => ({
        id: String(pr.id),
        price_name: pr.price_name,
        min_quantity: pr.min_quantity,
        unit_price: Number(pr.unit_price),
        linked_package_id: pr.linked_package_id ?? null,
      })),
      packaging_units: p.packaging_units?.map(pk => ({
        id: String(pk.id),
        name: pk.name,
        barcode: pk.barcode,
        units_per_package: Number(pk.units_per_package),
        package_price: Number(pk.package_price),
      })),
    })
    setQuery('')
    setResults([])
    devolverFoco()
  }
```

Nota: `cart_key = variantId` no interfiere con las cajas (`CartPanel.tsx:130` construye `${product_id}::caja::${tier}` a partir de la pieza y busca por `product_id`). `posStore.addItem` (`:108`) fusiona por `cart_key ?? product_id`, así que dos tallas quedan en renglones distintos.

- [ ] **Step 4: Correr y ver que pasa**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npm run build`
Expected: vitest en verde (261 + 4), `tsc` sin errores, build ok.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/pos/saleItems.ts frontend/src/pages/pos/__tests__/saleItems.test.ts frontend/src/pages/pos/POS.tsx frontend/src/components/pos/ProductSearch.tsx frontend/src/types/sales.ts frontend/src/types/products.ts
git commit -m "feat(pos): el carrito y la venta viajan con variant_id"
```

---

### Task 7: El Scanner de tienda opera sobre la variante escaneada

**Files:**
- Modify: `frontend/src/pages/scanner/productStock.ts` (nuevo helper `matchedVariant`)
- Modify: `frontend/src/pages/scanner/StoreScanner.tsx:420-431` (ficha), `:561` (`variantId` del conteo)
- Test: `frontend/src/pages/scanner/__tests__/productStock.test.ts` (ya existe; se agregan casos)

**Interfaces:**
- Consumes: `Product.matched_variant_id`, `ProductVariant.stock_total` (Task 3/4).
- Produces: `matchedVariant(product): ProductVariant | null` y `currentStock(product, branchId)` que prefiere la existencia de la variante empatada.

- [ ] **Step 1: Prueba que falla**

Agregar a `frontend/src/pages/scanner/__tests__/productStock.test.ts`:

```ts
import { currentStock, matchedVariant } from '../productStock'
import type { Product } from '../../../types/products'

// El conteo del scanner escribia el kardex de variants[0]: escanear la talla
// XL y contar anaquel ajustaba la talla S.
const playera = (): Product => ({
  id: 'p1', sku: 'PLY-M', name: 'Playera', description: null, brand_id: null, brand_name: null,
  department: null, department_name: null, unit: 'pza', cost: 60, price: 120, stock: 0,
  stock_total: 7, image_url: null, is_active: true, matched_variant_id: 'v-m',
  variants: [
    { id: 'v-s', product_id: 'p1', sku: 'PLY-S', variant_name: 'Rojo / S', price: 100, cost: 50, stock_total: '100' },
    { id: 'v-m', product_id: 'p1', sku: 'PLY-M', variant_name: 'Rojo / M', price: 120, cost: 60, stock_total: '7' },
  ],
  stock_levels: [{ branch_id: 20, qty_on_hand: 7, is_active: true }],
})

describe('matchedVariant', () => {
  it('devuelve la variante que empató el escaneo', () => {
    expect(matchedVariant(playera())?.id).toBe('v-m')
  })
  it('cae a la primera si el backend no dijo cuál', () => {
    expect(matchedVariant({ ...playera(), matched_variant_id: null })?.id).toBe('v-s')
  })
  it('null sin variantes', () => {
    expect(matchedVariant({ ...playera(), variants: [] })).toBeNull()
  })
})

describe('currentStock por variante', () => {
  it('usa stock_total de la variante empatada antes que stock_levels', () => {
    const p = playera()
    p.stock_levels = [{ branch_id: 20, qty_on_hand: 100, is_active: true }]
    expect(currentStock(p, 20)).toBe(7)
  })
})
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/pages/scanner`
Expected: FAIL (`matchedVariant` no existe; `currentStock` devuelve 100).

- [ ] **Step 3: Implementar**

`productStock.ts`, agregar:

```ts
import type { Product, ProductVariant } from '../../types/products'

/**
 * Variante sobre la que trabaja el scanner: la que empató el código escaneado
 * (`matched_variant_id`) o, si el backend no lo dijo, la primera. Nunca
 * `variants[0]` a secas: con varias tallas eso ajustaba la talla equivocada.
 */
export function matchedVariant(product: Product): ProductVariant | null {
  const vs = product.variants ?? []
  if (vs.length === 0) return null
  return vs.find((v) => v.id === product.matched_variant_id) ?? vs[0]
}
```

y en `currentStock`, antes de consultar `stock_levels`:

```ts
export function currentStock(product: Product, branchId: number | null): number {
  // La existencia por variante manda: `stock_levels` es del producto aplanado
  // y con varias tallas no dice cuántas hay de la escaneada.
  const v = matchedVariant(product)
  const porVariante = num(v?.stock_total)
  if (v && (product.variants?.length ?? 0) > 1 && porVariante !== null) return porVariante
  if (branchId != null) {
    const nivel = (product.stock_levels ?? []).find((s) => s.branch_id === branchId)
    const q = num(nivel?.qty_on_hand)
    if (q !== null) return q
  }
  return num(product.stock_total) ?? 0
}
```

`StoreScanner.tsx`:
- Importar `matchedVariant` desde `./productStock`.
- Ficha (línea ~427): debajo del nombre, mostrar la etiqueta:

```tsx
        <h2 className="text-lg font-black text-white leading-tight">
          {product.name}
          {matchedVariant(product)?.variant_name && matchedVariant(product)!.variant_name !== 'Estándar' && (
            <span className="ml-2 text-sm font-bold text-indigo-300">{matchedVariant(product)!.variant_name}</span>
          )}
        </h2>
        <p className="text-xs text-slate-400 font-mono">
          {matchedVariant(product)?.sku ?? product.sku}
          {(matchedVariant(product)?.barcode ?? product.barcode) ? ` · ${matchedVariant(product)?.barcode ?? product.barcode}` : ' · sin código'}
        </p>
```

- Conteo (línea 561): `const variantId = matchedVariant(product)?.id ?? null`.
- Tras `productsApi.getById(product.id)` en `apply`, conservar la variante: `setSelected` con `{ ...fresh, matched_variant_id: product.matched_variant_id ?? fresh.matched_variant_id }` (el detalle no sabe qué se escaneó).

- [ ] **Step 4: Correr y ver que pasa**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: verde.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/scanner/productStock.ts frontend/src/pages/scanner/StoreScanner.tsx frontend/src/pages/scanner/__tests__/productStock.test.ts
git commit -m "fix(scanner): el conteo y la ficha son de la variante escaneada"
```

**Hito de fase 1:** desplegar. Con variantes cargadas por script, Eleven ya vende y cuenta la talla correcta.

---
## Fase 2 — Alta y edición de variantes

### Task 8: Endpoints de variantes y `extra_variants` en el alta

**Files:**
- Create: `app/modules/products/router/variants.py`
- Modify: `app/modules/products/router/__init__.py` (registrar `variants` en el `from . import (...)` y en el `include_router` correspondiente)
- Modify: `app/modules/products/schemas.py:66-70` (`ProductVariantCreate`), nuevos `ProductVariantUpdate`, `VariantBatchCreate`
- Modify: `app/modules/products/router/core.py:327-345` (`create_product`: honrar `extra_variants`)
- Test: `tests/test_variant_endpoints.py`

**Interfaces:**
- Consumes: `variant_label`, `clean_attr` (Task 2); `require_module` de `app/core/permissions.py`; `MOD_VARIANTS` (Task 1).
- Produces:
  - `POST /api/products/{product_id}/variants` body `{"variants": [{"color", "size", "sku"?, "barcode"?, "price"?, "cost"?}]}` → `ProductRead` completo. SKU ausente = `<sku base>-<COLOR>-<TALLA>` en mayúsculas sin acentos. Crea `ProductBranchStatus` y `StockOnHand(0)` en las mismas sucursales donde ya está la primera variante.
  - `PUT /api/products/variants/{variant_id}` body `ProductVariantUpdate` (todos opcionales: `color, size, sku, barcode, price, cost`) → `ProductRead`.
  - `DELETE /api/products/variants/{variant_id}` → 204; 409 si tiene existencia > 0 o ventas; 409 si es la única variante. Soft delete (`deleted_at`).
  - Validaciones: SKU único por org (409), código de barras único por org (409), color/talla máximo 60/30 (422), pareja color+talla no repetida dentro del producto (409).

- [ ] **Step 1: Pruebas que fallan**

```python
# tests/test_variant_endpoints.py
"""CRUD de variantes (color/talla) del preset boutique."""
from decimal import Decimal

import pytest

from app.models.inventory import StockOnHand
from app.models.modules import Module, OrganizationModule
from app.models.products import ProductBranchStatus, ProductVariant
from conftest import _make_product


def _habilitar(db, org, key):
    if db.query(Module).filter(Module.key == key).first() is None:
        db.add(Module(key=key, name=key)); db.flush()
    om = db.query(OrganizationModule).filter(OrganizationModule.organization_id == org.id,
                                             OrganizationModule.module_key == key).first()
    if om is None:
        db.add(OrganizationModule(organization_id=org.id, module_key=key, is_enabled=True))
    else:
        om.is_enabled = True
    db.commit()


@pytest.fixture()
def playera(db, org, branch_a):
    _habilitar(db, org, "variants")
    p, v = _make_product(db, org, "Playera", "PLY", 100, [(branch_a.id, True)])
    v.variant_name = "Estándar"
    db.commit()
    return p, v


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


class TestCrearVariantes:
    def test_crea_matriz_con_sku_generado_y_stock_cero(self, client, db, org, branch_a, playera, auth_admin):
        p, v = playera
        r = client.post(f"/api/products/{p.id}/variants", json={"variants": [
            {"color": "Rojo", "size": "M"},
            {"color": "Rojo", "size": "L", "sku": "PLY-RL", "barcode": "7500000000009", "price": "130"},
        ]}, headers=_h(auth_admin, org))
        assert r.status_code == 201, r.text
        skus = {x["sku"]: x for x in r.json()["variants"]}
        assert set(skus) == {"PLY", "PLY-ROJO-M", "PLY-RL"}
        assert skus["PLY-ROJO-M"]["variant_name"] == "Rojo / M"
        assert Decimal(str(skus["PLY-ROJO-M"]["price"])) == Decimal("100")   # hereda el precio base
        assert Decimal(str(skus["PLY-RL"]["price"])) == Decimal("130")
        nueva = db.query(ProductVariant).filter(ProductVariant.sku == "PLY-ROJO-M").one()
        assert db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == nueva.id,
                                                    ProductBranchStatus.branch_id == branch_a.id).count() == 1
        soh = db.query(StockOnHand).filter(StockOnHand.variant_id == nueva.id).one()
        assert soh.qty_on_hand == Decimal("0")

    def test_rechaza_pareja_repetida_y_sku_duplicado(self, client, db, org, playera, auth_admin):
        p, v = playera
        r = client.post(f"/api/products/{p.id}/variants", json={"variants": [{"color": "Rojo", "size": "M"}]},
                        headers=_h(auth_admin, org))
        assert r.status_code == 201
        r2 = client.post(f"/api/products/{p.id}/variants", json={"variants": [{"color": "rojo", "size": "m"}]},
                         headers=_h(auth_admin, org))
        assert r2.status_code == 409
        r3 = client.post(f"/api/products/{p.id}/variants", json={"variants": [{"color": "Azul", "size": "M", "sku": "PLY"}]},
                         headers=_h(auth_admin, org))
        assert r3.status_code == 409

    def test_talla_demasiado_larga_es_422(self, client, org, playera, auth_admin):
        p, _ = playera
        r = client.post(f"/api/products/{p.id}/variants", json={"variants": [{"color": "Rojo", "size": "x" * 31}]},
                        headers=_h(auth_admin, org))
        assert r.status_code == 422

    def test_producto_de_otra_org_es_404(self, client, db, org, auth_admin):
        from app.models.organization import Organization
        otra = Organization(name="Otra", status="ACTIVE"); db.add(otra); db.flush()
        p_ajeno, _ = _make_product(db, otra, "Ajena", "AJ-1", 10); db.commit()
        r = client.post(f"/api/products/{p_ajeno.id}/variants", json={"variants": [{"color": "Rojo", "size": "M"}]},
                        headers=_h(auth_admin, org))
        assert r.status_code == 404

    def test_cajero_sin_modulo_es_403(self, client, db, org, branch_a, auth_cajero_a):
        p, v = _make_product(db, org, "Gorra", "GOR", 50, [(branch_a.id, True)]); db.commit()
        r = client.post(f"/api/products/{p.id}/variants", json={"variants": [{"color": "Rojo", "size": "U"}]},
                        headers=_h(auth_cajero_a, org))
        assert r.status_code == 403


class TestEditarYBorrar:
    def test_put_cambia_talla_y_recalcula_etiqueta(self, client, db, org, playera, auth_admin):
        p, v = playera
        r = client.put(f"/api/products/variants/{v.id}", json={"color": "Negro", "size": "XL", "barcode": "7500000000011"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        db.refresh(v)
        assert (v.color, v.size, v.variant_name, v.barcode) == ("Negro", "XL", "Negro / XL", "7500000000011")

    def test_put_barcode_repetido_en_la_org_es_409(self, client, db, org, branch_a, playera, auth_admin):
        p, v = playera
        _, otra = _make_product(db, org, "Gorra", "GOR", 50, [(branch_a.id, True)])
        otra.barcode = "7500000000022"; db.commit()
        r = client.put(f"/api/products/variants/{v.id}", json={"barcode": "7500000000022"}, headers=_h(auth_admin, org))
        assert r.status_code == 409

    def test_delete_con_stock_es_409_y_sin_stock_borra_suave(self, client, db, org, branch_a, playera, auth_admin):
        p, v = playera
        r = client.post(f"/api/products/{p.id}/variants", json={"variants": [{"color": "Rojo", "size": "M"}]},
                        headers=_h(auth_admin, org))
        nueva_id = next(x["id"] for x in r.json()["variants"] if x["sku"] == "PLY-ROJO-M")
        assert client.delete(f"/api/products/variants/{v.id}", headers=_h(auth_admin, org)).status_code == 409  # tiene 100
        r2 = client.delete(f"/api/products/variants/{nueva_id}", headers=_h(auth_admin, org))
        assert r2.status_code == 204
        assert db.query(ProductVariant).get(nueva_id).deleted_at is not None
        # La ultima variante no se puede borrar aunque quede en cero
        soh = db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).one(); soh.qty_on_hand = Decimal(0); db.commit()
        assert client.delete(f"/api/products/variants/{v.id}", headers=_h(auth_admin, org)).status_code == 409


class TestExtraVariantsEnElAlta:
    def test_create_product_honra_extra_variants(self, client, db, org, branch_a, auth_admin):
        _habilitar(db, org, "variants")
        r = client.post("/api/products/", json={
            "name": "Pantalón", "sku": "PNT", "price": "300", "cost": "150",
            "target_branch_ids": [branch_a.id],
            "extra_variants": [{"color": "Azul", "size": "30"}, {"color": "Azul", "size": "32", "sku": "PNT-A32"}],
        }, headers=_h(auth_admin, org))
        assert r.status_code in (200, 201), r.text
        skus = {x["sku"] for x in r.json()["variants"]}
        assert skus == {"PNT", "PNT-AZUL-30", "PNT-A32"}
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_variant_endpoints.py`
Expected: 404 en todas las rutas nuevas; `extra_variants` ignorado.

- [ ] **Step 3: Implementar**

`schemas.py`, sustituir `ProductVariantCreate` y agregar los dos nuevos:

```python
class ProductVariantCreate(BaseModel):
    """Una variante de color/talla. `sku` vacio = generado desde el SKU base.
    `price`/`cost` vacios = heredan de la variante principal."""
    color: Optional[str] = None
    size: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    price: Optional[Decimal] = None
    cost: Optional[Decimal] = None


class VariantBatchCreate(BaseModel):
    variants: List[ProductVariantCreate]


class ProductVariantUpdate(BaseModel):
    color: Optional[str] = None
    size: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    price: Optional[Decimal] = None
    cost: Optional[Decimal] = None
```

`app/modules/products/router/variants.py`:

```python
"""Variantes de color/talla (preset boutique).

Las tiendas ATLAS_POS siguen con una variante "Estándar" por producto y nunca
llaman estos endpoints. Aqui vive todo lo que crea, edita o retira variantes;
`create_product` (core.py) delega en `crear_variantes` para `extra_variants`.
"""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_module
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.models import Product, ProductBranchStatus, ProductVariant, StockOnHand, User
from app.models.sales import SalesLineItem
from app.modules.products.schemas import (
    ProductRead, ProductVariantCreate, ProductVariantUpdate, VariantBatchCreate,
)
from app.modules.products.variant_label import COLOR_MAX, SIZE_MAX, clean_attr, variant_label

from ._shared import _compute_product_read

router = APIRouter()


def _slug(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "".join(c for c in sin_acentos.upper() if c.isalnum())


def _sku_generado(base: str, color: Optional[str], size: Optional[str]) -> str:
    partes = [base] + [_slug(x) for x in (color, size) if x]
    return "-".join(partes)


def _producto_de_la_org(db: Session, org_id: int, product_id: str) -> Product:
    p = (
        db.query(Product)
        .filter(Product.id == product_id, Product.organization_id == org_id)
        .first()
    )
    if p is None or not p.variants:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return p


def _variante_de_la_org(db: Session, org_id: int, variant_id: str) -> ProductVariant:
    v = (
        db.query(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(ProductVariant.id == variant_id, Product.organization_id == org_id,
                ProductVariant.deleted_at.is_(None))
        .first()
    )
    if v is None:
        raise HTTPException(status_code=404, detail="Variante no encontrada")
    return v


def _sku_en_uso(db: Session, org_id: int, sku: str, excepto_id: Optional[str] = None) -> bool:
    q = db.query(ProductVariant).filter(
        ProductVariant.organization_id == org_id,
        func.lower(ProductVariant.sku) == sku.lower(),
        ProductVariant.deleted_at.is_(None),
    )
    if excepto_id:
        q = q.filter(ProductVariant.id != excepto_id)
    return db.query(q.exists()).scalar()


def _barcode_en_uso(db: Session, org_id: int, barcode: str, excepto_id: Optional[str] = None) -> bool:
    q = db.query(ProductVariant).filter(
        ProductVariant.organization_id == org_id,
        ProductVariant.barcode == barcode,
        ProductVariant.deleted_at.is_(None),
    )
    if excepto_id:
        q = q.filter(ProductVariant.id != excepto_id)
    return db.query(q.exists()).scalar()


def _atributos(color: Optional[str], size: Optional[str], indice: int) -> tuple[Optional[str], Optional[str]]:
    try:
        return clean_attr(color, COLOR_MAX), clean_attr(size, SIZE_MAX)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"variants[{indice}]: color/talla {e}")


def _pareja_repetida(producto: Product, color: Optional[str], size: Optional[str], excepto_id: Optional[str] = None) -> bool:
    clave = ((color or "").lower(), (size or "").lower())
    for v in producto.variants:
        if v.deleted_at is not None or v.id == excepto_id:
            continue
        if ((v.color or "").lower(), (v.size or "").lower()) == clave:
            return True
    return False


def crear_variantes(db: Session, org_id: int, producto: Product, entradas: List[ProductVariantCreate]) -> List[ProductVariant]:
    """Crea variantes hermanas de la principal. Sin commit: lo hace el caller.

    Cada variante nueva hereda precio/costo/IVA de la principal si no los trae,
    y se habilita (PBS) con existencia 0 en las mismas sucursales donde ya esta
    la principal, para que aparezca en el POS de inmediato.
    """
    principal = producto.variants[0]
    pbs_base = db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == principal.id).all()
    nuevas: List[ProductVariant] = []
    vistos: set[tuple[str, str]] = set()
    for i, e in enumerate(entradas):
        color, size = _atributos(e.color, e.size, i)
        if not color and not size:
            raise HTTPException(status_code=422, detail=f"variants[{i}]: indica color o talla")
        clave = ((color or "").lower(), (size or "").lower())
        if clave in vistos or _pareja_repetida(producto, color, size):
            raise HTTPException(status_code=409, detail=f"Ya existe la variante {variant_label(color, size)}")
        vistos.add(clave)

        sku = (e.sku or "").strip() or _sku_generado(principal.sku, color, size)
        if _sku_en_uso(db, org_id, sku):
            raise HTTPException(status_code=409, detail=f"El SKU '{sku}' ya existe en esta organización.")
        barcode = (e.barcode or "").strip() or None
        if barcode and _barcode_en_uso(db, org_id, barcode):
            raise HTTPException(status_code=409, detail=f"El código de barras '{barcode}' ya lo tiene otra variante.")

        v = ProductVariant(
            product_id=producto.id,
            sku=sku,
            barcode=barcode,
            color=color,
            size=size,
            variant_name=variant_label(color, size),
            price=e.price if e.price is not None else principal.price,
            cost=e.cost if e.cost is not None else principal.cost,
            has_iva=principal.has_iva,
            tax_rate=principal.tax_rate,
            organization_id=org_id,
        )
        db.add(v)
        db.flush()
        for pbs in pbs_base:
            db.add(ProductBranchStatus(
                variant_id=v.id, branch_id=pbs.branch_id, organization_id=org_id,
                is_active_pos=pbs.is_active_pos, is_active_hq=pbs.is_active_hq, is_visible=pbs.is_visible,
            ))
            db.add(StockOnHand(variant_id=v.id, branch_id=pbs.branch_id, organization_id=org_id,
                               qty_on_hand=Decimal(0), is_active=True))
        nuevas.append(v)
    producto.has_variants = True
    db.flush()
    return nuevas


def _leer(db: Session, current_user: User, producto_id: str) -> ProductRead:
    p = db.query(Product).filter(Product.id == producto_id).first()
    db.refresh(p)
    return _compute_product_read(p, db, current_user)


@router.post("/{product_id}/variants", response_model=ProductRead, status_code=201,
             dependencies=[Depends(require_module("variants"))])
def crear_variantes_endpoint(
    product_id: str,
    body: VariantBatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    if not body.variants:
        raise HTTPException(status_code=422, detail="Manda al menos una variante")
    producto = _producto_de_la_org(db, org_id, product_id)
    try:
        crear_variantes(db, org_id, producto, body.variants)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    return _leer(db, current_user, product_id)


@router.put("/variants/{variant_id}", response_model=ProductRead,
            dependencies=[Depends(require_module("variants"))])
def editar_variante(
    variant_id: str,
    body: ProductVariantUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    v = _variante_de_la_org(db, org_id, variant_id)
    enviados = body.model_dump(exclude_unset=True)
    color = clean_attr(body.color, COLOR_MAX) if "color" in enviados else v.color
    size = clean_attr(body.size, SIZE_MAX) if "size" in enviados else v.size
    if ("color" in enviados or "size" in enviados) and _pareja_repetida(v.product, color, size, excepto_id=v.id):
        raise HTTPException(status_code=409, detail=f"Ya existe la variante {variant_label(color, size)}")
    if "sku" in enviados:
        sku = (body.sku or "").strip()
        if not sku:
            raise HTTPException(status_code=422, detail="El SKU no puede quedar vacío")
        if _sku_en_uso(db, org_id, sku, excepto_id=v.id):
            raise HTTPException(status_code=409, detail=f"El SKU '{sku}' ya existe en esta organización.")
        v.sku = sku
    if "barcode" in enviados:
        barcode = (body.barcode or "").strip() or None
        if barcode and _barcode_en_uso(db, org_id, barcode, excepto_id=v.id):
            raise HTTPException(status_code=409, detail=f"El código de barras '{barcode}' ya lo tiene otra variante.")
        v.barcode = barcode
    if body.price is not None:
        if body.price <= 0:
            raise HTTPException(status_code=422, detail="El precio debe ser mayor a cero.")
        v.price = body.price
    if body.cost is not None:
        v.cost = body.cost
    v.color, v.size = color, size
    v.variant_name = variant_label(color, size)
    db.commit()
    return _leer(db, current_user, v.product_id)


@router.delete("/variants/{variant_id}", status_code=204,
               dependencies=[Depends(require_module("variants"))])
def retirar_variante(
    variant_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    v = _variante_de_la_org(db, org_id, variant_id)
    vivas = [x for x in v.product.variants if x.deleted_at is None]
    if len(vivas) <= 1:
        raise HTTPException(status_code=409, detail="Es la única variante del producto; desactiva el producto en su lugar.")
    con_stock = db.query(StockOnHand).filter(StockOnHand.variant_id == v.id, StockOnHand.qty_on_hand > 0).first()
    if con_stock is not None:
        raise HTTPException(status_code=409, detail="La variante tiene existencia; ajústala a cero antes de retirarla.")
    if db.query(SalesLineItem).filter(SalesLineItem.variant_id == v.id).first() is not None:
        raise HTTPException(status_code=409, detail="La variante tiene ventas; no se puede retirar, solo desactivar el producto.")
    v.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=204)
```

`router/__init__.py`: agregar `variants` a la tupla `from . import (...)` y registrarlo junto a los demás sub-routers (línea 46-55). No hay choque de rutas: `/variants/{id}` tiene dos segmentos y `core` solo declara `/{product_id}` con uno.

```python
router.include_router(variants.router)
```

`core.py`, en `create_product` justo después de `db.flush()` de `new_variant` y del bloque de stock inicial/PBS (es decir, después de que exista el PBS de la variante principal, antes del `db.commit()`):

```python
        # Variantes hermanas (boutique). Heredan precio/costo/IVA y se
        # habilitan donde quedo la principal. Solo llega con el modulo
        # `variants`; el formulario de las demas tiendas no manda la lista.
        if prod_in.extra_variants:
            from .variants import crear_variantes
            crear_variantes(db, org_id, new_prod, prod_in.extra_variants)
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `python3 -m pytest -q -p no:warnings tests/test_variant_endpoints.py tests/test_product_creation.py`
Expected: PASSED. Suite completa sin nuevos `failed`.

- [ ] **Step 5: Commit**

```bash
git add app/modules/products/router/variants.py app/modules/products/router/__init__.py app/modules/products/router/core.py app/modules/products/schemas.py tests/test_variant_endpoints.py
git commit -m "feat(variants): endpoints de variantes y extra_variants en el alta"
```

---

### Task 9: Cliente de API y generador puro de la matriz color × talla

**Files:**
- Create: `frontend/src/components/products/variantMatrix.ts`
- Modify: `frontend/src/api/products.ts` (`ProductCreate.extra_variants`, métodos `createVariants`, `updateVariant`, `deleteVariant`)
- Test: `frontend/src/components/products/__tests__/variantMatrix.test.ts`

**Interfaces:**
- Produces:
  - `VariantRow { key: string; color: string; size: string; sku: string; barcode: string; price: string }`
  - `buildVariantRows(baseSku: string, colors: string[], sizes: string[], previous: VariantRow[]): VariantRow[]` — producto cartesiano, conserva lo tecleado en filas que ya existían, SKU sugerido `BASE-COLOR-TALLA`.
  - `parseList(text: string): string[]` — separa por coma o salto de línea, recorta, deduplica sin distinguir mayúsculas.
  - `toExtraVariants(rows: VariantRow[]): ExtraVariantPayload[]`.
  - `productsApi.createVariants(productId, rows)`, `updateVariant(variantId, patch)`, `deleteVariant(variantId)`.

- [ ] **Step 1: Prueba que falla**

```ts
// frontend/src/components/products/__tests__/variantMatrix.test.ts
import { describe, it, expect } from 'vitest'

import { buildVariantRows, parseList, toExtraVariants } from '../variantMatrix'

describe('parseList', () => {
  it('separa por coma o salto de línea y deduplica sin mayúsculas', () => {
    expect(parseList('Rojo, azul\nROJO ,  Negro ')).toEqual(['Rojo', 'azul', 'Negro'])
  })
  it('vacío es lista vacía', () => {
    expect(parseList('  ')).toEqual([])
  })
})

describe('buildVariantRows', () => {
  it('hace el producto cartesiano con SKU sugerido', () => {
    const rows = buildVariantRows('PLY', ['Rojo'], ['S', 'M'], [])
    expect(rows.map((r) => r.sku)).toEqual(['PLY-ROJO-S', 'PLY-ROJO-M'])
    expect(rows[0].key).toBe('rojo|s')
  })
  it('conserva lo tecleado en filas que ya existían', () => {
    const prev = buildVariantRows('PLY', ['Rojo'], ['S'], [])
    prev[0].barcode = '750'
    prev[0].sku = 'MI-SKU'
    const rows = buildVariantRows('PLY', ['Rojo'], ['S', 'M'], prev)
    expect(rows[0]).toMatchObject({ sku: 'MI-SKU', barcode: '750' })
    expect(rows[1].sku).toBe('PLY-ROJO-M')
  })
  it('quita acentos y espacios del SKU sugerido', () => {
    expect(buildVariantRows('PLY', ['Azul marino'], ['Única'], [])[0].sku).toBe('PLY-AZULMARINO-UNICA')
  })
  it('solo colores o solo tallas también genera filas', () => {
    expect(buildVariantRows('PLY', [], ['S', 'M'], []).map((r) => r.size)).toEqual(['S', 'M'])
    expect(buildVariantRows('PLY', ['Rojo'], [], []).map((r) => r.color)).toEqual(['Rojo'])
  })
})

describe('toExtraVariants', () => {
  it('manda solo lo que trae valor', () => {
    const [row] = buildVariantRows('PLY', ['Rojo'], ['S'], [])
    row.price = ''
    expect(toExtraVariants([row])).toEqual([{ color: 'Rojo', size: 'S', sku: 'PLY-ROJO-S' }])
    row.price = '130'; row.barcode = '750'
    expect(toExtraVariants([row])[0]).toMatchObject({ price: 130, barcode: '750' })
  })
})
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/components/products`
Expected: FAIL, módulo no existe.

- [ ] **Step 3: Implementar**

`frontend/src/components/products/variantMatrix.ts`:

```ts
/**
 * Matriz color × talla del alta de producto (preset boutique).
 *
 * Funciones puras: el formulario solo pinta lo que sale de aquí. Cada fila es
 * una variante candidata; la principal (la del SKU base) no está en la matriz.
 */
export interface VariantRow {
  key: string      // "rojo|m" — identidad estable entre regeneraciones
  color: string
  size: string
  sku: string
  barcode: string
  price: string    // vacío = hereda el precio base
}

export interface ExtraVariantPayload {
  color?: string
  size?: string
  sku?: string
  barcode?: string
  price?: number
}

export function parseList(text: string): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const raw of text.split(/[,\n]/)) {
    const v = raw.trim()
    if (!v) continue
    const k = v.toLowerCase()
    if (seen.has(k)) continue
    seen.add(k)
    out.push(v)
  }
  return out
}

/** "Azul marino" → "AZULMARINO": mayúsculas, sin acentos ni espacios. */
export function skuPart(text: string): string {
  return text.normalize('NFKD').replace(/[̀-ͯ]/g, '').toUpperCase().replace(/[^A-Z0-9]/g, '')
}

const rowKey = (color: string, size: string) => `${color.toLowerCase()}|${size.toLowerCase()}`

export function buildVariantRows(baseSku: string, colors: string[], sizes: string[], previous: VariantRow[]): VariantRow[] {
  const cs = colors.length ? colors : ['']
  const ss = sizes.length ? sizes : ['']
  const prev = new Map(previous.map((r) => [r.key, r]))
  const rows: VariantRow[] = []
  for (const color of cs) {
    for (const size of ss) {
      if (!color && !size) continue
      const key = rowKey(color, size)
      const old = prev.get(key)
      if (old) { rows.push({ ...old, color, size }); continue }
      const sku = [baseSku.trim(), ...[color, size].filter(Boolean).map(skuPart)].filter(Boolean).join('-')
      rows.push({ key, color, size, sku, barcode: '', price: '' })
    }
  }
  return rows
}

export function toExtraVariants(rows: VariantRow[]): ExtraVariantPayload[] {
  return rows.map((r) => {
    const out: ExtraVariantPayload = {}
    if (r.color) out.color = r.color
    if (r.size) out.size = r.size
    if (r.sku.trim()) out.sku = r.sku.trim()
    if (r.barcode.trim()) out.barcode = r.barcode.trim()
    const p = Number(r.price)
    if (r.price.trim() && Number.isFinite(p) && p > 0) out.price = p
    return out
  })
}
```

`frontend/src/api/products.ts`: en `ProductCreate` agregar `extra_variants?: ExtraVariantPayload[]` (importar el tipo desde `../components/products/variantMatrix`), y en `productsApi`:

```ts
  /** POST /api/products/{id}/variants — agrega variantes de color/talla (módulo `variants`). */
  createVariants: async (productId: string, variants: ExtraVariantPayload[]): Promise<Product> => {
    const { data } = await client.post<Product>(`/products/${productId}/variants`, { variants })
    return data
  },

  updateVariant: async (
    variantId: string,
    patch: { color?: string | null; size?: string | null; sku?: string; barcode?: string | null; price?: number; cost?: number },
  ): Promise<Product> => {
    const { data } = await client.put<Product>(`/products/variants/${variantId}`, patch)
    return data
  },

  deleteVariant: async (variantId: string): Promise<void> => {
    await client.delete(`/products/variants/${variantId}`)
  },
```

- [ ] **Step 4: Correr y ver que pasa**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: verde.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/products/variantMatrix.ts frontend/src/components/products/__tests__/variantMatrix.test.ts frontend/src/api/products.ts
git commit -m "feat(variants): cliente de API y generador de la matriz color x talla"
```

---

### Task 10: Sección de variantes en el alta de producto (solo con el módulo activo)

**Files:**
- Create: `frontend/src/components/products/ProductVariantsSection.tsx`
- Modify: `frontend/src/pages/admin/AdminProductCreate.tsx` (estado `variantRows`, sección, payload)
- Modify: `frontend/src/pages/products/ProductForm.tsx` (mismo, modo `create`)

**Interfaces:**
- Consumes: `buildVariantRows`, `parseList`, `toExtraVariants`, `VariantRow` (Task 9); `useEnabledModulesStore` (`enabledModules.includes('variants')`).
- Produces: `<ProductVariantsSection baseSku rows onRowsChange />` con dos campos de texto (colores, tallas) y una tabla editable (SKU, código, precio) por combinación.

- [ ] **Step 1: Implementar el componente**

```tsx
// frontend/src/components/products/ProductVariantsSection.tsx
import { useState } from 'react'

import { buildVariantRows, parseList, type VariantRow } from './variantMatrix'

interface Props {
  baseSku: string
  rows: VariantRow[]
  onRowsChange: (rows: VariantRow[]) => void
}

/**
 * Matriz color × talla (preset boutique). El admin escribe los colores y las
 * tallas separados por coma; cada combinación es una variante con su SKU
 * sugerido, su código de barras y (opcional) su precio. La variante principal
 * (SKU base) no aparece aquí: es la que capturan los campos de arriba.
 */
export function ProductVariantsSection({ baseSku, rows, onRowsChange }: Props) {
  const [colors, setColors] = useState('')
  const [sizes, setSizes] = useState('')

  const regenerate = (c: string, s: string) => {
    onRowsChange(buildVariantRows(baseSku, parseList(c), parseList(s), rows))
  }
  const setRow = (key: string, patch: Partial<VariantRow>) => {
    onRowsChange(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)))
  }

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-black uppercase tracking-wide text-slate-300">Variantes (color / talla)</h3>
      <p className="text-[11px] text-slate-500">
        Escribe colores y tallas separados por coma. Cada combinación se crea como una variante con su
        propio código y existencia. Si la prenda no tiene variantes, deja esto vacío.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="text-xs text-slate-400">Colores</span>
          <input className="dax-input mt-1" value={colors} placeholder="Rojo, Negro, Azul marino"
                 onChange={(e) => { setColors(e.target.value); regenerate(e.target.value, sizes) }} />
        </label>
        <label className="block">
          <span className="text-xs text-slate-400">Tallas</span>
          <input className="dax-input mt-1" value={sizes} placeholder="S, M, L, XL"
                 onChange={(e) => { setSizes(e.target.value); regenerate(colors, e.target.value) }} />
        </label>
      </div>
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-400">
                <th className="py-1 pr-2">Variante</th>
                <th className="py-1 pr-2">SKU</th>
                <th className="py-1 pr-2">Código de barras</th>
                <th className="py-1 pr-2">Precio (vacío = base)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}>
                  <td className="py-1 pr-2 font-semibold text-slate-200">{[r.color, r.size].filter(Boolean).join(' / ')}</td>
                  <td className="py-1 pr-2"><input className="dax-input" value={r.sku} onChange={(e) => setRow(r.key, { sku: e.target.value })} /></td>
                  <td className="py-1 pr-2"><input className="dax-input" value={r.barcode} inputMode="numeric" onChange={(e) => setRow(r.key, { barcode: e.target.value })} /></td>
                  <td className="py-1 pr-2"><input className="dax-input" value={r.price} inputMode="decimal" onChange={(e) => setRow(r.key, { price: e.target.value })} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-[11px] text-slate-500 mt-1">{rows.length} variantes además de la principal.</p>
        </div>
      )}
    </section>
  )
}
```

- [ ] **Step 2: Conectar en `AdminProductCreate.tsx`**

Imports:

```ts
import { useEnabledModulesStore } from '../../store/enabledModulesStore'
import { ProductVariantsSection } from '../../components/products/ProductVariantsSection'
import { toExtraVariants, type VariantRow } from '../../components/products/variantMatrix'
```

Estado junto a `prices`:

```ts
  const hasVariantsModule = useEnabledModulesStore((s) => s.enabledModules.includes('variants'))
  const [variantRows, setVariantRows] = useState<VariantRow[]>([])
```

En `validate()`, después de la validación de `prices`:

```ts
    const skus = new Set<string>([form.sku.trim().toLowerCase()])
    variantRows.forEach((r, i) => {
      const s = r.sku.trim().toLowerCase()
      if (!s) e[`variants.${i}.sku`] = 'SKU requerido'
      else if (skus.has(s)) e[`variants.${i}.sku`] = 'SKU repetido'
      skus.add(s)
      if (r.price.trim() && !(Number(r.price) > 0)) e[`variants.${i}.price`] = 'Precio mayor a 0'
    })
```

En el `payload` de `handleSubmit`, después de `prices`:

```ts
      ...(hasVariantsModule && variantRows.length > 0 ? { extra_variants: toExtraVariants(variantRows) } : {}),
```

En el JSX, después de `<ProductTieredPricesSection …/>`:

```tsx
          {hasVariantsModule && (
            <ProductVariantsSection baseSku={form.sku} rows={variantRows} onRowsChange={setVariantRows} />
          )}
```

Repetir los mismos cuatro cambios en `ProductForm.tsx` (solo aplican en `mode === 'create'`; en edición la sección la cubre la Task 11).

- [ ] **Step 3: Verificar**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: verde. Prueba manual en local con una org boutique: crear "Playera" con colores "Rojo" y tallas "S, M" → `GET /api/products/{id}` devuelve tres variantes.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/products/ProductVariantsSection.tsx frontend/src/pages/admin/AdminProductCreate.tsx frontend/src/pages/products/ProductForm.tsx
git commit -m "feat(variants): matriz color x talla en el alta de producto"
```

---

### Task 11: Edición de un producto con variantes

**Files:**
- Create: `frontend/src/components/products/ProductVariantsEditor.tsx`
- Modify: `frontend/src/pages/products/ProductForm.tsx:72-96` (precarga) y `:211-230` (guardado)

**Interfaces:**
- Consumes: `productsApi.updateVariant`, `deleteVariant`, `createVariants` (Task 9); `ProductVariant` con `variant_name/color/size/stock_total` (Task 3).
- Produces: en modo edición, tabla de variantes existentes con edición en línea de color, talla, SKU, código y precio; botón "Agregar variantes" que reutiliza `ProductVariantsSection` y llama `createVariants`; retiro con confirmación (el backend rechaza si hay existencia o ventas). Los campos aplanados del formulario (SKU/código/precio) editan **solo la variante principal** y se etiquetan así cuando hay más de una.

- [ ] **Step 1: Implementar el editor**

```tsx
// frontend/src/components/products/ProductVariantsEditor.tsx
import { useState } from 'react'

import { productsApi } from '../../api/products'
import type { Product, ProductVariant } from '../../types/products'
import { errorDetailText } from '../../utils/errorDetail'
import { ProductVariantsSection } from './ProductVariantsSection'
import { toExtraVariants, type VariantRow } from './variantMatrix'

interface Props {
  product: Product
  onChanged: (p: Product) => void
}

/**
 * Variantes existentes de un producto (edición). Cada fila guarda por su
 * cuenta con PUT /api/products/variants/{id}; el formulario de arriba sigue
 * editando solo la principal. Retirar pasa por DELETE y el backend decide
 * (409 con existencia o ventas).
 */
export function ProductVariantsEditor({ product, onChanged }: Props) {
  const [busyId, setBusyId] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [rows, setRows] = useState<VariantRow[]>([])
  const variants = product.variants ?? []

  const save = async (v: ProductVariant, patch: Parameters<typeof productsApi.updateVariant>[1]) => {
    setBusyId(v.id); setMsg(null)
    try { onChanged(await productsApi.updateVariant(v.id, patch)) }
    catch (err) {
      const e = err as { response?: { data?: { detail?: unknown } } }
      setMsg(errorDetailText(e?.response?.data?.detail, 'No se pudo guardar la variante.'))
    } finally { setBusyId(null) }
  }

  const remove = async (v: ProductVariant) => {
    if (!window.confirm(`¿Retirar la variante ${v.variant_name ?? v.sku}?`)) return
    setBusyId(v.id); setMsg(null)
    try {
      await productsApi.deleteVariant(v.id)
      onChanged(await productsApi.getById(product.id))
    } catch (err) {
      const e = err as { response?: { data?: { detail?: unknown } } }
      setMsg(errorDetailText(e?.response?.data?.detail, 'No se pudo retirar la variante.'))
    } finally { setBusyId(null) }
  }

  const addRows = async () => {
    if (rows.length === 0) return
    setBusyId('new'); setMsg(null)
    try {
      onChanged(await productsApi.createVariants(product.id, toExtraVariants(rows)))
      setRows([]); setAdding(false)
    } catch (err) {
      const e = err as { response?: { data?: { detail?: unknown } } }
      setMsg(errorDetailText(e?.response?.data?.detail, 'No se pudieron crear las variantes.'))
    } finally { setBusyId(null) }
  }

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-black uppercase tracking-wide text-slate-300">Variantes ({variants.length})</h3>
      {msg && <p className="text-sm text-amber-400">{msg}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead><tr className="text-left text-slate-400">
            <th className="py-1 pr-2">Color</th><th className="py-1 pr-2">Talla</th><th className="py-1 pr-2">SKU</th>
            <th className="py-1 pr-2">Código</th><th className="py-1 pr-2">Precio</th><th className="py-1 pr-2">Existencia</th><th />
          </tr></thead>
          <tbody>
            {variants.map((v) => (
              <VariantRowEditor key={v.id} v={v} busy={busyId === v.id} onSave={(patch) => save(v, patch)} onRemove={() => remove(v)} />
            ))}
          </tbody>
        </table>
      </div>
      {!adding ? (
        <button type="button" className="dax-btn-secondary" onClick={() => setAdding(true)}>Agregar variantes</button>
      ) : (
        <div className="space-y-2">
          <ProductVariantsSection baseSku={product.sku} rows={rows} onRowsChange={setRows} />
          <div className="flex gap-2">
            <button type="button" className="dax-btn-primary" disabled={busyId === 'new' || rows.length === 0} onClick={addRows}>Crear {rows.length} variantes</button>
            <button type="button" className="dax-btn-secondary" onClick={() => { setAdding(false); setRows([]) }}>Cancelar</button>
          </div>
        </div>
      )}
    </section>
  )
}

function VariantRowEditor({ v, busy, onSave, onRemove }: {
  v: ProductVariant; busy: boolean
  onSave: (patch: { color?: string | null; size?: string | null; sku?: string; barcode?: string | null; price?: number }) => void
  onRemove: () => void
}) {
  const [color, setColor] = useState(v.color ?? '')
  const [size, setSize] = useState(v.size ?? '')
  const [sku, setSku] = useState(v.sku)
  const [barcode, setBarcode] = useState(v.barcode ?? '')
  const [price, setPrice] = useState(String(v.price))
  const dirty = color !== (v.color ?? '') || size !== (v.size ?? '') || sku !== v.sku || barcode !== (v.barcode ?? '') || Number(price) !== Number(v.price)
  return (
    <tr>
      <td className="py-1 pr-2"><input className="dax-input" value={color} onChange={(e) => setColor(e.target.value)} /></td>
      <td className="py-1 pr-2"><input className="dax-input" value={size} onChange={(e) => setSize(e.target.value)} /></td>
      <td className="py-1 pr-2"><input className="dax-input" value={sku} onChange={(e) => setSku(e.target.value)} /></td>
      <td className="py-1 pr-2"><input className="dax-input" value={barcode} onChange={(e) => setBarcode(e.target.value)} /></td>
      <td className="py-1 pr-2"><input className="dax-input" value={price} inputMode="decimal" onChange={(e) => setPrice(e.target.value)} /></td>
      <td className="py-1 pr-2 text-slate-300">{Number(v.stock_total ?? 0)}</td>
      <td className="py-1 flex gap-1">
        <button type="button" className="dax-btn-primary" disabled={!dirty || busy}
                onClick={() => onSave({ color: color || null, size: size || null, sku, barcode: barcode || null, price: Number(price) })}>Guardar</button>
        <button type="button" className="dax-btn-secondary" disabled={busy} onClick={onRemove}>Retirar</button>
      </td>
    </tr>
  )
}
```

- [ ] **Step 2: Conectar en `ProductForm.tsx`**

- Guardar el producto cargado: `const [loaded, setLoaded] = useState<Product | null>(null)` y `setLoaded(p)` en la precarga.
- Mostrar en modo edición, cuando `hasVariantsModule`:

```tsx
          {mode === 'edit' && hasVariantsModule && loaded && (
            <ProductVariantsEditor product={loaded} onChanged={setLoaded} />
          )}
```

- Si `loaded.variants.length > 1`, poner debajo de los campos SKU/código/precio el aviso: `Estos campos editan la variante principal (${loaded.variants[0].variant_name}). Las demás se editan en la tabla de variantes.`

- [ ] **Step 3: Verificar y commit**

Run: `cd frontend && npx tsc --noEmit && npm run build`

```bash
git add frontend/src/components/products/ProductVariantsEditor.tsx frontend/src/pages/products/ProductForm.tsx
git commit -m "feat(variants): edicion de variantes existentes y alta incremental"
```

**Hito de fase 2:** desplegar. Eleven captura prendas con su curva de tallas desde el panel.

---
## Fase 3 — Operación diaria

### Task 12: Selector de talla y color en el POS

**Files:**
- Create: `frontend/src/components/pos/modals/VariantPickerModal.tsx`
- Create: `frontend/src/components/pos/variantPicker.ts`
- Modify: `frontend/src/components/pos/ProductSearch.tsx` (auto-add por Enter, clic en tarjeta, badge "N variantes")
- Test: `frontend/src/components/pos/__tests__/variantPicker.test.ts`

**Interfaces:**
- Consumes: `productsApi.getById` (colección completa), `ProductVariant.stock_total`, `addToCart` (Task 6).
- Produces: `needsPicker(p: Product): boolean` (más de una variante viva y sin `matched_variant_id` que la resuelva), `groupVariants(vs): { colors: string[]; sizes: string[]; at(color, size): ProductVariant | undefined }`, `<VariantPickerModal product onPick onClose />`, y `pickVariantForCart(p: Product, v: ProductVariant): Product` que devuelve el producto con `matched_variant_id`, `sku`, `price` y `stock_total` de la variante para que `addToCart` no cambie.

- [ ] **Step 1: Prueba que falla**

```ts
// frontend/src/components/pos/__tests__/variantPicker.test.ts
import { describe, it, expect } from 'vitest'

import { groupVariants, needsPicker, pickVariantForCart } from '../variantPicker'
import type { Product, ProductVariant } from '../../../types/products'

const v = (id: string, color: string | null, size: string | null, stock: number): ProductVariant => ({
  id, product_id: 'p1', sku: `PLY-${id}`, color, size, variant_name: [color, size].filter(Boolean).join(' / ') || 'Estándar',
  price: 120, cost: 60, stock_total: stock,
})
const base: Product = {
  id: 'p1', sku: 'PLY-s', name: 'Playera', description: null, brand_id: null, brand_name: null, department: null,
  department_name: null, unit: 'pza', cost: 60, price: 100, stock: 0, stock_total: 3, image_url: null, is_active: true,
  variants: [v('s', 'Rojo', 'S', 3), v('m', 'Rojo', 'M', 0), v('lm', 'Negro', 'M', 5)],
}

describe('needsPicker', () => {
  it('sí con varias variantes y sin empate de código', () => {
    expect(needsPicker({ ...base, matched_variant_id: null })).toBe(true)
  })
  it('no cuando el escaneo ya resolvió la variante', () => {
    expect(needsPicker({ ...base, matched_variant_id: 'm' })).toBe(false)
  })
  it('no con una sola variante', () => {
    expect(needsPicker({ ...base, variants: [v('s', null, null, 3)], matched_variant_id: null })).toBe(false)
  })
})

describe('groupVariants', () => {
  it('lista colores y tallas en orden de aparición y localiza la celda', () => {
    const g = groupVariants(base.variants!)
    expect(g.colors).toEqual(['Rojo', 'Negro'])
    expect(g.sizes).toEqual(['S', 'M'])
    expect(g.at('Negro', 'M')?.id).toBe('lm')
    expect(g.at('Negro', 'S')).toBeUndefined()
  })
})

describe('pickVariantForCart', () => {
  it('deja el producto listo para addToCart con los datos de la talla', () => {
    const p = pickVariantForCart(base, base.variants![2])
    expect(p.matched_variant_id).toBe('lm')
    expect(p.sku).toBe('PLY-lm')
    expect(Number(p.stock_total)).toBe(5)
    expect(Number(p.price)).toBe(120)
  })
})
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/components/pos`
Expected: FAIL, módulo no existe.

- [ ] **Step 3: Implementar**

```ts
// frontend/src/components/pos/variantPicker.ts
import type { Product, ProductVariant } from '../../types/products'

/** ¿Hay que preguntar talla/color antes de agregar al carrito? */
export function needsPicker(p: Product): boolean {
  const n = p.variants?.length ?? 0
  if (n <= 1) return false
  return !p.matched_variant_id
}

export function groupVariants(vs: ProductVariant[]) {
  const colors: string[] = []
  const sizes: string[] = []
  const idx = new Map<string, ProductVariant>()
  const k = (c: string, s: string) => `${c.toLowerCase()}|${s.toLowerCase()}`
  for (const v of vs) {
    const c = v.color ?? ''
    const s = v.size ?? ''
    if (!colors.some((x) => x.toLowerCase() === c.toLowerCase())) colors.push(c)
    if (!sizes.some((x) => x.toLowerCase() === s.toLowerCase())) sizes.push(s)
    idx.set(k(c, s), v)
  }
  return { colors, sizes, at: (c: string, s: string) => idx.get(k(c, s)) }
}

/** Producto con los campos aplanados de la variante elegida (lo que consume addToCart). */
export function pickVariantForCart(p: Product, v: ProductVariant): Product {
  return {
    ...p,
    matched_variant_id: v.id,
    sku: v.sku,
    barcode: v.barcode ?? null,
    price: Number(v.price),
    stock_total: Number(v.stock_total ?? 0),
    prices: v.prices ?? p.prices,
    packaging_units: v.packaging_units ?? p.packaging_units,
  }
}
```

```tsx
// frontend/src/components/pos/modals/VariantPickerModal.tsx
import { useEffect, useState } from 'react'

import { productsApi } from '../../../api/products'
import type { Product, ProductVariant } from '../../../types/products'
import { formatCurrency } from '../../../utils/currency'
import { groupVariants } from '../variantPicker'

interface Props {
  product: Product
  onPick: (v: ProductVariant) => void
  onClose: () => void
}

/**
 * Cuadrícula color × talla con la existencia de cada celda. Recarga el
 * producto con GET /api/products/{id} porque la búsqueda del POS puede traer
 * la colección de variantes incompleta (eager-load filtrado por el término).
 */
export function VariantPickerModal({ product, onPick, onClose }: Props) {
  const [full, setFull] = useState<Product>(product)
  useEffect(() => {
    let cancelled = false
    productsApi.getById(product.id).then((p) => { if (!cancelled) setFull(p) }).catch(() => {})
    return () => { cancelled = true }
  }, [product.id])

  const g = groupVariants(full.variants ?? [])
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl p-4" style={{ background: 'var(--dax-surface)' }} onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-black" style={{ color: 'var(--dax-text)' }}>{full.name}</h3>
        <p className="text-xs mb-3" style={{ color: 'var(--dax-text-muted)' }}>Elige la variante</p>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead><tr>
              <th />
              {g.sizes.map((s) => <th key={s} className="py-1 px-1 text-center" style={{ color: 'var(--dax-text-muted)' }}>{s || '—'}</th>)}
            </tr></thead>
            <tbody>
              {g.colors.map((c) => (
                <tr key={c}>
                  <td className="py-1 pr-2 font-semibold" style={{ color: 'var(--dax-text)' }}>{c || '—'}</td>
                  {g.sizes.map((s) => {
                    const v = g.at(c, s)
                    const stock = Number(v?.stock_total ?? 0)
                    return (
                      <td key={s} className="py-1 px-1 text-center">
                        {v ? (
                          <button type="button" disabled={stock <= 0} onClick={() => onPick(v)}
                                  className="w-full rounded-lg px-2 py-2 font-bold disabled:opacity-40"
                                  style={{ background: 'var(--dax-elevated)', color: 'var(--dax-text)' }}
                                  title={`${v.sku} · ${formatCurrency(Number(v.price))}`}>
                            {stock}
                          </button>
                        ) : <span style={{ color: 'var(--dax-text-faint)' }}>·</span>}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-[11px] mt-2" style={{ color: 'var(--dax-text-faint)' }}>El número es la existencia en tu sucursal.</p>
        <button type="button" className="dax-btn-secondary mt-3 w-full" onClick={onClose}>Cancelar</button>
      </div>
    </div>
  )
}
```

`ProductSearch.tsx`:
- Estado: `const [pickerFor, setPickerFor] = useState<Product | null>(null)`.
- Nueva función que reemplaza las llamadas directas a `addToCart(p)` en el clic de tarjeta y en `handleKeyDown` (Enter con un solo resultado):

```ts
  const addOrPick = (p: Product) => {
    if (needsPicker(p)) { setPickerFor(p); return }
    addToCart(p)
  }
```

- Render del modal al final del componente:

```tsx
      {pickerFor && (
        <VariantPickerModal
          product={pickerFor}
          onPick={(v) => { addToCart(pickVariantForCart(pickerFor, v)); setPickerFor(null) }}
          onClose={() => { setPickerFor(null); devolverFoco() }}
        />
      )}
```

- Badge en la tarjeta, junto al SKU, cuando `(p.variants?.length ?? 0) > 1`: `<span className="text-[9px] font-bold px-1.5 py-0.5 rounded" style={{ background: 'rgba(99,102,241,0.15)', color: '#4338ca' }}>{p.variants!.length} variantes</span>`.
- El botón de la tarjeta se deshabilita hoy con `stock <= 0`; para productos con varias variantes usar la suma: `const stock = (p.variants?.length ?? 0) > 1 ? p.variants!.reduce((a, v) => a + Number(v.stock_total ?? 0), 0) : stockNum(p)`.

- [ ] **Step 4: Verificar y commit**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npm run build`

```bash
git add frontend/src/components/pos/variantPicker.ts frontend/src/components/pos/__tests__/variantPicker.test.ts frontend/src/components/pos/modals/VariantPickerModal.tsx frontend/src/components/pos/ProductSearch.tsx
git commit -m "feat(pos): selector de talla y color al agregar un producto con variantes"
```

---

### Task 13: Inventario por variante en las vistas y matriz de sucursales sobre todas las variantes

**Files:**
- Create: `frontend/src/pages/inventory/variantRows.ts`
- Modify: `frontend/src/pages/inventory/Inventory.tsx:38-52`, `frontend/src/pages/hq/HQInventory.tsx:39-61`, `frontend/src/components/branch/ProductsBranchView.tsx:19-22, 113, 942-961`, `frontend/src/pages/inventory/Products.tsx:183-190, 1293, 1381`
- Modify: `frontend/src/components/catalog/ProductBranchMatrix.tsx:17, 87, 117`
- Modify: `frontend/src/components/pos/modals/ProductDetailModal.tsx:300` (selector de variante para el ajuste)
- Test: `frontend/src/pages/inventory/__tests__/variantRows.test.ts`

**Interfaces:**
- Produces: `InventoryRow { product: Product; variant: ProductVariant; label: string; sku: string; barcode: string | null; qty: number }` y `expandVariantRows(products: Product[]): InventoryRow[]` — un renglón por variante (con una sola variante, la etiqueta es el nombre del producto a secas). Kardex y ajustes reciben `row.variant.id`.

- [ ] **Step 1: Prueba que falla**

```ts
// frontend/src/pages/inventory/__tests__/variantRows.test.ts
import { describe, it, expect } from 'vitest'

import { expandVariantRows } from '../variantRows'
import type { Product } from '../../../types/products'

const playera: Product = {
  id: 'p1', sku: 'PLY-S', name: 'Playera', description: null, brand_id: null, brand_name: null, department: null,
  department_name: null, unit: 'pza', cost: 60, price: 100, stock: 0, stock_total: 3, image_url: null, is_active: true,
  variants: [
    { id: 'v-s', product_id: 'p1', sku: 'PLY-S', variant_name: 'Rojo / S', price: 100, cost: 60, stock_total: '3' },
    { id: 'v-m', product_id: 'p1', sku: 'PLY-M', variant_name: 'Rojo / M', price: 100, cost: 60, stock_total: '0' },
  ],
}
const gorra: Product = { ...playera, id: 'p2', sku: 'GOR', name: 'Gorra', stock_total: 9,
  variants: [{ id: 'v-g', product_id: 'p2', sku: 'GOR', variant_name: 'Estándar', price: 50, cost: 20, stock_total: '9' }] }

describe('expandVariantRows', () => {
  it('un renglón por variante con etiqueta y existencia propia', () => {
    const rows = expandVariantRows([playera, gorra])
    expect(rows.map((r) => r.label)).toEqual(['Playera · Rojo / S', 'Playera · Rojo / M', 'Gorra'])
    expect(rows.map((r) => r.qty)).toEqual([3, 0, 9])
    expect(rows[1].variant.id).toBe('v-m')
  })
  it('producto sin variantes genera un renglón con lo aplanado', () => {
    const rows = expandVariantRows([{ ...gorra, variants: [] }])
    expect(rows).toHaveLength(1)
    expect(rows[0].qty).toBe(9)
    expect(rows[0].variant.id).toBe('p2')
  })
})
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/pages/inventory`

- [ ] **Step 3: Implementar**

```ts
// frontend/src/pages/inventory/variantRows.ts
import type { Product, ProductVariant } from '../../types/products'

export interface InventoryRow {
  product: Product
  variant: ProductVariant
  label: string
  sku: string
  barcode: string | null
  qty: number
}

/**
 * Un renglón de inventario por variante. Antes las pantallas tomaban
 * `variants[0]` y con varias tallas el kardex y los ajustes iban a la primera.
 */
export function expandVariantRows(products: Product[]): InventoryRow[] {
  const rows: InventoryRow[] = []
  for (const p of products) {
    const vs = p.variants ?? []
    if (vs.length === 0) {
      rows.push({
        product: p,
        variant: { id: p.id, product_id: p.id, sku: p.sku, price: p.price, cost: p.cost, variant_name: 'Estándar' },
        label: p.name, sku: p.sku, barcode: p.barcode ?? null, qty: Number(p.stock_total ?? 0),
      })
      continue
    }
    for (const v of vs) {
      const conNombre = vs.length > 1 && v.variant_name && v.variant_name !== 'Estándar'
      rows.push({
        product: p, variant: v,
        label: conNombre ? `${p.name} · ${v.variant_name}` : p.name,
        sku: v.sku, barcode: v.barcode ?? null, qty: Number(v.stock_total ?? 0),
      })
    }
  }
  return rows
}
```

Aplicar en cada pantalla:
- `Inventory.tsx` y `HQInventory.tsx`: sustituir `const variantId = (p: Product) => p.variants?.[0]?.id ?? p.id` por el mapeo a renglones (`const rows = expandVariantRows(products)`) y renderizar `rows` en vez de `products`: etiqueta `row.label`, existencia `row.qty`, kardex y ajuste con `row.variant.id`.
- `ProductsBranchView.tsx`: `firstVariantId` desaparece; la tabla se construye con `expandVariantRows` y cada fila lleva `variant_id = row.variant.id`.
- `Products.tsx`: `pickVariantId` se mantiene para el editor de PBS de la fila principal, pero la columna Stock muestra `row.qty` y, si `variants.length > 1`, un subtexto "N variantes".
- `ProductBranchMatrix.tsx`: donde se manda `variant_ids: [variant.id]`, mandar `variant_ids: (product.variants ?? []).map((v) => v.id)`; el `branch_status` que se lee sigue siendo el de la principal (todas las variantes comparten activación al crearse).
- `ProductDetailModal.tsx:300`: si `product.variants.length > 1`, un `<select>` de variantes sobre el bloque de ajuste de stock; `primaryVariantId` pasa a ser el seleccionado (por omisión `matched_variant_id ?? variants[0].id`).

- [ ] **Step 4: Verificar y commit**

Run: `cd frontend && npx vitest run && npx tsc --noEmit && npm run build`

```bash
git add frontend/src/pages/inventory frontend/src/pages/hq/HQInventory.tsx frontend/src/components/branch/ProductsBranchView.tsx frontend/src/components/catalog/ProductBranchMatrix.tsx frontend/src/components/pos/modals/ProductDetailModal.tsx
git commit -m "feat(inventario): un renglon por variante en kardex, ajustes y matriz de sucursales"
```

---

### Task 14: Asignar un código escaneado a una talla concreta

**Files:**
- Modify: `frontend/src/pages/scanner/StoreScanner.tsx:305-360` (`AttachCodePanel`)

**Interfaces:**
- Consumes: `productsApi.updateVariant` (Task 9), `groupVariants` (Task 12).

- [ ] **Step 1: Implementar**

En `AttachCodePanel`, al elegir un producto de `hits`:
- Si `(p.variants?.length ?? 0) <= 1`: comportamiento actual (`buildDetailsUpdatePayload` con `barcode`).
- Si tiene varias: mostrar chips con `variant_name` (o SKU) de cada variante **sin código**; al tocar una, `productsApi.updateVariant(v.id, { barcode: code })` y `onAttached({ ...updated, matched_variant_id: v.id })`.

```tsx
  const [pendingProduct, setPendingProduct] = useState<Product | null>(null)

  const attach = async (p: Product) => {
    if ((p.variants?.length ?? 0) > 1) { setPendingProduct(p); return }
    // ... flujo actual ...
  }

  const attachToVariant = async (p: Product, variantId: string) => {
    setBusy(true); setMsg(null)
    try {
      const updated = await productsApi.updateVariant(variantId, { barcode: code })
      onAttached({ ...updated, matched_variant_id: variantId })
    } catch (err) {
      const e = err as { response?: { data?: { detail?: unknown } } }
      setMsg(errorDetailText(e?.response?.data?.detail, 'No se pudo asignar el código a esa variante.'))
    } finally { setBusy(false) }
  }
```

y en el JSX, cuando `pendingProduct`:

```tsx
        {pendingProduct && (
          <div className="space-y-2">
            <p className="text-xs text-slate-400">¿A qué variante de {pendingProduct.name} pertenece este código?</p>
            <div className="flex flex-wrap gap-2">
              {(pendingProduct.variants ?? []).filter((v) => !v.barcode).map((v) => (
                <button key={v.id} disabled={busy} className="dax-btn-secondary" onClick={() => attachToVariant(pendingProduct, v.id)}>
                  {v.variant_name ?? v.sku}
                </button>
              ))}
            </div>
          </div>
        )}
```

- [ ] **Step 2: Verificar y commit**

Run: `cd frontend && npx tsc --noEmit && npm run build`

```bash
git add frontend/src/pages/scanner/StoreScanner.tsx
git commit -m "feat(scanner): asignar un codigo escaneado a la talla correcta"
```

**Hito de fase 3:** desplegar. Operación completa en Eleven: vender por talla, contar por talla, pegar códigos por talla.

---

## Fase 4 — Trazabilidad y carga masiva

### Task 15: La variante aparece en el ticket de devolución y en los reportes de existencia

**Files:**
- Modify: `app/pos_printer.py:176-180`
- Modify: `app/routers/reports.py:402-415, 845-857, 1050-1062`
- Test: `tests/test_variant_traceability.py`

**Interfaces:**
- Produces: línea de devolución `DEVUELTO 1x Playera (Rojo / M)`; en los reportes de stock bajo/crítico el campo `product_name` trae `"Playera (Rojo / M)"` cuando la variante no es "Estándar".

- [ ] **Step 1: Prueba que falla**

```python
# tests/test_variant_traceability.py
"""La talla debe verse donde hoy solo se ve el producto: ticket de devolucion
y reportes de existencia."""
from decimal import Decimal

from app.models.products import ProductVariant
from app.pos_printer import _describe_variant


def test_describe_variant_agrega_la_talla():
    v = ProductVariant(sku="PLY-M", variant_name="Rojo / M")
    v.product = type("P", (), {"name": "Playera"})()
    assert _describe_variant(v) == "Playera (Rojo / M)"


def test_describe_variant_omite_estandar():
    v = ProductVariant(sku="GOR", variant_name="Estándar")
    v.product = type("P", (), {"name": "Gorra"})()
    assert _describe_variant(v) == "Gorra"
```

Y una prueba de reporte: con el fixture `playera` de `tests/test_variant_read.py` pero `qty_on_hand = 2` para la talla M, `GET /api/reports/dashboard` (bloque "Alertas de Inventario", `app/routers/reports.py:400-416`, umbral `<= 5`) debe listar la alerta con `name == "Playera (Rojo / M)"`. Las otras dos consultas viven en `GET /api/reports/command-center/stats` (`:845-857`) y `GET /api/reports/export/csv` (`:1050-1062`).

- [ ] **Step 2: Implementar**

`app/pos_printer.py`, helper a nivel módulo y uso en la línea de devolución:

```python
def _describe_variant(variant) -> str:
    """"Playera (Rojo / M)" o solo el nombre del producto para la variante estandar."""
    nombre = variant.product.name if variant is not None and variant.product else "Producto"
    etiqueta = (variant.variant_name or "").strip() if variant is not None else ""
    if etiqueta and etiqueta != "Estándar":
        return f"{nombre} ({etiqueta})"
    return nombre
```

```python
                    p_name = _describe_variant(item.variant) if item.variant else "Producto"
```

`app/routers/reports.py`: en las tres consultas de stock bajo/crítico (`:402-415`, `:845-857`, `:1050-1062`), agregar `ProductVariant.variant_name` al `db.query(...)` y armar el nombre con `_describe_name(name, variant_name)`:

```python
def _describe_name(name: str, variant_name: Optional[str]) -> str:
    etiqueta = (variant_name or "").strip()
    return f"{name} ({etiqueta})" if etiqueta and etiqueta != "Estándar" else name
```

En el bloque de la línea 402 el diccionario de salida usa `"name": _describe_name(row.name, row.variant_name)` en vez de `row.name`; igual en los otros dos.

- [ ] **Step 3: Verificar y commit**

Run: `python3 -m pytest -q -p no:warnings tests/test_variant_traceability.py tests/test_pos_printer.py`

```bash
git add app/pos_printer.py app/routers/reports.py tests/test_variant_traceability.py
git commit -m "feat(variants): la talla se ve en el ticket de devolucion y en reportes de existencia"
```

---

### Task 16: Importador y exportador con color y talla

**Files:**
- Modify: `scripts/import_products.py:140-215`
- Modify: `app/modules/products/router/import_export.py:110-135` (export) y `:426-452` (upload)
- Test: `tests/test_import_products_variantes.py`

**Interfaces:**
- Consumes: `variant_label`, `clean_attr` (Task 2).
- Produces: columnas opcionales `Color` y `Talla` en el CSV/Excel. Filas con el mismo `Nombre*` (y misma categoría) y distinta pareja color/talla se agrupan en un producto con N variantes; la primera fila es la principal. Cada fila conserva su propio código, precio, costo y stock. Sin las columnas, comportamiento idéntico al actual. El export escribe `Color` y `Talla` y una fila por variante.

- [ ] **Step 1: Prueba que falla**

```python
# tests/test_import_products_variantes.py
"""Un CSV con Color/Talla agrupa filas del mismo nombre en un producto con N
variantes; sin esas columnas, importa como siempre (una fila = un producto)."""
import csv
import importlib

from app.models.inventory import StockOnHand
from app.models.products import Product, ProductVariant

imp = importlib.import_module("scripts.import_products")

CABECERAS = ["Nombre*", "Categoría", "Código", "Descripción", "Costo unitario", "Precio*",
             "Mostrar en el catálogo", "Controlar stock", "Stock actual", "Stock mínimo", "Color", "Talla"]


def _csv(tmp_path, filas):
    ruta = tmp_path / "ropa.csv"
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CABECERAS)
        w.writeheader()
        for f in filas:
            w.writerow({**{c: "" for c in CABECERAS}, **f})
    return str(ruta)


BASE = {"Nombre*": "Playera lisa", "Categoría": "Playeras", "Costo unitario": "60", "Precio*": "120",
        "Mostrar en el catálogo": "S", "Controlar stock": "S", "Stock mínimo": "1"}


def test_agrupa_por_nombre_en_un_producto_con_variantes(db, org, branch_a, tmp_path):
    filas = [
        {**BASE, "Código": "PLY-R-S", "Color": "Rojo", "Talla": "S", "Stock actual": "3"},
        {**BASE, "Código": "PLY-R-M", "Color": "Rojo", "Talla": "M", "Stock actual": "5"},
        {**BASE, "Código": "PLY-N-M", "Color": "Negro", "Talla": "M", "Stock actual": "0", "Precio*": "130"},
    ]
    r = imp.import_products(db, _csv(tmp_path, filas), org.id, branch_a.id)
    assert r["creados"] == 1 and r.get("variantes_creadas") == 3
    p = db.query(Product).filter(Product.organization_id == org.id, Product.name == "Playera lisa").one()
    vs = {v.sku: v for v in db.query(ProductVariant).filter(ProductVariant.product_id == p.id).all()}
    assert set(vs) == {"PLY-R-S", "PLY-R-M", "PLY-N-M"}
    assert vs["PLY-R-M"].variant_name == "Rojo / M"
    assert vs["PLY-N-M"].price == 130
    stock = {v.sku: db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).one().qty_on_hand for v in vs.values()}
    assert stock["PLY-R-M"] == 5 and stock["PLY-N-M"] == 0


def test_sin_columnas_de_variante_importa_como_antes(db, org, branch_a, tmp_path):
    filas = [{**BASE, "Código": "GOR-1", "Nombre*": "Gorra"}, {**BASE, "Código": "GOR-2", "Nombre*": "Gorra"}]
    r = imp.import_products(db, _csv(tmp_path, filas), org.id, branch_a.id)
    # Mismo nombre SIN color/talla = dos productos, como hoy.
    assert r["creados"] == 2


def test_pareja_repetida_se_reporta_y_omite(db, org, branch_a, tmp_path):
    filas = [
        {**BASE, "Código": "PLY-1", "Color": "Rojo", "Talla": "S"},
        {**BASE, "Código": "PLY-2", "Color": "rojo", "Talla": "s"},
    ]
    r = imp.import_products(db, _csv(tmp_path, filas), org.id, branch_a.id)
    assert r["creados"] == 1 and r["omitidos"] == 1
    assert any("Rojo / S" in x for x in r["incidencias"])
```

- [ ] **Step 2: Implementar en `scripts/import_products.py`**

Dentro del bucle de filas, después de resolver `nombre`, `precio`, `costo`, `sku` y `dep`:

```python
        color = _limpiar_attr(f.get("color"), 60, nfila)
        talla = _limpiar_attr(f.get("talla"), 30, nfila)
        con_variante = bool(color or talla)
        clave_padre = (nombre.lower(), (dep.id if dep is not None else None))

        if con_variante and clave_padre in padres:
            producto = padres[clave_padre]
            pareja = ((color or "").lower(), (talla or "").lower())
            if pareja in parejas[clave_padre]:
                resumen["omitidos"] += 1
                resumen["incidencias"].append(
                    f"fila {nfila}: '{nombre}' ya tiene la variante {variant_label(color, talla)}; se omite"
                )
                continue
            parejas[clave_padre].add(pareja)
        else:
            producto = Product(
                name=nombre,
                description=(f.get("descripcion") or "").strip() or None,
                organization_id=org_id,
                department_id=dep.id if dep is not None else None,
                is_active=True,
                has_variants=con_variante,
            )
            db.add(producto)
            db.flush()
            resumen["creados"] += 1
            if con_variante:
                padres[clave_padre] = producto
                parejas[clave_padre] = {((color or "").lower(), (talla or "").lower())}

        variante = ProductVariant(
            product_id=producto.id,
            sku=sku,
            color=color,
            size=talla,
            variant_name=variant_label(color, talla),
            price=precio,
            cost=costo,
            organization_id=org_id,
        )
        db.add(variante)
        db.flush()
        if con_variante:
            resumen["variantes_creadas"] = resumen.get("variantes_creadas", 0) + 1
```

con los diccionarios `padres: dict = {}` y `parejas: dict = {}` inicializados antes del bucle, `from app.modules.products.variant_label import clean_attr, variant_label` en los imports, y el helper:

```python
def _limpiar_attr(valor, maximo, nfila):
    try:
        return clean_attr(valor, maximo)
    except ValueError as e:
        raise SystemExit(f"fila {nfila}: color/talla {e}")
```

Ajustar el conteo `resumen["creados"]` para que ya no se incremente en el sitio anterior (ahora se hace al crear el `Product`). El lector `_leer` debe mapear las cabeceras `Color` → `color` y `Talla` → `talla` como hace con las demás.

- [ ] **Step 3: Implementar en `import_export.py`**

- Export (`:110-135`): iterar `for v in p.variants` y escribir una fila por variante con las columnas actuales más `Color` y `Talla` (`v.color or ""`, `v.size or ""`).
- Upload (`:426-452`): leer `Color`/`Talla` con los coercers de `_shared.py`; si vienen y ya existe un `Product` con el mismo nombre en la org creado en esta misma carga (diccionario en memoria como en el script), agregar la variante con `crear_variantes` (Task 8) en vez de crear otro producto.

- [ ] **Step 4: Verificar y commit**

Run: `python3 -m pytest -q -p no:warnings tests/test_import_products_variantes.py tests/test_import_products.py`

```bash
git add scripts/import_products.py app/modules/products/router/import_export.py tests/test_import_products_variantes.py
git commit -m "feat(variants): importar y exportar catalogo con color y talla"
```

**Hito de fase 4:** desplegar. Cierre del proyecto; una semana de observación en Eleven antes de ofrecer el preset a otra boutique.

---

## Despliegue de cada fase

1. Suite backend y frontend en verde (ver Global Constraints).
2. Fusionar la rama a `main` **con permiso del usuario**; el push a `main` redespliega Railway (Kaory).
3. VPS: `git archive --format=tar HEAD | ssh ionos 'tar -x -C /srv/apps/atlas-one-prod/src'` y `ssh ionos 'cd /srv/apps/atlas-one-prod && docker compose build && docker compose up -d'`. `railway_init` aplica los `ALTER` y siembra el módulo `variants` al arrancar.
4. Activar `variants` en Eleven: ya viene en `ATLAS_POS_BOUTIQUE`; volver a aplicar el preset a la organización 17 (`apply_industry_preset`) o activar el módulo desde el panel de plataforma.
5. Verificar con la sesión de `eleven`: `GET /api/org/capabilities/` incluye `variants`; escanear un código de talla en el Scanner muestra la etiqueta; una venta de prueba descuenta la talla correcta (cancelarla después).

## Auto-revisión del plan

- **Cobertura del diseño:** decisiones 1 (Task 1, 10, 12), 2 (Task 3, 4), 3 (Task 2), 4 (Task 5, 6), 5 (Task 4, 12), 6 (Task 8), 7 (Task 2), 8 (Task 16). Alcance "dentro" completo: ticket de devolución y reportes (Task 15), inventario por variante (Task 13), Scanner (Task 7, 14).
- **Consistencia de nombres:** `matched_variant_id` (Task 3, 4, 6, 7, 12, 14); `stock_total` en `ProductVariantRead` y en el tipo TS (Task 3, 6, 7, 12, 13); `variant_label`/`clean_attr` (Task 2, 8, 16); `crear_variantes` (Task 8, 16); `buildVariantRows`/`toExtraVariants`/`VariantRow` (Task 9, 10, 11); `needsPicker`/`pickVariantForCart`/`groupVariants` (Task 12, 14); `expandVariantRows` (Task 13).
- **Fuera de alcance explícito:** precio por talla en la UI de alta (el endpoint lo permite), fotos por variante, atributos adicionales, cajas en productos con variantes.
