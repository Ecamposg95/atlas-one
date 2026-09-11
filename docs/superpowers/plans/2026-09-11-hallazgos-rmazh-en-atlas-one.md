# Hallazgos de Atlas-Rmazh en Atlas ONE — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Traer a Atlas ONE todo lo que Atlas-Rmazh trabajó entre el 27 de agosto y el 10 de septiembre de 2026 (ola de la cajera, corte con historia, escáner, latencia, nivel SUPERADMIN) más los pendientes de la comparación del 1 de septiembre, conservando la identidad visual de Atlas ONE.

**Architecture:** Los dos repos no comparten historia de git, así que nada llega por merge. Cada flujo de trabajo (W1…W10) vive en su propio worktree y rama `feat/rmazh-<nombre>` sobre `main`, y se ejecuta con un subagente por tarea. Donde el archivo de Atlas ONE es idéntico al de Rmazh en su commit base `b00b431`, el diff se aplica con `git apply`; donde diverge, se porta a mano leyendo el diff de Rmazh como referencia. **Nada se fusiona ni se sube antes de las 19:00 CST del 2026-09-11 sin indicación del usuario.**

**Tech Stack:** FastAPI + SQLAlchemy (backend, pruebas con pytest sobre SQLite), React + Vite + TypeScript (frontend, vitest + tsc). Python del sistema: `python3` (3.12) ya tiene las dependencias; no existe `.venv/`.

**Spec:** Este plan argumenta desde tres documentos de Rmazh, que el ejecutor debe leer:
- `/mnt/d/Devs/Atlas-Rmazh/docs/superpowers/audits/2026-09-07-experiencia-cajero.md` (hallazgos C-01…C-27)
- `/mnt/d/Devs/Atlas-Rmazh/docs/superpowers/specs/2026-09-08-mega-plan-cajera-design.md` (§4 sistema visual, §5 fixes F0–F9, §6 rebanadas U1–U7)
- `/mnt/d/Devs/Atlas-Rmazh/docs/superpowers/specs/2026-09-09-superadmin-grupo-design.md` (piel C, tablero, reportes de dinero)
Y de la comparación previa en este repo: `docs/audits/2026-09-01-comparacion-atlas-rmazh.md`.

## Global Constraints

- **Decisión del usuario (2026-09-11): se conserva la identidad visual de Atlas ONE.** No se tocan los valores de `--dax-*` en `frontend/src/index.css`, ni el acento por vertical (`--p-accent`), ni el oscuro índigo, ni el `Sidebar.tsx` (cajón móvil). Las rebanadas U1 (tokens) y U2 (sidebar píldora) de Rmazh **quedan fuera**. Toda piel nueva consume los tokens que ya existen aquí.
- **Decisión del usuario (2026-09-11): el tablero SUPERADMIN se trae como vista por organización**, no como "grupo" de un solo dueño.
- **Sin merge ni push antes de las 19:00 CST** del 2026-09-11, salvo indicación explícita del usuario. Cada flujo termina con su rama local lista y su reporte.
- Reglas de oro de `CLAUDE.md`: toda query filtra `organization_id`; FKs a UUID son `String(36)`; columnas nuevas en tablas existentes van como ALTER idempotente en `scripts/railway_init.py`; **no Alembic**; `create_sale` se cambia con extremo cuidado; nada de `print()` de debug.
- Comandos de verificación (desde la raíz del worktree):
  - Backend: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py`
  - Frontend: `cd frontend && npx vitest run && npx tsc --noEmit && npm run build`
  - Línea base antes de tocar nada: la suite backend tiene fallos preexistentes (~35 failed + 4 errors, ver `CLAUDE.md §6`). Un cambio limpio **no aumenta** `failed`. Anota el conteo base del worktree antes de la primera tarea.
- Repositorio de referencia: `/mnt/d/Devs/Atlas-Rmazh` (rama `release/qa`, HEAD `230bd05`). Commit base para comparar con Atlas ONE: `b00b431`. Para ver un diff de referencia: `git -C /mnt/d/Devs/Atlas-Rmazh diff <base> <head> -- <ruta>`. Para probar si aplica aquí: `git -C /mnt/d/Devs/Atlas-Rmazh diff <base> <head> -- <ruta> | git apply --check`.
- Marca: cualquier texto `RMAZH`, `RmazhLogo` o "Atlas POS" del origen se sustituye por el nombre de la organización o "Atlas ONE". El pie de página de Rmazh (iteración 1c) **no se trae**.
- Movimiento: toda animación respeta `@media (prefers-reduced-motion: reduce)` y la bandera local `atlas_ui_motion=0` (archivo `frontend/src/theme/legacy.ts` de Rmazh, del que aquí se porta **solo** la parte de movimiento; la bandera `atlas_ui_legacy` no existe aquí porque no cambian los tokens).
- Frontend: las pruebas viven en `src/**/*.test.ts` (vitest, entorno `node`, sin jsdom). Pruebas de funciones puras, no de componentes.
- Commits: mensaje en español con scope (`feat(pos):`, `fix(caja):`…), terminados con las líneas `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_015B77nTPcqnumepn2y2YZKm`.

## Worktrees y ramas

| Flujo | Rama | Worktree | Base | Puede correr en paralelo con |
|---|---|---|---|---|
| W0 verificación de hallazgos P2 | (sin rama, solo lectura) | repo principal | — | todos |
| W1 POS operación | `feat/rmazh-pos-operacion` | `.claude/worktrees/rmazh-pos-operacion` | `main` | todos |
| W2 devolución por folio | `feat/rmazh-devolucion-folio` | `.claude/worktrees/rmazh-devolucion-folio` | `main` | todos |
| W3 Mi día y Mi caja | `feat/rmazh-mi-dia-mi-caja` | `.claude/worktrees/rmazh-mi-dia-mi-caja` | `main` | todos |
| W4 latencia por petición | `feat/rmazh-latencia` | `.claude/worktrees/rmazh-latencia` | `main` | todos |
| W5 plataforma piel C | `feat/rmazh-platform-piel` | `.claude/worktrees/rmazh-platform-piel` | `main` | todos |
| W6 plataforma tablero por org | `feat/rmazh-platform-tablero` | `.claude/worktrees/rmazh-platform-tablero` | **W5** | W7 |
| W7 plataforma reportes de dinero | `feat/rmazh-platform-reportes` | `.claude/worktrees/rmazh-platform-reportes` | **W5** | W6 |
| W8 corte con historia | `feat/rmazh-corte-historia` | `.claude/worktrees/rmazh-corte-historia` | `main` | todos salvo W10 |
| W9 escáner de pasillo | `feat/rmazh-scanner` | `.claude/worktrees/rmazh-scanner` | `main` | todos |
| W10 pendientes previos (IVA, apertura, PIN) | `feat/rmazh-pendientes-previos` | `.claude/worktrees/rmazh-pendientes-previos` | `main` | W2–W7, W9; **después** de W1 y W8 |

Crear un worktree: `git worktree add -b <rama> .claude/worktrees/<nombre> <base>`. El frontend de cada worktree necesita `node_modules`: `ln -s /mnt/d/Devs/atlas-one/frontend/node_modules <worktree>/frontend/node_modules` (enlace, no copia).

---

## W0 — Verificar en Atlas ONE los hallazgos P2 de la auditoría de cajera

**Files:**
- Create: `docs/audits/2026-09-11-hallazgos-rmazh-en-atlas-one.md`

**Interfaces:**
- Produces: tabla con una fila por hallazgo C-13…C-27, columnas: id, resumen, archivo:línea en Atlas ONE, estado (`APLICA` / `NO APLICA` / `YA RESUELTO`), evidencia (la línea de código leída). Los que salgan `APLICA` alimentan W10 y una segunda ronda.

- [ ] **Step 1: Leer §4.3 de la auditoría de Rmazh** (`/mnt/d/Devs/Atlas-Rmazh/docs/superpowers/audits/2026-09-07-experiencia-cajero.md`, líneas 169–189).
- [ ] **Step 2: Por cada C-13…C-27, localizar el código equivalente en Atlas ONE** (`app/routers/cash.py`, `app/routers/printer.py`, `app/routers/returns.py`, `app/crud/returns.py`, `app/routers/reports.py`, `app/routers/inventory.py`, `app/modules/products/router/branch_status.py`, `frontend/src/components/branch/CashBranchView.tsx`, `frontend/src/components/pos/CartPanel.tsx`, `frontend/src/pages/returns/*`) y leer la línea. No adivinar: si la ruta no existe aquí, decir "NO APLICA: la ruta no existe".
- [ ] **Step 3: Escribir el documento** con la tabla y, al final, una lista "Recomendado para la segunda ronda" ordenada por riesgo de dinero.
- [ ] **Step 4: Commit** (en el repo principal, rama `main` NO: crear rama `docs/rmazh-hallazgos-p2` desde `main` y commitear ahí).

```bash
git checkout -b docs/rmazh-hallazgos-p2 main
git add docs/audits/2026-09-11-hallazgos-rmazh-en-atlas-one.md
git commit -m "docs(audit): hallazgos P2 de la auditoria de cajera de Rmazh verificados en Atlas ONE"
```

---

## W1 — POS: operación de la cajera

Referencia en Rmazh: commits `6dfaa75` (F4), `9398f2f` (barra y foco), `c7f862c` (filas y Limpiar), `d280d29` (preview honesto, sobrepago, timeout), `9c9f9ca` (revisión final). Plan de origen: `/mnt/d/Devs/Atlas-Rmazh/docs/superpowers/plans/2026-09-08-cajera-ola-pos.md`.

### Task 1.1: El precio forzado sobrevive a recargar, navegar y reanudar (C-03 / F4)

**Files:**
- Create: `frontend/src/pages/pos/cartTiers.ts` (copiar de `/mnt/d/Devs/Atlas-Rmazh/frontend/src/pages/pos/cartTiers.ts`)
- Create: `frontend/src/pages/pos/__tests__/cartTiers.test.ts` (copiar de Rmazh)
- Modify: `frontend/src/components/pos/CartPanel.tsx` (efectos de hidratación y auto-escalón, alrededor de la línea 76 donde se lee `item.forcedPriceTier`)

**Interfaces:**
- Produces: `cartKeyOf(item)`, `cajaTierOf(item)`, `autoTierTarget(unit, cajasQty): number | null`, `forcedTierMap(cart): Map<string,string>`.

- [ ] **Step 1: Verificar que el defecto existe aquí.** Leer `CartPanel.tsx` y localizar los dos `useEffect` que dependen de `[cart]`: uno que hidrata `forcedPrices` desde `item.forcedPriceTier` y otro que aplica el escalón automático. Si el segundo lee el `Map` del mismo commit (antes de que el primero lo haya poblado), el defecto existe. Si Atlas ONE ya lo hace en un solo efecto, documentarlo en el reporte y saltar a la Task 1.2. Antes de decidir, compara con el diff de referencia: `git -C /mnt/d/Devs/Atlas-Rmazh show 6dfaa75 -- frontend/src/components/pos/CartPanel.tsx`.
- [ ] **Step 2: Copiar `cartTiers.ts` y su prueba.** Ajustar el import de `CartItem` si la ruta de tipos difiere (`frontend/src/types/sales.ts`). Correr `cd frontend && npx vitest run src/pages/pos/__tests__/cartTiers.test.ts`. Esperado: PASS (la prueba es de función pura, no depende de CartPanel).
- [ ] **Step 3: Reescribir los dos efectos como uno solo** siguiendo el diff de `6dfaa75`: un único `useEffect` que construye `forcedTierMap(cart)`, lo fusiona con el estado local y evalúa `autoTierTarget` en el mismo paso. Sin `setTimeout`.
- [ ] **Step 4: Verificar.** `npx tsc --noEmit` y `npx vitest run`. Esperado: sin errores; conteo de pruebas igual o mayor que la base.
- [ ] **Step 5: Commit** `fix(pos): el precio forzado sobrevive a recargar, navegar y reanudar`.

### Task 1.2: Aviso de sobrepago en el modal de efectivo (C-08 / F6)

**Files:**
- Create: `frontend/src/pages/pos/cashPayment.ts` y `frontend/src/pages/pos/__tests__/cashPayment.test.ts` (copiar de Rmazh; aplican limpios)
- Modify: `frontend/src/components/pos/modals/CashPaymentModal.tsx` (el diff de Rmazh `d280d29` **aplica limpio** aquí: `git -C /mnt/d/Devs/Atlas-Rmazh diff 7c0c068^ 9c9f9ca -- frontend/src/components/pos/modals/CashPaymentModal.tsx | git apply`)

**Interfaces:**
- Produces: `OVERPAY_FACTOR = 10`, `cashPaymentValidity(received, total) → { ok, short, overpay }`. El backend ya rechaza con 422 "Sobrepago anómalo" en `app/routers/sales.py:708`; este cambio lo previene en la UI con el mismo factor.

- [ ] **Step 1: Copiar helper y prueba; correr la prueba.** Esperado: PASS.
- [ ] **Step 2: Aplicar el diff del modal.** Revisar que el modal use tokens `--dax-*` existentes y no colores fijos nuevos. Si el diff trae clases `bg-black`/`text-white` en botones, cambiarlas por las clases que ya usa el modal aquí (mirar `CardPaymentModal.tsx` de este repo como referencia de estilo local).
- [ ] **Step 3: `npx tsc --noEmit && npx vitest run`.** Esperado: verde.
- [ ] **Step 4: Commit** `feat(pos): aviso de sobrepago antes de que el backend lo rechace`.

### Task 1.3: Limpiar pide confirmación, la barra se bloquea durante el cobro y el escáner conserva el foco (C-23)

**Files:**
- Modify: `frontend/src/components/pos/CartPanel.tsx` (botón Limpiar)
- Modify: `frontend/src/pages/pos/POS.tsx` (barra superior: `inert`/`pointer-events-none` mientras `payModalOpen`)
- Modify: `frontend/src/components/pos/ProductSearch.tsx` (el input recupera el foco tras clic en resultado, `onMouseDown={e => e.preventDefault()}` en los botones de resultado como hace Rmazh `9398f2f`)

- [ ] **Step 1: Leer los diffs de referencia** `git -C /mnt/d/Devs/Atlas-Rmazh show 9398f2f c7f862c --stat` y los hunks de los tres archivos. Los archivos aquí divergen: portar la **intención**, no el texto.
- [ ] **Step 2: Limpiar con confirmación.** Si el carrito tiene ≥ 1 línea, `window.confirm('¿Vaciar el carrito?')` o el diálogo de confirmación que ya use este repo (buscar `ConfirmDialog` en `frontend/src/components/ui/`). Preferir el componente local si existe.
- [ ] **Step 3: Barra gateada.** Mientras haya un modal de cobro abierto, el contenedor de la barra superior recibe `inert` (atributo booleano; ver cómo `Layout.tsx` de este repo ya usa `inert` en el cajón móvil, commit `7e8a5d3`) para que ningún clic ni tab llegue a las pestañas.
- [ ] **Step 4: Foco del escáner.** En `ProductSearch.tsx`, los botones de resultado usan `onMouseDown={(e) => e.preventDefault()}` para no robar el foco del input; tras `onSelect`, `inputRef.current?.focus()`.
- [ ] **Step 5: `npx tsc --noEmit && npx vitest run && npm run build`.** Esperado: verde.
- [ ] **Step 6: Commit** `fix(pos): limpiar confirma, la barra se bloquea durante el cobro y el escaner conserva el foco`.

### Task 1.4: Un preview fallido no abre el modal con el total local (C-07 / F6)

**Files:**
- Modify: `frontend/src/pages/pos/POS.tsx` (función que abre el modal de pago tras `POST /sales/preview`)

- [ ] **Step 1: Localizar en `POS.tsx`** dónde se llama al preview y qué pasa en el `catch`. Si hoy abre el modal con el total local, el defecto existe.
- [ ] **Step 2: Portar la intención de `d280d29`:** en el `catch`, mostrar el `detail` del error con el toast del repo y **no** abrir el modal. Tarjeta y transferencia no deben mandar `amount` calculado localmente si el preview falló.
- [ ] **Step 3: `npx tsc --noEmit && npm run build`.** Esperado: verde.
- [ ] **Step 4: Commit** `fix(pos): un preview fallido muestra el error y no abre el cobro con el total local`.

### Task 1.5: Reporte de W1

- [ ] Escribir en el mensaje final: conteo de pruebas antes/después, archivos tocados, qué se verificó a mano y qué quedó fuera (por ejemplo, si 1.1 ya estaba resuelto).

---

## W2 — Devolución por folio y método de reembolso (C-09, C-10)

### Task 2.1: `folio_search` en `read_sales`

**Files:**
- Modify: `app/routers/sales.py:272-283` (`read_sales`)
- Test: `tests/test_sales_folio_search.py`

**Interfaces:**
- Produces: query param `folio_search: Optional[str]` que filtra por folio exacto normalizado (`A-540` empata `A-0540`; comparación insensible a mayúsculas). Mantiene `organization_id` y `branch_id` del scoping actual.

- [ ] **Step 1: Escribir la prueba que falla.**

```python
# tests/test_sales_folio_search.py
def test_folio_search_encuentra_con_y_sin_ceros(client, auth_admin, db, org, branch_a, seeded_sale):
    """seeded_sale es una venta con folio 'A-0540' (usa las fixtures de conftest para crearla)."""
    r = client.get("/api/sales/", params={"folio_search": "a-540"}, headers=auth_admin)
    assert r.status_code == 200
    folios = [s["folio"] for s in r.json()["items"]]
    assert folios == ["A-0540"]

def test_folio_search_no_cruza_organizaciones(client, auth_other_org, seeded_sale):
    r = client.get("/api/sales/", params={"folio_search": "A-0540"}, headers=auth_other_org)
    assert r.json()["items"] == []
```

Adaptar los nombres de fixtures a los reales de `tests/conftest.py` (leerlo antes; hay `client`, `auth_admin`, `db`, `org`, `branch_a`). Si no hay fixture de venta sembrada, crear una con `POST /api/sales/` en la propia prueba siguiendo `tests/test_sales*.py` existentes.

- [ ] **Step 2: Correr.** `python3 -m pytest -q tests/test_sales_folio_search.py`. Esperado: FAIL (422 por parámetro desconocido o lista completa).
- [ ] **Step 3: Implementar.** En `read_sales`, añadir `folio_search: Optional[str] = None`. Normalizar: separar prefijo y número por el último `-`, `int(numero)` y comparar contra `func.upper(SalesDocument.folio)` con el número sin ceros; la forma más simple y correcta en SQLite y Postgres es traer candidatos por prefijo (`folio.ilike(f"{prefijo}-%")`) y filtrar en Python por `int(parte_numerica) == int(buscado)`. Ver cómo lo resolvió Rmazh: `grep -n folio_search /mnt/d/Devs/Atlas-Rmazh/app/routers/sales.py`.
- [ ] **Step 4: Correr.** Esperado: PASS. Correr la suite completa; `failed` no aumenta.
- [ ] **Step 5: Commit** `feat(sales): busqueda por folio exacto para devoluciones`.

### Task 2.2: `ReturnModal` usa `folio_search` y permite elegir método de reembolso

**Files:**
- Modify: `frontend/src/components/pos/modals/ReturnModal.tsx:83-95` (hoy manda `search:`, que el backend ignora)
- Modify: `frontend/src/api/sales.ts` (tipo de `list` acepta `folio_search`)

- [ ] **Step 1: Cambiar la búsqueda** a `salesApi.list({ folio_search: folio.trim(), limit: 5 })` y quitar el `find` por etiqueta.
- [ ] **Step 2: Selector de método de reembolso.** Leer `frontend/src/pages/returns/*` (el wizard) para reutilizar el mismo selector y los mismos valores de `refund_method` que acepta `app/routers/returns.py`. Por defecto, el método de pago original de la venta.
- [ ] **Step 3: `npx tsc --noEmit && npm run build`.** Verde.
- [ ] **Step 4: Commit** `fix(devoluciones): el modal busca por folio exacto y deja elegir el metodo de reembolso`.

---

## W3 — Mi día y Mi caja (U4, U5) con los tokens de Atlas ONE

Referencia: commits `e2fee6a`, `132fb6d`, `5bb7ad9`, `37caa4e`, `16b5f71`, `6c37a01`, `c2c97f6`, `53117f3` de Rmazh. Estos archivos son **idénticos** entre repos en el base: `Cockpit.tsx`, `CockpitGreeting.tsx`, `CockpitDayKPIs.tsx`, y los archivos nuevos aplican limpios.

### Task 3.1: Base de movimiento y helpers puros

**Files:**
- Create (copiar de Rmazh, aplican limpio): `frontend/src/theme/sky.ts`, `frontend/src/theme/verdict.ts`, `frontend/src/theme/heroState.ts`, `frontend/src/hooks/useCountUp.ts`, `frontend/src/styles/motion.css`, y sus pruebas en `frontend/src/theme/__tests__/{sky,verdict,heroState}.test.ts`
- Create: `frontend/src/theme/motion.ts` — **solo** la parte de `atlas_ui_motion` de `legacy.ts` de Rmazh (exportar `MOTION_KEY`, `motionDisabled(): boolean`, `applyMotionFlag(root)`); no traer `atlas_ui_legacy` ni `html.ui-legacy`.
- Modify: `frontend/src/main.tsx` (importar `./styles/motion.css` y llamar `applyMotionFlag(document.documentElement)` al arrancar)

- [ ] **Step 1: Copiar los archivos y correr `npx vitest run src/theme`.** Esperado: PASS.
- [ ] **Step 2: `motion.css`:** reemplazar cualquier color fijo (`#7C3AED`, `#000`, etc.) por `var(--dax-accent)`, `var(--dax-bg)`, etc. Verificar con `grep -nE '#[0-9a-fA-F]{3,6}' frontend/src/styles/motion.css` que no quede ninguno salvo dentro de `rgba(...)` de sombras.
- [ ] **Step 3: `npx tsc --noEmit`.** Verde.
- [ ] **Step 4: Commit** `feat(ui): base de movimiento respetuoso y helpers de cielo, veredicto y estado del turno`.

### Task 3.2: Mi día — cielo según la hora, cascada y contador (A1, A3)

**Files:**
- Create: `frontend/src/components/branch/Sky.tsx` (copiar; aplica limpio)
- Modify: `frontend/src/components/branch/CockpitGreeting.tsx`, `Cockpit.tsx`, `CockpitDayKPIs.tsx` (aplicar `git -C /mnt/d/Devs/Atlas-Rmazh diff 7c0c068^ 9c9f9ca -- <archivo> | git apply`; los tres aplican limpios)

- [ ] **Step 1: Aplicar los diffs.** Después, `grep -nE 'text-white|slate-|#[0-9a-fA-F]{6}' frontend/src/components/branch/{Sky,CockpitGreeting,Cockpit,CockpitDayKPIs}.tsx`: cada color fijo que venga de Rmazh se cambia por el token de Atlas ONE equivalente. El cielo (sol, nubes, luna) puede conservar sus colores propios porque son ilustración, no UI.
- [ ] **Step 2: Sustituir marca.** Si `CockpitGreeting` trae "RMAZH", usar `org?.name`.
- [ ] **Step 3: `npx tsc --noEmit && npx vitest run && npm run build`.** Verde.
- [ ] **Step 4: Verificación visual mínima:** `cd frontend && npm run dev` en segundo plano, abrir `/dataxpos` (o la ruta de Mi día en `App.tsx`) con un usuario de sucursal de la base local; confirmar en ambos temas que el saludo pinta el cielo y que las tarjetas entran. Documentar en el reporte qué se vio. Si no hay base local con datos, decirlo y no inventar.
- [ ] **Step 5: Commit** `feat(cajera): Mi dia con cielo segun la hora, entrada en cascada y KPIs que cuentan`.

### Task 3.3: Mi caja — hero con estado del turno, apertura celebrada y veredicto de cierre (A2, A6)

**Files:**
- Create: `frontend/src/components/branch/Confetti.tsx` (copiar; aplica limpio)
- Modify: `frontend/src/components/branch/CashBranchView.tsx` (diverge 196/873 líneas: portar a mano desde `git -C /mnt/d/Devs/Atlas-Rmazh show 37caa4e 16b5f71 6c37a01 -- frontend/src/components/branch/CashBranchView.tsx`)
- Modify: `frontend/src/components/pos/modals/CloseSessionModal.tsx` (diverge 15/117: portar el veredicto con `closeVerdict(difference)`)
- Modify: `frontend/src/components/branch/OpenShiftModal.tsx` (celebración tras `POST /cash/open` 2xx: confeti 2 s y contador del fondo inicial con `useCountUp`)

- [ ] **Step 1: Hero.** Banda superior con `heroState(isOpen, closedToday)` y píldora de estado. Fondo del hero con el `Sky` de la Task 3.2 solo si el usuario no tiene `prefers-reduced-motion`.
- [ ] **Step 2: Apertura.** Al resolver `POST /cash/open`, montar `<Confetti />` 2 s y contar el fondo inicial hasta su valor. No bloquear el cierre del modal.
- [ ] **Step 3: Veredicto de cierre.** En `CloseSessionModal`, al recibir la respuesta de cierre, mostrar `closeVerdict(difference)` con su `className` **mapeada a tokens** (`ok` → `--dax-success`, `over` → `--dax-warning`, `short` → `--dax-danger`; **estos tres tokens no existen aún aquí y los crea W5 Task 5.1** — si W3 termina antes que W5, definirlos en `index.css` en el mismo bloque donde viven `--dax-accent`, con los valores del vertical: claro `#059669/#D97706/#DC2626`, oscuro `#34D399/#FBBF24/#F87171`; W5 los reutiliza y no los redefine). La diferencia cuenta hasta su valor con `useCountUp`.
- [ ] **Step 4: `npx tsc --noEmit && npx vitest run && npm run build`.** Verde.
- [ ] **Step 5: Commit** `feat(cajera): Mi caja con estado del turno en el hero, apertura celebrada y veredicto de cierre`.

---

## W4 — Latencia por petición (F0)

Referencia: `4c35b24` y `425bf78` de Rmazh. Atlas ONE registra hoy solo errores efímeros (memoria `atlas-one-logs-efimeros`).

### Task 4.1: Middleware ASGI de tiempo por petición

**Files:**
- Create: `app/observability/__init__.py`, `app/observability/timing.py` (copiar de `/mnt/d/Devs/Atlas-Rmazh/app/observability/timing.py`)
- Create: `tests/test_request_timing.py` (copiar de Rmazh y adaptar fixtures)
- Modify: `app/main.py` (registrar `TimingMiddleware` **como ASGI puro**, no `BaseHTTPMiddleware`; ignorar `/assets`, `/icons`, `/static`; emitir campos planos cuando `LOG_JSON=true`)

**Interfaces:**
- Produces: logger `atlas.timing` con campos `path`, `method`, `status`, `ms`, `org` (del header `X-Organization-ID` si viene), `branch` (del token si existe), `user`.

- [ ] **Step 1: Copiar `timing.py` y la prueba; correr la prueba.** Esperado: FAIL porque el middleware no está montado.
- [ ] **Step 2: Montar en `main.py`.** Leer cómo Rmazh lo hace (`git -C /mnt/d/Devs/Atlas-Rmazh diff b00b431 release/qa -- app/main.py`) y replicar la intención en el `main.py` de aquí (que diverge). Respetar `LOG_LEVEL` en mayúsculas (trampa conocida). La forma de extraer `branch` del token debe usar `app/core/security/jwt.py` de este repo, no el de Rmazh.
- [ ] **Step 3: Correr `tests/test_request_timing.py` y la suite completa.** PASS; `failed` no aumenta.
- [ ] **Step 4: Commit** `feat(observabilidad): registrar la duracion, organizacion y sucursal de cada peticion`.

---

## W5 — Plataforma: piel C con los tokens de Atlas ONE y responsive (rebanada 1)

Referencia: commits `5f657e3`…`71decf2` (merge `ee8d54c`) de Rmazh. Plan de origen: `/mnt/d/Devs/Atlas-Rmazh/docs/superpowers/plans/2026-09-09-superadmin-rebanada-1-piel.md`. En seco, de los archivos de esta rebanada solo `DataTable.tsx` no aplica limpio.

### Task 5.1: Tokens que faltan y capa de alias `--p-*` → `--dax-*`

**Files:**
- Modify: `frontend/src/index.css` (añadir `--dax-accent-soft`, `--dax-success`, `--dax-warning`, `--dax-danger` en claro y oscuro, **derivados del acento por vertical** donde aplique: `--dax-accent-soft: color-mix(in srgb, var(--dax-accent) 14%, transparent)`; los tres de estado son fijos: claro `#059669/#D97706/#DC2626`, oscuro `#34D399/#FBBF24/#F87171`). Si W3 ya los definió, no duplicar.
- Modify: `frontend/src/styles/platform-v2.css` (aplicar el diff de Rmazh; aplica limpio; **quitar** el bloque `html.ui-legacy .pv2` porque aquí no existe esa bandera)
- Create: `frontend/src/theme/__tests__/platform.tokens.test.ts`, `platform.noFixedColors.test.ts`, `platform.responsive.test.ts` (copiar de Rmazh)

- [ ] **Step 1: Copiar las tres pruebas y correrlas.** Esperado: FAIL (tokens y alias ausentes).
- [ ] **Step 2: Añadir tokens y aplicar el diff de `platform-v2.css`.** Comprobar que cada `var(--dax-…)` que usa el alias existe en `index.css`: `for t in $(grep -oE 'var\(--dax-[a-z0-9-]+' frontend/src/styles/platform-v2.css | sed 's/var(//' | sort -u); do grep -q "$t:" frontend/src/index.css || echo "FALTA $t"; done` debe imprimir nada.
- [ ] **Step 3: Correr las pruebas.** PASS.
- [ ] **Step 4: Commit** `feat(platform): la piel de plataforma consume los tokens de Atlas ONE; tokens de estado y acento suave`.

### Task 5.2: Navegación como módulo, breakpoints 1024/768/480, barra inferior y filtros con scroll

**Files:**
- Create: `frontend/src/pages/platform/platformNav.ts` y `__tests__/platformNav.test.ts` (copiar; aplican limpios)
- Modify: `frontend/src/pages/platform/PlatformLayout.tsx` (idéntico al base: `git -C /mnt/d/Devs/Atlas-Rmazh diff b00b431 release/qa -- frontend/src/pages/platform/PlatformLayout.tsx | git apply`)
- Modify: `frontend/src/components/platform/PlatformPageShell.tsx`, `ReportFilterBar.tsx`, `ReportDrillDownDrawer.tsx` (aplican limpios)

- [ ] **Step 1: Aplicar los diffs y copiar los nuevos.** El toggle de tema del sidebar de plataforma debe usar `ThemeContext` de este repo (buscar `frontend/src/context/ThemeContext.tsx`).
- [ ] **Step 2: `npx tsc --noEmit && npx vitest run`.** Verde.
- [ ] **Step 3: Commit** `feat(platform): navegacion como modulo, breakpoints 1024/768/480 y barra inferior en telefono`.

### Task 5.3: `DataTable` en modo tarjeta bajo 640 px

**Files:**
- Create: `frontend/src/components/platform/dataTableCards.ts` y `__tests__/dataTableCards.test.ts` (copiar)
- Modify: `frontend/src/components/platform/DataTable.tsx` (**no aplica limpio**: portar a mano desde `git -C /mnt/d/Devs/Atlas-Rmazh diff b00b431 release/qa -- frontend/src/components/platform/DataTable.tsx`)

- [ ] **Step 1: Copiar helper y prueba; PASS.**
- [ ] **Step 2: Portar `DataTable.tsx`:** bajo 640 px cada fila se pinta como tarjeta con las columnas marcadas `primary`/`secondary` en `dataTableCards.ts`, conservando las acciones de fila; en escritorio la tabla tiene scroll horizontal propio (ver `TablaDesplazable` de este repo, commit `1b697d2`, y reutilizarla si encaja).
- [ ] **Step 3: `npx tsc --noEmit && npx vitest run && npm run build`.** Verde.
- [ ] **Step 4: Commit** `feat(platform): DataTable en modo tarjeta bajo 640 px con acciones conservadas`.

---

## W6 — Plataforma: tablero por organización (rebanada 2, adaptada)

Base: rama `feat/rmazh-platform-piel` (W5 terminado). Referencia: `7a8e35b`…`847a6ae` (merge `2dd49dc`). Spec §4 de `2026-09-09-superadmin-grupo-design.md`.

**Adaptación semántica obligatoria:** en Rmazh "Grupo" = todas las orgs de un dueño. Aquí el tablero muestra **una organización a la vez** (selector arriba, recordado en `localStorage`) con sus sucursales; la tira "Atención hoy" (cajas sin corte, cortes con diferencia, devoluciones pendientes) **sí cruza todas las organizaciones** porque el superadmin atiende a todos los clientes. Ningún KPI suma dinero de dos organizaciones.

### Task 6.1: Servicio y endpoint `GET /api/platform/organizations/{org_id}/overview` y `GET /api/platform/attention-today`

**Files:**
- Create: `app/services/org_overview.py` (portar `app/services/group_overview.py` de Rmazh, con `organization_id` como parámetro obligatorio en cada consulta)
- Create: `app/schemas/platform_overview.py` (portar `platform_group.py`)
- Create: `app/routers/platform/overview.py` (portar `group.py`: caché de 60 s por org, guard de plataforma `require_platform_admin` de este repo)
- Modify: `app/routers/platform/__init__.py` (registrar el router; el hunk de Rmazh no aplica: añadir a mano las dos líneas)
- Test: `tests/test_platform_org_overview.py` (portar `test_platform_group_overview.py`, 302 líneas, adaptando a "una org")

- [ ] **Step 1: Portar la prueba primero** con las fixtures de este `conftest.py`; correr; FAIL por 404.
- [ ] **Step 2: Portar servicio, esquema y router.** Ventanas de "hoy", "ayer" y "mismo día de la semana pasada" en **hora de México** (reutilizar la zona que ya usa `app/routers/cash.py` para la alerta de efectivo fuera de turno; no duplicar la constante: si no hay helper, crear `app/core/fechas.py` con `ZONA_NEGOCIO = os.getenv("BUSINESS_TIMEZONE", "America/Mexico_City")` y `hoy_negocio()`).
- [ ] **Step 3: Correr la prueba y la suite.** PASS; `failed` no aumenta.
- [ ] **Step 4: Commit** `feat(platform): resumen del dia por organizacion y tira de atencion hoy`.

### Task 6.2: Frontend — modo Global/Organización con tira "Atención hoy"

**Files:**
- Create (portar de `frontend/src/pages/platform/group/*` de Rmazh a `frontend/src/pages/platform/org/*`): `OrgBoard.tsx`, `OrgKpis.tsx`, `OrgTable.tsx`, `AttentionPanel.tsx`, `UnitDrawer.tsx`, `orgFormat.ts`, `orgPrefs.ts`, `useOrgOverview.ts` y las pruebas `__tests__/{orgFormat,orgPrefs}.test.ts`
- Create: `frontend/src/api/platformOverview.ts`, `frontend/src/types/platformOverview.ts`
- Modify: `frontend/src/pages/platform/PlatformMetrics.tsx` (diverge 101/573: portar a mano el conmutador Global/Organización y el selector de organización; la lista de orgs viene de `platformApi.organizations` que ya existe aquí)

- [ ] **Step 1: Portar helpers puros y pruebas; PASS.**
- [ ] **Step 2: Portar componentes** cambiando el vocabulario "grupo" → "organización" en textos y nombres; sin colores fijos (la prueba `platform.noFixedColors` de W5 lo vigila).
- [ ] **Step 3: `npx tsc --noEmit && npx vitest run && npm run build`.** Verde.
- [ ] **Step 4: Commit** `feat(platform): tablero por organizacion con modo Global/Organizacion y Atencion hoy`.

---

## W7 — Plataforma: reportes de dinero y comparación de periodos (rebanada 3)

Base: rama `feat/rmazh-platform-piel` (W5 terminado). Referencia: `78ba4fc`…`3abee48` (merge `230bd05`). Spec §5 y golden rules en `d8048d5`.

### Task 7.1: Backend — comparación de periodos en los cuatro pivotes existentes

**Files:**
- Create: `app/services/report_compare.py` (copiar; nuevo)
- Modify: `app/routers/platform/reports.py` (idéntico al base salvo 2 líneas: aplicar `git -C /mnt/d/Devs/Atlas-Rmazh diff b00b431 release/qa -- app/routers/platform/reports.py | git apply --3way` y resolver a mano si esas 2 líneas chocan)
- Test: `tests/test_platform_reports_compare.py` (copiar)

- [ ] **Step 1: Copiar prueba; FAIL.** **Step 2: Aplicar.** **Step 3: PASS y suite.** **Step 4: Commit** `feat(platform): comparacion de periodos (prev/yoy) en los reportes de plataforma`.

### Task 7.2: Backend — pivotes de dinero (cortes, devoluciones, cancelaciones, quincenal por método)

**Files:**
- Create: `app/routers/platform/reports_money.py` (copiar, 825 líneas; verificar que cada consulta filtra `organization_id` y que devoluciones/cancelaciones leen la **fecha del audit log**, no `updated_at`, como fija `006a7df`; el modelo de audit de este repo es `PlatformAuditLog` + `CashAuditLog`, comprobar cuál guarda la aprobación de devoluciones aquí, `grep -rn REFUND_APPROVED app/`)
- Modify: `app/routers/platform/__init__.py` (registrar)
- Test: `tests/test_platform_reports_money.py` (copiar, 434 líneas)

- [ ] **Step 1: Copiar prueba; FAIL.** **Step 2: Copiar router, adaptar nombres de modelos/eventos.** **Step 3: PASS y suite.** **Step 4: Commit** `feat(platform): pivotes de cortes, devoluciones, cancelaciones y quincenal por metodo`.

### Task 7.3: Frontend — pestañas de dinero, columnas delta y drawer de detalle

**Files:**
- Create (copiar; aplican limpios): `frontend/src/pages/platform/reports/{BiweeklyTab,CancellationsTab,CashCutsTab,MoneyDetailDrawer,MoneyTable,ReturnsTab}.tsx`, `reports/compareFormat.ts` + prueba, `frontend/src/api/reportsMoney.ts`, `frontend/src/types/reportsMoney.ts`, `frontend/src/types/reports.ts` (diff)
- Modify: `frontend/src/pages/platform/PlatformReports.tsx` (diverge 301/806: portar a mano; la unidad del quincenal vive en la URL para que el CSV coincida, `9c06ada`; paginación real en dinero y "Comparar" oculto ahí, `3abee48`)

- [ ] **Step 1: Copiar todo lo que aplica limpio; `npx tsc --noEmit`** para ver qué falta en `PlatformReports.tsx`.
- [ ] **Step 2: Portar `PlatformReports.tsx`.** **Step 3: `vitest && build`.** **Step 4: Commit** `feat(platform): pestanas de dinero, columnas delta y drawer de detalle en reportes`.

---

## W8 — Corte con historia (caja)

Referencia: `2ba1d23` y `4fb9916` de Rmazh. Toca dinero: **revisión adversarial obligatoria** (`/code-review high`) antes de dar por terminado. `cash.py` diverge 711/1130 y `pos_printer.py` también: se porta la intención.

### Task 8.1: El corte cuenta un solo relato causal

**Files:**
- Modify: `app/routers/cash.py` (endpoint de detalle/corte de sesión: añadir secciones `cobrado_por_metodo`, `devoluciones`, `ventas_netas`, `arqueo` en ese orden; la **hora de aprobación de una devolución sale del audit log**, no de `updated_at`)
- Modify: `app/pos_printer.py` (el ticket de corte imprime las cuatro secciones en ese orden; ver cómo Rmazh reescribió el bloque `== POR METODO DE PAGO ==`)
- Test: `tests/test_cash_cut_historia.py` (portar los 313 renglones de Rmazh adaptando fixtures), `tests/test_cash_cut_detalle.py` (ídem)

- [ ] **Step 1: Leer primero** `docs/superpowers/runbooks/cash-discrepancy-debugging.md` y la memoria del corte de caja de este repo (`compute_expected_cash` es correcta y **no se toca**).
- [ ] **Step 2: Portar las pruebas; FAIL.** **Step 3: Implementar sin cambiar `compute_expected_cash` ni `CASH_INCLUDED_STATUSES`.** **Step 4: PASS; suite; `failed` no aumenta.** 
- [ ] **Step 5: Revisión adversarial** con el skill `code-review` a nivel `high` sobre el diff; corregir hallazgos.
- [ ] **Step 6: Commit** `feat(caja): corte con historia — cobrado por metodo, devoluciones, ventas netas y arqueo`.

---

## W9 — Escáner de pasillo

Referencia: `da74d1f`, `a8436ad`, `de3dc60`, `b3fc35f`, `c0cef4f` de Rmazh.

### Task 9.1: Búsqueda exacta por código y guard de precio por escalón

**Files:**
- Modify: `app/modules/products/router/search.py` (portar `app/routers/products/search.py` de Rmazh: parámetro `exact=true` que empata `barcode`/`sku` completos y devuelve 0 o 1 resultados)
- Modify: `app/modules/products/router/core.py` (portar el guard de `tests/test_tier_price_guard.py`: un escalón no se guarda en cero, y `PUT` permite limpiar campos, `test_product_clear_fields.py`)
- Test: copiar `tests/test_scanner_exact_search.py`, `tests/test_tier_price_guard.py`, `tests/test_product_clear_fields.py`, `tests/test_tier_label.py` de Rmazh y adaptar rutas de import (`app.modules.products` aquí).

- [ ] **Step 1: Copiar pruebas; FAIL.** **Step 2: Implementar.** **Step 3: PASS; suite.** **Step 4: Commit** `feat(products): busqueda exacta por codigo y guard de escalones para el escaner`.

### Task 9.2: Página `/scanner`

**Files:**
- Create: `frontend/src/pages/scanner/{StoreScanner.tsx,barcodeReader.ts,productStock.ts,scanPayload.ts,stockAdjust.ts}` y `__tests__/*` (copiar), `frontend/src/utils/errorDetail.ts` + prueba (copiar)
- Modify: `frontend/src/api/products.ts` (funciones `scanExact`, `adjustStock`; portar del diff), `frontend/src/App.tsx` (ruta `/scanner` gateada al módulo de inventario con el mismo guard que usan las rutas de sucursal), menú móvil (`Sidebar.tsx`: añadir la entrada bajo Inventario **sin** cambiar el diseño del cajón)

- [ ] **Step 1: Copiar; `npx vitest run src/pages/scanner`.** PASS. **Step 2: Cablear ruta y API.** **Step 3: `tsc && build`.** **Step 4: Commit** `feat(scanner): escanear en el pasillo, corregir precio y contar inventario`.

---

## W10 — Pendientes de la comparación del 1 de septiembre

Base: `main`, **después** de que W1 y W8 terminen (comparten `sales.py`, `cash.py`, `printer.py`). Referencia: `docs/audits/2026-09-01-comparacion-atlas-rmazh.md` §3, §5, §6 y §7. El punto 9 (baseline de Alembic) **queda fuera**: contradice la regla de oro 3 de `CLAUDE.md`.

### Task 10.1: Servicio único de IVA

**Files:**
- Create: `app/services/tax.py` (portar de `/mnt/d/Devs/Atlas-Rmazh/app/services/tax.py`), con `price_includes_tax` leído de la organización
- Modify: los tres sitios que hoy calculan IVA en línea (ticket en `app/pos_printer.py`, reporte en `app/routers/reports.py`, devolución en `app/crud/returns.py`; localizarlos con `grep -rn '0.16\|\* 1.16\|/ 1.16' app/`)
- Test: portar las seis pruebas de IVA de Rmazh (`grep -rl 'tax' /mnt/d/Devs/Atlas-Rmazh/tests/ | head`)

- [ ] **Step 1: Pruebas; FAIL.** **Step 2: Servicio y reemplazo de las fórmulas.** **Step 3: PASS; suite.** **Step 4: Commit** `refactor(iva): una sola fuente para el calculo de impuesto`.

### Task 10.2: Serializar la apertura de caja

**Files:**
- Modify: `app/routers/cash.py` (endpoint de apertura: `with_for_update()` sobre la sesión abierta de la sucursal/usuario + índice único parcial "una sesión OPEN por usuario y sucursal" en `scripts/railway_init.py` como `CREATE UNIQUE INDEX IF NOT EXISTS`)
- Test: `tests/test_cash_open_race.py` (dos aperturas seguidas → la segunda responde 409)

- [ ] **Step 1–4** como arriba. Commit `fix(caja): una sola sesion abierta por usuario y sucursal`.

### Task 10.3: PIN de reimpresión

**Files:**
- Modify: `app/routers/printer.py` (reimpresión exige `pin` del supervisor o rol gerencial; rechaza ventas `CANCELLED`, hallazgo C-18)
- Modify: `frontend/src/pages/sales/SalesHistory.tsx` (o donde viva el botón de reimprimir) para pedir el PIN
- Test: `tests/test_reprint_pin.py`

- [ ] **Step 1–4** como arriba. Commit `feat(printer): reimpresion con PIN y sin ventas canceladas`.

---

## Cierre de cada flujo

Al terminar un flujo, el subagente reporta: rama, commits, conteo de pruebas backend y frontend antes/después, `npm run build` verde, lo que se verificó a mano, lo que quedó fuera y por qué. **No fusiona, no sube.** La integración a `main` se decide después de las 19:00 CST con el skill `superpowers:finishing-a-development-branch`, un flujo a la vez, corriendo la suite completa tras cada merge.
