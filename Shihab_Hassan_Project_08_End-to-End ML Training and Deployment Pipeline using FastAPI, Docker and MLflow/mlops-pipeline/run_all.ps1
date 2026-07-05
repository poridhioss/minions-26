# ============================================================
# run_all.ps1
# Boots the whole Customer Churn MLOps pipeline locally.
# Run from the mlops-pipeline/ folder.
# ============================================================

$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
Set-Location $root

$py = Join-Path $root '..\.venv\Scripts\python.exe'

Write-Host '============================================' -ForegroundColor Cyan
Write-Host '  Customer Churn MLOps - Local Quick Start  ' -ForegroundColor Cyan
Write-Host '============================================' -ForegroundColor Cyan
Write-Host ("Python: $py")
Write-Host ("Root  : $root")
Write-Host ''

# ---- 1. Generate synthetic data ---------------------------------------------
if (-not (Test-Path 'data\customer_churn.csv')) {
    Write-Host '[1/4] Generating synthetic data...' -ForegroundColor Yellow
    & $py data\generate_data.py
} else {
    Write-Host '[1/4] data\customer_churn.csv already exists - skipping generation.' -ForegroundColor DarkGray
}

# ---- 2. Train models + MLflow logging ---------------------------------------
if (-not (Test-Path 'models\best_model.joblib')) {
    Write-Host '[2/4] Training models (this may take a minute)...' -ForegroundColor Yellow
    & $py src\train.py
} else {
    Write-Host '[2/4] models\best_model.joblib already exists - skipping training.' -ForegroundColor DarkGray
}

# ---- 3. Start FastAPI in a new background window ----------------------------
Write-Host '[3/4] Launching FastAPI on http://localhost:8000 ...' -ForegroundColor Yellow
$apiCmd = "Set-Location '$root'; & '$py' -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
Start-Process powershell -ArgumentList '-NoExit', '-Command', $apiCmd -WindowStyle Normal

# ---- 4. Start Streamlit in a new background window --------------------------
Write-Host '[4/4] Launching Streamlit on http://localhost:8501 ...' -ForegroundColor Yellow
Start-Sleep -Seconds 4
$uiCmd = "Set-Location '$root'; & '$py' -m streamlit run app\frontend.py --server.port 8501"
Start-Process powershell -ArgumentList '-NoExit', '-Command', $uiCmd -WindowStyle Normal

Write-Host ''
Write-Host '============================================' -ForegroundColor Green
Write-Host '  Both services are starting in new windows' -ForegroundColor Green
Write-Host '  FastAPI  : http://localhost:8000/docs' -ForegroundColor Green
Write-Host '  Streamlit: http://localhost:8501' -ForegroundColor Green
Write-Host '============================================' -ForegroundColor Green
Write-Host 'When you are done, close the two pop-up PowerShell windows.'