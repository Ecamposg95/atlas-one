"""Códigos de barras EAN-13 internos por variante (talla/color).

Cada variante viva debe poder escanearse: el prefijo GS1 "2" es de uso
interno, así que `2 + org(3) + secuencia(8) + verificador` es un EAN-13 legal
que ningún fabricante emite. Se asigna al crear (alta, tallas, importación) y
bajo demanda para el catálogo que ya existe, nunca se sobrescribe uno de
fábrica, y se exporta como CSV de etiquetas.
"""
from decimal import Decimal

import pytest

from app.models.modules import Module, OrganizationModule
from app.models.organization import Organization
from app.models.products import ProductVariant
from app.services.barcodes import (
    asignar_codigos_faltantes,
    barcode_en_uso,
    ean13_check_digit,
    es_codigo_interno,
    siguiente_codigo_interno,
)
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


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


@pytest.fixture()
def boutique(db, org):
    _habilitar(db, org, "variants")
    return org


# ── 1. Formato y secuencia ───────────────────────────────────────────────────
class TestFormato:
    def test_digito_verificador_ean13(self):
        # Pesos 1-3 desde la izquierda: 2+0+1+21+0+…+3 = 27 → (10-7)%10 = 3.
        assert ean13_check_digit("201700000001") == "3"
        # ISBN-13 clásico 978-0-306-40615-7: verificador conocido.
        assert ean13_check_digit("978030640615") == "7"

    def test_siguiente_codigo_es_un_ean13_de_la_org(self, db, org, branch_a):
        _, v = _make_product(db, org, "Playera", "PLY", 100, [(branch_a.id, True)])
        c1 = siguiente_codigo_interno(db, org.id)
        assert len(c1) == 13 and c1.isdigit()
        assert c1.startswith(f"2{org.id:03d}")
        assert ean13_check_digit(c1[:12]) == c1[12]
        assert es_codigo_interno(org.id, c1)
        assert not es_codigo_interno(org.id + 1, c1)
        assert not es_codigo_interno(org.id, "7501234567890")

        # Dos llamadas seguidas (con el primero ya guardado) son consecutivas.
        v.barcode = c1
        db.flush()
        c2 = siguiente_codigo_interno(db, org.id)
        assert int(c2[4:12]) == int(c1[4:12]) + 1

    def test_no_reusa_un_ean_de_fabrica_que_coincida(self, db, org, branch_a):
        """Si un código de fábrica ya ocupa el candidato, la secuencia avanza."""
        _, v = _make_product(db, org, "Playera", "PLY", 100, [(branch_a.id, True)])
        candidato = siguiente_codigo_interno(db, org.id)
        v.barcode = candidato
        db.flush()
        assert barcode_en_uso(db, org.id, candidato)
        assert siguiente_codigo_interno(db, org.id) != candidato


# ── 2 y 4. Alta de producto ──────────────────────────────────────────────────
class TestAltaDeProducto:
    def test_alta_sin_codigo_genera_uno_por_variante(self, client, db, boutique, branch_a, auth_admin):
        r = client.post("/api/products/", json={
            "name": "Blusa", "sku": "BLS", "price": "300", "cost": "150",
            "color": "Rojo", "size": "S",
            "target_branch_ids": [branch_a.id],
            "extra_variants": [{"color": "Rojo", "size": "M"}, {"color": "Rojo", "size": "L"}],
        }, headers=_h(auth_admin, boutique))
        assert r.status_code in (200, 201), r.text
        codigos = [v["barcode"] for v in r.json()["variants"]]
        assert len(codigos) == 3
        assert all(c and len(c) == 13 and c.isdigit() for c in codigos), codigos
        assert len(set(codigos)) == 3, "cada talla lleva el suyo"
        assert all(es_codigo_interno(boutique.id, c) for c in codigos)

    def test_alta_con_codigo_explicito_lo_respeta(self, client, db, org, branch_a, auth_admin):
        r = client.post("/api/products/", json={
            "name": "Refresco", "sku": "REF", "price": "20", "cost": "10",
            "barcode": "7501234567890",
            "target_branch_ids": [branch_a.id],
        }, headers=_h(auth_admin, org))
        assert r.status_code in (200, 201), r.text
        assert r.json()["variants"][0]["barcode"] == "7501234567890"

    def test_alta_con_codigo_repetido_en_la_org_es_409(self, client, db, org, branch_a, auth_admin):
        _, v = _make_product(db, org, "Gorra", "GOR", 50, [(branch_a.id, True)])
        v.barcode = "7500000000022"
        db.commit()
        r = client.post("/api/products/", json={
            "name": "Otra Gorra", "sku": "GOR-2", "price": "50", "cost": "25",
            "barcode": "7500000000022",
            "target_branch_ids": [branch_a.id],
        }, headers=_h(auth_admin, org))
        assert r.status_code == 409, r.text

    def test_el_mismo_codigo_en_otra_org_se_permite(self, client, db, org, branch_a, auth_admin):
        otra = Organization(name="Otra Tienda", status="ACTIVE")
        db.add(otra); db.flush()
        _, ajena = _make_product(db, otra, "Ajena", "AJ-1", 10)
        ajena.barcode = "7500000000033"
        db.commit()
        r = client.post("/api/products/", json={
            "name": "Propia", "sku": "PRO-1", "price": "50", "cost": "25",
            "barcode": "7500000000033",
            "target_branch_ids": [branch_a.id],
        }, headers=_h(auth_admin, org))
        assert r.status_code in (200, 201), r.text
        assert r.json()["variants"][0]["barcode"] == "7500000000033"


# ── 3. Alta de tallas ────────────────────────────────────────────────────────
class TestAltaDeTallas:
    def test_cada_talla_nueva_recibe_su_codigo(self, client, db, boutique, branch_a, auth_admin):
        p, v = _make_product(db, boutique, "Playera", "PLY", 100, [(branch_a.id, True)])
        db.commit()
        r = client.post(f"/api/products/{p.id}/variants", json={"variants": [
            {"color": "Rojo", "size": "M"},
            {"color": "Rojo", "size": "L"},
            {"color": "Azul", "size": "M", "barcode": "7500000000044"},
        ]}, headers=_h(auth_admin, boutique))
        assert r.status_code == 201, r.text
        por_sku = {x["sku"]: x for x in r.json()["variants"]}
        generados = [por_sku["PLY-ROJO-M"]["barcode"], por_sku["PLY-ROJO-L"]["barcode"]]
        assert all(c and len(c) == 13 for c in generados)
        assert generados[0] != generados[1]
        assert por_sku["PLY-AZUL-M"]["barcode"] == "7500000000044"


# ── 5. Asignación bajo demanda ───────────────────────────────────────────────
@pytest.fixture()
def catalogo_sin_codigos(db, org, branch_a):
    """3 variantes sin código y 1 con código de fábrica."""
    p1, v1 = _make_product(db, org, "Playera", "PLY", 100, [(branch_a.id, True)])
    p2, v2 = _make_product(db, org, "Gorra", "GOR", 50, [(branch_a.id, True)])
    p3, v3 = _make_product(db, org, "Falda", "FLD", 300, [(branch_a.id, True)])
    p4, v4 = _make_product(db, org, "Refresco", "REF", 20, [(branch_a.id, True)])
    v4.barcode = "7501234567890"
    db.commit()
    return {"sin": [v1, v2, v3], "con": v4, "productos": [p1, p2, p3, p4]}


class TestAsignarFaltantes:
    def test_asigna_solo_los_vacios_y_es_idempotente(self, client, db, org, catalogo_sin_codigos, auth_admin):
        assert client.get("/api/products/barcodes/missing-count",
                          headers=_h(auth_admin, org)).json() == {"missing": 3}

        r = client.post("/api/products/barcodes/assign-missing", json={}, headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        assert r.json() == {"assigned": 3}

        for v in catalogo_sin_codigos["sin"]:
            db.refresh(v)
            assert v.barcode and len(v.barcode) == 13 and es_codigo_interno(org.id, v.barcode)
        db.refresh(catalogo_sin_codigos["con"])
        assert catalogo_sin_codigos["con"].barcode == "7501234567890", "no se sobrescribe el de fábrica"

        codigos = {v.barcode for v in catalogo_sin_codigos["sin"]}
        assert len(codigos) == 3

        r2 = client.post("/api/products/barcodes/assign-missing", json={}, headers=_h(auth_admin, org))
        assert r2.json() == {"assigned": 0}
        assert client.get("/api/products/barcodes/missing-count",
                          headers=_h(auth_admin, org)).json() == {"missing": 0}

    def test_filtra_por_producto(self, client, db, org, catalogo_sin_codigos, auth_admin):
        p1 = catalogo_sin_codigos["productos"][0]
        r = client.post("/api/products/barcodes/assign-missing",
                        json={"product_id": str(p1.id)}, headers=_h(auth_admin, org))
        assert r.json() == {"assigned": 1}
        assert client.get("/api/products/barcodes/missing-count",
                          headers=_h(auth_admin, org)).json() == {"missing": 2}

    def test_cajero_no_puede_asignar(self, client, db, org, catalogo_sin_codigos, auth_cajero_a):
        r = client.post("/api/products/barcodes/assign-missing", json={}, headers=_h(auth_cajero_a, org))
        assert r.status_code == 403, r.text

    def test_asignacion_directa_por_servicio(self, db, org, catalogo_sin_codigos):
        assert asignar_codigos_faltantes(db, org.id) == 3
        assert asignar_codigos_faltantes(db, org.id) == 0


# ── 6. El POS lo encuentra ───────────────────────────────────────────────────
class TestEscaneo:
    def test_el_codigo_generado_se_escanea_en_el_pos(self, client, db, org, branch_a,
                                                     catalogo_sin_codigos, auth_cajero_a, auth_admin):
        client.post("/api/products/barcodes/assign-missing", json={}, headers=_h(auth_admin, org))
        v = catalogo_sin_codigos["sin"][0]
        db.refresh(v)
        r = client.get(f"/api/products/pos/search?q={v.barcode}&exact=true",
                       headers=_h(auth_cajero_a, org))
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert [p["name"] for p in cuerpo] == ["Playera"]
        assert cuerpo[0]["matched_variant_id"] == v.id


# ── 7. CSV de etiquetas ──────────────────────────────────────────────────────
ENCABEZADO = "SKU,Codigo de barras,Producto,Marca,Talla,Color,Precio,Existencia"


class TestEtiquetasCsv:
    def test_csv_con_una_fila_por_variante(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Playera", "PLY", 100, [(branch_a.id, True)])
        v.barcode, v.color, v.size = "7501234567890", "Rojo", "M"
        _make_product(db, org, "Gorra", "GOR", 50, [(branch_a.id, True)])
        db.commit()

        r = client.get("/api/products/export/labels.csv", headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers["content-type"]
        assert "etiquetas_" in r.headers.get("content-disposition", "")
        texto = r.content.decode("utf-8-sig")
        assert r.content.startswith("﻿".encode("utf-8")), "Excel necesita el BOM"
        lineas = texto.strip().splitlines()
        assert lineas[0] == ENCABEZADO
        assert len(lineas) == 3, lineas
        fila = next(l for l in lineas[1:] if l.startswith("PLY,"))
        assert fila == "PLY,7501234567890,Playera,,M,Rojo,100.00,100"

    def test_filtra_por_producto(self, client, db, org, branch_a, auth_admin):
        p, v = _make_product(db, org, "Playera", "PLY", 100, [(branch_a.id, True)])
        _make_product(db, org, "Gorra", "GOR", 50, [(branch_a.id, True)])
        db.commit()
        r = client.get(f"/api/products/export/labels.csv?product_id={p.id}",
                       headers=_h(auth_admin, org))
        assert r.status_code == 200, r.text
        lineas = r.content.decode("utf-8-sig").strip().splitlines()
        assert len(lineas) == 2 and lineas[1].startswith("PLY,")

    def test_only_with_stock_descarta_los_vacios(self, client, db, org, branch_a, auth_admin):
        from app.models.inventory import StockOnHand
        p, v = _make_product(db, org, "Playera", "PLY", 100, [(branch_a.id, True)])
        _, sin_stock = _make_product(db, org, "Gorra", "GOR", 50, [(branch_a.id, True)])
        db.query(StockOnHand).filter(StockOnHand.variant_id == sin_stock.id).update(
            {StockOnHand.qty_on_hand: Decimal("0")}, synchronize_session=False)
        db.commit()
        r = client.get("/api/products/export/labels.csv?only_with_stock=true",
                       headers=_h(auth_admin, org))
        lineas = r.content.decode("utf-8-sig").strip().splitlines()
        assert len(lineas) == 2 and lineas[1].startswith("PLY,")

    def test_el_cajero_solo_ve_su_sucursal(self, client, db, org, branch_a, branch_b, auth_cajero_a):
        _make_product(db, org, "Playera", "PLY", 100, [(branch_a.id, True)])
        _make_product(db, org, "De la B", "SKU-B", 200, [(branch_b.id, True)])
        db.commit()
        r = client.get("/api/products/export/labels.csv", headers=_h(auth_cajero_a, org))
        assert r.status_code == 200, r.text
        lineas = r.content.decode("utf-8-sig").strip().splitlines()
        assert len(lineas) == 2 and lineas[1].startswith("PLY,")
