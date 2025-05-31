from typing import Dict, List, Optional, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

from app.schemas.user import UserResponse

class TenantSettings(BaseModel):
    """Configuración específica del tenant"""
    max_documents: Optional[int] = Field(None, example=1000, description="Límite máximo de documentos")
    max_storage_gb: Optional[float] = Field(None, example=10.0, description="Límite de almacenamiento en GB")
    allowed_file_types: Optional[List[str]] = Field(None, example=["pdf", "docx", "txt"], description="Tipos de archivo permitidos")
    enable_ocr: bool = Field(True, example=True, description="Habilitar OCR para documentos escaneados")
    enable_ai_features: bool = Field(True, example=True, description="Habilitar características de IA")
    custom_branding: Optional[Dict[str, str]] = Field(None, example={"logo_url": "https://example.com/logo.png"})
    
    class Config:
        extra = "allow"  # Permitir campos adicionales

class TenantBase(BaseModel):
    name: str = Field(..., example="Acme Corporation")
    description: Optional[str] = Field(None, example="Corporación de ejemplo")
    settings: Optional[TenantSettings] = None

class TenantCreate(TenantBase):
    pass

class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, example="Acme Corporation Updated")
    description: Optional[str] = Field(None, example="Descripción actualizada")
    is_active: Optional[bool] = Field(None, example=True)
    settings: Optional[TenantSettings] = None

class TenantResponse(TenantBase):
    id: UUID = Field(..., example="123e4567-e89b-12d3-a456-426614174000")
    bucket_name: str = Field(..., example="tenant-bucket-123")
    is_active: bool = Field(..., example=True)
    created_at: datetime = Field(..., example=datetime.now())
    updated_at: datetime = Field(..., example=datetime.now())
    
    class Config:
        orm_mode = True

class TenantWithUsers(TenantResponse):
    users: List[UserResponse] = []
    
    class Config:
        orm_mode = True

# Alias for backward compatibility
Tenant = TenantResponse