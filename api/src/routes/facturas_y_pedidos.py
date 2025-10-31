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
from ..auth.auth import get_current_user

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
    
    Maneja ambos formatos (snake_case y camelCase) para compatibilidad
    """
    if not isinstance(data, dict):
        return data
    
    # Función helper para obtener valor con múltiples posibles nombres
    def get_value(*keys, default=None):
        for key in keys:
            if key in data and data[key] is not None:
                return data[key]
        return default
    
    transformed = {
        "id": str(data.get("_id", "")) if data.get("_id") else None,
        "pedidoId": get_value("pedidoId", "pedido_id", default=""),
        "numeroFactura": get_value("numeroFactura", "numero_factura"),
        "clienteNombre": get_value("clienteNombre", "cliente_nombre"),
        "clienteId": get_value("clienteId", "cliente_id"),
        "fechaFacturacion": get_value("fechaFacturacion", "fecha_facturacion", default=""),
        "fechaCreacion": get_value("fechaCreacion", "fecha_creacion", "createdAt", default=""),
        "items": data.get("items", []),
        "montoTotal": get_value("montoTotal", "monto_total"),
        "estadoGeneral": get_value("estadoGeneral", "estado_general"),
        "datosCompletos": get_value("datosCompletos", "datos_completos", default={})
    }
    
    # Limpiar valores None (excepto items que puede ser lista vacía)
    result = {}
    for k, v in transformed.items():
        if v is not None or k == "items":
            result[k] = v
    
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
        
        # Preparar datos de la factura
        factura_dict = {
            "pedidoId": pedido_id,
            "numeroFactura": request.numeroFactura.strip() if request.numeroFactura else None,
            "cliente_nombre": request.cliente_nombre.strip() if request.cliente_nombre else None,
            "cliente_id": request.cliente_id.strip() if request.cliente_id else None,
            "fecha_facturacion": request.fecha_facturacion or fecha_actual,
            "items": request.items or [],
            "monto_total": float(request.monto_total) if request.monto_total is not None else None,
            "estado_general": request.estado_general.strip() if request.estado_general else None,
            "datos_completos": request.datos_completos or {}
        }
        
        if factura_existente:
            # Actualizar registro existente
            factura_dict["fecha_creacion"] = factura_existente.get("fecha_creacion", fecha_actual)
            
            result = facturas_confirmadas_collection.update_one(
                {"pedidoId": pedido_id},
                {"$set": factura_dict}
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

