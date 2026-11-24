const API = "/api";

/* Compras de trabajadores (solo sucursal lapape + rol dueno).
   El backend lee y escribe un journal local: funciona sin internet.
   Importe, pagado, total y estatus los calcula el backend. */

export type EstatusCompra = "pendiente" | "parcial" | "pagado";

export interface Compra {
  compra_id: string;
  nombre: string;
  producto: string;
  cantidad: number;
  precio: number;
  fecha: string; // AAAA-MM-DD
  importe: number;
  pagado: number;
  total: number;
  estatus: EstatusCompra;
  registrado_por: string | null;
}

export interface Abono {
  abono_id: string;
  compra_id: string;
  monto: number;
  fecha: string;
  registrado_por: string | null;
  nombre: string;
  producto: string;
  fecha_compra: string;
}

export interface ResumenCompras {
  por_cobrar: number;
  compras_abiertas: number;
  abonado_mes: number;
}

export interface EstadoCompras {
  compras: Compra[];
  abonos: Abono[];
  resumen: ResumenCompras;
  nombres: string[];
  pendientes_subir: number;
  hoy: string;
}

export interface DatosCompra {
  nombre: string;
  producto: string;
  cantidad: number;
  precio: number;
  fecha: string;
  pago?: number;
}

export class ErrorCompras extends Error {
  campo?: string;
  constructor(mensaje: string, campo?: string) {
    super(mensaje);
    this.campo = campo;
  }
}

function encabezados(): HeadersInit {
  const token = localStorage.getItem("token");
  if (!token) throw new Error("No hay token");
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

async function pedir<T>(ruta: string, metodo = "GET", cuerpo?: unknown): Promise<T> {
  const response = await fetch(`${API}${ruta}`, {
    method: metodo,
    headers: encabezados(),
    body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
  });
  if (!response.ok) {
    let mensaje = "No se pudo completar la operación";
    let campo: string | undefined;
    try {
      const datos = await response.json();
      if (datos?.error) mensaje = datos.error;
      campo = datos?.campo;
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    throw new ErrorCompras(mensaje, campo);
  }
  return response.json();
}

export const obtenerCompras = () => pedir<EstadoCompras>("/compras");

export const crearCompra = (datos: DatosCompra) =>
  pedir<Compra>("/compras", "POST", datos);

export const editarCompra = (id: string, datos: DatosCompra) =>
  pedir<Compra>(`/compras/${encodeURIComponent(id)}`, "PUT", datos);

export const eliminarCompra = (id: string) =>
  pedir<{ compra_id: string }>(`/compras/${encodeURIComponent(id)}`, "DELETE");

export const abonarCompra = (id: string, monto: number, fecha: string) =>
  pedir<{ abono_id: string; compra: Compra }>(
    `/compras/${encodeURIComponent(id)}/abonos`,
    "POST",
    { monto, fecha },
  );

export const eliminarAbono = (abonoId: string) =>
  pedir<{ abono_id: string }>(`/compras/abonos/${encodeURIComponent(abonoId)}`, "DELETE");
