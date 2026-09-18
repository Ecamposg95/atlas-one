"""La primera combinacion de la matriz ES la variante principal.

Antes, el alta de una prenda con tallas S/M/L creaba CUATRO variantes: la
"Estándar" sin talla que `create_product` siempre inventaba, mas las tres de
`extra_variants`. El POS pintaba una celda "—" que nadie podia vender.
Ahora el alta acepta `color`/`size` para la principal y la matriz manda su
primera fila ahi, no en `extra_variants`.
"""
from decimal import Decimal

import pytest

from app.models.modules import Module, OrganizationModule
from app.models.products import ProductVariant


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


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


@pytest.fixture()
def boutique(db, org):
    _habilitar(db, org, "variants")
    return org


class TestAltaConPrincipalConAtributos:
    def test_la_primera_combinacion_es_la_principal(self, client, db, boutique, branch_a, auth_admin):
        r = client.post("/api/products/", json={
            "name": "Blusa", "sku": "BLS", "price": "300", "cost": "150",
            "color": "Rojo", "size": "S",
            "target_branch_ids": [branch_a.id],
            "extra_variants": [{"color": "Rojo", "size": "M"}],
        }, headers=_h(auth_admin, boutique))
        assert r.status_code in (200, 201), r.text
        variantes = r.json()["variants"]
        assert len(variantes) == 2, variantes
        por_sku = {v["sku"]: v for v in variantes}
        assert por_sku["BLS"]["variant_name"] == "Rojo / S"
        assert por_sku["BLS"]["color"] == "Rojo" and por_sku["BLS"]["size"] == "S"
        assert por_sku["BLS-ROJO-M"]["variant_name"] == "Rojo / M"
        assert "Estándar" not in {v["variant_name"] for v in variantes}

    def test_pareja_repetida_entre_principal_y_extra_es_409(self, client, db, boutique, branch_a, auth_admin):
        r = client.post("/api/products/", json={
            "name": "Blusa", "sku": "BLS2", "price": "300", "cost": "150",
            "color": "Rojo", "size": "S",
            "target_branch_ids": [branch_a.id],
            "extra_variants": [{"color": "rojo", "size": "s", "sku": "BLS2-OTRO"}],
        }, headers=_h(auth_admin, boutique))
        assert r.status_code == 409, r.text
        assert "Ya existe la variante" in r.json()["detail"]
        # El alta aborta antes de crear la hermana. (Que tampoco quede la
        # principal lo garantiza el cierre de la sesión sin commit: aquí no se
        # puede comprobar porque el test comparte la sesión con la request.)
        assert db.query(ProductVariant).filter(ProductVariant.sku == "BLS2-OTRO").count() == 0

    def test_talla_demasiado_larga_en_la_principal_es_422(self, client, boutique, branch_a, auth_admin):
        r = client.post("/api/products/", json={
            "name": "Blusa", "sku": "BLS3", "price": "300", "cost": "150",
            "size": "x" * 31,
            "target_branch_ids": [branch_a.id],
        }, headers=_h(auth_admin, boutique))
        assert r.status_code == 422, r.text
        assert "talla" in r.json()["detail"].lower()

    def test_sin_color_ni_talla_sigue_siendo_estandar(self, client, org, branch_a, auth_admin):
        """Neutralidad: los tenants que no usan la matriz no cambian."""
        r = client.post("/api/products/", json={
            "name": "Refresco", "sku": "REF", "price": "20", "cost": "10",
            "target_branch_ids": [branch_a.id],
        }, headers=_h(auth_admin, org))
        assert r.status_code in (200, 201), r.text
        variantes = r.json()["variants"]
        assert len(variantes) == 1
        assert variantes[0]["variant_name"] == "Estándar"
        assert variantes[0]["color"] is None and variantes[0]["size"] is None


class TestEdicionDeLaPrincipal:
    def _crear(self, client, org, auth_admin, branch_a):
        r = client.post("/api/products/", json={
            "name": "Falda", "sku": "FLD", "price": "300", "cost": "150",
            "color": "Negro", "size": "S",
            "target_branch_ids": [branch_a.id],
            "extra_variants": [{"color": "Negro", "size": "M"}],
        }, headers=_h(auth_admin, org))
        assert r.status_code in (200, 201), r.text
        return r.json()["id"]

    def test_put_producto_actualiza_la_etiqueta_de_la_principal(self, client, db, boutique, branch_a, auth_admin):
        pid = self._crear(client, boutique, auth_admin, branch_a)
        r = client.put(f"/api/products/{pid}", json={"size": "Ch"}, headers=_h(auth_admin, boutique))
        assert r.status_code == 200, r.text
        principal = next(v for v in r.json()["variants"] if v["sku"] == "FLD")
        assert principal["size"] == "Ch"
        assert principal["variant_name"] == "Negro / Ch"

    def test_put_producto_con_pareja_de_una_hermana_es_409(self, client, db, boutique, branch_a, auth_admin):
        pid = self._crear(client, boutique, auth_admin, branch_a)
        r = client.put(f"/api/products/{pid}", json={"size": "M"}, headers=_h(auth_admin, boutique))
        assert r.status_code == 409, r.text
        assert db.query(ProductVariant).filter(ProductVariant.sku == "FLD").one().size == "S"


class TestExistenciaInicialEnElAlta:
    """El alta reparte la existencia inicial por talla, no toda en la primera.

    La primera fila de la matriz es la principal (`initial_stock` del
    formulario) y cada hermana trae la suya en `extra_variants`.
    """

    def test_cada_talla_nace_con_su_existencia_en_la_sucursal_elegida(
        self, client, db, boutique, branch_a, auth_admin,
    ):
        from app.models.inventory import InventoryMovement, StockOnHand
        r = client.post("/api/products/", json={
            "name": "Falda", "sku": "FLD", "price": "250", "cost": "100",
            "size": "Ch",
            "target_branch_ids": [branch_a.id],
            "initial_stock": "3", "branch_id": branch_a.id,
            "extra_variants": [
                {"size": "M", "initial_stock": "2"},
                {"size": "G"},
            ],
        }, headers=_h(auth_admin, boutique))
        assert r.status_code in (200, 201), r.text

        esperado = {"FLD": Decimal("3"), "FLD-M": Decimal("2"), "FLD-G": Decimal("0")}
        for sku, qty in esperado.items():
            v = db.query(ProductVariant).filter(ProductVariant.sku == sku).one()
            soh = db.query(StockOnHand).filter(StockOnHand.variant_id == v.id,
                                               StockOnHand.branch_id == branch_a.id).one()
            assert soh.qty_on_hand == qty, sku
            movs = db.query(InventoryMovement).filter(InventoryMovement.variant_id == v.id).count()
            assert movs == (1 if qty > 0 else 0), sku
