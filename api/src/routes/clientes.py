from fastapi import APIRouter, HTTPException, Depends
from ..config.mongodb import clientes_collection, clientes_usuarios_collection
from ..models.authmodels import Cliente
from ..auth.auth import get_current_cliente
from bson import ObjectId
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class ClienteUpdate(BaseModel):
    nombre: Optional[str] = None
    direccion: Optional[str] = None
    telefono: Optional[str] = None

@router.get("/all")
async def get_all_clientes():
    clientes = list(clientes_collection.find())
    for cliente in clientes:
        cliente["_id"] = str(cliente["_id"])
    return clientes

@router.get("/id/{cliente_id}/")
async def get_cliente(cliente_id: str):
    cliente = clientes_collection.find_one({"_id": cliente_id})
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return cliente

@router.post("/")
async def create_cliente(cliente: Cliente):
    try:
        # Preparar datos para inserción
        cliente_dict = cliente.dict(by_alias=True)
        if "id" in cliente_dict:
            del cliente_dict["id"]
        
        # Verificar si ya existe un cliente con el mismo nombre
        existing_client = clientes_collection.find_one({"nombre": cliente.nombre})
        if existing_client:
            raise HTTPException(status_code=400, detail="Ya existe un cliente con este nombre")
        
        result = clientes_collection.insert_one(cliente_dict)
        
        if not result.inserted_id:
            raise HTTPException(status_code=500, detail="Error al crear el cliente")
            
        return {"message": "Cliente creado correctamente", "id": str(result.inserted_id)}
        
    except HTTPException:
        # Re-lanzar HTTPExceptions (errores conocidos)
        raise
    except Exception as e:
        # Capturar cualquier otro error inesperado
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.post("", include_in_schema=False)
async def create_cliente_no_slash(cliente: Cliente):
    """Endpoint alternativo sin barra final para compatibilidad"""
    return await create_cliente(cliente)

@router.put("/id/{cliente_id}/")
async def update_cliente(cliente_id: str, cliente: Cliente):
    # Validación: ningún valor puede ser 0 o "0"
    for key, value in cliente.dict(exclude_unset=True).items():
        if value == 0 or value == "0":
            raise HTTPException(status_code=400, detail=f"error o")
    try:
        obj_id = ObjectId(cliente_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de cliente inválido")
    result = clientes_collection.update_one(
        {"_id": obj_id},
        {"$set": cliente.dict(exclude_unset=True)}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return {"message": "Cliente actualizado correctamente", "id": cliente_id}

# ============================================================================
# ENDPOINTS PARA CLIENTES AUTENTICADOS (perfil)
# ============================================================================

@router.get("/{cliente_id}")
async def get_cliente_perfil(cliente_id: str, cliente: dict = Depends(get_current_cliente)):
    """
    Obtener perfil del cliente autenticado.
    Solo puede ver su propio perfil.
    """
    try:
        # Verificar que el cliente_id coincida con el cliente autenticado
        if cliente.get("id") != cliente_id:
            raise HTTPException(status_code=403, detail="No puedes ver el perfil de otros clientes")
        
        try:
            obj_id = ObjectId(cliente_id)
        except Exception:
            raise HTTPException(status_code=400, detail="ID de cliente inválido")
        
        cliente_doc = clientes_usuarios_collection.find_one({"_id": obj_id})
        if not cliente_doc:
            raise HTTPException(status_code=404, detail="Cliente no encontrado")
        
        # No devolver la contraseña
        cliente_doc["_id"] = str(cliente_doc["_id"])
        cliente_doc.pop("password", None)
        cliente_doc["id"] = cliente_doc.pop("_id")
        
        return cliente_doc
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR GET CLIENTE PERFIL: {str(e)}")
        import traceback
        print(f"ERROR GET CLIENTE PERFIL TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener perfil: {str(e)}")

@router.put("/{cliente_id}")
async def update_cliente_perfil(cliente_id: str, cliente_update: ClienteUpdate, cliente: dict = Depends(get_current_cliente)):
    """
    Actualizar perfil del cliente autenticado.
    Solo puede actualizar su propio perfil.
    """
    try:
        # Verificar que el cliente_id coincida con el cliente autenticado
        if cliente.get("id") != cliente_id:
            raise HTTPException(status_code=403, detail="No puedes actualizar el perfil de otros clientes")
        
        try:
            obj_id = ObjectId(cliente_id)
        except Exception:
            raise HTTPException(status_code=400, detail="ID de cliente inválido")
        
        # Filtrar campos None
        update_data = {k: v for k, v in cliente_update.dict(exclude_unset=True).items() if v is not None}
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No se proporcionaron datos para actualizar")
        
        result = clientes_usuarios_collection.update_one(
            {"_id": obj_id},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Cliente no encontrado")
        
        # Obtener el cliente actualizado
        cliente_actualizado = clientes_usuarios_collection.find_one({"_id": obj_id})
        cliente_actualizado["_id"] = str(cliente_actualizado["_id"])
        cliente_actualizado.pop("password", None)
        cliente_actualizado["id"] = cliente_actualizado.pop("_id")
        
        return cliente_actualizado
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR UPDATE CLIENTE PERFIL: {str(e)}")
        import traceback
        print(f"ERROR UPDATE CLIENTE PERFIL TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al actualizar perfil: {str(e)}")