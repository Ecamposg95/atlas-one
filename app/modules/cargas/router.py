"""`/api/cargas` — Cargar mercancía con IA (PDF o planilla → plan → catálogo).

Handlers delgados: la lectura vive en `proceso`, las operaciones sobre el plan
en `operaciones`/`respuestas`, la aplicación en `aplicar` y las respuestas en
`vista`. Toda carga se busca filtrada por la organización autenticada (la de
otra organización es 404): es la única barrera de tenant, porque `aplicar_carga`
toma la org de la carga.

Roles: ADMINISTRADOR, DUEÑO y GERENTE; autorizar solo ADMINISTRADOR/DUEÑO.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.crud.products import _is_admin
from app.models import User
from app.modules.ai.cliente_anthropic import (
    ClienteEstructurado, ProveedorNoDisponible, cliente_estructurado_por_defecto,
)
from app.modules.ai.gating import exigir_modulo_ai
from app.modules.cargas import proceso, vista
from app.modules.cargas.aplicar import aplicar_carga
from app.modules.cargas.models import CargaMercancia
from app.modules.cargas.operaciones import aplicar_operaciones, deshacer_cambio
from app.modules.cargas.respuestas import interpretar_respuesta
from app.modules.cargas.schemas import (
    CargaAlta, CargaDetalle, CargaResumen, DudaRespuesta, Etiqueta, RespuestaCambio,
    RespuestaTexto, ResumenAplicacionVista,
)
from app.modules.tenants.models import Organization
from app.services.reprint_auth import ROLES_GERENCIALES

router = APIRouter()

_TROZO = 1024 * 1024


def obtener_cliente_estructurado() -> ClienteEstructurado:
    """Cliente del modelo; las pruebas lo cambian por `ClienteEstructuradoFalso`."""
    return cliente_estructurado_por_defecto()


def _oficina(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ROLES_GERENCIALES:
        raise HTTPException(status_code=403,
                            detail="Solo administración, dueño o gerencia pueden cargar mercancía.")
    return current_user


def _carga_o_404(db: Session, org_id: int, carga_id: str) -> CargaMercancia:
    carga = (db.query(CargaMercancia)
             .filter(CargaMercancia.id == carga_id, CargaMercancia.organization_id == org_id)
             .first())
    if carga is None:
        raise HTTPException(status_code=404, detail="Carga no encontrada.")
    return carga


def _instrucciones(db: Session, org_id: int) -> str:
    org = db.get(Organization, org_id)
    return (getattr(org, "ai_instrucciones", None) or "").strip()


async def _leer_archivo(archivo: UploadFile) -> bytes:
    """Lee a lo más 20 MB sin fiarse del Content-Length."""
    partes, total = [], 0
    while True:
        trozo = await archivo.read(_TROZO)
        if not trozo:
            break
        total += len(trozo)
        if total > proceso.MAX_BYTES:
            raise HTTPException(status_code=413, detail=proceso.ARCHIVO_GRANDE)
        partes.append(trozo)
    return b"".join(partes)


@router.post("", response_model=CargaAlta, status_code=202)
async def subir(
    archivo: UploadFile = File(...),
    proposito: str = Form("entrada"),
    sucursal_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(_oficina),
    org_id: int = Depends(exigir_modulo_ai),
    cliente: ClienteEstructurado = Depends(obtener_cliente_estructurado),
):
    contenido = await _leer_archivo(archivo)
    tipo = proceso.detectar_tipo(archivo.filename, contenido)
    if tipo is None:
        raise HTTPException(status_code=415, detail=proceso.TIPO_NO_SOPORTADO)
    carga = proceso.crear_carga(db, org_id, user, archivo.filename or f"archivo.{tipo}",
                                contenido, tipo, proposito, sucursal_id)
    db.commit()
    proceso.lanzar_proceso(carga.id, cliente, db=db)
    db.refresh(carga)
    return vista.alta(carga)


@router.get("", response_model=list[CargaResumen])
def listar(
    db: Session = Depends(get_db),
    user: User = Depends(_oficina),
    org_id: int = Depends(exigir_modulo_ai),
):
    proceso.recuperar_cargas_colgadas(db, org_id=org_id)
    cargas = (db.query(CargaMercancia)
              .filter(CargaMercancia.organization_id == org_id)
              .order_by(CargaMercancia.created_at.desc(), CargaMercancia.folio.desc())
              .all())
    return vista.lista(db, org_id, cargas)


@router.get("/{carga_id}", response_model=CargaDetalle)
def obtener(
    carga_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_oficina),
    org_id: int = Depends(exigir_modulo_ai),
):
    carga = _carga_o_404(db, org_id, carga_id)
    # Un hilo que murió (despliegue, falla al guardar) no deja la carga atorada.
    proceso.recuperar_cargas_colgadas(db, org_id=org_id)
    return vista.detalle(db, carga, user)


@router.post("/{carga_id}/respuestas", response_model=RespuestaCambio)
def responder(
    carga_id: str,
    body: RespuestaTexto,
    db: Session = Depends(get_db),
    user: User = Depends(_oficina),
    org_id: int = Depends(exigir_modulo_ai),
    cliente: ClienteEstructurado = Depends(obtener_cliente_estructurado),
):
    carga = _carga_o_404(db, org_id, carga_id)
    try:
        operaciones, rechazos, entrada, salida = interpretar_respuesta(
            db, carga, body.texto, cliente, _instrucciones(db, org_id))
    except ProveedorNoDisponible as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    carga.tokens_entrada = (carga.tokens_entrada or 0) + entrada
    carga.tokens_salida = (carga.tokens_salida or 0) + salida
    # El uso del modelo queda guardado aunque aplicar falle después (409, etc.).
    db.commit()
    cambio, rechazos_aplicar = (aplicar_operaciones(db, carga, user, operaciones, body.texto)
                                if operaciones else (None, []))
    db.commit()
    return vista.respuesta_cambio(db, carga, cambio, rechazos_aplicar + rechazos)


@router.post("/{carga_id}/dudas/{numero}", response_model=RespuestaCambio)
def resolver_duda(
    carga_id: str,
    numero: int,
    body: DudaRespuesta,
    db: Session = Depends(get_db),
    user: User = Depends(_oficina),
    org_id: int = Depends(exigir_modulo_ai),
):
    carga = _carga_o_404(db, org_id, carga_id)
    op = {"op": "resolver_duda", "numero": numero, "opcion": body.opcion}
    if body.valor is not None:
        op["valor"] = body.valor
    cambio, rechazos = aplicar_operaciones(db, carga, user, [op], None)
    db.commit()
    # Una sola operación: el "Operación 1: " no le dice nada al usuario.
    rechazos = [r.removeprefix("Operación 1: ") for r in rechazos]
    rechazos = [r[:1].upper() + r[1:] for r in rechazos]
    return vista.respuesta_cambio(db, carga, cambio, rechazos)


@router.post("/{carga_id}/cambios/{cambio_id}/deshacer", response_model=CargaDetalle)
def deshacer(
    carga_id: str,
    cambio_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_oficina),
    org_id: int = Depends(exigir_modulo_ai),
):
    carga = _carga_o_404(db, org_id, carga_id)
    deshacer_cambio(db, carga, cambio_id)
    db.commit()
    return vista.detalle(db, carga, user)


@router.post("/{carga_id}/reintentar", response_model=CargaAlta)
def reintentar(
    carga_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_oficina),
    org_id: int = Depends(exigir_modulo_ai),
    cliente: ClienteEstructurado = Depends(obtener_cliente_estructurado),
):
    carga = _carga_o_404(db, org_id, carga_id)
    leer = proceso.reintentar(db, carga)
    db.commit()
    if leer:
        proceso.lanzar_proceso(carga.id, cliente, db=db)
        db.refresh(carga)
    return vista.alta(carga)


@router.post("/{carga_id}/autorizar", response_model=ResumenAplicacionVista)
def autorizar(
    carga_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_oficina),
    org_id: int = Depends(exigir_modulo_ai),
):
    if not _is_admin(user):
        raise HTTPException(status_code=403,
                            detail="Solo un administrador o el dueño puede autorizar una carga.")
    carga = _carga_o_404(db, org_id, carga_id)
    resumen = aplicar_carga(db, carga, user)
    return vista.resumen_aplicacion(db, _carga_o_404(db, org_id, carga_id), resumen)


@router.post("/{carga_id}/descartar", response_model=CargaAlta)
def descartar(
    carga_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_oficina),
    org_id: int = Depends(exigir_modulo_ai),
):
    carga = _carga_o_404(db, org_id, carga_id)
    proceso.descartar(db, carga)
    db.commit()
    return vista.alta(carga)


@router.get("/{carga_id}/etiquetas", response_model=list[Etiqueta])
def etiquetas(
    carga_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(_oficina),
    org_id: int = Depends(exigir_modulo_ai),
):
    carga = _carga_o_404(db, org_id, carga_id)
    if carga.estado != "aplicada":
        raise HTTPException(status_code=409,
                            detail=f"La carga #{carga.folio} todavía no se aplica: no tiene etiquetas.")
    return vista.etiquetas(db, carga)
