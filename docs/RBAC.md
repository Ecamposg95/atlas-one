# RBAC, Autenticación y Multi-tenancy · Atlas BOS

Quién puede hacer qué, y cómo se aísla cada tenant. Fuente: auditoría profunda (julio 2026).

Archivos load-bearing:
- Roles/modelo: `app/modules/users/models.py`
- Matriz de vistas por rol: `app/core/role_permissions.py`
- Auth core: `app/core/security/{auth,jwt,config,passwords,guards}.py`
- Login/switch/logout: `app/modules/auth/router.py`
- Gating por módulo: `app/core/permissions.py`
- Resolución de módulos: `app/services/capabilities_service.py`, `app/models/modules.py`
- Tenancy: `app/core/tenant_context.py`, `app/core/tenant_query.py`, `app/models/mixins.py`
- Platform guards: `app/modules/platform/dependencies.py`
- Impersonación: `app/routers/platform/impersonation.py`, `app/main.py:268-279`

---

## 1. Dos ejes de identidad

Un mismo registro `User` tiene **dos roles ortogonales**:
- `role` — rol de **tenant** (enum `Role`, default `CAJERO`).
- `platform_role` — rol de **plataforma SaaS** (enum `PlatformRole`, default `NONE`).

Un usuario pertenece a una o más organizaciones vía `UserOrganization` (PK compuesta `user_id + organization_id`, con `org_role` = ADMIN/MEMBER/OWNER, distinto del `role` de tenant).

### Roles de tenant (`Role`)

| Rol | Contexto | Home | Alcance |
|---|---|---|---|
| **ADMINISTRADOR** | HQ | `/hq/operations` | Máximo tenant: HQ ops/reportes/control, catálogo, organización, usuarios, clientes, sucursales, inventario, ventas, compras, gastos, HR. **Bypass de gating por módulo.** Puede cambiar de contexto/sucursal. |
| **DUEÑO** | HQ | `/hq/operations` | Como admin pero reducido (sin organización, usuarios, HR, gestión de sucursales). **Bypass de gating por módulo.** |
| **GERENTE** | Sucursal | `/atlas-pos` | POS + reportes de sucursal: pos, caja, ventas, productos, reportes, devoluciones. Puede cerrar cajas de otros. |
| **CAJERO** | Sucursal | `/atlas-pos` | Solo POS: pos, caja, productos, config impresora, ventas, devoluciones, reportes. Ventas: las de su sucursal dentro del plazo de la tienda (`organization.dias_ventas_caja`, 30 días por omisión; 0 = solo hoy; día de México), sin totales del día (`/sales/stats`, `/sales/export/csv` y `/reports/{daily-summary,dashboard,sales-by-hour,export/csv,command-center/stats}` → 403); `/sales/by-folio` solo encuentra las de ese plazo (si no, 404); devoluciones solo de ventas de su sucursal dentro del mismo plazo, por el método con que se pagó y con turno abierto si es efectivo; las aprueba sola hasta `organization.devolucion_libre_hasta` (0 por omisión = nunca) y arriba de eso un gerente autoriza con su PIN en la caja (`POST /returns/{id}/autorizar`) o después (2026-11-24; el GERENTE conserva el histórico y el criterio). Regla única: `app/services/ventas_cajero.py`. `/sales/my-last` también solo de hoy. Caja (2026-11-17; solo mientras la tienda tenga el conteo ciego encendido, `cajera_a_ciegas`): con su turno abierto `/api/branch/dashboard` y `/api/cash/summary` no le mandan importes que despejen el esperado; `/api/cash/summary?session_id=` y `/api/cash/history` solo sus propios turnos de hoy. |
| **VENDEDOR** | Sucursal (mostrador) | `/atlas-pos` | Menú corto desde 2026-11-20: Mi día, Cobrar, Ventas, Corte de caja, Clientes y Productos (solo consulta). Misma regla de ventas y devoluciones que la cajera (`ventas_cajero.es_cajero`): su sucursal, el plazo de la tienda, sin totales. |
| **SOPORTE_OPERATIVO** | Móvil | `/mobile/dashboard` | Móvil solo-consulta (sin ventas). |
| **CLIENTE** | Portal | `/portal` | Solo portal de clientes (estado de cuenta cross-org por email). |

> `Role` hereda de `str, Enum`; el código compara a veces con el enum (`Role.GERENTE`) y a veces con strings (`"ADMINISTRADOR"`) — funciona por igualdad de valor, pero es frágil.

### Roles de plataforma (`PlatformRole`)

| Rol | Alcance | Guard |
|---|---|---|
| **SUPERADMIN** | Staff total de plataforma: cualquier org, ops destructivas. | `require_superadmin` |
| **SUPPORT** | Staff read-only; puede entrar a `/api/platform/*`, pero las ops destructivas revalidan SUPERADMIN dentro del handler. | `require_platform_admin` |
| **NONE** | Usuario normal de tenant (default). | — |

---

## 2. Autenticación

- **Password = PIN**, hasheado con bcrypt (passlib). Helpers en `app/core/security/passwords.py`.
- **JWT HS256**, `SECRET_KEY` de env (⚠️ **fallback hardcodeado inseguro** si no se setea — solo emite warning). Expira en **12h**.

### Flujo de login (`POST /api/auth/login`, OAuth2 password form)
```
username + password(=PIN)
  → get_user_by_username (filtra is_active) ; 401 si no existe
  → verify_pin ; 401 si falla
  → contexto inicial: ADMIN/DUEÑO/SUPERADMIN → HQ (ctx_id=None) ; resto → su branch
  → create_access_token(sub=username, role, ctx_id, ctx_type)   [claims: sub, role, ctx_id, ctx_type, exp]
  → Set-Cookie access_token="Bearer <jwt>" (httponly, samesite=lax, secure según COOKIE_SECURE)
  → resuelve org = primera membresía ACTIVA del user (orden fijo)
  → devuelve { access_token, user, organization, branch }
```

`get_current_user` (`app/core/security/auth.py`): lee el token del header `Authorization` **o** de la cookie; decodifica, **relee el User de la DB** (la BD manda; el claim `role` es informativo); 403 si `is_active=False`; adjunta `ctx_id`/`ctx_type` a `request.state`.

Otros: `POST /api/auth/context/switch?branch_id=` (reemite JWT con nuevo contexto — solo ADMIN/SUPERADMIN o `org_role=ADMIN`), `POST /api/auth/logout` (borra cookies `access_token` + `support_org_id`).

---

## 3. Autorización (RBAC dual)

Dos mecanismos paralelos (el código los reconoce como "dual RBAC" pendiente de unificar):

### A) Gating por rol
1. **Matriz de vistas** `ATLAS_POS_ROLE_VIEWS` (`role_permissions.py`): rol → templates permitidos. Alimenta el nav/sidebar del frontend (`get_atlas_pos_nav`, `/users/me/context`). Es gating de **UI/navegación**, no de datos.
   - **Frontend:** el menú y las guardas de ruta salen de `ROLE_ROUTES` (`frontend/src/components/layout/navConfig.ts`; `rolesConAcceso` + `RutaPorRol`). Desde la Fase 3 del admin (2026-10-25) ADMINISTRADOR y DUEÑO tienen `/returns` e `/inventory`, y `/hq/sales`, `/hq/returns`, `/hq/inventory` y `/admin/catalog` solo redirigen. `/returns` no lleva `module:` ni `RutaPorRol` propio y `/inventory` no lleva `hideForGastro` (a propósito: un solo ítem sirve a todos los roles y giros); `/reports` lo alcanzan ADMINISTRADOR/DUEÑO (por `/hq/reports-hub`) y GERENTE, no CAJERO (no está en su `ROLE_ROUTES`). `TEMPLATE_METADATA` de `role_permissions.py` y `app/ui/nav_registry.py` aún listan esas URL viejas: el frontend no los consume y el redirect las cubre (deuda, no bloqueante).
2. **Guards**: `require_admin_or_owner` (SUPERADMIN o ADMIN/DUEÑO).
3. **Checks inline ad-hoc**: ~67 sitios comparan `current_user.role` directamente. No hay decorador central de rol.

### B) Gating por módulo — `require_module(key)` (`app/core/permissions.py`)
Dependencia que exige que `key` esté habilitado (`OrganizationModule.is_enabled`) para la org activa. **ADMINISTRADOR y DUEÑO hacen bypass total.** Solo **3 routers** lo aplican a nivel router: `sales`→`pos`, `logistics`→`warehouse`, `quotes`→`quotes`. El resto (`cash`, `returns`, `purchases`, `expenses`, `transfers`, `inventory`, `reports`, `hr`, y **todos los módulos gastro**) **no** exige módulo — accesible con solo auth + tenant scope.

### Resolución de módulos habilitados de una org
- Habilitación viva: tabla `organization_modules`. La lee `/api/users/me/context` → `enabled_modules = {"core", …módulos activos}` (`core` siempre habilitado). Es lo que consume el Sidebar del frontend.
- Se siembra desde presets: `apply_industry_preset` toma de `industry_presets` (DB = fuente de verdad; fallback a dict hardcodeado `INDUSTRY_PRESETS`), filtra keys inexistentes contra el catálogo `modules`, y hace upsert.

> **Nota (2026-09-30): Los 403 por tope de plan (`app/services/plans.py`) no son RBAC:** dependen de la organización, no del rol. Un ADMINISTRADOR en una org FREE al tope recibe 403 al crear el tercer usuario.

---

## 4. Multi-tenancy (ver también ARCHITECTURE.md §4)

- **Aislamiento por organización**: fuerte pero de cobertura desigual (solo ~6 módulos usan los helpers `get_tenant_scoped`/`scoped_query`; el resto filtra a mano).
- **Aislamiento por sucursal**: **NO enforced a nivel framework** — ad-hoc por router.
- **Impersonación** (staff → org): dos mecanismos. (a) cookie `support_org_id` (la que realmente afecta queries, leída en la precedencia de `get_current_active_organization`); (b) `POST /api/platform/impersonate` — **audita** (`PlatformAuditLog` START/END con `reason`) pero es un **stub**: no emite JWT scoped ni marca `impersonator_id`.

---

## 5. ⚠️ Huecos de seguridad conocidos

Priorizados; la numeración es la de la auditoría original y no se recicla. Cada hueco dice su estado: **ABIERTO**, **PARCIAL** o **RESUELTO** (con fecha). Resumen al 2026-11-24: resueltos 3, 4, 8 y 12; parcial 10; abiertos 1, 2, 5, 6, 7, 9 y 11.

1. **ABIERTO — SECRET_KEY con fallback hardcodeado** (`security/config.py`) — si no se setea la env var, los JWT son firmables por cualquiera que lea el repo. Solo emite warning. **Setear SECRET_KEY en todos los entornos.**
2. **ABIERTO — Branch scoping no enforced** — `ctx_id`/`ctx_type` del token no se aplican a queries; `tenant_query` solo filtra por org. Fuga cross-sucursal posible en endpoints que confían en un `branch_id` de query param. Se cierra endpoint por endpoint, no a nivel framework: el 2026-11-24 `/reports/audit/discrepancies` y `/reports/command-center/stats` pasaron a respetar el ámbito por rol (`metricas_ventas.ambito_sin_eleccion`: dueño/administrador/superadmin ven la organización; el gerente, solo su sucursal; detalle por rol en `docs/API_REFERENCE.md`).
3. **RESUELTO 2026-11-24 — `set-support-context` sin guard de auth.** `POST /api/platform/set-support-context` y `clear-support-context` (`app/main.py`) exigen `require_platform_admin` (SUPERADMIN o SUPPORT), y el lector de la cookie (`app/core/tenant_context.py`) la ignora si quien la trae no es personal de plataforma. Sigue abierto lo que describe el hueco 9: fijar el tenant por esta cookie no pasa por el flujo `/impersonate` auditado.
4. **RESUELTO 2026-11-24 — `context/switch` no validaba la sucursal.** Ahora la sucursal debe ser de una organización donde el usuario tiene membresía activa (el SUPERADMIN entra a cualquiera); si no, 404.
5. **ABIERTO — SUPERADMIN + `X-Organization-ID` sin verificación de membresía** (por diseño) — amplifica el impacto de un token superadmin comprometido; sin marca de impersonación en las acciones de datos.
6. **ABIERTO — Cobertura baja de helpers de tenancy** — el resto filtra a mano; `TenantMixin.organization_id` es nullable → filas sin org pueden filtrarse mal.
7. **ABIERTO — Bypass de gating por módulo para ADMIN/DUEÑO** + solo 3 routers con `require_module` → el gating por módulo es casi inefectivo como control de seguridad (sirve como feature-flag, no como candado).
8. **RESUELTO 2026-11-24 — Login resolvía la org con el PRIMER `UserOrganization` sin filtrar `is_active`.** El login (y el acceso a cortes) solo considera membresías activas, en orden fijo. Un usuario multi-org sigue entrando a la primera de ese orden y cambia con `X-Organization-ID`.
9. **ABIERTO — Impersonación real es un stub** — sin claim `impersonator_id`; acciones durante impersonación se atribuyen al SUPERADMIN sin marca de "actuando como".
10. **PARCIAL — Platform: gating inconsistente.** Resuelto el 2026-11-24: `bootstrap_organization`, `assign_org_admin` y `export_organization_data` exigen `require_superadmin`, y `PUT /organizations/{id}` responde 403 a SUPPORT si el cuerpo trae `plan` (el plan mueve la suscripción; lista en `_SOLO_SUPERADMIN` de `app/routers/platform/organizations.py`). **Sigue abierto:** SUPPORT (read-only por convención) conserva escrituras con solo el guard `require_platform_admin` — crear organización (`POST /organizations`), editar el resto de la ficha (incluye `status`, `is_active`, `industry_type`, `perfil_ui`), archivar/desarchivar, suspender/activar, cambiar giro (`PATCH …/industry`), aplicar/restablecer preset y encender/apagar módulos (`PATCH …/modules/{key}`) — y lee `audit/logs`.
11. **ABIERTO — `users` core sin control de rol** — crear/editar/borrar usuarios solo exige auth + pertenencia a la org, no rol admin.
12. **RESUELTO 2026-11-24 — Cookies `secure=False`.** `access_token` y `support_org_id` salen con `Secure` según `COOKIE_SECURE` (`app/core/security/cookies.py`): `auto` (por omisión) = solo si la petición llegó por https (`X-Forwarded-Proto`), `true` = siempre, `false` = nunca.
