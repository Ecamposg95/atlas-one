# Altas de clientes: organización, usuarios y catálogo

Cómo se da de alta una tienda en Atlas One con lo que de verdad funcionó en producción
(2026-09 a 2026-11). Sirve a dos lectores: la persona o el agente que hace el alta hoy, y el
diseño de las funciones de IA que la van a automatizar (sección 9). Si algo aquí contradice al
código, gana el código: corrige este archivo.

> El repo es público. Este documento no lleva contraseñas, direcciones de servidores ni datos de
> clientes, y los archivos que traen hashes o contraseñas nunca entran al repo.

---

## 1. Reglas que aplican a todo

1. **Ensayo primero, confirmar después.** Todo script de alta corre en ensayo por omisión
   (`--dry-run`, o sin `--ejecutar`) y se confirma solo cuando el ensayo sale limpio. Un ensayo
   real hace todo el trabajo dentro de la transacción y la revierte al final.
2. **Respaldo antes de cada escritura en producción.** `pg_dump | gzip` a
   `/srv/backups/atlas_one_prod_antes_de_<qué>_<fecha>.sql.gz`, y el nombre del respaldo va en el
   reporte al usuario.
3. **Una transacción por carga.** Si un renglón revienta a media corrida, no queda medio catálogo.
   Cuando un servicio confirma por su cuenta (`import_products`, `apply_industry_preset`), el
   envoltorio cambia `db.commit` por `db.flush` y confirma al final.
4. **Idempotencia.** Repetir una carga no duplica: la identidad es el SKU dentro de la
   organización, el UUID en las mudanzas o una marca en `notes` (`[rmazh#id]`, `YA CARGADO`).
5. **Verificar como la cajera, no como el admin.** El admin hace bypass de varias guardas; la prueba
   final es iniciar sesión con la cajera y buscar un producto en `GET /api/products/pos/search`.
6. **Dónde corre.** Los scripts se copian al contenedor de la app (`docker cp`) y se ejecutan con
   `docker exec -w /app -e PYTHONPATH=/app <contenedor> python <script>`, usando los modelos y
   servicios de la app. Los archivos temporales se borran del servidor y del contenedor al terminar.
7. **Contraseñas.** Se entregan al usuario en el chat una sola vez y no se escriben en archivos,
   memoria ni commits. Las exportaciones con hashes bcrypt viven fuera del repo y se borran tras usarse.
8. **Las decisiones de negocio son del dueño.** Plan, existencias reales, umbral de mayoreo,
   nombres o precios dudosos: se preguntan o se toma un valor por defecto y se dice cuál (sección 8).

## 2. Organización

```bash
python scripts/onboard_org.py --name "<Nombre>" --industry ATLAS_POS --admin <usuario> [--plan FREE] [--branch "HQ - <Nombre>"] [--password ...]
```

- Crea la organización, la sucursal matriz con `can_sell=True`, el admin (ADMINISTRADOR) y enciende
  los módulos del preset. Es idempotente. Sin `--password` genera una y la imprime una sola vez.
- **Antes:** confirmar que el nombre no exista (`select id,name from organization`; la tabla es
  singular) ni el usuario.
- **Giro:** `ATLAS_POS` para tiendas de mostrador y novedades; `ATLAS_POS_BOUTIQUE` para ropa con
  talla/color (ver `docs/presets/BOUTIQUE.md`). Válidos: `IndustryType` en el código.
- **Plan:** FREE por omisión. El plan solo lo cambia la plataforma
  (`PUT /api/platform/organizations/{id}`); topes en `app/services/plans.py`. FREE = 2 usuarios
  activos y 1 sucursal que vende: el admin ya ocupa uno.
- **Verificar:** login del admin (`POST /api/auth/login`, form-urlencoded) responde 200, la
  sucursal tiene `can_sell=True` y los módulos del preset están encendidos.
- **Trampa:** una matriz con `can_sell=False` en un negocio de una sola sucursal deja el POS vacío.

## 3. Usuarios

| Caso | Cómo |
|---|---|
| Cajera nueva | `POST /api/users/` con el token del admin de la org: `{"username", "full_name", "role": "CAJERO", "branch_id", "password"}`. Respeta los topes del plan (403 que nombra el plan mínimo). |
| Usuarios que llegan de rmazh / Data X POS | `scripts/import_rmazh_users.py usuarios.json --org N --branch M --dry-run` → real. Copia el hash bcrypt: entran con su contraseña de siempre. |
| Mudanza con historial | Los crea `import_rmazh_org.py`. Llegan **inactivos** si se apagaron en el origen antes de exportar: reactivarlos en Atlas One. |

- Sin nombre ni contraseña dados por el dueño: usuario genérico (`caja_<org>`) y contraseña generada;
  avisar que se puede cambiar.
- Renombrar al admin en vez de crear otro usuario cuando el plan ya está lleno.
- **Verificar:** login de la cajera y búsqueda en el POS con su token.
- Las ventas quedan en la caja (`cash_session_id`) de quien las registra: una venta capturada con el
  admin no aparece en el corte de la cajera.

## 4. Catálogo según de dónde viene

| Origen | Herramienta | Notas |
|---|---|---|
| CSV de Atlas One o hoja armada a mano | `scripts/import_products.py archivo.csv --org N --branch M [--dry-run]` | Columnas: `Nombre*, Categoria, Codigo, Descripcion, Costo unitario, Precio*, Mostrar en el catalogo, Controlar stock, Stock actual, Stock minimo` (+ `Color`, `Talla` para variantes). No crea escalones de precio. |
| Foto de libreta (modelo / piezas / precio) | Transcribir a CSV → `import_products.py` | Nombre = SKU = modelo en mayúsculas; repetidos se suman; sin precio = $0 y oculto del POS (`is_active_pos=False`) hasta que lo den. Enseñar la transcripción antes de cargar. |
| Eleventa (`inventario.xlsx`: Código, Producto, P. Costo, P. Venta, P. Mayoreo, Existencia, Inv. Mínimo/Máximo, Departamento) | CSV intermedio → `import_products.py` + escalón `Mayoreo` en la misma transacción | Ver 4.1. |
| Data X POS (xlsx de inventario) | `scripts/import_datax_export.py` | Escalones con su nombre; existencias como movimiento ADJUSTMENT_IN "Carga inicial". |
| rmazh, solo catálogo y existencias | `scripts/import_rmazh_export.py catalogo.xlsx --org N --branch M --dry-run` | Lista "EXISTENCIAS MAYORES A 500"; `--tope N` recorta relleno. Fijar `branches.folio_inicial` al siguiente folio de rmazh. |
| rmazh, organización con historial | `scripts/export_rmazh_org.py` (en rmazh, solo lectura) → `scripts/import_rmazh_org.py` | Ver CLAUDE.md §5 "Con historial completo". Ventas posteriores al corte: `scripts/fusionar_rmazh_ventas.py`. |
| Prenda por prenda (boutique) | Servicios de `app.modules.products.services` por BD | Convenciones de SKU/nombre en `docs/presets/BOUTIQUE.md`. |

### 4.1 Limpieza de una exportación de Eleventa (lo aprendido)

- **Existencias:** `1E08` (100,000,000) y números como 99,999,9xx significan "no lleva inventario".
  No son conteos.
- **Departamentos:** suelen ser números sin sentido o "- Sin Departamento -". Se infieren por el
  nombre del producto y se le enseña al dueño la lista de los dudosos.
- **Costos:** $0 a $5 son relleno; se cargan en 0 y solo se conservan los que parecen reales.
- **Códigos:** se conservan tal cual como SKU, aunque sean `55555555` o tengan typos: es lo que la
  cajera escanea o teclea.
- **Nombres:** espacios sobrantes, caracteres sueltos (`|`, `,` final) y faltas de ortografía
  evidentes se corrigen; mayúsculas como venían.
- **Mayoreo:** solo si es > 0 y menor que el precio de venta.
- **Repetidos:** mismo nombre con distinto código y precio (sabores, tamaños) se cargan aparte y se
  avisan para que les pongan nombres distintos.

## 5. Existencias, precios y departamentos

- **El checkout rechaza vender con existencia insuficiente** (`create_sale`: "Stock insuficiente").
  Un producto en 0 no se puede vender. Si el origen no llevaba inventario: cargar relleno uniforme
  (p. ej. 1,000) y programar un conteo con escáner (módulo Conteo), o cargar en 0 si el dueño
  prefiere no vender hasta contar.
- **Relleno heredado** (10,000 o 999,999 piezas en rmazh): reportarlo; `--tope` lo recorta.
- **Escalones de precio** (`product_prices`): el backend toma el más barato con
  `min_quantity <= cantidad`, así que un `Mayoreo` con `min_quantity=1` se aplica **siempre**. Poner
  el umbral que diga el dueño (3 por omisión). La cajera puede forzar un escalón a mano en el carrito.
  Un `price_name` que contenga "caja" activa el flujo de cajas (`min_quantity` = piezas por caja).
- **`cost` NULL tumba el POS** (500 en la búsqueda de toda la org): siempre 0 como mínimo.
- **`variant_name` NULL tumba el cobro**: los importadores ponen "Estándar" si no hay color/talla.
- `SessionLocal` usa `autoflush=False`: hacer `db.flush()` antes de consultar lo recién agregado.

## 6. Impresora y agente

- `branches.printer_name` = el nombre de la cola o impresora en la PC de la tienda.
- El agente se descarga desde Configuración → Impresora → "Descargar agente" (instalador por
  sistema; `formato=zip` = modo manual). Acepta `*.atlasone.com.mx` por omisión.
- La prueba es una venta real con la cajera y su ticket impreso.

## 7. Lista de cierre de un alta

- [ ] Respaldo previo tomado y nombrado en el reporte.
- [ ] Login del admin y de la cajera = 200.
- [ ] La cajera encuentra productos en el POS con precio y escalones.
- [ ] Conteos esperados: productos, variantes, existencias, escalones, departamentos.
- [ ] Folio inicial correcto si la tienda ya emitía tickets.
- [ ] Archivos temporales borrados del servidor y del contenedor; exportaciones con hashes borradas.
- [ ] Pendientes para el dueño listados (precios faltantes, duplicados, departamentos dudosos, conteo).

## 8. Qué se pregunta y qué se decide por omisión

| Decisión | Por omisión | Preguntar cuando |
|---|---|---|
| Giro | `ATLAS_POS` | Ropa/calzado con tallas (boutique), restaurante, citas |
| Plan | FREE | Más de 2 usuarios o más de 1 sucursal que vende |
| Usuario/contraseña de la cajera | `caja_<org>` + generada | Siempre se ofrece cambiarlos |
| Existencias sin inventario de origen | **Preguntar**: relleno + conteo, o 0 | Siempre |
| Umbral de mayoreo | **Preguntar** (3 sugerido) | Siempre que haya mayoreo |
| Departamentos | Inferidos por nombre | Se listan los dudosos |
| Productos sin precio | $0 y ocultos del POS | Se listan |
| Cambios de estructura en un catálogo vivo | — | Siempre: mostrar antes/después y esperar el sí |

## 9. Hacia funciones de IA

Cada operación de arriba es candidata a herramienta (*tool use*) para un asistente con la API de
Anthropic. La regla de diseño que sale de estas altas: **el modelo interpreta y propone, el código
valida y escribe, el humano confirma.**

| Operación | Entrada | Lo que hace el modelo | Lo que hace el código | Confirmación humana |
|---|---|---|---|---|
| Crear organización | nombre, giro, plan | Sugerir giro por la descripción del negocio | `onboard_org` | Sí (crea cuenta) |
| Crear usuario | nombre, rol | — | `POST /api/users/` con topes del plan | Sí |
| Leer exportación de otro POS | xlsx/csv | Mapear columnas, detectar relleno, inferir departamentos, corregir nombres, marcar dudas | Validar tipos, SKU únicos, precios > 0 | Revisar el resumen |
| Transcribir foto de libreta | imagen | Visión: modelo/piezas/precio, marcar ilegibles | Mismo CSV que `import_products` | Revisar la transcripción |
| Cargar catálogo | CSV normalizado | — | Ensayo → resumen → carga en una transacción | Sí, tras el ensayo |
| Ajustar existencias / conteo | conteo | Señalar diferencias raras | Movimientos de inventario con referencia | Sí |

- El modelo nunca escribe SQL ni ve contraseñas o hashes; recibe el resumen del ensayo, no la base.
- Las herramientas que escriben devuelven el resumen del ensayo y piden confirmación antes de la
  corrida real; la corrida real es la misma llamada con `confirmar=true`.
- Las respuestas al dueño son cortas: conteos, tabla de dudas y qué falta.
- El módulo `ai` existe en el catálogo de planes (`plans.py`, desde SCALE): ahí se encienden estas
  funciones.
