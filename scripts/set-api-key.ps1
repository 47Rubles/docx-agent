<#
    Настройка ключа LLM-провайдера для DocxGen Agent.

    Ключ вводится с маскировкой и хранится ТОЛЬКО в пользовательской переменной
    окружения LLM_API_KEY. В файлы он не пишется: config/settings.yaml хранит
    плейсхолдер ${LLM_API_KEY}, который подставляется в памяти при загрузке.

    Скрипт сам читает config/settings.yaml и подстраивается под провайдера:
      * auth_style: header  -> ключ уходит в заголовок auth_header (Google, x-goog-api-key)
      * auth_style: bearer  -> ключ уходит в Authorization: Bearer (Groq, OpenAI-совместимые)

    Тот же секрет используется в CI:
    GitHub Actions -> Settings -> Secrets and variables -> Actions ->
    New repository secret -> LLM_API_KEY.

    Использование:
      powershell -ExecutionPolicy Bypass -File scripts\set-api-key.ps1
      powershell -ExecutionPolicy Bypass -File scripts\set-api-key.ps1 -UseExistingKey
#>

param(
    [switch]$UseExistingKey,
    [string]$ConfigPath
)

$ErrorActionPreference = 'Stop'

# Кириллица в консоли Windows PowerShell 5.1 иначе уходит в однобайтовую
# кодировку и читается как мусор.
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$EnvName = 'LLM_API_KEY'

if (-not $ConfigPath) {
    $ConfigPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'config\settings.yaml'
}
if (-not (Test-Path -LiteralPath $ConfigPath)) {
    Write-Error ("Не найден файл конфигурации: " + $ConfigPath)
    exit 1
}

# --- чтение секции llm из конфига ---------------------------------------------
function Get-LlmBlock {
    param([string]$Text)
    $lines = $Text -split "`r?`n"
    $inside = $false
    $block = @()
    foreach ($line in $lines) {
        if ($line -match '^llm:\s*$') { $inside = $true; continue }
        if ($inside -and $line -match '^[A-Za-z_][A-Za-z0-9_]*:') { break }
        if ($inside) { $block += $line }
    }
    return ($block -join "`n")
}

function Get-YamlValue {
    param([string]$Text, [string]$Key, [string]$Default = '')
    $pattern = '(?m)^\s+' + [regex]::Escape($Key) + '\s*:\s*(.+?)\s*$'
    $match = [regex]::Match($Text, $pattern)
    if (-not $match.Success) { return $Default }
    return $match.Groups[1].Value.Trim().Trim('"', "'")
}

$yaml = Get-Content -LiteralPath $ConfigPath -Raw
$llmBlock = Get-LlmBlock -Text $yaml

$Provider   = Get-YamlValue -Text $llmBlock -Key 'provider'   -Default 'unknown'
$BaseUrl    = Get-YamlValue -Text $llmBlock -Key 'base_url'
$AuthStyle  = Get-YamlValue -Text $llmBlock -Key 'auth_style' -Default 'bearer'
$AuthHeader = Get-YamlValue -Text $llmBlock -Key 'auth_header' -Default 'x-goog-api-key'

if (-not $BaseUrl) {
    Write-Error 'В секции llm конфигурации не найден base_url.'
    exit 1
}

# Имя переменной, которую читает именно этот провайдер.
switch ($Provider) {
    'groq'    { $ProviderVar = 'GROQ_API_KEY' }
    'gemini'  { $ProviderVar = 'GEMINI_API_KEY' }
    'anthropic' { $ProviderVar = 'ANTHROPIC_API_KEY' }
    default   { $ProviderVar = $EnvName }
}

Write-Host ''
Write-Host '  DocxGen Agent — настройка ключа API' -ForegroundColor Cyan
Write-Host '  ------------------------------------' -ForegroundColor Cyan
Write-Host ('  Провайдер: ' + $Provider) -ForegroundColor DarkGray
Write-Host ('  Endpoint:  ' + $BaseUrl) -ForegroundColor DarkGray
if ($AuthStyle -eq 'header') {
    Write-Host ('  Ключ уйдёт в заголовке: ' + $AuthHeader) -ForegroundColor DarkGray
} else {
    Write-Host '  Ключ уйдёт в заголовке: Authorization: Bearer' -ForegroundColor DarkGray
}

# --- получение ключа ----------------------------------------------------------
$key = $null
if ($UseExistingKey) {
    # Сначала переменная провайдера, затем общая LLM_API_KEY, затем окружение процесса.
    foreach ($candidate in @($ProviderVar, $EnvName)) {
        $key = [Environment]::GetEnvironmentVariable($candidate, 'User')
        if ([string]::IsNullOrWhiteSpace($key)) { $key = [Environment]::GetEnvironmentVariable($candidate, 'Process') }
        if (-not [string]::IsNullOrWhiteSpace($key)) { break }
    }
    if ([string]::IsNullOrWhiteSpace($key)) {
        Write-Host ('Переменные ' + $ProviderVar + ' и ' + $EnvName + ' пусты.') -ForegroundColor Red
        Write-Host 'Запусти скрипт без -UseExistingKey и вставь ключ.' -ForegroundColor Yellow
        exit 1
    }
    Write-Host ('Ключ взят из переменной окружения ' + $ProviderVar + '.') -ForegroundColor DarkGray
} else {
    Write-Host ('Ключ сохранится в пользовательской переменной окружения ' + $EnvName + '.')
    Write-Host 'В файлы, в репозиторий и в чат он не попадёт.'
    Write-Host ''
    $secure = Read-Host 'Вставь API-ключ' -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }

    if ([string]::IsNullOrWhiteSpace($key)) {
        Write-Host 'Пустой ключ, ничего не сохранено.' -ForegroundColor Red
        exit 1
    }
}

# --- проверка ключа -----------------------------------------------------------
$headers = @{ 'User-Agent' = 'docx-agent-setup' }
if ($AuthStyle -eq 'header') {
    # Google: ключи формата AQ.* принимаются только заголовком x-goog-api-key;
    # Authorization: Bearer с ними даёт 401.
    $headers[$AuthHeader] = $key
} else {
    $headers['Authorization'] = 'Bearer ' + $key
}

# Groq и Google с этой машины доступны только через прокси: .NET в PowerShell
# 5.1 не читает переменные HTTP_PROXY, поэтому прокси указываем явно.
$proxy = $env:HTTPS_PROXY
if ([string]::IsNullOrWhiteSpace($proxy)) { $proxy = $env:HTTP_PROXY }
$proxyArgs = @{}
if (-not [string]::IsNullOrWhiteSpace($proxy)) {
    $proxyArgs['Proxy'] = $proxy
    Write-Host ('  Прокси: ' + $proxy) -ForegroundColor DarkGray
}

try {
    $resp = Invoke-RestMethod -Uri ($BaseUrl + '/models') -Headers $headers -Method Get -TimeoutSec 30 -ErrorAction Stop @proxyArgs
    $names = @($resp.PSObject.Properties.Name)
    $count = 0
    if ($names -contains 'models') { $count = @($resp.models).Count }
    elseif ($names -contains 'data') { $count = @($resp.data).Count }
    Write-Host ('  Ключ принят. Моделей доступно: ' + $count + '.') -ForegroundColor Green
} catch {
    $msg = ($_.Exception.Message -split "`n")[0]
    $msg = $msg.Replace($key, '<KEY>')
    Write-Host ('  Проверить ключ не удалось: ' + $msg) -ForegroundColor Yellow
    Write-Host '  Ключ всё равно сохраню — реальная проверка будет при первом вызове.' -ForegroundColor Yellow
}

# --- сохранение ключа ---------------------------------------------------------
if (-not $UseExistingKey) {
    # Ключ сохраняется дважды: под имя провайдера (её читает opencode.json
    # в блоке provider) и под общее имя LLM_API_KEY (её читает MCP-сервер,
    # CI-секрет и все остальные потребители). Это один и тот же секрет.
    [Environment]::SetEnvironmentVariable($ProviderVar, $key, 'User')
    Set-Item -Path ('Env:' + $ProviderVar) -Value $key
    Write-Host ('  Ключ сохранён в ' + $ProviderVar + ' (пользовательская переменная).') -ForegroundColor Green

    if ($ProviderVar -ne $EnvName) {
        [Environment]::SetEnvironmentVariable($EnvName, $key, 'User')
        Set-Item -Path ('Env:' + $EnvName) -Value $key
        Write-Host ('  Ключ сохранён в ' + $EnvName + ' (пользовательская переменная).') -ForegroundColor Green
    }
}

Write-Host ''
Write-Host 'Что дальше:' -ForegroundColor Cyan
Write-Host '  1. Локально переменная уже доступна в новых терминалах.'
Write-Host '  2. Для CI добавь такой же секрет в настройках репозитория на GitHub.'
Write-Host '  3. Проверить связь с провайдером: python scripts\smoke_test.py'
Write-Host ''
