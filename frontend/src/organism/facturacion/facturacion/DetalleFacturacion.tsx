import React from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import NotaEntrega from "@/organism/formatosImpresion/NotaEntrega";
import ImageDisplay from "@/upfile/ImageDisplay";

interface PedidoItem {
  codigo: string;
  nombre: string;
  descripcion: string;
  categoria: string;
  precio: number;
  costo: number;
  cantidad: number;
  activo: boolean;
  detalleitem?: string;
  imagenes?: string[];
}

interface PedidoSeguimiento {
  orden: number;
  nombre_subestado: string;
  estado: string;
  asignado_a?: string;
  fecha_inicio?: string;
  fecha_fin?: string;
  notas?: string;
}

interface Pedido {
  _id: string;
  cliente_id: string;
  fecha_creacion: string;
  fecha_actualizacion: string;
  estado_general: string;
  items: PedidoItem[];
  seguimiento: PedidoSeguimiento[];
}

interface DetalleFacturacionProps {
  pedido: Pedido;
}

const DetalleFacturacion: React.FC<DetalleFacturacionProps> = ({ pedido }) => {
  return (
    <Card className="mb-4">
      <CardHeader className="flex flex-row items-center justify-between">
  <CardTitle>Detalle del Pedido {pedido._id}</CardTitle>
  {/* Botón de cerrar eliminado */}
      </CardHeader>
      <CardContent>
        <div className="mb-4 grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
          <div className="flex flex-col gap-2">
            <span className="font-semibold text-gray-700">Cliente</span>
            <span className="text-lg font-bold text-blue-700">{pedido.cliente_id}</span>
          </div>
          <div className="flex flex-row gap-4 items-center justify-end md:justify-start">
            <div className="flex flex-col items-center">
              <span className="text-xs text-gray-500">Creado</span>
              <span className="font-semibold text-green-700">{new Date(pedido.fecha_creacion).toLocaleDateString()}</span>
            </div>
            {pedido.fecha_actualizacion && (
              <div className="flex flex-col items-center">
                <span className="text-xs text-gray-500">Actualizado</span>
                <span className="font-semibold text-blue-700">{new Date(pedido.fecha_actualizacion).toLocaleDateString()}</span>
              </div>
            )}
            <div className="flex flex-col items-center">
              <span className="text-xs text-gray-500">Estado</span>
              <Badge variant="secondary" className="text-base px-3 py-1 rounded-full bg-blue-600 text-white font-bold shadow">{pedido.estado_general === "orden4" ? "Facturación" : pedido.estado_general}</Badge>
            </div>
          </div>
        </div>
        <div className="mb-2">
          <span className="font-semibold text-lg">Artículos del Pedido:</span>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
            {pedido.items.map((item: any, idx: number) => (
              <div
                key={idx}
                className="bg-white border border-blue-200 rounded-xl shadow p-4 flex flex-col gap-2 hover:shadow-lg transition-all"
              >
                <div className="flex items-center justify-between">
                  <span className="font-bold text-blue-700 text-base">{item.descripcion ?? item.nombre ?? `ID: ${item.itemId}`}</span>
                  <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs font-semibold">x{item.cantidad}</span>
                </div>
                {/* Mostrar imágenes si existen */}
                {item.imagenes && item.imagenes.length > 0 && (
                  <div className="flex flex-row gap-2 mt-2">
                    {item.imagenes.map((img: string, imgIdx: number) => (
                      <ImageDisplay
                        key={imgIdx}
                        imageName={img}
                        alt={`Imagen ${imgIdx + 1} de ${item.nombre}`}
                        style={{
                          maxWidth: 80,
                          maxHeight: 80,
                          borderRadius: 8,
                          border: "1px solid #ddd",
                          cursor: "pointer",
                        }}
                      />
                    ))}
                  </div>
                )}
                <div className="flex flex-row gap-4 mt-2">
                  <div className="flex flex-col">
                    <span className="text-xs text-gray-500">Costo</span>
                    <span className="font-semibold text-green-700">${item.costo ?? "-"}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-xs text-gray-500">Precio</span>
                    <span className="font-semibold text-blue-700">${item.precio ?? "-"}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="mt-8">
          <NotaEntrega pedido={pedido} />
        </div>
      </CardContent>
    </Card>
  );
};

export default DetalleFacturacion;
