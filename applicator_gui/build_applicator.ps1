# ==============================================================================
# Automated Build Script for Elliot Portable Desktop Applicator
# Generates standalone GUI executable without external Python dependencies
# ==============================================================================

param(
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Iniciando compilação determinística do Aplicador PT-BR v2" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\.."

Set-Location $ProjectRoot

# Verifica se o PyInstaller está disponível
Write-Host "Verificando dependências de build..." -ForegroundColor Yellow
& $PythonExe -m pip install --upgrade pyinstaller pycryptodome --quiet

# Executa o PyInstaller usando o spec oficial
Write-Host "Executando PyInstaller a partir do spec..." -ForegroundColor Yellow
& $PythonExe -m PyInstaller --clean --noconfirm "$ScriptDir\ElliotAplicadorPTBRv2.spec"

Write-Host "Compilação concluída com sucesso! Executável gerado na pasta dist/." -ForegroundColor Green
