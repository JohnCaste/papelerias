const API = "/api";

export type TipoLinea = "categoria" | "producto" | "servicio" | "recarga";

export interface LineaVentaEntrada {
  tipo: TipoLinea;
  categoria?: string;
  producto_id?: string;
  servicio_id?: string;
  descripcion?: string;
  cantidad?: number;
  monto: number;
  monto_comision?: number;
}

export interface VentaCapturada {
  id: string;
  total: number;
  metodo_pago: string;
  fecha_hora: string;
  usuario_id: string;
  vendedor: string | null;
  detallada: boolean;
  lineas: Record<string, unknown>[];
}

export interface VentaDelDia {
  id: string;
  total: number;
  metodo_pago: string;
  fecha_hora: string;
  estado_local: "pendiente" | "enviada";
  // Nombre de quien capturó la venta ("quién vendió"). Null en ventas
  // capturadas antes de esta función o migradas del histórico.
  vendedor?: string | null;
  // Derivados al leer el día: una reversión total la marca `cancelada`,
  // una recaptura de edición de monto la marca `editada` (y `total` ya
  // trae el monto vigente). `cancelada` tiene precedencia.
  cancelada?: boolean;
  editada?: boolean;
  lineas: { categoria?: string; tipo: string; subtotal: number }[];
}

export interface VentasDelDiaResponse {
  fecha: string;
  total: number;
  num_ventas: number;
  ventas: VentaDelDia[];
}

function encabezados(): HeadersInit {
  const token = localStorage.getItem("token");
  if (!token) {
    throw new Error("No hay token");
  }
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

async function extraerError(response: Response, mensajePorDefecto: string): Promise<never> {
  const cuerpo = await response.json().catch(() => null);
  throw new Error(cuerpo?.error || mensajePorDefecto);
}

export async function capturarVenta(
  lineas: LineaVentaEntrada[],
  metodoPago = "efectivo",
): Promise<VentaCapturada> {
  const response = await fetch(`${API}/ventas`, {
    method: "POST",
    headers: encabezados(),
    body: JSON.stringify({ lineas, metodo_pago: metodoPago }),
  });

  if (!response.ok) {
    return extraerError(response, "No se pudo registrar la venta");
  }

  return response.json();
}

export interface VentaCancelada {
  id: string;
  venta_original_id: string;
  total: number;
  estado: "cancelada" | "devolucion_parcial";
  motivo_cancelacion: string;
  cancelada_por: string;
  cancelada_en: string;
}

export async function cancelarVenta(
  id: string,
  motivo: string,
  opciones: { fecha: string; lineas?: number[] },
): Promise<VentaCancelada> {
  const response = await fetch(`${API}/ventas/${encodeURIComponent(id)}/cancelar`, {
    method: "POST",
    headers: encabezados(),
    body: JSON.stringify({
      motivo,
      fecha: opciones.fecha,
      ...(opciones.lineas ? { lineas: opciones.lineas } : {}),
    }),
  });

  if (!response.ok) {
    return extraerError(response, "No se pudo cancelar la venta");
  }

  return response.json();
}

export interface VentaEditada {
  id: string;
  venta_original_id: string;
  total: number;
  estado: "editada" | "editada_reversa";
  motivo_cancelacion: string;
  cancelada_por: string;
  cancelada_en: string;
}

export async function editarVenta(
  id: string,
  montoNuevo: number,
  opciones: { fecha: string; motivo: string },
): Promise<{ reversion: VentaEditada; recaptura: VentaEditada }> {
  const response = await fetch(`${API}/ventas/${encodeURIComponent(id)}/editar`, {
    method: "POST",
    headers: encabezados(),
    body: JSON.stringify({
      monto_nuevo: montoNuevo,
      motivo: opciones.motivo,
      fecha: opciones.fecha,
    }),
  });

  if (!response.ok) {
    return extraerError(response, "No se pudo editar la venta");
  }

  return response.json();
}

export async function obtenerVentasDelDia(fecha?: string): Promise<VentasDelDiaResponse> {
  const query = fecha ? `?fecha=${fecha}` : "";
  const response = await fetch(`${API}/ventas/dia${query}`, {
    method: "GET",
    headers: encabezados(),
  });

  if (!response.ok) {
    return extraerError(response, "No se pudieron obtener las ventas del día");
  }

  return response.json();
}
