# Compila el frontend para produccion (#12).
#
# No hace falta copiar el resultado a ningun lado: vite ya lo deja en
# frontend/dist, y backend/main.py lo sirve directamente desde esa
# ruta relativa. Este script solo automatiza el paso de compilacion y
# confirma que quedo en el lugar que el backend espera.

$ErrorActionPreference = "Stop"

$raiz = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $raiz "frontend"
$dist = Join-Path $frontend "dist"

Write-Host "Compilando frontend..." -ForegroundColor Cyan
Push-Location $frontend
try {
    npm install
    npm run build
} finally {
    Pop-Location
}

if (-not (Test-Path (Join-Path $dist "index.html"))) {
    throw "El build termino pero no se encontro frontend/dist/index.html -- revisa la salida de arriba."
}

Write-Host "Listo: $dist" -ForegroundColor Green
Write-Host "Para levantar el backend en produccion:"
Write-Host "  cd backend"
Write-Host "  .\venv\Scripts\Activate.ps1"
Write-Host "  python main.py"
