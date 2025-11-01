import React, { useState, useEffect, useRef } from "react";
// 1. Corregido: NavLink se importa desde 'react-router-dom'
import { NavLink } from "react-router";
import { LogOutIcon, XIcon, MenuIcon } from "lucide-react";

interface NavbarProps {
  links?: { label: string; href: string }[];
}

// --- Datos de ejemplo y configuración (sin cambios en la lógica) ---
const defaultLinks = [
  { label: "Inicio", href: "/" },
  { label: "Crear Cliente", href: "/crearcliente" },
  { label: "Modificar Cliente", href: "/modificarcliente" },
  { label: "Crear Item", href: "/crearitem" },
  { label: "Modificar Item", href: "/inventario/modificar" },
  { label: "Crear Pedido", href: "/crearpedido" },
  { label: "Monitor Pedidos", href: "/monitorpedidos" },
  { label: "Mis Asignaciones", href: "/terminarasignacion" },
  { label: "Asignar Herreria/Soldadura", href: "/pedidosherreria" },
  { label: "Asignar Masillar/Pintar", href: "/masillar" },
  { label: "Asignar Manillar", href: "/preparar" },
  { label: "Asignar Facturacion", href: "/facturacion" },
  { label: "Asignar Envios", href: "/envios" },
  { label: "Pagos", href: "/pagos" },
  { label: "Mis Pagos", href: "/mispagos" },
  { label: "Dashboard", href: "/dashboard" },
  { label: "Crear Empleado", href: "/crearempleado" },
  { label: "Modificar Empleado", href: "/modificarempleado" },
  { label: "Crear Usuario", href: "/register" },
  { label: "Modificar Usuario", href: "/modificarusuario" },
  { label: "Cuentas por Pagar", href: "/cuentas-por-pagar" },
  { label: "Reportes Comision", href: "/reportes/comisiones/produccion" },
];

const permisosRuta: Record<string, string | null> = {
  "/crearpedido": "ventas",
  "/crearcliente": "crearclientes",
  "/modificarcliente": "modificarclientes",
  "/crearitem": "crearinventario",
  "/inventario/modificar": "modificarinventario",
  "/pedidosherreria": "asignar",
  "/masillar": "asignar",
  "/preparar": "asignar",
  "/facturacion": "asignar",
  "/envios": "asignar",
  "/dashboard": "dashboard",
  "/crearempleado": "crearempleados",
  "/modificarempleado": "modificarempleados",
  "/register": "crearusuarios",
  "/modificarusuario": "modificarusuarios",
  "/terminarasignacion": "terminarasignacion",
  "/monitorpedidos": "monitorpedidos",
  "/pagos": "pagos",
  "/mispagos": "pagos",
  "/cuentas-por-pagar": "cuentas_por_pagar",
  "/home": null,
  "/": null,
};

// --- Componente Navbar Mejorado ---
const Navbar: React.FC<NavbarProps> = ({ links = defaultLinks }) => {
  const [isOpen, setIsOpen] = useState(false);
  const navRef = useRef<HTMLElement>(null);

  // Lógica para obtener permisos (sin cambios)
  const getPermisos = () => {
    try {
      const raw = localStorage.getItem("permisos");
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  };
  const permisos = getPermisos();

  // Lógica de filtrado de enlaces (sin cambios)
  const filteredLinks = links.filter((link) => {
    const permiso = permisosRuta[link.href];
    return !permiso || permisos.includes(permiso);
  });

  // Función para cerrar sesión (sin cambios)
  const handleLogout = () => {
    localStorage.clear();
    window.location.href = "/login";
  };

  // Cierra el menú si se hace clic fuera de él
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (navRef.current && !navRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  return (
    <nav
      ref={navRef}
      className="bg-white sticky top-0 z-50 shadow"
      style={{ background: "#fff" }}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Sección Izquierda: Logo */}
          <div className="flex-shrink-0">
            <NavLink
              to="/"
              className="text-2xl font-bold text-slate-800 hover:text-blue-600 transition-colors"
            >
              Crafteo
            </NavLink>
          </div>

          <div className="-mr-2 flex">
            <button
              onClick={() => setIsOpen(!isOpen)}
              type="button"
              className="bg-slate-100 inline-flex items-center justify-center p-2 rounded-md text-slate-600 hover:text-slate-900 hover:bg-slate-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-500"
              aria-controls="mobile-menu"
              aria-expanded="false"
            >
              <span className="sr-only">Abrir menú principal</span>
              {isOpen ? <XIcon /> : <MenuIcon />}
            </button>
          </div>
        </div>
      </div>

      <div
        className={`fixed z-50 bg-white transition-all duration-300 ease-in-out max-w-3xl ${
          isOpen
            ? "overflow-auto max-h-2/3 ocultar-scrollbar right-0 sm:right-32"
            : "max-h-0 hidden"
        }`}
        id="mobile-menu"
        style={{ backgroundColor: "#fff", opacity: 1, backdropFilter: "none", WebkitBackdropFilter: "none" }}
      >
        <div className="px-2 pt-2 pb-3 space-y-1 sm:px-3 border-t border-slate-200">
          {filteredLinks.map((link) => (
            <NavLink
              key={link.href}
              to={link.href}
              onClick={() => setIsOpen(false)} // Cierra el menú al hacer clic
              className={({ isActive }) =>
                `block px-3 py-2 rounded-md text-base font-medium transition-all duration-200 ${
                  isActive
                    ? "bg-blue-600 text-white shadow-sm"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
          <div className="pt-4 mt-4 border-t border-slate-200">
          </div>
        </div>
            <button
              onClick={handleLogout}
              className="w-full flex items-center justify-center px-4 py-2 rounded-md font-medium text-white bg-red-500 hover:bg-red-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 transition-all duration-200 shadow"
            >
              <LogOutIcon />
              Cerrar Sesión
            </button>
      </div>
    </nav>
  );
};

export default Navbar;
