from pydantic import BaseModel
from typing import List, Dict, Optional

class NavItem(BaseModel):
    key: str
    label: str
    href: str
    icon: str
    context: str # HQ, BRANCH, WAREHOUSE, etc.
    required_module: Optional[str] = None
    roles_allowed: List[str] = []

class PlanResumen(BaseModel):
    clave: str
    nombre: str

class OrgCapabilities(BaseModel):
    organization_id: int
    industry_type: str
    enabled_modules: List[str]
    ui_profile: str
    default_routes: Dict[str, str]
    nav_items: List[NavItem]
    plan: PlanResumen
