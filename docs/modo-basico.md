# Modo básico

La interfaz corta para quien no paga licencia (spec: `docs/superpowers/specs/2026-10-18-modo-basico-design.md`).
Solo cambia lo que se **muestra**: el backend no apaga nada y las pantallas completas siguen
abriendo por URL.

## Quién lo ve

`app/services/perfil_ui.py::perfil_efectivo(org)`:

| `organization.perfil_ui` | Plan | Perfil |
|---|---|---|
| `NULL` o `auto` | `FREE` explícito | básico |
| `NULL` o `auto` | START, PRO, BUSINESS, SCALE, ULTRA_PLUS, o plan NULL, vacío o desconocido | completo |
| `basico` | cualquiera | básico |
| `completo` | cualquiera | completo |

Viaja en `GET /api/users/me/context` como `perfil_ui`; el frontend lo lee con `useModoBasico()`
(`store/enabledModulesStore.ts`) y arranca en `completo` hasta que el contexto carga (si falla, se
queda en `completo`).

## Forzar un perfil (plataforma)

`/platform/organizations/{id}` → "Perfil de interfaz", o
`PUT /api/platform/organizations/{id}` con `{"perfil_ui": "completo"}` (`auto` regresa a la regla del
plan). El `PUT /api/organization/` de la tienda lo descarta. La tienda lo ve al recargar.

## Qué esconde

| Dónde | Básico | Dónde vive la lista |
|---|---|---|
| Menú de cajera/gerente | Devoluciones, Etiquetas, Escáner, Clientes, Mi expediente, Reportes, Valor de la tienda | `components/layout/navPerfilBasico.ts` (`OCULTAS_BASICO_SUCURSAL`) |
| Menú de la dueña | Departamentos, Marcas, Etiquetas, Escáner, Clientes, Sucursales, Inventario, Devoluciones, Valor de la tienda, Mi expediente, IA, Cotizaciones, Pedidos, Compras, Gastos (Control y Resumen móvil ya no existen en ningún menú desde SP6; desde la Fase 3 del admin, 2026-10-25, Catálogo, Existencias, Ventas HQ y Devoluciones HQ ya no existen: son Productos, Inventario, Ventas y Devoluciones) | `navPerfilBasico.ts` (`OCULTAS_BASICO_HQ`) |
| Conteo de inventario | el menú "Conteo" (`/inventory/conteos`) de la dueña/admin: se esconde en `OCULTAS_BASICO_HQ`; el backend sigue respondiendo | `components/layout/navPerfilBasico.ts` |
| POS | descuentos, botón Cliente, dólares, editar producto, forzar precio por pieza (el alta usa el formulario único en todos los perfiles; en básico sale corto por `campos_producto`) | `pages/pos/opcionesPos.ts` |
| Formulario de producto | marca, descripción, unidad, foto, tasa de IVA, empaques, tallas (y la matriz con una sola sucursal) | `app/modules/products/campos.py` (`OCULTOS_BASICO`) |
| Productos | importador, plantilla, etiquetas CSV, generar códigos, rejilla; y todo lo del Catálogo viejo (cifras, filtro de aprobación y marca, archivados, Exportar, acciones aprobar/duplicar/archivar/restaurar/matriz/historial): `catalogo = isHQ && !modoBasico` | `pages/inventory/Products.tsx`, `components/branch/ProductsBranchView.tsx` |
| Inicio y Reportes de la dueña | `/hq/operations` → `hq/Inicio` con solo las secciones de hoy (pide `completo=false`: no se mueve, pendientes, sucursales y utilidad no se consultan); `/hq/reports-hub` → `reports/Reportes` (la misma pantalla que en completo; el selector de sucursal solo aparece con más de una) | `pages/hq/Inicio.tsx` (`perfilUi`; en básico no monta `InicioGraficas`) |
| Empresa | logo, dólares, comisión y lo boutique del ticket bajo "Más opciones"; aparece el tope de "Se está acabando" | `pages/core/Organization.tsx` (`<MasOpciones>`) |

Un dato que ya existe (una marca, un descuento de un ticket pausado) se sigue viendo.

> **Umbral de "se está acabando" (SP6, 2026-10-21):** el tope de Empresa (`umbral_poca_existencia`, 3 piezas si no se capturó) es el único criterio en toda la app: Inicio, `/reports/dashboard`, `/command-center/stats`, CSV y KPIs del catálogo. Antes el tablero y el centro de mando marcaban ≤ 5 fijo; una tienda que quiera ese comportamiento captura 5 en Empresa.
