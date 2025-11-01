import React, { useState } from "react";

interface RegisterResponse {
  message: string;
}

  interface UserAdmin {
    usuario: string;
    password: string;
    permisos?: string[];
    nombreCompleto: string;
    identificador: string;
  }

  interface RegisterResponse {
    message: string;
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
    "dashboard",
    "monitorpedidos",
    "terminarasignacion",
    "pagos",
    "cuentas_por_pagar"
];

  const Register: React.FC = () => {
    const [form, setForm] = useState<UserAdmin>({
      usuario: "",
      password: "",
      permisos: [],
      nombreCompleto: "",
      identificador: ""
    });
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);

    // Validaciones
    const validate = (): string | null => {
      if (!form.usuario.trim()) return "El usuario es obligatorio.";
      if (!form.password || form.password.length < 6) return "La contraseña debe tener al menos 6 caracteres.";
      if (!form.nombreCompleto.trim()) return "El nombre completo es obligatorio.";
      if (!form.identificador.trim()) return "El identificador es obligatorio.";
      return null;
    };

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const { name, value } = e.target;
      setForm(prev => ({ ...prev, [name]: value }));
    };

    const handlePermisoChip = (permiso: string) => {
      setForm(prev => {
        const yaTiene = prev.permisos?.includes(permiso);
        return {
          ...prev,
          permisos: yaTiene
            ? prev.permisos?.filter(p => p !== permiso)
            : [...(prev.permisos || []), permiso],
        };
      });
    };

    const handleSubmit = async (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);
      setSuccess(null);
      const validationError = validate();
      if (validationError) {
        setError(validationError);
        return;
      }
      setLoading(true);
      try {
        const apiUrl = import.meta.env.VITE_API_URL || "https://localhost:3000";
        const res = await fetch(`${apiUrl}/auth/register/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(form)
        });
        if (!res.ok) {
          const data = await res.json();
          throw new Error(data.detail || "Error al registrar usuario");
        }
        const data: RegisterResponse = await res.json();
    setSuccess(data.message);
    setForm({ usuario: "", password: "", permisos: [], nombreCompleto: "", identificador: "" });
      } catch (err: any) {
        setError(err.message || "Error desconocido");
      } finally {
        setLoading(false);
      }
    };

    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-100">
        <form onSubmit={handleSubmit} className="bg-white p-8 rounded shadow-md w-full max-w-md">
          <h2 className="text-2xl font-bold mb-6 text-center">Registrar Usuario</h2>
          <div className="mb-4">
            <label className="block mb-2 font-semibold">Usuario</label>
            <input
              type="text"
              name="usuario"
              value={form.usuario}
              onChange={handleChange}
              className="w-full border px-3 py-2 rounded"
              required
            />
          </div>
          <div className="mb-4">
            <label className="block mb-2 font-semibold">Nombre Completo</label>
            <input
              type="text"
              name="nombreCompleto"
              value={form.nombreCompleto}
              onChange={handleChange}
              className="w-full border px-3 py-2 rounded"
              required
            />
          </div>
          <div className="mb-4">
            <label className="block mb-2 font-semibold">Identificador</label>
            <input
              type="text"
              name="identificador"
              value={form.identificador}
              onChange={handleChange}
              className="w-full border px-3 py-2 rounded"
              required
            />
          </div>
          <div className="mb-4">
            <label className="block mb-2 font-semibold">Permisos</label>
            <div className="flex flex-wrap gap-2">
              {permisosDisponibles.map((permiso) => (
                <button
                  type="button"
                  key={permiso}
                  className={`px-3 py-1 rounded-full border text-sm font-semibold transition-colors ${form.permisos?.includes(permiso)
                    ? "bg-blue-600 text-white border-blue-600"
                    : "bg-gray-100 text-gray-700 border-gray-300 hover:bg-blue-100"}`}
                  onClick={() => handlePermisoChip(permiso)}
                >
                  {permiso}
                </button>
              ))}
            </div>
            {form.permisos && form.permisos.length > 0 && (
              <div className="mt-2 text-xs text-gray-600">
                Seleccionados: {form.permisos.join(", ")}
              </div>
            )}
          </div>
          <div className="mb-6">
            <label className="block mb-2 font-semibold">Contraseña</label>
            <input
              type="password"
              name="password"
              value={form.password}
              onChange={handleChange}
              className="w-full border px-3 py-2 rounded"
              required
            />
          </div>
          {error && <div className="mb-4 text-red-600 text-center">{error}</div>}
          {success && <div className="mb-4 text-green-600 text-center">{success}</div>}
          <button
            type="submit"
            className="w-full bg-green-600 text-white py-2 rounded font-bold hover:bg-green-700 transition-colors"
            disabled={loading}
          >
            {loading ? "Registrando..." : "Registrar"}
          </button>
        </form>
      </div>
    );
  };

  export default Register;
