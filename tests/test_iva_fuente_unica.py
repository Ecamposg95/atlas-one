"""Una sola fuente de verdad para la tasa de IVA de un producto.

`app/services/desglose_fiscal.py::iva_efectivo` decide la tasa que el cobro
suma con factura y la que declara el desglose fiscal. Con clasificación
fiscal capturada (`iva_tratamiento`, u objeto de impuesto "01") manda ella;
sin clasificación, el cobro sigue `has_iva`/`tax_rate` como siempre.

Requisito duro: para ningún producto que se pueda guardar cambia lo que se le
cobra al cliente. Se prueba dos veces:

* en aritmética pura, exhaustivo: el cobro histórico (banderas de la variante)
  contra el nuevo (`iva_efectivo`) en toda combinación de banderas,
  clasificación, factura, modo de precio e importe; difieren exactamente en
  las combinaciones que el alta rechaza (`discrepancia_iva`);
* por la API de cobro, con la matriz con/sin factura × modo neto/bruto ×
  has_iva sí/no × tasas 16/8/0/exento × con/sin descuento, comparando el
  total cobrado contra el que calculaba el checkout antes del cambio.
"""
import csv
import io
import itertools
from decimal import Decimal

import pytest

from app.models.products import Product, ProductVariant
from app.services.desglose_fiscal import discrepancia_iva, iva_efectivo
from app.services.tax import compute_line_tax, quantize_amount, quantize_totals
from tests.test_iva_sale_integration import _abrir_caja, _documento, _producto

D = Decimal


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


def _cobro_historico(importe, has_iva, tax_rate, pit, factura):
    """Lo que hacía `create_sale` antes: leer directo las banderas de la variante."""
    return compute_line_tax(importe, tax_rate, bool(has_iva), pit, factura, quantize=False)


def _cobro_nuevo(importe, tratamiento, objeto, has_iva, tax_rate, pit, factura):
    iva = iva_efectivo(tratamiento, objeto, has_iva, tax_rate)
    return compute_line_tax(importe, iva.tasa_pct, iva.cobra_iva, pit, factura, quantize=False)


# --- 1. Aritmética pura, exhaustiva ---

HAS_IVA = (True, False, None)
TASAS_VARIANTE = (None, 0, "0.00", 8, "8.00", 16, "16.00", "5")
TRATAMIENTOS = (None, "16", "8", "0", "EXENTO")
OBJETOS = (None, "02", "01", "03")
IMPORTES = (D("100"), D("19.99") * 3 * D("0.85"), D("0.05"), D("33.33") * D("0.9"))


def test_sin_discrepancia_el_cobro_es_identico_en_toda_combinacion():
    revisadas = 0
    for has_iva, tasa, trat, objeto in itertools.product(HAS_IVA, TASAS_VARIANTE, TRATAMIENTOS, OBJETOS):
        discrepancia = discrepancia_iva(trat, objeto, has_iva, tasa)
        sin_clasificar = trat is None and objeto != "01"
        if sin_clasificar:
            assert discrepancia is None
        difiere_en_alguno = False
        for pit, factura, importe in itertools.product((False, True), (False, True), IMPORTES):
            antes = _cobro_historico(importe, has_iva, tasa, pit, factura)
            despues = _cobro_nuevo(importe, trat, objeto, has_iva, tasa, pit, factura)
            if discrepancia is None:
                assert despues == antes, (has_iva, tasa, trat, objeto, pit, factura, importe)
                revisadas += 1
            elif despues != antes:
                difiere_en_alguno = True
        # La validación no frena de más: lo que rechaza sí cobraría distinto.
        if discrepancia is not None:
            assert difiere_en_alguno, (has_iva, tasa, trat, objeto)
    assert revisadas > 1000


def test_sin_clasificacion_el_cobro_sigue_las_banderas_y_el_desglose_infiere():
    iva = iva_efectivo(None, None, False, D("16"))
    assert (iva.cobra_iva, iva.clasificado) == (False, False)
    assert iva.tratamiento.clave == "16" and iva.tratamiento.inferido is True
    iva = iva_efectivo(None, None, True, D("8"))
    assert (iva.cobra_iva, iva.tasa_pct) == (True, D("8"))
    assert iva.tratamiento.clave == "8"


def test_con_clasificacion_manda_para_cobro_y_desglose():
    iva = iva_efectivo("8", "02", True, D("8.00"))
    assert (iva.cobra_iva, iva.tasa_pct, iva.clasificado) == (True, D("8.0000"), True)
    assert iva.tratamiento.tasa == D("0.0800") and iva.tratamiento.inferido is False
    iva = iva_efectivo("EXENTO", None, False, D("16"))
    assert iva.cobra_iva is False and iva.tratamiento.tipo_factor == "Exento"
    iva = iva_efectivo(None, "01", False, D("16"))
    assert iva.cobra_iva is False and iva.clasificado and iva.tratamiento.clave == "NO_OBJETO"


@pytest.mark.parametrize("trat, objeto, has_iva, tasa, pista", [
    ("16", None, False, "16", "«Aplica IVA» apagado"),
    ("16", None, True, "0", "con tasa 0 %"),
    ("16", None, True, "8", "Pon 16 en «Tasa IVA (%)»"),
    ("8", None, True, "16", "Pon 8 en «Tasa IVA (%)»"),
    ("0", None, True, "16", "Apaga «Aplica IVA»"),
    ("EXENTO", None, True, "16", "«Exento de IVA»"),
    (None, "01", True, "16", "«No objeto de impuesto»"),
])
def test_mensajes_de_discrepancia_dicen_que_ajustar(trat, objeto, has_iva, tasa, pista):
    mensaje = discrepancia_iva(trat, objeto, has_iva, D(tasa))
    assert mensaje and pista in mensaje
    assert "datos fiscales" in mensaje


# --- 2. Por la API de cobro: el total cobrado antes y después ---

# (sku, has_iva, tax_rate, iva_tratamiento, sat_objeto_imp, precio)
CATALOGO = [
    ("M-NOIVA-16", False, "16", None, None, "19.99"),
    ("M-IVA-16", True, "16", None, None, "33.33"),
    ("M-IVA-8", True, "8", None, None, "57.10"),
    ("M-IVA-0", True, "0", None, None, "12.35"),
    ("M-NOIVA-0", False, "0", None, None, "8.75"),
    ("M-T16", True, "16", "16", "02", "99.99"),
    ("M-T8", True, "8", "8", "02", "41.27"),
    ("M-T0-NOIVA", False, "16", "0", "02", "23.50"),
    ("M-T0-IVA0", True, "0", "0", "02", "15.05"),
    ("M-EX-NOIVA", False, "16", "EXENTO", None, "12.30"),
    ("M-EX-IVA0", True, "0", "EXENTO", None, "7.77"),
    ("M-NOOBJ", False, "16", None, "01", "4.99"),
]


@pytest.mark.parametrize("factura", [False, True], ids=["sin_factura", "con_factura"])
@pytest.mark.parametrize("bruto", [False, True], ids=["neto", "bruto"])
@pytest.mark.parametrize("descuento", [0, 15], ids=["sin_desc", "desc15"])
def test_el_total_cobrado_no_cambia(client, db, org, branch_a, cajero_a, auth_cajero_a, factura, bruto, descuento):
    org.price_includes_tax = bruto
    db.commit()
    variantes = {}
    for sku, has_iva, tasa, trat, objeto, precio in CATALOGO:
        # Toda configuración de la matriz se puede guardar.
        assert discrepancia_iva(trat, objeto, has_iva, D(tasa)) is None, sku
        v = _producto(db, org, branch_a, sku, precio, has_iva=has_iva, tax_rate=D(tasa))
        v.product.iva_tratamiento = trat
        v.product.sat_objeto_imp = objeto
        variantes[sku] = v
    db.commit()
    _abrir_caja(db, org, branch_a, cajero_a)

    cantidad = 3
    subtotal = impuesto = total = D("0")
    por_renglon = {}
    for sku, v in variantes.items():
        importe = D(str(v.price)) * cantidad * (D(1) - D(descuento) / D(100))
        antes = _cobro_historico(importe, v.has_iva, v.tax_rate, bruto, factura)
        subtotal += antes.subtotal
        impuesto += antes.tax
        total += antes.total
        por_renglon[v.id] = antes.total
    total = quantize_amount(total)
    esperado = quantize_totals(subtotal, impuesto)

    items = [{"sku": sku, "quantity": cantidad, "discount": descuento} for sku in variantes]
    resp = client.post("/api/sales/", headers=_h(auth_cajero_a, org), json={
        "doc_type": "ORDER", "items": items, "requires_invoice": factura,
        "payments": [{"method": "CASH", "amount": str(total)}],
    })
    assert resp.status_code in (200, 201), resp.text
    assert D(str(resp.json()["total"])) == total

    doc = _documento(db, org)
    assert doc.total_amount == total
    assert (doc.subtotal, doc.tax_amount) == (esperado.subtotal, esperado.tax)
    # El renglón se guarda sin redondear y lo redondea la columna (en SQLite
    # 145.605 queda 145.60): se compara contra el mismo importe sin redondear.
    for linea in doc.lines:
        assert abs(D(str(linea.total_line)) - por_renglon[linea.variant_id]) <= D("0.005"), linea.description
    # Y el desglose fiscal sigue cuadrando contra lo cobrado.
    fiscal = sum((doc.iva_base_16, doc.iva_16, doc.iva_base_8, doc.iva_8, doc.iva_base_0,
                  doc.iva_base_exenta, doc.iva_base_no_objeto), D("0"))
    assert fiscal == total


def test_con_factura_y_clasificacion_el_desglose_coincide_con_el_ticket(
    client, db, org, branch_a, cajero_a, auth_cajero_a,
):
    """La misma tasa en el cobro y en el desglose: con factura en modo neto,
    base e IVA del desglose son el subtotal y el IVA del ticket."""
    v = _producto(db, org, branch_a, "UNA-8", "100.00", has_iva=True, tax_rate=D("8"))
    v.product.iva_tratamiento = "8"
    db.commit()
    _abrir_caja(db, org, branch_a, cajero_a)
    resp = client.post("/api/sales/", headers=_h(auth_cajero_a, org), json={
        "doc_type": "ORDER", "items": [{"sku": "UNA-8", "quantity": 1}], "requires_invoice": True,
        "payments": [{"method": "CASH", "amount": "108.00"}],
    })
    assert resp.status_code in (200, 201), resp.text
    doc = _documento(db, org)
    assert (doc.iva_base_8, doc.iva_8) == (doc.subtotal, doc.tax_amount) == (D("100.00"), D("8.00"))
    assert doc.lines[0].iva_inferido is False


# --- 3. Validación al guardar ---

def _alta(client, org, auth, **extra):
    cuerpo = {"name": "Galletas", "sku": extra.pop("sku", "VAL-1"), "price": "20", "cost": "10"}
    cuerpo.update(extra)
    return client.post("/api/products/", headers=_h(auth, org), json=cuerpo)


def test_alta_contradictoria_es_422_y_dice_que_ajustar(client, org, branch_a, auth_admin):
    resp = _alta(client, org, auth_admin, target_branch_ids=[branch_a.id], iva_tratamiento="16")
    assert resp.status_code == 422
    assert "«Aplica IVA»" in resp.json()["detail"]

    resp = _alta(client, org, auth_admin, target_branch_ids=[branch_a.id],
                 iva_tratamiento="0", has_iva=True, tax_rate="16")
    assert resp.status_code == 422
    assert "Apaga «Aplica IVA»" in resp.json()["detail"]

    resp = _alta(client, org, auth_admin, target_branch_ids=[branch_a.id],
                 iva_tratamiento="16", has_iva=True, tax_rate="16")
    assert resp.status_code in (200, 201), resp.text


def test_edicion_contradictoria_es_422_y_no_guarda_nada(client, db, org, branch_a, auth_admin):
    resp = _alta(client, org, auth_admin, target_branch_ids=[branch_a.id],
                 iva_tratamiento="16", has_iva=True, tax_rate="16")
    pid = resp.json()["id"]

    resp = client.put(f"/api/products/{pid}", headers=_h(auth_admin, org), json={"tax_rate": "8", "name": "Otro"})
    assert resp.status_code == 422
    assert "Pon 16 en «Tasa IVA (%)»" in resp.json()["detail"]
    resp = client.put(f"/api/products/{pid}", headers=_h(auth_admin, org), json={"iva_tratamiento": "EXENTO"})
    assert resp.status_code == 422
    db.expire_all()
    producto = db.query(Product).filter(Product.id == pid).one()
    assert (producto.name, producto.iva_tratamiento) == ("Galletas", "16")

    # Ajustando las dos cosas juntas sí se guarda.
    resp = client.put(f"/api/products/{pid}", headers=_h(auth_admin, org),
                      json={"iva_tratamiento": "EXENTO", "has_iva": False, "tax_rate": "0"})
    assert resp.status_code == 200, resp.text
    # Y quitar la clasificación siempre se puede: vuelven a mandar las banderas.
    resp = client.put(f"/api/products/{pid}", headers=_h(auth_admin, org),
                      json={"iva_tratamiento": None, "has_iva": True, "tax_rate": "16"})
    assert resp.status_code == 200, resp.text


def test_edicion_revisa_tambien_las_tallas(client, db, org, branch_a, auth_admin):
    resp = _alta(client, org, auth_admin, target_branch_ids=[branch_a.id],
                 iva_tratamiento="16", has_iva=True, tax_rate="16",
                 extra_variants=[{"size": "M", "sku": "VAL-1-M"}])
    assert resp.status_code in (200, 201), resp.text
    pid = resp.json()["id"]
    hermana = db.query(ProductVariant).filter(ProductVariant.sku == "VAL-1-M").one()
    assert hermana.has_iva is True    # hereda de la principal
    hermana.has_iva = False
    db.commit()
    resp = client.put(f"/api/products/{pid}", headers=_h(auth_admin, org), json={"name": "Galletas 2"})
    assert resp.status_code == 422
    assert "VAL-1-M" in resp.json()["detail"]


def test_importacion_no_deja_contradecir_la_clasificacion(client, db, org, branch_a, auth_admin):
    v = _producto(db, org, branch_a, "IMP-16", "50.00", has_iva=True, tax_rate=D("16"))
    v.product.iva_tratamiento = "16"
    db.commit()
    archivo = "SKU,Nombre,Departamento,Precio Base,Costo,Stock,Incluye IVA\nIMP-16,Producto IMP-16,General,55,10,,No\n"
    resp = client.post("/api/products/upload", headers=_h(auth_admin, org),
                       files={"file": ("cat.csv", archivo.encode(), "text/csv")})
    assert resp.status_code == 200, resp.text
    assert resp.json()["failed"] == 1
    assert "«Incluye IVA»" in str(resp.json()["details"])
    db.expire_all()
    v = db.query(ProductVariant).filter(ProductVariant.sku == "IMP-16").one()
    assert (v.has_iva, v.price) == (True, D("50.00"))


# --- 4. Reporte de revisión fiscal ---

@pytest.fixture
def catalogo_revision(db, org, branch_a, branch_b):
    sin = _producto(db, org, branch_a, "REV-SIN", "10.00", has_iva=False)
    ok = _producto(db, org, branch_a, "REV-OK", "10.00", has_iva=True)
    ok.product.iva_tratamiento = "16"
    mal = _producto(db, org, branch_a, "REV-MAL", "10.00", has_iva=False)
    mal.product.iva_tratamiento = "16"       # contradicción cargada por fuera de la API
    from app.models.products import ProductBranchStatus
    db.add(ProductBranchStatus(variant_id=mal.id, branch_id=branch_b.id, organization_id=org.id,
                               is_active_pos=True, is_visible=True))
    archivado = _producto(db, org, branch_a, "REV-ARCH", "10.00")
    archivado.product.is_active = False
    db.commit()
    return {"sin": sin, "ok": ok, "mal": mal}


def test_reporte_por_sucursal_para_admin(client, org, branch_a, branch_b, auth_admin, catalogo_revision):
    resp = client.get("/api/products/revision-fiscal", headers=_h(auth_admin, org))
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    resumen = {r["branch_id"]: r for r in cuerpo["resumen"]}
    assert (resumen[branch_a.id]["sin_clasificacion"], resumen[branch_a.id]["con_discrepancia"]) == (1, 1)
    assert (resumen[branch_b.id]["sin_clasificacion"], resumen[branch_b.id]["con_discrepancia"]) == (0, 1)
    assert cuerpo["total"] == 3
    assert [i["problema"] for i in cuerpo["items"]][:2] == ["DISCREPANCIA", "DISCREPANCIA"]
    skus = {i["sku"] for i in cuerpo["items"]}
    assert skus == {"REV-SIN", "REV-MAL"}   # ni el clasificado ni el archivado
    mal = cuerpo["items"][0]
    assert "«Aplica IVA»" in mal["detalle"]

    resp = client.get("/api/products/revision-fiscal?problema=sin_clasificacion&limit=1",
                      headers=_h(auth_admin, org))
    assert [i["sku"] for i in resp.json()["items"]] == ["REV-SIN"]
    assert "16 %" in resp.json()["items"][0]["detalle"]


def test_reporte_cajero_solo_ve_su_sucursal(client, org, branch_a, branch_b, auth_cajero_a, catalogo_revision):
    resp = client.get("/api/products/revision-fiscal", headers=_h(auth_cajero_a, org))
    assert resp.status_code == 200, resp.text
    assert {r["branch_id"] for r in resp.json()["resumen"]} == {branch_a.id}
    resp = client.get(f"/api/products/revision-fiscal?branch_id={branch_b.id}", headers=_h(auth_cajero_a, org))
    assert resp.status_code == 403


def test_reporte_csv(client, org, auth_admin, catalogo_revision):
    resp = client.get("/api/products/export/revision-fiscal.csv", headers=_h(auth_admin, org))
    assert resp.status_code == 200, resp.text
    filas = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))
    assert filas[0][:4] == ["Sucursal", "Producto", "SKU", "Problema"]
    assert len(filas) == 1 + 3
    assert filas[1][3] == "Discrepancia"
