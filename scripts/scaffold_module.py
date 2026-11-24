#!/usr/bin/env python3
"""Atlas BOS module scaffold.

Generates app/modules/<key>/{__init__,models,schemas,router}.py from the
skeleton template in docs/modules/MODULE_GUIDE.md §11.

Usage:
    python scripts/scaffold_module.py <key>            # creates module
    python scripts/scaffold_module.py <key> --stub     # creates router with no real endpoints (just /health)
    python scripts/scaffold_module.py <key> --force    # overwrite if dir exists

`<key>` must be snake_case (lowercase letters, digits, underscores).
The script does NOT modify app/main.py, scripts/init_presets_v2.py, or
frontend files — those steps are listed at the end of the run as a
manual checklist.
"""
import argparse
import os
import re
import sys
from pathlib import Path

# Repo root = parent of scripts/
REPO_ROOT = Path(__file__).resolve().parent.parent
MODULES_DIR = REPO_ROOT / "app" / "modules"

KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def to_camel(key: str) -> str:
    return "".join(part.capitalize() for part in key.split("_"))


def validate_key(key: str) -> None:
    if not KEY_PATTERN.match(key):
        raise SystemExit(
            f"❌ Invalid key '{key}'. Use snake_case: lowercase letters, digits, underscores; must start with a letter."
        )


def init_py(key: str, entity: str) -> str:
    return f'''"""Atlas BOS module - {key}.

DOMAIN: {entity}
STATUS: Beta
"""
'''


def models_py(key: str, entity: str, table: str) -> str:
    return f'''"""Atlas BOS modules/{key}/models — {entity}.

DOMAIN: {entity}
STATUS: Beta
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class {entity}(Base):
    __tablename__ = "{table}"

    id              = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organization.id"), nullable=False, index=True)
    branch_id       = Column(Integer, ForeignKey("branches.id"),     nullable=True)
    name            = Column(String, nullable=False)
    is_active       = Column(Boolean, default=True, nullable=False)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())

    organization = relationship("Organization")
    branch       = relationship("Branch")
'''


def schemas_py(key: str, entity: str) -> str:
    return f'''"""Atlas BOS modules/{key}/schemas — Pydantic v2."""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class {entity}Base(BaseModel):
    name: str
    branch_id: Optional[int] = None
    is_active: bool = True


class {entity}Create({entity}Base):
    pass


class {entity}Update(BaseModel):
    name: Optional[str] = None
    branch_id: Optional[int] = None
    is_active: Optional[bool] = None


class {entity}Read({entity}Base):
    id: int
    organization_id: int
    created_at: datetime

    class Config:
        from_attributes = True
'''


def router_py(key: str, entity: str, stub: bool) -> str:
    if stub:
        return f'''"""Atlas BOS modules/{key}/router — stub.

STATUS: Beta (placeholder). Only exposes /health for now.
Real endpoints land when this module is built out.
"""
from fastapi import APIRouter, Depends
from app.core.security import get_current_user
from app.models import User

router = APIRouter()


@router.get("/health")
def health(current_user: User = Depends(get_current_user)):
    return {{"module": "{key}", "status": "beta", "ready": False}}
'''

    return f'''"""Atlas BOS modules/{key}/router — REST API.

DOMAIN: {entity}
STATUS: Beta
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User
from app.modules.{key}.models  import {entity}
from app.modules.{key}.schemas import {entity}Create, {entity}Read, {entity}Update

router = APIRouter()


def _org_id(user: User) -> int:
    """Resolve the active org_id for the current user. Adjust if your app uses tenant_context."""
    org = getattr(user, "organization_id", None)
    if org is None:
        raise HTTPException(status_code=400, detail="No active organization in context")
    return org


@router.get("", response_model=List[{entity}Read])
def list_{key}(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query({entity})
        .filter(
            {entity}.organization_id == _org_id(current_user),
            {entity}.is_active == True,  # noqa: E712
        )
        .all()
    )


@router.post("", response_model={entity}Read, status_code=status.HTTP_201_CREATED)
def create_{key}(
    payload: {entity}Create,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = {entity}(organization_id=_org_id(current_user), **payload.dict())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{{item_id}}", response_model={entity}Read)
def get_{key}_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = (
        db.query({entity})
        .filter({entity}.id == item_id, {entity}.organization_id == _org_id(current_user))
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    return obj


@router.put("/{{item_id}}", response_model={entity}Read)
def update_{key}_item(
    item_id: int,
    payload: {entity}Update,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = (
        db.query({entity})
        .filter({entity}.id == item_id, {entity}.organization_id == _org_id(current_user))
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    for field, value in payload.dict(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{{item_id}}", status_code=status.HTTP_204_NO_CONTENT)
def delete_{key}_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    obj = (
        db.query({entity})
        .filter({entity}.id == item_id, {entity}.organization_id == _org_id(current_user))
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(obj)
    db.commit()
'''


def write_file(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"❌ {path} already exists. Use --force to overwrite.")
    path.write_text(content, encoding="utf-8")
    print(f"  ✓ wrote {path.relative_to(REPO_ROOT)}")


def scaffold(key: str, *, stub: bool, force: bool) -> None:
    validate_key(key)
    entity = to_camel(key).rstrip("s") or to_camel(key)  # naive singular
    if entity.endswith("ss"):  # don't strip business → busines
        entity = to_camel(key)
    table = key

    target = MODULES_DIR / key
    if target.exists() and not force:
        raise SystemExit(
            f"❌ {target} already exists. Use --force to overwrite, or pick another key."
        )

    target.mkdir(parents=True, exist_ok=True)
    print(f"📁 Scaffolding app/modules/{key}/ (entity={entity}, table={table}, stub={stub})")

    write_file(target / "__init__.py", init_py(key, entity), force)
    if not stub:
        write_file(target / "models.py", models_py(key, entity, table), force)
        write_file(target / "schemas.py", schemas_py(key, entity), force)
    write_file(target / "router.py", router_py(key, entity, stub), force)

    print()
    print("✅ Scaffold complete. Manual follow-up checklist:")
    print()
    print(f"  □ app/main.py:")
    print(f"      from app.modules.{key}.router import router as {key}_router")
    print(f'      app.include_router({key}_router, prefix="/api/{key}", tags=["{entity}"])')
    print()
    if not stub:
        print(f"  □ scripts/railway_init.py run_migrations(): add CREATE TABLE / column DDL if needed")
    print(f"  □ scripts/init_presets_v2.py MODULES_CATALOG: add tuple for '{key}'")
    print(f"  □ app/services/estado_modulos.py ESTADO_MODULOS: declare '{key}' (oculto until it has backend + screen)")
    print(f"      and mirror it in frontend/src/utils/estadoModulos.ts (see CLAUDE.md §5 «Destapar un módulo»)")
    print(f"  □ scripts/init_presets_v2.py MODULE_UPSELL: add entry for '{key}'")
    print(f"  □ scripts/init_presets_v2.py PRESETS: add '{key}' to the relevant ATLAS_ONE_* preset(s)")
    print(f"  □ frontend/src/api/{key}.ts: create client (see frontend/src/api/customers.ts for pattern)")
    print(f"  □ frontend/src/pages/{key}/: create page(s)")
    print(f"  □ frontend/src/App.tsx: add <Route path='{key}' element={{...}}/>")
    print(f"  □ frontend/src/components/layout/Sidebar.tsx: add nav item")
    print(f"  □ tests/test_{key}_*.py: TDD a few smoke tests")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold a new Atlas BOS module under app/modules/.")
    parser.add_argument("key", help="Module key in snake_case (matches OrganizationModule.module_key).")
    parser.add_argument("--stub", action="store_true", help="Only generate a /health endpoint (no models/schemas).")
    parser.add_argument("--force", action="store_true", help="Overwrite existing module dir.")
    args = parser.parse_args()
    scaffold(args.key, stub=args.stub, force=args.force)


if __name__ == "__main__":
    main()
