import { useMemo, useRef, useState, type ChangeEvent } from "react";
import { Modal, Spinner } from "react-bootstrap";
import { Download, FileSpreadsheet, Upload, AlertCircle, CheckCircle2 } from "lucide-react";
import {
  confirmarImportacion,
  descargarPlantilla,
  previsualizarImportacion,
  type FilaValida,
  type ResultadoImportacion,
  type VistaPreviaImportacion,
} from "../services/catalogo";
import "./ModalImportarCatalogo.css";

/* ==========================================================================
   Importar productos desde Excel/CSV (solo rol dueno) -- ver
   openspec/changes/importacion-catalogo-excel.
   1. Descargar plantilla / elegir archivo.
   2. Vista previa: el backend valida sin guardar; errores primero, 50 por
      página.
   3. "Importar N productos": solo las válidas (el backend revalida).
   4. Resultado + CSV con las filas con error para corregir y resubir.
   ========================================================================== */

const POR_PAGINA = 50;

// Mismo orden que la plantilla (backend/catalogos/importacion.py::COLUMNAS).
const COLUMNAS = [
  "nombre",
  "categoria",
  "precio",
  "codigo_barras",
  "marca",
  "costo",
  "cantidad",
  "stock_minimo",
  "codigo_interno",
  "descripcion",
] as const;

interface Props {
  show: boolean;
  onHide: (huboImportacion: boolean) => void;
}

interface FilaTabla {
  fila: number;
  datos: Record<string, unknown>;
  motivos: string[];
  advertencias: string[];
}

function guardarBlob(blob: Blob, nombre: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function celdaCsv(valor: unknown): string {
  const texto = valor == null ? "" : String(valor);
  return /[",\n\r]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto;
}

function ModalImportarCatalogo({ show, onHide }: Props) {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [vista, setVista] = useState<VistaPreviaImportacion | null>(null);
  const [resultado, setResultado] = useState<ResultadoImportacion | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState("");
  const [pagina, setPagina] = useState(0);
  const entrada = useRef<HTMLInputElement>(null);

  const reiniciar = () => {
    setArchivo(null);
    setVista(null);
    setResultado(null);
    setError("");
    setPagina(0);
    if (entrada.current) entrada.current.value = "";
  };

  const cerrar = () => {
    if (cargando) return;
    const hubo = (resultado?.creados ?? 0) > 0;
    reiniciar();
    onHide(hubo);
  };

  // Errores primero, luego válidas (con o sin advertencia), por número de fila.
  const filasTabla: FilaTabla[] = useMemo(() => {
    if (!vista) return [];
    const errores = vista.errores.map((e) => ({
      fila: e.fila,
      datos: e.datos,
      motivos: e.motivos,
      advertencias: [],
    }));
    const validas = vista.validas.map((v) => ({
      fila: v.fila,
      datos: v.producto as unknown as Record<string, unknown>,
      motivos: [],
      advertencias: v.advertencias,
    }));
    return [...errores, ...validas];
  }, [vista]);

  const paginas = Math.max(1, Math.ceil(filasTabla.length / POR_PAGINA));
  const visibles = filasTabla.slice(pagina * POR_PAGINA, (pagina + 1) * POR_PAGINA);

  const bajarPlantilla = async () => {
    setError("");
    try {
      guardarBlob(await descargarPlantilla(), "plantilla_productos.xlsx");
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const elegirArchivo = async (ev: ChangeEvent<HTMLInputElement>) => {
    const elegido = ev.target.files?.[0];
    if (!elegido) return;
    setArchivo(elegido);
    setVista(null);
    setResultado(null);
    setError("");
    setPagina(0);
    setCargando(true);
    try {
      setVista(await previsualizarImportacion(elegido));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCargando(false);
    }
  };

  const importar = async () => {
    if (!vista || vista.validas.length === 0) return;
    setCargando(true);
    setError("");
    try {
      setResultado(await confirmarImportacion(vista.validas));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCargando(false);
    }
  };

  // Filas con error de la vista previa + las omitidas al confirmar.
  const filasParaCsv = (): FilaTabla[] => {
    if (!vista) return [];
    const salida: FilaTabla[] = filasTabla.filter((f) => f.motivos.length > 0);
    const porFila = new Map<number, FilaValida>(vista.validas.map((v) => [v.fila, v]));
    for (const o of resultado?.omitidos ?? []) {
      const valida = porFila.get(o.fila);
      if (valida) {
        salida.push({
          fila: o.fila,
          datos: valida.producto as unknown as Record<string, unknown>,
          motivos: o.motivos,
          advertencias: [],
        });
      }
    }
    return salida.sort((a, b) => a.fila - b.fila);
  };

  const bajarErrores = () => {
    const filas = filasParaCsv();
    const lineas = [
      ["fila", ...COLUMNAS, "error"].join(","),
      ...filas.map((f) =>
        [f.fila, ...COLUMNAS.map((c) => f.datos[c]), f.motivos.join("; ")]
          .map(celdaCsv)
          .join(","),
      ),
    ];
    // BOM: que Excel abra el CSV como UTF-8 (acentos).
    const blob = new Blob(["﻿" + lineas.join("\r\n")], {
      type: "text/csv;charset=utf-8",
    });
    guardarBlob(blob, "filas_con_error.csv");
  };

  const nValidas = vista?.validas.length ?? 0;
  const nErrores = vista?.errores.length ?? 0;
  const hayErroresCsv = nErrores > 0 || (resultado?.omitidos.length ?? 0) > 0;

  return (
    <Modal show={show} onHide={cerrar} size="xl" centered className="importar-modal">
      <Modal.Header closeButton={!cargando}>
        <Modal.Title>Importar productos desde Excel</Modal.Title>
      </Modal.Header>

      <Modal.Body>
        {!resultado && (
          <div className="importar-paso">
            <p className="importar-texto">
              Llena la plantilla (una fila por producto; <strong>nombre</strong>,{" "}
              <strong>categoría</strong> y <strong>precio</strong> son obligatorios) y
              súbela como <code>.xlsx</code> o <code>.csv</code>. Nada se guarda hasta que
              confirmes.
            </p>
            <div className="importar-acciones">
              <button
                type="button"
                className="catalogo-btn catalogo-btn--outline"
                onClick={bajarPlantilla}
                disabled={cargando}
              >
                <Download size={16} strokeWidth={2} />
                Descargar plantilla
              </button>
              <label className={`catalogo-btn catalogo-btn--primary${cargando ? " is-disabled" : ""}`}>
                <Upload size={16} strokeWidth={2} />
                {archivo ? "Elegir otro archivo" : "Elegir archivo"}
                <input
                  ref={entrada}
                  type="file"
                  accept=".xlsx,.csv"
                  onChange={elegirArchivo}
                  disabled={cargando}
                  hidden
                  data-testid="importar-archivo"
                />
              </label>
              {archivo && (
                <span className="importar-archivo">
                  <FileSpreadsheet size={16} strokeWidth={2} />
                  {archivo.name}
                </span>
              )}
            </div>
          </div>
        )}

        {error && (
          <div className="importar-alerta importar-alerta--error" role="alert">
            <AlertCircle size={16} strokeWidth={2} />
            {error}
          </div>
        )}

        {cargando && (
          <div className="importar-cargando">
            <Spinner animation="border" size="sm" />
            {vista ? "Importando productos…" : "Leyendo y validando el archivo…"}
          </div>
        )}

        {vista && !resultado && !cargando && (
          <>
            <div className="importar-resumen">
              <span className="importar-chip importar-chip--ok">{nValidas} válidas</span>
              <span className={`importar-chip${nErrores ? " importar-chip--error" : ""}`}>
                {nErrores} con error
              </span>
              <span className="importar-resumen__total">de {vista.total} filas leídas</span>
            </div>

            {vista.advertencias.map((a) => (
              <div key={a} className="importar-alerta importar-alerta--aviso">
                <AlertCircle size={16} strokeWidth={2} />
                {a}
              </div>
            ))}

            <div className="importar-tabla-wrap">
              <table className="importar-tabla">
                <thead>
                  <tr>
                    <th>Fila</th>
                    <th>Nombre</th>
                    <th>Categoría</th>
                    <th className="num">Precio</th>
                    <th>Código de barras</th>
                    <th className="num">Cantidad</th>
                    <th>Motivo</th>
                  </tr>
                </thead>
                <tbody>
                  {visibles.map((f) => (
                    <tr
                      key={f.fila}
                      className={
                        f.motivos.length
                          ? "is-error"
                          : f.advertencias.length
                            ? "is-aviso"
                            : undefined
                      }
                    >
                      <td>{f.fila}</td>
                      <td>{String(f.datos.nombre ?? "")}</td>
                      <td>{String(f.datos.categoria ?? "")}</td>
                      <td className="num">{String(f.datos.precio ?? "")}</td>
                      <td>{String(f.datos.codigo_barras ?? "")}</td>
                      <td className="num">{String(f.datos.cantidad ?? "")}</td>
                      <td className="importar-motivo">
                        {f.motivos.length ? f.motivos.join(" · ") : f.advertencias.join(" · ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {paginas > 1 && (
              <div className="importar-paginador">
                <button
                  type="button"
                  className="catalogo-btn catalogo-btn--outline"
                  onClick={() => setPagina((p) => p - 1)}
                  disabled={pagina === 0}
                >
                  Anterior
                </button>
                <span>
                  Página {pagina + 1} de {paginas}
                </span>
                <button
                  type="button"
                  className="catalogo-btn catalogo-btn--outline"
                  onClick={() => setPagina((p) => p + 1)}
                  disabled={pagina + 1 >= paginas}
                >
                  Siguiente
                </button>
              </div>
            )}
          </>
        )}

        {resultado && (
          <div className="importar-resultado">
            <CheckCircle2 size={32} strokeWidth={1.8} className="importar-resultado__icono" />
            <h3>
              {resultado.creados} {resultado.creados === 1 ? "producto creado" : "productos creados"}
            </h3>
            {resultado.omitidos.length > 0 && (
              <p>{resultado.omitidos.length} filas se omitieron al guardar.</p>
            )}
            {nErrores > 0 && <p>{nErrores} filas tenían error y no se importaron.</p>}
            {resultado.error && (
              <div className="importar-alerta importar-alerta--error" role="alert">
                <AlertCircle size={16} strokeWidth={2} />
                {resultado.error}
              </div>
            )}
            {resultado.creados > 0 && (
              <p className="importar-texto--muted">
                Los productos ya aparecen en el catálogo. Podrás editarlos desde el formulario
                en unos minutos (BigQuery tarda en liberarlos).
              </p>
            )}
          </div>
        )}
      </Modal.Body>

      <Modal.Footer>
        {hayErroresCsv && !cargando && (
          <button
            type="button"
            className="catalogo-btn catalogo-btn--outline"
            onClick={bajarErrores}
          >
            <Download size={16} strokeWidth={2} />
            Descargar filas con error
          </button>
        )}
        {resultado ? (
          <button type="button" className="catalogo-btn catalogo-btn--primary" onClick={cerrar}>
            Cerrar
          </button>
        ) : (
          <>
            <button
              type="button"
              className="catalogo-btn catalogo-btn--outline"
              onClick={cerrar}
              disabled={cargando}
            >
              Cancelar
            </button>
            <button
              type="button"
              className="catalogo-btn catalogo-btn--primary"
              onClick={importar}
              disabled={cargando || nValidas === 0}
            >
              Importar {nValidas} {nValidas === 1 ? "producto" : "productos"}
            </button>
          </>
        )}
      </Modal.Footer>
    </Modal>
  );
}

export default ModalImportarCatalogo;
