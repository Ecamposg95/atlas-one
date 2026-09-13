"""La matriz de un negocio de una sola sucursal vende si el caller lo pide.

Antes, cualquier PUT sobre la matriz (incluso cambiar el telefono) forzaba
can_sell=False y dejaba el POS sin catalogo (produccion, 2026-09-13).
"""


def _hq_id(client, auth_admin):
    r = client.get("/api/branches/", headers=auth_admin)
    assert r.status_code == 200, r.text
    hq = [b for b in r.json() if b.get("branch_type") == "HQ" or b.get("is_headquarters")]
    assert hq, r.json()
    return hq[0]["id"]


def test_put_explicito_can_sell_true_en_matriz_se_respeta(client, auth_admin):
    bid = _hq_id(client, auth_admin)
    r = client.put(f"/api/branches/{bid}", json={"can_sell": True}, headers=auth_admin)
    assert r.status_code == 200, r.text
    assert r.json()["can_sell"] is True
    assert r.json()["is_headquarters"] is True


def test_put_de_otro_campo_no_apaga_la_venta_de_la_matriz(client, auth_admin):
    bid = _hq_id(client, auth_admin)
    client.put(f"/api/branches/{bid}", json={"can_sell": True}, headers=auth_admin)
    r = client.put(f"/api/branches/{bid}", json={"phone": "7221234567"}, headers=auth_admin)
    assert r.status_code == 200, r.text
    assert r.json()["can_sell"] is True, "editar otro campo no debe apagar la venta"


def test_matriz_sin_can_sell_explicito_sigue_sin_vender_por_defecto(client, auth_admin):
    bid = _hq_id(client, auth_admin)
    client.put(f"/api/branches/{bid}", json={"can_sell": False}, headers=auth_admin)
    r = client.put(f"/api/branches/{bid}", json={"branch_type": "HQ"}, headers=auth_admin)
    assert r.status_code == 200, r.text
    assert r.json()["can_sell"] is False
