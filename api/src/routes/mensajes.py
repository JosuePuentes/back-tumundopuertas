from fastapi import APIRouter, HTTPException, Body, Depends, Request
from fastapi import Request as FastAPIRequest
from bson import ObjectId
from datetime import datetime
from typing import List, Optional, Dict, Any
from ..config.mongodb import db, clientes_usuarios_collection, usuarios_collection
from ..auth.auth import get_current_user, get_current_cliente, SECRET_KEY, ALGORITHM
import jwt
from pydantic import BaseModel

router = APIRouter()

# Colección de mensajes
mensajes_collection = db["mensajes"]

class MensajeRequest(BaseModel):
    pedido_id: str
    mensaje: str
    remitente_id: Optional[str] = None
    remitente_nombre: Optional[str] = None
    remitente_tipo: Optional[str] = None  # "admin", "cliente"
    leido: bool = False

@router.get("/soporte")
async def get_conversaciones_soporte(current_user: dict = Depends(get_current_user)):
    """
    Obtener todas las conversaciones de soporte agrupadas por cliente.
    Solo para administradores.
    """
    try:
        # Verificar que sea administrador
        if current_user.get("rol") != "admin":
            raise HTTPException(status_code=403, detail="No tienes permisos para acceder a este recurso")
        
        # Buscar todos los mensajes de soporte (pedido_id que empiece con "soporte_")
        mensajes = list(mensajes_collection.find({
            "pedido_id": {"$regex": "^soporte_"}
        }).sort("fecha_creacion", 1))
        
        # Agrupar por cliente_id (extraído del pedido_id)
        conversaciones_por_cliente = {}
        
        for mensaje in mensajes:
            pedido_id = mensaje.get("pedido_id", "")
            # Extraer cliente_id del formato "soporte_{cliente_id}"
            if pedido_id.startswith("soporte_"):
                cliente_id = pedido_id.replace("soporte_", "")
                
                if cliente_id not in conversaciones_por_cliente:
                    # Buscar información del cliente
                    try:
                        cliente_obj_id = ObjectId(cliente_id)
                        cliente_doc = clientes_usuarios_collection.find_one({"_id": cliente_obj_id})
                        cliente_nombre = cliente_doc.get("nombre", "Cliente desconocido") if cliente_doc else "Cliente desconocido"
                    except Exception:
                        cliente_nombre = "Cliente desconocido"
                    
                    conversaciones_por_cliente[cliente_id] = {
                        "cliente_id": cliente_id,
                        "cliente_nombre": cliente_nombre,
                        "pedido_id": pedido_id,
                        "mensajes": [],
                        "total_mensajes": 0,
                        "mensajes_no_leidos": 0,
                        "ultimo_mensaje": None
                    }
                
                # Convertir ObjectId a string
                mensaje["_id"] = str(mensaje["_id"])
                
                # Agregar mensaje a la conversación
                conversaciones_por_cliente[cliente_id]["mensajes"].append(mensaje)
                conversaciones_por_cliente[cliente_id]["total_mensajes"] += 1
                
                # Contar no leídos
                if not mensaje.get("leido", False):
                    conversaciones_por_cliente[cliente_id]["mensajes_no_leidos"] += 1
                
                # Actualizar último mensaje (usar fecha si existe, sino fecha_creacion)
                fecha = mensaje.get("fecha") or mensaje.get("fecha_creacion", "")
                if fecha:
                    ultimo_mensaje_actual = conversaciones_por_cliente[cliente_id]["ultimo_mensaje"]
                    fecha_ultimo = ultimo_mensaje_actual.get("fecha") or ultimo_mensaje_actual.get("fecha_creacion", "") if ultimo_mensaje_actual else ""
                    if not ultimo_mensaje_actual or fecha > fecha_ultimo:
                        conversaciones_por_cliente[cliente_id]["ultimo_mensaje"] = mensaje
        
        # Convertir a lista y ordenar por último mensaje (más reciente primero)
        conversaciones = list(conversaciones_por_cliente.values())
        conversaciones.sort(
            key=lambda x: (x["ultimo_mensaje"].get("fecha") or x["ultimo_mensaje"].get("fecha_creacion", "")) if x["ultimo_mensaje"] else "",
            reverse=True
        )
        
        # Devolver directamente el array (el frontend espera un array, no un objeto)
        return conversaciones
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR GET CONVERSACIONES SOPORTE: {str(e)}")
        import traceback
        print(f"ERROR GET CONVERSACIONES SOPORTE TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener conversaciones: {str(e)}")

@router.post("")
async def crear_mensaje(
    request_data: FastAPIRequest
):
    """
    Crear un nuevo mensaje.
    Acepta pedido_id con formato soporte_{cliente_id} para mensajes de soporte.
    Puede ser usado por administradores o clientes.
    """
    try:
        # Intentar obtener token de admin o cliente desde headers
        authorization = request_data.headers.get("authorization", "")
        token = None
        if authorization.startswith("Bearer "):
            token = authorization.replace("Bearer ", "")
        
        if not token:
            raise HTTPException(status_code=401, detail="Debes estar autenticado para enviar mensajes")
        
        # Determinar el remitente (admin o cliente)
        remitente_id = None
        remitente_nombre = None
        remitente_tipo = None
        
        # Intentar validar token como admin primero
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            
            if payload.get("rol") == "admin":
                user_doc = usuarios_collection.find_one({"_id": ObjectId(payload.get("id"))})
                if user_doc:
                    remitente_id = str(user_doc["_id"])
                    remitente_nombre = user_doc.get("usuario", "Administrador")
                    remitente_tipo = "admin"
            elif payload.get("rol") == "cliente":
                cliente_doc = clientes_usuarios_collection.find_one({"_id": ObjectId(payload.get("id"))})
                if cliente_doc:
                    remitente_id = str(cliente_doc["_id"])
                    remitente_nombre = cliente_doc.get("nombre", "Cliente")
                    remitente_tipo = "cliente"
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Error al validar token: {str(e)}")
        
        if not remitente_id:
            raise HTTPException(status_code=401, detail="Debes estar autenticado para enviar mensajes")
        
        # Obtener datos del request
        data = await request_data.json()
        
        # Usar datos del request si están presentes, sino usar datos del usuario/cliente
        remitente_id = data.get("remitente_id") or remitente_id
        remitente_nombre = data.get("remitente_nombre") or remitente_nombre
        remitente_tipo = data.get("remitente_tipo") or remitente_tipo
        
        # Validar que el mensaje no esté vacío
        mensaje_texto = data.get("mensaje", "").strip()
        if not mensaje_texto:
            raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío")
        
        # Validar pedido_id
        pedido_id = data.get("pedido_id", "").strip()
        if not pedido_id:
            raise HTTPException(status_code=400, detail="pedido_id es requerido")
        
        # Crear documento del mensaje
        fecha_iso = datetime.now().isoformat()
        mensaje_doc = {
            "pedido_id": pedido_id,
            "mensaje": mensaje_texto,
            "remitente_id": str(remitente_id),
            "remitente_nombre": remitente_nombre,
            "remitente_tipo": remitente_tipo,
            "leido": data.get("leido", False),
            "fecha": fecha_iso,  # Campo fecha para compatibilidad
            "fecha_creacion": fecha_iso  # Mantener para ordenamiento
        }
        
        # Insertar mensaje
        result = mensajes_collection.insert_one(mensaje_doc)
        mensaje_doc["_id"] = str(result.inserted_id)
        
        return {
            "message": "Mensaje creado exitosamente",
            "mensaje": mensaje_doc
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR CREAR MENSAJE: {str(e)}")
        import traceback
        print(f"ERROR CREAR MENSAJE TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al crear mensaje: {str(e)}")

@router.get("/pedido/{pedido_id}")
async def get_mensajes_conversacion(
    pedido_id: str,
    request: FastAPIRequest
):
    """
    Obtener todos los mensajes de una conversación de soporte.
    Formato: /mensajes/pedido/soporte_{cliente_id}
    """
    try:
        # Intentar obtener token
        authorization = request.headers.get("authorization", "")
        token = None
        if authorization.startswith("Bearer "):
            token = authorization.replace("Bearer ", "")
        
        if not token:
            raise HTTPException(status_code=401, detail="Debes estar autenticado para ver mensajes")
        
        # Verificar autenticación (admin o cliente)
        es_admin = False
        es_cliente = False
        current_user = None
        current_cliente = None
        
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("rol") == "admin":
                user_doc = usuarios_collection.find_one({"_id": ObjectId(payload.get("id"))})
                if user_doc:
                    es_admin = True
                    current_user = {
                        "id": str(user_doc["_id"]),
                        "rol": user_doc.get("rol", "admin")
                    }
            elif payload.get("rol") == "cliente":
                cliente_doc = clientes_usuarios_collection.find_one({"_id": ObjectId(payload.get("id"))})
                if cliente_doc:
                    es_cliente = True
                    current_cliente = {
                        "id": str(cliente_doc["_id"]),
                        "nombre": cliente_doc.get("nombre", "Cliente")
                    }
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Error al validar token: {str(e)}")
        
        if not es_admin and not es_cliente:
            raise HTTPException(status_code=401, detail="Debes estar autenticado para ver mensajes")
        
        # Si es conversación de soporte, verificar permisos
        if pedido_id.startswith("soporte_"):
            cliente_id_conversacion = pedido_id.replace("soporte_", "")
            
            # Si es cliente, solo puede ver sus propias conversaciones
            if es_cliente and current_cliente:
                # Comparar IDs como strings para evitar problemas de tipo
                cliente_id_actual = str(current_cliente.get("id", ""))
                cliente_id_conv = str(cliente_id_conversacion)
                if cliente_id_actual != cliente_id_conv:
                    raise HTTPException(status_code=403, detail="No puedes ver conversaciones de otros clientes")
        
        # Buscar mensajes de la conversación
        # Ordenar por fecha_creacion (más antiguos primero), o por fecha si existe
        try:
            mensajes = list(mensajes_collection.find({
                "pedido_id": pedido_id
            }).sort("fecha_creacion", 1))
        except Exception as e:
            print(f"ERROR BUSCANDO MENSAJES: {str(e)}")
            # Si hay error en la búsqueda, retornar array vacío en lugar de fallar
            return []
        
        # Normalizar estructura de respuesta
        mensajes_normalizados = []
        try:
            for mensaje in mensajes:
                # Convertir ObjectId a string de forma segura
                try:
                    mensaje_id = str(mensaje.get("_id", ""))
                except Exception:
                    mensaje_id = ""
                
                # Normalizar campos: usar fecha si existe, sino fecha_creacion
                fecha = mensaje.get("fecha") or mensaje.get("fecha_creacion")
                if not fecha:
                    fecha = datetime.now().isoformat()
                
                mensaje_normalizado = {
                    "_id": mensaje_id,
                    "pedido_id": str(mensaje.get("pedido_id", pedido_id)),
                    "remitente_id": str(mensaje.get("remitente_id", "")),
                    "remitente_tipo": str(mensaje.get("remitente_tipo", "")),
                    "remitente_nombre": str(mensaje.get("remitente_nombre", "")),
                    "mensaje": str(mensaje.get("mensaje", "")),
                    "fecha": str(fecha),
                    "leido": bool(mensaje.get("leido", False))
                }
                mensajes_normalizados.append(mensaje_normalizado)
        except Exception as e:
            print(f"ERROR NORMALIZANDO MENSAJES: {str(e)}")
            # Si hay error normalizando, retornar array vacío
            return []
        
        # Si no hay mensajes, retornar array vacío (no 404)
        return mensajes_normalizados
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR GET MENSAJES: {str(e)}")
        import traceback
        print(f"ERROR GET MENSAJES TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener mensajes: {str(e)}")

@router.get("/pedido/{pedido_id}/no-leidos")
async def contar_mensajes_no_leidos(
    pedido_id: str,
    request: FastAPIRequest
):
    """
    Contar mensajes no leídos de una conversación de soporte.
    Formato: /mensajes/pedido/soporte_{cliente_id}/no-leidos
    """
    try:
        # Intentar obtener token
        authorization = request.headers.get("authorization", "")
        token = None
        if authorization.startswith("Bearer "):
            token = authorization.replace("Bearer ", "")
        
        if not token:
            raise HTTPException(status_code=401, detail="Debes estar autenticado para ver mensajes")
        
        # Verificar autenticación (admin o cliente)
        es_admin = False
        es_cliente = False
        current_user = None
        current_cliente = None
        
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            if payload.get("rol") == "admin":
                user_doc = usuarios_collection.find_one({"_id": ObjectId(payload.get("id"))})
                if user_doc:
                    es_admin = True
                    current_user = {
                        "id": str(user_doc["_id"]),
                        "rol": user_doc.get("rol", "admin")
                    }
            elif payload.get("rol") == "cliente":
                cliente_doc = clientes_usuarios_collection.find_one({"_id": ObjectId(payload.get("id"))})
                if cliente_doc:
                    es_cliente = True
                    current_cliente = {
                        "id": str(cliente_doc["_id"]),
                        "nombre": cliente_doc.get("nombre", "Cliente")
                    }
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Token inválido o expirado")
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Error al validar token: {str(e)}")
        
        if not es_admin and not es_cliente:
            raise HTTPException(status_code=401, detail="Debes estar autenticado para ver mensajes")
        
        # Si es conversación de soporte, verificar permisos
        if pedido_id.startswith("soporte_"):
            cliente_id_conversacion = pedido_id.replace("soporte_", "")
            
            # Si es cliente, solo puede ver sus propias conversaciones
            if es_cliente and current_cliente and current_cliente.get("id") != cliente_id_conversacion:
                raise HTTPException(status_code=403, detail="No puedes ver conversaciones de otros clientes")
        
        # Contar mensajes no leídos
        count = mensajes_collection.count_documents({
            "pedido_id": pedido_id,
            "leido": False
        })
        
        return {
            "pedido_id": pedido_id,
            "mensajes_no_leidos": count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR CONTAR NO LEIDOS: {str(e)}")
        import traceback
        print(f"ERROR CONTAR NO LEIDOS TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al contar mensajes no leídos: {str(e)}")

