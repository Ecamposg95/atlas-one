# Pendientes de código 2026-11-10 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar tres pendientes que tocan dinero o inventario real: el listado de productos que pierde filas al paginar, el importador CSV que deja costo NULL y el conteo ciego del corte de caja que se puede burlar.

**Architecture:** Tres arreglos independientes en la rama `fix/pendientes-2026-11-10`. El 1 y el 2 son backend con pruebas pytest; el 3 es solo frontend (React) con pruebas vitest y no toca el cálculo de `expected_cash` del backend.

**Tech Stack:** FastAPI + SQLAlchemy (pytest sobre SQLite en memoria), React + Vite + TS (vitest, `tsc`).

**Spec:** sin spec escrita. La fuente es la memoria del proyecto: la paginación (2026-09-28: `total`=620, el recorrido devolvió 607), el costo NULL del importador (alta 2026-10) y la medición de cierres exactos (2026-11-06). Las decisiones de diseño están en cada tarea.

## Global Constraints

- Nada se fusiona ni se empuja a `main` sin permiso explícito del usuario (push a main = deploy a producción).
- Pytest: `.venv/bin/python -m pytest -q --ignore=tests/test_cash_complete.py` si existe `.venv`, si no `python3 -m pytest …`. Un solo proceso pytest por worktree.
- Frontend: `cd frontend && npx vitest run <archivo>` y `npx tsc --noEmit -p .` deben pasar.
- Comentarios en español, estilo del código circundante. Sin `print()` de depuración.
- Colores por tokens: no agregar `text-white`, `text-slate-*`, `bg-slate-*`, `border-slate-*` ni hex sueltos en archivos fuera de `PENDIENTES` de `frontend/src/__tests__/coloresPorTokens.test.ts`.
- Commits con scope (`fix(products):`, `fix(import):`, `fix(caja):`) y terminan con:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf`.
- El repo es público: ningún nombre de cliente, precio ni dato de tienda en código, pruebas o commits.

## Review Focus

- Admin sin `branch_id`: el orden nuevo no debe romper `DISTINCT` en Postgres (las columnas del ORDER BY tienen que estar en el SELECT: usar solo columnas de `Product`).
- Dos productos con el mismo nombre: el orden debe desempatar por `Product.id` para que las páginas no se crucen.
- CSV con costo en blanco y precio presente: costo 0, no NULL; un costo inválido sigue siendo error claro.
- Cierre que falla en el servidor (POS): el modal no debe pasar a "resultado" ni revelar el esperado; el turno sigue abierto.
- El conteo ciego no debe ocultar nada **después** del cierre: el panel de resultado muestra esperado, contado y diferencia del backend (`closed.difference`).

---

### Task 1: Orden determinista en `GET /api/products/`

**Files:**
- Modify: `app/modules/products/router/core.py` (`read_products`, justo antes de `total_count = query.count()`)
- Test: `tests/test_products_paginacion.py` (nuevo)

**Interfaces:**
- Consumes: `query_visible_products` (`app/crud/products.py`), que devuelve `Query[Product]` con `.distinct()` y documenta "El caller añade `.order_by()`".
- Produces: nada nuevo; el listado ahora sale ordenado por `Product.name`, `Product.id`.

Causa: `read_products` hace `offset/limit` sobre un `SELECT DISTINCT` sin `ORDER BY`. En Postgres cada página es una consulta aparte sin orden garantizado, así que entre páginas se repiten productos y se saltan otros (13 de 620 invisibles en una tienda real).

- [ ] **Step 1: Escribir la prueba que falla**

Crear `tests/test_products_paginacion.py`. Usar los fixtures `client`, `auth_admin`, `db`, `org` de `tests/conftest.py` (revisar ahí sus nombres exactos y cómo se crean productos; `tests/test_product_visibility.py` es buen ejemplo). La prueba:
1. Crea 7 productos activos en `org` con nombres desordenados y **dos con el mismo nombre** (p. ej. "Bolsa", "Abrigo", "Camisa", "Bolsa", "Zapato", "Gorra", "Pantalón"), cada uno con una variante.
2. Recorre `GET /api/products/?skip=N&limit=2` hasta que `items` venga vacío.
3. Afirma: la cantidad de ids distintos recorridos == `total` de la respuesta; no hay ids repetidos; la secuencia de nombres está ordenada (`nombres == sorted(nombres)`).

- [ ] **Step 2: Correrla y verla fallar**

Run: `python3 -m pytest -q tests/test_products_paginacion.py`
Expected: FAIL en la aserción de orden (SQLite devuelve por inserción).

- [ ] **Step 3: Implementar**

En `read_products`, antes de `total_count = query.count()`:

```python
    # Orden determinista: sin ORDER BY, cada página del SELECT DISTINCT sale en
    # el orden que Postgres quiera y entre páginas se repiten y se saltan
    # productos (visto en prod: total=620, recorrido=607). Desempate por id para
    # nombres repetidos. Solo columnas de Product: con DISTINCT, Postgres exige
    # que el ORDER BY esté en el SELECT.
    query = query.order_by(Product.name, Product.id)
```

- [ ] **Step 4: Correr la prueba y las vecinas**

Run: `python3 -m pytest -q tests/test_products_paginacion.py tests/test_product_visibility.py tests/test_regresion_productos.py`
Expected: PASS.

- [ ] **Step 5: Commit** `fix(products): el listado pagina en orden fijo y ya no pierde productos`

---

### Task 2: El importador CSV no deja costo NULL

**Files:**
- Modify: `scripts/import_products.py` (donde se calcula `costo = _num(...)`, ~línea 167)
- Test: `tests/test_import_products.py` (agregar una prueba a `TestImportacion`)

**Interfaces:**
- Consumes: `_num(valor, campo, fila) -> Optional[Decimal]` (devuelve `None` si está en blanco).
- Produces: `ProductVariant.cost` siempre numérico tras importar.

Causa: con "Costo unitario" vacío, `_num` devuelve `None` y la variante queda con `cost` NULL; los reportes de margen y la ficha tratan NULL distinto de 0 (trampa ya vista en un alta real).

- [ ] **Step 1: Prueba que falla** — en `TestImportacion`:

```python
    def test_costo_en_blanco_queda_en_cero(self, db, org, branch_a, tmp_path):
        fila = {**FILA, "Código": "FOL-02", "Costo unitario": ""}
        imp.import_products(db, _csv(tmp_path, [fila]), org.id, branch_a.id)
        v = db.query(ProductVariant).filter(
            ProductVariant.organization_id == org.id, ProductVariant.sku == "FOL-02").one()
        assert v.cost is not None, "costo NULL rompe margenes y ficha"
        assert float(v.cost) == 0.0
```

- [ ] **Step 2:** `python3 -m pytest -q tests/test_import_products.py -k costo_en_blanco` → FAIL (`v.cost is None`).

- [ ] **Step 3: Implementar** — justo después de `costo = _num(f.get("costo"), "costo unitario", nfila)`:

```python
        if costo is None:
            # Costo en blanco = 0, no NULL: margenes y ficha tratan NULL aparte.
            costo = Decimal("0")
```
(`Decimal` ya está importado en el archivo; verificarlo.)

- [ ] **Step 4:** `python3 -m pytest -q tests/test_import_products.py tests/test_import_products_variantes.py` → PASS.

- [ ] **Step 5: Commit** `fix(import): costo en blanco se importa como 0, no NULL`

---

### Task 3: Conteo ciego de verdad en las tres pantallas de cierre

**Files:**
- Modify: `frontend/src/utils/blindCash.ts` (+ `frontend/src/utils/blindCash.test.ts`)
- Modify: `frontend/src/components/pos/modals/CloseSessionModal.tsx`
- Modify: `frontend/src/pages/pos/POS.tsx` (callback `onConfirm` del `CloseSessionModal`, ~línea 968)
- Modify: `frontend/src/components/branch/CashBranchView.tsx` (modal de cierre ~líneas 160-310 y tarjetas "Esperado por método de pago" ~767)
- Modify: `frontend/src/pages/finance/CashHistory.tsx` (modal de cierre ~líneas 60-180)

**Interfaces:**
- Consumes: `cashApi.close(amount, notes?)` devuelve la sesión cerrada con `id` y `difference` (string, = contado − esperado, calculado en el backend). `cashApi.getSummary()` devuelve `expected_cash`.
- Produces: en `blindCash.ts`, `shouldRevealExpected(closed: boolean): boolean` (true solo con turno ya cerrado). Elimina la versión que recibía el texto capturado.

Problema (medido 2026-11-06): en `CashHistory` y `CashBranchView` basta escribir cualquier número para que aparezcan el esperado y la diferencia, y el campo sigue editable, así que se corrige hasta que cuadre; `CloseSessionModal` (POS) enseña el esperado desde que se abre. Por eso casi todos los cierres salen exactos.

Regla nueva: **mientras el turno esté abierto, ninguna de las tres pantallas muestra el efectivo esperado ni la diferencia**, ni al teclear. Tras confirmar el cierre, cada una muestra un resultado con Esperado, Contado y Diferencia tomados de la respuesta del backend (`expected = contado − Number(closed.difference)`), con el veredicto de `closeVerdict` (`frontend/src/theme/verdict`). No se toca el backend.

- [ ] **Step 1: Pruebas de `blindCash` que fallan** — en `blindCash.test.ts` reemplazar las de `shouldRevealExpected` por:

```ts
describe('shouldRevealExpected', () => {
  it('no revela con el turno abierto aunque haya conteo', () => {
    expect(shouldRevealExpected(false)).toBe(false)
  })
  it('revela solo con el turno cerrado', () => {
    expect(shouldRevealExpected(true)).toBe(true)
  })
})
```
Run: `cd frontend && npx vitest run src/utils/blindCash.test.ts` → FAIL.

- [ ] **Step 2: `blindCash.ts`** — cambiar la función y su comentario:

```ts
/**
 * El esperado y la diferencia se revelan solo con el turno YA cerrado.
 *
 * Antes se revelaban en cuanto el cajero tecleaba un conteo válido, y como el
 * campo seguía editable bastaba corregir el número hasta ver diferencia $0.
 */
export function shouldRevealExpected(closed: boolean): boolean {
  return closed
}
```
Actualizar el comentario de cabecera del archivo si contradice esto. Run vitest del archivo → PASS.

- [ ] **Step 3: `CloseSessionModal` (POS)** — dos pasos dentro del modal:
  - Paso captura: sin la tarjeta "Efectivo esperado" ni el veredicto en vivo. No llamar `cashApi.getSummary()` (ya no se usa aquí; quitar `expectedCash`, `loadingData` y el spinner).
  - Cambiar la prop a `onConfirm: (closingAmount: number, notes: string) => Promise<{ difference: string | number | null } | null>`. Si devuelve `null` (falló), el modal se queda en captura.
  - Paso resultado (tras éxito): Esperado (`contado − difference`), Contado, Diferencia con `closeVerdict(diff)`, y un botón "Listo" (`dax-btn-primary`) que llama `onClose`. Sin botón de cancelar en este paso; el fondo ya no cierra el modal (el turno ya está cerrado).
  - Mantener el estilo existente del archivo (este archivo ya usa `fixed inset-0`; no agregar overlays nuevos).
- [ ] **Step 4: `POS.tsx`** — en el `onConfirm` del `CloseSessionModal`: en el `catch`, `return null`. En éxito, conservar la impresión del corte y `store.setSession(null)`, **quitar** `setClosingSession(false)` de ahí (lo hace `onClose` al pulsar "Listo") y `return closed`.
- [ ] **Step 5: `CashBranchView.tsx`** — en el modal de cierre: el renglón "Esperado en caja" muestra siempre `BLIND_MASK` con `BLIND_LABEL` mientras no se haya cerrado, y la "Diferencia" en vivo desaparece. El panel de resultado que ya existe tras cerrar (`CloseResultPanel`/`result`, ~línea 334) queda igual. En las tarjetas "Esperado por método de pago" con turno abierto, el renglón de **efectivo** se enmascara con `BLIND_MASK` (los demás métodos no son conteo físico y se quedan).
- [ ] **Step 6: `CashHistory.tsx`** — en su modal de cierre: igual que el paso 5 (esperado enmascarado, sin diferencia en vivo). Tras `cashApi.close(...)` exitoso, en lugar de cerrar el modal en silencio, mostrar el resultado (Esperado, Contado, Diferencia con `closeVerdict`) y un botón "Listo". Si `CashBranchView` exporta o puede exportar su panel de resultado sin arrastrar dependencias, reutilizarlo; si no, un bloque pequeño local.
- [ ] **Step 7: Verificación**
  Run: `cd frontend && npx vitest run && npx tsc --noEmit -p .`
  Expected: todo PASS (incluye `coloresPorTokens`, `overlaysFueraDelKit`, `botonesDelKit`). Revisar con `grep -n "shouldRevealExpected" -r src` que no quede ninguna llamada con el texto capturado.
- [ ] **Step 8: Commit** `fix(caja): conteo ciego real; el esperado y la diferencia salen solo después de cerrar`
