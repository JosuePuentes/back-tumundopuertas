from fastapi import APIRouter, HTTPException, UploadFile, File, status, Query, Body
from ..config.mongodb import items_collection, pedidos_collection
from ..models.authmodels import Item, InventarioExcelItem
from bson import ObjectId
from pydantic import BaseModel
from typing import List, Literal # Keep this import as it's used in the /bulk endpoint
import openpyxl
import io

router = APIRouter()

class ActualizarExistenciaRequest(BaseModel):
    cantidad: float
    tipo: Literal['cargar', 'descargar']

@router.post("/cargar-existencias-desde-pedido")
async def cargar_existencias_desde_pedido(pedido_id: str = Body(..., embed=True)):
    """Carga existencias al inventario a partir de un pedido específico.
    
    Request Body:
    {
        "pedido_id": "69042b91a9a8ebdaf861c3f0"
    }
    
    Para cada item del pedido:
    - Si existe en inventario: incrementa existencia con item.cantidad del pedido
    - Si no existe: crea un nuevo item en el inventario con existencia igual a cantidad del pedido
    """
    try:
        # Obtener el pedido
        pedido_obj_id = ObjectId(pedido_id)
        pedido = pedidos_collection.find_one({"_id": pedido_obj_id})
        
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido no encontrado")
        
        items_actualizados = 0
        items_creados = 0
        
        print(f"DEBUG CARGAR EXISTENCIAS: Procesando pedido {pedido_id}")
        
        # Para cada item del pedido
        for idx, item_pedido in enumerate(pedido.get("items", [])):
            codigo_item_raw = item_pedido.get("codigo") or item_pedido.get("id") or item_pedido.get("_id")
            if not codigo_item_raw:
                print(f"DEBUG CARGAR EXISTENCIAS: Item {idx} sin código, saltando")
                continue
            
            # Normalizar código: trim y convertir a string
            codigo_item = str(codigo_item_raw).strip()
            cantidad = int(item_pedido.get("cantidad", 0))
            
            print(f"DEBUG CARGAR EXISTENCIAS: Item {idx} - código: '{codigo_item}', cantidad: {cantidad}")
            
            if cantidad <= 0:
                print(f"DEBUG CARGAR EXISTENCIAS: Item {idx} con cantidad <= 0, saltando")
                continue
            
            # Buscar item en inventario con código normalizado
            # Intentar búsqueda exacta primero
            item_inventario = items_collection.find_one({"codigo": codigo_item})
            
            # Si no se encuentra, intentar búsqueda sin distinguir mayúsculas/minúsculas
            if not item_inventario:
                item_inventario = items_collection.find_one({
                    "codigo": {"$regex": f"^{codigo_item}$", "$options": "i"}
                })
            
            if item_inventario:
                # Verificar si el campo existencia existe y es numérico
                existencia_actual = item_inventario.get("existencia")
                if existencia_actual is None:
                    print(f"DEBUG CARGAR EXISTENCIAS: Item '{codigo_item}' no tiene campo 'existencia', creándolo con valor {cantidad}")
                    items_collection.update_one(
                        {"codigo": codigo_item},
                        {"$set": {"existencia": cantidad}}
                    )
                else:
                    # Verificar que sea numérico
                    if not isinstance(existencia_actual, (int, float)):
                        print(f"WARNING CARGAR EXISTENCIAS: Item '{codigo_item}' tiene existencia no numérica: {existencia_actual}, convirtiendo a número")
                        try:
                            existencia_actual = float(existencia_actual)
                            items_collection.update_one(
                                {"codigo": codigo_item},
                                {"$set": {"existencia": existencia_actual}}
                            )
                        except (ValueError, TypeError):
                            print(f"ERROR CARGAR EXISTENCIAS: No se pudo convertir existencia a número para item '{codigo_item}', usando 0")
                            existencia_actual = 0
                    
                    # Incrementar existencia
                    print(f"DEBUG CARGAR EXISTENCIAS: Incrementando existencia de '{codigo_item}' de {existencia_actual} a {existencia_actual + cantidad}")
                    result = items_collection.update_one(
                        {"codigo": codigo_item},
                        {"$inc": {"existencia": cantidad}}
                    )
                    print(f"DEBUG CARGAR EXISTENCIAS: Resultado update_one - matched: {result.matched_count}, modified: {result.modified_count}")
                
                items_actualizados += 1
            else:
                # Crear nuevo item en inventario
                print(f"DEBUG CARGAR EXISTENCIAS: Item '{codigo_item}' no existe en inventario, creándolo nuevo")
                nuevo_item = {
                    "codigo": codigo_item,
                    "nombre": item_pedido.get("nombre", item_pedido.get("descripcion", "")),
                    "descripcion": item_pedido.get("descripcion", ""),
                    "existencia": cantidad,
                    "precio": item_pedido.get("precio", 0),
                    "costo": item_pedido.get("costo", 0),
                    "costoProduccion": item_pedido.get("costoProduccion", 0),
                    "activo": True,
                    "cantidad": 0,
                    "imagenes": item_pedido.get("imagenes", [])
                }
                result = items_collection.insert_one(nuevo_item)
                print(f"DEBUG CARGAR EXISTENCIAS: Item '{codigo_item}' creado con _id: {result.inserted_id}")
                items_creados += 1
        
        print(f"DEBUG CARGAR EXISTENCIAS: Proceso completado - Actualizados: {items_actualizados}, Creados: {items_creados}")
        
        return {
            "message": "Existencias cargadas al inventario correctamente",
            "items_actualizados": items_actualizados,
            "items_creados": items_creados
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al cargar existencias: {str(e)}")

@router.get("/all")
async def get_all_items():
    items = list(items_collection.find())
    for item in items:
        item["_id"] = str(item["_id"])
    return items

@router.get("/id/{item_id}/")
async def get_item(item_id: str):
    try:
        item_obj_id = ObjectId(item_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"item_id no es un ObjectId válido: {str(e)}")

    item = items_collection.find_one({"_id": item_obj_id})
    if not item:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    item["_id"] = str(item["_id"])
    return item

@router.post("/")
async def create_item(item: Item):
    existing_item = items_collection.find_one({"codigo": item.codigo})
    if existing_item:
        raise HTTPException(status_code=400, detail="El item con este código ya existe")
    result = items_collection.insert_one(item.dict(by_alias=True, exclude_unset=True))
    return {"message": "Item creado correctamente", "id": str(result.inserted_id)}

@router.put("/id/{item_id}/")
async def update_item(item_id: str, item: Item):
    try:
        # Validar ObjectId
        try:
            item_obj_id = ObjectId(item_id)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"item_id no es un ObjectId válido: {str(e)}")

        # Preparar datos para actualización
        update_data = item.dict(exclude_unset=True, by_alias=True, exclude={"_id", "id"})
        
        # Verificar que hay datos para actualizar
        if not update_data:
            raise HTTPException(status_code=400, detail="No hay datos para actualizar")

        # Realizar la actualización
        result = items_collection.update_one(
            {"_id": item_obj_id},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Item no encontrado")
            
        return {"message": "Item actualizado correctamente", "id": item_id}
        
    except HTTPException:
        # Re-lanzar HTTPExceptions (errores conocidos)
        raise
    except Exception as e:
        # Capturar cualquier otro error inesperado
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.post("/preview-excel")
async def preview_inventory_excel(file: UploadFile = File(...)):
    """Endpoint para previsualizar el contenido del Excel antes de cargarlo"""
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Formato de archivo no válido. Se espera un archivo Excel (.xlsx o .xls)")

    try:
        contents = await file.read()
        workbook = openpyxl.load_workbook(io.BytesIO(contents))
        sheet = workbook.active

        # Asumiendo que la primera fila son los encabezados
        headers = [cell.value for cell in sheet[1]]
        expected_headers = ["codigo", "descripcion", "departamento", "marca", "precio", "costo", "existencia"]

        # Validar que los encabezados esperados estén presentes
        if not all(header in headers for header in expected_headers):
            raise HTTPException(status_code=400, detail=f"Faltan encabezados en el archivo Excel. Se esperan: {', '.join(expected_headers)}")

        preview_data = []
        for row_index in range(2, sheet.max_row + 1):
            row_data = {headers[i]: cell.value for i, cell in enumerate(sheet[row_index])}
            
            # Solo incluir datos si hay información en la fila
            if any(value is not None for value in row_data.values()):
                preview_data.append(row_data)

        return {
            "total_rows": len(preview_data),
            "headers": headers,
            "data": preview_data
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar el archivo Excel: {str(e)}")

@router.post("/upload-excel", status_code=status.HTTP_201_CREATED)
async def upload_inventory_excel(file: UploadFile = File(...)):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Formato de archivo no válido. Se espera un archivo Excel (.xlsx o .xls)")

    try:
        contents = await file.read()
        workbook = openpyxl.load_workbook(io.BytesIO(contents))
        sheet = workbook.active

        # Asumiendo que la primera fila son los encabezados
        headers = [cell.value for cell in sheet[1]]
        expected_headers = ["codigo", "descripcion", "departamento", "marca", "precio", "costo", "existencia"]

        # Validar que los encabezados esperados estén presentes
        if not all(header in headers for header in expected_headers):
            raise HTTPException(status_code=400, detail=f"Faltan encabezados en el archivo Excel. Se esperan: {', '.join(expected_headers)}")

        items_to_insert = []
        for row_index in range(2, sheet.max_row + 1):
            row_data = {headers[i]: cell.value for i, cell in enumerate(sheet[row_index])}
            
            # Validate with InventarioExcelItem model
            try:
                excel_item = InventarioExcelItem(**row_data)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Error de validación en la fila {row_index}: {e}")

            # Map to the main Item model
            item_data = Item(
                codigo=excel_item.codigo,
                nombre=excel_item.descripcion, # Defaulting nombre to descripcion
                descripcion=excel_item.descripcion,
                departamento=excel_item.departamento,
                marca=excel_item.marca,
                categoria="General", # Defaulting categoria
                precio=excel_item.precio,
                costo=excel_item.costo,
                # costoProduccion will use its default value from the Item model
                cantidad=0, # Defaulting quantity, as it's not in Excel input
                existencia=excel_item.existencia,
                activo=True,
                imagenes=[]
            )
            items_to_insert.append(item_data.dict(by_alias=True, exclude_unset=True))

        if not items_to_insert:
            raise HTTPException(status_code=400, detail="No se encontraron datos válidos para insertar en el archivo Excel.")

        # Insert or update items
        inserted_count = 0
        updated_count = 0
        for item_data in items_to_insert:
            # Check if item with this 'codigo' already exists
            existing_item = items_collection.find_one({"codigo": item_data["codigo"]})
            if existing_item:
                items_collection.update_one(
                    {"_id": existing_item["_id"]},
                    {"$set": item_data}
                )
                updated_count += 1
            else:
                items_collection.insert_one(item_data)
                inserted_count += 1

        return {"message": f"Inventario procesado correctamente. Insertados: {inserted_count}, Actualizados: {updated_count}"}

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar el archivo Excel: {str(e)}")

@router.get("/search", response_model=List[Item])
async def search_items(
    query: str = Query(..., min_length=1, description="Texto de búsqueda para código, descripción, nombre, departamento o marca"),
    limit: int = Query(10, gt=0, description="Número máximo de resultados a devolver"),
    skip: int = Query(0, ge=0, description="Número de resultados a omitir para paginación")
):
    search_filter = {
        "$or": [
            {"codigo": {"$regex": query, "$options": "i"}},
            {"descripcion": {"$regex": query, "$options": "i"}},
            {"nombre": {"$regex": query, "$options": "i"}},
            {"departamento": {"$regex": query, "$options": "i"}},
            {"marca": {"$regex": query, "$options": "i"}}
        ]
    }
    
    items = list(items_collection.find(search_filter).skip(skip).limit(limit))
    for item in items:
        item["_id"] = str(item["_id"])
    return items

@router.post("/bulk")
async def bulk_upsert_items(items: List[Item]):
    inserted_count = 0
    updated_count = 0
    skipped_items = []
    errors = []

    for item_data in items:
        item_dict = item_data.dict(by_alias=True)
        
        # Ensure _id is not set for new items, let MongoDB generate it
        if "_id" in item_dict:
            del item_dict["_id"]

        # Check if item with same codigo already exists
        existing_item = items_collection.find_one({"codigo": item_data.codigo})

        if existing_item:
            # Update existing item
            try:
                update_fields = {
                    "descripcion": item_dict.get("descripcion"),
                    "modelo": item_dict.get("modelo"),
                    "precio": item_dict.get("precio"),
                    "costo": item_dict.get("costo"),
                    "nombre": item_dict.get("nombre"),
                    "categoria": item_dict.get("categoria"),
                    "costoProduccion": item_dict.get("costoProduccion"),
                    "activo": item_dict.get("activo"),
                    "imagenes": item_dict.get("imagenes"),
                }
                # Remove None values to avoid setting them in MongoDB
                update_fields = {k: v for k, v in update_fields.items() if v is not None}

                update_operation = {"$set": update_fields}

                # Set cantidad if provided
                if "cantidad" in item_dict:
                    update_operation["$set"]["cantidad"] = item_dict["cantidad"]

                items_collection.update_one(
                    {"_id": existing_item["_id"]},
                    update_operation
                )
                updated_count += 1
            except Exception as e:
                errors.append({"item": item_data.dict(by_alias=True), "error": str(e), "action": "update"})
        else:
            # Insert new item
            try:
                items_collection.insert_one(item_dict)
                inserted_count += 1
            except Exception as e:
                errors.append({"item": item_data.dict(by_alias=True), "error": str(e), "action": "insert"})

    return {
        "message": f"Procesamiento de carga masiva completado. {inserted_count} items insertados, {updated_count} items actualizados, {len(errors)} con errores.",
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "errors": errors
    }

@router.post("/{item_id}/existencia")
async def actualizar_existencia(item_id: str, request: ActualizarExistenciaRequest):
    """
    Cargar o descargar existencia de un item
    Body esperado:
    {
        "cantidad": 10.0,
        "tipo": "cargar" o "descargar"
    }
    """
    try:
        # Validar ObjectId
        try:
            item_obj_id = ObjectId(item_id)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"item_id no es un ObjectId válido: {str(e)}")
        
        # Buscar el item
        item = items_collection.find_one({"_id": item_obj_id})
        if not item:
            raise HTTPException(status_code=404, detail="Item no encontrado")
        
        cantidad_actual = item.get("cantidad", 0.0)
        
        # Calcular nueva cantidad
        if request.tipo == "cargar":
            nueva_cantidad = cantidad_actual + request.cantidad
        elif request.tipo == "descargar":
            nueva_cantidad = cantidad_actual - request.cantidad
            # Validar que no sea negativa
            if nueva_cantidad < 0:
                raise HTTPException(
                    status_code=400, 
                    detail=f"No se puede descargar más de lo disponible. Existencia actual: {cantidad_actual}"
                )
        else:
            raise HTTPException(status_code=400, detail="Tipo debe ser 'cargar' o 'descargar'")
        
        # Actualizar la cantidad
        result = items_collection.update_one(
            {"_id": item_obj_id},
            {"$set": {"cantidad": nueva_cantidad}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Item no encontrado")
        
        # Obtener el item actualizado
        item_actualizado = items_collection.find_one({"_id": item_obj_id})
        
        return {
            "message": f"Existencia {request.tipo}da exitosamente",
            "cantidad": item_actualizado.get("cantidad", nueva_cantidad),
            "cantidad_anterior": cantidad_actual,
            "cantidad_operacion": request.cantidad,
            "tipo": request.tipo
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")
