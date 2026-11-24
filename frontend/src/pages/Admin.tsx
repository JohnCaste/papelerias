import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type CSSProperties,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import "bootstrap/dist/css/bootstrap.min.css";
import "./Catalogo.css";
import Tab from "react-bootstrap/Tab";
import Tabs from "react-bootstrap/Tabs";
import Table from "react-bootstrap/Table";
import { obtenerTodo } from "../services/catalogo";
import {
  cambiarRol,
  obtenerUsuarios,
  subirFotoPerfil,
  type Rol,
  type Usuario,
} from "../services/usuarios";
import { Alert, Button, Form, Spinner } from "react-bootstrap";
import { BsFillTrash3Fill } from "react-icons/bs";
import { RxUpdate } from "react-icons/rx";
import { IoMdAddCircle } from "react-icons/io";
import ModalAgregarProducto from "../components/AgregarProModal";
import ModalEliminarProducto from "../components/EliminarProModal";
import ModalActualizarProducto from "../components/ActualizarProModal";
import ModalArticuloInexistente from "../components/ModalArticuloInexistente";
import { useScannerGun } from "../hooks/useScannerGun";
// -----------------------------------------------------------------------------------
interface Producto {
  id: string;
  nombre: string;
  categoria: string;
  descripcion: string;
  imagen: string;
  marca: string;
  codigo_barras?: string | null;
  precio: number;
  cantidad: number;
}

function Admin() {
  const [showModal, setShowModal] = useState(false);
  const [expandido, setExpandido] = useState<boolean>(false);
  const estiloCelda: CSSProperties = {
    maxWidth: expandido ? "none" : "120px",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
    cursor: "pointer",
    borderBottom: expandido
      ? "var(--lp-border-width-strong) solid var(--lp-color-secondary)"
      : "none",
    transition: "all 0.2s ease-in-out",
  };
  const toggleExpandir = (): void => {
    setExpandido(!expandido);
  };
  const [productos, setProductos] = useState<Producto[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showEliminar, setShowEliminar] = useState(false);
  const [productoSeleccionado, setProductoSeleccionado] = useState<
    string | null
  >(null);
  const [showUpdate, setShowUpdate] = useState(false);
  const [productoEditar, setProductoEditar] = useState<Producto | null>(null);

  // Pistola de código de barras en la pestaña Inventario:
  // - filtroCodigo: la tabla se filtra al producto escaneado (null = sin filtro)
  // - codigoInexistente: código leído que no está en la lista -> modal
  // - codigoAltaInicial: se pasa a AgregarProModal para precargar el código
  const [filtroCodigo, setFiltroCodigo] = useState<string | null>(null);
  const [codigoInexistente, setCodigoInexistente] = useState<string | null>(null);
  const [codigoAltaInicial, setCodigoAltaInicial] = useState<string | undefined>(
    undefined,
  );

  const location = useLocation();
  const navigate = useNavigate();

  const cargarProductos = async () => {
    try {
      const data = await obtenerTodo();
      setProductos(data);
    } catch {
      setError("No se pudieron cargar los productos");
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    cargarProductos();
  }, []);

  // Lectura de la pistola: si el código está en la lista cargada, filtra la
  // tabla; si no, ofrece darlo de alta con el código ya puesto.
  useScannerGun((codigo) => {
    const existe = productos.some((p) => p.codigo_barras === codigo);
    if (existe) {
      setFiltroCodigo(codigo);
    } else {
      setCodigoInexistente(codigo);
    }
  });

  const productosVisibles = filtroCodigo
    ? productos.filter((p) => p.codigo_barras === filtroCodigo)
    : productos;

  // "Ver" desde el Catálogo navega a /admin con { editarProductoId }: al tener
  // los productos cargados, abrimos el modal de edición de ese producto.
  useEffect(() => {
    const id = (location.state as { editarProductoId?: string } | null)
      ?.editarProductoId;
    if (!id || productos.length === 0) return;

    const prod = productos.find((p) => p.id === id);
    if (prod) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setProductoEditar(prod);
      setShowUpdate(true);
    }
    // limpiar el state para que un refresh no vuelva a abrir el modal
    navigate(".", { replace: true, state: null });
  }, [location.state, productos, navigate]);

  return (
    <div className="catalogo-page">
      <h2 className="catalogo-title">Administración</h2>

      <Tabs
        defaultActiveKey="profile"
        id="uncontrolled-tab-example"
        className="mb-3"
      >
        <Tab eventKey="home" title="Inventario">
          {/* -------------------------- Tabla de inventarios-----  */}
          {/* ---------------------------Boton de agregar */}

          <Button
            variant="primary mb-3"
            size="lg"
            onClick={() => setShowModal(true)}
          >
            Agregar producto <IoMdAddCircle />
          </Button>
          {/* ---------------------------Modal agregar */}
          <ModalAgregarProducto
            show={showModal}
            codigoInicial={codigoAltaInicial}
            onHide={() => {
              setShowModal(false);
              setCodigoAltaInicial(undefined);
            }}
            onProductoAgregado={() => {
              setCodigoAltaInicial(undefined);
              cargarProductos();
            }}
          />

          {/* --------------------------- Filtro activo por escaneo */}
          {filtroCodigo && (
            <div className="d-flex align-items-center gap-2 mb-3">
              <span className="text-muted">
                Mostrando artículo escaneado «{filtroCodigo}»
              </span>
              <Button
                variant="outline-secondary"
                size="sm"
                onClick={() => setFiltroCodigo(null)}
              >
                Limpiar
              </Button>
            </div>
          )}

          {/* --------------------------- Modal: código escaneado sin producto */}
          <ModalArticuloInexistente
            show={codigoInexistente !== null}
            codigo={codigoInexistente ?? ""}
            puedeAgregar
            onCancelar={() => setCodigoInexistente(null)}
            onAgregar={() => {
              setCodigoAltaInicial(codigoInexistente ?? undefined);
              setCodigoInexistente(null);
              setShowModal(true);
            }}
          />

          {/* ---------------------------------------------EMPIEZA LA TABLA */}

          <Table striped bordered hover responsive="md">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Imagen</th>
                <th>Descripción</th>
                <th>Categoria</th>

                <th>Precio</th>
                <th>Cantidad</th>
                <th>Opciones</th>
              </tr>
            </thead>
            <tbody>
              {error && <p className="catalogo-error">{error}</p>}

              {productosVisibles.map((producto) => (
                <tr>
                  <td>{producto.nombre}</td>
                  <td
                    style={estiloCelda}
                    onClick={toggleExpandir}
                    title={
                      expandido ? "Click para contraer" : "Click para ver más"
                    }
                  >
                    {producto.imagen}
                  </td>
                  <td>{producto.descripcion}</td>
                  <td>{producto.categoria}</td>
                  <td>{producto.precio}</td>
                  <td>{producto.cantidad}</td>
                  <td>
                    <Button
                      variant="danger"
                      onClick={() => {
                        setProductoSeleccionado(producto.id);
                        setShowEliminar(true);
                      }}
                    >
                      <BsFillTrash3Fill />
                    </Button>
                    <ModalEliminarProducto
                      show={showEliminar}
                      productoId={productoSeleccionado || ""}
                      onHide={() => setShowEliminar(false)}
                      onEliminado={cargarProductos}
                    />
                    <Button
                      variant="success"
                      onClick={() => {
                        setProductoEditar(producto);
                        setShowUpdate(true);
                      }}
                    >
                      <RxUpdate />
                    </Button>

                    <ModalActualizarProducto
                      show={showUpdate}
                      producto={productoEditar}
                      onHide={() => setShowUpdate(false)}
                      onProductoActualizado={cargarProductos}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Tab>
        <Tab eventKey="profile" title="Configuración">
          <ConfiguracionUsuarios />
        </Tab>
        {/* <Tab eventKey="contact" title="Contact">
          Tab content for Contact
        </Tab> */}
      </Tabs>
    </div>
  );
}

// --------------------------------------------------------------------------
// Pestaña "Configuración": usuarios existentes con su foto de perfil y rol.
// La contraseña no se muestra (es un hash irreversible). Solo el usuario
// logueado puede cambiar SU foto; solo un 'dueno' puede cambiar roles (y no
// el suyo propio). El nuevo rol aplica en el próximo login de ese usuario.
// --------------------------------------------------------------------------

const AVATAR_PX = 44;

const ETIQUETA_ROL: Record<Rol, string> = {
  dueno: "Dueño",
  empleado: "Empleado",
};

function Avatar({ usuario }: { usuario: Usuario }) {
  const estiloBase: CSSProperties = {
    width: AVATAR_PX,
    height: AVATAR_PX,
    borderRadius: "50%",
    objectFit: "cover",
    flexShrink: 0,
  };

  if (usuario.foto_url) {
    return (
      <img
        src={usuario.foto_url}
        alt={`Foto de ${usuario.nombre}`}
        style={estiloBase}
      />
    );
  }

  return (
    <span
      aria-hidden="true"
      style={{
        ...estiloBase,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--lp-color-secondary, #6c757d)",
        color: "#fff",
        fontWeight: 600,
        textTransform: "uppercase",
      }}
    >
      {usuario.nombre.trim().charAt(0) || "?"}
    </span>
  );
}

function ConfiguracionUsuarios() {
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  const [subiendo, setSubiendo] = useState(false);
  const [rolEnCurso, setRolEnCurso] = useState<string | null>(null);
  const inputFotoRef = useRef<HTMLInputElement>(null);

  const usuarioActualId = localStorage.getItem("user_id");
  const soyDueno = localStorage.getItem("rol") === "dueno";

  const cargarUsuarios = async () => {
    setCargando(true);
    setError(null);
    try {
      setUsuarios(await obtenerUsuarios());
    } catch {
      setError("No se pudieron cargar los usuarios");
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => {
    cargarUsuarios();
  }, []);

  const alElegirFoto = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // permite volver a elegir el mismo archivo
    if (!file) return;

    setSubiendo(true);
    setError(null);
    try {
      const { foto_url } = await subirFotoPerfil(file);
      setUsuarios((prev) =>
        prev.map((u) =>
          u.id === usuarioActualId ? { ...u, foto_url } : u,
        ),
      );
      if (foto_url) {
        localStorage.setItem("foto_url", foto_url);
        // Avisa al navbar (Menu.tsx) para que refresque el avatar sin recargar.
        window.dispatchEvent(new Event("perfil:foto"));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo subir la foto");
    } finally {
      setSubiendo(false);
    }
  };

  const alCambiarRol = async (usuario: Usuario, nuevoRol: Rol) => {
    if (nuevoRol === usuario.rol) return;
    setRolEnCurso(usuario.id);
    setError(null);
    try {
      await cambiarRol(usuario.id, nuevoRol);
      setUsuarios((prev) =>
        prev.map((u) => (u.id === usuario.id ? { ...u, rol: nuevoRol } : u)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cambiar el rol");
    } finally {
      setRolEnCurso(null);
    }
  };

  return (
    <div>
      <h3 className="h5 mb-3">Usuarios</h3>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <input
        ref={inputFotoRef}
        type="file"
        accept="image/*"
        hidden
        onChange={alElegirFoto}
      />

      {cargando ? (
        <Spinner animation="border" role="status" size="sm" />
      ) : (
        <Table striped bordered hover responsive="md" style={{ maxWidth: 640 }}>
          <thead>
            <tr>
              <th style={{ width: AVATAR_PX + 24 }}>Foto</th>
              <th>Nombre</th>
              <th style={{ width: 150 }}>Rol</th>
              <th style={{ width: 150 }} />
            </tr>
          </thead>
          <tbody>
            {usuarios.length === 0 ? (
              <tr>
                <td colSpan={4} className="text-center text-muted">
                  Sin usuarios registrados
                </td>
              </tr>
            ) : (
              usuarios.map((u) => {
                const esActual = u.id === usuarioActualId;
                // Un dueño cambia roles de los demás, nunca el suyo propio.
                const puedeEditarRol = soyDueno && !esActual;
                return (
                  <tr key={u.id}>
                    <td>
                      <Avatar usuario={u} />
                    </td>
                    <td className="align-middle">
                      {u.nombre}
                      {esActual && (
                        <span className="badge bg-primary ms-2">tú</span>
                      )}
                    </td>
                    <td className="align-middle">
                      {puedeEditarRol ? (
                        <Form.Select
                          size="sm"
                          value={u.rol}
                          disabled={rolEnCurso === u.id}
                          onChange={(e) =>
                            alCambiarRol(u, e.target.value as Rol)
                          }
                        >
                          <option value="empleado">Empleado</option>
                          <option value="dueno">Dueño</option>
                        </Form.Select>
                      ) : (
                        ETIQUETA_ROL[u.rol]
                      )}
                    </td>
                    <td className="align-middle">
                      {esActual && (
                        <Button
                          size="sm"
                          variant="outline-primary"
                          disabled={subiendo}
                          onClick={() => inputFotoRef.current?.click()}
                        >
                          {subiendo ? "Subiendo…" : "Cambiar foto"}
                        </Button>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </Table>
      )}
    </div>
  );
}

export default Admin;
