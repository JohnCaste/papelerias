# Handoff → Claude Design · Rediseño de Login (lapape)

**Fecha:** 2026-09-02
**Pantalla:** `/` — Login
**Entregable esperado:** bundle `Login lapape.dc.html` (artboards + notas de anatomía), mismo formato que los handoffs previos (`Foundations lapape`, `Ventas lapape`, `Catalogo lapape`).

---

## 1. Objetivo

Rediseñar la pantalla de inicio de sesión:

1. **Navbar** — ajustar colores (traer presencia del verde de marca).
2. **Card de login** — refinar jerarquía, espaciado, elevación y estados.
3. **Logo** — incorporar el logo nuevo de la marca en la pantalla.

### Decisiones ya tomadas (no re-abrir)

| Tema | Decisión |
|---|---|
| Navbar en el login | **Ocultarlo.** El login es una pantalla de auth limpia, sin navbar. Hoy `<Menu>` se renderiza fuera de `<Routes>` en `App.tsx` y aparece encima del login; el rediseño asume que se condiciona para NO montarse en `/`. |
| Dirección de color | **Verde de marca presente.** Navbar (para el resto de la app) y acentos del login con `--lp-green`; card blanca con detalle verde. |
| Logo | El PNG se **adjunta directamente en la sesión de Claude Design** (el objeto en GCS es privado). Usar un placeholder de ~logo en los artboards y anotar dónde va. |
| Paleta base | Verde de marca sobre grises slate. El pedido histórico "naranja/azul/gris" quedó descartado el 2026-09-01. |

---

## 2. Alcance

Aunque la pantalla de login ya no lleva navbar, el usuario pidió “ajustar colores del navbar”. El navbar vive en el **shell autenticado** (post-login), así que el handoff cubre **dos piezas**:

### 2a. Login screen (sin navbar)
- Fondo de pantalla.
- Zona de marca (logo + wordmark “La pape”).
- Card de login: título, campos, toggle de contraseña, alerta de error, botón / spinner.
- Estados: idle, focus, error (credenciales / validación), loading, disabled.
- Responsive: móvil (card full-width con padding) y desktop (card centrada, `max-width` ~360–400px).
- Light y dark theme.

### 2b. Navbar (shell autenticado) — refresh de color
- Variante actual: `<Navbar bg="dark" data-bs-theme="dark">`, fondo `--lp-gray-800`, links en texto inverso, hover/active en primary.
- Objetivo: incorporar verde de marca (elegir UNA vía y mostrarla):
  - **Opción A** — barra verde: `background: --lp-color-primary` (green-600), links en `--lp-color-primary-text`, hover con capa sutil.
  - **Opción B** — barra slate + acento verde: mantener `--lp-gray-800`, mover el indicador de link activo / borde inferior / brand a verde.
- Incluir: brand con logo nuevo (30px), 5 links (`Vender`, `Catálogo`, `Ventas`, `Dashboard`, `Corte`), buscador (input claro sobre barra), dropdown “Usuario” (panel claro elevado con `Administración`, `Registros`, `Salir`).
- Anotar contraste AA de links y placeholder del buscador contra el fondo elegido.

---

## 3. Estado actual (para referencia / “antes”)

### `frontend/src/pages/Login.tsx` — anatomía
```
<div.login-container>            fondo pantalla, flex center, min-height 100vh
  <form.login-card>
    <h2>Iniciar sesión</h2>
    {error} → <AlertaMsj variant="danger" onClose>   (auto-cierra a los 3s)
    {toast} → <p.toast>                               (fixed top-right, rojo, 5s)
    <div.login-field>
      <label>Nombre</label>
      <input type="text" placeholder="Usuario">
    <div.login-field>
      <label>Contraseña</label>
      <input type={shown?text:password} placeholder="Contraseña" disabled={loading}>
      <button.toggle-password>{shown ? "Ocultar" : "Mostrar"}</button>   (link-style)
    <div.entrar>
      loading ? <Spinner variant="primary"> : <Button variant="secondary" type="submit">Ingresar</Button>
```

### Reglas de negocio del form (mantener)
- Ambos campos obligatorios → error `"Todos los campos son obligatorios"`.
- Password < 6 chars → error `"La contraseña debe tener al menos 6 caracteres"`.
- Fallo de auth → error `"Usuario o contraseña incorrectos"`.
- Éxito → `navigate("/catalogo")`.
- El error se auto-borra a los 3s (además del botón de cierre del alert).

### CSS actual (`Login.css`) — ya está en tokens
- `.login-container`: `min-height:100vh`, flex center, `padding: --lp-space-4`, `background: --lp-gray-800`.
- `.login-card`: `--lp-color-surface`, `padding: --lp-space-8`, `radius --lp-radius-lg`, `max-width 360px`, `shadow --lp-shadow-2`.
- `.login-card h2`: centrado, `--lp-font-size-2xl`, semibold, `mb --lp-space-6`.
- `.login-field`: columna, `mb --lp-space-4`; label `--lp-font-size-sm` medium.
- `.login-field input`: `height --lp-control-height-md`, `pad-x --lp-control-pad-x-md`, borde `--lp-color-border-strong`, `radius --lp-radius-md`; focus → borde primary + `--lp-focus-ring`; disabled → `--lp-color-disabled-bg/-text`.
- `.toggle-password`: botón estilo link, `--lp-color-link`, `--lp-font-size-xs`.
- `.toast`: fixed top-right, `--lp-color-danger`, texto blanco, `--lp-shadow-3`, animación fadeInOut 3s.
- `.entrar`: centrado. **Ojo:** `.entrar` también lo consumía `Catalogo.tsx` en el pasado; verificar antes de renombrar/borrar (hoy Catálogo ya no lo usa).

### Botón actual
Usa `variant="secondary"` (azul). Evaluar cambiar a `variant="primary"` (verde de marca) para que el CTA sea la acción principal — **decisión para el handoff**.

---

## 4. Sistema de diseño — tokens disponibles

Fuente: `frontend/src/index.css`. **La UI consume SOLO tokens semánticos (`--lp-color-*`, `--lp-shadow-*`, `--lp-focus-ring`); nunca un primitivo directo ni un hex suelto.** Los primitivos se listan solo para que Claude Design entienda las escalas.

### Semánticos · tema claro
```
--lp-color-bg              gray-50      fondo de app
--lp-color-surface         #FFFFFF      card / panel
--lp-color-surface-raised  #FFFFFF
--lp-color-border          gray-200
--lp-color-border-strong   gray-300     borde de inputs
--lp-color-text            gray-900
--lp-color-text-muted      gray-500
--lp-color-text-inverse    #FFFFFF

--lp-color-primary         green-600  #268038   (blanco encima = AA 4.96:1)
--lp-color-primary-hover   green-700
--lp-color-primary-text    #FFFFFF
--lp-color-secondary       blue-500   #2563EB
--lp-color-link            blue-600

--lp-color-danger          #DC2626   (+ -subtle #FEE2E2, -text #B91C1C)
--lp-color-success/-warning/-info   (con -subtle y -text)

--lp-color-disabled-bg     gray-200
--lp-color-disabled-text   gray-400
--lp-color-overlay         rgba(15,23,42,.45)
```

### Semánticos · tema oscuro (`[data-theme="dark"]`)
```
--lp-color-bg              gray-900
--lp-color-surface         gray-800
--lp-color-surface-raised  gray-700
--lp-color-border          gray-700
--lp-color-text            gray-50
--lp-color-primary         green-400  #47B15F
--lp-color-primary-text    gray-900
--lp-color-link            blue-300
```

### Elevación / foco
```
--lp-shadow-1  0 1px 2px    · --lp-shadow-2  0 4px 12px
--lp-shadow-3  0 10px 24px  · --lp-shadow-4  0 20px 48px
--lp-focus-ring  0 0 0 3px var(--lp-color-focus-ring)
```

### Primitivos relevantes
- **Espaciado (base 4):** `--lp-space-1..16` → 4,8,12,16,20,24,32,40,48,64px.
- **Radios:** sm 4 · md 6 · lg 8 · xl 12 · pill 999 · circle 50%.
- **Tipografía:** `--lp-font-sans` (system-ui …); tamaños xs12 sm14 md16 lg18 xl20 2xl24 3xl30 4xl40; pesos 400/500/600/700; line tight1.2 snug1.35 normal1.5 relaxed1.65.
- **Control:** `--lp-control-height-sm/md/lg` = 32/40/48; `--lp-control-pad-x-sm/md/lg` = 12/16/22.
- **Iconos (lucide-react):** `--lp-icon-size-sm/md/lg` = 14/16/18; `--lp-icon-stroke` = 2.
- **Verde escala:** 50 `#EEF8F0` · 100 `#D2EFD8` · 200 `#A6DFB3` · 300 `#74C888` · 400 `#47B15F` · 500 `#309C43` (marca) · 600 `#268038` · 700 `#1F672E` · 800 `#1A5527` · 900 `#164421`.

---

## 5. Marca / logo

- El **logo nuevo** (`papeLog.png`) se adjunta en la sesión de Claude Design — no está accesible por URL pública.
- Mascotas de marca existentes en `frontend/public/` como referencia de estilo: sacapuntas azul con cara + goma naranja/azul, estilo cartoon, contorno negro, guantes blancos.
- Wordmark: **“La pape”** (papelería). Definir en el handoff: ¿logo solo, o logo + wordmark? ¿lockup horizontal o vertical en el login?
- Tratamiento sugerido en el login: logo por encima de la card (zona de marca), ~48–72px de alto, centrado. En el navbar: 30px, alineado a la izquierda junto al wordmark.
- Anotar: el logo cartoon es a color y de alto contraste — si el fondo del login es verde/slate oscuro, verificar que el logo respire (posible “cápsula” blanca / halo, o versión sobre superficie clara).

---

## 6. Requisitos y restricciones

- **Stack destino:** React 19 + Vite + TS + React-Bootstrap 5.3 + lucide-react. Los artboards se portan a `Login.tsx` + `Login.css` en un PR aparte.
- **Solo tokens semánticos** en el CSS resultante; puente `--lp-* → --bs-*` ya existe en `index.css`.
- **Light + dark**: entregar ambos. Dark = `[data-theme="dark"]` en un ancestro.
- **Contraste AA** en texto y controles; anotar ratios de los pares críticos (links de navbar, placeholder, botón CTA, texto sobre fondo de pantalla).
- **Foco visible siempre**: `--lp-focus-ring` / outline; nunca `outline:none` sin reemplazo. Aplica a inputs, toggle de contraseña, botón, y links del navbar.
- **Touch targets ≥ 44px** en móvil (inputs ya a 40px de alto — evaluar `--lp-control-height-lg` = 48 en móvil).
- **Reduced motion**: la animación del toast/alert debe degradar (ya hay `@media (prefers-reduced-motion)` global).
- No romper las reglas de negocio del form (§3).

---

## 7. Preguntas abiertas para resolver en el handoff

1. **CTA**: ¿botón `primary` (verde) en vez de `secondary` (azul)? ¿ancho completo de la card?
2. **Navbar**: ¿Opción A (barra verde) u Opción B (slate + acento verde)? — mostrar la elegida, mencionar la otra.
3. **Logo lockup**: solo isotipo vs. isotipo + “La pape”; orientación en login.
4. **Fondo del login**: ¿slate `--lp-gray-800` actual, verde de marca, gradiente sutil, o superficie clara con la card como panel? 
5. **Error**: ¿alert dentro de la card (actual) o inline por campo? ¿se conserva el `.toast` fixed top-right o se elimina en favor del alert?
6. **Toggle de contraseña**: ¿texto “Mostrar/Ocultar” (actual) o ícono ojo de lucide (`Eye` / `EyeOff`) dentro del input?
7. **Densidad**: `padding` de la card (`--lp-space-8` actual) y `max-width` (360 actual → ¿400?).

---

## 8. Checklist de artboards sugerido

- [ ] Login — desktop, light, idle
- [ ] Login — desktop, light, con error
- [ ] Login — desktop, light, loading
- [ ] Login — desktop, dark
- [ ] Login — móvil (375px), light
- [ ] Navbar — shell autenticado, opción elegida, light + dark
- [ ] Notas de anatomía: tokens por elemento, estados de input (idle/focus/error/disabled), specs del botón, specs del lockup de logo, ratios de contraste
