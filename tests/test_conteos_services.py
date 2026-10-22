# tests/test_conteos_services.py
"""Reglas del conteo: resolución del código, suma, reporte y cierre."""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.inventory import StockOnHand
from app.models.products import Brand, Department, PackagingUnit, Product, ProductVariant
from app.modules.conteos import services
from app.modules.conteos.models import ABIERTO, CERRADO, InventoryCount


def _prenda(db, org, branch, *, name, sku, barcode, depto, stock="3", size="M",
            color="Negro", brand=None, activo=True):
    p = Product(name=name, organization_id=org.id, is_active=activo,
                department_id=depto.id, brand_id=brand.id if brand else None)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku=sku, barcode=barcode, organization_id=org.id,
                       price=Decimal("100"), cost=Decimal("50"), size=size, color=color)
    db.add(v)
    db.flush()
    if stock is not None:
        db.add(StockOnHand(variant_id=v.id, branch_id=branch.id, organization_id=org.id,
                           qty_on_hand=Decimal(stock), is_active=True))
    db.flush()
    return v


@pytest.fixture()
def tienda(db, org, branch_a):
    marca = Brand(name="Zegna", organization_id=org.id)
    playeras = Department(name="Playeras", organization_id=org.id)
    tenis = Department(name="Tenis", organization_id=org.id)
    db.add_all([marca, playeras, tenis])
    db.flush()
    roja = _prenda(db, org, branch_a, name="Playera", sku="ZEG-PLAY-ROJ-M",
                   barcode="2017000000013", depto=playeras, brand=marca, stock="3")
    azul = _prenda(db, org, branch_a, name="Playera", sku="zeg-play-azu-m",
                   barcode="2017000000020", depto=playeras, brand=marca, stock="2", color="Azul")
    sin_stock = _prenda(db, org, branch_a, name="Playera vieja", sku="PLAY-VIEJA",
                        barcode="2017000000037", depto=playeras, stock="0")
    tenis_v = _prenda(db, org, branch_a, name="Tenis", sku="ZEG-TENI-27",
                      barcode="2017000000044", depto=tenis, brand=marca, stock="1", size="27")
    db.add(PackagingUnit(variant_id=roja.id, organization_id=org.id, name="Caja",
                         barcode="CAJA-ROJA", units_per_package=Decimal("6"),
                         package_price=Decimal("500")))
    conteo = InventoryCount(organization_id=org.id, branch_id=branch_a.id,
                            department_id=playeras.id, status=ABIERTO)
    db.add(conteo)
    db.commit()
    return {"roja": roja, "azul": azul, "sin_stock": sin_stock, "tenis": tenis_v,
            "conteo": conteo, "playeras": playeras, "tenis_depto": tenis}


def test_resolver_por_barcode_sku_y_empaque(db, org, tienda):
    assert [v.id for v in services.resolver_codigo(db, org.id, "2017000000013")] == [tienda["roja"].id]
    assert [v.id for v in services.resolver_codigo(db, org.id, "CAJA-ROJA")] == [tienda["roja"].id]
    assert services.resolver_codigo(db, org.id, "no-existe") == []


def test_resolver_sku_mayusculas_y_espacios(db, org, tienda):
    hits = services.resolver_codigo(db, org.id, "  ZEG-PLAY-AZU-M ")
    assert [v.id for v in hits] == [tienda["azul"].id]


def test_resolver_no_cruza_organizaciones(db, org, tienda):
    assert services.resolver_codigo(db, org.id + 999, "2017000000013") == []


def test_escanear_dos_veces_suma_a_la_misma_linea(db, tienda):
    c = tienda["conteo"]
    r1 = services.escanear(db, c, "2017000000013", None)
    r2 = services.escanear(db, c, "2017000000013", None)
    assert r1.resultado == r2.resultado == "contado"
    assert r2.linea.qty_contada == Decimal("2")
    assert r2.qty_sistema == Decimal("3")
    assert r2.producto.nombre == "Zegna · Playera · Negro, Talla M"
    assert r2.fuera_de_alcance is False
    assert len(c.lineas) == 1


def test_escanear_de_otro_departamento_cuenta_y_avisa(db, tienda):
    r = services.escanear(db, tienda["conteo"], "2017000000044", None)
    assert r.resultado == "contado" and r.fuera_de_alcance is True


def test_escanear_desconocido_crea_linea_sin_variante(db, tienda):
    c = tienda["conteo"]
    r = services.escanear(db, c, "9999", None)
    r = services.escanear(db, c, "9999", None)
    assert r.resultado == "desconocido"
    assert r.linea.variant_id is None and r.linea.codigo == "9999"
    assert r.linea.qty_contada == Decimal("2")


def test_escanear_ambiguo_no_cuenta(db, org, tienda):
    # Un empaque cuyo código es el SKU de otra talla: dos variantes empatan.
    db.add(PackagingUnit(variant_id=tienda["azul"].id, organization_id=org.id, name="Caja",
                         barcode="ZEG-PLAY-ROJ-M", units_per_package=Decimal("6"),
                         package_price=Decimal("500")))
    db.commit()
    r = services.escanear(db, tienda["conteo"], "ZEG-PLAY-ROJ-M", None)
    assert r.resultado == "ambiguo"
    assert {p.variant_id for p in r.candidatos} == {tienda["roja"].id, tienda["azul"].id}
    assert tienda["conteo"].lineas == []


def test_escanear_en_cerrado_es_409(db, tienda):
    c = tienda["conteo"]
    c.status = CERRADO
    db.commit()
    with pytest.raises(HTTPException) as e:
        services.escanear(db, c, "2017000000013", None)
    assert e.value.status_code == 409


def test_agregar_y_fijar_linea(db, org, tienda):
    c = tienda["conteo"]
    l = services.agregar_linea(db, c, tienda["azul"].id, Decimal("2"), None)
    l = services.agregar_linea(db, c, tienda["azul"].id, Decimal("1"), None)
    assert l.qty_contada == Decimal("3")
    l = services.fijar_linea(db, c, l, Decimal("1"))
    assert l.qty_contada == Decimal("1")
    assert services.fijar_linea(db, c, l, Decimal("0")) is None
    assert c.lineas == []
    with pytest.raises(HTTPException) as e:
        services.agregar_linea(db, c, "no-existe", Decimal("1"), None)
    assert e.value.status_code == 404


def test_reporte_con_las_cuatro_secciones(db, tienda):
    c = tienda["conteo"]
    services.escanear(db, c, "2017000000013", None)          # roja: 1 de 3 → faltan 2
    services.escanear(db, c, "2017000000037", None)          # sin_stock: 1 de 0 → sobra 1
    services.escanear(db, c, "2017000000044", None)          # tenis: fuera de alcance
    services.escanear(db, c, "9999", None)                   # desconocido
    rep = services.reporte(db, c)
    assert rep.estado == ABIERTO
    faltantes = {f.sku: f for f in rep.faltantes}
    assert faltantes["ZEG-PLAY-ROJ-M"].diferencia == Decimal("-2")
    assert faltantes["zeg-play-azu-m"].contado == Decimal("0")   # nunca escaneada
    assert [s.sku for s in rep.sobrantes] == ["PLAY-VIEJA"]
    assert rep.sobrantes[0].diferencia == Decimal("1")
    assert [f.sku for f in rep.fuera_de_alcance] == ["ZEG-TENI-27"]
    assert rep.fuera_de_alcance[0].departamento == "Tenis"
    assert [d.codigo for d in rep.desconocidos] == ["9999"]
    assert rep.totales["esperadas_variantes"] == 2
    assert rep.totales["esperadas_piezas"] == Decimal("5")
    assert rep.totales["faltantes_piezas"] == Decimal("4")
    assert rep.totales["sobrantes_piezas"] == Decimal("1")
    assert rep.totales["fuera_de_alcance_piezas"] == Decimal("1")
    assert rep.totales["desconocidos"] == 1
    assert rep.alcance == {"sucursal": "Sucursal A", "departamento": "Playeras"}


def test_reporte_linea_de_producto_inactivo_va_a_fuera_de_alcance(db, tienda):
    c = tienda["conteo"]
    services.escanear(db, c, "2017000000013", None)
    tienda["roja"].product.is_active = False
    db.commit()
    rep = services.reporte(db, c)
    assert [f.sku for f in rep.fuera_de_alcance] == ["ZEG-PLAY-ROJ-M"]
    assert all(f.sku != "ZEG-PLAY-ROJ-M" for f in rep.faltantes)


def test_cerrar_sin_lineas_reporta_todo_faltante(db, tienda):
    rep = services.cerrar(db, tienda["conteo"], None)
    assert {f.sku for f in rep.faltantes} == {"ZEG-PLAY-ROJ-M", "zeg-play-azu-m"}
    assert rep.totales["contadas_piezas"] == Decimal("0")


def test_cerrar_congela_y_no_recalcula(db, tienda):
    c = tienda["conteo"]
    services.escanear(db, c, "2017000000013", None)
    rep = services.cerrar(db, c, None)
    assert c.status == CERRADO and c.closed_at is not None and c.resumen
    assert c.lineas[0].qty_sistema == Decimal("3")
    # El inventario cambia después: el reporte guardado no se mueve.
    soh = db.query(StockOnHand).filter_by(variant_id=tienda["roja"].id).first()
    soh.qty_on_hand = Decimal("10")
    db.commit()
    rep2 = services.reporte(db, c)
    assert rep2.faltantes[0].sistema == rep.faltantes[0].sistema == Decimal("3")
    with pytest.raises(HTTPException) as e:
        services.cerrar(db, c, None)
    assert e.value.status_code == 409


def test_avance(db, tienda):
    c = tienda["conteo"]
    services.escanear(db, c, "2017000000013", None)
    services.escanear(db, c, "9999", None)
    a = services.avance(db, c)
    assert (a.esperadas_variantes, a.esperadas_piezas) == (2, Decimal("5"))
    assert (a.contadas_variantes, a.contadas_piezas, a.desconocidos) == (1, Decimal("1"), 1)


def test_fijar_linea_de_otro_conteo_es_404(db, org, branch_a, tienda):
    otro = InventoryCount(organization_id=org.id, branch_id=branch_a.id, status=ABIERTO)
    db.add(otro)
    db.commit()
    ajena = services.agregar_linea(db, otro, tienda["azul"].id, Decimal("2"), None)
    with pytest.raises(HTTPException) as e:
        services.fijar_linea(db, tienda["conteo"], ajena, Decimal("0"))
    assert e.value.status_code == 404
    db.refresh(ajena)
    assert ajena.qty_contada == Decimal("2")


@pytest.mark.parametrize("codigo,esperado", [("2017000000013", "contado"), ("9999", "desconocido")])
def test_escanear_choque_de_primer_escaneo_no_pierde_la_pieza(db, org, tienda, monkeypatch,
                                                              codigo, esperado):
    """Otra petición inserta la misma línea justo antes de nuestro commit: el índice
    único revienta y el servicio debe reintentar sumando a la que ganó."""
    from sqlalchemy.exc import IntegrityError
    from app.modules.conteos.models import InventoryCountLine
    c = tienda["conteo"]
    cid, org_id = c.id, org.id
    variant_id = services.resolver_codigo(db, org_id, codigo)[0].id if esperado == "contado" else None
    estado = {"n": 0}

    def commit_con_choque():
        estado["n"] += 1
        if estado["n"] == 1:
            # La línea pendiente de este request nunca llegó a la base; la de la otra sí.
            for pendiente in list(db.new):
                db.expunge(pendiente)
            db.add(InventoryCountLine(organization_id=org_id, count_id=cid, variant_id=variant_id,
                                      codigo=None if variant_id else codigo,
                                      qty_contada=Decimal("1")))
            db.flush()
            raise IntegrityError("insert", {}, Exception("uq_count_line"))

    # La fixture `db` corre dentro de una transacción externa: un rollback real
    # borraría los datos de la prueba, así que aquí el rollback no hace nada.
    monkeypatch.setattr(db, "commit", commit_con_choque)
    monkeypatch.setattr(db, "rollback", lambda: None)
    r = services.escanear(db, c, codigo, None)
    monkeypatch.undo()
    assert r.resultado == esperado
    assert r.linea.qty_contada == Decimal("2")   # la de la otra petición + la nuestra
    assert db.query(InventoryCountLine).filter_by(count_id=cid).count() == 1
