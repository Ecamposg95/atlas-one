"""Una sola sesion de caja ABIERTA por (usuario, sucursal).

Hallazgo §5 de docs/audits/2026-09-01-comparacion-atlas-rmazh.md: el endpoint
de apertura hacia check-then-insert sin bloqueo ni restriccion unica, asi que
dos aperturas concurrentes del mismo cajero creaban DOS sesiones abiertas y a
partir de ahi el corte cuadraba mal.

Los locks (`with_for_update`, `pg_advisory_xact_lock`) son no-op en SQLite, que
es donde corren estas pruebas: aqui se verifica la garantia que SI se puede
ejercitar sin Postgres — el 409 de la segunda apertura secuencial y el indice
unico parcial, que es la guarda dura que sobrevive aunque alguien omita el
chequeo previo.
"""
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.cash import CashSession, CashSessionStatus


def _abrir(client, auth, org, fondo="500.00"):
    return client.post(
        "/api/cash/open",
        json={"opening_balance": fondo},
        headers={**auth, "X-Organization-ID": str(org.id)},
    )


class TestAperturaSecuencial:
    def test_la_primera_apertura_crea_la_sesion(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        resp = _abrir(client, auth_cajero_a, org)
        assert resp.status_code == 200, resp.text
        assert Decimal(str(resp.json()["opening_balance"])) == Decimal("500.00")

    def test_la_segunda_apertura_responde_409(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        assert _abrir(client, auth_cajero_a, org).status_code == 200
        segunda = _abrir(client, auth_cajero_a, org, fondo="1200.00")
        assert segunda.status_code == 409, segunda.text
        assert "ya tienes una caja abierta" in segunda.json()["detail"].lower()

    def test_la_segunda_apertura_no_crea_otra_sesion(self, client, db, org, branch_a, cajero_a, auth_cajero_a):
        _abrir(client, auth_cajero_a, org)
        _abrir(client, auth_cajero_a, org, fondo="1200.00")
        abiertas = db.query(CashSession).filter(
            CashSession.user_id == cajero_a.id,
            CashSession.branch_id == branch_a.id,
            CashSession.status == CashSessionStatus.OPEN,
        ).count()
        assert abiertas == 1


class TestIndiceUnicoParcial:
    """La guarda dura: aunque alguien omita el chequeo previo, la base no
    admite dos sesiones abiertas del mismo cajero en la misma sucursal."""

    def _sesion(self, org, branch, user, status=CashSessionStatus.OPEN):
        return CashSession(
            user_id=user.id, branch_id=branch.id, organization_id=org.id,
            opening_balance=Decimal("0"), status=status,
        )

    def test_la_base_rechaza_la_segunda_abierta(self, db, org, branch_a, cajero_a):
        db.add(self._sesion(org, branch_a, cajero_a))
        db.flush()
        db.add(self._sesion(org, branch_a, cajero_a))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_una_cerrada_no_estorba_a_la_siguiente(self, db, org, branch_a, cajero_a):
        """El indice es PARCIAL: el historial de cortes cerrados no se toca."""
        db.add(self._sesion(org, branch_a, cajero_a, status=CashSessionStatus.CLOSED))
        db.add(self._sesion(org, branch_a, cajero_a, status=CashSessionStatus.CLOSED))
        db.flush()
        db.add(self._sesion(org, branch_a, cajero_a))
        db.flush()  # no debe reventar

    def test_el_mismo_cajero_puede_abrir_en_otra_sucursal(self, db, org, branch_a, branch_b, cajero_a):
        db.add(self._sesion(org, branch_a, cajero_a))
        db.add(self._sesion(org, branch_b, cajero_a))
        db.flush()  # no debe reventar

    def test_dos_cajeros_pueden_abrir_en_la_misma_sucursal(self, db, org, branch_a, cajero_a, gerente_a):
        db.add(self._sesion(org, branch_a, cajero_a))
        db.add(self._sesion(org, branch_a, gerente_a))
        db.flush()  # no debe reventar


class TestCarreraSimulada:
    """Las dos peticiones ven la caja cerrada y las dos intentan insertar.

    Es lo que pasa de verdad en Postgres cuando dos PCs del mismo cajero abren
    a la vez y el chequeo previo no alcanza a ver la fila de la otra. Aqui se
    reproduce neutralizando ese chequeo: lo que queda por verificar es que el
    conflicto de la base sale como 409 y no como un 500.
    """

    def test_el_conflicto_de_la_base_sale_como_409(
        self, client, db, org, branch_a, cajero_a, auth_cajero_a, monkeypatch
    ):
        assert _abrir(client, auth_cajero_a, org).status_code == 200

        from app.routers import cash as cash_router
        monkeypatch.setattr(cash_router, "_sesion_abierta", lambda *a, **k: None)

        segunda = _abrir(client, auth_cajero_a, org, fondo="1200.00")
        assert segunda.status_code == 409, segunda.text
        # Nada mas se puede aseverar aqui: el rollback del endpoint deshace
        # tambien la transaccion de la prueba (ver la fixture `db`), asi que
        # las filas sembradas por las fixtures ya no existen.


def test_el_indice_tambien_se_crea_en_bases_existentes():
    """`create_all` no toca tablas que ya existen, asi que la base de produccion
    solo recibe el indice si railway_init lo crea explicitamente."""
    fuente = Path("scripts/railway_init.py").read_text(encoding="utf-8")
    assert "uq_cash_sessions_open_user_branch" in fuente
    assert "CREATE UNIQUE INDEX IF NOT EXISTS" in fuente
    assert "WHERE status = 'OPEN'" in fuente
