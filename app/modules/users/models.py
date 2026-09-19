"""Atlas BOS modules/users/models — Identity & Access Management.

MOONSHOT_ENGINE: Nucleus
DOMAIN: Identity & Access Management
STATUS: Stable

Phase 2 / S1 Phase B: this module owns the User, Role, PlatformRole, and
UserOrganization SQLAlchemy classes. The legacy `app/models/users.py` is
now a reverse-shim re-exporting from here.
"""
import enum

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Role(str, enum.Enum):
    ADMINISTRADOR = "ADMINISTRADOR"
    GERENTE = "GERENTE"
    CAJERO = "CAJERO"
    DUEÑO = "DUEÑO"
    VENDEDOR = "VENDEDOR"
    SOPORTE_OPERATIVO = "SOPORTE_OPERATIVO"
    CLIENTE = "CLIENTE"


class PlatformRole(str, enum.Enum):
    SUPERADMIN = "SUPERADMIN"
    SUPPORT = "SUPPORT"
    NONE = "NONE"


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)

    email = Column(String, nullable=True)            # Official/system email
    personal_email = Column(String, nullable=True)

    # Extended profile
    nationality = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    dob = Column(String, nullable=True)              # "dd/mm/yyyy" string for import flexibility

    # Biometrics / FaceID
    face_encoding = Column(JSON, nullable=True)      # 128-float list from face_recognition

    password_hash = Column(String, nullable=False)

    # PIN de reimpresion PROPIO, independiente de la contrasena (mismo hash
    # bcrypt, nunca el PIN en claro). NULL = sin PIN: ese usuario solo autoriza
    # una reimpresion tecleando su contrasena, como antes de esta columna.
    # Ver app/services/reprint_auth.py. NUNCA se expone: UserRead publica el
    # derivado `has_reprint_pin`.
    reprint_pin_hash = Column(String, nullable=True)

    # create_type=False: enum type is created externally by init_db.py
    role = Column(
        Enum(Role, name="role", create_type=False),
        default=Role.CAJERO,
        nullable=False,
    )

    is_active = Column(Boolean, default=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Platform role (SaaS)
    platform_role = Column(
        Enum(PlatformRole, name="platform_role", create_type=False),
        default=PlatformRole.NONE,
        nullable=False,
    )

    # SQLAlchemy resolves "Branch" via the registry.
    branch = relationship("Branch", back_populates="users")

    @property
    def branch_name(self) -> str | None:
        return self.branch.name if self.branch else None

    @property
    def has_reprint_pin(self) -> bool:
        """Derivado para el API: si el usuario tiene PIN de reimpresion.

        El hash nunca sale de aqui; el panel de Usuarios solo necesita saber si
        hay uno configurado para mostrar "PIN configurado" y ofrecer borrarlo.
        """
        return bool(self.reprint_pin_hash)

    # Multi-tenant relation
    organizations = relationship(
        "UserOrganization",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserOrganization(Base):
    __tablename__ = "user_organizations"
    __table_args__ = {"extend_existing": True}

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    organization_id = Column(Integer, ForeignKey("organization.id"), primary_key=True)

    org_role = Column(String, default="MEMBER")     # ADMIN, MEMBER, OWNER
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="organizations")
    organization = relationship("Organization", back_populates="users_association")
