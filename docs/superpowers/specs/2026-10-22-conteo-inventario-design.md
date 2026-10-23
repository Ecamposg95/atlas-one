# Conteo de inventario con escáner — diseño

**Fecha:** 2026-10-22 · **Estado:** aprobado en charla, pendiente de revisión del spec ·
**Caso guía:** Eleven Fashion (org 17, sucursal 20 Roma, ULTRA+): 21 departamentos, ~1,550
variantes todas con código de barras interno, ~2,900 piezas en sistema. **Quién lo usa:** el
dueño/admin con el teléfono (cámara), un departamento por sesión.

## 1. Problema

El sistema dice que hay 2,900 piezas; nadie sabe cuántas hay de verdad. Lo que existe hoy para
averiguarlo es el Escáner (`/scanner`, `pages/scanner/StoreScanner.tsx`): escanea un código,
muestra el producto y deja registrar un conteo que se aplica **al instante** como ajuste al
kardex. Sirve para corregir una pieza; no sirve para recorrer un departamento, porque no recuerda
nada entre escaneos: no hay lista de lo verificado, no dice qué faltó por escanear y no deja
reporte. Además el dueño quiere **ver antes de tocar**: un conteo físico no debe mover el
inventario hasta que alguien revise las diferencias.

Decisiones tomadas con el usuario el 2026-10-22:

| Pregunta | Decisión |
|---|---|
| Modo | Inventario físico completo: lo que el sistema tiene y nadie escaneó es faltante |
| Discrepancias | **Solo se reportan** en fase 1; los ajustes al kardex se aplican en fase 2 (§11) |
| Sesión | Una por departamento, guardada en el servidor; se puede seguir otro día o en otro teléfono |
| Escaneo | Cada lectura suma 1 pieza; la cantidad se puede corregir en la lista |
| Pieza sin código legible | Buscar por nombre/SKU y marcarla contada; o ligarle el código ahí mismo (**reemplaza** el interno, como hace el Escáner) |
| Reporte | En pantalla, dentro de Atlas (sin Excel/PDF por ahora) |
| Quién lo ve | ADMINISTRADOR y DUEÑO de cualquier org con módulo `inventory`; oculto en modo básico |
| Orden con la limpieza de Eleven | Diagnóstico ya hecho (solo lectura); la limpieza se decide con el primer conteo en mano |

Enfoque elegido: **sesiones en el servidor** (frente a una lista en `localStorage` o un híbrido
con cola sin red). Cada escaneo es una petición, igual que hoy en el Escáner.

## 2. Modelo de datos

Módulo nuevo `app/modules/conteos/` (`models.py`, `schemas.py`, `services.py`, `router.py`),
registrado en `app/models/__init__.py` con `from app.modules.conteos import models`. Las dos
tablas las crea `create_all`; no hay ALTER en `railway_init.py`.

**`inventory_counts`** (`InventoryCount`, `TenantMixin`)

| Columna | Tipo | Nota |
|---|---|---|
| `id` | Integer PK | |
| `branch_id` | Integer FK `branches.id` NOT NULL | sucursal contada |
| `department_id` | String(36) FK `departments.id` NULL | NULL = toda la tienda |
| `status` | String(10) NOT NULL | `ABIERTO` / `CERRADO` (constantes Python, no enum DB) |
| `notes` | String NULL | "Playeras, pared izquierda" |
| `created_by_user_id` | Integer FK `users.id` NULL | |
| `created_at` | DateTime tz, `server_default=now()` | |
| `closed_at` | DateTime tz NULL | |
| `resumen` | Text NULL | JSON del reporte congelado al cerrar (§5) |

**`inventory_count_lines`** (`InventoryCountLine`, `TenantMixin`)

| Columna | Tipo | Nota |
|---|---|---|
| `id` | Integer PK | |
| `count_id` | Integer FK `inventory_counts.id` NOT NULL, index | |
| `variant_id` | String(36) FK `product_variants.id` NULL | NULL = código desconocido |
| `codigo` | String NULL | lo escaneado, solo para desconocidos |
| `qty_contada` | Numeric(10,2) NOT NULL default 0 | |
| `qty_sistema` | Numeric(10,2) NULL | existencia al **cerrar**; NULL mientras está abierto |
| `created_by_user_id` | Integer FK `users.id` NULL | |
| `created_at` / `updated_at` | DateTime tz | |

Restricciones: `UniqueConstraint(count_id, variant_id)` y `UniqueConstraint(count_id, codigo)`.
Una línea por variante por conteo: escanear la misma talla dos veces suma 1 a la misma línea.
Una línea de desconocido por código. **FKs a UUID = `String(36)`** (regla de oro #4).

## 3. API — `/api/inventory/counts`

Router montado en `app/main.py` con `prefix="/api/inventory/counts"`, `tags=["Conteos"]`,
`dependencies=[Depends(require_module("inventory"))]`. Todos los handlers exigen
`_is_admin(current_user)` (`app/crud/products.py`); cualquier otro rol recibe 403. Un conteo de
otra org es 404 (consulta filtrada por `organization_id`). La sucursal: ADMIN/DUEÑO la mandan en
el cuerpo (como el Escáner, `branch_id` recordado en el dispositivo); si el usuario tiene
`branch_id` propio se usa el suyo e ignora el cuerpo.

| Método y ruta | Cuerpo | Respuesta | Reglas |
|---|---|---|---|
| `POST /` | `{branch_id, department_id?, notes?}` | `ConteoRead` | la sucursal y el departamento deben ser de la org; 409 si ya hay un conteo ABIERTO de esa sucursal y departamento (NULL cuenta como un departamento) |
| `GET /` | `?status=&branch_id=` | `List[ConteoRead]` | orden `created_at` desc; sin líneas |
| `GET /{id}` | | `ConteoDetalle` | conteo + `lineas` (con nombre/marca/talla/color/sku de la variante) + `avance` |
| `POST /{id}/scan` | `{code}` | `ScanResult` | 409 si CERRADO; ver §4 |
| `POST /{id}/lines` | `{variant_id, qty?=1}` | `LineaRead` | alta manual desde el buscador o elección entre candidatos; **suma** `qty` a la línea existente |
| `PATCH /{id}/lines/{line_id}` | `{qty_contada}` | `LineaRead` | fija la cantidad; `0` borra la línea; negativo 422 |
| `DELETE /{id}/lines/{line_id}` | | 204 | |
| `POST /{id}/close` | | `ConteoDetalle` | calcula el reporte, congela `qty_sistema` en cada línea, `status=CERRADO`, `closed_at`, guarda `resumen`; 409 si ya estaba cerrado |
| `GET /{id}/report` | | `Reporte` (§5) | abierto: se calcula en vivo ("avance"); cerrado: devuelve `resumen` tal cual |

`avance` en `ConteoDetalle`: `{esperadas_variantes, esperadas_piezas, contadas_variantes,
contadas_piezas, desconocidos}`. "Esperadas" = variantes del alcance con existencia > 0 (§5).

Esquemas Pydantic v2 en `schemas.py`: `ConteoCreate`, `ConteoRead`, `ConteoDetalle`,
`LineaRead`, `LineaCreate`, `LineaPatch`, `ScanRequest`, `ScanResult`, `Reporte`. Los
`Numeric` viajan como `Decimal` (cadena en JSON), como en `MovementRead`.

## 4. Resolución del código escaneado (`services.resolver_codigo`)

Misma regla exacta que el Escáner (`pos/search?exact=true`, `products/router/search.py`):
dentro de la org, producto activo y variante sin `deleted_at`, empata si
`lower(sku) == lower(code)` **o** `barcode == code` **o** `PackagingUnit.barcode == code`. Antes
de comparar, el cliente limpia con `normalizeCode` (cámara) o `normalizeTyped` (teclado) de
`pages/scanner/barcodeReader.ts`; el servidor solo hace `strip()`.

`POST /{id}/scan` devuelve `ScanResult`:

- **1 variante** → suma 1 a su línea y responde `{resultado: "contado", linea, producto:
  {variant_id, nombre, marca, talla, color, sku, barcode, foto}, qty_sistema,
  fuera_de_alcance: bool}`. `fuera_de_alcance` = el producto no es del departamento del conteo
  (se cuenta igual; el reporte lo separa, §5). `qty_sistema` es la existencia actual en la
  sucursal (`StockOnHand`, 0 si no hay registro).
- **Varias variantes** (un SKU repetido con otra mayúscula, un código de empaque que coincide con
  un SKU) → no cuenta nada: `{resultado: "ambiguo", candidatos: [producto…]}`; el cliente pregunta
  y manda `POST /{id}/lines` con la elegida. La prioridad `barcode` > `sku` **no** se aplica: en
  el pasillo es mejor preguntar que adivinar.
- **Ninguna** → línea de desconocido (`variant_id` NULL, `codigo`) y `{resultado: "desconocido",
  linea}`. El cliente ofrece "Buscar y ligar" (busca por nombre/SKU con `posSearch`, el usuario
  elige la talla, `PUT /products/variants/{id}` con `{barcode: code}` como ya hace el Escáner,
  borra la línea de desconocido y vuelve a escanear o manda `POST /lines`) o "Dejar como
  desconocido".

`nombre` = `sale_name` de la variante si existe, si no el nombre del producto. `foto` =
`image_url` del producto o `null`.

## 5. Reporte (`services.reporte`)

**Alcance** = variantes (sin `deleted_at`) de productos activos de la org; si el conteo tiene
`department_id`, solo las de productos de ese departamento. **Existencia** = `StockOnHand`
de `branch_id` del conteo (0 si no hay fila). **Esperadas** = alcance con existencia > 0.

Secciones, cada una con filas `{variant_id, sku, nombre, marca, talla, color, sistema, contado,
diferencia}` y ordenadas por `diferencia` absoluta descendente:

| Sección | Regla |
|---|---|
| `faltantes` | esperada con `contado < sistema` (incluye `contado = 0` si nunca se escaneó); `diferencia = contado − sistema` (negativa) |
| `sobrantes` | variante del alcance con `contado > sistema` (incluye sistema 0); `diferencia` positiva |
| `fuera_de_alcance` | líneas de variantes que no son del departamento del conteo, con `departamento`; no entran en faltantes ni sobrantes |
| `desconocidos` | `{codigo, contado}` |

`totales`: `esperadas_variantes`, `esperadas_piezas`, `contadas_variantes`, `contadas_piezas`,
`cuadradas_variantes` (contado == sistema > 0), `faltantes_piezas`, `sobrantes_piezas`,
`fuera_de_alcance_piezas`, `desconocidos`. Más `alcance: {sucursal, departamento}`,
`estado`, `generado_en`. Sin `department_id` la sección `fuera_de_alcance` queda vacía.

Al cerrar, el JSON se guarda en `resumen` y `qty_sistema` se congela en cada línea; el reporte
de un conteo cerrado **no** se recalcula aunque el inventario cambie después. Abierto, el mismo
cálculo sirve de avance.

## 6. Pantallas (teléfono primero, kit `components/ui/`)

Rutas nuevas en `App.tsx` (lazy, como `StoreScanner`) y en `ROLE_ROUTES` de `navConfig.ts` para
ADMINISTRADOR y DUEÑO. Ítem de menú `{label: 'Conteo', short: 'CNT', icon: 'fa-list-check',
url: '/inventory/conteos', group: 'hq', sort: 13.6, module: 'inventory'}`, junto al Escáner; la
URL entra en `OCULTAS_BASICO_HQ` (`navPerfilBasico.ts`). Cliente en `frontend/src/api/conteos.ts`.

**`/inventory/conteos` — `pages/inventory/conteos/Conteos.tsx`.** `CabeceraPagina` "Conteo de
inventario" con botón "Nuevo conteo" (`ui/Modal`: sucursal si el usuario no tiene una propia,
recordada como en el Escáner con la clave `atlas_scanner_branch_id`; departamento, lista de la
org con la opción "Toda la tienda"; notas). Lista de conteos (`ListaTarjetas`/`TarjetaFila` en
teléfono, tabla en escritorio): departamento, estado, fecha, avance `312 / 774 piezas`, quién.
Abierto → entra a la sesión; cerrado → al reporte.

**`/inventory/conteos/:id` — `ConteoSesion.tsx`.** Arriba: departamento, barra de avance
(variantes contadas / esperadas) y botón "Cerrar conteo" (`ConfirmDialog` que dice cuántas
esperadas faltan por escanear). Centro: cámara (`createDetector`/`isNativeDetectorAvailable` de
`pages/scanner/barcodeReader.ts`, mismo respaldo ZXing) con campo para teclear o pegar un código
(lector USB). Tras cada lectura buena la detección **se pausa** y se muestra la tarjeta de la
pieza (foto si hay, nombre, marca, talla/color, SKU, "contadas 2 · sistema 3") con dos botones:
"Siguiente" (reanuda la cámara) y "+1 igual" (otra pieza idéntica sin volver a escanear). Sin la
pausa, una pieza quieta frente a la cámara se cuenta una vez por cuadro. `navigator.vibrate(60)`
al contar, `[60, 60, 60]` en desconocido o ambiguo. Abajo: lista de líneas de la sesión (última
primero) con cantidad editable y borrar; buscador por nombre/SKU (`productsApi.posSearch`) que
abre la elección de talla y manda `POST /lines`. Hoja de desconocido y de ambiguo según §4.
Un error de red muestra el mensaje y no toca la lista (la lista siempre se vuelve a leer del
servidor: recargar la página no pierde nada).

**`/inventory/conteos/:id/reporte` — `ConteoReporte.tsx`.** Totales en tarjetas, luego cuatro
secciones plegables (faltantes, sobrantes, fuera de departamento, desconocidos) con filas
`TarjetaFila` en teléfono y tabla en escritorio. En un conteo abierto es el avance y lleva el
botón "Cerrar conteo"; cerrado, muestra fecha de cierre y quién.

Helpers puros con prueba vitest en `pages/inventory/conteos/avance.ts`: `porcentajeAvance`,
`agruparReporte` (ordena y resume las secciones) y `textoDiferencia` ("faltan 3", "sobra 1").

## 7. Permisos y gating

- Backend: módulo `inventory` + rol ADMIN/DUEÑO (403 al resto); org por `organization_id` en
  cada consulta (`scoped_query` o filtro explícito); sucursal validada contra la org.
- Frontend: `ROLE_ROUTES` ADMINISTRADOR/DUEÑO; menú por `module: 'inventory'`; oculto en básico.
- Ligar un código reutiliza `PUT /products/variants/{id}`, que ya aplica sus propias reglas.

## 8. Pruebas

pytest (`tests/test_conteos.py`, fixtures de `conftest.py`): crear conteo y 409 por duplicado
abierto; escaneo por `barcode`, por `sku` en otra mayúscula y por código de empaque; dos
escaneos = una línea con 2; desconocido crea línea con `codigo`; ambiguo no cuenta y lista
candidatos; `POST /lines` suma; `PATCH` a 0 borra; cerrar congela `qty_sistema`, guarda
`resumen` y rechaza el siguiente escaneo con 409; reporte con las cuatro secciones y totales
(faltante sin escanear, faltante parcial, sobrante con sistema 0, fuera de alcance, desconocido);
conteo de otra org 404; CAJERO 403. vitest: los tres helpers de `avance.ts` y la guardia de
`overlaysFueraDelKit.test.ts`/`botonesDelKit.test.ts` (nada nuevo fuera del kit). `tsc` y
`vite build`; las rutas son lazy, el presupuesto de la ruta crítica no cambia.

## 9. Fuera de alcance

Exportar a Excel/PDF; varias personas
en la misma sesión; cola sin red; cajeras/gerentes contando; código alterno de marca sin
reemplazar el interno; corregir la paginación sin `ORDER BY` de `read_products`.
Aplicar los ajustes al kardex ya no está fuera de alcance: ver §11.

## 10. Diagnóstico de Eleven y limpieza

El diagnóstico de solo lectura del 2026-10-22 (fuera del repo, datos del cliente) encontró:
familias del histórico aún activas con existencia, duplicados exactos por nombre+marca+
departamento, variantes vendidas que hoy están en cero, departamentos repetidos
(Hoddies/Hoodies/Sudaderas) y la mayoría de las variantes sin costo. Ninguna de esas limpiezas
se hace antes del conteo: el primer reporte por departamento dice qué existe de verdad y con eso
se decide archivar, fusionar y recostear.

## 11. Fase 2 (2026-10-22, tras la primera prueba en tienda): ajustar la existencia al conteo

El dueño probó el conteo y pidió **que el inventario se ajuste**. Decisiones confirmadas:

| Pregunta | Decisión |
|---|---|
| Cuándo | **Las dos vías**: "Ajustar ahora" por fila mientras se cuenta (conteo abierto) y un botón global "Ajustar existencias al conteo" sobre el reporte cerrado, con filas destildables |
| Tallas con existencia nunca escaneadas | **El dueño elige en el reporte**: vienen destildadas; si las marca bajan a 0 |

Reglas:

- Todo ajuste pasa por el **mismo kardex** que `POST /api/inventory/adjust` (`InventoryMovement` ADJUSTMENT_IN/OUT con `reference="Conteo"` y `notes="Conteo #<id> · <departamento>"`): la lógica de ese handler se extrae a `app.routers.inventory.aplicar_ajuste(...)` y el handler la reutiliza, sin cambiar su comportamiento.
- **Ajuste en piso** (`POST /{id}/lines/{line_id}/ajustar`, conteo ABIERTO): `delta = qty_contada − existencia actual` de la sucursal; si es 0, 409 "ya cuadra"; la línea guarda `ajustada_at`. Tras aplicar, la fila queda `revisado` (sistema == contado).
- **Ajuste al cerrar** (`POST /{id}/apply` con `{variant_ids: [...]}`, conteo CERRADO): se aplica la **diferencia congelada** (`contado − sistema` del `resumen`), no el valor absoluto, para que una venta posterior al cierre no se descuente dos veces. Si la existencia actual + delta quedaría negativa, se recorta a 0 y se anota. Cada fila aplicada queda en `resumen.ajustes` (`variant_id, delta, qty_before, qty_after, movimiento_id, en`) y el conteo guarda `aplicado_at`/`aplicado_por_user_id` la primera vez. Idempotente: una fila ya aplicada se omite; selección vacía = 422. Solo filas de faltantes, sobrantes y fuera de departamento (los desconocidos no tienen variante).
- Reporte: cada fila lleva `ajustada: bool`; totales `ajustadas` y `piezas_ajustadas`. Pantalla: casillas por fila; por defecto marcadas las filas **escaneadas** con diferencia (faltantes parciales y sobrantes), destildadas las nunca escaneadas (`contado = 0`) y las de fuera de departamento; botón "Ajustar existencias (N tallas, −X / +Y piezas)" con `ConfirmDialog`; tras aplicar, las filas muestran "ajustada" y la cabecera "Ajustes aplicados el … por …".
- Permisos: ADMINISTRADOR/DUEÑO, como el resto del módulo.

## 12. Ajuste 2026-10-23: más datos, ficha completa y ancho de pantalla

Pedido tras usar el conteo en tienda: ver más datos por fila, corregir más cosas sin ir al catálogo y aprovechar el ancho de la PC. Solo pantalla; el backend no cambia.

- **Fila de la lista**: nombre de venta; debajo marca · modelo · color; debajo SKU · código de barras (o "sin código"); columnas talla, departamento, precio, sistema y contado. En teléfono la tarjeta lleva lo mismo en subtítulo y datos. El costo **no** se muestra (solo se edita).
- **Escritorio (≥ 1024)**: dos columnas. Izquierda a todo lo ancho: avance, entrada de la pistola, lista. Derecha, panel fijo (`sticky`): última lectura y la ficha de la pieza, que se abre sola con cada lectura salvo que se esté corrigiendo otra; no es un modal, la pistola sigue palomeando. Teléfono y tablet: apilado como antes, ficha en modal. Mismo componente (`FichaProducto`, prop `modo`).
- **Ficha completa**, dos bloques y solo viaja lo que cambió (`ficha.ts::cambiosFicha`): *Producto* (nombre, marca, modelo, descripción, departamento, foto con el cargador del catálogo) → `PUT /api/products/{id}` + `POST /{id}/image`; *Esta talla* (talla, color, código de barras, precio, costo) → `PUT /api/products/variants/{id}`. Un código repetido devuelve el 409 del catálogo tal cual. Tras guardar la fila queda `corregida` y la lista se recarga; si el cambio de departamento saca la pieza de la lista, la ficha se cierra y se avisa.
