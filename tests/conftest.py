"""
Shared fixtures for Atlas API tests.
Uses SQLite in-memory DB for speed (~30s full suite).
"""
import os
import pytest
from decimal import Decimal
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Force SQLite before any app imports
os.environ["DATABASE_URL"] = "sqlite:///file::memory:?cache=shared"

# TrustedHostMiddleware (app/main.py) valida el header Host; el TestClient de
# Starlette manda "testserver". Se permite vía la misma env var extensible que
# usa producción — sin ella toda la suite responde 400 "Invalid host header".
os.environ.setdefault("ALLOWED_HOSTS", "testserver")

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

# parked_tickets.cart_json uses Postgres JSONB; SQLite needs plain JSON.
# Test-only compiler — does not affect prod.
@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kw):
    return "JSON"

from app.core.database import Base, get_db
from app.models.users import User, UserOrganization, Role, PlatformRole
from app.models.organization import Organization, Branch, BranchType
from app.models.products import Product, ProductVariant, ProductBranchStatus
from app.models.inventory import StockOnHand
from app.models.cash import CashSession, CashSessionStatus, CashMovement
from app.models.sales import SalesDocument, DocumentStatus, Payment, PaymentMethod
from app.core.security import get_password_hash, create_access_token

# ── Engine & Session ──────────────────────────────────────────────────────────
TEST_ENGINE = create_engine(
    "sqlite:///file::memory:?cache=shared",
    connect_args={"check_same_thread": False},
)

@event.listens_for(TEST_ENGINE, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    # El DB en memoria es compartido (cache=shared) entre el TEST_ENGINE y el
    # SessionLocal del app (startup/subscribers). Bajo carga esas conexiones
    # contienden por el write-lock → "database is locked" espurio (flaky). Con
    # busy_timeout la conexión ESPERA el lock en vez de fallar de inmediato.
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()
    # Los reportes agrupan por dia local con `timezone(zona, ts)`, que es de
    # Postgres (app/routers/reports.py::_mx). SQLite no la trae. Shim de solo
    # pruebas -- el SQL de produccion queda identico al que corre en Postgres.
    dbapi_connection.create_function("timezone", 2, _pg_timezone)
    # `sales-by-hour` agrupa con `to_char(ts, 'HH24')`, tambien de Postgres.
    dbapi_connection.create_function("to_char", 2, _pg_to_char)


def _pg_to_char(ts, fmt):
    """Shim de `to_char(ts, formato)` de Postgres para SQLite.

    Solo cubre 'HH24' -- el unico formato que usan los reportes. Cualquier otro
    revienta a proposito: un shim que devuelve algo plausible para un formato
    que no implementa haria pasar pruebas contra un SQL que en produccion
    devuelve otra cosa.
    """
    if ts is None:
        return None
    dt = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
    if fmt == "HH24":
        return f"{dt.hour:02d}"
    raise NotImplementedError(f"to_char no implementa el formato {fmt!r} en pruebas")


def _pg_timezone(zone, ts):
    """Equivalente de `timezone(zona, timestamptz)`: pasa el instante UTC
    almacenado a hora local de `zona` y lo devuelve sin offset, como Postgres."""
    if ts is None:
        return None
    dt = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(zone)).replace(tzinfo=None).isoformat(sep=" ")

TestSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


# ── App with overridden DB ───────────────────────────────────────────────────
@pytest.fixture(scope="session")
def app():
    """Create FastAPI app with test DB override."""
    from app.main import app as _app

    def _get_test_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    _app.dependency_overrides[get_db] = _get_test_db
    return _app


@pytest.fixture(scope="session")
def _create_tables(app):
    """Create all tables once per test session."""
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


@pytest.fixture()
def db(_create_tables):
    """Per-test DB session. Rolls back after each test for isolation."""
    connection = TEST_ENGINE.connect()
    transaction = connection.begin()
    session = TestSession(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(app, db):
    """HTTP test client with auth-ready DB session."""
    from httpx import ASGITransport, AsyncClient
    from fastapi.testclient import TestClient

    def _get_test_db_override():
        yield db

    app.dependency_overrides[get_db] = _get_test_db_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides[get_db] = lambda: (yield db)


# ── Seed Data ─────────────────────────────────────────────────────────────────
@pytest.fixture()
def org(db):
    """Test organization."""
    o = Organization(name="Test Org", status="ACTIVE")
    db.add(o)
    db.flush()
    return o


@pytest.fixture()
def branch_a(db, org):
    """Branch A (STORE) — the CAJERO's branch."""
    b = Branch(
        name="Sucursal A", branch_type=BranchType.STORE,
        can_sell=True, is_active=True, organization_id=org.id,
    )
    db.add(b)
    db.flush()
    return b


@pytest.fixture()
def branch_b(db, org):
    """Branch B (STORE) — a different branch."""
    b = Branch(
        name="Sucursal B", branch_type=BranchType.STORE,
        can_sell=True, is_active=True, organization_id=org.id,
    )
    db.add(b)
    db.flush()
    return b


@pytest.fixture()
def hq_branch(db, org):
    """HQ branch."""
    b = Branch(
        name="HQ", branch_type=BranchType.HQ,
        can_sell=False, is_active=True, is_headquarters=True,
        organization_id=org.id,
    )
    db.add(b)
    db.flush()
    return b


def _make_user(db, org, branch, username, role, platform_role=PlatformRole.NONE):
    u = User(
        username=username, password_hash=get_password_hash("test1234"),
        role=role, branch_id=branch.id if branch else None,
        is_active=True, platform_role=platform_role,
    )
    db.add(u)
    db.flush()
    assoc = UserOrganization(
        user_id=u.id, organization_id=org.id,
        org_role="MEMBER", is_active=True,
    )
    db.add(assoc)
    db.flush()
    return u


@pytest.fixture()
def cajero_a(db, org, branch_a):
    """CAJERO user at Branch A."""
    return _make_user(db, org, branch_a, "cajero_a", Role.CAJERO)


@pytest.fixture()
def gerente_a(db, org, branch_a):
    """GERENTE user at Branch A."""
    return _make_user(db, org, branch_a, "gerente_a", Role.GERENTE)


@pytest.fixture()
def vendedor_sin_sucursal(db, org):
    """VENDEDOR sin sucursal asignada.

    `User.branch_id` es nullable y la propia caja contempla el caso
    ("Tu usuario no tiene una sucursal asignada", app/routers/cash.py). Un rol
    asi no es de oficina central: no debe ver la organizacion entera.
    """
    return _make_user(db, org, None, "vendedor_sin_sucursal", Role.VENDEDOR)


@pytest.fixture()
def auth_vendedor_sin_sucursal(vendedor_sin_sucursal):
    return _auth_header(vendedor_sin_sucursal)


@pytest.fixture()
def admin_a(db, org, branch_a):
    """ADMINISTRADOR asignado a la Sucursal A — el que cobra en mostrador.

    Registrar un abono (`POST /api/customers/{id}/pay`) exige administrador o
    dueño desde 2026-09-22, pero el guard de efectivo NO hace excepción de rol:
    quien cobra efectivo desde una sucursal necesita su propia caja abierta.
    Las pruebas de atribución de abonos cobran con este usuario (antes lo hacía
    `cajero_a`, que ya no puede).
    """
    return _make_user(db, org, branch_a, "admin_a", Role.ADMINISTRADOR)


@pytest.fixture()
def auth_admin_a(admin_a):
    return _auth_header(admin_a)


@pytest.fixture()
def admin_user(db, org, hq_branch):
    """ADMINISTRADOR user (HQ, sees all)."""
    return _make_user(db, org, hq_branch, "admin_test", Role.ADMINISTRADOR)


@pytest.fixture()
def superadmin(db, org, hq_branch):
    """SUPERADMIN platform user."""
    return _make_user(db, org, hq_branch, "superadmin_test", Role.ADMINISTRADOR, PlatformRole.SUPERADMIN)


def _auth_header(user):
    """Generate Bearer token for a test user."""
    token = create_access_token({"sub": user.username})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def auth_cajero_a(cajero_a):
    return _auth_header(cajero_a)


@pytest.fixture()
def auth_gerente_a(gerente_a):
    return _auth_header(gerente_a)


@pytest.fixture()
def auth_admin(admin_user):
    return _auth_header(admin_user)


@pytest.fixture()
def auth_superadmin(superadmin):
    return _auth_header(superadmin)


# ── Product Fixtures ──────────────────────────────────────────────────────────
def _make_product(db, org, name, sku, price, branches_active=None):
    """
    Create a product + variant + optionally enable in specific branches.
    branches_active: list of (branch_id, is_active_pos) tuples
    """
    p = Product(name=name, organization_id=org.id, is_active=True)
    db.add(p)
    db.flush()

    v = ProductVariant(
        product_id=p.id, sku=sku, price=Decimal(str(price)),
        cost=Decimal(str(price)) * Decimal("0.6"),
        organization_id=org.id,
    )
    db.add(v)
    db.flush()

    if branches_active:
        for branch_id, active in branches_active:
            pbs = ProductBranchStatus(
                variant_id=v.id, branch_id=branch_id,
                organization_id=org.id,
                is_active_pos=active, is_visible=active,
            )
            db.add(pbs)
            soh = StockOnHand(
                variant_id=v.id, branch_id=branch_id,
                organization_id=org.id, qty_on_hand=Decimal("100"),
                is_active=True,
            )
            db.add(soh)

    db.flush()
    return p, v


@pytest.fixture()
def products_setup(db, org, branch_a, branch_b):
    """
    Creates 3 products:
    - product_a: enabled ONLY in branch A
    - product_b: enabled ONLY in branch B
    - product_both: enabled in BOTH branches
    """
    pa, va = _make_product(db, org, "Producto A", "SKU-A", 100,
                           [(branch_a.id, True)])
    pb, vb = _make_product(db, org, "Producto B", "SKU-B", 200,
                           [(branch_b.id, True)])
    pc, vc = _make_product(db, org, "Producto Ambos", "SKU-BOTH", 150,
                           [(branch_a.id, True), (branch_b.id, True)])

    db.flush()
    return {
        "product_a": (pa, va),
        "product_b": (pb, vb),
        "product_both": (pc, vc),
    }
