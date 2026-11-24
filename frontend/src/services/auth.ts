const API_URL = "/api/autentificacion/login";

interface LoginResponse {
  token: string;
  refresh_token: string;
  user_id: number;
  nombre: string | null;
  rol: "dueno" | "empleado";
}

export async function login(
  nombre: string,
  password: string,
): Promise<LoginResponse> {
  const response = await fetch(API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      nombre,
      password,
    }),
  });

  if (!response.ok) {
    throw new Error("Credenciales incorrectas");
  }

  return response.json();
}
