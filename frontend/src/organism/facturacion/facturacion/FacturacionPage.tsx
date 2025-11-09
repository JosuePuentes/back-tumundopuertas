import React, { useEffect, useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import DetalleFacturacion from "./DetalleFacturacion";
import AsignarArticulos from "@/organism/asignar/AsignarArticulos";
import { useEmpleado } from "@/hooks/useEmpleado";

const FacturacionPage: React.FC = () => {
  const [facturacion, setFacturacion] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const { dataEmpleados, fetchEmpleado } = useEmpleado();

  const fetchPedidosFacturacion = async () => {
    setLoading(true);
    setError("");
    try {
      const apiUrl = import.meta.env.VITE_API_URL || "https://localhost:3000";
      const res = await fetch(
        `${apiUrl}/pedidos/estado/?estado_general=orden4`
      );
      if (!res.ok) throw new Error("Error al obtener pedidos");
      const pedidos = await res.json();
      setFacturacion(pedidos);
    } catch (err: any) {
      setError(err.message || "Error desconocido");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Carga paralela: ambas peticiones se ejecutan simultáneamente
    const apiUrl = import.meta.env.VITE_API_URL || "https://localhost:3000";
    Promise.all([
      fetchPedidosFacturacion().catch(() => {
        // Error silencioso, se maneja en el estado
        return null;
      }),
      fetchEmpleado(`${apiUrl}/empleados/all/`).catch(() => {
        // Error silencioso, se maneja en el hook
        return null;
      })
    ]);
  }, []);

  return (
    <Card className="max-w-3xl mx-auto mt-8">
      <CardHeader>
        <CardTitle>Pedidos en Facturación</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex justify-center items-center py-8">
            <span className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-600 mr-2"></span>
            <span className="text-blue-600 font-semibold">
              Cargando pedidos...
            </span>
          </div>
        ) : error ? (
          <div className="text-red-600 font-semibold py-4">{error}</div>
        ) : facturacion.length === 0 ? (
          <p className="text-gray-500">No hay pedidos en facturación.</p>
        ) : (
          <ul className="space-y-8">
            {facturacion.map((pedido: any) => (
              <li
                key={pedido._id}
                className="border rounded-xl bg-white shadow p-4 transition-all duration-300 hover:shadow-lg"
              >
                <DetalleFacturacion pedido={pedido} />
                <div className="mt-4">
                  <AsignarArticulos
                    estado_general={"orden4"}
                    nuevo_estado_general="orden5"
                    numeroOrden="4"
                    items={pedido.items.map((item: any) => ({
                      id: item.id,
                      codigo: item.codigo,
                      nombre: item.nombre,
                      descripcion: item.descripcion,
                      categoria: item.categoria,
                      precio: item.precio,
                      costo: item.costo,
                      cantidad: item.cantidad,
                      activo: item.activo,
                      costoProduccion: item.costo, // Si tienes un campo específico, cámbialo aquí
                      detalleitem: item.detalleitem || "", // Asegúrate de mapear el nuevo campo
                      imagenes: item.imagenes || [], // Asegúrate de mapear el nuevo campo
                    }))}
                    empleados={Array.isArray(dataEmpleados) ? dataEmpleados : []}
                    pedidoId={pedido._id}
                    tipoEmpleado={["facturacion"]}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
};

export default FacturacionPage;
