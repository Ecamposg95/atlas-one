# Estado de los módulos, planes y presets

Auditoría del 2026-11-24 (frente F2 del megaplan). Decisión del dueño: **lo que se
vende y no está construido se oculta hasta que exista.**

- **Fuente única del estado:** [`app/services/estado_modulos.py`](../../app/services/estado_modulos.py)
  (`ESTADO_MODULOS`). Espejo del frontend: `frontend/src/utils/estadoModulos.ts`, amarrado
  por `frontend/src/__tests__/estadoModulos.test.ts`. Guardia del backend:
  `tests/test_estado_modulos.py`.
- **Este documento es la evidencia** de cada estado y la propuesta de qué hacer con
  planes y presets. Si cambias un estado en el código, cambia aquí su renglón.
- Para destapar un módulo terminado: `CLAUDE.md` §5 «Destapar un módulo cuando se termina».

| Estado | Significa | Qué pasa en pantalla |
|---|---|---|
| `disponible` | backend real + pantalla real | se muestra y se ofrece |
| `en_construccion` | hay la mitad (backend sin pantalla, o al revés) | no se muestra a la tienda; la plataforma lo ve marcado «En construcción» |
| `oculto` | cascarón o sin código | no se muestra a la tienda; la plataforma lo ve marcado «No construido» |

Ocultar es **solo de interfaz**: `organization_modules` no se toca, `require_module` no
cambió y la plataforma puede seguir encendiendo cualquier módulo. Una organización que
ya tenía encendido un módulo no disponible lo conserva encendido; solo deja de verlo.

> La columna `modules.status` (STABLE/BETA) **no es confiable**: marca STABLE a
> `promotions`, `workshops`, `manufacturing` e `invoicing` (seed de arranque), que no
> existen. El estado que vale es el de `estado_modulos.py`.

---

## 1. Estado por módulo

El catálogo son 39 claves: 35 de `scripts/init_presets_v2.py::MODULES_CATALOG` (se siembra
en cada deploy) más 4 que solo siembra `capabilities_service.seed_global_modules` en cada
arranque (`warehouse`, `customer_portal`, `work_orders`, `kds`). `bulk_pricing` y
`multi_currency` **no existen** en el repo (ni catálogo, ni código, ni frontend).

Planes: B = base (cualquier plan), y el plan mínimo que lo trae como crecimiento.
Presets abreviados: POS, BOU(tique), RET(ail), BEA\*(uty legacy), GAS\*(tro legacy),
BAR(ber), B&W, HEA(lth), RES(taurant), CAF(é), BAR-B (Bar), SER(vices), ENT(erprise),
CUS(tom). ENT trae todo el catálogo de despliegue menos `tienda_en_linea`.

### 1.1 No disponibles y dudosos (lo que importa)

| Módulo | Estado | Evidencia | Planes | Presets |
|---|---|---|---|---|
| `promotions` | **oculto** | Cero código: ningún router, modelo ni pantalla. Solo la constante en `app/ui/nav_registry.py:21`. El widget «Promociones» de `PresetHome` mandaba a `/products`. | START+ | RET, ENT |
| `invoicing` | **en_construccion** | No hay CFDI ni timbrado. Lo único que gobierna es la capacidad `factura` (`app/capacidades/catalogo.json`): casilla que suma 16 % de IVA al cobro (`components/pos/CartPanel.tsx`, `pages/pos/POS.tsx`). Esa casilla sigue funcionando donde el módulo esté encendido. | PRO+ | ENT (y fallback viejo `AUTO_REPAIR_SHOP`) |
| `warehouse` | **en_construccion** | Backend real `app/routers/logistics.py` (`require_module("warehouse")`: contenedores, cajas, cálculo de carga, embarques). Sin pantalla propia: embarques y cálculo de carga no tienen interfaz. La única pantalla que lo consume es «Cajas y contenedores» (`pages/inventory/Boxes.tsx`), que el menú cuelga de `logistics`. No está en el catálogo de despliegue. | PRO+ | ninguno v2 (fallback viejo `DISTRIBUTOR_POS`, `RETAIL_CHAIN`) |
| `commissions` | **oculto** | Cascarón: `app/modules/commissions/router.py` (20 líneas, solo `/health` con `"ready": False`). La pantalla era «Próximamente». | BUSINESS+ | BEA\*, BAR, B&W, HEA, RES, BAR-B, SER, ENT |
| `memberships` | **oculto** | Cascarón: `app/modules/memberships/router.py` (solo `/health`). Pantalla «Próximamente». | BUSINESS+ | BEA\*, BAR, B&W, HEA, ENT |
| `ai` | **en_construccion** | `app/modules/ai/` existe (en construcción en otro frente, F1); la pantalla `/ai` era «Próximamente». | SCALE+ | ENT |
| `appointments` | **en_construccion** | Backend real: `app/modules/appointments/` (1,744 líneas: router, services, `portal_router.py` de reserva pública en `/api/portal/booking`). Ninguna pantalla lo consume (`/appointments` era «Próximamente»). | — (vertical) | BEA\*, BAR, B&W, HEA, SER, ENT |
| `workshops` | **oculto** | Cero código (ni router ni modelo de órdenes de trabajo). El widget «Órdenes de trabajo» de Services apunta a `/seguimiento` (pedidos de cotizaciones). | — (vertical) | SER, ENT |
| `manufacturing` | **oculto** | Cero código. El widget «Manufactura» de Enterprise mandaba a `/inventory`. | — (vertical) | ENT |
| `kds` | **oculto** | Clave vieja de arranque, sustituida por `kitchen`; nada la lee. | — | fallback viejo `RESTAURANT_*` |
| `work_orders` | **oculto** | Clave vieja de arranque; solo `app/ui/nav_registry.py`. Sin código. | — | fallback viejo `AUTO_REPAIR_SHOP` |
| `purchasing` | disponible (**dudoso**) | El megaplan lo daba por cascarón, y `app/modules/purchasing/router.py` lo es (solo `/health`), igual que la ruta `/purchasing`. Pero la clave `purchasing` es la que enciende **«Compras» `/purchases`**, que sí es real: `app/routers/purchases.py` (414 líneas: órdenes, estados, recepción a inventario) + `pages/finance/Purchases.tsx`. Ocultarlo le quitaría esa pantalla a las tiendas Retail que ya la usan. Se retiró solo el relleno: `/purchasing` redirige a `/purchases`. | PRO+ | RET, ENT |
| `logistics` | disponible (**dudoso**) | «Logística» `/logistics` = traspasos entre sucursales (`pages/inventory/Logistics.tsx` → `app/routers/transfers.py`, sin gate). «Cajas y contenedores» `/boxes` también cuelga de `logistics` en el menú, pero su backend exige `warehouse`: con `logistics` encendido y `warehouse` apagado esa pantalla da 403. **Las claves están cruzadas** (ver §4). | PRO+ | ENT |
| `customer_portal` | disponible (**dudoso**) | El megaplan decía «sin código». Sí hay: `app/routers/portal.py` (cuentas, saldo, movimientos, cotizaciones) + `pages/portal/Portal.tsx` + alta de la cuenta desde Clientes (`app/modules/customers/router.py::_vincular_portal_a_org`). Pero **la clave no gobierna nada**: el portal funciona en cualquier organización con CRM, en cualquier plan. No está en el catálogo de despliegue. | BUSINESS+ | ninguno v2 (fallback viejo `AUTO_REPAIR_SHOP`) |
| `finance` | disponible (**parcial**) | Solo «Gastos»: `app/routers/expenses.py` + `pages/finance/Expenses.tsx`. El catálogo promete «cuentas por cobrar/pagar»: por cobrar vive en CRM (`/customers/cobranza`), por pagar no existe. | BUSINESS+ | ENT |
| `hr` | disponible (**parcial**) | Expedientes y asistencia: `app/routers/hr.py` + `pages/hr/HR.tsx`, `HRMe.tsx`. El catálogo promete «nómina básica»: no existe. | BUSINESS+ | ENT |
| `tables`, `kitchen`, `recipes`, `bar`, `menu` | disponible (**sin verificar en operación**) | Backend y pantallas reales: `app/modules/{tables,kitchen,recipes,bar}/` + `pages/tables/FloorPlan.tsx`, `pages/kitchen/KDS.tsx`, `pages/recipes/`, `pages/bar/Botellas.tsx`, `pages/menu/MenuVisual.tsx`, comanda móvil. Por código están completos; el megaplan deja Gastro «pendiente, con plan aparte», así que su calidad operativa no la avala esta auditoría. | — (vertical) | GAS\*, RES, CAF, BAR-B, ENT |

### 1.2 Disponibles

| Módulo | Evidencia | Planes | Presets |
|---|---|---|---|
| `core` | arranque, auth, organización (`app/modules/{auth,tenants}`) | B | todos |
| `pos` | `app/routers/sales.py` (`require_module("pos")`) + `pages/pos/POS.tsx` | B | todos menos SER y CUS |
| `catalog` | `app/modules/products/router/core.py` + `pages/inventory/Products.tsx` | B | todos menos CUS |
| `inventory` | `app/routers/inventory.py`, `app/modules/conteos/` + `pages/inventory/Inventory.tsx`, `conteos/` | B | POS, BOU, RET, BEA\*, GAS\*, B&W, RES, CAF, BAR-B, ENT |
| `cash_management` | `app/routers/cash.py` + `pages/finance/CashHistory.tsx` | B | todos menos SER y CUS |
| `payments` | pagos en `sales.py`/`cash.py` (sin pantalla propia: es el cobro) | B | todos menos CUS |
| `returns` | `app/routers/returns.py` + `pages/sales/Returns.tsx` | B | POS, BOU, RET, ENT |
| `reports` | `app/routers/reports*.py` + `pages/reports/Reportes.tsx` | B | todos menos CUS |
| `crm` | `app/modules/customers/` (`require_module("crm")`) + `pages/crm/Customers.tsx`, `Cobranza.tsx` | B | todos menos CUS |
| `labels` | `app/modules/labels/` + `pages/labels/Labels.tsx` | B | POS, BOU, ENT |
| `scanner` | `pages/scanner/StoreScanner.tsx` (Consultar) sobre el catálogo | B | BOU, ENT |
| `variants` | `app/modules/products/router/variants.py` + matriz en `FormularioProducto` | B | BOU, ENT |
| `pricing` | escalones y precio por sucursal (`app/modules/products/services/`) | B | POS, BOU, RET, ENT |
| `users` | `app/modules/users/` + `pages/core/Users.tsx`. Ojo: la clave no gatea nada (las tiendas POS la tienen apagada y dan de alta cajeras igual). | B | BEA\*, GAS\*, BAR, B&W, HEA, RES, CAF, BAR-B, SER, ENT, CUS |
| `branch_catalog_enablement` | matriz de sucursales (`app/modules/products/services/sucursales.py` + modal en Productos) | B | RET, ENT |
| `quotes` | `app/routers/quotes.py` (`require_module("quotes")`) + `pages/sales/Quotes.tsx`, `QuoteMaker.tsx`, `Seguimiento.tsx` | START+ | RET, SER, ENT |
| `tips` | capacidad `propina` (`app/capacidades/catalogo.json`) + reporte de meseros | — | GAS\*, RES, CAF, BAR-B, ENT |
| `tienda_en_linea` | `app/modules/canal/` + `pages/products/FotosProductos.tsx` | contratación aparte | ninguno |

---

## 2. Planes: qué prometen y qué existe

Regla vigente (`app/services/plans.py`): permitido = base ∪ preset del giro ∪ crecimiento del plan.

| Plan | Crecimiento que promete | Disponible hoy | Sin construir (oculto) |
|---|---|---|---|
| FREE | — | base completa | — |
| START | `quotes`, `promotions` | `quotes` | `promotions` |
| PRO | + `purchasing`, `warehouse`, `logistics`, `invoicing` | `purchasing`, `logistics` | `warehouse`, `invoicing` |
| BUSINESS | + `finance`, `hr`, `commissions`, `memberships`, `customer_portal` | `finance` (gastos), `hr` (expedientes y asistencia), `customer_portal` | `commissions`, `memberships` |
| SCALE | + `ai` | nada nuevo | `ai` |
| ULTRA+ | todo el catálogo | lo anterior + verticales | lo anterior + `appointments`, `workshops`, `manufacturing` |

`GET /api/platform/plans` ahora trae `modulos_no_disponibles` por plan, y «Plan y uso»
(`/platform/organizations/{id}`) lo pinta: «El plan ofrece hoy: … · Sin construir: …».

---

## 3. Los 14 presets

`scripts/init_presets_v2.py::PRESETS`. «Cojo» = su módulo central no está disponible.

| Preset | Legacy | Módulos disponibles | No disponibles que incluye | ¿Cojo? |
|---|---|---|---|---|
| `ATLAS_POS` | no | core, pos, cash_management, catalog, inventory, returns, pricing, payments, reports, labels, crm | — | no |
| `ATLAS_POS_BOUTIQUE` | no | los de POS + scanner, variants | — | no |
| `ATLAS_ONE_RETAIL` | no | los 9 de base POS + crm, branch_catalog_enablement, purchasing, quotes | promotions | no (falta un accesorio) |
| `ATLAS_ONE_BEAUTY` | **sí** | core, users, catalog, inventory, payments, cash_management, crm, pos, reports | appointments, commissions, memberships | **sí** (agenda) |
| `ATLAS_ONE_GASTRO` | **sí** | core, users, catalog, inventory, payments, cash_management, crm, pos, kitchen, tables, menu, bar, recipes, reports, tips | — | no |
| `ATLAS_ONE_BARBER` | no | core, users, catalog, payments, cash_management, crm, pos, reports | appointments, commissions, memberships | **sí** (agenda) |
| `ATLAS_ONE_BEAUTY_WELLNESS` | no | core, users, catalog, inventory, payments, cash_management, crm, pos, reports | appointments, commissions, memberships | **sí** (agenda) |
| `ATLAS_ONE_HEALTH` | no | core, users, catalog, payments, cash_management, crm, pos, reports | appointments, commissions, memberships | **sí** (agenda; además promete «planes de tratamiento», que no existen) |
| `ATLAS_ONE_RESTAURANT` | no | core, users, catalog, inventory, payments, cash_management, crm, pos, kitchen, tables, menu, bar, recipes, reports, tips | commissions | no (falta un accesorio) |
| `ATLAS_ONE_CAFE` | no | core, users, catalog, inventory, payments, cash_management, crm, pos, kitchen, menu, recipes, reports, tips | — | no |
| `ATLAS_ONE_BAR` | no | core, users, catalog, inventory, payments, cash_management, crm, pos, tables, menu, bar, recipes, reports, tips | commissions | no (la descripción promete «bartenders con comisión») |
| `ATLAS_ONE_SERVICES` | no | core, users, catalog, payments, crm, quotes, reports | workshops, appointments, commissions | **sí** (órdenes de trabajo y agenda). Además no trae `pos` ni `cash_management`: no puede cobrar. |
| `ATLAS_ONE_ENTERPRISE` | no | todo lo disponible del catálogo de despliegue | promotions, invoicing, commissions, memberships, ai, appointments, workshops, manufacturing | a medias: la descripción promete «IA, integraciones y todos los módulos» |
| `CUSTOM` | no | core, users | — | no |

Sin módulo central disponible, los cuatro giros de agenda y Services se reducen hoy a
«punto de venta con clientes» (Services, ni eso). Su Inicio (`pages/home/PresetHome.tsx`)
ya no anuncia Agenda, Comisiones ni Membresías; les quedan Clientes, Cobrar y Reportes.

Además de los 14, `capabilities_service.INDUSTRY_PRESETS` conserva un fallback de la
taxonomía previa (`DISTRIBUTOR_POS`, `RESTAURANT_QSR`, `RESTAURANT_FULL`,
`AUTO_REPAIR_SHOP`, `RETAIL_CHAIN`, `CAFE_BAKERY`) que solo se usa si la tabla
`industry_presets` no tiene la fila; nombra `kds`, `work_orders`, `warehouse`,
`invoicing` y `customer_portal`.

---

## 4. Propuesta (requiere decisión del dueño; nada de esto se aplicó)

### 4.1 Qué debería prometer cada plan mientras tanto

| Plan | Promesa propuesta | Cambio en `plans.py` |
|---|---|---|
| START | Cotizaciones y pedidos | sacar `promotions` de `_START` hasta que exista |
| PRO | + Compras y traspasos entre sucursales (Logística) | sacar `invoicing`; decidir `warehouse` (ver abajo) |
| BUSINESS | + Gastos, Personal (expedientes y asistencia), Portal de cliente | sacar `commissions` y `memberships`; no vender «nómina» ni «cuentas por pagar» |
| SCALE | hoy no agrega ningún módulo construido sobre BUSINESS: solo topes (100 usuarios, 20 sucursales) | decidir si `ai` entra aquí o en BUSINESS cuando salga F1 |
| ULTRA+ | todo lo disponible + verticales | sin cambio |

Mientras no se edite `plans.py`, el efecto visible ya es el de esta tabla (lo no
construido está oculto); editar `plans.py` solo evita que la plataforma pueda encender
por plan algo que no existe.

Tres decisiones puntuales:

1. **`warehouse` + `logistics`: unificar la clave.** El menú pide `logistics` y el
   backend de Cajas pide `warehouse`. Propuesta: que `app/routers/logistics.py` exija
   `logistics` (o que «Cajas y contenedores» pida `warehouse` en `navConfig.ts`) y retirar
   la otra clave. Toca `require_module`, por eso no se hizo aquí.
2. **`customer_portal`: o se le pone candado o se regala.** Hoy el portal funciona en
   cualquier plan. Si es de BUSINESS, hay que gatear `app/routers/portal.py` y el alta de
   cuentas de portal; si no, sacarlo de `_BUSINESS` y tratarlo como parte de CRM.
3. **`invoicing`:** separar la casilla de IVA (capacidad `factura`, que sí funciona) de la
   facturación electrónica (CFDI), que no existe. Mientras no haya CFDI, no venderlo.

### 4.2 Presets

- **Retirar los dos legacy** migrando organizaciones: `ATLAS_ONE_BEAUTY` →
  `ATLAS_ONE_BEAUTY_WELLNESS` (misma lista de módulos) y `ATLAS_ONE_GASTRO` →
  `ATLAS_ONE_RESTAURANT` (misma lista + `commissions`, que sobra). El cambio es de
  `organization.industry_type`; no hay que tocar `organization_modules`.
- **Marcar «en preparación»** (no ofrecer en altas nuevas) hasta que exista Agenda:
  `ATLAS_ONE_BARBER`, `ATLAS_ONE_BEAUTY_WELLNESS`, `ATLAS_ONE_HEALTH`; y hasta que existan
  órdenes de trabajo: `ATLAS_ONE_SERVICES`. `industry_presets.is_deprecated` ya los
  saca de los selectores y los conserva para las organizaciones existentes: basta
  marcarlos `deprecated` con el nombre «(en preparación)», sin columna nueva.
- **Limpiar las listas** de los presets que sí se venden: quitar `commissions` de
  Restaurant y Bar y `promotions` de Retail; redefinir Enterprise como «todo lo
  disponible» y corregir su descripción.
- **Dejar vendibles hoy:** `ATLAS_POS`, `ATLAS_POS_BOUTIQUE`, `ATLAS_ONE_RETAIL`, `CUSTOM`,
  y —si el plan de Gastro los avala— Restaurant, Café y Bar.

### 4.3 Qué organizaciones habría que migrar

Esta auditoría no vio producción. Consultas (solo lectura) para averiguarlo:

```sql
-- 1. Cuántas organizaciones hay por preset y plan
SELECT CAST(industry_type AS TEXT) AS preset, COALESCE(plan, '(null)') AS plan, COUNT(*)
FROM organization GROUP BY 1, 2 ORDER BY 1, 2;

-- 2. Organizaciones en presets legacy o cojos (las que habría que migrar o avisar)
SELECT id, name, CAST(industry_type AS TEXT) AS preset, plan
FROM organization
WHERE CAST(industry_type AS TEXT) IN (
  'ATLAS_ONE_BEAUTY', 'ATLAS_ONE_GASTRO',                                  -- legacy
  'ATLAS_ONE_BARBER', 'ATLAS_ONE_BEAUTY_WELLNESS', 'ATLAS_ONE_HEALTH',     -- sin agenda
  'ATLAS_ONE_SERVICES', 'ATLAS_ONE_ENTERPRISE',
  'DISTRIBUTOR_POS', 'RESTAURANT_QSR', 'RESTAURANT_FULL',                  -- taxonomía previa
  'AUTO_REPAIR_SHOP', 'RETAIL_CHAIN', 'CAFE_BAKERY')
ORDER BY 3, 1;

-- 3. Quién tiene ENCENDIDO un módulo que ahora se oculta (siguen encendidos; solo no se ven)
SELECT o.id, o.name, o.plan, CAST(o.industry_type AS TEXT) AS preset, om.module_key
FROM organization_modules om
JOIN organization o ON o.id = om.organization_id
WHERE om.is_enabled
  AND om.module_key IN ('promotions', 'warehouse', 'invoicing', 'commissions', 'memberships',
                        'ai', 'appointments', 'workshops', 'manufacturing', 'kds', 'work_orders')
ORDER BY o.id, om.module_key;

-- 4. Claves cruzadas: quién tiene una sola de logistics / warehouse
SELECT o.id, o.name,
       BOOL_OR(om.module_key = 'logistics') AS logistics,
       BOOL_OR(om.module_key = 'warehouse') AS warehouse
FROM organization_modules om
JOIN organization o ON o.id = om.organization_id
WHERE om.is_enabled AND om.module_key IN ('logistics', 'warehouse')
GROUP BY o.id, o.name
HAVING BOOL_OR(om.module_key = 'logistics') <> BOOL_OR(om.module_key = 'warehouse');

-- 5. Quién usa de verdad lo dudoso (antes de mover planes)
SELECT organization_id, COUNT(*) FROM purchase_orders GROUP BY 1;   -- Compras
SELECT organization_id, COUNT(*) FROM appointments GROUP BY 1;      -- Agenda (por API)

-- 6. Filas de presets que existen en la base (incluye las de la taxonomía previa)
SELECT industry_type, display_name, is_deprecated, modules FROM industry_presets ORDER BY 1;
```

Los nombres de tabla salen de los modelos (`organization`, `organization_modules`,
`industry_presets`, `purchase_orders`, `appointments`).

---

## 5. Qué se oculta hoy y dónde

| Lugar | Qué hace | Archivo |
|---|---|---|
| Menú lateral | un ítem cuyo `module` no está disponible no se pinta, ni con el módulo encendido ni mientras carga el contexto | `components/layout/navVisibility.ts` |
| Rutas | `/appointments`, `/commissions`, `/memberships`, `/ai` mandan al inicio del rol; `/purchasing` a `/purchases`. Las páginas «Próximamente» se borraron. | `App.tsx` |
| Inicio por giro | widgets y acciones rápidas de módulos sin construir no se pintan ni entran a la tarjeta «Tu plan»; subtítulos sin promesas | `pages/home/PresetHome.tsx` |
| Upsell de plataforma | no recomienda lo no construido | `app/routers/platform/organizations.py::get_upsell_recommendations` |
| Plan y uso (plataforma) | separa «ofrece hoy» de «sin construir» | `pages/platform/PlatformOrgDetail.tsx`, `GET /platform/plans` |
| Activación de módulos (plataforma) | **no se esconde**: marca «En construcción» / «No construido» y deja encender | `PlatformOrgDetail.tsx`, `PlatformModules.tsx`, `PlatformPresets.tsx` |
| Canal | `/users/me/context` → `modulos_no_disponibles` (`{clave: estado}`); `enabled_modules` no se recorta | `app/modules/users/router.py` |
