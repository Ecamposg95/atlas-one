# app/schemas/organization.py
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from app.models.organization import IndustryType

# Tope de los terminos de compra. El mismo numero vive en el `maxLength` del
# panel de Empresa: API y pantalla tienen que coincidir o el dueño escribe un
# texto que el PUT rechaza.
TERMS_MAX_LEN = 2000

# Estilo del renglon de producto del ticket. 'compact' es el de siempre (una
# linea); 'detailed' imprime marca / nombre completo / talla (boutique).
TICKET_LINE_STYLES = ("compact", "detailed")


def _valida_estilo_de_linea(v):
    """None pasa (el PUT no lo manda); cualquier otro valor tiene que ser uno
    de los dos estilos, o el ticket quedaria con una configuracion muerta."""
    if v is None:
        return v
    limpio = str(v).strip().lower()
    if limpio not in TICKET_LINE_STYLES:
        raise ValueError(f"debe ser uno de: {', '.join(TICKET_LINE_STYLES)}")
    return limpio


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

    # Secciones boutique del ticket (2026-09-19). None = la seccion no se
    # imprime; la linea del proveedor viene apagada, como en la base.
    ticket_terms: Optional[str] = Field(default=None, max_length=TERMS_MAX_LEN)
    ticket_terms_url: Optional[str] = Field(default=None, max_length=255)
    ticket_instagram: Optional[str] = None
    ticket_facebook: Optional[str] = None
    ticket_tiktok: Optional[str] = None
    ticket_whatsapp: Optional[str] = None
    ticket_show_vendor: bool = False
    # Renglon del producto: 'compact' (el de siempre) o 'detailed'.
    ticket_line_style: str = "compact"

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    maps_url: Optional[str] = None
    timezone: Optional[str] = "America/Mexico_City"

    # SaaS Fields
    status: Optional[str] = "ACTIVE"
    plan: Optional[str] = "FREE"
    branding_config: Optional[str] = None


    _estilo_valido = field_validator("ticket_line_style")(_valida_estilo_de_linea)


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

    # Secciones boutique del ticket (2026-09-19). Caen FUERA de la whitelist de
    # no-admins del router, asi que solo ADMINISTRADOR/DUEÑO las cambia.
    ticket_terms: Optional[str] = Field(default=None, max_length=TERMS_MAX_LEN)
    ticket_terms_url: Optional[str] = Field(default=None, max_length=255)
    ticket_instagram: Optional[str] = None
    ticket_facebook: Optional[str] = None
    ticket_tiktok: Optional[str] = None
    ticket_whatsapp: Optional[str] = None
    ticket_show_vendor: Optional[bool] = None
    # Cae FUERA de la whitelist de no-admins del router: solo
    # ADMINISTRADOR/DUEÑO cambia el estilo del ticket.
    ticket_line_style: Optional[str] = None

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

    # Comision por pago con tarjeta (2026-09-17). Cae FUERA de la whitelist de
    # no-admins del router (linea 76 de router.py), asi que solo
    # ADMINISTRADOR/DUEÑO puede cambiarla: no hace falta guardia nueva.
    card_surcharge_pct: Optional[Decimal] = None

    _estilo_valido = field_validator("ticket_line_style")(_valida_estilo_de_linea)

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

    # Comision por pago con tarjeta. Se expone en la lectura para que el panel
    # de Empresa arme el formulario sin un GET extra.
    card_surcharge_pct: Decimal = Decimal("0")

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


class CardSurchargeRead(BaseModel):
    """Lo unico que el POS necesita para cobrar la comision de tarjeta.

    `pct = 0` significa "no mostrar ni cobrar nada", que es el estado de toda
    organizacion que no la configuro.
    """
    pct: Decimal = Decimal("0")
