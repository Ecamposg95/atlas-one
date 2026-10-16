"""PUT /api/products/{id} por `services.actualizar_producto`.

Bug cerrado (spec §2.1): el SKU repetido respondía 400 con otro texto; ahora
409 con la misma regla que el alta (sin mayúsculas, incluye archivados).
"""
import inspect
from datetime import datetime, timezone

from conftest import _make_product
from app.models.products import ProductBranchStatus, ProductVariant


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


class TestSkuEnEdicion:
    def test_sku_de_otro_producto_es_409_no_400(self, client, db, org, branch_a, auth_admin):
        _make_product(db, org, "Uno", "UNO-1", 10, [(branch_a.id, True)])
        p2, _ = _make_product(db, org, "Dos", "DOS-1", 10, [(branch_a.id, True)])
        db.flush()
        r = client.put(f"/api/products/{p2.id}", json={"sku": "uno-1"}, headers=_h(auth_admin, org))
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == "El SKU 'uno-1' ya existe en esta organización."

    def test_sku_de_archivado_es_409_y_lo_dice(self, client, db, org, branch_a, auth_admin):
        p1, v1 = _make_product(db, org, "Vieja", "ARCH-1", 10, [(branch_a.id, True)])
        ahora = datetime.now(timezone.utc)
        p1.deleted_at = ahora; p1.is_active = False; v1.deleted_at = ahora
        p2, _ = _make_product(db, org, "Dos", "DOS-2", 10, [(branch_a.id, True)])
        db.flush()
        r = client.put(f"/api/products/{p2.id}", json={"sku": "ARCH-1"}, headers=_h(auth_admin, org))
        assert r.status_code == 409, r.text
        assert "archivado" in r.json()["detail"]

    def test_su_propio_sku_con_otra_caja_se_acepta(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Mío", "MIO-1", 10, [(branch_a.id, True)])
        db.flush()
        r = client.put(f"/api/products/{p.id}", json={"sku": " mio-1 "}, headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        db.refresh(v)
        assert v.sku == "mio-1"

    def test_sku_vacio_es_422_y_no_cambia(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Vacío", "VAC-1", 10, [(branch_a.id, True)])
        db.flush()
        r = client.put(f"/api/products/{p.id}", json={"sku": "   "}, headers=_h(auth_admin, org))
        assert r.status_code == 422, r.text
        assert r.json()["detail"] == "El SKU no puede quedar vacío"
        db.refresh(v)
        assert v.sku == "VAC-1"


class TestSucursalesEnEdicion:
    def test_sucursal_ajena_en_target_branch_ids_es_422(self, client, db, org, branch_a, auth_admin):
        from app.models.organization import Branch, BranchType, Organization
        otra = Organization(name="Otra", status="ACTIVE")
        db.add(otra); db.flush()
        ajena = Branch(name="Ajena", branch_type=BranchType.STORE, can_sell=True,
                       is_active=True, organization_id=otra.id)
        db.add(ajena); db.flush()
        p, v = _make_product(db, org, "P", "SUC-1", 10, [(branch_a.id, True)])
        db.flush()
        r = client.put(f"/api/products/{p.id}", json={"target_branch_ids": [ajena.id]}, headers=_h(auth_admin, org))
        assert r.status_code == 422, r.text
        assert r.json()["detail"] == "Una o más sucursales objetivo no pertenecen a tu organización."
        # Nada se borró: el PBS original sigue ahí.
        assert db.query(ProductBranchStatus).filter(ProductBranchStatus.variant_id == v.id).count() == 1


class TestHandlerDelgado:
    def test_update_product_cabe_en_40_lineas(self):
        from app.modules.products.router.core import update_product
        assert len(inspect.getsource(update_product).splitlines()) < 40

    def test_core_ya_no_define_atributos_principal(self):
        from app.modules.products.router import core
        assert not hasattr(core, "_atributos_principal")
