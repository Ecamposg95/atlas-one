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
