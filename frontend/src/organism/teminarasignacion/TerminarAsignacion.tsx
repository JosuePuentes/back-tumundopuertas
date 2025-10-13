import React, { useEffect, useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import useTerminarEmpleado from "@/hooks/useTerminarEmpleado";
import ImageDisplay from "@/upfile/ImageDisplay";
interface Asignacion {
  pedido_id: string;
  item_id: string;
  descripcionitem: string;
  costoproduccion: string;
  estado: string;
  orden?: string;
  fecha_inicio?: string;
  fecha_fin?: string;
  nombreempleado?: string;
  estado_subestado?: string;
  detalleitem?: string;
  cliente_id?: string;
  imagenes?: string[];
  cliente: {
    cliente_nombre?: string;
    cliente_direccion?: string;
    cliente_telefono?: string;
    cliente_email?: string;
  };
}

const TerminarAsignacion: React.FC = () => {
  const [asignaciones, setAsignaciones] = useState<Asignacion[]>([]);
  const [loading, setLoading] = useState(false);
  const identificador = localStorage.getItem("identificador");
  const apiUrl = import.meta.env.VITE_API_URL || "https://localhost:8002";

  const { terminarEmpleado } = useTerminarEmpleado()

  useEffect(() => {
    const fetchAsignaciones = async () => {
      setLoading(true);
      try {
        // Consulta todos los pedidos y extrae asignaciones en proceso para el usuario logueado
        const res = await fetch(`${apiUrl}/pedidos/`);
        const pedidos = await res.json();
        
        // Extraer todas las asignaciones en proceso del empleado actual
        const asignacionesEmpleado: any[] = [];
        pedidos.forEach((pedido: any) => {
          if (Array.isArray(pedido.seguimiento)) {
            pedido.seguimiento.forEach((subestado: any) => {
              if (subestado.estado === "en_proceso" && Array.isArray(subestado.asignaciones_articulos)) {
                subestado.asignaciones_articulos.forEach((asignacion: any) => {
                  if (asignacion.empleadoId === identificador) {
                    asignacionesEmpleado.push({
                      ...asignacion,
                      pedido_id: pedido._id,
                      cliente: pedido.cliente,
                      imagenes: pedido.imagenes,
                      estado_subestado: subestado.estado,
                      orden: subestado.orden
                    });
                  }
                });
              }
            });
          }
        });
        
        setAsignaciones(asignacionesEmpleado);
      } catch (err) {}
      setLoading(false);
    };
    if (identificador) fetchAsignaciones();
  }, [identificador, apiUrl]);

  if (loading) return <div>Cargando asignaciones...</div>;
  console.log(asignaciones.forEach((a) => console.log(a.cliente.cliente_nombre)));
  document.querySelectorAll('input[type="number"].no-mouse-wheel');
  return (
    <div className="max-w-3xl mx-auto mt-8">
      <h2 className="text-2xl font-bold mb-6">Asignaciones en proceso</h2>
      {asignaciones.length === 0 ? (
        <div className="text-gray-500">No tienes asignaciones en proceso.</div>
      ) : (
        <ul className="space-y-6">
          {asignaciones
            .filter((asig) => asig.estado_subestado === "en_proceso")
            .map((asig, idx) => (
              <li key={idx}>
                <Card className="border border-gray-200 shadow-sm">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-lg font-semibold text-primary">
                      Pedido #{asig.pedido_id?.slice(-4) || asig.pedido_id}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {/* Mostrar imágenes si existen */}
                    {Array.isArray(asig.imagenes) && asig.imagenes.length > 0 && (
                      <div className="flex gap-2 mb-2 flex-wrap">
                        {asig.imagenes.slice(0, 3).map((img, imgIdx) => (
                          <ImageDisplay
                            key={imgIdx}
                            imageName={img}
                            alt={`Imagen ${imgIdx + 1}`}
                            style={{ maxWidth: 70, maxHeight: 70, borderRadius: 8, border: '1px solid #ddd' }}
                          />
                        ))}
                      </div>
                    )}
                    <div className="font-bold text-gray-900">Descripción:</div>
                    <div className="text-gray-700 mb-2">
                      {asig.descripcionitem}
                    </div>
                    {asig.detalleitem && (
                      <div className="text-green-600 mb-2">
                        <span className="font-bold">Detalle:</span>{" "}
                        <span className="font-normal">{asig.detalleitem}</span>
                      </div>
                    )}
                    <div className="pt-2">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-1">
                        {asig.cliente.cliente_nombre && (
                          <div>
                            <span className="font-semibold">
                              Cliente:
                            </span>{" "}
                            {asig.cliente.cliente_nombre}
                          </div>
                        )}
                        {asig.cliente_id && (
                          <div>
                            <span className="font-semibold">ID Cliente:</span>{" "}
                            {asig.cliente_id}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="pt-4">
                      <button
                        onClick={async () => {
                          await terminarEmpleado({
                            orden: asig.orden,
                            pedido_id: asig.pedido_id,
                            item_id: asig.item_id,
                            empleado_id: identificador,
                            estado: "terminado",
                            fecha_fin: new Date().toISOString(),
                          });
                          window.location.reload();
                        }}
                        className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 transition"
                      >
                        Marcar como Terminado
                      </button>
                    </div>
                  </CardContent>
                </Card>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
};

export default TerminarAsignacion;
