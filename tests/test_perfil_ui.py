"""Modo básico: el perfil de interfaz sale del plan y la plataforma lo puede forzar.

FREE explícito → básico; el resto (incluido plan NULL o desconocido) → completo. `organization.perfil_ui` = 'basico'/'completo' manda; NULL o
'auto' = derivar. Solo la plataforma lo cambia: el PUT de tenant lo descarta.
"""
from types import SimpleNamespace

import pytest

from app.services.perfil_ui import normalizar_perfil_ui, perfil_efectivo
from scripts import railway_init


def _org(plan=None, perfil=None):
    return SimpleNamespace(plan=plan, perfil_ui=perfil)


@pytest.mark.parametrize("plan, perfil, esperado", [
    ("FREE", None, "basico"),
    ("FREE", "auto", "basico"),
    (None, None, "completo"),          # sin plan: no cambiar la interfaz sin decidirlo
    ("Demo", None, "completo"),        # desconocido: idem (ruling, distinto a los topes)
    ("START", None, "completo"),
    ("ULTRA_PLUS", None, "completo"),
    ("FREE", "completo", "completo"),  # demo de una FREE
    ("ULTRA_PLUS", "basico", "basico"),  # una de paga que quiere lo simple
    ("FREE", " COMPLETO ", "completo"),
    ("PRO", "raro", "completo"),       # valor raro guardado = auto
])
def test_perfil_efectivo(plan, perfil, esperado):
    assert perfil_efectivo(_org(plan, perfil)) == esperado


def test_sin_organizacion_es_completo():
    assert perfil_efectivo(None) == "completo"


def test_normalizar_perfil_ui():
    assert normalizar_perfil_ui(None) is None
    assert normalizar_perfil_ui(" Basico ") == "basico"
    assert normalizar_perfil_ui("auto") == "auto"
    with pytest.raises(ValueError, match="auto, basico, completo"):
        normalizar_perfil_ui("simple")


@pytest.mark.parametrize("columna", ["perfil_ui", "umbral_poca_existencia"])
def test_el_arranque_migra_las_columnas(columna):
    declaradas = {(t, c) for t, c, _ in railway_init.COLUMN_MIGRATIONS}
    assert ("organization", columna) in declaradas


def _contexto(client, auth, org):
    r = client.get("/api/users/me/context", headers={**auth, "X-Organization-ID": str(org.id)})
    assert r.status_code == 200, r.text
    return r.json()


def test_contexto_de_una_free_es_basico(client, db, auth_admin, org):
    org.plan = "FREE"
    db.flush()
    assert _contexto(client, auth_admin, org)["perfil_ui"] == "basico"


def test_contexto_de_una_de_paga_es_completo(client, db, auth_admin, org):
    org.plan = "ULTRA_PLUS"
    db.flush()
    assert _contexto(client, auth_admin, org)["perfil_ui"] == "completo"


def test_contexto_de_una_free_forzada_a_completo(client, db, auth_admin, org):
    """Review Focus #4: la plataforma fuerza completo y todo vuelve."""
    org.plan = "FREE"
    org.perfil_ui = "completo"
    db.flush()
    assert _contexto(client, auth_admin, org)["perfil_ui"] == "completo"


def test_la_plataforma_fuerza_y_regresa_a_auto(client, db, auth_superadmin, org):
    r = client.put(f"/api/platform/organizations/{org.id}", json={"perfil_ui": "completo"}, headers=auth_superadmin)
    assert r.status_code == 200, r.text
    assert r.json()["perfil_ui"] == "completo"
    r = client.put(f"/api/platform/organizations/{org.id}", json={"perfil_ui": "auto"}, headers=auth_superadmin)
    assert r.status_code == 200, r.text
    db.refresh(org)
    assert org.perfil_ui == "auto"


def test_la_plataforma_rechaza_un_perfil_desconocido(client, auth_superadmin, org):
    r = client.put(f"/api/platform/organizations/{org.id}", json={"perfil_ui": "simple"}, headers=auth_superadmin)
    assert r.status_code == 422
    assert "auto, basico, completo" in r.text


def test_el_tenant_no_cambia_su_perfil(client, db, auth_admin, org, admin_user):
    org.plan = "FREE"
    db.commit()
    r = client.put(
        "/api/organization/",
        json={"name": "Mi tienda", "perfil_ui": "completo"},
        headers={**auth_admin, "X-Organization-ID": str(org.id)},
    )
    assert r.status_code == 200, r.text
    db.refresh(org)
    assert org.perfil_ui is None
    assert org.name == "Mi tienda"


def test_el_tenant_guarda_el_umbral(client, db, auth_admin, org, admin_user):
    r = client.put(
        "/api/organization/",
        json={"umbral_poca_existencia": 5},
        headers={**auth_admin, "X-Organization-ID": str(org.id)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["umbral_poca_existencia"] == 5


def test_umbral_negativo_es_422(client, auth_admin, org, admin_user):
    r = client.put(
        "/api/organization/",
        json={"umbral_poca_existencia": -1},
        headers={**auth_admin, "X-Organization-ID": str(org.id)},
    )
    assert r.status_code == 422
