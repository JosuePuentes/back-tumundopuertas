from passlib.context import CryptContext
from ..config.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from ..config.mongodb import usuarios_collection, clientes_usuarios_collection
from bson import ObjectId
from datetime import datetime, timedelta
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")
oauth2_cliente_scheme = OAuth2PasswordBearer(tokenUrl="auth/clientes/login")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_admin_access_token(admin: dict, expires_delta: timedelta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)) -> str:
    to_encode = {
        "id": str(admin["_id"]),
        "usuario": admin["usuario"],
        "rol": admin.get("rol", "admin"),
        "modulos": admin.get("modulos", []),
        "exp": datetime.utcnow() + expires_delta,
    }
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Obtiene el usuario actual desde la base de datos en tiempo real.
    Valida el token JWT y luego consulta la BD para obtener datos actualizados.
    Esto garantiza que los permisos y datos del usuario estén siempre sincronizados.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Decodificar token para obtener user_id
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("id")
        if user_id is None:
            raise credentials_exception
        
        # Consultar la base de datos en tiempo real para obtener datos actualizados
        try:
            user_doc = usuarios_collection.find_one({"_id": ObjectId(user_id)})
            if not user_doc:
                raise credentials_exception
            
            # Retornar datos actualizados desde la BD, no del token
            return {
                "id": str(user_doc["_id"]),
                "usuario": user_doc.get("usuario", ""),
                "rol": user_doc.get("rol", "admin"),
                "permisos": user_doc.get("permisos", []),
                "modulos": user_doc.get("modulos", []),
                "nombreCompleto": user_doc.get("nombreCompleto", ""),
                "identificador": user_doc.get("identificador", ""),
            }
        except Exception as e:
            # Si hay error al consultar la BD, usar datos del token como fallback
            print(f"WARNING: Error consultando usuario en BD: {e}, usando datos del token")
            return payload
            
    except jwt.PyJWTError:
        raise credentials_exception

async def get_current_admin_user(current_user: dict = Depends(get_current_user)):
    if current_user.get("rol") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user

def create_cliente_access_token(cliente: dict, expires_delta: timedelta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)) -> str:
    """Crea un token JWT para clientes autenticados"""
    to_encode = {
        "id": str(cliente["_id"]),
        "usuario": cliente["usuario"],
        "rol": "cliente",
        "exp": datetime.utcnow() + expires_delta,
    }
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_cliente(token: str = Depends(oauth2_cliente_scheme)):
    """
    Obtiene el cliente actual desde la base de datos en tiempo real.
    Valida el token JWT de cliente y luego consulta la BD para obtener datos actualizados.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        print(f"DEBUG GET_CURRENT_CLIENTE: Token recibido (primeros 20 chars): {token[:20] if token else 'None'}...")
        
        # Decodificar token para obtener cliente_id
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print(f"DEBUG GET_CURRENT_CLIENTE: Payload decodificado - id: {payload.get('id')}, rol: {payload.get('rol')}")
        
        cliente_id: str = payload.get("id")
        if cliente_id is None:
            print(f"ERROR GET_CURRENT_CLIENTE: No se encontró 'id' en el payload")
            raise credentials_exception
        
        # Validar que el rol sea "cliente"
        if payload.get("rol") != "cliente":
            print(f"ERROR GET_CURRENT_CLIENTE: Token no es de cliente, rol: {payload.get('rol')}")
            raise credentials_exception
        
        # Consultar la base de datos en tiempo real para obtener datos actualizados
        try:
            cliente_doc = clientes_usuarios_collection.find_one({"_id": ObjectId(cliente_id)})
            if not cliente_doc:
                print(f"ERROR GET_CURRENT_CLIENTE: Cliente no encontrado en BD con id: {cliente_id}")
                raise credentials_exception
            
            if not cliente_doc.get("activo", True):
                print(f"ERROR GET_CURRENT_CLIENTE: Cliente inactivo: {cliente_id}")
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cliente inactivo")
            
            print(f"DEBUG GET_CURRENT_CLIENTE: Cliente encontrado y validado: {cliente_id}")
            
            # Retornar datos actualizados desde la BD
            return {
                "id": str(cliente_doc["_id"]),
                "usuario": cliente_doc.get("usuario", ""),
                "nombre": cliente_doc.get("nombre", ""),
                "cedula": cliente_doc.get("cedula", ""),
                "direccion": cliente_doc.get("direccion", ""),
                "telefono": cliente_doc.get("telefono", ""),
                "rol": "cliente",
            }
        except Exception as e:
            # Si hay error al consultar la BD, usar datos del token como fallback
            print(f"WARNING GET_CURRENT_CLIENTE: Error consultando cliente en BD: {e}, usando datos del token")
            import traceback
            print(f"TRACEBACK: {traceback.format_exc()}")
            return payload
            
    except jwt.ExpiredSignatureError:
        print(f"ERROR GET_CURRENT_CLIENTE: Token expirado")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        print(f"ERROR GET_CURRENT_CLIENTE: Token inválido: {str(e)}")
        raise credentials_exception
    except Exception as e:
        print(f"ERROR GET_CURRENT_CLIENTE: Error inesperado: {str(e)}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise credentials_exception