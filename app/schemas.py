from pydantic import BaseModel, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models import UserRole

# --- SCHEMAS PARA TENANT (NEGOCIO) ---

# Lo que esperamos recibir del frontend cuando crean un negocio nuevo
class TenantCreate(BaseModel):
    name: str
    tax_id: Optional[str] = None

# Lo que le devolvemos al frontend (incluye el ID generado y la fecha)
class TenantResponse(BaseModel):
    id: UUID
    name: str
    tax_id: Optional[str]
    created_at: datetime

    # Esta configuración le dice a Pydantic que sepa leer los modelos de SQLAlchemy
    model_config = ConfigDict(from_attributes=True)

# --- SCHEMAS PARA USUARIOS ---

# Lo que recibimos cuando creamos un cajero o administrador
class UserCreate(BaseModel):
    tenant_id: UUID
    username: str
    password: str
    role: UserRole = UserRole.CASHIER

# Lo que devolvemos (NUNCA devolvemos la contraseña, por eso no está acá)
class UserResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    username: str
    role: UserRole
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- SCHEMAS PARA LOGIN ---

# La estructura estándar que espera FastAPI para devolver un token
class Token(BaseModel):
    access_token: str
    token_type: str

# Los datos que irán "empaquetados" y ocultos dentro del Token
class TokenData(BaseModel):
    user_id: str
    tenant_id: str
    role: str