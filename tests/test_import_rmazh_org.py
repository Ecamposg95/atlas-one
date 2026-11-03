"""Mudanza de una organizacion de rmazh con historial (scripts/import_rmazh_org.py).

La exportacion de prueba usa a proposito los mismos ids enteros que ya ocupa la
org de las fixtures (organizacion, sucursal, usuario, caja): en Atlas ONE esas
secuencias son de todos los clientes y la mudanza tiene que renumerarlas sin
tocar lo ajeno.
"""
import base64
import copy
import gzip
import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.security.passwords import get_password_hash, verify_pin
from app.models import SalesDocument
from app.models.cash import CashSession
from app.models.organization import Branch
from app.services.cash_reconciliation import compute_expected_cash
from app.utils.folios import get_next_folio
from scripts.import_rmazh_org import Bloqueo, importar, leer_exportacion

HASH = get_password_hash("clave-de-siempre")


def _exportacion(org_id: int, suc_id: int, usr_id: int, caja_id: int, caja_status="CLOSED"):
    venta1, venta2 = str(uuid.uuid4()), str(uuid.uuid4())
    prod, var = str(uuid.uuid4()), str(uuid.uuid4())
    hq = suc_id + 1
    cajera = usr_id + 1
    t = "2026-10-30T15:00:00+00:00"
    return {
        "org_id": org_id,
        "exportado": "2026-11-03T00:00:00+00:00",
        "tablas": {
            "organization": [{"id": org_id, "name": "Novedades Origen", "status": "ACTIVE", "plan": "FREE",
                              "industry_type": "DATAXPOS", "timezone": "America/Mexico_City",
                              "is_active": True, "hq_branch_id": None, "ticket_footer_suffix": "x"}],
            "branches": [
                {"id": hq, "name": "HQ - Origen", "branch_type": "HQ", "can_sell": False, "is_active": True,
                 "is_headquarters": True, "organization_id": org_id, "ticket_font": "mono"},
                {"id": suc_id, "name": "Tienda 60", "branch_type": "STORE", "can_sell": True, "is_active": True,
                 "is_headquarters": False, "printer_name": "bixolon80", "organization_id": org_id},
            ],
            "users": [
                {"id": usr_id, "username": "america_rmz", "full_name": "America", "role": "ADMINISTRADOR",
                 "platform_role": "NONE", "is_active": True, "branch_id": hq, "password_hash": HASH,
                 "reprint_pin_hash": get_password_hash("4321"), "created_at": t},
                {"id": cajera, "username": "vanessa_rmz", "full_name": "Vanessa", "role": "CAJERO",
                 "platform_role": "NONE", "is_active": True, "branch_id": suc_id, "password_hash": HASH,
                 "reprint_pin_hash": None, "created_at": t},
            ],
            "user_organizations": [
                {"user_id": usr_id, "organization_id": org_id, "org_role": "MEMBER", "is_active": True},
                {"user_id": cajera, "organization_id": org_id, "org_role": "MEMBER", "is_active": True},
            ],
            "products": [{"id": prod, "name": "Taza", "is_active": True, "has_variants": False,
                          "organization_id": org_id, "created_by_user_id": 999999}],
            "product_variants": [{"id": var, "product_id": prod, "sku": "TZ-1", "variant_name": "Estándar",
                                  "price": "120.00", "cost": "60.00", "organization_id": org_id}],
            "product_branch_status": [{"id": str(uuid.uuid4()), "variant_id": var, "branch_id": suc_id,
                                       "is_active_pos": True, "is_visible": True, "organization_id": org_id}],
            "stock_on_hand": [{"id": 77, "branch_id": suc_id, "variant_id": var, "qty_on_hand": "8",
                               "is_active": True, "organization_id": org_id}],
            "cash_sessions": [{"id": caja_id, "user_id": cajera, "branch_id": suc_id, "opened_at": t,
                               "closed_at": None if caja_status == "OPEN" else "2026-10-30T23:00:00+00:00",
                               "opening_balance": "500", "status": caja_status, "organization_id": org_id}],
            "cash_audit_log": [{"id": 5, "ts": t, "session_id": caja_id, "organization_id": org_id,
                                "branch_id": suc_id, "user_id": 999998, "event_type": "SESSION_CLOSED",
                                "amount": "740", "related_table": "cash_sessions", "related_id": str(caja_id),
                                "payload_json": {"expected": 740.0}}],
            "sales_documents": [
                {"id": venta1, "doc_type": "INVOICE", "status": "PAID", "branch_id": suc_id, "seller_id": cajera,
                 "series": "A", "folio": 14467, "subtotal": "120", "tax_amount": "0", "total_amount": "120",
                 "cash_session_id": caja_id, "change_given": "0", "organization_id": org_id,
                 "created_at": t, "reprint_count": 2},
                {"id": venta2, "doc_type": "INVOICE", "status": "PAID", "branch_id": suc_id, "seller_id": cajera,
                 "series": "A", "folio": 14468, "subtotal": "240", "tax_amount": "0", "total_amount": "240",
                 "cash_session_id": caja_id, "change_given": "0", "organization_id": org_id, "created_at": t},
            ],
            "sales_lines": [
                {"id": str(uuid.uuid4()), "document_id": venta1, "variant_id": var, "description": "Taza",
                 "quantity": "1", "unit_price": "120", "total_line": "120", "organization_id": None,
                 "price_tier_name": "Menudeo"},
                {"id": str(uuid.uuid4()), "document_id": venta2, "variant_id": var, "description": "Taza",
                 "quantity": "2", "unit_price": "120", "total_line": "240", "organization_id": org_id},
            ],
            "payments": [
                {"id": str(uuid.uuid4()), "sales_document_id": venta1, "created_by_id": cajera,
                 "amount": "120", "method": "CASH", "organization_id": org_id, "created_at": t},
                {"id": str(uuid.uuid4()), "sales_document_id": venta2, "created_by_id": cajera,
                 "amount": "240", "method": "CARD", "organization_id": org_id, "created_at": t},
            ],
            "inventory_movements": [{"id": 9, "branch_id": suc_id, "variant_id": var, "user_id": cajera,
                                     "movement_type": "SALE_OUT", "qty_change": "-3", "qty_before": "11",
                                     "qty_after": "8", "reference": "Venta POS (Nueva)",
                                     "organization_id": org_id, "created_at": t}],
        },
    }


@pytest.fixture()
def caja_ajena(db, org, branch_a, cajero_a):
    """Una caja de otra org: su id es el mismo que trae la exportacion."""
    c = CashSession(user_id=cajero_a.id, branch_id=branch_a.id, opening_balance=Decimal("0"),
                    status="CLOSED", organization_id=org.id)
    db.add(c)
    db.flush()
    return c


@pytest.fixture()
def datos(org, branch_a, cajero_a, caja_ajena):
    return _exportacion(org.id, branch_a.id, cajero_a.id, caja_ajena.id)


def _importar(db, datos, **kw):
    return importar(db, datos, nombre="Novedades America", plan="PRO", giro="ATLAS_POS", **kw)


def test_renumera_ids_enteros_y_conserva_uuids(db, org, branch_a, cajero_a, caja_ajena, datos):
    r = _importar(db, datos)
    nueva = r["organization_id"]
    assert nueva != org.id
    tienda = r["sucursales"][branch_a.id]
    assert tienda != branch_a.id
    # Lo ajeno no se toca
    assert db.get(Branch, branch_a.id).organization_id == org.id
    assert db.get(CashSession, caja_ajena.id).organization_id == org.id

    venta = datos["tablas"]["sales_documents"][0]["id"]
    sd = db.get(SalesDocument, venta)  # UUID conservado
    assert sd.organization_id == nueva
    assert sd.branch_id == tienda
    assert sd.seller_id == r["usuarios"]["vanessa_rmz"]
    caja_nueva = sd.cash_session_id
    assert caja_nueva != caja_ajena.id
    assert db.get(CashSession, caja_nueva).branch_id == tienda

    # La partida sin organization_id en rmazh queda ligada a la org nueva
    assert db.execute(text("select count(*) from sales_lines where organization_id = :o"), {"o": nueva}).scalar() == 2
    # Los pagos heredan la caja de su venta
    cajas = db.execute(text("select distinct cash_session_id from payments where organization_id = :o"),
                       {"o": nueva}).scalars().all()
    assert cajas == [caja_nueva]
    # La bitacora apunta a la caja nueva; su autor (superadmin de rmazh) se anula
    log = db.execute(text("select session_id, related_id, user_id from cash_audit_log where organization_id = :o"),
                     {"o": nueva}).one()
    assert log.session_id == caja_nueva and log.related_id == str(caja_nueva) and log.user_id is None
    # Matriz de la org
    hq = r["sucursales"][branch_a.id + 1]
    assert db.execute(text("select hq_branch_id, plan, name from organization where id = :o"),
                      {"o": nueva}).one() == (hq, "PRO", "Novedades America")
    assert any("cash_audit_log.user_id" in a for a in r["avisos"])
    assert any("products.created_by_user_id" in a for a in r["avisos"])


def test_folio_sigue_la_numeracion_de_rmazh(db, datos, branch_a):
    r = _importar(db, datos)
    assert get_next_folio(db, r["sucursales"][branch_a.id], "A") == 14469


def test_usuarios_entran_con_su_contrasena_y_pin(db, datos):
    r = _importar(db, datos)
    fila = db.execute(text("select u.password_hash, u.reprint_pin_hash, uo.org_role from users u "
                           "join user_organizations uo on uo.user_id = u.id where u.id = :u"),
                      {"u": r["usuarios"]["america_rmz"]}).one()
    assert verify_pin("clave-de-siempre", fila.password_hash)
    assert verify_pin("4321", fila.reprint_pin_hash)
    assert fila.org_role == "ADMIN"
    cajera = db.execute(text("select org_role from user_organizations where user_id = :u"),
                        {"u": r["usuarios"]["vanessa_rmz"]}).scalar()
    assert cajera == "MEMBER"


def test_el_corte_importado_da_el_mismo_esperado(db, datos, branch_a):
    r = _importar(db, datos)
    venta = datos["tablas"]["sales_documents"][0]["id"]
    caja = db.get(CashSession, db.get(SalesDocument, venta).cash_session_id)
    # fondo 500 + efectivo 120; la tarjeta no entra al cajon
    assert compute_expected_cash(db, caja).expected == Decimal("620")


def test_caja_abierta_bloquea_salvo_en_ensayo(db, org, branch_a, cajero_a, caja_ajena):
    datos = _exportacion(org.id, branch_a.id, cajero_a.id, caja_ajena.id, caja_status="OPEN")
    with pytest.raises(Bloqueo, match="cajas abiertas"):
        _importar(db, datos)
    r = _importar(db, datos, permitir_cajas_abiertas=True)
    assert any("cajas abiertas" in a for a in r["avisos"])


def test_username_repetido_bloquea(db, datos, cajero_a):
    datos["tablas"]["users"][1]["username"] = cajero_a.username
    with pytest.raises(Bloqueo, match="ya existe en Atlas ONE"):
        _importar(db, datos)


def test_org_con_el_mismo_nombre_bloquea(db, datos):
    _importar(db, datos)
    otra = copy.deepcopy(datos)
    with pytest.raises(Bloqueo, match="ya existe una organizacion"):
        _importar(db, otra)


def test_referencia_fuera_de_la_org_bloquea(db, datos):
    datos["tablas"]["sales_documents"][0]["seller_id"] = 424242
    with pytest.raises(Bloqueo, match="apunta fuera de la organizacion"):
        _importar(db, datos)


def test_columna_de_referencia_sin_traduccion_bloquea(db, datos, monkeypatch):
    """Un entero ajeno copiado en silencio ligaria la fila a otro cliente."""
    import scripts.import_rmazh_org as mod

    sin_vendedor = {k: v for k, v in mod.REFERENCIAS.items() if k != "seller_id"}
    monkeypatch.setattr(mod, "REFERENCIAS", sin_vendedor)
    with pytest.raises(Bloqueo, match="sales_documents.seller_id: columna de referencia sin traduccion"):
        _importar(db, datos)


def test_columnas_que_solo_tiene_rmazh_no_viajan(db, datos):
    datos["tablas"]["stock_on_hand"][0]["warehouse_id"] = 3
    r = _importar(db, datos)
    assert any("stock_on_hand" in a and "warehouse_id" in a for a in r["avisos"])
    assert any("sales_documents" in a and "reprint_count" in a for a in r["avisos"])


def test_verificacion_que_no_cuadra_bloquea(db, datos, monkeypatch):
    import scripts.import_rmazh_org as mod

    original = mod.verificar

    def con_venta_de_mas(db_, datos_, *a, **kw):
        alterados = copy.deepcopy(datos_)
        alterados["tablas"]["sales_documents"][0]["total_amount"] = "999"
        return original(db_, alterados, *a, **kw)

    monkeypatch.setattr(mod, "verificar", con_venta_de_mas)
    with pytest.raises(Bloqueo, match="suma de ventas"):
        _importar(db, datos)


def test_lee_la_salida_de_railway_ssh_con_ruido(tmp_path, datos):
    crudo = base64.b64encode(gzip.compress(json.dumps(datos).encode())).decode()
    partido = "\n".join(crudo[i:i + 76] for i in range(0, len(crudo), 76))
    archivo = tmp_path / "salida.txt"
    archivo.write_text(f"Using SSH key...\nCONTEO branches 2\n###RMAZH_ORG_B64###\n{partido}\n###FIN###\nwarning: x\n")
    assert leer_exportacion(str(archivo))["tablas"]["branches"][1]["name"] == "Tienda 60"


def test_solo_una_sucursal_viaja(db, datos, branch_a):
    from scripts.import_rmazh_org import filtrar_sucursales

    hq, tienda = branch_a.id + 1, branch_a.id
    otra = 888888
    t = datos["tablas"]
    t["branches"].append({"id": otra, "name": "Taza", "branch_type": "STORE", "can_sell": True,
                          "is_active": True, "is_headquarters": False, "organization_id": datos["org_id"]})
    t["users"].append({"id": 777777, "username": "fernanda_rmz", "full_name": "Fernanda", "role": "CAJERO",
                       "platform_role": "NONE", "is_active": True, "branch_id": otra, "password_hash": HASH})
    t["user_organizations"].append({"user_id": 777777, "organization_id": datos["org_id"],
                                    "org_role": "MEMBER", "is_active": True})
    t["stock_on_hand"].append(dict(t["stock_on_hand"][0], id=78, branch_id=otra, qty_on_hand="5"))
    r = _importar(db, filtrar_sucursales(datos, {hq, tienda}))
    nueva = r["organization_id"]
    assert set(r["sucursales"]) == {hq, tienda}
    assert db.execute(text("select coalesce(sum(qty_on_hand),0) from stock_on_hand where organization_id=:o"),
                      {"o": nueva}).scalar() == 8
    fer = db.execute(text("select is_active, branch_id from users where username='fernanda_rmz'")).one()
    assert fer == (False, None)


def _venta_posterior(datos, folio, cuando="2026-11-03T19:00:00+00:00"):
    t = datos["tablas"]
    base = t["sales_documents"][0]
    var = t["product_variants"][0]["id"]
    vid = str(uuid.uuid4())
    t["sales_documents"].append(dict(base, id=vid, folio=folio, total_amount="120", subtotal="120",
                                     created_at=cuando))
    t["sales_lines"].append({"id": str(uuid.uuid4()), "document_id": vid, "variant_id": var, "description": "Taza",
                             "quantity": "1", "unit_price": "120", "total_line": "120",
                             "organization_id": datos["org_id"]})
    t["payments"].append({"id": str(uuid.uuid4()), "sales_document_id": vid, "created_by_id": base["seller_id"],
                          "amount": "120", "method": "CASH", "organization_id": datos["org_id"], "created_at": cuando})
    t["inventory_movements"].append(dict(t["inventory_movements"][0], id=10, qty_change="-1", qty_before="8",
                                         qty_after="7", created_at=cuando))
    return vid


def test_fusion_trae_solo_lo_nuevo_y_es_idempotente(db, datos, branch_a):
    import datetime as dt
    from scripts.fusionar_rmazh_ventas import fusionar

    r = _importar(db, datos)
    org_n, tienda = r["organization_id"], r["sucursales"][branch_a.id]
    vid = _venta_posterior(datos, 14469)
    # Una venta de una sucursal que sigue en rmazh no viaja
    datos["tablas"]["sales_documents"].append(dict(datos["tablas"]["sales_documents"][0], id=str(uuid.uuid4()),
                                                   branch_id=555555, folio=1))
    datos["tablas"]["sales_lines"].append(dict(datos["tablas"]["sales_lines"][1], id=str(uuid.uuid4()),
                                               document_id=datos["tablas"]["sales_documents"][-1]["id"]))
    corte = dt.datetime(2026, 11, 3, 18, 25, tzinfo=dt.timezone.utc)
    f = fusionar(db, datos, org=org_n, desde=corte)
    assert f["traidas"]["sales_documents"] == 1 and f["traidas"]["inventory_movements"] == 1
    venta = db.get(SalesDocument, vid)
    caja = db.get(SalesDocument, datos["tablas"]["sales_documents"][0]["id"]).cash_session_id
    assert venta.branch_id == tienda and venta.cash_session_id == caja and venta.folio == 14469
    assert db.execute(text("select qty_on_hand from stock_on_hand where branch_id=:b"), {"b": tienda}).scalar() == 7
    assert compute_expected_cash(db, db.get(CashSession, caja)).expected == Decimal("740")
    otra = fusionar(db, datos, org=org_n, desde=corte)
    assert otra["traidas"].get("sales_documents", 0) == 0
    assert otra["traidas"].get("inventory_movements", 0) == 0
    assert otra["existencias_ajustadas"] == 0
    assert db.execute(text("select qty_on_hand from stock_on_hand where branch_id=:b"), {"b": tienda}).scalar() == 7


def test_fusion_renumera_folio_ya_usado_en_atlas(db, datos, branch_a):
    import datetime as dt
    from scripts.fusionar_rmazh_ventas import fusionar

    r = _importar(db, datos)
    org_n = r["organization_id"]
    vid = _venta_posterior(datos, 14468)  # 14468 ya existe (importado)
    f = fusionar(db, datos, org=org_n, desde=dt.datetime(2026, 11, 3, 18, 25, tzinfo=dt.timezone.utc))
    venta = db.get(SalesDocument, vid)
    assert venta.folio == 14469 and "[rmazh A-14468]" in (venta.notes or "")
    assert any("ya usado" in a for a in f["avisos"])
