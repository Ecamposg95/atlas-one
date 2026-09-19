"""
MOONSHOT_ENGINE: Nucleus
DOMAIN: Identity & Access Management
STATUS: Stable
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

# Importaciones de tu proyecto
from app.core.database import get_db
from app.models import User
from app.models.organization import Organization, Branch
from app.models.users import UserOrganization
from app.schemas.users import UserCreate, UserRead, UserUpdate
from app.core.security import get_current_user, get_password_hash
from app.core.tenant_context import get_current_active_organization

router = APIRouter()

# --- 0. CONTEXTO COMPLETO (NEW) ---
@router.get("/me/context")
def read_user_context(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: Optional[int] = Depends(get_current_active_organization) # Can be None if platform admin with no header
):
    """
    Returns the resolved context for the frontend application.
    - User Info
    - Active Organization (with preset info)
    - Active Branch (explicit or derived)
    - Permissions/Roles
    - Context Type (HQ/BRANCH/MOBILE)
    """
    from app.core.role_permissions import get_allowed_templates, get_required_context

    ctx = {
        "user": {
            "id": current_user.id,
            "username": current_user.username,
            "full_name": current_user.full_name,
            "role": current_user.role.value if current_user.role else None,
            "platform_role": current_user.platform_role.value if current_user.platform_role else None,
            "branch_id": current_user.branch_id
        },
        "organization": None,
        "branch": None,
        "preset": None,
        "context_type": "HQ",  # Default
        "allowed_templates": []
    }

    # 1. Resolve Organization
    if org_id:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if org:
            ctx["organization"] = {
                "id": org.id,
                "name": org.name,
                "logo_url": org.logo_url
            }

            # Preset info
            if org.industry_type:
                ctx["preset"] = org.industry_type.value

            # 2. Resolve Branch
            if current_user.branch_id:
                branch = db.query(Branch).filter(Branch.id == current_user.branch_id).first()
                if branch and branch.organization_id == org_id:
                     ctx["branch"] = {
                         "id": branch.id,
                         "name": branch.name,
                         "branch_type": branch.branch_type.value if hasattr(branch.branch_type, 'value') else str(branch.branch_type),
                         "city": branch.city or None,
                         "latitude": float(branch.latitude) if branch.latitude is not None else None,
                         "longitude": float(branch.longitude) if branch.longitude is not None else None,
                     }

    # Flat aliases for frontend convenience
    ctx["branch_name"] = ctx["branch"]["name"] if ctx["branch"] else None
    ctx["org_name"] = ctx["organization"]["name"] if ctx["organization"] else None

    # 3. Determine Context Type
    if current_user.role:
        required_ctx = get_required_context(current_user.role)
        ctx["context_type"] = required_ctx

        # Override if user has branch assigned
        if current_user.branch_id and required_ctx != "MOBILE":
            ctx["context_type"] = "BRANCH"
        elif not current_user.branch_id and required_ctx != "MOBILE":
            ctx["context_type"] = "HQ"

    # 4. Get Allowed Templates
    if current_user.role:
        ctx["allowed_templates"] = get_allowed_templates(current_user.role)

    # 5. Enabled modules for the active org (E-gating, 2026-05-14)
    # Used by the frontend Sidebar to gate Atlas One stub items.
    # `core` is always considered enabled; other modules respect
    # OrganizationModule.is_enabled.
    ctx["enabled_modules"] = ["core"]
    if org_id:
        from app.models.modules import OrganizationModule
        enabled = (
            db.query(OrganizationModule.module_key)
            .filter(
                OrganizationModule.organization_id == org_id,
                OrganizationModule.is_enabled == True,  # noqa: E712
            )
            .all()
        )
        ctx["enabled_modules"] = sorted({"core", *(row[0] for row in enabled)})

    return ctx


# --- 1. LEER TODOS (READ) ---
@router.get("/", response_model=List[UserRead])
def read_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization) # [HARDENING] Required Context
):
    # Retrieve users belonging to the active organization
    users = db.query(User).join(UserOrganization).filter(
        UserOrganization.organization_id == org_id,
        UserOrganization.is_active == True,
    ).offset(skip).limit(limit).all()

    return users

# --- 2. LEER USUARIO ACTUAL (ME) ---
@router.get("/me", response_model=UserRead)
def read_user_me(current_user: User = Depends(get_current_user)):
    return current_user

# --- 3. LEER POR ID ---
@router.get("/{user_id}", response_model=UserRead)
def read_user_by_id(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization) # Ensure access within Org
):
    # Validar que el usuario buscado pertenezca a la misma organización
    user = db.query(User).join(UserOrganization).filter(
        User.id == user_id,
        UserOrganization.organization_id == org_id
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado en esta organización")
    return user

# --- 4. CREAR USUARIO (CREATE) ---
@router.post("/", response_model=UserRead)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    # Validar duplicados (globalmente por username?? O por org? Username suele ser único global en SaaS simple)
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")

    # Hashear password
    hashed_password = get_password_hash(user.password)

    # Branch validation
    effective_branch_id = user.branch_id
    if effective_branch_id:
        # verify branch belongs to org
        br = db.query(Branch).filter(Branch.id == effective_branch_id, Branch.organization_id == org_id).first()
        if not br:
             raise HTTPException(status_code=400, detail="La sucursal no pertenece a la organización activa")

    new_user = User(
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        password_hash=hashed_password,
        branch_id=effective_branch_id,
        # El PIN de reimpresión se hashea igual que la contraseña y nunca se
        # guarda en claro. Sin PIN en el alta queda NULL.
        reprint_pin_hash=get_password_hash(user.reprint_pin) if user.reprint_pin else None,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # [HARDENING] Link to Organization
    user_org = UserOrganization(
        user_id=new_user.id,
        organization_id=org_id,
        org_role="MEMBER", # Default
        is_active=True
    )
    db.add(user_org)
    db.commit()

    return new_user

# --- 5. ACTUALIZAR USUARIO (UPDATE) ---
@router.put("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    # 1. Buscar usuario en contexto de Org
    user_db = db.query(User).join(UserOrganization).filter(
        User.id == user_id,
        UserOrganization.organization_id == org_id
    ).first()

    if not user_db:
        raise HTTPException(status_code=404, detail="Usuario no encontrado o no pertenece a la organización")

    update_data = user_in.dict(exclude_unset=True)

    if 'password' in update_data:
        password_raw = update_data.pop('password')
        if password_raw:
            user_db.password_hash = get_password_hash(password_raw)

    # El PIN de reimpresión nunca pasa por el setattr genérico de abajo: el
    # modelo no tiene atributo `reprint_pin` (solo el hash), así que un setattr
    # crudo no persistiría nada. "" o null explícito borra el PIN; un valor
    # válido (ya filtrado por el schema) lo fija.
    if 'reprint_pin' in update_data:
        pin_raw = update_data.pop('reprint_pin')
        user_db.reprint_pin_hash = get_password_hash(pin_raw) if pin_raw else None

    for field, value in update_data.items():
        if hasattr(user_db, field):
            setattr(user_db, field, value)

    db.add(user_db)
    db.commit()
    db.refresh(user_db)
    return user_db

# --- 6. ELIMINAR/DESACTIVAR (SOFT DELETE) ---
@router.delete("/{user_id}", response_model=UserRead)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    user_db = db.query(User).join(UserOrganization).filter(
        User.id == user_id,
        UserOrganization.organization_id == org_id
    ).first()

    if not user_db:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if not user_db.is_active:
        raise HTTPException(status_code=400, detail="Este usuario ya estaba desactivado")

    user_db.is_active = False

    db.commit()
    db.refresh(user_db)
    return user_db
