# tests/test_plan_en_contexto.py
"""El plan comercial viaja con el contexto del usuario y con las capacidades de la org.

El frontend recorta el menú con `plan.clave`; `plan.nombre` es lo que se muestra
en la tarjeta de inicio. NULL o clave desconocida = FREE (misma regla que
plans.obtener_plan), para que una fila vieja nunca deje a nadie sin menú.
"""
import pytest

from app.models.modules import Module, OrganizationModule
from app.modules.tenants.models import IndustryType


def _cabeceras(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


def _con_core(db, org):
    if db.query(Module).filter(Module.key == "core").first() is None:
        db.add(Module(key="core", name="Core"))
        db.flush()
    db.add(OrganizationModule(organization_id=org.id, module_key="core", is_enabled=True))
    db.flush()


@pytest.mark.parametrize("guardado, clave, nombre", [
    (None, "FREE", "ONE FREE"),
    ("FREE", "FREE", "ONE FREE"),
    ("ULTRA_PLUS", "ULTRA_PLUS", "ULTRA+"),
    ("XYZ", "FREE", "ONE FREE"),
])
def test_me_context_trae_el_plan(client, db, auth_admin, org, guardado, clave, nombre):
    org.plan = guardado
    db.flush()
    r = client.get("/api/users/me/context", headers=_cabeceras(auth_admin, org))
    assert r.status_code == 200, r.text
    assert r.json()["plan"] == {"clave": clave, "nombre": nombre}


def test_org_capabilities_trae_el_plan(client, db, auth_admin, org):
    org.industry_type = IndustryType.ATLAS_POS
    org.plan = "PRO"
    _con_core(db, org)
    r = client.get("/api/org/capabilities/", headers=_cabeceras(auth_admin, org))
    assert r.status_code == 200, r.text
    assert r.json()["plan"] == {"clave": "PRO", "nombre": "ONE PRO"}


def test_el_resto_del_contexto_no_cambia(client, db, auth_admin, org):
    cuerpo = client.get("/api/users/me/context", headers=_cabeceras(auth_admin, org)).json()
    for clave in ("user", "organization", "preset", "enabled_modules", "capacidades", "plan"):
        assert clave in cuerpo
