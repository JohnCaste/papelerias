import { useEffect, useMemo, useState } from "react";
import { Modal } from "react-bootstrap";
import { Info, Save, Eraser } from "lucide-react";
import {
  guardarResumenDia,
  obtenerGastoDia,
  type DiaResumen,
} from "../services/admin";
import { CATEGORIAS } from "../categorias";
import "./ModalVentaDia.css";

/* ==========================================================================
   ModalVentaDia · Nivel 3 del drill-down de Ventas (handoff "Ventas lapape.dc.html", 2c).
   Detalle diario editable por categoría. Estados: con registro · sin registro
   (alert info) · dirty (punto verde + Guardar habilitado) · guardando (spinner,
   tabla atenuada). Consume tokens --lp-* de index.css.

   `Guardar` envía los montos a POST /api/ventas/resumen-dia. El modal es la
   autoridad del día: los montos son el total del día por categoría, y el
   backend reconcilia contra lo ya registrado (ver
   acceso_datos/repositorios/resumen_diario.py).

   Las categorías salen de src/categorias.ts (misma lista y mismo orden
   que el punto de venta y que el backend): el modal captura TODAS, no
   solo las cinco históricas.

   Columna "Gastos": un egreso del día (no una venta), al costado derecho
   de los totales. Su única función es descontarse del total general para
   mostrar el "Total con descuento" -- no toca ninguna categoría, solo el
   cálculo del total. Se guarda aparte (gasto_dia, ver services/admin.ts)
   y se precarga con GET /api/ventas/gasto-dia al abrir un día ya cerrado.
   ========================================================================== */

type Valores = Record<string, number>;

interface Props {
  show: boolean;
  dia: DiaResumen | null;
  onHide: () => void;
  onGuardado?: () => void;
}

const money = (n: number) => "$ " + Math.round(n).toLocaleString("es-AR");

function hoyISO(): string {
  const d = new Date();
  return [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, "0"),
    String(d.getDate()).padStart(2, "0"),
  ].join("-");
}

function fechaLarga(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const fecha = new Date(y, m - 1, d);
  const txt = fecha.toLocaleDateString("es-AR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  return txt.charAt(0).toUpperCase() + txt.slice(1);
}

function valoresDesde(dia: DiaResumen | null): Valores {
  const base: Valores = {};
  const porClave = new Map(
    (dia?.categorias ?? []).map((c) => [c.clave.toLowerCase(), c.monto]),
  );
  for (const c of CATEGORIAS) base[c.clave] = porClave.get(c.clave) ?? 0;
  return base;
}

export default function ModalVentaDia({ show, dia, onHide, onGuardado }: Props) {
  const inicial = useMemo(() => valoresDesde(dia), [dia]);
  const [valores, setValores] = useState<Valores>(inicial);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");

  // El día en curso (y cualquier fecha futura) no se edita aquí: se
  // registra en vivo desde Vender. Este resumen es para días ya cerrados.
  const bloqueado = dia ? dia.fecha >= hoyISO() : false;

  const [gasto, setGasto] = useState(0);
  const [gastoInicial, setGastoInicial] = useState(0);

  useEffect(() => {
    setValores(inicial);
    setGuardando(false);
    setError("");
    setGasto(0);
    setGastoInicial(0);

    // El gasto no viaja en `dia.categorias` (no es una categoría de
    // venta, ver services/admin.ts): se precarga aparte. Un día
    // bloqueado (en curso) nunca tuvo gasto capturado -- el backend
    // rechazaría la fecha, así que ni se pide.
    if (!dia || dia.fecha >= hoyISO()) return;
    let cancelado = false;
    obtenerGastoDia(dia.fecha)
      .then((monto) => {
        if (cancelado) return;
        setGasto(monto);
        setGastoInicial(monto);
      })
      .catch(() => {
        /* si falla la precarga, el campo simplemente arranca en 0 */
      });
    return () => {
      cancelado = true;
    };
  }, [inicial, dia]);

  const filaDirty = (key: string) => valores[key] !== inicial[key];
  const dirty = CATEGORIAS.some((c) => filaDirty(c.clave)) || gasto !== gastoInicial;
  const totalDia = CATEGORIAS.reduce((s, c) => s + (valores[c.clave] || 0), 0);
  const totalConDescuento = totalDia - (gasto || 0);

  const setCampo = (key: string, raw: string) => {
    const n = Number(raw.replace(/[^\d.-]/g, ""));
    setValores((v) => ({ ...v, [key]: Number.isFinite(n) ? n : 0 }));
  };

  const setCampoGasto = (raw: string) => {
    const n = Number(raw.replace(/[^\d.-]/g, ""));
    setGasto(Number.isFinite(n) ? n : 0);
  };

  const limpiar = () => {
    const cero: Valores = {};
    for (const c of CATEGORIAS) cero[c.clave] = 0;
    setValores(cero);
    setGasto(0);
  };

  const persistir = async () => {
    if (!dia) return;
    await guardarResumenDia(
      dia.fecha,
      CATEGORIAS.map((c) => ({ clave: c.clave, monto: valores[c.clave] || 0 })),
      gasto || 0,
    );
  };

  const guardar = async () => {
    setGuardando(true);
    setError("");
    try {
      await persistir();
      onGuardado?.();
      onHide();
    } catch (e) {
      setError(
        e instanceof Error && e.message
          ? e.message
          : "No se pudo guardar. Revisá la conexión e intentá de nuevo.",
      );
    } finally {
      setGuardando(false);
    }
  };

  if (!dia) return null;

  return (
    <Modal show={show} onHide={guardando ? undefined : onHide} centered contentClassName="mvd">
      <div className="mvd__head">
        <div>
          <strong className="mvd__title">{fechaLarga(dia.fecha)}</strong>
          <span
            className={`mvd__estado ${
              dia.tieneRegistro ? "mvd__estado--ok" : "mvd__estado--sin"
            }`}
          >
            <span className="mvd__dot" />
            {dia.tieneRegistro
              ? `Con registro · ${dia.numVentas} ventas`
              : "Sin registro"}
          </span>
        </div>
        <button
          type="button"
          className="mvd__x"
          aria-label="Cerrar"
          onClick={onHide}
          disabled={guardando}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M6 6l12 12M18 6 6 18" />
          </svg>
        </button>
      </div>

      {bloqueado ? (
        <div className="mvd__aviso">
          <Info size={16} strokeWidth={2.5} />
          <span>
            El día en curso se registra desde Vender. Este resumen es para
            días ya cerrados.
          </span>
        </div>
      ) : (
        !dia.tieneRegistro && (
          <div className="mvd__aviso">
            <Info size={16} strokeWidth={2.5} />
            <span>Este día no tiene registro. Capturá los montos y guardá.</span>
          </div>
        )
      )}

      {error && (
        <div className="mvd__aviso mvd__aviso--error">
          <Info size={16} strokeWidth={2.5} />
          <span>{error}</span>
        </div>
      )}

      <div className="mvd__body">
        <div
          className="mvd__tabla"
          data-guardando={guardando || undefined}
        >
          <div className="mvd__row mvd__row--head">
            <span>Categoría</span>
            <span>Monto</span>
          </div>
          {CATEGORIAS.map((c) => (
            <div className="mvd__row" key={c.clave}>
              <span className="mvd__cat">
                {c.etiqueta}
                {filaDirty(c.clave) && <span className="mvd__dirty" />}
              </span>
              <span className="mvd__input">
                <span className="mvd__prefix">$</span>
                <input
                  type="text"
                  inputMode="numeric"
                  value={(valores[c.clave] ?? 0).toLocaleString("es-AR")}
                  disabled={guardando || bloqueado}
                  onChange={(e) => setCampo(c.clave, e.target.value)}
                />
              </span>
            </div>
          ))}
        </div>

        <div className="mvd__totales" data-guardando={guardando || undefined}>
          <div className="mvd__totales-item">
            <span className="mvd__totales-label">Total general</span>
            <span className="mvd__totales-valor">{money(totalDia)}</span>
          </div>
          <div className="mvd__totales-item mvd__totales-item--gasto">
            <span className="mvd__totales-label">
              Gastos
              {gasto !== gastoInicial && <span className="mvd__dirty" />}
            </span>
            <span className="mvd__input">
              <span className="mvd__prefix">$</span>
              <input
                type="text"
                inputMode="numeric"
                value={gasto.toLocaleString("es-AR")}
                disabled={guardando || bloqueado}
                onChange={(e) => setCampoGasto(e.target.value)}
              />
            </span>
          </div>
          <div className="mvd__totales-item mvd__totales-item--final">
            <span className="mvd__totales-label">Total con descuento</span>
            <span className="mvd__totales-valor mvd__totales-valor--final">
              {money(totalConDescuento)}
            </span>
          </div>
        </div>
      </div>

      <div className="mvd__foot">
        <button
          type="button"
          className="mvd__btn mvd__btn--limpiar"
          onClick={limpiar}
          disabled={guardando || (totalDia === 0 && gasto === 0) || bloqueado}
        >
          <Eraser size={15} strokeWidth={2} />
          Limpiar registros
        </button>
        <span className="mvd__foot-right">
          <button
            type="button"
            className="mvd__btn mvd__btn--cancelar"
            onClick={onHide}
            disabled={guardando}
          >
            Cancelar
          </button>
          <button
            type="button"
            className="mvd__btn mvd__btn--guardar"
            onClick={guardar}
            disabled={!dirty || guardando || bloqueado}
            data-guardando={guardando || undefined}
          >
            {guardando ? (
              <>
                <span className="mvd__spin" />
                Guardando
              </>
            ) : (
              <>
                <Save size={15} strokeWidth={2} />
                Guardar
              </>
            )}
          </button>
        </span>
      </div>
    </Modal>
  );
}
