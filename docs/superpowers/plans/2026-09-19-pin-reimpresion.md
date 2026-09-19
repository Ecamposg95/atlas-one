# PIN de reimpresión por usuario Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un administrador/dueño/gerente puede fijar desde el panel de Usuarios un PIN numérico de reimpresión (4–8 dígitos) independiente de su contraseña; el POS acepta ese PIN al reimprimir, y sigue aceptando la contraseña de un supervisor como hasta hoy.

**Architecture:** Columna `users.reprint_pin_hash` (String, nullable; ALTER idempotente en `scripts/railway_init.py`), hash con `get_password_hash`. `UserCreate`/`UserUpdate` aceptan `reprint_pin` (validador 4–8 dígitos, `""` borra), `UserRead` expone `has_reprint_pin` (derivado, nunca el hash). `verificar_pin_supervisor` prueba PRIMERO los PIN configurados (`reprint_pin_hash`) de los supervisores y DESPUÉS las contraseñas, con el mismo orden sucursal → resto de la org. Panel de Usuarios: campo "PIN de reimpresión" solo para roles gerenciales, con indicador "PIN configurado" y opción de borrarlo. Referencia de origen: repo `/mnt/d/Devs/Atlas-Rmazh` (`app/models/users.py`, `app/schemas/users.py`, `app/routers/users.py`, `app/services/reprint_auth.py`, `frontend/src/pages/core/Users.tsx`).

**Tech Stack:** FastAPI + SQLAlchemy + Pydantic v2; React/TS.

**Spec:** este documento (diseño incluido arriba). Contexto: el dueño de Eleven Fashion quiere que `eleven` tenga PIN `1234` sin que sea su contraseña.

## Global Constraints

- Nunca exponer `reprint_pin_hash` en ninguna respuesta; solo `has_reprint_pin: bool`.
- El PIN se compara solo contra usuarios activos, con membresía activa en la org, rol en `ROLES_GERENCIALES` (ADMINISTRADOR, DUEÑO, GERENTE). El comportamiento actual (contraseña de supervisor) se conserva intacto como segundo intento; `tests/test_reprint_pin.py` debe seguir verde sin cambios.
- Límite anti fuerza bruta existente sin cambios.
- Migración: entrada en la lista `migrations` de `scripts/railway_init.py` con el patrón `("users", "reprint_pin_hash", "ALTER TABLE users ADD COLUMN reprint_pin_hash VARCHAR;")`.
- Tests: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py` (baseline 872 passed en main); `npx tsc --noEmit && npm run build` desde `frontend/`.
- Commits con `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` y `Claude-Session: https://claude.ai/code/session_01Lug2gDi7z3wjW7VJyjctTb`.

---

### Task 1: PIN de reimpresión por usuario (backend + panel de usuarios)

**Files:**
- Modify: `app/modules/users/models.py` (`User`: `reprint_pin_hash = Column(String, nullable=True)` + propiedad `has_reprint_pin`), `app/modules/users/schemas.py` (`reprint_pin: Optional[str]` en `UserCreate` y `UserUpdate` con validador; `has_reprint_pin: bool = False` en `UserRead`), `app/modules/users/router.py` (crear: hashear si viene; actualizar: `""`/None borra, valor hashea; nunca `setattr` del campo crudo), `app/services/reprint_auth.py` (`_primer_match` recibe qué hash comparar; `verificar_pin_supervisor` prueba PIN y luego contraseña), `scripts/railway_init.py` (ALTER).
- Modify: `frontend/src/api/users.ts` (tipos `reprint_pin?`, `has_reprint_pin`), `frontend/src/pages/core/Users.tsx` (campo + indicador + borrar), `frontend/src/hooks/useFieldValidation.ts` si ahí viven las reglas de campo (mira cómo lo hizo Rmazh en su `Users.tsx:71-99,258`).
- Test: `tests/test_reprint_pin_usuario.py` (nuevo).

**Interfaces:**
- Consumes: `get_password_hash`, `verify_pin` de `app.core.security`; fixtures de `tests/conftest.py` (`client`, `db`, `org`, `branch_a`, `auth_admin`, `auth_cajero_a`, `gerente_a`; lee `tests/test_reprint_pin.py` para ver cómo se crea una venta y se pide la reimpresión).
- Produces: `POST/PUT /api/users` con `reprint_pin`; `GET /api/users` con `has_reprint_pin`.

- [ ] **Step 1: Tests (fallan primero)** en `tests/test_reprint_pin_usuario.py`, misma mecánica que `tests/test_reprint_pin.py`:
  1. El admin se pone PIN `1234` por `PUT /api/users/{id}` → la respuesta trae `has_reprint_pin: true` y NO trae `reprint_pin_hash`; `GET /api/users` idem.
  2. El cajero reimprime una venta ajena con PIN `1234` → 200.
  3. Con `9999` → rechazado (mismo código que hoy para PIN incorrecto).
  4. La contraseña del gerente sigue funcionando después de configurar PIN.
  5. `PUT` con `reprint_pin: ""` borra el PIN → `has_reprint_pin: false` y `1234` deja de servir.
  6. `PUT` con `reprint_pin: "12"` o `"abcd"` → 422.
  7. Un cajero con PIN configurado (si el endpoint lo permite) NO autoriza: el PIN solo cuenta para roles gerenciales. Si `UserUpdate` debe rechazar el PIN para roles no gerenciales, hazlo con 422 y ajusta este test.
- [ ] **Step 2: Modelo, migración, schemas, router, servicio.** En `verificar_pin_supervisor`: para cada lista (sucursal, resto) probar primero `reprint_pin_hash` de quien lo tenga y luego `password_hash`; conserva el corte en el primer match y los comentarios existentes.
- [ ] **Step 3: Frontend.** En el formulario de usuario, cuando el rol sea ADMINISTRADOR/DUEÑO/GERENTE: campo "PIN de reimpresión (4–8 dígitos)" tipo password con `inputMode="numeric"`, texto "PIN configurado" / "Sin PIN" al editar, y casilla "Quitar PIN" que manda `""`. El PIN se manda solo si se escribió algo o se marcó quitar. Vocabulario en español.
- [ ] **Step 4: Verificar y commit.** Suite completa verde; `tsc` y `build`; commit `feat(usuarios): PIN de reimpresion por usuario, separado de la contrasena`.
