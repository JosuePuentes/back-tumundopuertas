from typing import List, Optional, Union
from fastapi import APIRouter, HTTPException, Body, Depends, Query
from bson import ObjectId
from datetime import datetime, timedelta, timezone
import os
from ..config.mongodb import pedidos_collection, db, items_collection, clientes_collection, clientes_usuarios_collection, facturas_cliente_collection, movimientos_logisticos_collection
transacciones_collection = db["transacciones"]
from ..models.authmodels import Pedido
from ..auth.auth import get_current_user, get_current_cliente
from pydantic import BaseModel

router = APIRouter()

# Control de logs: solo mostrar en desarrollo
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"
def debug_log(*args, **kwargs):
    """Función para logs de debug - solo muestra en modo DEBUG"""
    if DEBUG_MODE:
        print(*args, **kwargs)

# Modelo Pydantic para cancelar pedidos
class CancelarPedidoRequest(BaseModel):
    motivo_cancelacion: str

metodos_pago_collection = db["metodos_pago"]
empleados_collection = db["empleados"]
# items_collection ya está importado de mongodb.py como db["INVENTARIO"]
# NO redefinir aquí con minúsculas, usar la importación correcta
comisiones_collection = db["comisiones"]
apartados_collection = db["apartados"]  # Colección para módulo APARTADO

def obtener_siguiente_modulo(orden_actual: int) -> str:
    """Determinar el siguiente módulo según el orden actual"""
    flujo = {
        1: "masillar",      # Herrería → Masillar/Pintura
        2: "manillar",      # Masillar/Pintura → Manillar
        3: "listo_facturar" # Manillar → Listo para Facturar
    }
    return flujo.get(orden_actual, "completado")

def excluir_pedidos_web(query: dict) -> dict:
    """
    Agrega filtro para excluir pedidos web (tipo_pedido: "web") de una consulta.
    Incluye pedidos internos y pedidos sin tipo_pedido (retrocompatibilidad).
    """
    if "$and" in query:
        # Si ya tiene $and, agregar el filtro de exclusión
        query["$and"].append({
            "$or": [
                {"tipo_pedido": {"$ne": "web"}},
                {"tipo_pedido": {"$exists": False}}
            ]
        })
    else:
        # Si no tiene $and, crear uno
        query = {
            "$and": [
                query,
                {
                    "$or": [
                        {"tipo_pedido": {"$ne": "web"}},
                        {"tipo_pedido": {"$exists": False}}
                    ]
                }
            ]
        }
    return query

def excluir_pedidos_tu_mundo_puerta(query: dict) -> dict:
    """
    Agrega filtro para excluir pedidos de TU MUNDO PUERTA (RIF: J-507172554) de una consulta.
    Busca el cliente por RIF y excluye sus pedidos por cliente_id o cliente_nombre.
    """
    try:
        # Buscar el cliente TU MUNDO PUERTA por RIF
        cliente_tumundo = clientes_collection.find_one({"rif": "J-507172554"})
        if cliente_tumundo:
            cliente_tumundo_id = str(cliente_tumundo["_id"])
            
            # Crear condición de exclusión
            exclusion_condition = {
                "$and": [
                    {"cliente_id": {"$ne": cliente_tumundo_id}},
                    {"cliente_nombre": {"$not": {"$regex": "TU MUNDO.*PUERTA", "$options": "i"}}}
                ]
            }
            
            # Agregar a la query existente
            if "$and" in query:
                query["$and"].append(exclusion_condition)
            else:
                query = {
                    "$and": [
                        query,
                        exclusion_condition
                    ]
                }
    except Exception as e:
        # Si hay error, no fallar silenciosamente pero registrar
        print(f"WARNING: Error al excluir pedidos de TU MUNDO PUERTA: {e}")
        # Como alternativa, usar solo filtro por nombre
        if "$and" in query:
            query["$and"].append({
                "cliente_nombre": {"$not": {"$regex": "TU MUNDO.*PUERTA", "$options": "i"}}
            })
        else:
            query = {
                "$and": [
                    query,
                    {"cliente_nombre": {"$not": {"$regex": "TU MUNDO.*PUERTA", "$options": "i"}}}
                ]
            }
    
    return query

def enriquecer_pedido_con_datos_cliente(pedido: dict):
    """
    Enriquece un pedido con datos del cliente (cédula y teléfono) desde la colección de clientes.
    Si el cliente no existe, mantiene los valores por defecto.
    """
    cliente_id = pedido.get("cliente_id")
    if not cliente_id:
        return
    
    try:
        # Intentar buscar en clientes_collection primero
        cliente_obj_id = ObjectId(cliente_id)
        cliente = clientes_collection.find_one({"_id": cliente_obj_id})
        
        # Si no se encuentra, buscar en clientes_usuarios_collection
        if not cliente:
            cliente = clientes_usuarios_collection.find_one({"_id": cliente_obj_id})
        
        if cliente:
            # Obtener cédula/RIF
            cedula = cliente.get("cedula") or cliente.get("rif", "")
            # Obtener teléfono
            telefono = cliente.get("telefono") or cliente.get("telefono_contacto", "")
            
            # Agregar datos del cliente al pedido si no están presentes
            if cedula:
                pedido["cliente_cedula"] = cedula
            if telefono:
                pedido["cliente_telefono"] = telefono
    except Exception as e:
        # Si hay error al convertir ObjectId o buscar, simplemente no agregar datos
        print(f"Advertencia: No se pudo obtener datos del cliente {cliente_id}: {str(e)}")
        pass

@router.get("/all/")
async def get_all_pedidos():
    # Obtener todos los pedidos, excluyendo los pedidos web (tipo_pedido: "web")
    # Incluir pedidos internos (tipo_pedido: "interno") y pedidos sin tipo_pedido (retrocompatibilidad)
    query = {
        "$or": [
            {"tipo_pedido": {"$ne": "web"}},  # No es web
            {"tipo_pedido": {"$exists": False}}  # No tiene tipo_pedido (pedidos antiguos)
        ]
    }
    # Excluir pedidos web
    query = excluir_pedidos_web(query)
    # Excluir pedidos de TU MUNDO PUERTA (RIF: J-507172554)
    query = excluir_pedidos_tu_mundo_puerta(query)
    # Excluir todos los pedidos cancelados
    query["estado_general"] = {"$ne": "cancelado"}
    
    pedidos = list(pedidos_collection.find(query))
    for pedido in pedidos:
        pedido["_id"] = str(pedido["_id"])
        # Normalizar adicionales: None o no existe → []
        if "adicionales" not in pedido or pedido["adicionales"] is None:
            pedido["adicionales"] = []
        # Enriquecer con datos del cliente (cédula y teléfono)
        enriquecer_pedido_con_datos_cliente(pedido)
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
    if seguimiento is None:
        seguimiento = []
    
    procesos_info = []
    for i, sub in enumerate(seguimiento):
        if sub is None:
            continue
        asignaciones_articulos = sub.get("asignaciones_articulos", [])
        if asignaciones_articulos is None:
            asignaciones_articulos = []
            
        proceso_info = {
            "indice": i,
            "orden": sub.get("orden"),
            "estado": sub.get("estado"),
            "nombre": sub.get("nombre", "SIN_NOMBRE"),
            "asignaciones_count": len(asignaciones_articulos),
            "asignaciones": []
        }
        
        # Detalles de asignaciones
        for j, asignacion in enumerate(asignaciones_articulos):
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
    # Filtrar para excluir pedidos web
    filtro = {"orden": orden}
    filtro = excluir_pedidos_web(filtro)
    pedidos = list(pedidos_collection.find(filtro))
    for pedido in pedidos:
        pedido["_id"] = str(pedido["_id"])
    return pedidos

@router.get("/id/{pedido_id}/")
async def get_pedido(pedido_id: str):
    """
    Obtener un pedido por ID.
    Si es un pedido web (tipo_pedido: "web"), solo se puede acceder desde el módulo de pedidos-web.
    Para otros módulos, los pedidos web están bloqueados.
    """
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
    
    # Verificar si es un pedido web - si lo es, bloquear el acceso desde módulos internos
    tipo_pedido = pedido.get("tipo_pedido")
    if tipo_pedido == "web":
        # Los pedidos web solo se pueden ver desde GET /pedidos/cliente/{cliente_id}
        # Este endpoint está bloqueado para pedidos web
        raise HTTPException(
            status_code=403, 
            detail="Los pedidos web solo pueden ser vistos desde el módulo de pedidos-web"
        )
    
    pedido["_id"] = str(pedido["_id"])
    # Normalizar adicionales: None o no existe → []
    if "adicionales" not in pedido or pedido.get("adicionales") is None:
        pedido["adicionales"] = []
    # Enriquecer con datos del cliente (cédula y teléfono)
    enriquecer_pedido_con_datos_cliente(pedido)
    return pedido

@router.post("/")
async def create_pedido(pedido: Pedido, user: dict = Depends(get_current_user)):
    pedido.creado_por = user.get("usuario")
    
    # Salvaguarda para cliente con RIF específico: forzar producción
    try:
        rif_cliente = str(getattr(pedido, "cliente_id", "") or pedido.dict().get("cliente_id", "")).upper().replace(" ", "")
        if rif_cliente == "J-507172554":
            print("[AUDITORIA] Regla especial aplicada (RIF J-507172554): forzando items a produccion y desactivando todos_items_disponibles")
            # Forzar todos los items a estado pendiente/producción
            for item in pedido.items:
                try:
                    item.estado_item = 0
                except Exception:
                    pass
            # Asegurar estado general pendiente
            try:
                if getattr(pedido, "estado_general", None) != "pendiente":
                    pedido.estado_general = "pendiente"
            except Exception:
                pass
            # Si llega el flag 'todos_items_disponibles', desactivarlo
            try:
                if isinstance(getattr(pedido, "__dict__", None), dict) and "todos_items_disponibles" in pedido.__dict__:
                    pedido.__dict__["todos_items_disponibles"] = False
            except Exception:
                pass
    except Exception as e:
        print(f"[WARN] No se pudo evaluar salvaguarda por RIF: {e}")
    
    # Asegurar que cada item tenga estado_item si no viene del frontend
    for item in pedido.items:
        if not hasattr(item, 'estado_item') or item.estado_item is None:
            item.estado_item = 0  # Estado pendiente
    
    debug_log("Creando pedido:", pedido)
    
    # Marcar el pedido como tipo "interno" (desde /crearpedido)
    pedido_dict = pedido.dict()
    pedido_dict["tipo_pedido"] = "interno"
    
    # Insertar el pedido
    result = pedidos_collection.insert_one(pedido_dict)
    pedido_id = str(result.inserted_id)

    # Generar asignaciones unitarias para herrería (orden 1) por cada unidad pendiente (estado_item == 0)
    try:
        pedido_db = pedidos_collection.find_one({"_id": ObjectId(pedido_id)}) or pedido_dict
        seguimiento = pedido_db.get("seguimiento") or []

        # Ubicar proceso de herrería por orden 1 o por nombre
        orden_herreria = 1
        proceso_herreria = None
        for proc in seguimiento:
            if proc.get("orden") == orden_herreria or (
                str(proc.get("nombre_subestado", "")).strip().lower().startswith("herreria")
            ):
                proceso_herreria = proc
                break

        if not proceso_herreria:
            proceso_herreria = {
                "orden": orden_herreria,
                "nombre_subestado": "Herreria / soldadura",
                "estado": "pendiente",
                "asignaciones_articulos": [],
                "fecha_inicio": None,
                "fecha_fin": None,
            }
            seguimiento.append(proceso_herreria)

        asignaciones_articulos = proceso_herreria.get("asignaciones_articulos") or []

        items_src = pedido_db.get("items", [])
        items_iter = []
        for it in items_src:
            if hasattr(it, "dict"):
                items_iter.append(it.dict())
            else:
                items_iter.append(it)

        for it in items_iter:
            estado_item_val = it.get("estado_item", 0)
            cantidad_val = int(it.get("cantidad", 0) or 0)
            if estado_item_val == 0 and cantidad_val > 0:
                item_id_ref = str(it.get("id") or it.get("_id") or "")
                for idx in range(cantidad_val):
                    asignaciones_articulos.append({
                        "itemId": item_id_ref,
                        "empleadoId": None,
                        "nombreempleado": None,
                        "estado": "pendiente",
                        "fecha_inicio": None,
                        "fecha_fin": None,
                        "modulo": "herreria",
                        "cantidad": 1,
                        "unidad_index": idx + 1,
                    })

        proceso_herreria["asignaciones_articulos"] = asignaciones_articulos

        pedidos_collection.update_one(
            {"_id": ObjectId(pedido_id)},
            {"$set": {"seguimiento": seguimiento}},
        )
    except Exception as e:
        print(f"ERROR CREAR PEDIDO - asignaciones herreria: {e}")
    
    # Registrar movimientos logísticos para items que van a producción (estado_item = 0)
    for idx, item in enumerate(pedido.items):
        estado_item = getattr(item, 'estado_item', None) if hasattr(item, 'estado_item') else (item.get('estado_item') if isinstance(item, dict) else None)
        codigo = getattr(item, 'codigo', None) if hasattr(item, 'codigo') else (item.get('codigo') if isinstance(item, dict) else None)
        cantidad = getattr(item, 'cantidad', None) if hasattr(item, 'cantidad') else (item.get('cantidad') if isinstance(item, dict) else None)
        item_id = getattr(item, 'id', None) if hasattr(item, 'id') else (item.get('id') if isinstance(item, dict) else None)
        nombre = getattr(item, 'nombre', None) if hasattr(item, 'nombre') else (item.get('nombre') if isinstance(item, dict) else None)
        
        # Registrar movimiento para items que van a producción
        if estado_item == 0 and cantidad and cantidad > 0 and codigo:
            try:
                registrar_movimiento_logistico(
                    item_id=str(item_id) if item_id else str(codigo),
                    item_codigo=str(codigo),
                    item_nombre=nombre or codigo,
                    tipo_movimiento="crear_pedido",
                    cantidad=float(cantidad),
                    pedido_id=pedido_id
                )
            except Exception as e:
                debug_log(f"ERROR REGISTRAR MOVIMIENTO CREAR PEDIDO: {e}")
    
    # Restar cantidades del inventario SOLO para items con estado_item = 4 (disponibles)
    # Los items con estado_item = 0 (faltantes) NO se restan del inventario, van a producción
    debug_log(f"DEBUG CREAR PEDIDO: Procesando {len(pedido.items)} items para restar inventario")
    for idx, item in enumerate(pedido.items):
        # Obtener valores de manera segura (puede ser objeto Pydantic o dict después de .dict())
        estado_item = getattr(item, 'estado_item', None) if hasattr(item, 'estado_item') else (item.get('estado_item') if isinstance(item, dict) else None)
        codigo = getattr(item, 'codigo', None) if hasattr(item, 'codigo') else (item.get('codigo') if isinstance(item, dict) else None)
        cantidad = getattr(item, 'cantidad', None) if hasattr(item, 'cantidad') else (item.get('cantidad') if isinstance(item, dict) else None)
        item_id = getattr(item, 'id', None) if hasattr(item, 'id') else (item.get('id') if isinstance(item, dict) else None)
        
        debug_log(f"DEBUG CREAR PEDIDO [Item {idx}]: código='{codigo}', estado_item={estado_item}, cantidad={cantidad}, id='{item_id}'")
        
        # Solo restar del inventario si estado_item = 4 (disponible) y tiene cantidad
        if estado_item == 4 and cantidad and cantidad > 0:
            debug_log(f"DEBUG CREAR PEDIDO [Item {idx}]: Item calificado para restar inventario (estado_item=4, cantidad={cantidad})")
            
            try:
                # Buscar el item en el inventario por código o ID
                item_inventario = None
                
                # Intentar buscar por código primero (múltiples variantes)
                if codigo:
                    # Limpiar el código: quitar espacios al inicio y final
                    codigo_limpio = str(codigo).strip()
                    
                    # 1. Buscar exacto
                    item_inventario = items_collection.find_one({"codigo": codigo_limpio})
                    if not item_inventario:
                        # 2. Buscar con regex (insensible a mayúsculas/minúsculas y espacios)
                        codigo_regex = codigo_limpio.replace(" ", "\\s*")
                        item_inventario = items_collection.find_one({"codigo": {"$regex": f"^{codigo_regex}$", "$options": "i"}})
                        if not item_inventario:
                            # 3. Buscar como número si el código es numérico
                            try:
                                if codigo_limpio.isdigit() or (codigo_limpio.replace('.', '', 1).isdigit()):
                                    codigo_num = int(float(codigo_limpio))
                                    item_inventario = items_collection.find_one({"codigo": str(codigo_num)})
                                    if not item_inventario:
                                        item_inventario = items_collection.find_one({"codigo": codigo_num})
                            except:
                                pass
                
                # Si no se encontró por código, intentar por ID
                if not item_inventario and item_id:
                    try:
                        item_obj_id = ObjectId(item_id)
                        item_inventario = items_collection.find_one({"_id": item_obj_id})
                    except Exception:
                        pass
                
                if item_inventario:
                    # Obtener la sucursal del pedido (por defecto sucursal1)
                    sucursal = getattr(pedido, 'sucursal', None) or pedido.dict().get('sucursal', 'sucursal1')
                    if sucursal not in ['sucursal1', 'sucursal2']:
                        sucursal = 'sucursal1'  # Valor por defecto si no es válido
                    
                    # Determinar qué campo de existencia usar según la sucursal
                    # Sucursal 1 usa "cantidad" o "existencia", Sucursal 2 usa "existencia2"
                    campo_existencia = "cantidad" if sucursal == "sucursal1" else "existencia2"
                    
                    # Si es sucursal1 y no existe "cantidad", usar "existencia" como fallback
                    if sucursal == "sucursal1" and campo_existencia not in item_inventario:
                        campo_existencia = "existencia"
                    
                    cantidad_actual = item_inventario.get(campo_existencia, 0.0)
                    cantidad_a_restar = float(cantidad)
                    
                    debug_log(f"DEBUG CREAR PEDIDO [Item {idx}]: Sucursal={sucursal}, Campo={campo_existencia}, Cantidad actual={cantidad_actual}, Cantidad a restar={cantidad_a_restar}")
                    
                    if cantidad_a_restar > cantidad_actual:
                        debug_log(f"WARNING CREAR PEDIDO [Item {idx}]: No hay suficiente existencia en {sucursal} para {item_inventario.get('codigo', 'N/A')}. Existencia: {cantidad_actual}, Requerida: {cantidad_a_restar}")
                        # No lanzar error, solo registrar warning ya que el frontend ya validó
                    
                    # Restar la cantidad del inventario según la sucursal
                    nueva_cantidad = max(0, cantidad_actual - cantidad_a_restar)
                    items_collection.update_one(
                        {"_id": item_inventario["_id"]},
                        {"$set": {campo_existencia: nueva_cantidad}}
                    )
            except Exception as e:
                debug_log(f"ERROR CREAR PEDIDO [Item {idx}]: Error al actualizar inventario para item código='{codigo}': {e}")
    
    # Si hay abonos iniciales en el historial_pagos, incrementar el saldo de los métodos de pago
    if pedido.historial_pagos:
        debug_log(f"DEBUG CREAR PEDIDO: Procesando {len(pedido.historial_pagos)} abonos iniciales")
        for pago in pedido.historial_pagos:
            if pago.metodo and pago.monto and pago.monto > 0:
                debug_log(f"DEBUG CREAR PEDIDO: Procesando abono de {pago.monto} con método {pago.metodo}")
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
                        
                        # Actualizar saldo usando $inc (operación atómica)
                        result_update = metodos_pago_collection.update_one(
                            {"_id": metodo_pago["_id"]},
                            {"$inc": {"saldo": pago.monto}}
                        )
                        print(f"DEBUG CREAR PEDIDO: Resultado de actualización: {result_update.modified_count} documentos modificados")
                        
                        # Registrar transacción automáticamente (depósito)
                        try:
                            transaccion_deposito = {
                                "metodo_pago_id": str(metodo_pago["_id"]),
                                "tipo": "deposito",
                                "monto": float(pago.monto),
                                "concepto": pago.get("concepto") or f"Pago inicial de pedido {pedido_id}",
                                "pedido_id": pedido_id,
                                "fecha": datetime.utcnow().isoformat()
                            }
                            transacciones_collection.insert_one(transaccion_deposito)
                            print(f"DEBUG CREAR PEDIDO: Transacción de depósito registrada automáticamente para método '{metodo_pago.get('nombre', 'SIN_NOMBRE')}'")
                        except Exception as trans_error:
                            print(f"ERROR CREAR PEDIDO: Error al registrar transacción de depósito: {trans_error}")
                            # No interrumpimos el flujo si falla el registro de transacción
                            # pero logueamos el error para debugging
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
    print(f"Numero orden recibido: {numero_orden}")
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
    
    # Debug: mostrar todos los órdenes disponibles
    print(f"Órdenes disponibles en seguimiento: {[str(sub.get('orden')) for sub in seguimiento]}")
    print(f"Buscando orden: {numero_orden}")

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

# Endpoint OPTIONS específico para herreria
@router.options("/herreria/")
async def options_herreria():
    """Manejar solicitudes OPTIONS para /pedidos/herreria/ sin validación de parámetros"""
    return {"message": "OK"}

@router.get("/herreria/")
async def get_pedidos_herreria(
    ordenar: str = Query("fecha_desc", description="Ordenamiento: fecha_desc, fecha_asc, estado, cliente"),
    limite: int = Query(100, ge=1, le=1000, description="Límite de resultados (1-1000)")
):
    """Obtener ITEMS individuales para producción - Items pendientes (0) y en proceso (1-3)"""
    try:
        # Buscar solo pedidos internos (excluir pedidos web)
        # Incluir pedidos internos (tipo_pedido: "interno") y pedidos sin tipo_pedido (retrocompatibilidad)
        query = {
            "$or": [
                {"tipo_pedido": {"$ne": "web"}},  # No es web
                {"tipo_pedido": {"$exists": False}}  # No tiene tipo_pedido (pedidos antiguos)
            ]
        }
        pedidos = list(pedidos_collection.find(query, {
            "_id": 1,
            "numero_orden": 1,
            "cliente_nombre": 1,
            "fecha_creacion": 1,
            "estado_general": 1,
            "items": 1,
            "seguimiento": 1,
            "tipo_pedido": 1
        }))
        
        # Convertir a items individuales
        items_individuales = []
        
        for pedido in pedidos:
            # Verificación adicional: saltar pedidos web por si acaso
            tipo_pedido = pedido.get("tipo_pedido")
            if tipo_pedido == "web":
                continue
            pedido_id = str(pedido["_id"])
            
            # Filtrar items pendientes (0) y en proceso (1-3)
            for item in pedido.get("items", []):
                estado_item = item.get("estado_item", 0)  # Default 0
                
                if estado_item in [0, 1, 2, 3]:  # Pendientes y en proceso
                    # Crear item individual con información del pedido
                    item_individual = {
                        "id": item.get("id", str(item.get("_id", ""))),
                        "pedido_id": pedido_id,
                        "item_id": str(item.get("_id", item.get("id", ""))),
                        "numero_orden": pedido.get("numero_orden", ""),
                        "cliente_nombre": pedido.get("cliente_nombre", ""),
                        "fecha_creacion": pedido.get("fecha_creacion", ""),
                        "estado_general_pedido": pedido.get("estado_general", ""),
                        "descripcion": item.get("descripcion", ""),
                        "nombre": item.get("nombre", ""),
                        "categoria": item.get("categoria", ""),
                        "precio": item.get("precio", 0),
                        "costo": item.get("costo", 0),
                        "costoProduccion": item.get("costoProduccion", 0),
                        "cantidad": item.get("cantidad", 1),
                        "detalleitem": item.get("detalleitem", ""),
                        "imagenes": item.get("imagenes", []),
                        "estado_item": estado_item,
                        "empleado_asignado": item.get("empleado_asignado"),
                        "nombre_empleado": item.get("nombre_empleado"),
                        "modulo_actual": item.get("modulo_actual"),
                        "fecha_asignacion": item.get("fecha_asignacion")
                    }
                    items_individuales.append(item_individual)
        
        # Ordenar los items según el parámetro
        if ordenar == "fecha_desc":
            # Ordenar por fecha de creación descendente (más recientes primero)
            items_individuales.sort(key=lambda x: x.get("fecha_creacion", ""), reverse=True)
        elif ordenar == "fecha_asc":
            # Ordenar por fecha de creación ascendente (más antiguos primero)
            items_individuales.sort(key=lambda x: x.get("fecha_creacion", ""), reverse=False)
        elif ordenar == "estado":
            # Ordenar por estado_item
            items_individuales.sort(key=lambda x: x.get("estado_item", 0))
        elif ordenar == "cliente":
            # Ordenar por nombre del cliente
            items_individuales.sort(key=lambda x: x.get("cliente_nombre", ""))
        
        # Aplicar límite después del ordenamiento
        total_items = len(items_individuales)
        items_limitados = items_individuales[:limite]
        
        return {
            "items": items_limitados,
            "total_items": total_items,
            "items_mostrados": len(items_limitados),
            "limite_aplicado": limite,
            "ordenamiento": ordenar,
            "message": "Items individuales para producción"
        }
        
    except Exception as e:
        print(f"Error en get_pedidos_herreria: {e}")
        return {
            "items": [],
            "total_items": 0,
            "error": str(e)
        }

@router.put("/inicializar-estado-items/")
async def inicializar_estado_items():
    """Inicializar estado_item en 0 para todos los items que no lo tengan"""
    try:
        pedidos = list(pedidos_collection.find({}))
        items_actualizados = 0
        
        for pedido in pedidos:
            for item in pedido.get("items", []):
                if not item.get("estado_item"):
                    # Actualizar el item específico
                    result = pedidos_collection.update_one(
                        {"_id": pedido["_id"], "items.id": item["id"]},
                        {"$set": {"items.$.estado_item": 0}}  # Estado pendiente
                    )
                    if result.modified_count > 0:
                        items_actualizados += 1
        
        return {
            "message": f"Se inicializaron {items_actualizados} items con estado_item: 0",
            "items_actualizados": items_actualizados
        }
        
    except Exception as e:
        print(f"Error en inicializar_estado_items: {e}")
        return {
            "error": str(e),
            "items_actualizados": 0
        }

@router.put("/asignar-item/")
async def asignar_item(
    pedido_id: str = Body(...),
    item_id: str = Body(...),
    empleado_id: str = Body(...),
    empleado_nombre: str = Body(...),
    modulo: str = Body(...),  # "herreria", "masillar", "preparar"
    unidad_index: Optional[int] = Body(None)
):
    """
    Asignar un item a un empleado en un módulo específico
    Actualiza el estado_item según el módulo asignado
    """
    try:
        debug_log(f"DEBUG ASIGNAR ITEM: === DATOS RECIBIDOS ===")
        debug_log(f"DEBUG ASIGNAR ITEM: pedido_id={pedido_id} (tipo: {type(pedido_id)})")
        debug_log(f"DEBUG ASIGNAR ITEM: item_id={item_id} (tipo: {type(item_id)})")
        debug_log(f"DEBUG ASIGNAR ITEM: empleado_id={empleado_id} (tipo: {type(empleado_id)})")
        debug_log(f"DEBUG ASIGNAR ITEM: empleado_nombre={empleado_nombre} (tipo: {type(empleado_nombre)})")
        debug_log(f"DEBUG ASIGNAR ITEM: modulo={modulo} (tipo: {type(modulo)})")
        debug_log(f"DEBUG ASIGNAR ITEM: unidad_index={unidad_index}")
        debug_log(f"DEBUG ASIGNAR ITEM: === FIN DATOS RECIBIDOS ===")
        # Buscar el pedido
        pedido = pedidos_collection.find_one({"_id": ObjectId(pedido_id)})
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        # Mapeo de módulos a estados (SOLO para items sin estado_item definido)
        # 0 = Pendiente
        # 1 = Herrería
        # 2 = Masillar/Pintar
        # 3 = Manillar
        # 4 = Terminado
        estado_item_map = {
            "herreria": 1,
            "masillar": 2, 
            "preparar": 3
        }
        
        # OBTENER estado_item ACTUAL del item (NO forzar)
        item = None
        for item_pedido in pedido.get("items", []):
            if item_pedido.get("id") == item_id:
                item = item_pedido
                break
        
        estado_item_actual = item.get("estado_item", 0) if item else 0
        
        # Si el item ya tiene estado_item, mantenerlo. Solo establecerlo si es 0 (pendiente)
        if estado_item_actual == 0:
            nuevo_estado_item = estado_item_map.get(modulo, 1)
            debug_log(f"DEBUG ASIGNAR ITEM: Item sin estado, estableciendo según módulo: {nuevo_estado_item}")
        else:
            nuevo_estado_item = estado_item_actual  # MANTENER estado actual
            debug_log(f"DEBUG ASIGNAR ITEM: Manteniendo estado_item actual: {nuevo_estado_item}")
        
        # Buscar el empleado para obtener su nombre
        empleado = buscar_empleado_por_identificador(empleado_id)
        if empleado:
            nombre_empleado = empleado.get("nombreCompleto", empleado_nombre)
        else:
            nombre_empleado = empleado_nombre  # Usar el nombre enviado desde el frontend
            debug_log(f"DEBUG ASIGNAR ITEM: Empleado {empleado_id} no encontrado en BD, usando nombre del frontend: {empleado_nombre}")
        
        # Actualizar el item específico
        result = pedidos_collection.update_one(
            {
                "_id": ObjectId(pedido_id),
                "items.id": item_id
            },
            {
                "$set": {
                    "items.$.estado_item": nuevo_estado_item,
                    "items.$.empleado_asignado": empleado_id,
                    "items.$.nombre_empleado": nombre_empleado,
                    "items.$.modulo_actual": modulo,
                    "items.$.fecha_asignacion": datetime.now().isoformat()
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Item no encontrado en el pedido")
        
        # CREAR ASIGNACIÓN EN SEGUIMIENTO PARA DASHBOARD
        debug_log(f"DEBUG ASIGNAR ITEM: Creando asignación en seguimiento...")
        
        # Obtener el estado_item actual del item para determinar el orden correcto
        estado_item_actual = item.get("estado_item", 0) if item else 0
        
        # Determinar el orden según el estado_item del item
        # El orden debe basarse en el estado_item actual del item, NO en el módulo del frontend
        if estado_item_actual == 0 or estado_item_actual == 1:
            orden = 1  # Pendiente o Herrería -> orden 1
        elif estado_item_actual == 2:
            orden = 2  # Masillar
        elif estado_item_actual == 3:
            orden = 3  # Preparar
        else:
            # Fallback al módulo
            modulo_orden_map = {
                "herreria": 1,
                "masillar": 2, 
                "preparar": 3
            }
            orden = modulo_orden_map.get(modulo, 1)
        
        debug_log(f"DEBUG ASIGNAR ITEM: estado_item={estado_item_actual}, orden={orden}, modulo={modulo}")
        
        # Crear la asignación base (plantilla)
        nueva_asignacion = {
            "itemId": item_id,
            "empleadoId": empleado_id,
            "nombreempleado": nombre_empleado,
            "estado": "en_proceso",
            "fecha_inicio": datetime.now().isoformat(),
            "fecha_fin": None,
            "modulo": modulo,
            "descripcionitem": item.get("nombre", item.get("descripcion", "")) if item else "",
            "costoproduccion": item.get("costoProduccion", 0) if item else 0,
            "unidad_index": unidad_index
        }
        
        # Buscar o crear el proceso en seguimiento
        seguimiento = pedido.get("seguimiento") or []
        proceso_existente = None
        
        for proceso in seguimiento:
            if proceso.get("orden") == orden:
                proceso_existente = proceso
                break
        
        if proceso_existente:
            # Actualizar proceso existente con soporte para unidad_index
            debug_log(f"DEBUG ASIGNAR ITEM: Actualizando proceso existente orden {orden}")
            asignaciones_articulos = proceso_existente.get("asignaciones_articulos") or []

            # Elegir target según unidad_index o primera pendiente sin empleado
            target_index = None
            if unidad_index is not None:
                for i, asignacion in enumerate(asignaciones_articulos):
                    if (
                        asignacion.get("itemId") == item_id and
                        asignacion.get("modulo") == modulo and
                        int(asignacion.get("unidad_index", 0) or 0) == int(unidad_index)
                    ):
                        # Si ya está asignada y en pendiente/en_proceso, bloquear
                        if asignacion.get("empleadoId") and asignacion.get("estado") in ["pendiente", "en_proceso"]:
                            raise HTTPException(status_code=409, detail="Esa unidad ya está asignada")
                        # Permitir reasignar si está terminada (para reasignar en el mismo módulo)
                        # o si no tiene empleado asignado
                        target_index = i
                        break
                # Si no se encuentra en este módulo, buscar en módulos anteriores para verificar que existe
                if target_index is None:
                    # Buscar en otros órdenes del seguimiento para verificar que la unidad existe
                    unidad_existe_en_otro_modulo = False
                    for proceso in seguimiento:
                        asignaciones_otras = proceso.get("asignaciones_articulos") or []
                        for asignacion_otra in asignaciones_otras:
                            if (
                                asignacion_otra.get("itemId") == item_id and
                                int(asignacion_otra.get("unidad_index", 0) or 0) == int(unidad_index)
                            ):
                                unidad_existe_en_otro_modulo = True
                                break
                        if unidad_existe_en_otro_modulo:
                            break
                    
                    # Si la unidad existe en otro módulo o es una nueva unidad, crear nueva asignación
                    if unidad_existe_en_otro_modulo or True:  # Permitir crear nuevas asignaciones
                        # Agregar nueva asignación al array
                        nueva_asignacion_unidad = nueva_asignacion.copy()
                        nueva_asignacion_unidad["unidad_index"] = unidad_index
                        asignaciones_articulos.append(nueva_asignacion_unidad)
                        target_index = len(asignaciones_articulos) - 1
                        debug_log(f"DEBUG ASIGNAR ITEM: Creando nueva asignación para unidad_index={unidad_index} en módulo {modulo}")
                    else:
                        raise HTTPException(status_code=409, detail="Unidad solicitada no disponible para asignar")
            else:
                # Buscar primera pendiente sin empleado o terminada disponible
                for i, asignacion in enumerate(asignaciones_articulos):
                    if (
                        asignacion.get("itemId") == item_id and
                        asignacion.get("modulo") == modulo
                    ):
                        # Permitir asignar si está pendiente sin empleado
                        if asignacion.get("estado") == "pendiente" and not asignacion.get("empleadoId"):
                            target_index = i
                            break
                        # Permitir reasignar si está terminada (para reasignar en el mismo módulo)
                        elif asignacion.get("estado") == "terminado" and not asignacion.get("empleadoId"):
                            target_index = i
                            break
                # Si no se encuentra, crear una nueva asignación (unidad nueva o movida desde otro módulo)
                if target_index is None:
                    asignaciones_articulos.append(nueva_asignacion)
                    target_index = len(asignaciones_articulos) - 1
                    debug_log(f"DEBUG ASIGNAR ITEM: Creando nueva asignación para item {item_id} en módulo {modulo}")

            # Actualizar solo la asignación objetivo
            asignacion_obj = asignaciones_articulos[target_index]
            asignacion_obj.update({
                        "empleadoId": empleado_id,
                        "nombreempleado": nombre_empleado,
                        "estado": "en_proceso",
                        "fecha_inicio": datetime.now().isoformat(),
                    })
            # Preservar unidad_index existente si no vino en body
            if asignacion_obj.get("unidad_index") is None and unidad_index is not None:
                asignacion_obj["unidad_index"] = unidad_index
            asignaciones_articulos[target_index] = asignacion_obj
            debug_log(f"DEBUG ASIGNAR ITEM: Asignada unidad_index={asignacion_obj.get('unidad_index')} para item {item_id}")
            
            # Actualizar en la base de datos
            pedidos_collection.update_one(
                {
                    "_id": ObjectId(pedido_id),
                    "seguimiento.orden": orden
                },
                {
                    "$set": {
                        "seguimiento.$.asignaciones_articulos": asignaciones_articulos
                    }
                }
            )
        else:
            # Crear nuevo proceso
            debug_log(f"DEBUG ASIGNAR ITEM: Creando nuevo proceso orden {orden}")
            nuevo_proceso = {
                "orden": orden,
                "nombre_subestado": f"Módulo {modulo.title()}",
                "estado": "en_proceso",
                "asignaciones_articulos": [nueva_asignacion],
                "fecha_inicio": datetime.now().isoformat(),
                "fecha_fin": None
            }
            
            # Agregar a seguimiento
            pedidos_collection.update_one(
                {"_id": ObjectId(pedido_id)},
                {
                    "$push": {
                        "seguimiento": nuevo_proceso
                    }
                }
            )
        
        debug_log(f"DEBUG ASIGNAR ITEM: Asignación creada exitosamente en seguimiento")
        
        # Obtener información completa del item asignado
        item_asignado = None
        for item in pedido.get("items", []):
            if item.get("id") == item_id:
                item_asignado = item
                break
        
        return {
            "message": "Item asignado correctamente", 
            "estado_item": nuevo_estado_item,
            "modulo": modulo,
            "empleado": nombre_empleado,
            "item_info": {
                "id": item_asignado.get("id") if item_asignado else item_id,
                "descripcion": item_asignado.get("descripcion", "") if item_asignado else "",
                "nombre": item_asignado.get("nombre", "") if item_asignado else "",
                "categoria": item_asignado.get("categoria", "") if item_asignado else "",
                "precio": item_asignado.get("precio", 0) if item_asignado else 0,
                "costo": item_asignado.get("costo", 0) if item_asignado else 0,
                "costoProduccion": item_asignado.get("costoProduccion", 0) if item_asignado else 0,
                "cantidad": item_asignado.get("cantidad", 1) if item_asignado else 1,
                "detalleitem": item_asignado.get("detalleitem", "") if item_asignado else "",
                "imagenes": item_asignado.get("imagenes", []) if item_asignado else [],
                "empleado_asignado": empleado_id,
                "nombre_empleado": nombre_empleado,
                "modulo_actual": modulo,
                "fecha_asignacion": datetime.now().isoformat()
            },
            "pedido_info": {
                "pedido_id": pedido_id,
                "numero_orden": pedido.get("numero_orden", ""),
                "cliente_nombre": pedido.get("cliente_nombre", "")
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error asignar_item: {str(e)}")

@router.post("/asignar-bulk")
async def asignar_items_bulk(payload: dict = Body(...)):
    """Asignar múltiples unidades de múltiples items en un solo POST.

    Espera: {
      "asignaciones": [
        { "pedido_id", "item_id", "empleado_id", "empleado_nombre", "modulo", "unidad_index"? }
      ]
    }
    """
    asignaciones_req = payload.get("asignaciones") or []
    if not isinstance(asignaciones_req, list) or len(asignaciones_req) == 0:
        raise HTTPException(status_code=400, detail="'asignaciones' debe ser una lista no vacía")

    # Agrupar por pedido para minimizar I/O a BD
    from collections import defaultdict
    grupos: dict = defaultdict(list)
    for a in asignaciones_req:
        pid = a.get("pedido_id")
        if not pid:
            continue
        grupos[pid].append(a)

    resultados = []
    now_iso = datetime.now().isoformat()

    for pedido_id, asigns in grupos.items():
        try:
            pedido = pedidos_collection.find_one({"_id": ObjectId(pedido_id)})
            if not pedido:
                for a in asigns:
                    resultados.append({"pedido_id": pedido_id, "item_id": a.get("item_id"), "ok": False, "error": "Pedido no encontrado"})
                continue

            seguimiento = pedido.get("seguimiento") or []
            items_lista = pedido.get("items", [])

            # Índice de items por id para acceso rápido
            id_to_item = {}
            for it in items_lista:
                it_id = it.get("id")
                if it_id:
                    id_to_item[it_id] = it

            # Procesar asignaciones del mismo pedido en memoria
            for a in asigns:
                item_id = a.get("item_id")
                empleado_id = a.get("empleado_id")
                empleado_nombre = a.get("empleado_nombre")
                modulo = a.get("modulo")
                unidad_index = a.get("unidad_index")

                if not (item_id and empleado_id and modulo):
                    resultados.append({"pedido_id": pedido_id, "item_id": item_id, "ok": False, "error": "Faltan campos requeridos"})
                    continue

                item = id_to_item.get(item_id)
                estado_item_actual = item.get("estado_item", 0) if item else 0

                # Determinar orden basándose en estado_item, fallback a modulo
                if estado_item_actual in [0, 1]:
                    orden = 1
                elif estado_item_actual == 2:
                    orden = 2
                elif estado_item_actual == 3:
                    orden = 3
                else:
                    orden = {"herreria": 1, "masillar": 2, "preparar": 3}.get(modulo, 1)

                # Buscar o crear proceso
                proceso = None
                for p in seguimiento:
                    if p.get("orden") == orden:
                        proceso = p
                        break
                if not proceso:
                    proceso = {
                        "orden": orden,
                        "nombre_subestado": f"Módulo {modulo.title()}",
                        "estado": "en_proceso",
                        "asignaciones_articulos": [],
                        "fecha_inicio": now_iso,
                        "fecha_fin": None,
                    }
                    seguimiento.append(proceso)

                asignaciones_articulos = proceso.get("asignaciones_articulos") or []

                # Elegir target segun unidad_index o primera pendiente
                target_index = None
                if unidad_index is not None:
                    try:
                        unidad_index_int = int(unidad_index)
                    except Exception:
                        unidad_index_int = None
                    for i, asignacion in enumerate(asignaciones_articulos):
                        if (
                            asignacion.get("itemId") == item_id and
                            asignacion.get("modulo") == modulo and
                            int(asignacion.get("unidad_index", 0) or 0) == (unidad_index_int or 0)
                        ):
                            if asignacion.get("empleadoId") and asignacion.get("estado") in ["pendiente", "en_proceso"]:
                                resultados.append({"pedido_id": pedido_id, "item_id": item_id, "unidad_index": unidad_index_int, "ok": False, "error": "Esa unidad ya está asignada"})
                                target_index = None
                                break
                            target_index = i
                            break
                    if target_index is None:
                        # Si no se encontró la unidad solicitada
                        resultados.append({"pedido_id": pedido_id, "item_id": item_id, "unidad_index": unidad_index, "ok": False, "error": "Unidad solicitada no disponible para asignar"})
                        continue
                else:
                    for i, asignacion in enumerate(asignaciones_articulos):
                        if (
                            asignacion.get("itemId") == item_id and
                            asignacion.get("modulo") == modulo and
                            asignacion.get("estado") == "pendiente" and
                            not asignacion.get("empleadoId")
                        ):
                            target_index = i
                            break
                    if target_index is None:
                        resultados.append({"pedido_id": pedido_id, "item_id": item_id, "ok": False, "error": "No hay unidades pendientes para asignar"})
                        continue

                asignacion_obj = asignaciones_articulos[target_index]
                asignacion_obj.update({
                    "empleadoId": empleado_id,
                    "nombreempleado": empleado_nombre,
                    "estado": "en_proceso",
                    "fecha_inicio": now_iso,
                })
                if asignacion_obj.get("unidad_index") is None and unidad_index is not None:
                    asignacion_obj["unidad_index"] = unidad_index
                asignaciones_articulos[target_index] = asignacion_obj

                # Actualizar item meta info de forma optimista
                if item is not None:
                    if estado_item_actual == 0:
                        item["estado_item"] = {"herreria": 1, "masillar": 2, "preparar": 3}.get(modulo, 1)
                    item["empleado_asignado"] = empleado_id
                    item["nombre_empleado"] = empleado_nombre
                    item["modulo_actual"] = modulo
                    item["fecha_asignacion"] = now_iso

                resultados.append({
                    "pedido_id": pedido_id,
                    "item_id": item_id,
                    "unidad_index": asignacion_obj.get("unidad_index"),
                    "ok": True
                })

            # Persistir cambios del pedido (una sola escritura por pedido)
            pedidos_collection.update_one(
                {"_id": ObjectId(pedido_id)},
                {"$set": {"seguimiento": seguimiento, "items": items_lista}}
            )

        except HTTPException as he:
            for a in asigns:
                resultados.append({"pedido_id": pedido_id, "item_id": a.get("item_id"), "ok": False, "error": he.detail})
        except Exception as e:
            for a in asigns:
                resultados.append({"pedido_id": pedido_id, "item_id": a.get("item_id"), "ok": False, "error": str(e)})

    ok_count = sum(1 for r in resultados if r.get("ok"))
    fail_count = len(resultados) - ok_count
    return {"message": "Asignaciones procesadas", "ok": ok_count, "errores": fail_count, "resultados": resultados}


@router.put("/terminar-asignacion/")
async def terminar_asignacion(
    pedido_id: str = Body(...),
    item_id: str = Body(...),
    pin: str = Body(...)
):
    """
    Terminar una asignación y avanzar al siguiente estado
    Incrementa el estado_item en 1
    """
    try:
        # Buscar el pedido
        pedido = pedidos_collection.find_one({"_id": ObjectId(pedido_id)})
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        # Buscar el item específico
        item_encontrado = None
        for item in pedido.get("items", []):
            if item.get("id") == item_id:
                item_encontrado = item
                break
        
        if not item_encontrado:
            raise HTTPException(status_code=404, detail="Item no encontrado")
        
        estado_actual = item_encontrado.get("estado_item", 1)
        nuevo_estado = estado_actual + 1
        
        # Si llega a estado 4, el item desaparece de herreria
        if nuevo_estado > 4:
            nuevo_estado = 4  # Máximo estado
        
        # Actualizar el estado del item
        result = pedidos_collection.update_one(
            {
                "_id": ObjectId(pedido_id),
                "items.id": item_id
            },
            {
                "$set": {
                    "items.$.estado_item": nuevo_estado,
                    "items.$.fecha_terminacion": datetime.now().isoformat(),
                    "items.$.pin_usado": pin
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Item no encontrado para actualizar")
        
        return {
            "message": "Asignación terminada correctamente",
            "estado_anterior": estado_actual,
            "estado_nuevo": nuevo_estado,
            "visible_en_herreria": nuevo_estado <= 3
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error terminando asignación: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

@router.get("/item-estado/{pedido_id}/{item_id}")
async def get_item_estado(pedido_id: str, item_id: str):
    """
    Obtener el estado específico de un item
    """
    try:
        # Buscar el pedido
        pedido = pedidos_collection.find_one({"_id": ObjectId(pedido_id)})
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        # Buscar el item específico
        item_encontrado = None
        for item in pedido.get("items", []):
            if item.get("id") == item_id:
                item_encontrado = item
                break
        
        if not item_encontrado:
            raise HTTPException(status_code=404, detail="Item no encontrado")
        
        estado_item = item_encontrado.get("estado_item", 1)
        
        # Mapeo de estados a descripciones
        estado_descripcion = {
            1: "Pendiente - Herrería",
            2: "En proceso - Masillar/Pintar", 
            3: "En proceso - Manillar",
            4: "Terminado - Listo para facturar"
        }
        
        return {
            "pedido_id": pedido_id,
            "item_id": item_id,
            "estado_item": estado_item,
            "descripcion_estado": estado_descripcion.get(estado_item, "Estado desconocido"),
            "visible_en_herreria": estado_item <= 3,
            "empleado_asignado": item_encontrado.get("empleado_asignado"),
            "nombre_empleado": item_encontrado.get("nombre_empleado"),
            "modulo_actual": item_encontrado.get("modulo_actual"),
            "fecha_asignacion": item_encontrado.get("fecha_asignacion"),
            "fecha_terminacion": item_encontrado.get("fecha_terminacion")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error obteniendo estado del item: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

# NOTA: Este endpoint duplicado será ignorado por FastAPI (usa el primero)
# Se mantiene por compatibilidad pero no se ejecutará
# @router.get("/all/")
# async def get_all_pedidos():
#     """Obtener todos los pedidos para el monitor - Versión simplificada"""
#     ...

@router.get("/asignaciones-disponibles/{pedido_id}/{modulo}")
async def get_asignaciones_disponibles(pedido_id: str, modulo: str):
    """
    Obtener información detallada de unidades disponibles para asignar por item y módulo.
    Retorna estadísticas por item: total, asignadas, disponibles, y detalles de cada unidad.
    """
    try:
        # Validar pedido_id
        if not pedido_id or len(pedido_id) != 24:
            raise HTTPException(status_code=400, detail="ID de pedido inválido")
        
        # Validar modulo
        modulos_validos = ["herreria", "masillar", "preparar"]
        if modulo not in modulos_validos:
            raise HTTPException(status_code=400, detail=f"Módulo inválido. Debe ser uno de: {', '.join(modulos_validos)}")
        
        try:
            pedido_obj_id = ObjectId(pedido_id)
            pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"ID de pedido inválido: {str(e)}")
        
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        # Buscar asignaciones en el seguimiento del módulo especificado
        seguimiento = pedido.get("seguimiento", [])
        if not isinstance(seguimiento, list):
            seguimiento = []
        
        asignaciones_por_item = {}
        
        # Mapear número de orden a módulo
        orden_modulo_map = {
            "1": "herreria",
            "2": "masillar",
            "3": "preparar"
        }
        
        # Buscar en todos los procesos del seguimiento
        for proceso in seguimiento:
            if not isinstance(proceso, dict):
                continue
            
            proceso_modulo = None
            orden = proceso.get("orden")
            if orden and str(orden) in orden_modulo_map:
                proceso_modulo = orden_modulo_map[str(orden)]
            elif proceso.get("nombre_subestado", ""):
                nombre_subestado = str(proceso.get("nombre_subestado", "")).lower()
                if nombre_subestado.startswith("herreria"):
                    proceso_modulo = "herreria"
                elif nombre_subestado.startswith("masillar"):
                    proceso_modulo = "masillar"
                elif nombre_subestado.startswith("prepar"):
                    proceso_modulo = "preparar"
            
            if proceso_modulo != modulo:
                continue
            
            asignaciones_articulos = proceso.get("asignaciones_articulos", [])
            if not isinstance(asignaciones_articulos, list):
                continue
            
            for asignacion in asignaciones_articulos:
                if not isinstance(asignacion, dict):
                    continue
                
                item_id = asignacion.get("itemId")
                if not item_id:
                    continue
                
                unidad_index = asignacion.get("unidad_index", 1)
                try:
                    unidad_index = int(unidad_index) if unidad_index else 1
                except (ValueError, TypeError):
                    unidad_index = 1
                
                estado = asignacion.get("estado", "pendiente")
                empleado_id = asignacion.get("empleadoId")
                
                if item_id not in asignaciones_por_item:
                    asignaciones_por_item[item_id] = {
                        "unidades": {}
                    }
                
                # Una unidad está disponible si NO tiene empleado asignado Y NO está terminada
                disponible = not empleado_id and estado != "terminado"
                
                asignaciones_por_item[item_id]["unidades"][unidad_index] = {
                    "unidad_index": unidad_index,
                    "estado": estado,
                    "empleadoId": empleado_id,
                    "nombreempleado": asignacion.get("nombreempleado"),
                    "fecha_inicio": asignacion.get("fecha_inicio"),
                    "disponible": disponible
                }
        
        # Agregar información del item (cantidad total) y calcular estadísticas
        items = pedido.get("items", [])
        if not isinstance(items, list):
            items = []
        
        resultado = []
        
        for item in items:
            if not isinstance(item, dict):
                continue
            
            item_id = str(item.get("id") or item.get("_id") or "")
            if not item_id:
                continue
            
            cantidad_total = 0
            try:
                cantidad_total = int(item.get("cantidad", 0) or 0)
            except (ValueError, TypeError):
                cantidad_total = 0
            
            if cantidad_total <= 0:
                continue
            
            info_item = asignaciones_por_item.get(item_id, {"unidades": {}})
            if not isinstance(info_item, dict):
                info_item = {"unidades": {}}
            
            unidades_info = []
            asignadas = 0
            disponibles = 0
            terminadas = 0
            
            # Procesar unidades existentes en asignaciones
            for unidad_idx in range(1, cantidad_total + 1):
                if unidad_idx in info_item.get("unidades", {}):
                    unidad_data = info_item["unidades"][unidad_idx]
                    unidades_info.append(unidad_data)
                    if unidad_data.get("estado") == "terminado":
                        terminadas += 1
                    elif unidad_data.get("empleadoId"):
                        asignadas += 1
                    else:
                        disponibles += 1
                else:
                    # Unidad no tiene asignación, está disponible
                    unidades_info.append({
                        "unidad_index": unidad_idx,
                        "estado": "pendiente",
                        "empleadoId": None,
                        "nombreempleado": None,
                        "fecha_inicio": None,
                        "disponible": True
                    })
                    disponibles += 1
            
            resultado.append({
                "item_id": item_id,
                "item_nombre": item.get("nombre") or item.get("descripcion") or "",
                "cantidad_total": cantidad_total,
                "unidades_asignadas": asignadas,
                "unidades_disponibles": disponibles,
                "unidades_terminadas": terminadas,
                "unidades": unidades_info
            })
        
        return {
            "pedido_id": pedido_id,
            "modulo": modulo,
            "items": resultado
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR en get_asignaciones_disponibles: {str(e)}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error interno al obtener asignaciones disponibles: {str(e)}"
        )

@router.get("/item-estado/{pedido_id}/{item_id}")
async def get_item_estado(pedido_id: str, item_id: str):
    """Obtener estado detallado de un item específico"""
    try:
        # Validar IDs
        if not pedido_id or len(pedido_id) != 24:
            raise HTTPException(status_code=400, detail="ID de pedido inválido")
        if not item_id or len(item_id) != 24:
            raise HTTPException(status_code=400, detail="ID de item inválido")
        
        # Obtener el pedido
        try:
            pedido_obj_id = ObjectId(pedido_id)
            pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
        except Exception as e:
            raise HTTPException(status_code=400, detail="ID de pedido inválido")
        
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        # Encontrar el item específico
        item = None
        for i in pedido.get("items", []):
            if str(i.get("_id")) == item_id:
                item = i
                break
        
        if not item:
            raise HTTPException(status_code=404, detail="Item no encontrado")
        
        estado_item = item.get("estado_item", 1)
        
        # Obtener asignaciones del item
        asignaciones = []
        seguimiento = pedido.get("seguimiento", [])
        
        for proceso in seguimiento:
            if not isinstance(proceso, dict):
                continue
            
            asignaciones_articulos = proceso.get("asignaciones_articulos", [])
            if not isinstance(asignaciones_articulos, list):
                continue
            
            for asignacion in asignaciones_articulos:
                if not isinstance(asignacion, dict):
                    continue
                
                if str(asignacion.get("itemId")) == item_id:
                    asignaciones.append({
                        "modulo": proceso.get("orden", 1),
                        "estado": asignacion.get("estado"),
                        "empleado_id": asignacion.get("empleadoId"),
                        "empleado_nombre": asignacion.get("nombreempleado"),
                        "fecha_inicio": asignacion.get("fecha_inicio"),
                        "fecha_fin": asignacion.get("fecha_fin")
                    })
        
        # Determinar si está disponible para asignación
        disponible_para_asignacion = True
        for asignacion in asignaciones:
            if asignacion.get("estado") == "en_proceso":
                disponible_para_asignacion = False
                break
        
        return {
            "success": True,
            "pedido_id": pedido_id,
            "item_id": item_id,
            "estado_item": estado_item,
            "asignaciones": asignaciones,
            "disponible_para_asignacion": disponible_para_asignacion,
            "progreso": (estado_item / 4) * 100  # Progreso basado en estado_item
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error en get_item_estado: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@router.get("/debug-pedido-especifico/{pedido_id}")
async def debug_pedido_especifico(pedido_id: str):
    """Debuggear un pedido específico para ver por qué no aparece"""
    try:
        # Validar ID
        if not pedido_id or len(pedido_id) != 24:
            raise HTTPException(status_code=400, detail="ID de pedido inválido")
        
        # Obtener el pedido
        try:
            pedido_obj_id = ObjectId(pedido_id)
            pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
        except Exception as e:
            raise HTTPException(status_code=400, detail="ID de pedido inválido")
        
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        # Información básica del pedido
        info_pedido = {
            "_id": str(pedido["_id"]),
            "numero_orden": pedido.get("numero_orden"),
            "cliente_nombre": pedido.get("cliente_nombre"),
            "estado_general": pedido.get("estado_general"),
            "fecha_creacion": pedido.get("fecha_creacion"),
            "total_items": len(pedido.get("items", [])),
            "tiene_seguimiento": bool(pedido.get("seguimiento")),
            "seguimiento_count": len(pedido.get("seguimiento", []))
        }
        
        # Información de items
        items_info = []
        for item in pedido.get("items", []):
            items_info.append({
                "_id": str(item.get("_id")),
                "descripcion": item.get("descripcion"),
                "estado_item": item.get("estado_item"),
                "costoproduccion": item.get("costoproduccion")
            })
        
        # Información de seguimiento
        seguimiento_info = []
        for proceso in pedido.get("seguimiento", []):
            if isinstance(proceso, dict):
                seguimiento_info.append({
                    "orden": proceso.get("orden"),
                    "nombre_subestado": proceso.get("nombre_subestado"),
                    "asignaciones_count": len(proceso.get("asignaciones_articulos", []))
                })
        
        return {
            "success": True,
            "pedido_info": info_pedido,
            "items": items_info,
            "seguimiento": seguimiento_info,
            "aparece_en_herreria": pedido.get("estado_general") == "orden1",
            "tiene_items_activos": any(item.get("estado_item", 1) < 5 for item in pedido.get("items", []))
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error en debug_pedido_especifico: {e}")
        return {
            "success": False,
            "error": str(e)
        }


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
    # Devuelve todos los pedidos en estado_general orden1, orden2, orden3 (excluyendo pedidos web)
    filtro = {"estado_general": {"$in": ["orden1", "orden2", "orden3","pendiente","orden4","orden5","orden6","entregado"]}}
    filtro = excluir_pedidos_web(filtro)
    pedidos = list(pedidos_collection.find(filtro))
    for pedido in pedidos:
        pedido["_id"] = str(pedido["_id"])
    return pedidos

from fastapi import Query

@router.get("/estado/")
async def get_pedidos_por_estado(estado_general: list[str] = Query(..., description="Uno o varios estados separados por coma")):
    """
    Obtener pedidos por estado general - OPTIMIZADO
    Solo retorna pedidos con items pendientes (estado_item 0 o 1) para herrería
    """
    # Si solo se pasa uno, FastAPI lo convierte en lista de un elemento
    filtro = {"estado_general": {"$in": estado_general}}
    # Excluir pedidos web
    filtro = excluir_pedidos_web(filtro)
    # Filtrar solo pedidos que tienen items pendientes o en herrería (estado_item 0 o 1)
    filtro["items"] = {
        "$elemMatch": {
            "estado_item": {"$in": [0, 1]}  # Solo items pendientes o en herrería
        }
    }
    
    # Proyección optimizada: solo campos necesarios
    projection = {
        "_id": 1,
        "numero_orden": 1,
        "cliente_id": 1,
        "cliente_nombre": 1,
        "fecha_creacion": 1,
        "fecha_actualizacion": 1,
        "estado_general": 1,
        "items": 1,
        "seguimiento": 1,
        "adicionales": 1
    }
    
    # Limitar a 500 pedidos más recientes y ordenar por fecha descendente
    pedidos = list(pedidos_collection.find(filtro, projection)
                   .sort("fecha_creacion", -1)
                   .limit(500))
    
    # Filtrar items en memoria para mostrar solo los relevantes (estado_item 0 o 1)
    for pedido in pedidos:
        pedido["_id"] = str(pedido["_id"])
        # Filtrar items: solo mostrar los que tienen estado_item 0 o 1
        items_originales = pedido.get("items", [])
        items_filtrados = [item for item in items_originales if item.get("estado_item", 0) in [0, 1]]
        pedido["items"] = items_filtrados
        
        # Normalizar adicionales: None o no existe → []
        if "adicionales" not in pedido or pedido["adicionales"] is None:
            pedido["adicionales"] = []
        
        # NO enriquecer con datos del cliente para mejorar rendimiento (comentado temporalmente)
        # enriquecer_pedido_con_datos_cliente(pedido)
    
    # Filtrar pedidos que quedaron sin items después del filtrado
    pedidos = [p for p in pedidos if len(p.get("items", [])) > 0]
    
    return pedidos

@router.post("/{pedido_id}/facturar")
async def facturar_pedido(
    pedido_id: str,
    factura_data: dict = Body(...),
):
    """
    Marcar un pedido como facturado y guardar el número de factura
    """
    try:
        from ..config.mongodb import pedidos_collection
        
        pedido_obj_id = ObjectId(pedido_id)
        
        # Actualizar el pedido agregando información de facturación
        result = pedidos_collection.update_one(
            {"_id": pedido_obj_id},
            {
                "$set": {
                    "facturado": True,
                    "numero_factura": factura_data.get("numeroFactura"),
                    "fecha_facturacion": datetime.now().isoformat(),
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        return {
            "message": "Pedido facturado exitosamente",
            "numero_factura": factura_data.get("numeroFactura")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al facturar pedido: {str(e)}")

@router.get("/comisiones/produccion/terminadas/")
async def get_empleados_comisiones_produccion_terminadas(
    fecha_inicio: str = None,
    fecha_fin: str = None
):
    print(f"DEBUG COMISIONES TERMINADAS: Iniciando endpoint con fechas: {fecha_inicio} - {fecha_fin}")
    
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
    
    print(f"DEBUG COMISIONES TERMINADAS: Procesando {len(pedidos)} pedidos")
    
    for pedido in pedidos:
        pedido_id = str(pedido.get("_id"))
        
        # LEER COMISIONES DEL ARRAY COMISIONES DEL PEDIDO
        comisiones_pedido = pedido.get("comisiones", [])
        print(f"DEBUG COMISIONES TERMINADAS: Pedido {pedido_id} tiene {len(comisiones_pedido)} comisiones")
        
        for comision in comisiones_pedido:
            empleado_id = comision.get("empleado_id")
            nombre_empleado = comision.get("empleado_nombre")
            item_id = comision.get("item_id")
            descripcion_item = comision.get("descripcion", "")
            costo_produccion = comision.get("costo_produccion", 0)
            modulo = comision.get("modulo", "")
            fecha_comision = comision.get("fecha")
            
            print(f"DEBUG COMISIONES TERMINADAS: Comisión encontrada - empleado: {empleado_id}, costo: {costo_produccion}")
            
            # Filtrar por fecha si corresponde
            if filtro_fecha and fecha_comision:
                try:
                    if isinstance(fecha_comision, str):
                        fecha_comision_dt = datetime.strptime(fecha_comision[:10], "%Y-%m-%d")
                    else:
                        fecha_comision_dt = fecha_comision.date()
                        fecha_comision_dt = datetime.combine(fecha_comision_dt, datetime.min.time())
                    
                    if not (filtro_fecha[0] <= fecha_comision_dt <= filtro_fecha[1]):
                        continue
                except Exception as e:
                    print(f"DEBUG COMISIONES TERMINADAS: Error procesando fecha: {e}")
                    continue
            
            # Buscar información del item en el pedido
            item_info = next((item for item in pedido.get("items", []) if item.get("id") == item_id), {})
            
            asignacion_data = {
                "pedido_id": pedido_id,
                "orden": 1 if modulo == "herreria" else 2 if modulo == "masillar" else 3 if modulo == "preparar" else 0,
                "nombre_subestado": f"{modulo.title()} / Completado",
                "estado_subestado": "terminado",
                "fecha_inicio_subestado": None,
                "fecha_fin_subestado": fecha_comision,
                "item_id": item_id,
                "key": f"{item_id}-{empleado_id}",
                "empleadoId": empleado_id,
                "nombreempleado": nombre_empleado,
                "fecha_inicio": None,
                "estado": "completado",
                "descripcionitem": descripcion_item,
                "costoproduccion": costo_produccion,
                "fecha_fin": fecha_comision,
                "cantidad": item_info.get("cantidad", 1),
                "precio_item": item_info.get("precio", 0),
                "modulo": modulo
            }
            
            if empleado_id not in resultado:
                resultado[empleado_id] = {
                    "empleado_id": empleado_id,
                    "nombre_empleado": nombre_empleado,
                    "asignaciones": []
                }
            resultado[empleado_id]["asignaciones"].append(asignacion_data)
    
    print(f"DEBUG COMISIONES TERMINADAS: Total empleados con comisiones: {len(resultado)}")
    for empleado_id, data in resultado.items():
        print(f"DEBUG COMISIONES TERMINADAS: Empleado {empleado_id} ({data['nombre_empleado']}): {len(data['asignaciones'])} comisiones")
    
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
    """Endpoint para producción en proceso (excluyendo pedidos web)"""
    try:
        collections = get_collections()
        
        pipeline = [
            {
                "$match": {
                    "$and": [
                        {
                            "seguimiento": {
                                "$elemMatch": {
                                    "asignaciones_articulos": {"$exists": True, "$ne": []}
                                }
                            }
                        },
                        {
                            "$or": [
                                {"tipo_pedido": {"$ne": "web"}},
                                {"tipo_pedido": {"$exists": False}}
                            ]
                        }
                    ]
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
    """Endpoint para pedidos en proceso (excluyendo pedidos web)"""
    try:
        filtro = {"estado_general": {"$in": ["en_proceso", "pendiente"]}}
        filtro = excluir_pedidos_web(filtro)
        pedidos = list(pedidos_collection.find(filtro))
        
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
    """
    Obtener pedidos filtrados por fecha (excluyendo pedidos web).
    Si no se proporcionan fechas, retorna todos los pedidos internos.
    """
    filtro_fecha = None
    if fecha_inicio and fecha_fin:
        try:
            fecha_inicio_dt = datetime.strptime(fecha_inicio, "%Y-%m-%d")
            fecha_fin_dt = datetime.strptime(fecha_fin, "%Y-%m-%d")
            filtro_fecha = (fecha_inicio_dt, fecha_fin_dt)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Formato de fecha inválido: {str(e)}")
    
    # Construir filtro base: excluir pedidos web
    filtro_base = {
        "$or": [
            {"tipo_pedido": {"$ne": "web"}},
            {"tipo_pedido": {"$exists": False}}
        ]
    }
    
    # Si hay filtro de fecha, combinarlo
    if filtro_fecha:
        # Convertir fechas a formato ISO string para comparación
        fecha_inicio_str = fecha_inicio_dt.strftime("%Y-%m-%d")
        fecha_fin_str = (fecha_fin_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        
        filtro = {
            "$and": [
                filtro_base,
                {
                    "fecha_creacion": {
                        "$gte": fecha_inicio_str,
                        "$lt": fecha_fin_str
                    }
                }
            ]
        }
    else:
        filtro = filtro_base
    
    # Obtener pedidos con el filtro
    pedidos = list(pedidos_collection.find(filtro))
    
    # Procesar y filtrar por fecha si es necesario (para casos donde fecha_creacion es datetime)
    pedidos_filtrados = []
    for pedido in pedidos:
        # Verificación adicional: saltar pedidos web por si acaso
        tipo_pedido = pedido.get("tipo_pedido")
        if tipo_pedido == "web":
            continue
        
        fecha_creacion = pedido.get("fecha_creacion")
        
        # Si hay filtro de fecha, validar también parseando la fecha
        if filtro_fecha and fecha_creacion:
            try:
                # Intentar parsear como string ISO
                if isinstance(fecha_creacion, str):
                    fecha_creacion_dt = datetime.strptime(fecha_creacion[:10], "%Y-%m-%d")
                else:
                    # Si es datetime, usar directamente
                    fecha_creacion_dt = fecha_creacion
                    if isinstance(fecha_creacion_dt, datetime):
                        fecha_creacion_dt = fecha_creacion_dt.replace(tzinfo=None)
                
                if not (filtro_fecha[0] <= fecha_creacion_dt <= filtro_fecha[1]):
                    continue
            except Exception:
                # Si no se puede parsear, incluir el pedido de todas formas
                pass
        
        pedido["_id"] = str(pedido["_id"])
        # Normalizar adicionales
        if "adicionales" not in pedido or pedido.get("adicionales") is None:
            pedido["adicionales"] = []
        # Enriquecer con datos del cliente
        enriquecer_pedido_con_datos_cliente(pedido)
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
                            "orden": orden,
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
            "orden": orden,
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



# Endpoint de prueba para verificar conectividad
@router.get("/test-terminar")
async def test_terminar():
    """Endpoint de prueba para verificar que el servidor responde"""
    return {"message": "Endpoint de terminar funcionando", "status": "ok"}

# Endpoint de debug para ver empleados
@router.get("/debug-empleados")
@router.post("/debug-empleados")  # Agregar también POST para evitar 405
async def debug_empleados():
    """Endpoint para ver todos los empleados y sus identificadores"""
    try:
        empleados = list(empleados_collection.find({}, {
            "_id": 1,
            "identificador": 1,
            "nombreCompleto": 1,
            "pin": 1
        }))
        
        # Convertir ObjectId a string
        for empleado in empleados:
            empleado["_id"] = str(empleado["_id"])
            # Ocultar PIN por seguridad
            if "pin" in empleado and empleado["pin"]:
                empleado["pin"] = "***"
        
        return {
            "total_empleados": len(empleados),
            "empleados": empleados
        }
    except Exception as e:
        return {"error": str(e)}

# Endpoint para verificar empleados en la BD del backend
@router.get("/debug-verificar-empleados")
async def debug_verificar_empleados():
    """Endpoint para verificar todos los empleados en la BD del backend"""
    try:
        # Obtener todos los empleados con todos los campos
        empleados = list(empleados_collection.find({}))
        
        # Convertir ObjectId a string y procesar datos
        empleados_procesados = []
        for empleado in empleados:
            empleado["_id"] = str(empleado["_id"])
            empleados_procesados.append({
                "_id": empleado["_id"],
                "identificador": empleado.get("identificador", "N/A"),
                "nombreCompleto": empleado.get("nombreCompleto", "N/A"),
                "permisos": empleado.get("permisos", []),
                "cargo": empleado.get("cargo", "N/A"),
                "tipo": empleado.get("tipo", "N/A"),
                "activo": empleado.get("activo", True)
            })
        
        # Buscar empleados con permisos específicos
        empleados_herreria = [e for e in empleados_procesados if "herreria" in e.get("permisos", [])]
        empleados_masillar = [e for e in empleados_procesados if "masillar" in e.get("permisos", [])]
        empleados_pintar = [e for e in empleados_procesados if "pintar" in e.get("permisos", [])]
        empleados_ayudante = [e for e in empleados_procesados if "ayudante" in e.get("permisos", [])]
        empleados_manillar = [e for e in empleados_procesados if "manillar" in e.get("permisos", [])]
        empleados_facturacion = [e for e in empleados_procesados if "facturacion" in e.get("permisos", [])]
        
        return {
            "total_empleados": len(empleados_procesados),
            "empleados_activos": len([e for e in empleados_procesados if e.get("activo", True)]),
            "empleados_herreria": len(empleados_herreria),
            "empleados_masillar": len(empleados_masillar),
            "empleados_pintar": len(empleados_pintar),
            "empleados_ayudante": len(empleados_ayudante),
            "empleados_manillar": len(empleados_manillar),
            "empleados_facturacion": len(empleados_facturacion),
            "todos_los_empleados": empleados_procesados,  # Todos los empleados
            "problema": "No hay empleados con permisos de herreria, masillar, pintar o ayudante" if len(empleados_herreria) == 0 and len(empleados_masillar) == 0 and len(empleados_pintar) == 0 and len(empleados_ayudante) == 0 else "Empleados encontrados"
        }
    except Exception as e:
        return {"error": str(e), "traceback": str(e.__traceback__)}

@router.get("/debug-empleados-activos")
async def debug_empleados_activos():
    """Endpoint simple para verificar empleados activos"""
    try:
        empleados = list(empleados_collection.find({"activo": True}, {
            "_id": 1,
            "identificador": 1,
            "nombreCompleto": 1,
            "cargo": 1,
            "pin": 1
        }))
        
        empleados_procesados = []
        for emp in empleados:
            empleados_procesados.append({
                "_id": str(emp["_id"]),
                "identificador": emp.get("identificador"),
                "nombreCompleto": emp.get("nombreCompleto"),
                "cargo": emp.get("cargo"),
                "pin": emp.get("pin")
            })
        
        return {
            "total_empleados_activos": len(empleados_procesados),
            "empleados": empleados_procesados
        }
    except Exception as e:
        return {"error": str(e)}

# Endpoint para ver comisiones registradas
@router.get("/debug-comisiones")
async def debug_comisiones():
    """Endpoint para ver todas las comisiones registradas"""
    try:
        print(f"DEBUG COMISIONES: Obteniendo todas las comisiones")
        
        # Obtener todas las comisiones
        comisiones = list(comisiones_collection.find({}))
        
        # Convertir ObjectId a string
        for comision in comisiones:
            comision["_id"] = str(comision["_id"])
            if "pedido_id" in comision:
                comision["pedido_id"] = str(comision["pedido_id"])
            if "item_id" in comision:
                comision["item_id"] = str(comision["item_id"])
        
        # Buscar comisiones de ANUBIS PUENTES
        comisiones_anubis = list(comisiones_collection.find({
            "empleado_id": "24241240"
        }))
        
        return {
            "total_comisiones": len(comisiones),
            "comisiones": comisiones[:10],  # Solo las primeras 10
            "comisiones_anubis": len(comisiones_anubis),
            "comisiones_anubis_detalle": comisiones_anubis
        }
    except Exception as e:
        return {"error": str(e)}

# Endpoint para sincronizar TODOS los empleados automáticamente
@router.get("/sync-todos-empleados")
async def sync_todos_empleados():
    """Sincronizar automáticamente todos los empleados desde las asignaciones activas"""
    try:
        print(f"DEBUG SYNC: Iniciando sincronización automática de empleados")
        
        # Obtener todos los empleados únicos desde las asignaciones activas
        empleados_encontrados = set()
        
        # Buscar en todos los pedidos
        pedidos = list(pedidos_collection.find({}))
        print(f"DEBUG SYNC: Revisando {len(pedidos)} pedidos para encontrar empleados")
        
        for pedido in pedidos:
            if not pedido:
                continue
                
            seguimiento = pedido.get("seguimiento")
            if not seguimiento or not isinstance(seguimiento, list):
                continue
                
            for sub in seguimiento:
                if not sub or not isinstance(sub, dict):
                    continue
                    
                asignaciones_articulos = sub.get("asignaciones_articulos")
                if not asignaciones_articulos or not isinstance(asignaciones_articulos, list):
                    continue
                    
                for asignacion in asignaciones_articulos:
                    if not asignacion or not isinstance(asignacion, dict):
                        continue
                        
                    empleado_id = asignacion.get("empleadoId")
                    empleado_nombre = asignacion.get("nombreempleado", "")
                    
                    if empleado_id and empleado_id not in empleados_encontrados:
                        empleados_encontrados.add(empleado_id)
                        print(f"DEBUG SYNC: Empleado encontrado: {empleado_id} - {empleado_nombre}")
        
        print(f"DEBUG SYNC: Total empleados encontrados: {len(empleados_encontrados)}")
        
        empleados_sincronizados = []
        empleados_ya_existentes = []
        
        for empleado_id in empleados_encontrados:
            # Verificar si ya existe en la base de datos
            empleado_existente = empleados_collection.find_one({"identificador": empleado_id})
            
            if empleado_existente:
                print(f"DEBUG SYNC: Empleado {empleado_id} ya existe en BD")
                empleados_ya_existentes.append(empleado_id)
            else:
                # Buscar el nombre del empleado en las asignaciones
                nombre_empleado = f"Empleado {empleado_id}"
                for pedido in pedidos:
                    seguimiento = pedido.get("seguimiento", [])
                    if not seguimiento:
                        continue
                        
                    for sub in seguimiento:
                        if not sub:
                            continue
                            
                        asignaciones_articulos = sub.get("asignaciones_articulos", [])
                        if not asignaciones_articulos:
                            continue
                            
                        for asignacion in asignaciones_articulos:
                            if not asignacion:
                                continue
                                
                            if asignacion.get("empleadoId") == empleado_id:
                                nombre_empleado = asignacion.get("nombreempleado", f"Empleado {empleado_id}")
                                break
                        if nombre_empleado != f"Empleado {empleado_id}":
                            break
                    if nombre_empleado != f"Empleado {empleado_id}":
                        break
                
                # Crear nuevo empleado
                nuevo_empleado = {
                    "identificador": empleado_id,
                    "nombreCompleto": nombre_empleado,
                    "pin": "1234",  # PIN por defecto
                    "fecha_creacion": datetime.now(),
                    "activo": True
                }
                
                result = empleados_collection.insert_one(nuevo_empleado)
                print(f"DEBUG SYNC: Empleado {empleado_id} ({nombre_empleado}) sincronizado con ID: {result.inserted_id}")
                empleados_sincronizados.append(empleado_id)
        
        return {
            "mensaje": "Sincronización automática completada",
            "empleados_encontrados": list(empleados_encontrados),
            "empleados_sincronizados": empleados_sincronizados,
            "empleados_ya_existentes": empleados_ya_existentes,
            "total_encontrados": len(empleados_encontrados),
            "total_sincronizados": len(empleados_sincronizados),
            "total_ya_existentes": len(empleados_ya_existentes)
        }
        
    except Exception as e:
        print(f"ERROR SYNC: Error sincronizando empleados: {e}")
        import traceback
        print(f"ERROR SYNC: Traceback: {traceback.format_exc()}")
        return {"error": str(e)}

# Endpoint para obtener el progreso de un artículo
@router.get("/progreso-articulo/{pedido_id}/{item_id}")
async def get_progreso_articulo(pedido_id: str, item_id: str):
    """Obtener el progreso de un artículo específico para mostrar barra de progreso"""
    try:
        pedido_obj_id = ObjectId(pedido_id)
        pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
        
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        seguimiento = pedido.get("seguimiento", [])
        progreso = {
            "herreria": {"estado": "pendiente", "completado": False},
            "masillar": {"estado": "pendiente", "completado": False},
            "preparar": {"estado": "pendiente", "completado": False},
            "listo_facturar": {"estado": "pendiente", "completado": False}
        }
        
        # Mapear órdenes a módulos
        orden_modulo = {
            1: "herreria",
            2: "masillar", 
            3: "preparar",
            4: "listo_facturar"
        }
        
        for sub in seguimiento:
            orden = sub.get("orden")
            modulo = orden_modulo.get(orden)
            
            if not modulo:
                continue
                
            # Verificar si el artículo está en este módulo
            asignaciones = sub.get("asignaciones_articulos", [])
            articulo_en_modulo = any(
                a.get("itemId") == item_id for a in asignaciones
            )
            
            if articulo_en_modulo:
                # El artículo está en este módulo
                estado_modulo = sub.get("estado", "pendiente")
                progreso[modulo] = {
                    "estado": estado_modulo,
                    "completado": estado_modulo == "completado",
                    "en_proceso": estado_modulo == "en_proceso"
                }
            elif sub.get("estado") == "completado":
                # El módulo ya fue completado (el artículo pasó por aquí)
                progreso[modulo] = {
                    "estado": "completado",
                    "completado": True,
                    "en_proceso": False
                }
        
        return {
            "pedido_id": pedido_id,
            "item_id": item_id,
            "progreso": progreso,
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR PROGRESO: Error obteniendo progreso: {e}")
        raise HTTPException(status_code=500, detail="Error al obtener progreso")

# Endpoint simple para sincronizar ANUBIS PUENTES
@router.get("/sync-anubis")
async def sync_anubis_simple():
    """Endpoint simple para sincronizar ANUBIS PUENTES"""
    try:
        print(f"DEBUG SYNC: Sincronizando ANUBIS PUENTES")
        
        # Verificar si ya existe
        empleado_existente = empleados_collection.find_one({
            "identificador": "24241240"
        })
        
        if empleado_existente:
            return {
                "mensaje": "ANUBIS PUENTES ya existe en la BD",
                "empleado_id": str(empleado_existente["_id"]),
                "existe": True,
                "nombre": empleado_existente.get("nombreCompleto", "ANUBIS PUENTES")
            }
        
        # Crear ANUBIS PUENTES
        anubis_data = {
            "identificador": "24241240",
            "nombreCompleto": "ANUBIS PUENTES",
            "pin": "1234",
            "cargo": "HERRERO",
            "activo": True,
            "fecha_creacion": datetime.now()
        }
        
        resultado = empleados_collection.insert_one(anubis_data)
        
        return {
            "mensaje": "ANUBIS PUENTES sincronizado exitosamente",
            "empleado_id": str(resultado.inserted_id),
            "existe": False,
            "nombre": "ANUBIS PUENTES"
        }
        
    except Exception as e:
        print(f"ERROR SYNC: {str(e)}")
        return {"error": str(e)}

# Endpoint para sincronizar ANUBIS PUENTES específicamente (GET también)
@router.get("/sincronizar-anubis")
@router.post("/sincronizar-anubis")
async def sincronizar_anubis():
    """Endpoint para sincronizar específicamente a ANUBIS PUENTES"""
    try:
        print(f"DEBUG SINCRONIZAR: Sincronizando ANUBIS PUENTES")
        
        # Datos de ANUBIS PUENTES
        anubis_data = {
            "identificador": "24241240",
            "nombreCompleto": "ANUBIS PUENTES",
            "pin": "1234",  # PIN por defecto, puede cambiarse después
            "cargo": "HERRERO",
            "activo": True,
            "fecha_creacion": datetime.now()
        }
        
        # Verificar si ya existe
        empleado_existente = empleados_collection.find_one({
            "identificador": "24241240"
        })
        
        if empleado_existente:
            print(f"DEBUG SINCRONIZAR: ANUBIS PUENTES ya existe")
            return {
                "mensaje": "ANUBIS PUENTES ya existe en la BD",
                "empleado_id": str(empleado_existente["_id"]),
                "existe": True
            }
        
        # Crear ANUBIS PUENTES
        resultado = empleados_collection.insert_one(anubis_data)
        
        print(f"DEBUG SINCRONIZAR: ANUBIS PUENTES creado: {resultado.inserted_id}")
        
        return {
            "mensaje": "ANUBIS PUENTES sincronizado exitosamente",
            "empleado_id": str(resultado.inserted_id),
            "existe": False
        }
        
    except Exception as e:
        print(f"ERROR SINCRONIZAR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al sincronizar ANUBIS PUENTES: {str(e)}")

# Endpoint para sincronizar empleados desde el frontend
@router.post("/sincronizar-empleado")
async def sincronizar_empleado(
    empleado_data: dict = Body(...)
):
    """Endpoint para sincronizar un empleado desde el frontend al backend"""
    try:
        print(f"DEBUG SINCRONIZAR: Recibiendo empleado: {empleado_data}")
        
        # Buscar si ya existe
        empleado_existente = empleados_collection.find_one({
            "identificador": empleado_data.get("identificador")
        })
        
        if empleado_existente:
            print(f"DEBUG SINCRONIZAR: Empleado ya existe: {empleado_data.get('identificador')}")
            return {
                "mensaje": "Empleado ya existe",
                "empleado_id": str(empleado_existente["_id"]),
                "existe": True
            }
        
        # Crear nuevo empleado
        nuevo_empleado = {
            "identificador": empleado_data.get("identificador"),
            "nombreCompleto": empleado_data.get("nombreCompleto"),
            "pin": empleado_data.get("pin"),
            "cargo": empleado_data.get("cargo", "Empleado"),
            "activo": True,
            "fecha_creacion": datetime.now()
        }
        
        resultado = empleados_collection.insert_one(nuevo_empleado)
        
        print(f"DEBUG SINCRONIZAR: Empleado creado: {resultado.inserted_id}")
        
        return {
            "mensaje": "Empleado sincronizado exitosamente",
            "empleado_id": str(resultado.inserted_id),
            "existe": False
        }
        
    except Exception as e:
        print(f"ERROR SINCRONIZAR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al sincronizar empleado: {str(e)}")

# Endpoint para buscar específicamente a ANUBIS PUENTES
@router.get("/debug-buscar-anubis")
async def debug_buscar_anubis():
    """Endpoint para buscar específicamente a ANUBIS PUENTES"""
    try:
        # Buscar por nombre
        anubis_por_nombre = list(empleados_collection.find({
            "nombreCompleto": {"$regex": "ANUBIS", "$options": "i"}
        }))
        
        # Buscar por identificador
        anubis_por_id = list(empleados_collection.find({
            "identificador": "24241240"
        }))
        
        # Buscar por identificador como número
        anubis_por_id_num = list(empleados_collection.find({
            "identificador": 24241240
        }))
        
        # Buscar todos los empleados con identificador similar
        anubis_similar = list(empleados_collection.find({
            "identificador": {"$regex": "24241240"}
        }))
        
        return {
            "por_nombre": anubis_por_nombre,
            "por_id_string": anubis_por_id,
            "por_id_numero": anubis_por_id_num,
            "por_id_similar": anubis_similar,
            "total_encontrados": len(anubis_por_nombre) + len(anubis_por_id) + len(anubis_por_id_num) + len(anubis_similar)
        }
    except Exception as e:
        return {"error": str(e)}

# Endpoint de prueba para verificar que PUT funciona
@router.put("/test-asignacion-terminar")
async def test_asignacion_terminar():
    """Endpoint de prueba para verificar que PUT /pedidos/asignacion/terminar funciona"""
    return {
        "message": "Endpoint PUT funcionando",
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    }

# Endpoint para terminar una asignación de artículo dentro de un pedido
# Actualizado para buscar empleado por _id (ObjectId) o identificador
# LOG: Registrando endpoint PUT /asignacion/terminar
print("DEBUG: Registrando endpoint PUT /pedidos/asignacion/terminar")
@router.put("/asignacion/terminar")
async def terminar_asignacion_articulo(
    pedido_id: str = Body(...),
    orden: Union[int, str] = Body(...),
    item_id: str = Body(...),
    empleado_id: str = Body(...),
    estado: str = Body(...),
    fecha_fin: str = Body(...),
    pin: Optional[str] = Body(None),  # PIN opcional
    unidad_index: Optional[int] = Body(None)  # unidad_index opcional
):
    """
    Endpoint mejorado para terminar asignaciones con flujo flexible.
    Mantiene el item visible en pedidosherreria y lo mueve al siguiente módulo.
    """
    print(f"DEBUG TERMINAR: === Endpoint llamado ===")
    print(f"DEBUG TERMINAR: pedido_id={pedido_id}, orden={orden}, item_id={item_id}, empleado_id={empleado_id}")
    print(f"DEBUG TERMINAR: === DATOS RECIBIDOS ===")
    print(f"DEBUG TERMINAR: pedido_id={pedido_id}")
    print(f"DEBUG TERMINAR: orden={orden} (tipo: {type(orden)})")
    print(f"DEBUG TERMINAR: item_id={item_id}")
    print(f"DEBUG TERMINAR: empleado_id={empleado_id}")
    print(f"DEBUG TERMINAR: estado={estado}")
    print(f"DEBUG TERMINAR: fecha_fin={fecha_fin}")
    # unidad_index puede venir para identificar la unidad específica
    unidad_index_int = None
    if unidad_index is not None:
        try:
            unidad_index_int = int(unidad_index)
        except (ValueError, TypeError):
            unidad_index_int = None
    print(f"DEBUG TERMINAR: unidad_index={unidad_index_int}")
    print(f"DEBUG TERMINAR: pin={'***' if pin else None}")
    print(f"DEBUG TERMINAR: === FIN DATOS RECIBIDOS ===")
    
    # Convertir orden a int si viene como string
    try:
        orden_int = int(orden) if isinstance(orden, str) else orden
        print(f"DEBUG TERMINAR: Orden convertido a int: {orden_int}")
    except (ValueError, TypeError) as e:
        print(f"ERROR TERMINAR: Error convirtiendo orden a int: {e}")
        raise HTTPException(status_code=400, detail=f"orden debe ser un número válido: {str(e)}")
    
    # VALIDAR PIN - ES OBLIGATORIO
    if not pin:
        print(f"ERROR TERMINAR: PIN es obligatorio para terminar asignación")
        raise HTTPException(status_code=400, detail="PIN es obligatorio para terminar asignación")
    
    print(f"DEBUG TERMINAR: Validando PIN para empleado {empleado_id}")
    
    # Buscar empleado primero por _id (ObjectId), luego por identificador
    empleado = None
    try:
        # Intentar primero como ObjectId (_id)
        print(f"DEBUG TERMINAR: Buscando empleado por _id (ObjectId): '{empleado_id}'")
        try:
            empleado_obj_id = ObjectId(empleado_id)
            empleado = empleados_collection.find_one({"_id": empleado_obj_id})
            if empleado:
                print(f"DEBUG TERMINAR: ✓ Empleado encontrado por _id: {empleado.get('nombreCompleto', 'N/A')}")
            else:
                print(f"DEBUG TERMINAR: ✗ No se encontró empleado por _id")
        except Exception as e:
            print(f"DEBUG TERMINAR: Error al convertir a ObjectId o buscar por _id: {e}")
            import traceback
            print(f"DEBUG TERMINAR: Traceback ObjectId: {traceback.format_exc()}")
        
        # Si no se encuentra por _id, intentar por identificador como string
        if not empleado:
            print(f"DEBUG TERMINAR: Buscando empleado con identificador string: '{empleado_id}'")
            empleado = empleados_collection.find_one({"identificador": empleado_id})
            if empleado:
                print(f"DEBUG TERMINAR: ✓ Empleado encontrado por identificador string: {empleado.get('nombreCompleto', 'N/A')}")
            else:
                print(f"DEBUG TERMINAR: ✗ No se encontró empleado por identificador string")
        
        # Si no se encuentra, intentar identificador como número
        if not empleado:
            try:
                empleado_id_num = int(empleado_id)
                print(f"DEBUG TERMINAR: Buscando empleado con identificador número: {empleado_id_num}")
                empleado = empleados_collection.find_one({"identificador": empleado_id_num})
                if empleado:
                    print(f"DEBUG TERMINAR: ✓ Empleado encontrado por identificador número: {empleado.get('nombreCompleto', 'N/A')}")
                else:
                    print(f"DEBUG TERMINAR: ✗ No se encontró empleado por identificador número")
            except ValueError:
                print(f"DEBUG TERMINAR: No se pudo convertir a número: {empleado_id}")
        
        # Debug adicional: listar todos los empleados para verificar la colección
        if not empleado:
            print(f"DEBUG TERMINAR: === DEBUG: Listando todos los empleados ===")
            todos_empleados = list(empleados_collection.find({}, {"_id": 1, "identificador": 1, "nombreCompleto": 1}))
            print(f"DEBUG TERMINAR: Total empleados en BD: {len(todos_empleados)}")
            for emp in todos_empleados:
                print(f"DEBUG TERMINAR:   - _id: {emp.get('_id')}, identificador: {emp.get('identificador')}, nombre: {emp.get('nombreCompleto', 'N/A')}")
            
    except Exception as e:
        print(f"DEBUG TERMINAR: Error buscando empleado: {e}")
        import traceback
        print(f"DEBUG TERMINAR: Traceback: {traceback.format_exc()}")
    
    if not empleado:
        print(f"ERROR TERMINAR: Empleado no encontrado: {empleado_id}")
        raise HTTPException(status_code=404, detail=f"Empleado {empleado_id} no encontrado en la base de datos")
    
    print(f"DEBUG TERMINAR: Empleado encontrado: {empleado.get('nombreCompleto', empleado_id)}")
    
    # Validar que el empleado tenga PIN configurado
    if not empleado.get("pin"):
        print(f"ERROR TERMINAR: Empleado {empleado_id} no tiene PIN configurado")
        raise HTTPException(status_code=400, detail="Empleado no tiene PIN configurado")
    
    # Validar que el PIN sea correcto (convertir ambos a string para comparar)
    pin_empleado = str(empleado.get("pin", "")).strip()
    pin_recibido = str(pin).strip()
    
    if pin_empleado != pin_recibido:
        print(f"ERROR TERMINAR: PIN incorrecto para empleado {empleado_id}")
        print(f"ERROR TERMINAR: PIN recibido: '{pin_recibido}', PIN esperado: '{pin_empleado}'")
        raise HTTPException(status_code=400, detail="PIN incorrecto")
    
    print(f"DEBUG TERMINAR: PIN validado correctamente para empleado {empleado.get('nombreCompleto', empleado_id)}")
    
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
            asignaciones = sub.get("asignaciones_articulos") or []
            print(f"DEBUG TERMINAR: Asignaciones encontradas: {len(asignaciones)}")
            
            # Si no hay asignaciones en el subestado, crear una nueva asignación terminada
            if len(asignaciones) == 0:
                print(f"DEBUG TERMINAR: No hay asignaciones, creando nueva asignación terminada")
                nueva_asignacion = {
                    "itemId": item_id,
                    "empleadoId": empleado_id,
                    "nombreempleado": empleado.get("nombreCompleto", f"Empleado {empleado_id}") if empleado else f"Empleado {empleado_id}",
                    "estado": "terminado",
                    "estado_subestado": "terminado",
                    "fecha_inicio": datetime.now().isoformat(),
                    "fecha_fin": fecha_fin
                }
                sub["asignaciones_articulos"] = [nueva_asignacion]
                asignacion_encontrada = nueva_asignacion.copy()
                actualizado = True
                print(f"DEBUG TERMINAR: Nueva asignación terminada creada")
                break
            
            # Buscar la asignación existente - primero por unidad_index si viene, luego empleado, luego cualquiera
            for asignacion in asignaciones:
                print(f"DEBUG TERMINAR: Revisando asignación: itemId={asignacion.get('itemId')}, empleadoId={asignacion.get('empleadoId')}")
                if asignacion.get("itemId") == item_id:
                    if unidad_index_int is not None and int(asignacion.get("unidad_index", 0) or 0) != unidad_index_int:
                        continue
                    # Primero intentar coincidencia exacta de empleado
                    if asignacion.get("empleadoId") == empleado_id:
                        print(f"DEBUG TERMINAR: Asignación encontrada con empleado exacto, estado actual: {asignacion.get('estado')}")
                        
                        # Actualizar todos los campos necesarios
                        asignacion["estado"] = "terminado"  # Cambiar estado a terminado para que desaparezca del dashboard
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
                    elif not actualizado:
                        # Si no encontró con empleado exacto, usar esta asignación (cualquier empleado)
                        print(f"DEBUG TERMINAR: Asignación encontrada sin empleado exacto, usando esta asignación")
                        
                        # Actualizar todos los campos necesarios
                        asignacion["estado"] = "terminado"  # Cambiar estado a terminado para que desaparezca del dashboard
                        asignacion["estado_subestado"] = "terminado"  # Cambiar estado_subestado
                        asignacion["fecha_fin"] = fecha_fin
                        
                        # Guardar copia para respuesta
                        asignacion_encontrada = asignacion.copy()
                        actualizado = True
                        
                        print(f"DEBUG TERMINAR: Asignación actualizada:")
                        print(f"  - estado: {asignacion.get('estado')}")
                        print(f"  - estado_subestado: {asignacion.get('estado_subestado')}")
                        print(f"  - fecha_fin: {asignacion.get('fecha_fin')}")
                        # No hacer break aquí para permitir buscar otra mejor coincidencia
            
            # Si llegamos aquí sin actualizar y hay asignaciones, el item no tiene asignación específica
            if not actualizado and len(asignaciones) > 0:
                print(f"DEBUG TERMINAR: Asignación no encontrada en la lista de asignaciones")
            
            break
    
    if not actualizado:
        print(f"DEBUG TERMINAR: Asignación no encontrada")
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    
    print(f"DEBUG TERMINAR: Guardando cambios en el pedido...")
    
    # Obtener el estado_item actual del item
    item = None
    for item_pedido in pedido.get("items", []):
        if item_pedido.get("id") == item_id:
            item = item_pedido
            break
    
    estado_item_actual = item.get("estado_item", 1) if item else 1
    print(f"DEBUG TERMINAR: estado_item actual: {estado_item_actual}")
    
    # Incrementar estado_item SOLO si no quedan unidades pendientes/en_proceso en este orden para el mismo item
    modulo_actual = "herreria"
    if orden_int == 1:
        modulo_actual = "herreria"
    elif orden_int == 2:
        modulo_actual = "masillar"
    elif orden_int == 3:
        modulo_actual = "preparar"

    quedan_pendientes = False
    for sub in seguimiento:
        if int(sub.get("orden", -1)) == orden_int:
            for a in (sub.get("asignaciones_articulos") or []):
                if a.get("itemId") == item_id and a.get("modulo") == modulo_actual and a.get("estado") in ["pendiente", "en_proceso"]:
                    quedan_pendientes = True
                    break
            break

    if quedan_pendientes:
        nuevo_estado_item = estado_item_actual
    else:
        nuevo_estado_item = min(estado_item_actual + 1, 4)
    print(f"DEBUG TERMINAR: nuevo estado_item: {nuevo_estado_item} (quedan_pendientes={quedan_pendientes})")
    
    # LIMPIAR campos de asignación del item, actualizar seguimiento e incrementar estado_item
    try:
        # Limpiar empleado_asignado, nombre_empleado, modulo_actual del item E incrementar estado_item
        result = pedidos_collection.update_one(
            {
                "_id": pedido_obj_id,
                "items.id": item_id
            },
            {
                "$set": {
                    "seguimiento": seguimiento,
                    "items.$.empleado_asignado": None,
                    "items.$.nombre_empleado": None,
                    "items.$.modulo_actual": None,
                    "items.$.fecha_asignacion": None,
                    "items.$.estado_item": nuevo_estado_item
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Pedido no encontrado al actualizar")
            
        print(f"DEBUG TERMINAR: Asignación terminada, campos del item limpiados y estado_item actualizado a {nuevo_estado_item}")
        
        # Registrar movimiento logístico
        try:
            item_pedido = None
            for it in pedido.get("items", []):
                if it.get("id") == item_id:
                    item_pedido = it
                    break
            
            if item_pedido:
                codigo_item = item_pedido.get("codigo", "")
                nombre_item = item_pedido.get("nombre", "") or item_pedido.get("descripcion", "") or codigo_item
                cantidad_item = item_pedido.get("cantidad", 1)
                estado_anterior_item = item.get("estado_item", 0) if item else 0
                
                registrar_movimiento_logistico(
                    item_id=item_id,
                    item_codigo=str(codigo_item) if codigo_item else item_id,
                    item_nombre=nombre_item,
                    tipo_movimiento="terminar_asignacion",
                    cantidad=float(cantidad_item),
                    pedido_id=pedido_id,
                    estado_anterior=str(estado_anterior_item),
                    estado_nuevo=str(nuevo_estado_item),
                    empleado_id=empleado_id
                )
        except Exception as e:
            print(f"ERROR REGISTRAR MOVIMIENTO TERMINAR: {e}")
        
        # REGISTRAR COMISIÓN EN EL PEDIDO
        print(f"DEBUG TERMINAR: === INICIANDO REGISTRO DE COMISIÓN ===")
        
        comision_data = None
        try:
            # El item ya fue encontrado arriba
            costo_produccion = item.get("costoProduccion", 0) if item else 0
            print(f"DEBUG TERMINAR: Costo de producción: {costo_produccion}")
            
            # Determinar el módulo actual
            modulo_actual = "herreria"
            if orden_int == 1:
                modulo_actual = "herreria"
            elif orden_int == 2:
                modulo_actual = "masillar"
            elif orden_int == 3:
                modulo_actual = "preparar"
            print(f"DEBUG TERMINAR: Módulo actual: {modulo_actual}")
            
            # Obtener fecha_inicio de la asignación
            fecha_inicio = asignacion_encontrada.get("fecha_inicio", "") if asignacion_encontrada else ""
            
            # Crear registro de comisión
            comision_pedido = {
                "empleado_id": empleado_id,
                "empleado_nombre": empleado.get("nombreCompleto", f"Empleado {empleado_id}") if empleado else f"Empleado {empleado_id}",
                "item_id": item_id,
                "modulo": modulo_actual,
                "costo_produccion": costo_produccion,
                "costoProduccion": costo_produccion,  # Mapeo alternativo
                "fecha": datetime.now(),
                "fecha_inicio": fecha_inicio,
                "fecha_fin": fecha_fin,
                "estado": "terminado",
                "descripcion": item.get("descripcion", item.get("nombre", "Sin descripción")) if item else "Sin descripción",
                "pedido_id": pedido_id
            }
            
            print(f"DEBUG TERMINAR: Comisión a registrar: {comision_pedido}")
            
            # Agregar comisión al pedido si no existe
            if "comisiones" not in pedido:
                pedido["comisiones"] = []
            
            pedido["comisiones"].append(comision_pedido)
            
            # Actualizar el pedido con la comisión
            result_comision = pedidos_collection.update_one(
                {"_id": pedido_obj_id},
                {"$push": {"comisiones": comision_pedido}}
            )
            
            print(f"DEBUG TERMINAR: Resultado update_one comisión: {result_comision.modified_count} documentos modificados")
            
            comision_data = comision_pedido
            print(f"DEBUG TERMINAR: Comisión registrada en pedido exitosamente")
            
        except Exception as e:
            print(f"ERROR TERMINAR: Error registrando comisión: {e}")
            import traceback
            print(f"ERROR TERMINAR: Traceback: {traceback.format_exc()}")
        
        print(f"DEBUG TERMINAR: === FIN REGISTRO DE COMISIÓN ===")
        
        # Determinar el siguiente estado del item basado en el orden
        siguiente_estado_item_map = {
            1: 2,  # herreria -> masillar (orden1 -> orden2)
            2: 3,  # masillar -> preparar (orden2 -> orden3)
            3: 4,  # preparar -> facturar (orden3 -> orden4)
            4: 5   # facturar -> terminado (orden4 -> orden5)
        }

        siguiente_estado_item = siguiente_estado_item_map.get(orden_int)

        # IMPORTANTE: Actualizar inventario ANTES del return
        # Solo actualizar inventario cuando se termina en orden 3 (Preparar/Manillar)
        if orden_int == 3:
            try:
                # Obtener información del item del pedido
                item_pedido = None
                for item in pedido.get("items", []):
                    if item.get("id") == item_id:
                        item_pedido = item
                        break
                
                if item_pedido and "codigo" in item_pedido:
                    codigo_item = item_pedido.get("codigo")
                    cantidad = item_pedido.get("cantidad", 1)
                    cliente_nombre = pedido.get("cliente_nombre", "")
                    
                    print(f"DEBUG TERMINAR: Actualizando inventario para orden 3 (MANILLAR) - codigo: {codigo_item}, cantidad: {cantidad}, cliente: {cliente_nombre}")
                    
                    # Buscar el item en el inventario
                    item_inventario = items_collection.find_one({"codigo": codigo_item})
                    
                    if item_inventario:
                        # TODOS los items terminados en MANILLAR van a APARTADOS
                        print(f"DEBUG TERMINAR: Sumando a apartados para cliente: {cliente_nombre}")
                        item_apartado = items_collection.find_one({"codigo": codigo_item, "apartado": True})
                        
                        if item_apartado:
                            # Si existe apartado, sumar la cantidad
                            print(f"DEBUG TERMINAR: Item apartado existe - sumando cantidad")
                            result_actualizacion = items_collection.update_one(
                                {"codigo": codigo_item, "apartado": True},
                                {"$inc": {"cantidad": cantidad}}
                            )
                            print(f"DEBUG TERMINAR: Apartado actualizado: {result_actualizacion.modified_count} documentos modificados")
                        else:
                            # Si no existe apartado, crear uno nuevo con cantidad
                            print(f"DEBUG TERMINAR: Item apartado NO existe - creando nuevo apartado")
                            item_apartado_data = item_inventario.copy()
                            item_apartado_data["apartado"] = True
                            item_apartado_data["cantidad"] = cantidad
                            if "_id" in item_apartado_data:
                                del item_apartado_data["_id"]
                            items_collection.insert_one(item_apartado_data)
                            print(f"DEBUG TERMINAR: Nuevo apartado insertado")
                    else:
                        print(f"DEBUG TERMINAR: Item no encontrado en inventario con codigo: {codigo_item}")
                    
                    # GUARDAR ITEM EN MÓDULO APARTADOS
                    try:
                        print(f"DEBUG TERMINAR: Guardando item en módulo APARTADOS")
                        apartado_doc = {
                            "pedido_id": pedido_obj_id,
                            "item_id": ObjectId(item_id),
                            "codigo": item_pedido.get("codigo", ""),
                            "nombre": item_pedido.get("nombre", ""),
                            "descripcion": item_pedido.get("descripcion", ""),
                            "detalle": item_pedido.get("detalle", ""),
                            "cantidad": item_pedido.get("cantidad", 1),
                            "precio": item_pedido.get("precio", 0),
                            "costo_produccion": item_pedido.get("costoProduccion", 0),
                            "cliente_nombre": pedido.get("cliente_nombre", ""),
                            "numero_orden": pedido.get("numero_orden", ""),
                            "fecha_terminado_manillar": datetime.now().isoformat(),
                            "estado_item": nuevo_estado_item,
                            "empleado_ultimo_trabajo": empleado.get("nombreCompleto", empleado_id) if empleado else empleado_id,
                            "imagenes": item_pedido.get("imagenes", [])
                        }
                        
                        apartados_collection.insert_one(apartado_doc)
                        print(f"DEBUG TERMINAR: Item guardado en apartados exitosamente")
                        
                    except Exception as e:
                        print(f"ERROR TERMINAR: Error guardando en apartados: {str(e)}")
                        import traceback
                        print(f"ERROR TERMINAR: Traceback apartados: {traceback.format_exc()}")
                        
            except Exception as e:
                print(f"ERROR TERMINAR: Error actualizando inventario: {str(e)}")
                import traceback
                print(f"ERROR TERMINAR: Traceback inventario: {traceback.format_exc()}")
        
        # VERIFICAR SI EL PEDIDO PUEDE AVANZAR A FACTURACIÓN
        # Si todos los items tienen estado_item >= 4, mover a orden4 independientemente del estado actual
        try:
            print(f"DEBUG TERMINAR: Verificando si el pedido {pedido_id} puede avanzar a Facturación...")
            
            # Verificar estado actualizado del pedido
            pedido_actualizado = pedidos_collection.find_one({"_id": pedido_obj_id})
            
            if pedido_actualizado:
                items_actualizado = pedido_actualizado.get("items", [])
                if items_actualizado:  # Solo verificar si hay items
                    todos_completos = all(item.get("estado_item", 0) >= 4 for item in items_actualizado)
                    
                    print(f"DEBUG TERMINAR: Todos los items completos: {todos_completos}")
                    print(f"DEBUG TERMINAR: Estados items: {[item.get('estado_item', 'N/A') for item in items_actualizado]}")
                    
                    if todos_completos:
                        estado_general = pedido_actualizado.get("estado_general", "")
                        # Mover a orden4 si está en orden1, orden2 o orden3 (no si ya está en orden4, orden5, orden6 o cancelado)
                        if estado_general in ["orden1", "orden2", "orden3"]:
                            # Mover pedido a orden4 (Facturación)
                            result_orden = pedidos_collection.update_one(
                                {"_id": pedido_obj_id},
                                {"$set": {"estado_general": "orden4"}}
                            )
                            print(f"DEBUG TERMINAR: Pedido movido de {estado_general} a orden4 - {result_orden.modified_count} documentos modificados")
                        
        except Exception as e:
            print(f"ERROR TERMINAR: Error verificando pedido completo: {e}")
            # No lanzar error, solo loggear
        
        # Retornar respuesta exitosa CON el inventario actualizado
        return {
            "success": True,
            "message": "Asignación terminada y agregada a comisiones",
            "estado": estado,
            "fecha_fin": fecha_fin,
            "estado_item_anterior": estado_item_actual,
            "estado_item_nuevo": nuevo_estado_item,
            "comision": comision_data,
            "inventario_actualizado": orden_int == 3
        }
    except Exception as e:
        print(f"ERROR TERMINAR: Error actualizando pedido: {e}")
        raise HTTPException(status_code=500, detail=f"Error actualizando pedido: {str(e)}")

# Endpoint para obtener items disponibles para asignación
@router.get("/items-disponibles-asignacion/")
async def get_items_disponibles_asignacion():
    """
    Devuelve items que están disponibles para ser asignados al siguiente módulo
    """
    try:
        print("DEBUG ITEMS DISPONIBLES: Buscando items disponibles para asignación")
        
        # Buscar pedidos con items que necesitan asignación
        # Solo items con estado_item 1-3 (desaparecen cuando terminan MANILLAR)
        pedidos = pedidos_collection.find({
            "items": {
                "$elemMatch": {
                    "estado_item": {"$gte": 1, "$lt": 4}  # Items activos (1-3)
                }
            }
        })
        
        items_disponibles = []
        
        for pedido in pedidos:
            try:
                # Validar que el pedido tenga _id
                if not pedido.get("_id"):
                    print("DEBUG ITEMS DISPONIBLES: Pedido sin _id, saltando")
                    continue
                    
                pedido_id = str(pedido["_id"])
                seguimiento = pedido.get("seguimiento", [])
                
                # Validar que seguimiento sea una lista
                if not isinstance(seguimiento, list):
                    seguimiento = []
                
                items = pedido.get("items", [])
                # Validar que items sea una lista
                if not isinstance(items, list):
                    print(f"DEBUG ITEMS DISPONIBLES: Items no es lista en pedido {pedido_id}")
                    continue
                
                for item in items:
                    try:
                        # Validar que item sea un diccionario
                        if not isinstance(item, dict):
                            print(f"DEBUG ITEMS DISPONIBLES: Item no es diccionario en pedido {pedido_id}")
                            continue
                            
                        estado_item = item.get("estado_item", 1)
                        item_id = item.get("id", item.get("_id", ""))
                        
                        # Validar que item_id no esté vacío
                        if not item_id:
                            print(f"DEBUG ITEMS DISPONIBLES: Item sin ID en pedido {pedido_id}")
                            continue
                        
                        # Verificar si el item necesita asignación en el módulo actual
                        if estado_item < 5:  # No está completamente terminado
                            # Verificar si ya tiene asignación activa en el módulo actual
                            tiene_asignacion_activa = False
                            
                            for proceso in seguimiento:
                                try:
                                    if not isinstance(proceso, dict):
                                        continue
                                    if proceso.get("orden") == estado_item:
                                        asignaciones = proceso.get("asignaciones_articulos", [])
                                        if not isinstance(asignaciones, list):
                                            continue
                                        for asignacion in asignaciones:
                                            if not isinstance(asignacion, dict):
                                                continue
                                            if (asignacion.get("itemId") == item_id and 
                                                asignacion.get("estado") == "en_proceso"):
                                                tiene_asignacion_activa = True
                                                break
                                except Exception as e:
                                    print(f"DEBUG ITEMS DISPONIBLES: Error procesando proceso: {e}")
                                    continue
                            
                            if not tiene_asignacion_activa:
                                # Determinar qué empleados pueden trabajar en este módulo
                                tipos_empleado_requeridos = []
                                if estado_item == 1:  # Herrería
                                    tipos_empleado_requeridos = ["herreria", "masillar", "pintar", "ayudante"]
                                elif estado_item == 2:  # Masillar/Pintar
                                    tipos_empleado_requeridos = ["masillar", "pintar", "ayudante"]
                                elif estado_item == 3:  # Manillar
                                    tipos_empleado_requeridos = ["manillar", "ayudante"]
                                elif estado_item == 4:  # Facturar
                                    tipos_empleado_requeridos = ["facturacion"]
                                
                                items_disponibles.append({
                                    "pedido_id": pedido_id,
                                    "item_id": item_id,
                                    "item_nombre": item.get("nombre", item.get("descripcion", "Sin nombre")),
                                    "estado_item": estado_item,
                                    "modulo_actual": f"orden{estado_item}",
                                    "cliente_nombre": pedido.get("cliente_nombre", "Sin cliente"),
                                    "numero_orden": pedido.get("numero_orden", "Sin número"),
                                    "costo_produccion": item.get("costoProduccion", 0),
                                    "imagenes": item.get("imagenes", []),
                                    "tipos_empleado_requeridos": tipos_empleado_requeridos
                                })
                    except Exception as e:
                        print(f"DEBUG ITEMS DISPONIBLES: Error procesando item: {e}")
                        continue
                        
            except Exception as e:
                print(f"DEBUG ITEMS DISPONIBLES: Error procesando pedido: {e}")
                continue
        
        print(f"DEBUG ITEMS DISPONIBLES: Encontrados {len(items_disponibles)} items disponibles")
        
        return {
            "items_disponibles": items_disponibles,
            "total": len(items_disponibles)
        }
        
    except Exception as e:
        print(f"ERROR ITEMS DISPONIBLES: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# Endpoint para asignar item al siguiente módulo MANUALMENTE
@router.post("/asignar-siguiente-modulo/")
async def asignar_siguiente_modulo(
    pedido_id: str = Body(...),
    item_id: str = Body(...),
    empleado_id: str = Body(...),
    modulo_destino: int = Body(...)  # 2, 3, o 4
):
    """
    Asigna un item al siguiente módulo de producción
    """
    try:
        print(f"DEBUG ASIGNAR SIGUIENTE: Asignando item {item_id} al módulo {modulo_destino}")
        
        pedido_obj_id = ObjectId(pedido_id)
        pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
        
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        # Verificar que el item existe y está en el estado correcto
        item_encontrado = None
        for item in pedido.get("items", []):
            if item.get("id", item.get("_id", "")) == item_id:
                item_encontrado = item
                break
        
        if not item_encontrado:
            raise HTTPException(status_code=404, detail="Item no encontrado")
        
        estado_actual = item_encontrado.get("estado_item", 1)
        
        # Verificar que el módulo destino es el siguiente
        if modulo_destino != estado_actual + 1:
            raise HTTPException(
                status_code=400, 
                detail=f"El módulo destino debe ser {estado_actual + 1}, no {modulo_destino}"
            )
        
        # Buscar empleado
        empleado = buscar_empleado_por_identificador(empleado_id)
        if not empleado:
            raise HTTPException(status_code=404, detail=f"Empleado {empleado_id} no encontrado")
        
        # Crear nueva asignación en el siguiente módulo
        seguimiento = pedido.get("seguimiento", [])
        
        # Buscar o crear el proceso para el módulo destino
        proceso_destino = None
        for proceso in seguimiento:
            if proceso.get("orden") == modulo_destino:
                proceso_destino = proceso
                break
        
        if not proceso_destino:
            # Crear nuevo proceso si no existe
            proceso_destino = {
                "orden": modulo_destino,
                "nombre": f"orden{modulo_destino}",
                "asignaciones_articulos": []
            }
            seguimiento.append(proceso_destino)
        
        # Crear nueva asignación
        nueva_asignacion = {
            "itemId": item_id,
            "empleadoId": empleado_id,
            "nombreempleado": empleado.get("nombreCompleto", empleado_id),
            "estado": "en_proceso",
            "estado_subestado": "en_proceso",
            "fecha_inicio": datetime.now().isoformat(),
            "fecha_fin": None
        }
        
        proceso_destino["asignaciones_articulos"].append(nueva_asignacion)
        
        # Actualizar el estado del item
        result = pedidos_collection.update_one(
            {"_id": pedido_obj_id},
            {
                "$set": {
                    "items.$.estado_item": modulo_destino,
                    "seguimiento": seguimiento
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Item no encontrado para actualizar")
        
        print(f"DEBUG ASIGNAR SIGUIENTE: Item asignado exitosamente al módulo {modulo_destino}")
        
        return {
            "message": f"Item asignado al módulo {modulo_destino}",
            "nuevo_estado_item": modulo_destino,
            "modulo_actual": f"orden{modulo_destino}",
            "empleado_asignado": empleado.get("nombreCompleto", empleado_id),
            "asignacion_creada": nueva_asignacion
        }
        
    except Exception as e:
        print(f"ERROR ASIGNAR SIGUIENTE: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# Endpoint mejorado que mantiene el item visible y maneja el flujo flexible
@router.put("/asignacion/terminar-mejorado")
async def terminar_asignacion_articulo_mejorado(
    pedido_id: str = Body(...),
    orden: Union[int, str] = Body(...),
    item_id: str = Body(...),
    empleado_id: str = Body(...),
    estado: str = Body(...),
    fecha_fin: str = Body(...),
    pin: Optional[str] = Body(None)
):
    """
    Endpoint mejorado para terminar asignaciones con flujo flexible.
    Mantiene el item visible en pedidosherreria y lo mueve al siguiente módulo.
    """
    print(f"DEBUG TERMINAR MEJORADO: === INICIANDO TERMINACIÓN ===")
    print(f"DEBUG TERMINAR MEJORADO: pedido_id={pedido_id}, item_id={item_id}, empleado_id={empleado_id}")
    print(f"DEBUG TERMINAR MEJORADO: orden={orden}, estado={estado}, pin={'***' if pin else None}")
    
    # Convertir orden a int
    try:
        orden_int = int(orden) if isinstance(orden, str) else orden
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"orden debe ser un número válido: {str(e)}")
    
    # VALIDAR PIN - ES OBLIGATORIO
    if not pin:
        raise HTTPException(status_code=400, detail="PIN es obligatorio para terminar asignación")
    
    # Buscar empleado y validar PIN
    empleado = buscar_empleado_por_identificador(empleado_id)
    if not empleado:
        raise HTTPException(status_code=404, detail=f"Empleado {empleado_id} no encontrado")
    
    if not empleado.get("pin"):
        raise HTTPException(status_code=400, detail="Empleado no tiene PIN configurado")
    
    if empleado.get("pin") != pin:
        raise HTTPException(status_code=400, detail="PIN incorrecto")
    
    print(f"DEBUG TERMINAR MEJORADO: PIN validado para empleado {empleado.get('nombreCompleto', empleado_id)}")
    
    # Obtener pedido
    try:
        pedido_obj_id = ObjectId(pedido_id)
        pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"pedido_id no es un ObjectId válido: {str(e)}")
    
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    seguimiento = pedido.get("seguimiento", [])
    
    # Buscar y actualizar la asignación
    asignacion_actualizada = actualizar_asignacion_terminada(seguimiento, orden_int, item_id, empleado_id, estado, fecha_fin)
    if not asignacion_actualizada:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    
    # NO mover automáticamente al siguiente módulo
    # El item quedará disponible para asignación manual
    print(f"DEBUG TERMINAR MEJORADO: Asignación terminada. Item disponible para siguiente módulo.")
    
    # Actualizar pedido en base de datos
    try:
        result = pedidos_collection.update_one(
            {"_id": pedido_obj_id},
            {"$set": {"seguimiento": seguimiento}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Pedido no encontrado al actualizar")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error actualizando pedido: {str(e)}")
    
    # Determinar el siguiente módulo disponible
    siguiente_modulo_disponible = orden_int + 1 if orden_int < 4 else None
    
    print(f"DEBUG TERMINAR MEJORADO: === TERMINACIÓN COMPLETADA ===")
    
    return {
        "message": "Asignación terminada correctamente",
        "success": True,
        "asignacion_actualizada": asignacion_actualizada,
        "siguiente_modulo_disponible": siguiente_modulo_disponible,
        "empleado_nombre": empleado.get("nombreCompleto", empleado_id),
        "pedido_id": pedido_id,
        "item_id": item_id,
        "item_disponible_para_asignacion": siguiente_modulo_disponible is not None
    }


# Endpoint alternativo con barra al final (para compatibilidad)
@router.put("/asignacion/terminar/")
async def terminar_asignacion_articulo_alt(
    request_data: dict = Body(...)
):
    """Endpoint alternativo que redirige al mejorado"""
    print(f"DEBUG TERMINAR ALT: Redirigiendo al endpoint mejorado")
    return await terminar_asignacion_articulo_mejorado(
        pedido_id=request_data.get("pedido_id"),
        orden=request_data.get("orden"),
        item_id=request_data.get("item_id"),
        empleado_id=request_data.get("empleado_id"),
        estado=request_data.get("estado"),
        fecha_fin=request_data.get("fecha_fin"),
        pin=request_data.get("pin")
    )

@router.get("/estado/")
async def get_pedidos_por_estados(
    estado_general: List[str] = Query(...),
    fecha_inicio: Optional[str] = Query(None),  # "YYYY-MM-DD"
    fecha_fin: Optional[str] = Query(None),     # "YYYY-MM-DD"
):
    # filtro base por estados
    base_filter = {"estado_general": {"$in": estado_general}}
    # Excluir pedidos web del filtro base
    base_filter = excluir_pedidos_web(base_filter)

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

        # combinamos: estado_general AND (cond_date OR cond_string) (ya excluye pedidos web)
        final_query = {"$and": [base_filter, {"$or": [cond_date, cond_string]}]}

    try:
        # Obtener todos los campos, incluyendo "adicionales"
        # No usar projection para asegurar que se devuelvan todos los campos
        pedidos = list(pedidos_collection.find(final_query))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en la consulta a la DB: {e}")

    for pedido in pedidos:
        pedido["_id"] = str(pedido["_id"])
        # Normalizar adicionales: None o no existe → []
        if "adicionales" not in pedido or pedido["adicionales"] is None:
            pedido["adicionales"] = []
        # Enriquecer con datos del cliente (cédula y teléfono)
        enriquecer_pedido_con_datos_cliente(pedido)
    return pedidos





# Endpoint de debug para investigar pedidos del 16/10/2025
@router.get("/debug-pedidos-16octubre")
async def debug_pedidos_16octubre():
    """Debug específico para pedidos del 16/10/2025"""
    try:
        # Buscar pedidos del 16/10/2025
        fecha_inicio = datetime(2025, 10, 16, 0, 0, 0, tzinfo=timezone.utc)
        fecha_fin = datetime(2025, 10, 17, 0, 0, 0, tzinfo=timezone.utc)
        
        # Buscar por fecha_creacion (tanto Date como string)
        pedidos_16oct = list(pedidos_collection.find({
            "$or": [
                {"fecha_creacion": {"$gte": fecha_inicio, "$lt": fecha_fin}},
                {"fecha_creacion": {"$gte": "2025-10-16T00:00:00.000Z", "$lt": "2025-10-17T00:00:00.000Z"}}
            ]
        }))
        
        resultado = {
            "total_pedidos_16oct": len(pedidos_16oct),
            "pedidos": []
        }
        
        for pedido in pedidos_16oct:
            pedido_info = {
                "_id": str(pedido["_id"]),
                "numero_orden": pedido.get("numero_orden"),
                "cliente_nombre": pedido.get("cliente_nombre"),
                "fecha_creacion": pedido.get("fecha_creacion"),
                "estado_general": pedido.get("estado_general"),
                "items": []
            }
            
            # Analizar cada item
            for item in pedido.get("items", []):
                item_info = {
                    "item_id": str(item.get("_id", item.get("id", ""))),
                    "descripcion": item.get("descripcion", ""),
                    "estado_item": item.get("estado_item", "NO DEFINIDO"),
                    "tiene_asignacion": False,
                    "asignaciones": []
                }
                
                # Buscar asignaciones en seguimiento
                seguimiento = pedido.get("seguimiento", [])
                for proceso in seguimiento:
                    asignaciones = proceso.get("asignaciones_articulos", [])
                    for asignacion in asignaciones:
                        if str(asignacion.get("itemId")) == str(item_info["item_id"]):
                            item_info["tiene_asignacion"] = True
                            item_info["asignaciones"].append({
                                "estado": asignacion.get("estado"),
                                "empleado": asignacion.get("nombreempleado"),
                                "modulo": proceso.get("orden")
                            })
                
                pedido_info["items"].append(item_info)
            
            resultado["pedidos"].append(pedido_info)
        
        return resultado
        
    except Exception as e:
        print(f"Error en debug pedidos 16 octubre: {e}")
        return {"error": str(e)}

# Endpoint de debug simple para probar
@router.put("/cancelar/{pedido_id}")
async def cancelar_pedido(
    pedido_id: str,
    request: CancelarPedidoRequest,
    user: dict = Depends(get_current_user)
):
    """
    Cancelar un pedido que esté en estado 'pendiente'
    Solo permite cancelar pedidos que no hayan iniciado producción
    """
    try:
        # Validar ID del pedido
        if not pedido_id or len(pedido_id) != 24:
            raise HTTPException(status_code=400, detail="ID de pedido inválido")
        
        # Convertir a ObjectId
        try:
            pedido_obj_id = ObjectId(pedido_id)
        except Exception as e:
            raise HTTPException(status_code=400, detail="ID de pedido inválido")
        
        # Buscar el pedido
        pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        # Verificar que el pedido esté en estado 'pendiente'
        estado_actual = pedido.get("estado_general", "")
        if estado_actual != "pendiente":
            raise HTTPException(
                status_code=400, 
                detail=f"No se puede cancelar el pedido. Estado actual: {estado_actual}. Solo se pueden cancelar pedidos en estado 'pendiente'"
            )
        
        # Verificar que no tenga asignaciones activas
        seguimiento = pedido.get("seguimiento", [])
        if seguimiento is None:
            seguimiento = []
        tiene_asignaciones_activas = False
        
        for proceso in seguimiento:
            if isinstance(proceso, dict):
                asignaciones = proceso.get("asignaciones_articulos", [])
                if asignaciones is None:
                    asignaciones = []
                for asignacion in asignaciones:
                    if asignacion.get("estado") == "en_proceso":
                        tiene_asignaciones_activas = True
                        break
                if tiene_asignaciones_activas:
                    break
        
        if tiene_asignaciones_activas:
            raise HTTPException(
                status_code=400,
                detail="No se puede cancelar el pedido porque tiene asignaciones activas en producción"
            )
        
        # Actualizar el pedido con estado cancelado
        fecha_cancelacion = datetime.now().isoformat()
        usuario_cancelacion = user.get("username", "usuario_desconocido")
        
        # Actualizar el estado_general del pedido y limpiar pagos
        result = pedidos_collection.update_one(
            {"_id": pedido_obj_id},
            {
                "$set": {
                    "estado_general": "cancelado",
                    "fecha_cancelacion": fecha_cancelacion,
                    "motivo_cancelacion": request.motivo_cancelacion,
                    "cancelado_por": usuario_cancelacion,
                    "fecha_actualizacion": fecha_cancelacion,
                    "pago": "sin pago",  # Limpiar estado de pago
                    "total_abonado": 0,  # Limpiar total abonado
                    "historial_pagos": []  # Limpiar historial de pagos
                }
            }
        )
        
        # Actualizar el estado_item de todos los items a 4 (terminado/cancelado)
        # Esto hará que desaparezcan de PedidosHerreria
        items_actualizados = 0
        for i, item in enumerate(pedido.get("items", [])):
            item_result = pedidos_collection.update_one(
                {
                    "_id": pedido_obj_id,
                    f"items.{i}.id": item.get("id")
                },
                {
                    "$set": {
                        f"items.{i}.estado_item": 4,  # Estado terminado/cancelado
                        f"items.{i}.fecha_cancelacion": fecha_cancelacion,
                        f"items.{i}.cancelado_por": usuario_cancelacion
                    }
                }
            )
            if item_result.modified_count > 0:
                items_actualizados += 1
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Pedido no encontrado para actualizar")
        
        if result.modified_count == 0:
            raise HTTPException(status_code=400, detail="No se pudo actualizar el pedido")
        
        return {
            "success": True,
            "message": "Pedido cancelado exitosamente",
            "pedido_id": pedido_id,
            "numero_orden": pedido.get("numero_orden", ""),
            "cliente_nombre": pedido.get("cliente_nombre", ""),
            "fecha_cancelacion": fecha_cancelacion,
            "motivo_cancelacion": request.motivo_cancelacion,
            "cancelado_por": usuario_cancelacion,
            "items_actualizados": items_actualizados,
            "items_desapareceran_herreria": items_actualizados
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error cancelando pedido {pedido_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/estado-items-produccion/")
async def get_estado_items_produccion():
    """
    Endpoint para mostrar el estado actual de todos los items en producción
    Separa claramente: disponibles para asignar vs ya asignados
    """
    try:
        print("DEBUG ESTADO ITEMS: Analizando estado de items en producción")
        
        # Buscar pedidos con items en producción (estado_item 1-3), excluyendo pedidos web
        filtro = {
            "items": {
                "$elemMatch": {
                    "estado_item": {"$gte": 1, "$lt": 4}  # Solo items activos (1-3)
                }
            }
        }
        filtro = excluir_pedidos_web(filtro)
        pedidos = list(pedidos_collection.find(filtro, {
            "_id": 1,
            "numero_orden": 1,
            "cliente_nombre": 1,
            "fecha_creacion": 1,
            "estado_general": 1,
            "items": 1,
            "seguimiento": 1
        }).limit(200))
        
        items_disponibles = []
        items_asignados = []
        
        for pedido in pedidos:
            try:
                pedido_id = str(pedido["_id"])
                seguimiento = pedido.get("seguimiento", [])
                items = pedido.get("items", [])
                
                for item in items:
                    item_id = str(item.get("_id", item.get("id", "")))
                    estado_item = item.get("estado_item", 1)
                    
                    # Solo procesar items activos (1-3)
                    if estado_item >= 1 and estado_item < 4:
                        # Buscar si tiene asignación activa
                        tiene_asignacion_activa = False
                        asignacion_actual = None
                        
                        for proceso in seguimiento:
                            if isinstance(proceso, dict) and proceso.get("orden") == estado_item:
                                asignaciones_articulos = proceso.get("asignaciones_articulos", [])
                                for asignacion in asignaciones_articulos:
                                    if str(asignacion.get("itemId")) == item_id and asignacion.get("estado") == "en_proceso":
                                        tiene_asignacion_activa = True
                                        asignacion_actual = {
                                            "empleado": asignacion.get("nombreempleado", ""),
                                            "fecha_inicio": asignacion.get("fecha_inicio"),
                                            "modulo": "herreria" if estado_item == 1 else "masillar" if estado_item == 2 else "manillar"
                                        }
                                        break
                                if tiene_asignacion_activa:
                                    break
                        
                        item_info = {
                            "pedido_id": pedido_id,
                            "item_id": item_id,
                            "item_nombre": item.get("descripcion", item.get("nombre", "Sin nombre")),
                            "estado_item": estado_item,
                            "modulo_actual": "herreria" if estado_item == 1 else "masillar" if estado_item == 2 else "manillar",
                            "cliente_nombre": pedido.get("cliente_nombre", ""),
                            "numero_orden": pedido.get("numero_orden", ""),
                            "fecha_creacion": pedido.get("fecha_creacion"),
                            "costo_produccion": item.get("costoProduccion", 0),
                            "imagenes": item.get("imagenes", [])
                        }
                        
                        if tiene_asignacion_activa:
                            item_info["asignacion"] = asignacion_actual
                            items_asignados.append(item_info)
                        else:
                            items_disponibles.append(item_info)
                            
            except Exception as e:
                print(f"DEBUG ESTADO ITEMS: Error procesando pedido: {e}")
                continue
        
        print(f"DEBUG ESTADO ITEMS: Disponibles: {len(items_disponibles)}, Asignados: {len(items_asignados)}")
        
        return {
            "success": True,
            "items_disponibles": items_disponibles,
            "items_asignados": items_asignados,
            "total_disponibles": len(items_disponibles),
            "total_asignados": len(items_asignados),
            "total_items": len(items_disponibles) + len(items_asignados),
            "message": "Estado actual de items en producción"
        }
        
    except Exception as e:
        print(f"ERROR ESTADO ITEMS: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "items_disponibles": [],
            "items_asignados": [],
            "total_disponibles": 0,
            "total_asignados": 0,
            "total_items": 0,
            "error": str(e)
        }


@router.get("/cancelables/")
async def get_pedidos_cancelables():
    """
    Obtener pedidos que pueden ser cancelados (estado 'pendiente' sin asignaciones activas)
    """
    try:
        # Buscar pedidos en estado 'pendiente'
        pedidos_pendientes = list(pedidos_collection.find({
            "estado_general": "pendiente"
        }, {
            "_id": 1,
            "numero_orden": 1,
            "cliente_nombre": 1,
            "fecha_creacion": 1,
            "estado_general": 1,
            "seguimiento": 1,
            "items": 1
        }))
        
        pedidos_cancelables = []
        
        for pedido in pedidos_pendientes:
            try:
                pedido_id = str(pedido["_id"])
                seguimiento = pedido.get("seguimiento", [])
                
                # Asegurar que seguimiento sea una lista
                if seguimiento is None:
                    seguimiento = []
                elif not isinstance(seguimiento, list):
                    seguimiento = []
                
                # Verificar que no tenga asignaciones activas
                tiene_asignaciones_activas = False
                for proceso in seguimiento:
                    if isinstance(proceso, dict):
                        asignaciones = proceso.get("asignaciones_articulos", [])
                        if asignaciones is None:
                            asignaciones = []
                        elif not isinstance(asignaciones, list):
                            asignaciones = []
                            
                        for asignacion in asignaciones:
                            if isinstance(asignacion, dict) and asignacion.get("estado") == "en_proceso":
                                tiene_asignaciones_activas = True
                                break
                        if tiene_asignaciones_activas:
                            break
                
                # Solo incluir si no tiene asignaciones activas
                if not tiene_asignaciones_activas:
                    pedidos_cancelables.append({
                        "pedido_id": pedido_id,
                        "numero_orden": pedido.get("numero_orden", ""),
                        "cliente_nombre": pedido.get("cliente_nombre", ""),
                        "fecha_creacion": pedido.get("fecha_creacion", ""),
                        "estado_general": pedido.get("estado_general", ""),
                        "total_items": len(pedido.get("items", [])),
                        "puede_cancelar": True
                    })
                    
            except Exception as e:
                print(f"Error procesando pedido {pedido.get('_id')}: {e}")
                continue
        
        return {
            "success": True,
            "pedidos_cancelables": pedidos_cancelables,
            "total": len(pedidos_cancelables),
            "message": f"Se encontraron {len(pedidos_cancelables)} pedidos que pueden ser cancelados"
        }
        
    except Exception as e:
        print(f"Error obteniendo pedidos cancelables: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")


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

    # Obtener el pedido actual para calcular el total_abonado y verificar tipo
    try:
        pedido = pedidos_collection.find_one({"_id": ObjectId(pedido_id)})
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        # Verificar si es un pedido web - bloquear acceso desde módulos internos
        tipo_pedido = pedido.get("tipo_pedido")
        if tipo_pedido == "web":
            raise HTTPException(
                status_code=403,
                detail="Los pagos de pedidos web solo pueden ser gestionados desde el módulo de pedidos-web"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener pedido: {str(e)}")

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

        current_total_abonado = pedido.get("total_abonado", 0.0)
        new_total_abonado = current_total_abonado + (monto if monto is not None else 0.0)
        update["$set"]["total_abonado"] = new_total_abonado

        result = pedidos_collection.update_one(
            {"_id": ObjectId(pedido_id)},
            update
        )

        # Si es un pedido de cliente (tipo "cliente"), actualizar también la factura en facturas_cliente
        if pedido.get("tipo") == "cliente" and monto is not None and monto > 0:
            try:
                # Buscar la factura asociada al pedido
                factura = facturas_cliente_collection.find_one({"pedido_id": pedido_id})
                
                if factura:
                    # Crear registro de abono para la factura
                    abono_factura = {
                        "fecha": datetime.utcnow().isoformat(),
                        "monto": float(monto),
                        "metodo_pago_id": str(metodo) if metodo else None,
                        "metodo_pago_nombre": metodo if isinstance(metodo, str) else None,
                        "numero_referencia": data.get("numero_referencia"),
                        "comprobante": data.get("comprobante")
                    }
                    
                    # Calcular nuevos valores
                    monto_abonado_actual = float(factura.get("monto_abonado", 0))
                    nuevo_monto_abonado = monto_abonado_actual + monto
                    saldo_pendiente_actual = float(factura.get("saldo_pendiente", factura.get("monto_total", 0)))
                    nuevo_saldo_pendiente = saldo_pendiente_actual - monto
                    
                    # Actualizar la factura
                    update_factura = {
                        "$inc": {
                            "monto_abonado": monto,
                            "saldo_pendiente": -monto
                        },
                        "$push": {"historial_abonos": abono_factura}
                    }
                    
                    # Si el saldo pendiente queda en 0, cambiar estado a "pagada"
                    if nuevo_saldo_pendiente <= 0.01:
                        if "$set" not in update_factura:
                            update_factura["$set"] = {}
                        update_factura["$set"]["estado"] = "pagada"
                    
                    facturas_cliente_collection.update_one(
                        {"pedido_id": pedido_id},
                        update_factura
                    )
                    
                    print(f"DEBUG PAGO: Factura actualizada para pedido {pedido_id}")
                    print(f"  - Monto abonado: {monto_abonado_actual} -> {nuevo_monto_abonado}")
                    print(f"  - Saldo pendiente: {saldo_pendiente_actual} -> {nuevo_saldo_pendiente}")
                    
            except Exception as e:
                print(f"ERROR PAGO: Error al actualizar factura del cliente: {e}")
                import traceback
                print(f"TRACEBACK: {traceback.format_exc()}")
                # No interrumpimos el flujo principal, solo logueamos

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
                    
                    # Actualizar saldo usando $inc (operación atómica)
                    result_update = metodos_pago_collection.update_one(
                        {"_id": metodo_pago["_id"]},
                        {"$inc": {"saldo": monto}}
                    )
                    print(f"DEBUG PAGO: Resultado de actualización: {result_update.modified_count} documentos modificados")
                    
                    # Registrar transacción automáticamente (depósito)
                    try:
                        transaccion_deposito = {
                            "metodo_pago_id": str(metodo_pago["_id"]),
                            "tipo": "deposito",
                            "monto": float(monto),
                            "concepto": data.get("concepto") or f"Abono a pedido {pedido_id}",
                            "pedido_id": pedido_id,
                            "numero_referencia": data.get("numero_referencia"),
                            "comprobante": data.get("comprobante"),
                            "fecha": datetime.utcnow().isoformat()
                        }
                        transacciones_collection.insert_one(transaccion_deposito)
                        print(f"DEBUG PAGO: Transacción de depósito registrada automáticamente para método '{metodo_pago.get('nombre', 'SIN_NOMBRE')}'")
                    except Exception as trans_error:
                        print(f"ERROR PAGO: Error al registrar transacción de depósito: {trans_error}")
                        import traceback
                        print(f"TRACEBACK: {traceback.format_exc()}")
                        # No interrumpimos el flujo si falla el registro de transacción
                    
                    # Verificar que se actualizó correctamente
                    metodo_verificado = metodos_pago_collection.find_one({"_id": metodo_pago["_id"]})
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

    # Verificar si el pedido debería estar en orden4 (Facturación)
    # Si todos los items tienen estado_item >= 4, mover a orden4
    try:
        pedido_actualizado = pedidos_collection.find_one({"_id": ObjectId(pedido_id)})
        if pedido_actualizado:
            items = pedido_actualizado.get("items", [])
            if items:
                todos_completos = all(item.get("estado_item", 0) >= 4 for item in items)
                estado_general = pedido_actualizado.get("estado_general", "")
                
                if todos_completos and estado_general in ["orden1", "orden2", "orden3"]:
                    # Mover pedido a orden4 (Facturación)
                    pedidos_collection.update_one(
                        {"_id": ObjectId(pedido_id)},
                        {"$set": {"estado_general": "orden4"}}
                    )
                    print(f"DEBUG PAGO: Pedido {pedido_id} movido a orden4 después de actualizar pago")
    except Exception as e:
        print(f"ERROR PAGO: Error verificando si pedido debe estar en orden4: {e}")
        # No lanzar error, solo loggear

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
    Retorna los pagos de los pedidos internos, filtrando por rango de fechas si se especifica.
    Excluye pedidos web (tipo_pedido: "web").
    """

    filtro = {}

    if fecha_inicio and fecha_fin:
        try:
            inicio = datetime.strptime(fecha_inicio, "%Y-%m-%d")
            fin = datetime.strptime(fecha_fin, "%Y-%m-%d") + timedelta(days=1)
            filtro["fecha_creacion"] = {"$gte": inicio, "$lt": fin}
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de fecha inválido, use YYYY-MM-DD")

    # Excluir pedidos web
    filtro = excluir_pedidos_web(filtro)
    # Excluir pedidos de TU MUNDO PUERTA (RIF: J-507172554)
    filtro = excluir_pedidos_tu_mundo_puerta(filtro)
    # Excluir todos los pedidos cancelados
    filtro["estado_general"] = {"$ne": "cancelado"}

    # Buscar pedidos internos solamente
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
        
        # DEBUG: Mostrar ejemplos de fechas reales en la BD
        if abonos_raw:
            print(f"DEBUG VENTA DIARIA: === EJEMPLOS DE FECHAS EN LA BD ===")
            for i, abono in enumerate(abonos_raw[:5]):  # Solo los primeros 5
                fecha = abono.get("fecha")
                print(f"DEBUG VENTA DIARIA: Abono {i+1}: fecha={fecha} (tipo: {type(fecha)})")
                if isinstance(fecha, str):
                    print(f"DEBUG VENTA DIARIA:   - String completo: '{fecha}'")
                    print(f"DEBUG VENTA DIARIA:   - Primeros 10 chars: '{fecha[:10]}'")
                elif isinstance(fecha, datetime):
                    print(f"DEBUG VENTA DIARIA:   - Datetime: {fecha}")
                    print(f"DEBUG VENTA DIARIA:   - ISO string: {fecha.isoformat()}")
            print(f"DEBUG VENTA DIARIA: === FIN EJEMPLOS ===")

        # Procesar los abonos manualmente y aplicar filtro de fechas MEJORADO
        abonos = []
        for abono in abonos_raw:
            # Aplicar filtro de fechas si se especificó
            if fecha_busqueda_mmddyyyy:
                fecha_abono = abono.get("fecha")
                fecha_coincide = False
                
                if isinstance(fecha_abono, datetime):
                    # Si es datetime, convertir a string para comparar
                    fecha_str = fecha_abono.strftime("%m/%d/%Y")
                    print(f"DEBUG VENTA DIARIA: Datetime {fecha_abono} -> {fecha_str}")
                    fecha_coincide = fecha_str == fecha_busqueda_mmddyyyy
                    
                elif isinstance(fecha_abono, str):
                    # Si es string, buscar diferentes patrones
                    fecha_str = str(fecha_abono)
                    print(f"DEBUG VENTA DIARIA: String fecha: '{fecha_str}'")
                    
                    # Patrón 1: Buscar MM/DD/YYYY directamente
                    if fecha_busqueda_mmddyyyy in fecha_str:
                        fecha_coincide = True
                        print(f"DEBUG VENTA DIARIA: Encontrado patrón MM/DD/YYYY")
                    
                    # Patrón 2: Si es formato ISO (YYYY-MM-DD), convertir y comparar
                    elif len(fecha_str) >= 10 and fecha_str[4] == '-' and fecha_str[7] == '-':
                        try:
                            fecha_iso = datetime.strptime(fecha_str[:10], "%Y-%m-%d")
                            fecha_mmddyyyy = fecha_iso.strftime("%m/%d/%Y")
                            fecha_coincide = fecha_mmddyyyy == fecha_busqueda_mmddyyyy
                            print(f"DEBUG VENTA DIARIA: ISO {fecha_str[:10]} -> {fecha_mmddyyyy}")
                        except ValueError:
                            print(f"DEBUG VENTA DIARIA: Error parseando ISO: {fecha_str[:10]}")
                
                print(f"DEBUG VENTA DIARIA: Comparando '{fecha_abono}' con '{fecha_busqueda_mmddyyyy}' -> {fecha_coincide}")
                
                if not fecha_coincide:
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

@router.get("/{pedido_id}/pagos")
async def get_pagos_pedido(pedido_id: str):
    """
    Obtener todos los pagos de un pedido específico.
    Bloquea el acceso a pedidos web desde módulos internos.
    """
    try:
        # Buscar el pedido por ID
        pedido = pedidos_collection.find_one({"_id": ObjectId(pedido_id)})
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        # Verificar si es un pedido web - bloquear acceso desde módulos internos
        tipo_pedido = pedido.get("tipo_pedido")
        if tipo_pedido == "web":
            raise HTTPException(
                status_code=403,
                detail="Los pagos de pedidos web solo pueden ser vistos desde el módulo de pedidos-web"
            )
        
        # Obtener historial de pagos y total abonado
        historial_pagos = pedido.get("historial_pagos", [])
        total_abonado = pedido.get("total_abonado", 0)
        
        # Calcular total del pedido (items + adicionales)
        total_items = sum(item.get("precio", 0) * item.get("cantidad", 0) for item in pedido.get("items", []))

        # Calcular total de adicionales
        adicionales = pedido.get("adicionales", [])
        total_adicionales = 0
        if adicionales and isinstance(adicionales, list):
            for adicional in adicionales:
                cantidad = adicional.get("cantidad", 1)
                precio = adicional.get("precio", 0)
                total_adicionales += precio * cantidad

        total_pedido = total_items + total_adicionales
        saldo_pendiente = total_pedido - total_abonado
        
        return {
            "pedido_id": pedido_id,
            "historial_pagos": historial_pagos,
            "total_abonado": total_abonado,
            "total_pedido": total_pedido,
            "saldo_pendiente": saldo_pendiente,
            "estado_pago": pedido.get("pago", "")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener pagos: {str(e)}")

@router.post("/{pedido_id}/abono/{index}/aprobar")
async def aprobar_abono_pendiente(
    pedido_id: str,
    index: int,
    current_user: dict = Depends(get_current_user)
):
    """
    Aprobar un abono pendiente en el historial de pagos de un pedido.
    Cambia el estado del abono de "pendiente" a "abonado" o "pagado".
    """
    try:
        # Verificar permisos de administrador
        if current_user.get("rol") != "admin":
            raise HTTPException(status_code=403, detail="No tienes permisos para aprobar abonos")
        
        # Validar pedido_id
        try:
            pedido_obj_id = ObjectId(pedido_id)
        except Exception:
            raise HTTPException(status_code=400, detail="ID de pedido inválido")
        
        # Buscar el pedido
        pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        # Verificar si es un pedido web - bloquear acceso desde módulos internos
        tipo_pedido = pedido.get("tipo_pedido")
        if tipo_pedido == "web":
            raise HTTPException(
                status_code=403,
                detail="Los abonos de pedidos web solo pueden ser gestionados desde el módulo de pedidos-web"
            )
        
        # Obtener historial de pagos
        historial_pagos = pedido.get("historial_pagos", [])
        
        # Validar índice
        if index < 0 or index >= len(historial_pagos):
            raise HTTPException(status_code=400, detail=f"Índice de abono inválido. Debe estar entre 0 y {len(historial_pagos) - 1}")
        
        # Obtener el abono a aprobar
        abono = historial_pagos[index]
        
        # Verificar que el abono esté pendiente
        estado_actual = abono.get("estado", "sin pago")
        if estado_actual not in ["pendiente", "sin pago"]:
            raise HTTPException(
                status_code=400, 
                detail=f"El abono ya está aprobado o procesado. Estado actual: {estado_actual}"
            )
        
        # Calcular el total del pedido (items + adicionales)
        monto_total_items = sum(
            float(item.get("precio", 0)) * float(item.get("cantidad", 0))
            for item in pedido.get("items", [])
        )
        
        # Sumar adicionales si existen
        monto_total_adicionales = 0.0
        adicionales = pedido.get("adicionales", [])
        if adicionales and isinstance(adicionales, list):
            for adicional in adicionales:
                if isinstance(adicional, dict):
                    precio = float(adicional.get("precio", 0))
                    cantidad = float(adicional.get("cantidad", 1))
                    monto_total_adicionales += precio * cantidad
        
        total_pedido = monto_total_items + monto_total_adicionales
        total_abonado_actual = float(pedido.get("total_abonado", 0))
        monto_abono = float(abono.get("monto", 0))
        
        # Si el abono estaba pendiente, ahora se suma al total_abonado
        nuevo_total_abonado = total_abonado_actual + monto_abono
        
        # Determinar el nuevo estado del pedido
        if nuevo_total_abonado >= total_pedido - 0.01:  # Tolerancia para floats
            nuevo_estado_pago = "pagado"
            nuevo_estado_abono = "pagado"
        else:
            nuevo_estado_pago = "abonado"
            nuevo_estado_abono = "abonado"
        
        # Actualizar el abono en el historial usando la sintaxis de MongoDB para actualizar array
        update_query = {
            "$set": {
                f"historial_pagos.{index}.estado": nuevo_estado_abono,
                "total_abonado": nuevo_total_abonado,
                "pago": nuevo_estado_pago,
                "fecha_actualizacion": datetime.now().isoformat()
            }
        }
        
        result = pedidos_collection.update_one(
            {"_id": pedido_obj_id},
            update_query
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Error al actualizar el abono")
        
        # Obtener el pedido actualizado
        pedido_actualizado = pedidos_collection.find_one({"_id": pedido_obj_id})
        historial_actualizado = pedido_actualizado.get("historial_pagos", [])
        
        # Verificar si el pedido debería estar en orden4 (Facturación)
        # Si todos los items tienen estado_item >= 4, mover a orden4
        try:
            items = pedido_actualizado.get("items", [])
            if items:
                todos_completos = all(item.get("estado_item", 0) >= 4 for item in items)
                estado_general = pedido_actualizado.get("estado_general", "")
                
                if todos_completos and estado_general in ["orden1", "orden2", "orden3"]:
                    # Mover pedido a orden4 (Facturación)
                    pedidos_collection.update_one(
                        {"_id": pedido_obj_id},
                        {"$set": {"estado_general": "orden4"}}
                    )
                    print(f"DEBUG APROBAR ABONO: Pedido {pedido_id} movido a orden4 después de aprobar abono")
        except Exception as e:
            print(f"ERROR APROBAR ABONO: Error verificando si pedido debe estar en orden4: {e}")
            # No lanzar error, solo loggear
        
        return {
            "message": f"Abono aprobado exitosamente",
            "pedido_id": pedido_id,
            "abono_index": index,
            "abono_aprobado": historial_actualizado[index] if index < len(historial_actualizado) else None,
            "total_abonado": nuevo_total_abonado,
            "estado_pago": nuevo_estado_pago,
            "historial_pagos": historial_actualizado
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR APROBAR ABONO: {str(e)}")
        import traceback
        print(f"ERROR APROBAR ABONO TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al aprobar abono: {str(e)}")

@router.post("/{pedido_id}/abono")
async def agregar_abono_pedido(
    pedido_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Agregar un nuevo abono a un pedido.
    El abono puede ser pendiente o aprobado automáticamente según el parámetro.
    """
    try:
        # Verificar permisos de administrador
        if current_user.get("rol") != "admin":
            raise HTTPException(status_code=403, detail="No tienes permisos para agregar abonos")
        
        # Validar pedido_id
        try:
            pedido_obj_id = ObjectId(pedido_id)
        except Exception:
            raise HTTPException(status_code=400, detail="ID de pedido inválido")
        
        # Buscar el pedido
        pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        # Obtener datos del request
        data = await request.json()
        monto = float(data.get("monto", 0))
        metodo = data.get("metodo")  # ID del método de pago
        estado = data.get("estado", "pendiente")  # "pendiente", "abonado", "pagado"
        numero_referencia = data.get("numero_referencia")
        comprobante_url = data.get("comprobante_url")
        concepto = data.get("concepto")
        
        if monto <= 0:
            raise HTTPException(status_code=400, detail="El monto debe ser mayor que 0")
        
        # Calcular el total del pedido (items + adicionales)
        monto_total_items = sum(
            float(item.get("precio", 0)) * float(item.get("cantidad", 0))
            for item in pedido.get("items", [])
        )
        
        # Sumar adicionales si existen
        monto_total_adicionales = 0.0
        adicionales = pedido.get("adicionales", [])
        if adicionales and isinstance(adicionales, list):
            for adicional in adicionales:
                if isinstance(adicional, dict):
                    precio = float(adicional.get("precio", 0))
                    cantidad = float(adicional.get("cantidad", 1))
                    monto_total_adicionales += precio * cantidad
        
        total_pedido = monto_total_items + monto_total_adicionales
        total_abonado_actual = float(pedido.get("total_abonado", 0))
        
        # Crear registro de abono
        nuevo_abono = {
            "fecha": datetime.now().isoformat(),
            "monto": monto,
            "estado": estado,
        }
        
        if metodo:
            nuevo_abono["metodo"] = str(metodo)
        if numero_referencia:
            nuevo_abono["numero_referencia"] = numero_referencia
        if comprobante_url:
            nuevo_abono["comprobante_url"] = comprobante_url
        if concepto:
            nuevo_abono["concepto"] = concepto
        
        # Si el abono se aprueba automáticamente, actualizar total_abonado
        if estado in ["abonado", "pagado"]:
            nuevo_total_abonado = total_abonado_actual + monto
            
            # Determinar el nuevo estado del pedido
            if nuevo_total_abonado >= total_pedido - 0.01:  # Tolerancia para floats
                nuevo_estado_pago = "pagado"
                nuevo_abono["estado"] = "pagado"
            else:
                nuevo_estado_pago = "abonado"
        else:
            # Si es pendiente, no se suma al total_abonado
            nuevo_total_abonado = total_abonado_actual
            nuevo_estado_pago = pedido.get("pago", "sin pago")
            if nuevo_total_abonado > 0:
                nuevo_estado_pago = "abonado"
        
        # Preparar actualización
        update_query = {
            "$push": {"historial_pagos": nuevo_abono},
            "$set": {
                "total_abonado": nuevo_total_abonado,
                "pago": nuevo_estado_pago,
                "fecha_actualizacion": datetime.now().isoformat()
            }
        }
        
        result = pedidos_collection.update_one(
            {"_id": pedido_obj_id},
            update_query
        )
        
        if result.modified_count == 0:
            raise HTTPException(status_code=500, detail="Error al agregar el abono")
        
        # Obtener el pedido actualizado
        pedido_actualizado = pedidos_collection.find_one({"_id": pedido_obj_id})
        historial_actualizado = pedido_actualizado.get("historial_pagos", [])
        
        # Verificar si el pedido debería estar en orden4 (Facturación)
        # Si todos los items tienen estado_item >= 4, mover a orden4
        try:
            items = pedido_actualizado.get("items", [])
            if items:
                todos_completos = all(item.get("estado_item", 0) >= 4 for item in items)
                estado_general = pedido_actualizado.get("estado_general", "")
                
                if todos_completos and estado_general in ["orden1", "orden2", "orden3"]:
                    # Mover pedido a orden4 (Facturación)
                    pedidos_collection.update_one(
                        {"_id": pedido_obj_id},
                        {"$set": {"estado_general": "orden4"}}
                    )
                    print(f"DEBUG AGREGAR ABONO: Pedido {pedido_id} movido a orden4 después de agregar abono")
        except Exception as e:
            print(f"ERROR AGREGAR ABONO: Error verificando si pedido debe estar en orden4: {e}")
            # No lanzar error, solo loggear
        
        return {
            "message": "Abono agregado exitosamente",
            "pedido_id": pedido_id,
            "abono": nuevo_abono,
            "total_abonado": nuevo_total_abonado,
            "estado_pago": nuevo_estado_pago,
            "historial_pagos": historial_actualizado
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR AGREGAR ABONO: {str(e)}")
        import traceback
        print(f"ERROR AGREGAR ABONO TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al agregar abono: {str(e)}")

# ========================================
# ENDPOINT PARA ELIMINAR PEDIDOS
# ========================================

@router.delete("/{pedido_id}")
async def eliminar_pedido(
    pedido_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Eliminar un pedido y todos sus datos asociados.
    Solo administradores pueden eliminar pedidos.
    Elimina:
    - El pedido de la base de datos
    - Facturas asociadas (confirmadas y de cliente)
    - Mensajes del chat asociados
    """
    try:
        # Verificar que el usuario sea administrador
        if current_user.get("rol") != "admin":
            raise HTTPException(status_code=403, detail="Solo los administradores pueden eliminar pedidos")
        
        # Validar pedido_id
        try:
            pedido_obj_id = ObjectId(pedido_id)
        except Exception:
            raise HTTPException(status_code=400, detail="ID de pedido inválido")
        
        # Buscar el pedido para verificar que existe
        pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        # Obtener información del pedido antes de eliminar
        pedido_info = {
            "pedido_id": pedido_id,
            "numero_orden": pedido.get("numero_orden", ""),
            "cliente_nombre": pedido.get("cliente_nombre", ""),
            "cliente_id": pedido.get("cliente_id", "")
        }
        
        # Eliminar facturas asociadas
        facturas_eliminadas = 0
        
        # Eliminar facturas confirmadas (usa pedidoId como campo)
        facturas_confirmadas_collection = db["facturas_confirmadas"]
        result_facturas_confirmadas = facturas_confirmadas_collection.delete_many({"pedidoId": pedido_id})
        facturas_eliminadas += result_facturas_confirmadas.deleted_count
        
        # También intentar eliminar con ObjectId por si acaso
        try:
            result_facturas_confirmadas_obj = facturas_confirmadas_collection.delete_many({"pedidoId": str(pedido_obj_id)})
            facturas_eliminadas += result_facturas_confirmadas_obj.deleted_count
        except:
            pass
        
        # Eliminar facturas de cliente (usa pedido_id como campo)
        result_facturas_cliente = facturas_cliente_collection.delete_many({"pedido_id": pedido_id})
        facturas_eliminadas += result_facturas_cliente.deleted_count
        
        # También intentar eliminar con ObjectId convertido a string
        try:
            result_facturas_cliente_obj = facturas_cliente_collection.delete_many({"pedido_id": str(pedido_obj_id)})
            facturas_eliminadas += result_facturas_cliente_obj.deleted_count
        except:
            pass
        
        # Eliminar mensajes asociados al pedido
        mensajes_eliminados = 0
        try:
            mensajes_collection = db["mensajes"]
            result_mensajes = mensajes_collection.delete_many({"pedido_id": pedido_id})
            mensajes_eliminados = result_mensajes.deleted_count
        except Exception as e:
            print(f"ADVERTENCIA: No se pudo eliminar mensajes (puede que la colección no exista aún): {str(e)}")
        
        # Eliminar el pedido
        result_pedido = pedidos_collection.delete_one({"_id": pedido_obj_id})
        
        if result_pedido.deleted_count == 0:
            raise HTTPException(status_code=404, detail="No se pudo eliminar el pedido")
        
        return {
            "message": "Pedido eliminado exitosamente",
            "success": True,
            "pedido_id": pedido_id,
            "numero_orden": pedido_info["numero_orden"],
            "cliente_nombre": pedido_info["cliente_nombre"],
            "facturas_eliminadas": facturas_eliminadas,
            "mensajes_eliminados": mensajes_eliminados
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR ELIMINAR PEDIDO: {str(e)}")
        import traceback
        print(f"ERROR ELIMINAR PEDIDO TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al eliminar pedido: {str(e)}")

# ========================================
# ENDPOINT PARA DEBUGGING DE PEDIDOS
# ========================================

@router.get("/debug-pedido/{pedido_id}")
async def debug_pedido(pedido_id: str):
    """Endpoint para debuggear el estado de un pedido específico"""
    try:
        print(f"DEBUG PEDIDO: Verificando pedido {pedido_id}")
        
        # Validar ID
        if not pedido_id or len(pedido_id) != 24:
            raise HTTPException(status_code=400, detail="ID de pedido inválido")
        
        # Obtener el pedido
        try:
            pedido_obj_id = ObjectId(pedido_id)
            pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
        except Exception as e:
            print(f"Error convirtiendo ObjectId: {e}")
            raise HTTPException(status_code=400, detail="ID de pedido inválido")
        
        if not pedido:
            return {
                "success": False,
                "message": "Pedido no encontrado",
                "pedido_id": pedido_id
            }
        
        # Analizar el estado del pedido
        seguimiento = pedido.get("seguimiento", [])
        items = pedido.get("items", [])
        
        # Determinar en qué módulos están los items
        estado_items = {}
        for item in items:
            if isinstance(item, dict) and item.get("_id"):
                item_id = str(item.get("_id"))
                estado_items[item_id] = {
                    "descripcion": item.get("descripcion", "Sin descripción"),
                    "modulo_actual": determinar_modulo_actual_item(pedido, item_id),
                    "asignaciones": []
                }
        
        # Analizar asignaciones por módulo
        modulos_estado = {
            1: {"nombre": "herreria", "items_en_proceso": 0, "items_terminados": 0, "items_pendientes": 0},
            2: {"nombre": "masillar", "items_en_proceso": 0, "items_terminados": 0, "items_pendientes": 0},
            3: {"nombre": "manillar", "items_en_proceso": 0, "items_terminados": 0, "items_pendientes": 0},
            4: {"nombre": "listo_facturar", "items_en_proceso": 0, "items_terminados": 0, "items_pendientes": 0}
        }
        
        for proceso in seguimiento:
            if isinstance(proceso, dict):
                orden = proceso.get("orden", 1)
                asignaciones = proceso.get("asignaciones_articulos", [])
                
                if isinstance(asignaciones, list):
                    for asignacion in asignaciones:
                        if isinstance(asignacion, dict):
                            item_id = asignacion.get("itemId")
                            estado = asignacion.get("estado", "pendiente")
                            
                            if item_id in estado_items:
                                estado_items[item_id]["asignaciones"].append({
                                    "modulo": orden,
                                    "estado": estado,
                                    "empleado": asignacion.get("nombreempleado", "Sin empleado")
                                })
                                
                                if estado == "en_proceso":
                                    modulos_estado[orden]["items_en_proceso"] += 1
                                elif estado == "terminado":
                                    modulos_estado[orden]["items_terminados"] += 1
                                else:
                                    modulos_estado[orden]["items_pendientes"] += 1
        
        # Determinar si está listo para facturar
        total_items = len(items)
        items_completados = sum(1 for item_data in estado_items.values() 
                              if item_data["modulo_actual"] > 3)
        
        listo_para_facturar = items_completados == total_items and total_items > 0
        
        return {
            "success": True,
            "pedido_id": pedido_id,
            "cliente": pedido.get("cliente_nombre", "Sin cliente"),
            "estado_general": pedido.get("estado_general", "desconocido"),
            "total_items": total_items,
            "items_completados": items_completados,
            "listo_para_facturar": listo_para_facturar,
            "modulos_estado": modulos_estado,
            "estado_items": estado_items,
            "seguimiento_count": len(seguimiento),
            "items_count": len(items)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR DEBUG PEDIDO: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "pedido_id": pedido_id
        }

# ========================================
# NUEVOS ENDPOINTS PARA FLUJO DE PRODUCCIÓN INTELIGENTE
# ========================================

@router.get("/empleados-por-modulo/{pedido_id}/{item_id}")
async def get_empleados_por_modulo(pedido_id: str, item_id: str):
    """
    Retorna empleados filtrados por módulo específico
    """
    try:
        # Validar IDs
        if not pedido_id or len(pedido_id) != 24:
            raise HTTPException(status_code=400, detail="ID de pedido inválido")
        if not item_id or len(item_id) != 24:
            raise HTTPException(status_code=400, detail="ID de item inválido")
        
        # Obtener el pedido
        try:
            pedido_obj_id = ObjectId(pedido_id)
            pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
        except Exception as e:
            raise HTTPException(status_code=400, detail="ID de pedido inválido")
        
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        # Encontrar el item específico
        item = None
        for i in pedido.get("items", []):
            if str(i.get("_id")) == item_id:
                item = i
                break
        
        if not item:
            raise HTTPException(status_code=404, detail="Item no encontrado")
        
        estado_item = item.get("estado_item", 1)
        
        # Determinar módulos permitidos según el estado ACTUAL del item
        modulos_permitidos = []
        if estado_item == 1:  # Herrería
            modulos_permitidos = ["herreria", "masillar", "pintar", "ayudante"]
        elif estado_item == 2:  # Masillar/Pintar
            modulos_permitidos = ["masillar", "pintar", "ayudante"]
        elif estado_item == 3:  # Manillar
            modulos_permitidos = ["manillar", "ayudante"]
        elif estado_item == 4:  # Facturación
            modulos_permitidos = ["facturacion", "ayudante"]
        
        # Obtener empleados con esos permisos
        empleados = list(empleados_collection.find(
            {
                "activo": True,
                "$or": [
                    {"permisos": {"$in": modulos_permitidos}},
                    {"cargo": {"$regex": "|".join(modulos_permitidos), "$options": "i"}}
                ]
            },
            {
                "_id": 1,
                "identificador": 1,
                "nombreCompleto": 1,
                "cargo": 1,
                "permisos": 1,
                "pin": 1
            }
        ).limit(50))
        
        # Si no hay empleados con permisos, usar filtrado por cargo/nombre
        if not empleados:
            empleados = list(empleados_collection.find({
                "activo": True
            }, {
                "_id": 1,
                "identificador": 1,
                "nombreCompleto": 1,
                "cargo": 1,
                "pin": 1
            }).limit(50))
            
            empleados_disponibles = []
            for emp in empleados:
                cargo = emp.get("cargo", "").upper()
                nombre = emp.get("nombreCompleto", "").upper()
                
                tiene_permiso = False
                if estado_item == 1:  # Herreria
                    if ("HERRERO" in cargo or "HERRERO" in nombre) or \
                       ("MASILLADOR" in cargo or "MASILLADOR" in nombre or "PINTOR" in cargo or "PINTOR" in nombre) or \
                       ("AYUDANTE" in cargo or "AYUDANTE" in nombre):
                        tiene_permiso = True
                elif estado_item == 2:  # Masillar/Pintar
                    if ("MASILLADOR" in cargo or "MASILLADOR" in nombre or "PINTOR" in cargo or "PINTOR" in nombre) or \
                       ("AYUDANTE" in cargo or "AYUDANTE" in nombre):
                        tiene_permiso = True
                elif estado_item == 3:  # Manillar
                    if ("MANILLAR" in cargo or "MANILLAR" in nombre) or \
                       ("AYUDANTE" in cargo or "AYUDANTE" in nombre):
                        tiene_permiso = True
                elif estado_item == 4:  # Facturación
                    if ("FACTURACION" in cargo or "FACTURACION" in nombre or "VENDEDOR" in cargo or "VENDEDOR" in nombre):
                        tiene_permiso = True
                
                if tiene_permiso:
                    empleados_disponibles.append({
                        "_id": str(emp["_id"]),
                        "identificador": emp.get("identificador"),
                        "nombreCompleto": emp.get("nombreCompleto"),
                        "cargo": emp.get("cargo"),
                        "pin": emp.get("pin"),
                        "activo": True
                    })
        else:
            # Procesar empleados encontrados con permisos
            empleados_disponibles = []
            for emp in empleados:
                empleados_disponibles.append({
                    "_id": str(emp["_id"]),
                    "identificador": emp.get("identificador"),
                    "nombreCompleto": emp.get("nombreCompleto"),
                    "cargo": emp.get("cargo"),
                    "permisos": emp.get("permisos", []),
                    "pin": emp.get("pin"),
                    "activo": True
                })
        
        return {
            "success": True,
            "modulo_actual": estado_item,
            "modulos_permitidos": modulos_permitidos,
            "empleados": empleados_disponibles,
            "total": len(empleados_disponibles)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error en empleados por módulo: {e}")
        return {
            "success": False,
            "empleados": [],
            "total": 0,
            "error": str(e)
        }

@router.get("/comisiones/produccion/enproceso/")
async def obtener_comisiones_en_proceso(empleado_id: str = None):
    """
    Endpoint para obtener asignaciones en proceso
    Si no se especifica empleado_id, retorna todas las asignaciones
    """
    try:
        query = {"estado_subestado": "en_proceso"}
        if empleado_id:
            query["empleado_id"] = empleado_id
            
        asignaciones = list(pedidos_collection.find(query).limit(100))
        
        # Agregar información del cliente
        for asignacion in asignaciones:
            pedido = pedidos_collection.find_one(
                {"_id": ObjectId(asignacion["pedido_id"])},
                {"cliente_nombre": 1}
            )
            if pedido:
                asignacion["cliente"] = {"cliente_nombre": pedido.get("cliente_nombre", "")}
        
        return {
            "success": True,
            "asignaciones": asignaciones,
            "total": len(asignaciones)
        }
        
    except Exception as e:
        print(f"Error en comisiones en proceso: {e}")
        return {
            "success": False,
            "asignaciones": [],
            "total": 0,
            "error": str(e)
        }

def determinar_modulo_actual_item(pedido: dict, item_id: str) -> int:
    """Determinar en qué módulo está actualmente el item"""
    try:
        seguimiento = pedido.get("seguimiento", [])
        
        # Validar que seguimiento sea una lista
        if not isinstance(seguimiento, list):
            return 1
        
        # Buscar el item en las asignaciones activas
        for proceso in seguimiento:
            if not isinstance(proceso, dict):
                continue
                
            asignaciones = proceso.get("asignaciones_articulos", [])
            if not isinstance(asignaciones, list):
                continue
                
            for asignacion in asignaciones:
                if not isinstance(asignacion, dict):
                    continue
                    
                if asignacion.get("itemId") == item_id:
                    estado = asignacion.get("estado", "pendiente")
                    if estado == "en_proceso":
                        return proceso.get("orden", 1)
        
        # Si no está en proceso, buscar el primer módulo disponible
        return determinar_primer_modulo_disponible(pedido, item_id)
        
    except Exception as e:
        print(f"Error en determinar_modulo_actual_item: {e}")
        return 1

def determinar_primer_modulo_disponible(pedido: dict, item_id: str) -> int:
    """Determinar el primer módulo disponible para el item"""
    try:
        seguimiento = pedido.get("seguimiento", [])
        
        # Validar que seguimiento sea una lista
        if not isinstance(seguimiento, list):
            return 1
        
        # Buscar el primer módulo donde el item no esté completado
        for proceso in seguimiento:
            if not isinstance(proceso, dict):
                continue
                
            orden = proceso.get("orden", 1)
            asignaciones = proceso.get("asignaciones_articulos", [])
            
            if not isinstance(asignaciones, list):
                continue
            
            # Verificar si el item ya está completado en este módulo
            item_completado = False
            for asignacion in asignaciones:
                if not isinstance(asignacion, dict):
                    continue
                if asignacion.get("itemId") == item_id and asignacion.get("estado") == "terminado":
                    item_completado = True
                    break
            
            # Si no está completado, este es el módulo disponible
            if not item_completado:
                return orden
        
        # Si todos los módulos están completados, retornar el siguiente módulo
        return len(seguimiento) + 1 if seguimiento else 1
        
    except Exception as e:
        print(f"Error en determinar_primer_modulo_disponible: {e}")
        return 1

def filtrar_empleados_por_modulo(empleados: list, modulo_actual: int) -> list:
    """Filtrar empleados según el módulo actual usando permisos"""
    try:
        empleados_filtrados = []
        
        # Validar que empleados sea una lista
        if not isinstance(empleados, list):
            return []
        
        # Mapeo de módulos a permisos requeridos
        modulo_permisos = {
            1: ["herreria", "ayudante"],  # Herreria
            2: ["masillar", "pintar", "ayudante"],  # Masillar/Pintar
            3: ["manillar", "ayudante"],  # Manillar
            4: ["facturacion", "ayudante"]  # Facturar
        }
        
        permisos_requeridos = modulo_permisos.get(modulo_actual, ["ayudante"])
        
        for empleado in empleados:
            if not isinstance(empleado, dict):
                continue
                
            permisos_empleado = empleado.get("permisos", [])
            if not isinstance(permisos_empleado, list):
                continue
            
            # Verificar si el empleado tiene al menos uno de los permisos requeridos
            tiene_permiso = any(permiso in permisos_empleado for permiso in permisos_requeridos)
            
            if tiene_permiso:
                empleados_filtrados.append(empleado)
        
        return empleados_filtrados
        
    except Exception as e:
        print(f"Error en filtrar_empleados_por_modulo: {e}")
        return []

@router.put("/asignacion/terminar-v2")
async def terminar_asignacion_articulo_v2(
    pedido_id: str = Body(...),
    orden: Union[int, str] = Body(...),
    item_id: str = Body(...),
    empleado_id: str = Body(...),
    estado: str = Body(...),
    fecha_fin: str = Body(...),
    pin: Optional[str] = Body(None)
):
    """Endpoint mejorado para terminar una asignación de artículo con flujo flexible"""
    print(f"DEBUG TERMINAR V2: === INICIANDO TERMINACIÓN ===")
    print(f"DEBUG TERMINAR V2: pedido_id={pedido_id}, item_id={item_id}, empleado_id={empleado_id}")
    print(f"DEBUG TERMINAR V2: orden={orden}, estado={estado}, pin={'***' if pin else None}")
    
    # Convertir orden a int
    try:
        orden_int = int(orden) if isinstance(orden, str) else orden
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"orden debe ser un número válido: {str(e)}")
    
    # VALIDAR PIN - ES OBLIGATORIO
    if not pin:
        raise HTTPException(status_code=400, detail="PIN es obligatorio para terminar asignación")
    
    # Buscar empleado y validar PIN
    empleado = buscar_empleado_por_identificador(empleado_id)
    if not empleado:
        raise HTTPException(status_code=404, detail=f"Empleado {empleado_id} no encontrado")
    
    if not empleado.get("pin"):
        raise HTTPException(status_code=400, detail="Empleado no tiene PIN configurado")
    
    if empleado.get("pin") != pin:
        raise HTTPException(status_code=400, detail="PIN incorrecto")
    
    print(f"DEBUG TERMINAR V2: PIN validado para empleado {empleado.get('nombreCompleto', empleado_id)}")
    
    # Obtener pedido
    try:
        pedido_obj_id = ObjectId(pedido_id)
        pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"pedido_id no válido: {str(e)}")
    
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    
    seguimiento = pedido.get("seguimiento", [])
    
    # Buscar y actualizar la asignación
    asignacion_actualizada = actualizar_asignacion_terminada(seguimiento, orden_int, item_id, empleado_id, estado, fecha_fin)
    if not asignacion_actualizada:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    
    # Determinar siguiente módulo basado en permisos del empleado
    siguiente_modulo = determinar_siguiente_modulo_flexible(empleado, orden_int)
    print(f"DEBUG TERMINAR V2: Siguiente módulo determinado: {siguiente_modulo}")
    
    # Mover item al siguiente módulo si es necesario
    if siguiente_modulo and siguiente_modulo <= 4:
        mover_item_siguiente_modulo(seguimiento, item_id, orden_int, siguiente_modulo)
    
    # Actualizar pedido en base de datos
    try:
        result = pedidos_collection.update_one(
            {"_id": pedido_obj_id},
            {"$set": {"seguimiento": seguimiento}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Pedido no encontrado al actualizar")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error actualizando pedido: {str(e)}")
    
    print(f"DEBUG TERMINAR V2: === TERMINACIÓN COMPLETADA ===")
    
    return {
        "message": "Asignación terminada correctamente",
        "success": True,
        "asignacion_actualizada": asignacion_actualizada,
        "siguiente_modulo": siguiente_modulo,
        "empleado_nombre": empleado.get("nombreCompleto", empleado_id),
        "pedido_id": pedido_id,
        "item_id": item_id
    }

def buscar_empleado_por_identificador(empleado_id: str):
    """Buscar empleado primero por _id (ObjectId), luego por identificador (string o número)"""
    try:
        # Intentar primero como ObjectId (_id)
        try:
            empleado_obj_id = ObjectId(empleado_id)
            empleado = empleados_collection.find_one({"_id": empleado_obj_id})
            if empleado:
                return empleado
        except Exception:
            pass
        
        # Si no se encuentra por _id, intentar por identificador como string
        empleado = empleados_collection.find_one({"identificador": empleado_id})
        if empleado:
            return empleado
        
        # Intentar identificador como número
        empleado_id_num = int(empleado_id)
        empleado = empleados_collection.find_one({"identificador": empleado_id_num})
        return empleado
        
    except (ValueError, Exception):
        return None

def actualizar_asignacion_terminada(seguimiento: list, orden: int, item_id: str, empleado_id: str, estado: str, fecha_fin: str):
    """Actualizar la asignación terminada en el seguimiento"""
    for proceso in seguimiento:
        if proceso.get("orden") == orden:
            asignaciones = proceso.get("asignaciones_articulos", [])
            for asignacion in asignaciones:
                if asignacion.get("itemId") == item_id and asignacion.get("empleadoId") == empleado_id:
                    # Actualizar asignación
                    asignacion["estado"] = estado
                    asignacion["estado_subestado"] = "terminado"
                    asignacion["fecha_fin"] = fecha_fin
                    
            return {
                        "itemId": item_id,
                        "empleadoId": empleado_id,
                        "estado": estado,
                        "fecha_fin": fecha_fin,
                        "orden": orden
                    }
    return None

def determinar_siguiente_modulo_flexible(empleado: dict, orden_actual: int) -> int:
    """Determinar el siguiente módulo basado en permisos del empleado (flujo flexible)"""
    permisos_empleado = empleado.get("permisos", [])
    
    # Mapeo de permisos a módulos
    permisos_modulos = {
        "herreria": 1,
        "masillar": 2,
        "pintar": 2,
        "manillar": 3,
        "facturacion": 4
    }
    
    # Si el empleado tiene permisos para múltiples módulos, puede saltar
    modulos_disponibles = []
    for permiso in permisos_empleado:
        if permiso in permisos_modulos:
            modulos_disponibles.append(permisos_modulos[permiso])
    
    # Ordenar módulos disponibles
    modulos_disponibles = sorted(set(modulos_disponibles))
    
    # Encontrar el siguiente módulo disponible después del actual
    for modulo in modulos_disponibles:
        if modulo > orden_actual:
            return modulo
    
    # Si no hay módulos disponibles después del actual, seguir flujo normal
    siguiente_modulo_normal = orden_actual + 1
    return siguiente_modulo_normal if siguiente_modulo_normal <= 4 else None

def mover_item_siguiente_modulo(seguimiento: list, item_id: str, orden_actual: int, siguiente_modulo: int):
    """Mover el item al siguiente módulo en el seguimiento"""
    # Buscar el proceso siguiente
    proceso_siguiente = None
    for proceso in seguimiento:
        if proceso.get("orden") == siguiente_modulo:
            proceso_siguiente = proceso
            break
    
    if not proceso_siguiente:
        print(f"DEBUG TERMINAR V2: Proceso siguiente {siguiente_modulo} no encontrado")
        return
    
    # Crear nueva asignación en el proceso siguiente
    nueva_asignacion = {
        "itemId": item_id,
        "empleadoId": None,  # Se asignará después
        "estado": "pendiente",
        "estado_subestado": "pendiente",
        "fecha_inicio": None,
        "fecha_fin": None
    }

# =========================
# ASIGNAR ITEMS (multi-asignación)
# =========================
@router.post("/asignar")
async def asignar_item_multiple(
    pedido_id: str = Body(...),
    item_id: str = Body(...),
    orden: Union[int, str] = Body(...),
    asignaciones: List[dict] = Body(...),  # [{ empleado_id, cantidad, modulo? }]
    descripcionitem: Optional[str] = Body(None),
    costoproduccion: Optional[float] = Body(None)
):
    """
    Asignar cantidades de un item a uno o varios empleados en un módulo (orden).
    Validaciones:
      - sum(cantidad) <= cantidad_pendiente_item
      - cantidad > 0
    Efectos:
      - Agrega entradas en seguimiento[orden].asignaciones_articulos con estado="en_proceso"
      - Mantiene acumuladores por item dentro del pedido
    """
    # Normalizar orden
    try:
        orden_int = int(orden) if isinstance(orden, str) else orden
    except Exception:
        raise HTTPException(status_code=400, detail="orden inválido")

    # Obtener pedido
    try:
        pedido_obj_id = ObjectId(pedido_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"pedido_id inválido: {str(e)}")

    pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    items = pedido.get("items", [])
    item_doc = next((it for it in items if str(it.get("id") or it.get("_id") or it.get("itemId")) == str(item_id)), None)
    if not item_doc:
        raise HTTPException(status_code=404, detail="Item del pedido no encontrado")

    cantidad_total_item = float(item_doc.get("cantidad", 0) or 0)
    cantidad_asignada_acumulada = float(item_doc.get("cantidad_asignada_acumulada", 0) or 0)
    cantidad_terminada_acumulada = float(item_doc.get("cantidad_terminada_acumulada", 0) or 0)
    cantidad_pendiente_item = max(cantidad_total_item - cantidad_asignada_acumulada, 0)

    # Validaciones sobre asignaciones
    if not isinstance(asignaciones, list) or len(asignaciones) == 0:
        raise HTTPException(status_code=400, detail="asignaciones debe ser una lista no vacía")

    suma_cantidades = 0.0
    for a in asignaciones:
        try:
            cantidad = float(a.get("cantidad", 0))
        except Exception:
            raise HTTPException(status_code=400, detail="cantidad inválida en asignación")
        if cantidad <= 0:
            raise HTTPException(status_code=400, detail="Cada cantidad debe ser mayor a 0")
        suma_cantidades += cantidad

    if suma_cantidades > cantidad_pendiente_item:
        raise HTTPException(status_code=400, detail=f"La suma de cantidades ({suma_cantidades}) excede la pendiente ({cantidad_pendiente_item})")

    # Preparar estructura de seguimiento para el módulo
    seguimiento = pedido.get("seguimiento", [])
    subestado = next((s for s in seguimiento if s.get("orden") == orden_int), None)
    if not subestado:
        subestado = {"orden": orden_int, "estado": "pendiente", "asignaciones_articulos": []}
        seguimiento.append(subestado)

    asignaciones_articulos = subestado.get("asignaciones_articulos", [])

    # Insertar cada asignación
    now_iso = datetime.now().isoformat()
    for a in asignaciones:
        empleado_id_val = str(a.get("empleado_id") or a.get("empleadoId") or "").strip()
        cantidad_val = float(a.get("cantidad", 0) or 0)
        if not empleado_id_val:
            raise HTTPException(status_code=400, detail="empleado_id es requerido en cada asignación")

        asignaciones_articulos.append({
            "itemId": str(item_id),
            "empleadoId": empleado_id_val,
            "cantidad_asignada": cantidad_val,
            "cantidad_terminada": 0.0,
            "estado": "en_proceso",
            "estado_subestado": "en_proceso",
            "fecha_inicio": now_iso,
            "modulo": orden_int,
            "orden": orden_int,
            "descripcionitem": descripcionitem or item_doc.get("descripcion", ""),
            "costoproduccion": costoproduccion if costoproduccion is not None else item_doc.get("costoProduccion")
        })

    subestado["asignaciones_articulos"] = asignaciones_articulos

    # Actualizar acumuladores del item
    nueva_asignada = cantidad_asignada_acumulada + suma_cantidades
    nueva_pendiente = max(cantidad_total_item - nueva_asignada, 0)

    for it in items:
        if str(it.get("id") or it.get("_id") or it.get("itemId")) == str(item_id):
            it["cantidad_total_item"] = cantidad_total_item
            it["cantidad_asignada_acumulada"] = nueva_asignada
            it["cantidad_terminada_acumulada"] = cantidad_terminada_acumulada
            it["cantidad_pendiente_item"] = nueva_pendiente
            break

    # Persistir cambios
    result = pedidos_collection.update_one(
        {"_id": pedido_obj_id},
        {"$set": {"seguimiento": seguimiento, "items": items}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pedido no encontrado al actualizar")

    return {
        "message": "Asignaciones registradas",
        "success": True,
        "pedido_id": pedido_id,
        "item_id": item_id,
        "orden": orden_int,
        "cantidad_total_item": cantidad_total_item,
        "cantidad_asignada_acumulada": nueva_asignada,
        "cantidad_terminada_acumulada": cantidad_terminada_acumulada,
        "cantidad_pendiente_item": nueva_pendiente,
    }
    
    # Agregar asignación al proceso siguiente
    if "asignaciones_articulos" not in proceso_siguiente:
        proceso_siguiente["asignaciones_articulos"] = []
    
    proceso_siguiente["asignaciones_articulos"].append(nueva_asignacion)
    print(f"DEBUG TERMINAR V2: Item {item_id} movido al módulo {siguiente_modulo}")

@router.get("/debug-estructura-empleados")
async def debug_estructura_empleados():
    """Endpoint para verificar la estructura real de los empleados"""
    try:
        # Obtener algunos empleados para ver su estructura
        empleados = list(empleados_collection.find({}).limit(5))
        
        # Convertir ObjectId a string y mostrar estructura
        empleados_formateados = []
        for empleado in empleados:
            empleado_dict = {}
            for key, value in empleado.items():
                if key == "_id":
                    empleado_dict[key] = str(value)
                else:
                    empleado_dict[key] = value
            empleados_formateados.append(empleado_dict)
        
        # También obtener el total de empleados
        total_empleados = empleados_collection.count_documents({})
        
        return {
            "total_empleados": total_empleados,
            "estructura_ejemplo": empleados_formateados,
            "campos_encontrados": list(empleados[0].keys()) if empleados else []
        }
        
    except Exception as e:
        return {"error": str(e)}

@router.get("/debug-item-en-pedido/{pedido_id}/{item_id}")
async def debug_item_en_pedido(pedido_id: str, item_id: str):
    """Debug para verificar si un item existe en un pedido"""
    try:
        # Buscar el pedido
        pedido = pedidos_collection.find_one({"_id": ObjectId(pedido_id)})
        if not pedido:
            return {"error": "Pedido no encontrado", "pedido_id": pedido_id}
        
        # Buscar el item en seguimiento
        seguimiento = pedido.get("seguimiento", [])
        if seguimiento is None:
            seguimiento = []
        
        item_encontrado = False
        modulo_actual = None
        
        for proceso in seguimiento:
            if proceso is None:
                continue
            asignaciones = proceso.get("asignaciones_articulos", [])
            if asignaciones is None:
                asignaciones = []
            for asignacion in asignaciones:
                if asignacion is None:
                    continue
                if asignacion.get("itemId") == item_id:
                    modulo_actual = proceso.get("orden")
                    item_encontrado = True
                    break
            if item_encontrado:
                break
        
        return {
            "pedido_id": pedido_id,
            "item_id": item_id,
            "item_encontrado": item_encontrado,
            "modulo_actual": modulo_actual,
            "total_procesos": len(seguimiento) if seguimiento else 0,
            "debug_info": {
                "seguimiento_length": len(seguimiento) if seguimiento else 0,
                "seguimiento_is_none": seguimiento is None,
                "primeros_procesos": [
                    {
                        "orden": p.get("orden") if p else None,
                        "nombre": p.get("nombre") if p else None,
                        "asignaciones_count": len(p.get("asignaciones_articulos", [])) if p and p.get("asignaciones_articulos") else 0
                    } for p in (seguimiento[:3] if seguimiento else [])
                ]
            }
        }
        
    except Exception as e:
        return {"error": str(e), "pedido_id": pedido_id, "item_id": item_id}

@router.get("/progreso-pedido/{pedido_id}")
async def get_progreso_pedido(pedido_id: str):
    """Obtener el estado de progreso de un pedido con barra de progreso mejorada"""
    try:
        print(f"DEBUG PROGRESO V2: Obteniendo progreso para pedido {pedido_id}")
        
        # Validar pedido_id
        if not pedido_id or len(pedido_id) != 24:
            raise HTTPException(status_code=400, detail="ID de pedido inválido")
        
        # Obtener el pedido
        try:
            pedido_obj_id = ObjectId(pedido_id)
            pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
        except Exception as e:
            print(f"Error convirtiendo ObjectId: {e}")
            raise HTTPException(status_code=400, detail="ID de pedido inválido")
        
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        # Obtener datos con validación
        seguimiento = pedido.get("seguimiento", [])
        items = pedido.get("items", [])
        
        # Validar que sean listas
        if not isinstance(seguimiento, list):
            seguimiento = []
        if not isinstance(items, list):
            items = []
        
        print(f"DEBUG PROGRESO V2: Items: {len(items)}, Seguimiento: {len(seguimiento)}")
        
        # Calcular progreso mejorado
        progreso_data = calcular_progreso_mejorado(items, seguimiento)
        
        return {
            "pedido_id": pedido_id,
            "modulos": progreso_data["modulos"],
            "progreso_general": progreso_data["progreso_general"],
            "total_items": progreso_data["total_items"],
            "items_completados": progreso_data["items_completados"],
            "estado": progreso_data["estado"],
            "detalle_items": progreso_data["detalle_items"]
        }
        
    except HTTPException:
        # Re-lanzar HTTPExceptions
        raise
    except Exception as e:
        print(f"ERROR PROGRESO V2: {e}")
        # Retornar estructura básica en lugar de error 500
        return {
            "pedido_id": pedido_id,
            "modulos": [
                {"orden": 1, "nombre": "Herreria/Soldadura", "completado": 0, "total": 0, "en_proceso": 0, "porcentaje": 0, "porcentaje_en_proceso": 0},
                {"orden": 2, "nombre": "Masillar/Pintar", "completado": 0, "total": 0, "en_proceso": 0, "porcentaje": 0, "porcentaje_en_proceso": 0},
                {"orden": 3, "nombre": "Manillar/Preparar", "completado": 0, "total": 0, "en_proceso": 0, "porcentaje": 0, "porcentaje_en_proceso": 0},
                {"orden": 4, "nombre": "Facturar", "completado": 0, "total": 0, "en_proceso": 0, "porcentaje": 0, "porcentaje_en_proceso": 0}
            ],
            "progreso_general": 0,
            "total_items": 0,
            "items_completados": 0,
            "estado": "pendiente",
            "detalle_items": []
        }

def calcular_progreso_mejorado(items: list, seguimiento: list) -> dict:
    """Calcular progreso mejorado con más precisión y manejo de errores"""
    
    try:
        # Validar inputs con más robustez
        if not isinstance(items, list):
            items = []
        if not isinstance(seguimiento, list):
            seguimiento = []
        
        # Filtrar items válidos (aceptar items con "id" o "_id")
        items_validos = []
        for item in items:
            if isinstance(item, dict) and (item.get("id") or item.get("_id")):
                items_validos.append(item)
        
        items = items_validos
        
        # Filtrar seguimiento válido
        seguimiento_valido = []
        for proceso in seguimiento:
            if isinstance(proceso, dict) and proceso.get("orden") is not None:
                seguimiento_valido.append(proceso)
        
        seguimiento = seguimiento_valido
        
        # Inicializar módulos
        modulos = [
            {"orden": 1, "nombre": "Herreria/Soldadura", "completado": 0, "total": 0, "en_proceso": 0},
            {"orden": 2, "nombre": "Masillar/Pintar", "completado": 0, "total": 0, "en_proceso": 0},
            {"orden": 3, "nombre": "Manillar/Preparar", "completado": 0, "total": 0, "en_proceso": 0},
            {"orden": 4, "nombre": "Facturar", "completado": 0, "total": 0, "en_proceso": 0}
        ]
        
        # Detalle por item
        detalle_items = []
        
        for item in items:
            try:
                # Validar que el item tenga la estructura esperada
                if not isinstance(item, dict):
                    continue
                    
                # Obtener item_id de "_id" o "id"
                item_id = str(item.get("_id", item.get("id", "")))
                if not item_id:
                    continue
                    
                item_nombre = item.get("descripcionitem", f"Item {item_id}")
                
                # Estado del item en cada módulo
                item_estados = {
                    "herreria": "pendiente",
                    "masillar": "pendiente", 
                    "manillar": "pendiente",
                    "facturar": "pendiente"
                }
                
                # Buscar estado del item en cada módulo
                for proceso in seguimiento:
                    try:
                        if not isinstance(proceso, dict):
                            continue
                            
                        orden = proceso.get("orden", 0)
                        if not isinstance(orden, (int, str)):
                            continue
                            
                        orden = int(orden)
                        asignaciones = proceso.get("asignaciones_articulos", [])
                        
                        if not isinstance(asignaciones, list):
                            continue
                        
                        for asignacion in asignaciones:
                            try:
                                if not isinstance(asignacion, dict):
                                    continue
                                    
                                asignacion_item_id = asignacion.get("itemId", "")
                                if str(asignacion_item_id) == item_id:
                                    estado_asignacion = asignacion.get("estado", "pendiente")
                                    
                                    # Mapear orden a módulo
                                    modulo_nombre = {
                                        1: "herreria",
                                        2: "masillar",
                                        3: "manillar", 
                                        4: "facturar"
                                    }.get(orden, "desconocido")
                                    
                                    if modulo_nombre in item_estados:
                                        item_estados[modulo_nombre] = estado_asignacion
                                break
                            except Exception as e:
                                print(f"Error procesando asignación: {e}")
                                continue
                    except Exception as e:
                        print(f"Error procesando proceso: {e}")
                        continue
                
                # Agregar detalle del item
                detalle_items.append({
                    "item_id": item_id,
                    "nombre": item_nombre,
                    "estados": item_estados
                })
                
                # Contar para cada módulo
                for modulo in modulos:
                    try:
                        modulo_nombre = modulo["nombre"].split("/")[0].lower()
                        if "herreria" in modulo_nombre:
                            modulo_key = "herreria"
                        elif "masillar" in modulo_nombre:
                            modulo_key = "masillar"
                        elif "manillar" in modulo_nombre:
                            modulo_key = "manillar"
                        elif "facturar" in modulo_nombre:
                            modulo_key = "facturar"
                        else:
                            continue
                        
                        estado_item = item_estados.get(modulo_key, "pendiente")
                        
                        if estado_item == "terminado":
                            modulo["completado"] += 1
                        elif estado_item == "en_proceso":
                            modulo["en_proceso"] += 1
                        
                        modulo["total"] += 1
                    except Exception as e:
                        print(f"Error contando módulo: {e}")
                        continue
                        
            except Exception as e:
                print(f"Error procesando item: {e}")
                continue
        
        # Calcular porcentajes
        for modulo in modulos:
            try:
                if modulo["total"] > 0:
                    modulo["porcentaje"] = round((modulo["completado"] / modulo["total"]) * 100, 1)
                    modulo["porcentaje_en_proceso"] = round((modulo["en_proceso"] / modulo["total"]) * 100, 1)
                else:
                    modulo["porcentaje"] = 0
                    modulo["porcentaje_en_proceso"] = 0
            except Exception as e:
                print(f"Error calculando porcentajes: {e}")
                modulo["porcentaje"] = 0
                modulo["porcentaje_en_proceso"] = 0
        
        # Calcular progreso general más preciso
        total_items = len(detalle_items)
        
        # Contar items completamente terminados basado en estado_item
        items_terminados = 0
        for item in items:
            try:
                estado_item = item.get("estado_item", 0)
                # Item terminado si estado_item = 4
                if estado_item >= 4:
                    items_terminados += 1
            except Exception as e:
                print(f"Error contando item terminado: {e}")
                continue
        
        # Calcular progreso basado en estado_item de los items
        # Progreso = promedio de estado_item / 4 * 100
        suma_estado_items = 0
        for item in items:
            try:
                estado_item = item.get("estado_item", 0)
                suma_estado_items += min(estado_item, 4)  # Máximo 4
            except Exception as e:
                print(f"Error sumando estado_item: {e}")
                continue
        
        # Progreso general = porcentaje promedio de estado_item
        progreso_general = round((suma_estado_items / (total_items * 4)) * 100, 1) if total_items > 0 else 0
        
        # Determinar estado general
        if items_terminados == total_items and total_items > 0:
            estado_general = "completado"
        elif progreso_general > 0:
            estado_general = "en_proceso"
        else:
            estado_general = "pendiente"
        
        return {
            "modulos": modulos,
            "progreso_general": progreso_general,
            "total_items": total_items,
            "items_completados": items_terminados,
            "estado": estado_general,
            "detalle_items": detalle_items
        }
        
    except Exception as e:
        print(f"Error crítico en calcular_progreso_mejorado: {e}")
        # Retornar estructura básica en caso de error
        return {
            "modulos": [
                {"orden": 1, "nombre": "Herreria/Soldadura", "completado": 0, "total": 0, "en_proceso": 0, "porcentaje": 0, "porcentaje_en_proceso": 0},
                {"orden": 2, "nombre": "Masillar/Pintar", "completado": 0, "total": 0, "en_proceso": 0, "porcentaje": 0, "porcentaje_en_proceso": 0},
                {"orden": 3, "nombre": "Manillar/Preparar", "completado": 0, "total": 0, "en_proceso": 0, "porcentaje": 0, "porcentaje_en_proceso": 0},
                {"orden": 4, "nombre": "Facturar", "completado": 0, "total": 0, "en_proceso": 0, "porcentaje": 0, "porcentaje_en_proceso": 0}
            ],
            "progreso_general": 0,
            "total_items": 0,
            "items_completados": 0,
            "estado": "pendiente",
            "detalle_items": []
        }

@router.put("/inicializar-estado-items/")
async def inicializar_estado_items():
    """
    Inicializar estado_item = 0 en todos los items que no lo tengan
    """
    try:
        print("INICIALIZANDO: Buscando items sin estado_item")
        
        # Buscar todos los pedidos
        pedidos = list(pedidos_collection.find({}))
        items_actualizados = 0
        
        for pedido in pedidos:
            pedido_id = pedido["_id"]
            pedido_items_actualizados = 0
            
            # Actualizar cada item que no tenga estado_item
            for i, item in enumerate(pedido.get("items", [])):
                if not item.get("estado_item"):
                    result = pedidos_collection.update_one(
                        {
                            "_id": pedido_id,
                            f"items.{i}": item
                        },
                        {
                            "$set": {
                                f"items.{i}.estado_item": 0  # Estado pendiente
                            }
                        }
                    )
                    if result.modified_count > 0:
                        pedido_items_actualizados += 1
            
            if pedido_items_actualizados > 0:
                items_actualizados += pedido_items_actualizados
                print(f"INICIALIZANDO: Pedido {pedido_id} - {pedido_items_actualizados} items actualizados")
        
        return {
            "message": "Inicialización completada",
            "pedidos_procesados": len(pedidos),
            "items_actualizados": items_actualizados
        }
        
    except Exception as e:
        print(f"Error inicializando estado_items: {e}")
        return {"error": str(e)}

# ========================================
# ENDPOINTS PARA MÓDULO APARTADO
# ========================================

@router.get("/apartados/")
async def get_apartados():
    """
    Obtener todos los items en apartados
    """
    try:
        # Buscar items en la colección de apartados
        apartados = list(apartados_collection.find({}))
        
        # Convertir ObjectId a string
        for apartado in apartados:
            apartado["_id"] = str(apartado["_id"])
            apartado["pedido_id"] = str(apartado["pedido_id"])
            apartado["item_id"] = str(apartado["item_id"])
        
        return {
            "apartados": apartados,
            "total": len(apartados),
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR APARTADOS: Error al obtener apartados: {e}")
        raise HTTPException(status_code=500, detail=f"Error al obtener apartados: {str(e)}")

@router.delete("/apartados/{apartado_id}")
async def eliminar_apartado(apartado_id: str):
    """
    Eliminar un item de apartados
    """
    try:
        result = apartados_collection.delete_one({"_id": ObjectId(apartado_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Apartado no encontrado")
        
        return {
            "message": "Apartado eliminado correctamente",
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR APARTADOS: Error al eliminar apartado: {e}")
        raise HTTPException(status_code=500, detail=f"Error al eliminar apartado: {str(e)}")

@router.put("/apartados/{apartado_id}/marcar-facturado")
async def marcar_apartado_facturado(apartado_id: str):
    """
    Marcar un apartado como facturado
    """
    try:
        result = apartados_collection.update_one(
            {"_id": ObjectId(apartado_id)},
            {"$set": {
                "facturado": True,
                "fecha_facturado": datetime.now().isoformat()
            }}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Apartado no encontrado")
        
        return {
            "message": "Apartado marcado como facturado",
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR APARTADOS: Error al marcar como facturado: {e}")
        raise HTTPException(status_code=500, detail=f"Error al marcar como facturado: {str(e)}")

@router.post("/verificar-pedido-completo/{pedido_id}")
async def verificar_pedido_completo(pedido_id: str):
    """
    Verificar si un pedido puede avanzar a orden4 (Facturación)
    Si todos los items tienen estado_item >= 4, mueve el pedido a orden4 independientemente del estado actual
    """
    try:
        pedido_obj_id = ObjectId(pedido_id)
        pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
        
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        print(f"DEBUG VERIFICAR PEDIDO: Verificando pedido {pedido_id}")
        
        # Verificar si todos los items tienen estado_item >= 4
        items = pedido.get("items", [])
        if not items:
            return {
                "message": "Pedido sin items",
                "completado": False,
                "estado_general": pedido.get("estado_general", "")
            }
        
        todos_completos = all(item.get("estado_item", 0) >= 4 for item in items)
        
        estado_general = pedido.get("estado_general", "")
        print(f"DEBUG VERIFICAR PEDIDO: todos_completos={todos_completos}, estado_general={estado_general}")
        print(f"DEBUG VERIFICAR PEDIDO: Items: {[(item.get('id', 'N/A'), item.get('estado_item', 'N/A')) for item in items]}")
        
        # Si todos los items están completos y el pedido está en orden1, orden2 o orden3
        if todos_completos and estado_general in ["orden1", "orden2", "orden3"]:
            # Actualizar estado_general a orden4
            result = pedidos_collection.update_one(
                {"_id": pedido_obj_id},
                {"$set": {"estado_general": "orden4"}}
            )
            
            print(f"DEBUG VERIFICAR PEDIDO: Pedido movido de {estado_general} a orden4 - {result.modified_count} documentos modificados")
            
            return {
                "message": "Pedido completado y movido a Facturación",
                "estado_anterior": estado_general,
                "estado_nuevo": "orden4",
                "completado": True
            }
        
        return {
            "message": "Pedido aún en proceso" if not todos_completos else f"Pedido completo pero en estado {estado_general}",
            "completado": todos_completos,
            "estado_general": estado_general
        }
        
    except Exception as e:
        print(f"ERROR VERIFICAR PEDIDO: Error verificando pedido: {e}")
        import traceback
        print(f"ERROR VERIFICAR PEDIDO: Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error verificando pedido: {str(e)}")

@router.post("/verificar-todos-pedidos-completos")
async def verificar_todos_pedidos_completos():
    """
    Verificar todos los pedidos y mover aquellos que tienen 100% (todos items estado_item >= 4) a orden4
    Útil para corregir pedidos que deberían estar en Facturación pero no lo están
    """
    try:
        # Buscar todos los pedidos que están en orden1, orden2 o orden3
        pedidos = pedidos_collection.find({
            "estado_general": {"$in": ["orden1", "orden2", "orden3"]}
        })
        
        pedidos_movidos = []
        pedidos_completos_no_movidos = []
        
        for pedido in pedidos:
            try:
                pedido_id = str(pedido["_id"])
                items = pedido.get("items", [])
                
                if not items:
                    continue
                
                # Verificar si todos los items tienen estado_item >= 4
                todos_completos = all(item.get("estado_item", 0) >= 4 for item in items)
                
                if todos_completos:
                    estado_general = pedido.get("estado_general", "")
                    # Mover a orden4
                    result = pedidos_collection.update_one(
                        {"_id": pedido["_id"]},
                        {"$set": {"estado_general": "orden4"}}
                    )
                    
                    if result.modified_count > 0:
                        pedidos_movidos.append({
                            "pedido_id": pedido_id,
                            "estado_anterior": estado_general,
                            "estado_nuevo": "orden4"
                        })
                    else:
                        pedidos_completos_no_movidos.append({
                            "pedido_id": pedido_id,
                            "estado_actual": estado_general,
                            "razon": "No se pudo actualizar"
                        })
                        
            except Exception as e:
                print(f"ERROR VERIFICAR TODOS: Error procesando pedido {pedido.get('_id', 'N/A')}: {e}")
                continue
        
        return {
            "message": f"Verificación completada. {len(pedidos_movidos)} pedidos movidos a orden4",
            "pedidos_movidos": pedidos_movidos,
            "pedidos_completos_no_movidos": pedidos_completos_no_movidos,
            "total_movidos": len(pedidos_movidos)
        }
        
    except Exception as e:
        print(f"ERROR VERIFICAR TODOS: Error verificando pedidos: {e}")
        import traceback
        print(f"ERROR VERIFICAR TODOS: Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error verificando pedidos: {str(e)}")

@router.post("/recalcular-total-abonado/{pedido_id}")
async def recalcular_total_abonado(pedido_id: str):
    """
    Recalcular el total_abonado de un pedido sumando todos los montos del historial_pagos
    Útil para corregir inconsistencias en el cálculo de abonos
    """
    try:
        pedido_obj_id = ObjectId(pedido_id)
        pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
        
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        historial_pagos = pedido.get("historial_pagos", [])
        
        # Calcular total_abonado sumando todos los montos del historial
        total_abonado_calculado = 0.0
        for pago in historial_pagos:
            if isinstance(pago, dict):
                monto = pago.get("monto", 0)
                # Solo sumar pagos que no estén pendientes
                estado_pago = pago.get("estado", "")
                if estado_pago not in ["pendiente", "sin pago"]:
                    total_abonado_calculado += float(monto)
        
        total_abonado_actual = float(pedido.get("total_abonado", 0))
        
        # Calcular total del pedido
        items = pedido.get("items", [])
        monto_total_items = sum(
            float(item.get("precio", 0)) * float(item.get("cantidad", 0))
            for item in items
        )
        
        # Sumar adicionales si existen
        monto_total_adicionales = 0.0
        adicionales = pedido.get("adicionales", [])
        if adicionales and isinstance(adicionales, list):
            for adicional in adicionales:
                if isinstance(adicional, dict):
                    precio = float(adicional.get("precio", 0))
                    cantidad = float(adicional.get("cantidad", 1))
                    monto_total_adicionales += precio * cantidad
        
        total_pedido = monto_total_items + monto_total_adicionales
        
        # Determinar nuevo estado de pago
        if total_abonado_calculado >= total_pedido - 0.01:  # Tolerancia para floats
            nuevo_estado_pago = "pagado"
        elif total_abonado_calculado > 0:
            nuevo_estado_pago = "abonado"
        else:
            nuevo_estado_pago = "sin pago"
        
        # Actualizar total_abonado y estado de pago
        result = pedidos_collection.update_one(
            {"_id": pedido_obj_id},
            {
                "$set": {
                    "total_abonado": total_abonado_calculado,
                    "pago": nuevo_estado_pago
                }
            }
        )
        
        return {
            "message": "Total abonado recalculado",
            "pedido_id": pedido_id,
            "total_abonado_anterior": total_abonado_actual,
            "total_abonado_nuevo": total_abonado_calculado,
            "total_pedido": total_pedido,
            "estado_pago_anterior": pedido.get("pago", ""),
            "estado_pago_nuevo": nuevo_estado_pago,
            "historial_pagos_count": len(historial_pagos),
            "modificado": result.modified_count > 0
        }
        
    except Exception as e:
        print(f"ERROR RECALCULAR ABONO: Error recalculando total abonado: {e}")
        import traceback
        print(f"ERROR RECALCULAR ABONO: Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error recalculando total abonado: {str(e)}")

# ============================================================================
# ENDPOINTS PARA CLIENTES AUTENTICADOS
# ============================================================================

@router.post("/cliente")
async def create_pedido_cliente(pedido: Pedido, cliente: dict = Depends(get_current_cliente)):
    """
    Crear pedido desde cliente autenticado.
    Los pedidos creados por clientes tienen tipo: "cliente"
    """
    try:
        # Obtener datos del cliente autenticado
        cliente_id = cliente.get("id")
        cliente_nombre = cliente.get("nombre")
        
        # Asegurar que el cliente_id del pedido coincida con el cliente autenticado
        pedido.cliente_id = cliente_id
        pedido.cliente_nombre = cliente_nombre
        pedido.creado_por = cliente.get("usuario")
        
        # Marcar el pedido como tipo "web" (desde /clientes)
        pedido_dict = pedido.dict()
        pedido_dict["tipo_pedido"] = "web"
        # Mantener compatibilidad con campo "tipo" por si acaso
        pedido_dict["tipo"] = "cliente"
        pedido_dict["fecha_creacion"] = datetime.now().isoformat()
        pedido_dict["fecha_actualizacion"] = datetime.now().isoformat()
        
        # Asegurar estado_item inicial para cada item
        for item in pedido_dict.get("items", []):
            if item.get("estado_item") is None:
                item["estado_item"] = 0
        
        # Insertar el pedido
        result = pedidos_collection.insert_one(pedido_dict)
        pedido_id = str(result.inserted_id)
        
        # Generar asignaciones unitarias para herrería (similar al endpoint normal)
        try:
            seguimiento = pedido_dict.get("seguimiento") or []
            orden_herreria = 1
            proceso_herreria = None
            
            for proc in seguimiento:
                if proc.get("orden") == orden_herreria:
                    proceso_herreria = proc
                    break
            
            if not proceso_herreria:
                proceso_herreria = {
                    "orden": orden_herreria,
                    "nombre_subestado": "Herreria / soldadura",
                    "estado": "pendiente",
                    "asignaciones_articulos": [],
                    "fecha_inicio": None,
                    "fecha_fin": None,
                }
                seguimiento.append(proceso_herreria)
            
            asignaciones_articulos = proceso_herreria.get("asignaciones_articulos") or []
            items_iter = pedido_dict.get("items", [])
            
            for it in items_iter:
                estado_item_val = it.get("estado_item", 0)
                cantidad_val = int(it.get("cantidad", 0) or 0)
                if estado_item_val == 0 and cantidad_val > 0:
                    item_id_ref = str(it.get("id") or it.get("_id") or "")
                    for idx in range(cantidad_val):
                        asignaciones_articulos.append({
                            "itemId": item_id_ref,
                            "empleadoId": None,
                            "nombreempleado": None,
                            "estado": "pendiente",
                            "fecha_inicio": None,
                            "fecha_fin": None,
                            "modulo": "herreria",
                            "cantidad": 1,
                            "unidad_index": idx + 1,
                        })
            
            proceso_herreria["asignaciones_articulos"] = asignaciones_articulos
            
            pedidos_collection.update_one(
                {"_id": ObjectId(pedido_id)},
                {"$set": {"seguimiento": seguimiento}},
            )
        except Exception as e:
            print(f"ERROR CREAR PEDIDO CLIENTE - asignaciones herreria: {e}")
        
        # Crear factura automáticamente para el pedido del cliente
        try:
            # Calcular monto total del pedido (items + adicionales)
            monto_total_items = sum(
                float(item.get("precio", 0)) * float(item.get("cantidad", 0))
                for item in pedido_dict.get("items", [])
            )
            
            # Sumar adicionales si existen
            monto_total_adicionales = 0.0
            adicionales = pedido_dict.get("adicionales", [])
            if adicionales and isinstance(adicionales, list):
                # Los adicionales pueden tener estructura: [{"descripcion": "...", "precio": 100, "cantidad": 1}]
                # O simplemente: [{"precio": 100}] si cantidad es siempre 1
                for adicional in adicionales:
                    if isinstance(adicional, dict):
                        precio = float(adicional.get("precio", 0))
                        cantidad = float(adicional.get("cantidad", 1))  # Default cantidad = 1
                        monto_total_adicionales += precio * cantidad
            
            monto_total = monto_total_items + monto_total_adicionales
            
            # Obtener total_abonado inicial del pedido (si viene con historial_pagos)
            total_abonado_inicial = 0.0
            historial_abonos_inicial = []
            if pedido_dict.get("historial_pagos"):
                for pago in pedido_dict.get("historial_pagos", []):
                    monto_pago = float(pago.get("monto", 0))
                    total_abonado_inicial += monto_pago
                    # Crear registro de abono inicial
                    abono_inicial = {
                        "fecha": pago.get("fecha") or datetime.utcnow().isoformat(),
                        "monto": monto_pago,
                        "metodo_pago_id": pago.get("metodo"),
                        "metodo_pago_nombre": pago.get("metodo"),  # Se puede mejorar buscando el nombre real
                        "numero_referencia": pago.get("numero_referencia"),
                        "comprobante": pago.get("comprobante")
                    }
                    historial_abonos_inicial.append(abono_inicial)
            
            saldo_pendiente_inicial = monto_total - total_abonado_inicial
            
            # Generar número de factura (puede ser auto-incremental o basado en fecha)
            # Por ahora usar un formato simple: FACT-YYYYMMDD-{pedido_id[-6:]}
            fecha_actual = datetime.utcnow()
            numero_factura = f"FACT-{fecha_actual.strftime('%Y%m%d')}-{pedido_id[-6:]}"
            
            # Crear documento de factura
            factura_dict = {
                "pedido_id": pedido_id,
                "numero_factura": numero_factura,
                "cliente_id": cliente_id,
                "cliente_nombre": cliente_nombre,
                "fecha_creacion": datetime.utcnow().isoformat(),
                "fecha_facturacion": pedido_dict.get("fecha_creacion"),
                "items": pedido_dict.get("items", []),
                "adicionales": pedido_dict.get("adicionales", []),  # Incluir adicionales en la factura
                "monto_total": monto_total,
                "monto_abonado": total_abonado_inicial,
                "saldo_pendiente": saldo_pendiente_inicial,
                "estado": "pendiente" if saldo_pendiente_inicial > 0.01 else "pagada",
                "historial_abonos": historial_abonos_inicial,
                "datos_completos": {
                    "pedido": pedido_dict
                }
            }
            
            # Insertar la factura
            factura_result = facturas_cliente_collection.insert_one(factura_dict)
            print(f"DEBUG CREAR PEDIDO CLIENTE: Factura creada automáticamente para pedido {pedido_id}")
            print(f"  - Numero factura: {numero_factura}")
            print(f"  - Monto total: {monto_total}")
            print(f"  - Saldo pendiente: {saldo_pendiente_inicial}")
            
        except Exception as e:
            print(f"ERROR CREAR PEDIDO CLIENTE - crear factura: {e}")
            import traceback
            print(f"TRACEBACK: {traceback.format_exc()}")
            # No interrumpimos el flujo, solo logueamos el error
        
        return {
            "message": "Pedido creado exitosamente",
            "pedido_id": pedido_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR CREAR PEDIDO CLIENTE: {str(e)}")
        import traceback
        print(f"ERROR CREAR PEDIDO CLIENTE TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al crear pedido: {str(e)}")

@router.get("/web/")
async def get_pedidos_web():
    """
    Endpoint específico para obtener todos los pedidos web.
    Optimizado para mejorar el rendimiento en el módulo pedidos-web.
    Solo retorna pedidos con tipo_pedido: "web" o tipo: "cliente".
    """
    try:
        # Proyección optimizada: solo campos necesarios para la lista de pedidos
        projection = {
            "_id": 1,
            "numero_orden": 1,
            "cliente_id": 1,
            "cliente_nombre": 1,
            "fecha_creacion": 1,
            "fecha_actualizacion": 1,
            "estado_general": 1,
            "items": 1,
            "adicionales": 1,
            "pago": 1,
            "historial_pagos": 1,
            "total_abonado": 1,
            "tipo": 1,
            "tipo_pedido": 1,
            "creado_por": 1
        }
        
        # Buscar solo pedidos web
        pedidos = list(pedidos_collection.find(
            {
                "$or": [
                    {"tipo_pedido": "web"},
                    {"tipo": "cliente"}  # Retrocompatibilidad con pedidos antiguos
                ]
            },
            projection
        ).sort("fecha_creacion", -1).limit(1000))  # Limitar a 1000 pedidos más recientes
        
        # Normalizar y convertir ObjectId a string
        for pedido in pedidos:
            pedido["_id"] = str(pedido["_id"])
            # Normalizar adicionales: None o no existe → []
            if "adicionales" not in pedido or pedido.get("adicionales") is None:
                pedido["adicionales"] = []
            # Enriquecer con datos del cliente (cédula y teléfono)
            enriquecer_pedido_con_datos_cliente(pedido)
        
        return {
            "pedidos": pedidos,
            "total": len(pedidos),
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR GET PEDIDOS WEB: {str(e)}")
        import traceback
        print(f"ERROR GET PEDIDOS WEB TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener pedidos web: {str(e)}")

@router.get("/cliente/{cliente_id}")
async def get_pedidos_cliente(cliente_id: str, cliente: dict = Depends(get_current_cliente)):
    """
    Obtener todos los pedidos de un cliente autenticado.
    Solo puede ver sus propios pedidos.
    Optimizado con proyección para mejorar rendimiento.
    """
    try:
        # Verificar que el cliente_id coincida con el cliente autenticado
        if cliente.get("id") != cliente_id:
            raise HTTPException(status_code=403, detail="No puedes ver pedidos de otros clientes")
        
        # Proyección optimizada: solo campos necesarios para la lista de pedidos
        projection = {
            "_id": 1,
            "numero_orden": 1,
            "cliente_id": 1,
            "cliente_nombre": 1,
            "fecha_creacion": 1,
            "fecha_actualizacion": 1,
            "estado_general": 1,
            "items": 1,
            "adicionales": 1,
            "pago": 1,
            "historial_pagos": 1,
            "total_abonado": 1,
            "tipo": 1,
            "tipo_pedido": 1,
            "creado_por": 1
            # Excluir campos pesados como seguimiento, datos_completos, etc.
        }
        
        # Buscar pedidos del cliente con tipo_pedido "web" o tipo "cliente" (retrocompatibilidad)
        pedidos = list(pedidos_collection.find(
            {
                "cliente_id": cliente_id,
                "$or": [
                    {"tipo_pedido": "web"},
                    {"tipo": "cliente"}  # Retrocompatibilidad con pedidos antiguos
                ]
            },
            projection
        ).sort("fecha_creacion", -1).limit(500))  # Limitar a 500 pedidos más recientes
        
        # Normalizar y convertir ObjectId a string
        for pedido in pedidos:
            pedido["_id"] = str(pedido["_id"])
            # Normalizar adicionales: None o no existe → []
            if "adicionales" not in pedido or pedido.get("adicionales") is None:
                pedido["adicionales"] = []
            # Enriquecer con datos del cliente (cédula y teléfono)
            enriquecer_pedido_con_datos_cliente(pedido)
        
        return pedidos
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"ERROR GET PEDIDOS CLIENTE: {str(e)}")
        import traceback
        print(f"ERROR GET PEDIDOS CLIENTE TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener pedidos: {str(e)}")

# ============================================================================
# PANEL DE CONTROL LOGÍSTICO
# ============================================================================

def registrar_movimiento_logistico(
    item_id: str,
    item_codigo: str,
    item_nombre: str,
    tipo_movimiento: str,  # "crear_pedido", "terminar_asignacion", "facturar", "cancelar"
    cantidad: float,
    pedido_id: Optional[str] = None,
    estado_anterior: Optional[str] = None,
    estado_nuevo: Optional[str] = None,
    empleado_id: Optional[str] = None
):
    """
    Registra un movimiento de unidades en el sistema logístico
    """
    try:
        movimiento = {
            "item_id": item_id,
            "item_codigo": item_codigo,
            "item_nombre": item_nombre,
            "tipo_movimiento": tipo_movimiento,
            "cantidad": cantidad,
            "fecha": datetime.now().isoformat(),
            "timestamp": datetime.now().timestamp(),
            "pedido_id": pedido_id,
            "estado_anterior": estado_anterior,
            "estado_nuevo": estado_nuevo,
            "empleado_id": empleado_id
        }
        movimientos_logisticos_collection.insert_one(movimiento)
    except Exception as e:
        print(f"ERROR REGISTRAR MOVIMIENTO: Error registrando movimiento: {e}")
        # No lanzar error, solo loggear para no interrumpir el flujo principal

@router.get("/panel-control-logistico/resumen/")
async def get_resumen_panel_control_logistico():
    """
    Resumen general del panel de control logístico con totales
    """
    try:
        # Items en producción (estado_item < 4)
        items_produccion = pedidos_collection.aggregate([
            {"$unwind": "$items"},
            {"$match": {"items.estado_item": {"$lt": 4}}},
            {"$group": {
                "_id": "$items.codigo",
                "cantidad": {"$sum": "$items.cantidad"},
                "item_nombre": {"$first": "$items.nombre"},
                "item_descripcion": {"$first": "$items.descripcion"}
            }}
        ])
        
        total_items_produccion = sum(item["cantidad"] for item in items_produccion)
        
        # Items vendidos (estado_item >= 4 en pedidos facturados o completados)
        items_vendidos = pedidos_collection.aggregate([
            {"$unwind": "$items"},
            {"$match": {
                "items.estado_item": {"$gte": 4},
                "estado_general": {"$in": ["orden4", "orden5", "orden6"]}
            }},
            {"$group": {
                "_id": "$items.codigo",
                "cantidad": {"$sum": "$items.cantidad"}
            }}
        ])
        
        total_items_vendidos = sum(item["cantidad"] for item in items_vendidos)
        
        # Items en inventario
        total_items_inventario = items_collection.count_documents({"activo": True})
        
        # Items con existencia en 0
        items_existencia_cero = items_collection.count_documents({
            "$or": [
                {"cantidad": 0},
                {"cantidad": {"$exists": False}},
                {"existencia": 0},
                {"existencia": {"$exists": False}}
            ],
            "activo": True
        })
        
        # Movimientos en últimos 7 días
        fecha_7_dias = (datetime.now() - timedelta(days=7)).isoformat()
        movimientos_7_dias = movimientos_logisticos_collection.count_documents({
            "fecha": {"$gte": fecha_7_dias}
        })
        
        return {
            "total_items_produccion": total_items_produccion,
            "total_items_vendidos": total_items_vendidos,
            "total_items_inventario": total_items_inventario,
            "items_existencia_cero": items_existencia_cero,
            "movimientos_7_dias": movimientos_7_dias,
            "fecha_actualizacion": datetime.now().isoformat()
        }
    except Exception as e:
        print(f"ERROR RESUMEN PANEL: {e}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener resumen: {str(e)}")

@router.get("/panel-control-logistico/items-produccion/")
async def get_items_produccion():
    """
    Items en producción con detalles
    """
    try:
        items_produccion = list(pedidos_collection.aggregate([
            {"$unwind": "$items"},
            {"$match": {"items.estado_item": {"$lt": 4}}},
            {"$group": {
                "_id": "$items.codigo",
                "item_id": {"$first": "$items.id"},
                "cantidad": {"$sum": "$items.cantidad"},
                "item_nombre": {"$first": "$items.nombre"},
                "item_descripcion": {"$first": "$items.descripcion"},
                "estado_item": {"$first": "$items.estado_item"},
                "pedidos": {"$push": {
                    "pedido_id": {"$toString": "$_id"},
                    "cantidad": "$items.cantidad",
                    "estado_general": "$estado_general"
                }}
            }},
            {"$sort": {"cantidad": -1}}
        ]))
        
        # Enriquecer con datos del inventario
        for item in items_produccion:
            codigo = item.get("_id")
            if codigo:
                item_inventario = items_collection.find_one({"codigo": codigo})
                if item_inventario:
                    item["existencia_inventario"] = item_inventario.get("cantidad", 0)
                    item["existencia_sucursal2"] = item_inventario.get("existencia2", 0)
                    item["precio"] = item_inventario.get("precio", 0)
                    item["costo"] = item_inventario.get("costo", 0)
                else:
                    item["existencia_inventario"] = 0
                    item["existencia_sucursal2"] = 0
        
        return items_produccion
    except Exception as e:
        print(f"ERROR ITEMS PRODUCCION: {e}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener items en producción: {str(e)}")

@router.get("/panel-control-logistico/movimientos-unidades/")
async def get_movimientos_unidades(
    item_id: Optional[str] = Query(None),
    item_codigo: Optional[str] = Query(None),
    fecha_inicio: Optional[str] = Query(None),
    fecha_fin: Optional[str] = Query(None)
):
    """
    Movimientos de unidades por item
    """
    try:
        query = {}
        
        if item_id:
            query["item_id"] = item_id
        if item_codigo:
            query["item_codigo"] = item_codigo
        if fecha_inicio:
            query["fecha"] = {"$gte": fecha_inicio}
        if fecha_fin:
            if "fecha" in query:
                query["fecha"]["$lte"] = fecha_fin
            else:
                query["fecha"] = {"$lte": fecha_fin}
        
        movimientos = list(movimientos_logisticos_collection.find(query).sort("fecha", -1).limit(1000))
        
        # Convertir ObjectId a string
        for movimiento in movimientos:
            movimiento["_id"] = str(movimiento["_id"])
        
        return {
            "movimientos": movimientos,
            "total": len(movimientos)
        }
    except Exception as e:
        print(f"ERROR MOVIMIENTOS: {e}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener movimientos: {str(e)}")

@router.get("/panel-control-logistico/items-sin-movimiento/")
async def get_items_sin_movimiento():
    """
    Items sin movimiento en los últimos 7 días
    """
    try:
        fecha_7_dias = (datetime.now() - timedelta(days=7)).isoformat()
        
        # Obtener items que han tenido movimientos en los últimos 7 días
        items_con_movimiento = movimientos_logisticos_collection.distinct("item_codigo", {
            "fecha": {"$gte": fecha_7_dias}
        })
        
        # Obtener todos los items activos
        todos_items = list(items_collection.find({"activo": True}, {"codigo": 1, "nombre": 1, "descripcion": 1, "cantidad": 1, "existencia": 1, "existencia2": 1}))
        
        # Filtrar items sin movimiento
        items_sin_movimiento = []
        for item in todos_items:
            codigo = item.get("codigo")
            if codigo and codigo not in items_con_movimiento:
                # Calcular existencia real (inventario - producción - vendidas)
                existencia = item.get("cantidad", 0) or item.get("existencia", 0)
                existencia2 = item.get("existencia2", 0)
                
                # Calcular en producción
                items_produccion = list(pedidos_collection.aggregate([
                    {"$unwind": "$items"},
                    {"$match": {
                        "items.codigo": codigo,
                        "items.estado_item": {"$lt": 4}
                    }},
                    {"$group": {
                        "_id": None,
                        "cantidad": {"$sum": "$items.cantidad"}
                    }}
                ]))
                cantidad_produccion = items_produccion[0]["cantidad"] if items_produccion else 0
                
                # Calcular vendidas
                items_vendidas = list(pedidos_collection.aggregate([
                    {"$unwind": "$items"},
                    {"$match": {
                        "items.codigo": codigo,
                        "items.estado_item": {"$gte": 4},
                        "estado_general": {"$in": ["orden4", "orden5", "orden6"]}
                    }},
                    {"$group": {
                        "_id": None,
                        "cantidad": {"$sum": "$items.cantidad"}
                    }}
                ]))
                cantidad_vendidas = items_vendidas[0]["cantidad"] if items_vendidas else 0
                
                existencia_real = existencia - cantidad_produccion - cantidad_vendidas
                
                items_sin_movimiento.append({
                    "item_id": str(item["_id"]),
                    "codigo": codigo,
                    "nombre": item.get("nombre", ""),
                    "descripcion": item.get("descripcion", ""),
                    "existencia": existencia,
                    "existencia2": existencia2,
                    "existencia_real": existencia_real,
                    "categoria": "sin_movimiento"
                })
        
        return {
            "items": items_sin_movimiento,
            "total": len(items_sin_movimiento)
        }
    except Exception as e:
        print(f"ERROR ITEMS SIN MOVIMIENTO: {e}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener items sin movimiento: {str(e)}")

@router.get("/panel-control-logistico/items-mas-movidos/")
async def get_items_mas_movidos():
    """
    Items más movidos en los últimos 7 días
    """
    try:
        fecha_7_dias = (datetime.now() - timedelta(days=7)).isoformat()
        
        # Agrupar movimientos por item
        items_movidos = list(movimientos_logisticos_collection.aggregate([
            {"$match": {"fecha": {"$gte": fecha_7_dias}}},
            {"$group": {
                "_id": "$item_codigo",
                "item_id": {"$first": "$item_id"},
                "item_nombre": {"$first": "$item_nombre"},
                "total_movimientos": {"$sum": 1},
                "cantidad_total": {"$sum": "$cantidad"},
                "tipos_movimiento": {"$push": "$tipo_movimiento"},
                "ultimo_movimiento": {"$max": "$fecha"}
            }},
            {"$sort": {"total_movimientos": -1}},
            {"$limit": 50}
        ]))
        
        # Enriquecer con datos del inventario
        for item in items_movidos:
            codigo = item.get("_id")
            if codigo:
                item_inventario = items_collection.find_one({"codigo": codigo})
                if item_inventario:
                    item["existencia_inventario"] = item_inventario.get("cantidad", 0)
                    item["precio"] = item_inventario.get("precio", 0)
        
        return {
            "items": items_movidos,
            "total": len(items_movidos)
        }
    except Exception as e:
        print(f"ERROR ITEMS MAS MOVIDOS: {e}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener items más movidos: {str(e)}")

@router.get("/panel-control-logistico/items-existencia-cero/")
async def get_items_existencia_cero():
    """
    Items con existencia en 0
    """
    try:
        items_cero = list(items_collection.find({
            "$or": [
                {"cantidad": 0},
                {"cantidad": {"$exists": False}},
                {"existencia": 0},
                {"existencia": {"$exists": False}}
            ],
            "activo": True
        }, {
            "codigo": 1,
            "nombre": 1,
            "descripcion": 1,
            "cantidad": 1,
            "existencia": 1,
            "existencia2": 1,
            "precio": 1,
            "costo": 1,
            "categoria": 1
        }))
        
        # Enriquecer con datos de producción y ventas
        for item in items_cero:
            codigo = item.get("codigo")
            if codigo:
                # Calcular en producción
                items_produccion = list(pedidos_collection.aggregate([
                    {"$unwind": "$items"},
                    {"$match": {
                        "items.codigo": codigo,
                        "items.estado_item": {"$lt": 4}
                    }},
                    {"$group": {
                        "_id": None,
                        "cantidad": {"$sum": "$items.cantidad"}
                    }}
                ]))
                item["en_produccion"] = items_produccion[0]["cantidad"] if items_produccion else 0
                
                # Calcular vendidas en últimos 30 días
                fecha_30_dias = (datetime.now() - timedelta(days=30)).isoformat()
                items_vendidas = list(pedidos_collection.aggregate([
                    {"$unwind": "$items"},
                    {"$match": {
                        "items.codigo": codigo,
                        "items.estado_item": {"$gte": 4},
                        "estado_general": {"$in": ["orden4", "orden5", "orden6"]},
                        "fecha_creacion": {"$gte": fecha_30_dias}
                    }},
                    {"$group": {
                        "_id": None,
                        "cantidad": {"$sum": "$items.cantidad"}
                    }}
                ]))
                item["vendidas_30_dias"] = items_vendidas[0]["cantidad"] if items_vendidas else 0
                
                item["_id"] = str(item["_id"])
        
        return {
            "items": items_cero,
            "total": len(items_cero)
        }
    except Exception as e:
        print(f"ERROR ITEMS EXISTENCIA CERO: {e}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener items con existencia cero: {str(e)}")

@router.get("/panel-control-logistico/sugerencia-produccion/")
async def get_sugerencia_produccion():
    """
    Sugerencias de producción con prioridades
    """
    try:
        sugerencias = []
        
        # Obtener items con existencia baja o en producción
        todos_items = list(items_collection.find({"activo": True}, {
            "codigo": 1,
            "nombre": 1,
            "descripcion": 1,
            "cantidad": 1,
            "existencia": 1,
            "existencia2": 1,
            "precio": 1,
            "costo": 1
        }))
        
        for item in todos_items:
            codigo = item.get("codigo")
            if not codigo:
                continue
            
            existencia = item.get("cantidad", 0) or item.get("existencia", 0)
            
            # Calcular en producción
            items_produccion = list(pedidos_collection.aggregate([
                {"$unwind": "$items"},
                {"$match": {
                    "items.codigo": codigo,
                    "items.estado_item": {"$lt": 4}
                }},
                {"$group": {
                    "_id": None,
                    "cantidad": {"$sum": "$items.cantidad"}
                }}
            ]))
            cantidad_produccion = items_produccion[0]["cantidad"] if items_produccion else 0
            
            # Calcular vendidas en últimos 30 días
            fecha_30_dias = (datetime.now() - timedelta(days=30)).isoformat()
            items_vendidas = list(pedidos_collection.aggregate([
                {"$unwind": "$items"},
                {"$match": {
                    "items.codigo": codigo,
                    "items.estado_item": {"$gte": 4},
                    "estado_general": {"$in": ["orden4", "orden5", "orden6"]},
                    "fecha_creacion": {"$gte": fecha_30_dias}
                }},
                {"$group": {
                    "_id": None,
                    "cantidad": {"$sum": "$items.cantidad"}
                }}
            ]))
            cantidad_vendidas_30_dias = items_vendidas[0]["cantidad"] if items_vendidas else 0
            
            # Calcular existencia real
            existencia_real = existencia - cantidad_produccion
            
            # Calcular prioridad
            prioridad = 0
            if existencia_real <= 0:
                prioridad = 3  # Alta
            elif existencia_real <= 5:
                prioridad = 2  # Media
            elif cantidad_vendidas_30_dias > 0:
                prioridad = 1  # Baja
            
            # Solo agregar si tiene prioridad o está en producción
            if prioridad > 0 or cantidad_produccion > 0:
                sugerencias.append({
                    "item_id": str(item["_id"]),
                    "codigo": codigo,
                    "nombre": item.get("nombre", ""),
                    "descripcion": item.get("descripcion", ""),
                    "existencia_actual": existencia,
                    "existencia_real": existencia_real,
                    "en_produccion": cantidad_produccion,
                    "vendidas_30_dias": cantidad_vendidas_30_dias,
                    "prioridad": prioridad,
                    "cantidad_sugerida": max(cantidad_vendidas_30_dias - existencia_real, 0) if existencia_real < cantidad_vendidas_30_dias else 0
                })
        
        # Ordenar por prioridad
        sugerencias.sort(key=lambda x: (x["prioridad"], x["vendidas_30_dias"]), reverse=True)
        
        return {
            "sugerencias": sugerencias,
            "total": len(sugerencias)
        }
    except Exception as e:
        print(f"ERROR SUGERENCIA PRODUCCION: {e}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener sugerencias: {str(e)}")

@router.get("/panel-control-logistico/graficas/")
async def get_graficas_panel_control(
    periodo: Optional[str] = Query("7", description="Período en días: 7, 30, 90")
):
    """
    Datos para gráficas y comparaciones
    """
    try:
        periodo_int = int(periodo)
        fecha_inicio = (datetime.now() - timedelta(days=periodo_int)).isoformat()
        fecha_fin = datetime.now().isoformat()
        
        # Movimientos por día
        movimientos_por_dia = list(movimientos_logisticos_collection.aggregate([
            {"$match": {"fecha": {"$gte": fecha_inicio, "$lte": fecha_fin}}},
            {"$group": {
                "_id": {"$substr": ["$fecha", 0, 10]},  # Extraer fecha (YYYY-MM-DD)
                "total_movimientos": {"$sum": 1},
                "cantidad_total": {"$sum": "$cantidad"}
            }},
            {"$sort": {"_id": 1}}
        ]))
        
        # Items más movidos
        items_movidos = list(movimientos_logisticos_collection.aggregate([
            {"$match": {"fecha": {"$gte": fecha_inicio, "$lte": fecha_fin}}},
            {"$group": {
                "_id": "$item_codigo",
                "item_nombre": {"$first": "$item_nombre"},
                "total_movimientos": {"$sum": 1},
                "cantidad_total": {"$sum": "$cantidad"}
            }},
            {"$sort": {"total_movimientos": -1}},
            {"$limit": 10}
        ]))
        
        # Movimientos por tipo
        movimientos_por_tipo = list(movimientos_logisticos_collection.aggregate([
            {"$match": {"fecha": {"$gte": fecha_inicio, "$lte": fecha_fin}}},
            {"$group": {
                "_id": "$tipo_movimiento",
                "total": {"$sum": 1},
                "cantidad_total": {"$sum": "$cantidad"}
            }}
        ]))
        
        # Comparar con período anterior
        fecha_inicio_anterior = (datetime.now() - timedelta(days=periodo_int * 2)).isoformat()
        fecha_fin_anterior = fecha_inicio
        
        movimientos_anterior = movimientos_logisticos_collection.count_documents({
            "fecha": {"$gte": fecha_inicio_anterior, "$lte": fecha_fin_anterior}
        })
        
        movimientos_actual = movimientos_logisticos_collection.count_documents({
            "fecha": {"$gte": fecha_inicio, "$lte": fecha_fin}
        })
        
        variacion = ((movimientos_actual - movimientos_anterior) / movimientos_anterior * 100) if movimientos_anterior > 0 else 0
        
        return {
            "periodo": periodo_int,
            "fecha_inicio": fecha_inicio,
            "fecha_fin": fecha_fin,
            "movimientos_por_dia": movimientos_por_dia,
            "items_mas_movidos": items_movidos,
            "movimientos_por_tipo": movimientos_por_tipo,
            "comparacion_periodo_anterior": {
                "movimientos_actual": movimientos_actual,
                "movimientos_anterior": movimientos_anterior,
                "variacion_porcentual": round(variacion, 2)
            }
        }
    except Exception as e:
        print(f"ERROR GRAFICAS: {e}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener datos para gráficas: {str(e)}")

@router.get("/panel-control-logistico/planificacion-produccion/")
async def get_planificacion_produccion():
    """
    Planificación completa de producción
    """
    try:
        planificacion = {
            "items_urgentes": [],
            "items_en_produccion": [],
            "items_sugeridos": [],
            "resumen": {}
        }
        
        # Items urgentes (existencia <= 0)
        items_urgentes = list(items_collection.find({
            "$or": [
                {"cantidad": {"$lte": 0}},
                {"existencia": {"$lte": 0}}
            ],
            "activo": True
        }, {
            "codigo": 1,
            "nombre": 1,
            "descripcion": 1,
            "cantidad": 1,
            "existencia": 1,
            "precio": 1,
            "costo": 1
        }))
        
        for item in items_urgentes:
            codigo = item.get("codigo")
            if codigo:
                # Calcular en producción
                items_produccion = list(pedidos_collection.aggregate([
                    {"$unwind": "$items"},
                    {"$match": {
                        "items.codigo": codigo,
                        "items.estado_item": {"$lt": 4}
                    }},
                    {"$group": {
                        "_id": None,
                        "cantidad": {"$sum": "$items.cantidad"}
                    }}
                ]))
                cantidad_produccion = items_produccion[0]["cantidad"] if items_produccion else 0
                
                planificacion["items_urgentes"].append({
                    "item_id": str(item["_id"]),
                    "codigo": codigo,
                    "nombre": item.get("nombre", ""),
                    "descripcion": item.get("descripcion", ""),
                    "existencia_actual": item.get("cantidad", 0) or item.get("existencia", 0),
                    "en_produccion": cantidad_produccion,
                    "prioridad": "alta"
                })
        
        # Items en producción (del endpoint anterior)
        items_produccion_data = await get_items_produccion()
        planificacion["items_en_produccion"] = items_produccion_data[:20]  # Limitar a 20
        
        # Items sugeridos (del endpoint anterior)
        sugerencias_data = await get_sugerencia_produccion()
        planificacion["items_sugeridos"] = sugerencias_data["sugerencias"][:20]  # Limitar a 20
        
        # Resumen
        planificacion["resumen"] = {
            "items_urgentes": len(planificacion["items_urgentes"]),
            "items_en_produccion": len(planificacion["items_en_produccion"]),
            "items_sugeridos": len(planificacion["items_sugeridos"]),
            "fecha_actualizacion": datetime.now().isoformat()
        }
        
        return planificacion
    except Exception as e:
        print(f"ERROR PLANIFICACION: {e}")
        import traceback
        print(f"TRACEBACK: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al obtener planificación: {str(e)}")
