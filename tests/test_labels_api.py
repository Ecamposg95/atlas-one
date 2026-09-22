"""`/api/labels/*`: alcance, copias, omisiones y topes.

Lo que se prueba aquí es la DECISIÓN (qué se imprime y cuántas veces); la
geometría del ZPL vive en `tests/test_labels_zpl.py`.
"""
import base64
from decimal import Decimal

import pytest

from app.models.modules import Module, OrganizationModule
from app.models.organization import Organization
from app.models.products import Brand, Department, Product, ProductBranchStatus, ProductVariant
from app.models.inventory import StockOnHand

EAN_OK = "2017000000013"
EAN_OTRO = "2017000000020"


def _habilitar(db, org, key, enabled=True):
    if db.query(Module).filter(Module.key == key).first() is None:
        db.add(Module(key=key, name=key))
        db.flush()
    om = db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key == key,
    ).first()
    if om is None:
        db.add(OrganizationModule(organization_id=org.id, module_key=key, is_enabled=enabled))
    else:
        om.is_enabled = enabled
    db.commit()


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


def _prenda(db, org, branch, *, name, sku, barcode, price="1800.00", stock="3",
            brand=None, department=None, size="M", color="Negro", model=None,
            gender=None):
    """Producto + variante + disponibilidad y existencia en `branch`."""
    p = Product(
        name=name, organization_id=org.id, is_active=True,
        brand_id=brand.id if brand else None,
        department_id=department.id if department else None,
        model=model, gender=gender,
    )
    db.add(p)
    db.flush()
    v = ProductVariant(
        product_id=p.id, sku=sku, barcode=barcode, organization_id=org.id,
        price=Decimal(price), cost=Decimal("900.00"), size=size, color=color,
    )
    db.add(v)
    db.flush()
    if branch is not None:
        db.add(ProductBranchStatus(
            variant_id=v.id, branch_id=branch.id, organization_id=org.id,
            is_active_pos=True, is_visible=True,
        ))
        db.add(StockOnHand(
            variant_id=v.id, branch_id=branch.id, organization_id=org.id,
            qty_on_hand=Decimal(stock), is_active=True,
        ))
    db.flush()
    return p, v


@pytest.fixture()
def tienda(db, org, branch_a, branch_b):
    """Catálogo de la boutique: una prenda con código, una sin él y una que
    solo existe en la otra sucursal."""
    _habilitar(db, org, "labels")
    marca = Brand(name="Louis Vuitton", organization_id=org.id)
    depto = Department(name="Caballero", organization_id=org.id)
    db.add_all([marca, depto])
    db.flush()

    chamarra = _prenda(
        db, org, branch_a, name="Chamarra mezclilla", sku="LV-CHAM-SLI-NEG-M",
        barcode=EAN_OK, brand=marca, department=depto, model="Slim",
        gender="HOMBRE", stock="3",
    )
    sin_codigo = _prenda(
        db, org, branch_a, name="Playera lisa", sku="PLAY-BLA-CH",
        barcode=None, size="CH", color="Blanco", stock="5",
    )
    de_la_otra = _prenda(
        db, org, branch_b, name="Vestido largo", sku="VEST-ROJ-G",
        barcode=EAN_OTRO, size="G", color="Rojo", stock="2",
    )
    db.commit()
    return {"chamarra": chamarra, "sin_codigo": sin_codigo, "otra_sucursal": de_la_otra}


def _por_sku(items):
    return {item["sku"]: item for item in items}


# ── /candidates ──────────────────────────────────────────────────────────────
def test_candidatos_traen_los_campos_de_la_etiqueta(client, tienda, auth_admin, org):
    r = client.get("/api/labels/candidates", headers=_h(auth_admin, org))
    assert r.status_code == 200
    filas = _por_sku(r.json()["items"])
    chamarra = filas["LV-CHAM-SLI-NEG-M"]
    assert chamarra["barcode"] == EAN_OK
    assert chamarra["product_name"] == "Chamarra mezclilla"
    assert chamarra["brand"] == "Louis Vuitton"
    assert chamarra["department"] == "Caballero"
    assert chamarra["gender"] == "HOMBRE"
    assert (chamarra["size"], chamarra["color"]) == ("M", "Negro")
    assert chamarra["price"] == 1800.0
    assert chamarra["sale_name"].startswith("Louis Vuitton")
    assert chamarra["printable"] is True
    assert chamarra["reason"] is None


def test_copias_por_omision_son_la_existencia(client, tienda, auth_admin, org):
    r = client.get("/api/labels/candidates", headers=_h(auth_admin, org))
    filas = _por_sku(r.json()["items"])
    assert filas["LV-CHAM-SLI-NEG-M"]["stock"] == 3.0
    assert filas["LV-CHAM-SLI-NEG-M"]["copies_default"] == 3
    assert filas["PLAY-BLA-CH"]["copies_default"] == 5


def test_existencia_arriba_del_tope_se_sugiere_topada(client, db, org, branch_a, tienda, auth_admin):
    """150 piezas no sugieren 150 copias: el renglón acepta 99 como máximo."""
    _prenda(db, org, branch_a, name="Calcetín", sku="CALC-NEG-U",
            barcode="2017000000037", stock="150", size="U", color="Negro")
    db.commit()
    filas = _por_sku(client.get("/api/labels/candidates", headers=_h(auth_admin, org)).json()["items"])
    assert filas["CALC-NEG-U"]["stock"] == 150.0
    assert filas["CALC-NEG-U"]["copies_default"] == 99


def test_sin_codigo_se_lista_marcada_no_escondida(client, tienda, auth_admin, org):
    filas = _por_sku(client.get("/api/labels/candidates", headers=_h(auth_admin, org)).json()["items"])
    playera = filas["PLAY-BLA-CH"]
    assert playera["printable"] is False
    assert playera["reason"] == "Sin código de barras"


def test_filtros_de_busqueda_y_existencia(client, db, org, branch_a, tienda, auth_admin):
    r = client.get("/api/labels/candidates?search=Chamarra", headers=_h(auth_admin, org))
    assert list(_por_sku(r.json()["items"])) == ["LV-CHAM-SLI-NEG-M"]

    _prenda(db, org, branch_a, name="Gorra", sku="GORR-NEG-U",
            barcode="2017000000044", stock="0", size="U", color="Negro")
    db.commit()
    con_stock = _por_sku(client.get(
        "/api/labels/candidates?only_with_stock=true", headers=_h(auth_admin, org)
    ).json()["items"])
    assert "GORR-NEG-U" not in con_stock


def test_filtro_por_genero_invalido_es_422(client, tienda, auth_admin, org):
    r = client.get("/api/labels/candidates?gender=marciano", headers=_h(auth_admin, org))
    assert r.status_code == 422
    assert "HOMBRE" in r.json()["detail"]


def test_cajero_solo_ve_su_sucursal(client, tienda, auth_cajero_a, org):
    """`query_visible_products`: la prenda de la sucursal B no es suya."""
    filas = _por_sku(client.get("/api/labels/candidates", headers=_h(auth_cajero_a, org)).json()["items"])
    assert "LV-CHAM-SLI-NEG-M" in filas
    assert "VEST-ROJ-G" not in filas


def test_otra_organizacion_no_se_asoma(client, db, org, branch_a, tienda, auth_admin):
    otra = Organization(name="Otra Tienda", status="ACTIVE")
    db.add(otra)
    db.flush()
    _, ajena = _prenda(db, otra, None, name="Bolso ajeno", sku="AJENO-1",
                       barcode="2017000000051")
    db.commit()

    filas = _por_sku(client.get("/api/labels/candidates", headers=_h(auth_admin, org)).json()["items"])
    assert "AJENO-1" not in filas

    r = client.post("/api/labels/jobs", headers=_h(auth_admin, org),
                    json={"items": [{"variant_id": ajena.id, "copies": 1}]})
    assert r.status_code == 200
    assert r.json()["labels"] == 0
    assert r.json()["skipped"][0]["reason"] == "No disponible para tu sucursal"


# ── /preview ─────────────────────────────────────────────────────────────────
def test_preview_de_una_variante(client, tienda, auth_admin, org):
    _, variante = tienda["chamarra"]
    r = client.post("/api/labels/preview", headers=_h(auth_admin, org),
                    json={"variant_id": variante.id})
    assert r.status_code == 200
    cuerpo = r.json()
    assert (cuerpo["width"], cuerpo["height"]) == (408, 200)
    assert cuerpo["kind"] == "EAN13"
    assert cuerpo["zpl"].startswith("^XA")
    tipos = [e["type"] for e in cuerpo["elements"]]
    assert tipos.count("barcode") == 1
    barras = next(e for e in cuerpo["elements"] if e["type"] == "barcode")
    assert set(barras["bits"]) == {"0", "1"}
    assert len(barras["bits"]) == 95
    assert barras["module_width"] == 2
    textos = [e["text"] for e in cuerpo["elements"] if e["type"] == "text"]
    assert "Louis Vuitton" in textos
    assert "M / Negro" in textos


def test_preview_con_datos_sueltos(client, tienda, auth_admin, org):
    r = client.post("/api/labels/preview", headers=_h(auth_admin, org),
                    json={"sku": "X-1", "name": "Prueba", "barcode": "ABC-123", "price": "99.50"})
    assert r.status_code == 200
    assert r.json()["kind"] == "CODE128"
    assert "$99.50" in r.json()["zpl"]


def test_preview_sin_codigo_es_422(client, tienda, auth_admin, org):
    _, variante = tienda["sin_codigo"]
    r = client.post("/api/labels/preview", headers=_h(auth_admin, org),
                    json={"variant_id": variante.id})
    assert r.status_code == 422
    assert "código de barras" in r.json()["detail"]


def test_preview_de_variante_ajena_es_404(client, db, org, tienda, auth_admin):
    otra = Organization(name="Tercera", status="ACTIVE")
    db.add(otra)
    db.flush()
    _, ajena = _prenda(db, otra, None, name="Ajeno", sku="AJENO-2", barcode=EAN_OK)
    db.commit()
    r = client.post("/api/labels/preview", headers=_h(auth_admin, org),
                    json={"variant_id": ajena.id})
    assert r.status_code == 404


# ── /jobs ────────────────────────────────────────────────────────────────────
def test_trabajo_entrega_el_zpl_en_base64(client, tienda, auth_admin, org):
    _, variante = tienda["chamarra"]
    r = client.post("/api/labels/jobs", headers=_h(auth_admin, org),
                    json={"items": [{"variant_id": variante.id, "copies": 3}]})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["labels"] == 3
    assert cuerpo["skipped"] == []
    zpl = base64.b64decode(cuerpo["content_base64"]).decode("utf-8")
    assert zpl.count("^XA") == 1
    assert "^PQ3" in zpl
    assert f"^FD{EAN_OK}^FS" in zpl


def test_variante_sin_codigo_cae_en_skipped(client, tienda, auth_admin, org):
    _, con_codigo = tienda["chamarra"]
    _, sin_codigo = tienda["sin_codigo"]
    r = client.post("/api/labels/jobs", headers=_h(auth_admin, org), json={"items": [
        {"variant_id": con_codigo.id, "copies": 1},
        {"variant_id": sin_codigo.id, "copies": 4},
    ]})
    assert r.status_code == 200
    cuerpo = r.json()
    # El renglón malo no tumba el trabajo: se imprime el resto.
    assert cuerpo["labels"] == 1
    assert cuerpo["skipped"] == [
        {"variant_id": sin_codigo.id, "sku": "PLAY-BLA-CH", "reason": "Sin código de barras"}
    ]


def test_cajero_no_imprime_la_prenda_de_otra_sucursal(client, tienda, auth_cajero_a, org):
    _, ajena = tienda["otra_sucursal"]
    r = client.post("/api/labels/jobs", headers=_h(auth_cajero_a, org),
                    json={"items": [{"variant_id": ajena.id, "copies": 1}]})
    assert r.status_code == 200
    assert r.json()["labels"] == 0
    assert r.json()["skipped"][0]["reason"] == "No disponible para tu sucursal"


def test_tope_de_500_etiquetas(client, tienda, auth_admin, org):
    _, variante = tienda["chamarra"]
    items = [{"variant_id": variante.id, "copies": 99} for _ in range(6)]  # 594
    r = client.post("/api/labels/jobs", headers=_h(auth_admin, org), json={"items": items})
    assert r.status_code == 422
    detalle = r.json()["detail"]
    assert "594" in detalle and "500" in detalle


def test_justo_en_el_tope_pasa(client, tienda, auth_admin, org):
    _, variante = tienda["chamarra"]
    items = [{"variant_id": variante.id, "copies": 50} for _ in range(10)]  # 500
    r = client.post("/api/labels/jobs", headers=_h(auth_admin, org), json={"items": items})
    assert r.status_code == 200
    assert r.json()["labels"] == 500


def test_copias_fuera_de_rango_son_422(client, tienda, auth_admin, org):
    _, variante = tienda["chamarra"]
    for copias in (0, 100):
        r = client.post("/api/labels/jobs", headers=_h(auth_admin, org),
                        json={"items": [{"variant_id": variante.id, "copies": copias}]})
        assert r.status_code == 422, copias
    r = client.post("/api/labels/jobs", headers=_h(auth_admin, org), json={"items": []})
    assert r.status_code == 422


# ── /test y gating ───────────────────────────────────────────────────────────
def test_etiqueta_de_prueba(client, tienda, auth_admin, org):
    r = client.get("/api/labels/test", headers=_h(auth_admin, org))
    assert r.status_code == 200
    zpl = base64.b64decode(r.json()["content_base64"]).decode("utf-8")
    assert "PRUEBA-51X25" in zpl


def test_sin_el_modulo_el_cajero_no_entra(client, db, org, tienda, auth_cajero_a):
    """El gate es por módulo: ADMIN/DUEÑO lo brincan (`require_module`), un
    CAJERO no."""
    _habilitar(db, org, "labels", enabled=False)
    for metodo, ruta, cuerpo in (
        ("get", "/api/labels/candidates", None),
        ("get", "/api/labels/test", None),
        ("post", "/api/labels/preview", {"sku": "X", "name": "X", "barcode": EAN_OK}),
        ("post", "/api/labels/jobs", {"items": [{"variant_id": "x", "copies": 1}]}),
    ):
        r = getattr(client, metodo)(ruta, headers=_h(auth_cajero_a, org), json=cuerpo) \
            if cuerpo is not None else getattr(client, metodo)(ruta, headers=_h(auth_cajero_a, org))
        assert r.status_code == 403, ruta
        assert "labels" in r.json()["detail"]


def test_con_el_modulo_el_cajero_si_entra(client, tienda, auth_cajero_a, org):
    assert client.get("/api/labels/test", headers=_h(auth_cajero_a, org)).status_code == 200
