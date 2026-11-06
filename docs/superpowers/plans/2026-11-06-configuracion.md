# Configuración (antes Impresora) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El módulo Impresora pasa a llamarse Configuración (`/configuracion`) y recupera el botón Abrir cajón para caja y gerente, más las funciones de cajón y de instalación que se perdieron.

**Architecture:** Sin tablas ni columnas nuevas. El cajón se abre por el agente local de cada PC (`POST /drawer/open`, ya existe en Atlas-Print-Agent 3.1.0). Una tarjeta `CajonCard` compartida la usan las dos vistas; la de admin se ordena en pestañas Impresoras / Cajón / Ticket sin partir el componente de 1,389 líneas. La apertura manual deja rastro en `cash_audit_log`.

**Tech Stack:** FastAPI + SQLAlchemy, React + Vite + TS, pytest, vitest, Playwright para capturas.

**Spec:** este documento; el usuario pidió plan y PR directamente (2026-11-06). Las rulings de abajo hacen de spec.

## Diagnóstico (qué se perdió y cuándo)

| Qué | Hoy en Atlas One | Origen |
|---|---|---|
| Botón **Abrir cajón ahora** | Solo admin y dueño | `2120e540` (2026-09-29) dio a caja y gerente una pantalla simple sin él |
| Interruptor **Abrir cajón al imprimir** | Solo admin y dueño, y no se guarda hasta pulsar Guardar | Mismo commit. El backend sí deja al gerente (`branches.py:159`) |
| Instalar impresora, descargar agente, logo, editor de ticket | El gerente los perdió; la cajera no tiene ni la descarga del agente | Mismo commit |
| **Cobro en efectivo sin ticket abre el cajón** | No abre: la orden viaja dentro de los bytes del ticket | Atlas-Rmazh lo corrigió (`openDrawerOnly`); aquí nunca llegó |
| **Venta offline en efectivo abre el cajón** | No abre | Igual |
| **Cerrar turno abre el cajón** | No abre. `build_cash_cut_bytes(open_drawer=)` existe pero el endpoint nunca lo pasa | Rmazh sí lo manda al cerrar |
| Teléfono | Banner rojo de "agente offline" que no aplica | Pendiente de la auditoría de cajera en teléfono |

## Rulings

- **Ruling: la URL cambia a `/configuracion` y `/printer-settings` redirige** — el usuario renombró el módulo; la receta "Retirar una URL" de CLAUDE.md §5 ya cubre el redirect — si fuera mal, basta volver a la URL vieja sin tocar datos.
- **Ruling: el gerente vuelve a la pantalla completa** — responde por la sucursal, el backend ya se lo permite y Rmazh hace lo mismo — si no se quiere, es una línea en `vistaDeConfiguracion`.
- **Ruling: la cajera abre el cajón pero no cambia el interruptor** — `2120e540` dejó a propósito que nada de su pantalla escriba en la sucursal — Rmazh sí la deja; se abre si lo piden.
- **Ruling: la apertura manual se audita** — no estaba pedido, pero dar a la caja un botón que abre el cajón sin venta es el hueco clásico de faltantes, y `TICKET_REPRINTED` ya marca el patrón. Es informativo: nunca frena la apertura, y sin red se pierde el registro — hoy solo se ve en `/platform/cash-audit`.
- **Ruling: pestañas dentro de `PrinterSettings`, sin partirlo** — el estado (`config`, `save`) es uno solo; Rmazh partió el suyo en 1,000 líneas y aquí no hace falta para este PR — queda deuda de tamaño, no de comportamiento.
- **Ruling: el interruptor del cajón guarda al momento** — en una pestaña propia, depender del Guardar de la cabecera lo pierde en silencio.

**Fuera de este PR:** indicador de impresora en la barra del POS, fuente y columnas del ticket (`ticket_font`, `printer_cols`), Bluetooth, ver la auditoría del cajón desde el panel del dueño.

## Global Constraints

- `main` es producción: el PR no se fusiona sin permiso explícito.
- Sin columnas ni tablas nuevas: `event_type` de `cash_audit_log` es `String(40)` y no pide migración.
- `app/routers/sales.py::create_sale` no se toca. Lo del POS corre después de registrar la venta y nunca la bloquea.
- Botones con clases del kit (`dax-btn-*`); teléfono con `useEsTelefono`, render condicional, sin `hidden`; objetivos táctiles de 44 px.
- Textos en español llano. La palabra visible es **Configuración**.

## Review Focus

1. **Cajera sin permiso a la URL nueva:** si `/configuracion` falta en `ROLE_ROUTES` queda fuera de su propia pantalla. Lo fija la prueba de `navConfig` en la Tarea 4.
2. **Reimprimir un corte viejo no debe abrir el cajón:** solo el cierre manda `open_drawer`. Prueba de la Tarea 1 (por omisión no abre) y de la Tarea 5 (quién lo manda).
3. **Sucursal con el interruptor apagado:** ni el cobro sin ticket ni el corte abren el cajón. Pruebas en Tareas 1 y 2.
4. **Pago sin efectivo o impresora Bluetooth:** no se llama al agente. Pruebas de `debeAbrirCajonSinTicket` y `motivoSinCajon` en la Tarea 2.
5. **Falla la auditoría con el cajón ya abierto:** la cajera no ve un error. Prueba de `abrirCajonManual` en la Tarea 2.

---

### Task 1: Backend — el corte puede abrir el cajón y la apertura manual queda registrada

**Files:**
- Modify: `app/models/cash_audit.py`, `app/routers/printer.py`
- Test: `tests/test_printer_cajon.py`

**Interfaces:**
- Produces: `POST /api/printer/print-cash-cut` acepta `open_drawer: bool = False`; `POST /api/printer/drawer-opened` body `{printer_name?: str}` responde 204; `CashAuditEvent.DRAWER_OPENED_MANUAL`.

- [ ] **Step 1: Write the failing test**

`tests/test_printer_cajon.py` cubre: por omisión el corte no trae `CMD["DRAWER"]`; con `open_drawer=true` lo trae; con `Branch.open_drawer_on_print=False` no lo trae aunque se pida; `drawer-opened` deja una fila `DRAWER_OPENED_MANUAL` con usuario, sucursal, organización, `session_id` de su caja abierta e impresora; sin caja abierta también registra con `session_id=None`; sin token responde 401.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest -q -p no:warnings tests/test_printer_cajon.py`
Expected: FAIL (`open_drawer` ignorado, 404/405 en `drawer-opened`).

- [ ] **Step 3: Write minimal implementation**

```python
# app/models/cash_audit.py, debajo de REPRINT_PIN_FAILED
# Abrir el cajón sin venta: no mueve efectivo, pero es por donde se investiga un faltante.
DRAWER_OPENED_MANUAL = "DRAWER_OPENED_MANUAL"
```

```python
# app/routers/printer.py
class PrintCashCutRequest(BaseModel):
    session_id: int
    mode: str = "return_base64"
    # Solo el cierre de turno lo manda; reimprimir un corte viejo no abre el cajón.
    open_drawer: bool = False

# dentro de print_cash_cut_endpoint
session = _verify_session_access(db, req.session_id, current_user)
abrir = req.open_drawer and bool(getattr(session.branch, "open_drawer_on_print", False))
raw_bytes = printer.build_cash_cut_bytes(audit_data, open_drawer=abrir)

class DrawerOpenedRequest(BaseModel):
    printer_name: Optional[str] = None

@router.post("/drawer-opened", status_code=204)
def drawer_opened_endpoint(req, db, current_user, org_id):
    """Registra una apertura manual del cajón. La hace el agente local; esto solo deja el rastro."""
    from app.models.cash import CashSession
    from app.models.cash_audit import CashAuditEvent
    from app.services.cash_audit import audit_cash_event
    sesion = db.query(CashSession).filter(CashSession.user_id == current_user.id,
                                          CashSession.organization_id == org_id,
                                          CashSession.status == "OPEN").first()
    audit_cash_event(db, event_type=CashAuditEvent.DRAWER_OPENED_MANUAL, organization_id=org_id,
                     session_id=sesion.id if sesion else None,
                     branch_id=sesion.branch_id if sesion else current_user.branch_id,
                     user_id=current_user.id, payload={"printer_name": req.printer_name})
    db.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest -q -p no:warnings tests/test_printer_cajon.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/models/cash_audit.py app/routers/printer.py tests/test_printer_cajon.py
git commit -m "feat(impresion): el corte puede abrir el cajon y la apertura manual queda en la auditoria"
```

### Task 2: Frontend — reglas del cajón y tarjeta compartida

**Files:**
- Create: `frontend/src/utils/cajon.ts`, `frontend/src/utils/cajon.test.ts`, `frontend/src/components/pos/CajonCard.tsx`, `frontend/src/components/pos/__tests__/CajonCard.test.tsx`
- Modify: `frontend/src/api/printer.ts`

**Interfaces:**
- Produces: `motivoSinCajon(impresora: string | null, agente: boolean | null): string | null`; `pagoIncluyeEfectivo(pagos: {method?: string}[]): boolean`; `debeAbrirCajonSinTicket({ pagos, impresora, abreAlCobrar }): boolean`; `leerCajonAlCobrar(branchId): boolean` y `guardarCajonAlCobrar(branchId, valor): void` (localStorage, por omisión `true`, nunca lanza); `printerApi.abrirCajonManual(printerName): Promise<void>`; `printerApi.getCashCutBase64(sessionId, openDrawer = false)`; `<CajonCard impresora agenteEnLinea abreAlCobrar onCambiarAbreAlCobrar? />`.

- [ ] **Step 1: Write the failing test**

`cajon.test.ts`: `motivoSinCajon` da un texto si el agente no responde, si no hay impresora o si empieza con `BT:`, y `null` cuando todo está listo; `pagoIncluyeEfectivo` reconoce `CASH` y `EFECTIVO` sin importar mayúsculas y no cuenta `CARD`; `debeAbrirCajonSinTicket` es falso sin efectivo, sin impresora, con Bluetooth o con el interruptor apagado; `leerCajonAlCobrar` da `true` sin dato y devuelve lo guardado.

`CajonCard.test.tsx`: el botón llama a `abrirCajonManual` con la impresora; deshabilitado y con motivo visible si no hay impresora; sin `onCambiarAbreAlCobrar` no hay casilla y se lee el estado; con él, la casilla llama al callback; un fallo del agente se avisa con `toast.error`.

`printer.test.ts`: `abrirCajonManual` no rechaza si falla el registro de la auditoría, y sí rechaza si falla el agente sin llamar a la auditoría.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/utils/cajon.test.ts src/components/pos/__tests__/CajonCard.test.tsx`
Expected: FAIL (módulos inexistentes).

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/src/utils/cajon.ts
const CLAVE = (branchId: number) => `atlas_cajon_al_cobrar:${branchId}`

export function motivoSinCajon(impresora: string | null | undefined, agente: boolean | null): string | null {
  if (agente === false) return 'El agente de impresión no responde en esta PC.'
  if (!impresora) return 'Elige tu impresora primero.'
  if (impresora.startsWith('BT:')) return 'Las impresoras Bluetooth todavía no abren el cajón.'
  return null
}

export function pagoIncluyeEfectivo(pagos: { method?: string | null }[]): boolean {
  return pagos.some((p) => ['CASH', 'EFECTIVO'].includes((p.method ?? '').toUpperCase()))
}

export function debeAbrirCajonSinTicket({ pagos, impresora, abreAlCobrar }: {
  pagos: { method?: string | null }[]; impresora: string | null | undefined; abreAlCobrar: boolean
}): boolean {
  return abreAlCobrar && !!impresora && !impresora.startsWith('BT:') && pagoIncluyeEfectivo(pagos)
}

export function leerCajonAlCobrar(branchId: number | null | undefined): boolean {
  if (branchId == null) return true
  try { return localStorage.getItem(CLAVE(branchId)) !== '0' } catch { return true }
}

export function guardarCajonAlCobrar(branchId: number, valor: boolean): void {
  try { localStorage.setItem(CLAVE(branchId), valor ? '1' : '0') } catch { /* sin almacenamiento, queda el valor por omisión */ }
}
```

```ts
// frontend/src/api/printer.ts
abrirCajonManual: async (printerName: string): Promise<void> => {
  await printerApi.openDrawerViaAgent(printerName)
  // El cajón ya se abrió: un fallo del registro no es un error para la cajera.
  client.post('/printer/drawer-opened', { printer_name: printerName }).catch(() => {})
},
getCashCutBase64: async (sessionId: number, openDrawer = false): Promise<string> => {
  const { data } = await client.post('/printer/print-cash-cut', { session_id: sessionId, open_drawer: openDrawer })
  return data.content_base64 ?? data.base64 ?? ''
},
// printCashCut solo se usa al cerrar turno: pasa openDrawer = true.
```

`CajonCard` es una `DaxCard` con título "Cajón de dinero", casilla "Abrir cajón al imprimir ticket" (o texto de estado para quien no la administra), botón `dax-btn-secondary w-full min-h-[44px]` "Abrir cajón ahora" y el motivo debajo cuando está deshabilitado.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/utils/cajon.test.ts src/components/pos/__tests__/CajonCard.test.tsx src/api`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/cajon.ts frontend/src/utils/cajon.test.ts frontend/src/components/pos frontend/src/api/printer.ts
git commit -m "feat(impresion): tarjeta del cajon con sus reglas"
```

### Task 3: Pantallas — vista de caja, gerente de vuelta y pestañas

**Files:**
- Create: `frontend/src/pages/pos/Configuracion.tsx` (sustituye a `PrinterSettingsPorRol.tsx`), `frontend/src/utils/vistaDeConfiguracion.ts` y su prueba (sustituyen a `vistaDeImpresora*`)
- Modify: `frontend/src/pages/pos/PrinterSettings.tsx`, `frontend/src/pages/pos/PrinterSettingsCajera.tsx`, `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `CajonCard`, `guardarCajonAlCobrar`, `printerApi.downloadAgentUrl`.
- Produces: `vistaDeConfiguracion(role): 'completa' | 'caja'`; `Configuracion` como export con nombre.

- [ ] **Step 1: Write the failing test**

`vistaDeConfiguracion.test.ts`: ADMINISTRADOR, DUEÑO y GERENTE → `completa`; CAJERO, `null`, `undefined` → `caja`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/utils/vistaDeConfiguracion.test.ts`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

- `PrinterSettings.tsx`: título "Configuración" con `fa-gear`; estado `seccion: 'impresoras' | 'cajon' | 'ticket'` con `role="tablist"`. Impresoras = pestañas de sistema, aviso del agente y columna izquierda; Cajón = `CajonCard`; Ticket = papel, logo y editor. Descargar agente e Instalar impresora solo en Impresoras; Guardar no sale en Cajón, que guarda al momento:

```ts
const cambiarAbreAlCobrar = async (valor: boolean) => {
  if (!branch?.id) return
  const antes = config.open_drawer_on_print
  setConfig((c) => ({ ...c, open_drawer_on_print: valor }))
  try {
    await client.put(`/branches/${branch.id}`, { open_drawer_on_print: valor })
    guardarCajonAlCobrar(branch.id, valor)
    showToast('Cajón actualizado')
  } catch {
    setConfig((c) => ({ ...c, open_drawer_on_print: antes }))
    showToast('No se pudo guardar el ajuste del cajón', 'error')
  }
}
```

- `PrinterSettingsCajera.tsx`: título "Configuración"; lee `open_drawer_on_print` junto con el ancho de papel y lo guarda con `guardarCajonAlCobrar`; agrega `CajonCard` sin callback; con el agente caído ofrece "Descargar agente"; en teléfono (`useEsTelefono`) no pinta el diagnóstico ni el aviso del agente, sino una tarjeta que explica que impresora y cajón se usan desde la PC de la caja y que el ticket se manda por WhatsApp al cobrar.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/utils/vistaDeConfiguracion.test.ts && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src/pages/pos frontend/src/utils frontend/src/App.tsx
git commit -m "feat(configuracion): pestanas, cajon para caja y gerente, y pantalla honesta en telefono"
```

### Task 4: Renombrar el módulo y la URL

**Files:**
- Modify: `frontend/src/components/layout/navConfig.ts`, `navPerfilBasico.ts`, sus pruebas, `frontend/src/App.tsx`, `frontend/src/copy/branchCopy.ts`, `frontend/src/pages/sales/SalesHistory.tsx`, `app/core/role_permissions.py`, `docs/FRONTEND_VIEWS.md`
- Test: `frontend/src/components/layout/__tests__/navConfig.test.ts`, `frontend/src/__tests__/configuracionRuta.test.ts`

- [ ] **Step 1: Write the failing test**

`navConfig.test.ts`: `routeTitle('/configuracion')` es `Configuración`, y CAJERO, GERENTE, ADMINISTRADOR y DUEÑO tienen `/configuracion` en `ROLE_ROUTES`. `configuracionRuta.test.ts`: `App.tsx` redirige `printer-settings` con `RedirigirConQuery a="/configuracion"` y ninguna pantalla enlaza a `/printer-settings`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/layout src/__tests__/configuracionRuta.test.ts`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Ítem de menú `{ label: 'Configuración', short: 'CFG', icon: 'fa-gear', url: '/configuracion', group: 'pos', sort: 7 }`; sustituir la URL en `ROLE_ROUTES`, los grupos y las pruebas. El grupo del menú de sucursal se llama `Sistema` (y su color en `navConfig.ts:61`) para no decir "Configuración > Configuración". En App:

```tsx
<Route path="configuracion" element={<RutaPorRol url="/configuracion"><Suspense fallback={<PageLoader />}><Configuracion /></Suspense></RutaPorRol>} />
<Route path="printer-settings" element={<RedirigirConQuery a="/configuracion" />} />
```

`SalesHistory.tsx`: "Elige tu impresora en Configuración primero". `role_permissions.py:222`: etiqueta "Configuración", ícono `fa-gear`, URL nueva.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: PASS (`rutasPerezosas` es inestable bajo carga; si cae, correrla sola).

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src app/core/role_permissions.py docs/FRONTEND_VIEWS.md
git commit -m "feat(configuracion): el modulo Impresora se llama Configuracion y vive en /configuracion"
```

### Task 5: POS — el cajón abre cuando no hay ticket y al cerrar turno

**Files:**
- Modify: `frontend/src/pages/pos/POS.tsx`, `frontend/src/api/printer.ts`
- Test: `frontend/src/pages/pos/__tests__/cajonPos.test.ts`

- [ ] **Step 1: Write the failing test**

`cajonPos.test.ts` lee el fuente, como `printer.test.ts` en Rmazh: tras un cobro con ticket se llama a `printViaAgent`; sin ticket, a `abrirCajonSinTicket(payments)`; en la rama offline, tras `enqueueSale`, también. El cierre de `POS.tsx` llama a `getCashCutBase64(closed.id, true)`, y ni `CashHistory.tsx` ni `reprintCut` de `CashBranchView.tsx` pasan `true`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/pos/__tests__/cajonPos.test.ts`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```ts
// POS.tsx: el interruptor de la sucursal, recordado para cuando no haya red.
useEffect(() => {
  if (!branch?.id) return
  client.get(`/branches/${branch.id}`)
    .then(({ data }) => guardarCajonAlCobrar(branch.id, data?.open_drawer_on_print ?? true))
    .catch(() => {})
}, [branch?.id])

/** Sin ticket no viajan los bytes que abren el cajón: se pide aparte. Nunca bloquea: la venta ya está. */
const abrirCajonSinTicket = (pagos: { method?: string | null }[]) => {
  if (!debeAbrirCajonSinTicket({ pagos, impresora: savedPrinterName, abreAlCobrar: leerCajonAlCobrar(branch?.id) })) return
  printerApi.openDrawerViaAgent(savedPrinterName!).catch(() => {
    showToast('No se pudo abrir el cajón — ábrelo manualmente', 'error')
  })
}

// En línea
if (saleId && shouldPrint) printViaAgent(saleId)
else if (!shouldPrint) abrirCajonSinTicket(payments)

// Sin red, tras enqueueSale: no hay ticket, el agente es local y sí responde.
abrirCajonSinTicket(payments)
```

Cierre de turno en `POS.tsx`: `printerApi.getCashCutBase64(closed.id, true)`. `printCashCut` (usado solo al cerrar en `CashBranchView.tsx`) pasa `true`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/pages/pos/__tests__/cajonPos.test.ts && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/pos frontend/src/api/printer.ts
git commit -m "fix(pos): el cajon abre en efectivo sin ticket, sin red y al cerrar turno"
```

### Task 6: Verificación y PR

- [ ] **Step 1:** `python3 -m pytest -q --ignore=tests/test_cash_complete.py` — un solo proceso por worktree.
- [ ] **Step 2:** `cd frontend && npx vitest run && npm run build` — revisa el presupuesto `presupuesto_bundle.json`.
- [ ] **Step 3:** Capturas a 390 y 1440 de `/configuracion` como cajera, gerente y admin, y comprobar el redirect de `/printer-settings`.
- [ ] **Step 4:** Revisión final de toda la rama.
- [ ] **Step 5:** `git push -u origin feat/configuracion` y `gh pr create --base main`. No fusionar.
