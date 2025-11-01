from fastapi import APIRouter, HTTPException, Body, Depends, Request
from typing import List, Optional
from bson import ObjectId
from datetime import datetime
from ..config.mongodb import db
from ..models.cuentasporpagarmodels import (
    CuentaPorPagar,
    CrearCuentaPorPagarRequest,
    AbonarCuentaRequest,
    AbonoCuenta
)
from ..auth.auth import get_current_user
from ..config.mongodb import items_collection

router = APIRouter()
cuentas_por_pagar_collection = db["cuentas_por_pagar"]
metodos_pago_collection = db["metodos_pago"]
transacciones_collection = db["transacciones"]

def object_id_to_str(data):
    """Convierte ObjectId a string en documentos"""
    if isinstance(data, dict):
        data_copy = data.copy()
        if "_id" in data_copy:
            data_copy["id"] = str(data_copy["_id"])
            del data_copy["_id"]
        return data_copy
    elif isinstance(data, list):
        return [object_id_to_str(item) for item in data]
    return data

@router.get("/", response_model=List[CuentaPorPagar])
async def get_all_cuentas_por_pagar(
    estado: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Obtener todas las cuentas por pagar.
    Opcionalmente filtrar por estado: 'pendiente' o 'pagada'
    """
    try:
        query = {}
        if estado:
            if estado not in ["pendiente", "pagada"]:
                raise HTTPException(status_code=400, detail="Estado debe ser 'pendiente' o 'pagada'")
            query["estado"] = estado
        
        cuentas = list(cuentas_por_pagar_collection.find(query).sort("fecha_creacion", -1))
        return [object_id_to_str(cuenta) for cuenta in cuentas]
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR GET ALL CUENTAS: {str(e)}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener cuentas: {str(e)}")

@router.get("/{cuenta_id}", response_model=CuentaPorPagar)
async def get_cuenta_por_pagar(
    cuenta_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obtener una cuenta por pagar específica por su ID
    """
    try:
        cuenta_obj_id = ObjectId(cuenta_id)
        cuenta = cuentas_por_pagar_collection.find_one({"_id": cuenta_obj_id})
        
        if not cuenta:
            raise HTTPException(status_code=404, detail="Cuenta por pagar no encontrada")
        
        return object_id_to_str(cuenta)
    except HTTPException:
        raise
    except Exception as e:
        if "not a valid ObjectId" in str(e):
            raise HTTPException(status_code=400, detail="ID de cuenta inválido")
        print(f"ERROR GET CUENTA: {str(e)}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener cuenta: {str(e)}")

@router.post("/", response_model=CuentaPorPagar)
async def create_cuenta_por_pagar(
    request_body: dict = Body(...),
    user: dict = Depends(get_current_user)
):
    """
    Crear una nueva cuenta por pagar.
    
    Si la cuenta tiene items del inventario:
    - Actualiza la cantidad en el inventario (resta) para cada item
    
    Validaciones:
    - monto_total debe ser mayor a 0
    - Si hay items, el monto_total debe coincidir con la suma de subtotales
    - Proveedor_nombre es requerido
    
    Acepta dos formatos:
    1. Formato plano: { "proveedorNombre": "...", "montoTotal": ..., "items": [...] }
    2. Formato anidado: { "proveedor": { "nombre": "...", "rif": "...", ... }, "total": ..., "items": [...] }
    """
    try:
        print(f"DEBUG CREATE CUENTA: Body recibido: {request_body}")
        
        # Normalizar el request body a la estructura esperada
        normalized_data = {}
        
        # Manejar proveedor (puede venir como objeto anidado o campos planos)
        if "proveedor" in request_body and isinstance(request_body["proveedor"], dict):
            # Formato anidado: { "proveedor": { "nombre": "...", ... } }
            proveedor = request_body["proveedor"]
            normalized_data["proveedorNombre"] = proveedor.get("nombre") or proveedor.get("nombreCompleto") or ""
            normalized_data["proveedorRif"] = proveedor.get("rif")
            normalized_data["proveedorTelefono"] = proveedor.get("telefono")
            normalized_data["proveedorDireccion"] = proveedor.get("direccion")
            normalized_data["proveedorId"] = proveedor.get("id") or proveedor.get("_id")
        else:
            # Formato plano: campos directos
            normalized_data["proveedorNombre"] = request_body.get("proveedorNombre") or request_body.get("proveedor_nombre") or ""
            normalized_data["proveedorRif"] = request_body.get("proveedorRif") or request_body.get("proveedor_rif")
            normalized_data["proveedorTelefono"] = request_body.get("proveedorTelefono") or request_body.get("proveedor_telefono")
            normalized_data["proveedorDireccion"] = request_body.get("proveedorDireccion") or request_body.get("proveedor_direccion")
            normalized_data["proveedorId"] = request_body.get("proveedorId") or request_body.get("proveedor_id")
        
        # Manejar montoTotal (puede venir como "total" o "montoTotal")
        normalized_data["montoTotal"] = (
            request_body.get("montoTotal") or 
            request_body.get("monto_total") or 
            request_body.get("total") or 
            0
        )
        
        # Manejar items (normalizar estructura)
        items_raw = request_body.get("items", [])
        normalized_items = []
        for item in items_raw:
            normalized_item = {
                "itemId": item.get("itemId") or item.get("item_id") or item.get("_id"),
                "codigo": item.get("codigo"),
                "nombre": item.get("nombre") or item.get("descripcion", ""),
                "cantidad": float(item.get("cantidad", 0)),
                # costoUnitario puede venir como "costo" o "costoUnitario"
                "costoUnitario": float(item.get("costoUnitario") or item.get("costo_unitario") or item.get("costo", 0)),
                # subtotal se calcula si no viene
                "subtotal": float(item.get("subtotal") or (float(item.get("cantidad", 0)) * float(item.get("costoUnitario") or item.get("costo") or item.get("costo_unitario") or 0)))
            }
            normalized_items.append(normalized_item)
        
        normalized_data["items"] = normalized_items
        
        # Otros campos
        normalized_data["fechaVencimiento"] = request_body.get("fechaVencimiento") or request_body.get("fecha_vencimiento")
        normalized_data["descripcion"] = request_body.get("descripcion")
        normalized_data["notas"] = request_body.get("notas")
        
        print(f"DEBUG CREATE CUENTA: Datos normalizados: {normalized_data}")
        
        # Crear el objeto de request con los datos normalizados
        request = CrearCuentaPorPagarRequest(**normalized_data)
        
        # Log de debug para ver qué datos se están recibiendo
        print(f"DEBUG CREATE CUENTA: Request parseado:")
        print(f"  - proveedor_nombre: {request.proveedor_nombre}")
        print(f"  - proveedor_id: {request.proveedor_id}")
        print(f"  - monto_total: {request.monto_total}")
        print(f"  - items count: {len(request.items) if request.items else 0}")
        print(f"  - fecha_vencimiento: {request.fecha_vencimiento}")
        print(f"  - descripcion: {request.descripcion}")
        # Validaciones básicas
        if not request.proveedor_nombre or not request.proveedor_nombre.strip():
            raise HTTPException(status_code=400, detail="El nombre del proveedor es requerido")
        
        if request.monto_total <= 0:
            raise HTTPException(status_code=400, detail="El monto total debe ser mayor a 0")
        
        # Validar que si hay items, el monto total coincida con la suma
        if request.items and len(request.items) > 0:
            suma_subtotales = sum(item.subtotal for item in request.items)
            if abs(suma_subtotales - request.monto_total) > 0.01:  # Tolerancia para floats
                raise HTTPException(
                    status_code=400, 
                    detail=f"El monto total ({request.monto_total}) no coincide con la suma de subtotales ({suma_subtotales})"
                )
        
        # Preparar datos de la cuenta
        fecha_creacion = datetime.utcnow().isoformat()
        
        cuenta_dict = {
            "proveedor_id": request.proveedor_id,
            "proveedor_nombre": request.proveedor_nombre.strip(),
            "proveedor_rif": request.proveedor_rif.strip() if request.proveedor_rif else None,
            "proveedor_telefono": request.proveedor_telefono.strip() if request.proveedor_telefono else None,
            "proveedor_direccion": request.proveedor_direccion.strip() if request.proveedor_direccion else None,
            "fecha_creacion": fecha_creacion,
            "fecha_vencimiento": request.fecha_vencimiento,
            "descripcion": request.descripcion.strip() if request.descripcion else None,
            "items": [item.dict() for item in (request.items or [])],
            "monto_total": float(request.monto_total),
            "saldo_pendiente": float(request.monto_total),
            "estado": "pendiente",
            "historial_abonos": [],
            "notas": request.notas.strip() if request.notas else None
        }
        
        # Validar que los campos requeridos no estén vacíos antes de guardar
        if not cuenta_dict["proveedor_nombre"]:
            raise HTTPException(status_code=400, detail="El nombre del proveedor es requerido")
        
        # Insertar la cuenta
        result = cuentas_por_pagar_collection.insert_one(cuenta_dict)
        cuenta_creada = cuentas_por_pagar_collection.find_one({"_id": result.inserted_id})
        
        print(f"DEBUG CREAR CUENTA: Cuenta creada en BD:")
        print(f"  - _id: {cuenta_creada.get('_id')}")
        print(f"  - proveedor_nombre: '{cuenta_creada.get('proveedor_nombre')}'")
        print(f"  - proveedor_rif: '{cuenta_creada.get('proveedor_rif')}'")
        print(f"  - monto_total: {cuenta_creada.get('monto_total')}")
        print(f"  - saldo_pendiente: {cuenta_creada.get('saldo_pendiente')}")
        print(f"  - estado: '{cuenta_creada.get('estado')}'")
        print(f"  - items count: {len(cuenta_creada.get('items', []))}")
        
        # Si hay items del inventario, actualizar las cantidades
        if request.items and len(request.items) > 0:
            print(f"DEBUG CREAR CUENTA: Actualizando inventario para {len(request.items)} items")
            for item in request.items:
                if item.item_id or item.codigo:
                    try:
                        # Buscar el item en inventario
                        item_inventario = None
                        if item.item_id:
                            try:
                                item_inventario = items_collection.find_one({"_id": ObjectId(item.item_id)})
                            except:
                                pass
                        
                        if not item_inventario and item.codigo:
                            item_inventario = items_collection.find_one({"codigo": item.codigo.strip()})
                        
                        if item_inventario:
                            cantidad_a_restar = float(item.cantidad)
                            cantidad_actual = float(item_inventario.get("cantidad", 0))
                            
                            if cantidad_actual >= cantidad_a_restar:
                                nueva_cantidad = cantidad_actual - cantidad_a_restar
                                items_collection.update_one(
                                    {"_id": item_inventario["_id"]},
                                    {"$set": {"cantidad": nueva_cantidad}}
                                )
                                print(f"DEBUG CREAR CUENTA: Item {item_inventario.get('codigo', 'N/A')} actualizado: {cantidad_actual} -> {nueva_cantidad}")
                            else:
                                print(f"WARNING CREAR CUENTA: Item {item_inventario.get('codigo', 'N/A')} tiene cantidad insuficiente ({cantidad_actual} < {cantidad_a_restar})")
                        else:
                            print(f"WARNING CREAR CUENTA: Item no encontrado en inventario - codigo: {item.codigo}, item_id: {item.item_id}")
                    except Exception as e:
                        print(f"ERROR CREAR CUENTA: Error al actualizar item {item.codigo}: {str(e)}")
                        # No interrumpimos el flujo, solo logueamos el error
        
        # Convertir a formato de respuesta asegurando que todos los campos estén presentes
        cuenta_response = object_id_to_str(cuenta_creada)
        
        # Asegurar que los campos requeridos tengan valores por defecto si están None o vacíos
        if not cuenta_response.get("proveedor_nombre") or cuenta_response.get("proveedor_nombre") == "":
            cuenta_response["proveedor_nombre"] = "Sin nombre"
        if not cuenta_response.get("proveedor_rif"):
            cuenta_response["proveedor_rif"] = None
        if cuenta_response.get("monto_total") is None:
            cuenta_response["monto_total"] = 0.0
        if cuenta_response.get("saldo_pendiente") is None:
            cuenta_response["saldo_pendiente"] = cuenta_response.get("monto_total", 0.0)
        if not cuenta_response.get("estado"):
            cuenta_response["estado"] = "pendiente"
        if not cuenta_response.get("historial_abonos"):
            cuenta_response["historial_abonos"] = []
        if not cuenta_response.get("items"):
            cuenta_response["items"] = []
        
        print(f"DEBUG CREAR CUENTA: Respuesta final:")
        print(f"  {cuenta_response}")
        
        # Crear instancia del modelo para validación
        try:
            cuenta_validada = CuentaPorPagar(**cuenta_response)
            return cuenta_validada.dict(by_alias=True)
        except Exception as e:
            print(f"ERROR CREAR CUENTA: Error al validar modelo: {str(e)}")
            # Si falla la validación, retornar el diccionario directamente
            return cuenta_response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR CREATE CUENTA: {str(e)}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al crear cuenta: {str(e)}")

@router.post("/{cuenta_id}/abonar", response_model=CuentaPorPagar)
async def abonar_cuenta_por_pagar(
    cuenta_id: str,
    request: AbonarCuentaRequest,
    user: dict = Depends(get_current_user)
):
    """
    Registrar un abono a una cuenta por pagar.
    
    Operaciones realizadas:
    1. Valida que la cuenta exista y esté pendiente
    2. Valida que el monto no exceda el saldo pendiente
    3. Valida que el método de pago tenga saldo suficiente
    4. Resta el monto del saldo del método de pago
    5. Registra la transacción en el historial del método de pago
    6. Actualiza el saldo_pendiente de la cuenta
    7. Agrega el abono al historial_abonos
    8. Cambia el estado a "pagada" si saldo_pendiente === 0
    """
    try:
        # Validar ID de cuenta
        try:
            cuenta_obj_id = ObjectId(cuenta_id)
        except:
            raise HTTPException(status_code=400, detail="ID de cuenta inválido")
        
        # Obtener la cuenta
        cuenta = cuentas_por_pagar_collection.find_one({"_id": cuenta_obj_id})
        if not cuenta:
            raise HTTPException(status_code=404, detail="Cuenta por pagar no encontrada")
        
        if cuenta.get("estado") == "pagada":
            raise HTTPException(status_code=400, detail="La cuenta ya está completamente pagada")
        
        # Validar monto
        if request.monto <= 0:
            raise HTTPException(status_code=400, detail="El monto del abono debe ser mayor a 0")
        
        saldo_pendiente = float(cuenta.get("saldo_pendiente", 0))
        if request.monto > saldo_pendiente:
            raise HTTPException(
                status_code=400, 
                detail=f"El monto del abono ({request.monto}) excede el saldo pendiente ({saldo_pendiente})"
            )
        
        # Validar y actualizar método de pago
        try:
            metodo_pago_obj_id = ObjectId(request.metodo_pago_id)
        except:
            raise HTTPException(status_code=400, detail="ID de método de pago inválido")
        
        metodo_pago = metodos_pago_collection.find_one({"_id": metodo_pago_obj_id})
        if not metodo_pago:
            raise HTTPException(status_code=404, detail="Método de pago no encontrado")
        
        saldo_metodo = float(metodo_pago.get("saldo", 0))
        if saldo_metodo < request.monto:
            raise HTTPException(
                status_code=400,
                detail=f"Saldo insuficiente en el método de pago. Saldo disponible: {saldo_metodo}, Monto requerido: {request.monto}"
            )
        
        # Restar del saldo del método de pago
        nuevo_saldo_metodo = saldo_metodo - request.monto
        metodos_pago_collection.update_one(
            {"_id": metodo_pago_obj_id},
            {"$set": {"saldo": nuevo_saldo_metodo}}
        )
        print(f"DEBUG ABONAR: Método de pago '{metodo_pago.get('nombre', 'N/A')}' actualizado: {saldo_metodo} -> {nuevo_saldo_metodo}")
        
        # Registrar transacción en el historial del método de pago
        transaccion = {
            "metodo_pago_id": str(metodo_pago_obj_id),
            "tipo": "pago_cuenta_por_pagar",
            "monto": -request.monto,  # Negativo porque es un egreso
            "concepto": request.concepto or f"Abono a cuenta por pagar - Proveedor: {cuenta.get('proveedor_nombre', 'N/A')}",
            "cuenta_por_pagar_id": str(cuenta_obj_id),
            "fecha": datetime.utcnow().isoformat()
        }
        transacciones_collection.insert_one(transaccion)
        print(f"DEBUG ABONAR: Transacción registrada en historial del método de pago")
        
        # Calcular nuevo saldo pendiente
        nuevo_saldo_pendiente = saldo_pendiente - request.monto
        
        # Crear registro de abono
        abono = {
            "fecha": datetime.utcnow().isoformat(),
            "monto": float(request.monto),
            "metodo_pago_id": str(metodo_pago_obj_id),
            "metodo_pago_nombre": metodo_pago.get("nombre", "N/A"),
            "concepto": request.concepto
        }
        
        # Actualizar la cuenta
        update_data = {
            "$inc": {"saldo_pendiente": -request.monto},
            "$push": {"historial_abonos": abono}
        }
        
        # Si el saldo pendiente queda en 0, cambiar estado a "pagada"
        if nuevo_saldo_pendiente <= 0.01:  # Tolerancia para floats
            update_data["$set"] = {"estado": "pagada"}
            print(f"DEBUG ABONAR: Cuenta completamente pagada, cambiando estado")
        
        cuenta_actualizada = cuentas_por_pagar_collection.find_one_and_update(
            {"_id": cuenta_obj_id},
            update_data,
            return_document=True
        )
        
        if not cuenta_actualizada:
            raise HTTPException(status_code=500, detail="Error al actualizar la cuenta")
        
        print(f"DEBUG ABONAR: Cuenta actualizada exitosamente. Nuevo saldo pendiente: {cuenta_actualizada.get('saldo_pendiente', 0)}")
        
        return object_id_to_str(cuenta_actualizada)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR ABONAR CUENTA: {str(e)}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al registrar abono: {str(e)}")

