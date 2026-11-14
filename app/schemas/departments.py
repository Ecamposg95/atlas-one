from pydantic import BaseModel
from typing import Optional

class DepartmentBase(BaseModel):
    name: str
    description: Optional[str] = None

class DepartmentCreate(DepartmentBase):
    parent_id: Optional[str] = None

class DepartmentUpdate(DepartmentBase):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[str] = None

class DepartmentResponse(DepartmentBase):
    id: str # UUID
    parent_id: Optional[str] = None
    
    class Config:
        from_attributes = True