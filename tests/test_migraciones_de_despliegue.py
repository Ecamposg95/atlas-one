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
