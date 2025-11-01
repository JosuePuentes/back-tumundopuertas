from pydantic import BaseModel, Field
from typing import Optional, List
from bson import ObjectId
from datetime import datetime

class ProveedorItem(BaseModel):
    codigo: Optional[str] = None
    nombre: str
    cantidad: float
    costo_unitario: float
    subtotal: float

class CuentaPorPagarItem(BaseModel):
    """Item de inventario asociado a una cuenta"""
    item_id: Optional[str] = Field(None, alias="itemId")
    codigo: Optional[str] = None
    nombre: str
    cantidad: float
    costo_unitario: float = Field(..., alias="costoUnitario")
    subtotal: float
    
    class Config:
        extra = "ignore"
        arbitrary_types_allowed = True
        populate_by_name = True

class AbonoCuenta(BaseModel):
    """Abono realizado a una cuenta"""
    fecha: str
    monto: float
    metodo_pago_id: str
    metodo_pago_nombre: Optional[str] = None
    concepto: Optional[str] = None

class CuentaPorPagar(BaseModel):
    """Modelo principal para cuentas por pagar"""
    id: Optional[str] = Field(None, alias="_id")
    proveedor_id: Optional[str] = None
    proveedor_nombre: str
    proveedor_rif: Optional[str] = None
    proveedor_telefono: Optional[str] = None
    proveedor_direccion: Optional[str] = None
    fecha_creacion: str
    fecha_vencimiento: Optional[str] = None
    descripcion: Optional[str] = None
    items: Optional[List[CuentaPorPagarItem]] = []
    monto_total: float
    monto_abonado: float = 0.0  # Monto total abonado (suma de todos los abonos)
    saldo_pendiente: float
    estado: str = "pendiente"  # pendiente, pagada
    historial_abonos: List[AbonoCuenta] = []
    notas: Optional[str] = None
    
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class CrearCuentaPorPagarRequest(BaseModel):
    """Request para crear una nueva cuenta por pagar
    Acepta tanto camelCase (proveedorNombre, montoTotal) como snake_case (proveedor_nombre, monto_total)
    """
    # Campos con alias para aceptar camelCase del frontend
    # Usar Field(..., alias="...") hace que el campo sea requerido pero acepte el alias
    proveedor_id: Optional[str] = Field(default=None, alias="proveedorId")
    proveedor_nombre: str = Field(..., alias="proveedorNombre")  # Requerido - acepta proveedorNombre o proveedor_nombre
    proveedor_rif: Optional[str] = Field(default=None, alias="proveedorRif")
    proveedor_telefono: Optional[str] = Field(default=None, alias="proveedorTelefono")
    proveedor_direccion: Optional[str] = Field(default=None, alias="proveedorDireccion")
    fecha_vencimiento: Optional[str] = Field(default=None, alias="fechaVencimiento")
    descripcion: Optional[str] = None
    items: Optional[List[CuentaPorPagarItem]] = []
    monto_total: float = Field(..., alias="montoTotal")  # Requerido - acepta montoTotal o monto_total
    notas: Optional[str] = None
    
    class Config:
        # Permitir campos adicionales que puedan venir del frontend
        extra = "ignore"
        # Permitir tipos arbitrarios por si acaso
        arbitrary_types_allowed = True
        # Permitir usar tanto alias como nombre de campo
        populate_by_name = True

class AbonarCuentaRequest(BaseModel):
    """Request para abonar a una cuenta"""
    monto: float
    metodo_pago_id: str
    concepto: Optional[str] = None

