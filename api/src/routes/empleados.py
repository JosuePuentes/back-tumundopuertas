from fastapi import APIRouter, HTTPException, Body, Depends
from bson import ObjectId
from datetime import datetime
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
    """
    Obtener todos los empleados con caché (TTL: 5 minutos).
    Los empleados cambian poco, por lo que el caché mejora significativamente el rendimiento.
    """
    from ..utils.cache import cache, CACHE_KEY_EMPLEADOS
    
    # Verificar caché primero (TTL de 5 minutos = 300 segundos)
    cached_empleados = cache.get(CACHE_KEY_EMPLEADOS)
    if cached_empleados:
        return cached_empleados
    
    # Proyección optimizada: solo campos necesarios
    projection = {
        "_id": 1,
        "identificador": 1,
        "nombreCompleto": 1,
        "cargo": 1,
        "permisos": 1,
        "pin": 1,
        "activo": 1
    }
    empleados = list(empleados_collection.find({}, projection))
    
    # Mapear cargo a permisos automáticamente
    def mapear_cargo_a_permisos(cargo, nombre_completo):
        permisos = []
        cargo_lower = (cargo or "").lower()
        nombre_lower = (nombre_completo or "").lower()
        
        # Mapear cargos específicos a permisos
        if "herrero" in cargo_lower or "herrero" in nombre_lower:
            permisos.append("herreria")
        if "masillador" in cargo_lower or "masillador" in nombre_lower or "masillar" in cargo_lower:
            permisos.append("masillar")
        if "pintor" in cargo_lower or "pintor" in nombre_lower or "pintar" in cargo_lower:
            permisos.append("pintar")
        if "manillar" in cargo_lower or "manillar" in nombre_lower or "preparador" in cargo_lower:
            permisos.append("manillar")
        if "ayudante" in nombre_lower:
            permisos.append("ayudante")
        if "facturacion" in cargo_lower or "facturar" in cargo_lower:
            permisos.append("facturacion")
        if "envio" in cargo_lower or "envios" in cargo_lower:
            permisos.append("envios")
        if "produccion" in cargo_lower:
            permisos.append("produccion")
        if "mantenimiento" in cargo_lower:
            permisos.append("mantenimiento")
        if "fabricacion" in cargo_lower:
            permisos.append("fabricacion")
        
        return permisos
    
    for empleado in empleados:
        empleado["_id"] = str(empleado["_id"])
        
        # Si no tiene permisos, mapear desde cargo
        if "permisos" not in empleado or not empleado["permisos"]:
            empleado["permisos"] = mapear_cargo_a_permisos(
                empleado.get("cargo"), 
                empleado.get("nombreCompleto")
            )
    
    # Guardar en caché (TTL de 5 minutos = 300 segundos)
    cache.set(CACHE_KEY_EMPLEADOS, empleados, ttl_seconds=300)
    
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

# ========== ENDPOINTS PARA VALES ==========

@router.get("/{empleado_id}/vales")
async def get_vales_empleado(empleado_id: str):
    """
    Obtener todos los vales de un empleado
    """
    try:
        object_id = ObjectId(empleado_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de empleado inválido")
    
    empleado = empleados_collection.find_one({"_id": object_id})
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    # Retornar vales o array vacío si no existen
    vales = empleado.get("vales", [])
    
    # Calcular total de vales pendientes
    total_pendiente = sum(
        vale.get("monto", 0) - vale.get("abonado", 0) 
        for vale in vales 
        if isinstance(vale, dict)
    )
    
    return {
        "empleado_id": empleado_id,
        "nombre_empleado": empleado.get("nombreCompleto", ""),
        "vales": vales,
        "total_pendiente": total_pendiente,
        "cantidad_vales": len(vales)
    }

@router.post("/{empleado_id}/vales")
async def agregar_vale(empleado_id: str, vale_data: dict = Body(...)):
    """
    Agregar un nuevo vale a un empleado
    Body esperado:
    {
        "monto": float,
        "descripcion": str (opcional),
        "fecha": str (opcional, formato ISO),
        "metodo_pago_id": str (opcional pero recomendado)
    }
    """
    try:
        object_id = ObjectId(empleado_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de empleado inválido")
    
    empleado = empleados_collection.find_one({"_id": object_id})
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    # Validar monto
    monto = vale_data.get("monto")
    if not monto or monto <= 0:
        raise HTTPException(status_code=400, detail="El monto debe ser mayor a cero")
    
    # Crear nuevo vale
    nuevo_vale = {
        "monto": float(monto),
        "abonado": 0,
        "pendiente": float(monto),
        "descripcion": vale_data.get("descripcion", ""),
        "fecha": vale_data.get("fecha", datetime.now().isoformat()),
        "fecha_creacion": datetime.now().isoformat(),
        "metodo_pago_id": vale_data.get("metodo_pago_id")  # Guardar método de pago usado
    }
    
    # Inicializar array de vales si no existe
    vales = empleado.get("vales", [])
    vales.append(nuevo_vale)
    
    # Actualizar empleado
    result = empleados_collection.update_one(
        {"_id": object_id},
        {"$set": {"vales": vales}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    return {
        "message": "Vale agregado correctamente",
        "vale": nuevo_vale,
        "total_vales": len(vales)
    }

@router.post("/{empleado_id}/vales/abonar")
async def abonar_vale(empleado_id: str, abono_data: dict = Body(...)):
    """
    Abonar (reducir) un vale específico
    Body esperado:
    {
        "vale_index": int (índice del vale en el array, opcional - si no se envía, se abona al más antiguo pendiente),
        "monto_abono": float,
        "descripcion": str (opcional)
    }
    """
    try:
        object_id = ObjectId(empleado_id)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de empleado inválido")
    
    empleado = empleados_collection.find_one({"_id": object_id})
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    # Validar monto de abono
    monto_abono = abono_data.get("monto_abono")
    if not monto_abono or monto_abono <= 0:
        raise HTTPException(status_code=400, detail="El monto de abono debe ser mayor a cero")
    
    vales = empleado.get("vales", [])
    if not vales:
        raise HTTPException(status_code=400, detail="El empleado no tiene vales registrados")
    
    # Buscar vale a abonar
    vale_index = abono_data.get("vale_index")
    
    if vale_index is not None:
        # Abonar vale específico por índice
        if vale_index < 0 or vale_index >= len(vales):
            raise HTTPException(status_code=400, detail="Índice de vale inválido")
        
        vale = vales[vale_index]
        pendiente_actual = vale.get("monto", 0) - vale.get("abonado", 0)
        
        if monto_abono > pendiente_actual:
            raise HTTPException(
                status_code=400, 
                detail=f"El monto de abono ({monto_abono}) excede el pendiente ({pendiente_actual})"
            )
        
        # Actualizar vale
        nuevo_abonado = vale.get("abonado", 0) + monto_abono
        vales[vale_index] = {
            **vale,
            "abonado": nuevo_abonado,
            "pendiente": vale.get("monto", 0) - nuevo_abonado,
            "ultimo_abono": {
                "monto": monto_abono,
                "fecha": datetime.now().isoformat(),
                "descripcion": abono_data.get("descripcion", "")
            }
        }
    else:
        # Abonar el vale más antiguo que tenga pendiente
        vale_encontrado = False
        for idx, vale in enumerate(vales):
            pendiente_actual = vale.get("monto", 0) - vale.get("abonado", 0)
            if pendiente_actual > 0:
                if monto_abono > pendiente_actual:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"El monto de abono ({monto_abono}) excede el pendiente del vale ({pendiente_actual})"
                    )
                
                # Actualizar vale
                nuevo_abonado = vale.get("abonado", 0) + monto_abono
                vales[idx] = {
                    **vale,
                    "abonado": nuevo_abonado,
                    "pendiente": vale.get("monto", 0) - nuevo_abonado,
                    "ultimo_abono": {
                        "monto": monto_abono,
                        "fecha": datetime.now().isoformat(),
                        "descripcion": abono_data.get("descripcion", "")
                    }
                }
                vale_index = idx
                vale_encontrado = True
                break
        
        if not vale_encontrado:
            raise HTTPException(status_code=400, detail="No hay vales pendientes para abonar")
    
    # Actualizar empleado
    result = empleados_collection.update_one(
        {"_id": object_id},
        {"$set": {"vales": vales}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    return {
        "message": "Abono aplicado correctamente",
        "vale_index": vale_index,
        "vale_actualizado": vales[vale_index],
        "monto_abonado": monto_abono
    }
