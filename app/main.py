from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from app.database import get_db
from app.config import settings
from app import models, schemas, security

app = FastAPI(title="Gestión PWA API")

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