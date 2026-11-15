"""Esquemas de petición/respuesta de "Cargar mercancía con IA"."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, constr

LIMITE_RESPUESTA = 4000


class RespuestaTexto(BaseModel):
    """Respuesta escrita del dueño a las dudas del plan (tope: 4,000 caracteres)."""

    texto: constr(min_length=1, max_length=LIMITE_RESPUESTA)  # type: ignore[valid-type]


# ── HTTP de /api/cargas (contrato: los decimales viajan como texto) ────────

class DudaRespuesta(BaseModel):
    """Botón: `{opcion: "<clave>"}`; respuesta escrita: `{opcion: "", valor: "..."}`."""

    opcion: str = ""
    valor: Optional[constr(max_length=LIMITE_RESPUESTA)] = None  # type: ignore[valid-type]


class CargaAlta(BaseModel):
    id: str
    folio: int
    estado: str


class CargaResumen(BaseModel):
    id: str
    folio: int
    estado: str
    proposito: str
    archivo_nombre: str
    archivo_tipo: str
    sucursal_destino_id: Optional[int] = None
    sucursal_nombre: Optional[str] = None
    piezas: str
    usuario: str
    created_at: str
    aplicada_at: Optional[str] = None
    error: Optional[str] = None


class CargaConDetalle(CargaResumen):
    monedas: dict[str, Optional[str]] = Field(default_factory=dict)
    totales: Optional[dict[str, Any]] = None


class OpcionDuda(BaseModel):
    clave: str
    etiqueta: str


class DudaVista(BaseModel):
    numero: int
    tipo: str
    texto: str
    opciones: list[OpcionDuda]
    recomendada: Optional[str] = None
    acepta_texto: bool
    estado: str
    respuesta: Optional[str] = None


class RenglonPlan(BaseModel):
    orden: int
    talla: Optional[str] = None
    color: Optional[str] = None
    cantidad: str
    precio: Optional[str] = None
    costo: Optional[str] = None
    clase: str
    sku: Optional[str] = None
    origen: str
    descripcion: str = ""


class GrupoPlan(BaseModel):
    grupo: str
    titulo: str
    marca: Optional[str] = None
    tipo: Optional[str] = None
    departamento: Optional[str] = None
    genero: Optional[str] = None
    product_id: Optional[str] = None
    renglones: list[RenglonPlan]


class CambioGrupo(BaseModel):
    grupo: str
    titulo: str
    renglones: list[int]
    cambios: dict[str, dict[str, Any]]


class CambioResumen(BaseModel):
    grupos: list[CambioGrupo] = Field(default_factory=list)
    dudas_resueltas: list[int] = Field(default_factory=list)
    dudas_nuevas: list[int] = Field(default_factory=list)


class CambioVista(BaseModel):
    id: str
    secuencia: int
    texto: Optional[str] = None
    resumen: CambioResumen
    deshecho: bool
    puede_deshacer: bool
    usuario: str
    created_at: str


class Contadores(BaseModel):
    EXISTE: int = 0
    SUMA: int = 0
    NUEVO: int = 0
    YA_CARGADO: int = 0
    IGNORADO: int = 0
    piezas: str = "0"


class ConteoVista(BaseModel):
    departamento: str
    numero: int
    cerrado_at: str


class CargaDetalle(BaseModel):
    carga: CargaConDetalle
    contadores: Contadores
    dudas: list[DudaVista]
    grupos: list[GrupoPlan]
    cambios: list[CambioVista]
    ultimos_conteos: list[ConteoVista]
    puede_autorizar: bool


class RespuestaCambio(BaseModel):
    cambio: Optional[CambioVista] = None
    rechazos: list[str] = Field(default_factory=list)


class Etiqueta(BaseModel):
    marca: str
    producto: str
    sku: str
    talla: Optional[str] = None
    barcode: Optional[str] = None
    piezas: str
    precio: str


class ResumenAplicacionVista(BaseModel):
    productos_nuevos: int
    variantes_nuevas: int
    piezas: str
    valor_costo: str
    etiquetas: list[Etiqueta]
