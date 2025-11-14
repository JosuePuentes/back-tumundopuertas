# Instrucciones para Frontend - Implementación de Sucursales en Crear Pedido

## ✅ Cambios del Backend Completados

El backend ya está listo y soporta:
- Campo `sucursal` en el modelo Pedido (opcional, default: "sucursal1")
- Descuento automático del inventario según la sucursal seleccionada
- Endpoint de inventario con filtro por sucursal

---

## 📋 Tareas para el Frontend

### 1. **Modal de Selección de Sucursal al Entrar**

**Ubicación:** `frontend/src/organism/pedido/CrearPedido.tsx`

**Requisitos:**
- Al montar el componente o al entrar a la página, mostrar un modal/dialog
- Modal debe tener dos opciones: "Sucursal 1" y "Sucursal 2"
- El usuario debe seleccionar una antes de continuar
- Guardar la selección en el estado del componente

**Ejemplo de estructura:**
```tsx
const [sucursalSeleccionada, setSucursalSeleccionada] = useState<string | null>(null);
const [showModalSucursal, setShowModalSucursal] = useState(true);

// Modal de selección de sucursal
{showModalSucursal && (
  <Dialog open={showModalSucursal}>
    <DialogContent>
      <DialogTitle>Seleccionar Sucursal</DialogTitle>
      <DialogDescription>
        ¿Desde qué sucursal estás creando este pedido?
      </DialogDescription>
      <div className="flex gap-4">
        <Button onClick={() => {
          setSucursalSeleccionada("sucursal1");
          setShowModalSucursal(false);
        }}>Sucursal 1</Button>
        <Button onClick={() => {
          setSucursalSeleccionada("sucursal2");
          setShowModalSucursal(false);
        }}>Sucursal 2</Button>
      </div>
    </DialogContent>
  </Dialog>
)}
```

---

### 2. **Modificar Llamada a Inventario para Incluir Sucursal**

**Ubicación:** `frontend/src/organism/pedido/CrearPedido.tsx` y `frontend/src/hooks/useItems.ts`

**Cambio necesario:**
- Cuando se cargan los items del inventario, incluir el parámetro `sucursal` en la URL
- El endpoint ahora acepta: `/inventario/all?sucursal=sucursal1` o `/inventario/all?sucursal=sucursal2`

**Ejemplo:**
```tsx
// En lugar de:
fetchItems(`${apiUrl}/inventario/all`);

// Usar:
fetchItems(`${apiUrl}/inventario/all?sucursal=${sucursalSeleccionada}`);
```

**Importante:** Solo cargar items después de que el usuario haya seleccionado la sucursal.

---

### 3. **Mostrar Cantidades de la Sucursal Correcta**

**Ubicación:** `frontend/src/organism/pedido/CrearPedido.tsx`

**Cambio necesario:**
- El backend ahora retorna un campo `existencia_sucursal` cuando se especifica el parámetro `sucursal`
- Usar este campo para mostrar las cantidades disponibles en lugar de `cantidad` o `existencia`
- Mostrar claramente que son las cantidades de la sucursal seleccionada

**Ejemplo:**
```tsx
// En lugar de mostrar:
<div>Cantidad disponible: {item.cantidad}</div>

// Mostrar:
<div>
  Cantidad disponible ({sucursalSeleccionada === "sucursal1" ? "Sucursal 1" : "Sucursal 2"}): 
  {item.existencia_sucursal || 0}
</div>
```

---

### 4. **Incluir Campo sucursal al Crear el Pedido**

**Ubicación:** `frontend/src/organism/pedido/CrearPedido.tsx` - función `handleSubmit`

**Cambio necesario:**
- Al construir el payload del pedido, incluir el campo `sucursal` con el valor seleccionado

**Ejemplo:**
```tsx
const pedidoPayload: PedidoPayload = {
  cliente_id: String(clienteId),
  cliente_nombre: clienteObj?.nombre || "",
  fecha_creacion: fechaISO,
  fecha_actualizacion: fechaISO,
  estado_general: "pendiente",
  creado_por: user?.usuario || "N/A",
  sucursal: sucursalSeleccionada || "sucursal1", // ← AGREGAR ESTE CAMPO
  items: selectedItems.map((item) => {
    // ... resto del código
  }),
  seguimiento,
};
```

---

### 5. **Validar Cantidades Disponibles por Sucursal**

**Ubicación:** `frontend/src/organism/pedido/CrearPedido.tsx`

**Cambio necesario:**
- Al agregar items al pedido, validar que la cantidad solicitada no exceda `existencia_sucursal`
- Mostrar mensajes de error específicos indicando la sucursal

**Ejemplo:**
```tsx
const handleAddItem = () => {
  // ... código existente ...
  
  // Validar existencia de la sucursal
  const itemData = itemsData.find((it: any) => it._id === selectedItemId);
  if (itemData) {
    const existenciaDisponible = itemData.existencia_sucursal || 0;
    if (cantidad > existenciaDisponible) {
      setMensaje(`❌ No hay suficiente existencia en ${sucursalSeleccionada === "sucursal1" ? "Sucursal 1" : "Sucursal 2"}. Disponible: ${existenciaDisponible}`);
      setMensajeTipo("error");
      return;
    }
  }
  
  // ... resto del código
};
```

---

## 🔄 Flujo Completo

1. **Usuario entra a Crear Pedido**
   - Se muestra modal de selección de sucursal
   - Usuario selecciona "Sucursal 1" o "Sucursal 2"

2. **Cargar Inventario**
   - Se llama a `/inventario/all?sucursal=sucursal1` o `?sucursal=sucursal2`
   - Los items vienen con `existencia_sucursal` mostrando las cantidades de esa sucursal

3. **Agregar Items al Pedido**
   - Se valida que la cantidad no exceda `existencia_sucursal`
   - Se muestra claramente la sucursal de la que se está descontando

4. **Crear el Pedido**
   - Se incluye `sucursal: "sucursal1"` o `sucursal: "sucursal2"` en el payload
   - El backend descuenta automáticamente del campo correcto:
     - Sucursal 1 → descuenta de `cantidad` (o `existencia`)
     - Sucursal 2 → descuenta de `existencia2`

---

## 📝 Notas Importantes

- El campo `sucursal` es opcional en el backend (default: "sucursal1"), pero es recomendable siempre enviarlo
- Si no se envía `sucursal`, el backend usará "sucursal1" por defecto
- El campo `existencia_sucursal` solo aparece cuando se incluye el parámetro `sucursal` en la query
- No cambiar la lógica existente del componente, solo agregar estas funcionalidades

---

## ✅ Checklist de Implementación

- [ ] Modal de selección de sucursal al entrar
- [ ] Guardar sucursal seleccionada en estado
- [ ] Modificar llamada a `/inventario/all` para incluir parámetro `sucursal`
- [ ] Mostrar cantidades usando `existencia_sucursal`
- [ ] Validar cantidades disponibles según sucursal
- [ ] Incluir campo `sucursal` en el payload al crear pedido
- [ ] Mostrar indicadores visuales de qué sucursal está seleccionada

---

## 🧪 Pruebas Sugeridas

1. Crear pedido desde Sucursal 1 → Verificar que descuenta de `cantidad`
2. Crear pedido desde Sucursal 2 → Verificar que descuenta de `existencia2`
3. Intentar agregar más cantidad de la disponible → Verificar validación
4. Verificar que los logs del backend muestren la sucursal correcta






