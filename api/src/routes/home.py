from fastapi import APIRouter, HTTPException
from typing import Optional
from ..models.authmodels import HomeConfig, HomeConfigRequest
from ..config.mongodb import home_config_collection
from bson import ObjectId

router = APIRouter()

def get_default_config():
    """
    Retorna una estructura de configuración por defecto con arrays vacíos
    para evitar errores cuando el frontend intenta hacer .filter() en arrays undefined.
    """
    return {
        "banner": {
            "url": None,
            "alt": None,
            "active": True
        },
        "logo": {
            "url": None,
            "alt": None
        },
        "values": {
            "title": None,
            "subtitle": None,
            "values": []
        },
        "products": {
            "title": None,
            "subtitle": None,
            "products": []
        },
        "contact": {
            "phone": None,
            "email": None,
            "address": None,
            "social_media": None
        },
        "colors": {
            "primary": None,
            "secondary": None,
            "accent": None,
            "background": None,
            "text": None
        }
    }

def normalize_config(config_doc):
    """
    Normaliza la configuración para asegurar que todas las propiedades anidadas existan.
    Esto previene errores cuando el frontend intenta acceder a propiedades como .title en objetos undefined.
    """
    default = get_default_config()
    
    # Normalizar banner
    if "banner" not in config_doc or config_doc["banner"] is None:
        config_doc["banner"] = default["banner"]
    elif isinstance(config_doc["banner"], dict):
        for key in ["url", "alt", "active"]:
            if key not in config_doc["banner"]:
                config_doc["banner"][key] = default["banner"][key]
    
    # Normalizar logo
    if "logo" not in config_doc or config_doc["logo"] is None:
        config_doc["logo"] = default["logo"]
    elif isinstance(config_doc["logo"], dict):
        for key in ["url", "alt"]:
            if key not in config_doc["logo"]:
                config_doc["logo"][key] = default["logo"][key]
    
    # Normalizar values
    if "values" not in config_doc or config_doc["values"] is None:
        config_doc["values"] = default["values"]
    elif isinstance(config_doc["values"], dict):
        for key in ["title", "subtitle"]:
            if key not in config_doc["values"]:
                config_doc["values"][key] = default["values"][key]
        if "values" not in config_doc["values"] or config_doc["values"].get("values") is None:
            config_doc["values"]["values"] = []
    
    # Normalizar products
    if "products" not in config_doc or config_doc["products"] is None:
        config_doc["products"] = default["products"]
    elif isinstance(config_doc["products"], dict):
        for key in ["title", "subtitle"]:
            if key not in config_doc["products"]:
                config_doc["products"][key] = default["products"][key]
        if "products" not in config_doc["products"] or config_doc["products"].get("products") is None:
            config_doc["products"]["products"] = []
    
    # Normalizar contact
    if "contact" not in config_doc or config_doc["contact"] is None:
        config_doc["contact"] = default["contact"]
    elif isinstance(config_doc["contact"], dict):
        for key in ["phone", "email", "address", "social_media"]:
            if key not in config_doc["contact"]:
                config_doc["contact"][key] = default["contact"][key]
    
    # Normalizar colors
    if "colors" not in config_doc or config_doc["colors"] is None:
        config_doc["colors"] = default["colors"]
    elif isinstance(config_doc["colors"], dict):
        for key in ["primary", "secondary", "accent", "background", "text"]:
            if key not in config_doc["colors"]:
                config_doc["colors"][key] = default["colors"][key]
    
    return config_doc

@router.get("/config")
async def get_home_config():
    """
    Obtener la configuración de la página de inicio.
    Retorna la configuración completa normalizada o estructura por defecto si no existe.
    """
    try:
        # Buscar el único documento de configuración
        config_doc = home_config_collection.find_one({})
        
        # Si no existe configuración, retornar estructura por defecto
        if not config_doc:
            return {"config": get_default_config()}
        
        # Remover el _id de MongoDB
        if "_id" in config_doc:
            del config_doc["_id"]
        
        # Normalizar la configuración para asegurar que todas las propiedades existan
        config_doc = normalize_config(config_doc)
        
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
        
        # Si no hay configuración, retornar estructura por defecto
        if not updated_config:
            updated_config = get_default_config()
        else:
            # Normalizar la configuración antes de retornarla
            updated_config = normalize_config(updated_config)
        
        return {"config": updated_config, "message": "Configuración guardada exitosamente"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar configuración: {str(e)}")

