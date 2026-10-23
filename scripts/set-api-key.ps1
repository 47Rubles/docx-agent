<#
    Настройка ключа LLM-провайдера для DocxGen Agent.

    Ключ вводится с маскировкой и хранится ТОЛЬКО в пользовательской переменной
    окружения LLM_API_KEY. В файлы он не пишется: config/settings.yaml хранит
    плейсхолдер ${LLM_API_KEY}, который подставляется в памяти при загрузке
    конфигурации.

    Тот же секрет используется в CI:
    GitHub Actions -> Settings -> Secrets and variables -> Actions ->
    New repository secret -> LLM_API_KEY.

    Использование:
      powershell -ExecutionPolicy Bypass -File scripts\set-api-key.ps1
      powershell -ExecutionPolicy Bypass -File scripts\set-api-key.ps1 -UseExistingKey
      powershell -ExecutionPolicy Bypass -File scripts\set-api-key.ps1 -Provider openai -BaseUrl https://api.openai.com/v1
#>

param(
    [switch]$UseExistingKey,
    [ValidateSet('gemini', 'openai')]
    [string]$Provider = 'gemini',
    [string]$BaseUrl
)

$ErrorActionPreference = 'Stop'

# Кириллица в консоли Windows PowerShell 5.1 иначе уходит в однобайтовую
# кодировку и читается как мусор.
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$EnvName = 'LLM_API_KEY'

if (-not $BaseUrl) {
    switch ($Provider) {
        'gemini' { $BaseUrl = 'https://generativelanguage.googleapis.com/v1beta' }
        'openai' { $BaseUrl = 'https://api.openai.com/v1' }
    }
}

Write-Host ''
Write-Host '  DocxGen Agent — настройка ключа API' -ForegroundColor Cyan
Write-Host '  ------------------------------------' -ForegroundColor Cyan

# --- получение ключа ----------------------------------------------------------
$key = $null
if ($UseExistingKey) {
    $key = [Environment]::GetEnvironmentVariable($EnvName, 'User')
    if ([string]::IsNullOrWhiteSpace($key)) { $key = $env:LLM_API_KEY }
    if ([string]::IsNullOrWhiteSpace($key)) {
        Write-Host ('Переменная ' + $EnvName + ' пуста.') -ForegroundColor Red
        Write-Host 'Запусти скрипт без -UseExistingKey и вставь ключ.' -ForegroundColor Yellow
        exit 1
    }
    Write-Host ('Ключ взят из переменной окружения ' + $EnvName + '.') -ForegroundColor DarkGray
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
if ($Provider -eq 'gemini') {
    # Ключи формата AQ.* принимаются только заголовком x-goog-api-key;
    # Authorization: Bearer с ними даёт 401.
    $headers['x-goog-api-key'] = $key
} else {
    $headers['Authorization'] = 'Bearer ' + $key
}

try {
    $resp = Invoke-RestMethod -Uri ($BaseUrl + '/models') -Headers $headers -Method Get -TimeoutSec 30 -ErrorAction Stop
    $names = @($resp.PSObject.Properties.Name)
    $count = 0
    if ($names -contains 'models') { $count = @($resp.models).Count }
    elseif ($names -contains 'data') { $count = @($resp.data).Count }
    Write-Host ('Ключ принят. Моделей доступно: ' + $count + '.') -ForegroundColor Green
} catch {
    $msg = ($_.Exception.Message -split "`n")[0]
    $msg = $msg.Replace($key, '<KEY>')
    Write-Host ('Проверить ключ не удалось: ' + $msg) -ForegroundColor Yellow
    Write-Host 'Ключ всё равно сохраню — реальная проверка будет при первом вызове.' -ForegroundColor Yellow
}

# --- сохранение ключа ---------------------------------------------------------
if (-not $UseExistingKey) {
    [Environment]::SetEnvironmentVariable($EnvName, $key, 'User')
    Set-Item -Path ('Env:' + $EnvName) -Value $key
    Write-Host ('Ключ сохранён в пользовательскую переменную ' + $EnvName + '.') -ForegroundColor Green
}

Write-Host ''
Write-Host 'Что дальше:' -ForegroundColor Cyan
Write-Host '  1. Для локальной работы переменная уже доступна в новых терминалах.'
Write-Host '  2. Для CI добавь такой же секрет в настройках репозитория на GitHub.'
Write-Host '  3. Проверить связь с провайдером: python scripts\smoke_test.py'
Write-Host ''
