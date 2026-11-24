"""Precio por sucursal (2026-11-23).

Eleven Fashion: "quiero que cada quien tenga su precio". Con
`organization.precio_por_sucursal` encendido, el precio que edita alguien con
sucursal se guarda como `price_override` de SU sucursal; el precio base y las
demás sucursales no cambian. Apagado, todo sigue como antes.
"""
from decimal import Decimal

import pytest

from app.models.modules import Module, OrganizationModule
from app.models.products import ProductBranchStatus, ProductPrice, ProductVariant
from conftest import _make_product


def _habilitar(db, org, key):
    if db.query(Module).filter(Module.key == key).first() is None:
        db.add(Module(key=key, name=key))
        db.flush()
    om = db.query(OrganizationModule).filter(OrganizationModule.organization_id == org.id,
                                             OrganizationModule.module_key == key).first()
    if om is None:
        db.add(OrganizationModule(organization_id=org.id, module_key=key, is_enabled=True))
    else:
        om.is_enabled = True
    db.flush()


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


def _pbs(db, variante, branch):
    db.expire_all()
    return db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == variante.id,
                                                ProductBranchStatus.branch_id == branch.id).one()


@pytest.fixture()
def tienda(db, org, branch_a, branch_b):
    """Playera de $1,000 en talla M y G, dada de alta en las dos sucursales,
    con un escalón de mayoreo."""
    _habilitar(db, org, "catalog")
    _habilitar(db, org, "variants")
    p, v_m = _make_product(db, org, "Playera", "PLY-M", 1000, [(branch_a.id, True), (branch_b.id, True)])
    v_m.size = "M"
    v_g = ProductVariant(product_id=p.id, sku="PLY-G", price=Decimal("1000"), cost=Decimal("500"),
                         size="G", variant_name="G", organization_id=org.id)
    db.add(v_g)
    db.flush()
    for b in (branch_a, branch_b):
        db.add(ProductBranchStatus(variant_id=v_g.id, branch_id=b.id, organization_id=org.id,
                                   is_active_pos=True, is_visible=True))
    db.add(ProductPrice(variant_id=v_m.id, price_name="Mayoreo", min_quantity=Decimal("3"),
                        unit_price=Decimal("900"), organization_id=org.id))
    db.flush()
    return p, v_m, v_g


def _encender(db, org):
    org.precio_por_sucursal = True
    db.flush()


# ── Apagado: el comportamiento de siempre ────────────────────────────────────
def test_apagado_la_cajera_cambia_el_precio_base(client, db, org, tienda, branch_a, branch_b, auth_cajero_a):
    p, v_m, _ = tienda
    r = client.put(f"/api/products/{p.id}", json={"price": 800}, headers=_h(auth_cajero_a, org))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(ProductVariant, v_m.id).price == Decimal("800")
    assert _pbs(db, v_m, branch_a).price_override is None
    assert _pbs(db, v_m, branch_b).price_override is None


# ── Encendido ────────────────────────────────────────────────────────────────
def test_encendido_la_cajera_solo_cambia_su_sucursal(client, db, org, tienda, branch_a, branch_b, auth_cajero_a):
    p, v_m, v_g = tienda
    _encender(db, org)
    r = client.put(f"/api/products/{p.id}", json={"price": 800}, headers=_h(auth_cajero_a, org))
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["price"])) == Decimal("800")
    db.expire_all()
    assert db.get(ProductVariant, v_m.id).price == Decimal("1000")
    assert _pbs(db, v_m, branch_a).price_override == Decimal("800")
    assert _pbs(db, v_m, branch_b).price_override is None
    # Sin la casilla de "todas las tallas", la G no se toca.
    assert _pbs(db, v_g, branch_a).price_override is None


def test_encendido_a_todas_las_tallas_solo_en_su_sucursal(client, db, org, tienda, branch_a, branch_b, auth_cajero_a):
    p, v_m, v_g = tienda
    _encender(db, org)
    r = client.put(f"/api/products/{p.id}", json={"price": 700, "precio_a_todas_las_tallas": True},
                   headers=_h(auth_cajero_a, org))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert _pbs(db, v_m, branch_a).price_override == Decimal("700")
    assert _pbs(db, v_g, branch_a).price_override == Decimal("700")
    assert _pbs(db, v_g, branch_b).price_override is None
    assert db.get(ProductVariant, v_g.id).price == Decimal("1000")


def test_encendido_la_ficha_muestra_el_precio_de_cada_sucursal(client, db, org, tienda, branch_a, auth_cajero_a):
    p, v_m, v_g = tienda
    _encender(db, org)
    _pbs(db, v_g, branch_a).price_override = Decimal("650")
    db.flush()
    data = client.get(f"/api/products/{p.id}", headers=_h(auth_cajero_a, org)).json()
    por_sku = {v["sku"]: Decimal(str(v["price"])) for v in data["variants"]}
    # La talla con precio propio lo muestra en `price` (lo que pinta el editor);
    # la que no tiene, el base.
    assert por_sku == {"PLY-M": Decimal("1000"), "PLY-G": Decimal("650")}


def test_encendido_editar_una_talla_solo_cambia_su_sucursal(client, db, org, tienda, branch_a, branch_b, auth_cajero_a):
    p, v_m, v_g = tienda
    _encender(db, org)
    r = client.put(f"/api/products/variants/{v_g.id}", json={"price": 900}, headers=_h(auth_cajero_a, org))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(ProductVariant, v_g.id).price == Decimal("1000")
    assert _pbs(db, v_g, branch_a).price_override == Decimal("900")
    assert _pbs(db, v_g, branch_b).price_override is None
    g = next(v for v in r.json()["variants"] if v["sku"] == "PLY-G")
    assert Decimal(str(g["price"])) == Decimal("900")


def test_encendido_no_borra_los_escalones_del_catalogo(client, db, org, tienda, auth_cajero_a):
    """Con precio de sucursal la ficha llega sin escalones y el formulario los
    devuelve vacíos: no deben borrarse para las demás sucursales."""
    p, v_m, _ = tienda
    _encender(db, org)
    r = client.put(f"/api/products/{p.id}", json={"price": 800, "prices": []}, headers=_h(auth_cajero_a, org))
    assert r.status_code == 200, r.text
    db.expire_all()
    vivos = db.query(ProductPrice).filter(ProductPrice.variant_id == v_m.id,
                                          ProductPrice.deleted_at.is_(None)).count()
    assert vivos == 1


def test_encendido_sin_sucursal_se_edita_el_precio_base(client, db, org, tienda, branch_a, auth_admin_sin_sucursal):
    p, v_m, _ = tienda
    _encender(db, org)
    r = client.put(f"/api/products/{p.id}", json={"price": 1200}, headers=_h(auth_admin_sin_sucursal, org))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(ProductVariant, v_m.id).price == Decimal("1200")
    assert _pbs(db, v_m, branch_a).price_override is None


def test_encendido_talla_que_no_vende_su_sucursal_edita_el_base(client, db, org, branch_a, branch_b, auth_gerente_a):
    """Si la talla no está dada de alta en su sucursal, no hay precio de
    sucursal que editar: no se crea la fila (la habilitaría en el POS)."""
    _habilitar(db, org, "catalog")
    p, v = _make_product(db, org, "Solo B", "SOLO-B", 500, [(branch_b.id, True)])
    _encender(db, org)
    client.put(f"/api/products/{p.id}", json={"price": 450}, headers=_h(auth_gerente_a, org))
    db.expire_all()
    assert db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == v.id,
                                                ProductBranchStatus.branch_id == branch_a.id).count() == 0


def test_encendido_el_admin_con_sucursal_edita_el_precio_base(client, db, org, tienda, branch_a, branch_b, auth_admin_a):
    """ADMINISTRADOR/DUEÑO mandan en toda la organización aunque tengan sucursal."""
    p, v_m, v_g = tienda
    _encender(db, org)
    r = client.put(f"/api/products/{p.id}", json={"price": 1100}, headers=_h(auth_admin_a, org))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(ProductVariant, v_m.id).price == Decimal("1100")
    assert _pbs(db, v_m, branch_a).price_override is None
    r = client.put(f"/api/products/variants/{v_g.id}", json={"price": 1150}, headers=_h(auth_admin_a, org))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(ProductVariant, v_g.id).price == Decimal("1150")
    assert _pbs(db, v_g, branch_a).price_override is None


def test_encendido_la_ficha_del_admin_muestra_el_base_y_no_lo_pisa(client, db, org, tienda, branch_a, auth_admin_a):
    """Su sucursal tiene precio propio: la ficha del admin enseña el base, así
    que guardar sin tocar el precio no copia el de la sucursal al base."""
    p, v_m, _ = tienda
    _encender(db, org)
    _pbs(db, v_m, branch_a).price_override = Decimal("800")
    db.flush()
    data = client.get(f"/api/products/{p.id}", headers=_h(auth_admin_a, org)).json()
    assert Decimal(str(data["price"])) == Decimal("1000")
    assert len(data["prices"]) == 1  # los escalones siguen a la vista
    m = next(v for v in data["variants"] if v["sku"] == "PLY-M")
    assert Decimal(str(m["price"])) == Decimal("1000")
    assert Decimal(str(m["effective_price"])) == Decimal("800")  # el POS cobra el de la sucursal


def test_encendido_el_admin_fija_el_precio_de_una_sucursal_en_la_matriz(client, db, org, tienda, branch_a, branch_b, auth_admin_a):
    p, v_m, _ = tienda
    _encender(db, org)
    r = client.patch(f"/api/products/variants/{v_m.id}/branch-status", params={"branch_id": branch_b.id},
                     json={"price_override": 750}, headers=_h(auth_admin_a, org))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert _pbs(db, v_m, branch_b).price_override == Decimal("750")
    assert _pbs(db, v_m, branch_a).price_override is None
    assert db.get(ProductVariant, v_m.id).price == Decimal("1000")


# ── El ajuste ────────────────────────────────────────────────────────────────
def test_el_admin_lo_enciende_y_la_cajera_no(client, db, org, auth_admin, auth_cajero_a, admin_user, cajero_a):
    r = client.put("/api/organization/", json={"precio_por_sucursal": True}, headers=_h(auth_cajero_a, org))
    assert r.status_code == 403, r.text
    db.refresh(org)
    assert org.precio_por_sucursal is False
    r = client.put("/api/organization/", json={"precio_por_sucursal": True}, headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text
    assert r.json()["precio_por_sucursal"] is True
