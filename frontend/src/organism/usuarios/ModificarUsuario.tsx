import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useState, useEffect } from "react";
import { useNavigate } from "react-router";

interface Usuario {
  _id: string;
  usuario: string;
  nombreCompleto: string;
  identificador?: string;
  permisos?: string[];
  password?: string;
}

  const permisosDisponibles = [
    "asignar",
    "inventario",
    "ventas",
    "reportes",
    "empleados",
    "clientes",
    "admin",
    "crearusuarios",
    "crearclientes",
    "crearinventario",
    "crearempleados",
    "modificarusuarios",
    "modificarempleados",
    "modificarinventario",
    "modificarclientes",
    "monitorpedidos",
    "terminarasignacion",
    "dashboard",
    "pagos",
    "cuentas_por_pagar"
];

const ModificarUsuario: React.FC = () => {
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");
  const [usuarioSeleccionado, setUsuarioSeleccionado] = useState<Usuario | null>(null);
  const [mensaje, setMensaje] = useState<string>("");
  const [form, setForm] = useState({
    usuario: "",
    nombreCompleto: "",
    identificador: "",
    permisos: [] as string[],
    password: "",
  });

  const navigate = useNavigate();

  useEffect(() => {
    const apiUrl = import.meta.env.VITE_API_URL || "https://localhost:3000";
    const token = localStorage.getItem("access_token");
    setLoading(true);
    setError("");
    fetch(`${apiUrl}/usuarios/all`, {
      headers: {
        "Authorization": `Bearer ${token}`
      }
    })
      .then((response) => {
        if (!response.ok) throw new Error("Error al obtener usuarios");
        return response.json();
      })
      .then((data: Usuario[]) => {
        setUsuarios(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(`No se pudieron cargar los usuarios: ${err.message}`);
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (usuarioSeleccionado) {
      setForm({
        usuario: usuarioSeleccionado.usuario || "",
        nombreCompleto: usuarioSeleccionado.nombreCompleto || "",
        identificador: usuarioSeleccionado.identificador || "",
        permisos: usuarioSeleccionado.permisos || [],
        password: "",
      });
    }
  }, [usuarioSeleccionado]);

  const handleSelectUsuario = (id: string) => {
    const usuario = usuarios.find((u) => u._id === id) || null;
    setUsuarioSeleccionado(usuario);
    setMensaje("");
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handlePermisoChip = (permiso: string) => {
    setForm((prev) => {
      const yaTiene = prev.permisos?.includes(permiso);
      return {
        ...prev,
        permisos: yaTiene
          ? prev.permisos?.filter((p) => p !== permiso)
          : [...(prev.permisos || []), permiso],
      };
    });
  };

  const validate = (): string | null => {
    if (!form.usuario.trim()) return "El usuario es obligatorio.";
    if (usuarioSeleccionado && form.password && form.password.length < 6)
      return "La contraseña debe tener al menos 6 caracteres.";
    if (!form.nombreCompleto.trim()) return "El nombre completo es obligatorio.";
    if (!form.identificador.trim()) return "El identificador es obligatorio.";
    return null;
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMensaje("");
    setError("");
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    try {
      const apiUrl = import.meta.env.VITE_API_URL || "https://localhost:3000";
      const token = localStorage.getItem("access_token");
      const payload: any = {
        nombreCompleto: form.nombreCompleto,
        identificador: form.identificador,
        permisos: form.permisos,
      };
      if (form.password && form.password.length >= 6) {
        payload.password = form.password;
      }
      const res = await fetch(`${apiUrl}/usuarios/${usuarioSeleccionado?._id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Error al modificar usuario");
      const updated = await res.json();
      setUsuarios((prev) => prev.map((u) => (u._id === updated._id ? updated : u)));
      
      // Si el usuario modificado es el mismo que está logueado, actualizar sus permisos en localStorage
      const usuarioActual = localStorage.getItem("usuario");
      if (updated.usuario === usuarioActual && updated.permisos) {
        localStorage.setItem("permisos", JSON.stringify(updated.permisos));
        console.log("✅ Permisos actualizados en localStorage:", updated.permisos);
      }
      
      setMensaje("Usuario modificado correctamente ✅");
      setUsuarioSeleccionado(updated);
      navigate(`/modificarusuario`);
    } catch (err: any) {
      setError("No se pudo modificar el usuario");
    }
  };

  return (
    <Card className="w-full max-w-md mx-auto shadow-lg border border-gray-200 mt-8">
      <CardHeader>
        <CardTitle className="text-xl font-bold">Modificar Usuario</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="mb-6">
          <Label htmlFor="selectUsuario">Selecciona un usuario</Label>
          {loading ? (
            <div className="mt-2 text-gray-500">Cargando usuarios...</div>
          ) : error ? (
            <div className="mt-2 text-red-500">{error}</div>
          ) : (
            <select
              id="selectUsuario"
              className="mt-1 w-full border rounded px-2 py-2"
              value={usuarioSeleccionado?._id || ""}
              onChange={(e) => handleSelectUsuario(e.target.value)}
            >
              <option value="">-- Selecciona --</option>
              {usuarios.map((u) => (
                <option key={u._id} value={u._id}>
                  {u.nombreCompleto} ({u.usuario})
                </option>
              ))}
            </select>
          )}
        </div>
        {usuarioSeleccionado && (
          <form onSubmit={onSubmit} className="space-y-6">
            <div>
              <Label htmlFor="usuario">Usuario</Label>
              <Input
                id="usuario"
                name="usuario"
                value={form.usuario}
                disabled
                className="mt-1 bg-gray-100 cursor-not-allowed"
                required
              />
            </div>
            <div>
              <Label htmlFor="nombreCompleto">Nombre Completo</Label>
              <Input
                id="nombreCompleto"
                name="nombreCompleto"
                value={form.nombreCompleto}
                onChange={handleChange}
                className="mt-1"
                required
              />
            </div>
            <div>
              <Label htmlFor="identificador">Identificador</Label>
              <Input
                id="identificador"
                name="identificador"
                value={form.identificador}
                onChange={handleChange}
                className="mt-1"
                required
              />
            </div>
            <div>
              <Label htmlFor="permisos">Permisos</Label>
              <div className="flex flex-wrap gap-2 mt-1">
                {permisosDisponibles.map((permiso) => (
                  <Button
                    key={permiso}
                    type="button"
                    variant={form.permisos.includes(permiso) ? "default" : "outline"}
                    className={form.permisos.includes(permiso) ? "bg-green-500 text-white" : "bg-white border"}
                    onClick={() => handlePermisoChip(permiso)}
                  >
                    {permiso}
                  </Button>
                ))}
              </div>
            </div>
            <div>
              <Label htmlFor="password">¿Deseas cambiar la contraseña?</Label>
              <Input
                id="password"
                name="password"
                type="password"
                value={form.password}
                onChange={handleChange}
                className="mt-1"
                placeholder="Nueva contraseña (opcional)"
              />
              <span className="text-xs text-gray-500">Dejar vacío para no cambiar la contraseña</span>
            </div>
            <Button type="submit" className="w-full mt-4 font-bold py-2">
              Guardar Cambios
            </Button>
          </form>
        )}
        {mensaje && (
          <div className="mt-4 text-center text-green-600 font-semibold">
            {mensaje}
          </div>
        )}
        {error && (
          <div className="mt-4 text-center text-red-600 font-semibold">
            {error}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default ModificarUsuario;
