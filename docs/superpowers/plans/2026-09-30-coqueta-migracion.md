# Mudanza de Novedades Coqueta a Atlas ONE — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar de alta a Novedades Coqueta en Atlas ONE con su catálogo, escalones, existencias y sus dos usuarios (misma contraseña), arrancando los folios en 1464, sin escribir nada en rmazh.

**Architecture:** Dos scripts nuevos en `scripts/` (importador del xlsx que exporta rmazh y traspaso de usuarios por hash), copiados del patrón de `scripts/import_datax_export.py` (validar destino, identidad estable, un solo commit, `--dry-run`, resumen con incidencias). Un solo cambio en la aplicación: la columna `branches.folio_inicial` que `get_next_folio` respeta. La ejecución en producción es un runbook manual con permiso explícito antes de cada escritura.

**Tech Stack:** Python 3.11/3.12, SQLAlchemy 2, pytest (SQLite en memoria), lector xlsx con `zipfile` + `ElementTree` (stdlib), `railway ssh` solo lectura, `ssh ionos` + `docker exec` para producción.

**Spec:** `docs/superpowers/specs/2026-09-30-coqueta-migracion-design.md`

## Global Constraints

- **Cero escrituras en Railway.** Todo acceso a rmazh es `railway ssh … -- /opt/venv/bin/python < script.py` con scripts de solo lectura.
- **`main` = producción.** Trabajar en `feat/coqueta-migracion`; commits locales sí, **push y merge solo con permiso explícito del usuario**.
- **Migraciones en `scripts/railway_init.py`** como ALTER idempotente. Nada de Alembic.
- **FKs a UUID = `String(36)`** (aplica a `department_id`, `brand_id`, `variant_id`).
- **`ProductVariant.cost` y `price` nunca NULL** (un NULL tumba `/products/pos/search` con 500).
- **Toda escritura de negocio lleva `organization_id`.**
- Pruebas: `python3 -m pytest -q -p no:warnings <archivo>` con el Python 3.12 del sistema (no hay `.venv`). Nunca dos `pytest` a la vez en el mismo worktree. Siempre `--ignore=tests/test_cash_complete.py` si se corre la suite completa.
- Los hashes de contraseña exportados viven solo en el scratchpad (`/tmp/claude-1000/-mnt-d-Devs-atlas-one/e35ce3ce-1728-4f1c-8340-59ba97d45264/scratchpad/coqueta_users.json`). Nunca se versionan, nunca se pegan en el chat ni en un commit.
- Estilo del repo: comentarios y nombres en español, `from __future__ import annotations`, type hints en firmas nuevas, sin `print()` de depuración (los `print` de resumen del CLI sí son el producto).

## Review Focus

Entradas que el spec implica pero que ninguna prueba cubría al escribir el plan; cada línea tiene su prueba añadida a la tarea dueña.

1. **Escalón con precio mayor al precio base** (rmazh permite "Mayoreo" más caro que el base por error de captura): el importador lo carga igual y lo anota como incidencia; no lo corrige en silencio. → Tarea 4.
2. **Renglón duplicado de rmazh** (mismo código de barras y mismo nombre dos veces en el xlsx): la segunda aparición actualiza a la primera, no crea otro producto y **no duplica el movimiento de existencias**. → Tarea 5.
3. **`Incluye IVA` con valores raros** (`SI`, `sí`, `Sí`, vacío, `1`): todo lo que no sea afirmativo cae en `False`, y el afirmativo con acento también se reconoce. → Tarea 3.
4. **Usuario cuyo rol de rmazh no existe en Atlas ONE** (p. ej. `SUPERVISOR`): el script de usuarios aborta antes de escribir nada, con el nombre del rol en el error. → Tarea 2.
5. **`folio_inicial` menor o igual al máximo ya vendido** (alguien lo captura tarde, con ventas hechas): el folio sigue siendo máximo+1, nunca retrocede ni repite. → Tarea 1.

---

### Task 1: `branches.folio_inicial` respetado por `get_next_folio`

**Files:**
- Modify: `app/modules/tenants/models.py:113-120` (bloque "Printer config" de `Branch`)
- Modify: `scripts/railway_init.py:70-90` (lista `COLUMN_MIGRATIONS`)
- Modify: `app/utils/folios.py`
- Test: `tests/test_folios.py`

**Interfaces:**
- Consumes: `get_next_folio(db, branch_id: int, series: str = "A") -> int` (existente), fixtures `db`, `org`, `branch_a`, `cajero_a` y helper `_make_sale` de `tests/test_folios.py`.
- Produces: `Branch.folio_inicial: Optional[int]`. El runbook (Tarea 8) lo fija en 1464 por SQL.

- [ ] **Step 1: Escribir las pruebas que fallan**

Añadir al final de `tests/test_folios.py`:

```python
def test_folio_inicial_arranca_la_serie_sin_ventas(db, branch_a, org):
    branch_a.folio_inicial = 1464
    db.flush()
    assert get_next_folio(db, branch_id=branch_a.id, series="A") == 1464


def test_folio_inicial_sigue_contando_despues_de_la_primera_venta(db, branch_a, org, cajero_a):
    branch_a.folio_inicial = 1464
    db.flush()
    _make_sale(db, branch_a.id, "A", 1464, org.id, cajero_a.id)
    assert get_next_folio(db, branch_id=branch_a.id, series="A") == 1465


def test_folio_inicial_menor_al_maximo_no_retrocede(db, branch_a, org, cajero_a):
    """Review Focus #5: capturado tarde, con ventas hechas, nunca repite folio."""
    _make_sale(db, branch_a.id, "A", 2000, org.id, cajero_a.id)
    branch_a.folio_inicial = 1464
    db.flush()
    assert get_next_folio(db, branch_id=branch_a.id, series="A") == 2001


def test_folio_inicial_nulo_conserva_el_comportamiento_de_hoy(db, branch_a, org):
    assert branch_a.folio_inicial is None
    assert get_next_folio(db, branch_id=branch_a.id, series="A") == 1


def test_folio_inicial_aplica_a_todas_las_series_de_la_sucursal(db, branch_a, org):
    """Decision del spec §3.3: sin regla especial por serie."""
    branch_a.folio_inicial = 1464
    db.flush()
    assert get_next_folio(db, branch_id=branch_a.id, series="Q") == 1464
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_folios.py`
Expected: 5 FAIL con `AttributeError: 'Branch' object has no attribute 'folio_inicial'` (o `TypeError` al asignar); las 5 pruebas previas siguen en PASS.

- [ ] **Step 3: Columna en el modelo**

En `app/modules/tenants/models.py`, dentro de `class Branch`, después de `open_drawer_on_print`:

```python
    # Primer folio que emite esta sucursal (todas las series). Sirve para que
    # una tienda que llega de otro sistema siga su numeracion en vez de
    # volver al 1 (Coqueta: rmazh llego al 1463, aqui arranca en 1464).
    # NULL = comportamiento de siempre. Ver app/utils/folios.py.
    folio_inicial = Column(Integer, nullable=True)
```

- [ ] **Step 4: ALTER idempotente**

En `scripts/railway_init.py`, en `COLUMN_MIGRATIONS`, justo después de la línea de `("branches", "logo_url", …)`:

```python
    # Folio inicial por sucursal (2026-09-30, mudanza de Coqueta desde rmazh).
    ("branches", "folio_inicial",    "ALTER TABLE branches ADD COLUMN folio_inicial INTEGER;"),
```

- [ ] **Step 5: `get_next_folio` lo respeta**

Reemplazar el final de `app/utils/folios.py` (desde `max_folio = …`) por:

```python
    max_folio = db.query(func.max(SalesDocument.folio)).filter(
        SalesDocument.branch_id == branch_id,
        SalesDocument.series == series,
    ).scalar()
    siguiente = 1 if max_folio is None else max_folio + 1

    # Una sucursal que llega de otro sistema puede pedir que su numeracion
    # arranque donde la dejo (Branch.folio_inicial). Solo empuja hacia arriba:
    # si ya hay ventas por encima, manda el maximo, nunca se repite un folio.
    folio_inicial = db.query(Branch.folio_inicial).filter(Branch.id == branch_id).scalar()
    if folio_inicial is not None and folio_inicial > siguiente:
        return folio_inicial
    return siguiente
```

Y en los imports del mismo archivo añadir:

```python
from app.models.organization import Branch
```

- [ ] **Step 6: Correr y ver que pasan**

Run: `python3 -m pytest -q -p no:warnings tests/test_folios.py`
Expected: 10 passed.

- [ ] **Step 7: Regresión del checkout**

Run: `python3 -m pytest -q -p no:warnings tests/test_sales*.py tests/test_quotes*.py`
Expected: mismo conteo de `passed`/`failed` que en `main` (comparar con `git stash` si hay dudas; el cambio no debe sumar ningún `failed`).

- [ ] **Step 8: Commit**

```bash
git add app/modules/tenants/models.py scripts/railway_init.py app/utils/folios.py tests/test_folios.py
git commit -m "feat(folios): folio_inicial por sucursal para tiendas que llegan de otro sistema

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014rnFXXn9to8upxnFg1bpw8"
```

---

### Task 2: `scripts/import_rmazh_users.py` — usuarios con su hash

**Files:**
- Create: `scripts/import_rmazh_users.py`
- Test: `tests/test_import_rmazh_users.py`

**Interfaces:**
- Consumes: `User`, `UserOrganization`, `Role`, `PlatformRole` de `app.modules.users.models`; `Branch`, `Organization` de `app.models.organization`; fixtures `db`, `org`, `branch_a`, `admin_a` (username `admin_a`, ADMINISTRADOR), `branch_b`.
- Produces: `import_rmazh_users(db, usuarios: list[dict], org_id: int, branch_id: int, dry_run: bool = False) -> dict` con claves `creados`, `actualizados`, `incidencias`, `organizacion`, `sucursal`. CLI `python scripts/import_rmazh_users.py usuarios.json --org N --branch M [--dry-run]`.

Formato de entrada (lo que imprime `export_coq2.py` entre `###USERS###` y `###B64###`), un objeto por usuario:

```json
{"id": 41, "username": "Mirna", "full_name": "Mirna", "email": null, "personal_email": null,
 "phone": null, "rol": "ADMINISTRADOR", "is_active": true, "branch_id": 26, "sucursal": "HQ - …",
 "password_hash": "$2a$12$…", "reprint_pin_hash": "$2a$12$…", "alta": "2026-05-08"}
```

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_import_rmazh_users.py`:

```python
"""Tests: traspaso de usuarios desde rmazh con su hash (scripts/import_rmazh_users.py)."""
import importlib

import pytest

from app.modules.users.models import User, UserOrganization

imp = importlib.import_module("scripts.import_rmazh_users")

HASH = "$2a$12$abcdefghijklmnopqrstuuABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789ab"
PIN = "$2a$12$zyxwvutsrqponmlkjihgfeZYXWVUTSRQPONMLKJIHGFEDCBA9876543210zz"

MIRNA = {"id": 41, "username": "Mirna", "full_name": "Mirna", "email": None, "personal_email": None,
         "phone": None, "rol": "ADMINISTRADOR", "is_active": True, "branch_id": 26,
         "password_hash": HASH, "reprint_pin_hash": PIN}
JOSE = {"id": 42, "username": "Jose", "full_name": "Jose Rivas", "email": None, "personal_email": None,
        "phone": "5512345678", "rol": "CAJERO", "is_active": True, "branch_id": 27,
        "password_hash": HASH, "reprint_pin_hash": None}


class TestCrea:
    def test_crea_admin_y_cajero_con_su_hash(self, db, org, branch_a):
        r = imp.import_rmazh_users(db, [MIRNA, JOSE], org.id, branch_a.id)
        assert r["creados"] == 2 and r["actualizados"] == 0

        mirna = db.query(User).filter(User.username == "Mirna").one()
        assert mirna.role.value == "ADMINISTRADOR"
        assert mirna.password_hash == HASH
        assert mirna.reprint_pin_hash == PIN
        assert mirna.branch_id == branch_a.id
        assert mirna.platform_role.value == "NONE"
        enlace = db.query(UserOrganization).filter_by(user_id=mirna.id, organization_id=org.id).one()
        assert enlace.org_role == "ADMIN"

        jose = db.query(User).filter(User.username == "Jose").one()
        assert jose.role.value == "CAJERO"
        assert jose.full_name == "Jose Rivas"
        assert jose.phone == "5512345678"
        assert jose.reprint_pin_hash is None
        enlace = db.query(UserOrganization).filter_by(user_id=jose.id, organization_id=org.id).one()
        assert enlace.org_role == "MEMBER"

    def test_respeta_is_active_false(self, db, org, branch_a):
        imp.import_rmazh_users(db, [dict(JOSE, is_active=False)], org.id, branch_a.id)
        assert db.query(User).filter(User.username == "Jose").one().is_active is False


class TestActualiza:
    def test_reemplaza_el_hash_del_admin_que_creo_onboard(self, db, org, branch_a, admin_a):
        """onboard_org.py crea al admin con contrasena generada; aqui recupera la real."""
        viejo = admin_a.password_hash
        r = imp.import_rmazh_users(db, [dict(MIRNA, username="admin_a")], org.id, branch_a.id)
        assert r["creados"] == 0 and r["actualizados"] == 1
        db.refresh(admin_a)
        assert admin_a.password_hash == HASH and admin_a.password_hash != viejo
        assert admin_a.reprint_pin_hash == PIN
        assert admin_a.full_name == "Mirna"

    def test_es_idempotente(self, db, org, branch_a):
        imp.import_rmazh_users(db, [MIRNA, JOSE], org.id, branch_a.id)
        r = imp.import_rmazh_users(db, [MIRNA, JOSE], org.id, branch_a.id)
        assert r["creados"] == 0 and r["actualizados"] == 2
        assert db.query(User).filter(User.username.in_(["Mirna", "Jose"])).count() == 2
        assert db.query(UserOrganization).filter_by(organization_id=org.id).count() == 2


class TestRechaza:
    def test_username_de_otra_organizacion_aborta_sin_escribir(self, db, org, branch_a):
        from app.models.organization import Organization
        from app.modules.users.models import PlatformRole, Role
        otra = Organization(name="Otra Org", status="ACTIVE")
        db.add(otra); db.flush()
        ajeno = User(username="Jose", password_hash=HASH, role=Role.CAJERO, platform_role=PlatformRole.NONE, is_active=True)
        db.add(ajeno); db.flush()
        db.add(UserOrganization(user_id=ajeno.id, organization_id=otra.id, org_role="MEMBER", is_active=True)); db.flush()

        with pytest.raises(ValueError, match="Jose.*otra organizacion"):
            imp.import_rmazh_users(db, [MIRNA, JOSE], org.id, branch_a.id)
        assert db.query(User).filter(User.username == "Mirna").first() is None, "nada se escribio"

    def test_rol_desconocido_aborta_con_el_nombre_del_rol(self, db, org, branch_a):
        """Review Focus #4."""
        with pytest.raises(ValueError, match="SUPERVISOR"):
            imp.import_rmazh_users(db, [dict(JOSE, rol="SUPERVISOR")], org.id, branch_a.id)
        assert db.query(User).filter(User.username == "Jose").first() is None

    def test_sin_hash_bcrypt_aborta(self, db, org, branch_a):
        with pytest.raises(ValueError, match="hash"):
            imp.import_rmazh_users(db, [dict(JOSE, password_hash="plano")], org.id, branch_a.id)

    def test_sucursal_de_otra_organizacion_aborta(self, db, org, branch_a):
        from app.models.organization import Organization, Branch
        from app.modules.tenants.models import BranchType
        otra = Organization(name="Otra Org", status="ACTIVE")
        db.add(otra); db.flush()
        ajena = Branch(name="Ajena", branch_type=BranchType.STORE, can_sell=True,
                       is_active=True, organization_id=otra.id)
        db.add(ajena); db.flush()
        with pytest.raises(ValueError, match="pertenece"):
            imp.import_rmazh_users(db, [JOSE], org.id, ajena.id)


class TestDryRun:
    def test_dry_run_no_escribe(self, db, org, branch_a):
        r = imp.import_rmazh_users(db, [MIRNA, JOSE], org.id, branch_a.id, dry_run=True)
        assert r["creados"] == 2
        assert db.query(User).filter(User.username.in_(["Mirna", "Jose"])).count() == 0
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_import_rmazh_users.py`
Expected: error de colección `ModuleNotFoundError: No module named 'scripts.import_rmazh_users'`.

- [ ] **Step 3: Implementar el script**

Crear `scripts/import_rmazh_users.py`:

```python
"""Traspaso de usuarios desde rmazh (Data X POS) con su contrasena de siempre.

rmazh y Atlas ONE hashean con la misma libreria (passlib, bcrypt `$2a$`), asi
que el hash de la contrasena y el del PIN de reimpresion se copian tal cual y
la gente entra con lo que ya sabe. Aqui no se inventa ninguna clave.

Entrada: el JSON que imprime `export_coq2.py` (repo Atlas-Rmazh) entre
`###USERS###` y `###B64###` — una lista de usuarios con `username`,
`full_name`, `email`, `personal_email`, `phone`, `rol`, `is_active`,
`password_hash` y `reprint_pin_hash`. Ese archivo trae hashes: se guarda fuera
del repo y no se pega en ningun lado.

Reglas:
  - `username` es unico en TODA la base. Si ya existe y es de esta
    organizacion (el admin que creo `onboard_org.py`), se actualizan nombre,
    hash, PIN y sucursal. Si existe y es de otra organizacion, se aborta sin
    escribir nada.
  - El rol de rmazh debe existir en `Role` (los nombres coinciden:
    ADMINISTRADOR, CAJERO…). Uno desconocido aborta antes de escribir.
  - ADMINISTRADOR y DUEÑO enlazan a la organizacion como `org_role=ADMIN`;
    los demas como `MEMBER`.
  - Todo se confirma en un solo commit al final.

Uso:
    python scripts/import_rmazh_users.py usuarios.json --org 18 --branch 21 --dry-run
    python scripts/import_rmazh_users.py usuarios.json --org 18 --branch 21
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.models  # noqa: F401  (puebla la metadata)
from app.models.organization import Branch, Organization
from app.modules.users.models import PlatformRole, Role, User, UserOrganization

ROLES_ADMIN = {Role.ADMINISTRADOR, Role.DUEÑO}


def validar_destino(db, org_id: int, branch_id: int) -> Tuple[Organization, Branch]:
    """La organizacion y la sucursal existen y van juntas (mismo guard que los importadores)."""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        raise ValueError(f"la organizacion {org_id} no existe")
    sucursal = db.query(Branch).filter(Branch.id == branch_id).first()
    if sucursal is None:
        raise ValueError(f"la sucursal {branch_id} no existe")
    if sucursal.organization_id != org_id:
        raise ValueError(
            f"la sucursal {branch_id} ('{sucursal.name}') pertenece a la "
            f"organizacion {sucursal.organization_id}, no a la {org_id} ('{org.name}')"
        )
    return org, sucursal


def _rol(nombre: Optional[str]) -> Role:
    try:
        return Role[(nombre or "").strip()]
    except KeyError:
        validos = ", ".join(r.name for r in Role)
        raise ValueError(f"rol desconocido {nombre!r}; validos: {validos}") from None


def _hash_valido(h: Optional[str]) -> bool:
    return bool(h) and h.startswith("$2")


def _validar(db, usuarios: List[Dict[str, Any]], org_id: int) -> None:
    """Todo lo que puede abortar se comprueba ANTES de la primera escritura."""
    for u in usuarios:
        username = (u.get("username") or "").strip()
        if not username:
            raise ValueError("usuario sin username")
        _rol(u.get("rol"))
        if not _hash_valido(u.get("password_hash")):
            raise ValueError(f"{username}: password_hash no es un hash bcrypt — no se crea un usuario sin contrasena usable")
        pin = u.get("reprint_pin_hash")
        if pin and not _hash_valido(pin):
            raise ValueError(f"{username}: reprint_pin_hash no es un hash bcrypt")

        existente = db.query(User).filter(User.username == username).first()
        if existente is None:
            continue
        de_esta = (
            db.query(UserOrganization)
            .filter(UserOrganization.user_id == existente.id, UserOrganization.organization_id == org_id)
            .first()
        )
        if de_esta is None:
            raise ValueError(
                f"el username {username!r} ya existe (id={existente.id}) y es de otra organizacion — "
                f"users.username es unico global; elige otro nombre antes de seguir"
            )


def import_rmazh_users(
    db,
    usuarios: List[Dict[str, Any]],
    org_id: int,
    branch_id: int,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Crea o actualiza los usuarios en la organizacion y sucursal indicadas."""
    resumen: Dict[str, Any] = {"creados": 0, "actualizados": 0, "incidencias": []}
    org, sucursal = validar_destino(db, org_id, branch_id)
    resumen["organizacion"] = org.name
    resumen["sucursal"] = sucursal.name

    _validar(db, usuarios, org_id)

    try:
        for u in usuarios:
            username = u["username"].strip()
            rol = _rol(u.get("rol"))
            usuario = db.query(User).filter(User.username == username).first()

            if usuario is None:
                usuario = User(
                    username=username,
                    full_name=(u.get("full_name") or username).strip(),
                    email=u.get("email") or None,
                    personal_email=u.get("personal_email") or None,
                    phone=u.get("phone") or None,
                    password_hash=u["password_hash"],
                    reprint_pin_hash=u.get("reprint_pin_hash") or None,
                    role=rol,
                    platform_role=PlatformRole.NONE,
                    branch_id=branch_id,
                    is_active=bool(u.get("is_active", True)),
                )
                db.add(usuario)
                db.flush()
                resumen["creados"] += 1
            else:
                usuario.full_name = (u.get("full_name") or usuario.full_name or username).strip()
                usuario.password_hash = u["password_hash"]
                usuario.reprint_pin_hash = u.get("reprint_pin_hash") or None
                usuario.branch_id = branch_id
                if u.get("phone"):
                    usuario.phone = u["phone"]
                resumen["actualizados"] += 1

            enlace = (
                db.query(UserOrganization)
                .filter(UserOrganization.user_id == usuario.id, UserOrganization.organization_id == org_id)
                .first()
            )
            if enlace is None:
                db.add(
                    UserOrganization(
                        user_id=usuario.id,
                        organization_id=org_id,
                        is_active=True,
                        org_role="ADMIN" if rol in ROLES_ADMIN else "MEMBER",
                    )
                )
                db.flush()

        if dry_run:
            db.rollback()
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    return resumen


def main() -> None:
    p = argparse.ArgumentParser(description="Traspaso de usuarios desde rmazh con su hash")
    p.add_argument("json")
    p.add_argument("--org", type=int, required=True)
    p.add_argument("--branch", type=int, required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    with open(args.json, encoding="utf-8") as fh:
        usuarios = json.load(fh)

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        try:
            org, sucursal = validar_destino(db, args.org, args.branch)
        except ValueError as e:
            print(f"ABORTADO: {e}", file=sys.stderr)
            raise SystemExit(2)
        print("=" * 60)
        print("ENSAYO (nada se guarda)" if args.dry_run else "TRASPASO REAL")
        print(f"  organizacion  {org.name} (id={org.id})")
        print(f"  sucursal      {sucursal.name} (id={sucursal.id})")
        print(f"  usuarios      {', '.join(u.get('username', '?') for u in usuarios)}")
        print("=" * 60)
        try:
            r = import_rmazh_users(db, usuarios, args.org, args.branch, dry_run=args.dry_run)
        except ValueError as e:
            print(f"ABORTADO: {e}", file=sys.stderr)
            raise SystemExit(2)
    finally:
        db.close()

    print("=" * 60)
    print("ENSAYO — nada se guardo" if args.dry_run else "TRASPASO APLICADO")
    print(f"  creados       {r['creados']}")
    print(f"  actualizados  {r['actualizados']}")
    for inc in r["incidencias"]:
        print("   ·", inc)
    print("=" * 60)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `python3 -m pytest -q -p no:warnings tests/test_import_rmazh_users.py`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/import_rmazh_users.py tests/test_import_rmazh_users.py
git commit -m "feat(scripts): traspaso de usuarios desde rmazh conservando su contrasena

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014rnFXXn9to8upxnFg1bpw8"
```

---

### Task 3: `scripts/import_rmazh_export.py` — lector y catálogo base

Esta tarea deja el importador creando producto + variante (SKU, código, precio, costo, IVA, departamento con exclusiones) y el estado en sucursal. Escalones, existencias, tope e idempotencia completa llegan en las tareas 4 y 5 **sobre el mismo archivo**.

**Files:**
- Create: `scripts/import_rmazh_export.py`
- Test: `tests/test_import_rmazh_export.py`

**Interfaces:**
- Consumes: modelos `Product`, `ProductVariant`, `Department`, `Brand`, `ProductBranchStatus`, `ProductPrice` de `app.models.products`; `StockOnHand`, `InventoryMovement`, `MovementType` de `app.models.inventory`; `User`, `UserOrganization`, `Role` de `app.models.users`; `Branch`, `Organization` de `app.models.organization`. Fixtures `db`, `org`, `branch_a`, `admin_user`, `tmp_path`.
- Produces: `import_rmazh_export(db, ruta_xlsx: str, org_id: int, branch_id: int, dry_run: bool = False, tope: Optional[Decimal] = None, conservar_departamentos: bool = False, conservar_marcas: bool = False) -> dict` con claves `creados`, `actualizados`, `omitidos`, `escalones`, `movimientos`, `departamentos_creados`, `marcas_creadas`, `codigos_generados`, `existencias_altas` (lista de `(sku, nombre, Decimal)`), `incidencias`, `organizacion`, `sucursal`. Función `leer_export(ruta) -> Iterator[Tuple[int, Dict[str, str]]]`. Constantes `REFERENCIA_CARGA = "Carga inicial rmazh"`, `UMBRAL_EXISTENCIAS_ALTAS = Decimal("500")`, `DEPARTAMENTOS_EXCLUIDOS = {"ncoqueta", "general", "sin departamento"}`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `tests/test_import_rmazh_export.py`:

```python
"""Tests: carga de catalogo desde la exportacion de rmazh (scripts/import_rmazh_export.py).

El xlsx se arma aqui con `zipfile` y el XML minimo que escribe openpyxl (el
exportador de rmazh usa openpyxl): texto en `sharedStrings.xml`, numeros como
celdas sin atributo `t`. Asi la prueba ejercita el lector real.
"""
import importlib
import zipfile
from decimal import Decimal
from xml.sax.saxutils import escape

import pytest

from app.models.inventory import InventoryMovement, MovementType, StockOnHand
from app.models.products import Brand, Department, Product, ProductBranchStatus, ProductPrice, ProductVariant

imp = importlib.import_module("scripts.import_rmazh_export")

CABECERAS = [
    "SKU", "Nombre", "Descripcion", "Unidad", "Departamento", "Marca", "Codigo Barras",
    "Precio Base", "Costo", "Stock", "Incluye IVA",
] + [f"P{i} {f}" for i in range(1, 6) for f in ["Nombre", "Min", "Precio", "Empaque"]] \
  + [f"E{i} {f}" for i in range(1, 4) for f in ["Nombre", "Barcode", "Cantidad", "Precio"]]

CASCANUECES = {
    "SKU": "8888172121301", "Nombre": "CASCANUECES", "Descripcion": "", "Unidad": "pza",
    "Departamento": "Ncoqueta", "Marca": "Rmazh", "Codigo Barras": "8888172121301",
    "Precio Base": 220, "Costo": 140, "Stock": 2556, "Incluye IVA": "No",
    "P1 Nombre": "Mayoreo", "P1 Min": 3, "P1 Precio": 210,
}
STITCH = {
    "SKU": "STITCH", "Nombre": "STITCH", "Departamento": "General", "Marca": "Rmazh",
    "Codigo Barras": "", "Precio Base": 140, "Costo": 70, "Stock": 10000, "Incluye IVA": "Si",
    "P1 Nombre": "Mayoreo", "P1 Min": 3, "P1 Precio": 120,
    "P2 Nombre": "Caja", "P2 Min": 12, "P2 Precio": 100,
}


def _es_numero(v) -> bool:
    try:
        float(v)
    except (TypeError, ValueError):
        return False
    return True


def _xlsx(tmp_path, filas, nombre="rmazh.xlsx"):
    compartidas: list[str] = []
    indices: dict[str, int] = {}

    def _idx(texto: str) -> int:
        if texto not in indices:
            indices[texto] = len(compartidas)
            compartidas.append(texto)
        return indices[texto]

    def _columna(i: int) -> str:
        letra = ""
        i += 1
        while i:
            i, resto = divmod(i - 1, 26)
            letra = chr(65 + resto) + letra
        return letra

    xml_filas = []
    for nfila, valores in enumerate([{c: c for c in CABECERAS}] + filas, start=1):
        celdas = []
        for i, cab in enumerate(CABECERAS):
            v = valores.get(cab, "")
            if v == "" or v is None:
                continue
            ref = f"{_columna(i)}{nfila}"
            if nfila > 1 and _es_numero(v):
                celdas.append(f'<c r="{ref}"><v>{v}</v></c>')
            else:
                celdas.append(f'<c r="{ref}" t="s"><v>{_idx(str(v))}</v></c>')
        xml_filas.append(f'<row r="{nfila}">{"".join(celdas)}</row>')

    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    hoja = f'<?xml version="1.0" encoding="UTF-8"?><worksheet {ns}><sheetData>{"".join(xml_filas)}</sheetData></worksheet>'
    sst = "".join(f"<si><t>{escape(s)}</t></si>" for s in compartidas)
    cadenas = f'<?xml version="1.0" encoding="UTF-8"?><sst {ns} count="{len(compartidas)}" uniqueCount="{len(compartidas)}">{sst}</sst>'
    ruta = tmp_path / nombre
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("xl/sharedStrings.xml", cadenas)
        z.writestr("xl/worksheets/sheet1.xml", hoja)
        # La exportacion real trae una segunda hoja "Listas_Validacion": no debe leerse.
        z.writestr("xl/worksheets/sheet2.xml", f'<?xml version="1.0" encoding="UTF-8"?><worksheet {ns}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>')
    return str(ruta)


@pytest.fixture()
def cargar(db, org, branch_a, admin_user, tmp_path):
    def _cargar(filas, **kw):
        ruta = _xlsx(tmp_path, filas)
        return imp.import_rmazh_export(db, ruta, org.id, branch_a.id, **kw)
    return _cargar


class TestCatalogo:
    def test_crea_producto_variante_precio_costo_iva(self, db, org, branch_a, cargar):
        r = cargar([CASCANUECES])
        assert r["creados"] == 1 and r["omitidos"] == 0

        p = db.query(Product).filter(Product.organization_id == org.id).one()
        assert p.name == "CASCANUECES"
        v = db.query(ProductVariant).filter(ProductVariant.product_id == p.id).one()
        assert v.sku == "8888172121301"
        assert v.barcode == "8888172121301"
        assert v.variant_name == "Estándar"
        assert Decimal(str(v.price)) == Decimal("220")
        assert Decimal(str(v.cost)) == Decimal("140")
        assert v.has_iva is False
        pbs = db.query(ProductBranchStatus).filter_by(variant_id=v.id, branch_id=branch_a.id).one()
        assert pbs.is_active_pos is True and pbs.is_visible is True

    def test_departamento_ncoqueta_y_general_no_se_crean(self, db, org, cargar):
        cargar([CASCANUECES, STITCH])
        assert db.query(Department).filter(Department.organization_id == org.id).count() == 0
        for p in db.query(Product).filter(Product.organization_id == org.id):
            assert p.department_id is None

    def test_departamento_real_si_se_crea(self, db, org, cargar):
        r = cargar([dict(CASCANUECES, Departamento="Navidad")])
        assert r["departamentos_creados"] == 1
        d = db.query(Department).filter(Department.organization_id == org.id).one()
        assert d.name == "Navidad"
        assert db.query(Product).one().department_id == d.id

    def test_conservar_departamentos_crea_ncoqueta(self, db, org, cargar):
        cargar([CASCANUECES], conservar_departamentos=True)
        assert db.query(Department).filter(Department.name == "Ncoqueta").count() == 1

    def test_marca_se_ignora_salvo_bandera(self, db, org, cargar):
        cargar([CASCANUECES])
        assert db.query(Brand).filter(Brand.organization_id == org.id).count() == 0
        assert db.query(Product).one().brand_id is None

    def test_conservar_marcas_crea_rmazh(self, db, org, cargar):
        r = cargar([CASCANUECES], conservar_marcas=True)
        assert r["marcas_creadas"] == 1
        b = db.query(Brand).filter(Brand.organization_id == org.id).one()
        assert b.name == "Rmazh" and db.query(Product).one().brand_id == b.id

    def test_sin_codigo_de_barras_entra_con_sku_y_barcode_nulo(self, db, cargar):
        cargar([STITCH])
        v = db.query(ProductVariant).one()
        assert v.sku == "STITCH" and v.barcode is None

    def test_iva_variantes_de_escritura(self, db, cargar):
        """Review Focus #3."""
        filas = [
            dict(STITCH, SKU=f"S{i}", Nombre=f"S{i}", **{"Incluye IVA": v})
            for i, v in enumerate(["SI", "sí", "Sí", "1", "No", "", "quizas"])
        ]
        cargar(filas)
        iva = {v.sku: v.has_iva for v in db.query(ProductVariant)}
        assert iva == {"S0": True, "S1": True, "S2": True, "S3": True, "S4": False, "S5": False, "S6": False}

    def test_sin_nombre_se_omite_con_incidencia(self, db, cargar):
        r = cargar([dict(CASCANUECES, Nombre="")])
        assert r["omitidos"] == 1 and r["creados"] == 0
        assert any("sin nombre" in i for i in r["incidencias"])

    def test_costo_vacio_queda_en_cero_nunca_nulo(self, db, cargar):
        cargar([dict(CASCANUECES, Costo="")])
        v = db.query(ProductVariant).one()
        assert v.cost is not None and Decimal(str(v.cost)) == 0

    def test_precio_base_ausente_carga_cero_con_incidencia(self, db, cargar):
        r = cargar([dict(CASCANUECES, **{"Precio Base": ""})])
        v = db.query(ProductVariant).one()
        assert Decimal(str(v.price)) == 0
        assert any("Precio Base" in i for i in r["incidencias"])

    def test_sku_repetido_en_la_org_recibe_sufijo(self, db, org, cargar):
        cargar([CASCANUECES])
        r = cargar([dict(CASCANUECES, Nombre="CASCANUECES GRANDE", **{"Codigo Barras": "111"})])
        skus = sorted(v.sku for v in db.query(ProductVariant))
        assert skus == ["8888172121301", "8888172121301-2"]
        assert r["codigos_generados"] == 1

    def test_empaques_y_unidad_se_ignoran_con_aviso(self, db, cargar):
        r = cargar([dict(CASCANUECES, **{"E1 Nombre": "Caja 12", "E1 Cantidad": 12, "E1 Precio": 2000})])
        assert r["creados"] == 1
        assert any("empaque" in i.lower() for i in r["incidencias"])

    def test_destino_ajeno_aborta(self, db, org, branch_a, tmp_path):
        from app.models.organization import Organization, Branch
        from app.modules.tenants.models import BranchType
        otra = Organization(name="Otra", status="ACTIVE"); db.add(otra); db.flush()
        ajena = Branch(name="Ajena", branch_type=BranchType.STORE, can_sell=True, is_active=True, organization_id=otra.id)
        db.add(ajena); db.flush()
        ruta = _xlsx(tmp_path, [CASCANUECES])
        with pytest.raises(ValueError, match="pertenece"):
            imp.import_rmazh_export(db, ruta, org.id, ajena.id)

    def test_sin_cabeceras_de_rmazh_aborta(self, db, org, branch_a, tmp_path):
        import zipfile as zf
        ruta = tmp_path / "otro.xlsx"
        ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        with zf.ZipFile(ruta, "w") as z:
            z.writestr("xl/sharedStrings.xml", f'<sst {ns} count="1" uniqueCount="1"><si><t>Código</t></si></sst>')
            z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {ns}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>')
        with pytest.raises(ValueError, match="cabeceras"):
            imp.import_rmazh_export(db, str(ruta), org.id, branch_a.id)
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_import_rmazh_export.py`
Expected: error de colección `ModuleNotFoundError: No module named 'scripts.import_rmazh_export'`.

- [ ] **Step 3: Implementar lector + catálogo base**

Crear `scripts/import_rmazh_export.py`. Las funciones de escalones y existencias quedan como stubs que la tarea 4 rellena; el archivo ya compila y las pruebas de esta tarea pasan.

```python
"""Carga de catalogo desde la exportacion de rmazh (Data X POS, repo Atlas-Rmazh).

Hermano de `import_datax_export.py` (xlsx de Data X POS) e `import_products.py`
(CSV propio de Atlas ONE). Aqui la entrada es el xlsx que produce el boton
"Exportar" de rmazh — `export_products_template` — o el script
`scripts/adhoc/2026-09-01/coqueta/export_coq2.py` de ese repo, que llama al
mismo codigo. Ojo: exportar con la SUCURSAL QUE TIENE EXISTENCIAS, no con el HQ,
o el Stock viene en cero.

Columnas que se leen (fila 1, hoja "Plantilla"):
    SKU, Nombre, Descripcion, Departamento, Marca, Codigo Barras,
    Precio Base, Costo, Stock, Incluye IVA,
    Pn Nombre, Pn Min, Pn Precio            (n = 1..5, escalones)
Se ignoran, con aviso si vienen llenas: Unidad, Pn Empaque, E1..E3 (empaques).

Por cada renglon: departamento (si aplica), producto, variante con codigo,
precio, costo e IVA, un `ProductPrice` por cada escalon CON SU NOMBRE ORIGINAL
(Mayoreo, Caja, Precio 1… — "Caja" es un comportamiento del POS, igual que en
rmazh), el estado en la sucursal y las existencias como movimiento
ADJUSTMENT_IN con referencia "Carga inicial rmazh".

Identidad de un renglon: (Codigo Barras, Nombre) dentro de la organizacion.
Re-correr refresca precios, costo, IVA, escalones y estado; no duplica
productos ni vuelve a cargar existencias.

Departamento y marca de rmazh: la exportacion de Coqueta trae un unico
departamento "Ncoqueta" y una unica marca "Rmazh" que no dicen nada; por
omision no se crean (todo queda sin departamento, que el POS muestra como
"General"). `--conservar-departamentos` / `--conservar-marcas` los respetan.

Existencias: entran tal cual. Las mayores a 500 se listan al final para que
la duena las revise (en Coqueta hay 30 renglones con exactamente 10,000, que
es relleno). `--tope N` las recorta a N si se decide asi.

Todo se confirma en un solo commit al final.

Uso:
    python scripts/import_rmazh_export.py catalogo.xlsx --org 18 --branch 21 --dry-run
    python scripts/import_rmazh_export.py catalogo.xlsx --org 18 --branch 21
    python scripts/import_rmazh_export.py catalogo.xlsx --org 18 --branch 21 --tope 50
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.models  # noqa: F401  (puebla la metadata)
from app.models.inventory import InventoryMovement, MovementType, StockOnHand
from app.models.organization import Branch, Organization
from app.models.products import (
    Brand,
    Department,
    Product,
    ProductBranchStatus,
    ProductPrice,
    ProductVariant,
)
from app.models.users import Role, User, UserOrganization

# Referencia del kardex y marca de idempotencia de las existencias.
REFERENCIA_CARGA = "Carga inicial rmazh"

# Por encima de esto, la existencia se reporta para revision humana.
UMBRAL_EXISTENCIAS_ALTAS = Decimal("500")

# Departamentos que no se crean salvo `--conservar-departamentos` (normalizados).
# "general" y "sin departamento" son lo que rmazh escribe cuando no hay ninguno.
DEPARTAMENTOS_EXCLUIDOS = {"ncoqueta", "general", "sin departamento"}

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _norm(s: Optional[str]) -> str:
    """Normaliza una cabecera o un valor: sin acentos, sin signos, en minusculas."""
    s = (s or "").strip().replace("*", "").replace("¿", "").replace("?", "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", s).strip()


CAMPOS: Dict[str, str] = {
    "sku": "sku",
    "nombre": "nombre",
    "descripcion": "descripcion",
    "unidad": "unidad",
    "departamento": "departamento",
    "marca": "marca",
    "codigo barras": "codigo",
    "precio base": "precio",
    "costo": "costo",
    "stock": "stock",
    "incluye iva": "iva",
}
for _n in range(1, 6):
    CAMPOS[f"p{_n} nombre"] = f"p{_n}_nombre"
    CAMPOS[f"p{_n} min"] = f"p{_n}_min"
    CAMPOS[f"p{_n} precio"] = f"p{_n}_precio"
    CAMPOS[f"p{_n} empaque"] = f"p{_n}_empaque"
for _n in range(1, 4):
    CAMPOS[f"e{_n} nombre"] = f"e{_n}_nombre"
    CAMPOS[f"e{_n} barcode"] = f"e{_n}_barcode"
    CAMPOS[f"e{_n} cantidad"] = f"e{_n}_cantidad"
    CAMPOS[f"e{_n} precio"] = f"e{_n}_precio"

CABECERAS_MINIMAS = {"sku", "nombre", "precio"}


# --- Lectura del .xlsx (stdlib, igual que import_datax_export.py) -----------

def _columna(ref: str) -> int:
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def _cadenas_compartidas(z: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    raiz = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(_NS + "t")) for si in raiz]


def _ruta_hoja(z: zipfile.ZipFile) -> str:
    # La primera hoja es "Plantilla"; la segunda, "Listas_Validacion", no se lee.
    if "xl/worksheets/sheet1.xml" in z.namelist():
        return "xl/worksheets/sheet1.xml"
    hojas = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/") and n.endswith(".xml"))
    if not hojas:
        raise ValueError("el archivo no trae ninguna hoja de calculo")
    return hojas[0]


def _valor(celda: ET.Element, compartidas: List[str]) -> str:
    tipo = celda.get("t")
    if tipo == "s":
        v = celda.find(_NS + "v")
        if v is None or v.text is None:
            return ""
        return compartidas[int(v.text)]
    if tipo == "inlineStr":
        el = celda.find(_NS + "is")
        return "".join(t.text or "" for t in el.iter(_NS + "t")) if el is not None else ""
    v = celda.find(_NS + "v")
    return (v.text or "") if v is not None else ""


def leer_export(ruta: str) -> Iterator[Tuple[int, Dict[str, str]]]:
    """Devuelve (numero de fila, {campo canonico: valor}) por cada renglon con datos."""
    with zipfile.ZipFile(ruta) as z:
        compartidas = _cadenas_compartidas(z)
        hoja = ET.fromstring(z.read(_ruta_hoja(z)))

    cabeceras: Dict[int, str] = {}
    for nfila, fila in enumerate(hoja.iter(_NS + "row"), start=1):
        crudas: Dict[int, str] = {}
        for i, celda in enumerate(fila.iter(_NS + "c")):
            ref = celda.get("r")
            idx = _columna(ref) if ref else i
            crudas[idx] = (_valor(celda, compartidas) or "").strip()

        if not cabeceras:
            cabeceras = {i: CAMPOS[_norm(v)] for i, v in crudas.items() if _norm(v) in CAMPOS}
            if not CABECERAS_MINIMAS <= set(cabeceras.values()):
                raise ValueError(
                    "la primera fila no tiene las cabeceras de la exportacion de rmazh "
                    "(se esperaba al menos SKU, Nombre y Precio Base)"
                )
            continue

        f = {campo: crudas.get(i, "") for i, campo in cabeceras.items()}
        if any(v for v in f.values()):
            yield nfila, f


# --- Conversiones -----------------------------------------------------------

def _si(valor: Optional[str]) -> bool:
    return _norm(valor) in {"si", "s", "yes", "y", "true", "1"}


def _num(valor: Optional[str], campo: str, nfila: int) -> Optional[Decimal]:
    v = (valor or "").strip().replace(",", "").replace("$", "")
    if not v:
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        raise ValueError(f"fila {nfila}: {campo} invalido — {valor!r} no es un numero") from None


def _positivo(valor: Optional[Decimal]) -> Optional[Decimal]:
    return valor if valor is not None and valor > 0 else None


def _sku_desde_nombre(nombre: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]", "", unicodedata.normalize("NFKD", nombre).upper())
    return base[:8] or "PROD"


def validar_destino(db, org_id: int, branch_id: int) -> Tuple[Organization, Branch]:
    """La organizacion y la sucursal existen y van juntas."""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        raise ValueError(f"la organizacion {org_id} no existe")
    sucursal = db.query(Branch).filter(Branch.id == branch_id).first()
    if sucursal is None:
        raise ValueError(f"la sucursal {branch_id} no existe")
    if sucursal.organization_id != org_id:
        raise ValueError(
            f"la sucursal {branch_id} ('{sucursal.name}') pertenece a la "
            f"organizacion {sucursal.organization_id}, no a la {org_id} "
            f"('{org.name}') — revisa --org y --branch"
        )
    return org, sucursal


def _admin_de_org(db, org_id: int) -> Optional[User]:
    base = (
        db.query(User)
        .join(UserOrganization, UserOrganization.user_id == User.id)
        .filter(UserOrganization.organization_id == org_id, UserOrganization.is_active.is_(True))
    )
    admin = base.filter(UserOrganization.org_role == "ADMIN").order_by(User.id).first()
    if admin is not None:
        return admin
    return base.filter(User.role == Role.ADMINISTRADOR).order_by(User.id).first()


# --- Carga ------------------------------------------------------------------

def import_rmazh_export(
    db,
    ruta_xlsx: str,
    org_id: int,
    branch_id: int,
    dry_run: bool = False,
    tope: Optional[Decimal] = None,
    conservar_departamentos: bool = False,
    conservar_marcas: bool = False,
) -> Dict[str, Any]:
    """Carga el catalogo exportado por rmazh. Devuelve conteos e incidencias."""
    resumen: Dict[str, Any] = {
        "creados": 0,
        "actualizados": 0,
        "omitidos": 0,
        "escalones": 0,
        "movimientos": 0,
        "departamentos_creados": 0,
        "marcas_creadas": 0,
        "codigos_generados": 0,
        "existencias_altas": [],
        "incidencias": [],
    }

    org, sucursal = validar_destino(db, org_id, branch_id)
    resumen["organizacion"] = org.name
    resumen["sucursal"] = sucursal.name

    admin = _admin_de_org(db, org_id)
    if admin is None:
        resumen["incidencias"].append(
            "la organizacion no tiene administrador: los movimientos de carga quedan sin autor"
        )

    usados = {
        s for (s,) in db.query(ProductVariant.sku)
        .filter(ProductVariant.organization_id == org_id, ProductVariant.deleted_at.is_(None))
        .all()
        if s
    }
    departamentos: Dict[str, Department] = {}
    marcas: Dict[str, Brand] = {}

    def _departamento(nombre: str) -> Optional[Department]:
        clave = (nombre or "").strip()
        if not clave:
            return None
        if not conservar_departamentos and _norm(clave) in DEPARTAMENTOS_EXCLUIDOS:
            return None
        if clave in departamentos:
            return departamentos[clave]
        d = db.query(Department).filter(Department.organization_id == org_id, Department.name == clave).first()
        if d is None:
            d = Department(name=clave, organization_id=org_id)
            db.add(d)
            db.flush()
            resumen["departamentos_creados"] += 1
        departamentos[clave] = d
        return d

    def _marca(nombre: str) -> Optional[Brand]:
        clave = (nombre or "").strip()
        if not clave or not conservar_marcas:
            return None
        if clave in marcas:
            return marcas[clave]
        b = db.query(Brand).filter(Brand.organization_id == org_id, Brand.name == clave).first()
        if b is None:
            b = Brand(name=clave, organization_id=org_id)
            db.add(b)
            db.flush()
            resumen["marcas_creadas"] += 1
        marcas[clave] = b
        return b

    def _existente(codigo: str, nombre: str) -> Optional[ProductVariant]:
        """Identidad = (codigo de barras, nombre). El SKU no sirve: el repetido recibe sufijo."""
        q = (
            db.query(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .filter(
                ProductVariant.organization_id == org_id,
                ProductVariant.deleted_at.is_(None),
                Product.deleted_at.is_(None),
                Product.name == nombre,
            )
        )
        q = q.filter(ProductVariant.barcode == codigo) if codigo else q.filter(ProductVariant.barcode.is_(None))
        return q.first()

    try:
        for nfila, f in leer_export(ruta_xlsx):
            sku_archivo = (f.get("sku") or "").strip()
            nombre = (f.get("nombre") or "").strip()
            codigo = (f.get("codigo") or "").strip()
            etiqueta = sku_archivo or codigo or f"fila {nfila}"

            if not nombre:
                resumen["omitidos"] += 1
                resumen["incidencias"].append(f"fila {nfila} ({etiqueta}): sin nombre, se omite")
                continue

            precio = _num(f.get("precio"), "Precio Base", nfila)
            if not _positivo(precio):
                resumen["incidencias"].append(
                    f"{etiqueta}: sin Precio Base, la variante se carga con precio 0 — corrigelo antes de venderla"
                )
            try:
                costo = _num(f.get("costo"), "Costo", nfila)
            except ValueError:
                resumen["incidencias"].append(
                    f"{etiqueta}: Costo ilegible ({(f.get('costo') or '').strip()!r}), se carga como 0"
                )
                costo = None
            iva = _si(f.get("iva"))

            empaques = [k for k in f if (k.startswith("e") and k[1:2].isdigit() or k.endswith("_empaque")) and f[k]]
            if empaques:
                resumen["incidencias"].append(
                    f"{etiqueta}: trae empaques ({', '.join(sorted(empaques))}) — la carga no crea empaques, capturalos a mano"
                )

            dep = _departamento(f.get("departamento") or "")
            marca = _marca(f.get("marca") or "")
            variante = _existente(codigo, nombre)

            if variante is None:
                sku = sku_archivo or codigo or _sku_desde_nombre(nombre)
                generado = not sku_archivo
                if sku in usados:
                    base, i = sku, 2
                    while f"{base}-{i}" in usados:
                        i += 1
                    sku = f"{base}-{i}"
                    generado = True
                    resumen["incidencias"].append(
                        f"{etiqueta}: SKU repetido en la organizacion, la variante recibio {sku} (el codigo de barras no cambia)"
                    )
                if generado:
                    resumen["codigos_generados"] += 1
                usados.add(sku)

                producto = Product(
                    name=nombre,
                    description=(f.get("descripcion") or "").strip() or None,
                    organization_id=org_id,
                    department_id=dep.id if dep is not None else None,
                    brand_id=marca.id if marca is not None else None,
                    is_active=True,
                )
                db.add(producto)
                db.flush()

                variante = ProductVariant(
                    product_id=producto.id,
                    sku=sku,
                    barcode=codigo or None,
                    variant_name="Estándar",
                    price=precio if precio is not None else Decimal("0"),
                    cost=costo if costo is not None else Decimal("0"),
                    has_iva=iva,
                    organization_id=org_id,
                )
                db.add(variante)
                db.flush()
                resumen["creados"] += 1
            else:
                producto = variante.product
                producto.department_id = dep.id if dep is not None else None
                if marca is not None:
                    producto.brand_id = marca.id
                if f.get("descripcion"):
                    producto.description = f["descripcion"].strip()
                if precio is not None:
                    variante.price = precio
                elif variante.price is None:
                    variante.price = Decimal("0")
                if costo is not None:
                    variante.cost = costo
                elif variante.cost is None:
                    variante.cost = Decimal("0")
                variante.has_iva = iva
                resumen["actualizados"] += 1

            _cargar_escalones(db, org_id, variante, f, nfila, etiqueta, resumen)
            _estado_en_sucursal(db, org_id, branch_id, variante)
            _existencias(db, org_id, branch_id, variante, f, nfila, etiqueta, admin, tope, resumen)

        if dry_run:
            db.rollback()
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    return resumen


def _cargar_escalones(db, org_id, variante, f, nfila, etiqueta, resumen) -> None:
    """Tarea 4."""


def _estado_en_sucursal(db, org_id, branch_id, variante) -> None:
    """Habilita el producto en la sucursal (rmazh no exporta minimo/maximo)."""
    pbs = (
        db.query(ProductBranchStatus)
        .filter(
            ProductBranchStatus.organization_id == org_id,
            ProductBranchStatus.variant_id == variante.id,
            ProductBranchStatus.branch_id == branch_id,
        )
        .first()
    )
    if pbs is None:
        db.add(
            ProductBranchStatus(
                variant_id=variante.id,
                branch_id=branch_id,
                organization_id=org_id,
                is_active_pos=True,
                is_visible=True,
            )
        )


def _existencias(db, org_id, branch_id, variante, f, nfila, etiqueta, admin, tope, resumen) -> None:
    """Tarea 4."""


def main() -> None:
    """Tarea 5."""


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Correr y ver que pasan**

Run: `python3 -m pytest -q -p no:warnings tests/test_import_rmazh_export.py`
Expected: 15 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/import_rmazh_export.py tests/test_import_rmazh_export.py
git commit -m "feat(scripts): importador del catalogo exportado por rmazh (lector y catalogo base)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014rnFXXn9to8upxnFg1bpw8"
```

---

### Task 4: escalones con nombre original y existencias con tope y lista de revisión

**Files:**
- Modify: `scripts/import_rmazh_export.py` (rellenar `_cargar_escalones` y `_existencias`)
- Test: `tests/test_import_rmazh_export.py` (añadir clases)

**Interfaces:**
- Consumes: la firma de `import_rmazh_export` y las constantes de la Tarea 3.
- Produces: `resumen["escalones"]`, `resumen["movimientos"]`, `resumen["existencias_altas"]: list[tuple[str, str, Decimal]]`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Añadir a `tests/test_import_rmazh_export.py`:

```python
class TestEscalones:
    def test_un_escalon_con_su_nombre_y_minimo(self, db, cargar):
        r = cargar([CASCANUECES])
        assert r["escalones"] == 1
        e = db.query(ProductPrice).one()
        assert e.price_name == "Mayoreo"
        assert Decimal(str(e.min_quantity)) == 3 and Decimal(str(e.unit_price)) == 210

    def test_dos_escalones_conservan_caja(self, db, cargar):
        r = cargar([STITCH])
        assert r["escalones"] == 2
        nombres = {e.price_name: (Decimal(str(e.min_quantity)), Decimal(str(e.unit_price))) for e in db.query(ProductPrice)}
        assert nombres == {"Mayoreo": (Decimal("3"), Decimal("120")), "Caja": (Decimal("12"), Decimal("100"))}

    def test_nombres_numerados_de_rmazh_se_respetan(self, db, cargar):
        cargar([dict(CASCANUECES, **{"P1 Nombre": "Precio 1", "P2 Nombre": "Precio 2", "P2 Min": 6, "P2 Precio": 200})])
        assert {e.price_name for e in db.query(ProductPrice)} == {"Precio 1", "Precio 2"}

    def test_min_vacio_es_uno(self, db, cargar):
        cargar([dict(CASCANUECES, **{"P1 Min": ""})])
        assert Decimal(str(db.query(ProductPrice).one().min_quantity)) == 1

    def test_escalon_sin_precio_no_se_crea_y_avisa(self, db, cargar):
        r = cargar([dict(CASCANUECES, **{"P1 Precio": ""})])
        assert db.query(ProductPrice).count() == 0
        assert any("Mayoreo" in i and "sin precio" in i for i in r["incidencias"])

    def test_escalon_mas_caro_que_el_base_se_carga_y_avisa(self, db, cargar):
        """Review Focus #1: no se corrige en silencio."""
        r = cargar([dict(CASCANUECES, **{"P1 Precio": 300})])
        assert Decimal(str(db.query(ProductPrice).one().unit_price)) == 300
        assert any("mayor que el Precio Base" in i for i in r["incidencias"])

    def test_recorrer_refresca_el_escalon_sin_duplicarlo(self, db, cargar):
        cargar([CASCANUECES])
        cargar([dict(CASCANUECES, **{"P1 Precio": 205})])
        e = db.query(ProductPrice).one()
        assert Decimal(str(e.unit_price)) == 205


class TestExistencias:
    def test_stock_entra_como_movimiento_con_referencia(self, db, org, branch_a, admin_user, cargar):
        r = cargar([CASCANUECES])
        assert r["movimientos"] == 1
        s = db.query(StockOnHand).filter_by(branch_id=branch_a.id).one()
        assert Decimal(str(s.qty_on_hand)) == 2556 and s.is_active is True
        m = db.query(InventoryMovement).one()
        assert m.movement_type == MovementType.ADJUSTMENT_IN
        assert m.reference == imp.REFERENCIA_CARGA
        assert Decimal(str(m.qty_change)) == 2556 and Decimal(str(m.qty_before)) == 0 and Decimal(str(m.qty_after)) == 2556
        assert m.user_id == admin_user.id
        assert m.organization_id == org.id

    def test_stock_cero_crea_fila_sin_movimiento(self, db, branch_a, cargar):
        r = cargar([dict(CASCANUECES, Stock=0)])
        assert r["movimientos"] == 0
        assert db.query(StockOnHand).filter_by(branch_id=branch_a.id).count() == 1
        assert db.query(InventoryMovement).count() == 0

    def test_mayores_a_500_se_listan_y_entran_tal_cual(self, db, cargar):
        r = cargar([CASCANUECES, STITCH])
        assert sorted(r["existencias_altas"]) == [
            ("8888172121301", "CASCANUECES", Decimal("2556")),
            ("STITCH", "STITCH", Decimal("10000")),
        ]
        qty = {v.sku: Decimal(str(s.qty_on_hand)) for s, v in db.query(StockOnHand, ProductVariant).join(ProductVariant, ProductVariant.id == StockOnHand.variant_id)}
        assert qty == {"8888172121301": Decimal("2556"), "STITCH": Decimal("10000")}

    def test_tope_recorta_y_avisa(self, db, cargar):
        r = cargar([STITCH, dict(CASCANUECES, Stock=40)], tope=Decimal("50"))
        qty = {v.sku: Decimal(str(s.qty_on_hand)) for s, v in db.query(StockOnHand, ProductVariant).join(ProductVariant, ProductVariant.id == StockOnHand.variant_id)}
        assert qty == {"STITCH": Decimal("50"), "8888172121301": Decimal("40")}
        assert any("STITCH" in i and "tope" in i for i in r["incidencias"])
        assert Decimal(str(db.query(InventoryMovement).filter_by(variant_id=db.query(ProductVariant).filter_by(sku="STITCH").one().id).one().qty_change)) == 50
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_import_rmazh_export.py -k "Escalones or Existencias"`
Expected: 11 FAIL (los stubs no escriben nada: `escalones == 0`, `NoResultFound`).

- [ ] **Step 3: Rellenar `_cargar_escalones`**

Reemplazar el stub en `scripts/import_rmazh_export.py`:

```python
def _cargar_escalones(db, org_id, variante, f, nfila, etiqueta, resumen) -> None:
    """Un ProductPrice por cada Pn con nombre, CON SU NOMBRE ORIGINAL.

    En este repo "Caja" no es una etiqueta sino un comportamiento (el carrito
    arma renglones de caja con el escalon cuyo nombre contiene "caja" y trata
    `min_quantity` como piezas por caja). rmazh comparte ese flujo, asi que
    respetar el nombre es respetar la intencion de la tienda.
    """
    actuales = {
        p.price_name: p
        for p in db.query(ProductPrice).filter(
            ProductPrice.organization_id == org_id,
            ProductPrice.variant_id == variante.id,
        )
    }
    precio_base = Decimal(str(variante.price or 0))
    for n in range(1, 6):
        nombre = (f.get(f"p{n}_nombre") or "").strip()
        if not nombre:
            continue
        precio = _positivo(_num(f.get(f"p{n}_precio"), f"P{n} Precio", nfila))
        if precio is None:
            resumen["incidencias"].append(
                f"{etiqueta}: escalon {nombre} sin precio valido — no se creo"
            )
            continue
        if precio_base and precio > precio_base:
            resumen["incidencias"].append(
                f"{etiqueta}: escalon {nombre} (${precio}) mayor que el Precio Base (${precio_base}) — se carga igual, revisalo"
            )
        minimo = _num(f.get(f"p{n}_min"), f"P{n} Min", nfila) or Decimal("1")

        escalon = actuales.get(nombre)
        if escalon is None:
            db.add(
                ProductPrice(
                    variant_id=variante.id,
                    price_name=nombre,
                    min_quantity=minimo,
                    unit_price=precio,
                    organization_id=org_id,
                )
            )
        else:
            escalon.min_quantity = minimo
            escalon.unit_price = precio
        resumen["escalones"] += 1
```

- [ ] **Step 4: Rellenar `_existencias`**

Reemplazar el stub:

```python
def _existencias(db, org_id, branch_id, variante, f, nfila, etiqueta, admin, tope, resumen) -> None:
    """Carga el stock inicial como movimiento de inventario, una sola vez."""
    stock = _num(f.get("stock"), "Stock", nfila) or Decimal("0")
    if tope is not None and stock > tope:
        resumen["incidencias"].append(
            f"{etiqueta}: existencias {stock} recortadas al tope {tope}"
        )
        stock = tope
    if stock > UMBRAL_EXISTENCIAS_ALTAS:
        resumen["existencias_altas"].append((variante.sku, variante.product.name, stock))

    existencias = (
        db.query(StockOnHand)
        .filter(
            StockOnHand.organization_id == org_id,
            StockOnHand.variant_id == variante.id,
            StockOnHand.branch_id == branch_id,
        )
        .first()
    )
    if existencias is None:
        existencias = StockOnHand(
            variant_id=variante.id,
            branch_id=branch_id,
            organization_id=org_id,
            qty_on_hand=Decimal("0"),
            is_active=True,
        )
        db.add(existencias)
        db.flush()

    if stock <= 0:
        return

    ya_cargado = (
        db.query(InventoryMovement)
        .filter(
            InventoryMovement.organization_id == org_id,
            InventoryMovement.branch_id == branch_id,
            InventoryMovement.variant_id == variante.id,
            InventoryMovement.reference == REFERENCIA_CARGA,
        )
        .first()
    )
    if ya_cargado is not None:
        return

    antes = Decimal(str(existencias.qty_on_hand or 0))
    existencias.qty_on_hand = antes + stock
    db.add(
        InventoryMovement(
            branch_id=branch_id,
            variant_id=variante.id,
            user_id=admin.id if admin is not None else None,
            movement_type=MovementType.ADJUSTMENT_IN,
            qty_change=stock,
            qty_before=antes,
            qty_after=existencias.qty_on_hand,
            reference=REFERENCIA_CARGA,
            notes=f"Fila {nfila} de la exportacion de rmazh",
            organization_id=org_id,
        )
    )
    resumen["movimientos"] += 1
```

- [ ] **Step 5: Correr y ver que pasan**

Run: `python3 -m pytest -q -p no:warnings tests/test_import_rmazh_export.py`
Expected: 26 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/import_rmazh_export.py tests/test_import_rmazh_export.py
git commit -m "feat(scripts): escalones con nombre original y existencias con tope en el importador de rmazh

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014rnFXXn9to8upxnFg1bpw8"
```

---

### Task 5: idempotencia, dry-run y CLI del importador

**Files:**
- Modify: `scripts/import_rmazh_export.py` (rellenar `main`)
- Test: `tests/test_import_rmazh_export.py` (añadir clases)

- [ ] **Step 1: Escribir las pruebas que fallan**

Añadir a `tests/test_import_rmazh_export.py`:

```python
class TestIdempotencia:
    def test_segunda_corrida_no_duplica_ni_recarga_stock(self, db, org, cargar):
        cargar([CASCANUECES, STITCH])
        r = cargar([CASCANUECES, STITCH])
        assert r["creados"] == 0 and r["actualizados"] == 2
        assert db.query(Product).filter(Product.organization_id == org.id).count() == 2
        assert db.query(ProductVariant).count() == 2
        assert db.query(ProductPrice).count() == 3
        assert db.query(InventoryMovement).count() == 2, "el stock no se vuelve a cargar"
        qty = {v.sku: Decimal(str(s.qty_on_hand)) for s, v in db.query(StockOnHand, ProductVariant).join(ProductVariant, ProductVariant.id == StockOnHand.variant_id)}
        assert qty == {"8888172121301": Decimal("2556"), "STITCH": Decimal("10000")}

    def test_renglon_duplicado_en_el_mismo_archivo(self, db, cargar):
        """Review Focus #2: misma (codigo, nombre) dos veces = un producto, un movimiento."""
        r = cargar([CASCANUECES, dict(CASCANUECES, Stock=999)])
        assert r["creados"] == 1 and r["actualizados"] == 1
        assert db.query(Product).count() == 1
        assert db.query(InventoryMovement).count() == 1
        assert Decimal(str(db.query(StockOnHand).one().qty_on_hand)) == 2556


class TestDryRun:
    def test_dry_run_reporta_sin_escribir(self, db, org, cargar):
        r = cargar([CASCANUECES, STITCH], dry_run=True)
        assert r["creados"] == 2 and r["escalones"] == 3 and r["movimientos"] == 2
        assert len(r["existencias_altas"]) == 2
        assert db.query(Product).filter(Product.organization_id == org.id).count() == 0
        assert db.query(InventoryMovement).count() == 0
        assert db.query(Department).count() == 0


class TestCLI:
    def test_pos_search_lee_lo_cargado(self, db, org, branch_a, cargar):
        """Lo que tumba al POS es un NULL en price/cost: el schema de lectura debe aceptar todo."""
        from app.modules.products.schemas import ProductRead
        cargar([CASCANUECES, dict(STITCH, Costo="")])
        for p in db.query(Product).filter(Product.organization_id == org.id):
            ProductRead.model_validate(p)

    def test_main_dry_run_imprime_resumen(self, db, org, branch_a, admin_user, tmp_path, monkeypatch, capsys):
        import sys as _sys
        ruta = _xlsx(tmp_path, [CASCANUECES, STITCH])
        monkeypatch.setattr(_sys, "argv", ["import_rmazh_export.py", ruta, "--org", str(org.id), "--branch", str(branch_a.id), "--dry-run"])
        # El CLI abre su propia sesion; se le presta la de la prueba.
        import app.core.database as database
        monkeypatch.setattr(database, "SessionLocal", lambda: db)
        monkeypatch.setattr(db, "close", lambda: None)
        imp.main()
        out = capsys.readouterr().out
        assert "ENSAYO" in out and "productos creados      2" in out
        assert "EXISTENCIAS MAYORES A 500" in out and "STITCH" in out and "10000" in out
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `python3 -m pytest -q -p no:warnings tests/test_import_rmazh_export.py -k "Idempotencia or DryRun or CLI"`
Expected: `test_main_dry_run_imprime_resumen` FAIL (el stub de `main` no imprime); los demás PASS (la idempotencia ya la dan las tareas 3 y 4; si alguno falla, es un defecto real a corregir antes de seguir).

- [ ] **Step 3: Rellenar `main`**

Reemplazar el stub:

```python
def main() -> None:
    p = argparse.ArgumentParser(description="Carga de catalogo desde la exportacion de rmazh")
    p.add_argument("xlsx")
    p.add_argument("--org", type=int, required=True)
    p.add_argument("--branch", type=int, required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--tope", type=Decimal, default=None, help="recorta las existencias a este maximo")
    p.add_argument("--conservar-departamentos", action="store_true")
    p.add_argument("--conservar-marcas", action="store_true")
    args = p.parse_args()

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        try:
            org, sucursal = validar_destino(db, args.org, args.branch)
        except ValueError as e:
            print(f"ABORTADO: {e}", file=sys.stderr)
            raise SystemExit(2)
        print("=" * 60)
        print("ENSAYO (nada se guarda)" if args.dry_run else "CARGA REAL")
        print(f"  organizacion  {org.name} (id={org.id})")
        print(f"  sucursal      {sucursal.name} (id={sucursal.id})")
        print(f"  archivo       {args.xlsx}")
        if args.tope is not None:
            print(f"  tope          {args.tope}")
        print("=" * 60)

        r = import_rmazh_export(
            db, args.xlsx, args.org, args.branch,
            dry_run=args.dry_run, tope=args.tope,
            conservar_departamentos=args.conservar_departamentos,
            conservar_marcas=args.conservar_marcas,
        )
    finally:
        db.close()

    print("=" * 60)
    print("ENSAYO — nada se guardo" if args.dry_run else "CARGA APLICADA")
    print(f"  organizacion           {r['organizacion']}")
    print(f"  sucursal               {r['sucursal']}")
    print(f"  productos creados      {r['creados']}")
    print(f"  productos actualizados {r['actualizados']}")
    print(f"  renglones omitidos     {r['omitidos']}")
    print(f"  escalones de precio    {r['escalones']}")
    print(f"  movimientos de stock   {r['movimientos']}")
    print(f"  departamentos creados  {r['departamentos_creados']}")
    print(f"  marcas creadas         {r['marcas_creadas']}")
    print(f"  codigos generados      {r['codigos_generados']}")
    print(f"  incidencias            {len(r['incidencias'])}")
    for inc in r["incidencias"]:
        print("   ·", inc)
    if r["existencias_altas"]:
        print("-" * 60)
        print(f"EXISTENCIAS MAYORES A {UMBRAL_EXISTENCIAS_ALTAS} ({len(r['existencias_altas'])} renglones) — para revisar con la duena:")
        for sku, nombre, qty in sorted(r["existencias_altas"], key=lambda t: -t[2]):
            print(f"   {qty:>10}  {sku:<16} {nombre}")
    print("=" * 60)
```

- [ ] **Step 4: Correr todo el archivo**

Run: `python3 -m pytest -q -p no:warnings tests/test_import_rmazh_export.py`
Expected: 31 passed.

- [ ] **Step 5: Suite completa sin nuevos rojos**

Run: `python3 -m pytest -q -p no:warnings --ignore=tests/test_cash_complete.py 2>&1 | tail -3`
Expected: el conteo de `failed` es el mismo que en `main` (comparar con `git stash -u && … && git stash pop` si hay duda). Los tres archivos nuevos en verde.

- [ ] **Step 6: Commit**

```bash
git add scripts/import_rmazh_export.py tests/test_import_rmazh_export.py
git commit -m "feat(scripts): CLI, dry-run e idempotencia del importador de rmazh

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014rnFXXn9to8upxnFg1bpw8"
```

---

### Task 6: ensayo local de punta a punta con la exportación real de Coqueta

Sin producción, sin Railway. Se repite en una SQLite de archivo todo el alta con el xlsx real que ya está en el scratchpad, para ver el resumen real (218 renglones) antes de tocar nada.

**Files:**
- Create (scratchpad, no versionado): `/tmp/claude-1000/-mnt-d-Devs-atlas-one/e35ce3ce-1728-4f1c-8340-59ba97d45264/scratchpad/ensayo_coqueta.sh`
- Lee: `…/scratchpad/coqueta_catalogo.xlsx`, `…/scratchpad/coqueta_users.json` (ya existen, generados el 2026-09-30 en solo lectura desde rmazh)

- [ ] **Step 1: Escribir el guion de ensayo**

```bash
#!/usr/bin/env bash
# Ensayo local del alta de Coqueta sobre una SQLite de archivo. Nada toca prod.
set -euo pipefail
S=/tmp/claude-1000/-mnt-d-Devs-atlas-one/e35ce3ce-1728-4f1c-8340-59ba97d45264/scratchpad
cd /mnt/d/Devs/atlas-one
rm -f "$S/coqueta_ensayo.db"
export DATABASE_URL="sqlite:///$S/coqueta_ensayo.db"

python3 - <<'EOF'
import app.models
from app.core.database import Base, engine
Base.metadata.create_all(engine)
print("tablas:", len(Base.metadata.tables))
EOF

python3 scripts/onboard_org.py --name "Novedades Coqueta" --industry ATLAS_POS \
  --admin Mirna --full-name Mirna --branch "Novedades Coqueta" | tee "$S/ensayo_onboard.txt"

ORG=$(python3 -c "import re;print(re.search(r'organization_id[^0-9]*(\d+)',open('$S/ensayo_onboard.txt').read()).group(1))")
BR=$(python3 -c "import re;print(re.search(r'branch_id[^0-9]*(\d+)',open('$S/ensayo_onboard.txt').read()).group(1))")
echo "org=$ORG branch=$BR"

python3 scripts/import_rmazh_users.py "$S/coqueta_users.json" --org "$ORG" --branch "$BR" --dry-run
python3 scripts/import_rmazh_users.py "$S/coqueta_users.json" --org "$ORG" --branch "$BR"

python3 scripts/import_rmazh_export.py "$S/coqueta_catalogo.xlsx" --org "$ORG" --branch "$BR" --dry-run | tee "$S/ensayo_dryrun.txt"
python3 scripts/import_rmazh_export.py "$S/coqueta_catalogo.xlsx" --org "$ORG" --branch "$BR" | tee "$S/ensayo_real.txt"
# Segunda corrida: debe dar 0 creados, 218 actualizados, 0 movimientos nuevos.
python3 scripts/import_rmazh_export.py "$S/coqueta_catalogo.xlsx" --org "$ORG" --branch "$BR" | tee "$S/ensayo_recorrida.txt"

python3 - <<EOF
from decimal import Decimal
import app.models
from app.core.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
q = lambda s: db.execute(text(s)).fetchall()
o = $ORG
print("productos", q(f"select count(*) from products where organization_id={o}")[0][0])
print("variantes", q(f"select count(*) from product_variants where organization_id={o}")[0][0])
print("escalones", q(f"select price_name,count(*) from product_prices where organization_id={o} group by 1"))
print("stock filas/piezas", q(f"select count(*),sum(qty_on_hand) from stock_on_hand where organization_id={o}")[0])
print("movimientos", q(f"select count(*) from inventory_movements where organization_id={o} and reference='Carga inicial rmazh'")[0][0])
print("cost null", q(f"select count(*) from product_variants where organization_id={o} and cost is null")[0][0])
print("usuarios", q(f"select u.username,u.role,u.branch_id,uo.org_role,(u.reprint_pin_hash is not null) from users u join user_organizations uo on uo.user_id=u.id where uo.organization_id={o}"))
print("deptos", q(f"select name from departments where organization_id={o}"), "marcas", q(f"select name from brands where organization_id={o}"))
EOF
```

- [ ] **Step 2: Correrlo**

Run: `bash /tmp/claude-1000/-mnt-d-Devs-atlas-one/e35ce3ce-1728-4f1c-8340-59ba97d45264/scratchpad/ensayo_coqueta.sh 2>&1 | tail -60`

Expected (contra lo medido en rmazh el 2026-09-30):

| Línea | Esperado |
|---|---|
| productos / variantes | 218 / 218 |
| escalones | Mayoreo 186, Caja 23, Precio 1 9, Precio 2 1 (total 219) |
| stock filas / piezas | 218 / 387473 |
| movimientos | 155 (218 menos los 63 en cero) |
| cost null | 0 |
| usuarios | Mirna ADMINISTRADOR ADMIN con PIN, Jose CAJERO MEMBER sin PIN, ambos en la sucursal |
| deptos / marcas | `[]` / `[]` |
| EXISTENCIAS MAYORES A 500 | 47 renglones, 30 con 10000 |
| recorrida | `productos creados 0`, `actualizados 218`, `movimientos de stock 0` |

Si algún conteo difiere, el defecto está en el importador (no en los datos): corregir en la tarea correspondiente, añadir la prueba que lo pinne, y repetir el ensayo.

- [ ] **Step 3: Guardar el resumen del dry-run para Mirna**

El bloque `EXISTENCIAS MAYORES A 500` de `ensayo_dryrun.txt` es la lista que se le entrega a la dueña (§2.4 del spec). Copiarlo a `…/scratchpad/coqueta_existencias_a_revisar.txt`. No se versiona.

- [ ] **Step 4: Sin commit** (nada del ensayo entra al repo). Borrar `coqueta_ensayo.db` al terminar.

---

### Task 7: documentación y memoria

**Files:**
- Modify: `CLAUDE.md` (§6 gotcha del `.venv`; §5 receta "Alta de una organización desde rmazh")
- Modify: `docs/DATA_MODEL.md` (columna `branches.folio_inicial`)
- Create: `/home/ecamposg/.claude/projects/-mnt-d-Devs-atlas-one/memory/coqueta-migracion.md` + línea en `MEMORY.md`

- [ ] **Step 1: CLAUDE.md**

En §3 (Comandos), cambiar la línea del venv por:

```
Requiere **Python 3.11+** y **Node 20**. Si existe `.venv/` úsalo; si no, el `python3` del sistema (3.12) ya trae las dependencias y corre la suite.
```

En §5 añadir la receta:

```
### Dar de alta una tienda que llega de rmazh (Data X POS)
1. Exportar desde rmazh en **solo lectura** con `scripts/adhoc/2026-09-01/coqueta/export_coq2.py` (repo Atlas-Rmazh, por `railway ssh`; pasar la sucursal con existencias, no el HQ). Guarda el xlsx y el JSON de usuarios **fuera del repo** (trae hashes).
2. `scripts/onboard_org.py` crea org + matriz (`can_sell=True`) + admin. Luego fija `branches.printer_name` y, si la tienda ya emitía folios, `branches.folio_inicial` (siguiente al último de rmazh).
3. `scripts/import_rmazh_users.py usuarios.json --org N --branch M --dry-run` → real. Copia los hashes bcrypt: la gente entra con su contraseña de siempre.
4. `scripts/import_rmazh_export.py catalogo.xlsx --org N --branch M --dry-run` → revisar incidencias y "EXISTENCIAS MAYORES A 500" → real. Idempotente; `--tope N` recorta relleno.
5. Verificar el POS **con el cajero**, no con el admin (`GET /api/products/pos/search`).
```

- [ ] **Step 2: DATA_MODEL.md**

En la tabla de `branches`, añadir la fila:

```
| `folio_inicial` | Integer, NULL | Primer folio que emite la sucursal en todas sus series; `get_next_folio` devuelve `max(máximo+1, folio_inicial)`. Para tiendas que llegan de otro sistema (Coqueta: 1464). |
```

- [ ] **Step 3: Memoria**

Crear `coqueta-migracion.md`:

```markdown
---
name: coqueta-migracion
description: "Novedades Coqueta (rmazh org 10, Railway) se muda a Atlas ONE con catálogo + existencias, folios desde 1464, usuarios con su hash; estado y pendientes del corte"
metadata:
  type: project
---

Novedades Coqueta vendía en **rmazh** (Data X POS, Railway proyecto "Rmazh POS", env beta), org 10,
sucursal 27 "Sucursal Principal" (impresora `POS-80`), usuarios **Mirna** (admin, con PIN) y
**Jose** Rivas (cajero, autor de las 1,463 ventas, último folio 1463 el 28/09/26). Decisión
2026-09-30: arranca en Atlas ONE con **catálogo + existencias**, el historial se queda en rmazh;
`branches.folio_inicial = 1464` para que no se repitan folios. Spec:
`docs/superpowers/specs/2026-09-30-coqueta-migracion-design.md`; rama `feat/coqueta-migracion`.

**Por qué importa:** cero escrituras en Railway; los hashes bcrypt `$2a$` son compatibles, así que
Mirna y Jose entran con su contraseña de siempre. Ningún importador previo leía el formato de
rmazh (`SKU, Nombre, …, P1..P5 Nombre/Min/Precio`): se creó `scripts/import_rmazh_export.py`
(+ `import_rmazh_users.py`).

**Trampas medidas:** 30 productos con exactamente 10,000 piezas (relleno) y 47 con más de 500 —
lista para Mirna en el dry-run; 3 devoluciones PENDING en rmazh (folios 1090, 1228, 1422) y la
caja 1862 abierta desde el 28/09 hay que cerrarlas allá antes del corte; departamento "Ncoqueta"
y marca "Rmazh" se descartan a propósito; rmazh también parece mudarse al VPS
(`/srv/backups/rmazh/`). Ver [[imaltzin-org-alta]], [[kaory-historico-railway]].

**Estado:** (actualizar al ejecutar la Tarea 8: ids de org/sucursal/usuarios en prod, fecha de
carga, folio de la venta de prueba, si Railway ya se apagó).
```

Y en `MEMORY.md` añadir:

```
- [Mudanza de Coqueta desde rmazh](coqueta-migracion.md) — catálogo + existencias, folios desde 1464, usuarios con su hash; importador nuevo import_rmazh_export.py; pendientes del corte
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/DATA_MODEL.md docs/superpowers/specs/2026-09-30-coqueta-migracion-design.md docs/superpowers/plans/2026-09-30-coqueta-migracion.md
git commit -m "docs: alta desde rmazh, folio_inicial y spec/plan de la mudanza de Coqueta

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_014rnFXXn9to8upxnFg1bpw8"
```

---

### Task 8: runbook de producción (manual, con permiso en cada escritura)

Nada de esto se ejecuta sin que el usuario lo autorice paso por paso. Cada bloque marcado **PERMISO** se detiene y pregunta. Si el clasificador de permisos bloquea un `docker exec` que escribe, se entrega el comando al usuario para que lo corra con `!`.

**Prerequisitos:** Tareas 1-7 en verde y confirmadas por el usuario; en la tienda: Jose cerró la caja 1862 y Mirna resolvió las 3 devoluciones PENDING (o el usuario acepta perderlas).

- [ ] **Step 1 — PERMISO: fusionar y desplegar `folio_inicial`**

```bash
cd /mnt/d/Devs/atlas-one
git checkout main && git merge --no-ff feat/coqueta-migracion -m "merge: importadores de rmazh y folio_inicial para la mudanza de Coqueta"
git push origin main
gh run watch --exit-status   # CI + deploy-ionos
ssh ionos 'docker exec atlas-one-prod cat /app/.commit_desplegado; echo; curl -fsS https://app.atlasone.com.mx/health'
ssh ionos 'docker exec atlas-one-prod python -c "
from app.core.database import SessionLocal; from sqlalchemy import text
print(SessionLocal().execute(text(\"select column_name from information_schema.columns where table_name=\x27branches\x27 and column_name=\x27folio_inicial\x27\")).fetchall())"'
```
Expected: commit desplegado = el del merge; `/health` 200; la columna existe. Comprobar que una venta de Kaory o Eleven ese día sigue su folio normal (`select max(folio) …` antes y después, o preguntar a la tienda).

- [ ] **Step 2 — PERMISO: respaldo**

El contenedor de Postgres del VPS se llama `postgres` (imagen `postgres:18-alpine`), el usuario de la base es `atlas_prod` y ya hay un cron que deja `atlas_one_prod_YYYYMMDD_033001.dump` a las 3:30 cada día. El respaldo manual sigue el nombre del de Kaory:

```bash
ssh ionos 'docker exec postgres pg_dump -U atlas_prod -d atlas_one_prod | gzip > /srv/backups/atlas_one_prod_antes_de_migrar_coqueta_$(date +%Y%m%d_%H%M).sql.gz && ls -la /srv/backups/atlas_one_prod_antes_de_migrar_coqueta_*'
```
Expected: archivo de unos 3 MB comprimido (el dump del 30/09 pesa 7 MB sin comprimir); `zcat … | head -3` muestra el encabezado de pg_dump.

- [ ] **Step 3 — Exportación fresca de rmazh (solo lectura, sin permiso extra)**

```bash
S=/tmp/claude-1000/-mnt-d-Devs-atlas-one/e35ce3ce-1728-4f1c-8340-59ba97d45264/scratchpad
railway ssh -i ~/.ssh/id_railway_atlas --project 0953bba5-3e8f-45e7-9f6d-e92055ea8a0a \
  --environment beta --service Atlas-API -- /opt/venv/bin/python < $S/export_coq2.py > $S/coq_export_raw_final.txt
# separar con el mismo python de la sesion del 30/09: ###USERS### -> coqueta_users_final.json, ###B64### -> coqueta_catalogo_final.xlsx
```
Anotar `max(folio)` y la hora de la última venta en rmazh en ese momento (script `coq_verif2.py`, solo lectura). Si Jose vendió después de la exportación, esas piezas se descuentan a mano al final.

- [ ] **Step 4 — PERMISO: alta de la organización**

```bash
ssh ionos 'docker exec atlas-one-prod python scripts/onboard_org.py --name "Novedades Coqueta" --industry ATLAS_POS --admin Mirna --full-name Mirna --branch "Novedades Coqueta"'
```
Expected: `created: True`, `admin_created: True`, ids nuevos (org 18, sucursal 21, usuario 41 o los que toquen). La contraseña impresa se ignora: el paso 6 pone la real. **Anotar `ORG` y `BR`.**

- [ ] **Step 5 — PERMISO: ajustes de la sucursal**

```bash
ssh ionos "docker exec atlas-one-prod python -c \"
from app.core.database import SessionLocal; from app.models.organization import Branch
db=SessionLocal(); b=db.query(Branch).get(BR)
assert b.organization_id==ORG, b.organization_id
b.printer_name='POS-80'; b.folio_inicial=1464; b.ticket_header=''; b.ticket_footer=''; b.can_sell=True
db.commit(); print(b.id,b.name,b.printer_name,b.folio_inicial,b.can_sell)\""
```
(Reemplazar `ORG` y `BR`.) Expected: `BR Novedades Coqueta POS-80 1464 True`.

- [ ] **Step 6 — PERMISO: usuarios**

```bash
scp $S/coqueta_users_final.json ionos:/tmp/coqueta_users.json
ssh ionos 'docker cp /tmp/coqueta_users.json atlas-one-prod:/tmp/coqueta_users.json && docker exec atlas-one-prod python scripts/import_rmazh_users.py /tmp/coqueta_users.json --org ORG --branch BR --dry-run'
ssh ionos 'docker exec atlas-one-prod python scripts/import_rmazh_users.py /tmp/coqueta_users.json --org ORG --branch BR && docker exec atlas-one-prod rm /tmp/coqueta_users.json && rm /tmp/coqueta_users.json'
```
Expected: dry-run `creados 1, actualizados 1` (Jose nuevo, Mirna actualizada); real igual. El JSON se borra del VPS y del contenedor en el mismo comando.

- [ ] **Step 7 — PERMISO: catálogo**

```bash
scp $S/coqueta_catalogo_final.xlsx ionos:/tmp/coqueta_catalogo.xlsx
ssh ionos 'docker cp /tmp/coqueta_catalogo.xlsx atlas-one-prod:/tmp/ && docker exec atlas-one-prod python scripts/import_rmazh_export.py /tmp/coqueta_catalogo.xlsx --org ORG --branch BR --dry-run' | tee $S/prod_dryrun.txt
# Revisar incidencias y la lista de existencias altas con el usuario. Luego:
ssh ionos 'docker exec atlas-one-prod python scripts/import_rmazh_export.py /tmp/coqueta_catalogo.xlsx --org ORG --branch BR' | tee $S/prod_real.txt
```
Expected: mismos conteos que el ensayo local (Tarea 6) salvo los productos que rmazh haya dado de alta desde el 30/09.

- [ ] **Step 8 — Verificación (solo lectura)**

```bash
ssh ionos 'docker exec atlas-one-prod python -c "
from app.core.database import SessionLocal; from sqlalchemy import text
db=SessionLocal(); q=lambda s: db.execute(text(s)).fetchall(); o=ORG
print(\"productos\", q(f\"select count(*) from products where organization_id={o} and is_active\"))
print(\"variantes\", q(f\"select count(*) from product_variants where organization_id={o} and deleted_at is null\"))
print(\"escalones\", q(f\"select price_name,count(*) from product_prices where organization_id={o} group by 1\"))
print(\"stock\", q(f\"select count(*),sum(qty_on_hand),count(*) filter (where qty_on_hand<0) from stock_on_hand where organization_id={o}\"))
print(\"cost null\", q(f\"select count(*) from product_variants where organization_id={o} and cost is null\"))
print(\"usuarios\", q(f\"select u.username,u.role::text,u.branch_id,uo.org_role,(u.reprint_pin_hash is not null) from users u join user_organizations uo on uo.user_id=u.id where uo.organization_id={o}\"))
print(\"sucursal\", q(f\"select id,name,can_sell,printer_name,folio_inicial from branches where organization_id={o}\"))"'
```
Y con el token de **Jose** (login por `POST /api/auth/login` en `app.atlasone.com.mx`):
```bash
curl -fsS -H "Authorization: Bearer $TOKEN_JOSE" "https://app.atlasone.com.mx/api/products/pos/search?q=cascanueces" | head -c 400
curl -fsS -H "Authorization: Bearer $TOKEN_JOSE" "https://app.atlasone.com.mx/api/branches/BR" | grep -o '"can_sell":[a-z]*'
```
Expected: conteos de §4 del spec; búsqueda 200 con resultados; `can_sell:true`.

- [ ] **Step 9 — En la tienda (usuario/Mirna):** instalar `atlas-print-agent-setup-3.1.0.exe`, dirección `https://app.atlasone.com.mx`, impresora `POS-80`. Entrar como Jose, abrir caja, venta de prueba, imprimir. Expected: ticket **A-1464** impreso. Decidir si se cancela.

- [ ] **Step 10 — Cierre:** actualizar la memoria `coqueta-migracion.md` con ids reales, fecha, folio de prueba y el estado del corte en rmazh (que hace el usuario desde su otra sesión). Si hubo ventas en rmazh entre la exportación y el apagado, descontarlas con ajustes de inventario en Atlas ONE y anotarlo.
