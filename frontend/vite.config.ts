import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // El frontend llama a rutas relativas ("/api/..."), tanto en
    // produccion (Flask sirve todo desde un solo origen, ver
    // backend/main.py #12) como en desarrollo. Aqui, en desarrollo, el
    // servidor de Vite (:5173) reenvia esas llamadas al backend Flask
    // (:5000) -- asi el navegador nunca hace una peticion cruzada de
    // origen y no hace falta CORS tampoco en este modo.
    proxy: {
      '/api': 'http://localhost:5000',
    },
  },
})
