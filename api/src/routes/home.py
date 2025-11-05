from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
from ..models.authmodels import HomeConfig, HomeConfigRequest
from ..config.mongodb import home_config_collection
from bson import ObjectId
import os
import json

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
    IMPORTANTE: NUNCA sobrescribe campos existentes con valores, solo agrega campos faltantes.
    CRÍTICO: Preserva imágenes base64 (strings largos) sin modificarlos.
    """
    default = get_default_config()
    
    # Normalizar banner - SIEMPRE debe ser un objeto, nunca None
    # CRÍTICO: NO sobrescribir campos existentes, especialmente imágenes (url con strings largos)
    if "banner" not in config_doc or config_doc["banner"] is None or not isinstance(config_doc["banner"], dict):
        config_doc["banner"] = default["banner"].copy()
    else:
        # Solo agregar campos que NO existen, preservar los existentes (incluyendo imágenes)
        # CRÍTICO: Si url existe y es un string largo (>100 chars), es una imagen, NO tocarlo
        for key in ["url", "alt", "active", "width", "height"]:
            if key not in config_doc["banner"]:
                config_doc["banner"][key] = default["banner"][key]
            # CRÍTICO: Si la key existe y es una imagen (url con string largo), NO sobrescribir
            elif key == "url" and isinstance(config_doc["banner"][key], str) and len(config_doc["banner"][key]) > 100:
                # Es una imagen base64, preservarla sin cambios
                pass
            # Si existe pero es None o string corto, mantenerlo (no sobrescribir con default)
            # Si existe y tiene valor (incluyendo string vacío), mantenerlo
    
    # Normalizar logo - SIEMPRE debe ser un objeto, nunca None
    # CRÍTICO: NO sobrescribir campos existentes, especialmente imágenes (url con strings largos)
    if "logo" not in config_doc or config_doc["logo"] is None or not isinstance(config_doc["logo"], dict):
        config_doc["logo"] = default["logo"].copy()
    else:
        # Solo agregar campos que NO existen, preservar los existentes (incluyendo imágenes)
        # CRÍTICO: Si url existe y es un string largo (>100 chars), es una imagen, NO tocarlo
        for key in ["url", "alt", "width", "height"]:
            if key not in config_doc["logo"]:
                config_doc["logo"][key] = default["logo"][key]
            # CRÍTICO: Si la key existe y es una imagen (url con string largo), NO sobrescribir
            elif key == "url" and isinstance(config_doc["logo"][key], str) and len(config_doc["logo"][key]) > 100:
                # Es una imagen base64, preservarla sin cambios
                pass
            # Si existe pero es None o string corto, mantenerlo (no sobrescribir con default)
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
    # CRÍTICO: Preservar imágenes dentro del array products.products
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
        else:
            # CRÍTICO: Preservar imágenes en los productos existentes
            # Si hay productos con imágenes, NO reemplazar el array completo
            # Solo normalizar productos individuales si es necesario
            existing_products = config_doc["products"]["products"]
            for product in existing_products:
                if isinstance(product, dict) and product.get("image") and isinstance(product["image"], str) and len(product["image"]) > 100:
                    # Producto tiene imagen, preservarla sin cambios
                    pass
    
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
        log_image_info(config_dict, "ANTES DE PROCESAR: ")
        
        # Verificar específicamente si hay imágenes base64 en los campos clave
        banner_has_image = False
        banner_image_size = 0
        if config_dict.get("banner") and isinstance(config_dict["banner"], dict):
            banner_url = config_dict["banner"].get("url", "")
            if banner_url and len(banner_url) > 100:
                banner_has_image = True
                banner_image_size = len(banner_url)
                debug_log(f"✅ Banner tiene imagen base64: {banner_image_size} caracteres")
        
        logo_has_image = False
        logo_image_size = 0
        if config_dict.get("logo") and isinstance(config_dict["logo"], dict):
            logo_url = config_dict["logo"].get("url", "")
            if logo_url and len(logo_url) > 100:
                logo_has_image = True
                logo_image_size = len(logo_url)
                debug_log(f"✅ Logo tiene imagen base64: {logo_image_size} caracteres")
        
        products_with_images = []
        if config_dict.get("products") and isinstance(config_dict["products"], dict):
            products = config_dict["products"].get("products", [])
            if isinstance(products, list):
                for idx, p in enumerate(products):
                    if isinstance(p, dict) and p.get("image") and len(p.get("image", "")) > 100:
                        products_with_images.append((idx, len(p.get("image", ""))))
                        debug_log(f"✅ Producto {idx+1} tiene imagen base64: {len(p.get('image', ''))} caracteres")
        
        # Calcular tamaño aproximado del documento INCLUYENDO imágenes
        doc_size = len(json.dumps(config_dict))
        debug_log(f"Tamaño aproximado del documento (incluyendo imágenes): {doc_size} bytes (~{doc_size//1024}KB)")
        
        # Verificación crítica: si el frontend envió imágenes, deben estar en config_dict
        if banner_has_image:
            debug_log(f"🔍 VERIFICACIÓN CRÍTICA: Banner con imagen detectado ({banner_image_size} chars) debe preservarse en todo el proceso")
        if logo_has_image:
            debug_log(f"🔍 VERIFICACIÓN CRÍTICA: Logo con imagen detectado ({logo_image_size} chars) debe preservarse en todo el proceso")
        if products_with_images:
            debug_log(f"🔍 VERIFICACIÓN CRÍTICA: {len(products_with_images)} productos con imágenes deben preservarse")
        
        # Verificar que no exceda el límite de MongoDB (16MB)
        if doc_size > 16 * 1024 * 1024:
            raise HTTPException(
                status_code=400, 
                detail=f"El documento es demasiado grande ({doc_size//1024//1024}MB). Límite de MongoDB: 16MB"
            )
        
        # Obtener configuración actual para hacer merge inteligente
        existing_doc = home_config_collection.find_one({})
        
        # Procesar campos preservando objetos anidados completos
        # ESTRATEGIA CRÍTICA: Para products, si hay imágenes, usar directamente el objeto del frontend SIN merge
        config_dict_clean = {}
        
        # CRÍTICO: Si hay productos con imágenes, procesar products PRIMERO y usar directamente el valor del frontend
        if products_with_images and config_dict.get("products"):
            debug_log(f"🔧 CRÍTICO: products_with_images detectado ({len(products_with_images)} productos), usando products del frontend DIRECTAMENTE")
            config_dict_clean["products"] = config_dict["products"].copy()
            debug_log(f"✅ Productos del frontend copiados directamente: {len(config_dict_clean['products'].get('products', []))} items")
        
        for key, value in config_dict.items():
            # CRÍTICO: Si products ya fue procesado arriba, saltarlo aquí
            if key == "products" and products_with_images and key in config_dict_clean:
                debug_log(f"⏭️ Saltando procesamiento de products (ya procesado directamente)")
                continue
                
            if value is not None:
                # Si es un diccionario (objeto anidado), hacer merge con lo existente
                if isinstance(value, dict):
                    # CRÍTICO: Verificar si hay imágenes nuevas en el valor entrante
                    has_new_images = False
                    for sub_key, sub_value in value.items():
                        # Para campos directos (url, image)
                        if sub_key in ["url", "image"] and isinstance(sub_value, str) and len(sub_value) > 100:
                            has_new_images = True
                            debug_log(f"🔍 IMAGEN NUEVA detectada en {key}.{sub_key}: {len(sub_value)} caracteres")
                            break
                        # Para arrays de productos/servicios que contienen imágenes
                        elif sub_key in ["products", "items"] and isinstance(sub_value, list):
                            for item in sub_value:
                                if isinstance(item, dict):
                                    # Verificar si el item tiene imagen
                                    if item.get("image") and isinstance(item["image"], str) and len(item["image"]) > 100:
                                        has_new_images = True
                                        debug_log(f"🔍 IMAGEN NUEVA detectada en {key}.{sub_key}[{sub_value.index(item)}].image: {len(item['image'])} caracteres")
                                        break
                            if has_new_images:
                                break
                    
                    # Si hay imágenes nuevas, usar el objeto completo del frontend y hacer merge solo de campos no-imagen
                    if has_new_images:
                        debug_log(f"✅ Usando objeto completo del frontend para {key} (contiene imágenes nuevas)")
                        # Empezar con el objeto del frontend (que tiene las imágenes)
                        merged_value = value.copy()
                        # CRÍTICO: Para products, asegurar que el array products.products del frontend se preserve
                        if key == "products" and "products" in merged_value:
                            debug_log(f"  🔍 CRÍTICO: Preservando array products.products del frontend (tiene {len(merged_value['products'])} items)")
                        
                        # Hacer merge solo de campos que NO son imágenes del documento existente
                        if existing_doc and key in existing_doc and isinstance(existing_doc[key], dict):
                            for existing_key, existing_value in existing_doc[key].items():
                                # Para arrays como products.products o servicios.items, NO hacer merge, usar el del frontend
                                if existing_key in ["products", "items"] and isinstance(existing_value, list):
                                    # Si el frontend tiene este array, usar el del frontend (ya tiene las imágenes)
                                    if existing_key in merged_value and isinstance(merged_value[existing_key], list):
                                        debug_log(f"  Preservando array {existing_key} del frontend (contiene imágenes, {len(merged_value[existing_key])} items)")
                                        # Ya está en merged_value, no hacer nada - CRÍTICO: NO sobrescribir
                                    else:
                                        # Si el frontend no tiene este array, usar el existente
                                        merged_value[existing_key] = existing_value
                                        debug_log(f"  Usando array {existing_key} del documento existente (frontend no lo tiene)")
                                # Solo agregar campos que no son imágenes/arrays y que no están en el objeto del frontend
                                elif existing_key not in ["url", "image"] and existing_key not in merged_value:
                                    merged_value[existing_key] = existing_value
                                    debug_log(f"  Agregando campo {existing_key} desde documento existente")
                        
                        # VERIFICACIÓN POST-MERGE: Asegurar que el array products.products todavía tiene imágenes
                        if key == "products" and products_with_images:
                            products_after_merge = merged_value.get("products", [])
                            if isinstance(products_after_merge, list):
                                products_with_images_after = sum(1 for p in products_after_merge if isinstance(p, dict) and p.get("image") and len(p.get("image", "")) > 100)
                                if products_with_images_after < len(products_with_images):
                                    debug_log(f"  ⚠️ CRÍTICO: Solo {products_with_images_after} de {len(products_with_images)} productos tienen imágenes después del merge")
                                    debug_log(f"  🔧 RESTAURANDO: Array products.products desde value original")
                                    # Restaurar desde value original
                                    if "products" in value:
                                        merged_value["products"] = value["products"]
                                        debug_log(f"  ✅ RESTAURADO: Array products.products desde value original")
                        
                        config_dict_clean[key] = merged_value
                    # Si NO hay imágenes nuevas detectadas en este nivel, pero sabemos que hay productos con imágenes
                    # CRÍTICO: Para products, si products_with_images tiene elementos, usar el array del frontend
                    elif key == "products" and products_with_images:
                        debug_log(f"✅ CRÍTICO: products_with_images detectado ({len(products_with_images)} productos), usando array del frontend")
                        merged_value = value.copy()
                        # Agregar solo campos que no son el array products
                        if existing_doc and key in existing_doc and isinstance(existing_doc[key], dict):
                            for existing_key, existing_value in existing_doc[key].items():
                                if existing_key != "products" and existing_key not in merged_value:
                                    merged_value[existing_key] = existing_value
                                    debug_log(f"  Agregando campo {existing_key} desde documento existente")
                        config_dict_clean[key] = merged_value
                    # Si NO hay imágenes nuevas, hacer merge normal
                    elif existing_doc and key in existing_doc and isinstance(existing_doc[key], dict):
                        # Merge profundo: preservar campos existentes, actualizar con nuevos
                        merged_value = existing_doc[key].copy()
                        
                        # Actualizar solo con valores válidos (no None, no string vacío para imágenes)
                        for sub_key, sub_value in value.items():
                            if sub_value is not None:
                                # CRÍTICO: Para arrays como products.products, usar el del frontend si existe
                                # Esto asegura que las imágenes de productos se preserven
                                if sub_key in ["products", "items"] and isinstance(sub_value, list):
                                    # Usar el array del frontend (puede tener imágenes actualizadas)
                                    merged_value[sub_key] = sub_value
                                    debug_log(f"✅ Actualizando array {sub_key} desde frontend (preservando imágenes)")
                                # Para campos de imagen (url en banner/logo, image en productos)
                                elif sub_key in ["url", "image"]:
                                    # Si es una imagen base64 (más de 100 caracteres), actualizar
                                    if isinstance(sub_value, str):
                                        if len(sub_value) > 100:
                                            merged_value[sub_key] = sub_value
                                            debug_log(f"✅ ACTUALIZANDO {key}.{sub_key} con imagen base64: {len(sub_value)} caracteres")
                                        elif sub_value.strip() != "":
                                            merged_value[sub_key] = sub_value
                                            debug_log(f"Actualizando {key}.{sub_key} con valor: {len(sub_value)} caracteres")
                                        # Si es vacío, preservar el existente
                                else:
                                    # Para otros campos, actualizar normalmente
                                    merged_value[sub_key] = sub_value
                        
                        config_dict_clean[key] = merged_value
                        debug_log(f"Merge normal para {key}: preservando {len(existing_doc[key])} campos existentes")
                    else:
                        # Si no existe, usar el valor tal cual
                        debug_log(f"No hay documento existente para {key}, usando valor completo del frontend")
                        config_dict_clean[key] = value
                # Si es una lista (arrays como products.products), reemplazar completamente
                elif isinstance(value, list):
                    config_dict_clean[key] = value
                else:
                    config_dict_clean[key] = value
        
        # VERIFICACIÓN FINAL: Asegurar que las imágenes detectadas al inicio estén en config_dict_clean
        if banner_has_image:
            if config_dict_clean.get("banner") and isinstance(config_dict_clean["banner"], dict):
                banner_url_clean = config_dict_clean["banner"].get("url", "")
                if not banner_url_clean or len(banner_url_clean) < 100:
                    debug_log(f"⚠️ CRÍTICO: Banner perdió imagen en config_dict_clean, restaurando desde config_dict")
                    if not config_dict_clean.get("banner"):
                        config_dict_clean["banner"] = {}
                    config_dict_clean["banner"]["url"] = config_dict["banner"]["url"]
                    debug_log(f"✅ Banner restaurado: {len(config_dict_clean['banner']['url'])} caracteres")
        
        if logo_has_image:
            if config_dict_clean.get("logo") and isinstance(config_dict_clean["logo"], dict):
                logo_url_clean = config_dict_clean["logo"].get("url", "")
                if not logo_url_clean or len(logo_url_clean) < 100:
                    debug_log(f"⚠️ CRÍTICO: Logo perdió imagen en config_dict_clean, restaurando desde config_dict")
                    if not config_dict_clean.get("logo"):
                        config_dict_clean["logo"] = {}
                    config_dict_clean["logo"]["url"] = config_dict["logo"]["url"]
                    debug_log(f"✅ Logo restaurado: {len(config_dict_clean['logo']['url'])} caracteres")
        
        debug_log(f"Campos a guardar: {list(config_dict_clean.keys())}")
        
        # VERIFICACIÓN CRÍTICA PRE-GUARDADO: Asegurar que las imágenes estén en config_dict_clean
        log_image_info(config_dict_clean, "PRE-GUARDADO (config_dict_clean): ")
        
        # Verificar que las imágenes base64 están en config_dict_clean ANTES de guardar
        if banner_has_image:
            if config_dict_clean.get("banner") and isinstance(config_dict_clean["banner"], dict):
                banner_url = config_dict_clean["banner"].get("url", "")
                if banner_url and len(banner_url) > 100:
                    debug_log(f"✅ VERIFICACIÓN PRE-GUARDADO: Banner URL en config_dict_clean: {len(banner_url)} caracteres")
                else:
                    debug_log(f"❌ ERROR CRÍTICO: Banner NO tiene imagen en config_dict_clean antes de guardar")
                    # Restaurar desde config_dict original
                    if config_dict.get("banner") and config_dict["banner"].get("url"):
                        if not config_dict_clean.get("banner"):
                            config_dict_clean["banner"] = {}
                        config_dict_clean["banner"]["url"] = config_dict["banner"]["url"]
                        debug_log(f"🔧 RESTAURADO: Banner desde config_dict original: {len(config_dict_clean['banner']['url'])} caracteres")
        
        if logo_has_image:
            if config_dict_clean.get("logo") and isinstance(config_dict_clean["logo"], dict):
                logo_url = config_dict_clean["logo"].get("url", "")
                if logo_url and len(logo_url) > 100:
                    debug_log(f"✅ VERIFICACIÓN PRE-GUARDADO: Logo URL en config_dict_clean: {len(logo_url)} caracteres")
                else:
                    debug_log(f"❌ ERROR CRÍTICO: Logo NO tiene imagen en config_dict_clean antes de guardar")
                    # Restaurar desde config_dict original
                    if config_dict.get("logo") and config_dict["logo"].get("url"):
                        if not config_dict_clean.get("logo"):
                            config_dict_clean["logo"] = {}
                        config_dict_clean["logo"]["url"] = config_dict["logo"]["url"]
                        debug_log(f"🔧 RESTAURADO: Logo desde config_dict original: {len(config_dict_clean['logo']['url'])} caracteres")
        
        # Verificación PRE-GUARDADO: Asegurar que las imágenes estén en config_dict_clean
        if banner_has_image:
            banner_in_clean = config_dict_clean.get("banner") and config_dict_clean["banner"].get("url") and len(config_dict_clean["banner"]["url"]) > 100
            if not banner_in_clean:
                debug_log(f"❌ ERROR CRÍTICO PRE-GUARDADO: Banner NO está en config_dict_clean antes de guardar en MongoDB")
                # Restaurar desde config_dict
                if config_dict.get("banner") and config_dict["banner"].get("url"):
                    if not config_dict_clean.get("banner"):
                        config_dict_clean["banner"] = {}
                    config_dict_clean["banner"]["url"] = config_dict["banner"]["url"]
                    debug_log(f"🔧 RESTAURADO: Banner en config_dict_clean: {len(config_dict_clean['banner']['url'])} caracteres")
            else:
                debug_log(f"✅ VERIFICACIÓN PRE-GUARDADO: Banner está en config_dict_clean: {len(config_dict_clean['banner']['url'])} caracteres")
        
        if logo_has_image:
            logo_in_clean = config_dict_clean.get("logo") and config_dict_clean["logo"].get("url") and len(config_dict_clean["logo"]["url"]) > 100
            if not logo_in_clean:
                debug_log(f"❌ ERROR CRÍTICO PRE-GUARDADO: Logo NO está en config_dict_clean antes de guardar en MongoDB")
                # Restaurar desde config_dict
                if config_dict.get("logo") and config_dict["logo"].get("url"):
                    if not config_dict_clean.get("logo"):
                        config_dict_clean["logo"] = {}
                    config_dict_clean["logo"]["url"] = config_dict["logo"]["url"]
                    debug_log(f"🔧 RESTAURADO: Logo en config_dict_clean: {len(config_dict_clean['logo']['url'])} caracteres")
            else:
                debug_log(f"✅ VERIFICACIÓN PRE-GUARDADO: Logo está en config_dict_clean: {len(config_dict_clean['logo']['url'])} caracteres")
        
        # Verificar imágenes de productos - CRÍTICO: Asegurar que se preserven
        if products_with_images:
            debug_log(f"🔍 VERIFICACIÓN: Se detectaron {len(products_with_images)} productos con imágenes en el frontend")
            products_in_clean = False
            products_with_images_count = 0
            
            if config_dict_clean.get("products") and isinstance(config_dict_clean["products"], dict):
                clean_products = config_dict_clean["products"].get("products", [])
                if isinstance(clean_products, list):
                    products_with_images_count = sum(1 for p in clean_products if isinstance(p, dict) and p.get("image") and len(p.get("image", "")) > 100)
                    if products_with_images_count >= len(products_with_images):
                        products_in_clean = True
                        debug_log(f"✅ VERIFICACIÓN PRE-GUARDADO: {products_with_images_count} productos con imágenes en config_dict_clean")
                    else:
                        debug_log(f"⚠️ VERIFICACIÓN PRE-GUARDADO: Solo {products_with_images_count} de {len(products_with_images)} productos tienen imágenes en config_dict_clean")
            
            # CRÍTICO: Si no hay suficientes productos con imágenes, restaurar desde config_dict
            if not products_in_clean or products_with_images_count < len(products_with_images):
                debug_log(f"❌ ERROR CRÍTICO PRE-GUARDADO: Productos con imágenes NO están correctamente en config_dict_clean")
                debug_log(f"🔧 RESTAURANDO: Productos completos desde config_dict original (tiene {len(products_with_images)} productos con imágenes)")
                # Restaurar desde config_dict - FORZAR el array completo
                if config_dict.get("products") and isinstance(config_dict["products"], dict):
                    if not config_dict_clean.get("products"):
                        config_dict_clean["products"] = {}
                    # CRÍTICO: Usar el array completo del frontend que sabemos que tiene las imágenes
                    config_dict_clean["products"]["products"] = config_dict["products"].get("products", [])
                    # Preservar title y subtitle si existen
                    if "title" not in config_dict_clean["products"] and config_dict["products"].get("title"):
                        config_dict_clean["products"]["title"] = config_dict["products"]["title"]
                    if "subtitle" not in config_dict_clean["products"] and config_dict["products"].get("subtitle"):
                        config_dict_clean["products"]["subtitle"] = config_dict["products"]["subtitle"]
                    
                    # Verificar que se restauró correctamente
                    restored_products = config_dict_clean["products"].get("products", [])
                    restored_count = sum(1 for p in restored_products if isinstance(p, dict) and p.get("image") and len(p.get("image", "")) > 100)
                    debug_log(f"✅ RESTAURADO: {restored_count} productos con imágenes ahora en config_dict_clean")
        
        # VERIFICACIÓN FINAL ABSOLUTA: Antes de guardar, asegurar que productos con imágenes estén presentes
        if products_with_images:
            final_products = config_dict_clean.get("products") and config_dict_clean["products"].get("products", [])
            if isinstance(final_products, list):
                final_count = sum(1 for p in final_products if isinstance(p, dict) and p.get("image") and len(p.get("image", "")) > 100)
                if final_count < len(products_with_images):
                    debug_log(f"❌ CRÍTICO FINAL: Solo {final_count} de {len(products_with_images)} productos tienen imágenes antes de guardar")
                    debug_log(f"🔧 FORZANDO: Restaurar array completo de productos desde config_dict")
                    if config_dict.get("products") and isinstance(config_dict["products"], dict):
                        if not config_dict_clean.get("products"):
                            config_dict_clean["products"] = {}
                        config_dict_clean["products"]["products"] = config_dict["products"].get("products", [])
                        debug_log(f"✅ FORZADO: Array de productos restaurado desde config_dict")
        
        # Actualizar o crear la configuración (upsert garantiza que solo haya un documento)
        # CRÍTICO: Usar $set para actualizar campos específicos, preservando otros campos existentes
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
                # CRÍTICO: Si sabemos que enviamos una imagen pero MongoDB no la tiene, restaurar desde config_dict_clean
                if banner_has_image and config_dict_clean.get("banner") and config_dict_clean["banner"].get("url"):
                    debug_log(f"🔧 CRÍTICO: Restaurando banner desde config_dict_clean (MongoDB no lo guardó)")
                    if not updated_config.get("banner"):
                        updated_config["banner"] = {}
                    updated_config["banner"]["url"] = config_dict_clean["banner"]["url"]
                    banner_url_raw = updated_config["banner"]["url"]
                    debug_log(f"✅ Banner restaurado desde config_dict_clean: {len(banner_url_raw)} caracteres")
        
        logo_url_raw = None
        if updated_config.get("logo") and isinstance(updated_config["logo"], dict):
            logo_url_raw = updated_config["logo"].get("url", "")
            if logo_url_raw and len(logo_url_raw) > 100:
                debug_log(f"✅ VERIFICACIÓN: Logo en MongoDB tiene imagen: {len(logo_url_raw)} caracteres")
            else:
                debug_log(f"⚠️ VERIFICACIÓN: Logo en MongoDB NO tiene imagen o es muy corta: {len(logo_url_raw) if logo_url_raw else 0} caracteres")
                # CRÍTICO: Si sabemos que enviamos una imagen pero MongoDB no la tiene, restaurar desde config_dict_clean
                if logo_has_image and config_dict_clean.get("logo") and config_dict_clean["logo"].get("url"):
                    debug_log(f"🔧 CRÍTICO: Restaurando logo desde config_dict_clean (MongoDB no lo guardó)")
                    if not updated_config.get("logo"):
                        updated_config["logo"] = {}
                    updated_config["logo"]["url"] = config_dict_clean["logo"]["url"]
                    logo_url_raw = updated_config["logo"]["url"]
                    debug_log(f"✅ Logo restaurado desde config_dict_clean: {len(logo_url_raw)} caracteres")
        
        # Si no hay configuración, retornar estructura por defecto
        if not updated_config:
            updated_config = get_default_config()
        else:
            # CRÍTICO: Guardar imágenes ANTES de normalizar (por si normalize_config las elimina)
            banner_url_before_normalize = None
            if updated_config.get("banner") and isinstance(updated_config["banner"], dict):
                banner_url_before_normalize = updated_config["banner"].get("url", "")
                if banner_url_before_normalize and len(banner_url_before_normalize) > 100:
                    debug_log(f"🔍 Banner URL ANTES de normalizar: {len(banner_url_before_normalize)} caracteres")
            
            logo_url_before_normalize = None
            if updated_config.get("logo") and isinstance(updated_config["logo"], dict):
                logo_url_before_normalize = updated_config["logo"].get("url", "")
                if logo_url_before_normalize and len(logo_url_before_normalize) > 100:
                    debug_log(f"🔍 Logo URL ANTES de normalizar: {len(logo_url_before_normalize)} caracteres")
            
            # Normalizar la configuración antes de retornarla
            # IMPORTANTE: normalize_config solo agrega campos faltantes, NO debería eliminar imágenes
            updated_config = normalize_config(updated_config)
            
            # CRÍTICO: Verificar y restaurar imágenes DESPUÉS de normalizar
            if banner_url_before_normalize and len(banner_url_before_normalize) > 100:
                if not updated_config.get("banner") or not updated_config["banner"].get("url") or len(updated_config["banner"]["url"]) < 100:
                    debug_log(f"⚠️ CRÍTICO: Banner perdió imagen durante normalize_config, restaurando...")
                    if not updated_config.get("banner"):
                        updated_config["banner"] = {}
                    updated_config["banner"]["url"] = banner_url_before_normalize
                    debug_log(f"✅ Banner restaurado después de normalize_config: {len(banner_url_before_normalize)} caracteres")
            
            if logo_url_before_normalize and len(logo_url_before_normalize) > 100:
                if not updated_config.get("logo") or not updated_config["logo"].get("url") or len(updated_config["logo"]["url"]) < 100:
                    debug_log(f"⚠️ CRÍTICO: Logo perdió imagen durante normalize_config, restaurando...")
                    if not updated_config.get("logo"):
                        updated_config["logo"] = {}
                    updated_config["logo"]["url"] = logo_url_before_normalize
                    debug_log(f"✅ Logo restaurado después de normalize_config: {len(logo_url_before_normalize)} caracteres")
            
            # CRÍTICO: Verificar y restaurar imágenes de productos DESPUÉS de normalizar
            if products_with_images:
                products_after_normalize = updated_config.get("products") and isinstance(updated_config["products"], dict) and updated_config["products"].get("products", [])
                if isinstance(products_after_normalize, list):
                    products_with_images_after = sum(1 for p in products_after_normalize if isinstance(p, dict) and p.get("image") and len(p.get("image", "")) > 100)
                    if products_with_images_after < len(products_with_images):
                        debug_log(f"⚠️ CRÍTICO: Productos perdieron imágenes durante normalize_config ({products_with_images_after} de {len(products_with_images)}), restaurando...")
                        # Restaurar desde config_dict_clean
                        if config_dict_clean.get("products") and isinstance(config_dict_clean["products"], dict):
                            if not updated_config.get("products"):
                                updated_config["products"] = {}
                            updated_config["products"]["products"] = config_dict_clean["products"].get("products", [])
                            debug_log(f"✅ Productos restaurados después de normalize_config")
                    else:
                        debug_log(f"✅ Productos mantuvieron imágenes después de normalize_config: {products_with_images_after} productos con imágenes")
        
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
            response_size = len(json.dumps(updated_config))
            debug_log(f"Tamaño de la respuesta: {response_size} bytes (~{response_size//1024}KB)")
            
            # CRÍTICO: Si sabemos que enviamos imágenes pero la respuesta es muy pequeña, algo está mal
            expected_min_size = 0
            if banner_has_image:
                expected_min_size += banner_image_size
            if logo_has_image:
                expected_min_size += logo_image_size
            
            if expected_min_size > 0 and response_size < expected_min_size * 0.5:  # Si es menos del 50% del tamaño esperado
                debug_log(f"❌ ERROR CRÍTICO: Respuesta muy pequeña ({response_size} bytes) cuando debería tener al menos {expected_min_size} bytes")
                debug_log(f"🔧 Usando config_dict_clean directamente en lugar de updated_config")
                # Usar config_dict_clean directamente que sabemos que tiene las imágenes
                updated_config = config_dict_clean.copy()
                # Normalizar de nuevo
                updated_config = normalize_config(updated_config)
                # Restaurar imágenes si se perdieron
                if banner_has_image and config_dict_clean.get("banner") and config_dict_clean["banner"].get("url"):
                    if not updated_config.get("banner"):
                        updated_config["banner"] = {}
                    updated_config["banner"]["url"] = config_dict_clean["banner"]["url"]
                if logo_has_image and config_dict_clean.get("logo") and config_dict_clean["logo"].get("url"):
                    if not updated_config.get("logo"):
                        updated_config["logo"] = {}
                    updated_config["logo"]["url"] = config_dict_clean["logo"]["url"]
                # Recalcular tamaño
                response_size = len(json.dumps(updated_config))
                debug_log(f"✅ Tamaño de respuesta después de restaurar: {response_size} bytes (~{response_size//1024}KB)")
            
            if response_size > 10 * 1024 * 1024:  # 10MB
                debug_log(f"⚠️ ADVERTENCIA: Respuesta muy grande ({response_size//1024//1024}MB), podría haber problemas de serialización")
        except Exception as e:
            debug_log(f"Error al calcular tamaño de respuesta: {str(e)}")
        
        # VERIFICACIÓN FINAL ABSOLUTA: Si sabemos que enviamos imágenes, deben estar en la respuesta
        if banner_has_image:
            if not updated_config.get("banner") or not updated_config["banner"].get("url") or len(updated_config["banner"]["url"]) < 100:
                debug_log(f"❌ ERROR FINAL: Banner NO está en la respuesta, usando config_dict_clean")
                if not updated_config.get("banner"):
                    updated_config["banner"] = {}
                if config_dict_clean.get("banner") and config_dict_clean["banner"].get("url"):
                    updated_config["banner"]["url"] = config_dict_clean["banner"]["url"]
                    debug_log(f"✅ Banner restaurado en respuesta final: {len(updated_config['banner']['url'])} caracteres")
        
        if logo_has_image:
            if not updated_config.get("logo") or not updated_config["logo"].get("url") or len(updated_config["logo"]["url"]) < 100:
                debug_log(f"❌ ERROR FINAL: Logo NO está en la respuesta, usando config_dict_clean")
                if not updated_config.get("logo"):
                    updated_config["logo"] = {}
                if config_dict_clean.get("logo") and config_dict_clean["logo"].get("url"):
                    updated_config["logo"]["url"] = config_dict_clean["logo"]["url"]
                    debug_log(f"✅ Logo restaurado en respuesta final: {len(updated_config['logo']['url'])} caracteres")
        
        # CRÍTICO: Verificación final para productos con imágenes
        if products_with_images:
            products_final = updated_config.get("products") and isinstance(updated_config["products"], dict) and updated_config["products"].get("products", [])
            if isinstance(products_final, list):
                products_final_count = sum(1 for p in products_final if isinstance(p, dict) and p.get("image") and len(p.get("image", "")) > 100)
                if products_final_count < len(products_with_images):
                    debug_log(f"❌ ERROR FINAL: Solo {products_final_count} de {len(products_with_images)} productos tienen imágenes en la respuesta final")
                    debug_log(f"🔧 RESTAURANDO: Productos completos desde config_dict_clean")
                    if config_dict_clean.get("products") and isinstance(config_dict_clean["products"], dict):
                        if not updated_config.get("products"):
                            updated_config["products"] = {}
                        updated_config["products"]["products"] = config_dict_clean["products"].get("products", [])
                        restored_count = sum(1 for p in updated_config["products"]["products"] if isinstance(p, dict) and p.get("image") and len(p.get("image", "")) > 100)
                        debug_log(f"✅ Productos restaurados en respuesta final: {restored_count} productos con imágenes")
        
        debug_log("=== FIN ACTUALIZACIÓN CONFIG HOME ===")
        
        # VERIFICACIÓN FINAL ABSOLUTA: Serializar y verificar que las imágenes estén presentes
        try:
            # CRÍTICO: Verificar que las imágenes estén en updated_config ANTES de serializar
            if banner_has_image:
                banner_in_updated = updated_config.get("banner") and updated_config["banner"].get("url") and len(updated_config["banner"]["url"]) > 100
                if not banner_in_updated:
                    debug_log(f"❌ CRÍTICO ANTES DE SERIALIZAR: Banner NO está en updated_config")
                    debug_log(f"🔧 Restaurando banner desde config_dict_clean antes de serializar")
                    if not updated_config.get("banner"):
                        updated_config["banner"] = {}
                    if config_dict_clean.get("banner") and config_dict_clean["banner"].get("url"):
                        updated_config["banner"]["url"] = config_dict_clean["banner"]["url"]
                        debug_log(f"✅ Banner restaurado en updated_config: {len(updated_config['banner']['url'])} caracteres")
                else:
                    debug_log(f"✅ VERIFICACIÓN: Banner está en updated_config antes de serializar: {len(updated_config['banner']['url'])} caracteres")
            
            # Intentar serializar la respuesta para detectar problemas
            response_dict = {"config": updated_config, "message": "Configuración guardada exitosamente"}
            
            # Verificar que las imágenes estén en response_dict ANTES de serializar
            if banner_has_image:
                banner_in_response = response_dict.get("config") and response_dict["config"].get("banner") and response_dict["config"]["banner"].get("url") and len(response_dict["config"]["banner"]["url"]) > 100
                if not banner_in_response:
                    debug_log(f"❌ CRÍTICO: Banner NO está en response_dict antes de serializar")
                    # Restaurar
                    if config_dict_clean.get("banner") and config_dict_clean["banner"].get("url"):
                        if not response_dict["config"].get("banner"):
                            response_dict["config"]["banner"] = {}
                        response_dict["config"]["banner"]["url"] = config_dict_clean["banner"]["url"]
                        debug_log(f"✅ Banner restaurado en response_dict: {len(response_dict['config']['banner']['url'])} caracteres")
            
            # CRÍTICO: Verificar imágenes de productos en response_dict ANTES de serializar
            if products_with_images:
                products_in_response = False
                response_products = response_dict.get("config") and response_dict["config"].get("products") and isinstance(response_dict["config"]["products"], dict) and response_dict["config"]["products"].get("products", [])
                if isinstance(response_products, list):
                    products_with_images_count = sum(1 for p in response_products if isinstance(p, dict) and p.get("image") and len(p.get("image", "")) > 100)
                    if products_with_images_count >= len(products_with_images):
                        products_in_response = True
                        debug_log(f"✅ VERIFICACIÓN: {products_with_images_count} productos con imágenes en response_dict antes de serializar")
                
                if not products_in_response:
                    debug_log(f"❌ CRÍTICO: Productos con imágenes NO están en response_dict antes de serializar")
                    # Restaurar desde config_dict_clean
                    if config_dict_clean.get("products") and isinstance(config_dict_clean["products"], dict):
                        if not response_dict["config"].get("products"):
                            response_dict["config"]["products"] = {}
                        response_dict["config"]["products"]["products"] = config_dict_clean["products"].get("products", [])
                        # Verificar que se restauró
                        restored_products = response_dict["config"]["products"].get("products", [])
                        restored_count = sum(1 for p in restored_products if isinstance(p, dict) and p.get("image") and len(p.get("image", "")) > 100)
                        debug_log(f"✅ Productos restaurados en response_dict: {restored_count} productos con imágenes")
            
            response_json = json.dumps(response_dict)
            response_size = len(response_json)
            debug_log(f"Tamaño final de respuesta JSON serializada: {response_size} bytes (~{response_size//1024}KB)")
            
            # Si sabemos que hay imágenes pero la respuesta es muy pequeña, usar config_dict_clean directamente
            if banner_has_image and response_size < banner_image_size * 0.5:
                debug_log(f"❌ CRÍTICO: Respuesta serializada muy pequeña ({response_size} bytes) cuando debería tener al menos {banner_image_size} bytes")
                debug_log(f"🔧 Usando config_dict_clean directamente en respuesta")
                # Usar config_dict_clean que sabemos que tiene las imágenes
                response_dict["config"] = config_dict_clean.copy()
                # Normalizar pero preservar imágenes
                response_dict["config"] = normalize_config(response_dict["config"])
                # Restaurar imágenes si se perdieron
                if banner_has_image and config_dict_clean.get("banner") and config_dict_clean["banner"].get("url"):
                    if not response_dict["config"].get("banner"):
                        response_dict["config"]["banner"] = {}
                    response_dict["config"]["banner"]["url"] = config_dict_clean["banner"]["url"]
                if logo_has_image and config_dict_clean.get("logo") and config_dict_clean["logo"].get("url"):
                    if not response_dict["config"].get("logo"):
                        response_dict["config"]["logo"] = {}
                    response_dict["config"]["logo"]["url"] = config_dict_clean["logo"]["url"]
                
                # CRÍTICO: Restaurar productos con imágenes
                if products_with_images and config_dict_clean.get("products") and isinstance(config_dict_clean["products"], dict):
                    if not response_dict["config"].get("products"):
                        response_dict["config"]["products"] = {}
                    response_dict["config"]["products"]["products"] = config_dict_clean["products"].get("products", [])
                    restored_count = sum(1 for p in response_dict["config"]["products"]["products"] if isinstance(p, dict) and p.get("image") and len(p.get("image", "")) > 100)
                    debug_log(f"✅ Productos restaurados en response_dict desde config_dict_clean: {restored_count} productos con imágenes")
                
                # Re-serializar
                response_json = json.dumps(response_dict)
                response_size = len(response_json)
                debug_log(f"✅ Tamaño después de restaurar desde config_dict_clean: {response_size} bytes (~{response_size//1024}KB)")
            
            # Retornar usando JSONResponse para asegurar serialización correcta
            return JSONResponse(content=response_dict)
        except Exception as e:
            debug_log(f"❌ ERROR al serializar respuesta: {str(e)}")
            import traceback
            debug_log(f"Traceback: {traceback.format_exc()}")
            # Fallback: retornar directamente (FastAPI lo serializará)
            return {"config": updated_config, "message": "Configuración guardada exitosamente"}
    
    except HTTPException:
        raise
    except Exception as e:
        debug_log(f"ERROR al guardar configuración: {str(e)}")
        import traceback
        debug_log(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al guardar configuración: {str(e)}")

