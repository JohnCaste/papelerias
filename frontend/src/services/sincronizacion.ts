const API = "/api";

export interface EstadoSincronizacion {
  ultima_sincronizacion_exitosa: string | null;
  fallos_consecutivos: number;
  ultimo_error: string | null;
}

export async function obtenerEstadoSincronizacion(): Promise<EstadoSincronizacion> {
  const token = localStorage.getItem("token");
  if (!token) {
    throw new Error("No hay token");
  }

  const response = await fetch(`${API}/sincronizacion/estado`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error("No se pudo consultar el estado de sincronización");
  }

  return response.json();
}
