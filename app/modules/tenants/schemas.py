# app/schemas/organization.py
from datetime import date
from decimal import Decimal

from pydantic import BaseModel
from typing import Optional
from app.models.organization import IndustryType


class OrganizationBase(BaseModel):
    name: str = "Mi Empresa"
    legal_name: Optional[str] = None
    tax_id: Optional[str] = None
    tax_regime: Optional[str] = None

    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None

    logo_url: Optional[str] = None
    ticket_header: Optional[str] = "ATLAS POS - Nota de Venta"
    ticket_footer: Optional[str] = "Gracias por su compra!"
    printer_name: Optional[str] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    maps_url: Optional[str] = None
    timezone: Optional[str] = "America/Mexico_City"

    # SaaS Fields
    status: Optional[str] = "ACTIVE"
    plan: Optional[str] = "FREE"
    branding_config: Optional[str] = None


class OrganizationCreate(OrganizationBase):
    # Default ATLAS_POS — preset se aplica automáticamente al crear (ver router).
    industry_type: Optional[IndustryType] = IndustryType.ATLAS_POS

    model_config = {"extra": "ignore"}


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    legal_name: Optional[str] = None
    tax_id: Optional[str] = None
    tax_regime: Optional[str] = None

    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None

    logo_url: Optional[str] = None
    ticket_header: Optional[str] = None
    ticket_footer: Optional[str] = None
    printer_name: Optional[str] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    maps_url: Optional[str] = None
    timezone: Optional[str] = None

    # SaaS Fields
    status: Optional[str] = None
    plan: Optional[str] = None
    branding_config: Optional[str] = None
    industry_type: Optional[IndustryType] = None
    is_active: Optional[bool] = None

    # Equivalente en dolares (2026-09-17). Los tres caen FUERA de la whitelist
    # de no-admins del router (linea 67 de router.py), asi que solo
    # ADMINISTRADOR/DUEÑO pueden cambiarlos: no hace falta guardia nueva.
    usd_rate_mode: Optional[str] = None
    usd_rate_manual: Optional[Decimal] = None
    usd_rate_margin: Optional[Decimal] = None

    model_config = {"extra": "ignore"}


class OrganizationRead(OrganizationBase):
    id: int
    is_active: Optional[bool] = True
    industry_type: Optional[str] = None

    # Equivalente en dolares. Se exponen en la lectura para que el panel de
    # Empresa arme el formulario sin un GET extra.
    usd_rate_mode: str = "off"
    usd_rate_manual: Optional[Decimal] = None
    usd_rate_margin: Decimal = Decimal("0")

    class Config:
        from_attributes = True


class ExchangeRateRead(BaseModel):
    """Lo que el POS necesita para pintar el equivalente en dolares.

    `rate is None` significa "no mostrar nada": pasa en modo 'off' y tambien en
    modo 'auto' cuando todavia no hay FIX descargado. El POS NO debe distinguir
    esos dos casos.
    """
    mode: str
    rate: Optional[Decimal] = None        # tipo efectivo, ya con el margen
    source: Optional[str] = None          # 'banxico' | 'manual'
    fix_rate: Optional[Decimal] = None    # FIX crudo del dia (informativo)
    fix_date: Optional[date] = None
    margin: Decimal = Decimal("0")
    manual_rate: Optional[Decimal] = None
