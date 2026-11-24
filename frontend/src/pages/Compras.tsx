import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Modal } from "react-bootstrap";
import {
  AlertCircle,
  CloudOff,
  HandCoins,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import {
  abonarCompra,
  crearCompra,
  editarCompra,
  eliminarAbono,
  eliminarCompra,
  obtenerCompras,
  ErrorCompras,
  type Abono,
  type Compra,
  type DatosCompra,
  type EstadoCompras,
  type EstatusCompra,
} from "../services/compras";
import "./Compras.css";

/* ==========================================================================
   Compras de trabajadores · solo la dueña, solo sucursal lapape.
   Registro aparte: no toca ventas, cierres, desglose ni inventario.
   Importe, pagado, total y estatus los calcula el backend; aquí solo se
   muestran (la vista previa del formulario es orientativa).
   Funciona sin internet: el backend guarda en un journal local y lo sube
   a BigQuery después; "pendientes_subir" avisa cuántos cambios faltan.
   ========================================================================== */

const money = (n: number) =>
  "$ " +
  n.toLocaleString("es-MX", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const MESES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

// Fecha local (no UTC: después de las 6 pm UTC ya sería "mañana").
function hoyLocal(): string {
  const d = new Date();
  return [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, "0"),
    String(d.getDate()).padStart(2, "0"),
  ].join("-");
}

function fechaCorta(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y.slice(2)}`;
}

function nombreMes(clave: string): string {
  const [y, m] = clave.split("-");
  return `${MESES[Number(m) - 1]} ${y}`;
}

const ETIQUETA: Record<EstatusCompra, string> = {
  pendiente: "Pendiente",
  parcial: "Parcial",
  pagado: "Pagado",
};

type FiltroEstado = "abiertas" | "pagadas" | "todas";

interface Formulario {
  nombre: string;
  producto: string;
  cantidad: string;
  precio: string;
  fecha: string;
  pago: string;
}

const vacio = (hoy: string): Formulario => ({
  nombre: "",
  producto: "",
  cantidad: "1",
  precio: "",
  fecha: hoy,
  pago: "",
});

const num = (s: string) => {
  const n = Number(s);
  return Number.isFinite(n) ? n : 0;
};

function aDatos(f: Formulario, conPago: boolean): DatosCompra {
  const datos: DatosCompra = {
    nombre: f.nombre,
    producto: f.producto,
    cantidad: num(f.cantidad),
    precio: num(f.precio),
    fecha: f.fecha,
  };
  if (conPago) datos.pago = num(f.pago);
  return datos;
}

/* ---------- campos compartidos por alta y edición ---------- */
function CamposCompra({
  f,
  set,
  hoy,
  campoError,
  conPago,
}: {
  f: Formulario;
  set: (f: Formulario) => void;
  hoy: string;
  campoError?: string;
  conPago: boolean;
}) {
  const cls = (campo: string) =>
    "form-control" + (campoError === campo ? " is-invalid" : "");
  return (
    <>
      <label className="compras-campo compras-campo--nombre">
        <span>Nombre</span>
        <input
          className={cls("nombre")}
          list="compras-nombres"
          value={f.nombre}
          onChange={(e) => set({ ...f, nombre: e.target.value })}
          placeholder="Quién compra"
          maxLength={80}
          required
        />
      </label>
      <label className="compras-campo compras-campo--producto">
        <span>Producto</span>
        <input
          className={cls("producto")}
          value={f.producto}
          onChange={(e) => set({ ...f, producto: e.target.value })}
          placeholder="Qué se compró"
          maxLength={200}
          required
        />
      </label>
      <label className="compras-campo">
        <span>Cantidad</span>
        <input
          className={cls("cantidad")}
          type="number"
          min={1}
          step={1}
          inputMode="numeric"
          value={f.cantidad}
          onChange={(e) => set({ ...f, cantidad: e.target.value })}
          required
        />
      </label>
      <label className="compras-campo">
        <span>Precio unitario</span>
        <input
          className={cls("precio")}
          type="number"
          min={0}
          step="0.01"
          inputMode="decimal"
          value={f.precio}
          onChange={(e) => set({ ...f, precio: e.target.value })}
          placeholder="0.00"
          required
        />
      </label>
      {conPago && (
        <label className="compras-campo">
          <span>Pago</span>
          <input
            className={cls("pago")}
            type="number"
            min={0}
            step="0.01"
            inputMode="decimal"
            value={f.pago}
            onChange={(e) => set({ ...f, pago: e.target.value })}
            placeholder="0.00"
          />
        </label>
      )}
      <label className="compras-campo">
        <span>Fecha</span>
        <input
          className={cls("fecha")}
          type="date"
          max={hoy}
          value={f.fecha}
          onChange={(e) => set({ ...f, fecha: e.target.value })}
          required
        />
      </label>
    </>
  );
}

function Compras() {
  const [estado, setEstado] = useState<EstadoCompras | null>(null);
  const [cargando, setCargando] = useState(true);
  const [errorCarga, setErrorCarga] = useState("");

  const hoy = estado?.hoy ?? hoyLocal();

  // alta
  const [alta, setAlta] = useState<Formulario>(() => vacio(hoy));
  const [guardando, setGuardando] = useState(false);
  const [errorAlta, setErrorAlta] = useState<{ msg: string; campo?: string } | null>(null);

  // filtros
  const [filtro, setFiltro] = useState<FiltroEstado>("abiertas");
  const [persona, setPersona] = useState("");
  const [mes, setMes] = useState("");

  // modales
  const [abonando, setAbonando] = useState<Compra | null>(null);
  const [montoAbono, setMontoAbono] = useState("");
  const [fechaAbono, setFechaAbono] = useState(hoy);
  const [editando, setEditando] = useState<Compra | null>(null);
  const [formEdicion, setFormEdicion] = useState<Formulario>(() => vacio(hoy));
  const [confirmar, setConfirmar] = useState<
    | { tipo: "compra"; compra: Compra }
    | { tipo: "abono"; abono: Abono }
    | null
  >(null);
  const [errorModal, setErrorModal] = useState<{ msg: string; campo?: string } | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(() => {
    setErrorCarga("");
    return obtenerCompras()
      .then(setEstado)
      .catch((e: Error) => setErrorCarga(e.message || "No se pudo cargar la información"))
      .finally(() => setCargando(false));
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  /* ---------- derivados ---------- */
  const importeAlta = num(alta.precio) * Math.max(0, Math.floor(num(alta.cantidad)));
  const totalAlta = importeAlta - num(alta.pago);

  const mesesDisponibles = useMemo(() => {
    const claves = new Set<string>();
    estado?.compras.forEach((c) => claves.add(c.fecha.slice(0, 7)));
    estado?.abonos.forEach((a) => claves.add(a.fecha.slice(0, 7)));
    return [...claves].sort().reverse();
  }, [estado]);

  const comprasVisibles = useMemo(() => {
    if (!estado) return [];
    return estado.compras.filter((c) => {
      if (filtro === "abiertas" && c.estatus === "pagado") return false;
      if (filtro === "pagadas" && c.estatus !== "pagado") return false;
      if (persona && c.nombre !== persona) return false;
      if (mes && !c.fecha.startsWith(mes)) return false;
      return true;
    });
  }, [estado, filtro, persona, mes]);

  const abonosVisibles = useMemo(() => {
    if (!estado) return [];
    return estado.abonos.filter(
      (a) => (!persona || a.nombre === persona) && (!mes || a.fecha.startsWith(mes)),
    );
  }, [estado, persona, mes]);

  /* ---------- acciones ---------- */
  const enviarAlta = async (e: FormEvent) => {
    e.preventDefault();
    setGuardando(true);
    setErrorAlta(null);
    try {
      await crearCompra(aDatos(alta, true));
      setAlta({ ...vacio(hoy), fecha: alta.fecha });
      await cargar();
    } catch (err) {
      const e2 = err as ErrorCompras;
      setErrorAlta({ msg: e2.message, campo: e2.campo });
    } finally {
      setGuardando(false);
    }
  };

  const abrirAbono = (c: Compra) => {
    setErrorModal(null);
    setMontoAbono(String(c.total));
    setFechaAbono(hoy);
    setAbonando(c);
  };

  const abrirEdicion = (c: Compra) => {
    setErrorModal(null);
    setFormEdicion({
      nombre: c.nombre,
      producto: c.producto,
      cantidad: String(c.cantidad),
      precio: String(c.precio),
      fecha: c.fecha,
      pago: "",
    });
    setEditando(c);
  };

  const ejecutar = async (accion: () => Promise<unknown>, cerrar: () => void) => {
    setOcupado(true);
    setErrorModal(null);
    try {
      await accion();
      cerrar();
      await cargar();
    } catch (err) {
      const e2 = err as ErrorCompras;
      setErrorModal({ msg: e2.message, campo: e2.campo });
    } finally {
      setOcupado(false);
    }
  };

  /* ---------- render ---------- */
  if (cargando) {
    return (
      <div className="compras">
        <p className="compras-vacio">Cargando compras…</p>
      </div>
    );
  }

  if (!estado) {
    return (
      <div className="compras">
        <div className="compras-alerta compras-alerta--error" role="alert">
          <AlertCircle size={18} />
          <span>{errorCarga}</span>
          <button type="button" className="btn btn-sm btn-outline-secondary" onClick={cargar}>
            <RefreshCw size={14} /> Reintentar
          </button>
        </div>
      </div>
    );
  }

  const { resumen } = estado;
  const edicionImporte =
    num(formEdicion.precio) * Math.max(0, Math.floor(num(formEdicion.cantidad)));

  return (
    <div className="compras">
      <datalist id="compras-nombres">
        {estado.nombres.map((n) => (
          <option key={n} value={n} />
        ))}
      </datalist>

      <header className="compras-encabezado">
        <div>
          <h1>Compras de trabajadores</h1>
          <p>Registro aparte: no afecta ventas, cierres ni inventario.</p>
        </div>
        {estado.pendientes_subir > 0 && (
          <span
            className="compras-pendientes"
            title="Se guardaron en esta PC y se subirán solos cuando haya internet"
          >
            <CloudOff size={14} />
            {estado.pendientes_subir}{" "}
            {estado.pendientes_subir === 1 ? "cambio pendiente" : "cambios pendientes"} de subir
          </span>
        )}
      </header>

      {errorCarga && (
        <div className="compras-alerta compras-alerta--error" role="alert">
          <AlertCircle size={18} />
          <span>{errorCarga}</span>
        </div>
      )}

      <section className="compras-resumen" aria-label="Resumen">
        <div className="compras-tarjeta">
          <span className="compras-tarjeta__etq">Por cobrar</span>
          <span className="compras-tarjeta__val compras-tarjeta__val--destacado">
            {money(resumen.por_cobrar)}
          </span>
        </div>
        <div className="compras-tarjeta">
          <span className="compras-tarjeta__etq">Compras abiertas</span>
          <span className="compras-tarjeta__val">{resumen.compras_abiertas}</span>
        </div>
        <div className="compras-tarjeta">
          <span className="compras-tarjeta__etq">Abonado este mes</span>
          <span className="compras-tarjeta__val">{money(resumen.abonado_mes)}</span>
        </div>
      </section>

      <form className="compras-panel compras-alta" onSubmit={enviarAlta}>
        <h2>Nueva compra</h2>
        <div className="compras-alta__campos">
          <CamposCompra
            f={alta}
            set={setAlta}
            hoy={hoy}
            campoError={errorAlta?.campo}
            conPago
          />
        </div>
        <div className="compras-alta__pie">
          <span className="compras-alta__preview">
            Importe <strong>{money(importeAlta)}</strong>
            <span aria-hidden> · </span>
            Total <strong className={totalAlta < 0 ? "compras-negativo" : ""}>
              {money(totalAlta)}
            </strong>
          </span>
          {errorAlta && (
            <span className="compras-error" role="alert">
              {errorAlta.msg}
            </span>
          )}
          <button type="submit" className="btn btn-primary" disabled={guardando}>
            <Plus size={16} /> {guardando ? "Guardando…" : "Agregar"}
          </button>
        </div>
      </form>

      <section className="compras-panel">
        <div className="compras-filtros">
          <div className="compras-segmentos" role="group" aria-label="Estado">
            {(["abiertas", "pagadas", "todas"] as FiltroEstado[]).map((f) => (
              <button
                key={f}
                type="button"
                className={filtro === f ? "activo" : ""}
                aria-pressed={filtro === f}
                onClick={() => setFiltro(f)}
              >
                {f === "abiertas" ? "Abiertas" : f === "pagadas" ? "Pagadas" : "Todas"}
              </button>
            ))}
          </div>
          <select
            className="form-select form-select-sm"
            value={persona}
            onChange={(e) => setPersona(e.target.value)}
            aria-label="Persona"
          >
            <option value="">Todas las personas</option>
            {estado.nombres.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          <select
            className="form-select form-select-sm"
            value={mes}
            onChange={(e) => setMes(e.target.value)}
            aria-label="Mes"
          >
            <option value="">Todos los meses</option>
            {mesesDisponibles.map((m) => (
              <option key={m} value={m}>
                {nombreMes(m)}
              </option>
            ))}
          </select>
        </div>

        {comprasVisibles.length === 0 ? (
          <p className="compras-vacio">
            {estado.compras.length === 0
              ? "Todavía no hay compras registradas."
              : "No hay compras con estos filtros."}
          </p>
        ) : (
          <div className="compras-tabla-wrap">
            <table className="compras-tabla">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Nombre</th>
                  <th>Producto</th>
                  <th className="num">Cant</th>
                  <th className="num">Precio</th>
                  <th className="num">Importe</th>
                  <th className="num">Pagado</th>
                  <th className="num">Total</th>
                  <th>Estatus</th>
                  <th aria-label="Acciones" />
                </tr>
              </thead>
              <tbody>
                {comprasVisibles.map((c) => (
                  <tr key={c.compra_id}>
                    <td>{fechaCorta(c.fecha)}</td>
                    <td>{c.nombre}</td>
                    <td className="compras-tabla__producto">{c.producto}</td>
                    <td className="num">{c.cantidad}</td>
                    <td className="num">{money(c.precio)}</td>
                    <td className="num">{money(c.importe)}</td>
                    <td className="num">{money(c.pagado)}</td>
                    <td className="num compras-tabla__total">{money(c.total)}</td>
                    <td>
                      <span className={`compras-estatus compras-estatus--${c.estatus}`}>
                        {ETIQUETA[c.estatus]}
                      </span>
                    </td>
                    <td>
                      <div className="compras-acciones">
                        <button
                          type="button"
                          className="btn btn-sm btn-outline-primary"
                          onClick={() => abrirAbono(c)}
                          disabled={c.total <= 0}
                          title="Abonar"
                        >
                          <HandCoins size={14} /> Abonar
                        </button>
                        <button
                          type="button"
                          className="compras-icono"
                          onClick={() => abrirEdicion(c)}
                          title="Editar compra"
                          aria-label={`Editar compra de ${c.nombre}`}
                        >
                          <Pencil size={15} />
                        </button>
                        <button
                          type="button"
                          className="compras-icono compras-icono--peligro"
                          onClick={() => {
                            setErrorModal(null);
                            setConfirmar({ tipo: "compra", compra: c });
                          }}
                          title="Eliminar compra"
                          aria-label={`Eliminar compra de ${c.nombre}`}
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="compras-panel">
        <h2>Abonos</h2>
        {abonosVisibles.length === 0 ? (
          <p className="compras-vacio">No hay abonos registrados.</p>
        ) : (
          <div className="compras-tabla-wrap">
            <table className="compras-tabla">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Nombre</th>
                  <th>Compra</th>
                  <th className="num">Abono</th>
                  <th>Registró</th>
                  <th aria-label="Acciones" />
                </tr>
              </thead>
              <tbody>
                {abonosVisibles.map((a) => (
                  <tr key={a.abono_id}>
                    <td>{fechaCorta(a.fecha)}</td>
                    <td>{a.nombre}</td>
                    <td className="compras-tabla__producto">
                      {a.producto}{" "}
                      <span className="compras-muted">({fechaCorta(a.fecha_compra)})</span>
                    </td>
                    <td className="num">{money(a.monto)}</td>
                    <td>{a.registrado_por ?? "—"}</td>
                    <td>
                      <div className="compras-acciones">
                        <button
                          type="button"
                          className="compras-icono compras-icono--peligro"
                          onClick={() => {
                            setErrorModal(null);
                            setConfirmar({ tipo: "abono", abono: a });
                          }}
                          title="Eliminar abono"
                          aria-label={`Eliminar abono de ${a.nombre}`}
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ---------- modal abonar ---------- */}
      <Modal show={abonando !== null} onHide={() => setAbonando(null)} centered>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!abonando) return;
            ejecutar(
              () => abonarCompra(abonando.compra_id, num(montoAbono), fechaAbono),
              () => setAbonando(null),
            );
          }}
        >
          <Modal.Header closeButton>
            <Modal.Title>Abonar</Modal.Title>
          </Modal.Header>
          <Modal.Body className="compras-modal">
            {abonando && (
              <p className="compras-modal__contexto">
                <strong>{abonando.nombre}</strong> · {abonando.producto}
                <br />
                Resta <strong>{money(abonando.total)}</strong> de {money(abonando.importe)}
              </p>
            )}
            <div className="compras-modal__campos">
              <label className="compras-campo">
                <span>Monto</span>
                <input
                  className={"form-control" + (errorModal?.campo === "monto" ? " is-invalid" : "")}
                  type="number"
                  min={0.01}
                  max={abonando?.total}
                  step="0.01"
                  inputMode="decimal"
                  value={montoAbono}
                  onChange={(e) => setMontoAbono(e.target.value)}
                  autoFocus
                  required
                />
              </label>
              <label className="compras-campo">
                <span>Fecha</span>
                <input
                  className="form-control"
                  type="date"
                  max={hoy}
                  value={fechaAbono}
                  onChange={(e) => setFechaAbono(e.target.value)}
                  required
                />
              </label>
            </div>
            {errorModal && <p className="compras-error">{errorModal.msg}</p>}
          </Modal.Body>
          <Modal.Footer>
            <button type="button" className="btn btn-outline-secondary" onClick={() => setAbonando(null)}>
              Cancelar
            </button>
            <button type="submit" className="btn btn-primary" disabled={ocupado}>
              {ocupado ? "Guardando…" : "Registrar abono"}
            </button>
          </Modal.Footer>
        </form>
      </Modal>

      {/* ---------- modal editar ---------- */}
      <Modal show={editando !== null} onHide={() => setEditando(null)} centered>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!editando) return;
            ejecutar(
              () => editarCompra(editando.compra_id, aDatos(formEdicion, false)),
              () => setEditando(null),
            );
          }}
        >
          <Modal.Header closeButton>
            <Modal.Title>Editar compra</Modal.Title>
          </Modal.Header>
          <Modal.Body className="compras-modal">
            <div className="compras-modal__campos compras-modal__campos--edicion">
              <CamposCompra
                f={formEdicion}
                set={setFormEdicion}
                hoy={hoy}
                campoError={errorModal?.campo}
                conPago={false}
              />
            </div>
            {editando && (
              <p className="compras-modal__contexto">
                Importe <strong>{money(edicionImporte)}</strong> · Pagado{" "}
                <strong>{money(editando.pagado)}</strong> · Total{" "}
                <strong>{money(edicionImporte - editando.pagado)}</strong>
              </p>
            )}
            {errorModal && <p className="compras-error">{errorModal.msg}</p>}
          </Modal.Body>
          <Modal.Footer>
            <button type="button" className="btn btn-outline-secondary" onClick={() => setEditando(null)}>
              Cancelar
            </button>
            <button type="submit" className="btn btn-primary" disabled={ocupado}>
              {ocupado ? "Guardando…" : "Guardar cambios"}
            </button>
          </Modal.Footer>
        </form>
      </Modal>

      {/* ---------- modal confirmar eliminación ---------- */}
      <Modal show={confirmar !== null} onHide={() => setConfirmar(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title>
            {confirmar?.tipo === "abono" ? "Eliminar abono" : "Eliminar compra"}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body className="compras-modal">
          {confirmar?.tipo === "compra" && (
            <p>
              ¿Eliminar la compra de <strong>{confirmar.compra.nombre}</strong> (
              {confirmar.compra.producto}, {money(confirmar.compra.importe)})? También dejarán de
              contar sus abonos.
            </p>
          )}
          {confirmar?.tipo === "abono" && (
            <p>
              ¿Eliminar el abono de <strong>{money(confirmar.abono.monto)}</strong> de{" "}
              <strong>{confirmar.abono.nombre}</strong> del {fechaCorta(confirmar.abono.fecha)}?
              Lo que resta de la compra volverá a subir.
            </p>
          )}
          {errorModal && <p className="compras-error">{errorModal.msg}</p>}
        </Modal.Body>
        <Modal.Footer>
          <button type="button" className="btn btn-outline-secondary" onClick={() => setConfirmar(null)}>
            Cancelar
          </button>
          <button
            type="button"
            className="btn btn-danger"
            disabled={ocupado}
            onClick={() => {
              if (!confirmar) return;
              ejecutar(
                () =>
                  confirmar.tipo === "compra"
                    ? eliminarCompra(confirmar.compra.compra_id)
                    : eliminarAbono(confirmar.abono.abono_id),
                () => setConfirmar(null),
              );
            }}
          >
            {ocupado ? "Eliminando…" : "Eliminar"}
          </button>
        </Modal.Footer>
      </Modal>
    </div>
  );
}

export default Compras;
