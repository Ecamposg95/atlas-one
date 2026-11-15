# Cargar mercancía con IA — guía de operación

Para quien opera la plataforma y para el administrador de la tienda. La referencia técnica está en
[`API_REFERENCE.md`](../API_REFERENCE.md) (`/api/cargas`), [`DATA_MODEL.md`](../DATA_MODEL.md)
(`cargas_*`) y [`FRONTEND_VIEWS.md`](../FRONTEND_VIEWS.md) (`/inventory/cargas`). Diseño:
[`2026-11-14-cargar-mercancia-ia-design.md`](../superpowers/specs/2026-11-14-cargar-mercancia-ia-design.md).

## 1. Qué hace

La persona sube un PDF (pedimento, factura) o una hoja xlsx/csv (exportación de otro punto de venta, hoja
de libreta). La app arma un **plan** con cada renglón clasificado (EXISTE, SUMA, NUEVO, YA CARGADO,
IGNORADO) y **dudas numeradas**. Se contestan con botones o escribiendo ("1. es camisola 2. todo lo de
3000 es tipo suéter"), se ve el antes y el después de cada tanda de respuestas y, al **autorizar**, todo se
crea o se suma en una sola transacción. Al terminar sale la lista de etiquetas de esa carga.

El modelo **interpreta y propone**; el código **valida y escribe** (SKU, códigos de barras, costos,
duplicados); la persona **confirma**. Nada se escribe en el catálogo ni en las existencias antes de que
alguien con rol ADMINISTRADOR o DUEÑO pulse Autorizar.

Propósito al subir: **entrada** (las piezas se suman) o **migración** (la existencia del archivo es la que
hay).

**Límites de hoy (léelos antes de migrar una tienda):**

- Una hoja cuya única columna de texto es la **descripción** (lo normal en la exportación de otro punto de
  venta) **todavía no se interpreta sola**: el modelo solo dice qué columna es cuál, no separa marca y
  prenda de una descripción. Cada renglón sin prenda o sin marca queda aparte (no se junta con otros) y
  pregunta "¿Qué prenda es?" / "¿De qué marca es?" (dudas `sin_tipo` y `sin_marca`, se contestan
  escribiendo o con "No lo cargues"). Con cientos de renglones eso es inmanejable.
- Los **SKU y códigos de barras del sistema de origen no se conservan**: la carga calcula SKU propios y
  asigna códigos nuevos; las etiquetas ya impresas de la tienda dejarían de leerse.
- Por eso, **para migrar un catálogo completo sigue vigente el importador existente** (playbook de altas,
  `scripts/import_rmazh_export.py` o la importación de productos). Cargar mercancía en migración sirve
  para hojas que ya traen columnas de marca y prenda.

La tabla del plan enseña, debajo de cada renglón, la descripción original y de dónde salió (`pág. 3`,
`Hoja1!R12`), para ver qué se juntó en cada producto.

## 2. Activar el módulo `ai` en una organización

1. **Plan.** El módulo `ai` entra desde el plan SCALE (`_SCALE = _BUSINESS | {"ai"}` en
   `app/services/plans.py`). En un plan menor, el servidor responde 403 con el plan mínimo.
2. **Encender el módulo.** En `/platform/organizations/{id}` activa el módulo `ai` para la organización
   (tabla `organization_modules`). El gate (`exigir_modulo_ai`) es estricto: ADMINISTRADOR/DUEÑO tampoco
   lo saltan.
3. **Clave en el servidor.** `ANTHROPIC_API_KEY` en el `.env` del VPS (ver §6). Sin clave, subir un archivo
   responde 503 "IA no configurada: falta ANTHROPIC_API_KEY en el servidor." y **no se crea la carga**
   (contestar por escrito y "Volver a intentar" responden igual).
4. Con el módulo encendido aparece "Cargar mercancía" en el menú de Inventario (`/inventory/cargas`) y la
   sección "Reglas de carga" en Empresa (`/organization`).

## 3. Llenar las reglas y las instrucciones (Empresa)

Hay dos lugares, con funciones distintas:

- **Reglas de carga** (`organization.reglas_carga`, JSON): las aplica el **código** de forma determinista,
  la IA no las decide. Se editan en Empresa → "Reglas de carga". Campos:
  - `costo_si_falta`: `preguntar` o `fraccion_precio` (con `fraccion`, por omisión 0.5 = costo es esa
    fracción del precio; más de 0 y a lo más 1);
  - `iva` (por omisión no);
  - `sucursal_recibe`: sucursal que recibe la mercancía por omisión;
  - `activar_en`: `todas_las_que_venden` o `sucursal_recibe`;
  - `mapa_tallas` (p. ej. `S` → `Ch`) y `escala_ropa` (orden de las tallas);
  - `tipos`: por tipo de prenda, su `codigo_sku` y su `departamento`. El SKU de un producto nuevo es
    `PREFIJO-CODIGO[-MAT][-DAMA][-N]`: el prefijo es el que ya usan los SKU de la marca; una marca sin SKU
    (nueva) lo deriva como el SKU sugerido (iniciales o 3 letras) y, si ese prefijo ya es de otra marca, le
    añade un dígito (`DN`, `DN2`). Si el SKU calculado ya existe en la tienda (incluso archivado) o lo
    calculó otro producto de la misma carga, toma `-2`, `-3`…: la carga nunca falla al aplicar por SKU
    repetido;
  - `materiales_aparte` y `material_normal`: materiales que separan un producto de otro;
  - `genero_por_marca`, `genero_por_omision` y `sufijo_dama`;
  - `matriz_por_omision`: `completa` (todas las tallas en 0) o `solo_lo_que_hay`;
  - `precios_familia`: precios que ya maneja cada tipo (y marca); un precio fuera de ellos es una duda;
  - `ventana_ya_cargado_dias` (14, entre 0 y 90): cuánto atrás se busca un renglón ya aplicado. Un renglón
    sale `YA_CARGADO` si el archivo es idéntico (sha256) a una carga aplicada, o si su SKU y cantidad
    coinciden con una entrada de otra carga **en la misma sucursal que recibe** dentro de la ventana. Nunca
    se quita en silencio: hay una pregunta `ya_cargado` por carga previa ("N renglones coinciden con la
    Carga #M (fecha). ¿Los salto o los cargo de todos modos?"); "saltar" (recomendada) los deja fuera y
    "cargar" los fuerza (`_usuario.forzar`) y entran como cualquier otro.
  Un valor inválido se rechaza al guardar con el campo señalado.
- **Instrucciones para la IA** (`organization.ai_instrucciones`, texto libre, misma pantalla): convenciones
  de redacción que no caben en una regla (cómo se escribe el nombre sin la marca, abreviaturas de marca,
  etc.). Van al prompt como contexto; no sustituyen a las reglas.

No pongas en las instrucciones datos que no quieras que vea el proveedor (ver §4).

**Preguntas que salen de lo leído** (además de las de las reglas):

- `moneda` (solo PDF): el modelo debe dar la moneda del costo de cada renglón. Si un renglón trae costo sin
  moneda y el documento declara **una sola** moneda, la hereda; si declara varias (o ninguna), hay una
  pregunta por carga ("N renglones traen costo pero no dicen en qué moneda está") con cada moneda declarada
  y MXN. Mientras no se conteste, ese costo no se calcula: nunca se asume pesos. En un Excel/CSV, un
  costo sin moneda es en pesos.
- Precio: solo se pregunta (`precio_faltante`, `precio_fuera_familia`) para lo que se da de alta
  (producto o talla nueva). Lo que ya existe suma piezas y conserva su precio; solo si el renglón trae un
  precio distinto sale `precio_distinto_existente`. Un pedimento (sin precio de venta) no pregunta precio
  de lo que ya está en el catálogo.
- `ya_cargado`: ver `ventana_ya_cargado_dias` arriba.

## 4. Qué ve el proveedor (Anthropic)

| Llamada | Qué se envía |
|---|---|
| Lectura de un PDF | El documento, en bloques de 15 páginas, y las instrucciones de la org |
| Lectura de una hoja | Los encabezados y hasta 20 filas de muestra. Las cantidades y los precios los lee el código de las celdas, no el modelo |
| Respuesta escrita | Las dudas abiertas (número, texto, opciones), un resumen del plan **por grupo** (marca, tipo, tallas, cantidades, precios) y el texto que escribió la persona |

**Nunca** se envían clientes, usuarios, contraseñas, ventas ni existencias de otras tiendas. Los botones de
cada duda se resuelven sin modelo. Un precio solo sale de una celda que la persona asignó, del PDF o de lo
que escribió; el código descarta una operación del modelo que meta un monto que nadie escribió.

El archivo original se guarda en la base (`cargas_archivos`) como evidencia.

## 5. Costo aproximado por carga

No hay una cifra fija; depende de lo que se sube:

- **PDF:** una llamada por cada bloque de 15 páginas. Más páginas, más llamadas (y los escaneados pesan
  más que los de texto).
- **Hoja xlsx/csv:** una llamada para mapear los encabezados, sin importar cuántos renglones tenga.
- **Respuestas:** una llamada por cada respuesta escrita. Contestar con los botones no cuesta.
- **Tope diario:** cada organización tiene un máximo de tokens (entrada + salida) por día, tabla
  `ai_uso_diario`, variable `AI_TOKENS_DIA_ORG` (por omisión 200 000). Al alcanzarlo el servidor responde
  429 "Se alcanzó el límite diario de uso de IA de tu organización. Intenta mañana." Cada carga guarda los
  tokens que gastó (`tokens_entrada`, `tokens_salida`) para revisar el consumo.
- Límites del archivo: 20 MB y 2 000 renglones por carga.

Para consultar el precio vigente, usa la lista del proveedor; este documento no lo fija.

## 6. Variables de entorno

| Variable | Para qué | Por omisión |
|---|---|---|
| `ANTHROPIC_API_KEY` | Clave del proveedor. Sin ella subir, contestar por escrito y reintentar responden 503 y no se crea carga | vacía |
| `AI_MODELO` | Modelo que lee y traduce las respuestas | `claude-opus-5-5` |
| `AI_TOKENS_DIA_ORG` | Tope de tokens por organización y día | `200000` |
| `AI_TIMEOUT_SEG` | Tope en segundos de cada llamada al proveedor (un bloque de 15 páginas, un mapa de columnas, una respuesta escrita); el SDK reintenta una sola vez | `300` |
| `CARGAS_PROCESO_EN_LINEA` | Con `1`, la lectura corre en el mismo hilo de la petición en vez de uno de fondo. Solo para pruebas | sin definir (hilo de fondo) |

Se capturan en el `env_file:` del `docker-compose.yml` del servidor ([`DEPLOY.md §6`](../DEPLOY.md)).
Tras cambiar el `.env`, recrea el contenedor.

## 7. Leer una carga en `error`

El estado `error` guarda en `cargas_mercancia.error` una frase legible que la pantalla muestra. Casos
frecuentes:

| Mensaje | Causa | Qué hacer |
|---|---|---|
| "IA no configurada…" (503 al subir, sin carga) | Falta `ANTHROPIC_API_KEY` | Capturarla y recrear el contenedor; luego subir de nuevo |
| Límite diario | Se alcanzó `AI_TOKENS_DIA_ORG` | Esperar al día siguiente o subir el tope |
| Falla del proveedor (rechazo, 429, 5xx) | Lado del proveedor | Volver a intentar en unos minutos |
| Reinicio a media lectura | El proceso se reinició mientras leía, o la lectura dejó de avanzar 10 minutos | Volver a intentar |
| Falla al aplicar | Una validación o la base rechazó algo; **se revirtió todo** | Corregir lo indicado y Volver a intentar |

**"Volver a intentar"** (`POST /api/cargas/{id}/reintentar`) depende de dónde falló:

- si falló la **lectura**, vuelve a leer el archivo guardado desde cero;
- si falló la **aplicación**, la carga regresa al **plan** con sus respuestas intactas, para revisar y
  autorizar otra vez.

Nunca queda nada a medias: la aplicación es una sola transacción. Una carga `descartada` o `aplicada` ya
no se reintenta, y una carga que **alguna vez se aplicó** (`aplicada_at` puesto) tampoco vuelve a leerse ni
a revisión aunque aparezca en `error` (409): eso metería las piezas dos veces. Una carga en `error` también
puede descartarse.

**Lecturas largas.** La lectura de fondo marca su avance (`updated_at`) tras cada bloque de 15 páginas del
PDF y tras mapear cada pestaña del Excel, así que la recuperación de cargas colgadas (10 minutos sin
moverse) no toca una lectura viva. Cada subida y cada "Volver a intentar" ponen un intento nuevo
(`cargas_mercancia.intento`, uuid): si al terminar la carga ya no está en `leyendo` o su intento cambió,
el hilo descarta lo leído y no la toca (los tokens gastados sí se cuentan).

## 8. Rastro de lo aplicado

- **Kardex:** cada movimiento de la carga lleva `reference = "carga:<id>"` y
  `notes = "Carga #<folio> · <archivo>"`. Para auditar: `inventory_movements` con esa `reference`.
- **Auditoría:** evento `CARGA_APLICADA`; `aplicada_por` y `aplicada_at` en la carga.
- **Etiquetas:** `/labels?carga=<id>` (API: `GET /api/labels/candidates?carga_id=`) lista solo las
  variantes que recibieron piezas de esa carga y trae en `piezas_carga` lo que entró; sirve también para
  piezas sumadas a variantes que ya existían.
- Si la carga cambió un precio existente (respuesta "actualizar"), se audita el precio anterior y hay que
  reimprimir esas etiquetas.
