# Modo básico

La interfaz corta para quien no paga licencia (spec: `docs/superpowers/specs/2026-10-18-modo-basico-design.md`).
Solo cambia lo que se **muestra**: el backend no apaga nada y las pantallas completas siguen
abriendo por URL.

## Quién lo ve

`app/services/perfil_ui.py::perfil_efectivo(org)`:

| `organization.perfil_ui` | Plan | Perfil |
|---|---|---|
| `NULL` o `auto` | FREE (o NULL, vacío, desconocido: `plans.obtener_plan`) | básico |
| `NULL` o `auto` | START, PRO, BUSINESS, SCALE, ULTRA_PLUS | completo |
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
| Menú de la dueña | Control, Catálogo, Departamentos, Marcas, Etiquetas, Escáner, Clientes, Sucursales, Inventario, Existencias, Ventas HQ, Devoluciones HQ, Valor de la tienda, Resumen móvil, Mi expediente, IA, Cotizaciones, Pedidos, Compras, Gastos | `navPerfilBasico.ts` (`OCULTAS_BASICO_HQ`) |
| POS | descuentos, botón Cliente, dólares, editar producto, forzar precio por pieza; el alta rápida usa el formulario corto | `pages/pos/opcionesPos.ts` |
| Formulario de producto | marca, descripción, unidad, foto, tasa de IVA, empaques, tallas (y la matriz con una sola sucursal) | `app/modules/products/campos.py` (`OCULTOS_BASICO`) |
| Productos | importador, plantilla, etiquetas CSV, generar códigos, rejilla | `pages/inventory/Products.tsx`, `components/branch/ProductsBranchView.tsx` |
| Inicio y Reportes de la dueña | `/hq/operations` → `InicioBasico`; `/hq/reports-hub` → `finance/Reports` | `App.tsx` (`<PorPerfil>`) |
| Empresa | logo, dólares, comisión y lo boutique del ticket bajo "Más opciones"; aparece el tope de "Se está acabando" | `pages/core/Organization.tsx` (`<MasOpciones>`) |

Un dato que ya existe (una marca, un descuento de un ticket pausado) se sigue viendo.
