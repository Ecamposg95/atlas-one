# Auditoría funcional 2026-09-22

> Histórico fechado — no es referencia viva, no se actualiza. Snapshot del estado de los
> hallazgos al 2026-09-22. Si un hallazgo "abierto" se corrige después, este documento
> queda desactualizado en ese punto — verifica contra el código.

Resumen de la auditoría funcional de bugs que corrió en paralelo sobre `main` (backend
`@ 4054d6e`, frontend `@ 4054d6e`) el 2026-09-22, y qué se hizo con cada hallazgo. Fuentes
completas: `.superpowers/sdd/audit-funcional/backend-findings.md` (36 hallazgos, con
sondas `tests/test_sonda_*.py` para 18 de ellos), `frontend-findings.md` (43 hallazgos),
`frontend-fix-report.md` (los 12 corregidos, con commit por hallazgo). Estos tres archivos
viven en un worktree (`.superpowers/sdd/`, no versionado / gitignored) — este documento es
la versión que sí queda en el repo.

No es una auditoría de estilo/UX (esa vive en `.superpowers/sdd/ux-admin/admin-ux-findings.md`,
tampoco versionada) — solo bugs funcionales.

---

## 1. Backend — 36 hallazgos (Crítica 6 · Alta 9 · Media 14 · Baja 7)

### 1.1 Corregidos 2026-09-22

| # | Severidad | Archivo:línea | Qué era |
|---|---|---|---|
| C1 | Crítica | `app/routers/sales.py:648-661` | `discount` por línea evadía el guard de margen `MAX_DISCOUNT_PCT` (solo comparaba `unit_price` crudo) |
| C2 | Crítica | `app/schemas/sales.py:21`, `app/routers/sales.py:619-622,702-716` | `quantity` negativa inflaba stock y producía totales negativos |
| C3 | Crítica | `app/routers/sales.py:501-527,870-895` | Se podía tomar una venta PENDING de otra sucursal por `id` y cobrarla/descontarla en la propia |
| C4 | Crítica | `app/routers/sales.py:1411-1414` | `cancel_sale` (DELETE) sin `_assert_sale_branch_access`: cualquier cajero cancelaba ventas de cualquier sucursal |
| C5 | Crítica | `app/modules/users/router.py:214-248`, `schemas.py:48` | ADMINISTRADOR de tenant se autopromovía a `platform_role=SUPERADMIN` vía `PUT /api/users/{id}` |
| C6 | Crítica | `app/crud/returns.py:99-107` | Devolución reembolsaba `unit_price` bruto ignorando el descuento de línea → sobre-reembolso |
| A2 | Alta | `app/routers/sales.py:873,911` vs `:831-834` | `create_sale` aceptaba `customer_id` de OTRA organización en venta de contado (la validación por org solo corría en la rama de crédito) |
| A3 | Alta | `app/routers/cash.py:490-514` | GERENTE cerraba la caja de OTRA sucursal (`close-guided`, sin comparar `branch_id`) |
| A4 | Alta | `app/routers/cash.py:1161-1185` | `GET /cash/branch-summary?branch_id=` filtraba por org, no por sucursal — GERENTE veía el corte de otra sucursal |
| A5 | Alta | `app/modules/products/router/core.py:1036-1042` | `PUT /api/products/{id}` con `description`/`unit`/`image_url: null` no borraba el campo |
| A6 | Alta | `app/modules/products/router/__init__.py:48-59`, `core.py:581` | Rutas GET de un segmento registradas después de `core.router` quedaban tapadas por `/{product_id}` (`/boxes-inventory`, `/search`) |
| A7 | Alta | `app/modules/customers/router.py:213-236,266-290` | Cliente con portal (`enable_portal`) nunca recibía `UserOrganization` → portal inutilizable (403 siempre) |
| A8 | Alta | `app/routers/reports.py:147-154` | `daily-summary.gross_profit` descartaba líneas con `unit_cost` NULL (ingreso incluido, ganancia no) |
| A9 | Alta | `app/routers/reports.py:231,259` | `aging-report` restaba datetime naive − aware → 500 en Postgres |
| M1 | Media | `app/pos_printer.py:1453-1454` | Logo remoto que fallaba al rasterizar producía `NameError` en el `except` (variable indefinida) → 500 en vez de degradar a "sin logo" |
| M3 | Media | `app/routers/cash.py:512-513` | `close-guided` bloqueaba a ADMINISTRADOR/DUEÑO (solo aceptaba GERENTE), contradiciendo su propio comentario |
| M6 | Media | `app/routers/sales.py:1379-1384`, `templates/print/ticket.html:201` | `GET /sales/{id}/print-view` → 500 en cualquier venta con líneas (float × Decimal) |
| M14 | Media | `app/pos_printer.py:912-921,1058` | Corte de caja impreso reventaba con un carácter fuera de latin-1 en sucursal/cajero (sin `errors="replace"`) |
| B1 | Baja | `app/routers/sales.py:1525` | `POST /sales/{sale_id}/refund` declaraba `sale_id: int` (los ids son UUID) → siempre 422, endpoint muerto |

### 1.2 Abiertos (sin fecha de corrección)

| # | Severidad | Archivo:línea | Qué es | Por qué se difirió |
|---|---|---|---|---|
| A1 | Alta | `app/routers/sales.py:702-716,1428-1454` | Ningún `with_for_update()` en `sales.py`: overselling y doble reversión bajo concurrencia | PLAUSIBLE, Postgres-only — SQLite no reproduce el lock real (regla de oro #7); fuera del lote priorizado |
| M2 | Media | `app/routers/cash.py:1065-1080`, `printer.py:531` | `_verify_session_access` ignora la org activa y toma `UserOrganization.first()` sin `order_by` | Solo afecta usuarios multi-org (QA/soporte); confirmado pero de bajo alcance práctico hoy |
| M4 | Media | `app/routers/cash.py:281-300` | `corregir_saldo_inicial` tiene la misma fuga cross-sucursal que A3 | Mismo código que A3, sin sonda propia — pendiente de aplicar el mismo fix |
| M5 | Media | `app/routers/cash.py:480-487,498-507` | Cierre de sesión sin lock de fila → doble cierre concurrente | PLAUSIBLE, Postgres-only |
| M7 | Media | `app/modules/products/models.py:101`, `app/services/barcodes.py:59-73` | `product_variants.barcode` sin índice único a nivel de base (solo check-then-act en app) | PLAUSIBLE bajo concurrencia; requiere limpiar 2 duplicados preexistentes en prod antes de poder indexar (ver `docs/presets/BOUTIQUE.md §2.4`) |
| M8 | Media | `app/modules/products/router/variants.py:109-116,175-177,261-281` | Pareja color+talla duplicada bajo concurrencia (sin constraint DB) | PLAUSIBLE bajo concurrencia; requiere índice único parcial nuevo, fuera del lote |
| M9 | Media | `app/modules/products/router/branch_status.py:129`, `packaging.py:55,65,74,118`, `departments.py:27`, `stats.py:176` | Filtro `organization_id == org OR organization_id IS NULL` expone productos huérfanos a cualquier org | Patrón repetido 4 veces; requiere migrar huérfanos pre-multitenancy antes de poder quitar el `OR IS NULL` |
| M10 | Media | `app/modules/users/router.py:246-248` | `update_user` no valida que `branch_id` pertenezca a la org activa (`create_user` sí) | PLAUSIBLE, sin sonda propia |
| M11 | Media | `app/routers/reports.py:694-918,165-219` | `command-center/stats` y `audit/discrepancies` sin filtro de sucursal ni rol | PLAUSIBLE; requiere replicar `_resolver_sucursal` en dos endpoints más, fuera del lote |
| M12 | Media | `app/modules/customers/router.py:420-451` | `register_customer_payment` sin `with_for_update()` → doble abono puede pasar el guard anti-sobrepago | PLAUSIBLE, Postgres-only |
| M13 | Media | `app/schemas/returns.py:27`, `app/crud/returns.py:61-78` | `create_return` acepta cantidad ≤0 y `variant_id` repetido → PENDING inaprobable que bloquea devoluciones legítimas | PLAUSIBLE; requiere ajustar schema + loop de cómputo, fuera del lote |
| B2 | Baja | `app/routers/cash.py:907-915` | `expected.total_system` suma ventas de TODOS los métodos con ajustes solo-efectivo | Campo público sin consumidor en el frontend — bajo impacto |
| B3 | Baja | `app/routers/cash.py:928` | `diff_percent` = 0 cuando `expected_cash <= 0` enmascara diferencias reales | Bajo impacto, sin sonda |
| B4 | Baja | `app/routers/cash.py:966,1016` | `register_inflow`/`register_outflow` reciben `amount: float` (query) antes de `Decimal` | PLAUSIBLE, bajo impacto |
| B5 | Baja | `app/modules/products/router/barcodes.py:158-174` | `export/labels.csv` sin neutralizar fórmulas (`=`,`+`,`-`,`@`) — inyección CSV | PLAUSIBLE; requiere sanitizar el export, fuera del lote |
| B6 | Baja | `app/modules/customers/router.py:348-351,524-538` | Estado de cuenta del cliente compara TIMESTAMPTZ contra fechas naive (sin `_mx()`) | PLAUSIBLE; movimientos cerca de medianoche pueden caer en el día equivocado |
| B7 | Baja | `app/services/cash_reconciliation.py:42`, `app/pos_printer.py:15` | Hardcodea `America/Mexico_City` ignorando `BUSINESS_TIMEZONE` | Sin impacto hoy (default ya es CDMX); latente si se cambia de zona |

Sondas de los hallazgos confirmados: `.claude/worktrees/audit-backend/tests/test_sonda_*.py`
(24 archivos, sin commit — correr de a uno, nunca en paralelo en el mismo worktree, ver
`CLAUDE.md §6`).

---

## 2. Frontend — 43 hallazgos (Crítica 4 · Alta 13 · Media 17 · Baja 9)

### 2.1 Corregidos 2026-09-22 (rama `wt/fix-frontend`, merge `ed8f41f`)

Detalle completo por hallazgo (qué cambió, por qué, tests) en
`.superpowers/sdd/audit-funcional/frontend-fix-report.md`.

| # | Archivo:línea | Qué era | Commit |
|---|---|---|---|
| 1 | `frontend/src/pages/pos/saleItems.ts:34-42` | El precio real de una "caja" vendida no era el que se mandaba a `create_sale` (recalculaba desde el tier crudo, ignorando precio de paquete/forzado) | `3f838fd` |
| 3 | `frontend/src/App.tsx:325-334`, `pages/products/ProductForm.tsx` | "Nuevo producto" heredaba los datos del producto que se estaba editando (sin `key` que forzara remount) | `d6e031b` |
| 4 | `frontend/src/pages/finance/CashHistory.tsx:69-73` | Cerrar turno con dato inválido dejaba el botón bloqueado en "cargando" para siempre | `205be77` |
| 5 | `frontend/src/components/pos/ProductSearch.tsx:320` | Límite de stock mal calculado con variante emparejada (`cartQtyUnits` sin filtrar por variante) | `0acad93` |
| 6 | `frontend/src/pages/scanner/barcodeReader.ts:45-48` | El escáner de QR quitaba el guion del SKU boutique (`M-1151` → `m1151`) y dejaba de emparejar | `39575a9` |
| 7 | `frontend/src/api/products.ts:432,437,451,456` | Editar/borrar Marca o Departamento devolvía 405 (barra final que el backend no registra) | `b19080f` |
| 8 | `frontend/src/pages/sales/SalesHistory.tsx:282-289` | Botón "Reimprimir" de fila sin guard de reentrada — doble clic dispara dos impresiones | `f93e09d` |
| 9 | `frontend/src/pages/admin/AdminProductCreate.tsx:165-190,237` | Alta administrativa de producto perdía género/modelo/material aunque el formulario los capturaba | `14289e9` |
| 11 | `frontend/src/pages/core/AdminCatalog.tsx:140-149` | "Exportar" del catálogo admin ignoraba el checkbox "Incluir archivados" | `cb9d7bc` |
| 14 | `frontend/src/store/authStore.ts:50-58`, `pages/Login.tsx:111-112` | El contexto de organización de una sesión anterior sobrevivía a un login sin organización (SUPERADMIN) | `999acf4` |
| 16 | `frontend/src/pages/core/Organization.tsx:120,134` | Guardar/borrar sucursal ocultaba el motivo específico del error del backend | `31d9daa` |
| 17 | `frontend/src/pages/core/Organization.tsx:166,195` | Borrar "Razón social" y guardar dejaba `organization.name` en `NULL` | `3790212` |

Verificación final de la rama: `npx tsc --noEmit` limpio, `npx vitest run` → 482/482
(475 base + 7 nuevos), `npm run build` exitoso.

### 2.2 Abiertos — Alta, fuera de alcance por instrucción explícita

| # | Archivo:línea | Qué es |
|---|---|---|
| 2 | `frontend/src/pages/pos/PrinterSettings.tsx:292-294,320-336` vs `POS.tsx:204-212` | La impresora Bluetooth conectada en Configuración nunca se usa para imprimir una venta real (`connectBluetooth` no llama `setPrinterName`) |
| 10 | `frontend/src/pages/core/AdminCatalog.tsx:80-85` | Filtro "Sin sucursal" del catálogo admin es client-side sobre una sola página; el total no se recalcula |
| 12 | `frontend/src/components/catalog/ProductAuditDrawer.tsx:104-118` vs `branch_status.py:526-544` | El historial de auditoría no muestra el diff para la edición más común (`PATCH /variants/{id}/branch-status` escribe otro formato) |
| 13 | `frontend/src/App.tsx:258-360`, `app/modules/users/router.py:122`, `tenants/router.py:47` | Casi ninguna ruta protegida verifica el rol (~5-6 de ~55 con `RequireRole`); los `GET` de usuarios/organización tampoco gatean por rol en el backend |
| 15 | `frontend/src/components/layout/Sidebar.tsx:23-30,154-155,257-296` | `BranchNav` descarta en silencio ítems permitidos sin grupo asignado (Devoluciones, Recetas) |

### 2.3 Abiertos — Media (17) y Baja (9), sin priorizar aún

No se tocaron: el lote de corrección solo cubrió los 12 hallazgos Crítica/Alta listados
arriba, por instrucción explícita del encargo. Lista completa con escenario y corrección
sugerida en `.superpowers/sdd/audit-funcional/frontend-findings.md §Media` (#18-34) y
`§Baja` (#35-43). Resumen de una línea:

**Media:** #18 doble submit por Enter en modales de pago sin guard · #19 stock 0 tratado
como "sin límite" (comparación truthy) · #20 "Agregar" cierra el modal aunque no se haya
agregado nada · #21 búsqueda de productos sin guardia de secuencia (respuestas fuera de
orden) · #22 gating del módulo `scanner` solo cosmético · #23 guardar con Bluetooth
conectado corrompe `branches.printer_name` · #24 error de impresión automática siempre
muestra el mismo mensaje genérico · #25 alta admin de producto sin botón "Sugerir SKU" ·
#26 botón "Guardar" de variante puede quedar "sucio" tras guardar con éxito · #27
reordenar colores/tallas cambia en silencio cuál combinación es "la principal" · #28
CAJERO ve inputs editables de todas las sucursales en la matriz · #29 cajón lateral móvil
no se resetea al cruzar el breakpoint · #30 `RequireRole` redirige siempre a `/atlas-pos` ·
#31 `localStorage` del tema sin `try/catch` · #32 modal de movimiento de caja valida menos
que el backend (10 caracteres) · #33 movimientos del resumen de caja usan el índice del
array como `key` · #34 el 403 de "usuarios HQ sin historial de caja" se traga en silencio.

**Baja:** #35 tablero "Ventas hoy" se congela tras medianoche · #36 venta offline
descartada deja el parked ticket huérfano · #37 sugerencia de SKU puede colisionar sin
chequeo previo · #38 contador "activo en N/M sucursales" puede mostrar razón inconsistente ·
#39 interceptor de 401 limpia solo 2 de 5 claves de sesión · #40 fallo transitorio de
`/users/me/context` manda al admin a la home equivocada · #41 "Diferencia: $0.00" antes de
capturar el conteo de cierre (NaN) · #42 activar/desactivar usuario oculta el motivo del
fallo · #43 `localStorage` del nombre de impresora sin `try/catch` puede tumbar el store
del POS al importar.

---

## 3. Riesgo cruzado: `create_sale` en la misma ventana

C1-C4 (backend, corregidos) y #1 (frontend, corregido) tocan el mismo motor de checkout
(`app/routers/sales.py::create_sale`, zona peligrosa nº 1 del repo — `CLAUDE.md §2.8`).
Los cinco se corrigieron y desplegaron en la misma sesión de trabajo del 2026-09-22; no
hay evidencia de que se hayan combinado con la fusión de `feat/pago-atribuido-a-caja`
(`63ee8a2`, ver `docs/CHANGELOG-2026-09-boutique.md`), que tocó `create_sale` por un
motivo distinto (atribución de pago a caja) el mismo día — **ambos cambios conviven en
`main` a partir de este día y no se re-probaron juntos más allá de la suite de pytest**.
