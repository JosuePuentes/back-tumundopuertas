from fastapi import APIRouter, HTTPException
from typing import Optional
from ..models.authmodels import HomeConfig, HomeConfigRequest
from ..config.mongodb import home_config_collection
from bson import ObjectId
import os

router = APIRouter()

# Control de logs: solo mostrar en desarrollo
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"
def debug_log(*args, **kwargs):
    """Función para logs de debug - solo muestra en modo DEBUG"""
    if DEBUG_MODE:
        print(*args, **kwargs)

def get_default_config():
    """
    Retorna una estructura de configuración por defecto con arrays vacíos
    para evitar errores cuando el frontend intenta hacer .filter() en arrays undefined.
    """
    return {
        "banner": {
            "url": None,
            "alt": None,
            "active": True,
            "width": "100%",
            "height": "400px"
        },
        "logo": {
            "url": None,
            "alt": None,
            "width": "200px",
            "height": "auto"
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
        },
        "nosotros": {
            "historia": None,
            "mision": None,
            "vision": None,
            "enabled": True,
            "titleFontSize": None,
            "titleFontFamily": None,
            "titleFontWeight": None,
            "textFontSize": None,
            "textFontFamily": None,
            "textFontWeight": None
        },
        "servicios": {
            "items": [],
            "enabled": True,
            "titleFontSize": None,
            "titleFontFamily": None,
            "titleFontWeight": None,
            "textFontSize": None,
            "textFontFamily": None,
            "textFontWeight": None
        },
        "typography": {
            "defaultFontFamily": None,
            "defaultFontSize": None,
            "headingFontFamily": None,
            "headingFontSize": None,
            "headingFontWeight": None
        }
    }

def normalize_config(config_doc):
    """
    Normaliza la configuración para asegurar que todas las propiedades anidadas existan.
    Esto previene errores cuando el frontend intenta acceder a propiedades como .title en objetos undefined.
    IMPORTANTE: Siempre reemplaza None o undefined con objetos completos.
    """
    default = get_default_config()
    
    # Normalizar banner - SIEMPRE debe ser un objeto, nunca None
    # IMPORTANTE: NO sobrescribir campos existentes, solo agregar los que faltan
    if "banner" not in config_doc or config_doc["banner"] is None or not isinstance(config_doc["banner"], dict):
        config_doc["banner"] = default["banner"].copy()
    else:
        # Solo agregar campos que NO existen, preservar los existentes (incluyendo imágenes)
        for key in ["url", "alt", "active", "width", "height"]:
            if key not in config_doc["banner"]:
                config_doc["banner"][key] = default["banner"][key]
            # Si existe pero es None y el default también es None, mantenerlo
            # Si existe y tiene valor (incluyendo string vacío), mantenerlo
    
    # Normalizar logo - SIEMPRE debe ser un objeto, nunca None
    # IMPORTANTE: NO sobrescribir campos existentes, solo agregar los que faltan
    if "logo" not in config_doc or config_doc["logo"] is None or not isinstance(config_doc["logo"], dict):
        config_doc["logo"] = default["logo"].copy()
    else:
        # Solo agregar campos que NO existen, preservar los existentes (incluyendo imágenes)
        for key in ["url", "alt", "width", "height"]:
            if key not in config_doc["logo"]:
                config_doc["logo"][key] = default["logo"][key]
            # Si existe pero es None y el default también es None, mantenerlo
            # Si existe y tiene valor (incluyendo string vacío), mantenerlo
    
    # Normalizar values - SIEMPRE debe ser un objeto con title y subtitle, nunca None
    if "values" not in config_doc or config_doc["values"] is None or not isinstance(config_doc["values"], dict):
        config_doc["values"] = default["values"].copy()
    else:
        # Asegurar que title y subtitle existan
        if "title" not in config_doc["values"]:
            config_doc["values"]["title"] = default["values"]["title"]
        if "subtitle" not in config_doc["values"]:
            config_doc["values"]["subtitle"] = default["values"]["subtitle"]
        # Asegurar que el array values existe
        if "values" not in config_doc["values"] or not isinstance(config_doc["values"].get("values"), list):
            config_doc["values"]["values"] = []
    
    # Normalizar products - SIEMPRE debe ser un objeto con title y subtitle, nunca None
    if "products" not in config_doc or config_doc["products"] is None or not isinstance(config_doc["products"], dict):
        config_doc["products"] = default["products"].copy()
    else:
        # Asegurar que title y subtitle existan
        if "title" not in config_doc["products"]:
            config_doc["products"]["title"] = default["products"]["title"]
        if "subtitle" not in config_doc["products"]:
            config_doc["products"]["subtitle"] = default["products"]["subtitle"]
        # Asegurar que el array products existe
        if "products" not in config_doc["products"] or not isinstance(config_doc["products"].get("products"), list):
            config_doc["products"]["products"] = []
    
    # Normalizar contact - SIEMPRE debe ser un objeto, nunca None
    if "contact" not in config_doc or config_doc["contact"] is None or not isinstance(config_doc["contact"], dict):
        config_doc["contact"] = default["contact"].copy()
    else:
        for key in ["phone", "email", "address", "social_media"]:
            if key not in config_doc["contact"]:
                config_doc["contact"][key] = default["contact"][key]
    
    # Normalizar colors - SIEMPRE debe ser un objeto, nunca None
    if "colors" not in config_doc or config_doc["colors"] is None or not isinstance(config_doc["colors"], dict):
        config_doc["colors"] = default["colors"].copy()
    else:
        for key in ["primary", "secondary", "accent", "background", "text"]:
            if key not in config_doc["colors"]:
                config_doc["colors"][key] = default["colors"][key]
    
    # Normalizar nosotros - SIEMPRE debe ser un objeto, nunca None
    if "nosotros" not in config_doc or config_doc["nosotros"] is None or not isinstance(config_doc["nosotros"], dict):
        config_doc["nosotros"] = default["nosotros"].copy()
    else:
        for key in ["historia", "mision", "vision", "enabled", "titleFontSize", "titleFontFamily", "titleFontWeight", "textFontSize", "textFontFamily", "textFontWeight"]:
            if key not in config_doc["nosotros"]:
                config_doc["nosotros"][key] = default["nosotros"][key]
    
    # Normalizar servicios - SIEMPRE debe ser un objeto, nunca None
    if "servicios" not in config_doc or config_doc["servicios"] is None or not isinstance(config_doc["servicios"], dict):
        config_doc["servicios"] = default["servicios"].copy()
    else:
        for key in ["enabled", "titleFontSize", "titleFontFamily", "titleFontWeight", "textFontSize", "textFontFamily", "textFontWeight"]:
            if key not in config_doc["servicios"]:
                config_doc["servicios"][key] = default["servicios"][key]
        # Asegurar que el array items existe
        if "items" not in config_doc["servicios"] or not isinstance(config_doc["servicios"].get("items"), list):
            config_doc["servicios"]["items"] = []
    
    # Normalizar typography - SIEMPRE debe ser un objeto, nunca None
    if "typography" not in config_doc or config_doc["typography"] is None or not isinstance(config_doc["typography"], dict):
        config_doc["typography"] = default["typography"].copy()
    else:
        for key in ["defaultFontFamily", "defaultFontSize", "headingFontFamily", "headingFontSize", "headingFontWeight"]:
            if key not in config_doc["typography"]:
                config_doc["typography"][key] = default["typography"][key]
    
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
        
        # Guardar valores originales de imágenes ANTES de normalizar (para restaurar si se pierden)
        banner_url_raw = None
        if config_doc.get("banner") and isinstance(config_doc["banner"], dict):
            banner_url_raw = config_doc["banner"].get("url", "")
            if banner_url_raw and len(banner_url_raw) > 100:
                debug_log(f"GET: Banner tiene imagen ANTES de normalizar: {len(banner_url_raw)} caracteres")
        
        logo_url_raw = None
        if config_doc.get("logo") and isinstance(config_doc["logo"], dict):
            logo_url_raw = config_doc["logo"].get("url", "")
            if logo_url_raw and len(logo_url_raw) > 100:
                debug_log(f"GET: Logo tiene imagen ANTES de normalizar: {len(logo_url_raw)} caracteres")
        
        # Normalizar la configuración para asegurar que todas las propiedades existan
        config_doc = normalize_config(config_doc)
        
        # Verificar y restaurar imágenes si se perdieron durante la normalización
        if config_doc.get("banner") and isinstance(config_doc["banner"], dict):
            banner_url = config_doc["banner"].get("url", "")
            banner_len = len(banner_url) if banner_url else 0
            if banner_len > 100:
                debug_log(f"GET: ✅ Banner tiene imagen DESPUÉS de normalizar: {banner_len} caracteres")
            else:
                debug_log(f"GET: ⚠️ Banner perdió imagen después de normalizar")
                # Restaurar desde el valor original
                if banner_url_raw and len(banner_url_raw) > 100:
                    debug_log(f"GET: 🔧 RESTAURANDO banner desde valor original de MongoDB")
                    config_doc["banner"]["url"] = banner_url_raw
        
        if config_doc.get("logo") and isinstance(config_doc["logo"], dict):
            logo_url = config_doc["logo"].get("url", "")
            logo_len = len(logo_url) if logo_url else 0
            if logo_len > 100:
                debug_log(f"GET: ✅ Logo tiene imagen DESPUÉS de normalizar: {logo_len} caracteres")
            else:
                debug_log(f"GET: ⚠️ Logo perdió imagen después de normalizar")
                # Restaurar desde el valor original
                if logo_url_raw and len(logo_url_raw) > 100:
                    debug_log(f"GET: 🔧 RESTAURANDO logo desde valor original de MongoDB")
                    config_doc["logo"]["url"] = logo_url_raw
        
        # Verificación final de imágenes en la respuesta
        log_image_info(config_doc, "GET RESPUESTA FINAL: ")
        
        return {"config": config_doc}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener configuración: {str(e)}")

def get_image_size(image_str):
    """Obtener el tamaño aproximado de una imagen base64"""
    if not image_str or not isinstance(image_str, str):
        return 0
    # Base64 ocupa aproximadamente 4/3 del tamaño original + overhead
    return len(image_str)

def log_image_info(config_dict, prefix=""):
    """Log información sobre imágenes en la configuración para debugging"""
    debug_log(f"{prefix}=== INFORMACIÓN DE IMÁGENES ===")
    
    # Banner
    if config_dict.get("banner") and isinstance(config_dict["banner"], dict):
        banner_url = config_dict["banner"].get("url", "")
        if banner_url:
            size = get_image_size(banner_url)
            debug_log(f"{prefix}Banner URL: {len(banner_url)} caracteres, ~{size//1024}KB")
            if banner_url.startswith("data:image"):
                debug_log(f"{prefix}Banner es base64: SÍ (prefijo: {banner_url[:30]}...)")
    
    # Logo
    if config_dict.get("logo") and isinstance(config_dict["logo"], dict):
        logo_url = config_dict["logo"].get("url", "")
        if logo_url:
            size = get_image_size(logo_url)
            debug_log(f"{prefix}Logo URL: {len(logo_url)} caracteres, ~{size//1024}KB")
            if logo_url.startswith("data:image"):
                debug_log(f"{prefix}Logo es base64: SÍ (prefijo: {logo_url[:30]}...)")
    
    # Products
    if config_dict.get("products") and isinstance(config_dict["products"], dict):
        products = config_dict["products"].get("products", [])
        if isinstance(products, list):
            debug_log(f"{prefix}Productos: {len(products)} items")
            for idx, product in enumerate(products[:3]):  # Solo primeros 3 para no saturar
                if isinstance(product, dict) and product.get("image"):
                    img = product["image"]
                    size = get_image_size(img)
                    debug_log(f"{prefix}  Producto {idx+1} imagen: {len(img)} caracteres, ~{size//1024}KB")
    
    # Servicios
    if config_dict.get("servicios") and isinstance(config_dict["servicios"], dict):
        servicios = config_dict["servicios"].get("items", [])
        if isinstance(servicios, list):
            debug_log(f"{prefix}Servicios: {len(servicios)} items")
            for idx, servicio in enumerate(servicios[:3]):  # Solo primeros 3
                if isinstance(servicio, dict) and servicio.get("image"):
                    img = servicio["image"]
                    size = get_image_size(img)
                    debug_log(f"{prefix}  Servicio {idx+1} imagen: {len(img)} caracteres, ~{size//1024}KB")
    
    debug_log(f"{prefix}================================")

@router.put("/config")
async def update_home_config(request: HomeConfigRequest):
    """
    Guardar o actualizar la configuración de la página de inicio.
    Solo debe haber un documento en la colección HOME_CONFIG.
    Maneja correctamente imágenes base64 (strings largos).
    """
    try:
        debug_log("=== INICIO ACTUALIZACIÓN CONFIG HOME ===")
        
        # Convertir el modelo a diccionario
        # Usar exclude_none=False para mantener campos None que el frontend pueda querer limpiar
        config_dict = request.config.dict(exclude_unset=False)
        
        # Log información de imágenes ANTES de limpiar
        log_image_info(config_dict, "ANTES: ")
        
        # Verificar específicamente si hay imágenes base64 en los campos clave
        if config_dict.get("banner") and isinstance(config_dict["banner"], dict):
            banner_url = config_dict["banner"].get("url", "")
            if banner_url and len(banner_url) > 100:
                debug_log(f"✅ Banner tiene imagen base64: {len(banner_url)} caracteres")
        
        if config_dict.get("logo") and isinstance(config_dict["logo"], dict):
            logo_url = config_dict["logo"].get("url", "")
            if logo_url and len(logo_url) > 100:
                debug_log(f"✅ Logo tiene imagen base64: {len(logo_url)} caracteres")
        
        if config_dict.get("products") and isinstance(config_dict["products"], dict):
            products = config_dict["products"].get("products", [])
            if isinstance(products, list):
                for idx, p in enumerate(products):
                    if isinstance(p, dict) and p.get("image") and len(p.get("image", "")) > 100:
                        debug_log(f"✅ Producto {idx+1} tiene imagen base64: {len(p['image'])} caracteres")
        
        # Calcular tamaño aproximado del documento
        import json
        doc_size = len(json.dumps(config_dict))
        debug_log(f"Tamaño aproximado del documento: {doc_size} bytes (~{doc_size//1024}KB)")
        
        # Verificar que no exceda el límite de MongoDB (16MB)
        if doc_size > 16 * 1024 * 1024:
            raise HTTPException(
                status_code=400, 
                detail=f"El documento es demasiado grande ({doc_size//1024//1024}MB). Límite de MongoDB: 16MB"
            )
        
        # Obtener configuración actual para hacer merge inteligente
        existing_doc = home_config_collection.find_one({})
        
        # Procesar campos preservando objetos anidados completos
        # IMPORTANTE: Hacer merge profundo para preservar campos existentes
        # Esto asegura que las imágenes base64 y otros campos no se pierdan
        config_dict_clean = {}
        for key, value in config_dict.items():
            if value is not None:
                # Si es un diccionario (objeto anidado), hacer merge con lo existente
                if isinstance(value, dict):
                    # Si existe un valor previo, hacer merge
                    if existing_doc and key in existing_doc and isinstance(existing_doc[key], dict):
                        # Merge profundo: preservar campos existentes, actualizar con nuevos
                        merged_value = existing_doc[key].copy()
                        # Actualizar solo con valores válidos (no None, no string vacío para imágenes)
                        for sub_key, sub_value in value.items():
                            if sub_value is not None:
                                # Para campos de imagen (url en banner/logo, image en productos)
                                # Solo actualizar si el nuevo valor es realmente una imagen (base64 largo)
                                if sub_key in ["url", "image"]:
                                    # Si el nuevo valor es una imagen base64 (más de 100 caracteres)
                                    # o si es un string no vacío, actualizar
                                    if isinstance(sub_value, str):
                                        if len(sub_value) > 100 or sub_value.strip() != "":
                                            merged_value[sub_key] = sub_value
                                            debug_log(f"Actualizando {key}.{sub_key} con imagen base64: {len(sub_value)} caracteres")
                                        else:
                                            # String vacío o muy corto, preservar el existente
                                            debug_log(f"Preservando {key}.{sub_key} existente (nuevo valor es vacío)")
                                    else:
                                        merged_value[sub_key] = sub_value
                                else:
                                    # Para otros campos, actualizar normalmente
                                    merged_value[sub_key] = sub_value
                        config_dict_clean[key] = merged_value
                        debug_log(f"Merge para {key}: preservando {len(existing_doc[key])} campos existentes")
                    else:
                        # Si no existe, usar el valor tal cual
                        config_dict_clean[key] = value
                # Si es una lista (arrays como products.products), reemplazar completamente
                elif isinstance(value, list):
                    config_dict_clean[key] = value
                else:
                    config_dict_clean[key] = value
        
        debug_log(f"Campos a guardar: {list(config_dict_clean.keys())}")
        
        # Verificar que las imágenes base64 están en config_dict_clean
        if config_dict_clean.get("banner") and isinstance(config_dict_clean["banner"], dict):
            banner_url = config_dict_clean["banner"].get("url", "")
            if banner_url and len(banner_url) > 100:
                debug_log(f"✅ Banner URL en config_dict_clean: {len(banner_url)} caracteres")
        
        # Actualizar o crear la configuración (upsert garantiza que solo haya un documento)
        result = home_config_collection.update_one(
            {},
            {"$set": config_dict_clean},
            upsert=True
        )
        
        debug_log(f"Resultado update: matched={result.matched_count}, modified={result.modified_count}, upserted_id={result.upserted_id}")
        
        # Obtener la configuración actualizada para retornar
        # IMPORTANTE: No usar proyección, obtener TODO el documento incluyendo imágenes base64
        updated_config = home_config_collection.find_one({})
        
        if not updated_config:
            # Si por alguna razón no se encontró, usar el config_dict_clean que acabamos de guardar
            debug_log("⚠️ No se encontró documento después de guardar, usando config_dict_clean")
            updated_config = config_dict_clean
        else:
            # Remover _id de MongoDB
            if "_id" in updated_config:
                del updated_config["_id"]
        
        # Verificar que las imágenes se guardaron correctamente EN MongoDB (antes de normalizar)
        log_image_info(updated_config or {}, "DESPUÉS DE GUARDAR (ANTES NORMALIZAR): ")
        
        # Verificar explícitamente que las imágenes estén en el documento desde MongoDB
        banner_url_raw = None
        if updated_config.get("banner") and isinstance(updated_config["banner"], dict):
            banner_url_raw = updated_config["banner"].get("url", "")
            if banner_url_raw and len(banner_url_raw) > 100:
                debug_log(f"✅ VERIFICACIÓN: Banner en MongoDB tiene imagen: {len(banner_url_raw)} caracteres")
            else:
                debug_log(f"⚠️ VERIFICACIÓN: Banner en MongoDB NO tiene imagen o es muy corta: {len(banner_url_raw) if banner_url_raw else 0} caracteres")
        
        logo_url_raw = None
        if updated_config.get("logo") and isinstance(updated_config["logo"], dict):
            logo_url_raw = updated_config["logo"].get("url", "")
            if logo_url_raw and len(logo_url_raw) > 100:
                debug_log(f"✅ VERIFICACIÓN: Logo en MongoDB tiene imagen: {len(logo_url_raw)} caracteres")
            else:
                debug_log(f"⚠️ VERIFICACIÓN: Logo en MongoDB NO tiene imagen o es muy corta: {len(logo_url_raw) if logo_url_raw else 0} caracteres")
        
        # Si no hay configuración, retornar estructura por defecto
        if not updated_config:
            updated_config = get_default_config()
        else:
            # Normalizar la configuración antes de retornarla
            # IMPORTANTE: normalize_config solo agrega campos faltantes, NO debería eliminar imágenes
            updated_config = normalize_config(updated_config)
        
        # Verificar que las imágenes base64 se mantuvieron después de normalizar
        if updated_config.get("banner") and isinstance(updated_config["banner"], dict):
            banner_url = updated_config["banner"].get("url", "")
            banner_len = len(banner_url) if banner_url else 0
            debug_log(f"Banner después de normalizar: {banner_len} caracteres")
            if banner_len > 100:
                debug_log(f"✅ Banner tiene imagen base64 después de normalizar")
            else:
                debug_log(f"⚠️ Banner URL es muy corta después de normalizar (posible pérdida de imagen)")
                # Si se perdió la imagen, restaurarla desde el valor original
                if banner_url_raw and len(banner_url_raw) > 100:
                    debug_log(f"🔧 RESTAURANDO banner desde valor original de MongoDB")
                    updated_config["banner"]["url"] = banner_url_raw
        
        if updated_config.get("logo") and isinstance(updated_config["logo"], dict):
            logo_url = updated_config["logo"].get("url", "")
            logo_len = len(logo_url) if logo_url else 0
            debug_log(f"Logo después de normalizar: {logo_len} caracteres")
            if logo_len > 100:
                debug_log(f"✅ Logo tiene imagen base64 después de normalizar")
            else:
                debug_log(f"⚠️ Logo URL es muy corta después de normalizar (posible pérdida de imagen)")
                # Si se perdió la imagen, restaurarla desde el valor original
                if logo_url_raw and len(logo_url_raw) > 100:
                    debug_log(f"🔧 RESTAURANDO logo desde valor original de MongoDB")
                    updated_config["logo"]["url"] = logo_url_raw
        
        if updated_config.get("products") and isinstance(updated_config["products"], dict):
            products = updated_config["products"].get("products", [])
            products_con_imagen = sum(1 for p in products if isinstance(p, dict) and p.get("image") and len(p.get("image", "")) > 100)
            debug_log(f"Productos con imágenes base64 después de normalizar: {products_con_imagen} de {len(products)}")
        
        # Verificación FINAL antes de retornar: asegurar que las imágenes estén en la respuesta
        log_image_info(updated_config, "RESPUESTA FINAL (ANTES DE RETORNAR): ")
        
        # Calcular tamaño de la respuesta
        try:
            import json
            response_size = len(json.dumps(updated_config))
            debug_log(f"Tamaño de la respuesta: {response_size} bytes (~{response_size//1024}KB)")
            if response_size > 10 * 1024 * 1024:  # 10MB
                debug_log(f"⚠️ ADVERTENCIA: Respuesta muy grande ({response_size//1024//1024}MB), podría haber problemas de serialización")
        except Exception as e:
            debug_log(f"Error al calcular tamaño de respuesta: {str(e)}")
        
        debug_log("=== FIN ACTUALIZACIÓN CONFIG HOME ===")
        
        # Retornar la configuración completa con todas las imágenes
        return {"config": updated_config, "message": "Configuración guardada exitosamente"}
    
    except HTTPException:
        raise
    except Exception as e:
        debug_log(f"ERROR al guardar configuración: {str(e)}")
        import traceback
        debug_log(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al guardar configuración: {str(e)}")

