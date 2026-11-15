"""Respuestas en texto libre: el modelo solo traduce a operaciones validadas."""
import json
from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.ai.cliente_anthropic import ClienteEstructuradoFalso
from app.modules.ai.models import AiUsoDiario
from app.modules.ai.uso import registrar_uso
from app.modules.cargas.models import CargaDuda, CargaMercancia, CargaRenglon
from app.modules.cargas.operaciones import aplicar_operaciones, recalcular_plan
from app.modules.cargas.respuestas import ESQUEMA_OPERACIONES, interpretar_respuesta
from app.modules.cargas.schemas import RespuestaTexto
from app.modules.cargas.tipos import RenglonCrudo
from app.modules.customers.models import Customer
from app.modules.products.models import Brand, Department

REGLAS = {
    "costo_si_falta": "fraccion_precio",
    "escala_ropa": ["Ch", "M", "G"],
    "tipos": {"Playera": {"codigo_sku": "PLAY", "departamento": "Playeras"}},
    "genero_por_omision": "UNISEX",
}


def _crudo(**kw):
    base = dict(descripcion_original="Playera Marca Uno", marca="Marca Uno", tipo="Playera",
                talla="M", cantidad="2", precio=None, origen="Hoja1!R2")
    base.update(kw)
    return RenglonCrudo(**base).model_dump(mode="json")


@pytest.fixture()
def carga(db, org):
    """Dudas: 1 marca nueva (Casa Dos), 2 precio faltante (renglones 1-2), 3 departamento."""
    org.reglas_carga = REGLAS
    db.add_all([Brand(name="Marca Uno", organization_id=org.id),
                Department(name="Playeras", organization_id=org.id)])
    c = CargaMercancia(organization_id=org.id, folio=1, estado="plan", archivo_nombre="lista.xlsx")
    db.add(c)
    db.flush()
    crudos = [_crudo(talla="M"), _crudo(talla="G", cantidad="1"),
              _crudo(descripcion_original="Pantalon Casa Dos", marca="Casa Dos",
                     tipo="Pantalon", talla="Ch", precio="300")]
    for i, cr in enumerate(crudos, 1):
        db.add(CargaRenglon(organization_id=org.id, carga_id=c.id, orden=i, crudo=cr,
                            cantidad=Decimal(cr["cantidad"])))
    db.flush()
    recalcular_plan(db, c)
    return c


def _respuesta(operaciones=(), no_entendido=()):
    return {"operaciones": list(operaciones), "no_entendido": list(no_entendido)}


def _resolver(numero, opcion="", valor=None):
    return {"op": "resolver_duda", "numero": numero, "opcion": opcion, "valor": valor}


def test_respuesta_numerada_produce_operaciones(db, org, admin_a, carga):
    falso = ClienteEstructuradoFalso([_respuesta([_resolver(2, valor="350"), _resolver(1, "crear")])])
    ops, rechazos, t_in, t_out = interpretar_respuesta(
        db, carga, "el 2 a 350 y la marca sí créala", falso, "")
    assert rechazos == [] and (t_in, t_out) == (0, 0)
    assert ops == [{"op": "resolver_duda", "numero": 2, "opcion": "", "valor": "350"},
                   {"op": "resolver_duda", "numero": 1, "opcion": "crear"}]
    assert falso.llamadas[0]["esquema"] is ESQUEMA_OPERACIONES
    uso = db.query(AiUsoDiario).filter_by(organization_id=org.id).one()
    assert uso.llamadas == 1

    cambio, rechazos = aplicar_operaciones(db, carga, admin_a, ops, "el 2 a 350")
    assert rechazos == [] and cambio is not None
    dudas = {d.numero: d for d in db.query(CargaDuda).filter_by(carga_id=carga.id)}
    assert dudas[1].estado == dudas[2].estado == "resuelta"
    precios = {r.orden: r.precio for r in db.query(CargaRenglon).filter_by(carga_id=carga.id)}
    assert precios[1] == precios[2] == Decimal("350")


def test_no_entendido_vuelve_como_texto(db, carga):
    falso = ClienteEstructuradoFalso([_respuesta(no_entendido=[
        {"numero": 4, "texto": "lo del color"}, {"numero": None, "texto": "lo otro"}])])
    ops, rechazos, _, _ = interpretar_respuesta(db, carga, "el 4 en azul y lo otro", falso, "")
    assert ops == []
    assert rechazos == ["No entendí el punto 4: lo del color", "No entendí: lo otro"]


def test_operaciones_inventadas_se_rechazan(db, carga):
    grupo = db.query(CargaRenglon).filter_by(carga_id=carga.id, orden=1).one().grupo
    falso = ClienteEstructuradoFalso([_respuesta([
        {"op": "fijar_campo", "renglones": [999], "grupo": None, "campo": "precio", "valor": "10"},
        {"op": "usar_existente", "grupo": grupo, "product_id": "no-existe"},
        {"op": "fijar_campo", "renglones": [1], "grupo": None, "campo": "proveedor", "valor": "x"},
        _resolver(3, valor="Pantalones"),
    ])])
    ops, rechazos, _, _ = interpretar_respuesta(db, carga, "el 1 a 10", falso, "")
    assert ops == [{"op": "resolver_duda", "numero": 3, "opcion": "", "valor": "Pantalones"}]
    assert rechazos == [
        "Operación 1: renglón 999 no es de esta carga",
        "Operación 2: el producto no-existe no es de tu catálogo",
        'Operación 3: el campo "proveedor" no se puede cambiar',
    ]


def test_texto_mayor_a_4000_da_422(db, carga):
    with pytest.raises(ValidationError):
        RespuestaTexto(texto="x" * 4001)
    assert RespuestaTexto(texto="x" * 4000).texto == "x" * 4000
    falso = ClienteEstructuradoFalso([])
    with pytest.raises(HTTPException) as e:
        interpretar_respuesta(db, carga, "x" * 4001, falso, "")
    assert e.value.status_code == 422
    assert falso.llamadas == []


def test_sin_cupo_no_llama_al_modelo(db, org, carga, monkeypatch):
    monkeypatch.setenv("AI_TOKENS_DIA_ORG", "100")
    registrar_uso(db, org.id, 150, 0)
    falso = ClienteEstructuradoFalso([])
    with pytest.raises(HTTPException) as e:
        interpretar_respuesta(db, carga, "el 2 a 350", falso, "")
    assert e.value.status_code == 429
    assert falso.llamadas == []


def test_modelo_solo_ve_resumen_sin_clientes(db, org, admin_a, cajero_a, carga):
    db.add(Customer(name="Cliente Secreto Uno", organization_id=org.id, phone="5550001111"))
    db.flush()
    falso = ClienteEstructuradoFalso([_respuesta()])
    interpretar_respuesta(db, carga, "el 2 a 350", falso, "Somos una boutique.")
    llamada = falso.llamadas[0]
    enviado = json.dumps(llamada["contenido"], ensure_ascii=False)
    for prohibido in ("Cliente Secreto Uno", "5550001111", cajero_a.username, admin_a.username,
                      carga.id, *[r.id for r in db.query(CargaRenglon).filter_by(carga_id=carga.id)]):
        assert prohibido not in enviado
    datos = json.loads(llamada["contenido"][0]["text"])
    assert [d["numero"] for d in datos["dudas_abiertas"]] == [1, 2, 3]
    assert datos["respuesta"] == "el 2 a 350"
    grupo = next(g for g in datos["grupos"] if g["marca"] == "Marca Uno")
    assert grupo["tallas"] == ["M", "G"] and grupo["renglones"] == [1, 2]
    assert set(grupo) == {"llave", "marca", "tipo", "tallas", "precio", "clase", "renglones"}
    assert "Somos una boutique." in llamada["sistema"]


def test_solo_ve_dudas_abiertas(db, admin_a, carga):
    aplicar_operaciones(db, carga, admin_a, [_resolver(1, "crear")], None)
    falso = ClienteEstructuradoFalso([_respuesta()])
    interpretar_respuesta(db, carga, "ok", falso, "")
    datos = json.loads(falso.llamadas[0]["contenido"][0]["text"])
    assert [d["numero"] for d in datos["dudas_abiertas"]] == [2, 3]


def _objetos(nodo):
    if isinstance(nodo, dict):
        if nodo.get("type") == "object" or (isinstance(nodo.get("type"), list) and "object" in nodo["type"]):
            yield nodo
        for v in nodo.values():
            yield from _objetos(v)
    elif isinstance(nodo, list):
        for v in nodo:
            yield from _objetos(v)


def test_esquema_estricto():
    objetos = list(_objetos(ESQUEMA_OPERACIONES))
    assert len(objetos) >= 8
    for o in objetos:
        assert o["additionalProperties"] is False
        assert sorted(o["required"]) == sorted(o["properties"])


def _fijar_precio(grupo, valor):
    return {"op": "fijar_campo", "renglones": None, "grupo": grupo, "campo": "precio", "valor": valor}


@pytest.mark.parametrize("texto, aceptado", [("ponle 2500", False), ("ponle 3,000", True),
                                             ("ponle $3,000.00", True)])
def test_monto_que_no_escribio_el_usuario_se_rechaza(db, carga, texto, aceptado):
    grupo = db.query(CargaRenglon).filter_by(carga_id=carga.id, orden=1).one().grupo
    falso = ClienteEstructuradoFalso([_respuesta([
        _fijar_precio(grupo, "3000"), _resolver(2, valor="3000"),
        {"op": "tipo_cambio", "moneda": "USD", "valor": "18"},
        _resolver(3, valor="Pantalones"),
    ])])
    ops, rechazos, _, _ = interpretar_respuesta(db, carga, texto, falso, "")
    assert {"op": "resolver_duda", "numero": 3, "opcion": "", "valor": "Pantalones"} in ops
    assert "No entendí: el monto 18 no aparece en tu respuesta" in rechazos
    if aceptado:
        assert _fijar_precio(grupo, "3000") | {"renglones": None} in [o | {"renglones": None} for o in ops]
        assert not any("3000" in r for r in rechazos)
    else:
        assert len(ops) == 1
        assert "No entendí: el monto 3000 no aparece en tu respuesta" in rechazos
        assert "No entendí el punto 2: el monto 3000 no aparece en tu respuesta" in rechazos


def test_carga_fuera_de_plan_no_gasta_tokens(db, carga):
    carga.estado = "aplicada"
    falso = ClienteEstructuradoFalso([])
    with pytest.raises(HTTPException) as e:
        interpretar_respuesta(db, carga, "el 2 a 350", falso, "")
    assert e.value.status_code == 409
    assert falso.llamadas == []


def test_respuesta_con_tope_de_16000_tokens(db, carga):
    from app.modules.cargas import respuestas
    assert respuestas.MAX_TOKENS == 16000
    falso = ClienteEstructuradoFalso([_respuesta()])
    interpretar_respuesta(db, carga, "hola", falso, "")
    assert falso.llamadas[0]["max_tokens"] == 16000


def test_respuesta_cortada_pide_contestar_en_partes(db, carga):
    from app.modules.ai.cliente_anthropic import RespuestaIncompleta
    falso = ClienteEstructuradoFalso([RespuestaIncompleta("cortada")])
    with pytest.raises(HTTPException) as e:
        interpretar_respuesta(db, carga, "1. a 350 2. a 400", falso, "")
    assert e.value.status_code == 422
    assert "demasiado larga" in e.value.detail and "en partes" in e.value.detail
    assert "documento" not in e.value.detail
