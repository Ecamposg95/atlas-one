from typing import Optional
from pydantic import BaseModel

class BrandBase(BaseModel):
    name: str
    logo_url: Optional[str] = None

class BrandCreate(BrandBase):
    is_premium: bool = False

class BrandUpdate(BrandBase):
    # En PUT el nombre ya era obligatorio; is_premium solo cambia si se manda.
    is_premium: Optional[bool] = None

class BrandResponse(BrandBase):
    id: str
    product_count: int = 0
    is_premium: bool = False

    class Config:
        from_attributes = True
