"""Alta de una organizacion cliente en Atlas ONE.

Consolida lo que estaba repartido entre `seed_demo_orgs.py`, `init_users.py` y
`railway_init.py`, pero para clientes de verdad: sin productos de muestra, sin
correos `@atlasone.demo` y sin la contrasena `demo1234` que comparten las
organizaciones de demostracion.

Es idempotente: correrlo dos veces no duplica nada, asi que sirve tanto para dar
de alta como para rehacer un alta despues de restaurar una base.

Uso:
    python scripts/onboard_org.py --name "Novedades Ginebra" \
        --industry ATLAS_POS --admin ginebra
    python scripts/onboard_org.py --name "..." --industry ATLAS_POS \
        --admin ginebra --password "..." --branch "HQ - Novedades Ginebra"
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.models  # noqa: F401  (puebla la metadata antes de consultar)
from app.core.security import get_password_hash
from app.models.organization import Branch, Organization
from app.modules.tenants.models import BranchType, IndustryType
from app.modules.users.models import PlatformRole, Role, User, UserOrganization
from app.services.capabilities_service import apply_industry_preset


def generar_password() -> str:
    return secrets.token_urlsafe(18)


def _giro(nombre: str) -> IndustryType:
    try:
        return IndustryType[nombre]
    except KeyError:
        validos = ", ".join(sorted(t.name for t in IndustryType))
        raise ValueError(f"giro desconocido '{nombre}'. Validos: {validos}") from None


def onboard(
    db,
    *,
    name: str,
    industry: str,
    admin_username: str,
    branch_name: Optional[str] = None,
    password: Optional[str] = None,
    plan: str = "FREE",
    full_name: Optional[str] = None,
    email: Optional[str] = None,
) -> Dict[str, Any]:
    """Crea (o completa) la organizacion, su sucursal matriz y su administrador.

    Devuelve un resumen con los identificadores y la contrasena usada. La clave
    `created` dice si la organizacion se creo en esta corrida o ya existia.
    """
    from app.services.plans import claves_validas, es_plan_valido
    if not es_plan_valido(plan):
        raise ValueError(f"plan desconocido {plan!r}. Validos: {', '.join(claves_validas())}")
    tipo = _giro(industry)
    branch_name = branch_name or f"HQ - {name}"
    clave = password or generar_password()

    org = db.query(Organization).filter(Organization.name == name).first()
    creada = org is None
    if org is None:
        org = Organization(
            name=name,
            industry_type=tipo,
            is_active=True,
            plan=plan,
            status="ACTIVE",
        )
        db.add(org)
        db.commit()
        db.refresh(org)

    sucursal = (
        db.query(Branch)
        .filter(Branch.organization_id == org.id, Branch.name == branch_name)
        .first()
    )
    if sucursal is None:
        sucursal = Branch(
            name=branch_name,
            branch_type=BranchType.HQ,
            is_headquarters=True,
            is_active=True,
            can_sell=True,
            organization_id=org.id,
        )
        db.add(sucursal)
        db.commit()
        db.refresh(sucursal)

    admin = db.query(User).filter(User.username == admin_username).first()
    admin_creado = admin is None
    if admin is None:
        admin = User(
            username=admin_username,
            full_name=full_name or f"Administrador {name}",
            email=email,
            password_hash=get_password_hash(clave),
            role=Role.ADMINISTRADOR,
            platform_role=PlatformRole.NONE,
            branch_id=sucursal.id,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

    enlace = (
        db.query(UserOrganization)
        .filter(
            UserOrganization.user_id == admin.id,
            UserOrganization.organization_id == org.id,
        )
        .first()
    )
    if enlace is None:
        db.add(
            UserOrganization(
                user_id=admin.id,
                organization_id=org.id,
                is_active=True,
                org_role="ADMIN",
            )
        )
        db.commit()

    try:
        apply_industry_preset(db, org.id, tipo)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "organization_id": org.id,
        "organization": org.name,
        "industry": tipo.name,
        "plan": org.plan,
        "branch_id": sucursal.id,
        "branch": sucursal.name,
        "admin_user_id": admin.id,
        "admin_username": admin.username,
        # Solo es la contrasena real si el usuario se creo en esta corrida.
        "password": clave if admin_creado else None,
        "created": creada,
        "admin_created": admin_creado,
    }


def main() -> None:
    from app.services.plans import claves_validas

    p = argparse.ArgumentParser(description="Alta de una organizacion cliente")
    p.add_argument("--name", required=True)
    p.add_argument("--industry", required=True)
    p.add_argument("--admin", required=True, dest="admin_username")
    p.add_argument("--branch", dest="branch_name", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--plan", default="FREE", choices=claves_validas(), help="FREE, START, PRO, BUSINESS, SCALE o ULTRA_PLUS")
    p.add_argument("--full-name", dest="full_name", default=None)
    p.add_argument("--email", default=None)
    args = p.parse_args()

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        r = onboard(
            db,
            name=args.name,
            industry=args.industry,
            admin_username=args.admin_username,
            branch_name=args.branch_name,
            password=args.password,
            plan=args.plan,
            full_name=args.full_name,
            email=args.email,
        )
    finally:
        db.close()

    print("=" * 56)
    print("Organizacion:", r["organization"], f"(id={r['organization_id']})",
          "— creada" if r["created"] else "— ya existia")
    print("Giro:        ", r["industry"], "· plan", r["plan"])
    print("Sucursal:    ", r["branch"], f"(id={r['branch_id']})")
    print("Admin:       ", r["admin_username"], f"(id={r['admin_user_id']})")
    if r["password"]:
        print("Contrasena:  ", r["password"])
        print("             (no se vuelve a mostrar — guardala ahora)")
    else:
        print("Contrasena:   sin cambios, el usuario ya existia")
    print("=" * 56)


if __name__ == "__main__":
    main()
