# SP6 · Vista del dueño — diseño

**Fecha:** 2026-10-21 · **Estado:** aprobado para planear · **Padre:** mega plan 2026-10
(`docs/superpowers/specs/2026-10-14-mega-plan-altas-docs-responsivo-agente-design.md`, §SP6 y
decisión abierta 10). **Caso guía:** Eleven Fashion (ULTRA+, una sucursal que vende); las FREE
(Kaory, Coqueta, Imaltzin) entran por el modo básico (`docs/modo-basico.md`).

## 1. Problema

El dueño entra a `/hq/operations` y encuentra un tablero genérico (`HQOperations`, 785 líneas,
estilos inline, chart.js) que no junta lo que pregunta cada mañana. El grupo HQ tiene 9 pantallas
y 37 entradas de menú; tres de ellas (`HQOperations`, `HQReportsHub`, `HQControl`) repiten los
mismos KPIs sobre `command-center/stats`, `HQControl` es una rejilla de seis enlaces que ya
están en el menú, `HQBranchDetail` es una segunda pantalla para un dato que cabe en Sucursales,
y "poca existencia" se calcula con tres criterios distintos (≤ 5 fijo en `/dashboard`, ≤ 5 fijo
en `/command-center`, `umbral_poca_existencia` en `/inicio-basico`).

## 2. Las preguntas del dueño (validadas con el usuario el 2026-10-21)

Cada pregunta tiene UNA pantalla que la responde al entrar (el Inicio) y una pantalla de detalle.
Lo que no responde a ninguna pregunta sale del menú HQ.

| # | Pregunta | Inicio | Detalle |
|---|---|---|---|
| 1 | ¿Cuánto vendí hoy y ayer, y cómo me pagaron? | cifras hoy/ayer/7 días + cobros por método | Ventas (`/hq/sales`), Reportes |
| 2 | ¿Cómo va la caja? | turno abierto/cerrado, esperado vs contado | Corte de caja (`/cash-history`) |
| 3 | ¿Cuánto vale mi tienda y cuánto me falta por costear? | tarjeta de valor (SP3) | Valor de la tienda (`/hq/valor-inventario`) |
| 4 | ¿Qué se está acabando? | lista ≤ umbral de la empresa | Existencias (`/hq/inventory`) |
| 5 | ¿Qué no se mueve? | productos con existencia y sin venta en N días | Existencias |
| 6 | ¿Qué se vendió más? | top 5 de 7 días | Reportes |
| 7 | ¿Cómo va cada sucursal? | solo si hay > 1 que vende: ventas hoy, turno, poca existencia | Sucursales (`/hq/branches`) |
| 8 | ¿Qué tengo pendiente? | devoluciones por aprobar, turnos abiertos > 24 h, diferencias de caja de 7 días | Devoluciones, Corte de caja |

**Mapa pantalla → pregunta del grupo HQ (después de SP6):**

| Pantalla | Ruta | Pregunta | Qué cambia |
|---|---|---|---|
| Inicio | `/hq/operations` | 1-8 | una sola pantalla `Inicio` para básico y completo (§3) |
| Reportes | `/hq/reports-hub` | 1, 6, 7 | secciones con nombre y pregunta, sin inline, responsivo (§6) |
| Valor de la tienda | `/hq/valor-inventario` | 3 | sin cambios funcionales; inline → clases |
| Ventas | `/hq/sales` | 1 | detalle en `ui/Modal`; `sales/stats` por `salesApi` (§7) |
| Devoluciones | `/hq/returns` | 8 | detalle y rechazo en `ui/Modal` (§7) |
| Existencias | `/hq/inventory` | 4, 5 | costo e importe por fila, totales, filtro "sin costo", ajuste en `ui/Modal` (§5) |
| Sucursales | `/hq/branches` (+ `/:branchId`) | 7 | lista + detalle de la sucursal elegida en la misma pantalla (§8) |
| ~~Control~~ | ~~`/hq/control`~~ | — | **se elimina** (§9) |
| ~~Resumen móvil~~ | `/mobile/owner` | — | **sale del menú**; la ruta sigue abriendo (§9) |

Fuera de alcance: plataforma (`/platform/*`), vistas de cajera, gastro, `/home` de presets
`ATLAS_ONE_*`, instantánea diaria del valor (decisión 8 del mega plan), RBAC (`ROLE_ROUTES` solo
pierde las URLs que desaparecen).

## 3. Inicio único

### 3.1 Backend: `GET /api/reports/inicio`

`GET /api/reports/inicio-basico` se generaliza. La ruta nueva es `/inicio`; `/inicio-basico`
queda como alias (mismo handler) para clientes con el frontend viejo en caché. Parámetros:

- `branch_id` (como hoy: ADMIN/DUEÑO/SUPERADMIN la org o una sucursal, GERENTE la suya, demás 403).
- `completo: bool = False`. Con `false` la respuesta es exactamente la de hoy (`hoy`, `ayer`,
  `semana`, `por_metodo_hoy`, `top_semana`, `poca_existencia`, `corte`) y las secciones nuevas
  viajan en `null`: la FREE en una PC vieja no paga consultas que no pinta. Con `true` se
  calculan las cuatro secciones nuevas.
- `dias_sin_movimiento: int = 30` (1..365), solo cuenta con `completo=true`.

Secciones nuevas (schemas en `app/schemas/reports.py`, todo `float`, nunca `Decimal`):

- `sin_movimiento: {dias, productos: [{variant_id, nombre, sku, existencia, importe_venta}]} | null`.
  Variantes activas, no borradas, con existencia > 0 en las sucursales del ámbito (sin
  `branch_id`: activas que venden, como `poca_existencia`) y SIN renglón de venta
  (`sales_lines` ligado a un `sales_documents` en `SALES_REPORT_STATUSES`) con `created_at`
  dentro de los últimos `dias` días. `importe_venta = existencia × precio base de la variante`.
  Orden: importe desc, nombre, variant_id; máx. 10. Se implementa con `NOT EXISTS` sobre
  `sales_lines`/`sales_documents` filtrado por `organization_id` y fecha; en Postgres usa el
  índice existente de `sales_documents(organization_id, created_at)` y el de
  `sales_lines(variant_id)`; no hace falta índice nuevo (consulta acotada a la org y a 10 filas).
- `pendientes: {devoluciones, turnos_abiertos, diferencias_caja: [{session_id, sucursal, cajera, cerrado_en, esperado, contado, diferencia}]} | null`.
  `devoluciones` = `SaleReturn.status == 'PENDING'` del ámbito. `turnos_abiertos` = sesiones
  `OPEN` con `opened_at` hace más de 24 h. `diferencias_caja` = cortes cerrados en los últimos
  7 días cuya diferencia recalculada (`compute_expected_cash`, igual que
  `/audit/discrepancies`) es ≠ 0, máx. 10, más recientes primero.
- `sucursales: [{branch_id, nombre, ventas_hoy, tickets_hoy, corte: CorteInicio, poca_existencia}] | null`.
  Solo cuando la org tiene más de una sucursal activa que vende y no se pidió `branch_id`; si
  no, `null`. `poca_existencia` es el conteo de variantes ≤ umbral en esa sucursal.
- `utilidad_bruta_hoy: float | null`. Ventas de hoy menos `coalesce(unit_cost, 0) × cantidad`
  (mismo cálculo que `/daily-summary`). Solo para ADMIN/DUEÑO/SUPERADMIN; el gerente recibe
  `null` (misma regla que el costo en la valuación).

Todo filtra `organization_id` (regla de oro 5). Sin columnas nuevas: `scripts/railway_init.py`
no cambia.

### 3.2 Umbral único de poca existencia

`organization.umbral_poca_existencia` (3 si es nulo) pasa a ser EL criterio de "poca
existencia" en toda la app. Una función `umbral_poca_existencia(db, org_id) -> int` vive en
`app/routers/reports.py` y la usan `/dashboard` (`low_stock`), `/command-center/stats`
(`critical_stock` por sucursal y `alerts`), `/export/csv` (sección "Alertas Stock Bajo") e
`/inicio`. `CRITICAL_STOCK_THRESHOLD` desaparece. Consecuencia para las orgs de paga: el
tablero deja de marcar ≤ 5 y marca ≤ 3 hasta que la dueña capture su tope en Empresa; se
documenta en `docs/API_REFERENCE.md` y `docs/modo-basico.md`.

### 3.3 Frontend: `pages/hq/Inicio.tsx`

`InicioBasico.tsx` se renombra a `Inicio.tsx` (componente `Inicio`) y crece por secciones, una
por pregunta, cada una con su título y su enlace de detalle. `HQOperations.tsx` se borra.
`/hq/operations` monta `<Inicio />` directamente (sin `PorPerfil`); `Inicio` espera a
`enabledModulesStore.loaded` (como `PorPerfil`) y decide con `useModoBasico()`:

| Sección | Básico | Completo |
|---|---|---|
| 1 Cifras hoy/ayer/7 días + cobros de hoy | sí | sí (+ utilidad bruta de hoy si viene) |
| 2 Caja | sí | sí |
| 3 Valor de la tienda (tarjeta SP3) | sí | sí |
| 4 Se está acabando | sí | sí |
| 5 No se mueve | no | sí |
| 6 Lo más vendido | sí | sí |
| 7 Sucursales | no | sí, solo si `sucursales` no es `null` |
| 8 Pendientes | no | sí |

La pantalla pide `reportsApi.inicio({ completo: !modoBasico })` y `valorInventario`. Sin
chart.js ni react-chartjs-2 en el chunk (el guard `modoBasico.test.ts` se actualiza al nombre
nuevo y lo sigue exigiendo); el ritmo por hora y la dona de métodos viven en Reportes.
`PorPerfil` se conserva para `/hq/reports-hub`. Cero `style={{` en `pages/hq/*` (§10).

## 4. Menú y rutas

- `navConfig.ts`: salen `Control` (`/hq/control`) y `Resumen móvil` (`/mobile/owner`) de
  `ALL_NAV`; `HQ_NAV_GROUPS` pierde `/hq/control` y el grupo `Móvil`. `ROLE_ROUTES` pierde
  `/hq/control` en ADMINISTRADOR y DUEÑO; `/mobile/owner` se queda en `ROLE_ROUTES` (la ruta
  sigue abriendo por URL y desde el panel móvil del vendedor no se llega: `navMovil.ts` lo usa
  solo para el DUEÑO en teléfono, y ese caso se cambia a `rutaInicioPorRol`).
- `navPerfilPlan.ts` (FREE) y `navPerfilBasico.ts` (`OCULTAS_BASICO_HQ`) dejan de listar
  `/hq/control` y `/mobile/owner` (ya no existen en el menú). La administradora en básico sigue
  viendo exactamente 8 entradas.
- `App.tsx`: se quitan las rutas `/hq/control` y el import de `HQControl`, `HQOperations`,
  `HQBranchDetail`; `/hq/branches/:branchId` monta `HQBranches`.
- `rutaInicio.ts` no cambia: ADMINISTRADOR y DUEÑO siguen entrando a `/hq/operations`.
- `docs/FRONTEND_VIEWS.md`, `docs/modo-basico.md`, `docs/API_REFERENCE.md` se actualizan.

## 5. Existencias (`HQInventory.tsx`)

- Cada renglón (variante) muestra además **Costo**, **Importe a venta** (`existencia × precio`)
  e **Importe a costo** (`existencia × costo`); las dos columnas de costo solo para
  ADMINISTRADOR/DUEÑO (`useAuthStore`), el gerente no entra a esta pantalla. Pie con totales de
  los renglones listados.
- Filtro "Solo sin costo" (casilla): deja los renglones con `cost` nulo o ≤ 0. Es filtro de
  cliente sobre la búsqueda (máx. 30 productos), no un parámetro nuevo: la pregunta "¿qué me
  falta por costear?" se responde completa en Valor de la tienda; aquí es para corregir
  mientras se busca. Ruling: no se toca `GET /api/products/hq-inventory`.
- Enlaces de entrada: desde el Inicio, "No se mueve" y "Se está acabando" abren
  `/hq/inventory?q=<sku>&variant=<id>` (ya soportado).
- El diálogo "Ajuste de Inventario" pasa a `ui/Modal` (sale de `CONOCIDOS`).

## 6. Reportes (`HQReportsHub.tsx`)

Se mantiene chart.js (es la única pantalla HQ con gráficas) y se reorganiza en secciones con
nombre y pregunta, en este orden, cada una un `DaxCard` con `<Titulo pregunta="…">`:

1. **Resumen del periodo** (¿cuánto vendí?): 6 KPIs.
2. **Ritmo de hoy** (¿cómo va el día?): velocímetro y cumplimiento.
3. **Tendencia** (¿voy mejor que el periodo anterior?): línea doble.
4. **Cómo me pagan** (¿cómo me pagaron?): dona.
5. **Día y hora** (¿cuándo vendo más?): mapa de calor.
6. **Sucursales** (¿cómo va cada sucursal?): leaderboard, solo si hay > 1.
7. **Lo más vendido** (¿qué se vendió más?): top 10.

Se quita "Alertas de stock bajo" (es la pregunta 4 y vive en el Inicio y en Existencias) y la
etiqueta "Ultra". Sin `style={{` (alturas por clase `h-60`, barras de porcentaje con una
clase de ancho por décimas), sin `hidden sm:block`/`hidden md:block` (render condicional con
`useEsTelefono()`), top 10 con `TarjetaFila` en teléfono.

## 7. Ventas y Devoluciones

- `HQSalesLog`: el detalle de venta pasa a `ui/Modal` (`title` = folio, `size="lg"`); la
  llamada `client.get('/sales/stats')` pasa a `salesApi.stats(params)` en `api/sales.ts`.
- `HQReturns`: detalle (con Aprobar/Rechazar en `footer`) y rechazo con motivo pasan a
  `ui/Modal`; los dos `style={{ color: var(--dax-text…) }}` pasan a clases.
- Los tres archivos salen de `CONOCIDOS` en `overlaysFueraDelKit.test.ts` (quedan 48).

## 8. Sucursales (`HQBranches.tsx`)

Una sola pantalla: rejilla de tarjetas (como hoy, pero "Abierta" sale de `status === 'ONLINE'`
del backend y no de `pending_cuts`) y, al elegir una, el detalle que hoy pinta
`HQBranchDetail` (KPIs de hoy, información, top 5, poca existencia, últimas ventas) debajo de la
rejilla, con botón "Cerrar". La URL `/hq/branches/:branchId` monta el mismo componente con esa
sucursal elegida (enlaces viejos siguen funcionando). Datos por `organizationApi.getBranches`,
`reportsApi.commandCenterStats` y `reportsApi.dashboard({ branch_id })`; cero `client.get`
directo. `HQBranchDetail.tsx` se borra. Kit: `CabeceraPagina`, `TarjetaFila` en teléfono para
últimas ventas y poca existencia.

## 9. Lo que se quita

- `HQControl.tsx`: sus diferencias de caja son la pregunta 8 (Inicio → `pendientes`); su
  bitácora leía `/platform/audit/logs` (endpoint de plataforma) y desaparece; sus seis enlaces
  están en el menú.
- `HQOperations.tsx` y `HQBranchDetail.tsx`: absorbidos por `Inicio` y `HQBranches`.
- Ítem "Resumen móvil": `pages/mobile/MobileOwnerDashboard.tsx` y su ruta se conservan (no
  se borra código que funciona en teléfono), pero no hay entrada de menú.

## 10. Guardias y pruebas

- `frontend/src/pages/__tests__/hqSinEstilosInline.test.ts`: ningún archivo de `pages/hq/`
  contiene `style={{`, salvo líneas marcadas con el comentario `estilo dinámico` (barras cuyo
  ancho viene del dato).
- `responsivoOla2.test.ts` → `PAGINAS` suma `hq/Inicio.tsx`, `hq/HQReportsHub.tsx`,
  `hq/HQSalesLog.tsx`, `hq/HQReturns.tsx`, `hq/HQBranches.tsx`, `hq/HQValorInventario.tsx`
  (`SIN_TARJETA_FILA` para las que listan con tarjetas propias). Prohíbe `hidden md:block`.
- `overlaysFueraDelKit.test.ts`: `CONOCIDOS` sin HQInventory, HQReturns, HQSalesLog.
- `modoBasico.test.ts`: `Inicio` con `lazy()` en `App.tsx`, montado en `/hq/operations`, sin
  chart.js; `PorPerfil` sigue en `/hq/reports-hub`.
- `navPerfilBasico.test.ts`, `navPerfilPlan.test.ts`, `navConfig.test.ts`: sin `/hq/control`
  ni `/mobile/owner`; la administradora en básico sigue con 8 entradas.
- `pages/hq/__tests__/Inicio.test.tsx`: lo de hoy más: en básico no pide `completo` ni pinta
  "No se mueve"/"Pendientes"/"Sucursales"; en completo sí; `sucursales: null` no pinta la
  sección; `pendientes` en cero pinta "Nada pendiente".
- pytest `tests/test_reports_inicio.py` (renombrado): alias, `completo=false` sin secciones,
  `sin_movimiento` (vendido hace 10 días sale con 30, no con 5; existencia 0 no sale; otra org
  no), `pendientes` (devolución PENDING, turno de 25 h, diferencia ≠ 0 de ayer, cuadrado no),
  `sucursales` (null con una sucursal; dos sucursales con sus cifras; null con `branch_id`),
  `utilidad_bruta_hoy` (admin sí, gerente null), gerente/cajera como hoy.
- pytest umbral: `/dashboard` y `/command-center` marcan ≤ 3 por defecto y ≤ `umbral` cuando
  la org lo capturó (`tests/test_reports_umbral.py`).

## 11. Verificación

Capturas Playwright (herramienta en el scratchpad, puertos 8020/5190) a 390 y 1440 en los dos
temas: baseline antes de código (hecho en Tarea 0) y final de `/hq/*` + `/reports` como
`demo_pos` en ULTRA+ completo y en FREE básico, con una segunda sucursal que vende para la
sección 7. Criterios: 0 desbordes, 0 scroll interno a 390, taps ≥ 44 px, sin `style={{`.

## 12. Criterios de salida

- El dueño de Eleven responde las 8 preguntas desde `/hq/operations` sin abrir otra pantalla.
- `pages/hq/` sin `style={{`; cero overlays a mano en HQ; cero `client.get` directo en HQ.
- Menú HQ sin Control ni Resumen móvil; la FREE en básico sigue con 8 entradas.
- pytest, vitest, `tsc`, `vite build` y presupuesto (≤ 452,500 B) en verde.

## 13. Riesgos

- `inicio?completo=true` suma 4-6 consultas; todas acotadas a la org, a hoy/7 días y a 10
  filas. Si en Eleven (≈ 2,000 variantes) `sin_movimiento` tarda, se baja `dias` o se añade
  índice `sales_lines(organization_id, variant_id)` en `railway_init.py`.
- Cambiar el umbral de ≤ 5 a ≤ 3 por defecto cambia lo que ven las orgs de paga; aviso en docs.
- Borrar `HQControl` deja sin UI la bitácora de tenant (que de todos modos leía un endpoint de
  plataforma). Si alguien la pide, es un reporte nuevo con endpoint propio.
