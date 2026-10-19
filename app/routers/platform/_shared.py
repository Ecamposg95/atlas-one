"""Shared imports, helpers, and Pydantic schemas used across the
``app.routers.platform`` sub-package.

Created by the Sprint 5 split — keeps a single source of truth for
helpers that two or more sub-modules need (audit, whitelists, model
inspection helpers and user/org sync logic).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, field_validator
import json as _json
from datetime import datetime, timezone

from app.core.database import get_db
from app.models.organization import Organization
from app.models.users import User, UserOrganization, PlatformRole, Role as AppRole
from app.schemas.organization import OrganizationCreate, OrganizationRead, OrganizationUpdate
from app.schemas.branches import BranchCreate, BranchUpdate, BranchRead
from app.schemas.users import UserCreate, UserUpdate, UserRead as GlobalUserRead
from app.schemas.presets import IndustryPresetRead
from app.core.security import get_password_hash
from app.modules.platform.dependencies import require_platform_admin, require_superadmin


# --- Schemas Local
class AdminAssign(BaseModel):
    username: str
    password: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v):
        if v is not None and len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        return v


class IndustryPresetCreate(BaseModel):
    industry_type: str
    display_name: str
    description: Optional[str] = None
    modules: List[str] = []
    is_system: bool = False


class IndustryPresetUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    modules: Optional[List[str]] = None
    is_system: Optional[bool] = None
    is_deprecated: Optional[bool] = None


def _existing_tables(db: Session) -> set:
    """Return the set of existing public schema table names (cached per-call)."""
    from sqlalchemy import inspect
    return set(inspect(db.get_bind()).get_table_names())


def _safe_bulk_delete(db: Session, query, model, existing: set) -> int:
    """Run a bulk delete only if the model's table exists in DB."""
    tbl = getattr(model, "__tablename__", None)
    if not tbl or tbl not in existing:
        return 0
    n = query.delete(synchronize_session=False)
    db.flush()
    return n


# --- Audit Helper ---
def _audit(db: Session, user_id: int, action: str, entity_type: str, entity_id, details: str = ""):
    from app.models.platform import PlatformAuditLog
    db.add(PlatformAuditLog(
        actor_user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        payload=details or None,
    ))


# --- Whitelist constants for mass-assignment protection ---
_ORG_UPDATE_FIELDS = {
    "name", "legal_name", "email", "phone", "address", "logo_url",
    "tax_id", "tax_regime", "website", "timezone",
    "ticket_header", "ticket_footer", "printer_name",
    "industry_type", "status", "plan", "branding_config", "is_active", "perfil_ui",
    "latitude", "longitude", "maps_url",
}
_BRANCH_UPDATE_FIELDS = {
    "name", "address", "phone", "email", "is_active", "can_sell",
    "address_line1", "address_line2", "neighborhood", "city", "state",
    "postal_code", "country", "latitude", "longitude", "maps_url",
    "place_id", "timezone", "printer_name", "ticket_header",
    "ticket_footer", "paper_width_mm",
}
_USER_UPDATE_FIELDS = {"full_name", "email", "role", "branch_id", "is_active"}


# --- Helpers ---
def _sync_user_organization(db: Session, user_id: int, branch_id: int):
    """
    Ensures a user is associated with the organization of their branch.
    """
    from app.models.organization import Branch
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        return

    # Check if association already exists
    assoc = db.query(UserOrganization).filter(
        UserOrganization.user_id == user_id,
        UserOrganization.organization_id == branch.organization_id
    ).first()

    if not assoc:
        assoc = UserOrganization(
            user_id=user_id,
            organization_id=branch.organization_id,
            org_role="MEMBER",
            is_active=True
        )
        db.add(assoc)
        db.commit()
    return branch.organization_id
