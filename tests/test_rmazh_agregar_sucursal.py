"""Agregar una sucursal de rmazh a una org que ya se mudo (scripts/import_rmazh_org.py).

Caso real: Novedades America (rmazh org 5) se mudo el 2026-11-03 solo con la
sucursal 60 y la matriz; El Mundo de la Taza se quedo en rmazh. Despues se trae
la Taza, con su historial, a la MISMA org de Atlas ONE: el catalogo ya existe
(mismos UUID), los usuarios de la Taza existen inactivos y sin sucursal.
"""
import copy
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.security.passwords import verify_pin
from app.models import SalesDocument
from app.models.cash import CashSession
from app.models.organization import Branch
from app.services.cash_reconciliation import compute_expected_cash
from app.utils.folios import get_next_folio
from scripts.import_rmazh_org import Bloqueo, agregar_sucursales, filtrar_sucursales, importar
from tests.test_import_rmazh_org import HASH, _exportacion

TAZA = 880018
FER = 770028
CAJA_TAZA = 660018
T = "2026-11-10T16:00:00+00:00"


def _con_taza(datos):
    """Suma a la exportacion la sucursal de la Taza con su cajera, caja y 2 ventas."""
    t = datos["tablas"]
    org = datos["org_id"]
    var = t["product_variants"][0]["id"]
    t["branches"].append({"id": TAZA, "name": "El Mundo de la Taza Toluca", "branch_type": "STORE",
                          "can_sell": True, "is_active": True, "is_headquarters": False,
                          "printer_name": "ZJ-58", "organization_id": org})
    t["users"].append({"id": FER, "username": "fernanda_rmz", "full_name": "Fernanda", "role": "CAJERO",
                       "platform_role": "NONE", "is_active": True, "branch_id": TAZA, "password_hash": HASH,
                       "reprint_pin_hash": None, "created_at": T})
    t["user_organizations"].append({"user_id": FER, "organization_id": org, "org_role": "MEMBER",
                                    "is_active": True})
    t.setdefault("employees", []).append({"id": 15, "user_id": FER, "base_branch_id": TAZA,
                                          "first_name": "Fernanda", "organization_id": org})
    t["product_branch_status"].append({"id": str(uuid.uuid4()), "variant_id": var, "branch_id": TAZA,
                                       "is_active_pos": True, "is_visible": True, "organization_id": org})
    t["stock_on_hand"].append({"id": 79, "branch_id": TAZA, "variant_id": var, "qty_on_hand": "40",
                               "is_active": True, "organization_id": org})
    t["cash_sessions"].append({"id": CAJA_TAZA, "user_id": FER, "branch_id": TAZA, "opened_at": T,
                               "closed_at": "2026-11-10T23:00:00+00:00", "opening_balance": "300",
                               "status": "CLOSED", "organization_id": org})
    t["cash_audit_log"].append({"id": 6, "ts": T, "session_id": CAJA_TAZA, "organization_id": org,
                                "branch_id": TAZA, "user_id": FER, "event_type": "SESSION_CLOSED",
                                "amount": "420", "related_table": "cash_sessions",
                                "related_id": str(CAJA_TAZA), "payload_json": {}})
    for folio, total, metodo in ((1, "120", "CASH"), (2, "240", "CARD")):
        vid = str(uuid.uuid4())
        t["sales_documents"].append({"id": vid, "doc_type": "INVOICE", "status": "PAID", "branch_id": TAZA,
                                     "seller_id": FER, "series": "A", "folio": folio, "subtotal": total,
                                     "tax_amount": "0", "total_amount": total, "cash_session_id": CAJA_TAZA,
                                     "change_given": "0", "organization_id": org, "created_at": T})
        t["sales_lines"].append({"id": str(uuid.uuid4()), "document_id": vid, "variant_id": var,
                                 "description": "Taza", "quantity": str(int(Decimal(total) / 120)),
                                 "unit_price": "120", "total_line": total, "organization_id": org})
        t["payments"].append({"id": str(uuid.uuid4()), "sales_document_id": vid, "created_by_id": FER,
                              "amount": total, "method": metodo, "organization_id": org, "created_at": T})
    t["inventory_movements"].append({"id": 11, "branch_id": TAZA, "variant_id": var, "user_id": FER,
                                     "movement_type": "SALE_OUT", "qty_change": "-3", "qty_before": "43",
                                     "qty_after": "40", "reference": "Venta POS", "organization_id": org,
                                     "created_at": T})
    return datos


@pytest.fixture()
def caja_ajena(db, org, branch_a, cajero_a):
    c = CashSession(user_id=cajero_a.id, branch_id=branch_a.id, opening_balance=Decimal("0"),
                    status="CLOSED", organization_id=org.id)
    db.add(c)
    db.flush()
    return c


@pytest.fixture()
def mudada(db, org, branch_a, cajero_a, caja_ajena):
    """La org ya mudada con la 60 y la matriz; devuelve (exportacion completa, resultado)."""
    datos = _con_taza(_exportacion(org.id, branch_a.id, cajero_a.id, caja_ajena.id))
    hq, tienda = branch_a.id + 1, branch_a.id
    r = importar(db, filtrar_sucursales(copy.deepcopy(datos), {hq, tienda}),
                 nombre="Novedades America", plan="PRO", giro="ATLAS_POS")
    return datos, r


def _nueva_pieza(datos):
    """Un producto que se dio de alta en rmazh despues de la primera mudanza."""
    t = datos["tablas"]
    prod, var = str(uuid.uuid4()), str(uuid.uuid4())
    t["products"].append({"id": prod, "name": "Termo", "is_active": True, "has_variants": False,
                          "organization_id": datos["org_id"]})
    t["product_variants"].append({"id": var, "product_id": prod, "sku": "TR-1", "variant_name": "Estándar",
                                  "price": "200.00", "cost": "90.00", "organization_id": datos["org_id"]})
    t["product_branch_status"].append({"id": str(uuid.uuid4()), "variant_id": var, "branch_id": TAZA,
                                       "is_active_pos": True, "is_visible": True,
                                       "organization_id": datos["org_id"]})
    t["stock_on_hand"].append({"id": 80, "branch_id": TAZA, "variant_id": var, "qty_on_hand": "6",
                               "is_active": True, "organization_id": datos["org_id"]})
    return var


def test_crea_la_sucursal_con_su_historial(db, mudada):
    datos, r = mudada
    org_n = r["organization_id"]
    a = agregar_sucursales(db, datos, org_destino=org_n, sucursales={TAZA})
    nueva = a["sucursales"][TAZA]
    b = db.get(Branch, nueva)
    assert b.organization_id == org_n and b.can_sell and b.printer_name == "ZJ-58"
    assert not b.is_headquarters
    assert b.name == "El Mundo de la Taza Toluca"
    ventas = db.execute(text("select count(*), sum(total_amount) from sales_documents where branch_id = :b"),
                        {"b": nueva}).one()
    assert ventas[0] == 2 and Decimal(ventas[1]) == Decimal("360")
    # Folio propio de la sucursal: sigue donde se quedo en rmazh, sin chocar con la 60
    assert get_next_folio(db, nueva, "A") == 3
    la_60 = next(b_["id"] for b_ in datos["tablas"]["branches"]
                 if b_["id"] != TAZA and not b_.get("is_headquarters"))
    assert get_next_folio(db, r["sucursales"][la_60], "A") == 14469
    # Corte de la Taza: fondo 300 + efectivo 120
    venta = next(d for d in datos["tablas"]["sales_documents"] if d["branch_id"] == TAZA)
    caja = db.get(CashSession, db.get(SalesDocument, venta["id"]).cash_session_id)
    assert caja.branch_id == nueva and caja.organization_id == org_n
    assert compute_expected_cash(db, caja).expected == Decimal("420")
    assert db.execute(text("select coalesce(sum(qty_on_hand),0) from stock_on_hand where branch_id = :b"),
                      {"b": nueva}).scalar() == 40
    assert db.execute(text("select count(*) from inventory_movements where branch_id = :b"),
                      {"b": nueva}).scalar() == 1
    assert db.execute(text("select count(*) from product_branch_status where branch_id = :b"),
                      {"b": nueva}).scalar() == 1


def test_no_duplica_lo_ya_mudado(db, mudada):
    datos, r = mudada
    org_n = r["organization_id"]
    antes = db.execute(text("select count(*) from sales_documents where organization_id = :o"),
                       {"o": org_n}).scalar()
    productos = db.execute(text("select count(*) from products where organization_id = :o"),
                           {"o": org_n}).scalar()
    agregar_sucursales(db, datos, org_destino=org_n, sucursales={TAZA})
    assert db.execute(text("select count(*) from sales_documents where organization_id = :o"),
                      {"o": org_n}).scalar() == antes + 2
    assert db.execute(text("select count(*) from products where organization_id = :o"),
                      {"o": org_n}).scalar() == productos
    assert db.execute(text("select count(*) from branches where organization_id = :o"),
                      {"o": org_n}).scalar() == 3
    assert db.execute(text("select count(*) from users u join user_organizations uo on uo.user_id = u.id "
                           "where uo.organization_id = :o"), {"o": org_n}).scalar() == 3


def test_liga_a_la_cajera_que_ya_existia(db, mudada):
    datos, r = mudada
    org_n = r["organization_id"]
    fer = r["usuarios"]["fernanda_rmz"]
    assert db.execute(text("select branch_id from users where id = :u"), {"u": fer}).scalar() is None
    a = agregar_sucursales(db, datos, org_destino=org_n, sucursales={TAZA})
    nueva = a["sucursales"][TAZA]
    fila = db.execute(text("select branch_id, password_hash from users where id = :u"), {"u": fer}).one()
    assert fila.branch_id == nueva and verify_pin("clave-de-siempre", fila.password_hash)
    venta = next(d for d in datos["tablas"]["sales_documents"] if d["branch_id"] == TAZA)
    assert db.get(SalesDocument, venta["id"]).seller_id == fer
    emp = db.execute(text("select base_branch_id, organization_id from employees where user_id = :u"),
                     {"u": fer}).one()
    assert emp == (nueva, org_n)
    assert a["usuarios_ligados"] == {"fernanda_rmz": fer}


def test_trae_el_catalogo_que_falta(db, mudada):
    datos, r = mudada
    org_n = r["organization_id"]
    var = _nueva_pieza(datos)
    a = agregar_sucursales(db, datos, org_destino=org_n, sucursales={TAZA})
    assert db.execute(text("select organization_id from product_variants where id = :v"),
                      {"v": var}).scalar() == org_n
    assert db.execute(text("select qty_on_hand from stock_on_hand where variant_id = :v and branch_id = :b"),
                      {"v": var, "b": a["sucursales"][TAZA]}).scalar() == 6
    assert a["insertadas"]["products"] == 1


def test_repetir_bloquea(db, mudada):
    datos, r = mudada
    org_n = r["organization_id"]
    agregar_sucursales(db, datos, org_destino=org_n, sucursales={TAZA})
    with pytest.raises(Bloqueo, match="ya existe"):
        agregar_sucursales(db, datos, org_destino=org_n, sucursales={TAZA})


def test_caja_abierta_bloquea_salvo_permiso(db, mudada):
    datos, r = mudada
    caja = next(c for c in datos["tablas"]["cash_sessions"] if c["id"] == CAJA_TAZA)
    caja.update(status="OPEN", closed_at=None)
    with pytest.raises(Bloqueo, match="cajas abiertas"):
        agregar_sucursales(db, datos, org_destino=r["organization_id"], sucursales={TAZA})
    a = agregar_sucursales(db, datos, org_destino=r["organization_id"], sucursales={TAZA},
                           permitir_cajas_abiertas=True)
    assert any("cajas abiertas" in x for x in a["avisos"])


def test_catalogo_de_otra_org_bloquea(db, mudada, org):
    """Un UUID que existe pero en otro cliente no se puede reusar."""
    datos, r = mudada
    from app.models import Product

    ajeno = Product(name="Ajeno", organization_id=org.id)
    db.add(ajeno)
    db.flush()
    datos["tablas"]["products"].append({"id": ajeno.id, "name": "Ajeno", "is_active": True,
                                        "has_variants": False, "organization_id": datos["org_id"]})
    with pytest.raises(Bloqueo, match="otra organizacion"):
        agregar_sucursales(db, datos, org_destino=r["organization_id"], sucursales={TAZA})


def test_vendedor_desconocido_bloquea(db, mudada):
    datos, r = mudada
    venta = next(d for d in datos["tablas"]["sales_documents"] if d["branch_id"] == TAZA)
    venta["seller_id"] = 424242
    with pytest.raises(Bloqueo, match="apunta fuera"):
        agregar_sucursales(db, datos, org_destino=r["organization_id"], sucursales={TAZA})


def test_verificacion_que_no_cuadra_bloquea(db, mudada, monkeypatch):
    import scripts.import_rmazh_org as mod

    datos, r = mudada
    original = mod.verificar_sucursales

    def con_venta_de_mas(db_, datos_, *a, **kw):
        alterados = copy.deepcopy(datos_)
        venta = next(d for d in alterados["tablas"]["sales_documents"] if d["branch_id"] == TAZA)
        venta["total_amount"] = "999"
        return original(db_, alterados, *a, **kw)

    monkeypatch.setattr(mod, "verificar_sucursales", con_venta_de_mas)
    with pytest.raises(Bloqueo, match="suma de ventas"):
        agregar_sucursales(db, datos, org_destino=r["organization_id"], sucursales={TAZA})


def test_precios_nuevos_de_variantes_ya_mudadas_no_viajan(db, mudada):
    """rmazh recrea los escalones al editar (UUID nuevo): en Atlas ONE ya existen y ahi manda Atlas."""
    datos, r = mudada
    t = datos["tablas"]
    vieja = t["product_variants"][0]["id"]
    t.setdefault("product_prices", []).append({"id": str(uuid.uuid4()), "variant_id": vieja,
                                               "price_name": "Mayoreo", "min_quantity": "3",
                                               "unit_price": "100", "organization_id": datos["org_id"]})
    var = _nueva_pieza(datos)
    t["product_prices"].append({"id": str(uuid.uuid4()), "variant_id": var, "price_name": "Mayoreo",
                                "min_quantity": "3", "unit_price": "180", "organization_id": datos["org_id"]})
    a = agregar_sucursales(db, datos, org_destino=r["organization_id"], sucursales={TAZA})
    assert a["insertadas"]["product_prices"] == 1
    assert db.execute(text("select count(*) from product_prices where variant_id = :v"), {"v": vieja}).scalar() == 0
    assert any("product_prices" in x and "ya mudadas" in x for x in a["avisos"])
