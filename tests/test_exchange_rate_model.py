"""`exchange_rates` es global (sin organization_id) y admite una sola fila por
moneda y dia; la politica por inquilino vive en columnas de `organization`."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.exchange_rate import ExchangeRate
from app.models.organization import Organization


def test_la_tabla_no_tiene_organization_id():
    # Es un dato publico compartido por todos los inquilinos. Si alguien le
    # cuelga organization_id, la tabla deja de ser lo que el diseño dice y
    # habria que filtrar por org en cada lectura.
    assert "organization_id" not in ExchangeRate.__table__.columns


def test_guarda_el_fix_del_dia(db):
    db.add(ExchangeRate(currency="USD", rate_date=date(2026, 9, 17),
                        rate=Decimal("18.2345"), source="banxico"))
    db.flush()
    fila = db.query(ExchangeRate).filter(ExchangeRate.rate_date == date(2026, 9, 17)).one()
    assert fila.rate == Decimal("18.2345")
    assert fila.currency == "USD"
    assert fila.source == "banxico"


def test_un_solo_renglon_por_moneda_y_dia(db):
    db.add(ExchangeRate(currency="USD", rate_date=date(2026, 9, 17), rate=Decimal("18.20")))
    db.flush()
    db.add(ExchangeRate(currency="USD", rate_date=date(2026, 9, 17), rate=Decimal("18.90")))
    with pytest.raises(IntegrityError):
        db.flush()


def test_la_organizacion_arranca_apagada(db):
    # Neutralidad: ninguna de las organizaciones vivas ve nada nuevo.
    o = Organization(name="Sin dolares", status="ACTIVE")
    db.add(o)
    db.flush()
    db.refresh(o)
    assert o.usd_rate_mode == "off"
    assert o.usd_rate_manual is None
    assert Decimal(str(o.usd_rate_margin)) == Decimal("0")
