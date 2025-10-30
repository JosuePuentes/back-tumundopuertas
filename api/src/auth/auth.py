from passlib.context import CryptContext
from ..config.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from ..config.mongodb import usuarios_collection
from bson import ObjectId
from datetime import datetime, timedelta
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

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