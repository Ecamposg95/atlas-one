"""Contrato público del canal «Tienda en línea» (`/api/channel/v1`).

Lista de campos cerrada: ningún schema hereda de los internos y todos
rechazan claves extra. Nunca precios, costos, existencias ni proveedores.
"""
from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class _Canal(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CanalMarca(_Canal):
    id: str
    name: Optional[str] = None
    logo_url: Optional[str] = None
    is_premium: bool = False
    updated_at: datetime
    deleted: bool = False


class CanalDepartamento(_Canal):
    id: str
    name: Optional[str] = None
    parent_id: Optional[str] = None
    updated_at: datetime
    deleted: bool = False


class CanalImagen(_Canal):
    url: str
    alt: Optional[str] = None
    position: int = 0
    is_primary: bool = False


class CanalVariante(_Canal):
    id: str
    sku: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    available: bool


class CanalProducto(_Canal):
    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    brand_id: Optional[str] = None
    department_id: Optional[str] = None
    gender: Optional[str] = None
    model: Optional[str] = None
    material: Optional[str] = None
    available: bool
    images: List[CanalImagen]
    variants: List[CanalVariante]
    updated_at: datetime
    web_published_at: Optional[datetime] = None
    deleted: bool = False


class CanalBaja(_Canal):
    id: str
    updated_at: datetime
    deleted: bool = True


class CanalDisponibilidad(_Canal):
    product_id: str
    variant_id: str
    available: bool
    changed_at: datetime


class Pagina(_Canal, Generic[T]):
    items: List[T]
    next_cursor: Optional[str] = None
    server_time: datetime
