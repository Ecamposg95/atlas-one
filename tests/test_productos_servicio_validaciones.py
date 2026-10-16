"""Validaciones 422 del alta/edición y constantes compartidas (services/comun.py)."""
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.organization import Branch, BranchType, Organization
from app.models.products import Brand, Department
from app.modules.products.schemas import ProductCreate, ProductPriceCreate
from app.modules.products.services.validaciones import (
    atributos_principal, exigir_campos_de_cajero, validar_departamento_y_marca,
    validar_escalones, validar_precio, validar_sucursales_de_la_org,
)


def _422(fn, *args, **kwargs) -> str:
    with pytest.raises(HTTPException) as exc:
        fn(*args, **kwargs)
    assert exc.value.status_code == 422
    return exc.value.detail


class TestPrecio:
    def test_cero_y_negativo_son_422(self):
        assert "mayor a cero" in _422(validar_precio, Decimal("0"))
        _422(validar_precio, Decimal("-1"))

    def test_none_no_se_valida_y_positivo_pasa(self):
        validar_precio(None)
        validar_precio(Decimal("0.01"))

    def test_detalle_personalizado(self):
        assert _422(validar_precio, Decimal("0"), detalle="El precio debe ser mayor a cero.") == "El precio debe ser mayor a cero."


class TestEscalones:
    def test_nombra_el_escalon_en_cero(self):
        detalle = _422(validar_escalones, [
            ProductPriceCreate(price_name="Mayoreo", min_quantity=3, unit_price=10),
            ProductPriceCreate(price_name="Caja", min_quantity=72, unit_price=0),
        ])
        assert detalle == "El precio del escalón 'Caja' debe ser mayor a cero."

    def test_lista_vacia_o_none_pasa(self):
        validar_escalones(None)
        validar_escalones([])


class TestSucursales:
    def test_ajena_es_422(self, db, org, branch_a):
        otra = Organization(name="Otra", status="ACTIVE")
        db.add(otra); db.flush()
        ajena = Branch(name="Ajena", branch_type=BranchType.STORE, can_sell=True,
                       is_active=True, organization_id=otra.id)
        db.add(ajena); db.flush()
        detalle = _422(validar_sucursales_de_la_org, db, org.id, [branch_a.id, ajena.id])
        assert detalle == "Una o más sucursales objetivo no pertenecen a tu organización."

    def test_propias_devuelve_el_conjunto_sin_repetidos(self, db, org, branch_a, branch_b):
        assert validar_sucursales_de_la_org(db, org.id, [branch_a.id, branch_b.id, branch_a.id]) == {branch_a.id, branch_b.id}
        assert validar_sucursales_de_la_org(db, org.id, []) == set()


class TestDepartamentoYMarca:
    def test_de_otra_org_es_422(self, db, org):
        otra = Organization(name="Otra", status="ACTIVE")
        db.add(otra); db.flush()
        d = Department(name="X", organization_id=otra.id)
        m = Brand(name="Y", organization_id=otra.id)
        db.add_all([d, m]); db.flush()
        assert "Departamento" in _422(validar_departamento_y_marca, db, org.id, d.id, None)
        assert "Marca" in _422(validar_departamento_y_marca, db, org.id, None, m.id)

    def test_nones_y_propios_pasan(self, db, org):
        d = Department(name="Propio", organization_id=org.id)
        db.add(d); db.flush()
        validar_departamento_y_marca(db, org.id, None, None)
        validar_departamento_y_marca(db, org.id, d.id, None)


class TestCajeroYAtributos:
    def test_campos_requeridos_nombra_los_faltantes(self):
        datos = ProductCreate(name="  ", sku="X", price=Decimal("1"), cost=Decimal("1"))
        assert _422(exigir_campos_de_cajero, datos) == "Campos requeridos para CAJERO/GERENTE: name"

    def test_talla_larga_dice_el_campo(self):
        assert _422(atributos_principal, "Rojo", "x" * 31).startswith("talla:")
        assert atributos_principal(None, None) == (None, None)
        assert atributos_principal(" Rojo ", " M ") == ("Rojo", "M")


class TestReexportDesdeRouter:
    def test_shared_sigue_exponiendo_los_alias_historicos(self):
        from app.modules.products.router import _shared
        from app.modules.products.services import comun
        assert _shared._PRODUCT_ADVANCED_ROLES is comun.PRODUCT_ADVANCED_ROLES
        assert _shared._MANAGER_ROLES is comun.MANAGER_ROLES
        assert _shared.variante_principal is comun.variante_principal
        assert _shared._safe_decimal("1.5") == Decimal("1.5")
        assert _shared._safe_str(None) == "" and _shared._is_na("nan") is True
