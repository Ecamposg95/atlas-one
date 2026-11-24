# app/models/__init__.py

# 1. Base de datos (Origen de la clase declarativa)
from app.core.database import Base

# 2. Organización (Sucursales y Deptos)
from .organization import Branch, Organization, IndustryType
from .modules import Module, OrganizationModule, ModuleScope, ModuleStatus
# 3. Usuarios y Roles
from .users import User, Role 

# 4. Inventario y Productos
from .products import (
    Product, 
    ProductVariant, 
    Brand, 
    Department, 
    UnitOfMeasure, 
    ProductPrice,
    ProductPrice,
    PackagingUnit,
    ProductBranchStatus
)
from .inventory import InventoryMovement, MovementType, StockOnHand

# 5. Ventas y Caja
from .sales import (
    SalesDocument,
    SalesLineItem,
    Payment,
    DocumentStatus,
    DocumentType,
    PaymentMethod,
    ParkedTicket,
)

from .cash import (
    CashSession,
    CashSessionStatus,
    CashMovement
)
from .cash_audit import CashAuditLog, CashAuditEvent

# 6. Clientes
from .crm import Customer, CustomerLedgerEntry
# (Si cambiaste el nombre del archivo a 'customers.py', cambia '.crm' por '.customers')

from .returns import SaleReturn, SaleReturnItem

# 7. Impresion
from .print_job import PrintJob, PrintJobStatus

# 8. RRHH
from .hr import Employee, BranchAssignment, Attendance, EmployeeType, IncidentType

# 9. Finanzas (Portal Clientes + Compras + Gastos)
from .finance import (
    AccountTransaction, TransactionType,
    Expense,
    PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus,
)

# 10. Logística
from .logistics import (
    ContainerType, 
    BoxType, 
    ProductPackaging, 
    ContainerLoadCalc,
    InboundShipment,
    ShipmentItem,
    TransferOrder,
    TransferOrderLine,
    TransferFulfillment,
    TransferFulfillmentLine
)


# 11. Abasto
from .abasto import PurchaseRecommendation, RecommendationStatus

# 12. Outbox de eventos (entrega transaccional; create_all crea event_outbox)
from .event_outbox import EventOutbox, OutboxStatus

# 12. Plataforma (SaaS)
from .platform import (
    PlatformAuditLog,
    PlatformAlert,
    PlatformAnnouncement,
    PlatformIncident,
    FeatureFlag,
    OrgFeatureOverride,
    ApiKey,
)

# 13. Appointments (registered on Base.metadata for create_all)
from app.modules.appointments import models as _appointments_models  # noqa: F401

# 14. Gastro modules — Mesas, Cocina/KDS, Recetas
#     (registered on Base.metadata for create_all)
from app.modules.tables import models as _tables_models  # noqa: F401
from app.modules.kitchen import models as _kitchen_models  # noqa: F401
from app.modules.recipes import models as _recipes_models  # noqa: F401
from app.modules.bar import models as _bar_models  # noqa: F401

# 15. Tipo de cambio USD (tabla GLOBAL, sin organization_id — ver el docstring
#     de app/models/exchange_rate.py). Registrada aqui para `create_all`.
from .exchange_rate import ExchangeRate  # noqa: F401

# 16. Conteo físico de inventario (2026-10-22) — tablas inventory_counts e
#     inventory_count_lines; las crea `create_all`.
from app.modules.conteos import models as _conteos_models  # noqa: F401
# 17. Asistente IA (SP4): conversaciones, mensajes, propuestas y uso diario.
#     Registradas aqui para `create_all`.
from app.modules.ai import models as _ai_models  # noqa: F401
# 18. Cargar mercancía con IA: cargas, archivos, renglones, dudas y cambios.
from app.modules.cargas import models as _cargas_models  # noqa: F401
# 18. Canal «Tienda en línea»: galería de imágenes (product_images) y, en tareas
#     siguientes, el resto de tablas del canal. Registradas para `create_all`.
from app.modules.canal import models as _canal_models  # noqa: F401

# 20. Cobro de suscripciones (megaplan F3): suscripciones, suscripcion_cargos
#     y suscripcion_pagos. Registradas aqui para `create_all`.
from app.modules.suscripciones import models as _suscripciones_models  # noqa: F401

# 19. Disponibilidad web: el listener `before_flush` vive en la clase Session,
#     así que registrarlo aquí lo deja activo en todo proceso que cargue los
#     modelos (la app, pero también scripts con `SessionLocal()` que llaman
#     servicios). Módulo sin imports de la app (evita el ciclo). Idempotente:
#     el startup de app/main.py lo vuelve a llamar.
from app.services.canal_listener import registrar_listener as _registrar_listener_canal  # noqa: E402

_registrar_listener_canal()
