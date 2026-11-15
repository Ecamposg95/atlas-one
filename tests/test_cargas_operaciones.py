"""Operaciones sobre el plan de una carga: validar, aplicar, recalcular y deshacer."""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.modules.cargas.models import CargaCambio, CargaDuda, CargaMercancia, CargaRenglon
from app.modules.cargas.operaciones import (
    aplicar_operaciones, deshacer_cambio, recalcular_plan,
)
from app.modules.cargas.tipos import RenglonCrudo
from app.modules.products.models import Brand, Department, Product, ProductVariant
from app.modules.tenants.models import Organization

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


CRUDOS = [
    _crudo(talla="M"),
    _crudo(talla="G", cantidad="1"),
    _crudo(descripcion_original="Pantalon Casa Dos", marca="Casa Dos", tipo="Pantalon",
           talla="Ch", precio="300"),
]


def _armar(db, org, crudos=None, **carga_kw):
    org.reglas_carga = REGLAS
    if not db.query(Brand).filter_by(organization_id=org.id, name="Marca Uno").first():
        db.add_all([Brand(name="Marca Uno", organization_id=org.id),
                    Department(name="Playeras", organization_id=org.id)])
    carga = CargaMercancia(organization_id=org.id, folio=1, estado="plan",
                           archivo_nombre="lista.xlsx", **carga_kw)
    db.add(carga)
    db.flush()
    for i, c in enumerate(crudos or CRUDOS, 1):
        db.add(CargaRenglon(organization_id=org.id, carga_id=carga.id, orden=i, crudo=c,
                            cantidad=Decimal(c["cantidad"])))
    db.flush()
    recalcular_plan(db, carga)
    return carga


def _renglones(db, carga):
    return {r.orden: r for r in db.query(CargaRenglon).filter_by(carga_id=carga.id).all()}


def _dudas(db, carga):
    return {d.numero: d for d in db.query(CargaDuda).filter_by(carga_id=carga.id).all()}


def _foto(db, carga):
    """Estado comparable del plan (renglones, dudas, monedas y lectura)."""
    db.flush()
    return (
        sorted((r.orden, repr(r.normalizado), r.clase, r.grupo, r.product_id, r.sku,
                str(r.precio), str(r.costo), str(r.cantidad))
               for r in _renglones(db, carga).values()),
        sorted((d.numero, d.clave, d.estado, d.respuesta, d.texto)
               for d in _dudas(db, carga).values()),
        repr(carga.monedas), repr(carga.lectura),
    )


def test_recalcular_arma_plan_y_numera_dudas(db, org):
    carga = _armar(db, org)
    rs = _renglones(db, carga)
    assert rs[1].grupo == rs[2].grupo and rs[1].grupo != rs[3].grupo
    assert {r.clase for r in rs.values()} == {"NUEVO"}
    assert rs[1].sku == "PLAY" and rs[2].sku == "PLAY-G"
    dudas = _dudas(db, carga)
    assert [(n, d.tipo, d.estado) for n, d in sorted(dudas.items())] == [
        (1, "marca_nueva", "abierta"), (2, "precio_faltante", "abierta"),
        (3, "departamento", "abierta")]
    assert dudas[2].renglones == [1, 2]


def test_fijar_precio_a_grupo_recalcula_y_cierra_duda(db, org, admin_a):
    carga = _armar(db, org)
    grupo = _renglones(db, carga)[1].grupo
    cambio, rechazos = aplicar_operaciones(
        db, carga, admin_a,
        [{"op": "fijar_campo", "grupo": grupo, "campo": "precio", "valor": "$350"}],
        "el 2 a 350")
    assert rechazos == []
    rs = _renglones(db, carga)
    assert rs[1].precio == Decimal("350") and rs[2].precio == Decimal("350")
    assert rs[1].costo == Decimal("175.00")  # fracción del precio
    assert rs[3].precio == Decimal("300")
    dudas = _dudas(db, carga)
    assert dudas[2].estado == "resuelta"
    assert dudas[1].estado == "abierta" and dudas[3].estado == "abierta"
    assert len(dudas) == 3
    assert cambio.secuencia == 1 and cambio.texto == "el 2 a 350" and cambio.user_id == admin_a.id
    resumen = cambio.despues["resumen"]
    afectado = next(g for g in resumen["grupos"] if g["grupo"] == rs[1].grupo)
    assert afectado["renglones"] == [1, 2]
    assert afectado["cambios"]["precio"] == {"antes": None, "despues": "350"}
    assert resumen["dudas_resueltas"] == [2]


def test_override_sobrevive_al_recalculo(db, org, admin_a):
    carga = _armar(db, org)
    aplicar_operaciones(db, carga, admin_a, [
        {"op": "fijar_campo", "renglones": [3], "campo": "departamento", "valor": "Pantalones"},
        {"op": "ignorar", "renglones": [2]},
    ], None)
    recalcular_plan(db, carga)
    rs = _renglones(db, carga)
    assert rs[3].normalizado["departamento"] == "Pantalones"
    assert rs[3].normalizado["_usuario"]["departamento"] == "Pantalones"
    assert rs[2].clase == "IGNORADO"
    assert _dudas(db, carga)[3].estado == "resuelta"  # su causa desapareció


def test_resolver_duda_sin_operaciones_queda_resuelta(db, org, admin_a):
    carga = _armar(db, org)
    cambio, rechazos = aplicar_operaciones(
        db, carga, admin_a, [{"op": "resolver_duda", "numero": 1, "opcion": "crear"}], None)
    assert rechazos == [] and cambio is not None
    d = _dudas(db, carga)[1]
    assert d.estado == "resuelta" and d.resuelta_por == admin_a.id
    assert "Casa Dos" in d.respuesta
    recalcular_plan(db, carga)  # la causa sigue, pero la contestada no se reabre
    assert _dudas(db, carga)[1].estado == "resuelta"
    assert len(_dudas(db, carga)) == 3


def test_resolver_duda_con_texto(db, org, admin_a):
    carga = _armar(db, org)
    _, rechazos = aplicar_operaciones(db, carga, admin_a, [
        {"op": "resolver_duda", "numero": 2, "opcion": "", "valor": "1,250.50"},
        {"op": "resolver_duda", "numero": 3, "opcion": "", "valor": "Pantalones"},
    ], None)
    assert rechazos == []
    rs = _renglones(db, carga)
    assert rs[1].precio == Decimal("1250.50")
    assert rs[3].normalizado["departamento"] == "Pantalones"
    dudas = _dudas(db, carga)
    assert dudas[2].estado == dudas[3].estado == "resuelta"
    assert dudas[2].respuesta == "1,250.50"


def test_dudas_nuevas_toman_numeros_siguientes(db, org, admin_a):
    carga = _armar(db, org)
    aplicar_operaciones(db, carga, admin_a, [
        {"op": "fijar_campo", "renglones": [1], "campo": "marca", "valor": "Otra Firma"}], None)
    dudas = _dudas(db, carga)
    assert dudas[2].estado == "abierta" and dudas[2].renglones == [2]
    assert (dudas[4].tipo, dudas[4].estado) == ("marca_nueva", "abierta")
    assert (dudas[5].tipo, dudas[5].renglones) == ("precio_faltante", [1])


def test_operacion_con_renglon_ajeno_se_rechaza(db, org, admin_a):
    carga = _armar(db, org)
    antes = _foto(db, carga)
    cambio, rechazos = aplicar_operaciones(
        db, carga, admin_a, [{"op": "ignorar", "renglones": [999]}], None)
    assert cambio is None
    assert rechazos == ["Operación 1: renglón 999 no es de esta carga"]
    assert _foto(db, carga) == antes
    assert db.query(CargaCambio).filter_by(carga_id=carga.id).count() == 0


def test_lote_mixto_aplica_las_validas(db, org, admin_a):
    carga = _armar(db, org)
    cambio, rechazos = aplicar_operaciones(db, carga, admin_a, [
        {"op": "ignorar", "renglones": [3]},
        {"op": "fijar_campo", "renglones": [1], "campo": "sku", "valor": "X"},
        {"op": "fijar_campo", "renglones": [1], "campo": "precio", "valor": "abc"},
        {"op": "fijar_campo", "renglones": [1], "campo": "costo", "valor": "-5"},
        {"op": "resolver_duda", "numero": 1, "opcion": "otra"},
        {"op": "resolver_duda", "numero": 9, "opcion": "crear"},
        {"op": "volar"},
        {"op": "ignorar", "renglones": [1], "inventado": True},
    ], None)
    assert cambio is not None and cambio.operaciones == [{"op": "ignorar", "renglones": [3]}]
    assert [r.split(":", 1)[0] for r in rechazos] == [f"Operación {n}" for n in range(2, 9)]
    assert 'el campo "sku" no se puede cambiar' in rechazos[0]
    assert '"abc" no es una cantidad' in rechazos[1]
    assert "negativo" in rechazos[2]
    assert '"otra" no es una respuesta válida' in rechazos[3]
    assert "la pregunta 9 no existe" in rechazos[4]
    assert 'no sé hacer "volar"' in rechazos[5]
    assert '"inventado"' in rechazos[6]
    assert _renglones(db, carga)[3].clase == "IGNORADO"


def test_duda_ya_contestada_se_rechaza(db, org, admin_a):
    carga = _armar(db, org)
    _, rechazos = aplicar_operaciones(db, carga, admin_a, [
        {"op": "resolver_duda", "numero": 1, "opcion": "crear"},
        {"op": "resolver_duda", "numero": 1, "opcion": "crear"},
    ], None)
    assert rechazos == ["Operación 2: la pregunta 1 ya está contestada"]


def test_product_id_de_otra_org_se_rechaza(db, org, admin_a):
    otra = Organization(name="Otra Org", status="ACTIVE")
    db.add(otra)
    db.flush()
    ajeno = Product(name="Playera ajena", organization_id=otra.id, is_active=True)
    db.add(ajeno)
    db.flush()
    carga = _armar(db, org)
    grupo = _renglones(db, carga)[1].grupo
    cambio, rechazos = aplicar_operaciones(db, carga, admin_a, [
        {"op": "usar_existente", "grupo": grupo, "product_id": ajeno.id}], None)
    assert cambio is None
    assert rechazos == [f"Operación 1: el producto {ajeno.id} no es de tu catálogo"]
    assert _renglones(db, carga)[1].product_id is None


def test_nuevo_producto_y_usar_existente(db, org, admin_a):
    carga = _armar(db, org)
    marca = db.query(Brand).filter_by(organization_id=org.id, name="Marca Uno").one()
    depto = db.query(Department).filter_by(organization_id=org.id, name="Playeras").one()
    p = Product(name="Playera básica", organization_id=org.id, is_active=True,
                brand_id=marca.id, department_id=depto.id)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku="UNO-9", size="M", organization_id=org.id,
                       price=Decimal("350"), cost=Decimal("100"))
    db.add(v)
    db.flush()
    recalcular_plan(db, carga)
    rs = _renglones(db, carga)
    assert (rs[1].clase, rs[1].product_id, rs[1].variant_id, rs[1].sku) == ("SUMA", p.id, v.id, "UNO-9")
    assert (rs[2].clase, rs[2].product_id) == ("NUEVO", p.id)

    grupo = rs[1].grupo
    aplicar_operaciones(db, carga, admin_a, [{"op": "nuevo_producto", "grupo": grupo}], None)
    rs = _renglones(db, carga)
    assert (rs[1].clase, rs[1].product_id) == ("NUEVO", None)
    assert not any(d.tipo == "casi_igual" and d.estado == "abierta"
                   for d in _dudas(db, carga).values())

    aplicar_operaciones(db, carga, admin_a, [
        {"op": "usar_existente", "grupo": grupo, "product_id": p.id}], None)
    rs = _renglones(db, carga)
    assert (rs[1].clase, rs[1].product_id) == ("SUMA", p.id)


def test_tipo_cambio_recalcula_costos(db, org, admin_a):
    crudos = [_crudo(precio="200", costo_unitario="5", moneda="USD")]
    carga = _armar(db, org, crudos, monedas={"USD": None})
    d = _dudas(db, carga)[1]
    assert d.tipo == "tipo_cambio"
    _, rechazos = aplicar_operaciones(db, carga, admin_a, [
        {"op": "resolver_duda", "numero": 1, "opcion": "", "valor": "18,40"},
        {"op": "tipo_cambio", "moneda": "EUR", "valor": "20"},
    ], None)
    assert rechazos == ["Operación 2: la moneda EUR no aparece en esta carga"]
    assert Decimal(str(carga.monedas["USD"])) == Decimal("18.4")
    assert _renglones(db, carga)[1].costo == Decimal("92.00")
    assert _dudas(db, carga)[1].estado == "resuelta"


def test_rol_columna(db, org, admin_a):
    lectura = {"tablas": [{"pestana": "Hoja1", "encabezados": ["Modelo", "Talla", "Importe"],
                           "mapa": {"campos": {}, "columnas_dinero": [2], "texto_libre": []},
                           "rol_dinero": {}}]}
    carga = _armar(db, org, [_crudo(precio="100")], lectura=lectura)
    d = next(d for d in _dudas(db, carga).values() if d.tipo == "columnas_dinero")
    _, rechazos = aplicar_operaciones(db, carga, admin_a, [
        {"op": "rol_columna", "tabla": 0, "columna": 1, "rol": "precio"},
        {"op": "rol_columna", "tabla": 3, "columna": 2, "rol": "precio"},
        {"op": "resolver_duda", "numero": d.numero, "opcion": "costo"},
    ], None)
    assert rechazos == ["Operación 1: la columna 1 de la tabla 0 no es una columna de dinero",
                        "Operación 2: la tabla 3 no existe en esta carga"]
    assert carga.lectura["tablas"][0]["rol_dinero"] == {"2": "costo"}
    assert _dudas(db, carga)[d.numero].estado == "resuelta"


def test_deshacer_restaura_antes(db, org, admin_a):
    carga = _armar(db, org, monedas={"USD": None})
    antes = _foto(db, carga)
    grupo = _renglones(db, carga)[1].grupo
    cambio, _ = aplicar_operaciones(db, carga, admin_a, [
        {"op": "fijar_campo", "grupo": grupo, "campo": "precio", "valor": "350"},
        {"op": "fijar_campo", "renglones": [1], "campo": "marca", "valor": "Otra Firma"},
        {"op": "ignorar", "renglones": [3]},
        {"op": "tipo_cambio", "moneda": "USD", "valor": "18"},
    ], None)
    assert _foto(db, carga) != antes
    deshacer_cambio(db, carga, cambio.id)
    assert _foto(db, carga) == antes
    assert cambio.deshecho is True
    with pytest.raises(HTTPException) as e:
        deshacer_cambio(db, carga, cambio.id)
    assert e.value.status_code == 409


def test_solo_se_deshace_el_ultimo(db, org, admin_a):
    carga = _armar(db, org)
    primero, _ = aplicar_operaciones(db, carga, admin_a, [{"op": "ignorar", "renglones": [3]}], None)
    segundo, _ = aplicar_operaciones(db, carga, admin_a, [{"op": "ignorar", "renglones": [2]}], None)
    assert (primero.secuencia, segundo.secuencia) == (1, 2)
    with pytest.raises(HTTPException) as e:
        deshacer_cambio(db, carga, primero.id)
    assert e.value.status_code == 409
    deshacer_cambio(db, carga, segundo.id)
    deshacer_cambio(db, carga, primero.id)
    assert {r.clase for r in _renglones(db, carga).values()} == {"NUEVO"}


def test_fuera_de_plan_da_409(db, org, admin_a):
    carga = _armar(db, org)
    carga.estado = "aplicada"
    with pytest.raises(HTTPException) as e:
        aplicar_operaciones(db, carga, admin_a, [{"op": "ignorar", "renglones": [1]}], None)
    assert e.value.status_code == 409
