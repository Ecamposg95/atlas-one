# Cargar mercancía con IA — diseño

Fecha: 2026-11-14 · Sigue a SP4 (`2026-10-18-sp4-asistente-ia-design.md`), cuya base (tablas `ai_*`,
`organization.ai_instrucciones`, herramientas de lectura del catálogo) ya está en producción. Donde
este documento y el de SP4 difieran, manda este. El chat general de SP4 queda para un sub-proyecto
posterior (decisión del usuario, 2026-11-14).

## 1. Por qué

Hoy las altas de mercancía de una boutique se hacen fuera de la app. El dueño manda un documento y un
operador corre scripts contra la base: arma el plan, pregunta dudas, ensaya, aplica, verifica y pasa la
lista de etiquetas. Se revisaron 17 rondas reales (oct-nov 2026). El tiempo no se va en escribir, sino
en el juicio: si ya existe, si el precio cuadra, si la marca está mal escrita, si se suma o se reemplaza,
en qué departamento va lo que llegó fuera de su lugar. Lo mecánico ya está resuelto por código:
- SKU, código de barras y tallas;
- costo por regla;
- detectar una hoja ya cargada;
- comparar contra el último conteo;
- lista de etiquetas.

La meta: **el dueño sube el documento desde el teléfono o la PC, la app arma el plan con las dudas
numeradas, él las contesta como escribe hoy ("1. es camisola 2. todo lo de 3000 es tipo suéter"), ve el
antes y el después y autoriza.** Sin operador ni scripts.

## 2. Qué entra

| Origen | Formato | Para qué |
|---|---|---|
| Pedimento / factura de importación | PDF, en inglés o chino, a veces escaneado | Mercancía que llega: descripción, cantidad y costo en moneda extranjera; sin precio de venta ni tallas locales |
| Exportación de otro punto de venta | xlsx / csv con columnas de cada sistema | (a) mercancía que otra tienda le manda a la org; (b) una tienda nueva que migra su catálogo |
| Hoja de libreta | xlsx con un renglón por talla | Igual que hoy en Eleven (se cubre como caso de Excel) |

El usuario elige el **propósito** al subir: **Entrada de mercancía** (se suma) o **Migración de
catálogo** (la existencia del archivo es la que hay). El propósito decide si la existencia se suma o
se fija.

## 3. Metas, no metas y anti-metas

**Metas**
- Un documento → un plan revisable con clases EXISTE / SUMA / NUEVO / YA CARGADO / IGNORADO y dudas numeradas.
- Contestar las dudas en texto libre. La IA convierte la respuesta en cambios al plan y los muestra como antes y después.
- Autorizar → se aplica todo en una transacción, con rastro (kardex «Carga #N», auditoría).
- Al terminar, lista de etiquetas de esa carga y filtro **Carga #N** en Etiquetas (cubre también las
  piezas sumadas a variantes existentes, deuda abierta del módulo de etiquetas).
- Sirve a cualquier organización: las reglas de cada tienda viven en su configuración, no en el código.

**No metas (v1)**
- Chat general / consultas de ventas (SP posterior).
- Fotos sueltas de cajas o libreta: misma tubería, se agrega después.
- Cambios masivos de precio a productos existentes fuera de una carga.
- Archivar, borrar o poner en 0.
- Crear departamentos.

**Anti-metas (fracaso aunque "funcione")**
- Escribir algo sin el botón Autorizar de un humano con permiso.
- Un precio que nadie dio: ni inventado ni copiado de otro renglón.
- Cargar dos veces el mismo documento o los mismos renglones.
- Que el modelo escriba en la base o decida SKU/códigos: el modelo **interpreta y propone**, el código
  **valida y escribe**, el humano **confirma** (playbook de altas §9).
- Mandar al proveedor del modelo datos de clientes, usuarios o contraseñas.

## 4. Enfoques considerados

| Enfoque | Qué es | Por qué sí / no |
|---|---|---|
| A. Chat con archivo | El modelo lee todo y propone tarjeta por tarjeta (diseño original de SP4) | Descartado: 200 renglones = 200 tarjetas, y el modelo haría a ojo lo que el código hace exacto (SKU, duplicados, ya cargado) |
| B. Plan sin texto libre | El modelo solo extrae renglones; el código clasifica; dudas con selectores | Confiable, pero contestar 15 dudas con selectores en teléfono es lento |
| **C. B + respuestas en texto libre** | Igual que B; las dudas se contestan como el dueño escribe hoy y la IA las traduce a cambios del plan | **Elegido por el usuario (2026-11-14).** Cada duda conserva también sus opciones como botones |

## 5. Flujo

```
Subir archivo + propósito ──► 1. Extraer (IA) ──► 2. Normalizar y cruzar (código) ──► 3. Plan + dudas
                                                                                         │
            6. Resumen + etiquetas ◄── 5. Aplicar (código, 1 transacción) ◄── Autorizar ◄─┤
                                                                                         │
                                             4. Respuestas en texto ──► IA → cambios ──► antes/después
```

1. **Extraer.** Convierte el documento en renglones crudos: `{descripcion_original, marca, tipo,
   material, color, talla, cantidad, costo_unitario, moneda, precio, observacion, confianza, duda}`.
   - **PDF:** el modelo lee el documento completo (bloque `document`), traduce al español la
     descripción a tipo de prenda y marca, y conserva el texto original.
   - **Excel/CSV:** el código lee las celdas con openpyxl/csv. El modelo solo **mapea encabezados**
     (una llamada con los encabezados y unas 20 filas de muestra) y, si hay columnas de texto libre,
     interpreta descripciones por lotes. Las cantidades y los precios salen de las celdas, nunca del
     modelo.
   - Todo lo dudoso de la lectura se marca en `duda`: renglón ilegible, cantidad poco clara, marca
     incierta.
   - El tipo de cambio se toma del documento si lo declara. Si no lo declara, es una duda: "¿tipo de
     cambio?".
2. **Normalizar y cruzar (código, sin modelo).** Generaliza `hoja_plan.py` del operador:
   - **Tallas** con el mapa de la org (p. ej. S→Ch, L→G, XG→XL).
   - **Agrupación.** Se agrupa por marca + tipo + material + precio. El mismo tipo con otro precio en la
     misma talla da `-2`; en tallas distintas, precio por talla.
   - **Búsqueda en el catálogo** por SKU y por marca + departamento + tipo con SQL, no con el listado
     paginado. Resultado: EXISTE (usa la variante), SUMA (piezas sobre lo que hay), NUEVO (producto o
     variante nueva).
   - **SKU** con `sku_sugerido` y el prefijo que la marca ya usa en la org. Se valida que el prefijo no
     choque con otra marca.
   - **Costo.** El del documento convertido a pesos; si no viene, la regla de la org (§7).
   - **Precio.** Solo si vino en el documento. Si falta, o no cuadra con los precios que la familia ya
     tiene en la org, es una duda.
   - **YA CARGADO.** El mismo archivo (sha256) ya se aplicó, o el renglón coincide con uno aplicado en
     las últimas cargas (14 días). Se quita del plan y se avisa. Solo se fuerza con una respuesta
     explícita.
   - **Último conteo.** El último conteo cerrado del departamento se muestra como contexto.
   - **Dudas por regla.** Las genera el código, no el modelo:
     - marca que no existe o parecida a otra (distancia de edición);
     - producto casi igual (misma marca y tipo, otro precio o material);
     - renglón fuera del departamento de la pestaña o del tipo;
     - precio faltante o fuera de familia;
     - género no evidente;
     - piezas sin costo;
     - tipo de cambio.
3. **Plan + dudas.** Pantalla con contadores por clase, dudas numeradas arriba (cada una con sus
   opciones como botones y la recomendada primero) y la tabla del plan agrupada por producto.
4. **Respuestas en texto.** Una caja de texto. El modelo recibe las dudas abiertas, el plan resumido y la
   respuesta, y devuelve **operaciones estructuradas** sobre el plan:
   - `fijar_campo(renglones|grupo, campo, valor)`
   - `resolver_duda(n, opcion)`
   - `usar_existente(grupo, product_id)`
   - `nuevo_producto(grupo)`
   - `ignorar(renglones)`
   - `cambiar_departamento(grupo, depto)`

   El código valida cada operación (ids del plan, campos permitidos, valores) y recalcula el plan. La
   pantalla enseña el **antes y el después** de lo que cambió: el usuario acepta o deshace la tanda.
   Lo que el modelo no entendió vuelve como "no entendí el punto 4". Los botones de cada duda hacen lo
   mismo sin modelo.
5. **Autorizar.** Botón habilitado solo sin dudas abiertas. Repite el resumen final (productos nuevos,
   piezas que entran, valor a costo) y pide confirmar. Se aplica en **una transacción**:
   - productos y variantes con los servicios de SP1 (`crear_producto`, `crear_variantes`);
   - entradas con `aplicar_ajuste(..., commit=False)` y nota `Carga #N · <archivo>`;
   - en migración, `fijar_existencia`;
   - activación en las sucursales que venden;
   - auditoría `CARGA_APLICADA`.

   Si algo falla, se revierte todo y la carga queda en `error` con el detalle.
6. **Resumen + etiquetas.** Tabla Marca · Producto · SKU · Talla · Código · Piezas · Precio, con las
   piezas que entraron (no el stock total), y botón "Imprimir etiquetas" → `/labels?carga=N`.

## 6. Datos

Tablas nuevas (se crean solas con `create_all`; FKs a UUID = `String(36)`):

- `cargas_mercancia`:
  - id UUID; `folio` entero por org (el #N); org, user;
  - `proposito` entrada|migracion; `estado` leyendo|plan|aplicando|aplicada|error|descartada;
  - `archivo_nombre`, `archivo_sha256`, `archivo_tipo`, `archivo_ruta` (volumen de uploads,
    evidencia);
  - `sucursal_destino_id`; `moneda`, `tipo_cambio`;
  - `totales` JSON; `error` Text; `aplicada_por`, `aplicada_at`;
  - tokens usados.
- `cargas_renglones`:
  - id UUID; carga_id; `orden`; `crudo` JSON (lo extraído, con texto original); `normalizado` JSON;
  - `clase` EXISTE|SUMA|NUEVO|YA_CARGADO|IGNORADO; `grupo` (llave del producto destino);
  - `product_id`/`variant_id` destino (String(36), nullable); `sku`; `cantidad`; `precio`; `costo`;
  - resultado al aplicar (`variant_id` creado, `movement_id`).
- `cargas_dudas`:
  - id; carga_id; `numero`; `tipo`; `texto`; `opciones` JSON; `recomendada`;
  - `renglones` JSON; `estado` abierta|resuelta; `respuesta` (texto u opción); `resuelta_por`.
- `cargas_cambios`: bitácora de cada tanda de cambios (texto del usuario, operaciones validadas,
  antes/después) para deshacer y auditar.

`organization.reglas_carga` (JSON, ALTER idempotente en `railway_init.py`): reglas que el **código**
aplica de forma determinista. La IA no las decide:
- `costo_si_falta`: `preguntar` | `fraccion_precio` (con `fraccion`, p. ej. 0.5);
- `iva` por omisión;
- `sucursal_recibe` (id);
- `activar_en`: `todas_las_que_venden` | lista;
- `mapa_tallas`; `escala_ropa`;
- `ventana_ya_cargado_dias` (14);
- `sumar_por_omision` (true en entrada).

Las convenciones de texto (nombre sin marca, abreviaturas de marca, departamentos por tipo, precios por
familia) siguen en `organization.ai_instrucciones` y van al prompt. **Ningún dato de una tienda vive en
este repo** (es público).

Kardex: los movimientos de la carga llevan `reference = "carga:<id>"` y nota `Carga #N`. Etiquetas
filtra por esa referencia y cuenta como piezas la cantidad que entró (incluye las tallas nuevas, que
hoy nacen con nota «Creación de variante»).

## 7. IA

- **Proveedor:** API de Anthropic con el SDK oficial `anthropic` (Python), no la capa compatible con
  OpenAI de la base de SP4. El cliente actual (`cliente_llm.py`, httpx) se reemplaza o se envuelve
  detrás del mismo protocolo `ClienteLLM` para que la suite siga usando `ClienteFalso`.
  - Modelo `claude-opus-5-5` por variable `AI_MODELO`.
  - Lee PDF (también escaneado) e imágenes de forma nativa y maneja inglés/chino.
  - Datos sin uso para entrenamiento.
  - Variable `ANTHROPIC_API_KEY` en el `.env` del servidor.
- **Salida estructurada** (`output_config.format` con JSON Schema) para la extracción y para las
  operaciones sobre el plan. Nada de texto libre que el código tenga que adivinar.
- **Llamadas por carga:** extracción (1 por PDF; en PDFs largos, por bloques de páginas), mapeo de
  encabezados (1 por Excel) y 1 por cada tanda de respuestas. El código hace lo demás sin modelo.
- **Asíncrono:** la extracción de un PDF largo puede tardar más de un minuto. La subida responde de
  inmediato con la carga en `leyendo`; la pantalla consulta el estado cada pocos segundos. Se corre en
  un hilo de fondo del proceso (como el worker del outbox), con tope de tiempo. Si el proceso se
  reinicia a media lectura, la carga queda en `error` con "Vuelve a intentar".
- **Topes:** se reutiliza `AiUsoDiario` (tokens por org y día, `AI_TOKENS_DIA_ORG`). Tamaño de archivo
  ≤ 20 MB; ≤ 2,000 renglones por carga.
- **Rechazos y fallas del proveedor** (refusal, 429, 5xx) → la carga queda en `error` con un mensaje
  legible. Nunca se aplica nada a medias.

## 8. Permisos y gating

- Módulo `ai` con gate estricto `exigir_modulo_ai` (sin bypass de admin), como en SP4. Hoy SCALE en
  adelante.
- Subir, contestar dudas y descartar: roles de oficina (admin, dueño, gerente).
- **Autorizar: solo admin/dueño.**
- Todo filtra `organization_id`. Los ids que devuelve el modelo se validan contra la carga y la org.

## 9. Pantalla

- Ruta `/cargas` (lista de cargas con folio, archivo, estado, piezas, quién y cuándo) y
  `/cargas/:id` (plan). Entrada en el menú de Inventario y botón "Cargar mercancía" en Productos.
- Subida: arrastrar o elegir archivo (en teléfono abre archivos/cámara de documentos), propósito y
  sucursal que recibe (por omisión la de la regla).
- Plan en teléfono: contadores arriba, dudas como tarjetas numeradas, caja de respuesta fija abajo,
  tabla del plan como `ListaTarjetas` por grupo. En PC, tabla completa. Kit `ui/`, `useEsTelefono`,
  colores por tokens (guardas existentes).
- Antes/después de cada tanda: lista de cambios por grupo con "Deshacer esta tanda".
- Al aplicar: tabla de etiquetas y botón a Etiquetas filtrado por la carga.

## 10. Decisiones tras la revisión (2026-11-14)

**Del usuario**
- **Otro precio en una prenda que ya existe → duda con 3 opciones:**
  - mantener el actual (recomendada);
  - actualizar: se escribe `variant.price` y el costo, se audita el precio anterior y se avisa que hay
    que reimprimir esas etiquetas;
  - producto aparte con `-2`.
- **Costo de un pedimento = costo unitario × tipo de cambio.** No se reparten aranceles, flete, DTA ni IVA
  de importación. Hay un tipo de cambio por moneda dentro de la carga; si el documento no lo declara, es
  una duda por moneda.
- **Marcas nuevas sí, como duda** ("¿crear «Brioni» o es «Brunello Cucinelli»?"). Al aceptarla, la marca se
  crea dentro de la transacción de la carga. **Departamentos nuevos solo en migración**, también como duda.
  En entrada, un departamento que no existe es una duda con los existentes como opciones.
- **Excel de otra tienda: se pregunta en cada carga qué es cada columna de dinero.** Es la primera duda de
  la carga ("La columna «Precio venta» es: nuestro costo / nuestro precio / ignorar"), recomendada según el
  propósito. La regla "un precio que nadie dio" se cumple: el precio solo sale de una columna que el usuario
  asignó o de su respuesta.

**Llamadas mías (corrígelas si no)**
- **Reglas de agrupación y SKU en `reglas_carga`, no en texto libre**, para que sean deterministas:
  - `tipos`: {tipo de prenda → código SKU y departamento};
  - `materiales_aparte` (con `material_normal`);
  - `genero_por_marca` y sufijo de dama;
  - `matriz_por_omision`: completa en 0 | solo lo que hay;
  - `precios_familia`: rangos válidos por tipo/marca, para la duda de "precio fuera de familia".

  La pantalla de Empresa las edita como formulario; `ai_instrucciones` queda para lo que solo interpreta
  el modelo (cómo traducir descripciones, abreviaturas de texto).
- **v1 no reestructura productos existentes.** No renombra SKU ni convierte una variante única sin talla en
  matriz: eso lo hace el script del operador, y cambiar el SKU o el código de algo con etiqueta impresa es
  delicado. Lo que sí hace es **agregar tallas o colores faltantes** a un producto existente (`crear_variantes`).
  Un renglón que solo encaja convirtiendo un producto viejo sale como duda: "usar el existente tal cual
  (suma a su variante única)" o "producto nuevo". La conversión queda para una versión posterior.

## 11. Lo que decide quien construye

- Cómo repartir PDFs largos en bloques y cómo unir renglones partidos entre páginas.
- La heurística exacta de "precio fuera de familia" y de "marca parecida". Debe ser determinista y
  tener pruebas.
- Dónde vive el código (`app/modules/cargas/` recomendado, usando `app/modules/ai/` para el cliente y
  el uso).
- Formato visual de la tabla del plan dentro del kit `ui/`.

## 12. Sale cuando

- Suite verde: pytest, vitest, tsc, build y presupuesto del bundle (`/cargas` en su propio chunk).
- Con `ClienteFalso`, prueba de punta a punta:
  1. Un PDF de muestra produce renglones; el plan clasifica EXISTE/SUMA/NUEVO y genera las dudas
     esperadas.
  2. Una respuesta en texto se convierte en operaciones válidas.
  3. Autorizar crea productos y entradas en una transacción, con kardex `Carga #N`.
  4. Volver a subir el mismo archivo marca YA CARGADO.
  5. Etiquetas filtra por la carga.
  6. Un admin de org sin módulo `ai` recibe 403.
- Prueba de que una falla a media aplicación no deja nada escrito.
- En producción (manual, el usuario):
  1. Llenar `reglas_carga` e `ai_instrucciones` de la org piloto.
  2. Poner `ANTHROPIC_API_KEY`.
  3. Cargar un pedimento real y un Excel real, revisándolos contra lo que el operador habría hecho a
     mano.
