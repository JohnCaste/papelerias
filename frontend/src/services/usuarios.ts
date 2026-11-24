const API = "/api";

export type Rol = "dueno" | "empleado";

export interface Usuario {
  id: string;
  nombre: string;
  foto_url: string | null;
  rol: Rol;
}

function encabezados(): HeadersInit {
  const token = localStorage.getItem("token");
  if (!token) throw new Error("No hay token");
  return { Authorization: `Bearer ${token}` };
}

export async function obtenerUsuarios(): Promise<Usuario[]> {
  const response = await fetch(`${API}/usuarios`, {
    method: "GET",
    headers: { ...encabezados(), "Content-Type": "application/json" },
  });
  if (!response.ok) {
    throw new Error("No se pudieron cargar los usuarios");
  }
  return response.json();
}

// Cambia el rol de un usuario. El backend solo lo permite si quien llama
// es 'dueno' (403 en caso contrario). El nuevo rol aplica en el próximo
// inicio de sesión de ese usuario (viaja en el token).
export async function cambiarRol(
  usuarioId: string,
  rol: Rol,
): Promise<{ id: string; rol: Rol }> {
  const response = await fetch(`${API}/usuarios/${encodeURIComponent(usuarioId)}/rol`, {
    method: "POST",
    headers: { ...encabezados(), "Content-Type": "application/json" },
    body: JSON.stringify({ rol }),
  });

  if (!response.ok) {
    let mensaje = "No se pudo cambiar el rol";
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

// Sube/actualiza la foto de perfil del usuario logueado. El backend la
// convierte a .webp, la sube a GCS y guarda la URL en lapape.usuario_foto.
// Sin 'Content-Type' manual: el navegador pone el boundary de multipart.
export async function subirFotoPerfil(file: File): Promise<{ foto_url: string }> {
  const formData = new FormData();
  formData.append("archivo", file);

  const response = await fetch(`${API}/usuarios/foto`, {
    method: "POST",
    headers: encabezados(),
    body: formData,
  });

  if (!response.ok) {
    let mensaje = "No se pudo subir la foto";
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
