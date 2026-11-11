param(
    [Parameter(Mandatory = $true)][string]$PythonExe,
    [Parameter(Mandatory = $true)][string]$ServerPath
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$OutputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

try {
    foreach ($required in @($PythonExe, $ServerPath)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw 'MCP runtime or server file is missing; rerun setup_local_mcp.ps1.' }
    }
    if (-not $env:OPENAI_API_KEY -and $env:LOCALAPPDATA) {
        $keyPath = Join-Path $env:LOCALAPPDATA 'RuanwenjieGEO\openai-key.dpapi'
        if (Test-Path -LiteralPath $keyPath -PathType Leaf) {
            Import-Module (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
            $secure = Get-Content -LiteralPath $keyPath -Raw -Encoding ASCII | ConvertTo-SecureString
            $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
            try { $env:OPENAI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
            finally {
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
                $secure.Dispose()
            }
        }
    }
    & $PythonExe -u $ServerPath
    exit $LASTEXITCODE
}
catch {
    [Console]::Error.WriteLine('Local GEO MCP could not start. Check the runtime and the current Windows user API-key configuration.')
    exit 1
}
