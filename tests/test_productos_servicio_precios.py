"""Empaques y escalones: una sola versión del armado (antes create, update y
upload lo hacían cada uno a su manera)."""
import pytest
from fastapi import HTTPException

from conftest import _make_product
from app.models.products import PackagingUnit, ProductPrice
from app.modules.products.schemas import PackagingUnitCreate, ProductPriceCreate
from app.modules.products.services.precios import armar_empaques, armar_escalones


class TestEmpaquesYEscalones:
    def test_mapa_por_temp_id_y_nombre_enlaza_escalones(self, db, org, branch_a):
        _, v = _make_product(db, org, "Refresco", "REF-1", 10, [(branch_a.id, True)])
        mapa = armar_empaques(db, org.id, v, [
            PackagingUnitCreate(temp_id="tmp-caja", name="Caja", units_per_package=24, package_price=200),
        ])
        caja_id = mapa["tmp-caja"]
        assert mapa["caja"] == caja_id
        armar_escalones(db, org.id, v, [
            ProductPriceCreate(price_name="Mayoreo", min_quantity=12, unit_price=9, linked_package_id="tmp-caja"),
            ProductPriceCreate(price_name="Caja", min_quantity=24, unit_price=8),   # enlaza por nombre
            ProductPriceCreate(price_name="Suelto", min_quantity=1, unit_price=10),
        ], mapa)
        por_nombre = {p.price_name: p.linked_package_id
                      for p in db.query(ProductPrice).filter(ProductPrice.variant_id == v.id).all()}
        assert por_nombre == {"Mayoreo": caja_id, "Caja": caja_id, "Suelto": None}

    def test_reemplazar_borra_lo_anterior_y_desenlaza_antes(self, db, org, branch_a):
        _, v = _make_product(db, org, "Refresco", "REF-2", 10, [(branch_a.id, True)])
        mapa = armar_empaques(db, org.id, v, [PackagingUnitCreate(name="Caja", units_per_package=24, package_price=200)])
        armar_escalones(db, org.id, v, [ProductPriceCreate(price_name="Caja", min_quantity=24, unit_price=8)], mapa)
        mapa2 = armar_empaques(db, org.id, v, [PackagingUnitCreate(name="Pack", units_per_package=6, package_price=55)], reemplazar=True)
        armar_escalones(db, org.id, v, [ProductPriceCreate(price_name="Pack", min_quantity=6, unit_price=9)], mapa2, reemplazar=True)
        assert [p.name for p in db.query(PackagingUnit).filter(PackagingUnit.variant_id == v.id).all()] == ["Pack"]
        precios = db.query(ProductPrice).filter(ProductPrice.variant_id == v.id).all()
        assert [(p.price_name, p.linked_package_id) for p in precios] == [("Pack", mapa2["pack"])]
        # La relación cargada en la variante no queda con filas borradas.
        assert [p.name for p in v.packaging_units] == ["Pack"]
        assert [p.price_name for p in v.prices] == ["Pack"]

    def test_reemplazar_borra_registros_legados_sin_organizacion(self, db, org, branch_a):
        """Legado con `organization_id` NULL: debe salir (y desenlazarse antes)."""
        _, v = _make_product(db, org, "Legado", "LEG-1", 10, [(branch_a.id, True)])
        pkg = PackagingUnit(variant_id=v.id, name="Caja", units_per_package=12,
                            package_price=100, organization_id=None)
        db.add(pkg); db.flush()
        db.add(ProductPrice(variant_id=v.id, price_name="Caja", min_quantity=12,
                            unit_price=8, linked_package_id=pkg.id, organization_id=None))
        db.flush()
        armar_empaques(db, org.id, v, [], reemplazar=True)
        armar_escalones(db, org.id, v, [], {}, reemplazar=True)
        assert db.query(PackagingUnit).filter(PackagingUnit.variant_id == v.id).count() == 0
        assert db.query(ProductPrice).filter(ProductPrice.variant_id == v.id).count() == 0

    def test_escalon_en_cero_es_422_antes_de_escribir(self, db, org, branch_a):
        _, v = _make_product(db, org, "Refresco", "REF-3", 10, [(branch_a.id, True)])
        with pytest.raises(HTTPException) as exc:
            armar_escalones(db, org.id, v, [ProductPriceCreate(price_name="Caja", min_quantity=24, unit_price=0)], {})
        assert exc.value.status_code == 422 and "Caja" in exc.value.detail
        assert db.query(ProductPrice).filter(ProductPrice.variant_id == v.id).count() == 0

    def test_422_con_reemplazar_no_borra_los_escalones_previos(self, db, org, branch_a):
        _, v = _make_product(db, org, "Refresco", "REF-5", 10, [(branch_a.id, True)])
        armar_escalones(db, org.id, v, [ProductPriceCreate(price_name="Doc", min_quantity=12, unit_price=9)], {})
        with pytest.raises(HTTPException):
            armar_escalones(db, org.id, v, [ProductPriceCreate(price_name="Mal", min_quantity=2, unit_price=0)], {}, reemplazar=True)
        assert [p.price_name for p in db.query(ProductPrice).filter(ProductPrice.variant_id == v.id)] == ["Doc"]

    def test_listas_vacias_no_escriben_nada(self, db, org, branch_a):
        _, v = _make_product(db, org, "Refresco", "REF-4", 10, [(branch_a.id, True)])
        assert armar_empaques(db, org.id, v, None) == {}
        armar_escalones(db, org.id, v, None, {})
        assert db.query(PackagingUnit).filter(PackagingUnit.variant_id == v.id).count() == 0
