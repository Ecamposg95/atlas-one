"""Pydantic schemas for modules / upsell."""
from typing import Dict, List, Optional

from pydantic import BaseModel


class UpsellRecommendation(BaseModel):
    module_key: str
    module_name: str
    description: Optional[str] = None
    category: Optional[str] = None  # base | advanced | vertical
    status: str  # STABLE | BETA
    in_recommended_preset: bool
    recommended_presets: List[str] = []
    value_props: List[str] = []
    upgrade_prompt: Optional[str] = None
    icon: Optional[str] = None
    sort_hint: int = 100
    plan_minimo: Optional[str] = None  # clave del plan que lo incluye; None si no depende del plan

    class Config:
        from_attributes = True


class UpsellResponse(BaseModel):
    org_id: int
    active_preset: Optional[str] = None
    active_modules: List[str]
    recommendations: List[UpsellRecommendation]
    grouped_by_preset: Dict[str, List[str]]
