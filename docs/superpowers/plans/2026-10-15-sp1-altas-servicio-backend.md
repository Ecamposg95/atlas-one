# SP1 · Altas: servicio único de productos (backend) — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que crear, editar, duplicar, importar y crear variantes de producto pasen por **un** paquete de servicio (`app/modules/products/services/`) con las mismas validaciones y helpers compartidos, cerrando con prueba los bugs conocidos (duplicate sin color/talla ni código, update con 400 en SKU repetido, upload con precio 0, commits tragados, `print()`, sin guard de rol) sin cambiar la respuesta JSON de ningún endpoint.

**Architecture:** Hoy toda la lógica vive en cuatro handlers (`create_product` 356 líneas, `update_product` 240, `duplicate_product` 135, `upload_products` 547) que repiten unicidad de SKU, estado por sucursal, stock inicial, empaques y escalones con pequeñas diferencias entre sí. El plan extrae helpers puros primero (SKU/código, validaciones, sucursales/stock, empaques/escalones), luego migra **handler por handler** en el orden create → variantes → duplicate → update → upload, dejando cada handler en menos de 40 líneas (parsear, llamar al servicio, confirmar, serializar). Los servicios reciben la sesión, hacen `flush` y **nunca `commit`** (el handler confirma; el importador envuelve cada fila en un SAVEPOINT), y levantan `HTTPException` con el mismo `detail` que usaban los handlers — precedente del repo: `app/modules/kitchen/services.py`, `app/modules/appointments/services.py`.

**Por qué un paquete `services/` y no un `services.py`:** la spec nombra `services.py`, pero el cuerpo real de los cuatro handlers suma ~1,300 líneas; en un solo archivo quedaría más grande que el `core.py` que se quiere partir. El repo ya tiene el precedente de paquete en `app/services/labels/` (`__init__.py` que re-exporta). Se divide por responsabilidad: `codigos.py` (SKU y código de barras), `validaciones.py`, `sucursales.py` (estado por sucursal y existencias), `precios.py` (empaques y escalones), `variantes.py`, `productos.py` (crear/actualizar/duplicar) e `importacion.py` (fila del upload). `services/__init__.py` re-exporta la API pública, así que `from app.modules.products.services import crear_producto` funciona igual que si fuera un módulo.

**Regla de imports (evita un ciclo real):** `app/modules/products/router/__init__.py` importa `core`, `core` importa `services`. Si un servicio importara `router._shared`, importar `services` desde una prueba reventaría con `ImportError` a medio ciclo. Por eso los dos helpers de variantes vivas, los dos conjuntos de roles y los tres coercers de celdas se mudan a `services/comun.py` y `router/_shared.py` los **re-exporta con sus nombres históricos**. Los servicios nunca importan nada de `app/modules/products/router/`.

**Tech Stack:** FastAPI 0.127 + SQLAlchemy 2.0.45 + Pydantic 2.12; pytest sobre SQLite (`python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py`; si existe `.venv/`, usa `.venv/bin/python`). Sin cambios de frontend ni de esquema.

**Spec:** `docs/superpowers/specs/2026-10-14-mega-plan-altas-docs-responsivo-agente-design.md` (sección "SP1 · Altas"; hallazgos en §2.1; decisiones §3 y §6.3–6.4).

## Global Constraints

- **`main` = producción con clientes vivos.** Trabaja en `feat/altas-servicio-backend` (créala desde `main` al empezar: `git checkout main && git pull && git checkout -b feat/altas-servicio-backend`). Commits locales sí; **push y merge solo con permiso explícito del usuario** (CLAUDE.md regla de oro #1 y #2).
- **Sin migración de esquema.** No hay columnas ni tablas nuevas; `scripts/railway_init.py` no se toca. (`event_outbox` ya existe para la tarea opcional 11.)
- **La respuesta JSON de cada endpoint NO cambia.** `POST /api/products/`, `PUT /api/products/{id}`, `POST /api/products/{id}/duplicate` y `POST /api/products/{id}/variants` siguen devolviendo `ProductRead` por `_compute_product_read`; `POST /api/products/upload` sigue devolviendo `{"created","updated","failed","pending","details"}` y en `dry_run` `{"total_rows","to_create","to_update","errors","preview","error_details"}`.
- **Schemas públicos sin cambios.** No se agrega ningún campo a `ProductCreate`/`ProductUpdate`/`ProductVariantCreate`. El upload acepta una columna **opcional** nueva, `Tasa IVA` (0–100, default 16); el export no la emite (su orden de columnas tiene prueba).
- **Decisiones tomadas (no se vuelven a abrir):** (a) SKU único por organización **sin distinguir mayúsculas ni espacios en los extremos** e **incluyendo productos y variantes archivados** (soft-delete) — 409 en alta, edición, duplicado, variantes e importación; mensaje vivo exacto `"El SKU '{sku}' ya existe en esta organización."`, y si el choque es con uno archivado se agrega ` (está en un producto archivado: restáuralo o usa otro SKU)`. (b) Usuario sin sucursal y sin `target_branch_ids` → estado por sucursal en **todas** las sucursales con `is_active = true AND can_sell = true`; si la org no tiene ninguna que venda, se crea sin PBS (catálogo global, como hoy).
- **Códigos HTTP unificados:** 409 SKU/código de barras repetido (update deja de responder 400 en SKU repetido); 422 validaciones de datos, sucursal ajena (update deja de responder 400 `"Sucursal {id} no encontrada"` y usa el mismo 422 que el alta: `"Una o más sucursales objetivo no pertenecen a tu organización."`); 403 rol o módulo. Los textos de 4xx existentes se copian tal cual (están en cada tarea).
- **`require_module("catalog")`** en create, update, duplicate y upload (variantes ya lo tiene). `require_module` **exime a ADMINISTRADOR/DUEÑO**; a CAJERO/GERENTE les exige `organization_modules.catalog` encendido. Antes de desplegar el Paso 1 se corre la consulta de verificación de la sección "Despliegue" para que ninguna tienda viva pierda el alta desde caja.
- **Servicios:** `flush` sí, `commit` nunca; `HTTPException` para errores de negocio; nada de `print()`; comentarios en español; `from __future__ import annotations`; type hints en firmas nuevas. Los servicios **no importan de `app/modules/products/router/`**.
- **Handlers:** menos de 40 líneas contando decorador y firma (hay una prueba por handler que lo mide con `inspect.getsource`).
- **Pruebas:** las ~200 existentes de productos (`tests/test_product*.py`, `tests/test_variant*.py`, `tests/test_barcodes.py`, `tests/test_import_export_variantes.py`, `tests/test_admin_catalog_*.py`, `tests/test_sale_name.py`, `tests/test_tier_price_guard.py`, `tests/test_regresion_productos.py`, `tests/test_precio_a_todas_las_tallas.py`, `tests/test_variante_principal_viva.py`) siguen verdes. Nunca dos `pytest` a la vez en el mismo worktree (la "DB en memoria" es un archivo real). Suite completa siempre con `--ignore=tests/test_cash_complete.py`.
- **Commits** con scope `feat(productos):`/`refactor(productos):`/`fix(productos):`/`test(productos):` y terminan con:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
  ```

## Review Focus

1. **SKU que solo difiere en mayúsculas o espacios** (`" ply-1 "` contra `PLY-1` vivo) en alta, edición, variante hermana e importación: 409 siempre; en la importación la fila **actualiza** la variante existente en vez de intentar crear otra. → Tareas 1, 5, 6, 8, 9.
2. **SKU de un producto archivado** reutilizado desde el alta o desde el archivo: 409 con el sufijo "archivado" (una fila de upload lo reporta como fallida con ese texto), nunca un segundo producto que choque al restaurar. → Tareas 1, 5, 9.
3. **Usuario sin sucursal, sin destinos, con `initial_stock > 0` y dos sucursales que venden:** 422 pidiendo la sucursal (`branch_id`), no reparte ni elige la primera en silencio; con `branch_id` la existencia cae exactamente ahí. → Tarea 5.
4. **Fila de upload con precio en blanco o `0` sobre un SKU existente:** fila fallida y el precio anterior intacto (hoy se escribe `$0` y el POS lo vende regalado); y una **falla de commit** del lote responde 500 con `detail`, no 200 con `created > 0`. → Tarea 10.
5. **CAJERO/GERENTE de una organización sin `organization_modules.catalog`:** 403 con el nombre del módulo en `detail` (es el riesgo real del despliegue: la consulta previa de la sección "Despliegue" lo descarta en producción). → Tareas 5, 7, 9.

---

## Estructura de archivos

**Crear**
- `app/modules/products/services/__init__.py` — re-exporta la API pública.
- `app/modules/products/services/comun.py` — roles, `variantes_vivas`, `variante_principal`, coercers de celdas.
- `app/modules/products/services/codigos.py` — `sku_en_uso`, `validar_sku_unico`, `sku_de_copia`, `validar_barcode_libre`, `asignar_barcode_interno`.
- `app/modules/products/services/validaciones.py` — `exigir_campos_de_cajero`, `validar_precio`, `validar_escalones`, `validar_sucursales_de_la_org`, `validar_departamento_y_marca`, `atributos_principal`.
- `app/modules/products/services/sucursales.py` — `sucursales_que_venden`, `resolver_sucursales_destino`, `sucursal_de_existencia_inicial`, `armar_estado_por_sucursal`, `copiar_estado_por_sucursal`, `registrar_stock_inicial`, `fijar_existencia`.
- `app/modules/products/services/precios.py` — `armar_empaques`, `armar_escalones`.
- `app/modules/products/services/variantes.py` — `crear_variantes` (mudada desde el router), `sku_generado`, `pareja_repetida`, `atributos`.
- `app/modules/products/services/productos.py` — `crear_producto`, `actualizar_producto`, `duplicar_producto`.
- `app/modules/products/services/importacion.py` — `ContextoImportacion`, `ResultadoFila`, `FilaInvalida`, `importar_fila`.
- Pruebas nuevas: `tests/test_productos_servicio_codigos.py`, `tests/test_productos_servicio_validaciones.py`, `tests/test_productos_servicio_sucursales.py`, `tests/test_productos_servicio_precios.py`, `tests/test_altas_crear_producto.py`, `tests/test_altas_variantes_servicio.py`, `tests/test_altas_duplicar.py`, `tests/test_altas_actualizar.py`, `tests/test_altas_upload.py`, `tests/test_altas_evento.py` (opcional).

**Modificar**
- `app/modules/products/router/_shared.py` — re-exporta desde `services/comun.py`.
- `app/modules/products/router/core.py` — `create_product`, `duplicate_product`, `update_product` quedan delgados; `require_module("catalog")`.
- `app/modules/products/router/variants.py` — importa `crear_variantes` y helpers desde `services/variantes.py` (re-exporta los nombres privados que usa `import_export.py`).
- `app/modules/products/router/import_export.py` — `upload_products` delgado + helpers privados de parseo; `require_module("catalog")`; guard de rol; sin `print()`.
- `app/core/events.py` — `ProductCreated` (tarea opcional 11).
- `tests/conftest.py` — fixtures `catalog_module_enabled`, `admin_sin_sucursal`, `auth_admin_sin_sucursal`.
- `tests/test_product_creation.py`, `tests/test_admin_catalog_regression.py` — se quita la copia local de `catalog_module_enabled` (ahora en conftest); `tests/test_admin_catalog_advanced.py::TestDuplicateProduct::test_cajero_allowed` pide `catalog_module_enabled`.

---

### Task 1: `services/codigos.py` — una sola regla de SKU y de código interno

**Files:**
- Create: `app/modules/products/services/__init__.py`
- Create: `app/modules/products/services/codigos.py`
- Test: `tests/test_productos_servicio_codigos.py`

**Interfaces:**
- Consumes: `Product`, `ProductVariant` (`app.models`); `AsignadorDeCodigos`, `barcode_en_uso`, `siguiente_codigo_interno` (`app.services.barcodes`).
- Produces (las usan las tareas 5–10):
  - `sku_en_uso(db, org_id: int, sku: str, excepto_id: Optional[str] = None) -> bool` — case-insensitive, **incluye archivados**.
  - `validar_sku_unico(db, org_id: int, sku: str, excepto_id: Optional[str] = None) -> str` — devuelve el SKU recortado; 422 si vacío; 409 si existe (sufijo "archivado" cuando aplica).
  - `sku_de_copia(db, org_id: int, base_sku: str) -> str` — `<base>-COPY-<n>` libre (n = 1..99), fallback con 6 hex.
  - `validar_barcode_libre(db, org_id: int, barcode: Optional[str], excepto_id: Optional[str] = None) -> Optional[str]` — devuelve el código recortado o `None`; 409 si lo tiene otra variante viva.
  - `asignar_barcode_interno(db, org_id: int, variante: ProductVariant, asignador: Optional[AsignadorDeCodigos] = None) -> str` — asigna EAN-13 interno **solo si está vacío**, hace `flush`, devuelve el código final.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_productos_servicio_codigos.py`:

```python
"""Unicidad de SKU y código interno: una sola regla para todas las altas.

Decisión del mega plan 2026-10 (§6.3): el SKU se compara sin mayúsculas y
cuenta también los productos archivados, para que restaurar nunca choque.
"""
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from conftest import _make_product
from app.models.organization import Organization
from app.modules.products.services.codigos import (
    asignar_barcode_interno, sku_de_copia, sku_en_uso, validar_barcode_libre,
    validar_sku_unico,
)
from app.services.barcodes import es_codigo_interno


def _archivar(db, producto, variante):
    ahora = datetime.now(timezone.utc)
    producto.deleted_at = ahora
    producto.is_active = False
    variante.deleted_at = ahora
    db.flush()


class TestValidarSkuUnico:
    def test_distinto_solo_en_mayusculas_o_espacios_es_409(self, db, org, branch_a):
        _make_product(db, org, "Playera", "PLY-1", 100, [(branch_a.id, True)])
        for repetido in ("ply-1", " PLY-1 ", "Ply-1"):
            with pytest.raises(HTTPException) as exc:
                validar_sku_unico(db, org.id, repetido)
            assert exc.value.status_code == 409
            assert exc.value.detail == f"El SKU '{repetido.strip()}' ya existe en esta organización."

    def test_sku_de_producto_archivado_tambien_es_409_y_lo_dice(self, db, org, branch_a):
        p, v = _make_product(db, org, "Vieja", "ARCH-1", 100, [(branch_a.id, True)])
        _archivar(db, p, v)
        with pytest.raises(HTTPException) as exc:
            validar_sku_unico(db, org.id, "arch-1")
        assert exc.value.status_code == 409
        assert "archivado" in exc.value.detail
        assert sku_en_uso(db, org.id, "ARCH-1") is True

    def test_el_mismo_sku_en_otra_org_no_estorba(self, db, org):
        otra = Organization(name="Otra", status="ACTIVE")
        db.add(otra); db.flush()
        _make_product(db, otra, "Ajena", "OTRA-1", 10)
        assert validar_sku_unico(db, org.id, "OTRA-1") == "OTRA-1"
        assert sku_en_uso(db, org.id, "OTRA-1") is False

    def test_excepto_id_permite_conservar_el_propio(self, db, org, branch_a):
        _, v = _make_product(db, org, "Playera", "PLY-2", 100, [(branch_a.id, True)])
        assert validar_sku_unico(db, org.id, "ply-2", excepto_id=v.id) == "ply-2"

    def test_vacio_es_422_y_devuelve_recortado(self, db, org):
        with pytest.raises(HTTPException) as exc:
            validar_sku_unico(db, org.id, "   ")
        assert exc.value.status_code == 422
        assert validar_sku_unico(db, org.id, "  NUEVO-1 ") == "NUEVO-1"


class TestSkuDeCopia:
    def test_salta_sufijos_ocupados_incluso_archivados(self, db, org, branch_a):
        _make_product(db, org, "Base", "SKU-A", 100, [(branch_a.id, True)])
        p1, v1 = _make_product(db, org, "Copia vieja", "SKU-A-COPY-1", 100, [(branch_a.id, True)])
        _archivar(db, p1, v1)
        assert sku_de_copia(db, org.id, "SKU-A") == "SKU-A-COPY-2"

    def test_sin_base_usa_SKU(self, db, org):
        assert sku_de_copia(db, org.id, "") == "SKU-COPY-1"


class TestBarcode:
    def test_asigna_interno_solo_si_esta_vacio(self, db, org, branch_a):
        _, con = _make_product(db, org, "Con", "BC-1", 10, [(branch_a.id, True)])
        con.barcode = "7500000000011"
        _, sin = _make_product(db, org, "Sin", "BC-2", 10, [(branch_a.id, True)])
        db.flush()
        assert asignar_barcode_interno(db, org.id, con) == "7500000000011"
        nuevo = asignar_barcode_interno(db, org.id, sin)
        assert es_codigo_interno(org.id, nuevo)
        assert sin.barcode == nuevo

    def test_barcode_libre_recorta_y_409_si_lo_tiene_otra(self, db, org, branch_a):
        _, otra = _make_product(db, org, "Otra", "BC-3", 10, [(branch_a.id, True)])
        otra.barcode = "7500000000022"
        db.flush()
        assert validar_barcode_libre(db, org.id, "  ") is None
        assert validar_barcode_libre(db, org.id, " 7500000000033 ") == "7500000000033"
        assert validar_barcode_libre(db, org.id, "7500000000022", excepto_id=otra.id) == "7500000000022"
        with pytest.raises(HTTPException) as exc:
            validar_barcode_libre(db, org.id, "7500000000022")
        assert exc.value.status_code == 409
        assert exc.value.detail == "El código de barras '7500000000022' ya lo tiene otra variante."
```

- [ ] **Step 2: Correr para ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_productos_servicio_codigos.py`
Expected: FAIL en la colección con `ModuleNotFoundError: No module named 'app.modules.products.services'`.

- [ ] **Step 3: Crear el paquete y `codigos.py`**

`app/modules/products/services/__init__.py` (se irá llenando en cada tarea; por ahora solo esto):

```python
"""Capa de servicio del catálogo de productos (SP1 · Altas, 2026-10).

Un solo lugar para crear, editar, duplicar, importar y crear variantes. Los
servicios hacen `flush`, nunca `commit` (lo hace el handler o el SAVEPOINT del
importador) y levantan `HTTPException` con el mismo `detail` que usaban los
handlers. Nada de aquí importa de `app/modules/products/router/`.
"""
from .codigos import (  # noqa: F401
    asignar_barcode_interno, sku_de_copia, sku_en_uso, validar_barcode_libre,
    validar_sku_unico,
)
```

`app/modules/products/services/codigos.py`:

```python
"""SKU y código de barras: unicidad por organización y código interno.

Una sola regla de SKU para alta, edición, duplicado, variantes e importación:
se compara SIN distinguir mayúsculas y cuenta también los productos archivados
(soft-delete), para que restaurar un producto nunca choque con uno creado
después con el mismo SKU (mega plan 2026-10, §6.3). Antes había cuatro
consultas distintas: exacta (alta, upload), exacta con 400 (edición) y sin
mayúsculas pero solo vivas (variantes).

Toda consulta hace `join(Product)` y filtra `Product.organization_id`: las
filas viejas de `product_variants` pueden traer `organization_id` NULL.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Product, ProductVariant
from app.services.barcodes import AsignadorDeCodigos, barcode_en_uso, siguiente_codigo_interno


def _variante_con_sku(db: Session, org_id: int, sku: str, excepto_id: Optional[str] = None):
    """Primera variante de la org (viva o archivada) con ese SKU, o None."""
    q = (
        db.query(
            ProductVariant.id.label("id"),
            ProductVariant.deleted_at.label("variante_borrada"),
            Product.deleted_at.label("producto_borrado"),
        )
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            Product.organization_id == org_id,
            func.lower(ProductVariant.sku) == sku.strip().lower(),
        )
    )
    if excepto_id:
        q = q.filter(ProductVariant.id != excepto_id)
    return q.first()


def sku_en_uso(db: Session, org_id: int, sku: str, excepto_id: Optional[str] = None) -> bool:
    """¿Alguna variante de la org (viva o archivada) ya usa este SKU?"""
    return _variante_con_sku(db, org_id, sku, excepto_id) is not None


def validar_sku_unico(db: Session, org_id: int, sku: str, excepto_id: Optional[str] = None) -> str:
    """Devuelve el SKU recortado o levanta 422 (vacío) / 409 (repetido).

    El mensaje vivo es exactamente el que ya mostraba el alta; cuando el choque
    es con un producto archivado se agrega qué hacer, porque desde la pantalla
    ese producto no se ve y el usuario no entiende "ya existe".
    """
    limpio = (sku or "").strip()
    if not limpio:
        raise HTTPException(status_code=422, detail="El SKU no puede quedar vacío")
    fila = _variante_con_sku(db, org_id, limpio, excepto_id)
    if fila is None:
        return limpio
    archivado = fila.variante_borrada is not None or fila.producto_borrado is not None
    sufijo = " (está en un producto archivado: restáuralo o usa otro SKU)" if archivado else ""
    raise HTTPException(
        status_code=409,
        detail=f"El SKU '{limpio}' ya existe en esta organización.{sufijo}",
    )


def sku_de_copia(db: Session, org_id: int, base_sku: str) -> str:
    """`<base>-COPY-<n>` con el primer `n` libre en la org (archivados incluidos)."""
    base = (base_sku or "").strip() or "SKU"
    for n in range(1, 100):
        candidato = f"{base}-COPY-{n}"
        if not sku_en_uso(db, org_id, candidato):
            return candidato
    return f"{base}-COPY-{uuid.uuid4().hex[:6]}"


def validar_barcode_libre(
    db: Session, org_id: int, barcode: Optional[str], excepto_id: Optional[str] = None,
) -> Optional[str]:
    """Código recortado (o None si viene vacío); 409 si ya lo tiene otra variante viva."""
    limpio = (barcode or "").strip() or None
    if limpio and barcode_en_uso(db, org_id, limpio, excepto_id=excepto_id):
        raise HTTPException(
            status_code=409,
            detail=f"El código de barras '{limpio}' ya lo tiene otra variante.",
        )
    return limpio


def asignar_barcode_interno(
    db: Session, org_id: int, variante: ProductVariant,
    asignador: Optional[AsignadorDeCodigos] = None,
) -> str:
    """Si la variante no trae código, le genera el EAN-13 interno de la org.

    Un código NUNCA se sobrescribe. `asignador`: la importación pasa el suyo
    (uno por request) para no releer el MAX del catálogo en cada fila. Hace
    `flush` para que la siguiente variante del mismo request vea el código y
    no repita la secuencia.
    """
    if (variante.barcode or "").strip():
        return variante.barcode
    variante.barcode = asignador.siguiente() if asignador is not None else siguiente_codigo_interno(db, org_id)
    db.flush()
    return variante.barcode
```

- [ ] **Step 4: Correr y ver que pasa**

Run: `python3 -m pytest -q -p no:warnings tests/test_productos_servicio_codigos.py`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add app/modules/products/services/__init__.py app/modules/products/services/codigos.py tests/test_productos_servicio_codigos.py
git commit -m "feat(productos): servicio de SKU y codigo interno (unico sin mayusculas, incluye archivados)"
```

---
### Task 2: `services/comun.py` + `services/validaciones.py` — constantes compartidas y validaciones 422

**Files:**
- Create: `app/modules/products/services/comun.py`
- Create: `app/modules/products/services/validaciones.py`
- Modify: `app/modules/products/router/_shared.py:59-90` (roles y helpers de variantes) y `:318-344` (coercers de celdas)
- Modify: `app/modules/products/services/__init__.py`
- Test: `tests/test_productos_servicio_validaciones.py`

**Interfaces:**
- Consumes: `Product`, `ProductVariant`, `Brand`, `Department` (`app.models`); `Branch` (`app.models.organization`); `ProductCreate`, `ProductPriceCreate` (`app.modules.products.schemas`); `COLOR_MAX`, `SIZE_MAX`, `clean_attr` (`app.modules.products.variant_label`).
- Produces:
  - `comun.MANAGER_ROLES: frozenset[str]`, `comun.PRODUCT_ADVANCED_ROLES: frozenset[str]`, `comun.variantes_vivas(product) -> list[ProductVariant]`, `comun.variante_principal(product) -> Optional[ProductVariant]`, `comun.celda_texto(val) -> str`, `comun.celda_vacia(val) -> bool`, `comun.celda_decimal(val, default=Decimal(0)) -> Decimal`.
  - `router/_shared.py` sigue exponiendo `_MANAGER_ROLES`, `_PRODUCT_ADVANCED_ROLES`, `variantes_vivas`, `variante_principal`, `_safe_str`, `_is_na`, `_safe_decimal` (mismos objetos, re-exportados).
  - `validaciones.exigir_campos_de_cajero(datos: ProductCreate) -> None` (422), `validar_precio(precio: Optional[Decimal], detalle: str = "El precio del producto debe ser mayor a cero.") -> None` (422), `validar_escalones(escalones) -> None` (422 nombrando el escalón), `validar_sucursales_de_la_org(db, org_id, branch_ids) -> set[int]` (422), `validar_departamento_y_marca(db, org_id, department_id, brand_id) -> None` (422), `atributos_principal(color, size) -> tuple[Optional[str], Optional[str]]` (422 `"{campo}: {e}"`).

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_productos_servicio_validaciones.py`:

```python
"""Validaciones 422 del alta/edición y constantes compartidas (services/comun.py)."""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.organization import Branch, BranchType, Organization
from app.models.products import Brand, Department
from app.modules.products.schemas import ProductCreate, ProductPriceCreate
from app.modules.products.services.validaciones import (
    atributos_principal, exigir_campos_de_cajero, validar_departamento_y_marca,
    validar_escalones, validar_precio, validar_sucursales_de_la_org,
)


def _422(fn, *args, **kwargs) -> str:
    with pytest.raises(HTTPException) as exc:
        fn(*args, **kwargs)
    assert exc.value.status_code == 422
    return exc.value.detail


class TestPrecio:
    def test_cero_y_negativo_son_422(self):
        assert "mayor a cero" in _422(validar_precio, Decimal("0"))
        _422(validar_precio, Decimal("-1"))

    def test_none_no_se_valida_y_positivo_pasa(self):
        validar_precio(None)
        validar_precio(Decimal("0.01"))

    def test_detalle_personalizado(self):
        assert _422(validar_precio, Decimal("0"), detalle="El precio debe ser mayor a cero.") == "El precio debe ser mayor a cero."


class TestEscalones:
    def test_nombra_el_escalon_en_cero(self):
        detalle = _422(validar_escalones, [
            ProductPriceCreate(price_name="Mayoreo", min_quantity=3, unit_price=10),
            ProductPriceCreate(price_name="Caja", min_quantity=72, unit_price=0),
        ])
        assert detalle == "El precio del escalón 'Caja' debe ser mayor a cero."

    def test_lista_vacia_o_none_pasa(self):
        validar_escalones(None)
        validar_escalones([])


class TestSucursales:
    def test_ajena_es_422(self, db, org, branch_a):
        otra = Organization(name="Otra", status="ACTIVE")
        db.add(otra); db.flush()
        ajena = Branch(name="Ajena", branch_type=BranchType.STORE, can_sell=True,
                       is_active=True, organization_id=otra.id)
        db.add(ajena); db.flush()
        detalle = _422(validar_sucursales_de_la_org, db, org.id, [branch_a.id, ajena.id])
        assert detalle == "Una o más sucursales objetivo no pertenecen a tu organización."

    def test_propias_devuelve_el_conjunto_sin_repetidos(self, db, org, branch_a, branch_b):
        assert validar_sucursales_de_la_org(db, org.id, [branch_a.id, branch_b.id, branch_a.id]) == {branch_a.id, branch_b.id}
        assert validar_sucursales_de_la_org(db, org.id, []) == set()


class TestDepartamentoYMarca:
    def test_de_otra_org_es_422(self, db, org):
        otra = Organization(name="Otra", status="ACTIVE")
        db.add(otra); db.flush()
        d = Department(name="X", organization_id=otra.id)
        m = Brand(name="Y", organization_id=otra.id)
        db.add_all([d, m]); db.flush()
        assert "Departamento" in _422(validar_departamento_y_marca, db, org.id, d.id, None)
        assert "Marca" in _422(validar_departamento_y_marca, db, org.id, None, m.id)

    def test_nones_y_propios_pasan(self, db, org):
        d = Department(name="Propio", organization_id=org.id)
        db.add(d); db.flush()
        validar_departamento_y_marca(db, org.id, None, None)
        validar_departamento_y_marca(db, org.id, d.id, None)


class TestCajeroYAtributos:
    def test_campos_requeridos_nombra_los_faltantes(self):
        datos = ProductCreate(name="  ", sku="X", price=Decimal("1"), cost=Decimal("1"))
        assert _422(exigir_campos_de_cajero, datos) == "Campos requeridos para CAJERO/GERENTE: name"

    def test_talla_larga_dice_el_campo(self):
        assert _422(atributos_principal, "Rojo", "x" * 31).startswith("talla:")
        assert atributos_principal(None, None) == (None, None)
        assert atributos_principal(" Rojo ", " M ") == ("Rojo", "M")


class TestReexportDesdeRouter:
    def test_shared_sigue_exponiendo_los_alias_historicos(self):
        from app.modules.products.router import _shared
        from app.modules.products.services import comun
        assert _shared._PRODUCT_ADVANCED_ROLES is comun.PRODUCT_ADVANCED_ROLES
        assert _shared._MANAGER_ROLES is comun.MANAGER_ROLES
        assert _shared.variante_principal is comun.variante_principal
        assert _shared._safe_decimal("1.5") == Decimal("1.5")
        assert _shared._safe_str(None) == "" and _shared._is_na("nan") is True
```

- [ ] **Step 2: Correr para ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_productos_servicio_validaciones.py`
Expected: FAIL en la colección con `ModuleNotFoundError: No module named 'app.modules.products.services.validaciones'`.

- [ ] **Step 3: Crear `comun.py` y reescribir `_shared.py` para que re-exporte**

`app/modules/products/services/comun.py`:

```python
"""Constantes y helpers que comparten servicios y routers de productos.

Viven aquí (y no en `router/_shared.py`) porque los servicios NO pueden
importar del router: `router/__init__` importa `core`, `core` importa los
servicios, y un servicio que importara `router._shared` cerraría el ciclo.
`router/_shared.py` re-exporta estos nombres con sus alias históricos.
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Optional

from app.models import Product, ProductVariant

MANAGER_ROLES: frozenset = frozenset({"ADMINISTRADOR", "GERENTE", "DUEÑO"})

# Track 3 (POS bug-fix): el cajero es el usuario con más control en tiendas.
# Tiene CRUD completo + bulk + import/export + approve/reject/restore sobre
# productos visibles en su sucursal.
PRODUCT_ADVANCED_ROLES: frozenset = frozenset({"ADMINISTRADOR", "GERENTE", "DUEÑO", "CAJERO"})


def variantes_vivas(product: Product) -> list[ProductVariant]:
    """Variantes del producto que siguen vendibles (sin soft-delete)."""
    return [v for v in (product.variants or []) if v.deleted_at is None]


def variante_principal(product: Product) -> Optional[ProductVariant]:
    """La variante "principal": la primera VIVA en orden de creación.

    `product.variants[0]` incluye las retiradas (`DELETE /variants/{id}`), así
    que después de retirar la primera talla las rutas de escritura terminaban
    editando una variante que ya no se vende. None si no queda ninguna viva.
    """
    vivas = variantes_vivas(product)
    return vivas[0] if vivas else None


def celda_texto(val) -> str:
    """Celda de Excel/CSV como texto recortado ("" si viene vacía o 'nan')."""
    if val is None:
        return ""
    s = str(val).strip()
    if s.lower() == "nan":
        return ""
    return s


def celda_vacia(val) -> bool:
    """True cuando una celda de openpyxl/csv debe tratarse como ausente."""
    if val is None:
        return True
    if isinstance(val, float) and math.isnan(val):
        return True
    if isinstance(val, str) and val.strip().lower() in ("nan", "none"):
        return True
    return False


def celda_decimal(val, default: Decimal = Decimal(0)) -> Decimal:
    try:
        if celda_vacia(val):
            return default
        return Decimal(str(val))
    except Exception:
        return default
```

En `app/modules/products/router/_shared.py` **reemplaza** el bloque que va desde `_MANAGER_ROLES: frozenset = frozenset({"ADMINISTRADOR", "GERENTE", "DUEÑO"})` hasta el final de `variante_principal` (líneas 59–90: las dos constantes, el comentario de Track 3, `variantes_vivas` y `variante_principal`) por:

```python
# Fuente única: `services/comun.py` (los servicios no pueden importar de aquí).
# Se conservan los nombres históricos para los sub-routers que ya los usan.
from app.modules.products.services.comun import (  # noqa: E402
    MANAGER_ROLES as _MANAGER_ROLES,
    PRODUCT_ADVANCED_ROLES as _PRODUCT_ADVANCED_ROLES,
    celda_decimal as _safe_decimal,
    celda_texto as _safe_str,
    celda_vacia as _is_na,
    variante_principal,
    variantes_vivas,
)

CRITICAL_STOCK_THRESHOLD = 5
```

y **borra** las tres funciones `_safe_str`, `_is_na`, `_safe_decimal` del final del archivo (líneas 318–344). `CRITICAL_STOCK_THRESHOLD = 5` estaba dentro de ese bloque: queda tal cual, debajo del import (lo usa `stats.py`). Verifica con `grep -n "def _safe_str\|def _is_na\|def _safe_decimal\|def variantes_vivas\|def variante_principal" app/modules/products/router/_shared.py` que no quede ninguna definición (debe imprimir nada).

- [ ] **Step 4: Crear `validaciones.py`**

```python
"""Validaciones de negocio del alta/edición de productos (422).

Cada función levanta `HTTPException` con el MISMO texto que usaban los
handlers, para que la pantalla y los cuatro clientes vivos no vean mensajes
nuevos. Nada de aquí escribe en la base.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Brand, Department
from app.models.organization import Branch
from app.modules.products.schemas import ProductCreate, ProductPriceCreate
from app.modules.products.variant_label import COLOR_MAX, SIZE_MAX, clean_attr


def exigir_campos_de_cajero(datos: ProductCreate) -> None:
    """CAJERO/GERENTE deben mandar name, sku, price y cost (marca y
    departamento NO: una tienda recién dada de alta no los tiene)."""
    requeridos = {"name": datos.name, "sku": datos.sku, "price": datos.price, "cost": datos.cost}
    faltan = [
        k for k, v in requeridos.items()
        if v is None or (isinstance(v, str) and not v.strip())
    ]
    if faltan:
        raise HTTPException(
            status_code=422,
            detail=f"Campos requeridos para CAJERO/GERENTE: {', '.join(faltan)}",
        )


def validar_precio(
    precio: Optional[Decimal],
    detalle: str = "El precio del producto debe ser mayor a cero.",
) -> None:
    """ATS-25: un producto a $0 es invendible (o regalado). None = no se valida
    (la edición manda None cuando no toca el precio)."""
    if precio is not None and precio <= 0:
        raise HTTPException(status_code=422, detail=detalle)


def validar_escalones(escalones: Optional[Iterable[ProductPriceCreate]]) -> None:
    """Un escalón en $0 también regala el producto: el POS elige el escalón
    más barato aplicable. Nombra el escalón culpable."""
    for e in (escalones or []):
        if e.unit_price is not None and e.unit_price <= 0:
            raise HTTPException(
                status_code=422,
                detail=f"El precio del escalón '{e.price_name}' debe ser mayor a cero.",
            )


def validar_sucursales_de_la_org(db: Session, org_id: int, branch_ids: Iterable[int]) -> set[int]:
    """Guard cross-tenant: toda sucursal destino debe ser de esta org. Sin
    esto, `target_branch_ids` podría inyectar StockOnHand/PBS en otra tienda."""
    pedidas = set(branch_ids or [])
    if not pedidas:
        return set()
    propias = {
        b.id for b in db.query(Branch.id).filter(
            Branch.id.in_(pedidas), Branch.organization_id == org_id,
        ).all()
    }
    if propias != pedidas:
        raise HTTPException(
            status_code=422,
            detail="Una o más sucursales objetivo no pertenecen a tu organización.",
        )
    return propias


def validar_departamento_y_marca(
    db: Session, org_id: int, department_id: Optional[str], brand_id: Optional[str],
) -> None:
    if department_id and db.query(Department.id).filter(
        Department.id == department_id, Department.organization_id == org_id,
    ).first() is None:
        raise HTTPException(status_code=422, detail="Departamento no encontrado en tu organización.")
    if brand_id and db.query(Brand.id).filter(
        Brand.id == brand_id, Brand.organization_id == org_id,
    ).first() is None:
        raise HTTPException(status_code=422, detail="Marca no encontrada en tu organización.")


def atributos_principal(color: Optional[str], size: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Limpia color/talla de la variante principal o 422 nombrando el campo.

    `clean_attr` levanta ValueError cuando el texto excede el límite; sin este
    envoltorio Postgres truncaría (o reventaría) y el formulario no sabría cuál
    de los dos campos corregir.
    """
    salida = []
    for valor, tope, campo in ((color, COLOR_MAX, "color"), (size, SIZE_MAX, "talla")):
        try:
            salida.append(clean_attr(valor, tope))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"{campo}: {e}")
    return salida[0], salida[1]
```

Agrega a `app/modules/products/services/__init__.py`:

```python
from .comun import (  # noqa: F401
    MANAGER_ROLES, PRODUCT_ADVANCED_ROLES, celda_decimal, celda_texto, celda_vacia,
    variante_principal, variantes_vivas,
)
from .validaciones import (  # noqa: F401
    atributos_principal, exigir_campos_de_cajero, validar_departamento_y_marca,
    validar_escalones, validar_precio, validar_sucursales_de_la_org,
)
```

- [ ] **Step 5: Correr las nuevas y las que dependen de `_shared`**

Run: `python3 -m pytest -q -p no:warnings tests/test_productos_servicio_validaciones.py tests/test_productos_servicio_codigos.py tests/test_product_creation.py tests/test_variant_endpoints.py tests/test_import_export_variantes.py tests/test_admin_catalog_advanced.py`
Expected: todas passed (la re-exportación no cambia comportamiento).

- [ ] **Step 6: Commit**

```bash
git add app/modules/products/services/ app/modules/products/router/_shared.py tests/test_productos_servicio_validaciones.py
git commit -m "refactor(productos): constantes y validaciones del alta en services/ (router/_shared re-exporta)"
```

---

### Task 3: `services/sucursales.py` — estado por sucursal y existencias

**Files:**
- Create: `app/modules/products/services/sucursales.py`
- Modify: `app/modules/products/services/__init__.py`
- Test: `tests/test_productos_servicio_sucursales.py`

**Interfaces:**
- Consumes: `ProductBranchStatus`, `ProductVariant`, `StockOnHand`, `InventoryMovement`, `MovementType` (`app.models`); `Branch` (`app.models.organization`).
- Produces:
  - `sucursales_que_venden(db, org_id) -> list[int]` — `is_active AND can_sell`, ordenadas por id.
  - `resolver_sucursales_destino(db, org_id, user, target_branch_ids: Optional[Iterable[int]]) -> list[int]` — `targets ∪ {user.branch_id}`; vacío → `sucursales_que_venden` (decisión §6.4); ordenada.
  - `sucursal_de_existencia_inicial(user, branch_id: Optional[int], destinos: list[int]) -> Optional[int]` — `branch_id` si está en destinos, si no `user.branch_id` si está, si no `destinos[0]`, si no None.
  - `armar_estado_por_sucursal(db, org_id, variante, branch_ids, *, is_active_hq: bool = False, reemplazar: bool = False) -> None` — crea los PBS faltantes (`is_active_pos=True, is_visible=True`), a los que ya existen solo les pone `is_visible=True`; `reemplazar=True` borra antes todos los PBS de la variante. Hace `flush`.
  - `copiar_estado_por_sucursal(db, org_id, origen, destino) -> None` — copia banderas y `price_override/min_stock_alert/max_stock_limit`.
  - `registrar_stock_inicial(db, org_id, variante, branch_ids, destino: Optional[int], qty: Decimal, user_id, *, referencia="Alta Inicial", notas="Creación de producto") -> None` — un `StockOnHand` por sucursal (qty en `destino`, 0 en el resto) y kardex `ADJUSTMENT_IN` solo si qty > 0.
  - `fijar_existencia(db, org_id, variante, branch_id, objetivo: Decimal, user_id, *, referencia="Excel Upload", notas: str) -> None` — existencia absoluta con ajuste por diferencia (crea el `StockOnHand` si no existe; sin kardex si no hay diferencia).

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_productos_servicio_sucursales.py`:

```python
"""Estado por sucursal y existencias: los helpers que antes estaban copiados
en create, update, duplicate, crear_variantes y upload."""
from decimal import Decimal
from types import SimpleNamespace

from conftest import _make_product
from app.models.inventory import InventoryMovement, MovementType, StockOnHand
from app.models.products import ProductBranchStatus
from app.modules.products.services.sucursales import (
    armar_estado_por_sucursal, copiar_estado_por_sucursal, fijar_existencia,
    registrar_stock_inicial, resolver_sucursales_destino,
    sucursal_de_existencia_inicial, sucursales_que_venden,
)

SIN_SUCURSAL = SimpleNamespace(branch_id=None)


class TestResolverDestino:
    def test_sin_sucursal_ni_destinos_toma_todas_las_que_venden(self, db, org, branch_a, branch_b, hq_branch):
        # hq_branch tiene can_sell=False: no entra.
        assert resolver_sucursales_destino(db, org.id, SIN_SUCURSAL, None) == sorted([branch_a.id, branch_b.id])

    def test_inactiva_o_que_no_vende_no_entra(self, db, org, branch_a, branch_b):
        branch_b.is_active = False
        db.flush()
        assert sucursales_que_venden(db, org.id) == [branch_a.id]

    def test_con_destinos_une_la_del_usuario_y_ordena(self, db, org, branch_a, branch_b):
        usuario = SimpleNamespace(branch_id=branch_b.id)
        assert resolver_sucursales_destino(db, org.id, usuario, [branch_a.id, branch_a.id]) == sorted([branch_a.id, branch_b.id])

    def test_sin_ninguna_que_venda_queda_vacio(self, db, org, hq_branch):
        assert resolver_sucursales_destino(db, org.id, SIN_SUCURSAL, None) == []


class TestSucursalDeExistencia:
    def test_orden_de_preferencia(self, branch_a, branch_b):
        usuario = SimpleNamespace(branch_id=branch_b.id)
        destinos = sorted([branch_a.id, branch_b.id])
        assert sucursal_de_existencia_inicial(usuario, branch_a.id, destinos) == branch_a.id
        assert sucursal_de_existencia_inicial(usuario, None, destinos) == branch_b.id
        assert sucursal_de_existencia_inicial(SIN_SUCURSAL, 999999, destinos) == destinos[0]
        assert sucursal_de_existencia_inicial(SIN_SUCURSAL, None, []) is None


class TestEstadoPorSucursal:
    def test_crea_faltantes_y_no_duplica_existentes(self, db, org, branch_a, branch_b):
        _, v = _make_product(db, org, "P", "PBS-1", 10, [(branch_a.id, False)])
        armar_estado_por_sucursal(db, org.id, v, [branch_a.id, branch_b.id], is_active_hq=True)
        filas = {p.branch_id: p for p in db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == v.id).all()}
        assert set(filas) == {branch_a.id, branch_b.id}
        # La que ya existía solo se hace visible; sus demás banderas no se tocan.
        assert filas[branch_a.id].is_visible is True and filas[branch_a.id].is_active_pos is False
        assert filas[branch_b.id].is_active_hq is True and filas[branch_b.id].is_active_pos is True

    def test_reemplazar_borra_las_viejas(self, db, org, branch_a, branch_b):
        _, v = _make_product(db, org, "P", "PBS-2", 10, [(branch_a.id, True)])
        armar_estado_por_sucursal(db, org.id, v, [branch_b.id], reemplazar=True)
        assert [p.branch_id for p in db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == v.id).all()] == [branch_b.id]

    def test_copiar_conserva_banderas_y_overrides(self, db, org, branch_a):
        _, origen = _make_product(db, org, "O", "PBS-3", 10, [(branch_a.id, True)])
        pbs = db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == origen.id).one()
        pbs.price_override = Decimal("9.50")
        pbs.is_active_hq = True
        db.flush()
        _, destino = _make_product(db, org, "D", "PBS-4", 10)
        copiar_estado_por_sucursal(db, org.id, origen, destino)
        copia = db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == destino.id).one()
        assert (copia.branch_id, copia.price_override, copia.is_active_hq) == (branch_a.id, Decimal("9.50"), True)


class TestExistencias:
    def test_stock_inicial_va_al_destino_y_cero_a_las_demas_con_kardex(self, db, org, branch_a, branch_b, admin_user):
        _, v = _make_product(db, org, "S", "SOH-1", 10)
        registrar_stock_inicial(db, org.id, v, [branch_a.id, branch_b.id], branch_b.id, Decimal("7"), admin_user.id)
        por_sucursal = {s.branch_id: s.qty_on_hand for s in db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).all()}
        assert por_sucursal == {branch_a.id: Decimal("0"), branch_b.id: Decimal("7")}
        movs = db.query(InventoryMovement).filter(InventoryMovement.variant_id == v.id).all()
        assert len(movs) == 1
        assert (movs[0].branch_id, movs[0].reference, movs[0].notes) == (branch_b.id, "Alta Inicial", "Creación de producto")
        assert (movs[0].qty_before, movs[0].qty_after) == (Decimal("0"), Decimal("7"))

    def test_fijar_existencia_ajusta_por_diferencia_y_calla_si_no_cambia(self, db, org, branch_a, admin_user):
        _, v = _make_product(db, org, "F", "SOH-2", 10, [(branch_a.id, True)])   # nace con 100
        fijar_existencia(db, org.id, v, branch_a.id, Decimal("40"), admin_user.id, notas="Carga Masiva (Ajuste)")
        soh = db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).one()
        assert soh.qty_on_hand == Decimal("40")
        mov = db.query(InventoryMovement).filter(InventoryMovement.variant_id == v.id).one()
        assert (mov.movement_type, mov.qty_change, mov.qty_before, mov.qty_after, mov.reference) == \
            (MovementType.ADJUSTMENT_OUT, Decimal("60"), Decimal("100"), Decimal("40"), "Excel Upload")
        fijar_existencia(db, org.id, v, branch_a.id, Decimal("40"), admin_user.id, notas="Carga Masiva (Ajuste)")
        assert db.query(InventoryMovement).filter(InventoryMovement.variant_id == v.id).count() == 1

    def test_fijar_existencia_crea_el_registro_si_no_existe(self, db, org, branch_b, admin_user):
        _, v = _make_product(db, org, "F", "SOH-3", 10)
        fijar_existencia(db, org.id, v, branch_b.id, Decimal("3"), admin_user.id, notas="Carga Masiva (Inicial)")
        soh = db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).one()
        assert (soh.branch_id, soh.qty_on_hand) == (branch_b.id, Decimal("3"))
        mov = db.query(InventoryMovement).filter(InventoryMovement.variant_id == v.id).one()
        assert (mov.movement_type, mov.qty_change) == (MovementType.ADJUSTMENT_IN, Decimal("3"))
```

- [ ] **Step 2: Correr para ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_productos_servicio_sucursales.py`
Expected: FAIL en la colección con `ModuleNotFoundError: No module named 'app.modules.products.services.sucursales'`.

- [ ] **Step 3: Crear `sucursales.py`**

```python
"""Estado comercial por sucursal (ProductBranchStatus) y existencias.

Antes estaba copiado a mano en `create_product`, `update_product`,
`duplicate_product`, `crear_variantes` y `upload_products`, cada uno con
pequeñas diferencias. Aquí hay una sola versión de cada operación; las
diferencias legítimas (texto del kardex, `is_active_hq`) son parámetros.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models import (
    InventoryMovement, MovementType, ProductBranchStatus, ProductVariant, StockOnHand,
)
from app.models.organization import Branch


def sucursales_que_venden(db: Session, org_id: int) -> list[int]:
    """Sucursales activas con `can_sell=True`, por id (orden determinista)."""
    return [
        b.id for b in db.query(Branch.id).filter(
            Branch.organization_id == org_id,
            Branch.is_active == True,   # noqa: E712
            Branch.can_sell == True,    # noqa: E712
        ).order_by(Branch.id).all()
    ]


def resolver_sucursales_destino(
    db: Session, org_id: int, user, target_branch_ids: Optional[Iterable[int]],
) -> list[int]:
    """Dónde queda habilitado un producto nuevo.

    Las sucursales objetivo que mandó el formulario más la del usuario (un
    cajero/gerente siempre lleva la suya). Un usuario sin sucursal que no manda
    destinos (HQ puro) habilita el producto en TODAS las que venden (mega plan
    2026-10, §6.4); si la org no tiene ninguna que venda, queda sin PBS y el
    OUTER JOIN de ATS-11 lo muestra en todas, como antes.
    """
    destino = set(target_branch_ids or [])
    if user.branch_id:
        destino.add(user.branch_id)
    if not destino:
        destino = set(sucursales_que_venden(db, org_id))
    return sorted(destino)


def sucursal_de_existencia_inicial(user, branch_id: Optional[int], destinos: list[int]) -> Optional[int]:
    """Una sola sucursal recibe la existencia inicial: la que eligió el
    formulario, si no la del usuario, si no la primera destino."""
    if branch_id and branch_id in destinos:
        return branch_id
    if user.branch_id and user.branch_id in destinos:
        return user.branch_id
    return destinos[0] if destinos else None


def armar_estado_por_sucursal(
    db: Session, org_id: int, variante: ProductVariant, branch_ids: Iterable[int], *,
    is_active_hq: bool = False, reemplazar: bool = False,
) -> None:
    """Habilita la variante en `branch_ids` (POS sí, visible sí).

    Idempotente: a un PBS que ya existe solo le pone `is_visible=True` (es lo
    que hacía el upload). `reemplazar=True` (edición con `target_branch_ids`)
    borra primero todos los PBS de la variante. Hace `flush` para que
    `crear_variantes` —que lee el PBS de la principal— lo vea.
    """
    if reemplazar:
        db.query(ProductBranchStatus).filter(
            ProductBranchStatus.variant_id == variante.id,
            ProductBranchStatus.organization_id == org_id,
        ).delete(synchronize_session=False)
        existentes: dict[int, ProductBranchStatus] = {}
    else:
        existentes = {
            pbs.branch_id: pbs for pbs in db.query(ProductBranchStatus).filter(
                ProductBranchStatus.variant_id == variante.id,
                ProductBranchStatus.organization_id == org_id,
            ).all()
        }
    for bid in branch_ids:
        pbs = existentes.get(bid)
        if pbs is None:
            db.add(ProductBranchStatus(
                variant_id=variante.id,
                branch_id=bid,
                is_active_pos=True,
                is_active_hq=is_active_hq,
                is_visible=True,
                organization_id=org_id,
            ))
        else:
            pbs.is_visible = True
    db.flush()


def copiar_estado_por_sucursal(db: Session, org_id: int, origen: ProductVariant, destino: ProductVariant) -> None:
    """La copia hereda la misma configuración multi-sucursal (sin StockOnHand)."""
    for src in db.query(ProductBranchStatus).filter(
        ProductBranchStatus.variant_id == origen.id,
        ProductBranchStatus.organization_id == org_id,
    ).all():
        db.add(ProductBranchStatus(
            organization_id=org_id,
            variant_id=destino.id,
            branch_id=src.branch_id,
            is_active_pos=src.is_active_pos,
            is_active_hq=src.is_active_hq,
            is_visible=src.is_visible,
            price_override=src.price_override,
            min_stock_alert=src.min_stock_alert,
            max_stock_limit=src.max_stock_limit,
        ))
    db.flush()


def registrar_stock_inicial(
    db: Session, org_id: int, variante: ProductVariant, branch_ids: Iterable[int],
    destino: Optional[int], qty: Decimal, user_id: Optional[int], *,
    referencia: str = "Alta Inicial", notas: str = "Creación de producto",
) -> None:
    """Un StockOnHand por sucursal habilitada; la existencia inicial cae en
    `destino` y las demás nacen en 0. Kardex de apertura solo si hay piezas:
    sin movimiento, el inventario arranca con una existencia que no aparece
    en ningún reporte."""
    for bid in branch_ids:
        cantidad = qty if bid == destino else Decimal(0)
        db.add(StockOnHand(
            branch_id=bid, variant_id=variante.id, qty_on_hand=cantidad,
            is_active=True, organization_id=org_id,
        ))
        if cantidad > 0:
            db.add(InventoryMovement(
                branch_id=bid, variant_id=variante.id, user_id=user_id,
                movement_type=MovementType.ADJUSTMENT_IN,
                qty_change=cantidad, qty_before=Decimal(0), qty_after=cantidad,
                reference=referencia, notes=notas, organization_id=org_id,
            ))
    db.flush()


def fijar_existencia(
    db: Session, org_id: int, variante: ProductVariant, branch_id: int,
    objetivo: Decimal, user_id: Optional[int], *,
    referencia: str = "Excel Upload", notas: str,
) -> None:
    """Existencia ABSOLUTA (el "Stock" del archivo es lo que hay, no lo que
    entra): ajusta por diferencia y deja kardex solo si cambió algo."""
    registro = db.query(StockOnHand).filter(
        StockOnHand.variant_id == variante.id,
        StockOnHand.branch_id == branch_id,
        StockOnHand.organization_id == org_id,
    ).first()
    if registro is None:
        registro = StockOnHand(
            branch_id=branch_id, variant_id=variante.id, qty_on_hand=Decimal(0),
            is_active=True, organization_id=org_id,
        )
        db.add(registro)
        db.flush()
    anterior = Decimal(registro.qty_on_hand or 0)
    diferencia = objetivo - anterior
    if diferencia == 0:
        return
    registro.qty_on_hand = objetivo
    db.add(InventoryMovement(
        branch_id=branch_id, variant_id=variante.id, user_id=user_id,
        movement_type=MovementType.ADJUSTMENT_IN if diferencia > 0 else MovementType.ADJUSTMENT_OUT,
        qty_change=abs(diferencia), qty_before=anterior, qty_after=objetivo,
        reference=referencia, notes=notas, organization_id=org_id,
    ))
    db.flush()
```

Agrega a `services/__init__.py`:

```python
from .sucursales import (  # noqa: F401
    armar_estado_por_sucursal, copiar_estado_por_sucursal, fijar_existencia,
    registrar_stock_inicial, resolver_sucursales_destino,
    sucursal_de_existencia_inicial, sucursales_que_venden,
)
```

- [ ] **Step 4: Correr y ver que pasa**

Run: `python3 -m pytest -q -p no:warnings tests/test_productos_servicio_sucursales.py`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add app/modules/products/services/sucursales.py app/modules/products/services/__init__.py tests/test_productos_servicio_sucursales.py
git commit -m "feat(productos): helpers de estado por sucursal y existencias en services/"
```

---
### Task 4: `services/precios.py` — empaques y escalones

**Files:**
- Create: `app/modules/products/services/precios.py`
- Modify: `app/modules/products/services/__init__.py`
- Test: `tests/test_productos_servicio_precios.py`

**Interfaces:**
- Consumes: `PackagingUnit`, `ProductPrice`, `ProductVariant` (`app.models`); `PackagingUnitCreate`, `ProductPriceCreate` (schemas); `validar_escalones` (Task 2).
- Produces:
  - `armar_empaques(db, org_id, variante, empaques: Optional[list[PackagingUnitCreate]], *, reemplazar: bool = False) -> dict[str, str]` — crea los `PackagingUnit`; devuelve mapa `temp_id → id` y `nombre.lower() → id`. `reemplazar=True` desenlaza los escalones (`linked_package_id=None`) y borra los empaques previos.
  - `armar_escalones(db, org_id, variante, escalones: Optional[list[ProductPriceCreate]], mapa_empaques: dict[str, str], *, reemplazar: bool = False) -> None` — valida (422) **antes** de escribir; resuelve `linked_package_id` por el mapa (temp_id o nombre) y, si viene vacío, por `price_name.lower()`; `reemplazar=True` borra los escalones previos.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_productos_servicio_precios.py`:

```python
"""Empaques y escalones: una sola versión del armado (antes create, update y
upload lo hacían cada uno a su manera)."""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from conftest import _make_product
from app.models.products import PackagingUnit, ProductPrice
from app.modules.products.schemas import PackagingUnitCreate, ProductPriceCreate
from app.modules.products.services.precios import armar_empaques, armar_escalones


class TestEmpaquesYEscalones:
    def test_mapa_por_temp_id_y_nombre_enlaza_escalones(self, db, org, branch_a):
        _, v = _make_product(db, org, "Refresco", "REF-1", 10, [(branch_a.id, True)])
        mapa = armar_empaques(db, org.id, v, [
            PackagingUnitCreate(temp_id="tmp-caja", name="Caja", units_per_package=24, package_price=200),
        ])
        caja_id = mapa["tmp-caja"]
        assert mapa["caja"] == caja_id
        armar_escalones(db, org.id, v, [
            ProductPriceCreate(price_name="Mayoreo", min_quantity=12, unit_price=9, linked_package_id="tmp-caja"),
            ProductPriceCreate(price_name="Caja", min_quantity=24, unit_price=8),   # enlaza por nombre
            ProductPriceCreate(price_name="Suelto", min_quantity=1, unit_price=10),
        ], mapa)
        por_nombre = {p.price_name: p.linked_package_id
                      for p in db.query(ProductPrice).filter(ProductPrice.variant_id == v.id).all()}
        assert por_nombre == {"Mayoreo": caja_id, "Caja": caja_id, "Suelto": None}

    def test_reemplazar_borra_lo_anterior_y_desenlaza_antes(self, db, org, branch_a):
        _, v = _make_product(db, org, "Refresco", "REF-2", 10, [(branch_a.id, True)])
        mapa = armar_empaques(db, org.id, v, [PackagingUnitCreate(name="Caja", units_per_package=24, package_price=200)])
        armar_escalones(db, org.id, v, [ProductPriceCreate(price_name="Caja", min_quantity=24, unit_price=8)], mapa)
        mapa2 = armar_empaques(db, org.id, v, [PackagingUnitCreate(name="Pack", units_per_package=6, package_price=55)], reemplazar=True)
        armar_escalones(db, org.id, v, [ProductPriceCreate(price_name="Pack", min_quantity=6, unit_price=9)], mapa2, reemplazar=True)
        assert [p.name for p in db.query(PackagingUnit).filter(PackagingUnit.variant_id == v.id).all()] == ["Pack"]
        precios = db.query(ProductPrice).filter(ProductPrice.variant_id == v.id).all()
        assert [(p.price_name, p.linked_package_id) for p in precios] == [("Pack", mapa2["pack"])]

    def test_escalon_en_cero_es_422_antes_de_escribir(self, db, org, branch_a):
        _, v = _make_product(db, org, "Refresco", "REF-3", 10, [(branch_a.id, True)])
        with pytest.raises(HTTPException) as exc:
            armar_escalones(db, org.id, v, [ProductPriceCreate(price_name="Caja", min_quantity=24, unit_price=0)], {})
        assert exc.value.status_code == 422 and "Caja" in exc.value.detail
        assert db.query(ProductPrice).filter(ProductPrice.variant_id == v.id).count() == 0

    def test_listas_vacias_no_escriben_nada(self, db, org, branch_a):
        _, v = _make_product(db, org, "Refresco", "REF-4", 10, [(branch_a.id, True)])
        assert armar_empaques(db, org.id, v, None) == {}
        armar_escalones(db, org.id, v, None, {})
        assert db.query(PackagingUnit).filter(PackagingUnit.variant_id == v.id).count() == 0
```

- [ ] **Step 2: Correr para ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_productos_servicio_precios.py`
Expected: FAIL en la colección con `ModuleNotFoundError: No module named 'app.modules.products.services.precios'`.

- [ ] **Step 3: Crear `precios.py`**

```python
"""Empaques (PackagingUnit) y escalones de precio (ProductPrice) de una variante."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import PackagingUnit, ProductPrice, ProductVariant
from app.modules.products.schemas import PackagingUnitCreate, ProductPriceCreate

from .validaciones import validar_escalones


def armar_empaques(
    db: Session, org_id: int, variante: ProductVariant,
    empaques: Optional[list[PackagingUnitCreate]], *, reemplazar: bool = False,
) -> dict[str, str]:
    """Crea los empaques y devuelve el mapa para enlazar escalones:
    `temp_id -> id` (el formulario manda ids temporales) y `nombre -> id`.

    `reemplazar` (edición): primero se desenlazan los escalones que apuntan a
    un empaque (FK) y luego se borran los empaques viejos.
    """
    if reemplazar:
        db.query(ProductPrice).filter(ProductPrice.variant_id == variante.id).update(
            {ProductPrice.linked_package_id: None}, synchronize_session=False,
        )
        db.query(PackagingUnit).filter(PackagingUnit.variant_id == variante.id).delete(
            synchronize_session=False,
        )
        db.flush()
        db.expire(variante, ["packaging_units", "prices"])
    mapa: dict[str, str] = {}
    for e in (empaques or []):
        nuevo = PackagingUnit(
            variant_id=variante.id,
            name=e.name,
            barcode=e.barcode,
            units_per_package=e.units_per_package,
            package_price=e.package_price,
            weight=e.weight,
            dimensions=e.dimensions,
            organization_id=org_id,
        )
        db.add(nuevo)
        db.flush()
        if e.temp_id:
            mapa[e.temp_id] = nuevo.id
        mapa[(e.name or "").lower()] = nuevo.id
    return mapa


def armar_escalones(
    db: Session, org_id: int, variante: ProductVariant,
    escalones: Optional[list[ProductPriceCreate]], mapa_empaques: dict[str, str], *,
    reemplazar: bool = False,
) -> None:
    """Escalones de la variante. Valida ANTES de borrar/escribir: un 422 a
    medio camino dejaría al producto sin escalones."""
    validar_escalones(escalones)
    if reemplazar:
        db.query(ProductPrice).filter(ProductPrice.variant_id == variante.id).delete(
            synchronize_session=False,
        )
        db.flush()
        db.expire(variante, ["prices"])
    for e in (escalones or []):
        enlace = e.linked_package_id
        if enlace in mapa_empaques:
            enlace = mapa_empaques[enlace]
        elif not enlace and e.price_name:
            enlace = mapa_empaques.get(e.price_name.lower())
        db.add(ProductPrice(
            variant_id=variante.id,
            price_name=e.price_name,
            min_quantity=e.min_quantity,
            unit_price=e.unit_price,
            linked_package_id=enlace,
            organization_id=org_id,
        ))
    db.flush()
```

Agrega a `services/__init__.py`: `from .precios import armar_empaques, armar_escalones  # noqa: F401`.

- [ ] **Step 4: Correr y ver que pasa**

Run: `python3 -m pytest -q -p no:warnings tests/test_productos_servicio_precios.py`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/modules/products/services/precios.py app/modules/products/services/__init__.py tests/test_productos_servicio_precios.py
git commit -m "feat(productos): helpers de empaques y escalones en services/"
```

---

### Task 5: `crear_producto` + `POST /api/products/` delgado + `require_module("catalog")`

**Files:**
- Create: `app/modules/products/services/productos.py`
- Modify: `app/modules/products/services/__init__.py`
- Modify: `app/modules/products/router/core.py:187-545` (`create_product`) e imports
- Modify: `tests/conftest.py` (fixtures nuevas), `tests/test_product_creation.py:26-37` y `:266-281`, `tests/test_admin_catalog_regression.py:31-40`
- Test: `tests/test_altas_crear_producto.py`

**Interfaces:**
- Consumes: Tasks 1–4; `_is_admin` (`app.crud.products`); `PlatformAuditLog` (`app.models.platform`); `variant_label` (`app.modules.products.variant_label`); `crear_variantes` (hoy en `app.modules.products.router.variants`; se muda en Task 6 — **en esta tarea se importa de forma perezosa dentro de la función** para no cerrar el ciclo router↔services).
- Produces: `crear_producto(db, org_id: int, user: User, datos: ProductCreate, *, asignador: Optional[AsignadorDeCodigos] = None, is_active_hq: bool = False, kardex: tuple[str, str] = ("Alta Inicial", "Creación de producto")) -> Product` — sin commit; el handler confirma. Fixtures en conftest: `catalog_module_enabled`, `admin_sin_sucursal`, `auth_admin_sin_sucursal`.

- [ ] **Step 1: Fixtures en `tests/conftest.py`** (al final del bloque de usuarios, después de `auth_superadmin`):

```python
@pytest.fixture()
def admin_sin_sucursal(db, org):
    """ADMINISTRADOR sin `branch_id` (oficina central pura).

    Sin sucursal ni `target_branch_ids`, el alta lo habilita en todas las
    sucursales que venden (mega plan 2026-10, §6.4).
    """
    return _make_user(db, org, None, "admin_sin_sucursal", Role.ADMINISTRADOR)


@pytest.fixture()
def auth_admin_sin_sucursal(admin_sin_sucursal):
    return _auth_header(admin_sin_sucursal)


@pytest.fixture()
def catalog_module_enabled(db, org):
    """Enciende el módulo `catalog` para la org de prueba.

    `require_module("catalog")` exime a ADMINISTRADOR/DUEÑO; CAJERO/GERENTE
    lo necesitan para crear, editar, duplicar e importar productos.
    """
    from app.models.modules import Module, OrganizationModule
    if db.query(Module).filter(Module.key == "catalog").first() is None:
        db.add(Module(key="catalog", name="Catálogo"))
        db.flush()
    if db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key == "catalog",
    ).first() is None:
        db.add(OrganizationModule(organization_id=org.id, module_key="catalog", is_enabled=True))
        db.flush()
```

Borra la fixture local `catalog_module_enabled` de `tests/test_product_creation.py` (líneas 26–37, desde `@pytest.fixture()` hasta `db.flush()`) y de `tests/test_admin_catalog_regression.py` (líneas 31–40). Si `Module`/`OrganizationModule` quedan sin uso en esos archivos, quita el import. Corre `python3 -m pytest -q -p no:warnings tests/test_product_creation.py tests/test_admin_catalog_regression.py` → mismo conteo de passed que antes.

- [ ] **Step 2: Escribir las pruebas que fallan**

Crear `tests/test_altas_crear_producto.py`:

```python
"""Alta de producto por `services.crear_producto` (POST /api/products/)."""
import inspect
from datetime import datetime, timezone
from decimal import Decimal

from conftest import _make_product
from app.models.inventory import StockOnHand
from app.models.products import ProductBranchStatus, ProductPrice, ProductVariant


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


def _cuerpo(sku, **extra):
    return {"name": f"Prod {sku}", "sku": sku, "price": "100", "cost": "50", **extra}


def _archivar(db, producto, variante):
    ahora = datetime.now(timezone.utc)
    producto.deleted_at = ahora
    producto.is_active = False
    variante.deleted_at = ahora
    db.flush()


class TestSkuUnico:
    def test_mayusculas_distintas_es_409(self, client, db, org, branch_a, auth_admin):
        _make_product(db, org, "Playera", "PLY-1", 100, [(branch_a.id, True)])
        db.flush()
        r = client.post("/api/products/", json=_cuerpo("ply-1", target_branch_ids=[branch_a.id]),
                        headers=_h(auth_admin, org))
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == "El SKU 'ply-1' ya existe en esta organización."

    def test_sku_de_producto_archivado_es_409_y_lo_dice(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Vieja", "ARCH-1", 100, [(branch_a.id, True)])
        _archivar(db, p, v)
        r = client.post("/api/products/", json=_cuerpo("ARCH-1"), headers=_h(auth_admin, org))
        assert r.status_code == 409, r.text
        assert "archivado" in r.json()["detail"]

    def test_sku_con_espacios_se_guarda_recortado(self, client, db, org, branch_a, auth_admin):
        r = client.post("/api/products/", json=_cuerpo("  REC-1 ", target_branch_ids=[branch_a.id]),
                        headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        assert r.json()["sku"] == "REC-1"


class TestHqSinDestinos:
    def test_queda_habilitado_en_todas_las_que_venden(self, client, db, org, branch_a, branch_b, hq_branch, auth_admin_sin_sucursal):
        r = client.post("/api/products/", json=_cuerpo("HQ-1"), headers=_h(auth_admin_sin_sucursal, org))
        assert r.status_code == 200, r.text
        v = db.query(ProductVariant).filter(ProductVariant.sku == "HQ-1").one()
        pbs = {p.branch_id for p in db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == v.id).all()}
        assert pbs == {branch_a.id, branch_b.id}, "HQ no vende: no se habilita ahí"
        soh = {s.branch_id: s.qty_on_hand for s in db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).all()}
        assert soh == {branch_a.id: Decimal("0"), branch_b.id: Decimal("0")}

    def test_con_existencia_y_varias_que_venden_pide_sucursal(self, client, db, org, branch_a, branch_b, auth_admin_sin_sucursal):
        r = client.post("/api/products/", json=_cuerpo("HQ-2", initial_stock="5"), headers=_h(auth_admin_sin_sucursal, org))
        assert r.status_code == 422, r.text
        assert r.json()["detail"] == "Indica en qué sucursal entra la existencia inicial: no se reparte sola entre varias sucursales."
        r2 = client.post("/api/products/", json=_cuerpo("HQ-2", initial_stock="5", branch_id=branch_b.id),
                         headers=_h(auth_admin_sin_sucursal, org))
        assert r2.status_code == 200, r2.text
        v = db.query(ProductVariant).filter(ProductVariant.sku == "HQ-2").one()
        soh = {s.branch_id: s.qty_on_hand for s in db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).all()}
        assert soh == {branch_a.id: Decimal("0"), branch_b.id: Decimal("5")}

    def test_sin_ninguna_que_venda_sigue_siendo_catalogo_global(self, client, db, org, hq_branch, auth_admin_sin_sucursal):
        r = client.post("/api/products/", json=_cuerpo("HQ-3"), headers=_h(auth_admin_sin_sucursal, org))
        assert r.status_code == 200, r.text
        v = db.query(ProductVariant).filter(ProductVariant.sku == "HQ-3").one()
        assert db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == v.id).count() == 0


class TestValidacionesNuevas:
    def test_escalon_en_cero_tambien_se_rechaza_en_el_alta(self, client, db, org, branch_a, auth_admin):
        r = client.post("/api/products/", json=_cuerpo(
            "ESC-1", target_branch_ids=[branch_a.id],
            prices=[{"price_name": "Caja", "min_quantity": 12, "unit_price": 0}],
        ), headers=_h(auth_admin, org))
        assert r.status_code == 422, r.text
        assert "Caja" in r.json()["detail"]
        assert db.query(ProductVariant).filter(ProductVariant.sku == "ESC-1").count() == 0
        assert db.query(ProductPrice).count() == 0


class TestModuloCatalogo:
    def test_cajero_sin_modulo_catalog_es_403(self, client, org, cajero_a, auth_cajero_a):
        r = client.post("/api/products/", json=_cuerpo("CAJ-1"), headers=_h(auth_cajero_a, org))
        assert r.status_code == 403, r.text
        assert "catalog" in r.json()["detail"]

    def test_cajero_con_modulo_crea(self, client, org, catalog_module_enabled, cajero_a, auth_cajero_a):
        r = client.post("/api/products/", json=_cuerpo("CAJ-2"), headers=_h(auth_cajero_a, org))
        assert r.status_code == 200, r.text


class TestHandlerDelgado:
    def test_create_product_cabe_en_40_lineas(self):
        from app.modules.products.router.core import create_product
        assert len(inspect.getsource(create_product).splitlines()) < 40
```

- [ ] **Step 3: Correr para ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_altas_crear_producto.py`
Expected: fallan `test_mayusculas_distintas_es_409` (200), `test_sku_de_producto_archivado_es_409_y_lo_dice` (200), `test_sku_con_espacios_se_guarda_recortado` (sku con espacios), `test_queda_habilitado_en_todas_las_que_venden` (0 PBS), `test_con_existencia_y_varias_que_venden_pide_sucursal` (200), `test_escalon_en_cero_tambien_se_rechaza_en_el_alta` (200), `test_cajero_sin_modulo_catalog_es_403` (200), `test_create_product_cabe_en_40_lineas` (~360 líneas). Pasan `test_sin_ninguna_que_venda…` y `test_cajero_con_modulo_crea`.

- [ ] **Step 4: Crear `services/productos.py` con `crear_producto`**

```python
"""Crear, actualizar y duplicar productos: el cuerpo que antes vivía en
`router/core.py` (create_product, update_product, duplicate_product).

Reglas: sin `commit` (el handler confirma); `HTTPException` con los mismos
textos de siempre; toda consulta acotada a `org_id`.
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.crud.products import _is_admin
from app.models import Product, ProductVariant, User
from app.models.platform import PlatformAuditLog
from app.modules.products.schemas import ProductCreate
from app.modules.products.variant_label import variant_label
from app.services.barcodes import AsignadorDeCodigos

from .codigos import asignar_barcode_interno, validar_barcode_libre, validar_sku_unico
from .comun import MANAGER_ROLES
from .precios import armar_empaques, armar_escalones
from .sucursales import (
    armar_estado_por_sucursal, registrar_stock_inicial, resolver_sucursales_destino,
    sucursal_de_existencia_inicial,
)
from .validaciones import (
    atributos_principal, exigir_campos_de_cajero, validar_departamento_y_marca,
    validar_escalones, validar_precio, validar_sucursales_de_la_org,
)

_AMBIGUO = "Indica en qué sucursal entra la existencia inicial: no se reparte sola entre varias sucursales."


def _validar_destinos_y_rol(db: Session, org_id: int, user: User, datos: ProductCreate, es_admin: bool) -> None:
    """RBAC de sucursales: solo ADMIN/GERENTE/DUEÑO habilitan en varias; un
    usuario con sucursal (no admin) solo en la suya; toda sucursal de la org."""
    objetivo = datos.target_branch_ids or []
    if len(objetivo) > 1 and user.role not in MANAGER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Solo administradores pueden habilitar productos en múltiples sucursales",
        )
    if not es_admin and user.branch_id and objetivo:
        for bid in objetivo:
            if bid != user.branch_id:
                raise HTTPException(
                    status_code=403,
                    detail="Solo puedes crear productos para tu sucursal asignada.",
                )
    validar_sucursales_de_la_org(db, org_id, objetivo)


def _validar_existencia_inicial(user: User, datos: ProductCreate, destinos: list[int]) -> None:
    """La existencia inicial entra en UNA sucursal. Con varias objetivo y sin
    `branch_id` no hay forma de saber cuál: se rechaza en vez de repartir a
    ciegas. Cuenta también la de las hermanas (`extra_variants`)."""
    total = (datos.initial_stock or Decimal(0)) + sum(
        (v.initial_stock or Decimal(0)) for v in (datos.extra_variants or [])
    )
    if total <= 0:
        return
    objetivo = set(datos.target_branch_ids or [])
    if len(objetivo) > 1 and datos.branch_id not in objetivo:
        raise HTTPException(status_code=422, detail=_AMBIGUO)
    # Usuario sin sucursal y sin destinos: el alta lo habilita en todas las
    # que venden; con piezas y más de una, hay que decir en cuál.
    if not objetivo and not user.branch_id and len(destinos) > 1 and datos.branch_id not in destinos:
        raise HTTPException(status_code=422, detail=_AMBIGUO)


def _auditar_alta_de_cajero(db: Session, user: User, producto: Product, principal: ProductVariant) -> None:
    """D4 — CAJERO/GERENTE creó un producto para su propia sucursal."""
    db.add(PlatformAuditLog(
        actor_user_id=user.id,
        action="PRODUCT_CREATE_CAJERO",
        entity_type="Product",
        entity_id=str(producto.id),
        payload=json.dumps({
            "branch_id": user.branch_id,
            "sku": principal.sku,
            "name": producto.name,
            "variant_id": str(principal.id),
        }),
    ))


def crear_producto(
    db: Session, org_id: int, user: User, datos: ProductCreate, *,
    asignador: Optional[AsignadorDeCodigos] = None,
    is_active_hq: bool = False,
    kardex: tuple[str, str] = ("Alta Inicial", "Creación de producto"),
) -> Product:
    """Alta completa: producto + variante principal (+ hermanas), código
    interno, estado por sucursal, existencia inicial, empaques y escalones.

    `asignador`/`is_active_hq`/`kardex` los pasa la importación (un asignador
    por archivo; HQ cotiza lo que importa; texto del kardex de siempre).
    Sin commit.
    """
    es_admin = _is_admin(user)
    if not es_admin:
        if not user.branch_id:
            raise HTTPException(
                status_code=403,
                detail="Solo usuarios con sucursal asignada pueden crear productos.",
            )
        exigir_campos_de_cajero(datos)
    validar_precio(datos.price)
    validar_escalones(datos.prices)
    sku = validar_sku_unico(db, org_id, datos.sku)
    _validar_destinos_y_rol(db, org_id, user, datos, es_admin)
    destinos = resolver_sucursales_destino(db, org_id, user, datos.target_branch_ids)
    _validar_existencia_inicial(user, datos, destinos)
    validar_departamento_y_marca(db, org_id, datos.department_id, datos.brand_id)
    barcode = validar_barcode_libre(db, org_id, datos.barcode)

    # approval_status: siempre APPROVED. CAJERO/GERENTE ven su producto al
    # instante; el workflow de aprobación está fuera de alcance hoy.
    producto = Product(
        name=datos.name,
        description=datos.description,
        unit=datos.unit or "pza",
        image_url=datos.image_url or None,
        department_id=datos.department_id,
        brand_id=datos.brand_id,
        gender=datos.gender,   # ya normalizado por el schema
        model=(datos.model or "").strip() or None,
        material=(datos.material or "").strip() or None,
        has_variants=True,
        is_active=True,
        approval_status="APPROVED",
        created_by_user_id=user.id,
        organization_id=org_id,
    )
    db.add(producto)
    db.flush()

    # La principal ES la primera combinación color/talla (matriz boutique);
    # sin atributos, "Estándar".
    color, size = atributos_principal(datos.color, datos.size)
    principal = ProductVariant(
        product_id=producto.id,
        sku=sku,
        barcode=barcode,
        color=color,
        size=size,
        variant_name=variant_label(color, size),
        price=datos.price,
        cost=datos.cost,
        has_iva=datos.has_iva,
        tax_rate=datos.tax_rate,
        organization_id=org_id,
    )
    db.add(principal)
    db.flush()
    asignar_barcode_interno(db, org_id, principal, asignador)

    destino_stock = sucursal_de_existencia_inicial(user, datos.branch_id, destinos)
    registrar_stock_inicial(
        db, org_id, principal, destinos, destino_stock, datos.initial_stock or Decimal(0),
        user.id, referencia=kardex[0], notas=kardex[1],
    )
    armar_estado_por_sucursal(db, org_id, principal, destinos, is_active_hq=is_active_hq)
    mapa = armar_empaques(db, org_id, principal, datos.packaging_units)
    armar_escalones(db, org_id, principal, datos.prices, mapa)
    if not es_admin:
        _auditar_alta_de_cajero(db, user, producto, principal)

    if datos.extra_variants:
        # Import perezoso: hasta la Task 6 `crear_variantes` vive en el router
        # (router importa services; al revés cerraría el ciclo al cargar).
        from app.modules.products.router.variants import crear_variantes
        crear_variantes(db, org_id, producto, datos.extra_variants,
                        stock_branch_id=destino_stock, user_id=user.id, asignador=asignador)
    db.flush()
    return producto
```

Agrega a `services/__init__.py`: `from .productos import crear_producto  # noqa: F401`.

- [ ] **Step 5: Dejar `create_product` delgado y con `require_module`**

En `app/modules/products/router/core.py` añade a los imports:

```python
from sqlalchemy.exc import IntegrityError
from app.core.permissions import require_module
from app.modules.products.services import crear_producto
```

y **reemplaza completo** el handler (desde `@router.post("/", response_model=ProductRead)` hasta el `raise` final del `except Exception as e`, líneas 190–545) por:

```python
@router.post("/", response_model=ProductRead,
             dependencies=[Depends(require_module("catalog"))])
def create_product(
    prod_in: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Alta de producto. La lógica vive en `services.crear_producto`; aquí
    solo se confirma la transacción y se serializa la respuesta."""
    try:
        producto = crear_producto(db, org_id, current_user, prod_in)
        db.commit()
    except HTTPException:
        raise
    except IntegrityError as e:
        db.rollback()
        if "product_variants" in str(e) and "sku" in str(e):
            raise HTTPException(
                status_code=409,
                detail=f"El SKU '{prod_in.sku}' ya existe en esta organización.",
            )
        raise
    except Exception:
        db.rollback()
        raise
    db.refresh(producto)
    return _compute_product_read(producto, db, current_user, target_branch_id=current_user.branch_id)
```

Deja `_atributos_principal` y los demás imports de `core.py` como están (los sigue usando `update_product` hasta la Task 8).

- [ ] **Step 6: Ajustar `test_admin_creates_global_product`**

En `tests/test_product_creation.py` reemplaza la prueba `test_admin_creates_global_product` (clase `TestProductCreationScope`) por:

```python
    def test_admin_sin_sucursal_y_sin_ninguna_que_venda_crea_catalogo_global(
        self, client, db, catalog_module_enabled, org, hq_branch,
        admin_no_branch, auth_admin_nobranch,
    ):
        """Sin `target_branch_ids` el alta habilita en todas las sucursales que
        venden (mega plan 2026-10 §6.4). Si la org no tiene ninguna que venda
        (solo HQ con can_sell=False), no hay PBS y el OUTER JOIN de ATS-11 lo
        muestra en todas, como siempre."""
        r = client.post(
            "/api/products/", json=_payload(sku="G-1"),
            headers=_with_org(auth_admin_nobranch, org),
        )
        assert r.status_code == 200, r.text
        variant = db.query(ProductVariant).filter(ProductVariant.sku == "G-1").first()
        assert variant is not None
        pbs = db.query(ProductBranchStatus).filter(
            ProductBranchStatus.variant_id == variant.id
        ).all()
        assert len(pbs) == 0
```

- [ ] **Step 7: Correr las nuevas y toda la red de productos**

Run: `python3 -m pytest -q -p no:warnings tests/test_altas_crear_producto.py tests/test_product_creation.py tests/test_variant_endpoints.py tests/test_variant_principal_con_talla.py tests/test_barcodes.py tests/test_sale_name.py tests/test_admin_catalog_regression.py tests/test_admin_catalog_advanced.py tests/test_import_export_variantes.py`
Expected: todas passed. Si falla `test_cajero_sin_modulo_catalog_es_403` con 200, el `dependencies=[...]` no quedó en el decorador. Si `test_product_visible_in_own_branch_pos_search` falla, revisa que `armar_estado_por_sucursal` haga `flush` (el POS busca por PBS).

- [ ] **Step 8: Suite completa**

Run: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py`
Expected: mismo número de `failed` que en `main` (hoy 0 según la memoria del 2026-09-28: el baseline rojo de CLAUDE.md ya no existe). Si sube, el culpable es de esta tarea.

- [ ] **Step 9: Commit**

```bash
git add app/modules/products/services/ app/modules/products/router/core.py tests/conftest.py tests/test_product_creation.py tests/test_admin_catalog_regression.py tests/test_altas_crear_producto.py
git commit -m "feat(productos): crear_producto en services/, create_product delgado y require_module(catalog)"
```

---
### Task 6: mudar `crear_variantes` a `services/variantes.py`

**Files:**
- Create: `app/modules/products/services/variantes.py`
- Modify: `app/modules/products/router/variants.py:1-240` (se quitan `_slug`, `_sku_generado`, `_sku_en_uso`, `_barcode_en_uso`, `_atributos`, `_pareja_repetida`, `crear_variantes`; se importan desde services con alias)
- Modify: `app/modules/products/services/productos.py` (import directo en vez del perezoso), `app/modules/products/services/__init__.py`
- Test: `tests/test_altas_variantes_servicio.py`

**Interfaces:**
- Consumes: Tasks 1–3; `ProductVariantCreate` (schemas); `COLOR_MAX`, `SIZE_MAX`, `clean_attr`, `variant_label`.
- Produces: `variantes.crear_variantes(db, org_id, producto, entradas: list[ProductVariantCreate], principal_id: Optional[str] = None, stock_branch_id: Optional[int] = None, user_id: Optional[int] = None, asignador: Optional[AsignadorDeCodigos] = None) -> list[ProductVariant]` (misma firma de hoy), `variantes.sku_generado(base, color, size) -> str`, `variantes.pareja_repetida(producto, color, size, excepto_id=None) -> bool`, `variantes.atributos(color, size, contexto) -> tuple`. El router `variants.py` re-exporta `crear_variantes`, `_pareja_repetida`, `_sku_en_uso`, `_atributos` (los usan `core.py` hasta la Task 8 e `import_export.py` hasta la Task 9).

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_altas_variantes_servicio.py`:

```python
"""`crear_variantes` vive en services y usa la misma regla de SKU que el alta."""
from datetime import datetime, timezone
from decimal import Decimal

from conftest import _make_product
from app.models.products import ProductVariant
from app.services.barcodes import es_codigo_interno


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


class TestCrearVariantesDesdeServicio:
    def test_el_router_reexporta_la_misma_funcion(self):
        from app.modules.products.router import variants as router_variants
        from app.modules.products.services import variantes
        assert router_variants.crear_variantes is variantes.crear_variantes
        assert router_variants._pareja_repetida is variantes.pareja_repetida

    def test_sku_generado_que_choca_con_uno_archivado_es_409(self, client, db, org, branch_a, auth_admin):
        p, _ = _make_product(db, org, "Playera", "PLY", 100, [(branch_a.id, True)])
        p2, v2 = _make_product(db, org, "Vieja", "PLY-ROJO-M", 100, [(branch_a.id, True)])
        ahora = datetime.now(timezone.utc)
        p2.deleted_at = ahora; p2.is_active = False; v2.deleted_at = ahora
        db.flush()
        r = client.post(f"/api/products/{p.id}/variants",
                        json={"variants": [{"color": "Rojo", "size": "M"}]},
                        headers=_h(auth_admin, org))
        assert r.status_code == 409, r.text
        assert "archivado" in r.json()["detail"]
        assert db.query(ProductVariant).filter(ProductVariant.product_id == p.id).count() == 1

    def test_hermana_recibe_codigo_interno_y_kardex_de_variante(self, client, db, org, branch_a, auth_admin):
        from app.models.inventory import InventoryMovement
        p, _ = _make_product(db, org, "Playera", "PLY2", 100, [(branch_a.id, True)])
        db.flush()
        r = client.post(f"/api/products/{p.id}/variants",
                        json={"variants": [{"color": "Azul", "size": "L", "initial_stock": "2"}]},
                        headers=_h(auth_admin, org))
        assert r.status_code == 201, r.text
        nueva = db.query(ProductVariant).filter(ProductVariant.sku == "PLY2-AZUL-L").one()
        assert es_codigo_interno(org.id, nueva.barcode)
        mov = db.query(InventoryMovement).filter(InventoryMovement.variant_id == nueva.id).one()
        assert (mov.qty_change, mov.reference, mov.notes) == (Decimal("2"), "Alta Inicial", "Creación de variante")
```

- [ ] **Step 2: Correr para ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_altas_variantes_servicio.py`
Expected: FAIL en la colección (`ModuleNotFoundError: ...services.variantes`).

- [ ] **Step 3: Crear `services/variantes.py`** (cuerpo de `crear_variantes` tal cual estaba en `router/variants.py:120-240`, con los helpers de services):

```python
"""Variantes de color/talla (preset boutique): creación de hermanas.

`create_product` delega aquí para `extra_variants`, `POST /{id}/variants`
para la matriz y la importación para las filas con Color/Talla de un producto
ya creado en la misma carga. Sin commit: lo hace el caller.
"""
from __future__ import annotations

import logging
import unicodedata
from decimal import Decimal
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Product, ProductBranchStatus, ProductVariant
from app.modules.products.schemas import ProductVariantCreate
from app.modules.products.variant_label import COLOR_MAX, SIZE_MAX, clean_attr, variant_label
from app.services.barcodes import AsignadorDeCodigos

from .codigos import asignar_barcode_interno, validar_barcode_libre, validar_sku_unico
from .sucursales import registrar_stock_inicial

logger = logging.getLogger(__name__)


def _slug(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "".join(c for c in sin_acentos.upper() if c.isalnum())


def sku_generado(base: str, color: Optional[str], size: Optional[str]) -> str:
    """`PLY` + Rojo + M -> `PLY-ROJO-M`."""
    partes = [base] + [_slug(x) for x in (color, size) if x]
    return "-".join(partes)


def atributos(color: Optional[str], size: Optional[str], contexto: str) -> tuple[Optional[str], Optional[str]]:
    """Limpia/valida color+talla o levanta 422 con `contexto` en el detalle
    (p. ej. "variants[0]" en el alta, "variante <id>" en la edición)."""
    try:
        return clean_attr(color, COLOR_MAX), clean_attr(size, SIZE_MAX)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"{contexto}: color/talla {e}")


def pareja_repetida(producto: Product, color: Optional[str], size: Optional[str],
                    excepto_id: Optional[str] = None) -> bool:
    clave = ((color or "").lower(), (size or "").lower())
    for v in producto.variants:
        if v.deleted_at is not None or v.id == excepto_id:
            continue
        if ((v.color or "").lower(), (v.size or "").lower()) == clave:
            return True
    return False


def crear_variantes(
    db: Session, org_id: int, producto: Product, entradas: List[ProductVariantCreate],
    principal_id: Optional[str] = None,
    stock_branch_id: Optional[int] = None,
    user_id: Optional[int] = None,
    asignador: Optional[AsignadorDeCodigos] = None,
) -> List[ProductVariant]:
    """Crea variantes hermanas de la principal. Sin commit: lo hace el caller.

    Cada variante nueva hereda precio/costo/IVA de la principal si no los trae,
    y se habilita (PBS) con existencia 0 en las mismas sucursales donde ya está
    la principal, para que aparezca en el POS de inmediato.

    `principal_id`: fija cuál variante es la principal en vez de tomar la
    primera de `producto.variants` (orden no garantizado una vez que el
    producto ya tiene más de una variante — p. ej. la carga masiva por fila).

    `initial_stock` de cada entrada aterriza en `stock_branch_id` (o en la
    única sucursal habilitada, si solo hay una) con su movimiento de apertura.
    """
    if principal_id is not None:
        principal = next(v for v in producto.variants if v.id == principal_id and v.deleted_at is None)
    else:
        principal = next(v for v in producto.variants if v.deleted_at is None)
    pbs_base = db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == principal.id).all()
    if not pbs_base:
        logger.warning(
            "crear_variantes: la variante principal %s no tiene ProductBranchStatus; "
            "las variantes hermanas nacen sin PBS/stock por sucursal.",
            principal.id,
        )
    sucursales = [pbs.branch_id for pbs in pbs_base]
    destino_stock: Optional[int] = None
    if stock_branch_id is not None and stock_branch_id in sucursales:
        destino_stock = stock_branch_id
    elif stock_branch_id is None and len(sucursales) == 1:
        destino_stock = sucursales[0]

    nuevas: List[ProductVariant] = []
    vistos: set[tuple[str, str]] = set()
    for i, e in enumerate(entradas):
        color, size = atributos(e.color, e.size, f"variants[{i}]")
        if not color and not size:
            raise HTTPException(status_code=422, detail=f"variants[{i}]: indica color o talla")
        clave = ((color or "").lower(), (size or "").lower())
        if clave in vistos or pareja_repetida(producto, color, size):
            raise HTTPException(status_code=409, detail=f"Ya existe la variante {variant_label(color, size)}")
        vistos.add(clave)

        if e.price is not None and e.price <= 0:
            raise HTTPException(status_code=422, detail=f"variants[{i}]: el precio debe ser mayor a cero.")

        qty_inicial = Decimal(e.initial_stock or 0)
        if qty_inicial < 0:
            raise HTTPException(status_code=422, detail=f"variants[{i}]: la existencia inicial no puede ser negativa.")
        if qty_inicial > 0 and destino_stock is None:
            raise HTTPException(
                status_code=422,
                detail="Indica en qué sucursal entra la existencia inicial de las variantes.",
            )

        # Misma regla de SKU que el alta: sin mayúsculas e incluyendo archivados.
        sku = validar_sku_unico(db, org_id, (e.sku or "").strip() or sku_generado(principal.sku, color, size))
        barcode = validar_barcode_libre(db, org_id, e.barcode)

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
        # Cada talla necesita su propio código o la etiquetadora no distingue
        # las piezas en el anaquel; el flush de arriba lo deja visible para la
        # siguiente vuelta, así que no se repiten entre hermanas.
        asignar_barcode_interno(db, org_id, v, asignador)
        # Hereda las banderas por sucursal de la principal (no los defaults).
        for pbs in pbs_base:
            db.add(ProductBranchStatus(
                variant_id=v.id, branch_id=pbs.branch_id, organization_id=org_id,
                is_active_pos=pbs.is_active_pos, is_active_hq=pbs.is_active_hq, is_visible=pbs.is_visible,
            ))
        registrar_stock_inicial(db, org_id, v, sucursales, destino_stock, qty_inicial, user_id,
                                notas="Creación de variante")
        nuevas.append(v)
    producto.has_variants = True
    db.flush()
    return nuevas
```

- [ ] **Step 4: Dejar el router `variants.py` como consumidor**

En `app/modules/products/router/variants.py`:

1. Reemplaza el bloque de imports de barcodes/`_shared` y los helpers privados (desde `def _exigir_rol_avanzado` **no** — ese se queda; quita `_slug`, `_sku_generado`, `_sku_en_uso`, `_barcode_en_uso = barcode_en_uso`, `_atributos`, `_pareja_repetida` y la función completa `crear_variantes`, líneas 50–240 salvo `_exigir_rol_avanzado`, `_producto_de_la_org`, `_variante_de_la_org`) y agrega, junto a los demás imports:

```python
from app.modules.products.services.codigos import sku_en_uso as _sku_en_uso, validar_barcode_libre
from app.modules.products.services.variantes import (  # noqa: F401  (re-export para core/import_export)
    atributos as _atributos,
    crear_variantes,
    pareja_repetida as _pareja_repetida,
)
```

2. En `editar_variante`, el bloque del código de barras pasa a usar el helper (mismo 409):

```python
    if "barcode" in enviados:
        v.barcode = validar_barcode_libre(db, org_id, body.barcode, excepto_id=v.id)
```

3. Quita de los imports lo que quede sin uso (`unicodedata`, `Decimal`, `func`, `InventoryMovement`, `MovementType`, `StockOnHand`, `ProductVariantCreate`, `COLOR_MAX`, `SIZE_MAX`, `clean_attr`, `AsignadorDeCodigos`, `barcode_en_uso`, `siguiente_codigo_interno`). Verifica cada uno con `grep -n "<nombre>" app/modules/products/router/variants.py` antes de quitarlo; `variant_label` y `ProductVariant` siguen en uso.

4. En `app/modules/products/services/productos.py` sustituye el import perezoso dentro de `crear_producto` por un import de módulo: `from .variantes import crear_variantes` (arriba, junto a los demás), y borra el comentario de "Import perezoso".

5. En `services/__init__.py`: `from .variantes import atributos, crear_variantes, pareja_repetida, sku_generado  # noqa: F401`.

- [ ] **Step 5: Correr**

Run: `python3 -m pytest -q -p no:warnings tests/test_altas_variantes_servicio.py tests/test_variant_endpoints.py tests/test_variant_principal_con_talla.py tests/test_barcodes.py tests/test_import_export_variantes.py tests/test_altas_crear_producto.py tests/test_product_creation.py`
Expected: todas passed. Nota: `test_rechaza_pareja_repetida_y_sku_duplicado` (variant_endpoints) sigue pasando porque `validar_sku_unico` da 409 con SKU "PLY" repetido.

- [ ] **Step 6: Commit**

```bash
git add app/modules/products/services/ app/modules/products/router/variants.py tests/test_altas_variantes_servicio.py
git commit -m "refactor(productos): crear_variantes en services/variantes.py con la regla unica de SKU"
```

> **Fin del Paso 1 de despliegue** (ver sección "Despliegue en dos pasos" al final): con las Tasks 1–6 la suite está verde y producción solo cambia en el alta (`POST /`, variantes). Se puede desplegar aquí antes de seguir.

---

### Task 7: `duplicar_producto` — conserva color/talla, asigna código, ignora retiradas

**Files:**
- Modify: `app/modules/products/services/productos.py` (añadir `duplicar_producto`)
- Modify: `app/modules/products/router/core.py:841-976` (`duplicate_product`)
- Modify: `app/modules/products/services/__init__.py`
- Modify: `tests/test_admin_catalog_advanced.py:141-152` (`TestDuplicateProduct::test_cajero_allowed`)
- Test: `tests/test_altas_duplicar.py`

**Interfaces:**
- Consumes: `sku_de_copia`, `asignar_barcode_interno` (Task 1); `copiar_estado_por_sucursal` (Task 3); `variantes_vivas` (Task 2); `PackagingUnit`, `ProductPrice` (`app.models`).
- Produces: `duplicar_producto(db, org_id: int, user: User, product_id: str) -> Product` — 404 si no existe en la org; 409 si no tiene variantes vivas; sin commit.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_altas_duplicar.py`:

```python
"""POST /api/products/{id}/duplicate por `services.duplicar_producto`.

Bugs cerrados (spec §2.1): la copia perdía color/talla, nacía sin código de
barras y recorría también las variantes retiradas.
"""
import inspect
from datetime import datetime, timezone
from decimal import Decimal

from conftest import _make_product
from app.models.products import PackagingUnit, Product, ProductPrice, ProductVariant
from app.services.barcodes import es_codigo_interno


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


class TestDuplicar:
    def test_conserva_color_y_talla_y_asigna_codigo(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Playera", "PLY-R-M", 100, [(branch_a.id, True)])
        v.color, v.size, v.variant_name = "Rojo", "M", "Rojo / M"
        v.barcode = "7500000000011"
        db.flush()
        r = client.post(f"/api/products/{p.id}/duplicate", headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        assert r.json()["sku"] == "PLY-R-M-COPY-1"
        copia = db.query(ProductVariant).filter(ProductVariant.sku == "PLY-R-M-COPY-1").one()
        assert (copia.color, copia.size, copia.variant_name) == ("Rojo", "M", "Rojo / M")
        assert es_codigo_interno(org.id, copia.barcode)
        assert copia.barcode != v.barcode

    def test_no_copia_variantes_retiradas(self, client, db, org, branch_a, auth_admin):
        p, _ = _make_product(db, org, "Playera", "PLY-2", 100, [(branch_a.id, True)])
        db.add(ProductVariant(
            product_id=p.id, sku="PLY-2-L", price=Decimal("100"), cost=Decimal("50"),
            organization_id=org.id, deleted_at=datetime.now(timezone.utc),
        ))
        db.flush()
        r = client.post(f"/api/products/{p.id}/duplicate", headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        copia = db.get(Product, r.json()["id"])
        assert [x.sku for x in copia.variants] == ["PLY-2-COPY-1"]

    def test_copia_empaques_y_escalones_enlazados(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Refresco", "REF-1", 10, [(branch_a.id, True)])
        caja = PackagingUnit(variant_id=v.id, name="Caja", barcode="CAJA-1", units_per_package=Decimal("24"),
                             package_price=Decimal("200"), organization_id=org.id)
        db.add(caja); db.flush()
        db.add(ProductPrice(variant_id=v.id, price_name="Caja", min_quantity=Decimal("24"),
                            unit_price=Decimal("8"), linked_package_id=caja.id, organization_id=org.id))
        db.flush()
        r = client.post(f"/api/products/{p.id}/duplicate", headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        nueva = db.query(ProductVariant).filter(ProductVariant.sku == "REF-1-COPY-1").one()
        pkg = db.query(PackagingUnit).filter(PackagingUnit.variant_id == nueva.id).one()
        assert (pkg.name, pkg.barcode) == ("Caja", None)   # el barcode del empaque no se copia (único)
        precio = db.query(ProductPrice).filter(ProductPrice.variant_id == nueva.id).one()
        assert precio.linked_package_id == pkg.id

    def test_sin_variantes_vivas_es_409(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Vacía", "VAC-1", 100, [(branch_a.id, True)])
        v.deleted_at = datetime.now(timezone.utc)
        db.flush()
        r = client.post(f"/api/products/{p.id}/duplicate", headers=_h(auth_admin, org))
        assert r.status_code == 409, r.text
        assert db.query(Product).filter(Product.name == "Vacía (copia)").count() == 0

    def test_cajero_sin_modulo_catalog_es_403(self, client, org, products_setup, auth_cajero_a):
        product, _ = products_setup["product_a"]
        r = client.post(f"/api/products/{product.id}/duplicate", headers=_h(auth_cajero_a, org))
        assert r.status_code == 403, r.text
        assert "catalog" in r.json()["detail"]

    def test_duplicate_product_cabe_en_40_lineas(self):
        from app.modules.products.router.core import duplicate_product
        assert len(inspect.getsource(duplicate_product).splitlines()) < 40
```

- [ ] **Step 2: Correr para ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_altas_duplicar.py`
Expected: fallan `test_conserva_color_y_talla_y_asigna_codigo` (color None / barcode None), `test_no_copia_variantes_retiradas` (2 SKUs), `test_sin_variantes_vivas_es_409` (200), `test_cajero_sin_modulo_catalog_es_403` (200), `test_duplicate_product_cabe_en_40_lineas`. `test_copia_empaques_y_escalones_enlazados` ya pasa (ese comportamiento se conserva).

- [ ] **Step 3: Añadir `duplicar_producto` a `services/productos.py`**

Imports adicionales en `productos.py`:

```python
from app.models import PackagingUnit, ProductPrice
from .codigos import sku_de_copia
from .comun import variantes_vivas
from .sucursales import copiar_estado_por_sucursal
```

Función (al final del archivo):

```python
def duplicar_producto(db: Session, org_id: int, user: User, product_id: str) -> Product:
    """Copia producto + variantes VIVAS (SKU `-COPY-<n>`, código interno
    nuevo, color/talla), empaques (sin barcode), escalones y estado por
    sucursal. NO copia StockOnHand: la copia arranca sin existencias."""
    origen = db.query(Product).filter(
        Product.id == product_id, Product.organization_id == org_id,
    ).first()
    if origen is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    vivas = variantes_vivas(origen)
    if not vivas:
        raise HTTPException(status_code=409, detail="El producto no tiene variantes vivas que duplicar.")

    copia = Product(
        name=f"{origen.name} (copia)",
        description=origen.description,
        unit=origen.unit,
        image_url=origen.image_url,
        department_id=origen.department_id,
        brand_id=origen.brand_id,
        # Ficha boutique: la copia es la misma prenda, con su género, modelo
        # y material — si no, su nombre de venta sale distinto.
        gender=origen.gender,
        model=origen.model,
        material=origen.material,
        has_variants=origen.has_variants,
        is_active=True,
        approval_status="APPROVED",
        created_by_user_id=user.id,
        organization_id=org_id,
    )
    db.add(copia)
    db.flush()

    asignador = AsignadorDeCodigos(db, org_id)
    for v in vivas:
        nueva = ProductVariant(
            product_id=copia.id,
            sku=sku_de_copia(db, org_id, v.sku),
            barcode=None,                  # único por org: se genera uno interno abajo
            color=v.color,
            size=v.size,
            variant_name=v.variant_name,
            price=v.price,
            cost=v.cost,
            has_iva=v.has_iva,
            tax_rate=v.tax_rate,
            organization_id=org_id,
        )
        db.add(nueva)
        db.flush()
        asignar_barcode_interno(db, org_id, nueva, asignador)

        mapa_empaques: dict[str, str] = {}
        for pkg in (v.packaging_units or []):
            nuevo_pkg = PackagingUnit(
                variant_id=nueva.id,
                name=pkg.name,
                barcode=None,
                units_per_package=pkg.units_per_package,
                package_price=pkg.package_price,
                weight=pkg.weight,
                dimensions=pkg.dimensions,
                organization_id=org_id,
            )
            db.add(nuevo_pkg)
            db.flush()
            mapa_empaques[pkg.id] = nuevo_pkg.id
        for pr in (v.prices or []):
            db.add(ProductPrice(
                variant_id=nueva.id,
                price_name=pr.price_name,
                min_quantity=pr.min_quantity,
                unit_price=pr.unit_price,
                linked_package_id=mapa_empaques.get(pr.linked_package_id) if pr.linked_package_id else None,
                organization_id=org_id,
            ))
        copiar_estado_por_sucursal(db, org_id, v, nueva)
    db.flush()
    return copia
```

`services/__init__.py`: `from .productos import crear_producto, duplicar_producto  # noqa: F401`.

- [ ] **Step 4: Dejar `duplicate_product` delgado**

En `core.py` cambia el import a `from app.modules.products.services import crear_producto, duplicar_producto` y reemplaza el handler completo (líneas 841–976, desde `@router.post("/{product_id}/duplicate"` hasta el `return _compute_product_read(new_prod, ...)`) por:

```python
@router.post("/{product_id}/duplicate", response_model=ProductRead,
             dependencies=[Depends(require_module("catalog"))])
def duplicate_product(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Duplica un producto (ver `services.duplicar_producto`). Sin existencias."""
    # Track 3: cajero también puede duplicar productos visibles en su sucursal.
    if current_user.role not in _PRODUCT_ADVANCED_ROLES:
        raise HTTPException(status_code=403, detail="No autorizado")
    try:
        copia = duplicar_producto(db, org_id, current_user, product_id)
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        logger.exception("PRODUCT_DUPLICATE_FAILED product_id=%s org_id=%s", product_id, org_id)
        raise HTTPException(status_code=500, detail="Error al duplicar producto")
    db.refresh(copia)
    return _compute_product_read(copia, db, current_user, target_branch_id=current_user.branch_id)
```

- [ ] **Step 5: `test_cajero_allowed` pide el módulo**

En `tests/test_admin_catalog_advanced.py`, clase `TestDuplicateProduct`, cambia la firma de `test_cajero_allowed` a:

```python
    def test_cajero_allowed(
        self, client, products_setup, catalog_module_enabled, cajero_a, auth_cajero_a, org,
    ):
```

(el resto de la prueba igual; el comentario puede decir que desde SP1 el cajero además necesita el módulo `catalog`).

- [ ] **Step 6: Correr**

Run: `python3 -m pytest -q -p no:warnings tests/test_altas_duplicar.py tests/test_admin_catalog_advanced.py tests/test_sale_name.py`
Expected: todas passed (`test_la_copia_conserva_genero_modelo_y_material` y `test_duplicate_creates_copy_with_suffix` incluidas).

- [ ] **Step 7: Commit**

```bash
git add app/modules/products/services/ app/modules/products/router/core.py tests/test_admin_catalog_advanced.py tests/test_altas_duplicar.py
git commit -m "fix(productos): duplicar conserva color/talla, asigna codigo interno e ignora variantes retiradas"
```

---
### Task 8: `actualizar_producto` — 409 en SKU repetido y `PUT /{id}` delgado

**Files:**
- Modify: `app/modules/products/services/productos.py` (añadir `actualizar_producto`)
- Modify: `app/modules/products/router/core.py:983-1223` (`update_product`), borrar `_atributos_principal` (`:58-73`) y limpiar imports
- Modify: `app/modules/products/services/__init__.py`
- Test: `tests/test_altas_actualizar.py`

**Interfaces:**
- Consumes: Tasks 1–4 y 6 (`pareja_repetida`), `variante_principal`, `variantes_vivas` (Task 2); `ProductUpdate` (schemas); `ProductBranchStatus` (`app.models`).
- Produces: `actualizar_producto(db, org_id: int, user: User, product_id: str, datos: ProductUpdate) -> Product` — sin commit. El handler conserva el guard de rol (`_PRODUCT_ADVANCED_ROLES`).

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_altas_actualizar.py`:

```python
"""PUT /api/products/{id} por `services.actualizar_producto`.

Bug cerrado (spec §2.1): el SKU repetido respondía 400 con otro texto; ahora
409 con la misma regla que el alta (sin mayúsculas, incluye archivados).
"""
import inspect
from datetime import datetime, timezone

from conftest import _make_product
from app.models.products import ProductBranchStatus, ProductVariant


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


class TestSkuEnEdicion:
    def test_sku_de_otro_producto_es_409_no_400(self, client, db, org, branch_a, auth_admin):
        _make_product(db, org, "Uno", "UNO-1", 10, [(branch_a.id, True)])
        p2, _ = _make_product(db, org, "Dos", "DOS-1", 10, [(branch_a.id, True)])
        db.flush()
        r = client.put(f"/api/products/{p2.id}", json={"sku": "uno-1"}, headers=_h(auth_admin, org))
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == "El SKU 'uno-1' ya existe en esta organización."

    def test_sku_de_archivado_es_409_y_lo_dice(self, client, db, org, branch_a, auth_admin):
        p1, v1 = _make_product(db, org, "Vieja", "ARCH-1", 10, [(branch_a.id, True)])
        ahora = datetime.now(timezone.utc)
        p1.deleted_at = ahora; p1.is_active = False; v1.deleted_at = ahora
        p2, _ = _make_product(db, org, "Dos", "DOS-2", 10, [(branch_a.id, True)])
        db.flush()
        r = client.put(f"/api/products/{p2.id}", json={"sku": "ARCH-1"}, headers=_h(auth_admin, org))
        assert r.status_code == 409, r.text
        assert "archivado" in r.json()["detail"]

    def test_su_propio_sku_con_otra_caja_se_acepta(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Mío", "MIO-1", 10, [(branch_a.id, True)])
        db.flush()
        r = client.put(f"/api/products/{p.id}", json={"sku": " mio-1 "}, headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        db.refresh(v)
        assert v.sku == "mio-1"


class TestSucursalesEnEdicion:
    def test_sucursal_ajena_en_target_branch_ids_es_422(self, client, db, org, branch_a, auth_admin):
        from app.models.organization import Branch, BranchType, Organization
        otra = Organization(name="Otra", status="ACTIVE")
        db.add(otra); db.flush()
        ajena = Branch(name="Ajena", branch_type=BranchType.STORE, can_sell=True,
                       is_active=True, organization_id=otra.id)
        db.add(ajena); db.flush()
        p, v = _make_product(db, org, "P", "SUC-1", 10, [(branch_a.id, True)])
        db.flush()
        r = client.put(f"/api/products/{p.id}", json={"target_branch_ids": [ajena.id]}, headers=_h(auth_admin, org))
        assert r.status_code == 422, r.text
        assert r.json()["detail"] == "Una o más sucursales objetivo no pertenecen a tu organización."
        # Nada se borró: el PBS original sigue ahí.
        assert db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == v.id).count() == 1


class TestHandlerDelgado:
    def test_update_product_cabe_en_40_lineas(self):
        from app.modules.products.router.core import update_product
        assert len(inspect.getsource(update_product).splitlines()) < 40

    def test_core_ya_no_define_atributos_principal(self):
        from app.modules.products.router import core
        assert not hasattr(core, "_atributos_principal")
```

- [ ] **Step 2: Correr para ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_altas_actualizar.py`
Expected: fallan `test_sku_de_otro_producto_es_409_no_400` (400), `test_sku_de_archivado_es_409_y_lo_dice` (200), `test_su_propio_sku_con_otra_caja_se_acepta` (queda `" mio-1 "` sin recortar), `test_sucursal_ajena_en_target_branch_ids_es_422` (400), y los dos de `TestHandlerDelgado`.

- [ ] **Step 3: Añadir `actualizar_producto` a `services/productos.py`**

Imports adicionales:

```python
from app.models import ProductBranchStatus
from app.modules.products.schemas import ProductUpdate
from .comun import variante_principal
from .variantes import pareja_repetida
```

Función:

```python
def _principal_editable_por_cajero(db: Session, user: User, producto: Product) -> None:
    """CAJERO solo edita productos habilitados en su sucursal."""
    if user.role != "CAJERO":
        return
    if not user.branch_id:
        raise HTTPException(status_code=403, detail="CAJERO debe tener una sucursal asignada")
    variante = producto.variants[0] if producto.variants else None
    tiene_acceso = False
    if variante is not None:
        tiene_acceso = db.query(ProductBranchStatus).filter(
            ProductBranchStatus.variant_id == variante.id,
            ProductBranchStatus.branch_id == user.branch_id,
        ).first() is not None
    if not tiene_acceso:
        raise HTTPException(status_code=403, detail="No tienes acceso para editar este producto en tu sucursal")


def _editar_ficha(producto: Product, datos: ProductUpdate, enviados: set[str]) -> None:
    """`is not None` no distingue "no lo mandes" de "bórralo": un null explícito
    BORRA descripción/unidad/imagen/marca/departamento/género/modelo/material y
    no mandar el campo lo deja como está (`model_fields_set`). `name` es la
    excepción: un producto sin nombre no existe."""
    if datos.name is not None and datos.name.strip():
        producto.name = datos.name
    if "description" in enviados:
        producto.description = datos.description
    if "unit" in enviados:
        producto.unit = datos.unit
    if "image_url" in enviados:
        producto.image_url = (datos.image_url or "").strip() or None
    if "department_id" in enviados:
        producto.department_id = datos.department_id
    if "brand_id" in enviados:
        producto.brand_id = datos.brand_id
    if "gender" in enviados:
        producto.gender = datos.gender
    if "model" in enviados:
        producto.model = (datos.model or "").strip() or None
    if "material" in enviados:
        producto.material = (datos.material or "").strip() or None
    if datos.is_active is not None:
        producto.is_active = datos.is_active
    if datos.approval_status is not None:
        producto.approval_status = datos.approval_status


def _editar_principal(db: Session, org_id: int, producto: Product, v: ProductVariant,
                      datos: ProductUpdate, enviados: set[str]) -> None:
    if datos.sku is not None and datos.sku.strip() != v.sku:
        v.sku = validar_sku_unico(db, org_id, datos.sku, excepto_id=v.id)
    if "barcode" in enviados:
        # Tanto null como cadena vacía significan "quítalo".
        v.barcode = validar_barcode_libre(db, org_id, datos.barcode, excepto_id=v.id)
    if "color" in enviados or "size" in enviados:
        color, size = atributos_principal(
            datos.color if "color" in enviados else v.color,
            datos.size if "size" in enviados else v.size,
        )
        if pareja_repetida(producto, color, size, excepto_id=v.id):
            raise HTTPException(status_code=409, detail=f"Ya existe la variante {variant_label(color, size)}")
        v.color, v.size = color, size
        v.variant_name = variant_label(color, size)
    if datos.price is not None:
        v.price = datos.price
        # La casilla del formulario baja el precio nuevo a todas las tallas
        # vivas (las retiradas no).
        if datos.precio_a_todas_las_tallas:
            for hermana in variantes_vivas(producto):
                hermana.price = datos.price
    if datos.cost is not None:
        v.cost = datos.cost
    if datos.has_iva is not None:
        v.has_iva = datos.has_iva
    if datos.tax_rate is not None:
        v.tax_rate = datos.tax_rate


def actualizar_producto(db: Session, org_id: int, user: User, product_id: str, datos: ProductUpdate) -> Product:
    """Edición de ficha + variante principal (la primera VIVA) + empaques y
    escalones (reemplazo completo) + disponibilidad por sucursal (solo
    ADMIN/DUEÑO, reescribe el PBS de todas las variantes vivas). Sin commit."""
    validar_precio(datos.price, detalle="El precio debe ser mayor a cero.")
    validar_escalones(datos.prices)
    producto = db.query(Product).filter(
        Product.id == product_id, Product.organization_id == org_id,
    ).first()
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    _principal_editable_por_cajero(db, user, producto)

    enviados = datos.model_fields_set
    _editar_ficha(producto, datos, enviados)

    v = variante_principal(producto)
    if v is not None:
        _editar_principal(db, org_id, producto, v, datos, enviados)
        mapa: dict[str, str] = {}
        if datos.packaging_units is not None:
            mapa = armar_empaques(db, org_id, v, datos.packaging_units, reemplazar=True)
        if datos.prices is not None:
            armar_escalones(db, org_id, v, datos.prices, mapa, reemplazar=True)
        # Disponibilidad: CAJERO no la toca; lista vacía tampoco (borraría toda
        # la visibilidad). Se valida ANTES de borrar nada.
        if datos.target_branch_ids and user.role in ("ADMINISTRADOR", "DUEÑO"):
            vivas = variantes_vivas(producto)
            if vivas:
                destinos = sorted(validar_sucursales_de_la_org(db, org_id, datos.target_branch_ids))
                for variante in vivas:
                    armar_estado_por_sucursal(db, org_id, variante, destinos, reemplazar=True)
    db.flush()
    return producto
```

`services/__init__.py`: `from .productos import actualizar_producto, crear_producto, duplicar_producto  # noqa: F401`.

- [ ] **Step 4: Dejar `update_product` delgado y limpiar `core.py`**

En `core.py` cambia el import a `from app.modules.products.services import actualizar_producto, crear_producto, duplicar_producto` y reemplaza el handler completo (líneas 983–1223, desde `@router.put("/{product_id}", response_model=ProductRead)` hasta `return _compute_product_read(product, db, current_user)`) por:

```python
@router.put("/{product_id}", response_model=ProductRead,
            dependencies=[Depends(require_module("catalog"))])
def update_product(
    product_id: str,
    prod_in: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Edición de producto (ver `services.actualizar_producto`)."""
    if current_user.role not in _PRODUCT_ADVANCED_ROLES:
        raise HTTPException(status_code=403, detail="No autorizado")
    producto = actualizar_producto(db, org_id, current_user, product_id, prod_in)
    db.commit()
    db.refresh(producto)
    return _compute_product_read(producto, db, current_user)
```

Borra la función `_atributos_principal` (líneas 58–73). Luego limpia imports de `core.py` que quedaron sin uso; para cada nombre corre `grep -n "<nombre>" app/modules/products/router/core.py` y quítalo del `import` **solo si** la única aparición es la línea del import. Candidatos: `Decimal`, `InventoryMovement`, `MovementType`, `Department`, `ProductPrice`, `PackagingUnit`, `Brand`, `Branch`, `COLOR_MAX`, `SIZE_MAX`, `clean_attr`, `variant_label`, `barcode_en_uso`, `siguiente_codigo_interno`, `_MANAGER_ROLES`, `variante_principal`, `variantes_vivas`, `shutil`, `time`, `or_`. Se quedan seguro: `StockOnHand`, `ProductBranchStatus` (listado y delete), `ProductVariant`, `Product`, `sku_sugerido`, `_PRODUCT_ADVANCED_ROLES`, `_compute_product_read`, `image_storage`, `Path`.

- [ ] **Step 5: Correr toda la red de edición**

Run: `python3 -m pytest -q -p no:warnings tests/test_altas_actualizar.py tests/test_product_clear_fields.py tests/test_regresion_productos.py tests/test_tier_price_guard.py tests/test_precio_a_todas_las_tallas.py tests/test_variante_principal_viva.py tests/test_variant_principal_con_talla.py tests/test_barcodes.py tests/test_sale_name.py tests/test_admin_catalog_regression.py`
Expected: todas passed. `test_variante_principal_viva` (PBS reescrito para todas las vivas) y `test_product_clear_fields` (null explícito borra) son las que detectan un port incompleto.

- [ ] **Step 6: Suite completa**

Run: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py`
Expected: mismo `failed` que `main`.

- [ ] **Step 7: Commit**

```bash
git add app/modules/products/services/ app/modules/products/router/core.py tests/test_altas_actualizar.py
git commit -m "fix(productos): PUT responde 409 en SKU repetido y usa la regla unica; update_product delgado"
```

---
### Task 9: `importar_fila` — el upload usa el servicio fila por fila (guard de rol + módulo)

**Files:**
- Create: `app/modules/products/services/importacion.py`
- Modify: `app/modules/products/router/import_export.py:1-40` (imports, `_FilaInvalida`) y `:274-822` (`upload_products`)
- Modify: `app/modules/products/services/__init__.py`
- Test: `tests/test_altas_upload.py`

**Interfaces:**
- Consumes: `crear_producto` (Task 5), `crear_variantes`, `pareja_repetida` (Task 6), `armar_estado_por_sucursal`, `fijar_existencia` (Task 3), `validar_sucursales_de_la_org` (Task 2), `celda_*` (Task 2), `barcode_en_uso` (`app.services.barcodes`), `PackagingUnit`, `ProductPrice`, `Department`, `Brand` (`app.models`).
- Produces:
  - `importacion.FilaInvalida(Exception)` — fila rechazada por negocio.
  - `@dataclass importacion.ContextoImportacion(org_id, user, target_branch_id: Optional[int], sucursales: list[int], dept_map: dict[str,str], brand_map: dict[str,str], has_pkg_cols: bool, has_tier_cols: bool, asignador: AsignadorDeCodigos, productos_cargados: dict = {})`.
  - `@dataclass importacion.ResultadoFila(accion: str, sku: str, nombre: str, precio: Optional[float])` con `accion ∈ {"NEW","UPDATE","SKIP"}`.
  - `importacion.importar_fila(db, ctx: ContextoImportacion, fila: dict) -> ResultadoFila` — una fila completa (upsert por SKU, hermanas, habilitación, existencia, empaques, escalones). Levanta `FilaInvalida` o `HTTPException`; el router las convierte en fila fallida.
  - En el router: `_leer_filas(file) -> list[dict]`, `_contexto_de_carga(db, org_id, user, branch_id, target_branch_ids, scope, filas) -> ContextoImportacion`, `_procesar_filas(db, org_id, ctx, filas, dry_run) -> dict`, `_confirmar(db, hasta_fila: int) -> None` (helpers privados).

Comportamientos que **cambian a propósito** en esta tarea (documentados aquí porque son decisiones, no accidentes): (1) `target_branch_ids` mal formado o con sucursal ajena responde **400/422 de entrada** en vez de marcar cada fila como fallida; (2) la búsqueda del SKU existente es **sin mayúsculas** (`"ply-1"` actualiza `PLY-1` en vez de intentar crearlo y chocar); (3) una fila nueva crea `StockOnHand` en 0 en todas las sucursales donde queda habilitada (antes solo en la de destino) y queda habilitada (PBS) también en la sucursal donde entra su existencia; (4) un cajero que importa deja su fila `PRODUCT_CREATE_CAJERO` en `platform_audit_log` como en el alta manual.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_altas_upload.py`:

```python
"""POST /api/products/upload por `services.importacion.importar_fila`."""
import inspect
import io
from datetime import datetime, timezone
from decimal import Decimal

from conftest import _make_product
from app.models.inventory import StockOnHand
from app.models.products import ProductBranchStatus, ProductVariant
from app.services.barcodes import es_codigo_interno

CABECERAS = ["SKU", "Nombre", "Departamento", "Precio Base", "Costo", "Stock"]


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


def _csv(filas, cabeceras=CABECERAS):
    buf = io.StringIO()
    buf.write(",".join(cabeceras) + "\n")
    for f in filas:
        buf.write(",".join(str(f.get(c, "")) for c in cabeceras) + "\n")
    return buf.getvalue().encode("utf-8")


def _subir(client, auth, org, filas, cabeceras=CABECERAS, **form):
    return client.post(
        "/api/products/upload",
        headers=_h(auth, org),
        files={"file": ("catalogo.csv", _csv(filas, cabeceras), "text/csv")},
        data=form,
    )


def _fila(sku, **extra):
    base = {"SKU": sku, "Nombre": f"Prod {sku}", "Departamento": "General",
            "Precio Base": "10", "Costo": "5", "Stock": "1"}
    base.update(extra)
    return base


class TestGuardias:
    def test_vendedor_es_403(self, client, org, auth_vendedor_sin_sucursal):
        r = _subir(client, auth_vendedor_sin_sucursal, org, [_fila("V-1")])
        assert r.status_code == 403, r.text

    def test_cajero_sin_modulo_catalog_es_403(self, client, org, cajero_a, auth_cajero_a):
        r = _subir(client, auth_cajero_a, org, [_fila("C-1")])
        assert r.status_code == 403, r.text
        assert "catalog" in r.json()["detail"]

    def test_cajero_con_modulo_importa_a_su_sucursal(self, client, db, org, branch_a, catalog_module_enabled,
                                                     cajero_a, auth_cajero_a):
        r = _subir(client, auth_cajero_a, org, [_fila("C-2", Stock="2")])
        assert r.status_code == 200, r.text
        assert r.json()["created"] == 1 and r.json()["failed"] == 0
        v = db.query(ProductVariant).filter(ProductVariant.sku == "C-2").one()
        pbs = db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == v.id).one()
        assert (pbs.branch_id, pbs.is_active_pos, pbs.is_active_hq) == (branch_a.id, True, False)
        soh = db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).one()
        assert (soh.branch_id, soh.qty_on_hand) == (branch_a.id, Decimal("2"))

    def test_target_branch_ids_mal_formado_es_400_de_entrada(self, client, org, branch_a, auth_admin_sin_sucursal):
        r = _subir(client, auth_admin_sin_sucursal, org, [_fila("T-1")],
                   scope="selected", target_branch_ids="abc")
        assert r.status_code == 400, r.text


class TestFilaNueva:
    def test_pasa_por_crear_producto(self, client, db, org, hq_branch, admin_user, auth_admin):
        r = _subir(client, auth_admin, org, [_fila("N-1", Stock="3")])
        assert r.status_code == 200, r.text
        assert r.json() == {"created": 1, "updated": 0, "failed": 0, "pending": 0, "details": []}
        v = db.query(ProductVariant).filter(ProductVariant.sku == "N-1").one()
        assert es_codigo_interno(org.id, v.barcode)
        assert Decimal(str(v.tax_rate)) == Decimal("16")
        # admin_user tiene sucursal HQ: todo cae ahí, como siempre.
        pbs = db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == v.id).one()
        assert pbs.branch_id == hq_branch.id
        soh = db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).one()
        assert (soh.branch_id, soh.qty_on_hand) == (hq_branch.id, Decimal("3"))

    def test_sku_archivado_se_reporta_como_fila_fallida_accionable(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Vieja", "ARCH-1", 10, [(branch_a.id, True)])
        ahora = datetime.now(timezone.utc)
        p.deleted_at = ahora; p.is_active = False; v.deleted_at = ahora
        db.flush()
        r = _subir(client, auth_admin, org, [_fila("ARCH-1")])
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert (cuerpo["created"], cuerpo["failed"]) == (0, 1)
        assert "archivado" in cuerpo["details"][0]["error"]
        assert cuerpo["details"][0]["row"] == 2

    def test_sku_con_otra_caja_actualiza_en_vez_de_duplicar(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Playera", "PLY-1", 100, [(branch_a.id, True)])
        db.flush()
        r = _subir(client, auth_admin, org, [_fila("ply-1", **{"Precio Base": "120"})])
        assert r.status_code == 200, r.text
        assert (r.json()["created"], r.json()["updated"]) == (0, 1)
        db.refresh(v)
        assert Decimal(str(v.price)) == Decimal("120")
        assert db.query(ProductVariant).filter(ProductVariant.product_id == p.id).count() == 1

    def test_dry_run_no_escribe_y_reporta(self, client, db, org, auth_admin):
        r = _subir(client, auth_admin, org, [_fila("DRY-1"), _fila("")], dry_run="true")
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert (cuerpo["total_rows"], cuerpo["to_create"], cuerpo["errors"]) == (1, 1, 0)
        assert cuerpo["preview"][0]["action"] == "NEW"
        assert db.query(ProductVariant).filter(ProductVariant.sku == "DRY-1").count() == 0


class TestHandlerDelgado:
    def test_upload_products_cabe_en_40_lineas(self):
        from app.modules.products.router.import_export import upload_products
        assert len(inspect.getsource(upload_products).splitlines()) < 40

    def test_sin_print_en_el_importador(self):
        from app.modules.products.router import import_export
        from app.modules.products.services import importacion
        assert "print(" not in inspect.getsource(import_export)
        assert "print(" not in inspect.getsource(importacion)
```

- [ ] **Step 2: Correr para ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_altas_upload.py`
Expected: fallan `test_vendedor_es_403` (200), `test_cajero_sin_modulo_catalog_es_403` (200), `test_target_branch_ids_mal_formado_es_400_de_entrada` (200 con fila fallida), `test_sku_archivado…` (created 1), `test_sku_con_otra_caja…` (created 1), `TestHandlerDelgado` (ambas: `ModuleNotFoundError` para `importacion` y ~550 líneas). Pasan `test_cajero_con_modulo_importa…`, `test_pasa_por_crear_producto` y `test_dry_run…` (comportamiento que se conserva).

- [ ] **Step 3: Crear `services/importacion.py`**

```python
"""Importación de catálogo fila por fila (POST /api/products/upload).

Cada fila es un "upsert" por SKU dentro de un SAVEPOINT que abre el router:
  * SKU nuevo                  -> `crear_producto` (mismas validaciones que el alta manual);
  * SKU nuevo con Color/Talla y un producto de ESTA carga con el mismo
    Nombre + Departamento      -> `crear_variantes` (variante hermana);
  * SKU existente (vivo)       -> `_actualizar_desde_fila`.
Después, para las tres ramas: habilitación por sucursal, existencia absoluta
("Stock" es lo que HAY, no lo que entra), empaques y escalones por columnas.

Cualquier `HTTPException` del servicio o `FilaInvalida` revierte la fila
completa (ROLLBACK TO SAVEPOINT) y el router la reporta con su `detail`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Brand, Department, PackagingUnit, Product, ProductPrice, ProductVariant, User,
)
from app.modules.products.schemas import ProductCreate, ProductVariantCreate
from app.modules.products.variant_label import COLOR_MAX, SIZE_MAX, clean_attr, variant_label
from app.services.barcodes import AsignadorDeCodigos, barcode_en_uso

from .comun import celda_decimal, celda_texto, celda_vacia, variante_principal
from .productos import crear_producto
from .sucursales import armar_estado_por_sucursal, fijar_existencia
from .variantes import crear_variantes, pareja_repetida

TASA_IVA_DEFAULT = Decimal("16.0")
KARDEX_UPLOAD = ("Excel Upload", "Carga Masiva (Inicial)")


class FilaInvalida(Exception):
    """Fila rechazada por una validación de negocio.

    Se lanza en vez de `continue`: salir del `with db.begin_nested()` por la
    puerta buena hace RELEASE SAVEPOINT (confirma lo ya escrito en esa fila);
    la excepción hace ROLLBACK TO SAVEPOINT.
    """


@dataclass
class ContextoImportacion:
    org_id: int
    user: User
    target_branch_id: Optional[int]        # dónde cae el "Stock" del archivo
    sucursales: list[int]                  # dónde queda habilitado (scope)
    dept_map: dict[str, str]
    brand_map: dict[str, str]
    has_pkg_cols: bool
    has_tier_cols: bool
    asignador: AsignadorDeCodigos
    # (nombre_lower, department_id) -> (Product, id de su variante principal)
    # creado en esta misma carga con Color/Talla; solo se registra cuando la
    # fila entera terminó bien (si no, apuntaría a un objeto ya revertido).
    productos_cargados: dict = field(default_factory=dict)


@dataclass
class ResultadoFila:
    accion: str              # "NEW" | "UPDATE" | "SKIP"
    sku: str
    nombre: str
    precio: Optional[float]


def _sku_de_la_fila(fila: dict) -> str:
    sku = celda_texto(fila.get("sku")).strip()
    if sku.endswith(".0"):   # Excel convierte "1001" en 1001.0
        sku = sku[:-2]
    return sku


def _variante_viva_por_sku(db: Session, org_id: int, sku: str) -> Optional[ProductVariant]:
    return (
        db.query(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            func.lower(ProductVariant.sku) == sku.lower(),
            Product.organization_id == org_id,
            ProductVariant.deleted_at.is_(None),
        )
        .first()
    )


def _id_de_catalogo(db: Session, ctx: ContextoImportacion, modelo, mapa: dict[str, str], nombre: str) -> Optional[str]:
    """Departamento/marca por nombre; se crea en la org si no existe (el
    upload siempre lo hizo así: el archivo ES el catálogo)."""
    if not nombre:
        return None
    clave = nombre.lower()
    if clave not in mapa:
        nuevo = modelo(name=nombre, organization_id=ctx.org_id)
        db.add(nuevo)
        db.flush()
        mapa[clave] = nuevo.id
    return mapa[clave]


def _tasa_iva(fila: dict, sku: str) -> Decimal:
    """Columna opcional `Tasa IVA` (0–100). Ausente o vacía = 16."""
    cruda = fila.get("tasa iva")
    if celda_vacia(cruda) or celda_texto(cruda) == "":
        return TASA_IVA_DEFAULT
    tasa = celda_decimal(cruda, Decimal(-1))
    if tasa < 0 or tasa > 100:
        raise FilaInvalida(f"'{sku}': la tasa de IVA debe estar entre 0 y 100.")
    return tasa


def _atributos(fila: dict, sku: str) -> tuple[Optional[str], Optional[str]]:
    try:
        return (clean_attr(celda_texto(fila.get("color")), COLOR_MAX),
                clean_attr(celda_texto(fila.get("talla")), SIZE_MAX))
    except ValueError as e:
        raise FilaInvalida(f"'{sku}': color/talla {e}")


def _validar_barcode_de_fila(db: Session, ctx: ContextoImportacion, sku: str,
                             barcode: Optional[str], excepto_id: Optional[str] = None) -> None:
    """Mismo texto de siempre (sin acento en "codigo": hay pruebas que lo buscan así)."""
    if barcode and barcode_en_uso(db, ctx.org_id, barcode, excepto_id=excepto_id):
        raise FilaInvalida(f"'{sku}': el codigo de barras '{barcode}' ya lo tiene otra variante.")


def _crear_desde_fila(db: Session, ctx: ContextoImportacion, fila: dict, sku: str, nombre: str,
                      dept_id: Optional[str], brand_id: Optional[str], precio: Decimal, costo: Decimal,
                      has_iva: bool, tasa_iva: Decimal, barcode: Optional[str],
                      color: Optional[str], talla: Optional[str]) -> Product:
    """Fila nueva = alta manual. La sucursal de existencias queda también
    habilitada, y la existencia inicial entra ahí (`branch_id`)."""
    stock = celda_decimal(fila.get("stock", -1))
    destinos = set(ctx.sucursales)
    if ctx.target_branch_id:
        destinos.add(ctx.target_branch_id)
    datos = ProductCreate(
        name=nombre,
        description=celda_texto(fila.get("descripcion", "")),
        unit=celda_texto(fila.get("unidad", "pza")) or "pza",
        sku=sku,
        barcode=barcode,
        color=color,
        size=talla,
        price=precio,
        cost=costo,
        has_iva=has_iva,
        tax_rate=tasa_iva,
        department_id=dept_id,
        brand_id=brand_id,
        initial_stock=stock if (stock > 0 and ctx.target_branch_id) else Decimal(0),
        branch_id=ctx.target_branch_id,
        target_branch_ids=sorted(destinos) or None,
    )
    return crear_producto(
        db, ctx.org_id, ctx.user, datos,
        asignador=ctx.asignador, is_active_hq=not ctx.user.branch_id, kardex=KARDEX_UPLOAD,
    )


def _actualizar_desde_fila(db: Session, ctx: ContextoImportacion, variante: ProductVariant, fila: dict,
                           nombre: str, dept_id: Optional[str], brand_id: Optional[str],
                           precio: Decimal, costo: Decimal, has_iva: bool, barcode: Optional[str],
                           color: Optional[str], talla: Optional[str]) -> ProductVariant:
    """Celda vacía NO borra (descripción, unidad, código, color/talla): un
    archivo que viene del export trae las columnas pero no siempre el dato."""
    producto = variante.product
    if nombre:
        producto.name = nombre
    producto.department_id = dept_id
    if brand_id:
        producto.brand_id = brand_id
    descripcion = celda_texto(fila.get("descripcion", ""))
    if descripcion:
        producto.description = descripcion
    unidad = celda_texto(fila.get("unidad", ""))
    if unidad:
        producto.unit = unidad
    variante.has_iva = has_iva
    variante.price = precio
    variante.cost = costo
    if barcode and barcode != (variante.barcode or ""):
        # Un código nunca se sobrescribe con uno que ya tiene otra talla: el
        # escáner cobraría la equivocada.
        _validar_barcode_de_fila(db, ctx, variante.sku, barcode, excepto_id=variante.id)
        variante.barcode = barcode
    if color or talla:
        nueva = ((color or "").lower(), (talla or "").lower())
        actual = ((variante.color or "").lower(), (variante.size or "").lower())
        if nueva != actual and pareja_repetida(producto, color, talla, excepto_id=variante.id):
            raise FilaInvalida(
                f"'{variante.sku}': ya existe la variante {variant_label(color, talla)} en este producto"
            )
        variante.color, variante.size = color, talla
        variante.variant_name = variant_label(color, talla)
    return variante


def _habilitar_y_surtir(db: Session, ctx: ContextoImportacion, variante: ProductVariant,
                        fila: dict, es_nueva: bool) -> None:
    if ctx.sucursales:
        armar_estado_por_sucursal(db, ctx.org_id, variante, ctx.sucursales,
                                  is_active_hq=not ctx.user.branch_id)
    stock = celda_decimal(fila.get("stock", -1))   # -1 = la columna no viene
    if stock >= 0 and ctx.target_branch_id:
        fijar_existencia(
            db, ctx.org_id, variante, ctx.target_branch_id, stock, ctx.user.id,
            notas="Carga Masiva (Inicial)" if es_nueva else "Carga Masiva (Ajuste)",
        )


def _empaques_y_escalones(db: Session, ctx: ContextoImportacion, variante: ProductVariant, fila: dict) -> None:
    """Columnas E1..E3 (empaques) y P1..P5 (escalones): reemplazo completo de
    lo que haya, respetando la FK escalón -> empaque."""
    if ctx.has_pkg_cols:
        if ctx.has_tier_cols:
            db.query(ProductPrice).filter(ProductPrice.variant_id == variante.id).delete(synchronize_session=False)
        else:
            db.query(ProductPrice).filter(ProductPrice.variant_id == variante.id).update(
                {ProductPrice.linked_package_id: None}, synchronize_session=False,
            )
        db.query(PackagingUnit).filter(PackagingUnit.variant_id == variante.id).delete(synchronize_session=False)
    elif ctx.has_tier_cols:
        db.query(ProductPrice).filter(ProductPrice.variant_id == variante.id).delete(synchronize_session=False)
    db.flush()

    empaques: dict[str, PackagingUnit] = {}
    if ctx.has_pkg_cols:
        for i in range(1, 4):
            e_nombre = fila.get(f"e{i} nombre")
            e_barcode = fila.get(f"e{i} barcode")
            e_qty = fila.get(f"e{i} cantidad")
            e_precio = fila.get(f"e{i} precio")
            if e_nombre and not celda_vacia(e_nombre) and e_precio and not celda_vacia(e_precio):
                pkg = PackagingUnit(
                    variant_id=variante.id,
                    name=str(e_nombre),
                    barcode=str(e_barcode) if not celda_vacia(e_barcode) else None,
                    units_per_package=celda_decimal(e_qty, Decimal(1)),
                    package_price=celda_decimal(e_precio, Decimal(0)),
                    organization_id=ctx.org_id,
                )
                db.add(pkg)
                empaques[str(e_nombre).lower()] = pkg
        db.flush()

    if ctx.has_tier_cols:
        for i in range(1, 6):
            p_nombre = fila.get(f"p{i} nombre")
            p_min = fila.get(f"p{i} min")
            p_val = fila.get(f"p{i} precio")
            p_link = fila.get(f"p{i} empaque")
            if p_nombre and not celda_vacia(p_nombre) and p_val and not celda_vacia(p_val):
                enlace = str(p_link).lower() if p_link and not celda_vacia(p_link) else None
                linked_id = None
                if enlace and enlace in empaques:
                    linked_id = empaques[enlace].id
                elif str(p_nombre).lower() in empaques:
                    linked_id = empaques[str(p_nombre).lower()].id
                db.add(ProductPrice(
                    variant_id=variante.id,
                    price_name=str(p_nombre),
                    min_quantity=celda_decimal(p_min, Decimal(1)),
                    unit_price=celda_decimal(p_val, Decimal(0)),
                    linked_package_id=linked_id,
                    organization_id=ctx.org_id,
                ))
        db.flush()


def importar_fila(db: Session, ctx: ContextoImportacion, fila: dict) -> ResultadoFila:
    """Una fila del archivo, de principio a fin. Ver docstring del módulo."""
    sku = _sku_de_la_fila(fila)
    nombre = celda_texto(fila.get("nombre"))
    if not sku:
        return ResultadoFila("SKIP", "", nombre, None)

    precio = celda_decimal(fila.get("precio base", fila.get("precio", 0)))
    costo = celda_decimal(fila.get("costo", 0))
    has_iva = celda_texto(fila.get("incluye iva", "no")).strip().lower() in ("si", "sí", "yes", "1", "true")
    tasa_iva = _tasa_iva(fila, sku)
    dept_id = _id_de_catalogo(db, ctx, Department, ctx.dept_map, celda_texto(fila.get("departamento", "General")))
    brand_id = _id_de_catalogo(db, ctx, Brand, ctx.brand_map, celda_texto(fila.get("marca", "")))
    color, talla = _atributos(fila, sku)
    con_variante = bool(color or talla)
    clave_padre = (nombre.lower(), dept_id)
    barcode = celda_texto(fila.get("codigo barras")) or None

    registrar_grupo = False
    existente = _variante_viva_por_sku(db, ctx.org_id, sku)
    if existente is not None:
        producto = existente.product
        variante = _actualizar_desde_fila(db, ctx, existente, fila, nombre, dept_id, brand_id,
                                          precio, costo, has_iva, barcode, color, talla)
        accion, es_nueva = "UPDATE", False
    elif con_variante and clave_padre in ctx.productos_cargados:
        producto, principal_id = ctx.productos_cargados[clave_padre]
        # `crear_variantes` lee `producto.variants` y el PBS de la principal:
        # hay que flushear lo pendiente y refrescar la colección cacheada.
        db.flush()
        db.expire(producto, ["variants"])
        _validar_barcode_de_fila(db, ctx, sku, barcode)
        nuevas = crear_variantes(
            db, ctx.org_id, producto,
            [ProductVariantCreate(color=color, size=talla, sku=sku, barcode=barcode, price=precio, cost=costo)],
            principal_id=principal_id, asignador=ctx.asignador,
        )
        variante = nuevas[0]
        variante.has_iva = has_iva
        variante.tax_rate = tasa_iva
        accion, es_nueva = "NEW", True
    else:
        _validar_barcode_de_fila(db, ctx, sku, barcode)
        producto = _crear_desde_fila(db, ctx, fila, sku, nombre or "Producto sin Nombre", dept_id, brand_id,
                                     precio, costo, has_iva, tasa_iva, barcode, color, talla)
        variante = variante_principal(producto)
        accion, es_nueva = "NEW", True
        registrar_grupo = con_variante

    _habilitar_y_surtir(db, ctx, variante, fila, es_nueva)
    _empaques_y_escalones(db, ctx, variante, fila)
    if registrar_grupo:
        # Recién ahora: la fila entera terminó sin excepciones.
        ctx.productos_cargados[clave_padre] = (producto, variante.id)
    return ResultadoFila(accion, variante.sku, nombre or producto.name, float(precio))
```

`services/__init__.py`: `from .importacion import ContextoImportacion, FilaInvalida, ResultadoFila, importar_fila  # noqa: F401`.

- [ ] **Step 4: Reescribir `upload_products` y sus helpers en `import_export.py`**

Reemplaza los imports de la cabecera (líneas 7–32) por:

```python
import csv
import io
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.permissions import require_module
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.crud.products import _is_admin, query_visible_products
from app.models import Brand, Department, Product, ProductVariant, StockOnHand, User
from app.models.organization import Branch, BranchType
from app.modules.products.services.importacion import ContextoImportacion, importar_fila
from app.modules.products.services.validaciones import validar_sucursales_de_la_org
from app.services.barcodes import AsignadorDeCodigos

from ._shared import _PRODUCT_ADVANCED_ROLES

logger = logging.getLogger(__name__)

router = APIRouter()
```

Borra la clase `_FilaInvalida` (ahora `FilaInvalida` vive en services). `export_products_template` no se toca. Reemplaza **todo** desde `@router.post("/upload")` hasta el final del archivo por:

```python
async def _leer_filas(file: UploadFile) -> list[dict]:
    """CSV o Excel -> lista de dicts con cabeceras en minúsculas."""
    nombre = (file.filename or "").lower()
    es_csv = nombre.endswith(".csv")
    es_excel = nombre.endswith((".xlsx", ".xlsm", ".xls"))
    if not (es_csv or es_excel):
        raise HTTPException(status_code=400, detail="Formato inválido. Use Excel o CSV.")
    contenido = await file.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="Archivo vacío.")
    try:
        if es_csv:
            texto = contenido.decode("utf-8-sig", errors="replace")
            return [{k.lower().strip(): v for k, v in r.items()} for r in csv.DictReader(io.StringIO(texto))]
        from openpyxl import load_workbook
        ws = load_workbook(io.BytesIO(contenido), data_only=True).active
        cabeceras = [str(c.value or "").lower().strip() for c in ws[1]]
        return [{cabeceras[i]: v for i, v in enumerate(fila)} for fila in ws.iter_rows(min_row=2, values_only=True)]
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="El archivo no se pudo leer. Verifique que sea un Excel o CSV válido e intente de nuevo.",
        )


def _sucursal_hq_o_cualquiera(db: Session, org_id: int) -> Optional[int]:
    hq = db.query(Branch.id).filter(Branch.organization_id == org_id, Branch.branch_type == BranchType.HQ).first()
    if hq:
        return hq.id
    cualquiera = db.query(Branch.id).filter(Branch.organization_id == org_id).first()
    return cualquiera.id if cualquiera else None


def _sucursales_de_carga(db: Session, org_id: int, user: User, scope: str,
                         target_branch_ids: Optional[str]) -> list[int]:
    """Dónde queda habilitado lo importado. Usuario con sucursal: siempre la
    suya (no puede afectar otras). HQ: `scope` all | selected | branch (=HQ)."""
    if user.branch_id:
        return [user.branch_id]
    if scope == "all":
        ids = [b.id for b in db.query(Branch.id).filter(Branch.organization_id == org_id).all()]
    elif scope == "selected" and target_branch_ids:
        try:
            ids = [int(x.strip()) for x in target_branch_ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"target_branch_ids inválido: '{target_branch_ids}'")
        validar_sucursales_de_la_org(db, org_id, ids)
    else:
        hq = db.query(Branch.id).filter(Branch.organization_id == org_id, Branch.branch_type == BranchType.HQ).first()
        ids = [hq.id] if hq else []
    return sorted(set(ids))


def _contexto_de_carga(db: Session, org_id: int, user: User, branch_id: Optional[int],
                       target_branch_ids: Optional[str], scope: str, filas: list[dict]) -> ContextoImportacion:
    # RBAC: un usuario con sucursal (CAJERO/GERENTE) importa a la suya, se
    # ignora cualquier branch_id del form.
    if user.branch_id:
        destino = user.branch_id
    else:
        destino = branch_id
        if destino and db.query(Branch.id).filter(Branch.id == destino, Branch.organization_id == org_id).first() is None:
            raise HTTPException(status_code=400, detail="Sucursal de destino inválida o no pertenece a tu organización.")
    if not destino:
        destino = _sucursal_hq_o_cualquiera(db, org_id)
    columnas = set(filas[0].keys()) if filas else set()
    return ContextoImportacion(
        org_id=org_id,
        user=user,
        target_branch_id=destino,
        sucursales=_sucursales_de_carga(db, org_id, user, scope, target_branch_ids),
        dept_map={(d.name or "").lower(): d.id for d in db.query(Department).filter(Department.organization_id == org_id).all() if d.name},
        brand_map={(b.name or "").lower(): b.id for b in db.query(Brand).filter(Brand.organization_id == org_id).all() if b.name},
        has_pkg_cols=any(k.startswith("e1") for k in columnas),
        has_tier_cols=any(k.startswith("p1") for k in columnas),
        # Un solo asignador para todo el archivo: no releer el MAX por fila.
        asignador=AsignadorDeCodigos(db, org_id),
    )


def _confirmar(db: Session, hasta_fila: int) -> None:
    """Commit por lote. Si falla, se dice: antes se tragaba y el cliente
    recibía "created: 50" con la transacción caída."""
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("upload: no se pudo guardar el lote (hasta la fila %s)", hasta_fila)
        raise HTTPException(
            status_code=500,
            detail=f"No se pudieron guardar las filas procesadas (hasta la fila {hasta_fila}): {e}",
        )


def _procesar_filas(db: Session, org_id: int, ctx: ContextoImportacion, filas: list[dict], dry_run: bool) -> dict:
    creadas = actualizadas = fallidas = 0
    detalles: list[dict] = []
    preview: list[dict] = []
    for idx, fila in enumerate(filas):
        try:
            with db.begin_nested():
                res = importar_fila(db, ctx, fila)
        except Exception as e:   # noqa: BLE001 — cada fila se aísla y se reporta
            detalle = e.detail if isinstance(e, HTTPException) else str(e)
            logger.warning("upload org=%s fila %s: %s", org_id, idx + 2, detalle)
            fallidas += 1
            detalles.append({"row": idx + 2, "sku": str(fila.get("sku", "N/A")), "error": detalle})
            if len(preview) < 20:
                preview.append({"action": "ERROR", "sku": fila.get("sku") or None,
                                "name": fila.get("nombre"), "price": None, "error_message": detalle})
            continue
        if res.accion == "SKIP":
            continue
        creadas += res.accion == "NEW"
        actualizadas += res.accion == "UPDATE"
        if len(preview) < 20:
            preview.append({"action": res.accion, "sku": res.sku, "name": res.nombre,
                            "price": res.precio, "error_message": None})
        # Commit por lotes para no sostener el lock; en dry_run no se confirma nada.
        if not dry_run and (creadas + actualizadas + fallidas) % 50 == 0:
            _confirmar(db, hasta_fila=idx + 2)
    return {"creadas": creadas, "actualizadas": actualizadas, "fallidas": fallidas,
            "detalles": detalles, "preview": preview}


@router.post("/upload", dependencies=[Depends(require_module("catalog"))])
async def upload_products(
    branch_id: Optional[int] = Form(None),
    target_branch_ids: Optional[str] = Form(None),   # lista separada por comas
    scope: str = Form("branch"),                     # "branch" | "all" | "selected"
    dry_run: bool = Form(False),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Carga masiva. Parseo y sucursales en helpers de este módulo; cada fila
    en `services.importacion.importar_fila` dentro de su SAVEPOINT."""
    if current_user.role not in _PRODUCT_ADVANCED_ROLES:
        raise HTTPException(status_code=403, detail="No autorizado para importar productos")
    filas = await _leer_filas(file)
    ctx = _contexto_de_carga(db, org_id, current_user, branch_id, target_branch_ids, scope, filas)
    r = _procesar_filas(db, org_id, ctx, filas, dry_run)
    if dry_run:
        db.rollback()
        return {"total_rows": r["creadas"] + r["actualizadas"] + r["fallidas"], "to_create": r["creadas"],
                "to_update": r["actualizadas"], "errors": r["fallidas"], "preview": r["preview"],
                "error_details": r["detalles"]}
    _confirmar(db, hasta_fila=len(filas) + 1)
    return {"created": r["creadas"], "updated": r["actualizadas"], "failed": r["fallidas"],
            "pending": 0, "details": r["detalles"]}
```

Si tras el reemplazo queda sin uso alguno de `Product`, `ProductVariant`, `StockOnHand`, `joinedload`, `datetime`, `_is_admin`, `query_visible_products`, verifica con `grep -n` (los usa `export_products_template`) y conserva los que sí se usan.

- [ ] **Step 5: Correr**

Run: `python3 -m pytest -q -p no:warnings tests/test_altas_upload.py tests/test_import_export_variantes.py tests/test_barcodes.py tests/test_admin_catalog_regression.py tests/test_altas_crear_producto.py`
Expected: todas passed. Las que vigilan regresiones del importador: `test_agrupa_filas_del_mismo_nombre_en_un_producto` (hermanas), `test_pareja_repetida_entre_hermanas_no_se_pierde_por_cache`, `test_fila_fallida_no_escribe_precio_ni_nombre` (SAVEPOINT), `test_fila_nueva_con_codigo_ya_usado_se_rechaza` (texto "codigo de barras" sin acento), `test_filas_nuevas_sin_codigo_reciben_uno_distinto` (asignador compartido).

- [ ] **Step 6: Suite completa**

Run: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py`
Expected: mismo `failed` que `main`.

- [ ] **Step 7: Commit**

```bash
git add app/modules/products/services/ app/modules/products/router/import_export.py tests/test_altas_upload.py
git commit -m "refactor(productos): upload usa services.importacion fila por fila; guard de rol y require_module(catalog)"
```

---
### Task 10: bugs del upload — precio ≤ 0, `Tasa IVA`, commit que no se traga

**Files:**
- Modify: `app/modules/products/services/importacion.py` (`importar_fila`: precio > 0 antes de cualquier escritura)
- Test: `tests/test_altas_upload.py` (clases nuevas)

**Interfaces:**
- Consumes: Task 9 completa.
- Produces: nada nuevo; pruebas que fijan los tres bugs. (El 500 por commit fallido y la columna `Tasa IVA` ya quedaron implementados en la Task 9 — `_confirmar` y `_tasa_iva` —; aquí se les pone la prueba que faltaba. El precio ≤ 0 en una fila que **actualiza** todavía pasa: `_actualizar_desde_fila` escribe `precio` sin validar.)

- [ ] **Step 1: Escribir las pruebas que fallan** — añadir al final de `tests/test_altas_upload.py`:

```python
class TestPrecioYTasa:
    def test_precio_cero_en_fila_nueva_y_en_existente_falla_sin_tocar_nada(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Playera", "PLY-0", 100, [(branch_a.id, True)])
        db.flush()
        r = _subir(client, auth_admin, org, [
            _fila("PLY-0", **{"Precio Base": "0"}),      # existente
            _fila("NUEVO-0", **{"Precio Base": ""}),     # nueva, precio en blanco
            _fila("NEG-1", **{"Precio Base": "-3"}),     # nueva, negativo
        ])
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert (cuerpo["created"], cuerpo["updated"], cuerpo["failed"]) == (0, 0, 3)
        assert all("mayor a cero" in d["error"] for d in cuerpo["details"])
        db.refresh(v)
        assert Decimal(str(v.price)) == Decimal("100"), "el precio anterior queda intacto"
        assert db.query(ProductVariant).filter(ProductVariant.sku.in_(["NUEVO-0", "NEG-1"])).count() == 0

    def test_columna_tasa_iva_opcional(self, client, db, org, auth_admin):
        cabeceras = CABECERAS + ["Incluye IVA", "Tasa IVA"]
        r = _subir(client, auth_admin, org, [
            _fila("IVA-8", **{"Incluye IVA": "Si", "Tasa IVA": "8"}),
            _fila("IVA-16", **{"Incluye IVA": "Si", "Tasa IVA": ""}),
        ], cabeceras=cabeceras)
        assert r.status_code == 200, r.text
        assert r.json()["created"] == 2
        por_sku = {v.sku: v for v in db.query(ProductVariant).filter(ProductVariant.sku.in_(["IVA-8", "IVA-16"])).all()}
        assert (por_sku["IVA-8"].has_iva, Decimal(str(por_sku["IVA-8"].tax_rate))) == (True, Decimal("8"))
        assert Decimal(str(por_sku["IVA-16"].tax_rate)) == Decimal("16")

    def test_tasa_iva_fuera_de_rango_es_fila_fallida(self, client, db, org, auth_admin):
        r = _subir(client, auth_admin, org, [_fila("IVA-X", **{"Tasa IVA": "150"})], cabeceras=CABECERAS + ["Tasa IVA"])
        assert r.status_code == 200, r.text
        assert r.json()["failed"] == 1
        assert "tasa de IVA" in r.json()["details"][0]["error"]
        assert db.query(ProductVariant).filter(ProductVariant.sku == "IVA-X").count() == 0


class TestCommit:
    def test_commit_fallido_es_500_y_no_reporta_exito(self, client, db, org, auth_admin, monkeypatch):
        def _revienta():
            raise RuntimeError("disco lleno")
        monkeypatch.setattr(db, "commit", _revienta, raising=False)
        r = _subir(client, auth_admin, org, [_fila("CM-1")])
        assert r.status_code == 500, r.text
        assert "No se pudieron guardar" in r.json()["detail"]
        assert "created" not in r.json()

    def test_commit_por_lote_fallido_tambien_es_500(self, client, db, org, auth_admin, monkeypatch):
        """El commit cada 50 filas tampoco se traga: la fila 50 dispara el lote."""
        def _revienta():
            raise RuntimeError("conexión perdida")
        monkeypatch.setattr(db, "commit", _revienta, raising=False)
        r = _subir(client, auth_admin, org, [_fila(f"LOTE-{i}") for i in range(50)])
        assert r.status_code == 500, r.text
        assert "hasta la fila 51" in r.json()["detail"]
```

- [ ] **Step 2: Correr para ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_altas_upload.py -k "PrecioYTasa or Commit"`
Expected: falla `test_precio_cero_en_fila_nueva_y_en_existente_falla_sin_tocar_nada` (`updated == 1`, el precio de `PLY-0` quedó en 0). Los otros cuatro pasan ya (fijan lo hecho en Task 9); si alguno falla, el `_confirmar`/`_tasa_iva` de la Task 9 no quedó como está escrito ahí.

- [ ] **Step 3: Validar el precio antes de cualquier escritura**

En `services/importacion.py::importar_fila`, justo después de `precio = celda_decimal(...)`:

```python
    if precio <= 0:
        raise FilaInvalida(f"'{sku}': el precio debe ser mayor a cero.")
```

(Para la rama "nueva" `crear_producto` ya lo rechazaba con 422; con este guard las tres ramas dan el mismo texto y nada se escribe antes.)

- [ ] **Step 4: Correr**

Run: `python3 -m pytest -q -p no:warnings tests/test_altas_upload.py tests/test_import_export_variantes.py tests/test_barcodes.py`
Expected: todas passed.

- [ ] **Step 5: Commit**

```bash
git add app/modules/products/services/importacion.py tests/test_altas_upload.py
git commit -m "fix(productos): upload rechaza precio <= 0, acepta Tasa IVA y no traga errores de commit"
```

> **Fin del Paso 2 de despliegue:** con las Tasks 7–10 la suite está verde y producción cambia en duplicate/update/upload.

---

### Task 11 (OPCIONAL — se decide con el usuario antes de hacerla): evento `ProductCreated`

> Marcada opcional por la spec ("Opcional; se decide en el spec"). No tiene subscriber: solo deja la fila en `event_outbox` para que etiquetas, reportes o el agente (SP2) se suscriban después. El worker del outbox la marcará `PROCESSED` sin handlers. Si el usuario la descarta, el plan termina en la Task 10.

**Files:**
- Modify: `app/core/events.py` (añadir `ProductCreated` al final)
- Modify: `app/modules/products/services/productos.py` (`crear_producto` y `duplicar_producto` encolan)
- Test: `tests/test_altas_evento.py`

**Interfaces:**
- Consumes: `EventBus.enqueue`, `register_event`, `BaseEvent` (`app.core.events`); `EventOutbox` (`app.models.event_outbox`).
- Produces: `ProductCreated(product_id: str, organization_id: int, variant_ids: list[str] = [], origen: str = "alta")` con `origen ∈ {"alta","duplicado","importacion"}`; `crear_producto(..., origen: str = "alta")` nuevo kwarg; la importación pasa `origen="importacion"`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_altas_evento.py`:

```python
"""`ProductCreated` queda en el outbox en la misma transacción del alta."""
from conftest import _make_product
from app.models.event_outbox import EventOutbox


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


def _eventos(db):
    return db.query(EventOutbox).filter(EventOutbox.event_type == "ProductCreated").all()


class TestProductCreated:
    def test_esta_registrado_para_el_outbox(self):
        from app.core.events import EVENT_REGISTRY, ProductCreated
        assert EVENT_REGISTRY["ProductCreated"] is ProductCreated

    def test_el_alta_deja_un_evento(self, client, db, org, branch_a, auth_admin):
        r = client.post("/api/products/", json={
            "name": "Playera", "sku": "EV-1", "price": "100", "cost": "50",
            "target_branch_ids": [branch_a.id],
            "extra_variants": [{"color": "Rojo", "size": "M"}],
        }, headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        filas = _eventos(db)
        assert len(filas) == 1
        payload = filas[0].payload
        assert payload["product_id"] == r.json()["id"]
        assert payload["organization_id"] == org.id
        assert payload["origen"] == "alta"
        assert len(payload["variant_ids"]) == 2

    def test_el_duplicado_tambien(self, client, db, org, branch_a, auth_admin):
        p, _ = _make_product(db, org, "Gorra", "EV-2", 50, [(branch_a.id, True)])
        db.flush()
        r = client.post(f"/api/products/{p.id}/duplicate", headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        assert [f.payload["origen"] for f in _eventos(db)] == ["duplicado"]

    def test_un_alta_rechazada_no_deja_evento(self, client, db, org, branch_a, auth_admin):
        r = client.post("/api/products/", json={"name": "X", "sku": "EV-3", "price": "0", "cost": "1"},
                        headers=_h(auth_admin, org))
        assert r.status_code == 422
        assert _eventos(db) == []
```

- [ ] **Step 2: Correr para ver que falla**

Run: `python3 -m pytest -q -p no:warnings tests/test_altas_evento.py`
Expected: FAIL `test_esta_registrado_para_el_outbox` con `ImportError: cannot import name 'ProductCreated'`; los demás con `len(filas) == 0`.

- [ ] **Step 3: Definir el evento** — al final de `app/core/events.py`:

```python
@register_event
class ProductCreated(BaseEvent):
    """Un producto nuevo quedó en la base (alta manual, duplicado o importación).

    Sin subscriber por ahora: etiquetas, reportes o el asistente (SP2) se
    suscriben cuando lo necesiten. Los handlers deben ser idempotentes por
    `product_id` (regla de oro #6).
    """
    product_id: str
    organization_id: int
    variant_ids: List[str] = []
    origen: str = "alta"   # alta | duplicado | importacion
```

- [ ] **Step 4: Encolar en el servicio**

En `services/productos.py` agrega `from app.core.events import EventBus, ProductCreated` y:

- `crear_producto` gana el kwarg `origen: str = "alta"` (después de `kardex`) y, justo antes del `db.flush()` final (el `expire` es obligatorio: `crear_variantes` ya cargó `producto.variants` con solo la principal y las hermanas se insertaron por `product_id`, no por la relación):

```python
    db.flush()
    db.expire(producto, ["variants"])
    EventBus.enqueue(db, ProductCreated(
        product_id=producto.id, organization_id=org_id,
        variant_ids=[v.id for v in variantes_vivas(producto)], origen=origen,
    ))
```

- `duplicar_producto`, antes de su `db.flush()` final:

```python
    EventBus.enqueue(db, ProductCreated(
        product_id=copia.id, organization_id=org_id,
        variant_ids=[v.id for v in variantes_vivas(copia)], origen="duplicado",
    ))
```

- En `services/importacion.py::_crear_desde_fila` agrega `origen="importacion"` a la llamada de `crear_producto`.

Nota: `producto.variants` es una relación perezosa; tras el `flush` de las hermanas, acceder a ella la carga desde la base, así que `variantes_vivas(producto)` incluye a las `extra_variants`.

- [ ] **Step 5: Correr**

Run: `python3 -m pytest -q -p no:warnings tests/test_altas_evento.py tests/test_outbox.py tests/test_altas_crear_producto.py tests/test_altas_upload.py`
Expected: todas passed.

- [ ] **Step 6: Commit**

```bash
git add app/core/events.py app/modules/products/services/ tests/test_altas_evento.py
git commit -m "feat(productos): evento ProductCreated en el outbox (sin subscriber)"
```

---

## Despliegue en dos pasos

Las cuatro tiendas vivas capturan por `POST /api/products/` todos los días. Por eso el cambio sale en dos despliegues, cada uno con la suite verde y con `main` tocado **solo con permiso explícito**.

### Verificación previa (antes del Paso 1, en producción, solo lectura)

`require_module("catalog")` empieza a exigir el módulo a CAJERO/GERENTE en el alta. Confirmar que ninguna organización con usuarios de caja activos lo tenga apagado:

```sql
SELECT o.id, o.name, o.plan
FROM organization o
WHERE NOT EXISTS (
  SELECT 1 FROM organization_modules m
  WHERE m.organization_id = o.id AND m.module_key = 'catalog' AND m.is_enabled
)
AND EXISTS (
  SELECT 1 FROM users u
  JOIN user_organizations uo ON uo.user_id = u.id
  WHERE uo.organization_id = o.id AND u.role IN ('CAJERO', 'GERENTE') AND u.is_active
);
```

Debe devolver **cero filas**. Si devuelve alguna, se enciende el módulo desde `/platform/organizations/{id}` (o `INSERT INTO organization_modules (organization_id, module_key, is_enabled) VALUES (<id>, 'catalog', true)`) **antes** de fusionar. `catalog` está en la base de todos los presets (`scripts/init_presets_v2.py:276`), así que lo esperable es cero.

### Paso 1 — servicio + create + variantes (Tasks 1–6)

1. `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py` → mismo `failed` que `main`.
2. Pedir permiso al usuario para `git push -u origin feat/altas-servicio-backend` y abrir PR a `main` (`gh pr create`); describir: regla única de SKU (sin mayúsculas, incluye archivados), HQ sin destinos → todas las que venden, escalón en $0 rechazado en el alta, `require_module("catalog")` en el alta.
3. Con permiso explícito, fusionar. El push a `main` dispara `deploy-ionos` (`docs/DEPLOY.md`). Verificar: `gh run list --limit 3`, luego `ssh ionos 'docker exec atlas-one-prod cat /app/.commit_desplegado'` = sha fusionado, y `curl -s https://app.atlasone.com.mx/health`.
4. Humo en producción (cuenta QA, no cliente): crear un producto con una talla extra desde la ficha y verificar que aparece en `GET /api/products/pos/search` de una cajera; intentar repetir el SKU en minúsculas → 409.

### Paso 2 — duplicate / update / upload (Tasks 7–10, opcionalmente 11)

1. Misma suite verde.
2. Permiso para push/PR; describir: duplicate conserva color/talla y asigna código, PUT 409 en SKU repetido (antes 400) y 422 en sucursal ajena (antes 400), upload rechaza precio ≤ 0, columna opcional `Tasa IVA`, 500 explícito si falla el commit, `target_branch_ids` inválido → 400 de entrada.
3. Fusionar con permiso; misma verificación de deploy.
4. Humo: duplicar un producto con color/talla y confirmar la copia en la ficha; subir un CSV de 2 filas con una a precio 0 y ver `failed: 1` con el texto "mayor a cero".

### Vuelta atrás

Cada paso es un merge independiente; si el Paso 1 da problemas en tienda, `git revert -m 1 <merge>` sobre `main` (con permiso) devuelve el handler anterior sin tocar esquema (no hay migración).

---

## Hallazgos del código que matizan la spec (para quien ejecute)

- **"Upload no fija `tax_rate`" (§2.1):** el ORM ya aplica `default=16.0` al insertar, así que ninguna variante importada quedaba con `tax_rate` NULL. El plan lo deja explícito (`crear_producto` recibe `tax_rate`) y le da sentido con la columna opcional `Tasa IVA`.
- **"variantes sin mayúsculas" (§2.1):** `router/variants.py::_sku_en_uso` ya era case-insensitive; lo que le faltaba era contar archivados. Queda unificado en `validar_sku_unico`.
- **Admin con `branch_id` = HQ (`admin_user` de las pruebas y varios admins reales):** no es "usuario HQ sin sucursales destino" para la regla §6.4; su alta sin `target_branch_ids` sigue habilitando solo en su HQ (`can_sell=False`), como hoy. Cambiarlo sería otra decisión; no está en este plan.
- Los números de línea de la spec (create 190–545, duplicate 841–976, update 983–1223, upload 275–822, `core.py:912`, `variants.py:83`, `import_export.py:417`, prints en 773/792/810) coinciden con el código al 2026-10-15 (último commit que tocó `core.py`: `5bb9720`).
