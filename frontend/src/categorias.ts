/**
 * Lista canónica de categorías de venta — espejo de
 * backend/utilidades/categorias.py (misma lista, mismo orden).
 *
 * `clave` es lo que se guarda en la venta y nunca se renombra (la
 * historia en BigQuery ya la usa). `etiqueta` es solo presentación y se
 * puede cambiar libremente: por eso "Dulces y Bebidas" sigue guardándose
 * bajo la clave `dulces`.
 *
 * `tecla` es el atajo del punto de venta (posición en la lista).
 */
export interface Categoria {
  clave: string;
  etiqueta: string;
  tecla: string;
}

export const CATEGORIAS: readonly Categoria[] = [
  { clave: "papeleria", etiqueta: "Papelería", tecla: "1" },
  { clave: "copias", etiqueta: "Copias y hojas", tecla: "2" },
  { clave: "dulces", etiqueta: "Dulces y Bebidas", tecla: "3" },
  { clave: "helados", etiqueta: "Helados", tecla: "4" },
  { clave: "recargas", etiqueta: "Recargas", tecla: "5" },
  { clave: "sublimacion", etiqueta: "Sublimación", tecla: "6" },
  { clave: "limpieza", etiqueta: "Limpieza", tecla: "7" },
  { clave: "terramar", etiqueta: "Terramar", tecla: "8" },
  { clave: "otros", etiqueta: "Otros", tecla: "9" },
] as const;

const ETIQUETAS = new Map(CATEGORIAS.map((c) => [c.clave, c.etiqueta]));

/** Etiqueta legible de una clave; si es desconocida (legado), la devuelve tal cual. */
export function etiquetaCategoria(clave: string): string {
  return ETIQUETAS.get(clave) ?? clave;
}
