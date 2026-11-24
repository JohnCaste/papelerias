import Login from "./pages/Login";
import { useEffect, useState, type ReactNode } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useLocation,
} from "react-router-dom";
import Catalogo from "./pages/Catalogo";
import "bootstrap/dist/css/bootstrap.min.css";
import Menu from "./pages/Menu";
import Admin from "./pages/Admin";
import Ventas from "./pages/Ventas";
import Desglose from "./pages/Desglose";
import PuntoVenta from "./pages/PuntoVenta";
import Foundations from "./pages/Foundations";
import Compras from "./pages/Compras";
import Faltantes from "./pages/Faltantes";
import { obtenerSucursal } from "./services/sucursal";
import { useTheme } from "./useTheme";

/* Rutas sin navbar: login y la página standalone de foundations. */
const RUTAS_SIN_MENU = ["/", "/foundations"];

/* Bloquea el acceso a cualquier pantalla si no hay sesión iniciada:
   sin token en localStorage se redirige al login. */
function RutaProtegida({ children }: { children: ReactNode }) {
  if (!localStorage.getItem("token")) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

/* Ventas es solo para el rol 'dueno'. Un empleado que llegue a esa ruta
   (link viejo, URL escrita a mano) se manda al catálogo.
   El bloqueo es solo de interfaz: la API no valida el rol. */
function RutaDueno({ children }: { children: ReactNode }) {
  if (!localStorage.getItem("token")) {
    return <Navigate to="/" replace />;
  }
  if (localStorage.getItem("rol") !== "dueno") {
    return <Navigate to="/catalogo" replace />;
  }
  return <>{children}</>;
}

/* Compras de trabajadores: solo la dueña y solo en la sucursal original
   (dataset 'lapape'). El backend aplica la misma regla (404 / 403). */
function RutaDuenaLapape({ children }: { children: ReactNode }) {
  const [permitido, setPermitido] = useState<boolean | null>(null);

  useEffect(() => {
    obtenerSucursal()
      .then((s) => setPermitido(s.dataset === "lapape"))
      .catch(() => setPermitido(false));
  }, []);

  if (!localStorage.getItem("token")) {
    return <Navigate to="/" replace />;
  }
  if (localStorage.getItem("rol") !== "dueno") {
    return <Navigate to="/catalogo" replace />;
  }
  if (permitido === null) return null;
  if (!permitido) return <Navigate to="/catalogo" replace />;
  return <>{children}</>;
}

function Shell() {
  const { pathname } = useLocation();
  const { theme, toggleTheme } = useTheme();
  const mostrarMenu = !RUTAS_SIN_MENU.includes(pathname);

  return (
    <>
      {mostrarMenu && <Menu theme={theme} toggleTheme={toggleTheme} />}
      <Routes>
        <Route path="/" element={<Login />} />
        <Route
          path="/vender"
          element={
            <RutaProtegida>
              <PuntoVenta />
            </RutaProtegida>
          }
        />
        <Route
          path="/catalogo"
          element={
            <RutaProtegida>
              <Catalogo />
            </RutaProtegida>
          }
        />
        <Route
          path="/admin"
          element={
            <RutaProtegida>
              <Admin />
            </RutaProtegida>
          }
        />
        <Route
          path="/ventas"
          element={
            <RutaDueno>
              <Ventas />
            </RutaDueno>
          }
        />
        <Route
          path="/desglose"
          element={
            <RutaProtegida>
              <Desglose />
            </RutaProtegida>
          }
        />
        <Route
          path="/compras"
          element={
            <RutaDuenaLapape>
              <Compras />
            </RutaDuenaLapape>
          }
        />
        <Route
          path="/faltantes"
          element={
            <RutaProtegida>
              <Faltantes />
            </RutaProtegida>
          }
        />
        <Route
          path="/foundations"
          element={
            <RutaProtegida>
              <Foundations />
            </RutaProtegida>
          }
        />
      </Routes>
    </>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}

export default App;
