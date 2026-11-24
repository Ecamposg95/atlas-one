# IA en Atlas ONE: cimientos (fase A0)

Qué hay debajo de todo lo que usa un modelo: Cargar mercancía hoy
([`cargar-mercancia.md`](cargar-mercancia.md)), el agente conversacional después (fase A1).
Plan general: `docs/superpowers/specs/2026-11-24-megaplan-pendientes-y-agente-design.md §5`.
Variables de entorno: [`../DEPLOY.md §6`](../DEPLOY.md).

## 1. Piezas

```
app/modules/ai/
  proveedores/          interfaz única + implementaciones
    base.py             Proveedor (protocolo), Respuesta, RespuestaJSON, LlamadaHerramienta, errores
    anthropic_nativo.py ProveedorAnthropic (SDK oficial, streaming)
    openai_compatible.py ProveedorOpenAI (httpx; Gemini, Groq, Mistral, OpenAI…)
    respaldo.py         ProveedorConRespaldo (lista ordenada)
    falso.py            ProveedorFalso (pruebas)
  tareas.py             qué modelo atiende cada tarea; proveedor_para(db, org_id, tarea)
  uso.py                cupo (verificar_cupo) y consumo (registrar_uso, Medidor)
  gating.py             exigir_modulo_ai: candado de módulo sin pase libre de administrador
  models.py             ai_conversations, ai_messages, ai_propuestas, ai_uso_diario, ai_llamadas
  herramientas*.py, prompt.py, historial.py   piezas del chat (SP4), aún sin endpoint
```

Regla: **nadie importa un cliente concreto**. El código de negocio pide
`proveedor_para(db, org_id, tarea)` y habla con el protocolo `Proveedor`.

## 2. La interfaz

```python
class Proveedor(Protocol):
    nombre: str
    modelo: str
    def conversar(self, *, mensajes: list[dict], herramientas: list[dict] | None = None,
                  max_tokens: int = 16000) -> Respuesta: ...
    def generar_json(self, *, sistema: str, contenido: list[dict], esquema: dict,
                     max_tokens: int = 64000, latido: Callable[[], None] | None = None) -> RespuestaJSON: ...
```

- `conversar`: un turno sobre el historial; devuelve `texto`, `tool_calls`
  (`LlamadaHerramienta`), `tokens_entrada`, `tokens_salida`, y `proveedor`/`modelo` de quien
  contestó. No ejecuta herramientas: eso es del motor del chat (A1).
- `generar_json`: salida estructurada que cumple un JSON Schema; devuelve `datos` y los mismos
  contadores.
- Formato canónico (el de `ai_messages`): mensajes y herramientas estilo OpenAI; contenido de
  `generar_json` en bloques `text` / `document` (base64). Cada implementación traduce al suyo.
- `Respuesta.nativo` / `Respuesta.mensaje_asistente()`: Anthropic exige reenviar sus bloques
  de razonamiento sin tocar. Quien arme el ciclo de herramientas debe agregar al historial
  `respuesta.mensaje_asistente()` (trae `nativo`), no reconstruir el mensaje a mano; los demás
  proveedores ignoran ese campo. **A1 tiene que guardar `nativo` junto al mensaje** (hoy
  `ai_messages` no tiene esa columna).
- Errores: `ProveedorNoDisponible(recuperable=…)` y `RespuestaIncompleta` (salida cortada por
  `max_tokens`). `recuperable=True` = red, 5xx o cuota del proveedor.

## 3. Tareas y modelos

Tres tareas: `consulta` (precio, existencia), `captura` (altas, documentos), `analisis`
(reportes). Cada una tiene una lista ordenada de `proveedor:modelo`; se usa la primera entrada
con llave y, si falla de forma recuperable, la siguiente. Un rechazo del modelo, una respuesta
cortada o un 4xx **no** pasan al siguiente.

| Prioridad | Dónde | Formato |
|---|---|---|
| 1 | `organization.ai_modelos` (JSON; lo guarda `PUT /api/platform/organizations/{id}`) | `{"consulta": ["compatible:gemini-3.8-flash", "anthropic:claude-haiku-5-5"]}` |
| 2 | `AI_MODELOS_CONSULTA` / `AI_MODELOS_CAPTURA` / `AI_MODELOS_ANALISIS` | `anthropic:claude-haiku-5-5,compatible:gemini-3.8-flash` |
| 3 | Por omisión | `consulta` → `anthropic:claude-haiku-5-5`; `captura` y `analisis` → `anthropic:claude-opus-5-5` |

Proveedores: `anthropic` (`ANTHROPIC_API_KEY`); `compatible` (`LLM_BASE_URL`, `LLM_API_KEY`,
`LLM_MODEL` si la entrada no nombra modelo; por omisión la capa compatible de Gemini); y
cualquier otro nombre `x`, también compatible con OpenAI, con `AI_PROVEEDOR_X_BASE_URL` y
`AI_PROVEEDOR_X_API_KEY`. Una entrada sin llave se salta; si no queda ninguna, 503
"IA no configurada: falta … en el servidor."

Modelos gratuitos: permitidos por decisión del dueño, sabiendo que el proveedor puede usar el
contenido (Gemini en su nivel gratuito lo hace). Lo que se le manda sale de la tienda.

## 4. Cupo y consumo

- **Cupo** = tokens de entrada + salida por organización y día de negocio. Orden:
  `organization.ai_tokens_dia` (excepción, plataforma) → `AI_TOKENS_DIA_ORG` (si está puesta,
  tope global) → `plans.CUPO_IA_TOKENS_DIA[plan]`. El valor por plan es **provisional**
  (2 000 000, igual para todos): la cifra final sale de medir consumo real en A1.
- Tope por persona, opcional: `AI_TOKENS_DIA_USUARIO`.
- `verificar_cupo(db, org_id, user_id)` responde 429 **antes** de llamar. Es una comprobación
  previa: la llamada que cruza el tope pasa y la siguiente ya no.
- `registrar_uso` / `registrar_llamadas` escriben una fila por llamada en `ai_llamadas`
  (organización, usuario, rol, tarea, proveedor, modelo, tokens) y suman a `ai_uso_diario` con
  un UPSERT atómico (`ON CONFLICT … DO UPDATE SET x = x + …`), sin leer la fila antes.
- Consumo por rol de la última semana:

```sql
SELECT rol, tarea, modelo, count(*) AS llamadas,
       sum(tokens_entrada) AS entrada, sum(tokens_salida) AS salida
FROM ai_llamadas WHERE fecha >= current_date - 7
GROUP BY rol, tarea, modelo ORDER BY entrada + salida DESC;
```

## 5. Plan comercial y candado

`ai` viene incluido en SCALE (y ULTRA+ permite todo); la plataforma puede encenderlo a mano en
otra organización y entonces aparece como "Fuera de plan". Todo endpoint de IA depende de
`exigir_modulo_ai`: lee `organization_modules` y no deja pasar a ADMIN/DUEÑO sin el módulo
(a diferencia de `require_module`).

## 6. Bitácora

Toda escritura aplicada por IA deja fila en `platform_audit_log` dentro de la misma transacción.
Hoy: `CARGA_APLICADA` (una por carga autorizada; `payload` con `organization_id`, `carga_id`,
`folio`, `rol`, `totales`, `source: "ai"`) y `CARGA_PRECIO_ACTUALIZADO` (una por precio
cambiado). Las propuestas del agente (A2) deben seguir el mismo patrón.

## 7. Cómo añadir un modelo o un proveedor

- **Otro modelo de un proveedor que ya existe:** no hay código. Ponlo en la variable de la
  tarea (`AI_MODELOS_CONSULTA=anthropic:claude-haiku-5-5,compatible:otro-modelo`) o en
  `ai_modelos` de una organización, y reinicia el contenedor si fue variable.
- **Otro servicio compatible con OpenAI** (Groq, Mistral…): define
  `AI_PROVEEDOR_GROQ_BASE_URL` y `AI_PROVEEDOR_GROQ_API_KEY` y úsalo como `groq:<modelo>`.
- **Un proveedor con API propia:** clase nueva en `proveedores/` que cumpla `Proveedor`
  (mismas firmas, llenar `proveedor`/`modelo` en la respuesta, marcar `recuperable` en red,
  5xx y cuota), exportarla en `proveedores/__init__.py` y darle una rama en
  `tareas.construir` y `tareas.variable_de_llave`. Pruebas con el SDK sustituido, como
  `tests/test_ai_proveedor_anthropic.py`.

## 8. Pruebas

`tests/test_ai_proveedor_anthropic.py`, `test_ai_proveedor_openai.py`, `test_ai_tareas_cupo.py`,
`test_ai_uso_gating.py`, `test_cargas_*.py`. Ninguna sale a la red: `ProveedorFalso`,
`httpx.MockTransport` o el SDK sustituido.
