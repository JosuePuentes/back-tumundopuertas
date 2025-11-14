# Instrucciones Frontend - Optimizar PedidosHerreria y Ocultar Logs

## 📋 Cambios en el Backend (Ya Implementados)

### ✅ Optimizaciones Aplicadas:
1. **Endpoint `/pedidos/estado/` optimizado:**
   - Filtra solo items con `estado_item` 0 o 1 (pendientes y en herrería)
   - Usa proyección para traer solo campos necesarios
   - Limita a 500 pedidos más recientes
   - Ordena por fecha descendente
   - Eliminado enriquecimiento de cliente (mejora rendimiento)

2. **Índices de MongoDB creados:**
   - Índice compuesto en `estado_general` y `tipo_pedido`
   - Índice en `items.estado_item`
   - Índice en `fecha_creacion` (descendente)

3. **Logs de debug deshabilitados:**
   - Todos los `print()` de debug ahora usan `debug_log()`
   - Solo se muestran si `DEBUG=true` está en variables de entorno
   - En producción no se mostrarán logs

---

## 🎯 Tareas para el Frontend

### 1. **Optimizar PedidosHerreria.tsx**

**Archivo:** `frontend/src/organism/fabricacion/creacion/PedidosHerreria.tsx`

**Cambios necesarios:**

#### A. Eliminar console.log innecesarios
```tsx
// ELIMINAR esta línea:
console.log("Pedidos cargados:", dataPedidos);
```

#### B. Agregar paginación o límite (opcional)
Si hay muchos pedidos, considerar mostrar solo los primeros 20-30 y cargar más al hacer scroll.

#### C. Agregar loading optimizado
```tsx
// Mejorar el mensaje de loading
{loading && (
  <div className="flex justify-center items-center py-8">
    <span className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-600 mr-2"></span>
    <span className="text-blue-600 font-semibold">Cargando pedidos de herrería...</span>
  </div>
)}
```

---

### 2. **Deshabilitar console.log en Producción**

**Archivo:** `frontend/src/main.tsx` o crear un archivo de configuración

**Opción A: Deshabilitar todos los console.log (Recomendado)**

Agregar al inicio de `main.tsx` o en un archivo de utilidades:

```typescript
// Deshabilitar console.log en producción
if (import.meta.env.PROD) {
  // Guardar funciones originales por si acaso
  const noop = () => {};
  
  // Reemplazar console.log, console.debug, console.info
  console.log = noop;
  console.debug = noop;
  console.info = noop;
  
  // Mostrar mensaje informativo
  console.warn = function(...args: any[]) {
    if (args[0]?.includes?.('DEBUG') || args[0]?.includes?.('LOG')) {
      return; // No mostrar logs de debug
    }
    // Mostrar warnings importantes
    if (typeof window !== 'undefined') {
      console.warn = function() {
        // Solo mostrar errores críticos
      };
    }
  };
  
  // Mostrar mensaje en consola
  console.log = function() {
    console.info('%c🔒 Los logs están deshabilitados en producción. Para ver logs, abra las herramientas de desarrollo en modo desarrollo.', 'color: #666; font-size: 12px;');
  };
  
  // Mostrar el mensaje una vez
  (function() {
    const style = 'color: #666; font-size: 14px; font-weight: bold; padding: 10px;';
    console.log('%c🔒 Logs Deshabilitados', style);
    console.log('%cLos logs de debug están deshabilitados en producción para mejorar el rendimiento.', 'color: #999; font-size: 12px;');
  })();
}
```

**Opción B: Mensaje personalizado en F12**

Agregar esto al inicio de `main.tsx`:

```typescript
// Mostrar mensaje cuando se abre la consola
if (import.meta.env.PROD && typeof window !== 'undefined') {
  const originalLog = console.log;
  console.log = function(...args: any[]) {
    if (args.length === 0 || !args[0]?.includes?.('🔒')) {
      // Mostrar mensaje grande
      const style = `
        font-size: 24px;
        font-weight: bold;
        color: #2563eb;
        text-align: center;
        padding: 20px;
        background: #eff6ff;
        border: 2px solid #2563eb;
        border-radius: 8px;
        margin: 20px;
      `;
      console.log('%c🔒 LOGS DESHABILITADOS EN PRODUCCIÓN', style);
      console.log('%cLos logs de debug están deshabilitados para mejorar el rendimiento y seguridad.', 'font-size: 14px; color: #666;');
      console.log = function() {}; // Deshabilitar después del primer mensaje
      return;
    }
    originalLog.apply(console, args);
  };
}
```

**Opción C: Interceptar console.log (Más robusto)**

Crear archivo: `frontend/src/utils/consoleConfig.ts`

```typescript
// frontend/src/utils/consoleConfig.ts
export const configureConsole = () => {
  if (import.meta.env.PROD) {
    // Guardar funciones originales
    const originalLog = console.log;
    const originalDebug = console.debug;
    const originalInfo = console.info;
    
    // Función para mostrar mensaje
    const showMessage = () => {
      const style = `
        font-size: 20px;
        font-weight: bold;
        color: #2563eb;
        text-align: center;
        padding: 15px;
        background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
        border: 2px solid #2563eb;
        border-radius: 8px;
        margin: 10px 0;
      `;
      originalLog('%c🔒 LOGS DESHABILITADOS EN PRODUCCIÓN', style);
      originalLog('%cLos logs de desarrollo están deshabilitados para mejorar el rendimiento.', 'font-size: 12px; color: #666;');
    };
    
    // Mostrar mensaje la primera vez
    let messageShown = false;
    
    // Interceptar console.log
    console.log = function(...args: any[]) {
      if (!messageShown) {
        showMessage();
        messageShown = true;
      }
      // No mostrar nada más
    };
    
    // Interceptar console.debug
    console.debug = function() {};
    
    // Interceptar console.info
    console.info = function() {};
    
    // Mantener console.error y console.warn para errores importantes
    // console.error y console.warn se mantienen activos
  }
};
```

Luego en `main.tsx`:

```typescript
import { configureConsole } from './utils/consoleConfig';

// Configurar consola antes de renderizar
configureConsole();

// ... resto del código
```

---

### 3. **Optimizar Carga de Empleados**

**Archivo:** `frontend/src/organism/fabricacion/creacion/PedidosHerreria.tsx`

**Cambio:**
```tsx
// Cargar empleados solo cuando sea necesario o en paralelo
useEffect(() => {
  setLoading(true);
  
  // Cargar ambos en paralelo
  Promise.all([
    fetchPedido("/pedidos/estado/?estado_general=orden1&estado_general=pendiente"),
    fetchEmpleado(`${import.meta.env.VITE_API_URL}/empleados/all/`)
  ])
    .catch(() => setError("Error al cargar los datos"))
    .finally(() => setLoading(false));
}, []);
```

---

### 4. **Agregar Memoización (Opcional - Para mejor rendimiento)**

```tsx
import React, { useEffect, useState, useMemo } from "react";

// ... código existente ...

// Memoizar pedidos filtrados
const pedidosFiltrados = useMemo(() => {
  if (!Array.isArray(dataPedidos)) return [];
  return dataPedidos.filter((pedido: Pedido) => {
    // Solo mostrar pedidos con items pendientes o en herrería
    return pedido.items.some(item => 
      item.estado_item === 0 || item.estado_item === 1
    );
  });
}, [dataPedidos]);
```

---

## ✅ Checklist de Implementación

- [ ] Eliminar `console.log("Pedidos cargados:", dataPedidos)` de PedidosHerreria.tsx
- [ ] Implementar deshabilitación de console.log en producción (elegir una opción)
- [ ] Optimizar carga paralela de pedidos y empleados
- [ ] Probar que el módulo carga más rápido (menos de 1 minuto)
- [ ] Verificar que F12 no muestra logs (solo mensaje informativo)
- [ ] Probar en producción que los logs están deshabilitados

---

## 🧪 Pruebas

1. **Rendimiento:**
   - Abrir PedidosHerreria
   - Medir tiempo de carga (debe ser < 1 minuto)
   - Verificar que no hay delays

2. **Logs:**
   - Abrir F12 en producción
   - Verificar que no aparecen logs de debug
   - Verificar que aparece mensaje informativo (si se implementó)

3. **Funcionalidad:**
   - Verificar que los pedidos se muestran correctamente
   - Verificar que las asignaciones funcionan
   - Verificar que no hay errores en consola

---

## 📝 Notas Importantes

- Los logs del backend solo se muestran si `DEBUG=true` en variables de entorno
- En producción, el backend NO mostrará logs de debug
- El frontend debe manejar sus propios logs
- Los índices de MongoDB se crean automáticamente al iniciar el servidor

---

## 🚀 Resultado Esperado

- ✅ PedidosHerreria carga en menos de 1 minuto
- ✅ F12 no muestra logs de debug en producción
- ✅ Mensaje informativo al abrir F12 (opcional)
- ✅ Mejor rendimiento general del módulo






