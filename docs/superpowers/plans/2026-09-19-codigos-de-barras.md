# Códigos de barras por talla Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Toda variante (talla/color) tiene un código de barras propio y único en su organización: se genera solo al crear productos y tallas, se puede completar para el catálogo existente con un clic, se valida contra duplicados, y se exporta como CSV de etiquetas listo para ZebraDesigner / la app de la etiquetadora.

**Architecture:** Servicio `app/services/barcodes.py` con formato EAN-13 interno `2` + `org_id` (3 dígitos) + secuencia de 8 dígitos + dígito verificador (prefijo GS1 "20–29" = uso interno, así un escáner lo lee como EAN-13 normal). La secuencia se toma con `pg_advisory_xact_lock(org_id, hashtext('barcode'))` + `MAX` de los códigos internos de la org (mismo patrón que `app/utils/folios.py`; en SQLite se omite el lock). Se asigna al crear (`core.py::create_product`, `variants.py::crear_variantes`, importación de filas nuevas sin código) y bajo demanda (`POST /api/products/barcodes/assign-missing`). Exportación `GET /api/products/export/labels.csv`. Frontend: botones "Códigos faltantes" y "Exportar etiquetas" en la barra de Productos.

**Tech Stack:** FastAPI + SQLAlchemy; React/TS.

**Spec:** este documento. Contexto: Eleven Fashion (org 17) tiene 85 tallas y 81 sin código; los pocos que hay son ruido (`*1A43KE*`). Producción tiene 2 códigos duplicados en otras orgs (16: `2024033050038`; 14: `522`) que NO se tocan.

## Global Constraints

- Un código nunca se sobrescribe: solo se asigna cuando está vacío. Los códigos de fábrica (EAN reales importados) se conservan.
- Unicidad por organización (no global: dos tiendas pueden vender el mismo EAN). Crear o editar una variante con un código que ya usa otra variante viva de la org → 409 con el mensaje que ya usa `variants.py::_barcode_en_uso`.
- Toda consulta filtra `organization_id` (las variantes no lo tienen: siempre `join(Product)`).
- Sin cambios de esquema: `product_variants.barcode` ya existe e indexado.
- El POS ya busca por código exacto (`pos/search?exact=true`): un código generado se cobra escaneándolo sin más; agrega un test que lo pruebe.
- Tests: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py` (baseline 914 passed, 2 skipped, 3 xfailed en main); frontend `npx tsc --noEmit && npm run build`.
- Commits con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb`.

---

### Task 1: Backend — servicio, asignación automática, endpoints y CSV

**Files:**
- Create: `app/services/barcodes.py`, `tests/test_barcodes.py`.
- Modify: `app/modules/products/router/core.py` (`create_product` ~línea 366 y `extra_variants`; `update_product` ~1017 valida duplicado), `app/modules/products/router/variants.py` (`crear_variantes` ~197: si `barcode` vacío → generar), `app/modules/products/router/import_export.py` (variantes NUEVAS sin "Codigo Barras" → generar; el export Excel ya trae la columna), nuevo archivo de router `app/modules/products/router/barcodes.py` montado desde `app/modules/products/router/__init__.py` (mira cómo se montan `search`/`variants`).

**Interfaces:**
- Produces: `ean13_check_digit(d12: str) -> str`; `es_codigo_interno(org_id: int, code: str) -> bool`; `siguiente_codigo_interno(db, org_id) -> str`; `asignar_codigos_faltantes(db, org_id, product_id: str | None = None) -> int` (flush por variante, no commit); `barcode_en_uso(db, org_id, code, excepto_id=None) -> bool` (mueve `_barcode_en_uso` aquí y deja `variants.py` importándolo).
- Endpoints: `GET /api/products/barcodes/missing-count` → `{"missing": n}` (visibles para el usuario); `POST /api/products/barcodes/assign-missing` body `{product_id?: str}` → `{"assigned": n}` (solo ADMINISTRADOR/DUEÑO: usa `require_admin_or_owner` de `app/core/security/guards.py`); `GET /api/products/export/labels.csv?product_id=&only_with_stock=false` → CSV UTF-8 con BOM, separador `,`, encabezados `SKU,Codigo de barras,Producto,Marca,Talla,Color,Precio,Existencia`, una fila por variante viva, respetando `query_visible_products` (mismo scope que el export Excel) y existencia de la sucursal del usuario (admin sin sucursal: suma de sucursales). Nombre de archivo `etiquetas_<fecha>.csv`.

- [ ] **Step 1: Tests (fallan primero)** — `tests/test_barcodes.py` (fixtures de `conftest.py`: `client`, `db`, `org`, `branch_a`, `auth_admin`, `auth_cajero_a`, `_make_product`):
  1. `ean13_check_digit("201700000001") == "8"`? — calcula el correcto con el algoritmo estándar (pesos 1-3 de derecha a izquierda) y fija ese valor; además `len(siguiente_codigo_interno(...)) == 13`, empieza con `f"2{org.id:03d}"`, y dos llamadas seguidas devuelven consecutivos.
  2. Crear un producto sin `barcode` por `POST /api/products/` deja `barcode` de 13 dígitos en la variante principal y en cada `extra_variants` sin código; con `barcode` explícito se respeta.
  3. `POST /api/products/{id}/variants` con tallas sin código → cada una recibe uno distinto.
  4. `POST /api/products/` con un `barcode` que ya usa otra variante de la org → 409; el mismo código en OTRA org → 200.
  5. `assign-missing`: con 3 variantes sin código y 1 con, devuelve `assigned: 3`, la que tenía no cambia; segunda llamada devuelve 0; `missing-count` pasa de 3 a 0; un CAJERO recibe 403.
  6. `pos/search?q=<código generado>&exact=true` encuentra la variante.
  7. `export/labels.csv`: 200, `text/csv`, empieza con BOM, encabezado exacto, una fila por variante con SKU/código/talla/precio correctos; `product_id` filtra a un producto.
- [ ] **Step 2: `app/services/barcodes.py`** con las funciones de Interfaces. `siguiente_codigo_interno`: lock advisory solo en Postgres; `MAX(barcode)` filtrando `barcode LIKE '2{org:03d}%' AND length(barcode)=13 AND barcode ~ '^[0-9]+$'` (en SQLite usa `GLOB`); si no hay, secuencia 1. Verifica que el candidato no esté en uso (por si un EAN de fábrica coincide) y avanza hasta uno libre.
- [ ] **Step 3: Asignación automática** en `create_product` (principal + hermanas, después del `db.flush()` de las hermanas), `crear_variantes` y filas nuevas de la importación. Validación 409 en `create_product` y `update_product` con `barcode_en_uso`.
- [ ] **Step 4: Router `barcodes.py`** (tres endpoints) montado en `__init__.py`.
- [ ] **Step 5:** suite completa verde; commit `feat(productos): codigo de barras EAN-13 interno por talla, asignacion y exportacion de etiquetas`.

---

### Task 2: Frontend — botones en Productos

**Files:**
- Modify: `frontend/src/api/products.ts` (`barcodesMissingCount()`, `assignMissingBarcodes(productId?)`, `downloadLabelsCsv(productId?)` con `responseType: 'blob'` como `downloadTemplate`), `frontend/src/pages/inventory/Products.tsx` (barra ~línea 1255).

- [ ] **Step 1:** Junto a "Importar": botón "Etiquetas CSV" (icono `fa-tags`) que descarga el CSV; y, solo para admin/dueño y solo si `missing > 0`, botón "Generar códigos (N)" que llama `assign-missing`, muestra toast "N códigos generados", recarga la lista y el contador. Al abrir la pantalla se pide `missing-count` una vez.
- [ ] **Step 2:** En el detalle de producto por talla que ya existe en esta pantalla (filas de `variantRows`), mostrar el código de barras junto al SKU cuando exista (texto pequeño, `font-mono`).
- [ ] **Step 3:** `npx tsc --noEmit && npm run build`; commit `feat(productos): generar codigos faltantes y exportar etiquetas CSV`.
