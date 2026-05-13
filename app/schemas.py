from pydantic import BaseModel, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models import UserRole
from typing import List, Optional

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

# --- SCHEMAS PARA CATEGORÍAS ---

class CategoryCreate(BaseModel):
    name: str

class CategoryResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)

# --- SCHEMAS PARA PROVEEDORES ---
class SupplierBase(BaseModel):
    name: str
    cuit: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    contact_name: Optional[str] = None

class SupplierCreate(SupplierBase):
    pass # No necesitamos nada extra para crearlo, el tenant_id lo pone el backend

class SupplierResponse(SupplierBase):
    id: UUID
    tenant_id: UUID
    created_at: datetime

    
    model_config = ConfigDict(from_attributes=True)

# --- SCHEMAS PARA PRODUCTOS ---

# Esquema para los datos de la Familia
class ProductFamilyCreate(BaseModel):
    name: str
    category_id: UUID
    supplier_id: Optional[UUID] = None
    description: Optional[str] = None
    is_active: bool = True

# Esquema para las Variantes
class ProductVariantCreate(BaseModel):
    sku: str
    barcode: Optional[str] = None
    price: float
    cost: float
    attributes: dict = {}

# EL SUPER ESQUEMA (Lo que manda Vue.js)
class FullProductPayload(BaseModel):
    # O me mandás el ID que el usuario seleccionó en el buscador...
    existing_family_id: Optional[UUID] = None
    
    # ... O me mandás los textos para que yo cree la familia.
    new_family_data: Optional[ProductFamilyCreate] = None
    
    # Las variantes siempre van.
    variants: List[ProductVariantCreate]

# 1. El esquema hijo (La variante individual)
class ProductVariantResponse(BaseModel):
    id: UUID
    product_family_id: UUID
    sku: Optional[str] = None
    barcode: Optional[str] = None
    price: float
    cost: float
    attributes: dict
    created_at: datetime

    # Esto le dice a Pydantic que sepa leer objetos directos de SQLAlchemy
    model_config = ConfigDict(from_attributes=True)


# 2. El esquema padre (La familia completa con sus variantes anidadas)
class ProductFamilyResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    category_id: Optional[UUID] = None
    supplier_id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    
    # ¡Acá está la magia! Le decimos que devuelva la lista de variantes adentro de la familia
    variants: List[ProductVariantResponse] = []

    model_config = ConfigDict(from_attributes=True)

class ProductStockResponse(BaseModel):
    product_variant_id: UUID
    total_stock: float

# --- SCHEMAS PARA SUCURSALES (BRANCHES) ---

class BranchCreate(BaseModel):
    name: str

class BranchResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- SCHEMAS PARA MOVIMIENTOS DE STOCK ---

class StockMovementCreate(BaseModel):
    product_id: UUID
    branch_id: UUID
    quantity: int  # Positivo para ingresos (compras), negativo para egresos (ventas/roturas)
    movement_type: str  # Ej: 'IN_PURCHASE', 'OUT_SALE', 'OUT_DAMAGE', 'ADJUSTMENT'
    notes: Optional[str] = None

class StockMovementResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    product_id: UUID
    branch_id: UUID
    user_id: UUID  # Para saber QUÉ cajero hizo el movimiento
    quantity: int
    movement_type: str
    notes: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- SCHEMA PARA CONSULTA DE STOCK ---

class ProductStockResponse(BaseModel):
    product_id: UUID
    total_stock: int

# --- SCHEMAS PARA VENTAS (SALES) ---

class SaleItemCreate(BaseModel):
    product_id: UUID
    quantity: int

class SaleCreate(BaseModel):
    branch_id: UUID
    payment_method: str # Ej: 'CASH', 'DEBIT', 'CREDIT', 'TRANSFER'
    items: list[SaleItemCreate]

class SaleItemResponse(BaseModel):
    product_id: UUID
    quantity: int
    unit_price: float
    subtotal: float

    model_config = ConfigDict(from_attributes=True)

class SaleResponse(BaseModel):
    id: UUID
    branch_id: UUID
    total_amount: float
    payment_method: str
    created_at: datetime
    items: list[SaleItemResponse]

    model_config = ConfigDict(from_attributes=True)