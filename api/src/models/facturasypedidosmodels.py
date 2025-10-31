from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from bson import ObjectId

class FacturaConfirmada(BaseModel):
    """Modelo para facturas confirmadas - Devuelve siempre camelCase
    
    El modelo acepta datos en snake_case desde la BD pero devuelve camelCase.
    Usa aliases para mapear campos automáticamente.
    """
    id: Optional[str] = Field(None, alias="_id")
    pedidoId: str  # Debe ser único
    numeroFactura: Optional[str] = Field(None, alias="numero_factura")
    clienteNombre: Optional[str] = Field(None, alias="cliente_nombre")
    clienteId: Optional[str] = Field(None, alias="cliente_id")
    fechaFacturacion: Optional[str] = Field(None, alias="fecha_facturacion")
    fechaCreacion: Optional[str] = Field(None, alias="fecha_creacion")
    items: Optional[list] = []
    montoTotal: Optional[float] = Field(None, alias="monto_total")
    estadoGeneral: Optional[str] = Field(None, alias="estado_general")
    datosCompletos: Optional[Dict[str, Any]] = Field(None, alias="datos_completos")
    
    class Config:
        populate_by_name = True
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class CrearFacturaConfirmadaRequest(BaseModel):
    """Request para crear/actualizar una factura confirmada
    Acepta tanto camelCase como snake_case para compatibilidad
    """
    pedidoId: str
    numeroFactura: Optional[str] = Field(None, alias="numero_factura")
    clienteNombre: Optional[str] = Field(None, alias="cliente_nombre")
    clienteId: Optional[str] = Field(None, alias="cliente_id")
    fechaFacturacion: Optional[str] = Field(None, alias="fecha_facturacion")
    items: Optional[list] = []
    montoTotal: Optional[float] = Field(None, alias="monto_total")
    estadoGeneral: Optional[str] = Field(None, alias="estado_general")
    datosCompletos: Optional[Dict[str, Any]] = Field(None, alias="datos_completos")
    
    class Config:
        populate_by_name = True
        allow_population_by_field_name = True

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

