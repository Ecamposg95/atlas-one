# app/routers/organization.py
"""
MOONSHOT_ENGINE: Nucleus
DOMAIN: Organizational / Tenancy
STATUS: Stable
"""
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Body
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pathlib import Path
import shutil
import time

from app.core.database import get_db
from app.models.organization import Organization
from app.schemas.organization import (
    CardSurchargeRead,
    ExchangeRateRead,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
)
from app.core.security import get_current_user
from app.models.users import Role

from app.core.tenant_context import get_current_active_organization

router = APIRouter()

# Domain-owned sub-router: capabilities son info de contexto por usuario
# para su organización activa. `main.py` lo monta en /api/org/capabilities
# para preservar la URL histórica.
capabilities_router = APIRouter()

ADMIN_ROLES = {Role.ADMINISTRADOR, Role.DUEÑO}


def require_admin(current_user):
    from app.models.users import PlatformRole
    if current_user.platform_role == PlatformRole.SUPERADMIN:
        return current_user
    if current_user.role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Requiere permisos de administrador")
    return current_user


@router.get("/", response_model=OrganizationRead)
def get_organization(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization) # [HARDENING]
):
    # [HARDENING] Fetch specific to context
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
         raise HTTPException(status_code=404, detail="Organization context not found")
    return org


@router.put("/", response_model=OrganizationRead)
def update_organization(
    org_in: OrganizationUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization) # [HARDENING]
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # `exclude_unset` una sola vez: el bloque de permisos y el de escritura
    # tienen que mirar exactamente el mismo diccionario.
    data_to_update = org_in.dict(exclude_unset=True)

    # [HARDENING] Refined Logic: Check what is ACTUALLY changing
    if current_user.role not in ADMIN_ROLES:
        allowed_subset = {"printer_name", "ticket_header", "ticket_footer", "paper_width_mm"}

        for key, new_val in data_to_update.items():
            current_val = getattr(org, key)
            # If value is changing...
            if new_val != current_val:
                # ...and it's not in the whitelist, BLOCK IT.
                if key not in allowed_subset:
                     print(f"[AUTH BLOCK] User {current_user.username} tried to change restricted field '{key}' from '{current_val}' to '{new_val}'")
                     require_admin(current_user)

    # Equivalente en dolares: se valida la configuracion RESULTANTE (la que
    # quedaria guardada), no el payload parcial. Asi un PUT que solo cambia el
    # margen no puede dejar la organizacion en modo manual sin tipo capturado,
    # y un PUT que no toca nada de USD ni siquiera entra aqui.
    if any(k.startswith("usd_rate_") for k in data_to_update):
        from app.services.exchange_rate import MODO_OFF, validar_config_usd

        modo = (data_to_update.get("usd_rate_mode", org.usd_rate_mode) or MODO_OFF).strip().lower()
        manual = data_to_update.get("usd_rate_manual", org.usd_rate_manual)
        margen = data_to_update.get("usd_rate_margin", org.usd_rate_margin)
        try:
            validar_config_usd(modo, manual, margen)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        if "usd_rate_mode" in data_to_update:
            data_to_update["usd_rate_mode"] = modo  # normalizado a minusculas

    # Comision por pago con tarjeta: se valida ANTES del setattr, para no dejar
    # la organizacion a medio escribir y tener que hacer rollback a media
    # peticion. `None` = "no tocar": la columna es NOT NULL y el panel manda el
    # objeto completo, asi que escribir None seria un 500 al commitear.
    if "card_surcharge_pct" in data_to_update:
        if data_to_update["card_surcharge_pct"] is None:
            data_to_update.pop("card_surcharge_pct")
        else:
            from app.services.card_surcharge import validar_pct

            try:
                validar_pct(data_to_update["card_surcharge_pct"])
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))

    # Linea del proveedor y estilo del renglon: las dos columnas son NOT NULL,
    # asi que un `null` en el payload es "no tocar" y no un 500 al commitear.
    for _campo_no_nulo in ("ticket_show_vendor", "ticket_line_style"):
        if _campo_no_nulo in data_to_update and data_to_update[_campo_no_nulo] is None:
            data_to_update.pop(_campo_no_nulo)

    for key, value in data_to_update.items():
        setattr(org, key, value)

    db.commit()
    db.refresh(org)
    return org

# [DEPRECATED] Creation handled via Platform Router
# @router.post("/", ... )


# ═════════════════════════════════════════════════════════════════════════════
# TIPO DE CAMBIO USD (2026-09-17)
# Endpoint propio y barato para el POS: lo consume la cajera, que NO es admin y
# no tiene por que leer RFC ni configuracion fiscal solo para pintar un numero.
# Dos SELECT y cero llamadas de red.
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/exchange-rate", response_model=ExchangeRateRead)
def get_exchange_rate(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Tipo de cambio vigente de la organización. `rate = null` = no mostrar nada."""
    from app.services.exchange_rate import MODO_OFF, resolve_usd_rate, ultimo_fix

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization context not found")

    modo = (org.usd_rate_mode or MODO_OFF).strip().lower()
    fix = ultimo_fix(db) if modo != MODO_OFF else None
    resuelto = resolve_usd_rate(org, fix)

    # El FIX se expone aunque no haya tipo efectivo: el panel de Empresa lo
    # muestra para que el dueño vea que el job SI esta bajando datos. `is None`
    # explicito (no `or`): un FIX de $0 seria falsy y tapado por el fallback.
    fix_rate = resuelto.fix_rate if resuelto is not None and resuelto.fix_rate is not None else (
        fix.rate if fix is not None else None
    )
    fix_date = resuelto.fix_date if resuelto is not None and resuelto.fix_date is not None else (
        fix.rate_date if fix is not None else None
    )

    return ExchangeRateRead(
        mode=modo,
        rate=resuelto.rate if resuelto else None,
        source=resuelto.source if resuelto else None,
        fix_rate=fix_rate,
        fix_date=fix_date,
        margin=org.usd_rate_margin or 0,
        manual_rate=org.usd_rate_manual,
    )


# ═════════════════════════════════════════════════════════════════════════════
# COMISION POR PAGO CON TARJETA (2026-09-17)
# Endpoint propio y barato para el POS, por el mismo motivo que el del tipo de
# cambio: lo consume la cajera, que NO es admin y no tiene por que leer RFC ni
# configuracion fiscal solo para cobrar. Un SELECT y cero llamadas de red.
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/card-surcharge", response_model=CardSurchargeRead)
def get_card_surcharge(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Porcentaje de comisión por pago con tarjeta. `pct = 0` = apagado."""
    from app.services.card_surcharge import pct_de_organizacion

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization context not found")

    return CardSurchargeRead(pct=pct_de_organizacion(org))


@router.post("/exchange-rate/refresh")
def refresh_exchange_rate(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    """Baja el FIX de Banxico a demanda, para no esperar al job de mañana."""
    require_admin(current_user)

    from app.core.exchange_rate_job import actualizar_fix_ahora
    from app.services.banxico import token_configurado
    from app.services.exchange_rate import ultimo_fix

    token = token_configurado()
    if not token:
        raise HTTPException(
            status_code=503,
            detail="El servidor no tiene BANXICO_TOKEN configurado. Usa el modo manual.",
        )

    ok, mensaje = actualizar_fix_ahora(db, token)
    if not ok:
        raise HTTPException(status_code=503, detail=f"Banxico no respondió: {mensaje}")

    fila = ultimo_fix(db)
    return {
        "ok": True,
        "rate_date": fila.rate_date.isoformat() if fila else None,
        "rate": float(fila.rate) if fila else None,
        "source": fila.source if fila else None,
    }


@router.post("/logo")
async def upload_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization) # [HARDENING]
):
    require_admin(current_user)

    # Validar tipo
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Solo se permiten imágenes")

    # SVG removed: ESC/POS pipeline rasterizes via Pillow (Image.open),
    # which does not read SVG. Accepting SVG made the upload appear to work
    # but the logo silently disappeared from printed tickets. Use a raster
    # format so the print path matches the upload path.
    allowed_types = {"image/png", "image/jpeg", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Formato no permitido (PNG/JPEG/WEBP)")

    content = await file.read()
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    from app.utils import image_storage
    org.logo_url = image_storage.upload_image(
        content,
        public_id=f"org_{org_id}",
        folder=image_storage.ORG_LOGOS_FOLDER,
        content_type=file.content_type,
    )
    db.commit()
    db.refresh(org)

    return {"status": "success", "logo_url": org.logo_url}


@router.delete("/logo")
def delete_org_logo(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    require_admin(current_user)
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    from app.utils import image_storage
    image_storage.delete_image(f"org_{org_id}", folder=image_storage.ORG_LOGOS_FOLDER)
    org.logo_url = None
    db.commit()
    return {"status": "success", "logo_url": None}


# ═════════════════════════════════════════════════════════════════════════════
# CAPABILITIES — consolidado desde app/routers/org_capabilities.py (Fase A).
# El handler devuelve módulos habilitados + nav contextual para el usuario
# actual. main.py lo monta en /api/org/capabilities (URL histórica).
# ═════════════════════════════════════════════════════════════════════════════
from fastapi import Request as _CapabilitiesRequest
from app.services.capabilities_service import get_organization_capabilities as _get_org_caps
from app.ui.nav_registry import get_nav_for_context as _get_nav
from app.schemas.capabilities import OrgCapabilities as _OrgCapabilities
from app.models.organization import IndustryType as _IndustryType


@capabilities_router.get("/", response_model=_OrgCapabilities)
async def get_org_caps(
    request: _CapabilitiesRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),  # [HARDENING] User no tiene .organization_id
):
    """Returns the capabilities (enabled modules + nav) for the current user's organization."""
    org = db.get(Organization, org_id)
    enabled_mods = _get_org_caps(db, org.id)

    ctx_type = getattr(request.state, "ctx_type", "HQ")
    nav = _get_nav(ctx_type, enabled_mods, current_user.role.value)

    branch_default = "/pos"
    if org.industry_type in [
        _IndustryType.RESTAURANT_QSR,
        _IndustryType.RESTAURANT_FULL,
        _IndustryType.CAFE_BAKERY,
    ]:
        branch_default = "/pos"
    elif org.industry_type == _IndustryType.AUTO_REPAIR_SHOP:
        branch_default = "/service/orders"
    elif org.industry_type == _IndustryType.WAREHOUSE_LOGISTICS:
        branch_default = "/warehouse/dashboard"

    return {
        "organization_id": org.id,
        "industry_type": org.industry_type.value,
        "enabled_modules": enabled_mods,
        "ui_profile": current_user.role.value.lower(),
        "default_routes": {
            "hq": "/command-center",
            "branch": branch_default,
            "warehouse": "/warehouse/dashboard",
        },
        "nav_items": nav,
    }
