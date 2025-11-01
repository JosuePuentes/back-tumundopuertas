from fastapi import APIRouter, HTTPException, Depends, Body
from ..config.mongodb import (
    clientes_collection, 
    clientes_usuarios_collection,
    carritos_clientes_collection,
    borradores_clientes_collection,
    preferencias_clientes_collection
)
from ..models.authmodels import Cliente
from ..auth.auth import get_current_cliente
from bson import ObjectId
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

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

# ============================================================================
# ENDPOINTS PARA DATOS DEL DASHBOARD DE CLIENTES (Carrito, Borradores, Preferencias)
# ============================================================================

# ----------------------------- CARRITO -----------------------------

@router.get("/{cliente_id}/carrito")
async def get_carrito_cliente(cliente_id: str, cliente: dict = Depends(get_current_cliente)):
    """
    Obtener el carrito de compras guardado del cliente autenticado.
    Solo puede ver su propio carrito.
    """
    try:
        # Verificar que el cliente_id coincida con el cliente autenticado
        if cliente.get("id") != cliente_id:
            raise HTTPException(status_code=403, detail="No puedes ver el carrito de otros clientes")
        
        try:
            obj_id = ObjectId(cliente_id)
        except Exception:
            raise HTTPException(status_code=400, detail="ID de cliente inválido")
        
        # Buscar el documento del carrito
        carrito_doc = carritos_clientes_collection.find_one({"cliente_id": cliente_id})
        
        if not carrito_doc:
            # Si no existe, retornar carrito vacío
            return {"cliente_id": cliente_id, "items": [], "fecha_actualizacion": None}
        
        carrito_doc["_id"] = str(carrito_doc["_id"])
        return carrito_doc
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR GET CARRITO: {str(e)}")
        import traceback
        print(f"ERROR GET CARRITO TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener carrito: {str(e)}")

@router.put("/{cliente_id}/carrito")
async def save_carrito_cliente(
    cliente_id: str, 
    carrito_data: dict = Body(...),
    cliente: dict = Depends(get_current_cliente)
):
    """
    Guardar o actualizar el carrito de compras del cliente autenticado.
    Body debe contener: { "items": [...] }
    Solo puede guardar su propio carrito.
    """
    try:
        # Verificar que el cliente_id coincida con el cliente autenticado
        if cliente.get("id") != cliente_id:
            raise HTTPException(status_code=403, detail="No puedes modificar el carrito de otros clientes")
        
        try:
            obj_id = ObjectId(cliente_id)
        except Exception:
            raise HTTPException(status_code=400, detail="ID de cliente inválido")
        
        # Validar estructura del carrito
        items = carrito_data.get("items", [])
        if not isinstance(items, list):
            raise HTTPException(status_code=400, detail="El campo 'items' debe ser un array")
        
        # Preparar documento del carrito
        carrito_doc = {
            "cliente_id": cliente_id,
            "items": items,
            "fecha_actualizacion": datetime.utcnow().isoformat()
        }
        
        # Usar upsert para crear o actualizar
        result = carritos_clientes_collection.update_one(
            {"cliente_id": cliente_id},
            {"$set": carrito_doc},
            upsert=True
        )
        
        # Retornar el documento actualizado
        carrito_actualizado = carritos_clientes_collection.find_one({"cliente_id": cliente_id})
        carrito_actualizado["_id"] = str(carrito_actualizado["_id"])
        
        return {
            "message": "Carrito guardado correctamente",
            "carrito": carrito_actualizado
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR SAVE CARRITO: {str(e)}")
        import traceback
        print(f"ERROR SAVE CARRITO TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al guardar carrito: {str(e)}")

# ----------------------------- BORRADORES -----------------------------

@router.get("/{cliente_id}/borradores")
async def get_borradores_cliente(cliente_id: str, cliente: dict = Depends(get_current_cliente)):
    """
    Obtener todos los borradores (reclamo, soporte) del cliente autenticado.
    Solo puede ver sus propios borradores.
    """
    try:
        # Verificar que el cliente_id coincida con el cliente autenticado
        if cliente.get("id") != cliente_id:
            raise HTTPException(status_code=403, detail="No puedes ver los borradores de otros clientes")
        
        try:
            obj_id = ObjectId(cliente_id)
        except Exception:
            raise HTTPException(status_code=400, detail="ID de cliente inválido")
        
        # Buscar el documento de borradores
        borradores_doc = borradores_clientes_collection.find_one({"cliente_id": cliente_id})
        
        if not borradores_doc:
            # Si no existe, retornar estructura vacía
            return {
                "cliente_id": cliente_id,
                "borradores": {
                    "reclamo": None,
                    "soporte": None
                },
                "fecha_actualizacion": None
            }
        
        # Asegurar que tenga la estructura correcta con borradores anidado
        if "borradores" not in borradores_doc:
            borradores_doc["borradores"] = {"reclamo": None, "soporte": None}
        
        borradores_doc["_id"] = str(borradores_doc["_id"])
        return borradores_doc
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR GET BORRADORES: {str(e)}")
        import traceback
        print(f"ERROR GET BORRADORES TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener borradores: {str(e)}")

@router.put("/{cliente_id}/borradores/{tipo}")
async def save_borrador_cliente(
    cliente_id: str,
    tipo: str,
    borrador_data: dict = Body(...),
    cliente: dict = Depends(get_current_cliente)
):
    """
    Guardar o actualizar un borrador específico (reclamo o soporte).
    tipo debe ser: "reclamo" o "soporte"
    Body debe contener los datos del borrador.
    Solo puede guardar sus propios borradores.
    """
    try:
        # Verificar que el cliente_id coincida con el cliente autenticado
        if cliente.get("id") != cliente_id:
            raise HTTPException(status_code=403, detail="No puedes modificar los borradores de otros clientes")
        
        # Validar tipo
        if tipo not in ["reclamo", "soporte"]:
            raise HTTPException(status_code=400, detail="El tipo debe ser 'reclamo' o 'soporte'")
        
        try:
            obj_id = ObjectId(cliente_id)
        except Exception:
            raise HTTPException(status_code=400, detail="ID de cliente inválido")
        
        # Preparar actualización del borrador específico
        update_field = {f"borradores.{tipo}": borrador_data}
        update_doc = {
            "cliente_id": cliente_id,
            "fecha_actualizacion": datetime.utcnow().isoformat()
        }
        
        # Actualizar o crear el documento de borradores
        result = borradores_clientes_collection.update_one(
            {"cliente_id": cliente_id},
            {
                "$set": {
                    **update_field,
                    **update_doc
                }
            },
            upsert=True
        )
        
        # Retornar el documento actualizado
        borradores_actualizado = borradores_clientes_collection.find_one({"cliente_id": cliente_id})
        borradores_actualizado["_id"] = str(borradores_actualizado["_id"])
        
        return {
            "message": f"Borrador {tipo} guardado correctamente",
            "borradores": borradores_actualizado
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR SAVE BORRADOR: {str(e)}")
        import traceback
        print(f"ERROR SAVE BORRADOR TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al guardar borrador: {str(e)}")

@router.delete("/{cliente_id}/borradores/{tipo}")
async def delete_borrador_cliente(
    cliente_id: str,
    tipo: str,
    cliente: dict = Depends(get_current_cliente)
):
    """
    Eliminar un borrador específico después de enviarlo.
    tipo debe ser: "reclamo" o "soporte"
    Solo puede eliminar sus propios borradores.
    """
    try:
        # Verificar que el cliente_id coincida con el cliente autenticado
        if cliente.get("id") != cliente_id:
            raise HTTPException(status_code=403, detail="No puedes eliminar los borradores de otros clientes")
        
        # Validar tipo
        if tipo not in ["reclamo", "soporte"]:
            raise HTTPException(status_code=400, detail="El tipo debe ser 'reclamo' o 'soporte'")
        
        try:
            obj_id = ObjectId(cliente_id)
        except Exception:
            raise HTTPException(status_code=400, detail="ID de cliente inválido")
        
        # Eliminar el campo específico del borrador
        result = borradores_clientes_collection.update_one(
            {"cliente_id": cliente_id},
            {
                "$unset": {f"borradores.{tipo}": ""},
                "$set": {"fecha_actualizacion": datetime.utcnow().isoformat()}
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Borrador no encontrado")
        
        return {
            "message": f"Borrador {tipo} eliminado correctamente"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR DELETE BORRADOR: {str(e)}")
        import traceback
        print(f"ERROR DELETE BORRADOR TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al eliminar borrador: {str(e)}")

# ----------------------------- PREFERENCIAS -----------------------------

@router.get("/{cliente_id}/preferencias")
async def get_preferencias_cliente(cliente_id: str, cliente: dict = Depends(get_current_cliente)):
    """
    Obtener las preferencias del cliente autenticado.
    Solo puede ver sus propias preferencias.
    """
    try:
        # Verificar que el cliente_id coincida con el cliente autenticado
        if cliente.get("id") != cliente_id:
            raise HTTPException(status_code=403, detail="No puedes ver las preferencias de otros clientes")
        
        try:
            obj_id = ObjectId(cliente_id)
        except Exception:
            raise HTTPException(status_code=400, detail="ID de cliente inválido")
        
        # Buscar el documento de preferencias
        preferencias_doc = preferencias_clientes_collection.find_one({"cliente_id": cliente_id})
        
        if not preferencias_doc:
            # Si no existe, retornar estructura vacía con valores por defecto
            return {
                "cliente_id": cliente_id,
                "vista_activa": "catalogo",  # Valor por defecto
                "configuraciones": {},
                "fecha_actualizacion": None
            }
        
        preferencias_doc["_id"] = str(preferencias_doc["_id"])
        return preferencias_doc
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR GET PREFERENCIAS: {str(e)}")
        import traceback
        print(f"ERROR GET PREFERENCIAS TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener preferencias: {str(e)}")

@router.put("/{cliente_id}/preferencias")
async def save_preferencias_cliente(
    cliente_id: str,
    preferencias_data: dict = Body(...),
    cliente: dict = Depends(get_current_cliente)
):
    """
    Guardar o actualizar las preferencias del cliente autenticado.
    Body debe contener: { "vista_activa": "...", "configuraciones": {...} }
    Solo puede guardar sus propias preferencias.
    """
    try:
        # Verificar que el cliente_id coincida con el cliente autenticado
        if cliente.get("id") != cliente_id:
            raise HTTPException(status_code=403, detail="No puedes modificar las preferencias de otros clientes")
        
        try:
            obj_id = ObjectId(cliente_id)
        except Exception:
            raise HTTPException(status_code=400, detail="ID de cliente inválido")
        
        # Preparar documento de preferencias
        preferencias_doc = {
            "cliente_id": cliente_id,
            "vista_activa": preferencias_data.get("vista_activa", "catalogo"),
            "configuraciones": preferencias_data.get("configuraciones", {}),
            "fecha_actualizacion": datetime.utcnow().isoformat()
        }
        
        # Usar upsert para crear o actualizar
        result = preferencias_clientes_collection.update_one(
            {"cliente_id": cliente_id},
            {"$set": preferencias_doc},
            upsert=True
        )
        
        # Retornar el documento actualizado
        preferencias_actualizado = preferencias_clientes_collection.find_one({"cliente_id": cliente_id})
        preferencias_actualizado["_id"] = str(preferencias_actualizado["_id"])
        
        return {
            "message": "Preferencias guardadas correctamente",
            "preferencias": preferencias_actualizado
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR SAVE PREFERENCIAS: {str(e)}")
        import traceback
        print(f"ERROR SAVE PREFERENCIAS TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al guardar preferencias: {str(e)}")