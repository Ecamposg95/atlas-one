"""Fase A0 del agente: modelo por tarea con respaldo, cupo configurable y
registro de consumo por llamada. La suite nunca llama a un proveedor real."""
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.ai import tareas
from app.modules.ai.models import AiLlamada, AiUsoDiario
from app.modules.ai.proveedores import (
    Proveedor, ProveedorAnthropic, ProveedorConRespaldo, ProveedorFalso, ProveedorNoDisponible,
    ProveedorOpenAI, Respuesta, RespuestaIncompleta,
)
from app.modules.ai.tareas import Opcion, cadena_de, cadena_global, proveedor_para, validar_ai_modelos
from app.modules.ai.uso import (
    Llamada, Medidor, limite_tokens_dia, registrar_llamadas, registrar_uso, verificar_cupo,
)
from app.services import plans

VARIABLES = ("AI_MODELOS_CONSULTA", "AI_MODELOS_CAPTURA", "AI_MODELOS_ANALISIS", "AI_MODELO",
             "ANTHROPIC_API_KEY", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL",
             "AI_TOKENS_DIA_ORG", "AI_TOKENS_DIA_USUARIO")


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch):
    for v in VARIABLES:
        monkeypatch.delenv(v, raising=False)
    tareas.reiniciar_proveedores()
    yield
    tareas.reiniciar_proveedores()


# ── interfaz ─────────────────────────────────────────────────────────────

def test_todas_las_implementaciones_cumplen_la_interfaz():
    compatible = ProveedorOpenAI("https://x.prueba/v1", "k", "m")
    try:
        for p in (ProveedorAnthropic("k", "m"), compatible, ProveedorFalso(),
                  ProveedorConRespaldo([ProveedorFalso()]), Medidor(ProveedorFalso())):
            assert isinstance(p, Proveedor), type(p).__name__
            assert p.nombre and p.modelo
    finally:
        compatible.cerrar()


# ── lista de modelos por tarea ───────────────────────────────────────────

def test_omision_claude_en_las_tres():
    assert cadena_global("consulta") == [Opcion("anthropic", "claude-haiku-5-5")]
    assert cadena_global("captura") == [Opcion("anthropic", "claude-opus-5-5")]
    assert cadena_global("analisis") == [Opcion("anthropic", "claude-opus-5-5")]


def test_variable_global_con_lista_ordenada(monkeypatch):
    monkeypatch.setenv("AI_MODELOS_CONSULTA", " anthropic:claude-haiku-5-5 , compatible:gemini-3.8-flash, basura:: ,,")
    assert cadena_global("consulta") == [Opcion("anthropic", "claude-haiku-5-5"),
                                         Opcion("compatible", "gemini-3.8-flash"), Opcion("basura", ":")]
    # Las otras tareas no se tocan.
    assert cadena_global("analisis") == [Opcion("anthropic", "claude-opus-5-5")]


def test_ai_modelo_heredado_solo_mueve_captura(monkeypatch):
    monkeypatch.setenv("AI_MODELO", "claude-sonnet-5-5")
    assert cadena_global("captura") == [Opcion("anthropic", "claude-sonnet-5-5")]
    assert cadena_global("consulta") == [Opcion("anthropic", "claude-haiku-5-5")]
    monkeypatch.setenv("AI_MODELOS_CAPTURA", "anthropic:claude-opus-5-5")
    assert cadena_global("captura") == [Opcion("anthropic", "claude-opus-5-5")]  # la lista nueva gana


def test_tarea_desconocida():
    with pytest.raises(ValueError):
        cadena_global("resumen")


def test_excepcion_por_organizacion(db, org, monkeypatch):
    monkeypatch.setenv("AI_MODELOS_CONSULTA", "anthropic:claude-haiku-5-5")
    org.ai_modelos = {"consulta": ["compatible:gemini-3.8-flash", "anthropic:claude-haiku-5-5"]}
    db.flush()
    assert cadena_de(db, org.id, "consulta") == [Opcion("compatible", "gemini-3.8-flash"),
                                                 Opcion("anthropic", "claude-haiku-5-5")]
    # Tarea sin excepción: la global.
    assert cadena_de(db, org.id, "captura") == [Opcion("anthropic", "claude-opus-5-5")]
    # Una excepción ilegible no deja a la tienda sin IA: cae a la global.
    org.ai_modelos = {"consulta": ["???"]}
    db.flush()
    assert cadena_de(db, org.id, "consulta") == [Opcion("anthropic", "claude-haiku-5-5")]


def test_validar_ai_modelos():
    assert validar_ai_modelos(None) is None and validar_ai_modelos({}) is None
    assert validar_ai_modelos({"consulta": [" Compatible:gemini-3.8-flash ", "anthropic:claude-haiku-5-5"]}) == {
        "consulta": ["compatible:gemini-3.8-flash", "anthropic:claude-haiku-5-5"]}
    for malo in ({"resumen": ["anthropic:x"]}, {"consulta": []}, {"consulta": ["anthropic"]},
                 {"consulta": "anthropic:x"}, ["anthropic:x"], {"consulta": ["con espacio:x"]}):
        with pytest.raises(ValueError):
            validar_ai_modelos(malo)


def test_sin_llave_503_nombra_la_variable(monkeypatch):
    with pytest.raises(HTTPException) as e:
        proveedor_para(None, None, "captura")
    assert e.value.status_code == 503
    assert e.value.detail == "IA no configurada: falta ANTHROPIC_API_KEY en el servidor."
    monkeypatch.setenv("AI_MODELOS_CAPTURA", "anthropic:claude-opus-5-5,compatible")
    with pytest.raises(HTTPException) as e:
        proveedor_para(None, None, "captura")
    assert e.value.detail == "IA no configurada: falta ANTHROPIC_API_KEY o LLM_API_KEY en el servidor."


def test_las_entradas_sin_llave_se_saltan(monkeypatch):
    monkeypatch.setenv("AI_MODELOS_CONSULTA", "anthropic:claude-haiku-5-5,compatible:gemini-3.8-flash")
    monkeypatch.setenv("LLM_API_KEY", "k")
    p = proveedor_para(None, None, "consulta")
    assert [(o.nombre, o.modelo) for o in p.opciones] == [("compatible", "gemini-3.8-flash")]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    p = proveedor_para(None, None, "consulta")
    assert [(o.nombre, o.modelo) for o in p.opciones] == [
        ("anthropic", "claude-haiku-5-5"), ("compatible", "gemini-3.8-flash")]


# ── respaldo ─────────────────────────────────────────────────────────────

def test_respaldo_cae_al_siguiente_si_la_falla_es_recuperable():
    a = ProveedorFalso([ProveedorNoDisponible("sin cuota", recuperable=True)], nombre="a", modelo="m1")
    b = ProveedorFalso([{"x": 1}], nombre="b", modelo="m2")
    r = ProveedorConRespaldo([a, b]).generar_json(sistema="s", contenido=[], esquema={})
    assert r.datos == {"x": 1} and (r.proveedor, r.modelo) == ("b", "m2")
    assert len(a.llamadas) == 1 and len(b.llamadas) == 1

    a = ProveedorFalso([ProveedorNoDisponible("5xx", recuperable=True)], nombre="a", modelo="m1")
    b = ProveedorFalso([Respuesta(texto="hola", tokens_entrada=4, tokens_salida=2)], nombre="b", modelo="m2")
    r = ProveedorConRespaldo([a, b]).conversar(mensajes=[{"role": "user", "content": "x"}])
    assert r.texto == "hola" and (r.proveedor, r.modelo) == ("b", "m2")


@pytest.mark.parametrize("falla", [
    ProveedorNoDisponible("el modelo rechazó"),            # no recuperable
    RespuestaIncompleta("cortada"),
])
def test_respaldo_no_tapa_fallas_que_otro_modelo_no_arregla(falla):
    a = ProveedorFalso([falla])
    b = ProveedorFalso([{"x": 1}])
    with pytest.raises(type(falla)):
        ProveedorConRespaldo([a, b]).generar_json(sistema="s", contenido=[], esquema={})
    assert b.llamadas == []


def test_respaldo_agotado_propaga_la_ultima_falla():
    a = ProveedorFalso([ProveedorNoDisponible("uno", recuperable=True)])
    b = ProveedorFalso([ProveedorNoDisponible("dos", recuperable=True)])
    with pytest.raises(ProveedorNoDisponible, match="dos"):
        ProveedorConRespaldo([a, b]).generar_json(sistema="s", contenido=[], esquema={})


# ── cupo ─────────────────────────────────────────────────────────────────

def test_cupo_por_plan_es_provisional_y_alto():
    assert set(plans.CUPO_IA_TOKENS_DIA) == set(plans.claves_validas())
    assert plans.cupo_ia_tokens_dia("SCALE") == plans.CUPO_IA_TOKENS_DIA_PROVISIONAL >= 1_000_000
    assert plans.cupo_ia_tokens_dia(None) == plans.CUPO_IA_TOKENS_DIA["FREE"]
    assert plans.cupo_ia_tokens_dia("no-existe") == plans.CUPO_IA_TOKENS_DIA["FREE"]


def test_orden_del_cupo_org_variable_plan(db, org, monkeypatch):
    org.plan = "SCALE"
    db.flush()
    monkeypatch.setitem(plans.CUPO_IA_TOKENS_DIA, "SCALE", 777)
    assert limite_tokens_dia(db, org.id) == 777              # el del plan
    monkeypatch.setenv("AI_TOKENS_DIA_ORG", "500")
    assert limite_tokens_dia(db, org.id) == 500              # la variable global lo tapa
    monkeypatch.setenv("AI_TOKENS_DIA_ORG", "mucho")
    assert limite_tokens_dia(db, org.id) == 777              # variable inválida = no puesta
    monkeypatch.setenv("AI_TOKENS_DIA_ORG", "500")
    org.ai_tokens_dia = 9000
    db.flush()
    assert limite_tokens_dia(db, org.id) == 9000             # la excepción de la org gana


def test_verificar_cupo_por_usuario(db, org, admin_a, cajero_a, monkeypatch):
    registrar_uso(db, org.id, 60, 40, user_id=cajero_a.id, rol=cajero_a.role, tarea="consulta")
    verificar_cupo(db, org.id, cajero_a.id)                  # sin tope por usuario: pasa
    monkeypatch.setenv("AI_TOKENS_DIA_USUARIO", "100")
    with pytest.raises(HTTPException) as e:
        verificar_cupo(db, org.id, cajero_a.id)
    assert e.value.status_code == 429 and "Alcanzaste tu límite" in e.value.detail
    verificar_cupo(db, org.id, admin_a.id)                   # otra persona no carga con ese gasto
    verificar_cupo(db, org.id)                               # sin persona no aplica el tope


# ── registro de consumo ──────────────────────────────────────────────────

def test_registra_una_fila_por_llamada_con_todos_los_datos(db, org, cajero_a):
    registrar_llamadas(db, org.id, [
        Llamada(tokens_entrada=100, tokens_salida=20, proveedor="anthropic", modelo="claude-haiku-5-5"),
        Llamada(tokens_entrada=30, tokens_salida=5, proveedor="compatible", modelo="gemini-3.8-flash"),
    ], user_id=cajero_a.id, rol=cajero_a.role, tarea="consulta")
    filas = db.query(AiLlamada).filter_by(organization_id=org.id).order_by(AiLlamada.id).all()
    assert [(f.user_id, f.rol, f.tarea, f.proveedor, f.modelo, f.tokens_entrada, f.tokens_salida)
            for f in filas] == [
        (cajero_a.id, "CAJERO", "consulta", "anthropic", "claude-haiku-5-5", 100, 20),
        (cajero_a.id, "CAJERO", "consulta", "compatible", "gemini-3.8-flash", 30, 5),
    ]
    dia = db.query(AiUsoDiario).filter_by(organization_id=org.id).one()
    assert (dia.tokens_entrada, dia.tokens_salida, dia.llamadas) == (130, 25, 2)
    assert filas[0].fecha == dia.fecha


def test_sin_llamadas_no_escribe_nada(db, org):
    registrar_llamadas(db, org.id, [], tarea="captura")
    assert db.query(AiUsoDiario).filter_by(organization_id=org.id).count() == 0


def test_la_suma_no_se_pierde_con_una_lectura_vieja(db, org):
    """Dos sesiones sobre la misma fila: la que la leyó antes no pisa lo que la
    otra sumó después. Con leer-sumar-guardar en Python esto daba 13, no 18."""
    registrar_uso(db, org.id, 10, 0)
    vieja = db.query(AiUsoDiario).filter_by(organization_id=org.id).one()
    assert vieja.tokens_entrada == 10                         # `db` ya tiene la fila cargada
    otra = Session(bind=db.get_bind(), autoflush=False)
    try:
        registrar_uso(otra, org.id, 5, 0)
        otra.flush()
    finally:
        otra.close()
    registrar_uso(db, org.id, 3, 0)
    db.expire_all()
    fila = db.query(AiUsoDiario).filter_by(organization_id=org.id).one()
    assert (fila.tokens_entrada, fila.llamadas) == (18, 3)


def test_registrar_uso_emite_un_upsert(db, org):
    from sqlalchemy import event

    sentencias = []
    motor = db.get_bind().engine
    escucha = lambda conn, cur, sql, *a: sentencias.append(sql)  # noqa: E731
    event.listen(motor, "before_cursor_execute", escucha)
    try:
        registrar_uso(db, org.id, 1, 1)
    finally:
        event.remove(motor, "before_cursor_execute", escucha)
    sobre_el_dia = [s for s in sentencias if "ai_uso_diario" in s]
    assert len(sobre_el_dia) == 1 and "ON CONFLICT" in sobre_el_dia[0].upper()
    assert not any(s.lstrip().upper().startswith("SELECT") and "ai_uso_diario" in s for s in sentencias)


def test_medidor_anota_cada_respuesta():
    falso = ProveedorFalso([{"a": 1}, Respuesta(texto="x", tokens_entrada=7, tokens_salida=3)],
                           nombre="falso", modelo="m")
    m = Medidor(falso)
    m.generar_json(sistema="s", contenido=[], esquema={})
    m.conversar(mensajes=[])
    assert [(ll.proveedor, ll.modelo, ll.tokens_entrada, ll.tokens_salida) for ll in m.llamadas] == [
        ("falso", "m", 0, 0), ("falso", "m", 7, 3)]


# ── la plataforma configura; la tienda no ────────────────────────────────

def test_plataforma_guarda_modelos_y_cupo_y_la_tienda_no(client, db, org, auth_superadmin, auth_admin_a):
    r = client.put(f"/api/platform/organizations/{org.id}", headers=auth_superadmin,
                   json={"ai_modelos": {"consulta": ["compatible:gemini-3.8-flash"]}, "ai_tokens_dia": 5000})
    assert r.status_code == 200, r.text
    db.refresh(org)
    assert org.ai_modelos == {"consulta": ["compatible:gemini-3.8-flash"]} and org.ai_tokens_dia == 5000

    r = client.put(f"/api/platform/organizations/{org.id}", headers=auth_superadmin,
                   json={"ai_modelos": {"resumen": ["anthropic:x"]}})
    assert r.status_code == 422

    # El administrador de la tienda no puede subirse el cupo ni cambiar de modelo.
    r = client.put("/api/organization/", headers=auth_admin_a,
                   json={"ai_tokens_dia": 999999999, "ai_modelos": {"consulta": ["anthropic:claude-opus-5-5"]}})
    db.refresh(org)
    assert org.ai_tokens_dia == 5000 and org.ai_modelos == {"consulta": ["compatible:gemini-3.8-flash"]}
