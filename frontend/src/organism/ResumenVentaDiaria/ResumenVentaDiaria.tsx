import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

interface Abono {
  pedido_id: string;
  cliente_nombre?: string;
  fecha: string;
  monto: number;
  metodo?: string;
  descripcion?: string;
  nombre_quien_envia?: string;
}

interface VentaDiariaResponse {
  total_ingresos: number;
  abonos: Abono[];
  ingresos_por_metodo: { [key: string]: number };
}

const ResumenVentaDiaria = () => {
  const [fechaInicio, setFechaInicio] = useState<string>(new Date().toISOString().slice(0, 10));
  const [fechaFin, setFechaFin] = useState<string>(new Date().toISOString().slice(0, 10));
  const [data, setData] = useState<VentaDiariaResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchVentasDiarias = async () => {
    setLoading(true);
    setError(null);
    try {
      const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
      const response = await fetch(
        `${apiUrl}/pedidos/venta-diaria/?fecha_inicio=${fechaInicio}&fecha_fin=${fechaFin}`
      );
      if (!response.ok) {
        throw new Error("Error al obtener los datos de venta diaria");
      }
      const responseData: VentaDiariaResponse = await response.json();
      setData(responseData);
    } catch (error: any) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Resumen de Venta Diaria</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex gap-4 mb-4">
          <Input
            type="date"
            value={fechaInicio}
            onChange={(e) => setFechaInicio(e.target.value)}
          />
          <Input
            type="date"
            value={fechaFin}
            onChange={(e) => setFechaFin(e.target.value)}
          />
          <Button onClick={fetchVentasDiarias} disabled={loading}>
            {loading ? "Buscando..." : "Buscar"}
          </Button>
        </div>
        {error && <p className="text-red-500">{error}</p>}
        {data && (
          <div className="space-y-4">
            <div className="bg-gray-50 p-4 rounded-lg">
              <p className="text-lg font-semibold">
                Total de Ingresos: ${data.total_ingresos.toFixed(2)}
              </p>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID Pedido</TableHead>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Fecha</TableHead>
                  <TableHead>Método</TableHead>
                  <TableHead className="text-right">Monto</TableHead>
                  <TableHead>Nombre del Titular</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.abonos && data.abonos.length > 0 ? (
                  data.abonos.map((abono, index) => (
                    <TableRow key={index}>
                      <TableCell className="font-medium">
                        {abono.pedido_id?.slice(-6) || "-"}
                      </TableCell>
                      <TableCell>{abono.cliente_nombre || "-"}</TableCell>
                      <TableCell>
                        {abono.fecha ? new Date(abono.fecha).toLocaleDateString() : "-"}
                      </TableCell>
                      <TableCell>{abono.metodo || "N/A"}</TableCell>
                      <TableCell className="text-right">
                        ${(abono.monto || 0).toFixed(2)}
                      </TableCell>
                      <TableCell>{abono.nombre_quien_envia || "-"}</TableCell>
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-gray-500">
                      No hay pagos registrados en este rango de fechas
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default ResumenVentaDiaria;