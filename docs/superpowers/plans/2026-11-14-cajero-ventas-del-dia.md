# Ventas del día para el CAJERO — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** La cajera ve en Ventas solo los tickets de hoy de su sucursal, sin totales del día, y el servidor no le sirve nada fuera de eso.

**Architecture:** Un módulo chico `app/services/ventas_cajero.py` concentra la regla ("¿es cajero?", "rango de hoy en México", "¿esta venta es de hoy y de su sucursal?"). `read_sales`, `get_sale_detail`, `get_sale_print_view`, `/sales/stats` y `POST /returns/` la consultan. En el frontend `SalesHistory.tsx` se ramifica por rol CAJERO y `ReturnModal.tsx` explica por qué no encuentra un ticket viejo.

**Tech Stack:** FastAPI + SQLAlchemy (pytest, SQLite en memoria) · React + TS (vitest).

**Spec:** `docs/superpowers/specs/2026-11-14-cajero-ventas-del-dia-design.md`

## Global Constraints

- Solo el rol `Role.CAJERO` cambia. GERENTE, ADMINISTRADOR, DUEÑO, SUPERADMIN: comportamiento idéntico al de hoy.
- "Hoy" = día calendario de `America/Mexico_City` (`metricas_ventas.hoy_mx()`).
- Comparar el rol contra el enum `Role.CAJERO`, nunca contra strings sueltos.
- No tocar `create_sale` ni `/printer/reprint-ticket` (la reimpresión vieja ya exige PIN de supervisor).
- Copys exactos: título `Ventas de hoy`; devolución rechazada `Solo puedes devolver ventas de hoy. Para días anteriores pide al gerente.`; ticket no encontrado por la cajera `Ticket no encontrado. Solo aparecen ventas de hoy; para días anteriores pide al gerente.`
- Correr pytest con `--ignore=tests/test_cash_complete.py`; frontend debe pasar `npx tsc --noEmit` y vitest.

## Review Focus

- Venta de las 23:50 de ayer (hora MX) que en UTC ya es "hoy": debe quedar fuera para la cajera → test `test_venta_de_ayer_noche_no_aparece` (Task 1).
- Venta con `branch_id` NULL (legado): la cajera no la ve ni por lista ni por detalle → cubierto en `venta_visible_para_cajero` (Task 1, test `test_venta_sin_sucursal_invisible_para_cajero`).
- La cajera manda `start_date`/`end_date`/`branch_id` a mano en la URL: se ignoran, sigue viendo solo hoy de su sucursal → `test_cajero_ignora_fechas_y_sucursal` (Task 1).
- Tienda con más de 100 tickets en el día: la paginación sigue funcionando para la cajera (el `total` refleja solo hoy) → assert de `total` en `test_cajero_ignora_fechas_y_sucursal` (Task 1) y paginación conservada en Task 4.
- Gerente intentando devolver una venta de ayer: debe seguir pudiendo → `test_gerente_devuelve_venta_de_ayer` (Task 3).

---

### Task 1: Regla única + lista, detalle e impresión para CAJERO

**Files:**
- Create: `app/services/ventas_cajero.py`
- Modify: `app/routers/sales.py` (`read_sales` ~L183, `get_sale_detail` ~L1385, `get_sale_print_view` ~L1401)
- Test: `tests/test_cajero_ventas_del_dia.py` (crear; reusar el patrón `_venta(...)` de `tests/test_sales_stats_y_returns.py`, copiándolo o moviéndolo a un helper compartido)

**Interfaces:**
- Produces:
  - `es_cajero(user: User) -> bool`
  - `rango_hoy_mx() -> tuple[datetime, datetime]` — inicio y fin (inclusive, 23:59:59.999999) de hoy, tz-aware `America/Mexico_City`.
  - `venta_visible_para_cajero(sale: SalesDocument, user: User) -> bool` — `True` solo si `sale.branch_id == user.branch_id` (no NULL) y `sale.created_at` cae en `rango_hoy_mx()`. `created_at` naive se interpreta como UTC (así lo devuelve SQLite).

- [ ] **Step 1: Write the failing tests** (todas con `auth_cajero_a` salvo que se diga; habilitar `OrganizationModule(module_key="pos")` como hace `test_sales_stats_cajera_solo_su_sucursal`)
  - `test_cajero_solo_ve_ventas_de_hoy`: venta hoy (A) + venta ayer (A) → `GET /api/sales/` devuelve solo la de hoy.
  - `test_cajero_ignora_fechas_y_sucursal`: ventas hoy en A y B, ayer en A; `GET /api/sales/?start_date=<ayer>&end_date=<ayer>&branch_id=<B>` → solo la de hoy en A, `total == 1`.
  - `test_venta_de_ayer_noche_no_aparece`: venta de ayer a las 23 h MX → no aparece.
  - `test_folio_search_de_ayer_vacio`: `?folio_search=<folio de ayer>` → `items == []`.
  - `test_detalle_de_ayer_404` y `test_print_view_de_ayer_404`: `GET /api/sales/{id}` y `/{id}/print-view` de venta de ayer → 404; de hoy → 200.
  - `test_venta_sin_sucursal_invisible_para_cajero`: `branch_id=None` hoy → no en lista, detalle 404.
  - `test_gerente_sigue_viendo_ayer` (`auth_gerente_a`): `GET /api/sales/?start_date=<ayer>&end_date=<ayer>` incluye la de ayer.

- [ ] **Step 2: Run to verify they fail**
  Run: `python3 -m pytest -q tests/test_cajero_ventas_del_dia.py`
  Expected: FAIL (ventas de ayer aparecen; módulo no existe).

- [ ] **Step 3: Implement `app/services/ventas_cajero.py`** con las tres funciones de Interfaces (usa `metricas_ventas.hoy_mx()` y `ZoneInfo("America/Mexico_City")`).

- [ ] **Step 4: Wire into `app/routers/sales.py`**
  - `read_sales`: si `es_cajero(current_user)`, después del filtro de sucursal sobrescribir `start_date, end_date = rango_hoy_mx()` antes de aplicarlos, y añadir `SalesDocument.branch_id.isnot(None)` (ya cubierto por `== branch_id`). `branch_id` del query ya se ignora para no-HQ.
  - `get_sale_detail` y `get_sale_print_view`: tras `_assert_sale_branch_access`, si `es_cajero(...)` y `not venta_visible_para_cajero(...)` → `HTTPException(404, "Venta no encontrada")`.

- [ ] **Step 5: Run to verify they pass**
  Run: `python3 -m pytest -q tests/test_cajero_ventas_del_dia.py tests/test_sales_stats_y_returns.py`
  Expected: PASS.

- [ ] **Step 6: Commit**
  `git commit -m "feat(ventas): la cajera solo ve las ventas de hoy de su sucursal"`

### Task 2: `/sales/stats` cerrado para la cajera

**Files:**
- Modify: `app/routers/sales.py::get_sales_stats` (~L150)
- Modify: `tests/test_sales_stats_y_returns.py::test_sales_stats_cajera_solo_su_sucursal` → renombrar `test_sales_stats_cajera_403` y esperar 403.
- Test: `tests/test_cajero_ventas_del_dia.py::test_gerente_stats_sigue_200`

**Interfaces:** Consumes `es_cajero` (Task 1).

- [ ] **Step 1: Ajustar/añadir tests**: cajera → `status_code == 403`; gerente → 200 con `total_sales` de su sucursal.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_sales_stats_y_returns.py tests/test_cajero_ventas_del_dia.py` → FAIL en el 403.
- [ ] **Step 3: Implement**: al inicio de `get_sales_stats`, `if es_cajero(current_user): raise HTTPException(403, "Los totales del día no están disponibles para la cajera.")`.
- [ ] **Step 4: Run** lo mismo → PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(ventas): la cajera ya no recibe los totales del día"`

### Task 3: Devoluciones — cajera solo hoy, sucursal validada para roles de sucursal

**Files:**
- Modify: `app/routers/returns.py::create_new_return` (~L64)
- Test: `tests/test_cajero_ventas_del_dia.py`

**Interfaces:** Consumes `es_cajero`, `venta_visible_para_cajero` (Task 1).

- [ ] **Step 1: Write the failing tests** (payload mínimo de `SaleReturnCreate`: tomar el de un test existente de devoluciones, p. ej. `grep -rn '"/api/returns/"' tests`)
  - `test_cajero_devuelve_venta_de_hoy`: 200 y `status == "PENDING"`.
  - `test_cajero_no_devuelve_venta_de_ayer`: 403 y `detail == "Solo puedes devolver ventas de hoy. Para días anteriores pide al gerente."`.
  - `test_cajero_no_devuelve_otra_sucursal`: venta de hoy en B → 404.
  - `test_gerente_devuelve_venta_de_ayer` (`auth_gerente_a`): 200.
  - `test_gerente_no_devuelve_otra_sucursal`: venta en B → 404.
- [ ] **Step 2: Run** `python3 -m pytest -q tests/test_cajero_ventas_del_dia.py -k devuelve` → FAIL.
- [ ] **Step 3: Implement** tras encontrar `sale`: para roles no HQ (reusar `_is_hq_role` de `app/routers/sales.py` o el criterio `ADMINISTRADOR/DUEÑO/SUPERADMIN`) con `sale.branch_id != current_user.branch_id` → 404 `"Venta no encontrada"`; luego si `es_cajero` y la venta no es de hoy → 403 con el copy exacto. Las `HTTPException` deben lanzarse antes del `try` (el `except Exception` las convertiría en 500).
- [ ] **Step 4: Run** → PASS; luego `python3 -m pytest -q --ignore=tests/test_cash_complete.py -k "return or devol"` sin nuevos fallos.
- [ ] **Step 5: Commit** `git commit -m "feat(devoluciones): la cajera solo devuelve ventas de hoy; sucursal validada"`

### Task 4: Pantalla Ventas en versión cajera

**Files:**
- Modify: `frontend/src/pages/sales/SalesHistory.tsx`
- Test: `frontend/src/pages/sales/__tests__/SalesHistory.test.tsx`

**Interfaces:** Consumes el contrato de Tasks 1–2 (`/sales/` ya filtrado; `/sales/stats` → 403 para cajera).

- [ ] **Step 1: Write the failing tests** (mockear `useAuthStore` con `role: 'CAJERO'` como ya se hace para HQ/no-HQ en el archivo)
  - `cajera: no pide totales ni enseña KPIs` → `getStats` no llamado; `queryByTestId('kpi-total')` null.
  - `cajera: sin filtros de periodo ni fechas` → `queryByRole('group', { name: 'Periodo' })`, `queryByLabelText('Desde')`, `queryByLabelText('Sucursal')` null.
  - `cajera: título "Ventas de hoy"` y conserva `getByLabelText('Buscar folio o cliente')`.
  - `cajera: list se llama sin start_date ni branch_id`.
  - `gerente: conserva KPIs y periodo` (regresión).
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/pages/sales/__tests__/SalesHistory.test.tsx` → FAIL.
- [ ] **Step 3: Implement**: `const esCajera = useAuthStore((s) => s.user?.role) === 'CAJERO'`. Con `esCajera`: `load` no llama `getStats` ni manda fechas/`branch_id`; no se renderizan KPIs, `BarraFiltros` de periodo/fechas/sucursal ni el toggle de abiertos (queda fijo en cerrados); cabecera `Ventas de hoy · <día de la semana y fecha>` (formatear con `toLocaleDateString('es-MX', { weekday: 'long', day: 'numeric', month: 'short' })`). Tabla, tarjetas en teléfono, paginación, buscador y acciones (Ver, Reimprimir, WhatsApp, Devolver) sin cambios.
- [ ] **Step 4: Run** vitest del archivo + `npx tsc --noEmit` → PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(ventas): pantalla de ventas de hoy para la cajera"`

### Task 5: ReturnModal explica el límite a la cajera

**Files:**
- Modify: `frontend/src/components/pos/modals/ReturnModal.tsx` (~L121-123 y el submit)
- Test: `frontend/src/components/pos/modals/__tests__/ReturnModal.test.tsx` (crear o ampliar si existe)

- [ ] **Step 1: Write the failing tests**
  - Rol CAJERO, `salesApi.list` → `{ items: [] }` → muestra `Ticket no encontrado. Solo aparecen ventas de hoy; para días anteriores pide al gerente.`
  - Rol GERENTE, vacío → sigue mostrando `Ticket no encontrado`.
  - Al confirmar, un 403 del backend muestra su `detail` tal cual.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/components/pos/modals` → FAIL.
- [ ] **Step 3: Implement** el mensaje por rol y que el error del POST muestre `errorDetailText(detail, …)`, si no lo hace ya.
- [ ] **Step 4: Run** → PASS; `npx tsc --noEmit` limpio.
- [ ] **Step 5: Commit** `git commit -m "feat(devoluciones): la cajera sabe que solo busca ventas de hoy"`

### Task 6: Tema oscuro "full black" (pedido del usuario 2026-11-14)

El usuario: "quiero que sea full black, el más oscuro será el nav bar, el body un poco menos". Aplica a toda la app (no solo cajera) en el modo oscuro, y al sidebar en ambos temas (el sidebar ya es oscuro también en modo claro). El modo claro del contenido no cambia; tampoco qué tema es el predeterminado.

**Files:**
- Modify: `frontend/src/index.css` — bloque `:root` (`--sb-bg` ~L110) y bloque `.dark` (~L265-310)
- Test: `frontend/src/__tests__/temaFullBlack.test.ts` (crear; lee `index.css` como texto, igual que `coloresPorTokens.test.ts` lee archivos)

- [ ] **Step 1: Write the failing test** `temaFullBlack.test.ts`:
  - `--sb-bg` vale `#000000` en `:root` y en `.dark`.
  - En `.dark`: `--dax-bg: #0a0a0a`, `--dax-surface: #111111`, `--dax-card-solid: #161616`, `--dax-on-accent: #000000`.
  - En `.dark` no queda ningún hex índigo de la paleta vieja (`#0b0b22`, `#10102a`, `#14142e`, `#0e0e28`).
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/__tests__/temaFullBlack.test.ts` → FAIL.
- [ ] **Step 3: Implement**: los valores de arriba; textos/bordes de `.dark` pasan de tinte índigo a neutro (`--dax-text: #ededed`, `--dax-text-muted: #b5b5b5`, `--dax-text-faint: #8a8a8a`, bordes `rgba(255,255,255,0.14)` / `0.08`, `--dax-row-border: rgba(255,255,255,0.10)`, sombras y `--dax-modal-backdrop` con `rgba(0,0,0,…)`, `--sb-border` y `--sb-text` con base `255,255,255`). `--dax-violet-glow` y los acentos por giro no cambian. Actualizar el comentario "void índigo" → "full black". Si algún otro archivo de `frontend/src` repite los hex índigo viejos para el fondo (buscar con `git grep -n -i "0b0b22\|10102a\|14142e\|0e0e28\|101022" -- frontend/src frontend/index.html`), alinearlo al token; las pruebas de guardia existentes (`coloresPorTokens`, tope de `html.light`) deben seguir verdes.
- [ ] **Step 4: Run** `cd frontend && npx vitest run && npx tsc --noEmit` → PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(tema): modo oscuro full black, barra lateral en negro puro"`

### Task 7: Verificación final y docs

- [ ] **Step 1:** `python3 -m pytest -q --ignore=tests/test_cash_complete.py` → sin fallos nuevos frente a `main` (comparar conteo).
- [ ] **Step 2:** `cd frontend && npm run build && npx vitest run` → verde.
- [ ] **Step 3:** Actualizar `docs/RBAC.md` (fila CAJERO: "Ventas: solo hoy de su sucursal; sin totales; devoluciones solo de hoy") y `docs/API_REFERENCE.md` (`/sales/`, `/sales/stats`, `/returns/`).
- [ ] **Step 4: Commit** `git commit -m "docs: cajera con ventas del día"`

### Task 8: Login nuevo — distribución del ejemplo + identidad de atlasone.com.mx

Spec: anexo "Login" de `docs/superpowers/specs/2026-11-14-cajero-ventas-del-dia-design.md` (valores exactos de paleta, copys, botón y ticket ahí).

**Files:**
- Modify: `frontend/src/pages/Login.tsx` (quitar `HERO_MESSAGES`, rotación, `HairlineArc`, `isRevealed`/`handleReveal`/`handleSceneClick`; conservar `handleSubmit` y su redirección por rol tal cual)
- Rewrite: `frontend/src/pages/login.css` (solo lo usa `Login.tsx`)
- Modify: `frontend/index.html` — no cargar Archivo Black globalmente; cargarla desde `login.css` con `@import url('https://fonts.googleapis.com/css2?family=Archivo+Black&display=swap')` o un `<link>` inyectado por la página, para no tocar la ruta crítica del POS.
- Test: `frontend/src/pages/__tests__/Login.test.tsx` (crear)

- [ ] **Step 1: Write the failing tests** (mockear `authApi.login` y `useNavigate`)
  - `formulario visible sin interacción`: `getByLabelText('Usuario')` y `getByLabelText('Contraseña')` presentes al montar, sin clics.
  - `copys`: `getByText('Software de operación')`, `getByRole('heading', { level: 1 })` contiene `Un punto de venta por` y `cada giro.`; `getByRole('heading', { name: 'Entra a tu tienda' })`; enlace `Conoce Atlas ONE` con `href="https://atlasone.com.mx"`.
  - `CAJERO entra al POS`: login OK con `role: 'CAJERO'` → `navigate('/atlas-pos')`.
  - `error visible`: login rechaza con `detail` → `getByRole('alert')` muestra el texto.
  - `ojo de contraseña`: alterna `type` entre `password` y `text`.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/pages/__tests__/Login.test.tsx` → FAIL.
- [ ] **Step 3: Implement** según el anexo. Colores del sitio como variables CSS locales del contenedor `.login` (p. ej. `--maiz`), no hex sueltos en el TSX. Ticket térmico en CSS puro con contenido de ejemplo genérico (folio, 2–3 partidas, total), `aria-hidden="true"`, oculto en < 768 px con render condicional (`useEsTelefono`). Botones con clases propias de `login.css` (el login no está bajo las guardias del admin; verificar que `botonesDelKit`/`overlaysFueraDelKit` sigan verdes). Accesibilidad: labels asociados, foco visible (`outline 3px maíz`), `autocomplete="username"`/`"current-password"`.
- [ ] **Step 4: Run** vitest completo + `npx tsc --noEmit` + `npm run build` (presupuesto de la ruta crítica debe pasar) → PASS.
- [ ] **Step 5: Capturas** a 390 y 1440 con Playwright (ver memoria/`docs`: paquete de la caché npx; el login ya no esconde los campos) guardadas en `.superpowers/sdd/2026-11-14-cajero-ventas-del-dia/login-390.png` y `login-1440.png`. Si Playwright no arranca, reportarlo (no bloquea).
- [ ] **Step 6: Commit** `git commit -m "feat(login): nuevo login con la identidad de atlasone.com.mx"`
