param(
    [Parameter(Mandatory = $true)][string]$WorkBuddyProject,
    [string]$PythonExe = 'python',
    [switch]$SetApiKey
)

$ErrorActionPreference = 'Stop'

function Resolve-RuntimePython {
    param([string]$Executable)

    # Packaged Python can redirect AppData; WorkBuddy needs the physical executable path.
    $output = @(& $Executable -c 'from pathlib import Path; import sys; print(Path(sys.executable).resolve())')
    if ($LASTEXITCODE -ne 0 -or $output.Count -ne 1) { throw 'Resolving the installed Python executable failed.' }
    $resolved = ([string]$output[0]).Trim()
    if (-not [IO.Path]::IsPathRooted($resolved) -or -not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        throw 'The installed Python executable did not resolve to an existing absolute path.'
    }
    return [IO.Path]::GetFullPath($resolved)
}

function Write-WorkBuddyConfig {
    param([string]$ProjectPath, [string]$RuntimePython, [string]$LauncherPath, [string]$ServerPath)

    $project = [IO.Path]::GetFullPath($ProjectPath)
    if (-not (Test-Path -LiteralPath $project -PathType Container)) {
        throw 'The WorkBuddy project directory does not exist.'
    }
    $folder = Join-Path $project '.workbuddy'
    $path = Join-Path $folder 'mcp.json'
    $config = [pscustomobject]@{ mcpServers = [pscustomobject]@{} }
    if (Test-Path -LiteralPath $path) {
        $config = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($config -isnot [pscustomobject]) { throw 'mcp.json must contain a JSON object.' }
        if ($null -eq $config.PSObject.Properties['mcpServers']) {
            $config | Add-Member -MemberType NoteProperty -Name 'mcpServers' -Value ([pscustomobject]@{})
        }
        if ($config.mcpServers -isnot [pscustomobject]) { throw 'mcpServers must be a JSON object.' }
    }
    $entry = [pscustomobject]@{
        type = 'stdio'
        command = (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe')
        args = @('-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
            '-File', $LauncherPath, '-PythonExe', $RuntimePython, '-ServerPath', $ServerPath)
        env = [pscustomobject]@{ GEO_WORKSPACE = $project }
        timeout = 1800000
    }
    $config.mcpServers | Add-Member -MemberType NoteProperty -Name 'ruanwenjie-geo' -Value $entry -Force
    $json = $config | ConvertTo-Json -Depth 64
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    if (Test-Path -LiteralPath $path) {
        $backup = $path + '.backup-' + [DateTime]::Now.ToString('yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N')
        Copy-Item -LiteralPath $path -Destination $backup
    }
    $temporary = Join-Path $folder ('mcp-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [IO.File]::WriteAllText($temporary, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
        Move-Item -LiteralPath $temporary -Destination $path -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary }
    }
    return $path
}

$skill = Split-Path -Parent $PSScriptRoot
$server = Join-Path $PSScriptRoot 'geo_mcp.py'
$launcher = Join-Path $PSScriptRoot 'launch_local_mcp.ps1'
$requirements = Join-Path $skill 'requirements-mcp.txt'
foreach ($required in @($server, $launcher, $requirements)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw ('Missing skill file: ' + $required) }
}
if (-not (Test-Path -LiteralPath $WorkBuddyProject -PathType Container)) {
    throw 'The WorkBuddy project directory does not exist.'
}
if (-not $env:LOCALAPPDATA) { throw 'LOCALAPPDATA is unavailable; run this installer on Windows.' }

& $PythonExe -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ is required"'
if ($LASTEXITCODE -ne 0) { throw 'A working Python 3.10+ installation is required.' }
$privateFolder = Join-Path $env:LOCALAPPDATA 'RuanwenjieGEO'
$runtime = Join-Path $privateFolder 'runtime'
$runtimePython = Join-Path $runtime 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $runtimePython -PathType Leaf)) {
    & $PythonExe -m venv $runtime
    if ($LASTEXITCODE -ne 0) { throw 'Creating the local Python environment failed.' }
}
& $runtimePython -m pip install --disable-pip-version-check -r $requirements
if ($LASTEXITCODE -ne 0) { throw 'Installing MCP dependencies failed; WorkBuddy configuration was not changed.' }
$runtimePython = Resolve-RuntimePython -Executable $runtimePython

if ($SetApiKey) {
    Import-Module (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
    $secret = Read-Host 'OpenAI API Key (hidden; leave empty to cancel)' -AsSecureString
    if ($secret.Length -eq 0) { throw 'No API key was saved.' }
    New-Item -ItemType Directory -Path $privateFolder -Force | Out-Null
    $encrypted = ConvertFrom-SecureString -SecureString $secret
    [IO.File]::WriteAllText((Join-Path $privateFolder 'openai-key.dpapi'), $encrypted, [Text.Encoding]::ASCII)
    $secret.Dispose()
    $encrypted = $null
}
$configPath = Write-WorkBuddyConfig -ProjectPath $WorkBuddyProject -RuntimePython $runtimePython -LauncherPath $launcher -ServerPath $server
Write-Host ('MCP configuration: ' + $configPath)
Write-Host ('Python runtime: ' + $runtimePython)
if ($env:OPENAI_API_KEY -or (Test-Path -LiteralPath (Join-Path $privateFolder 'openai-key.dpapi'))) {
    Write-Host 'An API key is configured. Model access has not been verified.'
}
else {
    Write-Host 'No API key is configured. MCP can start, but GPT calls require OPENAI_API_KEY or running this installer with -SetApiKey.'
}
Write-Host 'Open the configured project in WorkBuddy and check the MCP connection. Existing customer reports were not changed.'
