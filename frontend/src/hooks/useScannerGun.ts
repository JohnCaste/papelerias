import { useEffect, useRef } from "react";

/* ==========================================================================
   useScannerGun — lectura de pistola de código de barras USB.

   Una pistola lectora se presenta al sistema como un teclado HID: al leer una
   etiqueta "teclea" los dígitos a gran velocidad y cierra con Enter (algunos
   modelos con Tab). No hace falta ninguna API de dispositivo.

   El hook escucha `keydown` en `document`, acumula los caracteres y, cuando la
   secuencia llega muy seguida y termina en Enter/Tab, entrega el código a
   `alLeer`. La escritura humana normal (con pausas mayores al umbral) nunca
   dispara el callback.
   ========================================================================== */

export interface OpcionesScanner {
  /** Máximo de ms entre teclas para considerar la ráfaga "de pistola". */
  umbralMs?: number;
  /** Largo mínimo del código para aceptarlo. */
  minLargo?: number;
}

const UMBRAL_MS = 50;
const MIN_LARGO = 3;

interface EstadoBuffer {
  buffer: string;
  ultimaTeclaMs: number;
}

/**
 * Aplica una tecla imprimible al estado del buffer. Función pura: si entre esta
 * tecla y la anterior pasó más que `umbralMs`, el buffer se reinicia (así una
 * persona tecleando despacio nunca acumula una secuencia completa).
 */
export function acumularTecla(
  estado: EstadoBuffer,
  char: string,
  ahoraMs: number,
  umbralMs: number,
): EstadoBuffer {
  const vieneSeguida = ahoraMs - estado.ultimaTeclaMs <= umbralMs;
  const base = vieneSeguida ? estado.buffer : "";
  return { buffer: base + char, ultimaTeclaMs: ahoraMs };
}

/** ¿El foco está en un campo editable donde NO debemos robar el teclado? */
function focoEnCampoEditableAjeno(): boolean {
  const el = document.activeElement as HTMLElement | null;
  if (!el) return false;
  const editable =
    el.tagName === "INPUT" ||
    el.tagName === "TEXTAREA" ||
    el.isContentEditable;
  if (!editable) return false;
  // El buscador del catálogo se marca con este atributo: ahí sí dejamos pasar
  // la lectura (además de que el texto se escriba en el propio input).
  return !el.hasAttribute("data-scanner-passthrough");
}

export function useScannerGun(
  alLeer: (codigo: string) => void,
  opciones: OpcionesScanner = {},
): void {
  const { umbralMs = UMBRAL_MS, minLargo = MIN_LARGO } = opciones;

  // `alLeer` en un ref para no re-suscribir el listener en cada render.
  const alLeerRef = useRef(alLeer);
  useEffect(() => {
    alLeerRef.current = alLeer;
  }, [alLeer]);

  useEffect(() => {
    let estado: EstadoBuffer = { buffer: "", ultimaTeclaMs: 0 };
    let limpiezaId: number | undefined;

    const reiniciar = () => {
      estado = { buffer: "", ultimaTeclaMs: 0 };
    };

    const programarLimpieza = () => {
      if (limpiezaId !== undefined) window.clearTimeout(limpiezaId);
      limpiezaId = window.setTimeout(reiniciar, umbralMs * 2);
    };

    const alPresionar = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.altKey || e.metaKey) return;
      if (focoEnCampoEditableAjeno()) return;

      if (e.key === "Enter" || e.key === "Tab") {
        const ahora = e.timeStamp;
        const seguida = ahora - estado.ultimaTeclaMs <= umbralMs;
        if (seguida && estado.buffer.length >= minLargo) {
          e.preventDefault();
          alLeerRef.current(estado.buffer);
        }
        reiniciar();
        return;
      }

      // Solo caracteres imprimibles (Shift, flechas, F5… tienen key.length > 1).
      if (e.key.length === 1) {
        estado = acumularTecla(estado, e.key, e.timeStamp, umbralMs);
        programarLimpieza();
      }
    };

    document.addEventListener("keydown", alPresionar);
    return () => {
      document.removeEventListener("keydown", alPresionar);
      if (limpiezaId !== undefined) window.clearTimeout(limpiezaId);
    };
  }, [umbralMs, minLargo]);
}
