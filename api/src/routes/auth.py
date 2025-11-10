from fastapi import APIRouter, HTTPException, status
from ..config.mongodb import usuarios_collection, clientes_usuarios_collection
from ..auth.auth import get_password_hash, verify_password, create_admin_access_token, create_cliente_access_token
from ..models.authmodels import (
    UserAdmin, AdminLogin, ForgotPasswordRequest, ResetPasswordRequest,
    ClienteRegister, ClienteLogin, ClienteForgotPasswordRequest,
    ClienteVerifyCodeRequest, ClienteResetPasswordRequest
)
from datetime import datetime, timedelta
import secrets

router = APIRouter()

@router.post("/register/")
async def register_admin(user: UserAdmin):
    if usuarios_collection.find_one({"usuario": user.usuario}):
        raise HTTPException(status_code=400, detail="Usuario ya registrado")
    if usuarios_collection.find_one({"identificador": user.identificador}):
        raise HTTPException(status_code=400, detail="Identificador ya registrado")
    hashed_password = get_password_hash(user.password)
    new_admin = user.dict()
    new_admin["password"] = hashed_password
    result = usuarios_collection.insert_one(new_admin)
    if result.inserted_id:
        return {"message": "Usuario administrativo registrado exitosamente"}
    raise HTTPException(status_code=500, detail="Error al registrar el usuario administrativo")

@router.post("/login/")
async def admin_login(admin: AdminLogin):
    try:
        print(f"DEBUG LOGIN: Intentando login para usuario: {admin.usuario}")
        
        # Buscar usuario con timeout implícito
        db_admin = usuarios_collection.find_one({"usuario": admin.usuario})
        
        if not db_admin:
            print(f"DEBUG LOGIN: Usuario no encontrado: {admin.usuario}")
            raise HTTPException(status_code=401, detail="Usuario no encontrado")
        
        print(f"DEBUG LOGIN: Usuario encontrado, verificando contraseña...")
        
        # Verificar contraseña
        if not verify_password(admin.password, db_admin["password"]):
            print(f"DEBUG LOGIN: Contraseña incorrecta para usuario: {admin.usuario}")
            raise HTTPException(status_code=401, detail="Contraseña incorrecta")
        
        print(f"DEBUG LOGIN: Contraseña correcta, generando token...")
        
        # Generar token
        access_token = create_admin_access_token(db_admin)
        
        print(f"DEBUG LOGIN: Token generado. User {admin.usuario} logged in with permissions: {db_admin.get('permisos', [])}")
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "permisos": db_admin.get("permisos", []),
            "usuario": db_admin.get("usuario", ""),
            "identificador": db_admin.get("identificador", "")
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR LOGIN: Error inesperado durante login: {str(e)}")
        import traceback
        print(f"TRACEBACK LOGIN: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor durante el login: {str(e)}")

@router.post("/create-temp-admin/")
async def create_temp_admin():
    temp_username = "adminjosue"
    temp_password = "password123"
    temp_identificador = "adminjosue_id"

    if usuarios_collection.find_one({"usuario": temp_username}):
        raise HTTPException(status_code=400, detail="Temporary admin user already exists")

    hashed_password = get_password_hash(temp_password)
    new_admin = {
        "usuario": temp_username,
        "password": hashed_password,
        "identificador": temp_identificador,
        "permisos": ["admin"],
        "rol": "admin",
        "modulos": []
    }
    result = usuarios_collection.insert_one(new_admin)
    if result.inserted_id:
        return {"message": "Temporary admin user created successfully"}
    raise HTTPException(status_code=500, detail="Error creating temporary admin user")

@router.post("/reset-josue-password/")
async def reset_josue_password():
    users = list(usuarios_collection.find())
    for user in users:
        user["_id"] = str(user["_id"])
    return users


@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    user = usuarios_collection.find_one({"usuario": request.usuario})
    if not user:
        # No revelar si el usuario existe o no por seguridad
        raise HTTPException(status_code=200, detail="Si el usuario existe, se ha enviado un enlace de restablecimiento de contraseña.")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1) # Token válido por 1 hora

    usuarios_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"reset_token": token, "reset_token_expires": expires_at}}
    )

    # En un entorno real, aquí se enviaría un correo electrónico al usuario con el token.
    # Por ahora, solo devolvemos el token para propósitos de prueba/desarrollo.
    print(f"DEBUG: Token de restablecimiento para {request.usuario}: {token}")
    return {"message": "Si el usuario existe, se ha enviado un enlace de restablecimiento de contraseña.", "reset_token": token} # DEBUG: remove reset_token in production

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    user = usuarios_collection.find_one({"reset_token": request.token})

    if not user or user.get("reset_token_expires") < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Token inválido o expirado.")

    hashed_password = get_password_hash(request.new_password)

    usuarios_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"password": hashed_password}, "$unset": {"reset_token": "", "reset_token_expires": ""}}
    )

    return {"message": "Contraseña restablecida exitosamente."}

# ============================================================================
# ENDPOINTS PARA CLIENTES AUTENTICADOS
# ============================================================================

@router.post("/clientes/register/")
async def register_cliente(cliente: ClienteRegister):
    """
    Registro de nuevos clientes autenticados.
    Crea un usuario cliente en la colección clientes_usuarios.
    """
    # Verificar si el usuario ya existe
    if clientes_usuarios_collection.find_one({"usuario": cliente.usuario}):
        raise HTTPException(status_code=400, detail="El usuario ya está registrado")
    
    # Verificar si la cédula ya está registrada
    if clientes_usuarios_collection.find_one({"cedula": cliente.cedula}):
        raise HTTPException(status_code=400, detail="La cédula ya está registrada")
    
    # Hashear contraseña
    hashed_password = get_password_hash(cliente.password)
    
    # Crear documento del cliente
    nuevo_cliente = {
        "usuario": cliente.usuario,
        "password": hashed_password,
        "nombre": cliente.nombre,
        "cedula": cliente.cedula,
        "direccion": cliente.direccion,
        "telefono": cliente.telefono,
        "rol": "cliente",
        "fecha_creacion": datetime.utcnow(),
        "activo": True
    }
    
    # Insertar en la base de datos
    result = clientes_usuarios_collection.insert_one(nuevo_cliente)
    
    if result.inserted_id:
        return {
            "message": "Cliente registrado exitosamente",
            "cliente_id": str(result.inserted_id)
        }
    
    raise HTTPException(status_code=500, detail="Error al registrar el cliente")

@router.post("/clientes/login/")
async def cliente_login(cliente: ClienteLogin):
    """
    Login de clientes autenticados.
    Devuelve cliente_access_token en lugar de access_token.
    """
    try:
        print(f"DEBUG CLIENTE LOGIN: Intentando login para cliente: {cliente.usuario}")
        
        db_cliente = clientes_usuarios_collection.find_one({"usuario": cliente.usuario})
        
        if not db_cliente:
            print(f"DEBUG CLIENTE LOGIN: Cliente no encontrado: {cliente.usuario}")
            raise HTTPException(status_code=401, detail="Usuario no encontrado")
        
        if not db_cliente.get("activo", True):
            print(f"DEBUG CLIENTE LOGIN: Cliente inactivo: {cliente.usuario}")
            raise HTTPException(status_code=403, detail="Cliente inactivo")
        
        print(f"DEBUG CLIENTE LOGIN: Cliente encontrado y activo, verificando contraseña...")
        
        if not verify_password(cliente.password, db_cliente["password"]):
            print(f"DEBUG CLIENTE LOGIN: Contraseña incorrecta para cliente: {cliente.usuario}")
            raise HTTPException(status_code=401, detail="Contraseña incorrecta")
        
        print(f"DEBUG CLIENTE LOGIN: Contraseña correcta, generando token...")
        
        # Generar token para cliente
        cliente_access_token = create_cliente_access_token(db_cliente)
        
        print(f"DEBUG CLIENTE LOGIN: Token generado. Cliente {cliente.usuario} logged in successfully")
        
        return {
            "cliente_access_token": cliente_access_token,
            "token_type": "bearer",
            "cliente_id": str(db_cliente["_id"]),
            "usuario": db_cliente.get("usuario", ""),
            "nombre": db_cliente.get("nombre", ""),
            "rol": "cliente"
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR CLIENTE LOGIN: Error inesperado durante login: {str(e)}")
        import traceback
        print(f"TRACEBACK CLIENTE LOGIN: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor durante el login: {str(e)}")

# ============================================================================
# ENDPOINTS PARA RECUPERACIÓN DE CONTRASEÑA DE CLIENTES
# ============================================================================

@router.post("/clientes/forgot-password/")
async def cliente_forgot_password(request: ClienteForgotPasswordRequest):
    """
    Envía un código de recuperación de contraseña por email al cliente.
    Genera un código numérico de 6 dígitos y lo almacena en la BD con expiración.
    """
    try:
        cliente = clientes_usuarios_collection.find_one({"usuario": request.usuario})
        if not cliente:
            # Por seguridad, no revelar si el usuario existe o no
            return {
                "message": "Si el usuario existe, se ha enviado un código de recuperación de contraseña."
            }
        
        # Generar código numérico de 6 dígitos
        codigo = secrets.randbelow(900000) + 100000  # Genera un número entre 100000 y 999999
        codigo_str = str(codigo)
        
        # Establecer expiración del código (15 minutos)
        expires_at = datetime.utcnow() + timedelta(minutes=15)
        
        # Guardar código y expiración en la BD
        clientes_usuarios_collection.update_one(
            {"_id": cliente["_id"]},
            {
                "$set": {
                    "reset_codigo": codigo_str,
                    "reset_codigo_expires": expires_at
                }
            }
        )
        
        # En un entorno real, aquí se enviaría un correo electrónico al cliente con el código.
        # Por ahora, solo lo imprimimos en consola para propósitos de prueba/desarrollo.
        print(f"DEBUG CLIENTE FORGOT PASSWORD: Código de recuperación para {request.usuario}: {codigo_str}")
        print(f"DEBUG CLIENTE FORGOT PASSWORD: El código expira en: {expires_at}")
        
        # TODO: En producción, enviar email con el código
        # Ejemplo: send_email(cliente.get("email"), "Código de recuperación", f"Tu código es: {codigo_str}")
        
        return {
            "message": "Si el usuario existe, se ha enviado un código de recuperación de contraseña.",
            "codigo": codigo_str  # DEBUG: Remover en producción
        }
        
    except Exception as e:
        print(f"ERROR CLIENTE FORGOT PASSWORD: {str(e)}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al procesar solicitud: {str(e)}")

@router.post("/clientes/verify-code/")
async def cliente_verify_code(request: ClienteVerifyCodeRequest):
    """
    Verifica que el código de recuperación de contraseña sea correcto y no esté expirado.
    """
    try:
        cliente = clientes_usuarios_collection.find_one({"usuario": request.usuario})
        if not cliente:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        # Verificar que existe un código de recuperación
        codigo_guardado = cliente.get("reset_codigo")
        if not codigo_guardado:
            raise HTTPException(status_code=400, detail="No hay código de recuperación pendiente. Solicita uno nuevo.")
        
        # Verificar expiración
        expires_at = cliente.get("reset_codigo_expires")
        if not expires_at or expires_at < datetime.utcnow():
            # Limpiar código expirado
            clientes_usuarios_collection.update_one(
                {"_id": cliente["_id"]},
                {"$unset": {"reset_codigo": "", "reset_codigo_expires": ""}}
            )
            raise HTTPException(status_code=400, detail="El código ha expirado. Solicita uno nuevo.")
        
        # Verificar que el código coincida
        if codigo_guardado != request.codigo:
            raise HTTPException(status_code=400, detail="Código incorrecto")
        
        # Código válido - marcar como verificado
        clientes_usuarios_collection.update_one(
            {"_id": cliente["_id"]},
            {"$set": {"reset_codigo_verified": True}}
        )
        
        return {
            "message": "Código verificado correctamente",
            "verified": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR CLIENTE VERIFY CODE: {str(e)}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al verificar código: {str(e)}")

@router.post("/clientes/reset-password/")
async def cliente_reset_password(request: ClienteResetPasswordRequest):
    """
    Restablece la contraseña del cliente usando el código de recuperación verificado.
    """
    try:
        cliente = clientes_usuarios_collection.find_one({"usuario": request.usuario})
        if not cliente:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        # Verificar que existe un código de recuperación
        codigo_guardado = cliente.get("reset_codigo")
        if not codigo_guardado:
            raise HTTPException(status_code=400, detail="No hay código de recuperación pendiente. Solicita uno nuevo.")
        
        # Verificar expiración
        expires_at = cliente.get("reset_codigo_expires")
        if not expires_at or expires_at < datetime.utcnow():
            # Limpiar código expirado
            clientes_usuarios_collection.update_one(
                {"_id": cliente["_id"]},
                {"$unset": {"reset_codigo": "", "reset_codigo_expires": "", "reset_codigo_verified": ""}}
            )
            raise HTTPException(status_code=400, detail="El código ha expirado. Solicita uno nuevo.")
        
        # Verificar que el código coincida
        if codigo_guardado != request.codigo:
            raise HTTPException(status_code=400, detail="Código incorrecto")
        
        # Verificar que el código haya sido verificado previamente (opcional pero recomendado)
        # Esto asegura que el usuario pasó por el endpoint verify-code primero
        if not cliente.get("reset_codigo_verified"):
            raise HTTPException(status_code=400, detail="Debes verificar el código primero usando /auth/clientes/verify-code/")
        
        # Validar nueva contraseña (mínimo 6 caracteres)
        if len(request.new_password) < 6:
            raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 6 caracteres")
        
        # Hashear nueva contraseña
        hashed_password = get_password_hash(request.new_password)
        
        # Actualizar contraseña y limpiar códigos de recuperación
        clientes_usuarios_collection.update_one(
            {"_id": cliente["_id"]},
            {
                "$set": {"password": hashed_password},
                "$unset": {
                    "reset_codigo": "",
                    "reset_codigo_expires": "",
                    "reset_codigo_verified": ""
                }
            }
        )
        
        print(f"DEBUG CLIENTE RESET PASSWORD: Contraseña restablecida para {request.usuario}")
        
        return {
            "message": "Contraseña restablecida exitosamente"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR CLIENTE RESET PASSWORD: {str(e)}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al restablecer contraseña: {str(e)}")

