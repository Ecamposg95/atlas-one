# Mega plan 2026-10: altas de producto, interfaz agéntica, responsivo y docs — diseño maestro

Fecha: 2026-10-14 · Estado: **borrador aprobado para planear**; cada sub-proyecto lleva su propio
spec corto y su plan en `docs/superpowers/plans/`. Caso guía: Eleven Fashion (org 17, ULTRA+),
que captura lotes de decenas de productos con variantes color × talla y es quien pide poder
decir "agrega el siguiente producto…".

## 1. Qué pidió el usuario

1. Auditar el código de **altas** de producto (crear, editar, duplicar, importar, variantes).
2. Actualizar la **documentación** de referencia (`docs/` + `CLAUDE.md`).
3. Revisar que la **interfaz** sea responsiva y congruente (mismo kit en todas las vistas).
4. Respetar la **separación de niveles de cuenta** FREE → START → PRO → BUSINESS → SCALE →
   ULTRA+ ya especificada en `docs/superpowers/specs/2026-09-30-planes-y-topes-design.md` y
   codificada en `app/services/plans.py`. **No se rediseña**: se usa como está.
5. Una **interfaz agéntica** donde el usuario pida en lenguaje natural "agrega el siguiente
   producto …" y el sistema lo dé de alta.

## 2. Hallazgos del levantamiento (2026-10-14, solo lectura)

### 2.1 Altas (backend `app/modules/products/`)

- **No hay capa de servicio.** Toda la lógica vive en los handlers: `create_product`
  (`router/core.py:190-545`, ~356 líneas), `update_product` (`:983-1223`, ~240),
  `duplicate_product` (`:841-976`), `upload_products` (`router/import_export.py:275-822`, ~547).
- **Unicidad de SKU escrita cuatro veces** y distinta cada vez: create exacta → 409
  (`core.py:237-247`); update exacta → **400** (`:1083-1089`); variantes **sin mayúsculas**
  (`variants.py:83`); upload exacta (`import_export.py:385-394`). El comentario de `core.py:236`
  dice "incluyendo soft-deleted" pero la consulta los excluye.
- **Barcode interno EAN-13** se asigna en create, variantes y upload, pero **no en duplicate**
  (`core.py:912` deja `barcode=None`).
- **Bug en duplicate:** copia `variant_name` pero **no `color` ni `size`** (`core.py:909-919`) y
  recorre variantes borradas.
- **Estado por sucursal + stock + movimiento inicial + empaques + escalones** están copiados a
  mano en create (`core.py:421-494`), update (`:1131-1217`), duplicate (`:923-967`),
  `crear_variantes` (`variants.py:222-240`) y upload (`import_export.py` ~600-760).
- **Precio > 0** se valida en create, update y variantes, **no en upload** (`_safe_decimal(…, 0)`,
  `import_export.py:417`): entran productos a $0.
- **Upload** no fija `tax_rate` (`:560-571`), no tiene guard de rol, deja `print()` en `:773`,
  `:792`, `:810` y **traga errores de commit** (puede reportar éxito con la transacción caída).
- **Ningún alta revisa plan ni módulo.** `plans.py` no tiene tope de productos; `require_module`
  solo está en variantes (`variants.py:262`).
- Usuario HQ sin sucursales destino → **no se crea estado por sucursal** y el producto queda
  visible en todas (`core.py:320-322`). Estado de aprobación siempre `'APPROVED'`.
- No existen eventos de producto en `app/core/events.py` (solo `SalesDocumentCreated`).
- Cobertura: ~200 pruebas en 20 archivos, pero ninguna cubre que duplicate conserve color/talla o
  asigne código.

### 2.2 Altas (frontend)

- **Cuatro formularios** de producto: `pages/admin/AdminProductCreate.tsx` (290 líneas),
  `pages/products/ProductForm.tsx` (465), `ProductModal` dentro de `pages/inventory/Products.tsx`
  (`:714-1130`, sin matriz de variantes, crea con `initial_stock: 0`) y `CreateProductMiniModal`
  (`Products.tsx:485-686`) **inalcanzable**.
- Validación y armado del payload **copiados** entre AdminProductCreate (`:135-162`) y
  ProductForm (`:238-268`).
- **No hay configuración de campos por preset:** género/modelo/material se muestran a todos los
  giros (`components/products/ProductCommercialSection.tsx:51-68`, `Products.tsx:908-922`). El
  único interruptor es si el módulo `variants` está encendido.
- `Products.tsx` tiene 1,772 líneas; `api/products.ts` 551.

### 2.3 Responsivo y congruencia

- Ola 1 (`plans/2026-10-01-responsivo-admin-ola-1.md`) está en `main` (T1-T6) pero **sin cerrar**:
  T7 verificación en curso sin reporte, T8 (`utils/rutaInicio.ts:11` sigue mandando al dueño a
  `/mobile/owner`), T9 docs. Las casillas del plan siguen sin marcar.
- Solo 8 páginas usan el kit nuevo (`TarjetaFila`, `ListaTarjetas`, `BarraFiltros`,
  `CabeceraPagina`). Sin ningún prefijo de breakpoint y con tablas: Brands, Departments,
  HQInventory, Inventory, Boxes, Logistics, HR, Seguimiento, Portal. Sin prefijos:
  AdminProductCreate, StoreScanner (818 líneas), PresetHome, Startup. Casi sin: Users, Customers,
  CustomerFormModal, Expenses, Purchases, Quotes, PrinterSettings (1,356 líneas).
- **Dos juegos de componentes paralelos:** `components/ui/Button.tsx` (7 usos) vs
  `components/atlas-one/Button.tsx` (3 páginas), mientras 49 archivos usan la clase cruda
  `dax-btn-primary`. Mismo caso para Badge.
- `ui/Modal.tsx` solo lo usan KDS y ProductsBranchView; **18 overlays** arman su `fixed inset-0`
  a mano y sin `.dax-modal` (Customers, CustomerFormModal, Purchases, Expenses, HR, Boxes,
  Logistics, Quotes, Seguimiento, MovementModal, OpenShiftModal, CashBranchView,
  ProductBranchMatrix, ProductAuditDrawer, VariantPickerModal, PrinterInstallWizard,
  TableFormModal, ConfirmDialog).
- `pages/platform/*` queda fuera (estilos inline + `platform-v2.css`), igual que en la spec de
  responsivo.

### 2.4 Documentación

| Doc | Último commit | Vencido |
|---|---|---|
| `docs/README.md` | 2026-09-22 | "73 tablas" (son 74), "76 vistas" (son 80); no indexa etiquetas ni planes |
| `API_REFERENCE.md` | 2026-10-03 | "3 routers con `require_module`" (son 6); "11 sub-routers" de products (12); "16" de platform (20); el gotcha de `/search` inalcanzable se corrigió el 09-22 |
| `ARCHITECTURE.md` | **2026-07-10** | 73 tablas; dice que cada módulo tiene `services.py` (products, customers, users, tenants no); sin labels, planes ni Cloudinary |
| `FRONTEND_VIEWS.md` | 2026-09-22 | 76 vistas; `ROLE_ROUTES` ya vive en `navConfig.ts:139`; faltan StoreScanner, PrinterSettings por rol, CustomerFormModal; sin nota de ola 1 |
| `RBAC.md` | 2026-09-30 | "3 routers" (6) |
| `ONTOLOGY.md` | 2026-09-22 | sin códigos de barras, boutique, etiquetas ni claves de plan |
| `modules/MODULE_GUIDE.md` | 2026-09-22 | "item en Sidebar.tsx" (es `navConfig.ts`); sin paso "añadir el módulo a un plan" |
| `presets/README.md` | 2026-09-21 | no explica permitido = base ∪ preset ∪ plan |
| `CLAUDE.md` | — | 73 tablas, 76 vistas, 16 sub-routers, "3 routers" |

**Cloudinary** (activo en producción desde 2026-10-14, `app/utils/image_storage.py`) no aparece en
ninguna referencia salvo `docs/infra/deployment-map.md`.

### 2.5 Interfaz agéntica: punto de partida

- **Cero código LLM** en el repo (ni dependencia, ni embeddings, ni voz).
- Existe el gancho completo: módulo `ai` en el catálogo (`scripts/init_presets_v2.py:62`, BETA,
  "Copilotos, predicciones, automatización"), incluido en **SCALE y ULTRA+** (`plans.py`), ruta
  `/ai` con "coming soon" (`App.tsx:380`), entrada de nav (`navConfig.ts:112`), widget "Copiloto
  IA" en `PresetHome.tsx:378` y router stub `app/modules/ai/router.py` (15 líneas, `/api/ai/health`).
- Patrón de UI reutilizable: `components/platform/CommandPalette.tsx` (⌘K, 399 líneas), hoy solo en
  la plataforma superadmin.
- La búsqueda semántica del POS (`specs/2026-04-28-pos-semantic-search-design.md`) nunca se hizo;
  el POS busca con `ILIKE` palabra por palabra (`router/search.py:322-445`).

## 3. Decisiones de diseño

1. **Orden por dependencias:** altas → agente → responsivo → docs. El agente llama al servicio
   de altas, no a los handlers; la ola 2 de responsivo toca justo el formulario de producto, así
   que primero se unifica y luego se hace responsivo; las docs se tocan una sola vez al final
   porque API_REFERENCE y FRONTEND_VIEWS cambian con todo lo anterior.
2. **Planes: no se rediseñan.** Se consumen tal cual: el agente es parte del módulo `ai` (SCALE+),
   y el alta de productos pasa a usar `require_module("catalog")`. Un tope de productos por plan
   queda como decisión abierta (ver §6); no está en el papel de precios y hoy nadie lo pide.
3. **Alcance del agente, primera versión = "Asistente de altas" (opción A, pendiente de
   confirmación del usuario):** solo crea y edita productos y variantes; siempre muestra la ficha
   propuesta y pide confirmación antes de guardar; nunca ejecuta altas sin un "sí" explícito.
   Consultas (ventas, inventario) y captura por foto o voz quedan para versiones posteriores sobre
   el mismo esqueleto.
4. **El agente no inventa datos de dinero:** si falta precio o costo, pregunta; no asume.
5. **Proveedor LLM:** API de Claude con tool use (modelo por defecto `claude-sonnet-5-5` por
   costo/latencia, escalable a `claude-opus-5-5`). Clave en `ANTHROPIC_API_KEY` del `.env` del
   servidor, una sola para la plataforma; costo por org se mide con un contador de tokens por
   organización y día en una tabla nueva. Antes de escribir código leer la skill `claude-api`.
6. **Una sola fuente de verdad para campos por giro:** un `catalogo_de_campos` por preset
   (backend) que consumen el formulario, el importador y el agente. Hoy esa lógica no existe.

## 4. Sub-proyectos

### SP1 · Altas: servicio único de productos (backend + frontend)

**Objetivo:** que crear, editar, duplicar, importar y crear variantes pasen por **una** función de
servicio con helpers compartidos, con las mismas validaciones y la misma respuesta.

Entregables:
- `app/modules/products/services.py`: `crear_producto(db, org_id, user, datos) -> Product`,
  `actualizar_producto`, `duplicar_producto`, `crear_variantes`, más helpers `validar_sku_unico`
  (case-insensitive, 409 siempre, incluye borrados si así se decide), `asignar_barcode_interno`,
  `armar_estado_por_sucursal`, `registrar_stock_inicial`, `armar_escalones`, `armar_empaques`.
- Los handlers quedan en < 40 líneas: parsear, llamar al servicio, serializar.
- `upload_products` usa el mismo servicio fila por fila dentro de una transacción con
  `savepoint`; errores por fila se reportan, el commit no se traga; sin `print()`.
- Corrección de bugs: duplicate conserva color/talla y asigna barcode; upload rechaza precio ≤ 0 y
  fija `tax_rate`; usuario HQ sin sucursales destino → estado por sucursal en todas las que
  venden (o 400, a decidir en el spec del SP).
- `require_module("catalog")` en todo alta; guard de rol en upload.
- Evento `ProductCreated` en `app/core/events.py` (idempotente, por si etiquetas o reportes lo
  quieren después). Opcional; se decide en el spec.
- Frontend: **un solo `ProductForm`** (se eliminan `AdminProductCreate`, `ProductModal` y
  `CreateProductMiniModal`), validación en un helper, campos por preset desde el backend
  (`GET /api/org/capabilities/` o endpoint nuevo `GET /api/products/campos`).
- Pruebas: las ~200 existentes siguen verdes; nuevas para duplicate (color/talla/barcode), upload
  ($0 rechazado, commit fallido reportado), SKU case-insensitive, HQ sin sucursales.

Riesgo principal: `create_product` es la ruta de captura de los cuatro clientes vivos. Se migra
handler por handler, con las pruebas existentes como red, y se despliega en dos pasos (servicio
+ create primero; update/duplicate/upload después).

### SP2 · Interfaz agéntica: asistente de altas (módulo `ai`)

**Objetivo:** en `/ai` (y como panel lateral en Productos), un chat donde el usuario escribe o pega
"Playera Versace negra, Ch a XL, costo 600, venta 1200, 3 piezas en M" y el asistente propone la
ficha completa (nombre de venta, SKU sugerido, departamento, marca, género, matriz color × talla
con existencias), la muestra como tarjeta editable y la guarda **solo al confirmar**.

Entregables:
- Backend `app/modules/ai/`: `router.py` (`POST /api/ai/conversaciones`, `POST
  /api/ai/conversaciones/{id}/mensajes`, SSE o polling para respuestas), `services.py` (bucle de
  tool use con la API de Claude), `tools.py` (herramientas: `buscar_producto`, `listar_departamentos`,
  `listar_marcas`, `sugerir_sku`, `proponer_producto` — devuelve la ficha, no guarda —,
  `crear_producto` — solo se ejecuta tras confirmación del usuario, llama a SP1 —,
  `actualizar_existencias`), `models.py` (conversación, mensaje, uso de tokens por org/día).
- Gating: `require_module("ai")` (SCALE y ULTRA+ por plan; la plataforma puede encenderlo a mano
  en otros, como con cualquier módulo). Sin módulo → 403 con el plan mínimo en el `detail`.
- Guardarraíles: el agente opera con el rol del usuario (misma org, mismas sucursales); toda alta
  pasa por el servicio de SP1 y queda en `PlatformAuditLog` con `source="ai"`; límite diario de
  tokens por org configurable; prompt del sistema con las convenciones de la org (escala de
  tallas, abreviaturas de marca, departamentos) leídas de la base, no hardcodeadas.
- Frontend: página `/ai` con chat + tarjeta de confirmación (reutiliza `ProductForm` en modo
  "revisión"); botón "Asistente" en Productos que abre lo mismo como drawer; el widget "Copiloto
  IA" de `PresetHome` apunta aquí.
- Pruebas: servicio con un cliente LLM falso (fixture que devuelve tool calls deterministas);
  nunca se llama a la API real en la suite.

Decisión de alcance pendiente: **A** (solo altas, recomendada) vs **B** (también consultas) vs
**C** (foto/voz). El esqueleto anterior sirve para las tres.

### SP3 · Responsivo y congruencia (olas 1-cierre y 2)

- **Cerrar ola 1:** T7 (reporte de verificación en móvil real de las 6 vistas), T8 (el dueño
  aterriza en la vista de escritorio; cambiar `rutaInicio.ts` y su test), T9 (nota en
  `FRONTEND_VIEWS.md` y receta en `CLAUDE.md` §5), marcar casillas del plan.
- **Ola 2 = catálogo y personas**, sobre el `ProductForm` unificado de SP1: Products (los 5
  `grid-cols` sin prefijo), AdminCatalog, Brands, Departments, Users, Customers +
  CustomerFormModal, Inventory, HQInventory.
- **Congruencia:** un solo `Button` y un solo `Badge` (decidir `ui/` o `atlas-one/`, migrar el
  otro y las 49 clases crudas con codemod), un solo mecanismo de modal (`ui/Modal` con
  `.dax-modal` por dentro) y migración de los 18 overlays manuales. Lint rule o test que falle si
  aparece un `fixed inset-0` nuevo fuera de `ui/Modal`.
- Ola 3 (resto + gastro + PrinterSettings 1,356 líneas + StoreScanner 818) queda fuera de este
  mega plan salvo que sobre tiempo.

### SP4 · Documentación

Una pasada al final, en un solo PR `docs:`:
- Corregir conteos (74 tablas, 80 vistas, 6 routers con gating, 12/20 sub-routers) en README,
  ARCHITECTURE, API_REFERENCE, RBAC, CLAUDE.md.
- ARCHITECTURE: módulos sin `services.py` (ya no, tras SP1), labels, planes, Cloudinary, módulo
  `ai` y el flujo de tool use.
- API_REFERENCE §Productos reescrita contra el servicio nuevo; §IA nueva.
- FRONTEND_VIEWS: `navConfig.ts`, vistas faltantes, ola 1 y 2, `/ai`.
- MODULE_GUIDE: paso "añadir a un plan en `plans.py`", `navConfig.ts` en vez de Sidebar.
- ONTOLOGY: códigos de barras, boutique, etiquetas, planes, asistente.
- presets/README: permitido = base ∪ preset ∪ plan; BOUTIQUE §4 con "Altas desde".
- `CLAUDE.md` §5: receta "Añadir una herramienta al asistente".

## 5. Orden, tamaño y criterio de salida

| # | Sub-proyecto | Depende de | Tamaño estimado | Sale cuando |
|---|---|---|---|---|
| 1 | SP1 altas | — | 2 planes (backend, frontend) | suite verde, 4 bugs cerrados con prueba, un solo formulario |
| 2 | SP2 agente | SP1 backend | 1 spec + 1 plan | Eleven da de alta un lote real por chat, con confirmación, y queda en auditoría |
| 3 | SP3 responsivo | SP1 frontend | 1 plan (cierre ola 1 + ola 2 + congruencia) | T7-T9 cerrados; 0 overlays fuera de `ui/Modal`; ola 2 verificada en móvil |
| 4 | SP4 docs | 1-3 | 1 PR | conteos y claims verificados con un script `scripts/verificar_docs.py` que compare contra el código |

Cada sub-proyecto: rama `feat/*` o `docs/*`, spec corto en `specs/`, plan en `plans/`, fusión a
`main` solo con permiso explícito (regla de oro #1).

## 6. Decisiones abiertas (el usuario decide)

1. Alcance del agente v1: A / B / C (§3.3). Recomendación: **A**.
2. ¿Tope de productos por plan? No está en el papel de precios. Recomendación: **no** por ahora.
3. Unicidad de SKU: ¿incluir productos borrados (soft-delete)? Recomendación: **sí**, para que
   restaurar nunca choque.
4. Usuario HQ sin sucursales destino al crear: ¿todas las que venden o error? Recomendación:
   todas las que venden.
5. Kit de componentes ganador: `ui/` (más usado) o `atlas-one/` (más completo, diseñado en la
   spec del design system). Recomendación: **`atlas-one/`** como destino, migrando `ui/` hacia él.

## 7. Riesgos

- SP1 toca la ruta de captura de clientes vivos: migración incremental y despliegue en dos pasos.
- Costo del LLM: medir desde el día uno (tokens por org/día) y poner tope.
- El agente puede proponer datos plausibles pero falsos (precio, marca): la confirmación visual
  obligatoria y "no inventar dinero" son el candado; se prueba con un lote real de Eleven antes de
  abrirlo a otras orgs.
- Responsivo sin dispositivo real: T7 exige verificación en teléfono, no solo en el emulador.
