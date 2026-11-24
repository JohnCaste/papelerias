import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Container from "react-bootstrap/Container";
import Nav from "react-bootstrap/Nav";
import Navbar from "react-bootstrap/Navbar";
import NavDropdown from "react-bootstrap/NavDropdown";
import { obtenerSucursal } from "../services/sucursal";
import { obtenerFaltantes } from "../services/faltantes";
import type { Theme } from "../useTheme";
import "./Menu.css";

interface MenuProps {
  theme: Theme;
  toggleTheme: () => void;
}

const Menu = ({ theme, toggleTheme }: MenuProps) => {
  const navigate = useNavigate();
  const nombre = localStorage.getItem("nombre");
  // Solo 'dueno' ve Ventas. El rol lo guarda el login; aplica al
  // volver a iniciar sesión si un dueño lo cambia desde Configuración.
  const esDueno = localStorage.getItem("rol") === "dueno";

  // La foto vive en localStorage (la escribe el login y la pantalla de
  // Configuración al subir una nueva). Se guarda en estado para poder
  // refrescarla sin recargar: Configuración dispara "perfil:foto" tras
  // subir, y "storage" cubre el cambio hecho en otra pestaña.
  const [fotoUrl, setFotoUrl] = useState<string | null>(() =>
    localStorage.getItem("foto_url"),
  );

  useEffect(() => {
    const sincronizar = () => setFotoUrl(localStorage.getItem("foto_url"));
    window.addEventListener("perfil:foto", sincronizar);
    window.addEventListener("storage", sincronizar);
    return () => {
      window.removeEventListener("perfil:foto", sincronizar);
      window.removeEventListener("storage", sincronizar);
    };
  }, []);

  // Nombre de la sucursal junto al logo: con dos papelerías, quien cobra
  // tiene que ver de un vistazo en cuál está. Si la consulta falla, la
  // barra se queda como antes.
  const [sucursal, setSucursal] = useState<string | null>(null);
  // Compras de trabajadores solo existe en la sucursal original.
  const [esLapape, setEsLapape] = useState(false);

  useEffect(() => {
    obtenerSucursal()
      .then((s) => {
        setSucursal(s.nombre);
        setEsLapape(s.dataset === "lapape");
      })
      .catch(() => setSucursal(null));
  }, []);

  // Contador de faltantes pendientes junto al link. Lectura local del
  // journal (barata); si falla, el link se queda sin contador. La pantalla
  // de Faltantes avisa con "faltantes:cambio" al agregar o marcar.
  const [faltantes, setFaltantes] = useState<number | null>(null);

  useEffect(() => {
    if (!localStorage.getItem("token")) return;
    obtenerFaltantes()
      .then((e) => setFaltantes(e.pendientes.length))
      .catch(() => setFaltantes(null));
    const alCambiar = (e: Event) => setFaltantes((e as CustomEvent<number>).detail);
    window.addEventListener("faltantes:cambio", alCambiar);
    return () => window.removeEventListener("faltantes:cambio", alCambiar);
  }, []);

  const salir = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("user_id");
    localStorage.removeItem("nombre");
    localStorage.removeItem("foto_url");
    localStorage.removeItem("rol");
    navigate("/");
  };

  return (
    <Navbar data-bs-theme="dark" expand="lg" sticky="top" className="lp-navbar">
      <Container fluid className="lp-navbar__container">
        <Navbar.Brand href="/catalogo">
          <img src="/nuevoLogo.svg" width="30" height="30" alt="" />
          La pape
          {sucursal && (
            <span className="lp-navbar__sucursal" title="Sucursal">
              {sucursal}
            </span>
          )}
        </Navbar.Brand>
        <Navbar.Toggle aria-controls="basic-navbar-nav" />
        <Navbar.Collapse id="basic-navbar-nav">
          <Nav className="me-auto">
            <Nav.Link href="/vender">Vender</Nav.Link>
            <Nav.Link href="/catalogo">Catálogo</Nav.Link>
            {esDueno && <Nav.Link href="/ventas">Ventas</Nav.Link>}
            <Nav.Link href="/desglose">Desglose</Nav.Link>
            {esDueno && esLapape && <Nav.Link href="/compras">Compras</Nav.Link>}
            <Nav.Link href="/faltantes" className="lp-navbar__faltantes">
              Faltantes
              {!!faltantes && (
                <span className="lp-navbar__contador" aria-label={`${faltantes} pendientes`}>
                  {faltantes}
                </span>
              )}
            </Nav.Link>
          </Nav>
        </Navbar.Collapse>
        {(fotoUrl || nombre) && (
          <div className="lp-navbar__usuario" title={nombre ?? undefined}>
            {fotoUrl && (
              <img
                src={fotoUrl}
                alt="Foto de perfil"
                className="lp-navbar__avatar"
                onError={() => setFotoUrl(null)}
              />
            )}
            {nombre && (
              <span className="lp-navbar__usuario-nombre">{nombre}</span>
            )}
          </div>
        )}
        <button
          type="button"
          onClick={toggleTheme}
          className="lp-navbar__theme"
          aria-label="Cambiar modo claro / oscuro"
        >
          <span className="lp-navbar__theme-dot" />
          {theme === "dark" ? "Modo oscuro" : "Modo claro"}
        </button>
        <NavDropdown
          title="Usuarios"
          id="basic-nav-dropdown"
          className="lp-navbar__usuarios"
        >
          <NavDropdown.Item href="/admin">Administración</NavDropdown.Item>
          <NavDropdown.Item href="/foundations">Diseño General</NavDropdown.Item>
          <NavDropdown.Divider />
          <NavDropdown.Item onClick={salir} className="lp-navbar__salir">
            Salir
          </NavDropdown.Item>
        </NavDropdown>
      </Container>
    </Navbar>
  );
};

export default Menu;
