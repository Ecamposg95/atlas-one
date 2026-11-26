"""Filtros avanzados de la lista de Productos (`GET /api/products/`).

Género, talla, color, solo con existencia y fecha de alta se filtran en el
servidor (la lista es paginada); las opciones de talla/color salen de
`GET /api/products/facets`. Las cifras (`/stats/catalog-kpis`) y el Excel
(`/export/excel`) aceptan los mismos parámetros.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.inventory import StockOnHand
from app.models.organization import Branch, BranchType, Organization
from app.models.products import Product, ProductBranchStatus, ProductVariant
from app.models.users import Role
from tests.conftest import _auth_header, _make_user

VIEJO = datetime(2025, 1, 1, tzinfo=timezone.utc)
RECIENTE = datetime(2026, 11, 20, tzinfo=timezone.utc)


def _producto(db, org, nombre, genero, variantes, creado=VIEJO):
    """variantes: lista de (sku, talla, color, {branch_id: qty}, creado_variante|None)."""
    p = Product(name=nombre, organization_id=org.id, is_active=True, gender=genero, created_at=creado)
    db.add(p)
    db.flush()
    for sku, talla, color, stock, creado_v in variantes:
        v = ProductVariant(
            product_id=p.id, sku=sku, size=talla, color=color, price=Decimal("100"),
            cost=Decimal("50"), organization_id=org.id, created_at=creado_v or creado,
        )
        db.add(v)
        db.flush()
        for branch_id, qty in stock.items():
            db.add(ProductBranchStatus(variant_id=v.id, branch_id=branch_id, organization_id=org.id,
                                       is_active_pos=True, is_visible=True))
            db.add(StockOnHand(variant_id=v.id, branch_id=branch_id, organization_id=org.id,
                               qty_on_hand=Decimal(str(qty)), is_active=True))
    db.flush()
    return p


@pytest.fixture()
def catalogo(db, org, branch_a, branch_b):
    """
    - Blusa (MUJER):    M/Negro con 5 en A; G/Blanco con 0 en A.
    - Camisa (HOMBRE):  M/Blanco con 0 en A; talla L/Azul agregada RECIENTE con 0 en B.
    - Cinturón (UNISEX, alta RECIENTE): sin talla, " café " con 3 en B.
    - Otra organización: Blusa MUJER XXL/Rojo con 9 (no debe asomarse nunca).
    """
    a, b = branch_a.id, branch_b.id
    blusa = _producto(db, org, "Blusa", "MUJER", [
        ("BL-M-NEG", "M", "Negro", {a: 5}, None),
        ("BL-G-BLA", "G", "Blanco", {a: 0}, None),
    ])
    camisa = _producto(db, org, "Camisa", "HOMBRE", [
        ("CA-M-BLA", "M", "Blanco", {a: 0}, None),
        ("CA-L-AZU", "L", "Azul", {b: 0}, RECIENTE),
    ])
    cinturon = _producto(db, org, "Cinturón", "UNISEX", [
        ("CI-CAFE", None, " café ", {b: 3}, None),
    ], creado=RECIENTE)

    otra = Organization(name="Otra Org", status="ACTIVE")
    db.add(otra)
    db.flush()
    sucursal_otra = Branch(name="Otra", branch_type=BranchType.STORE, can_sell=True,
                           is_active=True, organization_id=otra.id)
    db.add(sucursal_otra)
    db.flush()
    _producto(db, otra, "Blusa ajena", "MUJER", [
        ("OT-XXL-ROJ", "XXL", "Rojo", {sucursal_otra.id: 9}, None),
        ("OT-M-NEG", "M", "Negro", {sucursal_otra.id: 9}, None),
    ], creado=RECIENTE)
    return {"blusa": blusa, "camisa": camisa, "cinturon": cinturon}


@pytest.fixture()
def auth_oficina(db, org):
    """Admin sin sucursal: la existencia se mide en toda la organización."""
    return _auth_header(_make_user(db, org, None, "admin_oficina", Role.ADMINISTRADOR))


def _nombres(client, headers, **params):
    r = client.get("/api/products/", params={"limit": 100, **params}, headers=headers)
    assert r.status_code == 200, r.text
    datos = r.json()
    nombres = sorted(p["name"] for p in datos["items"])
    assert datos["total"] == len(nombres)
    return nombres


def test_sin_filtros_avanzados_la_lista_no_cambia(client, auth_oficina, catalogo):
    assert _nombres(client, auth_oficina) == ["Blusa", "Camisa", "Cinturón"]


@pytest.mark.parametrize("genero,esperado", [
    ("MUJER", ["Blusa"]),
    ("hombre", ["Camisa"]),
    ("Unisex", ["Cinturón"]),
    ("niño", []),
])
def test_genero(client, auth_oficina, catalogo, genero, esperado):
    assert _nombres(client, auth_oficina, gender=genero) == esperado


def test_genero_invalido_es_422(client, auth_oficina, catalogo):
    r = client.get("/api/products/", params={"gender": "PERRO"}, headers=auth_oficina)
    assert r.status_code == 422
    assert "gender" in r.json()["detail"]


def test_talla(client, auth_oficina, catalogo):
    assert _nombres(client, auth_oficina, size="M") == ["Blusa", "Camisa"]
    assert _nombres(client, auth_oficina, size=" g ") == ["Blusa"]
    assert _nombres(client, auth_oficina, size="L") == ["Camisa"]
    # XXL solo existe en la otra organización.
    assert _nombres(client, auth_oficina, size="XXL") == []


def test_color_sin_distinguir_mayusculas_ni_espacios(client, auth_oficina, catalogo):
    assert _nombres(client, auth_oficina, color="blanco") == ["Blusa", "Camisa"]
    assert _nombres(client, auth_oficina, color=" CAFÉ ") == ["Cinturón"]
    assert _nombres(client, auth_oficina, color="café") == ["Cinturón"]
    assert _nombres(client, auth_oficina, color="Rojo") == []


def test_talla_y_color_en_la_misma_variante(client, auth_oficina, catalogo):
    # Camisa tiene M (Blanco) y Azul (L): "M Azul" no es la misma variante.
    assert _nombres(client, auth_oficina, size="M", color="Azul") == []
    assert _nombres(client, auth_oficina, size="M", color="Negro") == ["Blusa"]
    assert _nombres(client, auth_oficina, size="L", color="azul") == ["Camisa"]


def test_solo_con_existencia_en_toda_la_org(client, auth_oficina, catalogo):
    # Sin sucursal: suma de la organización. Camisa tiene 0 en todas.
    assert _nombres(client, auth_oficina, only_with_stock=True) == ["Blusa", "Cinturón"]


def test_solo_con_existencia_respeta_la_sucursal_de_la_lista(client, db, org, branch_a, catalogo):
    # Admin en la Sucursal A: la lista pinta la existencia de A, el filtro también.
    admin_a = _auth_header(_make_user(db, org, branch_a, "admin_sucursal_a", Role.ADMINISTRADOR))
    assert _nombres(client, admin_a, only_with_stock=True) == ["Blusa"]


def test_solo_con_existencia_con_drill_down_de_sucursal(client, auth_oficina, branch_b, catalogo):
    assert _nombres(client, auth_oficina, only_with_stock=True, branch_id=branch_b.id) == ["Cinturón"]


def test_gerente_ve_solo_lo_de_su_sucursal(client, auth_gerente_a, catalogo):
    assert _nombres(client, auth_gerente_a) == ["Blusa", "Camisa"]
    assert _nombres(client, auth_gerente_a, only_with_stock=True) == ["Blusa"]
    assert _nombres(client, auth_gerente_a, color="café") == []


def test_dados_de_alta_desde(client, auth_oficina, catalogo):
    # Cinturón es alta reciente; Camisa es vieja pero su talla L es nueva.
    assert _nombres(client, auth_oficina, created_after="2026-11-01T00:00:00Z") == ["Camisa", "Cinturón"]
    # Con zona: medianoche de México del 20 = 06:00 UTC, después de las 00:00 UTC de las altas.
    assert _nombres(client, auth_oficina, created_after="2026-11-20T00:00:00-06:00") == []
    assert _nombres(client, auth_oficina, created_after="2024-01-01T00:00:00") == ["Blusa", "Camisa", "Cinturón"]


def test_combinacion_de_filtros(client, auth_oficina, catalogo):
    assert _nombres(client, auth_oficina, gender="MUJER", size="M", only_with_stock=True) == ["Blusa"]
    assert _nombres(client, auth_oficina, gender="HOMBRE", only_with_stock=True) == []
    assert _nombres(client, auth_oficina, color="blanco", created_after="2026-11-01T00:00:00Z") == ["Camisa"]
    assert _nombres(client, auth_oficina, search="blu", size="G") == ["Blusa"]


def test_paginacion_cuenta_lo_filtrado(client, auth_oficina, catalogo):
    r = client.get("/api/products/", params={"size": "M", "limit": 1}, headers=auth_oficina)
    assert r.status_code == 200
    assert r.json()["total"] == 2
    assert len(r.json()["items"]) == 1


def test_facetas_del_catalogo_de_la_org(client, auth_oficina, catalogo):
    r = client.get("/api/products/facets", headers=auth_oficina)
    assert r.status_code == 200, r.text
    datos = r.json()
    # Orden de escala: M, G, L; la otra org (XXL, Rojo) no aparece.
    assert datos["sizes"] == ["M", "G", "L"]
    assert datos["colors"] == ["Azul", "Blanco", "café", "Negro"]


def test_facetas_de_un_rol_de_sucursal(client, auth_gerente_a, catalogo):
    datos = client.get("/api/products/facets", headers=auth_gerente_a).json()
    assert datos["sizes"] == ["M", "G", "L"]  # Camisa es visible en A: trae todas sus tallas
    assert "café" not in datos["colors"]      # el cinturón solo está en B


def test_facetas_sin_variantes_borradas(client, db, auth_oficina, catalogo):
    v = db.query(ProductVariant).filter(ProductVariant.sku == "CA-L-AZU").one()
    v.deleted_at = datetime.now(timezone.utc)
    db.flush()
    datos = client.get("/api/products/facets", headers=auth_oficina).json()
    assert "L" not in datos["sizes"]
    assert "Azul" not in datos["colors"]
    assert _nombres(client, auth_oficina, size="L") == []


def test_kpis_con_los_mismos_filtros(client, auth_oficina, catalogo):
    total = client.get("/api/products/stats/catalog-kpis", headers=auth_oficina).json()
    assert total["total_skus"] == 5
    filtrado = client.get("/api/products/stats/catalog-kpis",
                          params={"gender": "MUJER", "only_with_stock": True}, headers=auth_oficina)
    assert filtrado.status_code == 200, filtrado.text
    # Solo Blusa (2 tallas).
    assert filtrado.json()["total_skus"] == 2
    r = client.get("/api/products/stats/catalog-kpis", params={"gender": "X"}, headers=auth_oficina)
    assert r.status_code == 422


def test_export_excel_con_filtros(client, auth_oficina, catalogo):
    import io
    from openpyxl import load_workbook

    def skus(**params):
        r = client.get("/api/products/export/excel", params=params, headers=auth_oficina)
        assert r.status_code == 200, r.text
        hoja = load_workbook(io.BytesIO(r.content)).active
        cabecera = [c.value for c in hoja[1]]
        col = next(i for i, v in enumerate(cabecera) if v and "SKU" in str(v).upper())
        return sorted(str(f[col]) for f in hoja.iter_rows(min_row=2, values_only=True) if f[col])

    assert "CI-CAFE" in skus()
    filtrados = skus(color="café")
    assert filtrados == ["CI-CAFE"]
