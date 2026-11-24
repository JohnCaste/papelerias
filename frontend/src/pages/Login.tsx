import { useEffect, useState } from "react";
import { login } from "../services/auth";
import { obtenerUsuarios } from "../services/usuarios";
import { useNavigate } from "react-router-dom";
import "./Login.css";
import { Button } from "react-bootstrap";
import { Eye, EyeOff } from "lucide-react";
import AlertaMsj from "../components/Alerta";

function Login() {
  const [nombre, setNombre] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [shown, setShown] = useState(false);

  const navigate = useNavigate();

  const switchShown = () => setShown(!shown);
  const enviarDatos = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!nombre || !password) {
      setError("Todos los campos son obligatorios");
      return;
    }

    if (password.length < 6) {
      setError("La contraseña debe tener al menos 6 caracteres");
      return;
    }

    setLoading(true);
    try {
      const data = await login(nombre, password);

      localStorage.setItem("token", data.token);
      localStorage.setItem("refresh_token", data.refresh_token);
      localStorage.setItem("user_id", data.user_id.toString());
      if (data.nombre) localStorage.setItem("nombre", data.nombre);
      // Rol: define si ve Ventas (solo 'dueno').
      localStorage.setItem("rol", data.rol ?? "empleado");

      // La foto de perfil no viene en la respuesta de login: se resuelve
      // desde la lista de usuarios para que aparezca en el navbar tras un
      // login limpio (p. ej. en otra PC). Es opcional; si falla no bloquea.
      localStorage.removeItem("foto_url");
      try {
        const usuarios = await obtenerUsuarios();
        const yo = usuarios.find((u) => u.id === data.user_id.toString());
        if (yo?.foto_url) localStorage.setItem("foto_url", yo.foto_url);
      } catch {
        /* la foto es opcional */
      }

      setLoading(false);

      navigate("/catalogo");
    } catch {
      setError("Usuario o contraseña incorrectos");
      setLoading(false);
    }
  };

  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [error]);

  return (
    <div className="login-container">
      <div className="login-brand">
        <img src="/nuevoLogo.svg" alt="" className="login-brand__logo" />
        <span className="login-brand__name">La pape</span>
      </div>

      <form className="login-card" onSubmit={enviarDatos}>
        <h2>Iniciar sesión</h2>

        {error && (
          <AlertaMsj
            message={error}
            variant="danger"
            onClose={() => setError(null)}
          />
        )}

        <div className="login-field">
          <label htmlFor="login-usuario">Usuario</label>
          <input
            id="login-usuario"
            type="text"
            value={nombre}
            autoComplete="username"
            onChange={(e) => setNombre(e.target.value)}
            disabled={loading}
          />
        </div>

        <div className="login-field">
          <label htmlFor="login-password">Contraseña</label>
          <div className="login-password">
            <input
              id="login-password"
              type={shown ? "text" : "password"}
              value={password}
              autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
            />
            <button
              type="button"
              className="login-password__toggle"
              onClick={switchShown}
              disabled={loading}
              aria-label={shown ? "Ocultar contraseña" : "Mostrar contraseña"}
              aria-pressed={shown}
            >
              {shown ? (
                <EyeOff size={16} strokeWidth={2} aria-hidden="true" />
              ) : (
                <Eye size={16} strokeWidth={2} aria-hidden="true" />
              )}
            </button>
          </div>
        </div>

        <Button
          variant="primary"
          type="submit"
          className="login-submit"
          disabled={loading}
        >
          {loading ? (
            <>
              <span className="login-submit__spinner" aria-hidden="true" />
              Ingresando
            </>
          ) : (
            "Ingresar"
          )}
        </Button>
      </form>
    </div>
  );
}

export default Login;
