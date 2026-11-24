const API = "/api";

export interface Desglose {
  clave: string;
  monto: number;
}

export interface DetalleCaptura {
  monto_detallado: number;
  monto_total: number;
  porcentaje: number;
}

export interface ComparacionSemana {
  fecha: string;
  total: number;
  num_ventas: number;
  delta_total: number;
  delta_pct: number | null;
}

export interface VentaResumen {
  id: string;
  hora: string;
  total: number;
  metodo_pago: string;
  vendedor?: string | null;
  detallada: boolean;
  estado: "pendiente" | "enviada" | "cancelada" | "editada";
  cancelable: boolean;
  editable: boolean;
}

export interface EstadoDia {
  cerrado: boolean;
  cerrado_en: string | null;
}

export interface DesgloseDia {
  fecha: string;
  total: number;
  num_ventas: number;
  desglose_categoria: Desglose[];
  desglose_metodo_pago: Desglose[];
  detalle: DetalleCaptura;
  comparacion_semana_anterior: ComparacionSemana;
  ultimas_ventas: VentaResumen[];
  estado_dia: EstadoDia;
  dias_sin_cerrar: string[];
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

export async function obtenerDesgloseDia(fecha?: string): Promise<DesgloseDia> {
  const query = fecha ? `?fecha=${fecha}` : "";
  const response = await fetch(`${API}/dashboard/dia${query}`, {
    method: "GET",
    headers: encabezados(),
  });

  if (!response.ok) {
    const cuerpo = await response.json().catch(() => null);
    throw new Error(cuerpo?.error || "No se pudo cargar el desglose del día");
  }

  return response.json();
}
