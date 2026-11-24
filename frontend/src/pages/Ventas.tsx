import { useEffect, useMemo, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import {
  obtenerResumenAnual,
  calcularResumenAnual,
  calcularExtremosDelMes,
  type MesResumen,
  type DiaResumen,
} from "../services/admin";
import ModalVentaDia from "../components/ModalVentaDia";
import "./Ventas.css";

/* ==========================================================================
   Ventas · drill-down por Cards (handoff "Ventas lapape.dc.html").
   Reemplaza meses + botones de semana + tabla por Año -> Mes -> Día.
   - Nivel 1: grid de 12 Cards de mes con barra de cobertura + stepper de año.
   - Nivel 2: calendario del mes; verde con registro / rojo sin registro / anillo hoy.
   - Nivel 3: ModalVentaDia (2c) con el detalle editable por categoría.
   Todo consume tokens --lp-* de index.css.
   ========================================================================== */

const HOY = new Date();
const HOY_ISO = [
  HOY.getFullYear(),
  String(HOY.getMonth() + 1).padStart(2, "0"),
  String(HOY.getDate()).padStart(2, "0"),
].join("-");

const WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

const money = (n: number) => "$ " + Math.round(n).toLocaleString("es-AR");
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

type Nivel = "meses" | "dias";

function Ventas() {
  const [anio, setAnio] = useState(HOY.getFullYear());
  const [nivel, setNivel] = useState<Nivel>("meses");
  const [mesSel, setMesSel] = useState<number | null>(null); // 0..11
  const [diaModal, setDiaModal] = useState<DiaResumen | null>(null);

  const [data, setData] = useState<MesResumen[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [recarga, setRecarga] = useState(0);

  useEffect(() => {
    let vivo = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError("");
    obtenerResumenAnual(anio)
      .then((res) => {
        if (vivo) setData(res);
      })
      .catch(() => {
        if (vivo) setError("No se pudo cargar la información");
      })
      .finally(() => {
        if (vivo) setLoading(false);
      });
    return () => {
      vivo = false;
    };
  }, [anio, recarga]);

  const mesActual = mesSel != null ? data[mesSel] : null;
  const anioVacio =
    !loading && !error && data.length > 0 && data.every((m) => m.total === 0);

  const resumenAnual = useMemo(() => calcularResumenAnual(data), [data]);
  const extremosMes = useMemo(
    () => calcularExtremosDelMes(mesActual),
    [mesActual],
  );

  const esFuturo = (i: number) =>
    anio > HOY.getFullYear() ||
    (anio === HOY.getFullYear() && i > HOY.getMonth());

  const cambiarAnio = (delta: number) => {
    setAnio((a) => a + delta);
    setNivel("meses");
    setMesSel(null);
  };

  const abrirMes = (i: number) => {
    if (esFuturo(i)) return;
    setMesSel(i);
    setNivel("dias");
  };

  const volverAMeses = () => {
    setNivel("meses");
    setMesSel(null);
  };

  const weekdayLabels = useMemo(
    () =>
      WEEKDAYS.map((w) => (
        <div key={w} className="ventas-cal__wd">
          {w}
        </div>
      )),
    [],
  );

  return (
    <div className="ventas">
      {/* ================= NIVEL 1 · MESES ================= */}
      {nivel === "meses" && (
        <>
          <div className="ventas-topbar">
            <nav className="ventas-crumbs">
              <span className="ventas-crumbs__actual">{anio}</span>
            </nav>
            <div className="ventas-stepper">
              <button
                type="button"
                aria-label="Año anterior"
                onClick={() => cambiarAnio(-1)}
              >
                <ChevronLeft size={16} strokeWidth={2} />
              </button>
              <span className="ventas-stepper__val">{anio}</span>
              <button
                type="button"
                aria-label="Año siguiente"
                onClick={() => cambiarAnio(1)}
              >
                <ChevronRight size={16} strokeWidth={2} />
              </button>
            </div>
          </div>

          <div className="ventas-head">
            <h1 className="ventas-title">Ventas {anio}</h1>
            <p className="ventas-sub">Elegí un mes para ver el detalle por día</p>
          </div>

          {error && (
            <div className="ventas-error" role="alert">
              <span className="ventas-error__icono">
                <AlertCircle size={24} strokeWidth={1.7} />
              </span>
              <h3>No se pudo cargar la información</h3>
              <p>Revisá la conexión e intentá de nuevo.</p>
              <button
                type="button"
                className="ventas-btn ventas-btn--outline"
                onClick={() => setRecarga((n) => n + 1)}
              >
                <RefreshCw size={16} strokeWidth={2} />
                Reintentar
              </button>
            </div>
          )}

          {loading && !error && (
            <div className="ventas-grid-meses" aria-hidden>
              {Array.from({ length: 12 }).map((_, i) => (
                <div key={i} className="ventas-skeleton">
                  <span className="ventas-skeleton__l ventas-skeleton__l--name" />
                  <span className="ventas-skeleton__l ventas-skeleton__l--total" />
                  <span className="ventas-skeleton__l ventas-skeleton__l--bar" />
                </div>
              ))}
            </div>
          )}

          {!loading && !error && data.length > 0 && (
            <div className="ventas-panel-anual">
              <div
                className="ventas-panel-anual__item ventas-panel-anual__item--total"
              >
                <span className="ventas-panel-anual__label">Total del año</span>
                <strong className="ventas-panel-anual__valor">
                  {money(resumenAnual.total)}
                </strong>
              </div>
              {resumenAnual.mesMayor && (
                <div
                  className="ventas-panel-anual__item"
                  data-tipo="mayor"
                >
                  <span className="ventas-panel-anual__label">
                    Mes que más vendió
                  </span>
                  <strong className="ventas-panel-anual__valor">
                    {cap(resumenAnual.mesMayor.mesStr)}
                  </strong>
                  <span className="ventas-panel-anual__sub">
                    {money(resumenAnual.mesMayor.total)}
                  </span>
                </div>
              )}
              {resumenAnual.mesMenor && (
                <div
                  className="ventas-panel-anual__item"
                  data-tipo="menor"
                >
                  <span className="ventas-panel-anual__label">
                    Mes que menos vendió
                  </span>
                  <strong className="ventas-panel-anual__valor">
                    {cap(resumenAnual.mesMenor.mesStr)}
                  </strong>
                  <span className="ventas-panel-anual__sub">
                    {money(resumenAnual.mesMenor.total)}
                  </span>
                </div>
              )}
            </div>
          )}

          {!loading && !error && (
            <>
              {anioVacio && (
                <p className="ventas-vacio">
                  Todavía no hay ventas registradas en {anio}.
                </p>
              )}
              <div className="ventas-grid-meses">
                {data.map((m, i) => {
                  const futuro = esFuturo(i);
                  const pct = m.diasDelMes
                    ? Math.round((m.diasConRegistro / m.diasDelMes) * 100)
                    : 0;
                  return (
                    <article
                      key={m.mes}
                      className="ventas-card-mes"
                      data-dim={futuro || m.total === 0 || undefined}
                      data-clickable={!futuro || undefined}
                      role={futuro ? undefined : "button"}
                      tabIndex={futuro ? undefined : 0}
                      onClick={() => abrirMes(i)}
                      onKeyDown={(e) => {
                        if (!futuro && (e.key === "Enter" || e.key === " ")) {
                          e.preventDefault();
                          abrirMes(i);
                        }
                      }}
                    >
                      <div className="ventas-card-mes__top">
                        <h3>{cap(m.mesStr)}</h3>
                        <ChevronRight
                          size={18}
                          strokeWidth={2}
                          className="ventas-card-mes__chev"
                        />
                      </div>
                      <div className="ventas-card-mes__total">
                        {money(m.total)}
                      </div>
                      <div className="ventas-card-mes__cov">
                        <span className="ventas-bar">
                          <span
                            className="ventas-bar__fill"
                            style={{ width: `${pct}%` }}
                          />
                        </span>
                        <span className="ventas-card-mes__cov-label">
                          {m.diasConRegistro} / {m.diasDelMes} días
                        </span>
                      </div>
                    </article>
                  );
                })}
              </div>
            </>
          )}
        </>
      )}

      {/* ================= NIVEL 2 · DÍAS ================= */}
      {nivel === "dias" && mesActual && (
        <>
          <nav className="ventas-crumbs">
            <button
              type="button"
              className="ventas-crumbs__link"
              onClick={volverAMeses}
            >
              {anio}
            </button>
            <ChevronRight size={14} strokeWidth={2} />
            <span className="ventas-crumbs__actual">
              {cap(mesActual.mesStr)}
            </span>
          </nav>

          <div className="ventas-head ventas-head--dias">
            <h2 className="ventas-title ventas-title--dias">
              {cap(mesActual.mesStr)} {anio}
            </h2>
            <span className="ventas-sub">
              Total del mes:{" "}
              <strong>{money(mesActual.total)}</strong>
            </span>
          </div>

          <div className="ventas-leyenda">
            <span>
              <span className="ventas-leyenda__dot ventas-leyenda__dot--ok" />
              Con registro
            </span>
            <span>
              <span className="ventas-leyenda__dot ventas-leyenda__dot--sin" />
              Sin registro
            </span>
            <span>
              <span className="ventas-leyenda__dot ventas-leyenda__dot--hoy" />
              Hoy
            </span>
          </div>

          {(extremosMes.diaMayor || extremosMes.diaMenor) && (
            <div className="ventas-extremos-mes">
              {extremosMes.diaMayor && (
                <span
                  className="ventas-extremos-mes__item"
                  data-tipo="mayor"
                >
                  Día de mayor venta:{" "}
                  <strong>{extremosMes.diaMayor.dia}</strong>{" "}
                  <span className="ventas-extremos-mes__monto">
                    {money(extremosMes.diaMayor.total)}
                  </span>
                </span>
              )}
              {extremosMes.diaMenor && (
                <span
                  className="ventas-extremos-mes__item"
                  data-tipo="menor"
                >
                  Día de menor venta:{" "}
                  <strong>{extremosMes.diaMenor.dia}</strong>{" "}
                  <span className="ventas-extremos-mes__monto">
                    {money(extremosMes.diaMenor.total)}
                  </span>
                </span>
              )}
            </div>
          )}

          <div className="ventas-cal">
            {weekdayLabels}
            {mesActual.dias.map((d, idx) => {
              const esHoy = d.fecha === HOY_ISO;
              return (
                <article
                  key={d.fecha}
                  className="ventas-cal__dia"
                  data-estado={d.tieneRegistro ? "ok" : "sin"}
                  data-hoy={esHoy || undefined}
                  role="button"
                  tabIndex={0}
                  style={idx === 0 ? { gridColumnStart: d.columna } : undefined}
                  onClick={() => setDiaModal(d)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setDiaModal(d);
                    }
                  }}
                >
                  <div className="ventas-cal__dia-top">
                    <span className="ventas-cal__wdlabel">
                      {WEEKDAYS[d.columna - 1]}
                    </span>
                    <span className="ventas-cal__num">{d.dia}</span>
                  </div>
                  <span className="ventas-cal__status">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
                      <circle cx="12" cy="12" r="9" />
                    </svg>
                    {d.tieneRegistro ? "Con registro" : "Sin registro"}
                  </span>
                  <span className="ventas-cal__total">
                    {d.tieneRegistro ? money(d.total) : "—"}
                  </span>
                </article>
              );
            })}
          </div>
        </>
      )}

      <ModalVentaDia
        show={diaModal !== null}
        dia={diaModal}
        onHide={() => setDiaModal(null)}
        onGuardado={() => setRecarga((n) => n + 1)}
      />
    </div>
  );
}

export default Ventas;
