# SP6 Vista del dueño — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que el dueño entre a `/hq/operations` y responda sus 8 preguntas en una pantalla, con un grupo HQ en el que cada pantalla responde a una pregunta, usa el kit y funciona en teléfono.

**Architecture:** el backend generaliza `GET /api/reports/inicio-basico` a `GET /api/reports/inicio` (alias conservado) con secciones nuevas detrás de `completo=true`, y unifica el umbral de poca existencia en `organization.umbral_poca_existencia`. El frontend convierte `InicioBasico` en `Inicio` (secciones por pregunta, básico = subconjunto), borra `HQOperations`, `HQControl` y `HQBranchDetail`, migra los diálogos HQ a `ui/Modal`, reorganiza Reportes por preguntas y añade costo/importe a Existencias. Guardias: sin `style={{` en `pages/hq`, responsivo, overlays.

**Tech Stack:** FastAPI + SQLAlchemy (tests pytest/SQLite), React 18 + TS + vitest, Playwright (scratchpad) para capturas.

**Spec:** `docs/superpowers/specs/2026-10-21-sp6-vista-dueno-design.md`

## Global Constraints

- Toda consulta filtra `organization_id`; floats en las respuestas (nunca `Decimal`).
- Sin columnas nuevas; `scripts/railway_init.py` no cambia.
- `pages/hq/*` sin `style={{` (salvo líneas con `estilo dinámico`), sin `hidden md:block`, rejillas con prefijo, `useEsTelefono()` + `CabeceraPagina` + `TarjetaFila`.
- Render condicional, nunca `hidden`. Cero `fixed inset-0` nuevos; los HQ migran a `ui/Modal`.
- Chunk del Inicio sin chart.js. Presupuesto de la ruta crítica ≤ 452,500 B.
- Un solo pytest a la vez en el worktree: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py`.
- Commits con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf`.

## Review Focus

1. `sin_movimiento` con una venta `CANCELLED` dentro de la ventana: el producto SÍ debe salir (solo cuentan `SALES_REPORT_STATUSES`). Test en Tarea 2.
2. `completo=true` pedido por un GERENTE: `utilidad_bruta_hoy` debe ser `null` y `sucursales` `null` (va fijado a su sucursal). Test en Tarea 3.
3. Org con dos sucursales pero una de ellas `can_sell=False`: `sucursales` es `null` (una sola que vende). Test en Tarea 3.
4. Umbral capturado en 0: ≤ 0 marca solo lo agotado; no debe caer al default 3. Test en Tarea 1.
5. `Inicio` en básico con el contexto aún sin cargar: no debe pedir `completo=true` por el default `'completo'` del store. Test en Tarea 4 (espera a `loaded`).

---

### Task 0: Herramienta de capturas y baseline

**Files:** scratchpad `sp6-vista-dueno/capturas/` (copia de `modo-basico/capturas/`, puertos 8020/5190, `vite.capturas.config.mts` en `frontend/` excluido de git).

- [x] Copiar la herramienta, cambiar puertos y la ruta `R`.
- [x] `./stack.sh up`; `plan_demo.py ULTRA_PLUS completo`; capturas `baseline/` de `/hq/operations,/hq/reports-hub,/hq/control,/hq/sales,/hq/returns,/hq/inventory,/hq/valor-inventario,/hq/branches` a 390 y 1440, claro y oscuro.
- [x] `plan_demo.py FREE basico`; capturas `baseline-basico/` de `/hq/operations,/hq/reports-hub`.

### Task 1: Umbral único de poca existencia (backend)

**Files:** Modify `app/routers/reports.py`; Modify `app/routers/reports_inicio.py`; Test `tests/test_reports_umbral.py`.

**Interfaces:** Produces `umbral_poca_existencia(db, org_id) -> int` en `app/routers/reports.py` (3 si la org no capturó); `CRITICAL_STOCK_THRESHOLD` desaparece.

- [ ] Test: `test_dashboard_marca_tres_por_defecto` (variantes con 2, 3, 4, 5 → `low_stock` lista 2 y 3); `test_dashboard_respeta_el_umbral_de_la_empresa` (umbral 5 → lista 2..5); `test_umbral_cero_solo_agotados`; `test_command_center_usa_el_mismo_umbral` (`branches[].critical_stock` y `alerts`).
- [ ] Correr: FAIL (hoy marca ≤ 5).
- [ ] Implementar `umbral_poca_existencia`, usarla en `/dashboard`, `/command-center/stats`, `/export/csv`; `reports_inicio.py` la importa y borra `UMBRAL_POCA_EXISTENCIA`.
- [ ] Correr `tests/test_reports_umbral.py tests/test_reports_inicio_basico.py tests/test_variant_traceability.py`: PASS. Commit `feat(reports): umbral único de poca existencia`.

### Task 2: `GET /api/reports/inicio` — alias, `completo`, `sin_movimiento`, `utilidad_bruta_hoy`

**Files:** Modify `app/routers/reports_inicio.py`, `app/schemas/reports.py`; Rename `tests/test_reports_inicio_basico.py` → `tests/test_reports_inicio.py`.

**Interfaces:** Produces schemas `ProductoSinMovimiento {variant_id, nombre, sku, existencia, importe_venta}`, `SinMovimiento {dias, productos}`, `InicioResponse(InicioBasicoResponse)` con `sin_movimiento: Optional[SinMovimiento] = None`, `pendientes: Optional[Pendientes] = None`, `sucursales: Optional[List[SucursalInicio]] = None`, `utilidad_bruta_hoy: Optional[float] = None`. Handler `inicio(branch_id, completo: bool = False, dias_sin_movimiento: int = Query(30, ge=1, le=365))` montado en `/inicio` y `/inicio-basico`.

- [ ] Tests: `test_alias_inicio_basico_sigue_respondiendo`, `test_sin_completo_las_secciones_nuevas_son_null`, `test_sin_movimiento_vendido_hace_diez_dias_sale_con_treinta_no_con_cinco`, `test_sin_movimiento_cancelada_no_cuenta_como_venta`, `test_sin_movimiento_sin_existencia_no_sale_y_otra_org_no_se_mezcla`, `test_sin_movimiento_orden_por_importe_y_tope_diez`, `test_utilidad_bruta_hoy_admin_si_gerente_null`.
- [ ] Correr: FAIL.
- [ ] Implementar `_sin_movimiento(db, org_id, sucursal, dias)` con `~exists()` sobre `SalesLineItem` join `SalesDocument` (`organization_id`, `status.in_(SALES_REPORT_STATUSES)`, `created_at >= ahora - dias`); `importe_venta = existencia * ProductVariant.price`; `_utilidad_bruta_hoy` reusa la resta de `get_daily_summary` (extraer a `utilidad_bruta_del_dia(db, org_id, sucursal, dia)` en `reports.py`).
- [ ] Correr `tests/test_reports_inicio.py`: PASS. Commit `feat(reports): GET /inicio con sin_movimiento y utilidad bruta`.

### Task 3: `pendientes` y `sucursales`

**Files:** Modify `app/routers/reports_inicio.py`, `app/schemas/reports.py`; Test `tests/test_reports_inicio.py`.

**Interfaces:** `DiferenciaCaja {session_id, sucursal, cajera, cerrado_en, esperado, contado, diferencia}`, `Pendientes {devoluciones: int, turnos_abiertos: int, diferencias_caja: List[DiferenciaCaja]}`, `SucursalInicio {branch_id, nombre, ventas_hoy, tickets_hoy, corte: CorteInicio, poca_existencia: int}`.

- [ ] Tests: `test_pendientes_devolucion_pending_turno_viejo_y_diferencia`, `test_pendientes_corte_cuadrado_no_cuenta`, `test_sucursales_null_con_una_sola_que_vende`, `test_sucursales_con_dos_que_venden`, `test_sucursales_null_al_pedir_una_sucursal_y_para_el_gerente`.
- [ ] Correr: FAIL. Implementar `_pendientes`, `_sucursales` (reusa `_periodo`, `_corte`, conteo ≤ umbral por sucursal). Correr: PASS. Commit `feat(reports): pendientes y sucursales en /inicio`.

### Task 4: `Inicio.tsx` único (frontend)

**Files:** Rename `frontend/src/pages/hq/InicioBasico.tsx` → `Inicio.tsx`; Delete `frontend/src/pages/hq/HQOperations.tsx`; Modify `frontend/src/api/reports.ts`, `frontend/src/App.tsx`, `frontend/src/__tests__/modoBasico.test.ts`; Rename test `pages/hq/__tests__/InicioBasico.test.tsx` → `Inicio.test.tsx`.

**Interfaces:** `reportsApi.inicio(params?: { branch_id?: number; completo?: boolean; dias_sin_movimiento?: number }): Promise<Inicio>`; tipo `Inicio` = `InicioBasico` + campos opcionales/null. `reportsApi.inicioBasico` se elimina.

- [ ] Tests (vitest): los de hoy + `en básico pide completo=false y no pinta No se mueve/Pendientes/Sucursales`, `en completo pide completo=true y pinta las tres`, `sucursales null no pinta la sección`, `pendientes en cero dice Nada pendiente`, `espera a loaded antes de pedir`. `modoBasico.test.ts`: `const Inicio = lazy(...)`, ruta `operations` monta `<Inicio />`, `Inicio.tsx` sin chart.js, `PorPerfil` sigue en reports-hub.
- [ ] Implementar: `Inicio` lee `useEnabledModulesStore` (`loaded`, `load`, `perfilUi`); secciones `Cifras`, `Caja`, `ValorTiendaCard`, `SeAcaba`, `NoSeMueve`, `MasVendido`, `Sucursales`, `Pendientes` con `data-testid`; enlaces: Existencias `/hq/inventory?q=<sku>&variant=<id>`, Devoluciones `/hq/returns`, Corte `/cash-history`, Sucursales `/hq/branches/<id>`.
- [ ] `npm run test -- src/pages/hq src/__tests__/modoBasico.test.ts` PASS; `tsc` PASS. Commit `feat(hq): Inicio único por preguntas; adiós HQOperations`.

### Task 5: Menú y rutas

**Files:** Modify `navConfig.ts`, `navPerfilPlan.ts`, `navPerfilBasico.ts`, `utils/navMovil.ts`, `App.tsx`; Delete `pages/hq/HQControl.tsx`; tests `navConfig.test.ts`, `navPerfilPlan.test.ts`, `navPerfilBasico.test.ts`, `navMovil.test.ts`, `rutaInicio.test.ts`.

- [ ] Tests: `ALL_NAV` sin `/hq/control` ni `/mobile/owner`; `HQ_NAV_GROUPS` sin grupo Móvil; `ROLE_ROUTES.ADMINISTRADOR` conserva `/mobile/owner` y pierde `/hq/control`; administradora en básico sigue con 8; FREE admin ya no "pierde" `/hq/control` (no existe); `navMovil` del dueño: `Resumen` apunta a `rutaInicioPorRol`.
- [ ] Implementar, borrar `HQControl.tsx` y su ruta. vitest de layout + utils PASS. Commit `feat(hq): menú sin Control ni Resumen móvil`.

### Task 6: Sucursales fusionada

**Files:** Modify `pages/hq/HQBranches.tsx`; Delete `pages/hq/HQBranchDetail.tsx`; Modify `App.tsx` (`branches/:branchId` → `HQBranches`).

- [ ] Implementar: `useParams` + `useNavigate`; tarjetas (botón, 44 px) → `navigate('/hq/branches/'+id)`; panel de detalle con `reportsApi.dashboard({start_date: hoy, end_date: hoy, branch_id})`; "Abierta" = `status === 'ONLINE'`; `CabeceraPagina`; `TarjetaFila` para últimas ventas/poca existencia en teléfono; sin `client`.
- [ ] Test `pages/hq/__tests__/HQBranches.test.tsx`: con `:branchId` en la URL pinta el detalle de esa sucursal; sin él, solo la rejilla. Commit `feat(hq): Sucursales con detalle en la misma pantalla`.

### Task 7: Existencias con costo e importe

**Files:** Modify `pages/hq/HQInventory.tsx`; Test `pages/hq/__tests__/HQInventory.test.tsx`.

- [ ] Test: admin ve columnas Costo/Importe venta/Importe costo y totales; casilla "Solo sin costo" deja los renglones con `cost` nulo o 0; el ajuste abre `ui/Modal` (role dialog).
- [ ] Implementar (`useAuthStore` para `veCosto`), modal del kit, `TarjetaFila` con `datos` de importe. Quitar de `CONOCIDOS`. Commit `feat(hq): Existencias con costo, importe y filtro sin costo`.

### Task 8: Ventas y Devoluciones en `ui/Modal`

**Files:** Modify `pages/hq/HQSalesLog.tsx`, `pages/hq/HQReturns.tsx`, `api/sales.ts` (`salesApi.stats`); `__tests__/overlaysFueraDelKit.test.ts` (quitar las 3 entradas HQ).

- [ ] Implementar; `grep -c "fixed inset-0"` = 0 en los tres; sin `client.get` en HQ. vitest PASS. Commit `refactor(hq): diálogos de Ventas y Devoluciones en ui/Modal`.

### Task 9: Reportes por preguntas, Valor sin inline, guardias

**Files:** Modify `pages/hq/HQReportsHub.tsx`, `pages/hq/HQValorInventario.tsx`; Create `pages/__tests__/hqSinEstilosInline.test.ts`; Modify `pages/__tests__/responsivoOla2.test.ts` (PAGINAS + hq).

- [ ] Guardias primero (FAIL), luego: secciones `Titulo pregunta=…` en el orden del spec §6, sin "Alertas de stock bajo" ni "Ultra", alturas `h-60`, `hidden sm:block` → `esTelefono`, top 10 con `TarjetaFila`; `HQValorInventario` `style={{ color: var(--dax-text-muted) }}` → `text-dax-muted` (clase existente en `index.css`). Guardias PASS. Commit `refactor(hq): Reportes por preguntas y HQ sin estilos inline`.

### Task 10: Docs, verificación y cierre

**Files:** `docs/FRONTEND_VIEWS.md`, `docs/API_REFERENCE.md`, `docs/modo-basico.md`, `docs/RBAC.md` si lista `/hq/control`, `CLAUDE.md` (receta modo básico menciona `PorPerfil`: sigue válida).

- [ ] Docs. pytest completo, vitest completo, `npm run build`, `python3 scripts/presupuesto_bundle.py`.
- [ ] Capturas finales: `sucursal2.py` (segunda sucursal que vende, en el scratchpad) → `final/` (ULTRA+ completo) y `final-basico/` (FREE básico), 390 y 1440; 0 desbordes, 0 scroll interno a 390; taps ≥ 44.
- [ ] Commit `docs(sp6): vista del dueño`. Informe `scratchpad/mega-plan-cierre/sp6-final.md`.
