from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel
from ..auth.auth import get_current_user

router = APIRouter()

class ConfiguracionFormato(BaseModel):
    nombre_empresa: Optional[str] = None
    logo_url: Optional[str] = None
    rif: Optional[str] = None
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    componentes: List[dict] = []

class FormatoImpresion(BaseModel):
    id: Optional[str] = None
    nombre: str
    tipo: str  # "preliminar" o "nota_entrega"
    configuracion: ConfiguracionFormato
    activo: bool = True

# Endpoints básicos
@router.get("/formatos-impresion")
async def get_formatos(current_user = Depends(get_current_user)):
    # Retornar formatos por defecto o desde base de datos
    return [
        {
            "id": "preliminar_default",
            "nombre": "Preliminar por defecto",
            "tipo": "preliminar",
            "configuracion": {
                "nombre_empresa": "Tu Empresa",
                "rif": "J-12345678-9",
                "direccion": "Tu Dirección",
                "telefono": "0212-1234567",
                "email": "info@tuempresa.com",
                "componentes": []
            },
            "activo": True
        },
        {
            "id": "nota_entrega_default",
            "nombre": "Nota de Entrega por defecto",
            "tipo": "nota_entrega",
            "configuracion": {
                "nombre_empresa": "Tu Empresa",
                "rif": "J-12345678-9",
                "direccion": "Tu Dirección",
                "telefono": "0212-1234567",
                "email": "info@tuempresa.com",
                "componentes": []
            },
            "activo": True
        }
    ]

@router.post("/formatos-impresion")
async def create_formato(formato: FormatoImpresion, current_user = Depends(get_current_user)):
    # Implementar creación de formato
    return {"message": "Formato creado exitosamente", "formato": formato}

@router.put("/formatos-impresion/{formato_id}")
async def update_formato(formato_id: str, formato: FormatoImpresion, current_user = Depends(get_current_user)):
    # Implementar actualización de formato
    return {"message": "Formato actualizado exitosamente", "formato": formato}
