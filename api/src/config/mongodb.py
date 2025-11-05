from pymongo import MongoClient
from dotenv import load_dotenv
import os
from .config import MONGO_URI
# Cargar variables de entorno
dotenv_path = os.path.join(os.path.dirname(__file__), '../../.env')
load_dotenv(dotenv_path)

# Configuración de conexión a MongoDB
client = MongoClient(MONGO_URI, tls=True, tlsAllowInvalidCertificates=True)
db = client["PROCESOS"]

usuarios_collection = db["USUARIOS"]
clientes_collection = db["CLIENTES"]  # Clientes de negocios (para pedidos)
clientes_usuarios_collection = db["clientes_usuarios"]  # Usuarios clientes autenticados
empleados_collection = db["EMPLEADOS"]
pedidos_collection = db["PEDIDOS"]
items_collection = db["INVENTARIO"]
contadores_collection = db["CONTADORES"]

# Colecciones para datos del dashboard de clientes
carritos_clientes_collection = db["carritos_clientes"]
borradores_clientes_collection = db["borradores_clientes"]
preferencias_clientes_collection = db["preferencias_clientes"]
soporte_reclamos_clientes_collection = db["soporte_reclamos_clientes"]
facturas_cliente_collection = db["facturas_cliente"]
home_config_collection = db["HOME_CONFIG"]

def init_pedidos_indexes():
    """
    Inicializar índices para optimizar queries de pedidos.
    Mejora el rendimiento de búsquedas por estado_general y items.estado_item.
    """
    try:
        # Índice compuesto para estado_general y tipo_pedido
        pedidos_collection.create_index(
            [("estado_general", 1), ("tipo_pedido", 1)],
            name="idx_estado_tipo_pedido"
        )
    except Exception as e:
        if "already exists" in str(e).lower():
            pass  # Índice ya existe
        
    try:
        # Índice para items.estado_item (para filtrar items por estado)
        pedidos_collection.create_index(
            [("items.estado_item", 1)],
            name="idx_items_estado_item"
        )
    except Exception as e:
        if "already exists" in str(e).lower():
            pass  # Índice ya existe
    
    try:
        # Índice para fecha_creacion (para ordenamiento)
        pedidos_collection.create_index(
            [("fecha_creacion", -1)],
            name="idx_fecha_creacion_desc"
        )
    except Exception as e:
        if "already exists" in str(e).lower():
            pass  # Índice ya existe

def init_clientes_indexes():
    """
    Inicializar índices únicos para las colecciones de datos del dashboard de clientes.
    Garantiza un solo documento por cliente_id en cada colección.
    
    Esta función debe ejecutarse al inicio de la aplicación.
    """
    try:
        # Índice único en cliente_id para carritos_clientes
        carritos_clientes_collection.create_index(
            [("cliente_id", 1)],
            unique=True,
            name="idx_carrito_cliente_id_unique"
        )
        print("✅ Índice único creado en carritos_clientes.cliente_id")
    except Exception as e:
        # Si el índice ya existe, ignorar el error
        if "already exists" in str(e).lower() or "duplicate key" in str(e).lower():
            print("ℹ️  Índice único en carritos_clientes.cliente_id ya existe")
        else:
            print(f"⚠️  Error al crear índice en carritos_clientes: {e}")
    
    try:
        # Índice único en cliente_id para borradores_clientes
        borradores_clientes_collection.create_index(
            [("cliente_id", 1)],
            unique=True,
            name="idx_borradores_cliente_id_unique"
        )
        print("✅ Índice único creado en borradores_clientes.cliente_id")
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate key" in str(e).lower():
            print("ℹ️  Índice único en borradores_clientes.cliente_id ya existe")
        else:
            print(f"⚠️  Error al crear índice en borradores_clientes: {e}")
    
    try:
        # Índice único en cliente_id para preferencias_clientes
        preferencias_clientes_collection.create_index(
            [("cliente_id", 1)],
            unique=True,
            name="idx_preferencias_cliente_id_unique"
        )
        print("✅ Índice único creado en preferencias_clientes.cliente_id")
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate key" in str(e).lower():
            print("ℹ️  Índice único en preferencias_clientes.cliente_id ya existe")
        else:
            print(f"⚠️  Error al crear índice en preferencias_clientes: {e}")
