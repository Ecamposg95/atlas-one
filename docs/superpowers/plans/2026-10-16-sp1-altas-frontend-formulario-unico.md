# SP1 · Altas, frontend: un solo formulario de producto — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que crear y editar un producto desde cualquier pantalla (Catálogo del admin, lista de Productos de HQ, lista de Productos de sucursal, URL directa) pase por **un solo** componente `FormularioProducto`, con **una** validación y **un** armado de payload, y que los campos de la ficha boutique (género, modelo, material) se muestren según lo que el backend diga para el giro de la organización.

**Architecture:** el backend expone `campos_producto` dentro de `GET /api/users/me/context` (función pura `app/modules/products/campos.py`, decidida por preset y módulos). En el frontend la lógica de formulario se extrae a helpers puros en `components/products/productoForm.ts` (validar, armar payload de alta, armar payload de edición, traducir errores de la API) y a un componente `components/products/FormularioProducto.tsx` que reúne las secciones ya existentes más una sección nueva de empaques. Las tres pantallas que hoy tienen su propio formulario (`pages/admin/AdminProductCreate.tsx`, `ProductModal` en `pages/inventory/Products.tsx`, `ProductFormModal` en `components/branch/ProductsBranchView.tsx`) pasan a montar `FormularioProducto`, como página o dentro de `components/ui/Modal`. Se borra el código muerto (`CreateProductMiniModal`, ramas `isBranchEditor`).

**Tech Stack:** React 18 + TypeScript + Vite; Zustand; vitest (+ `@vitest-environment jsdom` y `@testing-library/react` para componentes); FastAPI + pytest (SQLite) para el campo nuevo del contexto.

**Spec:** `docs/superpowers/specs/2026-10-14-mega-plan-altas-docs-responsivo-agente-design.md` §4 SP1 (entregable "Frontend: un solo `ProductForm`…", principio 3 "una sola fuente de verdad para campos por giro"). Levantamiento del frontend (rutas y líneas exactas): copia en el scratchpad de la sesión `sp1-frontend-levantamiento.md`; si no está disponible, los rangos citados aquí bastan.

**Rama y base:** `feat/sp1-altas-frontend`, creada **desde `feat/sp1-altas-servicio-backend`** (commit `4cea4c5` o posterior) en el worktree `.worktrees/sp1-altas-frontend`. Las líneas citadas corresponden a esa base.

## Global Constraints

- `cd frontend && npm run build` (es `tsc && vite build`) debe pasar al final de **cada** tarea; el CI lo exige.
- Sin dependencias nuevas en `frontend/package.json` ni en `requirements.txt`.
- Idioma del código nuevo: nombres y comentarios en español, como el resto del repo; los nombres de props/campos que ya existen en inglés (`price_name`, `initial_stock`…) se conservan.
- Estilos: se siguen usando las clases `dax-input`, `dax-btn-primary`, `dax-btn-secondary` y `DaxCard`; **el único mecanismo de modal para el formulario es `components/ui/Modal`** (principio 2 del spec). No se crean overlays a mano nuevos.
- El backend **no cambia de comportamiento** salvo el campo nuevo `campos_producto` en `/api/users/me/context`. Nada de migraciones.
- Reglas del payload que el backend ya exige y el formulario debe respetar: precio **> 0** (`validar_precio`, `app/modules/products/services/productos.py`); `packaging_units` y `prices` se **reemplazan completos** cuando viajan, así que el formulario solo los manda cuando los cargó desde `GET /api/products/{id}` (en edición) o cuando el usuario los capturó (en alta); `target_branch_ids` solo lo manda un ADMINISTRADOR/DUEÑO.
- Regla de "nada se apaga" (spec, principio 1): un campo oculto por preset **se muestra igual** si el producto que se edita ya trae valor en él.
- La suite de vitest corre con `cd frontend && npx vitest run`; pytest con `python3 -m pytest -q --ignore=tests/test_cash_complete.py` desde la raíz del worktree. Un solo proceso de pytest por worktree.
- Commits con prefijo `feat(products-ui):` / `refactor(products-ui):` / `test(products-ui):` y las líneas `Co-Authored-By` / `Claude-Session` del harness.

## Review Focus

1. **Editar una talla que no es la principal desde la lista de sucursal** (renglón "M" de un producto con tallas): el SKU y el código capturados deben ir a `PUT /products/variants/{id}` y **nunca** a `PUT /products/{id}`, que sobrescribiría la principal. Prueba en Tarea 4 (`armarPayloadEdicion` con `variantId` no principal) y Tarea 6.
2. **Editar desde el Catálogo un producto con empaques**: al guardar, los empaques deben seguir existiendo. Antes `ProductForm` no los mandaba (los conservaba) y `ProductModal` sí; el formulario único los carga y los manda. Prueba en Tarea 6 (payload de edición incluye los empaques cargados).
3. **Organización sin el módulo `variants`**: el alta no manda `color`, `size` ni `extra_variants`. Prueba en Tarea 4.
4. **Organización ATLAS_POS (Kaory, Coqueta) que edita un producto que ya trae `gender`**: el campo se ve y se manda aunque el preset lo oculte. Prueba en Tarea 5 (`campoVisible`) y Tarea 6.
5. **`/api/users/me/context` falla o no trae `campos_producto`**: el formulario muestra todos los campos (falla abierto), exactamente como hoy. Prueba en Tarea 2.

---

### Task 1: Backend — `campos_producto` por preset en `/me/context`

**Files:**
- Create: `app/modules/products/campos.py`
- Modify: `app/modules/users/router.py:117-122` (final de `read_user_context`, junto a `capacidades`)
- Modify: `docs/API_REFERENCE.md` (fila de `GET /api/users/me/context`)
- Test: `tests/test_campos_producto.py`

**Interfaces:**
- Produces: `campos_producto(preset: str | None, modulos: Iterable[str]) -> dict` con la forma `{"visibles": [...], "ocultos": [...]}`. `ocultos` lista las claves de la ficha boutique (`gender`, `model`, `material`) cuando el preset no es boutique; `visibles` lista todo lo demás más la ficha cuando sí lo es. La clave `variants` aparece en `visibles` solo si el módulo `variants` está encendido.
- Consumed by: Tarea 2 (store del frontend).

- [ ] **Step 1: Escribir las pruebas que fallan**

```python
"""Qué campos del formulario de producto ve cada giro (principio 3 del mega plan)."""
from app.modules.products.campos import CAMPOS_FICHA, campos_producto
from app.modules.tenants.models import IndustryType


def test_boutique_ve_la_ficha():
    r = campos_producto("ATLAS_POS_BOUTIQUE", ["core", "catalog", "variants"])
    assert set(CAMPOS_FICHA) <= set(r["visibles"])
    assert r["ocultos"] == []
    assert "variants" in r["visibles"]


def test_pos_normal_esconde_la_ficha_y_sin_modulo_no_hay_variantes():
    r = campos_producto("ATLAS_POS", ["core", "catalog"])
    assert r["ocultos"] == list(CAMPOS_FICHA)
    assert not (set(CAMPOS_FICHA) & set(r["visibles"]))
    assert "variants" not in r["visibles"]
    # Lo básico siempre va.
    for clave in ("name", "sku", "price", "cost", "packaging_units", "prices", "uses_inventory"):
        assert clave in r["visibles"]


def test_sin_preset_falla_abierto():
    r = campos_producto(None, [])
    assert r["ocultos"] == []
    assert set(CAMPOS_FICHA) <= set(r["visibles"])


def test_contexto_trae_campos_producto(client, db, auth_admin, org):
    org.industry_type = IndustryType.ATLAS_POS_BOUTIQUE
    db.commit()
    r = client.get("/api/users/me/context",
                   headers={**auth_admin, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert "campos_producto" in cuerpo
    assert "gender" in cuerpo["campos_producto"]["visibles"]
    assert cuerpo["campos_producto"]["ocultos"] == []
```

- [ ] **Step 2: Correr y ver que falla**

Run: `python3 -m pytest -q tests/test_campos_producto.py`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.modules.products.campos'`.

- [ ] **Step 3: Implementar `campos.py`**

```python
"""Catálogo de campos del producto por giro (mega plan 2026-10, principio 3).

Una sola fuente de verdad que consumen el formulario (hoy), el importador y el
asistente (después). Aquí solo se decide QUÉ se ve; nunca se borra ni se apaga
nada: un producto que ya trae un campo oculto lo sigue mostrando (eso lo
resuelve el frontend con el valor en mano).
"""
from typing import Iterable, Optional

# Siempre presentes, para cualquier giro.
CAMPOS_BASE = (
    "name", "sku", "barcode", "unit", "description", "image_url",
    "department_id", "brand_id", "price", "cost", "has_iva", "tax_rate",
    "initial_stock", "prices", "packaging_units", "uses_inventory",
)
# Ficha boutique: nombre de venta y etiqueta de ropa/calzado.
CAMPOS_FICHA = ("gender", "model", "material")
# Presets que capturan la ficha. El resto la esconde (sin apagarla).
PRESETS_CON_FICHA = frozenset({"ATLAS_POS_BOUTIQUE"})


def campos_producto(preset: Optional[str], modulos: Iterable[str]) -> dict:
    """`{"visibles": [...], "ocultos": [...]}` para el preset y módulos dados.

    Sin preset (org recién creada, contexto de plataforma) se falla abierto:
    todo visible. `variants` solo es visible con el módulo encendido.
    """
    con_ficha = preset is None or preset in PRESETS_CON_FICHA
    visibles = list(CAMPOS_BASE)
    if con_ficha:
        visibles.extend(CAMPOS_FICHA)
    if "variants" in set(modulos):
        visibles.append("variants")
    ocultos = [] if con_ficha else list(CAMPOS_FICHA)
    return {"visibles": visibles, "ocultos": ocultos}
```

- [ ] **Step 4: Exponerlo en el contexto**

En `app/modules/users/router.py`, justo después de `ctx["capacidades"] = resolver(ctx["enabled_modules"])` y antes de `return ctx`:

```python
    # Campos del formulario de producto según el giro (mega plan, principio 3).
    from app.modules.products.campos import campos_producto
    ctx["campos_producto"] = campos_producto(ctx["preset"], ctx["enabled_modules"])
```

- [ ] **Step 5: Correr las pruebas**

Run: `python3 -m pytest -q tests/test_campos_producto.py tests/test_contexto_capacidades.py`
Expected: PASS (4 + 3).

- [ ] **Step 6: Documentar y correr la suite**

En `docs/API_REFERENCE.md`, en la fila de `GET /api/users/me/context`, añadir al final de la descripción: "· `campos_producto` `{visibles, ocultos}`: qué campos del formulario de producto muestra el giro (ficha boutique `gender/model/material` solo en `ATLAS_POS_BOUTIQUE`; `variants` solo con el módulo)". Si el archivo tiene CRLF, conservarlo (`file docs/API_REFERENCE.md`).

Run: `python3 -m pytest -q --ignore=tests/test_cash_complete.py`
Expected: 1422 passed (1418 de la base + 4), 0 failed.

- [ ] **Step 7: Commit**

```bash
git add app/modules/products/campos.py app/modules/users/router.py tests/test_campos_producto.py docs/API_REFERENCE.md
git commit -m "feat(products): campos_producto por preset en /me/context"
```

---

### Task 2: Frontend — el store lee `campos_producto` y un helper decide la visibilidad

**Files:**
- Create: `frontend/src/components/products/camposProducto.ts`
- Modify: `frontend/src/store/enabledModulesStore.ts:19-81`
- Test: `frontend/src/components/products/__tests__/camposProducto.test.ts`
- Test: `frontend/src/store/enabledModulesStore.test.ts`

**Interfaces:**
- Produces: `interface CamposProducto { visibles: string[]; ocultos: string[] }`, `TODO_VISIBLE: CamposProducto`, `campoVisible(campos, clave, valorActual?) => boolean`, `leerCamposProducto(crudo: unknown) => CamposProducto`; en el store, el estado `camposProducto: CamposProducto` y el hook `useCamposProducto()`.
- Consumed by: Tareas 5 y 6.

- [ ] **Step 1: Pruebas del helper (fallan)**

```ts
import { describe, it, expect } from 'vitest'
import { campoVisible, leerCamposProducto, TODO_VISIBLE } from '../camposProducto'

describe('campoVisible', () => {
  const pos = { visibles: ['name', 'sku'], ocultos: ['gender', 'model', 'material'] }

  it('esconde la ficha boutique cuando el giro la oculta', () => {
    expect(campoVisible(pos, 'gender')).toBe(false)
    expect(campoVisible(pos, 'model', '')).toBe(false)
  })

  it('nada se apaga: un producto que ya trae el valor lo sigue mostrando', () => {
    expect(campoVisible(pos, 'gender', 'MUJER')).toBe(true)
    expect(campoVisible(pos, 'material', '  piel ')).toBe(true)
  })

  it('lo que no está en ocultos se ve', () => {
    expect(campoVisible(pos, 'price')).toBe(true)
    expect(campoVisible(TODO_VISIBLE, 'gender')).toBe(true)
  })
})

describe('leerCamposProducto', () => {
  it('falla abierto si el contexto no trae el campo o viene roto', () => {
    expect(leerCamposProducto(undefined)).toEqual(TODO_VISIBLE)
    expect(leerCamposProducto({ visibles: 'x' })).toEqual(TODO_VISIBLE)
  })
  it('acepta la forma del servidor', () => {
    expect(leerCamposProducto({ visibles: ['name'], ocultos: ['gender'] }))
      .toEqual({ visibles: ['name'], ocultos: ['gender'] })
  })
})
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/components/products/__tests__/camposProducto.test.ts`
Expected: FAIL, el módulo `../camposProducto` no existe.

- [ ] **Step 3: Implementar el helper**

```ts
/**
 * Campos del formulario de producto por giro. El servidor decide
 * (`campos_producto` en /users/me/context); aquí solo se lee y se aplica la
 * regla "nada se apaga": un campo oculto por preset se muestra igual si el
 * producto ya trae valor.
 */
export interface CamposProducto {
  visibles: string[]
  ocultos: string[]
}

export const TODO_VISIBLE: CamposProducto = { visibles: [], ocultos: [] }

export function campoVisible(campos: CamposProducto, clave: string, valorActual?: string | null): boolean {
  if (valorActual != null && String(valorActual).trim() !== '') return true
  return !campos.ocultos.includes(clave)
}

/** Lee lo que mande el servidor; cualquier cosa rara = todo visible. */
export function leerCamposProducto(crudo: unknown): CamposProducto {
  const c = crudo as { visibles?: unknown; ocultos?: unknown } | null | undefined
  if (!c || !Array.isArray(c.visibles) || !Array.isArray(c.ocultos)) return TODO_VISIBLE
  return {
    visibles: c.visibles.filter((x): x is string => typeof x === 'string'),
    ocultos: c.ocultos.filter((x): x is string => typeof x === 'string'),
  }
}
```

- [ ] **Step 4: Prueba del store (falla)**

Sigue el patrón de `src/store/cardSurchargeStore.test.ts` (único `vi.mock` del repo):

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

const get = vi.fn()
vi.mock('../api/client', () => ({ default: { get: (...a: unknown[]) => get(...a) } }))

const { useEnabledModulesStore } = await import('./enabledModulesStore')

beforeEach(() => {
  useEnabledModulesStore.getState().reset()
  get.mockReset()
})

describe('enabledModulesStore: campos_producto', () => {
  it('guarda lo que manda el contexto', async () => {
    get.mockResolvedValue({ data: {
      enabled_modules: ['core', 'variants'], preset: 'ATLAS_POS', capacidades: [],
      campos_producto: { visibles: ['name'], ocultos: ['gender', 'model', 'material'] },
    } })
    await useEnabledModulesStore.getState().load()
    expect(useEnabledModulesStore.getState().camposProducto.ocultos).toEqual(['gender', 'model', 'material'])
  })

  it('sin el campo, o si el contexto falla, todo es visible', async () => {
    get.mockResolvedValue({ data: { enabled_modules: ['core'], preset: null, capacidades: [] } })
    await useEnabledModulesStore.getState().load()
    expect(useEnabledModulesStore.getState().camposProducto).toEqual({ visibles: [], ocultos: [] })

    useEnabledModulesStore.getState().reset()
    get.mockRejectedValue(new Error('red'))
    await useEnabledModulesStore.getState().load()
    expect(useEnabledModulesStore.getState().camposProducto).toEqual({ visibles: [], ocultos: [] })
  })
})
```

- [ ] **Step 5: Modificar el store**

En `enabledModulesStore.ts`:

```ts
import { leerCamposProducto, TODO_VISIBLE, type CamposProducto } from '../components/products/camposProducto'

interface ContextResponse {
  enabled_modules?: string[]
  preset?: string | null
  capacidades?: string[]
  campos_producto?: unknown
  // (other fields present in /me/context but not needed here)
}

interface EnabledModulesStore {
  enabledModules: string[]
  preset: string | null
  capacidades: string[]
  /** Campos del formulario de producto según el giro; falla abierto. */
  camposProducto: CamposProducto
  loaded: boolean
  loading: boolean
  load: () => Promise<void>
  reset: () => void
}
```

Estado inicial: `camposProducto: TODO_VISIBLE`. En `load()`, en el `set` del éxito: `camposProducto: leerCamposProducto(r.data?.campos_producto)`; en el `catch` y en `reset()`: `camposProducto: TODO_VISIBLE`. Al final del archivo:

```ts
/** Campos del formulario de producto que ve este giro. */
export const useCamposProducto = (): CamposProducto =>
  useEnabledModulesStore((s) => s.camposProducto)
```

Si la rama ya trae `plan` en este store (viene de SP2), no tocarlo: solo se añade `camposProducto`.

- [ ] **Step 6: Correr las dos pruebas y el build**

Run: `cd frontend && npx vitest run src/components/products/__tests__/camposProducto.test.ts src/store/enabledModulesStore.test.ts && npm run build`
Expected: PASS (5 + 2) y build verde.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/products/camposProducto.ts frontend/src/components/products/__tests__/camposProducto.test.ts frontend/src/store/enabledModulesStore.ts frontend/src/store/enabledModulesStore.test.ts
git commit -m "feat(products-ui): el store lee campos_producto y campoVisible aplica 'nada se apaga'"
```

---

### Task 3: Tipos de la API exportados y `PackagingRow` compartido

**Files:**
- Modify: `frontend/src/api/products.ts:20-67` (exportar `ProductPricePayload`, `PackagingUnitPayload`, `ProductCreate`; crear `ProductUpdate`) y `:259` (`update` tipa con `ProductUpdate`)
- Modify: `frontend/src/components/products/types.ts` (añadir `uses_inventory` al form, `PackagingRow`, `emptyPackagingRow`)
- Test: `frontend/src/components/products/__tests__/types.test.ts`

**Interfaces:**
- Produces: `export interface ProductCreate` (igual que hoy), `export type ProductUpdate = Partial<ProductCreate>`, `export interface PackagingUnitPayload`, `export interface ProductPricePayload`; en `types.ts`: `ProductFormValue.uses_inventory: boolean` (default `true` en `EMPTY_PRODUCT_FORM`), `interface PackagingRow { id?: string; name: string; barcode: string; units_per_package: number; package_price: number }`, `emptyPackagingRow()`.
- Consumed by: Tareas 4, 5, 6.

- [ ] **Step 1: Prueba (falla)**

```ts
import { describe, it, expect } from 'vitest'
import { EMPTY_PRODUCT_FORM, emptyPackagingRow } from '../types'

describe('types del formulario', () => {
  it('el producto nace llevando inventario', () => {
    expect(EMPTY_PRODUCT_FORM.uses_inventory).toBe(true)
  })
  it('un empaque nuevo es una caja de 1 pieza a $0', () => {
    expect(emptyPackagingRow()).toEqual({ name: 'Caja', barcode: '', units_per_package: 1, package_price: 0 })
  })
})
```

Run: `cd frontend && npx vitest run src/components/products/__tests__/types.test.ts` → FAIL (`uses_inventory` undefined, `emptyPackagingRow` no existe).

- [ ] **Step 2: Cambios en `types.ts`**

Añadir a `ProductFormValue`, después de `tax_rate: string`:

```ts
  /** false = servicio o producto sin existencias (no descuenta inventario). */
  uses_inventory: boolean
```

En `EMPTY_PRODUCT_FORM`, después de `tax_rate: '16',`: `uses_inventory: true,`. Al final del archivo, antes del `export type { Brand, Department, Branch }`:

```ts
/** Fila editable de empaque (caja, master…). */
export interface PackagingRow {
  id?: string
  name: string
  barcode: string
  units_per_package: number
  package_price: number
}

export const emptyPackagingRow = (): PackagingRow => ({ name: 'Caja', barcode: '', units_per_package: 1, package_price: 0 })
```

- [ ] **Step 3: Cambios en `api/products.ts`**

Anteponer `export` a `interface ProductPricePayload`, `interface PackagingUnitPayload` e `interface ProductCreate`. Debajo de `ProductCreate` añadir:

```ts
/** PUT /products/{id}: parcial; lo que no viaja no se toca (incluidos `prices` y `packaging_units`). */
export type ProductUpdate = Partial<ProductCreate>
```

Cambiar la firma `update: async (id: string, payload: Partial<ProductCreate>)` por `update: async (id: string, payload: ProductUpdate)`.

- [ ] **Step 4: Prueba y build**

Run: `cd frontend && npx vitest run src/components/products/__tests__/types.test.ts && npm run build`
Expected: PASS y build verde (ningún consumidor se rompe: `uses_inventory` se añade con valor por defecto y los objetos literales que llenan `ProductFormValue` en `AdminProductCreate.tsx:~90` y `ProductForm.tsx:91-109` deben recibir `uses_inventory: p.uses_inventory ?? true` / `true`; si `tsc` los acusa, añadirlo ahí: esos archivos se borran o reescriben en las Tareas 7-8).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/products.ts frontend/src/components/products/types.ts frontend/src/components/products/__tests__/types.test.ts frontend/src/pages/products/ProductForm.tsx frontend/src/pages/admin/AdminProductCreate.tsx
git commit -m "refactor(products-ui): exporta ProductCreate/ProductUpdate y comparte PackagingRow"
```

---

### Task 4: Helpers puros del formulario: validar, armar payloads, leer un producto y traducir errores

**Files:**
- Create: `frontend/src/components/products/productoForm.ts`
- Test: `frontend/src/components/products/__tests__/productoForm.test.ts`

**Interfaces:**
- Consumes: `ProductFormValue`, `PriceRow`, `PackagingRow`, `ProductErrors` (`types.ts`); `VariantRow`, `splitPrincipal`, `toExtraVariants`, `variantDetailErrors`, `variantFieldErrors` (`variantMatrix.ts`); `planIdentidadDeFila`, `esFilaPrincipal` (`components/branch/variantEdit.ts`); `fieldErrorsFromDetail`, `summarizeFieldErrors` (`utils/apiErrors`); `ProductCreate`, `ProductUpdate` (`api/products.ts`); `Product` (`types/products.ts`).
- Produces (firmas exactas):

```ts
export interface EntradaFormulario {
  form: ProductFormValue
  mode: 'create' | 'edit'
  isAdmin: boolean
  userBranchId: number | null
  enabledBranchIds: number[]
  prices: PriceRow[]
  packagings: PackagingRow[]
  variantRows: VariantRow[]
  hasVariantsModule: boolean
}
export function stockHermanas(variantRows: VariantRow[], hasVariantsModule: boolean): number
export function totalInicial(form: ProductFormValue, variantRows: VariantRow[], hasVariantsModule: boolean): number
export function validarProducto(e: EntradaFormulario): ProductErrors
export function armarPayloadAlta(e: EntradaFormulario): ProductCreate
export interface EntradaEdicion extends EntradaFormulario { loaded: Product; variantId?: string; precioATodas: boolean }
export interface PlanEdicion {
  productPatch: ProductUpdate
  variantPatch: { variantId: string; patch: { sku?: string; barcode?: string | null } } | null
}
export function armarPayloadEdicion(e: EntradaEdicion): PlanEdicion
export interface EstadoDesdeProducto { form: ProductFormValue; prices: PriceRow[]; packagings: PackagingRow[] }
export function formDesdeProducto(p: Product, variantId?: string): EstadoDesdeProducto
export interface ErroresDeApi { errors: ProductErrors; mensaje: string }
export function erroresDeApi(err: unknown, variantRows: VariantRow[], mode: 'create' | 'edit'): ErroresDeApi
```

- [ ] **Step 1: Pruebas (fallan)**

```ts
import { describe, it, expect } from 'vitest'
import {
  armarPayloadAlta, armarPayloadEdicion, erroresDeApi, formDesdeProducto, totalInicial, validarProducto,
  type EntradaFormulario,
} from '../productoForm'
import { EMPTY_PRODUCT_FORM } from '../types'
import type { VariantRow } from '../variantMatrix'
import type { Product } from '../../../types/products'

const fila = (p: Partial<VariantRow>): VariantRow => ({
  key: 'k', color: '', size: '', sku: '', barcode: '', price: '', initial_stock: '', ...p,
})

const base = (extra: Partial<EntradaFormulario> = {}): EntradaFormulario => ({
  form: { ...EMPTY_PRODUCT_FORM, name: 'Tenis', sku: 'NK-TENIS', price: '4000', cost: '1500' },
  mode: 'create', isAdmin: true, userBranchId: null, enabledBranchIds: [20],
  prices: [], packagings: [], variantRows: [], hasVariantsModule: false,
  ...extra,
})

describe('validarProducto', () => {
  it('exige precio mayor a cero, como el backend', () => {
    expect(validarProducto(base({ form: { ...base().form, price: '0' } })).price).toBe('Precio mayor a 0')
    expect(validarProducto(base()).price).toBeUndefined()
  })
  it('admin: sucursal activa y sucursal de la existencia si hay piezas', () => {
    const e = validarProducto(base({ enabledBranchIds: [], form: { ...base().form, initial_stock: '3' } }))
    expect(e.target_branch_ids).toBe('Activa al menos una sucursal')
    expect(e.initial_stock_branch_id).toBe('Requerido con existencia inicial')
  })
  it('la existencia de las tallas hermanas también exige sucursal', () => {
    const rows = [fila({ key: 'a', size: '40', sku: 'NK-TENIS-40' }), fila({ key: 'b', size: '41', sku: 'NK-TENIS-41', initial_stock: '2' })]
    const e = validarProducto(base({ variantRows: rows, hasVariantsModule: true }))
    expect(e.initial_stock_branch_id).toBe('Requerido con existencia inicial')
  })
  it('cajero sin sucursal no puede dar de alta', () => {
    expect(validarProducto(base({ isAdmin: false, userBranchId: null })).target_branch_ids)
      .toBe('Tu usuario no tiene sucursal asignada')
  })
  it('empaques: unidades mayores a 0 y precio numérico', () => {
    const e = validarProducto(base({ packagings: [{ name: '', barcode: '', units_per_package: 0, package_price: -1 }] }))
    expect(e['packaging.0.name']).toBe('Requerido')
    expect(e['packaging.0.units_per_package']).toBe('Unidades mayores a 0')
    expect(e['packaging.0.package_price']).toBe('Número ≥ 0')
  })
  it('matriz: SKU de talla requerido y no repetido (incluye el base)', () => {
    const rows = [fila({ key: 'a', size: '40', sku: 'NK-TENIS-40' }), fila({ key: 'b', size: '41', sku: 'nk-tenis' })]
    const e = validarProducto(base({ variantRows: rows, hasVariantsModule: true }))
    expect(e['variants.0.sku']).toBe('SKU repetido')
  })
  it('en edición no valida stock ni sucursales', () => {
    const e = validarProducto(base({ mode: 'edit', enabledBranchIds: [], form: { ...base().form, initial_stock: '-1' } }))
    expect(e.target_branch_ids).toBeUndefined()
    expect(e.initial_stock).toBeUndefined()
  })
})

describe('armarPayloadAlta', () => {
  it('sin módulo de variantes no viajan color, talla ni extra_variants', () => {
    const p = armarPayloadAlta(base({ variantRows: [fila({ size: '40', sku: 'X-40' })], hasVariantsModule: false }))
    expect(p.color).toBeUndefined(); expect(p.size).toBeUndefined(); expect(p.extra_variants).toBeUndefined()
    expect(p.uses_inventory).toBe(true)
    expect(p.branch_id).toBeNull()
    expect(p.target_branch_ids).toEqual([20])
  })
  it('con matriz: la primera fila es la principal y las demás van en extra_variants', () => {
    const rows = [fila({ key: 'a', color: 'Negro', size: '40', sku: 'NK-TENIS-NEG-40', initial_stock: '1' }),
      fila({ key: 'b', color: 'Negro', size: '41', sku: 'NK-TENIS-NEG-41', initial_stock: '2', price: '4200' })]
    const p = armarPayloadAlta(base({ variantRows: rows, hasVariantsModule: true,
      form: { ...base().form, initial_stock: '1', initial_stock_branch_id: '20' } }))
    expect(p.color).toBe('Negro'); expect(p.size).toBe('40')
    expect(p.extra_variants).toEqual([{ color: 'Negro', size: '41', sku: 'NK-TENIS-NEG-41', price: 4200, initial_stock: 2 }])
    expect(p.branch_id).toBe(20)
  })
  it('cajero: la sucursal es la suya y no manda target_branch_ids', () => {
    const p = armarPayloadAlta(base({ isAdmin: false, userBranchId: 7, enabledBranchIds: [7],
      form: { ...base().form, initial_stock: '2' } }))
    expect(p.branch_id).toBe(7)
    expect(p.target_branch_ids).toBeUndefined()
  })
  it('manda empaques y escalones capturados; sin IVA la tasa es 0', () => {
    const p = armarPayloadAlta(base({
      prices: [{ price_name: 'Mayoreo', min_quantity: 6, unit_price: 3500 }],
      packagings: [{ name: 'Caja', barcode: '', units_per_package: 12, package_price: 40000 }],
    }))
    expect(p.prices).toEqual([{ price_name: 'Mayoreo', min_quantity: 6, unit_price: 3500 }])
    expect(p.packaging_units).toEqual([{ name: 'Caja', barcode: null, units_per_package: 12, package_price: 40000 }])
    expect(p.tax_rate).toBe(0)
  })
})

const producto = (extra: Partial<Product> = {}): Product => ({
  id: 'p1', name: 'Tenis', sku: 'NK-TENIS-NEG-40', price: 4000, cost: 1500, unit: 'pza',
  is_active: true, uses_inventory: true,
  variants: [
    { id: 'v1', sku: 'NK-TENIS-NEG-40', color: 'Negro', size: '40', price: 4000, cost: 1500, barcode: '111' },
    { id: 'v2', sku: 'NK-TENIS-NEG-41', color: 'Negro', size: '41', price: 4000, cost: 1500, barcode: '222' },
  ],
  prices: [{ id: 'pr1', price_name: 'Mayoreo', min_quantity: 6, unit_price: 3500, linked_package_id: null }],
  packaging_units: [{ id: 'pk1', name: 'Caja', barcode: null, units_per_package: 12, package_price: 40000 }],
  ...extra,
} as Product)

describe('formDesdeProducto', () => {
  it('lee precio y código de la principal, y carga escalones y empaques', () => {
    const s = formDesdeProducto(producto())
    expect(s.form.sku).toBe('NK-TENIS-NEG-40'); expect(s.form.barcode).toBe('111'); expect(s.form.price).toBe('4000')
    expect(s.form.uses_inventory).toBe(true)
    expect(s.prices).toEqual([{ id: 'pr1', price_name: 'Mayoreo', min_quantity: 6, unit_price: 3500 }])
    expect(s.packagings).toEqual([{ id: 'pk1', name: 'Caja', barcode: '', units_per_package: 12, package_price: 40000 }])
  })
  it('con una talla no principal, SKU y código son los de esa talla', () => {
    const s = formDesdeProducto(producto(), 'v2')
    expect(s.form.sku).toBe('NK-TENIS-NEG-41'); expect(s.form.barcode).toBe('222')
  })
})

describe('armarPayloadEdicion', () => {
  const entrada = (variantId?: string, extra: Partial<EntradaFormulario> = {}) => {
    const s = formDesdeProducto(producto(), variantId)
    return { ...base({ mode: 'edit' as const, prices: s.prices, packagings: s.packagings, form: s.form, ...extra }),
      loaded: producto(), variantId, precioATodas: true }
  }
  it('principal: SKU y código van al producto; empaques cargados se conservan', () => {
    const plan = armarPayloadEdicion(entrada())
    expect(plan.productPatch.sku).toBe('NK-TENIS-NEG-40')
    expect(plan.productPatch.barcode).toBe('111')
    expect(plan.productPatch.packaging_units).toEqual([{ name: 'Caja', barcode: null, units_per_package: 12, package_price: 40000 }])
    expect(plan.productPatch.precio_a_todas_las_tallas).toBe(true)
    expect(plan.productPatch.uses_inventory).toBe(true)
    expect(plan.variantPatch).toBeNull()
  })
  it('talla no principal: SKU y código cambiados van a la talla, nunca al producto', () => {
    const e = entrada('v2')
    e.form = { ...e.form, sku: 'NK-TENIS-NEG-41B' }
    const plan = armarPayloadEdicion(e)
    expect(plan.productPatch.sku).toBeUndefined()
    expect(plan.productPatch.barcode).toBeUndefined()
    expect(plan.variantPatch).toEqual({ variantId: 'v2', patch: { sku: 'NK-TENIS-NEG-41B' } })
  })
  it('con una sola talla no manda precio_a_todas_las_tallas', () => {
    const uno = producto({ variants: [producto().variants![0]] })
    const s = formDesdeProducto(uno)
    const plan = armarPayloadEdicion({ ...base({ mode: 'edit', form: s.form }), loaded: uno, precioATodas: true })
    expect(plan.productPatch.precio_a_todas_las_tallas).toBeUndefined()
  })
})

describe('erroresDeApi', () => {
  const rows = [fila({ key: 'a', size: '40', sku: 'A-40' }), fila({ key: 'b', size: '41', sku: 'A-41' })]
  it('409 de SKU cae en el campo sku con el texto del servidor', () => {
    const r = erroresDeApi({ response: { status: 409, data: { detail: "El SKU 'A' ya existe en esta organización." } } }, [], 'create')
    expect(r.errors.sku).toContain('ya existe')
    expect(r.mensaje).toContain('ya existe')
  })
  it('422 en lista marca el campo', () => {
    const r = erroresDeApi({ response: { status: 422, data: { detail: [{ loc: ['body', 'price'], msg: 'mayor a 0' }] } } }, [], 'edit')
    expect(r.errors.price).toBeTruthy()
  })
  it('sin detalle usable da el mensaje genérico del modo', () => {
    expect(erroresDeApi(new Error('x'), rows, 'create').mensaje).toBe('No se pudo crear el producto.')
    expect(erroresDeApi({}, rows, 'edit').mensaje).toBe('No se pudo actualizar el producto.')
  })
  it('el 409 de una talla marca su fila', () => {
    const r = erroresDeApi({ response: { status: 409, data: { detail: "El SKU 'A-41' ya existe en esta organización." } } }, rows, 'create')
    expect(r.errors['variants.0.sku'] ?? r.errors['variants.1.sku']).toBeTruthy()
    expect(r.mensaje).toBe('Revisa la variante marcada.')
  })
})
```

Nota para quien implementa: la cuarta prueba de `erroresDeApi` depende de lo que `variantDetailErrors` (`variantMatrix.ts:157-181`) reconozca; si marca la fila con otra clave, ajusta la aserción a la clave real (es una prueba de caracterización, no cambies `variantDetailErrors`). Las filas en `extras` son las que **no** son la principal: con `rows` de dos filas, `splitPrincipal` deja una extra, la de índice 0.

- [ ] **Step 2: Correr y ver que falla**

Run: `cd frontend && npx vitest run src/components/products/__tests__/productoForm.test.ts`
Expected: FAIL, `../productoForm` no existe.

- [ ] **Step 3: Implementar `productoForm.ts`**

```ts
/**
 * Lógica pura del formulario de producto: la única validación y el único
 * armado de payload para alta y edición. `FormularioProducto.tsx` solo pinta.
 *
 * Sale de fusionar lo que tenían copiado AdminProductCreate, ProductForm,
 * ProductModal (HQ) y ProductFormModal (sucursal). Reglas que el backend
 * exige y aquí se repiten para avisar antes de mandar: precio > 0, SKU
 * requerido, escalones y empaques bien formados.
 */
import type { ProductCreate, ProductUpdate } from '../../api/products'
import type { Product } from '../../types/products'
import { fieldErrorsFromDetail, summarizeFieldErrors } from '../../utils/apiErrors'
import { esFilaPrincipal, planIdentidadDeFila } from '../branch/variantEdit'
import type { PackagingRow, PriceRow, ProductErrors, ProductFormValue } from './types'
import { splitPrincipal, toExtraVariants, variantDetailErrors, variantFieldErrors, type VariantRow } from './variantMatrix'

export interface EntradaFormulario {
  form: ProductFormValue
  mode: 'create' | 'edit'
  isAdmin: boolean
  userBranchId: number | null
  /** Admin: sucursales marcadas en la matriz. Cajero/gerente: la suya. */
  enabledBranchIds: number[]
  prices: PriceRow[]
  packagings: PackagingRow[]
  variantRows: VariantRow[]
  hasVariantsModule: boolean
}

/** Existencia que traen las tallas hermanas de la matriz (sin la principal). */
export function stockHermanas(variantRows: VariantRow[], hasVariantsModule: boolean): number {
  return splitPrincipal(hasVariantsModule ? variantRows : []).extras
    .reduce((acc, r) => acc + (Number(r.initial_stock) || 0), 0)
}

/** Existencia inicial total del alta: principal + hermanas. */
export function totalInicial(form: ProductFormValue, variantRows: VariantRow[], hasVariantsModule: boolean): number {
  return (Number(form.initial_stock || '0') || 0) + stockHermanas(variantRows, hasVariantsModule)
}

export function validarProducto(e: EntradaFormulario): ProductErrors {
  const { form, mode, isAdmin, userBranchId, enabledBranchIds, prices, packagings, variantRows, hasVariantsModule } = e
  const errores: ProductErrors = {}
  if (!form.name.trim()) errores.name = 'Requerido'
  if (!form.sku.trim()) errores.sku = 'Requerido'
  const precio = Number(form.price)
  const costo = Number(form.cost)
  // El backend rechaza precio 0 (`validar_precio`); avisar aquí evita un 422 opaco.
  if (!Number.isFinite(precio) || precio <= 0) errores.price = 'Precio mayor a 0'
  if (!Number.isFinite(costo) || costo < 0) errores.cost = 'Número ≥ 0'
  if (mode === 'create') {
    const stock = Number(form.initial_stock || '0')
    if (!Number.isFinite(stock) || stock < 0) errores.initial_stock = 'Número ≥ 0'
    const total = totalInicial(form, variantRows, hasVariantsModule)
    if (isAdmin) {
      if (enabledBranchIds.length === 0) errores.target_branch_ids = 'Activa al menos una sucursal'
      // La existencia se reparte por talla: la sucursal hace falta si
      // cualquiera de las filas trae existencia, no solo la principal.
      if (total > 0 && !form.initial_stock_branch_id) errores.initial_stock_branch_id = 'Requerido con existencia inicial'
    } else if (!userBranchId) {
      errores.target_branch_ids = 'Tu usuario no tiene sucursal asignada'
    }
  }
  prices.forEach((p, i) => {
    if (!p.price_name.trim()) errores[`prices.${i}.price_name`] = 'Requerido'
    if (!Number.isFinite(Number(p.min_quantity)) || Number(p.min_quantity) <= 0)
      errores[`prices.${i}.min_quantity`] = 'Cantidad mínima mayor a 0'
    if (!Number.isFinite(Number(p.unit_price)) || Number(p.unit_price) < 0)
      errores[`prices.${i}.unit_price`] = 'Número ≥ 0'
  })
  packagings.forEach((u, i) => {
    if (!u.name.trim()) errores[`packaging.${i}.name`] = 'Requerido'
    if (!Number.isFinite(Number(u.units_per_package)) || Number(u.units_per_package) <= 0)
      errores[`packaging.${i}.units_per_package`] = 'Unidades mayores a 0'
    if (!Number.isFinite(Number(u.package_price)) || Number(u.package_price) < 0)
      errores[`packaging.${i}.package_price`] = 'Número ≥ 0'
  })
  if (form.has_iva && !Number.isFinite(Number(form.tax_rate))) errores.tax_rate = 'Escribe un número'
  if (mode === 'create' && hasVariantsModule) {
    // La primera fila es la principal: su SKU es el base, no se valida aparte.
    const skus = new Set<string>([form.sku.trim().toLowerCase()])
    splitPrincipal(variantRows).extras.forEach((r, i) => {
      const s = r.sku.trim().toLowerCase()
      if (!s) errores[`variants.${i}.sku`] = 'SKU requerido'
      else if (skus.has(s)) errores[`variants.${i}.sku`] = 'SKU repetido'
      skus.add(s)
      if (r.price.trim() && !(Number(r.price) > 0)) errores[`variants.${i}.price`] = 'Precio mayor a 0'
      const st = Number(r.initial_stock)
      if (r.initial_stock.trim() && !(Number.isFinite(st) && st >= 0)) errores[`variants.${i}.initial_stock`] = 'Número ≥ 0'
    })
  }
  return errores
}

const escalones = (prices: PriceRow[]) => prices.map((p) => ({
  price_name: p.price_name, min_quantity: Number(p.min_quantity), unit_price: Number(p.unit_price),
}))

const empaques = (packagings: PackagingRow[]) => packagings.map((u) => ({
  name: u.name.trim() || 'Caja', barcode: u.barcode.trim() || null,
  units_per_package: Number(u.units_per_package), package_price: Number(u.package_price),
}))

/** Campos comunes a alta y edición, ya limpios. */
function camposComunes(form: ProductFormValue) {
  return {
    name: form.name.trim(),
    unit: form.unit,
    description: form.description.trim() || null,
    image_url: form.image_url.trim() || null,
    department_id: form.department_id || null,
    brand_id: form.brand_id || null,
    gender: form.gender || null,
    model: form.model.trim() || null,
    material: form.material.trim() || null,
    price: Number(form.price),
    cost: Number(form.cost),
    has_iva: form.has_iva,
    tax_rate: form.has_iva ? Number(form.tax_rate) : 0,
    uses_inventory: form.uses_inventory,
  }
}

export function armarPayloadAlta(e: EntradaFormulario): ProductCreate {
  const { form, isAdmin, userBranchId, enabledBranchIds, prices, packagings, variantRows, hasVariantsModule } = e
  // Matriz boutique: la primera combinación ES la variante principal
  // (`color`/`size` del producto); el resto viajan como `extra_variants`.
  const { principal, extras } = splitPrincipal(hasVariantsModule ? variantRows : [])
  const variantes = principal
    ? {
        ...(principal.color ? { color: principal.color } : {}),
        ...(principal.size ? { size: principal.size } : {}),
        ...(extras.length > 0 ? { extra_variants: toExtraVariants(extras) } : {}),
      }
    : {}
  const total = totalInicial(form, variantRows, hasVariantsModule)
  // La sucursal destino viaja si CUALQUIER talla trae existencia: sin ella el
  // backend no sabría dónde meter la de las hermanas.
  const sucursalStock = total > 0 ? (isAdmin ? Number(form.initial_stock_branch_id) : userBranchId) : null
  return {
    ...camposComunes(form),
    sku: form.sku.trim(),
    barcode: form.barcode.trim() || null,
    initial_stock: Number(form.initial_stock || '0') || 0,
    branch_id: sucursalStock,
    // Solo el admin reparte sucursales; el backend ignora el campo a los demás.
    ...(isAdmin ? { target_branch_ids: enabledBranchIds } : {}),
    prices: escalones(prices),
    packaging_units: empaques(packagings),
    ...variantes,
  }
}

export interface EntradaEdicion extends EntradaFormulario {
  loaded: Product
  /** Talla de la que salió el renglón (lista de sucursal); sin ella se edita la principal. */
  variantId?: string
  precioATodas: boolean
}

export interface PlanEdicion {
  productPatch: ProductUpdate
  variantPatch: { variantId: string; patch: { sku?: string; barcode?: string | null } } | null
}

export function armarPayloadEdicion(e: EntradaEdicion): PlanEdicion {
  const { form, prices, packagings, loaded, variantId, precioATodas } = e
  // El SKU/código de una talla no principal NO puede viajar en PUT /products/{id}:
  // ahí sobrescribiría los de la principal (ver components/branch/variantEdit.ts).
  const identidad = planIdentidadDeFila(loaded, variantId, { sku: form.sku.trim(), barcode: form.barcode.trim() || null })
  const varias = (loaded.variants?.length ?? 0) > 1
  return {
    productPatch: {
      ...camposComunes(form),
      ...identidad.productPatch,
      // Solo tiene sentido con varias tallas; sin ellas no se manda.
      ...(varias ? { precio_a_todas_las_tallas: precioATodas } : {}),
      // Cargados desde GET /products/{id}: mandarlos completos conserva lo que había.
      prices: escalones(prices),
      packaging_units: empaques(packagings),
    },
    variantPatch: identidad.variantPatch,
  }
}

export interface EstadoDesdeProducto { form: ProductFormValue; prices: PriceRow[]; packagings: PackagingRow[] }

/** Estado del formulario a partir de un producto cargado con GET /products/{id}. */
export function formDesdeProducto(p: Product, variantId?: string): EstadoDesdeProducto {
  const principal = p.variants?.[0]
  const fila = variantId && !esFilaPrincipal(p, variantId) ? p.variants?.find((v) => v.id === variantId) : undefined
  const identidad = fila ?? principal
  return {
    form: {
      name: p.name ?? '',
      sku: (identidad?.sku ?? p.sku ?? '') as string,
      barcode: (identidad?.barcode ?? p.barcode ?? '') as string,
      unit: p.unit ?? 'pza',
      description: p.description ?? '',
      image_url: p.image_url ?? '',
      department_id: (p.department?.id ?? '') as string,
      brand_id: (p.brand_id ?? '') as string,
      gender: p.gender ?? '',
      model: p.model ?? '',
      material: p.material ?? '',
      price: String(principal?.price ?? p.price ?? ''),
      cost: String(principal?.cost ?? p.cost ?? ''),
      has_iva: Boolean(principal?.has_iva ?? p.has_iva ?? false),
      tax_rate: String(principal?.tax_rate ?? p.tax_rate ?? '16'),
      uses_inventory: p.uses_inventory ?? true,
      initial_stock: '0',
      initial_stock_branch_id: '',
    },
    // Escalones: variante principal o top-level como respaldo.
    prices: (principal?.prices ?? p.prices ?? []).map((tp) => ({
      id: tp.id, price_name: tp.price_name, min_quantity: Number(tp.min_quantity), unit_price: Number(tp.unit_price),
    })),
    packagings: (p.packaging_units ?? []).map((u) => ({
      id: u.id, name: u.name, barcode: u.barcode ?? '', units_per_package: Number(u.units_per_package), package_price: Number(u.package_price),
    })),
  }
}

export interface ErroresDeApi { errors: ProductErrors; mensaje: string }

/** Traduce la respuesta de error de la API a errores por campo y un aviso. */
export function erroresDeApi(err: unknown, variantRows: VariantRow[], mode: 'create' | 'edit'): ErroresDeApi {
  const e = err as { response?: { status?: number; data?: { detail?: unknown } } } | null
  const status = e?.response?.status
  const detail = e?.response?.data?.detail
  // Un 409 de la matriz (SKU o código repetido de una talla) cita la fila
  // culpable: marcarla ahí en vez de acusar al SKU base del producto.
  const porFila = variantDetailErrors(detail as string | undefined, splitPrincipal(variantRows).extras)
  if (Object.keys(porFila).length > 0) return { errors: porFila, mensaje: 'Revisa la variante marcada.' }
  const errors: ProductErrors = {}
  if (status === 409 || (typeof detail === 'string' && detail.toLowerCase().includes('sku'))) {
    errors.sku = typeof detail === 'string' ? detail : 'SKU duplicado'
  }
  // Un 422 trae `detail` como LISTA de campos.
  const porCampo = variantFieldErrors(fieldErrorsFromDetail(detail))
  if (Object.keys(porCampo).length > 0) return { errors: { ...errors, ...porCampo }, mensaje: summarizeFieldErrors(porCampo) }
  const generico = `No se pudo ${mode === 'create' ? 'crear' : 'actualizar'} el producto.`
  return { errors, mensaje: typeof detail === 'string' ? detail : generico }
}
```

Si `variantDetailErrors` o `fieldErrorsFromDetail` tipan `detail` de otra forma, adapta el `as` al tipo que declaran (están en `variantMatrix.ts:157` y `utils/apiErrors.ts`); no cambies esas funciones.

- [ ] **Step 4: Correr las pruebas**

Run: `cd frontend && npx vitest run src/components/products/__tests__/productoForm.test.ts`
Expected: PASS (todas). Si la prueba de la fila 409 falla por la clave, ajústala como dice la nota del Step 1.

- [ ] **Step 5: Build y commit**

Run: `cd frontend && npm run build` → verde.

```bash
git add frontend/src/components/products/productoForm.ts frontend/src/components/products/__tests__/productoForm.test.ts
git commit -m "feat(products-ui): validación y payloads del producto en un solo helper puro"
```

---

### Task 5: Sección de empaques, ficha por giro en Comerciales y unidades unificadas

**Files:**
- Create: `frontend/src/components/products/ProductPackagingSection.tsx`
- Modify: `frontend/src/components/products/ProductCommercialSection.tsx:1-100`
- Modify: `frontend/src/components/products/ProductBasicsSection.tsx:46-55` (opciones de unidad)
- Test: `frontend/src/components/products/__tests__/ProductPackagingSection.test.tsx`
- Test: `frontend/src/components/products/__tests__/ProductCommercialSection.test.tsx`

**Interfaces:**
- Produces: `ProductPackagingSection({ packagings: PackagingRow[]; onChange: (rows: PackagingRow[]) => void; errors?: ProductErrors })`; `ProductCommercialSection` gana la prop `campos?: CamposProducto` (default `TODO_VISIBLE`) y la casilla `uses_inventory`; `ProductBasicsSection` muestra `pza, kg, lt, mt, caja, par, srv` y conserva como opción extra el valor actual si no está en la lista.
- Consumed by: Tarea 6.

- [ ] **Step 1: Pruebas (fallan)**

`ProductPackagingSection.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { ProductPackagingSection } from '../ProductPackagingSection'

afterEach(cleanup)

describe('ProductPackagingSection', () => {
  it('sin empaques muestra el aviso y agrega una caja de 1', () => {
    const onChange = vi.fn()
    render(<ProductPackagingSection packagings={[]} onChange={onChange} />)
    expect(screen.getByText('Sin empaques definidos')).toBeTruthy()
    fireEvent.click(screen.getByText('Agregar empaque'))
    expect(onChange).toHaveBeenCalledWith([{ name: 'Caja', barcode: '', units_per_package: 1, package_price: 0 }])
  })

  it('pinta las filas, sus errores y quita la fila pedida', () => {
    const onChange = vi.fn()
    const filas = [
      { name: 'Caja', barcode: '', units_per_package: 12, package_price: 100 },
      { name: '', barcode: '', units_per_package: 0, package_price: 0 },
    ]
    render(<ProductPackagingSection packagings={filas} onChange={onChange}
      errors={{ 'packaging.1.name': 'Requerido', 'packaging.1.units_per_package': 'Unidades mayores a 0' }} />)
    expect(screen.getByText('Requerido')).toBeTruthy()
    expect(screen.getByText('Unidades mayores a 0')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Quitar el empaque 1'))
    expect(onChange).toHaveBeenCalledWith([filas[1]])
  })
})
```

`ProductCommercialSection.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { ProductCommercialSection } from '../ProductCommercialSection'
import { EMPTY_PRODUCT_FORM } from '../types'

afterEach(cleanup)
const ocultaFicha = { visibles: ['name'], ocultos: ['gender', 'model', 'material'] }
const props = { onChange: vi.fn(), errors: {}, departments: [], brands: [] }

describe('ProductCommercialSection: campos por giro', () => {
  it('sin campos (falla abierto) muestra género, modelo y material', () => {
    render(<ProductCommercialSection {...props} value={EMPTY_PRODUCT_FORM} />)
    expect(screen.getByText('Género')).toBeTruthy()
    expect(screen.getByText('Modelo')).toBeTruthy()
    expect(screen.getByText('Material')).toBeTruthy()
  })
  it('un giro sin ficha no los muestra', () => {
    render(<ProductCommercialSection {...props} value={EMPTY_PRODUCT_FORM} campos={ocultaFicha} />)
    expect(screen.queryByText('Género')).toBeNull()
    expect(screen.queryByText('Modelo')).toBeNull()
    expect(screen.queryByText('Material')).toBeNull()
  })
  it('nada se apaga: con valor capturado el campo sigue ahí', () => {
    render(<ProductCommercialSection {...props} value={{ ...EMPTY_PRODUCT_FORM, gender: 'MUJER' }} campos={ocultaFicha} />)
    expect(screen.getByText('Género')).toBeTruthy()
    expect(screen.queryByText('Modelo')).toBeNull()
  })
  it('tiene la casilla de inventario', () => {
    render(<ProductCommercialSection {...props} value={EMPTY_PRODUCT_FORM} />)
    expect(screen.getByLabelText('Lleva inventario')).toBeTruthy()
  })
})
```

Run: `cd frontend && npx vitest run src/components/products/__tests__/ProductPackagingSection.test.tsx src/components/products/__tests__/ProductCommercialSection.test.tsx` → FAIL.

- [ ] **Step 2: Crear `ProductPackagingSection.tsx`**

Es la sección de `Products.tsx:1034-1104` convertida en componente controlado, con errores por fila. Usa las mismas clases.

```tsx
import { emptyPackagingRow, type PackagingRow, type ProductErrors } from './types'

interface Props {
  packagings: PackagingRow[]
  onChange: (rows: PackagingRow[]) => void
  errors?: ProductErrors
}

const Error = ({ texto }: { texto?: string }) => texto ? <span className="text-rose-400 text-[11px] block">{texto}</span> : null

/** Empaques (caja, master…) con su propio código y precio. */
export function ProductPackagingSection({ packagings, onChange, errors = {} }: Props) {
  const actualizar = (i: number, patch: Partial<PackagingRow>) =>
    onChange(packagings.map((u, idx) => (idx === i ? { ...u, ...patch } : u)))
  const quitar = (i: number) => onChange(packagings.filter((_, idx) => idx !== i))

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wide">Empaques / Cajas</h2>
        <button type="button" onClick={() => onChange([...packagings, emptyPackagingRow()])}
          className="flex items-center gap-1 text-[10px] font-bold text-indigo-400 hover:text-indigo-300 px-2 py-0.5 rounded hover:bg-indigo-500/10 transition-colors">
          <i className="fa-solid fa-plus" /> Agregar empaque
        </button>
      </div>
      {packagings.length === 0 ? (
        <p className="text-xs py-2 text-center" style={{ color: 'var(--dax-text-faint)' }}>Sin empaques definidos</p>
      ) : (
        <div className="space-y-2">
          {packagings.map((u, i) => (
            <div key={u.id ?? i}
              className="grid grid-cols-1 sm:grid-cols-[1fr_70px_90px_1fr_28px] gap-2 items-end rounded-lg border border-slate-800/70 p-2 sm:rounded-none sm:border-0 sm:p-0">
              <label className="text-[10px] text-slate-500 space-y-0.5">
                Nombre
                <input className="dax-input w-full text-xs" value={u.name} placeholder="Caja"
                  onChange={(e) => actualizar(i, { name: e.target.value })} />
                <Error texto={errors[`packaging.${i}.name`]} />
              </label>
              <label className="text-[10px] text-slate-500 space-y-0.5">
                Unidades
                <input className="dax-input w-full text-xs" type="number" min="1" value={u.units_per_package}
                  onChange={(e) => actualizar(i, { units_per_package: Number(e.target.value) })} />
                <Error texto={errors[`packaging.${i}.units_per_package`]} />
              </label>
              <label className="text-[10px] text-slate-500 space-y-0.5">
                Precio/caja
                <input className="dax-input w-full text-xs" type="number" min="0" step="0.01" value={u.package_price}
                  onChange={(e) => actualizar(i, { package_price: Number(e.target.value) })} />
                <Error texto={errors[`packaging.${i}.package_price`]} />
              </label>
              <label className="text-[10px] text-slate-500 space-y-0.5">
                Código de barras
                <input className="dax-input w-full text-xs font-mono" value={u.barcode} placeholder="Opcional"
                  onChange={(e) => actualizar(i, { barcode: e.target.value })} />
              </label>
              <button type="button" onClick={() => quitar(i)} aria-label={`Quitar el empaque ${i + 1}`}
                className="w-full min-h-[44px] sm:w-7 sm:h-8 sm:min-h-0 flex items-center justify-center gap-1.5 rounded border border-slate-700 sm:border-0 text-slate-500 hover:text-red-400 transition-colors">
                <i className="fa-solid fa-xmark text-xs" />
                <span className="text-[11px] font-semibold sm:hidden">Quitar</span>
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
```

- [ ] **Step 3: `ProductCommercialSection` con `campos` y `uses_inventory`**

Cambios exactos:

```tsx
import { campoVisible, TODO_VISIBLE, type CamposProducto } from './camposProducto'

interface Props {
  value: ProductFormValue
  onChange: SetField
  errors: ProductErrors
  departments: Department[]
  brands: Brand[]
  /** Qué campos ve este giro; sin la prop se ve todo. */
  campos?: CamposProducto
}

export function ProductCommercialSection({ value, onChange, errors, departments, brands, campos = TODO_VISIBLE }: Props) {
```

Envolver cada una de las tres etiquetas de la ficha (`Género`, `Modelo`, `Material`, líneas 49-69) en su condición: `{campoVisible(campos, 'gender', value.gender) && (<label …>Género…</label>)}`, igual con `'model'`/`value.model` y `'material'`/`value.material`. Después de la etiqueta de "Aplica IVA" (y su tasa), añadir:

```tsx
        <label className="text-xs text-slate-400 flex items-center gap-2">
          <input type="checkbox" checked={value.uses_inventory}
            onChange={(e) => onChange('uses_inventory', e.target.checked)} />
          Lleva inventario
        </label>
```

- [ ] **Step 4: Unidades en `ProductBasicsSection`**

Reemplazar el `<select>` de Unidad (líneas 48-55) por:

```tsx
          <select className="dax-input w-full" value={value.unit}
            onChange={(e) => onChange('unit', e.target.value)}>
            {UNIDADES.map((u) => <option key={u} value={u}>{u}</option>)}
            {/* Un producto viejo con una unidad fuera de la lista no se queda sin opción. */}
            {value.unit && !UNIDADES.includes(value.unit) && <option value={value.unit}>{value.unit}</option>}
          </select>
```

y arriba del componente: `const UNIDADES = ['pza', 'kg', 'lt', 'mt', 'caja', 'par', 'srv']` (unión de las dos listas que había: `ProductBasicsSection` y `ProductModal`; `cja` no se conserva como opción, pero un producto que la tenga la sigue viendo por la rama de arriba).

- [ ] **Step 5: Pruebas, build, commit**

Run: `cd frontend && npx vitest run src/components/products && npm run build` → PASS y verde.

```bash
git add frontend/src/components/products/ProductPackagingSection.tsx frontend/src/components/products/ProductCommercialSection.tsx frontend/src/components/products/ProductBasicsSection.tsx frontend/src/components/products/__tests__/ProductPackagingSection.test.tsx frontend/src/components/products/__tests__/ProductCommercialSection.test.tsx
git commit -m "feat(products-ui): sección de empaques, ficha por giro y unidades unificadas"
```

---

### Task 6: `FormularioProducto`, el único formulario

**Files:**
- Create: `frontend/src/components/products/FormularioProducto.tsx`
- Test: `frontend/src/components/products/__tests__/FormularioProducto.test.tsx`

**Interfaces:**
- Consumes: todo lo de las Tareas 2-5; `ProductBasicsSection`, `ProductTieredPricesSection`, `ProductVariantsSection`, `ProductVariantsEditor`, `ProductBranchMatrixSection`, `ProductInitialStockSection`, `ProductImageUploader` (props en el levantamiento §2); `productsApi.getById/create/update/updateVariant/skuSuggest/getBrands/getDepartments`; `organizationApi.getBranches`; `useAuthStore`; `useEnabledModulesStore`; `confirm` (`components/ui/ConfirmDialog`); `toast` (`store/toastStore`); `Spinner`.
- Produces:

```ts
export interface FormularioProductoProps {
  mode: 'create' | 'edit'
  /** Obligatorio en edición: el formulario carga el producto con GET /products/{id}. */
  productId?: string
  /** Talla de la que salió el renglón (lista de sucursal). */
  variantId?: string
  /** 'pagina' pinta encabezado y tarjeta; 'modal' solo el contenido (el título lo pone el Modal). */
  presentacion: 'pagina' | 'modal'
  onDone: (producto: Product) => void
  onCancel: () => void
}
export function FormularioProducto(props: FormularioProductoProps): JSX.Element
```

- [ ] **Step 1: Pruebas (fallan)**

Mocks: `api/products`, `api/organization`, el store de auth y el de módulos se fijan con `setState`. `confirm` no se usa en estas pruebas.

```tsx
// @vitest-environment jsdom
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const api = {
  getDepartments: vi.fn(async () => []),
  getBrands: vi.fn(async () => []),
  getById: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  updateVariant: vi.fn(),
  skuSuggest: vi.fn(),
}
vi.mock('../../../api/products', () => ({ productsApi: api }))
vi.mock('../../../api/organization', () => ({
  organizationApi: { getBranches: vi.fn(async () => [{ id: 20, name: 'Roma', branch_type: 'STORE', is_headquarters: false }]) },
}))
vi.mock('../../../store/toastStore', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

const { FormularioProducto } = await import('../FormularioProducto')
const { useAuthStore } = await import('../../../store/authStore')
const { useEnabledModulesStore } = await import('../../../store/enabledModulesStore')

const admin = { id: 1, username: 'admin', role: 'ADMINISTRADOR', branch_id: null, branch_name: null }
const cajera = { id: 2, username: 'caja', role: 'CAJERO', branch_id: 20, branch_name: 'Roma' }

const producto = {
  id: 'p1', name: 'Tenis', sku: 'NK-TENIS-NEG-40', price: 4000, cost: 1500, unit: 'pza', is_active: true,
  uses_inventory: true, gender: 'MUJER',
  variants: [
    { id: 'v1', sku: 'NK-TENIS-NEG-40', color: 'Negro', size: '40', price: 4000, cost: 1500, barcode: '111' },
    { id: 'v2', sku: 'NK-TENIS-NEG-41', color: 'Negro', size: '41', price: 4000, cost: 1500, barcode: '222' },
  ],
  prices: [],
  packaging_units: [{ id: 'pk1', name: 'Caja', barcode: null, units_per_package: 12, package_price: 40000 }],
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuthStore.setState({ user: admin } as never)
  useEnabledModulesStore.setState({ enabledModules: ['core'], loaded: true, camposProducto: { visibles: [], ocultos: [] } } as never)
})
afterEach(cleanup)

const escribir = (etiqueta: RegExp | string, valor: string) =>
  fireEvent.change(screen.getByLabelText(etiqueta), { target: { value: valor } })

describe('FormularioProducto', () => {
  it('alta de admin: manda el payload único con la sucursal marcada', async () => {
    api.create.mockResolvedValue({ ...producto, id: 'nuevo' })
    const onDone = vi.fn()
    render(<FormularioProducto mode="create" presentacion="pagina" onDone={onDone} onCancel={() => {}} />)
    await screen.findByText('Crear producto')
    escribir(/Nombre/, 'Tenis'); escribir(/SKU/, 'nk-tenis'); escribir(/Precio \*/, '4000'); escribir(/Costo \*/, '1500')
    fireEvent.click(screen.getByLabelText(/Roma/))
    fireEvent.click(screen.getByText('Crear producto'))
    await waitFor(() => expect(api.create).toHaveBeenCalled())
    const payload = api.create.mock.calls[0][0]
    expect(payload.sku).toBe('NK-TENIS')
    expect(payload.target_branch_ids).toEqual([20])
    expect(payload.uses_inventory).toBe(true)
    expect(payload.color).toBeUndefined()
    expect(onDone).toHaveBeenCalledWith(expect.objectContaining({ id: 'nuevo' }))
  })

  it('precio 0 no se manda', async () => {
    render(<FormularioProducto mode="create" presentacion="pagina" onDone={() => {}} onCancel={() => {}} />)
    await screen.findByText('Crear producto')
    escribir(/Nombre/, 'Tenis'); escribir(/SKU/, 'X'); escribir(/Precio \*/, '0'); escribir(/Costo \*/, '0')
    fireEvent.click(screen.getByText('Crear producto'))
    expect(await screen.findByText('Precio mayor a 0')).toBeTruthy()
    expect(api.create).not.toHaveBeenCalled()
  })

  it('cajera: la sucursal es la suya y no hay matriz de sucursales', async () => {
    useAuthStore.setState({ user: cajera } as never)
    api.create.mockResolvedValue({ ...producto, id: 'nuevo' })
    render(<FormularioProducto mode="create" presentacion="modal" onDone={() => {}} onCancel={() => {}} />)
    await screen.findByText('Crear producto')
    expect(screen.queryByText(/Activar en sucursales/)).toBeNull()
    escribir(/Nombre/, 'Tenis'); escribir(/SKU/, 'X'); escribir(/Precio \*/, '10'); escribir(/Costo \*/, '1')
    escribir(/Existencia inicial/, '2')
    fireEvent.click(screen.getByText('Crear producto'))
    await waitFor(() => expect(api.create).toHaveBeenCalled())
    const payload = api.create.mock.calls[0][0]
    expect(payload.branch_id).toBe(20)
    expect(payload.target_branch_ids).toBeUndefined()
  })

  it('edición: conserva los empaques cargados y muestra la ficha aunque el giro la oculte', async () => {
    useEnabledModulesStore.setState({ enabledModules: ['core', 'variants'], loaded: true,
      camposProducto: { visibles: [], ocultos: ['gender', 'model', 'material'] } } as never)
    api.getById.mockResolvedValue(producto)
    api.update.mockResolvedValue(producto)
    render(<FormularioProducto mode="edit" productId="p1" presentacion="pagina" onDone={() => {}} onCancel={() => {}} />)
    await screen.findByText('Guardar cambios')
    expect(screen.getByText('Género')).toBeTruthy()      // trae MUJER: nada se apaga
    expect(screen.queryByText('Modelo')).toBeNull()      // vacío y oculto por el giro
    fireEvent.click(screen.getByText('Guardar cambios'))
    await waitFor(() => expect(api.update).toHaveBeenCalled())
    const [id, patch] = api.update.mock.calls[0]
    expect(id).toBe('p1')
    expect(patch.packaging_units).toEqual([{ name: 'Caja', barcode: null, units_per_package: 12, package_price: 40000 }])
    expect(patch.sku).toBe('NK-TENIS-NEG-40')
    expect(patch.gender).toBe('MUJER')
    expect(api.updateVariant).not.toHaveBeenCalled()
  })

  it('edición de una talla no principal: el SKU va a la talla', async () => {
    api.getById.mockResolvedValue(producto)
    api.update.mockResolvedValue(producto)
    api.updateVariant.mockResolvedValue(producto)
    render(<FormularioProducto mode="edit" productId="p1" variantId="v2" presentacion="modal" onDone={() => {}} onCancel={() => {}} />)
    await screen.findByText('Guardar cambios')
    expect((screen.getByLabelText(/SKU/) as HTMLInputElement).value).toBe('NK-TENIS-NEG-41')
    escribir(/SKU/, 'NK-TENIS-NEG-41B')
    fireEvent.click(screen.getByText('Guardar cambios'))
    await waitFor(() => expect(api.updateVariant).toHaveBeenCalledWith('v2', { sku: 'NK-TENIS-NEG-41B' }))
    expect(api.update.mock.calls[0][1].sku).toBeUndefined()
  })

  it('si el producto no carga, avisa y cancela', async () => {
    api.getById.mockRejectedValue(new Error('404'))
    const onCancel = vi.fn()
    render(<FormularioProducto mode="edit" productId="nada" presentacion="modal" onDone={() => {}} onCancel={onCancel} />)
    await waitFor(() => expect(onCancel).toHaveBeenCalled())
  })
})
```

Notas: las etiquetas que usa `getByLabelText` son las de las secciones existentes (`Nombre *`, `SKU *`, `Precio *`, `Costo *`; en `ProductInitialStockSection` la etiqueta de la existencia es "Existencia inicial"; verifica el texto real en `ProductInitialStockSection.tsx` y `ProductBranchMatrixSection.tsx` y ajusta las expresiones regulares; la casilla de sucursal de la matriz debe ser alcanzable por `getByLabelText(/Roma/)`; si la matriz no usa `<label>`, usa `getByText('Roma')` y haz clic en su casilla). El `user` del `authStore` puede exigir más campos en su tipo; por eso los `as never`.

Run: `cd frontend && npx vitest run src/components/products/__tests__/FormularioProducto.test.tsx` → FAIL (no existe el componente).

- [ ] **Step 2: Implementar `FormularioProducto.tsx`**

Nace de `pages/products/ProductForm.tsx` (base citada arriba) con estos cambios: el estado de edición sale de `formDesdeProducto`; validación/payload/errores vienen de `productoForm.ts`; se añaden empaques, `uses_inventory`, subida de imagen en edición y `campos`; `onDone`/`onCancel` en vez de `navigate`.

```tsx
import { useEffect, useState } from 'react'
import { productsApi } from '../../api/products'
import { organizationApi } from '../../api/organization'
import { sortByName } from '../../utils/sortByName'
import { useAuthStore } from '../../store/authStore'
import { useCamposProducto, useEnabledModulesStore } from '../../store/enabledModulesStore'
import { DaxCard } from '../ui/DaxCard'
import { Spinner } from '../ui/Spinner'
import { toast } from '../../store/toastStore'
import { confirm } from '../ui/ConfirmDialog'
import { ProductBasicsSection } from './ProductBasicsSection'
import { ProductCommercialSection } from './ProductCommercialSection'
import { ProductTieredPricesSection } from './ProductTieredPricesSection'
import { ProductPackagingSection } from './ProductPackagingSection'
import { ProductVariantsSection } from './ProductVariantsSection'
import { ProductVariantsEditor } from './ProductVariantsEditor'
import { ProductBranchMatrixSection } from './ProductBranchMatrixSection'
import { ProductInitialStockSection } from './ProductInitialStockSection'
import { ProductImageUploader } from './ProductImageUploader'
import {
  EMPTY_PRODUCT_FORM, type BranchActivation, type Brand, type Branch, type Department,
  type PackagingRow, type PriceRow, type ProductErrors, type ProductFormValue,
} from './types'
import { type VariantRow } from './variantMatrix'
import { variantLabel } from './variantWords'
import { argsSugerencia, mensajeSugerencia } from './skuSuggest'
import {
  armarPayloadAlta, armarPayloadEdicion, erroresDeApi, formDesdeProducto, totalInicial, validarProducto,
  type EntradaFormulario,
} from './productoForm'
import type { Product } from '../../types/products'

const ADMIN_ROLES = new Set(['ADMINISTRADOR', 'DUEÑO'])

export interface FormularioProductoProps {
  mode: 'create' | 'edit'
  /** Obligatorio en edición: el formulario carga el producto con GET /products/{id}. */
  productId?: string
  /** Talla de la que salió el renglón (lista de sucursal). */
  variantId?: string
  /** 'pagina' pinta encabezado y tarjeta; 'modal' solo el contenido (el título lo pone el Modal). */
  presentacion: 'pagina' | 'modal'
  onDone: (producto: Product) => void
  onCancel: () => void
}

/**
 * El único formulario de producto (mega plan SP1): alta y edición para
 * admin, gerente y cajero, como página o dentro de un Modal. Toda la lógica
 * de validación y payload vive en `productoForm.ts`.
 */
export function FormularioProducto({ mode, productId, variantId, presentacion, onDone, onCancel }: FormularioProductoProps) {
  const { user } = useAuthStore()
  const isAdmin = user ? ADMIN_ROLES.has(user.role) : false
  const userBranchId = user?.branch_id ?? null
  const hasVariantsModule = useEnabledModulesStore((s) => s.enabledModules.includes('variants'))
  const campos = useCamposProducto()

  const [departments, setDepartments] = useState<Department[]>([])
  const [brands, setBrands] = useState<Brand[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)

  const [form, setForm] = useState<ProductFormValue>(EMPTY_PRODUCT_FORM)
  const [branchActivation, setBranchActivation] = useState<Record<number, BranchActivation>>({})
  const [prices, setPrices] = useState<PriceRow[]>([])
  const [packagings, setPackagings] = useState<PackagingRow[]>([])
  const [errors, setErrors] = useState<ProductErrors>({})
  // El precio de la ficha es el de la talla principal; con la casilla baja a todas.
  const [precioATodas, setPrecioATodas] = useState(true)
  const [variantRows, setVariantRows] = useState<VariantRow[]>([])
  const [loaded, setLoaded] = useState<Product | null>(null)
  const [sugiriendoSku, setSugiriendoSku] = useState(false)

  useEffect(() => {
    let cancelled = false
    const loaders: Promise<unknown>[] = [
      productsApi.getDepartments().then((d) => { if (!cancelled) setDepartments(sortByName(d)) }),
      productsApi.getBrands().then((b) => { if (!cancelled) setBrands(sortByName(b)) }),
    ]
    // Admin necesita la lista de sucursales para la matriz; cajero solo la propia.
    if (isAdmin) {
      loaders.push(organizationApi.getBranches().then((bchs) => {
        if (cancelled) return
        setBranches(bchs)
        const init: Record<number, BranchActivation> = {}
        for (const b of bchs) init[b.id] = { enabled: false, is_active_pos: true, is_active_hq: false, is_visible: true }
        setBranchActivation(init)
      }))
    } else if (userBranchId && user?.branch_name) {
      // Branch mínima para poder mostrar el nombre en la sección de existencia.
      setBranches([{ id: userBranchId, name: user.branch_name, branch_type: 'STORE', is_headquarters: false }])
    }
    if (mode === 'edit') {
      if (!productId) { onCancel(); return () => { cancelled = true } }
      // Sin el detalle completo no se edita: un PUT armado desde la fila de la
      // lista (sin empaques ni escalones) los borraría al reemplazarlos.
      loaders.push(productsApi.getById(productId).then((p) => {
        if (cancelled) return
        setLoaded(p)
        const estado = formDesdeProducto(p, variantId)
        setForm(estado.form); setPrices(estado.prices); setPackagings(estado.packagings)
      }).catch(() => {
        if (cancelled) return
        toast.error('No se pudo cargar el producto.')
        onCancel()
      }))
    }
    Promise.all(loaders)
      .catch(() => { if (!cancelled) toast.error('No se pudo cargar el formulario.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, productId, variantId, isAdmin, userBranchId, user?.branch_name])

  const setField = <K extends keyof ProductFormValue>(key: K, value: ProductFormValue[K]) => {
    setForm((f) => ({ ...f, [key]: value }))
    if (errors[key as string]) setErrors((e) => { const { [key as string]: _, ...rest } = e; return rest })
  }

  /** Pide el SKU de la familia y lo aplica SOLO si el usuario acepta. */
  const sugerirSku = async () => {
    if (!form.name.trim()) { setErrors((e) => ({ ...e, name: 'Escribe el nombre antes de sugerir el SKU' })); return }
    setSugiriendoSku(true)
    try {
      const { sku, available } = await productsApi.skuSuggest(argsSugerencia(form, brands))
      if (!sku) { toast.error('Faltan datos para sugerir un SKU.'); return }
      const ok = await confirm({
        title: 'Usar el SKU sugerido',
        message: <span style={{ whiteSpace: 'pre-line' }}>{mensajeSugerencia(sku, available, form.sku)}</span>,
        confirmText: 'Usar este SKU',
        variant: available ? 'info' : 'warning',
      })
      if (ok) setField('sku', sku)
    } catch {
      toast.error('No se pudo sugerir el SKU.')
    } finally {
      setSugiriendoSku(false)
    }
  }

  const toggleBranch = (branchId: number, patch: Partial<BranchActivation>) => {
    setBranchActivation((prev) => ({ ...prev, [branchId]: { ...prev[branchId], ...patch } }))
    if (patch.enabled === false && Number(form.initial_stock_branch_id) === branchId) setField('initial_stock_branch_id', '')
  }
  const setAllBranches = (enabled: boolean) => {
    setBranchActivation((prev) => Object.fromEntries(Object.entries(prev).map(([k, v]) => [k, { ...v, enabled }])))
    if (!enabled) setField('initial_stock_branch_id', '')
  }

  const enabledBranchIds = isAdmin
    ? Object.entries(branchActivation).filter(([, v]) => v.enabled).map(([k]) => Number(k))
    : (userBranchId ? [userBranchId] : [])
  const total = totalInicial(form, variantRows, hasVariantsModule)
  const sucursalStock = isAdmin
    ? branches.find((b) => b.id === Number(form.initial_stock_branch_id)) ?? null
    : branches.find((b) => b.id === userBranchId) ?? null

  const handleSubmit = async () => {
    const entrada: EntradaFormulario = { form, mode, isAdmin, userBranchId, enabledBranchIds, prices, packagings, variantRows, hasVariantsModule }
    const clientErrors = validarProducto(entrada)
    if (Object.keys(clientErrors).length > 0) { setErrors(clientErrors); toast.error('Revisa los campos marcados.'); return }
    setSubmitting(true)
    try {
      if (mode === 'create') {
        const creado = await productsApi.create(armarPayloadAlta(entrada))
        toast.success('Producto creado.')
        onDone(creado)
      } else if (loaded) {
        const plan = armarPayloadEdicion({ ...entrada, loaded, variantId, precioATodas })
        // Primero el producto: si revienta (409 por SKU), la talla queda intacta.
        let actualizado = await productsApi.update(loaded.id, plan.productPatch)
        if (plan.variantPatch) actualizado = await productsApi.updateVariant(plan.variantPatch.variantId, plan.variantPatch.patch)
        toast.success('Producto actualizado.')
        onDone(actualizado)
      }
    } catch (err: unknown) {
      const r = erroresDeApi(err, variantRows, mode)
      setErrors((prev) => ({ ...prev, ...r.errors }))
      toast.error(r.mensaje)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><Spinner size="lg" /></div>

  // Estos campos son los de la PRIMERA talla, no los del producto entero.
  const principalCargada = mode === 'edit' && hasVariantsModule && loaded && (loaded.variants?.length ?? 0) > 1 ? loaded.variants![0] : null
  const cta = mode === 'create' ? 'Crear producto' : 'Guardar cambios'

  const contenido = (
    <div className="p-0 sm:p-4 space-y-6">
      {principalCargada && (
        <>
          <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
            {`Nombre, precio y código de aquí son los de la talla ${variantLabel(principalCargada, loaded?.name ?? '')}. Las demás tallas, abajo.`}
          </p>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={precioATodas} onChange={(e) => setPrecioATodas(e.target.checked)} />
            Aplicar el precio a todas las tallas
          </label>
        </>
      )}
      <ProductBasicsSection value={form} onChange={setField} errors={errors} onSuggestSku={sugerirSku} suggestingSku={sugiriendoSku} />
      {mode === 'edit' && loaded && (
        <ProductImageUploader product={loaded} onUpdated={(p) => { setLoaded(p); setField('image_url', p.image_url ?? '') }} />
      )}
      <ProductCommercialSection value={form} onChange={setField} errors={errors} departments={departments} brands={brands} campos={campos} />
      <ProductTieredPricesSection prices={prices} onChange={setPrices} errors={errors}
        help="Para precios por cantidad (mayoreo, promo). Se aplica sobre el precio base." />
      <ProductPackagingSection packagings={packagings} onChange={setPackagings} errors={errors} />
      {mode === 'create' && hasVariantsModule && (
        <ProductVariantsSection baseSku={form.sku} rows={variantRows} onRowsChange={setVariantRows} firstIsPrincipal
          errors={errors} showInitialStock principalStock={form.initial_stock}
          onPrincipalStockChange={(v) => setField('initial_stock', v)} stockBranchName={sucursalStock?.name ?? null} />
      )}
      {mode === 'create' && isAdmin && (
        <ProductBranchMatrixSection branches={branches} activation={branchActivation} onToggle={toggleBranch} onSetAll={setAllBranches} errors={errors} />
      )}
      {mode === 'create' && (
        <ProductInitialStockSection value={form} onChange={setField} errors={errors} branches={branches} enabledBranchIds={enabledBranchIds}
          lockedBranchId={!isAdmin && userBranchId ? userBranchId : undefined}
          perVariantTotal={hasVariantsModule && variantRows.length > 0 ? total : null}
          footer={isAdmin ? 'Para existencia en varias sucursales, usa Inventario después de crear.' : 'La existencia se aplica a tu sucursal.'} />
      )}
      {mode === 'edit' && hasVariantsModule && loaded && <ProductVariantsEditor product={loaded} onChanged={setLoaded} />}
      <div className="flex flex-col-reverse sm:flex-row items-stretch sm:items-center sm:justify-end gap-2 pt-2 border-t border-slate-800/60">
        <button type="button" className="dax-btn-secondary text-xs min-h-[44px] sm:min-h-0 justify-center" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
        <button type="button" className="dax-btn-primary text-xs inline-flex items-center justify-center gap-1.5 min-h-[44px] sm:min-h-0"
          onClick={handleSubmit} disabled={submitting}>
          {submitting ? <Spinner size="sm" /> : <i className="fa-solid fa-save" />}
          {cta}
        </button>
      </div>
    </div>
  )

  if (presentacion === 'modal') return contenido
  const title = mode === 'create' ? 'Nuevo producto' : 'Editar producto'
  const iconCls = mode === 'create' ? 'fa-solid fa-plus' : 'fa-solid fa-pen-to-square'
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3 flex-wrap">
        <i className={`${iconCls} text-indigo-400 text-xl`} />
        <h1 className="text-xl sm:text-2xl font-black text-white">{title}</h1>
        {!isAdmin && user?.branch_name && <span className="text-xs text-slate-500">· sucursal {user.branch_name}</span>}
      </div>
      <DaxCard>{contenido}</DaxCard>
    </div>
  )
}
```

Si `ProductImageUploader` necesita un `<Product>` con campos que el tipo exige y el mock de prueba no trae, deja el componente tal cual: solo se pinta.

- [ ] **Step 3: Correr las pruebas; ajustar selectores de etiqueta según las secciones reales**

Run: `cd frontend && npx vitest run src/components/products/__tests__/FormularioProducto.test.tsx`
Expected: PASS (6). Si una etiqueta no se encuentra, corrige la expresión regular de la prueba con el texto real de la sección (no cambies el texto de la sección).

- [ ] **Step 4: Build y commit**

Run: `cd frontend && npm run build` → verde (el componente nuevo aún no tiene consumidores; `tsc` lo compila igual).

```bash
git add frontend/src/components/products/FormularioProducto.tsx frontend/src/components/products/__tests__/FormularioProducto.test.tsx
git commit -m "feat(products-ui): FormularioProducto, el único formulario de alta y edición"
```

---

### Task 7: La página `/products/new` y `/products/:id/edit` usa el formulario único; `/admin/products/new` desaparece

**Files:**
- Modify: `frontend/src/pages/products/ProductForm.tsx` (se reescribe entero, de 465 líneas a ~35)
- Create: `frontend/src/pages/products/volver.ts`
- Delete: `frontend/src/pages/admin/AdminProductCreate.tsx`
- Modify: `frontend/src/App.tsx:42-43, 293-299`
- Modify: `frontend/src/pages/core/AdminCatalog.tsx:129-135, 278-283`
- Modify: `docs/FRONTEND_VIEWS.md` (filas de `/products/new`, `/products/:id/edit`, `/admin/products/new`)
- Test: `frontend/src/pages/products/__tests__/volver.test.ts`

**Interfaces:**
- Produces: `destinoDeRegreso(search: string, defecto: string): string` (lee `?volver=`; solo acepta rutas internas que empiecen con `/` y no con `//`).
- `ProductForm` (página) conserva su nombre exportado y sus rutas; `/admin/products/new` redirige a `/products/new?volver=/admin/catalog`.

- [ ] **Step 1: Prueba de `destinoDeRegreso` (falla)**

```ts
import { describe, it, expect } from 'vitest'
import { destinoDeRegreso } from '../volver'

describe('destinoDeRegreso', () => {
  it('sin parámetro vuelve al defecto', () => {
    expect(destinoDeRegreso('', '/products')).toBe('/products')
  })
  it('acepta rutas internas', () => {
    expect(destinoDeRegreso('?volver=/admin/catalog', '/products')).toBe('/admin/catalog')
    expect(destinoDeRegreso('?volver=%2Fadmin%2Fcatalog%3Fq%3D1', '/products')).toBe('/admin/catalog?q=1')
  })
  it('rechaza destinos externos o raros', () => {
    expect(destinoDeRegreso('?volver=https://evil', '/products')).toBe('/products')
    expect(destinoDeRegreso('?volver=//evil', '/products')).toBe('/products')
  })
})
```

Run: `cd frontend && npx vitest run src/pages/products/__tests__/volver.test.ts` → FAIL.

- [ ] **Step 2: `volver.ts`**

```ts
/** A dónde regresa el formulario al terminar: `?volver=/ruta` interna o el defecto. */
export function destinoDeRegreso(search: string, defecto: string): string {
  const v = new URLSearchParams(search).get('volver')
  if (!v || !v.startsWith('/') || v.startsWith('//')) return defecto
  return v
}
```

- [ ] **Step 3: Reescribir la página `ProductForm.tsx`**

```tsx
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { FormularioProducto } from '../../components/products/FormularioProducto'
import { destinoDeRegreso } from './volver'

/**
 * Página de alta/edición de producto (`/products/new`, `/products/:id/edit`).
 * Solo decide el modo y a dónde volver; el formulario es `FormularioProducto`.
 * Se llega desde el Catálogo del admin con `?volver=/admin/catalog`.
 */
export function ProductForm() {
  const navigate = useNavigate()
  const { search } = useLocation()
  const { id } = useParams<{ id?: string }>()
  const volver = () => navigate(destinoDeRegreso(search, '/products'))
  return (
    <FormularioProducto
      mode={id ? 'edit' : 'create'}
      productId={id}
      presentacion="pagina"
      onDone={volver}
      onCancel={volver}
    />
  )
}
```

- [ ] **Step 4: Rutas y Catálogo**

En `App.tsx`: borrar la línea `const AdminProductCreate = lazy(...)` (42). Reemplazar la ruta `admin/products/new` (293-299) por:

```tsx
          {/* El alta del Catálogo es el mismo formulario que /products/new. */}
          <Route path="admin/products/new" element={<Navigate to="/products/new?volver=/admin/catalog" replace />} />
```

(`Navigate` ya se importa de `react-router-dom` en `App.tsx`; si no, añadirlo.) En `AdminCatalog.tsx`: el `<Link to="/admin/products/new">` (279) pasa a `to="/products/new?volver=/admin/catalog"`; `handleEdit` navega a `` `/products/${product.id}/edit?volver=/admin/catalog` `` y su comentario (130-133) se corrige: "La edición completa (escalones, empaques, tallas) vive en /products/:id/edit; `volver` regresa aquí al guardar." Borrar `frontend/src/pages/admin/AdminProductCreate.tsx` con `git rm`. Buscar otras referencias: `grep -rn "AdminProductCreate\|admin/products/new" frontend/src` debe dejar solo la ruta de redirección y, si existe, el título en `navConfig.ts:184` (se conserva).

- [ ] **Step 5: Docs**

En `docs/FRONTEND_VIEWS.md`: la fila de `/admin/products/new` dice ahora "redirige a `/products/new?volver=/admin/catalog`"; las filas de `/products/new` y `/products/:id/edit` apuntan a `pages/products/ProductForm.tsx` → `components/products/FormularioProducto.tsx` (alta/edición para los 4 roles; API `POST /products/`, `PUT /products/{id}`, `PUT /products/variants/{id}`). Eliminar la fila de `pages/admin/AdminProductCreate.tsx`.

- [ ] **Step 6: Pruebas, build, commit**

Run: `cd frontend && npx vitest run && npm run build` → todo verde (la prueba `navConfig.test.ts:119` del título de edición sigue igual).

```bash
git add -A frontend/src/pages/products frontend/src/pages/admin frontend/src/App.tsx frontend/src/pages/core/AdminCatalog.tsx docs/FRONTEND_VIEWS.md
git commit -m "refactor(products-ui): la página de producto usa FormularioProducto; adiós AdminProductCreate"
```

---

### Task 8: La lista de Productos de HQ abre el formulario único en un Modal; código muerto fuera

**Files:**
- Modify: `frontend/src/pages/inventory/Products.tsx` (borrar `ProductModal` 688-1130, `CreateProductMiniModal` 476-686, interfaces `PriceRow`/`PackagingRow` 690-703, estado `showMiniCreate` 1172, `handleMiniCreated` 1285-1288, montaje 1762-1769, ramas `isBranchEditor`; cambiar `openEdit`, `handleSaved`, `handleNewProductClick` y el montaje del modal)
- Test: `frontend/src/pages/inventory/__tests__/productsSinFormularioPropio.test.ts`

**Interfaces:**
- Consumes: `FormularioProducto` (Tarea 6), `Modal` (`components/ui/Modal`: `{open, onClose, title, children, size, closeOnBackdrop}`).

- [ ] **Step 1: Prueba de que el archivo ya no trae formulario propio (falla)**

```ts
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const fuente = readFileSync(resolve(__dirname, '../Products.tsx'), 'utf8')

describe('Products.tsx: la lista no tiene formulario propio', () => {
  it('no define ProductModal ni CreateProductMiniModal', () => {
    expect(fuente).not.toMatch(/function ProductModal\b/)
    expect(fuente).not.toMatch(/CreateProductMiniModal/)
    expect(fuente).not.toMatch(/productsApi\.(create|update)\(/)
  })
  it('monta FormularioProducto dentro de Modal', () => {
    expect(fuente).toMatch(/<FormularioProducto/)
    expect(fuente).toMatch(/from '\.\.\/\.\.\/components\/ui\/Modal'/)
  })
  it('no queda la rama muerta isBranchEditor', () => {
    expect(fuente).not.toMatch(/isBranchEditor/)
  })
})
```

Run: `cd frontend && npx vitest run src/pages/inventory/__tests__/productsSinFormularioPropio.test.ts` → FAIL.

- [ ] **Step 2: Reescribir la parte de edición de `ProductsHQView`**

Imports: añadir `import { Modal } from '../../components/ui/Modal'` y `import { FormularioProducto } from '../../components/products/FormularioProducto'`; quitar los que queden sin uso tras borrar (`GENEROS`, `ProductImageUploader`, `claseEtiquetaFila` si solo lo usaban los modales borrados: comprobar con `grep -n`).

Estado: sustituir `const [modalProduct, setModalProduct] = useState<Product | null | undefined>(undefined)` (y `showMiniCreate`) por:

```tsx
  // Formulario único (components/products/FormularioProducto) dentro de un Modal.
  const [editor, setEditor] = useState<{ mode: 'create' } | { mode: 'edit'; productId: string } | null>(null)
```

`openEdit` queda sin la rama de `BRANCH_EDIT_ROLES` (esos roles nunca llegan aquí: `Products` los desvía a `ProductsBranchView` en 1137) y sin `getById` (lo hace el formulario):

```tsx
  const openEdit = (p: Product) => setEditor({ mode: 'edit', productId: p.id })
  const handleSaved = () => { setEditor(null); load(search, deptId, page) }
  const handleNewProductClick = () => setEditor({ mode: 'create' })
```

Borrar `handleMiniCreated` y toda referencia a `isBranchEditor` (declaración y usos). Si `BRANCH_EDIT_ROLES` queda sin uso, borrarla. **`BranchStatusEditor` (224-474) solo se borra si `grep -n "BranchStatusEditor" Products.tsx` muestra que únicamente lo usaban las ramas `isBranchEditor`; si la tabla (≈1697-1711) lo monta para el admin, se conserva.**

Montaje (sustituye 1750-1769):

```tsx
      {editor && (
        <Modal open onClose={() => setEditor(null)} size="xl" closeOnBackdrop={false}
          title={editor.mode === 'create' ? 'Nuevo producto' : 'Editar producto'}>
          <FormularioProducto
            mode={editor.mode}
            productId={editor.mode === 'edit' ? editor.productId : undefined}
            presentacion="modal"
            onDone={handleSaved}
            onCancel={() => setEditor(null)}
          />
        </Modal>
      )}
```

Borrar las funciones `ProductModal` y `CreateProductMiniModal` y sus interfaces locales. Revisar que el botón "Nuevo producto" y el lápiz de la tabla/cuadrícula sigan llamando a `handleNewProductClick` y `openEdit`.

- [ ] **Step 3: Pruebas, build, revisión manual del tamaño**

Run: `cd frontend && npx vitest run && npm run build` → verde. `wc -l src/pages/inventory/Products.tsx` debe bajar de 1772 a menos de 1100.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/inventory/Products.tsx frontend/src/pages/inventory/__tests__/productsSinFormularioPropio.test.ts
git commit -m "refactor(products-ui): la lista HQ abre FormularioProducto en Modal; fuera ProductModal y MiniModal"
```

---

### Task 9: La lista de Productos de sucursal usa el mismo formulario; una sola llamada a `create`/`update` en todo el frontend

**Files:**
- Modify: `frontend/src/components/branch/ProductsBranchView.tsx` (borrar `ProductFormModal` 535-955, `TierRow` 957, `PackRow` 964; cambiar `openEdit` 165-173 y el montaje 319-338; el `Modal` local 1073-1093 se borra solo si ya nadie lo usa)
- Test: `frontend/src/__tests__/unSoloFormularioDeProducto.test.ts`

**Interfaces:**
- Consumes: `FormularioProducto`, `Modal` de `components/ui/Modal`.

- [ ] **Step 1: Prueba global (falla)**

```ts
import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

const raiz = resolve(__dirname, '..')
function archivos(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    if (statSync(p).isDirectory()) return n === '__tests__' ? [] : archivos(p)
    return /\.(ts|tsx)$/.test(n) && !/\.test\.tsx?$/.test(n) ? [p] : []
  })
}

describe('un solo formulario de producto', () => {
  const llamadas = archivos(raiz).flatMap((f) => {
    const s = readFileSync(f, 'utf8')
    const n = (s.match(/productsApi\.(create|update)\(/g) ?? []).length
    return n > 0 ? [[f.replace(raiz, ''), n] as const] : []
  })
  it('solo FormularioProducto llama a productsApi.create/update', () => {
    expect(llamadas).toEqual([['/components/products/FormularioProducto.tsx', 2]])
  })
  it('los formularios viejos ya no existen', () => {
    const todo = archivos(raiz).map((f) => readFileSync(f, 'utf8')).join('\n')
    expect(todo).not.toMatch(/function ProductFormModal\b/)
    expect(todo).not.toMatch(/function ProductModal\b/)
    expect(todo).not.toMatch(/AdminProductCreate/)
  })
})
```

Nota: `api/products.ts` define `create:`/`update:` pero no los *llama* con `productsApi.`, así que no cuenta. Si otro archivo legítimo llama a `productsApi.update(` (por ejemplo para activar/desactivar), ajusta la expectativa listándolo con su conteo y explica en el commit por qué no es un formulario.

Run: `cd frontend && npx vitest run src/__tests__/unSoloFormularioDeProducto.test.ts` → FAIL.

- [ ] **Step 2: Cambiar `ProductsBranchView.tsx`**

Estado: `editing` pasa a `useState<{ productId: string; variantId?: string } | null>(null)`; `openEdit` ya no carga el producto:

```tsx
  function openEdit(p: ProductRow) {
    setEditing({ productId: p.id, variantId: p.variant_id })
  }
```

Montaje (sustituye 319-338):

```tsx
      {creating && (
        <Modal open onClose={() => setCreating(false)} size="xl" closeOnBackdrop={false} title="Nuevo producto">
          <FormularioProducto mode="create" presentacion="modal"
            onDone={() => { setCreating(false); load(search); loadKpis() }}
            onCancel={() => setCreating(false)} />
        </Modal>
      )}
      {editing && (
        <Modal open onClose={() => setEditing(null)} size="xl" closeOnBackdrop={false} title="Editar producto">
          <FormularioProducto mode="edit" productId={editing.productId} variantId={editing.variantId} presentacion="modal"
            onDone={() => { setEditing(null); load(search); loadKpis() }}
            onCancel={() => setEditing(null)} />
        </Modal>
      )}
```

Importar `Modal` de `'../ui/Modal'` y `FormularioProducto` de `'../products/FormularioProducto'`. Borrar `ProductFormModal`, `TierRow`, `PackRow`, y los imports que queden sin uso (`useRef`, `ProductPrice`, `PackagingUnit`, `esFilaPrincipal`, `planIdentidadDeFila`, `nombreDeVariante`, `grupoDeVariantes`… solo los que `tsc`/eslint acusen). El `Modal` local (1073-1093) se borra solo si `ImportExcelModal` y `StockAdjustModal` no lo usan; si lo usan, se queda (migrarlos no es parte de este plan).

- [ ] **Step 3: Pruebas, build, commit**

Run: `cd frontend && npx vitest run && npm run build` → verde.

```bash
git add frontend/src/components/branch/ProductsBranchView.tsx frontend/src/__tests__/unSoloFormularioDeProducto.test.ts
git commit -m "refactor(products-ui): la lista de sucursal usa FormularioProducto; un solo create/update en el frontend"
```

---

### Task 10: El importador de HQ ya no esconde los errores por fila

**Files:**
- Modify: `frontend/src/pages/inventory/Products.tsx` (`ImportModal`, 26-185 en la base; la condición de cierre en `:43` y el bloque de resultado `:168-175`)
- Create: `frontend/src/pages/inventory/importacion.ts`
- Test: `frontend/src/pages/inventory/__tests__/importacion.test.ts`

**Interfaces:**
- Produces: `debeCerrarSolo(r: { created: number; updated: number; errors?: string[] }): boolean` (true solo si hubo altas o cambios **y** ningún error).

- [ ] **Step 1: Prueba (falla)**

```ts
import { describe, it, expect } from 'vitest'
import { debeCerrarSolo } from '../importacion'

describe('debeCerrarSolo', () => {
  it('cierra cuando todo entró sin errores', () => {
    expect(debeCerrarSolo({ created: 3, updated: 0, errors: [] })).toBe(true)
  })
  it('se queda abierto si hubo errores por fila, aunque algo haya entrado', () => {
    expect(debeCerrarSolo({ created: 2, updated: 0, errors: ['Fila 3: precio 0'] })).toBe(false)
  })
  it('se queda abierto si no entró nada', () => {
    expect(debeCerrarSolo({ created: 0, updated: 0 })).toBe(false)
  })
})
```

- [ ] **Step 2: Implementar y usar**

```ts
/** El modal de importación solo se cierra solo cuando no hay nada que leer. */
export function debeCerrarSolo(r: { created: number; updated: number; errors?: string[] }): boolean {
  return (r.created > 0 || r.updated > 0) && (r.errors?.length ?? 0) === 0
}
```

En `ImportModal`, donde hoy dice (≈43) `if (res.created > 0 || res.updated > 0) onDone()` (o equivalente), usar `if (debeCerrarSolo(res)) onDone()`; en el bloque de resultado con errores (168-175) asegurarse de que haya un botón "Cerrar" que llame a `onDone()` (para que la lista se recargue con lo que sí entró). El backend de SP1 ya rechaza filas con precio ≤ 0 y las reporta en `errors`; con el cierre automático la tienda no las veía.

- [ ] **Step 3: Pruebas, build, commit**

Run: `cd frontend && npx vitest run src/pages/inventory && npm run build` → verde.

```bash
git add frontend/src/pages/inventory/importacion.ts frontend/src/pages/inventory/__tests__/importacion.test.ts frontend/src/pages/inventory/Products.tsx
git commit -m "fix(products-ui): el importador de HQ muestra los errores por fila en vez de cerrarse"
```

---

## Cierre del plan

- Suite completa: `python3 -m pytest -q --ignore=tests/test_cash_complete.py` (1422) y `cd frontend && npx vitest run && npm run build`.
- Humo manual con cuenta QA (antes de fusionar, en el stack local `docker compose up -d` o en beta): (1) admin crea desde el Catálogo con dos tallas y existencia en una sucursal → vuelve al Catálogo y el producto aparece; (2) admin edita desde `/products` un producto con empaques → los empaques siguen; (3) cajera de Eleven edita desde su lista el renglón de la talla 41 y cambia el SKU → la 40 no cambia; (4) Kaory (ATLAS_POS) abre "Nuevo producto" → sin género/modelo/material; abre uno que ya tiene género → se ve.
- **Despliegue:** frontend más un campo aditivo en `/me/context`; sin migraciones. Va después (o junto) de `feat/sp1-altas-servicio-backend`, de la que parte. Si SP2 ya se fusionó a `main` antes, `enabledModulesStore.ts` y `app/modules/users/router.py` tendrán un conflicto pequeño (campo `plan` junto a `campos_producto`): se resuelve conservando ambos.
- **Fuera de alcance (anotar para SP5/SP7):** unificar los dos importadores, migrar `ImportModal`/`ImportExcelModal`/`StockAdjustModal` a `components/ui/Modal`, el `readOnly` de SKU/precio para un CAJERO sin sucursal que `ProductModal` aplicaba (el backend ya limita lo que un cajero puede editar con `_principal_editable_por_cajero`), partir `Products.tsx` y `ProductsBranchView.tsx`.
