# Lado administrador responsivo — ola 1 — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que las nueve pantallas que el dueño abre a diario (Inicio HQ, Ventas HQ, Mis ventas, Corte de caja, Reportes HQ, Reportes, Devoluciones HQ, Devoluciones) quepan en un teléfono de 390 px sin scroll horizontal, con tablas convertidas en tarjetas, filtros y KPIs apilados y modales en hoja inferior, sin cambiar un píxel en escritorio de 1024 px hacia arriba; y que el dueño ya no sea desviado a `/mobile/owner`.

**Architecture:** Primitivas nuevas en `frontend/src/components/ui/` (`TarjetaFila`, `ListaTarjetas`, `BarraFiltros` + `ParFechas`, `CabeceraPagina`) y `Modal.tsx` con `.dax-modal`. Cada pantalla conserva su `<table>` intacta para `≥ md` y, bajo `md`, renderiza una lista de tarjetas con `useEsTelefono()` (render condicional, no `hidden md:block`). Rejillas y filtros ganan prefijos responsivos. Verificación con Playwright en el scratchpad: capturas y comprobación de desborde en 390/768/1024 claro y oscuro, y diff pixel a pixel a 1440 contra un baseline tomado antes de tocar código.

**Tech Stack:** React 18 + TypeScript + Tailwind (utilidades con prefijos `sm/md/lg`) + tokens `--dax-*`; vitest 2 (+ `jsdom` y `@testing-library/react` como devDeps nuevas, solo para pruebas de componentes); Playwright (paquete npm en el scratchpad, chromium ya instalado en `~/.cache/ms-playwright`); backend local FastAPI sobre SQLite con `seed_demo_orgs.py` más datos de muestra insertados por ORM.

**Spec:** `docs/superpowers/specs/2026-09-30-responsivo-admin-design.md`

## Global Constraints

- **Escritorio no cambia**: de 1024 px hacia arriba cada pantalla renderiza igual que hoy. Todo lo nuevo vive detrás de `max-width` / prefijos (`sm:`, `md:`, `lg:`) o del hook `useEsTelefono()` (`< 768`). Cuando una clase ya traía `lg:` con un valor, ese valor se conserva; solo se añaden cortes inferiores.
- Cortes: `< 640` modal → hoja inferior y formularios a 1 columna; `< 768` tabla → tarjetas, cabecera apilada, KPIs a 2 columnas; `< 1024` rejillas de 3-4 → 2.
- **Render condicional** tabla/tarjetas con `useEsTelefono()` de `hooks/useIsMobile.ts`; nunca montar los dos árboles.
- **Formateos compartidos**: lo que hoy formatea la fila de la tabla (`formatCurrency`, fechas, mapas de estado, `saleLabel`, etc.) se reutiliza en la tarjeta; no se copian literales.
- Tap targets `≥ 44 px` bajo 768 (`dax-btn-icon` ya lo da a botones de icono). Toda tarjeta tocable es `<button>`; las acciones van fuera del botón.
- Tokens `--dax-*` y clases del kit (`dax-card`, `dax-badge-*`, `dax-input`, `dax-modal`, `dax-modal-footer`); nada de color nuevo.
- `main` = producción; rama `feat/responsivo-admin-ola-1`; commits locales; **push y merge solo con permiso explícito**.
- Pruebas: `cd frontend && npm test -- --run` (vitest) y `npm run build` (tsc + vite) deben pasar. Backend no se toca.
- Comentarios y nombres en español como el resto del kit (`TablaDesplazable`, `DaxCard`).
- Commits terminan con:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_014rnFXXn9to8upxnFg1bpw8
  ```
- Vite en `/mnt/d` (WSL) no detecta cambios: reiniciar el dev server antes de capturar.

## Review Focus

1. **Lista larga en teléfono** (Mis ventas con 100 filas paginadas): la lista de tarjetas no debe montar la tabla a la vez ni perder la paginación que ya existe debajo de la tabla. → Tareas 1 y 3 (test de `ListaTarjetas` con 60 ítems; la paginación se conserva fuera del condicional).
2. **Modal abierto al rotar o redimensionar** (cruza el corte `sm`): la hoja inferior y el modal centrado comparten DOM; `.dax-modal` solo cambia posición por CSS, nada se remonta. → Tarea 1 (test: `Modal` conserva su contenido tras cambiar `matchMedia`).
3. **Tarjeta con acciones y `onClick`**: tocar "Reimprimir" no debe abrir el detalle. → Tarea 1 (test de `TarjetaFila`).
4. **Cabecera con muchas acciones** (Inicio HQ: CSV, actualizar, periodos): en 390 px nada se sale del ancho y el botón primario sigue visible sin scroll. → Tarea 7 (comprobación de desborde automática) y Tarea 6.
5. **Dueño con preset `ATLAS_ONE_*` en teléfono**: al quitar el redirect debe caer en `/home`, no en `/hq/operations`. → Tarea 8 (test de `rutaInicio`).

---

### Task 0: herramientas de verificación y baseline de escritorio

Se hace **antes** de tocar código de la ola: sin el baseline a 1440 no hay forma de probar que escritorio no cambió.

**Files:**
- Create (scratchpad, no versionado): `/tmp/claude-1000/-mnt-d-Devs-atlas-one/e35ce3ce-1728-4f1c-8340-59ba97d45264/scratchpad/responsivo/` con `stack.sh`, `datos_muestra.py`, `capturas.mjs`, `diff1440.mjs`, `package.json`
- Output: `.superpowers/sdd/responsivo-ola1/baseline-1440/*.png` (gitignored)

**Interfaces:**
- Produces: `bash stack.sh up|down` (backend SQLite seeded en :8000 + Vite en :5173), `node capturas.mjs --out DIR [--anchos 390,768,1024,1440] [--temas claro,oscuro] [--rutas …]` que escribe `DIR/<ruta>__<ancho>__<tema>.png` y `DIR/desbordes.json`, `node diff1440.mjs BASE_DIR NEW_DIR` que escribe `NEW_DIR/diff1440.json` (`{ruta: {pixelesDistintos, porcentaje}}`).

- [ ] **Step 1: `stack.sh`**

```bash
#!/usr/bin/env bash
# Stack local para capturas: backend sobre SQLite de archivo + Vite. Nada toca prod.
set -euo pipefail
R=/mnt/d/Devs/atlas-one; S=$(dirname "$0")
export DATABASE_URL="sqlite:///$S/responsivo.db" SECRET_KEY=capturas
case "${1:-up}" in
  up)
    cd "$R"
    if [ ! -f "$S/responsivo.db" ]; then
      python3 - <<'PY'
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
@compiles(JSONB, "sqlite")
def _j(_t, _c, **_k): return "JSON"
import app.models
from app.core.database import Base, engine
Base.metadata.create_all(engine)
PY
      python3 scripts/init_presets_v2.py >/dev/null
      python3 scripts/seed_demo_orgs.py | tail -3
      python3 "$S/datos_muestra.py"
    fi
    (nohup python3 -m uvicorn app.main:app --port 8000 > "$S/backend.log" 2>&1 & echo $! > "$S/backend.pid")
    (cd frontend && nohup npm run dev -- --port 5173 --strictPort > "$S/vite.log" 2>&1 & echo $! > "$S/vite.pid")
    for i in $(seq 1 60); do curl -fsS http://localhost:8000/health >/dev/null 2>&1 && curl -fsS http://localhost:5173 >/dev/null 2>&1 && break; sleep 1; done
    echo "backend $(curl -fsS http://localhost:8000/health) · vite listo"
    ;;
  down) for p in backend vite; do [ -f "$S/$p.pid" ] && kill "$(cat "$S/$p.pid")" 2>/dev/null; rm -f "$S/$p.pid"; done; echo abajo ;;
esac
```

Si `app.main` arranca el worker del outbox o algo que no cabe en SQLite, `backend.log` lo dirá; el CLAUDE.md anota que el worker está gateado off en SQLite.

- [ ] **Step 2: `datos_muestra.py`** — inserta por ORM, en la org `demo_pos` (ATLAS_POS) y su sucursal que vende: 2 cortes cerrados + 1 abierto (`CashSession`), 40 ventas `SalesDocument` (status PAID, series "A", folios 1..40, fechas repartidas en los últimos 20 días, 1-3 `SalesLine` cada una sobre productos del seed, `Payment` CASH/CARD alternado, `cash_session_id` del corte abierto para las de hoy), 3 `SaleReturn` (PENDING, APPROVED, REJECTED) sobre ventas existentes, y 6 `CashMovement` (entradas/salidas) en el corte abierto. Toma los nombres de columnas de los modelos (`app/models/sales.py`, `app/models/cash.py`, `app/models/returns.py` o donde vivan: `grep -rn "class SalesDocument\|class CashSession\|class SaleReturn\|class CashMovement" app`). Idempotente: si ya hay 40 ventas en la org, no hace nada. Imprime los conteos.

- [ ] **Step 3: `capturas.mjs`** (Playwright)

`package.json` del scratchpad: `{"type":"module","dependencies":{"playwright":"1.5x","pixelmatch":"^6","pngjs":"^7"}}` — elegir la versión de `playwright` cuyo chromium sea el `1243` ya instalado (`ls ~/.cache/ms-playwright`): probar `npm i playwright@1.57` y si Playwright pide descargar, dejar que descargue (una vez). Script:

```js
// Entra como demo_pos / demo1234, visita cada ruta en cada ancho y tema, captura
// pantalla completa y mide desbordes: scrollWidth > innerWidth y elementos cuyo
// right > innerWidth + 1. Abre el primer modal de cada pantalla si hay selector.
import { chromium } from 'playwright'
import fs from 'node:fs'
const args = Object.fromEntries(process.argv.slice(2).map(a => a.replace(/^--/, '').split('=')))
const OUT = args.out; fs.mkdirSync(OUT, { recursive: true })
const ANCHOS = (args.anchos ?? '390,768,1024,1440').split(',').map(Number)
const TEMAS = (args.temas ?? 'claro,oscuro').split(',')
const RUTAS = (args.rutas ?? '/hq/operations,/hq/sales,/sales,/cash-history,/hq/reports-hub,/reports,/hq/returns,/returns').split(',')
const ALTO = { 390: 844, 768: 1024, 1024: 768, 1440: 900 }
const MODAL = { '/sales': 'table tbody tr, [data-tarjeta-fila]', '/hq/sales': 'table tbody tr, [data-tarjeta-fila]', '/returns': 'button[aria-label="Ver detalle"], table tbody tr button', '/hq/returns': 'table tbody tr button' }
const browser = await chromium.launch()
const desbordes = {}
for (const tema of TEMAS) for (const ancho of ANCHOS) {
  const ctx = await browser.newContext({ viewport: { width: ancho, height: ALTO[ancho] ?? 900 }, colorScheme: tema === 'oscuro' ? 'dark' : 'light', deviceScaleFactor: 1 })
  const page = await ctx.newPage()
  await page.goto('http://localhost:5173/login'); await page.fill('input[name="username"], input[type="text"]', 'demo_pos'); await page.fill('input[type="password"]', 'demo1234'); await page.keyboard.press('Enter'); await page.waitForURL(u => !u.pathname.includes('login'), { timeout: 15000 })
  await page.evaluate(t => localStorage.setItem('atlas-theme', t === 'oscuro' ? 'dark' : 'light'), tema)
  for (const ruta of RUTAS) {
    await page.goto('http://localhost:5173' + ruta); await page.waitForLoadState('networkidle'); await page.waitForTimeout(600)
    const clave = `${ruta.replace(/\//g, '_')}__${ancho}__${tema}`
    await page.screenshot({ path: `${OUT}/${clave}.png`, fullPage: true })
    desbordes[clave] = await page.evaluate(() => {
      const w = window.innerWidth; const malos = []
      for (const el of document.querySelectorAll('body *')) { const r = el.getBoundingClientRect(); if (r.width > 0 && r.right > w + 1) malos.push({ tag: el.tagName, cls: (el.className || '').toString().slice(0, 80), right: Math.round(r.right) }) }
      return { scrollWidth: document.documentElement.scrollWidth, innerWidth: w, desborda: document.documentElement.scrollWidth > w, elementos: malos.slice(0, 15) }
    })
    if (MODAL[ruta]) { const t = page.locator(MODAL[ruta]).first(); if (await t.count()) { await t.click(); await page.waitForTimeout(400); await page.screenshot({ path: `${OUT}/${clave}__modal.png`, fullPage: true }); await page.keyboard.press('Escape') } }
  }
  await ctx.close()
}
fs.writeFileSync(`${OUT}/desbordes.json`, JSON.stringify(desbordes, null, 2)); await browser.close()
const rotos = Object.entries(desbordes).filter(([, d]) => d.desborda || d.elementos.length)
console.log(`capturas: ${Object.keys(desbordes).length} · con desborde: ${rotos.length}`); for (const [k, d] of rotos) console.log(' ·', k, d.scrollWidth, '>', d.innerWidth, d.elementos.slice(0, 3))
```
Ajustar los selectores de login a los reales de `pages/Login.tsx` y la clave de tema a la que use `context/ThemeContext.tsx` (`grep -n localStorage frontend/src/context/ThemeContext.tsx`).

- [ ] **Step 4: `diff1440.mjs`** — con `pngjs` + `pixelmatch`, para cada `*__1440__*.png` de BASE que exista en NEW: compara (umbral 0.1), escribe `NEW/diff/<clave>.png` y `NEW/diff1440.json`; imprime las rutas con más de 0 píxeles distintos. Si los tamaños difieren (altura de página), recorta al mínimo común y lo anota.

- [ ] **Step 5: Baseline sobre `main`**

Desde la rama (que aún no toca código de pantallas): `bash stack.sh up && node capturas.mjs --out /mnt/d/Devs/atlas-one/.superpowers/sdd/responsivo-ola1/baseline --anchos 390,768,1024,1440`. Guardar también el `desbordes.json` del baseline: es la lista de lo roto HOY en teléfono (sirve de "antes"). Expected: 64 capturas + modales; a 1440 cero desbordes; a 390 varios.

- [ ] **Step 6: Sin commit** (todo es scratchpad y `.superpowers/`, gitignored). Reporte: rutas que desbordan a 390 en el baseline y qué elementos.

---

### Task 1: primitivas del kit y `Modal` como hoja inferior

**Files:**
- Create: `frontend/src/components/ui/TarjetaFila.tsx`, `frontend/src/components/ui/ListaTarjetas.tsx`, `frontend/src/components/ui/BarraFiltros.tsx`, `frontend/src/components/ui/CabeceraPagina.tsx`
- Modify: `frontend/src/components/ui/Modal.tsx` (panel: `dax-modal`; pie: `dax-modal-footer`)
- Modify: `frontend/src/index.css` (regla `.dax-filtros` bajo `sm`)
- Modify: `frontend/package.json` (devDeps `jsdom`, `@testing-library/react`, `@testing-library/user-event`)
- Test: `frontend/src/components/ui/__tests__/TarjetaFila.test.tsx`, `ListaTarjetas.test.tsx`, `BarraFiltros.test.tsx`, `Modal.test.tsx` (cada archivo con `// @vitest-environment jsdom` en la primera línea para no cambiar el entorno global)

**Interfaces (las consumen las tareas 2-6):**

```tsx
// TarjetaFila.tsx
export interface DatoTarjeta { etiqueta: string; valor: React.ReactNode }
export interface TarjetaFilaProps {
  titulo: React.ReactNode            // folio, nombre…
  subtitulo?: React.ReactNode        // una línea, se trunca
  importe?: React.ReactNode          // derecha, tabular-nums
  estado?: React.ReactNode           // chip junto al importe
  datos?: DatoTarjeta[]              // rejilla 2 columnas
  maxDatosVisibles?: number          // default 4; el resto tras "Ver más"
  acciones?: React.ReactNode         // fila al pie, botones ≥ 44 px
  onClick?: () => void               // toda la tarjeta tocable
  className?: string
  'data-testid'?: string
}
export function TarjetaFila(props: TarjetaFilaProps): JSX.Element
// Raíz: <article data-tarjeta-fila className="dax-card p-3 …">; si hay onClick, el cuerpo es <button type="button" className="w-full text-left …"> y `acciones` queda FUERA del button.

// ListaTarjetas.tsx
export function ListaTarjetas({ children, vacio, textoVacio = 'Sin resultados', cargando, className }: {
  children: React.ReactNode; vacio?: boolean; textoVacio?: string; cargando?: boolean; className?: string
}): JSX.Element   // <div className="space-y-2">; estados vacío/cargando con el mismo texto que la tabla

// BarraFiltros.tsx
export function BarraFiltros({ children, accion, className }: { children: React.ReactNode; accion?: React.ReactNode; className?: string }): JSX.Element
// <div className="dax-filtros flex flex-wrap items-end gap-2">{children}{accion && <div className="dax-filtros-accion">{accion}</div>}</div>
export function ParFechas({ children, className }: { children: React.ReactNode; className?: string }): JSX.Element
// <div className="grid grid-cols-2 gap-2 sm:contents"> — en escritorio `sm:contents` deja a los dos inputs como hijos directos de la barra (fila idéntica a hoy)

// CabeceraPagina.tsx
export function CabeceraPagina({ titulo, descripcion, acciones, accionPrincipal, className }: {
  titulo: React.ReactNode; descripcion?: React.ReactNode; acciones?: React.ReactNode; accionPrincipal?: React.ReactNode; className?: string
}): JSX.Element
// ≥ md: <div className="flex items-center justify-between flex-wrap gap-3"> como hoy; < md: apilado, accionPrincipal `w-full`, acciones en fila con gap-2
```

CSS a añadir en `index.css`, en la zona "BASE RESPONSIVA" (fuera de `@layer`):

```css
/* ─── 3. Barra de filtros: en teléfono cada control ocupa el ancho ──── */
@media (max-width: 639px) {
  .dax-filtros > * { width: 100%; max-width: none; }
  .dax-filtros > .grid { display: grid; }          /* ParFechas conserva sus 2 columnas */
  .dax-filtros-accion > * { width: 100%; min-height: 44px; }
}
```

`Modal.tsx`: al panel (`className={\`w-full ${SIZES[size]} rounded-xl flex flex-col max-h-[90vh] outline-none\`}`) quitarle `max-h-[90vh]` y añadir `dax-modal`; al contenedor del `footer` añadir `dax-modal-footer`. Comentario: `.dax-modal` da el tope de alto (90dvh) y la hoja inferior bajo `sm` (ver `index.css §2`).

- [ ] **Step 1: devDeps y un test que falle**

`cd frontend && npm i -D jsdom@^25 @testing-library/react@^16 @testing-library/user-event@^14 @testing-library/jest-dom@^6`. Crear los cuatro archivos de test (con `// @vitest-environment jsdom`), por ejemplo `TarjetaFila.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TarjetaFila } from '../TarjetaFila'

describe('TarjetaFila', () => {
  it('pinta titulo, importe, estado y datos', () => {
    render(<TarjetaFila titulo="A-41" subtitulo="29/09" importe="$1,250.00" estado={<span>PAGADA</span>} datos={[{ etiqueta: 'Pago', valor: 'Tarjeta' }]} />)
    expect(screen.getByText('A-41')).toBeTruthy(); expect(screen.getByText('$1,250.00')).toBeTruthy()
    expect(screen.getByText('Pago')).toBeTruthy(); expect(screen.getByText('Tarjeta')).toBeTruthy()
  })
  it('oculta los datos de mas y los muestra con Ver mas', () => {
    const datos = Array.from({ length: 6 }, (_, i) => ({ etiqueta: `E${i}`, valor: `V${i}` }))
    render(<TarjetaFila titulo="x" datos={datos} maxDatosVisibles={4} />)
    expect(screen.queryByText('E5')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /ver más/i }))
    expect(screen.getByText('E5')).toBeTruthy()
    expect(screen.getByRole('button', { name: /ver menos/i }).getAttribute('aria-expanded')).toBe('true')
  })
  it('las acciones no disparan el onClick de la tarjeta', () => {
    const abrir = vi.fn(); const imprimir = vi.fn()
    render(<TarjetaFila titulo="x" onClick={abrir} acciones={<button onClick={imprimir}>Reimprimir</button>} />)
    fireEvent.click(screen.getByRole('button', { name: 'Reimprimir' }))
    expect(imprimir).toHaveBeenCalledTimes(1); expect(abrir).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /^x$/ }))
    expect(abrir).toHaveBeenCalledTimes(1)
  })
  it('sin onClick no hay boton envolvente', () => {
    render(<TarjetaFila titulo="solo" />)
    expect(screen.queryByRole('button')).toBeNull()
  })
})
```

`ListaTarjetas.test.tsx`: 60 hijos se renderizan todos; `vacio` muestra `textoVacio`; `cargando` muestra "Cargando…" y no los hijos. `BarraFiltros.test.tsx`: raíz tiene clase `dax-filtros`; `accion` va dentro de `.dax-filtros-accion`; `ParFechas` tiene `grid grid-cols-2 sm:contents`. `Modal.test.tsx`: el panel tiene `dax-modal` y el pie `dax-modal-footer`; el contenido sigue montado (misma instancia: un `data-testid` con contador de montajes vía `useEffect`) tras disparar el `change` de un `matchMedia` falso (Review Focus #2: la hoja inferior es CSS, no remonta).

- [ ] **Step 2: Correr y ver que fallan**

Run: `cd frontend && npx vitest run src/components/ui/__tests__ 2>&1 | tail -5`
Expected: fallan por módulos inexistentes (`TarjetaFila`, `ListaTarjetas`, `BarraFiltros`) y por clases ausentes en `Modal`.

- [ ] **Step 3: Implementar las cuatro primitivas, el CSS y el cambio de `Modal`** según las interfaces de arriba. Reglas de `TarjetaFila`: rejilla `grid grid-cols-2 gap-x-3 gap-y-1 text-xs` con etiqueta en `--dax-text-faint` y valor en `--dax-text`; importe `font-semibold tabular-nums`; botón "Ver más"/"Ver menos" con `aria-expanded`, `min-h-[44px]`; `acciones` en `flex flex-wrap gap-2 mt-2` con `[&>button]:min-h-[44px]`.

- [ ] **Step 4: Correr y ver que pasan**

Run: `cd frontend && npx vitest run src/components/ui/__tests__ 2>&1 | tail -3 && npm test -- --run 2>&1 | tail -2 && npm run build 2>&1 | tail -2`
Expected: tests verdes, suite completa sin nuevos fallos, build ok.

- [ ] **Step 5: Comprobar el POS** (usa `.dax-modal`, no `Modal.tsx`, pero `KDS.tsx` sí usa `Modal`): `node capturas.mjs --out …/t1 --rutas /pos,/kitchen --anchos 390,1440` y mirar que el POS de cajera sigue igual a 390 y a 1440 (comparar a ojo con el baseline; `/kitchen` solo si el demo_pos tiene el módulo; si no, omitir y anotarlo).

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/ui/TarjetaFila.tsx frontend/src/components/ui/ListaTarjetas.tsx frontend/src/components/ui/BarraFiltros.tsx frontend/src/components/ui/CabeceraPagina.tsx frontend/src/components/ui/Modal.tsx frontend/src/index.css frontend/src/components/ui/__tests__
git commit -m "feat(ui): TarjetaFila, ListaTarjetas, BarraFiltros y CabeceraPagina; Modal como hoja inferior en telefono

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014rnFXXn9to8upxnFg1bpw8"
```

---

### Patrón común de las tareas 2 a 6 (léelo antes de cualquiera)

Para cada pantalla:

1. **Cabecera**: si el `<h1>` y las acciones están en `flex items-center justify-between flex-wrap gap-3`, envolverlos en `CabeceraPagina` (título = el `<h1>` tal cual, `accionPrincipal` = el botón que más usa el dueño, `acciones` = el resto). Escritorio queda idéntico porque `CabeceraPagina` reproduce esa misma fila `≥ md`.
2. **Filtros**: envolver la fila de `dax-input w-36` en `BarraFiltros`; las dos fechas en `ParFechas`; el botón de aplicar/exportar como `accion`. No cambiar los `w-36` (la regla CSS los anula bajo `sm`).
3. **KPIs**: `grid-cols-N` sin prefijo → `grid-cols-2 sm:grid-cols-3 lg:grid-cols-N` (si N ≤ 3, `grid-cols-2 lg:grid-cols-N`); `grid-cols-2 sm:grid-cols-4` ya está bien. Valores `text-3xl` dentro de tarjeta de 2 columnas → `text-2xl md:text-3xl`.
4. **Tabla → tarjetas**: `const esTelefono = useEsTelefono()`; `{esTelefono ? <ListaTarjetas …>{filas.map(f => <TarjetaFila …/>)}</ListaTarjetas> : (<tabla de hoy intacta>)}`. La paginación que esté debajo de la tabla queda **fuera** del condicional. Las funciones de formato de la fila se extraen a helpers del archivo (si no lo son ya) y las usan tabla y tarjeta.
5. **Modales** hechos a mano (`fixed inset-0 … <div className="dax-card … max-w-md">`): a la tarjeta del modal añadir `dax-modal` si no la tiene; al bloque de botones finales `dax-modal-footer -mx-6 px-6` (igual que `HQReturns.tsx:241` ya hace). Las tablas internas de artículos (≤ 4 columnas cortas) se dejan como tabla; si tienen más, misma conversión a tarjetas.
6. **Verificar**: `node capturas.mjs --out …/tN --rutas <las de la tarea>` → `desbordes.json` sin desbordes a 390/768/1024 en claro y oscuro; `node diff1440.mjs baseline tN` → 0 píxeles distintos en las rutas de la tarea. Si hay diferencia a 1440, explicarla o corregirla. Adjuntar al reporte las capturas a 390 (ruta de los PNG).
7. Commit por tarea con el mensaje indicado.

---

### Task 2: Ventas HQ y Mis ventas

**Files:** Modify `frontend/src/pages/hq/HQSalesLog.tsx` (277 l.), `frontend/src/pages/sales/SalesHistory.tsx` (414 l.)

Mapa de la tabla de ventas (igual en ambas) → `TarjetaFila`:

| Columna | En la tarjeta |
|---|---|
| Folio (`saleLabel(s)`, mono índigo) | `titulo` |
| Fecha (`toLocaleString … day/month/hour/minute`) + sucursal (HQ) | `subtitulo` ("29 sep 14:32 · Sucursal A") |
| Total (`formatCurrency`, verde) | `importe` |
| Estado (`<Badge>`) | `estado` |
| Cliente ("Público general" en cursiva si falta) | `datos[0]` etiqueta "Cliente" |
| Pago (`dax-badge-blue` por método) | `datos[1]` etiqueta "Pago", valor = los badges |
| Acciones Ver / Reimprimir / Devolver | `acciones` (mismos handlers y `disabled`; textos completos, no solo icono) |
| `onClick` de la fila (`setSel(s)`) | `onClick` |

KPIs: `SalesHistory` l.167 `grid-cols-2 sm:grid-cols-3 lg:grid-cols-6` ya está bien; `HQSalesLog` l.106 `grid-cols-2 sm:grid-cols-4` bien. Filtros: ambos (`select max-w-[160px]`, dos fechas, buscador) → `BarraFiltros` + `ParFechas`. Modal de detalle (`fixed inset-0`, l.319 / l.218): `dax-modal` en la tarjeta, `dax-modal-footer` al pie si hay botones; la tabla interna de artículos (4 columnas) se queda. `SalesHistory` además abre el modal de devolución (`setReturnSale`): si ese modal es un componente aparte, localizarlo y aplicarle el paso 5.

Commit: `feat(ventas): Ventas HQ y Mis ventas en tarjetas bajo 768 px, filtros y modal responsivos`.

### Task 3: Corte de caja

**Files:** Modify `frontend/src/pages/finance/CashHistory.tsx` (392 l.)

- Dos modales propios (l.34 movimiento, l.76 cierre): `dax-modal` en la tarjeta, `dax-modal-footer -mx-6 px-6` en los botones; los inputs de monto conservan su tamaño (`text-xl`+ no se tocan).
- KPIs l.230 y l.287 `grid-cols-2 sm:grid-cols-4` bien; l.250 `grid-cols-2` (dos tarjetas) → dejar (2 columnas caben en 390 si los valores son `text-2xl`; comprobar en captura, si no → `grid-cols-1 sm:grid-cols-2`).
- Tabla de movimientos del corte abierto (l.266, 4 columnas Tipo/Concepto/Monto/Hora): tarjetas con `titulo`=Concepto, `subtitulo`=Hora, `importe`=Monto con signo/color según tipo, `estado`=chip del tipo.
- Tabla "Historial de cortes" (l.326, 7 columnas): `titulo`="Apertura <fecha>", `subtitulo`=Cajero, `importe`=Cierre reportado (o "—"), `estado`=Abierto/Cerrado, `datos`=[Fondo, Cierre (fecha o "Activo")], `acciones`=PDF y Reimprimir (mismos handlers, con texto).
- Cabecera l.207 → `CabeceraPagina` (acción principal: el botón de abrir/cerrar turno que exista).

Commit: `feat(caja): Corte de caja en tarjetas bajo 768 px y modales en hoja inferior`.

### Task 4: Devoluciones HQ y Devoluciones

**Files:** Modify `frontend/src/pages/hq/HQReturns.tsx` (290 l.), `frontend/src/pages/sales/Returns.tsx` (267 l.)

Tabla (8 columnas en HQ, 7 en tienda) → `titulo`=Ticket (`returnLabel`), `subtitulo`=Fecha · Sucursal (HQ) · Solicitó, `importe`=Total (rojo), `estado`=Badge, `datos`=[Motivo (texto completo, sin truncar)], `acciones`=Ver detalle (y en HQ Aprobar/Rechazar si están en la fila), `onClick`=`setSelected(r)`. Los modales ya traen `dax-modal` y `dax-modal-footer` (HQ) — verificar que `Returns.tsx` también; el modal de rechazo (`z-[60]`) igual. Cabecera l.116/l.107 → `CabeceraPagina` con el `select` de estado como filtro en `BarraFiltros`.

Commit: `feat(devoluciones): listas en tarjetas bajo 768 px en tienda y HQ`.

### Task 5: Reportes HQ y Reportes

**Files:** Modify `frontend/src/pages/hq/HQReportsHub.tsx` (615 l.), `frontend/src/pages/finance/Reports.tsx` (219 l.)

- Filtros (select de sucursal + fechas) → `BarraFiltros` + `ParFechas`.
- `HQReportsHub` l.353/450/501 `grid-cols-1 lg:grid-cols-3` ya apilan; l.406 `grid-cols-2 sm:grid-cols-3 lg:grid-cols-6` bien. Revisar que cada gráfica de `react-chartjs-2` esté en un contenedor con `w-full` y `maintainAspectRatio` coherente (chart.js es responsivo por defecto; si alguna tiene `width`/`height` fijos en px, quitarlos y fijar alto con `h-56 sm:h-64`). `Heatmap`, `Gauge`, `Leaderboard`, `Sparkline` (`components/reports/`): comprobar a 390 que no desbordan; si uno lo hace, corregirlo en su componente con `w-full overflow-hidden` o tamaño relativo, sin tocar su aspecto a 1440.
- `Reports.tsx` l.131 `grid-cols-2 sm:grid-cols-4` bien; l.158 `grid-cols-1 sm:grid-cols-2` bien. Cabecera l.95 → `CabeceraPagina`.

Commit: `feat(reportes): filtros y graficas de Reportes HQ y Reportes caben en telefono`.

### Task 6: Inicio HQ

**Files:** Modify `frontend/src/pages/hq/HQOperations.tsx` (704 l.)

- Cabecera l.296-383: `CabeceraPagina` con título "Inicio"; `acciones` = botones de periodo (hoy/semana/mes/rango) como grupo `flex flex-wrap gap-1`, el par de fechas del rango en `ParFechas`; CSV y actualizar como `acciones` secundarias (icono + `aria-label` bajo md).
- l.384 `grid-cols-2 md:grid-cols-4` bien. l.413 `grid-cols-1 sm:grid-cols-2 lg:grid-cols-4` bien; valores `text-3xl` (l.430, 494) → `text-2xl md:text-3xl`.
- l.515 `grid grid-cols-1 lg:grid-cols-3 gap-5 lg:min-h-[380px]` bien (el `min-h` ya es `lg:`). Dentro, el panel de sucursales con `select` + `input search` (l.545-552): `flex-wrap`.
- l.610 `grid-cols-1 lg:grid-cols-2` bien. Tabla "Lo más vendido" (l.616, 3 columnas con barra de %): tarjetas `titulo`=Producto, `importe`=Vendido, `datos`=[% del total con la barra como `valor`]. Quitar `max-w-[140px]` solo si truncaba el nombre en teléfono (está tras `md:`, así que a 390 no aplica: dejar).
- Pantalla con `h1` en estilo propio (sombra verde): `CabeceraPagina` recibe el `<h1>` tal cual.

Commit: `feat(inicio): Inicio HQ cabe en telefono — cabecera apilada, KPIs y lo mas vendido en tarjetas`.

---

### Task 7: verificación de la ola y hallazgos

**Files:** Output `.superpowers/sdd/responsivo-ola1/final/` (capturas, `desbordes.json`, `diff1440.json`), `.superpowers/sdd/responsivo-ola1/ola-1-findings.md`

- [ ] `bash stack.sh down && bash stack.sh up` (reinicia Vite para que vea los cambios).
- [ ] `node capturas.mjs --out …/final` (las 8 rutas, 4 anchos, 2 temas) → `desbordes.json`: **cero** entradas con `desborda` o `elementos` a 390/768/1024. Cada una que quede es un hallazgo con su elemento.
- [ ] `node diff1440.mjs baseline final` → **cero** píxeles distintos en las 8 rutas a 1440 (claro y oscuro). Toda diferencia se lista con su recorte `diff/*.png`.
- [ ] Tap targets a 390: en cada captura de modal y lista, `page.evaluate` que mida todos los `button, a, [role=button]` visibles y liste los de alto < 44 px → hallazgos.
- [ ] Escribir `ola-1-findings.md`: tabla ruta × ancho × tema con ✅/❌, lista de hallazgos con archivo:línea propuesto, y las rutas de las capturas a 390 para que el usuario las vea. Si hay hallazgos Important (desborde, diff a 1440, tap < 44 en acción principal), **vuelven como fix round a la tarea dueña** antes de la Tarea 8.

---

### Task 8: el dueño entra al escritorio adaptado

**Files:** Modify `frontend/src/utils/rutaInicio.ts`; Test `frontend/src/utils/rutaInicio.test.ts`; Modify `frontend/src/hooks/useIsMobile.ts` (comentario de `PHONE_BREAKPOINT` que cita el redirect)

- [ ] Tests: dueño/admin con `esMovil=true` y preset `ATLAS_POS` → `/hq/operations`; con preset `ATLAS_ONE_RETAIL` → `/home` (Review Focus #5); vendedor móvil sigue a `/mobile/dashboard`; cliente a `/portal`; cajero a `/atlas-pos`. Ajustar/retirar el test actual que espera `/mobile/owner`.
- [ ] Quitar la rama `if (esOficina && esMovil) return '/mobile/owner'`; `esMovil` queda en la firma (lo usan vendedores) con un comentario de por qué ya no aplica al dueño. Actualizar el comentario de `useIsMobile.ts` l.22-29.
- [ ] `/mobile/owner` y el ítem "Resumen móvil" del menú **no se tocan**.
- [ ] `npm test -- --run` y `npm run build` verdes. Commit: `feat(inicio): el dueno y el admin entran al escritorio adaptado tambien en telefono`.

---

### Task 9: docs y memoria

- `docs/FRONTEND_VIEWS.md`: una nota al inicio: "Desde la ola 1 (2026-10-01) las vistas de admin/dueño listadas abajo se adaptan a teléfono con `TarjetaFila`/`BarraFiltros`/`CabeceraPagina` (`components/ui/`); el patrón está en `docs/superpowers/specs/2026-09-30-responsivo-admin-design.md §4`". Marcar las 8 rutas con "📱 ola 1".
- `CLAUDE.md` §5: receta "Hacer responsiva una pantalla de admin" (5 líneas: hook, primitivas, regla de rejillas, modal, verificación con `capturas.mjs`).
- Commit `docs: patron responsivo del lado administrador (ola 1)` que incluye también el plan (`docs/superpowers/plans/2026-10-01-responsivo-admin-ola-1.md`).
- Memoria (controlador): actualizar `responsivo-telefono.md` con la ola 1 y los hallazgos pendientes.

### Task 10: entrega (manual, con permiso)

Merge a `main` + push (despliega), verificación de `/health` y del commit, y revisión en el teléfono real del dueño de Eleven y de Mirna en Coqueta. Las olas 2 y 3 tienen su propio plan.
