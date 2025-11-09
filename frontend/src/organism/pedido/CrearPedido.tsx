import { useRef, useState, useEffect } from "react";
import {
  FaPlus,
  FaClipboardList,
  FaSearch,
  FaTrashRestore,
} from "react-icons/fa";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { usePedido } from "@/hooks/usePedido";
import { useClientes } from "@/hooks/useClientes";
import { useItems } from "@/hooks/useItems";
import ImageDisplay from "@/upfile/ImageDisplay";

// Tipos locales para el payload
interface PedidoItem {
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
}

interface PedidoSeguimiento {
  orden: number;
  nombre_subestado: string;
  estado: string;
  asignado_a?: string | null;
  fecha_inicio?: string | null;
  fecha_fin?: string | null;
  notas?: string;
}

interface PedidoPayload {
  cliente_id: string;
  cliente_nombre: string;
  fecha_creacion: string;
  fecha_actualizacion: string;
  estado_general: string;
  creado_por?: string;
  items: PedidoItem[];
  seguimiento: PedidoSeguimiento[];
}

type SelectedItem = {
  itemId: string;
  codigo: string; // Added
  nombre: string;
  descripcion: string;
  departamento?: string;
  marca?: string;
  categoria: string;
  precio: number;
  costo: number;
  costoProduccion: number;
  cantidad: number;
  existencia: number;
  activo: boolean;
  detalleitem?: string;
  showSuggestions?: boolean;
  confirmed?: boolean;
  imagenes?: string[];
  search?: string;
};

const CrearPedido: React.FC = () => {
  const [clienteId, setClienteId] = useState<number>(0);
  const [clienteSearch, setClienteSearch] = useState<string>("");
  const [showClienteSuggestions, setShowClienteSuggestions] =
    useState<boolean>(false);
  const [fecha, setFecha] = useState<string>(
    new Date().toISOString().slice(0, 10)
  );
  const [selectedItems, setSelectedItems] = useState<SelectedItem[]>([]);
  const [mensaje, setMensaje] = useState<string>("");
  const [mensajeTipo, setMensajeTipo] = useState<"error" | "success" | "">("");
  const [enviando, setEnviando] = useState(false);

  const { fetchPedido } = usePedido();
  const {
    data: clientesData,
    loading: clientesLoading,
    error: clientesError,
    fetchClientes,
  } = useClientes();
  const { data: itemsData, loading: itemsLoading, fetchItems } = useItems();

  const blurTimeouts = useRef<Record<number, number>>({});
  const apiUrl = import.meta.env.VITE_API_URL || "https://localhost:3000";

  useEffect(() => {
    // Carga paralela: ambas peticiones se ejecutan simultáneamente
    Promise.all([
      fetchClientes(`${apiUrl}/clientes/all`).catch(() => {
        // Error silencioso, se maneja en el hook
        return null;
      }),
      fetchItems(`${apiUrl}/inventario/all`).catch(() => {
        // Error silencioso, se maneja en el hook
        return null;
      })
    ]);
  }, []);

  // === Helpers de totales ===
  const totalItems = selectedItems.reduce(
    (acc, item) => acc + (item.confirmed ? item.cantidad : 0),
    0
  );
  const totalMonto = selectedItems.reduce(
    (acc, item) =>
      acc + (item.confirmed && item.precio ? item.cantidad * item.precio : 0),
    0
  );

  // === Handlers ===
  const handleAddItem = () => {
    if (
      selectedItems.length > 0 &&
      !selectedItems[selectedItems.length - 1].confirmed
    ) {
      setMensaje(
        "Complete la selección del artículo anterior antes de agregar uno nuevo."
      );
      setMensajeTipo("error");
      return;
    }
    setSelectedItems((prev) => [
      ...prev,
      {
        itemId: "",
        codigo: "", // Added default
        nombre: "", // Added default
        descripcion: "", // Added default
        categoria: "", // Added default
        precio: 0, // Added default
        costo: 0, // Added default
        costoProduccion: 0, // Added default
        cantidad: 1,
        existencia: 0, // Added default
        activo: true, // Added default
        search: "",
        showSuggestions: false,
        confirmed: false,
      },
    ]);
    setMensaje("");
    setMensajeTipo("");
  };

  const handleItemChange = (
    index: number,
    field: "itemId" | "cantidad" | "search" | "precio" | "detalleitem",
    value: number | string
  ) => {
    setSelectedItems((prev) => {
      const copy = [...prev];
      const updated = { ...copy[index], [field]: value } as SelectedItem;
      if (field === "search") {
        updated.confirmed = false;
        updated.showSuggestions = true;
      }
      copy[index] = updated;
      return copy;
    });
  };

  const handleInputBlur = (index: number) => {
    blurTimeouts.current[index] = window.setTimeout(() => {
      setSelectedItems((prev) => {
        const copy = [...prev];
        if (copy[index]) {
          if (!copy[index].confirmed) {
            copy[index].search = "";
            copy[index].itemId = "";
            copy[index].precio = 0;
          }
          copy[index].showSuggestions = false;
        }
        return copy;
      });
      delete blurTimeouts.current[index];
    }, 120);
  };

  const handleSelectSuggestion = (
    index: number,
    producto: { _id: string; nombre: string; precio: number }
  ) => {
    setSelectedItems((prev) => {
      const copy = [...prev];
      copy[index] = {
        ...copy[index],
        itemId: producto._id,
        search: producto.nombre,
        precio: producto.precio,
        showSuggestions: false,
        confirmed: true,
      };
      return copy;
    });
    if (blurTimeouts.current[index]) {
      clearTimeout(blurTimeouts.current[index]);
      delete blurTimeouts.current[index];
    }
  };

  const handleRemoveItem = (index: number) => {
    setSelectedItems((prev) => prev.filter((_, i) => i !== index));
    if (blurTimeouts.current[index]) {
      clearTimeout(blurTimeouts.current[index]);
      delete blurTimeouts.current[index];
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMensaje("");
    setMensajeTipo("");

    if (!clienteId || selectedItems.length === 0) {
      setMensaje("Seleccione un cliente y al menos un item.");
      setMensajeTipo("error");
      return;
    }

    if (selectedItems.some((item) => !item.confirmed)) {
      setMensaje("Hay artículos pendientes por seleccionar.");
      setMensajeTipo("error");
      return;
    }

    setEnviando(true);

    const now = new Date();
    const fechaISO = now.toISOString();

    const subestados = [
      "Herreria / soldadura",
      "Masillar / Pintura",
      "Preparacion / Verificacion",
      "Facturacion",
      "Despacho",
      "sin definir 1",
      "sin definir 2",
    ];

    const seguimiento: PedidoSeguimiento[] = subestados.map((nombre, idx) => ({
      orden: idx + 1,
      nombre_subestado: nombre,
      estado: "pendiente",
      asignado_a: null,
      fecha_inicio: null,
      fecha_fin: null,
    }));

    const clienteObj = Array.isArray(clientesData)
      ? clientesData.find((c: any) => String(c.rif) === String(clienteId))
      : null;

    const user = JSON.parse(localStorage.getItem("user") || "{}");

    const pedidoPayload: PedidoPayload = {
      cliente_id: String(clienteId),
      cliente_nombre: clienteObj?.nombre || "",
      fecha_creacion: fechaISO,
      fecha_actualizacion: fechaISO,
      estado_general: "pendiente",
      creado_por: user?.usuario || "N/A",
      items: selectedItems.map((item) => {
        const itemData = Array.isArray(itemsData)
          ? (itemsData as any[]).find((it: any) => it._id === item.itemId)
          : undefined;
        return {
          id: itemData?._id ?? String(item.itemId),
          codigo: itemData?.codigo ?? String(item.itemId),
          nombre: itemData?.nombre ?? "",
          descripcion: itemData?.descripcion ?? "",
          categoria: itemData?.categoria ?? "",
          precio: item.precio ?? itemData?.precio ?? 0,
          costo: itemData?.costo ?? 0,
          costoProduccion: itemData?.costoProduccion ?? 0,
          cantidad: item.cantidad,
          activo: itemData?.activo ?? true,
          detalleitem: item.detalleitem || "",
          imagenes: itemData?.imagenes ?? [],
        };
      }),
      seguimiento,
    };

    try {
      const resultado = await fetchPedido(`/pedidos/`, {
        method: "POST",
        body: pedidoPayload,
      });

      if (resultado?.success) {
        setMensaje("✅ Pedido creado correctamente.");
        setMensajeTipo("success");
        setClienteId(0);
        setClienteSearch("");
        setSelectedItems([]);
        setFecha(new Date().toISOString().slice(0, 10));
      } else {
        setMensaje(resultado?.error || "Ocurrió un error al crear el pedido.");
        setMensajeTipo("error");
      }
    } catch (err: any) {
      setMensaje("No se pudo comunicar con el servidor.");
      setMensajeTipo("error");
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Card className="w-full max-w-5xl mx-auto shadow-xl border border-gray-100 rounded-2xl overflow-hidden">
      {/* Header */}
      <CardHeader className="flex items-center gap-3 bg-gradient-to-r from-blue-50 to-blue-100 border-b">
        <FaClipboardList className="text-blue-600 text-2xl" />
        <CardTitle className="text-2xl font-bold text-gray-800">
          Crear Pedido
        </CardTitle>
      </CardHeader>

      <Separator />

      <CardContent className="p-8">
        <form onSubmit={handleSubmit} className="space-y-8">
          {/* Cliente + Fecha */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Cliente */}
            <div className="space-y-2">
              <Label className="text-sm font-semibold text-gray-700">
                Cliente
              </Label>
              <div className="relative flex items-center gap-2">
                <div className="relative w-full">
                  <Input
                    type="text"
                    value={
                      clienteId && Array.isArray(clientesData)
                        ? `${clienteId} - ${
                            (clientesData as any[]).find(
                              (c: any) => c.rif === clienteId
                            )?.nombre || ""
                          }`
                        : clienteSearch || ""
                    }
                    onChange={(e) => {
                      setClienteSearch(e.target.value);
                      setShowClienteSuggestions(true);
                    }}
                    onFocus={() => setShowClienteSuggestions(true)}
                    onBlur={() =>
                      setTimeout(() => setShowClienteSuggestions(false), 120)
                    }
                    placeholder={
                      clientesLoading
                        ? "Cargando..."
                        : clientesError
                        ? "Error al cargar"
                        : "Buscar cliente por nombre o RIF..."
                    }
                    className="focus:ring-2 focus:ring-blue-400"
                    disabled={clientesLoading || !!clientesError}
                    autoComplete="off"
                  />

                  {showClienteSuggestions &&
                    clienteSearch.trim().length > 0 && (
                      <ScrollArea className="absolute left-0 right-0 top-full mt-2 z-30 border rounded-xl bg-white shadow-lg max-h-64 overflow-y-auto">
                        {clientesLoading && (
                          <div className="px-3 py-2 text-gray-500 text-sm">
                            Cargando...
                          </div>
                        )}
                        {clientesError && (
                          <div className="px-3 py-2 text-red-500 text-sm">
                            Error al cargar clientes
                          </div>
                        )}
                        {Array.isArray(clientesData) &&
                        (clientesData as any[]).length > 0 ? (
                          (clientesData as any[])
                            .filter((cliente: any) => {
                              const search = clienteSearch.toLowerCase();
                              return (
                                cliente.nombre.toLowerCase().includes(search) ||
                                String(cliente.rif)
                                  .toLowerCase()
                                  .includes(search)
                              );
                            })
                            .map((cliente: any, idx: number) => (
                              <div
                                key={`${cliente.rif}-${idx}`}
                                onMouseDown={(ev) => {
                                  ev.preventDefault();
                                  setClienteId(cliente.rif);
                                  setClienteSearch("");
                                  setShowClienteSuggestions(false);
                                }}
                                className="px-4 py-2 hover:bg-blue-50 cursor-pointer transition-colors"
                              >
                                <p className="font-medium text-gray-800">
                                  {cliente.nombre}{" "}
                                  <span className="text-xs text-gray-500">
                                    ({cliente.rif})
                                  </span>
                                </p>
                                <p className="text-xs text-gray-500">
                                  {cliente.direccion}
                                </p>
                                {cliente.telefono && (
                                  <p className="text-xs text-gray-500">
                                    Tel: {cliente.telefono}
                                  </p>
                                )}
                              </div>
                            ))
                        ) : (
                          <div className="px-3 py-2 text-gray-500 text-sm">
                            No hay clientes disponibles
                          </div>
                        )}
                      </ScrollArea>
                    )}
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!clienteId}
                  onClick={() => {
                    setClienteId(0);
                    setClienteSearch("");
                  }}
                >
                  Limpiar
                </Button>
              </div>
            </div>

            {/* Fecha */}
            <div className="space-y-2">
              <Label className="text-sm font-semibold text-gray-700">
                Fecha
              </Label>
              <Input
                type="date"
                value={fecha}
                onChange={(e) => setFecha(e.target.value)}
                className="focus:ring-2 focus:ring-blue-400"
              />
            </div>
          </div>

          <Separator />

          {/* Items */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <Label className="text-lg font-semibold text-gray-800">
                Items
              </Label>
              <Button type="button" onClick={handleAddItem} size="sm">
                <FaPlus /> Agregar Item
              </Button>
            </div>

            <div className="space-y-4">
              {selectedItems.map((item, idx) => {
                const filtered: any[] = (itemsData as any[])?.filter((it) =>
                  it.nombre.toLowerCase().includes(item.search?.toLowerCase() || '')
                );

                // Buscar el itemData para mostrar imágenes
                const itemData = Array.isArray(itemsData)
                  ? (itemsData as any[]).find((it: any) => it._id === item.itemId)
                  : undefined;
                return (
                  <div
                    key={idx}
                    className="grid grid-cols-1 md:grid-cols-12 gap-4 items-start border p-4 rounded-xl bg-gray-50 shadow-sm hover:shadow-md transition"
                  >
                    {/* Buscador */}
                    <div className="col-span-1 md:col-span-7 relative">
                      <div className="relative">
                        <FaSearch className="absolute left-3 top-3 text-gray-400" />
                        <Input
                          className="pl-9 focus:ring-2 focus:ring-blue-400"
                          value={item.search || ''}
                          onChange={(e) =>
                            handleItemChange(idx, "search", e.target.value)
                          }
                          onBlur={() => handleInputBlur(idx)}
                          onFocus={() =>
                            setSelectedItems((prev) => {
                              const copy = [...prev];
                              copy[idx].showSuggestions = true;
                              return copy;
                            })
                          }
                          placeholder="Buscar producto..."
                          autoComplete="off"
                          />
                      </div>
                      {item.showSuggestions &&
                        item.search && item.search.trim().length > 0 && (
                          <ScrollArea className="absolute left-0 right-0 z-30 mt-2 overflow-auto border rounded-xl bg-white max-h-44 shadow-lg">
                            {filtered.length > 0 ? (
                              filtered.map((f: any, fidx: number) => (
                                <div
                                  key={`item-${f._id}-${fidx}`}
                                  onMouseDown={(ev) => {
                                    ev.preventDefault();
                                    handleSelectSuggestion(idx, f);
                                  }}
                                  className="px-3 py-2 hover:bg-blue-50 cursor-pointer transition-colors"
                                >
                                  <span className="font-medium text-gray-800">
                                    {f.nombre}
                                  </span>
                                  <span className="ml-2 text-xs text-gray-500">
                                    ${f.precio}
                                  </span>
                                </div>
                              ))
                            ) : (
                              <div className="px-3 py-2 text-gray-500 text-sm">
                                No encontrado
                              </div>
                            )}
                          </ScrollArea>
                        )}
                    </div>

                    {/* Cantidad */}
                    <div className="col-span-1 md:col-span-2">
                      <Label className="block text-xs text-gray-600 mb-1">
                        Cantidad
                      </Label>
                      <Input
                        type="number"
                        min={1}
                        value={item.cantidad}
                        onChange={(e) =>
                          handleItemChange(
                            idx,
                            "cantidad",
                            Number(e.target.value)
                          )
                        }
                        disabled={!item.confirmed}
                        className="w-24 focus:ring-2 focus:ring-blue-400"
                      />
                    </div>

                    {/* Precio */}
                    <div className="col-span-1 md:col-span-2">
                      <Label className="block text-xs text-gray-600 mb-1">
                        Precio
                      </Label>
                      <Input
                        type="number"
                        min={0}
                        step="0.01"
                        value={item.precio ?? ""}
                        onChange={(e) =>
                          handleItemChange(
                            idx,
                            "precio",
                            Number(e.target.value)
                          )
                        }
                        disabled={!item.confirmed}
                        className="w-28 focus:ring-2 focus:ring-blue-400"
                      />
                    </div>

                    {/* Quitar */}
                    <div className="col-span-1 md:col-span-1 flex justify-end">
                      <Button
                        type="button"
                        onClick={() => handleRemoveItem(idx)}
                        variant="destructive"
                        size="icon"
                        className="bg-red-600 hover:bg-red-700 text-white"
                      >
                        <FaTrashRestore />
                      </Button>
                    </div>

                    {/* Detalle */}
                    <div className="col-span-1 md:col-span-12">
                      <Label className="block text-xs text-gray-600 mb-1">
                        Detalle del artículo
                      </Label>
                      <Input
                        type="text"
                        onChange={(e) =>
                          handleItemChange(idx, "detalleitem", e.target.value)
                        }
                        placeholder="Escribe un detalle..."
                        className="w-full focus:ring-2 focus:ring-blue-400"
                        />
                    </div>
                    {/* Imágenes del item seleccionado */}
                    {itemData && Array.isArray(itemData.imagenes) && itemData.imagenes.length > 0 && (
                      <div className="col-span-1 md:col-span-2 flex flex-col gap-2 items-center justify-center">
                        <Label className="block text-xs text-gray-600 mb-1">Imágenes</Label>
                        <div className="flex gap-2 flex-row">
                          {itemData.imagenes.slice(0, 3).map((img: string, imgIdx: number) => (
                            <ImageDisplay
                              key={imgIdx}
                              imageName={img}
                              alt={`Imagen ${imgIdx + 1}`}
                              style={{ maxWidth: 60, maxHeight: 60, borderRadius: 6, border: '1px solid #ddd' }}
                            />
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}

              {selectedItems.length === 0 && (
                <p className="text-sm text-gray-500 text-center py-6">
                  No hay items seleccionados.
                </p>
              )}
            </div>

            {/* Totales */}
            {selectedItems.length > 0 && (
              <div className="mt-6 flex justify-end">
                <Card className="bg-gradient-to-r from-blue-50 to-blue-100 px-6 py-4 rounded-xl shadow-md">
                  <p className="text-gray-700 font-medium">
                    Total items:{" "}
                    <span className="font-bold text-gray-900">
                      {totalItems}
                    </span>
                  </p>
                  <p className="text-gray-700 font-medium">
                    Total:{" "}
                    <span className="text-xl font-bold text-blue-700">
                      $
                      {totalMonto.toLocaleString("es-AR", {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </span>
                  </p>
                </Card>
              </div>
            )}
          </div>

          {/* Estado */}
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-600">
              Estado: <Badge variant="secondary">Pendiente</Badge>
            </p>
          </div>

          {/* Submit */}
          <Button
            type="submit"
            className="w-full mt-4 text-lg font-bold py-3 rounded-xl shadow-md hover:shadow-lg transition"
            disabled={itemsLoading || clientesLoading || enviando}
          >
            {enviando
              ? "Enviando..."
              : itemsLoading || clientesLoading
              ? "Procesando..."
              : "Crear Pedido"}
          </Button>
        </form>

        {/* Alertas */}
        {mensaje && (
          <div className="mt-8">
            <Alert
              variant={mensajeTipo === "error" ? "destructive" : "default"}
              className="rounded-xl"
            >
              <AlertTitle>
                {mensajeTipo === "error" ? "Error" : "Éxito"}
              </AlertTitle>
              <AlertDescription>{mensaje}</AlertDescription>
            </Alert>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default CrearPedido;