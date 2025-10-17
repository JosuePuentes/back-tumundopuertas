from fastapi import APIRouter, HTTPException, Depends, Body
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
from ..auth.auth import get_current_user
from ..config.mongodb import db
from ..models.authmodels import Empleado

router = APIRouter()

# Obtener las colecciones
def get_collections():
    return {
        "asignaciones": db["asignaciones"],
        "empleados": db["empleados"],
        "comisiones": db["comisiones"],
        "pedidos": db["pedidos"]
    }

def obtener_siguiente_modulo(modulo_actual: str) -> str:
    """Determinar el siguiente módulo según el flujo de producción"""
    flujo = {
        "herreria": "masillar",
        "masillar": "preparar", 
        "preparar": "listo_facturar",
        "listo_facturar": "completado"
    }
    return flujo.get(modulo_actual, "completado")

def registrar_comision(asignacion: dict, empleado_id: str):
    """Registrar comisión en el reporte de comisiones"""
    collections = get_collections()
    
    comision = {
        "empleado_id": empleado_id,
        "asignacion_id": asignacion["_id"],
        "pedido_id": asignacion.get("pedido_id"),
        "item_id": asignacion.get("item_id"),
        "costo_produccion": asignacion.get("costo_produccion", 0),
        "fecha": datetime.now(),
        "modulo": asignacion.get("modulo"),
        "descripcion": asignacion.get("descripcionitem", ""),
        "cliente_nombre": asignacion.get("cliente_nombre", ""),
        "empleado_nombre": asignacion.get("empleado_nombre", "")
    }
    
    try:
        collections["comisiones"].insert_one(comision)
        print(f"DEBUG COMISION: Comisión registrada para empleado {empleado_id}")
        return True
    except Exception as e:
        print(f"ERROR COMISION: Error al registrar comisión: {e}")
        return False

@router.get("/debug-asignaciones")
async def debug_dashboard_asignaciones():
    """Endpoint de debug para verificar el estado del dashboard"""
    try:
        from ..config.mongodb import pedidos_collection, items_collection
        from bson import ObjectId
        
        print("DEBUG DASHBOARD: Iniciando debug completo")
        
        # 1. Verificar si hay pedidos
        total_pedidos = pedidos_collection.count_documents({})
        print(f"DEBUG DASHBOARD: Total pedidos en BD: {total_pedidos}")
        
        # 2. Verificar pedidos con seguimiento
        pedidos_con_seguimiento = pedidos_collection.count_documents({
            "seguimiento": {"$exists": True, "$ne": []}
        })
        print(f"DEBUG DASHBOARD: Pedidos con seguimiento: {pedidos_con_seguimiento}")
        
        # 3. Verificar asignaciones activas
        pipeline = [
            {
                "$match": {
                    "seguimiento": {
                        "$elemMatch": {
                            "asignaciones_articulos": {
                                "$elemMatch": {
                                    "estado": {"$in": ["en_proceso", "pendiente"]}
                                }
                            }
                        }
                    }
                }
            },
            {
                "$unwind": "$seguimiento"
            },
            {
                "$match": {
                    "seguimiento.asignaciones_articulos": {
                        "$elemMatch": {
                            "estado": {"$in": ["en_proceso", "pendiente"]}
                        }
                    }
                }
            },
            {
                "$unwind": "$seguimiento.asignaciones_articulos"
            },
            {
                "$match": {
                    "seguimiento.asignaciones_articulos.estado": {"$in": ["en_proceso", "pendiente"]}
                }
            },
            {
                "$count": "total"
            }
        ]
        
        resultado_agregacion = list(pedidos_collection.aggregate(pipeline))
        asignaciones_activas = resultado_agregacion[0]["total"] if resultado_agregacion else 0
        print(f"DEBUG DASHBOARD: Asignaciones activas encontradas: {asignaciones_activas}")
        
        # 4. Verificar empleados activos
        from ..config.mongodb import empleados_collection
        empleados_activos = empleados_collection.count_documents({"activo": True})
        print(f"DEBUG DASHBOARD: Empleados activos: {empleados_activos}")
        
        # 5. Obtener muestra de datos
        muestra_pedidos = list(pedidos_collection.find({}).limit(3))
        muestra_empleados = list(empleados_collection.find({"activo": True}).limit(3))
        
        return {
            "debug_info": {
                "total_pedidos": total_pedidos,
                "pedidos_con_seguimiento": pedidos_con_seguimiento,
                "asignaciones_activas": asignaciones_activas,
                "empleados_activos": empleados_activos,
                "muestra_pedidos": [
                    {
                        "_id": str(p.get("_id")),
                        "numero_orden": p.get("numero_orden"),
                        "estado_general": p.get("estado_general"),
                        "tiene_seguimiento": bool(p.get("seguimiento")),
                        "items_count": len(p.get("items", []))
                    } for p in muestra_pedidos
                ],
                "muestra_empleados": [
                    {
                        "_id": str(e.get("_id")),
                        "nombreCompleto": e.get("nombreCompleto"),
                        "tipo": e.get("tipo"),
                        "activo": e.get("activo")
                    } for e in muestra_empleados
                ]
            },
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR DEBUG DASHBOARD: {str(e)}")
        import traceback
        print(f"ERROR DEBUG DASHBOARD: Traceback: {traceback.format_exc()}")
        return {
            "error": str(e),
            "success": False
        }

@router.get("/asignaciones")
async def get_dashboard_asignaciones():
    """
    Endpoint optimizado para Dashboard de Asignaciones
    Retorna todas las asignaciones en proceso para que los empleados vean qué tienen asignado
    """
    try:
        from ..config.mongodb import pedidos_collection, empleados_collection
        from bson import ObjectId
        
        # Consulta optimizada - solo campos necesarios
        asignaciones = []
        
        # Buscar pedidos con asignaciones activas
        pedidos = list(pedidos_collection.find({
            "estado_general": {"$in": ["orden1", "orden2", "orden3"]},
            "seguimiento": {"$exists": True, "$ne": []}
        }, {
            "_id": 1,
            "numero_orden": 1,
            "cliente_nombre": 1,
            "fecha_creacion": 1,
            "seguimiento": 1,
            "items": 1
        }).limit(100))  # Limitar para mejor rendimiento
        
        for pedido in pedidos:
            try:
                for proceso in pedido.get("seguimiento", []):
                    if not isinstance(proceso, dict):
                        continue
                    
                    orden = proceso.get("orden", 1)
                    modulo_nombre = "herreria" if orden == 1 else "masillar" if orden == 2 else "manillar" if orden == 3 else "facturacion"
                    
                    asignaciones_articulos = proceso.get("asignaciones_articulos", [])
                    if not isinstance(asignaciones_articulos, list):
                        continue
                    
                                for asignacion in asignaciones_articulos:
                                    if not isinstance(asignacion, dict):
                                        continue
                                    
                                    # Solo mostrar asignaciones ACTIVAS (en_proceso)
                                    if asignacion.get("estado") == "en_proceso":
                                        # Buscar información del item
                                        item_info = {}
                                        for item in pedido.get("items", []):
                                            if str(item.get("_id")) == str(asignacion.get("itemId")):
                                                item_info = {
                                                    "descripcion": item.get("descripcion", ""),
                                                    "detalle": item.get("detalle", ""),
                                                    "costoproduccion": item.get("costoproduccion", 0),
                                                    "imagenes": item.get("imagenes", [])
                                                }
                                                break
                                        
                                        asignaciones.append({
                                            "_id": str(pedido["_id"]),
                                            "pedido_id": str(pedido["_id"]),
                                            "item_id": str(asignacion.get("itemId", "")),
                                            "empleado_id": asignacion.get("empleadoId", ""),
                                            "nombreempleado": asignacion.get("nombreempleado", ""),
                                            "orden": orden,
                                            "modulo": modulo_nombre,
                                            "estado": asignacion.get("estado"),
                                            "fecha_inicio": asignacion.get("fecha_inicio"),
                                            "fecha_fin": asignacion.get("fecha_fin"),
                                            "numero_orden": pedido.get("numero_orden"),
                                            "cliente": {"cliente_nombre": pedido.get("cliente_nombre", "")},
                                            **item_info
                                        })
            except Exception as e:
                print(f"Error procesando pedido {pedido.get('_id')}: {e}")
                continue
        
        return {
            "success": True,
            "asignaciones": asignaciones,
            "total": len(asignaciones)
        }
        
    except Exception as e:
        print(f"Error en /asignaciones: {e}")
        return {
            "success": False,
            "asignaciones": [],
            "total": 0,
            "error": str(e)
        }

@router.put("/asignaciones/terminar")
async def terminar_asignacion_dashboard(
    asignacion_id: str = Body(...),
    pin: str = Body(...),
    empleado_id: str = Body(...),
    current_user = Depends(get_current_user)
):
    """Terminar una asignación desde el dashboard"""
    try:
        collections = get_collections()
        
        print(f"DEBUG DASHBOARD TERMINAR: Iniciando terminación")
        print(f"DEBUG DASHBOARD TERMINAR: asignacion_id={asignacion_id}, empleado_id={empleado_id}")
        
        # 1. Validar PIN del empleado
        empleado = collections["empleados"].find_one({"identificador": empleado_id})
        if not empleado:
            print(f"ERROR DASHBOARD TERMINAR: Empleado no encontrado: {empleado_id}")
            raise HTTPException(status_code=404, detail="Empleado no encontrado")
        
        if empleado.get("pin") != pin:
            print(f"ERROR DASHBOARD TERMINAR: PIN incorrecto para empleado {empleado_id}")
            raise HTTPException(status_code=400, detail="PIN incorrecto")
        
        print(f"DEBUG DASHBOARD TERMINAR: PIN validado para empleado {empleado.get('nombreCompleto', empleado_id)}")
        
        # 2. Obtener asignación actual
        asignacion_obj_id = ObjectId(asignacion_id)
        asignacion = collections["asignaciones"].find_one({"_id": asignacion_obj_id})
        
        if not asignacion:
            print(f"ERROR DASHBOARD TERMINAR: Asignación no encontrada: {asignacion_id}")
            raise HTTPException(status_code=404, detail="Asignación no encontrada")
        
        modulo_actual = asignacion.get("modulo", "herreria")
        print(f"DEBUG DASHBOARD TERMINAR: Módulo actual: {modulo_actual}")
        
        # 3. Determinar siguiente módulo
        siguiente_modulo = obtener_siguiente_modulo(modulo_actual)
        print(f"DEBUG DASHBOARD TERMINAR: Siguiente módulo: {siguiente_modulo}")
        
        # 4. Actualizar asignación
        update_data = {
            "estado": "terminado",
            "fecha_fin": datetime.now(),
            "modulo": siguiente_modulo
        }
        
        result = collections["asignaciones"].update_one(
            {"_id": asignacion_obj_id},
            {"$set": update_data}
        )
        
        if result.modified_count == 0:
            print(f"ERROR DASHBOARD TERMINAR: No se pudo actualizar la asignación")
            raise HTTPException(status_code=500, detail="Error al actualizar asignación")
        
        print(f"DEBUG DASHBOARD TERMINAR: Asignación actualizada: {result.modified_count} documentos")
        
        # 5. Registrar comisión en reporte
        comision_registrada = registrar_comision(asignacion, empleado_id)
        
        # 6. Si no es el último módulo, crear nueva asignación para el siguiente módulo
        nueva_asignacion_creada = False
        if siguiente_modulo != "completado":
            try:
                # Verificar si ya existe una asignación pendiente para este item en el siguiente módulo
                asignacion_existente = collections["asignaciones"].find_one({
                    "item_id": asignacion.get("item_id"),
                    "modulo": siguiente_modulo,
                    "estado": "pendiente"
                })
                
                if not asignacion_existente:
                    nueva_asignacion = {
                        "pedido_id": asignacion.get("pedido_id"),
                        "item_id": asignacion.get("item_id"),
                        "empleado_id": None,  # Sin asignar aún
                        "empleado_nombre": "",
                        "modulo": siguiente_modulo,
                        "estado": "pendiente",
                        "fecha_asignacion": None,
                        "fecha_fin": None,
                        "descripcionitem": asignacion.get("descripcionitem", ""),
                        "detalleitem": asignacion.get("detalleitem", ""),
                        "cliente_nombre": asignacion.get("cliente_nombre", ""),
                        "costo_produccion": asignacion.get("costo_produccion", 0),
                        "imagenes": asignacion.get("imagenes", [])
                    }
                    
                    collections["asignaciones"].insert_one(nueva_asignacion)
                    nueva_asignacion_creada = True
                    print(f"DEBUG DASHBOARD TERMINAR: Nueva asignación creada para módulo {siguiente_modulo}")
                else:
                    print(f"DEBUG DASHBOARD TERMINAR: Ya existe asignación pendiente en módulo {siguiente_modulo}")
                
            except Exception as e:
                print(f"ERROR DASHBOARD TERMINAR: Error al crear nueva asignación: {e}")
        
        print(f"DEBUG DASHBOARD TERMINAR: Terminación completada exitosamente")
        
        return {
            "message": "Asignación terminada exitosamente",
            "success": True,
            "siguiente_modulo": siguiente_modulo,
            "comision_registrada": comision_registrada,
            "nueva_asignacion_creada": nueva_asignacion_creada,
            "asignacion_id": asignacion_id,
            "empleado_id": empleado_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR DASHBOARD TERMINAR: Error inesperado: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

@router.get("/asignaciones/empleado/{empleado_id}")
async def get_asignaciones_empleado(
    empleado_id: str,
    current_user = Depends(get_current_user)
):
    """Obtener asignaciones de un empleado específico"""
    try:
        collections = get_collections()
        
        asignaciones = list(collections["asignaciones"].find({
            "empleado_id": empleado_id,
            "estado": {"$in": ["en_proceso", "pendiente"]}
        }).sort("fecha_asignacion", -1))
        
        # Convertir ObjectId a string para JSON
        for asignacion in asignaciones:
            asignacion["_id"] = str(asignacion["_id"])
            if "pedido_id" in asignacion:
                asignacion["pedido_id"] = str(asignacion["pedido_id"])
            if "item_id" in asignacion:
                asignacion["item_id"] = str(asignacion["item_id"])
        
        return {
            "asignaciones": asignaciones,
            "total": len(asignaciones),
            "empleado_id": empleado_id,
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR DASHBOARD EMPLEADO: Error al obtener asignaciones: {e}")
        raise HTTPException(status_code=500, detail="Error al obtener asignaciones del empleado")

@router.get("/asignaciones/modulo/{modulo}")
async def get_asignaciones_modulo(
    modulo: str,
    current_user = Depends(get_current_user)
):
    """Obtener asignaciones de un módulo específico"""
    try:
        collections = get_collections()
        
        asignaciones = list(collections["asignaciones"].find({
            "modulo": modulo,
            "estado": {"$in": ["en_proceso", "pendiente"]}
        }).sort("fecha_asignacion", -1))
        
        # Convertir ObjectId a string para JSON
        for asignacion in asignaciones:
            asignacion["_id"] = str(asignacion["_id"])
            if "pedido_id" in asignacion:
                asignacion["pedido_id"] = str(asignacion["pedido_id"])
            if "item_id" in asignacion:
                asignacion["item_id"] = str(asignacion["item_id"])
        
        return {
            "asignaciones": asignaciones,
            "total": len(asignaciones),
            "modulo": modulo,
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR DASHBOARD MODULO: Error al obtener asignaciones: {e}")
        raise HTTPException(status_code=500, detail="Error al obtener asignaciones del módulo")

@router.get("/asignaciones/estadisticas")
async def get_estadisticas_dashboard():
    """Obtener estadísticas generales del dashboard de asignaciones"""
    try:
        collections = get_collections()
        
        # Estadísticas por módulo
        estadisticas = {}
        modulos = ["herreria", "masillar", "preparar", "listo_facturar"]
        
        for modulo in modulos:
            total = collections["asignaciones"].count_documents({
                "modulo": modulo,
                "estado": {"$in": ["en_proceso", "pendiente"]}
            })
            
            en_proceso = collections["asignaciones"].count_documents({
                "modulo": modulo,
                "estado": "en_proceso"
            })
            
            pendientes = collections["asignaciones"].count_documents({
                "modulo": modulo,
                "estado": "pendiente"
            })
            
            estadisticas[modulo] = {
                "total": total,
                "en_proceso": en_proceso,
                "pendientes": pendientes
            }
        
        # Estadísticas generales
        total_asignaciones = sum(stats["total"] for stats in estadisticas.values())
        total_en_proceso = sum(stats["en_proceso"] for stats in estadisticas.values())
        total_pendientes = sum(stats["pendientes"] for stats in estadisticas.values())
        
        print(f"DEBUG ESTADISTICAS: Total asignaciones activas: {total_asignaciones}")
        
        return {
            "estadisticas_por_modulo": estadisticas,
            "totales": {
                "total_asignaciones": total_asignaciones,
                "total_en_proceso": total_en_proceso,
                "total_pendientes": total_pendientes
            },
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR ESTADISTICAS: Error al obtener estadísticas: {e}")
        raise HTTPException(status_code=500, detail="Error al obtener estadísticas")

@router.post("/asignaciones/poblar-datos")
async def poblar_datos_asignaciones(current_user = Depends(get_current_user)):
    """Endpoint para poblar datos de prueba en la colección de asignaciones"""
    try:
        collections = get_collections()
        
        # Datos de prueba
        asignaciones_prueba = [
            {
                "pedido_id": "68e53ad2a05e21da5396c47f",
                "item_id": "68af166910b63f047bce95fc",
                "empleado_id": "17180554",
                "empleado_nombre": "Juan Pérez",
                "modulo": "herreria",
                "estado": "en_proceso",
                "fecha_asignacion": datetime.now(),
                "descripcionitem": "Puerta de hierro 2x1",
                "detalleitem": "Puerta principal con marco",
                "cliente_nombre": "DELIANNY QUINTERO",
                "costo_produccion": 150.00,
                "imagenes": []
            },
            {
                "pedido_id": "68e53ad2a05e21da5396c47f",
                "item_id": "68af166910b63f047bce95fd",
                "empleado_id": "17180555",
                "empleado_nombre": "María García",
                "modulo": "masillar",
                "estado": "pendiente",
                "fecha_asignacion": None,
                "descripcionitem": "Ventana de aluminio 1x1",
                "detalleitem": "Ventana corrediza",
                "cliente_nombre": "DELIANNY QUINTERO",
                "costo_produccion": 80.00,
                "imagenes": []
            },
            {
                "pedido_id": "68e5351da05e21da5396c47d",
                "item_id": "68af166910b63f047bce95fe",
                "empleado_id": None,
                "empleado_nombre": "",
                "modulo": "preparar",
                "estado": "pendiente",
                "fecha_asignacion": None,
                "descripcionitem": "Reja de seguridad",
                "detalleitem": "Reja para ventana",
                "cliente_nombre": "CARLOS RODRIGUEZ",
                "costo_produccion": 120.00,
                "imagenes": []
            }
        ]
        
        # Insertar datos de prueba
        resultado = collections["asignaciones"].insert_many(asignaciones_prueba)
        
        print(f"DEBUG POBLAR: Insertadas {len(resultado.inserted_ids)} asignaciones de prueba")
        
        return {
            "message": f"Datos de prueba insertados exitosamente",
            "asignaciones_insertadas": len(resultado.inserted_ids),
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR POBLAR: Error al poblar datos: {e}")
        raise HTTPException(status_code=500, detail="Error al poblar datos de prueba")

@router.post("/asignaciones/migrar-datos-reales")
async def migrar_datos_reales_dashboard():
    """Migrar datos reales del seguimiento de pedidos a la colección de asignaciones"""
    try:
        collections = get_collections()
        
        print(f"DEBUG MIGRAR: Iniciando migración de datos reales")
        
        # Obtener todos los pedidos con seguimiento
        pedidos = list(collections["pedidos"].find({
            "seguimiento": {"$exists": True, "$ne": []}
        }))
        
        print(f"DEBUG MIGRAR: Encontrados {len(pedidos)} pedidos con seguimiento")
        
        asignaciones_migradas = []
        modulo_orden = {
            1: "herreria",
            2: "masillar", 
            3: "preparar",
            4: "listo_facturar"
        }
        
        for pedido in pedidos:
            pedido_id = str(pedido["_id"])
            cliente_nombre = pedido.get("cliente_nombre", "Sin nombre")
            
            print(f"DEBUG MIGRAR: Procesando pedido {pedido_id} - {cliente_nombre}")
            
            seguimiento = pedido.get("seguimiento", [])
            
            for sub in seguimiento:
                orden = sub.get("orden")
                modulo = modulo_orden.get(orden, "desconocido")
                
                if modulo == "desconocido":
                    continue
                
                asignaciones_articulos = sub.get("asignaciones_articulos", [])
                
                for asignacion in asignaciones_articulos:
                    # Crear asignación para el dashboard
                    nueva_asignacion = {
                        "pedido_id": pedido_id,
                        "item_id": str(asignacion.get("itemId", "")),
                        "empleado_id": asignacion.get("empleadoId"),
                        "empleado_nombre": asignacion.get("nombreempleado", ""),
                        "modulo": modulo,
                        "estado": asignacion.get("estado", "pendiente"),
                        "fecha_asignacion": asignacion.get("fecha_inicio"),
                        "fecha_fin": asignacion.get("fecha_fin"),
                        "descripcionitem": asignacion.get("descripcionitem", ""),
                        "detalleitem": asignacion.get("detalleitem", ""),
                        "cliente_nombre": cliente_nombre,
                        "costo_produccion": asignacion.get("costoproduccion", 0),
                        "imagenes": asignacion.get("imagenes", []),
                        "orden": orden,
                        "estado_subestado": asignacion.get("estado_subestado", "pendiente")
                    }
                    
                    # Verificar si ya existe esta asignación
                    asignacion_existente = collections["asignaciones"].find_one({
                        "pedido_id": pedido_id,
                        "item_id": nueva_asignacion["item_id"],
                        "modulo": modulo
                    })
                    
                    if not asignacion_existente:
                        resultado = collections["asignaciones"].insert_one(nueva_asignacion)
                        nueva_asignacion["_id"] = str(resultado.inserted_id)
                        asignaciones_migradas.append(nueva_asignacion)
                        print(f"DEBUG MIGRAR: Asignación migrada - {modulo} - {nueva_asignacion['descripcionitem']}")
                    else:
                        print(f"DEBUG MIGRAR: Asignación ya existe - {modulo} - {nueva_asignacion['descripcionitem']}")
        
        print(f"DEBUG MIGRAR: Migración completada - {len(asignaciones_migradas)} asignaciones migradas")
        
        return {
            "message": f"Migración completada exitosamente",
            "asignaciones_migradas": len(asignaciones_migradas),
            "pedidos_procesados": len(pedidos),
            "asignaciones": asignaciones_migradas[:10],  # Mostrar solo las primeras 10
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR MIGRAR: Error al migrar datos: {e}")
        raise HTTPException(status_code=500, detail=f"Error al migrar datos reales: {str(e)}")

@router.get("/asignaciones/datos-reales")
async def get_datos_reales_dashboard():
    """Obtener datos reales directamente del seguimiento de pedidos para el dashboard"""
    try:
        collections = get_collections()
        
        print(f"DEBUG DATOS REALES: Obteniendo datos reales del seguimiento")
        
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
            # Lookup para obtener las imágenes del item desde inventario
            {
                "$lookup": {
                    "from": "inventario",
                    "localField": "item_id",
                    "foreignField": "_id",
                    "as": "item_info"
                }
            },
            {
                "$addFields": {
                    "imagenes_item": {
                        "$cond": {
                            "if": {"$gt": [{"$size": "$item_info"}, 0]},
                            "then": {
                                "$filter": {
                                    "input": {
                                        "$concatArrays": [
                                            {"$ifNull": ["$item_info.imagen1", []]},
                                            {"$ifNull": ["$item_info.imagen2", []]},
                                            {"$ifNull": ["$item_info.imagen3", []]}
                                        ]
                                    },
                                    "cond": {"$ne": ["$$this", ""]}
                                }
                            },
                            "else": []
                        }
                    }
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "cliente_nombre": 1,
                    "pedido_id": 1,
                    "item_id": 1,
                    "empleado_id": 1,
                    "empleado_nombre": 1,
                    "modulo": 1,
                    "estado": 1,
                    "estado_subestado": 1,
                    "fecha_asignacion": 1,
                    "fecha_fin": 1,
                    "descripcionitem": 1,
                    "detalleitem": 1,
                    "costo_produccion": 1,
                    "imagenes": 1,
                    "imagenes_item": 1,  # Nuevas imágenes del item
                    "orden": 1
                }
            },
            {
                "$sort": {"orden": 1, "fecha_asignacion": -1}
            }
        ]
        
        asignaciones = list(collections["pedidos"].aggregate(pipeline))
        
        # Convertir ObjectId a string para JSON
        for asignacion in asignaciones:
            asignacion["pedido_id"] = str(asignacion["pedido_id"])
            asignacion["item_id"] = str(asignacion["item_id"])
            if asignacion.get("_id"):
                asignacion["_id"] = str(asignacion["_id"])
        
        print(f"DEBUG DATOS REALES: Encontradas {len(asignaciones)} asignaciones reales")
        
        return {
            "asignaciones": asignaciones,
            "total": len(asignaciones),
            "fuente": "seguimiento_pedidos",
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR DATOS REALES: Error al obtener datos reales: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener datos reales: {str(e)}")

@router.get("/asignaciones/todas-sin-filtro")
async def get_todas_asignaciones_sin_filtro():
    """Endpoint temporal para ver todas las asignaciones sin filtro de estado"""
    try:
        collections = get_collections()
        
        print(f"DEBUG TODAS: Obteniendo TODAS las asignaciones sin filtro de estado")
        
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
            # Lookup para obtener las imágenes del item desde inventario
            {
                "$lookup": {
                    "from": "inventario",
                    "localField": "item_id",
                    "foreignField": "_id",
                    "as": "item_info"
                }
            },
            {
                "$addFields": {
                    "imagenes_item": {
                        "$cond": {
                            "if": {"$gt": [{"$size": "$item_info"}, 0]},
                            "then": {
                                "$filter": {
                                    "input": {
                                        "$concatArrays": [
                                            {"$ifNull": ["$item_info.imagen1", []]},
                                            {"$ifNull": ["$item_info.imagen2", []]},
                                            {"$ifNull": ["$item_info.imagen3", []]}
                                        ]
                                    },
                                    "cond": {"$ne": ["$$this", ""]}
                                }
                            },
                            "else": []
                        }
                    }
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "cliente_nombre": 1,
                    "pedido_id": 1,
                    "item_id": 1,
                    "empleado_id": 1,
                    "empleado_nombre": 1,
                    "modulo": 1,
                    "estado": 1,
                    "estado_subestado": 1,
                    "fecha_asignacion": 1,
                    "fecha_fin": 1,
                    "descripcionitem": 1,
                    "detalleitem": 1,
                    "costo_produccion": 1,
                    "imagenes": 1,
                    "imagenes_item": 1,
                    "orden": 1
                }
            },
            {
                "$sort": {"orden": 1, "fecha_asignacion": -1}
            },
            {
                "$limit": 10  # Solo las primeras 10 para prueba
            }
        ]
        
        asignaciones = list(collections["pedidos"].aggregate(pipeline))
        
        # Convertir ObjectId a string para JSON
        for asignacion in asignaciones:
            asignacion["pedido_id"] = str(asignacion["pedido_id"])
            asignacion["item_id"] = str(asignacion["item_id"])
            if asignacion.get("_id"):
                asignacion["_id"] = str(asignacion["_id"])
        
        print(f"DEBUG TODAS: Encontradas {len(asignaciones)} asignaciones (todas)")
        
        return {
            "asignaciones": asignaciones,
            "total": len(asignaciones),
            "fuente": "seguimiento_pedidos_todas",
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR TODAS: Error al obtener todas las asignaciones: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener todas las asignaciones: {str(e)}")

@router.get("/asignaciones/test-migracion")
async def test_migracion_dashboard():
    """Endpoint de prueba para verificar si hay datos para migrar"""
    try:
        collections = get_collections()
        
        print(f"DEBUG TEST: Verificando datos para migración")
        
        # Contar pedidos con seguimiento
        pedidos_con_seguimiento = collections["pedidos"].count_documents({
            "seguimiento": {"$exists": True, "$ne": []}
        })
        
        # Contar asignaciones existentes en dashboard
        asignaciones_existentes = collections["asignaciones"].count_documents({})
        
        # Obtener muestra de datos
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
                    "cliente_nombre": 1,
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
                    "empleado_id": "$seguimiento.asignaciones_articulos.empleadoId",
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
                "$limit": 5
            }
        ]
        
        muestra_datos = list(collections["pedidos"].aggregate(pipeline))
        
        # Convertir ObjectId a string
        for item in muestra_datos:
            item["pedido_id"] = str(item["pedido_id"])
        
        print(f"DEBUG TEST: Pedidos con seguimiento: {pedidos_con_seguimiento}")
        print(f"DEBUG TEST: Asignaciones en dashboard: {asignaciones_existentes}")
        print(f"DEBUG TEST: Muestra de datos: {len(muestra_datos)}")
        
        return {
            "pedidos_con_seguimiento": pedidos_con_seguimiento,
            "asignaciones_en_dashboard": asignaciones_existentes,
            "necesita_migracion": pedidos_con_seguimiento > 0 and asignaciones_existentes == 0,
            "muestra_datos": muestra_datos,
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR TEST: Error al verificar datos: {e}")
        raise HTTPException(status_code=500, detail=f"Error al verificar datos: {str(e)}")

@router.post("/asignaciones/asignar")
async def asignar_articulo_a_empleado(
    pedido_id: str = Body(...),
    item_id: str = Body(...),
    empleado_id: str = Body(...),
    modulo: str = Body(...),
    current_user = Depends(get_current_user)
):
    """Asignar un artículo específico a un empleado desde los módulos de producción"""
    try:
        collections = get_collections()
        
        print(f"DEBUG ASIGNAR: Iniciando asignación de artículo")
        print(f"DEBUG ASIGNAR: pedido_id={pedido_id}, item_id={item_id}, empleado_id={empleado_id}, modulo={modulo}")
        
        # 1. Verificar que el empleado existe
        empleado = collections["empleados"].find_one({"identificador": empleado_id})
        if not empleado:
            print(f"ERROR ASIGNAR: Empleado no encontrado: {empleado_id}")
            raise HTTPException(status_code=404, detail="Empleado no encontrado")
        
        empleado_nombre = empleado.get("nombreCompleto", empleado_id)
        print(f"DEBUG ASIGNAR: Empleado encontrado: {empleado_nombre}")
        
        # 2. Obtener información del pedido e item
        pedido_obj_id = ObjectId(pedido_id)
        pedido = collections["pedidos"].find_one({"_id": pedido_obj_id})
        
        if not pedido:
            print(f"ERROR ASIGNAR: Pedido no encontrado: {pedido_id}")
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        # Buscar el item específico en el pedido
        item_encontrado = None
        for item in pedido.get("items", []):
            if str(item.get("id")) == item_id:
                item_encontrado = item
                break
        
        if not item_encontrado:
            print(f"ERROR ASIGNAR: Item no encontrado en pedido: {item_id}")
            raise HTTPException(status_code=404, detail="Item no encontrado en el pedido")
        
        print(f"DEBUG ASIGNAR: Item encontrado: {item_encontrado.get('descripcion', 'Sin descripción')}")
        
        # 3. Crear la asignación
        nueva_asignacion = {
            "pedido_id": pedido_id,
            "item_id": item_id,
            "empleado_id": empleado_id,
            "empleado_nombre": empleado_nombre,
            "modulo": modulo,
            "estado": "en_proceso",
            "fecha_asignacion": datetime.now(),
            "fecha_fin": None,
            "descripcionitem": item_encontrado.get("descripcion", ""),
            "detalleitem": item_encontrado.get("detalle", ""),
            "cliente_nombre": pedido.get("cliente", {}).get("nombre", ""),
            "costo_produccion": item_encontrado.get("costoproduccion", 0),
            "imagenes": item_encontrado.get("imagenes", [])
        }
        
        # 4. Insertar la asignación
        resultado = collections["asignaciones"].insert_one(nueva_asignacion)
        asignacion_id = str(resultado.inserted_id)
        
        print(f"DEBUG ASIGNAR: Asignación creada con ID: {asignacion_id}")
        
        return {
            "message": "Artículo asignado exitosamente",
            "success": True,
            "asignacion_id": asignacion_id,
            "empleado_nombre": empleado_nombre,
            "modulo": modulo,
            "descripcionitem": nueva_asignacion["descripcionitem"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR ASIGNAR: Error inesperado: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

