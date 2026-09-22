# Changelog — preset boutique (2026-09-16 → 2026-09-21)

Bitácora fechada de lo construido para **Eleven Fashion** (org 17) y el preset
`ATLAS_POS_BOUTIQUE`. Es historial, no referencia viva — para el estado actual del
sistema ver [`docs/presets/BOUTIQUE.md`](presets/BOUTIQUE.md),
[`docs/DATA_MODEL.md`](DATA_MODEL.md) y [`docs/API_REFERENCE.md`](API_REFERENCE.md).

Rango: `git log --oneline 959be7d..main` — 86 commits entre el 2026-09-17 y el
2026-09-21 (`959be7d` es el commit donde se desplegó la primera fase de variantes
color/talla, el 2026-09-17 por la mañana; `main` al cerrar esta bitácora está en
`5c73854`, un commit por delante de `a30c112`).

---

## 1. Comisión por pago con tarjeta (2026-09-17, 13 commits)

Diseño: `docs/superpowers/specs/2026-09-17-comision-tarjeta-design.md`. Función
**general** (cualquier organización), apagada por default (`card_surcharge_pct = 0`).

- `745d93b` docs: diseño y plan
- `7bba444` feat: configuración por organización y servicio `card_surcharge.py`
- `92e70bd` feat: el POS cobra la comisión y Empresa la configura
- `c695d7b` feat: `create_sale` cobra la comisión y la congela en la venta
- `48dd30b` test: ruta PENDING→PAID y el 422 nombra la comisión
- `5f40127` feat: ticket, corte de caja y reportes muestran la comisión
- `54495fa` fix: el ticket ya no reporta la comisión como cambio
- `b49c721` fix: el pago mixto sin tarjeta ya no muestra ni pide comisión
- `5c7e0a3` fix: el % se refresca y se recarga tras un 422
- `c49fb71` fix: la cola offline avisa cuando descarta una venta por el %
- `d8913b5` fix: el % se muestra sin ceros de relleno
- `816c33b` docs: el corte explica por qué la comisión no entra en Ventas Totales
- `77a0509` fix: una caída de red ya no borra el % de comisión

**Resultado:** `sales_documents.card_surcharge_pct/amount`, ticket con `COM. TARJETA` y
`TOTAL A PAGAR`, corte con `card_surcharges`, CSV con dos columnas nuevas.
**No** se reintegra en devoluciones (el banco ya se la quedó).

## 2. Variantes color/talla — corrección y auditoría UX tras el despliegue base (2026-09-17, 27 commits)

La primera fase de variantes (módulo `variants`, columnas `color`/`size`) ya estaba en
`main` antes de `959be7d`. Este bloque es la ronda de auditoría UI/UX del mismo día
(3 olas paralelas A/B/C, ver `variantes-color-talla-auditoria.md` en la memoria de
sesión) que cazó bugs reales de uso:

- `2d35d16` fix: marcas y departamentos en orden alfabético en los formularios
- `fbc352e`, `a76c1ec` feat: la primera fila de la matriz es la variante principal (antes quedaba una "Estándar" sin talla junto a las tallas reales)
- `08a3399` fix: guardar precio desde el Scanner escribe la talla que se ve, no la principal
- `7dd6af5` feat: elegir la talla en la ficha cuando el código no empató
- `03a3f6c`, `a8412f8` feat/fix: existencia y precio por talla en la ficha, refrescan tras ajustar
- `ea4ee0e`, `9b5ef31` feat/fix: el selector de talla dice talla/existencia/precio; la talla elegida viaja al carrito
- `9ec3e1b` fix: modales del POS se anuncian como diálogo y cierran con Escape
- `45f7000` fix: los escalones de precio son de la talla principal, no del producto (deuda que sigue abierta — ver §Deuda)
- `f79afaf`, `cd21cfc` fix: cada talla muestra su precio; editar una fila de talla ya no pisa el SKU de la principal
- `44848c8` fix: apagar POS/precio de sucursal aplica a todas las tallas
- `71f2cb0`, `5f2f9cb` feat/fix: el catálogo suma existencia de todas las tallas y se despliega; vocabulario "Tallas", nunca "Estándar"
- `51b8a02` fix: el abanico por talla tolera fallos parciales y el rol del cajero
- `472028c`, `f6ff376`, `3420033`, `096a14c` feat: existencia inicial por talla en el alta; agregar tallas ya no deja una "Estándar" colgando
- `a6981fe`, `f81fd2c` fix: existencia de las hermanas exige sucursal; un solo aviso cuando el backend señala una fila de la matriz
- `baef4f1` fix: el POS muestra el precio que de verdad cobra cada talla
- `b9005eb` fix: "Ajustar" aterriza en la talla, no en un buscador vacío
- `8555b7f` fix: el editor habla de "variantes" cuando la tienda usa colores
- `049cf3b` fix: la matriz no ofrece acciones masivas al cajero

**Datos de Eleven:** 6 playeras con tallas Ch/M/G (+XL en manga corta); stock previo
quedó en Ch.

## 3. Cliente en el POS de escritorio (2026-09-17, 8 commits)

Diseño: `docs/superpowers/specs/2026-09-17-cliente-en-pos-design.md`.

- `022ce6a` docs: diseño y plan
- `2491d54` feat: botón Cliente en el carrito con búsqueda, alta rápida o nombre libre
- `b82a57c` feat: el cobro y la pausa llevan el nombre del cliente
- `9f75b59` feat: la venta guarda el nombre del cliente y el ticket lo imprime
- `8d152df` fix: el botón Cliente funciona con la caja cerrada y el modal se pule
- `e8f7399` fix: 4 ajustes de revisión al nombre del cliente en ventas y tickets
- `6fb19e2` merge `sdd/cli-front` → `sdd/cli-back`
- `3cb7597` fix: **la búsqueda de clientes sí filtra** (mandaba `q`, el backend esperaba `search`) y los tickets pausados muestran al cliente

`CustomerSelector.tsx` (código muerto) se borró; lo reemplaza `CustomerModal`.

## 4. Autoarranque del agente de impresión — Linux y macOS (2026-09-19, 5 commits)

Diseño: `docs/superpowers/specs/2026-09-19-agente-autoarranque-design.md`. Runbook:
`docs/superpowers/runbooks/print-agent-autostart.md`.

- `c727d00` docs: diseño y plan
- `1dd0ac3` feat: autoarranque en Linux portado de Atlas-Rmazh (systemd, instalador, bundle test)
- `70426a5` feat: autoarranque en macOS con launchd (LaunchAgent de usuario, instalador, guarda, bundle, UI)
- `abfdcac` fix: blockers de la revisión + macOS 14 sin colas raw
- `38440d7` fix: vuelta atrás si el servicio no responde; `lpadmin` en macOS y la ruta de Ajustes del Sistema

**Instalado en campo:** MacBook Air M1 de Eleven Fashion, impresora SPRT SP-EP —
`lpadmin -m raw` no funciona en macOS 14+; se resolvió con el driver **Epson 9-Pin
Series** vía Ajustes del Sistema y `lp -o raw` forzado por el agente en cada trabajo.
**Ninguna caja está convertida al autoarranque todavía** (la conversión la hace el
dueño en persona, caja por caja — ver la bitácora vacía al final del runbook).

## 5. PIN de reimpresión por usuario (2026-09-19, 3 commits)

Plan: `docs/superpowers/plans/2026-09-19-pin-reimpresion.md`.

- `9b42847` docs: plan
- `1149484` feat: PIN de reimpresión por usuario, separado de la contraseña
- `279be7f` fix: solo admin/dueño editan usuarios, el PIN no queda huérfano al degradar un rol, validador estricto (4-8 dígitos)

La revisión encontró que `POST/PUT/DELETE /api/users` **no tenía guard de rol**
(cualquier cajero podía cambiar la contraseña del dueño) — corregido en el mismo commit.

## 6. Ticket boutique y códigos de barras (2026-09-19, 13 commits)

Planes: `docs/superpowers/plans/2026-09-19-ticket-boutique.md` y
`docs/superpowers/plans/2026-09-19-codigos-de-barras.md`.

**Ticket:**
- `97fad4a` fix: marca y departamento dejan de ser obligatorios para cajeros y gerentes
- `5d68b49` fix: el pie del ticket ya no lleva el sufijo `rmazh.mx`
- `d8e099d` feat: la impresión de prueba va brandeada Atlas Tech
- `152ffd7` docs: plan del ticket boutique
- `323ec47` feat: secciones boutique — encabezado, redes, términos y proveedor
- `29e725a` feat: captura de términos/redes/proveedor en Empresa
- `7262a8b` feat: enlace con QR, términos de compra y proveedor **apagado por defecto**
- `b7615cf` fix: el sitio web solo acompaña a redes capturadas; tope del QR; symlink fuera del repo

**Códigos de barras:**
- `dd40d80` docs: plan de códigos de barras por talla
- `3ad5042` feat: EAN-13 interno por talla, asignación automática y exportación de etiquetas
- `bbec419` feat: botones "Generar códigos" y "Etiquetas CSV" en Productos
- `4c2a868` fix: asignación masiva sin un `MAX` por variante; duplicados en la importación
- `49dbf6e` fix: el contador se resincroniza con el máximo real si un candidato está ocupado

**Eleven:** ticket con términos (1,067 caracteres), URL `elevenboutique.mx/terminos`,
WhatsApp, web y proveedor encendidos; 81 códigos generados, CSV con 85 filas entregado.

## 7. Ficha de producto boutique (2026-09-21, 9 commits)

Plan: `docs/superpowers/plans/2026-09-21-ficha-producto-boutique.md`.

- `1270d7a` docs: plan
- `e0ed410` feat: género, modelo, material, nombre de venta, SKU sugerido y ticket detallado
- `2f3b8e7` feat: ficha con los 3 campos; nombre de venta en POS; selector de estilo de ticket en Empresa
- `e97e866` fix: ronda 1 de revisión de la ficha boutique
- `395784c` fix: el SKU sugerido distingue palabras del nombre y el género
- `c743d67` fix: la marca "Sin marca" no encabeza el nombre de venta ni el ticket
- `07f54fa` fix: la búsqueda por texto empata cada palabra en nombre, marca, modelo o código
- `41bcfa0` fix: la búsqueda por texto ignora acentos en Postgres
- `5c73854` fix: el renglón congelado con marca solo aplica en el ticket **detallado** (el `compact` no cambia)

**Eleven:** 87 productos renombrados (nombre = prenda, marca en su campo, género,
modelo, material; descripción provisional borrada), marcas Celine y Schiaparelli
creadas, 99 SKU nuevos (4 colisiones numeradas a mano: Balmain/Balenciaga abrevian
igual, `BAL`), código de fábrica de los tenis LV conservado, departamentos Suéteres y
Tenis separados de Playeras y Calzado. `ticket_line_style = detailed` activo en Eleven.

## 8. Responsivo en teléfono y tablet (2026-09-21, 8 commits)

Plan: `docs/superpowers/plans/2026-09-21-responsivo.md`. Auditorías (no versionadas):
`.superpowers/sdd/responsive-audit/{cajera,admin}-findings.md`.

- `007d1a2` fix: la barra inferior móvil respeta los módulos de la organización
- `2f54001` docs: plan responsivo cajera y administrador
- `e379dd8` fix: base responsiva — inputs sin zoom, alturas `dvh`, molde de modales (`.dax-modal`)
- `1b5edfb` fix: venta y cobro completos en teléfono (POS una columna, carrito como hoja inferior)
- `56aa6c0` fix: formularios, tablas y modales usables en teléfono (admin)
- `3db5526` merge `sdd/resp-admin` → `sdd/resp-base`
- `588fe75` fix: el teclado virtual encoge la vista; el título de pantalla se conserva en teléfono
- `a30c112` fix: el anti-zoom es un piso, título legible en teléfono, tres deltas de escritorio

**Por qué importa:** el dueño de Eleven reportó que ni como cajera ni como admin era
usable en teléfono — no se podía completar una venta (carrito `min-w-[420px]`, modal
de cobro sin scroll). **Escritorio ≥1024px verificado byte a byte sin cambios.**

---

## Diferidos y deudas conocidas

Pulido de las notas de sesión y de los specs/planes — lo que quedó fuera a propósito o
sin verificar, agrupado por área. No es una auditoría de código, es lo que las
personas que hicieron el trabajo dejaron anotado.

**Comisión por tarjeta / USD**
- KPIs de plataforma que suman `Payment.amount` incluyen la comisión de tarjeta (no se
  excluye en ningún reporte cross-tenant).
- Fase B de USD (cobrar en dólares: método `USD_CASH`, `Payment.amount_foreign`, corte
  con dólares recibidos) — diseñada en el spec pero **sin implementar**.
- `quotes convert-to-sale` no congela `usd_rate` ni comisión (esa ruta ya tenía huecos
  conocidos: tampoco emite el evento outbox).
- `BANXICO_TOKEN` **no está definido en el VPS**: el modo `auto` de USD queda apagado
  hasta que se configure.
- Venta offline con el % de comisión cambiado a medio camino se descarta con aviso
  (no se reconcilia).

**Variantes / catálogo**
- Escalones de precio (`product_prices`) son **solo de la talla principal** — las
  variantes hermanas venden siempre al precio base, no heredan el escalón por volumen.
- `is_visible` diverge entre el bulk-toggle y el `PATCH` individual.
- `/hq-inventory` hace una query extra por producto (sin `branch_statuses_cache` en
  `reports.py`).
- Inventory/HQ muestran el precio base en la columna Precio (no el `effective_price`
  por variante).
- `dept_map`/`brand_map` con ids revertidos por savepoint en la subida masiva
  (`autoflush=False`).
- Export de catálogo hace N+1 por variante.
- Vocabulario "Estándar" sigue siendo un string mágico en algunos puntos.

**Ficha de producto boutique**
- `import_export.py` (importador Excel) y el alta rápida del cajero **no conocen**
  `gender`/`model`/`material` — solo el formulario completo de admin los captura.
- `GET /api/products/search` es **inalcanzable**: `core.router` monta `/{product_id}`
  antes que `search.router`, así que cualquier ruta de `search.py` queda tapada.
  Preexistente, no introducido por este trabajo, pero sin corregir.
- El estilo de ticket `detailed` gasta 2-4 renglones por prenda (costo aceptado por el
  dueño de Eleven).

**Códigos de barras**
- 2 duplicados preexistentes en prod bloquean poner un índice único a nivel de base
  (org 16 `2024033050038`, org 14 `522`) — sin limpiar.
- El CSV de etiquetas no respeta los filtros de pantalla.
- Productos inactivos se cuentan como faltantes de código pero no se exportan.

**PIN de reimpresión**
- El limitador anti fuerza bruta vive en memoria (3 intentos/15 min) — se pierde al
  redesplegar.
- El panel SUPERADMIN descarta `reprint_pin` en silencio si se manda ahí.
- DUEÑO/GERENTE no ven `/users` en el menú (aunque el backend ya se los permite).

**Agente de impresión**
- Ninguna caja convertida al autoarranque todavía (bitácora vacía en el runbook).
- Rotación de logs de launchd sin implementar; `find` profundo de certificados en
  macOS sin implementar; `--uninstall` en Linux sin implementar; `_es_health` del
  instalador Linux sin implementar.
- **El agente se está moviendo a un repo propio**,
  <https://github.com/Ecamposg95/Atlas-Print-Agent> — a la fecha de esta bitácora
  `GET /api/printer/download-agent` todavía empaqueta desde `tools/print_agent/` en
  este repo; la migración de código y del endpoint queda pendiente.
- Impresión Bluetooth sin agente (investigación 2026-09-17, sin implementar): rutas
  identificadas — Windows emparejando la impresora BT como puerto SPP y siguiendo con
  el agente; Android con la app **RawBT** por intent `rawbt:`; **PUQU Q1** (etiquetadora)
  sin SDK público, ruta operativa = CSV de variantes importado a la app del fabricante.

**Responsivo**
- Cobro en 390px con el teclado abierto en **iOS** (ignora `interactive-widget`) sin
  verificar en dispositivo real.
- Modales abiertos desde la hoja del carrito, sin verificar en dispositivo real.
- Banda del `.dax-modal-footer` en modo oscuro — comportamiento deliberado, pendiente
  de confirmación visual.
- Rotar el teléfono remonta el editor de tallas (se pierde lo no guardado).
- Laptops táctiles ≥768px siguen dependiendo de hover para editar.
- 768px en `/pos` sigue apretado (dos paneles compitiendo por el ancho).

**Auditoría de esquema (2026-09-19, `.superpowers/sdd/db-audit/`, no versionada)**
43 hallazgos sobre el esquema completo (no todos introducidos por el trabajo de
boutique, pero relevantes para el siguiente preset — ver `CLAUDE.md §6` y
`docs/presets/BOUTIQUE.md §8` para lo aplicable). Los tres de mayor impacto:
1. `parked_tickets.status`/`converted_to_sale_id` se escriben con `setattr` sobre
   columnas no mapeadas por el ORM → nunca se persisten (cobro doble de una mesa ya
   pagada, mesa que nunca se libera al cobrar).
2. Tres mecanismos de migración conviven; solo uno corre en el deploy — el índice que
   impide el **cobro duplicado por reintento** (`uq_sales_org_client_uuid`) vive
   únicamente en un script manual sin correr en todos los entornos.
3. `organization_id` nullable en 37 tablas, y ausente en 5 que sí llevan datos de
   inquilino (incluida `cash_movements`, que mueve efectivo).

**Auditoría responsiva (2026-09-21, `.superpowers/sdd/responsive-audit/`, no versionada)**
Informes `cajera-findings.md` y `admin-findings.md` con hallazgo file:line — base de la
sección 8 de este changelog; léelos si se retoma el trabajo de responsivo.
