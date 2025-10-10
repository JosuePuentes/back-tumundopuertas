from fastapi import APIRouter, HTTPException, Body
from typing import List, Optional
from bson import ObjectId
from ..config.mongodb import db
from ..models.pagosmodels import MetodoPago
from ..models.transaccionmodels import Transaccion
from pydantic import BaseModel

router = APIRouter()
metodos_pago_collection = db["metodos_pago"]
transacciones_collection = db["transacciones"]

def object_id_to_str(data):
    if isinstance(data, dict):
        data_copy = data.copy()
        if "_id" in data_copy:
            data_copy["id"] = str(data_copy["_id"])
            del data_copy["_id"]
        return data_copy
    return data

class MontoRequest(BaseModel):
    monto: float

class DepositoRequest(BaseModel):
    monto: float
    concepto: Optional[str] = None

class TransferenciaRequest(BaseModel):
    monto: float
    concepto: Optional[str] = None

@router.post("/", response_model=MetodoPago)
async def create_metodo_pago(metodo_pago: MetodoPago):
    try:
        # Log de entrada para debug
        print(f"DEBUG: Recibido método de pago: {metodo_pago.dict()}")
        
        # Validaciones básicas más simples
        if not metodo_pago.nombre:
            raise HTTPException(status_code=400, detail="El nombre del método de pago es requerido")
        
        if not metodo_pago.banco:
            raise HTTPException(status_code=400, detail="El banco es requerido")
        
        if not metodo_pago.numero_cuenta:
            raise HTTPException(status_code=400, detail="El número de cuenta es requerido")
        
        if not metodo_pago.titular:
            raise HTTPException(status_code=400, detail="El titular es requerido")
        
        if not metodo_pago.moneda:
            raise HTTPException(status_code=400, detail="La moneda es requerida")
        
        # Preparar datos para inserción de forma más simple
        metodo_pago_dict = {
            "nombre": metodo_pago.nombre.strip(),
            "banco": metodo_pago.banco.strip(),
            "numero_cuenta": metodo_pago.numero_cuenta.strip(),
            "titular": metodo_pago.titular.strip(),
            "cedula": metodo_pago.cedula.strip() if metodo_pago.cedula else None,
            "moneda": metodo_pago.moneda.strip(),
            "saldo": float(metodo_pago.saldo) if metodo_pago.saldo is not None else 0.0
        }
        
        print(f"DEBUG: Datos preparados para inserción: {metodo_pago_dict}")
        
        # Verificar si ya existe un método con el mismo nombre
        existing = metodos_pago_collection.find_one({"nombre": metodo_pago_dict["nombre"]})
        if existing:
            raise HTTPException(status_code=400, detail=f"Ya existe un método de pago con el nombre '{metodo_pago_dict['nombre']}'")
        
        # Insertar en la base de datos
        result = metodos_pago_collection.insert_one(metodo_pago_dict)
        print(f"DEBUG: Resultado de inserción: {result.inserted_id}")
        
        # Obtener el documento creado
        created_metodo = metodos_pago_collection.find_one({"_id": result.inserted_id})
        if not created_metodo:
            raise HTTPException(status_code=500, detail="Error al recuperar el método de pago creado")
        
        print(f"DEBUG: Método creado exitosamente: {created_metodo}")
        return object_id_to_str(created_metodo)
        
    except HTTPException:
        # Re-lanzar HTTPExceptions (errores conocidos)
        raise
    except Exception as e:
        # Log del error para debug
        print(f"ERROR: Error interno al crear método de pago: {str(e)}")
        print(f"ERROR: Tipo de error: {type(e).__name__}")
        import traceback
        print(f"ERROR: Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.post("/simple", include_in_schema=False)
async def create_metodo_pago_simple(request_data: dict):
    """Endpoint simplificado que acepta cualquier JSON para debug"""
    try:
        print(f"DEBUG SIMPLE: Datos recibidos: {request_data}")
        
        # Validaciones básicas
        if not request_data.get("nombre"):
            raise HTTPException(status_code=400, detail="El nombre es requerido")
        
        if not request_data.get("banco"):
            raise HTTPException(status_code=400, detail="El banco es requerido")
        
        if not request_data.get("numero_cuenta"):
            raise HTTPException(status_code=400, detail="El número de cuenta es requerido")
        
        if not request_data.get("titular"):
            raise HTTPException(status_code=400, detail="El titular es requerido")
        
        if not request_data.get("moneda"):
            raise HTTPException(status_code=400, detail="La moneda es requerida")
        
        # Preparar datos
        metodo_pago_dict = {
            "nombre": str(request_data["nombre"]).strip(),
            "banco": str(request_data["banco"]).strip(),
            "numero_cuenta": str(request_data["numero_cuenta"]).strip(),
            "titular": str(request_data["titular"]).strip(),
            "cedula": str(request_data.get("cedula", "")).strip() if request_data.get("cedula") else None,
            "moneda": str(request_data["moneda"]).strip(),
            "saldo": float(request_data.get("saldo", 0))
        }
        
        print(f"DEBUG SIMPLE: Datos preparados: {metodo_pago_dict}")
        
        # Verificar duplicados
        existing = metodos_pago_collection.find_one({"nombre": metodo_pago_dict["nombre"]})
        if existing:
            raise HTTPException(status_code=400, detail=f"Ya existe un método con el nombre '{metodo_pago_dict['nombre']}'")
        
        # Insertar
        result = metodos_pago_collection.insert_one(metodo_pago_dict)
        created_metodo = metodos_pago_collection.find_one({"_id": result.inserted_id})
        
        return object_id_to_str(created_metodo)
        
    except Exception as e:
        print(f"ERROR SIMPLE: {str(e)}")
        import traceback
        print(f"TRACEBACK SIMPLE: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@router.post("", response_model=MetodoPago, include_in_schema=False)
async def create_metodo_pago_no_slash(metodo_pago: MetodoPago):
    """Endpoint alternativo sin barra final para compatibilidad"""
    return await create_metodo_pago(metodo_pago)

@router.post("/debug", include_in_schema=False)
async def debug_create_metodo_pago(metodo_pago: MetodoPago):
    """Endpoint de debug para diagnosticar problemas al crear métodos de pago"""
    try:
        return {
            "received_data": metodo_pago.dict(),
            "validation_checks": {
                "nombre": metodo_pago.nombre if hasattr(metodo_pago, 'nombre') else "MISSING",
                "banco": metodo_pago.banco if hasattr(metodo_pago, 'banco') else "MISSING",
                "numero_cuenta": metodo_pago.numero_cuenta if hasattr(metodo_pago, 'numero_cuenta') else "MISSING",
                "titular": metodo_pago.titular if hasattr(metodo_pago, 'titular') else "MISSING",
                "moneda": metodo_pago.moneda if hasattr(metodo_pago, 'moneda') else "MISSING",
                "saldo": metodo_pago.saldo if hasattr(metodo_pago, 'saldo') else "MISSING",
            },
            "existing_methods": [
                {"nombre": m["nombre"], "_id": str(m["_id"])} 
                for m in metodos_pago_collection.find({}, {"nombre": 1})
            ]
        }
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}

@router.get("/test-db", include_in_schema=False)
async def test_database_connection():
    """Endpoint para probar la conexión a la base de datos"""
    try:
        # Probar conexión básica
        count = metodos_pago_collection.count_documents({})
        return {
            "status": "success",
            "message": "Conexión a la base de datos exitosa",
            "total_methods": count,
            "collection_name": metodos_pago_collection.name
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error de conexión a la base de datos: {str(e)}",
            "error_type": type(e).__name__
        }

@router.get("/", response_model=List[MetodoPago])
async def get_all_metodos_pago():
    metodos = list(metodos_pago_collection.find())
    return [object_id_to_str(metodo) for metodo in metodos]

@router.get("", response_model=List[MetodoPago], include_in_schema=False)
async def get_all_metodos_pago_no_slash():
    metodos = list(metodos_pago_collection.find())
    return [object_id_to_str(metodo) for metodo in metodos]

@router.get("/{id}", response_model=MetodoPago)
async def get_metodo_pago(id: str):
    metodo = metodos_pago_collection.find_one({"_id": ObjectId(id)})
    if metodo:
        return object_id_to_str(metodo)
    raise HTTPException(status_code=404, detail="Método de pago no encontrado")

@router.put("/{id}", response_model=MetodoPago)
async def update_metodo_pago(id: str, metodo_pago: MetodoPago):
    metodo_pago_dict = metodo_pago.dict(by_alias=True, exclude_unset=True)
    if "id" in metodo_pago_dict:
        del metodo_pago_dict["id"]

    updated_metodo = metodos_pago_collection.find_one_and_update(
        {"_id": ObjectId(id)},
        {"$set": metodo_pago_dict},
        return_document=True
    )
    if updated_metodo:
        return object_id_to_str(updated_metodo)
    raise HTTPException(status_code=404, detail="Método de pago no encontrado")

@router.delete("/{id}", response_model=dict)
async def delete_metodo_pago(id: str):
    result = metodos_pago_collection.delete_one({"_id": ObjectId(id)})
    if result.deleted_count == 1:
        return {"message": "Método de pago eliminado correctamente"}
    raise HTTPException(status_code=404, detail="Método de pago no encontrado")

@router.post("/{id}/deposito", response_model=MetodoPago)
async def depositar_dinero(id: str, request: DepositoRequest):
    """Depositar dinero en un método de pago"""
    print(f"DEBUG DEPOSITO: Iniciando depósito para método {id}")
    print(f"DEBUG DEPOSITO: Request: {request.dict()}")
    
    try:
        # Validar ID
        if not id or id == "undefined":
            print(f"DEBUG DEPOSITO: ID inválido: {id}")
            raise HTTPException(status_code=400, detail="ID de método de pago inválido")
        
        # Verificar que el método existe
        metodo = metodos_pago_collection.find_one({"_id": ObjectId(id)})
        if not metodo:
            print(f"DEBUG DEPOSITO: Método no encontrado")
            raise HTTPException(status_code=404, detail="Método de pago no encontrado")
        
        print(f"DEBUG DEPOSITO: Método encontrado: {metodo.get('nombre', 'SIN_NOMBRE')}")
        
        # Incrementar el saldo
        updated_metodo = metodos_pago_collection.find_one_and_update(
            {"_id": ObjectId(id)},
            {"$inc": {"saldo": request.monto}},
            return_document=True
        )
        print(f"DEBUG DEPOSITO: Método actualizado: {updated_metodo is not None}")
        
        if not updated_metodo:
            print(f"DEBUG DEPOSITO: Error al actualizar método")
            raise HTTPException(status_code=500, detail="Error al actualizar método de pago")

        # Registrar la transacción
        transaccion = Transaccion(
            metodo_pago_id=id,
            tipo="deposito",
            monto=request.monto,
            concepto=request.concepto
        )
        transaccion_dict = transaccion.dict(by_alias=True)
        if "id" in transaccion_dict:
            del transaccion_dict["id"]
        
        print(f"DEBUG DEPOSITO: Insertando transacción: {transaccion_dict}")
        transacciones_collection.insert_one(transaccion_dict)
        print(f"DEBUG DEPOSITO: Transacción insertada correctamente")

        result = object_id_to_str(updated_metodo)
        print(f"DEBUG DEPOSITO: Retornando resultado: {result.get('nombre', 'SIN_NOMBRE')}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"DEBUG DEPOSITO: Error inesperado: {e}")
        import traceback
        print(f"DEBUG DEPOSITO: Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al depositar: {str(e)}")

@router.post("/{id}/transferir", response_model=MetodoPago)
async def transferir_dinero(id: str, request: TransferenciaRequest):
    """Transferir dinero desde un método de pago"""
    print(f"DEBUG TRANSFERIR: Iniciando transferencia para método {id}")
    print(f"DEBUG TRANSFERIR: Request: {request.dict()}")
    
    # Validar ID
    if not id or id == "undefined":
        raise HTTPException(status_code=400, detail="ID de método de pago inválido")
    
    # Verificar saldo suficiente
    metodo = metodos_pago_collection.find_one({"_id": ObjectId(id)})
    if not metodo:
        raise HTTPException(status_code=404, detail="Método de pago no encontrado")
    if metodo.get("saldo", 0) < request.monto:
        raise HTTPException(status_code=400, detail="Saldo insuficiente")

    # Disminuir el saldo
    updated_metodo = metodos_pago_collection.find_one_and_update(
        {"_id": ObjectId(id)},
        {"$inc": {"saldo": -request.monto}},
        return_document=True
    )

    # Registrar la transacción
    transaccion = Transaccion(
        metodo_pago_id=id,
        tipo="transferencia",
        monto=request.monto,
        concepto=request.concepto
    )
    transaccion_dict = transaccion.dict(by_alias=True)
    if "id" in transaccion_dict:
        del transaccion_dict["id"]
    transacciones_collection.insert_one(transaccion_dict)

    return object_id_to_str(updated_metodo)

@router.get("/all", response_model=List[MetodoPago])
async def get_all_metodos_pago_all():
    """Endpoint específico para obtener todos los métodos de pago"""
    metodos = list(metodos_pago_collection.find())
    return [object_id_to_str(metodo) for metodo in metodos]

@router.get("/historial-completo", response_model=List[Transaccion])
async def get_historial_completo():
    """Obtener el historial completo de todas las transacciones"""
    transacciones = list(transacciones_collection.find().sort("fecha", -1))
    return [object_id_to_str(t) for t in transacciones]

@router.get("/{id}/historial", response_model=List[Transaccion])
async def get_historial_transacciones(id: str):
    """Obtener el historial completo de transacciones de un método de pago"""
    print(f"DEBUG HISTORIAL: Buscando historial para método {id}")
    try:
        transacciones = list(transacciones_collection.find({"metodo_pago_id": id}).sort("fecha", -1))
        print(f"DEBUG HISTORIAL: Encontradas {len(transacciones)} transacciones")
        result = [object_id_to_str(t) for t in transacciones]
        print(f"DEBUG HISTORIAL: Resultado procesado: {len(result)} elementos")
        return result
    except Exception as e:
        print(f"DEBUG HISTORIAL: Error: {e}")
        import traceback
        print(f"DEBUG HISTORIAL: Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener historial: {str(e)}")