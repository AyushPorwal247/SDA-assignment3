$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Python = "python"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) { $Python = $VenvPython }

Write-Host "Starting Kafka live components..." -ForegroundColor Cyan
Write-Host "Keep the four new PowerShell windows open." -ForegroundColor Yellow

# Start consumer first, so it does not miss live events.
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root'; & '$Python' buckling_engine.py"
Start-Sleep -Seconds 2

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root'; & '$Python' weather_producer.py"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root'; & '$Python' rail_temperature_producer.py"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$Root'; & '$Python' train_movement_producer.py"

Write-Host "Live components started." -ForegroundColor Green
Write-Host "Open Grafana: http://localhost:3000"
