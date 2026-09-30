# El lado administrador cabe en cualquier pantalla — diseño

Fecha: 2026-09-30 · Caso guía: Eleven Fashion (dueña que revisa desde el iPhone) y Novedades
Kaory (admin que alterna laptop, tablet y teléfono) · Roles: ADMINISTRADOR y DUEÑO

## 1. El problema

El 21/09/26 se hizo responsivo el **armazón** y el **POS de cajera** (rama `feat/responsivo`):
bajo 1024 px el menú lateral es un cajón, los modales con `.dax-modal` son hoja inferior en
teléfono, el POS va en una columna. Eso resolvió "no puedo cobrar desde el teléfono".

Lo que NO se tocó es el **contenido de las ~40 pantallas de administración**. El dueño abre la
aplicación casi siempre en el teléfono; el administrador la abre en lo que tenga a mano. Hoy, en
390 px de ancho:

| Síntoma | Pantallas afectadas (barrido del 29/09/26 sobre `frontend/src/pages`) |
|---|---|
| Tablas que solo tienen scroll horizontal: se ven 3 columnas y hay que arrastrar | 26 |
| Rejillas de KPIs o formularios con `grid-cols-N` sin prefijo responsivo: no se apilan | 22 |
| Modales hechos a mano (`fixed inset-0 …`) sin `.dax-modal`: no desplazan, el pie se pierde tras el teclado | 9 |
| Barras de filtros en una sola fila con anchos fijos (`w-36`) | la mayoría de las de listado |

Además, al entrar desde teléfono el dueño es **redirigido a `/mobile/owner`**, un panel aparte
que solo muestra un resumen: desde ahí no llega a ventas, corte ni reportes sin pasar por el menú
"Más" y aterrizar en pantallas rotas.

## 2. Decisiones tomadas (con el usuario, 29/09/26)

1. **Adaptar cada pantalla de escritorio**, no crecer el armazón `/mobile/*`. Una sola versión
   de cada pantalla que se acomoda al ancho. Menos que mantener y todo el admin sirve en cualquier
   dispositivo. El redirect del dueño a `/mobile/owner` desaparece al final de la ola 1; la ruta
   y el ítem "Resumen móvil" del menú se conservan.
2. **Las tablas se vuelven tarjetas por renglón bajo 768 px.** Los 3-4 datos clave arriba, el
   detalle al desplegar. Sin scroll horizontal nunca en teléfono.
3. **Entrega por olas según uso del dueño**, cada una en su rama y desplegable por separado.
4. **Mecanismo elegido para tablas → tarjetas: render condicional con una tarjeta compartida**
   (opción A). Cada pantalla conserva su `<table>` intacta para escritorio; bajo 768 px un hook
   renderiza en su lugar una lista de `TarjetaFila`. Se descartaron: (B) reescribir las 26 tablas
   como definiciones de columnas —cambia el DOM de escritorio en pantallas de dinero—, y (C) solo
   CSS con `data-label` —apila las 7 columnas sin jerarquía.

## 3. Regla de oro: escritorio no cambia

Todo lo que este diseño introduce vive detrás de `max-width` o de utilidades con prefijo
(`sm:`, `md:`, `lg:`). **De 1024 px hacia arriba cada pantalla debe renderizar exactamente igual
que hoy.** Se verifica con capturas a 1440 px antes y después, comparadas pixel a pixel (§7).

Cortes, heredados del trabajo del 21/09 (`hooks/useIsMobile.ts`):

| Corte | Qué decide |
|---|---|
| `< 640` (`sm`) | Modal → hoja inferior. Campos de formulario a una columna. |
| `< 768` (`md`) — `useEsTelefono()` | Tabla → tarjetas. Cabecera de página apilada. KPIs en 2 columnas. |
| `< 1024` (`lg`) — `useIsMobile()` | Sidebar → cajón (ya existe). Rejillas de 3-4 columnas → 2. |
| `≥ 1024` | Sin cambios. |

## 4. Base común (se construye en la ola 1, la usan las tres)

Todo en `frontend/src/components/ui/` salvo lo indicado. Nombres en español, como el resto del
kit (`TablaDesplazable`, `DaxCard`).

### 4.1 `TarjetaFila`

La unidad de la lista en teléfono. Reemplaza a un `<tr>`.

```tsx
<TarjetaFila
  titulo="A-41"                       // folio, nombre, SKU… (negrita)
  subtitulo="29/09 14:32 · María"     // opcional, una línea, se trunca
  importe="$1,250.00"                  // opcional, a la derecha, tabular-nums
  estado={<StatusChip …/>}            // opcional, junto al importe
  datos={[                             // pares etiqueta/valor, rejilla de 2 columnas
    { etiqueta: 'Pago', valor: 'Tarjeta' },
    { etiqueta: 'Artículos', valor: 3 },
  ]}
  maxDatosVisibles={4}                 // los demás quedan tras "Ver más"
  acciones={<>…botones…</>}           // fila al pie, cada botón ≥ 44 px de alto
  onClick={() => abrirDetalle(v)}      // toda la tarjeta es tocable si se pasa
/>
```

- Se pinta con `dax-card` y los tokens existentes (`--dax-text`, `--dax-border-dim`); nada de
  color nuevo.
- Cuando hay más de `maxDatosVisibles` datos, aparece un botón "Ver más / Ver menos" con
  `aria-expanded`; el estado es local a la tarjeta.
- Si hay `onClick`, la tarjeta es `<button>` a todo lo ancho (accesible por teclado); las
  `acciones` van fuera del botón para que un toque en ellas no abra el detalle.
- Lista contenedora: `ListaTarjetas` — un `div` con `space-y-2` y estados vacío/cargando que
  reciben los mismos textos que hoy muestra la tabla.

Patrón de uso en una pantalla (lo que cambia por tabla):

```tsx
const esTelefono = useEsTelefono()
…
{esTelefono ? (
  <ListaTarjetas vacio={filas.length === 0} textoVacio="Sin ventas en el periodo">
    {filas.map(v => <TarjetaFila key={v.id} … />)}
  </ListaTarjetas>
) : (
  <TablaDesplazable>{/* la <table> de hoy, sin tocar */}</TablaDesplazable>
)}
```

Se usa el hook y no `hidden md:block`, para no montar los dos árboles a la vez: las tablas de
ventas traen cientos de filas.

### 4.2 `BarraFiltros`

Contenedor de los filtros de listado (fechas, buscador, selects, botón de aplicar/exportar).

- `flex flex-wrap gap-2 items-end`. Cada hijo declara su ancho de escritorio como hoy (`w-36`)
  y la barra le impone `w-full` bajo `sm` con una regla CSS por descendiente directo
  (`.dax-filtros > * { width: 100% }` dentro de `@media (max-width: 639px)`).
- `ParFechas`: envuelve "desde/hasta" en `grid grid-cols-2 gap-2` para que en teléfono vayan
  juntas en una fila.
- La acción principal (`accion` prop) se pinta al final; bajo `sm` ocupa todo el ancho.
- Escritorio: la fila actual, sin cambios.

### 4.3 `CabeceraPagina`

Título + descripción + acciones, que hoy cada pantalla arma a mano con `flex justify-between`.

- `≥ md`: igual que hoy (título a la izquierda, acciones a la derecha).
- `< md`: se apila; la acción **principal** se queda con texto y ancho completo; las
  **secundarias** pasan a solo icono con `aria-label` y `dax-btn-icon` (44 px).
- Las pantallas que ya tienen una cabecera propia y funciona, no se migran por migrar: solo las
  que se rompen.

### 4.4 Modales

- `components/ui/Modal.tsx`: el panel recibe `dax-modal` (hoja inferior bajo `sm`, `90dvh`,
  scroll interno) y el pie recibe `dax-modal-footer` (pegado abajo, visible con teclado). Cambia
  `max-h-[90vh]` por lo que ya impone `.dax-modal`. Es un solo archivo y arregla de golpe todo lo
  que ya usa `Modal`.
- Los 9 overlays hechos a mano (`Returns`, `SalesHistory`, `Seguimiento`, `CashHistory`,
  `Purchases`, `Boxes`, `Logistics`, `CustomerFormModal`, `HR`) migran a `Modal` cuando su
  estructura es simple (título + cuerpo + botones); si tienen cabecera o cuerpo con lógica
  propia, solo se les añade `dax-modal` a la tarjeta y `dax-modal-footer` al pie, tal como
  documenta `index.css §2`.

### 4.5 Reglas de rejilla (sin componente; se aplican al editar cada pantalla)

| Hoy | Queda |
|---|---|
| KPIs `grid-cols-4` / `grid-cols-6` | `grid-cols-2 sm:grid-cols-3 lg:grid-cols-4` (o `-6`) |
| Formulario `grid-cols-2` | `grid-cols-1 sm:grid-cols-2` |
| Paneles `grid-cols-3` | `grid-cols-1 lg:grid-cols-3` |
| Botonera de 3+ botones en `flex` | `flex flex-wrap`; en teléfono los botones ≥ 44 px de alto |
| Texto de KPI `text-3xl` en tarjeta de 2 columnas | `text-2xl md:text-3xl` si desborda |

Cuando escritorio ya tenía el prefijo `lg:` con un valor, se conserva ese valor: la regla solo
añade los cortes inferiores.

### 4.6 Inicio del dueño en teléfono

`utils/rutaInicio.ts`: se elimina la rama `if (esOficina && esMovil) return '/mobile/owner'`.
Admin y dueño entran a `/hq/operations` (o `/home` en presets `ATLAS_ONE_*`) en cualquier
ancho. Sus pruebas se actualizan. Se hace **al final de la ola 1**, cuando Inicio HQ ya pasó la
verificación en 390 px. `/mobile/owner` y el ítem "Resumen móvil" se conservan.

## 5. Olas

Cada ola: rama `feat/responsivo-admin-ola-N` desde `main`, verificación de §7, y despliegue
solo con permiso explícito.

### Ola 1 — base + lo que el dueño abre a diario

| Pantalla | Ruta | Archivo | Qué le toca |
|---|---|---|---|
| Inicio HQ | `/hq/operations` | `pages/hq/HQOperations.tsx` | KPIs a 2 col, paneles `lg:grid-cols-3` → 1 col, tabla de top productos → tarjetas, quitar `min-h` fijo bajo lg |
| Ventas HQ | `/hq/sales` | `pages/hq/HQSalesLog.tsx` | filtros → `BarraFiltros`, 2 tablas → tarjetas, `grid-cols` |
| Mis ventas | `/sales` | `pages/sales/SalesHistory.tsx` | filtros, tabla → tarjetas, modal de detalle → `Modal` (tabla interna de artículos → tarjetas o lista simple) |
| Corte de caja | `/cash-history` | `pages/finance/CashHistory.tsx` | 2 modales → `dax-modal`, 3 `grid-cols-2/4`, 2 tablas → tarjetas |
| Reportes HQ | `/hq/reports-hub` | `pages/hq/HQReportsHub.tsx` | rejilla de gráficas → 1 col, gráficas con ancho fluido (revisar `ResponsiveContainer`/ancho fijo) |
| Reportes | `/reports` | `pages/finance/Reports.tsx` | `grid-cols`, KPIs |
| Devoluciones HQ | `/hq/returns` | `pages/hq/HQReturns.tsx` | 2 tablas → tarjetas |
| Devoluciones | `/returns` | `pages/sales/Returns.tsx` | 2 modales → `Modal`, 2 tablas → tarjetas |
| Inicio del dueño | — | `utils/rutaInicio.ts` | quitar redirect (§4.6), último paso |

### Ola 2 — catálogo y personas

`Products`, `AdminCatalog`, `ProductForm`, `AdminProductCreate`, `Inventory`, `HQInventory`,
`Departments`, `Brands`, `Customers` + `CustomerFormModal`, `Users`, `Organization`,
`HQBranches`, `HQBranchDetail`, `HQControl`, `PrinterSettings`, `Labels`, `StoreScanner`.

`Products.tsx` (1,772 líneas) ya tuvo una pasada el 21/09; aquí solo se verifica y se corrigen
los 5 `grid-cols` sin prefijo que quedan.

### Ola 3 — el resto y gastro

`Purchases`, `Expenses`, `Quotes`, `QuoteMaker`, `Seguimiento`, `Logistics`, `Boxes`, `HR`,
`HRMe`, `PresetHome`, `GastroHomeDay`, `Startup`; gastro: `Recipes`, `RecipeForm`, `FloorPlan`,
`KDS`, `Meseros`, `Botellas`, `MenuVisual`.

### Fuera de alcance

- Las 17 pantallas de `pages/platform/` (superadmin): no las ve admin ni dueño.
- El POS de cajera (`/pos`, `/atlas-pos`): ya es responsivo.
- Rediseñar contenido, copy o arquitectura de información (eso es el plan
  `.superpowers/sdd/ux-admin/`, aparte). Aquí solo se acomoda lo que ya existe.
- Cambios de backend: ninguno.

## 6. Criterios de aceptación (por pantalla, en cada ola)

En 390 × 844 (teléfono), 768 × 1024 (tablet vertical) y 1024 × 768, claro y oscuro:

1. **Sin desbordamiento horizontal**: `document.documentElement.scrollWidth <= innerWidth` y
   ningún elemento con `getBoundingClientRect().right > innerWidth + 1`.
2. **Ninguna tabla visible bajo 768 px** salvo las de detalle dentro de un modal con ≤ 4
   columnas cortas (artículos de un ticket), que caben.
3. **Todo control tocable ≥ 44 × 44 px** bajo 768 px (botones, filas tocables, chips que
   filtran).
4. **Modales**: cierran con Escape, desplazan por dentro, el pie con la acción principal queda
   visible sin desplazar.
5. **Sin texto cortado** en KPIs ni títulos (nada de `overflow: hidden` que trunque un importe).
6. **Escritorio 1440 × 900 idéntico** a la captura previa (§7.2).

## 7. Verificación

### 7.1 Recorrido automático (scratchpad, no versionado)

Script de Playwright (`chromium` ya está en `~/.cache/ms-playwright`; se instala el paquete
`playwright` en el scratchpad, no en el repo). Contra el stack local (`uvicorn` + Vite, o el
`docker compose` del repo), con una cuenta ADMINISTRADOR de una org con datos (Kaory u
Eleven restauradas, o la QA demo).

Por cada ruta de la ola y cada tamaño de §6: entra, espera a que no haya `PageLoader`,
captura pantalla completa, ejecuta la comprobación 1 y la 3 de §6, y guarda un informe
`ola-N-findings.md` en `.superpowers/sdd/responsivo-admin/` (gitignored). Se abre cada modal
que tenga la pantalla desde un `data-testid` o el texto de su botón.

### 7.2 Escritorio intacto

Antes de tocar código de una ola: capturas a 1440 × 900 de todas sus rutas sobre `main`.
Al terminar: mismas capturas sobre la rama, comparación con `pixelmatch` (umbral 0). Cualquier
diferencia se explica o se corrige. El único cambio de escritorio que se acepta de antemano es el
del `Modal` compartido, si el paso de `90vh` a `90dvh` mueve un píxel; en escritorio ambos miden lo mismo.

### 7.3 Pruebas unitarias (vitest, versionadas)

- `TarjetaFila`: pinta título/importe/estado; oculta datos más allá de `maxDatosVisibles` y los
  muestra al tocar "Ver más"; las acciones no disparan `onClick` de la tarjeta.
- `BarraFiltros`/`ParFechas`: estructura y clases.
- `rutaInicio.test.ts`: dueño/admin en móvil → `/hq/operations` (y `/home` con `ATLAS_ONE_*`).
- `tsc` y `vite build` limpios; `npm test` sin nuevos fallos.

### 7.4 Dispositivo real

Tras desplegar cada ola, el usuario revisa en el iPhone de Eleven. Se anotan los pendientes que
solo aparecen en dispositivo (teclado de iOS, safe-area), igual que en `responsivo-telefono`.

## 8. Riesgos

- **Duplicar la lógica de una fila en tabla y tarjeta** puede desincronizar datos (una columna
  nueva que se añade a la tabla y no a la tarjeta). Mitigación: en cada pantalla, los formateos
  (`fmtMoney`, `fmtDate`, mapeos de estado) viven en funciones compartidas por ambos renders,
  no se copian.
- **Gráficas** (`HQReportsHub`, `Reports`): si la librería fija ancho en píxeles, el desborde no
  se arregla con clases. Se revisa primero en la ola 1 y, si hace falta, se envuelve en un
  contenedor con `ResizeObserver`.
- **`Modal` compartido** lo usan pantallas de las tres olas y del POS. El cambio de §4.4 se hace
  primero y se verifica el POS de cajera en 390 px antes de seguir.
- **Vite en `/mnt/d` (WSL) no detecta cambios**: reiniciar el dev server antes de capturar, o
  las capturas salen viejas (lección del 20/08).
- **Dos `pytest`/`vitest` en el mismo worktree se pisan** (CLAUDE.md §6): una ola a la vez.
