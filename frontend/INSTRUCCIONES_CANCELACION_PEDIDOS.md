# 📋 INSTRUCCIONES FRONTEND - CANCELACIÓN DE PEDIDOS

## ⚠️ PROBLEMA IDENTIFICADO

El frontend actualmente usa `/pedidos/actualizar-estado-general/` para cambiar el estado a "cancelado", pero esto **NO ejecuta** las acciones necesarias:
- ❌ No elimina transacciones de métodos de pago
- ❌ No revierte saldos de métodos de pago
- ❌ Solo cambia el estado, pero no limpia completamente el pedido

## ✅ SOLUCIÓN

Cuando se cancela un pedido, el frontend **DEBE usar el endpoint específico** `/pedidos/cancelar/{pedido_id}` en lugar de `actualizar-estado-general`.

---

## 🔧 CAMBIOS NECESARIOS EN FRONTEND

### **1. Modificar MonitorPedidos.tsx**

**UBICACIÓN:** `frontend/src/organism/monitorped/MonitorPedidos.tsx`

**PROBLEMA ACTUAL:**
```tsx
const handleActualizarEstado = useCallback(async (pedidoId: string) => {
  if (!estadoSeleccionado[pedidoId]) return;
  setActualizando(pedidoId);
  try {
    const res = await fetch(`${apiUrl}/pedidos/actualizar-estado-general/`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pedido_id: pedidoId, nuevo_estado_general: estadoSeleccionado[pedidoId] }),
    });
    // ...
  }
}, [apiUrl, estadoSeleccionado]);
```

**SOLUCIÓN:**
```tsx
const handleActualizarEstado = useCallback(async (pedidoId: string) => {
  if (!estadoSeleccionado[pedidoId]) return;
  setActualizando(pedidoId);
  try {
    // Si se está cancelando, usar el endpoint específico de cancelación
    if (estadoSeleccionado[pedidoId] === "cancelado") {
      // Solicitar motivo de cancelación
      const motivo = prompt("Ingrese el motivo de cancelación:");
      if (!motivo || motivo.trim() === "") {
        alert("El motivo de cancelación es requerido");
        setActualizando("");
        return;
      }
      
      const res = await fetch(`${apiUrl}/pedidos/cancelar/${pedidoId}`, {
        method: "PUT",
        headers: { 
          "Content-Type": "application/json",
          "Authorization": `Bearer ${localStorage.getItem("access_token")}`
        },
        body: JSON.stringify({ motivo_cancelacion: motivo.trim() }),
      });
      
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Error al cancelar pedido");
      }
      
      const result = await res.json();
      // Recargar pedidos para reflejar los cambios
      await fetchPedidos();
      alert(`Pedido cancelado exitosamente. Transacciones eliminadas: ${result.transacciones_eliminadas || 0}`);
    } else {
      // Para otros estados, usar el endpoint normal
      const res = await fetch(`${apiUrl}/pedidos/actualizar-estado-general/`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pedido_id: pedidoId, nuevo_estado_general: estadoSeleccionado[pedidoId] }),
      });
      if (!res.ok) throw new Error("Error actualizando estado");
      // Actualizar localmente el estado
      setPedidos((prev) => prev.map((p) => p._id === pedidoId ? { ...p, estado_general: estadoSeleccionado[pedidoId] } : p));
    }
  } catch (err: any) {
    alert(err.message || "Error al actualizar estado");
  } finally {
    setActualizando("");
  }
}, [apiUrl, estadoSeleccionado, fetchPedidos]);
```

---

## 📝 ENDPOINT DE CANCELACIÓN

### **PUT `/pedidos/cancelar/{pedido_id}`**

**Headers:**
```
Authorization: Bearer {token}
Content-Type: application/json
```

**Body:**
```json
{
  "motivo_cancelacion": "Motivo de la cancelación"
}
```

**Respuesta exitosa:**
```json
{
  "success": true,
  "message": "Pedido cancelado exitosamente",
  "pedido_id": "...",
  "transacciones_eliminadas": 2,
  "saldos_revertidos": 1,
  "total_abonado_revertido": 500.0,
  "items_actualizados": 3
}
```

**Errores posibles:**
- `400`: Pedido no está en estado "pendiente"
- `400`: Pedido tiene asignaciones activas
- `404`: Pedido no encontrado
- `500`: Error interno

---

## ✅ VERIFICACIONES QUE DEBE HACER EL FRONTEND

### **1. Verificar que NO se muestren pedidos cancelados**

El backend ya filtra automáticamente, pero el frontend puede agregar una verificación adicional:

```tsx
// En cualquier componente que muestre pedidos
const pedidosFiltrados = pedidos.filter(p => p.estado_general !== "cancelado");
```

### **2. Verificar que se recarguen los datos después de cancelar**

Después de cancelar exitosamente, **SIEMPRE** recargar los datos:

```tsx
// Después de cancelar exitosamente
await fetchPedidos(); // O el método que cargue los pedidos
```

### **3. Verificar que se muestre mensaje de éxito**

Mostrar información al usuario sobre lo que se hizo:

```tsx
if (result.transacciones_eliminadas > 0) {
  alert(`Pedido cancelado. Se eliminaron ${result.transacciones_eliminadas} transacciones y se revirtieron ${result.saldos_revertidos} saldos.`);
}
```

---

## 🎯 COMPONENTES QUE DEBEN VERIFICARSE

### **1. MonitorPedidos.tsx** ⚠️ **CRÍTICO**
- ✅ Cambiar `handleActualizarEstado` para usar `/cancelar/{pedido_id}` cuando estado es "cancelado"
- ✅ Solicitar motivo de cancelación
- ✅ Recargar pedidos después de cancelar
- ✅ Mostrar mensaje de éxito

### **2. Otros componentes que puedan cancelar pedidos**
- Buscar en el código si hay otros lugares donde se cambie el estado a "cancelado"
- Aplicar el mismo cambio

---

## 📋 CHECKLIST DE IMPLEMENTACIÓN

- [ ] Modificar `MonitorPedidos.tsx` para usar endpoint `/cancelar/{pedido_id}`
- [ ] Agregar solicitud de motivo de cancelación
- [ ] Agregar recarga de datos después de cancelar
- [ ] Agregar mensaje de éxito/error
- [ ] Verificar que no se muestren pedidos cancelados en otros componentes
- [ ] Probar cancelación de un pedido
- [ ] Verificar que el pedido desaparece de todos los módulos
- [ ] Verificar que las transacciones se eliminan
- [ ] Verificar que los saldos se revierten

---

## 🔍 CÓMO VERIFICAR QUE FUNCIONA

### **1. Cancelar un pedido:**
1. Ir a `/monitorpedidos`
2. Seleccionar un pedido en estado "pendiente"
3. Cambiar estado a "cancelado"
4. Ingresar motivo de cancelación
5. Verificar mensaje de éxito

### **2. Verificar que desaparece:**
- ✅ No aparece en `/pedidosherreria`
- ✅ No aparece en `/facturacion`
- ✅ No aparece en `/pagos`
- ✅ No aparece en `/mispagos`
- ✅ No aparece en `/monitorpedidos` (después de filtrar)

### **3. Verificar transacciones:**
- ✅ Las transacciones relacionadas se eliminaron
- ✅ Los saldos de métodos de pago se revirtieron

---

## ⚠️ IMPORTANTE

**NO usar `/actualizar-estado-general/` para cancelar pedidos.**

Solo usar `/cancelar/{pedido_id}` porque:
- ✅ Elimina transacciones
- ✅ Revierte saldos
- ✅ Limpia pagos correctamente
- ✅ Actualiza items correctamente

---

## 📚 ENDPOINTS DEL BACKEND

### **Cancelar pedido (CORRECTO):**
```
PUT /pedidos/cancelar/{pedido_id}
Body: { "motivo_cancelacion": "..." }
```

### **Actualizar estado (NO usar para cancelar):**
```
PUT /pedidos/actualizar-estado-general/
Body: { "pedido_id": "...", "nuevo_estado_general": "..." }
```

---

**Última actualización:** $(date)  
**Versión:** 1.0

