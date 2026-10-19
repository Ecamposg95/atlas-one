"""PUT /api/products/variants/{id}: el SKU solo se valida si cambia."""
from datetime import datetime, timezone

from conftest import _make_product
from app.models.products import ProductVariant


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


def _con_gemelo_archivado(db, org, branch_a, sku_vivo, sku_archivado):
    _, v = _make_product(db, org, "Vivo", sku_vivo, 100, [(branch_a.id, True)])
    p2, v2 = _make_product(db, org, "Viejo", sku_archivado, 100, [(branch_a.id, True)])
    ahora = datetime.now(timezone.utc)
    p2.deleted_at = ahora; p2.is_active = False; v2.deleted_at = ahora
    db.flush()
    return v


class TestEditarVarianteSku:
    def test_mismo_sku_con_gemelo_archivado_no_choca(self, client, db, org, branch_a, auth_admin):
        # La única (org, sku) distingue mayúsculas; `sku_en_uso` no: el gemelo
        # archivado "gem-x" chocaba con el vivo "GEM-X" aunque no cambiara.
        v = _con_gemelo_archivado(db, org, branch_a, "GEM-X", "gem-x")
        r = client.put(f"/api/products/variants/{v.id}", json={"sku": "GEM-X", "price": "250"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        db.expire_all()
        assert db.query(ProductVariant).get(v.id).price == 250

    def test_cambiar_a_sku_de_archivado_es_409_con_pista(self, client, db, org, branch_a, auth_admin):
        v = _con_gemelo_archivado(db, org, branch_a, "VIVO-1", "ARCH-1")
        r = client.put(f"/api/products/variants/{v.id}", json={"sku": "ARCH-1"},
                       headers=_h(auth_admin, org))
        assert r.status_code == 409, r.text
        assert "archivado" in r.json()["detail"]
