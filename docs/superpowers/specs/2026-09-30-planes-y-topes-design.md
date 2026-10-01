# Planes y topes de Atlas ONE — diseño

Fecha: 2026-09-30 · Fuente comercial: "Atlas ONE Pricing" (Atlas_Tech, planes y precios MXN, 2 páginas)
· Caso guía: las cuatro novedades (Kaory, Ginebra, Imaltzin, Coqueta) en FREE y Eleven Fashion en ULTRA+

## 1. El problema

El papel de precios define seis planes (FREE, START, PRO, BUSINESS, SCALE, ULTRA+) con funciones y
topes de usuarios y sucursales. En el código, `Organization.plan` es un `String` con valor por omisión
`"FREE"` que **nada lee para decidir nada**: solo lo usan los anuncios (segmentar por plan) y los
incidentes de plataforma (alcance por plan). No hay catálogo de planes, no hay topes, y activar un
módulo desde la plataforma no mira el plan. Las cinco organizaciones vivas están en `FREE`.

Medido en producción el 2026-09-30:

| Org | Preset | Sucursales (venden) | Usuarios activos | Módulos encendidos |
|---|---|---|---|---|
| 14 Kaory | ATLAS_POS | 2 (1) | 2 | base |
| 15 Ginebra | ATLAS_POS | 1 (1) | 2 | base + crm, labels |
| 16 Imaltzin | ATLAS_POS | 1 (1) | 2 | base + crm, labels |
| 17 Eleven | ATLAS_POS_BOUTIQUE | 1 (1) | 4 | base + crm, labels, scanner, variants |
| 18 Coqueta | ATLAS_POS | 1 (1) | 2 | base + crm, labels |

Si el papel se aplicara a rajatabla, FREE le quitaría etiquetas y clientes a las novedades y el
escáner y las variantes a Eleven, y Eleven excedería cualquier tope razonable de usuarios de FREE.

## 2. Decisiones (con el usuario, 2026-09-30)

1. **Techo con base libre.** Los módulos base y los que siembra el preset son de cualquier plan. El
   plan gobierna solo los módulos de crecimiento y los topes de usuarios y sucursales. **Nada se le
   quita a una organización**: cambiar de plan no apaga módulos; los topes solo frenan altas nuevas.
2. **Topes:** usuarios activos FREE 2 / START 3 / PRO 10 / BUSINESS 25 / SCALE 100 / ULTRA+ sin tope;
   sucursales que venden FREE 1 / START 1 / PRO 2 / BUSINESS 5 / SCALE 20 / ULTRA+ sin tope.
3. **Eleven Fashion queda en ULTRA+.** Las cuatro novedades siguen en FREE.
4. Catálogo **en código**, no en tabla: el papel cambia poco y una tabla sería YAGNI.
5. Fuera de alcance: cobro de la mensualidad, visitas y soporte, Cortex y automatizaciones (no son
   módulos hoy), apagar módulos a quien ya los usa.

## 3. Catálogo de planes (`app/services/plans.py`)

Claves de almacenamiento (van en `organization.plan`): `FREE`, `START`, `PRO`, `BUSINESS`, `SCALE`,
`ULTRA_PLUS`. Nombre visible de la última: "ULTRA+". El orden importa: cada plan incluye todo lo del
anterior.

```python
@dataclass(frozen=True)
class Plan:
    clave: str                 # "FREE"
    nombre: str                # "ONE FREE"
    precio_mxn: Optional[int]  # 0, 499, 999, 5000, 10000, 30000 ("desde") — informativo
    max_usuarios: Optional[int]        # None = sin tope
    max_sucursales_venta: Optional[int]
    modulos_crecimiento: frozenset[str]  # ACUMULADO (incluye los de los planes anteriores)
    lema: str                  # "Digitaliza", "Opera", …
```

| Clave | Nombre | Precio | Usuarios | Suc. venta | Módulos de crecimiento (acumulados) |
|---|---|---|---|---|---|
| FREE | ONE FREE | 0 | 2 | 1 | — |
| START | ONE START | 499 | 3 | 1 | `quotes`, `promotions` |
| PRO | ONE PRO | 999 | 10 | 2 | + `purchasing`, `warehouse`, `logistics`, `invoicing` |
| BUSINESS | BUSINESS | 5000 | 25 | 5 | + `finance`, `hr`, `commissions`, `memberships`, `customer_portal` |
| SCALE | SCALE | 10000 | 100 | 20 | + `ai` |
| ULTRA_PLUS | ULTRA+ | 30000 | None | None | todos los del catálogo |

**Módulos base** (permitidos en cualquier plan, constante `MODULOS_BASE`): `core`, `pos`, `catalog`,
`inventory`, `cash_management`, `payments`, `returns`, `reports`, `crm`, `labels`, `scanner`,
`variants`, `pricing`, `users`, `branch_catalog_enablement`.

**Módulos de preset:** todo lo que siembra `apply_industry_preset` para el giro de la organización
(`init_presets_v2.py`, p. ej. `tables`, `kitchen`, `kds`, `menu`, `recipes`, `bar`, `tips`,
`appointments`, `workshops`, `work_orders`, `manufacturing`). Un restaurante FREE conserva mesas y
cocina: el plan nunca pelea con el preset.

**Regla:**

```
permitido(org, modulo) = modulo ∈ MODULOS_BASE
                      ∪ modulos_del_preset(org.industry_type)
                      ∪ PLANES[org.plan].modulos_crecimiento
```

Funciones públicas del servicio (todas puras salvo las que reciben `db`):

- `obtener_plan(clave: str | None) -> Plan` — `None`/vacío/desconocido → `FREE` (compatibilidad con
  filas viejas). `es_plan_valido(clave) -> bool` para la validación del `PUT`.
- `modulos_permitidos(db, org) -> set[str]` — la unión de arriba. Usa la lista del preset del
  catálogo (`INDUSTRY_PRESETS` de `init_presets_v2` o el fallback de `capabilities_service`), no los
  módulos encendidos: lo que pregunta es qué se *puede* encender.
- `plan_minimo_para(modulo: str) -> Plan | None` — el primer plan (en orden) cuyo
  `modulos_crecimiento` lo incluye; `None` si es base o de preset (es decir, no depende del plan).
- `uso(db, org_id) -> Uso(usuarios_activos: int, sucursales_venta: int)` — cuenta `UserOrganization`
  activos cuyo `User.is_active` sea verdadero y cuyo `platform_role` sea `NONE` (el personal de
  plataforma enlazado para soporte no consume el tope del cliente), y `Branch.is_active and can_sell`.
- `verificar_alta_usuario(db, org) -> None` y `verificar_alta_sucursal(db, org, can_sell: bool) -> None`
  — lanzan `LimitePlanAlcanzado(ValueError)` con el mensaje accionable; los routers lo convierten a
  403.
- `verificar_activar_modulo(db, org, modulo) -> None` — lanza `ModuloFueraDePlan(ValueError)` con el
  plan mínimo en el mensaje.

Mensajes (español, accionables; son los que ve el admin de la tienda en el toast):

- `"Tu plan ONE FREE permite 2 usuarios activos. Para agregar más, sube a ONE START."`
- `"Tu plan ONE FREE permite 1 sucursal que vende. Para abrir otra, sube a ONE PRO."` (el plan
  mínimo que suba el tope, no simplemente el siguiente)
- `"El módulo Cotizaciones requiere el plan ONE START o superior (la organización está en ONE FREE)."`

## 4. Dónde se hace valer

| Punto | Archivo | Comportamiento |
|---|---|---|
| Crear usuario | `app/modules/users/router.py::create_user` | antes de escribir, `verificar_alta_usuario`; si falla → `HTTPException(403, detail=mensaje)`. Reactivar un usuario inactivo (`PUT` con `is_active=True`) también cuenta como alta y pasa por el mismo guard. |
| Crear sucursal | `app/routers/branches.py::create_branch` | si la sucursal resultante tiene `can_sell=True`, `verificar_alta_sucursal` → 403. Marcar `can_sell=True` en una existente por `PUT` también pasa por el guard. Matriz sin venta, almacenes y oficinas no cuentan. |
| Activar módulo | `app/routers/platform/organizations.py::toggle_org_module` (enable=True) | `verificar_activar_modulo` → 403 con el plan mínimo. Apagar nunca se bloquea. |
| Cambiar plan | `app/routers/platform/organizations.py::update_organization` (ya acepta `plan`) | `es_plan_valido` o 400 con la lista de claves válidas. Cambiar el plan **no** toca `organization_modules`. Registra en el log de auditoría de plataforma como hoy hace el toggle de módulos. |
| Alta por script | `scripts/onboard_org.py` | `--plan` valida contra el catálogo (hoy acepta cualquier texto). |
| `require_module` | `app/core/permissions.py` | **sin cambios**: sigue leyendo `organization_modules.is_enabled`. Es lo que garantiza que nada se apaga. |
| `apply_industry_preset` | `app/services/capabilities_service.py` | **sin cambios**: los módulos del preset son siempre permitidos. |

Los anuncios (`app/routers/announcements.py`, `platform/announcements.py`) e incidentes
(`platform/incidents.py`) comparan `org.plan` contra cadenas: siguen funcionando porque las claves
son las mismas cadenas; `ULTRA_PLUS` es la única nueva.

## 5. API nueva y cambios de respuesta

- `GET /api/platform/plans` (solo plataforma): lista ordenada del catálogo con `clave`, `nombre`,
  `precio_mxn`, `max_usuarios`, `max_sucursales_venta`, `modulos_crecimiento` (lista) y `lema`.
- `GET /api/platform/organizations/{id}` (lo que ya devuelve el detalle) gana un bloque
  `plan_uso`: `{plan: {...}, usuarios_activos, sucursales_venta, modulos_fuera_de_plan: [claves]}`
  donde `modulos_fuera_de_plan` son los **encendidos** que el plan actual no cubre (heredados).
- `GET …/organizations/{id}/modules` (listado que pinta el toggle): cada módulo gana
  `plan_minimo: clave | null` y `permitido_por_plan: bool`.
- `GET …/organizations/{id}/upsell-recommendations`: cada recomendación gana `plan_minimo`.

## 6. Pantallas

**Plataforma, detalle de organización** (`PlatformOrgDetail.tsx`):
- Selector de plan (las seis opciones con nombre y precio) que llama al `PUT` existente; confirma
  con el `ConfirmDialog` del kit cuando se baja de plan, con el texto "No se apaga ningún módulo;
  solo cambian los topes para altas nuevas".
- Tarjeta de uso: "Usuarios activos 2 de 2 · Sucursales que venden 1 de 1" (sin tope → "sin tope").
- En la lista de módulos: etiqueta "Requiere ONE PRO" en los apagados que el plan no cubre (el
  toggle sigue visible; al intentar encender, el 403 llega al toast) y "Fuera de plan" en los
  encendidos heredados.

**Plataforma, lista de organizaciones** (`PlatformOrganizations.tsx`): columna "Plan" y filtro.

**Lado tienda:** sin pantallas nuevas. Los formularios de alta de usuario y de sucursal ya muestran
el `detail` del error en un toast; el mensaje del §3 es lo que ve el admin.

## 7. Datos iniciales

- Kaory, Ginebra, Imaltzin, Coqueta: `FREE` (ya lo están; no se toca).
- Eleven Fashion: `ULTRA_PLUS` por el `PUT` de plataforma una vez desplegado (o SQL de una fila con
  permiso). Con eso sus 4 usuarios y sus módulos de boutique quedan dentro de plan.
- Sin migración de esquema: `organization.plan` ya existe como `String`. `railway_init.py` no cambia.

## 8. Pruebas (SQLite, `tests/test_planes.py` + ajustes en los existentes)

1. Catálogo: seis planes en orden; cada `modulos_crecimiento` contiene al del anterior; todos los
   módulos de crecimiento existen en el catálogo `modules` de `seed_global_modules`; `obtener_plan`
   con `None`, `""` y `"XYZ"` devuelve FREE; `es_plan_valido("ULTRA_PLUS")`.
2. `modulos_permitidos`: org ATLAS_POS en FREE → base ∪ preset, sin `quotes`; en START → con
   `quotes`; org ATLAS_ONE_GASTRO en FREE → incluye `tables` y `kitchen`.
3. `plan_minimo_para("quotes") == START`, `("ai") == SCALE`, `("pos") is None`, `("tables") is None`.
4. Crear usuario: org FREE con 2 activos → 403 y el mensaje nombra START; con 1 activo → 201; un
   usuario inactivo no cuenta; reactivar por `PUT` cuando ya hay 2 activos → 403; ULTRA_PLUS nunca
   bloquea.
5. Crear sucursal: org FREE con 1 que vende → crear otra `STORE` → 403 nombrando PRO; crear
   `WAREHOUSE` → 201; crear `STORE` con `can_sell=False` → 201; `PUT can_sell=True` sobre esa → 403.
6. Toggle de módulo (plataforma): encender `quotes` en FREE → 403 con START en el mensaje; en START
   → 200; apagar siempre 200; encender `tables` en gastro FREE → 200.
7. Cambio de plan: `PUT plan="PRO"` → 200 y `organization_modules` idéntico antes y después;
   `plan="GOLD"` → 400 con las claves válidas.
8. Herencia: org FREE con `quotes` encendido a mano → `require_module("quotes")` sigue dejando pasar;
   el detalle lo lista en `modulos_fuera_de_plan`.
9. `GET /api/platform/plans` requiere plataforma (403 para un admin de tienda) y devuelve 6.
10. Regresión: `test_seed_presets`, `test_crm_en_presets_pos`, `test_boutique_preset`,
    `test_module_upsell_metadata`, `test_platform_security`, anuncios e incidentes sin cambios de conteo.

## 9. Riesgos

- **Conteo de usuarios por organización.** `users.username` es global y un usuario puede estar en
  varias organizaciones por `user_organizations`; el tope cuenta enlaces activos a *esta* org con
  usuario activo. Un superadmin de plataforma enlazado a una org (soporte) contaría: se excluye
  `platform_role != NONE` del conteo.
- **Preset `CUSTOM` y presets sin lista.** `modulos_del_preset` devuelve vacío → solo base + plan.
  Aceptado; CUSTOM es manual por definición y el toggle sigue disponible dentro del plan.
- **Topes al revés de la realidad.** Si algún día una org tiene más usuarios de los que su plan
  permite (p. ej. se le baja el plan), nada se rompe: solo no puede dar de alta otro. La tarjeta de
  uso lo muestra en rojo.
- **Cadena `ULTRA_PLUS` en filtros de anuncios/incidentes.** Verificado el 2026-09-30 en producción: no
  hay anuncios ni incidentes segmentados por plan, ni usuarios de plataforma enlazados a organizaciones
  de clientes. No hay datos viejos que migrar.
