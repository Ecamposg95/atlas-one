# Atlas One — Mapa de Vistas del Frontend

> Referencia de las **76 vistas** de `frontend/src/pages/`. Pensada para ubicar rápido "¿qué archivo es esta pantalla, quién la ve, de dónde saca los datos y con qué se relaciona?".
> Generada por auditoría de código (julio 2026). Los `file:line` y conteos de líneas son puntos de entrada, no exhaustivos — verifica contra el código antes de asumir.

## Cómo leer este documento

- **§1 Arquitectura global** — el andamiaje que comparten todas las vistas: routing, layouts, gating (rol + módulo), tema, stores y componentes base. **Léelo primero.**
- **§2–§9** — una ficha por vista, agrupadas por dominio. Cada ficha: propósito, quién la ve, datos/API, componentes clave, estado & notas.
- **§10 Hallazgos transversales** — duplicaciones, migraciones a medias y deuda que cruzan varios dominios. Útil antes de refactorizar.

---

## 1. Arquitectura global

### Routing (`App.tsx`)
Tres árboles bajo `<BrowserRouter>`:
1. **`/login`** — público (`Login.tsx`).
2. **`/` (App shell)** — envuelto en `Layout` (sidebar + topbar) tras auth. Aquí viven casi todas las vistas operativas. Incluye `/hq/*`, `/mobile/*`, y el resto de rutas planas.
3. **`/platform/*`** — panel super-admin, envuelto en `PlatformLayout` (sidebar propia), gate SUPERADMIN.

`RoleHomeRedirect` (index de `/`) decide el landing por rol/preset: gastro → `/home`; sin preset Atlas One → `/hq/operations`. El **login** enruta directamente: SUPERADMIN→`/platform/metrics`, VENDEDOR/SOPORTE→`/mobile/dashboard`, CAJERO/GERENTE→`/atlas-pos`, CLIENTE→`/portal`, Admin/Dueño→`/`.

### Gating en dos capas (defensa en profundidad; el backend siempre revalida)
1. **Por rol** — `ROLE_ROUTES` en `components/layout/Sidebar.tsx` lista las URLs permitidas por rol tenant. El guard `RequireRole` (`components/layout/RequireRole.tsx`) protege rutas puntuales; es **solo UX** (evita redirecciones confusas), no seguridad. SUPERADMIN/SUPPORT saltan el RBAC tenant.
2. **Por módulo** — cada ítem de nav declara `module: 'pos'|'catalog'|...`; solo aparece si `enabledModulesStore.enabledModules` lo incluye (fail-open: si la lista está vacía porque `/me/context` no cargó, se muestran todos los permitidos por rol). El preset de la org define qué módulos están activos.

**Roles tenant:** `ADMINISTRADOR`, `DUEÑO` (HQ, ven todo), `GERENTE`, `CAJERO` (sucursal), `VENDEDOR` (móvil), `SOPORTE_OPERATIVO`, `CLIENTE` (portal). **Platform:** `SUPERADMIN`, `SUPPORT` (via `platform_role`).

### Tema
Tokens CSS `--dax-*` + clases `.dax-*` en `index.css`, modo claro/oscuro por `.light`/`.dark` en `<html>`. La app arranca en oscuro; un shim `html.light` con `!important` remapea las clases `slate/white` hardcodeadas. **La mayoría de vistas son dark-first**; las que respetan el tema claro de verdad son pocas (Reports, HQReportsHub, MobileOwnerDashboard). El panel Platform usa su propio tema (`platform-v2.css`, tokens `--p-*`).

### Stores (Zustand, `store/`)
- `authStore` — user, token, org, branch, `hydrated`, `platform_role`.
- `enabledModulesStore` — módulos habilitados + preset activo (pinta `data-preset` en `<html>`).
- `posStore` — carrito, sesión de caja, `printerName`, cliente, propina, descuento global.
- `impersonationStore` — modo auditoría (super-admin actuando como org).
- `toastStore` — toasts globales (varias vistas viejas aún usan `alert()`/`confirm()` nativos).

### Componentes base compartidos
`DaxCard` (tarjeta tokenizada), `StatusChip`/`Badge` (estados), `Button` (`dax-btn-*`), `Spinner`, `.dax-input`, `.dax-table`. Gráficas: `components/atlas-one/*` (BarChart, Sparkline, Donut, LineChart) y Chart.js en varias vistas HQ/reportes.

### Índice maestro (ruta → archivo → quién)
| Ruta | Archivo | Roles | Módulo |
|---|---|---|---|
| `/login` | `Login.tsx` | público | — |
| `/` (index) | `RoleHomeRedirect` | todos | — |
| `/home` | `home/PresetHome` | Admin, Dueño (gastro) | — |
| `/atlas-pos` | `pos/AtlasPOS` | Gerente, Cajero | pos |
| `/pos` | `pos/POS` | Cajero, Gerente | pos |
| `/printer-settings` | `pos/PrinterSettings` | Cajero, Gerente | pos |
| `/sales` | `sales/SalesHistory` | Gerente, Cajero | pos |
| `/quotes`, `/quotes/new` | `sales/Quotes`, `QuoteMaker` | Admin, Dueño | quotes |
| `/returns` | `sales/Returns` | Gerente, Cajero | returns |
| `/seguimiento` | `sales/Seguimiento` | Admin, Dueño | quotes |
| `/hq/operations` | `hq/HQOperations` | Admin, Dueño | pos |
| `/hq/reports-hub` | `hq/HQReportsHub` | Admin, Dueño | pos |
| `/hq/control` | `hq/HQControl` | Admin, Dueño | pos |
| `/hq/sales` | `hq/HQSalesLog` | Admin, Dueño | pos |
| `/hq/returns` | `hq/HQReturns` | Admin, Dueño | returns |
| `/hq/inventory` | `hq/HQInventory` | Admin | inventory |
| `/hq/branches`, `/:id` | `hq/HQBranches`, `HQBranchDetail` | Admin (detail: +Dueño) | inventory/pos |
| `/labels` | `labels/Labels` | Admin, Dueño, Gerente, Cajero | labels |
| `/products`, `/new`, `/:id/edit` | `inventory/Products`, `products/ProductForm` | Admin, Dueño, Gerente, Cajero | catalog |
| `/inventory` | `inventory/Inventory` | — | inventory |
| `/logistics`, `/boxes` | `inventory/Logistics`, `Boxes` | — | logistics |
| `/admin/catalog`, `/admin/products/new` | `core/AdminCatalog`, `admin/AdminProductCreate` | Admin | catalog |
| `/departments`, `/brands` | `core/Departments`, `Brands` | Admin | catalog (hideForGastro) |
| `/cash-history` | `finance/CashHistory` | Gerente, Cajero | cash_management |
| `/expenses`, `/purchases` | `finance/Expenses`, `Purchases` | Admin, Dueño | payments |
| `/reports` | `finance/Reports` | Gerente | — |
| `/customers` | `crm/Customers` | Admin, Dueño | crm |
| `/hr`, `/hr/me` | `hr/HR`, `HRMe` | Admin / todos | — |
| `/portal` | `portal/Portal` | Cliente | — |
| `/users`, `/organization`, `/startup` | `core/Users`, `Organization`, `Startup` | Admin | — |
| `/home`, `/tables`, `/kitchen`, `/meseros`, `/bar/bottles`, `/menu`, `/recipes` | ver §2 Gastro | según preset | tables/kitchen/bar/menu/recipes |
| `/mobile/*` | `mobile/*` | Vendedor (owner: Dueño/Admin) | — |
| `/appointments`, `/commissions`, `/memberships`, `/ai`, `/purchasing` | `coming-soon/index` | según módulo | (stubs) |
| `/platform/*` | `platform/*` | SUPERADMIN | — |
| `/__dev__/atlas-one-preview` | `__dev__/AtlasOnePreview` | solo dev | — |
| `*` | `NotFound` | todos | — |

---

## 2. Home & Gastro (RESTAURANT / CAFE / BAR)

> Los 3 presets gastro comparten motor. Restaurant = superset (cocina+mesas+bar+comisiones); Café = Restaurant sin {mesas, bar, comisiones}; Bar = Restaurant sin {cocina}. Ver `docs/audits/` para el detalle de robustez.

### `/home` — Home por preset (router)
- **Archivo:** `pages/home/PresetHome.tsx` (377 líneas)
- **Propósito:** Switch por `preset` que renderiza el home correcto. Los 3 gastro (`RestaurantHome`/`CafeHome`/`BarHome`) delegan al mismo `GastroHomeDay` variando title/subtitle/accent/topLabel/acciones; los verticales no-gastro (Barber/Beauty/Retail…) usan un `HomeShell` local con **otro** sistema de tokens (`--p-*` inline). Default no-Atlas-One → `Navigate /hq/operations`.
- **Quién la ve:** Admin/Dueño de una org con preset Atlas One (gastro landea aquí desde login).
- **Datos/API:** ninguno directo (delega). Accent por preset: restaurant `#e2531b`, café `#8b4a2b`, bar `#7c3aed`.
- **Notas:** **Inconsistencia arquitectónica** — PresetHome (tokens `--p-*` inline) y su hijo GastroHomeDay (tokens `--dax-*` + Tailwind) hablan idiomas distintos. Fugas: BarHome enlaza "Inventario líquido" a `/inventory` genérico, no a `/bar/bottles`; Comisiones se ofrece como CTA "beta" pero es un ComingSoon; ningún home expone `/menu` ni `/meseros`.

### `/home` (cuerpo) — Home del día
- **Archivo:** `pages/home/GastroHomeDay.tsx` (213 líneas)
- **Propósito:** Dashboard del día para gastro: KPIs (ventas, órdenes, ticket promedio, cuentas abiertas), gráfica top del día, ritmo por hora y grid de accesos rápidos.
- **Quién la ve:** presets RESTAURANT/CAFE/BAR (via PresetHome).
- **Datos/API:** `reportsApi.dashboard({start,end,branch_id})` del día. Store `useAuthStore` (branch).
- **Componentes clave:** `DaxCard`, `BarChart`, `Sparkline`. Deltas emerald/rose.
- **Notas:** Skeleton parcial (solo KPIs, con texto "Cargando…" dentro de la tarjeta); `money()` redefinido local (dup de `utils/currency`); accesos rápidos siempre visibles aunque el reporte falle. Dark-first.

### `/tables` — Mesas (plano de salón)
- **Archivo:** `pages/tables/FloorPlan.tsx` (222 líneas)
- **Propósito:** Plano por áreas con estado de cada mesa (libre/ocupada/…), KPIs (ocupadas/libres/cuentas abiertas/tiempo prom.), abrir/liberar mesa y crear áreas/mesas.
- **Quién la ve:** Admin, Dueño, Gerente, Cajero — módulo `tables` (RESTAURANT y BAR).
- **Datos/API:** `tablesApi.listAreas/listTables/createArea/createTable/open/free`, `parkedTicketsApi.get` (total de cuenta), `kitchenApi.feed` (comandas en cocina por mesa).
- **Componentes clave:** `StatusChip` + `toneBorder/toneBg`, `TableFormModal`, `DaxCard`.
- **Notas:** **6 hues decorativos** en los KPIs (arcoíris sin significado — el peor caso de ruido de color). Loading = Spinner full-screen (layout shift). Punto de entrada natural a la Comanda.

### `/kitchen` — Cocina (KDS)
- **Archivo:** `pages/kitchen/KDS.tsx` (156 líneas)
- **Propósito:** Tablero kanban de comandas activas por estación: avanzar (bump) ítem o comanda completa, crear estaciones. Auto-refresco cada 8s.
- **Quién la ve:** Admin, Dueño, Gerente, Cajero — módulo `kitchen` (RESTAURANT y CAFE; **no** BAR).
- **Datos/API:** `kitchenApi.feed/listStations/createStation/bumpItem/bumpTicket`.
- **Componentes clave:** `StatusChip` (KDS_STATUS/ITEM_STATUS), `Button`, `DaxCard`.
- **Notas:** `window.prompt()` crudo para crear estación. Sin SLA/timing (solo `age` en minutos). Botón bump sin `aria-label` real. Auto-refresh silencioso (parpadeo). Bug backend conocido: "avanzar comanda" avanza ítems de todas las estaciones.

### `/recipes` — Recetas
- **Archivo:** `pages/recipes/Recipes.tsx` (102 líneas)
- **Propósito:** Lista de recetas (nombre, rinde, nº insumos); crear/editar/borrar. Costea platillos y descuenta insumos automáticamente en cada venta.
- **Quién la ve:** Admin, Dueño, Gerente — módulo `recipes` (los 3 presets). Marcada "beta" en los homes.
- **Datos/API:** `recipesApi.list/remove`.
- **Componentes clave:** `DaxCard`, `confirm()` dialog (buen patrón, no `window.confirm`).
- **Notas:** La más flaca en UX (solo lista). Falta el desglose costo→margen + panel de insumos/merma que el backend ya soporta. Mejor manejada que otras (empty/loading presentes).

### `/recipes/new`, `/recipes/:id/edit` — Formulario de receta
- **Archivo:** `pages/recipes/RecipeForm.tsx` (241 líneas)
- **Propósito:** Alta/edición de receta: platillo (variante), rinde, e ingredientes con cantidad y % merma; muestra costeo/margen.
- **Datos/API:** `recipesApi.get/create/update`, catálogo de variantes.
- **Notas:** **6 inputs con clases oscuras hardcodeadas** (no usan `.dax-input`, sin ring de foco). Botón quitar-fila sin `aria-label`. Margen emerald (semántico OK).

### `/menu` — Menú visual
- **Archivo:** `pages/menu/MenuVisual.tsx` (122 líneas)
- **Propósito:** El catálogo como carta visual agrupada por categoría, con precio; pensado para la barra/mostrador.
- **Quién la ve:** los 3 presets — módulo `menu`. (No expuesto en ningún Home.)
- **Datos/API:** `productsApi.list({is_active:true})`.
- **Notas:** **Rotura de contraste #1 en claro**: chip inactivo `color:'#cbd5e1'` inline (casi invisible). `presetAccent()` via `getComputedStyle` (default `#8b4a2b`, divergente del de Meseros). La card de producto ≈ el tile de ComandaOrder (dup).

### `/meseros` — Ventas por mesero
- **Archivo:** `pages/reports/Meseros.tsx` (160 líneas)
- **Propósito:** Desempeño y propinas por colaborador: KPIs, gráfica y tabla por mesero, con rango Hoy/7d/30d.
- **Quién la ve:** Admin, Dueño, Gerente — módulo `tables`. (No expuesto en ningún Home.)
- **Datos/API:** `reportsApi.byWaiter({start,end,branch_id})`.
- **Componentes clave:** `DaxCard`, `BarChart`. `presetAccent()` via `getComputedStyle` (default `#7c3aed`).
- **Notas:** Tab de rango inactiva `color:'#94a3b8'` inline (bajo contraste en claro). Los 3 estados (loading/empty/error) presentes — modelo a seguir.

### `/bar/bottles` — Botellas (inventario líquido)
- **Archivo:** `pages/bar/Botellas.tsx` (168 líneas)
- **Propósito:** Botellas abiertas con % de volumen; servir (pour), registrar merma y ajustar por conteo físico; resalta las de reponer.
- **Quién la ve:** Admin, Dueño, Gerente, Cajero — módulo `bar` (RESTAURANT y BAR).
- **Datos/API:** `barApi.list/open/pour/waste/refill`.
- **Notas:** **La más cruda.** Dos `window.prompt()` para merma y ajuste (la operación más sensible con el peor input). Botones 100% ad-hoc (no usan `<Button>`), `ACCENT='#7c3aed'` hardcodeado (ignora preset). Backend sin ledger → cortes de turno imposibles.

### `/mobile/comanda` — Comanda (selección de mesa)
- **Archivo:** `pages/mobile/ComandaTables.tsx` (77 líneas)
- **Propósito:** Lista táctil de mesas para que el mesero elija una y tome la orden.
- **Quién la ve:** roles con módulo `tables`, experiencia móvil.
- **Datos/API:** `tablesApi.listTables`.
- **Notas:** Chips `bg-amber-500` (otra variante de chip). `StatusChip dotOnly` con `scale` inline.

### `/mobile/comanda/:tableId` — Comanda (toma de orden)
- **Archivo:** `pages/mobile/ComandaOrder.tsx` (177 líneas)
- **Propósito:** Toma de orden por mesa: menú por categoría, arma "por enviar", dispara a cocina (fire) y persiste en la cuenta; pedir cuenta.
- **Datos/API:** `tablesApi.listTables/setStatus`, `parkedTicketsApi.get/update`, `kitchenApi.fire`, `productsApi.list`.
- **Notas:** **Mejor manejo de error del set** (caso "disparó a cocina pero falló la cuenta" es accionable). Falta enviar modificadores (KDS los soporta). Botones ± y back sin `aria-label`.

---

## 3. POS & Ventas

### `/pos` — Punto de Venta (POS principal)
- **Archivo:** `pages/pos/POS.tsx` (724 líneas)
- **Propósito:** Caja operativa: busca productos, arma carrito, cobra (efectivo/tarjeta/transferencia/mixto), pausa/reanuda tickets, devoluciones, movimientos de efectivo e impresión.
- **Quién la ve:** Cajero, Gerente — módulo `pos`.
- **Datos/API:** `cashApi.getStatus/close`, `salesApi.create/getMyLast`, `parkedTicketsApi.list/park/resume/remove`, `printerApi.*` (agente local), `utils/offlineQueue` (IndexedDB). Store `usePOSStore`.
- **Componentes clave:** `ProductSearch`, `CartPanel`, `PendingOrders`; modales `SessionModal`, `Cash/Card/Transfer/MixedPaymentModal`, `ReturnModal`, `CashMovementModal`, `CloseSessionModal`, `ProductDetailModal`.
- **Notas:** Sin turno de caja abierto → carrito bloqueado. Layout 40/60. Polling de pausados 10s + flush offline 30s. Ítems "caja" se expanden a piezas; descuento global se distribuye al unit_price. Auto-imprime ticket/corte. Toast inline propio (debería usar `toastStore`).

### `/atlas-pos` — Mi día (AtlasPOS)
- **Archivo:** `pages/pos/AtlasPOS.tsx` (173 líneas)
- **Propósito:** Panel de bienvenida del cajero: saludo, reloj, KPIs del día, accesos rápidos y últimas operaciones. Puerta al POS.
- **Quién la ve:** Gerente, Cajero (via `AtlasPOSGate`). Si es usuario de sucursal renderiza `Cockpit`.
- **Datos/API:** `salesApi.list` (hoy, limit 5).
- **Notas:** Errores silenciados; reloj cada 10s. **Gotcha:** hooks tras early-return (`useIsBranchUser` antes del return) — patrón frágil.

### `/printer-settings` — Configuración de impresora
- **Archivo:** `pages/pos/PrinterSettings.tsx` (1200 líneas)
- **Propósito:** Instalar/descargar el agente local por SO, elegir impresora (o Bluetooth BLE), ancho de papel, cajón, logo y editor de ticket con preview realista.
- **Quién la ve:** Cajero, Gerente — módulo `pos`.
- **Datos/API:** `client.get/put('/branches/:id')`, logo `post/delete`, `client.get('/organization/')`, `printerApi.*`, Web Bluetooth API.
- **Componentes clave:** `AgentDiagnosticsPanel`, `PrinterInstallWizard`, `TicketPreview` (interno).
- **Notas:** Tabs por SO con autodetección; banner si el agente está offline. CUPS server-side deprecado (solo agente local). Datos de muestra hardcodeados en el preview.

### `/sales` — Historial de ventas
- **Archivo:** `pages/sales/SalesHistory.tsx` (367 líneas)
- **Propósito:** Ventas por rango con KPIs, detalle de ticket, reimprimir y disparar devoluciones.
- **Quién la ve:** Gerente, Cajero.
- **Datos/API:** `salesApi.list/getStats`, `printerApi.getTicketBase64/printViaAgent`.
- **Notas:** Presets de fecha + paginación (100). Toggle "incluir abiertas" (por defecto solo PAID/REFUNDED/CANCELLED). Devolver solo en PAID. Reimprimir requiere `printerName`. `Promise.allSettled`.

### `/quotes` — Cotizaciones
- **Archivo:** `pages/sales/Quotes.tsx` (181 líneas)
- **Propósito:** Listar cotizaciones con KPIs, ver detalle, convertir a venta (efectivo) o eliminar.
- **Quién la ve:** Admin, Dueño — módulo `quotes`.
- **Datos/API:** `quotesApi.list/getStats/convertToSale/delete`.
- **Notas:** Convertir/eliminar solo en PENDING. Usa `confirm()`/`alert()` nativos.

### `/quotes/new` — Nueva cotización (QuoteMaker)
- **Archivo:** `pages/sales/QuoteMaker.tsx` (265 líneas)
- **Propósito:** Armar cotización: buscar productos, cantidad/descuento por línea, cliente, notas, guardar.
- **Quién la ve:** Admin, Dueño — módulo `quotes`.
- **Datos/API:** `productsApi.search`, `customersApi.search`, `quotesApi.create`.
- **Notas:** Carrito/dropdowns inline (debounce 300ms). **Gotcha:** `notes` se captura pero NO se envía; el payload solo manda `{sku, quantity}`.

### `/returns` — Devoluciones
- **Archivo:** `pages/sales/Returns.tsx` (261 líneas)
- **Propósito:** Bandeja de aprobación: pendientes/historial, detalle (reingreso vs merma), aprobar/rechazar con motivo.
- **Quién la ve:** Gerente, Cajero — módulo `returns`. Si es CAJERO renderiza `ReturnsBranchView`. `CAN_APPROVE`=Admin/Dueño/Gerente.
- **Datos/API:** `returnsApi.list/approve/reject`.
- **Notas:** Regla R-3: reembolso CASH >$10,000 requiere `force=true` (doble confirmación). `serverDetail()` extrae el `detail` de FastAPI. **Gotcha:** hooks tras early-return.

### `/seguimiento` — Pedidos abiertos
- **Archivo:** `pages/sales/Seguimiento.tsx` (124 líneas)
- **Propósito:** Ventas en estado PENDING (crédito/sin cerrar) por sucursal, con detalle.
- **Quién la ve:** Admin, Dueño.
- **Datos/API:** `salesApi.list({status:'PENDING'})`. Solo lectura.

---

## 4. HQ (multisucursal)

> **Solapamiento fuerte:** HQOperations, HQReportsHub y HQControl consumen `reportsApi.commandCenterStats` y repiten el "strip de KPIs del día", métodos de pago (doughnut), ranking de sucursales y top productos, con `PAYMENT_COLORS`/rangos reimplementados en cada archivo. Diferenciadores reales abajo.

### `/hq/operations` — Operaciones (command center)
- **Archivo:** `pages/hq/HQOperations.tsx` (664 líneas)
- **Propósito:** "War room" en vivo: revenue/tickets/métodos, velocidad por hora, estado de cada sucursal, top productos, feed de alertas. Auto-refresh 60s.
- **Quién la ve:** Admin, Dueño — módulo `pos`.
- **Datos/API:** `reportsApi.commandCenterStats/exportCsv`. Alertas leídas en `localStorage`.
- **Componentes clave:** `KPICard`, `Bar`/`Doughnut` (chart.js), `useKeyboardShortcuts` (1/2/3/r).
- **Notas:** Auto-refresh se pausa con `document.hidden`. Errores solo a consola. Tema oscuro fijo. **Diferenciador:** es el "live monitor".

### `/hq/reports-hub` — Reportes HQ (Ultra)
- **Archivo:** `pages/hq/HQReportsHub.tsx` (655 líneas)
- **Propósito:** Suite analítica premium: velocímetro hora actual, gauge de cumplimiento, 6 KPIs, tendencia dual, doughnut de pagos, heatmap día×hora, leaderboard, stock bajo, top con sparklines.
- **Quién la ve:** Admin, Dueño — módulo `pos`.
- **Datos/API:** `reportsApi.dashboard/commandCenterStats/salesByHour`, `organizationApi.getBranches`. `Promise.allSettled`.
- **Notas:** **Único HQ que respeta `useTheme`.** **Gotcha:** dos fallbacks de datos simulados con disclaimer (`buildHeatmapFallback`, `fakeTrend`) — hay TODO para quitarlos. **Diferenciador:** análisis histórico/comparativo.

### `/hq/control` — Control HQ
- **Archivo:** `pages/hq/HQControl.tsx` (205 líneas)
- **Propósito:** Gobierno: KPIs del día, accesos a configuración, auditoría de diferencias de caja y feed de actividad.
- **Quién la ve:** Admin, Dueño — módulo `pos`.
- **Datos/API:** `reportsApi.auditDiscrepancies/commandCenterStats`, `organizationApi.getBranches`, import dinámico `GET /platform/audit/logs`.
- **Notas:** **Diferenciador:** lo exclusivo de gobierno (diferencias de caja, audit log, config). Navegación cruzada con Operations.

### `/hq/sales` — Ventas HQ (log)
- **Archivo:** `pages/hq/HQSalesLog.tsx` (259 líneas)
- **Propósito:** Bitácora consolidada de todas las sucursales: KPIs, filtros fecha/sucursal, búsqueda folio/cliente, paginación, detalle.
- **Quién la ve:** Admin, Dueño — módulo `pos`.
- **Datos/API:** `salesApi.list`, `GET /sales/stats`, `organizationApi.getBranches`.
- **Notas:** Búsqueda de texto filtra en cliente sobre la página actual (no server-side).

### `/hq/returns` — Devoluciones HQ
- **Archivo:** `pages/hq/HQReturns.tsx` (274 líneas)
- **Propósito:** Aprobación de devoluciones multisucursal: pendientes/historial, filtro por sucursal, aprobar/rechazar.
- **Quién la ve:** Admin, Dueño — módulo `returns` (`CAN_APPROVE` incluye Gerente).
- **Datos/API:** `returnsApi.list/approve/reject`, `organizationApi.getBranches`, `toast`.
- **Notas:** Misma regla de reembolso CASH alto con `force`. Única HQ que muta con toasts.

### `/hq/inventory` — Inventario por sucursal
- **Archivo:** `pages/hq/HQInventory.tsx` (224 líneas)
- **Propósito:** Búsqueda global de productos con kardex por variante y ajustes manuales de stock por sucursal.
- **Quién la ve:** **Solo Admin** — módulo `inventory`.
- **Datos/API:** `productsApi.search`, `inventoryApi.getKardex/createAdjustment`, `organizationApi.getBranches`.
- **Notas:** Errores con `alert()`. Búsqueda sin debounce. Casi idéntica a `inventory/Inventory.tsx`.

### `/hq/branches` — Sucursales (grid)
- **Archivo:** `pages/hq/HQBranches.tsx` (121 líneas)
- **Propósito:** Directorio en tarjetas: abierta/cerrada, ventas del día, sesiones abiertas, stock crítico; strip resumen.
- **Quién la ve:** **Solo Admin** — módulo `inventory`.
- **Datos/API:** `organizationApi.getBranches` + `reportsApi.commandCenterStats`.
- **Notas:** **Gotcha semántico:** "online" se deriva de `pending_cuts > 0`, no de `status === 'ONLINE'` como en Operations (mismo dato, criterio distinto).

### `/hq/branches/:branchId` — Detalle de sucursal
- **Archivo:** `pages/hq/HQBranchDetail.tsx` (224 líneas)
- **Propósito:** Ficha individual: KPIs del día, contacto, top productos, stock bajo, últimas transacciones.
- **Quién la ve:** Admin, Dueño — módulo `pos`.
- **Datos/API:** `client.get('/branches/')` (busca por id en el array) + `GET /reports/dashboard`.
- **Notas:** **Único con estado de error visible completo** (+ "Sucursal no encontrada"). **Gotcha:** trae todas las sucursales para encontrar una (ineficiente).

---

## 5. Inventario, Productos & Catálogo

> **4 superficies para crear/editar producto, migración a medias.** `ProductForm` = fuente de verdad canónica (create/edit por rol). `AdminProductCreate` = variante admin-create. `ProductModal` embebido en `Products.tsx` = editor completo legacy (empaques + precios escalonados) que aún usan admins. `AdminCatalog` no edita campos: delega a `/products?edit=:id`. Comentarios "A3+ migrará…" confirman consolidación futura.

### `/products` — Catálogo / consulta de productos
- **Archivo:** `pages/inventory/Products.tsx` (1500 líneas)
- **Propósito:** Vista central del catálogo: buscar/filtrar, lista o grid, crear/editar, importar Excel/CSV, y (roles sucursal) ajustar precio/stock/flags por sucursal.
- **Quién la ve:** Admin, Dueño, Gerente, Cajero — módulo `catalog`. UI bifurca por rol (HQ ve matriz global; sucursal ve `ProductsBranchView`).
- **Datos/API:** `productsApi.list/search/getById/create/update/getDepartments/getBrands/uploadProducts/downloadTemplate/updateBranchStatus`.
- **Componentes clave:** `ImportModal`, `ProductModal`, `BranchStatusEditor`, `ProductImageUploader`.
- **Notas:** **Dos rutas de edición por rol:** Gerente/Cajero → `/products/:id/edit` (ProductForm); Admin/Dueño → ProductModal inline. Refetch por `location.key`.

### `/inventory` — Inventario (kardex y ajustes)
- **Archivo:** `pages/inventory/Inventory.tsx` (193 líneas)
- **Propósito:** Buscar producto → kardex (historial de movimientos) + ajustes manuales por sucursal.
- **Quién la ve:** módulo `inventory`.
- **Datos/API:** `productsApi.search`, `inventoryApi.getKardex/createAdjustment`, `organizationApi.getBranches`.
- **Notas:** **Gotcha:** la API espera variant UUID (`p.variants?.[0]?.id ?? p.id`). Casi idéntica a `HQInventory` (candidata a unificar).

### `/logistics` — Logística / transferencias
- **Archivo:** `pages/inventory/Logistics.tsx` (270 líneas)
- **Propósito:** Listar y crear solicitudes de transferencia de inventario entre sucursales.
- **Quién la ve:** módulo `logistics`.
- **Datos/API:** `client.get/post('/transfers/')`, `organizationApi.getBranches`, `productsApi.search`.
- **Notas:** Estados DRAFT/REQUESTED/PARTIALLY_FULFILLED/COMPLETED/CANCELLED. Solo lista + creación (sin detalle ni cambio de estado).

### `/boxes` — Cajas y contenedores
- **Archivo:** `pages/inventory/Boxes.tsx` (300 líneas)
- **Propósito:** Catálogo de tipos de contenedor (dim. internas) y de caja (dim. externas) para empaque/logística.
- **Quién la ve:** módulo `logistics`.
- **Datos/API:** `client.get/post('/logistics/containers' | '/logistics/boxes')`.
- **Notas:** 2 tabs; solo crear + listar. Contenedores `inner_*`, cajas `outer_*`.

### `/products/new`, `/products/:id/edit` — Formulario de producto
- **Archivo:** `pages/products/ProductForm.tsx` (447 líneas)
- **Propósito:** Formulario de página completa para crear/editar. Destino de Gerente/Cajero desde `/products`.
- **Quién la ve:** `RequireRole(Admin, Dueño, Gerente, Cajero)`.
- **Datos/API:** `productsApi.getById/create/update/getDepartments/getBrands`, `organizationApi.getBranches` (admin).
- **Componentes clave:** secciones `ProductBasicsSection`, `ProductCommercialSection`, `ProductTieredPricesSection`, `ProductBranchMatrixSection`, `ProductInitialStockSection`.
- **Notas:** Admin en create ve matriz + stock inicial; cajero tiene sucursal bloqueada. En edit no toca matriz/stock. Maneja 409/SKU duplicado. **`products/new` monta `<ProductForm key="new" />` y `products/:id/edit` monta un wrapper `ProductFormEditRoute` con `<ProductForm key={id} />`** (`App.tsx:44-50`) — fix 2026-09-22: sin el `key`, React Router reutilizaba la instancia y "Nuevo producto" heredaba los datos del producto que se estaba editando (auditoría #3, `docs/AUDITORIA-2026-09-22.md`).

### `/admin/catalog` — Catálogo (administración)
- **Archivo:** `pages/core/AdminCatalog.tsx` (534 líneas)
- **Propósito:** Panel avanzado: KPIs, filtros por aprobación, ciclo de vida (aprobar/rechazar/archivar/restaurar/duplicar), matriz de sucursales, auditoría.
- **Quién la ve:** Admin — módulo `catalog`.
- **Datos/API:** `productsApi.list/catalogKpis/duplicate/approve/reject/restore/getDepartments/getBrands`, `client.delete('/products/:id')`.
- **Componentes clave:** `CatalogKpis`, `ProductBranchMatrix`, `ProductAuditDrawer`.
- **Notas:** **No edita campos aquí:** "Nuevo"→AdminProductCreate, "Editar"→`/products?edit=:id`.

### `/admin/products/new` — Nuevo producto (administración)
- **Archivo:** `pages/admin/AdminProductCreate.tsx` (290 líneas)
- **Propósito:** Creación de producto del flujo administrativo (siempre matriz completa, exige ≥1 sucursal). Vuelve a `/admin/catalog`.
- **Quién la ve:** `RequireRole(Admin, Dueño, Gerente, Cajero)`.
- **Datos/API:** `productsApi.getDepartments/getBrands/create`, `organizationApi.getBranches`.
- **Notas:** Subconjunto "create + admin" de `ProductForm` (mismas secciones). Fix
  2026-09-22: el payload ya manda `gender`/`model`/`material` (antes se capturaban en
  el formulario y se perdían al enviar — auditoría #9). Sigue **sin** botón "Sugerir
  SKU" a diferencia de `ProductForm` (auditoría #25, abierto).

### `/departments` — Departamentos
- **Archivo:** `pages/core/Departments.tsx` (112 líneas)
- **Propósito:** CRUD de departamentos (categorías). **Quién la ve:** Admin — módulo `catalog`, `hideForGastro`.
- **Datos/API:** `productsApi.get/create/update/deleteDepartment`. `confirm()`/`alert()`.
- **Notas:** Fix 2026-09-22 (`api/products.ts`): editar/borrar devolvía 405 siempre
  (barra final en la URL que el backend no registra) — auditoría #7, mismo fix que
  `/brands`.

### `/brands` — Marcas
- **Archivo:** `pages/core/Brands.tsx` (143 líneas)
- **Propósito:** CRUD de marcas con logo opcional + búsqueda en cliente. **Quién la ve:** Admin — módulo `catalog`, `hideForGastro`.
- **Datos/API:** `productsApi.get/create/update/deleteBrand`.
- **Notas:** Fix 2026-09-22 (`api/products.ts`): editar/borrar devolvía 405 siempre —
  ver nota en `/departments` arriba (auditoría #7). Relevante para boutique: es donde
  se cargan las marcas del catálogo (`docs/presets/BOUTIQUE.md §6`).

---

## 6. Finanzas, CRM, RRHH, Portal & Core-admin

### `/cash-history` — Control de caja
- **Archivo:** `pages/finance/CashHistory.tsx` (356 líneas)
- **Propósito:** Turno abierto: entradas/salidas manuales, KPIs por método, cerrar/arquear e imprimir/descargar cortes históricos.
- **Quién la ve:** Gerente, Cajero — módulo `cash_management`. Usuario de sucursal → `CashBranchView`.
- **Datos/API:** `cashApi.getStatus/getSummary/history/inflow/outflow/close/getPdf`, `printerApi.getCashCutBase64/printViaAgent`.
- **Componentes clave:** `MovementModal`, `CloseModal` (esperado vs contado).
- **Notas:** "Corte Parcial" deshabilitado (sin handler). **Gotcha:** hooks tras early-return.

### `/expenses` — Gastos
- **Archivo:** `pages/finance/Expenses.tsx` (214 líneas)
- **Propósito:** Registrar/consultar gastos con KPIs (mes/semana/prom. diario) y desglose por categoría.
- **Quién la ve:** Admin, Dueño — módulo `payments`.
- **Datos/API:** `expensesApi.list/getStats/getCategories/create/delete`. `alert()`/`confirm()`.

### `/purchases` — Órdenes de compra
- **Archivo:** `pages/finance/Purchases.tsx` (281 líneas)
- **Propósito:** Crear y dar seguimiento a OC (borrador→enviada→parcial/recibida→cancelada) + recepción (impacta inventario).
- **Quién la ve:** Admin, Dueño — módulo `payments`.
- **Datos/API:** `purchasesApi.list/getStats/create/updateStatus/getById/receive`.

### `/reports` — Reportes
- **Archivo:** `pages/finance/Reports.tsx` (219 líneas)
- **Propósito:** Dashboard de ventas por rango: KPIs, ventas por hora, métodos, top productos, ventas recientes.
- **Quién la ve:** Gerente.
- **Datos/API:** `reportsApi.dashboard`.
- **Notas:** **Consciente del tema** (`useTheme` para la gráfica). Chart.js.

### `/customers` — Clientes
- **Archivo:** `pages/crm/Customers.tsx` (236 líneas)
- **Propósito:** Directorio con crédito/cuenta corriente: lista buscable con saldo, estado de cuenta (ledger) y registro de abonos.
- **Quién la ve:** Admin, Dueño — módulo `crm`.
- **Datos/API:** `customersApi.getAll/getStats/getStatement/pay`.
- **Notas:** Búsqueda debounce 400ms. Botón pago solo si `current_balance < 0` (deuda).

### `/hr` — Recursos Humanos
- **Archivo:** `pages/hr/HR.tsx` (202 líneas)
- **Propósito:** Alta/edición de empleados (nombre, tipo, sucursal base, ingreso, contacto).
- **Quién la ve:** Admin.
- **Datos/API:** `hrApi.getAll/create/update`, `organizationApi.getBranches`. Búsqueda en cliente.

### `/hr/me` — Mi expediente
- **Archivo:** `pages/hr/HRMe.tsx` (181 líneas)
- **Propósito:** Autoservicio del empleado: consulta su expediente y edita datos personales (identificadores oficiales solo lectura).
- **Quién la ve:** todos los autenticados con expediente.
- **Datos/API:** `hrApi.getMe/updateMe`.
- **Notas:** **Error + success banner completos** (raro en la app). **Gotcha:** "Sin sucursal asignada" hardcodeado.

### `/portal` — Mi portal (cliente externo)
- **Archivo:** `pages/portal/Portal.tsx` (258 líneas)
- **Propósito:** **Portal de cara al cliente externo** (no empleado): estado de cuenta consolidado a través de varias organizaciones vinculadas — saldo, cuentas, movimientos, cotizaciones.
- **Quién la ve:** rol CLIENTE (contexto multi-organización).
- **Datos/API:** `portalApi.getAccounts/getBalance/getTransactions/getQuotes` (`Promise.allSettled`).
- **Notas:** La vista más distinta: orientada a cliente final, no a operación interna.

### `/users` — Usuarios
- **Archivo:** `pages/core/Users.tsx` (193 líneas)
- **Propósito:** Cuentas del sistema: alta/edición, rol, sucursal, activar/desactivar, cambiar contraseña.
- **Quién la ve:** Admin.
- **Datos/API:** `usersApi.getAll/create/update`, `organizationApi.getBranches`.
- **Notas:** Username no editable en edición. Sucursal vacía = "HQ / Global". Errores muestran el detalle real del backend.

### `/organization` — Empresa y sucursales
- **Archivo:** `pages/core/Organization.tsx` (631 líneas — creció por USD/comisión de tarjeta/ticket boutique, ver `docs/presets/BOUTIQUE.md §3.4`)
- **Propósito:** Config de empresa (datos fiscales, logo, header/footer de ticket) + CRUD de sucursales.
- **Quién la ve:** Admin.
- **Datos/API:** `organizationApi.getOrg/updateOrg/getBranches/createBranch/updateBranch/deleteBranch`, logo via `client`.
- **Notas:** 2 tabs. Validación de logo (PNG/JPEG/WEBP ≤1MB). HQ no se elimina.
  Header/footer se imprimen en el POS. Fixes 2026-09-22: guardar/borrar sucursal ahora
  muestra el motivo real del backend en vez de un mensaje genérico (auditoría #16); no
  se puede dejar "Razón social" vacía y guardar — antes ponía `organization.name` en
  `NULL` silenciosamente (auditoría #17, los 4 botones que comparten `saveOrg` se
  deshabilitan si el campo está vacío).

### `/startup` — Onboarding (asistente inicial)
- **Archivo:** `pages/core/Startup.tsx` (271 líneas)
- **Propósito:** **Bootstrap del tenant:** asistente cinemático donde se elige un preset de industria que inicializa los módulos de la org.
- **Quién la ve:** Admin (primera configuración).
- **Datos/API:** `platformApi.getPresets`, `client.post('/setup/initialize', {industry_type})` → redirige.
- **Notas:** **No usa el layout/tema estándar** (full-screen custom, `startup.css`). `FALLBACK_PRESETS` si el endpoint falla.

---

## 7. Móvil (vendedor de campo)

> Vistas de vendedor (dashboard/query/sales/profile) son dark-only; `MobileOwnerDashboard` es la excepción con tema claro. Comanda* están en §2 Gastro.

### `/mobile/dashboard` — Dashboard móvil (vendedor)
- **Archivo:** `pages/mobile/MobileDashboard.tsx` (106 líneas)
- **Propósito:** Inicio del vendedor: saludo, resumen de ventas de hoy, accesos rápidos.
- **Quién la ve:** Vendedor (y Soporte por el ruteo de login).
- **Datos/API:** `reportsApi.dailySummary(hoy)`. Errores silenciados. Reloj 60s.

### `/mobile/owner` — Dashboard móvil (dueño)
- **Archivo:** `pages/mobile/MobileOwnerDashboard.tsx` (155 líneas)
- **Propósito:** Vistazo de solo lectura del dueño: KPIs, top productos, ventas recientes.
- **Quién la ve:** Dueño, Admin.
- **Datos/API:** `reportsApi.dashboard`. Fallback: si hoy=0 reconsulta 7 días.
- **Notas:** **Soporta tema claro/oscuro.** Footer "vista de solo lectura".

### `/mobile/profile` — Mi perfil móvil
- **Archivo:** `pages/mobile/MobileProfile.tsx` (156 líneas)
- **Propósito:** Perfil del empleado en móvil; edita teléfono y email personal.
- **Quién la ve:** Vendedor (única vista móvil con escritura).
- **Datos/API:** `hrApi.getMe/updateMe`. Estado `noProfile` si falla getMe.

### `/mobile/query` — Consulta móvil
- **Archivo:** `pages/mobile/MobileQuery.tsx` (148 líneas)
- **Propósito:** Buscador de productos en piso (nombre/SKU/código): precio, stock, precios por volumen.
- **Quién la ve:** Vendedor.
- **Datos/API:** `productsApi.search`. Debounce 350ms. Solo lectura.

### `/mobile/sales` — Cotización móvil
- **Archivo:** `pages/mobile/MobileSales.tsx` (243 líneas)
- **Propósito:** Armar cotización desde el móvil: productos, carrito, cliente opcional, genera folio.
- **Quién la ve:** Vendedor.
- **Datos/API:** `productsApi.search`, `customersApi.search`, `quotesApi.create`.
- **Notas:** Pantalla de éxito con folio. **Gotcha:** `notes` capturado pero no enviado.

---

## 8. Platform — núcleo (super-admin SaaS)

> Todo bajo `/platform/*`, gate SUPERADMIN, dentro de `PlatformLayout`, tema `platform-v2.css` (`--p-*`). Dos generaciones conviven: **v2 "Editorial"** (Metrics/Health, `components/platform/v2/*`) y **v1 "PageShell"** (el resto: `PlatformPageShell` + `DataTable` + `SideDrawer` + `ConfirmModal`).

### `/platform` — Layout del panel
- **Archivo:** `pages/platform/PlatformLayout.tsx` (165 líneas)
- **Propósito:** Cascarón: sidebar (grupos **Platform** y **Admin**), buscador `⌘K` (`CommandPalette`), `ImpersonationBanner`, `Outlet`.
- **Datos/API:** solo `useAuthStore`. "Salir al App" → `/hq/operations`.

### `/platform/metrics` — Métricas globales (dashboard)
- **Archivo:** `pages/platform/PlatformMetrics.tsx` (570 líneas) — **ruta índice.**
- **Propósito:** Dashboard cross-tenant: KPIs, tendencias, mix de pago, comparativa de sucursales, heatmap, leaderboards.
- **Datos/API:** `platformApi.kpisExtended/trendsMulti/topTenants/topBranches/topProducts/paymentMethods/branchComparison/activityHeatmap` (`Promise.allSettled`); `cohortRetention` lazy.
- **Componentes clave:** `KPICardV2`, `TrendChart`, `ActivityHeatmap`, `Leaderboard`, `BranchComparisonTable`, `CohortTable` (Suspense). Tema v2.

### `/platform/health` — Health matrix
- **Archivo:** `pages/platform/PlatformHealth.tsx` (367 líneas)
- **Propósito:** Salud por tenant: score 0-100, última venta, ventas 7d, revenue 30d, módulos, estado.
- **Datos/API:** `platformApi.healthMatrix()`. `DataTable` + CSV. Verde ≥70 / ámbar ≥40 / rojo <40. Tema v2.

### `/platform/organizations` — Organizaciones
- **Archivo:** `pages/platform/PlatformOrganizations.tsx` (996 líneas)
- **Propósito:** CRUD/ciclo de vida de tenants: crear (con preset), editar, archivar, exportar, bootstrap, eliminar (protegido por deps).
- **Datos/API:** `getOrgs/createOrg/updateOrg/archiveOrg/unarchiveOrg/deleteOrg/exportOrg/bootstrapOrg/getOrgDependencies/getPresets`.
- **Componentes clave:** `PlatformPageShell`, `DataTable`, `RowMenu`, `SideDrawer`, `PlatformOrgWizard` (`?new=1`), `ConfirmModal` typed-name. Tema v1.

### `/platform/organizations/:orgId` — Detalle de organización
- **Archivo:** `pages/platform/PlatformOrgDetail.tsx` (1317 líneas)
- **Propósito:** Vista 360: editar, gestionar módulos (toggle), upsell, aplicar/resetear preset, sucursales/usuarios (tabs), impersonar, zona peligrosa.
- **Datos/API:** carga paralela `getOrg/getOrgModules/getUsers/getBranches/getPresets/getModulesCatalog/getUpsellRecommendations`; acciones `toggleModule/updateOrg/setIndustry/applyPreset/resetPreset/archiveOrg/deleteOrg/impersonate`. `useImpersonationStore`.
- **Notas:** Toggle de módulos optimista con rollback. Impersonación registra en AuditLog → `/hq/operations`. "Reset config" es placeholder sin backend. Tema v1.

### `/platform/users` — Usuarios cross-tenant
- **Archivo:** `pages/platform/PlatformUsers.tsx` (910 líneas)
- **Propósito:** Usuarios de todas las orgs: crear/editar, reset password (temporal), cambio de rol, soft-delete.
- **Datos/API:** `getUsers/getOrgs/getBranches` + `createUser/updateUser/resetUserPassword/changeUserRole/deleteUser`.
- **Notas:** SUPPORT ve tabla con email enmascarado y acciones deshabilitadas. Delete = soft. Tema v1.

### `/platform/branches` — Sucursales cross-org
- **Archivo:** `pages/platform/PlatformBranches.tsx` (1086 líneas)
- **Propósito:** Sucursales de todas las orgs: crear/editar (datos + dirección + impresora/tickets), archivar, eliminar (cascade opcional), panel de alertas.
- **Datos/API:** `getBranches/getOrgs/createBranch/updateBranch/archiveBranch/unarchiveBranch/deleteBranch/getBranchDependencies`.
- **Notas:** Varios `TODO(backend)` (sesiones live, endpoint de alertas). Tema v1.

### `/platform/admins` — Administradores de plataforma
- **Archivo:** `pages/platform/PlatformAdmins.tsx` (1136 líneas)
- **Propósito:** Los propios admins: invitar (password temporal), crear manual, cambiar rol (SUPERADMIN/SUPPORT/NONE), revocar, audit trail por admin.
- **Quién la ve:** SUPERADMIN estricto — SUPPORT recibe panel 403.
- **Datos/API:** `listPlatformAdmins/invitePlatformAdmin/createPlatformAdminManual/changePlatformAdminRole/revokePlatformAdmin/getAuditLogs`.
- **Notas:** No permite auto-revocación. Password temporal no se re-muestra. Tema v1.

### `/platform/modules` — Catálogo de módulos
- **Archivo:** `pages/platform/PlatformModules.tsx` (981 líneas)
- **Propósito:** Catálogo global de módulos: crear/editar (key inmutable, scope, BETA/STABLE), dependencias (presets + orgs), eliminar (solo si ninguna org lo usa).
- **Datos/API:** `getModulesCatalog/getModulesCounts/getModuleDependencies/createModule/updateModule/deleteModule`.
- **Notas:** Counts iniciales agregados; detalle se hidrata al abrir panel. Eliminar bloqueado si `orgs>0`. Tema v1.

### `/platform/presets` — Industry presets
- **Archivo:** `pages/platform/PlatformPresets.tsx` (982 líneas)
- **Propósito:** Presets de industria (`industry_type` + set de módulos): crear, editar, duplicar, eliminar; system presets protegidos.
- **Datos/API:** `getPresets/getModulesCatalog/getOrgs` + `createPreset/updatePreset/deletePreset`.
- **Componentes clave:** grid de cards (no DataTable), multi-select de módulos con preview, warning typed-name para editar system preset (lista orgs afectadas). Tema v1.

---

## 9. Platform — operaciones / observabilidad

### `/platform/alerts` — Alertas
- **Archivo:** `pages/platform/PlatformAlerts.tsx` (777 líneas)
- **Propósito:** Anomalías (caída de ingresos, orgs sin ventas 24h, churn): escanear, ack, resolver.
- **Datos/API:** `alertsApi.listAlerts/alertCounts/scanAlerts/ackAlert/resolveAlert`. `KPICardV2`, filtros por severidad/tipo. Optimista.

### `/platform/reportes` — Reportes
- **Archivo:** `pages/platform/PlatformReports.tsx` (797 líneas)
- **Propósito:** Análisis cross-tenant: top productos/sucursales/vendedores/clientes por revenue, drill-down, CSV.
- **Datos/API:** `reportApi.getProducts/getBranches/getSellers/getCustomers` + `export*Csv`. Filtros en URL (`useSearchParams`).
- **Componentes clave:** `PlatformPageShell`, `ReportFilterBar`, `ReportDrillDownDrawer`, `TopChart` (Recharts), `useReportFetch` (timeout 15s).

### `/platform/announcements` — Comunicados
- **Archivo:** `pages/platform/PlatformAnnouncements.tsx` (915 líneas)
- **Propósito:** Banners/comunicados a tenants con targeting (industria/plan/orgs), Markdown, drafts, publicar.
- **Datos/API:** `announcementsApi.list/create/update/publish/unpublish/remove`, `platformApi.getPresets`.
- **Notas:** Renderer Markdown propio XSS-safe. Targeting vacío = universal.

### `/platform/flags` — Feature flags
- **Archivo:** `pages/platform/PlatformFlags.tsx` (1130 líneas)
- **Propósito:** Catálogo de flags con rollout % determinístico (hash org+key), overrides por org, kill-switch, preview de resolución.
- **Datos/API:** `flagsApi.list/create/update/remove/listOverrides/upsertOverride/removeOverride/preview`, `platformApi.getOrgs`.
- **Notas:** Kill-switch fuerza off e ignora overrides. Borrar flag gated a SUPERADMIN. Key `^[a-z][a-z0-9_]*$`.

### `/platform/incidents` — Incident mode
- **Archivo:** `pages/platform/PlatformIncidents.tsx` (1027 líneas)
- **Propósito:** Kill-switch temporal que suspende masivamente orgs (por industria/plan/orgs/todas), reversible por snapshot.
- **Datos/API:** `incidentsApi.list/create/resolve`, `platformApi.getPresets/getOrgs`.
- **Notas:** Scope "all" con warning; >100 orgs requiere `force`. Doble confirmación. Resolver restaura estado previo.

### `/platform/api-keys` — API keys
- **Archivo:** `pages/platform/PlatformApiKeys.tsx` (904 líneas)
- **Propósito:** Tokens server-to-server por org: crear (reveal único), listar, revocar.
- **Datos/API:** `apiKeysApi.list/create/revoke`, `platformApi.getOrgs`.
- **Notas:** Secreto se muestra UNA vez (solo se guarda hash SHA-256); cerrar deshabilitado hasta copiar. Scopes informativos por ahora.

### `/platform/audit` — Audit log
- **Archivo:** `pages/platform/PlatformAuditLog.tsx` (765 líneas)
- **Propósito:** Bitácora cross-tenant de acciones admin, timeline inverso agrupado por día, filtros, payload expandible.
- **Datos/API:** `platformApi.getAuditLogs`, `getUsers` (resolver actores). Acción/actor en cliente.
- **Notas:** IMPERSONATE resaltado (`--p-magenta`). "Cargar más" paginación client-side. Solo lectura.

### `/platform/cash-audit`, `/:sessionId` — Cash audit
- **Archivo:** `pages/platform/PlatformCashAudit.tsx` (219 líneas)
- **Propósito:** Forense de una sesión de caja: desglose esperado vs reportado vs diferencia + timeline de eventos.
- **Datos/API:** `cashAuditApi.getAuditLog/getSummary` (no `platformApi`).
- **Notas:** Timeline vacío = sesión anterior a F3. **Gotcha:** auto-load con `useState(() => …)` initializer.

### `/mobile/platform` — Monitor móvil de plataforma
- **Archivo:** `pages/platform/MobilePlatformMonitor.tsx` (78 líneas)
- **Propósito:** Lista móvil de solo lectura de orgs con métricas resumidas.
- **Datos/API:** `client.get('/platform/organizations')` directo. **Tailwind** (no `platform-v2.css`).

### `/mobile/platform/org/:orgId` — Detalle móvil de organización
- **Archivo:** `pages/platform/MobileOrgDetail.tsx` (71 líneas)
- **Propósito:** Detalle móvil de solo lectura de una org (sucursales, usuarios, ventas de hoy).
- **Datos/API:** `client.get('/platform/organizations/:orgId')` directo. Tailwind. Hija de MobilePlatformMonitor.

---

## Anexo — Entrada, dev & stubs

### `/login` — Login (Atlas One)
- **Archivo:** `pages/Login.tsx` (349 líneas) — público. Branding animado (cortina, partículas canvas, dial, typewriter).
- **Datos/API:** `authApi.login` → `authStore.setAuth/setBranch`. Ruteo por rol/preset tras login (ver §1). Botones sociales aún no cableados (TODO OAuth).

### `*` — NotFound
- **Archivo:** `pages/NotFound.tsx` (15 líneas). 404 estático con botón a `/`.

### `/__dev__/atlas-one-preview` — Preview del design system
- **Archivo:** `pages/__dev__/AtlasOnePreview.tsx` (271 líneas). Solo dev. Renderiza todas las primitivas de `components/atlas-one` e itera por los 11 presets. Datos demo hardcodeados; único con `export default`.

### `/appointments`, `/commissions`, `/memberships`, `/ai`, `/purchasing` — "Próximamente"
- **Archivo:** `pages/coming-soon/index.tsx` (98 líneas). Un `ComingSoon` parametrizado por `ComingSoonMeta`; exporta un wrapper por módulo (Appointments/Commissions/Memberships/AI/Purchasing/Recipes). Estático, categoría por línea de producto.

---

## 10. Hallazgos transversales (para antes de refactorizar)

1. **Dashboards HQ duplicados.** HQOperations / HQReportsHub / HQControl repiten KPIs-del-día, doughnut de métodos, ranking de sucursales y top productos desde `commandCenterStats`, con `PAYMENT_COLORS`/rangos reimplementados en cada archivo (y colores divergentes: CARD `#0ea5e9` vs `#6366f1`). Además el concepto "sucursal online" difiere (`status==='ONLINE'` vs `pending_cuts>0`).

2. **4 superficies de producto, migración a medias.** `ProductForm` (canónico) · `AdminProductCreate` (admin-create) · `ProductModal` en `Products.tsx` (editor legacy completo) · `AdminCatalog` (delega a `/products?edit=`). Comentarios "A3+ migrará…" apuntan a consolidar en AdminCatalog.

3. **Dos generaciones de UI en Platform.** v2 "Editorial" (Metrics/Health, `KPICardV2`, `SkeletonState`) vs v1 "PageShell" (el resto). Las Mobile* de platform son un tercer mundo (Tailwind + axios directo).

4. **Dos sistemas de tokens en Home.** `PresetHome` (`--p-*` inline) vs `GastroHomeDay` y el resto (`--dax-*` + Tailwind). `Startup` es full-screen custom aparte.

5. **Manejo de errores inconsistente.** Muchas vistas usan `alert()`/`confirm()` nativos y toasts inline propios (POS, PrinterSettings) en vez de `toastStore`. Solo HRMe y HQBranchDetail tienen estados de error/success completos.

6. **Componentes repetidos por extraer** (candidatos): `<PageHeader>` (~3 patrones), `<KpiCard>/<KpiGrid>` (copiado literal en varias), `<SegmentedControl>/<FilterChips>` (4 variantes de chip), `<DocumentDetailModal>`/`<LineItemsTable>` (SalesHistory/Quotes/Returns/Seguimiento/HQSalesLog), `<SalesTable>`, `<ProductTile>` (MenuVisual ≈ ComandaOrder), `useAccent()` (3 métodos con defaults divergentes), `<AsyncState>`/`<PageSkeleton>` (elimina el layout-shift del Spinner full-screen), `useReprintTicket()`.

7. **`window.prompt()`/`alert()` crudos** en operaciones sensibles: Botellas (merma/ajuste por conteo), KDS (crear estación). Recipes ya demuestra el patrón correcto con `confirm()` dialog.

8. **Gotcha de reglas de hooks:** varias vistas declaran hooks tras un `return` condicional (AtlasPOS, Returns, CashHistory, Products via `useIsBranchUser`). Funciona porque la rama es estable, pero es frágil.

9. **`notes` no se envía** en QuoteMaker y MobileSales (se captura en UI pero el payload lo omite).
</content>
</invoke>
