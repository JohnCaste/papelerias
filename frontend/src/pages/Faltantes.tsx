import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Modal } from "react-bootstrap";
import {
  AlertCircle,
  BookOpen,
  Check,
  Copy,
  Mail,
  MessageCircle,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { buscarProductos } from "../services/catalogo";
import { obtenerSucursal } from "../services/sucursal";
import {
  armarTexto,
  asuntoCorreo,
  cambiarEstadoFaltante,
  crearFaltante,
  editarFaltante,
  eliminarFaltante,
  enlaceCorreo,
  enlaceWhatsApp,
  ErrorFaltantes,
  fechaHoy,
  LIMITE_MAILTO,
  obtenerFaltantes,
  type EstadoFaltantes,
  type Faltante,
} from "../services/faltantes";
import "./Faltantes.css";

/* ==========================================================================
   Lista de faltantes · todos los usuarios, todas las sucursales.
   - Cualquiera agrega (del catálogo o texto libre) y edita cantidad/nota.
   - Solo la dueña marca comprado y envía la lista (WhatsApp / correo /
     copiar). El backend aplica las mismas reglas.
   - Funciona sin internet: el backend guarda en un journal local y lo sube
     a BigQuery después; "pendientes_de_subir" avisa cuántos cambios faltan.
   ========================================================================== */

interface Sugerencia {
  id: string;
  nombre: string;
  marca?: string | null;
  categoria?: string | null;
  stock?: number | null;
}

type Pestana = "pendientes" | "comprados";

/* Avisa al menú (contador) que la lista cambió. */
function avisarMenu(pendientes: number) {
  window.dispatchEvent(new CustomEvent("faltantes:cambio", { detail: pendientes }));
}

function cuando(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const hoy = new Date();
  const ayer = new Date();
  ayer.setDate(hoy.getDate() - 1);
  const hora = d.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit", hour12: false });
  if (d.toDateString() === hoy.toDateString()) return `hoy ${hora}`;
  if (d.toDateString() === ayer.toDateString()) return `ayer ${hora}`;
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
}

const mismaClave = (a: string, b: string) =>
  a.trim().replace(/\s+/g, " ").toLocaleLowerCase("es") === b.trim().replace(/\s+/g, " ").toLocaleLowerCase("es");

export default function Faltantes() {
  const esDueno = localStorage.getItem("rol") === "dueno";
  const usuarioId = localStorage.getItem("user_id");

  const [estado, setEstado] = useState<EstadoFaltantes | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pestana, setPestana] = useState<Pestana>("pendientes");
  const [sucursal, setSucursal] = useState("La Papelería");
  const [aviso, setAviso] = useState<string | null>(null);

  // ---- formulario de alta
  const [texto, setTexto] = useState("");
  const [elegido, setElegido] = useState<Sugerencia | null>(null);
  const [cantidad, setCantidad] = useState("");
  const [nota, setNota] = useState("");
  const [sugerencias, setSugerencias] = useState<Sugerencia[]>([]);
  const [abierto, setAbierto] = useState(false);
  const [activo, setActivo] = useState(0);
  const [guardando, setGuardando] = useState(false);
  const [errorCampo, setErrorCampo] = useState<{ campo?: string; mensaje: string } | null>(null);
  const cajaRef = useRef<HTMLDivElement>(null);

  // ---- modales
  const [editando, setEditando] = useState<Faltante | null>(null);
  const [editCantidad, setEditCantidad] = useState("");
  const [editNota, setEditNota] = useState("");
  const [borrando, setBorrando] = useState<Faltante | null>(null);

  const cargar = useCallback(async () => {
    try {
      const datos = await obtenerFaltantes();
      setEstado(datos);
      setError(null);
      avisarMenu(datos.pendientes.length);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la lista");
    }
  }, []);

  useEffect(() => {
    cargar();
    obtenerSucursal()
      .then((s) => setSucursal(s.nombre))
      .catch(() => undefined);
  }, [cargar]);

  // Búsqueda en catálogo con debounce (lee el espejo local: sin internet ok).
  useEffect(() => {
    const q = texto.trim();
    if (elegido || q.length < 2) {
      setSugerencias([]);
      return;
    }
    let vigente = true;
    const t = window.setTimeout(() => {
      buscarProductos({ q, limit: 8 })
        .then((r) => {
          if (vigente) {
            setSugerencias((r.items ?? []) as Sugerencia[]);
            setActivo(0);
          }
        })
        .catch(() => vigente && setSugerencias([]));
    }, 250);
    return () => {
      vigente = false;
      window.clearTimeout(t);
    };
  }, [texto, elegido]);

  // Cerrar sugerencias al hacer clic fuera.
  useEffect(() => {
    const cerrar = (e: MouseEvent) => {
      if (cajaRef.current && !cajaRef.current.contains(e.target as Node)) setAbierto(false);
    };
    document.addEventListener("mousedown", cerrar);
    return () => document.removeEventListener("mousedown", cerrar);
  }, []);

  useEffect(() => {
    if (!aviso) return;
    const t = window.setTimeout(() => setAviso(null), 2500);
    return () => window.clearTimeout(t);
  }, [aviso]);

  const pendientes = useMemo(() => estado?.pendientes ?? [], [estado]);
  const comprados = useMemo(() => estado?.comprados ?? [], [estado]);
  const lista = pestana === "pendientes" ? pendientes : comprados;

  const textoLibreRepetido = useMemo(
    () => !elegido && texto.trim() !== "" && pendientes.some((f) => !f.producto_id && mismaClave(f.nombre, texto)),
    [elegido, texto, pendientes],
  );

  const mensaje = useMemo(() => armarTexto(sucursal, fechaHoy(), pendientes), [sucursal, pendientes]);
  const correoLargo = enlaceCorreo(asuntoCorreo(sucursal, fechaHoy()), mensaje).length > LIMITE_MAILTO;

  // Opciones del desplegable: productos + "texto libre" al final.
  const opciones = abierto && !elegido && texto.trim() ? [...sugerencias, null] : [];

  function elegir(op: Sugerencia | null) {
    if (op) {
      setElegido(op);
      setTexto(op.nombre);
    } else {
      setElegido(null);
      setTexto(texto.trim());
    }
    setAbierto(false);
  }

  function teclaBuscador(e: KeyboardEvent<HTMLInputElement>) {
    if (!opciones.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActivo((i) => (i + 1) % opciones.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActivo((i) => (i - 1 + opciones.length) % opciones.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      elegir(opciones[activo] ?? null);
    } else if (e.key === "Escape") {
      setAbierto(false);
    }
  }

  async function agregar(e: FormEvent) {
    e.preventDefault();
    setErrorCampo(null);
    if (!texto.trim()) {
      setErrorCampo({ campo: "nombre", mensaje: "Escribe o busca un producto" });
      return;
    }
    setGuardando(true);
    try {
      await crearFaltante({
        nombre: elegido ? elegido.nombre : texto,
        producto_id: elegido?.id ?? null,
        cantidad: cantidad ? Number(cantidad) : null,
        nota: nota || null,
      });
      setTexto("");
      setElegido(null);
      setCantidad("");
      setNota("");
      setPestana("pendientes");
      await cargar();
    } catch (err) {
      if (err instanceof ErrorFaltantes) {
        setErrorCampo({
          campo: err.campo,
          mensaje: err.status === 409 ? `${err.message}. Edita su cantidad o nota en la lista.` : err.message,
        });
      } else {
        setErrorCampo({ mensaje: "No se pudo agregar" });
      }
    } finally {
      setGuardando(false);
    }
  }

  async function alternarComprado(f: Faltante) {
    try {
      await cambiarEstadoFaltante(f.faltante_id, f.estado === "pendiente" ? "comprado" : "pendiente");
      await cargar();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cambiar el estado");
    }
  }

  function abrirEdicion(f: Faltante) {
    setEditando(f);
    setEditCantidad(f.cantidad ? String(f.cantidad) : "");
    setEditNota(f.nota ?? "");
    setErrorCampo(null);
  }

  async function guardarEdicion(e: FormEvent) {
    e.preventDefault();
    if (!editando) return;
    try {
      await editarFaltante(editando.faltante_id, {
        cantidad: editCantidad ? Number(editCantidad) : null,
        nota: editNota || null,
      });
      setEditando(null);
      await cargar();
    } catch (err) {
      setErrorCampo({ mensaje: err instanceof Error ? err.message : "No se pudo guardar" });
    }
  }

  async function confirmarBorrado() {
    if (!borrando) return;
    try {
      await eliminarFaltante(borrando.faltante_id);
      setBorrando(null);
      await cargar();
    } catch (err) {
      setBorrando(null);
      setError(err instanceof Error ? err.message : "No se pudo eliminar");
    }
  }

  function enviarWhatsApp() {
    window.open(enlaceWhatsApp(mensaje), "_blank", "noopener");
  }

  function enviarCorreo() {
    window.location.href = enlaceCorreo(asuntoCorreo(sucursal, fechaHoy()), mensaje);
  }

  async function copiar() {
    try {
      await navigator.clipboard.writeText(mensaje);
      setAviso("Lista copiada");
    } catch {
      setAviso("No se pudo copiar: selecciona el texto a mano");
    }
  }

  const puedeEliminar = (f: Faltante) => esDueno || f.usuario_id === usuarioId;

  return (
    <div className="faltantes">
      <header className="faltantes-encabezado">
        <div>
          <h1>Lista de faltantes</h1>
          <p>
            {esDueno
              ? "Anota lo que se acabó. La lista se manda por WhatsApp o correo."
              : "¿Se acabó algo? Anótalo aquí."}
          </p>
        </div>
        {!!estado?.pendientes_de_subir && (
          <span className="faltantes-sin-subir" title="Se suben solos cuando hay internet">
            <RefreshCw size={14} aria-hidden="true" />
            {estado.pendientes_de_subir} {estado.pendientes_de_subir === 1 ? "cambio sin subir" : "cambios sin subir"}
          </span>
        )}
      </header>

      {error && (
        <div className="faltantes-alerta" role="alert">
          <AlertCircle size={16} aria-hidden="true" />
          <span>{error}</span>
          <button type="button" className="faltantes-icono" aria-label="Cerrar aviso" onClick={() => setError(null)}>
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      )}

      {/* ---------------------------------------------------------- alta */}
      <section className="faltantes-tarjeta faltantes-alta" aria-labelledby="t-agregar">
        <h2 id="t-agregar">Agregar faltante</h2>
        <form className="faltantes-form" onSubmit={agregar} noValidate>
          <div className="faltantes-campo faltantes-campo--producto" ref={cajaRef}>
            <label htmlFor="f-producto">Producto</label>
            <div className="faltantes-buscador">
              <Search size={16} aria-hidden="true" className="faltantes-buscador__lupa" />
              <input
                id="f-producto"
                type="text"
                autoComplete="off"
                role="combobox"
                aria-expanded={opciones.length > 0}
                aria-controls="f-sugerencias"
                aria-invalid={errorCampo?.campo === "nombre"}
                placeholder="Buscar en catálogo o escribir…"
                value={texto}
                maxLength={120}
                onChange={(e) => {
                  setTexto(e.target.value);
                  setElegido(null);
                  setAbierto(true);
                  setErrorCampo(null);
                }}
                onFocus={() => setAbierto(true)}
                onKeyDown={teclaBuscador}
              />
              {elegido && (
                <span className="faltantes-chip faltantes-chip--catalogo faltantes-buscador__chip">Catálogo</span>
              )}
            </div>
            {opciones.length > 0 && (
              <ul id="f-sugerencias" role="listbox" className="faltantes-sugerencias">
                {opciones.map((op, i) => (
                  <li
                    key={op ? op.id : "__libre"}
                    role="option"
                    aria-selected={i === activo}
                    className={i === activo ? "activo" : undefined}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      elegir(op);
                    }}
                    onMouseEnter={() => setActivo(i)}
                  >
                    {op ? (
                      <>
                        <span className="faltantes-sugerencias__icono">
                          <BookOpen size={16} aria-hidden="true" />
                        </span>
                        <span className="faltantes-sugerencias__texto">
                          <strong>{op.nombre}</strong>
                          <small>{[op.marca, op.categoria].filter(Boolean).join(" · ")}</small>
                        </span>
                        {op.stock != null && <small>Stock {op.stock}</small>}
                      </>
                    ) : (
                      <>
                        <span className="faltantes-sugerencias__icono faltantes-sugerencias__icono--libre">
                          <Plus size={16} aria-hidden="true" />
                        </span>
                        <span>
                          Agregar <strong>«{texto.trim()}»</strong> como texto libre
                        </span>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="faltantes-campo faltantes-campo--cantidad">
            <label htmlFor="f-cantidad">Cantidad</label>
            <input
              id="f-cantidad"
              type="number"
              min={1}
              step={1}
              inputMode="numeric"
              aria-invalid={errorCampo?.campo === "cantidad"}
              value={cantidad}
              onChange={(e) => setCantidad(e.target.value)}
            />
          </div>
          <div className="faltantes-campo faltantes-campo--nota">
            <label htmlFor="f-nota">Nota (opcional)</label>
            <input
              id="f-nota"
              type="text"
              maxLength={200}
              placeholder="Marca, color, tamaño…"
              aria-invalid={errorCampo?.campo === "nota"}
              value={nota}
              onChange={(e) => setNota(e.target.value)}
            />
          </div>
          <button type="submit" className="faltantes-boton faltantes-boton--primario" disabled={guardando}>
            <Plus size={16} aria-hidden="true" />
            Agregar
          </button>
        </form>
        {textoLibreRepetido && !errorCampo && (
          <p className="faltantes-nota-aviso">Ya hay un «{texto.trim()}» en pendientes. Puedes agregarlo de todos modos.</p>
        )}
        {errorCampo && !editando && (
          <p className="faltantes-error-campo" role="alert">
            {errorCampo.mensaje}
          </p>
        )}
      </section>

      {/* ---------------------------------------------------------- lista */}
      <section className="faltantes-tarjeta faltantes-lista" aria-labelledby="t-lista">
        <div className="faltantes-lista__barra">
          <h2 id="t-lista">Faltantes</h2>
          <div role="tablist" aria-label="Estado" className="faltantes-pestanas">
            <button
              type="button"
              role="tab"
              aria-selected={pestana === "pendientes"}
              onClick={() => setPestana("pendientes")}
            >
              Pendientes ({pendientes.length})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={pestana === "comprados"}
              onClick={() => setPestana("comprados")}
            >
              Comprados
            </button>
          </div>
        </div>
        {pestana === "comprados" && (
          <p className="faltantes-lista__ayuda">
            Últimos 30 días.{esDueno && " Desmarca uno para regresarlo a pendientes."}
          </p>
        )}

        {estado === null && !error ? (
          <p className="faltantes-vacio">Cargando…</p>
        ) : lista.length === 0 ? (
          <p className="faltantes-vacio">
            {pestana === "pendientes" ? "No hay faltantes pendientes." : "Nada comprado en los últimos 30 días."}
          </p>
        ) : (
          <ul className="faltantes-filas">
            {lista.map((f) => {
              const comprado = f.estado === "comprado";
              return (
                <li key={f.faltante_id} className={comprado ? "comprado" : undefined}>
                  {esDueno && (
                    <input
                      type="checkbox"
                      id={`chk-${f.faltante_id}`}
                      checked={comprado}
                      onChange={() => alternarComprado(f)}
                      aria-label={comprado ? `Regresar «${f.nombre}» a pendiente` : `Marcar «${f.nombre}» como comprado`}
                    />
                  )}
                  <div className="faltantes-filas__nombre">
                    <span className="faltantes-filas__titulo">
                      {esDueno ? <label htmlFor={`chk-${f.faltante_id}`}>{f.nombre}</label> : f.nombre}
                      {!comprado && (
                        <span className={`faltantes-chip ${f.producto_id ? "faltantes-chip--catalogo" : "faltantes-chip--libre"}`}>
                          {f.producto_id ? "Catálogo" : "Texto libre"}
                        </span>
                      )}
                    </span>
                    {f.nota && <span className="faltantes-filas__nota">“{f.nota}”</span>}
                  </div>
                  <span className="faltantes-filas__cantidad">{f.cantidad ? `×${f.cantidad}` : "—"}</span>
                  <span className="faltantes-filas__meta">
                    {comprado ? (
                      <>
                        <Check size={14} aria-hidden="true" /> {cuando(f.comprado_en)} · {f.comprado_por ?? "—"}
                      </>
                    ) : (
                      <>
                        {f.registrado_por ?? "—"} · {cuando(f.creado_en)}
                      </>
                    )}
                  </span>
                  <div className="faltantes-filas__acciones">
                    {!comprado && (
                      <button type="button" className="faltantes-icono" aria-label={`Editar «${f.nombre}»`} onClick={() => abrirEdicion(f)}>
                        <Pencil size={16} aria-hidden="true" />
                      </button>
                    )}
                    {puedeEliminar(f) && (
                      <button
                        type="button"
                        className="faltantes-icono faltantes-icono--peligro"
                        aria-label={`Eliminar «${f.nombre}»`}
                        onClick={() => setBorrando(f)}
                      >
                        <Trash2 size={16} aria-hidden="true" />
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {esDueno && pestana === "pendientes" && (
          <div className="faltantes-envio">
            <span className="faltantes-envio__texto">
              {pendientes.length ? (
                <>
                  Enviar los <strong>{pendientes.length} pendientes</strong>:
                </>
              ) : (
                "Sin pendientes que enviar."
              )}
            </span>
            <button type="button" className="faltantes-boton faltantes-boton--whatsapp" disabled={!pendientes.length} onClick={enviarWhatsApp}>
              <MessageCircle size={16} aria-hidden="true" />
              WhatsApp
            </button>
            <button type="button" className="faltantes-boton faltantes-boton--correo" disabled={!pendientes.length} onClick={enviarCorreo}>
              <Mail size={16} aria-hidden="true" />
              Correo
            </button>
            <button type="button" className="faltantes-boton faltantes-boton--secundario" disabled={!pendientes.length} onClick={copiar}>
              <Copy size={16} aria-hidden="true" />
              Copiar lista
            </button>
            {correoLargo && !!pendientes.length && (
              <p className="faltantes-envio__aviso">
                La lista es larga: algunos programas de correo la cortan. Si pasa, usa «Copiar lista».
              </p>
            )}
          </div>
        )}
      </section>

      {aviso && (
        <div className="faltantes-toast" role="status">
          <Check size={16} aria-hidden="true" />
          {aviso}
        </div>
      )}

      {/* ---------------------------------------------------------- modales */}
      <Modal show={!!editando} onHide={() => setEditando(null)} centered>
        <form onSubmit={guardarEdicion} noValidate>
          <Modal.Header closeButton>
            <Modal.Title>Editar faltante</Modal.Title>
          </Modal.Header>
          <Modal.Body className="faltantes-modal">
            <p className="faltantes-modal__nombre">{editando?.nombre}</p>
            <div className="faltantes-campo">
              <label htmlFor="e-cantidad">Cantidad</label>
              <input id="e-cantidad" type="number" min={1} step={1} value={editCantidad} onChange={(e) => setEditCantidad(e.target.value)} />
            </div>
            <div className="faltantes-campo">
              <label htmlFor="e-nota">Nota</label>
              <input id="e-nota" type="text" maxLength={200} value={editNota} onChange={(e) => setEditNota(e.target.value)} />
            </div>
            {errorCampo && editando && (
              <p className="faltantes-error-campo" role="alert">
                {errorCampo.mensaje}
              </p>
            )}
          </Modal.Body>
          <Modal.Footer>
            <button type="button" className="faltantes-boton faltantes-boton--secundario" onClick={() => setEditando(null)}>
              Cancelar
            </button>
            <button type="submit" className="faltantes-boton faltantes-boton--primario">
              Guardar
            </button>
          </Modal.Footer>
        </form>
      </Modal>

      <Modal show={!!borrando} onHide={() => setBorrando(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title>Eliminar faltante</Modal.Title>
        </Modal.Header>
        <Modal.Body>
          ¿Eliminar <strong>«{borrando?.nombre}»</strong> de la lista?
        </Modal.Body>
        <Modal.Footer>
          <button type="button" className="faltantes-boton faltantes-boton--secundario" onClick={() => setBorrando(null)}>
            Cancelar
          </button>
          <button type="button" className="faltantes-boton faltantes-boton--peligro" onClick={confirmarBorrado}>
            Eliminar
          </button>
        </Modal.Footer>
      </Modal>
    </div>
  );
}
