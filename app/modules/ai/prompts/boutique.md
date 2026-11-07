### Ficha
- **El nombre es la prenda, no la marca.** `name` = tipo de prenda + rasgo que la distingue
  ("Playera cuello redondo", "Camisa seda manga larga", "Tenis Trainer"). La marca va en
  `brand_id`, nunca repetida en el nombre. El nombre de venta ("Marca · Nombre modelo · Talla")
  lo arma el sistema.
- **La manga, el corte y el largo van en el nombre**, no en `model`: "Camisa manga corta",
  "Pantalón mezclilla recto".
- **`model`** = colección, línea o seña del dueño ("Dior Oblique", "GG Supreme", "Métiers d'art
  2026 AP5294", "De piedras"). **`material`** solo si se sabe (seda, mezclilla, piel, rafia).
- **El nombre NO lleva talla ni color.** Eso vive en las variantes.
- **La descripción guarda el texto original** tal como llegó (etiqueta, código de fábrica,
  referencia de caja, mensaje del dueño). Es la evidencia para corregir después.
- **Género:** `HOMBRE`, `MUJER`, `UNISEX`, `NINO`. Todo producto lleva género; si no es
  evidente, preguntar. En zapatos manda la carpeta/caja de origen, no la etiqueta "MAN/WOMAN"
  (es código de fábrica).

### SKU
- Convención `MARCA-PRENDA[-INICIALES]-MODELO[-MUJ|NIN]-COLOR-TALLA`, solo `[A-Z0-9-]`. La
  genera `sku_sugerido` (`GET /api/products/sku-suggest`); el asistente la pide con la
  herramienta `sugerir_sku` y revisa que esté libre.
- Marca: iniciales si tiene 2+ palabras, 3 letras si una. **Antes de usar un prefijo, revisar que
  ninguna otra marca lo use ya** (buscar SKU que empiecen igual). Las abreviaturas que la tienda
  ya usa vienen en sus instrucciones y mandan sobre esta regla. SM = sin marca.
- Prenda: 4 letras (PLAY, CAMI, PANT, SUET, CHAM, TENIS, BOTA, ZAPAT, BOLS). **Camisola = CAMS**
  (distinta de camisa), bermuda = BERM, traje de baño = TRAJ-B.
- Variantes hermanas: si el SKU principal ya trae talla, **mandar `sku` explícito** en cada
  hermana; si no, el generador produce `CH-PLAY-EP-CH-XL`.
- Talla tal cual sin signos ("26.5" → "265"). Zapatos: `PREFIJO-TENIS|BOTA-MODELO6-COLOR3[-COLOR3]-TALLA`.
- Cuando el SKU sugerido ya existe para una pieza distinta, numerar (`-2`), no inventar otra
  abreviatura.

### Matriz color × talla y existencias
- **Un producto por modelo; una variante por combinación color × talla.** La variante
  principal es la primera combinación real (la que tiene código impreso y existencia), nunca
  una "Estándar" sin talla.
- Escala de ropa boutique: **Ch / M / G / XL** ("XG" se guarda XL). Tallas
  numéricas en pantalón y calzado (40, 41, 42…; "US 10" o "UK 7" son marcadores por corregir).
- **La existencia va en la talla que se contó**, no toda en la principal. "3 piezas en M" =
  `extra_variants[M].initial_stock = 3`; el resto de tallas nace en 0 para que aparezca en el POS.
- Mismo modelo en varios colores = **un producto con variantes por color** (un mismo bolso
  en tres colores). Precio distinto por variante sí se puede.
- Bolsas, maletas, relojes y piezas únicas: **un producto por pieza** (cada una tiene su
  referencia); no agruparlas aunque sean del mismo modelo si el dueño las dictó por separado.
- Zapatos por foto: si una caja parece idéntica a una ya cargada, **preguntar si es otro par**,
  salvo que las instrucciones de la tienda lo resuelvan. Si es otro par y la variante ya existe,
  se suma 1 con un ajuste "Compra".
- En notas manuscritas: **guion entre colores = pares distintos** ("Silver-Blue; Pink-Beige" con
  cantidad 8 → 8 pares); **diagonal = un color combinado** ("Blue/White").
- Filas tachadas no se cuentan. Sin nota de conteo = 1 pieza con la talla de la caja.

### Departamentos por tipo de pieza
- Tenis → **Tenis**; botas y zapatos de vestir → **Calzado**; mochilas, maletas, maletines,
  neceser y vanities → **Bolsas**; carteras, tarjeteros y relojeras → **Accesorios**; joyería →
  **Joyería** (no Accesorios); bermudas → **Pantalones**; suéteres jersey/premium → **Suéteres**
  aunque el dueño los llame playeras; chamarra, bomber y chaleco → **Chamarras**; trajes de baño
  → **Trajes de baño**; camisa y camisola → **Camisas** (son prendas distintas, no se fusionan).
- Si el departamento no existe, **preguntar antes de crearlo**; el asistente no crea
  departamentos ni marcas (se hacen en Catálogo).

### Dinero
- **Nunca inventar precio ni costo.** Si falta uno, preguntar. Precio > 0 obligatorio; costo 0
  solo si el dueño lo dijo ("las cajas no traen costo").
- Precio base de piezas de alto valor (bolsas, relojes) es **referencia**; se confirma al
  vender. Anotar "confirmar al vender" en la descripción cuando el dueño lo diga.
- Precio por categoría cuando el dueño da una regla ("estas marcas a un precio, lo demás a
  otro"): aplicarla a todo el lote y decirlo en el resumen. Nunca proponer precios propios.

### Qué revisar antes de proponer
- Buscar primero si ya existe la familia (marca + prenda + precio + descripción iguales): si
  coincide, **agregar variantes al producto existente**, no crear otro.
- Buscar por SKU o por departamento, no por el listado general paginado (en Postgres el
  listado sin `ORDER BY` se come productos).
- Marcar como **pendiente de confirmar** cualquier pieza repetida en la lista (misma marca,
  modelo y precio dos veces): no cargarla dos veces hasta que el dueño lo confirme.
- Cosas sin marca o sin precio se quedan fuera de la propuesta y se preguntan al final, en una
  sola lista.
