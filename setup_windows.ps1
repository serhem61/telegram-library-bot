# إعداد تلقائي للبوت على Windows — يستخدم بايثون الحقيقي مهما كان اختصار python مكسوراً
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

$pyCandidates = @(
  "$env:LOCALAPPDATA\Python\bin\python.exe",
  "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe",
  "C:\Python312\python.exe", "C:\Python311\python.exe"
)
$PY = $pyCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $PY) { $PY = "py" }
Write-Host "PY=$PY"
& $PY --version

if (-not (Test-Path ".\venv\Scripts\python.exe")) {
  & $PY -m venv venv
}
.\venv\Scripts\python.exe --version
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install -r requirements.txt

if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Write-Host "تم إنشاء .env — ضع BOT_TOKEN ثم أعد التشغيل" }
.\venv\Scripts\python.exe check.py
Write-Host ""
Write-Host "للتشغيل: .\venv\Scripts\python.exe bot.py"
