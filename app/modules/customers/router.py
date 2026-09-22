"""Atlas BOS modules/customers/router — CRM REST API.

DOMAIN: Customer Relationship Management
STATUS: Stable

Phase 2 / S2: moved from app/routers/customers.py. Imports point to the
local module (models, schemas) instead of the legacy global namespace.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_
from typing import List, Optional
from decimal import Decimal

from app.core.database import get_db
from app.modules.customers.models import Customer, CustomerLedgerEntry
from app.modules.customers.schemas import (
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
    LedgerEntryResponse,
    CustomerPaymentCreate,
)
from app.core.security import get_current_user
from app.models import User
from app.core.tenant_context import get_current_active_organization

logger = logging.getLogger(__name__)

router = APIRouter()


# --------------------------------------------------------------------------
# 0. STATS (KPIs)
# --------------------------------------------------------------------------
@router.get("/stats")
def get_customer_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization),
):
    base = db.query(Customer).filter(
        Customer.is_active == True,
        Customer.organization_id == org_id,
    )
    total = base.count()
    total_debt = db.query(func.coalesce(func.sum(Customer.current_balance), 0)).filter(
        Customer.is_active == True,
        Customer.organization_id == org_id,
        Customer.current_balance > 0,
    ).scalar()
    total_credit = db.query(func.coalesce(func.sum(Customer.current_balance), 0)).filter(
        Customer.is_active == True,
        Customer.organization_id == org_id,
        Customer.current_balance < 0,
    ).scalar()
    return {
        "total": total,
        "total_debt": round(float(total_debt), 2),
        "total_credit": round(abs(float(total_credit)), 2),
        "with_debt": base.filter(Customer.current_balance > 0).count(),
        "with_credit": base.filter(Customer.current_balance < 0).count(),
    }


# --------------------------------------------------------------------------
# 1. LISTAR CLIENTES
# --------------------------------------------------------------------------
@router.get("/")
def get_customers(
    skip: int = 0,
    limit: int = 100,
    search: str = None,
    balance_filter: Optional[str] = Query(None),  # 'debt' | 'credit' | None
    paginate: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    query = db.query(Customer).filter(
        Customer.is_active == True,
        Customer.organization_id == org_id
    )
    
    if search:
        # Búsqueda multi-campo insensible a mayúsculas
        search_fmt = f"%{search}%"
        from sqlalchemy import or_
        query = query.filter(
            or_(
                Customer.name.ilike(search_fmt),
                Customer.tax_id.ilike(search_fmt),
                Customer.email.ilike(search_fmt),
                Customer.phone.ilike(search_fmt)
            )
        )
        
    if balance_filter == 'debt':
        query = query.filter(Customer.current_balance > 0)
    elif balance_filter == 'credit':
        query = query.filter(Customer.current_balance < 0)

    total = query.count()
    customers = query.order_by(Customer.name).offset(skip).limit(limit).all()

    # Enrich with Portal Status
    # Optimization: We could do a join, but for <100 customers, a list of emails check is fine or just check one by one.
    # Let's do a bulk check for emails that exist in User table.
    if customers:
        customer_emails = [c.email for c in customers if c.email]
        if customer_emails:
            from app.models.users import User, Role
            portal_users = db.query(User.username).filter(
                User.username.in_(customer_emails),
                User.role == Role.CLIENTE
            ).all()
            active_emails = {u.username for u in portal_users}
            
            for c in customers:
                if c.email and c.email in active_emails:
                    c.portal_active = True
                else:
                    c.portal_active = False
                    
    serialized = [CustomerRead.model_validate(c) for c in customers]
    if paginate:
        return {"items": serialized, "total": total, "skip": skip, "limit": limit}
    return serialized

# --------------------------------------------------------------------------
# 2. OBTENER DETALLE (INDIVIDUAL)
# --------------------------------------------------------------------------
@router.get("/{customer_id}", response_model=CustomerRead)
def get_customer(
    customer_id: int, 
    db: Session = Depends(get_db),
    org_id: int = Depends(get_current_active_organization)
):
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.organization_id == org_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
        
    # Check Portal Status
    if customer.email:
        from app.models.users import User, Role
        user_exists = db.query(User).filter(User.username == customer.email, User.role == Role.CLIENTE).first()
        customer.portal_active = bool(user_exists)
    else:
        customer.portal_active = False
        
    return customer

# --------------------------------------------------------------------------
# 3. CREAR CLIENTE
# --------------------------------------------------------------------------
@router.post("", response_model=CustomerRead, include_in_schema=False)
@router.post("/", response_model=CustomerRead)
def create_customer(
    customer_in: CustomerCreate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    # Validar RFC único (si no es nulo y no es el genérico XAXX010101000)
    if customer_in.tax_id and len(customer_in.tax_id) > 10: 
        exists = db.query(Customer).filter(
            Customer.tax_id == customer_in.tax_id, 
            Customer.tax_id != "XAXX010101000", # Excepción para Público General
            Customer.organization_id == org_id
        ).first()
        if exists:
            raise HTTPException(status_code=400, detail=f"El RFC {customer_in.tax_id} ya está registrado.")

    # Validar Correo Electrónico único (si no es nulo)
    if customer_in.email:
        email_exists = db.query(Customer).filter(
            Customer.email == customer_in.email,
            Customer.is_active == True, # Solo checar activos
            Customer.organization_id == org_id
        ).first()
        if email_exists:
            raise HTTPException(status_code=400, detail=f"El correo electrónico {customer_in.email} ya está registrado.")

    # Validar Teléfono único (si no es nulo)
    if customer_in.phone:
        phone_exists = db.query(Customer).filter(
            Customer.phone == customer_in.phone,
            Customer.is_active == True, # Solo checar activos
            Customer.organization_id == org_id
        ).first()
        if phone_exists:
            raise HTTPException(status_code=400, detail=f"El teléfono {customer_in.phone} ya está registrado.")

    new_customer = Customer(
        name=customer_in.name,
        tax_id=customer_in.tax_id,
        tax_system=customer_in.tax_system,
        email=customer_in.email,
        phone=customer_in.phone,
        address=customer_in.address,
        zip_code=customer_in.zip_code,
        has_credit=customer_in.has_credit,
        credit_limit=customer_in.credit_limit,
        credit_days=customer_in.credit_days,
        notes=customer_in.notes,
        current_balance=0, # Empieza en cero
        organization_id=org_id
    )
    
    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)

    # PORTAL ACCESS LOGIC
    if customer_in.enable_portal and customer_in.email and customer_in.password:
        from app.models.users import User, Role
        from app.core.security import get_password_hash
        
        # Check if user exists
        existing_user = db.query(User).filter(User.username == customer_in.email).first()
        
        if not existing_user:
            # Create new CLIENT user
            new_user = User(
                username=customer_in.email,
                full_name=customer_in.name,
                email=customer_in.email,
                password_hash=get_password_hash(customer_in.password),
                role=Role.CLIENTE,
                is_active=True
            )
            db.add(new_user)
            db.commit()
        else:
            # Optionally update existing user role if not ADMIN/STAFF?
            # For now, we assume if user exists, they are linked.
            # We might want to ensure they have CLIENTE role capability or just assume email link is enough.
            pass
    return new_customer

# --------------------------------------------------------------------------
# 4. ACTUALIZAR CLIENTE (PUT)
# --------------------------------------------------------------------------
@router.put("/{customer_id}", response_model=CustomerRead)
def update_customer(
    customer_id: int, 
    customer_in: CustomerUpdate, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.organization_id == org_id
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    
    # Actualizamos campos dinámicamente
    update_data = customer_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(customer, field):
            setattr(customer, field, value)
            
    db.commit()
    db.refresh(customer)

    # PORTAL ACCESS LOGIC (Update/Enable)
    if (customer_in.enable_portal or customer_in.password) and customer.email:
        from app.models.users import User, Role
        from app.core.security import get_password_hash
        
        user = db.query(User).filter(User.username == customer.email).first()
        
        if not user:
            # Create if explicitly requested via enable_portal or password provided
            if customer_in.password:
                new_user = User(
                    username=customer.email,
                    full_name=customer.name,
                    email=customer.email,
                    password_hash=get_password_hash(customer_in.password),
                    role=Role.CLIENTE,
                    is_active=True
                )
                db.add(new_user)
                db.commit()
        else:
            # Update password if provided
            if customer_in.password:
                user.password_hash = get_password_hash(customer_in.password)
                db.commit()

    return customer

# --------------------------------------------------------------------------
# 5. ELIMINAR (SOFT DELETE)
# --------------------------------------------------------------------------
@router.delete("/{customer_id}", response_model=CustomerRead)
def delete_customer(
    customer_id: int, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.organization_id == org_id
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
        
    # No eliminar si tiene deuda
    if customer.current_balance > 0:
        raise HTTPException(
            status_code=400, 
            detail=f"No se puede eliminar. El cliente tiene una deuda pendiente de ${customer.current_balance}"
        )

    customer.is_active = False # Soft Delete
    db.commit()
    return customer

# --------------------------------------------------------------------------
# 6. ESTADO DE CUENTA (MOVIMIENTOS)
# --------------------------------------------------------------------------
@router.get("/{customer_id}/statement", response_model=List[LedgerEntryResponse])
def get_customer_statement(
    customer_id: int, 
    limit: int = 50,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Obtiene el historial de cargos y abonos del cliente.
    """
    # Verificar que el cliente exista
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.organization_id == org_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
        
    query = db.query(CustomerLedgerEntry).filter(
            CustomerLedgerEntry.customer_id == customer_id,
            CustomerLedgerEntry.organization_id == org_id
        )
    
    if start_date:
        query = query.filter(CustomerLedgerEntry.created_at >= f"{start_date} 00:00:00")
    if end_date:
        query = query.filter(CustomerLedgerEntry.created_at <= f"{end_date} 23:59:59")
        
    entries = query.order_by(desc(CustomerLedgerEntry.created_at)).limit(limit).all()
        
    return entries

@router.get("/{customer_id}/unpaid-documents")
def get_customer_unpaid_documents(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Obtiene los documentos de venta (Orders/Quotes convertidos) que tienen saldo pendiente.
    Útil para seleccionar a qué documento aplicar un pago específico.
    """
    from app.models import SalesDocument, DocumentStatus, DocumentType
    
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.organization_id == org_id).first()
    if not customer:
        raise HTTPException(404, "Cliente no encontrado")
    
    # Get documents that are PENDING or PAID but linked to credit sales
    # For simplicity, we'll get all documents for this customer that might have balance
    docs = db.query(SalesDocument).filter(
        SalesDocument.customer_id == customer_id,
        SalesDocument.organization_id == org_id,
        SalesDocument.doc_type.in_([DocumentType.ORDER, DocumentType.INVOICE])
    ).order_by(desc(SalesDocument.created_at)).limit(50).all()
    
    results = []
    for doc in docs:
        # Calculate payments made to this document
        from app.models import Payment
        payments_sum = db.query(func.sum(Payment.amount)).filter(
            Payment.sales_document_id == doc.id
        ).scalar() or 0
        
        balance = float(doc.total_amount) - float(payments_sum)
        
        # Only include if there's a balance
        if balance > 0.01:
            results.append({
                "id": doc.id,
                "folio": f"{doc.series}-{doc.folio}" if doc.series and doc.folio else doc.id,
                "created_at": doc.created_at.isoformat(),
                "total_amount": float(doc.total_amount),
                "paid_amount": float(payments_sum),
                "balance": balance,
                "doc_type": doc.doc_type.value
            })
    
    return results

@router.post("/{customer_id}/pay", response_model=LedgerEntryResponse)
def register_customer_payment(
    customer_id: int,
    payment_in: CustomerPaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    """
    Registra un abono/pago de un cliente y actualiza su saldo.
    Si se proporciona sales_document_id, vincula el pago a ese documento específico.
    """
    from app.models import SalesDocument
    
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.organization_id == org_id).first()
    if not customer:
        raise HTTPException(404, "Cliente no encontrado")

    if payment_in.amount <= 0:
        raise HTTPException(400, "El monto del pago debe ser mayor a cero")

    # ATS-37: Overpayment guard — solo aplica cuando el abono está vinculado a un documento específico.
    # Abonos generales ("saldo a favor") sin documento se permiten siempre (balance puede volverse negativo).
    if payment_in.sales_document_id and payment_in.amount > customer.current_balance:
        raise HTTPException(
            status_code=422,
            detail=f"El monto del abono (${payment_in.amount}) excede el saldo pendiente del cliente (${customer.current_balance})."
        )

    # Validate document if provided
    doc_reference = None
    doc = None
    if payment_in.sales_document_id:
        doc = db.query(SalesDocument).filter(
            SalesDocument.id == payment_in.sales_document_id,
            SalesDocument.customer_id == customer_id,
            SalesDocument.organization_id == org_id
        ).first()

        if not doc:
            raise HTTPException(404, "Documento de venta no encontrado o no pertenece al cliente")

        doc_reference = f"{doc.series}-{doc.folio}" if doc.series and doc.folio else doc.id

    from app.models.sales import Payment as SalesPayment, DocumentStatus, PaymentMethod as SalesPaymentMethod
    try:
        method_enum = SalesPaymentMethod(payment_in.method.upper())
    except (ValueError, AttributeError):
        method_enum = SalesPaymentMethod.CASH

    # --- Caja que recibe el abono (y guard de efectivo) ---
    # El abono debe acreditarse a la caja de QUIEN LO COBRA hoy, no a la del
    # documento de venta original (que puede llevar semanas cerrada). Mismo
    # criterio que el checkout (app/routers/sales.py ~linea 783): sesion OPEN
    # de current_user por user_id + branch_id.
    from app.models.cash import CashSession, CashSessionStatus
    active_cash = db.query(CashSession.id).filter(
        CashSession.user_id == current_user.id,
        CashSession.branch_id == current_user.branch_id,
        CashSession.status == CashSessionStatus.OPEN,
    ).first()
    cash_session_id_value = active_cash[0] if active_cash else None

    # Replica del guard H-5 del checkout (app/routers/sales.py:419-450): el
    # efectivo es fisico y no admite excepciones de rol — si estos billetes
    # entran a un cajon de sucursal, tiene que haber una caja abierta que
    # responda por ellos. Sin este guard el pago nacia con cash_session_id en
    # NULL, caia a la rama de respaldo por documento de
    # `session_payments_filter` y se sumaba al esperado de la sesion de la
    # venta original —cerrada y cuadrada dias antes—, que pasaba a mostrar un
    # faltante por el monto del abono.
    #
    # Dos diferencias deliberadas con el checkout, ambas conservan lo que ya
    # se permitia aqui: (a) solo el efectivo exige turno; tarjeta y
    # transferencia se siguen registrando sin caja (no tocan el cajon) y se
    # atribuyen cuando hay una abierta; (b) la exencion de oficina central es
    # la misma que alla — sin `branch_id` no hay cajon del que responder.
    cobra_efectivo = method_enum == SalesPaymentMethod.CASH
    requiere_caja = cobra_efectivo and bool(current_user.branch_id)
    if requiere_caja and cash_session_id_value is None:
        logger.warning(
            "BLOCKED_CUSTOMER_PAYMENT: user_id=%s branch_id=%s customer_id=%s "
            "sales_document_id=%s reason=no_open_cash_session_cash_payment",
            current_user.id, current_user.branch_id, customer_id,
            payment_in.sales_document_id,
        )
        raise HTTPException(
            status_code=409,
            detail="Debes abrir caja antes de cobrar en efectivo",
        )

    # 1. Actualizar saldo (restar el abono)
    customer.current_balance -= payment_in.amount

    # 2. Registrar en el Ledger (Kardex de dinero)
    description = f"PAGO RECIBIDO: {payment_in.reference or 'Abono'}"
    if doc_reference:
        description = f"ABONO A TICKET {doc_reference}: {payment_in.reference or payment_in.method}"

    new_entry = CustomerLedgerEntry(
        customer_id=customer.id,
        sales_document_id=payment_in.sales_document_id,  # Link to document
        amount=-payment_in.amount,  # Negativo porque reduce la deuda
        description=description,
        organization_id=org_id
    )
    db.add(new_entry)

    # ATS-37: Create a Payment record linked to the SalesDocument
    # (`method_enum` y `cash_session_id_value` se resolvieron arriba, antes de
    # tocar el saldo, porque el guard de efectivo depende de ambos.)
    payment_record = SalesPayment(
        sales_document_id=payment_in.sales_document_id,
        customer_id=customer.id,
        created_by_id=current_user.id,
        amount=payment_in.amount,
        method=method_enum,
        reference=payment_in.reference,
        organization_id=org_id,
        cash_session_id=cash_session_id_value,
    )
    db.add(payment_record)

    # ATS-37: Mark document as PAID when the customer balance is fully covered
    if doc is not None and customer.current_balance <= 0:
        doc.status = DocumentStatus.PAID

    db.commit()
    db.refresh(new_entry)
    return new_entry

from fastapi import Response
from app.modules.customers.statement_pdf import (
    build_statement_context,
    generate_account_statement_pdf,
)

@router.get("/{customer_id}/pdf-statement")
def get_customer_statement_pdf(
    customer_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    org_id: int = Depends(get_current_active_organization)
):
    from app.modules.tenants.models import Organization

    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.organization_id == org_id
    ).first()
    if not customer:
        raise HTTPException(404, "Cliente no encontrado")

    query = db.query(CustomerLedgerEntry).filter(
        CustomerLedgerEntry.customer_id == customer_id,
        CustomerLedgerEntry.organization_id == org_id
    )

    # 1. Calcular Saldo Anterior (si hay start_date)
    previous_balance = Decimal("0.00")
    if start_date:
        # Sumar todo lo anterior a start_date
        prev_sum = db.query(func.sum(CustomerLedgerEntry.amount)).filter(
            CustomerLedgerEntry.customer_id == customer_id,
            CustomerLedgerEntry.organization_id == org_id,
            CustomerLedgerEntry.created_at < f"{start_date} 00:00:00"
        ).scalar()
        if prev_sum:
            previous_balance = prev_sum

    # 2. Filtrar entradas del periodo
    if start_date:
        query = query.filter(CustomerLedgerEntry.created_at >= f"{start_date} 00:00:00")
    if end_date:
        query = query.filter(CustomerLedgerEntry.created_at <= f"{end_date} 23:59:59")

    # Ordenar por fecha ASCENDENTE para el estado de cuenta (linea de tiempo)
    entries = query.order_by(CustomerLedgerEntry.created_at.asc()).all()

    # Recuperar Organization del tenant
    organization = db.query(Organization).filter(Organization.id == org_id).first()

    context = build_statement_context(
        customer,
        entries,
        organization=organization,
        start_date=start_date,
        end_date=end_date,
        previous_balance=previous_balance,
    )
    pdf_content = generate_account_statement_pdf(context)

    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=EdoCuenta_{customer.tax_id or 'Cliente'}.pdf"}
    )