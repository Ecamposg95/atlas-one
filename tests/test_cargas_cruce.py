"""Cruce con el catálogo, clasificación y detección de cargas repetidas."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.inventory import InventoryMovement, MovementType
from app.modules.cargas.cruce import (
    Coincidencia, clasificar, cruzar_con_catalogo, marcar_ya_cargado,
    ultimo_conteo_por_departamento,
)
from app.modules.cargas.models import CargaMercancia, CargaRenglon
from app.modules.cargas.reglas import ReglasCarga, TipoPrenda
from app.modules.cargas.tipos import Grupo, RenglonNormalizado
from app.modules.conteos.models import CERRADO, InventoryCount
from app.modules.products.models import Brand, Department, Product, ProductVariant

REGLAS = ReglasCarga(
    escala_ropa=["Ch", "M", "G"],
    tipos={"Playera": TipoPrenda(codigo_sku="PLAY", departamento="Playeras")},
)


def _catalogo(db, org, *, depto="Playeras", nombre="Playera básica", skus=(("UNO-PLAY", "M", "100.00"),),
              marca="Marca Uno"):
    b = db.query(Brand).filter_by(organization_id=org.id, name=marca).first() or Brand(name=marca, organization_id=org.id)
    d = db.query(Department).filter_by(organization_id=org.id, name=depto).first() or Department(name=depto, organization_id=org.id)
    db.add_all([b, d]); db.flush()
    p = Product(name=nombre, organization_id=org.id, is_active=True, brand_id=b.id, department_id=d.id)
    db.add(p); db.flush()
    vs = []
    for sku, talla, precio in skus:
        v = ProductVariant(product_id=p.id, sku=sku, size=talla, organization_id=org.id,
                           price=Decimal(precio), cost=Decimal("50"))
        db.add(v); vs.append(v)
    db.flush()
    return p, vs, d


def _renglon(talla, depto="Playeras", cantidad="2"):
    return RenglonNormalizado(
        descripcion_original="x", marca="Marca Uno", tipo="Playera", talla=talla,
        cantidad=Decimal(cantidad), origen="Hoja1!R1", departamento=depto, llave_grupo="g",
    )


def _grupo(tallas, n=None):
    return Grupo(llave="g", renglones=list(range(n or len(tallas))), tallas=tallas,
                 marca="Marca Uno", tipo="Playera")


def test_encuentra_por_sku_en_otro_departamento(db, org):
    p, vs, _ = _catalogo(db, org, depto="Otro depto")
    g = _grupo({"M": Decimal("100.00")})
    c = cruzar_con_catalogo(db, org.id, [g], [_renglon("M", depto="Playeras")], REGLAS)["g"]
    assert c is not None and c.product_id == p.id
    assert c.variante_por_talla == {"M": vs[0].id}
    assert c.precio_actual == Decimal("100.00") and c.exacta is True


def test_exacta_falsa_si_el_precio_cambia(db, org):
    _catalogo(db, org)
    g = _grupo({"M": Decimal("120.00")})
    c = cruzar_con_catalogo(db, org.id, [g], [_renglon("M")], REGLAS)["g"]
    assert c.exacta is False


def test_encuentra_por_marca_departamento_tipo(db, org):
    p, vs, _ = _catalogo(db, org, skus=(("X-1", "M", "100.00"),))  # SKU distinto al calculado
    g = _grupo({"M": None})
    c = cruzar_con_catalogo(db, org.id, [g], [_renglon("M")], REGLAS)["g"]
    assert c is not None and c.product_id == p.id
    assert c.variante_por_talla == {"M": vs[0].id}


def test_respaldo_ambiguo_no_elige(db, org):
    _catalogo(db, org, nombre="Playera lisa", skus=(("X-1", "M", "100"),))
    _catalogo(db, org, nombre="Playera rayada", skus=(("X-2", "M", "100"),))
    g = _grupo({"M": None})
    assert cruzar_con_catalogo(db, org.id, [g], [_renglon("M")], REGLAS)["g"] is None


def test_marca_inexistente_no_coincide(db, org):
    _catalogo(db, org, marca="Casa Dos")
    g = _grupo({"M": None})
    assert cruzar_con_catalogo(db, org.id, [g], [_renglon("M")], REGLAS)["g"] is None


def test_producto_archivado_no_cuenta(db, org):
    p, vs, _ = _catalogo(db, org)
    p.deleted_at = datetime.now(timezone.utc); db.flush()
    g = _grupo({"M": None})
    assert cruzar_con_catalogo(db, org.id, [g], [_renglon("M")], REGLAS)["g"] is None


def _coinc():
    return Coincidencia(product_id="p", variante_por_talla={"M": "v"},
                        precio_actual=Decimal("1"), exacta=True)


def test_talla_existente_es_suma_en_entrada():
    assert clasificar(_grupo({"M": None}), _coinc(), "entrada", [_renglon("M")]) == [(0, "SUMA")]


def test_talla_existente_es_existe_en_migracion():
    assert clasificar(_grupo({"M": None}), _coinc(), "migracion", [_renglon("M")]) == [(0, "EXISTE")]


def test_talla_nueva_es_nuevo_variante():
    assert clasificar(_grupo({"G": None}), _coinc(), "entrada", [_renglon("G")]) == [(0, "NUEVO")]


def test_sin_coincidencia_es_nuevo():
    assert clasificar(_grupo({"M": None}), None, "entrada", [_renglon("M")]) == [(0, "NUEVO")]


def _carga(db, org, folio, sha="abc", estado="plan", nombre="a.xlsx"):
    c = CargaMercancia(organization_id=org.id, folio=folio, estado=estado,
                       archivo_sha256=sha, archivo_nombre=nombre)
    db.add(c); db.flush()
    return c


def _plan(db, org, carga, sku="UNO-PLAY", cant="2"):
    orden = db.query(CargaRenglon).filter_by(carga_id=carga.id).count() + 1  # único por carga
    r = CargaRenglon(organization_id=org.id, carga_id=carga.id, sku=sku, orden=orden,
                     cantidad=Decimal(cant), clase="SUMA")
    db.add(r); db.flush()
    return r


def _n(por_carga):
    return sum(len(rs) for rs in por_carga.values())


def test_mismo_sha_aplicado_marca_todo_ya_cargado(db, org):
    previa = _carga(db, org, 1, estado="aplicada")
    nueva = _carga(db, org, 2)
    rs = [_plan(db, org, nueva), _plan(db, org, nueva, sku="OTRO")]
    marcados = marcar_ya_cargado(db, org.id, nueva, rs, 14)
    assert list(marcados) == [previa.id] and _n(marcados) == 2
    assert {r.clase for r in rs} == {"YA_CARGADO"}


def test_mismo_contenido_otro_nombre_marca_ya_cargado(db, org):
    _carga(db, org, 1, estado="aplicada", nombre="viejo.xlsx")
    nueva = _carga(db, org, 2, nombre="nuevo.xlsx")
    rs = [_plan(db, org, nueva)]
    assert _n(marcar_ya_cargado(db, org.id, nueva, rs, 14)) == 1


def test_sha_no_aplicado_o_propio_no_marca(db, org):
    _carga(db, org, 1, estado="plan")
    nueva = _carga(db, org, 2)
    rs = [_plan(db, org, nueva)]
    assert marcar_ya_cargado(db, org.id, nueva, rs, 14) == {}
    assert rs[0].clase == "SUMA"


def test_renglon_forzado_no_se_marca(db, org, branch_a):
    _carga(db, org, 1, estado="aplicada")
    nueva = _carga(db, org, 2)
    forzado, normal = _plan(db, org, nueva), _plan(db, org, nueva, sku="OTRO")
    forzado.normalizado = {"_usuario": {"forzar": True}}
    assert _n(marcar_ya_cargado(db, org.id, nueva, [forzado, normal], 14)) == 1
    assert (forzado.clase, normal.clase) == ("SUMA", "YA_CARGADO")


def _mov(db, org, branch, variante, ref, dias, qty="2"):
    db.add(InventoryMovement(
        organization_id=org.id, branch_id=branch.id, variant_id=variante.id,
        movement_type=MovementType.ADJUSTMENT_IN, qty_change=Decimal(qty),
        qty_before=Decimal(0), qty_after=Decimal(qty), reference=ref,
        created_at=datetime.now(timezone.utc) - timedelta(days=dias),
    ))
    db.flush()


def test_renglon_de_carga_reciente_marca_ya_cargado(db, org, branch_a):
    _, vs, _ = _catalogo(db, org)
    previa = _carga(db, org, 1, sha="yyy", estado="aplicada")
    _mov(db, org, branch_a, vs[0], f"carga:{previa.id}", 3)
    nueva = _carga(db, org, 2, sha="zzz")
    rs = [_plan(db, org, nueva), _plan(db, org, nueva, cant="5")]
    marcados = marcar_ya_cargado(db, org.id, nueva, rs, 14, branch_id=branch_a.id)
    assert list(marcados) == [previa.id] and [r.orden for r in marcados[previa.id]] == [1]
    assert [r.clase for r in rs] == ["YA_CARGADO", "SUMA"]


def test_movimiento_de_otra_sucursal_no_marca(db, org, branch_a, branch_b):
    """Un resurtido igual en otra sucursal no es la misma entrada."""
    _, vs, _ = _catalogo(db, org)
    previa = _carga(db, org, 1, sha="yyy", estado="aplicada")
    _mov(db, org, branch_b, vs[0], f"carga:{previa.id}", 3)
    nueva = _carga(db, org, 2, sha="zzz")
    assert marcar_ya_cargado(db, org.id, nueva, [_plan(db, org, nueva)], 14,
                             branch_id=branch_a.id) == {}


def test_sin_sucursal_que_recibe_no_compara_por_sku(db, org, branch_a):
    _, vs, _ = _catalogo(db, org)
    previa = _carga(db, org, 1, sha="yyy", estado="aplicada")
    _mov(db, org, branch_a, vs[0], f"carga:{previa.id}", 3)
    nueva = _carga(db, org, 2, sha="zzz")
    assert marcar_ya_cargado(db, org.id, nueva, [_plan(db, org, nueva)], 14) == {}


def test_fuera_de_ventana_no_marca(db, org, branch_a):
    _, vs, _ = _catalogo(db, org)
    previa = _carga(db, org, 1, sha="yyy", estado="aplicada")
    _mov(db, org, branch_a, vs[0], f"carga:{previa.id}", 20)
    nueva = _carga(db, org, 2, sha="zzz")
    assert marcar_ya_cargado(db, org.id, nueva, [_plan(db, org, nueva)], 14,
                             branch_id=branch_a.id) == {}


def test_movimientos_de_la_propia_carga_no_marcan(db, org, branch_a):
    _, vs, _ = _catalogo(db, org)
    nueva = _carga(db, org, 2, sha="zzz")
    _mov(db, org, branch_a, vs[0], f"carga:{nueva.id}", 1)
    assert marcar_ya_cargado(db, org.id, nueva, [_plan(db, org, nueva)], 14,
                             branch_id=branch_a.id) == {}


def test_ultimo_conteo_por_departamento(db, org, branch_a):
    _, _, d = _catalogo(db, org)
    ahora = datetime.now(timezone.utc)
    viejo = InventoryCount(organization_id=org.id, branch_id=branch_a.id, department_id=d.id,
                           status=CERRADO, closed_at=ahora - timedelta(days=9))
    nuevo = InventoryCount(organization_id=org.id, branch_id=branch_a.id, department_id=d.id,
                           status=CERRADO, closed_at=ahora - timedelta(days=2))
    abierto = InventoryCount(organization_id=org.id, branch_id=branch_a.id, department_id=d.id,
                             status="ABIERTO")
    db.add_all([viejo, nuevo, abierto]); db.flush()
    r = ultimo_conteo_por_departamento(db, org.id, [d.id, "otro"])
    assert list(r) == [d.id]
    assert r[d.id]["conteo_id"] == nuevo.id and r[d.id]["cerrado_at"] is not None


def test_sku_de_otra_marca_no_coincide(db, org):
    """El SKU calculado ("PLAY") es de una Playera de otra marca: no es la misma."""
    _catalogo(db, org, marca="Casa Dos", nombre="Camisa", skus=(("PLAY", "M", "100.00"),))
    db.add(Brand(name="Marca Uno", organization_id=org.id))
    db.flush()
    g = _grupo({"M": Decimal("100.00")})
    assert cruzar_con_catalogo(db, org.id, [g], [_renglon("M")], REGLAS)["g"] is None
