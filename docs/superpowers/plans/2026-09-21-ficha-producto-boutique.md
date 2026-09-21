# Ficha de producto boutique Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El producto gana género, modelo y material; el sistema deriva un **nombre de venta** (Marca · Nombre Modelo · Talla / Color) que usan el POS, la ficha, la búsqueda, la etiqueta CSV y el ticket; existe una convención de SKU con sugerencia automática; y un estilo de ticket **detallado** por tienda imprime marca, nombre completo y talla sin recortar.

**Architecture:** Columnas `products.gender` (String(10), valores `HOMBRE|MUJER|UNISEX|NINO`, nullable), `products.model` (String(80)), `products.material` (String(80)); `organization.ticket_line_style` (String(12), `compact` por defecto, `detailed`). ALTERs idempotentes en `scripts/railway_init.py`. Helper puro `app/modules/products/sale_name.py` con `sale_name(brand, name, model) -> str` y `variant_sale_name(brand, name, model, color, size) -> str` y `sku_sugerido(brand, name, model, color, size) -> str`. `ProductRead.sale_name` y `ProductVariantRead.sale_name` aplanados en `_compute_product_read`. `create_sale` guarda en `sales_lines.description` el `variant_sale_name` (una sola línea de `_line_description`). `pos_printer.py` gana `_product_lines_detailed(...)` usado cuando la org tiene `ticket_line_style == "detailed"`. Frontend: formulario con los 3 campos y botón "Sugerir SKU"; tarjeta del POS, ficha y búsqueda muestran `sale_name`; Empresa gana el selector del estilo de ticket. Etiqueta CSV con columnas Genero, Modelo, Material y Nombre de venta.

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic v2; ESC/POS; React/TS; pytest + vitest.

**Spec:** este documento. Decisiones del dueño de Eleven Boutique (2026-09-21): sí a los tres campos; el nombre de venta lleva la marca primero; se separan los departamentos (Suéteres de Playeras, Tenis de Calzado — eso es dato, se hace en la pasada de corrección, no aquí); convención de SKU ahora.

## Global Constraints

- Ninguna tienda cambia de comportamiento sin configurarlo: `ticket_line_style` nace `compact`; `sale_name` de un producto sin marca ni modelo es exactamente el `name` de hoy; `_line_description` para un producto sin marca/modelo produce el mismo texto que hoy (`Nombre` o `Nombre (Talla)`), así los tests de ticket existentes no cambian.
- `create_sale` (`app/routers/sales.py`): solo cambia `_line_description` (una función pura); nada más se toca en ese archivo.
- El SKU sugerido es una **sugerencia**: nunca se aplica solo; el alta sigue aceptando cualquier SKU único por organización.
- Tests: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py` (baseline 975 passed, 2 skipped, 3 xfailed); frontend `npx vitest run && npx tsc --noEmit && npm run build`.
- Commits con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb`.

---

### Task 1: Backend — campos, nombre de venta, SKU sugerido, ticket detallado, CSV

**Files:**
- Create: `app/modules/products/sale_name.py`, `tests/test_sale_name.py`, `tests/test_ticket_detallado.py`.
- Modify: `app/modules/products/models.py` (Product: `gender`, `model`, `material`), `app/modules/tenants/models.py` + `schemas.py` (`ticket_line_style`), `scripts/railway_init.py` (4 ALTERs), `app/modules/products/schemas.py` (`ProductCreate/Update`: los 3 campos con validador de `gender`; `ProductRead.sale_name`, `ProductVariantRead.sale_name`), `app/modules/products/router/_shared.py::_compute_product_read` (aplanar `sale_name` en producto y en cada variante), `app/modules/products/router/core.py` (persistir los 3 campos en create/update; endpoint `GET /api/products/sku-suggest?brand=&name=&model=&color=&size=` → `{"sku": …, "available": bool}`), `app/routers/sales.py::_line_description`, `app/pos_printer.py` (`_product_lines_detailed`, uso en `build_ticket_bytes` y `build_reissued_ticket_bytes`), `app/modules/products/router/barcodes.py` (CSV: columnas `Genero,Modelo,Material,Nombre de venta` al final), `app/modules/products/router/search.py` si la búsqueda por texto debe encontrar por marca/modelo (añade `Brand.name` y `Product.model` al `ilike` de `q`).

**Interfaces (exactas):**
```python
# app/modules/products/sale_name.py
GENDERS = ("HOMBRE", "MUJER", "UNISEX", "NINO")
def sale_name(brand: str | None, name: str, model: str | None) -> str:
    """'Louis Vuitton · Chamarra mezclilla' — marca primero; sin marca → 'Chamarra mezclilla'; modelo se pega al nombre con espacio."""
def variant_sale_name(brand, name, model, color, size) -> str:
    """sale_name + ' · Talla M' / ' · Beige' / ' · Beige, Talla M'; sin atributos → sale_name."""
def sku_sugerido(brand, name, model, color, size) -> str:
    """MARCA-PRENDA-MODELO-COLOR-TALLA sin acentos, mayúsculas, solo [A-Z0-9-]; partes vacías se omiten.
    Marca: iniciales si tiene 2+ palabras (Louis Vuitton→LV, Chrome Hearts→CH, Dolce & Gabbana→DG, Tiffany & Co.→TC),
    si no las 3 primeras letras (Gucci→GUC, Amiri→AMI). Prenda: 4 primeras letras de la primera palabra del nombre (Pantalón→PANT, Playera→PLAY,
    Chamarra→CHAM, Tenis→TENI). Modelo y color: 3 primeras letras de la primera palabra (Mezclilla→MEZ, Beige→BEI). Talla tal cual (M, CH, XL, 26.5→265)."""
```
`_line_description(variant)` pasa a devolver `variant_sale_name(brand, product.name, product.model, variant.color, variant.size)`. Con marca y modelo vacíos y talla vacía → `product.name` (idéntico a hoy); con talla → hoy da `Nombre (M)`: **conserva** ese formato exacto cuando no hay marca ni modelo (`Nombre (Talla)`), y usa el formato con ` · ` solo cuando hay marca o modelo. Documenta la regla en el helper con tests.

**Ticket detallado (80 mm, 56 cols; 58 mm, 32 cols):**
```
1x  LOUIS VUITTON
    Chamarra mezclilla beige
    Talla M                          @4,000.00    4,000.00
```
- Línea 1: `qty(4)` + marca en mayúsculas (o el nombre si no hay marca, y entonces se omite la línea 2).
- Línea 2+: nombre + modelo envuelto con `_wrap_text` a `cols - 4`, sangría 4.
- Última línea: sangría 4 + atributos (`Talla M`, `Beige`, `Beige, Talla M`; vacío si no hay) rellenado a la izquierda, `@unit` y `total` a la derecha con los mismos anchos de `_product_line`. Miles con coma (`4,000.00`).
- Fuente: obtén marca/nombre/modelo/color/talla de `line.variant.product` / `line.variant` (ya se carga con `joinedload(SalesLineItem.variant)` en `printer.py:453`; añade `.joinedload(ProductVariant.product).joinedload(Product.brand)` para no hacer N+1); si `line.variant` es None, imprime `line.description` envuelto.
- `build_ticket_bytes`/`build_reissued_ticket_bytes` eligen por `getattr(organization, "ticket_line_style", "compact") == "detailed"`.

- [ ] **Step 1: Tests (fallan primero).** `tests/test_sale_name.py`: casos de `sale_name`, `variant_sale_name`, `sku_sugerido` (incluye "Louis Vuitton"/"Chamarra"/"Mezclilla"/"Beige"/"M" → `LV-CHAM-MEZ-BEI-M`; "Gucci"/"Pantalón formal"/None/None/"32" → `GUC-PANT-32`; acentos: "Suéter"→`SUET`), validación de `gender` (422 con "DAMA"), `POST /api/products/` con los 3 campos persiste y `GET` devuelve `sale_name` y `variants[].sale_name`, `GET /api/products/sku-suggest` devuelve la sugerencia y `available` (falso si ya existe en la org, verdadero en otra org), búsqueda `pos/search?q=vuitton` encuentra por marca. `tests/test_ticket_detallado.py`: mismo estilo que `tests/test_ticket_layout.py`; con `ticket_line_style="detailed"` las tres líneas, wrap de un nombre largo en 58 mm sin exceder cols, sin marca → dos líneas, sin talla → línea de precio sin atributos; con `compact` (o sin atributo) el ticket es byte-idéntico al de hoy; reimpresión igual. Y en `tests/test_sale_customer_name.py` o nuevo: `_line_description` para producto sin marca/modelo y talla M sigue dando `Nombre (M)`; con marca → `Marca · Nombre · Talla M`.
- [ ] **Step 2: Modelo, migraciones, schemas, `_compute_product_read`, `core.py` (persistir + endpoint), `search.py`, `_line_description`, `pos_printer.py`, CSV.**
- [ ] **Step 3: Suite completa verde; commit** `feat(productos): genero, modelo, material, nombre de venta, SKU sugerido y ticket detallado`.

---

### Task 2: Frontend — formulario, POS, ficha, Empresa

**Files:**
- Modify: `frontend/src/types/products.ts` y `frontend/src/api/products.ts` (`gender`, `model`, `material`, `sale_name`, `skuSuggest()`), `frontend/src/pages/products/ProductForm.tsx` + `frontend/src/components/products/ProductCommercialSection.tsx` (o donde vivan marca/departamento) — selector Género (Hombre/Mujer/Unisex/Niño/—), inputs Modelo y Material, botón "Sugerir SKU" junto al SKU que llama `skuSuggest` con marca/nombre/modelo/color/talla actuales y rellena el SKU (y los de la matriz de tallas con sufijo `-TALLA`) solo si el usuario acepta; `frontend/src/pages/inventory/Products.tsx` (mismo trío en el modal de alta/edición que vive ahí, y `sale_name` en la lista), `frontend/src/components/pos/ProductSearch.tsx` (tarjeta: `p.sale_name ?? p.name`; el `name` que va al carrito usa `sale_name`), `frontend/src/components/pos/modals/ProductDetailModal.tsx` y `VariantPickerModal.tsx` (título con `sale_name`; filas por talla con `variants[].sale_name`), `frontend/src/pages/scanner/StoreScanner.tsx` (título con `sale_name`), `frontend/src/pages/core/Organization.tsx` (selector "Estilo de línea del ticket": Compacto / Detallado, con una vista previa de texto de 3 líneas).
- Test: `frontend/src/components/products/__tests__/skuSuggest.test.ts` solo si creas un helper puro (por ejemplo para armar los SKU de la matriz con sufijo de talla); no hay tests de componentes.

- [ ] **Step 1:** Tipos y API. **Step 2:** Formularios (alta y edición, ambos sitios). **Step 3:** POS/ficha/scanner con `sale_name`. **Step 4:** Empresa. **Step 5:** `npx vitest run && npx tsc --noEmit && npm run build`; commit `feat(productos): ficha con genero, modelo y material; nombre de venta en POS y ticket detallado en Empresa`.
