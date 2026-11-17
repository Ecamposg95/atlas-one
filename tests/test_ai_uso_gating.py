"""Uso diario de tokens y gate estricto del módulo ai."""
import pytest
from fastapi import APIRouter, Depends, HTTPException

from app.models.modules import Module, OrganizationModule
from app.modules.ai.gating import exigir_modulo_ai
from app.modules.ai.models import AiUsoDiario
from app.modules.ai.uso import registrar_uso, verificar_cupo


def test_registrar_uso_acumula_en_el_dia(db, org):
    registrar_uso(db, org.id, 10, 5)
    registrar_uso(db, org.id, 3, 2)
    filas = db.query(AiUsoDiario).filter_by(organization_id=org.id).all()
    assert len(filas) == 1
    assert (filas[0].tokens_entrada, filas[0].tokens_salida, filas[0].llamadas) == (13, 7, 2)


def test_verificar_cupo_429_al_pasar_el_tope(db, org, monkeypatch):
    monkeypatch.setenv("AI_TOKENS_DIA_ORG", "100")
    verificar_cupo(db, org.id)  # sin uso: pasa
    registrar_uso(db, org.id, 60, 40)
    with pytest.raises(HTTPException) as e:
        verificar_cupo(db, org.id)
    assert e.value.status_code == 429


@pytest.fixture()
def ruta_de_prueba(app):
    r = APIRouter()

    @r.get("/api/_t1_gate_ai")
    def _ruta(org_id: int = Depends(exigir_modulo_ai)):
        return {"org_id": org_id}

    # Al principio: el comodín de la SPA ya está montado y se comería la ruta.
    n = len(app.router.routes)
    app.include_router(r)
    nuevas = app.router.routes[n:]
    del app.router.routes[n:]
    app.router.routes[0:0] = nuevas
    yield
    app.router.routes[:] = [x for x in app.router.routes if getattr(x, "path", "") != "/api/_t1_gate_ai"]


def test_gate_403_admin_sin_modulo(client, auth_admin_a, ruta_de_prueba):
    r = client.get("/api/_t1_gate_ai", headers=auth_admin_a)
    assert r.status_code == 403
    assert "complemento" in r.json()["detail"] and "SCALE" not in r.json()["detail"]


def test_gate_pasa_con_modulo_habilitado(client, db, org, auth_admin_a, ruta_de_prueba):
    if not db.query(Module).filter_by(key="ai").first():
        db.add(Module(key="ai", name="Asistente IA"))
        db.flush()
    db.add(OrganizationModule(organization_id=org.id, module_key="ai", is_enabled=True))
    db.flush()
    r = client.get("/api/_t1_gate_ai", headers=auth_admin_a)
    assert r.status_code == 200
    assert r.json()["org_id"] == org.id
