from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from .routes.auth import router as auth_router
from .routes.clientes import router as cliente_router
from .routes.empleados import router as empleado_router
from .routes.pedidos import router as pedido_router
from .routes.inventario import router as inventario_router
from .routes.users import router as usuarios_router
from .routes.files import router as files_router
from .routes.metodos_pago import router as metodos_pago_router
from .routes.formatos_impresion import router as formatos_impresion_router
from .routes.dashboard import router as dashboard_router
from .routes.dashboard import get_dashboard_asignaciones
from .routes.cuentas_por_pagar import router as cuentas_por_pagar_router

from dotenv import load_dotenv
from passlib.context import CryptContext
import os
import traceback

# Cargar variables de entorno
dotenv_path = os.path.join(os.path.dirname(__file__), '../../.env')
load_dotenv(dotenv_path)

# Configuración de cifrado de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Inicializar FastAPI
app = FastAPI(
    title="Crafteo API",
    description="API para el sistema de gestión de Crafteo",
    version="1.0.0"
)

# Middleware para confiar en los encabezados de proxy
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# Middleware para hosts confiables
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

# Habilitar CORS con configuración más robusta
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.tumundopuerta.com",
        "https://tumundopuerta.com",
        "https://crafteo-three.vercel.app",
        "https://crafteo-three-git-main-josuepuentes.vercel.app",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    allow_headers=[
        "Accept",
        "Accept-Language",
        "Content-Language",
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "Origin",
        "Access-Control-Request-Method",
        "Access-Control-Request-Headers",
        "Access-Control-Allow-Origin",
        "Access-Control-Allow-Methods",
        "Access-Control-Allow-Headers",
    ],
    expose_headers=[
        "Access-Control-Allow-Origin",
        "Access-Control-Allow-Methods", 
        "Access-Control-Allow-Headers",
    ],
)

# Middleware para manejo de errores
@app.middleware("http")
async def catch_exceptions_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        print(f"ERROR MIDDLEWARE: {str(e)}")
        print(f"ERROR MIDDLEWARE TRACEBACK: {traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"Error interno del servidor: {str(e)}",
                "error_type": type(e).__name__
            }
        )

# Endpoint de prueba para verificar CORS
@app.get("/health")
async def health_check():
    return {
        "status": "ok", 
        "message": "API funcionando correctamente",
        "cors": "configurado"
    }

# Endpoint de prueba para CORS con PUT
@app.put("/test-cors")
async def test_cors_put():
    return {
        "status": "ok",
        "message": "CORS PUT funcionando correctamente",
        "method": "PUT"
    }

# Endpoint OPTIONS removido - FastAPI maneja automáticamente las solicitudes OPTIONS con CORS

# Endpoint de prueba para métodos de pago
@app.post("/test-metodos-pago")
async def test_metodos_pago():
    return {"message": "Endpoint de prueba funcionando", "status": "ok"}

# Incluir routers segmentados
app.include_router(auth_router, prefix="/auth", tags=["Autenticación"])
app.include_router(cliente_router,prefix="/clientes", tags=["Clientes"])
app.include_router(empleado_router, prefix="/empleados", tags=["Empleados"])
app.include_router(pedido_router, prefix="/pedidos", tags=["Pedidos"])
app.include_router(inventario_router, prefix="/inventario", tags=["Inventario"])
app.include_router(usuarios_router, prefix="/usuarios", tags=["Usuarios"])
app.include_router(files_router, prefix="/files", tags=["Archivos"])
app.include_router(metodos_pago_router, prefix="/metodos-pago", tags=["Metodos de Pago"])
app.include_router(formatos_impresion_router, prefix="/api", tags=["Formatos de Impresión"])
app.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
app.include_router(cuentas_por_pagar_router, prefix="/cuentas-por-pagar", tags=["Cuentas por Pagar"])

# Endpoint directo para /asignaciones (sin prefijo)
@app.get("/asignaciones")
async def asignaciones_directo():
    """Endpoint directo para /asignaciones sin prefijo /dashboard"""
    return await get_dashboard_asignaciones()