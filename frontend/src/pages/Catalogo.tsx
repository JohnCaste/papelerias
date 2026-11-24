import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Plus,
  Search,
  X,
  Package,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import {
  buscarProductos,
  obtenerCategorias,
  obtenerMarcas,
} from "../services/catalogo";
import ProductoCard from "../components/ProductoCard";
import ModalAgregarProducto from "../components/AgregarProModal";
import ModalArticuloInexistente from "../components/ModalArticuloInexistente";
import { useScannerGun } from "../hooks/useScannerGun";
import "./Catalogo.css";

/* ==========================================================================
   Catálogo · recreación del handoff "Catalogo lapape.dc.html".
   - Grilla de ProductoCard con badge de stock.
   - Búsqueda y filtros SERVER-SIDE (GET /api/catalogo/buscar): el término del
     navbar, la categoría y la marca se resuelven sobre TODO el catálogo, no
     sobre la página cargada. El único filtro en cliente es el orden de la
     página actual.
   - Paginación real: la respuesta trae { items, total }; "Siguiente" se
     deshabilita cuando offset + LIMIT >= total.
   - La tarjeta es solo lectura: acción única "Ver" que lleva a /admin y abre
     el modal de edición de ese producto. Editar/eliminar viven en
     Administración.
   ========================================================================== */

interface Producto {
  id: string;
  nombre: string;
  categoria?: string;
  descripcion?: string;
  imagen?: string;
  marca?: string;
  precio: number;
  cantidad: number;
  costo?: number;
  papeleria?: string;
}

type Orden = "nombre-asc" | "nombre-desc" | "precio-asc" | "precio-desc";

interface CatalogoProps {
  filtro?: string;
  rol?: "admin" | "vendedor";
}

const LIMIT = 12;

function Catalogo({ filtro = "", rol = "admin" }: CatalogoProps) {
  const esAdmin = rol === "admin";
  const navigate = useNavigate();

  const [productos, setProductos] = useState<Producto[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [recargar, setRecargar] = useState(0);

  // filtros (la búsqueda arranca desde el navbar via prop `filtro`)
  const [q, setQ] = useState(filtro);
  // `q` con debounce de 300ms: evita disparar una búsqueda server-side por
  // cada tecla (cada una es una llamada a BigQuery). Solo el término de
  // texto espera; categoría, marca y paginación siguen siendo inmediatos.
  const [qDebounced, setQDebounced] = useState(filtro);
  const [categoria, setCategoria] = useState("todas");
  const [marca, setMarca] = useState("todas");
  const [orden, setOrden] = useState<Orden>("nombre-asc");

  // opciones de los selectores (todo el catálogo, no la página actual)
  const [categorias, setCategorias] = useState<string[]>([]);
  const [marcas, setMarcas] = useState<string[]>([]);

  // modal de alta
  const [showAgregar, setShowAgregar] = useState(false);
  const [codigoAltaInicial, setCodigoAltaInicial] = useState<string | undefined>(
    undefined,
  );

  // código escaneado que no dio resultados -> modal "artículo inexistente"
  const [codigoInexistente, setCodigoInexistente] = useState<string | null>(null);
  // marca que el próximo resultado de búsqueda viene de un escaneo (no de
  // escritura manual): solo entonces se ofrece dar de alta el código.
  const escaneoPendiente = useRef(false);

  useEffect(() => {
    setQ(filtro);
  }, [filtro]);

  // Pistola de código de barras: al leer, el código pasa a ser el término de
  // búsqueda y la grilla/paginación existentes muestran el producto. El
  // `useEffect` de filtros ya reinicia `offset` a 0.
  useScannerGun((codigo) => {
    escaneoPendiente.current = true;
    setQ(codigo);
  });

  // opciones de categoría y marca: una sola carga
  useEffect(() => {
    obtenerCategorias()
      .then(setCategorias)
      .catch(() => setCategorias([]));
    obtenerMarcas()
      .then(setMarcas)
      .catch(() => setMarcas([]));
  }, [recargar]);

  // debounce: `qDebounced` solo se actualiza 300ms después de la última
  // tecla en `q`. Un escaneo de pistola también pasa por aquí -- no hay
  // caso especial para saltarse la espera.
  useEffect(() => {
    const id = setTimeout(() => setQDebounced(q), 300);
    return () => clearTimeout(id);
  }, [q]);

  // cualquier cambio de filtro vuelve a la primera página
  useEffect(() => {
    setOffset(0);
  }, [qDebounced, categoria, marca]);

  useEffect(() => {
    let vivo = true;
    setLoading(true);
    setError("");

    buscarProductos({
      q: qDebounced.trim() || undefined,
      categoria: categoria === "todas" ? undefined : categoria,
      marca: marca === "todas" ? undefined : marca,
      limit: LIMIT,
      offset,
    })
      .then((data) => {
        if (!vivo) return;
        setProductos(Array.isArray(data.items) ? (data.items as Producto[]) : []);
        const totalNuevo = typeof data.total === "number" ? data.total : 0;
        setTotal(totalNuevo);

        // Si este resultado responde a un escaneo y no encontró nada, ofrecer
        // dar de alta el código. Escribir a mano nunca toca `escaneoPendiente`.
        if (escaneoPendiente.current) {
          escaneoPendiente.current = false;
          if (totalNuevo === 0) setCodigoInexistente(qDebounced.trim());
        }
      })
      .catch(() => {
        if (!vivo) return;
        setError("No se pudo cargar el catálogo");
      })
      .finally(() => {
        if (vivo) setLoading(false);
      });

    return () => {
      vivo = false;
    };
  }, [qDebounced, categoria, marca, offset, recargar]);

  // orden: único filtro que sigue en cliente, sobre la página cargada
  const visibles = useMemo(() => {
    return [...productos].sort((a, b) => {
      switch (orden) {
        case "nombre-desc":
          return b.nombre.localeCompare(a.nombre, "es");
        case "precio-asc":
          return a.precio - b.precio;
        case "precio-desc":
          return b.precio - a.precio;
        default:
          return a.nombre.localeCompare(b.nombre, "es");
      }
    });
  }, [productos, orden]);

  const hayFiltros =
    q.trim() !== "" || categoria !== "todas" || marca !== "todas";

  const limpiarFiltros = () => {
    setQ("");
    setCategoria("todas");
    setMarca("todas");
    setOrden("nombre-asc");
  };

  const recargarPagina = () => setRecargar((n) => n + 1);

  const desde = total === 0 ? 0 : offset + 1;
  const hasta = offset + productos.length;
  const haySiguiente = offset + LIMIT < total;

  return (
    <div className="catalogo-page">
      {/* ---------- header ---------- */}
      <header className="catalogo-header">
        <div>
          <h1 className="catalogo-title">Catálogo</h1>
          <p className="catalogo-sub">
            {loading
              ? "Cargando productos…"
              : total > 0
                ? `Mostrando ${desde}–${hasta} de ${total}`
                : "Sin productos"}
          </p>
        </div>
        {esAdmin && (
          <button
            type="button"
            className="catalogo-btn catalogo-btn--primary"
            onClick={() => setShowAgregar(true)}
            disabled={loading}
          >
            <Plus size={16} strokeWidth={2} />
            Nuevo producto
          </button>
        )}
      </header>

      {/* ---------- barra de filtros ---------- */}
      <div className="catalogo-filtros">
        <span className="catalogo-search">
          <Search size={16} strokeWidth={2} />
          <input
            type="text"
            value={q}
            placeholder="Buscar por nombre o código de barras"
            onChange={(e) => setQ(e.target.value)}
            data-scanner-passthrough
          />
          {q && (
            <button
              type="button"
              className="catalogo-search-clear"
              aria-label="Limpiar búsqueda"
              onClick={() => setQ("")}
            >
              <X size={12} strokeWidth={2.5} />
            </button>
          )}
        </span>

        <select
          value={categoria}
          onChange={(e) => setCategoria(e.target.value)}
          aria-label="Filtrar por categoría"
        >
          <option value="todas">Todas las categorías</option>
          {categorias.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>

        <select
          value={marca}
          onChange={(e) => setMarca(e.target.value)}
          aria-label="Filtrar por marca"
        >
          <option value="todas">Todas las marcas</option>
          {marcas.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>

        <select
          value={orden}
          onChange={(e) => setOrden(e.target.value as Orden)}
          aria-label="Ordenar"
        >
          <option value="nombre-asc">Orden: Nombre A–Z</option>
          <option value="nombre-desc">Orden: Nombre Z–A</option>
          <option value="precio-asc">Orden: Precio ↑</option>
          <option value="precio-desc">Orden: Precio ↓</option>
        </select>
      </div>

      {/* ---------- error ---------- */}
      {error && (
        <div className="catalogo-alerta" role="alert">
          <AlertCircle size={18} strokeWidth={2.5} />
          <div className="catalogo-alerta__cuerpo">
            <div>
              <strong>No se pudo cargar el catálogo</strong>
              <span>
                El servidor no respondió. Revisá la conexión e intentá de nuevo.
              </span>
            </div>
            <button type="button" onClick={recargarPagina}>
              <RefreshCw size={14} strokeWidth={2} />
              Reintentar
            </button>
          </div>
        </div>
      )}

      {/* ---------- carga · skeletons ---------- */}
      {loading && !error && (
        <div className="catalogo-grid" aria-hidden>
          {Array.from({ length: LIMIT }).map((_, i) => (
            <div key={i} className="catalogo-skeleton">
              <div className="catalogo-skeleton__media" />
              <div className="catalogo-skeleton__body">
                <span className="catalogo-skeleton__line" />
                <span className="catalogo-skeleton__line catalogo-skeleton__line--sm" />
                <span className="catalogo-skeleton__line catalogo-skeleton__line--price" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ---------- vacío total ---------- */}
      {!loading && !error && total === 0 && !hayFiltros && (
        <div className="catalogo-estado catalogo-estado--vacio">
          <span className="catalogo-estado__icono">
            <Package size={26} strokeWidth={1.7} />
          </span>
          <h3>Todavía no hay productos</h3>
          <p>
            Cargá el primer producto para que aparezca en el catálogo y en el
            punto de venta.
          </p>
          {esAdmin && (
            <button
              type="button"
              className="catalogo-btn catalogo-btn--primary"
              onClick={() => setShowAgregar(true)}
            >
              <Plus size={16} strokeWidth={2} />
              Nuevo producto
            </button>
          )}
        </div>
      )}

      {/* ---------- sin resultados de búsqueda ---------- */}
      {!loading && !error && total === 0 && hayFiltros && (
        <div className="catalogo-estado">
          <span className="catalogo-estado__icono">
            <Search size={26} strokeWidth={1.7} />
          </span>
          <h3>Sin resultados{q.trim() && ` para “${q.trim()}”`}</h3>
          <p>Probá con menos palabras o quitá los filtros de categoría y marca.</p>
          <button
            type="button"
            className="catalogo-btn catalogo-btn--outline"
            onClick={limpiarFiltros}
          >
            Limpiar filtros
          </button>
        </div>
      )}

      {/* ---------- grilla ---------- */}
      {!loading && !error && visibles.length > 0 && (
        <div className="catalogo-grid">
          {visibles.map((p) => (
            <ProductoCard
              key={p.id}
              nombre={p.nombre}
              marca={p.marca}
              imagen={p.imagen}
              precio={p.precio}
              cantidad={p.cantidad}
              costo={p.costo}
              mostrarCosto={esAdmin && p.costo != null}
              soloLectura={!esAdmin}
              soloAccionVer={esAdmin}
              onVer={() =>
                navigate("/admin", { state: { editarProductoId: p.id } })
              }
            />
          ))}
        </div>
      )}

      {/* ---------- paginación ---------- */}
      {!error && total > 0 && (
        <div className="catalogo-pager">
          <button
            type="button"
            onClick={() => setOffset(Math.max(offset - LIMIT, 0))}
            disabled={offset === 0 || loading}
          >
            <ChevronLeft size={14} strokeWidth={2} />
            Anterior
          </button>
          <span className="catalogo-pager__estado">
            Página {Math.floor(offset / LIMIT) + 1} de{" "}
            {Math.max(1, Math.ceil(total / LIMIT))}
          </span>
          <button
            type="button"
            onClick={() => setOffset(offset + LIMIT)}
            disabled={loading || !haySiguiente}
          >
            Siguiente
            <ChevronRight size={14} strokeWidth={2} />
          </button>
        </div>
      )}

      {/* ---------- modal de alta ---------- */}
      {esAdmin && (
        <ModalAgregarProducto
          show={showAgregar}
          codigoInicial={codigoAltaInicial}
          onHide={() => {
            setShowAgregar(false);
            setCodigoAltaInicial(undefined);
          }}
          onProductoAgregado={() => {
            setCodigoAltaInicial(undefined);
            recargarPagina();
          }}
        />
      )}

      {/* ---------- código escaneado sin resultados ---------- */}
      <ModalArticuloInexistente
        show={codigoInexistente !== null}
        codigo={codigoInexistente ?? ""}
        puedeAgregar={esAdmin}
        onCancelar={() => setCodigoInexistente(null)}
        onAgregar={() => {
          setCodigoAltaInicial(codigoInexistente ?? undefined);
          setCodigoInexistente(null);
          setShowAgregar(true);
        }}
      />
    </div>
  );
}

export default Catalogo;
