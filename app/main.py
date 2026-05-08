from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func
from jose import JWTError, jwt
from app.database import get_db
from app.config import settings
from app import models, schemas, security
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Gestión PWA API")

# --- CONFIGURACIÓN DE CORS ---
# Acá definimos qué "patentes" dejamos entrar a la planta
origins = [
    "http://localhost:5173",      # El puerto por defecto de Vue/Vite
    "http://127.0.0.1:5173",
    # Cuando subamos esto a un servidor real, agregaremos la URL final acá (ej: "https://mi-kiosco.com")
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Permite todos los métodos (GET, POST, PUT, DELETE)
    allow_headers=["*"], # Permite todos los encabezados (incluyendo el token de autorización)
)

# Este es el "guardia" que va a buscar el token en la cabecera de las peticiones
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

@app.get("/")
def read_root():
    return {"mensaje": "Backend operativo y seguro 🚀"}

# ==========================================
# ENDPOINTS DE NEGOCIO (TENANTS)
# ==========================================

@app.post("/tenants/", response_model=schemas.TenantResponse)
def create_tenant(tenant: schemas.TenantCreate, db: Session = Depends(get_db)):
    db_tenant = models.Tenant(name=tenant.name, tax_id=tenant.tax_id)
    db.add(db_tenant)
    db.commit()
    db.refresh(db_tenant)
    return db_tenant

# ==========================================
# ENDPOINTS DE USUARIOS Y SEGURIDAD
# ==========================================

@app.post("/users/", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # 1. Verificamos que el usuario no exista ya en ese negocio
    db_user = db.query(models.User).filter(
        models.User.username == user.username,
        models.User.tenant_id == user.tenant_id
    ).first()
    if db_user:
        raise HTTPException(status_code=400, detail="El usuario ya existe en este negocio")
    
    # 2. Encriptamos la clave usando nuestra función de security.py
    hashed_password = security.get_password_hash(user.password)
    
    # 3. Guardamos en base de datos
    new_user = models.User(
        tenant_id=user.tenant_id,
        username=user.username,
        password_hash=hashed_password,
        role=user.role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/login", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # 1. Buscamos al usuario en la base de datos (por ahora asumimos usernames únicos globales para simplificar el login estándar)
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    
    # 2. Si no existe o la clave no coincide usando nuestro verificador...
    if not user or not security.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 3. Armamos el paquete de datos que va adentro del token
    token_data = {
        "sub": str(user.username), # "sub" es el estándar para el sujeto del token
        "user_id": str(user.id),
        "tenant_id": str(user.tenant_id),
        "role": user.role.value
    }
    
    # 4. Fabricamos el token y lo devolvemos
    access_token = security.create_access_token(data=token_data)
    return {"access_token": access_token, "token_type": "bearer"}

# ==========================================
# EL "ESCANER" DE TOKENS (DEPENDENCIA)
# ==========================================

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Esta función la vamos a inyectar en las rutas que queramos proteger"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Abrimos el token con nuestra llave secreta
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    # Buscamos que el usuario del token siga existiendo en la base de datos
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user

# Un endpoint de prueba protegido para validar que todo funciona
@app.get("/users/me", response_model=schemas.UserResponse)
def read_users_me(current_user: models.User = Depends(get_current_user)):
    # Si llegaste hasta acá, es porque tu token es válido
    return current_user

# ==========================================
# ENDPOINTS DE CATEGORÍAS
# ==========================================

@app.post("/categories/", response_model=schemas.CategoryResponse)
def create_category(
    category: schemas.CategoryCreate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user) # <-- El pase VIP
):
    # Armamos la categoría inyectando el tenant_id del usuario logueado
    db_category = models.Category(
        tenant_id=current_user.tenant_id,
        name=category.name,
        description=category.description
    )
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category

@app.get("/categories/", response_model=list[schemas.CategoryResponse])
def get_categories(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Solo devolvemos las categorías de SU negocio
    categories = db.query(models.Category).filter(
        models.Category.tenant_id == current_user.tenant_id,
        models.Category.is_active == True # Filtramos las dadas de baja
    ).offset(skip).limit(limit).all()
    return categories

# ==========================================
# ENDPOINTS DE PRODUCTOS
# ==========================================

@app.post("/products/", response_model=schemas.ProductResponse)
def create_product(
    product: schemas.ProductCreate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Validamos que, si mandó una categoría, esa categoría le pertenezca a su negocio
    if product.category_id:
        category = db.query(models.Category).filter(
            models.Category.id == product.category_id,
            models.Category.tenant_id == current_user.tenant_id
        ).first()
        if not category:
            raise HTTPException(status_code=400, detail="Categoría no encontrada o no válida para este negocio")

    db_product = models.Product(
        tenant_id=current_user.tenant_id,
        category_id=product.category_id,
        name=product.name,
        barcode=product.barcode,
        description=product.description,
        price=product.price,
        min_stock_alert=product.min_stock_alert
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product

@app.get("/products/", response_model=list[schemas.ProductResponse])
def get_products(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # La consulta del catálogo filtrada por el tenant_id
    products = db.query(models.Product).filter(
        models.Product.tenant_id == current_user.tenant_id,
        models.Product.is_active == True
    ).offset(skip).limit(limit).all()
    return products

@app.get("/products/{product_id}/stock", response_model=schemas.ProductStockResponse)
def get_product_stock(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Validamos que el producto exista y sea del negocio de este usuario
    product = db.query(models.Product).filter(
        models.Product.id == product_id,
        models.Product.tenant_id == current_user.tenant_id
    ).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    # 2. Le pedimos a PostgreSQL que sume todas las cantidades de ese producto
    # Usamos func.sum() que es infinitamente más rápido que traer todos los registros y sumarlos con Python
    total_stock = db.query(func.sum(models.StockMovement.quantity)).filter(
        models.StockMovement.product_id == product_id,
        models.StockMovement.tenant_id == current_user.tenant_id
    ).scalar() # .scalar() extrae el número crudo de la respuesta de la base de datos

    # Si el producto es nuevo y no tiene movimientos, func.sum() devuelve None. Lo pasamos a 0.
    if total_stock is None:
        total_stock = 0

    return {
        "product_id": product_id,
        "total_stock": total_stock
    }

# ==========================================
# ENDPOINTS DE SUCURSALES
# ==========================================

@app.post("/branches/", response_model=schemas.BranchResponse)
def create_branch(
    branch: schemas.BranchCreate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    db_branch = models.Branch(
        tenant_id=current_user.tenant_id,
        name=branch.name,
        address=branch.address
    )
    db.add(db_branch)
    db.commit()
    db.refresh(db_branch)
    return db_branch

@app.get("/branches/", response_model=list[schemas.BranchResponse])
def get_branches(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    branches = db.query(models.Branch).filter(
        models.Branch.tenant_id == current_user.tenant_id,
        models.Branch.is_active == True
    ).offset(skip).limit(limit).all()
    return branches

# ==========================================
# ENDPOINTS DE MOVIMIENTOS DE STOCK
# ==========================================

@app.post("/stock-movements/", response_model=schemas.StockMovementResponse)
def create_stock_movement(
    movement: schemas.StockMovementCreate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # 1. Control de calidad: ¿El producto es de este negocio?
    product = db.query(models.Product).filter(
        models.Product.id == movement.product_id,
        models.Product.tenant_id == current_user.tenant_id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado en este negocio")

    # 2. Control de calidad: ¿La sucursal es de este negocio?
    branch = db.query(models.Branch).filter(
        models.Branch.id == movement.branch_id,
        models.Branch.tenant_id == current_user.tenant_id
    ).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada en este negocio")

    # 3. Registramos el movimiento (dejando la huella digital del usuario que lo hizo)
    db_movement = models.StockMovement(
        tenant_id=current_user.tenant_id,
        product_id=movement.product_id,
        branch_id=movement.branch_id,
        user_id=current_user.id, # El ID del cajero que sacamos de su Token VIP
        quantity=movement.quantity,
        movement_type=movement.movement_type,
        notes=movement.notes
    )
    
    db.add(db_movement)
    db.commit()
    db.refresh(db_movement)
    return db_movement

@app.post("/sales/", response_model=schemas.SaleResponse)
def create_sale(
    sale_data: schemas.SaleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    try:
        # 1. Creamos la cabecera de la venta
        db_sale = models.Sale(
            tenant_id=current_user.tenant_id,
            branch_id=sale_data.branch_id,
            user_id=current_user.id,
            payment_method=sale_data.payment_method,
            total_amount=0 # Lo calcularemos sumando los items
        )
        db.add(db_sale)
        db.flush() # flush() nos da el ID de la venta sin cerrar la transacción todavía

        total_venta = 0

        # 2. Procesamos cada producto del ticket
        for item in sale_data.items:
            # Buscamos el producto en la base para tener el precio real
            product = db.query(models.Product).filter(
                models.Product.id == item.product_id,
                models.Product.tenant_id == current_user.tenant_id
            ).first()

            if not product:
                raise HTTPException(status_code=404, detail=f"Producto {item.product_id} no encontrado")

            subtotal = product.price * item.quantity
            total_venta += subtotal

            # Guardamos el detalle de la venta
            db_item = models.SaleItem(
                sale_id=db_sale.id,
                product_id=product.id,
                quantity=item.quantity,
                unit_price=product.price,
                subtotal=subtotal
            )
            db.add(db_item)

            # 3. ¡IMPORTANTE! Descontamos el stock automáticamente
            # Registramos un movimiento de salida (negativo)
            db_stock_move = models.StockMovement(
                tenant_id=current_user.tenant_id,
                product_id=product.id,
                branch_id=sale_data.branch_id,
                user_id=current_user.id,
                quantity=-item.quantity, # Restamos la cantidad vendida
                movement_type="OUT_SALE",
                notes=f"Venta ID: {db_sale.id}"
            )
            db.add(db_stock_move)

        # 4. Actualizamos el total final de la venta
        db_sale.total_amount = total_venta
        
        db.commit() # Si llegamos acá, se guarda TODO junto
        db.refresh(db_sale)
        return db_sale

    except Exception as e:
        db.rollback() # Si hubo CUALQUIER error, se deshacen los cambios
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Error al procesar la venta: {str(e)}")