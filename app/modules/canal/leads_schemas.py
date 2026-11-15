"""Esquemas de `POST /api/channel/v1/leads` y utilidades de teléfono."""
import re
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Ventana aceptada para `occurred_at`: la web puede reintentar con retraso,
# pero no fechar eventos semanas atrás ni en el futuro (inflaría métricas).
MAX_ATRASO = timedelta(days=7)
MAX_ADELANTO = timedelta(days=1)


def normalizar_telefono(s: Optional[str]) -> Optional[str]:
    """Quita lo que no sea dígito y toma los últimos 10; con menos de 10 → None."""
    digitos = re.sub(r"\D", "", s or "")
    return digitos[-10:] if len(digitos) >= 10 else None


class Utm(BaseModel):
    """Solo source/medium/campaign, 100 caracteres cada una; otra clave → 422."""
    model_config = ConfigDict(extra="forbid")

    source: Optional[str] = Field(None, max_length=100)
    medium: Optional[str] = Field(None, max_length=100)
    campaign: Optional[str] = Field(None, max_length=100)


class LeadIn(BaseModel):
    source: Literal["web_whatsapp_click", "web_selection", "web_form"]
    product_ids: List[str] = Field(default_factory=list, max_length=50)
    line: Optional[Literal["general", "boutique"]] = None
    name: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=30)
    email: Optional[str] = Field(None, max_length=200)
    utm: Optional[Utm] = None
    occurred_at: Optional[datetime] = None

    @field_validator("occurred_at")
    @classmethod
    def _ventana(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return v
        u = v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)
        ahora = datetime.now(timezone.utc)
        if u < ahora - MAX_ATRASO:
            raise ValueError("occurred_at no puede ser de hace más de 7 días")
        if u > ahora + MAX_ADELANTO:
            raise ValueError("occurred_at no puede ser más de 1 día en el futuro")
        return v
