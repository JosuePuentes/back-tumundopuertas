"""
Script de prueba para verificar que los endpoints del Panel de Control Logístico estén funcionando
"""
import requests
import sys

BASE_URL = "http://localhost:8002"

endpoints = [
    "/pedidos/panel-control-logistico/resumen/",
    "/pedidos/panel-control-logistico/items-produccion/",
    "/pedidos/panel-control-logistico/movimientos-unidades/",
    "/pedidos/panel-control-logistico/items-sin-movimiento/",
    "/pedidos/panel-control-logistico/items-mas-movidos/",
    "/pedidos/panel-control-logistico/items-existencia-cero/",
    "/pedidos/panel-control-logistico/sugerencia-produccion/",
    "/pedidos/panel-control-logistico/graficas/?periodo=7",
    "/pedidos/panel-control-logistico/planificacion-produccion/",
]

print("=" * 60)
print("Verificación de Endpoints del Panel de Control Logístico")
print("=" * 60)

all_ok = True

for endpoint in endpoints:
    url = f"{BASE_URL}{endpoint}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            print(f"✅ {endpoint} - OK (Status: {response.status_code})")
        else:
            print(f"❌ {endpoint} - ERROR (Status: {response.status_code})")
            print(f"   Response: {response.text[:200]}")
            all_ok = False
    except requests.exceptions.ConnectionError:
        print(f"⚠️  {endpoint} - No se puede conectar al servidor")
        print(f"   Asegúrate de que el servidor esté corriendo en {BASE_URL}")
        all_ok = False
    except Exception as e:
        print(f"❌ {endpoint} - ERROR: {str(e)}")
        all_ok = False

print("=" * 60)
if all_ok:
    print("✅ Todos los endpoints están funcionando correctamente")
    sys.exit(0)
else:
    print("❌ Algunos endpoints tienen problemas")
    print("\nPasos para solucionar:")
    print("1. Verifica que el servidor del backend esté corriendo")
    print("2. Reinicia el servidor del backend para cargar los nuevos endpoints")
    print("3. Verifica los logs del servidor para errores")
    sys.exit(1)



