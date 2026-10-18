# SP5 · Lado administrador responsivo — ola 2 (catálogo y personas) + cierre de la ola 1 — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que las ocho pantallas de catálogo y personas que usa el administrador (Productos, Catálogo, Marcas, Departamentos, Usuarios, Clientes, Inventario, Existencias HQ) quepan en un teléfono de 390 px sin scroll horizontal, con tablas convertidas en tarjetas, cabeceras apiladas y modales en hoja inferior, sin cambiar un píxel en escritorio; y cerrar lo que la ola 1 dejó abierto (el dueño ya no es desviado a `/mobile/owner`, verificación con capturas, docs).

**Architecture:** Se reutiliza tal cual el kit de la ola 1 que vive en `frontend/src/components/ui/` (`TarjetaFila`, `ListaTarjetas`, `BarraFiltros`, `CabeceraPagina`, `TablaDesplazable`, `Modal` con `.dax-modal`). Cada pantalla conserva su `<table>` intacta para `≥ md` y, bajo `md`, renderiza una lista de tarjetas con `useEsTelefono()` (render condicional, nunca los dos árboles). Los modales hechos a mano de estas pantallas reciben `.dax-modal` / `.dax-modal-footer` o migran a `ui/Modal` cuando son título + cuerpo + botones. `ConfirmDialog` (compartido por todo el admin) pasa al kit. Un test de guardia congela el inventario de overlays manuales y prohíbe rejillas sin prefijo en las pantallas de la ola. Verificación con Playwright en el scratchpad: capturas y comprobación de desborde a 390/768/1024 en claro y oscuro, y diff pixel a pixel a 1440 contra un baseline tomado antes de tocar código.

**Tech Stack:** React 18 + TypeScript + Tailwind (prefijos `sm/md/lg`) + tokens `--dax-*`; vitest 2 con `// @vitest-environment jsdom` + `@testing-library/react` (ya instalados); Playwright 1.63 en el scratchpad (chromium 1243 ya está en `~/.cache/ms-playwright`); backend FastAPI local sobre SQLite con `scripts/seed_demo_orgs.py` + datos de muestra por ORM.

**Spec:** `docs/superpowers/specs/2026-10-14-mega-plan-altas-docs-responsivo-agente-design.md` §4 SP5 (hallazgos, decisiones, entregables) y, como diseño de detalle, `docs/superpowers/specs/2026-09-30-responsivo-admin-design.md` (§3 regla de oro, §4 base común, §4.5 reglas de rejilla, §6 criterios de aceptación, §7 verificación). Plan previo: `docs/superpowers/plans/2026-10-01-responsivo-admin-ola-1.md` (T7, T8 y T9 quedaron sin hacer; se cierran aquí).

**Rama:** `feat/sp5-responsivo-admin`, creada desde `feat/sp1-altas-frontend` (b2c3004) porque la ola 2 toca el `FormularioProducto` unificado de SP1. Worktree: `.worktrees/sp5-responsivo-admin`.

## Decisiones respecto al mega plan (levantamiento del 2026-10-18 sobre b2c3004)

1. **El kit destino es `components/ui/`, no `components/atlas-one/`.** El mega plan (principio 2) suponía que `atlas-one/` era el kit en uso; en el código `atlas-one/` es el kit de *vista previa de diseño* (estilos inline, sin Tailwind) y solo lo importa `pages/__dev__/AtlasOnePreview.tsx` (más tres gráficas y el logo). Ninguna página de producción usa su `Button` ni su `Badge`. Todo el kit responsivo de la ola 1 y los 45+ usos de `DaxCard` están en `ui/`. Costo si está mal: ninguno visible; `atlas-one/` no se toca.
2. **La "congruencia" de botones queda fuera de este plan.** Las clases crudas son `dax-btn-primary` (48 archivos / 76 usos), `dax-btn-secondary` (52 / 104) y `dax-btn-danger` (7 / 11); `dax-btn-ghost` no existe ni en CSS ni en código. Un codemod a `ui/Button` tocaría el POS y gastro (fuera del foco "vistas de admin") y `ui/Button` hoy duplica el padding que ya ponen las clases. Se registra como seguimiento con esos números; no bloquea nada responsivo.
3. **Los overlays manuales son 52, no 18**, y 26 ya llevan `.dax-modal` (Brands, Departments, Users, Inventory, HQInventory, Products/ImportModal incluidos). Este plan migra o arregla solo los de las pantallas de la ola 2 (Customers ×2, CustomerFormModal) y el `ConfirmDialog` compartido; el resto queda congelado por el test de guardia de la Tarea 8 (no puede aparecer uno nuevo) y listado como seguimiento.
4. **`Products.tsx` ya no mide 1,772 líneas sino 724** (SP1) y solo le quedan 2 `grid-cols` sin prefijo, ambos dentro de `ImportModal`. `AdminCatalog` ya tiene tarjetas propias bajo 768 px (con un `useMediaQuery` literal): se conservan y solo se unifica el hook y la cabecera.
5. **Los 8 overlays sin `.dax-modal` de la ola 3** (Expenses, Purchases ×2, HR, Boxes ×2, Logistics, Quotes, Seguimiento) y `ProductDetailModal` del POS no se tocan: fuera de alcance según el spec.

## Global Constraints

- **Escritorio no cambia**: de 1024 px hacia arriba cada pantalla renderiza igual que hoy. Todo lo nuevo vive detrás de prefijos (`sm:`, `md:`, `lg:`, `max-md:`) o del hook `useEsTelefono()` (`< 768`). Cuando una clase ya traía `lg:` con un valor, se conserva; solo se añaden cortes inferiores.
- **Única excepción de escritorio admitida de antemano:** `ConfirmDialog` pasa de colores fijos (`bg-slate-900/95`, `#ffffff`) a la tarjeta del kit (`.dax-modal` sobre `--dax-card-solid`), porque hoy en tema claro es un cuadro negro con texto blanco. Se mira en las capturas de la Tarea 9.
- Cortes: `< 640` modal → hoja inferior y formularios a 1 columna; `< 768` tabla → tarjetas, cabecera apilada, KPIs a 2 columnas; `< 1024` rejillas de 3-4 → 2.
- **Render condicional** tabla/tarjetas con `useEsTelefono()` de `hooks/useIsMobile.ts`; nunca montar los dos árboles. `AdminCatalog` cambia su `useMediaQuery('(max-width: 767px)')` por el mismo hook.
- **Formateos compartidos**: lo que hoy formatea la fila (`formatCurrency`, `rolUsuario`, `roleVariant`, `balanceColor`, `movColor`/`movementColor`, `tipoMovimiento`, fechas) se reutiliza en la tarjeta; no se copian literales.
- Tap targets `≥ 44 px` bajo 768 (`dax-btn-icon` ya lo da a botones de icono; `TarjetaFila` lo impone a `acciones`). Toda tarjeta tocable es `<button>`; las acciones van fuera del botón.
- Tokens `--dax-*` y clases del kit (`dax-card`, `dax-badge-*`, `dax-input`, `dax-modal`, `dax-modal-footer`, `dax-filtros`); nada de color nuevo.
- Las tarjetas de teléfono conservan **todas** las acciones de la fila (editar, eliminar, ver, pagar, kardex, ajustar) con texto visible; nada se pierde por pasar a tarjeta.
- `main` = producción; rama `feat/sp5-responsivo-admin`; commits locales; **push y merge solo con permiso explícito**.
- Pruebas: `cd frontend && npm test -- --run` (vitest, hoy 667 verdes) y `npm run build` (tsc + vite) deben pasar en cada tarea. Backend no se toca. Una sola suite por worktree a la vez.
- Comentarios, nombres y textos en español como el resto del kit.
- Commits terminan con:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
  ```
- Vite en `/mnt/d` (WSL) no detecta cambios: reiniciar el dev server antes de capturar.

## Review Focus

1. **Clientes con 50 filas paginadas en teléfono**: la lista de tarjetas no monta la tabla y la paginación que vive bajo la tabla sigue visible y funcional. → Tarea 5 (test de guardia: el bloque `pages > 1` queda fuera del condicional `esTelefono ?`).
2. **Modales anidados en Clientes en teléfono** (estado de cuenta → Registrar pago, o → Editar cliente): el segundo queda encima del primero y Escape cierra solo el de arriba. → Tarea 5 (`Registrar pago` y `CustomerFormModal` sobre `ui/Modal`, z-[900] > z-50 del estado de cuenta; test jsdom de `CustomerFormModal`: Escape llama a `onClose` una vez).
3. **Kardex en Inventario/Existencias a 390 px**: la cabecera del kardex (título + "Ajustar" + "Cerrar") envuelve sin salirse y la tabla de movimientos pasa a tarjetas con signo y color del movimiento. → Tarea 6 (test de guardia: las dos tablas de cada archivo están dentro de un condicional `esTelefono`).
4. **Diálogo de confirmación en tema claro**: legible (texto del tema, no `#ffffff` fijo) y como hoja inferior bajo `sm`. → Tarea 1 (test jsdom: la tarjeta lleva `dax-modal`, los botones `dax-modal-footer`, y el archivo no contiene `#ffffff`).
5. **Dueño con preset `ATLAS_ONE_*` en teléfono**: al quitar el redirect cae en `/home`, no en `/hq/operations`; cualquier otro admin cae en `/hq/operations`. → Tarea 2 (test de `rutaInicio`).

---

### Task 0: herramientas de verificación y baseline de escritorio

Las herramientas de la ola 1 vivían en el scratchpad de aquella sesión y ya no existen (`.superpowers/sdd/responsivo-ola1/final/` está vacío: la T7 de la ola 1 nunca corrió). Se reconstruyen con las lecciones de su reporte y se toma el baseline **antes** de tocar código.

**Files:**
- Create (scratchpad, no versionado): `/tmp/claude-1000/-mnt-d-Devs-atlas-one/88dd20d9-ffe0-4c18-b01a-da7647838260/scratchpad/responsivo/` con `package.json`, `stack.sh`, `servidor.py`, `datos_muestra.py`, `capturas.mjs`, `diff1440.mjs`, `libs/`
- Output: `.superpowers/sdd/2026-10-18-sp5-responsivo-admin-ola-2/baseline/*.png` + `desbordes.json` + `baseline-resumen.md` (gitignored)

**Interfaces:**
- Produces: `R=<worktree> bash stack.sh up|down`; `node capturas.mjs --out DIR [--anchos 390,768,1024,1440] [--temas claro,oscuro] [--rutas …] [--usuario demo_pos]` que escribe `DIR/<ruta>__<ancho>__<tema>.png`, `…__modal.png`, `…__kardex.png` y `DIR/desbordes.json`; `node diff1440.mjs BASE_DIR NEW_DIR` que escribe `NEW_DIR/diff/*.png` y `NEW_DIR/diff1440.json` (`{clave: {pixelesDistintos, porcentaje}}`).

- [ ] **Step 1: `package.json` y navegador**

```json
{ "type": "module", "dependencies": { "playwright": "1.63.0", "pixelmatch": "^6", "pngjs": "^7" } }
```

`npm i` en el scratchpad. Playwright 1.63.0 usa el chromium 1243 ya instalado; no debe descargar nada. Al navegador le faltan `libnspr4`, `libnss3` y `libasound2t64` y no hay sudo: `apt-get download libnspr4 libnss3 libasound2t64 && for d in *.deb; do dpkg-deb -x $d libs/; done` y exportar `LD_LIBRARY_PATH=$PWD/libs/usr/lib/x86_64-linux-gnu` desde `capturas.mjs` (`process.env` antes de `chromium.launch()`).

- [ ] **Step 2: `servidor.py`** — punto de entrada de uvicorn (`servidor:app`). Antes de importar `app.main`, registra en SQLite equivalentes de `timezone()`, `to_char()` y `extract()` de Postgres (con `sqlalchemy.event.listens_for(engine, "connect")` → `dbapi_conn.create_function(...)`) y compila `JSONB` como `JSON`. Sin esto `/api/sales/stats`, `/api/reports/*` y `command-center/stats` devuelven 500 en SQLite y las pantallas se capturan con errores.

- [ ] **Step 3: `stack.sh`**

```bash
#!/usr/bin/env bash
# Stack local para capturas: backend sobre SQLite de archivo + Vite. Nada toca prod.
set -euo pipefail
R=${R:-/mnt/d/Devs/atlas-one/.worktrees/sp5-responsivo-admin}; S=$(cd "$(dirname "$0")" && pwd)
export DATABASE_URL="sqlite:///$S/responsivo.db" SECRET_KEY=capturas PYTHONPATH="$R:$S"
case "${1:-up}" in
  up)
    for p in 8000 5173; do (ss -ltn | grep -q ":$p ") && { echo "puerto $p ocupado"; exit 1; }; done
    cd "$R"
    if [ ! -f "$S/responsivo.db" ]; then
      python3 -c "import servidor; from app.core.database import Base, engine; Base.metadata.create_all(engine)"
      python3 scripts/init_presets_v2.py >/dev/null
      python3 scripts/seed_demo_orgs.py | tail -3
    fi
    python3 "$S/datos_muestra.py"        # idempotente, corre siempre
    (cd "$S" && nohup python3 -m uvicorn servidor:app --port 8000 </dev/null > "$S/backend.log" 2>&1 & echo $! > "$S/backend.pid")
    (cd "$R/frontend" && nohup npm run dev -- --port 5173 --strictPort </dev/null > "$S/vite.log" 2>&1 & echo $! > "$S/vite.pid")
    for i in $(seq 1 60); do curl -fsS http://localhost:8000/health >/dev/null 2>&1 && curl -fsS http://localhost:5173 >/dev/null 2>&1 && break; sleep 1; done
    echo "backend $(curl -fsS http://localhost:8000/health) · vite 200"
    ;;
  down)
    for p in backend vite; do [ -f "$S/$p.pid" ] && pkill -P "$(cat "$S/$p.pid")" 2>/dev/null; [ -f "$S/$p.pid" ] && kill "$(cat "$S/$p.pid")" 2>/dev/null; rm -f "$S/$p.pid"; done
    fuser -k 8000/tcp 5173/tcp 2>/dev/null || true; echo abajo ;;
esac
```

- [ ] **Step 4: `datos_muestra.py`** — inserta por ORM en la org `demo_pos` (ATLAS_POS, admin `demo_pos` / `demo1234`) y su sucursal que vende. Se niega a correr si `DATABASE_URL` no es SQLite. Idempotente (si ya hay 12 clientes en la org, no hace nada). Crea: 5 marcas y 5 departamentos (`grep -rn "class Brand\|class Department" app`), **30 productos** con 1-3 `ProductVariant` cada uno (talla/color), precio y costo, `brand_id`/`department_id` repartidos, nombres largos en 5 de ellos ("Playera manga larga algodón peinado edición limitada"), **existencias** en la sucursal (`grep -rn "class StockOnHand\|class InventoryMovement" app`) con 3 productos en 0, y **10 movimientos** (IN/OUT/ADJUSTMENT) sobre la primera variante para el kardex; **12 clientes** (`app/modules/customers/models.py`) con teléfono, RFC, 3 con `current_balance > 0` y crédito, y 2-3 movimientos de estado de cuenta en uno de ellos (`grep -rn "class CustomerLedger\|ledger" app/modules/customers`); **6 usuarios** de roles distintos (uno inactivo, uno sin sucursal fija) ligados por `UserOrganization` como hace `seed_demo_orgs.ensure_user`. Imprime los conteos.

- [ ] **Step 5: `capturas.mjs`** (Playwright). Reglas que ya se aprendieron y hay que conservar:

1. Login: clic en `.reveal-cta`, luego `#login-user`, `#login-pass`, Enter; esperar a que la URL salga de `/login`.
2. Tema: `localStorage['atlas_theme']` = `'light'|'dark'` con `context.addInitScript` para que aplique antes de cada documento.
3. Contexto: `viewport` `{390:844, 768:1024, 1024:768, 1440:900}`, `deviceScaleFactor 1`, `timezoneId 'America/Mexico_City'`, `locale 'es-MX'`, `reducedMotion 'reduce'`, `colorScheme` según tema.
4. Reloj determinista: tras el login, instalar un reloj falso **pausado** (`page.clock.install({ time })` + `page.clock.runFor(2500)` dos veces por ruta) con la fecha de `reloj.txt` que escribe `datos_muestra.py` (la de la última venta del seed). Sin esto las gráficas y las fechas relativas cambian entre corridas.
5. Página completa: el shell mide `h-dvh overflow-hidden` y el scroll vive en `<main>`. Medir **primero** en el estado real; luego, solo para la foto, `page.evaluate` cambia `<main>` y sus ancestros a `height:auto; overflow-y:visible; overflow-x:clip` y se captura `fullPage: true`.
6. Medición (en el estado real): `desborda` = scroll horizontal en `<html>` o en `<main>`; `elementos` = cada nodo con `getBoundingClientRect().right > scroller.clientWidth + 1`, clasificado como `empuja` / `scrollInterno` (dentro de un ancestro `overflow-x:auto`) / `oculto` (ancestro `overflow:hidden`), `raiz: true` si su padre sí cabe; `contenedores` = los `overflow-x:auto` con `scrollWidth > clientWidth`; `tap` = `button, a, [role=button]` visibles con alto o ancho `< 44` (solo a 390 y 768); `api` = respuestas 4xx/5xx; `redirigido` si la URL final no es la pedida.
7. Rutas y acciones por ruta (clave `__modal` o `__kardex`):

```js
const RUTAS_OLA2 = ['/products', '/admin/catalog', '/brands', '/departments', '/users', '/customers', '/inventory', '/hq/inventory']
const RUTAS_OLA1 = ['/hq/operations', '/hq/sales', '/sales', '/cash-history', '/hq/reports-hub', '/hq/returns']
// /reports y /returns no están en ROLE_ROUTES.ADMINISTRADOR; se capturan con demo_gerente_pos si datos_muestra lo crea (opcional, no bloquea).
const ACCIONES = {
  '/brands':       [{ clave: 'modal', clic: 'button:has-text("Nueva Marca")' }],
  '/departments':  [{ clave: 'modal', clic: 'button:has-text("Nuevo")' }],
  '/users':        [{ clave: 'modal', clic: 'button:has-text("Nuevo usuario")' }],
  '/customers':    [{ clave: 'modal', clic: 'button:has-text("Nuevo cliente")' },
                    { clave: 'detalle', clic: 'table tbody tr button, [data-tarjeta-fila] button:has-text("Ver")' }],
  '/inventory':    [{ clave: 'kardex', escribir: ['input[placeholder^="Buscar"]', 'a'], clic: 'button:has-text("Ver")' },
                    { clave: 'modal', clic: 'button:has-text("Ajustar")' }],
  '/hq/inventory': [{ clave: 'kardex', escribir: ['input[placeholder^="Buscar"]', 'a'], clic: 'button:has-text("Kardex")' },
                    { clave: 'modal', clic: 'button:has-text("Ajustar")' }],
  '/products':     [{ clave: 'modal', clic: '[aria-label="Importar productos"]' },
                    { clave: 'formulario', clic: '[aria-label="Nuevo producto"]' }],
}
```
Cada acción: ejecutar `escribir` si existe (`fill` + 800 ms), clic en el primer `clic` que exista, esperar 500 ms, medir y capturar con la clave, y `Escape` (o clic en "Cerrar"/"Cancelar") antes de la siguiente. Si el selector no existe, anotarlo en `desbordes.json` sin fallar.
8. Salida: `desbordes.json` por clave y un resumen por consola: número de capturas, claves con `desborda`, con `scrollInterno` y con `tap < 44`.

- [ ] **Step 6: `diff1440.mjs`** — con `pngjs` + `pixelmatch` (umbral 0.1), para cada `*__1440__*.png` de BASE que exista en NEW (incluidas las `__modal`, `__detalle`, `__kardex`, `__formulario`): compara, escribe `NEW/diff/<clave>.png` y `NEW/diff1440.json`; si los tamaños difieren compara el área común y lo anota (`recortado: true`). Imprime las claves con más de 0 píxeles distintos.

- [ ] **Step 7: Baseline** sobre b2c3004 (la rama aún no toca pantallas): `bash stack.sh up && node capturas.mjs --out /mnt/d/Devs/atlas-one/.superpowers/sdd/2026-10-18-sp5-responsivo-admin-ola-2/baseline --rutas <RUTAS_OLA2 + RUTAS_OLA1>` → 14 rutas × 4 anchos × 2 temas = 112 capturas de página + acciones. Correr **dos veces** la misma ruta y confirmar 0 píxeles distintos a 1440 (el reloj está bien pausado). Escribir `baseline-resumen.md`: tabla ruta × ancho con ok / scroll interno / desborde y el elemento culpable, y las rarezas (redirecciones, errores de API).

- [ ] **Step 8: Sin commit** (todo es scratchpad y `.superpowers/`, gitignored). Reporte: rutas que desbordan a 390 hoy y qué elementos; cualquier selector de `ACCIONES` que no encontró su botón.

---

### Task 1: `ConfirmDialog` al kit (compartido por todo el admin)

Lo abren Brands, Departments, Users, Customers, AdminCatalog, Organization, Expenses, HQReturns, Labels, Quotes, Recipes, FloorPlan, el carrito del POS y el menú lateral. Hoy pinta `bg-slate-900/95` con `color:#ffffff` fijo: en tema claro es un cuadro negro, y bajo `sm` no es hoja inferior.

**Files:**
- Modify: `frontend/src/components/ui/ConfirmDialog.tsx:123-171`
- Test: `frontend/src/components/ui/__tests__/ConfirmDialog.test.tsx` (nuevo)

**Interfaces:** no cambia la API (`confirm(opts)`, `useConfirm()`, `ConfirmDialogProvider`, `ConfirmVariant`). Solo el DOM del diálogo.

- [ ] **Step 1: Test que falla**

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ConfirmDialogProvider, confirm } from '../ConfirmDialog'

describe('ConfirmDialog', () => {
  it('usa la tarjeta y el pie del kit, y Escape cancela', async () => {
    render(<ConfirmDialogProvider><div /></ConfirmDialogProvider>)
    let resultado: Promise<boolean>
    act(() => { resultado = confirm({ title: '¿Eliminar la marca?', message: 'No se puede deshacer', variant: 'danger' }) })
    const titulo = await screen.findByText('¿Eliminar la marca?')
    const tarjeta = titulo.closest('.dax-modal')
    expect(tarjeta).not.toBeNull()
    expect(tarjeta!.querySelector('.dax-modal-footer')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Cancelar' }).className).toContain('dax-btn-secondary')
    expect(screen.getByRole('button', { name: 'Confirmar' }).className).toContain('dax-btn-danger')
    fireEvent.keyDown(document, { key: 'Escape' })
    await expect(resultado!).resolves.toBe(false)
  })
  it('no fija colores fuera de los tokens', () => {
    const fuente = readFileSync(resolve(__dirname, '../ConfirmDialog.tsx'), 'utf8')
    expect(fuente).not.toMatch(/#ffffff|bg-slate-900|rgba\(255,255,255/)
  })
})
```

- [ ] **Step 2: Correr y ver que falla** — `cd frontend && npx vitest run src/components/ui/__tests__/ConfirmDialog.test.tsx`. Expected: FAIL (`.dax-modal` null; la fuente contiene `#ffffff`).

- [ ] **Step 3: Implementar.** Mantener la lógica (refs, teclado, foco). Cambiar solo el JSX a partir de la l.123:

```tsx
  return (
    <div
      className="fixed inset-0 z-[1000] flex items-center justify-center p-4 backdrop-blur-sm transition-opacity"
      style={{ background: 'var(--dax-modal-backdrop)' }}
      role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title"
      onClick={(e) => { if (e.target === e.currentTarget) onCancel() }}
    >
      {/* `.dax-modal`: tope de alto y hoja inferior bajo `sm` (index.css §2). Colores del tema, no fijos. */}
      <div className={`dax-card dax-modal w-full max-w-md p-5 border ${styles.accent} shadow-2xl`}>
        <div className="flex items-start gap-3 mb-3">
          <i className={`fa-solid ${styles.icon} text-xl mt-0.5`} aria-hidden="true" />
          <h2 id="confirm-dialog-title" className="font-bold text-base leading-snug" style={{ color: 'var(--dax-text)' }}>
            {options.title}
          </h2>
        </div>
        {options.message && (
          <div className="text-sm leading-relaxed mb-5 ml-8" style={{ color: 'var(--dax-text-dim)' }}>{options.message}</div>
        )}
        <div className="dax-modal-footer -mx-5 px-5 flex items-center justify-end gap-2">
          <button ref={cancelBtnRef} type="button" onClick={onCancel} className="dax-btn-secondary text-sm">
            {options.cancelText ?? 'Cancelar'}
          </button>
          <button ref={confirmBtnRef} type="button" onClick={onConfirm}
            className={`text-sm ${options.variant === 'danger' ? 'dax-btn-danger' : 'dax-btn-primary'}`}>
            {options.confirmText ?? 'Confirmar'}
          </button>
        </div>
      </div>
    </div>
  )
```

`styles.btn` deja de usarse (quitarlo del mapa de estilos si queda huérfano; `styles.accent` e `styles.icon` se conservan). Verificar que `--dax-text-dim` existe en `index.css` (`grep -n "dax-text-dim\|dax-text-faint" frontend/src/index.css`); si solo existe `--dax-text-faint`, usar ese.

- [ ] **Step 4: Correr y ver que pasa** — el test nuevo y la suite completa (`npm test -- --run`): 667 + 2. `npm run build` verde.

- [ ] **Step 5: Commit** — `git commit -m "feat(ui): ConfirmDialog usa la tarjeta y el pie del kit (hoja inferior en telefono, colores del tema)"` con el trailer.

---

### Task 2: cierre de la ola 1 — el dueño entra al escritorio adaptado

(T8 de la ola 1, nunca hecha.) `utils/rutaInicio.ts:11` sigue mandando a ADMINISTRADOR/DUEÑO en teléfono a `/mobile/owner`.

**Files:**
- Modify: `frontend/src/utils/rutaInicio.ts`
- Modify: `frontend/src/utils/rutaInicio.test.ts`
- Modify: `frontend/src/hooks/useIsMobile.ts:41-48` (comentario de `PHONE_BREAKPOINT` que cita el redirect)
- Modify: `frontend/src/utils/cajonLateral.ts:5` (comentario dice "por debajo de 768px"; el corte es 1024)

- [ ] **Step 1: Tests** — reemplazar los dos primeros `it` de `rutaInicio.test.ts` por:

```ts
  it('el ADMINISTRADOR y el DUEÑO entran al escritorio adaptado también en teléfono', () => {
    // Ola 1 del responsivo: ya no se les desvía a /mobile/owner (la ruta y el ítem "Resumen móvil" siguen existiendo).
    expect(rutaInicioPorRol('ADMINISTRADOR', true, 'ATLAS_POS')).toBe('/hq/operations')
    expect(rutaInicioPorRol('DUEÑO', true, 'ATLAS_POS')).toBe('/hq/operations')
  })
  it('con preset ATLAS_ONE_* el dueño en teléfono cae en /home', () => {
    expect(rutaInicioPorRol('DUEÑO', true, 'ATLAS_ONE_RETAIL')).toBe('/home')
  })
```
Los otros dos `it` se conservan.

- [ ] **Step 2: Correr y ver que falla** — `npx vitest run src/utils/rutaInicio.test.ts`. Expected: 2 FAIL (`/mobile/owner`).

- [ ] **Step 3: Implementar** — en `rutaInicio.ts` quitar la l.11 (`if (esOficina && esMovil) return '/mobile/owner'`); `esMovil` queda en la firma (lo usan vendedores) con un comentario: `// esMovil ya no desvía al dueño: desde la ola 1 del responsivo el escritorio cabe en teléfono.` Actualizar el comentario de la l.3 (vitest ya incluye `.tsx`). En `useIsMobile.ts:41-48` y `cajonLateral.ts:5` corregir los comentarios (sin tocar lógica). `/mobile/owner` y el ítem "Resumen móvil" del menú **no se tocan**. `App.tsx:172-186` no cambia (sigue pasando `isMobile`).

- [ ] **Step 4: Correr y ver que pasa** — suite completa y `npm run build`.

- [ ] **Step 5: Commit** — `git commit -m "feat(inicio): el dueno y el admin entran al escritorio adaptado tambien en telefono"`.

---

### Patrón común de las tareas 3 a 7 (léelo antes de cualquiera)

Referencia viva del patrón: `pages/sales/SalesHistory.tsx` (l.12 import, l.73 `esTelefono`, l.219 `CabeceraPagina`, l.274 `BarraFiltros`, l.311-315 condicional tabla/tarjetas) y `pages/hq/HQReturns.tsx` (l.33/121/160/167).

```tsx
import { useEsTelefono } from '../../hooks/useIsMobile'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { ListaTarjetas } from '../../components/ui/ListaTarjetas'
import { TarjetaFila } from '../../components/ui/TarjetaFila'
// …
const esTelefono = useEsTelefono()
// Cabecera: el <h1> con su icono se pasa tal cual como `titulo`; el botón "Nuevo…" como `accionPrincipal`.
<CabeceraPagina
  titulo={<div className="flex items-center gap-3"><i className="fa-solid fa-tags text-indigo-400 text-xl" /><h1 className="text-2xl font-black text-white">Marcas</h1></div>}
  accionPrincipal={<button onClick={openCreate} className="dax-btn-primary text-xs"><i className="fa-solid fa-plus" /> Nueva Marca</button>}
/>
// Lista: la <table> de hoy NO se toca; solo se envuelve en el condicional.
{esTelefono ? (
  <ListaTarjetas vacio={filtered.length === 0} textoVacio="Sin marcas" cargando={loading} className="p-3">
    {filtered.map((b) => (
      <TarjetaFila key={b.id} titulo={b.name} /* … */ acciones={<>…</>} />
    ))}
  </ListaTarjetas>
) : (
  /* …el bloque actual: Spinner / vacío / <div className="overflow-x-auto"><table …> sin cambios… */
)}
```

Reglas:
- Los estados `loading` / vacío de la tabla se expresan con `cargando` / `vacio` + `textoVacio` de `ListaTarjetas` con **los mismos textos** que hoy muestra la tabla.
- `DaxCard padding={false}` se conserva; la lista recibe `className="p-3"`.
- Acciones de la fila → `acciones` de la tarjeta, con texto visible (`<i …/> Editar`), clases `dax-btn-secondary text-xs` (eliminar: `dax-btn-danger text-xs`) y el mismo `onClick`/`aria-label` que en la tabla. `TarjetaFila` ya les impone 44 px.
- Rejillas: aplicar §4.5 del spec (`grid-cols-2` → `grid-cols-1 sm:grid-cols-2`; `grid-cols-3` → `grid-cols-1 sm:grid-cols-3` o `grid-cols-2 sm:grid-cols-3` si son KPIs).
- Modal hecho a mano que **ya lleva** `dax-card dax-modal` + `dax-modal-footer`: no se toca.
- Modal sin `.dax-modal`: si es título + cuerpo + botones, migra a `ui/Modal` (`open`, `onClose`, `title`, `footer`, `size`); si tiene cabecera con lógica propia, solo añade `dax-modal` a la tarjeta y `dax-modal-footer` al pie, quitando el `max-h-[Nvh] overflow-y-auto` que `.dax-modal` ya impone.
- Prohibido montar tabla y tarjetas a la vez (`hidden md:block`).
- Test de guardia compartido `frontend/src/pages/__tests__/responsivoOla2.test.ts` (lo crea la Tarea 3; las siguientes **añaden** su página a `PAGINAS`). Comprueba, leyendo la fuente, que cada página importa `useEsTelefono`, usa `<CabeceraPagina`, usa `<TarjetaFila` (salvo las de `SIN_TARJETA_FILA`), no tiene `grid-cols-N` sin prefijo, y no tiene `hidden md:block`/`md:hidden`.

---

### Task 3: Marcas y Departamentos (+ test de guardia de la ola)

**Files:**
- Modify: `frontend/src/pages/core/Brands.tsx:62-119` (cabecera l.64-73, buscador l.75-78, tabla l.80-119)
- Modify: `frontend/src/pages/core/Departments.tsx:67-109` (cabecera l.69-78, tabla l.80-109)
- Test: `frontend/src/pages/__tests__/responsivoOla2.test.ts` (nuevo)

**Interfaces:**
- Produces: el test de guardia con `PAGINAS: string[]` y `SIN_TARJETA_FILA: string[]` que las tareas 4-7 extienden.

- [ ] **Step 1: Test de guardia que falla**

```ts
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/** Pantallas de la ola 2 del responsivo (catálogo y personas). Cada tarea añade la suya. */
export const PAGINAS = ['core/Brands.tsx', 'core/Departments.tsx']
/** Tienen tarjetas propias y no usan TarjetaFila. */
export const SIN_TARJETA_FILA: string[] = []

const fuente = (p: string) => readFileSync(resolve(__dirname, '..', p), 'utf8')
// `grid-cols-3` o más sin prefijo sm:/md:/lg:/max-*: (1 y 2 columnas sí caben en 390 px).
// Excepción explícita: la línea lleva el comentario `rejilla fija:` (N columnas cortas que caben).
const REJILLA_SIN_PREFIJO = /(?<![\w:-])grid-cols-(?:[3-9]|1[0-2])\b/
const sinExcepciones = (s: string) => s.split('\n').filter((l) => !l.includes('rejilla fija:')).join('\n')

describe('ola 2 responsiva: catálogo y personas', () => {
  it.each(PAGINAS)('%s usa el hook y el kit', (p) => {
    const s = fuente(p)
    expect(s).toMatch(/useEsTelefono\(\)/)
    expect(s).toMatch(/<CabeceraPagina/)
    if (!SIN_TARJETA_FILA.includes(p)) expect(s).toMatch(/<TarjetaFila/)
  })
  it.each(PAGINAS)('%s no tiene rejillas sin prefijo ni dos árboles montados', (p) => {
    const s = fuente(p)
    expect(sinExcepciones(s)).not.toMatch(REJILLA_SIN_PREFIJO)
    expect(s).not.toMatch(/hidden md:block|md:hidden/)
  })
})
```

- [ ] **Step 2: Correr y ver que falla** — `npx vitest run src/pages/__tests__/responsivoOla2.test.ts`. Expected: 2 FAIL (sin `useEsTelefono`).

- [ ] **Step 3: Brands.tsx.** Cabecera l.64-73 → `CabeceraPagina` (título = icono + h1; `accionPrincipal` = botón "Nueva Marca"). Buscador l.75-78: se conserva (ya es `flex-1`). Tabla l.80-119 → condicional. Tarjeta:

```tsx
<TarjetaFila key={b.id}
  titulo={<span className="flex items-center gap-2">
    {b.logo_url ? <img src={b.logo_url} alt="" className="h-8 w-8 object-contain rounded" /> : <span className="h-8 w-8 bg-slate-700 rounded flex items-center justify-center"><i className="fa-solid fa-image text-slate-500 text-xs" /></span>}
    {b.name}
  </span>}
  acciones={<>
    <button onClick={() => openEdit(b)} aria-label={`Editar ${b.name}`} className="dax-btn-secondary text-xs"><i className="fa-solid fa-pen" /> Editar</button>
    <button onClick={() => handleDelete(b)} aria-label={`Eliminar ${b.name}`} className="dax-btn-danger text-xs"><i className="fa-solid fa-trash" /> Eliminar</button>
  </>}
/>
```
`ListaTarjetas cargando={loading} vacio={filtered.length === 0} textoVacio="Sin marcas"`. El modal (l.123-148) ya lleva `dax-modal` + `dax-modal-footer`: no se toca.

- [ ] **Step 4: Departments.tsx.** Igual: cabecera l.69-78 → `CabeceraPagina` (acción "Nuevo"); tabla l.80-109 → condicional con `TarjetaFila titulo={d.name}` y las mismas dos acciones; `textoVacio="Sin departamentos"`, `cargando={loading}`. Modal l.113-131 no se toca.

- [ ] **Step 5: Correr y ver que pasa** — guardia + suite completa + `npm run build`.

- [ ] **Step 6: Commit** — `git commit -m "feat(catalogo): Marcas y Departamentos caben en telefono — cabecera apilada y tarjetas por renglon"`.

---

### Task 4: Usuarios

**Files:**
- Modify: `frontend/src/pages/core/Users.tsx:133-188` (cabecera l.135-144, tabla l.146-188)
- Test: `frontend/src/pages/__tests__/responsivoOla2.test.ts` (añadir `'core/Users.tsx'` a `PAGINAS`)

- [ ] **Step 1: Añadir la página al test y ver que falla.**

- [ ] **Step 2: Implementar.** Cabecera → `CabeceraPagina` (acción principal "Nuevo usuario"). Tabla (dentro de `TablaDesplazable sangrado={false}`, l.149) → condicional. Tarjeta:

```tsx
<TarjetaFila key={u.id}
  titulo={<span className="font-mono text-indigo-400">{u.username}</span>}
  subtitulo={u.full_name ?? '—'}
  estado={<Badge variant={roleVariant(u.role) as 'red' | 'yellow' | 'blue' | 'green' | 'slate'}>{rolUsuario(u.role)}</Badge>}
  datos={[
    { etiqueta: 'Sucursal', valor: u.branch_name ?? 'Sin sucursal fija' },
    { etiqueta: 'Estado', valor: <span className={u.is_active ? 'text-emerald-400' : 'text-slate-500'}>{u.is_active ? 'Activo' : 'Inactivo'}</span> },
  ]}
  acciones={<>
    <button onClick={() => openEdit(u)} aria-label={`Editar a ${u.username}`} className="dax-btn-secondary text-xs"><i className="fa-solid fa-pen" /> Editar</button>
    <button onClick={() => handleToggle(u)} aria-label={u.is_active ? `Desactivar a ${u.username}` : `Activar a ${u.username}`} className="dax-btn-secondary text-xs">
      <i className={`fa-solid ${u.is_active ? 'fa-circle-xmark' : 'fa-circle-check'}`} /> {u.is_active ? 'Desactivar' : 'Activar'}
    </button>
  </>}
/>
```
`textoVacio="Sin usuarios"`, `cargando={loading}`. El modal l.192-290 ya lleva `dax-modal` + `dax-modal-footer`; su rejilla l.213 ya es `grid-cols-1 sm:grid-cols-2`. No se toca.

- [ ] **Step 3: Suite + build verdes. Commit** — `git commit -m "feat(usuarios): la lista de usuarios cabe en telefono"`.

---

### Task 5: Clientes y su formulario

**Files:**
- Modify: `frontend/src/pages/crm/Customers.tsx` (cabecera l.134-137; buscador l.160-168; tabla l.171-212; paginación l.214-220 **se queda fuera del condicional**; modal estado de cuenta l.225-316; modal pago l.320-340)
- Modify: `frontend/src/pages/crm/CustomerFormModal.tsx:62-124`
- Test: `frontend/src/pages/__tests__/responsivoOla2.test.ts` (añadir `'crm/Customers.tsx'` a `PAGINAS` y un `it` específico), `frontend/src/pages/crm/__tests__/CustomerFormModal.test.tsx` (nuevo)

- [ ] **Step 1: Tests que fallan.** En el test de guardia añadir la página y:

```ts
  it('Customers conserva la paginación fuera del condicional y usa Modal del kit para pago y formulario', () => {
    const s = fuente('crm/Customers.tsx')
    expect(s.indexOf('pages > 1')).toBeGreaterThan(s.indexOf('esTelefono ?'))
    expect(s).toMatch(/import \{ Modal \} from '\.\.\/\.\.\/components\/ui\/Modal'/)
    expect((s.match(/fixed inset-0/g) ?? []).length).toBe(1) // solo el estado de cuenta (cabecera propia)
    expect(fuente('crm/CustomerFormModal.tsx')).not.toMatch(/fixed inset-0/)
  })
```

`CustomerFormModal.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import CustomerFormModal from '../CustomerFormModal'

vi.mock('../../../api/customers', () => ({ customersApi: { create: vi.fn(), update: vi.fn() } }))

describe('CustomerFormModal', () => {
  it('se pinta con el Modal del kit, apila los campos bajo sm y Escape cierra una sola vez', () => {
    const onClose = vi.fn()
    render(<CustomerFormModal customer={null} onClose={onClose} onSaved={() => {}} />)
    expect(screen.getByRole('dialog').querySelector('.dax-modal')).not.toBeNull()
    expect(screen.getByRole('button', { name: /Guardar/ }).closest('.dax-modal-footer')).not.toBeNull()
    const rejillas = Array.from(document.querySelectorAll('[class*="grid-cols-2"]'))
    expect(rejillas.length).toBeGreaterThan(0)
    for (const r of rejillas) expect(r.className).toMatch(/grid-cols-1 sm:grid-cols-2/)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
```
Ajustar el export (`default` o nombrado) y la ruta del mock a lo que haya en `CustomerFormModal.tsx:1-20` (`grep -n "^import\|^export" frontend/src/pages/crm/CustomerFormModal.tsx`).

- [ ] **Step 2: Correr y ver que fallan.**

- [ ] **Step 3: `CustomerFormModal.tsx`** → `ui/Modal`:

```tsx
<Modal open onClose={onClose} size="lg"
  title={<><i className={`fa-solid ${isEdit ? 'fa-pen' : 'fa-user-plus'} mr-2 text-indigo-400`} />{isEdit ? 'Editar cliente' : 'Nuevo cliente'}</>}
  footer={<>
    <button onClick={onClose} className="dax-btn-secondary flex-1">Cancelar</button>
    <button onClick={submit} disabled={saving || !form.name.trim()} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">
      {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar</>}
    </button>
  </>}>
  <div className="space-y-3">{/* …los campos de hoy… */}</div>
</Modal>
```
Las tres rejillas l.72, l.76 y l.90: `grid grid-cols-2 gap-3` → `grid grid-cols-1 sm:grid-cols-2 gap-3`. `Modal` ya cierra con Escape y con el fondo; quitar el `onClick={onClose}` del envoltorio viejo y el `stopPropagation`.

- [ ] **Step 4: `Customers.tsx`.** Cabecera l.134-137 → `CabeceraPagina` solo con `titulo` (icono + h1). El botón "Nuevo cliente" **se queda junto al buscador** (l.160-168) para no mover nada en escritorio; esa fila pasa a `flex flex-wrap gap-2` y el botón recibe `max-md:w-full max-md:min-h-[44px] justify-center`. KPIs l.141 ya son `grid-cols-2 sm:grid-cols-4`: no se tocan. Tabla l.176-212 → condicional; la paginación l.214-220 **permanece fuera**, después del condicional. Tarjeta:

```tsx
<TarjetaFila key={c.id}
  titulo={c.name}
  subtitulo={[c.phone, c.tax_id].filter(Boolean).join(' · ') || '—'}
  importe={<span className={balanceColor(c.current_balance)}>{formatCurrency(c.current_balance)}</span>}
  datos={[{ etiqueta: 'Crédito', valor: c.credit_limit != null ? formatCurrency(c.credit_limit) : '—' }]}
  onClick={() => openDetail(c)}
  acciones={<>
    <button onClick={() => openDetail(c)} className="dax-btn-secondary text-xs"><i className="fa-solid fa-eye" /> Ver</button>
    {c.current_balance > 0 && <button onClick={() => setPayModal({ id: c.id, name: c.name })} className="dax-btn-primary text-xs"><i className="fa-solid fa-money-bill-wave" /> Pagar</button>}
  </>}
/>
```
Modal **estado de cuenta** (l.225-316, cabecera propia con editar/eliminar/cerrar): a la tarjeta l.226 añadir `dax-modal` y quitar `max-h-[85vh] overflow-y-auto`; envolver los botones de acción del pie (si los hay) o dejar el cuerpo con scroll propio de `.dax-modal`; rejillas: l.263 `grid-cols-3` **se conserva** con el comentario `{/* rejilla fija: 3 KPIs cortos caben a 390 */}` en la misma línea (si en la Tarea 9 desborda, pasa a `grid-cols-2 sm:grid-cols-3`); l.285 `grid-cols-2` se conserva (2 columnas caben). Los dos botones de icono de la cabecera del modal (editar l.246, eliminar l.252) reciben `dax-btn-icon`. Modal **Registrar pago** (l.320-340) → `ui/Modal size="sm"` con `title="Registrar Pago"`, `footer` = los dos botones; `onClose` = `() => { setPayModal(null); setPayAmount('') }`.

- [ ] **Step 5: Suite + build verdes. Commit** — `git commit -m "feat(clientes): lista, estado de cuenta y formulario de cliente caben en telefono"`.

---

### Task 6: Inventario y Existencias HQ

Dos pantallas casi gemelas: buscador, tabla de existencias (5 columnas), y al elegir un renglón una vista de kardex con cabecera (título + "Ajustar" + cerrar) y tabla de movimientos (6 / 5 columnas). Los modales de ajuste (Inventory l.187-220, HQInventory l.222-255) ya llevan `dax-modal` + `dax-modal-footer`.

**Files:**
- Modify: `frontend/src/pages/inventory/Inventory.tsx:89-176` (cabecera l.91-94, tabla l.106-131, cabecera kardex l.135-149, tabla kardex l.151-175)
- Modify: `frontend/src/pages/hq/HQInventory.tsx:102-209` (cabecera l.104-107, tabla l.120-152, cabecera kardex l.156-171, tabla kardex l.173-208)
- Test: guardia (añadir `'inventory/Inventory.tsx'` y `'hq/HQInventory.tsx'`) + un `it`:

```ts
  it.each(['inventory/Inventory.tsx', 'hq/HQInventory.tsx'])('%s: las dos tablas están tras el condicional', (p) => {
    const s = fuente(p)
    expect((s.match(/<table/g) ?? []).length).toBe(2)
    expect((s.match(/esTelefono \?/g) ?? []).length).toBe(2)
  })
```

- [ ] **Step 1: Añadir al test y ver que falla.**

- [ ] **Step 2: Implementar (en los dos archivos, mismo patrón).** Cabecera de página → `CabeceraPagina` (sin acciones). Tabla de existencias → condicional; tarjeta:

```tsx
<TarjetaFila key={row.variant.id}
  titulo={row.label}
  subtitulo={<span className="font-mono text-indigo-400">{row.sku}</span>}
  importe={formatCurrency(row.variant.price ?? 0)}
  estado={<span className={`font-bold tabular-nums ${row.qty <= 0 ? 'text-red-400' : 'text-emerald-400'}`}>{row.qty} en stock</span>}
  acciones={<button onClick={() => openKardex(row) /* HQ: openDetail(row) */} className="dax-btn-secondary text-xs"><i className="fa-solid fa-chart-line" /> Kardex</button>}
/>
```
`textoVacio` no aplica (la tabla solo se pinta con `rows.length > 0`); `cargando={loading}`. Cabecera del kardex (`flex items-center justify-between`): → `flex flex-wrap items-start justify-between gap-2`, y la botonera `flex gap-2` → `flex flex-wrap gap-2 max-md:[&>button]:min-h-[44px]`. Tabla de movimientos → condicional; tarjeta:

```tsx
<TarjetaFila key={k.id}
  titulo={new Date(k.created_at).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })}
  subtitulo={/* Inventory */ <span className={movColor(k.movement_type)}>{k.movement_type}</span>
            /* HQInventory */ <span className={`dax-badge ${movementColor(k.movement_type)}`}>{tipoMovimiento(k.movement_type)}</span>}
  importe={<span className={movColor(k.movement_type)}>{k.qty_change > 0 ? '+' : ''}{k.qty_change}</span>}
  datos={[
    { etiqueta: 'Saldo', valor: k.qty_after },
    { etiqueta: 'Ref.', valor: <span className="font-mono">{k.reference ?? '—'}</span> },
    /* solo Inventory */ { etiqueta: 'Por', valor: k.user_name },
  ]}
/>
```
Los helpers de color/tipo ya existen en cada archivo (Inventory `movColor` l.87; HQInventory `movementColor` l.99 y `tipoMovimiento`); no se duplican.

- [ ] **Step 3: Suite + build verdes. Commit** — `git commit -m "feat(inventario): existencias y kardex caben en telefono en Inventario y Existencias HQ"`.

---

### Task 7: Productos y Catálogo

**Files:**
- Modify: `frontend/src/pages/inventory/Products.tsx` (ImportModal l.72 `grid-cols-2`, l.155 `grid-cols-3`; cabecera l.323-407; filtros l.410-424; tabla l.517-; `ui/Modal size="xl"` del formulario ya está)
- Modify: `frontend/src/pages/core/AdminCatalog.tsx` (l.51 hook; cabecera l.265-296; `TablaDesplazable`/tarjetas propias l.410-438 se conservan)
- Test: guardia (añadir `'inventory/Products.tsx'` y `'core/AdminCatalog.tsx'` a `PAGINAS`, y `'core/AdminCatalog.tsx'` a `SIN_TARJETA_FILA`)

- [ ] **Step 1: Añadir al test y ver que falla.**

- [ ] **Step 2: `Products.tsx`.**
  - ImportModal: l.72 `grid grid-cols-2 gap-2` (alcance) **se conserva** (dos columnas caben; la guardia lo permite). l.155 `grid grid-cols-3 gap-3 text-center` → `grid grid-cols-3 gap-2 sm:gap-3 text-center` con el comentario `{/* rejilla fija: 3 contadores cortos caben a 390 */}` en la línea anterior **y en la misma línea** de la clase (la guardia filtra por línea), y los `text-2xl` de los tres contadores → `text-xl sm:text-2xl`.
  - Cabecera l.323-407: ya es `flex … flex-wrap` con botones solo icono bajo `sm`. Se migra a `CabeceraPagina` con `titulo` = icono + h1 + chip y `acciones` = **todo el bloque de botones de hoy en su mismo orden** (contador, Importar, Etiquetas CSV, Generar códigos, Nuevo producto, conmutador lista/cuadrícula), conservando `aria-label` y `hidden sm:inline`. **No** se usa `accionPrincipal` (el kit la movería al frente y cambiaría el orden en escritorio).
  - Filtros l.410-424 → `BarraFiltros` (el input `dax-input max-w-xs` y el select `dax-input max-w-[200px]` quedan como hijos; bajo `sm` la barra los hace `w-full`).
  - Tabla l.517- (vista `list`) → condicional con `esTelefono`; la vista `grid` (l.432, ya responsiva `grid-cols-2 sm:…`) no cambia y sigue mandando si `viewMode === 'grid'`. Para no duplicar lógica, el cuerpo de cuatro celdas se extrae a componentes locales del archivo que usan **tanto el `<td>` como la tarjeta**: `PrecioDeFila({ p })` (cuerpo de la celda Precio, l.552-582: `priceRange`, `grupoDeVariantes`, `SINGULAR_GRUPO`), `ExistenciaDeFila({ p, abierto, onToggle })` (celda Stock, l.583-619, incluido el botón "de N tallas" con `aria-expanded`), `EstadoDeFila({ p })` (celda Estado, l.620-635, los `Badge` "POS activo"/"POS inactivo") y `AccionesDeFila({ p })` (última columna, l.637-648). La tarjeta:

```tsx
<TarjetaFila key={p.id}
  titulo={p.name}
  subtitulo={<span className="font-mono text-slate-400">{p.sku}</span>}
  importe={<PrecioDeFila p={p} />}
  estado={<EstadoDeFila p={p} />}
  datos={[
    { etiqueta: 'Departamento', valor: p.department_name ?? '—' },
    { etiqueta: 'Existencia', valor: <ExistenciaDeFila p={p} abierto={tallasAbiertas} onToggle={() => setExpandedVariantsId(tallasAbiertas ? null : p.id)} /> },
  ]}
  acciones={canEdit ? <AccionesDeFila p={p} /> : undefined}
/>
```
  Cuando `tallasAbiertas`, después de la tarjeta se pintan los sub-renglones (`expandVariantRows([p])`, l.650) como `TarjetaFila className="ml-4"` con `titulo` = nombre de la talla/color, `subtitulo` = SKU, `importe` = precio de la talla y `estado` = existencia, con los mismos formateos que las celdas de l.651-660. Los botones de `AccionesDeFila` llevan texto visible junto al icono (`<span className="md:sr-only">Editar</span>` no: el texto se muestra siempre en la tarjeta y en la tabla sigue como hoy; si hoy son solo icono, el componente recibe `conTexto?: boolean` y la tarjeta lo pasa `true`).

- [ ] **Step 3: `AdminCatalog.tsx`.** l.51 `const enTarjetas = useMediaQuery('(max-width: 767px)')` → `const enTarjetas = useEsTelefono()` (quitar el import de `useMediaQuery` si queda huérfano). Cabecera l.265-296 → `CabeceraPagina` con `titulo` = icono + h1, `descripcion` = "Gestión completa de productos · {org}", `accionPrincipal` = Link "Nuevo producto", `acciones` = Exportar + Vista completa. Las tarjetas propias l.411-436 se conservan.

- [ ] **Step 4: Suite + build verdes. Commit** — `git commit -m "feat(productos): Productos y Catalogo con cabecera del kit, filtros apilables y tarjetas en telefono"`.

---

### Task 8: guardia de overlays y rejillas (congela la deuda)

**Files:**
- Test: `frontend/src/__tests__/overlaysFueraDelKit.test.ts` (nuevo)

- [ ] **Step 1: Escribir el test.** Recorre `src/` (misma función `archivos()` de `src/__tests__/unSoloFormularioDeProducto.test.ts`, excluyendo `__tests__`), cuenta `fixed inset-0` por archivo (sin contar `components/ui/Modal.tsx` ni `components/ui/ConfirmDialog.tsx`) y compara con la lista congelada:

```ts
/** Overlays hechos a mano que existían el 2026-10-18 (deuda conocida; ver spec SP5).
 *  Para añadir uno nuevo: usa components/ui/Modal. Para quitar uno: bórralo de aquí. */
const CONOCIDOS: Record<string, number> = {
  '/components/branch/CashBranchView.tsx': 1, '/components/branch/MovementModal.tsx': 1, '/components/branch/OpenShiftModal.tsx': 1,
  '/components/branch/ProductsBranchView.tsx': 1, '/components/catalog/ProductAuditDrawer.tsx': 1, '/components/catalog/ProductBranchMatrix.tsx': 1,
  '/components/pos/modals/CardPaymentModal.tsx': 1, '/components/pos/modals/CashMovementModal.tsx': 1, '/components/pos/modals/CashPaymentModal.tsx': 1,
  '/components/pos/modals/CloseSessionModal.tsx': 1, '/components/pos/modals/CustomerModal.tsx': 1, '/components/pos/modals/MixedPaymentModal.tsx': 1,
  '/components/pos/modals/ProductDetailModal.tsx': 1, '/components/pos/modals/ReprintPinModal.tsx': 1, '/components/pos/modals/ReturnModal.tsx': 1,
  '/components/pos/modals/SaleSuccessModal.tsx': 1, '/components/pos/modals/SessionModal.tsx': 1, '/components/pos/modals/TransferPaymentModal.tsx': 1,
  '/components/pos/modals/VariantPickerModal.tsx': 1, '/components/pos/PrinterInstallWizard.tsx': 1, '/components/tables/TableFormModal.tsx': 1,
  '/pages/core/Brands.tsx': 1, '/pages/core/Departments.tsx': 1, '/pages/core/Organization.tsx': 1, '/pages/core/Users.tsx': 1,
  '/pages/crm/Customers.tsx': 1,
  '/pages/finance/CashHistory.tsx': 2, '/pages/finance/Expenses.tsx': 1, '/pages/finance/Purchases.tsx': 2,
  '/pages/hq/HQInventory.tsx': 1, '/pages/hq/HQReturns.tsx': 2, '/pages/hq/HQSalesLog.tsx': 1, '/pages/hr/HR.tsx': 1,
  '/pages/inventory/Boxes.tsx': 2, '/pages/inventory/Inventory.tsx': 1, '/pages/inventory/Logistics.tsx': 1, '/pages/inventory/Products.tsx': 1,
  '/pages/labels/Labels.tsx': 1, '/pages/pos/POS.tsx': 2, '/pages/sales/Quotes.tsx': 1, '/pages/sales/Returns.tsx': 2,
  '/pages/sales/SalesHistory.tsx': 1, '/pages/sales/Seguimiento.tsx': 1,
}
it('no aparece ningún overlay manual nuevo fuera de ui/Modal', () => { expect(encontrados).toEqual(CONOCIDOS) })
```
Al escribirlo, **regenerar la lista desde el árbol real** (`grep -rc "fixed inset-0" frontend/src --include=*.tsx | grep -v ":0"`) porque las tareas 5 ya quitaron `CustomerFormModal` y el segundo de `Customers`; la lista de arriba es la esperada tras las tareas 1-7 (Customers queda en 1). El test también comprueba que ningún archivo de `CONOCIDOS` falta (si alguien migra uno, debe borrarlo de la lista: eso es intencional, falla "para bien").

- [ ] **Step 2: Correr** — debe pasar a la primera si la lista coincide con el árbol; si no, la diferencia es un hallazgo (anotar y corregir la lista o el código).

- [ ] **Step 3: Commit** — `git commit -m "test(ui): congela el inventario de overlays manuales fuera de ui/Modal"`.

---

### Task 9: verificación de la ola y hallazgos (cierra también la T7 de la ola 1)

**Files:** Output `.superpowers/sdd/2026-10-18-sp5-responsivo-admin-ola-2/final/` (capturas, `desbordes.json`, `diff1440.json`, `diff/`), `.superpowers/sdd/2026-10-18-sp5-responsivo-admin-ola-2/ola-2-findings.md`

- [ ] `bash stack.sh down && bash stack.sh up` (reinicia Vite para que vea los cambios).
- [ ] `node capturas.mjs --out …/final --rutas <las 14>` (4 anchos, 2 temas) → `desbordes.json`: **cero** claves con `desborda` y cero con `scrollInterno` a 390/768/1024 en las 8 rutas de la ola 2 y sus acciones. En las 6 de la ola 1, cero `desborda` (la T7 de aquella ola nunca corrió; esto la cierra). Cada entrada que quede es un hallazgo con su elemento.
- [ ] `node diff1440.mjs baseline final` → **cero** píxeles distintos a 1440 en las 14 rutas (claro y oscuro) y sus acciones, **salvo** `ConfirmDialog` (no aparece en capturas) y lo que explique el cambio de cabecera a `CabeceraPagina` si mueve 1 px el `h1` (se mira el recorte y se decide: si es ≤ 2 px de alto de fila, se acepta y se anota; si cambia el orden o el ancho de algo, es hallazgo).
- [ ] Tap targets a 390 y 768: lista de `tap < 44` de `desbordes.json` → cada botón de acción principal o de fila que mida menos es hallazgo.
- [ ] Escribir `ola-2-findings.md`: tabla ruta × ancho × tema con ✅/❌, lista de hallazgos con archivo:línea propuesto, y las rutas de las capturas a 390 para que el usuario las vea. Los hallazgos Important (desborde, scroll interno, diff a 1440 no explicado, tap < 44 en acción principal) **vuelven como fix round a la tarea dueña** antes de la Tarea 10.

---

### Task 10: docs y cierre

**Files:**
- Modify: `docs/FRONTEND_VIEWS.md` (nota en §1 l.40-41; marcar con "📱" las 8 rutas de la ola 1 y las 8 de la ola 2 en sus líneas: l.272 `/hq/inventory`, l.299 `/products`, l.307 `/inventory`, l.336 `/admin/catalog`, l.348 `/departments`, l.356 `/brands`, l.395 `/customers`, l.422 `/users`, más las de la ola 1)
- Modify: `CLAUDE.md` §5 (nueva receta tras la l.133, antes de §6)
- Modify: `docs/superpowers/plans/2026-10-01-responsivo-admin-ola-1.md` (marcar `- [x]` las casillas de T1-T6, T8 y T9 que este plan cerró; en T7 anotar "cerrada por SP5 ola 2, Tarea 9, 2026-10-18")
- Modify: `docs/superpowers/specs/2026-10-14-mega-plan-altas-docs-responsivo-agente-design.md` §4 SP5: una línea "Ejecutado 2026-10-18 con las decisiones de `plans/2026-10-18-sp5-responsivo-admin-ola-2.md` (kit `ui/`, 52 overlays, congruencia de botones diferida)".

- [ ] `docs/FRONTEND_VIEWS.md` §1: "Las vistas marcadas 📱 se adaptan a teléfono con el kit de `components/ui/` (`TarjetaFila`, `ListaTarjetas`, `BarraFiltros`, `CabeceraPagina`, `Modal` con `.dax-modal`); patrón en `docs/superpowers/specs/2026-09-30-responsivo-admin-design.md §4` y guardia en `src/pages/__tests__/responsivoOla2.test.ts` y `src/__tests__/overlaysFueraDelKit.test.ts`."
- [ ] `CLAUDE.md` §5, receta **"Hacer responsiva una pantalla de admin"** (6 líneas): 1) `const esTelefono = useEsTelefono()` (`hooks/useIsMobile.ts`, < 768); 2) cabecera → `CabeceraPagina`, filtros → `BarraFiltros`; 3) la `<table>` no se toca: `esTelefono ? <ListaTarjetas><TarjetaFila…/> : <table…>`, nunca `hidden md:block`; 4) rejillas: `grid-cols-N` siempre con prefijo (`grid-cols-1 sm:grid-cols-2`); 5) modales: `ui/Modal`, o `dax-modal` + `dax-modal-footer` si tienen cabecera propia; nunca un `fixed inset-0` nuevo (lo frena `overlaysFueraDelKit.test.ts`); 6) verificar con `capturas.mjs` a 390/768/1024 y `diff1440.mjs` contra baseline (herramienta en el scratchpad; receta en el plan de SP5).
- [ ] Commit `docs: patron responsivo del lado administrador (olas 1 y 2) y cierre del plan de la ola 1`, que incluye también este plan (`docs/superpowers/plans/2026-10-18-sp5-responsivo-admin-ola-2.md`) con sus casillas marcadas.
- [ ] Memoria (controlador): actualizar `responsivo-telefono.md` y `mega-plan-2026-10-ejecucion.md` con la ola 2, los hallazgos pendientes y los seguimientos (botones crudos, 8 overlays de la ola 3, `ProductDetailModal`).

### Cierre (manual, con permiso)

Merge a `main` + push (despliega), verificación de `/health` y del commit desplegado, y revisión en el teléfono real de la dueña de Eleven y de Mirna en Coqueta: abrir Productos, Clientes (estado de cuenta → pagar), Inventario (kardex → ajustar) y Usuarios. Las pantallas de la ola 3 (`Purchases`, `Expenses`, `Quotes`, `Seguimiento`, `Logistics`, `Boxes`, `HR`, `PresetHome`, gastro, `PrinterSettings`, `StoreScanner`) tienen su propio plan.
