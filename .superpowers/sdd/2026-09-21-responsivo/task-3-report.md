# Task 3 — Flujo de administrador: formularios, tablas y modales en teléfono

Rama `sdd/resp-admin` (worktree `.claude/worktrees/resp-admin`), sobre la base de la Task 1.
Verificación: `npx vitest run` → **44 archivos / 464 pruebas, verde** (baseline de la Task 1:
44/456; las 8 nuevas son de los dos ayudantes extraídos), `npx tsc --noEmit` limpio,
`npm run build` ok.

20 archivos modificados, 4 nuevos (2 de código, 2 de pruebas). Sin dependencias nuevas.

---

## 1. Qué se arregló, por hallazgo de la auditoría

| # | Hallazgo | Dónde | Cómo |
|---|---|---|---|
| **C-1** | Rejillas de columnas fijas (campos de 34–49 px) | `ProductTieredPricesSection.tsx`, `Products.tsx` (precios y empaques), datos generales del modal | `grid-cols-1 sm:grid-cols-[…]` + etiqueta por campo en toda fila bajo `sm` |
| **C-2** | Modales sin tope de alto ni scroll | `Users`, `Brands`, `Departments`, `Organization`, `Products` ×3, `Inventory`, `HQInventory`, `HQSalesLog`, `HQReturns` ×2 | `.dax-modal` en la tarjeta + `.dax-modal-footer` en la barra de Guardar |
| **C-3** | Barra de acciones de `/products` sin `flex-wrap` | `Products.tsx` | `flex-wrap` + `w-full sm:w-auto`, texto `hidden sm:inline`, `aria-label`, `whitespace-nowrap` |
| **C-4** | `/admin/catalog`: 7 columnas + 7 botones ⇒ ~1020 px | `AdminCatalog.tsx` | Tarjeta por producto bajo `md`; tabla intacta de `md` hacia arriba |
| **C-5** | Botones de editar invisibles al tacto | `Products.tsx` (cuadrícula) | `opacity-100 md:opacity-0 md:group-hover:opacity-100 focus-within:opacity-100` + 44 px |
| **C-6** | Tablas de variantes con 5 campos por fila | `ProductVariantsEditor.tsx`, `ProductVariantsSection.tsx` | Tarjeta por variante bajo `md`; tabla de `md` hacia arriba |
| **I-1** | `ProductBranchMatrix` desborda y pierde el contexto | `ProductBranchMatrix.tsx` | Primera columna `sticky left-0` (solo `< md`) + campos `w-14/w-20` bajo `sm` |
| **I-2** | Tablas sin contenedor de scroll ⇒ se desplaza la página | `Inventory.tsx` | `TablaDesplazable` |
| **I-3** | Tabla dentro de modal ⇒ doble eje | `HQSalesLog.tsx`, `HQReturns.tsx` | `TablaDesplazable` alrededor de la tabla de partidas |
| **I-4** | Scroll anidado en `/hq/operations` | `HQOperations.tsx` | `lg:min-h-[380px]`, `lg:flex-1 lg:overflow-y-auto`, `lg:max-h-64`, `overscroll-contain` |
| **I-6** | `display:flex` sobre `<td>` | `Brands`, `Departments`, `Organization`, `ProductVariantsEditor` | `<td className="whitespace-nowrap"><div className="flex">…` |
| **M-1** | 4–5 renglones de filtros antes del primer producto | `AdminCatalog.tsx` | Búsqueda a todo lo ancho; los dos selectores a mitad y mitad; grupo de aprobación con `flex-wrap` |
| **M-2** | Grupo de presets sin `flex-wrap` | `HQReportsHub.tsx` | `flex-wrap` |
| **M-4** | Casillas de 16 px como único control | `ProductBranchMatrixSection.tsx`, `ProductBranchMatrix.tsx` | `<label>` de 44 px alrededor (la casilla no cambia) |
| **M-7** | Nombre de producto recortado a 140 px | `HQOperations.tsx` | `max-w-none md:max-w-[140px]` |

**No implementado (y por qué):**

- **I-5** (heatmap táctil) — vive en `components/reports/Heatmap.tsx`, que **no** está en la
  lista de archivos de este brief. Es un cambio de interacción (tooltip por `click`/`focus`
  en vez de `hover`), no de maquetación; conviene hacerlo junto al resto de `/hq/reports-hub`.
- **I-9** (título de pantalla en teléfono) — su única sede es `Layout.tsx:185`, y las reglas
  de este encargo prohíben tocar `Layout.tsx`. El parche es de una línea y lo dejo escrito
  para quien sea dueño del archivo: `<div className="hidden sm:flex flex-col min-w-0">` →
  `<div className="flex flex-col min-w-0">`, moviendo el `hidden sm:block` al `<span>` del
  nombre de la organización y al distintivo «ACTIVO», de modo que a 390 px la barra superior
  solo gane el `pageTitle` (una línea, `truncate`) y no el bloque entero.
- **I-7, I-8, I-10, I-11, C-7** — ya resueltos por la Task 1.
- **M-3** (`CashHistory` con `text-2xl` en `grid-cols-2`) y su tabla de movimientos (I-2) —
  `pages/finance/CashHistory.tsx` no está en la lista del brief y el corte de caja es
  territorio de la Task 2. Queda pendiente: `TablaDesplazable` en `:266` y
  `text-xl sm:text-2xl` en `:250-258`.
- **M-5** (sparkline oculta en teléfono) — es una decisión de diseño, no un defecto.
- **M-6** (toast de `PrinterSettings`) — archivo de la Task 2.

---

## 2. Código nuevo

### `src/utils/formResponsivo.ts` + prueba (3 casos)

`claseEtiquetaFila(indice, base)`. En escritorio la fila repetida es una tabla y la etiqueta
se pinta solo en la primera fila, haciendo de encabezado de columna; apilada en teléfono, las
filas 2..n quedaban con tres campos sin nombre. La función devuelve la clase base para la
primera fila y `base + " sm:hidden"` para las demás: visible siempre en teléfono, oculta de
640 px hacia arriba. Se usa en los tres sitios del hallazgo C-1.

### `src/pages/core/catalogActions.ts` + prueba (5 casos)

`accionesDeProducto(p)` decide qué botones lleva un producto (`aprobar`/`rechazar` solo si
está `PENDING`; `archivar` o `restaurar` según `is_active`) y `ACCIONES_CATALOGO` guarda
etiqueta, icono y colores de cada uno. Se extrajo porque esa decisión estaba incrustada en el
JSX de la tabla y la vista de tarjetas la habría duplicado; ahora las dos vistas recorren la
misma lista con `botonesDeAcciones(product, conTexto)`.

### `TablaDesplazable`: prop `sangrado`

El `-mx-4 px-4` del componente hace la caja 32 px más ancha que su padre. Eso está bien
dentro de un contenedor que recorta (el caso de `ProductBranchMatrix`, que ya lo usaba), pero
dentro de una `DaxCard padding={false}` —que no recorta— el desbordamiento se lo habría
comido la página, justo lo que el componente existe para evitar. `sangrado={false}` (nuevo,
opt-in; el default no cambia) desactiva el sangrado. Lo usan los siete envoltorios nuevos que
viven dentro de una tarjeta sin padding.

### Patrón «tabla → tarjetas»

Siguiendo el precedente que ya había en `components/platform/DataTable.tsx:150`
(`useMediaQuery('(max-width: 639px)')`), las tres pantallas que cambian de forma usan
`useMediaQuery('(max-width: 767px)')` y renderizan **una sola** de las dos vistas. Se
descartó el `hidden md:block` puro en CSS a propósito: con las dos ramas montadas, cada fila
tendría dos copias del estado del formulario y lo tecleado en la tarjeta no aparecería en la
tabla al girar el teléfono.

---

## 3. Cómo queda cada pantalla (leyendo las clases; no hubo navegador)

### `/products` — catálogo HQ (`Products.tsx`)

- **390 px** · Cabecera: título (`text-2xl`, envuelve) y, en su propio renglón
  (`w-full sm:w-auto` + `flex-wrap`), el contador y los botones **solo icono** de 44×44
  (`dax-btn-icon`, texto en `hidden sm:inline` y en `aria-label`) más el conmutador
  lista/cuadrícula, también a 44 px. Suman ~300 px y envuelven a dos renglones: ya no hay
  desbordamiento lateral. Cuadrícula: dos tarjetas por renglón, con los botones
  *Ajustes*/*Editar* **visibles** (44×44, esquina superior derecha). Lista: la tabla sigue en
  su `overflow-x-auto` y los dos botones de la fila miden 44 px.
- **768 px** · Idéntico al escritorio salvo que los botones conservan el piso de 44 px
  (`.dax-btn-icon` corta en 767, así que a 768 ya no aplica) — es decir: igual que hoy, con
  las etiquetas de texto visibles desde 640.

### `/products` — modal de alta/edición (`ProductModal`)

- **390 px** · `.dax-modal` lo convierte en **hoja inferior**: pegado abajo, de borde a borde,
  esquinas superiores redondeadas, tope de `90dvh`, scroll interno y respeto de la barra de
  inicio. *Datos generales* baja a **una columna** (antes dos de ~145 px). Cada precio
  escalonado y cada empaque es un bloque con borde propio de cuatro/cinco campos a lo ancho,
  todos rotulados, y un botón «✕ Quitar» de 44 px de alto. El pie *Cancelar / Guardar* queda
  **pegado abajo** (`.dax-modal-footer`, `position: sticky`) y sigue visible con el teclado
  abierto.
- **768 px** · Tarjeta centrada de `max-w-2xl` con tope de `90dvh`: rejillas de dos columnas y
  filas de precios/empaques en su reparto de columnas de siempre (`sm:` ya está activo desde
  640). Única diferencia con hoy: el tope de alto y el pie pegado.

### `/products/new` y editar (`ProductForm.tsx`)

- **390 px** · Se recupera el ancho útil: el `p-4` interno pasa a `p-0` bajo `sm` (de 286 a
  318 px). Título a `text-xl`. Precios escalonados apilados y rotulados (C-1). Las variantes
  existentes son **tarjetas** (color/talla de titular, luego Color · Talla · SKU · Código ·
  Precio en rejilla de dos, «Ajustar existencia» a lo ancho y *Guardar* / *Retirar* al 50 %
  con 44 px de alto). La matriz color × talla del alta también es una tarjeta por combinación.
  *Cancelar* / *Guardar* a lo ancho, en columna invertida (la acción principal arriba).
- **768 px** · Vuelve la tabla de variantes dentro de su `TablaDesplazable`, la rejilla de
  precios en columnas y el pie en fila alineado a la derecha: igual que hoy.

### `/admin/catalog` (`AdminCatalog.tsx`)

- **390 px** · Filtros en tres renglones (búsqueda a todo lo ancho; Departamento y Marca a
  mitad y mitad; los cuatro botones de aprobación repartiéndose el ancho, 44 px de alto).
  Lista: **una tarjeta por producto** con nombre + marca a la izquierda y precio a la derecha,
  luego SKU · departamento · distintivo de sucursales · estado en una línea que envuelve, y
  las acciones **rotuladas** («Matriz de sucursales», «Aprobar», «Editar»…) en botones de
  44 px que envuelven. Cero scroll horizontal, y nunca se pierde de vista de qué producto se
  trata.
- **768 px** · Vuelve la tabla de 7 columnas dentro de `TablaDesplazable` con los mismos
  botones de icono de siempre (mismas clases, mismos `title`), y la `DaxCard` recupera su
  `p-5`. Desplaza de lado **dentro de la tarjeta**, no la página.

### `/users` (`Users.tsx`)

- **390 px** · Tabla dentro de `TablaDesplazable`; el botón de estado y el lápiz miden 44 px y
  llevan `aria-label` con el nombre de usuario. El modal —el más alto de la app, 7 campos más
  el bloque de PIN— es hoja inferior con `90dvh`, scroll interno y *Cancelar / Guardar*
  pegados abajo: **ya se puede dar de alta y editar un usuario desde el teléfono**. Rol y
  Sucursal pasan a una columna.
- **768 px** · Modal centrado `max-w-md` con las dos columnas de Rol/Sucursal y el pie pegado;
  el resto igual que hoy.

### `/organization` (`Organization.tsx`)

- **390 px** · Las dos pestañas se reparten el ancho con 44 px de alto. Formularios ya eran
  `sm:grid-cols-2/3` y quedan en una columna. Tabla de sucursales en `TablaDesplazable`, con
  la celda de acciones arreglada (I-6: el `flex` estaba en el `<td>`, que dejaba de alinearse
  con su `<th>`). Modal de sucursal como hoja inferior con pie pegado.
- **768 px** · Pestañas a su ancho natural, tabla completa, modal centrado.

### `/brands` y `/departments`

- **390 px** · I-6 corregido, lápiz y papelera a 44 px con `aria-label` («Editar Samsung»),
  modal como hoja inferior con pie pegado.
- **768 px** · Sin cambios visibles respecto a hoy salvo la alineación correcta de la última
  columna.

### `ProductBranchMatrix` (cajón de la matriz de sucursales)

- **390 px** · La columna *Sucursal* queda **fija** a la izquierda mientras se desplaza el
  resto; los campos de override y min/máx bajan a `w-20` / `w-14`, así que el ancho mínimo cae
  de ~490 a ~330 px. La casilla de POS tiene 44 px de área táctil.
- **768 px** · `md:static md:bg-transparent` devuelve la celda a su comportamiento normal
  (incluido el tinte del hover) y los campos a `w-28` / `w-20`: idéntico a hoy.

### `/hq/*`

- **`/hq/operations`** · 390 px: la rejilla se apila sin el `minHeight: 380` fijo, y ni la
  lista de sucursales ni el feed de alertas tienen scroll propio (la página es la que
  desplaza), con `overscroll-contain` donde sí lo tienen. El nombre de producto ya no se
  recorta a 140 px bajo `md`. 768 px: igual que 390 salvo las rejillas `md:`; las tres cajas
  vuelven a su alto y scroll propios solo desde `lg` (1024), que es donde conviven de lado.
- **`/hq/sales`** · Tabla de 8 columnas en `TablaDesplazable` (desplaza la tabla, no la
  página). El modal de detalle es hoja inferior a 390 px y tarjeta `max-w-lg` a 768, con la
  tabla de partidas en su propio contenedor: ya no arrastra de lado todo el modal.
- **`/hq/inventory`** y **`/hq/returns`** · Modales de ajuste y de rechazo con `.dax-modal` y
  pie pegado; la tabla de artículos del detalle de devolución, envuelta.
- **`/hq/reports-hub`** · El grupo de presets envuelve.
- **`/inventory`** · La tabla de resultados estrena contenedor de scroll: antes, al no tener
  ninguno, quien se desplazaba de lado era el `<main>` y el botón «Ver» de la fila quedaba
  fuera de pantalla.

---

## 4. Qué se hizo para no tocar el escritorio (≥ 1024 px)

Todo va detrás de `sm:` / `md:` / `lg:`, del corte `max-width: 767px` de `.dax-btn-icon` (que
la Task 1 dejó ya escrito y que aquí solo se **aplica** a botones que no lo tenían), o de un
`useMediaQuery('(max-width: 767px)')` que en escritorio devuelve `false` y renderiza el árbol
de siempre. Tres deltas que sí se habrían visto en escritorio se corrigieron a propósito:

- el `gap-3` de la barra de `/products` se conserva con `gap-2 sm:gap-3`;
- M-7 se aplicó como `max-w-none md:max-w-[140px]` (y no `sm:max-w-none`) para que de 768 px
  hacia arriba el recorte a 140 px sea exactamente el de hoy;
- la columna fija de `ProductBranchMatrix` se apaga con `md:static md:bg-transparent`, y a las
  casillas de `ProductBranchMatrixSection` **no** se les tocó el aspecto: solo crece el
  `<label>` que las envuelve, y solo bajo `sm`.

Los únicos cambios que sí se ven en escritorio son los pedidos por la auditoría: I-6 (la
última columna de cuatro tablas ahora se alinea con su encabezado) y la extracción de las
acciones de `/admin/catalog` (mismas clases, mismos `title`, ahora también con `aria-label`).

---

## 5. Lo que hay que comprobar en un dispositivo real

Nada de esto se ejecutó en un navegador; los anchos salen del CSS declarado.

1. **`.dax-modal` como hoja inferior con el teclado abierto** en los ocho modales nuevos
   (Users es el caso límite: 7 campos + PIN). Confirmar que el pie pegado (`sticky bottom-0`)
   queda por encima del teclado de iOS y de Android, y que el `90dvh` no deja la cabecera
   fuera.
2. **Color del pie pegado.** `.dax-modal-footer` pinta `var(--dax-card-solid)`, que es opaco,
   mientras `.dax-card` es translúcido con `backdrop-filter`. En modo oscuro el pie se ve como
   una banda ligeramente distinta del cuerpo. Es intencional (si fuera translúcido se vería el
   contenido pasar por debajo), pero conviene mirarlo. En `ProductModal` se forzó
   `var(--dax-surface)` para que empate con esa tarjeta concreta.
3. **El corte a 767 px de las tres vistas tarjeta/tabla.** Girar el teléfono o redimensionar
   cruza el umbral y **remonta** la fila: un campo a medio teclear en `ProductVariantsEditor`
   se pierde. Es el precio de no duplicar el estado; verificar que no molesta en uso real.
4. **Columna `sticky` de `ProductBranchMatrix`** dentro del cajón, que a su vez está dentro de
   `overflow-y-auto`: comprobar que la celda fija no tapa el campo de override al desplazar y
   que el fondo `bg-[var(--dax-surface)]` no canta contra el de la fila.
5. **`/admin/catalog` en tarjetas con muchos productos** (50 por página): confirmar que el
   scroll va fluido y que los botones rotulados no hacen la tarjeta demasiado alta.
6. **Los botones solo icono de `/products` bajo 640 px**: cuatro iconos seguidos sin texto
   piden que el `aria-label` y el `title` basten para distinguirlos. Es el punto más discutible
   de la Task y el primero que conviene ver con la dueña del negocio.
