"""Unicidad de SKU y código interno: una sola regla para todas las altas.

Decisión del mega plan 2026-10 (§6.3): el SKU se compara sin mayúsculas y
cuenta también los productos archivados, para que restaurar nunca choque.
"""
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from conftest import _make_product
from app.models.organization import Organization
from app.modules.products.services.codigos import (
    asignar_barcode_interno, sku_de_copia, sku_en_uso, validar_barcode_libre,
    validar_sku_unico,
)
from app.services.barcodes import es_codigo_interno


def _archivar(db, producto, variante):
    ahora = datetime.now(timezone.utc)
    producto.deleted_at = ahora
    producto.is_active = False
    variante.deleted_at = ahora
    db.flush()


class TestValidarSkuUnico:
    def test_distinto_solo_en_mayusculas_o_espacios_es_409(self, db, org, branch_a):
        _make_product(db, org, "Playera", "PLY-1", 100, [(branch_a.id, True)])
        for repetido in ("ply-1", " PLY-1 ", "Ply-1"):
            with pytest.raises(HTTPException) as exc:
                validar_sku_unico(db, org.id, repetido)
            assert exc.value.status_code == 409
            assert exc.value.detail == f"El SKU '{repetido.strip()}' ya existe en esta organización."

    def test_sku_de_producto_archivado_tambien_es_409_y_lo_dice(self, db, org, branch_a):
        p, v = _make_product(db, org, "Vieja", "ARCH-1", 100, [(branch_a.id, True)])
        _archivar(db, p, v)
        with pytest.raises(HTTPException) as exc:
            validar_sku_unico(db, org.id, "arch-1")
        assert exc.value.status_code == 409
        assert "archivado" in exc.value.detail
        assert sku_en_uso(db, org.id, "ARCH-1") is True

    def test_el_mismo_sku_en_otra_org_no_estorba(self, db, org):
        otra = Organization(name="Otra", status="ACTIVE")
        db.add(otra); db.flush()
        _make_product(db, otra, "Ajena", "OTRA-1", 10)
        assert validar_sku_unico(db, org.id, "OTRA-1") == "OTRA-1"
        assert sku_en_uso(db, org.id, "OTRA-1") is False

    def test_excepto_id_permite_conservar_el_propio(self, db, org, branch_a):
        _, v = _make_product(db, org, "Playera", "PLY-2", 100, [(branch_a.id, True)])
        assert validar_sku_unico(db, org.id, "ply-2", excepto_id=v.id) == "ply-2"

    def test_vacio_es_422_y_devuelve_recortado(self, db, org):
        with pytest.raises(HTTPException) as exc:
            validar_sku_unico(db, org.id, "   ")
        assert exc.value.status_code == 422
        assert validar_sku_unico(db, org.id, "  NUEVO-1 ") == "NUEVO-1"


class TestSkuDeCopia:
    def test_salta_sufijos_ocupados_incluso_archivados(self, db, org, branch_a):
        _make_product(db, org, "Base", "SKU-A", 100, [(branch_a.id, True)])
        p1, v1 = _make_product(db, org, "Copia vieja", "SKU-A-COPY-1", 100, [(branch_a.id, True)])
        _archivar(db, p1, v1)
        assert sku_de_copia(db, org.id, "SKU-A") == "SKU-A-COPY-2"

    def test_sin_base_usa_SKU(self, db, org):
        assert sku_de_copia(db, org.id, "") == "SKU-COPY-1"


class TestBarcode:
    def test_asigna_interno_solo_si_esta_vacio(self, db, org, branch_a):
        _, con = _make_product(db, org, "Con", "BC-1", 10, [(branch_a.id, True)])
        con.barcode = "7500000000011"
        _, sin = _make_product(db, org, "Sin", "BC-2", 10, [(branch_a.id, True)])
        db.flush()
        assert asignar_barcode_interno(db, org.id, con) == "7500000000011"
        nuevo = asignar_barcode_interno(db, org.id, sin)
        assert es_codigo_interno(org.id, nuevo)
        assert sin.barcode == nuevo

    def test_barcode_libre_recorta_y_409_si_lo_tiene_otra(self, db, org, branch_a):
        _, otra = _make_product(db, org, "Otra", "BC-3", 10, [(branch_a.id, True)])
        otra.barcode = "7500000000022"
        db.flush()
        assert validar_barcode_libre(db, org.id, "  ") is None
        assert validar_barcode_libre(db, org.id, " 7500000000033 ") == "7500000000033"
        assert validar_barcode_libre(db, org.id, "7500000000022", excepto_id=otra.id) == "7500000000022"
        with pytest.raises(HTTPException) as exc:
            validar_barcode_libre(db, org.id, "7500000000022")
        assert exc.value.status_code == 409
        assert exc.value.detail == "El código de barras '7500000000022' ya lo tiene otra variante."
