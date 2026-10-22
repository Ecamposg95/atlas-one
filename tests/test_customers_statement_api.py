"""Endpoint /api/customers/{id}/pdf-statement: auth, org-scoping, PDF válido."""
import re
import zlib
from datetime import datetime
from decimal import Decimal

import pytest

from app.modules.customers.models import Customer, CustomerLedgerEntry
from app.models.organization import Organization


def _pdf_text(pdf_bytes: bytes) -> bytes:
    """Extrae y descomprime los streams del PDF para poder buscar texto plano.

    Con fuentes TTF embebidas el texto se codifica como glyph IDs; los tests
    que necesitan leer texto deben forzar el fallback a Helvetica (core font,
    texto plano en el stream) vía monkeypatch de `_FONTS_DIR`.
    """
    chunks = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf_bytes, re.S):
        datos = m.group(1)
        # Si el último byte del stream comprimido es 0x0d, el `\r?` de arriba se lo
        # come y `zlib.decompress` revienta por "truncated stream" (1 de cada 256
        # PDFs: el byte es parte del adler32). `decompressobj` devuelve lo que
        # alcanzó a inflar sin exigir el cierre, que es todo el contenido.
        try:
            chunks.append(zlib.decompressobj().decompress(datos))
        except Exception:
            chunks.append(datos)
    return b"".join(chunks)


@pytest.fixture()
def customer_a(db, org):
    c = Customer(name="Cliente Uno", phone="4491112233",
                 organization_id=org.id, current_balance=Decimal("100.00"))
    db.add(c)
    db.commit()
    db.refresh(c)
    db.add(CustomerLedgerEntry(customer_id=c.id, amount=Decimal("100.00"),
                               description="Venta a crédito", organization_id=org.id))
    db.commit()
    return c


@pytest.fixture()
def other_org_customer(db):
    other = Organization(name="Otra Org", status="ACTIVE")
    db.add(other)
    db.commit()
    c = Customer(name="Ajeno", organization_id=other.id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_pdf_statement_requires_auth(client, customer_a):
    r = client.get(f"/api/customers/{customer_a.id}/pdf-statement")
    assert r.status_code == 401


def test_pdf_statement_cross_org_is_404(client, auth_admin, other_org_customer):
    r = client.get(f"/api/customers/{other_org_customer.id}/pdf-statement",
                   headers=auth_admin)
    assert r.status_code == 404


def test_pdf_statement_returns_pdf(client, auth_admin, customer_a):
    r = client.get(f"/api/customers/{customer_a.id}/pdf-statement", headers=auth_admin)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")


def test_pdf_statement_contains_org_and_customer(
    client, auth_admin, customer_a, org, monkeypatch, tmp_path
):
    import app.modules.customers.statement_pdf as spdf
    monkeypatch.setattr(spdf, "_FONTS_DIR", tmp_path / "no-fonts")  # fallback Helvetica → texto plano

    r = client.get(f"/api/customers/{customer_a.id}/pdf-statement", headers=auth_admin)
    assert r.status_code == 200
    text = _pdf_text(r.content)
    assert len(text) > 0
    assert org.name.encode("latin-1") in text
    assert b"Cliente Uno" in text


def test_pdf_statement_start_date_compacts_previous_into_saldo_anterior(
    client, auth_admin, org, db, monkeypatch, tmp_path
):
    import app.modules.customers.statement_pdf as spdf
    monkeypatch.setattr(spdf, "_FONTS_DIR", tmp_path / "no-fonts")  # fallback Helvetica → texto plano

    customer = Customer(name="Cliente Historico", organization_id=org.id,
                         current_balance=Decimal("150.00"))
    db.add(customer)
    db.commit()
    db.refresh(customer)

    # Movimiento viejo (antes de start_date) + reciente (dentro del periodo).
    # server_default solo aplica si no se pasa created_at explícito.
    db.add(CustomerLedgerEntry(customer_id=customer.id, amount=Decimal("100.00"),
                               description="Venta antigua", organization_id=org.id,
                               created_at=datetime(2026, 1, 10, 12, 0)))
    db.add(CustomerLedgerEntry(customer_id=customer.id, amount=Decimal("50.00"),
                               description="Venta reciente", organization_id=org.id,
                               created_at=datetime(2026, 8, 1, 12, 0)))
    db.commit()

    r = client.get(
        f"/api/customers/{customer.id}/pdf-statement",
        params={"start_date": "2026-06-01"},
        headers=auth_admin,
    )
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")
    text = _pdf_text(r.content)
    assert len(text) > 0
    # "Saldo anterior" solo se imprime cuando previous_balance != 0: su
    # presencia prueba que el movimiento de 2026-01-10 se compactó ahí en
    # vez de listarse como fila del periodo.
    assert "Saldo anterior".encode("latin-1") in text
