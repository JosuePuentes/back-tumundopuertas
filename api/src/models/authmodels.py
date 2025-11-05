from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict
from bson import ObjectId
from datetime import datetime

class ForgotPasswordRequest(BaseModel):
    usuario: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class Client(BaseModel):
    rif: str
    encargado: str
    direccion: str
    telefono: str
    email: str
    password: str
    descripcion: str
    dias_credito: int
    limite_credito: float
    activo: bool = True
    descuento1: float = 0
    descuento2: float = 0
    descuento3: float = 0

class ClientUpdate(BaseModel):
    rif: Optional[str] = None
    encargado: Optional[str] = None
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None # Para cambiarla opcionalmente
    descripcion: Optional[str] = None
    dias_credito: Optional[int] = None
    limite_credito: Optional[float] = None
    activo: Optional[bool] = None
    descuento1: Optional[float] = None
    descuento2: Optional[float] = None
    descuento3: Optional[float] = None



class UserLogin(BaseModel):
    email: str
    password: str

class AdminLogin(BaseModel):
    usuario: str
    password: str
    
class UserAdmin(BaseModel):
    usuario: Optional[str] = None
    password: Optional[str] = None
    permisos: Optional[List[str]] = None
    nombreCompleto: Optional[str] = None
    identificador: Optional[str] = None
    rol: Optional[str] = "admin"
    reset_token: Optional[str] = None
    reset_token_expires: Optional[datetime] = None

class Empleado(BaseModel):
    permisos: List[str] = []
    nombreCompleto: Optional[str] = None
    identificador: Optional[str] = None
    pin: Optional[str] = None  # PIN de 4 dígitos, opcional para empleados existentes

class EmpleadoCreate(BaseModel):
    permisos: List[str] = []
    nombreCompleto: Optional[str] = None
    identificador: Optional[str] = None
    pin: Optional[str] = None  # PIN opcional para nuevos empleados

class EmpleadoUpdate(BaseModel):
    permisos: Optional[List[str]] = None
    nombreCompleto: Optional[str] = None
    identificador: Optional[str] = None
    pin: Optional[str] = None  # PIN opcional para actualizaciones

class Asignacion(BaseModel):
    pedido_id: str
    item_id: str
    empleado_id: Optional[str] = None
    empleado_nombre: Optional[str] = None
    modulo: str  # herreria|masillar|preparar|listo_facturar
    estado: str = "pendiente"  # en_proceso|terminado|pendiente
    fecha_asignacion: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    descripcionitem: str
    detalleitem: Optional[str] = None
    cliente_nombre: str
    costo_produccion: float
    imagenes: List[str] = []

class AsignacionCreate(BaseModel):
    pedido_id: str
    item_id: str
    empleado_id: Optional[str] = None
    empleado_nombre: Optional[str] = None
    modulo: str
    estado: str = "pendiente"
    descripcionitem: str
    detalleitem: Optional[str] = None
    cliente_nombre: str
    costo_produccion: float
    imagenes: List[str] = []

class AsignacionUpdate(BaseModel):
    empleado_id: Optional[str] = None
    empleado_nombre: Optional[str] = None
    estado: Optional[str] = None
    fecha_asignacion: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None

class Comision(BaseModel):
    empleado_id: str
    asignacion_id: str
    pedido_id: Optional[str] = None
    item_id: Optional[str] = None
    costo_produccion: float
    fecha: datetime
    modulo: str
    descripcion: str
    cliente_nombre: Optional[str] = None
    empleado_nombre: Optional[str] = None

class Cliente(BaseModel):
    nombre: str
    rif: str
    direccion: str
    telefono: str

# Modelos para clientes autenticados (usuarios clientes)
class ClienteRegister(BaseModel):
    usuario: str
    password: str
    nombre: str
    cedula: str
    direccion: str
    telefono: str

class ClienteLogin(BaseModel):
    usuario: str
    password: str

class ClienteResponse(BaseModel):
    id: str
    usuario: str
    nombre: str
    cedula: str
    direccion: str
    telefono: str
    rol: str = "cliente"
    fecha_creacion: str
    activo: bool

class ClienteForgotPasswordRequest(BaseModel):
    usuario: str

class ClienteVerifyCodeRequest(BaseModel):
    usuario: str
    codigo: str

class ClienteResetPasswordRequest(BaseModel):
    usuario: str
    codigo: str
    new_password: str

class PedidoItem(BaseModel):
    id: str
    codigo: str
    nombre: str
    descripcion: str
    categoria: str
    precio: float
    costo: float
    costoProduccion: float  # Nuevo campo
    cantidad: int
    activo: bool = True
    detalleitem: Optional[str] = ""
    imagenes: Optional[List[str]] = []
    estado_item: int = 0  # NUEVO: Estado inicial pendiente (0=pendiente, 1=herreria, 2=masillar, 3=preparar, 4=terminado)

class AsignacionArticulo(BaseModel):
    itemId: str
    empleadoId: str
    nombreempleado: str
    fecha_inicio: str
    estado: str
    descripcionitem: str
    costoproduccion: str

class PedidoSeguimiento(BaseModel):
    orden: int
    nombre_subestado: str
    estado: str
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    asignaciones_articulos: Optional[List[AsignacionArticulo]] = None

class RegistroPago(BaseModel):
    fecha: str   # ISO date
    monto: float
    estado: str  # "abonado", "pagado", "sin pago"
    metodo: Optional[str] = None  # ID del método de pago

class Adicional(BaseModel):
    """Modelo para adicionales en pedidos"""
    descripcion: Optional[str] = None
    precio: float
    cantidad: Optional[int] = 1

class Pedido(BaseModel):
    cliente_id: str
    cliente_nombre: str
    fecha_creacion: str
    fecha_actualizacion: str
    estado_general: str
    creado_por: Optional[str] = None
    items: List[PedidoItem]
    seguimiento: List[PedidoSeguimiento]
    pago: Optional[str] = "sin pago"   # "sin pago" | "abonado" | "pagado"
    historial_pagos: Optional[List[RegistroPago]] = []
    total_abonado: float = 0.0
    adicionales: Optional[List[Adicional]] = []  # Campo para adicionales del pedido
    tipo_pedido: Optional[str] = None  # "interno" para /crearpedido, "web" para /clientes
    sucursal: Optional[str] = "sucursal1"  # "sucursal1" o "sucursal2" - determina de qué sucursal se descuenta el inventario
    
    class Config:
        extra = "allow"  # Permitir campos adicionales no definidos en el modelo
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class Company(BaseModel):
    nombre: str
    rif: str
    direccion: str
    telefono: str
    email: str

class Item(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    codigo: Optional[str] = None  # Opcional: si no se proporciona, se genera automáticamente
    nombre: str
    descripcion: str
    departamento: Optional[str] = None
    marca: Optional[str] = None
    categoria: str
    modelo: Optional[str] = None # Keeping remote's new field, making it optional
    precio: float
    costo: float
    costoProduccion: float = 0.0  # Keeping my default value
    cantidad: int
    existencia: int = 0 # Sucursal 1 - New field for stock
    existencia2: int = 0 # Sucursal 2 - Nueva sucursal
    activo: bool = True
    imagenes: Optional[List[str]] = []

    class Config: # Keeping remote's Config class
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class InventarioExcelItem(BaseModel): # Keeping my new model
    codigo: str
    descripcion: str
    departamento: Optional[str] = None
    marca: Optional[str] = None
    precio: float
    costo: float
    existencia: int = 0  # Sucursal 1
    existencia2: Optional[int] = 0  # Sucursal 2 (opcional, puede venir como "Sucursal 2" del Excel)
    
    class Config:
        # Permitir mapeo de nombres alternativos del Excel
        extra = "allow"
        populate_by_name = True

# Modelos para configuración de Home Page
class BannerConfig(BaseModel):
    url: Optional[str] = None
    alt: Optional[str] = None
    active: bool = True

class LogoConfig(BaseModel):
    url: Optional[str] = None
    alt: Optional[str] = None

class ValueConfig(BaseModel):
    title: str
    description: str
    icon: Optional[str] = None

class ValuesConfig(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    values: List[ValueConfig] = []

class ProductItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    image: Optional[str] = None
    price: Optional[float] = None
    link: Optional[str] = None

class ProductsConfig(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None
    products: List[ProductItem] = []

class ContactConfig(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    social_media: Optional[Dict[str, str]] = None

class ColorsConfig(BaseModel):
    primary: Optional[str] = None
    secondary: Optional[str] = None
    accent: Optional[str] = None
    background: Optional[str] = None
    text: Optional[str] = None

class HomeConfig(BaseModel):
    banner: Optional[BannerConfig] = None
    logo: Optional[LogoConfig] = None
    values: Optional[ValuesConfig] = None
    products: Optional[ProductsConfig] = None
    contact: Optional[ContactConfig] = None
    colors: Optional[ColorsConfig] = None

class HomeConfigRequest(BaseModel):
    config: HomeConfig