const API = "/api";

export interface Cierre {
  id: string;
  total: number;
  num_ventas: number;
  generado_por: "automatico" | "perezoso" | "manual" | "regeneracion";
  generado_en: string;
  provisional?: boolean;
}

export interface EstadoDia {
  fecha: string;
  cerrado: boolean;
  cierre: Cierre | null;
  // Solo presentes cuando la fecha consultada es hoy.
  antes_de_hora_cierre?: boolean;
  hora_cierre?: string;
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

export async function obtenerEstadoDia(): Promise<EstadoDia> {
  const response = await fetch(`${API}/cierres/dia`, {
    method: "GET",
    headers: encabezados(),
  });

  if (!response.ok) {
    return extraerError(response, "No se pudo consultar el estado del día");
  }

  return response.json();
}

export async function cerrarDiaManual(): Promise<Cierre> {
  const response = await fetch(`${API}/cierres/dia`, {
    method: "POST",
    headers: encabezados(),
    body: JSON.stringify({}),
  });

  if (!response.ok) {
    return extraerError(response, "No se pudo cerrar el día");
  }

  return response.json();
}

export async function regenerarActaDia(): Promise<Cierre> {
  const response = await fetch(`${API}/cierres/dia/regenerar`, {
    method: "POST",
    headers: encabezados(),
    body: JSON.stringify({}),
  });

  if (!response.ok) {
    return extraerError(response, "No se pudo regenerar el acta");
  }

  return response.json();
}
