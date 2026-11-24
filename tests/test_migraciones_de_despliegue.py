"""Las columnas de esta rama tienen que existir en la base al arrancar.

Las cuatro rutas de despliegue (`Procfile`, `nixpacks.toml`, `railway.json`,
`Dockerfile`) corren un solo comando antes de uvicorn:
`python scripts/railway_init.py`. Nada invoca los `scripts/migrate_*.py`
sueltos. Si una columna nueva no esta en las listas de migracion de
`railway_init`, el codigo nuevo arranca contra el esquema viejo y la primera
consulta que la mencione revienta con `UndefinedColumn` (cobros, cortes y
reportes en 500).

Es la regla 3 de CLAUDE.md: las migraciones de esquema van en
`scripts/railway_init.py`.
"""
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect, text

from scripts import railway_init


# ── Las columnas estan enganchadas al arranque ───────────────────────────────

@pytest.mark.parametrize("tabla, columna", [
    ("payments", "cash_session_id"),
    ("cash_movements", "created_by_user_id"),
])
def test_el_arranque_migra_la_columna(tabla, columna):
    declaradas = {(t, c) for t, c, _ in railway_init.COLUMN_MIGRATIONS}
    assert (tabla, columna) in declaradas, (
        f"{tabla}.{columna} no esta en railway_init.COLUMN_MIGRATIONS: en un "
        f"despliegue por push la columna nunca se crea"
    )


@pytest.mark.parametrize("indice", [
    "ix_payments_cash_session_id",
    "ix_cash_movements_created_by",
])
def test_el_arranque_crea_el_indice(indice):
    declarados = {nombre for nombre, _ in railway_init.INDEX_MIGRATIONS}
    assert indice in declarados


# ── La aplicacion de las migraciones es idempotente y sirve en SQLite ────────

def _engine_con_tablas():
    """Base de juguete con las tablas justas, sin las columnas nuevas."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE cash_sessions (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        conn.execute(text("""
            CREATE TABLE sales_documents (
                id VARCHAR(36) PRIMARY KEY,
                cash_session_id INTEGER
            )
        """))
        conn.execute(text("""
            CREATE TABLE payments (
                id VARCHAR(36) PRIMARY KEY,
                sales_document_id VARCHAR(36),
                amount NUMERIC(10, 2)
            )
        """))
        conn.execute(text("""
            CREATE TABLE cash_movements (
                id INTEGER PRIMARY KEY,
                session_id INTEGER
            )
        """))
    return engine


def test_aplicar_migraciones_de_columna_es_idempotente():
    engine = _engine_con_tablas()
    migraciones = (
        railway_init.MIGRACIONES_PAYMENTS_CASH_SESSION
        + railway_init.MIGRACIONES_CASH_MOVEMENT_AUTHOR
    )

    with engine.connect() as conn:
        aplicadas = railway_init.aplicar_migraciones_de_columna(conn, migraciones)
    assert aplicadas == ["payments.cash_session_id", "cash_movements.created_by_user_id"]

    # Segunda corrida: no hay nada que hacer y no truena (cada deploy la repite).
    with engine.connect() as conn:
        assert railway_init.aplicar_migraciones_de_columna(conn, migraciones) == []

    inspector = inspect(engine)
    assert "cash_session_id" in {c["name"] for c in inspector.get_columns("payments")}
    assert "created_by_user_id" in {c["name"] for c in inspector.get_columns("cash_movements")}


def test_aplicar_migraciones_de_indice_es_idempotente():
    engine = _engine_con_tablas()
    migraciones = (
        railway_init.MIGRACIONES_PAYMENTS_CASH_SESSION
        + railway_init.MIGRACIONES_CASH_MOVEMENT_AUTHOR
    )
    indices = (
        railway_init.INDICES_PAYMENTS_CASH_SESSION
        + railway_init.INDICES_CASH_MOVEMENT_AUTHOR
    )
    with engine.connect() as conn:
        railway_init.aplicar_migraciones_de_columna(conn, migraciones)
        railway_init.aplicar_migraciones_de_indice(conn, indices)
        railway_init.aplicar_migraciones_de_indice(conn, indices)

    nombres = {ix["name"] for ix in inspect(engine).get_indexes("payments")}
    assert "ix_payments_cash_session_id" in nombres


# ── El relleno historico ─────────────────────────────────────────────────────

def test_el_relleno_hereda_la_caja_del_documento_sin_pisar_atribuciones():
    """Hasta esta rama el pago se creaba en la misma transaccion que la venta,
    asi que la caja del documento SI era la que recibio el dinero. El relleno
    nunca pisa una atribucion ya escrita ni inventa sesion donde el documento
    no tiene."""
    engine = _engine_con_tablas()
    with engine.connect() as conn:
        railway_init.aplicar_migraciones_de_columna(
            conn, railway_init.MIGRACIONES_PAYMENTS_CASH_SESSION)
        conn.commit()

    with engine.begin() as conn:
        conn.execute(text("INSERT INTO cash_sessions (id) VALUES (1), (2)"))
        conn.execute(text(
            "INSERT INTO sales_documents (id, cash_session_id) VALUES "
            "('doc-con-caja', 1), ('doc-sin-caja', NULL)"))
        conn.execute(text(
            "INSERT INTO payments (id, sales_document_id, amount, cash_session_id) VALUES "
            "('p-historico', 'doc-con-caja', 100, NULL),"      # hereda la 1
            "('p-ya-atribuido', 'doc-con-caja', 50, 2),"        # se respeta la 2
            "('p-sin-caja', 'doc-sin-caja', 30, NULL)"          # se queda en NULL
        ))

    rellenados, pendientes = railway_init.rellenar_payments_cash_session(engine)
    assert (rellenados, pendientes) == (1, 1)

    with engine.connect() as conn:
        filas = dict(conn.execute(text(
            "SELECT id, cash_session_id FROM payments")).fetchall())
    assert filas == {"p-historico": 1, "p-ya-atribuido": 2, "p-sin-caja": None}

    # Repetirlo (cada deploy) no mueve nada.
    assert railway_init.rellenar_payments_cash_session(engine)[0] == 0


# ── Indices unicos de dinero ─────────────────────────────────────────────────
# `uq_sales_org_client_uuid` (cobro doble) y `uq_sale_return_pending_per_sale`
# (devolucion duplicada) vivian solo en scripts manuales: una base nueva o
# restaurada arrancaba sin ellos.

def _engine_de_dinero():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE sales_documents (
                id VARCHAR(36) PRIMARY KEY, organization_id INTEGER,
                client_uuid VARCHAR(64), deleted_at DATETIME
            )
        """))
        conn.execute(text("""
            CREATE TABLE sale_returns (
                id VARCHAR(36) PRIMARY KEY, sale_id VARCHAR(36),
                status VARCHAR, deleted_at DATETIME
            )
        """))
    return engine


def _indices(engine, tabla):
    return {ix["name"] for ix in inspect(engine).get_indexes(tabla)}


def test_el_arranque_declara_los_indices_unicos_de_dinero():
    nombres = {n for n, *_ in railway_init.INDICES_UNICOS_DE_DINERO}
    assert nombres == {"uq_sales_org_client_uuid", "uq_sale_return_pending_per_sale"}
    assert ("sales_documents", "client_uuid") in {
        (t, c) for t, c, _ in railway_init.COLUMN_MIGRATIONS}


def test_run_migrations_llama_a_los_indices_de_dinero():
    import inspect as _inspect
    assert "asegurar_indices_unicos_de_dinero(engine)" in _inspect.getsource(
        railway_init.run_migrations)


def test_indices_de_dinero_se_crean_y_son_idempotentes():
    engine = _engine_de_dinero()
    assert railway_init.asegurar_indices_unicos_de_dinero(engine) == []
    assert railway_init.asegurar_indices_unicos_de_dinero(engine) == []
    assert "uq_sales_org_client_uuid" in _indices(engine, "sales_documents")
    assert "uq_sale_return_pending_per_sale" in _indices(engine, "sale_returns")

    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO sales_documents (id, organization_id, client_uuid) VALUES ('a', 1, 'x')"))
        # Otra organizacion, sin client_uuid y borrada: no chocan.
        conn.execute(text(
            "INSERT INTO sales_documents (id, organization_id, client_uuid) VALUES "
            "('b', 2, 'x'), ('c', 1, NULL), ('d', 1, NULL)"))
        conn.execute(text(
            "INSERT INTO sale_returns (id, sale_id, status) VALUES "
            "('r1', 'a', 'PENDING'), ('r2', 'a', 'APPROVED'), ('r3', 'a', 'REJECTED')"))
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO sales_documents (id, organization_id, client_uuid) VALUES ('e', 1, 'x')"))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO sale_returns (id, sale_id, status) VALUES ('r4', 'a', 'PENDING')"))


def test_duplicados_preexistentes_avisan_y_no_tumban_el_arranque(capsys, caplog):
    engine = _engine_de_dinero()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO sales_documents (id, organization_id, client_uuid) VALUES "
            "('a', 1, 'repetido'), ('b', 1, 'repetido')"))

    with caplog.at_level("WARNING"):
        pendientes = railway_init.asegurar_indices_unicos_de_dinero(engine)

    # El que tiene duplicados no se crea; el otro si, y nada revienta.
    assert pendientes == ["uq_sales_org_client_uuid"]
    assert "uq_sales_org_client_uuid" not in _indices(engine, "sales_documents")
    assert "uq_sale_return_pending_per_sale" in _indices(engine, "sale_returns")
    assert "uq_sales_org_client_uuid NO se creo" in capsys.readouterr().out
    assert any("uq_sales_org_client_uuid" in r.getMessage() for r in caplog.records)

    # Resueltos los duplicados, el siguiente arranque lo crea.
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sales_documents WHERE id = 'b'"))
    assert railway_init.asegurar_indices_unicos_de_dinero(engine) == []
    assert "uq_sales_org_client_uuid" in _indices(engine, "sales_documents")


def test_una_tabla_ausente_tampoco_tumba_el_arranque():
    engine = create_engine("sqlite://")
    assert sorted(railway_init.asegurar_indices_unicos_de_dinero(engine)) == [
        "uq_sale_return_pending_per_sale", "uq_sales_org_client_uuid"]
