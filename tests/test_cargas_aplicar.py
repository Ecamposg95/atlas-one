"""Aplicar una carga autorizada: catálogo + existencias en una transacción."""
import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models import InventoryMovement, ProductBranchStatus, StockOnHand
from app.models.platform import PlatformAuditLog
from app.modules.cargas.aplicar import aplicar_carga, volver_a_plan
from app.modules.cargas.models import CargaDuda, CargaMercancia, CargaRenglon
from app.modules.cargas.operaciones import aplicar_operaciones, recalcular_plan
from app.modules.cargas.tipos import RenglonCrudo
from app.modules.products.models import Brand, Department, Product, ProductVariant

D = Decimal


def _reglas(branch, **kw):
    base = {
        "costo_si_falta": "fraccion_precio",
        "fraccion": "0.5",
        "escala_ropa": ["Ch", "M", "G"],
        "tipos": {"Playera": {"codigo_sku": "PLAY", "departamento": "Playeras"}},
        "genero_por_omision": "UNISEX",
        "sucursal_recibe": branch.id,
        "activar_en": "todas_las_que_venden",
    }
    base.update(kw)
    return base


def _crudo(**kw):
    base = dict(descripcion_original="Playera Marca Uno", marca="Marca Uno", tipo="Playera",
                talla="M", cantidad="3", precio="350", origen="Hoja1!R2")
    base.update(kw)
    return RenglonCrudo(**base).model_dump(mode="json")


def _pantalon(talla="Ch", cantidad="2"):
    return _crudo(descripcion_original="Pantalon Casa Dos", marca="Casa Dos", tipo="Pantalon",
                  talla=talla, cantidad=cantidad, precio="300")


@pytest.fixture()
def catalogo(db, org, branch_a):
    """Marca Uno con una Playera talla M a $350 y 2 piezas en la sucursal A."""
    org.reglas_carga = _reglas(branch_a)
    marca = Brand(name="Marca Uno", organization_id=org.id)
    playeras = Department(name="Playeras", organization_id=org.id)
    pantalones = Department(name="Pantalones", organization_id=org.id)
    db.add_all([marca, playeras, pantalones])
    db.flush()
    p = Product(name="Playera", brand_id=marca.id, department_id=playeras.id,
                organization_id=org.id, is_active=True, has_variants=True)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku="PLAY", size="M", variant_name="M",
                       barcode="7500000000017", price=D("350"), cost=D("175"),
                       organization_id=org.id)
    db.add(v)
    db.flush()
    db.add(ProductBranchStatus(variant_id=v.id, branch_id=branch_a.id, organization_id=org.id,
                               is_active_pos=True, is_visible=True))
    db.add(StockOnHand(variant_id=v.id, branch_id=branch_a.id, qty_on_hand=D("2"),
                       organization_id=org.id))
    db.flush()
    return {"marca": marca, "producto": p, "variante": v}


_folios = iter(range(1, 10_000))


def _carga(db, org, crudos, proposito="entrada", folio=None, sha=None, **kw):
    carga = CargaMercancia(organization_id=org.id, folio=folio or next(_folios), estado="plan",
                           proposito=proposito, archivo_nombre="lista.xlsx",
                           archivo_sha256=sha, **kw)
    db.add(carga)
    db.flush()
    for i, c in enumerate(crudos, 1):
        db.add(CargaRenglon(organization_id=org.id, carga_id=carga.id, orden=i, crudo=c,
                            cantidad=D(c["cantidad"])))
    db.flush()
    recalcular_plan(db, carga)
    return carga


def _abiertas(db, carga):
    return (db.query(CargaDuda).filter_by(carga_id=carga.id, estado="abierta")
            .order_by(CargaDuda.numero).all())


def _contestar(db, carga, user, eleccion=None):
    """Contesta cada duda abierta con `eleccion[tipo]` o con la recomendada."""
    eleccion = eleccion or {}
    for _ in range(10):
        abiertas = _abiertas(db, carga)
        if not abiertas:
            return
        d = abiertas[0]
        opcion = eleccion.get(d.tipo, d.recomendada)
        assert opcion, f"duda sin recomendada: {d.tipo}"
        _, rechazos = aplicar_operaciones(
            db, carga, user, [{"op": "resolver_duda", "numero": d.numero, "opcion": opcion}], None)
        assert rechazos == []
    raise AssertionError("las dudas no se terminan")


def _renglones(db, carga):
    return {r.orden: r for r in db.query(CargaRenglon).filter_by(carga_id=carga.id).all()}


def _movs(db, carga):
    return db.query(InventoryMovement).filter_by(reference=f"carga:{carga.id}").all()


def _stock(db, variant_id, branch):
    s = db.query(StockOnHand).filter_by(variant_id=variant_id, branch_id=branch.id).first()
    return None if s is None else D(s.qty_on_hand)


def _variante(db, org, sku):
    return db.query(ProductVariant).filter_by(organization_id=org.id, sku=sku).one()


def _audit(db, accion):
    return [json.loads(a.payload) for a in db.query(PlatformAuditLog).filter_by(action=accion).all()]


# ── conducta principal ────────────────────────────────────────────────────

def test_entrada_crea_nuevos_y_suma_existentes(db, org, branch_a, admin_a, catalogo):
    carga = _carga(db, org, [_crudo(talla="M", cantidad="3"), _crudo(talla="G", cantidad="1"),
                             _pantalon("Ch", "2"), _pantalon("G", "1")])
    rs = _renglones(db, carga)
    assert [rs[i].clase for i in (1, 2, 3, 4)] == ["SUMA", "NUEVO", "NUEVO", "NUEVO"]
    _contestar(db, carga, admin_a)

    resumen = aplicar_carga(db, carga, admin_a)

    assert carga.estado == "aplicada" and carga.error is None
    assert carga.aplicada_por == admin_a.id and carga.aplicada_at is not None
    v = catalogo["variante"]
    assert _stock(db, v.id, branch_a) == D("5")          # 2 + 3
    g = _variante(db, org, "PLAY-G")                      # talla nueva del producto existente
    assert g.product_id == catalogo["producto"].id and g.size == "G"
    assert g.price == D("350") and g.cost == D("175")
    assert _stock(db, g.id, branch_a) == D("1")
    pantalon = db.query(Product).filter_by(organization_id=org.id, name="Pantalon").one()
    vivas = {x.size: x for x in pantalon.variants}
    assert set(vivas) == {"Ch", "G"}
    assert _stock(db, vivas["Ch"].id, branch_a) == D("2")
    assert _stock(db, vivas["G"].id, branch_a) == D("1")
    assert all(x.barcode for x in vivas.values()) and g.barcode

    movs = _movs(db, carga)
    assert len(movs) == 4
    assert all(m.notes == f"Carga #{carga.folio} · lista.xlsx" for m in movs)
    assert sorted(D(m.qty_change) for m in movs) == [D(1), D(1), D(2), D(3)]
    # Nada más dejó kardex: el alta nace en 0 y las piezas entran por la carga.
    assert db.query(InventoryMovement).filter(
        InventoryMovement.variant_id.in_([vivas["Ch"].id, vivas["G"].id, g.id]),
        InventoryMovement.reference != f"carga:{carga.id}").count() == 0

    assert resumen.productos_nuevos == 1 and resumen.variantes_nuevas == 3
    assert resumen.piezas == D("7")
    assert resumen.valor_costo == D("175") * 4 + D("150") * 3
    assert carga.totales["productos_nuevos"] == 1 and carga.totales["piezas"] == "7"
    r = _renglones(db, carga)
    assert r[1].resultado["variant_id"] == v.id and r[1].resultado["piezas"] == "3"
    assert r[2].resultado["variant_id"] == g.id and r[2].resultado["creado"] == "variante"
    assert r[3].resultado["creado"] == "producto"
    [aud] = _audit(db, "CARGA_APLICADA")
    assert aud["carga_id"] == carga.id and aud["folio"] == carga.folio and aud["source"] == "ai"
    assert aud["totales"]["productos_nuevos"] == 1


def test_migracion_fija_existencia(db, org, branch_a, admin_a, catalogo):
    carga = _carga(db, org, [_crudo(talla="M", cantidad="7"), _crudo(talla="G", cantidad="4")],
                   proposito="migracion")
    assert {r.clase for r in _renglones(db, carga).values()} == {"EXISTE", "NUEVO"}
    _contestar(db, carga, admin_a)
    aplicar_carga(db, carga, admin_a)
    v = catalogo["variante"]
    assert _stock(db, v.id, branch_a) == D("7")
    g = _variante(db, org, "PLAY-G")
    assert _stock(db, g.id, branch_a) == D("4")
    por_variante = {m.variant_id: m for m in _movs(db, carga)}
    assert D(por_variante[v.id].qty_change) == D("5") and D(por_variante[v.id].qty_after) == D("7")
    assert D(por_variante[g.id].qty_change) == D("4")
    assert por_variante[v.id].notes == f"Carga #{carga.folio} · lista.xlsx"


def test_costo_y_iva_por_reglas(db, org, branch_a, admin_a, catalogo):
    org.reglas_carga = _reglas(branch_a, iva=True, fraccion="0.4")
    carga = _carga(db, org, [_crudo(descripcion_original="Pantalon Casa Dos", marca="Casa Dos",
                                    tipo="Pantalon", talla="Ch", cantidad="2", precio="500")])
    _contestar(db, carga, admin_a)
    aplicar_carga(db, carga, admin_a)
    r = _renglones(db, carga)[1]
    v = db.get(ProductVariant, r.resultado["variant_id"])
    assert v.price == D("500") and v.cost == D("200.00") and v.has_iva is True


def test_activa_en_todas_las_que_venden(db, org, branch_a, branch_b, hq_branch, admin_a, catalogo):
    carga = _carga(db, org, [_pantalon("Ch", "2")])
    _contestar(db, carga, admin_a)
    aplicar_carga(db, carga, admin_a)
    vid = _renglones(db, carga)[1].resultado["variant_id"]
    pbs = {p.branch_id for p in db.query(ProductBranchStatus).filter_by(variant_id=vid)}
    assert pbs == {branch_a.id, branch_b.id}             # HQ no vende
    assert _stock(db, vid, branch_a) == D("2") and _stock(db, vid, branch_b) == D("0")


def test_activa_solo_en_la_que_recibe_aunque_autorice_otra(db, org, branch_a, branch_b, admin_a,
                                                          catalogo):
    org.reglas_carga = _reglas(branch_b, activar_en="sucursal_recibe")
    carga = _carga(db, org, [_pantalon("Ch", "2")])
    _contestar(db, carga, admin_a)
    aplicar_carga(db, carga, admin_a)                     # admin_a es de la sucursal A
    vid = _renglones(db, carga)[1].resultado["variant_id"]
    pbs = {p.branch_id for p in db.query(ProductBranchStatus).filter_by(variant_id=vid)}
    assert pbs == {branch_b.id}
    assert _stock(db, vid, branch_b) == D("2") and _stock(db, vid, branch_a) is None


def test_sucursal_destino_de_la_carga_gana_a_la_regla(db, org, branch_a, branch_b, admin_a,
                                                      catalogo):
    carga = _carga(db, org, [_crudo(talla="M", cantidad="3")], sucursal_destino_id=branch_b.id)
    _contestar(db, carga, admin_a)
    aplicar_carga(db, carga, admin_a)
    v = catalogo["variante"]
    assert _stock(db, v.id, branch_b) == D("3") and _stock(db, v.id, branch_a) == D("2")


def test_marca_nueva_aceptada_se_crea(db, org, branch_a, admin_a, catalogo):
    carga = _carga(db, org, [_pantalon("Ch", "2")])
    assert any(d.tipo == "marca_nueva" for d in _abiertas(db, carga))
    _contestar(db, carga, admin_a)
    assert db.query(Brand).filter_by(organization_id=org.id, name="Casa Dos").count() == 0
    aplicar_carga(db, carga, admin_a)
    marca = db.query(Brand).filter_by(organization_id=org.id, name="Casa Dos").one()
    p = db.get(Product, _renglones(db, carga)[1].resultado["product_id"])
    assert p.brand_id == marca.id
    assert p.department_id == db.query(Department).filter_by(
        organization_id=org.id, name="Pantalones").one().id


def test_actualizar_precio_audita_anterior(db, org, branch_a, admin_a, catalogo):
    carga = _carga(db, org, [_crudo(talla="M", cantidad="3", precio="400")])
    _contestar(db, carga, admin_a, {"precio_distinto_existente": "actualizar"})
    resumen = aplicar_carga(db, carga, admin_a)
    v = catalogo["variante"]
    db.refresh(v)
    assert v.price == D("400") and v.cost == D("200.00")
    assert _stock(db, v.id, branch_a) == D("5")
    [aud] = _audit(db, "CARGA_PRECIO_ACTUALIZADO")
    assert aud["variant_id"] == v.id and aud["carga_id"] == carga.id
    assert D(aud["precio_anterior"]) == D("350") and D(aud["precio_nuevo"]) == D("400")
    assert D(aud["costo_anterior"]) == D("175")
    assert resumen.etiquetas[0]["precio"] == "400.00"


def test_mantener_precio_no_toca_variante(db, org, branch_a, admin_a, catalogo):
    carga = _carga(db, org, [_crudo(talla="M", cantidad="3", precio="400")])
    _contestar(db, carga, admin_a, {"precio_distinto_existente": "mantener"})
    resumen = aplicar_carga(db, carga, admin_a)
    v = catalogo["variante"]
    db.refresh(v)
    assert v.price == D("350") and v.cost == D("175")
    assert _stock(db, v.id, branch_a) == D("5")
    assert _audit(db, "CARGA_PRECIO_ACTUALIZADO") == []
    assert resumen.productos_nuevos == 0 and resumen.variantes_nuevas == 0


def test_aparte_crea_producto_separado(db, org, branch_a, admin_a, catalogo):
    carga = _carga(db, org, [_crudo(talla="M", cantidad="3", precio="400")])
    _contestar(db, carga, admin_a, {"precio_distinto_existente": "aparte"})
    r = _renglones(db, carga)[1]
    assert r.clase == "NUEVO" and r.product_id is None and r.sku == "PLAY-2"
    resumen = aplicar_carga(db, carga, admin_a)
    v = catalogo["variante"]
    db.refresh(v)
    assert v.price == D("350") and _stock(db, v.id, branch_a) == D("2")
    nueva = _variante(db, org, "PLAY-2")
    assert nueva.product_id != catalogo["producto"].id and nueva.price == D("400")
    assert _stock(db, nueva.id, branch_a) == D("3")
    assert resumen.productos_nuevos == 1


# ── fallas y reintento ────────────────────────────────────────────────────

def _con_sku_archivado(db, org, catalogo):
    """Una Playera archivada de Marca Uno ocupa el SKU "PLAY"; la Playera viva
    también se archiva, así el cruce no encuentra nada y el plan sale NUEVO."""
    p = Product(name="Playera vieja", brand_id=catalogo["marca"].id, organization_id=org.id,
                deleted_at=datetime.now(timezone.utc))
    db.add(p)
    db.flush()
    db.add(ProductVariant(product_id=p.id, sku="PLAY", size="Ch", price=D("100"),
                          organization_id=org.id))
    catalogo["variante"].sku = "VIEJA-1"
    catalogo["variante"].deleted_at = datetime.now(timezone.utc)
    catalogo["producto"].deleted_at = datetime.now(timezone.utc)
    db.flush()


def _conteos(db, org):
    return (db.query(Product).filter_by(organization_id=org.id).count(),
            db.query(ProductVariant).filter_by(organization_id=org.id).count(),
            db.query(Brand).filter_by(organization_id=org.id).count(),
            db.query(Department).filter_by(organization_id=org.id).count(),
            db.query(InventoryMovement).filter_by(organization_id=org.id).count(),
            db.query(PlatformAuditLog).count())


def test_falla_a_media_no_deja_nada(db, org, branch_a, admin_a, catalogo):
    _con_sku_archivado(db, org, catalogo)
    carga = _carga(db, org, [_pantalon("Ch", "2"), _pantalon("G", "1"),
                             _crudo(talla="Ch", cantidad="1", precio="350")])
    rs = _renglones(db, carga)
    assert rs[3].clase == "NUEVO" and rs[3].sku == "PLAY"
    _contestar(db, carga, admin_a)
    antes = _conteos(db, org)

    with pytest.raises(HTTPException) as e:
        aplicar_carga(db, carga, admin_a)

    assert e.value.status_code == 422
    assert "PLAY" in e.value.detail and "renglón 3" in e.value.detail
    assert _conteos(db, org) == antes
    assert _movs(db, carga) == []
    assert db.query(Brand).filter_by(organization_id=org.id, name="Casa Dos").count() == 0
    assert carga.estado == "error" and "PLAY" in carga.error
    assert all(r.resultado is None for r in _renglones(db, carga).values())


def test_reintento_tras_error_funciona(db, org, branch_a, admin_a, catalogo):
    _con_sku_archivado(db, org, catalogo)
    carga = _carga(db, org, [_pantalon("Ch", "2"), _pantalon("G", "1"),
                             _crudo(talla="Ch", cantidad="1", precio="350")])
    _contestar(db, carga, admin_a)
    with pytest.raises(HTTPException):
        aplicar_carga(db, carga, admin_a)
    with pytest.raises(HTTPException) as otra:
        aplicar_carga(db, carga, admin_a)                 # en error no se reaplica
    assert otra.value.status_code == 409

    volver_a_plan(db, carga)
    assert carga.estado == "plan" and carga.error is None
    _, rechazos = aplicar_operaciones(db, carga, admin_a, [{"op": "ignorar", "renglones": [3]}], None)
    assert rechazos == []
    resumen = aplicar_carga(db, carga, admin_a)
    assert carga.estado == "aplicada" and resumen.productos_nuevos == 1
    assert len(_movs(db, carga)) == 2
    assert _renglones(db, carga)[3].resultado is None


def test_volver_a_plan_solo_desde_error(db, org, branch_a, admin_a, catalogo):
    carga = _carga(db, org, [_crudo()])
    with pytest.raises(HTTPException) as e:
        volver_a_plan(db, carga)
    assert e.value.status_code == 409
    vacia = CargaMercancia(organization_id=org.id, folio=next(_folios), estado="error",
                           error="x", archivo_nombre="a.pdf")
    db.add(vacia)
    db.flush()
    with pytest.raises(HTTPException) as e:
        volver_a_plan(db, vacia)
    assert e.value.status_code == 409


def test_dudas_abiertas_409(db, org, branch_a, admin_a, catalogo):
    carga = _carga(db, org, [_pantalon("Ch", "2")])
    assert _abiertas(db, carga)
    antes = _conteos(db, org)
    with pytest.raises(HTTPException) as e:
        aplicar_carga(db, carga, admin_a)
    assert e.value.status_code == 409
    assert carga.estado == "plan" and _conteos(db, org) == antes


def test_plan_que_cambio_con_dudas_nuevas_409(db, org, branch_a, admin_a, catalogo):
    carga = _carga(db, org, [_crudo(talla="M", cantidad="3")])
    assert _abiertas(db, carga) == []
    catalogo["marca"].deleted_at = datetime.now(timezone.utc)   # la marca se archivó
    db.flush()
    with pytest.raises(HTTPException) as e:
        aplicar_carga(db, carga, admin_a)
    assert e.value.status_code == 409 and "cambió" in e.value.detail
    assert carga.estado == "plan"
    assert [d.tipo for d in _abiertas(db, carga)] == ["marca_nueva"]
    assert _movs(db, carga) == []


def test_estado_distinto_de_plan_409(db, org, branch_a, admin_a, catalogo):
    carga = _carga(db, org, [_crudo(talla="M", cantidad="3")])
    carga.estado = "aplicando"
    db.flush()
    with pytest.raises(HTTPException) as e:
        aplicar_carga(db, carga, admin_a)
    assert e.value.status_code == 409 and _movs(db, carga) == []


def test_sin_sucursal_que_recibe_422(db, org, branch_a, admin_a, catalogo):
    org.reglas_carga = {**_reglas(branch_a), "sucursal_recibe": None}
    carga = _carga(db, org, [_crudo(talla="M", cantidad="3")])
    with pytest.raises(HTTPException) as e:
        aplicar_carga(db, carga, admin_a)
    assert e.value.status_code == 422 and "sucursal" in e.value.detail
    assert carga.estado == "plan" and _movs(db, carga) == []


def test_gerente_no_puede_autorizar_403(db, org, branch_a, gerente_a, admin_a, catalogo):
    carga = _carga(db, org, [_crudo(talla="M", cantidad="3")])
    with pytest.raises(HTTPException) as e:
        aplicar_carga(db, carga, gerente_a)
    assert e.value.status_code == 403
    assert carga.estado == "plan" and _movs(db, carga) == []


def test_etiquetas_cuentan_lo_que_entro_no_el_stock(db, org, branch_a, admin_a, catalogo):
    carga = _carga(db, org, [_crudo(talla="M", cantidad="3")])
    resumen = aplicar_carga(db, carga, admin_a)
    assert _stock(db, catalogo["variante"].id, branch_a) == D("5")
    assert resumen.etiquetas == [{
        "marca": "Marca Uno", "producto": "Playera", "sku": "PLAY", "talla": "M",
        "barcode": "7500000000017", "piezas": "3", "precio": "350.00",
    }]


def test_segunda_aplicacion_del_mismo_archivo_sale_ya_cargado(db, org, branch_a, admin_a, catalogo):
    crudos = [_crudo(talla="M", cantidad="3"), _pantalon("Ch", "2")]
    primera = _carga(db, org, crudos, sha="a" * 64)
    _contestar(db, primera, admin_a)
    aplicar_carga(db, primera, admin_a)
    antes = _conteos(db, org)

    segunda = _carga(db, org, crudos, sha="a" * 64)
    assert {r.clase for r in _renglones(db, segunda).values()} == {"YA_CARGADO"}
    resumen = aplicar_carga(db, segunda, admin_a)

    assert segunda.estado == "aplicada"
    assert resumen.productos_nuevos == 0 and resumen.piezas == 0 and resumen.etiquetas == []
    assert _movs(db, segunda) == []
    p_antes = antes[:5]
    assert _conteos(db, org)[:5] == p_antes
    assert _stock(db, catalogo["variante"].id, branch_a) == D("5")


# ── ronda de revisión 1 ───────────────────────────────────────────────────

def test_entrada_departamento_de_reglas_inexistente_es_duda_sin_crear(db, org, branch_a, admin_a,
                                                                     catalogo):
    reglas = _reglas(branch_a)
    reglas["tipos"]["Sudadera"] = {"codigo_sku": "SUD", "departamento": "Sudaderas"}
    org.reglas_carga = reglas
    carga = _carga(db, org, [_crudo(tipo="Sudadera", talla="M", cantidad="2")])
    [d] = [d for d in _abiertas(db, carga) if d.tipo == "departamento"]
    assert '"Sudaderas"' in d.texto and "crear" not in {o["clave"] for o in d.opciones}
    playeras = db.query(Department).filter_by(organization_id=org.id, name="Playeras").one()
    _contestar(db, carga, admin_a, {"departamento": f"depto:{playeras.id}"})
    antes = db.query(Department).filter_by(organization_id=org.id).count()
    aplicar_carga(db, carga, admin_a)
    assert db.query(Department).filter_by(organization_id=org.id).count() == antes
    p = db.get(Product, _renglones(db, carga)[1].resultado["product_id"])
    assert p.department_id == playeras.id


def test_entrada_departamento_archivado_antes_de_autorizar_409(db, org, branch_a, admin_a, catalogo):
    carga = _carga(db, org, [_crudo(talla="G", cantidad="2", marca="Marca Uno")])
    _contestar(db, carga, admin_a)
    db.query(Department).filter_by(organization_id=org.id, name="Playeras").one().deleted_at = \
        datetime.now(timezone.utc)
    db.flush()
    with pytest.raises(HTTPException) as e:
        aplicar_carga(db, carga, admin_a)
    assert e.value.status_code == 409
    assert [d.tipo for d in _abiertas(db, carga)] == ["departamento"]
    assert db.query(Department).filter_by(organization_id=org.id, name="Playeras",
                                          deleted_at=None).count() == 0


def test_migracion_crea_departamento_solo_con_crear(db, org, branch_a, admin_a, catalogo):
    reglas = _reglas(branch_a)
    reglas["tipos"]["Sudadera"] = {"codigo_sku": "SUD", "departamento": "Sudaderas"}
    org.reglas_carga = reglas
    carga = _carga(db, org, [_crudo(tipo="Sudadera", talla="M", cantidad="2")], proposito="migracion")
    [d] = [d for d in _abiertas(db, carga) if d.tipo == "departamento"]
    assert d.recomendada == "crear"
    _contestar(db, carga, admin_a)
    resumen = aplicar_carga(db, carga, admin_a)
    nuevo = db.query(Department).filter_by(organization_id=org.id, name="Sudaderas").one()
    assert db.get(Product, _renglones(db, carga)[1].resultado["product_id"]).department_id == nuevo.id
    assert carga.totales["departamentos_nuevos"] == 1 and resumen.productos_nuevos == 1


def test_migracion_departamento_escrito_sin_crear_falla(db, org, branch_a, admin_a, catalogo):
    reglas = _reglas(branch_a)
    reglas["tipos"]["Sudadera"] = {"codigo_sku": "SUD", "departamento": "Sudaderas"}
    org.reglas_carga = reglas
    carga = _carga(db, org, [_crudo(tipo="Sudadera", talla="M", cantidad="2")], proposito="migracion")
    [d] = [d for d in _abiertas(db, carga) if d.tipo == "departamento"]
    _, rechazos = aplicar_operaciones(db, carga, admin_a, [
        {"op": "resolver_duda", "numero": d.numero, "opcion": "", "valor": "Ropa de abrigo"}], None)
    assert rechazos == []
    _contestar(db, carga, admin_a)
    with pytest.raises(HTTPException) as e:
        aplicar_carga(db, carga, admin_a)
    assert e.value.status_code == 422 and '"Ropa de abrigo" no existe' in e.value.detail
    assert db.query(Department).filter_by(organization_id=org.id, name="Ropa de abrigo").count() == 0


def test_suma_activa_la_variante_en_la_que_recibe(db, org, branch_a, branch_b, admin_a, catalogo):
    v = catalogo["variante"]
    pbs = db.query(ProductBranchStatus).filter_by(variant_id=v.id).one()
    pbs.branch_id = branch_b.id                      # hoy solo se vende en B
    pbs.price_override = D("360")
    db.flush()
    carga = _carga(db, org, [_crudo(talla="M", cantidad="3")])
    aplicar_carga(db, carga, admin_a)                # recibe la sucursal A
    por_sucursal = {p.branch_id: p for p in db.query(ProductBranchStatus).filter_by(variant_id=v.id)}
    assert set(por_sucursal) == {branch_a.id, branch_b.id}
    assert por_sucursal[branch_a.id].is_active_pos and por_sucursal[branch_a.id].is_visible
    assert por_sucursal[branch_b.id].price_override == D("360")
    assert _stock(db, v.id, branch_a) == D("5")


def test_suma_reactiva_la_variante_apagada_en_la_que_recibe(db, org, branch_a, admin_a, catalogo):
    v = catalogo["variante"]
    pbs = db.query(ProductBranchStatus).filter_by(variant_id=v.id, branch_id=branch_a.id).one()
    pbs.is_active_pos = False
    db.flush()
    aplicar_carga(db, _carga(db, org, [_crudo(talla="M", cantidad="1")]), admin_a)
    db.refresh(pbs)
    assert pbs.is_active_pos is True


def test_actualizar_una_vez_por_variante(db, org, branch_a, admin_a, catalogo):
    carga = _carga(db, org, [_crudo(talla="M", cantidad="3", precio="400"),
                             _crudo(talla="M", cantidad="2", precio="400")])
    _contestar(db, carga, admin_a, {"precio_distinto_existente": "actualizar"})
    aplicar_carga(db, carga, admin_a)
    [aud] = _audit(db, "CARGA_PRECIO_ACTUALIZADO")
    assert D(aud["precio_anterior"]) == D("350") and D(aud["precio_nuevo"]) == D("400")
    assert carga.totales["precios_actualizados"] == 1
    assert _stock(db, catalogo["variante"].id, branch_a) == D("7")


def test_tallas_nuevas_llevan_el_color_del_grupo(db, org, branch_a, admin_a, catalogo):
    carga = _carga(db, org, [_crudo(talla="M", cantidad="1", color="Rojo"),
                             _crudo(talla="G", cantidad="1", color="Rojo")])
    _contestar(db, carga, admin_a)
    aplicar_carga(db, carga, admin_a)
    assert _variante(db, org, "PLAY-G").color == "Rojo"


def test_variante_de_producto_archivado_no_cuenta(db, org, branch_a, admin_a, catalogo):
    from app.modules.cargas.aplicar import _Aplicador, _Falla
    from app.modules.cargas.reglas import reglas_de_la_org
    catalogo["producto"].deleted_at = datetime.now(timezone.utc)
    db.flush()
    carga = CargaMercancia(organization_id=org.id, folio=next(_folios), estado="plan",
                           archivo_nombre="x.xlsx")
    db.add(carga)
    db.flush()
    ap = _Aplicador(db=db, carga=carga, user=admin_a, reglas=reglas_de_la_org(org),
                    branch_id=branch_a.id)
    with pytest.raises(_Falla):
        ap.variante(catalogo["variante"].id)


def test_valor_costo_usa_el_costo_que_queda_en_catalogo(db, org, branch_a, admin_a, catalogo):
    carga = _carga(db, org, [_crudo(talla="M", cantidad="3", precio="400")])   # costo del plan: 200
    _contestar(db, carga, admin_a, {"precio_distinto_existente": "mantener"})
    resumen = aplicar_carga(db, carga, admin_a)
    assert resumen.valor_costo == D("175") * 3


def test_misma_talla_con_costos_distintos_falla(db, org, branch_a, admin_a, catalogo):
    carga = _carga(db, org, [
        {**_pantalon("Ch", "1"), "costo_unitario": "100", "moneda": "MXN"},
        {**_pantalon("Ch", "1"), "costo_unitario": "120", "moneda": "MXN"},
    ])
    _contestar(db, carga, admin_a)
    antes = _conteos(db, org)
    with pytest.raises(HTTPException) as e:
        aplicar_carga(db, carga, admin_a)
    assert e.value.status_code == 422 and "renglones 1, 2" in e.value.detail
    assert _conteos(db, org) == antes and carga.estado == "error"
