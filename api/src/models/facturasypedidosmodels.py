from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from bson import ObjectId

class FacturaConfirmada(BaseModel):
    """Modelo para facturas confirmadas"""
    id: Optional[str] = Field(None, alias="_id")
    pedidoId: str  # Debe ser único
    numeroFactura: Optional[str] = None
    cliente_nombre: Optional[str] = None
    cliente_id: Optional[str] = None
    fecha_facturacion: str
    fecha_creacion: str
    items: Optional[list] = []
    monto_total: Optional[float] = None
    estado_general: Optional[str] = None
    datos_completos: Optional[Dict[str, Any]] = {}  # Guardar el pedido completo como backup
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class CrearFacturaConfirmadaRequest(BaseModel):
    """Request para crear/actualizar una factura confirmada"""
    pedidoId: str
    numeroFactura: Optional[str] = None
    cliente_nombre: Optional[str] = None
    cliente_id: Optional[str] = None
    fecha_facturacion: Optional[str] = None
    items: Optional[list] = []
    monto_total: Optional[float] = None
    estado_general: Optional[str] = None
    datos_completos: Optional[Dict[str, Any]] = {}

class PedidoCargadoInventario(BaseModel):
    """Modelo para pedidos cargados al inventario"""
    id: Optional[str] = Field(None, alias="_id")
    pedidoId: str  # Debe ser único
    cliente_nombre: Optional[str] = None
    cliente_id: Optional[str] = None
    fecha_carga: str
    fecha_creacion: str
    items: Optional[list] = []
    items_actualizados: Optional[int] = 0
    items_creados: Optional[int] = 0
    datos_completos: Optional[Dict[str, Any]] = {}  # Guardar el pedido completo como backup
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class CrearPedidoCargadoRequest(BaseModel):
    """Request para crear/actualizar un pedido cargado al inventario"""
    pedidoId: str
    cliente_nombre: Optional[str] = None
    cliente_id: Optional[str] = None
    fecha_carga: Optional[str] = None
    items: Optional[list] = []
    items_actualizados: Optional[int] = 0
    items_creados: Optional[int] = 0
    datos_completos: Optional[Dict[str, Any]] = {}

class ActualizarPedidoCargadoRequest(BaseModel):
    """Request para actualizar un pedido cargado"""
    cliente_nombre: Optional[str] = None
    cliente_id: Optional[str] = None
    fecha_carga: Optional[str] = None
    items: Optional[list] = []
    items_actualizados: Optional[int] = None
    items_creados: Optional[int] = None
    datos_completos: Optional[Dict[str, Any]] = None

