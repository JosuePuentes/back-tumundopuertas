from fastapi import APIRouter, HTTPException, Body, Depends
from bson import ObjectId
from ..config.mongodb import usuarios_collection
from ..auth.auth import get_password_hash, get_current_admin_user
from ..models.authmodels import UserAdmin

router = APIRouter()

@router.put("/{id}", dependencies=[Depends(get_current_admin_user)])
async def update_user(id: str, update: UserAdmin):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="ID inválido")
    existing_user = usuarios_collection.find_one({"_id": ObjectId(id)})
    if not existing_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    update_data = update.dict(exclude_unset=True)
    print(f"Updating user {id} with data: {update_data}")
    for key, value in update_data.items():
        if value == 0 or value == "0":
            raise HTTPException(status_code=400, detail=f"error o")
    if "password" in update_data and update_data["password"]:
        update_data["password"] = get_password_hash(update_data["password"])
    result = usuarios_collection.update_one({"_id": ObjectId(id)}, {"$set": update_data})
    if result.modified_count:
        updated_user = usuarios_collection.find_one({"_id": ObjectId(id)})
        updated_user["_id"] = str(updated_user["_id"])
        return updated_user
    return {"message": "No se realizaron cambios"}

@router.get("/all", dependencies=[Depends(get_current_admin_user)])
async def get_all_users():
    users = list(usuarios_collection.find())
    for user in users:
        user["_id"] = str(user["_id"])
    return users

@router.post("/agregar-permiso-cuentas-por-pagar", dependencies=[Depends(get_current_admin_user)])
async def agregar_permiso_cuentas_por_pagar():
    """
    Endpoint específico para agregar el permiso 'cuentas_por_pagar' a usuarios.
    Agrega el permiso a:
    1. Usuario JOHE (específico)
    2. Todos los usuarios con rol 'admin'
    
    Este endpoint es idempotente: no duplicará el permiso si ya existe.
    """
    permiso = "cuentas_por_pagar"
    resultados = {
        "permiso": permiso,
        "johe_actualizado": False,
        "johe_ya_tenia": False,
        "admins_actualizados": 0,
        "admins_ya_tenian": 0,
        "usuarios_con_permiso": []
    }
    
    # 1. Agregar a usuario JOHE específico
    resultado_johe = usuarios_collection.update_one(
        {"usuario": "JOHE"},
        {"$addToSet": {"permisos": permiso}}
    )
    
    if resultado_johe.matched_count > 0:
        if resultado_johe.modified_count > 0:
            resultados["johe_actualizado"] = True
            print(f"✅ Permiso '{permiso}' agregado al usuario JOHE")
        else:
            resultados["johe_ya_tenia"] = True
            print(f"ℹ️  Usuario JOHE ya tenía el permiso '{permiso}'")
    else:
        print(f"⚠️  Usuario JOHE no encontrado")
    
    # 2. Agregar a todos los usuarios con rol 'admin'
    resultado_admins = usuarios_collection.update_many(
        {"rol": "admin"},
        {"$addToSet": {"permisos": permiso}}
    )
    
    resultados["admins_actualizados"] = resultado_admins.modified_count
    resultados["admins_ya_tenian"] = resultado_admins.matched_count - resultado_admins.modified_count
    
    print(f"✅ {resultado_admins.modified_count} usuarios admin actualizados")
    print(f"ℹ️  {resultado_admins.matched_count - resultado_admins.modified_count} usuarios admin ya tenían el permiso")
    
    # 3. Verificar usuarios con el permiso
    usuarios_con_permiso = list(usuarios_collection.find(
        {"permisos": {"$in": [permiso]}},
        {"usuario": 1, "nombreCompleto": 1, "permisos": 1, "rol": 1}
    ))
    
    for usuario in usuarios_con_permiso:
        resultados["usuarios_con_permiso"].append({
            "usuario": usuario.get("usuario"),
            "nombreCompleto": usuario.get("nombreCompleto"),
            "rol": usuario.get("rol"),
            "permisos": usuario.get("permisos", [])
        })
    
    return resultados

@router.post("/agregar-permiso/{permiso}", dependencies=[Depends(get_current_admin_user)])
async def agregar_permiso_a_usuarios(
    permiso: str,
    usuarios: list[str] = Body(None, description="Lista de nombres de usuario. Si está vacío, se agrega a todos los admins"),
    rol: str = Body(None, description="Rol específico. Si se proporciona, se agrega a todos los usuarios con ese rol")
):
    """
    Agrega un permiso específico a usuarios.
    
    - Si se proporciona lista de usuarios: agrega el permiso solo a esos usuarios
    - Si se proporciona rol: agrega el permiso a todos los usuarios con ese rol
    - Si no se proporciona nada: agrega el permiso a todos los usuarios con rol 'admin'
    """
    if not permiso or not permiso.strip():
        raise HTTPException(status_code=400, detail="El permiso no puede estar vacío")
    
    permiso = permiso.strip()
    resultados = {
        "permiso": permiso,
        "usuarios_actualizados": 0,
        "usuarios_ya_tenian": 0,
        "usuarios_no_encontrados": 0,
        "usuarios_afectados": []
    }
    
    query = {}
    
    if usuarios and len(usuarios) > 0:
        # Agregar a usuarios específicos
        query["usuario"] = {"$in": usuarios}
    elif rol:
        # Agregar a todos los usuarios con un rol específico
        query["rol"] = rol
    else:
        # Por defecto, agregar a todos los admins
        query["rol"] = "admin"
    
    # Actualizar usuarios
    resultado = usuarios_collection.update_many(
        query,
        {"$addToSet": {"permisos": permiso}}
    )
    
    resultados["usuarios_actualizados"] = resultado.modified_count
    resultados["usuarios_ya_tenian"] = resultado.matched_count - resultado.modified_count
    
    # Obtener usuarios afectados para verificación
    usuarios_afectados = list(usuarios_collection.find(
        query,
        {"usuario": 1, "nombreCompleto": 1, "permisos": 1, "rol": 1}
    ))
    
    for usuario in usuarios_afectados:
        resultados["usuarios_afectados"].append({
            "usuario": usuario.get("usuario"),
            "nombreCompleto": usuario.get("nombreCompleto"),
            "rol": usuario.get("rol"),
            "tiene_permiso": permiso in usuario.get("permisos", [])
        })
    
    return resultados