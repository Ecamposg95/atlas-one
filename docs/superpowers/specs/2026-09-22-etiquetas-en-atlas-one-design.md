# Módulo de Etiquetas dentro de Atlas One — diseño

Fecha: 2026-09-22 · Caso guía: Eleven Fashion (org 17), Zebra GX420t a 203 dpi, etiqueta 51 × 25 mm.

## Qué problema resuelve

Hoy, para imprimir etiquetas, la dueña baja un CSV desde Productos, lo abre en la app de
escritorio del agente (`atlas_labels`) y desde ahí elige, ajusta copias e imprime. Son dos
programas y un archivo intermedio que envejece en cuanto alguien cambia un precio.

El agente de impresión (repositorio aparte, <https://github.com/Ecamposg95/Atlas-Print-Agent>)
se queda con **el control de la impresora**. Atlas One se queda con **los datos, la decisión y
la pantalla**: qué se imprime, cuántas copias, cómo se ve.

## Reparto de responsabilidades

| Capa | Responsabilidad |
|---|---|
| Atlas One (backend) | Elegir variantes, calcular copias, componer el ZPL de la etiqueta, entregarlo en base64 |
| Atlas One (frontend) | Pantalla de selección, filtros, copias, vista previa, resumen y confirmación |
| Agente local | Recibir el trabajo y mandarlo en RAW a la cola de la Zebra |

Es exactamente el camino que ya usa el ticket de venta: el backend arma los bytes
(`app/pos_printer.py`), el navegador los manda al agente (`POST https://localhost:9100/print`
con `{printer_name, content_base64}`). Las etiquetas reusan ese transporte sin tocar el agente.

## El ZPL

Se porta el layout ya probado en la Zebra física (`atlas_labels/zpl.py` del repo del agente),
sin cambiarlo, para que lo que salga del papel sea idéntico a lo que la tienda ya validó:

- Lienzo 408 × 200 dots (51 × 25 mm a 203 dpi), margen 12.
- Marca arriba (altura 22), nombre (18), talla/color (15).
- Código de barras centrado a 76 dots de alto 48: `^BEN` si es EAN-13 con checksum válido,
  `^BCN` (Code 128) en cualquier otro caso.
- Abajo: SKU a la izquierda (14) y precio a la derecha (22).
- Texto que no cabe se recorta con `..`; `^` y `~` se neutralizan; `^CI28` para acentos.
- `^PQ{copias}` por etiqueta; un lote es la concatenación de bloques `^XA…^XZ`.

`layout()` devuelve la lista de elementos con coordenadas y es la **única fuente** tanto del ZPL
como de la vista previa, así que la pantalla no puede mentir sobre lo que va a salir.

## Endpoints (`/api/labels`, módulo `labels`)

| Método | Ruta | Para qué |
|---|---|---|
| GET | `/api/labels/candidates` | Variantes imprimibles con sus campos de etiqueta y copias sugeridas. Filtros: `search`, `department_id`, `brand_id`, `gender`, `only_with_stock`, `product_id`. Marca las no imprimibles con su motivo en vez de esconderlas. |
| POST | `/api/labels/preview` | Una variante (o datos sueltos) → elementos del layout + ZPL crudo, para dibujar la etiqueta en pantalla. |
| POST | `/api/labels/jobs` | `items: [{variant_id, copies}]` → `{content_base64, labels, skipped:[{sku, reason}]}`. No imprime: entrega el trabajo. |
| GET | `/api/labels/test` | Etiqueta de prueba en base64, para calibrar la Zebra. |

Reglas de negocio:

- **Copias por omisión = existencia** de la sucursal del usuario (un admin ve la organización
  entera, igual que el CSV de hoy). Existencia 0 → la fila aparece con 0 copias, no se esconde.
- **Sin código de barras → no se imprime** y se reporta en `skipped`. El sistema ya asigna
  EAN-13 interno, así que esto solo pasa con datos a medias.
- **Alcance por sucursal**: se reusa `query_visible_products`, así una cajera solo ve lo suyo.
- **Copias**: entero de 1 a 99 por renglón; el lote entero se topa en 500 etiquetas para que un
  error de dedo no vacíe un rollo.
- Gating por módulo `labels`, rol CAJERO en adelante (quien etiqueta es quien acomoda el piso).

## Pantalla `/labels` — "Etiquetas"

Una sola pantalla, dos zonas: la tabla a la izquierda, la vista previa a la derecha.

- **Filtros**: búsqueda libre, departamento, marca, género y "solo con existencia".
- **Tabla**: SKU, código, marca, nombre, talla, color, precio, existencia y **Etiquetas**
  (copias, editable en la celda). Selección múltiple con casilla.
- **Acciones en lote**: "Usar existencia" y "Poner N a los seleccionados".
- **Vista previa**: dibujo de la etiqueta en SVG a escala, más una pestaña con el ZPL crudo.
- **Imprimir**: elige la cola (las que reporta el agente), muestra el resumen —cuántas
  etiquetas, cuántos renglones se omiten y por qué— y pide confirmación antes de mandar.
- **Etiqueta de prueba** para calibrar antes de gastar rollo.
- Entrada en el menú bajo "Mi tienda", gateada por el módulo `labels`.
- En teléfono la tabla se vuelve tarjetas y la vista previa pasa a una hoja inferior.

## Qué NO entra

- Diseñador de plantillas. Una sola plantilla, la que la tienda ya validó.
- Otros tamaños de etiqueta o impresoras que no sean ZPL.
- Impresión automática al recibir mercancía.
- Tocar el agente: su contrato (`POST /print` con base64) ya sirve tal cual.
