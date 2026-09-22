"""Quién puede qué en el CRM de clientes.

Hasta 2026-09-22 `app/modules/customers/router.py` no tenía NINGÚN candado:
ni de módulo ni de rol. Cualquier sesión válida de la organización hacía el
CRUD completo de clientes —incluido borrar— y registraba abonos.

El reparto que se prueba aquí:

  * consultar, dar de alta y editar  → cajero en adelante
  * borrar y registrar abono         → administrador / dueño
  * todo el router                   → solo con el módulo `crm` encendido

`require_module` exime a ADMINISTRADOR/DUEÑO (app/core/permissions.py), así
que el gating por módulo solo se puede observar desde una cuenta de mostrador.
"""
from decimal import Decimal

import pytest

from app.models.modules import Module, OrganizationModule
from app.models.organization import Organization
from app.modules.customers.models import Customer


@pytest.fixture()
def crm_encendido(db, org):
    """La organización tiene el módulo `crm` (lo trae el preset de mostrador)."""
    if db.query(Module).filter(Module.key == "crm").first() is None:
        db.add(Module(key="crm", name="CRM"))
        db.flush()
    ya = db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key == "crm",
    ).first()
    if ya is None:
        db.add(OrganizationModule(organization_id=org.id, module_key="crm", is_enabled=True))
    else:
        ya.is_enabled = True
    db.commit()
    return org


@pytest.fixture()
def cliente(db, org):
    c = Customer(
        name="Clienta de mostrador", phone="4491110000",
        organization_id=org.id, has_credit=True,
        credit_limit=Decimal("1000"), current_balance=Decimal("300"),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@pytest.fixture()
def cliente_ajeno(db):
    otra = Organization(name="Otra tienda", status="ACTIVE")
    db.add(otra)
    db.flush()
    c = Customer(name="Cliente de otra tienda", organization_id=otra.id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _h(auth, org):
    return {**auth, "X-Organization-ID": str(org.id)}


# ── La cajera consulta y edita ───────────────────────────────────────────────

def test_la_cajera_ve_la_lista_de_clientes(client, org, auth_cajero_a, crm_encendido, cliente):
    r = client.get("/api/customers/", headers=_h(auth_cajero_a, org))
    assert r.status_code == 200, r.text
    assert [c["name"] for c in r.json()] == ["Clienta de mostrador"]


def test_la_cajera_busca_desde_el_carrito_del_pos(client, org, auth_cajero_a, crm_encendido, cliente):
    """El botón "Cliente" del POS usa `GET /api/customers/?search=` — el mismo
    endpoint de la lista. Si se cerrara, la cajera no podría ponerle nombre a
    una venta."""
    r = client.get("/api/customers/", params={"search": "mostrador", "limit": 10},
                   headers=_h(auth_cajero_a, org))
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1


def test_la_cajera_ve_la_ficha_el_estado_de_cuenta_y_los_kpis(
    client, org, auth_cajero_a, crm_encendido, cliente
):
    h = _h(auth_cajero_a, org)
    assert client.get(f"/api/customers/{cliente.id}", headers=h).status_code == 200
    assert client.get(f"/api/customers/{cliente.id}/statement", headers=h).status_code == 200
    assert client.get(f"/api/customers/{cliente.id}/unpaid-documents", headers=h).status_code == 200
    assert client.get("/api/customers/stats", headers=h).status_code == 200
    assert client.get(f"/api/customers/{cliente.id}/pdf-statement", headers=h).status_code == 200


def test_la_cajera_da_de_alta_y_edita(client, db, org, auth_cajero_a, crm_encendido):
    h = _h(auth_cajero_a, org)
    alta = client.post("/api/customers/", json={"name": "Clienta nueva", "phone": "4492220000"},
                       headers=h)
    assert alta.status_code == 200, alta.text
    nuevo_id = alta.json()["id"]

    edicion = client.put(f"/api/customers/{nuevo_id}", json={"phone": "4493330000"}, headers=h)
    assert edicion.status_code == 200, edicion.text
    assert edicion.json()["phone"] == "4493330000"


# ── Borrar es del administrador; abonar es de quien cobra ────────────────────

def test_la_cajera_no_puede_borrar_un_cliente(client, db, org, auth_cajero_a, crm_encendido, cliente):
    r = client.delete(f"/api/customers/{cliente.id}", headers=_h(auth_cajero_a, org))
    assert r.status_code == 403, r.text
    db.refresh(cliente)
    assert cliente.is_active is True, "el cliente no se pudo haber dado de baja"


def test_la_cajera_si_registra_un_abono(client, db, org, auth_cajero_a, crm_encendido, cliente):
    """Recibir un abono es cobrar, y cobrar es del mostrador.

    El endpoint exige caja abierta a quien cobra cuando el abono es en
    efectivo, asi que dejarlo solo en manos del administrador —que desde el
    2026-09-22 ya no tiene turno— dejaba a la tienda sin forma de recibir un
    pago de credito.
    """
    r = client.post(f"/api/customers/{cliente.id}/pay",
                    json={"amount": "100", "method": "TRANSFER"},
                    headers=_h(auth_cajero_a, org))
    assert r.status_code == 200, r.text
    db.refresh(cliente)
    assert cliente.current_balance == Decimal("200")


def test_el_gerente_abona_pero_no_borra(client, db, org, auth_gerente_a, crm_encendido, cliente):
    h = _h(auth_gerente_a, org)
    assert client.delete(f"/api/customers/{cliente.id}", headers=h).status_code == 403
    assert client.post(f"/api/customers/{cliente.id}/pay",
                       json={"amount": "100", "method": "TRANSFER"}, headers=h).status_code == 200


def test_el_administrador_registra_el_abono(client, db, org, auth_admin, cliente):
    r = client.post(f"/api/customers/{cliente.id}/pay",
                    json={"amount": "100", "method": "TRANSFER"},
                    headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text
    db.refresh(cliente)
    assert cliente.current_balance == Decimal("200")


def test_el_administrador_borra_al_cliente_sin_deuda(client, db, org, auth_admin, cliente):
    cliente.current_balance = Decimal("0")
    db.commit()
    r = client.delete(f"/api/customers/{cliente.id}", headers=_h(auth_admin, org))
    assert r.status_code == 200, r.text
    db.refresh(cliente)
    assert cliente.is_active is False


# ── Sin el módulo `crm` no hay pantalla de clientes ──────────────────────────

def test_sin_el_modulo_crm_todo_el_router_responde_403(client, org, auth_cajero_a, cliente):
    """Sin la fila en `organization_modules` (la que siembra el preset y el
    backfill de scripts/init_presets_v2.py) la cajera no ve nada del CRM."""
    h = _h(auth_cajero_a, org)
    assert client.get("/api/customers/", headers=h).status_code == 403
    assert client.get("/api/customers/stats", headers=h).status_code == 403
    assert client.get(f"/api/customers/{cliente.id}", headers=h).status_code == 403
    assert client.post("/api/customers/", json={"name": "X"}, headers=h).status_code == 403
    assert client.put(f"/api/customers/{cliente.id}", json={"phone": "1"}, headers=h).status_code == 403
    assert client.delete(f"/api/customers/{cliente.id}", headers=h).status_code == 403


def test_el_modulo_apagado_a_proposito_tambien_cierra_el_crm(client, db, org, auth_cajero_a, crm_encendido, cliente):
    om = db.query(OrganizationModule).filter(
        OrganizationModule.organization_id == org.id,
        OrganizationModule.module_key == "crm",
    ).one()
    om.is_enabled = False
    db.commit()
    assert client.get("/api/customers/", headers=_h(auth_cajero_a, org)).status_code == 403


# ── El aislamiento por organización sigue en pie ─────────────────────────────

def test_la_cajera_no_ve_al_cliente_de_otra_tienda(client, org, auth_cajero_a, crm_encendido, cliente, cliente_ajeno):
    h = _h(auth_cajero_a, org)
    lista = client.get("/api/customers/", headers=h)
    assert lista.status_code == 200
    assert [c["id"] for c in lista.json()] == [cliente.id]
    assert client.get(f"/api/customers/{cliente_ajeno.id}", headers=h).status_code == 404


def test_el_administrador_tampoco_toca_al_cliente_de_otra_tienda(client, org, auth_admin, cliente_ajeno):
    h = _h(auth_admin, org)
    assert client.get(f"/api/customers/{cliente_ajeno.id}", headers=h).status_code == 404
    assert client.delete(f"/api/customers/{cliente_ajeno.id}", headers=h).status_code == 404
    assert client.post(f"/api/customers/{cliente_ajeno.id}/pay",
                       json={"amount": "10", "method": "TRANSFER"}, headers=h).status_code == 404
