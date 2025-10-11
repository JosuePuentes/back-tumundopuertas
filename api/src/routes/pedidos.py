from typing import List, Optional, Union
from fastapi import APIRouter, HTTPException, Body, Depends
from bson import ObjectId
from datetime import datetime, timedelta, timezone
from ..config.mongodb import pedidos_collection, db
from ..models.authmodels import Pedido
from ..auth.auth import get_current_user

router = APIRouter()
metodos_pago_collection = db["metodos_pago"]

def obtener_siguiente_modulo(orden_actual: int) -> str:
    """Determinar el siguiente módulo según el orden actual"""
    flujo = {
        1: "masillar",      # Herrería → Masillar
        2: "preparar",      # Masillar → Preparar  
        3: "listo_facturar" # Preparar → Listo para Facturar
    }
    return flujo.get(orden_actual, "completado")

@router.get("/all/")
async def get_all_pedidos():
    pedidos = list(pedidos_collection.find())
    for pedido in pedidos:
        pedido["_id"] = str(pedido["_id"])
    return pedidos

@router.get("/test-terminar")
async def test_terminar_endpoint():
    """Endpoint de prueba para verificar que el servidor está funcionando"""
    return {
        "message": "Endpoint de prueba funcionando",
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    }

@router.get("/debug-seguimiento/{pedido_id}")
async def debug_seguimiento_pedido(pedido_id: str):
    """Endpoint para debuggear la estructura de seguimiento de un pedido"""
    try:
        pedido_obj_id = ObjectId(pedido_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"pedido_id no es un ObjectId válido: {str(e)}")
    
    pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    seguimiento = pedido.get("seguimiento", [])
    
    procesos_info = []
    for i, sub in enumerate(seguimiento):
        proceso_info = {
            "indice": i,
            "orden": sub.get("orden"),
            "estado": sub.get("estado"),
            "nombre": sub.get("nombre", "SIN_NOMBRE"),
            "asignaciones_count": len(sub.get("asignaciones_articulos", [])),
            "asignaciones": []
        }
        
        # Detalles de asignaciones
        for j, asignacion in enumerate(sub.get("asignaciones_articulos", [])):
            asignacion_info = {
                "indice": j,
                "itemId": asignacion.get("itemId"),
                "empleadoId": asignacion.get("empleadoId"),
                "estado": asignacion.get("estado"),
                "estado_subestado": asignacion.get("estado_subestado")
            }
            proceso_info["asignaciones"].append(asignacion_info)
        
        procesos_info.append(proceso_info)
    
    return {
        "pedido_id": pedido_id,
        "cliente_nombre": pedido.get("cliente_nombre", "SIN_NOMBRE"),
        "total_procesos": len(seguimiento),
        "procesos": procesos_info
    }

@router.put("/test-terminar-put")
async def test_terminar_put_endpoint():
    """Endpoint de prueba PUT para verificar CORS"""
    return {
        "message": "Endpoint PUT de prueba funcionando",
        "status": "ok",
        "method": "PUT",
        "timestamp": datetime.now().isoformat()
    }

@router.put("/test-terminar-simple")
async def test_terminar_simple():
    """Endpoint de prueba simple para verificar que el servidor funciona"""
    try:
        return {
            "message": "Endpoint simple funcionando",
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "test": "simple"
        }
    except Exception as e:
        print(f"ERROR TEST SIMPLE: {e}")
        import traceback
        print(f"ERROR TEST SIMPLE TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error en test simple: {str(e)}")

@router.get("/all/{orden}")
async def get_all_pedidos_por_orden(orden: str):
    pedidos = list(pedidos_collection.find({"orden": orden}))
    for pedido in pedidos:
        pedido["_id"] = str(pedido["_id"])
    return pedidos

@router.get("/id/{pedido_id}/")
async def get_pedido(pedido_id: str):
    try:
        pedido_obj_id = ObjectId(pedido_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"pedido_id no es un ObjectId válido: {str(e)}")
    try:
        pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando la base de datos: {str(e)}")
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    pedido["_id"] = str(pedido["_id"])
    return pedido

@router.post("/")
async def create_pedido(pedido: Pedido, user: dict = Depends(get_current_user)):
    pedido.creado_por = user.get("usuario")
    print("Creando pedido:", pedido)
    
    # Insertar el pedido
    result = pedidos_collection.insert_one(pedido.dict())
    pedido_id = str(result.inserted_id)
    
    # Si hay abonos iniciales en el historial_pagos, incrementar el saldo de los métodos de pago
    if pedido.historial_pagos:
        print(f"DEBUG CREAR PEDIDO: Procesando {len(pedido.historial_pagos)} abonos iniciales")
        for pago in pedido.historial_pagos:
            if pago.metodo and pago.monto and pago.monto > 0:
                print(f"DEBUG CREAR PEDIDO: Procesando abono de {pago.monto} con método {pago.metodo}")
                try:
                    # Buscar el método de pago por _id o por nombre
                    metodo_pago = None
                    
                    # Intentar buscar por ObjectId primero
                    try:
                        metodo_pago = metodos_pago_collection.find_one({"_id": ObjectId(pago.metodo)})
                        print(f"DEBUG CREAR PEDIDO: Buscando por ObjectId: {pago.metodo}")
                    except:
                        print(f"DEBUG CREAR PEDIDO: No es ObjectId válido, buscando por nombre: {pago.metodo}")
                    
                    # Si no se encontró por ObjectId, buscar por nombre
                    if not metodo_pago:
                        metodo_pago = metodos_pago_collection.find_one({"nombre": pago.metodo})
                        print(f"DEBUG CREAR PEDIDO: Buscando por nombre: {pago.metodo}")
                    
                    if metodo_pago:
                        saldo_actual = metodo_pago.get("saldo", 0.0)
                        nuevo_saldo = saldo_actual + pago.monto
                        print(f"DEBUG CREAR PEDIDO: Incrementando saldo de {saldo_actual} a {nuevo_saldo} para método '{metodo_pago.get('nombre', 'SIN_NOMBRE')}'")
                        
                        result_update = metodos_pago_collection.update_one(
                            {"_id": metodo_pago["_id"]},
                            {"$set": {"saldo": nuevo_saldo}}
                        )
                        print(f"DEBUG CREAR PEDIDO: Resultado de actualización: {result_update.modified_count} documentos modificados")
                    else:
                        print(f"DEBUG CREAR PEDIDO: Método de pago '{pago.metodo}' no encontrado ni por ID ni por nombre")
                except Exception as e:
                    print(f"DEBUG CREAR PEDIDO: Error al actualizar saldo: {e}")
                    import traceback
                    print(f"DEBUG CREAR PEDIDO: Traceback: {traceback.format_exc()}")
    
    return {"message": "Pedido creado correctamente", "id": pedido_id, "cliente_nombre": pedido.cliente_nombre}

@router.put("/subestados/")
async def update_subestados(
    pedido_id: str = Body(...),
    numero_orden: str = Body(...),
    tipo_fecha: str = Body(...),  # "inicio" o "fin" o ""
    estado: str = Body(...),
    asignaciones: list = Body(None),  # lista de asignaciones por artículo
    estado_general: str = Body(None),
):
    # Validaciones iniciales
    print(f"Pedido: {pedido_id}, Asignaciones: {asignaciones}, Estado General: {estado_general}, Tipo Fecha: {tipo_fecha}")
    pedido_id = ObjectId(pedido_id)

    if not pedido_id:
        raise HTTPException(status_code=400, detail="Falta el pedido_id")
    if not numero_orden:
        raise HTTPException(status_code=400, detail="Falta el numero_orden")
    if tipo_fecha not in ["inicio", "fin", ""]:
        raise HTTPException(status_code=400, detail="tipo_fecha debe ser 'inicio', 'fin' o vacio")
    if not estado:
        raise HTTPException(status_code=400, detail="Falta el estado")

    pedido = pedidos_collection.find_one({"_id": pedido_id})
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    seguimiento = pedido.get("seguimiento", [])
    if not isinstance(seguimiento, list) or not seguimiento:
        raise HTTPException(status_code=400, detail="El pedido no tiene seguimiento válido")

    actualizado = False
    error_subestado = None
    for sub in seguimiento:
        if str(sub.get("orden")) == numero_orden:
            try:
                sub["estado"] = estado
                # Solo actualizar fecha si tipo_fecha es "inicio" o "fin"
                if tipo_fecha == "inicio":
                    sub["fecha_inicio"] = datetime.now().isoformat()
                elif tipo_fecha == "fin":
                    sub["fecha_fin"] = datetime.now().isoformat()
                # Guardar asignaciones por artículo en el subestado
                if asignaciones is not None:
                    sub["asignaciones_articulos"] = asignaciones
                actualizado = True
            except Exception as e:
                error_subestado = str(e)
            break
    if error_subestado:
        raise HTTPException(status_code=500, detail=f"Error actualizando subestado: {error_subestado}")
    if not actualizado:
        raise HTTPException(status_code=400, detail="Subestado no encontrado")
    # Actualizar estado_general si se envía
    update_fields = {"seguimiento": seguimiento}
    if estado_general is not None:
        update_fields["estado_general"] = estado_general
    try:
        result = pedidos_collection.update_one(
            {"_id": pedido_id},
            {"$set": update_fields}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error actualizando pedido: {str(e)}")
    if result.matched_count == 0:
        raise HTTPException(status_code=400, detail="Pedido no encontrado al actualizar")
    return {"message": "Subestado actualizado correctamente"}

@router.get("/herreria/")
async def get_pedidos_herreria():
    pedidos = list(pedidos_collection.find({"estado_general": "orden1"}))
    for pedido in pedidos:
        pedido["_id"] = str(pedido["_id"])
    return pedidos


@router.put("/finalizar/")
async def finalizar_pedido(
    pedido_id: str = Body(...),
    numero_orden: str = Body(...),
    nuevo_estado_general: str = Body(...)
):
    # Validaciones iniciales
    try:
        pedido_obj_id = ObjectId(pedido_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"pedido_id no es un ObjectId válido: {str(e)}")
    if not numero_orden:
        raise HTTPException(status_code=400, detail="Falta el numero_orden")
    if not nuevo_estado_general:
        raise HTTPException(status_code=400, detail="Falta el nuevo estado_general")

    pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    seguimiento = pedido.get("seguimiento", [])
    if not isinstance(seguimiento, list) or not seguimiento:
        raise HTTPException(status_code=400, detail="El pedido no tiene seguimiento válido")

    actualizado = False
    error_subestado = None
    for sub in seguimiento:
        if str(sub.get("orden")) == numero_orden:
            try:
                sub["estado"] = "terminado"
                sub["fecha_fin"] = datetime.now().isoformat()
                # Agregar fecha_fin a cada asignación de artículo si existen
                if "asignaciones_articulos" in sub and isinstance(sub["asignaciones_articulos"], list):
                    for asignacion in sub["asignaciones_articulos"]:
                        asignacion["fecha_fin"] = sub["fecha_fin"]
                actualizado = True
            except Exception as e:
                error_subestado = str(e)
            break
    if error_subestado:
        raise HTTPException(status_code=500, detail=f"Error actualizando subestado: {error_subestado}")
    if not actualizado:
        raise HTTPException(status_code=400, detail="Subestado no encontrado")
    try:
        result = pedidos_collection.update_one(
            {"_id": pedido_obj_id},
            {"$set": {"seguimiento": seguimiento, "estado_general": nuevo_estado_general}}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error actualizando pedido: {str(e)}")
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pedido no encontrado al actualizar")
    return {"message": "Pedido finalizado correctamente"}

@router.get("/produccion/ruta")
async def get_pedidos_ruta_produccion():
    # Devuelve todos los pedidos en estado_general orden1, orden2, orden3
    pedidos = list(pedidos_collection.find({"estado_general": {"$in": ["orden1", "orden2", "orden3","pendiente","orden4","orden5","orden6","entregado"]}}))
    for pedido in pedidos:
        pedido["_id"] = str(pedido["_id"])
    return pedidos

from fastapi import Query

@router.get("/estado/")
async def get_pedidos_por_estado(estado_general: list[str] = Query(..., description="Uno o varios estados separados por coma")):
    # Si solo se pasa uno, FastAPI lo convierte en lista de un elemento
    filtro = {"estado_general": {"$in": estado_general}}
    pedidos = list(pedidos_collection.find(filtro))
    for pedido in pedidos:
        pedido["_id"] = str(pedido["_id"])
    return pedidos

@router.get("/comisiones/produccion/terminadas/")
async def get_empleados_comisiones_produccion_terminadas(
    fecha_inicio: str = None,
    fecha_fin: str = None
):
    # Parsear fechas si se proporcionan
    filtro_fecha = None
    if fecha_inicio and fecha_fin:
        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d")
            fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d")
            filtro_fecha = (fecha_inicio_dt, fecha_fin_dt)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Formato de fecha inválido: {str(e)}")
    pedidos = list(pedidos_collection.find({}))
    resultado = {}
    for pedido in pedidos:
        pedido_id = str(pedido.get("_id"))
        seguimiento = pedido.get("seguimiento", [])
        for sub in seguimiento:
            if sub.get("estado") == "terminado" and "asignaciones_articulos" in sub:
                asignaciones = sub.get("asignaciones_articulos")
                if isinstance(asignaciones, list):
                    for idx, asignacion in enumerate(asignaciones):
                        empleado_id = asignacion.get("empleadoId")
                        nombre_empleado = asignacion.get("nombreempleado")
                        item_id = asignacion.get("itemId")
                        descripcion_item = asignacion.get("descripcionitem")
                        costo_produccion = asignacion.get("costoproduccion")
                        key = f"{item_id}-{idx}"
                        # Filtrar por fecha si corresponde
                        if filtro_fecha:
                            fecha_fin_asignacion = asignacion.get("fecha_fin")
                            if not fecha_fin_asignacion:
                                continue
                            try:
                                fecha_fin_dt_asignacion = datetime.strptime(fecha_fin_asignacion[:10], "%Y-%m-%d")
                            except Exception:
                                continue
                            if not (filtro_fecha[0] <= fecha_fin_dt_asignacion <= filtro_fecha[1]):
                                continue
                        asignacion_data = {
                            "pedido_id": pedido_id,
                            "orden": sub.get("orden"),
                            "nombre_subestado": sub.get("nombre_subestado"),
                            "estado_subestado": sub.get("estado"),
                            "fecha_inicio_subestado": sub.get("fecha_inicio"),
                            "fecha_fin_subestado": sub.get("fecha_fin"),
                            "item_id": item_id,
                            "key": key,
                            "empleadoId": empleado_id,
                            "nombreempleado": nombre_empleado,
                            "fecha_inicio": asignacion.get("fecha_inicio"),
                            "estado": asignacion.get("estado"),
                            "descripcionitem": descripcion_item,
                            "costoproduccion": costo_produccion,
                            "fecha_fin": asignacion.get("fecha_fin"),
                            "cantidad": next((item.get("cantidad") for item in pedido.get("items", []) if item.get("id") == item_id), 1),
                            "precio_item": next((item.get("precio") for item in pedido.get("items", []) if item.get("id") == item_id), 0)
                        }
                        if empleado_id not in resultado:
                            resultado[empleado_id] = {
                                "empleado_id": empleado_id,
                                "nombre_empleado": nombre_empleado,
                                "asignaciones": []
                            }
                        resultado[empleado_id]["asignaciones"].append(asignacion_data)
    # Devuelve como lista
    return list(resultado.values())

@router.get("/comisiones/produccion/pendientes/")
async def get_asignaciones_pendientes_empleado(empleado_id: str):
    pedidos = list(pedidos_collection.find({}))
    resultado = []
    for pedido in pedidos:
        pedido_id = str(pedido.get("_id"))
        seguimiento = pedido.get("seguimiento", [])
        for sub in seguimiento:
            if "asignaciones_articulos" in sub:
                asignaciones = sub.get("asignaciones_articulos")
                if isinstance(asignaciones, list):
                    for asignacion in asignaciones:
                        if asignacion.get("empleadoId") == empleado_id and asignacion.get("estado") != "terminado":
                            asignacion_data = {
                                "pedido_id": pedido_id,
                                "orden": sub.get("orden"),
                                "nombre_subestado": sub.get("nombre_subestado"),
                                "estado_subestado": sub.get("estado"),
                                "fecha_inicio_subestado": sub.get("fecha_inicio"),
                                "fecha_fin_subestado": sub.get("fecha_fin"),
                                "item_id": asignacion.get("itemId"),
                                "empleadoId": asignacion.get("empleadoId"),
                                "nombreempleado": asignacion.get("nombreempleado"),
                                "fecha_inicio": asignacion.get("fecha_inicio"),
                                "estado": asignacion.get("estado"),
                                "descripcionitem": asignacion.get("descripcionitem"),
                                "costoproduccion": asignacion.get("costoproduccion"),
                                "fecha_fin": asignacion.get("fecha_fin"),
                            }
                            resultado.append(asignacion_data)
    return resultado

@router.get("/comisiones/produccion/terminadas/empleado/")
async def get_comisiones_produccion_terminadas_por_empleado(
    empleado_id: str,
    fecha_inicio: str = None,
    fecha_fin: str = None
):
    # Parsear fechas si se proporcionan
    filtro_fecha = None
    if fecha_inicio and fecha_fin:
        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d")
            fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d")
            filtro_fecha = (fecha_inicio_dt, fecha_fin_dt)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Formato de fecha inválido: {str(e)}")
    pedidos = list(pedidos_collection.find({}))
    asignaciones_empleado = []
    for pedido in pedidos:
        pedido_id = str(pedido.get("_id"))
        seguimiento = pedido.get("seguimiento", [])
        items = pedido.get("items", [])
        for sub in seguimiento:
            if sub.get("estado") == "terminado" and "asignaciones_articulos" in sub:
                asignaciones = sub.get("asignaciones_articulos")
                if isinstance(asignaciones, list):
                    for idx, asignacion in enumerate(asignaciones):
                        if asignacion.get("empleadoId") != empleado_id:
                            continue
                        # Filtrar por fecha si corresponde
                        if filtro_fecha:
                            fecha_fin_asignacion = asignacion.get("fecha_fin")
                            if not fecha_fin_asignacion:
                                continue
                            try:
                                fecha_fin_dt_asignacion = datetime.strptime(fecha_fin_asignacion[:10], "%Y-%m-%d")
                            except Exception:
                                continue
                            if not (filtro_fecha[0] <= fecha_fin_dt_asignacion <= filtro_fecha[1]):
                                continue
                        # Buscar el precio del item
                        precio_item = 0
                        print("Buscando precio para item_id:", asignacion.get("itemId"))
                        item_id = asignacion.get("itemId")
                        for item in items:
                            if item.get("id") == item_id:
                                precio_item = item.get("precio")
                                break
                        asignacion_data = {
                            "pedido_id": pedido_id,
                            "orden": sub.get("orden"),
                            "nombre_subestado": sub.get("nombre_subestado"),
                            "estado_subestado": sub.get("estado"),
                            "fecha_inicio_subestado": sub.get("fecha_inicio"),
                            "fecha_fin_subestado": sub.get("fecha_fin"),
                            "item_id": item_id,
                            "key": f"{item_id}-{idx}",
                            "empleadoId": asignacion.get("empleadoId"),
                            "nombreempleado": asignacion.get("nombreempleado"),
                            "fecha_inicio": asignacion.get("fecha_inicio"),
                            "estado": asignacion.get("estado"),
                            "descripcionitem": descripcion_item,
                            "costoproduccion": asignacion.get("costoproduccion"),
                            "fecha_fin": asignacion.get("fecha_fin"),
                            
                        }
                        asignaciones_empleado.append(asignacion_data)
    return asignaciones_empleado

@router.get("/comisiones/produccion/enproceso/")
async def get_asignaciones_enproceso_empleado(empleado_id: str = None, modulo: str = None):
    print(f"DEBUG COMISIONES: empleado_id={empleado_id}, modulo={modulo}")
    
    # Mapear módulos a órdenes
    modulo_orden = {
        "herreria": 1,
        "masillar": 2, 
        "preparar": 3,
        "listo_facturar": 4
    }
    
    orden_filtro = None
    if modulo:
        orden_filtro = modulo_orden.get(modulo)
        if not orden_filtro:
            raise HTTPException(status_code=400, detail=f"Módulo no válido: {modulo}")
        print(f"DEBUG COMISIONES: Filtrando por módulo {modulo} (orden {orden_filtro})")
    
    pedidos = list(pedidos_collection.find({}))
    resultado = []
    for pedido in pedidos:
        pedido_id = str(pedido.get("_id"))
        seguimiento = pedido.get("seguimiento", [])
        for sub in seguimiento:
            # Filtrar por módulo si se especifica
            if modulo and sub.get("orden") != orden_filtro:
                continue
                
            if "asignaciones_articulos" in sub:
                asignaciones = sub.get("asignaciones_articulos")
                if isinstance(asignaciones, list):
                    for asignacion in asignaciones:
                        # Mostrar tanto asignaciones en_proceso como terminadas
                        filtro_empleado = True
                        if empleado_id:
                            filtro_empleado = asignacion.get("empleadoId") == empleado_id
                        
                        if (
                            filtro_empleado and
                            asignacion.get("estado") in ["en_proceso", "terminado"]
                        ):
                            # Buscar el detalleitem en pedido["items"] por itemId
                            detalleitem = None
                            for item in pedido.get("items", []):
                                if item.get("id") == asignacion.get("itemId"):
                                    detalleitem = item.get("detalleitem")
                                    break
                            # Obtener info del cliente
                            imagenes = []
                            for item in pedido.get("items", []):
                                if item.get("id") == asignacion.get("itemId"):
                                    imagenes = item.get("imagenes", [])
                                    break
                            cliente_info = {
                                "cliente_id": pedido.get("cliente_id"),
                                "cliente_nombre": pedido.get("cliente_nombre"),
                                "cliente_telefono": pedido.get("cliente_telefono"),
                                "cliente_direccion": pedido.get("cliente_direccion"),
                                "cliente_email": pedido.get("cliente_email"),
                                # Agrega aquí otros campos relevantes del cliente si existen
                            }
                            # Determinar el módulo basado en el orden
                            modulo_nombre = "desconocido"
                            for mod, ord in modulo_orden.items():
                                if ord == sub.get("orden"):
                                    modulo_nombre = mod
                                    break
                            
                            asignacion_data = {
                                "pedido_id": pedido_id,
                                "orden": sub.get("orden"),
                                "modulo": modulo_nombre,
                                "nombre_subestado": sub.get("nombre_subestado"),
                                "estado_subestado": sub.get("estado"),
                                "fecha_inicio_subestado": sub.get("fecha_inicio"),
                                "fecha_fin_subestado": sub.get("fecha_fin"),
                                "item_id": asignacion.get("itemId"),
                                "empleadoId": asignacion.get("empleadoId"),
                                "nombreempleado": asignacion.get("nombreempleado"),
                                "fecha_inicio": asignacion.get("fecha_inicio"),
                                "estado": asignacion.get("estado"),
                                "descripcionitem": asignacion.get("descripcionitem"),
                                "costoproduccion": asignacion.get("costoproduccion"),
                                "fecha_fin": asignacion.get("fecha_fin"),
                                "detalleitem": detalleitem,
                                "cliente": cliente_info,
                                "imagenes": imagenes}
                            resultado.append(asignacion_data)
    
    print(f"DEBUG COMISIONES: Encontradas {len(resultado)} asignaciones")
    print(f"DEBUG COMISIONES: Filtros aplicados - empleado_id: {empleado_id}, modulo: {modulo}")
    
    return {
        "asignaciones": resultado,
        "total": len(resultado),
        "filtros": {
            "empleado_id": empleado_id,
            "modulo": modulo
        },
        "success": True
    }

# Endpoints adicionales para compatibilidad con frontend
@router.get("/comisiones/produccion/enproceso")
async def get_asignaciones_enproceso_empleado_sin_slash(empleado_id: str = None, modulo: str = None):
    """Endpoint sin barra final para compatibilidad"""
    return await get_asignaciones_enproceso_empleado(empleado_id, modulo)

@router.get("/comisiones/produccion")
async def get_comisiones_produccion_general():
    """Endpoint general para comisiones de producción"""
    try:
        print(f"DEBUG COMISIONES GENERAL: Iniciando endpoint general")
        
        # Obtener estadísticas generales
        pipeline = [
            {
                "$match": {
                    "seguimiento": {
                        "$elemMatch": {
                            "asignaciones_articulos": {"$exists": True, "$ne": []}
                        }
                    }
                }
            },
            {
                "$unwind": "$seguimiento"
            },
            {
                "$match": {
                    "seguimiento.asignaciones_articulos": {"$exists": True, "$ne": []}
                }
            },
            {
                "$unwind": "$seguimiento.asignaciones_articulos"
            },
            {
                "$project": {
                    "modulo": {
                        "$switch": {
                            "branches": [
                                {"case": {"$eq": ["$seguimiento.orden", 1]}, "then": "herreria"},
                                {"case": {"$eq": ["$seguimiento.orden", 2]}, "then": "masillar"},
                                {"case": {"$eq": ["$seguimiento.orden", 3]}, "then": "preparar"},
                                {"case": {"$eq": ["$seguimiento.orden", 4]}, "then": "listo_facturar"}
                            ],
                            "default": "desconocido"
                        }
                    },
                    "estado": "$seguimiento.asignaciones_articulos.estado"
                }
            },
            {
                "$match": {
                    "modulo": {"$ne": "desconocido"}
                }
            },
            {
                "$group": {
                    "_id": {
                        "modulo": "$modulo",
                        "estado": "$estado"
                    },
                    "count": {"$sum": 1}
                }
            }
        ]
        
        estadisticas = list(pedidos_collection.aggregate(pipeline))
        
        return {
            "estadisticas": estadisticas,
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR COMISIONES GENERAL: Error al obtener estadísticas: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener estadísticas: {str(e)}")

@router.get("/produccion/enproceso")
async def get_produccion_enproceso():
    """Endpoint para producción en proceso"""
    try:
        collections = get_collections()
        
        pipeline = [
            {
                "$match": {
                    "seguimiento": {
                        "$elemMatch": {
                            "asignaciones_articulos": {"$exists": True, "$ne": []}
                        }
                    }
                }
            },
            {
                "$unwind": "$seguimiento"
            },
            {
                "$match": {
                    "seguimiento.asignaciones_articulos": {"$exists": True, "$ne": []}
                }
            },
            {
                "$unwind": "$seguimiento.asignaciones_articulos"
            },
            {
                "$project": {
                    "_id": 1,
                    "cliente_nombre": 1,
                    "pedido_id": "$_id",
                    "item_id": "$seguimiento.asignaciones_articulos.itemId",
                    "empleado_id": "$seguimiento.asignaciones_articulos.empleadoId",
                    "empleado_nombre": "$seguimiento.asignaciones_articulos.nombreempleado",
                    "modulo": {
                        "$switch": {
                            "branches": [
                                {"case": {"$eq": ["$seguimiento.orden", 1]}, "then": "herreria"},
                                {"case": {"$eq": ["$seguimiento.orden", 2]}, "then": "masillar"},
                                {"case": {"$eq": ["$seguimiento.orden", 3]}, "then": "preparar"},
                                {"case": {"$eq": ["$seguimiento.orden", 4]}, "then": "listo_facturar"}
                            ],
                            "default": "desconocido"
                        }
                    },
                    "estado": "$seguimiento.asignaciones_articulos.estado",
                    "descripcionitem": "$seguimiento.asignaciones_articulos.descripcionitem",
                    "costo_produccion": "$seguimiento.asignaciones_articulos.costoproduccion",
                    "orden": "$seguimiento.orden"
                }
            },
            {
                "$match": {
                    "estado": {"$in": ["en_proceso", "pendiente"]},
                    "modulo": {"$ne": "desconocido"}
                }
            },
            {
                "$sort": {"orden": 1, "pedido_id": 1}
            }
        ]
        
        asignaciones = list(pedidos_collection.aggregate(pipeline))
        
        # Convertir ObjectId a string
        for asignacion in asignaciones:
            asignacion["pedido_id"] = str(asignacion["pedido_id"])
            asignacion["item_id"] = str(asignacion["item_id"])
            if asignacion.get("_id"):
                asignacion["_id"] = str(asignacion["_id"])
        
        return {
            "asignaciones": asignaciones,
            "total": len(asignaciones),
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR PRODUCCION ENPROCESO: Error al obtener datos: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener datos: {str(e)}")

@router.get("/enproceso")
async def get_pedidos_enproceso():
    """Endpoint para pedidos en proceso"""
    try:
        pedidos = list(pedidos_collection.find({
            "estado_general": {"$in": ["en_proceso", "pendiente"]}
        }))
        
        # Convertir ObjectId a string
        for pedido in pedidos:
            pedido["_id"] = str(pedido["_id"])
        
        return {
            "pedidos": pedidos,
            "total": len(pedidos),
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR PEDIDOS ENPROCESO: Error al obtener pedidos: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener pedidos: {str(e)}")

@router.get("/debug/asignaciones-empleados")
async def debug_asignaciones_empleados():
    """Endpoint de debug para verificar asignaciones por empleado"""
    try:
        print(f"DEBUG EMPLEADOS: Analizando asignaciones por empleado")
        
        pipeline = [
            {
                "$match": {
                    "seguimiento": {
                        "$elemMatch": {
                            "asignaciones_articulos": {"$exists": True, "$ne": []}
                        }
                    }
                }
            },
            {
                "$unwind": "$seguimiento"
            },
            {
                "$match": {
                    "seguimiento.asignaciones_articulos": {"$exists": True, "$ne": []}
                }
            },
            {
                "$unwind": "$seguimiento.asignaciones_articulos"
            },
            {
                "$project": {
                    "pedido_id": "$_id",
                    "item_id": "$seguimiento.asignaciones_articulos.itemId",
                    "empleado_id": "$seguimiento.asignaciones_articulos.empleadoId",
                    "empleado_nombre": "$seguimiento.asignaciones_articulos.nombreempleado",
                    "modulo": {
                        "$switch": {
                            "branches": [
                                {"case": {"$eq": ["$seguimiento.orden", 1]}, "then": "herreria"},
                                {"case": {"$eq": ["$seguimiento.orden", 2]}, "then": "masillar"},
                                {"case": {"$eq": ["$seguimiento.orden", 3]}, "then": "preparar"},
                                {"case": {"$eq": ["$seguimiento.orden", 4]}, "then": "listo_facturar"}
                            ],
                            "default": "desconocido"
                        }
                    },
                    "estado": "$seguimiento.asignaciones_articulos.estado",
                    "descripcionitem": "$seguimiento.asignaciones_articulos.descripcionitem"
                }
            },
            {
                "$match": {
                    "estado": {"$in": ["en_proceso", "pendiente"]},
                    "modulo": {"$ne": "desconocido"}
                }
            },
            {
                "$group": {
                    "_id": "$empleado_id",
                    "empleado_nombre": {"$first": "$empleado_nombre"},
                    "total_asignaciones": {"$sum": 1},
                    "modulos": {"$addToSet": "$modulo"},
                    "asignaciones": {
                        "$push": {
                            "pedido_id": "$pedido_id",
                            "item_id": "$item_id",
                            "modulo": "$modulo",
                            "estado": "$estado",
                            "descripcionitem": "$descripcionitem"
                        }
                    }
                }
            },
            {
                "$sort": {"total_asignaciones": -1}
            }
        ]
        
        empleados_con_asignaciones = list(pedidos_collection.aggregate(pipeline))
        
        # Convertir ObjectId a string
        for empleado in empleados_con_asignaciones:
            if empleado.get("_id"):
                empleado["empleado_id"] = str(empleado["_id"])
                del empleado["_id"]
            
            for asignacion in empleado.get("asignaciones", []):
                asignacion["pedido_id"] = str(asignacion["pedido_id"])
                asignacion["item_id"] = str(asignacion["item_id"])
        
        # Estadísticas generales
        total_con_empleado = sum(1 for emp in empleados_con_asignaciones if emp.get("empleado_id"))
        total_sin_empleado = len(empleados_con_asignaciones) - total_con_empleado
        
        print(f"DEBUG EMPLEADOS: Encontrados {len(empleados_con_asignaciones)} empleados con asignaciones")
        print(f"DEBUG EMPLEADOS: Con empleado asignado: {total_con_empleado}")
        print(f"DEBUG EMPLEADOS: Sin empleado asignado: {total_sin_empleado}")
        
        return {
            "empleados_con_asignaciones": empleados_con_asignaciones,
            "estadisticas": {
                "total_empleados": len(empleados_con_asignaciones),
                "con_empleado_asignado": total_con_empleado,
                "sin_empleado_asignado": total_sin_empleado
            },
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR DEBUG EMPLEADOS: Error al analizar empleados: {e}")
        raise HTTPException(status_code=500, detail=f"Error al analizar empleados: {str(e)}")

@router.get("/filtrar/por-fecha/")
async def get_pedidos_por_fecha(fecha_inicio: str = None, fecha_fin: str = None):
    filtro_fecha = None
    if fecha_inicio and fecha_fin:
        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d")
            fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d")
            filtro_fecha = (fecha_inicio_dt, fecha_fin_dt)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Formato de fecha inválido: {str(e)}")
    pedidos = list(pedidos_collection.find({}))
    pedidos_filtrados = []
    for pedido in pedidos:
        fecha_creacion = pedido.get("fecha_creacion")
        if filtro_fecha and fecha_creacion:
            try:
                fecha_creacion_dt = datetime.strptime(fecha_creacion[:10], "%Y-%m-%d")
            except Exception:
                continue
            if filtro_fecha[0] <= fecha_creacion_dt <= filtro_fecha[1]:
                pedido["_id"] = str(pedido["_id"])
                pedidos_filtrados.append(pedido)
        else:
            pedido["_id"] = str(pedido["_id"])
            pedidos_filtrados.append(pedido)
    return pedidos_filtrados

@router.put("/actualizar-estado-general/")
async def actualizar_estado_general_pedido(
    pedido_id: str = Body(...),
    nuevo_estado_general: str = Body(...)
):
    try:
        pedido_obj_id = ObjectId(pedido_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"pedido_id no es un ObjectId válido: {str(e)}")
    if not nuevo_estado_general:
        raise HTTPException(status_code=400, detail="Falta el nuevo estado_general")
    result = pedidos_collection.update_one(
        {"_id": pedido_obj_id},
        {"$set": {"estado_general": nuevo_estado_general}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return {"message": "Estado general actualizado correctamente"}

@router.get("/asignaciones/modulo/{modulo}")
async def get_asignaciones_modulo_produccion(modulo: str):
    """Obtener asignaciones reales de un módulo específico para el dashboard"""
    try:
        print(f"DEBUG MODULO: Obteniendo asignaciones para módulo {modulo}")
        
        # Mapear módulos a órdenes
        modulo_orden = {
            "herreria": 1,
            "masillar": 2, 
            "preparar": 3,
            "listo_facturar": 4
        }
        
        orden = modulo_orden.get(modulo)
        if not orden:
            raise HTTPException(status_code=400, detail=f"Módulo no válido: {modulo}")
        
        print(f"DEBUG MODULO: Buscando pedidos con orden {orden}")
        
        # Buscar pedidos que tengan asignaciones en este módulo
        pipeline = [
            {
                "$match": {
                    "seguimiento": {
                        "$elemMatch": {
                            "orden": orden_int,
                            "asignaciones_articulos": {"$exists": True, "$ne": []}
                        }
                    }
                }
            },
            {
                "$unwind": "$seguimiento"
            },
            {
                "$match": {
                    "seguimiento.orden": orden
                }
            },
            {
                "$unwind": "$seguimiento.asignaciones_articulos"
            },
            {
                "$project": {
                    "_id": 1,
                    "cliente_nombre": 1,
                    "pedido_id": "$_id",
                    "item_id": "$seguimiento.asignaciones_articulos.itemId",
                    "empleado_id": "$seguimiento.asignaciones_articulos.empleadoId",
                    "empleado_nombre": "$seguimiento.asignaciones_articulos.nombreempleado",
                    "modulo": modulo,
                    "estado": "$seguimiento.asignaciones_articulos.estado",
                    "estado_subestado": "$seguimiento.asignaciones_articulos.estado_subestado",
                    "fecha_asignacion": "$seguimiento.asignaciones_articulos.fecha_inicio",
                    "fecha_fin": "$seguimiento.asignaciones_articulos.fecha_fin",
                    "descripcionitem": "$seguimiento.asignaciones_articulos.descripcionitem",
                    "detalleitem": "$seguimiento.asignaciones_articulos.detalleitem",
                    "costo_produccion": "$seguimiento.asignaciones_articulos.costoproduccion",
                    "imagenes": "$seguimiento.asignaciones_articulos.imagenes",
                    "orden": "$seguimiento.orden"
                }
            },
            {
                "$match": {
                    "estado": {"$in": ["en_proceso", "pendiente"]}
                }
            }
        ]
        
        asignaciones = list(pedidos_collection.aggregate(pipeline))
        
        # Convertir ObjectId a string para JSON
        for asignacion in asignaciones:
            asignacion["pedido_id"] = str(asignacion["pedido_id"])
            asignacion["item_id"] = str(asignacion["item_id"])
            if asignacion.get("_id"):
                asignacion["_id"] = str(asignacion["_id"])
        
        print(f"DEBUG MODULO: Encontradas {len(asignaciones)} asignaciones para módulo {modulo}")
        
        return {
            "asignaciones": asignaciones,
            "total": len(asignaciones),
            "modulo": modulo,
            "orden": orden_int,
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR MODULO: Error al obtener asignaciones: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener asignaciones del módulo: {str(e)}")

@router.get("/asignaciones/todas")
async def get_todas_asignaciones_produccion():
    """Obtener todas las asignaciones de todos los módulos para el dashboard"""
    try:
        print(f"DEBUG TODAS: Obteniendo todas las asignaciones de producción")
        
        pipeline = [
            {
                "$match": {
                    "seguimiento": {
                        "$elemMatch": {
                            "asignaciones_articulos": {"$exists": True, "$ne": []}
                        }
                    }
                }
            },
            {
                "$unwind": "$seguimiento"
            },
            {
                "$match": {
                    "seguimiento.asignaciones_articulos": {"$exists": True, "$ne": []}
                }
            },
            {
                "$unwind": "$seguimiento.asignaciones_articulos"
            },
            {
                "$project": {
                    "_id": 1,
                    "cliente_nombre": 1,
                    "pedido_id": "$_id",
                    "item_id": "$seguimiento.asignaciones_articulos.itemId",
                    "empleado_id": "$seguimiento.asignaciones_articulos.empleadoId",
                    "empleado_nombre": "$seguimiento.asignaciones_articulos.nombreempleado",
                    "modulo": {
                        "$switch": {
                            "branches": [
                                {"case": {"$eq": ["$seguimiento.orden", 1]}, "then": "herreria"},
                                {"case": {"$eq": ["$seguimiento.orden", 2]}, "then": "masillar"},
                                {"case": {"$eq": ["$seguimiento.orden", 3]}, "then": "preparar"},
                                {"case": {"$eq": ["$seguimiento.orden", 4]}, "then": "listo_facturar"}
                            ],
                            "default": "desconocido"
                        }
                    },
                    "estado": "$seguimiento.asignaciones_articulos.estado",
                    "estado_subestado": "$seguimiento.asignaciones_articulos.estado_subestado",
                    "fecha_asignacion": "$seguimiento.asignaciones_articulos.fecha_inicio",
                    "fecha_fin": "$seguimiento.asignaciones_articulos.fecha_fin",
                    "descripcionitem": "$seguimiento.asignaciones_articulos.descripcionitem",
                    "detalleitem": "$seguimiento.asignaciones_articulos.detalleitem",
                    "costo_produccion": "$seguimiento.asignaciones_articulos.costoproduccion",
                    "imagenes": "$seguimiento.asignaciones_articulos.imagenes",
                    "orden": "$seguimiento.orden"
                }
            },
            {
                "$match": {
                    "estado": {"$in": ["en_proceso", "pendiente"]},
                    "modulo": {"$ne": "desconocido"}
                }
            },
            {
                "$sort": {"orden": 1, "fecha_asignacion": -1}
            }
        ]
        
        asignaciones = list(pedidos_collection.aggregate(pipeline))
        
        # Convertir ObjectId a string para JSON
        for asignacion in asignaciones:
            asignacion["pedido_id"] = str(asignacion["pedido_id"])
            asignacion["item_id"] = str(asignacion["item_id"])
            if asignacion.get("_id"):
                asignacion["_id"] = str(asignacion["_id"])
        
        print(f"DEBUG TODAS: Encontradas {len(asignaciones)} asignaciones totales")
        
        return {
            "asignaciones": asignaciones,
            "total": len(asignaciones),
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR TODAS: Error al obtener todas las asignaciones: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener asignaciones: {str(e)}")



# Endpoint para terminar una asignación de artículo dentro de un pedido
@router.put("/asignacion/terminar")
async def terminar_asignacion_articulo(
    pedido_id: str = Body(...),
    orden: Union[int, str] = Body(...),  # Aceptar tanto int como string
    item_id: str = Body(...),
    empleado_id: str = Body(...),
    estado: str = Body(...),  # Debe ser "terminado"
    fecha_fin: str = Body(...),
    pin: Optional[str] = Body(None),  # PIN opcional para validación
):
    """Endpoint para terminar una asignación de artículo"""
    print(f"DEBUG TERMINAR: Iniciando terminación de asignación")
    print(f"DEBUG TERMINAR: pedido_id={pedido_id}, orden={orden} (tipo: {type(orden)}), item_id={item_id}, empleado_id={empleado_id}")
    print(f"DEBUG TERMINAR: estado={estado}, fecha_fin={fecha_fin}")
    
    # Convertir orden a int si viene como string
    try:
        orden_int = int(orden) if isinstance(orden, str) else orden
        print(f"DEBUG TERMINAR: Orden convertido a int: {orden_int}")
    except (ValueError, TypeError) as e:
        print(f"ERROR TERMINAR: Error convirtiendo orden a int: {e}")
        raise HTTPException(status_code=400, detail=f"orden debe ser un número válido: {str(e)}")
    
    # Validar PIN si se proporciona
    if pin:
        print(f"DEBUG TERMINAR: Validando PIN para empleado {empleado_id}")
        empleado = empleados_collection.find_one({"identificador": empleado_id})
        if not empleado:
            print(f"ERROR TERMINAR: Empleado no encontrado: {empleado_id}")
            raise HTTPException(status_code=404, detail="Empleado no encontrado")
        
        if empleado.get("pin") != pin:
            print(f"ERROR TERMINAR: PIN incorrecto para empleado {empleado_id}")
            raise HTTPException(status_code=400, detail="PIN incorrecto")
        
        print(f"DEBUG TERMINAR: PIN validado correctamente para empleado {empleado.get('nombreCompleto', empleado_id)}")
    else:
        print(f"DEBUG TERMINAR: No se proporcionó PIN, continuando sin validación")
    
    try:
        pedido_obj_id = ObjectId(pedido_id)
    except Exception as e:
        print(f"DEBUG TERMINAR: Error en ObjectId: {e}")
        raise HTTPException(status_code=400, detail=f"pedido_id no es un ObjectId válido: {str(e)}")
    
    pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
    if not pedido:
        print(f"DEBUG TERMINAR: Pedido no encontrado")
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    print(f"DEBUG TERMINAR: Pedido encontrado: {pedido.get('cliente_nombre', 'SIN_NOMBRE')}")
    
    seguimiento = pedido.get("seguimiento", [])
    actualizado = False
    asignacion_encontrada = None
    
    for sub in seguimiento:
        if int(sub.get("orden", -1)) == orden_int:
            print(f"DEBUG TERMINAR: Encontrado subestado con orden {orden_int}")
            asignaciones = sub.get("asignaciones_articulos", [])
            print(f"DEBUG TERMINAR: Asignaciones encontradas: {len(asignaciones)}")
            
            for asignacion in asignaciones:
                print(f"DEBUG TERMINAR: Revisando asignación: itemId={asignacion.get('itemId')}, empleadoId={asignacion.get('empleadoId')}")
                if asignacion.get("itemId") == item_id and asignacion.get("empleadoId") == empleado_id:
                    print(f"DEBUG TERMINAR: Asignación encontrada, estado actual: {asignacion.get('estado')}")
                    
                    # Actualizar todos los campos necesarios
                    asignacion["estado"] = estado
                    asignacion["estado_subestado"] = "terminado"  # Cambiar estado_subestado
                    asignacion["fecha_fin"] = fecha_fin
                    
                    # Guardar copia para respuesta
                    asignacion_encontrada = asignacion.copy()
                    actualizado = True
                    
                    print(f"DEBUG TERMINAR: Asignación actualizada:")
                    print(f"  - estado: {asignacion.get('estado')}")
                    print(f"  - estado_subestado: {asignacion.get('estado_subestado')}")
                    print(f"  - fecha_fin: {asignacion.get('fecha_fin')}")
                    break
            break
    
    if not actualizado:
        print(f"DEBUG TERMINAR: Asignación no encontrada")
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    
    # ACTUALIZAR ESTADO_SUBESTADO DEL ARTÍCULO PARA MOVER AL SIGUIENTE MÓDULO
    print(f"DEBUG TERMINAR: Actualizando estado_subestado del artículo")
    siguiente_modulo = obtener_siguiente_modulo(orden)
    print(f"DEBUG TERMINAR: Siguiente módulo: {siguiente_modulo}")
    
    try:
        # Actualizar el estado_subestado del artículo específico
        result_item = pedidos_collection.update_one(
            {
                "_id": pedido_obj_id,
                "items.id": item_id
            },
            {
                "$set": {
                    "items.$.estado_subestado": siguiente_modulo,
                    "items.$.fecha_progreso": datetime.now().isoformat()
                }
            }
        )
        print(f"DEBUG TERMINAR: Artículo actualizado: {result_item.modified_count} documentos modificados")
        
        if result_item.modified_count == 0:
            print(f"DEBUG TERMINAR: Advertencia: No se pudo actualizar el estado_subestado del artículo")
    except Exception as e:
        print(f"DEBUG TERMINAR: Error al actualizar estado_subestado: {e}")
        import traceback
        print(f"DEBUG TERMINAR: Traceback: {traceback.format_exc()}")
    
    # MOVER EL ARTÍCULO INDIVIDUAL AL SIGUIENTE PROCESO
    print(f"DEBUG TERMINAR: Moviendo artículo individual al siguiente proceso")
    proceso_actual = None
    asignacion_terminada = None
    
    try:
        # Encontrar el proceso actual y la asignación terminada
        for sub in seguimiento:
            if int(sub.get("orden", -1)) == orden:
                proceso_actual = sub
                asignaciones = sub.get("asignaciones_articulos", [])
                print(f"DEBUG TERMINAR: Proceso actual tiene {len(asignaciones)} asignaciones")
                
                for asignacion in asignaciones:
                    if asignacion.get("itemId") == item_id and asignacion.get("empleadoId") == empleado_id:
                        asignacion_terminada = asignacion.copy()
                        print(f"DEBUG TERMINAR: Asignación encontrada para mover: {asignacion.get('itemId')}")
                        break
                break
        
        # Buscar el siguiente proceso
        siguiente_orden = orden + 1
        proceso_siguiente = None
        
        print(f"DEBUG TERMINAR: Buscando proceso siguiente con orden {siguiente_orden}")
        print(f"DEBUG TERMINAR: Total de procesos en seguimiento: {len(seguimiento)}")
        
        for i, sub in enumerate(seguimiento):
            orden_proceso = sub.get("orden", -1)
            nombre_proceso = sub.get("nombre", "SIN_NOMBRE")
            print(f"DEBUG TERMINAR: Proceso {i}: orden={orden_proceso}, nombre={nombre_proceso}, estado={sub.get('estado', 'SIN_ESTADO')}")
            if int(orden_proceso) == siguiente_orden:
                proceso_siguiente = sub
                print(f"DEBUG TERMINAR: Proceso siguiente encontrado: orden={siguiente_orden}, nombre={nombre_proceso}")
                break
        
        if proceso_siguiente and asignacion_terminada:
            print(f"DEBUG TERMINAR: Moviendo artículo {item_id} al siguiente proceso (orden {siguiente_orden})")
            
            # Inicializar asignaciones_articulos si no existe
            if "asignaciones_articulos" not in proceso_siguiente:
                proceso_siguiente["asignaciones_articulos"] = []
            
            # Crear nueva asignación para el siguiente proceso
            nueva_asignacion = {
                "itemId": asignacion_terminada.get("itemId"),
                "empleadoId": None,  # Sin asignar aún
                "nombreempleado": "",
                "descripcionitem": asignacion_terminada.get("descripcionitem"),
                "costoproduccion": asignacion_terminada.get("costoproduccion"),
                "estado": "pendiente",  # Pendiente de asignar
                "estado_subestado": "pendiente",
                "fecha_inicio": None,
                "fecha_fin": None
            }
            
            # Agregar al siguiente proceso
            proceso_siguiente["asignaciones_articulos"].append(nueva_asignacion)
            proceso_siguiente["estado"] = "en_proceso"
            
            # Remover la asignación del proceso actual
            if proceso_actual and "asignaciones_articulos" in proceso_actual:
                proceso_actual["asignaciones_articulos"] = [
                    a for a in proceso_actual["asignaciones_articulos"] 
                    if not (a.get("itemId") == item_id and a.get("empleadoId") == empleado_id)
                ]
                print(f"DEBUG TERMINAR: Asignación removida del proceso actual")
            
            print(f"DEBUG TERMINAR: Artículo movido exitosamente al siguiente proceso")
        else:
            print(f"DEBUG TERMINAR: No hay siguiente proceso o asignación no encontrada")
            if not proceso_siguiente:
                print(f"DEBUG TERMINAR: No se encontró proceso con orden {siguiente_orden}")
            if not asignacion_terminada:
                print(f"DEBUG TERMINAR: No se encontró asignación terminada")
                
    except Exception as e:
        print(f"DEBUG TERMINAR: Error en movimiento de artículo: {e}")
        import traceback
        print(f"DEBUG TERMINAR: Traceback: {traceback.format_exc()}")
    
    # Actualizar el pedido en la base de datos
    result = pedidos_collection.update_one(
        {"_id": pedido_obj_id},
        {"$set": {"seguimiento": seguimiento}}
    )
    
    print(f"DEBUG TERMINAR: Resultado de actualización: {result.modified_count} documentos modificados")
    
    if result.modified_count == 0:
        print(f"DEBUG TERMINAR: Error al actualizar el pedido")
        raise HTTPException(status_code=500, detail="Error al actualizar el pedido")
    
    print(f"DEBUG TERMINAR: Asignación terminada exitosamente")
    
    # Información adicional para debug
    debug_info = {
        "proceso_actual_encontrado": proceso_actual is not None,
        "asignacion_terminada_encontrada": asignacion_terminada is not None,
        "proceso_siguiente_encontrado": proceso_siguiente is not None,
        "siguiente_orden": siguiente_orden,
        "asignaciones_restantes": len(proceso_actual.get("asignaciones_articulos", [])) if proceso_actual else 0,
        "total_procesos": len(seguimiento),
        "siguiente_modulo": siguiente_modulo,
        "estado_subestado_actualizado": result_item.modified_count > 0 if 'result_item' in locals() else False
    }
    print(f"DEBUG TERMINAR: Info debug: {debug_info}")
    
    return {
        "message": "Asignación terminada correctamente",
        "success": True,
        "asignacion_actualizada": asignacion_encontrada,
        "pedido_id": pedido_id,
        "orden": orden_int,
        "item_id": item_id,
        "empleado_id": empleado_id,
        "estado_anterior": "en_proceso",
        "estado_nuevo": "terminado",
        "fecha_fin": fecha_fin,
        "articulo_movido": proceso_siguiente is not None,
        "siguiente_proceso": siguiente_orden if proceso_siguiente else None,
        "proceso_actual_vacio": len(proceso_actual.get("asignaciones_articulos", [])) == 0 if proceso_actual else False,
        "debug_info": debug_info
    }

# Endpoint alternativo con barra al final (para compatibilidad)
@router.put("/asignacion/terminar/")
async def terminar_asignacion_articulo_alt(
    pedido_id: str = Body(...),
    orden: int = Body(...),
    item_id: str = Body(...),
    empleado_id: str = Body(...),
    estado: str = Body(...),  # Debe ser "terminado"
    fecha_fin: str = Body(...),
):
    try:
        pedido_obj_id = ObjectId(pedido_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"pedido_id no es un ObjectId válido: {str(e)}")
    pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    seguimiento = pedido.get("seguimiento", [])
    actualizado = False
    for sub in seguimiento:
        if int(sub.get("orden", -1)) == orden:
            asignaciones = sub.get("asignaciones_articulos", [])
            for asignacion in asignaciones:
                if asignacion.get("itemId") == item_id and asignacion.get("empleadoId") == empleado_id:
                    asignacion["estado"] = estado
                    asignacion["fecha_fin"] = fecha_fin
                    actualizado = True
                    break
            break
    if not actualizado:
        raise HTTPException(status_code=404, detail="Asignación no encontrada para actualizar")
    
    try:
        result = pedidos_collection.update_one(
            {"_id": pedido_obj_id},
            {"$set": {"seguimiento": seguimiento}}
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Error al actualizar el pedido")
        
        return {"message": "Asignación terminada correctamente"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al actualizar: {str(e)}")

@router.get("/estado/")
async def get_pedidos_por_estados(
    estado_general: List[str] = Query(...),
    fecha_inicio: Optional[str] = Query(None),  # "YYYY-MM-DD"
    fecha_fin: Optional[str] = Query(None),     # "YYYY-MM-DD"
):
    # filtro base por estados
    base_filter = {"estado_general": {"$in": estado_general}}

    # Si no hay filtro de fecha, usamos solo el filtro base
    if not fecha_inicio:
        final_query = base_filter
    else:
        # parseo seguro de fechas
        try:
            d_start = datetime.fromisoformat(fecha_inicio)
            start_dt = datetime(d_start.year, d_start.month, d_start.day, tzinfo=timezone.utc)
            if fecha_fin:
                d_end = datetime.fromisoformat(fecha_fin)
                end_dt = datetime(d_end.year, d_end.month, d_end.day, tzinfo=timezone.utc) + timedelta(days=1)
            else:
                end_dt = start_dt + timedelta(days=1)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Formato de fecha inválido (usar YYYY-MM-DD): {e}")

        # strings ISO con Z (coincide con tu formato en la DB "2025-09-01T12:20:58.912Z")
        start_str = f"{start_dt.strftime('%Y-%m-%dT%H:%M:%S')}.000Z"
        end_str = f"{end_dt.strftime('%Y-%m-%dT%H:%M:%S')}.000Z"

        # condiciones: para Date (BSON) usamos objetos datetime, para string usamos strings ISO
        cond_date = {"fecha_creacion": {"$gte": start_dt, "$lt": end_dt}}
        cond_string = {"fecha_creacion": {"$gte": start_str, "$lt": end_str}}

        # combinamos: estado_general AND (cond_date OR cond_string)
        final_query = {"$and": [base_filter, {"$or": [cond_date, cond_string]}]}

    try:
        pedidos = list(pedidos_collection.find(final_query))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en la consulta a la DB: {e}")

    for pedido in pedidos:
        pedido["_id"] = str(pedido["_id"])
    return pedidos





# Endpoint para totalizar un pago de un pedido
@router.put("/{pedido_id}/totalizar-pago")
async def totalizar_pago(
    pedido_id: str
):
    try:
        pedido_obj_id = ObjectId(pedido_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"pedido_id no es un ObjectId válido: {str(e)}")

    update_result = pedidos_collection.update_one(
        {"_id": pedido_obj_id},
        {"$set": {"pago": "pagado", "fecha_totalizado": datetime.utcnow().isoformat()}}
    )

    if update_result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    return {"message": "Pago totalizado correctamente"}

@router.get("/company-details")
async def get_company_details():
    # Hardcoded company details for now
    return {
        "nombre": "Tu Mundo Puertas",
        "rif": "J-12345678-9",
        "direccion": "Calle Ficticia, Edificio Ejemplo, Piso 1, Oficina 1A, Ciudad Ficticia, Estado Imaginario",
        "telefono": "+58 212 1234567",
        "email": "info@tumundopuertas.com"
    }

# Endpoint único para actualizar el estado de pago y/o registrar abonos
from fastapi import Request

@router.patch("/{pedido_id}/pago")
async def actualizar_pago(
    pedido_id: str,
    request: Request
):
    data = await request.json()
    pago = data.get("pago")
    monto = data.get("monto")
    metodo = data.get("metodo")

    # Debug: Log de los datos recibidos
    print(f"DEBUG PAGO: Pedido {pedido_id}")
    print(f"DEBUG PAGO: Datos recibidos: {data}")
    print(f"DEBUG PAGO: Método recibido: {metodo} (tipo: {type(metodo).__name__})")

    if pago not in ["sin pago", "abonado", "pagado"]:
        raise HTTPException(status_code=400, detail="Valor de pago inválido")

    update = {"$set": {"pago": pago}}
    registro = None
    if monto is not None:
        registro = {
            "fecha": datetime.utcnow().isoformat(),
            "monto": monto,
            "estado": pago,
        }
        if metodo:
            registro["metodo"] = metodo
            print(f"DEBUG PAGO: Método guardado en registro: {registro['metodo']}")
        update["$push"] = {"historial_pagos": registro}

    try:
        # Obtener el pedido actual para calcular el total_abonado
        pedido = pedidos_collection.find_one({"_id": ObjectId(pedido_id)})
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")

        current_total_abonado = pedido.get("total_abonado", 0.0)
        new_total_abonado = current_total_abonado + (monto if monto is not None else 0.0)
        update["$set"]["total_abonado"] = new_total_abonado

        result = pedidos_collection.update_one(
            {"_id": ObjectId(pedido_id)},
            update
        )

        # Si hay un método de pago y un monto, incrementar el saldo del método
        if metodo and monto is not None and monto > 0:
            print(f"DEBUG PAGO: Incrementando saldo del método '{metodo}' en {monto}")
            print(f"DEBUG PAGO: Tipo de metodo: {type(metodo).__name__}")
            try:
                # Buscar el método de pago por _id o por nombre
                metodo_pago = None
                
                # Intentar buscar por ObjectId primero
                try:
                    metodo_pago = metodos_pago_collection.find_one({"_id": ObjectId(metodo)})
                    print(f"DEBUG PAGO: Buscando por ObjectId: {metodo}")
                except:
                    print(f"DEBUG PAGO: No es ObjectId válido, buscando por nombre: {metodo}")
                
                # Si no se encontró por ObjectId, buscar por nombre
                if not metodo_pago:
                    metodo_pago = metodos_pago_collection.find_one({"nombre": metodo})
                    print(f"DEBUG PAGO: Buscando por nombre: {metodo}")
                
                print(f"DEBUG PAGO: Método encontrado: {metodo_pago is not None}")
                if metodo_pago:
                    saldo_actual = metodo_pago.get("saldo", 0.0)
                    nuevo_saldo = saldo_actual + monto
                    print(f"DEBUG PAGO: Saldo actual: {saldo_actual}, Nuevo saldo: {nuevo_saldo} para método '{metodo_pago.get('nombre', 'SIN_NOMBRE')}'")
                    
                    result_update = metodos_pago_collection.update_one(
                        {"_id": metodo_pago["_id"]},
                        {"$set": {"saldo": nuevo_saldo}}
                    )
                    print(f"DEBUG PAGO: Resultado de actualización: {result_update.modified_count} documentos modificados")
                    
                    # Verificar que se actualizó correctamente
                    metodo_verificado = metodos_pago_collection.find_one({"_id": ObjectId(metodo)})
                    print(f"DEBUG PAGO: Saldo verificado después de actualizar: {metodo_verificado.get('saldo', 'ERROR')}")
                else:
                    print(f"DEBUG PAGO: Método de pago '{metodo}' no encontrado")
                    # Listar todos los métodos disponibles para debug
                    todos_metodos = list(metodos_pago_collection.find({}, {"_id": 1, "nombre": 1}))
                    print(f"DEBUG PAGO: Métodos disponibles: {[(str(m['_id']), m.get('nombre', 'SIN_NOMBRE')) for m in todos_metodos]}")
            except Exception as e:
                print(f"DEBUG PAGO: Error al actualizar saldo: {e}")
                print(f"DEBUG PAGO: Tipo de error: {type(e).__name__}")
                import traceback
                print(f"DEBUG PAGO: Traceback: {traceback.format_exc()}")
                # No lanzamos excepción para no interrumpir el flujo principal

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en la DB: {e}")

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    response = {"message": "Pago actualizado correctamente", "pago": pago}
    if registro:
        response["registro"] = registro
    return response

@router.get("/mis-pagos")
async def obtener_pagos(
    fecha_inicio: Optional[str] = Query(None, description="Fecha inicio en formato YYYY-MM-DD"),
    fecha_fin: Optional[str] = Query(None, description="Fecha fin en formato YYYY-MM-DD"),
):
    """
    Retorna los pagos de los pedidos, filtrando por rango de fechas si se especifica.
    """

    filtro = {}

    if fecha_inicio and fecha_fin:
        try:
            inicio = datetime.strptime(fecha_inicio, "%Y-%m-%d")
            fin = datetime.strptime(fecha_fin, "%Y-%m-%d") + timedelta(days=1)
            filtro["fecha_creacion"] = {"$gte": inicio, "$lt": fin}
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de fecha inválido, use YYYY-MM-DD")

    # Buscar pedidos
    pedidos = list(
        pedidos_collection.find(
            filtro,
            {
                "_id": 1,
                "cliente_id": 1,
                "cliente_nombre": 1,
                "pago": 1,
                "historial_pagos": 1,
                "total_abonado": 1,
                "items": 1, # Necesario para calcular el total del pedido en el frontend
            },
        )
    )

    # Convertir ObjectId a str
    for p in pedidos:
        p["_id"] = str(p["_id"])

    return pedidos

@router.get("/venta-diaria/")
async def get_venta_diaria(
    fecha_inicio: Optional[str] = Query(None, description="Fecha inicio en formato YYYY-MM-DD"),
    fecha_fin: Optional[str] = Query(None, description="Fecha fin en formato YYYY-MM-DD"),
):
    """
    Retorna un resumen de todos los abonos (pagos) realizados,
    filtrando por rango de fechas si se especifica.
    """
    try:
        print(f"DEBUG VENTA DIARIA: Iniciando consulta con fechas {fecha_inicio} a {fecha_fin}")
        
        # Obtener todos los métodos de pago primero
        metodos_pago = {}
        for metodo in metodos_pago_collection.find({}):
            metodos_pago[str(metodo["_id"])] = metodo["nombre"]
            metodos_pago[metodo["nombre"]] = metodo["nombre"]
        
        print(f"DEBUG VENTA DIARIA: Cargados {len(metodos_pago)} métodos de pago")
        
        # Convertir fecha de búsqueda al formato MM/DD/YYYY que está en la BD
        fecha_busqueda_mmddyyyy = None
        if fecha_inicio and fecha_fin:
            try:
                # Intentar diferentes formatos de fecha
                fecha_obj = None
                
                # Formato 1: YYYY-MM-DD
                try:
                    fecha_obj = datetime.strptime(fecha_inicio, "%Y-%m-%d")
                    print(f"DEBUG VENTA DIARIA: Fecha parseada como YYYY-MM-DD: {fecha_inicio}")
                except ValueError:
                    pass
                
                # Formato 2: MM/DD/YYYY
                if fecha_obj is None:
                    try:
                        fecha_obj = datetime.strptime(fecha_inicio, "%m/%d/%Y")
                        print(f"DEBUG VENTA DIARIA: Fecha parseada como MM/DD/YYYY: {fecha_inicio}")
                    except ValueError:
                        pass
                
                if fecha_obj is None:
                    raise ValueError(f"No se pudo parsear la fecha: {fecha_inicio}")
                
                # Convertir a formato MM/DD/YYYY para buscar en la BD
                fecha_busqueda_mmddyyyy = fecha_obj.strftime("%m/%d/%Y")
                print(f"DEBUG VENTA DIARIA: Buscando fecha en formato MM/DD/YYYY: {fecha_busqueda_mmddyyyy}")
                
            except ValueError as e:
                print(f"ERROR VENTA DIARIA: Error parsing fechas: {e}")
                raise HTTPException(status_code=400, detail=f"Formato de fecha inválido: {fecha_inicio}. Use YYYY-MM-DD o MM/DD/YYYY")
        
        # Pipeline simplificado sin filtros problemáticos
        pipeline = [
            {"$unwind": "$historial_pagos"},
            {
                "$project": {
                    "_id": 0,
                    "pedido_id": "$_id",
                    "cliente_nombre": "$cliente_nombre",
                    "fecha": "$historial_pagos.fecha",
                    "monto": "$historial_pagos.monto",
                    "metodo_id": "$historial_pagos.metodo"
                }
            },
            {"$sort": {"fecha": -1}},
        ]

        print(f"DEBUG VENTA DIARIA: Ejecutando pipeline con {len(pipeline)} etapas")
        abonos_raw = list(pedidos_collection.aggregate(pipeline))
        print(f"DEBUG VENTA DIARIA: Encontrados {len(abonos_raw)} abonos raw")

        # Procesar los abonos manualmente y aplicar filtro de fechas SIMPLE
        abonos = []
        for abono in abonos_raw:
            # Filtro SIMPLE: solo comparar strings directamente
            if fecha_busqueda_mmddyyyy:
                fecha_abono = str(abono.get("fecha", ""))
                print(f"DEBUG VENTA DIARIA: Comparando '{fecha_abono}' con '{fecha_busqueda_mmddyyyy}'")
                
                # Buscar si la fecha contiene la fecha que buscamos
                if fecha_busqueda_mmddyyyy not in fecha_abono:
                    print(f"DEBUG VENTA DIARIA: Fecha no coincide, saltando")
                    continue
                    
                print(f"DEBUG VENTA DIARIA: ¡Fecha encontrada! {fecha_abono}")
            
            metodo_id = abono.get("metodo_id")
            metodo_nombre = metodos_pago.get(str(metodo_id), metodos_pago.get(metodo_id, metodo_id))
            
            abono_procesado = {
                "pedido_id": str(abono["pedido_id"]),
                "cliente_nombre": abono.get("cliente_nombre"),
                "fecha": abono.get("fecha"),
                "monto": abono.get("monto", 0),
                "metodo": metodo_nombre
            }
            abonos.append(abono_procesado)

        print(f"DEBUG VENTA DIARIA: Procesados {len(abonos)} abonos")

        # Calcular totales
        total_ingresos = sum(abono.get("monto", 0) for abono in abonos)

        ingresos_por_metodo = {}
        for abono in abonos:
            metodo = abono.get("metodo", "Desconocido")
            if metodo not in ingresos_por_metodo:
                ingresos_por_metodo[metodo] = 0
            ingresos_por_metodo[metodo] += abono.get("monto", 0)

        print(f"DEBUG VENTA DIARIA: Total ingresos: {total_ingresos}, Métodos: {len(ingresos_por_metodo)}")

        return {
            "total_ingresos": total_ingresos,
            "abonos": abonos,
            "ingresos_por_metodo": ingresos_por_metodo,
        }
        
    except Exception as e:
        print(f"ERROR VENTA DIARIA: Error completo: {str(e)}")
        print(f"ERROR VENTA DIARIA: Tipo de error: {type(e).__name__}")
        import traceback
        print(f"ERROR VENTA DIARIA: Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error en la consulta a la DB: {str(e)}")

@router.get("/venta-diaria", include_in_schema=False)
async def get_venta_diaria_no_slash(
    fecha_inicio: Optional[str] = Query(None, description="Fecha inicio en formato YYYY-MM-DD"),
    fecha_fin: Optional[str] = Query(None, description="Fecha fin en formato YYYY-MM-DD"),
):
    """Endpoint alternativo sin barra final para compatibilidad"""
    return await get_venta_diaria(fecha_inicio, fecha_fin)

@router.get("/debug-historial-pagos/{pedido_id}")
async def debug_historial_pagos(pedido_id: str):
    """Endpoint de debug para ver el historial de pagos de un pedido específico"""
    try:
        pedido = pedidos_collection.find_one({"_id": ObjectId(pedido_id)})
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        historial = pedido.get("historial_pagos", [])
        
        # También obtener todos los métodos de pago para comparar
        metodos_pago = list(metodos_pago_collection.find())
        
        return {
            "pedido_id": pedido_id,
            "historial_pagos": historial,
            "metodos_pago_disponibles": [
                {"_id": str(m["_id"]), "nombre": m["nombre"]} 
                for m in metodos_pago
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@router.get("/debug-venta-diaria-simple")
async def debug_venta_diaria_simple():
    """Endpoint simplificado para debug del resumen de venta diaria"""
    try:
        # Obtener todos los pedidos con historial de pagos
        pedidos_con_pagos = list(pedidos_collection.find(
            {"historial_pagos": {"$exists": True, "$ne": []}},
            {"historial_pagos": 1, "cliente_nombre": 1}
        ))
        
        # Obtener todos los métodos de pago
        metodos_pago = list(metodos_pago_collection.find({}))
        
        # Procesar manualmente para debug
        debug_data = []
        for pedido in pedidos_con_pagos:
            for pago in pedido.get("historial_pagos", []):
                metodo_id = pago.get("metodo")
                
                # Buscar el método de pago manualmente
                metodo_encontrado = None
                for metodo in metodos_pago:
                    if (str(metodo["_id"]) == str(metodo_id) or 
                        metodo["nombre"] == metodo_id or
                        str(metodo_id) == metodo["nombre"]):
                        metodo_encontrado = metodo
                        break
                
                debug_data.append({
                    "pedido_id": str(pedido["_id"]),
                    "cliente": pedido.get("cliente_nombre"),
                    "metodo_id_original": metodo_id,
                    "metodo_id_tipo": type(metodo_id).__name__,
                    "metodo_encontrado": metodo_encontrado["nombre"] if metodo_encontrado else "NO ENCONTRADO",
                    "monto": pago.get("monto"),
                    "fecha": pago.get("fecha")
                })
        
        return {
            "total_registros": len(debug_data),
            "metodos_pago_disponibles": [
                {"_id": str(m["_id"]), "nombre": m["nombre"]} 
                for m in metodos_pago
            ],
            "debug_data": debug_data
        }
        
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}

@router.get("/debug-fechas-abonos")
async def debug_fechas_abonos():
    """Endpoint para ver las fechas de los abonos más recientes"""
    try:
        pipeline = [
            {"$unwind": "$historial_pagos"},
            {
                "$project": {
                    "_id": 0,
                    "pedido_id": "$_id",
                    "cliente_nombre": "$cliente_nombre",
                    "fecha": "$historial_pagos.fecha",
                    "monto": "$historial_pagos.monto",
                    "metodo": "$historial_pagos.metodo",
                    "fecha_tipo": {"$type": "$historial_pagos.fecha"}
                }
            },
            {"$sort": {"fecha": -1}},
            {"$limit": 10}
        ]
        
        abonos_recientes = list(pedidos_collection.aggregate(pipeline))
        
        # Convertir ObjectId a string
        for abono in abonos_recientes:
            abono["pedido_id"] = str(abono["pedido_id"])
        
        return {
            "total_abonos_recientes": len(abonos_recientes),
            "abonos_recientes": abonos_recientes,
            "fechas_unicas": list(set([str(abono["fecha"])[:10] for abono in abonos_recientes]))
        }
        
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}

@router.get("/debug-filtro-fechas")
async def debug_filtro_fechas(
    fecha_inicio: str = "2025-10-11",
    fecha_fin: str = "2025-10-11"
):
    """Endpoint para debuggear el filtro de fechas"""
    try:
        print(f"DEBUG FILTRO: Iniciando debug con fechas {fecha_inicio} a {fecha_fin}")
        
        # Construir filtro como en el endpoint principal
        inicio = datetime.strptime(fecha_inicio, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        fin = datetime.strptime(fecha_fin, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
        
        print(f"DEBUG FILTRO: Fechas parseadas - inicio: {inicio}, fin: {fin}")
        
        filtro_fecha = {
            "historial_pagos.fecha": {
                "$gte": inicio,
                "$lt": fin
            }
        }
        
        print(f"DEBUG FILTRO: Filtro construido: {filtro_fecha}")
        
        # Probar el filtro directamente
        pedidos_con_filtro = list(pedidos_collection.find(filtro_fecha))
        print(f"DEBUG FILTRO: Pedidos encontrados con filtro: {len(pedidos_con_filtro)}")
        
        # Probar sin filtro
        todos_pedidos = list(pedidos_collection.find({}))
        print(f"DEBUG FILTRO: Total pedidos: {len(todos_pedidos)}")
        
        # Ver algunos ejemplos de fechas
        pipeline_ejemplos = [
            {"$unwind": "$historial_pagos"},
            {
                "$project": {
                    "_id": 0,
                    "pedido_id": "$_id",
                    "fecha": "$historial_pagos.fecha",
                    "fecha_tipo": {"$type": "$historial_pagos.fecha"},
                    "fecha_string": {"$dateToString": {"format": "%Y-%m-%d", "date": "$historial_pagos.fecha"}}
                }
            },
            {"$limit": 5}
        ]
        
        ejemplos = list(pedidos_collection.aggregate(pipeline_ejemplos))
        
        return {
            "filtro_aplicado": filtro_fecha,
            "pedidos_con_filtro": len(pedidos_con_filtro),
            "total_pedidos": len(todos_pedidos),
            "ejemplos_fechas": ejemplos,
            "fecha_inicio_parsed": str(inicio),
            "fecha_fin_parsed": str(fin)
        }
        
    except Exception as e:
        print(f"ERROR DEBUG FILTRO: {str(e)}")
        return {"error": str(e), "type": type(e).__name__}

@router.delete("/eliminar-pedido-prueba2")
async def eliminar_pedido_prueba2():
    """Endpoint para eliminar pedidos con método de pago PRUEBA 2"""
    try:
        print("DEBUG ELIMINAR: Buscando pedidos con método PRUEBA 2")
        
        # Buscar pedidos que tengan método de pago "PRUEBA 2"
        pedidos_problema = list(pedidos_collection.find({
            "historial_pagos.metodo": "PRUEBA 2"
        }))
        
        print(f"DEBUG ELIMINAR: Encontrados {len(pedidos_problema)} pedidos con PRUEBA 2")
        
        pedidos_eliminados = []
        for pedido in pedidos_problema:
            pedido_id = str(pedido["_id"])
            cliente_nombre = pedido.get("cliente_nombre", "SIN_NOMBRE")
            
            print(f"DEBUG ELIMINAR: Eliminando pedido {pedido_id} - Cliente: {cliente_nombre}")
            
            # Eliminar el pedido
            result = pedidos_collection.delete_one({"_id": pedido["_id"]})
            
            if result.deleted_count > 0:
                pedidos_eliminados.append({
                    "pedido_id": pedido_id,
                    "cliente_nombre": cliente_nombre,
                    "eliminado": True
                })
                print(f"DEBUG ELIMINAR: Pedido {pedido_id} eliminado exitosamente")
            else:
                print(f"ERROR ELIMINAR: No se pudo eliminar pedido {pedido_id}")
        
        return {
            "mensaje": f"Eliminados {len(pedidos_eliminados)} pedidos con método PRUEBA 2",
            "pedidos_eliminados": pedidos_eliminados,
            "total_encontrados": len(pedidos_problema),
            "total_eliminados": len(pedidos_eliminados)
        }
        
    except Exception as e:
        print(f"ERROR ELIMINAR: {str(e)}")
        return {"error": str(e), "type": type(e).__name__}

@router.get("/debug-todas-fechas")
async def debug_todas_fechas():
    """Endpoint para ver todas las fechas de abonos"""
    try:
        pipeline = [
            {"$unwind": "$historial_pagos"},
            {
                "$project": {
                    "_id": 0,
                    "pedido_id": "$_id",
                    "cliente_nombre": "$cliente_nombre",
                    "fecha": "$historial_pagos.fecha",
                    "monto": "$historial_pagos.monto",
                    "metodo": "$historial_pagos.metodo",
                    "fecha_tipo": {"$type": "$historial_pagos.fecha"},
                    "fecha_string": {
                        "$dateToString": {
                            "format": "%Y-%m-%d", 
                            "date": "$historial_pagos.fecha"
                        }
                    }
                }
            },
            {
                "$group": {
                    "_id": "$fecha_string",
                    "total_monto": {"$sum": "$monto"},
                    "cantidad_abonos": {"$sum": 1},
                    "ejemplos": {"$push": {
                        "pedido_id": "$pedido_id",
                        "cliente": "$cliente_nombre",
                        "monto": "$monto",
                        "metodo": "$metodo"
                    }}
                }
            },
            {"$sort": {"_id": -1}},
            {"$limit": 20}
        ]
        
        fechas_agrupadas = list(pedidos_collection.aggregate(pipeline))
        
        # Convertir ObjectId a string
        for grupo in fechas_agrupadas:
            for ejemplo in grupo.get("ejemplos", []):
                ejemplo["pedido_id"] = str(ejemplo["pedido_id"])
        
        return {
            "total_fechas_unicas": len(fechas_agrupadas),
            "fechas_agrupadas": fechas_agrupadas,
            "resumen": {
                "total_general": sum(grupo["total_monto"] for grupo in fechas_agrupadas),
                "fechas_con_abonos": [grupo["_id"] for grupo in fechas_agrupadas]
            }
        }
        
    except Exception as e:
        print(f"ERROR DEBUG FECHAS: {str(e)}")
        return {"error": str(e), "type": type(e).__name__}

@router.get("/{pedido_id}/datos-impresion")
async def get_datos_impresion(pedido_id: str, current_user = Depends(get_current_user)):
    """Retornar datos del pedido para impresión"""
    try:
        # Buscar el pedido por ID
        pedido = pedidos_collection.find_one({"_id": ObjectId(pedido_id)})
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        # Convertir ObjectId a string
        pedido["_id"] = str(pedido["_id"])
        
        # Calcular saldo pendiente
        total_pedido = sum(item.get("precio", 0) * item.get("cantidad", 0) for item in pedido.get("items", []))
        total_abonado = pedido.get("total_abonado", 0)
        saldo_pendiente = total_pedido - total_abonado
        
        return {
            "pedido": pedido,
            "cliente": {
                "nombre": pedido.get("cliente_nombre", ""),
                "id": pedido.get("cliente_id", "")
            },
            "items": pedido.get("items", []),
            "pagos": pedido.get("historial_pagos", []),
            "total": total_pedido,
            "total_abonado": total_abonado,
            "saldo_pendiente": saldo_pendiente,
            "fecha_creacion": pedido.get("fecha_creacion", ""),
            "estado_general": pedido.get("estado_general", ""),
            "pago": pedido.get("pago", "")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener datos de impresión: {str(e)}")