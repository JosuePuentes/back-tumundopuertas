# 📋 DOCUMENTACIÓN - ENDPOINTS PANEL DE CONTROL LOGÍSTICO

## ✅ Endpoints Implementados

Todos los endpoints están implementados en `api/src/routes/pedidos.py` (líneas 8128-8614).

---

## 📍 ENDPOINTS NUEVOS IMPLEMENTADOS

### 1. **GET `/pedidos/panel-control-logistico/items-produccion-por-estado/`**

**Descripción:** Items en producción agrupados por estado_item

**Respuesta:**
```json
{
  "items_por_estado": {
    "pendiente": {
      "estado": 0,
      "estado_nombre": "pendiente",
      "items": [...],
      "total_items": 10,
      "total_cantidad": 50
    },
    "herreria": {...},
    "masillar": {...},
    "preparar": {...}
  },
  "fecha_actualizacion": "2024-01-01T12:00:00"
}
```

---

### 2. **GET `/pedidos/panel-control-logistico/asignaciones-terminadas/`**

**Descripción:** Asignaciones terminadas con detalles

**Parámetros opcionales:**
- `fecha_inicio` (string): Fecha inicio formato ISO
- `fecha_fin` (string): Fecha fin formato ISO
- `empleado_id` (string): ID del empleado

**Ejemplo:**
```
GET /pedidos/panel-control-logistico/asignaciones-terminadas/?fecha_inicio=2024-01-01&empleado_id=12345
```

**Respuesta:**
```json
{
  "asignaciones_terminadas": [...],
  "total": 50,
  "fecha_actualizacion": "2024-01-01T12:00:00"
}
```

---

### 3. **GET `/pedidos/panel-control-logistico/empleados-items-terminados/`**

**Descripción:** Empleados con cantidad de items terminados

**Parámetros opcionales:**
- `fecha_inicio` (string): Fecha inicio formato ISO
- `fecha_fin` (string): Fecha fin formato ISO

**Respuesta:**
```json
{
  "empleados": [
    {
      "_id": "empleado_id",
      "empleado_nombre": "Juan Pérez",
      "empleado_identificador": "12345",
      "total_items_terminados": 100,
      "total_asignaciones": 50,
      "items": [...]
    }
  ],
  "total_empleados": 10,
  "fecha_actualizacion": "2024-01-01T12:00:00"
}
```

---

### 4. **GET `/pedidos/panel-control-logistico/items-por-ventas/`**

**Descripción:** Items vendidos con detalles de ventas

**Parámetros opcionales:**
- `fecha_inicio` (string): Fecha inicio formato ISO
- `fecha_fin` (string): Fecha fin formato ISO

**Respuesta:**
```json
{
  "items_ventas": [
    {
      "_id": "codigo_item",
      "item_id": "item_id",
      "cantidad_vendida": 50,
      "item_nombre": "Puerta Principal",
      "precio_promedio": 100.00,
      "total_ventas": 5000.00,
      "existencia_actual": 10,
      "pedidos": [...]
    }
  ],
  "total_items": 20,
  "total_cantidad_vendida": 500,
  "fecha_actualizacion": "2024-01-01T12:00:00"
}
```

---

### 5. **GET `/pedidos/panel-control-logistico/inventario-por-sucursal/`**

**Descripción:** Inventario agrupado por sucursal

**Respuesta:**
```json
{
  "inventario_por_sucursal": {
    "sucursal_1": {
      "nombre": "Sucursal Principal",
      "items": [...],
      "total_items": 1000,
      "total_valor": 50000.00
    },
    "sucursal_2": {
      "nombre": "Sucursal 2",
      "items": [...],
      "total_items": 500,
      "total_valor": 25000.00
    }
  },
  "fecha_actualizacion": "2024-01-01T12:00:00"
}
```

---

### 6. **GET `/pedidos/panel-control-logistico/sugerencia-produccion-mejorada/`**

**Descripción:** Sugerencias mejoradas de producción con más detalles

**Respuesta:**
```json
{
  "sugerencias": [
    {
      "item_id": "item_id",
      "codigo": "COD001",
      "nombre": "Puerta Principal",
      "existencia_actual": 5,
      "existencia_real": 3,
      "en_produccion": {
        "total": 2,
        "por_estado": {
          "0": 1,
          "1": 1,
          "2": 0,
          "3": 0
        }
      },
      "vendidas": {
        "ultimos_30_dias": 10,
        "ultimos_60_dias": 20,
        "promedio_mensual": 10.0
      },
      "prioridad": 2,
      "cantidad_sugerida": 7.0,
      "precio": 100.00,
      "costo": 50.00
    }
  ],
  "total": 15,
  "fecha_actualizacion": "2024-01-01T12:00:00"
}
```

---

### 7. **GET `/pedidos/panel-control-logistico/exportar-pdf/`**

**Descripción:** Exportar datos del panel de control para PDF

**Parámetros requeridos:**
- `tipo` (string): Tipo de exportación. Valores válidos:
  - `resumen`
  - `items-produccion`
  - `ventas`
  - `inventario`

**Parámetros opcionales:**
- `fecha_inicio` (string): Fecha inicio formato ISO (solo para tipo "ventas")
- `fecha_fin` (string): Fecha fin formato ISO (solo para tipo "ventas")

**Ejemplo:**
```
GET /pedidos/panel-control-logistico/exportar-pdf/?tipo=ventas&fecha_inicio=2024-01-01&fecha_fin=2024-01-31
```

**Respuesta:**
```json
{
  "tipo": "ventas",
  "datos": {...},
  "fecha_exportacion": "2024-01-01T12:00:00"
}
```

---

## 📝 NOTAS IMPORTANTES

1. **Todos los endpoints usan `debug_log()`** en lugar de `print()` para logs
2. **No requieren autenticación** (no tienen `Depends(get_current_user)`)
3. **URLs completas:** Con el prefijo `/pedidos` del router:
   - `GET http://localhost:8002/pedidos/panel-control-logistico/items-produccion-por-estado/`
   - `GET http://localhost:8002/pedidos/panel-control-logistico/asignaciones-terminadas/`
   - etc.

---

## ✅ VERIFICACIÓN

- ✅ Todos los endpoints implementados
- ✅ Sin errores de sintaxis
- ✅ Usan `debug_log()` para logs
- ✅ Manejo de errores con HTTPException
- ✅ Documentación en docstrings

---

## 🚀 PRÓXIMOS PASOS

1. Reiniciar el servidor del backend
2. Probar los endpoints con Postman o curl
3. Integrar en el frontend

