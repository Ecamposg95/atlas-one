# Vista del administrador: precisión, Inicio con gráficas y fusiones — diseño

**Fecha:** 2026-10-23 · **Estado:** aprobado en charla, pendiente de revisión del spec ·
**Caso guía:** Eleven Fashion (org 17, una sucursal, ULTRA+) y las orgs FREE de una sucursal
(Kaory, Coqueta, Imaltzin). **Quién lo usa:** ADMINISTRADOR y DUEÑO en escritorio; cajera y
gerente heredan las pantallas fusionadas.

## 1. Problema

El administrador entra y ve módulos que repiten lo mismo con otro nombre, y cifras que no
coinciden entre pantallas. Auditoría del 2026-10-23 (capturas con Playwright a 1440 sobre una
base de demo con 70 ventas repartidas en 30 días):

**Pantallas duplicadas** (mismos endpoints, distinta pantalla):

| Concepto | Pantalla A | Pantalla B | Diferencia real |
|---|---|---|---|
| Ventas | `/sales` Mis ventas (`pages/sales/SalesHistory.tsx`) | `/hq/sales` Ventas (`pages/hq/HQSalesLog.tsx`) | A: estado, reimprimir, devolver. B: filtro de sucursal |
| Devoluciones | `/returns` (`pages/sales/Returns.tsx`) | `/hq/returns` (`pages/hq/HQReturns.tsx`) | B: filtro de sucursal |
| Inventario | `/inventory` (`pages/inventory/Inventory.tsx`) | `/hq/inventory` Existencias (`pages/hq/HQInventory.tsx`) | B: costo, importe, "solo sin costo" |
| Productos | `/products` (`pages/inventory/Products.tsx`) | `/admin/catalog` Catálogo (`pages/core/AdminCatalog.tsx`) | A: importar, etiquetas, códigos. B: cifras, aprobación, duplicar, archivar |
| Reportes | `/hq/reports-hub` (`HQReportsHub.tsx`) | `/reports` cajera (`finance/Reports.tsx`), detalle de `/hq/branches`, `GastroHomeDay` | Cuatro vistas de `/reports/dashboard` |

El menú del admin (`HQ_NAV_GROUPS`) muestra "Mi tienda" (Mis ventas, Productos, Etiquetas,
Impresora) y además Ventas, Catálogo e Inventario: ahí nace la sensación de duplicado.

**Cifras imprecisas** (todas en producción):

1. La tendencia diaria de `/reports/dashboard` agrupa por día UTC
   (`app/routers/reports.py:376`) mientras los filtros usan día de México: las ventas después
   de las 18:00 caen al día siguiente y las del último día del rango desaparecen. La serie del
   periodo anterior sí usa día de México, así que la comparación está sesgada.
2. Cuatro definiciones de "venta": `/reports/inicio` y `/reports/daily-summary` cuentan
   PAID + REFUNDED_PARTIAL + REFUNDED_TOTAL a importe bruto; `/reports/dashboard`,
   `/reports/sales-by-hour` y `/reports/command-center/stats` solo PAID (una venta con
   devolución parcial desaparece entera); `/sales/stats` todo menos CANCELLED (suma PENDING y
   DRAFT). Ninguna resta devoluciones. "Ventas hoy" da tres números distintos.
3. "Todas las sucursales" del hub manda `branch_id` vacío y `/reports/dashboard` lo convierte
   en "la sucursal del admin" (`reports.py:328-338`); el centro de mando, al lado, sí es global.
4. El efectivo del dashboard no resta el cambio entregado; `daily-summary` y el corte sí.
5. La distribución por hora descarta lo vendido fuera de 8 a 21 h (`reports.py:401`).
6. "Semana" del hub son 8 días (`daysAgoStr(7)` a hoy) y "Mes" 31; `Reports.tsx` usa 6 o 7.
7. `/returns/` compara fechas como texto contra UTC (`app/routers/returns.py:163-174`) y sin
   filtro devuelve las 50 más recientes.

**Bugs de paso:** `@router.post("")` quedó pegado a `_line_description` en
`app/routers/sales.py:368`, así que `POST /api/sales` sin barra final responde 422 (el POS usa
la barra). `app/main.py:328` redirige `/hq/sales` a `/hq/sales-log`, ruta que ya no existe: abrir
Ventas por URL o con F5 muestra "Página no encontrada".

**Estilo:** conviven tres lenguajes (Inicio plano en texto, hub "premium" con degradados,
velocímetros y conteo animado, Reportes de cajera con tarjetas simples). El modo claro se logra
sobrescribiendo con `!important` cada clase oscura de Tailwind (`index.css:339-437`) porque las
pantallas traen `text-white` y `slate-*` fijos.

Decisiones tomadas con el usuario el 2026-10-23:

| Pregunta | Decisión |
|---|---|
| Fusiones | Las cuatro: Ventas, Devoluciones, Inventario, Productos |
| Inicio | Inicio = hoy con gráficas; Reportes = periodos y comparativos |
| Regla de venta | Pagadas menos devoluciones aprobadas, día de México, en todos los indicadores |
| Estilo | Limpio y plano con el kit actual, colores por tokens; sin `!important` nuevos |
| Gráficas del Inicio | Tendencia 7 días (línea), ventas por hora (barras), métodos (dona), sucursales (barras horizontales) |
| URLs que sobreviven | Las cortas: `/sales`, `/returns`, `/inventory`, `/products`; las viejas redirigen |
| Enfoque | Tres fases encadenadas, una rama y un despliegue por fase |

## 2. Fase 1 · Precisión (backend)

### 2.1 Servicio único: `app/services/metricas_ventas.py`

Funciones puras sobre una `Session`; ningún router vuelve a escribir el criterio a mano.

```python
@dataclass(frozen=True)
class Periodo:
    inicio: date   # día de México, inclusive
    fin: date      # día de México, inclusive
    def anterior(self) -> "Periodo": ...   # mismo largo, termina el día antes de `inicio`

@dataclass(frozen=True)
class Ambito:
    organization_id: int
    branch_id: int | None     # None = toda la organización

def resolver_ambito(current_user, org_id, branch_id) -> Ambito
def periodo_preset(clave: str, hoy: date) -> Periodo
def resumen(db, ambito, periodo) -> Resumen
def por_dia(db, ambito, periodo) -> list[DiaVentas]
def por_hora(db, ambito, periodo) -> list[HoraVentas]
def por_metodo(db, ambito, periodo) -> dict[str, MetodoVentas]
def top_productos(db, ambito, periodo, limite=10) -> list[ProductoTop]
```

**Regla de venta (la única):**

- Documentos con `status` en `SALES_REPORT_STATUSES` (`PAID`, `REFUNDED_PARTIAL`,
  `REFUNDED_TOTAL`, definido en `app/services/cash_reconciliation.py`) y `doc_type` de venta,
  a su `total_amount` original. `PENDING`, `DRAFT` y `CANCELLED` nunca cuentan.
- Devoluciones: `SaleReturn.status == "APPROVED"`, por la fecha de la devolución
  (`SaleReturn.created_at` en día de México), sumando `total_refunded`. Una devolución
  pendiente no cuenta hasta aprobarse.
- `venta_bruta` = suma de documentos; `devuelto` = suma de devoluciones;
  `venta_neta = venta_bruta - devuelto`; `tickets` = número de documentos;
  `ticket_promedio = venta_neta / tickets` (0 si no hay tickets).
- Por método: `Payment.amount` agrupado por `method`, menos `SalesDocument.change_given` en
  `CASH`, menos `total_refunded` por `refund_method` de las devoluciones aprobadas.
- Utilidad bruta: igual que hoy en `/reports/inicio` (líneas con costo), menos el costo de lo
  devuelto que reingresó (`SaleReturnItem.is_inventory_reentry`); `venta_sin_costo` se sigue
  reportando aparte.
- Día de México en toda comparación de fechas (`_mx` de `app/routers/reports.py` se mueve al
  servicio). Las series por día y por hora agrupan sobre la misma expresión que filtra.

**Ámbito (`resolver_ambito`):** roles en `HQ_ROLES` (hoy ADMINISTRADOR, GERENTE y DUEÑO en
`reports.py:49`; no se cambia la lista): `branch_id` ausente o `0` = toda la organización;
número = esa sucursal. Cualquier otro rol: siempre `current_user.branch_id`. Esto corrige el
punto 3 de §1 y queda documentado en `docs/API_REFERENCE.md`.

**Periodos (`periodo_preset`):** `hoy`, `ayer`, `7d` (hoy y seis anteriores), `30d` (hoy y
29 anteriores), `mes` (del 1 al día de hoy), `rango` (fechas explícitas). El comparativo es
siempre `Periodo.anterior()`.

**Series:** `por_dia` devuelve un renglón por cada día del periodo, con ceros. `por_hora`
devuelve las 24 horas (0 a 23) con `neta` y `tickets`; es el frontend quien recorta a
`min(9, primera hora con venta) .. max(21, última hora con venta)`.

### 2.2 Endpoints que pasan al servicio

| Endpoint | Cambio |
|---|---|
| `GET /reports/inicio` | `hoy`, `ayer`, `semana`, `por_metodo_hoy`, `utilidad_bruta_hoy`, `top_semana`, `sucursales[].ventas_hoy` salen del servicio. Campos nuevos: `hoy.devuelto`, `ayer.devuelto`, `semana.devuelto`, `tendencia` (§3.1) y `por_hora_hoy` (§3.1) |
| `GET /reports/dashboard` | `kpis.sales` es neta; `kpis.returns` nuevo; `kpis.pending`/`draft` se conservan como informativos; `charts.trend` por día de México; `charts.hourly` con las 24 horas; `charts.payments` neto de cambio y devoluciones; ámbito por `resolver_ambito` |
| `GET /reports/daily-summary` | Mismos campos, calculados por el servicio |
| `GET /reports/sales-by-hour` | Mismos campos, 24 horas |
| `GET /reports/command-center/stats` | `global.total_sales` neta; `returns_total` = `devuelto`; `branches[].total_sales` neta |
| `GET /sales/stats` | Mismos campos, calculados por el servicio (deja de sumar PENDING/DRAFT) |
| `GET /returns/` | `start_date`/`end_date` como `date` en día de México; sin fechas, los últimos 30 días; `branch_id` por `resolver_ambito` |

La caja (`/cash/*`) no cambia: el corte es por turno y se concilia con sus propios pagos.

### 2.3 Bugs de paso

- `app/routers/sales.py:368`: el decorador `@router.post("", include_in_schema=False)` pasa a
  `create_sale`, junto al de `"/"`. Prueba: `POST /api/sales` sin barra crea la venta.
- `app/main.py:326-330`: se elimina el redirect de `/hq/sales`; la SPA sirve la ruta.

### 2.4 Pruebas

`tests/test_metricas_ventas.py` (fixtures de `conftest.py`): venta a las 19:30 de México
(01:30 UTC del día siguiente) cae en el día de México; devolución aprobada resta y pendiente
no; cambio entregado se resta del efectivo; venta PENDING no cuenta; ámbito de sucursal
contra organización para admin y para cajera; `Periodo.anterior()` de `7d` y de `mes`;
`por_hora` trae 24 renglones. Las pruebas existentes de reportes
(`tests/test_reports_inicio.py`, `test_reports_daily_summary.py`, `test_regresion_reportes.py`,
`test_branch_dashboard.py`) se ajustan solo donde asumían el bruto o las 14 horas.

### 2.5 Añadido 2026-10-24 · Valor de la tienda: distribución por departamento y marca

Pedido del usuario durante la ejecución: "en el módulo de valor de tienda quiero ver por
departamento y marca para saber cómo está distribuido el valor de la tienda". Hoy
`/hq/valor-inventario` agrupa por sucursal **o** departamento **o** marca (un selector, una
tabla) y no muestra porcentajes, así que la distribución no se ve.

- **Pantalla:** sin selector "Agrupar por"; dos paneles a la vez, **Por departamento** y **Por
  marca**, cada uno con piezas, valor a venta, **% del valor** con barra, valor a costo (si el rol
  lo ve), piezas sin costo y su CSV (columna "% del valor"). Tocar un departamento acota el panel
  de marcas a ese departamento ("Marcas en Bolsas · Quitar"); "Sin departamento" no es elegible.
  Con más de una sucursal que vende y sin filtro de sucursal, un tercer panel **Por sucursal**.
  Barra en CSS con tokens (`bg-dax-accent` sobre `bg-dax-border-dim`); la Fase 2 puede cambiarla
  por una dona del kit. La tarjeta del Inicio no cambia.
- **Backend:** `GET /reports/valor-inventario` gana `department_id` (UUID) que acota totales y
  grupos; de otra org → 404; la respuesta lo devuelve (`null` si no se pidió). El gerente sigue
  limitado a su sucursal y sin costo.
- **Dónde:** plan de la Fase 1, Tarea 8 (corre antes del cierre de la Tarea 7).

## 3. Fase 2 · Inicio, Reportes y tema

### 3.1 Inicio del administrador (`pages/hq/Inicio.tsx`)

Conserva las preguntas de SP6 (spec `2026-10-21-sp6-vista-dueno-design.md` §2) y añade
gráficas. Una sola llamada: `/reports/inicio` con dos campos nuevos:

```json
"tendencia": { "dias": [{ "fecha": "2026-10-17", "neta": 1200.0, "tickets": 3 }],
               "anterior": [{ "fecha": "2026-10-10", "neta": 900.0, "tickets": 2 }] },
"por_hora_hoy": [{ "hora": 0, "neta": 0, "tickets": 0 }]
```

Orden en escritorio (≥1024, rejilla de 12 columnas; en teléfono todo apilado):

1. Cifras: Hoy (neta; detalle "N ventas · $X devuelto" si hubo devoluciones), Ayer, 7 días,
   Utilidad bruta de hoy. Cada una con variación contra ayer o contra la semana anterior
   (`▲ 12 %` en `dax-success`, `▼` en `dax-danger`, "igual" en `dax-muted`).
2. Tendencia de 7 días (línea, 8 columnas; la semana anterior en gris) · Cómo te pagaron (dona,
   4 columnas, total al centro).
3. Ventas por hora de hoy (barras, 8 columnas; la hora actual resaltada con el acento) · Caja
   (4 columnas, como hoy).
4. Pendientes.
5. Se está acabando · Lo que más se vendió.
6. No se mueve.
7. Cómo va cada sucursal (barras horizontales ordenadas por venta + las tarjetas actuales).
   Solo con más de una sucursal.

Modo básico (`perfilUi === 'basico'`): el Inicio sigue sin gráficas y sin cargar el chunk
`charts` (decisión SP2/SP6 para PC viejas); solo cambian las cifras a netas.

### 3.2 Reportes (`pages/reports/Reportes.tsx`, nuevo)

Un componente para todos. `/hq/reports-hub` lo monta con selector de sucursal; `/reports`
(cajera, gerente y perfil básico) lo monta fijado a la sucursal del usuario.
`pages/finance/Reports.tsx` y `pages/hq/HQReportsHub.tsx` se borran.

- Barra: presets `Hoy · Ayer · 7 días · 30 días · Este mes` + rango; sucursal (solo quien ve
  varias); Exportar CSV (el de hoy).
- Cifras con variación contra el periodo anterior: Venta neta, Tickets, Ticket promedio,
  Devoluciones, Utilidad bruta (solo si la org tiene costos).
- Tendencia (línea con el periodo anterior en gris) · Cómo me pagaron (dona).
- Ventas por hora (barras, promedio por hora del periodo).
- Día y hora (el `Heatmap` actual, repintado con tokens).
- Sucursales (barras horizontales; solo con más de una).
- Lo más vendido (tabla: producto, piezas, importe, barra de proporción).

Se quita: `Gauge`, el conteo animado y las chispas de `KPICard`, `Leaderboard`, el sondeo de
ventas por hora cada 30 segundos y las tarjetas "En tránsito" y "Ritmo actual".

### 3.3 Gráficas y tarjetas (kit)

`frontend/src/components/graficas/`: `GraficaLinea`, `GraficaBarras`, `GraficaDona`, envoltorios
de `react-chartjs-2` (chart.js ya vive en el chunk `charts`, prohibido solo en la precarga del
POS). `useTemaGrafica()` lee `--dax-text-muted`, `--dax-border-dim`, `--dax-accent`,
`--dax-success`, `--dax-warning`, `--dax-danger` con `getComputedStyle` y se vuelve a leer cuando
cambia la clase de `<html>` (MutationObserver), para que la gráfica se repinte al cambiar de
tema. Serie principal: acento; comparativo: `--dax-text-faint`; métodos: efectivo = success,
tarjeta = accent, transferencia = warning, otros = faint. Ejes con `formatCurrency` abreviado
(`$1.2k`), tooltips con `formatCurrency`, animación de 300 ms, sin degradados ni relleno.

`components/ui/KpiCard.tsx`: `etiqueta`, `valor`, `detalle?`, `variacion?: { pct, texto }`,
`tono?: 'success'|'warning'|'danger'`. Usa `dax-kpi-label` y `dax-kpi-value`. Sustituye a
`components/reports/KPICard.tsx` y a la `Cifra` local de `Inicio.tsx`.

### 3.4 Tema por tokens

Tailwind ya expone `text-dax-text`, `text-dax-muted`, `text-dax-faint`, `bg-dax-card`,
`bg-dax-elevated`, `border-dax-border`, `border-dax-border-dim`, `text-dax-success/warning/danger`
(`frontend/tailwind.config.js`). Las pantallas de este proyecto —`pages/hq/`, `pages/home/`,
`pages/finance/`, `pages/sales/`, `pages/inventory/`, `pages/core/`, `pages/reports/`,
`components/reports/`, `components/graficas/`— dejan de usar `text-white`, `text-slate-*`,
`bg-slate-*`, `border-slate-*` y colores hex sueltos. Guardia nueva
`frontend/src/__tests__/coloresPorTokens.test.ts`: recorre esas carpetas y falla si encuentra
esas clases; arranca con una lista blanca de archivos que cada fase vacía. Las sobrescrituras
`html.light` de `index.css` se quedan mientras POS y plataforma las usen; retirarlas es otro
proyecto.

Tipografía: títulos de sección con `dax-section-title` y formulados como pregunta (como en el
Inicio de SP6), cifras con `dax-kpi-*`. Un solo `CabeceraPagina` por pantalla.

## 4. Fase 3 · Fusiones y menú

### 4.1 Pantallas

| Ruta final | Base | Se le suma | Solo HQ (`ADMINISTRADOR`/`DUEÑO`) |
|---|---|---|---|
| `/sales` Ventas | `SalesHistory.tsx` | filtro de sucursal | el selector, visible con más de una sucursal |
| `/returns` Devoluciones | `Returns.tsx` | filtro de sucursal y periodo (presets de §2.1) | el selector |
| `/inventory` Inventario | `Inventory.tsx` | costo, importe, "solo sin costo", búsqueda por `?q=&variant=` | las columnas de costo |
| `/products` Productos | `Products.tsx` | cifras de catálogo (`CatalogKpis`), filtro y acciones de aprobación, duplicar, archivar, restaurar | aprobación, archivar, restaurar |

"Solo HQ" se decide con `useAuthStore().user.role`; "más de una sucursal" con la lista de
`/branches` que ya cargan `HQSalesLog` y `HQReturns`. Se borran `HQSalesLog.tsx`,
`HQReturns.tsx`, `HQInventory.tsx` y `AdminCatalog.tsx`. Redirects en `App.tsx` conservando la
consulta: `/hq/sales → /sales`, `/hq/returns → /returns`, `/hq/inventory → /inventory`,
`/admin/catalog → /products`. Referencias a actualizar: `pages/hq/Inicio.tsx:41-44,176,219`,
`components/layout/Sidebar.tsx:17`, `pages/menu/MenuVisual.tsx:92`, `navPerfilBasico.ts`.

### 4.2 Menú del administrador (`navConfig.ts`)

Desaparecen los grupos "Mi tienda" y "Caja" y los cuatro ítems de HQ fusionados.

| Grupo | Ítems en orden |
|---|---|
| Operación | Inicio, Reportes, Valor de la tienda |
| Ventas | Ventas, Devoluciones, Corte de caja, Cotizaciones, Nueva cotización, Pedidos |
| Catálogo | Productos, Departamentos, Marcas, Etiquetas |
| Inventario | Inventario, Conteo, Escáner, Logística, Cajas y contenedores |
| Compras | Compras, Gastos, Pedidos compras |
| Clientes | Clientes, Agenda, Comisiones, Membresías |
| Restaurante | sin cambios |
| Organización | Empresa, Sucursales, Usuarios, Recursos Humanos, Impresora |
| Inteligencia | IA |

`ROLE_ROUTES` quita las URL fusionadas y añade `/returns` e `/inventory` a ADMINISTRADOR y
DUEÑO (hoy solo tienen las de HQ); `OCULTAS_BASICO_HQ` cambia `/hq/sales`, `/hq/returns`,
`/hq/inventory`, `/admin/catalog` por nada (Ventas y Productos ya se ven en básico; Inventario
y Devoluciones se siguen ocultando como `/inventory` y `/returns`). `routeTitle` conserva los
nombres. Pruebas de `components/layout/__tests__/` y `docs/FRONTEND_VIEWS.md` al día.

## 5. Lo que no cambia

El POS, la caja y el corte, el panel móvil del dueño (hereda la regla neta por
`daily-summary`, sin restilizar), la plataforma, el Escáner, el Conteo y las Etiquetas.
`GastroHomeDay` y el detalle de `HQBranches` siguen llamando a `/reports/dashboard` y heredan
la precisión sin cambiar de pantalla.

## 6. Guardias y pruebas

- Backend: `tests/test_metricas_ventas.py` (§2.4); las de reportes existentes ajustadas.
- Frontend: `coloresPorTokens.test.ts` (§3.4); `navConfig.test.ts` y `navPerfilBasico.test.ts`
  con el menú nuevo; `unSoloFormularioDeProducto.test.ts`, `botonesDelKit.test.ts` y
  `overlaysFueraDelKit.test.ts` siguen vigentes; `rutasPerezosas.test.ts` registra los módulos
  nuevos que carguen con `lazy()`.
- Presupuesto de bundle: la ruta crítica del POS no cambia (`frontend/presupuesto_bundle.json`).

## 7. Verificación por fase

Cada fase: `pytest -q --ignore=tests/test_cash_complete.py`, `vitest`, `tsc`, `vite build`,
capturas Playwright a 1440 y 390 en claro y oscuro sobre la base de demo (receta en la memoria
`playwright-sin-sudo-wsl`, con el registro de `timezone`/`to_char` para SQLite del
`demo_server.py` del scratchpad). La fusión a `main` la autoriza el usuario en cada fase.
Tras desplegar la fase 1 se comprueba en Eleven que "Ventas hoy" coincida en Inicio, Reportes
y Mis ventas.

## 8. Criterios de salida

1. Un solo número de venta por periodo y sucursal en todas las pantallas.
2. Inicio del admin con las cuatro gráficas, en claro y oscuro, sin colores fijos.
3. Ningún módulo del admin repetido; las URL viejas redirigen.
4. `docs/FRONTEND_VIEWS.md`, `docs/API_REFERENCE.md` y este spec al día.

## 9. Riesgos

- La regla neta baja las cifras de quien tenía devoluciones: avisar al usuario antes de
  desplegar la fase 1.
- `HQ_ROLES` incluye GERENTE en reportes pero el menú lo trata como rol de sucursal; se conserva
  tal cual para no cambiar lo que hoy ve un gerente.
- `tests/test_cash_complete.py` y el uvicorn ajeno en :8000 siguen vigentes (CLAUDE.md §6).
