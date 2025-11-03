# Documentación: Estructura de Datos para Adicionales en Facturas

## Resumen del Problema
Los adicionales no se estaban mostrando en los modales de factura ni se estaban sumando al total. Este problema ha sido corregido.

## Estructura de Datos Esperada

### Campo `adicionales` en el Pedido/Factura

El campo `adicionales` debe ser un **array de objetos** con la siguiente estructura:

```json
{
  "adicionales": [
    {
      "descripcion": "Servicio de instalación",
      "precio": 50.00,
      "cantidad": 1
    },
    {
      "descripcion": "Material adicional",
      "precio": 100.00,
      "cantidad": 2
    }
  ]
}
```

### Campos de Cada Adicional

| Campo | Tipo | Requerido | Descripción | Default |
|-------|------|-----------|-------------|---------|
| `descripcion` | string | Opcional | Descripción del adicional | - |
| `precio` | number | **Requerido** | Precio unitario del adicional | 0 |
| `cantidad` | number | Opcional | Cantidad del adicional | 1 |

### Ejemplo Completo

```json
{
  "pedido_id": "12345",
  "items": [
    {
      "codigo": "ITEM001",
      "nombre": "VENTANA PRIMA 1X1",
      "precio": 160.00,
      "cantidad": 1
    }
  ],
  "adicionales": [
    {
      "descripcion": "Instalación",
      "precio": 25.00,
      "cantidad": 1
    },
    {
      "descripcion": "Transporte",
      "precio": 15.00,
      "cantidad": 1
    }
  ],
  "monto_total": 200.00  // items (160) + adicionales (25 + 15)
}
```

## Cálculo del Total

El `monto_total` ahora se calcula así:

```
monto_total = suma(items) + suma(adicionales)

donde:
- suma(items) = Σ(item.precio × item.cantidad)
- suma(adicionales) = Σ(adicional.precio × adicional.cantidad)
```

Si un adicional no tiene `cantidad`, se asume `cantidad = 1`.

## Endpoints que Incluyen Adicionales

Los siguientes endpoints ahora incluyen el campo `adicionales` en sus respuestas:

1. **GET `/facturas/pedido/{pedido_id}`**
   - Incluye `adicionales` en la respuesta
   - El `monto_total` incluye los adicionales

2. **GET `/facturas/cliente/{cliente_id}`**
   - Incluye `adicionales` en cada factura de la lista
   - Usa `transform_factura_to_camelcase` que incluye adicionales

3. **POST `/facturas-confirmadas`**
   - Acepta `adicionales` en el request
   - Calcula automáticamente el `monto_total` incluyendo adicionales si no se proporciona

4. **Creación automática de facturas al crear pedidos de cliente**
   - Incluye `adicionales` del pedido en la factura
   - Calcula el `monto_total` incluyendo adicionales

## Formato de Respuesta (CamelCase)

El backend devuelve los datos en formato camelCase:

```json
{
  "id": "factura_id",
  "pedidoId": "12345",
  "numeroFactura": "FACT-20251103-123456",
  "clienteNombre": "Josue",
  "clienteId": "J-507172554",
  "items": [...],
  "adicionales": [
    {
      "descripcion": "Servicio adicional",
      "precio": 50.00,
      "cantidad": 1
    }
  ],
  "montoTotal": 210.00,
  "montoAbonado": 10.00,
  "saldoPendiente": 200.00
}
```

## Notas para el Frontend

1. **Verificar que el campo existe**: Siempre verificar si `adicionales` existe y es un array antes de iterar:
   ```javascript
   const adicionales = factura.adicionales || [];
   ```

2. **Mostrar adicionales en el modal**: Iterar sobre `adicionales` igual que se hace con `items`:
   ```javascript
   {factura.adicionales?.map((adicional, idx) => (
     <div key={idx}>
       <span>{adicional.descripcion || 'Adicional'}</span>
       <span>Cant: {adicional.cantidad || 1}</span>
       <span>${adicional.precio}</span>
     </div>
   ))}
   ```

3. **El total ya incluye adicionales**: El campo `montoTotal` (o `monto_total`) ya incluye los adicionales calculados, no es necesario sumarlos manualmente en el frontend.

## Cambios Realizados

- ✅ Incluido `adicionales` en el cálculo del `monto_total` al crear facturas
- ✅ Incluido `adicionales` en las respuestas de todos los endpoints de facturas
- ✅ Incluido `adicionales` en la función `transform_factura_to_camelcase`
- ✅ Guardado de `adicionales` en la base de datos cuando se crean facturas

