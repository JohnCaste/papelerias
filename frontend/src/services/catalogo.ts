const API = "/api";

// ----------------------------OBtener productos paginados
export async function obtenerProductosPaginados(limit: number, offset: number) {
  const token = localStorage.getItem("token");

  if (!token) {
    throw new Error("No hay token");
  }

  const response = await fetch(
    `${API}/catalogo/paginador?limit=${limit}&offset=${offset}`,
    {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
    },
  );

  if (!response.ok) {
    throw new Error("Error al obtener productos");
  }

  return response.json();
}

// ----------------------------Búsqueda server-side sobre todo el catálogo
export interface FiltrosBusqueda {
  q?: string;
  categoria?: string;
  marca?: string;
  precioMin?: number;
  precioMax?: number;
  limit?: number;
  offset?: number;
}

export async function buscarProductos(filtros: FiltrosBusqueda = {}) {
  const token = localStorage.getItem("token");
  if (!token) {
    throw new Error("No hay token");
  }

  const params = new URLSearchParams();
  if (filtros.q) params.set("q", filtros.q);
  if (filtros.categoria) params.set("categoria", filtros.categoria);
  if (filtros.marca) params.set("marca", filtros.marca);
  if (filtros.precioMin != null) params.set("precio_min", String(filtros.precioMin));
  if (filtros.precioMax != null) params.set("precio_max", String(filtros.precioMax));
  params.set("limit", String(filtros.limit ?? 12));
  params.set("offset", String(filtros.offset ?? 0));

  const response = await fetch(`${API}/catalogo/buscar?${params.toString()}`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    throw new Error("Error al buscar productos");
  }

  return response.json() as Promise<{ items: unknown[]; total: number }>;
}

// ----------------------------Categorías existentes (para selectores)
export async function obtenerCategorias(): Promise<string[]> {
  const token = localStorage.getItem("token");
  if (!token) {
    throw new Error("No hay token");
  }

  const response = await fetch(`${API}/catalogo/categorias`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    throw new Error("Error al obtener categorías");
  }

  return response.json();
}

// ----------------------------Marcas existentes (para filtro por marca)
export async function obtenerMarcas(): Promise<string[]> {
  const token = localStorage.getItem("token");
  if (!token) {
    throw new Error("No hay token");
  }

  const response = await fetch(`${API}/catalogo/marcas`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    throw new Error("Error al obtener marcas");
  }

  return response.json();
}

// ----------------------------Subir imagen de producto (cámara o archivo)
// El backend la convierte a .webp optimizada y la sube a GCS; devuelve la URL.
export async function subirImagenProducto(file: File): Promise<{ url: string }> {
  const token = localStorage.getItem("token");
  if (!token) {
    throw new Error("No hay token");
  }

  const formData = new FormData();
  formData.append("archivo", file);

  // Sin 'Content-Type' manual: el navegador pone el boundary de multipart.
  const response = await fetch(`${API}/catalogo/imagen`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  });

  if (!response.ok) {
    let mensaje = "Error al subir la imagen";
    try {
      const cuerpo = await response.json();
      if (cuerpo?.error) mensaje = cuerpo.error;
    } catch {
      /* respuesta sin cuerpo JSON */
    }
    throw new Error(mensaje);
  }

  return response.json();
}

// ----------------------------Obtener Todos productos
export async function obtenerTodo() {
  const token = localStorage.getItem("token");
  if (!token) {
    throw new Error("No hay token");
  }

  const response = await fetch(`${API}/catalogo`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    throw new Error("Error al obtener productos");
  }

  return response.json();
}

// Extrae el mensaje de error del backend ({ error: "..." }) si viene.
async function _mensajeError(response: Response, porDefecto: string) {
  try {
    const cuerpo = await response.json();
    if (cuerpo?.error) return cuerpo.error as string;
  } catch {
    /* sin cuerpo JSON */
  }
  return porDefecto;
}

// ----------------------------Agregar producto (POST /api/catalogo)
// El payload incluye los campos del formulario. `codigo_barras` es opcional:
// vacío o solo espacios se guarda como null; si ya lo usa otro producto activo
// el backend responde 400 { error }.
export async function agregarProducto(producto: unknown) {
  const token = localStorage.getItem("token");

  const response = await fetch(`${API}/catalogo`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(producto),
  });

  if (!response.ok) {
    throw new Error(await _mensajeError(response, "Error al agregar producto"));
  }

  return response.json();
}

// ----------------------------Eliminar producto (DELETE /api/catalogo?id=)
export async function eliminarProducto(id: string) {
  const token = localStorage.getItem("token");

  const response = await fetch(`${API}/catalogo?id=${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error(
      await _mensajeError(response, "Error al eliminar el producto"),
    );
  }

  return response.json();
}

// ----------------------------Actualizar Producto (PATCH /api/catalogo)
// Si el payload trae `codigo_barras`, aplica la misma regla que el alta: vacío
// -> null, y 400 si el código pertenece a otro producto (conservar el propio
// código es válido).
export async function actualizarProducto(data: unknown) {
  const token = localStorage.getItem("token");

  const response = await fetch(`${API}/catalogo`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error(
      await _mensajeError(response, "Error al actualizar producto"),
    );
  }

  return response.json();
}

// ----------------------------Importación desde Excel/CSV (solo rol dueno)
// Ver backend/catalogos/importacion.py. Las rutas exigen JWT, así que la
// descarga se hace con fetch + Blob (un <a href> simple no manda el token).

export interface ProductoImportado {
  nombre: string;
  categoria: string;
  precio: number;
  codigo_barras: string | null;
  codigo_interno: string | null;
  marca: string | null;
  descripcion: string | null;
  costo: number | null;
  cantidad: number | null;
  stock_minimo: number | null;
}

export interface FilaValida {
  fila: number;
  producto: ProductoImportado;
  advertencias: string[];
}

export interface FilaConError {
  fila: number;
  datos: Record<string, unknown>;
  motivos: string[];
}

export interface VistaPreviaImportacion {
  total: number;
  validas: FilaValida[];
  errores: FilaConError[];
  advertencias: string[];
}

export interface ResultadoImportacion {
  creados: number;
  omitidos: { fila: number; motivos: string[] }[];
  error?: string;
}

function tokenImportacion(): string {
  const token = localStorage.getItem("token");
  if (!token) throw new Error("No hay token");
  return token;
}

async function errorDeRespuesta(response: Response, defecto: string): Promise<Error> {
  try {
    const data = await response.json();
    if (data?.error) return new Error(data.error);
  } catch {
    /* respuesta sin JSON */
  }
  return new Error(defecto);
}

export async function descargarPlantilla(): Promise<Blob> {
  const response = await fetch(`${API}/catalogo/importar/plantilla`, {
    headers: { Authorization: `Bearer ${tokenImportacion()}` },
  });
  if (!response.ok) throw await errorDeRespuesta(response, "No se pudo descargar la plantilla");
  return response.blob();
}

export async function previsualizarImportacion(
  archivo: File,
): Promise<VistaPreviaImportacion> {
  const datos = new FormData();
  datos.append("archivo", archivo);
  const response = await fetch(`${API}/catalogo/importar/previsualizar`, {
    method: "POST",
    headers: { Authorization: `Bearer ${tokenImportacion()}` },
    body: datos,
  });
  if (!response.ok) throw await errorDeRespuesta(response, "No se pudo leer el archivo");
  return response.json();
}

export async function confirmarImportacion(
  filas: FilaValida[],
): Promise<ResultadoImportacion> {
  const response = await fetch(`${API}/catalogo/importar/confirmar`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${tokenImportacion()}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      filas: filas.map((f) => ({ fila: f.fila, datos: f.producto })),
    }),
  });
  if (!response.ok) throw await errorDeRespuesta(response, "No se pudo importar");
  return response.json();
}
