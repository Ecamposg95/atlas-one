"""Esquemas de `POST /api/channel/v1/leads` y utilidades de teléfono."""
import re
from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


def normalizar_telefono(s: Optional[str]) -> Optional[str]:
    """Quita lo que no sea dígito y toma los últimos 10; con menos de 10 → None."""
    digitos = re.sub(r"\D", "", s or "")
    return digitos[-10:] if len(digitos) >= 10 else None


class LeadIn(BaseModel):
    source: Literal["web_whatsapp_click", "web_selection", "web_form"]
    product_ids: List[str] = Field(default_factory=list, max_length=50)
    line: Optional[Literal["general", "boutique"]] = None
    name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=40)
    email: Optional[str] = Field(None, max_length=200)
    utm: Optional[Dict[str, Optional[str]]] = None
    occurred_at: Optional[datetime] = None
