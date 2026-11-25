"""El cobro guarda el desglose fiscal de TODA venta, pida factura o no.

Complementa a `tests/test_iva_sale_integration.py` (que vigila el desglose del
ticket) y a `tests/test_desglose_fiscal.py` (la aritmética pura).
"""
from decimal import Decimal

from app.models.sales import SalesDocument, SalesLineItem
from tests.test_iva_sale_integration import _abrir_caja, _documento, _producto

D = Decimal


def _vender(client, org, auth, items, monto, *, requires_invoice=False, tip=None):
    cuerpo = {
        "doc_type": "ORDER",
        "items": items,
        "payments": [{"method": "CASH", "amount": str(monto)}],
        "requires_invoice": requires_invoice,
    }
    if tip is not None:
        cuerpo["tip_amount"] = str(tip)
    return client.post("/api/sales/", json=cuerpo, headers={**auth, "X-Organization-ID": str(org.id)})


def _suma_fiscal(doc: SalesDocument) -> Decimal:
    return sum((
        doc.iva_base_16, doc.iva_16, doc.iva_base_8, doc.iva_8,
        doc.iva_base_0, doc.iva_base_exenta, doc.iva_base_no_objeto,
    ), D("0"))


def _lineas(db, doc):
    return db.query(SalesLineItem).filter(SalesLineItem.document_id == doc.id).all()


def test_venta_sin_factura_guarda_su_iva(client, db, org, branch_a, cajero_a, auth_cajero_a):
    """Lo cobrado no cambia (100) y el ticket sigue sin IVA; el desglose
    fiscal sí lo trae: 100 con IVA incluido = 86.21 + 13.79."""
    _producto(db, org, branch_a, "FIS-SF", "100.00")
    _abrir_caja(db, org, branch_a, cajero_a)
    resp = _vender(client, org, auth_cajero_a, [{"sku": "FIS-SF", "quantity": 1}], "100.00")
    assert resp.status_code in (200, 201), resp.text

    doc = _documento(db, org)
    assert doc.total_amount == D("100.00")
    assert doc.tax_amount == D("0.00")          # el ticket, como siempre
    assert (doc.iva_base_16, doc.iva_16) == (D("86.21"), D("13.79"))
    assert _suma_fiscal(doc) == D("100.00")
    (linea,) = _lineas(db, doc)
    assert (linea.iva_base, linea.iva_importe) == (D("86.21"), D("13.79"))
    assert linea.iva_tasa == D("0.1600")
    assert linea.iva_tipo_factor == "Tasa"
    assert linea.iva_inferido is True           # el producto no tenía tasa capturada


def test_venta_con_factura_modo_neto_coincide_con_el_ticket(client, db, org, branch_a, cajero_a, auth_cajero_a):
    _producto(db, org, branch_a, "FIS-CF", "100.00")
    _abrir_caja(db, org, branch_a, cajero_a)
    resp = _vender(client, org, auth_cajero_a, [{"sku": "FIS-CF", "quantity": 1}], "116.00", requires_invoice=True)
    assert resp.status_code in (200, 201), resp.text
    doc = _documento(db, org)
    assert (doc.iva_base_16, doc.iva_16) == (doc.subtotal, doc.tax_amount) == (D("100.00"), D("16.00"))


def test_mezcla_de_tasas_claves_sat_y_propina(client, db, org, branch_a, cajero_a, auth_cajero_a):
    """Tasa explícita del producto, fotografía de las claves del SAT, y la
    propina fuera del desglose."""
    v16 = _producto(db, org, branch_a, "FIS-16", "58.00")
    v0 = _producto(db, org, branch_a, "FIS-0", "23.50", has_iva=False)
    vex = _producto(db, org, branch_a, "FIS-EX", "12.30", has_iva=False)
    v16.product.sat_clave_prod_serv = "50202306"
    v16.product.sat_clave_unidad = "H87"
    v16.product.sat_objeto_imp = "02"
    v16.product.iva_tratamiento = "16"
    v0.product.iva_tratamiento = "0"
    vex.product.iva_tratamiento = "EXENTO"
    db.commit()
    _abrir_caja(db, org, branch_a, cajero_a)

    items = [
        {"sku": "FIS-16", "quantity": 2},
        {"sku": "FIS-0", "quantity": 1},
        {"sku": "FIS-EX", "quantity": 1},
    ]
    resp = _vender(client, org, auth_cajero_a, items, "151.80")
    assert resp.status_code in (200, 201), resp.text
    doc = _documento(db, org)
    assert (doc.iva_base_16, doc.iva_16) == (D("100.00"), D("16.00"))
    assert doc.iva_base_0 == D("23.50")
    assert doc.iva_base_exenta == D("12.30")
    assert doc.iva_base_8 == D("0.00") and doc.iva_8 == D("0.00")
    assert _suma_fiscal(doc) == doc.total_amount - (doc.tip_amount or 0) == D("151.80")

    por_sku = {ln.variant_id: ln for ln in _lineas(db, doc)}
    l16 = por_sku[v16.id]
    assert (l16.sat_clave_prod_serv, l16.sat_clave_unidad, l16.sat_objeto_imp) == ("50202306", "H87", "02")
    assert l16.iva_inferido is False
    assert por_sku[vex.id].iva_tipo_factor == "Exento"
    assert por_sku[vex.id].iva_tasa is None

    # Cambiar el catálogo después no mueve la fotografía de la venta.
    v16.product.sat_clave_prod_serv = "01010101"
    db.commit()
    db.refresh(l16)
    assert l16.sat_clave_prod_serv == "50202306"


def test_descuento_y_centavos_cuadran(client, db, org, branch_a, cajero_a, auth_cajero_a):
    """Tres renglones con descuento: la suma de los renglones es exactamente
    lo cobrado y cada renglón cumple base + IVA == su importe."""
    _producto(db, org, branch_a, "FIS-C1", "19.99")
    _producto(db, org, branch_a, "FIS-C2", "0.05")
    _producto(db, org, branch_a, "FIS-C3", "33.33")
    _abrir_caja(db, org, branch_a, cajero_a)
    items = [
        {"sku": "FIS-C1", "quantity": 3, "discount": 15},
        {"sku": "FIS-C2", "quantity": 7},
        {"sku": "FIS-C3", "quantity": 1, "discount": 10},
    ]
    esperado = (D("19.99") * 3 * D("0.85") + D("0.05") * 7 + D("33.33") * D("0.9")).quantize(D("0.01"))
    resp = _vender(client, org, auth_cajero_a, items, str(esperado + 1))
    assert resp.status_code in (200, 201), resp.text
    doc = _documento(db, org)
    assert _suma_fiscal(doc) == doc.total_amount == esperado
    lineas = _lineas(db, doc)
    assert sum((ln.iva_base + ln.iva_importe for ln in lineas), D("0")) == esperado
    assert sum((ln.iva_base for ln in lineas), D("0")) == doc.iva_base_16


def test_lugar_de_expedicion(client, db, org, branch_a, cajero_a, auth_cajero_a):
    branch_a.postal_code = None
    org.codigo_postal_fiscal = "06600"
    db.commit()
    _producto(db, org, branch_a, "FIS-CP", "10.00")
    _abrir_caja(db, org, branch_a, cajero_a)
    resp = _vender(client, org, auth_cajero_a, [{"sku": "FIS-CP", "quantity": 1}], "10.00")
    assert resp.status_code in (200, 201), resp.text
    assert _documento(db, org).lugar_expedicion == "06600"


def test_alta_y_edicion_de_producto_con_claves_sat(client, db, org, branch_a, auth_admin):
    headers = {**auth_admin, "X-Organization-ID": str(org.id)}
    resp = client.post("/api/products/", headers=headers, json={
        "name": "Refresco", "sku": "SAT-1", "price": "20", "cost": "10",
        "target_branch_ids": [branch_a.id],
        "sat_clave_prod_serv": "50202306", "sat_clave_unidad": "h87",
        "sat_objeto_imp": "02", "iva_tratamiento": "16",
    })
    assert resp.status_code in (200, 201), resp.text
    pid = resp.json()["id"]
    assert resp.json()["sat_clave_unidad"] == "H87"

    resp = client.put(f"/api/products/{pid}", headers=headers, json={"iva_tratamiento": "exento"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["iva_tratamiento"] == "EXENTO"
    assert resp.json()["sat_clave_prod_serv"] == "50202306"   # lo no enviado no se toca

    resp = client.put(f"/api/products/{pid}", headers=headers, json={"sat_clave_prod_serv": "123"})
    assert resp.status_code == 422


def test_cp_fiscal_de_la_organizacion_se_valida(client, org, auth_admin):
    headers = {**auth_admin, "X-Organization-ID": str(org.id)}
    resp = client.put("/api/organization/", headers=headers, json={"codigo_postal_fiscal": "066"})
    assert resp.status_code == 422
    resp = client.put("/api/organization/", headers=headers, json={"codigo_postal_fiscal": "06600"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["codigo_postal_fiscal"] == "06600"


def test_migraciones_de_columna_cubren_el_modelo():
    """Cada columna nueva tiene su ALTER idempotente en railway_init y existe
    en el modelo (si no, prod no la crea: create_all no altera tablas vivas)."""
    from app.core.database import Base
    from scripts.railway_init import COLUMN_MIGRATIONS, MIGRACIONES_DESGLOSE_FISCAL

    assert all(m in COLUMN_MIGRATIONS for m in MIGRACIONES_DESGLOSE_FISCAL)
    for tabla, columna, ddl in MIGRACIONES_DESGLOSE_FISCAL:
        assert columna in Base.metadata.tables[tabla].columns, (tabla, columna)
        assert Base.metadata.tables[tabla].columns[columna].nullable
        assert "NOT NULL" not in ddl and "DEFAULT" not in ddl


def test_cotizacion_convertida_en_venta_lleva_desglose(
    client, db, org, branch_a, cajero_a, auth_cajero_a, products_setup
):
    from tests.test_quote_convert_cash_session import _abrir_caja as abrir, _crear_cotizacion, _habilitar_modulo

    _habilitar_modulo(db, org, "quotes")
    _, variant = products_setup["product_a"]
    h = {**auth_cajero_a, "X-Organization-ID": str(org.id)}
    abrir(db, org, branch_a, cajero_a)
    qid = _crear_cotizacion(client, h, variant.sku)
    assert db.query(SalesDocument).filter(SalesDocument.id == qid).one().iva_base_16 is None

    resp = client.post(f"/api/quotes/{qid}/convert-to-sale?payment_method=CASH", headers=h)
    assert resp.status_code in (200, 201), resp.text
    venta = db.query(SalesDocument).filter(SalesDocument.id == qid).one()
    db.refresh(venta)
    assert _suma_fiscal(venta) == venta.total_amount
    assert venta.iva_16 > 0
