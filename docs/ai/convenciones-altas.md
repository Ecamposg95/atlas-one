# Convenciones para dar de alta productos (lo aprendido con Eleven, 2026-09 → 2026-10)

Este documento alimenta al asistente IA (SP4) y sirve a cualquier persona o script que capture
catálogo. Tiene dos partes: **convenciones generales del preset boutique** (van en el prompt
base `app/modules/ai/prompts/boutique.md`) y **convenciones de Eleven Fashion** (texto listo
para pegar en Empresa → "Instrucciones para el asistente IA" de esa organización).

Fuentes: lotes cargados a mano y por API en Eleven (org 17) entre el 2026-09-21 y el
2026-10-16: normalización de la ficha boutique, playeras y camisas de caballero, cuaderno del
dueño (3 hojas), bolsas por WhatsApp, zapatos (4 lotes de fotos), depuración del relleno del
histórico.

---

## Parte 1 · Convenciones generales (preset boutique)

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
- **Género:** `HOMBRE`, `MUJER`, `UNISEX`, `NINO`. Regla práctica en boutique: todo caballero
  salvo lo evidente de dama (Miu Miu y Chanel completas; Prada sin mangas, tirantes o brillos).
  En zapatos manda la carpeta/caja de origen, no la etiqueta "MAN/WOMAN" (es código de fábrica).

### SKU
- Convención `MARCA-PRENDA[-INICIALES]-MODELO[-MUJ|NIN]-COLOR-TALLA`, solo `[A-Z0-9-]`. La
  genera `sku_sugerido` (`GET /api/products/sku-suggest`); el asistente la pide con la
  herramienta `sugerir_sku` y revisa que esté libre.
- Marca: iniciales si tiene 2+ palabras (Loro Piana = LP, Saint Laurent = YSL por uso), 3 letras
  si una (VER, GUC, PRA). **Colisiones conocidas que se respetan:** MAM = Maison Margiela (MM es
  Miu Miu), BLC = Balenciaga (BAL quedó de Balmain), AS = Acne Studios, PB = Purple Brand,
  SM = sin marca.
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
- Escala de ropa boutique: **Ch / M / G / XL** (el dueño escribe "XG"; se guarda XL). Tallas
  numéricas en pantalón y calzado (40, 41, 42…; "US 10" o "UK 7" son marcadores por corregir).
- **La existencia va en la talla que se contó**, no toda en la principal. "3 piezas en M" =
  `extra_variants[M].initial_stock = 3`; el resto de tallas nace en 0 para que aparezca en el POS.
- Mismo modelo en varios colores = **un producto con variantes por color** (Goyard Grand Hôtel
  NAR/AMA/MAR). Precio distinto por variante sí se puede.
- Bolsas, maletas, relojes y piezas únicas: **un producto por pieza** (cada una tiene su
  referencia); no agruparlas aunque sean del mismo modelo si el dueño las dictó por separado.
- Zapatos por foto: **cada foto es un par nuevo**, aunque la caja sea idéntica a una ya cargada;
  no deduplicar contra el catálogo. Si la variante ya existe, se suma 1 con un ajuste "Compra".
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
- Precio por categoría cuando el dueño da una regla ("Loro Piana, Zegna y Brunello $4,500; LV
  $5,000; lo demás $4,000"): aplicarla a todo el lote y decirlo en el resumen.

### Qué revisar antes de proponer
- Buscar primero si ya existe la familia (marca + prenda + precio + descripción iguales): si
  coincide, **agregar variantes al producto existente**, no crear otro.
- Buscar por SKU o por departamento, no por el listado general paginado (en Postgres el
  listado sin `ORDER BY` se come productos).
- Marcar como **pendiente de confirmar** cualquier pieza repetida en la lista (misma marca,
  modelo y precio dos veces): no cargarla dos veces hasta que el dueño lo confirme.
- Cosas sin marca o sin precio se quedan fuera de la propuesta y se preguntan al final, en una
  sola lista.

---

## Parte 2 · Instrucciones para Eleven Fashion (pegar en Empresa → Instrucciones para el asistente IA)

```
Somos una boutique de ropa, calzado y bolsas de marca (una sucursal: Roma, id 20).
Tallas de ropa: Ch, M, G, XL (si escribo XG es XL). Calzado con número (40-46 hombre, 35-40 dama).
Abreviaturas de marca que ya usamos en SKU: MAM = Maison Margiela, MM = Miu Miu, BLC = Balenciaga,
BAL = Balmain, LP = Loro Piana, LV = Louis Vuitton, YSL = Saint Laurent, GG = Golden Goose,
GUC = Gucci, HER = Hermès, ZEG = Zegna, CH = Chrome Hearts, CHA = Chanel, DIO = Dior, FEN = Fendi,
MON = Moncler, RO = Rick Owens, TIM = Timberland, AS = Acne Studios, PB = Purple Brand, SM = sin marca.
Departamentos: Tenis (tenis), Calzado (botas y zapatos de vestir), Bolsas (incluye maletas, mochilas,
vanities), Accesorios (carteras, relojeras), Joyería, Camisas (camisa y camisola son distintas),
Playeras, Suéteres (jersey y premium van aquí), Pantalones (incluye bermudas), Chamarras (bomber,
chaleco), Trajes de baño, Vestidos, Faldas, Conjuntos, Trajes.
Género: casi todo HOMBRE; Miu Miu y Chanel son MUJER salvo que diga lo contrario; dama lleva
variante única con sufijo -MUJ en el SKU.
Precios de calzado salvo que diga otra cosa: Loro Piana, Zegna y Brunello 4500; Louis Vuitton 5000;
el resto 4000. Costo 0 cuando no lo doy.
Bolsas y relojes: un producto por pieza, con la referencia de fábrica en la descripción.
Zapatos por foto: cada foto es un par nuevo, no deduplicar; la etiqueta grande no define talla ni
color, manda la nota amarilla.
Si una pieza se repite en mi lista, pregúntame antes de proponerla dos veces.
```

---

## Cómo se usa
- El asistente carga la Parte 1 por preset (`ATLAS_POS_BOUTIQUE`) y la Parte 2 desde
  `organization.ai_instrucciones`. Cambiar la Parte 1 es un cambio de código; la Parte 2 la
  edita el dueño cuando quiera.
- Scripts previos de carga (solo lectura histórica): `eleven_hombre_playeras_camisas.py`,
  `eleven_hombre_lote2.py`, `eleven_lote3.py`, `zapatos/cargar_zapatos.py`,
  `zapatos/cargar_lote2.py`, `zapatos/cargar_lote3_mujer.py`, `zapatos/cargar_lote4.py`
  (scratchpad de sesiones anteriores, no versionados). Todos con `DRY_RUN=1`, idempotentes por
  SKU y con verificación GET al final: el asistente hereda ese contrato (proponer → confirmar →
  verificar).
