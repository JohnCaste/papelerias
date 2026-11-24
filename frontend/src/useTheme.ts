import { useCallback, useSyncExternalStore } from "react";

/* Tono claro / oscuro global. Escribe data-theme="dark" en <html> (los tokens
   semánticos de index.css cuelgan de [data-theme="dark"]) y lo persiste en
   localStorage. Un store a nivel de módulo mantiene en sync a todos los
   componentes que llamen useTheme() (navbar, Foundations, …) y a otras pestañas
   vía el evento `storage`. */

export type Theme = "light" | "dark";
const KEY = "lp-theme";

function read(): Theme {
  try {
    return localStorage.getItem(KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

function apply(t: Theme) {
  const root = document.documentElement;
  // Bootstrap 5.3 usa su propio flag: así Card/Table/Modal/Badge de las
  // pantallas hechas solo con react-bootstrap (Desglose, Admin) siguen el tema.
  // Solo se marca en oscuro; en claro se quita para no alterar el look previo.
  // El <Navbar data-bs-theme="dark"> mantiene su barra verde en ambos modos.
  if (t === "dark") {
    root.setAttribute("data-theme", "dark");
    root.setAttribute("data-bs-theme", "dark");
  } else {
    root.removeAttribute("data-theme");
    root.removeAttribute("data-bs-theme");
  }
}

let current: Theme = read();
apply(current);

const listeners = new Set<() => void>();

function setTheme(t: Theme) {
  if (t === current) return;
  current = t;
  try {
    localStorage.setItem(KEY, t);
  } catch {
    /* no-op */
  }
  apply(t);
  listeners.forEach((l) => l());
}

if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => {
    if (e.key !== KEY) return;
    current = read();
    apply(current);
    listeners.forEach((l) => l());
  });
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function useTheme() {
  const theme = useSyncExternalStore(
    subscribe,
    () => current,
    () => current,
  );
  const toggleTheme = useCallback(
    () => setTheme(current === "dark" ? "light" : "dark"),
    [],
  );
  return { theme, toggleTheme, setTheme };
}
