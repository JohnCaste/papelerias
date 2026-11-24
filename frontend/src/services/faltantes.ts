const API = "/api";

/* Lista de faltantes (todos los usuarios, todas las sucursales).
   El backend lee y escribe un journal local: funciona sin internet.
   El envío por WhatsApp / correo se arma aquí: el backend no manda nada. */

export type EstadoFaltante = "pendiente" | "comprado";

export interface Faltante {
  faltante_id: string;
  producto_id: string | null; // null = texto libre
  nombre: string;
  cantidad: number | null;
  nota: string | null;
  estado: EstadoFaltante;
  usuario_id: string;
  registrado_por: string | null;
  creado_en: string; // ISO UTC
  comprado_por: string | null;
  comprado_en: string | null;
}

export interface EstadoFaltantes {
  pendientes: Faltante[];
  comprados: Faltante[];
  pendientes_de_subir: number;
}

export interface DatosFaltante {
  nombre: string;
  producto_id?: string | null;
  cantidad?: number | null;
  nota?: string | null;
}

export class ErrorFaltantes extends Error {
  campo?: string;
  status: number;
  faltanteId?: string;
  constructor(mensaje: string, status: number, campo?: string, faltanteId?: string) {
    super(mensaje);
    this.status = status;
    this.campo = campo;
    this.faltanteId = faltanteId;
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
    let faltanteId: string | undefined;
    try {
      const datos = await response.json();
      if (datos?.error) mensaje = datos.error;
      campo = datos?.campo;
      faltanteId = datos?.faltante_id;
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    throw new ErrorFaltantes(mensaje, response.status, campo, faltanteId);
  }
  return response.json();
}

const ruta = (id: string) => `/faltantes/${encodeURIComponent(id)}`;

export const obtenerFaltantes = () => pedir<EstadoFaltantes>("/faltantes");

export const crearFaltante = (datos: DatosFaltante) =>
  pedir<Faltante>("/faltantes", "POST", datos);

export const editarFaltante = (id: string, datos: { cantidad: number | null; nota: string | null }) =>
  pedir<Faltante>(ruta(id), "PUT", datos);

export const cambiarEstadoFaltante = (id: string, estado: EstadoFaltante) =>
  pedir<Faltante>(`${ruta(id)}/estado`, "PUT", { estado });

export const eliminarFaltante = (id: string) =>
  pedir<{ faltante_id: string }>(ruta(id), "DELETE");

/* ------------------------------------------------------------- envío */

export function fechaHoy(d = new Date()): string {
  return [
    String(d.getDate()).padStart(2, "0"),
    String(d.getMonth() + 1).padStart(2, "0"),
    d.getFullYear(),
  ].join("/");
}

/* Texto que se manda. El `*` es negritas en WhatsApp; en correo se ve tal cual. */
export function armarTexto(sucursal: string, fecha: string, pendientes: Faltante[]): string {
  const lineas = pendientes.map((f) => {
    let linea = `• ${f.nombre}`;
    if (f.cantidad) linea += ` ×${f.cantidad}`;
    if (f.nota) linea += ` — ${f.nota}`;
    return linea;
  });
  return [`*Faltantes – ${sucursal}* (${fecha})`, ...lineas].join("\n");
}

export const asuntoCorreo = (sucursal: string, fecha: string) =>
  `Faltantes – ${sucursal} – ${fecha}`;

export const enlaceWhatsApp = (texto: string) =>
  `https://wa.me/?text=${encodeURIComponent(texto)}`;

export const enlaceCorreo = (asunto: string, texto: string) =>
  `mailto:?subject=${encodeURIComponent(asunto)}&body=${encodeURIComponent(texto)}`;

/* Algunos clientes de correo cortan los mailto: largos. */
export const LIMITE_MAILTO = 2000;
