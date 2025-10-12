from fastapi import APIRouter, HTTPException, Body, Depends
from bson import ObjectId
from ..config.mongodb import empleados_collection
from ..auth.auth import get_password_hash, get_current_admin_user
from ..models.authmodels import Empleado, EmpleadoCreate, EmpleadoUpdate
import re

router = APIRouter()

def validar_pin(pin: str) -> bool:
    """Validar que el PIN tenga exactamente 4 dígitos"""
    if not pin:
        return False
    return bool(re.match(r'^\d{4}$', pin))

def verificar_pin_unico(pin: str, empleado_id: str = None) -> bool:
    """Verificar que el PIN no esté en uso por otro empleado"""
    query = {"pin": pin}
    if empleado_id:
        query["_id"] = {"$ne": ObjectId(empleado_id)}
    
    empleado_existente = empleados_collection.find_one(query)
    return empleado_existente is None

@router.get("/test")
async def test_empleados_endpoint():
    """Endpoint de prueba para verificar que el router funciona"""
    return {"message": "Router de empleados funcionando correctamente", "status": "ok"}

@router.get("/all/")
async def get_all_empleados():
    empleados = list(empleados_collection.find())
    for empleado in empleados:
        empleado["_id"] = str(empleado["_id"])
    return empleados

@router.post("/crear")
async def create_empleado(empleado: EmpleadoCreate):
    # Validar formato del PIN solo si se proporciona
    if empleado.pin and not validar_pin(empleado.pin):
        raise HTTPException(
            status_code=400, 
            detail="El PIN debe tener exactamente 4 dígitos numéricos"
        )
    
    # Verificar que el PIN sea único solo si se proporciona
    if empleado.pin and not verificar_pin_unico(empleado.pin):
        raise HTTPException(
            status_code=400, 
            detail="El PIN ya está en uso por otro empleado"
        )
    
    # Verificar que el identificador sea único
    existing_user = empleados_collection.find_one({"identificador": empleado.identificador})
    if existing_user:
        raise HTTPException(status_code=400, detail="El usuario ya existe")
    
    result = empleados_collection.insert_one(empleado.dict())
    return {"message": "Empleado creado correctamente", "id": str(result.inserted_id)}

@router.get("/{empleado_id}/")
async def get_empleado(empleado_id: str):
    empleado = empleados_collection.find_one({"_id": empleado_id})
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    return empleado

@router.put("/{empleado_id}/")
@router.put("/{empleado_id}")  # Sin barra al final
async def update_empleado(empleado_id: str, empleado: EmpleadoUpdate):
    # Validar que ningún valor del empleado sea 0 o "0"
    for key, value in empleado.dict(exclude_unset=True).items():
        if value == 0 or value == "0":
            raise HTTPException(status_code=400, detail=f"error o")

    try:
        object_id = ObjectId(empleado_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de empleado inválido")
    
    # Validar PIN si se proporciona
    if empleado.pin is not None:
        if not validar_pin(empleado.pin):
            raise HTTPException(
                status_code=400, 
                detail="El PIN debe tener exactamente 4 dígitos numéricos"
            )
        
        if not verificar_pin_unico(empleado.pin, empleado_id):
            raise HTTPException(
                status_code=400, 
                detail="El PIN ya está en uso por otro empleado"
            )
    
    result = empleados_collection.update_one(
        {"_id": object_id},
        {"$set": empleado.dict(exclude_unset=True)}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    return {"message": "Empleado actualizado correctamente", "id": empleado_id}

@router.get("/verificar-pin/{pin}")
async def verificar_disponibilidad_pin(pin: str):
    """Verificar si un PIN está disponible para uso"""
    if not validar_pin(pin):
        return {
            "disponible": False,
            "mensaje": "El PIN debe tener exactamente 4 dígitos numéricos"
        }
    
    if not verificar_pin_unico(pin):
        return {
            "disponible": False,
            "mensaje": "El PIN ya está en uso por otro empleado"
        }
    
    return {
        "disponible": True,
        "mensaje": "PIN disponible para uso"
    }
