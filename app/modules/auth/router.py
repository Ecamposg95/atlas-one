from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from app.core.security.cookies import cookie_segura
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import List, Optional
from app.core.database import get_db
from app.core.security import verify_pin, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, get_current_user
from app.schemas.auth import Token, TokenWithUser
from app.crud.users import get_user_by_username
from app.models.users import User, Role, PlatformRole, UserOrganization
from app.models.organization import Branch, Organization, BranchType

router = APIRouter()

# Eliminamos LoginRequest y usamos el estándar OAuth2PasswordRequestForm
@router.post("/login", response_model=TokenWithUser)
async def login_for_access_token(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(), # <--- ESTO CAMBIA TODO
    db: Session = Depends(get_db)
):
    # 1. Buscar usuario
    user = get_user_by_username(db, username=form_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario incorrecto",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Verificar PIN
    # NOTA: OAuth2 siempre envía los campos como 'username' y 'password'.
    # Nosotros usaremos el campo 'password' para recibir el PIN.
    if not verify_pin(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="PIN incorrecto",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Determine Initial Context
    # Default context is the user's branch. If no branch, it might be HQ.
    # [FIX] Admins/Owners always default to HQ context initially, even if assigned to a branch.
    if user.role in [Role.ADMINISTRADOR, Role.DUEÑO] or user.platform_role == PlatformRole.SUPERADMIN:
        ctx_id = None
        ctx_type = "HQ"
    else:
        ctx_id = user.branch_id
        ctx_type = "HQ" if ctx_id is None else "BRANCH"

    # 4. Generar Token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": user.username,
            "role": user.role.value,
            "ctx_id": ctx_id,
            "ctx_type": ctx_type
        },
        expires_delta=access_token_expires
    )

    # [NEW] Set Cookie for Server-Side Rendering checks
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True, # Prevent JS access for security
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=cookie_segura(request),  # COOKIE_SECURE: auto = solo por https
    )

    # 5. Resolver organización del usuario via UserOrganization
    # Solo membresías activas y en orden fijo (misma regla que el contexto).
    from app.core.tenant_context import membresia_principal
    user_org = membresia_principal(db, user.id)
    org = None
    org_id = None
    if user_org:
        org_id = user_org.organization_id
        org = db.query(Organization).filter(Organization.id == org_id).first()

    branch_obj = None
    if user.branch_id:
        branch_obj = db.query(Branch).filter(Branch.id == user.branch_id).first()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value if user.role else "CAJERO",
            "platform_role": user.platform_role.value if user.platform_role else "NONE",
            "branch_id": user.branch_id,
            "organization_id": org_id,
            "is_active": user.is_active,
        },
        "organization": {
            "id": org.id,
            "name": org.name,
            "industry_type": org.industry_type.value if org.industry_type else None,
            "hq_branch_id": org.hq_branch_id,
        } if org else None,
        "branch": {
            "id": branch_obj.id,
            "name": branch_obj.name,
            "branch_type": branch_obj.branch_type.value,
            "is_headquarters": branch_obj.branch_type == BranchType.HQ,
        } if branch_obj else None,
    }

@router.post("/context/switch")
async def switch_context(
    request: Request,
    response: Response,
    branch_id: Optional[int] = None, # None means HQ
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Enables context switching (Impersonation).
    Only Admins or Superadmins can switch.
    """
    from app.models.users import Role, PlatformRole, UserOrganization

    # 1. Permission Check
    if current_user.role != Role.ADMINISTRADOR and current_user.platform_role != PlatformRole.SUPERADMIN:
        # Check if user has explicit Admin role in an org
        is_org_admin = db.query(UserOrganization).filter(
            UserOrganization.user_id == current_user.id,
            UserOrganization.org_role == "ADMIN",
            UserOrganization.is_active == True,  # noqa: E712
        ).first()
        if not is_org_admin:
            raise HTTPException(status_code=403, detail="No tienes permisos para cambiar de contexto")

    # 2. Verify Branch exists and belongs to organization (if branch_id provided)
    ctx_type = "HQ"
    ctx_id = None

    if branch_id:
        branch = db.query(Branch).filter(Branch.id == branch_id).first()
        if not branch:
            raise HTTPException(status_code=404, detail="Sucursal no encontrada")
        # La sucursal debe ser de una organización donde el usuario tiene
        # membresía activa (el SUPERADMIN entra a cualquiera). Se responde 404,
        # igual que si no existiera, para no confirmar ids de otras empresas.
        if current_user.platform_role != PlatformRole.SUPERADMIN:
            tiene_acceso = db.query(UserOrganization).filter(
                UserOrganization.user_id == current_user.id,
                UserOrganization.organization_id == branch.organization_id,
                UserOrganization.is_active == True,  # noqa: E712
            ).first()
            if not tiene_acceso:
                raise HTTPException(status_code=404, detail="Sucursal no encontrada")
        ctx_id = branch.id
        ctx_type = branch.branch_type.value if hasattr(branch.branch_type, 'value') else str(branch.branch_type)

    # 3. Issue New Token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    token_data = {
        "sub": current_user.username,
        "role": current_user.role.value,
        "ctx_id": ctx_id,
        "ctx_type": ctx_type
    }

    access_token = create_access_token(data=token_data, expires_delta=access_token_expires)

    # 4. Update Cookie
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=cookie_segura(request),
    )

    return {"message": "Context switched successfully", "ctx_id": ctx_id, "ctx_type": ctx_type, "access_token": access_token}

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    response.delete_cookie("support_org_id")
    return {"message": "Logged out successfully"}
