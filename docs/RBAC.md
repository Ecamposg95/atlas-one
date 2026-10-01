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
| **CAJERO** | Sucursal | `/atlas-pos` | Solo POS: pos, caja, productos, config impresora, ventas, devoluciones, reportes. |
| **VENDEDOR** | Móvil | `/mobile/dashboard` | UI móvil de campo: dashboard, consulta, ventas/cotización, perfil. |
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
  → Set-Cookie access_token="Bearer <jwt>" (httponly, samesite=lax, secure=False)
  → resuelve org = PRIMER UserOrganization del user
  → devuelve { access_token, user, organization, branch }
```

`get_current_user` (`app/core/security/auth.py`): lee el token del header `Authorization` **o** de la cookie; decodifica, **relee el User de la DB** (la BD manda; el claim `role` es informativo); 403 si `is_active=False`; adjunta `ctx_id`/`ctx_type` a `request.state`.

Otros: `POST /api/auth/context/switch?branch_id=` (reemite JWT con nuevo contexto — solo ADMIN/SUPERADMIN o `org_role=ADMIN`), `POST /api/auth/logout` (borra cookies `access_token` + `support_org_id`).

---

## 3. Autorización (RBAC dual)

Dos mecanismos paralelos (el código los reconoce como "dual RBAC" pendiente de unificar):

### A) Gating por rol
1. **Matriz de vistas** `ATLAS_POS_ROLE_VIEWS` (`role_permissions.py`): rol → templates permitidos. Alimenta el nav/sidebar del frontend (`get_atlas_pos_nav`, `/users/me/context`). Es gating de **UI/navegación**, no de datos.
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

Priorizados. Estos NO están resueltos — son hallazgos de la auditoría para el backlog.

1. **SECRET_KEY con fallback hardcodeado** (`security/config.py`) — si no se setea la env var, los JWT son firmables por cualquiera que lea el repo. Solo emite warning. **Setear SECRET_KEY en todos los entornos.**
2. **Branch scoping no enforced** — `ctx_id`/`ctx_type` del token no se aplican a queries; `tenant_query` solo filtra por org. Fuga cross-sucursal posible en endpoints que confían en un `branch_id` de query param.
3. **`set-support-context` sin guard de auth en la firma** (`main.py:268`) — puede fijar la cookie de tenant activo (4h); con un SUPERADMIN, fija tenant sin pasar por el flujo `/impersonate` auditado.
4. **`context/switch` no valida** que la sucursal pertenezca a la org del usuario (comentario lo admite).
5. **SUPERADMIN + `X-Organization-ID` sin verificación de membresía** (por diseño) — amplifica el impacto de un token superadmin comprometido; sin marca de impersonación en las acciones de datos.
6. **Cobertura baja de helpers de tenancy** — el resto filtra a mano; `TenantMixin.organization_id` es nullable → filas sin org pueden filtrarse mal.
7. **Bypass de gating por módulo para ADMIN/DUEÑO** + solo 3 routers con `require_module` → el gating por módulo es casi inefectivo como control de seguridad (sirve como feature-flag, no como candado).
8. **Login resuelve org con el PRIMER `UserOrganization` sin filtrar `is_active`** e ignorando multi-org — inconsistente con los resolvers que sí filtran.
9. **Impersonación real es un stub** — sin claim `impersonator_id`; acciones durante impersonación se atribuyen al SUPERADMIN sin marca de "actuando como".
10. **Platform: gating inconsistente** — varios endpoints mutantes/sensibles solo tienen el guard router-level (`require_platform_admin` = SUPERADMIN **o SUPPORT**) sin revalidar SUPERADMIN: `bootstrap_organization` (crea sucursales), `assign_org_admin`, `export_organization_data`, `audit/logs`. SUPPORT (read-only por convención) podría mutar.
11. **`users` core sin control de rol** — crear/editar/borrar usuarios solo exige auth + pertenencia a la org, no rol admin.
12. **Cookies `secure=False`** hardcoded en auth (nota "poner True en prod").
