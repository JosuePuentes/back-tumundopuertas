"""
Script para agregar el permiso 'cuentas_por_pagar' a usuarios existentes en MongoDB.
Ejecutar desde el directorio raíz del proyecto.

Uso:
    python api/src/scripts/agregar_permiso_cuentas_por_pagar.py
"""
import sys
import os
from pathlib import Path

# Obtener el directorio raíz del proyecto (donde está este script)
script_dir = Path(__file__).resolve().parent
api_dir = script_dir.parent
project_root = api_dir.parent.parent

# Agregar el directorio raíz al path
sys.path.insert(0, str(project_root))

# Cargar variables de entorno
from dotenv import load_dotenv
env_file = project_root / '.env'
if env_file.exists():
    load_dotenv(env_file)

from pymongo import MongoClient

# Obtener MONGO_URI desde variables de entorno
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    print("❌ Error: MONGO_URI no encontrada en las variables de entorno")
    print(f"   Buscando .env en: {env_file}")
    sys.exit(1)

# Conectar a MongoDB
try:
    client = MongoClient(MONGO_URI, tls=True, tlsAllowInvalidCertificates=True)
    db = client["PROCESOS"]
    usuarios_collection = db["USUARIOS"]
    print("✅ Conectado a MongoDB")
except Exception as e:
    print(f"❌ Error conectando a MongoDB: {e}")
    sys.exit(1)

def agregar_permiso_cuentas_por_pagar():
    """
    Agrega el permiso 'cuentas_por_pagar' a usuarios específicos.
    Por defecto agrega a todos los usuarios con rol 'admin'.
    También agrega específicamente al usuario JOHE.
    """
    permiso = "cuentas_por_pagar"
    
    print(f"\n🔧 Agregando permiso '{permiso}' a usuarios...")
    print("-" * 60)
    
    # 1. Agregar a usuario específico JOHE
    resultado_johe = usuarios_collection.update_one(
        {"usuario": "JOHE"},
        {"$addToSet": {"permisos": permiso}}
    )
    
    if resultado_johe.matched_count > 0:
        if resultado_johe.modified_count > 0:
            print(f"✅ Permiso '{permiso}' agregado al usuario JOHE")
        else:
            print(f"ℹ️  Usuario JOHE ya tenía el permiso '{permiso}'")
    else:
        print(f"⚠️  Usuario JOHE no encontrado")
    
    # 2. Agregar a todos los usuarios con rol 'admin'
    resultado_admins = usuarios_collection.update_many(
        {"rol": "admin"},
        {"$addToSet": {"permisos": permiso}}
    )
    
    print(f"\n✅ {resultado_admins.modified_count} usuarios admin actualizados")
    print(f"ℹ️  {resultado_admins.matched_count - resultado_admins.modified_count} usuarios admin ya tenían el permiso")
    
    # 3. Verificar usuarios actualizados
    print("\n📋 Verificando usuarios con el permiso:")
    print("-" * 60)
    
    usuarios_actualizados = list(usuarios_collection.find({
        "permisos": {"$in": [permiso]}
    }, {
        "usuario": 1,
        "permisos": 1,
        "rol": 1,
        "nombreCompleto": 1
    }))
    
    if usuarios_actualizados:
        for usuario in usuarios_actualizados:
            print(f"  ✓ {usuario.get('usuario', 'N/A')} ({usuario.get('nombreCompleto', 'N/A')})")
            print(f"    Rol: {usuario.get('rol', 'N/A')}")
            print(f"    Permisos: {', '.join(usuario.get('permisos', []))}")
            print()
    else:
        print("  ⚠️  No se encontraron usuarios con el permiso")
    
    print(f"✅ Total de usuarios con permiso '{permiso}': {len(usuarios_actualizados)}")
    return usuarios_actualizados

if __name__ == "__main__":
    try:
        usuarios = agregar_permiso_cuentas_por_pagar()
        print("\n✅ Script ejecutado correctamente!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error ejecutando script: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
