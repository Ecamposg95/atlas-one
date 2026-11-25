# Megaplan: pendientes de Atlas ONE, agente por rol, cobro y planes

Fecha: 2026-11-24. Estado: aprobado en lo general por el dueño; cada frente lleva su plan de tareas antes de construirse.
Sustituye como hoja de ruta al megaplan del 2026-10-14 (SP1 a SP7), del que quedaban abiertos SP4 (asistente), SP5 (responsivo, parcial) y SP7 (documentación).
Gastro tiene plan aparte: [`../plans/2026-11-24-gastro-pendientes.md`](../plans/2026-11-24-gastro-pendientes.md).

## 1. De dónde sale

Revisión de los 54 planes y 45 specs de `docs/superpowers/`, las auditorías (`AUDITORIA-2026-09-22`, `AUDITORIA-CRM-CREDITO`, `RBAC.md §5`, `docs/audits/`), las ramas sin fusionar y el código de `origin/main` (79cb8eb0). Los checkboxes de los planes no se usaron: casi ninguno se marcó. El estado sale del código.

Verificado directamente: `set-support-context` sin autenticación (`app/main.py:347`); los índices `uq_sales_org_client_uuid` y `uq_sale_return_pending_per_sale` existen en producción; producción no tiene `LLM_API_KEY` ni `ANTHROPIC_API_KEY`. Lo demás viene de revisión por lectura y cada frente lo reconfirma al arrancar.

## 2. Decisiones del dueño (2026-11-24)

1. **Orden:** primero cerrar riesgos de seguridad y dinero; después el agente.
2. **Modelos:** el agente debe poder usar varios modelos, incluidos gratuitos. Para arrancar y probar, Claude. Usar modelos gratuitos aunque el proveedor aproveche el contenido está aceptado.
3. **Cajera:** solo consulta con el agente.
4. **Gerente:** las mismas facultades que el administrador, limitadas a su tienda. Confirma sus propios cambios, precios incluidos.
5. **Superadministrador:** elige la organización en un selector antes de preguntar. El agente no adivina la empresa.
6. **Venta del agente:** incluido en planes altos. El cupo no está definido.
7. **WhatsApp:** entra en la fase A5.
8. **Módulos sin construir:** se ocultan hasta que existan.
9. **Gastro:** sigue pendiente, con plan aparte.
10. **Negocio:** preparar el módulo de cobro de la mensualidad y dejar bien definidos presets y planes.

## 3. Frentes y orden

| # | Frente | Tamaño estimado | Depende de |
|---|---|---|---|
| F0 | Cerrar riesgos (seguridad, dinero, servidor) | 1 a 2 semanas | nada |
| F1 | Agente Atlas por rol | 5 a 7 semanas, en fases A0 a A5 | F0 |
| F2 | Presets y planes bien definidos; ocultar lo no construido | 1 a 2 semanas | nada (puede ir en paralelo a F1) |
| F3 | Cobro de suscripciones | 3 a 4 semanas | F2 |
| F4 | Tienda en línea transaccional | 4 a 6 semanas | F3 (comparte pasarela) |
| F5 | Módulos por construir, uno por uno | por módulo | F2 (los destapa al terminar) |
| F6 | Deuda y sueltos | continuo | nada |
| — | Gastro | plan aparte | sin fecha |

Los tamaños son estimaciones gruesas, sin plan de tareas detrás.

Secuencia propuesta: F0 → F1 (A0, A1) con F2 en paralelo → F3 → F1 (A2 a A4) → F4 → F1 (A5) → F5 según demanda.

## 4. F0: cerrar riesgos

El agente lee con los permisos del usuario. Si los permisos tienen huecos, el agente los hereda y los vuelve más fáciles de explotar. Por eso va antes.

Seguridad
- `POST /api/platform/set-support-context` y `clear-support-context`: exigir SUPERADMIN o SUPPORT (`app/main.py:347`).
- `context/switch`: validar que la sucursal sea de la organización del usuario (`app/modules/auth/router.py:141`).
- `/reports/audit/discrepancies` y `/command-center/stats`: filtrar por rol y sucursal (`app/routers/reports.py:88, 477`).
- Traspasos: el cajero no envía a cualquier sucursal sin aprobación (`app/routers/inventory.py:116`).
- Fusionar `fix/fugas-cajera` (conteo ciego en servidor, corte por sesión).
- SUPPORT no puede `bootstrap`, exportar ni asignar administradores (`platform/organizations.py:465, 575, 617`).
- Cookies `secure=True` en producción; login que respete `UserOrganization.is_active`.
- `organization.is_active` corta el acceso (lo necesita F3 para suspender por falta de pago); devoluciones con la sucursal de la venta, no la de quien captura.

Dinero
- `with_for_update` sobre existencias en `create_sale` y en abonos. Probar contra Postgres, no SQLite.
- Pasar los dos índices únicos de dinero a `railway_init.py`.
- Devoluciones: rechazar cantidad ≤ 0 y variante repetida.
- `quotes convert-to-sale`: emitir `SalesDocumentCreated`.

Servidor
- Ventana de mantenimiento: 57 actualizaciones y reinicio (tumba también rmazh y hrflow; avisar).
- Certificado de `rmazh.mx` (sale en los tickets).
- Respaldos fuera del servidor.

## 5. F1: Agente Atlas

### 5.1 Qué hay hoy
- `main`: tablas `ai_*`, cliente LLM compatible con OpenAI (apunta a Gemini), prompt y cinco herramientas de lectura (`buscar_producto`, `consultar_existencias`, `listar_departamentos`, `listar_marcas`, `sugerir_sku`). Sin endpoint de chat ni pantalla; `/ai` dice "Próximamente".
- `feat/cargar-mercancia-ia`: carga desde PDF o Excel con dudas, autorización y etiquetas; cliente de Anthropic, cupo diario (`uso.py`), candado de módulo (`gating.py`). 26 commits detrás de `main`.

### 5.2 Matriz por rol
Un motor, una lista de herramientas por rol. El servidor arma la lista según el rol y la sucursal de la sesión; el modelo no recibe las que no le tocan. Organización y sucursal salen siempre de la sesión, nunca del modelo.

| Rol | Ámbito | Consulta | Cambia |
|---|---|---|---|
| Cajera, vendedor | Su sucursal | Precio de su sucursal; existencia de su sucursal; "hay o no hay" en otras; sus ventas de hoy (`ventas_cajero.py`). Sin costos | Nada |
| Gerente | Su sucursal | Todo lo del administrador, acotado a su tienda: costos, márgenes, ventas, conteos, faltantes | Altas, precios, ajustes y traspasos de su tienda, con su propia confirmación |
| Administrador, dueño | Toda la empresa | Costos, márgenes, valor de inventario, comparativo de sucursales, ventas (`metricas_ventas.py`) | Lo mismo que el gerente en cualquier sucursal, más altas y precios masivos |
| Superadministrador | La organización elegida en el selector | Lo del administrador de esa empresa, más salud, uso y errores de la plataforma | Altas de tienda y soporte, con bitácora |

Gerente y administrador comparten las mismas herramientas; lo único que cambia es el filtro de sucursal que impone el servidor. Lo que hoy es de toda la empresa por naturaleza (catálogo compartido, marcas, departamentos) lo decide el plan de A2: qué edita el gerente cuando el dato no es de una sola tienda.

### 5.3 Superadministrador: selector de organización
- El panel del agente en plataforma abre con un selector de organización, obligatorio. Sin organización elegida no se puede enviar la pregunta.
- La conversación queda atada a esa organización (`ai_conversations.organization_id`). Cambiar de organización abre otra conversación; el historial de una no viaja a la otra.
- El nombre de la organización se ve fijo en la cabecera del chat y en cada propuesta de cambio.
- Opción "Toda la plataforma" en el mismo selector, solo lectura: salud, uso, tiendas sin vender. Nunca permite cambios.

### 5.4 Reglas de seguridad
- Toda escritura es una propuesta (`ai_propuestas`) que una persona confirma en pantalla. El resumen lo arma el servidor, no el modelo. Al confirmar se revalidan rol y sucursal de quien confirma.
- Texto del catálogo (nombres, marcas, notas) entra al modelo delimitado como dato, para que un nombre de producto no pueda dar instrucciones.
- Cada propuesta aplicada va a `PlatformAuditLog`.
- Cupo por organización y por usuario, contado con candado.

### 5.5 Varios modelos
- Una interfaz de proveedor con dos implementaciones: Anthropic (nativa, la de la rama de cargas) y compatible con OpenAI (la de `main`; sirve para Gemini y modelos gratuitos).
- El modelo se elige por tipo de tarea: `consulta` (precio, stock), `captura` (altas, documentos), `analisis` (reportes). Se configura desde plataforma: valor global y excepción por organización.
- Arranque y pruebas: Claude en las tres (`claude-haiku-5-5` para `consulta`; `claude-opus-5-5` para `captura` y `analisis`).
- Modelos gratuitos: permitidos. La pantalla de plataforma indica, por modelo, si el proveedor usa el contenido, para que quede a la vista qué tienda manda datos a dónde.
- Si un modelo falla o agota su cuota, el motor cae al siguiente de la lista de esa tarea.

### 5.6 Dónde aparece
- Botón del agente en la barra de la aplicación, en escritorio y teléfono, para todos los roles con el módulo.
- Dentro de Consultar (`/mobile/query`): la búsqueda acepta una pregunta además de un código.
- En Productos: "Cargar con el agente" (documento, foto o conversación).
- En plataforma: panel con el selector de organización.

### 5.7 Plan comercial
- Módulo `ai` incluido en planes altos. Hoy el código lo pone en SCALE; si entra también en BUSINESS se decide en F2 junto con el cupo.
- Se revierte "IA fuera de cualquier plan" de la rama de cargas.
- El cupo se construye configurable por plan (tokens o mensajes al mes) con un valor provisional alto; la cifra final sale de medir el consumo real en A1.

### 5.8 Fases
- **A0, cimientos:** traer `feat/cargar-mercancia-ia` al día con `main`; interfaz de proveedor única; candado, cupo configurable y bitácora; variables en `docs/DEPLOY.md`.
- **A1, consultas:** endpoint de conversación, matriz por rol, precio por sucursal (`services/precio_sucursal.py`), `consultar_existencias` con `query_visible_products`, chat en pantalla y dentro de Consultar. Sale para cajera, gerente, administrador y dueño. Mide consumo por rol para fijar el cupo.
- **A2, cambios con confirmación:** `proponer_cambio`, ejecutores sobre los servicios de altas (SP1), tarjeta de propuesta; gerente y administrador con las mismas herramientas; fusionar la carga por documento.
- **A3, ventas, reportes y conteos:** `resumen_ventas`, `buscar_ventas`, estado de conteos, valor de inventario.
- **A4, superadministrador:** panel con selector de organización; "Toda la plataforma" en lectura.
- **A5, más entradas y avisos:** WhatsApp para el dueño (resumen diario y preguntas), foto de etiqueta o factura, voz, avisos de stock bajo, productos sin contar y datos atípicos.

## 6. F2: presets y planes bien definidos

### 6.1 Estado actual
Regla vigente (`app/services/plans.py`): permitido = base ∪ preset del giro ∪ crecimiento del plan.

| Plan | Precio | Usuarios | Sucursales | Módulos de crecimiento que promete | Sin construir |
|---|---|---|---|---|---|
| FREE | $0 | 2 | 1 | ninguno | — |
| START | $499 | 3 | 1 | cotizaciones, promociones | promociones |
| PRO | $999 | 10 | 2 | + compras, almacén, logística, facturación | compras (cascarón), facturación (sin código); almacén y logística por verificar |
| BUSINESS | $5,000 | 25 | 5 | + finanzas, RH, comisiones, membresías, portal de cliente | comisiones y membresías (cascarón), portal de cliente (sin código) |
| SCALE | $10,000 | 100 | 20 | + IA | IA (en construcción, F1) |
| ULTRA+ | desde $30,000 | sin tope | sin tope | todo el catálogo | lo anterior |

Presets (`scripts/init_presets_v2.py`): 14 filas, entre ellas dos marcadas "legacy" (Beauty, Gastro) y "Personalizado". Barber, Beauty & Wellness, Health, Restaurant, Bar y Services incluyen `commissions` o `memberships`, que no existen; tres giros dependen de Agenda, que no tiene pantalla.

### 6.2 Qué se hace
1. **Estado por módulo en el catálogo:** cada módulo declara `disponible`, `en_construccion` u `oculto` en un solo lugar (junto a `MODULOS_BASE`). Una prueba guardia impide que una ruta "Próximamente" corresponda a un módulo `disponible`.
2. **Ocultar lo no construido:** los módulos no disponibles no aparecen en el menú, en "Plan y uso", en el upsell, en la activación desde plataforma ni en la descripción de los planes. Las rutas "Próximamente" (`/appointments`, `/commissions`, `/memberships`, `/purchasing`, `/ai`) redirigen al inicio. Si una organización ya lo tenía encendido, sigue encendido en la base y simplemente no se muestra.
3. **Auditar cada módulo de crecimiento:** almacén, logística, finanzas, RH y cotizaciones se revisan contra el código y se clasifican. El resultado es la tabla definitiva de qué incluye cada plan hoy.
4. **Planes:** con esa tabla se decide qué promete cada plan mientras tanto, si `ai` entra en BUSINESS, el cupo del agente por plan y si hay tope de productos por plan (decisión abierta desde octubre).
5. **Presets:** retirar los dos legacy (migrando las organizaciones que los usen), dejar un preset por giro con su lista de módulos disponibles, y marcar como "en preparación" los giros cuyo módulo central no existe (los que dependen de Agenda). Documentar cada preset en `docs/presets/`.
6. **Una sola fuente:** la página de precios, la pantalla "Plan y uso" y la plataforma leen el mismo catálogo; nada escrito a mano en dos lugares.

## 7. F3: cobro de suscripciones

No confundir con CRM Cobranza (`/crm/cobranza`), que es el crédito de las tiendas a sus clientes y ya existe. Este módulo es lo que Atlas le cobra a cada tienda.

Hoy no hay nada: `Plan.precio_mxn` es informativo y el plan se cambia a mano desde plataforma.

Alcance
- **Suscripción por organización:** plan, precio pactado (puede diferir del de lista), día de corte, estado (`al_corriente`, `por_vencer`, `vencida`, `suspendida`, `cortesia`), fecha de inicio y de próxima renovación.
- **Cargos y pagos:** un cargo por periodo; pagos registrados contra el cargo con método y referencia. Historial visible para la tienda y para plataforma.
- **Primera versión con registro manual:** plataforma registra transferencias y depósitos, que es como se cobra hoy. La pasarela entra detrás de una interfaz, igual que los modelos del agente, para no casarse con una.
- **Pasarela (segunda versión):** cargo recurrente con tarjeta, webhooks idempotentes, reintentos. Proveedor por decidir.
- **Avisos:** banner y correo antes del vencimiento y al vencer (reusa `AnnouncementBanner`).
- **Suspensión:** días de gracia configurables; al suspender, la tienda entra en solo lectura y puede pagar. Nunca se borra nada. Depende de que `organization.is_active` corte de verdad (F0).
- **Cambio de plan:** la dueña ve su plan, su uso contra los topes y pide subir o bajar; el prorrateo se define en el plan de tareas.
- **Pantallas:** "Mi plan y pagos" dentro de Configuración (administrador y dueño); "Suscripciones" en plataforma con cartera, vencidos e ingreso mensual real (hoy la métrica es una aproximación).
- **Factura (CFDI):** fuera de la primera versión; el modelo guarda los datos fiscales para emitirla después.

Zona peligrosa: suspender por error deja a una tienda sin vender. La suspensión automática sale apagada y se enciende por organización cuando el registro de pagos esté probado.

## 8. Resto de frentes

**F4, tienda en línea.** Carrito, precios web, pagos (misma interfaz de pasarela que F3), pedidos, envíos, webhooks y bandeja de prospectos (hoy los leads se guardan y nadie los ve en pantalla).

**F5, módulos por construir.** Orden por decidir cuando termine F2: Agenda (backend de 27 endpoints listo; faltan calendario y portal `/book/<slug>`), Compras y proveedores, Comisiones, Membresías, Promociones, Facturación CFDI, Portal de cliente. Cada uno se destapa en el catálogo al terminarse.

**F6, deuda y sueltos.**
- POS por preset, olas 2 a 4: candados sin pase libre de administrador; módulos `bulk_pricing` y `multi_currency`.
- Cobro en dólares (fase B): `USD_CASH`, tipo de cambio por pago, corte en dos monedas.
- Bitácora de impresión de etiquetas; más tamaños y plantillas.
- Control Tower: construir la pantalla o borrar los cinco endpoints.
- Búsqueda semántica en POS: la absorbe el agente en A1.
- Responsivo: 17 pantallas de plataforma; 28 overlays fuera del kit; 24 archivos en `PENDIENTES` de colores; alias `--p-magenta` y `--p-purple`.
- SP7 documentación: verificador de conteos, `CLAUDE.md` al día.
- Rediseño del rol gerente (se alinea con la decisión 4); límite de crédito y vencimientos en cobranza.
- Conteos: exportar, varias personas por sesión, cola sin red.
- Impersonación real (hoy es un stub); 35 pruebas rojas de base.
- Ramas: `feat/rmazh-agregar-sucursal`, `docs/canal-leads`, `feat/login-animacion`, y el trabajo sin commit de `feat/rol-vendedor-movil`.

## 9. Lo que sigue abierto

1. Cupo del agente por plan y qué pasa al agotarse (se corta o se cobra extra). Se fija con el consumo medido en A1.
2. Si `ai` entra en BUSINESS o solo en SCALE.
3. Pasarela para el cobro recurrente y si la primera versión ya debe emitir CFDI.
4. Días de gracia antes de suspender y qué puede hacer una tienda suspendida.
5. Tope de productos por plan.
6. Qué edita el gerente cuando el dato es de toda la empresa (catálogo compartido).
7. Orden de construcción de los módulos de F5.

## 10. Planes de tareas a escribir, en orden

1. `F0-cerrar-riesgos`
2. `F1-A0-cimientos-del-agente`
3. `F2-presets-y-planes`
4. `F1-A1-consultas-por-rol`
5. `F3-cobro-de-suscripciones`
