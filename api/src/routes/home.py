from fastapi import APIRouter, HTTPException
from typing import Optional
from ..models.authmodels import HomeConfig, HomeConfigRequest
from ..config.mongodb import home_config_collection
from bson import ObjectId

router = APIRouter()

@router.get("/config")
async def get_home_config():
    """
    Obtener la configuración de la página de inicio.
    Retorna la configuración completa o un objeto vacío si no existe.
    """
    try:
        # Buscar el único documento de configuración
        config_doc = home_config_collection.find_one({})
        
        # Si no existe configuración, retornar objeto vacío en lugar de 404
        if not config_doc:
            return {"config": {}}
        
        # Remover el _id de MongoDB y retornar solo la configuración
        if "_id" in config_doc:
            del config_doc["_id"]
        
        return {"config": config_doc}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener configuración: {str(e)}")

@router.put("/config")
async def update_home_config(request: HomeConfigRequest):
    """
    Guardar o actualizar la configuración de la página de inicio.
    Solo debe haber un documento en la colección HOME_CONFIG.
    """
    try:
        # Convertir el modelo a diccionario
        # Usar exclude_none=False para mantener campos None que el frontend pueda querer limpiar
        config_dict = request.config.dict(exclude_unset=False)
        
        # Remover campos None vacíos para mantener la estructura limpia
        # Pero mantener la estructura si el frontend envía valores None explícitos
        config_dict_clean = {}
        for key, value in config_dict.items():
            if value is not None:
                config_dict_clean[key] = value
        
        # Actualizar o crear la configuración (upsert garantiza que solo haya un documento)
        home_config_collection.update_one(
            {},
            {"$set": config_dict_clean},
            upsert=True
        )
        
        # Obtener la configuración actualizada para retornar
        updated_config = home_config_collection.find_one({})
        if updated_config and "_id" in updated_config:
            del updated_config["_id"]
        
        # Si no hay configuración, retornar objeto vacío
        if not updated_config:
            updated_config = {}
        
        return {"config": updated_config, "message": "Configuración guardada exitosamente"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar configuración: {str(e)}")

