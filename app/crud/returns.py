from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.returns import SaleReturn, SaleReturnItem
from app.models.sales import SalesDocument, SalesLineItem, DocumentStatus, DocumentType, PaymentMethod
from app.models.inventory import InventoryMovement, StockOnHand, MovementType
from app.schemas.returns import SaleReturnCreate
from app.models.products import ProductVariant
from app.models.organization import Organization
from app.services.tax import prorate_sale_after_refund, resolve_org_tax_mode
from typing import List
import uuid


class CashSessionClosedError(ValueError):
    """Raised when a cash refund needs an OPEN session and none is available.

    Routers should map this to HTTP 409 Conflict (state conflict, not bad
    input). Inherits from ValueError so existing `except ValueError` catches
    keep working as a fallback to 400 if not handled explicitly.
    """
    pass


# Fat-finger threshold for CASH refunds. Refunds above this value require
# explicit `force=True` from the caller (UI must confirm twice). Configurable
# per org in the future; today a single global default. $10,000 chosen so
# 99% of legitimate refunds pass without friction while catching the
# pathological cases (e.g. session 65: $104,400 single-line refund).
LARGE_CASH_REFUND_THRESHOLD = Decimal("10000")

def _lineas_por_variante(db: Session, sale_id: str) -> dict:
    """Líneas de la venta agrupadas por variante (una variante puede ocupar
    varias líneas), en orden estable."""
    grupos: dict = {}
    for linea in (
        db.query(SalesLineItem)
        .filter(SalesLineItem.document_id == sale_id)
        .order_by(SalesLineItem.id)
        .all()
    ):
        grupos.setdefault(linea.variant_id, []).append(linea)
    return grupos


def create_return(db: Session, return_in: SaleReturnCreate, user_id: int, branch_id: int, organization_id: int = None):
    # 1. Obtener la venta original — defense-in-depth: filtrar por org_id
    # aunque el router también lo verifique. Cualquier caller futuro del CRUD
    # queda protegido contra cross-tenant lookup por sale_id.
    sale_q = db.query(SalesDocument).filter(SalesDocument.id == return_in.sale_id)
    if organization_id is not None:
        sale_q = sale_q.filter(SalesDocument.organization_id == organization_id)
    sale = sale_q.first()
    if not sale:
        raise ValueError("Venta no encontrada")

    # 1b. Verificar que no haya ya una devolución PENDIENTE para esta venta
    # (mismo scope de tenant para evitar cruces en el guard).
    pending_q = db.query(SaleReturn).filter(
        SaleReturn.sale_id == sale.id,
        SaleReturn.status == "PENDING",
    )
    if organization_id is not None:
        pending_q = pending_q.filter(SaleReturn.organization_id == organization_id)
    existing_pending = pending_q.first()
    if existing_pending:
        raise ValueError("Ya existe una devolución pendiente de aprobación para esta venta")

    # 1c. Forma de la solicitud (auditoría 2026-09-22, M13). Una partida con
    # cantidad <= 0 o la misma variante dos veces pasaba la validación de
    # abajo (que compara partida por partida, sin acumular) y dejaba una
    # devolución PENDING que no se podía aprobar y que, por el guard 1b,
    # bloqueaba cualquier devolución legítima de esa venta.
    if not return_in.items:
        raise ValueError("La devolución no tiene productos: agrega al menos una partida.")
    variantes_vistas = set()
    for item_in in return_in.items:
        if item_in.quantity is None or Decimal(str(item_in.quantity)) <= 0:
            raise ValueError(
                f"La cantidad a devolver debe ser mayor a cero (producto {item_in.variant_id}). "
                "Corrige la cantidad o quita esa partida."
            )
        if item_in.variant_id in variantes_vistas:
            raise ValueError(
                f"El producto {item_in.variant_id} aparece más de una vez en la solicitud. "
                "Déjalo en una sola partida con la cantidad total a devolver."
            )
        variantes_vistas.add(item_in.variant_id)

    # 2. Validar cantidades contra lo disponible
    # Obtener devoluciones previas que fueron aprobadas
    previous_returns = db.query(SaleReturnItem).join(SaleReturn).filter(
        SaleReturn.sale_id == sale.id,
        SaleReturn.status == "APPROVED"
    ).all()
    
    returned_totals = {}
    for pr in previous_returns:
        returned_totals[pr.variant_id] = returned_totals.get(pr.variant_id, 0) + pr.quantity

    # La misma variante puede venir en VARIAS líneas de la venta (escaneada dos
    # veces sin agrupar, o una con descuento y otra sin él). Antes se miraba
    # solo la primera línea (`.first()`): de 2 + 3 piezas solo dejaba devolver
    # 2. Lo vendido —y lo cobrado— de una variante es la suma de sus líneas.
    lineas_por_variante = _lineas_por_variante(db, sale.id)

    for item_in in return_in.items:
        lineas = lineas_por_variante.get(item_in.variant_id)

        if not lineas:
            raise ValueError(f"Producto {item_in.variant_id} no pertenece a esta venta")

        vendido = sum((Decimal(str(l.quantity or 0)) for l in lineas), Decimal("0"))
        already_returned = Decimal(str(returned_totals.get(item_in.variant_id, 0)))
        available = vendido - already_returned

        if item_in.quantity > available:
            raise ValueError(f"Cantidad a devolver ({item_in.quantity}) excede lo disponible ({available}) para el producto {lineas[0].description}")

    # 3. Crear el registro de devolución
    db_return = SaleReturn(
        sale_id=return_in.sale_id,
        user_id=user_id,
        branch_id=branch_id,
        cash_session_id=return_in.cash_session_id,
        total_refunded=return_in.total_refunded,
        refund_method=return_in.refund_method,
        reason=return_in.reason,
        status="PENDING",
        supervisor_id=return_in.supervisor_id,
        organization_id=organization_id,
    )
    db.add(db_return)
    db.flush() # Para obtener el ID de la devolución

    # 4. Procesar items
    db_items = []
    for item_in in return_in.items:
        # Recompute refund_amount from source line price (don't trust client)
        lineas = lineas_por_variante.get(item_in.variant_id)
        if lineas:
            # Se prorratea `total_line` (lo que el cliente pagó de verdad por
            # esa partida), no `unit_price`, que es PRE-descuento: 2 piezas de
            # $100 con 50% de descuento se cobran $100 en total, y devolver
            # una reembolsaba $100 — el doble de lo pagado por esa pieza.
            # Auditoría C-6. Con la variante en varias líneas se prorratea
            # sobre la suma de todas (precio promedio pagado): devolverlas
            # todas reembolsa exactamente lo cobrado por ellas.
            line_item = lineas[0]
            qty_linea = sum((Decimal(str(l.quantity or 0)) for l in lineas), Decimal("0"))
            total_linea = sum((Decimal(str(l.total_line or 0)) for l in lineas), Decimal("0"))
            qty_dev = Decimal(str(item_in.quantity))
            if qty_linea > 0:
                item_refund = (total_linea * qty_dev / qty_linea).quantize(Decimal("0.01"))
            else:
                item_refund = Decimal(str(line_item.unit_price)) * qty_dev
        else:
            item_refund = Decimal(str(item_in.refund_amount))  # fallback only

        db_item = SaleReturnItem(
            return_id=db_return.id,
            variant_id=item_in.variant_id,
            quantity=item_in.quantity,
            refund_amount=item_refund,
            is_inventory_reentry=item_in.is_inventory_reentry,
            organization_id=organization_id,
        )
        db.add(db_item)
        db_items.append(db_item)

    # Override client total with server-computed sum
    computed_total = sum(item.refund_amount for item in db_items)
    db_return.total_refunded = computed_total

    db.commit()
    db.refresh(db_return)
    return db_return

def approve_return(db: Session, return_id: str, supervisor_id: int,
                   organization_id: int = None, force: bool = False):
    """Approve a pending return.

    `force=True` overrides the fat-finger threshold for large CASH refunds.
    UI must confirm twice before passing force=True. Other invariants
    (R-1 zero, R-2 exceeds sale total) are NEVER overridable — they reflect
    impossible states.
    """
    # 1. Get Return — lock row FOR UPDATE so concurrent approvals serialize.
    # H-3: scope by organization_id when provided (router supplies it).
    # H-4: row-level lock + post-lock status re-check makes this idempotent;
    # a second concurrent approve sees status=APPROVED and returns the same
    # record without double-writing inventory or cash movements.
    q = db.query(SaleReturn).filter(SaleReturn.id == return_id)
    if organization_id is not None:
        q = q.filter(SaleReturn.organization_id == organization_id)
    # `populate_existing`: el router ya cargó esta devolución (sin candado)
    # para validar la organización, y una fila que la sesión ya tiene NO se
    # refresca al releerla con `FOR UPDATE`: la segunda aprobación esperaba el
    # candado y luego seguía viendo su copia vieja en PENDING. En una
    # devolución total la frenaba R-2 (ya no queda nada por devolver); en una
    # PARCIAL se aprobaba dos veces — doble reingreso y doble salida de caja.
    db_return = q.populate_existing().with_for_update().first()
    if not db_return:
        raise ValueError("Devolución no encontrada")

    # H-4: idempotency — if another transaction already approved this return,
    # just return it. Don't raise, don't re-apply side-effects.
    if db_return.status == "APPROVED":
        return db_return
    if db_return.status != "PENDING":
        raise ValueError(f"La devolución ya está en estado {db_return.status}")

    # ── F2 invariants (pre-checks, before any side-effect) ───────────────
    refund_amount = Decimal(str(db_return.total_refunded or 0))

    # R-1: refund must be > 0
    if refund_amount <= Decimal("0"):
        raise ValueError("El monto de la devolución debe ser mayor a cero.")

    # 2. Get Sale (needed for R-2) — con candado y recién leída. Sin él, una
    # cancelación simultánea de la venta pasaba el R-0 de abajo (las dos
    # peticiones veían la venta sin cancelar) y el dinero salía dos veces.
    # Orden global de candados: (devolución →) documento → existencias →
    # cliente, el mismo de cobrar, cancelar y abonar.
    sale = (
        db.query(SalesDocument)
        .filter(SalesDocument.id == db_return.sale_id)
        .populate_existing()
        .with_for_update(of=SalesDocument)
        .first()
    )

    # R-0: una venta cancelada ya devolvio su dinero por otra via. Aprobar una
    # devolucion encima sobrescribiria su estado CANCELLED y sacaria efectivo
    # real por segunda vez.
    if sale.status == DocumentStatus.CANCELLED:
        raise ValueError("La venta fue cancelada; no se puede aprobar su devolución.")

    # R-2: no se puede devolver mas de lo que QUEDA por devolver.
    #
    # `sale.total_amount` ya viene neteado por cada aprobacion previa, asi que
    # ES el monto restante. Antes se reconstruia el total original sumandole de
    # vuelta lo ya devuelto y se comparaba contra el: tras aprobar una primera
    # devolucion por el total (restante ~0), una segunda por el total —creada
    # por la carrera que evade el guard de PENDING— tambien pasaba, produciendo
    # un DOBLE reembolso. Portado de Atlas-Rmazh (critico #3, auditoria
    # 2026-08-12).
    remaining = Decimal(str(sale.total_amount or 0))
    if refund_amount > remaining + Decimal("0.01"):
        raise ValueError(
            f"El monto a devolver ({refund_amount}) excede el restante de la "
            f"venta ({remaining})."
        )

    # R-3: large CASH refunds require explicit force=True (fat-finger guard).
    # Card/Transfer/StoreCredit refunds are exempt because they don't drain
    # the physical drawer.
    if (db_return.refund_method == PaymentMethod.CASH
            and refund_amount > LARGE_CASH_REFUND_THRESHOLD
            and not force):
        raise ValueError(
            f"Devolución en EFECTIVO de monto alto ({refund_amount}) — "
            f"confirma con force=True (umbral {LARGE_CASH_REFUND_THRESHOLD})."
        )

    # 3. Update Status
    db_return.status = "APPROVED"
    db_return.supervisor_id = supervisor_id
    db.flush()

    # 4. Inventory & Stock
    # Existencias que reingresan: bloqueadas juntas y en orden de id, para que
    # el reingreso no pise (ni lo pise) una venta simultánea de esa pieza. El
    # `.first()` de abajo devuelve estas mismas filas ya bloqueadas.
    db.query(StockOnHand).filter(
        StockOnHand.branch_id == db_return.branch_id,
        StockOnHand.variant_id.in_(
            [i.variant_id for i in db_return.items if i.is_inventory_reentry]),
    ).order_by(StockOnHand.id).with_for_update().all()
    for item in db_return.items:
        if item.is_inventory_reentry:
             # Actualizar StockOnHand
            stock = db.query(StockOnHand).filter(
                StockOnHand.branch_id == db_return.branch_id,
                StockOnHand.variant_id == item.variant_id
            ).first()

            qty_before = Decimal("0")
            if stock:
                qty_before = Decimal(str(stock.qty_on_hand))
                stock.qty_on_hand = qty_before + Decimal(str(item.quantity))
            else:
                stock = StockOnHand(
                    branch_id=db_return.branch_id,
                    variant_id=item.variant_id,
                    qty_on_hand=Decimal(str(item.quantity)),
                    organization_id=db_return.organization_id,
                )
                db.add(stock)

            # Registrar Movimiento (M-4: pure Decimal, no float coercion)
            qty_change = Decimal(str(item.quantity))
            qty_after = qty_before + qty_change
            movement = InventoryMovement(
                branch_id=db_return.branch_id,
                variant_id=item.variant_id,
                user_id=db_return.user_id,
                movement_type=MovementType.SALE_RETURN,
                qty_change=qty_change,
                qty_before=qty_before,
                qty_after=qty_after,
                reference=f"RETURN:{db_return.id}",
                notes=f"Devolución APROBADA {sale.id} - Razón: {db_return.reason}",
                organization_id=db_return.organization_id,
            )
            db.add(movement)

    # 4b. Venta fiada: lo devuelto baja primero la deuda del cliente.
    # Antes una devolución en efectivo sobre una venta a crédito le entregaba
    # dinero a un cliente que no había pagado la mercancía, y su deuda seguía
    # intacta. Solo lo que exceda la deuda viva se entrega por el método
    # elegido (auditoría del crédito, 2026-10-28).
    from app.modules.customers.services import aplicar_devolucion_a_saldo, deuda_viva_del_documento
    aplicado_a_saldo = aplicar_devolucion_a_saldo(
        db, org_id=db_return.organization_id, documento=sale, monto=refund_amount,
        descripcion=f"Devolución #{db_return.id[:8].upper()} aplicada al saldo",
    )
    a_entregar = refund_amount - aplicado_a_saldo
    db.flush()
    # Con el estado de ANTES de esta devolución: un ticket que ya estaba PAID
    # no vuelve a quedar por cobrar aunque su cargo no tenga abono enlazado.
    sigue_debiendo = bool(sale.customer_id) and deuda_viva_del_documento(
        db, org_id=db_return.organization_id, documento=sale, customer_id=sale.customer_id,
    ) > Decimal("0")

    # 5. Update Sale Status (Check if fully or partially refunded)
    # Query all approved returns for this sale
    all_returned_items = db.query(SaleReturnItem).join(SaleReturn).filter(
        SaleReturn.sale_id == sale.id,
        SaleReturn.status == "APPROVED"
    ).all()
    
    returned_totals = {}
    for ri in all_returned_items:
        returned_totals[ri.variant_id] = returned_totals.get(ri.variant_id, 0) + ri.quantity
    
    fully_refunded = True
    any_refunded = False
    
    # Por variante, no por línea: con la misma variante en dos líneas (1 + 1),
    # devolver UNA pieza igualaba la cantidad de cada línea y la venta quedaba
    # como devuelta por completo.
    vendido_por_variante = {}
    for line in sale.lines:
        vendido_por_variante[line.variant_id] = (
            vendido_por_variante.get(line.variant_id, Decimal("0")) + Decimal(str(line.quantity or 0))
        )
    for variant_id, qty_vendida in vendido_por_variante.items():
        qty_returned = Decimal(str(returned_totals.get(variant_id, 0)))
        if qty_returned > 0:
            any_refunded = True
        if qty_returned < qty_vendida:
            fully_refunded = False
            
    if fully_refunded:
        sale.status = DocumentStatus.REFUNDED_TOTAL
    elif sigue_debiendo:
        # Devolvió parte pero sigue debiendo el resto: la venta sigue por
        # cobrar (y fuera de la venta neta, como toda venta a crédito).
        sale.status = DocumentStatus.PENDING
    elif any_refunded:
        sale.status = DocumentStatus.REFUNDED_PARTIAL
    else:
        # Should not happen if we just approved one, but for completeness
        sale.status = DocumentStatus.PAID

    # 6. Crear movimiento de caja (salida de efectivo por devolución)
    # Track 1 (POS bug-fix): si refund es CASH, asociar el CashMovement a
    # la sesión OPEN del aprobador en este momento — no a la sesión donde
    # se creó la devolución (que puede estar cerrada o ser cross-day).
    # Si el aprobador no tiene sesión OPEN: error claro, dinero no sale
    # del cajón sin trazabilidad.
    if db_return.refund_method == PaymentMethod.CASH and a_entregar > Decimal("0"):
        from app.models.cash import CashSession, CashSessionStatus, CashMovement
        # Prioridad de asignación del CashMovement OUT:
        #   1) Sesión OPEN del aprobador en este branch (cajero/gerente con caja)
        #   2) Sesión original del return SI SIGUE OPEN
        #   3) Sesión original cerrada → POST-CLOSE adjustment (fallback)
        #
        # GERENTEs típicamente no operan caja propia. Si el cajero original
        # ya cerró su turno, la única forma realista de aprobar es registrar
        # la salida de efectivo contra la sesión cerrada como ajuste
        # post-corte. Se marca con prefijo [POST-CLOSE] en el reason para
        # que aparezca en auditoría/reportes como adjustment manual y el
        # gerente reconcilie con el cajero original.
        active = db.query(CashSession.id).filter(
            CashSession.user_id == supervisor_id,
            CashSession.branch_id == db_return.branch_id,
            CashSession.status == CashSessionStatus.OPEN,
        ).first()
        if not active and db_return.cash_session_id:
            active = db.query(CashSession.id).filter(
                CashSession.id == db_return.cash_session_id,
                CashSession.status == CashSessionStatus.OPEN,
            ).first()

        post_close = False
        if active:
            target_session_id = active[0]
        elif db_return.cash_session_id:
            # Fallback: sesión original aunque ya cerró → ajuste post-corte
            target_session_id = db_return.cash_session_id
            post_close = True
        else:
            # Caso recurrente en producción: la devolución se creó desde un
            # flujo (HQReturns, ReturnsBranchView, Returns admin) que NO pasó
            # cash_session_id en el body. El cajero original SÍ tuvo sesiones
            # — encontramos la más reciente en esta sucursal y registramos el
            # OUT como ajuste post-corte. Si el cajero nunca abrió caja aquí,
            # buscamos cualquier sesión reciente de la sucursal como último
            # recurso (raro pero defensivo). Solo entonces rendimos error.
            recent = db.query(CashSession.id).filter(
                CashSession.user_id == db_return.user_id,
                CashSession.branch_id == db_return.branch_id,
            ).order_by(CashSession.opened_at.desc()).first()
            if not recent:
                recent = db.query(CashSession.id).filter(
                    CashSession.branch_id == db_return.branch_id,
                    CashSession.organization_id == db_return.organization_id,
                ).order_by(CashSession.opened_at.desc()).first()
            if recent:
                target_session_id = recent[0]
                post_close = True
            else:
                raise CashSessionClosedError(
                    "La devolución no tiene una sesión de caja asociada y la "
                    "sucursal no tiene historial de cajas. Cambia el método de "
                    "reembolso a STORE_CREDIT/CARD/TRANSFER."
                )

        # CRITICAL: el reason DEBE empezar con "Devolución #" para que
        # `cash_reconciliation._is_refund_movement` lo categorice como
        # `refund_cash_outflows` en el breakdown (sino cae en `manual_out`
        # — la matemática de `expected` cuadra igual porque ambos restan,
        # pero la UI/ticket muestran el monto en "Salidas/Gastos" en vez
        # de "Reembolsos efectivo" y el warning W1 nunca dispara).
        # Por eso "[POST-CLOSE]" va al final como sufijo.
        reason_suffix = " [POST-CLOSE]" if post_close else ""
        cash_mov = CashMovement(
            session_id=target_session_id,
            type='OUT',
            amount=a_entregar,
            reason=f"Devolución #{db_return.id[:8].upper()} - {db_return.reason}{reason_suffix}",
            # Ronda de correcciones 1 de Task 4: sin esto, cada devolución
            # en efectivo nace con autor NULL — no es una fila histórica,
            # es un agujero que se sigue llenando. El autor está a la mano:
            # `supervisor_id` es quien aprueba la devolución (y por tanto
            # quien autoriza la salida de efectivo).
            created_by_user_id=supervisor_id,
        )
        db.add(cash_mov)
        # Re-asociar la devolución a la sesión donde el dinero realmente
        # sale del cajón (auditoría coherente con el corte).
        db_return.cash_session_id = target_session_id

    # 7. M-2: persistir totales NETOS en el SalesDocument padre.
    # El prorrateo vive en app/services/tax.py (fuente única de IVA, auditoría
    # Rmazh §3); aquí solo se resuelve qué se le entrega.
    #
    # `refund_amount` se calcula en create_return() como qty * unit_price, y
    # `unit_price` es neto o bruto según el modo de precio de la organización —
    # de ahí `refund_includes_tax`. El descuento se aplica sobre el estado
    # ACTUAL de la venta (que ya refleja las aprobaciones previas), así que
    # varias devoluciones secuenciales convergen sin reconstruir el original.
    # Sin esto los reportes fiscales suman valores pre-devolución y se inflan.
    this_refund = sum(
        (Decimal(str(it.refund_amount)) for it in db_return.items),
        Decimal("0"),
    )

    org_modo_bruto = resolve_org_tax_mode(
        db.query(Organization).filter(Organization.id == db_return.organization_id).first()
    )
    netos = prorate_sale_after_refund(
        current_subtotal=sale.subtotal,
        current_tax=sale.tax_amount,
        refunded_amount=this_refund,
        refund_includes_tax=org_modo_bruto,
    )

    sale.subtotal = netos.subtotal
    sale.tax_amount = netos.tax
    sale.total_amount = netos.total

    # F3: audit row before commit (atomic with the refund approval).
    from app.services.cash_audit import audit_cash_event
    from app.models.cash_audit import CashAuditEvent
    audit_cash_event(
        db,
        event_type=CashAuditEvent.REFUND_APPROVED,
        organization_id=db_return.organization_id,
        session_id=db_return.cash_session_id,
        branch_id=db_return.branch_id,
        user_id=supervisor_id,
        amount=refund_amount,
        related_table="sale_returns",
        related_id=db_return.id,
        payload={
            "sale_id": sale.id,
            "refund_method": (
                db_return.refund_method.value
                if hasattr(db_return.refund_method, "value")
                else str(db_return.refund_method)
            ),
            "force_used": force,
            "supervisor_id": supervisor_id,
        },
    )

    db.commit()
    db.refresh(db_return)
    return db_return

def reject_return(db: Session, return_id: str, supervisor_id: int, organization_id: int = None):
    """Reject a pending return.

    `organization_id` mirrors `approve_return` — defense-in-depth para
    evitar que un caller del CRUD sin la guardia del router cruce tenants.
    """
    q = db.query(SaleReturn).filter(SaleReturn.id == return_id)
    if organization_id is not None:
        q = q.filter(SaleReturn.organization_id == organization_id)
    db_return = q.first()
    if not db_return:
        raise ValueError("Devolución no encontrada")
    if db_return.status != "PENDING":
        raise ValueError("La devolución no está pendiente")

    db_return.status = "REJECTED"
    db_return.supervisor_id = supervisor_id
    db.commit()
    db.refresh(db_return)
    return db_return

def get_returns_by_sale(db: Session, sale_id: str, organization_id: int = None):
    """Devuelve los returns de una venta. `organization_id` evita que un
    caller exponga returns de otra org pasando un sale_id legítimo."""
    q = db.query(SaleReturn).filter(SaleReturn.sale_id == sale_id)
    if organization_id is not None:
        q = q.filter(SaleReturn.organization_id == organization_id)
    return q.all()
