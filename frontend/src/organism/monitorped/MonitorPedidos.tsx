import React, { useEffect, useState, useMemo, useCallback } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";

interface Pedido {
  _id: string;
  cliente_nombre: string;
  estado_general: string;
  fecha_creacion?: string;
  items?: Array<{
    nombre: string;
    descripcion: string;
    cantidad: number;
    costoProduccion?: string;
  }>;
}

const MonitorPedidos: React.FC = () => {
  const [pedidos, setPedidos] = useState<Pedido[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [fechaInicio, setFechaInicio] = useState<string>("");
  const [fechaFin, setFechaFin] = useState<string>("");
  const [shouldSearch, setShouldSearch] = useState(false);
  const apiUrl = import.meta.env.VITE_API_URL || "https://localhost:8002";

  const ordenMap: Record<string, string> = {
    orden1: "Herreria",
    orden2: "Masillar/Pintar",
    orden3: "Manillar",
    orden4: "Facturación",
    orden5: "Envío",
    orden6: "Completados",
    cancelado: "Cancelado",
  };

  const [ordenFilter, setOrdenFilter] = useState<string>("");
  const [estadoSeleccionado, setEstadoSeleccionado] = useState<Record<string, string>>({});
  const [actualizando, setActualizando] = useState<string>("");

  // Función memoizada para cargar pedidos
  const fetchPedidos = useCallback(async () => {
    setLoading(true);
    try {
      let url: string;
      
      // Si hay fechas, usar el endpoint de filtrado por fecha
      if (fechaInicio && fechaFin) {
        url = `${apiUrl}/pedidos/filtrar/por-fecha/?fecha_inicio=${fechaInicio}&fecha_fin=${fechaFin}`;
      } else {
        // Si no hay fechas, usar el endpoint /all/ que retorna todos los pedidos ordenados por fecha
        url = `${apiUrl}/pedidos/all/?limite=1000`;
      }
      
      console.log("🔍 Cargando pedidos desde:", url);
      const res = await fetch(url);
      
      if (!res.ok) {
        throw new Error(`Error al cargar pedidos: ${res.status} ${res.statusText}`);
      }
      
      const data = await res.json();
      const pedidosArray = Array.isArray(data) ? data : (data.pedidos || []);
      
      console.log("✅ Pedidos recibidos:", pedidosArray.length);
      setPedidos(pedidosArray);
    } catch (error) {
      console.error("❌ Error al cargar pedidos:", error);
      setPedidos([]);
    } finally {
      setLoading(false);
      setShouldSearch(false);
    }
  }, [apiUrl, fechaInicio, fechaFin]);

  // Carga inicial automática
  useEffect(() => {
    fetchPedidos();
  }, []);

  // Carga cuando se activa shouldSearch
  useEffect(() => {
    if (shouldSearch) {
      fetchPedidos();
    }
  }, [shouldSearch, fetchPedidos]);

  const handleActualizarEstado = useCallback(async (pedidoId: string) => {
    if (!estadoSeleccionado[pedidoId]) return;
    setActualizando(pedidoId);
    try {
      const res = await fetch(`${apiUrl}/pedidos/actualizar-estado-general/`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pedido_id: pedidoId, nuevo_estado_general: estadoSeleccionado[pedidoId] }),
      });
      if (!res.ok) throw new Error("Error actualizando estado");
      // Actualizar localmente el estado
      setPedidos((prev) => prev.map((p) => p._id === pedidoId ? { ...p, estado_general: estadoSeleccionado[pedidoId] } : p));
    } catch {}
    setActualizando("");
  }, [apiUrl, estadoSeleccionado]);

  // Memoizar pedidos filtrados para evitar recalcular en cada render
  const pedidosFiltrados = useMemo(() => {
    return pedidos.filter(
      (p) =>
        (ordenFilter === "" || p.estado_general === ordenFilter) &&
        ((p.cliente_nombre?.toLowerCase?.().includes(search.toLowerCase()) || "") ||
          (p.estado_general?.toLowerCase?.().includes(search.toLowerCase()) || "") ||
          (p._id?.includes(search) || ""))
    );
  }, [pedidos, ordenFilter, search]);

  return (
    <div className="max-w-4xl mx-auto mt-8">
      <h2 className="text-2xl font-bold mb-6">Monitor de Pedidos</h2>
      <div className="flex gap-4 mb-6">
        <Input
          placeholder="Buscar por cliente, estado o ID..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-1/3"
        />
        <Input
          type="date"
          value={fechaInicio}
          onChange={(e) => setFechaInicio(e.target.value)}
          className="w-1/6"
        />
        <Input
          type="date"
          value={fechaFin}
          onChange={(e) => setFechaFin(e.target.value)}
          className="w-1/6"
        />
        <button
          className="bg-blue-600 text-white px-4 py-2 rounded shadow hover:bg-blue-700"
          onClick={() => setShouldSearch(true)}
        >
          Buscar
        </button>
      </div>
        <select
          className="border rounded px-2 py-1 w-1/3 mb-4"
          value={ordenFilter}
          onChange={(e) => setOrdenFilter(e.target.value)}
        >
          <option value="">Todos los estados</option>
          {Object.entries(ordenMap).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
      {loading ? (
        <div>Cargando pedidos...</div>
      ) : pedidosFiltrados.length === 0 ? (
        <div className="text-gray-500">No hay pedidos para mostrar.</div>
      ) : (
        <ul className="space-y-4">
          {pedidosFiltrados.map((pedido) => (
            <li key={pedido._id}>
              <Card>
                <CardHeader>
                  <CardTitle>
                    Pedido: {pedido._id}
                    <Badge variant="secondary" className="ml-2">
                      {pedido.estado_general}
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="mb-2 text-base font-bold text-gray-900">
                    Cliente: <span className="font-normal text-gray-700">{pedido.cliente_nombre}</span>
                  </div>
                  <div className="mb-2 text-base font-bold text-blue-700">
                    Estado general: <span className="font-normal text-blue-900">{ordenMap[pedido.estado_general] || pedido.estado_general}</span>
                  </div>
                  {pedido.fecha_creacion && (
                    <div className="text-base text-gray-700">
                      Fecha: {new Date(pedido.fecha_creacion).toLocaleDateString()}
                    </div>
                  )}
                  {Array.isArray(pedido.items) && pedido.items.length > 0 && (
                    <div className="mt-2">
                      <div className="font-semibold mb-1">Items:</div>
                      <ul className="list-disc ml-6">
                        {pedido.items.map((item, idx) => (
                          <li key={idx} className="mb-1">
                            <span className="font-bold">{item.nombre}</span> - {item.descripcion} <span className="text-gray-600">x{item.cantidad}</span>
                            {item.costoProduccion && (
                              <span className="ml-2 text-green-700 font-semibold">${item.costoProduccion}</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </CardContent>
                <div className="px-6 pb-4 flex flex-col gap-2">
                  <Select
                    value={estadoSeleccionado[pedido._id] || ""}
                    onValueChange={(val) => setEstadoSeleccionado((prev) => ({ ...prev, [pedido._id]: val }))}
                  >
                    <SelectTrigger className="w-full max-w-xs" aria-label="Seleccionar estado">
                      <SelectValue placeholder="Selecciona nuevo estado" />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(ordenMap).map(([key, label]) => (
                        <SelectItem key={key} value={key}>{label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button
                    variant="outline"
                    className="w-full max-w-xs bg-black text-white border-black hover:bg-gray-900 hover:text-white"
                    disabled={!estadoSeleccionado[pedido._id] || actualizando === pedido._id}
                    onClick={() => handleActualizarEstado(pedido._id)}
                  >
                    {actualizando === pedido._id ? "Actualizando..." : "Cambiar Estado"}
                  </Button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default MonitorPedidos;
