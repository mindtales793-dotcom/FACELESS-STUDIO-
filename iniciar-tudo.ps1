# Iniciar ambos os servidores: Python (3114) + Node.js Narração (3115)
# Execute este script na raiz do diretório fcs/

# Parar servidores existentes nas portas 3114 e 3115
$c3114 = Get-NetTCPConnection -LocalPort 3114 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($c3114) { Stop-Process -Id $c3114.OwningProcess -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 1000 }

$c3115 = Get-NetTCPConnection -LocalPort 3115 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($c3115) { Stop-Process -Id $c3115.OwningProcess -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 1000 }

Remove-Item Env:APP_PASSWORD -ErrorAction SilentlyContinue

cd "C:\Users\Lucas\Downloads\faceless_cloud_studio_v4 (1)\fcs"

Write-Host "🚀 Iniciando servidor Python (porta 3114)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '.'; Remove-Item Env:APP_PASSWORD -ErrorAction SilentlyContinue; .\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 3114`""

Start-Sleep -Seconds 2

Write-Host "🚀 Iniciando servidor Node.js Narração (porta 3115)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit -Command `"cd '.'; node server-narration.js`""

Write-Host ""
Write-Host "✅ Servidores iniciados!" -ForegroundColor Green
Write-Host "   Python (FastAPI):  http://127.0.0.1:3114" -ForegroundColor Yellow
Write-Host "   Node.js (Narração): http://127.0.0.1:3115" -ForegroundColor Yellow
Write-Host ""
Write-Host "📋 Endpoints de narração:" -ForegroundColor Cyan
Write-Host "   POST  http://127.0.0.1:3114/api/narrations-proxy" -ForegroundColor Yellow
Write-Host "   GET   http://127.0.0.1:3114/api/narrations-proxy/{id}" -ForegroundColor Yellow
Write-Host "   GET   http://127.0.0.1:3114/api/narrations-proxy/{id}/download" -ForegroundColor Yellow
Write-Host ""
Write-Host "Ou use o Node.js diretamente:" -ForegroundColor Cyan
Write-Host "   POST  http://127.0.0.1:3115/api/narration/generate" -ForegroundColor Yellow
Write-Host "   GET   http://127.0.0.1:3115/api/narration/{id}/events (SSE)" -ForegroundColor Yellow
