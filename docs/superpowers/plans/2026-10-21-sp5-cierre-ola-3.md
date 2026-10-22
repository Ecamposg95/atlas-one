# SP5 cierre · Ola 3 responsiva, minors y congruencia de botones — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar SP5: las siete pantallas de admin que faltaban (Gastos, Compras, RR.HH., Cajas y contenedores, Logística, Cotizaciones, Pedidos) caben en teléfono con el kit `ui/`, sus 9 overlays a mano pasan a `ui/Modal`, se corrigen los minors M2–M7 de la verificación de la ola 2 y las clases `dax-btn-*` quedan declaradas como la única API de botones (sin codemod).

**Architecture:** Misma receta que la ola 2 (CLAUDE.md §5 "Hacer responsiva una pantalla de admin"): `useEsTelefono()` decide entre la `<table>` de siempre (escritorio intacto) y `ListaTarjetas` + `TarjetaFila`; cabecera con `CabeceraPagina`; filtros con `BarraFiltros`; diálogos con `components/ui/Modal`. Sin backend. Verificación con la herramienta Playwright del scratchpad (baseline a 1440 antes de tocar código, diff pixel a pixel después).

**Tech Stack:** React 18 + TS + Tailwind (frontend), vitest para las guardias estáticas, Playwright (scratchpad) para capturas.

**Spec:** `docs/superpowers/specs/2026-09-30-responsivo-admin-design.md` (§4 base común, §4.4 modales, §4.5 rejillas, §5 ola 3, §6 criterios) + sección SP5 de `docs/superpowers/specs/2026-10-14-mega-plan-altas-docs-responsivo-agente-design.md` + hallazgos `…/.worktrees/sp5-responsivo-admin/.superpowers/sdd/2026-10-18-sp5-responsivo-admin-ola-2/ola-2-findings.md` (M2–M7).

## Global Constraints

- **Escritorio no cambia** (spec §3): a 1440 × 900 cada ruta da 0 px de diferencia contra el baseline, salvo los modales que pasan a `ui/Modal` (diferencia aceptada y explicada en `findings.md`, como en la ola 2).
- Nunca `hidden md:block` / `md:hidden`: render condicional con `esTelefono ? … : …`. La `<table>` no se toca.
- Rejillas `grid-cols-3+` siempre con prefijo (`grid-cols-1 sm:grid-cols-…`) o con el comentario `rejilla fija:` en la misma línea.
- Tap targets ≥ 44 px bajo 768 (`dax-btn-icon`, `max-md:min-h-[44px]`, `TarjetaFila` ya lo impone a `acciones`).
- Modales nuevos solo con `components/ui/Modal`; un `fixed inset-0` nuevo lo frena `overlaysFueraDelKit.test.ts`.
- Sin backend, sin `print()`, sin secretos. Commits con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf`.
- Suite: `cd frontend && npx vitest run` verde; `npm run build` verde; `python3 scripts/presupuesto_bundle.py` ≤ 452,500 B; `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py` sin bajar de 1499 (no se toca backend).

## Review Focus

1. **Modal de Compras "Nueva OC" a 390:** la rejilla de artículos (`grid-cols-12`) cabe sin desborde y cada fila se puede borrar con un botón de 44 px (test estático de la Tarea 2 + captura `/purchases · nueva`).
2. **Detalle de cotización/pedido/OC en teléfono:** las líneas se pintan como lista, no como tabla de 4–5 columnas (criterio §6.2); en escritorio sigue la tabla (test de la Tarea 4: dos `<table` de detalle tras `esTelefono ?`).
3. **Escape cierra el detalle del cliente** (observación de la ola 2): `Customers.tsx` escucha `keydown` solo mientras `selected` existe y lo quita al desmontar (test Tarea 5).
4. **`ui/Button` sigue pintando lo mismo en gastro** (los 7 archivos que lo importan): `md` deja de duplicar padding (1.6 px) y `ghost` pasa a `.dax-btn-ghost`; la guardia de la Tarea 1 exige que la clase exista en `index.css`.
5. **Un overlay migrado que no se borre de `CONOCIDOS`** rompe `overlaysFueraDelKit.test.ts` (ya existe); la Tarea 6 corre la suite completa y las capturas.

---

### Task 0: Herramienta de capturas, datos de la ola 3 y baseline

**Files:**
- Scratchpad (no versionado): `/tmp/claude-1000/-mnt-d-Devs-atlas-one/88dd20d9-ffe0-4c18-b01a-da7647838260/scratchpad/sp5-cierre/capturas/{stack.sh,capturas.mjs,datos_muestra.py}` (copia de `modo-basico/capturas/`, ya hecha: puertos 8010/5180, `R=.worktrees/sp5-cierre`).

**Interfaces:**
- Produces: `node capturas.mjs --out DIR --rutas … --anchos 390,1440` con `RUTAS_OLA3 = ['/expenses','/purchases','/hr','/boxes','/logistics','/quotes','/seguimiento']` y acciones por ruta; baseline en `<workspace>/baseline/`.

- [ ] **Step 1: Datos de muestra de la ola 3 en `datos_muestra.py`**

Añadir al final de `cargar(...)` una llamada `cargar_ola3(db, org, branch, admin, cajero, planas)` y, fuera de `cargar`, la función. Idempotencia: `main()` ya no inserta nada si hay ≥ 12 clientes, así que para bases viejas se agrega en `main()` una segunda guarda: si `db.query(Expense).filter(Expense.organization_id == org.id).count() == 0` → `cargar_ola3(...)` + `commit()`. Imports nuevos: `from app.models.finance import Expense, PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus`, `from app.models.hr import Employee, EmployeeType`, `from app.models.logistics import BoxType, ContainerType, TransferOrder, TransferOrderLine, TransferStatus`.

```python
def cargar_ola3(db, org, branch, admin, cajero, planas):
    """Gastos, compras, cotizaciones/pedidos, transferencias, cajas y empleados (ola 3)."""
    oid = org.id
    for k, (cat, monto, desc) in enumerate((("SERVICIOS", "1250.00", "Luz CFE octubre"), ("ALQUILER", "9000.00", "Renta local"),
                                            ("SUMINISTROS", "340.50", "Bolsas y papel de ticket"), ("MANTENIMIENTO", "780.00", "Aire acondicionado"),
                                            ("MARKETING", "1500.00", "Anuncios en redes"), ("LOGÍSTICA", "220.00", "Envío de mercancía a cliente"),
                                            ("NÓMINA", "4200.00", "Semana 41"), ("OTRO", "99.90", None))):
        db.add(Expense(organization_id=oid, branch_id=branch.id, amount=D(monto), category=cat, description=desc,
                       user_id=admin.id if k % 2 else cajero.id, created_at=hace(k * 3, 2)))
    for k, (estado, prov) in enumerate(((PurchaseOrderStatus.DRAFT, "Textiles del Norte S.A. de C.V."),
                                        (PurchaseOrderStatus.ORDERED, "Calzado Levante"),
                                        (PurchaseOrderStatus.PARTIAL, "Distribuidora Ámbar"),
                                        (PurchaseOrderStatus.RECEIVED, "Abarrotes La Selva"))):
        po = PurchaseOrder(organization_id=oid, folio=f"OC-{k + 1:05d}", branch_id=branch.id, supplier_name=prov, status=estado,
                           notes="Entregar en bodega, horario de 9 a 14" if k == 1 else None, created_by_user_id=admin.id,
                           created_at=hace(10 - k * 2, 1))
        db.add(po)
        db.flush()
        for j in range(2 + k):
            v = planas[(k * 5 + j * 3) % len(planas)]
            db.add(PurchaseOrderLine(purchase_order_id=po.id, variant_id=v.id, product_name=v.product.name, sku=v.sku,
                                     qty_ordered=D(6 + j), qty_received=D(6 + j) if estado == PurchaseOrderStatus.RECEIVED else (D(2) if estado == PurchaseOrderStatus.PARTIAL else D(0)),
                                     unit_cost=v.cost or D("50.00")))
    # Cotizaciones (QUOTE, serie Q) y pedidos abiertos (ORDER, serie P, PENDING)
    for k, (tipo, serie, estado) in enumerate(((DocumentType.QUOTE, "Q", DocumentStatus.PENDING), (DocumentType.QUOTE, "Q", DocumentStatus.PAID),
                                               (DocumentType.QUOTE, "Q", DocumentStatus.CANCELLED), (DocumentType.ORDER, "P", DocumentStatus.PENDING),
                                               (DocumentType.ORDER, "P", DocumentStatus.PENDING))):
        cuando = hace(6 - k, 2, 15 * k)
        sd = SalesDocument(doc_type=tipo, status=estado, branch_id=branch.id, seller_id=admin.id, organization_id=oid,
                           series=serie, folio=k + 1, customer_id=None, created_at=cuando, updated_at=cuando,
                           card_surcharge_amount=D(0), tip_amount=D(0), change_given=D(0))
        db.add(sd)
        db.flush()
        total = D(0)
        for j in range(1 + k % 3):
            v = planas[(k * 9 + j * 4) % len(planas)]
            linea = (v.price * (1 + j)).quantize(D("0.01"))
            total += linea
            db.add(SalesLineItem(document_id=sd.id, variant_id=v.id, organization_id=oid, description=v.product.name,
                                 quantity=float(1 + j), unit_price=v.price, unit_cost=v.cost, discount_percent=D(0),
                                 total_line=linea, created_at=cuando, updated_at=cuando))
        sd.total_amount = total
        sd.subtotal = (total / D("1.16")).quantize(D("0.01"))
        sd.tax_amount = total - sd.subtotal
    for k, estado in enumerate((TransferStatus.REQUESTED, TransferStatus.PARTIALLY_FULFILLED, TransferStatus.COMPLETED)):
        t = TransferOrder(organization_id=oid, requesting_branch_id=branch.id, status=estado,
                          notes=["Urgente: se acabaron las tallas M", None, "Reposición semanal"][k], created_at=hace(5 - k, 3))
        db.add(t)
        db.flush()
        for j in range(2):
            v = planas[(k * 7 + j * 2) % len(planas)]
            db.add(TransferOrderLine(organization_id=oid, transfer_id=t.id, variant_id=v.id, qty_requested=D(3 + j),
                                     qty_received=D(3 + j) if estado == TransferStatus.COMPLETED else D(0)))
    for nombre, l, w, h in (("Contenedor 20 pies demo", 589, 235, 239), ("Camioneta 3.5 t demo", 420, 200, 190)):
        if not db.query(ContainerType).filter(ContainerType.name == nombre).first():  # name es único global
            db.add(ContainerType(organization_id=oid, name=nombre, inner_length=D(l), inner_width=D(w), inner_height=D(h), max_weight_kg=D(1000)))
    for nombre, l, w, h in (("Caja chica 30×20 demo", 30, 20, 15), ("Caja master 60×40 demo", 60, 40, 40)):
        if not db.query(BoxType).filter(BoxType.name == nombre).first():
            db.add(BoxType(organization_id=oid, name=nombre, outer_length=D(l), outer_width=D(w), outer_height=D(h)))
    for k, (nom, ape, tipo) in enumerate((("Juan", "Pérez García", EmployeeType.FULL_TIME), ("María Fernanda", "López de la Rosa Hernández", EmployeeType.PART_TIME),
                                          ("Luis", "Ramírez", EmployeeType.CONTRACTOR), ("Ana", "Torres", EmployeeType.FULL_TIME),
                                          ("Pedro", "Sánchez", EmployeeType.FULL_TIME))):
        db.add(Employee(organization_id=oid, first_name=nom, last_name=ape, employee_type=tipo, base_branch_id=branch.id if k % 2 == 0 else None,
                        hire_date=hace(400 - k * 60).date(), phone=f"55 1234 56{k:02d}", email_personal=f"{nom.split()[0].lower()}@ejemplo.mx"))
```

- [ ] **Step 2: Rutas y acciones de la ola 3 en `capturas.mjs`**

Después de `RUTAS_GERENTE`:

```js
const RUTAS_OLA3 = ['/expenses', '/purchases', '/hr', '/boxes', '/logistics', '/quotes', '/seguimiento']
```

En `RUTAS` incluir `...RUTAS_OLA3`. En `ACCIONES` añadir:

```js
  '/expenses':    [{ clave: 'modal', clic: 'button:has-text("Registrar Gasto")' }],
  '/purchases':   [{ clave: 'detalle', clic: 'table tbody tr button, [data-tarjeta-fila] button' },
                   { clave: 'modal', clic: 'button:has-text("Nueva OC")' }],
  '/hr':          [{ clave: 'modal', clic: 'button:has-text("Nuevo Empleado")' }],
  '/boxes':       [{ clave: 'modal', clic: 'button:has-text("Nuevo Contenedor")' }],
  '/logistics':   [{ clave: 'modal', clic: 'button:has-text("Nueva Solicitud")' }],
  '/quotes':      [{ clave: 'detalle', clic: 'table tbody tr button, [data-tarjeta-fila] button' }],
  '/seguimiento': [{ clave: 'detalle', clic: 'table tbody tr button, [data-tarjeta-fila] button' }],
```

- [ ] **Step 3: Levantar el stack y tomar el baseline (ANTES de tocar `frontend/src`)**

Run: `cd <scratchpad>/sp5-cierre/capturas && bash stack.sh up && node capturas.mjs --out <workspace>/baseline --anchos 390,1440 --rutas /expenses,/purchases,/hr,/boxes,/logistics,/quotes,/seguimiento,/products,/admin/catalog,/customers`
Expected: `backend {"status":"ok"} · vite 200`; capturas sin "selector no encontrado" para las acciones de la ola 3 (en baseline las acciones abren los overlays viejos); `baseline/desbordes.json` existe.

- [ ] **Step 4: Bajar el stack** — `bash stack.sh down` → `abajo`. No hay commit (todo vive en el scratchpad).

---

### Task 1: Botones del kit — `.dax-btn-ghost`, `ui/Button` sin padding duplicado, guardia y doc

**Files:**
- Modify: `frontend/src/index.css` (después de `.dax-btn-danger:disabled`, ~l.526)
- Modify: `frontend/src/components/ui/Button.tsx`
- Modify: `docs/FRONTEND_VIEWS.md` l.41
- Test: `frontend/src/__tests__/botonesDelKit.test.ts`

**Interfaces:**
- Produces: clase `.dax-btn-ghost`; `Button` con `sizeMap = { sm: 'text-xs', md: '', lg: 'text-sm px-6 py-3' }`.

- [ ] **Step 1: Escribir la guardia (falla)**

```ts
import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

const raiz = resolve(__dirname, '..')
const css = readFileSync(join(raiz, 'index.css'), 'utf8')
function archivos(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n)
    if (statSync(p).isDirectory()) return n === '__tests__' ? [] : archivos(p)
    return /\.tsx$/.test(n) && !/\.test\.tsx$/.test(n) ? [p] : []
  })
}
const PAGINAS_OLA3 = ['pages/finance/Expenses.tsx', 'pages/finance/Purchases.tsx', 'pages/hr/HR.tsx', 'pages/inventory/Boxes.tsx',
  'pages/inventory/Logistics.tsx', 'pages/sales/Quotes.tsx', 'pages/sales/Seguimiento.tsx']

describe('botones del kit: dax-btn-* es la API', () => {
  it('las cuatro variantes existen en index.css (ghost incluida)', () => {
    for (const v of ['primary', 'secondary', 'danger', 'ghost']) expect(css).toMatch(new RegExp(`\\.dax-btn-${v}\\s*\\{`))
  })
  it('ui/Button mapea a las clases y no duplica el padding en md', () => {
    const s = readFileSync(join(raiz, 'components/ui/Button.tsx'), 'utf8')
    expect(s).toMatch(/ghost: 'dax-btn-ghost'/)
    expect(s).toMatch(/md: ''/)
  })
  it('ningún archivo usa la clase `dax-btn` a secas (no existe en CSS)', () => {
    const culpables = archivos(raiz).filter((f) => /["'`\s]dax-btn(?![-\w])/.test(readFileSync(f, 'utf8'))).map((f) => f.replace(raiz, ''))
    expect(culpables).toEqual([])
  })
  it('las pantallas de la ola 3 no estilizan botones con style={{', () => {
    for (const p of PAGINAS_OLA3) {
      const s = readFileSync(join(raiz, p), 'utf8')
      expect(s, p).not.toMatch(/<(button|a)\b[^>]*style=\{\{/s)
    }
  })
})
```

- [ ] **Step 2: Correr** — `cd frontend && npx vitest run src/__tests__/botonesDelKit.test.ts`
Expected: FAIL en "ghost incluida", "no duplica el padding" y "dax-btn a secas" (`/pages/inventory/Products.tsx` usa `dax-btn dax-btn-icon`).

- [ ] **Step 3: CSS** — en `index.css`, tras `.dax-btn-danger:disabled { … }`:

```css
  /* ─── Botón fantasma (sin fondo; solo texto + hover) ── */
  .dax-btn-ghost {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background: transparent;
    color: var(--dax-text-muted);
    font-weight: 600;
    font-size: 0.75rem;
    padding: 0.5rem 1.1rem;
    border-radius: 10px;
    border: 1px solid transparent;
    cursor: pointer;
    transition: all 0.2s ease;
  }
  .dax-btn-ghost:hover:not(:disabled) { background: var(--dax-surface); color: var(--dax-text); }
  .dax-btn-ghost:disabled { opacity: 0.45; cursor: not-allowed; }
```

- [ ] **Step 4: `Button.tsx`** — `ghost: 'dax-btn-ghost'` en `variantMap`; `sizeMap = { sm: 'text-xs', md: '', lg: 'text-sm px-6 py-3' }` con el comentario `// el padding lo ponen las clases dax-btn-*; md no añade nada`.

- [ ] **Step 5: Products.tsx l.515** — `className="dax-btn dax-btn-icon …"` → `className="dax-btn-primary dax-btn-icon …"` (M3: en teléfono el "+" ahora tiene fondo; en escritorio ese botón ya se veía sin clase válida, así que la diferencia a 1440 se documenta en `findings.md`).

- [ ] **Step 6: Doc** — en `docs/FRONTEND_VIEWS.md` l.41 sustituir `` `Button` (`dax-btn-*`) `` por: `` botones: las clases `dax-btn-primary` / `dax-btn-secondary` / `dax-btn-danger` / `dax-btn-ghost` (+ `dax-btn-icon` para solo-icono en teléfono) son la API oficial; `ui/Button` es solo un envoltorio de esas clases (lo usa gastro). Guardia: `src/__tests__/botonesDelKit.test.ts` ``.

- [ ] **Step 7: Correr** — `npx vitest run src/__tests__/botonesDelKit.test.ts` → PASS 4/4. Luego `npx vitest run` completo → verde.

- [ ] **Step 8: Commit** — `feat(ui): dax-btn-* como API de botones, .dax-btn-ghost y guardia`

---

### Task 2: Gastos y Compras en teléfono (finance)

**Files:**
- Modify: `frontend/src/pages/finance/Expenses.tsx`, `frontend/src/pages/finance/Purchases.tsx`
- Modify: `frontend/src/__tests__/overlaysFueraDelKit.test.ts` (quitar `/pages/finance/Expenses.tsx` y `/pages/finance/Purchases.tsx`)
- Test: `frontend/src/pages/__tests__/responsivoOla3.test.ts`

**Interfaces:**
- Produces: `responsivoOla3.test.ts` con `PAGINAS_OLA3` (las 7) y las mismas guardias que la ola 2 + "sin `fixed inset-0`" + "importa `Modal` del kit".

- [ ] **Step 1: Guardia (falla)** — `frontend/src/pages/__tests__/responsivoOla3.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/** Pantallas de la ola 3 (spec responsivo §5): el resto del admin. */
export const PAGINAS_OLA3 = ['finance/Expenses.tsx', 'finance/Purchases.tsx', 'hr/HR.tsx', 'inventory/Boxes.tsx',
  'inventory/Logistics.tsx', 'sales/Quotes.tsx', 'sales/Seguimiento.tsx']
/** Detalle con líneas: tabla en escritorio, lista en teléfono (criterio §6.2). */
const CON_DETALLE = ['finance/Purchases.tsx', 'sales/Quotes.tsx', 'sales/Seguimiento.tsx']

const fuente = (p: string) => readFileSync(resolve(__dirname, '..', p), 'utf8')
const REJILLA_SIN_PREFIJO = /(?<![\w:-])grid-cols-(?:[3-9]|1[0-2])\b/
const sinExcepciones = (s: string) => s.split('\n').filter((l) => !l.includes('rejilla fija:')).join('\n')

describe('ola 3 responsiva: el resto del admin', () => {
  it.each(PAGINAS_OLA3)('%s usa el hook, el kit y Modal', (p) => {
    const s = fuente(p)
    expect(s).toMatch(/useEsTelefono\(\)/)
    expect(s).toMatch(/<CabeceraPagina/)
    expect(s).toMatch(/<TarjetaFila/)
    expect(s).toMatch(/import \{ Modal \} from '\.\.\/\.\.\/components\/ui\/Modal'/)
    expect(s).not.toMatch(/fixed inset-0/)
  })
  it.each(PAGINAS_OLA3)('%s no tiene rejillas sin prefijo ni dos árboles montados', (p) => {
    const s = fuente(p)
    expect(sinExcepciones(s)).not.toMatch(REJILLA_SIN_PREFIJO)
    expect(s).not.toMatch(/hidden md:block|md:hidden/)
  })
  it.each(CON_DETALLE)('%s: la tabla de líneas del detalle solo en escritorio', (p) => {
    const s = fuente(p)
    expect((s.match(/<table/g) ?? []).length).toBe(2)
    expect((s.match(/esTelefono \?/g) ?? []).length).toBe(2)
  })
})
```

Run: `npx vitest run src/pages/__tests__/responsivoOla3.test.ts` → Expected: FAIL en las 7 (ninguna usa el hook).

- [ ] **Step 2: `Expenses.tsx`** — imports: `useEsTelefono`, `CabeceraPagina`, `BarraFiltros, ParFechas`, `ListaTarjetas`, `TarjetaFila`, `Modal`. `const esTelefono = useEsTelefono()`.
  - Cabecera: `<CabeceraPagina titulo={<div className="flex items-center gap-3"><i className="fa-solid fa-money-bill-wave text-indigo-400 text-xl" /><h1 className="text-2xl font-black text-white">Gastos</h1></div>} accionPrincipal={<button onClick={() => setModal(true)} className="dax-btn-primary text-xs"><i className="fa-solid fa-plus" /> Registrar Gasto</button>} />`.
  - Filtros: `<BarraFiltros accion={<button onClick={() => load(startDate, endDate, filterCat)} className="dax-btn-primary text-xs"><i className="fa-solid fa-search" /> Filtrar</button>}><select …className="dax-input text-xs max-w-[160px]">…</select><ParFechas><input type="date" … className="dax-input w-36 text-xs" /><input type="date" … /></ParFechas></BarraFiltros>`.
  - Lista: `{esTelefono ? (<ListaTarjetas cargando={loading} vacio={expenses.length === 0} textoVacio="Sin gastos en este período" className="p-3">{expenses.map((e) => <TarjetaFila key={e.id} titulo={e.description ?? e.category} subtitulo={`${fecha(e.created_at)} · ${e.branch_name ?? '—'} · ${e.user_name ?? '—'}`} importe={<span className="text-red-400">{formatCurrency(e.amount)}</span>} estado={<span className="dax-badge dax-badge-slate">{e.category}</span>} acciones={<button onClick={() => handleDelete(e)} aria-label={`Eliminar gasto de ${formatCurrency(e.amount)}`} className="dax-btn-danger text-xs"><i className="fa-solid fa-trash" /> Eliminar</button>} />)}</ListaTarjetas>) : ( …la tabla de hoy sin cambios… )}` dentro del mismo `<DaxCard padding={false}>`. Helper local `const fecha = (s: string) => new Date(s).toLocaleDateString('es-MX', { day: '2-digit', month: 'short' })` reutilizado por la celda de la tabla. El botón de la papelera de la tabla recibe `dax-btn-icon` y `aria-label`.
  - Modal: `<Modal open={modal} onClose={() => setModal(false)} title="Nuevo Gasto" size="sm" footer={<><button onClick={() => setModal(false)} className="dax-btn-secondary flex-1">Cancelar</button><button onClick={handleCreate} disabled={…} className="dax-btn-primary flex-1 justify-center disabled:opacity-40">…</button></>}>{…los tres campos…}</Modal>`. Se elimina el overlay `fixed inset-0`.

- [ ] **Step 3: `Purchases.tsx`** — mismos imports + `Badge` ya está. 
  - Cabecera igual que Gastos (icono `fa-shopping-cart`, "Compras", `accionPrincipal` "Nueva OC").
  - Chips de estado: `className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors max-md:min-h-[44px] ${…}`}`.
  - Lista: `esTelefono ? <ListaTarjetas …>{orders.map((o) => <TarjetaFila key={o.id} titulo={o.folio ?? `OC-${o.id}`} subtitulo={`${o.supplier_name} · ${o.branch_name ?? '—'} · ${fecha(o.created_at)}`} importe={formatCurrency(o.total)} estado={<Badge variant={statusVariant(o.status)}>{STATUS_LABELS[o.status]}</Badge>} onClick={() => setSelected(o)} />)}</ListaTarjetas> : tabla`. Ojo del renglón de la tabla: `className="dax-btn-icon text-slate-500 hover:text-white text-xs" aria-label={`Ver ${o.folio ?? `OC-${o.id}`}`}`.
  - Detalle: `<Modal open={!!selected} onClose={() => setSelected(null)} title={<span>Orden de compra <span className="font-mono text-indigo-400">{selected.folio ?? `OC-${selected.id}`}</span></span>} size="lg" footer={ selected && (… los tres botones condicionados, mismos handlers …) }>` con el cuerpo: datos (proveedor, estado, notas) + `{esTelefono ? (<ul className="divide-y divide-slate-700/40 text-xs mb-4">{lines.map(l => <li key={l.id} className="py-2 flex justify-between gap-3"><span className="min-w-0"><span className="block font-semibold text-white truncate">{l.product_name}</span><span className="block font-mono text-slate-500">{l.sku ?? '—'} · {l.qty_received}/{l.qty_ordered} recibidas</span></span><span className="tabular-nums shrink-0">{formatCurrency(l.unit_cost)}</span></li>)}</ul>) : (<table …igual…>)}` + total. Como `Modal` exige `children` siempre, el cuerpo va envuelto en `{selected && (…)}`.
  - Nueva OC: `<Modal open={modal} onClose={() => setModal(false)} title="Nueva Orden de Compra" size="lg" footer={…Cancelar/Crear OC…}>`; rejilla de artículos: `grid grid-cols-2 sm:grid-cols-12 gap-1 items-center` con `col-span-2 sm:col-span-4` (producto), `col-span-1 sm:col-span-2` (SKU), `col-span-1 sm:col-span-2` (cant.), `col-span-1 sm:col-span-3` (costo) y el botón de quitar `dax-btn-icon col-span-1 sm:col-span-1 text-center` con `aria-label="Quitar artículo"`.

- [ ] **Step 4: `overlaysFueraDelKit.test.ts`** — borrar las dos entradas de finance.

- [ ] **Step 5: Correr** — `npx vitest run src/pages/__tests__/responsivoOla3.test.ts src/__tests__/overlaysFueraDelKit.test.ts src/__tests__/botonesDelKit.test.ts`
Expected: ola 3 PASS para `finance/*` (las otras 5 siguen en rojo), overlays PASS, botones PASS. `npx tsc --noEmit -p .` sin errores.

- [ ] **Step 6: Commit** — `feat(responsivo): Gastos y Compras en teléfono con el kit y Modal`

---

### Task 3: RR.HH., Cajas y contenedores y Logística en teléfono

**Files:**
- Modify: `frontend/src/pages/hr/HR.tsx`, `frontend/src/pages/inventory/Boxes.tsx`, `frontend/src/pages/inventory/Logistics.tsx`
- Modify: `frontend/src/__tests__/overlaysFueraDelKit.test.ts` (quitar `/pages/hr/HR.tsx`, `/pages/inventory/Boxes.tsx`, `/pages/inventory/Logistics.tsx`)

- [ ] **Step 1: `HR.tsx`** — cabecera con `CabeceraPagina` (icono `fa-user-tie`, "Recursos Humanos", `accionPrincipal` "Nuevo Empleado"). Buscador: `<BarraFiltros><input … className="dax-input flex-1 text-sm" /></BarraFiltros>`. Lista: `esTelefono ? <ListaTarjetas cargando={loading} vacio={filtered.length === 0} textoVacio="Sin empleados" className="p-3">{filtered.map((e) => <TarjetaFila key={e.id} titulo={employeeFullName(e)} subtitulo={branches.find((b) => b.id === e.base_branch_id)?.name ?? 'HQ'} estado={<Badge …>{typeLabel(…)}</Badge>} datos={[{ etiqueta: 'Ingreso', valor: fechaIngreso(e) }, { etiqueta: 'Teléfono', valor: e.phone ?? '—' }]} acciones={<button onClick={() => openEdit(e)} aria-label={`Editar a ${employeeFullName(e)}`} className="dax-btn-secondary text-xs"><i className="fa-solid fa-pen" /> Editar</button>} />)}</ListaTarjetas> : tabla` (el lápiz de la tabla recibe `dax-btn-icon` + `aria-label`). Helper `fechaIngreso(e)` compartido. Modal: `<Modal open={modal !== null} onClose={() => setModal(null)} title={modal === 'create' ? 'Nuevo Empleado' : 'Editar Empleado'} size="md" footer={…Cancelar/Guardar…}>`; las tres rejillas `grid-cols-2` → `grid-cols-1 sm:grid-cols-2`.

- [ ] **Step 2: `Boxes.tsx`** — cabecera con `CabeceraPagina` (`accionPrincipal` = el botón de hoy que depende de `tab`). Pestañas: añadir `max-md:min-h-[44px]`. Listas: en cada pestaña `esTelefono ? <ListaTarjetas vacio={…} textoVacio="Sin tipos de contenedor registrados" className="p-3">{containers.map((c) => <TarjetaFila key={c.id} titulo={c.name} subtitulo={`#${c.id} · ${dims(…)}`} />)}</ListaTarjetas> : tabla` (ídem cajas). Los dos modales → `Modal` `size="md"` con `footer`; la rejilla `grid-cols-3` de Largo/Ancho/Alto se conserva con `{/* rejilla fija: 3 números cortos caben a 390 */}` en la misma línea.

- [ ] **Step 3: `Logistics.tsx`** — cabecera con `CabeceraPagina` (`accionPrincipal` "Nueva Solicitud"). Lista: `esTelefono ? <ListaTarjetas cargando={loading} vacio={orders.length === 0} textoVacio="Sin solicitudes de transferencia" className="p-3">{orders.map((o) => <TarjetaFila key={o.id} titulo={`TR-${o.id}`} subtitulo={branchName(o.requesting_branch_id)} estado={<span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${STATUS_CLASS[o.status]}`}>{STATUS_LABEL[o.status]}</span>} datos={[{ etiqueta: 'Fecha', valor: fmtDate(o.created_at) }, { etiqueta: 'Notas', valor: o.notes ?? '—' }]} />)}</ListaTarjetas> : tabla`. Modal → `Modal` `size="lg"` `closeOnBackdrop={false}` (tiene líneas capturadas) con `footer` Cancelar/Enviar Solicitud. Botones −/+ de las líneas: `w-6 h-6 max-md:w-11 max-md:h-11`, el de quitar `dax-btn-icon` + `aria-label="Quitar"`.

- [ ] **Step 4: `overlaysFueraDelKit.test.ts`** — borrar HR, Boxes y Logistics.

- [ ] **Step 5: Correr** — mismos tests que la Tarea 2 → ola 3 PASS para 5 de 7; overlays PASS; `tsc` limpio.

- [ ] **Step 6: Commit** — `feat(responsivo): RR.HH., Cajas y Logística en teléfono con el kit y Modal`

---

### Task 4: Cotizaciones y Pedidos en teléfono

**Files:**
- Modify: `frontend/src/pages/sales/Quotes.tsx`, `frontend/src/pages/sales/Seguimiento.tsx`
- Modify: `frontend/src/__tests__/overlaysFueraDelKit.test.ts` (quitar `/pages/sales/Quotes.tsx`, `/pages/sales/Seguimiento.tsx`)

- [ ] **Step 1: `Quotes.tsx`** — cabecera con `CabeceraPagina` (`accionPrincipal` = el `<Link to="/quotes/new" className="dax-btn-primary text-xs">`). Lista: `esTelefono ? <ListaTarjetas cargando={loading} vacio={quotes.length === 0} textoVacio="Sin cotizaciones" className="p-3">{quotes.map((q) => <TarjetaFila key={q.id} titulo={quoteLabel(q)} subtitulo={`${fecha(q.created_at)} · ${q.customer_name ?? 'Sin cliente'}`} importe={formatCurrency(q.total_amount)} estado={<Badge …>{q.status}</Badge>} onClick={() => setSelected(q)} />)}</ListaTarjetas> : tabla` (`ErrorState` se mantiene fuera del condicional: `loadError ? <ErrorState/> : esTelefono ? … : …`). Ojo: `dax-btn-icon` + `aria-label={`Ver ${quoteLabel(q)}`}`. Detalle → `Modal size="lg"` con `title` = etiqueta, cuerpo con datos + `esTelefono ? <ul>…</ul> : <table>` (líneas: `description ?? sku`, `quantity × unit_price`, `total_line`) + totales; `footer` solo si `selected.status === 'PENDING'` (Convertir a Venta + Eliminar con `aria-label="Eliminar cotización"`).

- [ ] **Step 2: `Seguimiento.tsx`** — cabecera con `CabeceraPagina` (`acciones` = contador + Actualizar). Lista igual que Cotizaciones (titulo `saleLabel(s)`, subtitulo `${s.branch_name ?? '—'} · ${fechaHora(s.created_at)} · ${s.customer_name ?? 'Público general'}`, importe en verde, estado `Badge blue`). Detalle → `Modal size="lg"` con lista/tabla de líneas y total.

- [ ] **Step 3: `overlaysFueraDelKit.test.ts`** — borrar Quotes y Seguimiento.

- [ ] **Step 4: Correr** — `npx vitest run src/pages/__tests__/responsivoOla3.test.ts src/__tests__/overlaysFueraDelKit.test.ts` → PASS completo (7/7 + detalle 3/3); `tsc` limpio.

- [ ] **Step 5: Commit** — `feat(responsivo): Cotizaciones y Pedidos en teléfono con el kit y Modal`

---

### Task 5: Minors M2, M4, M5, Escape en el detalle del cliente y M7

**Files:**
- Modify: `frontend/src/components/products/ProductBasicsSection.tsx` (botón Sugerir), `ProductBranchMatrixSection.tsx` (Seleccionar todas / Ninguna), `frontend/src/pages/core/AdminCatalog.tsx:373` (OK), `frontend/src/pages/crm/Customers.tsx` (RFC + Escape), `frontend/src/components/layout/BranchSwitcher.tsx` (botón Sucursal), `frontend/src/pages/sales/Returns.tsx:132`, `frontend/src/pages/hq/HQReturns.tsx:149` (pestañas), `frontend/src/pages/hq/HQOperations.tsx:738` (Marcar leídas)
- Test: `frontend/src/pages/crm/__tests__/customersEscape.test.ts` (estático)

- [ ] **Step 1: Test (falla)**

```ts
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const s = readFileSync(resolve(__dirname, '../Customers.tsx'), 'utf8')
describe('detalle del cliente (overlay propio)', () => {
  it('cierra con Escape mientras hay un cliente seleccionado', () => {
    expect(s).toMatch(/e\.key === 'Escape'/)
    expect(s).toMatch(/addEventListener\('keydown'/)
    expect(s).toMatch(/removeEventListener\('keydown'/)
  })
  it('el RFC no se sale de su tarjeta a 390', () => {
    expect(s).toMatch(/font-mono text-sm text-slate-400 break-all/)
  })
})
```

Run: `npx vitest run src/pages/crm/__tests__/customersEscape.test.ts` → FAIL 2/2.

- [ ] **Step 2: `Customers.tsx`** — tras los `useState`: 

```ts
  // El detalle es un overlay propio (cabecera con editar/eliminar): no pasa por ui/Modal, así que Escape se escucha aquí.
  useEffect(() => {
    if (!selected) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setSelected(null) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [selected])
```

y el RFC: `className="font-mono text-sm text-slate-400 break-all"`.

- [ ] **Step 3: M2** — `ProductBasicsSection.tsx` botón Sugerir: añadir `max-md:min-h-[44px]`; `ProductBranchMatrixSection.tsx` los dos botones: `dax-btn-secondary text-[11px] max-md:min-h-[44px]`.
- [ ] **Step 4: M4** — `AdminCatalog.tsx:373` añadir `min-w-[44px]` a la clase de los chips de aprobación.
- [ ] **Step 5: M7** — `BranchSwitcher.tsx` botón "Sucursal": añadir `className="max-md:min-h-[44px]"` (conserva el `style`); `Returns.tsx` y `HQReturns.tsx` pestañas: `… rounded-md text-sm font-semibold transition-colors max-md:min-h-[44px] …`; `HQOperations.tsx` "Marcar leídas": `… transition max-md:min-h-[44px] max-md:px-2`.
- [ ] **Step 6: Correr** — `npx vitest run` completo → verde; `tsc` limpio.
- [ ] **Step 7: Commit** — `fix(responsivo): minors de la ola 2 (taps, RFC, Escape en el detalle del cliente, shell)`

---

### Task 6: Verificación con capturas, findings y doc

**Files:**
- Modify: `docs/FRONTEND_VIEWS.md` (marcar 📱 las 7 vistas y nombrar `responsivoOla3.test.ts` junto a la ola 2 en l.43)
- Scratch: `<workspace>/final/`, `<workspace>/findings.md`

- [ ] **Step 1: Suite completa** — `npx vitest run` → todo verde; `npm run build` → OK; `python3 scripts/presupuesto_bundle.py` → ≤ 452,500; `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py` → 1499 passed (sin cambios de backend).
- [ ] **Step 2: Capturas** — `bash stack.sh up && node capturas.mjs --out <workspace>/final --anchos 390,1440 --rutas <las 10 de la Tarea 0> && node diff1440.mjs <workspace>/baseline <workspace>/final && bash stack.sh down`.
Expected: desborde 0, scroll interno 0 a 390 en las 7 rutas (incluidas acciones); taps < 44 a 390: solo nada o lo que se explique; diff 1440: 0 px en las páginas; distinto de 0 solo en las claves `modal`/`detalle` (ui/Modal) y en `/products` (M3, botón ahora con `dax-btn-primary`).
- [ ] **Step 3: `findings.md`** en el workspace con la tabla ruta × ancho × tema, los Important (si hay → fix en esta misma tarea, re-captura) y los Minor diferidos.
- [ ] **Step 4: Doc** — `docs/FRONTEND_VIEWS.md`: añadir 📱 a Gastos, Compras, RR.HH., Cajas, Logística, Cotizaciones y Pedidos y citar `responsivoOla3.test.ts`.
- [ ] **Step 5: Commit** — `docs(responsivo): ola 3 verificada y marcada en FRONTEND_VIEWS`
