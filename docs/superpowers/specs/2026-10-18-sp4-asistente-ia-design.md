# SP4 · Asistente IA: altas y consultas por chat — diseño

Fecha: 2026-10-18 · Sub-proyecto 4 del mega plan
(`2026-10-14-mega-plan-altas-docs-responsivo-agente-design.md`, §4 SP4 y §2 principios).
Este documento concreta lo que el mega plan dejó abierto y registra las decisiones que lo
modifican. Donde los dos difieran, manda este.

## 1. Qué construye

Un chat en `/ai` (y como drawer en Productos) donde el usuario escribe o pega texto como
"Playera Versace negra, Ch a XL, costo 600, venta 1200, 3 piezas en M" y el asistente:

1. consulta el catálogo de la organización (departamentos, marcas, productos parecidos, SKU
   sugerido) con herramientas de solo lectura;
2. propone una **ficha completa** (nombre, SKU, departamento, marca, género, modelo, material,
   precio, costo, matriz color × talla con existencias) como **propuesta pendiente**;
3. la pantalla la muestra como tarjeta; el usuario **Confirma**, **Ajusta en formulario** o
   **Descarta**. Nada se guarda sin confirmación explícita;
4. al confirmar, el servidor ejecuta la propuesta con el **servicio de altas de SP1**
   (`crear_producto`, `crear_variantes`, `fijar_existencia`) y deja rastro en
   `PlatformAuditLog`;
5. responde preguntas de solo lectura: existencias por producto/talla/sucursal, resumen de
   ventas de un periodo, búsqueda de ventas por folio/cliente/fecha.

Fuera de alcance (igual que el mega plan): foto, voz, cambios de precio masivos, borrar
productos, mutaciones fuera de las tres propuestas de §4.

## 2. Decisiones que cambian respecto al mega plan

| Tema | Mega plan | Este diseño | Por qué |
|---|---|---|---|
| Proveedor LLM | API de Claude, `ANTHROPIC_API_KEY` | **Cualquier API compatible con OpenAI** (`/chat/completions` con `tools`). Por defecto Gemini en `https://generativelanguage.googleapis.com/v1beta/openai/`, modelo `gemini-3.8-flash`, variables `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`. Sin SDK: `httpx` (ya en requirements). | El usuario pidió un proveedor gratuito (2026-10-18). Gemini Flash tiene nivel gratuito con tool calling; la capa compatible permite cambiar a Groq, Mistral u OpenAI cambiando tres variables. Importante: en el nivel gratuito Google **usa el contenido para mejorar sus productos**; no mandar datos de clientes (el asistente no lee clientes). |
| Respuesta | SSE o polling | **Síncrona**: `POST …/mensajes` devuelve la respuesta completa cuando el bucle termina (tope 8 llamadas a herramientas, 60 s). | Flash responde en segundos; SSE agrega complejidad sin valor en v1. |
| Auditoría `source="ai"` | columna `source` | `PlatformAuditLog` no tiene `source`; se usa `action="AI_PROPUESTA_APLICADA"` (+ `PRODUCT_CREATE_AI` por producto) y `payload.source = "ai"`. | No tocar el modelo de auditoría de la plataforma. |
| Convenciones de la org | "leídas de la base" | Columna nueva `organization.ai_instrucciones` (Text) editable en `/organization` (Empresa) + prompts base por preset en el repo (`app/modules/ai/prompts/`). | La escala de tallas, abreviaturas de marca (MAM, BLC) y departamentos raros son de cada tienda; el dueño las escribe una vez. |
| Gating | `require_module("ai")` | Gate **estricto** `exigir_modulo_ai`: admin y dueño NO lo brincan (`require_module` les hace bypass). 403 con `detail` que nombra el plan mínimo (`plan_minimo_para("ai")`). | El asistente cuesta dinero/cuota; un admin de una org FREE no debe poder usarlo. |
| Tarjeta editable | "reutiliza ProductForm en modo revisión" | Tarjeta de **solo lectura** con resumen + botón "Ajustar en formulario" que abre `FormularioProducto` (modo create) **prellenado** con la propuesta (`prop inicial`). Al guardar desde el formulario la propuesta se marca `aplicada_manual`. | No duplicar el formulario; SP1 ya lo unificó. |

## 3. Arquitectura

```
frontend /ai ──► POST /api/ai/conversaciones            (crea; devuelve id)
         ──► POST /api/ai/conversaciones/{id}/mensajes  (texto) ──► services.responder()
                    │                                                  │ bucle: LLM ⇄ herramientas (≤8)
                    │                                                  │ registra uso (tokens org/día)
                    ◄── {mensaje_asistente, propuestas_pendientes[]} ◄─┘
         ──► POST …/propuestas/{pid}/confirmar  ──► ejecutores (SP1 services) + auditoría
         ──► POST …/propuestas/{pid}/descartar
         ──► POST …/propuestas/{pid}/aplicada-manual  (tras guardar desde el formulario)
         ──► GET  /api/ai/conversaciones  · GET …/{id}  (historial, últimas 20)
```

Backend `app/modules/ai/` (el stub actual se reemplaza):

- `models.py`: `AiConversation` (UUID, org, user, titulo, AuditMixin), `AiMessage` (UUID,
  conversation_id String(36), `rol` user|assistant|tool|system, `contenido` Text,
  `tool_calls` JSON nullable, `tool_call_id` nullable, `tokens_entrada/salida` Integer),
  `AiPropuesta` (UUID, conversation_id, `tipo`, `datos` JSON, `estado`
  pendiente|confirmada|descartada|aplicada_manual|error, `resultado` JSON, `resumen` String,
  `confirmada_por` Integer nullable, `confirmada_at`), `AiUsoDiario` (Integer PK, org, `fecha`
  Date, `tokens_entrada`, `tokens_salida`, `llamadas`; UNIQUE(org, fecha)). FKs a UUID =
  `String(36)` (regla de oro #4). Registro en `app/models/__init__.py`.
- `cliente_llm.py`: `RespuestaLLM(texto, tool_calls: list[LlamadaHerramienta], tokens_entrada,
  tokens_salida)`; protocolo `ClienteLLM.completar(mensajes, herramientas) -> RespuestaLLM`;
  `ClienteOpenAICompatible(base_url, api_key, modelo, timeout=45)` con `httpx.Client` (acepta
  `transport` para pruebas con `httpx.MockTransport`); `ClienteFalso(guion: list[RespuestaLLM])`
  para la suite; `cliente_por_defecto()` lee las variables de entorno y falla con 503
  "Asistente no configurado" si falta `LLM_API_KEY`. Errores del proveedor (429, 5xx, timeout)
  → `ProveedorNoDisponible` → HTTP 503 con `detail` legible; nunca se reintenta más de una vez.
- `prompt.py`: `prompt_del_sistema(db, org, user, preset, campos_producto)` = prompt base del
  preset (`prompts/base.md` + `prompts/boutique.md` si `ATLAS_POS_BOUTIQUE`) + bloque de datos
  de la org (departamentos y marcas con id y nombre, sucursales que venden, sucursal del
  usuario, campos visibles/ocultos de `campos_producto`, fecha de hoy en la zona del negocio) +
  `organization.ai_instrucciones`. Reglas fijas: no inventar precio ni costo (si faltan,
  preguntar); una propuesta por producto; nunca afirmar que algo se guardó si no hubo
  confirmación; responder en español neutro, corto.
- `herramientas.py`: definiciones JSON (formato OpenAI `tools`) + ejecutores
  `ejecutar(nombre, args, ctx)` con `ctx = (db, org_id, user, conversation)`. Lectura:
  `listar_departamentos`, `listar_marcas`, `buscar_producto(q, limite=10)` (usa
  `query_visible_products` → nombre, sku, marca, depto, variantes con color/talla/precio),
  `sugerir_sku(nombre, marca, modelo, color, talla, genero)` (usa `sale_name.sku_sugerido` +
  `codigos.sku_en_uso`), `consultar_existencias(q, sucursal_id?)` (respeta `_resolver_sucursal`:
  cajero/gerente solo su sucursal), `resumen_ventas(desde, hasta, sucursal_id?)` (total, tickets,
  top 10 productos; mismas reglas de sucursal), `buscar_ventas(folio?, cliente?, fecha?)` (hasta
  20 filas: folio, fecha, total, estado, cajero). Propuesta: `proponer_cambio(tipo, datos)`:
  valida con el schema del tipo y las validaciones de SP1 en seco (SKU único, precio > 0,
  departamento/marca de la org, sucursal), guarda `AiPropuesta(pendiente)` y devuelve al modelo
  `{propuesta_id, resumen, avisos[]}`; errores de validación vuelven al modelo como texto para
  que corrija. Toda herramienta filtra `organization_id`.
- `ejecutores.py`: `aplicar(propuesta, db, user)` por tipo, sin commit (lo hace el router):
  - `crear_producto`: `ProductCreate` → `services.productos.crear_producto` (+ `extra_variants`
    con `initial_stock` por talla); auditoría `PRODUCT_CREATE_AI`.
  - `agregar_variantes`: `{product_id, variantes:[{color,talla,sku?,precio?,existencia}],
    sucursal_id?}` → `services.variantes.crear_variantes`.
  - `ajustar_existencias`: `{ajustes:[{variant_id, sucursal_id, existencia_nueva}]}` →
    `services.sucursales.fijar_existencia(referencia="Asistente IA", notas=…)`; cajero/gerente
    solo su sucursal.
  Resultado `{producto_id, sku, variantes:[…]}` se guarda en `propuesta.resultado` y se agrega
  a la conversación como mensaje `tool` ("Propuesta aplicada: …") para que el modelo lo sepa.
- `services.py`: `responder(db, conv, texto, cliente)`: guarda el mensaje del usuario; arma
  `[system] + últimos 30 mensajes`; bucle hasta que el modelo no pida herramientas (tope 8); por
  cada llamada ejecuta y agrega mensaje `tool`; suma tokens a `AiUsoDiario`; si el uso del día
  ya supera `AI_TOKENS_DIA_ORG` (int, por defecto 200000) responde 429 antes de llamar al
  proveedor. Devuelve `{mensaje, propuestas}`.
- `gating.py`: `exigir_modulo_ai` (dependencia): módulo `ai` habilitado en `organization_modules`
  de la org activa, sin bypass por rol; 403 `detail` = "El asistente IA no está incluido en tu
  plan (mínimo SCALE). La plataforma puede activarlo." (plan desde `plan_minimo_para("ai")`).
- `router.py`: endpoints de §3; todos con `Depends(get_current_user)`,
  `get_current_active_organization` y `exigir_modulo_ai`. Schemas Pydantic v2 en `schemas.py`.
- `scripts/railway_init.py`: `("organization", "ai_instrucciones", "ALTER TABLE organization
  ADD COLUMN ai_instrucciones TEXT;")`. Las tablas nuevas las crea `create_all`.

Frontend:

- `src/api/ai.ts`: cliente tipado de los endpoints.
- `src/components/ai/ChatAsistente.tsx`: lista de mensajes, caja de texto (Enter envía,
  Shift+Enter salto), estado "Pensando…", error 503/429 legible; recibe `presentacion:
  'pagina' | 'drawer'`.
- `src/components/ai/TarjetaPropuesta.tsx`: resumen por tipo (producto: nombre, SKU, depto,
  marca, género, precio, costo, tabla color × talla × existencia; variantes; ajustes) +
  botones Confirmar / Ajustar en formulario / Descartar; estados confirmada/descartada en gris.
- `src/components/ai/propuestaAFormulario.ts`: función pura `propuestaAFormulario(datos,
  departments, brands)` → `{ form: ProductFormValue, variantRows: VariantRow[] }`.
- `FormularioProducto`: prop nueva opcional `inicial?: { form: Partial<ProductFormValue>;
  variantRows?: VariantRow[] }` aplicada una vez al montar en modo create (sin cambios en edit).
- `pages/ai/Asistente.tsx` reemplaza `AIComingSoon` en `/ai`; responsiva desde el inicio (kit
  `ui/`, `useEsTelefono`, sin `grid-cols-N` sin prefijo; se suma a `PAGINAS` del guard
  `responsivoOla2.test.ts` como página sin tabla).
- Productos: botón "Asistente" (icono `fa-microchip`, `aria-label`) junto a las acciones que abre
  `ui/Modal size="lg"` con `ChatAsistente presentacion="drawer"`; al crear un producto desde ahí,
  recarga la lista.
- Empresa (`pages/core/Organization.tsx`): textarea "Instrucciones para el asistente IA"
  (`ai_instrucciones`, `OrganizationUpdate`), con ayuda de una línea y enlace a
  `docs/ai/convenciones-altas.md`.
- `PresetHome` widget "Copiloto IA": texto "Altas por chat y consultas de existencias y ventas"
  (quita `beta`), sigue apuntando a `/ai`.

## 4. Propuestas (contrato JSON que ve el modelo)

```json
{"tipo": "crear_producto", "datos": {
  "name": "Playera cuello redondo", "sku": "VER-PLAY-CR-NEG-CH", "department_id": "…", "brand_id": "…",
  "gender": "HOMBRE", "model": null, "material": null, "description": null,
  "price": 1200, "cost": 600, "has_iva": false,
  "color": "Negro", "size": "Ch", "initial_stock": 0, "branch_id": 20,
  "extra_variants": [{"color": "Negro", "size": "M", "initial_stock": 3}, {"color": "Negro", "size": "G"}, {"color": "Negro", "size": "XL"}]
}}
{"tipo": "agregar_variantes", "datos": {"product_id": "…", "sucursal_id": 20,
  "variantes": [{"color": "Negro", "size": "XL", "existencia": 1}]}}
{"tipo": "ajustar_existencias", "datos": {"ajustes": [{"variant_id": "…", "sucursal_id": 20, "existencia_nueva": 3}]}}
```

`crear_producto.datos` es exactamente `ProductCreate` de SP1 (mismos nombres); la validación en
seco reutiliza `validar_sku_unico`, `validar_precio`, `validar_departamento_y_marca` y
`validar_sucursales_de_la_org` sin escribir. El `resumen` humano lo arma el servidor, no el
modelo.

## 5. Guardarraíles

- Confirmación obligatoria: ninguna herramienta escribe; solo el endpoint `confirmar` ejecuta,
  con el usuario autenticado y su rol (cajero: solo su sucursal y los campos que SP1 le exige).
- No inventar dinero: el prompt lo prohíbe y `proponer_cambio` rechaza `price`/`cost` ausentes
  en `crear_producto` (devuelve "falta precio/costo: pregunta al usuario"). `cost = 0` se acepta
  solo si el usuario lo dijo (aviso en la tarjeta).
- Tope diario de tokens por org (`AI_TOKENS_DIA_ORG`) y tope de 8 herramientas por turno; tope
  de 4000 caracteres por mensaje de usuario.
- Aislamiento: cada herramienta recibe `org_id` del contexto, nunca del modelo; `product_id`,
  `variant_id`, `sucursal_id` que no pertenezcan a la org → la herramienta responde "no existe".
- Auditoría: `AI_PROPUESTA_APLICADA` con `{propuesta_id, conversation_id, tipo, resultado,
  source: "ai"}`; `PRODUCT_CREATE_AI` por producto creado (mismo payload que
  `PRODUCT_CREATE_CAJERO`).
- Privacidad: el prompt y las herramientas no exponen clientes ni usuarios (nombres de cajero
  sí en `buscar_ventas`, como la pantalla de ventas). La clave vive solo en el `.env` del
  servidor.
- Suite: nunca llama al proveedor; `ClienteFalso` y `httpx.MockTransport`.

## 6. Documentación que entrega

- `docs/ai/convenciones-altas.md`: lo aprendido dando de alta el catálogo de Eleven (regla de
  nombre, SKU, matriz de tallas, departamentos por tipo, marcas que chocan, un producto por
  pieza en bolsas/zapatos, cada foto es un par, no deduplicar contra el catálogo, precio base
  de referencia, etc.) en dos partes: convenciones generales del preset boutique (van en
  `prompts/boutique.md`) y las de Eleven (texto listo para pegar en `ai_instrucciones`).
- `docs/ai/README.md`: cómo configurar el proveedor (`LLM_*`), cómo activar el módulo `ai` a
  una org desde la plataforma, cuotas gratuitas y el aviso de uso de datos de Google, cómo
  cambiar a otro proveedor compatible.
- `docs/API_REFERENCE.md` (sección `/api/ai`), `docs/FRONTEND_VIEWS.md` (`/ai`),
  `.env.example` (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `AI_TOKENS_DIA_ORG`),
  `docs/DEPLOY.md` (nota de variables nuevas).

## 7. Sale cuando

- Suite verde (pytest + vitest + build + presupuesto del bundle: `/ai` va en su propio chunk,
  la ruta crítica no crece).
- Con `ClienteFalso`: un lote de tres prendas con matriz de tallas se propone, se confirma y
  aparece en `GET /api/products/{id}` con sus variantes, existencias y auditoría.
- En producción (manual, el usuario): activar `ai` a Eleven desde la plataforma, poner
  `LLM_API_KEY` en el `.env`, pegar sus convenciones en Empresa y dar de alta un lote real con
  confirmación. Verificar que un admin de una org FREE recibe 403.
