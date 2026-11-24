# Abre La Papeleria (#13): levanta el backend si no esta corriendo, y
# abre el navegador en modo app (sin barra de direcciones, se ve como
# un programa normal, no como una pestana de Chrome).
#
# Esto es lo que ejecuta el acceso directo del escritorio y el arranque
# automatico -- no hace falta correrlo a mano en el uso diario.

$ErrorActionPreference = "Stop"

$raiz = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $raiz "backend"
$puerto = 5000
$url = "http://localhost:$puerto"

function Puerto-Escuchando {
    param([int]$Puerto)
    $conexion = Get-NetTCPConnection -LocalPort $Puerto -State Listen -ErrorAction SilentlyContinue
    return $null -ne $conexion
}

if (Puerto-Escuchando -Puerto $puerto) {
    # Algo ya esta escuchando en el puerto -- lo normal es que sea nuestro
    # propio backend de una sesion anterior. Confirmamos con una peticion
    # real antes de asumirlo, para dar un error claro si en realidad es
    # otra cosa ocupando el puerto (tarea explicita de #13).
    try {
        $respuesta = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
        if ($respuesta.Content -notmatch 'id="root"') {
            Write-Warning "El puerto $puerto esta ocupado, pero lo que responde no parece ser La Papeleria. Cierra el programa que este usando ese puerto, o cambia el puerto con la variable de entorno PORT."
        } else {
            Write-Host "El backend ya estaba corriendo. Abriendo el navegador..."
        }
    } catch {
        Write-Warning "El puerto $puerto esta ocupado por algo que no responde como una pagina web. Revisa que programa lo esta usando."
    }
} else {
    Write-Host "Iniciando el backend..."

    $venvPython = Join-Path $backend "venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        throw "No se encontro backend\venv. Corre scripts\instalar.ps1 primero."
    }

    # Se lanza via cmd /k (no directo) para que la ventana NO se cierre
    # sola si el backend truena al arrancar -- asi el error queda
    # visible en vez de parpadear y desaparecer.
    Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/k `"$venvPython`" main.py" `
        -WorkingDirectory $backend `
        -WindowStyle Minimized

    $intentos = 0
    while (-not (Puerto-Escuchando -Puerto $puerto) -and $intentos -lt 40) {
        Start-Sleep -Milliseconds 500
        $intentos++
    }

    if (-not (Puerto-Escuchando -Puerto $puerto)) {
        throw "El backend no respondio en el puerto $puerto despues de 20 segundos. Revisa la ventana minimizada en la barra de tareas para ver el error."
    }
}

$navegadores = @(
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
)
$navegador = $navegadores | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($navegador) {
    # --app quita la barra de direcciones y las pestanas: se ve como un
    # programa de escritorio, no como el navegador.
    Start-Process -FilePath $navegador -ArgumentList "--app=$url"
} else {
    # Sin Chrome/Edge en las rutas conocidas: se abre con el navegador
    # predeterminado, normal (con barra de direcciones).
    Start-Process $url
}
