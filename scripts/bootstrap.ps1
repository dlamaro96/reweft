param([switch]$Demo)
$ErrorActionPreference = "Stop"
$RepoDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoDir

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker Desktop/Engine with Compose v2 is required." }
docker compose version | Out-Null

if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }

function New-Secret { -join ((1..64) | ForEach-Object { "0123456789abcdef"[(Get-Random -Maximum 16)] }) }
function Set-IfEmpty([string]$Key) {
  $lines = Get-Content ".env"
  if (-not ($lines | Where-Object { $_ -match "^$([regex]::Escape($Key))=.+" })) {
    $value = New-Secret
    $lines = $lines | ForEach-Object { if ($_ -match "^$([regex]::Escape($Key))=") { "$Key=$value" } else { $_ } }
    [IO.File]::WriteAllLines((Join-Path $RepoDir ".env"), $lines)
  }
}
Set-IfEmpty "REWEFT_SECRET_KEY"
Set-IfEmpty "POSTGRES_PASSWORD"
Set-IfEmpty "TEMPORAL_DB_PASSWORD"
if ($Demo) { (Get-Content ".env") -replace '^REWEFT_MODE=.*', 'REWEFT_MODE=synthetic_demo' | Set-Content ".env" }

docker compose --env-file .env config | Out-Null
docker compose --env-file .env up --build --detach
$portLine = Get-Content ".env" | Where-Object { $_ -match '^REWEFT_HTTP_PORT=' } | Select-Object -First 1
$port = if ($portLine) { $portLine.Split('=',2)[1] } else { "8080" }
for ($i = 0; $i -lt 60; $i++) {
  try { Invoke-WebRequest "http://127.0.0.1:$port/api/v1/health" -UseBasicParsing | Out-Null; Write-Host "Reweft is available at http://127.0.0.1:$port"; if ($Demo) { Write-Host "Mode: SYNTHETIC DEMONSTRATION" }; exit 0 } catch { Start-Sleep -Seconds 2 }
}
throw "Reweft did not become healthy. Inspect: docker compose logs api gateway"

