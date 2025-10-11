from fastapi import APIRouter, HTTPException, Depends, Body
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
from ..auth.auth import get_current_user
from ..database import get_database
from ..models.authmodels import Empleado

router = APIRouter()

# Obtener la base de datos
def get_collections():
    db = get_database()
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

@router.get("/asignaciones")
async def get_dashboard_asignaciones(current_user = Depends(get_current_user)):
    """Obtener todas las asignaciones para el dashboard"""
    try:
        collections = get_collections()
        
        # Obtener todas las asignaciones activas
        asignaciones = list(collections["asignaciones"].find({
            "estado": {"$in": ["en_proceso", "pendiente"]}
        }).sort("fecha_asignacion", -1))
        
        # Convertir ObjectId a string para JSON
        for asignacion in asignaciones:
            asignacion["_id"] = str(asignacion["_id"])
            if "pedido_id" in asignacion:
                asignacion["pedido_id"] = str(asignacion["pedido_id"])
            if "item_id" in asignacion:
                asignacion["item_id"] = str(asignacion["item_id"])
        
        print(f"DEBUG DASHBOARD: Encontradas {len(asignaciones)} asignaciones")
        
        return {
            "asignaciones": asignaciones,
            "total": len(asignaciones),
            "success": True
        }
        
    except Exception as e:
        print(f"ERROR DASHBOARD: Error al obtener asignaciones: {e}")
        raise HTTPException(status_code=500, detail="Error al obtener asignaciones")

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
