# Fase 3 · Fusiones y menú del administrador — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un solo módulo por concepto en el admin: `/sales`, `/returns`, `/inventory` y `/products` absorben lo que hacían `HQSalesLog`, `HQReturns`, `HQInventory` y `AdminCatalog` (que se borran), las URL viejas redirigen conservando la consulta, y el menú del administrador queda con los grupos de la spec §4.2.

**Architecture:** Cada pantalla que sobrevive se reescribe (o se amplía, en Productos) sobre el kit `components/ui/` y los tokens `dax-*`, con las funciones de oficina gateadas por rol (`esRolHq`: ADMINISTRADOR y DUEÑO) y, donde aplica, por "más de una sucursal que vende" (`useSucursalesVendibles`). `branch_id` solo viaja cuando un rol de oficina elige sucursal: el backend impone la sucursal a la cajera y, según el endpoint, al gerente (`/sales/` y `/sales/stats` lo confinan a la suya; `/returns/` lo trata como oficina —`HQ_ROLES` de `app/services/metricas_ventas.py:35` incluye GERENTE— y le da toda la organización, como hoy). Las rutas viejas pasan a `<RedirigirConQuery a="/nueva" />` en `App.tsx` (React Router; `app/main.py` no cambia). El menú se reordena en `navConfig.ts` y las guardias estáticas (`coloresPorTokens`, `overlaysFueraDelKit`, `responsivoOla2`, nueva `fusionesAdmin`) fijan el resultado.

**Tech Stack:** React 18 + Vite + TypeScript + Tailwind (tokens `dax` de `tailwind.config.js`), react-router-dom 6, zustand, vitest 2 + @testing-library/react 16 (jsdom). Backend FastAPI sin cambios (solo verificación).

**Spec:** `docs/superpowers/specs/2026-10-23-admin-precision-inicio-fusiones-design.md` — §4 (4.1 Pantallas, 4.2 Menú), §1 (tabla de duplicados), §5, §6, §7, §8 (criterio 3: "ningún módulo del admin repetido; las URL viejas redirigen"). §2 y §3 ya están en `main` (4321268e).

## Global Constraints

- **Worktree:** `/mnt/d/Devs/atlas-one/.worktrees/admin-fase3`, rama `feat/admin-fase3-fusiones-menu` (base `main` 4321268e). Todas las rutas de este plan son relativas a esa raíz. `frontend/node_modules` es un enlace al checkout principal: `npm ci` no hace falta. No hacer `cd` al checkout principal.
- **Las cuatro fusiones (spec §4.1):** la base sobrevive en la URL corta; la pantalla HQ se borra con `git rm`; la URL vieja redirige **conservando la consulta** (`/hq/inventory?q=ABR-1&variant=v9` → `/inventory?q=ABR-1&variant=v9`) con `components/layout/RedirigirConQuery.tsx` (Tarea 1). Nada se añade al backend: `app/main.py` no tiene redirect de `/hq/*` (el de `/hq/sales` se quitó en la Fase 1, commit 97fc2e72; `tests/test_sales_rutas.py::test_hq_sales_no_redirige_a_ruta_muerta` lo vigila) y el catch-all de la SPA sirve la ruta.
- **"Solo HQ"** = `esRolHq(user.role)` (`frontend/src/utils/rolesHq.ts`, Tarea 1: `ADMINISTRADOR` y `DUEÑO`). Igual que hacen hoy `HQInventory` (`ADMIN_ROLES`) y `Products` (`HQ_ROLES`): no se mira `platform_role` (quien impersona trae un rol de tenant). GERENTE **no** ve costos (regla de la valuación, Fase 1) ni selector de sucursal.
- **"Más de una sucursal"** = sucursales activas con `can_sell !== false`, como el Inicio y Reportes de la Fase 2 (`useSucursalesVendibles(esHq)`, Tarea 1: solo HQ pide `/branches/`). El selector arranca en "Todas las sucursales" y vive en el estado de la pantalla (no se persiste: la spec calla y hoy tampoco se persiste).
- **Periodos:** Ventas y Devoluciones usan los presets de `pages/reports/presetsReportes.ts` (`Hoy · Ayer · 7 días · 30 días · Este mes` + rango a mano; mismos tramos que `metricas_ventas.periodo_preset`). Ventas arranca en **Hoy** (como `HQSalesLog` al abrir; ruling del coordinador); Devoluciones en `30d` y el periodo acota **solo el Historial**: los Pendientes se piden siempre completos.
- **Lo que cada rol ve hoy se conserva:** la cajera sigue con Ver/Reimprimir/Devolver y el asistente de devoluciones (`ReturnsBranchView`); el gerente aprueba devoluciones; cajera y gerente llegan a `/inventory` desde "Ajustar" del editor de variantes (la ruta sigue **sin** `RutaPorRol`, como hoy) y ven kardex y ajuste sin costos. Productos en perfil **básico** no cambia: todo lo que viene de `AdminCatalog` se pinta solo con `isHQ && !modoBasico` (el modo básico escondía el Catálogo a propósito).
- **Tokens (CLAUDE.md §6):** `SalesHistory.tsx`, `Returns.tsx`, `Inventory.tsx` y `pages/core/catalogActions.ts` se reescriben limpios: cero `text-white`, `slate-*`, hex y **ninguna clase de paleta Tailwind** (van a `LIMPIOS` de `coloresPorTokens.test.ts` y salen de `PENDIENTES`). Solo `text-dax-*`, `bg-dax-*`, `border-dax-*` (`tailwind.config.js` → `colors.dax`: `bg`, `surface`, `card`, `border`, `border-dim`, `accent`, `accent-text`, `accent-soft`, `on-accent`, `text`, `muted`, `faint`, `elevated`, `success`, `warning`, `danger`, `success-soft`, `warning-soft`, `danger-soft`) y las clases del kit (`dax-badge-*`, `dax-btn-*`, `dax-input`, `dax-table`, `dax-card`). `Products.tsx` (829 líneas) recibe ediciones acotadas y **se queda en `PENDIENTES`**; todo JSX nuevo que se le añade es solo tokens.
- **Responsivo (CLAUDE.md §5):** `useEsTelefono()`; `CabeceraPagina`, `BarraFiltros`/`ParFechas`; `<table>` en escritorio y `ListaTarjetas`/`TarjetaFila` bajo 768 con render condicional (`esTelefono ? … : …`), nunca `hidden md:block`; rejillas de 3+ columnas siempre con prefijo; modales con `ui/Modal` (ningún `fixed inset-0` nuevo: las tres pantallas reescritas salen de `CONOCIDOS` en `overlaysFueraDelKit.test.ts`); botones `dax-btn-primary/-secondary/-danger/-ghost`, solo icono con `dax-btn-icon`.
- **Menú (spec §4.2):** grupos y orden exactos de la tabla; `ROLE_ROUTES` de ADMINISTRADOR y DUEÑO ganan `/returns` e `/inventory` y pierden `/hq/sales`, `/hq/returns`, `/hq/inventory`, `/admin/catalog`; `OCULTAS_BASICO_HQ` pierde esas cuatro y gana `/returns` (`/inventory` ya estaba). Rótulos: el ítem de `/sales` pasa de «Mis ventas» a «Ventas» para todos (glosario: una pantalla, un nombre); `/inventory` se llama «Inventario» («Existencias» desaparece con `/hq/inventory`).
- **Pruebas frontend:** `cd frontend && npx vitest run <rutas relativas a frontend/> --reporter=dot` (el entorno por defecto es `node`: cada prueba de pantalla lleva `// @vitest-environment jsdom`); `npx tsc --noEmit -p tsconfig.json` (excluye `*.test.ts(x)`); `npm run build`. Las pruebas de pantalla usan los stores reales (`useAuthStore.setState`, `useEnabledModulesStore.setState`, `useBranchCountStore.setState`) y `vi.mock` de los módulos de API (patrón de `pages/hq/__tests__/HQInventory.test.tsx`).
- **Pruebas backend (solo en la Tarea 7):** `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py --ignore=tests/test_branch_dashboard.py --ignore=tests/test_cash_close_guided.py` (hoy 1638 passed; los dos últimos fallan en esta máquina por un uvicorn ajeno en :8000). **Un solo pytest por worktree.**
- **Estilo:** comentarios e identificadores en español; sin `print()`/`console.log` de depuración; `type="button"` en todo botón nuevo.
- **Commits:** uno por tarea, con `git add`/`git rm` de rutas explícitas y los trailers
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y
  `Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf`. **Nunca push ni merge**: la fusión la autoriza el usuario.

## Review Focus

1. **Dueña con una tienda y una bodega** (`can_sell=false`): no debe ver selector ni columna "Sucursal" en Ventas ni en Devoluciones (Tarea 1, `SalesHistory.test.tsx` «con una sola sucursal que vende…»; Tarea 2, `Returns.test.tsx` «la administradora con dos sucursales…» cubre el caso contrario).
2. **Una devolución pendiente de hace dos meses** sigue en Pendientes aunque el historial esté en «30 días» (Tarea 2, `Returns.test.tsx` «en Historial, el preset Hoy acota solo el historial…»).
3. **Cajera que entra a `/inventory` desde «Ajustar»** del editor de variantes: abre el kardex de esa talla, sin costos ni casilla «Solo sin costo» (Tarea 3, `Inventory.test.tsx` «la cajera tampoco ve costos» y «?q=&variant= siembra la búsqueda…»).
4. **Enlace viejo con filtros** (`/hq/inventory?q=ABR-1&variant=v9`, un marcador o un correo): llega a `/inventory?q=ABR-1&variant=v9` y abre ese kardex (Tarea 1, `RedirigirConQuery.test.tsx` «conserva la consulta…»; Tarea 5, `fusionesAdmin.test.ts`).
5. **Dueña FREE en básico en `/products`**: no ve cifras, aprobación ni archivados, y no se consultan (`catalogKpis`/`getBrands` sin llamadas) (Tarea 4, `ProductsCatalogo.test.tsx` «en básico la dueña no ve cifras…»).

---

## Decisiones donde la spec calla (resumen; cada tarea las repite donde aplican)

| Tema | Decisión |
|---|---|
| Qué es "HQ" | `esRolHq(role)`: ADMINISTRADOR o DUEÑO. Sin `platform_role`. |
| Qué es "más de una sucursal" | sucursales activas que venden (`can_sell !== false`), como Inicio/Reportes. Solo HQ pide `/branches/`. |
| Selector de sucursal | estado en memoria, arranca en «Todas». |
| Presets de fecha | `presetsReportes` en Ventas (arranca en Hoy) y Devoluciones (30d, solo historial). |
| «Incluir abiertas/borradores» en Ventas | arranca **encendida** para HQ (`HQSalesLog` mostraba PENDING/DRAFT) y apagada para cajera y gerente (como `SalesHistory`). |
| Cifra «Método principal · $X recaudado» de `HQSalesLog` | se deja caer: la `KpiCard` «Método top» muestra solo el método (decisión aceptada). |
| Buscador de folio/cliente | se conserva de `HQSalesLog` para todos (filtro en cliente). |
| Rótulos de estado en Ventas | los de `SalesHistory` (`Pagado`, `Dev. parcial`…) y sus métodos (incluye `Crédito tienda`, `Cheque`, `Mixto`); en Devoluciones, `estadoDevolucion` de `utils/enumsEspanol` (antes la base mostraba `PENDING` crudo). |
| GERENTE en Inventario | sin costo, sin «Solo sin costo», con kardex (columna «Por») y ajuste. |
| GERENTE en Devoluciones | sin selector, pero con columna «Sucursal»: `/returns/` le da toda la organización (como hoy) y sus filas pueden venir de otras sucursales. |
| Gates del menú | `/returns` sigue sin `module:` y `/inventory` sin `hideForGastro`: un solo ítem sirve a todos los roles y giros. |
| Ruta `/inventory` | sigue sin `RutaPorRol` (hoy cualquier rol autenticado llega desde «Ajustar»); solo se añade al menú de ADMIN/DUEÑO. |
| Productos en básico | nada del Catálogo viejo (`isHQ && !modoBasico`). |
| Matriz de sucursales | solo con más de una sucursal (`!esTiendaUnica`); con una, el formulario ya trae su sección de sucursal. |
| Vista de cuadrícula de Productos | conserva solo Editar; las acciones de catálogo viven en la lista. |
| Exportar, duplicar, cifras y filtro por marca | se conservan de `AdminCatalog` solo para HQ en perfil completo (la spec §4.1 no marca duplicar ni cifras como «solo HQ»: desviación aceptada, cajera y gerente siguen en `ProductsBranchView`; la Tarea 6 la anota en la spec). Productos sin sucursal llevan un `Badge` «Sin sucursal» visible. |
| `DELETE /products/{id}` | nuevo `productsApi.archive(id)` (antes `client.delete` con import dinámico). |
| `/admin/products/new` | redirige a `/products/new` (el regreso por defecto ya es `/products`). |
| `app/core/role_permissions.py` y `app/ui/nav_registry.py` | conservan las URL viejas: el frontend no los consume y el redirect cubre. Fuera de alcance; anotado en `docs/RBAC.md`. |
| Orden de grupos | el de la tabla §4.2 (Restaurante pasa al 7.º lugar). |

---

### Task 1: Ventas — `SalesHistory` absorbe `HQSalesLog`; `RedirigirConQuery`

**Files:**
- Create: `frontend/src/utils/rolesHq.ts`
- Create: `frontend/src/hooks/useSucursalesVendibles.ts`
- Create: `frontend/src/components/layout/RedirigirConQuery.tsx`
- Create: `frontend/src/components/layout/__tests__/RedirigirConQuery.test.tsx`
- Rewrite: `frontend/src/pages/sales/SalesHistory.tsx`
- Create: `frontend/src/pages/sales/__tests__/SalesHistory.test.tsx`
- Delete: `frontend/src/pages/hq/HQSalesLog.tsx`
- Modify: `frontend/src/App.tsx:14-15, 29, 279`
- Modify: `frontend/src/pages/hq/Inicio.tsx:49`, `frontend/src/pages/hq/__tests__/Inicio.test.tsx:300`
- Modify: `frontend/src/__tests__/coloresPorTokens.test.ts:26,33,41-44`, `frontend/src/__tests__/overlaysFueraDelKit.test.ts:51`, `frontend/src/pages/__tests__/responsivoOla2.test.ts:9`

**Interfaces:**
- Produces: `esRolHq(role: string | null | undefined): boolean` y `ROLES_HQ: ReadonlySet<string>` (`utils/rolesHq.ts`); `useSucursalesVendibles(activo: boolean): Branch[]` (`hooks/useSucursalesVendibles.ts`; `Branch` de `api/organization`); `RedirigirConQuery({ a }: { a: string })` (`components/layout/RedirigirConQuery.tsx`). Las Tareas 2-4 los consumen.
- Consumes: `PRESETS`, `rangoPreset`, `presetActivo`, `ClavePreset`, `Rango` de `pages/reports/presetsReportes.ts`; `KpiCard` de `components/ui/KpiCard.tsx`; `salesApi.list/getStats`, `organizationApi.getBranches` (ya existen).

- [ ] **Step 1: Utilidades compartidas**

`frontend/src/utils/rolesHq.ts`:

```ts
// frontend/src/utils/rolesHq.ts
/**
 * Roles de oficina (spec 2026-10-23 §4.1, "Solo HQ"): ven toda la organización,
 * los costos y las acciones de catálogo. Es la misma lista que usaban
 * `HQInventory` (ADMIN_ROLES) y `Products` (HQ_ROLES). No mira `platform_role`:
 * quien impersona trae un rol de tenant.
 */
export const ROLES_HQ: ReadonlySet<string> = new Set(['ADMINISTRADOR', 'DUEÑO'])

export const esRolHq = (role: string | null | undefined): boolean => ROLES_HQ.has(role ?? '')
```

`frontend/src/hooks/useSucursalesVendibles.ts`:

```ts
// frontend/src/hooks/useSucursalesVendibles.ts
import { useEffect, useState } from 'react'
import { organizationApi, type Branch } from '../api/organization'

/**
 * Sucursales activas que venden, para el selector de las pantallas fusionadas
 * (Ventas, Devoluciones). Misma regla que Inicio y Reportes: una bodega no es
 * "una tienda" para filtrar. Solo pide `/branches/` cuando `activo` (rol de
 * oficina); si la lista falla, no hay selector y la pantalla sigue.
 */
export function useSucursalesVendibles(activo: boolean): Branch[] {
  const [sucursales, setSucursales] = useState<Branch[]>([])
  useEffect(() => {
    if (!activo) return
    let vigente = true
    organizationApi.getBranches()
      .then((bs) => { if (vigente) setSucursales(bs.filter((b) => b.is_active !== false && b.can_sell !== false)) })
      .catch(() => { /* sin lista no hay selector */ })
    return () => { vigente = false }
  }, [activo])
  return sucursales
}
```

`frontend/src/components/layout/RedirigirConQuery.tsx`:

```tsx
// frontend/src/components/layout/RedirigirConQuery.tsx
import { Navigate, useLocation } from 'react-router-dom'

/**
 * Redirección que conserva la consulta (`?q=…&variant=…`) y el hash. Para las
 * URL viejas del admin que la Fase 3 fusionó (`/hq/sales` → `/sales`, …): un
 * enlace guardado con filtros sigue abriendo lo mismo en la ruta nueva.
 */
export function RedirigirConQuery({ a }: { a: string }) {
  const { search, hash } = useLocation()
  return <Navigate to={`${a}${search}${hash}`} replace />
}
```

- [ ] **Step 2: Prueba de la redirección (falla: el módulo no existe aún si saltaste el paso 1; si no, pasa)**

`frontend/src/components/layout/__tests__/RedirigirConQuery.test.tsx`:

```tsx
// frontend/src/components/layout/__tests__/RedirigirConQuery.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import { render, screen, cleanup } from '@testing-library/react'
import { RedirigirConQuery } from '../RedirigirConQuery'

function Destino() {
  const { pathname, search, hash } = useLocation()
  return <p data-testid="destino">{pathname}{search}{hash}</p>
}
const pintar = (inicial: string) => render(
  <MemoryRouter initialEntries={[inicial]}>
    <Routes>
      <Route path="hq/sales" element={<RedirigirConQuery a="/sales" />} />
      <Route path="hq/inventory" element={<RedirigirConQuery a="/inventory" />} />
      <Route path="admin/catalog" element={<RedirigirConQuery a="/products" />} />
      <Route path="*" element={<Destino />} />
    </Routes>
  </MemoryRouter>,
)
afterEach(cleanup)

describe('RedirigirConQuery (URL viejas del admin, spec §4.1)', () => {
  it('conserva la consulta al redirigir', () => {
    pintar('/hq/inventory?q=ABR-1&variant=v9')
    expect(screen.getByTestId('destino').textContent).toBe('/inventory?q=ABR-1&variant=v9')
  })
  it('sin consulta llega limpio', () => {
    pintar('/hq/sales')
    expect(screen.getByTestId('destino').textContent).toBe('/sales')
  })
  it('conserva también el hash', () => {
    pintar('/admin/catalog?x=1#arriba')
    expect(screen.getByTestId('destino').textContent).toBe('/products?x=1#arriba')
  })
})
```

Run: `cd frontend && npx vitest run src/components/layout/__tests__/RedirigirConQuery.test.tsx --reporter=dot`
Expected: 3 passed.

- [ ] **Step 3: Prueba de la pantalla fusionada (falla contra la pantalla vieja)**

`frontend/src/pages/sales/__tests__/SalesHistory.test.tsx`:

```tsx
// frontend/src/pages/sales/__tests__/SalesHistory.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react'

const { list, getStats, getBranches } = vi.hoisted(() => ({ list: vi.fn(), getStats: vi.fn(), getBranches: vi.fn() }))
vi.mock('../../../api/sales', () => ({ salesApi: { list, getStats } }))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches } }))
vi.mock('../../../api/printer', () => ({ printerApi: { getTicketBase64: vi.fn(), printViaAgent: vi.fn() } }))
vi.mock('../../../store/posStore', () => ({
  usePOSStore: (sel: (s: { printerName: string | null }) => unknown) => sel({ printerName: null }),
}))
vi.mock('../../../components/pos/modals/ReturnModal', () => ({ ReturnModal: () => <div data-testid="return-modal" /> }))
vi.mock('../../../components/pos/modals/ReprintPinModal', () => ({ ReprintPinModal: () => <div data-testid="pin-modal" /> }))

import { SalesHistory } from '../SalesHistory'
import { useAuthStore } from '../../../store/authStore'
import { rangoPreset } from '../../reports/presetsReportes'

const hoy = rangoPreset('hoy')
const VENTA = {
  id: 'venta-1', series: 'A', folio: 41, status: 'PAID', total_amount: 250, subtotal: 250, tax_amount: 0,
  created_at: '2026-10-20T15:00:00Z', customer_name: null, branch_id: 1, branch_name: 'Roma',
  payments: [{ method: 'CASH', amount: 250 }],
  lines: [{ description: 'Blusa', sku: 'BLU', quantity: 1, unit_price: '250', total_line: '250' }],
}
const STATS = { total_sales: 250, total_transactions: 1, average_ticket: 250, payment_methods: { CASH: 250 }, refund_count: 0, refund_total: 0, peak_hour: '15:00' }
const SUC = (id: number, name: string, can_sell = true) =>
  ({ id, name, branch_type: 'STORE', address: null, phone: null, is_headquarters: false, is_active: true, can_sell })
const usuario = (role: string, branch_id: number | null = null) =>
  useAuthStore.setState({ user: { id: 1, username: 'u', role, branch_id, platform_role: 'NONE' } } as never)
const pintar = () => render(<MemoryRouter><SalesHistory /></MemoryRouter>)
const cabeceras = () => screen.getAllByRole('columnheader').map((th) => th.textContent)

beforeEach(() => {
  list.mockReset().mockResolvedValue({ items: [VENTA], total: 1, page: 0, pages: 1 })
  getStats.mockReset().mockResolvedValue(STATS)
  getBranches.mockReset().mockResolvedValue([SUC(1, 'Roma'), SUC(2, 'Condesa')])
})
afterEach(cleanup)

describe('Ventas (/sales, fusión de HQSalesLog)', () => {
  it('la cajera arranca en Hoy, solo estados cerrados, sin pedir sucursales ni mandar branch_id; el título es Ventas', async () => {
    usuario('CAJERO', 1)
    pintar()
    await screen.findByText('A-0041')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Ventas')
    expect(screen.getByRole('button', { name: 'Hoy' }).getAttribute('aria-pressed')).toBe('true')
    expect(list).toHaveBeenCalledWith({
      start_date: hoy.inicio, end_date: hoy.fin, limit: 100, skip: 0, statuses: 'PAID,REFUNDED_PARTIAL,REFUNDED_TOTAL,CANCELLED',
    })
    expect(getStats).toHaveBeenCalledWith({ start_date: hoy.inicio, end_date: hoy.fin })
    expect((screen.getByLabelText('Incluir abiertas/borradores') as HTMLInputElement).checked).toBe(false)
    expect(getBranches).not.toHaveBeenCalled()
    expect(screen.queryByLabelText('Sucursal')).toBeNull()
    expect(cabeceras()).not.toContain('Sucursal')
  })

  it('la cajera conserva Ver, Reimprimir y Devolver; el detalle abre el Modal del kit', async () => {
    usuario('CAJERO', 1)
    pintar()
    await screen.findByText('A-0041')
    expect(screen.getByRole('button', { name: /Reimprimir/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Devolver/ })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Ver' }))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText('Blusa')).toBeTruthy()
    expect(within(dialogo).getByRole('button', { name: /Registrar devolución/ })).toBeTruthy()
  })

  it('la administradora con dos sucursales que venden ve el selector y la columna Sucursal; al elegir una manda branch_id', async () => {
    usuario('ADMINISTRADOR')
    pintar()
    await screen.findByText('A-0041')
    const selector = await screen.findByLabelText('Sucursal')
    expect(cabeceras()).toContain('Sucursal')
    expect(list.mock.calls[0][0]).not.toHaveProperty('branch_id')
    // HQ veía abiertas y borradores por defecto (HQSalesLog): la casilla arranca encendida y no viaja `statuses`.
    expect((screen.getByLabelText('Incluir abiertas/borradores') as HTMLInputElement).checked).toBe(true)
    expect(list.mock.calls[0][0]).not.toHaveProperty('statuses')
    fireEvent.change(selector, { target: { value: '2' } })
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ branch_id: 2, skip: 0 })))
    expect(getStats).toHaveBeenLastCalledWith({ start_date: hoy.inicio, end_date: hoy.fin, branch_id: 2 })
  })

  it('con una sola sucursal que vende (la otra es bodega) no hay selector ni columna', async () => {
    usuario('DUEÑO')
    getBranches.mockResolvedValue([SUC(1, 'Roma'), SUC(9, 'Bodega', false)])
    pintar()
    await screen.findByText('A-0041')
    await waitFor(() => expect(getBranches).toHaveBeenCalled())
    expect(screen.queryByLabelText('Sucursal')).toBeNull()
    expect(cabeceras()).not.toContain('Sucursal')
  })

  it('el buscador filtra por folio o cliente sin volver al servidor', async () => {
    usuario('CAJERO', 1)
    list.mockResolvedValue({ items: [VENTA, { ...VENTA, id: 'venta-2', folio: 42, customer_name: 'Lupita' }], total: 2, page: 0, pages: 1 })
    pintar()
    await screen.findByText('A-0042')
    fireEvent.change(screen.getByLabelText('Buscar folio o cliente'), { target: { value: 'lupita' } })
    expect(screen.queryByText('A-0041')).toBeNull()
    expect(screen.getByText('A-0042')).toBeTruthy()
    expect(list).toHaveBeenCalledTimes(1)
  })
})
```

Run: `cd frontend && npx vitest run src/pages/sales/__tests__/SalesHistory.test.tsx --reporter=dot`
Expected: FAIL (el título dice «Mis ventas», no hay selector, `list` se llama con `start_date: daysAgoStr(7)`).

Decisiones de esta tarea: Ventas arranca en **Hoy** (`HQSalesLog` abría en hoy, `SalesHistory` en 7 días hacia atrás; el coordinador fijó Hoy); «Incluir abiertas/borradores» arranca encendida para HQ (`HQSalesLog` no filtraba estados) y apagada para cajera y gerente; la cifra «Método principal · $X recaudado» de `HQSalesLog` se deja caer (la `KpiCard` «Método top» muestra solo el método).

- [ ] **Step 4: Reescribir `SalesHistory.tsx`**

Sustituir el archivo completo por:

```tsx
// frontend/src/pages/sales/SalesHistory.tsx
import { useEffect, useState, useCallback, useMemo } from 'react'
import { salesApi, type SalesStats } from '../../api/sales'
import { printerApi } from '../../api/printer'
import { usePOSStore } from '../../store/posStore'
import { useAuthStore } from '../../store/authStore'
import { DaxCard } from '../../components/ui/DaxCard'
import { Modal } from '../../components/ui/Modal'
import { TablaDesplazable } from '../../components/ui/TablaDesplazable'
import { Spinner } from '../../components/ui/Spinner'
import { Badge } from '../../components/ui/Badge'
import { KpiCard } from '../../components/ui/KpiCard'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { BarraFiltros, ParFechas } from '../../components/ui/BarraFiltros'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { useSucursalesVendibles } from '../../hooks/useSucursalesVendibles'
import { esRolHq } from '../../utils/rolesHq'
import type { SalesDocument } from '../../types/sales'
import { saleLabel } from '../../types/sales'
import { ReturnModal } from '../../components/pos/modals/ReturnModal'
import { ReprintPinModal } from '../../components/pos/modals/ReprintPinModal'
import { formatCurrency } from '../../utils/currency'
import { toast } from '../../store/toastStore'
import { mensajeReimpresion, pinBloqueado, pinIncorrecto, requierePin } from '../../utils/reimpresion'
import { formatPct } from '../pos/cardSurcharge'
import { PRESETS, presetActivo, rangoPreset, type ClavePreset, type Rango } from '../reports/presetsReportes'

/**
 * Ventas (`/sales`). Una sola pantalla para todos los roles (Fase 3 del admin,
 * spec 2026-10-23 §4.1): cajera y gerente ven su sucursal (el backend la
 * impone); administrador y dueño ven toda la organización y, con más de una
 * sucursal que vende, un selector. Sustituye a `pages/hq/HQSalesLog.tsx`.
 * Solo tokens `dax-*` (coloresPorTokens.test.ts, LIMPIOS).
 */

const STATUS_LABELS: Record<string, string> = {
  PAID:             'Pagado',
  CANCELLED:        'Cancelado',
  REFUNDED_PARTIAL: 'Dev. parcial',
  REFUNDED_TOTAL:   'Dev. total',
  PENDING:          'Pendiente',
  DRAFT:            'Borrador',
}

const METHOD_LABELS: Record<string, string> = {
  CASH:         'Efectivo',
  CARD:         'Tarjeta',
  TRANSFER:     'Transferencia',
  STORE_CREDIT: 'Crédito tienda',
  CHECK:        'Cheque',
  MIXED:        'Mixto',
}

// Por defecto solo ventas realizadas (PAID, REFUNDED_*) y CANCELLED: PENDING y
// DRAFT son créditos abiertos / borradores que confunden a la cajera ("¿vendí o no?").
const ESTADOS_CERRADOS = 'PAID,REFUNDED_PARTIAL,REFUNDED_TOTAL,CANCELLED'
const LIMIT = 100

// Formatos de la fila: los comparten la tabla (escritorio) y la tarjeta (teléfono).
const fechaVenta = (s: SalesDocument) =>
  new Date(s.created_at).toLocaleString('es-MX', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
const clienteVenta = (s: SalesDocument) =>
  s.customer_name ?? <span className="text-dax-faint italic">Público general</span>
const pagosVenta = (s: SalesDocument) =>
  s.payments?.map((p, i) => (
    <span key={i} className="dax-badge dax-badge-blue mr-1">{METHOD_LABELS[p.method] ?? p.method}</span>
  ))
const sePuedeDevolver = (s: SalesDocument) => s.status === 'PAID' || s.status === 'REFUNDED_PARTIAL'
// Estados reales del backend: PAID / CANCELLED / REFUNDED_* / PENDING / DRAFT
const statusVariant = (s: string): 'green' | 'red' | 'blue' | 'yellow' =>
  s === 'PAID' ? 'green' : s === 'CANCELLED' ? 'red' : s.startsWith('REFUNDED') ? 'blue' : 'yellow'
const badgeEstado = (s: SalesDocument) => <Badge variant={statusVariant(s.status)}>{STATUS_LABELS[s.status] ?? s.status}</Badge>

export function SalesHistory() {
  const printerName = usePOSStore((s) => s.printerName)
  const esHq = esRolHq(useAuthStore((s) => s.user?.role))
  const esTelefono = useEsTelefono()
  // Solo los roles de oficina piden la lista; el selector sale con más de una sucursal que vende.
  const sucursales = useSucursalesVendibles(esHq)
  const conSucursales = esHq && sucursales.length > 1
  const [sucursal, setSucursal] = useState<number | ''>('')

  const [sales, setSales] = useState<SalesDocument[]>([])
  const [stats, setStats] = useState<SalesStats | null>(null)
  const [loading, setLoading] = useState(true)
  // Arranca en Hoy, como la pantalla HQ que sustituye.
  const [rango, setRango] = useState<Rango>(() => rangoPreset('hoy'))
  const [desde, setDesde] = useState(rango.inicio)
  const [hasta, setHasta] = useState(rango.fin)
  // En el día 1 del mes «Este mes» y «Hoy» son el mismo rango: se recuerda cuál se pulsó.
  const [presetElegido, setPresetElegido] = useState<ClavePreset | null>('hoy')
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [busqueda, setBusqueda] = useState('')
  // HQ veía PENDING/DRAFT por defecto (HQSalesLog); la cajera no (SalesHistory). Cada rol conserva su costumbre.
  const [includeOpenStates, setIncludeOpenStates] = useState(esHq)
  const [selected, setSel] = useState<SalesDocument | null>(null)
  const [returnSale, setReturnSale] = useState<SalesDocument | null>(null)
  const [reprinting, setReprinting] = useState(false)
  // Venta cuya reimpresión espera el PIN de un supervisor (428 del backend).
  const [ventaPorAutorizar, setVentaPorAutorizar] = useState<SalesDocument | null>(null)

  /**
   * Reimprime un ticket. El backend exige rol gerencial o el PIN de un
   * supervisor (428) salvo que sea una venta propia recién cobrada, así que el
   * primer intento va sin PIN y solo se pide cuando hace falta.
   *
   * Devuelve el mensaje de error si el PIN no sirvió —el modal lo muestra y
   * deja reintentar— o null cuando ya no hay nada pendiente.
   */
  const reprintTicket = async (sale: SalesDocument, pin?: string): Promise<string | null> => {
    if (!printerName) {
      toast.error('Configura una impresora en /printer-settings primero')
      return null
    }
    setReprinting(true)
    try {
      const b64 = await printerApi.getTicketBase64(sale.id, pin)
      if (b64) await printerApi.printViaAgent(printerName, b64)
      toast.success('Ticket enviado a la impresora')
      setVentaPorAutorizar(null)
      return null
    } catch (e: unknown) {
      if (requierePin(e)) {
        setVentaPorAutorizar(sale)
        return null
      }
      // Un PIN equivocado deja el modal abierto para reintentar. El bloqueo por
      // intentos lo cierra: hay que esperar, insistir no sirve. Y cualquier otro
      // conflicto (venta cancelada, sin acceso) también lo cierra con aviso.
      if (pin && pinIncorrecto(e) && !pinBloqueado(e)) return mensajeReimpresion(e)
      toast.error(mensajeReimpresion(e))
      setVentaPorAutorizar(null)
      return null
    } finally {
      setReprinting(false)
    }
  }

  const load = useCallback(async (r: Rango, pg: number, bid: number | '') => {
    setLoading(true)
    try {
      const params: Record<string, unknown> = { start_date: r.inicio, end_date: r.fin, limit: LIMIT, skip: pg * LIMIT }
      if (!includeOpenStates) params.statuses = ESTADOS_CERRADOS
      // `branch_id` solo cuando un rol de oficina eligió sucursal. Sin él, el backend
      // da toda la organización a HQ y su sucursal a cajera y gerente (regla de la Fase 1).
      if (bid !== '') params.branch_id = bid
      const [listRes, statsRes] = await Promise.allSettled([
        salesApi.list(params),
        salesApi.getStats({ start_date: r.inicio, end_date: r.fin, ...(bid !== '' ? { branch_id: bid } : {}) }),
      ])
      if (listRes.status === 'fulfilled') {
        let items = listRes.value?.items ?? []
        // Respaldo en cliente por si el backend ignorara `statuses`.
        if (!includeOpenStates) items = items.filter((s) => !['PENDING', 'DRAFT'].includes(String(s.status)))
        setSales(items)
        setTotal(listRes.value?.total ?? items.length)
      } else {
        setSales([])
        setTotal(0)
      }
      setStats(statsRes.status === 'fulfilled' ? statsRes.value : null)
    } finally {
      setLoading(false)
    }
  }, [includeOpenStates])

  useEffect(() => { load(rango, page, sucursal) }, [load, rango, page, sucursal])

  const aplicar = (r: Rango, clave: ClavePreset | null) => {
    setRango(r); setDesde(r.inicio); setHasta(r.fin); setPresetElegido(clave); setPage(0)
  }
  const aplicarFechas = () => {
    if (desde > hasta) { toast.error('La fecha inicial no puede ser mayor que la final.'); return }
    aplicar({ inicio: desde, fin: hasta }, null)
  }
  const activo: ClavePreset | null = presetActivo(rango) && presetElegido ? presetElegido : presetActivo(rango)

  // Buscador de folio/cliente sobre la página cargada (venía de la pantalla HQ; sirve a todos).
  const visibles = useMemo(() => {
    const q = busqueda.trim().toLowerCase()
    if (!q) return sales
    return sales.filter((s) => saleLabel(s).toLowerCase().includes(q) || (s.customer_name ?? '').toLowerCase().includes(q))
  }, [sales, busqueda])
  const pages = Math.ceil(total / LIMIT)
  const metodoTop = useMemo(
    () => Object.entries(stats?.payment_methods ?? {}).sort((a, b) => b[1] - a[1])[0]?.[0],
    [stats],
  )

  // Ver / Reimprimir / Devolver: los mismos botones en la fila y en la tarjeta.
  // `stopPropagation` evita que el toque abra además el detalle de la fila.
  const accionesVenta = (s: SalesDocument) => (
    <>
      <button type="button" onClick={(e) => { e.stopPropagation(); setSel(s) }} className="dax-btn-secondary text-xs" title="Ver detalle">
        <i className="fa-solid fa-eye" aria-hidden="true" /> Ver
      </button>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); reprintTicket(s) }}
        disabled={reprinting || !printerName}
        className="dax-btn-secondary text-xs disabled:opacity-40 disabled:cursor-not-allowed"
        title={printerName ? 'Reimprimir ticket' : 'Configura una impresora'}
      >
        <i className="fa-solid fa-print" aria-hidden="true" /> Reimprimir
      </button>
      {sePuedeDevolver(s) && (
        <button type="button" onClick={(e) => { e.stopPropagation(); setReturnSale(s) }} className="dax-btn-danger text-xs" title="Iniciar devolución">
          <i className="fa-solid fa-undo" aria-hidden="true" /> Devolver
        </button>
      )}
    </>
  )

  // Paginación: una sola, debajo de la tabla (escritorio) o de las tarjetas (teléfono).
  const paginacion = pages > 1 && (
    <div className={`flex items-center justify-between px-4 py-3 ${esTelefono ? '' : 'border-t border-dax-border-dim'}`}>
      <button type="button" onClick={() => setPage(page - 1)} disabled={page === 0} className="dax-btn-secondary text-xs disabled:opacity-40 max-md:min-h-[44px]">← Anterior</button>
      <span className="text-dax-muted text-xs">Pág. {page + 1} / {pages} · {total} registros</span>
      <button type="button" onClick={() => setPage(page + 1)} disabled={page >= pages - 1} className="dax-btn-secondary text-xs disabled:opacity-40 max-md:min-h-[44px]">Siguiente →</button>
    </div>
  )

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={
          <div className="flex items-center gap-3">
            <i className="fa-solid fa-receipt text-dax-accent-text text-xl" aria-hidden="true" />
            <h1 className="text-2xl font-black text-dax-text">Ventas</h1>
          </div>
        }
      />

      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <KpiCard etiqueta="Total" valor={formatCurrency(stats.total_sales)} tono="success" data-testid="kpi-total" />
          <KpiCard etiqueta="Transacciones" valor={String(stats.total_transactions)} />
          <KpiCard etiqueta="Ticket promedio" valor={formatCurrency(stats.average_ticket)} />
          <KpiCard etiqueta="Método top" valor={metodoTop ? (METHOD_LABELS[metodoTop] ?? metodoTop) : '—'} />
          <KpiCard etiqueta="Devoluciones" valor={`${stats.refund_count ?? 0} · ${formatCurrency(stats.refund_total ?? 0)}`} tono="danger" />
          <KpiCard etiqueta="Hora pico" valor={stats.peak_hour ?? '—'} />
        </div>
      )}

      {/* `!items-center` conserva la alineación de hoy (BarraFiltros trae items-end). */}
      <BarraFiltros
        className="!items-center"
        accion={
          <button type="button" onClick={aplicarFechas} className="dax-btn-primary text-xs">
            <i className="fa-solid fa-search" aria-hidden="true" /> Filtrar
          </button>
        }
      >
        <div className="flex flex-wrap gap-1" role="group" aria-label="Periodo">
          {PRESETS.map((p) => (
            <button
              key={p.clave}
              type="button"
              onClick={() => aplicar(rangoPreset(p.clave), p.clave)}
              aria-pressed={activo === p.clave}
              className={`${activo === p.clave ? 'dax-btn-primary' : 'dax-btn-secondary'} text-xs max-sm:min-h-[44px]`}
            >
              {p.etiqueta}
            </button>
          ))}
        </div>
        <ParFechas>
          <input type="date" aria-label="Desde" value={desde} onChange={(e) => setDesde(e.target.value)} className="dax-input w-36 text-xs" />
          <input type="date" aria-label="Hasta" value={hasta} onChange={(e) => setHasta(e.target.value)} className="dax-input w-36 text-xs" />
        </ParFechas>
        {conSucursales && (
          <select
            aria-label="Sucursal"
            value={sucursal}
            onChange={(e) => { setSucursal(e.target.value ? Number(e.target.value) : ''); setPage(0) }}
            className="dax-input text-xs max-w-[180px]"
          >
            <option value="">Todas las sucursales</option>
            {sucursales.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        )}
        <input
          type="search"
          aria-label="Buscar folio o cliente"
          placeholder="Buscar folio o cliente..."
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          className="dax-input text-xs w-44"
        />
        <label className="flex items-center gap-1.5 text-[10px] text-dax-muted cursor-pointer max-md:min-h-[44px]">
          <input type="checkbox" checked={includeOpenStates} onChange={(e) => { setIncludeOpenStates(e.target.checked); setPage(0) }} className="rounded" />
          Incluir abiertas/borradores
        </label>
      </BarraFiltros>

      {/* Teléfono: tarjetas; escritorio: la tabla de siempre (nunca ambos) */}
      {esTelefono ? (
        <>
          <ListaTarjetas cargando={loading} vacio={visibles.length === 0} textoVacio="Sin ventas en este periodo">
            {visibles.map((s) => (
              <TarjetaFila
                key={s.id}
                titulo={<span className="font-mono text-dax-accent-text">{saleLabel(s)}</span>}
                subtitulo={[fechaVenta(s), conSucursales ? s.branch_name : null].filter(Boolean).join(' · ')}
                importe={<span className="text-dax-success">{formatCurrency(s.total_amount)}</span>}
                estado={badgeEstado(s)}
                datos={[
                  { etiqueta: 'Cliente', valor: clienteVenta(s) },
                  { etiqueta: 'Pago', valor: s.payments?.length ? pagosVenta(s) : '—' },
                ]}
                acciones={accionesVenta(s)}
                onClick={() => setSel(s)}
              />
            ))}
          </ListaTarjetas>
          {paginacion && <DaxCard padding={false}>{paginacion}</DaxCard>}
        </>
      ) : (
        <DaxCard padding={false}>
          {loading ? <Spinner text="Cargando ventas..." /> : visibles.length === 0 ? (
            <div className="p-12 text-center text-dax-faint">Sin ventas en este periodo</div>
          ) : (
            <TablaDesplazable sangrado={false}>
              <table className="dax-table w-full">
                <thead>
                  <tr>
                    <th>Folio</th>
                    {conSucursales && <th>Sucursal</th>}
                    <th>Fecha</th>
                    <th>Cliente</th>
                    <th className="text-right">Total</th>
                    <th>Pago</th>
                    <th>Estado</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {visibles.map((s) => (
                    <tr key={s.id} onClick={() => setSel(s)} className="cursor-pointer">
                      <td className="font-mono text-dax-accent-text text-xs">{saleLabel(s)}</td>
                      {conSucursales && <td className="text-xs text-dax-muted">{s.branch_name ?? '—'}</td>}
                      <td className="text-xs text-dax-muted">{fechaVenta(s)}</td>
                      <td className="text-sm">{clienteVenta(s)}</td>
                      <td className="text-right font-semibold text-dax-success">{formatCurrency(s.total_amount)}</td>
                      <td>{pagosVenta(s)}</td>
                      <td>{badgeEstado(s)}</td>
                      <td className="text-right">
                        <div className="flex items-center justify-end gap-2">{accionesVenta(s)}</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TablaDesplazable>
          )}
          {paginacion}
        </DaxCard>
      )}

      {/* Detalle de la venta: Modal del kit (Escape, foco, hoja inferior en teléfono). */}
      {selected && (
        <Modal
          open
          onClose={() => setSel(null)}
          size="lg"
          title={
            <span>
              <span className="block text-[10px] text-dax-muted uppercase tracking-widest">Folio</span>
              <span className="text-xl font-black text-dax-accent-text font-mono">{saleLabel(selected)}</span>
            </span>
          }
          footer={
            <>
              <button
                type="button"
                disabled={reprinting || !printerName}
                onClick={() => reprintTicket(selected)}
                className="dax-btn-secondary flex-1 justify-center disabled:opacity-40"
                title={printerName ? 'Reimprimir vía agente local' : 'Configura una impresora en /printer-settings primero'}
              >
                {reprinting
                  ? <i className="fa-solid fa-spinner fa-spin" aria-hidden="true" />
                  : <><i className="fa-solid fa-print" aria-hidden="true" /> {printerName ? 'Reimprimir ticket' : 'Sin impresora configurada'}</>}
              </button>
              {sePuedeDevolver(selected) && (
                <button type="button" onClick={() => { setSel(null); setReturnSale(selected) }} className="dax-btn-danger flex-1 justify-center">
                  <i className="fa-solid fa-undo" aria-hidden="true" /> Registrar devolución
                </button>
              )}
            </>
          }
        >
          <div className="space-y-3 text-sm">
            {conSucursales && <div className="flex justify-between"><span className="text-dax-muted">Sucursal</span><span>{selected.branch_name ?? '—'}</span></div>}
            <div className="flex justify-between"><span className="text-dax-muted">Cliente</span><span>{selected.customer_name ?? 'Público general'}</span></div>
            <div className="flex justify-between"><span className="text-dax-muted">Fecha</span><span>{new Date(selected.created_at).toLocaleString('es-MX')}</span></div>
            <div className="flex justify-between"><span className="text-dax-muted">Estado</span>{badgeEstado(selected)}</div>
          </div>

          <div className="mt-4 border-t border-dax-border-dim pt-4">
            <p className="text-[10px] font-bold text-dax-muted uppercase tracking-widest mb-2">Artículos</p>
            {/* Sin envoltorio, la tabla arrastraba de lado todo el modal. */}
            <TablaDesplazable sangrado={false}>
              <table className="dax-table w-full text-xs">
                <thead><tr><th>Producto</th><th className="text-right">Cant.</th><th className="text-right">Precio</th><th className="text-right">Total</th></tr></thead>
                <tbody>
                  {selected.lines?.map((line, i) => (
                    <tr key={i}>
                      <td>{line.description ?? line.sku ?? '—'}</td>
                      <td className="text-right">{line.quantity}</td>
                      <td className="text-right">{formatCurrency(Number(line.unit_price))}</td>
                      <td className="text-right font-semibold">{formatCurrency(Number(line.total_line))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TablaDesplazable>
          </div>

          <div className="mt-4 border-t border-dax-border-dim pt-4 space-y-1 text-sm">
            <div className="flex justify-between text-dax-muted"><span>Subtotal</span><span>{formatCurrency(Number(selected.subtotal))}</span></div>
            {Number(selected.tax_amount) > 0 && <div className="flex justify-between text-dax-muted"><span>IVA</span><span>{formatCurrency(Number(selected.tax_amount))}</span></div>}
            <div className="flex justify-between font-black text-dax-text text-base pt-1"><span>Total</span><span>{formatCurrency(selected.total_amount)}</span></div>
            {Number(selected.card_surcharge_amount ?? 0) > 0 && (
              <>
                <div className="flex justify-between text-dax-muted">
                  <span>Comisión tarjeta {formatPct(selected.card_surcharge_pct)}%</span>
                  <span>{formatCurrency(Number(selected.card_surcharge_amount))}</span>
                </div>
                <div className="flex justify-between font-black text-dax-success text-base">
                  <span>Total cobrado</span>
                  <span>{formatCurrency(Number(selected.total_amount) + Number(selected.card_surcharge_amount))}</span>
                </div>
              </>
            )}
          </div>
        </Modal>
      )}
      {returnSale && (
        <ReturnModal
          initialSale={returnSale}
          onClose={() => setReturnSale(null)}
          onSuccess={() => { setReturnSale(null); load(rango, page, sucursal) }}
        />
      )}
      {ventaPorAutorizar && (
        <ReprintPinModal
          etiqueta={saleLabel(ventaPorAutorizar)}
          onCancel={() => setVentaPorAutorizar(null)}
          onSubmit={(pin) => reprintTicket(ventaPorAutorizar, pin)}
        />
      )}
    </div>
  )
}
```

- [ ] **Step 5: Baja de `HQSalesLog`, redirect en `App.tsx`, enlace del Inicio**

```bash
git rm frontend/src/pages/hq/HQSalesLog.tsx
```

En `frontend/src/App.tsx`:

1. Debajo de la línea 14 (`import { RequireRole, RutaPorRol } from './components/layout/RequireRole'`) añadir:

```tsx
import { RedirigirConQuery } from './components/layout/RedirigirConQuery'
```

2. Borrar la línea 29: `const HQSalesLog      = lazy(() => import('./pages/hq/HQSalesLog').then(m => ({ default: m.HQSalesLog })))`.

3. Sustituir la línea 279 (`<Route path="sales" element={<RutaPorRol url="/hq/sales">…HQSalesLog…`) por:

```tsx
            {/* Fase 3 del admin: Ventas, Devoluciones e Inventario son una sola pantalla en la URL corta; las viejas redirigen con su consulta. */}
            <Route path="sales" element={<RedirigirConQuery a="/sales" />} />
```

En `frontend/src/pages/hq/Inicio.tsx` línea 49, cambiar `completo: { existencias: '/hq/inventory', ventas: '/hq/sales' },` por
`completo: { existencias: '/hq/inventory', ventas: '/sales' },` (la existencia la cambia la Tarea 3).

En `frontend/src/pages/hq/__tests__/Inicio.test.tsx` línea 300, cambiar `.toBe('/hq/sales')` por `.toBe('/sales')`.

- [ ] **Step 6: Guardias**

`frontend/src/__tests__/coloresPorTokens.test.ts`:
- Línea 26: quitar `'pages/hq/HQSalesLog.tsx'` (la línea queda `'pages/hq/HQBranches.tsx', 'pages/hq/HQInventory.tsx', 'pages/hq/HQReturns.tsx',`).
- Línea 33: quitar `'pages/sales/SalesHistory.tsx'` (queda `'pages/sales/QuoteMaker.tsx', 'pages/sales/Quotes.tsx', 'pages/sales/Returns.tsx',`).
- Sustituir el bloque `LIMPIOS` (líneas 39-44) por:

```ts
/** Lo que las Fases 2 y 3 crearon o reescribieron: cero colores fijos, de ninguna paleta, y sin hex.
 *  `KpiCard.tsx` (components/ui) entra por aquí y no por CARPETAS: no se escanea toda `ui/`. */
const LIMPIOS = [
  'pages/hq/Inicio.tsx', 'pages/hq/InicioGraficas.tsx', 'pages/reports/Reportes.tsx', 'pages/reports/presetsReportes.ts',
  'components/reports/Heatmap.tsx', 'components/reports/ValorTiendaCard.tsx', 'components/ui/KpiCard.tsx',
  // Fase 3 (fusiones): las pantallas que sobreviven se reescribieron solo con tokens.
  'pages/sales/SalesHistory.tsx',
]
```

`frontend/src/__tests__/overlaysFueraDelKit.test.ts`: borrar la línea 51 `'/pages/sales/SalesHistory.tsx': 1,`.

`frontend/src/pages/__tests__/responsivoOla2.test.ts`: en `PAGINAS` (líneas 6-10) cambiar `'hq/HQSalesLog.tsx'` por `'sales/SalesHistory.tsx'`.

- [ ] **Step 7: Correr**

Run: `cd frontend && npx vitest run src/pages/sales src/components/layout src/pages/hq src/__tests__ src/pages/__tests__ --reporter=dot 2>&1 | tail -6 && npx tsc --noEmit -p tsconfig.json`
Expected: todo verde (SalesHistory 5, RedirigirConQuery 3, Inicio sin cambios de conteo, guardias verdes); tsc limpio.

Run: `git grep -n "HQSalesLog" -- 'frontend/src' ':!*.test.*'`
Expected: **exactamente una** línea, el comentario de cabecera de `frontend/src/pages/sales/SalesHistory.tsx` («Sustituye a `pages/hq/HQSalesLog.tsx`»). Cualquier `import` o `lazy()` que aparezca es un fallo. (Con pruebas incluidas aparece además el `describe` de `SalesHistory.test.tsx` y nada más.)

- [ ] **Step 8: Commit**

```bash
git add frontend/src/utils/rolesHq.ts frontend/src/hooks/useSucursalesVendibles.ts \
  frontend/src/components/layout/RedirigirConQuery.tsx frontend/src/components/layout/__tests__/RedirigirConQuery.test.tsx \
  frontend/src/pages/sales/SalesHistory.tsx frontend/src/pages/sales/__tests__/SalesHistory.test.tsx \
  frontend/src/App.tsx frontend/src/pages/hq/Inicio.tsx frontend/src/pages/hq/__tests__/Inicio.test.tsx \
  frontend/src/__tests__/coloresPorTokens.test.ts frontend/src/__tests__/overlaysFueraDelKit.test.ts \
  frontend/src/pages/__tests__/responsivoOla2.test.ts
git commit -m "feat(ventas): /sales absorbe HQSalesLog (selector de sucursal para HQ) y /hq/sales redirige con su consulta

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 2: Devoluciones — `Returns` absorbe `HQReturns` (sucursal y periodo)

**Files:**
- Rewrite: `frontend/src/pages/sales/Returns.tsx`
- Create: `frontend/src/pages/sales/__tests__/Returns.test.tsx`
- Delete: `frontend/src/pages/hq/HQReturns.tsx`
- Modify: `frontend/src/App.tsx` (lazy `HQReturns` y ruta `hq/returns`), `frontend/src/components/layout/Sidebar.tsx:17`, `frontend/src/pages/hq/Inicio.tsx:245`, `frontend/src/pages/hq/__tests__/Inicio.test.tsx:162`
- Modify: `frontend/src/components/layout/navConfig.ts:150-151` (`/returns` para ADMINISTRADOR y DUEÑO), `frontend/src/components/layout/navPerfilBasico.ts:27` (`/returns` oculto en básico), `frontend/src/components/layout/__tests__/navConfig.test.ts` (una prueba)
- Modify: `frontend/src/__tests__/coloresPorTokens.test.ts`, `frontend/src/__tests__/overlaysFueraDelKit.test.ts:50`, `frontend/src/pages/__tests__/responsivoOla2.test.ts:9`

**Interfaces:**
- Consumes: `esRolHq` (`utils/rolesHq.ts`), `useSucursalesVendibles` (`hooks/useSucursalesVendibles.ts`), `RedirigirConQuery` (Tarea 1); `PRESETS/rangoPreset/presetActivo/ClavePreset/Rango` (`pages/reports/presetsReportes.ts`); `returnsApi.list({ status?, branch_id?, start_date?, end_date? })`, `approve(id, force)`, `reject(id, reason?)`; `estadoDevolucion` (`utils/enumsEspanol`); `errorDetailText(detail, respaldo)` (`utils/errorDetail`); `confirm(options)` (`components/ui/ConfirmDialog`).
- Produces: `Returns` (export sin cambios: `CAJERO` → `ReturnsBranchView`; resto → bandeja). `ROLE_ROUTES.ADMINISTRADOR/DUEÑO` ya incluyen `/returns` y `OCULTAS_BASICO_HQ` lo esconde (la Tarea 5 lo conserva).

Decisiones: el periodo (default `30d`) acota **solo el Historial**; el gerente no tiene selector (no es HQ) pero sí columna «Sucursal», porque `/returns/` le devuelve toda la organización (`HQ_ROLES` de `metricas_ventas.py:35` lo incluye), igual que hoy; Pendientes se pide siempre sin fechas. El selector vive en las `acciones` de la cabecera (como en `HQReturns`) para seguir visible en ambas pestañas. Los estados se pintan con `estadoDevolucion` («Por aprobar», «Aprobada», «Rechazada»): la base mostraba el enum en inglés. El reembolso en efectivo alto se confirma con el `confirm()` de la app (como `HQReturns`), no con `window.confirm`.

- [ ] **Step 1: Prueba (falla contra la pantalla vieja)**

`frontend/src/pages/sales/__tests__/Returns.test.tsx`:

```tsx
// frontend/src/pages/sales/__tests__/Returns.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react'

const { list, approve, reject, getBranches } = vi.hoisted(() => ({ list: vi.fn(), approve: vi.fn(), reject: vi.fn(), getBranches: vi.fn() }))
vi.mock('../../../api/returns', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/returns')>()),
  returnsApi: { list, approve, reject },
}))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches } }))
vi.mock('../../../components/branch/ReturnsBranchView', () => ({ ReturnsBranchView: () => <div data-testid="asistente-cajera" /> }))
vi.mock('../../../components/ui/ConfirmDialog', () => ({ confirm: vi.fn(async () => true) }))

import { Returns } from '../Returns'
import { useAuthStore } from '../../../store/authStore'
import { rangoPreset } from '../../reports/presetsReportes'

const r30 = rangoPreset('30d')
const hoy = rangoPreset('hoy')
const DEV = (id: string, status: 'PENDING' | 'APPROVED') => ({
  id, sale_id: 's1', reason: 'Talla equivocada', total_refunded: 300, refund_method: 'CASH', status,
  branch_id: 1, branch: { id: 1, name: 'Roma' }, user: { id: 2, username: 'mirna', full_name: 'Mirna' }, supervisor: null,
  created_at: '2026-10-20T15:00:00Z',
  items: [{ id: 'i1', return_id: id, variant_id: 'v1', quantity: 1, refund_amount: 300, is_inventory_reentry: true, variant: { id: 'v1', sku: 'BLU', product_name: 'Blusa' } }],
})
const SUC = (id: number, name: string, can_sell = true) =>
  ({ id, name, branch_type: 'STORE', address: null, phone: null, is_headquarters: false, is_active: true, can_sell })
const usuario = (role: string, branch_id: number | null = null) =>
  useAuthStore.setState({ user: { id: 1, username: 'u', role, branch_id, platform_role: 'NONE' } } as never)
const pintar = () => render(<MemoryRouter><Returns /></MemoryRouter>)
const llamadasPendientes = () => list.mock.calls.filter(([p]) => (p as { status?: string } | undefined)?.status === 'PENDING')

beforeEach(() => {
  list.mockReset().mockImplementation(async (p?: { status?: string }) =>
    (p?.status === 'PENDING' ? [DEV('dev-000001', 'PENDING')] : [DEV('dev-000001', 'PENDING'), DEV('dev-000002', 'APPROVED')]))
  approve.mockReset().mockResolvedValue(DEV('dev-000001', 'APPROVED'))
  reject.mockReset()
  getBranches.mockReset().mockResolvedValue([SUC(1, 'Roma'), SUC(2, 'Condesa')])
})
afterEach(cleanup)

describe('Devoluciones (/returns, fusión de HQReturns)', () => {
  it('la cajera ve el asistente de sucursal, no la bandeja', () => {
    usuario('CAJERO', 1)
    pintar()
    expect(screen.getByTestId('asistente-cajera')).toBeTruthy()
    expect(list).not.toHaveBeenCalled()
  })

  it('el gerente ve la bandeja sin selector pero con columna Sucursal (recibe toda la org): pendientes sin fechas, historial en 30 días, estados en español, y aprueba', async () => {
    usuario('GERENTE', 1)
    pintar()
    await screen.findByText('DEV-000001')
    expect(getBranches).not.toHaveBeenCalled()
    expect(list).toHaveBeenCalledWith({ status: 'PENDING' })
    expect(list).toHaveBeenCalledWith({ start_date: r30.inicio, end_date: r30.fin })
    expect(screen.queryByLabelText('Sucursal')).toBeNull()
    expect(screen.getAllByRole('columnheader').map((th) => th.textContent)).toContain('Sucursal')
    expect(screen.getByText('Roma')).toBeTruthy()
    expect(screen.getByText('Por aprobar')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Ver detalle de DEV-000001'))
    const dialogo = await screen.findByRole('dialog')
    fireEvent.click(within(dialogo).getByRole('button', { name: /Aprobar/ }))
    await waitFor(() => expect(approve).toHaveBeenCalledWith('dev-000001', false))
  })

  it('la administradora con dos sucursales que venden ve el selector y la columna; al elegir, pendientes e historial llevan branch_id', async () => {
    usuario('ADMINISTRADOR')
    pintar()
    await screen.findByText('DEV-000001')
    const selector = await screen.findByLabelText('Sucursal')
    expect(screen.getAllByRole('columnheader').map((th) => th.textContent)).toContain('Sucursal')
    fireEvent.change(selector, { target: { value: '2' } })
    await waitFor(() => expect(list).toHaveBeenCalledWith({ branch_id: 2, status: 'PENDING' }))
    expect(list).toHaveBeenCalledWith({ branch_id: 2, start_date: r30.inicio, end_date: r30.fin })
  })

  it('en Historial, el preset Hoy acota solo el historial; los pendientes se siguen pidiendo completos', async () => {
    usuario('GERENTE', 1)
    pintar()
    await screen.findByText('DEV-000001')
    fireEvent.click(screen.getByRole('button', { name: 'Historial' }))
    await screen.findByText('DEV-000002')
    fireEvent.click(screen.getByRole('button', { name: 'Hoy' }))
    await waitFor(() => expect(list).toHaveBeenLastCalledWith({ start_date: hoy.inicio, end_date: hoy.fin }))
    expect(llamadasPendientes().length).toBeGreaterThanOrEqual(2)
    for (const [p] of llamadasPendientes()) expect(p).not.toHaveProperty('start_date')
  })
})
```

Run: `cd frontend && npx vitest run src/pages/sales/__tests__/Returns.test.tsx --reporter=dot`
Expected: FAIL (sin selector, `list` sin fechas, «PENDING» en vez de «Por aprobar», `window.confirm` en vez de `confirm`).

- [ ] **Step 2: Reescribir `Returns.tsx`**

```tsx
// frontend/src/pages/sales/Returns.tsx
import { useEffect, useState, useCallback } from 'react'
import { ReturnsBranchView } from '../../components/branch/ReturnsBranchView'
import {
  returnsApi, type ReturnDocument, type ReturnStatus,
  returnLabel, returnRequestedBy, returnApprovedBy, returnBranchName,
} from '../../api/returns'
import { useAuthStore } from '../../store/authStore'
import { toast } from '../../store/toastStore'
import { confirm } from '../../components/ui/ConfirmDialog'
import { DaxCard } from '../../components/ui/DaxCard'
import { Modal } from '../../components/ui/Modal'
import { TablaDesplazable } from '../../components/ui/TablaDesplazable'
import { Badge } from '../../components/ui/Badge'
import { Spinner } from '../../components/ui/Spinner'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { BarraFiltros, ParFechas } from '../../components/ui/BarraFiltros'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { useSucursalesVendibles } from '../../hooks/useSucursalesVendibles'
import { esRolHq } from '../../utils/rolesHq'
import { formatCurrency } from '../../utils/currency'
import { errorDetailText } from '../../utils/errorDetail'
import { estadoDevolucion } from '../../utils/enumsEspanol'
import { PRESETS, presetActivo, rangoPreset, type ClavePreset, type Rango } from '../reports/presetsReportes'

/**
 * Devoluciones (`/returns`). Una sola pantalla (Fase 3 del admin, spec
 * 2026-10-23 §4.1): la cajera usa el asistente de sucursal; gerente,
 * administrador y dueño ven la bandeja (pendientes e historial). Los roles de
 * oficina eligen sucursal cuando hay más de una que vende. Sustituye a
 * `pages/hq/HQReturns.tsx`. Solo tokens `dax-*` (coloresPorTokens, LIMPIOS).
 */

const CAN_APPROVE = ['ADMINISTRADOR', 'DUEÑO', 'GERENTE']
type Pestana = 'pending' | 'history'

const fechaCorta = (iso: string) => new Date(iso).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })
const statusVariant = (s: ReturnStatus): 'green' | 'red' | 'yellow' =>
  (s === 'APPROVED' ? 'green' : s === 'REJECTED' ? 'red' : 'yellow')
const badgeEstado = (s: ReturnStatus) => <Badge variant={statusVariant(s)}>{estadoDevolucion(s)}</Badge>
// Saca el `detail` de FastAPI (409/422 traen mensajes accionables) o cae al respaldo.
const detalle = (err: unknown, respaldo: string) =>
  errorDetailText((err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail, respaldo)

export function Returns() {
  const role = useAuthStore((s) => s.user?.role)
  if (role === 'CAJERO') return <ReturnsBranchView />
  return <ReturnsAdminView />
}

// Separado para no romper Rules of Hooks: el return condicional de arriba
// no puede convivir con hooks en el mismo componente.
function ReturnsAdminView() {
  const role = useAuthStore((s) => s.user?.role)
  const canApprove = CAN_APPROVE.includes(role ?? '')
  const esHq = esRolHq(role)
  const esTelefono = useEsTelefono()
  const sucursales = useSucursalesVendibles(esHq)
  const conSucursales = esHq && sucursales.length > 1
  // El gerente no elige sucursal, pero `/returns/` le devuelve toda la organización:
  // la columna "Sucursal" le dice de dónde viene cada fila.
  const muestraSucursal = conSucursales || role === 'GERENTE'
  const [sucursal, setSucursal] = useState<number | ''>('')

  const [tab, setTab] = useState<Pestana>('pending')
  // El periodo acota el historial; los pendientes se piden siempre completos: una
  // devolución de hace dos meses sigue por aprobar aunque el rango no la cubra.
  const [rango, setRango] = useState<Rango>(() => rangoPreset('30d'))
  const [desde, setDesde] = useState(rango.inicio)
  const [hasta, setHasta] = useState(rango.fin)
  const [presetElegido, setPresetElegido] = useState<ClavePreset | null>('30d')
  const [pending, setPending] = useState<ReturnDocument[]>([])
  const [history, setHistory] = useState<ReturnDocument[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<ReturnDocument | null>(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [rejectingId, setRejectingId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  const loadData = useCallback(async (bid: number | '', r: Rango) => {
    setLoading(true)
    try {
      // `branch_id` solo cuando un rol de oficina eligió sucursal. Sin él, `/returns/`
      // (`resolver_ambito`; HQ_ROLES incluye GERENTE) da toda la organización a admin,
      // dueño y gerente —como hoy— y a la cajera la suya.
      const ambito = bid !== '' ? { branch_id: bid } : {}
      const [pendientes, historial] = await Promise.all([
        returnsApi.list({ ...ambito, status: 'PENDING' }),
        returnsApi.list({ ...ambito, start_date: r.inicio, end_date: r.fin }),
      ])
      setPending(pendientes)
      setHistory(historial)
    } catch {
      setPending([]); setHistory([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData(sucursal, rango) }, [loadData, sucursal, rango])

  const aplicar = (r: Rango, clave: ClavePreset | null) => {
    setRango(r); setDesde(r.inicio); setHasta(r.fin); setPresetElegido(clave)
  }
  const aplicarFechas = () => {
    if (desde > hasta) { toast.error('La fecha inicial no puede ser mayor que la final.'); return }
    aplicar({ inicio: desde, fin: hasta }, null)
  }
  // En el día 1 «Este mes» y «Hoy» coinciden: manda el que se pulsó.
  const activo: ClavePreset | null = presetActivo(rango) && presetElegido ? presetElegido : presetActivo(rango)

  const handleApprove = async (id: string, force = false) => {
    setActionLoading(true)
    try {
      await returnsApi.approve(id, force)
      await loadData(sucursal, rango)
      setSelected(null)
      toast.success('Devolución aprobada')
    } catch (err) {
      const texto = detalle(err, 'Error al aprobar la devolución')
      // R-3: el backend rechaza efectivo > $10,000 sin force=true. Se confirma con el
      // diálogo de la app (Esc cancela, el foco arranca en Cancelar), no con el del navegador.
      if (!force && /EFECTIVO de monto alto|force=True/i.test(texto)) {
        const ok = await confirm({
          title: 'Confirmar reembolso en efectivo',
          message: texto,
          confirmText: 'Sí, reembolsar en efectivo',
          cancelText: 'Cancelar',
          variant: 'danger',
        })
        if (ok) {
          setActionLoading(false)
          return handleApprove(id, true)
        }
      } else {
        toast.error(texto)
      }
    } finally { setActionLoading(false) }
  }

  const handleReject = async (id: string, reason?: string) => {
    setActionLoading(true)
    try {
      await returnsApi.reject(id, reason)
      await loadData(sucursal, rango)
      setSelected(null)
      setRejectingId(null)
      setRejectReason('')
      toast.success('Devolución rechazada')
    } catch (err) {
      toast.error(detalle(err, 'Error al rechazar la devolución'))
    } finally { setActionLoading(false) }
  }

  const items = tab === 'pending' ? pending : history
  const textoVacio = tab === 'pending' ? 'No hay devoluciones pendientes' : 'Sin devoluciones en este periodo'

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={
          <div className="flex items-center gap-3">
            <i className="fa-solid fa-undo text-dax-accent-text text-xl" aria-hidden="true" />
            <h1 className="text-2xl font-black text-dax-text">Devoluciones</h1>
          </div>
        }
        acciones={
          <>
            {conSucursales && (
              <select
                aria-label="Sucursal"
                value={sucursal}
                onChange={(e) => setSucursal(e.target.value ? Number(e.target.value) : '')}
                className="dax-input text-xs max-w-[180px]"
              >
                <option value="">Todas las sucursales</option>
                {sucursales.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            )}
            <button type="button" onClick={() => loadData(sucursal, rango)} className="dax-btn-secondary text-xs">
              <i className="fa-solid fa-rotate-right" aria-hidden="true" /> Actualizar
            </button>
          </>
        }
      />

      {/* Pestañas */}
      <div className="flex gap-1 w-fit" role="group" aria-label="Bandeja">
        {(['pending', 'history'] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            aria-pressed={tab === t}
            className={`${tab === t ? 'dax-btn-primary' : 'dax-btn-secondary'} text-sm max-md:min-h-[44px]`}
          >
            {t === 'pending' ? 'Pendientes' : 'Historial'}
            {t === 'pending' && pending.length > 0 && (
              <span className="ml-1.5 rounded-full bg-dax-danger text-dax-on-accent text-[10px] font-black px-1.5 py-0.5">{pending.length}</span>
            )}
          </button>
        ))}
      </div>

      {tab === 'history' && (
        <BarraFiltros
          className="!items-center"
          accion={<button type="button" onClick={aplicarFechas} className="dax-btn-primary text-xs">Aplicar</button>}
        >
          <div className="flex flex-wrap gap-1" role="group" aria-label="Periodo">
            {PRESETS.map((p) => (
              <button
                key={p.clave}
                type="button"
                onClick={() => aplicar(rangoPreset(p.clave), p.clave)}
                aria-pressed={activo === p.clave}
                className={`${activo === p.clave ? 'dax-btn-primary' : 'dax-btn-secondary'} text-xs max-sm:min-h-[44px]`}
              >
                {p.etiqueta}
              </button>
            ))}
          </div>
          <ParFechas>
            <input type="date" aria-label="Desde" value={desde} onChange={(e) => setDesde(e.target.value)} className="dax-input w-36 text-xs" />
            <input type="date" aria-label="Hasta" value={hasta} onChange={(e) => setHasta(e.target.value)} className="dax-input w-36 text-xs" />
          </ParFechas>
        </BarraFiltros>
      )}

      {esTelefono ? (
        <ListaTarjetas cargando={loading} vacio={items.length === 0} textoVacio={textoVacio}>
          {items.map((r) => (
            <TarjetaFila
              key={r.id}
              titulo={returnLabel(r)}
              subtitulo={[fechaCorta(r.created_at), muestraSucursal ? (returnBranchName(r) ?? '—') : null, returnRequestedBy(r)].filter(Boolean).join(' · ')}
              importe={<span className="text-dax-danger">{formatCurrency(r.total_refunded)}</span>}
              estado={badgeEstado(r.status)}
              datos={[{ etiqueta: 'Motivo', valor: r.reason }]}
              onClick={() => setSelected(r)}
              acciones={
                <button type="button" onClick={() => setSelected(r)} className="dax-btn-secondary text-xs">
                  <i className="fa-solid fa-eye" aria-hidden="true" /> Ver detalle
                </button>
              }
            />
          ))}
        </ListaTarjetas>
      ) : (
        <DaxCard padding={false}>
          {loading ? <Spinner text="Cargando..." /> : items.length === 0 ? (
            <div className="p-12 text-center text-dax-faint">{textoVacio}</div>
          ) : (
            <TablaDesplazable sangrado={false}>
              <table className="dax-table w-full">
                <thead>
                  <tr>
                    <th>Ticket</th>
                    {muestraSucursal && <th>Sucursal</th>}
                    <th>Solicitó</th>
                    <th>Fecha</th>
                    <th>Motivo</th>
                    <th className="text-right">Total</th>
                    <th>Estado</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((r) => (
                    <tr key={r.id}>
                      <td className="font-mono text-dax-accent-text text-xs">{returnLabel(r)}</td>
                      {muestraSucursal && <td className="text-xs text-dax-muted">{returnBranchName(r) ?? '—'}</td>}
                      <td className="text-sm">{returnRequestedBy(r)}</td>
                      <td className="text-xs text-dax-muted">{fechaCorta(r.created_at)}</td>
                      <td className="text-xs max-w-[160px] truncate">{r.reason}</td>
                      <td className="text-right font-semibold text-dax-danger">{formatCurrency(r.total_refunded)}</td>
                      <td>{badgeEstado(r.status)}</td>
                      <td>
                        <button
                          type="button"
                          onClick={() => setSelected(r)}
                          className="dax-btn-icon text-dax-muted hover:text-dax-text text-xs"
                          aria-label={`Ver detalle de ${returnLabel(r)}`}
                        >
                          <i className="fa-solid fa-eye" aria-hidden="true" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TablaDesplazable>
          )}
        </DaxCard>
      )}

      {/* Detalle: Modal del kit con Aprobar/Rechazar en el pie. */}
      {selected && (
        <Modal
          open
          onClose={() => setSelected(null)}
          size="lg"
          title="Detalle de devolución"
          footer={canApprove && selected.status === 'PENDING' ? (
            <>
              <button type="button" onClick={() => handleApprove(selected.id)} disabled={actionLoading} className="dax-btn-primary flex-1 justify-center">
                {actionLoading ? <i className="fa-solid fa-spinner fa-spin" aria-hidden="true" /> : <><i className="fa-solid fa-check" aria-hidden="true" /> Aprobar</>}
              </button>
              <button type="button" onClick={() => { setRejectingId(selected.id); setRejectReason('') }} disabled={actionLoading} className="dax-btn-danger flex-1 justify-center">
                <i className="fa-solid fa-xmark" aria-hidden="true" /> Rechazar
              </button>
            </>
          ) : undefined}
        >
          <div className="space-y-2 text-sm mb-4">
            <div className="flex justify-between"><span className="text-dax-muted">Ticket</span><span className="font-mono text-dax-accent-text">{returnLabel(selected)}</span></div>
            {muestraSucursal && <div className="flex justify-between"><span className="text-dax-muted">Sucursal</span><span>{returnBranchName(selected) ?? '—'}</span></div>}
            <div className="flex justify-between"><span className="text-dax-muted">Solicitó</span><span>{returnRequestedBy(selected)}</span></div>
            <div className="flex justify-between"><span className="text-dax-muted">Motivo</span><span className="text-right max-w-[60%]">{selected.reason}</span></div>
            <div className="flex justify-between"><span className="text-dax-muted">Estado</span>{badgeEstado(selected.status)}</div>
            {selected.supervisor && <div className="flex justify-between"><span className="text-dax-muted">Aprobó</span><span>{returnApprovedBy(selected)}</span></div>}
          </div>

          {selected.items?.length > 0 && (
            <div className="border-t border-dax-border-dim pt-4 mb-4">
              <p className="text-[10px] font-bold text-dax-muted uppercase tracking-widest mb-2">Artículos</p>
              {/* Sin envoltorio, la tabla arrastraba de lado todo el modal. */}
              <TablaDesplazable sangrado={false}>
                <table className="dax-table w-full text-xs">
                  <thead><tr><th>Producto</th><th className="text-right">Cant.</th><th className="text-right">Reembolso</th><th>Stock</th></tr></thead>
                  <tbody>
                    {selected.items.map((item, i) => (
                      <tr key={i}>
                        <td>{item.variant?.product_name ?? item.variant?.sku ?? '—'}</td>
                        <td className="text-right">{item.quantity}</td>
                        <td className="text-right text-dax-danger">{formatCurrency(Number(item.refund_amount))}</td>
                        <td><Badge variant={item.is_inventory_reentry ? 'green' : 'red'}>{item.is_inventory_reentry ? 'Regresa' : 'Merma'}</Badge></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TablaDesplazable>
            </div>
          )}

          <div className="flex justify-between font-black text-dax-text border-t border-dax-border-dim pt-3">
            <span>Total reembolso</span><span className="text-dax-danger">{formatCurrency(selected.total_refunded)}</span>
          </div>
        </Modal>
      )}

      {/* Rechazo con motivo. */}
      {rejectingId && (
        <Modal
          open
          onClose={() => setRejectingId(null)}
          size="sm"
          title={<span><i className="fa-solid fa-circle-exclamation mr-2 text-dax-danger" aria-hidden="true" />Rechazar devolución</span>}
          footer={
            <>
              <button type="button" onClick={() => setRejectingId(null)} className="dax-btn-secondary flex-1" disabled={actionLoading}>
                Cancelar
              </button>
              <button
                type="button"
                onClick={() => handleReject(rejectingId, rejectReason.trim() || undefined)}
                className="dax-btn-danger flex-1 justify-center"
                disabled={actionLoading}
              >
                {actionLoading ? <i className="fa-solid fa-spinner fa-spin" aria-hidden="true" /> : <><i className="fa-solid fa-xmark" aria-hidden="true" /> Confirmar rechazo</>}
              </button>
            </>
          }
        >
          <label htmlFor="motivo-rechazo" className="text-[10px] font-bold uppercase tracking-wider block mb-1 text-dax-muted">
            Motivo (opcional)
          </label>
          <textarea
            id="motivo-rechazo"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            className="dax-input w-full"
            rows={3}
            placeholder="Ej: Producto fuera de plazo de devolución, ticket duplicado..."
            autoFocus
          />
        </Modal>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Baja de `HQReturns`, redirect, referencias**

```bash
git rm frontend/src/pages/hq/HQReturns.tsx
```

`frontend/src/App.tsx`:
1. Borrar `const HQReturns       = lazy(() => import('./pages/hq/HQReturns').then(m => ({ default: m.HQReturns })))`.
2. Sustituir `<Route path="returns" element={<RutaPorRol url="/hq/returns"><Suspense fallback={<PageLoader />}><HQReturns /></Suspense></RutaPorRol>} />` (dentro de `<Route path="hq">`) por:

```tsx
            <Route path="returns" element={<RedirigirConQuery a="/returns" />} />
```

`frontend/src/components/layout/Sidebar.tsx` línea 17: `const RETURNS_URLS = new Set(['/returns', '/hq/returns'])` → `const RETURNS_URLS = new Set(['/returns'])`.

`frontend/src/pages/hq/Inicio.tsx` línea 245: `<Link to="/hq/returns"` → `<Link to="/returns"`.

`frontend/src/pages/hq/__tests__/Inicio.test.tsx` línea 162: `.toBe('/hq/returns')` → `.toBe('/returns')`.

**Sin bloqueo entre esta tarea y la 5:** `/returns` está bajo `RutaPorRol url="/returns"` y hoy ADMINISTRADOR/DUEÑO no lo tienen en `ROLE_ROUTES`; con `/hq/returns` redirigiendo, se quedarían fuera hasta la Tarea 5. Por eso aquí:
- en `frontend/src/components/layout/navConfig.ts`, en `ROLE_ROUTES.ADMINISTRADOR` y `ROLE_ROUTES.DUEÑO`, insertar `'/returns',` justo después de `'/sales',` (quedan `['/sales','/returns','/products',…]` y `['/pos','/sales','/returns','/products',…]`);
- en `frontend/src/components/layout/navPerfilBasico.ts`, en `OCULTAS_BASICO_HQ`, cambiar la línea `'/hq/sales', '/hq/returns',          // Mis ventas (/sales) es global…` por `'/hq/sales', '/hq/returns', '/returns',   // Ventas (/sales) es global para la dueña y devuelve por ticket` (spec §4.2: Devoluciones sigue oculta en básico; sin esto la prueba «administradora: exactamente ocho entradas» pasaría a nueve).

En `frontend/src/components/layout/__tests__/navConfig.test.ts`, dentro de `describe('las guardas de ruta', …)`, añadir:

```ts
  it('Fase 3: el admin y el dueño abren /returns (antes solo /hq/returns)', () => {
    expect(rolesConAcceso('/returns')).toEqual(expect.arrayContaining(['ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO']))
  })
```

La Tarea 5 conserva estas tres ediciones.

- [ ] **Step 4: Guardias**

`frontend/src/__tests__/coloresPorTokens.test.ts`: quitar `'pages/hq/HQReturns.tsx'` (línea 26) y `'pages/sales/Returns.tsx'` (línea 33) de `PENDIENTES`; en `LIMPIOS`, la línea de la Fase 3 queda `'pages/sales/SalesHistory.tsx', 'pages/sales/Returns.tsx',`.

`frontend/src/__tests__/overlaysFueraDelKit.test.ts`: borrar `'/pages/sales/Returns.tsx': 2,`.

`frontend/src/pages/__tests__/responsivoOla2.test.ts`: en `PAGINAS` cambiar `'hq/HQReturns.tsx'` por `'sales/Returns.tsx'`.

- [ ] **Step 5: Correr**

Run: `cd frontend && npx vitest run src/pages/sales src/pages/hq src/__tests__ src/pages/__tests__ src/components/layout --reporter=dot 2>&1 | tail -6 && npx tsc --noEmit -p tsconfig.json`
Expected: todo verde; tsc limpio.

Run: `git grep -n "HQReturns" -- 'frontend/src' ':!*.test.*'`
Expected: **exactamente una** línea, el comentario de cabecera de `pages/sales/Returns.tsx` («Sustituye a `pages/hq/HQReturns.tsx`»).

Run: `git grep -n "/hq/returns" -- 'frontend/src' ':!*.test.*'`
Expected: exactamente dos archivos: `components/layout/navConfig.ts` (ítem `/hq/returns` de `ALL_NAV`, su grupo y `ROLE_ROUTES`, que limpia la Tarea 5) y `components/layout/navPerfilBasico.ts` (la línea `'/hq/sales', '/hq/returns', '/returns'`, que limpia la Tarea 5). Ni `App.tsx` ni `Sidebar.tsx` ni `Inicio.tsx` deben aparecer.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/sales/Returns.tsx frontend/src/pages/sales/__tests__/Returns.test.tsx \
  frontend/src/components/layout/navConfig.ts frontend/src/components/layout/navPerfilBasico.ts \
  frontend/src/components/layout/__tests__/navConfig.test.ts \
  frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx frontend/src/pages/hq/Inicio.tsx \
  frontend/src/pages/hq/__tests__/Inicio.test.tsx frontend/src/__tests__/coloresPorTokens.test.ts \
  frontend/src/__tests__/overlaysFueraDelKit.test.ts frontend/src/pages/__tests__/responsivoOla2.test.ts
git commit -m "feat(devoluciones): /returns absorbe HQReturns (sucursal y periodo del historial) y /hq/returns redirige

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 3: Inventario — `Inventory` absorbe `HQInventory` (costo, importes, «Solo sin costo»)

**Files:**
- Rewrite: `frontend/src/pages/inventory/Inventory.tsx`
- Move + rewrite: `frontend/src/pages/hq/__tests__/HQInventory.test.tsx` → `frontend/src/pages/inventory/__tests__/Inventory.test.tsx`
- Delete: `frontend/src/pages/hq/HQInventory.tsx`
- Modify: `frontend/src/App.tsx` (lazy `HQInventory` y ruta `hq/inventory`), `frontend/src/pages/hq/Inicio.tsx:45-52, 201`, `frontend/src/pages/hq/__tests__/Inicio.test.tsx:161, 284-301`
- Modify: `frontend/src/__tests__/coloresPorTokens.test.ts`, `frontend/src/__tests__/overlaysFueraDelKit.test.ts:46`, `frontend/src/pages/__tests__/responsivoOla2.test.ts:8, 32`

**Interfaces:**
- Consumes: `esRolHq`, `RedirigirConQuery` (Tarea 1); `expandVariantRows`, `initialInventoryQuery`, `InventoryRow` (`pages/inventory/variantRows.ts`); `productsApi.search(q, skip, limit)`, `inventoryApi.getKardex(variantId)`, `inventoryApi.createAdjustment`, `organizationApi.getBranches` (todas las sucursales, para el ajuste, como hoy); `tipoMovimiento` (`utils/enumsEspanol`); `errorDetailText`.
- Produces: `Inventory` (export sin cambios). La ruta `/inventory` sigue sin `RutaPorRol` (CLAUDE: cajera y gerente llegan desde «Ajustar» del editor de variantes).

Decisiones: la base es el cuerpo de `HQInventory` (Modal del kit, `tipoMovimiento`) más la columna «Por» (`user_name`) que solo tenía `Inventory`. `veCosto = esRolHq(role)`: costo, importe a costo y la casilla «Solo sin costo» solo para HQ (sin costo la casilla no tiene sentido). Título «Inventario», icono `fa-boxes`.

- [ ] **Step 1: Mover la prueba y ampliarla (falla contra la pantalla vieja)**

```bash
git mv frontend/src/pages/hq/__tests__/HQInventory.test.tsx frontend/src/pages/inventory/__tests__/Inventory.test.tsx
```

Sustituir su contenido por:

```tsx
// frontend/src/pages/inventory/__tests__/Inventory.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, within, waitFor } from '@testing-library/react'

const { search, getKardex, createAdjustment, getBranches } = vi.hoisted(() => ({
  search: vi.fn(), getKardex: vi.fn(), createAdjustment: vi.fn(), getBranches: vi.fn(),
}))
vi.mock('../../../api/products', () => ({ productsApi: { search } }))
vi.mock('../../../api/inventory', () => ({ inventoryApi: { getKardex, createAdjustment } }))
vi.mock('../../../api/organization', () => ({ organizationApi: { getBranches } }))

import { Inventory } from '../Inventory'
import { useAuthStore } from '../../../store/authStore'

const PRODUCTOS = [
  { id: 'p1', name: 'Blusa', sku: 'BLU', price: 100, cost: 40, stock_total: 3, is_active: true,
    variants: [{ id: 'v1', product_id: 'p1', sku: 'BLU', price: 100, cost: 40, stock_total: 3, variant_name: 'Estándar' }] },
  { id: 'p2', name: 'Falda', sku: 'FAL', price: 200, cost: 0, stock_total: 2, is_active: true,
    variants: [{ id: 'v2', product_id: 'p2', sku: 'FAL', price: 200, cost: 0, stock_total: 2, variant_name: 'Estándar' }] },
]
const MOVIMIENTO = { id: 1, movement_type: 'ADJUSTMENT_IN', qty_change: 2, qty_after: 3, reference: 'AJ-1', created_at: '2026-10-20T15:00:00Z', user_name: 'Mirna' }
const usuario = (role: string) => useAuthStore.setState({ user: { id: 1, username: 'u', role, branch_id: 1, platform_role: 'NONE' } } as never)
const pintar = (ruta = '/inventory') => render(<MemoryRouter initialEntries={[ruta]}><Inventory /></MemoryRouter>)
const buscar = () => fireEvent.change(screen.getByPlaceholderText(/Buscar producto/), { target: { value: 'a' } })
const cabeceras = () => screen.getAllByRole('columnheader').map((th) => th.textContent)

beforeEach(() => {
  usuario('ADMINISTRADOR')
  search.mockReset().mockResolvedValue({ items: PRODUCTOS, total: 2, page: 0, pages: 1 })
  getKardex.mockReset().mockResolvedValue([])
  getBranches.mockReset().mockResolvedValue([{ id: 1, name: 'Roma', branch_type: 'STORE', is_active: true }])
})
afterEach(cleanup)

describe('Inventario (/inventory, fusión de Existencias)', () => {
  it('la administradora ve costo, importe a venta y a costo, y los totales de lo listado', async () => {
    pintar(); buscar()
    await screen.findByText('Blusa')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Inventario')
    expect(cabeceras()).toEqual(['SKU', 'Producto', 'Precio', 'Costo', 'Stock', 'Importe venta', 'Importe costo', ''])
    const tot = screen.getByTestId('totales').textContent
    expect(tot).toContain('5')          // 3 + 2 piezas
    expect(tot).toContain('$700.00')    // 300 + 400 a venta
    expect(tot).toContain('$120.00')    // 120 + 0 a costo
    expect(screen.getByText('sin costo')).toBeTruthy()
  })

  it('"Solo sin costo" deja los renglones con costo nulo o cero', async () => {
    pintar(); buscar()
    await screen.findByText('Blusa')
    fireEvent.click(screen.getByLabelText('Solo sin costo'))
    expect(screen.queryByText('Blusa')).toBeNull()
    expect(screen.getByText('Falda')).toBeTruthy()
    expect(screen.getByTestId('totales').textContent).toContain('$400.00')
  })

  it('el gerente no ve costos ni la casilla "Solo sin costo", pero sí kardex y ajuste', async () => {
    usuario('GERENTE')
    pintar(); buscar()
    await screen.findByText('Blusa')
    expect(cabeceras()).toEqual(['SKU', 'Producto', 'Precio', 'Stock', 'Importe venta', ''])
    expect(screen.queryByLabelText('Solo sin costo')).toBeNull()
    fireEvent.click(screen.getAllByText('Kardex')[0])
    expect(await screen.findByText('Ajustar')).toBeTruthy()
  })

  it('la cajera tampoco ve costos (misma regla que la valuación)', async () => {
    usuario('CAJERO')
    pintar(); buscar()
    await screen.findByText('Blusa')
    expect(cabeceras()).toEqual(['SKU', 'Producto', 'Precio', 'Stock', 'Importe venta', ''])
  })

  it('el ajuste abre el Modal del kit (role dialog) desde el kardex', async () => {
    pintar(); buscar()
    await screen.findByText('Blusa')
    fireEvent.click(screen.getAllByText('Kardex')[0])
    fireEvent.click(await screen.findByText('Ajustar'))
    const dialogo = await screen.findByRole('dialog')
    expect(within(dialogo).getByText('Ajuste de inventario')).toBeTruthy()
    expect(within(dialogo).getByLabelText('Cerrar')).toBeTruthy()
  })

  it('?q=&variant= siembra la búsqueda y abre el kardex de esa talla, con la columna "Por"', async () => {
    getKardex.mockResolvedValue([MOVIMIENTO])
    pintar('/inventory?q=BLU&variant=v1')
    await waitFor(() => expect(search).toHaveBeenCalledWith('BLU', 0, 30))
    await waitFor(() => expect(getKardex).toHaveBeenCalledWith('v1'))
    expect(await screen.findByText('Mirna')).toBeTruthy()
    expect(screen.getByText('Ajuste (+)')).toBeTruthy()
  })
})
```

Run: `cd frontend && npx vitest run src/pages/inventory/__tests__/Inventory.test.tsx --reporter=dot`
Expected: FAIL (la pantalla vieja no tiene costos ni totales; el kardex no traduce el tipo).

- [ ] **Step 2: Reescribir `Inventory.tsx`**

```tsx
// frontend/src/pages/inventory/Inventory.tsx
import { useState, useCallback, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { productsApi } from '../../api/products'
import { inventoryApi } from '../../api/inventory'
import { organizationApi, type Branch } from '../../api/organization'
import { useAuthStore } from '../../store/authStore'
import { DaxCard } from '../../components/ui/DaxCard'
import { Modal } from '../../components/ui/Modal'
import { TablaDesplazable } from '../../components/ui/TablaDesplazable'
import { Spinner } from '../../components/ui/Spinner'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
import { toast } from '../../store/toastStore'
import { errorDetailText } from '../../utils/errorDetail'
import { tipoMovimiento } from '../../utils/enumsEspanol'
import { esRolHq } from '../../utils/rolesHq'
import type { Product } from '../../types/products'
import { formatCurrency } from '../../utils/currency'
import { expandVariantRows, initialInventoryQuery, type InventoryRow } from './variantRows'

/**
 * Inventario (`/inventory`): buscar → un renglón por variante con precio,
 * existencia e importe a venta; kardex y ajuste por sucursal. Para los roles
 * de oficina (Fase 3 del admin, spec 2026-10-23 §4.1) suma costo, importe a
 * costo, totales y la casilla "Solo sin costo" que vivían en `hq/HQInventory`
 * (borrada). Acepta `?q=&variant=` (el "Ajustar" del editor de variantes y los
 * enlaces del Inicio). Solo tokens `dax-*` (coloresPorTokens, LIMPIOS).
 */

const sinCosto = (r: InventoryRow) => !(Number(r.variant.cost) > 0)
const fechaCorta = (iso: string) => new Date(iso).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })
const colorMovimiento = (type: string) =>
  type.includes('IN') || type === 'ADJUSTMENT_IN' ? 'text-dax-success' : 'text-dax-danger'
const colorExistencia = (qty: number) => (qty <= 0 ? 'text-dax-danger' : 'text-dax-success')

export function Inventory() {
  const location = useLocation()
  const esTelefono = useEsTelefono()
  // Costo e importe a costo solo para quien ve costos (misma regla que la valuación: ADMIN/DUEÑO).
  const veCosto = esRolHq(useAuthStore((s) => s.user?.role))
  const [soloSinCosto, setSoloSinCosto] = useState(false)
  const [search, setSearch] = useState('')
  const [products, setProducts] = useState<Product[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<InventoryRow | null>(null)
  const [kardex, setKardex] = useState<Awaited<ReturnType<typeof inventoryApi.getKardex>>>([])
  const [kardexLoading, setKardexLoading] = useState(false)
  const [adjustModal, setAdjustModal] = useState(false)
  const [adjQty, setAdjQty] = useState('')
  const [adjReason, setAdjReason] = useState('')
  const [adjBranch, setAdjBranch] = useState('')
  const [adjSaving, setAdjSaving] = useState(false)

  // Todas las sucursales (también las que no venden): el ajuste puede ir a una bodega.
  useEffect(() => {
    organizationApi.getBranches().then(setBranches).catch(() => {})
  }, [])

  const doSearch = useCallback(async (q: string): Promise<Product[]> => {
    if (!q.trim()) { setProducts([]); return [] }
    setLoading(true)
    try {
      const res = await productsApi.search(q, 0, 30)
      const items = res.items ?? []
      setProducts(items)
      return items
    } catch { setProducts([]); return [] } finally { setLoading(false) }
  }, [])

  // Un renglón por variante — con varias tallas, kardex y ajuste van a la que se eligió, no a la primera.
  // "Solo sin costo" filtra lo buscado (máx. 30 productos): es para corregir mientras se busca; el
  // conteo completo de piezas sin costo vive en Valor de la tienda.
  const todas = expandVariantRows(products)
  const rows = veCosto && soloSinCosto ? todas.filter(sinCosto) : todas
  const importeVenta = (r: InventoryRow) => r.qty * Number(r.variant.price ?? 0)
  const importeCosto = (r: InventoryRow) => r.qty * Number(r.variant.cost ?? 0)
  const totales = rows.reduce(
    (t, r) => ({ piezas: t.piezas + r.qty, venta: t.venta + importeVenta(r), costo: t.costo + importeCosto(r) }),
    { piezas: 0, venta: 0, costo: 0 },
  )

  const openDetail = async (row: InventoryRow) => {
    setSelected(row)
    setKardexLoading(true)
    try { setKardex(await inventoryApi.getKardex(row.variant.id)) }
    catch { setKardex([]) } finally { setKardexLoading(false) }
  }

  // Entrada con ?variant=<id>&q=<sku> (el "Ajustar" del editor de variantes, el Inicio
  // o un enlace pegado): se siembra el buscador y se abre el kardex de ESA talla.
  // Solo al montar; de ahí en adelante manda lo que el usuario teclee.
  useEffect(() => {
    const { q, variant } = initialInventoryQuery(location.search)
    if (!q && !variant) return
    setSearch(q)
    doSearch(q).then((items) => {
      if (!variant) return
      const fila = expandVariantRows(items).find((r) => r.variant.id === variant)
      if (fila) openDetail(fila)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleAdjust = async () => {
    if (!selected || !adjQty || !adjReason || !adjBranch) return
    setAdjSaving(true)
    try {
      await inventoryApi.createAdjustment({
        variant_id: selected.variant.id,
        quantity: parseInt(adjQty),
        branch_id: Number(adjBranch),
        reason: adjReason,
      })
      setAdjustModal(false); setAdjQty(''); setAdjReason(''); setAdjBranch('')
      // Recargar la tabla: sin esto la existencia del renglón seguía mostrando
      // la de antes del ajuste hasta que el usuario volvía a buscar.
      const frescos = await doSearch(search)
      const actualizado = expandVariantRows(frescos).find((r) => r.variant.id === selected.variant.id)
      if (actualizado) setSelected(actualizado)
      setKardex(await inventoryApi.getKardex(selected.variant.id))
    } catch (e: unknown) {
      toast.error(errorDetailText(
        (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail,
        'No se pudo ajustar la existencia. No se guardó nada: revisa la cantidad y el motivo, y vuelve a intentar.',
      ))
    } finally { setAdjSaving(false) }
  }

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={
          <div className="flex items-center gap-3">
            <i className="fa-solid fa-boxes text-dax-accent-text text-xl" aria-hidden="true" />
            <h1 className="text-2xl font-black text-dax-text">Inventario</h1>
          </div>
        }
      />

      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="text" placeholder="Buscar producto por nombre o SKU..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); doSearch(e.target.value) }}
          className="dax-input flex-1 min-w-[12rem] text-sm" />
        {veCosto && (
          <label className="flex items-center gap-2 text-xs text-dax-muted max-md:min-h-[44px] cursor-pointer">
            <input type="checkbox" checked={soloSinCosto} onChange={(e) => setSoloSinCosto(e.target.checked)} />
            Solo sin costo
          </label>
        )}
      </div>

      {loading && <Spinner text="Buscando..." />}

      {rows.length > 0 && !selected && (
        <DaxCard padding={false}>
          {esTelefono ? (
            <ListaTarjetas className="p-3">
              {rows.map((row) => (
                <TarjetaFila key={row.variant.id}
                  titulo={row.label}
                  subtitulo={<span className="font-mono text-dax-accent-text">{row.sku}</span>}
                  importe={formatCurrency(importeVenta(row))}
                  estado={<span className={`font-bold tabular-nums ${colorExistencia(row.qty)}`}>{row.qty} en stock</span>}
                  datos={[
                    { etiqueta: 'Precio', valor: formatCurrency(row.variant.price ?? 0) },
                    ...(veCosto ? [
                      { etiqueta: 'Costo', valor: sinCosto(row) ? <span className="text-dax-warning">sin costo</span> : formatCurrency(row.variant.cost ?? 0) },
                      { etiqueta: 'A costo', valor: formatCurrency(importeCosto(row)) },
                    ] : []),
                  ]}
                  acciones={<button type="button" onClick={() => openDetail(row)} className="dax-btn-secondary text-xs"><i className="fa-solid fa-chart-line" aria-hidden="true" /> Kardex</button>}
                />
              ))}
            </ListaTarjetas>
          ) : (
          <TablaDesplazable sangrado={false}>
            <table className="dax-table w-full">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Producto</th>
                  <th className="text-right">Precio</th>
                  {veCosto && <th className="text-right">Costo</th>}
                  <th className="text-right">Stock</th>
                  <th className="text-right">Importe venta</th>
                  {veCosto && <th className="text-right">Importe costo</th>}
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.variant.id}>
                    <td className="font-mono text-dax-accent-text text-xs">{row.sku}</td>
                    <td className="text-dax-text font-semibold">{row.label}</td>
                    {/* Precio de ESTA talla: `product.price` es el aplanado de la principal. */}
                    <td className="text-right text-dax-muted tabular-nums">{formatCurrency(row.variant.price ?? 0)}</td>
                    {veCosto && (
                      <td className="text-right text-dax-muted tabular-nums">
                        {sinCosto(row) ? <span className="text-dax-warning text-xs font-bold">sin costo</span> : formatCurrency(row.variant.cost ?? 0)}
                      </td>
                    )}
                    <td className={`text-right font-bold tabular-nums ${colorExistencia(row.qty)}`}>{row.qty}</td>
                    <td className="text-right text-dax-muted tabular-nums">{formatCurrency(importeVenta(row))}</td>
                    {veCosto && <td className="text-right text-dax-muted tabular-nums">{formatCurrency(importeCosto(row))}</td>}
                    <td>
                      <button type="button" onClick={() => openDetail(row)} className="dax-btn-secondary text-xs">
                        <i className="fa-solid fa-chart-line" aria-hidden="true" /> Kardex
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="font-bold text-dax-text" data-testid="totales">
                  <td colSpan={veCosto ? 4 : 3}>Total de lo listado</td>
                  <td className="text-right tabular-nums">{totales.piezas}</td>
                  <td className="text-right tabular-nums">{formatCurrency(totales.venta)}</td>
                  {veCosto && <td className="text-right tabular-nums">{formatCurrency(totales.costo)}</td>}
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </TablaDesplazable>
          )}
        </DaxCard>
      )}

      {selected && (
        <div className="space-y-3">
          <div className="flex max-md:flex-wrap items-center max-md:items-start justify-between gap-2">
            <div>
              <p className="text-[10px] text-dax-muted uppercase tracking-widest">Kardex</p>
              <p className="text-lg font-black text-dax-text">{selected.label}</p>
              <p className="text-xs font-mono text-dax-accent-text">{selected.sku}</p>
            </div>
            <div className="flex max-md:flex-wrap gap-2 max-md:[&>button]:min-h-[44px]">
              <button type="button" onClick={() => setAdjustModal(true)} className="dax-btn-secondary text-xs">
                <i className="fa-solid fa-sliders" aria-hidden="true" /> Ajustar
              </button>
              <button type="button" onClick={() => { setSelected(null); setKardex([]) }} className="dax-btn-secondary text-xs">
                <i className="fa-solid fa-xmark" aria-hidden="true" /> Cerrar
              </button>
            </div>
          </div>

          <DaxCard padding={false}>
            {esTelefono ? (
              <ListaTarjetas cargando={kardexLoading} vacio={kardex.length === 0} textoVacio="Sin movimientos registrados" className="p-3">
                {kardex.map((k) => (
                  <TarjetaFila key={k.id}
                    titulo={fechaCorta(k.created_at)}
                    subtitulo={<span className={`dax-badge ${colorMovimiento(k.movement_type)}`}>{tipoMovimiento(k.movement_type)}</span>}
                    importe={<span className={colorMovimiento(k.movement_type)}>{k.qty_change > 0 ? '+' : ''}{k.qty_change}</span>}
                    datos={[
                      { etiqueta: 'Saldo', valor: k.qty_after },
                      { etiqueta: 'Ref.', valor: <span className="font-mono">{k.reference ?? '—'}</span> },
                      { etiqueta: 'Por', valor: k.user_name },
                    ]}
                  />
                ))}
              </ListaTarjetas>
            ) : (
              kardexLoading ? <Spinner text="Cargando kardex..." /> : kardex.length === 0 ? (
                <div className="p-12 text-center text-dax-faint">Sin movimientos registrados</div>
              ) : (
                <TablaDesplazable sangrado={false}>
                  <table className="dax-table w-full">
                    <thead>
                      <tr>
                        <th>Fecha</th>
                        <th>Tipo</th>
                        <th className="text-right">Cantidad</th>
                        <th className="text-right">Saldo</th>
                        <th>Referencia</th>
                        <th>Por</th>
                      </tr>
                    </thead>
                    <tbody>
                      {kardex.map((k) => (
                        <tr key={k.id}>
                          <td className="text-xs text-dax-muted">{fechaCorta(k.created_at)}</td>
                          <td className="text-xs">
                            <span className={`dax-badge ${colorMovimiento(k.movement_type)}`}>{tipoMovimiento(k.movement_type)}</span>
                          </td>
                          <td className={`text-right font-bold tabular-nums ${colorMovimiento(k.movement_type)}`}>
                            {k.qty_change > 0 ? '+' : ''}{k.qty_change}
                          </td>
                          <td className="text-right text-dax-muted text-xs tabular-nums">{k.qty_after}</td>
                          <td className="text-dax-muted text-xs font-mono">{k.reference ?? '—'}</td>
                          <td className="text-dax-muted text-xs">{k.user_name}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </TablaDesplazable>
              )
            )}
          </DaxCard>
        </div>
      )}

      {!loading && !selected && products.length === 0 && search && (
        <DaxCard><div className="p-12 text-center text-dax-faint">Sin resultados para "{search}"</div></DaxCard>
      )}

      {!search && !selected && !loading && (
        <DaxCard><div className="p-12 text-center text-dax-faint">Busca un producto para ver su kardex</div></DaxCard>
      )}

      {/* Ajuste de existencia: Modal del kit. */}
      {adjustModal && selected && (
        <Modal
          open
          onClose={() => setAdjustModal(false)}
          size="sm"
          title="Ajuste de inventario"
          footer={
            <>
              <button type="button" onClick={() => setAdjustModal(false)} className="dax-btn-secondary flex-1">Cancelar</button>
              <button type="button" onClick={handleAdjust} disabled={adjSaving || !adjQty || !adjReason || !adjBranch} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
                {adjSaving ? <i className="fa-solid fa-spinner fa-spin" aria-hidden="true" /> : <><i className="fa-solid fa-check" aria-hidden="true" /> Ajustar</>}
              </button>
            </>
          }
        >
          <p className="text-dax-muted text-sm mb-4">{selected.label}</p>
          <div className="space-y-3">
            <div>
              <label className="dax-label" htmlFor="ajuste-sucursal">Sucursal</label>
              <select id="ajuste-sucursal" value={adjBranch} onChange={(e) => setAdjBranch(e.target.value)} className="dax-input w-full">
                <option value="">Seleccionar...</option>
                {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </div>
            <div>
              <label className="dax-label" htmlFor="ajuste-cantidad">Cantidad (+ agregar / - restar)</label>
              <input id="ajuste-cantidad" type="number" value={adjQty} onChange={(e) => setAdjQty(e.target.value)}
                placeholder="+10 o -5" className="dax-input w-full text-lg font-bold" autoFocus />
            </div>
            <div>
              <label className="dax-label" htmlFor="ajuste-motivo">Motivo</label>
              <input id="ajuste-motivo" value={adjReason} onChange={(e) => setAdjReason(e.target.value)}
                placeholder="Conteo físico, merma, etc." className="dax-input w-full" />
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
```

> `dax-label` no está definida en `index.css` pero la usan 59 archivos del repo (incluidas las dos pantallas de inventario de hoy): se conserva tal cual, no es trabajo de esta fase.

- [ ] **Step 3: Baja de `HQInventory`, redirect, enlaces del Inicio**

```bash
git rm frontend/src/pages/hq/HQInventory.tsx
```

`frontend/src/App.tsx`:
1. Borrar `const HQInventory     = lazy(() => import('./pages/hq/HQInventory').then(m => ({ default: m.HQInventory })))`.
2. Sustituir `<Route path="inventory" element={<RutaPorRol url="/hq/inventory"><Suspense fallback={<PageLoader />}><HQInventory /></Suspense></RutaPorRol>} />` (dentro de `<Route path="hq">`) por:

```tsx
            <Route path="inventory" element={<RedirigirConQuery a="/inventory" />} />
```

`frontend/src/pages/hq/Inicio.tsx`, sustituir las líneas 45-52 (comentario, `ENLACES`, `urlExistencias`) por:

```tsx
/** Enlaces de detalle por perfil: en básico, a las pantallas que SÍ están en su menú
 *  (Productos y Ventas); en completo, a Inventario (kardex, ajuste, costo) y Ventas. */
const ENLACES = {
  basico:   { existencias: '/products', ventas: '/sales' },
  completo: { existencias: '/inventory', ventas: '/sales' },
} as const
const urlExistencias = (basico: boolean, sku: string, variantId: string) =>
  basico ? ENLACES.basico.existencias : `/inventory?q=${encodeURIComponent(sku)}&variant=${encodeURIComponent(variantId)}`
```

Y en la línea 201: `<Titulo enlace={{ a: '/hq/inventory', texto: 'Ver existencias →' }}>` → `<Titulo enlace={{ a: '/inventory', texto: 'Ver inventario →' }}>`. En la línea 135 (`texto: basico ? 'Ver productos →' : 'Ver existencias →'`) cambiar `'Ver existencias →'` por `'Ver inventario →'`.

`frontend/src/pages/hq/__tests__/Inicio.test.tsx`:
- Línea 161: `.toBe('/hq/inventory?q=ABR-1&variant=v9')` → `.toBe('/inventory?q=ABR-1&variant=v9')`.
- Sustituir las dos pruebas de las líneas 284-301 por:

```tsx
  it('en básico los enlaces van a Productos y Ventas, nunca a Inventario ni Devoluciones (escondidas en básico)', async () => {
    pintar()
    await screen.findByTestId('cifra-hoy')
    const hrefs = Array.from(document.querySelectorAll('a')).map((a) => a.getAttribute('href'))
    expect(hrefs).toContain('/products')
    expect(hrefs).toContain('/sales')
    expect(hrefs.some((h) => h?.startsWith('/inventory') || h?.startsWith('/returns') || h?.startsWith('/hq/inventory') || h?.startsWith('/hq/sales'))).toBe(false)
    expect(screen.getByText('Falda negra').closest('a')?.getAttribute('href')).toBe('/products')
  })

  it('en completo los mismos enlaces abren el kardex en Inventario y la pantalla de Ventas', async () => {
    perfil('completo')
    inicio.mockResolvedValue(COMPLETO)
    pintar()
    await screen.findByTestId('cifra-hoy')
    expect(screen.getByText('Falda negra').closest('a')?.getAttribute('href')).toBe('/inventory?q=FAL-1&variant=v1')
    expect(screen.getByText('Ver ventas →').getAttribute('href')).toBe('/sales')
    expect(screen.getAllByText('Ver inventario →').length).toBeGreaterThan(0)
  })
```

- [ ] **Step 4: Guardias**

`frontend/src/__tests__/coloresPorTokens.test.ts`: quitar `'pages/hq/HQInventory.tsx'` (línea 26; la línea queda `'pages/hq/HQBranches.tsx',`) y `'pages/inventory/Inventory.tsx'` (línea 27) de `PENDIENTES`; en `LIMPIOS` la línea de la Fase 3 queda `'pages/sales/SalesHistory.tsx', 'pages/sales/Returns.tsx', 'pages/inventory/Inventory.tsx',`.

`frontend/src/__tests__/overlaysFueraDelKit.test.ts`: borrar `'/pages/inventory/Inventory.tsx': 1,`.

`frontend/src/pages/__tests__/responsivoOla2.test.ts`: en `PAGINAS` quitar `'hq/HQInventory.tsx'`; en la línea 32 cambiar `it.each(['inventory/Inventory.tsx', 'hq/HQInventory.tsx'])` por `it.each(['inventory/Inventory.tsx'])`.

- [ ] **Step 5: Correr**

Run: `cd frontend && npx vitest run src/pages/inventory src/pages/hq src/__tests__ src/pages/__tests__ --reporter=dot 2>&1 | tail -6 && npx tsc --noEmit -p tsconfig.json`
Expected: todo verde (Inventory 6; `responsivoOla2` «las dos tablas están tras el condicional» cuenta 2 `<table` y 2 `esTelefono ?` en `Inventory.tsx`); tsc limpio.

Run: `git grep -n "HQInventory" -- 'frontend/src' ':!*.test.*'`
Expected: **exactamente una** línea, el comentario de cabecera de `pages/inventory/Inventory.tsx` («…que vivían en `hq/HQInventory` (borrada)»).

Run: `git grep -n "/hq/inventory" -- 'frontend/src' ':!*.test.*'`
Expected: exactamente dos archivos: `components/layout/navConfig.ts` (ítem «Existencias», grupo Inventario y `ROLE_ROUTES`) y `components/layout/navPerfilBasico.ts`; ambos los limpia la Tarea 5. Ni `App.tsx` ni `Inicio.tsx` deben aparecer. (Entre las pruebas, `Inicio.test.tsx` conserva a propósito `startsWith('/hq/inventory')` en la aserción de básico.)

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src/pages/inventory/Inventory.tsx frontend/src/pages/inventory/__tests__/Inventory.test.tsx \
  frontend/src/pages/hq/__tests__/HQInventory.test.tsx frontend/src/App.tsx frontend/src/pages/hq/Inicio.tsx \
  frontend/src/pages/hq/__tests__/Inicio.test.tsx frontend/src/__tests__/coloresPorTokens.test.ts \
  frontend/src/__tests__/overlaysFueraDelKit.test.ts frontend/src/pages/__tests__/responsivoOla2.test.ts
git commit -m "feat(inventario): /inventory absorbe Existencias (costo, importes y 'solo sin costo' para HQ) y /hq/inventory redirige con su consulta

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 4: Productos — `Products` absorbe `AdminCatalog` (cifras, aprobación, archivar, duplicar, restaurar)

**Files:**
- Modify: `frontend/src/pages/inventory/Products.tsx` (ediciones acotadas; se queda en `PENDIENTES` de tokens)
- Rewrite: `frontend/src/pages/core/catalogActions.ts`; Modify: `frontend/src/pages/core/__tests__/catalogActions.test.ts`
- Modify: `frontend/src/api/products.ts` (nuevo `archive`)
- Create: `frontend/src/pages/inventory/__tests__/ProductsCatalogo.test.tsx`; Modify: `frontend/src/pages/inventory/__tests__/ProductsBasico.test.tsx:6-11`
- Delete: `frontend/src/pages/core/AdminCatalog.tsx`
- Modify: `frontend/src/App.tsx` (lazy `AdminCatalog`, rutas `admin/catalog` y `admin/products/new`), `frontend/src/pages/menu/MenuVisual.tsx:92`, `frontend/src/pages/home/PresetHome.tsx:402`, `frontend/src/pages/products/ProductForm.tsx:8`, `frontend/src/pages/products/__tests__/volver.test.ts:9-10`
- Modify: `frontend/src/__tests__/coloresPorTokens.test.ts`, `frontend/src/pages/__tests__/responsivoOla2.test.ts:8, 12`

**Interfaces:**
- Consumes: `RedirigirConQuery` (Tarea 1); `CatalogKpis` (`components/catalog/CatalogKpis.tsx`, props `data`, `loading`, `onFilterPending`, `onFilterNoBranch`), `ProductBranchMatrix` (`product`, `onClose`, `onSaved?`), `ProductAuditDrawer` (`product`, `onClose`); `confirm({ title, message, confirmText, variant })`; `productsApi.list/catalogKpis/getBrands/approve/reject/duplicate/restore/downloadTemplate`; `esTiendaUnica(useBranchCountStore(s => s.count))` (ya en `Products.tsx`).
- Produces: `productsApi.archive(id: string): Promise<void>`; `accionesDeProducto(p, { conMatriz?: boolean })` y `ACCIONES_CATALOGO[clave].clase` ∈ `'dax-btn-ghost' | 'dax-btn-primary' | 'dax-btn-danger'`.

Decisiones: todo lo fusionado —incluidos duplicar, Exportar y las cifras, que la spec §4.1 no marca como «solo HQ»— se pinta solo con `catalogo = isHQ && !modoBasico` (desviación aceptada por el coordinador; cajera y gerente siguen en `ProductsBranchView`; la Tarea 6 la anota en la spec). El básico escondía el Catálogo a propósito y "lo que no se pinta no se consulta": sin `catalogKpis` ni `getBrands`. El `Badge` «Sin sucursal» (tono `yellow`) queda visible para HQ en la celda de sucursales. Se conservan de `AdminCatalog` el filtro por marca y «Exportar» (Excel con los filtros vigentes). «Matriz de sucursales» solo con más de una sucursal (`!unaSolaSucursal`). La cuadrícula conserva solo Editar. El formulario sigue siendo `FormularioProducto` en el `Modal` (como `Products` hoy; `AdminCatalog` navegaba a la página).

- [ ] **Step 1: `catalogActions.ts` con clases del kit y `conMatriz` (prueba primero)**

Añadir al final de `frontend/src/pages/core/__tests__/catalogActions.test.ts` (dentro del `describe`):

```ts
  it('con conMatriz: false no ofrece la matriz (una sola tienda)', () => {
    expect(accionesDeProducto({ approval_status: 'APPROVED', is_active: true }, { conMatriz: false }))
      .toEqual(['historial', 'editar', 'duplicar', 'archivar'])
  })

  it('toda acción usa una clase de botón del kit (sin colores sueltos)', () => {
    for (const meta of Object.values(ACCIONES_CATALOGO)) expect(meta.clase).toMatch(/^dax-btn-(ghost|primary|danger)$/)
  })
```

Run: `cd frontend && npx vitest run src/pages/core/__tests__/catalogActions.test.ts --reporter=dot` → Expected: 2 fallos.

Sustituir `frontend/src/pages/core/catalogActions.ts` por:

```ts
/**
 * Acciones por producto del catálogo (lista de `/products`, HQ en perfil
 * completo; antes `/admin/catalog`, fusionado en la Fase 3 del admin).
 *
 * Qué botones aparecen depende del estado del producto (pendiente de
 * aprobación, archivado…). La decisión vive aquí —pura y probable— y la tabla
 * (escritorio) y las tarjetas (teléfono) la recorren igual.
 */

export type ClaveAccionCatalogo =
  | 'matriz' | 'aprobar' | 'rechazar' | 'historial'
  | 'editar' | 'duplicar' | 'archivar' | 'restaurar'

/** Clase del botón del kit (botonesDelKit.test.ts): neutras en ghost, aprobar en primary, destructivas en danger. */
export type ClaseBotonAccion = 'dax-btn-ghost' | 'dax-btn-primary' | 'dax-btn-danger'

export interface MetaAccionCatalogo {
  /** Texto del `title` y del `aria-label` («Acción — Producto»); en tarjeta también se pinta. */
  etiqueta: string
  /** Clase de Font Awesome. */
  icono: string
  clase: ClaseBotonAccion
}

export const ACCIONES_CATALOGO: Record<ClaveAccionCatalogo, MetaAccionCatalogo> = {
  matriz:    { etiqueta: 'Matriz de sucursales', icono: 'fa-store',             clase: 'dax-btn-ghost' },
  aprobar:   { etiqueta: 'Aprobar',              icono: 'fa-check',             clase: 'dax-btn-primary' },
  rechazar:  { etiqueta: 'Rechazar',             icono: 'fa-xmark',             clase: 'dax-btn-danger' },
  historial: { etiqueta: 'Historial',            icono: 'fa-clock-rotate-left', clase: 'dax-btn-ghost' },
  editar:    { etiqueta: 'Editar',               icono: 'fa-pencil',            clase: 'dax-btn-ghost' },
  duplicar:  { etiqueta: 'Duplicar',             icono: 'fa-copy',              clase: 'dax-btn-ghost' },
  archivar:  { etiqueta: 'Archivar',             icono: 'fa-box-archive',       clase: 'dax-btn-danger' },
  restaurar: { etiqueta: 'Restaurar',            icono: 'fa-box-open',          clase: 'dax-btn-ghost' },
}

/** Producto visto solo por lo que decide sus acciones. */
export interface ProductoAccionable {
  approval_status?: string | null
  is_active?: boolean
}

/**
 * Acciones disponibles para un producto, en el orden en que se pintan.
 *
 * Aprobar y rechazar solo tienen sentido mientras está `PENDING`; archivar y
 * restaurar son excluyentes según `is_active`. Con una sola sucursal la matriz
 * sobra (`conMatriz: false`): el formulario ya trae su sección de sucursal.
 */
export function accionesDeProducto(p: ProductoAccionable, opciones: { conMatriz?: boolean } = {}): ClaveAccionCatalogo[] {
  const claves: ClaveAccionCatalogo[] = opciones.conMatriz === false ? [] : ['matriz']
  if (p.approval_status === 'PENDING') claves.push('aprobar', 'rechazar')
  claves.push('historial', 'editar', 'duplicar')
  claves.push(p.is_active ? 'archivar' : 'restaurar')
  return claves
}
```

Run otra vez → Expected: 7 passed.

- [ ] **Step 2: `productsApi.archive`**

En `frontend/src/api/products.ts`, justo antes de `createVariants:` (después del bloque `restore`), añadir:

```ts
  /** DELETE /api/products/{id} — archiva (soft-delete, admin-only); `restore` lo revierte. */
  archive: async (id: string): Promise<void> => {
    await client.delete(`/products/${id}`)
  },
```

- [ ] **Step 3: Pruebas de la lista fusionada (fallan)**

Crear `frontend/src/pages/inventory/__tests__/ProductsCatalogo.test.tsx`:

```tsx
// frontend/src/pages/inventory/__tests__/ProductsCatalogo.test.tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

const api = vi.hoisted(() => ({
  list: vi.fn(),
  getDepartments: vi.fn(async () => []),
  getBrands: vi.fn(async () => [{ id: 'b1', name: 'Kaws', logo_url: null }]),
  barcodesMissingCount: vi.fn(async () => 0),
  catalogKpis: vi.fn(),
  approve: vi.fn(async () => ({ status: 'approved', product_id: 'p1' })),
  reject: vi.fn(async () => ({ status: 'rejected', product_id: 'p1' })),
  duplicate: vi.fn(),
  archive: vi.fn(async () => undefined),
  restore: vi.fn(async () => ({ status: 'ok', product_id: 'p2', message: 'Restaurado' })),
  downloadTemplate: vi.fn(async () => undefined),
}))
vi.mock('../../../api/products', () => ({ productsApi: api }))
vi.mock('../../../components/branch/ProductsBranchView', () => ({ ProductsBranchView: () => <div data-testid="vista-sucursal" /> }))
vi.mock('../../../components/catalog/CatalogKpis', () => ({
  CatalogKpis: ({ data }: { data: unknown }) => <div data-testid="kpis-catalogo" data-cargado={data ? '1' : '0'} />,
}))
vi.mock('../../../components/catalog/ProductBranchMatrix', () => ({ ProductBranchMatrix: () => <div data-testid="matriz" /> }))
vi.mock('../../../components/catalog/ProductAuditDrawer', () => ({ ProductAuditDrawer: () => <div data-testid="historial" /> }))
vi.mock('../../../components/ui/ConfirmDialog', () => ({ confirm: vi.fn(async () => true) }))
vi.mock('../../../components/products/FormularioProducto', () => ({ FormularioProducto: () => <div data-testid="formulario" /> }))

import { Products } from '../Products'
import { useAuthStore } from '../../../store/authStore'
import { useEnabledModulesStore } from '../../../store/enabledModulesStore'
import { useBranchCountStore } from '../../../store/branchCountStore'

const KPIS = { total_skus: 2, active_pos: 1, pending_approval: 1, no_branch: 0, critical_stock: 0, zero_stock: 0, threshold: 3 }
const producto = (id: string, name: string, extra: Record<string, unknown>) => ({
  id, sku: id.toUpperCase(), name, description: null, brand_id: null, brand_name: null, department: null, department_name: null,
  unit: null, cost: 10, price: 100, stock: 1, stock_total: 1, image_url: null, is_active: true, approval_status: 'APPROVED',
  variants: [], branch_statuses: [], ...extra,
})
const PENDIENTE = producto('p1', 'Blusa nueva', { approval_status: 'PENDING' })
const ARCHIVADO = producto('p2', 'Falda vieja', { is_active: false })
const admin = { id: 1, username: 'admin', role: 'ADMINISTRADOR', branch_id: null, platform_role: 'NONE' }
const perfil = (perfilUi: 'basico' | 'completo') => useEnabledModulesStore.setState({ loaded: true, perfilUi } as never)
const pintar = () => render(<MemoryRouter><Products /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  api.list.mockResolvedValue({ items: [PENDIENTE, ARCHIVADO], total: 2, page: 0, pages: 1 })
  api.catalogKpis.mockResolvedValue(KPIS)
  useAuthStore.setState({ user: admin } as never)
  useBranchCountStore.setState({ count: 1 })
  perfil('completo')
})
afterEach(cleanup)

describe('Productos: catálogo fusionado (HQ en perfil completo)', () => {
  it('pinta las cifras, el filtro de aprobación, Incluir archivados y Exportar; la lista se pide con los filtros', async () => {
    pintar()
    await screen.findByText('Blusa nueva')
    expect(screen.getByTestId('kpis-catalogo')).toBeTruthy()
    await waitFor(() => expect(api.catalogKpis).toHaveBeenCalled())
    expect(screen.getByRole('group', { name: 'Aprobación' })).toBeTruthy()
    expect(screen.getByLabelText('Exportar catálogo')).toBeTruthy()
    fireEvent.click(screen.getByLabelText('Incluir archivados'))
    await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ include_inactive: true })))
    fireEvent.click(screen.getByRole('button', { name: 'Pendientes' }))
    await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ approval_status: 'PENDING' })))
    fireEvent.change(screen.getByLabelText('Marca'), { target: { value: 'b1' } })
    await waitFor(() => expect(api.list).toHaveBeenLastCalledWith(expect.objectContaining({ brand_id: 'b1' })))
  })

  it('un pendiente ofrece Aprobar y Rechazar; un archivado, Restaurar; con una sola tienda no hay Matriz', async () => {
    pintar()
    await screen.findByText('Blusa nueva')
    expect(screen.getByText('Pendiente')).toBeTruthy()
    expect(screen.getByText('Archivado')).toBeTruthy()
    expect(screen.getAllByText('Sin sucursal')).toHaveLength(2)   // ambos productos tienen branch_statuses vacío
    expect(screen.getByLabelText('Aprobar — Blusa nueva')).toBeTruthy()
    expect(screen.getByLabelText('Rechazar — Blusa nueva')).toBeTruthy()
    expect(screen.getByLabelText('Restaurar — Falda vieja')).toBeTruthy()
    expect(screen.queryByLabelText('Archivar — Falda vieja')).toBeNull()
    expect(screen.queryByLabelText(/Matriz de sucursales/)).toBeNull()
    fireEvent.click(screen.getByLabelText('Aprobar — Blusa nueva'))
    await waitFor(() => expect(api.approve).toHaveBeenCalledWith('p1'))
    fireEvent.click(screen.getByLabelText('Archivar — Blusa nueva'))
    await waitFor(() => expect(api.archive).toHaveBeenCalledWith('p1'))
  })

  it('con varias sucursales aparece la Matriz de sucursales y abre su modal', async () => {
    useBranchCountStore.setState({ count: 2 })
    pintar()
    await screen.findByText('Blusa nueva')
    fireEvent.click(screen.getByLabelText('Matriz de sucursales — Blusa nueva'))
    expect(await screen.findByTestId('matriz')).toBeTruthy()
  })

  it('en básico la dueña no ve cifras, aprobación ni archivados, y no se consultan', async () => {
    perfil('basico')
    pintar()
    await screen.findByText('Blusa nueva')
    expect(screen.queryByTestId('kpis-catalogo')).toBeNull()
    expect(screen.queryByRole('group', { name: 'Aprobación' })).toBeNull()
    expect(screen.queryByLabelText('Incluir archivados')).toBeNull()
    expect(screen.queryByLabelText('Aprobar — Blusa nueva')).toBeNull()
    expect(screen.getAllByLabelText('Editar producto').length).toBe(2)   // una por fila: solo Editar
    expect(api.catalogKpis).not.toHaveBeenCalled()
    expect(api.getBrands).not.toHaveBeenCalled()
  })

  it('la gerente ve la vista de sucursal, sin acciones de catálogo', async () => {
    useAuthStore.setState({ user: { ...admin, role: 'GERENTE', branch_id: 20 } } as never)
    pintar()
    expect(await screen.findByTestId('vista-sucursal')).toBeTruthy()
    expect(api.catalogKpis).not.toHaveBeenCalled()
  })
})
```

En `frontend/src/pages/inventory/__tests__/ProductsBasico.test.tsx`, el objeto `api` (líneas 6-11) pasa a:

```ts
const api = vi.hoisted(() => ({
  list: vi.fn(async () => ({ items: [], total: 0 })),
  getDepartments: vi.fn(async () => []),
  getBrands: vi.fn(async () => []),
  barcodesMissingCount: vi.fn(async () => 4),
  getCatalogKpis: vi.fn(async () => null),
  catalogKpis: vi.fn(async () => null),
}))
```

y en la prueba «básico: solo Nuevo producto» añadir, tras `expect(api.barcodesMissingCount).not.toHaveBeenCalled()`:

```ts
    expect(api.catalogKpis).not.toHaveBeenCalled()
    expect(screen.queryByLabelText('Incluir archivados')).toBeNull()
```

Run: `cd frontend && npx vitest run src/pages/inventory/__tests__/ProductsCatalogo.test.tsx src/pages/inventory/__tests__/ProductsBasico.test.tsx --reporter=dot` → Expected: `ProductsCatalogo` falla (no hay cifras, filtros ni acciones); `ProductsBasico` pasa.

- [ ] **Step 4: Ediciones en `Products.tsx`**

Todas las referencias son al archivo tal como está en `main` 4321268e; busca por el texto, no por el número de línea.

**4a. Imports.** Sustituir `import type { Product, Department } from '../../types/products'` por:

```tsx
import type { Product, Department, Brand } from '../../types/products'
```

y, debajo de `import { cerrarImportacion, debeCerrarSolo } from './importacion'`, añadir:

```tsx
import { CatalogKpis } from '../../components/catalog/CatalogKpis'
import { ProductBranchMatrix } from '../../components/catalog/ProductBranchMatrix'
import { ProductAuditDrawer } from '../../components/catalog/ProductAuditDrawer'
import { confirm } from '../../components/ui/ConfirmDialog'
import { ACCIONES_CATALOGO, accionesDeProducto, type ClaveAccionCatalogo } from '../core/catalogActions'
```

**4b. Constantes.** Debajo de `const CAN_EDIT_ROLES = ['ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO']` añadir:

```tsx
// Catálogo (fusión de /admin/catalog, Fase 3 del admin): filtro de aprobación. Solo HQ en perfil completo.
type FiltroAprobacion = 'ALL' | 'PENDING' | 'APPROVED' | 'REJECTED'
const FILTROS_APROBACION: { clave: FiltroAprobacion; etiqueta: string }[] = [
  { clave: 'ALL', etiqueta: 'Todos' }, { clave: 'PENDING', etiqueta: 'Pendientes' },
  { clave: 'APPROVED', etiqueta: 'Aprobados' }, { clave: 'REJECTED', etiqueta: 'Rechazados' },
]
```

**4b-bis. «Sin sucursal» visible.** En `EstadoDeFila`, la rama `isHQ` pinta «N sucursales»; un producto sin ninguna (`branch_statuses` vacío) debe gritarlo (antes lo hacía `BranchBadge` del Catálogo). Sustituir

```tsx
  return isHQ ? (
    <span className="text-xs text-slate-400">
      {p.branch_statuses?.filter(s => s.is_active_pos).length ?? 0}
      <span className="text-slate-600 ml-0.5">sucursales</span>
    </span>
  ) : user?.branch_id ? (
```

por

```tsx
  return isHQ ? (
    (p.branch_statuses?.length ?? 0) === 0 ? (
      <Badge variant="yellow">Sin sucursal</Badge>
    ) : (
      <span className="text-xs text-slate-400">
        {p.branch_statuses?.filter(s => s.is_active_pos).length ?? 0}
        <span className="text-slate-600 ml-0.5">sucursales</span>
      </span>
    )
  ) : user?.branch_id ? (
```

(`yellow` es el tono de advertencia del kit `Badge`; se muestra a HQ en ambos perfiles: es un dato del producto.)

**4c. Distintivo de aprobación.** Después de la función `EstadoDeFila` (termina en `  ) : null\n}`), añadir:

```tsx
/** Distintivo de aprobación/archivado del catálogo (solo HQ en perfil completo). Solo tokens. */
function EstadoAprobacion({ p }: { p: Product }) {
  if (!p.is_active) return <Badge variant="slate">Archivado</Badge>
  const s = p.approval_status || 'APPROVED'
  if (s === 'PENDING') return <Badge variant="yellow">Pendiente</Badge>
  if (s === 'REJECTED') return <Badge variant="red">Rechazado</Badge>
  return <Badge variant="green">Aprobado</Badge>
}
```

**4d. `AccionesDeFila`.** Sustituir la función completa (desde su comentario `/** Última columna: Editar…` hasta su `}` de cierre) por:

```tsx
/**
 * Última columna. Fuera del catálogo: solo Editar (icono en la tabla; con texto
 * en la tarjeta, hijo directo de las acciones de `TarjetaFila` para sus 44 px).
 * Con `catalogo` (HQ en perfil completo): las acciones de `accionesDeProducto`
 * en orden —matriz (solo con varias sucursales), aprobar/rechazar (pendientes),
 * historial, editar, duplicar y archivar/restaurar— con `aria-label` «Acción — Producto».
 */
function AccionesDeFila({ p, onEditar, conTexto = false, catalogo = false, conMatriz = true, onAccion }: {
  p: Product
  onEditar: (p: Product) => void
  conTexto?: boolean
  catalogo?: boolean
  conMatriz?: boolean
  onAccion?: (clave: ClaveAccionCatalogo, p: Product) => void
}) {
  if (catalogo && onAccion) {
    return (
      <div className={conTexto ? 'flex flex-wrap gap-1.5' : 'inline-flex items-center gap-1'}>
        {accionesDeProducto(p, { conMatriz }).map((clave) => {
          const meta = ACCIONES_CATALOGO[clave]
          return (
            <button
              key={clave}
              type="button"
              onClick={() => (clave === 'editar' ? onEditar(p) : onAccion(clave, p))}
              className={`${meta.clase} ${conTexto ? 'text-xs' : 'dax-btn-icon text-xs'}`}
              title={meta.etiqueta}
              aria-label={`${meta.etiqueta} — ${p.name}`}
            >
              <i className={`fa-solid ${meta.icono}`} aria-hidden="true" />
              {conTexto && <span> {meta.etiqueta}</span>}
            </button>
          )
        })}
      </div>
    )
  }
  if (conTexto) {
    return (
      <button onClick={() => onEditar(p)} className="dax-btn-secondary text-xs" aria-label="Editar producto">
        <i className="fa-solid fa-pencil" /> Editar
      </button>
    )
  }
  return (
    <div className="inline-flex items-center gap-1">
      <button
        onClick={() => onEditar(p)}
        className="dax-btn-icon transition-colors p-1 text-slate-500 hover:text-indigo-400"
        title="Editar producto"
        aria-label="Editar producto"
      >
        <i className="fa-solid fa-pencil text-xs" />
      </button>
    </div>
  )
}
```

**4e. Estado del catálogo.** Dentro de `ProductsHQView`, después de `const modoBasico = useModoBasico()`, añadir:

```tsx
  // Catálogo (fusión de /admin/catalog, Fase 3): cifras, aprobación, archivados y acciones
  // por producto. Solo HQ en perfil completo: el básico escondía el Catálogo a propósito y
  // lo que no se pinta no se consulta.
  const catalogo = isHQ && !modoBasico
  const [brands, setBrands] = useState<Brand[]>([])
  const [brandId, setBrandId] = useState('')
  const [aprobacion, setAprobacion] = useState<FiltroAprobacion>('ALL')
  const [incluirArchivados, setIncluirArchivados] = useState(false)
  const [soloSinSucursal, setSoloSinSucursal] = useState(false)
  const [kpis, setKpis] = useState<Awaited<ReturnType<typeof productsApi.catalogKpis>> | null>(null)
  const [kpisLoading, setKpisLoading] = useState(false)
  const [matrixProduct, setMatrixProduct] = useState<Product | null>(null)
  const [auditProduct, setAuditProduct] = useState<Product | null>(null)
```

Cambiar `const [products, setProducts] = useState<Product[]>([])` por:

```tsx
  const [todos, setTodos] = useState<Product[]>([])
  // "Sin sucursal" (tarjeta de cifras): filtro en cliente sobre la página cargada, como en el Catálogo viejo.
  const products = soloSinSucursal ? todos.filter((p) => !p.branch_statuses || p.branch_statuses.length === 0) : todos
```

**4f. `load` y `cargarKpis`.** Sustituir el `load` completo (desde `const load = useCallback(async (q: string, dept: string, pg: number) => {` hasta `}, [])`) por:

```tsx
  const load = useCallback(async (q: string, dept: string, pg: number) => {
    setLoading(true)
    try {
      const params: Record<string, unknown> = { search: q, skip: pg * LIMIT, limit: LIMIT }
      if (dept) params.department_id = dept
      // Filtros del catálogo (HQ en perfil completo). Fuera de él no viajan: la lista es la de siempre.
      if (catalogo) {
        if (brandId) params.brand_id = brandId
        if (aprobacion !== 'ALL') params.approval_status = aprobacion
        if (incluirArchivados) params.include_inactive = true
      }
      // No enviamos branch_id ni active_in_branch: el backend los deriva del JWT
      // (defense in depth). Esta vista es la de HQ; ningún rol los envía desde aquí.
      const res = await productsApi.list(params)
      setTodos(res.items ?? [])
      setTotal(res.total ?? 0)
    } catch (e: any) {
      setTodos([])
      setTotal(0)
      const detail = e?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'No se pudo cargar el catálogo. Reintenta.')
    } finally {
      setLoading(false)
    }
  }, [catalogo, brandId, aprobacion, incluirArchivados])

  // Cifras del catálogo con los mismos filtros que la lista (sin `include_inactive`: el endpoint no lo acepta).
  const cargarKpis = useCallback(async () => {
    if (!catalogo) return
    setKpisLoading(true)
    try {
      setKpis(await productsApi.catalogKpis({
        search: search.trim() || undefined,
        department_id: deptId || undefined,
        brand_id: brandId || undefined,
        approval_status: aprobacion === 'ALL' ? undefined : aprobacion,
      }))
    } catch {
      setKpis(null)
    } finally {
      setKpisLoading(false)
    }
  }, [catalogo, search, deptId, brandId, aprobacion])
```

**4g. Efecto de montaje.** En el `useEffect(() => { productsApi.getDepartments() … }, [])`, después del bloque `if (!modoBasico) { … }` y antes de `}, [])`, añadir:

```tsx
    if (catalogo) {
      productsApi.getBrands()
        .then((b) => setBrands(sortByName(b)))
        .catch(() => toast.error('No se pudieron cargar las marcas.'))
    }
```

**4h. Efecto con debounce.** Sustituir el efecto `useEffect(() => { if (debounceRef.current) clearTimeout(…) … }, [search, deptId, load])` por:

```tsx
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setPage(0)
      load(search, deptId, 0)
      cargarKpis()
    }, 300)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [search, deptId, load, cargarKpis])
```

**4i. Acciones y exportar.** Después de `const handleNewProductClick = () => setEditor({ mode: 'create' })` añadir:

```tsx
  // Acciones del catálogo (antes en AdminCatalog). Tras cada una se releen lista y cifras.
  const detalleError = (e: unknown, respaldo: string) => {
    const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
    toast.error(typeof detail === 'string' ? detail : respaldo)
  }
  const recargarCatalogo = () => { load(search, deptId, page); cargarKpis() }
  const correrAccion = async (clave: ClaveAccionCatalogo, p: Product) => {
    switch (clave) {
      case 'matriz': setMatrixProduct(p); return
      case 'historial': setAuditProduct(p); return
      case 'editar': openEdit(p); return
      case 'aprobar':
        try { await productsApi.approve(p.id); toast.success(`Aprobado: ${p.name}`); recargarCatalogo() }
        catch (e) { detalleError(e, 'Error al aprobar.') }
        return
      case 'rechazar':
        if (!(await confirm({ title: 'Rechazar producto', message: `"${p.name}" se desactivará en el punto de venta de todas las sucursales.`, confirmText: 'Rechazar', variant: 'danger' }))) return
        try { await productsApi.reject(p.id); toast.success(`Rechazado: ${p.name}`); recargarCatalogo() }
        catch (e) { detalleError(e, 'Error al rechazar.') }
        return
      case 'duplicar':
        if (!(await confirm({ title: 'Duplicar producto', message: `Se creará una copia de "${p.name}" con SKU nuevo y sin existencias.`, confirmText: 'Duplicar', variant: 'info' }))) return
        try { const copia = await productsApi.duplicate(p.id); toast.success(`Copia creada: ${copia.sku}`); recargarCatalogo() }
        catch (e) { detalleError(e, 'Error al duplicar.') }
        return
      case 'archivar':
        if (!(await confirm({ title: 'Archivar producto', message: `"${p.name}" se desactivará en todas las sucursales. Podrás volver a verlo con "Incluir archivados".`, confirmText: 'Archivar', variant: 'danger' }))) return
        try { await productsApi.archive(p.id); toast.success('Producto archivado.'); recargarCatalogo() }
        catch (e) { detalleError(e, 'Error al archivar.') }
        return
      case 'restaurar':
        try { const r = await productsApi.restore(p.id); toast.success(r.message ?? 'Producto restaurado.'); recargarCatalogo() }
        catch (e) { detalleError(e, 'Error al restaurar.') }
        return
    }
  }
  const exportar = async () => {
    try {
      await productsApi.downloadTemplate({
        search: search.trim() || undefined,
        department_id: deptId || undefined,
        brand_id: brandId || undefined,
        approval_status: aprobacion === 'ALL' ? undefined : aprobacion,
        include_inactive: incluirArchivados || undefined,
      })
      toast.success('Descarga iniciada.')
    } catch (e) {
      detalleError(e, 'No se pudo exportar el catálogo.')
    }
  }
```

**4j. Cabecera.** Dentro de `acciones`, justo antes del botón «Nuevo producto» (`<button onClick={handleNewProductClick}`) y dentro del `{canEdit && (<>…`, añadir:

```tsx
                  {catalogo && (
                    <button
                      type="button"
                      onClick={exportar}
                      className="dax-btn-secondary dax-btn-icon text-xs flex items-center gap-1.5 whitespace-nowrap"
                      title="Exportar el catálogo filtrado a Excel"
                      aria-label="Exportar catálogo"
                    >
                      <i className="fa-solid fa-file-excel" aria-hidden="true" /> <span className="hidden sm:inline">Exportar</span>
                    </button>
                  )}
```

**4k. Cifras.** Entre `/>` que cierra `<CabeceraPagina` y el comentario `{/* Filtros */}` añadir:

```tsx
      {catalogo && (
        <CatalogKpis
          data={kpis}
          loading={kpisLoading}
          onFilterPending={() => setAprobacion('PENDING')}
          onFilterNoBranch={() => setSoloSinSucursal(true)}
        />
      )}
```

**4l. Filtros.** Dentro de `<BarraFiltros className="gap-3 !items-stretch">`, después del `</select>` de departamentos, añadir:

```tsx
        {catalogo && (
          <>
            <select
              aria-label="Marca"
              value={brandId}
              onChange={(e) => { setBrandId(e.target.value); setPage(0) }}
              className="dax-input max-w-[200px]"
            >
              <option value="">Todas las marcas</option>
              {brands.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
            <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Aprobación">
              {FILTROS_APROBACION.map((f) => (
                <button
                  key={f.clave}
                  type="button"
                  onClick={() => { setAprobacion(f.clave); setPage(0) }}
                  aria-pressed={aprobacion === f.clave}
                  className={`${aprobacion === f.clave ? 'dax-btn-primary' : 'dax-btn-secondary'} text-xs max-sm:min-h-[44px]`}
                >
                  {f.etiqueta}
                </button>
              ))}
            </div>
            <label className="inline-flex items-center gap-2 text-xs text-dax-muted select-none py-2 max-md:min-h-[44px]">
              <input type="checkbox" checked={incluirArchivados} onChange={(e) => { setIncluirArchivados(e.target.checked); setPage(0) }} />
              Incluir archivados
            </label>
            {soloSinSucursal && (
              <button type="button" onClick={() => setSoloSinSucursal(false)} className="dax-btn-ghost text-xs" title="Quitar filtro">
                <i className="fa-solid fa-xmark" aria-hidden="true" /> Sin sucursal
              </button>
            )}
          </>
        )}
```

**4m. Tarjetas (teléfono).** En el `<TarjetaFila` del producto (vista lista en teléfono), en `datos={[…]}` añadir tras la entrada `Existencia`:

```tsx
                      ...(catalogo ? [{ etiqueta: 'Aprobación', valor: <EstadoAprobacion p={p} /> }] : []),
```

y cambiar `acciones={canEdit ? <AccionesDeFila p={p} onEditar={openEdit} conTexto /> : undefined}` por:

```tsx
                    acciones={canEdit ? <AccionesDeFila p={p} onEditar={openEdit} conTexto catalogo={catalogo} conMatriz={!unaSolaSucursal} onAccion={correrAccion} /> : undefined}
```

**4n. Tabla.** En `<thead>`, después de `<th>Estado</th>` añadir `{catalogo && <th>Aprobación</th>}`. Cambiar `const colCount = 6 + (canEdit ? 1 : 0)` por `const colCount = 6 + (catalogo ? 1 : 0) + (canEdit ? 1 : 0)`. Después del `<td>` que contiene `<EstadoDeFila p={p} />` añadir:

```tsx
                        {catalogo && <td><EstadoAprobacion p={p} /></td>}
```

y cambiar `<AccionesDeFila p={p} onEditar={openEdit} />` por:

```tsx
                            <AccionesDeFila p={p} onEditar={openEdit} catalogo={catalogo} conMatriz={!unaSolaSucursal} onAccion={correrAccion} />
```

**4o. Modales.** Después del bloque `{editor && (<Modal …><FormularioProducto … /></Modal>)}` añadir:

```tsx
      {matrixProduct && (
        <ProductBranchMatrix
          product={matrixProduct}
          onClose={() => setMatrixProduct(null)}
          onSaved={recargarCatalogo}
        />
      )}
      {auditProduct && (
        <ProductAuditDrawer product={auditProduct} onClose={() => setAuditProduct(null)} />
      )}
```

Run: `cd frontend && npx vitest run src/pages/inventory --reporter=dot && npx tsc --noEmit -p tsconfig.json`
Expected: todo verde (ProductsCatalogo 5, ProductsBasico 4, Inventory 6, el resto igual); tsc limpio.

- [ ] **Step 5: Baja de `AdminCatalog`, redirects, referencias**

```bash
git rm frontend/src/pages/core/AdminCatalog.tsx
```

`frontend/src/App.tsx`:
1. Borrar `const AdminCatalog    = lazy(() => import('./pages/core/AdminCatalog').then(m => ({ default: m.AdminCatalog })))`.
2. Sustituir el bloque desde el comentario `{/* Admin / Core — Track 3 (POS bug-fix): cajero tiene control` hasta `<Route path="admin/products/new" element={<Navigate to="/products/new?volver=/admin/catalog" replace />} />` (inclusive) por:

```tsx
          {/* El Catálogo del admin vive en /products desde la Fase 3 (cifras, aprobación y
              archivado para HQ en perfil completo); la URL vieja y su alta redirigen. */}
          <Route path="admin/catalog" element={<RedirigirConQuery a="/products" />} />
          <Route path="admin/products/new" element={<Navigate to="/products/new" replace />} />
```

3. En el comentario del Scanner, cambiar `Mismo guard que admin/catalog y products/:id/edit:` por `Mismo guard que products/:id/edit:`.

`frontend/src/pages/menu/MenuVisual.tsx` línea 92: `<Link to="/admin/catalog"` → `<Link to="/products"`.
`frontend/src/pages/home/PresetHome.tsx` línea 402: `ctaUrl="/admin/catalog"` → `ctaUrl="/products"`.
`frontend/src/pages/products/ProductForm.tsx` línea 8: ` * Se llega desde el Catálogo del admin con `?volver=/admin/catalog`.` → ` * Acepta `?volver=/ruta` para regresar a quien la abrió (por defecto, `/products`).`
`frontend/src/pages/products/__tests__/volver.test.ts` líneas 9-10: cambiar `/admin/catalog` por `/hq/branches` y `%2Fadmin%2Fcatalog%3Fq%3D1` / `/admin/catalog?q=1` por `%2Fhq%2Fbranches%3Fq%3D1` / `/hq/branches?q=1` (la función es pura; solo se quita la referencia a la ruta borrada).

- [ ] **Step 6: Guardias**

`frontend/src/__tests__/coloresPorTokens.test.ts`: en `PENDIENTES` quitar `'pages/core/AdminCatalog.tsx'` (línea 22) y `'pages/core/catalogActions.ts'` (línea 23); en `LIMPIOS` la línea de la Fase 3 queda `'pages/sales/SalesHistory.tsx', 'pages/sales/Returns.tsx', 'pages/inventory/Inventory.tsx', 'pages/core/catalogActions.ts',`.

`frontend/src/pages/__tests__/responsivoOla2.test.ts`: quitar `'core/AdminCatalog.tsx'` de `PAGINAS` (línea 8) y de `SIN_TARJETA_FILA` (línea 12, que queda `['hq/HQValorInventario.tsx']`).

- [ ] **Step 7: Correr**

Run: `cd frontend && npx vitest run --reporter=dot 2>&1 | tail -6 && npx tsc --noEmit -p tsconfig.json`
Expected: toda la suite verde; tsc limpio.

Run: `git grep -n "AdminCatalog\|admin/catalog" -- 'frontend/src' ':!*.test.*'`
Expected: exactamente estos archivos y ninguno más: `App.tsx` (el comentario «El Catálogo del admin vive en /products…» y la ruta `path="admin/catalog" element={<RedirigirConQuery a="/products" />}`), `pages/core/catalogActions.ts` (comentario «antes `/admin/catalog`»), `components/layout/navConfig.ts` (ítem «Catálogo», grupo y `ROLE_ROUTES`, que limpia la Tarea 5) y `components/layout/navPerfilBasico.ts` (que limpia la Tarea 5). Un `lazy(() => import('./pages/core/AdminCatalog'))` o un `<Link to="/admin/catalog"` es un fallo.

- [ ] **Step 8: Commit**

```bash
git add -A frontend/src/pages/inventory/Products.tsx frontend/src/pages/core/catalogActions.ts \
  frontend/src/pages/core/__tests__/catalogActions.test.ts frontend/src/api/products.ts \
  frontend/src/pages/inventory/__tests__/ProductsCatalogo.test.tsx frontend/src/pages/inventory/__tests__/ProductsBasico.test.tsx \
  frontend/src/pages/core/AdminCatalog.tsx frontend/src/App.tsx frontend/src/pages/menu/MenuVisual.tsx \
  frontend/src/pages/home/PresetHome.tsx frontend/src/pages/products/ProductForm.tsx frontend/src/pages/products/__tests__/volver.test.ts \
  frontend/src/__tests__/coloresPorTokens.test.ts frontend/src/pages/__tests__/responsivoOla2.test.ts
git commit -m "feat(productos): /products absorbe el Catálogo del admin (cifras, aprobación, archivar, duplicar, restaurar) y /admin/catalog redirige

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 5: Menú del administrador, `ROLE_ROUTES`, perfil básico y guardia de fusiones

**Files:**
- Modify: `frontend/src/components/layout/navConfig.ts:29-66, 79-138, 140-151, 181-186`
- Modify: `frontend/src/components/layout/navPerfilBasico.ts:16-31`
- Modify: `frontend/src/copy/branchCopy.ts:69` (`sales: 'Mis ventas'` → `sales: 'Ventas'`; ninguna prueba lo asevera)
- Modify: `frontend/src/components/layout/__tests__/navConfig.test.ts:77-103, 119-125`, `frontend/src/components/layout/__tests__/navPerfilBasico.test.ts:53, 65`, `frontend/src/components/layout/__tests__/navPerfilPlan.test.ts:22-26, 89`
- Create: `frontend/src/__tests__/fusionesAdmin.test.ts`

**Interfaces:**
- Consumes: todas las fusiones (Tareas 1-4) ya hechas: `App.tsx` sin `HQSalesLog|HQReturns|HQInventory|AdminCatalog` y con los cuatro `RedirigirConQuery`.
- Produces: `HQ_NAV_GROUPS` con los 9 grupos de la spec §4.2; `ALL_NAV` sin `/hq/sales`, `/hq/returns`, `/hq/inventory`, `/admin/catalog` y con `/sales` rotulado «Ventas»; `ROLE_ROUTES.ADMINISTRADOR/DUEÑO` con `/returns` (ya desde la Tarea 2) e `/inventory`; `OCULTAS_BASICO_HQ` con `/returns` (Tarea 2) e `/inventory` y sin las fusionadas. `rutasPerezosas.test.ts` no cambia: los `lazy()` borrados nunca estuvieron registrados y la fase no añade ninguno.

Decisiones: `/returns` sigue **sin** `module:` y `/inventory` **sin** `hideForGastro` (los ítems HQ que se borran los tenían): un solo ítem sirve a todos los roles y giros, y la prueba existente «la operación diaria sigue sin `module:`» lo exige para `/returns`. El rótulo «Mis ventas» pasa a «Ventas» también en `copy/branchCopy.ts` (`pages.sales`, el Cockpit de la cajera): una pantalla, un nombre.

- [ ] **Step 1: Pruebas (fallan)**

En `frontend/src/components/layout/__tests__/navConfig.test.ts`, sustituir el `describe('los grupos del menú', …)` completo (líneas 77-103) por:

```ts
describe('los grupos del menú', () => {
  it('el menú del admin tiene los grupos y el orden de la Fase 3 (spec §4.2), sin «Mi tienda» ni «Caja»', () => {
    expect(HQ_NAV_GROUPS.map((g) => g.header)).toEqual([
      'Operación', 'Ventas', 'Catálogo', 'Inventario', 'Compras', 'Clientes', 'Restaurante', 'Organización', 'Inteligencia',
    ])
    const grupo = (h: string) => HQ_NAV_GROUPS.find((g) => g.header === h)?.urls
    expect(grupo('Operación')).toEqual(['/hq/operations', '/hq/reports-hub', '/hq/valor-inventario'])
    expect(grupo('Ventas')).toEqual(['/sales', '/returns', '/cash-history', '/quotes', '/quotes/new', '/seguimiento'])
    expect(grupo('Catálogo')).toEqual(['/products', '/departments', '/brands', '/labels'])
    expect(grupo('Inventario')).toEqual(['/inventory', '/inventory/conteos', '/scanner', '/logistics', '/boxes'])
    expect(grupo('Compras')).toEqual(['/purchases', '/expenses', '/purchasing'])
    expect(grupo('Clientes')).toEqual(['/customers', '/appointments', '/commissions', '/memberships'])
    expect(grupo('Restaurante')).toEqual(['/menu', '/tables', '/mobile/comanda', '/kitchen', '/recipes', '/meseros', '/bar/bottles'])
    expect(grupo('Organización')).toEqual(['/organization', '/hq/branches', '/users', '/hr', '/printer-settings'])
    expect(grupo('Inteligencia')).toEqual(['/ai'])
  })

  it('Ventas, Devoluciones, Productos e Inventario son un solo ítem con la URL corta', () => {
    const urls = menu('ADMINISTRADOR', BOUTIQUE)
    expect(urls).toEqual(expect.arrayContaining(['/sales', '/returns', '/products', '/inventory']))
    for (const u of ['/hq/sales', '/hq/returns', '/hq/inventory', '/admin/catalog']) expect(urls).not.toContain(u)
    expect(ALL_NAV.filter((n) => n.label === 'Ventas')).toHaveLength(1)
    expect(ALL_NAV.filter((n) => n.label === 'Devoluciones')).toHaveLength(1)
    expect(ALL_NAV.filter((n) => n.label === 'Inventario')).toHaveLength(1)
    expect(rolesConAcceso('/inventory')).toEqual(expect.arrayContaining(['ADMINISTRADOR', 'DUEÑO']))
    expect(rolesConAcceso('/returns')).toEqual(expect.arrayContaining(['ADMINISTRADOR', 'DUEÑO', 'GERENTE', 'CAJERO']))
  })

  it('la cajera encuentra Clientes en su propio grupo, no en «Más»', () => {
    const grupo = BRANCH_NAV_GROUPS.find((g) => g.urls.includes('/customers'))
    expect(grupo?.header).toBe('Clientes')
  })

  it('el corte de caja vive en Ventas y ya no cae en «Más»', () => {
    const grupo = HQ_NAV_GROUPS.find((g) => g.urls.includes('/cash-history'))
    expect(grupo?.header).toBe('Ventas')
  })

  it('ninguna URL está en dos grupos (se pintaría dos veces)', () => {
    for (const grupos of [HQ_NAV_GROUPS, BRANCH_NAV_GROUPS]) {
      const urls = grupos.flatMap((g) => g.urls)
      expect(new Set(urls).size).toBe(urls.length)
    }
  })

  it('el ítem del corte de caja se llama «Corte de caja»', () => {
    expect(ALL_NAV.find((n) => n.url === '/cash-history')?.label).toBe('Corte de caja')
  })
})
```

Y en `describe('el título de la barra superior', …)` sustituir la prueba «usa el rótulo del menú para las pantallas que antes tenían dos nombres» (líneas 119-125) por:

```ts
  it('usa el rótulo del menú para las pantallas que antes tenían dos nombres', () => {
    expect(routeTitle('/inventory')).toBe('Inventario')
    expect(routeTitle('/sales')).toBe('Ventas')
    expect(routeTitle('/products')).toBe('Productos')
    expect(routeTitle('/cash-history')).toBe('Corte de caja')
    expect(routeTitle('/printer-settings')).toBe('Impresora')
  })
```

En `frontend/src/components/layout/__tests__/navPerfilBasico.test.ts`: línea 53 `not.toContain('/hq/inventory')` → `not.toContain('/inventory')`; línea 65 `rolesConAcceso('/hq/inventory')` → `rolesConAcceso('/inventory')`. Añadir dentro del `describe`:

```ts
  it('Fase 3: en básico la dueña no ve Inventario ni Devoluciones (fusionadas), pero sí Ventas y Productos', () => {
    const urls = menu('ADMINISTRADOR', 'basico')
    expect(urls).not.toContain('/inventory')
    expect(urls).not.toContain('/returns')
    expect(urls).toContain('/sales')
    expect(urls).toContain('/products')
    expect(menu('ADMINISTRADOR', 'completo', ULTRA)).toEqual(expect.arrayContaining(['/inventory', '/returns']))
  })
```

En `frontend/src/components/layout/__tests__/navPerfilPlan.test.ts`: sustituir `DIARIO_ADMIN` (líneas 22-26) por:

```ts
const DIARIO_ADMIN = [
  '/hq/operations', '/hq/reports-hub', '/sales', '/products', '/labels', '/printer-settings',
  '/cash-history', '/returns', '/inventory',
  '/users', '/hq/branches', '/organization',
]
```

y en la línea 89 `rolesConAcceso('/hq/inventory')` → `rolesConAcceso('/inventory')`.

Crear `frontend/src/__tests__/fusionesAdmin.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ALL_NAV, HQ_NAV_GROUPS, ROLE_ROUTES } from '../components/layout/navConfig'
import { OCULTAS_BASICO_HQ } from '../components/layout/navPerfilBasico'

/**
 * Fase 3 del admin (spec 2026-10-23 §4, criterio §8.3): ningún módulo del admin
 * repetido; las URL viejas redirigen conservando la consulta. Si una fusión se
 * deshace o alguien vuelve a enlazar `/hq/sales`, esta guardia lo dice.
 */
const raiz = resolve(__dirname, '..')
const src = (p: string) => readFileSync(resolve(raiz, p), 'utf8')
const FUSIONADAS = ['/hq/sales', '/hq/returns', '/hq/inventory', '/admin/catalog']
const BORRADOS = ['pages/hq/HQSalesLog.tsx', 'pages/hq/HQReturns.tsx', 'pages/hq/HQInventory.tsx', 'pages/core/AdminCatalog.tsx']

describe('Fase 3 del admin: ningún módulo repetido', () => {
  it('las pantallas HQ fusionadas ya no existen', () => {
    for (const f of BORRADOS) expect(existsSync(resolve(raiz, f)), f).toBe(false)
  })

  it('App.tsx redirige las cuatro URL viejas conservando la consulta y no carga los componentes borrados', () => {
    const app = src('App.tsx')
    expect(app).not.toMatch(/HQSalesLog|HQReturns|HQInventory|AdminCatalog/)
    expect(app).toMatch(/path="sales" element=\{<RedirigirConQuery a="\/sales" \/>\}/)
    expect(app).toMatch(/path="returns" element=\{<RedirigirConQuery a="\/returns" \/>\}/)
    expect(app).toMatch(/path="inventory" element=\{<RedirigirConQuery a="\/inventory" \/>\}/)
    expect(app).toMatch(/path="admin\/catalog" element=\{<RedirigirConQuery a="\/products" \/>\}/)
  })

  it('ni el menú, ni los permisos, ni el perfil básico nombran una URL fusionada', () => {
    const urls = ALL_NAV.map((n) => n.url)
    const grupos = HQ_NAV_GROUPS.flatMap((g) => g.urls)
    const permisos = Object.values(ROLE_ROUTES).flat()
    for (const u of FUSIONADAS) {
      expect(urls, u).not.toContain(u)
      expect(grupos, u).not.toContain(u)
      expect(permisos, u).not.toContain(u)
      expect(OCULTAS_BASICO_HQ, u).not.toContain(u)
    }
  })

  it('ninguna pantalla enlaza a una URL fusionada', () => {
    for (const f of ['pages/hq/Inicio.tsx', 'components/layout/Sidebar.tsx', 'pages/menu/MenuVisual.tsx', 'pages/home/PresetHome.tsx']) {
      expect(src(f), f).not.toMatch(/\/hq\/(sales|returns|inventory)|\/admin\/catalog/)
    }
  })
})
```

Run: `cd frontend && npx vitest run src/components/layout src/__tests__/fusionesAdmin.test.ts --reporter=dot`
Expected: fallan `navConfig.test` (grupos), `navPerfilBasico.test`, `navPerfilPlan.test` y `fusionesAdmin` («ni el menú, ni los permisos…»).

- [ ] **Step 2: `navConfig.ts`**

Sustituir el bloque desde el comentario `// Grupos del menú HQ/admin. Los items no listados caen en "Más"…` hasta `export const DEFAULT_GROUP_COLOR = 'var(--sb-mod-violet)'` (líneas 29-66) por:

```ts
// Grupos del menú HQ/admin (spec 2026-10-23 §4.2, Fase 3). Los ítems no listados
// caen en "Más" (no se ocultan). Ventas, Devoluciones, Productos e Inventario son
// una sola pantalla en la URL corta: las de HQ (/hq/sales, /hq/returns,
// /hq/inventory, /admin/catalog) solo redirigen. Cobrar (/pos) no está aquí:
// el punto de venta es de la cajera (ver ROLE_ROUTES.ADMINISTRADOR).
export const HQ_NAV_GROUPS: { header: string; urls: string[] }[] = [
  { header: 'Operación',    urls: ['/hq/operations', '/hq/reports-hub', '/hq/valor-inventario'] },
  { header: 'Ventas',       urls: ['/sales', '/returns', '/cash-history', '/quotes', '/quotes/new', '/seguimiento'] },
  { header: 'Catálogo',     urls: ['/products', '/departments', '/brands', '/labels'] },
  { header: 'Inventario',   urls: ['/inventory', '/inventory/conteos', '/scanner', '/logistics', '/boxes'] },
  { header: 'Compras',      urls: ['/purchases', '/expenses', '/purchasing'] },
  { header: 'Clientes',     urls: ['/customers', '/appointments', '/commissions', '/memberships'] },
  { header: 'Restaurante',  urls: ['/menu', '/tables', '/mobile/comanda', '/kitchen', '/recipes', '/meseros', '/bar/bottles'] },
  { header: 'Organización', urls: ['/organization', '/hq/branches', '/users', '/hr', '/printer-settings'] },
  { header: 'Inteligencia', urls: ['/ai'] },
]

// Color de acento por grupo — identidad de módulo en el sidebar. El ícono se
// tiñe con el color del grupo; el ítem activo lo usa para el riel lateral, el
// resplandor y el relleno suave. Los encabezados de sección y las etiquetas
// inactivas se quedan neutros. Los matices viven en index.css (--sb-mod-*),
// no como hex sueltos aquí.
export const GROUP_COLOR: Record<string, string> = {
  // Grupos HQ (admin)
  'Operación': 'var(--sb-mod-violet)', 'Catálogo': 'var(--sb-mod-green)',
  'Ventas': 'var(--sb-mod-blue)', 'Inventario': 'var(--sb-mod-amber)',
  'Compras': 'var(--sb-mod-teal)', 'Clientes': 'var(--sb-mod-rose)',
  'Organización': 'var(--sb-mod-cyan)', 'Inteligencia': 'var(--sb-mod-indigo)',
  'Restaurante': 'var(--sb-mod-orange)', 'Más': 'var(--sb-mod-slate)',
  'Móvil': 'var(--sb-mod-blue)',
  // Grupos de sucursal
  'Mi día': 'var(--sb-mod-violet)', 'Mi turno': 'var(--sb-mod-green)',
  'Reportes': 'var(--sb-mod-indigo)', 'Configuración': 'var(--sb-mod-slate)',
}
export const DEFAULT_GROUP_COLOR = 'var(--sb-mod-violet)'
```

En `ALL_NAV`:
- Borrar las cuatro líneas de `/admin/catalog` (label «Catálogo», sort 3), `/hq/sales` («Ventas», sort 6), `/hq/returns` («Devoluciones», sort 7) y `/hq/inventory` («Existencias», sort 14).
- Cambiar `{ label: 'Mis ventas',        short: 'HST', icon: 'fa-history',             url: '/sales',            group: 'pos',  sort: 2  },` por
  `{ label: 'Ventas',            short: 'VTA', icon: 'fa-receipt',             url: '/sales',            group: 'pos',  sort: 2  },`.
- En el comentario del glosario (líneas 75-78) añadir una línea: `// Fase 3 (2026-10-25): /sales, /returns, /products e /inventory sirven a todos los roles; su ítem es uno.`

Sustituir el comentario y las dos primeras entradas de `ROLE_ROUTES` (líneas 141-151; la Tarea 2 ya insertó `'/returns'` tras `'/sales'` en ambas, y este es el resultado final) por:

```ts
  // `/sales`, `/products`, `/printer-settings`, `/returns` e `/inventory` entran al
  // menú del admin: desde la Fase 3 son las únicas pantallas de ventas, catálogo,
  // devoluciones e inventario (las de HQ redirigen aquí).
  //
  // `/pos` NO está en la lista del administrador (sí en la del dueño): cobrar
  // es de la cajera. Una venta capturada por el admin cae en la caja del
  // admin, no en la de quien está en el mostrador, y hubo que mover ventas a
  // mano por eso. El backend sigue aceptando al admin en `create_sale` (se usa
  // para capturar ventas históricas por API); esto es solo la navegación.
  ADMINISTRADOR:    ['/sales','/returns','/products','/inventory','/printer-settings','/labels','/mobile/owner','/cash-history','/hq/operations','/hq/reports-hub','/hq/valor-inventario','/scanner','/inventory/conteos','/departments','/organization','/users','/customers','/hq/branches','/brands','/hr','/hr/me','/logistics','/boxes','/quotes','/quotes/new','/seguimiento','/purchases','/expenses','/appointments','/commissions','/memberships','/recipes','/ai','/purchasing','/tables','/kitchen','/meseros','/bar/bottles','/menu','/mobile/comanda'],
  DUEÑO:            ['/pos','/sales','/returns','/products','/inventory','/printer-settings','/labels','/mobile/owner','/cash-history','/hq/operations','/hq/reports-hub','/hq/valor-inventario','/scanner','/inventory/conteos','/customers','/hr/me','/logistics','/boxes','/quotes','/quotes/new','/seguimiento','/purchases','/expenses','/appointments','/commissions','/memberships','/recipes','/ai','/purchasing','/tables','/kitchen','/meseros','/bar/bottles','/menu','/mobile/comanda'],
```

En `EXTRA_TITLES` borrar `'/admin/products/new': 'Nuevo producto',` (la ruta redirige antes de pintar título).

En `frontend/src/copy/branchCopy.ts` línea 69: `    sales: 'Mis ventas',` → `    sales: 'Ventas',`.

- [ ] **Step 3: `navPerfilBasico.ts`**

Sustituir las líneas 16-31 (ya con el `'/returns'` que añadió la Tarea 2) por:

```ts
/** Cajera y gerente: Cobrar · Ventas · Corte · Productos · Impresora · Mi día. */
export const OCULTAS_BASICO_SUCURSAL: readonly string[] = [
  '/returns',             // se llega desde el ticket en Ventas y desde el POS
  '/labels', '/scanner', '/customers', '/hr/me',
  '/reports', '/hq/valor-inventario',   // gerente
]

/** Dueña: Inicio · Ventas · Corte · Productos · Reportes · Empresa · Usuarios · Impresora. */
export const OCULTAS_BASICO_HQ: readonly string[] = [
  '/departments', '/brands', '/labels', '/scanner',
  '/customers', '/hq/branches', '/inventory', '/inventory/conteos',
  '/returns',                          // Ventas (/sales) devuelve por ticket; Productos (/products) ya se ve en básico
  '/hq/valor-inventario',              // entra como tarjeta en el Inicio básico
  '/hr/me', '/ai',
  '/quotes', '/quotes/new', '/seguimiento', '/purchases', '/expenses', '/purchasing',
]
```

- [ ] **Step 4: Correr**

Run: `cd frontend && npx vitest run --reporter=dot 2>&1 | tail -6 && npx tsc --noEmit -p tsconfig.json`
Expected: toda la suite verde (`navPerfilBasico` «administradora: exactamente ocho entradas» sigue en 8: `/inventory` y `/returns` se esconden en básico); tsc limpio.

Run: `git grep -n "/hq/sales\|/hq/returns\|/hq/inventory\|/admin/catalog" -- 'frontend/src' ':!*.test.*'`
Expected: solo `App.tsx` (los cuatro `RedirigirConQuery` y su comentario) y el comentario de cabecera de `pages/core/catalogActions.ts`. Si aparece `navConfig.ts`, `navPerfilBasico.ts`, `Sidebar.tsx`, `Inicio.tsx`, `MenuVisual.tsx` o `PresetHome.tsx`, falta una edición. Con pruebas incluidas se suman solo `RedirigirConQuery.test.tsx`, `fusionesAdmin.test.ts` y la aserción de básico de `Inicio.test.tsx`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout/navConfig.ts frontend/src/components/layout/navPerfilBasico.ts \
  frontend/src/copy/branchCopy.ts \
  frontend/src/components/layout/__tests__/navConfig.test.ts frontend/src/components/layout/__tests__/navPerfilBasico.test.ts \
  frontend/src/components/layout/__tests__/navPerfilPlan.test.ts frontend/src/__tests__/fusionesAdmin.test.ts
git commit -m "feat(menu): grupos de la Fase 3 (sin Mi tienda ni Caja), un ítem por pantalla, /returns e /inventory para admin y dueño

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 6: Documentación — vistas, modo básico, RBAC, receta en CLAUDE.md y estado de la spec

**Files:**
- Modify: `docs/FRONTEND_VIEWS.md` (§1 gating, §1 tema, índice maestro, secciones `/sales`, `/returns`, Inicio, las tres de HQ, `/products`, `/inventory`, `/admin/catalog`, hallazgo 6)
- Modify: `docs/modo-basico.md` (filas «Menú de la dueña» y «Productos» de la tabla «Qué esconde»)
- Modify: `docs/RBAC.md` (§3 A «Gating por rol»)

> Los números de línea de abajo son los de `main` 4321268e y solo orientan: **ubica cada edición por el texto citado** (`grep -n "<texto>" docs/FRONTEND_VIEWS.md`), porque las Tareas 1-5 no tocan estos docs pero cualquier `fix(...)` intermedio pudo moverlos.
- Modify: `CLAUDE.md` §5 (nueva receta tras «Esconder algo en modo básico»)
- Modify: `docs/superpowers/specs/2026-10-23-admin-precision-inicio-fusiones-design.md:3`

**Interfaces:** ninguna de código. Esta tarea documenta lo que las Tareas 1-5 dejaron; no toca `frontend/` ni `app/`. Verificación: `app/main.py` **no cambia** (confirmado al planear: el redirect `/hq/sales → /hq/sales-log` se quitó en la Fase 1, commit 97fc2e72; `tests/test_sales_rutas.py::test_hq_sales_no_redirige_a_ruta_muerta` lo vigila y el catch-all de la SPA sirve `/hq/*` y `/admin/*`).

- [ ] **Step 1: `docs/FRONTEND_VIEWS.md`**

1. Línea 20 (Gating en dos capas, punto 1): cambiar «`ROLE_ROUTES` en `components/layout/Sidebar.tsx`» por «`ROLE_ROUTES` en `components/layout/navConfig.ts` (`rolesConAcceso` deriva de la misma lista que dibuja el menú; `RutaPorRol` lo aplica)».
2. Línea 31: tras «…más MobileOwnerDashboard» añadir «; desde la Fase 3 (2026-10-25) también Ventas (`sales/SalesHistory`), Devoluciones (`sales/Returns`) e Inventario (`inventory/Inventory`), reescritas solo con tokens al fusionar sus pares HQ».
3. Índice maestro — sustituir estas filas:
   - `| /sales | sales/SalesHistory | Gerente, Cajero | pos |` → `| /sales | sales/SalesHistory (Ventas: cajera y gerente ven su sucursal; admin y dueño toda la org, con selector si hay más de una sucursal que vende) | Todos | pos |`
   - `| /returns | sales/Returns | Gerente, Cajero | returns |` → `| /returns | sales/Returns (cajera: ReturnsBranchView; gerente, admin y dueño: bandeja con periodo; admin y dueño con selector de sucursal) | Todos | returns |`
   - Borrar las filas de `/hq/sales`, `/hq/returns` y `/hq/inventory`; en su lugar, tras la fila de `/hq/reports-hub`, añadir: `| /hq/sales, /hq/returns, /hq/inventory, /admin/catalog | redirigen (RedirigirConQuery, conserva ?…) a /sales, /returns, /inventory, /products — Fase 3, 2026-10-25 | — | — |`
   - `| /products, /new, /:id/edit | inventory/Products, products/ProductForm | Admin, Dueño, Gerente, Cajero | catalog |` → `| /products, /new, /:id/edit | inventory/Products (Productos; para admin y dueño en perfil completo trae las cifras, aprobación y archivado del Catálogo viejo), products/ProductForm | Admin, Dueño, Gerente, Cajero | catalog |`
   - `| /inventory | inventory/Inventory | — | inventory |` → `| /inventory | inventory/Inventory (Inventario: kardex y ajuste para todos; costo e importes solo admin y dueño) | Admin, Dueño (menú); gerente y cajera llegan desde «Ajustar» del editor de variantes | inventory |`
   - Borrar la fila `| /admin/catalog | core/AdminCatalog | Admin | catalog |`.
4. Sustituir la sección `### /sales — Historial de ventas 📱` (líneas 199-205) por:

```markdown
### `/sales` — Ventas 📱
- **Archivo:** `pages/sales/SalesHistory.tsx`. Sustituye también a `hq/HQSalesLog.tsx` (borrada 2026-10-25, Fase 3 del admin; `/hq/sales` redirige con su consulta).
- **Propósito:** ventas por periodo (`Hoy · Ayer · 7 días · 30 días · Este mes` + rango, `pages/reports/presetsReportes.ts`) con cifras (`KpiCard`), buscador de folio/cliente, detalle en `ui/Modal`, reimprimir (PIN de supervisor si el backend lo pide) y devolver.
- **Quién la ve:** todos. Cajera y gerente ven su sucursal (el backend la impone); admin y dueño toda la organización y, con más de una sucursal que vende (`useSucursalesVendibles`), un selector y la columna «Sucursal». `branch_id` solo viaja cuando eligen una.
- **Datos/API:** `salesApi.list/getStats`, `printerApi.getTicketBase64/printViaAgent`, `organizationApi.getBranches` (solo HQ).
- **Notas:** por defecto solo PAID/REFUNDED_*/CANCELLED (casilla «Incluir abiertas/borradores»). Paginación de 100. Solo tokens `dax-*`.
```

5. Sustituir la sección `### /returns — Devoluciones 📱` (líneas 221-227) por:

```markdown
### `/returns` — Devoluciones 📱
- **Archivo:** `pages/sales/Returns.tsx`. Sustituye también a `hq/HQReturns.tsx` (borrada 2026-10-25; `/hq/returns` redirige).
- **Propósito:** cajera → `ReturnsBranchView` (asistente). Gerente, admin y dueño → bandeja: Pendientes (siempre completos) e Historial acotado por periodo (`presetsReportes`, arranca en 30 días); detalle en `ui/Modal` con Aprobar/Rechazar (motivo opcional); reembolso en efectivo alto confirmado con `confirm()` y `force=true` (R-3).
- **Quién la ve:** todos — módulo `returns`. `CAN_APPROVE` = Admin/Dueño/Gerente. Admin y dueño con más de una sucursal que vende ven el selector y la columna «Sucursal». El gerente no tiene selector pero sí la columna: `GET /returns/` lo trata como rol de oficina (`HQ_ROLES` de `metricas_ventas.py`) y le devuelve toda la organización, como antes de la fusión. El ítem de menú sigue sin `module:` a propósito: un solo ítem para todos los roles.
- **Datos/API:** `returnsApi.list/approve/reject`, `organizationApi.getBranches` (solo HQ).
- **Notas:** estados con `estadoDevolucion` («Por aprobar», «Aprobada», «Rechazada»). **Gotcha:** hooks tras early-return (`Returns` → `ReturnsAdminView`).
```

6. Línea 245 (Inicio, Responsivo): `/hq/inventory?q=<sku>&variant=<id>` → `/inventory?q=<sku>&variant=<id>`.
7. Borrar las tres secciones `### /hq/sales — Ventas 📱`, `### /hq/returns — Devoluciones 📱` y `### /hq/inventory — Existencias 📱` (líneas 254-268) y en su lugar dejar:

```markdown
> **Fase 3 del admin (2026-10-25):** Ventas, Devoluciones y Existencias de HQ se fusionaron en `/sales`, `/returns` e `/inventory` (§3 y §5); el Catálogo del admin, en `/products`. Las URL `/hq/sales`, `/hq/returns`, `/hq/inventory` y `/admin/catalog` redirigen conservando la consulta (`components/layout/RedirigirConQuery.tsx`, en `App.tsx`). Guardia: `src/__tests__/fusionesAdmin.test.ts`.
```

8. Sustituir la sección `### /products — Catálogo / consulta de productos 📱` (líneas 288-295) por:

```markdown
### `/products` — Productos 📱
- **Archivo:** `pages/inventory/Products.tsx`. Desde la Fase 3 (2026-10-25) absorbe `core/AdminCatalog.tsx` (borrado; `/admin/catalog` redirige).
- **Propósito:** vista central del catálogo: buscar/filtrar, lista o cuadrícula, crear/editar (`FormularioProducto` en `Modal`), importar Excel/CSV, etiquetas CSV, códigos de barras. Para admin y dueño **en perfil completo** (`catalogo = isHQ && !modoBasico`): cifras (`components/catalog/CatalogKpis`), filtro por marca y por aprobación, «Incluir archivados», «Exportar» (Excel con los filtros), distintivo de aprobación por fila y acciones por producto (`pages/core/catalogActions.ts`: matriz de sucursales —solo con varias—, aprobar/rechazar pendientes, historial, editar, duplicar, archivar/restaurar).
- **Quién la ve:** Admin, Dueño, Gerente, Cajero — módulo `catalog`. Roles de sucursal ven `ProductsBranchView`.
- **Datos/API:** `productsApi.list/search/getDepartments/getBrands/catalogKpis/approve/reject/duplicate/archive/restore/downloadTemplate/uploadProducts/barcodesMissingCount/assignMissingBarcodes/downloadLabelsCsv`.
- **Componentes clave:** `ImportModal`, `FormularioProducto`, `CatalogKpis`, `ProductBranchMatrix`, `ProductAuditDrawer`.
- **Notas:** en básico no se pinta ni consulta nada del catálogo viejo (`docs/modo-basico.md`). Refetch por `location.key`. Pendiente de tokens (`coloresPorTokens.test.ts`, `PENDIENTES`).
```

9. Sustituir la sección `### /inventory — Inventario (kardex y ajustes) 📱` (líneas 296-302) por:

```markdown
### `/inventory` — Inventario 📱
- **Archivo:** `pages/inventory/Inventory.tsx`. Desde la Fase 3 (2026-10-25) absorbe `hq/HQInventory.tsx` (borrada; `/hq/inventory` redirige con su consulta).
- **Propósito:** buscar por nombre/SKU → un renglón por variante con precio, existencia e importe a venta; kardex (con quién lo movió) y ajuste por sucursal (`ui/Modal`). Para admin y dueño (`esRolHq`): costo, importe a costo, totales de lo listado y la casilla «Solo sin costo». Acepta `?q=&variant=` (el «Ajustar» del editor de variantes y los enlaces del Inicio abren esa talla).
- **Quién la ve:** admin y dueño desde el menú (grupo Inventario; el ítem no lleva `hideForGastro`, a diferencia del «Existencias» borrado: un solo ítem sirve a todos los giros); gerente y cajera llegan por enlace y ven lo mismo sin costos. La ruta no lleva `RutaPorRol` (comportamiento histórico).
- **Datos/API:** `productsApi.search`, `inventoryApi.getKardex/createAdjustment`, `organizationApi.getBranches`.
- **Notas:** **Gotcha:** la API espera variant UUID (`expandVariantRows`). Solo tokens `dax-*`.
```

10. Sustituir las secciones `### /admin/catalog — Catálogo (administración) 📱` y `### /admin/products/new — redirección` (líneas 345-356) por:

```markdown
### `/admin/catalog` y `/admin/products/new` — redirecciones
- **Archivo:** `App.tsx` (sin página propia). `/admin/catalog` → `/products` conservando la consulta (`RedirigirConQuery`); `/admin/products/new` → `/products/new`. `pages/core/AdminCatalog.tsx` se borró en la Fase 3 (2026-10-25): sus cifras, filtros y acciones viven en `/products`.
```

11. Línea 654 (hallazgo 6): quitar `/HQSalesLog` de «`<DocumentDetailModal>`/`<LineItemsTable>` (SalesHistory/Quotes/Returns/Seguimiento/HQSalesLog)».

- [ ] **Step 2: `docs/modo-basico.md`**

- Línea 33 (Menú de la dueña, columna Básico): sustituir «Catálogo, Departamentos, Marcas, Etiquetas, Escáner, Clientes, Sucursales, Inventario, Existencias, Ventas HQ, Devoluciones HQ, Valor de la tienda, Mi expediente, IA, Cotizaciones, Pedidos, Compras, Gastos» por «Departamentos, Marcas, Etiquetas, Escáner, Clientes, Sucursales, Inventario, Devoluciones, Valor de la tienda, Mi expediente, IA, Cotizaciones, Pedidos, Compras, Gastos (desde la Fase 3 del admin, 2026-10-25, Catálogo, Existencias, Ventas HQ y Devoluciones HQ ya no existen: son Productos, Inventario, Ventas y Devoluciones)».
- Línea 37 (Productos, columna Básico): sustituir «importador, plantilla, etiquetas CSV, generar códigos, rejilla» por «importador, plantilla, etiquetas CSV, generar códigos, rejilla; y todo lo del Catálogo viejo (cifras, filtro de aprobación y marca, archivados, Exportar, acciones aprobar/duplicar/archivar/restaurar/matriz/historial): `catalogo = isHQ && !modoBasico`».

- [ ] **Step 3: `docs/RBAC.md`**

En §3 A) «Gating por rol», tras el punto 1 (`ATLAS_POS_ROLE_VIEWS`…), añadir:

```markdown
   - **Frontend:** el menú y las guardas de ruta salen de `ROLE_ROUTES` (`frontend/src/components/layout/navConfig.ts`; `rolesConAcceso` + `RutaPorRol`). Desde la Fase 3 del admin (2026-10-25) ADMINISTRADOR y DUEÑO tienen `/returns` e `/inventory`, y `/hq/sales`, `/hq/returns`, `/hq/inventory` y `/admin/catalog` solo redirigen. `TEMPLATE_METADATA` de `role_permissions.py` y `app/ui/nav_registry.py` aún listan esas URL viejas: el frontend no los consume y el redirect las cubre (deuda, no bloqueante).
```

- [ ] **Step 4: Receta en `CLAUDE.md` §5**

Después de la receta «Esconder algo en modo básico» añadir:

```markdown
### Retirar una URL del admin (fusionar dos pantallas)
1. La pantalla que sobrevive absorbe lo que la otra hacía de más, gateado por rol (`esRolHq` de `frontend/src/utils/rolesHq.ts`) y, si aplica, por "más de una sucursal que vende" (`hooks/useSucursalesVendibles.ts`). `branch_id` solo viaja cuando un rol de oficina elige sucursal: el backend impone la sucursal a la cajera; al gerente según cada endpoint (`/sales/` y `/sales/stats` lo confinan, `/returns/` no: `HQ_ROLES` de `metricas_ventas.py` lo incluye). Revisa el router antes de decidir qué columnas enseñarle.
2. `git rm` la pantalla vieja y su `lazy()` en `App.tsx`; la ruta vieja pasa a `<RedirigirConQuery a="/nueva" />` (`components/layout/RedirigirConQuery.tsx`: conserva `?…` y `#…`). `app/main.py` no necesita redirect: la SPA sirve la ruta.
3. Quita la URL de `ALL_NAV`, `HQ_NAV_GROUPS`, `ROLE_ROUTES` y `OCULTAS_BASICO_HQ`; actualiza enlaces (`git grep -n '/ruta/vieja' -- frontend/src docs`).
4. Guardias: `__tests__/fusionesAdmin.test.ts` (añade la URL a `FUSIONADAS` y el archivo a `BORRADOS`), `coloresPorTokens` (saca el borrado de `PENDIENTES`; el reescrito va a `LIMPIOS`), `overlaysFueraDelKit` (`CONOCIDOS`), `pages/__tests__/responsivoOla2.test.ts` (`PAGINAS`), y `docs/FRONTEND_VIEWS.md`. Ejemplo completo: `docs/superpowers/plans/2026-10-25-admin-fase3-fusiones-menu.md`.
```

- [ ] **Step 5: Estado de la spec y desviación anotada en §4.1**

En `docs/superpowers/specs/2026-10-23-admin-precision-inicio-fusiones-design.md`, en la tabla de §4.1, sustituir la fila de Productos

`| `/products` Productos | `Products.tsx` | cifras de catálogo (`CatalogKpis`), filtro y acciones de aprobación, duplicar, archivar, restaurar | aprobación, archivar, restaurar |`

por

`| `/products` Productos | `Products.tsx` | cifras de catálogo (`CatalogKpis`), filtro por marca y aprobación, acciones de aprobación, duplicar, archivar, restaurar, exportar | **todo lo anterior** (decisión al implementar, 2026-10-25: duplicar, exportar y cifras también solo HQ en perfil completo; cajera y gerente siguen en `ProductsBranchView`) |`

Y en la línea 3, sustituir
`**Estado:** fases 1 y 2 implementadas (fase 2 en `feat/admin-fase2-inicio-reportes`, pendiente de fusión); fase 3 (fusiones y menú) pendiente ·`
por
`**Estado:** fases 1 y 2 en `main`; fase 3 (fusiones y menú) implementada en `feat/admin-fase3-fusiones-menu` (plan `docs/superpowers/plans/2026-10-25-admin-fase3-fusiones-menu.md`), pendiente de fusión ·`

- [ ] **Step 6: Comprobar y commit**

Run: `git grep -n "HQSalesLog\|HQReturns\|HQInventory\|AdminCatalog\|/hq/sales\|/hq/returns\|/hq/inventory\|/admin/catalog" -- docs/FRONTEND_VIEWS.md docs/modo-basico.md docs/RBAC.md CLAUDE.md`
Expected: solo las líneas escritas en esta tarea: en `FRONTEND_VIEWS.md` la fila del índice «redirigen (RedirigirConQuery…)», la nota de §4 «Fase 3 del admin», los «Sustituye también a…»/«absorbe…» de `/sales`, `/returns`, `/products`, `/inventory` y la sección «`/admin/catalog` y `/admin/products/new` — redirecciones»; en `modo-basico.md` la fila del menú de la dueña; en `RBAC.md` la nota de §3 A; en `CLAUDE.md` la receta. Cualquier fila del índice que siga mapeando `/hq/sales`, `/hq/returns`, `/hq/inventory` o `/admin/catalog` a un archivo `hq/HQ*`/`core/AdminCatalog` es un fallo.

```bash
git add docs/FRONTEND_VIEWS.md docs/modo-basico.md docs/RBAC.md CLAUDE.md \
  docs/superpowers/specs/2026-10-23-admin-precision-inicio-fusiones-design.md
git commit -m "docs(admin): vistas, modo básico y RBAC tras las fusiones de la Fase 3; receta para retirar una URL del admin

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf"
```

---

### Task 7: Verificación completa, build, presupuesto y capturas

**Files:** ninguno nuevo. Solo correcciones si algo falla (cada una se comete en un `fix(...)` propio con los trailers).

- [ ] **Step 1: Backend (sin cambios esperados)**

Run: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py --ignore=tests/test_branch_dashboard.py --ignore=tests/test_cash_close_guided.py 2>&1 | tail -3`
Expected: `1638 passed` (mismo conteo que `main` 4321268e: esta fase no toca `app/`). Incluye `tests/test_sales_rutas.py::test_hq_sales_no_redirige_a_ruta_muerta` (la SPA sirve `/hq/sales`).

- [ ] **Step 2: Frontend**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json && npx vitest run --reporter=dot 2>&1 | tail -6`
Expected: tsc limpio; toda la suite verde (1056 de `main` − 4 de `HQInventory.test` movidas + nuevas: RedirigirConQuery 3, SalesHistory 5, Returns 4, Inventory 6, ProductsCatalogo 5, catalogActions +2, navConfig/navPerfilBasico +2, fusionesAdmin 4 ≈ 1083). `rutasPerezosas > MobileLayout` puede exceder el tiempo bajo carga: si es la única roja, relanzar solo ese archivo (`npx vitest run src/__tests__/rutasPerezosas.test.ts`) y seguir.

- [ ] **Step 3: Build y presupuesto de la ruta crítica del POS**

Run: `cd frontend && npm run build 2>&1 | tail -5 && cd .. && python3 scripts/presupuesto_bundle.py --dist frontend/dist --presupuesto frontend/presupuesto_bundle.json`
Expected: build sin errores; el presupuesto pasa (`tope_bytes` 452500 sin tocar, `charts-` fuera de la precarga). Las pantallas fusionadas son chunks `lazy()` ajenos a login → POS: la ruta crítica no cambia. Si el presupuesto fallara, el culpable sería un import estático nuevo en `App.tsx` o en `posStore`/`components/pos`: no hay ninguno en este plan.

- [ ] **Step 4: Sin rastros**

Run: `git grep -n "HQSalesLog\|HQReturns\|HQInventory\|AdminCatalog" -- 'frontend/src' ':!*.test.*'`
Expected: exactamente tres líneas, todas comentarios de cabecera: `pages/sales/SalesHistory.tsx`, `pages/sales/Returns.tsx`, `pages/inventory/Inventory.tsx`. Ningún `import`, `lazy()` ni JSX. (`app/` no cambia: `HQInventoryPage`/`HQInventoryKPIs` de `app/modules/products/schemas.py` son del endpoint `/products/hq-inventory`, ajeno a esta fase.) Luego `ls frontend/src/pages/hq` → `HQBranches.tsx HQValorInventario.tsx Inicio.tsx InicioGraficas.tsx __tests__`.

- [ ] **Step 5: Capturas (las toma el controlador con Playwright; receta en la memoria `playwright-sin-sudo-wsl`, backend SQLite de demo con los shims `timezone`/`to_char`)**

Rutas, roles, anchos y temas a capturar, en claro y oscuro, a 1440 y 390:

| Ruta | Roles | Qué mirar |
|---|---|---|
| `/sales` | admin con 2 sucursales que venden; admin con 1 tienda + 1 bodega; gerente; cajera | selector y columna «Sucursal» solo en el primero; cifras `KpiCard`; presets; detalle en Modal; a 390 tarjetas con Ver/Reimprimir/Devolver |
| `/returns` | admin (2 sucursales); gerente; cajera | selector en la cabecera solo para admin; pestañas; barra de periodo solo en Historial; cajera ve el asistente |
| `/inventory?q=<sku>&variant=<id>` | admin; gerente | kardex abierto al entrar; columnas Costo/Importe costo/totales solo admin; «Solo sin costo» solo admin; columna «Por» |
| `/products` | admin completo (count 1 y count 2); dueña FREE básico; gerente | cifras, chips de aprobación, Marca, Incluir archivados, Exportar y acciones por fila solo en admin completo; Matriz solo con count 2 |
| `/hq/sales?x=1`, `/hq/inventory?q=A&variant=v`, `/admin/catalog`, `/hq/returns` | admin | la barra de direcciones termina en `/sales?x=1`, `/inventory?q=A&variant=v`, `/products`, `/returns` |
| menú lateral (cualquier pantalla) | admin ULTRA+ completo; dueña FREE básico; cajera | grupos y orden de §4.2; básico con 8 entradas; cajera con «Ventas» en Mi turno |

Diff a 1440 contra el baseline de `main` solo para `/products` (vista de admin **básico** y de gerente: deben ser idénticas a antes salvo el rótulo del menú «Ventas»).

- [ ] **Step 6: Cierre**

Confirmar que `git status` está limpio y `git log --oneline main..HEAD` muestra los 6 commits de las Tareas 1-6 (más los `fix(...)` que hayan hecho falta). **No** hacer push ni merge: el usuario autoriza la fusión a `main` (CLAUDE.md §2) y el despliegue sale solo del push a `main`.

---

## Cobertura de la spec (revisión del plan)

| Spec | Tarea |
|---|---|
| §4.1 Ventas: base `SalesHistory` + filtro de sucursal (HQ, >1 sucursal) | Tarea 1 |
| §4.1 Devoluciones: base `Returns` + sucursal (HQ) y periodo (presets §2.1) | Tarea 2 |
| §4.1 Inventario: base `Inventory` + costo, importe, «solo sin costo», `?q=&variant=`; columnas de costo solo HQ | Tarea 3 |
| §4.1 Productos: base `Products` + `CatalogKpis`, aprobación, duplicar, archivar, restaurar; aprobación/archivar/restaurar solo HQ | Tarea 4 |
| §4.1 Borrar `HQSalesLog`, `HQReturns`, `HQInventory`, `AdminCatalog` | Tareas 1-4 (`git rm`), guardia en Tarea 5 |
| §4.1 Redirects en `App.tsx` conservando la consulta | Tarea 1 (`RedirigirConQuery` + prueba) y cada fusión; Tarea 5 (`fusionesAdmin.test.ts`) |
| §4.1 Referencias: `Inicio.tsx:41-44,176,219`, `Sidebar.tsx:17`, `MenuVisual.tsx:92`, `navPerfilBasico.ts` | Tareas 1-3 (Inicio, Sidebar), 4 (MenuVisual, PresetHome), 5 (navPerfilBasico) |
| §4.2 Grupos y orden; fuera «Mi tienda» y «Caja» y los cuatro ítems HQ | Tarea 5 |
| §4.2 `ROLE_ROUTES`: fuera las fusionadas; `/returns` e `/inventory` para ADMIN/DUEÑO | Tarea 2 (`/returns`, para que el redirect no deje fuera al admin) y Tarea 5 (`/inventory` y bajas) |
| §4.2 `OCULTAS_BASICO_HQ`: fuera las cuatro; Inventario y Devoluciones siguen ocultas como `/inventory` y `/returns` | Tarea 2 (añade `/returns`, que hoy no estaba) y Tarea 5 (bajas) |
| §4.1 Productos: duplicar y cifras sin «solo HQ» en la spec | Desviación aceptada (solo HQ en perfil completo); la Tarea 6 la escribe en la spec §4.1 |
| §4.2 `routeTitle` conserva nombres; pruebas de `components/layout/__tests__/` y `docs/FRONTEND_VIEWS.md` al día | Tareas 5 y 6 |
| §5 Lo que no cambia (POS, caja, panel móvil, plataforma, Escáner, Conteo, Etiquetas) | ninguna tarea los toca; `ProductsBranchView`/`ReturnsBranchView` intactos |
| §6 Guardias: `coloresPorTokens`, `navConfig.test`, `navPerfilBasico.test`, `botonesDelKit`, `overlaysFueraDelKit`, `rutasPerezosas` | Tareas 1-5 (`rutasPerezosas` sin cambios: no hay `lazy()` nuevos); presupuesto en Tarea 7 |
| §7 Verificación por fase (pytest, vitest, tsc, build, capturas 1440/390 claro/oscuro) | Tarea 7 |
| §8.3 Ningún módulo repetido; URL viejas redirigen | Tarea 5 (`fusionesAdmin.test.ts`), Tarea 7 paso 4 |
| §8.4 Docs y spec al día | Tarea 6 |

**Lo que la spec dice y el código contradecía (resuelto en el plan):**
- La spec apoya "más de una sucursal" en la lista de `/branches` que cargaban `HQSalesLog`/`HQReturns` (todas las sucursales); la Fase 2 ya decidió "solo las que venden" en Inicio y Reportes. El plan sigue la Fase 2 (`useSucursalesVendibles`).
- `OCULTAS_BASICO_HQ` hoy **no** contiene `/returns` y `ROLE_ROUTES` de ADMIN/DUEÑO no contiene `/inventory` ni `/returns`: el ítem «Inventario» de `ALL_NAV` nunca se veía. La Tarea 5 lo corrige como pide la spec.
- La ruta `/inventory` no lleva `RutaPorRol` (cualquier rol autenticado llega desde «Ajustar»); se conserva así y se documenta.
- `navConfig.test.ts:120` esperaba `routeTitle('/hq/inventory') === 'Existencias'`: pasa a `routeTitle('/inventory') === 'Inventario'`.
- `rutasPerezosas.test.ts` "registra los módulos nuevos que carguen con `lazy()`": esta fase no crea ninguno y los borrados nunca estuvieron ahí.
- `app/core/role_permissions.py` y `app/ui/nav_registry.py` siguen con las URL viejas (el frontend no los consume): fuera de alcance, anotado en `docs/RBAC.md`.
