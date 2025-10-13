import React, { useState } from "react";
import FinalizarSubestado from "@/organism/designar/FinalizarSubestado";
import useTerminarEmpleado from "@/hooks/useTerminarEmpleado";

interface PedidoItem {
  id: string;
  codigo: string;
  nombre: string;
  descripcion: string;
  categoria: string;
  precio: number;
  costo: number;
  cantidad: number;
  activo: boolean;
  costoProduccion: number;
}

interface Empleado {
  identificador: string;
  nombreCompleto?: string;
  permisos: string[];
}

interface AsignacionArticulo {
  key: string;
  empleadoId: string;
  nombreempleado: string;
  fecha_inicio: string;
  estado: string;
  descripcionitem: string;
  costoproduccion: string;
}

interface AsignarArticulosProps {
  items: PedidoItem[];
  empleados: Empleado[];
  pedidoId: string;
  numeroOrden: string;
  estado_general: string;
  nuevo_estado_general: string;
  tipoEmpleado: string[];
}

const AsignarArticulos: React.FC<AsignarArticulosProps> = ({
  items,
  empleados,
  pedidoId,
  numeroOrden,
  estado_general,
  nuevo_estado_general,
  tipoEmpleado,
}) => {
  const [asignaciones, setAsignaciones] = useState<
    Record<string, AsignacionArticulo>
  >({});
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string>("");
  const [asignadosPrevios, setAsignadosPrevios] = useState<Record<string, AsignacionArticulo>>({});
  const [showCambio, setShowCambio] = useState<Record<string, boolean>>({});
  const [showFinalizar, setShowFinalizar] = useState(false);
  // Hook para terminar asignación de artículo
  const [messageTerminar, setMessageTerminar] = useState<string>("");
  const {
    terminarEmpleado,
    loading: loadingTerminar,
    error: errorTerminar,
  } = useTerminarEmpleado({
    onSuccess: () => setMessageTerminar("Artículo terminado correctamente"),
    onError: (err) => setMessageTerminar(err.message || "Error al terminar artículo"),
  });

  // Buscar asignaciones previas al montar
  React.useEffect(() => {
    const fetchPedido = async () => {
      try {
        const apiUrl = import.meta.env.VITE_API_URL || "https://localhost:3000";
        const res = await fetch(`${apiUrl}/pedidos/id/${pedidoId}/`);
        if (!res.ok) return;
        const pedido = await res.json();
        // Buscar asignaciones en TODOS los subestados que estén "en_proceso"
        const prev: Record<string, AsignacionArticulo> = {};
        if (Array.isArray(pedido.seguimiento)) {
          pedido.seguimiento.forEach((s: any) => {
            if (s.estado === "en_proceso" && Array.isArray(s.asignaciones_articulos)) {
              s.asignaciones_articulos.forEach((a: AsignacionArticulo) => {
                prev[a.key] = a;
              });
            }
          });
        }
        setAsignadosPrevios(prev);
      } catch {}
    };
    fetchPedido();
  }, [pedidoId, numeroOrden]);

  // Copia asignaciones previas al estado local si no existen
  React.useEffect(() => {
    if (Object.keys(asignadosPrevios).length > 0) {
      setAsignaciones((prev) => {
        const nuevo = { ...prev };
        Object.entries(asignadosPrevios).forEach(([key, asignacion]) => {
          if (!nuevo[key]) {
            nuevo[key] = { ...asignacion };
          }
        });
        return nuevo;
      });
    }
  }, [asignadosPrevios]);

  const handleEmpleadoChange = (
    item: PedidoItem,
    idx: number,
    empleadoId: string,
    nombreempleado: string
  ) => {
    setAsignaciones((prev) => ({
      ...prev,
      [`${item.id}-${idx}`]: {
        key: `${item.id}-${idx}`,
        empleadoId,
        nombreempleado,
        fecha_inicio: new Date().toISOString(),
        estado: "en_proceso",
        descripcionitem: item.descripcion,
        costoproduccion: String(item.costoProduccion),
      },
    }));
    setShowCambio((prev) => ({ ...prev, [`${item.id}-${idx}`]: false }));
  };

  const handleAsignar = async () => {
    setLoading(true);
    setMessage("");
    const asignacionPorItem = items.map((item, idx) => ({
      itemId: item.id,
      ...asignaciones[`${item.id}-${idx}`],
    }));
    // Detectar si es cambio (ya existe asignación previa)
    const esCambio = Object.keys(asignadosPrevios).length > 0;
    const consulta: any = {
      pedido_id: pedidoId,
      asignaciones: asignacionPorItem,
      numero_orden: numeroOrden,
      estado: "en_proceso",
      estado_general: estado_general,
    };
    if (!esCambio) {
      consulta.tipo_fecha = "inicio";
    } else {
      consulta.tipo_fecha = "";
    }
    try {
      const apiUrl = import.meta.env.VITE_API_URL || "https://localhost:3000";
      const res = await fetch(`${apiUrl}/pedidos/subestados/`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(consulta),
      });
      console.log("Respuesta de /pruebaapi1:", res);
      setMessage("Asignación enviada correctamente");
      const result = await res.json();
      console.log("Respuesta de /pruebaapi1:", result);
    } catch (err) {
      setMessage("Error al enviar la asignación");
      console.error("Error al enviar a /pruebaapi1:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-4">
      <h4 className="font-semibold mb-2">Asignar empleados por artículo:</h4>
      <ul className="space-y-4">
        {items.map((item, idx) => {
          const key = `${item.id}-${idx}`;
          const asignacion = asignaciones[key] || {};
          const asignadoPrevio = asignadosPrevios[key];
          const cambioActivo = showCambio[key];
          return (
            <li key={key} className="flex flex-col gap-2 border rounded p-3">
              <span className="font-medium">{item.nombre}</span>
              {asignadoPrevio && !cambioActivo ? (
                <div className="flex flex-col gap-2">
                  <span className="text-blue-700 text-sm font-semibold">
                    Ya asignado a: {asignadoPrevio.nombreempleado}
                  </span>
                  <div className="flex flex-row gap-4 w-full justify-center p-4">

                  <button
                    type="button"
                    className="bg-yellow-500 text-white px-2 py-1 rounded shadow hover:bg-yellow-600 w-fit"
                    onClick={() => setShowCambio((prev) => ({ ...prev, [key]: true }))}
                  >
                    Cambiar asignación
                  </button>
                  {/* Botón para terminar asignación de este artículo */}
                  <button
                    type="button"
                    className="bg-red-600 text-white px-2 py-1 rounded shadow hover:bg-red-700 w-fit mt-1"
                    disabled={loadingTerminar}
                    onClick={async () => {
                      await terminarEmpleado({
                        pedido_id: pedidoId,
                        item_id: item.id,
                        empleado_id: asignadoPrevio.empleadoId,
                        estado: "terminado",
                        fecha_fin: new Date().toISOString(),
                        orden: numeroOrden,
                      });
                    }}
                  >
                    {loadingTerminar ? "Terminando..." : "Terminar asignación"}
                  </button>
                  </div>
                </div>
              ) : (
                <div className="flex gap-4 items-center">
                  <select
                    className="border rounded px-2 py-1"
                    value={asignacion.empleadoId || ""}
                    onChange={(e) => {
                      const empleadoId = e.target.value;
                      const empleado = empleados.find(
                        (emp) => emp.identificador === empleadoId
                      );
                      handleEmpleadoChange(
                        item,
                        idx,
                        empleadoId,
                        empleado?.nombreCompleto || empleadoId
                      );
                    }}
                  >
                    <option value="">Seleccionar empleado</option>
                    {empleados
                      .filter(
                        (e) =>
                          Array.isArray(e.permisos) &&
                          (
                            Array.isArray(tipoEmpleado)
                              ? tipoEmpleado.some((tipo) => e.permisos.includes(tipo))
                              : e.permisos.includes(tipoEmpleado)
                          )
                      )
                      .map((empleado) => (
                        <option
                          key={empleado.identificador}
                          value={empleado.identificador}
                        >
                          {empleado.nombreCompleto || empleado.identificador}
                        </option>
                      ))}
                  </select>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <button
        type="button"
        className="bg-blue-600 text-white px-4 py-2 rounded shadow hover:bg-blue-700 mt-4"
        onClick={handleAsignar}
        disabled={loading}
      >
        Asignar empleados
      </button>
      <button
        type="button"
        className="bg-green-600 text-white px-4 py-2 rounded shadow hover:bg-green-700 mt-4 ml-2"
        onClick={() => setShowFinalizar(true)}
      >
        Finalizar pedido
      </button>
      {showFinalizar && (
        <FinalizarSubestado
          pedidoId={pedidoId}
          numeroOrden={numeroOrden}
          estadoGeneralActual={estado_general}
          nuevoEstadoGeneral={nuevo_estado_general}
          onFinalizado={() => setShowFinalizar(false)}
        />
      )}
      {message && (
        <div className="mt-2 text-green-600 font-semibold">{message}</div>
      )}
      {messageTerminar && (
        <div className="mt-2 text-green-600 font-semibold">{messageTerminar}</div>
      )}
      {errorTerminar && (
        <div className="mt-2 text-red-600 font-semibold">{errorTerminar}</div>
      )}
    </div>
  );
};

export default AsignarArticulos;
