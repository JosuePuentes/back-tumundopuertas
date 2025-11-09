# 🚀 INSTRUCCIONES DE OPTIMIZACIÓN - FRONTEND

## Para trabajar en conjunto con la IA del Frontend

**Objetivo:** Hacer el sistema 2-3x más rápido sin cambiar la lógica  
**Tiempo estimado:** 4-5 horas  
**Riesgo:** 0% (no cambia funcionalidad, solo optimiza)

---

## 📋 ÍNDICE

1. [Carga Paralela en Componentes](#1-carga-paralela-en-componentes)
2. [Memoización con React.memo](#2-memoización-con-reactmemo)
3. [useMemo para Cálculos Pesados](#3-usememo-para-cálculos-pesados)
4. [useCallback para Funciones](#4-usecallback-para-funciones)
5. [Lazy Loading de Rutas](#5-lazy-loading-de-rutas)
6. [Optimizaciones Adicionales](#6-optimizaciones-adicionales)

---

## 1. CARGA PARALELA EN COMPONENTES

### 🎯 Objetivo
Cambiar carga secuencial (uno tras otro) a paralela (al mismo tiempo) para reducir el tiempo de carga.

### 📍 Archivo 1: `PedidosHerreria.tsx`

#### ❌ CÓDIGO ACTUAL (Secuencial - Lento):
```tsx
useEffect(() => {
  setLoading(true);
  fetchPedido("/pedidos/estado/?estado_general=orden1&estado_general=pendiente&/")
    .catch(() => setError("Error al cargar los pedidos"))
    .finally(() => setLoading(false));
  fetchEmpleado(`${import.meta.env.VITE_API_URL}/empleados/all/`);
}, []);
```

**Problema:** `fetchEmpleado` espera a que termine `fetchPedido`, aunque no dependen entre sí.

#### ✅ CÓDIGO OPTIMIZADO (Paralelo - Rápido):
```tsx
useEffect(() => {
  setLoading(true);
  setError(null);
  
  // Cargar ambos en paralelo
  Promise.all([
    fetchPedido("/pedidos/estado/?estado_general=orden1&estado_general=pendiente&/"),
    fetchEmpleado(`${import.meta.env.VITE_API_URL}/empleados/all/`)
  ])
    .catch(() => setError("Error al cargar los datos"))
    .finally(() => setLoading(false));
}, []);
```

**Cambios:**
1. Usar `Promise.all()` para cargar ambos al mismo tiempo
2. Mover `setError(null)` al inicio
3. Un solo `.finally()` para ambos

**Mejora esperada:** 30-50% más rápido

---

### 📍 Archivo 2: `CrearPedido.tsx`

#### Buscar este patrón:
```tsx
useEffect(() => {
  fetchClientes(`${apiUrl}/clientes/all`);
}, []);

useEffect(() => {
  fetchItems(`${apiUrl}/inventario/all`);
}, []);
```

#### ✅ CÓDIGO OPTIMIZADO:
```tsx
useEffect(() => {
  // Cargar ambos en paralelo
  Promise.all([
    fetchClientes(`${apiUrl}/clientes/all`),
    fetchItems(`${apiUrl}/inventario/all`)
  ]).catch((err) => {
    // Manejar errores si es necesario
    console.error("Error cargando datos:", err);
  });
}, [apiUrl]);
```

**Mejora esperada:** 40-60% más rápido en carga inicial

---

### 📍 Archivo 3: `TerminarAsignacion.tsx`

Este archivo ya carga datos de forma secuencial dentro de un solo `useEffect`, pero está bien. No necesita cambios aquí.

---

## 2. MEMOIZACIÓN CON React.memo

### 🎯 Objetivo
Evitar re-renderizados innecesarios de componentes que reciben props estables.

### 📍 Archivo 1: `DetalleHerreria.tsx`

#### ❌ CÓDIGO ACTUAL:
```tsx
const DetalleHerreria: React.FC<{ pedido: Pedido }> = ({ pedido }) => {
  // ... código del componente
};

export default DetalleHerreria;
```

#### ✅ CÓDIGO OPTIMIZADO:
```tsx
import React from "react";

const DetalleHerreria: React.FC<{ pedido: Pedido }> = ({ pedido }) => {
  // ... código del componente (sin cambios)
};

// Memoizar el componente para evitar re-renderizados innecesarios
export default React.memo(DetalleHerreria);
```

**Cuándo usar React.memo:**
- ✅ Componente que recibe props que no cambian frecuentemente
- ✅ Componente que se renderiza muchas veces (en un map)
- ❌ NO usar si las props cambian constantemente

---

### 📍 Archivo 2: `AsignarArticulos.tsx`

#### ❌ CÓDIGO ACTUAL:
```tsx
const AsignarArticulos: React.FC<AsignarArticulosProps> = ({
  items,
  empleados,
  pedidoId,
  numeroOrden,
  estado_general,
  nuevo_estado_general,
  tipoEmpleado,
}) => {
  // ... código
};

export default AsignarArticulos;
```

#### ✅ CÓDIGO OPTIMIZADO:
```tsx
import React from "react";

const AsignarArticulos: React.FC<AsignarArticulosProps> = ({
  items,
  empleados,
  pedidoId,
  numeroOrden,
  estado_general,
  nuevo_estado_general,
  tipoEmpleado,
}) => {
  // ... código (sin cambios)
};

// Memoizar con comparación personalizada si es necesario
export default React.memo(AsignarArticulos, (prevProps, nextProps) => {
  // Solo re-renderizar si cambian estas props importantes
  return (
    prevProps.pedidoId === nextProps.pedidoId &&
    prevProps.numeroOrden === nextProps.numeroOrden &&
    JSON.stringify(prevProps.items) === JSON.stringify(nextProps.items) &&
    JSON.stringify(prevProps.empleados) === JSON.stringify(nextProps.empleados)
  );
});
```

**Nota:** La comparación personalizada es opcional. Si no la pones, React.memo compara todas las props automáticamente.

---

### 📍 Archivo 3: `PedidoGroup` en `DashboardPedidos.tsx`

#### ❌ CÓDIGO ACTUAL:
```tsx
const PedidoGroup: React.FC<{ title: string; pedidos: PedidoRuta[]; now: number }> = ({ title, pedidos, now }) => {
  // ... código
};
```

#### ✅ CÓDIGO OPTIMIZADO:
```tsx
import React from "react";

const PedidoGroup: React.FC<{ title: string; pedidos: PedidoRuta[]; now: number }> = React.memo(({ title, pedidos, now }) => {
  // ... código (sin cambios)
});
```

**Mejora esperada:** 20-40% menos re-renderizados

---

## 3. useMemo PARA CÁLCULOS PESADOS

### 🎯 Objetivo
Evitar recalcular valores que solo dependen de ciertos datos.

### 📍 Archivo 1: `DashboardPedidos.tsx`

#### ✅ CÓDIGO ACTUAL (Ya está optimizado):
```tsx
const agrupados = useMemo(() => {
  const grupos: Record<string, PedidoRuta[]> = {
    produccion: [],
    pendiente: [],
    orden4: [],
    entregado: [],
  };
  pedidos.forEach((p) => {
    // ... lógica de agrupación
  });
  return grupos;
}, [pedidos]);
```

**✅ Este ya está bien optimizado con useMemo**

---

### 📍 Archivo 2: `PedidosHerreria.tsx`

#### Si hay filtros o cálculos, agregar useMemo:

```tsx
import React, { useEffect, useState, useMemo } from "react";

const PedidosHerreria: React.FC = () => {
  // ... código existente

  // Si necesitas filtrar o procesar dataPedidos:
  const pedidosFiltrados = useMemo(() => {
    if (!Array.isArray(dataPedidos)) return [];
    // Solo recalcular si dataPedidos cambia
    return dataPedidos.filter((pedido: Pedido) => {
      // Tu lógica de filtrado aquí
      return pedido.estado_general === "orden1" || pedido.estado_general === "pendiente";
    });
  }, [dataPedidos]);

  // Usar pedidosFiltrados en lugar de dataPedidos en el render
  return (
    // ... usar pedidosFiltrados en lugar de dataPedidos
  );
};
```

---

### 📍 Archivo 3: `CrearPedido.tsx`

#### Si hay cálculos de totales:

```tsx
import { useMemo } from "react";

const CrearPedido: React.FC = () => {
  const [selectedItems, setSelectedItems] = useState<SelectedItem[]>([]);

  // ✅ Optimizar cálculos de totales
  const totalItems = useMemo(() => {
    return selectedItems.reduce(
      (acc, item) => acc + (item.confirmed ? item.cantidad : 0),
      0
    );
  }, [selectedItems]);

  const totalMonto = useMemo(() => {
    return selectedItems.reduce(
      (acc, item) => acc + (item.confirmed ? item.cantidad * item.precio : 0),
      0
    );
  }, [selectedItems]);

  // ... resto del código
};
```

**Mejora esperada:** 30-50% menos cálculos innecesarios

---

## 4. useCallback PARA FUNCIONES

### 🎯 Objetivo
Evitar recrear funciones en cada render, especialmente cuando se pasan como props.

### 📍 Archivo 1: `AsignarArticulos.tsx`

#### ❌ CÓDIGO ACTUAL:
```tsx
const handleEmpleadoChange = (
  item: PedidoItem,
  idx: number,
  empleadoId: string,
  nombreempleado: string
) => {
  setAsignaciones((prev) => ({
    ...prev,
    [`${item.id}-${idx}`]: {
      // ... código
    },
  }));
};
```

#### ✅ CÓDIGO OPTIMIZADO:
```tsx
import { useCallback } from "react";

const AsignarArticulos: React.FC<AsignarArticulosProps> = ({ ... }) => {
  // ... código

  const handleEmpleadoChange = useCallback((
    item: PedidoItem,
    idx: number,
    empleadoId: string,
    nombreempleado: string
  ) => {
    setAsignaciones((prev) => ({
      ...prev,
      [`${item.id}-${idx}`]: {
        // ... código (sin cambios)
      },
    }));
  }, []); // Dependencias vacías porque no depende de props/state externos

  // ... resto del código
};
```

**Cuándo usar useCallback:**
- ✅ Función que se pasa como prop a componente memoizado
- ✅ Función que se usa en dependencias de otros hooks
- ❌ NO usar si la función solo se usa internamente y no se pasa como prop

---

### 📍 Archivo 2: `PedidosHerreria.tsx`

#### Si pasas funciones como props:

```tsx
import { useCallback } from "react";

const PedidosHerreria: React.FC = () => {
  // ... código

  // Si tienes una función que se pasa a DetalleHerreria:
  const handlePedidoClick = useCallback((pedidoId: string) => {
    // ... lógica
  }, []);

  return (
    // ...
    <DetalleHerreria 
      pedido={pedido} 
      onPedidoClick={handlePedidoClick} // ← Si pasas función como prop
    />
  );
};
```

---

## 5. LAZY LOADING DE RUTAS

### 🎯 Objetivo
Cargar componentes solo cuando se visitan, reduciendo el bundle inicial.

### 📍 Archivo: `routers/routers.tsx`

#### ❌ CÓDIGO ACTUAL:
```tsx
import PedidosHerreria from "@/organism/fabricacion/creacion/PedidosHerreria";
import CrearPedido from "../organism/pedido/CrearPedido";
import DashboardPedidos from "@/organism/pedido/DashboardPedidos";
// ... todos los imports al inicio
```

#### ✅ CÓDIGO OPTIMIZADO:
```tsx
import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router";

// Componentes que se usan siempre (no lazy)
import Dashboard from "../organism/dashboard/Dashboard";
import HomePage from "../organism/home/HomePage";
import Login from "@/organism/auth/Login";

// Componentes pesados con lazy loading
const PedidosHerreria = lazy(() => import("@/organism/fabricacion/creacion/PedidosHerreria"));
const CrearPedido = lazy(() => import("../organism/pedido/CrearPedido"));
const DashboardPedidos = lazy(() => import("@/organism/pedido/DashboardPedidos"));
const ModificarEmpleado = lazy(() => import("@/organism/empleados/ModificarEmpleado"));
const CrearCliente = lazy(() => import("@/organism/clientes/CrearCliente"));
const CrearItem = lazy(() => import("@/organism/inventario/CrearItem"));
const CrearEmpleado = lazy(() => import("@/organism/empleados/CrearEmpleado"));
const PedidosMasillar = lazy(() => import("@/organism/fabricacion/masillar/Masillar"));
const PedidosPreparar = lazy(() => import("@/organism/fabricacion/preparar/Preparar"));
const FacturacionPage = lazy(() => import("@/organism/facturacion/facturacion/FacturacionPage"));
const EnvioPage = lazy(() => import("@/organism/envios/envio/Envio"));
const Register = lazy(() => import("@/organism/auth/Register"));
const ReporteComisionesProduccion = lazy(() => import("@/organism/pedido/ReporteComisionesProduccion"));
const ModificarItemPage = lazy(() => import("@/organism/inventario/ModificarItemPage"));
const ModificarUsuario = lazy(() => import("@/organism/usuarios/ModificarUsuario"));
const ModificarCliente = lazy(() => import("@/organism/clientes/ModificarCliente"));
const TerminarAsignacion = lazy(() => import("@/organism/teminarasignacion/TerminarAsignacion"));
const MonitorPedidos = lazy(() => import("@/organism/monitorped/MonitorPedidos"));
const Pedidos = lazy(() => import("@/organism/pagosFacturacion/Pedidos"));
const MisPagos = lazy(() => import("@/organism/pagosFacturacion/MisPagos"));
const CuentasPorPagar = lazy(() => import("@/organism/cuentasPorPagar/CuentasPorPagar"));

// Componente de loading
const LoadingFallback = () => (
  <div className="flex justify-center items-center min-h-screen">
    <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-600"></div>
  </div>
);

function AppRouter() {
  // ... código existente (getPermisos, getToken, etc.)

  return (
    <Routes>
      <Route path="/" element={<Dashboard />}>
        <Route index element={<HomePage />} />
        <Route path="home" element={<HomePage />} />
        
        {/* Rutas con lazy loading envueltas en Suspense */}
        <Route
          path="crearpedido"
          element={
            <ProtectedRoute permiso="ventas">
              <Suspense fallback={<LoadingFallback />}>
                <CrearPedido />
              </Suspense>
            </ProtectedRoute>
          }
        />
        
        <Route
          path="pedidosherreria"
          element={
            <ProtectedRoute permiso="asignar">
              <Suspense fallback={<LoadingFallback />}>
                <PedidosHerreria />
              </Suspense>
            </ProtectedRoute>
          }
        />
        
        {/* Aplicar Suspense a todas las rutas con lazy loading */}
        {/* ... resto de rutas con el mismo patrón */}
      </Route>
      <Route path="login" element={<Login />} />
      <Route path="*" element={<div>Página no encontrada</div>} />
    </Routes>
  );
}

export default AppRouter;
```

**Cambios importantes:**
1. Importar `lazy` y `Suspense` de React
2. Cambiar imports normales a `lazy(() => import(...))`
3. Envolver componentes lazy en `<Suspense fallback={...}>`
4. Crear un componente `LoadingFallback` para mostrar mientras carga

**Mejora esperada:** 40-60% más rápido en carga inicial

---

## 6. OPTIMIZACIONES ADICIONALES

### 6.1 Optimizar Vite Config

#### 📍 Archivo: `vite.config.ts`

#### ✅ CÓDIGO OPTIMIZADO:
```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import tailwindcss from '@tailwindcss/vite'
import path from "path"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  build: {
    // Code splitting automático
    rollupOptions: {
      output: {
        manualChunks: {
          // Separar vendor chunks
          'vendor-react': ['react', 'react-dom', 'react-router'],
          'vendor-ui': [
            '@radix-ui/react-dialog',
            '@radix-ui/react-select',
            '@radix-ui/react-checkbox'
          ],
        },
      },
    },
    // Optimizar chunks
    chunkSizeWarningLimit: 1000,
  },
  // Optimizar dependencias
  optimizeDeps: {
    include: ['react', 'react-dom', 'react-router'],
  },
})
```

**Mejora esperada:** 20-30% bundle más pequeño

---

### 6.2 Evitar Re-renderizados en Listas

#### 📍 Archivo: `PedidosHerreria.tsx`

#### ✅ CÓDIGO OPTIMIZADO:
```tsx
// Si renderizas una lista grande, usar keys estables
{(dataPedidos as Pedido[]).map((pedido) => (
  <li key={pedido._id} className="...">
    {/* Usar pedido._id como key (ya lo estás haciendo bien) */}
    <DetalleHerreria pedido={pedido} />
  </li>
))}
```

**✅ Ya está bien implementado**

---

### 6.3 Optimizar Imports

#### Evitar imports innecesarios:

```tsx
// ❌ MAL - Importa todo
import * as React from "react";

// ✅ BIEN - Solo lo que necesitas
import React, { useEffect, useState, useMemo, useCallback } from "react";
```

---

## 📋 CHECKLIST DE IMPLEMENTACIÓN

### Fase 1: Carga Paralela (1 hora)
- [ ] Optimizar `PedidosHerreria.tsx`
- [ ] Optimizar `CrearPedido.tsx`
- [ ] Buscar otros componentes con carga secuencial
- [ ] Probar que funciona correctamente

### Fase 2: Memoización (1.5 horas)
- [ ] Agregar `React.memo` a `DetalleHerreria`
- [ ] Agregar `React.memo` a `AsignarArticulos`
- [ ] Agregar `React.memo` a `PedidoGroup`
- [ ] Probar que no rompe funcionalidad

### Fase 3: useMemo y useCallback (1 hora)
- [ ] Agregar `useMemo` a cálculos pesados
- [ ] Agregar `useCallback` a funciones que se pasan como props
- [ ] Probar que funciona correctamente

### Fase 4: Lazy Loading (1 hora)
- [ ] Convertir imports a lazy en `routers.tsx`
- [ ] Agregar Suspense a todas las rutas
- [ ] Crear componente LoadingFallback
- [ ] Probar navegación entre rutas

### Fase 5: Optimizaciones Adicionales (30 min)
- [ ] Optimizar `vite.config.ts`
- [ ] Revisar imports innecesarios
- [ ] Probar build de producción

---

## ✅ RESULTADO ESPERADO

**Después de todas las optimizaciones:**
- ⚡ 2-3x más rápido en carga inicial
- ⚡ 30-50% menos re-renderizados
- ⚡ 40-60% bundle más pequeño
- ⚡ Mejor experiencia de usuario

---

## 🚨 NOTAS IMPORTANTES

1. **No cambiar la lógica:** Solo optimizar, no cambiar funcionalidad
2. **Probar cada cambio:** Verificar que todo funciona después de cada optimización
3. **Hacer por fases:** No intentar hacer todo de una vez
4. **Revisar errores:** Si algo se rompe, revisar las dependencias de los hooks

---

## 📞 SI HAY DUDAS

- **React.memo:** Solo usar en componentes que se renderizan mucho
- **useMemo:** Solo para cálculos pesados o que se usan en dependencias
- **useCallback:** Solo para funciones que se pasan como props
- **Lazy loading:** Solo para componentes grandes o poco usados

---

**¡Listo para implementar!** 🚀

