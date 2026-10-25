# tests/test_reports_inicio_basico.py
"""`GET /api/reports/inicio-basico` — el "¿cómo voy?" de la dueña en modo básico.

Una sola llamada (una PC vieja de tienda no debe hacer cinco): vendido hoy,
ayer y en 7 días, cobros de hoy por método, lo más vendido, lo que se está
acabando y el estado de la caja. Aislado por organización y por sucursal con
las mismas reglas que el valor de la tienda.
"""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from itertools import count
from zoneinfo import ZoneInfo

from app.models.cash import CashSession
from app.models.inventory import StockOnHand
from app.models.organization import Branch, BranchType, Organization
from app.models.products import Product, ProductVariant
from app.models.sales import DocumentStatus, Payment, PaymentMethod, SalesDocument, SalesLineItem

_MX = ZoneInfo("America/Mexico_City")
URL = "/api/reports/inicio-basico"
_folios = count(1)


def _instante(dias_atras: int, hora: int = 12) -> datetime:
    """Mediodía (hora de México) de hace `dias_atras` días, en UTC."""
    dia = datetime.now(_MX).date() - timedelta(days=dias_atras)
    return datetime.combine(dia, time(hora), tzinfo=_MX).astimezone(timezone.utc)


def _variante(db, org, branch, nombre, sku, existencia):
    p = Product(name=nombre, organization_id=org.id, is_active=True)
    db.add(p)
    db.flush()
    v = ProductVariant(product_id=p.id, sku=sku, price=Decimal("100"), cost=Decimal("40"),
                       organization_id=org.id)
    db.add(v)
    db.flush()
    v.created_at = _instante(400)   # catálogo viejo: "no se mueve" excluye lo recién dado de alta
    db.add(StockOnHand(variant_id=v.id, branch_id=branch.id, organization_id=org.id,
                       qty_on_hand=Decimal(str(existencia)), is_active=True))
    db.flush()
    return v


def _venta(db, org, branch, user, variante, total, *, metodo=PaymentMethod.CASH, dias_atras=0,
           descripcion="Producto", cantidad=1, status=DocumentStatus.PAID):
    doc = SalesDocument(
        organization_id=org.id, branch_id=branch.id, seller_id=user.id, folio=next(_folios),
        series="A", subtotal=Decimal(total), tax_amount=Decimal("0"),
        total_amount=Decimal(total), status=status, doc_type="ORDER",
    )
    doc.created_at = _instante(dias_atras)
    db.add(doc)
    db.flush()
    db.add(SalesLineItem(
        organization_id=org.id, document_id=doc.id, variant_id=variante.id,
        description=descripcion, quantity=cantidad,
        unit_price=Decimal(total) / cantidad, total_line=Decimal(total), unit_cost=Decimal("10"),
    ))
    pago = Payment(organization_id=org.id, sales_document_id=doc.id, method=metodo, amount=Decimal(total))
    pago.created_at = _instante(dias_atras)
    db.add(pago)
    db.commit()
    return doc


def test_hoy_ayer_y_semana(client, db, org, branch_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100")
    _venta(db, org, branch_a, admin_user, v, "50", metodo=PaymentMethod.CARD)
    _venta(db, org, branch_a, admin_user, v, "500", status=DocumentStatus.CANCELLED)
    _venta(db, org, branch_a, admin_user, v, "70", dias_atras=1)
    _venta(db, org, branch_a, admin_user, v, "30", dias_atras=6)
    _venta(db, org, branch_a, admin_user, v, "999", dias_atras=7)

    r = client.get(URL, headers=auth_admin)

    assert r.status_code == 200, r.text
    d = r.json()
    assert d["branch_id"] is None
    assert (d["hoy"]["total"], d["hoy"]["tickets"]) == (150.0, 2)
    assert (d["ayer"]["total"], d["ayer"]["tickets"]) == (70.0, 1)
    assert (d["semana"]["total"], d["semana"]["tickets"]) == (250.0, 4)
    assert d["hoy"]["desde"] == d["hoy"]["hasta"] == d["semana"]["hasta"]


def test_cobros_de_hoy_por_metodo(client, db, org, branch_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100")
    _venta(db, org, branch_a, admin_user, v, "50", metodo=PaymentMethod.CARD)
    _venta(db, org, branch_a, admin_user, v, "80", dias_atras=1)

    d = client.get(URL, headers=auth_admin).json()

    assert d["por_metodo_hoy"] == {"CASH": 100.0, "CARD": 50.0}


def test_lo_mas_vendido_de_la_semana_por_piezas_y_maximo_cinco(client, db, org, branch_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "40", descripcion="Blusa", cantidad=2)
    _venta(db, org, branch_a, admin_user, v, "20", descripcion="Blusa", cantidad=1, dias_atras=3)
    for nombre in ("Falda", "Short", "Gorra", "Bolsa", "Cinto"):
        _venta(db, org, branch_a, admin_user, v, "10", descripcion=nombre)
    _venta(db, org, branch_a, admin_user, v, "999", descripcion="Vieja", cantidad=50, dias_atras=8)

    top = client.get(URL, headers=auth_admin).json()["top_semana"]

    assert len(top) == 5
    assert top[0] == {"nombre": "Blusa", "cantidad": 3.0, "total": 60.0}
    assert "Vieja" not in [t["nombre"] for t in top]


def test_poca_existencia_con_el_tope_de_la_empresa(client, db, org, branch_a, admin_user, auth_admin):
    for n in range(12):
        _variante(db, org, branch_a, f"Prod {n:02d}", f"SKU-{n:02d}", n)
    db.commit()

    d = client.get(URL, headers=auth_admin).json()["poca_existencia"]
    assert d["umbral"] == 3
    assert [p["existencia"] for p in d["productos"]] == [0.0, 1.0, 2.0, 3.0]
    assert d["productos"][0]["nombre"] == "Prod 00"

    org.umbral_poca_existencia = 20
    db.commit()
    d = client.get(URL, headers=auth_admin).json()["poca_existencia"]
    assert d["umbral"] == 20
    assert len(d["productos"]) == 10


def test_poca_existencia_empata_con_orden_estable(client, db, org, branch_a, admin_user, auth_admin):
    for n in range(4):
        _variante(db, org, branch_a, "Igual", f"IG-{n}", 1)
    db.commit()
    a = client.get(URL, headers=auth_admin).json()["poca_existencia"]["productos"]
    b = client.get(URL, headers=auth_admin).json()["poca_existencia"]["productos"]
    assert [p["variant_id"] for p in a] == [p["variant_id"] for p in b]
    assert [p["variant_id"] for p in a] == sorted(p["variant_id"] for p in a)


def test_poca_existencia_sin_inactivos_borrados_ni_bodegas(client, db, org, branch_a, hq_branch, admin_user, auth_admin):
    _variante(db, org, branch_a, "Activo", "A-1", 1)
    inactivo = _variante(db, org, branch_a, "Inactivo", "I-1", 0)
    db.get(Product, inactivo.product_id).is_active = False
    borrada = _variante(db, org, branch_a, "Borrada", "B-1", 0)
    borrada.deleted_at = datetime.now(timezone.utc)
    _variante(db, org, hq_branch, "Bodega", "H-1", 0)  # HQ de conftest: can_sell=False
    db.commit()

    productos = client.get(URL, headers=auth_admin).json()["poca_existencia"]["productos"]

    assert [p["nombre"] for p in productos] == ["Activo"]


def test_otra_organizacion_no_se_mezcla(client, db, org, branch_a, admin_user, auth_admin):
    otra = Organization(name="Otra", status="ACTIVE")
    db.add(otra)
    db.flush()
    ajena = Branch(name="Ajena", branch_type=BranchType.STORE, can_sell=True, is_active=True,
                   organization_id=otra.id)
    db.add(ajena)
    db.flush()
    v = _variante(db, otra, ajena, "Ajeno", "AJ-1", 0)
    _venta(db, otra, ajena, admin_user, v, "777")

    d = client.get(URL, headers=auth_admin).json()

    assert d["hoy"]["tickets"] == 0
    assert d["por_metodo_hoy"] == {}
    assert d["top_semana"] == []
    assert d["poca_existencia"]["productos"] == []
    assert client.get(f"{URL}?branch_id={ajena.id}", headers=auth_admin).status_code == 404


def test_la_duena_puede_mirar_una_sucursal(client, db, org, branch_a, branch_b, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100")
    _venta(db, org, branch_b, admin_user, v, "700")

    d = client.get(f"{URL}?branch_id={branch_b.id}", headers=auth_admin).json()

    assert d["branch_id"] == branch_b.id
    assert d["hoy"]["total"] == 700.0
    assert client.get(URL, headers=auth_admin).json()["hoy"]["total"] == 800.0


def test_el_gerente_solo_ve_su_sucursal(client, db, org, branch_a, branch_b, gerente_a, auth_gerente_a):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, gerente_a, v, "100")
    _venta(db, org, branch_b, gerente_a, v, "700")

    d = client.get(f"{URL}?branch_id={branch_b.id}", headers=auth_gerente_a).json()

    assert d["branch_id"] == branch_a.id
    assert d["hoy"]["total"] == 100.0
    assert d["por_metodo_hoy"] == {"CASH": 100.0}


def test_la_cajera_no_ve_el_inicio(client, cajero_a, auth_cajero_a):
    assert client.get(URL, headers=auth_cajero_a).status_code == 403


def test_corte_abierto_con_efectivo_esperado(client, db, org, branch_a, cajero_a, admin_user, auth_admin):
    db.add(CashSession(user_id=cajero_a.id, branch_id=branch_a.id, organization_id=org.id,
                       opening_balance=Decimal("500"), status="OPEN"))
    db.commit()

    c = client.get(URL, headers=auth_admin).json()["corte"]

    assert c["estado"] == "abierto"
    assert c["cajera"] == "cajero_a"
    assert c["efectivo_esperado"] == 500.0
    assert c["abierto_en"] is not None
    assert c["efectivo_contado"] is None


def test_corte_sin_turno_y_cerrado(client, db, org, branch_a, cajero_a, admin_user, auth_admin):
    assert client.get(URL, headers=auth_admin).json()["corte"] == {
        "estado": "sin_turno", "cajera": None, "abierto_en": None, "cerrado_en": None,
        "efectivo_esperado": None, "efectivo_contado": None,
    }
    db.add(CashSession(user_id=cajero_a.id, branch_id=branch_a.id, organization_id=org.id,
                       opening_balance=Decimal("500"), closing_balance=Decimal("850"),
                       status="CLOSED", closed_at=datetime.now(timezone.utc)))
    db.commit()

    c = client.get(URL, headers=auth_admin).json()["corte"]

    assert c["estado"] == "cerrado"
    assert c["efectivo_contado"] == 850.0
    assert c["efectivo_esperado"] is None
    assert c["cerrado_en"] is not None


# ── SP6: /inicio, alias, completo, sin_movimiento, utilidad, pendientes, sucursales ──
from app.models.returns import SaleReturn  # noqa: E402

INICIO = "/api/reports/inicio"


def test_alias_inicio_basico_sigue_respondiendo(client, db, org, branch_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100")
    a = client.get(URL, headers=auth_admin).json()
    b = client.get(INICIO, headers=auth_admin).json()
    assert a == b
    assert a["hoy"]["total"] == 100.0
    assert set(a) == {"branch_id", "hoy", "ayer", "semana", "por_metodo_hoy", "top_semana", "poca_existencia", "corte",
                      "sin_movimiento", "pendientes", "sucursales", "utilidad_bruta_hoy", "venta_sin_costo_hoy", "venta_con_costo_hoy",
                      "tendencia", "por_hora_hoy", "utilidad_bruta_ayer"}


def test_sin_completo_las_secciones_nuevas_son_null(client, db, org, branch_a, admin_user, auth_admin):
    _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    db.commit()
    d = client.get(INICIO, headers=auth_admin).json()
    assert d["sin_movimiento"] is None
    assert d["pendientes"] is None
    assert d["sucursales"] is None
    assert d["utilidad_bruta_hoy"] is None


def test_sin_movimiento_vendido_hace_diez_dias_sale_con_treinta_no_con_cinco(client, db, org, branch_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 4)
    _venta(db, org, branch_a, admin_user, v, "100", dias_atras=10)
    nunca = _variante(db, org, branch_a, "Nunca vendida", "NUN-1", 2)
    db.commit()

    con30 = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()["sin_movimiento"]
    assert con30["dias"] == 30
    assert [p["sku"] for p in con30["productos"]] == ["NUN-1"]
    assert con30["productos"][0] == {"variant_id": str(nunca.id), "nombre": "Nunca vendida", "sku": "NUN-1",
                                      "existencia": 2.0, "importe_venta": 200.0}

    con5 = client.get(f"{INICIO}?completo=true&dias_sin_movimiento=5", headers=auth_admin).json()["sin_movimiento"]
    assert con5["dias"] == 5
    assert sorted(p["sku"] for p in con5["productos"]) == ["BLU-1", "NUN-1"]


def test_sin_movimiento_cancelada_no_cuenta_como_venta(client, db, org, branch_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 4)
    _venta(db, org, branch_a, admin_user, v, "100", dias_atras=1, status=DocumentStatus.CANCELLED)
    db.commit()
    d = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()["sin_movimiento"]
    assert [p["sku"] for p in d["productos"]] == ["BLU-1"]


def test_sin_movimiento_sin_existencia_no_sale_y_otra_org_no_se_mezcla(client, db, org, branch_a, admin_user, auth_admin):
    _variante(db, org, branch_a, "Agotada", "AGO-1", 0)
    otra = Organization(name="Otra", status="ACTIVE")
    db.add(otra)
    db.flush()
    ajena = Branch(name="Ajena", branch_type=BranchType.STORE, can_sell=True, is_active=True, organization_id=otra.id)
    db.add(ajena)
    db.flush()
    _variante(db, otra, ajena, "Ajena", "AJ-1", 9)
    db.commit()
    d = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()["sin_movimiento"]
    assert d["productos"] == []


def test_sin_movimiento_orden_por_importe_y_tope_diez(client, db, org, branch_a, admin_user, auth_admin):
    for n in range(12):
        _variante(db, org, branch_a, f"P{n:02d}", f"P-{n:02d}", n + 1)   # importe = (n+1) × 100
    db.commit()
    d = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()["sin_movimiento"]["productos"]
    assert len(d) == 10
    assert [p["importe_venta"] for p in d] == [1200.0, 1100.0, 1000.0, 900.0, 800.0, 700.0, 600.0, 500.0, 400.0, 300.0]


def test_utilidad_bruta_hoy_admin_si_gerente_null(client, db, org, branch_a, admin_user, gerente_a, auth_admin, auth_gerente_a):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100", cantidad=2)   # unit_cost 10 × 2 = 20
    _venta(db, org, branch_a, admin_user, v, "999", dias_atras=1)
    d = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()
    assert (d["utilidad_bruta_hoy"], d["venta_sin_costo_hoy"]) == (80.0, 0.0)
    g = client.get(f"{INICIO}?completo=true", headers=auth_gerente_a).json()
    assert (g["utilidad_bruta_hoy"], g["venta_sin_costo_hoy"]) == (None, None)


def test_utilidad_bruta_solo_sobre_renglones_con_costo(client, db, org, branch_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100", cantidad=2)   # con costo: 100 − 20 = 80
    sin = _venta(db, org, branch_a, admin_user, v, "500")         # sin costo: fuera de la utilidad
    for r in sin.lines if hasattr(sin, "lines") else db.query(SalesLineItem).filter(SalesLineItem.document_id == sin.id).all():
        r.unit_cost = None
    db.commit()
    d = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()
    assert (d["utilidad_bruta_hoy"], d["venta_sin_costo_hoy"], d["hoy"]["total"]) == (80.0, 500.0, 600.0)


def test_sin_movimiento_no_lista_variantes_recien_dadas_de_alta(client, db, org, branch_a, admin_user, auth_admin):
    vieja = _variante(db, org, branch_a, "Vieja", "VIE-1", 2)
    vieja.created_at = _instante(40)
    nueva = _variante(db, org, branch_a, "Nueva", "NUE-1", 9)
    nueva.created_at = _instante(5)
    db.commit()
    d = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()["sin_movimiento"]["productos"]
    assert [p["sku"] for p in d] == ["VIE-1"]
    d = client.get(f"{INICIO}?completo=true&dias_sin_movimiento=3", headers=auth_admin).json()["sin_movimiento"]["productos"]
    assert sorted(p["sku"] for p in d) == ["NUE-1", "VIE-1"]


def test_cajera_tampoco_con_completo(client, auth_cajero_a):
    assert client.get(f"{INICIO}?completo=true", headers=auth_cajero_a).status_code == 403


def _devolucion(db, org, branch, user, doc, status="PENDING"):
    db.add(SaleReturn(organization_id=org.id, sale_id=doc.id, user_id=user.id, branch_id=branch.id,
                      total_refunded=Decimal("10"), reason="Defecto", status=status))
    db.commit()


def test_pendientes_devolucion_pending_turno_viejo_y_diferencia(client, db, org, branch_a, cajero_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    doc = _venta(db, org, branch_a, admin_user, v, "100")
    _devolucion(db, org, branch_a, cajero_a, doc)
    _devolucion(db, org, branch_a, cajero_a, doc, status="APPROVED")
    db.add(CashSession(user_id=cajero_a.id, branch_id=branch_a.id, organization_id=org.id,
                       opening_balance=Decimal("500"), status="OPEN", opened_at=_instante(2)))
    # Un turno abierto hoy (otra persona: solo cabe un turno abierto por cajera y sucursal) no cuenta.
    db.add(CashSession(user_id=admin_user.id, branch_id=branch_a.id, organization_id=org.id,
                       opening_balance=Decimal("500"), status="OPEN", opened_at=_instante(0, hora=9)))
    # Cerrado ayer: esperado 500 (solo fondo), contado 480 → diferencia -20.
    db.add(CashSession(user_id=cajero_a.id, branch_id=branch_a.id, organization_id=org.id,
                       opening_balance=Decimal("500"), closing_balance=Decimal("480"), status="CLOSED",
                       opened_at=_instante(1, hora=9), closed_at=_instante(1, hora=20)))
    db.commit()

    p = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()["pendientes"]

    assert p["devoluciones"] == 1
    assert p["turnos_abiertos"] == 1
    assert len(p["diferencias_caja"]) == 1
    dif = p["diferencias_caja"][0]
    assert (dif["sucursal"], dif["cajera"], dif["esperado"], dif["contado"], dif["diferencia"]) == \
        ("Sucursal A", "cajero_a", 500.0, 480.0, -20.0)


def test_pendientes_corte_cuadrado_o_viejo_no_cuenta(client, db, org, branch_a, cajero_a, auth_admin):
    db.add(CashSession(user_id=cajero_a.id, branch_id=branch_a.id, organization_id=org.id,
                       opening_balance=Decimal("500"), closing_balance=Decimal("500"), status="CLOSED",
                       opened_at=_instante(1, hora=9), closed_at=_instante(1, hora=20)))
    db.add(CashSession(user_id=cajero_a.id, branch_id=branch_a.id, organization_id=org.id,
                       opening_balance=Decimal("500"), closing_balance=Decimal("100"), status="CLOSED",
                       opened_at=_instante(9, hora=9), closed_at=_instante(9, hora=20)))
    db.commit()
    p = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()["pendientes"]
    assert p == {"devoluciones": 0, "turnos_abiertos": 0, "diferencias_caja": []}


def test_sucursales_null_con_una_sola_que_vende(client, db, org, branch_a, hq_branch, auth_admin):
    _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    db.commit()
    assert client.get(f"{INICIO}?completo=true", headers=auth_admin).json()["sucursales"] is None


def test_sucursales_con_dos_que_venden(client, db, org, branch_a, branch_b, cajero_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 1)
    _venta(db, org, branch_a, admin_user, v, "100")
    _venta(db, org, branch_b, admin_user, v, "700")
    _venta(db, org, branch_b, admin_user, v, "50")
    db.add(CashSession(user_id=cajero_a.id, branch_id=branch_b.id, organization_id=org.id,
                       opening_balance=Decimal("300"), status="OPEN"))
    db.commit()

    s = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()["sucursales"]

    assert [x["nombre"] for x in s] == ["Sucursal A", "Sucursal B"]
    a, b = s
    assert (a["branch_id"], a["ventas_hoy"], a["tickets_hoy"], a["corte"]["estado"], a["poca_existencia"]) == \
        (branch_a.id, 100.0, 1, "sin_turno", 1)
    assert (b["ventas_hoy"], b["tickets_hoy"], b["corte"]["estado"], b["corte"]["efectivo_esperado"], b["poca_existencia"]) == \
        (750.0, 2, "abierto", 300.0, 0)


def test_sucursales_null_al_pedir_una_sucursal_y_para_el_gerente(client, db, org, branch_a, branch_b, gerente_a, auth_admin, auth_gerente_a):
    _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    db.commit()
    assert client.get(f"{INICIO}?completo=true&branch_id={branch_a.id}", headers=auth_admin).json()["sucursales"] is None
    g = client.get(f"{INICIO}?completo=true", headers=auth_gerente_a).json()
    assert g["sucursales"] is None
    assert g["sin_movimiento"] is not None


def test_dias_sin_movimiento_fuera_de_rango_es_422(client, auth_admin):
    assert client.get(f"{INICIO}?completo=true&dias_sin_movimiento=0", headers=auth_admin).status_code == 422
    assert client.get(f"{INICIO}?completo=true&dias_sin_movimiento=400", headers=auth_admin).status_code == 422


from app.models.returns import SaleReturn  # noqa: E402


def test_inicio_hoy_es_neto_y_trae_devuelto(client, db, org, branch_a, cajero_a, auth_admin_a):
    var = _variante(db, org, branch_a, "Gorra", "GOR-1", 5)
    v = _venta(db, org, branch_a, cajero_a, var, "100")
    db.add(SaleReturn(organization_id=org.id, sale_id=v.id, user_id=cajero_a.id, branch_id=branch_a.id,
                      total_refunded=Decimal("40"), refund_method=PaymentMethod.CASH, reason="Prueba",
                      status="APPROVED"))
    db.commit()
    d = client.get("/api/reports/inicio?completo=true", headers=auth_admin_a).json()
    assert d["hoy"]["total"] == 60.0 and d["hoy"]["devuelto"] == 40.0 and d["hoy"]["tickets"] == 1
    assert d["semana"]["total"] == 60.0
    assert d["por_metodo_hoy"]["CASH"] == 60.0


# ── Fase 2 (spec 2026-10-23 §3.1): tendencia de 7 días, horas de hoy y utilidad de ayer ──

def test_inicio_completo_trae_tendencia_de_7_dias_y_los_7_anteriores(client, db, org, branch_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    tarde = _venta(db, org, branch_a, admin_user, v, "100")
    tarde.created_at = _instante(0, hora=19)        # 01:00 UTC de mañana: sigue siendo hoy en México
    _venta(db, org, branch_a, admin_user, v, "70", dias_atras=6)      # primer día del tramo actual
    _venta(db, org, branch_a, admin_user, v, "999", dias_atras=7)     # último día del comparativo
    _venta(db, org, branch_a, admin_user, v, "5", dias_atras=14)      # fuera de los dos tramos
    db.commit()

    t = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()["tendencia"]

    hoy = datetime.now(_MX).date()
    assert [d["fecha"] for d in t["dias"]] == [str(hoy - timedelta(days=6 - i)) for i in range(7)]
    assert [d["neta"] for d in t["dias"]] == [70.0, 0.0, 0.0, 0.0, 0.0, 0.0, 100.0]
    assert [d["tickets"] for d in t["dias"]] == [1, 0, 0, 0, 0, 0, 1]
    assert [d["fecha"] for d in t["anterior"]] == [str(hoy - timedelta(days=13 - i)) for i in range(7)]
    assert [d["neta"] for d in t["anterior"]] == [0.0] * 6 + [999.0]


def test_inicio_tendencia_respeta_la_sucursal_pedida(client, db, org, branch_a, branch_b, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100")
    _venta(db, org, branch_b, admin_user, v, "700")
    t = client.get(f"{INICIO}?completo=true&branch_id={branch_a.id}", headers=auth_admin).json()["tendencia"]
    assert t["dias"][-1]["neta"] == 100.0
    assert client.get(f"{INICIO}?completo=true", headers=auth_admin).json()["tendencia"]["dias"][-1]["neta"] == 800.0


def test_inicio_por_hora_hoy_trae_24_horas_en_hora_de_mexico(client, db, org, branch_a, admin_user, auth_admin):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    tarde = _venta(db, org, branch_a, admin_user, v, "100")
    tarde.created_at = _instante(0, hora=19)
    dev = SaleReturn(organization_id=org.id, sale_id=tarde.id, user_id=admin_user.id, branch_id=branch_a.id,
                     total_refunded=Decimal("40"), refund_method=PaymentMethod.CASH, reason="Prueba", status="APPROVED")
    dev.created_at = _instante(0, hora=20)
    db.add(dev)
    db.commit()

    h = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()["por_hora_hoy"]

    assert [x["hora"] for x in h] == list(range(24))
    assert h[19] == {"hora": 19, "neta": 100.0, "tickets": 1}
    assert h[20] == {"hora": 20, "neta": -40.0, "tickets": 0}   # la devolución resta en su hora


def test_inicio_sin_completo_no_trae_tendencia_horas_ni_utilidad_de_ayer(client, db, org, branch_a, admin_user, auth_admin):
    _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    db.commit()
    d = client.get(INICIO, headers=auth_admin).json()
    assert d["tendencia"] is None and d["por_hora_hoy"] is None and d["utilidad_bruta_ayer"] is None


def test_inicio_utilidad_bruta_ayer_para_admin_y_null_para_gerente(client, db, org, branch_a, admin_user, gerente_a, auth_admin, auth_gerente_a):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100", cantidad=2, dias_atras=1)   # 100 − 10 × 2 = 80
    d = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()
    assert d["utilidad_bruta_ayer"] == 80.0
    assert client.get(f"{INICIO}?completo=true", headers=auth_gerente_a).json()["utilidad_bruta_ayer"] is None


# ── Ola final: la misma base de utilidad bruta en Inicio y Reportes ──

def test_inicio_venta_con_costo_hoy_es_la_base_de_la_utilidad(client, db, org, branch_a, admin_user, gerente_a, auth_admin, auth_gerente_a):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100", cantidad=2)   # con costo (unit_cost 10)
    sin = _venta(db, org, branch_a, admin_user, v, "500")         # sin costo: fuera de la base
    for r in db.query(SalesLineItem).filter(SalesLineItem.document_id == sin.id).all():
        r.unit_cost = None
    db.commit()

    d = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()
    assert d["venta_con_costo_hoy"] == 100.0
    assert (d["utilidad_bruta_hoy"], d["venta_sin_costo_hoy"]) == (80.0, 500.0)
    assert client.get(f"{INICIO}?completo=true", headers=auth_gerente_a).json()["venta_con_costo_hoy"] is None
    assert client.get(INICIO, headers=auth_admin).json()["venta_con_costo_hoy"] is None


# ── Ola final (T1): gerente y org sin ventas en tendencia y horas ──

def test_inicio_gerente_tendencia_y_horas_solo_de_su_sucursal(client, db, org, branch_a, branch_b, admin_user, gerente_a, auth_gerente_a):
    v = _variante(db, org, branch_a, "Blusa", "BLU-1", 50)
    _venta(db, org, branch_a, admin_user, v, "100")
    _venta(db, org, branch_b, admin_user, v, "700")

    d = client.get(f"{INICIO}?completo=true&branch_id={branch_b.id}", headers=auth_gerente_a).json()

    assert d["tendencia"]["dias"][-1]["neta"] == 100.0
    assert sum(h["neta"] for h in d["por_hora_hoy"]) == 100.0


def test_inicio_org_sin_ventas_trae_7_dias_y_24_horas_en_cero(client, db, org, branch_a, auth_admin):
    db.commit()
    d = client.get(f"{INICIO}?completo=true", headers=auth_admin).json()
    assert [x["neta"] for x in d["tendencia"]["dias"]] == [0.0] * 7
    assert [x["tickets"] for x in d["tendencia"]["dias"]] == [0] * 7
    assert len(d["tendencia"]["anterior"]) == 7
    assert [h["hora"] for h in d["por_hora_hoy"]] == list(range(24))
    assert all(h["neta"] == 0.0 and h["tickets"] == 0 for h in d["por_hora_hoy"])
