# Variantes de color y talla para boutiques — diseño

- **Fecha:** 2026-09-17
- **Estado:** diseño aprobado por el usuario en conversación; plan en
  `docs/superpowers/plans/2026-09-17-variantes-color-talla.md`
- **Cliente que lo pide:** Eleven Fashion (org 17, preset `ATLAS_POS_BOUTIQUE`)
- **Auditoría base:** conversación del 2026-09-17 (backend y frontend), resumida en §2

## 1. Problema

Una boutique vende **prendas con variaciones**: la misma playera en tres colores y
cinco tallas son quince artículos con su propio código de barras y su propia
existencia, pero un solo producto para el dueño. Atlas One modela eso en la base
(`product_variants` cuelga de `products`, y stock, ventas, devoluciones, compras y
traspasos van por `variant_id`), pero **toda la capa de aplicación asume una
variante "Estándar" por producto**. En producción no existe hoy ningún producto
con más de una variante, así que ningún flujo multi-variante se ha ejercitado.

## 2. Hallazgos que dictan el diseño

| # | Hallazgo | Evidencia |
|---|---|---|
| 1 | No hay forma de crear una segunda variante: `extra_variants` se declara y nadie lo lee; no hay endpoint de variantes | `app/modules/products/schemas.py:101`, `router/core.py:327-339` |
| 2 | No hay atributos: solo `variant_name` texto libre | `app/modules/products/models.py:86` |
| 3 | La lectura aplana a `variants[0]` y la relación no tiene `order_by` | `router/_shared.py:95-108`, `models.py:62` |
| 4 | `ProductVariantRead` no expone `variant_name` ni existencia por variante | `schemas.py:53-64` |
| 5 | `SaleItemCreate` descarta `variant_id`; el checkout ya lo contempla | `app/schemas/sales.py:16-21`, `app/routers/sales.py:522-587` |
| 6 | El carrito se indexa por `product_id`; `CartItem` no tiene `variant_id` | `frontend/src/store/posStore.ts:76`, `types/sales.ts:66-82` |
| 7 | Nueve pantallas del frontend toman `variants[0]` (el Scanner ajusta el stock de la primera variante, no la escaneada) | `pages/scanner/StoreScanner.tsx:561` y otros |
| 8 | `barcode` sin unicidad ni por organización | `models.py:85` |
| 9 | Importadores y exportación: una fila = un producto | `scripts/import_products.py:184-207`, `router/import_export.py:110-135` |

## 3. Decisiones

1. **Es una capacidad del preset boutique, no global.** Se crea el módulo
   `variants` ("Variantes color/talla"), incluido en `ATLAS_POS_BOUTIQUE`. La UI
   de matriz y el selector del POS solo aparecen con el módulo activo; los
   endpoints de creación de variantes exigen `require_module("variants")`.
   Las tiendas `ATLAS_POS` no ven nada nuevo.
2. **Las correcciones de lectura son universales pero neutras.** Dejar de
   aplanar a `variants[0]`, exponer `variant_name` y existencia por variante y
   ordenar la relación son cambios de corrección: con datos 1:1 el resultado es
   idéntico al de hoy. Se aplican a todas las organizaciones.
3. **Atributos = dos columnas, no JSON.** `product_variants.color VARCHAR(60)` y
   `product_variants.size VARCHAR(30)`, ambas opcionales. Es lo que la boutique
   necesita, se filtra e indexa sin funciones JSON y la UI puede ofrecer chips.
   `variant_name` se conserva como etiqueta derivada ("Rojo / M") para no tocar
   el ticket, cotizaciones, recetas ni reportes que ya la imprimen.
4. **La unidad de venta es la variante.** `CartItem` lleva `variant_id` y
   `variant_label`; la clave del carrito es el `variant_id`; el POST de venta
   manda `variant_id` y el SKU como respaldo. El backend prioriza `variant_id`.
5. **La respuesta del POS sigue siendo por producto**, con `variants[]` completo
   y `matched_variant_id` cuando la búsqueda empató por código de una variante.
   Con un solo resultado y varias variantes, el POS abre el selector en vez de
   agregar al carrito. Cambiar la unidad de respuesta a variante rompería el
   contrato con 76 vistas; no vale la pena.
6. **Unicidad de código de barras solo aplicativa.** Se valida al crear y
   editar variantes dentro de la organización. No se agrega índice único en la
   base porque Kaory y Ginebra pueden tener duplicados históricos y `create_all`
   fallaría en el arranque.
7. **Sin Alembic.** Los `ALTER TABLE` idempotentes van en `scripts/railway_init.py`
   como el resto del proyecto.
8. **Importación por nombre de producto padre.** Las filas con el mismo
   `Nombre*` y distinta pareja color/talla se agrupan en un producto con N
   variantes. Es la única forma de que un Excel plano cargue una curva de tallas.

## 4. Alcance

**Dentro:** módulo y preset · columnas color/talla · lectura por variante ·
`variant_id` en carrito y venta · CRUD de variantes · matriz color×talla en el
alta y edición · selector de variante en el POS · Scanner sobre la variante
escaneada · inventario por variante en las vistas · ticket de devolución y
reportes con la variante · importador y exportador con color/talla.

**Fuera:** precios distintos por talla desde la UI (el modelo lo permite; la UI
sigue precio por producto, con override por sucursal) · curva de tallas en
compras (la recepción sigue línea por línea) · fotos por variante · atributos
distintos de color y talla (material, etc.).

## 5. Fases y estimación

| Fase | Contenido | Tareas del plan | Estimación |
|---|---|---|---|
| 0 Cimientos | módulo `variants`, columnas, orden, lectura por variante | 1–3 | 1 día |
| 1 Venta correcta | POS y Scanner sobre la variante empatada, `variant_id` en venta y carrito | 4–7 | 2 días |
| 2 Alta de variantes | endpoints de variantes, matriz color×talla en alta y edición | 8–11 | 3 días |
| 3 Operación | selector de variante en POS, inventario por variante, asignar código a una talla | 12–14 | 3 días |
| 4 Trazabilidad y carga | ticket de devolución, reportes, importador y exportador | 15–16 | 2 días |

Total: **11 días de desarrollo** más una semana de uso real en Eleven antes de
ofrecerlo a otra boutique. Cada fase se despliega sola y deja el sistema
operable; después de la fase 1 Eleven ya puede vender con variantes cargadas
por script, y después de la 2 puede capturarlas desde el panel.

## 6. Riesgos

- **Caché de eager-load parcial.** El POS carga `variants` con `contains_eager`
  filtrado por el término de búsqueda, así que la colección puede venir
  incompleta. Por eso el selector de variante recarga el producto con
  `GET /api/products/{id}` antes de mostrar las tallas.
- **Cajas por `cart_key`.** El flujo de cajas construye claves
  `product_id::caja::tier`. Con `variant_id` como clave de pieza, ese flujo no
  cambia; un producto con variantes y cajas queda fuera de alcance.
- **`require_module` no aplica a ADMINISTRADOR/DUEÑO.** Un admin de Ginebra podría
  llamar el endpoint de variantes a mano. La UI no se lo muestra; se documenta.
