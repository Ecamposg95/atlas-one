import re
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

# --- DEFINICIÓN DE CLASES (Sin self-imports) ---

# PIN de reimpresión: 4-8 dígitos numéricos. La cadena vacía también es válida
# a nivel de schema — es la señal de "borrar el PIN" que usan UserCreate/
# UserUpdate. El campo ausente (None) significa "no tocar".
REPRINT_PIN_PATTERN = re.compile(r"^\d{4,8}$")


def _validar_reprint_pin(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return value
    if not REPRINT_PIN_PATTERN.match(value):
        raise ValueError('reprint_pin debe ser de 4 a 8 dígitos numéricos (o "" para borrarlo)')
    return value


class UserBase(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: str = "CAJERO"
    platform_role: Optional[str] = "NONE"
    branch_id: Optional[int] = None
    is_active: bool = True

class UserCreate(UserBase):
    password: str
    organization_id: Optional[int] = None
    # Solo-escritura: se hashea en el router y nunca se devuelve.
    # None = alta sin PIN. "" = sin efecto (no hay PIN que borrar en un alta).
    reprint_pin: Optional[str] = None

    _validar_reprint_pin = field_validator("reprint_pin")(_validar_reprint_pin)

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    platform_role: Optional[str] = None
    branch_id: Optional[int] = None
    organization_id: Optional[int] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    # Solo-escritura, nunca se devuelve (ver UserRead.has_reprint_pin).
    # Campo ausente = no tocar. "" explícito = borrar el PIN.
    reprint_pin: Optional[str] = None

    _validar_reprint_pin = field_validator("reprint_pin")(_validar_reprint_pin)

class UserRead(UserBase):
    id: int
    created_at: Optional[datetime] = None
    organization_id: Optional[int] = None
    branch_name: Optional[str] = None
    # Derivado de User.reprint_pin_hash: nunca se expone el hash ni el PIN.
    has_reprint_pin: bool = False

    class Config:
        from_attributes = True
