"""Ciclo de vida de una carga: alta del archivo, lectura en segundo plano,
reintento, descarte y recuperación de lecturas que se quedaron a medias.

La lectura (`procesar_carga`) abre su propia sesión porque corre en un hilo
aparte de la petición que subió el archivo. Con `CARGAS_PROCESO_EN_LINEA=1`
(pruebas) corre en línea con la sesión y el cliente de la petición.
Cualquier falla deja la carga en `error` con un mensaje legible en español.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User
from app.models.organization import Branch
from app.modules.ai.cliente_anthropic import (
    ClienteEstructurado, ProveedorNoDisponible, cliente_estructurado_por_defecto,
)
from app.modules.ai.uso import registrar_uso, verificar_cupo
from app.modules.cargas.aplicar import YA_APLICADA, volver_a_plan
from app.modules.cargas.extraccion_pdf import extraer_pdf
from app.modules.cargas.lectura_excel import leer_tablas, mapear_columnas
from app.modules.cargas.models import (
    PROPOSITOS, CargaArchivo, CargaCambio, CargaDuda, CargaMercancia, CargaRenglon,
)
from app.modules.cargas.operaciones import rearmar_renglones_excel, recalcular_plan
from app.modules.tenants.models import Organization

logger = logging.getLogger(__name__)

MAX_BYTES = 20 * 1024 * 1024
MAX_RENGLONES = 2000
MINUTOS_COLGADA = 10
TIPOS = ("pdf", "xlsx", "csv")

ARCHIVO_GRANDE = "El archivo pesa más de 20 MB. Divídelo en partes y súbelas por separado."
TIPO_NO_SOPORTADO = "Solo se pueden subir archivos PDF, Excel (.xlsx) o CSV."
LECTURA_INTERRUMPIDA = "La lectura se interrumpió. Vuelve a intentar."
APLICACION_INTERRUMPIDA = "La aplicación se interrumpió y no se escribió nada. Vuelve a intentar."
_INTERRUMPIDA = {"leyendo": LECTURA_INTERRUMPIDA, "aplicando": APLICACION_INTERRUMPIDA}
_FALLA_GENERICA = "No se pudo leer el archivo. Revisa que no esté dañado y vuelve a intentar."


class LecturaFallida(Exception):
    """Falla de lectura con un mensaje que se le enseña al usuario tal cual."""


# ── alta ──────────────────────────────────────────────────────────────────

def detectar_tipo(nombre: Optional[str], contenido: bytes) -> Optional[str]:
    """Tipo por extensión Y por contenido; None si no coinciden o no es soportado."""
    ext = (nombre or "").rsplit(".", 1)[-1].lower() if "." in (nombre or "") else ""
    if ext == "pdf":
        return "pdf" if contenido.lstrip()[:4] == b"%PDF" else None
    if ext == "xlsx":
        return "xlsx" if contenido[:4] == b"PK\x03\x04" else None
    if ext == "csv":
        if not contenido or b"\x00" in contenido[:8192]:
            return None
        try:
            contenido[:8192].decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                contenido[:8192].decode("latin-1")
            except UnicodeDecodeError:  # pragma: no cover - latin-1 decodifica todo
                return None
        return "csv"
    return None


def siguiente_folio(db: Session, org_id: int) -> int:
    ultimo = (db.query(func.max(CargaMercancia.folio))
              .filter(CargaMercancia.organization_id == org_id).scalar())
    return (ultimo or 0) + 1


def crear_carga(db: Session, org_id: int, user: User, nombre: str, contenido: bytes,
                tipo: str, proposito: str, sucursal_id: Optional[int]) -> CargaMercancia:
    """Guarda la carga (estado `leyendo`) y su archivo original. Sin commit."""
    if proposito not in PROPOSITOS:
        raise HTTPException(status_code=422,
                            detail="El propósito debe ser «entrada» o «migracion».")
    if sucursal_id is not None:
        existe = db.query(Branch.id).filter(Branch.id == sucursal_id,
                                            Branch.organization_id == org_id).first()
        if existe is None:
            raise HTTPException(status_code=404, detail="Sucursal no encontrada.")
    sha = hashlib.sha256(contenido).hexdigest()
    # Dos subidas a la vez pueden tomar el mismo folio: la restricción única lo
    # detecta y se reintenta con el siguiente.
    for _ in range(5):
        try:
            with db.begin_nested():
                carga = CargaMercancia(
                    organization_id=org_id, folio=siguiente_folio(db, org_id),
                    user_id=user.id, proposito=proposito, estado="leyendo",
                    archivo_nombre=nombre, archivo_sha256=sha, archivo_tipo=tipo,
                    sucursal_destino_id=sucursal_id, intento=str(uuid.uuid4()),
                )
                db.add(carga)
                db.flush()
        except IntegrityError:
            continue
        db.add(CargaArchivo(organization_id=org_id, carga_id=carga.id, contenido=contenido))
        db.flush()
        return carga
    raise HTTPException(status_code=409, detail="No se pudo numerar la carga. Vuelve a intentar.")


# ── lectura ───────────────────────────────────────────────────────────────

@dataclass
class _Tokens:
    entrada: int = 0
    salida: int = 0

    def sumar(self, entrada: int, salida: int) -> None:
        self.entrada += int(entrada or 0)
        self.salida += int(salida or 0)


def _demasiados(n: int) -> LecturaFallida:
    return LecturaFallida(
        f"El archivo trae {n:,} renglones y el máximo por carga es {MAX_RENGLONES:,}. "
        "Divídelo en partes y súbelas por separado.")


def _extraer_pdf(contenido: bytes, cliente: ClienteEstructurado, instrucciones: str,
                 tokens: _Tokens, latido: Callable[[], None]):
    """Llama al modelo por bloques. No escribe nada en la base."""
    try:
        ext = extraer_pdf(contenido, cliente, instrucciones, al_terminar_bloque=latido)
    except ValueError as e:
        if type(e) is ValueError:  # los de extraccion_pdf ya vienen en español
            raise LecturaFallida(str(e)) from e
        raise
    tokens.sumar(ext.tokens_entrada, ext.tokens_salida)
    if not ext.renglones:
        raise LecturaFallida("No encontré renglones de mercancía en el PDF.")
    if len(ext.renglones) > MAX_RENGLONES:
        raise _demasiados(len(ext.renglones))
    return ext


def _guardar_pdf(db: Session, carga: CargaMercancia, ext) -> None:
    for orden, r in enumerate(ext.renglones, 1):
        db.add(CargaRenglon(organization_id=carga.organization_id, carga_id=carga.id,
                            orden=orden, crudo=r.model_dump(mode="json"), cantidad=r.cantidad))
    carga.monedas = {k: (None if v is None else float(v)) for k, v in ext.monedas.items()}
    db.flush()


def _mapear_excel(carga: CargaMercancia, contenido: bytes, cliente: ClienteEstructurado,
                  instrucciones: str, tokens: _Tokens, latido: Callable[[], None]) -> dict:
    """Pide al modelo el mapa de columnas de cada pestaña. No escribe nada en la base."""
    try:
        tablas = leer_tablas(contenido, carga.archivo_tipo or "")
    except Exception as e:
        raise LecturaFallida("No se pudo leer la hoja de cálculo: el archivo está dañado "
                             "o no es un Excel o CSV válido.") from e
    filas = sum(len(t.filas) for t in tablas)
    if filas == 0:
        raise LecturaFallida("El archivo no trae renglones con datos.")
    if filas > MAX_RENGLONES:
        raise _demasiados(filas)
    lectura = []
    for t in tablas:
        mapa, entrada, salida = mapear_columnas(t, cliente, instrucciones)
        tokens.sumar(entrada, salida)
        latido()
        if not any(v is not None for v in mapa.campos.values()) and not mapa.columnas_dinero:
            continue  # pestaña sin columnas que sirvan
        lectura.append({
            "pestana": t.pestana, "encabezados": t.encabezados,
            "mapa": {"campos": mapa.campos, "columnas_dinero": mapa.columnas_dinero,
                     "texto_libre": mapa.texto_libre},
            "rol_dinero": {},
        })
    if not lectura:
        raise LecturaFallida("No reconocí columnas de mercancía (descripción, cantidad, "
                             "precio…) en el archivo.")
    return {"tablas": lectura}


def _limpiar_lectura_previa(db: Session, carga: CargaMercancia) -> None:
    """Un reintento parte de cero (la lectura anterior no dejó renglones)."""
    for modelo in (CargaCambio, CargaDuda, CargaRenglon):
        (db.query(modelo)
         .filter(modelo.organization_id == carga.organization_id, modelo.carga_id == carga.id)
         .delete(synchronize_session=False))
    carga.lectura = None
    carga.monedas = None
    db.flush()


class _Descartada(Exception):
    """La carga cambió mientras el hilo leía (otro intento, error o aplicada)."""


def _vigente(db: Session, carga_id: str, intento: Optional[str]) -> Optional[CargaMercancia]:
    """Relee la carga con candado de fila. None si ya no está en `leyendo` o si su
    intento no es el de este hilo: lo leído se descarta sin tocarla."""
    db.flush()
    carga = (db.query(CargaMercancia).filter(CargaMercancia.id == carga_id)
             .with_for_update().populate_existing().first())
    if carga is None or carga.estado != "leyendo" or carga.intento != intento:
        return None
    return carga


def _extraer(db: Session, carga: CargaMercancia, cliente: Optional[ClienteEstructurado],
             tokens: _Tokens, latido: Callable[[], None]) -> dict:
    """Todo lo que pasa por el modelo, sin escribir nada en la base: el latido
    toca la fila desde otra sesión y no debe toparse con un candado de este hilo."""
    org = db.get(Organization, carga.organization_id)
    instrucciones = (getattr(org, "ai_instrucciones", None) or "").strip()
    verificar_cupo(db, carga.organization_id)
    if cliente is None:
        cliente = cliente_estructurado_por_defecto()
    archivo = (db.query(CargaArchivo)
               .filter(CargaArchivo.organization_id == carga.organization_id,
                       CargaArchivo.carga_id == carga.id)
               .first())
    if archivo is None:
        raise LecturaFallida("La carga no tiene su archivo: vuelve a subirlo.")
    if carga.archivo_tipo == "pdf":
        return {"pdf": _extraer_pdf(archivo.contenido, cliente, instrucciones, tokens, latido)}
    return {"lectura": _mapear_excel(carga, archivo.contenido, cliente, instrucciones, tokens, latido)}


def _escribir(db: Session, carga_id: str, intento: Optional[str], leido: dict) -> CargaMercancia:
    """Con la carga bloqueada y comprobada vigente: renglones y plan. Sin commit."""
    carga = _vigente(db, carga_id, intento)
    if carga is None:
        raise _Descartada()
    _limpiar_lectura_previa(db, carga)
    if "pdf" in leido:
        _guardar_pdf(db, carga, leido["pdf"])
    else:
        carga.lectura = leido["lectura"]
        # Sin columnas de dinero no hay nada que preguntar: los renglones salen ya.
        rearmar_renglones_excel(db, carga)
    recalcular_plan(db, carga)
    return carga


def _mensaje(e: Exception) -> str:
    if isinstance(e, (LecturaFallida, ProveedorNoDisponible)):
        return str(e) or _FALLA_GENERICA
    if isinstance(e, HTTPException) and isinstance(e.detail, str):
        return e.detail
    return _FALLA_GENERICA


def _cargar(db: Session, carga_id: str) -> Optional[CargaMercancia]:
    # Proceso interno: el id viene de una carga que la petición ya filtró por org.
    return db.query(CargaMercancia).filter(CargaMercancia.id == carga_id).first()


def latir(carga_id: str, intento: Optional[str], sesiones=None) -> bool:
    """Toca `updated_at` en una transacción corta y aparte, para que la
    recuperación perezosa no tome por colgada una lectura que sigue viva.
    Solo si la carga sigue en `leyendo` con este intento. Nunca lanza."""
    if sesiones is None:
        from app.core.database import SessionLocal as sesiones
    s = sesiones()
    try:
        n = (s.query(CargaMercancia)
             .filter(CargaMercancia.id == carga_id, CargaMercancia.estado == "leyendo",
                     CargaMercancia.intento == intento)
             .update({CargaMercancia.updated_at: datetime.now(timezone.utc)},
                     synchronize_session=False))
        s.commit()
        return bool(n)
    except Exception:  # noqa: BLE001 - un latido perdido no detiene la lectura
        logger.warning("No se pudo marcar el avance de la carga %s", carga_id, exc_info=True)
        s.rollback()
        return False
    finally:
        s.close()


def procesar_carga(carga_id: str, cliente: Optional[ClienteEstructurado] = None,
                   db: Optional[Session] = None,
                   latido: Optional[Callable[[], None]] = None) -> None:
    """Lee el archivo y deja el plan (`plan`) o el error (`error`). Nunca lanza.

    Si mientras leía la carga dejó de ser suya (la recuperación la marcó `error`,
    un "Volver a intentar" puso otro intento, se aplicó o se descartó), lo leído
    se descarta y la carga no se toca."""
    propia = db is None
    if propia:
        from app.core.database import SessionLocal
        db = SessionLocal()
    try:
        carga = _cargar(db, carga_id)
        if carga is None or carga.estado != "leyendo":
            return
        intento = carga.intento
        org_id = carga.organization_id
        if latido is None:
            # En línea (pruebas) no hay otro hilo que pueda tomarla por colgada.
            latido = (lambda: latir(carga_id, intento)) if propia else (lambda: None)
        tokens = _Tokens()
        fallo: Optional[Exception] = None
        descartada = False
        try:
            leido = _extraer(db, carga, cliente, tokens, latido)
            with db.begin_nested():  # todo o nada: una falla no deja renglones a medias
                carga = _escribir(db, carga_id, intento, leido)
                carga.estado = "plan"
                carga.error = None
                db.flush()
        except _Descartada:
            descartada = True
        except Exception as e:  # noqa: BLE001 - toda falla queda en la carga
            fallo = e
            if not isinstance(e, (LecturaFallida, ProveedorNoDisponible, HTTPException)):
                logger.exception("Falla al leer la carga %s", carga_id)
            carga = _vigente(db, carga_id, intento)
            if carga is None:
                descartada = True
            else:
                carga.estado = "error"
                carga.error = _mensaje(e)
        if descartada:
            # Lo escrito quedó dentro del SAVEPOINT revertido; la carga no se toca.
            logger.info("Carga %s: la lectura terminó con la carga ya cambiada; se descarta", carga_id)
            if tokens.entrada or tokens.salida:  # el gasto del modelo sí ocurrió
                registrar_uso(db, org_id, tokens.entrada, tokens.salida)
            db.commit()  # suelta el candado de `_vigente`
            return
        if tokens.entrada or tokens.salida:
            registrar_uso(db, carga.organization_id, tokens.entrada, tokens.salida)
            carga.tokens_entrada = (carga.tokens_entrada or 0) + tokens.entrada
            carga.tokens_salida = (carga.tokens_salida or 0) + tokens.salida
        db.commit()
        if fallo is None:
            logger.info("Carga %s leída", carga_id)
    except Exception:  # pragma: no cover - ni siquiera se pudo guardar el error
        logger.exception("No se pudo guardar el resultado de la carga %s", carga_id)
        db.rollback()
    finally:
        if propia:
            db.close()


def lanzar_proceso(carga_id: str, cliente: Optional[ClienteEstructurado] = None,
                   db: Optional[Session] = None) -> None:
    """En producción, un hilo con su propia sesión y su propio cliente. Con
    `CARGAS_PROCESO_EN_LINEA=1` corre aquí mismo con la sesión y el cliente dados."""
    if os.getenv("CARGAS_PROCESO_EN_LINEA") == "1":
        procesar_carga(carga_id, cliente, db=db)
        return
    threading.Thread(target=procesar_carga, args=(carga_id,), daemon=True,
                     name=f"carga-{carga_id}").start()


# ── reintentar, descartar, recuperar ──────────────────────────────────────

def _tiene_renglones(db: Session, carga: CargaMercancia) -> bool:
    return db.query(CargaRenglon.id).filter(
        CargaRenglon.organization_id == carga.organization_id,
        CargaRenglon.carga_id == carga.id).first() is not None


def reintentar(db: Session, carga: CargaMercancia) -> bool:
    """Solo en `error`. Con renglones (falló al aplicar) vuelve a revisión; sin
    renglones (falló al leer) vuelve a `leyendo`. Devuelve True si hay que leer.
    Sin commit."""
    if carga.estado != "error":
        raise HTTPException(status_code=409, detail="Solo se reintenta una carga con error.")
    if carga.aplicada_at is not None:
        # Ya entró al inventario: leerla o revisarla otra vez metería las piezas dos veces.
        raise HTTPException(status_code=409, detail=YA_APLICADA)
    if _tiene_renglones(db, carga):
        volver_a_plan(db, carga)
        return False
    carga.estado = "leyendo"
    carga.error = None
    carga.intento = str(uuid.uuid4())
    db.flush()
    return True


def descartar(db: Session, carga: CargaMercancia) -> None:
    if carga.estado not in ("plan", "error"):
        raise HTTPException(status_code=409,
                            detail=f"La carga #{carga.folio} no se puede descartar "
                                   f"(estado: {carga.estado}).")
    carga.estado = "descartada"
    db.flush()


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def recuperar_cargas_colgadas(db: Session, minutos: int = MINUTOS_COLGADA,
                              org_id: Optional[int] = None) -> int:
    """Cargas en `leyendo`/`aplicando` sin moverse en `minutos` quedan en `error`
    para que el usuario las reintente o las descarte. Al arrancar se llama con
    `minutos=0` (en un proceso nuevo ninguna lectura sigue viva); las consultas
    de la pantalla la llaman con el tope normal y su `org_id`. Devuelve cuántas marcó."""
    limite = datetime.now(timezone.utc) - timedelta(minutes=minutos)
    # Solo se bloquean las que llevan `minutos` sin moverse, y sin esperar: una
    # carga cuyo hilo está guardando su resultado (fila bloqueada) no está colgada.
    q = (db.query(CargaMercancia)
         .filter(CargaMercancia.estado.in_(tuple(_INTERRUMPIDA)), CargaMercancia.updated_at <= limite)
         .with_for_update(skip_locked=True))
    if org_id is not None:
        q = q.filter(CargaMercancia.organization_id == org_id)
    marcadas = 0
    for carga in q.all():
        if (_utc(carga.updated_at) or limite) <= limite:
            carga.error = _INTERRUMPIDA[carga.estado]
            carga.estado = "error"
            marcadas += 1
    if marcadas:
        db.commit()
    return marcadas


def piezas_por_carga(db: Session, org_id: int, ids: list[str]) -> dict[str, Decimal]:
    """Suma de cantidades que cuentan (sin YA_CARGADO ni IGNORADO) por carga."""
    if not ids:
        return {}
    filas = (db.query(CargaRenglon.carga_id, func.sum(CargaRenglon.cantidad))
             .filter(CargaRenglon.organization_id == org_id, CargaRenglon.carga_id.in_(ids),
                     (CargaRenglon.clase == None) | CargaRenglon.clase.notin_(("YA_CARGADO", "IGNORADO")))  # noqa: E711
             .group_by(CargaRenglon.carga_id).all())
    return {cid: Decimal(str(total or 0)) for cid, total in filas}
