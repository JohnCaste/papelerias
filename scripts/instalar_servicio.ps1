# Instala el backend como Servicio de Windows (#servicio) -- OPCIONAL,
# aparte de scripts\instalar.ps1.
#
# Por que aparte: instalar un servicio de Windows requiere privilegios
# de Administrador; scripts\instalar.ps1 esta pensado para correr SIN
# elevar (crea un venv, hace pip install, copia un acceso directo), asi
# que forzar elevacion ahi rompe ese flujo simple. Este script es un
# paso deliberado que se corre UNA VEZ, cuando se quiere que el backend
# arranque con Windows sin que nadie tenga que iniciar sesion primero.
#
# Requisito previo: haber corrido scripts\instalar.ps1 al menos una vez
# (necesita el venv y backend\.env ya configurados).
#
# Que hace:
#   1. Se relanza a si mismo elevado si hace falta.
#   2. Registra las DLLs de pywin32 (idempotente).
#   3. Instala el servicio, corriendo con la cuenta de Windows actual
#      (no LocalSystem -- ver design.md: asi lee la llave de GCP en
#      C:\Users\<usuario>\secretos\ sin tocar permisos NTFS).
#   4. Configura reinicio automatico si el proceso truena (pywin32 no
#      lo hace por si solo).
#   5. Arranca el servicio.
#
# Idempotente: se puede correr mas de una vez (por ejemplo, tras
# actualizar el codigo) sin duplicar el servicio.

$ErrorActionPreference = "Stop"

# ------------------------------------------------------- 1. Elevacion
$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) {
    Write-Host "Este paso necesita privilegios de Administrador -- reabriendo elevado..." -ForegroundColor Yellow
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

$raiz = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $raiz "backend"
$python = Join-Path $backend "venv\Scripts\python.exe"
$servicio = Join-Path $backend "servicio_windows.py"
$nombreServicio = "LaPapeleria"

if (-not (Test-Path $python)) {
    throw "No se encontro backend\venv. Corre scripts\instalar.ps1 primero."
}
if (-not (Test-Path (Join-Path $backend ".env"))) {
    throw "No se encontro backend\.env. Configuralo primero (ver INSTALAR.md, Paso 3) -- el servicio no arranca sin el."
}

Write-Host "1/4 Registrando componentes de pywin32..." -ForegroundColor Cyan
$postinstall = Join-Path $backend "venv\Scripts\pywin32_postinstall.py"
& $python $postinstall -install -silent

Write-Host "2/4 Instalando el servicio (correra con tu cuenta de Windows actual)..." -ForegroundColor Cyan
Write-Host "    Se te pedira tu clave de Windows -- pywin32 la necesita para" -ForegroundColor Gray
Write-Host "    configurar con que cuenta arranca el servicio; no se guarda en ningun" -ForegroundColor Gray
Write-Host "    archivo de este proyecto." -ForegroundColor Gray

$usuario = "$env:COMPUTERNAME\$env:USERNAME"
$claveSegura = Read-Host -AsSecureString "Clave de Windows para $usuario"
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($claveSegura)
try {
    $clavePlana = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

$servicioExistente = Get-Service -Name $nombreServicio -ErrorAction SilentlyContinue
if ($servicioExistente) {
    Write-Host "    Ya estaba instalado -- actualizando la configuracion." -ForegroundColor Gray
    & $python $servicio update --username $usuario --password $clavePlana --startup auto
} else {
    & $python $servicio install --username $usuario --password $clavePlana --startup auto
}
$clavePlana = $null  # no dejarla viva en memoria mas de lo necesario

Write-Host "3/4 Configurando reinicio automatico ante fallo..." -ForegroundColor Cyan
# pywin32 no configura esto por si solo -- sc.exe si. reset=86400 (24h):
# el contador de fallos consecutivos se reinicia si el servicio aguanta
# un dia completo sin tronar.
sc.exe failure $nombreServicio reset= 86400 actions= restart/60000/restart/60000/restart/60000 | Out-Null

Write-Host "4/4 Arrancando el servicio..." -ForegroundColor Cyan
Start-Service -Name $nombreServicio

Write-Host ""
Write-Host "Listo." -ForegroundColor Green
Write-Host "El backend ahora arranca con Windows, sin necesidad de iniciar sesion."
Write-Host "Verificar estado: Get-Service $nombreServicio"
Write-Host "Detenerlo: Stop-Service $nombreServicio    -- Quitarlo: $python $servicio remove (elevado)"
