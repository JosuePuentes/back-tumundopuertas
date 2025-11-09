import React, { useEffect, useState, useMemo } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

// --- INTERFACES Y TIPOS (Sin cambios) ---
interface AsignacionArticulo {
  itemId: string;
  key: string;
  empleadoId: string;
  nombreempleado: string;
  fecha_inicio: string;
  estado: string;
  descripcionitem: string;
  costoproduccion: string;
}

type PedidoRuta = {
  _id: string;
  cliente_id: string;
  cliente_nombre: string;
  fecha_creacion: string;
  fecha_actualizacion: string;
  estado_general: string;
  creado_por?: string;
  items: PedidoItem[];
  seguimiento: Array<{
    orden: number;
    nombre_subestado: string;
    estado: string;
    fecha_inicio?: string;
    fecha_fin?: string;
    asignaciones_articulos?: AsignacionArticulo[] | null;
  }>;
};

type PedidoItem = {
  id: string;
  codigo: string;
  nombre: string;
  descripcion: string;
  categoria: string;
  precio: number;
  costo: number;
  costoProduccion: number;
  cantidad: number;
  activo: boolean;
  detalleitem?: string;
};

// --- CONSTANTES (Sin cambios) ---
const ORDEN_LABELS: Record<string, string> = {
  orden1: "Herrería",
  orden2: "Masillar",
  orden3: "Preparar",
  orden4: "Facturación",
  orden5: "Envíos",
};

const ESTADOS_SECCIONES = [
  { key: "pendiente", label: "Pendientes" },
  { key: "produccion", label: "En Producción" },
  { key: "orden4", label: "Facturación" },
  { key: "entregado", label: "Envíos" },
];

// --- COMPONENTES SECUNDARIOS ---

const TimeTracker: React.FC<{ inicio?: string; fin?: string; now: number }> = ({ inicio, fin, now }) => {
  if (!inicio) {
    return <span className="text-sm text-gray-400 italic">-</span>;
  }

  const startTime = new Date(inicio).getTime();
  const endTime = fin ? new Date(fin).getTime() : now;
  const diffMs = Math.max(0, endTime - startTime);

  const hours = Math.floor(diffMs / 3600000);
  const minutes = Math.floor((diffMs % 3600000) / 60000);
  const seconds = Math.floor((diffMs % 60000) / 1000);

  return (
    <span className="font-mono text-sm md:text-base font-semibold text-gray-700">
      {hours.toString().padStart(2, "0")}:
      {minutes.toString().padStart(2, "0")}:
      {seconds.toString().padStart(2, "0")}
    </span>
  );
};

const PedidoRow: React.FC<{ pedido: PedidoRuta; now: number; isProduccion: boolean }> = ({ pedido, now, isProduccion }) => {
  const ordenActual = Number(pedido.estado_general.replace("orden", ""));
  const subestadoActual = pedido.seguimiento?.find((s) => Number(s.orden) === ordenActual);

  const nombresAsignados = useMemo(() => {
    if (!subestadoActual?.asignaciones_articulos) return [];
    const nombres = subestadoActual.asignaciones_articulos.map((a) => a.nombreempleado);
    return [...new Set(nombres.filter(Boolean))];
  }, [subestadoActual]);

  const getItemStatus = (itemId: string): string => {
    const asignacion = subestadoActual?.asignaciones_articulos?.find((a) => a.itemId === itemId);
    return asignacion?.estado || "Sin estado";
  };

  return (
    <tr className="border-b border-gray-200 hover:bg-gray-50 transition">
      <td className="p-3 font-bold text-gray-900 whitespace-nowrap">#{pedido._id.slice(-4)}</td>
      <td className="p-3 text-gray-700">{pedido.cliente_nombre}</td>
      <td className="p-3 text-gray-500">{pedido.cliente_id}</td>
      <td className="p-3 text-gray-600">{new Date(pedido.fecha_creacion).toLocaleDateString()}</td>
      <td className="p-3 text-gray-600">{pedido.creado_por || "-"}</td>
      <td className="p-3">
        <ul className="flex flex-col gap-2">
          {pedido.items.map((item) => {
            const status = getItemStatus(item.id);
            return (
              <li
                key={item.id}
                className="flex items-center gap-2 flex-wrap p-2 bg-gray-100 rounded-lg border border-gray-200"
              >
                <span className="font-semibold text-gray-800">{item.nombre}</span>
                <Badge variant="outline" className="bg-white border-gray-300">x{item.cantidad}</Badge>
                <Badge
                  variant="secondary"
                  className={
                    status === "terminado"
                      ? "bg-green-100 text-green-700 border-green-300"
                      : status === "en_proceso"
                      ? "bg-yellow-100 text-yellow-700 border-yellow-300"
                      : "bg-blue-100 text-blue-700 border-blue-300"
                  }
                >
                  {status}
                </Badge>
                {item.detalleitem && <span className="text-sm text-gray-600 italic">({item.detalleitem})</span>}
                {item.categoria && (
                  <Badge variant="default" className="bg-gray-800 text-white">
                    {item.categoria}
                  </Badge>
                )}
              </li>
            );
          })}
        </ul>
      </td>
      <td className="p-3">
        <Badge variant="secondary" className="bg-indigo-100 text-indigo-700 border border-indigo-200 font-semibold">
          {ORDEN_LABELS[pedido.estado_general] || pedido.estado_general}
        </Badge>
      </td>
      <td className="p-3">
        {nombresAsignados.length > 0 ? (
          <div className="flex flex-col gap-1">
            {nombresAsignados.map((nombre) => (
              <span key={nombre} className="text-sm text-gray-700">
                {nombre}
              </span>
            ))}
          </div>
        ) : (
          <span className="text-sm text-gray-400">-</span>
        )}
      </td>
      <td className="p-3">
        {isProduccion && <TimeTracker inicio={subestadoActual?.fecha_inicio} fin={subestadoActual?.fecha_fin} now={now} />}
      </td>
    </tr>
  );
};

const PedidoGroup: React.FC<{ title: string; pedidos: PedidoRuta[]; now: number }> = ({ title, pedidos, now }) => (
  <Card className="overflow-hidden border-gray-200 shadow-lg rounded-2xl">
    <CardHeader className="bg-gray-50 border-b border-gray-200 px-6 py-4">
      <CardTitle className="flex items-center gap-3 text-lg font-bold text-gray-900">
        {title}
        <Badge variant="default" className="bg-gray-900 text-white">
          {pedidos?.length || 0}
        </Badge>
      </CardTitle>
    </CardHeader>
    <CardContent className="p-0">
      {pedidos && pedidos.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left border-collapse">
            <thead className="bg-gray-100 text-xs text-gray-600 uppercase tracking-wide">
              <tr>
                <th className="p-3 font-semibold">Pedido</th>
                <th className="p-3 font-semibold">Cliente</th>
                <th className="p-3 font-semibold">ID</th>
                <th className="p-3 font-semibold">Fecha</th>
                <th className="p-3 font-semibold">Creado por</th>
                <th className="p-3 font-semibold">Items</th>
                <th className="p-3 font-semibold">Estado Actual</th>
                <th className="p-3 font-semibold">Asignado a</th>
                <th className="p-3 font-semibold">Tiempo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {pedidos.map((pedido) => (
                <PedidoRow key={pedido._id} pedido={pedido} now={now} isProduccion={title === "En Producción"} />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="p-6 text-center text-gray-500 italic">No hay pedidos en esta sección.</p>
      )}
    </CardContent>
  </Card>
);

const DashboardPedidos: React.FC = () => {
  const [pedidos, setPedidos] = useState<PedidoRuta[]>([]);
  const [now, setNow] = useState(Date.now());
      const apiUrl = import.meta.env.VITE_API_URL || "https://localhost:3000";
      const fetchPedidos = () => {
    fetch(`${apiUrl}/pedidos/produccion/ruta`)
      .then((res) => res.json())
      .then((data) => setPedidos(data))
      .catch((err) => {
        // Solo mostrar errores críticos en producción
        if (!import.meta.env.PROD) {
          console.error(err);
        }
      });
  };

  useEffect(() => {
    fetchPedidos();
    const reloadInterval = setInterval(fetchPedidos, 60_000);
    return () => clearInterval(reloadInterval);
  }, []);

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, []);

  const agrupados = useMemo(() => {
    const grupos: Record<string, PedidoRuta[]> = {
      produccion: [],
      pendiente: [],
      orden4: [],
      entregado: [],
    };
    pedidos.forEach((p) => {
      if (["orden1", "orden2", "orden3"].includes(p.estado_general)) {
        grupos.produccion.push(p);
      } else if (p.estado_general === "orden4") {
        grupos.orden4.push(p);
      } else if (p.estado_general === "pendiente") {
        grupos.pendiente.push(p);
      } else if (p.estado_general === "orden5") {
        grupos.entregado.push(p);
      }
    });
    return grupos;
  }, [pedidos]);

  return (
    <div className="container mx-auto p-4 md:p-8 space-y-8">
      {ESTADOS_SECCIONES.map(({ key, label }) => (
        <PedidoGroup key={key} title={label} pedidos={agrupados[key]} now={now} />
      ))}
    </div>
  );
};

export default DashboardPedidos;