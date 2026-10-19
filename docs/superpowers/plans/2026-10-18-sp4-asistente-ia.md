# SP4 · Asistente IA: altas y consultas por chat — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un chat en `/ai` (y como panel en Productos) que consulta el catálogo, propone fichas completas de producto (nombre, SKU, departamento, marca, ficha boutique, precio, costo, matriz color × talla con existencias) como **propuestas pendientes** que solo se guardan al **Confirmar**, mediante el servicio de altas de SP1 y con rastro en `PlatformAuditLog`; además responde existencias y ventas en solo lectura.

**Architecture:** Módulo `app/modules/ai/` con un cliente LLM propio sobre `httpx` (API compatible con OpenAI, por defecto Gemini Flash), un bucle síncrono de *tool calling* (≤ 8 herramientas, 60 s) en `services.responder`, herramientas de solo lectura acotadas a la organización (y a la sucursal para quien no es admin/dueño), una única herramienta que escribe —`proponer_cambio`— y que solo crea una fila `ai_propuestas` en estado `pendiente` tras validar en seco con los helpers de SP1, y `ejecutores.aplicar`, que es lo único que llama a `crear_producto` / `crear_variantes` / `fijar_existencia`, invocado solo desde `POST …/confirmar`. El frontend agrega `src/api/ai.ts`, `ChatAsistente`, `TarjetaPropuesta`, la función pura `propuestaAFormulario`, la página `/ai` (chunk propio) y tres integraciones: botón en Productos, `FormularioProducto` con `inicial`, textarea en Empresa.

**Tech Stack:** FastAPI 0.141 + SQLAlchemy 2.0.52 + Pydantic 2.13 + httpx 0.28 (ya en `requirements.txt`); pytest sobre SQLite (`python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py`; no hay `.venv/` en este worktree). React 18 + TS + Tailwind; vitest 2 con `// @vitest-environment jsdom` + `@testing-library/react`.

**Spec:** `docs/superpowers/specs/2026-10-18-sp4-asistente-ia-design.md` (manda). Contexto: `docs/superpowers/specs/2026-10-14-mega-plan-altas-docs-responsivo-agente-design.md` §4 SP4 y `docs/ai/convenciones-altas.md` (su Parte 1 se copia tal cual a `app/modules/ai/prompts/boutique.md`).

**Rama / worktree:** `feat/sp4-asistente-ia` en `.worktrees/sp4-asistente-ia` (ya existe, limpia, sobre `16700d2`). Commits locales; **push y merge solo con permiso explícito del usuario**.

## Decisiones que el spec dejó abiertas (resueltas aquí)

1. **El aviso "Propuesta aplicada" no puede ser un mensaje `tool`.** En el formato OpenAI un `tool` sin el `assistant` que lo pidió hace que el proveedor rechace la petición. Se guarda con `rol="evento"` y al armar el historial se manda como `{"role": "user", "content": "[Aviso del sistema] …"}`; la pantalla lo pinta como nota gris.
2. **`ai_propuestas.avisos` (JSON)** guarda los avisos que la tarjeta muestra (costo $0, sin marca…); el spec los devuelve al modelo pero no decía dónde vivían.
3. **`ai_messages.orden` (Integer)** da un orden determinista dentro de la conversación (varias filas del mismo turno pueden compartir `created_at`).
4. **Recorte del historial:** los últimos 30 mensajes, quitando los `tool` huérfanos del principio (`recortar_historial`).
5. **Alcance por sucursal:** `reports.HQ_ROLES` incluye GERENTE, pero el spec dice "cajero/gerente solo su sucursal". El asistente usa su propio `ambito_sucursal`: solo ADMINISTRADOR/DUEÑO ven la organización entera.
6. **Quién puede confirmar:** roles `PRODUCT_ADVANCED_ROLES` de SP1 (ADMINISTRADOR, GERENTE, DUEÑO, CAJERO). GERENTE/CAJERO necesitan el módulo `catalog` encendido para altas y variantes (igual que `POST /api/products/`) y solo tocan su sucursal.
7. **Fallo al confirmar:** la ejecución corre en un SAVEPOINT; si SP1 responde 4xx (p. ej. SKU tomado entre la propuesta y el clic), la propuesta queda `error` con `resultado.detail` y la respuesta HTTP conserva el código y el texto. Desde `error` se puede **Ajustar en formulario** o **Descartar**, no volver a confirmar.
8. **Sucursal de la existencia:** `proponer_cambio` normaliza `crear_producto`: sin `branch_id`, toma la del usuario (no admin) o la única que vende; con `branch_id` y sin `target_branch_ids`, fija `target_branch_ids=[branch_id]`. Sin esto, un admin asignado a la matriz (que no vende) dejaría la existencia en la matriz por la regla de `sucursal_de_existencia_inicial`.
9. **`inicial` de `FormularioProducto`** lleva además `colores` y `tallas` (texto): `ProductVariantsSection` regenera la matriz desde esos campos al montar y sin ellos borraría las filas prellenadas. La matriz es rectangular: combinaciones que no venían en la propuesta nacen sin existencia y la conversión lo avisa.
10. **Prompts `.md` dentro de la imagen:** `.dockerignore` tiene `*.md` (en Docker solo aplica a la raíz), se agrega `!app/modules/ai/prompts/*.md` para dejarlo explícito.
11. **Borrado forzado de organización** (`DELETE /api/platform/organizations/{id}?force=true`): las cuatro tablas nuevas tienen FK a `organization`/`users`; se agrega `borrar_datos_ai_de_org` a la cascada.
12. **Reintentos del proveedor:** a lo más uno, solo ante 5xx o timeout/red; un 429 no se reintenta.
13. **Privacidad en `buscar_ventas`:** filtra por `customer_name` pero nunca lo devuelve.
14. **Navegación:** `/ai` sigue visible solo para ADMINISTRADOR y DUEÑO (`navConfig.ts`, sin cambios) y el botón de Productos vive en la vista HQ. El backend ya acepta GERENTE/CAJERO con sus límites; abrirles la pantalla es una decisión de producto aparte.

## Global Constraints

- **Nunca se llama al LLM real en las pruebas.** Toda prueba usa `ClienteFalso` o `httpx.MockTransport`; la dependencia `obtener_cliente_llm` se sustituye con `app.dependency_overrides`.
- **FKs a UUID = `String(36)`** (regla de oro #4): `ai_messages.conversation_id`, `ai_propuestas.conversation_id`.
- **Toda consulta filtra `organization_id`**; el `org_id` sale del contexto (`get_current_active_organization`), **nunca** de los argumentos del modelo. `product_id`, `variant_id`, `sucursal_id` que no sean de la organización → la herramienta responde "… no existe".
- **Gate estricto del módulo `ai` sin bypass por rol:** `exigir_modulo_ai` exige `organization_modules.ai` encendido también para ADMINISTRADOR/DUEÑO (no usar `require_module`, que los exime). 403 con `detail` = `"El asistente IA no está incluido en tu plan (mínimo SCALE). La plataforma puede activarlo."` (plan desde `plan_minimo_para("ai")`).
- **Ninguna escritura fuera de `confirmar`** (y de `descartar` / `aplicada-manual`, que solo cambian el estado de la propuesta): las herramientas leen o crean `ai_propuestas` pendientes; ningún endpoint de chat crea productos, variantes ni existencias.
- **Precio y costo nunca se inventan:** `proponer_cambio` rechaza `crear_producto` sin `price` o sin `cost` con `"Falta precio: pregunta al usuario; nunca lo inventes."` (o costo / "precio y costo"); `cost = 0` se acepta con aviso.
- **Textos de pantalla en español**, cortos; comentarios en español; `from __future__ import annotations`; type hints en firmas nuevas; sin `print()`.
- **Responsivo desde el día uno:** kit `components/ui/` (`CabeceraPagina`, `Modal`, `DaxCard`), `useEsTelefono()`, ninguna `grid-cols-N` (N ≥ 3) sin prefijo, **ningún `fixed inset-0` nuevo** (lo congela `src/__tests__/overlaysFueraDelKit.test.ts`); botones ≥ 44 px bajo `sm`.
- **`/ai` en su propio chunk perezoso** (`lazy(() => import('./pages/ai/Asistente'))`); Productos carga `ChatAsistente` también con `lazy`. El presupuesto de la ruta crítica (`frontend/presupuesto_bundle.json`, `tope_bytes` 452500) **no se toca**.
- **Esquema:** columna nueva `organization.ai_instrucciones TEXT` vía `scripts/railway_init.py::COLUMN_MIGRATIONS`; las cuatro tablas nuevas las crea `create_all` al registrarlas en `app/models/__init__.py`. Nada de Alembic.
- **Variables nuevas:** `LLM_BASE_URL` (default `https://generativelanguage.googleapis.com/v1beta/openai/`), `LLM_MODEL` (default `gemini-3.8-flash`), `LLM_API_KEY` (sin default; sin ella → 503 `"Asistente no configurado: falta LLM_API_KEY en el servidor."`), `AI_TOKENS_DIA_ORG` (default `200000`).
- **Topes:** 8 herramientas por turno, 60 s por turno, 45 s por llamada al proveedor, 30 mensajes de historial, 4000 caracteres por mensaje de usuario, 20 conversaciones en el listado.
- **Pruebas:** backend `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py`; frontend `cd frontend && npx vitest run` y `npm run build`. **Una sola suite por worktree a la vez** (la "DB en memoria" de `conftest.py` es un archivo real).
- **Commits** con scope `feat(ai):` / `test(ai):` / `docs(ai):` y terminan con:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
  ```

## Review Focus

1. **El modelo inventa un `department_id` (o uno de otra organización):** `proponer_cambio` responde al modelo `"Departamento no encontrado en tu organización."` y **no** crea propuesta. → Tarea 5, `test_departamento_de_otra_org_no_crea_propuesta`.
2. **Argumentos de `tool_call` con JSON mal formado:** el cliente no revienta (marca `error_json`), la herramienta no se ejecuta, el modelo recibe un `tool` con el error y el turno termina con la siguiente respuesta. → Tarea 2, `test_argumentos_mal_formados_no_revientan`; Tarea 7, `test_json_mal_formado_vuelve_al_modelo_y_el_turno_termina`.
3. **Doble clic en Confirmar sobre la misma propuesta:** el segundo `POST …/confirmar` responde 409 `"La propuesta ya fue confirmada."` y existe un solo producto con ese SKU (en Postgres el `with_for_update` serializa; en SQLite basta la verificación de estado). → Tarea 7, `test_confirmar_dos_veces_da_409_y_no_duplica`.
4. **Cajero confirma una propuesta que toca otra sucursal:** 403 `"Solo puedes aplicar cambios en tu sucursal."` y la existencia de la otra sucursal intacta. → Tarea 6, `test_cajero_no_aplica_ajuste_en_otra_sucursal`.
5. **El LLM responde sin texto y sin herramientas:** el usuario ve `"No obtuve respuesta del asistente. Intenta de nuevo con otras palabras."`, nunca un globo vacío ni un 500. → Tarea 7, `test_respuesta_vacia_da_mensaje_legible`.

---

## Estructura de archivos

**Crear (backend)**
- `app/modules/ai/models.py` — `AiConversation`, `AiMessage`, `AiPropuesta`, `AiUsoDiario`.
- `app/modules/ai/schemas.py` — requests/responses del router y datos de `agregar_variantes` / `ajustar_existencias`.
- `app/modules/ai/historial.py` — `guardar_mensaje`, `mensajes_de`, `recortar_historial`, `a_formato_llm`, `historial_para_llm`.
- `app/modules/ai/limpieza.py` — `borrar_datos_ai_de_org` (cascada de plataforma).
- `app/modules/ai/cliente_llm.py` — `LlamadaHerramienta`, `RespuestaLLM`, `ClienteLLM`, `ClienteOpenAICompatible`, `ClienteFalso`, `ProveedorNoDisponible`, `configuracion`, `cliente_por_defecto`, `limite_tokens_dia`.
- `app/modules/ai/prompts/base.md`, `app/modules/ai/prompts/boutique.md`.
- `app/modules/ai/prompt.py` — `prompt_del_sistema`, `armar_prompt`.
- `app/modules/ai/contexto.py` — `Contexto`, `Herramienta`, `ErrorHerramienta`, `texto_de_validacion`, `ambito_sucursal`, `sucursal_de_la_org`.
- `app/modules/ai/herramientas_catalogo.py`, `herramientas_propuestas.py`, `herramientas_ventas.py` — implementaciones.
- `app/modules/ai/herramientas.py` — `REGISTRO`, `definiciones`, `ejecutar`.
- `app/modules/ai/gating.py` — `modulo_encendido`, `mensaje_sin_modulo`, `exigir_modulo_ai`.
- `app/modules/ai/ejecutores.py` — `aplicar`.
- `app/modules/ai/services.py` — `Turno`, `verificar_cuota`, `registrar_uso`, `responder`.
- Pruebas: `tests/test_ai_modelos.py`, `tests/test_ai_cliente_llm.py`, `tests/test_ai_prompt.py`, `tests/test_ai_herramientas_catalogo.py`, `tests/test_ai_propuestas.py`, `tests/test_ai_ejecutores.py`, `tests/test_ai_servicio.py`, `tests/test_ai_api.py`, `tests/test_ai_herramientas_ventas.py`.

**Modificar (backend)**
- `app/modules/ai/router.py` — reemplaza el stub.
- `app/models/__init__.py` — registra `app.modules.ai.models`.
- `app/modules/tenants/models.py` — `Organization.ai_instrucciones`.
- `app/modules/tenants/schemas.py` — `AI_INSTRUCCIONES_MAX`, campo en `OrganizationUpdate` y `OrganizationRead`.
- `scripts/railway_init.py` — tupla `("organization", "ai_instrucciones", …)`.
- `app/routers/platform/organizations.py` — llama a `borrar_datos_ai_de_org` en el borrado forzado.
- `.dockerignore` — `!app/modules/ai/prompts/*.md`.

**Crear (frontend)**
- `frontend/src/api/ai.ts`
- `frontend/src/components/ai/propuestaAFormulario.ts`, `TarjetaPropuesta.tsx`, `ChatAsistente.tsx`
- `frontend/src/pages/ai/Asistente.tsx`
- Pruebas: `frontend/src/components/ai/__tests__/propuestaAFormulario.test.ts`, `TarjetaPropuesta.test.tsx`, `ChatAsistente.test.tsx`; `frontend/src/pages/ai/__tests__/Asistente.test.tsx`; `frontend/src/__tests__/rutaAsistente.test.ts`; `frontend/src/__tests__/integracionAsistente.test.ts`; `frontend/src/pages/core/__tests__/OrganizationAsistente.test.tsx`.

**Modificar (frontend)**
- `frontend/src/App.tsx` (ruta `ai`), `frontend/src/pages/__tests__/responsivoOla2.test.ts` (`PAGINAS`, `SIN_TARJETA_FILA`)
- `frontend/src/components/products/types.ts` (`InicialFormulario`), `FormularioProducto.tsx` (prop `inicial`), `__tests__/FormularioProducto.test.tsx`
- `frontend/src/pages/inventory/Products.tsx` (botón + drawer), `frontend/src/pages/core/Organization.tsx` (textarea), `frontend/src/api/organization.ts` (tipo), `frontend/src/pages/home/PresetHome.tsx` (texto del widget)

**Docs:** `docs/ai/README.md` (nuevo), `.env.example` (nuevo), `docs/API_REFERENCE.md`, `docs/FRONTEND_VIEWS.md`, `docs/DEPLOY.md`.

---

## Antes de empezar

- [ ] Confirmar la rama y que el árbol está limpio:

```bash
git status --short --branch
```

Expected: `## feat/sp4-asistente-ia` sin cambios pendientes.

- [ ] Anotar la línea base de la suite (la comparación final de la Tarea 12 es contra este número):

```bash
python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py 2>&1 | tail -3
cd frontend && npx vitest run 2>&1 | tail -4 && npm run build >/dev/null && cd .. && \
  python3 scripts/presupuesto_bundle.py --dist frontend/dist --presupuesto frontend/presupuesto_bundle.json
```

Expected: anota `N passed, M failed` de pytest, el total de vitest y los bytes medidos del presupuesto (guárdalos en el scratchpad de la sesión, no en el repo).

---

### Task 1: Modelos, schemas, historial y `organization.ai_instrucciones`

**Files:**
- Create: `app/modules/ai/models.py`, `app/modules/ai/schemas.py`, `app/modules/ai/historial.py`, `app/modules/ai/limpieza.py`
- Modify: `app/models/__init__.py` (al final, tras `ExchangeRate`)
- Modify: `app/modules/tenants/models.py` (tras `card_surcharge_pct`, ~línea 241)
- Modify: `app/modules/tenants/schemas.py` (constante tras `TERMS_MAX_LEN`; campo en `OrganizationUpdate` y `OrganizationRead`)
- Modify: `scripts/railway_init.py` (tras la tupla `ticket_line_style`, ~línea 163)
- Modify: `app/routers/platform/organizations.py` (imports del borrado forzado ~línea 158; antes de `deleted["print_jobs"]`, ~línea 312)
- Test: `tests/test_ai_modelos.py`

**Interfaces:**
- Consumes: `UUIDMixin`, `AuditMixin`, `TenantMixin` (`app/models/mixins.py`); `Base` (`app.core.database`).
- Produces (las usan las tareas 2–10):
  - Modelos `AiConversation(id, organization_id, user_id, titulo, created_at, updated_at, deleted_at)`, `AiMessage(id, organization_id, conversation_id: String(36), orden: int, rol: str, contenido: str|None, tool_calls: list|None, tool_call_id: str|None, tokens_entrada: int, tokens_salida: int, created_at)`, `AiPropuesta(id, organization_id, conversation_id: String(36), tipo, datos: dict, avisos: list, estado, resultado: dict|None, resumen, confirmada_por, confirmada_at, created_at)`, `AiUsoDiario(id, organization_id, fecha: date, tokens_entrada, tokens_salida, llamadas)`.
  - Constantes `ROLES_MENSAJE = ("user", "assistant", "tool", "evento")`, `TIPOS_PROPUESTA = ("crear_producto", "agregar_variantes", "ajustar_existencias")`, `ESTADOS_PROPUESTA = ("pendiente", "confirmada", "descartada", "aplicada_manual", "error")`.
  - Schemas `ConversacionCrear{titulo?}`, `MensajeCrear{texto: 1..4000}`, `AplicadaManual{producto_id?}`, `MensajeRead{id, rol, contenido: str|None, created_at}`, `PropuestaRead{id, tipo, datos, estado, resumen, avisos: list[str], resultado: dict|None, created_at}`, `ConversacionResumen{id, titulo, created_at, updated_at}`, `ConversacionDetalle(ConversacionResumen){mensajes, propuestas}`, `RespuestaTurno{mensaje: MensajeRead, propuestas_pendientes: list[PropuestaRead]}`, `VarianteNueva{color?, size? (alias "talla"), sku?, precio?, existencia≥0}`, `DatosAgregarVariantes{product_id, sucursal_id?, variantes[1..60]}`, `AjusteExistencia{variant_id, sucursal_id, existencia_nueva≥0}`, `DatosAjustarExistencias{ajustes[1..50]}`, `TOPE_TEXTO = 4000`.
  - `guardar_mensaje(db, conv: AiConversation, rol: str, contenido: str|None, *, tool_calls=None, tool_call_id=None, tokens_entrada=0, tokens_salida=0) -> AiMessage` (hace `flush`).
  - `mensajes_de(db, conv) -> list[AiMessage]` (por `orden`).
  - `recortar_historial(mensajes: list[AiMessage], tope: int = 30) -> list[AiMessage]`.
  - `a_formato_llm(m: AiMessage) -> dict`, `historial_para_llm(db, conv, tope: int = 30) -> list[dict]`.
  - `borrar_datos_ai_de_org(db, org_id: int) -> dict[str, int]` con claves `ai_propuestas`, `ai_messages`, `ai_conversations`, `ai_uso_diario`.
  - `Organization.ai_instrucciones: Text|None`; `AI_INSTRUCCIONES_MAX = 4000` en `app/modules/tenants/schemas.py`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_ai_modelos.py`:

```python
"""Tablas del asistente IA, `organization.ai_instrucciones` y el historial que
se le manda al modelo (SP4, 2026-10)."""
import pytest
from sqlalchemy.exc import IntegrityError

from conftest import _make_user
from app.core.fechas import hoy_negocio
from app.models.organization import Organization
from app.models.users import Role
from app.modules.ai.historial import guardar_mensaje, historial_para_llm, recortar_historial
from app.modules.ai.limpieza import borrar_datos_ai_de_org
from app.modules.ai.models import AiConversation, AiMessage, AiPropuesta, AiUsoDiario
from scripts import railway_init

LLAMADA = {"id": "c1", "type": "function", "function": {"name": "listar_marcas", "arguments": "{}"}}


def _conv(db, org, user):
    c = AiConversation(organization_id=org.id, user_id=user.id, titulo="Prueba")
    db.add(c)
    db.flush()
    return c


class TestEsquema:
    def test_fks_a_uuid_son_string_36(self):
        assert AiConversation.__table__.c.id.type.length == 36
        assert AiMessage.__table__.c.conversation_id.type.length == 36
        assert AiPropuesta.__table__.c.conversation_id.type.length == 36

    def test_uso_diario_unico_por_org_y_fecha(self, db, org):
        db.add(AiUsoDiario(organization_id=org.id, fecha=hoy_negocio()))
        db.flush()
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.add(AiUsoDiario(organization_id=org.id, fecha=hoy_negocio()))
                db.flush()

    def test_el_arranque_migra_ai_instrucciones(self):
        declaradas = {(t, c) for t, c, _ in railway_init.COLUMN_MIGRATIONS}
        assert ("organization", "ai_instrucciones") in declaradas


class TestInstruccionesDeLaOrg:
    def test_admin_las_guarda_y_las_lee(self, client, db, org, auth_admin):
        texto = "Tallas Ch, M, G, XL. MAM = Maison Margiela."
        r = client.put("/api/organization/", json={"ai_instrucciones": texto}, headers=auth_admin)
        assert r.status_code == 200, r.text
        assert r.json()["ai_instrucciones"] == texto
        db.refresh(org)
        assert org.ai_instrucciones == texto
        assert client.get("/api/organization/", headers=auth_admin).json()["ai_instrucciones"] == texto

    def test_cajero_no_las_cambia(self, client, auth_cajero_a):
        r = client.put("/api/organization/", json={"ai_instrucciones": "x"}, headers=auth_cajero_a)
        assert r.status_code == 403

    def test_tope_de_4000_caracteres(self, client, auth_admin):
        r = client.put("/api/organization/", json={"ai_instrucciones": "x" * 4001}, headers=auth_admin)
        assert r.status_code == 422


class TestHistorial:
    def test_orden_crece_por_conversacion(self, db, org, admin_user):
        c = _conv(db, org, admin_user)
        a = guardar_mensaje(db, c, "user", "hola")
        b = guardar_mensaje(db, c, "assistant", "qué tal")
        assert (a.orden, b.orden) == (1, 2)
        assert a.organization_id == org.id

    def test_recorte_no_empieza_en_tool_huerfano(self, db, org, admin_user):
        c = _conv(db, org, admin_user)
        guardar_mensaje(db, c, "user", "busca marcas")
        guardar_mensaje(db, c, "assistant", "", tool_calls=[LLAMADA])
        guardar_mensaje(db, c, "tool", '{"marcas": []}', tool_call_id="c1")
        guardar_mensaje(db, c, "assistant", "No hay marcas.")
        todos = db.query(AiMessage).filter(AiMessage.conversation_id == c.id).order_by(AiMessage.orden).all()
        # Los dos últimos son tool + assistant: el tool quedaría huérfano.
        assert [m.rol for m in recortar_historial(todos, tope=2)] == ["assistant"]
        assert [m.rol for m in recortar_historial(todos, tope=30)] == ["user", "assistant", "tool", "assistant"]

    def test_formato_llm(self, db, org, admin_user):
        c = _conv(db, org, admin_user)
        guardar_mensaje(db, c, "user", "hola")
        guardar_mensaje(db, c, "assistant", "", tool_calls=[LLAMADA])
        guardar_mensaje(db, c, "tool", "{}", tool_call_id="c1")
        guardar_mensaje(db, c, "evento", "Propuesta aplicada: Alta VER-1")
        h = historial_para_llm(db, c)
        assert h[0] == {"role": "user", "content": "hola"}
        assert h[1]["role"] == "assistant" and h[1]["tool_calls"] == [LLAMADA]
        assert h[2] == {"role": "tool", "tool_call_id": "c1", "content": "{}"}
        assert h[3] == {"role": "user", "content": "[Aviso del sistema] Propuesta aplicada: Alta VER-1"}


class TestLimpieza:
    def test_borra_solo_la_org_indicada(self, db, org, admin_user):
        otra = Organization(name="Otra", status="ACTIVE")
        db.add(otra)
        db.flush()
        dueno = _make_user(db, otra, None, "dueno_otra", Role.DUEÑO)
        mia, ajena = _conv(db, org, admin_user), _conv(db, otra, dueno)
        for c in (mia, ajena):
            guardar_mensaje(db, c, "user", "hola")
            db.add(AiPropuesta(
                organization_id=c.organization_id, conversation_id=c.id, tipo="ajustar_existencias",
                datos={}, avisos=[], resumen="r", confirmada_por=c.user_id,
            ))
        db.add(AiUsoDiario(organization_id=otra.id, fecha=hoy_negocio(), tokens_entrada=5))
        db.flush()

        borrados = borrar_datos_ai_de_org(db, otra.id)

        assert borrados == {"ai_propuestas": 1, "ai_messages": 1, "ai_conversations": 1, "ai_uso_diario": 1}
        assert db.query(AiConversation).filter(AiConversation.organization_id == otra.id).count() == 0
        assert db.query(AiConversation).filter(AiConversation.organization_id == org.id).count() == 1
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_ai_modelos.py`
Expected: FAIL en la colección con `ModuleNotFoundError: No module named 'app.modules.ai.historial'`.

- [ ] **Step 3: Crear `app/modules/ai/models.py`**

```python
"""Tablas del asistente IA (SP4, 2026-10).

Conversación → mensajes (el historial que se le manda al modelo, en `orden`) y
propuestas (lo único que el asistente puede "escribir": una ficha pendiente
que la persona confirma en pantalla). `ai_uso_diario` mide tokens por
organización y día para el tope `AI_TOKENS_DIA_ORG`.

Regla de oro #4: toda FK a una tabla con PK UUID es String(36).
Estados y roles son cadenas con constantes de Python, no enums de Postgres
(CLAUDE.md §5: un valor nuevo no debe costar un ALTER TYPE).
"""
from __future__ import annotations

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint

from app.core.database import Base
from app.models.mixins import AuditMixin, TenantMixin, UUIDMixin

# `evento` = aviso del sistema dentro de la conversación ("Propuesta aplicada…").
# Al modelo se le manda como mensaje de usuario: un `tool` sin el `assistant`
# que lo pidió hace que el proveedor rechace la petición.
ROLES_MENSAJE = ("user", "assistant", "tool", "evento")
TIPOS_PROPUESTA = ("crear_producto", "agregar_variantes", "ajustar_existencias")
ESTADOS_PROPUESTA = ("pendiente", "confirmada", "descartada", "aplicada_manual", "error")


class AiConversation(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "ai_conversations"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    titulo = Column(String(120), nullable=True)


class AiMessage(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "ai_messages"

    conversation_id = Column(String(36), ForeignKey("ai_conversations.id"), nullable=False, index=True)
    # Orden dentro de la conversación: varias filas del mismo turno pueden
    # compartir `created_at`.
    orden = Column(Integer, nullable=False)
    rol = Column(String(12), nullable=False)
    contenido = Column(Text, nullable=True)
    # Formato OpenAI: [{"id", "type": "function", "function": {"name", "arguments"}}]
    tool_calls = Column(JSON, nullable=True)
    tool_call_id = Column(String(80), nullable=True)
    tokens_entrada = Column(Integer, nullable=False, default=0)
    tokens_salida = Column(Integer, nullable=False, default=0)


class AiPropuesta(Base, UUIDMixin, AuditMixin, TenantMixin):
    __tablename__ = "ai_propuestas"

    conversation_id = Column(String(36), ForeignKey("ai_conversations.id"), nullable=False, index=True)
    tipo = Column(String(30), nullable=False)
    # Datos ya normalizados por el schema del tipo (crear_producto = ProductCreate de SP1).
    datos = Column(JSON, nullable=False)
    avisos = Column(JSON, nullable=True)
    estado = Column(String(20), nullable=False, default="pendiente", index=True)
    resultado = Column(JSON, nullable=True)
    # Resumen humano: lo arma el servidor, nunca el modelo.
    resumen = Column(String(300), nullable=False)
    confirmada_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmada_at = Column(DateTime(timezone=True), nullable=True)


class AiUsoDiario(Base):
    __tablename__ = "ai_uso_diario"
    __table_args__ = (UniqueConstraint("organization_id", "fecha", name="uq_ai_uso_org_fecha"),)

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False, index=True)
    fecha = Column(Date, nullable=False)  # día del negocio (app/core/fechas.py)
    tokens_entrada = Column(Integer, nullable=False, default=0)
    tokens_salida = Column(Integer, nullable=False, default=0)
    llamadas = Column(Integer, nullable=False, default=0)
```

- [ ] **Step 4: Crear `app/modules/ai/schemas.py`**

```python
"""Schemas del asistente IA: lo que entra y sale del router y los datos de
las propuestas `agregar_variantes` / `ajustar_existencias`.

`crear_producto` no tiene schema propio: sus datos son exactamente
`ProductCreate` de SP1 (`app/modules/products/schemas.py`).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

TOPE_TEXTO = 4000


class ConversacionCrear(BaseModel):
    titulo: Optional[str] = Field(default=None, max_length=120)


class MensajeCrear(BaseModel):
    texto: str = Field(min_length=1, max_length=TOPE_TEXTO)


class AplicadaManual(BaseModel):
    """La persona guardó la propuesta desde el formulario (Ajustar en formulario)."""
    producto_id: Optional[str] = Field(default=None, max_length=36)


class MensajeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rol: str
    contenido: Optional[str] = None
    created_at: datetime


class PropuestaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tipo: str
    datos: dict[str, Any]
    estado: str
    resumen: str
    avisos: List[str] = Field(default_factory=list)
    resultado: Optional[dict[str, Any]] = None
    created_at: datetime

    @field_validator("avisos", mode="before")
    @classmethod
    def _sin_avisos_es_lista(cls, v):
        return v or []


class ConversacionResumen(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    titulo: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ConversacionDetalle(ConversacionResumen):
    mensajes: List[MensajeRead] = Field(default_factory=list)
    propuestas: List[PropuestaRead] = Field(default_factory=list)


class RespuestaTurno(BaseModel):
    mensaje: MensajeRead
    propuestas_pendientes: List[PropuestaRead] = Field(default_factory=list)


# ── Datos de las propuestas ──────────────────────────────────────────────────

class VarianteNueva(BaseModel):
    color: Optional[str] = None
    # El spec usa "talla" en el texto y "size" en el ejemplo: se aceptan los dos.
    size: Optional[str] = Field(default=None, validation_alias=AliasChoices("size", "talla"))
    sku: Optional[str] = None
    precio: Optional[Decimal] = None
    existencia: Decimal = Field(default=Decimal(0), ge=0)


class DatosAgregarVariantes(BaseModel):
    product_id: str
    sucursal_id: Optional[int] = None
    variantes: List[VarianteNueva] = Field(min_length=1, max_length=60)


class AjusteExistencia(BaseModel):
    variant_id: str
    sucursal_id: int
    existencia_nueva: Decimal = Field(ge=0)


class DatosAjustarExistencias(BaseModel):
    ajustes: List[AjusteExistencia] = Field(min_length=1, max_length=50)
```

- [ ] **Step 5: Crear `app/modules/ai/historial.py`**

```python
"""Historial de una conversación: guardar mensajes en orden y armar lo que se
le manda al modelo (formato OpenAI `messages`)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import AiConversation, AiMessage

TOPE_HISTORIAL = 30


def guardar_mensaje(
    db: Session, conv: AiConversation, rol: str, contenido: Optional[str], *,
    tool_calls: Optional[list] = None, tool_call_id: Optional[str] = None,
    tokens_entrada: int = 0, tokens_salida: int = 0,
) -> AiMessage:
    """Agrega un mensaje al final de la conversación. Hace `flush`."""
    ultimo = db.query(func.max(AiMessage.orden)).filter(AiMessage.conversation_id == conv.id).scalar() or 0
    mensaje = AiMessage(
        organization_id=conv.organization_id,
        conversation_id=conv.id,
        orden=ultimo + 1,
        rol=rol,
        contenido=contenido,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        tokens_entrada=tokens_entrada,
        tokens_salida=tokens_salida,
    )
    db.add(mensaje)
    db.flush()
    return mensaje


def mensajes_de(db: Session, conv: AiConversation) -> list[AiMessage]:
    return (
        db.query(AiMessage)
        .filter(AiMessage.conversation_id == conv.id, AiMessage.organization_id == conv.organization_id)
        .order_by(AiMessage.orden)
        .all()
    )


def recortar_historial(mensajes: list[AiMessage], tope: int = TOPE_HISTORIAL) -> list[AiMessage]:
    """Los últimos `tope`, sin empezar en un `tool` huérfano (sin el
    `assistant` que lo pidió el proveedor rechaza la petición)."""
    recorte = list(mensajes[-tope:]) if tope > 0 else []
    while recorte and recorte[0].rol == "tool":
        recorte.pop(0)
    return recorte


def a_formato_llm(m: AiMessage) -> dict:
    if m.rol == "tool":
        return {"role": "tool", "tool_call_id": m.tool_call_id or "", "content": m.contenido or ""}
    if m.rol == "assistant":
        salida = {"role": "assistant", "content": m.contenido or ""}
        if m.tool_calls:
            salida["tool_calls"] = m.tool_calls
        return salida
    if m.rol == "evento":
        return {"role": "user", "content": f"[Aviso del sistema] {m.contenido or ''}"}
    return {"role": "user", "content": m.contenido or ""}


def historial_para_llm(db: Session, conv: AiConversation, tope: int = TOPE_HISTORIAL) -> list[dict]:
    return [a_formato_llm(m) for m in recortar_historial(mensajes_de(db, conv), tope)]
```

- [ ] **Step 6: Crear `app/modules/ai/limpieza.py`**

```python
"""Borrado de los datos del asistente de una organización.

Lo llama la cascada manual de `DELETE /api/platform/organizations/{id}?force=true`
(app/routers/platform/organizations.py): las cuatro tablas tienen FK a
`organization` o `users` y sin esto el borrado forzado truena.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AiConversation, AiMessage, AiPropuesta, AiUsoDiario


def borrar_datos_ai_de_org(db: Session, org_id: int) -> dict[str, int]:
    conversaciones = select(AiConversation.id).where(AiConversation.organization_id == org_id)
    borrados = {
        "ai_propuestas": db.query(AiPropuesta).filter(
            AiPropuesta.conversation_id.in_(conversaciones)
        ).delete(synchronize_session=False),
        "ai_messages": db.query(AiMessage).filter(
            AiMessage.conversation_id.in_(conversaciones)
        ).delete(synchronize_session=False),
    }
    borrados["ai_conversations"] = db.query(AiConversation).filter(
        AiConversation.organization_id == org_id
    ).delete(synchronize_session=False)
    borrados["ai_uso_diario"] = db.query(AiUsoDiario).filter(
        AiUsoDiario.organization_id == org_id
    ).delete(synchronize_session=False)
    db.flush()
    return borrados
```

- [ ] **Step 7: Registrar los modelos y la columna**

En `app/models/__init__.py`, al final del archivo:

```python

# 16. Asistente IA (SP4): conversaciones, mensajes, propuestas y uso diario.
#     Registradas aqui para `create_all`.
from app.modules.ai import models as _ai_models  # noqa: F401
```

En `app/modules/tenants/models.py`, justo después de la línea `card_surcharge_pct = Column(Numeric(5, 2), default=0, server_default="0", nullable=False)`:

```python

    # Instrucciones del dueño para el asistente IA (SP4, 2026-10): escala de
    # tallas, abreviaturas de marca en el SKU, departamentos. NULL = solo las
    # convenciones del preset (app/modules/ai/prompts/).
    ai_instrucciones = Column(Text, nullable=True)
```

En `scripts/railway_init.py`, justo después de la tupla `("organization", "ticket_line_style", …)`:

```python
    # Asistente IA (SP4, 2026-10): instrucciones del dueño. NULL para todas
    # las organizaciones vivas; las tablas ai_* las crea `create_all`.
    ("organization", "ai_instrucciones", "ALTER TABLE organization ADD COLUMN ai_instrucciones TEXT;"),
```

- [ ] **Step 8: Exponer el campo en Empresa (`app/modules/tenants/schemas.py`)**

Tras `TERMS_MAX_LEN = 2000`:

```python

# Tope de las instrucciones del asistente IA. El textarea de Empresa usa el
# mismo `maxLength`.
AI_INSTRUCCIONES_MAX = 4000
```

En `OrganizationUpdate`, reemplazar la línea `    card_surcharge_pct: Optional[Decimal] = None` por:

```python
    card_surcharge_pct: Optional[Decimal] = None

    # Instrucciones para el asistente IA (SP4). Caen FUERA de la whitelist de
    # no-admins del router: solo ADMINISTRADOR/DUEÑO las cambia.
    ai_instrucciones: Optional[str] = Field(default=None, max_length=AI_INSTRUCCIONES_MAX)
```

En `OrganizationRead`, reemplazar `    card_surcharge_pct: Decimal = Decimal("0")` por:

```python
    card_surcharge_pct: Decimal = Decimal("0")

    # Instrucciones para el asistente IA; el panel de Empresa las edita.
    ai_instrucciones: Optional[str] = None
```

- [ ] **Step 9: Enganchar la limpieza al borrado forzado**

En `app/routers/platform/organizations.py`, dentro de `delete_organization`, junto a los demás imports locales (después de `from app.models.print_job import PrintJob`):

```python
    from app.modules.ai.limpieza import borrar_datos_ai_de_org
```

Y justo antes de `        deleted["print_jobs"] = db.query(PrintJob).filter(`:

```python
        # Asistente IA (SP4): conversaciones/mensajes/propuestas apuntan a
        # users y organization; van antes de borrar usuarios y la org.
        deleted.update(borrar_datos_ai_de_org(db, org_id))
```

- [ ] **Step 10: Correr las pruebas**

Run: `python3 -m pytest -q -p no:warnings tests/test_ai_modelos.py tests/test_migraciones_de_despliegue.py tests/test_card_surcharge_config.py`
Expected: PASS (todas).

- [ ] **Step 11: Commit**

```bash
git add app/modules/ai/models.py app/modules/ai/schemas.py app/modules/ai/historial.py app/modules/ai/limpieza.py \
  app/models/__init__.py app/modules/tenants/models.py app/modules/tenants/schemas.py scripts/railway_init.py \
  app/routers/platform/organizations.py tests/test_ai_modelos.py
git commit -m "$(cat <<'EOF'
feat(ai): tablas del asistente, historial y organization.ai_instrucciones

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 2: `cliente_llm.py` — proveedor compatible con OpenAI sobre httpx

**Files:**
- Create: `app/modules/ai/cliente_llm.py`
- Test: `tests/test_ai_cliente_llm.py`

**Interfaces:**
- Consumes: nada de tareas anteriores (`httpx`, `fastapi.HTTPException`).
- Produces (tareas 7 y 8 los usan):
  - `class ProveedorNoDisponible(RuntimeError)` — `str(e)` es el `detail` del 503.
  - `@dataclass LlamadaHerramienta(id: str, nombre: str, argumentos: dict, argumentos_crudos: str = "{}", error_json: str | None = None)`; `LlamadaHerramienta.desde_crudo(id, nombre, crudo) -> LlamadaHerramienta`; `.como_tool_call() -> dict` (formato OpenAI).
  - `@dataclass RespuestaLLM(texto: str | None = None, tool_calls: list[LlamadaHerramienta] = [], tokens_entrada: int = 0, tokens_salida: int = 0)`.
  - `class ClienteLLM(Protocol): def completar(self, mensajes: list[dict], herramientas: list[dict]) -> RespuestaLLM`.
  - `ClienteOpenAICompatible(base_url: str, api_key: str, modelo: str, timeout: float = 45.0, transport: httpx.BaseTransport | None = None)` con atributos `url`, `modelo`.
  - `ClienteFalso(guion: list[RespuestaLLM])` con `.llamadas: list[dict]` (`{"mensajes", "herramientas"}`); sin guion → `AssertionError`.
  - `configuracion() -> ConfiguracionLLM(base_url, modelo, api_key)`; `cliente_por_defecto() -> ClienteOpenAICompatible` (503 `NO_CONFIGURADO` sin clave); `limite_tokens_dia() -> int`.
  - Constantes `BASE_URL_POR_DEFECTO`, `MODELO_POR_DEFECTO`, `NO_CONFIGURADO`, `TIMEOUT_SEGUNDOS = 45.0`, `TOKENS_DIA_POR_DEFECTO = 200000`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_ai_cliente_llm.py`:

```python
"""Cliente del proveedor LLM (API compatible con OpenAI). La suite nunca sale
a la red: `httpx.MockTransport` hace de proveedor."""
import json

import httpx
import pytest
from fastapi import HTTPException

from app.modules.ai.cliente_llm import (
    BASE_URL_POR_DEFECTO, MODELO_POR_DEFECTO, NO_CONFIGURADO, ClienteFalso, ClienteOpenAICompatible,
    LlamadaHerramienta, ProveedorNoDisponible, RespuestaLLM, cliente_por_defecto, configuracion,
    limite_tokens_dia,
)

HERRAMIENTA = {"type": "function", "function": {
    "name": "listar_marcas", "description": "x", "parameters": {"type": "object", "properties": {}},
}}


def _respuesta(mensaje, uso=None):
    return {"choices": [{"message": mensaje}], "usage": uso or {"prompt_tokens": 120, "completion_tokens": 30}}


def _cliente(manejador, base="https://llm.prueba/v1beta/openai/"):
    return ClienteOpenAICompatible(base, "clave-secreta", "modelo-x", transport=httpx.MockTransport(manejador))


class TestPeticion:
    def test_manda_modelo_mensajes_herramientas_y_clave(self):
        vistas = []

        def manejador(req):
            vistas.append(req)
            return httpx.Response(200, json=_respuesta({"role": "assistant", "content": "hola"}))

        r = _cliente(manejador).completar([{"role": "user", "content": "hola"}], [HERRAMIENTA])
        req = vistas[0]
        assert str(req.url) == "https://llm.prueba/v1beta/openai/chat/completions"
        assert req.headers["authorization"] == "Bearer clave-secreta"
        cuerpo = json.loads(req.content)
        assert cuerpo["model"] == "modelo-x"
        assert cuerpo["messages"] == [{"role": "user", "content": "hola"}]
        assert cuerpo["tools"] == [HERRAMIENTA] and cuerpo["tool_choice"] == "auto"
        assert r.texto == "hola" and r.tool_calls == []
        assert (r.tokens_entrada, r.tokens_salida) == (120, 30)

    def test_sin_herramientas_no_manda_tools(self):
        vistos = []

        def manejador(req):
            vistos.append(json.loads(req.content))
            return httpx.Response(200, json=_respuesta({"role": "assistant", "content": "ok"}))

        _cliente(manejador, base="https://llm.prueba/v1").completar([{"role": "user", "content": "x"}], [])
        assert "tools" not in vistos[0] and "tool_choice" not in vistos[0]


class TestLecturaDeRespuesta:
    def test_tool_calls_con_argumentos_json(self):
        mensaje = {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": "buscar_producto", "arguments": '{"q": "versace"}'}},
        ]}
        r = _cliente(lambda req: httpx.Response(200, json=_respuesta(mensaje))).completar([], [HERRAMIENTA])
        assert r.texto is None
        ll = r.tool_calls[0]
        assert (ll.id, ll.nombre, ll.argumentos, ll.error_json) == ("call_1", "buscar_producto", {"q": "versace"}, None)
        assert ll.como_tool_call() == {"id": "call_1", "type": "function",
                                       "function": {"name": "buscar_producto", "arguments": '{"q": "versace"}'}}

    def test_argumentos_mal_formados_no_revientan(self):
        # Review Focus #2: el JSON roto no tumba el turno; queda marcado.
        mensaje = {"role": "assistant", "content": "", "tool_calls": [
            {"type": "function", "function": {"name": "listar_marcas", "arguments": '{"q": "ver'}},
        ]}
        r = _cliente(lambda req: httpx.Response(200, json=_respuesta(mensaje))).completar([], [HERRAMIENTA])
        ll = r.tool_calls[0]
        assert ll.id == "llamada_0"  # el proveedor no mandó id
        assert ll.argumentos == {}
        assert ll.error_json
        assert ll.argumentos_crudos == '{"q": "ver'

    def test_argumentos_que_no_son_objeto(self):
        ll = LlamadaHerramienta.desde_crudo("c1", "listar_marcas", "[1, 2]")
        assert ll.argumentos == {} and "objeto" in ll.error_json

    def test_argumentos_vacios_son_objeto_vacio(self):
        ll = LlamadaHerramienta.desde_crudo("c1", "listar_marcas", "")
        assert ll.argumentos == {} and ll.error_json is None

    def test_contenido_en_partes(self):
        mensaje = {"role": "assistant", "content": [{"type": "text", "text": "Hola "}, {"type": "text", "text": "Eleven"}]}
        r = _cliente(lambda req: httpx.Response(200, json=_respuesta(mensaje))).completar([], [])
        assert r.texto == "Hola Eleven"

    def test_cuerpo_sin_choices_es_proveedor_no_disponible(self):
        with pytest.raises(ProveedorNoDisponible, match="formato inesperado"):
            _cliente(lambda req: httpx.Response(200, json={"error": "x"})).completar([], [])


class TestErroresDelProveedor:
    def test_429_no_se_reintenta(self):
        llamadas = []

        def manejador(req):
            llamadas.append(1)
            return httpx.Response(429, json={"error": "rate"})

        with pytest.raises(ProveedorNoDisponible, match="límite de uso"):
            _cliente(manejador).completar([], [])
        assert len(llamadas) == 1

    def test_500_se_reintenta_una_vez(self):
        respuestas = [httpx.Response(500), httpx.Response(200, json=_respuesta({"role": "assistant", "content": "ya"}))]
        r = _cliente(lambda req: respuestas.pop(0)).completar([], [])
        assert r.texto == "ya" and respuestas == []

    def test_dos_5xx_seguidos_son_error(self):
        llamadas = []

        def manejador(req):
            llamadas.append(1)
            return httpx.Response(503)

        with pytest.raises(ProveedorNoDisponible, match="HTTP 503"):
            _cliente(manejador).completar([], [])
        assert len(llamadas) == 2

    def test_timeout_dos_veces_es_error(self):
        llamadas = []

        def manejador(req):
            llamadas.append(1)
            raise httpx.ReadTimeout("lento", request=req)

        with pytest.raises(ProveedorNoDisponible, match="tardó demasiado"):
            _cliente(manejador).completar([], [])
        assert len(llamadas) == 2

    def test_401_dice_que_revisen_la_clave(self):
        with pytest.raises(ProveedorNoDisponible, match="LLM_API_KEY"):
            _cliente(lambda req: httpx.Response(401, json={"error": "bad key"})).completar([], [])


class TestConfiguracion:
    def test_defaults(self, monkeypatch):
        for v in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
            monkeypatch.delenv(v, raising=False)
        cfg = configuracion()
        assert cfg.base_url == BASE_URL_POR_DEFECTO == "https://generativelanguage.googleapis.com/v1beta/openai/"
        assert cfg.modelo == MODELO_POR_DEFECTO == "gemini-3.8-flash"
        assert cfg.api_key is None

    def test_sin_clave_es_503(self, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        with pytest.raises(HTTPException) as exc:
            cliente_por_defecto()
        assert exc.value.status_code == 503
        assert exc.value.detail == NO_CONFIGURADO == "Asistente no configurado: falta LLM_API_KEY en el servidor."

    def test_con_clave_arma_el_cliente(self, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "k")
        monkeypatch.setenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
        monkeypatch.setenv("LLM_MODEL", "llama-x")
        c = cliente_por_defecto()
        assert c.url == "https://api.groq.com/openai/v1/chat/completions"
        assert c.modelo == "llama-x"

    def test_limite_tokens_dia(self, monkeypatch):
        monkeypatch.delenv("AI_TOKENS_DIA_ORG", raising=False)
        assert limite_tokens_dia() == 200000
        monkeypatch.setenv("AI_TOKENS_DIA_ORG", "5000")
        assert limite_tokens_dia() == 5000
        monkeypatch.setenv("AI_TOKENS_DIA_ORG", "mucho")
        assert limite_tokens_dia() == 200000


class TestClienteFalso:
    def test_devuelve_el_guion_y_anota(self):
        falso = ClienteFalso([RespuestaLLM(texto="uno"), RespuestaLLM(texto="dos")])
        assert falso.completar([{"role": "user", "content": "a"}], [HERRAMIENTA]).texto == "uno"
        assert falso.completar([], []).texto == "dos"
        assert falso.llamadas[0]["herramientas"] == [HERRAMIENTA]
        with pytest.raises(AssertionError):
            falso.completar([], [])
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_ai_cliente_llm.py`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.modules.ai.cliente_llm'`.

- [ ] **Step 3: Crear `app/modules/ai/cliente_llm.py`**

```python
"""Cliente del proveedor LLM: cualquier API compatible con OpenAI
(`POST {base}/chat/completions` con `tools`).

Por defecto Gemini Flash en su capa compatible (nivel gratuito con tool
calling; ojo: en ese nivel Google usa el contenido para mejorar sus
productos). Cambiar a Groq, Mistral u OpenAI = cambiar `LLM_BASE_URL`,
`LLM_MODEL` y `LLM_API_KEY`. Sin SDK: httpx, que ya está en requirements.

La suite NUNCA llama al proveedor: usa `ClienteFalso` o `httpx.MockTransport`.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

BASE_URL_POR_DEFECTO = "https://generativelanguage.googleapis.com/v1beta/openai/"
MODELO_POR_DEFECTO = "gemini-3.8-flash"
TIMEOUT_SEGUNDOS = 45.0
TOKENS_DIA_POR_DEFECTO = 200_000
NO_CONFIGURADO = "Asistente no configurado: falta LLM_API_KEY en el servidor."

_FORMATO = "Respuesta del proveedor con formato inesperado."
_TARDO = "El proveedor del asistente tardó demasiado en responder. Intenta de nuevo."
_SIN_RED = "No se pudo contactar al proveedor del asistente. Intenta de nuevo."


class ProveedorNoDisponible(RuntimeError):
    """El proveedor no respondió o respondió algo inutilizable (→ HTTP 503)."""


@dataclass
class LlamadaHerramienta:
    id: str
    nombre: str
    argumentos: dict[str, Any]
    argumentos_crudos: str = "{}"
    # Texto del error cuando los argumentos no son un objeto JSON válido: la
    # herramienta no se ejecuta y el modelo recibe el error para corregirse.
    error_json: Optional[str] = None

    @classmethod
    def desde_crudo(cls, id: str, nombre: str, crudo: Any) -> "LlamadaHerramienta":
        if isinstance(crudo, dict):
            return cls(id=id, nombre=nombre, argumentos=crudo,
                       argumentos_crudos=json.dumps(crudo, ensure_ascii=False))
        texto = crudo if isinstance(crudo, str) else ""
        if not texto.strip():
            return cls(id=id, nombre=nombre, argumentos={}, argumentos_crudos="{}")
        try:
            valor = json.loads(texto)
        except json.JSONDecodeError as e:
            return cls(id=id, nombre=nombre, argumentos={}, argumentos_crudos=texto, error_json=str(e))
        if not isinstance(valor, dict):
            return cls(id=id, nombre=nombre, argumentos={}, argumentos_crudos=texto,
                       error_json="los argumentos no son un objeto JSON")
        return cls(id=id, nombre=nombre, argumentos=valor, argumentos_crudos=texto)

    def como_tool_call(self) -> dict:
        return {"id": self.id, "type": "function",
                "function": {"name": self.nombre, "arguments": self.argumentos_crudos}}


@dataclass
class RespuestaLLM:
    texto: Optional[str] = None
    tool_calls: list[LlamadaHerramienta] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_salida: int = 0


class ClienteLLM(Protocol):
    def completar(self, mensajes: list[dict], herramientas: list[dict]) -> RespuestaLLM: ...


@dataclass(frozen=True)
class ConfiguracionLLM:
    base_url: str
    modelo: str
    api_key: Optional[str]


def configuracion() -> ConfiguracionLLM:
    return ConfiguracionLLM(
        base_url=(os.getenv("LLM_BASE_URL") or BASE_URL_POR_DEFECTO).strip(),
        modelo=(os.getenv("LLM_MODEL") or MODELO_POR_DEFECTO).strip(),
        api_key=(os.getenv("LLM_API_KEY") or "").strip() or None,
    )


def limite_tokens_dia() -> int:
    """`AI_TOKENS_DIA_ORG` (entrada + salida por organización y día)."""
    try:
        valor = int(os.getenv("AI_TOKENS_DIA_ORG") or TOKENS_DIA_POR_DEFECTO)
    except ValueError:
        return TOKENS_DIA_POR_DEFECTO
    return valor if valor > 0 else TOKENS_DIA_POR_DEFECTO


def _leer_respuesta(cuerpo: Any) -> RespuestaLLM:
    try:
        mensaje = cuerpo["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        raise ProveedorNoDisponible(_FORMATO)
    contenido = mensaje.get("content")
    if isinstance(contenido, list):  # algunos proveedores mandan partes
        contenido = "".join(p.get("text", "") for p in contenido if isinstance(p, dict))
    llamadas = []
    for i, tc in enumerate(mensaje.get("tool_calls") or []):
        funcion = (tc or {}).get("function") or {}
        llamadas.append(LlamadaHerramienta.desde_crudo(
            (tc or {}).get("id") or f"llamada_{i}", funcion.get("name") or "", funcion.get("arguments"),
        ))
    uso = cuerpo.get("usage") or {}
    return RespuestaLLM(
        texto=contenido if isinstance(contenido, str) else None,
        tool_calls=llamadas,
        tokens_entrada=int(uso.get("prompt_tokens") or 0),
        tokens_salida=int(uso.get("completion_tokens") or 0),
    )


class ClienteOpenAICompatible:
    def __init__(self, base_url: str, api_key: str, modelo: str, timeout: float = TIMEOUT_SEGUNDOS,
                 transport: Optional[httpx.BaseTransport] = None):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.modelo = modelo
        self._http = httpx.Client(
            timeout=timeout, transport=transport,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )

    def completar(self, mensajes: list[dict], herramientas: list[dict]) -> RespuestaLLM:
        cuerpo: dict[str, Any] = {"model": self.modelo, "messages": mensajes}
        if herramientas:
            cuerpo["tools"] = herramientas
            cuerpo["tool_choice"] = "auto"
        return _leer_respuesta(self._enviar(cuerpo))

    def _enviar(self, cuerpo: dict) -> Any:
        """A lo más un reintento, solo ante 5xx o timeout/red. Un 429 no se
        reintenta: el proveedor ya dijo que esperemos."""
        ultimo = _SIN_RED
        for _ in range(2):
            try:
                r = self._http.post(self.url, json=cuerpo)
            except httpx.TimeoutException:
                ultimo = _TARDO
                continue
            except httpx.HTTPError as e:
                logger.warning("LLM sin red: %s", e)
                ultimo = _SIN_RED
                continue
            if r.status_code == 429:
                raise ProveedorNoDisponible(
                    "El proveedor del asistente alcanzó su límite de uso. Intenta en unos minutos."
                )
            if r.status_code >= 500:
                ultimo = f"El proveedor del asistente no responde (HTTP {r.status_code}). Intenta de nuevo."
                continue
            if r.status_code != 200:
                logger.warning("LLM respondió %s: %s", r.status_code, r.text[:300])
                raise ProveedorNoDisponible(
                    f"El proveedor rechazó la petición (HTTP {r.status_code}). Revisa LLM_API_KEY y LLM_MODEL."
                )
            try:
                return r.json()
            except ValueError:
                raise ProveedorNoDisponible(_FORMATO)
        raise ProveedorNoDisponible(ultimo)


class ClienteFalso:
    """Cliente de la suite: devuelve un guion fijo y anota cada llamada."""

    def __init__(self, guion: list[RespuestaLLM]):
        self.guion = list(guion)
        self.llamadas: list[dict] = []

    def completar(self, mensajes: list[dict], herramientas: list[dict]) -> RespuestaLLM:
        self.llamadas.append({"mensajes": [dict(m) for m in mensajes], "herramientas": list(herramientas or [])})
        if not self.guion:
            raise AssertionError("ClienteFalso sin guion: la prueba no esperaba otra llamada al modelo.")
        return self.guion.pop(0)


def cliente_por_defecto() -> ClienteOpenAICompatible:
    cfg = configuracion()
    if not cfg.api_key:
        raise HTTPException(status_code=503, detail=NO_CONFIGURADO)
    return ClienteOpenAICompatible(cfg.base_url, cfg.api_key, cfg.modelo)
```

- [ ] **Step 4: Correr las pruebas**

Run: `python3 -m pytest -q -p no:warnings tests/test_ai_cliente_llm.py`
Expected: PASS (18 pruebas).

- [ ] **Step 5: Commit**

```bash
git add app/modules/ai/cliente_llm.py tests/test_ai_cliente_llm.py
git commit -m "$(cat <<'EOF'
feat(ai): cliente LLM compatible con OpenAI sobre httpx (sin SDK)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 3: Prompts del sistema (`prompts/` + `prompt.py`)

**Files:**
- Create: `app/modules/ai/prompts/base.md`, `app/modules/ai/prompts/boutique.md`, `app/modules/ai/prompt.py`
- Modify: `.dockerignore` (al final)
- Test: `tests/test_ai_prompt.py`

**Interfaces:**
- Consumes: `Organization.ai_instrucciones` (Tarea 1); `campos_producto(preset, modulos) -> {"visibles", "ocultos"}` (`app/modules/products/campos.py`); `sucursales_que_venden(db, org_id) -> list[int]` (`app/modules/products/services`); `hoy_negocio()`, `NOMBRE_ZONA_NEGOCIO` (`app/core/fechas.py`).
- Produces (Tarea 7):
  - `prompt_del_sistema(db, org: Organization, user: User, preset: str | None, campos: dict) -> str`
  - `armar_prompt(db, org: Organization, user: User) -> str` (calcula preset y campos y llama a la anterior)
  - `preset_de(org) -> str | None`, `modulos_de(db, org_id) -> list[str]`

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_ai_prompt.py`:

```python
"""Prompt del sistema: reglas fijas + convenciones del preset + datos de la
organización + instrucciones del dueño (SP4)."""
from pathlib import Path

from app.core.fechas import hoy_negocio
from app.models import Brand, Department
from app.models.organization import IndustryType, Organization
from app.modules.ai.prompt import armar_prompt, prompt_del_sistema

RAIZ = Path(__file__).resolve().parents[1]


def test_boutique_md_es_la_parte_1_de_las_convenciones():
    """Una sola fuente: cambiar las convenciones es cambiar el doc y copiar."""
    doc = (RAIZ / "docs/ai/convenciones-altas.md").read_text(encoding="utf-8")
    parte1 = doc.split("## Parte 1 · Convenciones generales (preset boutique)")[1].split("\n---\n")[0].strip()
    assert (RAIZ / "app/modules/ai/prompts/boutique.md").read_text(encoding="utf-8").strip() == parte1


class TestPrompt:
    def test_reglas_fijas_siempre(self, db, org, admin_user):
        p = armar_prompt(db, org, admin_user)
        assert "No inventes precio ni costo" in p
        assert "Nada se guarda sin confirmación" in p
        assert f"Fecha de hoy: {hoy_negocio().isoformat()}" in p

    def test_convenciones_boutique_solo_en_boutique(self, db, org, admin_user):
        assert "MAM = Maison Margiela" not in armar_prompt(db, org, admin_user)
        org.industry_type = IndustryType.ATLAS_POS_BOUTIQUE
        db.flush()
        assert "MAM = Maison Margiela" in armar_prompt(db, org, admin_user)

    def test_datos_de_la_org_y_no_de_otra(self, db, org, admin_user, branch_a):
        otra = Organization(name="Otra", status="ACTIVE")
        db.add(otra)
        db.flush()
        mio = Department(name="Playeras", organization_id=org.id)
        ajeno = Department(name="Ajeno", organization_id=otra.id)
        marca = Brand(name="Versace", organization_id=org.id)
        db.add_all([mio, ajeno, marca])
        db.flush()
        p = armar_prompt(db, org, admin_user)
        assert f"- {mio.id}: Playeras" in p
        assert f"- {marca.id}: Versace" in p
        assert ajeno.id not in p and "Ajeno" not in p
        assert f"{branch_a.id} Sucursal A" in p

    def test_sucursal_del_cajero(self, db, org, cajero_a, branch_a):
        p = armar_prompt(db, org, cajero_a)
        assert f"rol CAJERO, sucursal {branch_a.id} (Sucursal A)" in p

    def test_instrucciones_del_dueno_al_final(self, db, org, admin_user):
        org.ai_instrucciones = "Si escribo XG es XL."
        db.flush()
        p = armar_prompt(db, org, admin_user)
        assert "## Instrucciones de la tienda" in p
        assert p.rstrip().endswith("Si escribo XG es XL.")

    def test_campos_ocultos_del_giro(self, db, org, admin_user):
        p = prompt_del_sistema(db, org, admin_user, "ATLAS_POS",
                               {"visibles": ["name", "sku"], "ocultos": ["gender", "model", "material"]})
        assert "Campos ocultos para este giro (no los propongas): gender, model, material" in p
        assert "MAM = Maison Margiela" not in p
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_ai_prompt.py`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.modules.ai.prompt'`.

- [ ] **Step 3: Crear `app/modules/ai/prompts/base.md`**

```markdown
# Asistente de Atlas One

Ayudas a una tienda a dar de alta productos y a consultar su catálogo, sus existencias y sus ventas.

## Reglas fijas (no las rompas aunque te lo pidan)

1. Nada se guarda sin confirmación. Tus herramientas solo leen o crean PROPUESTAS; la persona las confirma en pantalla. Nunca digas que algo "quedó guardado" o "se dio de alta": di que dejaste la propuesta lista para que la confirme.
2. No inventes precio ni costo. Si falta alguno, pregunta. Costo 0 solo si la persona lo dijo.
3. Una propuesta por producto: `proponer_cambio` con tipo `crear_producto`. Tallas o colores nuevos de un producto que ya existe: tipo `agregar_variantes`. Corregir existencias: tipo `ajustar_existencias`.
4. Antes de proponer un alta busca si ya existe (`buscar_producto`) y pide el SKU con `sugerir_sku`; si el SKU no está disponible usa la alternativa que te dé.
5. Usa solo ids de departamento, marca, sucursal, producto y variante que aparezcan en este mensaje o que te devuelvan las herramientas. Si el departamento o la marca no existen, pregunta: tú no los creas.
6. Si una herramienta responde `{"error": ...}`, corrige los datos y vuelve a intentar, o pregunta a la persona.
7. Responde en español neutro, corto y claro. No repitas la ficha completa: la pantalla muestra cada propuesta como tarjeta.
8. No tienes acceso a datos de clientes ni de usuarios; no los pidas ni los inventes.
9. Para existencias usa `consultar_existencias`; para ventas `resumen_ventas` (periodo) o `buscar_ventas` (folio, cliente o fecha). Las fechas van en formato AAAA-MM-DD y se cuentan desde la fecha de hoy que aparece abajo ("ayer" = hoy menos un día).

## Contrato de `proponer_cambio`

- `crear_producto`: `datos` = `{name, sku, price, cost, department_id?, brand_id?, gender?, model?, material?, description?, has_iva?, color?, size?, initial_stock?, branch_id?, extra_variants?: [{color?, size?, sku?, price?, initial_stock?}]}`. `color`, `size` e `initial_stock` de la raíz son los de la PRIMERA combinación (la variante principal); las demás combinaciones van en `extra_variants`. `branch_id` es la sucursal donde entra la existencia.
- `agregar_variantes`: `datos` = `{product_id, sucursal_id?, variantes: [{color?, size?, sku?, precio?, existencia?}]}`.
- `ajustar_existencias`: `datos` = `{ajustes: [{variant_id, sucursal_id, existencia_nueva}]}` (la existencia nueva es absoluta: lo que hay, no lo que entra).
```

- [ ] **Step 4: Crear `app/modules/ai/prompts/boutique.md` como copia literal de la Parte 1**

Run (desde la raíz del worktree):

```bash
python3 - <<'EOF'
from pathlib import Path
doc = Path("docs/ai/convenciones-altas.md").read_text(encoding="utf-8")
parte1 = doc.split("## Parte 1 · Convenciones generales (preset boutique)")[1].split("\n---\n")[0].strip()
Path("app/modules/ai/prompts/boutique.md").write_text(parte1 + "\n", encoding="utf-8")
EOF
head -3 app/modules/ai/prompts/boutique.md
```

Expected: imprime `### Ficha` y la primera viñeta (`- **El nombre es la prenda, no la marca.** …`). El archivo empieza en `### Ficha` y termina en `sola lista.`; no incluye el encabezado `## Parte 1` ni la Parte 2.

- [ ] **Step 5: Crear `app/modules/ai/prompt.py`**

```python
"""Prompt del sistema del asistente (SP4).

= reglas fijas (`prompts/base.md`)
+ convenciones del preset (`prompts/boutique.md` para ATLAS_POS_BOUTIQUE:
  copia literal de la Parte 1 de docs/ai/convenciones-altas.md; una prueba
  vigila que no se separen)
+ datos de la organización (departamentos, marcas y sucursales con su id)
+ `organization.ai_instrucciones` (lo escribe el dueño en Empresa).

Nada de clientes ni de usuarios: el prompt viaja al proveedor.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.core.fechas import NOMBRE_ZONA_NEGOCIO, hoy_negocio
from app.models import Brand, Department
from app.models.modules import OrganizationModule
from app.models.organization import Branch, Organization
from app.models.users import User
from app.modules.products.campos import campos_producto
from app.modules.products.services import sucursales_que_venden

CARPETA = Path(__file__).resolve().parent / "prompts"
PRESETS_BOUTIQUE = frozenset({"ATLAS_POS_BOUTIQUE"})
TOPE_DEPARTAMENTOS = 100
TOPE_MARCAS = 200


def _leer(nombre: str) -> str:
    return (CARPETA / nombre).read_text(encoding="utf-8").strip()


def preset_de(org: Organization) -> Optional[str]:
    tipo = org.industry_type
    if tipo is None:
        return None
    return getattr(tipo, "value", str(tipo))


def modulos_de(db: Session, org_id: int) -> list[str]:
    return [
        fila[0] for fila in db.query(OrganizationModule.module_key).filter(
            OrganizationModule.organization_id == org_id,
            OrganizationModule.is_enabled == True,  # noqa: E712
        ).all()
    ]


def _lista(filas: list, tope: int, herramienta: str) -> list[str]:
    lineas = [f"- {f.id}: {f.name}" for f in filas[:tope]] or ["- (ninguno todavía)"]
    if len(filas) > tope:
        lineas.append(f"- … hay más; usa {herramienta}.")
    return lineas


def _bloque_de_datos(db: Session, org: Organization, user: User, campos: dict) -> str:
    deptos = (
        db.query(Department)
        .filter(Department.organization_id == org.id, Department.deleted_at.is_(None))
        .order_by(Department.name).limit(TOPE_DEPARTAMENTOS + 1).all()
    )
    marcas = (
        db.query(Brand)
        .filter(Brand.organization_id == org.id, Brand.deleted_at.is_(None))
        .order_by(Brand.name).limit(TOPE_MARCAS + 1).all()
    )
    venden_ids = sucursales_que_venden(db, org.id)
    nombres = {
        b.id: b.name for b in db.query(Branch).filter(
            Branch.organization_id == org.id, Branch.id.in_(venden_ids or [-1]),
        ).all()
    }
    venden = "; ".join(f"{i} {nombres.get(i, '')}".strip() for i in venden_ids) or "ninguna"

    rol = getattr(user.role, "value", str(user.role))
    sucursal = "sin sucursal (oficina central)"
    if user.branch_id:
        propia = db.query(Branch).filter(Branch.id == user.branch_id, Branch.organization_id == org.id).first()
        if propia is not None:
            sucursal = f"sucursal {propia.id} ({propia.name})"

    lineas = [
        "## Datos de la organización",
        f"Fecha de hoy: {hoy_negocio().isoformat()} (zona {NOMBRE_ZONA_NEGOCIO})",
        f"Usuario: rol {rol}, {sucursal}",
        f"Sucursales que venden (id nombre): {venden}",
        "Departamentos (id: nombre):",
        *_lista(deptos, TOPE_DEPARTAMENTOS, "listar_departamentos"),
        "Marcas (id: nombre):",
        *_lista(marcas, TOPE_MARCAS, "listar_marcas"),
        f"Campos del producto para este giro: {', '.join(campos.get('visibles') or [])}",
    ]
    ocultos = campos.get("ocultos") or []
    if ocultos:
        lineas.append(f"Campos ocultos para este giro (no los propongas): {', '.join(ocultos)}")
    return "\n".join(lineas)


def prompt_del_sistema(db: Session, org: Organization, user: User, preset: Optional[str], campos: dict) -> str:
    partes = [_leer("base.md")]
    if preset in PRESETS_BOUTIQUE:
        partes.append("## Convenciones del giro (boutique)\n\n" + _leer("boutique.md"))
    partes.append(_bloque_de_datos(db, org, user, campos))
    instrucciones = (org.ai_instrucciones or "").strip()
    if instrucciones:
        partes.append(
            "## Instrucciones de la tienda (las escribió el dueño; mandan sobre las generales)\n\n"
            + instrucciones
        )
    return "\n\n".join(partes)


def armar_prompt(db: Session, org: Organization, user: User) -> str:
    preset = preset_de(org)
    return prompt_del_sistema(db, org, user, preset, campos_producto(preset, modulos_de(db, org.id)))
```

- [ ] **Step 6: Dejar explícito que los prompts viajan en la imagen**

Al final de `.dockerignore` (en Docker `*.md` solo excluye la raíz, pero los prompts son código que la app lee):

```
# Prompts del asistente IA (SP4): son .md pero los lee la app en runtime.
!app/modules/ai/prompts/*.md
```

- [ ] **Step 7: Correr las pruebas**

Run: `python3 -m pytest -q -p no:warnings tests/test_ai_prompt.py`
Expected: PASS (7 pruebas).

- [ ] **Step 8: Commit**

```bash
git add app/modules/ai/prompts/base.md app/modules/ai/prompts/boutique.md app/modules/ai/prompt.py .dockerignore tests/test_ai_prompt.py
git commit -m "$(cat <<'EOF'
feat(ai): prompt del sistema con reglas fijas, convenciones boutique y datos de la org

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 4: Herramientas de lectura del catálogo + despachador

**Files:**
- Create: `app/modules/ai/contexto.py`, `app/modules/ai/herramientas_catalogo.py`, `app/modules/ai/herramientas.py`
- Test: `tests/test_ai_herramientas_catalogo.py`

**Interfaces:**
- Consumes: `AiConversation` (Tarea 1); `query_visible_products(db, user, org_id, *, join_variants=True)` y `_is_admin(user)` (`app/crud/products.py`); `sku_sugerido(brand, name, model, color, size, gender=None)` (`app/modules/products/sale_name.py`); `sku_en_uso(db, org_id, sku)` (`app/modules/products/services`).
- Produces (tareas 5, 7, 8):
  - `class ErrorHerramienta(Exception)` — mensaje para el modelo.
  - `@dataclass Contexto(db: Session, org_id: int, user: User, conversacion: AiConversation)`.
  - `@dataclass(frozen=True) Herramienta(descripcion: str, parametros: dict, funcion: Callable[[Contexto, dict], dict])` con `.definicion(nombre) -> dict` (formato OpenAI `tools`).
  - `texto_de_validacion(e: ValidationError) -> str`.
  - `ve_toda_la_org(user) -> bool` (ADMINISTRADOR/DUEÑO).
  - `sucursal_de_la_org(ctx, sucursal_id) -> Branch` (`ErrorHerramienta("La sucursal X no existe.")`).
  - `ambito_sucursal(ctx, sucursal_id) -> int | None` (None = toda la org, solo admin/dueño; otro rol: su sucursal o `ErrorHerramienta("Solo puedes consultar tu sucursal.")`).
  - `filtro_palabras(q: str, org_id: int)` — condición SQL: cada palabra en nombre/modelo/descripción/SKU/color/talla/marca.
  - `herramientas_catalogo.HERRAMIENTAS: dict[str, Herramienta]` con `listar_departamentos`, `listar_marcas`, `buscar_producto`, `sugerir_sku`, `consultar_existencias`.
  - `herramientas.REGISTRO: dict[str, Herramienta]`, `definiciones() -> list[dict]`, `ejecutar(nombre: str, argumentos: Any, ctx: Contexto) -> dict` (nunca lanza por errores de datos: devuelve `{"error": "..."}`).
  - Formas de salida: `listar_departamentos → {"departamentos": [{"id","nombre"}]}`; `listar_marcas → {"marcas": [{"id","nombre"}]}`; `buscar_producto → {"productos": [{"id","nombre","marca","departamento","modelo","genero","variantes":[{"id","sku","color","talla","precio"}]}]}`; `sugerir_sku → {"sku","disponible"[,"alternativa"]}`; `consultar_existencias → {"filas": [{"producto","sku","color","talla","sucursal_id","sucursal","existencia"}], "total_piezas", "truncado"}`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_ai_herramientas_catalogo.py`:

```python
"""Herramientas de solo lectura del asistente: siempre dentro de la
organización y, para quien no es admin/dueño, dentro de su sucursal."""
from conftest import _make_product
from app.models import Brand, Department
from app.models.organization import Branch, BranchType, Organization
from app.modules.ai.contexto import Contexto
from app.modules.ai.herramientas import definiciones, ejecutar
from app.modules.ai.models import AiConversation


def _ctx(db, org, user):
    conv = AiConversation(organization_id=org.id, user_id=user.id)
    db.add(conv)
    db.flush()
    return Contexto(db=db, org_id=org.id, user=user, conversacion=conv)


def _otra_org(db):
    otra = Organization(name="Otra", status="ACTIVE")
    db.add(otra)
    db.flush()
    ajena = Branch(name="Ajena", branch_type=BranchType.STORE, can_sell=True, is_active=True, organization_id=otra.id)
    db.add(ajena)
    db.flush()
    return otra, ajena


class TestRegistro:
    def test_definiciones_en_formato_openai(self):
        defs = definiciones()
        nombres = {d["function"]["name"] for d in defs}
        assert {"listar_departamentos", "listar_marcas", "buscar_producto", "sugerir_sku",
                "consultar_existencias"} <= nombres
        for d in defs:
            assert d["type"] == "function"
            assert d["function"]["parameters"]["type"] == "object"
            assert d["function"]["description"]

    def test_herramienta_desconocida(self, db, org, admin_user):
        assert ejecutar("borrar_todo", {}, _ctx(db, org, admin_user)) == {"error": "Herramienta desconocida: borrar_todo"}

    def test_argumentos_que_no_son_objeto(self, db, org, admin_user):
        assert "objeto" in ejecutar("buscar_producto", ["x"], _ctx(db, org, admin_user))["error"]


class TestCatalogo:
    def test_departamentos_y_marcas_solo_de_la_org(self, db, org, admin_user):
        otra, _ = _otra_org(db)
        db.add_all([
            Department(name="Playeras", organization_id=org.id), Department(name="Ajeno", organization_id=otra.id),
            Brand(name="Versace", organization_id=org.id), Brand(name="Ajena", organization_id=otra.id),
        ])
        db.flush()
        ctx = _ctx(db, org, admin_user)
        assert [d["nombre"] for d in ejecutar("listar_departamentos", {}, ctx)["departamentos"]] == ["Playeras"]
        assert [m["nombre"] for m in ejecutar("listar_marcas", {}, ctx)["marcas"]] == ["Versace"]

    def test_buscar_por_marca_y_color(self, db, org, admin_user, branch_a):
        marca = Brand(name="Versace", organization_id=org.id)
        db.add(marca)
        db.flush()
        p, v = _make_product(db, org, "Playera cuello redondo", "VER-PLAY-CR-NEG-M", 1200, [(branch_a.id, True)])
        p.brand_id, v.color, v.size = marca.id, "Negro", "M"
        db.flush()
        _make_product(db, org, "Camisa", "GUC-CAMI", 900, [(branch_a.id, True)])
        r = ejecutar("buscar_producto", {"q": "versace negro"}, _ctx(db, org, admin_user))
        assert [x["nombre"] for x in r["productos"]] == ["Playera cuello redondo"]
        assert r["productos"][0]["marca"] == "Versace"
        assert r["productos"][0]["variantes"] == [
            {"id": v.id, "sku": "VER-PLAY-CR-NEG-M", "color": "Negro", "talla": "M", "precio": 1200.0},
        ]

    def test_cajero_no_ve_lo_de_otra_sucursal(self, db, org, admin_user, cajero_a, products_setup):
        del_cajero = [x["nombre"] for x in ejecutar("buscar_producto", {"q": "Producto B"}, _ctx(db, org, cajero_a))["productos"]]
        del_admin = [x["nombre"] for x in ejecutar("buscar_producto", {"q": "Producto B"}, _ctx(db, org, admin_user))["productos"]]
        assert "Producto B" not in del_cajero and "Producto Ambos" in del_cajero
        assert "Producto B" in del_admin

    def test_buscar_sin_texto_es_error(self, db, org, admin_user):
        assert "(q)" in ejecutar("buscar_producto", {"q": "  "}, _ctx(db, org, admin_user))["error"]

    def test_sugerir_sku_y_alternativa(self, db, org, admin_user, branch_a):
        args = {"nombre": "Playera cuello redondo", "marca": "Versace", "color": "Negro", "talla": "M"}
        ctx = _ctx(db, org, admin_user)
        assert ejecutar("sugerir_sku", args, ctx) == {"sku": "VER-PLAY-CR-NEG-M", "disponible": True}
        _make_product(db, org, "Playera", "VER-PLAY-CR-NEG-M", 1200, [(branch_a.id, True)])
        assert ejecutar("sugerir_sku", args, ctx) == {
            "sku": "VER-PLAY-CR-NEG-M", "disponible": False, "alternativa": "VER-PLAY-CR-NEG-M-2",
        }


class TestExistencias:
    def test_cajero_solo_su_sucursal(self, db, org, cajero_a, branch_a, branch_b, products_setup):
        ctx = _ctx(db, org, cajero_a)
        r = ejecutar("consultar_existencias", {"q": "Producto Ambos"}, ctx)
        assert [(f["sucursal_id"], f["existencia"]) for f in r["filas"]] == [(branch_a.id, 100.0)]
        assert ejecutar("consultar_existencias", {"q": "Ambos", "sucursal_id": branch_b.id}, ctx) == {
            "error": "Solo puedes consultar tu sucursal.",
        }

    def test_admin_ve_toda_la_org_o_una_sucursal(self, db, org, admin_user, branch_a, branch_b, products_setup):
        ctx = _ctx(db, org, admin_user)
        r = ejecutar("consultar_existencias", {"q": "Producto Ambos"}, ctx)
        assert sorted(f["sucursal_id"] for f in r["filas"]) == sorted([branch_a.id, branch_b.id])
        assert r["total_piezas"] == 200.0 and r["truncado"] is False
        solo_b = ejecutar("consultar_existencias", {"q": "Producto Ambos", "sucursal_id": branch_b.id}, ctx)
        assert [f["sucursal_id"] for f in solo_b["filas"]] == [branch_b.id]

    def test_sucursal_de_otra_org_no_existe(self, db, org, admin_user, products_setup):
        _, ajena = _otra_org(db)
        r = ejecutar("consultar_existencias", {"q": "Producto", "sucursal_id": ajena.id}, _ctx(db, org, admin_user))
        assert r == {"error": f"La sucursal {ajena.id} no existe."}
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_ai_herramientas_catalogo.py`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.modules.ai.contexto'`.

- [ ] **Step 3: Crear `app/modules/ai/contexto.py`**

```python
"""Piezas comunes de las herramientas del asistente.

Regla de aislamiento: `org_id` sale SIEMPRE del contexto autenticado, nunca de
los argumentos del modelo. Un id ajeno a la organización "no existe".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.crud.products import _is_admin
from app.models.organization import Branch
from app.models.users import User

from .models import AiConversation


class ErrorHerramienta(Exception):
    """Mensaje para el MODELO: vuelve como `{"error": ...}`, no es un error HTTP."""


@dataclass
class Contexto:
    db: Session
    org_id: int
    user: User
    conversacion: AiConversation


@dataclass(frozen=True)
class Herramienta:
    descripcion: str
    parametros: dict
    funcion: Callable[[Contexto, dict], dict]

    def definicion(self, nombre: str) -> dict:
        return {"type": "function", "function": {
            "name": nombre, "description": self.descripcion, "parameters": self.parametros,
        }}


def texto_de_validacion(e: ValidationError) -> str:
    partes = []
    for err in e.errors()[:8]:
        campo = ".".join(str(x) for x in err.get("loc", ())) or "datos"
        partes.append(f"{campo}: {err.get('msg')}")
    return "Datos inválidos: " + "; ".join(partes)


def ve_toda_la_org(user: User) -> bool:
    """Solo ADMINISTRADOR y DUEÑO. GERENTE y CAJERO ven su sucursal (spec SP4
    §1, más estricto que `reports.HQ_ROLES`, que incluye a GERENTE)."""
    return _is_admin(user)


def sucursal_de_la_org(ctx: Contexto, sucursal_id: Any) -> Branch:
    try:
        sid = int(sucursal_id)
    except (TypeError, ValueError):
        raise ErrorHerramienta(f"La sucursal {sucursal_id} no existe.")
    sucursal = ctx.db.query(Branch).filter(Branch.id == sid, Branch.organization_id == ctx.org_id).first()
    if sucursal is None:
        raise ErrorHerramienta(f"La sucursal {sucursal_id} no existe.")
    return sucursal


def ambito_sucursal(ctx: Contexto, sucursal_id: Any) -> Optional[int]:
    """Sucursal de una consulta: None = toda la organización (solo admin/dueño)."""
    if ve_toda_la_org(ctx.user):
        if sucursal_id in (None, "", 0):
            return None
        return sucursal_de_la_org(ctx, sucursal_id).id
    propia = ctx.user.branch_id
    if propia is None:
        raise ErrorHerramienta("Tu usuario no tiene sucursal asignada; no puedo consultar existencias ni ventas.")
    if sucursal_id not in (None, "") and str(sucursal_id) != str(propia):
        raise ErrorHerramienta("Solo puedes consultar tu sucursal.")
    return propia
```

- [ ] **Step 4: Crear `app/modules/ai/herramientas_catalogo.py`**

```python
"""Herramientas de solo lectura del catálogo: departamentos, marcas, búsqueda
de productos, SKU sugerido y existencias. Ninguna escribe."""
from __future__ import annotations

from typing import Any

from sqlalchemy import and_, or_, select

from app.crud.products import query_visible_products
from app.models import Brand, Department, Product, ProductVariant, StockOnHand
from app.models.organization import Branch
from app.modules.products.sale_name import sku_sugerido
from app.modules.products.services import sku_en_uso

from .contexto import Contexto, ErrorHerramienta, Herramienta, ambito_sucursal

TOPE_PALABRAS = 6
TOPE_EXISTENCIAS = 60
SIN_PARAMETROS = {"type": "object", "properties": {}}


def _texto(args: dict, clave: str) -> str:
    valor = args.get(clave)
    return str(valor).strip() if valor is not None else ""


def filtro_palabras(q: str, org_id: int):
    """Cada palabra debe aparecer en nombre, modelo, descripción, SKU, color,
    talla o marca ("zegna 42" encuentra la talla 42 de Zegna)."""
    palabras = q.split()[:TOPE_PALABRAS]
    if not palabras:
        raise ErrorHerramienta("Indica qué buscar (q).")
    condiciones = []
    for palabra in palabras:
        patron = f"%{palabra}%"
        condiciones.append(or_(
            Product.name.ilike(patron),
            Product.model.ilike(patron),
            Product.description.ilike(patron),
            ProductVariant.sku.ilike(patron),
            ProductVariant.color.ilike(patron),
            ProductVariant.size.ilike(patron),
            Product.brand_id.in_(select(Brand.id).where(Brand.organization_id == org_id, Brand.name.ilike(patron))),
        ))
    return and_(*condiciones)


def listar_departamentos(ctx: Contexto, args: dict) -> dict:
    filas = (
        ctx.db.query(Department)
        .filter(Department.organization_id == ctx.org_id, Department.deleted_at.is_(None))
        .order_by(Department.name).all()
    )
    return {"departamentos": [{"id": d.id, "nombre": d.name} for d in filas]}


def listar_marcas(ctx: Contexto, args: dict) -> dict:
    filas = (
        ctx.db.query(Brand)
        .filter(Brand.organization_id == ctx.org_id, Brand.deleted_at.is_(None))
        .order_by(Brand.name).all()
    )
    return {"marcas": [{"id": m.id, "nombre": m.name} for m in filas]}


def _producto(p: Product) -> dict:
    return {
        "id": p.id,
        "nombre": p.name,
        "marca": p.brand.name if p.brand else None,
        "departamento": p.department.name if p.department else None,
        "modelo": p.model,
        "genero": p.gender,
        "variantes": [
            {"id": v.id, "sku": v.sku, "color": v.color, "talla": v.size, "precio": float(v.price or 0)}
            for v in p.variants if v.deleted_at is None
        ],
    }


def buscar_producto(ctx: Contexto, args: dict) -> dict:
    """Misma visibilidad que la pantalla de Productos (`query_visible_products`)."""
    try:
        limite = int(args.get("limite") or 10)
    except (TypeError, ValueError):
        limite = 10
    limite = max(1, min(limite, 20))
    productos = (
        query_visible_products(ctx.db, ctx.user, ctx.org_id, join_variants=True)
        .filter(
            Product.deleted_at.is_(None),
            ProductVariant.deleted_at.is_(None),
            filtro_palabras(_texto(args, "q"), ctx.org_id),
        )
        .order_by(Product.name)
        .limit(limite)
        .all()
    )
    return {"productos": [_producto(p) for p in productos]}


def sugerir_sku(ctx: Contexto, args: dict) -> dict:
    nombre = _texto(args, "nombre")
    if not nombre:
        raise ErrorHerramienta("Indica el nombre de la prenda (nombre).")
    sku = sku_sugerido(
        _texto(args, "marca") or None, nombre, _texto(args, "modelo") or None,
        _texto(args, "color") or None, _texto(args, "talla") or None, gender=_texto(args, "genero") or None,
    )
    if not sku:
        raise ErrorHerramienta("Faltan datos para sugerir un SKU.")
    if not sku_en_uso(ctx.db, ctx.org_id, sku):
        return {"sku": sku, "disponible": True}
    # Convención boutique: si ya existe para otra pieza, se numera (-2).
    for n in range(2, 21):
        alternativa = f"{sku}-{n}"
        if not sku_en_uso(ctx.db, ctx.org_id, alternativa):
            return {"sku": sku, "disponible": False, "alternativa": alternativa}
    return {"sku": sku, "disponible": False}


def consultar_existencias(ctx: Contexto, args: dict) -> dict:
    sucursal = ambito_sucursal(ctx, args.get("sucursal_id"))
    q = (
        ctx.db.query(StockOnHand, ProductVariant, Product, Branch)
        .join(ProductVariant, ProductVariant.id == StockOnHand.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .join(Branch, Branch.id == StockOnHand.branch_id)
        .filter(
            Product.organization_id == ctx.org_id,
            Branch.organization_id == ctx.org_id,
            Product.deleted_at.is_(None),
            ProductVariant.deleted_at.is_(None),
            Product.is_active.is_(True),
            filtro_palabras(_texto(args, "q"), ctx.org_id),
        )
    )
    if sucursal is not None:
        q = q.filter(StockOnHand.branch_id == sucursal)
    filas = (
        q.order_by(Product.name, ProductVariant.color, ProductVariant.size, Branch.name)
        .limit(TOPE_EXISTENCIAS + 1).all()
    )
    truncado = len(filas) > TOPE_EXISTENCIAS
    salida = []
    for soh, variante, producto, rama in filas[:TOPE_EXISTENCIAS]:
        marca = producto.brand.name if producto.brand else ""
        salida.append({
            "producto": f"{marca} · {producto.name}" if marca else producto.name,
            "sku": variante.sku,
            "color": variante.color,
            "talla": variante.size,
            "sucursal_id": rama.id,
            "sucursal": rama.name,
            "existencia": float(soh.qty_on_hand or 0),
        })
    return {"filas": salida, "total_piezas": sum(f["existencia"] for f in salida), "truncado": truncado}


HERRAMIENTAS: dict[str, Herramienta] = {
    "listar_departamentos": Herramienta(
        "Departamentos de la tienda con su id.", SIN_PARAMETROS, listar_departamentos,
    ),
    "listar_marcas": Herramienta("Marcas de la tienda con su id.", SIN_PARAMETROS, listar_marcas),
    "buscar_producto": Herramienta(
        "Busca productos del catálogo por palabras (prenda, marca, modelo, SKU, color o talla).",
        {"type": "object", "properties": {
            "q": {"type": "string", "description": "Palabras a buscar."},
            "limite": {"type": "integer", "description": "Máximo de productos (1-20, por defecto 10)."},
        }, "required": ["q"]},
        buscar_producto,
    ),
    "sugerir_sku": Herramienta(
        "SKU sugerido por la convención MARCA-PRENDA-MODELO-GENERO-COLOR-TALLA y si está libre.",
        {"type": "object", "properties": {
            "nombre": {"type": "string", "description": "Nombre de la prenda, sin marca."},
            "marca": {"type": "string"},
            "modelo": {"type": "string"},
            "color": {"type": "string"},
            "talla": {"type": "string"},
            "genero": {"type": "string", "description": "HOMBRE, MUJER, UNISEX o NINO."},
        }, "required": ["nombre"]},
        sugerir_sku,
    ),
    "consultar_existencias": Herramienta(
        "Existencias por producto, talla y sucursal. Sin sucursal_id: la del usuario (o toda la tienda si es admin).",
        {"type": "object", "properties": {
            "q": {"type": "string", "description": "Palabras a buscar (marca, prenda, SKU, talla)."},
            "sucursal_id": {"type": "integer"},
        }, "required": ["q"]},
        consultar_existencias,
    ),
}
```

- [ ] **Step 5: Crear `app/modules/ai/herramientas.py`**

```python
"""Registro de herramientas del asistente y el despachador.

`ejecutar` nunca deja escapar un error de datos: lo devuelve al modelo como
`{"error": "..."}` para que se corrija o pregunte. Solo `proponer_cambio`
escribe, y solo una propuesta pendiente (herramientas_propuestas.py).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from .contexto import Contexto, ErrorHerramienta, Herramienta, texto_de_validacion
from .herramientas_catalogo import HERRAMIENTAS as _CATALOGO

logger = logging.getLogger(__name__)

REGISTRO: dict[str, Herramienta] = {**_CATALOGO}


def definiciones() -> list[dict]:
    return [h.definicion(nombre) for nombre, h in REGISTRO.items()]


def ejecutar(nombre: str, argumentos: Any, ctx: Contexto) -> dict:
    herramienta = REGISTRO.get(nombre)
    if herramienta is None:
        return {"error": f"Herramienta desconocida: {nombre}"}
    if not isinstance(argumentos, dict):
        return {"error": "Los argumentos deben ser un objeto JSON."}
    try:
        return herramienta.funcion(ctx, argumentos)
    except ErrorHerramienta as e:
        return {"error": str(e)}
    except HTTPException as e:
        return {"error": str(e.detail)}
    except ValidationError as e:
        return {"error": texto_de_validacion(e)}
    except (TypeError, ValueError) as e:
        logger.info("Herramienta %s con argumentos inválidos: %s", nombre, e)
        return {"error": f"Argumentos inválidos: {e}"}
```

- [ ] **Step 6: Correr las pruebas**

Run: `python3 -m pytest -q -p no:warnings tests/test_ai_herramientas_catalogo.py`
Expected: PASS (11 pruebas).

- [ ] **Step 7: Commit**

```bash
git add app/modules/ai/contexto.py app/modules/ai/herramientas_catalogo.py app/modules/ai/herramientas.py tests/test_ai_herramientas_catalogo.py
git commit -m "$(cat <<'EOF'
feat(ai): herramientas de lectura del catálogo y despachador acotado a la org

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 5: `proponer_cambio` — validación en seco y propuesta pendiente

**Files:**
- Create: `app/modules/ai/herramientas_propuestas.py`
- Modify: `app/modules/ai/herramientas.py` (import y `REGISTRO`)
- Test: `tests/test_ai_propuestas.py`

**Interfaces:**
- Consumes: `Contexto`, `ErrorHerramienta`, `Herramienta`, `sucursal_de_la_org`, `ve_toda_la_org` (Tarea 4); `AiPropuesta`, `TIPOS_PROPUESTA`, `DatosAgregarVariantes`, `DatosAjustarExistencias` (Tarea 1); de `app.modules.products.services`: `validar_sku_unico`, `validar_precio(precio, detalle=…)`, `validar_departamento_y_marca`, `validar_sucursales_de_la_org`, `sucursales_que_venden`, `atributos(color, size, contexto)`, `atributos_principal(color, size)`, `pareja_repetida(producto, color, size)`, `sku_generado(base, color, size)`, `variante_principal(producto)`; `ProductCreate` (`app/modules/products/schemas.py`); `variant_label` (`app/modules/products/variant_label.py`).
- Produces:
  - Herramienta `proponer_cambio(tipo, datos)` registrada en `REGISTRO`; salida `{"propuesta_id", "resumen", "avisos": [str], "nota"}` o `{"error": "..."}`.
  - `AiPropuesta.datos` normalizado: `crear_producto` = `ProductCreate.model_dump(mode="json")` con `branch_id` y `target_branch_ids` resueltos (Decimal como cadena, p. ej. `"1200"`); `agregar_variantes` = `DatosAgregarVariantes` con `sucursal_id` resuelto (`variantes[].size`, `precio`, `existencia`); `ajustar_existencias` = `DatosAjustarExistencias`.
  - Resúmenes: `"Alta: [Marca · ]Nombre · SKU X · $1,200.00 (costo $600.00) · N variante(s) · P pieza(s)"`, `"Agregar N variante(s) a Nombre (SKU X) · P pieza(s)"`, `"Ajustar existencias de N variante(s): SKU en Sucursal: antes → después; …"`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_ai_propuestas.py`:

```python
"""`proponer_cambio`: valida en seco con las reglas de SP1 y deja una
propuesta PENDIENTE; nunca crea productos ni mueve existencias."""
from decimal import Decimal

from conftest import _make_product
from app.models import Brand, Department, Product, StockOnHand
from app.models.organization import Branch, BranchType, Organization
from app.modules.ai.contexto import Contexto
from app.modules.ai.herramientas import definiciones, ejecutar
from app.modules.ai.models import AiConversation, AiPropuesta


def _ctx(db, org, user):
    conv = AiConversation(organization_id=org.id, user_id=user.id)
    db.add(conv)
    db.flush()
    return Contexto(db=db, org_id=org.id, user=user, conversacion=conv)


def _otra_org(db):
    otra = Organization(name="Otra", status="ACTIVE")
    db.add(otra)
    db.flush()
    ajena = Branch(name="Ajena", branch_type=BranchType.STORE, can_sell=True, is_active=True, organization_id=otra.id)
    db.add(ajena)
    db.flush()
    return otra, ajena


def _alta(branch_id, **cambios):
    datos = {
        "name": "Playera cuello redondo", "sku": "VER-PLAY-CR-NEG-CH", "price": 1200, "cost": 600,
        "color": "Negro", "size": "Ch", "initial_stock": 0, "branch_id": branch_id,
        "extra_variants": [
            {"color": "Negro", "size": "M", "sku": "VER-PLAY-CR-NEG-M", "initial_stock": 3},
            {"color": "Negro", "size": "G", "sku": "VER-PLAY-CR-NEG-G"},
        ],
    }
    datos.update(cambios)
    return {"tipo": "crear_producto", "datos": datos}


def _propuestas(db, org):
    return db.query(AiPropuesta).filter(AiPropuesta.organization_id == org.id).all()


def test_proponer_cambio_esta_registrada():
    assert "proponer_cambio" in {d["function"]["name"] for d in definiciones()}


def test_datos_declara_propiedades_explicitas():
    # La capa compatible de Gemini rechaza un OBJECT sin `properties`.
    d = next(x for x in definiciones() if x["function"]["name"] == "proponer_cambio")
    datos = d["function"]["parameters"]["properties"]["datos"]
    assert {"name", "sku", "price", "cost", "extra_variants", "product_id", "variantes", "ajustes"} <= set(datos["properties"])
    assert datos["properties"]["ajustes"]["items"]["required"] == ["variant_id", "sucursal_id", "existencia_nueva"]


def test_tipo_invalido(db, org, admin_user):
    r = ejecutar("proponer_cambio", {"tipo": "borrar_producto", "datos": {}}, _ctx(db, org, admin_user))
    assert r == {"error": "tipo debe ser uno de: crear_producto, agregar_variantes, ajustar_existencias"}


class TestAlta:
    def test_valida_y_deja_pendiente_sin_crear_nada(self, db, org, admin_user, branch_a):
        marca = Brand(name="Versace", organization_id=org.id)
        db.add(marca)
        db.flush()
        r = ejecutar("proponer_cambio", _alta(branch_a.id, brand_id=marca.id), _ctx(db, org, admin_user))
        assert "error" not in r, r
        p = db.query(AiPropuesta).filter(AiPropuesta.id == r["propuesta_id"]).one()
        assert (p.estado, p.tipo) == ("pendiente", "crear_producto")
        assert p.datos["target_branch_ids"] == [branch_a.id]
        assert p.resumen == (
            "Alta: Versace · Playera cuello redondo · SKU VER-PLAY-CR-NEG-CH · $1,200.00 (costo $600.00)"
            " · 3 variante(s) · 3 pieza(s)"
        )
        assert r["resumen"] == p.resumen
        assert r["avisos"] == ["Sin departamento."]
        assert db.query(Product).filter(Product.organization_id == org.id).count() == 0

    def test_falta_precio_o_costo_no_se_inventa(self, db, org, admin_user, branch_a):
        ctx = _ctx(db, org, admin_user)
        sin_precio = _alta(branch_a.id)
        del sin_precio["datos"]["price"]
        assert ejecutar("proponer_cambio", sin_precio, ctx) == {
            "error": "Falta precio: pregunta al usuario; nunca lo inventes."}
        sin_nada = _alta(branch_a.id)
        del sin_nada["datos"]["price"], sin_nada["datos"]["cost"]
        assert ejecutar("proponer_cambio", sin_nada, ctx) == {
            "error": "Falta precio y costo: pregunta al usuario; nunca lo inventes."}
        assert _propuestas(db, org) == []

    def test_costo_cero_se_acepta_con_aviso(self, db, org, admin_user, branch_a):
        r = ejecutar("proponer_cambio", _alta(branch_a.id, cost=0), _ctx(db, org, admin_user))
        assert "Costo en $0: confírmalo antes de guardar." in r["avisos"]

    def test_departamento_de_otra_org_no_crea_propuesta(self, db, org, admin_user, branch_a):
        # Review Focus #1: el modelo inventa (o arrastra) un id que no es de la org.
        otra, _ = _otra_org(db)
        ajeno = Department(name="Playeras", organization_id=otra.id)
        db.add(ajeno)
        db.flush()
        ctx = _ctx(db, org, admin_user)
        esperado = {"error": "Departamento no encontrado en tu organización."}
        assert ejecutar("proponer_cambio", _alta(branch_a.id, department_id=ajeno.id), ctx) == esperado
        inventado = _alta(branch_a.id, department_id="00000000-0000-0000-0000-000000000000")
        assert ejecutar("proponer_cambio", inventado, ctx) == esperado
        assert _propuestas(db, org) == []

    def test_sku_tomado_o_repetido_en_la_propuesta(self, db, org, admin_user, branch_a):
        ctx = _ctx(db, org, admin_user)
        _make_product(db, org, "Vieja", "VER-PLAY-CR-NEG-M", 100, [(branch_a.id, True)])
        assert ejecutar("proponer_cambio", _alta(branch_a.id), ctx) == {
            "error": "El SKU 'VER-PLAY-CR-NEG-M' ya existe en esta organización."}
        repetida = _alta(branch_a.id, extra_variants=[{"color": "Negro", "size": "XL", "sku": "VER-PLAY-CR-NEG-CH"}])
        assert ejecutar("proponer_cambio", repetida, ctx) == {
            "error": "El SKU VER-PLAY-CR-NEG-CH está repetido dentro de la propuesta."}

    def test_cajero_solo_su_sucursal(self, db, org, cajero_a, branch_a, branch_b):
        r = ejecutar("proponer_cambio", _alta(branch_b.id), _ctx(db, org, cajero_a))
        assert r == {"error": "Solo puedes proponer altas para tu sucursal."}

    def test_cajero_sin_sucursal_explicita_usa_la_suya(self, db, org, cajero_a, branch_a, branch_b):
        r = ejecutar("proponer_cambio", _alta(None), _ctx(db, org, cajero_a))
        p = db.query(AiPropuesta).filter(AiPropuesta.id == r["propuesta_id"]).one()
        assert p.datos["branch_id"] == branch_a.id and p.datos["target_branch_ids"] == [branch_a.id]

    def test_admin_con_varias_sucursales_debe_decir_cual(self, db, org, admin_user, branch_a, branch_b):
        r = ejecutar("proponer_cambio", _alta(None), _ctx(db, org, admin_user))
        assert r == {"error": "Indica en qué sucursal (branch_id) entra la existencia: hay varias que venden."}


class TestVariantes:
    def test_producto_de_otra_org_no_existe(self, db, org, admin_user):
        otra, _ = _otra_org(db)
        p, _ = _make_product(db, otra, "Ajeno", "AJ-1", 10)
        r = ejecutar("proponer_cambio", {"tipo": "agregar_variantes",
                                         "datos": {"product_id": p.id, "variantes": [{"size": "M"}]}},
                     _ctx(db, org, admin_user))
        assert r == {"error": f"El producto {p.id} no existe."}

    def test_pareja_que_ya_existe(self, db, org, admin_user, branch_a):
        p, v = _make_product(db, org, "Tenis", "NK-TENIS-40", 4000, [(branch_a.id, True)])
        v.size = "40"
        db.flush()
        r = ejecutar("proponer_cambio", {"tipo": "agregar_variantes",
                                         "datos": {"product_id": p.id, "variantes": [{"talla": "40"}]}},
                     _ctx(db, org, admin_user))
        assert r == {"error": "Ya existe la variante 40"}

    def test_valida_y_resume(self, db, org, admin_user, branch_a):
        p, v = _make_product(db, org, "Tenis", "NK-TENIS-40", 4000, [(branch_a.id, True)])
        v.size = "40"
        db.flush()
        r = ejecutar("proponer_cambio", {"tipo": "agregar_variantes", "datos": {
            "product_id": p.id, "sucursal_id": branch_a.id,
            "variantes": [{"talla": "41", "sku": "NK-TENIS-41", "existencia": 2}],
        }}, _ctx(db, org, admin_user))
        prop = db.query(AiPropuesta).filter(AiPropuesta.id == r["propuesta_id"]).one()
        assert prop.resumen == "Agregar 1 variante(s) a Tenis (SKU NK-TENIS-40) · 2 pieza(s)"
        assert prop.datos["variantes"][0]["size"] == "41"
        assert prop.datos["sucursal_id"] == branch_a.id


class TestAjustes:
    def test_resumen_con_antes_y_despues(self, db, org, admin_user, branch_a):
        _, v = _make_product(db, org, "Tenis", "NK-TENIS-40", 4000, [(branch_a.id, True)])
        r = ejecutar("proponer_cambio", {"tipo": "ajustar_existencias", "datos": {"ajustes": [
            {"variant_id": v.id, "sucursal_id": branch_a.id, "existencia_nueva": 7},
        ]}}, _ctx(db, org, admin_user))
        prop = db.query(AiPropuesta).filter(AiPropuesta.id == r["propuesta_id"]).one()
        assert prop.resumen == "Ajustar existencias de 1 variante(s): NK-TENIS-40 en Sucursal A: 100 → 7"
        # Proponer no mueve nada.
        assert db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).one().qty_on_hand == Decimal("100")

    def test_variante_o_sucursal_ajena(self, db, org, admin_user, branch_a):
        otra, ajena = _otra_org(db)
        _, v_ajena = _make_product(db, otra, "Ajeno", "AJ-1", 10)
        _, v = _make_product(db, org, "Tenis", "NK-TENIS-40", 4000, [(branch_a.id, True)])
        ctx = _ctx(db, org, admin_user)
        r1 = ejecutar("proponer_cambio", {"tipo": "ajustar_existencias", "datos": {"ajustes": [
            {"variant_id": v_ajena.id, "sucursal_id": branch_a.id, "existencia_nueva": 1}]}}, ctx)
        assert r1 == {"error": f"La variante {v_ajena.id} no existe."}
        r2 = ejecutar("proponer_cambio", {"tipo": "ajustar_existencias", "datos": {"ajustes": [
            {"variant_id": v.id, "sucursal_id": ajena.id, "existencia_nueva": 1}]}}, ctx)
        assert r2 == {"error": f"La sucursal {ajena.id} no existe."}

    def test_cajero_otra_sucursal(self, db, org, cajero_a, branch_a, branch_b, products_setup):
        _, vb = products_setup["product_both"]
        r = ejecutar("proponer_cambio", {"tipo": "ajustar_existencias", "datos": {"ajustes": [
            {"variant_id": vb.id, "sucursal_id": branch_b.id, "existencia_nueva": 1}]}}, _ctx(db, org, cajero_a))
        assert r == {"error": "Solo puedes ajustar existencias de tu sucursal."}
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_ai_propuestas.py`
Expected: FAIL — `test_proponer_cambio_esta_registrada` con `AssertionError` y las demás con `{"error": "Herramienta desconocida: proponer_cambio"}`.

- [ ] **Step 3: Crear `app/modules/ai/herramientas_propuestas.py`**

```python
"""`proponer_cambio`: la ÚNICA herramienta que escribe, y solo una fila de
`ai_propuestas` en estado `pendiente`.

Valida en seco con las mismas reglas de SP1 (SKU único sin mayúsculas e
incluyendo archivados, precio > 0, departamento/marca/sucursal de la org,
combinación color/talla repetida) para que el modelo corrija ANTES de que la
persona vea la tarjeta. Productos, variantes y existencias solo se tocan en
`ejecutores.aplicar`, desde `POST …/confirmar`. El resumen lo arma el
servidor, nunca el modelo.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.models import Brand, Product, ProductBranchStatus, ProductVariant, StockOnHand
from app.modules.products.schemas import ProductCreate
from app.modules.products.services import (
    atributos, atributos_principal, pareja_repetida, sku_generado, sucursales_que_venden,
    validar_departamento_y_marca, validar_precio, validar_sku_unico, validar_sucursales_de_la_org,
    variante_principal,
)
from app.modules.products.variant_label import variant_label

from .contexto import Contexto, ErrorHerramienta, Herramienta, sucursal_de_la_org, ve_toda_la_org
from .models import TIPOS_PROPUESTA, AiPropuesta
from .schemas import DatosAgregarVariantes, DatosAjustarExistencias

_NOMBRE_DINERO = {"price": "precio", "cost": "costo"}


def _dinero(valor: Any) -> str:
    return f"${Decimal(str(valor)):,.2f}"


def _num(valor: Any) -> str:
    d = Decimal(str(valor or 0))
    return str(int(d)) if d == d.to_integral_value() else str(d.normalize())


def _normalizar_alta(ctx: Contexto, datos: ProductCreate) -> ProductCreate:
    """La existencia entra en `branch_id`: si no viene, la del usuario (no
    admin) o la única sucursal que vende. Y el producto se habilita ahí: sin
    `target_branch_ids`, un admin asignado a la matriz (que no vende) dejaría
    la existencia en la matriz (`sucursal_de_existencia_inicial` de SP1)."""
    branch_id = datos.branch_id
    if branch_id is None:
        if not ve_toda_la_org(ctx.user) and ctx.user.branch_id:
            branch_id = ctx.user.branch_id
        else:
            venden = sucursales_que_venden(ctx.db, ctx.org_id)
            if len(venden) == 1:
                branch_id = venden[0]
    destinos = datos.target_branch_ids or ([branch_id] if branch_id else None)
    return datos.model_copy(update={"branch_id": branch_id, "target_branch_ids": destinos})


def _validar_alta(ctx: Contexto, crudo: dict) -> tuple[dict, list[str], str]:
    faltan = [_NOMBRE_DINERO[c] for c in ("price", "cost") if crudo.get(c) in (None, "")]
    if faltan:
        raise ErrorHerramienta(f"Falta {' y '.join(faltan)}: pregunta al usuario; nunca lo inventes.")
    datos = _normalizar_alta(ctx, ProductCreate(**crudo))
    db, org_id, user = ctx.db, ctx.org_id, ctx.user

    validar_precio(datos.price)
    if datos.cost < 0:
        raise ErrorHerramienta("El costo no puede ser negativo.")
    validar_departamento_y_marca(db, org_id, datos.department_id, datos.brand_id)
    sucursales = [b for b in [datos.branch_id, *(datos.target_branch_ids or [])] if b]
    validar_sucursales_de_la_org(db, org_id, sucursales)
    if not ve_toda_la_org(user) and any(b != user.branch_id for b in sucursales):
        raise ErrorHerramienta("Solo puedes proponer altas para tu sucursal.")
    if (datos.initial_stock or 0) < 0:
        raise ErrorHerramienta("La existencia no puede ser negativa.")
    piezas = (datos.initial_stock or Decimal(0)) + sum(
        (v.initial_stock or Decimal(0)) for v in datos.extra_variants
    )
    if piezas > 0 and not datos.branch_id:
        raise ErrorHerramienta("Indica en qué sucursal (branch_id) entra la existencia: hay varias que venden.")

    sku = validar_sku_unico(db, org_id, datos.sku)
    color, size = atributos_principal(datos.color, datos.size)
    skus = {sku.lower()}
    pares = {((color or "").lower(), (size or "").lower())}
    for i, v in enumerate(datos.extra_variants):
        c, s = atributos(v.color, v.size, f"extra_variants[{i}]")
        if not c and not s:
            raise ErrorHerramienta(f"extra_variants[{i}]: indica color o talla.")
        par = ((c or "").lower(), (s or "").lower())
        if par in pares:
            raise ErrorHerramienta(f"La combinación {variant_label(c, s)} está repetida en la propuesta.")
        pares.add(par)
        if v.price is not None:
            validar_precio(v.price, f"extra_variants[{i}]: el precio debe ser mayor a cero.")
        if (v.initial_stock or 0) < 0:
            raise ErrorHerramienta(f"extra_variants[{i}]: la existencia no puede ser negativa.")
        sku_v = (v.sku or "").strip() or sku_generado(sku, c, s)
        if sku_v.lower() in skus:
            raise ErrorHerramienta(f"El SKU {sku_v} está repetido dentro de la propuesta.")
        validar_sku_unico(db, org_id, sku_v)
        skus.add(sku_v.lower())

    avisos = []
    if datos.cost == 0:
        avisos.append("Costo en $0: confírmalo antes de guardar.")
    if not datos.department_id:
        avisos.append("Sin departamento.")
    if not datos.brand_id:
        avisos.append("Sin marca.")
    marca = None
    if datos.brand_id:
        marca = db.query(Brand.name).filter(Brand.id == datos.brand_id, Brand.organization_id == org_id).scalar()
    prenda = f"{marca} · {datos.name}" if marca else datos.name
    resumen = (
        f"Alta: {prenda} · SKU {sku} · {_dinero(datos.price)} (costo {_dinero(datos.cost)})"
        f" · {1 + len(datos.extra_variants)} variante(s) · {_num(piezas)} pieza(s)"
    )
    return datos.model_copy(update={"sku": sku}).model_dump(mode="json"), avisos, resumen


def _validar_variantes(ctx: Contexto, crudo: dict) -> tuple[dict, list[str], str]:
    datos = DatosAgregarVariantes(**crudo)
    db, org_id, user = ctx.db, ctx.org_id, ctx.user
    producto = db.query(Product).filter(
        Product.id == datos.product_id, Product.organization_id == org_id, Product.deleted_at.is_(None),
    ).first()
    if producto is None:
        raise ErrorHerramienta(f"El producto {datos.product_id} no existe.")
    principal = variante_principal(producto)
    if principal is None:
        raise ErrorHerramienta("El producto no tiene variantes vivas; propón un alta nueva.")

    sucursal = datos.sucursal_id
    if sucursal is None and not ve_toda_la_org(user):
        sucursal = user.branch_id
    if sucursal is not None:
        sucursal_de_la_org(ctx, sucursal)
        if not ve_toda_la_org(user) and sucursal != user.branch_id:
            raise ErrorHerramienta("Solo puedes agregar variantes en tu sucursal.")
    piezas = sum((v.existencia for v in datos.variantes), Decimal(0))
    if piezas > 0 and sucursal is None:
        habilitadas = db.query(ProductBranchStatus.branch_id).filter(
            ProductBranchStatus.variant_id == principal.id,
        ).count()
        if habilitadas != 1:
            raise ErrorHerramienta("Indica en qué sucursal (sucursal_id) entra la existencia.")

    skus: set[str] = set()
    pares: set[tuple[str, str]] = set()
    for i, v in enumerate(datos.variantes):
        c, s = atributos(v.color, v.size, f"variantes[{i}]")
        if not c and not s:
            raise ErrorHerramienta(f"variantes[{i}]: indica color o talla.")
        par = ((c or "").lower(), (s or "").lower())
        if par in pares or pareja_repetida(producto, c, s):
            raise ErrorHerramienta(f"Ya existe la variante {variant_label(c, s)}")
        pares.add(par)
        if v.precio is not None:
            validar_precio(v.precio, f"variantes[{i}]: el precio debe ser mayor a cero.")
        sku_v = (v.sku or "").strip() or sku_generado(principal.sku, c, s)
        if sku_v.lower() in skus:
            raise ErrorHerramienta(f"El SKU {sku_v} está repetido dentro de la propuesta.")
        validar_sku_unico(db, org_id, sku_v)
        skus.add(sku_v.lower())

    resumen = (f"Agregar {len(datos.variantes)} variante(s) a {producto.name} (SKU {principal.sku})"
               f" · {_num(piezas)} pieza(s)")
    return datos.model_copy(update={"sucursal_id": sucursal}).model_dump(mode="json"), [], resumen


def _validar_ajustes(ctx: Contexto, crudo: dict) -> tuple[dict, list[str], str]:
    datos = DatosAjustarExistencias(**crudo)
    db, org_id, user = ctx.db, ctx.org_id, ctx.user
    lineas = []
    for a in datos.ajustes:
        variante = (
            db.query(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .filter(
                ProductVariant.id == a.variant_id, Product.organization_id == org_id,
                ProductVariant.deleted_at.is_(None), Product.deleted_at.is_(None),
            ).first()
        )
        if variante is None:
            raise ErrorHerramienta(f"La variante {a.variant_id} no existe.")
        sucursal = sucursal_de_la_org(ctx, a.sucursal_id)
        if not ve_toda_la_org(user) and sucursal.id != user.branch_id:
            raise ErrorHerramienta("Solo puedes ajustar existencias de tu sucursal.")
        actual = db.query(StockOnHand.qty_on_hand).filter(
            StockOnHand.variant_id == variante.id, StockOnHand.branch_id == sucursal.id,
        ).scalar() or 0
        lineas.append(f"{variante.sku} en {sucursal.name}: {_num(actual)} → {_num(a.existencia_nueva)}")
    resumen = f"Ajustar existencias de {len(datos.ajustes)} variante(s): " + "; ".join(lineas[:5])
    if len(lineas) > 5:
        resumen += f"; y {len(lineas) - 5} más"
    return datos.model_dump(mode="json"), [], resumen


_VALIDADORES = {
    "crear_producto": _validar_alta,
    "agregar_variantes": _validar_variantes,
    "ajustar_existencias": _validar_ajustes,
}


def proponer_cambio(ctx: Contexto, args: dict) -> dict:
    tipo = args.get("tipo")
    if tipo not in TIPOS_PROPUESTA:
        raise ErrorHerramienta(f"tipo debe ser uno de: {', '.join(TIPOS_PROPUESTA)}")
    crudo = args.get("datos")
    if not isinstance(crudo, dict):
        raise ErrorHerramienta("datos debe ser un objeto JSON.")
    guardado, avisos, resumen = _VALIDADORES[tipo](ctx, crudo)
    propuesta = AiPropuesta(
        organization_id=ctx.org_id,
        conversation_id=ctx.conversacion.id,
        tipo=tipo,
        datos=guardado,
        avisos=avisos,
        estado="pendiente",
        resumen=resumen[:300],
    )
    ctx.db.add(propuesta)
    ctx.db.flush()
    return {
        "propuesta_id": propuesta.id,
        "resumen": propuesta.resumen,
        "avisos": avisos,
        "nota": "Propuesta pendiente: la persona la confirma en pantalla. No digas que ya se guardó.",
    }


_STR = {"type": "string"}
_NUM = {"type": "number"}
_INT = {"type": "integer"}
PROPIEDADES_DATOS: dict = {
    # crear_producto
    "name": _STR, "sku": _STR, "price": _NUM, "cost": _NUM, "department_id": _STR, "brand_id": _STR,
    "gender": {"type": "string", "enum": ["HOMBRE", "MUJER", "UNISEX", "NINO"]},
    "model": _STR, "material": _STR, "description": _STR, "has_iva": {"type": "boolean"},
    "color": _STR, "size": _STR, "initial_stock": _NUM, "branch_id": _INT,
    "extra_variants": {"type": "array", "items": {"type": "object", "properties": {
        "color": _STR, "size": _STR, "sku": _STR, "price": _NUM, "initial_stock": _NUM}}},
    # agregar_variantes
    "product_id": _STR, "sucursal_id": _INT,
    "variantes": {"type": "array", "items": {"type": "object", "properties": {
        "color": _STR, "size": _STR, "sku": _STR, "precio": _NUM, "existencia": _NUM}}},
    # ajustar_existencias
    "ajustes": {"type": "array", "items": {"type": "object", "properties": {
        "variant_id": _STR, "sucursal_id": _INT, "existencia_nueva": _NUM},
        "required": ["variant_id", "sucursal_id", "existencia_nueva"]}},
}

HERRAMIENTAS: dict[str, Herramienta] = {
    "proponer_cambio": Herramienta(
        "Deja una PROPUESTA pendiente (no guarda nada): alta de producto, variantes nuevas o ajuste de "
        "existencias. La persona la confirma en pantalla. Ver el contrato de `datos` en el mensaje del sistema.",
        {"type": "object", "properties": {
            "tipo": {"type": "string", "enum": list(TIPOS_PROPUESTA)},
            # Propiedades EXPLÍCITAS (superconjunto de los tres tipos): la capa
            # compatible de Gemini rechaza un OBJECT sin `properties`. Todo es
            # opcional aquí; lo obligatorio por tipo lo exige el schema Pydantic.
            "datos": {"type": "object", "description": "Datos según el tipo (ver mensaje del sistema).",
                      "properties": PROPIEDADES_DATOS},
        }, "required": ["tipo", "datos"]},
        proponer_cambio,
    ),
}
```

- [ ] **Step 4: Registrar la herramienta en `app/modules/ai/herramientas.py`**

Reemplazar:

```python
from .herramientas_catalogo import HERRAMIENTAS as _CATALOGO

logger = logging.getLogger(__name__)

REGISTRO: dict[str, Herramienta] = {**_CATALOGO}
```

por:

```python
from .herramientas_catalogo import HERRAMIENTAS as _CATALOGO
from .herramientas_propuestas import HERRAMIENTAS as _PROPUESTAS

logger = logging.getLogger(__name__)

REGISTRO: dict[str, Herramienta] = {**_CATALOGO, **_PROPUESTAS}
```

- [ ] **Step 5: Correr las pruebas**

Run: `python3 -m pytest -q -p no:warnings tests/test_ai_propuestas.py tests/test_ai_herramientas_catalogo.py`
Expected: PASS (16 + 11).

- [ ] **Step 6: Commit**

```bash
git add app/modules/ai/herramientas_propuestas.py app/modules/ai/herramientas.py tests/test_ai_propuestas.py
git commit -m "$(cat <<'EOF'
feat(ai): proponer_cambio valida en seco con SP1 y deja la propuesta pendiente

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 6: `ejecutores.aplicar` — la propuesta confirmada pasa por SP1

**Files:**
- Create: `app/modules/ai/gating.py` (solo `modulo_encendido`; la Tarea 7 agrega el gate HTTP)
- Create: `app/modules/ai/ejecutores.py`
- Test: `tests/test_ai_ejecutores.py`

**Interfaces:**
- Consumes: `AiConversation`, `AiPropuesta`, `DatosAgregarVariantes`, `DatosAjustarExistencias`, `guardar_mensaje` (Tarea 1); de `app.modules.products.services`: `crear_producto(db, org_id, user, datos: ProductCreate) -> Product`, `crear_variantes(db, org_id, producto, entradas: list[ProductVariantCreate], principal_id=None, stock_branch_id=None, user_id=None) -> list[ProductVariant]`, `fijar_existencia(db, org_id, variante, branch_id, objetivo: Decimal, user_id, *, referencia, notas)`, `validar_sucursales_de_la_org`, `variante_principal`, `PRODUCT_ADVANCED_ROLES`; `PlatformAuditLog`.
- Produces (Tarea 7):
  - `modulo_encendido(db, org_id: int, clave: str) -> bool`.
  - `aplicar(db, propuesta: AiPropuesta, user: User) -> dict` — sin commit; levanta `HTTPException` (403 permiso, 409/422 de SP1); deja `estado="confirmada"`, `resultado`, `confirmada_por`, `confirmada_at`, auditoría `AI_PROPUESTA_APLICADA` (y `PRODUCT_CREATE_AI` por alta) y un mensaje `evento`.
  - Formas de `resultado`: `crear_producto → {"producto_id", "sku", "variantes": [{"id","sku","color","talla"}]}`; `agregar_variantes → {"producto_id", "variantes": [...]}`; `ajustar_existencias → {"ajustes": [{"variant_id","sku","sucursal_id","existencia"}]}`.
  - `REFERENCIA_KARDEX = "Asistente IA"`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_ai_ejecutores.py`:

```python
"""`ejecutores.aplicar`: lo único del asistente que crea productos, variantes y
existencias, y solo con una propuesta que una persona confirmó."""
import json
from decimal import Decimal

import pytest
from fastapi import HTTPException

from conftest import _make_product
from app.models import InventoryMovement, Product, StockOnHand
from app.models.platform import PlatformAuditLog
from app.modules.ai.ejecutores import aplicar
from app.modules.ai.models import AiConversation, AiMessage, AiPropuesta
from app.modules.ai.schemas import AjusteExistencia, DatosAgregarVariantes, DatosAjustarExistencias, VarianteNueva
from app.modules.products.schemas import ProductCreate, ProductVariantCreate


def _conv(db, org, user):
    c = AiConversation(organization_id=org.id, user_id=user.id, titulo="Prueba")
    db.add(c)
    db.flush()
    return c


def _propuesta(db, conv, tipo, datos):
    p = AiPropuesta(organization_id=conv.organization_id, conversation_id=conv.id, tipo=tipo,
                    datos=datos, avisos=[], estado="pendiente", resumen=f"Prueba {tipo}")
    db.add(p)
    db.flush()
    return p


def _alta(branch_id):
    return ProductCreate(
        name="Playera cuello redondo", sku="VER-PLAY-NEG-CH", price=Decimal("1200"), cost=Decimal("600"),
        color="Negro", size="Ch", initial_stock=Decimal(0), branch_id=branch_id, target_branch_ids=[branch_id],
        extra_variants=[
            ProductVariantCreate(color="Negro", size="M", sku="VER-PLAY-NEG-M", initial_stock=Decimal(3)),
            ProductVariantCreate(color="Negro", size="G", sku="VER-PLAY-NEG-G"),
        ],
    ).model_dump(mode="json")


def _ajuste(variant_id, branch_id, n):
    return DatosAjustarExistencias(ajustes=[
        AjusteExistencia(variant_id=variant_id, sucursal_id=branch_id, existencia_nueva=Decimal(n)),
    ]).model_dump(mode="json")


def _existencia(db, variant_id, branch_id):
    return db.query(StockOnHand.qty_on_hand).filter(
        StockOnHand.variant_id == variant_id, StockOnHand.branch_id == branch_id,
    ).scalar()


class TestAlta:
    def test_crea_producto_variantes_existencia_y_auditoria(self, db, org, admin_user, branch_a):
        conv = _conv(db, org, admin_user)
        prop = _propuesta(db, conv, "crear_producto", _alta(branch_a.id))

        res = aplicar(db, prop, admin_user)

        producto = db.query(Product).filter(Product.id == res["producto_id"], Product.organization_id == org.id).one()
        tallas = {v.size: v for v in producto.variants}
        assert set(tallas) == {"Ch", "M", "G"}
        assert _existencia(db, tallas["M"].id, branch_a.id) == Decimal("3")
        assert _existencia(db, tallas["Ch"].id, branch_a.id) == Decimal("0")
        assert res["sku"] == "VER-PLAY-NEG-CH"
        assert {v["talla"] for v in res["variantes"]} == {"Ch", "M", "G"}
        assert (prop.estado, prop.resultado) == ("confirmada", res)
        assert prop.confirmada_por == admin_user.id and prop.confirmada_at is not None
        alta = db.query(PlatformAuditLog).filter(
            PlatformAuditLog.action == "PRODUCT_CREATE_AI", PlatformAuditLog.entity_id == producto.id,
        ).one()
        assert json.loads(alta.payload)["source"] == "ai"
        aplicada = db.query(PlatformAuditLog).filter(
            PlatformAuditLog.action == "AI_PROPUESTA_APLICADA", PlatformAuditLog.entity_id == prop.id,
        ).one()
        carga = json.loads(aplicada.payload)
        assert (carga["source"], carga["tipo"], carga["conversation_id"]) == ("ai", "crear_producto", conv.id)
        evento = db.query(AiMessage).filter(AiMessage.conversation_id == conv.id, AiMessage.rol == "evento").one()
        assert evento.contenido.startswith("Propuesta aplicada por admin_test")
        assert "VER-PLAY-NEG-M" in evento.contenido

    def test_cajero_sin_modulo_catalog_no_crea(self, db, org, cajero_a, branch_a):
        prop = _propuesta(db, _conv(db, org, cajero_a), "crear_producto", _alta(branch_a.id))
        with pytest.raises(HTTPException) as exc:
            aplicar(db, prop, cajero_a)
        assert exc.value.status_code == 403 and "catalog" in exc.value.detail
        assert db.query(Product).filter(Product.organization_id == org.id).count() == 0

    def test_cajero_con_catalog_crea_en_su_sucursal(self, db, org, cajero_a, branch_a, catalog_module_enabled):
        prop = _propuesta(db, _conv(db, org, cajero_a), "crear_producto", _alta(branch_a.id))
        res = aplicar(db, prop, cajero_a)
        assert db.query(Product).filter(Product.id == res["producto_id"]).count() == 1


class TestVariantes:
    def test_agrega_talla_con_existencia(self, db, org, admin_user, branch_a):
        p, v = _make_product(db, org, "Tenis", "NK-TENIS-40", 4000, [(branch_a.id, True)])
        v.size = "40"
        db.flush()
        datos = DatosAgregarVariantes(product_id=p.id, sucursal_id=branch_a.id, variantes=[
            VarianteNueva(size="41", sku="NK-TENIS-41", existencia=Decimal(2)),
        ]).model_dump(mode="json")
        res = aplicar(db, _propuesta(db, _conv(db, org, admin_user), "agregar_variantes", datos), admin_user)
        assert [x["sku"] for x in res["variantes"]] == ["NK-TENIS-41"]
        assert _existencia(db, res["variantes"][0]["id"], branch_a.id) == Decimal("2")


class TestAjustes:
    def test_fija_la_existencia_con_kardex(self, db, org, admin_user, branch_a):
        _, v = _make_product(db, org, "Tenis", "NK-TENIS-40", 4000, [(branch_a.id, True)])
        prop = _propuesta(db, _conv(db, org, admin_user), "ajustar_existencias", _ajuste(v.id, branch_a.id, 7))
        res = aplicar(db, prop, admin_user)
        assert _existencia(db, v.id, branch_a.id) == Decimal("7")
        mov = db.query(InventoryMovement).filter(
            InventoryMovement.variant_id == v.id, InventoryMovement.reference == "Asistente IA",
        ).one()
        assert mov.qty_change == Decimal("93") and mov.notes == f"Propuesta {prop.id}"
        assert res == {"ajustes": [{"variant_id": v.id, "sku": "NK-TENIS-40", "sucursal_id": branch_a.id, "existencia": 7.0}]}

    def test_cajero_no_aplica_ajuste_en_otra_sucursal(self, db, org, cajero_a, branch_a, branch_b, products_setup):
        # Review Focus #4: la propuesta pudo armarse con otro usuario o datos viejos.
        _, vb = products_setup["product_both"]
        prop = _propuesta(db, _conv(db, org, cajero_a), "ajustar_existencias", _ajuste(vb.id, branch_b.id, 1))
        with pytest.raises(HTTPException) as exc:
            aplicar(db, prop, cajero_a)
        assert exc.value.status_code == 403
        assert exc.value.detail == "Solo puedes aplicar cambios en tu sucursal."
        assert _existencia(db, vb.id, branch_b.id) == Decimal("100")
        assert prop.estado == "pendiente"

    def test_rol_sin_permiso(self, db, org, vendedor_sin_sucursal, branch_a, products_setup):
        _, va = products_setup["product_a"]
        prop = _propuesta(db, _conv(db, org, vendedor_sin_sucursal), "ajustar_existencias", _ajuste(va.id, branch_a.id, 1))
        with pytest.raises(HTTPException) as exc:
            aplicar(db, prop, vendedor_sin_sucursal)
        assert (exc.value.status_code, exc.value.detail) == (403, "Tu rol no puede aplicar propuestas del asistente.")
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_ai_ejecutores.py`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.modules.ai.ejecutores'`.

- [ ] **Step 3: Crear `app/modules/ai/gating.py`**

```python
"""Módulos encendidos por organización y el gate del asistente (SP4)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.modules import OrganizationModule


def modulo_encendido(db: Session, org_id: int, clave: str) -> bool:
    """¿`organization_modules.<clave>` está encendido? Sin excepción por rol."""
    return db.query(OrganizationModule.module_key).filter(
        OrganizationModule.organization_id == org_id,
        OrganizationModule.module_key == clave,
        OrganizationModule.is_enabled == True,  # noqa: E712
    ).first() is not None
```

- [ ] **Step 4: Crear `app/modules/ai/ejecutores.py`**

```python
"""Aplicar una propuesta confirmada.

Es lo ÚNICO del asistente que crea productos, variantes o existencias, y lo
hace con el servicio de altas de SP1 (`crear_producto`, `crear_variantes`,
`fijar_existencia`) y con el usuario que confirmó: su rol y su sucursal. Sin
commit: el router confirma (y envuelve la llamada en un SAVEPOINT).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.crud.products import _is_admin
from app.models import Product, ProductVariant
from app.models.platform import PlatformAuditLog
from app.models.users import User
from app.modules.products.schemas import ProductCreate, ProductVariantCreate
from app.modules.products.services import (
    PRODUCT_ADVANCED_ROLES, crear_producto, crear_variantes, fijar_existencia,
    validar_sucursales_de_la_org, variante_principal,
)

from .gating import modulo_encendido
from .historial import guardar_mensaje
from .models import AiConversation, AiPropuesta
from .schemas import DatosAgregarVariantes, DatosAjustarExistencias

REFERENCIA_KARDEX = "Asistente IA"


def _sucursales_de(propuesta: AiPropuesta) -> set[int]:
    datos = propuesta.datos or {}
    if propuesta.tipo == "crear_producto":
        return {b for b in [datos.get("branch_id"), *(datos.get("target_branch_ids") or [])] if b}
    if propuesta.tipo == "agregar_variantes":
        return {datos["sucursal_id"]} if datos.get("sucursal_id") else set()
    return {a.get("sucursal_id") for a in (datos.get("ajustes") or []) if a.get("sucursal_id")}


def _exigir_permiso(db: Session, org_id: int, user: User, propuesta: AiPropuesta) -> None:
    """Mismas reglas que las pantallas: roles de catálogo; GERENTE/CAJERO con
    el módulo `catalog` para altas y variantes (como `POST /api/products/`) y
    solo en su sucursal."""
    if user.role not in PRODUCT_ADVANCED_ROLES:
        raise HTTPException(status_code=403, detail="Tu rol no puede aplicar propuestas del asistente.")
    if _is_admin(user):
        return
    if not user.branch_id:
        raise HTTPException(status_code=403, detail="Tu usuario no tiene sucursal asignada.")
    if propuesta.tipo in ("crear_producto", "agregar_variantes") and not modulo_encendido(db, org_id, "catalog"):
        raise HTTPException(status_code=403, detail="El módulo 'catalog' no está habilitado para esta organización.")
    if any(b != user.branch_id for b in _sucursales_de(propuesta)):
        raise HTTPException(status_code=403, detail="Solo puedes aplicar cambios en tu sucursal.")


def _variante(v: ProductVariant) -> dict:
    return {"id": v.id, "sku": v.sku, "color": v.color, "talla": v.size}


def _aplicar_alta(db: Session, org_id: int, user: User, propuesta: AiPropuesta) -> dict:
    datos = ProductCreate(**propuesta.datos)
    producto = crear_producto(db, org_id, user, datos)
    # Las hermanas se agregaron por product_id: la colección cargada está vieja.
    db.expire(producto, ["variants"])
    vivas = [v for v in producto.variants if v.deleted_at is None]
    principal = vivas[0]
    db.add(PlatformAuditLog(
        actor_user_id=user.id,
        action="PRODUCT_CREATE_AI",
        entity_type="Product",
        entity_id=str(producto.id),
        payload=json.dumps({
            "branch_id": datos.branch_id, "sku": principal.sku, "name": producto.name,
            "variant_id": str(principal.id), "source": "ai", "propuesta_id": propuesta.id,
        }),
    ))
    return {"producto_id": producto.id, "sku": principal.sku, "variantes": [_variante(v) for v in vivas]}


def _producto_de_la_org(db: Session, org_id: int, product_id: str) -> Product:
    producto = db.query(Product).filter(
        Product.id == product_id, Product.organization_id == org_id, Product.deleted_at.is_(None),
    ).first()
    if producto is None:
        raise HTTPException(status_code=409, detail="El producto de la propuesta ya no existe.")
    return producto


def _aplicar_variantes(db: Session, org_id: int, user: User, propuesta: AiPropuesta) -> dict:
    datos = DatosAgregarVariantes(**propuesta.datos)
    producto = _producto_de_la_org(db, org_id, datos.product_id)
    principal = variante_principal(producto)
    if principal is None:
        raise HTTPException(status_code=409, detail="El producto ya no tiene variantes vivas.")
    if datos.sucursal_id is not None:
        validar_sucursales_de_la_org(db, org_id, [datos.sucursal_id])
    entradas = [
        ProductVariantCreate(color=v.color, size=v.size, sku=v.sku, price=v.precio, initial_stock=v.existencia)
        for v in datos.variantes
    ]
    nuevas = crear_variantes(db, org_id, producto, entradas, principal_id=principal.id,
                             stock_branch_id=datos.sucursal_id, user_id=user.id)
    return {"producto_id": producto.id, "variantes": [_variante(v) for v in nuevas]}


def _aplicar_ajustes(db: Session, org_id: int, user: User, propuesta: AiPropuesta) -> dict:
    datos = DatosAjustarExistencias(**propuesta.datos)
    salida = []
    for a in datos.ajustes:
        variante = (
            db.query(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .filter(
                ProductVariant.id == a.variant_id, Product.organization_id == org_id,
                ProductVariant.deleted_at.is_(None), Product.deleted_at.is_(None),
            ).first()
        )
        if variante is None:
            raise HTTPException(status_code=409, detail=f"La variante {a.variant_id} ya no existe.")
        validar_sucursales_de_la_org(db, org_id, [a.sucursal_id])
        fijar_existencia(db, org_id, variante, a.sucursal_id, a.existencia_nueva, user.id,
                         referencia=REFERENCIA_KARDEX, notas=f"Propuesta {propuesta.id}")
        salida.append({"variant_id": variante.id, "sku": variante.sku, "sucursal_id": a.sucursal_id,
                       "existencia": float(a.existencia_nueva)})
    return {"ajustes": salida}


_APLICADORES = {
    "crear_producto": _aplicar_alta,
    "agregar_variantes": _aplicar_variantes,
    "ajustar_existencias": _aplicar_ajustes,
}


def aplicar(db: Session, propuesta: AiPropuesta, user: User) -> dict:
    org_id = propuesta.organization_id
    _exigir_permiso(db, org_id, user, propuesta)
    resultado = _APLICADORES[propuesta.tipo](db, org_id, user, propuesta)

    propuesta.estado = "confirmada"
    propuesta.resultado = resultado
    propuesta.confirmada_por = user.id
    propuesta.confirmada_at = datetime.now(timezone.utc)
    db.add(PlatformAuditLog(
        actor_user_id=user.id,
        action="AI_PROPUESTA_APLICADA",
        entity_type="AiPropuesta",
        entity_id=propuesta.id,
        payload=json.dumps({
            "propuesta_id": propuesta.id, "conversation_id": propuesta.conversation_id,
            "tipo": propuesta.tipo, "resultado": resultado, "source": "ai", "organization_id": org_id,
        }, default=str),
    ))
    # El modelo se entera en el siguiente turno (rol `evento` → aviso del sistema).
    conv = db.query(AiConversation).filter(
        AiConversation.id == propuesta.conversation_id, AiConversation.organization_id == org_id,
    ).one()
    skus = [v["sku"] for v in resultado.get("variantes", [])] + [a["sku"] for a in resultado.get("ajustes", [])]
    texto = f"Propuesta aplicada por {user.username}: {propuesta.resumen}"
    if skus:
        texto += f". SKU: {', '.join(skus)}"
    guardar_mensaje(db, conv, "evento", texto[:2000])
    db.flush()
    return resultado
```

- [ ] **Step 5: Correr las pruebas**

Run: `python3 -m pytest -q -p no:warnings tests/test_ai_ejecutores.py`
Expected: PASS (7 pruebas).

- [ ] **Step 6: Commit**

```bash
git add app/modules/ai/gating.py app/modules/ai/ejecutores.py tests/test_ai_ejecutores.py
git commit -m "$(cat <<'EOF'
feat(ai): aplicar propuestas confirmadas con el servicio de altas de SP1 y auditoría

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 7: Bucle `services.responder`, gate estricto y router `/api/ai`

**Files:**
- Create: `app/modules/ai/services.py`
- Modify: `app/modules/ai/gating.py` (reemplazo completo: agrega `mensaje_sin_modulo` y `exigir_modulo_ai`)
- Modify: `app/modules/ai/router.py` (reemplazo completo del stub; `app/main.py` ya lo monta en `/api/ai`, línea ~260)
- Test: `tests/test_ai_servicio.py`, `tests/test_ai_api.py`

**Interfaces:**
- Consumes: `ClienteLLM`, `ClienteFalso`, `RespuestaLLM`, `LlamadaHerramienta`, `ProveedorNoDisponible`, `cliente_por_defecto`, `configuracion`, `limite_tokens_dia` (Tarea 2); `armar_prompt` (Tarea 3); `Contexto`, `definiciones`, `ejecutar` (Tarea 4); `aplicar`, `modulo_encendido` (Tarea 6); modelos, schemas y `guardar_mensaje`, `historial_para_llm`, `mensajes_de` (Tarea 1); `plan_minimo_para` (`app/services/plans.py`).
- Produces:
  - `services.Turno(mensaje: AiMessage, propuestas_pendientes: list[AiPropuesta])`; `verificar_cuota(db, org_id) -> None` (429); `registrar_uso(db, org_id, r: RespuestaLLM) -> None`; `responder(db, conv: AiConversation, user: User, texto: str, cliente: ClienteLLM) -> Turno`; constantes `TOPE_HERRAMIENTAS = 8`, `TIEMPO_MAX_TURNO = 60.0`, `SIN_RESPUESTA`, `TOPE_ALCANZADO`, `CUOTA_AGOTADA`.
  - `gating.exigir_modulo_ai` (dependencia FastAPI, devuelve `org_id`), `gating.mensaje_sin_modulo() -> str`.
  - `router.obtener_cliente_llm()` — dependencia que la suite sustituye.
  - **Contrato HTTP (lo consume la Tarea 9 tal cual):**
    - `GET /api/ai/health` (solo auth) → `{"module": "ai", "status": "beta", "ready": bool}`
    - `GET /api/ai/conversaciones` → `[{"id": str, "titulo": str|null, "created_at": iso, "updated_at": iso}]` (las 20 más recientes del usuario)
    - `POST /api/ai/conversaciones` body `{"titulo"?: str}` → 201 `{"id","titulo","created_at","updated_at"}`
    - `GET /api/ai/conversaciones/{id}` → `{"id","titulo","created_at","updated_at","mensajes": [{"id","rol": "user"|"assistant"|"evento","contenido": str|null,"created_at"}], "propuestas": [Propuesta]}`
    - `POST /api/ai/conversaciones/{id}/mensajes` body `{"texto": str (1..4000)}` → `{"mensaje": Mensaje, "propuestas_pendientes": [Propuesta]}`
    - `POST /api/ai/conversaciones/{id}/propuestas/{pid}/confirmar` → `Propuesta`
    - `POST /api/ai/conversaciones/{id}/propuestas/{pid}/descartar` → `Propuesta`
    - `POST /api/ai/conversaciones/{id}/propuestas/{pid}/aplicada-manual` body `{"producto_id"?: str}` → `Propuesta`
    - `Propuesta` = `{"id","tipo": "crear_producto"|"agregar_variantes"|"ajustar_existencias","datos": object,"estado": "pendiente"|"confirmada"|"descartada"|"aplicada_manual"|"error","resumen": str,"avisos": [str],"resultado": object|null,"created_at"}`
    - Errores: 403 sin módulo (`detail` con el plan mínimo); 404 `"Conversación no encontrada."` / `"Propuesta no encontrada."`; 409 estado (`"La propuesta ya fue confirmada."`, `"La propuesta fue descartada."`, `"La propuesta ya se guardó desde el formulario."`, `"La propuesta no se pudo aplicar; ajústala en el formulario o descártala."`); 422 texto vacío o > 4000; 429 cuota; 503 proveedor (`NO_CONFIGURADO` o el texto de `ProveedorNoDisponible`).

- [ ] **Step 1: Escribir las pruebas del bucle (fallan)**

Crear `tests/test_ai_servicio.py`:

```python
"""Bucle del asistente con un cliente falso: nunca sale a la red."""
import json

import pytest
from fastapi import HTTPException

from app.core.fechas import hoy_negocio
from app.modules.ai.cliente_llm import ClienteFalso, LlamadaHerramienta, RespuestaLLM
from app.modules.ai.historial import guardar_mensaje
from app.modules.ai.models import AiConversation, AiMessage, AiUsoDiario
from app.modules.ai.services import SIN_RESPUESTA, TOPE_ALCANZADO, responder


def _conv(db, org, user):
    c = AiConversation(organization_id=org.id, user_id=user.id)
    db.add(c)
    db.flush()
    return c


def texto(t, entrada=10, salida=5):
    return RespuestaLLM(texto=t, tokens_entrada=entrada, tokens_salida=salida)


def pide(*llamadas):
    return RespuestaLLM(texto=None, tool_calls=list(llamadas), tokens_entrada=20, tokens_salida=8)


def llamada(nombre, args, id="c1"):
    return LlamadaHerramienta.desde_crudo(id, nombre, json.dumps(args))


def _roles(db, conv):
    return [m.rol for m in db.query(AiMessage).filter(AiMessage.conversation_id == conv.id).order_by(AiMessage.orden)]


class TestTurno:
    def test_herramienta_y_respuesta(self, db, org, admin_user):
        conv = _conv(db, org, admin_user)
        falso = ClienteFalso([pide(llamada("listar_marcas", {})), texto("No tienes marcas todavía.")])
        turno = responder(db, conv, admin_user, "¿qué marcas tengo?", falso)
        assert turno.mensaje.contenido == "No tienes marcas todavía."
        assert _roles(db, conv) == ["user", "assistant", "tool", "assistant"]
        segunda = falso.llamadas[1]["mensajes"]
        assert segunda[0]["role"] == "system"
        assert segunda[-1] == {"role": "tool", "tool_call_id": "c1", "content": '{"marcas": []}'}
        nombres = {h["function"]["name"] for h in falso.llamadas[0]["herramientas"]}
        assert {"buscar_producto", "proponer_cambio"} <= nombres
        assert conv.titulo == "¿qué marcas tengo?"

    def test_json_mal_formado_vuelve_al_modelo_y_el_turno_termina(self, db, org, admin_user):
        # Review Focus #2
        conv = _conv(db, org, admin_user)
        rota = LlamadaHerramienta.desde_crudo("c1", "buscar_producto", '{"q": "vers')
        turno = responder(db, conv, admin_user, "busca versace",
                          ClienteFalso([pide(rota), texto("Perdón, ¿qué buscabas?")]))
        assert turno.mensaje.contenido == "Perdón, ¿qué buscabas?"
        tool = db.query(AiMessage).filter(AiMessage.conversation_id == conv.id, AiMessage.rol == "tool").one()
        assert "JSON inválido" in json.loads(tool.contenido)["error"]

    def test_respuesta_vacia_da_mensaje_legible(self, db, org, admin_user):
        # Review Focus #5
        turno = responder(db, _conv(db, org, admin_user), admin_user, "hola", ClienteFalso([RespuestaLLM(texto="  ")]))
        assert turno.mensaje.contenido == SIN_RESPUESTA
        assert SIN_RESPUESTA == "No obtuve respuesta del asistente. Intenta de nuevo con otras palabras."

    def test_tope_de_ocho_herramientas(self, db, org, admin_user):
        conv = _conv(db, org, admin_user)
        guion = [pide(llamada("listar_marcas", {}, f"c{i}")) for i in range(8)] + [texto("Listo con lo que encontré.")]
        falso = ClienteFalso(guion)
        turno = responder(db, conv, admin_user, "dame todo", falso)
        assert turno.mensaje.contenido == "Listo con lo que encontré."
        assert _roles(db, conv).count("tool") == 8
        assert len(falso.llamadas) == 9 and falso.llamadas[-1]["herramientas"] == []

    def test_si_insiste_en_herramientas_se_detiene(self, db, org, admin_user):
        guion = [pide(llamada("listar_marcas", {}, f"c{i}")) for i in range(9)]
        turno = responder(db, _conv(db, org, admin_user), admin_user, "dame todo", ClienteFalso(guion))
        assert turno.mensaje.contenido == TOPE_ALCANZADO

    def test_historial_de_30_mas_el_sistema(self, db, org, admin_user):
        conv = _conv(db, org, admin_user)
        for i in range(40):
            guardar_mensaje(db, conv, "user", f"mensaje {i}")
        falso = ClienteFalso([texto("ok")])
        responder(db, conv, admin_user, "último", falso)
        enviados = falso.llamadas[0]["mensajes"]
        assert len(enviados) == 31 and enviados[0]["role"] == "system"
        assert enviados[-1] == {"role": "user", "content": "último"}

    def test_cuenta_tokens_del_dia(self, db, org, admin_user):
        falso = ClienteFalso([pide(llamada("listar_marcas", {})), texto("ok", entrada=100, salida=40)])
        responder(db, _conv(db, org, admin_user), admin_user, "marcas", falso)
        uso = db.query(AiUsoDiario).filter(
            AiUsoDiario.organization_id == org.id, AiUsoDiario.fecha == hoy_negocio(),
        ).one()
        assert (uso.tokens_entrada, uso.tokens_salida, uso.llamadas) == (120, 48, 2)

    def test_mensaje_vacio_o_largo_es_422(self, db, org, admin_user):
        conv = _conv(db, org, admin_user)
        for malo in ("   ", "x" * 4001):
            with pytest.raises(HTTPException) as exc:
                responder(db, conv, admin_user, malo, ClienteFalso([]))
            assert exc.value.status_code == 422
```

- [ ] **Step 2: Escribir las pruebas de la API (fallan)**

Crear `tests/test_ai_api.py`:

```python
"""API del asistente: gate estricto del módulo `ai`, flujo proponer → confirmar
y estados de la propuesta. El proveedor es siempre un ClienteFalso."""
import json
from decimal import Decimal

import pytest

from conftest import _make_product
from app.core.fechas import hoy_negocio
from app.models import Product, StockOnHand
from app.models.platform import PlatformAuditLog
from app.modules.ai.cliente_llm import ClienteFalso, LlamadaHerramienta, ProveedorNoDisponible, RespuestaLLM
from app.modules.ai.models import AiUsoDiario
from app.modules.ai.router import obtener_cliente_llm


@pytest.fixture()
def ai_habilitado(db, org):
    from app.models.modules import Module, OrganizationModule
    if db.query(Module).filter(Module.key == "ai").first() is None:
        db.add(Module(key="ai", name="IA"))
        db.flush()
    db.add(OrganizationModule(organization_id=org.id, module_key="ai", is_enabled=True))
    db.flush()


@pytest.fixture()
def usar_guion(app):
    def _usar(*respuestas):
        falso = ClienteFalso(list(respuestas))
        app.dependency_overrides[obtener_cliente_llm] = lambda: falso
        return falso
    yield _usar
    app.dependency_overrides.pop(obtener_cliente_llm, None)


def texto(t):
    return RespuestaLLM(texto=t, tokens_entrada=50, tokens_salida=10)


def pide(*llamadas):
    return RespuestaLLM(tool_calls=list(llamadas), tokens_entrada=80, tokens_salida=20)


def alta(id_llamada, sku_base, nombre, branch_id):
    datos = {
        "name": nombre, "sku": f"{sku_base}-CH", "price": 1200, "cost": 600,
        "color": "Negro", "size": "Ch", "initial_stock": 0, "branch_id": branch_id,
        "extra_variants": [
            {"color": "Negro", "size": "M", "sku": f"{sku_base}-M", "initial_stock": 3},
            {"color": "Negro", "size": "G", "sku": f"{sku_base}-G"},
        ],
    }
    return LlamadaHerramienta.desde_crudo(id_llamada, "proponer_cambio",
                                          json.dumps({"tipo": "crear_producto", "datos": datos}))


def _nueva(client, headers):
    r = client.post("/api/ai/conversaciones", json={}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _url(conv, *resto):
    return "/".join(["/api/ai/conversaciones", conv, *resto])


def _primera_propuesta(client, conv, headers):
    r = client.post(_url(conv, "mensajes"), json={"texto": "alta"}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["propuestas_pendientes"][0]["id"]


class TestGate:
    def test_admin_sin_modulo_recibe_403_con_el_plan(self, client, auth_admin):
        r = client.post("/api/ai/conversaciones", json={}, headers=auth_admin)
        assert r.status_code == 403
        assert r.json()["detail"] == (
            "El asistente IA no está incluido en tu plan (mínimo SCALE). La plataforma puede activarlo."
        )
        assert client.get("/api/ai/conversaciones", headers=auth_admin).status_code == 403

    def test_sin_clave_del_proveedor_es_503(self, client, auth_admin, ai_habilitado, monkeypatch):
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        conv = _nueva(client, auth_admin)
        r = client.post(_url(conv, "mensajes"), json={"texto": "hola"}, headers=auth_admin)
        assert r.status_code == 503
        assert r.json()["detail"] == "Asistente no configurado: falta LLM_API_KEY en el servidor."

    def test_health_dice_si_esta_listo(self, client, auth_admin, monkeypatch):
        monkeypatch.setenv("LLM_API_KEY", "k")
        assert client.get("/api/ai/health", headers=auth_admin).json()["ready"] is True


class TestFlujo:
    def test_lote_de_tres_prendas_se_propone_confirma_y_queda_en_productos(
        self, client, db, org, branch_a, auth_admin, ai_habilitado, usar_guion,
    ):
        usar_guion(
            pide(alta("c1", "VER-PLAY-NEG", "Playera cuello redondo", branch_a.id),
                 alta("c2", "GUC-CAMI-ML-NEG", "Camisa manga larga", branch_a.id),
                 alta("c3", "PRA-SUET-CV-NEG", "Suéter cuello V", branch_a.id)),
            texto("Dejé tres propuestas listas para que las confirmes."),
        )
        conv = _nueva(client, auth_admin)
        r = client.post(_url(conv, "mensajes"), headers=auth_admin, json={
            "texto": "Playera, camisa y suéter negros, Ch a G, costo 600, venta 1200, 3 en M",
        })
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert cuerpo["mensaje"]["rol"] == "assistant"
        assert cuerpo["mensaje"]["contenido"] == "Dejé tres propuestas listas para que las confirmes."
        pendientes = cuerpo["propuestas_pendientes"]
        assert [p["estado"] for p in pendientes] == ["pendiente"] * 3
        assert db.query(Product).filter(Product.organization_id == org.id).count() == 0  # nada sin confirmar

        for p in pendientes:
            c = client.post(_url(conv, "propuestas", p["id"], "confirmar"), headers=auth_admin)
            assert c.status_code == 200, c.text
            assert c.json()["estado"] == "confirmada"
            g = client.get(f"/api/products/{c.json()['resultado']['producto_id']}", headers=auth_admin)
            assert g.status_code == 200, g.text
            variantes = {v["size"]: v for v in g.json()["variants"]}
            assert set(variantes) == {"Ch", "M", "G"}
            assert db.query(StockOnHand.qty_on_hand).filter(
                StockOnHand.variant_id == variantes["M"]["id"], StockOnHand.branch_id == branch_a.id,
            ).scalar() == Decimal("3")
        assert db.query(PlatformAuditLog).filter(PlatformAuditLog.action == "PRODUCT_CREATE_AI").count() == 3
        detalle = client.get(_url(conv), headers=auth_admin).json()
        assert [m["rol"] for m in detalle["mensajes"]] == ["user", "assistant", "evento", "evento", "evento"]
        assert [p["estado"] for p in detalle["propuestas"]] == ["confirmada"] * 3

    def test_confirmar_dos_veces_da_409_y_no_duplica(self, client, db, org, branch_a, auth_admin, ai_habilitado, usar_guion):
        # Review Focus #3: doble clic.
        usar_guion(pide(alta("c1", "VER-PLAY-NEG", "Playera", branch_a.id)), texto("Lista."))
        conv = _nueva(client, auth_admin)
        pid = _primera_propuesta(client, conv, auth_admin)
        assert client.post(_url(conv, "propuestas", pid, "confirmar"), headers=auth_admin).status_code == 200
        r = client.post(_url(conv, "propuestas", pid, "confirmar"), headers=auth_admin)
        assert r.status_code == 409 and r.json()["detail"] == "La propuesta ya fue confirmada."
        assert db.query(Product).filter(Product.organization_id == org.id).count() == 1

    def test_sku_tomado_al_confirmar_deja_la_propuesta_en_error(
        self, client, db, org, branch_a, auth_admin, ai_habilitado, usar_guion,
    ):
        usar_guion(pide(alta("c1", "VER-PLAY-NEG", "Playera", branch_a.id)), texto("Lista."))
        conv = _nueva(client, auth_admin)
        pid = _primera_propuesta(client, conv, auth_admin)
        _make_product(db, org, "Intrusa", "VER-PLAY-NEG-CH", 100, [(branch_a.id, True)])
        r = client.post(_url(conv, "propuestas", pid, "confirmar"), headers=auth_admin)
        assert r.status_code == 409 and "ya existe" in r.json()["detail"]
        prop = client.get(_url(conv), headers=auth_admin).json()["propuestas"][0]
        assert prop["estado"] == "error" and "ya existe" in prop["resultado"]["detail"]
        assert client.post(_url(conv, "propuestas", pid, "confirmar"), headers=auth_admin).status_code == 409
        assert client.post(_url(conv, "propuestas", pid, "descartar"), headers=auth_admin).json()["estado"] == "descartada"
        assert db.query(Product).filter(Product.organization_id == org.id).count() == 1  # solo la intrusa

    def test_descartar_y_aplicada_manual(self, client, db, org, branch_a, auth_admin, ai_habilitado, usar_guion):
        usar_guion(pide(alta("c1", "VER-PLAY-NEG", "Playera", branch_a.id),
                        alta("c2", "GUC-CAMI-NEG", "Camisa", branch_a.id)), texto("Listas."))
        conv = _nueva(client, auth_admin)
        r = client.post(_url(conv, "mensajes"), json={"texto": "alta"}, headers=auth_admin)
        p1, p2 = [p["id"] for p in r.json()["propuestas_pendientes"]]
        assert client.post(_url(conv, "propuestas", p1, "descartar"), headers=auth_admin).json()["estado"] == "descartada"
        r = client.post(_url(conv, "propuestas", p1, "confirmar"), headers=auth_admin)
        assert r.status_code == 409 and r.json()["detail"] == "La propuesta fue descartada."
        producto, _ = _make_product(db, org, "Camisa", "GUC-CAMI-NEG-CH", 1200, [(branch_a.id, True)])
        m = client.post(_url(conv, "propuestas", p2, "aplicada-manual"), json={"producto_id": producto.id}, headers=auth_admin)
        assert m.status_code == 200, m.text
        assert m.json()["estado"] == "aplicada_manual" and m.json()["resultado"] == {"producto_id": producto.id}
        r = client.post(_url(conv, "propuestas", p1, "aplicada-manual"), json={}, headers=auth_admin)
        assert r.status_code == 409

    def test_cuota_diaria_agotada_es_429_sin_llamar_al_proveedor(
        self, client, db, org, auth_admin, ai_habilitado, usar_guion, monkeypatch,
    ):
        monkeypatch.setenv("AI_TOKENS_DIA_ORG", "100")
        db.add(AiUsoDiario(organization_id=org.id, fecha=hoy_negocio(), tokens_entrada=90, tokens_salida=20, llamadas=3))
        db.flush()
        falso = usar_guion()
        conv = _nueva(client, auth_admin)
        r = client.post(_url(conv, "mensajes"), json={"texto": "hola"}, headers=auth_admin)
        assert r.status_code == 429
        assert r.json()["detail"] == "Se agotó la cuota diaria del asistente para tu organización. Vuelve a intentarlo mañana."
        assert falso.llamadas == []

    def test_proveedor_caido_es_503_y_no_deja_rastro(self, app, client, auth_admin, ai_habilitado):
        class Caido:
            def completar(self, mensajes, herramientas):
                raise ProveedorNoDisponible("El proveedor del asistente no responde (HTTP 503). Intenta de nuevo.")

        app.dependency_overrides[obtener_cliente_llm] = lambda: Caido()
        try:
            conv = _nueva(client, auth_admin)
            r = client.post(_url(conv, "mensajes"), json={"texto": "hola"}, headers=auth_admin)
            assert r.status_code == 503 and "no responde" in r.json()["detail"]
            assert client.get(_url(conv), headers=auth_admin).json()["mensajes"] == []
        finally:
            app.dependency_overrides.pop(obtener_cliente_llm, None)

    def test_texto_de_mas_de_4000_es_422(self, client, auth_admin, ai_habilitado, usar_guion):
        usar_guion()
        conv = _nueva(client, auth_admin)
        assert client.post(_url(conv, "mensajes"), json={"texto": "x" * 4001}, headers=auth_admin).status_code == 422


class TestAislamiento:
    def test_solo_mis_conversaciones(self, client, auth_admin, auth_cajero_a, ai_habilitado):
        mia = _nueva(client, auth_admin)
        r = client.get(_url(mia), headers=auth_cajero_a)
        assert r.status_code == 404 and r.json()["detail"] == "Conversación no encontrada."
        assert client.get("/api/ai/conversaciones", headers=auth_cajero_a).json() == []
        assert [c["id"] for c in client.get("/api/ai/conversaciones", headers=auth_admin).json()] == [mia]

    def test_propuesta_de_otra_conversacion_es_404(self, client, branch_a, auth_admin, ai_habilitado, usar_guion):
        usar_guion(pide(alta("c1", "VER-PLAY-NEG", "Playera", branch_a.id)), texto("Lista."))
        conv1 = _nueva(client, auth_admin)
        pid = _primera_propuesta(client, conv1, auth_admin)
        conv2 = _nueva(client, auth_admin)
        r = client.post(_url(conv2, "propuestas", pid, "confirmar"), headers=auth_admin)
        assert r.status_code == 404 and r.json()["detail"] == "Propuesta no encontrada."
```

- [ ] **Step 3: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_ai_servicio.py tests/test_ai_api.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.ai.services'` y `ImportError: cannot import name 'obtener_cliente_llm'`.

- [ ] **Step 4: Crear `app/modules/ai/services.py`**

```python
"""Bucle del asistente (SP4): en un turno el modelo y las herramientas se
turnan hasta que el modelo responde con texto. Tope de 8 herramientas y 60 s.

Síncrono: `POST …/mensajes` devuelve la respuesta completa. Todo lo del turno
(mensajes, propuestas, uso de tokens) se escribe en la sesión; el router lo
envuelve en un SAVEPOINT y confirma al final.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.fechas import hoy_negocio
from app.models.organization import Organization
from app.models.users import User

from .cliente_llm import ClienteLLM, RespuestaLLM, limite_tokens_dia
from .contexto import Contexto
from .herramientas import definiciones, ejecutar
from .historial import guardar_mensaje, historial_para_llm
from .models import AiConversation, AiMessage, AiPropuesta, AiUsoDiario
from .prompt import armar_prompt
from .schemas import TOPE_TEXTO

TOPE_HERRAMIENTAS = 8
TIEMPO_MAX_TURNO = 60.0
SIN_RESPUESTA = "No obtuve respuesta del asistente. Intenta de nuevo con otras palabras."
TOPE_ALCANZADO = "Me detuve porque la petición pidió demasiados pasos. Divídela en partes más pequeñas."
CUOTA_AGOTADA = "Se agotó la cuota diaria del asistente para tu organización. Vuelve a intentarlo mañana."
_NO_EJECUTADA = {"error": "No ejecutada: se alcanzó el tope de pasos de este turno."}


@dataclass
class Turno:
    mensaje: AiMessage
    propuestas_pendientes: list[AiPropuesta] = field(default_factory=list)


def verificar_cuota(db: Session, org_id: int) -> None:
    """429 ANTES de llamar al proveedor si el día ya rebasó `AI_TOKENS_DIA_ORG`."""
    uso = db.query(AiUsoDiario).filter(
        AiUsoDiario.organization_id == org_id, AiUsoDiario.fecha == hoy_negocio(),
    ).first()
    if uso is not None and (uso.tokens_entrada + uso.tokens_salida) >= limite_tokens_dia():
        raise HTTPException(status_code=429, detail=CUOTA_AGOTADA)


def registrar_uso(db: Session, org_id: int, r: RespuestaLLM) -> None:
    hoy = hoy_negocio()
    uso = (
        db.query(AiUsoDiario)
        .filter(AiUsoDiario.organization_id == org_id, AiUsoDiario.fecha == hoy)
        .with_for_update().first()
    )
    if uso is None:
        # Dos turnos simultáneos el primer día pueden insertar la misma fila:
        # el SAVEPOINT absorbe el UNIQUE(org, fecha) y se relee la fila ganadora.
        try:
            with db.begin_nested():
                uso = AiUsoDiario(organization_id=org_id, fecha=hoy, tokens_entrada=0, tokens_salida=0, llamadas=0)
                db.add(uso)
                db.flush()
        except IntegrityError:
            uso = (
                db.query(AiUsoDiario)
                .filter(AiUsoDiario.organization_id == org_id, AiUsoDiario.fecha == hoy)
                .with_for_update().one()
            )
    uso.tokens_entrada += r.tokens_entrada
    uso.tokens_salida += r.tokens_salida
    uso.llamadas += 1
    db.flush()


def _llamar(db: Session, org_id: int, cliente: ClienteLLM, sistema: str, conv: AiConversation,
            herramientas: list[dict]) -> RespuestaLLM:
    mensajes = [{"role": "system", "content": sistema}, *historial_para_llm(db, conv)]
    r = cliente.completar(mensajes, herramientas)
    registrar_uso(db, org_id, r)
    return r


def _pendientes(db: Session, conv: AiConversation) -> list[AiPropuesta]:
    return (
        db.query(AiPropuesta)
        .filter(
            AiPropuesta.conversation_id == conv.id,
            AiPropuesta.organization_id == conv.organization_id,
            AiPropuesta.estado == "pendiente",
        )
        .order_by(AiPropuesta.created_at).all()
    )


def _salida_de(llamada, ctx: Contexto) -> dict:
    if llamada.error_json:
        return {"error": f"Argumentos con JSON inválido ({llamada.error_json}). "
                         "Vuelve a llamar la herramienta con un objeto JSON válido."}
    return ejecutar(llamada.nombre, llamada.argumentos, ctx)


def responder(db: Session, conv: AiConversation, user: User, texto: str, cliente: ClienteLLM) -> Turno:
    limpio = (texto or "").strip()
    if not limpio:
        raise HTTPException(status_code=422, detail="Escribe un mensaje.")
    if len(limpio) > TOPE_TEXTO:
        raise HTTPException(status_code=422, detail=f"El mensaje es demasiado largo (máximo {TOPE_TEXTO} caracteres).")
    org = db.query(Organization).filter(Organization.id == conv.organization_id).one()
    verificar_cuota(db, org.id)

    guardar_mensaje(db, conv, "user", limpio)
    if not conv.titulo:
        conv.titulo = limpio[:60]
    conv.updated_at = datetime.now(timezone.utc)
    sistema = armar_prompt(db, org, user)
    ctx = Contexto(db=db, org_id=org.id, user=user, conversacion=conv)
    herramientas = definiciones()
    usadas = 0
    inicio = time.monotonic()

    while True:
        r = _llamar(db, org.id, cliente, sistema, conv, herramientas)
        if not r.tool_calls:
            final = guardar_mensaje(db, conv, "assistant", (r.texto or "").strip() or SIN_RESPUESTA,
                                    tokens_entrada=r.tokens_entrada, tokens_salida=r.tokens_salida)
            break
        guardar_mensaje(db, conv, "assistant", r.texto or "",
                        tool_calls=[ll.como_tool_call() for ll in r.tool_calls],
                        tokens_entrada=r.tokens_entrada, tokens_salida=r.tokens_salida)
        # Cada tool_call recibe su respuesta (aunque no se ejecute): el
        # proveedor rechaza un assistant con llamadas sin contestar.
        for ll in r.tool_calls:
            agotado = usadas >= TOPE_HERRAMIENTAS or time.monotonic() - inicio > TIEMPO_MAX_TURNO
            salida = _NO_EJECUTADA if agotado else _salida_de(ll, ctx)
            usadas += 1
            guardar_mensaje(db, conv, "tool", json.dumps(salida, ensure_ascii=False, default=str),
                            tool_call_id=ll.id)
        if usadas >= TOPE_HERRAMIENTAS or time.monotonic() - inicio > TIEMPO_MAX_TURNO:
            # Última vuelta sin herramientas: que conteste con lo que ya tiene.
            r = _llamar(db, org.id, cliente, sistema, conv, [])
            contenido = "" if r.tool_calls else (r.texto or "").strip()
            final = guardar_mensaje(db, conv, "assistant", contenido or TOPE_ALCANZADO,
                                    tokens_entrada=r.tokens_entrada, tokens_salida=r.tokens_salida)
            break

    db.flush()
    return Turno(mensaje=final, propuestas_pendientes=_pendientes(db, conv))
```

- [ ] **Step 5: Reemplazar `app/modules/ai/gating.py` completo**

```python
"""Módulos encendidos por organización y el gate del asistente (SP4).

`require_module` (app/core/permissions.py) exime a ADMINISTRADOR/DUEÑO; el
asistente cuesta cuota, así que su gate NO tiene excepción por rol: un admin
de una organización FREE recibe 403.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_context import get_current_active_organization
from app.models.modules import OrganizationModule
from app.services.plans import plan_minimo_para


def modulo_encendido(db: Session, org_id: int, clave: str) -> bool:
    """¿`organization_modules.<clave>` está encendido? Sin excepción por rol."""
    return db.query(OrganizationModule.module_key).filter(
        OrganizationModule.organization_id == org_id,
        OrganizationModule.module_key == clave,
        OrganizationModule.is_enabled == True,  # noqa: E712
    ).first() is not None


def mensaje_sin_modulo() -> str:
    plan = plan_minimo_para("ai")
    minimo = plan.nombre if plan else "SCALE"
    return f"El asistente IA no está incluido en tu plan (mínimo {minimo}). La plataforma puede activarlo."


def exigir_modulo_ai(
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_active_organization),
) -> int:
    if not modulo_encendido(db, org_id, "ai"):
        raise HTTPException(status_code=403, detail=mensaje_sin_modulo())
    return org_id
```

- [ ] **Step 6: Reemplazar `app/modules/ai/router.py` completo**

```python
"""API del asistente IA (`/api/ai`, SP4).

Todo endpoint de chat exige el módulo `ai` SIN excepción por rol
(`exigir_modulo_ai`). Solo `confirmar` crea productos, variantes o
existencias; `descartar` y `aplicada-manual` solo cambian el estado.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.tenant_context import get_current_active_organization
from app.models import Product, User

from .cliente_llm import ClienteLLM, ProveedorNoDisponible, cliente_por_defecto, configuracion
from .ejecutores import aplicar
from .gating import exigir_modulo_ai
from .historial import guardar_mensaje, mensajes_de
from .models import AiConversation, AiPropuesta
from .schemas import (
    AplicadaManual, ConversacionCrear, ConversacionDetalle, ConversacionResumen, MensajeCrear,
    MensajeRead, PropuestaRead, RespuestaTurno,
)
from .services import responder

router = APIRouter()

_GATE = [Depends(exigir_modulo_ai)]
TOPE_CONVERSACIONES = 20
_VISIBLES = ("user", "assistant", "evento")
_YA = {
    "confirmada": "La propuesta ya fue confirmada.",
    "descartada": "La propuesta fue descartada.",
    "aplicada_manual": "La propuesta ya se guardó desde el formulario.",
    "error": "La propuesta no se pudo aplicar; ajústala en el formulario o descártala.",
}
_SKU_CARRERA = "Otro registro tomó el mismo SKU mientras tanto. Ajusta la propuesta en el formulario."


def obtener_cliente_llm() -> ClienteLLM:
    """Dependencia aparte para que la suite la sustituya por un ClienteFalso."""
    return cliente_por_defecto()


@router.get("/health")
def health(current_user: User = Depends(get_current_user)):
    return {"module": "ai", "status": "beta", "ready": configuracion().api_key is not None}


def _conversacion(db: Session, org_id: int, user: User, conv_id: str) -> AiConversation:
    conv = db.query(AiConversation).filter(
        AiConversation.id == conv_id,
        AiConversation.organization_id == org_id,
        AiConversation.user_id == user.id,
        AiConversation.deleted_at.is_(None),
    ).first()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversación no encontrada.")
    return conv


def _propuesta(db: Session, conv: AiConversation, pid: str, *, bloquear: bool = False) -> AiPropuesta:
    q = db.query(AiPropuesta).filter(
        AiPropuesta.id == pid,
        AiPropuesta.conversation_id == conv.id,
        AiPropuesta.organization_id == conv.organization_id,
    )
    if bloquear:
        q = q.with_for_update()  # doble clic: en Postgres el segundo espera y ve "confirmada"
    prop = q.first()
    if prop is None:
        raise HTTPException(status_code=404, detail="Propuesta no encontrada.")
    return prop


def _detalle(db: Session, conv: AiConversation) -> ConversacionDetalle:
    mensajes = [m for m in mensajes_de(db, conv) if m.rol in _VISIBLES and (m.contenido or "").strip()]
    propuestas = (
        db.query(AiPropuesta)
        .filter(AiPropuesta.conversation_id == conv.id, AiPropuesta.organization_id == conv.organization_id)
        .order_by(AiPropuesta.created_at).all()
    )
    return ConversacionDetalle(
        id=conv.id, titulo=conv.titulo, created_at=conv.created_at, updated_at=conv.updated_at,
        mensajes=[MensajeRead.model_validate(m) for m in mensajes],
        propuestas=[PropuestaRead.model_validate(p) for p in propuestas],
    )


@router.get("/conversaciones", response_model=List[ConversacionResumen], dependencies=_GATE)
def listar_conversaciones(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    filas = (
        db.query(AiConversation)
        .filter(
            AiConversation.organization_id == org_id,
            AiConversation.user_id == current_user.id,
            AiConversation.deleted_at.is_(None),
        )
        .order_by(AiConversation.updated_at.desc())
        .limit(TOPE_CONVERSACIONES).all()
    )
    return [ConversacionResumen.model_validate(c) for c in filas]


@router.post("/conversaciones", response_model=ConversacionResumen, status_code=201, dependencies=_GATE)
def crear_conversacion(
    body: Optional[ConversacionCrear] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    titulo = ((body.titulo if body else None) or "").strip() or None
    conv = AiConversation(organization_id=org_id, user_id=current_user.id, titulo=titulo)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return ConversacionResumen.model_validate(conv)


@router.get("/conversaciones/{conv_id}", response_model=ConversacionDetalle, dependencies=_GATE)
def ver_conversacion(
    conv_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    return _detalle(db, _conversacion(db, org_id, current_user, conv_id))


@router.post("/conversaciones/{conv_id}/mensajes", response_model=RespuestaTurno, dependencies=_GATE)
def enviar_mensaje(
    conv_id: str,
    body: MensajeCrear,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
    cliente: ClienteLLM = Depends(obtener_cliente_llm),
):
    conv = _conversacion(db, org_id, current_user, conv_id)
    try:
        # Si el proveedor falla a medio turno no queda rastro (ni el mensaje).
        with db.begin_nested():
            turno = responder(db, conv, current_user, body.texto, cliente)
            respuesta = RespuestaTurno(
                mensaje=MensajeRead.model_validate(turno.mensaje),
                propuestas_pendientes=[PropuestaRead.model_validate(p) for p in turno.propuestas_pendientes],
            )
    except ProveedorNoDisponible as e:
        raise HTTPException(status_code=503, detail=str(e))
    db.commit()
    return respuesta


def _marcar_error(db: Session, conv: AiConversation, pid: str, status: int, detail) -> None:
    prop = _propuesta(db, conv, pid)
    prop.estado = "error"
    prop.resultado = {"status": status, "detail": detail}
    db.commit()


@router.post("/conversaciones/{conv_id}/propuestas/{pid}/confirmar", response_model=PropuestaRead,
             dependencies=_GATE)
def confirmar_propuesta(
    conv_id: str,
    pid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    conv = _conversacion(db, org_id, current_user, conv_id)
    prop = _propuesta(db, conv, pid, bloquear=True)
    if prop.estado != "pendiente":
        raise HTTPException(status_code=409, detail=_YA.get(prop.estado, "La propuesta ya no está pendiente."))
    try:
        with db.begin_nested():
            aplicar(db, prop, current_user)
    except IntegrityError:
        _marcar_error(db, conv, pid, 409, _SKU_CARRERA)
        raise HTTPException(status_code=409, detail=_SKU_CARRERA)
    except HTTPException as e:
        # 403 = permiso: la propuesta sigue pendiente (otro día, con el módulo
        # encendido, se puede confirmar). 4xx de datos (SKU tomado, sucursal):
        # queda en `error` con el motivo para que la tarjeta lo muestre.
        if e.status_code != 403:
            _marcar_error(db, conv, pid, e.status_code, e.detail)
        raise
    db.commit()
    db.refresh(prop)
    return PropuestaRead.model_validate(prop)


@router.post("/conversaciones/{conv_id}/propuestas/{pid}/descartar", response_model=PropuestaRead,
             dependencies=_GATE)
def descartar_propuesta(
    conv_id: str,
    pid: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    conv = _conversacion(db, org_id, current_user, conv_id)
    prop = _propuesta(db, conv, pid, bloquear=True)
    if prop.estado not in ("pendiente", "error"):
        raise HTTPException(status_code=409, detail=_YA[prop.estado])
    prop.estado = "descartada"
    db.commit()
    db.refresh(prop)
    return PropuestaRead.model_validate(prop)


@router.post("/conversaciones/{conv_id}/propuestas/{pid}/aplicada-manual", response_model=PropuestaRead,
             dependencies=_GATE)
def marcar_aplicada_manual(
    conv_id: str,
    pid: str,
    body: Optional[AplicadaManual] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """La persona ajustó la propuesta en el formulario y la guardó ella misma."""
    conv = _conversacion(db, org_id, current_user, conv_id)
    prop = _propuesta(db, conv, pid, bloquear=True)
    if prop.estado not in ("pendiente", "error"):
        raise HTTPException(status_code=409, detail=_YA[prop.estado])
    producto_id = body.producto_id if body else None
    if producto_id and db.query(Product.id).filter(
        Product.id == producto_id, Product.organization_id == org_id,
    ).first() is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
    prop.estado = "aplicada_manual"
    prop.resultado = {"producto_id": producto_id}
    prop.confirmada_por = current_user.id
    prop.confirmada_at = datetime.now(timezone.utc)
    guardar_mensaje(db, conv, "evento",
                    f"Propuesta guardada desde el formulario por {current_user.username}: {prop.resumen}"[:2000])
    db.commit()
    db.refresh(prop)
    return PropuestaRead.model_validate(prop)
```

- [ ] **Step 7: Correr las pruebas del módulo**

Run: `python3 -m pytest -q -p no:warnings tests/test_ai_servicio.py tests/test_ai_api.py`
Expected: PASS (8 + 12).

Run: `python3 -m pytest -q -p no:warnings tests/test_ai_*.py`
Expected: PASS (todo el módulo).

- [ ] **Step 8: Commit**

```bash
git add app/modules/ai/services.py app/modules/ai/gating.py app/modules/ai/router.py tests/test_ai_servicio.py tests/test_ai_api.py
git commit -m "$(cat <<'EOF'
feat(ai): bucle de herramientas, gate estricto del módulo ai y API /api/ai

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 8: Herramientas de ventas (`resumen_ventas`, `buscar_ventas`)

**Files:**
- Create: `app/modules/ai/herramientas_ventas.py`
- Modify: `app/modules/ai/herramientas.py` (import y `REGISTRO`)
- Test: `tests/test_ai_herramientas_ventas.py`

**Interfaces:**
- Consumes: `Contexto`, `ErrorHerramienta`, `Herramienta`, `ambito_sucursal` (Tarea 4); `SalesDocument`, `SalesLineItem` (`app.models`); `SALES_REPORT_STATUSES` (`app/services/cash_reconciliation.py`: PAID, REFUNDED_PARTIAL, REFUNDED_TOTAL); `NOMBRE_ZONA_NEGOCIO`, `ZONA_NEGOCIO` (`app/core/fechas.py`). En SQLite la función `timezone(zona, ts)` la simula `tests/conftest.py::_pg_timezone`.
- Produces:
  - `resumen_ventas(desde, hasta?, sucursal_id?) → {"desde","hasta","sucursal_id": int|None,"tickets": int,"total": float,"top_productos": [{"descripcion","piezas","importe"}]}` (solo estados de `SALES_REPORT_STATUSES`; periodo ≤ 92 días).
  - `buscar_ventas(folio?, cliente?, fecha?, sucursal_id?) → {"ventas": [{"id","folio","fecha","total","estado","sucursal_id","cajero"}], "truncado": bool}` (cualquier estado; ≤ 20 filas; **nunca** devuelve el nombre del cliente).

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_ai_herramientas_ventas.py`:

```python
"""Consultas de ventas del asistente (solo lectura): mismas reglas de sucursal
que el resto de herramientas y sin datos de clientes en la respuesta."""
import json
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.fechas import ZONA_NEGOCIO, hoy_negocio
from app.models.sales import DocumentStatus, DocumentType, SalesDocument, SalesLineItem
from app.modules.ai.contexto import Contexto
from app.modules.ai.herramientas import definiciones, ejecutar
from app.modules.ai.models import AiConversation


def _ctx(db, org, user):
    conv = AiConversation(organization_id=org.id, user_id=user.id)
    db.add(conv)
    db.flush()
    return Contexto(db=db, org_id=org.id, user=user, conversacion=conv)


def _a_mediodia(dia):
    return datetime.combine(dia, time(12), tzinfo=ZONA_NEGOCIO).astimezone(timezone.utc)


def _venta(db, org, sucursal, vendedor, variante, folio, total, *, estado=DocumentStatus.PAID,
           cliente=None, dia=None, descripcion="Producto"):
    doc = SalesDocument(
        organization_id=org.id, branch_id=sucursal.id, seller_id=vendedor.id, folio=folio, series="A",
        subtotal=Decimal(total), tax_amount=Decimal(0), total_amount=Decimal(total),
        status=estado, doc_type=DocumentType.INVOICE, customer_name=cliente,
    )
    doc.created_at = _a_mediodia(dia or hoy_negocio())
    db.add(doc)
    db.flush()
    db.add(SalesLineItem(
        organization_id=org.id, document_id=doc.id, variant_id=variante.id, description=descripcion,
        quantity=1, unit_price=Decimal(total), total_line=Decimal(total), unit_cost=Decimal("10"),
    ))
    db.flush()
    return doc


@pytest.fixture()
def ventas(db, org, branch_a, branch_b, cajero_a, admin_user, products_setup):
    variante = products_setup["product_a"][1]
    _venta(db, org, branch_a, cajero_a, variante, 12, "100", cliente="Ana López", descripcion="Playera")
    _venta(db, org, branch_b, admin_user, variante, 13, "200", descripcion="Camisa")
    _venta(db, org, branch_a, cajero_a, variante, 14, "999", estado=DocumentStatus.CANCELLED, descripcion="Cancelada")
    _venta(db, org, branch_a, cajero_a, variante, 9, "50", dia=hoy_negocio() - timedelta(days=1), descripcion="Ayer")


def test_herramientas_de_ventas_registradas():
    assert {"resumen_ventas", "buscar_ventas"} <= {d["function"]["name"] for d in definiciones()}


class TestResumen:
    def test_admin_ve_toda_la_org(self, db, org, admin_user, ventas):
        hoy = hoy_negocio().isoformat()
        r = ejecutar("resumen_ventas", {"desde": hoy, "hasta": hoy}, _ctx(db, org, admin_user))
        assert (r["tickets"], r["total"], r["sucursal_id"]) == (2, 300.0, None)
        assert {p["descripcion"] for p in r["top_productos"]} == {"Playera", "Camisa"}

    def test_cajero_solo_su_sucursal(self, db, org, cajero_a, branch_a, branch_b, ventas):
        ctx = _ctx(db, org, cajero_a)
        hoy = hoy_negocio().isoformat()
        r = ejecutar("resumen_ventas", {"desde": hoy, "hasta": hoy}, ctx)
        assert (r["tickets"], r["total"], r["sucursal_id"]) == (1, 100.0, branch_a.id)
        assert ejecutar("resumen_ventas", {"desde": hoy, "sucursal_id": branch_b.id}, ctx) == {
            "error": "Solo puedes consultar tu sucursal."}

    def test_periodo_de_dos_dias(self, db, org, admin_user, ventas):
        ayer = (hoy_negocio() - timedelta(days=1)).isoformat()
        r = ejecutar("resumen_ventas", {"desde": ayer, "hasta": hoy_negocio().isoformat()}, _ctx(db, org, admin_user))
        assert (r["tickets"], r["total"]) == (3, 350.0)

    def test_fechas_invalidas(self, db, org, admin_user):
        ctx = _ctx(db, org, admin_user)
        assert ejecutar("resumen_ventas", {"desde": "ayer"}, ctx) == {"error": "desde debe ser una fecha AAAA-MM-DD."}
        assert ejecutar("resumen_ventas", {"desde": "2026-10-10", "hasta": "2026-10-01"}, ctx) == {
            "error": "hasta no puede ser anterior a desde."}
        assert ejecutar("resumen_ventas", {"desde": "2026-01-01", "hasta": "2026-10-01"}, ctx) == {
            "error": "El periodo no puede pasar de 92 días."}


class TestBuscar:
    def test_por_folio_con_serie(self, db, org, admin_user, ventas):
        r = ejecutar("buscar_ventas", {"folio": "A-12"}, _ctx(db, org, admin_user))
        assert [v["folio"] for v in r["ventas"]] == ["A-12"]
        venta = r["ventas"][0]
        assert (venta["cajero"], venta["total"], venta["estado"]) == ("cajero_a", 100.0, "PAID")
        assert "cliente" not in venta and "customer_name" not in venta

    def test_por_cliente_no_devuelve_su_nombre(self, db, org, admin_user, ventas):
        r = ejecutar("buscar_ventas", {"cliente": "ana"}, _ctx(db, org, admin_user))
        assert [v["folio"] for v in r["ventas"]] == ["A-12"]
        assert "Ana" not in json.dumps(r, ensure_ascii=False)

    def test_por_fecha_incluye_canceladas(self, db, org, admin_user, ventas):
        r = ejecutar("buscar_ventas", {"fecha": hoy_negocio().isoformat()}, _ctx(db, org, admin_user))
        assert sorted(v["folio"] for v in r["ventas"]) == ["A-12", "A-13", "A-14"]

    def test_cajero_no_ve_otra_sucursal(self, db, org, cajero_a, ventas):
        assert ejecutar("buscar_ventas", {"folio": 13}, _ctx(db, org, cajero_a)) == {"ventas": [], "truncado": False}

    def test_sin_filtros_es_error(self, db, org, admin_user):
        assert ejecutar("buscar_ventas", {}, _ctx(db, org, admin_user)) == {"error": "Indica folio, cliente o fecha."}
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_ai_herramientas_ventas.py`
Expected: FAIL — `test_herramientas_de_ventas_registradas` con `AssertionError` y el resto con `{"error": "Herramienta desconocida: resumen_ventas"}` / `buscar_ventas`.

- [ ] **Step 3: Crear `app/modules/ai/herramientas_ventas.py`**

```python
"""Consultas de ventas del asistente (solo lectura).

Totales con el mismo criterio de "venta reconocida" que los reportes
(`SALES_REPORT_STATUSES`); la búsqueda muestra cualquier estado. Alcance:
`ambito_sucursal` (admin/dueño toda la org, el resto su sucursal). Nunca
devuelve datos del cliente: se puede filtrar por su nombre, pero la
respuesta no lo trae (el contenido viaja al proveedor del LLM).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import desc, func

from app.core.fechas import NOMBRE_ZONA_NEGOCIO, ZONA_NEGOCIO
from app.models import SalesDocument, SalesLineItem
from app.services.cash_reconciliation import SALES_REPORT_STATUSES

from .contexto import Contexto, ErrorHerramienta, Herramienta, ambito_sucursal

TOPE_DIAS = 92
TOPE_VENTAS = 20
TOPE_PRODUCTOS = 10
_FOLIO = re.compile(r"\s*([A-Za-z]*)\s*-?\s*(\d+)\s*")


def _dia_local(columna):
    """Día del negocio de un TIMESTAMPTZ (`timezone()` de Postgres; la suite la simula)."""
    return func.date(func.timezone(NOMBRE_ZONA_NEGOCIO, columna))


def _fecha(valor: Any, campo: str) -> date:
    try:
        return date.fromisoformat(str(valor).strip())
    except (TypeError, ValueError):
        raise ErrorHerramienta(f"{campo} debe ser una fecha AAAA-MM-DD.")


def _hora_local(momento: Optional[datetime]) -> Optional[str]:
    if momento is None:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(ZONA_NEGOCIO).strftime("%Y-%m-%d %H:%M")


def resumen_ventas(ctx: Contexto, args: dict) -> dict:
    desde = _fecha(args.get("desde"), "desde")
    hasta = desde if args.get("hasta") in (None, "") else _fecha(args.get("hasta"), "hasta")
    if hasta < desde:
        raise ErrorHerramienta("hasta no puede ser anterior a desde.")
    if (hasta - desde).days > TOPE_DIAS:
        raise ErrorHerramienta(f"El periodo no puede pasar de {TOPE_DIAS} días.")
    sucursal = ambito_sucursal(ctx, args.get("sucursal_id"))
    filtros = [
        SalesDocument.organization_id == ctx.org_id,
        SalesDocument.status.in_(SALES_REPORT_STATUSES),
        _dia_local(SalesDocument.created_at).between(desde, hasta),
    ]
    if sucursal is not None:
        filtros.append(SalesDocument.branch_id == sucursal)
    tickets, total = ctx.db.query(
        func.count(SalesDocument.id), func.coalesce(func.sum(SalesDocument.total_amount), 0),
    ).filter(*filtros).one()
    top = (
        ctx.db.query(
            SalesLineItem.description,
            func.sum(SalesLineItem.quantity).label("piezas"),
            func.sum(SalesLineItem.total_line).label("importe"),
        )
        .join(SalesDocument, SalesDocument.id == SalesLineItem.document_id)
        .filter(*filtros)
        .group_by(SalesLineItem.description)
        .order_by(desc("piezas"))
        .limit(TOPE_PRODUCTOS).all()
    )
    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "sucursal_id": sucursal,
        "tickets": int(tickets or 0),
        "total": float(total or 0),
        "top_productos": [
            {"descripcion": d, "piezas": float(p or 0), "importe": float(i or 0)} for d, p, i in top
        ],
    }


def buscar_ventas(ctx: Contexto, args: dict) -> dict:
    folio = args.get("folio")
    cliente = str(args.get("cliente") or "").strip()
    fecha = args.get("fecha")
    if folio in (None, "") and not cliente and fecha in (None, ""):
        raise ErrorHerramienta("Indica folio, cliente o fecha.")
    sucursal = ambito_sucursal(ctx, args.get("sucursal_id"))
    q = ctx.db.query(SalesDocument).filter(SalesDocument.organization_id == ctx.org_id)
    if sucursal is not None:
        q = q.filter(SalesDocument.branch_id == sucursal)
    if folio not in (None, ""):
        m = _FOLIO.fullmatch(str(folio))
        if not m:
            raise ErrorHerramienta("folio debe ser un número, por ejemplo 41 o A-41.")
        q = q.filter(SalesDocument.folio == int(m.group(2)))
        if m.group(1):
            q = q.filter(func.upper(SalesDocument.series) == m.group(1).upper())
    if cliente:
        q = q.filter(SalesDocument.customer_name.ilike(f"%{cliente}%"))
    if fecha not in (None, ""):
        q = q.filter(_dia_local(SalesDocument.created_at) == _fecha(fecha, "fecha"))
    docs = q.order_by(SalesDocument.created_at.desc()).limit(TOPE_VENTAS + 1).all()
    ventas = [{
        "id": d.id,
        "folio": f"{d.series}-{d.folio}" if d.series else str(d.folio),
        "fecha": _hora_local(d.created_at),
        "total": float(d.total_amount or 0),
        "estado": getattr(d.status, "value", str(d.status)),
        "sucursal_id": d.branch_id,
        "cajero": (d.seller.full_name or d.seller.username) if d.seller else None,
    } for d in docs[:TOPE_VENTAS]]
    return {"ventas": ventas, "truncado": len(docs) > TOPE_VENTAS}


HERRAMIENTAS: dict[str, Herramienta] = {
    "resumen_ventas": Herramienta(
        "Total vendido, número de tickets y los 10 productos más vendidos de un periodo (AAAA-MM-DD).",
        {"type": "object", "properties": {
            "desde": {"type": "string", "description": "Fecha inicial AAAA-MM-DD."},
            "hasta": {"type": "string", "description": "Fecha final AAAA-MM-DD (por defecto = desde)."},
            "sucursal_id": {"type": "integer"},
        }, "required": ["desde"]},
        resumen_ventas,
    ),
    "buscar_ventas": Herramienta(
        "Busca ventas por folio (41 o A-41), nombre del cliente o fecha (AAAA-MM-DD). Hasta 20 filas.",
        {"type": "object", "properties": {
            "folio": {"type": "string"},
            "cliente": {"type": "string"},
            "fecha": {"type": "string"},
            "sucursal_id": {"type": "integer"},
        }},
        buscar_ventas,
    ),
}
```

- [ ] **Step 4: Registrar en `app/modules/ai/herramientas.py`**

Reemplazar:

```python
from .herramientas_propuestas import HERRAMIENTAS as _PROPUESTAS

logger = logging.getLogger(__name__)

REGISTRO: dict[str, Herramienta] = {**_CATALOGO, **_PROPUESTAS}
```

por:

```python
from .herramientas_propuestas import HERRAMIENTAS as _PROPUESTAS
from .herramientas_ventas import HERRAMIENTAS as _VENTAS

logger = logging.getLogger(__name__)

REGISTRO: dict[str, Herramienta] = {**_CATALOGO, **_PROPUESTAS, **_VENTAS}
```

- [ ] **Step 5: Correr las pruebas**

Run: `python3 -m pytest -q -p no:warnings tests/test_ai_herramientas_ventas.py tests/test_ai_herramientas_catalogo.py tests/test_ai_servicio.py`
Expected: PASS (10 + 11 + 8).

- [ ] **Step 6: Commit**

```bash
git add app/modules/ai/herramientas_ventas.py app/modules/ai/herramientas.py tests/test_ai_herramientas_ventas.py
git commit -m "$(cat <<'EOF'
feat(ai): consultas de ventas por periodo y por folio/cliente/fecha, sin datos del cliente

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 9: Frontend — cliente `api/ai.ts`, `propuestaAFormulario`, `TarjetaPropuesta`, `ChatAsistente`

**Files:**
- Create: `frontend/src/api/ai.ts`
- Modify: `frontend/src/components/products/types.ts` (tipo `InicialFormulario`)
- Create: `frontend/src/components/ai/propuestaAFormulario.ts`, `frontend/src/components/ai/TarjetaPropuesta.tsx`, `frontend/src/components/ai/ChatAsistente.tsx`
- Test: `frontend/src/components/ai/__tests__/propuestaAFormulario.test.ts`, `TarjetaPropuesta.test.tsx`, `ChatAsistente.test.tsx`

**Interfaces:**
- Consumes: el contrato HTTP de la Tarea 7 (rutas y formas JSON, sin cambios de nombre); `client` (`src/api/client.ts`, base `/api`); `productsApi.getDepartments(): Promise<Department[]>`, `productsApi.getBrands(): Promise<Brand[]>`; `VariantRow`, `skuPart` (`components/products/variantMatrix.ts`); `ProductFormValue`, `Department`, `Brand` (`components/products/types.ts`); `formatCurrency` (`utils/currency.ts`); `toast` (`store/toastStore.ts`); `Spinner` (`components/ui/Spinner.tsx`).
- Produces (tareas 10 y 11):
  - `api/ai.ts`: tipos `TipoPropuesta`, `EstadoPropuesta`, `MensajeIA {id, rol: 'user'|'assistant'|'evento', contenido: string|null, created_at}`, `PropuestaIA {id, tipo, datos: Record<string, unknown>, estado, resumen, avisos: string[], resultado: Record<string, unknown>|null, created_at}`, `ConversacionResumen`, `ConversacionDetalle`, `RespuestaTurno {mensaje, propuestas_pendientes}`; `aiApi.{listar(), obtener(id), crear(titulo?), enviar(id, texto), confirmar(id, pid), descartar(id, pid), aplicadaManual(id, pid, productoId?)}`; `textoDeError(e: unknown, porDefecto?: string): string`.
  - `components/products/types.ts`: `interface InicialFormulario { form: Partial<ProductFormValue>; variantRows?: VariantRow[]; colores?: string; tallas?: string }`.
  - `propuestaAFormulario(datos: Record<string, unknown>, departments: Department[], brands: Brand[]): InicialFormulario & { avisos: string[] }`.
  - `<TarjetaPropuesta propuesta departments brands ocupada onConfirmar onAjustar onDescartar />`; `ETIQUETA_ESTADO`.
  - `<ChatAsistente presentacion: 'pagina'|'drawer' conversacionId: string|null onConversacion(id) onAjustar(propuesta, inicial: InicialFormulario, conversacionId) onAplicada?(propuesta) />`; la caja de texto tiene etiqueta accesible `"Mensaje para el asistente"` y el botón se llama `"Enviar"`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `frontend/src/components/ai/__tests__/propuestaAFormulario.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { propuestaAFormulario } from '../propuestaAFormulario'

const deptos = [{ id: 'd1', name: 'Playeras' }]
const marcas = [{ id: 'b1', name: 'Versace', logo_url: null }]
const datos = {
  name: 'Playera cuello redondo', sku: 'VER-PLAY-CR-NEG-CH', price: '1200', cost: '600', has_iva: false,
  department_id: 'd1', brand_id: 'b1', gender: 'HOMBRE', model: null, material: null, description: 'Mensaje del dueño',
  color: 'Negro', size: 'Ch', initial_stock: '0', branch_id: 20, target_branch_ids: [20],
  extra_variants: [
    { color: 'Negro', size: 'M', sku: 'VER-PLAY-CR-NEG-M', price: null, initial_stock: '3' },
    { color: 'Negro', size: 'G', sku: 'VER-PLAY-CR-NEG-G', price: null, initial_stock: '0' },
  ],
}

describe('propuestaAFormulario', () => {
  it('pasa la ficha al formulario como texto, sin inventar nada', () => {
    const r = propuestaAFormulario(datos, deptos, marcas)
    expect(r.form).toMatchObject({
      name: 'Playera cuello redondo', sku: 'VER-PLAY-CR-NEG-CH', price: '1200', cost: '600',
      department_id: 'd1', brand_id: 'b1', gender: 'HOMBRE', model: '', material: '',
      description: 'Mensaje del dueño', initial_stock: '0', initial_stock_branch_id: '20', has_iva: false,
    })
    expect(r.avisos).toEqual([])
  })

  it('arma la matriz con la principal primero y la existencia en su talla', () => {
    const r = propuestaAFormulario(datos, deptos, marcas)
    expect(r.colores).toBe('Negro')
    expect(r.tallas).toBe('Ch, M, G')
    expect(r.variantRows!.map((f) => [f.key, f.sku, f.initial_stock, f.skuTocado ?? false])).toEqual([
      ['negro|ch', 'VER-PLAY-CR-NEG-CH-NEGRO-CH', '0', false],
      ['negro|m', 'VER-PLAY-CR-NEG-M', '3', true],
      ['negro|g', 'VER-PLAY-CR-NEG-G', '0', true],
    ])
  })

  it('departamento o marca que no existen quedan vacíos con aviso', () => {
    const r = propuestaAFormulario({ ...datos, department_id: 'otro', brand_id: 'otra' }, deptos, marcas)
    expect(r.form.department_id).toBe('')
    expect(r.form.brand_id).toBe('')
    expect(r.avisos).toEqual([
      'El departamento propuesto no existe; elígelo en el formulario.',
      'La marca propuesta no existe; elígela en el formulario.',
    ])
  })

  it('matriz no rectangular: avisa las combinaciones que agrega', () => {
    const r = propuestaAFormulario({ ...datos, extra_variants: [{ color: 'Blanco', size: 'M', initial_stock: 1 }] }, deptos, marcas)
    expect(r.variantRows).toHaveLength(4)
    expect(r.variantRows!.find((f) => f.key === 'blanco|ch')!.initial_stock).toBe('')
    expect(r.variantRows!.find((f) => f.key === 'blanco|m')!.initial_stock).toBe('1')
    expect(r.avisos).toEqual(['La matriz agrega 2 combinación(es) que no venían en la propuesta; nacen sin existencia.'])
  })

  it('sin color ni talla no hay matriz', () => {
    const r = propuestaAFormulario({ name: 'Bolsa', sku: 'goy-bols', price: 5000, cost: 0 }, [], [])
    expect(r.variantRows).toEqual([])
    expect([r.colores, r.tallas]).toEqual(['', ''])
    expect(r.form).toMatchObject({ sku: 'GOY-BOLS', price: '5000', cost: '0', initial_stock: '0' })
  })
})
```

Crear `frontend/src/components/ai/__tests__/TarjetaPropuesta.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { TarjetaPropuesta } from '../TarjetaPropuesta'
import type { PropuestaIA } from '../../../api/ai'

const base: PropuestaIA = {
  id: 'p1', tipo: 'crear_producto', estado: 'pendiente', created_at: '2026-10-18T12:00:00Z', resultado: null,
  resumen: 'Alta: Versace · Playera · SKU VER-1 · $1,200.00 (costo $0.00) · 2 variante(s) · 3 pieza(s)',
  avisos: ['Costo en $0: confírmalo antes de guardar.'],
  datos: {
    name: 'Playera', sku: 'VER-1', price: '1200', cost: '0', brand_id: 'b1', department_id: 'd1', gender: 'HOMBRE',
    color: 'Negro', size: 'Ch', initial_stock: '0', extra_variants: [{ color: 'Negro', size: 'M', initial_stock: '3' }],
  },
}
const acciones = () => ({ onConfirmar: vi.fn(), onAjustar: vi.fn(), onDescartar: vi.fn() })

afterEach(cleanup)

describe('TarjetaPropuesta', () => {
  it('pendiente: resumen, nombres, matriz, avisos y los tres botones', () => {
    const on = acciones()
    render(<TarjetaPropuesta propuesta={base} departments={[{ id: 'd1', name: 'Playeras' }]}
      brands={[{ id: 'b1', name: 'Versace', logo_url: null }]} ocupada={false} {...on} />)
    expect(screen.getByText(base.resumen)).toBeTruthy()
    expect(screen.getByText('Versace')).toBeTruthy()
    expect(screen.getByText('Playeras')).toBeTruthy()
    expect(screen.getByText('Costo en $0: confírmalo antes de guardar.')).toBeTruthy()
    expect(screen.getAllByRole('row')).toHaveLength(3) // encabezado + Ch + M
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ajustar en formulario' }))
    fireEvent.click(screen.getByRole('button', { name: 'Descartar' }))
    expect([on.onConfirmar, on.onAjustar, on.onDescartar].every((f) => f.mock.calls.length === 1)).toBe(true)
  })

  it('confirmada: en gris, con su estado y sin botones', () => {
    render(<TarjetaPropuesta propuesta={{ ...base, estado: 'confirmada' }} departments={[]} brands={[]} ocupada={false} {...acciones()} />)
    expect(screen.getByText('Confirmada')).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('error: muestra el motivo y deja ajustar o descartar, no confirmar', () => {
    const conError = { ...base, estado: 'error' as const, resultado: { status: 409, detail: "El SKU 'VER-1' ya existe en esta organización." } }
    render(<TarjetaPropuesta propuesta={conError} departments={[]} brands={[]} ocupada={false} {...acciones()} />)
    expect(screen.getByRole('alert').textContent).toContain('ya existe')
    expect(screen.queryByRole('button', { name: 'Confirmar' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Ajustar en formulario' })).toBeTruthy()
  })

  it('ajuste de existencias no ofrece el formulario', () => {
    const ajuste: PropuestaIA = { ...base, tipo: 'ajustar_existencias', avisos: [],
      datos: { ajustes: [{ variant_id: 'v1', sucursal_id: 20, existencia_nueva: '7' }] } }
    render(<TarjetaPropuesta propuesta={ajuste} departments={[]} brands={[]} ocupada={false} {...acciones()} />)
    expect(screen.queryByRole('button', { name: 'Ajustar en formulario' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Confirmar' })).toBeTruthy()
  })
})
```

Crear `frontend/src/components/ai/__tests__/ChatAsistente.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'

const ai = {
  listar: vi.fn(), obtener: vi.fn(), crear: vi.fn(), enviar: vi.fn(),
  confirmar: vi.fn(), descartar: vi.fn(), aplicadaManual: vi.fn(),
}
vi.mock('../../../api/ai', async () => {
  const real = await vi.importActual<typeof import('../../../api/ai')>('../../../api/ai')
  return { ...real, aiApi: ai }
})
vi.mock('../../../api/products', () => ({
  productsApi: {
    getDepartments: vi.fn(async () => [{ id: 'd1', name: 'Playeras' }]),
    getBrands: vi.fn(async () => [{ id: 'b1', name: 'Versace', logo_url: null }]),
  },
}))
vi.mock('../../../store/toastStore', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }))

const { ChatAsistente } = await import('../ChatAsistente')

const propuesta = {
  id: 'p1', tipo: 'crear_producto', estado: 'pendiente', resumen: 'Alta: Versace · Playera · SKU VER-1',
  avisos: [], resultado: null, created_at: '2026-10-18T12:00:00Z',
  datos: { name: 'Playera', sku: 'VER-1', price: '1200', cost: '600', color: 'Negro', size: 'Ch', initial_stock: '0', extra_variants: [] },
}
const conversacion = (propuestas: unknown[] = []) => ({ id: 'c1', titulo: null, created_at: '', updated_at: '', mensajes: [], propuestas })
const caja = () => screen.getByLabelText('Mensaje para el asistente') as HTMLTextAreaElement

beforeEach(() => vi.clearAllMocks())
afterEach(cleanup)

describe('ChatAsistente', () => {
  it('Enter crea la conversación, envía y pinta la respuesta y la tarjeta', async () => {
    let soltar: (v: unknown) => void = () => {}
    ai.crear.mockResolvedValue({ id: 'c1', titulo: null, created_at: '', updated_at: '' })
    ai.enviar.mockReturnValue(new Promise((r) => { soltar = r }))
    const onConversacion = vi.fn()
    render(<ChatAsistente presentacion="pagina" conversacionId={null} onConversacion={onConversacion} onAjustar={vi.fn()} />)
    const texto = 'Playera Versace negra, Ch, costo 600, venta 1200'
    fireEvent.change(caja(), { target: { value: texto } })
    fireEvent.keyDown(caja(), { key: 'Enter' })
    expect(await screen.findByText('Pensando…')).toBeTruthy()
    expect(screen.getByText(texto)).toBeTruthy()
    await waitFor(() => expect(ai.enviar).toHaveBeenCalledWith('c1', texto))
    expect(onConversacion).toHaveBeenCalledWith('c1')
    soltar({
      mensaje: { id: 'm2', rol: 'assistant', contenido: 'Listo, revisa la propuesta.', created_at: '' },
      propuestas_pendientes: [propuesta],
    })
    expect(await screen.findByText('Listo, revisa la propuesta.')).toBeTruthy()
    expect(screen.getByText('Alta: Versace · Playera · SKU VER-1')).toBeTruthy()
    expect(screen.queryByText('Pensando…')).toBeNull()
  })

  it('Shift+Enter no envía', () => {
    render(<ChatAsistente presentacion="pagina" conversacionId={null} onConversacion={vi.fn()} onAjustar={vi.fn()} />)
    fireEvent.change(caja(), { target: { value: 'hola' } })
    fireEvent.keyDown(caja(), { key: 'Enter', shiftKey: true })
    expect(ai.crear).not.toHaveBeenCalled()
    expect(ai.enviar).not.toHaveBeenCalled()
  })

  it('un 503 muestra el motivo y devuelve el texto a la caja', async () => {
    ai.obtener.mockResolvedValue(conversacion())
    ai.enviar.mockRejectedValue({ response: { status: 503, data: { detail: 'Asistente no configurado: falta LLM_API_KEY en el servidor.' } } })
    render(<ChatAsistente presentacion="drawer" conversacionId="c1" onConversacion={vi.fn()} onAjustar={vi.fn()} />)
    fireEvent.change(caja(), { target: { value: 'hola' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enviar' }))
    expect((await screen.findByRole('alert')).textContent).toBe('Asistente no configurado: falta LLM_API_KEY en el servidor.')
    expect(caja().value).toBe('hola')
    expect(ai.crear).not.toHaveBeenCalled()
  })

  it('Confirmar llama a la API y avisa a quien monta el chat', async () => {
    ai.obtener.mockResolvedValue(conversacion([propuesta]))
    ai.confirmar.mockResolvedValue({ ...propuesta, estado: 'confirmada', resultado: { producto_id: 'x' } })
    const onAplicada = vi.fn()
    render(<ChatAsistente presentacion="pagina" conversacionId="c1" onConversacion={vi.fn()} onAjustar={vi.fn()} onAplicada={onAplicada} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Confirmar' }))
    await waitFor(() => expect(ai.confirmar).toHaveBeenCalledWith('c1', 'p1'))
    await waitFor(() => expect(onAplicada).toHaveBeenCalledWith(expect.objectContaining({ estado: 'confirmada' })))
  })

  it('Ajustar en formulario entrega la ficha convertida', async () => {
    ai.obtener.mockResolvedValue(conversacion([propuesta]))
    const onAjustar = vi.fn()
    render(<ChatAsistente presentacion="pagina" conversacionId="c1" onConversacion={vi.fn()} onAjustar={onAjustar} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Ajustar en formulario' }))
    expect(onAjustar).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'p1' }),
      expect.objectContaining({ form: expect.objectContaining({ name: 'Playera', sku: 'VER-1', price: '1200' }) }),
      'c1',
    )
  })
})
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `cd frontend && npx vitest run src/components/ai`
Expected: FAIL — `Failed to resolve import "../propuestaAFormulario"` (y los otros dos módulos).

- [ ] **Step 3: Agregar `InicialFormulario` a `frontend/src/components/products/types.ts`**

Tras las dos líneas `import type …` del inicio, agregar:

```ts
import type { VariantRow } from './variantMatrix'
```

Y al final del archivo (antes de `export type { Brand, Department, Branch }`):

```ts
/**
 * Valores con los que arranca un alta (asistente IA → "Ajustar en formulario").
 * `colores`/`tallas` son el texto de los campos de la matriz: la matriz se
 * regenera desde ellos al montar y sin ellos borraría `variantRows`.
 */
export interface InicialFormulario {
  form: Partial<ProductFormValue>
  variantRows?: VariantRow[]
  colores?: string
  tallas?: string
}
```

- [ ] **Step 4: Crear `frontend/src/api/ai.ts`**

```ts
import client from './client'

/** Contrato de `/api/ai` (backend: app/modules/ai/router.py). */
export type TipoPropuesta = 'crear_producto' | 'agregar_variantes' | 'ajustar_existencias'
export type EstadoPropuesta = 'pendiente' | 'confirmada' | 'descartada' | 'aplicada_manual' | 'error'

export interface MensajeIA {
  id: string
  rol: 'user' | 'assistant' | 'evento'
  contenido: string | null
  created_at: string
}

export interface PropuestaIA {
  id: string
  tipo: TipoPropuesta
  datos: Record<string, unknown>
  estado: EstadoPropuesta
  resumen: string
  avisos: string[]
  resultado: Record<string, unknown> | null
  created_at: string
}

export interface ConversacionResumen {
  id: string
  titulo: string | null
  created_at: string
  updated_at: string
}

export interface ConversacionDetalle extends ConversacionResumen {
  mensajes: MensajeIA[]
  propuestas: PropuestaIA[]
}

export interface RespuestaTurno {
  mensaje: MensajeIA
  propuestas_pendientes: PropuestaIA[]
}

const BASE = '/ai/conversaciones'

export const aiApi = {
  listar: async (): Promise<ConversacionResumen[]> => (await client.get(BASE)).data,
  obtener: async (id: string): Promise<ConversacionDetalle> => (await client.get(`${BASE}/${id}`)).data,
  crear: async (titulo?: string): Promise<ConversacionResumen> =>
    (await client.post(BASE, titulo ? { titulo } : {})).data,
  enviar: async (id: string, texto: string): Promise<RespuestaTurno> =>
    (await client.post(`${BASE}/${id}/mensajes`, { texto })).data,
  confirmar: async (id: string, pid: string): Promise<PropuestaIA> =>
    (await client.post(`${BASE}/${id}/propuestas/${pid}/confirmar`)).data,
  descartar: async (id: string, pid: string): Promise<PropuestaIA> =>
    (await client.post(`${BASE}/${id}/propuestas/${pid}/descartar`)).data,
  aplicadaManual: async (id: string, pid: string, productoId?: string): Promise<PropuestaIA> =>
    (await client.post(`${BASE}/${id}/propuestas/${pid}/aplicada-manual`, { producto_id: productoId ?? null })).data,
}

/** El `detail` del servidor (403 plan, 429 cuota, 503 proveedor) o un texto legible. */
export function textoDeError(e: unknown, porDefecto = 'No se pudo hablar con el asistente. Intenta de nuevo.'): string {
  const r = (e as { response?: { status?: number; data?: { detail?: unknown } } } | null)?.response
  const detail = r?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) return 'Revisa el mensaje (máximo 4000 caracteres).'
  if (r?.status === 429) return 'Se agotó la cuota del asistente por hoy.'
  if (r?.status === 503) return 'El asistente no está disponible en este momento.'
  return porDefecto
}
```

- [ ] **Step 5: Crear `frontend/src/components/ai/propuestaAFormulario.ts`**

```ts
/**
 * Propuesta `crear_producto` del asistente → valores iniciales del
 * FormularioProducto ("Ajustar en formulario"). Función pura: no inventa
 * nada; lo que no viene queda vacío y lo que no cuadra se avisa.
 */
import type { Brand, Department, InicialFormulario, ProductFormValue } from '../products/types'
import { skuPart, type VariantRow } from '../products/variantMatrix'

type Datos = Record<string, unknown>
interface Combo { color: string; size: string; initial_stock?: unknown; sku?: unknown; price?: unknown }

const texto = (v: unknown): string => (v === null || v === undefined ? '' : String(v).trim())
const numeroTexto = (v: unknown): string => {
  const t = texto(v)
  if (!t) return ''
  const n = Number(t)
  return Number.isFinite(n) ? String(n) : ''
}
const unicos = (xs: string[]): string[] => {
  const vistos = new Set<string>()
  return xs.filter((x) => {
    const k = x.toLowerCase()
    if (!x || vistos.has(k)) return false
    vistos.add(k)
    return true
  })
}
const llave = (color: string, size: string) => `${color.toLowerCase()}|${size.toLowerCase()}`

export function propuestaAFormulario(
  datos: Datos, departments: Department[], brands: Brand[],
): InicialFormulario & { avisos: string[] } {
  const avisos: string[] = []
  const deptId = texto(datos.department_id)
  const brandId = texto(datos.brand_id)
  const deptOk = !deptId || departments.some((d) => d.id === deptId)
  const brandOk = !brandId || brands.some((b) => b.id === brandId)
  if (!deptOk) avisos.push('El departamento propuesto no existe; elígelo en el formulario.')
  if (!brandOk) avisos.push('La marca propuesta no existe; elígela en el formulario.')

  const sku = texto(datos.sku).toUpperCase()
  const form: Partial<ProductFormValue> = {
    name: texto(datos.name),
    sku,
    description: texto(datos.description),
    department_id: deptOk ? deptId : '',
    brand_id: brandOk ? brandId : '',
    gender: texto(datos.gender),
    model: texto(datos.model),
    material: texto(datos.material),
    price: numeroTexto(datos.price),
    cost: numeroTexto(datos.cost),
    has_iva: datos.has_iva === true,
    initial_stock: numeroTexto(datos.initial_stock) || '0',
    initial_stock_branch_id: texto(datos.branch_id),
  }

  const extras = Array.isArray(datos.extra_variants) ? (datos.extra_variants as Datos[]) : []
  const combos: Combo[] = [
    { color: texto(datos.color), size: texto(datos.size), initial_stock: datos.initial_stock },
    ...extras.map((e) => ({ color: texto(e.color), size: texto(e.size), initial_stock: e.initial_stock, sku: e.sku, price: e.price })),
  ].filter((c) => c.color || c.size)
  if (combos.length === 0) return { form, variantRows: [], colores: '', tallas: '', avisos }

  // La matriz es colores × tallas y la PRIMERA fila es la principal: con la
  // principal primero en cada lista, la primera combinación es la suya.
  const colores = unicos(combos.map((c) => c.color))
  const tallas = unicos(combos.map((c) => c.size))
  const porLlave = new Map(combos.map((c) => [llave(c.color, c.size), c]))
  const variantRows: VariantRow[] = []
  let agregadas = 0
  for (const color of colores.length ? colores : ['']) {
    for (const size of tallas.length ? tallas : ['']) {
      const c = porLlave.get(llave(color, size))
      if (!c) agregadas++
      const skuPropio = texto(c?.sku).toUpperCase()
      variantRows.push({
        key: llave(color, size), color, size,
        sku: skuPropio || [sku, ...[color, size].filter(Boolean).map(skuPart)].filter(Boolean).join('-'),
        barcode: '',
        price: numeroTexto(c?.price),
        initial_stock: numeroTexto(c?.initial_stock),
        ...(skuPropio ? { skuTocado: true } : {}),
      })
    }
  }
  if (agregadas > 0) {
    avisos.push(`La matriz agrega ${agregadas} combinación(es) que no venían en la propuesta; nacen sin existencia.`)
  }
  return { form, variantRows, colores: colores.join(', '), tallas: tallas.join(', '), avisos }
}
```

- [ ] **Step 6: Crear `frontend/src/components/ai/TarjetaPropuesta.tsx`**

```tsx
/**
 * Tarjeta de una propuesta del asistente IA (SP4). SOLO LECTURA: Confirmar la
 * aplica en el servidor; "Ajustar en formulario" (solo altas) abre el
 * FormularioProducto prellenado; Descartar la archiva. Las ya resueltas se
 * pintan en gris y sin botones.
 */
import type { EstadoPropuesta, PropuestaIA, TipoPropuesta } from '../../api/ai'
import type { Brand, Department } from '../products/types'
import { formatCurrency } from '../../utils/currency'

type Datos = Record<string, unknown>
interface Fila { color: string; talla: string; existencia: string }

const TITULO: Record<TipoPropuesta, string> = {
  crear_producto: 'Alta de producto',
  agregar_variantes: 'Variantes nuevas',
  ajustar_existencias: 'Ajuste de existencias',
}
export const ETIQUETA_ESTADO: Record<EstadoPropuesta, string> = {
  pendiente: 'Pendiente de confirmar',
  confirmada: 'Confirmada',
  descartada: 'Descartada',
  aplicada_manual: 'Guardada desde el formulario',
  error: 'No se pudo aplicar',
}

const texto = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : String(v))
const piezas = (v: unknown) => String(Number(v ?? 0) || 0)
const lista = (v: unknown): Datos[] => (Array.isArray(v) ? (v as Datos[]) : [])
const nombreDe = (items: { id: string; name: string }[], id: unknown) =>
  id ? items.find((x) => x.id === id)?.name ?? 'No encontrado' : '—'

function Dato({ etiqueta, valor }: { etiqueta: string; valor: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--dax-text-muted)' }}>{etiqueta}</dt>
      <dd className="truncate">{valor}</dd>
    </div>
  )
}

function Combinaciones({ filas }: { filas: Fila[] }) {
  if (filas.length === 0) return null
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-left" style={{ color: 'var(--dax-text-muted)' }}>
          <th className="font-normal py-1">Color</th>
          <th className="font-normal py-1">Talla</th>
          <th className="font-normal py-1 text-right">Existencia</th>
        </tr>
      </thead>
      <tbody>
        {filas.map((f, i) => (
          <tr key={`${f.color}|${f.talla}|${i}`} className="border-t" style={{ borderColor: 'var(--dax-border-dim)' }}>
            <td className="py-1">{f.color}</td>
            <td className="py-1">{f.talla}</td>
            <td className="py-1 text-right tabular-nums">{f.existencia}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function DetalleAlta({ datos, departments, brands }: { datos: Datos; departments: Department[]; brands: Brand[] }) {
  const filas = [datos, ...lista(datos.extra_variants)]
    .filter((x) => x.color || x.size)
    .map((x) => ({ color: texto(x.color), talla: texto(x.size), existencia: piezas(x.initial_stock) }))
  return (
    <>
      <dl className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
        <Dato etiqueta="SKU" valor={texto(datos.sku)} />
        <Dato etiqueta="Departamento" valor={nombreDe(departments, datos.department_id)} />
        <Dato etiqueta="Marca" valor={nombreDe(brands, datos.brand_id)} />
        <Dato etiqueta="Género" valor={texto(datos.gender)} />
        <Dato etiqueta="Precio" valor={formatCurrency(Number(datos.price ?? 0))} />
        <Dato etiqueta="Costo" valor={formatCurrency(Number(datos.cost ?? 0))} />
      </dl>
      <Combinaciones filas={filas} />
    </>
  )
}

export interface TarjetaPropuestaProps {
  propuesta: PropuestaIA
  departments: Department[]
  brands: Brand[]
  ocupada: boolean
  onConfirmar: () => void
  onAjustar: () => void
  onDescartar: () => void
}

export function TarjetaPropuesta({ propuesta: p, departments, brands, ocupada, onConfirmar, onAjustar, onDescartar }: TarjetaPropuestaProps) {
  const activa = p.estado === 'pendiente' || p.estado === 'error'
  const detalle = p.resultado?.detail
  const motivo = p.estado === 'error' && typeof detalle === 'string' ? detalle : null
  const boton = 'text-xs min-h-[44px] sm:min-h-0 justify-center inline-flex items-center gap-1.5'
  return (
    <article className={`dax-card p-3 space-y-2 ${activa ? '' : 'opacity-60'}`} aria-label={`Propuesta: ${TITULO[p.tipo]}`}>
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-bold">{TITULO[p.tipo]}</h3>
        <span className="text-[11px] uppercase tracking-wide" style={{ color: 'var(--dax-text-muted)' }}>
          {ETIQUETA_ESTADO[p.estado]}
        </span>
      </header>
      <p className="text-sm">{p.resumen}</p>
      {p.tipo === 'crear_producto' && <DetalleAlta datos={p.datos} departments={departments} brands={brands} />}
      {p.tipo === 'agregar_variantes' && (
        <Combinaciones filas={lista(p.datos.variantes).map((v) => ({
          color: texto(v.color), talla: texto(v.size), existencia: piezas(v.existencia),
        }))} />
      )}
      {p.avisos.length > 0 && (
        <ul className="text-xs text-amber-400 list-disc pl-4 space-y-0.5">
          {p.avisos.map((a) => <li key={a}>{a}</li>)}
        </ul>
      )}
      {motivo && <p role="alert" className="text-xs text-red-400">{motivo}</p>}
      {activa && (
        <div className="flex flex-col sm:flex-row gap-2 pt-1">
          {p.estado === 'pendiente' && (
            <button type="button" className={`dax-btn-primary ${boton}`} onClick={onConfirmar} disabled={ocupada}>Confirmar</button>
          )}
          {p.tipo === 'crear_producto' && (
            <button type="button" className={`dax-btn-secondary ${boton}`} onClick={onAjustar} disabled={ocupada}>Ajustar en formulario</button>
          )}
          <button type="button" className={`dax-btn-secondary ${boton}`} onClick={onDescartar} disabled={ocupada}>Descartar</button>
        </div>
      )}
    </article>
  )
}
```

- [ ] **Step 7: Crear `frontend/src/components/ai/ChatAsistente.tsx`**

```tsx
/**
 * Chat del asistente IA (SP4). Lo usan la página /ai y el panel de Productos.
 * Enter envía, Shift+Enter salta de línea. Las propuestas se pintan como
 * tarjetas; "Ajustar en formulario" lo resuelve quien monta el chat
 * (`onAjustar`), porque el formulario vive en su propio Modal.
 */
import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { aiApi, textoDeError, type MensajeIA, type PropuestaIA } from '../../api/ai'
import { productsApi } from '../../api/products'
import { toast } from '../../store/toastStore'
import type { Brand, Department, InicialFormulario } from '../products/types'
import { Spinner } from '../ui/Spinner'
import { TarjetaPropuesta } from './TarjetaPropuesta'
import { propuestaAFormulario } from './propuestaAFormulario'

export const TOPE_TEXTO = 4000

export interface ChatAsistenteProps {
  presentacion: 'pagina' | 'drawer'
  conversacionId: string | null
  onConversacion: (id: string) => void
  onAjustar: (propuesta: PropuestaIA, inicial: InicialFormulario, conversacionId: string) => void
  onAplicada?: (propuesta: PropuestaIA) => void
}

function fusionar(actuales: PropuestaIA[], nuevas: PropuestaIA[]): PropuestaIA[] {
  const porId = new Map(actuales.map((p) => [p.id, p]))
  for (const p of nuevas) porId.set(p.id, p)
  return [...porId.values()]
}

function Burbuja({ mensaje }: { mensaje: MensajeIA }) {
  const contenido = mensaje.contenido ?? ''
  if (mensaje.rol === 'evento') {
    return <p className="text-center text-[11px]" style={{ color: 'var(--dax-text-muted)' }}>{contenido}</p>
  }
  const mio = mensaje.rol === 'user'
  return (
    <div className={`flex ${mio ? 'justify-end' : 'justify-start'}`}>
      <p className={`max-w-[85%] whitespace-pre-wrap break-words rounded-lg px-3 py-2 text-sm ${mio ? 'bg-indigo-600/25' : 'dax-card'}`}>
        {contenido}
      </p>
    </div>
  )
}

export function ChatAsistente({ presentacion, conversacionId, onConversacion, onAjustar, onAplicada }: ChatAsistenteProps) {
  const [mensajes, setMensajes] = useState<MensajeIA[]>([])
  const [propuestas, setPropuestas] = useState<PropuestaIA[]>([])
  const [texto, setTexto] = useState('')
  const [pensando, setPensando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ocupada, setOcupada] = useState<string | null>(null)
  const [departments, setDepartments] = useState<Department[]>([])
  const [brands, setBrands] = useState<Brand[]>([])
  // Conversación creada por este mismo chat: no se relee al volver por props
  // (borraría el mensaje que va en camino).
  const propiaRef = useRef<string | null>(null)
  const finRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    productsApi.getDepartments().then(setDepartments).catch(() => {})
    productsApi.getBrands().then(setBrands).catch(() => {})
  }, [])

  const cargar = (id: string) =>
    aiApi.obtener(id)
      .then((c) => { setMensajes(c.mensajes); setPropuestas(c.propuestas) })
      .catch((e) => setError(textoDeError(e, 'No se pudo cargar la conversación.')))

  useEffect(() => {
    if (!conversacionId || conversacionId === propiaRef.current) return
    void cargar(conversacionId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversacionId])

  useEffect(() => { finRef.current?.scrollIntoView?.({ block: 'end' }) }, [mensajes, propuestas, pensando])

  const idActual = () => conversacionId ?? propiaRef.current

  const enviar = async () => {
    const limpio = texto.trim()
    if (!limpio || pensando) return
    setError(null)
    setPensando(true)
    setTexto('')
    const local: MensajeIA = { id: `local-${Date.now()}`, rol: 'user', contenido: limpio, created_at: new Date().toISOString() }
    setMensajes((m) => [...m, local])
    try {
      let id = idActual()
      if (!id) {
        const nueva = await aiApi.crear(limpio.slice(0, 60))
        id = nueva.id
        propiaRef.current = id
        onConversacion(id)
      }
      const r = await aiApi.enviar(id, limpio)
      setMensajes((m) => [...m, r.mensaje])
      setPropuestas((ps) => fusionar(ps, r.propuestas_pendientes))
    } catch (e) {
      setMensajes((m) => m.filter((x) => x.id !== local.id))
      setTexto(limpio)
      setError(textoDeError(e))
    } finally {
      setPensando(false)
    }
  }

  const alTeclear = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void enviar()
    }
  }

  const actuar = async (p: PropuestaIA, accion: 'confirmar' | 'descartar') => {
    const id = idActual()
    if (!id) return
    setOcupada(p.id)
    try {
      const nueva = accion === 'confirmar' ? await aiApi.confirmar(id, p.id) : await aiApi.descartar(id, p.id)
      setPropuestas((ps) => fusionar(ps, [nueva]))
      if (accion === 'confirmar') {
        toast.success('Guardado.')
        onAplicada?.(nueva)
      }
    } catch (e) {
      toast.error(textoDeError(e, 'No se pudo aplicar la propuesta.'))
    } finally {
      setOcupada(null)
      void cargar(id) // trae el aviso "Propuesta aplicada" o el estado de error
    }
  }

  const ajustar = (p: PropuestaIA) => {
    const id = idActual()
    if (!id) return
    const { avisos, ...inicial } = propuestaAFormulario(p.datos, departments, brands)
    avisos.forEach((a) => toast.warning(a))
    onAjustar(p, inicial, id)
  }

  const alto = presentacion === 'drawer' ? 'max-h-[60vh]' : 'min-h-[40vh] max-h-[65vh]'
  return (
    <div className="flex flex-col gap-3">
      <div className={`overflow-y-auto space-y-3 pr-1 ${alto}`} aria-live="polite">
        {mensajes.length === 0 && propuestas.length === 0 && !pensando && (
          <p className="text-sm" style={{ color: 'var(--dax-text-muted)' }}>
            Escribe o pega lo que quieres dar de alta, por ejemplo: «Playera Versace negra, Ch a XL, costo 600,
            venta 1200, 3 piezas en M». También puedes preguntar «¿cuántos Zegna 42 quedan?» o «¿qué vendimos ayer?».
            Nada se guarda sin que lo confirmes.
          </p>
        )}
        {mensajes.map((m) => <Burbuja key={m.id} mensaje={m} />)}
        {propuestas.map((p) => (
          <TarjetaPropuesta key={p.id} propuesta={p} departments={departments} brands={brands} ocupada={ocupada === p.id}
            onConfirmar={() => void actuar(p, 'confirmar')} onDescartar={() => void actuar(p, 'descartar')}
            onAjustar={() => ajustar(p)} />
        ))}
        {pensando && (
          <p className="text-sm flex items-center gap-2" style={{ color: 'var(--dax-text-muted)' }}>
            <Spinner size="sm" /> Pensando…
          </p>
        )}
        <div ref={finRef} />
      </div>
      {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
      <div className="flex flex-col sm:flex-row gap-2">
        <label htmlFor="ai-texto" className="sr-only">Mensaje para el asistente</label>
        <textarea
          id="ai-texto"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={alTeclear}
          rows={presentacion === 'drawer' ? 2 : 3}
          maxLength={TOPE_TEXTO}
          disabled={pensando}
          placeholder="Escribe aquí. Enter envía; Shift+Enter, salto de línea."
          className="dax-input w-full resize-none text-sm"
        />
        <button type="button" onClick={() => void enviar()} disabled={pensando || !texto.trim()}
          className="dax-btn-primary text-xs min-h-[44px] sm:self-end inline-flex items-center justify-center gap-1.5">
          <i className="fa-solid fa-paper-plane" aria-hidden="true" /> Enviar
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 8: Correr las pruebas y el chequeo de tipos**

Run: `cd frontend && npx vitest run src/components/ai`
Expected: PASS (5 + 4 + 5).

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/api/ai.ts frontend/src/components/products/types.ts frontend/src/components/ai
git commit -m "$(cat <<'EOF'
feat(ai): chat del asistente, tarjeta de propuesta y conversión a formulario

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 10: `FormularioProducto` con `inicial`, página `/ai` en su propio chunk

**Files:**
- Modify: `frontend/src/components/products/FormularioProducto.tsx` (import de tipos ~línea 20; props ~línea 36-46; firma ~línea 53; estados ~líneas 66 y 74; init de sucursales ~líneas 87-89; `ProductVariantsSection` ~línea 221)
- Modify: `frontend/src/components/products/__tests__/FormularioProducto.test.tsx` (nuevo `describe` al final)
- Create: `frontend/src/pages/ai/Asistente.tsx`
- Modify: `frontend/src/App.tsx` (línea 100 y línea 377)
- Modify: `frontend/src/pages/__tests__/responsivoOla2.test.ts` (`PAGINAS`, `SIN_TARJETA_FILA`)
- Test: `frontend/src/pages/ai/__tests__/Asistente.test.tsx`, `frontend/src/__tests__/rutaAsistente.test.ts`

**Interfaces:**
- Consumes: `InicialFormulario` (Tarea 9, `components/products/types.ts`); `ChatAsistente`, `aiApi`, `ConversacionResumen`, `PropuestaIA` (Tarea 9); `CabeceraPagina`, `DaxCard`, `Modal` (`components/ui/`); `useEsTelefono` (`hooks/useIsMobile.ts`); `useEnabledModulesStore`; `toast`.
- Produces (Tarea 11):
  - `FormularioProductoProps.inicial?: InicialFormulario` — solo en `mode="create"`, se aplica una vez al montar (form, filas de la matriz, textos de colores/tallas y la sucursal de la existencia marcada en la matriz de sucursales del admin). En edición se ignora.
  - `export function Asistente()` en `pages/ai/Asistente.tsx`, montada en la ruta `ai` con `lazy`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Al final de `frontend/src/components/products/__tests__/FormularioProducto.test.tsx`, agregar:

```tsx
describe('FormularioProducto con `inicial` (asistente IA)', () => {
  it('arranca prellenado y manda la matriz de la propuesta', async () => {
    useEnabledModulesStore.setState({ enabledModules: ['core', 'variants'], loaded: true, camposProducto: { visibles: [], ocultos: [] } } as never)
    api.create.mockResolvedValue({ ...producto, id: 'nuevo' })
    const inicial = {
      form: { name: 'Playera cuello redondo', sku: 'VER-PLAY-CR-NEG-CH', price: '1200', cost: '600', initial_stock: '0', initial_stock_branch_id: '20' },
      colores: 'Negro',
      tallas: 'Ch, M',
      variantRows: [
        { key: 'negro|ch', color: 'Negro', size: 'Ch', sku: 'VER-PLAY-CR-NEG-CH-NEGRO-CH', barcode: '', price: '', initial_stock: '0' },
        { key: 'negro|m', color: 'Negro', size: 'M', sku: 'VER-PLAY-CR-NEG-M', barcode: '', price: '', initial_stock: '3', skuTocado: true },
      ],
    }
    render(<MemoryRouter><FormularioProducto mode="create" presentacion="pagina" inicial={inicial} onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Crear producto')
    expect((screen.getByLabelText(/^Nombre/) as HTMLInputElement).value).toBe('Playera cuello redondo')
    fireEvent.click(screen.getByText('Crear producto'))
    await waitFor(() => expect(api.create).toHaveBeenCalled())
    const payload = api.create.mock.calls[0][0]
    expect(payload).toMatchObject({
      name: 'Playera cuello redondo', sku: 'VER-PLAY-CR-NEG-CH', color: 'Negro', size: 'Ch',
      branch_id: 20, target_branch_ids: [20],
    })
    expect(payload.extra_variants).toEqual([
      expect.objectContaining({ color: 'Negro', size: 'M', sku: 'VER-PLAY-CR-NEG-M', initial_stock: 3 }),
    ])
  })

  it('en edición `inicial` no se usa', async () => {
    api.getById.mockResolvedValue(producto)
    render(<MemoryRouter><FormularioProducto mode="edit" productId="p1" presentacion="pagina"
      inicial={{ form: { name: 'No debe verse' } }} onDone={() => {}} onCancel={() => {}} /></MemoryRouter>)
    await screen.findByText('Guardar cambios')
    expect((screen.getByLabelText(/^Nombre/) as HTMLInputElement).value).toBe('Tenis')
  })
})
```

Crear `frontend/src/pages/ai/__tests__/Asistente.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, cleanup } from '@testing-library/react'

const ai = {
  listar: vi.fn(async () => [] as unknown[]), obtener: vi.fn(), crear: vi.fn(), enviar: vi.fn(),
  confirmar: vi.fn(), descartar: vi.fn(), aplicadaManual: vi.fn(),
}
vi.mock('../../../api/ai', async () => {
  const real = await vi.importActual<typeof import('../../../api/ai')>('../../../api/ai')
  return { ...real, aiApi: ai }
})
vi.mock('../../../api/products', () => ({
  productsApi: { getDepartments: vi.fn(async () => []), getBrands: vi.fn(async () => []) },
}))
vi.mock('../../../store/toastStore', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }))

const { Asistente } = await import('../Asistente')
const { useEnabledModulesStore } = await import('../../../store/enabledModulesStore')

beforeEach(() => vi.clearAllMocks())
afterEach(cleanup)

describe('/ai', () => {
  it('sin el módulo ai explica el plan y no llama a la API', () => {
    useEnabledModulesStore.setState({ enabledModules: ['core'], loaded: true } as never)
    render(<MemoryRouter><Asistente /></MemoryRouter>)
    expect(screen.getByText(/no está incluido en tu plan \(mínimo SCALE\)/)).toBeTruthy()
    expect(ai.listar).not.toHaveBeenCalled()
  })

  it('con el módulo muestra el chat y las conversaciones anteriores', async () => {
    useEnabledModulesStore.setState({ enabledModules: ['core', 'ai'], loaded: true } as never)
    ai.listar.mockResolvedValue([{ id: 'c1', titulo: 'Playeras Versace', created_at: '', updated_at: '' }])
    render(<MemoryRouter><Asistente /></MemoryRouter>)
    expect(await screen.findByText('Playeras Versace')).toBeTruthy()
    expect(screen.getByLabelText('Mensaje para el asistente')).toBeTruthy()
    expect(screen.getByRole('button', { name: /Nueva conversación/ })).toBeTruthy()
  })
})
```

Crear `frontend/src/__tests__/rutaAsistente.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const fuente = (p: string) => readFileSync(resolve(__dirname, '..', p), 'utf8')

describe('/ai va en su propio chunk', () => {
  it('App.tsx carga la página con lazy y nunca de forma estática', () => {
    const app = fuente('App.tsx')
    expect(app).toMatch(/lazy\(\(\) => import\('\.\/pages\/ai\/Asistente'\)/)
    expect(app).toMatch(/<Asistente \/>/)
    expect(app).not.toMatch(/^import .*pages\/ai\//m)
    expect(app).not.toMatch(/^import .*components\/ai\//m)
    expect(app).not.toMatch(/AIComingSoon/)
  })
})
```

En `frontend/src/pages/__tests__/responsivoOla2.test.ts`, reemplazar las dos constantes por:

```ts
/** Pantallas de la ola 2 del responsivo (catálogo y personas). Cada tarea añade la suya.
 *  `ai/Asistente.tsx` (SP4) nace responsiva y entra a la misma guardia. */
export const PAGINAS = ['core/Brands.tsx', 'core/Departments.tsx', 'core/Users.tsx', 'crm/Customers.tsx', 'inventory/Inventory.tsx', 'hq/HQInventory.tsx', 'inventory/Products.tsx', 'core/AdminCatalog.tsx', 'ai/Asistente.tsx']
/** Tienen tarjetas propias o no tienen tabla, y no usan TarjetaFila. */
export const SIN_TARJETA_FILA: string[] = ['core/AdminCatalog.tsx', 'ai/Asistente.tsx']
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `cd frontend && npx vitest run src/components/products/__tests__/FormularioProducto.test.tsx src/pages/ai src/__tests__/rutaAsistente.test.ts src/pages/__tests__/responsivoOla2.test.ts`
Expected: FAIL — el alta con `inicial` encuentra el nombre vacío; `Failed to resolve import "../Asistente"`; `rutaAsistente` no encuentra el `lazy`; `responsivoOla2` falla con `ENOENT … ai/Asistente.tsx`.

- [ ] **Step 3: Agregar la prop `inicial` a `FormularioProducto.tsx`**

En el import de `./types`, reemplazar:

```tsx
  EMPTY_PRODUCT_FORM, type BranchActivation, type Brand, type Branch, type Department,
  type PackagingRow, type PriceRow, type ProductErrors, type ProductFormValue,
} from './types'
```

por:

```tsx
  EMPTY_PRODUCT_FORM, type BranchActivation, type Brand, type Branch, type Department,
  type InicialFormulario, type PackagingRow, type PriceRow, type ProductErrors, type ProductFormValue,
} from './types'
```

En `FormularioProductoProps`, reemplazar:

```tsx
  onDone: (producto: Product) => void
  onCancel: () => void
}
```

por:

```tsx
  onDone: (producto: Product) => void
  onCancel: () => void
  /** Solo en alta: valores con los que arranca (asistente IA → "Ajustar en formulario"). Se aplica una vez al montar. */
  inicial?: InicialFormulario
}
```

Reemplazar la firma:

```tsx
export function FormularioProducto({ mode, productId, variantId, presentacion, onDone, onCancel }: FormularioProductoProps) {
```

por:

```tsx
export function FormularioProducto({ mode, productId, variantId, presentacion, onDone, onCancel, inicial }: FormularioProductoProps) {
```

Reemplazar `  const [form, setForm] = useState<ProductFormValue>(EMPTY_PRODUCT_FORM)` por:

```tsx
  const [form, setForm] = useState<ProductFormValue>(() =>
    mode === 'create' && inicial ? { ...EMPTY_PRODUCT_FORM, ...inicial.form } : EMPTY_PRODUCT_FORM)
```

Reemplazar `  const [variantRows, setVariantRows] = useState<VariantRow[]>([])` por:

```tsx
  const [variantRows, setVariantRows] = useState<VariantRow[]>(() =>
    mode === 'create' && inicial?.variantRows ? inicial.variantRows : [])
```

Reemplazar:

```tsx
        const init: Record<number, BranchActivation> = {}
        for (const b of bchs) init[b.id] = { enabled: false, is_active_pos: true, is_active_hq: false, is_visible: true }
```

por:

```tsx
        // Alta desde el asistente: la sucursal de la existencia ya viene marcada.
        const marcada = mode === 'create' ? Number(inicial?.form.initial_stock_branch_id ?? '') : NaN
        const init: Record<number, BranchActivation> = {}
        for (const b of bchs) init[b.id] = { enabled: b.id === marcada, is_active_pos: true, is_active_hq: false, is_visible: true }
```

Reemplazar:

```tsx
          onPrincipalStockChange={(v) => setField('initial_stock', v)} stockBranchName={sucursalStock?.name ?? null} />
```

por:

```tsx
          onPrincipalStockChange={(v) => setField('initial_stock', v)} stockBranchName={sucursalStock?.name ?? null}
          defaultColors={inicial?.colores ?? ''} defaultSizes={inicial?.tallas ?? ''} />
```

- [ ] **Step 4: Crear `frontend/src/pages/ai/Asistente.tsx`**

```tsx
/**
 * /ai — Asistente IA (SP4): altas por chat y consultas de existencias y
 * ventas. Nada se guarda sin Confirmar. Chunk propio (lazy en App.tsx).
 * Responsiva: en teléfono el historial es un <select> sobre el chat; en
 * escritorio, una columna a la izquierda. Sin tablas: no usa TarjetaFila.
 */
import { useCallback, useEffect, useState } from 'react'
import { aiApi, type ConversacionResumen, type PropuestaIA } from '../../api/ai'
import { ChatAsistente } from '../../components/ai/ChatAsistente'
import { FormularioProducto } from '../../components/products/FormularioProducto'
import type { InicialFormulario } from '../../components/products/types'
import { CabeceraPagina } from '../../components/ui/CabeceraPagina'
import { DaxCard } from '../../components/ui/DaxCard'
import { Modal } from '../../components/ui/Modal'
import { useEsTelefono } from '../../hooks/useIsMobile'
import { useEnabledModulesStore } from '../../store/enabledModulesStore'
import { toast } from '../../store/toastStore'

interface Ajuste { propuesta: PropuestaIA; inicial: InicialFormulario; conversacionId: string }

const TITULO = (
  <div className="flex items-center gap-3">
    <i className="fa-solid fa-microchip text-indigo-400 text-xl" aria-hidden="true" />
    <h1 className="text-2xl font-black">Asistente IA</h1>
  </div>
)
const DESCRIPCION = 'Altas por chat y consultas de existencias y ventas. Nada se guarda sin tu confirmación.'

export function Asistente() {
  const esTelefono = useEsTelefono()
  const { enabledModules, loaded } = useEnabledModulesStore()
  const conModulo = !loaded || enabledModules.includes('ai')
  const [conversaciones, setConversaciones] = useState<ConversacionResumen[]>([])
  const [actual, setActual] = useState<string | null>(null)
  // Cambiar la llave remonta el chat: conversación nueva o relectura tras guardar.
  const [recarga, setRecarga] = useState(0)
  const [ajuste, setAjuste] = useState<Ajuste | null>(null)

  const cargarLista = useCallback(() => {
    aiApi.listar().then(setConversaciones).catch(() => setConversaciones([]))
  }, [])
  useEffect(() => { if (conModulo) cargarLista() }, [conModulo, cargarLista])

  if (!conModulo) {
    return (
      <div className="space-y-5">
        <CabeceraPagina titulo={TITULO} />
        <DaxCard>
          <p className="text-sm">El asistente IA no está incluido en tu plan (mínimo SCALE). La plataforma puede activarlo.</p>
        </DaxCard>
      </div>
    )
  }

  const elegir = (id: string | null) => {
    setActual(id)
    setRecarga((r) => r + 1)
  }

  const alGuardar = async (productoId: string) => {
    if (!ajuste) return
    try {
      await aiApi.aplicadaManual(ajuste.conversacionId, ajuste.propuesta.id, productoId)
    } catch {
      toast.warning('El producto se guardó, pero la propuesta no quedó marcada como aplicada.')
    }
    setAjuste(null)
    setRecarga((r) => r + 1)
  }

  const historial = esTelefono ? (
    <div>
      <label htmlFor="ai-historial" className="dax-label">Conversación</label>
      <select id="ai-historial" className="dax-input w-full min-h-[44px]" value={actual ?? ''}
        onChange={(e) => elegir(e.target.value || null)}>
        <option value="">Nueva conversación</option>
        {conversaciones.map((c) => <option key={c.id} value={c.id}>{c.titulo ?? 'Sin título'}</option>)}
      </select>
    </div>
  ) : (
    <nav aria-label="Conversaciones anteriores" className="space-y-1">
      <p className="text-[10px] font-bold uppercase tracking-widest mb-2" style={{ color: 'var(--dax-text-muted)' }}>Conversaciones</p>
      {conversaciones.length === 0 && (
        <p className="text-xs" style={{ color: 'var(--dax-text-muted)' }}>Aún no hay conversaciones.</p>
      )}
      {conversaciones.map((c) => (
        <button key={c.id} type="button" onClick={() => elegir(c.id)} aria-current={c.id === actual ? 'true' : undefined}
          className={`w-full text-left text-sm truncate rounded-md px-2 py-1.5 ${c.id === actual ? 'bg-indigo-600/20 text-indigo-300' : 'hover:bg-slate-800/60'}`}>
          {c.titulo ?? 'Sin título'}
        </button>
      ))}
    </nav>
  )

  return (
    <div className="space-y-5">
      <CabeceraPagina
        titulo={TITULO}
        descripcion={DESCRIPCION}
        acciones={
          <button type="button" className="dax-btn-secondary text-xs inline-flex items-center gap-1.5" onClick={() => elegir(null)}>
            <i className="fa-solid fa-plus" aria-hidden="true" /> Nueva conversación
          </button>
        }
      />
      <div className="grid grid-cols-1 lg:grid-cols-[15rem_minmax(0,1fr)] gap-4">
        <DaxCard>{historial}</DaxCard>
        <DaxCard>
          <ChatAsistente
            key={recarga}
            presentacion="pagina"
            conversacionId={actual}
            onConversacion={(id) => { setActual(id); cargarLista() }}
            onAjustar={(propuesta, inicial, conversacionId) => setAjuste({ propuesta, inicial, conversacionId })}
          />
        </DaxCard>
      </div>
      {ajuste && (
        <Modal open onClose={() => setAjuste(null)} size="xl" closeOnBackdrop={false} closeOnEscape={false}
          title="Ajustar y guardar el producto">
          <FormularioProducto mode="create" presentacion="modal" inicial={ajuste.inicial}
            onDone={(p) => void alGuardar(p.id)} onCancel={() => setAjuste(null)} />
        </Modal>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Montar la ruta en `frontend/src/App.tsx`**

Reemplazar la línea:

```tsx
const AIComingSoon           = lazy(() => import('./pages/coming-soon').then(m => ({ default: m.AIComingSoon })))
```

por:

```tsx
const Asistente              = lazy(() => import('./pages/ai/Asistente').then(m => ({ default: m.Asistente })))
```

Y la ruta:

```tsx
          <Route path="ai"           element={<RutaPorRol url="/ai"><Suspense fallback={<PageLoader />}><AIComingSoon /></Suspense></RutaPorRol>} />
```

por:

```tsx
          <Route path="ai"           element={<RutaPorRol url="/ai"><Suspense fallback={<PageLoader />}><Asistente /></Suspense></RutaPorRol>} />
```

(`pages/coming-soon/index.tsx` conserva su export `AIComingSoon`; queda sin uso y no se toca.)

- [ ] **Step 6: Correr las pruebas**

Run: `cd frontend && npx vitest run src/components/products/__tests__/FormularioProducto.test.tsx src/pages/ai src/__tests__/rutaAsistente.test.ts src/pages/__tests__/responsivoOla2.test.ts src/__tests__/overlaysFueraDelKit.test.ts`
Expected: PASS.

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/products/FormularioProducto.tsx frontend/src/components/products/__tests__/FormularioProducto.test.tsx \
  frontend/src/pages/ai frontend/src/App.tsx frontend/src/__tests__/rutaAsistente.test.ts frontend/src/pages/__tests__/responsivoOla2.test.ts
git commit -m "$(cat <<'EOF'
feat(ai): página /ai en su propio chunk y FormularioProducto prellenado desde la propuesta

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 11: Integraciones — botón en Productos, instrucciones en Empresa, widget de inicio

**Files:**
- Modify: `frontend/src/pages/inventory/Products.tsx` (imports líneas 1 y 23; estado ~línea 350; `handleSaved` línea 414; acciones de la cabecera ~línea 482; modales al final ~líneas 803-815)
- Modify: `frontend/src/api/organization.ts` (tipo `Organization`)
- Modify: `frontend/src/pages/core/Organization.tsx` (imports, hook ~línea 60, tarjeta nueva antes de `{/* Encabezado y pie de ticket */}` ~línea 394)
- Modify: `frontend/src/pages/home/PresetHome.tsx` (línea 442)
- Test: `frontend/src/__tests__/integracionAsistente.test.ts`, `frontend/src/pages/core/__tests__/OrganizationAsistente.test.tsx`

**Interfaces:**
- Consumes: `ChatAsistente`, `aiApi.aplicadaManual`, `PropuestaIA` (Tarea 9); `InicialFormulario` y la prop `inicial` de `FormularioProducto` (tareas 9 y 10); `useEnabledModulesStore`; `Modal`, `Spinner`; `PUT /api/organization/` con `ai_instrucciones` (Tarea 1).
- Produces: nada que otra tarea consuma (cierre de la UI).

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `frontend/src/__tests__/integracionAsistente.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const fuente = (p: string) => readFileSync(resolve(__dirname, '..', p), 'utf8')

describe('integraciones del asistente IA', () => {
  it('Productos abre el chat en un Modal del kit, perezoso y solo con el módulo ai', () => {
    const s = fuente('pages/inventory/Products.tsx')
    expect(s).toMatch(/lazy\(\(\) => import\('\.\.\/\.\.\/components\/ai\/ChatAsistente'\)/)
    expect(s).not.toMatch(/^import .*components\/ai\/ChatAsistente/m)
    expect(s).toMatch(/enabledModules\.includes\('ai'\)/)
    expect(s).toMatch(/aria-label="Asistente IA"/)
    expect(s).toMatch(/<ChatAsistente[\s\S]*?presentacion="drawer"/)
    expect(s).toMatch(/inicial=\{editor\.mode === 'create' \? editor\.inicial : undefined\}/)
    expect(s).toMatch(/aiApi\.aplicadaManual\(/)
  })

  it('el widget de inicio ya no es beta y dice lo que hace', () => {
    const linea = fuente('pages/home/PresetHome.tsx').split('\n').find((l) => l.includes('title="Copiloto IA"'))!
    expect(linea).toContain('description="Altas por chat y consultas de existencias y ventas."')
    expect(linea).toContain('ctaUrl="/ai"')
    expect(linea).not.toMatch(/\bbeta\b/)
  })
})
```

Crear `frontend/src/pages/core/__tests__/OrganizationAsistente.test.tsx`:

```tsx
// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'

const orgApi = {
  getOrg: vi.fn(async () => ({
    id: 1, name: 'Eleven', tax_id: null, address: null, phone: null, email: null, logo_url: null,
    website: null, ticket_header: null, ticket_footer: null, industry_type: 'ATLAS_POS_BOUTIQUE', ai_instrucciones: null,
  })),
  getBranches: vi.fn(async () => []),
  getExchangeRate: vi.fn(async () => { throw new Error('sin tipo de cambio') }),
  updateOrg: vi.fn(async (o: unknown) => o),
  refreshExchangeRate: vi.fn(),
}
vi.mock('../../../api/organization', () => ({ organizationApi: orgApi }))
vi.mock('../../../store/toastStore', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }))

const { Organization } = await import('../Organization')
const { useEnabledModulesStore } = await import('../../../store/enabledModulesStore')

beforeEach(() => vi.clearAllMocks())
afterEach(cleanup)

describe('Empresa: instrucciones para el asistente IA', () => {
  it('con el módulo ai se editan y se guardan', async () => {
    useEnabledModulesStore.setState({ enabledModules: ['core', 'ai'], loaded: true } as never)
    render(<Organization />)
    const caja = await screen.findByLabelText('Instrucciones para el asistente IA')
    fireEvent.change(caja, { target: { value: 'Si escribo XG es XL.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar instrucciones del asistente' }))
    await waitFor(() => expect(orgApi.updateOrg).toHaveBeenCalledWith(
      expect.objectContaining({ ai_instrucciones: 'Si escribo XG es XL.' }),
    ))
  })

  it('sin el módulo no aparece', async () => {
    useEnabledModulesStore.setState({ enabledModules: ['core'], loaded: true } as never)
    render(<Organization />)
    await screen.findByText('Información de la Empresa')
    expect(screen.queryByLabelText('Instrucciones para el asistente IA')).toBeNull()
  })
})
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `cd frontend && npx vitest run src/__tests__/integracionAsistente.test.ts src/pages/core/__tests__/OrganizationAsistente.test.tsx`
Expected: FAIL — Productos no tiene el `lazy` del chat; el widget sigue con `beta`; Empresa no tiene la caja "Instrucciones para el asistente IA".

- [ ] **Step 3: Productos — botón "Asistente" y panel con el chat**

En `frontend/src/pages/inventory/Products.tsx`, reemplazar la línea 1:

```tsx
import { Fragment, useEffect, useState, useCallback, useRef } from 'react'
```

por:

```tsx
import { Fragment, lazy, Suspense, useEffect, useState, useCallback, useRef } from 'react'
```

Reemplazar `import { cerrarImportacion, debeCerrarSolo } from './importacion'` por:

```tsx
import { cerrarImportacion, debeCerrarSolo } from './importacion'
import { aiApi, type PropuestaIA } from '../../api/ai'
import type { InicialFormulario } from '../../components/products/types'
import { useEnabledModulesStore } from '../../store/enabledModulesStore'

// El chat del asistente va en su propio chunk: Productos no descarga el código
// del asistente hasta que alguien abre el panel.
const ChatAsistente = lazy(() => import('../../components/ai/ChatAsistente').then((m) => ({ default: m.ChatAsistente })))
```

Reemplazar:

```tsx
  const [editor, setEditor] = useState<{ mode: 'create' } | { mode: 'edit'; productId: string } | null>(null)
```

por:

```tsx
  const [editor, setEditor] = useState<
    | { mode: 'create'; inicial?: InicialFormulario; propuestaIA?: { conversacionId: string; propuestaId: string } }
    | { mode: 'edit'; productId: string }
    | null
  >(null)
  // Asistente IA (SP4): panel con el chat; la conversación sigue viva al abrir el formulario.
  const conAsistente = useEnabledModulesStore((s) => s.enabledModules.includes('ai'))
  const [asistente, setAsistente] = useState(false)
  const [conversacionIA, setConversacionIA] = useState<string | null>(null)
```

Reemplazar:

```tsx
  const handleSaved = () => { setEditor(null); load(search, deptId, page) }
```

por:

```tsx
  const handleSaved = (producto?: Product) => {
    // Alta que salió de una propuesta del asistente: queda como "guardada desde el formulario".
    if (producto && editor?.mode === 'create' && editor.propuestaIA) {
      const { conversacionId, propuestaId } = editor.propuestaIA
      aiApi.aplicadaManual(conversacionId, propuestaId, producto.id)
        .catch(() => toast.warning('El producto se guardó, pero la propuesta no quedó marcada como aplicada.'))
    }
    setEditor(null)
    load(search, deptId, page)
  }
  const ajustarDesdeAsistente = (propuesta: PropuestaIA, inicial: InicialFormulario, conversacionId: string) => {
    setAsistente(false)
    setEditor({ mode: 'create', inicial, propuestaIA: { conversacionId, propuestaId: propuesta.id } })
  }
```

En las acciones de la cabecera, justo antes del botón de importar (el bloque que empieza con `<button` y sigue con `onClick={() => setShowImport(true)}`), insertar:

```tsx
                  {conAsistente && (
                    <button
                      onClick={() => setAsistente(true)}
                      aria-label="Asistente IA"
                      className="dax-btn-secondary dax-btn-icon text-xs flex items-center gap-1.5 whitespace-nowrap"
                    >
                      <i className="fa-solid fa-microchip" aria-hidden="true" /> <span className="hidden sm:inline">Asistente</span>
                    </button>
                  )}
```

En el Modal del editor, reemplazar:

```tsx
            productId={editor.mode === 'edit' ? editor.productId : undefined}
```

por:

```tsx
            productId={editor.mode === 'edit' ? editor.productId : undefined}
            inicial={editor.mode === 'create' ? editor.inicial : undefined}
```

Y reemplazar el cierre del archivo:

```tsx
            onCancel={() => setEditor(null)}
          />
        </Modal>
      )}
    </div>
  )
}
```

por:

```tsx
            onCancel={() => setEditor(null)}
          />
        </Modal>
      )}
      {asistente && (
        <Modal open onClose={() => setAsistente(false)} size="lg" closeOnBackdrop={false} title="Asistente IA">
          <Suspense fallback={<div className="flex justify-center py-8"><Spinner size="md" /></div>}>
            <ChatAsistente
              presentacion="drawer"
              conversacionId={conversacionIA}
              onConversacion={setConversacionIA}
              onAjustar={ajustarDesdeAsistente}
              onAplicada={() => load(search, deptId, page)}
            />
          </Suspense>
        </Modal>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Empresa — "Instrucciones para el asistente IA"**

En `frontend/src/api/organization.ts`, dentro de `interface Organization`, tras `  card_surcharge_pct?: number | string`:

```ts
  // Instrucciones para el asistente IA (SP4): tallas, abreviaturas de marca,
  // departamentos. Solo administrador/dueño las cambia.
  ai_instrucciones?: string | null
```

En `frontend/src/pages/core/Organization.tsx`, tras `import { errorDetailText } from '../../utils/errorDetail'`:

```tsx
import { useEnabledModulesStore } from '../../store/enabledModulesStore'

// Mismo tope que `AI_INSTRUCCIONES_MAX` del backend (app/modules/tenants/schemas.py).
const MAX_INSTRUCCIONES_IA = 4000
const EJEMPLO_INSTRUCCIONES = 'https://github.com/Ecamposg95/atlas-one/blob/main/docs/ai/convenciones-altas.md'
```

Tras `  const [fxRefreshing, setFxRefreshing] = useState(false)`:

```tsx
  const conAsistente = useEnabledModulesStore((s) => s.enabledModules.includes('ai'))
```

Y justo antes de `          {/* Encabezado y pie de ticket */}`:

```tsx
          {/* Asistente IA (SP4): solo con el módulo encendido */}
          {conAsistente && (
            <DaxCard>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-4">
                <i className="fa-solid fa-microchip mr-1.5" />Asistente IA
              </p>
              <label htmlFor="ai-instrucciones" className="dax-label">Instrucciones para el asistente IA</label>
              <textarea
                id="ai-instrucciones"
                value={orgForm.ai_instrucciones ?? ''}
                onChange={(e) => setOrgForm((p) => ({ ...p, ai_instrucciones: e.target.value || null }))}
                rows={8}
                maxLength={MAX_INSTRUCCIONES_IA}
                className="dax-input w-full font-mono text-xs"
                placeholder={'Tallas de ropa: Ch, M, G, XL (si escribo XG es XL).\nMAM = Maison Margiela, BLC = Balenciaga.\nCamisa y camisola son departamentos distintos.'}
              />
              <div className="flex items-start justify-between gap-3 mt-1">
                <p className="text-[10px] text-slate-600">
                  Lo que el asistente debe saber de tu tienda para dar de alta productos.{' '}
                  <a href={EJEMPLO_INSTRUCCIONES} target="_blank" rel="noreferrer" className="underline">Ver ejemplo</a>
                </p>
                <p className="text-[10px] text-slate-600 tabular-nums whitespace-nowrap">
                  {(orgForm.ai_instrucciones ?? '').length}/{MAX_INSTRUCCIONES_IA}
                </p>
              </div>
              <div className="flex justify-end mt-4">
                <button onClick={saveOrg} disabled={saving || nameInvalido} aria-label="Guardar instrucciones del asistente"
                  className="dax-btn-primary text-xs disabled:opacity-40">
                  {saving ? <i className="fa-solid fa-spinner fa-spin" /> : <><i className="fa-solid fa-check" /> Guardar</>}
                </button>
              </div>
            </DaxCard>
          )}

```

- [ ] **Step 5: Widget "Copiloto IA" en `frontend/src/pages/home/PresetHome.tsx`**

Reemplazar:

```tsx
      <Widget module="ai" icon="fa-microchip" title="Copiloto IA" description="Predicciones, automatizaciones y resúmenes." cta="Abrir IA" ctaUrl="/ai" beta />
```

por:

```tsx
      <Widget module="ai" icon="fa-microchip" title="Copiloto IA" description="Altas por chat y consultas de existencias y ventas." cta="Abrir IA" ctaUrl="/ai" />
```

- [ ] **Step 6: Correr las pruebas**

Run: `cd frontend && npx vitest run src/__tests__/integracionAsistente.test.ts src/pages/core/__tests__/OrganizationAsistente.test.tsx src/pages/inventory src/__tests__/overlaysFueraDelKit.test.ts src/pages/__tests__/responsivoOla2.test.ts`
Expected: PASS (el inventario de `fixed inset-0` no cambia: Productos sigue en 1, Empresa en 1).

Run: `cd frontend && npx tsc --noEmit`
Expected: sin errores.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/inventory/Products.tsx frontend/src/api/organization.ts frontend/src/pages/core/Organization.tsx \
  frontend/src/pages/home/PresetHome.tsx frontend/src/__tests__/integracionAsistente.test.ts \
  frontend/src/pages/core/__tests__/OrganizationAsistente.test.tsx
git commit -m "$(cat <<'EOF'
feat(ai): asistente en Productos, instrucciones en Empresa y widget de inicio

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

---

### Task 12: Documentación, `.env.example` y verificación final

**Files:**
- Create: `docs/ai/README.md`, `.env.example`
- Modify: `docs/API_REFERENCE.md` (nueva sección antes de `## Stubs / Beta`, ~línea 215; quitar `/api/ai` de los stubs)
- Modify: `docs/FRONTEND_VIEWS.md` (fila de la tabla ~línea 81; sección ~línea 636)
- Modify: `docs/DEPLOY.md` (§6, ~línea 97)

**Interfaces:**
- Consumes: todo lo anterior (nombres de variables, rutas, estados, textos de error).
- Produces: nada de código.

- [ ] **Step 1: Crear `docs/ai/README.md`**

````markdown
# Asistente IA (SP4)

Chat en `/ai` (y en Productos → botón **Asistente**) para dar de alta productos y consultar
existencias y ventas. El asistente **propone**: cada alta, variante nueva o ajuste de existencias
llega como tarjeta y **nada se guarda hasta que la persona pulsa Confirmar** (o lo ajusta y guarda en
el formulario). Diseño: `docs/superpowers/specs/2026-10-18-sp4-asistente-ia-design.md`. Plan:
`docs/superpowers/plans/2026-10-18-sp4-asistente-ia.md`.

## 1. Configurar el proveedor

Cualquier API compatible con OpenAI (`POST {LLM_BASE_URL}/chat/completions` con `tools`). Sin SDK:
`httpx`. Las variables van en el `env_file` del `docker-compose.yml` del servidor (ver
`docs/DEPLOY.md` §6) y se leen en cada petición; basta reiniciar el contenedor.

| Variable | Por defecto | Qué es |
|---|---|---|
| `LLM_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` | Capa compatible con OpenAI de Gemini |
| `LLM_MODEL` | `gemini-3.8-flash` | Modelo con *tool calling* |
| `LLM_API_KEY` | (vacía) | Clave del proveedor. Sin ella: 503 `Asistente no configurado: falta LLM_API_KEY en el servidor.` |
| `AI_TOKENS_DIA_ORG` | `200000` | Tope de tokens (entrada + salida) por organización y día |

Gemini: crea la clave en Google AI Studio, pégala en `LLM_API_KEY` y reinicia. `GET /api/ai/health`
responde `ready: true` cuando hay clave.

**Aviso de datos.** En el nivel gratuito, Google **usa el contenido de las peticiones para mejorar sus
productos**. Por eso el asistente no lee clientes ni usuarios: el prompt lleva departamentos, marcas,
sucursales y las instrucciones de la tienda; `buscar_ventas` puede filtrar por nombre del cliente pero
nunca lo devuelve. Para clientes que no acepten esto, usa un proveedor de pago.

**Cambiar de proveedor.** Groq (`https://api.groq.com/openai/v1`), Mistral (`https://api.mistral.ai/v1`)
u OpenAI (`https://api.openai.com/v1`): cambia las tres variables `LLM_*` y elige un modelo de su
catálogo que soporte *tool calling*. No hay código que tocar.

Errores del proveedor: 429 → 503 "alcanzó su límite de uso" (no se reintenta); 5xx o timeout → un
reintento y luego 503; 401/400 → 503 "Revisa LLM_API_KEY y LLM_MODEL".

## 2. Activar el módulo a una organización

El módulo `ai` viene en los planes **SCALE** y **ULTRA+** (`app/services/plans.py`). Desde la plataforma
(`/platform/organizations/{id}` → Módulos) se enciende a mano en cualquier otra. El gate **no tiene
excepción para administrador ni dueño** (`app/modules/ai/gating.py::exigir_modulo_ai`): sin el módulo,
`403` con `"El asistente IA no está incluido en tu plan (mínimo SCALE). La plataforma puede activarlo."`

La pantalla `/ai` la ven ADMINISTRADOR y DUEÑO (`navConfig.ts`). El backend acepta también a GERENTE y
CAJERO con sus límites: solo su sucursal y, para altas y variantes, con el módulo `catalog` encendido.

## 3. Instrucciones de la tienda

- **Convenciones del giro:** `app/modules/ai/prompts/boutique.md` (para `ATLAS_POS_BOUTIQUE`) es copia
  literal de la Parte 1 de `docs/ai/convenciones-altas.md`; `tests/test_ai_prompt.py` falla si se
  separan. Si cambias el doc, vuelve a copiar (comando en la Tarea 3 del plan).
- **Convenciones de la tienda:** Empresa → **Instrucciones para el asistente IA** (hasta 4000
  caracteres, solo administrador/dueño). Ejemplo listo para Eleven: Parte 2 de `docs/ai/convenciones-altas.md`.
- Reglas fijas que el dueño no puede quitar (`prompts/base.md`): nada se guarda sin confirmación; no
  inventar precio ni costo; una propuesta por producto; solo ids que vengan del sistema.

## 4. Qué puede hacer

| Herramienta | Tipo | Notas |
|---|---|---|
| `listar_departamentos`, `listar_marcas` | lectura | solo de la organización |
| `buscar_producto` | lectura | misma visibilidad que la pantalla de Productos |
| `sugerir_sku` | lectura | convención `MARCA-PRENDA-MODELO-GENERO-COLOR-TALLA`; si está ocupado sugiere `-2` |
| `consultar_existencias` | lectura | admin/dueño toda la tienda; gerente/cajero su sucursal |
| `resumen_ventas`, `buscar_ventas` | lectura | mismas reglas de sucursal; periodo ≤ 92 días; ≤ 20 ventas |
| `proponer_cambio` | propuesta | `crear_producto` (= `ProductCreate` de SP1), `agregar_variantes`, `ajustar_existencias`; valida en seco y deja la propuesta **pendiente** |

Al confirmar se usa el servicio de altas de SP1 (`crear_producto`, `crear_variantes`,
`fijar_existencia` con referencia de kárdex "Asistente IA") y queda en `platform_audit_log`:
`AI_PROPUESTA_APLICADA` (con `payload.source = "ai"`) y `PRODUCT_CREATE_AI` por producto creado.

Estados de una propuesta: `pendiente` → `confirmada` | `descartada` | `aplicada_manual` (guardada desde
el formulario) | `error` (SP1 la rechazó al confirmar; la tarjeta muestra el motivo y deja Ajustar o
Descartar).

## 5. Cuotas y costo

- Topes por turno: 8 herramientas, 60 s, 30 mensajes de historial, 4000 caracteres por mensaje.
- Uso por organización y día en `ai_uso_diario`; al llegar a `AI_TOKENS_DIA_ORG`, `429` antes de llamar
  al proveedor. Consulta rápida:

  ```sql
  SELECT fecha, tokens_entrada, tokens_salida, llamadas
  FROM ai_uso_diario WHERE organization_id = 17 ORDER BY fecha DESC LIMIT 14;
  ```
- Las cuotas gratuitas del proveedor cambian; revisa su página de límites antes de abrir el módulo a
  más tiendas.

## 6. Verificación en producción (manual)

1. Poner `LLM_API_KEY` en el `env_file` y reiniciar; `GET /api/ai/health` → `ready: true`.
2. Encender `ai` a Eleven desde la plataforma y pegar sus instrucciones en Empresa.
3. Dar de alta un lote real por chat y confirmar; revisar en Productos y en `platform_audit_log`.
4. Con un admin de una organización FREE: `POST /api/ai/conversaciones` → `403` con el plan mínimo.
````

- [ ] **Step 2: Crear `.env.example`**

```bash
# Asistente IA (SP4) — cualquier API compatible con OpenAI (/chat/completions con tools).
# Por defecto Gemini Flash en su capa compatible. Sin LLM_API_KEY el asistente responde 503.
# Ver docs/ai/README.md (incluye el aviso de uso de datos del nivel gratuito de Google).
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_MODEL=gemini-3.8-flash
LLM_API_KEY=
# Tope de tokens (entrada + salida) por organización y día.
AI_TOKENS_DIA_ORG=200000
```

- [ ] **Step 3: `docs/API_REFERENCE.md`**

Justo antes de la línea `## Stubs / Beta (solo \`GET /health\`, \`ready:false\`)`, insertar:

```markdown
## Asistente IA · `/api/ai` `[module:ai, sin excepción para admin/dueño]` (SP4, 2026-10)
Gate `exigir_modulo_ai`: sin `organization_modules.ai` → 403 `"El asistente IA no está incluido en tu plan (mínimo SCALE). La plataforma puede activarlo."`. Cada conversación es del usuario que la creó (otra → 404).

| Método | Ruta | Respuesta |
|---|---|---|
| GET | /health | `{"module":"ai","status":"beta","ready":bool}` (solo auth; `ready` = hay `LLM_API_KEY`) |
| GET | /conversaciones | las 20 más recientes del usuario: `[{id, titulo, created_at, updated_at}]` |
| POST | /conversaciones `{titulo?}` | 201 `{id, titulo, created_at, updated_at}` |
| GET | /conversaciones/{id} | `{…, mensajes:[{id, rol: user\|assistant\|evento, contenido, created_at}], propuestas:[Propuesta]}` |
| POST | /conversaciones/{id}/mensajes `{texto: 1..4000}` | `{mensaje, propuestas_pendientes:[Propuesta]}`. Síncrono: el bucle LLM ⇄ herramientas corre completo (≤ 8 herramientas, 60 s). 429 cuota diaria (`AI_TOKENS_DIA_ORG`), 503 proveedor o sin `LLM_API_KEY` |
| POST | /conversaciones/{id}/propuestas/{pid}/confirmar | `Propuesta` confirmada; **única escritura**: SP1 (`crear_producto`/`crear_variantes`/`fijar_existencia`) + `platform_audit_log` (`AI_PROPUESTA_APLICADA`, `PRODUCT_CREATE_AI`). 409 si ya no está pendiente; 4xx de SP1 → la propuesta queda `error` con `resultado.detail`; 403 de permiso la deja pendiente |
| POST | /conversaciones/{id}/propuestas/{pid}/descartar | `Propuesta` descartada (desde pendiente o error) |
| POST | /conversaciones/{id}/propuestas/{pid}/aplicada-manual `{producto_id?}` | `Propuesta` `aplicada_manual` (se guardó desde el formulario) |

`Propuesta` = `{id, tipo: crear_producto|agregar_variantes|ajustar_existencias, datos, estado: pendiente|confirmada|descartada|aplicada_manual|error, resumen, avisos[], resultado, created_at}`. `datos` de `crear_producto` es `ProductCreate`. Proveedor y variables: `docs/ai/README.md`.

```

Y en la sección de stubs, reemplazar `` `/api/commissions`, `/api/memberships`, `/api/ai`, `/api/purchasing`. `` por `` `/api/commissions`, `/api/memberships`, `/api/purchasing`. ``

- [ ] **Step 4: `docs/FRONTEND_VIEWS.md`**

Reemplazar la fila:

```markdown
| `/appointments`, `/commissions`, `/memberships`, `/ai`, `/purchasing` | `coming-soon/index` | según módulo | (stubs) |
```

por:

```markdown
| `/ai` | `ai/Asistente` | Admin / Dueño | ai (gate estricto) |
| `/appointments`, `/commissions`, `/memberships`, `/purchasing` | `coming-soon/index` | según módulo | (stubs) |
```

Reemplazar el encabezado `### \`/appointments\`, \`/commissions\`, \`/memberships\`, \`/ai\`, \`/purchasing\` — "Próximamente"` por `### \`/appointments\`, \`/commissions\`, \`/memberships\`, \`/purchasing\` — "Próximamente"` y agregar antes de él:

```markdown
### `/ai` — Asistente IA (SP4)
- **Archivo:** `pages/ai/Asistente.tsx` (chunk propio, `lazy` en `App.tsx`). Chat `components/ai/ChatAsistente.tsx` + tarjetas `components/ai/TarjetaPropuesta.tsx`; historial en columna (escritorio) o `<select>` (teléfono). Sin el módulo `ai` explica el plan mínimo.
- **API:** `/api/ai/conversaciones*` (ver `API_REFERENCE.md`). "Ajustar en formulario" abre `FormularioProducto` (modo alta) con `inicial` armado por `components/ai/propuestaAFormulario.ts`; al guardar marca la propuesta `aplicada_manual`.
- **También en:** Productos (botón **Asistente** → `ui/Modal` con el chat, cargado perezoso) y Empresa (textarea **Instrucciones para el asistente IA** → `organization.ai_instrucciones`).

```

- [ ] **Step 5: `docs/DEPLOY.md` §6**

Al final de la sección `## 6. Variables de entorno en producción` (antes de `## 7. Qué NO cambió`), agregar:

```markdown

**Asistente IA (SP4, 2026-10):** `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` y `AI_TOKENS_DIA_ORG`
(plantilla en `.env.example`, detalle y aviso de uso de datos en `docs/ai/README.md`). Sin
`LLM_API_KEY` todo arranca igual y `/api/ai/*/mensajes` responde 503 "Asistente no configurado". El
despliegue agrega la columna `organization.ai_instrucciones` (`railway_init.py`) y cuatro tablas
`ai_*` (`create_all`); no hay migración manual. Los prompts `app/modules/ai/prompts/*.md` viajan en la
imagen (`.dockerignore` los exceptúa de `*.md`).
```

- [ ] **Step 6: Verificación completa**

Run: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py 2>&1 | tail -3`
Expected: la misma cantidad de `failed` que la línea base anotada en "Antes de empezar" (cero fallos nuevos) y todas las `tests/test_ai_*.py` verdes.

Run: `cd frontend && npx vitest run 2>&1 | tail -5`
Expected: `Test Files … passed`, sin fallos.

Run: `cd frontend && npm run build`
Expected: `tsc` sin errores y `vite build` termina con `✓ built in …`.

Run: `ls frontend/dist/assets | grep -E '^Asistente-.*\.js$' && grep -l "Mensaje para el asistente" frontend/dist/assets/*.js`
Expected: existe `Asistente-<hash>.js`; el texto del chat aparece solo en chunks del asistente (`Asistente-*.js` o `ChatAsistente-*.js`), **nunca** en `index-*.js` ni en `POS-*.js`.

Run: `python3 scripts/presupuesto_bundle.py --dist frontend/dist --presupuesto frontend/presupuesto_bundle.json`
Expected: código de salida 0; el medido queda por debajo de `tope_bytes` (452500) y no cambia respecto a la línea base (la ruta crítica no carga nada del asistente). `frontend/presupuesto_bundle.json` no se edita.

- [ ] **Step 7: Commit**

```bash
git add docs/ai/README.md .env.example docs/API_REFERENCE.md docs/FRONTEND_VIEWS.md docs/DEPLOY.md
git commit -m "$(cat <<'EOF'
docs(ai): guía del asistente, variables LLM_* y referencia de /api/ai y /ai

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GrtNxw21eDzCu5rRSFgaDf
EOF
)"
```

- [ ] **Step 8: Entrega**

No hacer push ni merge. Reportar al usuario: rama `feat/sp4-asistente-ia`, commits de las 12 tareas, conteos de pytest/vitest contra la línea base, tamaño medido del presupuesto, y los pasos manuales de producción de `docs/ai/README.md` §6 (clave, módulo a Eleven, instrucciones, lote real, 403 en una org FREE).
