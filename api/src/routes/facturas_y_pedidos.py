from fastapi import APIRouter, HTTPException, Body, Depends
from typing import List, Optional
from bson import ObjectId
from datetime import datetime
from ..config.mongodb import db
from ..models.facturasypedidosmodels import (
    FacturaConfirmada,
    CrearFacturaConfirmadaRequest,
    PedidoCargadoInventario,
    CrearPedidoCargadoRequest,
    ActualizarPedidoCargadoRequest
)
from ..auth.auth import get_current_user, get_current_cliente
from ..config.mongodb import pedidos_collection

router = APIRouter()
facturas_confirmadas_collection = db["facturas_confirmadas"]
pedidos_cargados_inventario_collection = db["pedidos_cargados_inventario"]

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

def transform_factura_to_camelcase(data):
    """Transforma una factura de snake_case a camelCase para el frontend
    
    Asegura que TODOS los campos necesarios se devuelvan siempre, 
    incluso si están vacíos o son None.
    Maneja ambos formatos (snake_case y camelCase) para compatibilidad.
    Si los datos no están en el nivel principal, busca en datos_completos como fallback.
    """
    if not isinstance(data, dict):
        return data
    
    # Obtener datos_completos primero para usarlo como fallback
    datos_completos = data.get("datos_completos") or data.get("datosCompletos") or {}
    if not isinstance(datos_completos, dict):
        datos_completos = {}
    
    # Función helper para obtener valor con múltiples posibles nombres
    # Busca primero en data, luego en datos_completos como fallback
    def get_value(*keys, default=None):
        # Primero buscar en el nivel principal
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        # Si no se encuentra, buscar en datos_completos
        for key in keys:
            if key in datos_completos and datos_completos[key] is not None:
                return datos_completos[key]
        return default
    
    # Extraer datos del pedido completo si está disponible
    # Si datos_completos contiene información del pedido, usarla para llenar campos faltantes
    pedido_completo = datos_completos.get("pedido") or datos_completos.get("pedido_completo") or datos_completos
    
    # Obtener nombre del cliente desde múltiples fuentes
    cliente_nombre_final = (
        get_value("clienteNombre", "cliente_nombre") or 
        pedido_completo.get("cliente_nombre") if isinstance(pedido_completo, dict) else None or
        None
    )
    
    # Obtener monto total desde múltiples fuentes
    monto_total_final = get_value("montoTotal", "monto_total")
    if monto_total_final is None and isinstance(pedido_completo, dict):
        monto_total_final = pedido_completo.get("monto_total") or pedido_completo.get("montoTotal")
    
    # Transformar a camelCase - SIEMPRE incluir todos los campos necesarios
    result = {
        "id": str(data.get("_id", "")) if data.get("_id") else None,
        "pedidoId": get_value("pedidoId", "pedido_id", default=""),
        "numeroFactura": get_value("numeroFactura", "numero_factura") or None,
        "clienteNombre": cliente_nombre_final,
        "clienteId": get_value("clienteId", "cliente_id") or None,
        "fechaFacturacion": get_value("fechaFacturacion", "fecha_facturacion", default="") or None,
        "fechaCreacion": get_value("fechaCreacion", "fecha_creacion", "createdAt", default="") or None,
        "items": data.get("items", []) or datos_completos.get("items", []),  # Siempre incluir items
        "montoTotal": float(monto_total_final) if monto_total_final is not None else None,
        "estadoGeneral": get_value("estadoGeneral", "estado_general") or None,
        "datosCompletos": datos_completos
    }
    
    # Asegurar que items siempre sea una lista (nunca None)
    if result["items"] is None:
        result["items"] = []
    
    # Asegurar que datosCompletos siempre sea un objeto (nunca None)
    if result["datosCompletos"] is None:
        result["datosCompletos"] = {}
    
    return result

# ============================================================================
# ENDPOINTS PARA FACTURAS CONFIRMADAS
# ============================================================================

@router.post("/facturas-confirmadas", response_model=FacturaConfirmada)
async def crear_factura_confirmada(
    request: CrearFacturaConfirmadaRequest,
    user: dict = Depends(get_current_user)
):
    """
    Crear o actualizar una factura confirmada.
    
    Si ya existe un registro con el mismo pedidoId, lo actualiza.
    Si no existe, crea uno nuevo.
    
    Validaciones:
    - pedidoId es requerido y único
    """
    try:
        # Validaciones básicas
        if not request.pedidoId or not request.pedidoId.strip():
            raise HTTPException(status_code=400, detail="pedidoId es requerido")
        
        pedido_id = request.pedidoId.strip()
        fecha_actual = datetime.utcnow().isoformat()
        
        # Verificar si ya existe un registro con este pedidoId
        factura_existente = facturas_confirmadas_collection.find_one({"pedidoId": pedido_id})
        
        # Obtener valores del request (acepta camelCase y snake_case)
        numero_factura = request.numeroFactura or None
        cliente_nombre = request.clienteNombre or None
        cliente_id = request.clienteId or None
        fecha_facturacion = request.fechaFacturacion or fecha_actual
        items = request.items or []
        monto_total = request.montoTotal if request.montoTotal is not None else None
        estado_general = request.estadoGeneral or None
        datos_completos = request.datosCompletos or {}
        
        # Si no vienen en el request pero están en datos_completos, extraerlos de ahí
        if not cliente_nombre and datos_completos:
            cliente_nombre = (
                datos_completos.get("cliente_nombre") or 
                datos_completos.get("clienteNombre") or
                (datos_completos.get("pedido") or {}).get("cliente_nombre") if isinstance(datos_completos.get("pedido"), dict) else None
            )
        
        if monto_total is None and datos_completos:
            monto_total = (
                datos_completos.get("monto_total") or 
                datos_completos.get("montoTotal") or
                (datos_completos.get("pedido") or {}).get("monto_total") if isinstance(datos_completos.get("pedido"), dict) else None
            )
        
        if not items and datos_completos:
            items = (
                datos_completos.get("items") or 
                (datos_completos.get("pedido") or {}).get("items") if isinstance(datos_completos.get("pedido"), dict) else []
            )
        
        # Preparar datos de la factura (guardar en snake_case en BD para consistencia)
        factura_dict = {
            "pedidoId": pedido_id,
            "numeroFactura": numero_factura.strip() if numero_factura else None,
            "cliente_nombre": cliente_nombre.strip() if cliente_nombre else None,
            "cliente_id": cliente_id.strip() if cliente_id else None,
            "fecha_facturacion": fecha_facturacion,
            "items": items,
            "monto_total": float(monto_total) if monto_total is not None else None,
            "estado_general": estado_general.strip() if estado_general else None,
            "datos_completos": datos_completos
        }
        
        if factura_existente:
            # Actualizar registro existente - Combinar datos existentes con nuevos datos
            # Si un campo viene en el request, usarlo; si no, preservar el existente
            factura_dict_actualizada = {
                "pedidoId": pedido_id,
                "numeroFactura": numero_factura.strip() if numero_factura else factura_existente.get("numeroFactura"),
                "cliente_nombre": cliente_nombre.strip() if cliente_nombre else factura_existente.get("cliente_nombre"),
                "cliente_id": cliente_id.strip() if cliente_id else factura_existente.get("cliente_id"),
                "fecha_facturacion": fecha_facturacion,
                "items": items if items else factura_existente.get("items", []),
                "monto_total": float(monto_total) if monto_total is not None else factura_existente.get("monto_total"),
                "estado_general": estado_general.strip() if estado_general else factura_existente.get("estado_general"),
                "datos_completos": datos_completos if datos_completos else factura_existente.get("datos_completos", {}),
                "fecha_creacion": factura_existente.get("fecha_creacion", fecha_actual)
            }
            
            result = facturas_confirmadas_collection.update_one(
                {"pedidoId": pedido_id},
                {"$set": factura_dict_actualizada}
            )
            
            if result.modified_count == 0:
                raise HTTPException(status_code=500, detail="Error al actualizar factura confirmada")
            
            factura_actualizada = facturas_confirmadas_collection.find_one({"pedidoId": pedido_id})
            print(f"DEBUG FACTURA: Factura confirmada actualizada para pedidoId: {pedido_id}")
            # Transformar a camelCase para el frontend
            factura_transformed = transform_factura_to_camelcase(factura_actualizada)
            return factura_transformed
        else:
            # Crear nuevo registro
            factura_dict["fecha_creacion"] = fecha_actual
            
            result = facturas_confirmadas_collection.insert_one(factura_dict)
            factura_creada = facturas_confirmadas_collection.find_one({"_id": result.inserted_id})
            
            print(f"DEBUG FACTURA: Nueva factura confirmada creada para pedidoId: {pedido_id}")
            # Transformar a camelCase para el frontend
            factura_transformed = transform_factura_to_camelcase(factura_creada)
            return factura_transformed
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR CREATE FACTURA: {str(e)}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al crear/actualizar factura: {str(e)}")

@router.get("/facturas-confirmadas", response_model=List[FacturaConfirmada])
async def listar_facturas_confirmadas(
    user: dict = Depends(get_current_user)
):
    """
    Listar todas las facturas confirmadas.
    Ordenadas por fecha de creación descendente (más recientes primero).
    """
    try:
        facturas = list(
            facturas_confirmadas_collection.find().sort("fecha_creacion", -1)
        )
        # Transformar todas las facturas a camelCase para el frontend
        return [transform_factura_to_camelcase(factura) for factura in facturas]
    except Exception as e:
        print(f"ERROR GET FACTURAS: {str(e)}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener facturas: {str(e)}")

@router.delete("/facturas-confirmadas/{pedidoId}")
async def eliminar_factura_confirmada(
    pedidoId: str,
    user: dict = Depends(get_current_user)
):
    """
    Eliminar una factura confirmada por su pedidoId.
    """
    try:
        pedido_id = pedidoId.strip()
        
        result = facturas_confirmadas_collection.delete_one({"pedidoId": pedido_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Factura confirmada no encontrada")
        
        return {
            "message": "Factura confirmada eliminada correctamente",
            "pedidoId": pedido_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR DELETE FACTURA: {str(e)}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al eliminar factura: {str(e)}")

# ============================================================================
# ENDPOINTS PARA PEDIDOS CARGADOS AL INVENTARIO
# ============================================================================

@router.post("/pedidos-cargados-inventario", response_model=PedidoCargadoInventario)
async def crear_pedido_cargado_inventario(
    request: CrearPedidoCargadoRequest,
    user: dict = Depends(get_current_user)
):
    """
    Crear o actualizar un pedido cargado al inventario.
    
    Si ya existe un registro con el mismo pedidoId, lo actualiza.
    Si no existe, crea uno nuevo.
    
    Validaciones:
    - pedidoId es requerido y único
    """
    try:
        # Validaciones básicas
        if not request.pedidoId or not request.pedidoId.strip():
            raise HTTPException(status_code=400, detail="pedidoId es requerido")
        
        pedido_id = request.pedidoId.strip()
        fecha_actual = datetime.utcnow().isoformat()
        
        # Verificar si ya existe un registro con este pedidoId
        pedido_existente = pedidos_cargados_inventario_collection.find_one({"pedidoId": pedido_id})
        
        # Preparar datos del pedido cargado
        pedido_dict = {
            "pedidoId": pedido_id,
            "cliente_nombre": request.cliente_nombre.strip() if request.cliente_nombre else None,
            "cliente_id": request.cliente_id.strip() if request.cliente_id else None,
            "fecha_carga": request.fecha_carga or fecha_actual,
            "items": request.items or [],
            "items_actualizados": int(request.items_actualizados) if request.items_actualizados is not None else 0,
            "items_creados": int(request.items_creados) if request.items_creados is not None else 0,
            "datos_completos": request.datos_completos or {}
        }
        
        if pedido_existente:
            # Actualizar registro existente
            pedido_dict["fecha_creacion"] = pedido_existente.get("fecha_creacion", fecha_actual)
            
            result = pedidos_cargados_inventario_collection.update_one(
                {"pedidoId": pedido_id},
                {"$set": pedido_dict}
            )
            
            if result.modified_count == 0:
                raise HTTPException(status_code=500, detail="Error al actualizar pedido cargado")
            
            pedido_actualizado = pedidos_cargados_inventario_collection.find_one({"pedidoId": pedido_id})
            print(f"DEBUG PEDIDO CARGADO: Pedido cargado actualizado para pedidoId: {pedido_id}")
            return object_id_to_str(pedido_actualizado)
        else:
            # Crear nuevo registro
            pedido_dict["fecha_creacion"] = fecha_actual
            
            result = pedidos_cargados_inventario_collection.insert_one(pedido_dict)
            pedido_creado = pedidos_cargados_inventario_collection.find_one({"_id": result.inserted_id})
            
            print(f"DEBUG PEDIDO CARGADO: Nuevo pedido cargado creado para pedidoId: {pedido_id}")
            return object_id_to_str(pedido_creado)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR CREATE PEDIDO CARGADO: {str(e)}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al crear/actualizar pedido cargado: {str(e)}")

@router.get("/pedidos-cargados-inventario", response_model=List[PedidoCargadoInventario])
async def listar_pedidos_cargados_inventario(
    user: dict = Depends(get_current_user)
):
    """
    Listar todos los pedidos cargados al inventario.
    Ordenados por fecha de creación descendente (más recientes primero).
    """
    try:
        pedidos = list(
            pedidos_cargados_inventario_collection.find().sort("fecha_creacion", -1)
        )
        return [object_id_to_str(pedido) for pedido in pedidos]
    except Exception as e:
        print(f"ERROR GET PEDIDOS CARGADOS: {str(e)}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener pedidos cargados: {str(e)}")

@router.patch("/pedidos-cargados-inventario/{pedidoId}", response_model=PedidoCargadoInventario)
async def actualizar_pedido_cargado_inventario(
    pedidoId: str,
    request: ActualizarPedidoCargadoRequest,
    user: dict = Depends(get_current_user)
):
    """
    Actualizar un pedido cargado al inventario por su pedidoId.
    
    Solo actualiza los campos proporcionados en el request.
    """
    try:
        pedido_id = pedidoId.strip()
        
        # Verificar que el pedido existe
        pedido_existente = pedidos_cargados_inventario_collection.find_one({"pedidoId": pedido_id})
        if not pedido_existente:
            raise HTTPException(status_code=404, detail="Pedido cargado no encontrado")
        
        # Preparar datos para actualización (solo los campos proporcionados)
        update_data = {}
        
        if request.cliente_nombre is not None:
            update_data["cliente_nombre"] = request.cliente_nombre.strip() if request.cliente_nombre else None
        
        if request.cliente_id is not None:
            update_data["cliente_id"] = request.cliente_id.strip() if request.cliente_id else None
        
        if request.fecha_carga is not None:
            update_data["fecha_carga"] = request.fecha_carga
        
        if request.items is not None:
            update_data["items"] = request.items
        
        if request.items_actualizados is not None:
            update_data["items_actualizados"] = int(request.items_actualizados)
        
        if request.items_creados is not None:
            update_data["items_creados"] = int(request.items_creados)
        
        if request.datos_completos is not None:
            update_data["datos_completos"] = request.datos_completos
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No hay campos para actualizar")
        
        # Actualizar el registro
        result = pedidos_cargados_inventario_collection.update_one(
            {"pedidoId": pedido_id},
            {"$set": update_data}
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Error al actualizar pedido cargado")
        
        pedido_actualizado = pedidos_cargados_inventario_collection.find_one({"pedidoId": pedido_id})
        print(f"DEBUG PEDIDO CARGADO: Pedido cargado actualizado para pedidoId: {pedido_id}")
        
        return object_id_to_str(pedido_actualizado)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR UPDATE PEDIDO CARGADO: {str(e)}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al actualizar pedido cargado: {str(e)}")

# ============================================================================
# ENDPOINTS PARA CLIENTES AUTENTICADOS - FACTURAS
# ============================================================================

@router.get("/facturas/cliente/{cliente_id}")
async def get_facturas_cliente(cliente_id: str, cliente: dict = Depends(get_current_cliente)):
    """
    Obtener todas las facturas de un cliente autenticado.
    Solo puede ver sus propias facturas.
    Las facturas se obtienen de los pedidos del cliente que tienen facturación.
    """
    try:
        # Verificar que el cliente_id coincida con el cliente autenticado
        if cliente.get("id") != cliente_id:
            raise HTTPException(status_code=403, detail="No puedes ver facturas de otros clientes")
        
        # Buscar facturas confirmadas que tengan el cliente_id en pedidoId o datos_completos
        # Primero obtenemos los pedidos del cliente
        pedidos_cliente = list(pedidos_collection.find({
            "cliente_id": cliente_id,
            "tipo": "cliente"
        }, {"_id": 1}))
        
        pedido_ids = [str(p["_id"]) for p in pedidos_cliente]
        
        # Buscar facturas confirmadas que pertenezcan a estos pedidos
        facturas = list(facturas_confirmadas_collection.find({
            "pedidoId": {"$in": pedido_ids}
        }).sort("fecha_creacion", -1))
        
        # Transformar a camelCase para el frontend
        facturas_transformed = [transform_factura_to_camelcase(factura) for factura in facturas]
        
        return facturas_transformed
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR GET FACTURAS CLIENTE: {str(e)}")
        import traceback
        print(f"ERROR GET FACTURAS CLIENTE TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener facturas: {str(e)}")

@router.get("/facturas/pedido/{pedido_id}")
async def get_factura_por_pedido(pedido_id: str, cliente: dict = Depends(get_current_cliente)):
    """
    Obtener factura de cliente por pedido_id.
    Busca en la colección facturas_cliente.
    Solo puede ver facturas de sus propios pedidos.
    """
    try:
        # Buscar factura por pedido_id
        factura = facturas_cliente_collection.find_one({"pedido_id": pedido_id})
        
        if not factura:
            raise HTTPException(status_code=404, detail="Factura no encontrada para este pedido")
        
        # Verificar que la factura pertenezca al cliente autenticado
        cliente_id = cliente.get("id")
        if factura.get("cliente_id") != cliente_id:
            raise HTTPException(status_code=403, detail="No puedes ver facturas de otros clientes")
        
        # Convertir ObjectId a string
        factura["_id"] = str(factura["_id"])
        
        # Transformar a camelCase para el frontend
        factura_response = {
            "id": factura.get("_id"),
            "pedido_id": factura.get("pedido_id"),
            "numero_factura": factura.get("numero_factura"),
            "cliente_id": factura.get("cliente_id"),
            "cliente_nombre": factura.get("cliente_nombre"),
            "fecha_creacion": factura.get("fecha_creacion"),
            "fecha_facturacion": factura.get("fecha_facturacion"),
            "items": factura.get("items", []),
            "monto_total": float(factura.get("monto_total", 0)),
            "monto_abonado": float(factura.get("monto_abonado", 0)),
            "saldo_pendiente": float(factura.get("saldo_pendiente", 0)),
            "estado": factura.get("estado", "pendiente"),
            "historial_abonos": factura.get("historial_abonos", []),
            "datos_completos": factura.get("datos_completos", {})
        }
        
        return factura_response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR GET FACTURA POR PEDIDO: {str(e)}")
        import traceback
        print(f"ERROR GET FACTURA POR PEDIDO TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener factura: {str(e)}")

