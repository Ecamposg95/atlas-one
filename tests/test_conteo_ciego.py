"""Conteo ciego opcional por organización (2026-11-21).

Nace encendido; solo ADMINISTRADOR/DUEÑO lo apaga desde Empresa, y la interfaz
lo lee de `/users/me/context`.
"""


def _ctx(client, auth, org):
    return client.get("/api/users/me/context",
                      headers={**auth, "X-Organization-ID": str(org.id)}).json()


def _put(client, auth, org, cuerpo):
    return client.put("/api/organization/", json=cuerpo,
                      headers={**auth, "X-Organization-ID": str(org.id)})


def test_nace_encendido(client, auth_admin, org, admin_user):
    assert _ctx(client, auth_admin, org)["conteo_ciego"] is True


def test_el_admin_lo_apaga_y_el_contexto_lo_refleja(client, db, auth_admin, org, admin_user):
    r = _put(client, auth_admin, org, {"conteo_ciego": False})
    assert r.status_code == 200, r.text
    assert r.json()["conteo_ciego"] is False
    assert _ctx(client, auth_admin, org)["conteo_ciego"] is False


def test_null_no_toca_el_ajuste(client, db, auth_admin, org, admin_user):
    r = _put(client, auth_admin, org, {"conteo_ciego": None})
    assert r.status_code == 200, r.text
    db.refresh(org)
    assert org.conteo_ciego is True


def test_la_cajera_no_puede_apagarlo(client, db, auth_cajero_a, org, cajero_a):
    r = _put(client, auth_cajero_a, org, {"conteo_ciego": False})
    assert r.status_code == 403, r.text
    db.refresh(org)
    assert org.conteo_ciego is True
    assert _ctx(client, auth_cajero_a, org)["conteo_ciego"] is True
