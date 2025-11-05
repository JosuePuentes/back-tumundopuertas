# Instrucciones Completas para Backend - Cambios Consolidados

Este documento contiene las instrucciones para implementar **3 cambios importantes** en el backend.

---

## 📋 Cambio 1: Limpiar Pagos al Cancelar Pedido

### Descripción
Al cancelar un pedido, se deben limpiar automáticamente todos los pagos asociados (estado de pago, total abonado e historial de pagos).

### Ubicación
**Archivo:** `api/src/routes/pedidos.py`  
**Endpoint:** `PUT /pedidos/cancelar/{pedido_id}`  
**Línea aproximada:** ~4233

### Código a Modificar

**ANTES:**
```python
# Actualizar el estado_general del pedido
result = pedidos_collection.update_one(
    {"_id": pedido_obj_id},
    {
        "$set": {
            "estado_general": "cancelado",
            "fecha_cancelacion": fecha_cancelacion,
            "motivo_cancelacion": request.motivo_cancelacion,
            "cancelado_por": usuario_cancelacion,
            "fecha_actualizacion": fecha_cancelacion
        }
    }
)
```

**DESPUÉS:**
```python
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
```

### Pasos de Implementación

1. Abrir el archivo `api/src/routes/pedidos.py`
2. Buscar la función `cancelar_pedido` (línea ~4171)
3. Buscar el bloque `update_one` que actualiza el estado del pedido (línea ~4233)
4. Agregar las 3 líneas dentro del `$set`:
   - `"pago": "sin pago",`
   - `"total_abonado": 0,`
   - `"historial_pagos": []`
5. Actualizar el comentario de `# Actualizar el estado_general del pedido` a `# Actualizar el estado_general del pedido y limpiar pagos`

### Verificación

Después de implementar:
1. Crear un pedido de prueba
2. Agregar un pago al pedido
3. Cancelar el pedido
4. Verificar en la base de datos que:
   - `pago` = "sin pago"
   - `total_abonado` = 0
   - `historial_pagos` = []

---

## 📋 Cambio 2: Filtrar Todos los Pedidos Cancelados

### Descripción
Excluir **todos los pedidos cancelados** (de cualquier cliente) de los endpoints `/pedidos/mis-pagos` y `/pedidos/all/`.

### ⚠️ Aclaración Importante
Este filtro aplica a **todos los pedidos cancelados** de cualquier cliente, no solo a los de TU MUNDO PUERTA. Esto excluye pedidos con `estado_general = "cancelado"`.

### Ubicación
**Archivo:** `api/src/routes/pedidos.py`

#### 2.1 Modificar Endpoint `/pedidos/all/`

**Ubicación:** Línea ~150

**ANTES:**
```python
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
    
    pedidos = list(pedidos_collection.find(query))
```

**DESPUÉS:**
```python
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
```

#### 2.2 Modificar Endpoint `/pedidos/mis-pagos`

**Ubicación:** Línea ~4704

**ANTES:**
```python
    # Excluir pedidos web
    filtro = excluir_pedidos_web(filtro)
    # Excluir pedidos de TU MUNDO PUERTA (RIF: J-507172554)
    filtro = excluir_pedidos_tu_mundo_puerta(filtro)

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
```

**DESPUÉS:**
```python
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
```

### Pasos de Implementación

1. **Modificar endpoint `/all/`:**
   - Buscar `@router.get("/all/")` (línea ~150)
   - Después de `query = excluir_pedidos_tu_mundo_puerta(query)`, agregar:
     ```python
     # Excluir todos los pedidos cancelados
     query["estado_general"] = {"$ne": "cancelado"}
     ```

2. **Modificar endpoint `/mis-pagos`:**
   - Buscar `@router.get("/mis-pagos")` (línea ~4704)
   - Después de `filtro = excluir_pedidos_tu_mundo_puerta(filtro)`, agregar:
     ```python
     # Excluir todos los pedidos cancelados
     filtro["estado_general"] = {"$ne": "cancelado"}
     ```

### Verificación

Después de implementar:
1. Crear un pedido de cualquier cliente
2. Cancelar el pedido (estado_general = "cancelado")
3. Llamar a `GET /pedidos/all/` → Verificar que NO aparece el pedido cancelado
4. Llamar a `GET /pedidos/mis-pagos` → Verificar que NO aparece el pedido cancelado
5. Verificar que pedidos NO cancelados SÍ aparecen normalmente
6. Verificar que en MonitorPedidos, cuando se activa el filtro de cancelados, SÍ aparecen

---

## 📋 Cambio 3: Filtrar Pedidos de TU MUNDO PUERTA

### Descripción
Excluir pedidos del cliente TU MUNDO PUERTA (RIF: J-507172554) de los endpoints `/pedidos/mis-pagos` y `/pedidos/all/`.

### Ubicación
**Archivo:** `api/src/routes/pedidos.py`

#### 3.1 Función Auxiliar

**Ubicación:** Después de la función `excluir_pedidos_web()` (línea ~59)

**Código a Agregar:**
```python
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
```

#### 3.2 Modificar Endpoint `/pedidos/all/`

**Ubicación:** Línea ~150

**ANTES:**
```python
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
    
    pedidos = list(pedidos_collection.find(query))
```

**DESPUÉS:**
```python
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
```

#### 3.3 Modificar Endpoint `/pedidos/mis-pagos`

**Ubicación:** Línea ~4704

**ANTES:**
```python
    # Excluir pedidos web
    filtro = excluir_pedidos_web(filtro)

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
```

**DESPUÉS:**
```python
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
```

### Pasos de Implementación

1. **Agregar función auxiliar:**
   - Abrir `api/src/routes/pedidos.py`
   - Buscar la función `excluir_pedidos_web()` (línea ~33)
   - Agregar la función `excluir_pedidos_tu_mundo_puerta()` justo después (después de la línea ~59)

2. **Modificar endpoint `/all/`:** (Ya debe tener el filtro de cancelados)
   - Buscar `@router.get("/all/")` (línea ~150)
   - Después de `query = excluir_pedidos_web(query)`, agregar:
     ```python
     query = excluir_pedidos_tu_mundo_puerta(query)
     ```

3. **Modificar endpoint `/mis-pagos`:** (Ya debe tener el filtro de cancelados)
   - Buscar `@router.get("/mis-pagos")` (línea ~4704)
   - Después de `filtro = excluir_pedidos_web(filtro)`, agregar:
     ```python
     filtro = excluir_pedidos_tu_mundo_puerta(filtro)
     ```

### Verificación

Después de implementar:
1. Crear un pedido con cliente TU MUNDO PUERTA (RIF: J-507172554)
2. Llamar a `GET /pedidos/all/` → Verificar que NO aparece el pedido
3. Llamar a `GET /pedidos/mis-pagos` → Verificar que NO aparece el pedido
4. Verificar que otros pedidos SÍ aparecen normalmente

---

## 📊 Resumen de los 3 Cambios

### Cambio 1: Limpiar Pagos al Cancelar
- **Efecto:** Cuando se cancela un pedido, limpia automáticamente los pagos
- **Aplica a:** Endpoint `/pedidos/cancelar/{pedido_id}`
- **Resultado:** Los pagos se limpian al cancelar

### Cambio 2: Filtrar Todos los Pedidos Cancelados
- **Efecto:** Excluye **todos los pedidos cancelados** (de cualquier cliente) de Mis Pagos y Pagos
- **Aplica a:** Endpoints `/pedidos/all/` y `/pedidos/mis-pagos`
- **Resultado:** Ningún pedido cancelado aparece en Mis Pagos ni en Pagos

### Cambio 3: Filtrar TU MUNDO PUERTA
- **Efecto:** Excluye solo los pedidos del cliente TU MUNDO PUERTA (aunque no estén cancelados)
- **Aplica a:** Endpoints `/pedidos/all/` y `/pedidos/mis-pagos`
- **Resultado:** Los pedidos de TU MUNDO PUERTA no aparecen en Mis Pagos ni en Pagos

---

## ✅ Resultado Final Esperado

1. **Todos los pedidos cancelados** (de cualquier cliente) **NO aparecen** en Mis Pagos ni en Pagos
2. **Los pedidos de TU MUNDO PUERTA** (aunque no estén cancelados) **NO aparecen** en Mis Pagos ni en Pagos
3. **Todos los pedidos cancelados SÍ aparecen** en MonitorPedidos cuando se activa el filtro de cancelados
4. **Otros pedidos** (no cancelados y no de TU MUNDO PUERTA) **SÍ aparecen** normalmente

---

## ✅ Checklist Completo

### Cambio 1: Limpiar Pagos al Cancelar
- [ ] Abrir archivo `api/src/routes/pedidos.py`
- [ ] Buscar función `cancelar_pedido` (línea ~4171)
- [ ] Encontrar el bloque `update_one` que actualiza el estado (línea ~4233)
- [ ] Agregar `"pago": "sin pago",` al `$set`
- [ ] Agregar `"total_abonado": 0,` al `$set`
- [ ] Agregar `"historial_pagos": []` al `$set`
- [ ] Actualizar comentario del bloque
- [ ] Probar cancelar un pedido con pagos
- [ ] Verificar que los pagos se limpiaron

### Cambio 2: Filtrar Todos los Pedidos Cancelados
- [ ] Modificar endpoint `/all/` para agregar `query["estado_general"] = {"$ne": "cancelado"}`
- [ ] Modificar endpoint `/mis-pagos` para agregar `filtro["estado_general"] = {"$ne": "cancelado"}`
- [ ] Probar que pedidos cancelados no aparecen en `/all/`
- [ ] Probar que pedidos cancelados no aparecen en `/mis-pagos`
- [ ] Verificar que pedidos NO cancelados siguen apareciendo normalmente

### Cambio 3: Filtrar TU MUNDO PUERTA
- [ ] Agregar función `excluir_pedidos_tu_mundo_puerta()` después de `excluir_pedidos_web()`
- [ ] Modificar endpoint `/all/` para usar la nueva función
- [ ] Modificar endpoint `/mis-pagos` para usar la nueva función
- [ ] Probar que pedidos de TU MUNDO PUERTA no aparecen
- [ ] Verificar que otros pedidos siguen apareciendo normalmente

---

## 🔍 Notas Importantes

1. **Compatibilidad:** Todos los cambios son compatibles con la lógica existente
2. **Orden de aplicación:** Los filtros se aplican en orden:
   - Primero excluir pedidos web
   - Luego excluir pedidos de TU MUNDO PUERTA
   - Finalmente excluir pedidos cancelados
3. **Manejo de errores:** La función `excluir_pedidos_tu_mundo_puerta` tiene manejo de errores robusto con fallback
4. **Búsqueda del cliente:** La función busca el cliente por RIF "J-507172554" en `clientes_collection`
5. **Doble filtro:** Se excluyen pedidos tanto por `cliente_id` como por `cliente_nombre` (regex) para mayor seguridad
6. **Filtro de cancelados:** El filtro `estado_general != "cancelado"` aplica a TODOS los pedidos, no solo a TU MUNDO PUERTA

---

## 📝 Resumen de Archivos Modificados

- **Archivo único:** `api/src/routes/pedidos.py`
  - Línea ~4233: Agregar limpieza de pagos al cancelar
  - Línea ~61: Agregar función `excluir_pedidos_tu_mundo_puerta()`
  - Línea ~165: Agregar filtro de cancelados en `/all/`
  - Línea ~4731: Agregar filtro de cancelados en `/mis-pagos`
  - Línea ~163: Agregar filtro de TU MUNDO PUERTA en `/all/`
  - Línea ~4729: Agregar filtro de TU MUNDO PUERTA en `/mis-pagos`

---

## 🧪 Pruebas Recomendadas

1. **Prueba de limpieza de pagos:**
   - Crear pedido → Agregar pago → Cancelar → Verificar que pagos se limpiaron

2. **Prueba de filtrado de cancelados:**
   - Crear pedido de cualquier cliente → Cancelar → Verificar que NO aparece en `/all/` ni `/mis-pagos`
   - Verificar que pedidos NO cancelados SÍ aparecen normalmente

3. **Prueba de filtrado de TU MUNDO PUERTA:**
   - Crear pedido de TU MUNDO PUERTA → Verificar que NO aparece en `/all/` ni `/mis-pagos`
   - Crear pedido de otro cliente → Verificar que SÍ aparece normalmente

4. **Prueba de integración:**
   - Verificar que los endpoints siguen funcionando correctamente
   - Verificar que no se rompió ninguna funcionalidad existente
   - Verificar que en MonitorPedidos, cuando se activa el filtro de cancelados, SÍ aparecen los pedidos cancelados

---

## ✅ Estado de Implementación

- ✅ **Cambio 1 (Limpiar pagos):** IMPLEMENTADO
- ✅ **Cambio 2 (Filtrar todos los cancelados):** IMPLEMENTADO
- ✅ **Cambio 3 (Filtrar TU MUNDO PUERTA):** IMPLEMENTADO

Todos los cambios ya están implementados y subidos al repositorio. Este documento sirve como referencia y documentación.
