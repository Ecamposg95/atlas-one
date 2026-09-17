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
