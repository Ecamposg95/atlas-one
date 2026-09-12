"""Búsqueda EXACTA por código para el scanner de tienda.

`GET /api/products/pos/search` busca con `%parcial%`, que es lo correcto cuando
la cajera teclea. Pero cuando el texto viene de un ESCANEO el código es
completo y exacto, y el parcial produce falsos positivos: escanear
"750123456789" también trae cualquier producto cuyo código lo contenga
(p. ej. "7501234567890"). En el pasillo eso significa editarle el precio al
producto equivocado.

`?exact=true` compara por igualdad contra barcode de variante, barcode de
empaque y SKU. Sin el parámetro el endpoint responde idéntico a hoy.
"""
from decimal import Decimal

import pytest

from app.models.products import PackagingUnit
from conftest import _make_product


@pytest.fixture()
def scanner_setup(db, org, branch_a, branch_b):
    """Dos productos cuyos códigos son uno prefijo del otro — el caso que
    rompe la búsqueda parcial — más uno en otra sucursal para el scope."""
    corto, v_corto = _make_product(
        db, org, "Pluma Corta", "SKU-CORTO", 10.0, branches_active=[(branch_a.id, True)]
    )
    v_corto.barcode = "750123456789"

    largo, v_largo = _make_product(
        db, org, "Pluma Larga", "SKU-LARGO", 20.0, branches_active=[(branch_a.id, True)]
    )
    # Contiene al código corto como prefijo: con ILIKE '%corto%' matchea.
    v_largo.barcode = "7501234567890"

    otra, v_otra = _make_product(
        db, org, "Pluma De Otra Sucursal", "SKU-OTRA", 30.0,
        branches_active=[(branch_b.id, True)],
    )
    v_otra.barcode = "111111111111"

    # La CAJA trae su propio código, distinto al de la pieza. Escanear la caja
    # tiene que encontrar el producto aunque ni el SKU ni el barcode de la
    # variante empaten.
    con_caja, v_caja = _make_product(
        db, org, "Pluma Con Caja", "SKU-CAJA", 15.0,
        branches_active=[(branch_a.id, True)],
    )
    v_caja.barcode = "222222222222"
    db.add(PackagingUnit(
        variant_id=v_caja.id, organization_id=org.id, name="Caja",
        barcode="999888777666", units_per_package=Decimal("24"),
        package_price=Decimal("300"),
    ))

    db.flush()
    return {"corto": corto, "largo": largo, "otra": otra, "con_caja": con_caja}


class TestBusquedaExacta:
    def test_escanear_no_trae_el_codigo_que_lo_contiene(
        self, client, auth_admin, scanner_setup
    ):
        resp = client.get(
            "/api/products/pos/search?q=750123456789&exact=true", headers=auth_admin
        )
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert names == ["Pluma Corta"], (
            "exact debe devolver SOLO el código escaneado; "
            f"'Pluma Larga' lo contiene como prefijo. Recibido: {names}"
        )

    def test_sin_exact_el_comportamiento_no_cambia(
        self, client, auth_admin, scanner_setup
    ):
        # No-regresión: el POS teclea parcial y debe seguir trayendo ambos.
        resp = client.get("/api/products/pos/search?q=750123456789", headers=auth_admin)
        assert resp.status_code == 200
        names = sorted(p["name"] for p in resp.json())
        assert names == ["Pluma Corta", "Pluma Larga"]

    def test_exact_tambien_encuentra_por_sku(self, client, auth_admin, scanner_setup):
        # Hay 2,259 productos cuyo identificador es un código interno, no un
        # código de barras; el scanner debe hallarlos si se teclea el SKU.
        resp = client.get(
            "/api/products/pos/search?q=SKU-CORTO&exact=true", headers=auth_admin
        )
        assert resp.status_code == 200
        assert [p["name"] for p in resp.json()] == ["Pluma Corta"]

    def test_exact_con_sku_parcial_no_devuelve_nada(
        self, client, auth_admin, scanner_setup
    ):
        resp = client.get(
            "/api/products/pos/search?q=SKU-COR&exact=true", headers=auth_admin
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_escanear_el_codigo_de_la_caja_encuentra_el_producto(
        self, client, auth_admin, scanner_setup
    ):
        # Ni el SKU ni el barcode de la variante empatan: solo el de la caja.
        resp = client.get(
            "/api/products/pos/search?q=999888777666&exact=true", headers=auth_admin
        )
        assert resp.status_code == 200
        assert [p["name"] for p in resp.json()] == ["Pluma Con Caja"]

    def test_codigo_inexistente_devuelve_vacio(self, client, auth_admin, scanner_setup):
        resp = client.get(
            "/api/products/pos/search?q=000000000000&exact=true", headers=auth_admin
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_exact_respeta_el_scope_de_sucursal(
        self, client, auth_cajero_a, scanner_setup
    ):
        # El scanner NO puede volverse una puerta lateral para ver el catálogo
        # de otra sucursal: exact pasa por el mismo helper de visibilidad.
        resp = client.get(
            "/api/products/pos/search?q=111111111111&exact=true", headers=auth_cajero_a
        )
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.fixture()
def stock_setup(db, org, branch_a, branch_b):
    """Mismo producto con existencias DISTINTAS en dos sucursales."""
    from app.models.inventory import StockOnHand
    prod, v = _make_product(
        db, org, "Pluma Con Stock", "SKU-STOCK", 10.0,
        branches_active=[(branch_a.id, True), (branch_b.id, True)],
    )
    v.barcode = "555555555555"
    for br, qty in ((branch_a.id, Decimal("40")), (branch_b.id, Decimal("7"))):
        soh = db.query(StockOnHand).filter_by(variant_id=v.id, branch_id=br).first()
        soh.qty_on_hand = qty
    db.flush()
    return prod


class TestStockPorSucursal:
    """El scanner necesita la existencia de la tienda donde está parado el admin.

    Un ADMINISTRADOR de HQ tiene `branch_id = NULL`, así que sin decir de qué
    sucursal se trata el backend devuelve 0 — y con base 0 un conteo SIEMPRE se
    convierte en una entrada, nunca en una salida. El scanner no podría detectar
    un faltante de anaquel, solo inflar el inventario.
    """

    def test_admin_recibe_el_stock_de_la_sucursal_que_pide(
        self, client, auth_admin, stock_setup, branch_b
    ):
        resp = client.get(
            f"/api/products/pos/search?q=555555555555&exact=true&branch_id={branch_b.id}",
            headers=auth_admin,
        )
        assert resp.status_code == 200
        # OJO: el backend serializa Decimal como CADENA ("7.00"), no como número.
        # El frontend tiene que convertirlo o Number.isFinite lo rechaza y cae en 0.
        assert float(resp.json()[0]["stock_total"]) == 7, "debe traer la existencia de branch_b, no 0 ni la de otra"

    def test_la_otra_sucursal_da_su_propio_numero(
        self, client, auth_admin, stock_setup, branch_a
    ):
        resp = client.get(
            f"/api/products/pos/search?q=555555555555&exact=true&branch_id={branch_a.id}",
            headers=auth_admin,
        )
        assert resp.status_code == 200
        assert float(resp.json()[0]["stock_total"]) == 40

    def test_el_cajero_no_puede_espiar_otra_sucursal_con_branch_id(
        self, client, auth_cajero_a, stock_setup, branch_b
    ):
        # Defense in depth: el parámetro es un hint, no una autorización.
        resp = client.get(
            f"/api/products/pos/search?q=555555555555&exact=true&branch_id={branch_b.id}",
            headers=auth_cajero_a,
        )
        assert resp.status_code == 200
        items = resp.json()
        assert items and float(items[0]["stock_total"]) == 40, "el cajero de A ve SU sucursal, ignorando el hint"


class TestSkuTecleado:
    """El SKU se teclea a mano, y la mitad del catálogo lo tiene en minúsculas
    (`m-1151`). Una comparación sensible a mayúsculas obliga a adivinar cómo se
    capturó. El código de barras SÍ se compara exacto: son dígitos."""

    def test_encuentra_el_sku_sin_importar_mayusculas(self, client, auth_admin, scanner_setup):
        resp = client.get(
            "/api/products/pos/search?q=sku-corto&exact=true", headers=auth_admin
        )
        assert resp.status_code == 200
        assert [p["name"] for p in resp.json()] == ["Pluma Corta"]

    def test_y_al_reves_tambien(self, client, auth_admin, scanner_setup):
        resp = client.get(
            "/api/products/pos/search?q=SKU-CORTO&exact=true", headers=auth_admin
        )
        assert resp.status_code == 200
        assert [p["name"] for p in resp.json()] == ["Pluma Corta"]

    def test_sigue_sin_aceptar_parciales(self, client, auth_admin, scanner_setup):
        # Insensible a mayúsculas no significa difuso: exacto sigue siendo exacto.
        resp = client.get(
            "/api/products/pos/search?q=sku-cor&exact=true", headers=auth_admin
        )
        assert resp.status_code == 200
        assert resp.json() == []
