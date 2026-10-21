# SP1-c · La ficha del POS deja de ser el sexto formulario — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el POS edite y dé de alta productos con `FormularioProducto` (el formulario único de SP1) y que `ProductDetailModal` quede como ficha de consulta de la cajera (existencia por talla, precios, agregar existencia, agregar al carrito).

**Architecture:** `ProductDetailModal` pierde sus modos `editing`/`create` (estado del formulario, escalones editables, empaques, foto, `productsApi.create/update`) y se monta sobre `components/ui/Modal`. "Editar" abre `components/pos/EditarProductoPos.tsx` (un `Modal size="xl"` con `FormularioProducto mode="edit"`), cargado con `lazy()` + `LimiteDeError` + precarga, igual que `AltaRapidaProducto`, para que el formulario no viaje en `POS-*.js`. "Nuevo producto" en el POS usa `AltaRapidaProducto` en todos los perfiles: la bandera `altaCorta` desaparece.

**Tech Stack:** React 18 + TS, vitest + testing-library (jsdom), `components/ui/Modal`, Playwright para capturas (herramienta del scratchpad `sp1c-ficha-pos/capturas/`).

**Spec:** `docs/superpowers/specs/2026-10-14-mega-plan-altas-docs-responsivo-agente-design.md` §SP1 ("un solo formulario de producto"); ruling de SP1 frontend T9 (ledger `sp1-frontend-ledger.md`): la ficha del POS quedó fuera y es este plan. Referencias: `docs/superpowers/plans/2026-10-16-sp1-altas-frontend-formulario-unico.md` (contrato de `FormularioProducto`), `docs/modo-basico.md` (`AltaRapidaProducto`, `opcionesPorPerfil`).

## Global Constraints

- Nunca push ni merge; commits con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf`.
- `app/routers/sales.py::create_sale` y el backend no se tocan. Solo `frontend/` y docs.
- Presupuesto de la ruta crítica: `python3 scripts/presupuesto_bundle.py` ≤ 452,500 B; el chunk `POS-*.js` (hoy 130,338 B) debe bajar o quedar igual. `FormularioProducto` NO puede entrar en `POS-*.js` (solo por `lazy()`).
- Render condicional, nunca `hidden`; un overlay nuevo solo con `components/ui/Modal` (`src/__tests__/overlaysFueraDelKit.test.ts`).
- `src/__tests__/unSoloFormularioDeProducto.test.ts`: al final solo `FormularioProducto` (2) y `pages/scanner/StoreScanner.tsx` (3) llaman `productsApi.create/update`.
- Vitest, `npm run build` (tsc) y el presupuesto deben pasar en cada commit. Un solo `pytest` a la vez por worktree (no aplica: no hay cambios de backend).
- Cambio de comportamiento aceptado y documentado: las reglas de alta propias del POS (costo > 0, código de barras y existencia inicial > 0 obligatorios) ceden a `validarProducto`/`campos_producto` del formulario único; la foto se sube desde el formulario (`ProductImageUploader`).

## Review Focus

1. **Carrito abierto + chunk viejo tras un deploy:** abrir "Editar" o "Nuevo producto" con un chunk `lazy()` que ya no existe no debe tirar el POS ni el carrito → `LimiteDeError` + toast, test de fuente en T2 y T3.
2. **Cajera sin sucursal asignada** pulsa "Agregar existencia" → mensaje "Tu usuario no tiene sucursal asignada", sin llamada al API (test T3).
3. **Producto del carrito que todavía no cargó** (`CartPanel.openDetail` pasa un producto parcial y luego `getById`) → la ficha pinta con lo parcial y se actualiza al llegar el completo; nunca "Editar" con `productId` vacío (test T3: Editar manda `product.id`).
4. **`canEdit=false` (modo básico, `opciones.editarProducto=false`)** → ni "Editar" ni "Agregar existencia"; sí "Agregar" al carrito (test T3).
5. **Guardar desde el editor refresca la ficha y al padre**: el precio/nombre nuevo se ve sin cerrar la ficha, y `onSaved` recarga el grid del buscador (test T3).

---

### Task 0: Herramienta de capturas y baseline (antes de tocar código)

**Files:**
- Scratchpad (fuera del repo): `/tmp/claude-1000/-mnt-d-Devs-atlas-one/88dd20d9-ffe0-4c18-b01a-da7647838260/scratchpad/sp1c-ficha-pos/capturas/` (copia de `modo-basico/capturas/`, puertos 8030/5200, `R` = este worktree).

- [ ] **Step 1:** Copiar la herramienta, cambiar puertos y la ruta `R`; añadir en `capturas.mjs` las acciones de `/pos`: `ficha-tallas` (buscar "Playera básica" → "Ver detalles"), `ficha-simple` ("Abrigo de lana" → "Ver detalles"), `editar` (ficha → `clic2` "Editar"), `alta` (`[aria-label="Crear nuevo producto"]`). Soporte de `clic2` (segundo clic dentro del overlay).
- [ ] **Step 2:** `bash stack.sh up` (SQLite propia + `datos_muestra.py`).
- [ ] **Step 3:** Baseline: `node capturas.mjs --out baseline/cajero --usuario demo_cajero_pos --rutas /pos --anchos 390,1440` y lo mismo con `demo_dueno_pos` en `baseline/dueno` (el ADMINISTRADOR no tiene `/pos` en `ROLE_ROUTES`; el DUEÑO sí). En el baseline `editar` abre la ficha en modo edición (botón "Editar" actual) y `alta` abre la ficha en modo create.
- [ ] **Step 4:** Anotar en el ledger: capturas, claves sin selector, taps < 44 a 390.

### Task 1: `EditarProductoPos` (editor del POS sobre el formulario único)

**Files:**
- Create: `frontend/src/components/pos/EditarProductoPos.tsx`
- Test: `frontend/src/components/pos/__tests__/EditarProductoPos.test.tsx`

**Interfaces:**
- Produces: `export default function EditarProductoPos({ productId, variantId, onClose, onGuardado }: { productId: string; variantId?: string | null; onClose: () => void; onGuardado: (p: Product) => void })`. Se importa SIEMPRE con `lazy(() => import('../EditarProductoPos'))` (default export, como `AltaRapidaProducto`).

- [ ] **Step 1: Write the failing test**

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'

// El formulario único se sustituye por un doble: aquí solo se prueba el envoltorio.
vi.mock('../../products/FormularioProducto', () => ({
  FormularioProducto: (p: { mode: string; productId?: string; variantId?: string; presentacion: string; onDone: (x: unknown) => void; onCancel: () => void }) => (
    <div>
      <span>doble:{p.mode}:{p.productId}:{p.variantId ?? '-'}:{p.presentacion}</span>
      <button onClick={() => p.onDone({ id: p.productId, name: 'Blusa', sku: 'BLU', price: 1 })}>guardar-doble</button>
      <button onClick={p.onCancel}>cancelar-doble</button>
    </div>
  ),
}))

const { default: EditarProductoPos } = await import('../EditarProductoPos')
afterEach(cleanup)

describe('EditarProductoPos', () => {
  it('monta el formulario único en edición dentro del Modal del kit', () => {
    render(<EditarProductoPos productId="p1" variantId="v2" onClose={() => {}} onGuardado={() => {}} />)
    expect(screen.getByText('Editar producto')).toBeTruthy()
    expect(screen.getByText('doble:edit:p1:v2:modal')).toBeTruthy()
  })

  it('al guardar avisa con el producto; al cancelar cierra', () => {
    const onGuardado = vi.fn(); const onClose = vi.fn()
    render(<EditarProductoPos productId="p1" onClose={onClose} onGuardado={onGuardado} />)
    fireEvent.click(screen.getByText('guardar-doble'))
    expect(onGuardado).toHaveBeenCalledWith(expect.objectContaining({ id: 'p1', name: 'Blusa' }))
    fireEvent.click(screen.getByText('cancelar-doble'))
    expect(onClose).toHaveBeenCalled()
  })

  it('no se cierra con Escape ni con el fondo (formulario largo)', () => {
    const onClose = vi.fn()
    render(<EditarProductoPos productId="p1" onClose={onClose} onGuardado={() => {}} />)
    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.click(screen.getByRole('dialog'))
    expect(onClose).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2:** `npx vitest run src/components/pos/__tests__/EditarProductoPos.test.tsx` → FAIL (módulo no existe).
- [ ] **Step 3: Implementación**

```tsx
import { Modal } from '../ui/Modal'
import { FormularioProducto } from '../products/FormularioProducto'
import type { Product } from '../../types/products'

/**
 * Edición desde el POS con el formulario único (SP1-c). POS.tsx y la ficha lo
 * cargan con `lazy()` para que el formulario no viaje en `POS-*.js`.
 */
export default function EditarProductoPos({ productId, variantId, onClose, onGuardado }: {
  productId: string
  variantId?: string | null
  onClose: () => void
  onGuardado: (producto: Product) => void
}) {
  return (
    <Modal open onClose={onClose} size="xl" closeOnBackdrop={false} closeOnEscape={false} title="Editar producto">
      <FormularioProducto mode="edit" productId={productId} variantId={variantId ?? undefined} presentacion="modal"
        onDone={onGuardado} onCancel={onClose} />
    </Modal>
  )
}
```

- [ ] **Step 4:** test → PASS. `npx tsc --noEmit -p .` limpio.
- [ ] **Step 5:** Commit `feat(pos): EditarProductoPos, el formulario único como editor del POS`.

### Task 2: Alta en el POS con `AltaRapidaProducto` en todos los perfiles

**Files:**
- Modify: `frontend/src/pages/pos/opcionesPos.ts` (quitar `altaCorta`), `frontend/src/pages/pos/__tests__/opcionesPos.test.ts`, `frontend/src/pages/pos/POS.tsx` (alta sin rama por perfil; precarga de `AltaRapidaProducto` y de `EditarProductoPos` cuando `canEditProducts`; quitar el import de `ProductDetailModal`), `docs/modo-basico.md` (fila POS: ya no "el alta rápida usa el formulario corto").
- Test: `frontend/src/pages/pos/__tests__/altaEnPos.test.ts` (guardia de fuente).

- [ ] **Step 1: Tests** — en `opcionesPos.test.ts` quitar `altaCorta` de los tres objetos esperados; nuevo `altaEnPos.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const pos = readFileSync(resolve(__dirname, '../POS.tsx'), 'utf8')

describe('alta y edición de producto en el POS (SP1-c)', () => {
  it('el POS ya no importa la ficha vieja ni decide el alta por perfil', () => {
    expect(pos).not.toMatch(/ProductDetailModal/)
    expect(pos).not.toMatch(/altaCorta/)
  })
  it('AltaRapidaProducto y EditarProductoPos van por lazy() con precarga y límite de error', () => {
    expect(pos).toMatch(/lazy\(\(\) => import\('\.\.\/\.\.\/components\/pos\/AltaRapidaProducto'\)\)/)
    expect(pos).toMatch(/import\('\.\.\/\.\.\/components\/pos\/EditarProductoPos'\)/)
    expect((pos.match(/<LimiteDeError/g) ?? []).length).toBeGreaterThanOrEqual(1)
  })
})
```

- [ ] **Step 2:** Correr ambos → FAIL.
- [ ] **Step 3: Implementación.** `opcionesPos.ts`: borrar la propiedad `altaCorta` de la interfaz y de `COMPLETO`/`BASICO`, y su doc-comment. `POS.tsx`: quitar el import de `ProductDetailModal`; la precarga pasa a

```ts
// Precarga de los chunks de alta/edición: si quedaron viejos tras un deploy, fallan aquí y no al abrirlos.
useEffect(() => {
  if (!canEditProducts) return
  void import('../../components/pos/AltaRapidaProducto').catch(() => {})
  void import('../../components/pos/EditarProductoPos').catch(() => {})
}, [canEditProducts])
```

(mover el `useEffect` debajo de la declaración de `canEditProducts`), y el bloque `{createProductOpen && (opciones.altaCorta ? (...) : (<ProductDetailModal .../>))}` queda solo con la rama de `AltaRapidaProducto` (con `LimiteDeError` + `Suspense`), sin `showToast('Producto creado')` (el formulario ya da el toast). Si `opciones` deja de usarse en POS.tsx, quitar también esa línea y el import.

- [ ] **Step 4:** tests → PASS; `npx tsc --noEmit -p .`.
- [ ] **Step 5:** `docs/modo-basico.md` fila POS: "descuentos, botón Cliente, dólares, editar producto, forzar precio por pieza" (sin la frase del alta). Commit `feat(pos): alta con el formulario único en todos los perfiles`.

### Task 3: `ProductDetailModal` como ficha de consulta sobre `ui/Modal`

**Files:**
- Rewrite: `frontend/src/components/pos/modals/ProductDetailModal.tsx` (1,077 → ≤ 450 líneas)
- Modify: `frontend/src/components/pos/ProductSearch.tsx` (quitar nada: la firma sin `mode` sigue igual), `frontend/src/components/pos/CartPanel.tsx` (igual), `frontend/src/__tests__/overlaysFueraDelKit.test.ts` (quitar la entrada `/components/pos/modals/ProductDetailModal.tsx`), `frontend/src/__tests__/unSoloFormularioDeProducto.test.ts` (quitar la excepción y su comentario).
- Test: `frontend/src/components/pos/__tests__/ProductDetailModal.test.tsx`

**Interfaces:**
- Consumes: `EditarProductoPos` (T1) vía `lazy()`; `inventoryApi.createAdjustment({ variant_id, quantity, branch_id, reason })`; `productsApi.getById(id)`; `useAuthStore` (`user.branch_id`); helpers de `../variantPicker`.
- Produces: `export function ProductDetailModal({ product, onClose, onAddToCart?, onSaved?, canEdit? }: Props)` — misma firma que hoy menos `mode`.

Comportamiento:
- `product === null` → `null`. Si no, `<Modal open onClose title={product.sale_name ?? product.name} size="md">`.
- Cuerpo, en orden: franja con la foto (o icono); SKU en mono; chip de talla elegida + "N en stock"/"Sin stock"; tabla de tallas (existencia y precio por talla, fila actual resaltada) si hay > 1; "Precios disponibles" (lista de escalones, misma lógica `viewTiers`); rejilla de meta (marca, departamento, stock mín., código, IVA); descripción.
- Si `canEdit`: botón "Editar" en la cabecera del cuerpo (abre el editor) y sección plegable "Agregar existencia" (selector de talla si > 1, cantidad, motivo, botón Agregar) — la lógica actual de `addStock`, incluidos los mensajes "Producto sin variante…", "Cantidad debe ser > 0", "Tu usuario no tiene sucursal asignada", y la recarga con `getById` + `onSaved`.
- Pie (`footer` del Modal): "Cerrar" y, si `onAddToCart && displayStock > 0`, "Agregar" (al carrito, cierra).
- Editor: estado `editando`; `<LimiteDeError onError={…toast.error('No se pudo abrir el editor. Recarga la página.')…}><Suspense fallback={null}><EditarProductoPos productId={product.id} variantId={selectedVariantId} onClose={() => setEditando(false)} onGuardado={(p) => { setRefreshed({ ...p, matched_variant_id: product.matched_variant_id ?? p.matched_variant_id }); setEditando(false); onSaved?.(p) }} /></Suspense></LimiteDeError>` cuando `editando`. (Ruling: el editor se monta encima de la ficha — dos portales del kit; el segundo queda arriba por orden en el DOM.)
- `live = refreshed ?? product` para todo lo que se pinta (como hoy).

- [ ] **Step 1: Write the failing tests**

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react'

const api = vi.hoisted(() => ({
  getById: vi.fn(),
  createAdjustment: vi.fn(),
}))
vi.mock('../../../api/products', () => ({ productsApi: { getById: api.getById } }))
vi.mock('../../../api/inventory', () => ({ inventoryApi: { createAdjustment: api.createAdjustment } }))
vi.mock('../../../store/toastStore', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))
// Editor doble: solo importa que se abra con el id y que avise al guardar.
vi.mock('../EditarProductoPos', () => ({
  default: (p: { productId: string; variantId?: string | null; onGuardado: (x: unknown) => void; onClose: () => void }) => (
    <div>
      <span>editor:{p.productId}:{p.variantId ?? '-'}</span>
      <button onClick={() => p.onGuardado({ ...blusa, name: 'Blusa nueva', price: 150 })}>guardar-editor</button>
      <button onClick={p.onClose}>cerrar-editor</button>
    </div>
  ),
}))

const { ProductDetailModal } = await import('../modals/ProductDetailModal')
const { useAuthStore } = await import('../../../store/authStore')

const v1 = { id: 'v1', sku: 'BLU-CH', variant_name: 'Rojo / CH', color: 'Rojo', size: 'CH', price: 100, stock_total: 3 }
const v2 = { id: 'v2', sku: 'BLU-M', variant_name: 'Rojo / M', color: 'Rojo', size: 'M', price: 100, stock_total: 0 }
const blusa = {
  id: 'p1', sku: 'BLU-CH', name: 'Blusa', price: 100, cost: 50, stock: 3, stock_total: 3, is_active: true,
  description: 'Lino', brand_id: 'b1', brand_name: 'Nike', department: null, department_name: 'Blusas', unit: null, image_url: null,
  barcode: '750', has_iva: true, tax_rate: 16, variants: [v1, v2], matched_variant_id: 'v1',
  prices: [{ id: 't1', price_name: 'Mayoreo', min_quantity: 6, unit_price: 90 }],
} as never

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ user: { id: 2, username: 'caja', role: 'CAJERO', branch_id: 20 } } as never)
})
afterEach(cleanup)

describe('ficha de consulta del POS (SP1-c)', () => {
  it('sin producto no pinta nada', () => {
    const { container } = render(<ProductDetailModal product={null} onClose={() => {}} />)
    expect(container.innerHTML).toBe('')
    expect(document.querySelector('[role=dialog]')).toBeNull()
  })

  it('pinta existencia y precio por talla, los escalones y la meta', () => {
    render(<ProductDetailModal product={blusa} onClose={() => {}} onAddToCart={() => {}} canEdit />)
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('Blusa')).toBeTruthy()
    expect(within(dialog).getByText('3 en stock')).toBeTruthy()
    expect(within(dialog).getByText('Rojo / M')).toBeTruthy()
    expect(within(dialog).getByText('sin existencia')).toBeTruthy()
    expect(within(dialog).getByText('Mayoreo')).toBeTruthy()
    expect(within(dialog).getByText('mín. 6u')).toBeTruthy()
    expect(within(dialog).getByText('Nike')).toBeTruthy()
    expect(within(dialog).getByText('Con IVA 16%')).toBeTruthy()
    expect(within(dialog).getByText('Agregar')).toBeTruthy()   // al carrito
  })

  it('sin permiso de edición: ni Editar ni Agregar existencia, pero sí al carrito', () => {
    render(<ProductDetailModal product={blusa} onClose={() => {}} onAddToCart={() => {}} canEdit={false} />)
    expect(screen.queryByText('Editar')).toBeNull()
    expect(screen.queryByText('Agregar existencia')).toBeNull()
    expect(screen.getByText('Agregar')).toBeTruthy()
  })

  it('Editar abre el formulario único con el producto y la talla; guardar refresca la ficha y avisa', async () => {
    const onSaved = vi.fn()
    render(<ProductDetailModal product={blusa} onClose={() => {}} canEdit onSaved={onSaved} />)
    fireEvent.click(screen.getByText('Editar'))
    expect(await screen.findByText('editor:p1:v1')).toBeTruthy()
    fireEvent.click(screen.getByText('guardar-editor'))
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ name: 'Blusa nueva' })))
    expect(screen.queryByText(/^editor:/)).toBeNull()
    expect(screen.getByText('Blusa nueva')).toBeTruthy()
  })

  it('Agregar existencia ajusta la talla elegida en la sucursal de la cajera y recarga', async () => {
    api.createAdjustment.mockResolvedValue({})
    api.getById.mockResolvedValue({ ...blusa, stock_total: 8, variants: [{ ...v1, stock_total: 8 }, v2] })
    const onSaved = vi.fn()
    render(<ProductDetailModal product={blusa} onClose={() => {}} canEdit onSaved={onSaved} />)
    fireEvent.click(screen.getByText('Agregar existencia'))
    fireEvent.change(screen.getByLabelText('Cantidad'), { target: { value: '5' } })
    fireEvent.click(screen.getByRole('button', { name: /^Agregar$/ }))
    await waitFor(() => expect(api.createAdjustment).toHaveBeenCalledWith({ variant_id: 'v1', quantity: 5, branch_id: 20, reason: 'Reposición POS' }))
    await screen.findByText('+5 agregadas al stock')
    expect(onSaved).toHaveBeenCalled()
    expect(screen.getByText('8 en stock')).toBeTruthy()
  })

  it('cajera sin sucursal: aviso y ninguna llamada', async () => {
    useAuthStore.setState({ user: { id: 2, username: 'caja', role: 'CAJERO', branch_id: null } } as never)
    render(<ProductDetailModal product={blusa} onClose={() => {}} canEdit />)
    fireEvent.click(screen.getByText('Agregar existencia'))
    fireEvent.change(screen.getByLabelText('Cantidad'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('button', { name: /^Agregar$/ }))
    expect(await screen.findByText('Tu usuario no tiene sucursal asignada')).toBeTruthy()
    expect(api.createAdjustment).not.toHaveBeenCalled()
  })

  it('Agregar al carrito manda el producto y cierra; sin existencia no hay botón', () => {
    const onAdd = vi.fn(); const onClose = vi.fn()
    render(<ProductDetailModal product={blusa} onClose={onClose} onAddToCart={onAdd} />)
    fireEvent.click(screen.getByText('Agregar'))
    expect(onAdd).toHaveBeenCalledWith(blusa); expect(onClose).toHaveBeenCalled()
    cleanup()
    render(<ProductDetailModal product={{ ...blusa, stock_total: 0, matched_variant_id: 'v2' }} onClose={() => {}} onAddToCart={onAdd} />)
    expect(screen.queryByText('Agregar')).toBeNull()
    expect(screen.getByText('Sin stock')).toBeTruthy()
  })
})
```

Nota: en la ficha nueva el botón de "Agregar existencia" dentro de la sección se llama "Agregar" (como hoy) y el del pie "Agregar" (al carrito). Para que los tests no choquen, el del pie lleva `aria-label="Agregar al carrito"` y texto "Agregar"; el de existencia lleva texto "Agregar" y `aria-label="Agregar existencia"`. El test del carrito usa `getByText('Agregar')` solo cuando la sección de existencia está plegada o `canEdit` es falso (así es en esos tests); el de existencia usa `getByRole('button', { name: 'Agregar existencia' })`. **Corregir los tests de arriba con esos nombres accesibles al escribirlos.**

- [ ] **Step 2:** `npx vitest run src/components/pos/__tests__/ProductDetailModal.test.tsx` → FAIL (la ficha vieja exige `mode`/pinta distinto).
- [ ] **Step 3: Reescribir la ficha.** Conservar: `TIER_PALETTE`/`paletteFor` (solo para la lista de precios), `MetaCell`, `viewTiers`, chip de talla, tabla de tallas, `addStock` (ahora dentro de una sección plegada `const [agregando, setAgregando] = useState(false)`), `refreshed`/`live`, `selectedVariantId`. Borrar: `initialTiers`, `TierSlot`, `DEFAULT_CREATE_TIERS`, `PackRow`, `Mode`, `editing`, `saving`, `error`, estados del formulario, `uploadImage`/`deleteImage`, `fileRef`, carga de marcas/departamentos, `cancelEdit`, `updateTier`/`bumpPrice`/`bumpMin`/`addTier`/`removeTier`, `save`, listeners propios de Escape/foco (los da el Modal) y el `fixed inset-0`. Envolver en `<Modal open onClose={onClose} title={…} size="md" footer={…}>`.
- [ ] **Step 4:** Tests → PASS. Quitar la entrada en `overlaysFueraDelKit.test.ts` y la excepción en `unSoloFormularioDeProducto.test.ts`; correr la suite completa de vitest; `npm run build`; `python3 scripts/presupuesto_bundle.py` (anotar bytes de `POS-*.js`).
- [ ] **Step 5:** Commit `refactor(pos): la ficha del producto es solo consulta; Editar abre el formulario único`.

### Task 4: Documentación

**Files:**
- Modify: `docs/FRONTEND_VIEWS.md` (l.181 componentes del POS: `ProductDetailModal` = ficha de consulta, `EditarProductoPos`, `AltaRapidaProducto`; l.313 y l.651: quitar la excepción de la ficha; queda solo `StoreScanner`), `docs/modo-basico.md` (si quedó algo de `altaCorta`), `CLAUDE.md` §5 "Esconder algo en modo básico" (no nombra `altaCorta`; verificar y no tocar si no hace falta).

- [ ] **Step 1:** Editar los tres puntos; añadir en FRONTEND_VIEWS una nota corta "SP1-c (2026-10-21): la ficha del POS ya no crea ni edita; las reglas de alta del POS (costo, código y existencia inicial obligatorios) ceden a `campos_producto`/`validarProducto`; la foto se sube desde el formulario".
- [ ] **Step 2:** `grep -rn "altaCorta" docs CLAUDE.md frontend/src` → vacío. Commit `docs(pos): ficha de consulta y formulario único en el POS`.

### Task 5: Verificación final con capturas

- [ ] **Step 1:** Con el stack arriba (`stack.sh`, Vite recarga sola), `node capturas.mjs --out final/cajero --usuario demo_cajero_pos --rutas /pos --anchos 390,1440` y `final/dueno` con `demo_dueno_pos`.
- [ ] **Step 2:** `node diff1440.mjs baseline/cajero final/cajero` y lo mismo para dueño: `_pos__1440__*` (la pantalla sin ficha) debe dar **0 px**; `__ficha-*`, `__editar`, `__alta` cambian por diseño (anotar px y revisar a ojo las capturas a 390 y 1440).
- [ ] **Step 3:** Revisar `desbordes.json`: 0 desbordes, 0 scroll interno a 390, taps < 44 en la ficha a 390 (anotar; los botones del pie los cubre `.dax-modal-footer`).
- [ ] **Step 4:** Resumen en `<workspace>/final-resumen.md` + ledger. Suite completa (vitest, build, presupuesto) una vez más sobre HEAD. `bash stack.sh down`.
