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

# Colecciones para datos del dashboard de clientes
carritos_clientes_collection = db["carritos_clientes"]
borradores_clientes_collection = db["borradores_clientes"]
preferencias_clientes_collection = db["preferencias_clientes"]
