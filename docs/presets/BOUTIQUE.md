# Preset Boutique (`ATLAS_POS_BOUTIQUE`)

Guía de referencia del preset construido para **Eleven Fashion** (org 17, boutique de
ropa de la Roma, VPS) entre el 2026-09-16 y el 2026-09-21. Documenta qué es el preset,
el estándar de datos que asume, y el checklist para dar de alta la siguiente boutique.
Es la plantilla de la que debe partir cualquier preset nuevo — ver
[`docs/presets/README.md`](README.md) para el proceso genérico.

> Todo lo de aquí es código en `main` salvo donde se diga "deuda" o "diferido". Los
> commits exactos están en [`docs/CHANGELOG-2026-09-boutique.md`](../CHANGELOG-2026-09-boutique.md).

---

## 1. Qué es el preset

`ATLAS_POS_BOUTIQUE` (`scripts/init_presets_v2.py::PRESETS`, id `"ATLAS_POS_BOUTIQUE"`)
es **Atlas POS + dos módulos**:

```
ATLAS_POS_MODS = core, pos, cash_management, catalog, inventory,
                 returns, pricing, payments, reports
ATLAS_POS_BOUTIQUE = ATLAS_POS_MODS + scanner + variants
```

| Módulo | Scope | Por qué lo necesita una boutique |
|---|---|---|
| `scanner` | `BRANCH` | La cajera lee el código de barras con la cámara del celular/tablet para consultar precio y existencia en piso — sin escanear al carrito (eso sigue siendo el POS). Sin este módulo, `ROLE_ROUTES.CAJERO` no muestra `/scanner` aunque la ruta lo permitiera. |
| `variants` | `GLOBAL` | Gobierna toda la UI de **matriz color×talla**: el formulario de alta con filas por talla, el selector de variante en el POS/Scanner, y el CRUD de variantes (`POST/PUT/DELETE /api/products/{id}/variants…`). Sin el módulo activo el alta vuelve a ser un solo SKU/precio/código por producto — el modelo de datos (`product_variants.color/size`) es universal, pero la UI de matriz no aparece. |

El resto de los módulos es el mismo Atlas POS de cualquier tienda (Kaory, Ginebra,
Imaltzin): caja, catálogo, inventario, devoluciones, precios, pagos, reportes. Una
boutique **no** es un vertical nuevo de negocio — es Atlas POS con dos capacidades
encendidas y una convención de datos que cualquier tienda podría adoptar si quisiera.

**Enum de industria.** `IndustryType.ATLAS_POS_BOUTIQUE` es un enum nativo de Postgres;
`scripts/railway_init.py` lo sincroniza con `ALTER TYPE … ADD VALUE IF NOT EXISTS` en
AUTOCOMMIT en cada deploy (mismo bloque que sincroniza el resto de la taxonomía). El
catálogo de módulos y el preset los siembra `scripts/init_presets_v2.py::seed_modules_and_presets`,
que `railway_init.py` **ya llama automáticamente** (línea ~611) — no es un paso manual
pese a lo que dice un comentario viejo en `railway_init.py:90`.

**Activar el preset en una org existente:** `apply_industry_preset(db, org_id, IndustryType.ATLAS_POS_BOUTIQUE)`
(`app/services/capabilities_service.py`) — es lo mismo que hace `POST /api/setup/initialize`
o `POST /api/platform/organizations/{id}/apply-preset` desde plataforma. Verifica con
`GET /api/org/capabilities/` que la respuesta traiga `scanner` y `variants`.

---

## 2. Estándar de datos de producto

Decisiones tomadas con el dueño de Eleven Fashion el 2026-09-21 (rama
`feat/ficha-producto-boutique`, ver spec en `docs/superpowers/plans/2026-09-21-ficha-producto-boutique.md`).
**Aplican a cualquier boutique nueva** — son la plantilla, no una particularidad de Eleven.

### 2.1 Nombre del producto = la prenda, no la marca

- `products.name` = **solo la prenda**: "Chamarra mezclilla", "Playera cuello redondo
  manga corta". Nunca lleva la marca.
- La marca vive en `products.brand_id` → `brands.name` (mayúsculas, sin acentos, sin
  puntuación decorativa — convención de Eleven: `HERMES`, `ENFANTS RICHES DEPRIMES`).
  Alta con `POST /api/brands/`, deduplicar por nombre en mayúsculas antes de crear.
- `products.gender` (`String(10)`, valores `HOMBRE|MUJER|UNISEX|NINO` — sin enum de
  Postgres, regla de oro §5), `products.model` (`String(80)`, nombre comercial del
  modelo: "Air Force 1", "501") y `products.material` (`String(80)`, informativo: NO
  entra en ningún nombre derivado, solo en la ficha y la etiqueta CSV).
- `product_variants.color` (`String(60)`) y `product_variants.size` (`String(30)`) son
  la unidad vendible: cada combinación color×talla es una variante con su propio SKU,
  código de barras, precio, costo y existencia.

### 2.2 Nombre de venta derivado (`sale_name`)

`app/modules/products/sale_name.py` — sin base de datos ni FastAPI, es la **única
fuente** del texto que pintan el POS, la ficha, el CSV de etiquetas y el ticket
congelado:

```
sale_name(marca, nombre, modelo)                       -> "Louis Vuitton · Chamarra mezclilla"
variant_sale_name(marca, nombre, modelo, color, talla)  -> "Louis Vuitton · Chamarra mezclilla · Beige, Talla M"
```

- La **marca va primero** (así se pide en mostrador) y separa con ` · `.
- Marcas "vacías" (`Sin marca`, `Genérico`, `N/A`…) no encabezan nada — `marca_visible()`
  las filtra.
- **Compatibilidad hacia atrás, no negociable:** un producto SIN marca y SIN modelo se
  sigue llamando exactamente como hoy (`"Playera (M)"`, el formato heredado con
  paréntesis). El formato con ` · ` solo aparece cuando hay marca o modelo capturados.
  Esto es lo que deja a Kaory/Ginebra/Imaltzin sin ver ningún cambio si nunca tocan los
  3 campos nuevos.

`GET /api/products/{id}` y `GET /api/products/pos/search` aplanan `sale_name` en el
producto y en cada variante (`_compute_product_read`). `create_sale` congela el
`variant_sale_name` en `sales_lines.description` vía `_line_description` — el renglón
de la venta **no** vuelve a calcularse si el producto cambia después.

### 2.3 Convención de SKU

`sku_sugerido()` en el mismo archivo, expuesto por `GET /api/products/sku-suggest?brand=&name=&model=&color=&size=&gender=`
(devuelve `{"sku": "...", "available": bool}` — `available` es falso si el SKU ya
existe en la organización). **Es una sugerencia**: el botón "Sugerir SKU" del
formulario propone, el alta acepta cualquier SKU único por organización, nada lo
aplica solo.

Convención:

```
MARCA-PRENDA[-INICIALES]-MODELO[-MUJ|NIN]-COLOR-TALLA
```

| Parte | Regla | Ejemplo |
|---|---|---|
| Marca | Iniciales si tiene 2+ palabras ("Louis Vuitton"→`LV`, "Dolce & Gabbana"→`DG`); si no, 3 primeras letras ("Gucci"→`GUC`) | |
| Prenda | 4 primeras letras de la primera palabra del nombre + iniciales de las palabras restantes con peso, como token aparte ("Blusa manga corta"→`BLUS-MC`) | |
| Modelo | 3 primeras letras de la primera palabra | "Mezclilla"→`MEZ` |
| Género | solo se marca `MUJ` o `NIN`; hombre/unisex es el caso base (no se anota) | |
| Color | 3 primeras letras de la primera palabra | "Beige"→`BEI` |
| Talla | tal cual, sin signos | "26.5"→`265` |

Sin acentos, mayúsculas, solo `[A-Z0-9-]`. Partes vacías se omiten. Ejemplo completo:
"Louis Vuitton" / "Chamarra mezclilla" / — / "Beige" / "M" → **`LV-CHAM-MEZ-BEI-M`**.
Colisiones reales en Eleven (marcas que abrevian igual, p. ej. Balmain/Balenciaga → `BAL`)
se resuelven a mano numerando el SKU — el sugeridor no las evita.

### 2.4 Códigos de barras internos (EAN-13)

`app/services/barcodes.py`. Toda variante nueva recibe un código automáticamente al
crearse (alta, matriz de tallas, importación) si no trae uno de fábrica. Formato:

```
2 + org_id (3 dígitos) + secuencia (8 dígitos) + dígito verificador   = 13 dígitos
```

El prefijo GS1 `20–29` está reservado a uso interno de tienda, así que ningún
fabricante emite un EAN igual y cualquier lector de código de barras (incluido el
Scanner de cámara y el escaneo al cobrar) lo lee como EAN-13 normal. La secuencia se
protege con `pg_advisory_xact_lock` por organización en Postgres (no-op en SQLite);
la unicidad es **solo aplicativa, por organización** (`barcode_en_uso`) — no hay índice
único en la base porque Kaory/Ginebra tienen duplicados históricos y `create_all`
fallaría. Un código NUNCA se sobrescribe: solo se asigna cuando está vacío; los EAN de
fábrica importados se conservan.

Endpoints:

| Endpoint | Rol | Qué hace |
|---|---|---|
| `GET /api/products/barcodes/missing-count` | cualquiera | `{"missing": n}` de las variantes visibles sin código |
| `POST /api/products/barcodes/assign-missing` | ADMIN/DUEÑO | genera el código de las variantes sin uno (opcional `product_id`) → `{"assigned": n}` |
| `GET /api/products/export/labels.csv?product_id=&only_with_stock=` | cualquiera (scope de `query_visible_products`) | CSV UTF-8 con BOM: `SKU,Codigo de barras,Producto,Marca,Talla,Color,Precio,Existencia,Genero,Modelo,Material,Nombre de venta` |

**Deuda conocida:** 2 duplicados preexistentes en prod (org 16 `2024033050038`, org 14
`522`) impiden poner un índice único a nivel de base sin limpiarlos primero; el CSV no
respeta los filtros de pantalla; los productos inactivos se cuentan como faltantes pero
no se exportan.

---

## 3. El ticket

### 3.1 Secciones configurables (Empresa)

Columnas nuevas en `organization` (todas opcionales; ticket idéntico al de hoy si no se
capturan): `ticket_terms` (TEXT), `ticket_terms_url`, `ticket_instagram`,
`ticket_facebook`, `ticket_tiktok`, `ticket_whatsapp`, `ticket_show_vendor` (BOOLEAN,
**default `false`**). Se capturan en **Empresa** (`Organization.tsx`, sección
"Encabezado y Pie de Ticket").

`app/pos_printer.py::_build_boutique_footer(organization, branch)` arma el bloque y lo
emite `build_ticket_bytes` y `build_reissued_ticket_bytes` justo después del pie
normal, antes del corte de papel:

1. **Encabezado personalizado** (`ticket_header`) — se imprime bajo el nombre del
   negocio SOLO si es distinto del valor heredado `"ATLAS POS - Nota de Venta"` que
   traen todas las orgs por default. Así una tienda que nunca tocó el campo no ve una
   línea nueva.
2. **SIGUENOS** — una línea por red presente (`Instagram: …`, `Facebook: …`,
   `TikTok: …`, `WhatsApp: …`, `Web: …` desde `organization.website`, que solo aparece
   si hay alguna red capturada — el sitio web nunca sale solo).
3. **TERMINOS DE COMPRA** (o el texto de `ticket_terms_url` si se capturó, con el QR —
   ver 3.2) — párrafo largo envuelto a `cols` con `_wrap_text`.
4. **Proveedor** — `"Sistema: Atlas One | Atlas Tech"` + `atlasone.com.mx`, solo si
   `ticket_show_vendor = true` (apagado por defecto: el dueño lo enciende si quiere).

Todo en latin-1 con `replace` como el resto del ticket, sin exceder `self.cols` (32 a
58 mm, 56 a 80 mm). `ticket.html` (el HTML de impresión/reimpresión web) imprime las
mismas secciones bajo las mismas condiciones.

### 3.2 QR

Si `ticket_terms_url` está capturado, el ticket emite un QR nativo ESC/POS
(`GS ( k`, ≤ 255 bytes) apuntando a esa URL, además del texto plano de la URL (por si
el cliente no puede escanear). Eleven usa `elevenboutique.mx/terminos`.

### 3.3 Estilo de línea del producto: compacto vs. detallado

`organization.ticket_line_style` (`String(12)`, `compact` por default, o `detailed`).
Se elige en Empresa. Con `detailed`, cada renglón de producto ocupa 2–4 líneas en vez
de una:

```
1x  LOUIS VUITTON
    Chamarra mezclilla beige
    Talla M                          @4,000.00    4,000.00
```

- Línea 1: cantidad + marca en mayúsculas (o el nombre si no hay marca; entonces se
  omite la línea 2).
- Línea 2+: nombre + modelo, envuelto con `_wrap_text` a `cols - 4`.
- Última línea: atributos (`Talla M`, `Beige`, `Beige, Talla M`) a la izquierda,
  `@precio_unitario` y `total` a la derecha, sangría 4, miles con coma.

Implementado en `PosPrinter._product_lines_detailed`, usado por `build_ticket_bytes` y
`build_reissued_ticket_bytes` cuando `ticket_line_style == "detailed"`. Con `compact`
(el default de toda org existente) el ticket es byte-idéntico al de siempre. Eleven usa
`detailed` desde el 2026-09-21 — el dueño aceptó el costo de 2-4 renglones por prenda a
cambio de ver marca y talla sin recortar.

### 3.4 Cómo configurarlo en Empresa

Todo lo de este apartado se captura en **Organización → Empresa**: sección de
ticket (encabezado, redes, términos, proveedor, estilo de línea) y sección "Tipo de
cambio USD" / "Comisión por tarjeta" si aplican (§5).

---

## 4. Etiquetas

- **CSV** (`GET /api/products/export/labels.csv`, §2.4) — la ruta operativa hoy:
  exportar y abrir en la app de la etiquetadora del cliente.
- **Zebra (ZPL)**: **no implementado**. La investigación de impresión Bluetooth
  (2026-09-17) descartó integrar directamente una **PUQU Q1** (protocolo propietario
  sin SDK público, familia Niimbot/Phomemo) — la ruta operativa es el CSV de arriba
  importado a la app "PUQU Print" del fabricante, que imprime por lotes. Si el
  siguiente cliente boutique trae una **Zebra** de verdad (ZPL estándar), el plan es un
  módulo "Etiquetas" con una segunda cola CUPS servida por el mismo agente de
  impresión (ver §6) — diseño pendiente, sin código todavía.

---

## 5. Funciones de cajera

| Función | Dónde vive | Notas |
|---|---|---|
| **Scanner** (consulta con cámara) | módulo `scanner`, `/scanner` en el menú de CAJERO/GERENTE | Consulta precio/existencia/conteo — NO agrega al carrito del POS. Selector de talla en pantalla cuando el código no empata exacto. Respaldo `@zxing/browser` para navegadores sin `BarcodeDetector` nativo (Firefox, Safari, Chrome en Windows/Linux). |
| **Botón Cliente en el carrito** | `CartPanel.tsx` + `CustomerModal` | Busca en CRM por nombre/teléfono, da de alta rápido, o usa un nombre libre sin crear cliente. El nombre viaja en `customer_name`, se imprime en el ticket (`Cliente: …`, se omite si es "Público General"), sobrevive a pausar/reanudar. Funciona con la caja cerrada. |
| **PIN de reimpresión** | `users.reprint_pin_hash` | PIN de 4-8 dígitos, independiente de la contraseña, solo para roles gerenciales (ADMIN/DUEÑO/GERENTE). El POS prueba primero el PIN y luego la contraseña de un supervisor (sucursal → resto de la org). Se fija en **Usuarios → editar → "PIN de reimpresión"**. |
| **Equivalente en USD** | `organization.usd_rate_mode` (`off`\|`auto`\|`manual`) | Función general (no exclusiva de boutique), útil en zona turística/fronteriza. `auto` = FIX de Banxico + margen; `manual` = tipo fijo capturado por el admin. El tipo se congela en `sales_documents.usd_rate` al cobrar; el ticket imprime `USD (T.C. …)`. **Solo Fase A (mostrar el equivalente)** — cobrar en dólares es Fase B, sin implementar. |
| **Comisión por pago con tarjeta** | `organization.card_surcharge_pct` (0-20%, `NUMERIC(5,2)`) | Se suma solo a la parte pagada con `CARD`; en mixto, solo sobre esa parte. `total_amount` sigue siendo mercancía; la comisión vive en `sales_documents.card_surcharge_amount/pct`. Ticket imprime `COM. TARJETA` y `TOTAL A PAGAR`; el corte de caja muestra `card_surcharges`. **No se reintegra en devoluciones** (el banco ya se la quedó). |
| **Escanear al carrito** | — | **No existe.** El Scanner es solo consulta; cobrar escaneando es agregar manualmente el producto encontrado, o usar el buscador del POS que sí resuelve por código exacto. |

---

## 6. Checklist de alta de una boutique nueva

Sigue el patrón de altas ya hechas (Eleven Fashion org 17, Imaltzin org 16). Todo por
API con el CLI/scripts, nunca a mano en la base:

1. **Organización + sucursal + admin** — `python scripts/onboard_org.py --name "..." --industry ATLAS_POS --admin <usuario>` (idempotente; genera contraseña si no se pasa `--password`). Confirma sucursal única con `can_sell=True`.
2. **Preset boutique** — `apply_industry_preset(db, org_id, IndustryType.ATLAS_POS_BOUTIQUE)` (o `POST /api/platform/organizations/{id}/apply-preset` desde plataforma). Verifica `GET /api/org/capabilities/` → deben salir `scanner` y `variants`.
3. **Usuarios** — cajera(s) con rol CAJERO en la sucursal; PIN de reimpresión para ADMIN/DUEÑO/GERENTE si lo van a usar (§5).
4. **Marcas** — cargar con `POST /api/brands/` usando la sesión del admin de la tienda (nunca SUPERADMIN). **Decidir con el dueño la ortografía oficial** (mayúsculas/minúsculas, con o sin acentos) ANTES de cargar el catálogo — cambiarla después implica renombrar todas las marcas. Deduplicar por nombre en mayúsculas.
5. **Departamentos** — crear los que el dueño use para separar su catálogo (Eleven separó "Suéteres" de "Playeras" y "Tenis" de "Calzado" — es una decisión de negocio, no una convención técnica).
6. **Ticket** — capturar en Empresa: encabezado (si aplica), redes sociales, términos y condiciones (+ URL para el QR), proveedor (on/off), estilo de línea (compact/detailed). Imprimir un ticket de prueba y revisarlo con el dueño.
7. **Impresora / agente** — instalar el agente local (Linux: systemd; macOS: LaunchAgent) siguiendo `docs/superpowers/runbooks/print-agent-autostart.md`. El agente se está moviendo a un repo propio — ver §7 de este documento.
8. **PIN de reimpresión** — configurarlo si el dueño lo pide (recomendar 6 dígitos, no 4).
9. **Catálogo** — el alta la hace el cliente desde el panel, o se carga por script API-driven (ver §7) si viene de una migración/Excel.
10. **Códigos de barras y etiquetas** — `POST /api/products/barcodes/assign-missing` una vez cargado el catálogo; exportar `labels.csv` y entregarlo si el cliente tiene etiquetadora.
11. **Comisión por tarjeta / USD** — activar solo si el dueño lo pide explícitamente; ambas nacen apagadas (`card_surcharge_pct = 0`, `usd_rate_mode = 'off'`) y no cambian nada hasta que se configuran.
12. **Verificación cruzada** — sesión de la cajera en `/api/users/me/context` (org y sucursal correctos), `/api/branches/` con `can_sell=True`, POS search y `/api/products/` en 200, y un 403 al intentar tocar otra organización.

**Decisiones a tomar con el dueño ANTES de cargar datos** (la lista real que se le hizo
a Eleven — repetirla con el siguiente cliente):
- ¿Nombre del producto = solo la prenda, marca aparte? (sí, siempre — es el estándar).
- ¿Se capturan género/modelo/material, o solo lo esencial?
- Orden del nombre de venta: ¿marca primero? (es el default del sistema).
- Departamentos: ¿cuáles y cómo se separan?
- Convención de SKU: ¿se adopta la sugerida o el cliente ya tiene la suya?
- Ticket: ¿qué redes, términos, encabezado, estilo de línea?
- ¿Comisión por tarjeta? ¿Qué porcentaje?
- ¿Equivalente en USD? ¿Modo automático o manual, qué margen?
- ¿PIN de reimpresión genérico o por persona?

---

## 7. Scripts operativos y su patrón

Las cargas de datos de Eleven (corrección de catálogo, pasada de SKU, ventas
históricas) se hicieron como **scripts Python idempotentes que hablan por API**, nunca
tocando la base directamente. Patrón:

- El script hace login como el **admin de la tienda** (`eleven`, no SUPERADMIN ni un
  script con acceso directo a SQLAlchemy) y llama los mismos endpoints que usaría el
  panel. Así cualquier regla de negocio (tenancy, validaciones, eventos) se ejercita
  igual que si lo hiciera un humano.
- **Idempotente**: correrlo dos veces no duplica nada — dedup por nombre/SKU antes de
  crear, `PATCH`/`PUT` en vez de `POST` si el registro ya existe.
- Vive en el scratchpad de la sesión que lo escribió (no en el repo) salvo que sea de
  uso recurrente — `scripts/onboard_org.py` es el único de este tipo que sí quedó en
  el repo porque se reutiliza en cada alta.
- **Ventas registradas por API deben usar el usuario de la cajera que va a hacer el
  corte, no el admin.** El corte de caja agrupa por `sales_documents.cash_session_id`
  (`session_sales_filter`); vender con `eleven` abre la caja de `eleven` y la cajera no
  ve nada en su corte. Si ya se registraron con el usuario equivocado, hay que mover
  `cash_session_id` con un script ORM — y esa migración de datos **la debe correr el
  dueño de la operación** (o alguien con acceso directo a la base), no queda como
  tarea de agente porque el clasificador de comandos bloquea logins/escrituras por
  script contra producción.
- Las **re-fechas** de ventas (`created_at`, folios fuera de orden) también requieren
  un script DB directo — mismo punto: el dueño lo corre, no un agente vía API.

---

## 8. Deuda y diferidos conocidos del preset

Ver el detalle completo y fechado en [`docs/CHANGELOG-2026-09-boutique.md`](../CHANGELOG-2026-09-boutique.md).
Resumen de lo más relevante para quien construya el siguiente preset:

- **`GET /api/products/search` es inalcanzable** — `core.router` monta `/{product_id}`
  antes que `search.router`, así que cualquier ruta de `search.py` queda tapada
  (preexistente, no introducido por el preset boutique, pero lo hereda cualquier
  boutique nueva).
- **`import_export` y el alta rápida del cajero no conocen `gender/model/material`.**
  Solo el formulario completo de admin los captura.
- **Fase B de USD** (cobrar en dólares, método `USD_CASH`, corte con dólares) no
  existe — solo se muestra el equivalente.
- **Escalones de precio son solo de la variante principal** — las tallas hermanas
  venden siempre al precio base, no heredan el escalón por volumen.
- **Responsivo en teléfono real sin verificar del todo** — cobro con teclado abierto
  en iOS, laptops táctiles ≥768px siguen dependiendo de hover para editar. Ver
  `docs/superpowers/plans/2026-09-21-responsivo.md` y la nota "pendiente de
  dispositivo real" en la memoria de la sesión.
- **Auditoría de esquema 2026-09-19** (`.superpowers/sdd/db-audit/`, no versionada)
  encontró 43 hallazgos preexistentes (no introducidos por el preset boutique, pero
  relevantes si el siguiente preset toca las mismas tablas): entre ellos, que
  `product_variants.barcode` no tiene UNIQUE a nivel de base (solo aplicativo, §2.4) y
  que existen **tres mecanismos de migración** distintos en el repo — ver
  `CLAUDE.md §6`.
