# 新机器初始化：创建虚拟环境、安装依赖、生成 .env
# 用法：powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

# 工具包 runtime（scripts/run.py、query.py、install.py）
$rootPy = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $rootPy)) {
    Write-Host '[runtime] 创建虚拟环境' -ForegroundColor Cyan
    python -m venv (Join-Path $root '.venv')
}
Write-Host '[runtime] 安装依赖' -ForegroundColor Cyan
& $rootPy -m pip install --upgrade pip
& $rootPy -m pip install -r (Join-Path $root 'requirements.txt')

foreach ($tool in @('hexin-db-tools', 'hexin-data-gen')) {
    $dir = Join-Path $root $tool
    $py = Join-Path $dir '.venv\Scripts\python.exe'

    if (-not (Test-Path $py)) {
        Write-Host "[$tool] 创建虚拟环境" -ForegroundColor Cyan
        python -m venv (Join-Path $dir '.venv')
    }

    Write-Host "[$tool] 安装依赖" -ForegroundColor Cyan
    & $py -m pip install --upgrade pip
    & $py -m pip install -r (Join-Path $dir 'requirements.txt')

    $envFile = Join-Path $dir '.env'
    if (-not (Test-Path $envFile)) {
        Copy-Item (Join-Path $dir '.env.example') $envFile
        Write-Host "[$tool] 已生成 .env，请填入账号密码" -ForegroundColor Yellow
    }
}

$e2e = Join-Path $root 'hexin-e2e'
if (-not (Test-Path (Join-Path $e2e 'node_modules'))) {
    Write-Host '[hexin-e2e] 安装 npm 依赖' -ForegroundColor Cyan
    Push-Location $e2e
    $env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = '1'
    npm install
    Pop-Location
}

Write-Host '初始化完成' -ForegroundColor Green
