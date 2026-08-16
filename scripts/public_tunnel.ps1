$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker no está disponible. Instala o inicia Docker Desktop."
}
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    throw "cloudflared no está disponible."
}

$env:OLLAMA_HOST = "0.0.0.0:11434"
Write-Host "Asegúrate de reiniciar Ollama después de establecer OLLAMA_HOST=0.0.0.0:11434."
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw "No se pudo iniciar el contenedor." }

Write-Host "Creando enlace público temporal. Mantén esta ventana abierta."
cloudflared tunnel --url http://127.0.0.1:5000
