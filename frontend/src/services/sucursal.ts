const API = "/api";

export interface Sucursal {
  nombre: string;
  dataset: string;
}

// Una sola consulta por carga de página: la sucursal no cambia mientras
// el backend corre (cambiarla exige reiniciarlo, ver utilidades/sucursal.py).
let pendiente: Promise<Sucursal> | null = null;

export function obtenerSucursal(): Promise<Sucursal> {
  if (!pendiente) {
    pendiente = fetch(`${API}/sucursal`).then((response) => {
      if (!response.ok) {
        pendiente = null;
        throw new Error("No se pudo consultar la sucursal");
      }
      return response.json();
    });
  }
  return pendiente;
}
