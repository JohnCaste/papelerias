const API = "/api";

export type Granularidad = "dia" | "semana" | "mes" | "anio";

export interface Desglose {
  clave: string;
  monto: number;
}

export interface BucketAgregado {
  periodo_inicio: string;
  periodo_fin: string;
  etiqueta: string;
  total: number;
  num_ventas: number;
  desglose_categoria: Desglose[];
  desglose_servicio: Desglose[];
  desglose_metodo_pago: Desglose[];
}

export async function obtenerAgregaciones(
  granularidad: Granularidad,
  desde: string,
  hasta: string,
): Promise<BucketAgregado[]> {
  const token = localStorage.getItem("token");
  const params = new URLSearchParams({ granularidad, desde, hasta });

  const response = await fetch(`${API}/agregaciones?${params.toString()}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error("Error al obtener agregaciones");
  }

  return response.json();
}

// --- Datos de la pantalla de Ventas ---------------------------------------
// Reemplaza a registros/valores.py: antes el backend armaba el árbol
// mes -> semana -> día (cálculo de semanas frágil en bisiestos). Ahora se
// pide la agregación diaria y se agrupa aquí como grid Año -> Mes -> Día,
// sin nivel de semana.

// Claves de categoría que usa la captura de resumen (las mismas del POS).
// El frontend dejó de usar `productos`; la historia migrada (#10) y algún
// bucket legado pueden traer `productos`/`hojas`, que se pliegan aquí.
const PLIEGUE_CATEGORIA: Record<string, string> = {
  productos: "papeleria",
  hojas: "copias",
};

function plegarCategorias(desglose: Desglose[]): Desglose[] {
  const acc = new Map<string, number>();
  for (const d of desglose) {
    const clave = PLIEGUE_CATEGORIA[d.clave] ?? d.clave;
    acc.set(clave, (acc.get(clave) ?? 0) + d.monto);
  }
  return [...acc].map(([clave, monto]) => ({ clave, monto }));
}

const MESES = [
  "enero",
  "febrero",
  "marzo",
  "abril",
  "mayo",
  "junio",
  "julio",
  "agosto",
  "septiembre",
  "octubre",
  "noviembre",
  "diciembre",
];

function isoFecha(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dia = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dia}`;
}

// --- Resumen anual para el drill-down Año -> Mes -> Día --------------------
// (handoff "Ventas lapape.dc.html"). Misma fuente que el calendario de
// arriba — la agregación diaria — pero agrupada como grid de meses y, dentro
// de cada mes, un array denso de días 1..N para pintar el calendario.

export interface DiaResumen {
  fecha: string; // YYYY-MM-DD
  dia: number; // 1..31
  columna: number; // 1..7 (lunes = 1) — posición en la grilla semanal
  total: number;
  numVentas: number;
  tieneRegistro: boolean;
  categorias: Desglose[];
}

export interface MesResumen {
  mes: number; // 1..12
  mesStr: string;
  total: number;
  diasConRegistro: number;
  diasDelMes: number;
  dias: DiaResumen[];
}

export function agruparResumenAnual(
  buckets: BucketAgregado[],
  anio: number,
): MesResumen[] {
  const porFecha = new Map(buckets.map((b) => [b.periodo_inicio, b]));
  const meses: MesResumen[] = [];

  for (let mes = 0; mes < 12; mes++) {
    const diasDelMes = new Date(anio, mes + 1, 0).getDate();
    const dias: DiaResumen[] = [];
    let total = 0;
    let diasConRegistro = 0;

    for (let d = 1; d <= diasDelMes; d++) {
      const fecha = isoFecha(new Date(anio, mes, d));
      const bucket = porFecha.get(fecha);
      const tieneRegistro = !!bucket && bucket.num_ventas > 0;
      if (tieneRegistro) {
        diasConRegistro += 1;
        total += bucket!.total;
      }
      dias.push({
        fecha,
        dia: d,
        columna: ((new Date(anio, mes, d).getDay() + 6) % 7) + 1,
        total: bucket?.total ?? 0,
        numVentas: bucket?.num_ventas ?? 0,
        tieneRegistro,
        categorias: plegarCategorias(bucket?.desglose_categoria ?? []),
      });
    }

    meses.push({
      mes: mes + 1,
      mesStr: MESES[mes],
      total,
      diasConRegistro,
      diasDelMes,
      dias,
    });
  }
  return meses;
}

export async function obtenerResumenAnual(anio: number): Promise<MesResumen[]> {
  const buckets = await obtenerAgregaciones(
    "dia",
    `${anio}-01-01`,
    `${anio}-12-31`,
  );
  return agruparResumenAnual(buckets, anio);
}

// --- Panel anual: total del año y extremos mes / día ---------------------
// Puro y sin llamadas: deriva de lo que ya trae obtenerResumenAnual.

export interface ExtremoMes {
  mes: number; // 1..12
  mesStr: string;
  total: number;
}

export interface ResumenAnual {
  total: number;
  mesMayor: ExtremoMes | null;
  mesMenor: ExtremoMes | null;
}

export function calcularResumenAnual(meses: MesResumen[]): ResumenAnual {
  const total = meses.reduce((s, m) => s + m.total, 0);
  const conRegistro = meses.filter((m) => m.diasConRegistro > 0);
  if (conRegistro.length === 0) {
    return { total, mesMayor: null, mesMenor: null };
  }
  const ordenados = [...conRegistro].sort((a, b) => a.total - b.total);
  const aExtremo = (m: MesResumen): ExtremoMes => ({
    mes: m.mes,
    mesStr: m.mesStr,
    total: m.total,
  });
  return {
    total,
    mesMayor: aExtremo(ordenados[ordenados.length - 1]),
    // Un solo mes con registro: solo hay "mayor".
    mesMenor: conRegistro.length > 1 ? aExtremo(ordenados[0]) : null,
  };
}

export interface ExtremoDia {
  dia: number; // 1..31
  fecha: string;
  total: number;
}

export interface ExtremosDelMes {
  diaMayor: ExtremoDia | null;
  diaMenor: ExtremoDia | null;
}

export function calcularExtremosDelMes(mes: MesResumen | null): ExtremosDelMes {
  if (!mes) return { diaMayor: null, diaMenor: null };
  const conRegistro = mes.dias.filter((d) => d.tieneRegistro);
  if (conRegistro.length === 0) return { diaMayor: null, diaMenor: null };
  const ordenados = [...conRegistro].sort((a, b) => a.total - b.total);
  const aExtremo = (d: DiaResumen): ExtremoDia => ({
    dia: d.dia,
    fecha: d.fecha,
    total: d.total,
  });
  return {
    diaMayor: aExtremo(ordenados[ordenados.length - 1]),
    diaMenor: conRegistro.length > 1 ? aExtremo(ordenados[0]) : null,
  };
}

// --- Captura manual del resumen de un día ------------------------------
// POST /api/ventas/resumen-dia. El backend reconcilia: los montos son el
// total del día por categoría, no un ajuste (ver
// acceso_datos/repositorios/resumen_diario.py).
//
// `gasto` (columna "Gastos" del modal) es un egreso, no una venta: el
// backend lo guarda aparte (gasto_dia) y no afecta ninguna categoría de
// venta ni ningún reporte agregado. Solo sirve para el total con
// descuento que se muestra EN EL MODAL.

export interface ResumenDiaGuardado {
  fecha: string;
  total: number;
  categorias: Desglose[];
  gasto: number;
}

export async function guardarResumenDia(
  fecha: string,
  categorias: Desglose[],
  gasto = 0,
): Promise<ResumenDiaGuardado> {
  const token = localStorage.getItem("token");
  const response = await fetch(`${API}/ventas/resumen-dia`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ fecha, categorias, gasto }),
  });

  if (!response.ok) {
    const cuerpo = await response.json().catch(() => null);
    throw new Error(cuerpo?.error || "No se pudo guardar el resumen del día");
  }

  return response.json();
}

// GET /api/ventas/gasto-dia -- precarga el campo "Gastos" al abrir el
// modal de un día ya cerrado. 0 si el día nunca tuvo gasto capturado.
export async function obtenerGastoDia(fecha: string): Promise<number> {
  const token = localStorage.getItem("token");
  const response = await fetch(`${API}/ventas/gasto-dia?fecha=${fecha}`, {
    method: "GET",
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok) {
    const cuerpo = await response.json().catch(() => null);
    throw new Error(cuerpo?.error || "No se pudo cargar el gasto del día");
  }

  const data = await response.json();
  return data.gasto ?? 0;
}
