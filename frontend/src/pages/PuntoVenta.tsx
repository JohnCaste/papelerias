import { useEffect, useRef, useState } from "react";
import { Alert, Badge, Table } from "react-bootstrap";
import {
  capturarVenta,
  obtenerVentasDelDia,
  type VentaDelDia,
} from "../services/ventas";
import {
  cerrarDiaManual,
  obtenerEstadoDia,
  regenerarActaDia,
  type EstadoDia,
} from "../services/cierres";
import { obtenerEstadoSincronizacion } from "../services/sincronizacion";
import { useTheme } from "../useTheme";
import { CATEGORIAS } from "../categorias";
import "./PuntoVenta.css";

// Cada cuanto se refresca el indicador de sincronizacion (#55) -- no
// hace falta mas fino, el sincronizador de verdad corre cada 5-60s.
const INTERVALO_REFRESCO_SINCRONIZACION_MS = 20_000;

const METODOS_PAGO = [
  { valor: "efectivo", etiqueta: "Efectivo" },
  { valor: "transferencia", etiqueta: "Transferencia" },
  { valor: "tarjeta", etiqueta: "Tarjeta" },
] as const;

function formatearHora(fechaIso: string): string {
  try {
    return new Date(fechaIso).toLocaleTimeString("es-MX", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return fechaIso;
  }
}

function formatearFecha(fechaIso: string): string {
  try {
    const [anio, mes, dia] = fechaIso.split("-").map(Number);
    return new Date(anio, mes - 1, dia).toLocaleDateString("es-MX", {
      weekday: "long",
      day: "numeric",
      month: "long",
    });
  } catch {
    return fechaIso;
  }
}

function etiquetaLinea(venta: VentaDelDia): string {
  const primera = venta.lineas?.[0];
  if (!primera) return "—";
  if (primera.tipo === "categoria") {
    const categoria = CATEGORIAS.find((c) => c.clave === primera.categoria);
    return categoria?.etiqueta ?? String(primera.categoria);
  }
  return primera.tipo;
}

function PuntoVenta() {
  const [categoria, setCategoria] = useState<string>(CATEGORIAS[0].clave);
  const [metodoPago, setMetodoPago] = useState<string>("efectivo");
  const [monto, setMonto] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const [ventasHoy, setVentasHoy] = useState<VentaDelDia[]>([]);
  const [totalHoy, setTotalHoy] = useState(0);
  const [estadoDia, setEstadoDia] = useState<EstadoDia | null>(null);
  const [cerrandoDia, setCerrandoDia] = useState(false);
  const [regenerando, setRegenerando] = useState(false);
  const [ultimoErrorSync, setUltimoErrorSync] = useState<string | null>(null);

  const { theme } = useTheme();
  const inputMontoRef = useRef<HTMLInputElement>(null);
  const pendientesHoy = ventasHoy.filter((v) => v.estado_local === "pendiente").length;

  const cargarVentasDelDia = async () => {
    try {
      const data = await obtenerVentasDelDia();
      setVentasHoy(data.ventas);
      setTotalHoy(data.total);
    } catch {
      // Si esto falla (por ejemplo, token vencido) no se bloquea la
      // captura -- solo no se actualiza la lista visible.
    }
  };

  const cargarEstadoDia = async () => {
    try {
      setEstadoDia(await obtenerEstadoDia());
    } catch {
      // Igual que arriba: no bloquea la pantalla si falla.
    }
  };

  const cargarEstadoSincronizacion = async () => {
    try {
      const estado = await obtenerEstadoSincronizacion();
      setUltimoErrorSync(estado.ultimo_error);
    } catch {
      // No bloquea la pantalla -- el indicador simplemente no se actualiza.
    }
  };

  useEffect(() => {
    cargarVentasDelDia();
    cargarEstadoDia();
    cargarEstadoSincronizacion();
    inputMontoRef.current?.focus();

    // #55: refresca el indicador de sincronizacion periodicamente, sin
    // que nadie tenga que recargar la pagina para ver si ya se puso al
    // dia con BigQuery (o si sigue sin internet).
    const intervalo = setInterval(() => {
      cargarVentasDelDia();
      cargarEstadoSincronizacion();
    }, INTERVALO_REFRESCO_SINCRONIZACION_MS);
    return () => clearInterval(intervalo);
  }, []);

  const forzarCierre = async () => {
    const horaCierre = estadoDia?.hora_cierre ?? "21:00";
    const mensaje =
      ventasHoy.length === 0
        ? "¿Cerrar el día ahora sin ninguna venta capturada?"
        : `¿Forzar el cierre con ${ventasHoy.length} venta(s) por $${totalHoy.toFixed(2)}? Se puede seguir vendiendo después y regenerar el acta hasta las ${horaCierre}.`;
    if (!window.confirm(mensaje)) return;

    setCerrandoDia(true);
    setError("");
    try {
      await cerrarDiaManual();
      await cargarEstadoDia();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cerrar el día");
    } finally {
      setCerrandoDia(false);
    }
  };

  const regenerarActa = async () => {
    setRegenerando(true);
    setError("");
    try {
      await regenerarActaDia();
      await cargarEstadoDia();
      await cargarVentasDelDia();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo regenerar el acta");
    } finally {
      setRegenerando(false);
    }
  };

  const guardar = async () => {
    const montoNumero = Number(monto);
    if (!monto || Number.isNaN(montoNumero) || montoNumero <= 0) {
      setError("Escribe un monto mayor a cero");
      return;
    }

    setGuardando(true);
    setError("");
    try {
      const venta = await capturarVenta(
        [{ tipo: "categoria", categoria, monto: montoNumero }],
        metodoPago,
      );

      // Actualizacion optimista: no hace falta volver a pedir toda la
      // lista, ya tenemos la venta que se acaba de guardar.
      setVentasHoy((previas) => [
        {
          id: venta.id,
          total: venta.total,
          metodo_pago: venta.metodo_pago,
          fecha_hora: venta.fecha_hora,
          estado_local: "pendiente",
          vendedor: venta.vendedor,
          lineas: venta.lineas as VentaDelDia["lineas"],
        },
        ...previas,
      ]);
      setTotalHoy((previo) => previo + venta.total);
      setMonto("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar la venta");
    } finally {
      setGuardando(false);
      inputMontoRef.current?.focus();
    }
  };

  const alPresionarTecla = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      guardar();
    }
  };

  return (
    <div className="punto-venta">
      <div className="punto-venta-total">
        <span className="punto-venta-total-label">Total de hoy</span>
        <span className="punto-venta-total-monto">
          ${totalHoy.toFixed(2)}
        </span>
        <span className="punto-venta-total-count">
          {ventasHoy.length} {ventasHoy.length === 1 ? "venta" : "ventas"}
        </span>
      </div>

      <div className="punto-venta-estado-sync">
        {pendientesHoy === 0 ? (
          <Badge bg="success">☁️ Sincronizado</Badge>
        ) : ultimoErrorSync ? (
          <Badge bg="danger" title={ultimoErrorSync}>
            🔌 Sin conexión — {pendientesHoy} pendiente{pendientesHoy === 1 ? "" : "s"}
          </Badge>
        ) : (
          <Badge bg="warning" text="dark">
            ⏳ {pendientesHoy} pendiente{pendientesHoy === 1 ? "" : "s"} de subir
          </Badge>
        )}
      </div>

      <div className="punto-venta-estado-dia">
        {estadoDia?.cerrado ? (
          <Badge bg="secondary">
            Día cerrado · {estadoDia.fecha ? formatearFecha(estadoDia.fecha) : ""}
            {estadoDia.cierre?.provisional ? " · provisional" : ""}
          </Badge>
        ) : (
          <Badge bg="success">
            Día abierto · Hoy, {estadoDia?.fecha ? formatearFecha(estadoDia.fecha) : ""}
          </Badge>
        )}

        {estadoDia?.cerrado ? (
          <button
            type="button"
            className="punto-venta-cerrar-dia"
            onClick={regenerarActa}
            disabled={regenerando}
          >
            {regenerando ? "Regenerando..." : "Regenerar acta"}
          </button>
        ) : estadoDia?.antes_de_hora_cierre ? (
          <div className="punto-venta-acciones-dia">
            <button
              type="button"
              className="punto-venta-cerrar-dia"
              disabled
              title={`El día se cierra automáticamente a las ${estadoDia.hora_cierre ?? "21:00"}`}
            >
              Se cierra automáticamente a las {estadoDia.hora_cierre ?? "21:00"}
            </button>
            <button
              type="button"
              className="punto-venta-forzar-cierre"
              onClick={forzarCierre}
              disabled={cerrandoDia}
            >
              {cerrandoDia ? "Cerrando..." : "Forzar cierre ahora"}
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="punto-venta-cerrar-dia"
            onClick={forzarCierre}
            disabled={cerrandoDia}
          >
            {cerrandoDia ? "Cerrando..." : "Cerrar el día"}
          </button>
        )}
      </div>

      {error && (
        <Alert variant="danger" onClose={() => setError("")} dismissible>
          {error}
        </Alert>
      )}

      <div className="punto-venta-categorias">
        {CATEGORIAS.map((c) => (
          <button
            key={c.clave}
            type="button"
            accessKey={c.tecla}
            className={
              "punto-venta-categoria" +
              (categoria === c.clave ? " seleccionada" : "")
            }
            onClick={() => {
              setCategoria(c.clave);
              inputMontoRef.current?.focus();
            }}
          >
            {c.etiqueta}
            <span className="punto-venta-categoria-tecla">Alt+{c.tecla}</span>
          </button>
        ))}
      </div>

      <div className="punto-venta-captura">
        <input
          ref={inputMontoRef}
          type="number"
          inputMode="decimal"
          min="0"
          step="0.01"
          placeholder="0.00"
          className="punto-venta-monto"
          value={monto}
          disabled={guardando}
          onChange={(e) => setMonto(e.target.value)}
          onKeyDown={alPresionarTecla}
        />
        <button
          type="button"
          className="punto-venta-guardar"
          disabled={guardando}
          onClick={guardar}
        >
          {guardando ? "Guardando..." : "Guardar (Enter)"}
        </button>
      </div>

      <div className="punto-venta-metodos">
        {METODOS_PAGO.map((m) => (
          <button
            key={m.valor}
            type="button"
            className={
              "punto-venta-metodo" +
              (metodoPago === m.valor ? " seleccionado" : "")
            }
            onClick={() => setMetodoPago(m.valor)}
          >
            {m.etiqueta}
          </button>
        ))}
      </div>

      <h3 className="punto-venta-historial-titulo">Ventas de hoy</h3>
      <Table
        striped
        bordered
        hover
        size="sm"
        responsive
        variant={theme === "dark" ? "dark" : undefined}
      >
        <thead>
          <tr>
            <th>Hora</th>
            <th>Categoría</th>
            <th>Monto</th>
            <th>Método</th>
            <th>Vendió</th>
            <th>Estado</th>
          </tr>
        </thead>
        <tbody>
          {ventasHoy.length === 0 ? (
            <tr>
              <td colSpan={6} className="text-center text-muted">
                Sin ventas todavía
              </td>
            </tr>
          ) : (
            ventasHoy.map((v) => (
              <tr
                key={v.id}
                className={
                  v.cancelada ? "text-muted text-decoration-line-through" : undefined
                }
              >
                <td>{formatearHora(v.fecha_hora)}</td>
                <td>{etiquetaLinea(v)}</td>
                <td>${v.total.toFixed(2)}</td>
                <td>{v.metodo_pago}</td>
                <td>{v.vendedor ?? "—"}</td>
                <td>
                  {v.cancelada ? (
                    <Badge bg="danger">cancelada</Badge>
                  ) : v.editada ? (
                    <Badge bg="info">editada</Badge>
                  ) : (
                    <Badge bg={v.estado_local === "enviada" ? "success" : "secondary"}>
                      {v.estado_local === "enviada" ? "sincronizada" : "pendiente"}
                    </Badge>
                  )}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </Table>
    </div>
  );
}

export default PuntoVenta;
