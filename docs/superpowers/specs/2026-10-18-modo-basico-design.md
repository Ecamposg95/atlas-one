# Modo básico: la app corta para tiendas FREE (Kaory, Coqueta, Imaltzin) — diseño

Fecha: 2026-10-18 · Continúa SP2 "versión ligera FREE" del mega plan
(`2026-10-14-mega-plan-altas-docs-responsivo-agente-design.md`). SP2 escondió 10 entradas del
menú y bajó la descarga un 30 %; este diseño va al siguiente nivel: **las pantallas mismas se
vuelven cortas** para quien no paga licencia y no necesita opciones.

## 1. Qué pide el usuario

"Kaory y Coqueta son usuarios muy básicos: no requieren tantas opciones y no pagan licencia."
No hay un dolor que corregir; hay opciones que sobran. El producto gratuito debe verse y sentirse
simple, y lo completo queda para los planes de paga (o para quien la plataforma lo decida).

## 2. Qué usan de verdad (producción, 60 días al 2026-10-18)

Cuatro orgs FREE, todas `ATLAS_POS`, dos usuarios cada una (administradora y cajera), una sucursal.

| Función | Kaory 14 | Ginebra 15 | Imaltzin 16 | Coqueta 18 | Decisión |
|---|---|---|---|---|---|
| Ventas (60 d) | 8,632 | 92 | 1,743 | 328 | — |
| Cobro efectivo / tarjeta / transferencia | 8,631 / 1 / 0 | 86 / 6 / 0 | 1,630 / 107 / 6 | 274 / 54 / 0 | se quedan los tres |
| Renglones a precio de escalón | 2,641 de 13,626 | 17 | 3,496 de 3,762 | 277 de 567 | **escalones se quedan** (Mayoreo, Menudeo, Caja) |
| Precio distinto al base sin escalón | 160 | 9 | ~0 | ~0 | edición manual del precio se queda (Kaory cobra "Servicios" a importe libre) |
| Tickets pausados | 68 | 2 | 13 | 0 | **pausar se queda** |
| Salidas / entradas de efectivo | 0 / 1 | 1 / 4 | 38 / 0 | 17 / 0 | se quedan |
| Cliente en venta, clientes capturados | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | se esconde |
| Descuento (global o por renglón) | 0 | 0 | 0 | 0 | se esconde |
| Dólares, propina, factura, comisión tarjeta, nota, cotización | 0 | 0 | 0 | 0 | se esconden |
| Devoluciones | 0 | 0 | 0 | 0 | se queda, pero desde el ticket (no en el menú) |
| Productos creados por la cajera (90 d) | 106 en total | | | | alta rápida desde el POS se queda, con el formulario corto |
| Catálogo: fotos / marcas reales / tallas / empaques | 0 / 0 / 0 / 0 | 0/0/0/0 | 1/0/0/0 | 0/0/0/0 | se esconden |
| Catálogo: código de barras / IVA / costo / descripción | 321 / 128 / 321 / 321 (importados) | 3/0/102/0 | 487/0/18/62 | 201/197/219/203 (importados) | código, IVA y costo se quedan; descripción se esconde |
| Departamentos | 11 | 9 | 1 | 0 | se quedan (lista corta) |

Consultas en `scratchpad/modo-basico/consultas_uso_free*.sh` (solo lectura). Ginebra está inactiva.

## 3. Decisiones

1. **Un perfil de interfaz, no un frontend aparte.** `perfil_ui: "basico" | "completo"` viaja en
   `GET /api/users/me/context`. Se deriva del plan (**FREE → básico**, el resto → completo) y la
   plataforma puede forzarlo por organización con `organization.perfil_ui` (`auto` | `basico` |
   `completo`, por defecto `auto`). Así un cliente de paga que quiera lo simple lo tiene, y una
   FREE en demostración puede ver todo.
2. **Nada se apaga (principio de los planes).** El backend no cambia validaciones, gating ni
   endpoints; las pantallas completas siguen abriendo por URL (soporte). Básico solo decide qué
   se **muestra**. Un dato que ya exista en la tienda (una marca, un cliente) se sigue viendo
   donde aparezca.
3. **La cajera gana pantalla, no la pierde:** el POS básico tiene los mismos botones grandes de
   siempre menos los que nadie usa. Las reglas de cobro (`saneaCobro`, capacidades) no se tocan.
4. **La dueña entra a una sola pantalla que responde "¿cómo voy?"** y un menú de ocho entradas.
   Es la primera versión del "Inicio del dueño" de SP6, acotada a básico; SP6 completo sigue
   siendo otro sub-proyecto.
5. **El formulario de producto corto se hace con `campos_producto`** (SP1, principio 3): el
   catálogo de campos recibe el perfil y esconde más campos; el formulario ya sabe esconderlos.
   Un producto importado que traiga descripción o marca la muestra (regla existente).
6. **Responsivo y kit `ui/` desde el día uno** (receta de CLAUDE.md §5); lo nuevo entra al guard
   `responsivoOla2.test.ts` y a la verificación con capturas de SP5.
7. **Fuera de alcance:** cambios de precio o topes de plan, PWA/offline, plataforma superadmin
   (salvo el selector de perfil), vistas móviles, gastro, un "modo básico" para cajeras de
   boutique (Eleven es ULTRA+ y ve todo).

## 4. Qué ve cada quien en básico

### 4.1 Cajera (rol CAJERO; también GERENTE si lo hubiera)

**Menú (6):** Cobrar · Mis ventas · Corte · Productos · Impresora · Mi día (inicio actual,
`/atlas-pos`, sin cambios). Fuera del menú: Devoluciones (se llega desde el ticket en Mis
ventas y desde el POS, como hoy), Etiquetas, Escáner, Clientes, Mi expediente.

**POS (`/pos`) básico esconde:** descuento global y por renglón, botón Cliente, equivalente en
dólares, propina y factura (ya por capacidad), comisión de tarjeta (sigue cobrándose si la org
la configuró: solo se esconde el aviso), nota del ticket, "Editar producto" desde el carrito
(ficha de 1,077 líneas), panel de diagnóstico del agente y asistente de instalación (quedan en
Impresora), "Forzar precio por pieza al vender caja". **Se queda:** buscar, agregar, cantidad,
elegir precio o escalón, editar precio del renglón, pausar y retomar tickets, cobro en efectivo,
tarjeta, transferencia y mixto, cambio, imprimir y reimprimir (con PIN), devolver, abrir y
cerrar turno, entradas y salidas de efectivo, crear producto rápido (formulario corto).

**Productos (`/products`, vista de sucursal) básico:** lista con producto, código, precio,
existencia y activo; acciones nuevo, editar, activar/desactivar, ajustar existencia. Se
esconden importador, etiquetas CSV, generar códigos, vista de rejilla y filtros avanzados.

### 4.2 Administradora / dueña (ADMINISTRADOR, DUEÑO)

**Menú (8):** Inicio · Ventas · Corte · Productos · Reportes · Empresa · Usuarios · Impresora.
Se esconden: Control, Catálogo, Departamentos, Marcas, Etiquetas, Escáner, Clientes, Sucursales
(una sola), Inventario HQ, Devoluciones HQ, Valor de la tienda (entra como tarjeta en Inicio),
Resumen móvil, Mi expediente, IA, Cotizaciones, Seguimiento, Compras, Gastos.

**Inicio básico (`/hq/operations` cuando el perfil es básico; página nueva `InicioBasico`):**
- Vendido hoy y ayer (importe y tickets) y la semana; efectivo vs tarjeta de hoy.
- Corte: turno abierto o cerrado, quién, desde cuándo, efectivo esperado en caja (datos de
  `cashApi` como en Corte).
- Lo que se está acabando: productos con existencia ≤ 3 (tope en Empresa, por defecto 3),
  máximo 10, con enlace a Productos.
- Los 5 que más se venden esta semana (`reportsApi` dashboard / top products).
- Cuánto vale mi tienda a precio de venta y a costo (tarjeta de SP3, `ValorTiendaCard`).
- Sin estilos inline, sin "glow": kit `ui/` (`CabeceraPagina`, `DaxCard`, `ListaTarjetas`).

**Reportes básico (`/reports` ya existente para la cajera, reutilizado):** periodo hoy / ayer /
semana / mes, total y tickets, por método de pago, los 10 productos más vendidos, ventas por
hora. `HQReportsHub` queda fuera del menú.

**Productos (`/products`, vista HQ) básico:** misma lista corta; **formulario corto**: nombre,
código de barras, departamento, precio, costo, IVA (sí/no), existencia inicial y escalones
("precio de mayoreo a partir de N piezas", presentados como filas simples). Se esconden
marca, descripción, unidad, foto, tasa de IVA (queda 16), empaques, variantes y la matriz de
sucursales (una sola). `campos_producto(preset, modulos, perfil)` devuelve esos ocultos.

**Empresa básico:** nombre, teléfono, dirección, encabezado y pie del ticket, impresora, tope de
"se está acabando". Lo demás (ticket detallado, redes, términos, dólares, comisión tarjeta,
instrucciones IA) se esconde bajo "Más opciones" plegado.

**Usuarios:** sin cambios (ya es corta: dos personas).

## 5. Arquitectura

**Backend (pequeño):**
- `organization.perfil_ui` `String(12)` nullable + ALTER en `scripts/railway_init.py`;
  `organization.umbral_poca_existencia` `Integer` nullable (tope de "se está acabando").
- `app/services/perfil_ui.py::perfil_efectivo(org) -> "basico" | "completo"` (`perfil_ui` si no
  es `auto`; si no, `basico` cuando `plan == FREE`). Pruebas unitarias.
- `/me/context` agrega `perfil_ui` y pasa el perfil a `campos_producto(preset, modulos,
  perfil)`; en básico `ocultos += brand_id, description, unit, image_url, tax_rate,
  packaging_units, variants`. Pruebas en `tests/test_campos_producto.py` (o donde viva).
- `PUT /api/platform/organizations/{id}` acepta `perfil_ui` (solo plataforma; el PUT de tenant
  lo ignora, como `plan`). `OrganizationUpdate` de tenant acepta `umbral_poca_existencia`.
- Endpoint de lectura para el inicio básico si hace falta uno solo:
  `GET /api/reports/inicio-basico?branch_id=` que junte hoy/ayer/semana, por método, top 5 y
  poca existencia (reusa `get_daily_summary`, `get_dashboard_stats` y la consulta de
  existencias); evita cinco llamadas desde una PC vieja. Filtra org y sucursal como reports.

**Frontend:**
- `store/enabledModulesStore`: `perfilUi: 'basico' | 'completo'` (por defecto `completo` hasta
  cargar), `useModoBasico()`.
- `navPerfilPlan.ts` → `navPerfil.ts`: perfil por **perfil_ui** además de por plan; listas
  `OCULTAS_BASICO_CAJERA` y `OCULTAS_BASICO_HQ` de §4. Pruebas puras.
- `App.tsx`: `/hq/operations` renderiza `InicioBasico` o `HQOperations` según `useModoBasico()`.
- POS: un objeto `opcionesPos = opcionesPorPerfil(perfil, capacidades)` con banderas
  (`descuentos`, `cliente`, `usd`, `nota`, `editarProducto`, `diagnostico`, `forzarPieza`)
  que `POS.tsx`/`CartPanel.tsx` consultan; función pura con pruebas. Ningún cambio en el
  payload del cobro.
- `FormularioProducto`: ya esconde por `campos_producto`; básico solo añade que `prices`
  (escalones) se pinte con la sección simple. Pruebas con el store en básico.
- Products/ProductsBranchView: `useModoBasico()` esconde importador, etiquetas, códigos, rejilla
  y filtros avanzados (render condicional, no `hidden`).
- `pages/hq/InicioBasico.tsx` (nueva, ≤ 300 líneas) + `api/reports.ts::inicioBasico`.
- `Organization.tsx`: sección "Más opciones" plegada en básico; campo umbral.
- Plataforma: selector "Perfil de interfaz" junto a "Plan y uso" en `PlatformOrgDetail.tsx`.
- Guardias: nuevas páginas en `PAGINAS` de `responsivoOla2.test.ts`; ningún `fixed inset-0`
  nuevo; presupuesto del bundle intacto (`InicioBasico` es chunk propio).

## 6. Pruebas y verificación

- Backend: `perfil_efectivo` (auto/forzado × planes), `campos_producto` con perfil,
  `/me/context` de una org FREE trae `perfil_ui = basico` y los ocultos; `inicio-basico` con
  ventas sembradas (hoy/ayer/semana, por método, top, poca existencia) y aislamiento por org y
  sucursal.
- Frontend: `navPerfil` (cajera y HQ en básico vs completo con los mismos módulos),
  `opcionesPorPerfil`, `InicioBasico` (jsdom con datos falsos), POS sin botón Cliente/descuento
  en básico (jsdom), formulario corto (jsdom), Products sin importador en básico.
- Capturas Playwright a 390/768/1024/1440 de `/pos`, `/products`, `/hq/operations`,
  `/reports`, `/organization` en básico, con la herramienta de SP5 (Tarea 0 de su plan).
- Manual (usuario): en producción, forzar `perfil_ui = completo` a una FREE y volver a `auto`;
  revisión de 10 minutos con la cajera de Kaory (cobrar con escalón, pausar, reimprimir, crear
  un producto) y con Mirna (Inicio, Corte, Reportes).

## 7. Sale cuando

- Una org FREE entra y ve el menú de 6 (cajera) u 8 (dueña), el POS sin las opciones de §4, el
  formulario corto y el Inicio básico; una org de paga no nota ningún cambio (capturas a 1440
  idénticas en completo).
- Suite verde, presupuesto del bundle intacto, cero overlays nuevos.
- Kaory y Coqueta revisadas en tienda; lo que la cajera eche de menos vuelve al perfil en un
  commit de seguimiento antes de fusionar.
