"""
Script para migrar pedidos existentes y agregar el campo tipo_pedido.
Identifica pedidos web por:
- Campo "tipo": "cliente"
- Existencia de comprobante_url en historial_pagos
- Existencia de numero_referencia en historial_pagos
- Métodos de pago típicos de pedidos web

Ejecutar desde el directorio raíz del proyecto:
    python api/src/scripts/migrar_tipo_pedido.py
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
    pedidos_collection = db["PEDIDOS"]
    print("✅ Conectado a MongoDB")
except Exception as e:
    print(f"❌ Error conectando a MongoDB: {e}")
    sys.exit(1)

def es_pedido_web(pedido):
    """
    Determina si un pedido es web basándose en características típicas.
    Retorna True si es pedido web, False si es interno.
    """
    # 1. Si ya tiene tipo_pedido definido, usarlo
    tipo_pedido = pedido.get("tipo_pedido")
    if tipo_pedido == "web":
        return True
    if tipo_pedido == "interno":
        return False
    
    # 2. Si tiene campo "tipo": "cliente", es pedido web
    if pedido.get("tipo") == "cliente":
        return True
    
    # 3. Revisar historial_pagos para indicadores de pedidos web
    historial_pagos = pedido.get("historial_pagos", [])
    if isinstance(historial_pagos, list):
        for pago in historial_pagos:
            # Pedidos web suelen tener comprobante_url o numero_referencia
            if isinstance(pago, dict):
                if pago.get("comprobante_url") or pago.get("comprobante"):
                    return True
                if pago.get("numero_referencia"):
                    return True
                # Métodos de pago típicos de web (Zelle, Paypal, Transferencia, etc.)
                metodo = str(pago.get("metodo", "")).lower()
                metodo_nombre = str(pago.get("metodo_pago_nombre", "")).lower()
                if any(term in metodo or term in metodo_nombre for term in ["zelle", "paypal", "transferencia", "pago movil", "pm"]):
                    return True
    
    # 4. Si tiene factura asociada (pedidos web suelen tener factura automática)
    # Esto se puede verificar buscando en facturas_cliente_collection, pero por ahora
    # no lo hacemos para no complicar
    
    # 5. Por defecto, si no tiene indicadores claros de web, es interno
    return False

def migrar_pedidos():
    """
    Migra todos los pedidos existentes agregando el campo tipo_pedido.
    """
    print("\n🔧 Iniciando migración de pedidos...")
    print("-" * 60)
    
    # Obtener todos los pedidos sin tipo_pedido o con tipo_pedido None
    pedidos_sin_tipo = list(pedidos_collection.find({
        "$or": [
            {"tipo_pedido": {"$exists": False}},
            {"tipo_pedido": None}
        ]
    }))
    
    total_pedidos = len(pedidos_sin_tipo)
    print(f"📊 Total de pedidos a migrar: {total_pedidos}")
    
    if total_pedidos == 0:
        print("ℹ️  No hay pedidos que migrar. Todos los pedidos ya tienen tipo_pedido definido.")
        return
    
    # Contadores
    pedidos_web = 0
    pedidos_internos = 0
    errores = 0
    
    # Migrar cada pedido
    for idx, pedido in enumerate(pedidos_sin_tipo, 1):
        try:
            pedido_id = str(pedido["_id"])
            
            # Determinar si es web o interno
            es_web = es_pedido_web(pedido)
            tipo = "web" if es_web else "interno"
            
            # Actualizar el pedido
            resultado = pedidos_collection.update_one(
                {"_id": pedido["_id"]},
                {"$set": {"tipo_pedido": tipo}}
            )
            
            if resultado.modified_count > 0:
                if es_web:
                    pedidos_web += 1
                    print(f"  [{idx}/{total_pedidos}] ✅ Pedido {pedido_id[:8]}... marcado como WEB")
                else:
                    pedidos_internos += 1
                    print(f"  [{idx}/{total_pedidos}] ✅ Pedido {pedido_id[:8]}... marcado como INTERNO")
            else:
                print(f"  [{idx}/{total_pedidos}] ⚠️  Pedido {pedido_id[:8]}... no se pudo actualizar")
                errores += 1
                
        except Exception as e:
            print(f"  [{idx}/{total_pedidos}] ❌ Error migrando pedido {pedido.get('_id', 'N/A')}: {e}")
            errores += 1
    
    # Resumen
    print("\n" + "=" * 60)
    print("📊 RESUMEN DE MIGRACIÓN")
    print("=" * 60)
    print(f"✅ Pedidos marcados como WEB: {pedidos_web}")
    print(f"✅ Pedidos marcados como INTERNO: {pedidos_internos}")
    print(f"❌ Errores: {errores}")
    print(f"📦 Total procesado: {pedidos_web + pedidos_internos + errores} de {total_pedidos}")
    
    # Verificar resultados
    print("\n🔍 Verificando resultados...")
    print("-" * 60)
    
    total_web = pedidos_collection.count_documents({"tipo_pedido": "web"})
    total_interno = pedidos_collection.count_documents({"tipo_pedido": "interno"})
    total_sin_tipo = pedidos_collection.count_documents({
        "$or": [
            {"tipo_pedido": {"$exists": False}},
            {"tipo_pedido": None}
        ]
    })
    total_general = pedidos_collection.count_documents({})
    
    print(f"📊 Total pedidos WEB en BD: {total_web}")
    print(f"📊 Total pedidos INTERNO en BD: {total_interno}")
    print(f"⚠️  Pedidos sin tipo_pedido: {total_sin_tipo}")
    print(f"📦 Total de pedidos: {total_general}")
    
    if total_sin_tipo > 0:
        print(f"\n⚠️  ADVERTENCIA: Aún quedan {total_sin_tipo} pedidos sin tipo_pedido definido.")
        print("   Puede ser necesario ejecutar el script nuevamente o revisar manualmente.")

if __name__ == "__main__":
    try:
        # Confirmación antes de ejecutar
        print("\n" + "=" * 60)
        print("⚠️  MIGRACIÓN DE PEDIDOS - CONFIRMACIÓN")
        print("=" * 60)
        print("Este script actualizará todos los pedidos sin tipo_pedido.")
        print("Los pedidos web se marcarán como 'web' y los internos como 'interno'.")
        respuesta = input("\n¿Deseas continuar? (s/n): ").strip().lower()
        
        if respuesta not in ['s', 'si', 'sí', 'y', 'yes']:
            print("❌ Migración cancelada por el usuario.")
            sys.exit(0)
        
        migrar_pedidos()
        print("\n✅ Script ejecutado correctamente!")
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n\n❌ Script interrumpido por el usuario.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error ejecutando script: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

