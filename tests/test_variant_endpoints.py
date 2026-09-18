"""CRUD de variantes (color/talla) del preset boutique."""
from decimal import Decimal

import pytest

from app.models.inventory import StockOnHand
from app.models.modules import Module, OrganizationModule
from app.models.products import ProductBranchStatus, ProductVariant
from conftest import _make_product


def _habilitar(db, org, key):
    if db.query(Module).filter(Module.key == key).first() is None:
        db.add(Module(key=key, name=key)); db.flush()
    om = db.query(OrganizationModule).filter(OrganizationModule.organization_id == org.id,
                                             OrganizationModule.module_key == key).first()
    if om is None:
        db.add(OrganizationModule(organization_id=org.id, module_key=key, is_enabled=True))
    else:
        om.is_enabled = True
    db.commit()


@pytest.fixture()
def playera(db, org, branch_a):
    _habilitar(db, org, "variants")
    p, v = _make_product(db, org, "Playera", "PLY", 100, [(branch_a.id, True)])
    v.variant_name = "Estándar"
    db.commit()
    return p, v


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


class TestCrearVariantes:
    def test_crea_matriz_con_sku_generado_y_stock_cero(self, client, db, org, branch_a, playera, auth_admin):
        p, v = playera
        r = client.post(f"/api/products/{p.id}/variants", json={"variants": [
            {"color": "Rojo", "size": "M"},
            {"color": "Rojo", "size": "L", "sku": "PLY-RL", "barcode": "7500000000009", "price": "130"},
        ]}, headers=_h(auth_admin, org))
        assert r.status_code == 201, r.text
        skus = {x["sku"]: x for x in r.json()["variants"]}
        assert set(skus) == {"PLY", "PLY-ROJO-M", "PLY-RL"}
        assert skus["PLY-ROJO-M"]["variant_name"] == "Rojo / M"
        assert Decimal(str(skus["PLY-ROJO-M"]["price"])) == Decimal("100")   # hereda el precio base
        assert Decimal(str(skus["PLY-RL"]["price"])) == Decimal("130")
        nueva = db.query(ProductVariant).filter(ProductVariant.sku == "PLY-ROJO-M").one()
        assert db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == nueva.id,
                                                    ProductBranchStatus.branch_id == branch_a.id).count() == 1
        soh = db.query(StockOnHand).filter(StockOnHand.variant_id == nueva.id).one()
        assert soh.qty_on_hand == Decimal("0")

    def test_rechaza_pareja_repetida_y_sku_duplicado(self, client, db, org, playera, auth_admin):
        p, v = playera
        r = client.post(f"/api/products/{p.id}/variants", json={"variants": [{"color": "Rojo", "size": "M"}]},
                        headers=_h(auth_admin, org))
        assert r.status_code == 201
        r2 = client.post(f"/api/products/{p.id}/variants", json={"variants": [{"color": "rojo", "size": "m"}]},
                         headers=_h(auth_admin, org))
        assert r2.status_code == 409
        r3 = client.post(f"/api/products/{p.id}/variants", json={"variants": [{"color": "Azul", "size": "M", "sku": "PLY"}]},
                         headers=_h(auth_admin, org))
        assert r3.status_code == 409

    def test_talla_demasiado_larga_es_422(self, client, org, playera, auth_admin):
        p, _ = playera
        r = client.post(f"/api/products/{p.id}/variants", json={"variants": [{"color": "Rojo", "size": "x" * 31}]},
                        headers=_h(auth_admin, org))
        assert r.status_code == 422

    def test_producto_de_otra_org_es_404(self, client, db, org, auth_admin):
        from app.models.organization import Organization
        otra = Organization(name="Otra", status="ACTIVE"); db.add(otra); db.flush()
        p_ajeno, _ = _make_product(db, otra, "Ajena", "AJ-1", 10); db.commit()
        r = client.post(f"/api/products/{p_ajeno.id}/variants", json={"variants": [{"color": "Rojo", "size": "M"}]},
                        headers=_h(auth_admin, org))
        assert r.status_code == 404

    def test_cajero_sin_modulo_es_403(self, client, db, org, branch_a, auth_cajero_a):
        p, v = _make_product(db, org, "Gorra", "GOR", 50, [(branch_a.id, True)]); db.commit()
        r = client.post(f"/api/products/{p.id}/variants", json={"variants": [{"color": "Rojo", "size": "U"}]},
                        headers=_h(auth_cajero_a, org))
        assert r.status_code == 403


class TestEditarYBorrar:
    def test_put_cambia_talla_y_recalcula_etiqueta(self, client, db, org, playera, auth_admin):
        p, v = playera
        r = client.put(f"/api/products/variants/{v.id}", json={"color": "Negro", "size": "XL", "barcode": "7500000000011"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        db.refresh(v)
        assert (v.color, v.size, v.variant_name, v.barcode) == ("Negro", "XL", "Negro / XL", "7500000000011")

    def test_put_barcode_repetido_en_la_org_es_409(self, client, db, org, branch_a, playera, auth_admin):
        p, v = playera
        _, otra = _make_product(db, org, "Gorra", "GOR", 50, [(branch_a.id, True)])
        otra.barcode = "7500000000022"; db.commit()
        r = client.put(f"/api/products/variants/{v.id}", json={"barcode": "7500000000022"}, headers=_h(auth_admin, org))
        assert r.status_code == 409

    def test_put_talla_demasiado_larga_es_422(self, client, org, playera, auth_admin):
        p, v = playera
        r = client.put(f"/api/products/variants/{v.id}", json={"size": "x" * 31}, headers=_h(auth_admin, org))
        assert r.status_code == 422

    def test_delete_con_stock_es_409_y_sin_stock_borra_suave(self, client, db, org, branch_a, playera, auth_admin):
        p, v = playera
        r = client.post(f"/api/products/{p.id}/variants", json={"variants": [{"color": "Rojo", "size": "M"}]},
                        headers=_h(auth_admin, org))
        nueva_id = next(x["id"] for x in r.json()["variants"] if x["sku"] == "PLY-ROJO-M")
        assert client.delete(f"/api/products/variants/{v.id}", headers=_h(auth_admin, org)).status_code == 409  # tiene 100
        r2 = client.delete(f"/api/products/variants/{nueva_id}", headers=_h(auth_admin, org))
        assert r2.status_code == 204
        assert db.query(ProductVariant).get(nueva_id).deleted_at is not None
        # La variante retirada ya no aparece en el producto ni sigue vendible/visible.
        r3 = client.get(f"/api/products/{p.id}", headers=_h(auth_admin, org))
        assert r3.status_code == 200, r3.text
        assert nueva_id not in {x["id"] for x in r3.json()["variants"]}
        pbs = db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == nueva_id,
                                                    ProductBranchStatus.branch_id == branch_a.id).one()
        assert (pbs.is_active_pos, pbs.is_visible) == (False, False)
        # La ultima variante no se puede borrar aunque quede en cero
        soh = db.query(StockOnHand).filter(StockOnHand.variant_id == v.id).one(); soh.qty_on_hand = Decimal(0); db.commit()
        assert client.delete(f"/api/products/variants/{v.id}", headers=_h(auth_admin, org)).status_code == 409


class TestExtraVariantsEnElAlta:
    def test_create_product_honra_extra_variants(self, client, db, org, branch_a, auth_admin):
        _habilitar(db, org, "variants")
        r = client.post("/api/products/", json={
            "name": "Pantalón", "sku": "PNT", "price": "300", "cost": "150",
            "target_branch_ids": [branch_a.id],
            "extra_variants": [{"color": "Azul", "size": "30"}, {"color": "Azul", "size": "32", "sku": "PNT-A32"}],
        }, headers=_h(auth_admin, org))
        assert r.status_code in (200, 201), r.text
        skus = {x["sku"] for x in r.json()["variants"]}
        assert skus == {"PNT", "PNT-AZUL-30", "PNT-A32"}
        # Las hermanas deben quedar tan vendibles como la principal: PBS +
        # StockOnHand(0) en la misma sucursal (era el bug critico #1: la
        # principal se `add()`-eaba sin flush y `crear_variantes` no la veia).
        for sku in ("PNT-AZUL-30", "PNT-A32"):
            hermana = db.query(ProductVariant).filter(ProductVariant.sku == sku).one()
            pbs = db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == hermana.id,
                                                       ProductBranchStatus.branch_id == branch_a.id).one()
            assert pbs.is_active_pos is True
            soh = db.query(StockOnHand).filter(StockOnHand.variant_id == hermana.id,
                                               StockOnHand.branch_id == branch_a.id).one()
            assert soh.qty_on_hand == Decimal("0")


class TestGuardDeRol:
    """`require_module("variants")` solo mira el modulo de la org: sin guard de
    rol, un VENDEDOR de la boutique podia crear variantes, cambiar precios y
    retirar tallas. Mismo criterio que `delete_product` (_PRODUCT_ADVANCED_ROLES).
    """

    def test_vendedor_no_puede_crear_variantes(self, client, db, org, playera,
                                               auth_vendedor_sin_sucursal):
        p, v = playera
        r = client.post(f"/api/products/{p.id}/variants",
                        json={"variants": [{"color": "Rojo", "size": "M"}]},
                        headers=_h(auth_vendedor_sin_sucursal, org))
        assert r.status_code == 403, r.text
        assert db.query(ProductVariant).filter(ProductVariant.product_id == p.id).count() == 1

    def test_vendedor_no_puede_editar_variantes(self, client, db, org, playera,
                                                auth_vendedor_sin_sucursal):
        p, v = playera
        r = client.put(f"/api/products/variants/{v.id}", json={"price": "1"},
                       headers=_h(auth_vendedor_sin_sucursal, org))
        assert r.status_code == 403, r.text
        db.refresh(v)
        assert Decimal(str(v.price)) == Decimal("100")

    def test_vendedor_no_puede_retirar_variantes(self, client, db, org, playera,
                                                 auth_vendedor_sin_sucursal, auth_admin):
        p, v = playera
        client.post(f"/api/products/{p.id}/variants",
                    json={"variants": [{"color": "Rojo", "size": "M"}]},
                    headers=_h(auth_admin, org))
        nueva = db.query(ProductVariant).filter(ProductVariant.sku == "PLY-ROJO-M").one()
        r = client.delete(f"/api/products/variants/{nueva.id}",
                          headers=_h(auth_vendedor_sin_sucursal, org))
        assert r.status_code == 403, r.text
        db.refresh(nueva)
        assert nueva.deleted_at is None


class TestExistenciaInicialPorVariante:
    """Existencia inicial por talla (hallazgo #2 de la auditoria de variantes).

    Antes el alta cargaba TODO el stock inicial en la principal y las hermanas
    nacian en 0: la boutique terminaba con las diez prendas en la talla Ch y
    M/G invendibles hasta hacer un ajuste manual.
    """

    def test_cada_hermana_nace_con_su_existencia_y_su_kardex(
        self, client, db, org, branch_a, playera, auth_admin,
    ):
        from app.models.inventory import InventoryMovement, MovementType
        p, _ = playera
        r = client.post(f"/api/products/{p.id}/variants", json={"variants": [
            {"color": "Rojo", "size": "M", "initial_stock": "5"},
            {"color": "Rojo", "size": "L"},
        ]}, headers=_h(auth_admin, org))
        assert r.status_code == 201, r.text

        con_stock = db.query(ProductVariant).filter(ProductVariant.sku == "PLY-ROJO-M").one()
        soh = db.query(StockOnHand).filter(StockOnHand.variant_id == con_stock.id).one()
        assert soh.branch_id == branch_a.id
        assert soh.qty_on_hand == Decimal("5")
        movs = db.query(InventoryMovement).filter(InventoryMovement.variant_id == con_stock.id).all()
        assert len(movs) == 1
        assert movs[0].movement_type == MovementType.ADJUSTMENT_IN
        assert movs[0].qty_change == Decimal("5")
        assert movs[0].qty_before == Decimal("0") and movs[0].qty_after == Decimal("5")
        assert movs[0].branch_id == branch_a.id

        # Neutralidad: sin `initial_stock` todo sigue como antes (0 y sin kardex).
        sin_stock = db.query(ProductVariant).filter(ProductVariant.sku == "PLY-ROJO-L").one()
        assert db.query(StockOnHand).filter(StockOnHand.variant_id == sin_stock.id).one().qty_on_hand == Decimal("0")
        assert db.query(InventoryMovement).filter(InventoryMovement.variant_id == sin_stock.id).count() == 0

    def test_existencia_inicial_negativa_es_422(self, client, db, org, playera, auth_admin):
        p, _ = playera
        r = client.post(f"/api/products/{p.id}/variants", json={"variants": [
            {"color": "Rojo", "size": "M", "initial_stock": "-1"},
        ]}, headers=_h(auth_admin, org))
        assert r.status_code == 422, r.text
        assert db.query(ProductVariant).filter(ProductVariant.sku == "PLY-ROJO-M").count() == 0

    def test_con_varias_sucursales_pide_cual_y_la_respeta(
        self, client, db, org, branch_a, branch_b, auth_admin,
    ):
        _habilitar(db, org, "variants")
        p, _ = _make_product(db, org, "Vestido", "VST", 400,
                             [(branch_a.id, True), (branch_b.id, True)])
        db.commit()
        # Sin decir a que sucursal, el backend no adivina.
        r = client.post(f"/api/products/{p.id}/variants", json={"variants": [
            {"size": "M", "initial_stock": "4"},
        ]}, headers=_h(auth_admin, org))
        assert r.status_code == 422, r.text

        r2 = client.post(f"/api/products/{p.id}/variants", json={
            "branch_id": branch_b.id,
            "variants": [{"size": "M", "initial_stock": "4"}],
        }, headers=_h(auth_admin, org))
        assert r2.status_code == 201, r2.text
        nueva = db.query(ProductVariant).filter(ProductVariant.sku == "VST-M").one()
        por_sucursal = {s.branch_id: s.qty_on_hand
                        for s in db.query(StockOnHand).filter(StockOnHand.variant_id == nueva.id).all()}
        assert por_sucursal == {branch_a.id: Decimal("0"), branch_b.id: Decimal("4")}
