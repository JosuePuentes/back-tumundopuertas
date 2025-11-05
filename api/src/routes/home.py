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
    Retorna la configuración completa o 404 si no existe.
    """
    try:
        # Buscar el único documento de configuración
        config_doc = home_config_collection.find_one({})
        
        if not config_doc:
            raise HTTPException(status_code=404, detail="Configuración no encontrada")
        
        # Remover el _id de MongoDB y retornar solo la configuración
        if "_id" in config_doc:
            del config_doc["_id"]
        
        return {"config": config_doc}
    
    except HTTPException:
        raise
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
        config_dict = request.config.dict(exclude_unset=True, exclude_none=True)
        
        # Buscar si ya existe una configuración
        existing_config = home_config_collection.find_one({})
        
        if existing_config:
            # Actualizar la configuración existente
            result = home_config_collection.update_one(
                {},
                {"$set": config_dict},
                upsert=False
            )
            
            if result.modified_count == 0:
                # Si no se modificó nada, intentar actualizar de todas formas
                home_config_collection.update_one(
                    {},
                    {"$set": config_dict}
                )
        else:
            # Crear nueva configuración
            home_config_collection.insert_one(config_dict)
        
        # Obtener la configuración actualizada para retornar
        updated_config = home_config_collection.find_one({})
        if updated_config and "_id" in updated_config:
            del updated_config["_id"]
        
        return {"config": updated_config, "message": "Configuración guardada exitosamente"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar configuración: {str(e)}")

