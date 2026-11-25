# Cargar mercancía con IA — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pantalla "Cargar mercancía". El usuario sube un PDF (pedimento) o un Excel, revisa un plan con dudas numeradas, las contesta en texto libre o con botones, autoriza, y todo se aplica en una transacción con su lista de etiquetas.

**Architecture:** Módulo nuevo `app/modules/cargas/`. La IA (SDK `anthropic`, salida JSON estructurada) solo hace tres cosas:
- extraer renglones de un PDF;
- mapear los encabezados de un Excel;
- traducir respuestas en texto libre a operaciones.

Todo lo demás es código determinista, generalizado del `hoja_plan.py` del operador:
- normalizar tallas y armar SKU;
- clasificar cada renglón en EXISTE / SUMA / NUEVO / YA CARGADO;
- generar las dudas;
- aplicar.

La lectura corre en un hilo de fondo y la pantalla consulta el estado.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, `anthropic` (Python SDK), `openpyxl`, `pypdf`, React + Vite + TS, vitest, pytest (SQLite en memoria).

**Spec:** `docs/superpowers/specs/2026-11-14-cargar-mercancia-ia-design.md` (leer completo, sobre todo §5, §6, §10).

## Global Constraints

- Repo público: **ningún dato de una tienda** (marcas, precios, SKU reales) en código, pruebas ni docs. Las pruebas usan marcas inventadas ("Marca Uno", "Casa Dos").
- Modelo `claude-opus-5-5` por omisión. Variable `AI_MODELO`; clave `ANTHROPIC_API_KEY`. Fallback server-side `fallbacks: "default"` con beta `server-side-fallback-2026-07-01`.
- La suite **nunca** llama al proveedor: `ClienteEstructuradoFalso`.
- FKs a tablas con PK UUID = `String(36)`. Estados como `String` con constantes Python, no enums de Postgres.
- Columnas nuevas en tablas existentes: ALTER idempotente en `scripts/railway_init.py`. Tablas nuevas: registro en `app/models/__init__.py`.
- Toda query filtra `organization_id`. El `org_id` sale del contexto autenticado, nunca del modelo.
- Nada se escribe en catálogo ni existencias fuera de `aplicar_carga`. `aplicar_carga` corre solo desde el endpoint `autorizar`, solo para ADMINISTRADOR/DUEÑO y solo sin dudas abiertas.
- Un precio solo sale de una celda asignada por el usuario, del PDF o de una respuesta del usuario. Nunca de otro renglón ni del modelo por su cuenta.
- Costo = costo unitario × tipo de cambio de su moneda. Si falta, se aplica `reglas_carga.costo_si_falta`: `preguntar` → duda, `fraccion_precio` → precio × fracción.
- Kardex de la carga: `reference = "carga:<id>"`, `notes = "Carga #<folio> · <archivo_nombre>"`.
- Gate estricto `exigir_modulo_ai` (sin bypass de admin), 403 con el plan mínimo en `detail`.
- Topes: archivo ≤ 20 MB, ≤ 2,000 renglones, tope diario de tokens `AI_TOKENS_DIA_ORG` (existente).
- Frontend: kit `components/ui/`, `useEsTelefono`, colores por tokens `dax-*`, `grid-cols-N` siempre con prefijo, modales con `ui/Modal`, botones `dax-btn-*`.
- Pytest siempre con `--ignore=tests/test_cash_complete.py`. Una sola corrida de pytest a la vez en este worktree.

## Review Focus

- **PDF escaneado o con renglones partidos entre páginas.** La extracción por bloques no debe duplicar ni perder el renglón del corte → prueba en Task 4.
- **Mismo archivo subido dos veces, o el mismo contenido renombrado.** Debe salir YA CARGADO, no sumar otra vez. Un archivo distinto con renglones ya aplicados en los últimos 14 días también → prueba en Task 6.
- **Respuesta del usuario que el modelo interpreta con ids o campos inventados.** La operación se rechaza y vuelve como "no entendí el punto N", sin tocar el plan → prueba en Task 8.
- **Falla a media aplicación** (SKU que choca, existencia negativa, marca duplicada por concurrencia). No queda nada escrito, la carga pasa a `error` con detalle y se puede reintentar → prueba en Task 9.
- **El proceso se reinicia mientras una carga está en `leyendo`.** No debe quedarse colgada para siempre: al arrancar se marca `error` "Vuelve a intentar" → prueba en Task 10.

---

## File Structure

```
app/modules/ai/
  cliente_anthropic.py   # ClienteEstructurado (protocolo), ClienteAnthropic, ClienteEstructuradoFalso
  uso.py                 # verificar_cupo, registrar_uso (AiUsoDiario)
  gating.py              # exigir_modulo_ai
app/modules/cargas/
  __init__.py
  models.py              # CargaMercancia, CargaArchivo, CargaRenglon, CargaDuda, CargaCambio
  reglas.py              # ReglasCarga (Pydantic) + reglas_de_la_org()
  tipos.py               # RenglonCrudo, RenglonPlan, DudaNueva, Operacion (dataclasses/Pydantic)
  lectura_excel.py       # leer_tabla, mapear_columnas, renglones_desde_excel
  extraccion_pdf.py      # extraer_pdf
  normalizar.py          # normalizar_renglon, agrupar, sku_para_grupo, prefijo_de_marca
  cruce.py               # cruzar_con_catalogo, marcar_ya_cargado
  dudas.py               # generar_dudas, opciones_a_operaciones
  operaciones.py         # aplicar_operaciones, deshacer_cambio
  respuestas.py          # interpretar_respuesta
  aplicar.py             # aplicar_carga
  proceso.py             # procesar_carga (hilo), recuperar_cargas_colgadas
  schemas.py             # respuestas HTTP
  router.py              # /api/cargas
frontend/src/api/cargas.ts
frontend/src/pages/inventory/cargas/Cargas.tsx        # lista + subida
frontend/src/pages/inventory/cargas/CargaPlan.tsx     # plan, dudas, respuesta, autorizar, resumen
frontend/src/pages/inventory/cargas/componentes/*.tsx # TarjetaDuda, TablaPlan, CambiosAntesDespues, ResumenEtiquetas
frontend/src/pages/core/ReglasCarga.tsx               # sección en Empresa
```

---

### Task 1: Cliente estructurado de Anthropic, uso diario y gate estricto

**Files:**
- Modify: `requirements.txt` (agregar `anthropic>=1.0,<2` y `pypdf>=5`)
- Create: `app/modules/ai/cliente_anthropic.py`, `app/modules/ai/uso.py`, `app/modules/ai/gating.py`
- Test: `tests/test_ai_cliente_anthropic.py`, `tests/test_ai_uso_gating.py`

**Interfaces:**
- Produces:
  - `RespuestaEstructurada(datos: dict, tokens_entrada: int, tokens_salida: int)` (dataclass)
  - `class ClienteEstructurado(Protocol): def generar(self, *, sistema: str, contenido: list[dict], esquema: dict, max_tokens: int = 64000) -> RespuestaEstructurada`
  - `ClienteAnthropic(api_key: str, modelo: str)`. Usa `client.beta.messages.stream(model, max_tokens, system, messages=[{"role":"user","content":contenido}], output_config={"format":{"type":"json_schema","schema":esquema}}, betas=["server-side-fallback-2026-07-01"], fallbacks="default")` y luego `.get_final_message()`; parsea el primer bloque `text` con `json.loads`.
  - `ClienteEstructuradoFalso(guion: list[dict | Exception])`, que guarda `.llamadas` (lista de kwargs).
  - `cliente_estructurado_por_defecto() -> ClienteAnthropic`: 503 `"IA no configurada: falta ANTHROPIC_API_KEY en el servidor."` si falta la clave.
  - `ProveedorNoDisponible` (reusar la de `cliente_llm.py`).
  - `verificar_cupo(db, org_id) -> None`: 429 si el uso de hoy ≥ `limite_tokens_dia()`.
  - `registrar_uso(db, org_id, tokens_entrada, tokens_salida) -> None`: upsert de `AiUsoDiario` del día de negocio, sin commit.
  - `exigir_modulo_ai`: dependencia FastAPI que devuelve `org_id: int`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ai_cliente_anthropic.py
def test_falso_devuelve_guion_y_registra_llamadas(): ...  # datos == guion[0]; len(llamadas)==1; llamadas[0]["esquema"] is el esquema
def test_falso_propaga_excepcion_del_guion(): ...        # guion=[ProveedorNoDisponible("x")] -> raises
def test_sin_clave_da_503(monkeypatch): ...              # delenv ANTHROPIC_API_KEY; HTTPException.status_code==503 y "ANTHROPIC_API_KEY" in detail
def test_refusal_se_vuelve_proveedor_no_disponible(monkeypatch): ...  # mensaje falso con stop_reason="refusal" -> ProveedorNoDisponible
def test_error_de_api_se_vuelve_proveedor_no_disponible(monkeypatch): ...  # anthropic.RateLimitError / APIConnectionError -> ProveedorNoDisponible
```

```python
# tests/test_ai_uso_gating.py
def test_registrar_uso_acumula_en_el_dia(db, org): ...   # dos llamadas -> una fila, tokens sumados, llamadas==2
def test_verificar_cupo_429_al_pasar_el_tope(db, org, monkeypatch): ...  # AI_TOKENS_DIA_ORG=100; uso 100 -> 429
def test_gate_403_admin_sin_modulo(client, auth_admin_a): ...  # endpoint de prueba con Depends(exigir_modulo_ai) -> 403, "SCALE" in detail
def test_gate_pasa_con_modulo_habilitado(client, db, org, auth_admin_a): ...  # OrganizationModule(ai, enabled) -> 200
```

Las pruebas de refusal y de error de API sustituyen `anthropic.Anthropic` con un doble cuyo `beta.messages.stream(...)` es un context manager que devuelve un mensaje con `stop_reason` y `content`. No se hace red.

- [ ] **Step 2: Run, verify they fail**

Run: `python3 -m pytest -q tests/test_ai_cliente_anthropic.py tests/test_ai_uso_gating.py`
Expected: FAIL (`ModuleNotFoundError: app.modules.ai.cliente_anthropic`)

- [ ] **Step 3: Implement** los tres archivos con las firmas de arriba.
  - `exigir_modulo_ai` resuelve la org con `get_current_active_organization` y consulta `OrganizationModule(module_key="ai", is_enabled=True)`, **sin** el bypass de `require_module`.
  - `detail` del 403: `f"El asistente IA no está incluido en tu plan (mínimo {plan_minimo_para('ai').nombre}). La plataforma puede activarlo."`. Usa el atributo de nombre que tenga `Plan` en `plans.py`.
  - `registrar_uso` usa la fecha de negocio de `app/core/fechas.py`.
  - `pip install -r requirements.txt` en el entorno.

- [ ] **Step 4: Run, verify they pass** (mismo comando). Expected: PASS

- [ ] **Step 5: Commit** — `feat(ai): cliente estructurado de Anthropic, uso diario y gate estricto`

---

### Task 2: Tablas de cargas y `reglas_carga`

**Files:**
- Create: `app/modules/cargas/__init__.py`, `app/modules/cargas/models.py`, `app/modules/cargas/reglas.py`
- Modify:
  - `app/models/__init__.py` (import de `app.modules.cargas.models`)
  - `app/modules/tenants/models.py` (`reglas_carga = Column(JSON, nullable=True)`)
  - `app/modules/tenants/schemas.py` (`reglas_carga: Optional[ReglasCarga]` en update y read)
  - `scripts/railway_init.py` (ALTER `organization.reglas_carga` JSON; en Postgres `JSONB`, igual que las otras JSON de esa lista)
  - `app/modules/ai/limpieza.py` (borrar también las tablas de cargas de la org)
- Test: `tests/test_cargas_modelos.py`

**Interfaces:**
- Produces (constantes y modelos):
  - `ESTADOS_CARGA = ("leyendo","plan","aplicando","aplicada","error","descartada")`
  - `PROPOSITOS = ("entrada","migracion")`
  - `CLASES = ("EXISTE","SUMA","NUEVO","YA_CARGADO","IGNORADO")`
  - `CargaMercancia`: UUIDMixin, AuditMixin, TenantMixin. Campos:
    - `folio` Integer (único por org);
    - `user_id`, `proposito`, `estado`;
    - `archivo_nombre`, `archivo_sha256` (index), `archivo_tipo` (`pdf`|`xlsx`|`csv`);
    - `sucursal_destino_id`;
    - `monedas` JSON (`{"USD": 18.2, "CNY": null}`);
    - `totales` JSON, `error` Text;
    - `aplicada_por`, `aplicada_at`;
    - `tokens_entrada`, `tokens_salida`.
  - `CargaArchivo`: `carga_id` String(36), `contenido` LargeBinary. El original se guarda en la base: no es público y sobrevive a los redespliegues.
  - `CargaRenglon`:
    - `carga_id`, `orden`;
    - `crudo` JSON, `normalizado` JSON;
    - `clase`, `grupo`;
    - `product_id`, `variant_id` (String(36) nullable);
    - `sku`, `cantidad` Numeric, `precio` Numeric nullable, `costo` Numeric nullable;
    - `resultado` JSON.
  - `CargaDuda`: `carga_id`, `numero`, `tipo`, `texto`, `opciones` JSON (`[{"clave","etiqueta"}]`), `recomendada`, `renglones` JSON, `estado` (`abierta`|`resuelta`), `respuesta` Text, `resuelta_por`.
  - `CargaCambio`: `carga_id`, `user_id`, `texto` Text nullable, `operaciones` JSON, `antes` JSON, `despues` JSON, `deshecho` Boolean.
  - `ReglasCarga` (Pydantic, todos los campos con default):
    - `costo_si_falta: Literal["preguntar","fraccion_precio"]="preguntar"`, `fraccion: Decimal = Decimal("0.5")`;
    - `iva: bool = False`;
    - `sucursal_recibe: Optional[int] = None`;
    - `activar_en: Literal["todas_las_que_venden","sucursal_recibe"] = "todas_las_que_venden"`;
    - `mapa_tallas: dict[str,str] = {}`, `escala_ropa: list[str] = []`;
    - `tipos: dict[str, TipoPrenda] = {}` con `TipoPrenda(codigo_sku: str, departamento: str)`;
    - `materiales_aparte: list[str] = []`, `material_normal: Optional[str] = None`;
    - `genero_por_marca: dict[str,str] = {}`, `genero_por_omision: Optional[str] = None`, `sufijo_dama: Optional[str] = None`;
    - `matriz_por_omision: Literal["completa","solo_lo_que_hay"] = "solo_lo_que_hay"`;
    - `precios_familia: list[RangoPrecio] = []` con `RangoPrecio(tipo: str, marca: Optional[str], precios: list[Decimal])`;
    - `ventana_ya_cargado_dias: int = 14`.
  - `reglas_de_la_org(org: Organization) -> ReglasCarga`: `None` → todas las defaults.

- [ ] **Step 1: Write the failing tests**

```python
def test_tablas_se_crean_y_fk_uuid_son_string36(db): ...    # inspect CargaRenglon.__table__.c.carga_id.type.length == 36
def test_folio_unico_por_org(db, org): ...                   # dos cargas con el mismo folio en la org -> IntegrityError
def test_reglas_vacias_dan_defaults(org): ...                # reglas_de_la_org(org).costo_si_falta == "preguntar"; ventana_ya_cargado_dias == 14
def test_reglas_invalidas_dan_422(client, auth_admin_a): ... # PUT org con reglas_carga.costo_si_falta="x" -> 422
def test_limpieza_borra_cargas_de_la_org(db, org): ...       # borrar_datos_ai_de_org -> 0 filas de cargas_* para la org
```

- [ ] **Step 2: Run, verify they fail** — `python3 -m pytest -q tests/test_cargas_modelos.py` → FAIL (import)
- [ ] **Step 3: Implement.** Copia la forma de las tuplas existentes en `railway_init.py` (línea ~171, la de `ai_instrucciones`).
- [ ] **Step 4: Run, verify they pass**
- [ ] **Step 5: Commit** — `feat(cargas): tablas de cargas y reglas_carga por organización`

---

### Task 3: Lectura de Excel y mapeo de encabezados

**Files:**
- Create: `app/modules/cargas/tipos.py`, `app/modules/cargas/lectura_excel.py`
- Test: `tests/test_cargas_excel.py`

**Interfaces:**
- Consumes: `ClienteEstructurado` (Task 1).
- Produces:
  - `RenglonCrudo` (Pydantic):
    - `descripcion_original: str`; `marca`, `tipo`, `material`, `color`, `talla`: `Optional[str]`;
    - `cantidad: Decimal`;
    - `costo_unitario`, `precio`: `Optional[Decimal]`; `moneda: Optional[str]`;
    - `observacion: Optional[str]`, `duda: Optional[str]`;
    - `origen: str` (p. ej. `"Hoja1!R12"` o `"pág. 3"`).
  - `TablaCruda(pestana: str, encabezados: list[str], filas: list[list[Any]])`
  - `leer_tablas(contenido: bytes, archivo_tipo: str) -> list[TablaCruda]`: xlsx con openpyxl `read_only=True, data_only=True`; csv con sniff de separador y `utf-8-sig`/`latin-1`. Omite filas vacías.
  - `MapaColumnas(campos: dict[str, Optional[int]], columnas_dinero: list[int], texto_libre: list[int])`. `campos` son las llaves de `RenglonCrudo` → índice de columna.
  - `ESQUEMA_MAPA: dict` (JSON Schema estricto de `MapaColumnas`).
  - `mapear_columnas(tabla: TablaCruda, cliente: ClienteEstructurado, instrucciones: str) -> tuple[MapaColumnas, int, int]`: manda encabezados + 20 filas de muestra; devuelve el mapa y los tokens.
  - `renglones_desde_excel(tabla: TablaCruda, mapa: MapaColumnas, rol_dinero: dict[int, Literal["costo","precio","ignorar"]]) -> list[RenglonCrudo]`. Cantidad y dinero se leen de las celdas con `celda_decimal`; el modelo no toca valores.

- [ ] **Step 1: Write the failing tests**

```python
def test_lee_xlsx_con_dos_pestanas(): ...          # xlsx creado en la prueba con openpyxl; 2 TablaCruda, filas vacías omitidas
def test_lee_csv_punto_y_coma_latin1(): ...
def test_mapear_usa_solo_20_filas_de_muestra(): ...  # tabla de 50 filas; el contenido enviado al falso trae 20
def test_renglones_toman_valores_de_celdas_no_del_modelo(): ...  # mapa del falso; cantidad "3" -> Decimal(3); precio de la celda
def test_columna_dinero_sin_rol_no_llena_precio_ni_costo(): ...  # rol_dinero vacío -> precio None y costo None
def test_cantidad_vacia_o_cero_marca_duda(): ...    # renglón con cantidad vacía -> duda == "Cantidad vacía"
```

- [ ] **Step 2: Run, verify they fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run, verify they pass**
- [ ] **Step 5: Commit** — `feat(cargas): lectura de Excel/CSV y mapeo de encabezados con IA`

---

### Task 4: Extracción de PDF

**Files:**
- Create: `app/modules/cargas/extraccion_pdf.py`
- Test: `tests/test_cargas_pdf.py`

**Interfaces:**
- Consumes: `ClienteEstructurado`, `RenglonCrudo`.
- Produces:
  - `ExtraccionPdf(renglones: list[RenglonCrudo], monedas: dict[str, Optional[Decimal]], tokens_entrada: int, tokens_salida: int)`
  - `PAGINAS_POR_BLOQUE = 15`
  - `ESQUEMA_PDF: dict`: `{renglones: [...RenglonCrudo], monedas: [{codigo, tipo_cambio|null}], continua_en_siguiente: bool}`
  - `extraer_pdf(contenido: bytes, cliente: ClienteEstructurado, instrucciones: str) -> ExtraccionPdf`
- Algoritmo:
  - Con `pypdf`, parte el PDF en bloques de `PAGINAS_POR_BLOQUE`. Cada bloque va como `{"type":"document","source":{"type":"base64","media_type":"application/pdf","data":...}}`, seguido del texto con instrucciones fijas:
    - traducir al español solo tipo/marca/color;
    - conservar `descripcion_original` literal;
    - marcar `duda` en lo ilegible;
    - no inventar precio de venta.
  - Al bloque k > 0 se le pasa el último renglón del bloque anterior. Si el bloque anterior dijo `continua_en_siguiente`, el primer renglón del bloque k que repite esa descripción se **une** al anterior en lugar de duplicarse.
  - Monedas: se unen; si dos bloques dan tipos de cambio distintos para la misma moneda, queda `None` (eso se vuelve duda en Task 7).

- [ ] **Step 1: Write the failing tests** (PDFs generados en la prueba con `pypdf` o reportlab, si ya está en requirements; si no, PDFs mínimos de bytes fijos)

```python
def test_pdf_corto_una_llamada(): ...              # 3 páginas -> 1 llamada; renglones del guion
def test_pdf_largo_se_parte_en_bloques(): ...       # 31 páginas -> 3 llamadas
def test_renglon_partido_entre_bloques_no_se_duplica(): ...  # bloque1 continua_en_siguiente=True + bloque2 repite descripción -> 1 renglón
def test_tipo_cambio_contradictorio_queda_none(): ...
def test_tokens_se_suman(): ...
```

- [ ] **Step 2: Run, verify they fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run, verify they pass**
- [ ] **Step 5: Commit** — `feat(cargas): extracción de renglones de PDF por bloques`

---

### Task 5: Normalizar, agrupar y armar SKU (sin base de datos)

**Files:**
- Create: `app/modules/cargas/normalizar.py`
- Test: `tests/test_cargas_normalizar.py`

**Interfaces:**
- Consumes: `RenglonCrudo`, `ReglasCarga`, `sku_sugerido` (`app/modules/products/sale_name.py`).
- Produces:
  - `RenglonNormalizado` (en `tipos.py`): campos de `RenglonCrudo` normalizados + `genero: Optional[str]`, `departamento: Optional[str]`, `costo_mxn: Optional[Decimal]`, `llave_grupo: str`.
  - `normalizar_renglon(r: RenglonCrudo, reglas: ReglasCarga, monedas: dict[str, Optional[Decimal]]) -> RenglonNormalizado`. Hace lo siguiente:
    - talla con `mapa_tallas` (insensible a mayúsculas, sin espacios);
    - tipo → departamento con `reglas.tipos`;
    - género: `genero_por_marca` > `genero_por_omision`;
    - `costo_mxn = costo_unitario × monedas[moneda]`, o `None` si falta el tipo de cambio;
    - si no hay costo y la regla es `fraccion_precio` y hay precio: `costo_mxn = precio × fraccion`.
  - `llave_grupo` = marca|tipo|material efectivo|precio. El material efectivo es `None` salvo que esté en `materiales_aparte`; `material_normal` cuenta como `None`.
  - `agrupar(renglones: list[RenglonNormalizado]) -> list[Grupo]`, con `Grupo(llave: str, renglones: list[int], tallas: dict[str, Decimal], sufijo: str)`. El mismo tipo con distinto precio **en la misma talla** produce grupos con `sufijo` `""`, `"-2"`, `"-3"`. Con distinto precio en tallas distintas, un solo grupo con precio por talla.
  - `prefijo_de_marca(skus_existentes_de_la_marca: list[str]) -> Optional[str]`: el prefijo más común antes del primer `-`.
  - `sku_para(grupo, talla, reglas, prefijo) -> str`. Forma `PREFIJO-CODIGO[-MAT][sufijo]`; la talla principal va sin sufijo y las demás con `-<talla>`, igual que la convención de Ch/M/G/XL. Si el tipo no está en `reglas.tipos`, cae en `sku_sugerido`.

- [ ] **Step 1: Write the failing tests**

```python
def test_mapa_tallas_normaliza(): ...                 # {"S":"Ch","L":"G"}; "s " -> "Ch"
def test_costo_por_tipo_de_cambio(): ...              # 10 USD × 18.5 -> 185.00
def test_costo_fraccion_cuando_falta(): ...           # precio 3000, fraccion 0.5 -> 1500
def test_costo_none_y_regla_preguntar(): ...
def test_material_aparte_separa_grupo(): ...          # "Pana" en materiales_aparte -> otra llave; "Algodón" == material_normal -> misma llave
def test_mismo_tipo_precio_distinto_misma_talla_da_sufijos(): ...  # sufijos "", "-2"
def test_precio_distinto_tallas_distintas_un_grupo(): ...
def test_prefijo_de_marca_mas_comun(): ...            # ["MU-PLAY","MU-CAMI-M","X1"] -> "MU"
def test_sku_principal_y_tallas(): ...                # MU-CAMI-ML para Ch, MU-CAMI-ML-M para M
```

- [ ] **Step 2–4:** fail → implement → pass
- [ ] **Step 5: Commit** — `feat(cargas): normalización, agrupación y SKU deterministas`

---

### Task 6: Cruce con el catálogo y YA CARGADO

**Files:**
- Create: `app/modules/cargas/cruce.py`
- Test: `tests/test_cargas_cruce.py`

**Interfaces:**
- Consumes: `Grupo`, `RenglonNormalizado`, modelos de productos, `CargaMercancia`.
- Produces:
  - `Coincidencia(product_id: str, variante_por_talla: dict[str, str], precio_actual: Decimal, exacta: bool)`
  - `cruzar_con_catalogo(db, org_id: int, grupos: list[Grupo], renglones: list[RenglonNormalizado]) -> dict[str, Optional[Coincidencia]]`, por llave de grupo:
    - busca por SKU calculado (vivo, cualquier departamento);
    - si no lo encuentra, por marca + departamento + nombre del tipo con SQL directo (no `read_products`);
    - `exacta` = mismo precio.
  - `clasificar(grupo, coincidencia, proposito) -> list[tuple[int, str]]` (renglón, clase):
    - talla que existe → `SUMA` en entrada, `EXISTE` en migración;
    - talla nueva en producto existente → `NUEVO` (variante);
    - sin coincidencia → `NUEVO`.
  - `marcar_ya_cargado(db, org_id: int, carga: CargaMercancia, renglones_plan: list[CargaRenglon], ventana_dias: int) -> int` (cuántos marcó). Marca `YA_CARGADO`:
    - todos los renglones, si otra carga `aplicada` de la org tiene el mismo `archivo_sha256`;
    - si no, cada renglón cuyo `(sku, cantidad)` coincide con un movimiento `reference LIKE 'carga:%'` de los últimos `ventana_dias` días.

- [ ] **Step 1: Write the failing tests** (fixtures `db`, `org`, `branch_a`; productos creados con `crear_producto`)

```python
def test_encuentra_por_sku_en_otro_departamento(db, org, admin_a): ...
def test_encuentra_por_marca_departamento_tipo(db, org, admin_a): ...
def test_talla_existente_es_suma_en_entrada(): ...
def test_talla_existente_es_existe_en_migracion(): ...
def test_talla_nueva_es_nuevo_variante(): ...
def test_mismo_sha_aplicado_marca_todo_ya_cargado(db, org): ...
def test_mismo_contenido_otro_nombre_marca_ya_cargado(db, org): ...   # sha igual, archivo_nombre distinto
def test_renglon_de_carga_reciente_marca_ya_cargado(db, org): ...     # movimiento reference="carga:<otra>" hace 3 días
def test_fuera_de_ventana_no_marca(db, org): ...                      # hace 20 días -> 0
def test_ultimo_conteo_por_departamento(db, org, ...): ...            # conteo cerrado de "Playeras" -> {depto_id: {conteo_id, cerrado_at}}
```

Agrega también `ultimo_conteo_por_departamento(db, org_id: int, department_ids: list[str]) -> dict[str, dict]`. Lee el último `inventory_counts` cerrado de cada departamento del plan y devuelve `{conteo_id, numero, cerrado_at}`. Es contexto para la pantalla (spec §5.2); no cambia clases.

- [ ] **Step 2–4:** fail → implement → pass
- [ ] **Step 5: Commit** — `feat(cargas): cruce con catálogo y detección de cargas repetidas`

---

### Task 7: Dudas por regla

**Files:**
- Create: `app/modules/cargas/dudas.py`
- Test: `tests/test_cargas_dudas.py`

**Interfaces:**
- Consumes: Tasks 5–6, `ReglasCarga`.
- Produces:
  - `TIPOS_DUDA = ("columnas_dinero","tipo_cambio","marca_nueva","marca_parecida","casi_igual","precio_faltante","precio_fuera_familia","precio_distinto_existente","departamento","genero","sin_costo","extraccion")`
  - `DudaNueva(tipo: str, texto: str, opciones: list[dict], recomendada: str, renglones: list[int])`
  - `generar_dudas(db, org_id, carga, renglones, grupos, coincidencias, reglas) -> list[DudaNueva]`, ordenadas por tipo según la tupla y numeradas desde 1 al guardarse. Opciones fijas por tipo (claves exactas):
    - `columnas_dinero`: una duda por columna de dinero → `costo|precio|ignorar`. Recomendada: `costo` si el propósito es `entrada`, `precio` si es `migracion`.
    - `tipo_cambio`: sin opciones; se contesta con texto ("18.40").
    - `marca_nueva`: `crear` | `usar:<brand_id>` por cada marca existente con distancia de Levenshtein ≤ 2 o prefijo común ≥ 5 letras. Recomendada: la más parecida si la hay; si no, `crear`.
    - `casi_igual`: `usar:<product_id>` | `nuevo`. Recomendada: `usar` si solo difiere el material normal.
    - `precio_faltante`: sin opciones (texto).
    - `precio_fuera_familia`: `mantener` | texto. Se dispara si `reglas.precios_familia` define precios para (tipo, marca o cualquiera) y el precio no está en la lista.
    - `precio_distinto_existente`: `mantener` | `actualizar` | `aparte`. Recomendada: `mantener`.
    - `departamento`: `depto:<id>` por cada departamento existente. En migración, además `crear`.
    - `genero`: `HOMBRE|MUJER|UNISEX|NINO`.
    - `sin_costo`: solo si `costo_si_falta == "preguntar"`; texto.
    - `extraccion`: una por cada renglón con `duda` del modelo → `confirmar` | `ignorar`.
  - `opcion_a_operaciones(duda: CargaDuda, clave: str, valor_texto: Optional[str]) -> list[dict]`: traduce una opción o texto a operaciones del formato de Task 8.

- [ ] **Step 1: Write the failing tests** (una prueba por tipo de duda, con los valores exactos del texto y las opciones, y además):

```python
def test_sin_dudas_cuando_todo_cuadra(): ...
def test_marca_parecida_recomienda_existente(db, org): ...       # existe "Casa Dos"; llega "Casa Do" -> recomendada == "usar:<id>"
def test_precio_nunca_se_copia_de_otro_renglon(): ...            # dos renglones mismo grupo, uno sin precio -> duda precio_faltante, precio sigue None
def test_columnas_dinero_recomendacion_por_proposito(): ...
def test_opcion_a_operaciones_actualizar_precio(): ...           # -> [{"op":"fijar_campo","grupo":g,"campo":"accion_precio","valor":"actualizar"}]
```

- [ ] **Step 2–4:** fail → implement → pass
- [ ] **Step 5: Commit** — `feat(cargas): dudas numeradas por regla con opciones`

---

### Task 8: Operaciones sobre el plan e interpretación de texto libre

**Files:**
- Create: `app/modules/cargas/operaciones.py`, `app/modules/cargas/respuestas.py`
- Test: `tests/test_cargas_operaciones.py`, `tests/test_cargas_respuestas.py`

**Interfaces:**
- Consumes: modelos (Task 2), `generar_dudas`/recalcular (Tasks 5–7), `ClienteEstructurado`.
- Produces:
  - Operaciones (dicts validados con Pydantic, unión discriminada por `op`):
    - `fijar_campo{renglones?: list[int], grupo?: str, campo: Literal["marca","tipo","material","color","talla","precio","costo","genero","departamento","cantidad","accion_precio"], valor: str}`
    - `resolver_duda{numero: int, opcion: str, valor?: str}`
    - `usar_existente{grupo, product_id}`
    - `nuevo_producto{grupo}`
    - `ignorar{renglones}`
    - `tipo_cambio{moneda, valor: Decimal}`
  - `aplicar_operaciones(db, carga: CargaMercancia, user: User, operaciones: list[dict], texto: Optional[str]) -> tuple[CargaCambio, list[str]]` (cambio, rechazos legibles). Pasos:
    - valida cada operación: los renglones son de la carga, el `product_id` es de la org, la duda está abierta, el campo está permitido;
    - aplica las válidas sobre `normalizado`;
    - **recalcula** grupos, cruce, clases y dudas: las dudas resueltas conservan su número y las nuevas toman números siguientes;
    - guarda `antes`/`despues` por grupo afectado.
  - `deshacer_cambio(db, carga, cambio_id) -> None`: restaura `antes` y marca `deshecho`. Solo el último cambio no deshecho.
  - `ESQUEMA_OPERACIONES: dict` = `{operaciones: [...], no_entendido: [{numero?: int, texto: str}]}`
  - `interpretar_respuesta(db, carga, texto: str, cliente: ClienteEstructurado, instrucciones: str) -> tuple[list[dict], list[str], int, int]`. El modelo recibe:
    - dudas abiertas: número, texto, opciones;
    - resumen del plan por grupo: llave, marca, tipo, tallas, precio, clase, renglones;
    - la respuesta del usuario.

    No recibe la base ni datos de clientes. Tope de `texto`: 4,000 caracteres.

- [ ] **Step 1: Write the failing tests**

```python
# operaciones
def test_fijar_precio_a_grupo_recalcula_y_cierra_duda(db, ...): ...
def test_operacion_con_renglon_ajeno_se_rechaza(db, ...): ...      # rechazos == ["Operación 1: renglón 999 no es de esta carga"]; plan sin cambios
def test_product_id_de_otra_org_se_rechaza(db, ...): ...
def test_deshacer_restaura_antes(db, ...): ...
def test_solo_se_deshace_el_ultimo(db, ...): ...                   # deshacer el penúltimo -> 409
# respuestas
def test_respuesta_numerada_produce_operaciones(db, ...): ...      # falso devuelve 2 ops válidas -> aplicadas
def test_no_entendido_vuelve_como_texto(db, ...): ...              # no_entendido=[{numero:4,...}] -> rechazos contiene "No entendí el punto 4"
def test_texto_mayor_a_4000_da_422(client, ...): ...
def test_modelo_solo_ve_resumen_sin_clientes(db, ...): ...         # el contenido enviado al falso no contiene nombres de clientes ni usernames
```

- [ ] **Step 2–4:** fail → implement → pass
- [ ] **Step 5: Commit** — `feat(cargas): operaciones sobre el plan y respuestas en texto libre`

---

### Task 9: Aplicar la carga en una transacción

**Files:**
- Create: `app/modules/cargas/aplicar.py`
- Test: `tests/test_cargas_aplicar.py`

**Interfaces:**
- Consumes:
  - `crear_producto(db, org_id, user, ProductCreate, asignador=..., kardex=...)`;
  - `crear_variantes(db, org_id, producto, entradas, stock_branch_id=None, user_id=..., asignador=...)`;
  - `aplicar_ajuste(db, org_id=, branch_id=, variant_id=, user_id=, quantity=, reason=, notes=, commit=False)` (`app/routers/inventory.py`);
  - `fijar_existencia(db, org_id, variante, branch_id, objetivo, user_id, referencia=, notas=)`;
  - `sucursales_que_venden`;
  - `AsignadorDeCodigos`.
- Produces:
  - `ResumenAplicacion(productos_nuevos: int, variantes_nuevas: int, piezas: Decimal, valor_costo: Decimal, etiquetas: list[dict])`. Cada etiqueta: `{marca, producto, sku, talla, barcode, piezas, precio}`; `piezas` = lo que entró.
  - `aplicar_carga(db, carga: CargaMercancia, user: User) -> ResumenAplicacion`.
- Reglas:
  - 409 si hay dudas abiertas o el estado no es `plan`; 403 si el rol no es ADMINISTRADOR/DUEÑO.
  - Todo dentro de `db.begin_nested()` + commit final. Ante cualquier excepción: rollback, `estado="error"`, `error` = detail legible, commit de solo ese estado, y se relanza como 422.
  - Marcas y departamentos nuevos (dudas resueltas con `crear`) se crean aquí.
  - Productos NUEVOS: `ProductCreate` con `has_iva=reglas.iva`, `target_branch_ids` según `reglas.activar_en`, existencia inicial 0. Las piezas entran por `aplicar_ajuste` para que todo quede con `reference="carga:<id>"`.
  - Variantes nuevas en productos existentes: con `crear_variantes`.
  - Entrada: `aplicar_ajuste(+cantidad)`. Migración: `fijar_existencia(objetivo=cantidad)`.
  - `accion_precio == "actualizar"`: escribe `variant.price` y `variant.cost` y registra auditoría `CARGA_PRECIO_ACTUALIZADO` con el precio anterior.
  - Renglones `YA_CARGADO` e `IGNORADO` no se tocan.
  - Al final: `estado="aplicada"`, `aplicada_por`, `aplicada_at`, `totales`, y auditoría `CARGA_APLICADA` con `{carga_id, folio, totales, source:"ai"}`. Usa el modelo de auditoría de plataforma que ya usa `productos.py` (`_auditar_alta_de_cajero`).

- [ ] **Step 1: Write the failing tests**

```python
def test_entrada_crea_nuevos_y_suma_existentes(db, ...): ...    # existencias y kardex reference=="carga:<id>", notes.startswith("Carga #1")
def test_migracion_fija_existencia(db, ...): ...
def test_costo_y_iva_por_reglas(db, ...): ...
def test_activa_en_todas_las_que_venden(db, ...): ...
def test_marca_nueva_aceptada_se_crea(db, ...): ...
def test_actualizar_precio_audita_anterior(db, ...): ...
def test_mantener_precio_no_toca_variante(db, ...): ...
def test_falla_a_media_no_deja_nada(db, ...): ...                # SKU que choca en el renglón 3 -> 0 productos nuevos, 0 movimientos, estado=="error"
def test_reintento_tras_error_funciona(db, ...): ...             # se corrige vía operación y aplica
def test_dudas_abiertas_409(db, ...): ...
def test_gerente_no_puede_autorizar_403(db, ...): ...
def test_etiquetas_cuentan_lo_que_entro_no_el_stock(db, ...): ...  # existía 2, entran 3 -> piezas == 3
def test_segunda_aplicacion_del_mismo_archivo_sale_ya_cargado(db, ...): ...
```

- [ ] **Step 2–4:** fail → implement → pass
- [ ] **Step 5: Commit** — `feat(cargas): aplicar la carga en una transacción con kardex y auditoría`

---

### Task 10: Proceso en segundo plano y endpoints `/api/cargas`

**Files:**
- Create: `app/modules/cargas/proceso.py`, `app/modules/cargas/schemas.py`, `app/modules/cargas/router.py`
- Modify: `app/main.py` (montar en `/api/cargas`; en startup llamar `recuperar_cargas_colgadas`)
- Test: `tests/test_cargas_api.py`

**Interfaces:**
- Consumes: Tasks 1–9.
- Produces:
  - `procesar_carga(carga_id: str, cliente: Optional[ClienteEstructurado] = None) -> None`. Abre su propia `SessionLocal`, verifica el cupo, lee (Excel → `mapear_columnas` + dudas `columnas_dinero`; PDF → `extraer_pdf`), normaliza, cruza, marca YA CARGADO, genera dudas, guarda renglones y dudas, registra uso y deja `estado="plan"`. Si algo falla (incluido `ProveedorNoDisponible`), queda `estado="error"` con el mensaje.
  - Excel: los renglones se arman cuando se resuelven las dudas `columnas_dinero`. Mientras tanto el plan muestra solo esas dudas, y `aplicar_operaciones` → `renglones_desde_excel` cuando la última se resuelve.
  - `lanzar_proceso(carga_id)`: `threading.Thread(daemon=True)`. Si `os.getenv("CARGAS_PROCESO_EN_LINEA") == "1"`, corre en línea. Las pruebas lo activan y además inyectan el falso con `app.dependency_overrides[obtener_cliente_estructurado]`.
  - `recuperar_cargas_colgadas(db) -> int`: `leyendo|aplicando` con `updated_at` de más de 10 minutos → `error` "La lectura se interrumpió. Vuelve a intentar."
  - Endpoints (todos con `exigir_modulo_ai`, `get_current_user`, roles de oficina ADMINISTRADOR/DUEÑO/GERENTE):
    - `POST /api/cargas` (multipart: `archivo`, `proposito`, `sucursal_id?`) → 202 `{id, folio, estado}`. 413 si pesa más de 20 MB; 415 si no es pdf/xlsx/csv. El folio es el siguiente de la org.
    - `GET /api/cargas` → lista: folio, archivo, estado, propósito, piezas, usuario, fechas.
    - `GET /api/cargas/{id}` → `{carga, contadores_por_clase, dudas, grupos (con renglones), cambios, ultimos_conteos}`. La pantalla de Task 13 muestra `ultimos_conteos` bajo los contadores: "Último conteo de Playeras: #12, 5 nov".
    - `POST /api/cargas/{id}/respuestas {texto}` → `{cambio, rechazos}`
    - `POST /api/cargas/{id}/dudas/{numero} {opcion, valor?}` → `{cambio, rechazos}`
    - `POST /api/cargas/{id}/cambios/{cambio_id}/deshacer`
    - `POST /api/cargas/{id}/reintentar`: solo en `error` → vuelve a `leyendo` y lanza el proceso.
    - `POST /api/cargas/{id}/autorizar` → `ResumenAplicacion` (solo ADMINISTRADOR/DUEÑO).
    - `POST /api/cargas/{id}/descartar`
    - `GET /api/cargas/{id}/etiquetas` → la lista de etiquetas de una carga aplicada.

- [ ] **Step 1: Write the failing tests**

```python
def test_flujo_completo_pdf(client, db, auth_admin_a, ...): ...       # subir -> plan con dudas -> respuesta -> autorizar -> etiquetas
def test_flujo_excel_pide_columnas_dinero_primero(client, ...): ...
def test_archivo_grande_413(client, ...): ...
def test_tipo_no_soportado_415(client, ...): ...
def test_cajero_403(client, ...): ...
def test_org_sin_modulo_ai_403(client, ...): ...
def test_carga_de_otra_org_404(client, ...): ...
def test_proveedor_caido_deja_error_y_reintentar_funciona(client, ...): ...
def test_recuperar_colgadas_marca_error(db, ...): ...                  # leyendo con updated_at hace 15 min -> error
def test_folio_consecutivo_por_org(client, ...): ...
```

- [ ] **Step 2–4:** fail → implement → pass
- [ ] **Step 5: Run the full backend suite** — `python3 -m pytest -q --ignore=tests/test_cash_complete.py`. Expected: el mismo número de fallos que en `main` (0 hoy, según la memoria del proyecto) y todo lo nuevo en verde.
- [ ] **Step 6: Commit** — `feat(cargas): endpoints /api/cargas con lectura en segundo plano`

---

### Task 11: Etiquetas por carga

**Files:**
- Modify: `app/modules/labels/services.py` (`variantes_visibles`/`candidatos`: filtro `carga_id`), `app/modules/labels/router.py` (query `carga_id: Optional[str]`), `frontend/src/api/labels.ts` (`carga_id` en filtros), `frontend/src/pages/labels/Labels.tsx` (leer `?carga=<id>` y mostrar el chip "Carga #N" con opción de quitarlo)
- Test: `tests/test_labels_por_carga.py`, `frontend/src/pages/labels/__tests__/LabelsCarga.test.tsx`

**Interfaces:**
- Con `carga_id`, solo salen las variantes con movimientos `reference == f"carga:{carga_id}"` de la org. Cada fila trae `piezas_carga` = suma de `qty_change` de esa referencia, y la pantalla la usa como cantidad de copias por omisión.

- [ ] **Step 1: Write the failing tests**

```python
def test_filtra_solo_variantes_de_la_carga(client, ...): ...
def test_piezas_carga_es_lo_que_entro(client, ...): ...      # stock 5, entraron 3 -> piezas_carga == 3
def test_carga_de_otra_org_da_lista_vacia(client, ...): ...
```

```ts
it('con ?carga=… pide candidates con carga_id y muestra el chip Carga', ...)
it('copias por omisión = piezas_carga', ...)
```

- [ ] **Step 2–4:** fail → implement → pass (`npx vitest run src/pages/labels`)
- [ ] **Step 5: Commit** — `feat(labels): filtrar etiquetas por carga con las piezas que entraron`

---

### Task 12: Frontend — lista y subida de cargas

**Files:**
- Create: `frontend/src/api/cargas.ts`, `frontend/src/pages/inventory/cargas/Cargas.tsx`, `frontend/src/pages/inventory/cargas/__tests__/Cargas.test.tsx`
- Modify:
  - `frontend/src/App.tsx`: `lazy()` de `Cargas` y `CargaPlan`; rutas `/inventory/cargas` y `/inventory/cargas/:id`.
  - `frontend/src/components/layout/navConfig.ts`:
    - `ALL_NAV`: `{label:'Cargar mercancía', short:'CRG', icon:'fa-file-import', url:'/inventory/cargas', group:'hq', sort:13.55, module:'ai'}`;
    - en `HQ_NAV_GROUPS`, Inventario;
    - en `ROLE_ROUTES`, ADMINISTRADOR, DUEÑO y GERENTE.
  - `frontend/src/components/layout/navPerfilBasico.ts`: ocultarla en básico, porque es de planes de paga.
  - Página de Productos: botón "Cargar mercancía" (`dax-btn-secondary`) visible solo si el módulo `ai` está activo.
  - Guardas: `pages/__tests__/responsivoOla2.test.ts` (`PAGINAS`) y `coloresPorTokens` (archivo nuevo limpio).

**Interfaces:**
- Produces: `cargasApi` con `subir(archivo: File, proposito: 'entrada'|'migracion', sucursalId?: number)`, `listar()`, `obtener(id)`, `responder(id, texto)`, `resolverDuda(id, numero, opcion, valor?)`, `deshacer(id, cambioId)`, `reintentar(id)`, `autorizar(id)`, `descartar(id)`, `etiquetas(id)`. Tipos TS espejo de `schemas.py`.

**Pantalla:**
- `CabeceraPagina` "Cargar mercancía".
- Zona de subida con `<input type="file" accept=".pdf,.xlsx,.csv">`; en teléfono se abre el selector nativo.
- Selector de propósito "Entrada de mercancía" / "Migración de catálogo" y selector de sucursal (por omisión `reglas_carga.sucursal_recibe`).
- Lista de cargas: tabla en PC, `ListaTarjetas` en teléfono, con folio, archivo, estado (`StatusChip`), piezas, quién y cuándo. Cada fila navega a `/inventory/cargas/:id`.

- [ ] **Step 1: Write the failing tests** (vitest con api mockeada)

```ts
it('sube el archivo con el propósito elegido y navega al plan', ...)
it('rechaza en cliente archivos de más de 20 MB con mensaje', ...)
it('en teléfono muestra tarjetas, no tabla', ...)
```

- [ ] **Step 2–4:** fail → implement → pass (`npx vitest run src/pages/inventory/cargas`)
- [ ] **Step 5: Commit** — `feat(cargas): pantalla de lista y subida`

---

### Task 13: Frontend — plan, dudas, respuestas, autorizar y resumen

**Files:**
- Create:
  - `frontend/src/pages/inventory/cargas/CargaPlan.tsx`
  - `frontend/src/pages/inventory/cargas/componentes/TarjetaDuda.tsx`, `TablaPlan.tsx`, `CambiosAntesDespues.tsx`, `ResumenEtiquetas.tsx`
  - `frontend/src/pages/inventory/cargas/__tests__/CargaPlan.test.tsx`

**Comportamiento:**
- **Estado `leyendo`:** `Spinner` con "Leyendo el documento…", y consulta `obtener` cada 3 s hasta que cambie.
- **Estado `error`:** `ErrorState` con el mensaje y el botón "Volver a intentar".
- **Estado `plan`:**
  - contadores por clase arriba (`KpiCard` o `Badge`);
  - dudas abiertas como `TarjetaDuda` numeradas, cada opción como botón con la recomendada primero y marcada "Recomendado";
  - en dudas de texto, un input pequeño.
- **Caja de respuesta:**
  - `textarea` fija abajo en teléfono, con placeholder "Contesta por número: 1. … 2. …";
  - botón "Enviar";
  - tras enviar, `CambiosAntesDespues` (lista por grupo: campo, antes → después) con "Deshacer", y los rechazos en un aviso.
- **`TablaPlan`:** agrupado por producto, con marca, nombre, SKU, tallas × piezas, precio, costo y clase. En teléfono, `ListaTarjetas`. YA CARGADO e IGNORADO en gris.
- **Autorizar:**
  - habilitado solo sin dudas abiertas y para ADMINISTRADOR/DUEÑO;
  - abre `ConfirmDialog` con el resumen: productos nuevos, piezas, valor a costo;
  - al confirmar llama `autorizar`.
- **Estado `aplicada`:** `ResumenEtiquetas` con la tabla Marca · Producto · SKU · Talla · Código · Piezas · Precio y el botón "Imprimir etiquetas" → `/labels?carga=<id>`.
- **Descartar:** con `ConfirmDialog`.

- [ ] **Step 1: Write the failing tests**

```ts
it('mientras lee, consulta cada 3 s y luego muestra el plan', ...)   // fake timers
it('un botón de opción llama resolverDuda con su clave', ...)
it('enviar respuesta muestra antes/después y rechazos', ...)
it('Autorizar deshabilitado con dudas abiertas', ...)
it('Autorizar no aparece para GERENTE', ...)
it('tras autorizar muestra el resumen y el enlace a /labels?carga=', ...)
it('error muestra Volver a intentar y llama reintentar', ...)
```

- [ ] **Step 2–4:** fail → implement → pass
- [ ] **Step 5: Commit** — `feat(cargas): pantalla del plan con dudas, respuestas y autorización`

---

### Task 14: Empresa — reglas de carga e instrucciones de la IA

**Files:**
- Create: `frontend/src/pages/core/ReglasCarga.tsx`, `frontend/src/pages/core/__tests__/ReglasCarga.test.tsx`
- Modify: `frontend/src/pages/core/Organization.tsx` (secciones "Instrucciones para la IA" con un `textarea` de `ai_instrucciones`, y "Reglas de carga", visibles solo con el módulo `ai`), `frontend/src/api/organization.ts` (tipos `ReglasCarga`)

**Comportamiento:**
- Formulario de `ReglasCarga`:
  - costo si falta: radio, más fracción;
  - IVA: switch;
  - sucursal que recibe y activar en;
  - mapa de tallas: pares editables;
  - tipos de prenda: filas tipo → código SKU → departamento (selector);
  - materiales aparte y material normal;
  - género por marca: filas, con la marca como selector de marcas existentes;
  - género por omisión, sufijo de dama, matriz por omisión;
  - precios por familia: filas tipo → marca opcional → lista de precios;
  - ventana de días.
- Guarda con `PUT` de la organización. Los errores 422 se muestran junto al campo.

- [ ] **Step 1: Write the failing tests**

```ts
it('carga reglas existentes y guarda cambios con PUT', ...)
it('agregar una fila de tipo de prenda la envía en reglas_carga.tipos', ...)
it('sin módulo ai no muestra las secciones', ...)
```

- [ ] **Step 2–4:** fail → implement → pass
- [ ] **Step 5: Commit** — `feat(organizacion): reglas de carga e instrucciones de la IA en Empresa`

---

### Task 15: Documentación y verificación completa

**Files:**
- Modify:
  - `docs/API_REFERENCE.md` (sección `/api/cargas` y el filtro `carga_id` de labels)
  - `docs/FRONTEND_VIEWS.md` (`/inventory/cargas`, `/inventory/cargas/:id`)
  - `docs/DATA_MODEL.md` (tablas `cargas_*`, `organization.reglas_carga`)
  - `.env.example` (`ANTHROPIC_API_KEY`, `AI_MODELO=claude-opus-5-5`, `AI_TOKENS_DIA_ORG`)
  - `docs/DEPLOY.md` (variables nuevas y `pip` de `anthropic`/`pypdf` en la imagen)
  - `docs/playbooks/altas-de-clientes.md` §9 (la fila "Leer exportación de otro POS" apunta a Cargar mercancía)
- Create: `docs/ai/cargar-mercancia.md`. Contenido:
  - cómo activar el módulo `ai` a una org;
  - cómo llenar reglas e instrucciones;
  - qué ve el proveedor: documento, encabezados y resumen del plan; nunca clientes ni usuarios;
  - costos aproximados por carga;
  - cómo leer una carga en `error`.

- [ ] **Step 1: Escribir los docs** (sin datos de tiendas).
- [ ] **Step 2: Suite completa backend:** `python3 -m pytest -q --ignore=tests/test_cash_complete.py`. Expected: 0 fallos nuevos frente a `main`.
- [ ] **Step 3: Frontend:** `cd frontend && npx vitest run && npm run build`. Expected: todo verde; `tsc` sin errores; el presupuesto de `frontend/presupuesto_bundle.json` no sube (cargas en su propio chunk).
- [ ] **Step 4: Commit** — `docs(cargas): referencia, vistas, modelo de datos y guía de la IA`
