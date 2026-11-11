"""Check the Windows launcher and config merge without touching user configuration."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1] / '.codebuddy/skills/ruanwenjie-geo'
SCRIPTS = ROOT / 'scripts'
POWERSHELL = shutil.which('powershell.exe')


@unittest.skipUnless(os.name == 'nt' and POWERSHELL, 'Windows PowerShell is required')
class LocalMcpSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='geo-mcp-windows-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = os.environ.copy()
        self.env.pop('OPENAI_API_KEY', None)
        self.env['LOCALAPPDATA'] = str(self.root / 'private')
        self.env['PYTHONUTF8'] = '1'
        self.env['PYTHONIOENCODING'] = 'utf-8'

    def powershell(self, script, *args):
        path = self.root / 'test.ps1'
        path.write_text(script, encoding='utf-8-sig')
        run = subprocess.run([
            POWERSHELL, '-NoLogo', '-NoProfile', '-NonInteractive',
            '-ExecutionPolicy', 'Bypass', '-File', str(path), *map(str, args),
        ], env=self.env, capture_output=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr.decode('utf-8', errors='replace'))
        return run.stdout.decode('utf-8-sig').strip()

    def launch(self, script):
        probe = self.root / 'probe.py'
        probe.write_text(script, encoding='utf-8')
        run = subprocess.run([
            POWERSHELL, '-NoLogo', '-NoProfile', '-NonInteractive',
            '-ExecutionPolicy', 'Bypass', '-File', str(SCRIPTS / 'launch_local_mcp.ps1'),
            '-PythonExe', sys.executable, '-ServerPath', str(probe),
        ], env=self.env, capture_output=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr.decode('utf-8', errors='replace'))
        return json.loads(run.stdout.decode('utf-8-sig'))

    def test_scripts_parse_and_merge_preserves_other_servers_and_exact_backup(self):
        project = self.root / '客户 项目'
        folder = project / '.workbuddy'
        folder.mkdir(parents=True)
        old = '{"custom":"保留中文","mcpServers":{"other":{"command":"existing.exe"}}}'
        (folder / 'mcp.json').write_text(old, encoding='utf-8')
        self.powershell(r'''
param([string]$Setup,[string]$Launcher,[string]$Project)
$ErrorActionPreference='Stop'
foreach($file in @($Setup,$Launcher)) {
    $tokens=$null;$errors=$null
    $tree=[Management.Automation.Language.Parser]::ParseFile($file,[ref]$tokens,[ref]$errors)
    if($errors.Count){throw ($errors|Out-String)}
}
$tokens=$null;$errors=$null
$tree=[Management.Automation.Language.Parser]::ParseFile($Setup,[ref]$tokens,[ref]$errors)
$function=$tree.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Write-WorkBuddyConfig'},$true)
Invoke-Expression $function.Extent.Text
Write-WorkBuddyConfig -ProjectPath $Project -RuntimePython 'D:\测试 Python\python.exe' -LauncherPath $Launcher -ServerPath 'D:\中文技能\geo_mcp.py' | Out-Null
''', SCRIPTS / 'setup_local_mcp.ps1', SCRIPTS / 'launch_local_mcp.ps1', project)
        config = json.loads((folder / 'mcp.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(config['custom'], '保留中文')
        self.assertEqual(config['mcpServers']['other'], {'command': 'existing.exe'})
        entry = config['mcpServers']['ruanwenjie-geo']
        self.assertEqual(entry['args'][-1], r'D:\中文技能\geo_mcp.py')
        self.assertEqual(entry['timeout'], 1800000)
        self.assertEqual(Path(entry['env']['GEO_WORKSPACE']), project.resolve())
        backups = list(folder.glob('mcp.json.backup-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding='utf-8'), old)

    def test_bad_existing_config_is_rejected_without_write(self):
        project = self.root / 'project'
        folder = project / '.workbuddy'
        folder.mkdir(parents=True)
        old = '{"mcpServers":[]}'
        (folder / 'mcp.json').write_text(old, encoding='utf-8')
        self.powershell(r'''
param([string]$Setup,[string]$Project)
$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$tree=[Management.Automation.Language.Parser]::ParseFile($Setup,[ref]$tokens,[ref]$errors)
$function=$tree.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Write-WorkBuddyConfig'},$true)
Invoke-Expression $function.Extent.Text
$rejected=$false
try { Write-WorkBuddyConfig -ProjectPath $Project -RuntimePython 'x' -LauncherPath 'x' -ServerPath 'x' | Out-Null }
catch { $rejected=$true }
if(-not $rejected){throw 'Invalid config was accepted'}
''', SCRIPTS / 'setup_local_mcp.ps1', project)
        self.assertEqual((folder / 'mcp.json').read_text(encoding='utf-8'), old)
        self.assertEqual(list(folder.glob('*.backup-*')), [])

    def test_runtime_resolution_uses_existing_physical_path_and_rejects_invalid_output(self):
        self.powershell(r'''
param([string]$Setup,[string]$Python)
$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$tree=[Management.Automation.Language.Parser]::ParseFile($Setup,[ref]$tokens,[ref]$errors)
$function=$tree.Find({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Resolve-RuntimePython'},$true)
Invoke-Expression $function.Extent.Text
$actual=Resolve-RuntimePython -Executable $Python
if(-not [IO.Path]::IsPathRooted($actual) -or -not (Test-Path -LiteralPath $actual -PathType Leaf)){throw 'Physical Python path was not resolved'}
$global:resolvedTestPath=$actual
function Redirected-TestPython { $global:LASTEXITCODE=0; return $global:resolvedTestPath }
if((Resolve-RuntimePython -Executable 'Redirected-TestPython') -ne $actual){throw 'Redirected path was not retained'}
function Invalid-TestPython { $global:LASTEXITCODE=0; return 'relative\python.exe' }
$rejected=$false
try { Resolve-RuntimePython -Executable 'Invalid-TestPython' | Out-Null } catch { $rejected=$true }
if(-not $rejected){throw 'Invalid runtime path was accepted'}
function Noisy-TestPython { $global:LASTEXITCODE=0; return @($global:resolvedTestPath,'unexpected output') }
$rejected=$false
try { Resolve-RuntimePython -Executable 'Noisy-TestPython' | Out-Null } catch { $rejected=$true }
if(-not $rejected){throw 'Ambiguous runtime output was accepted'}
''', SCRIPTS / 'setup_local_mcp.ps1', sys.executable)

    def test_launcher_without_key_has_only_utf8_json_stdout(self):
        result = self.launch(
            "import json, os; print(json.dumps({'jsonrpc':'2.0','text':'中文通路',"
            "'configured':bool(os.environ.get('OPENAI_API_KEY'))}, ensure_ascii=False))"
        )
        self.assertEqual(result, {'jsonrpc': '2.0', 'text': '中文通路', 'configured': False})

    def test_dpapi_key_is_loaded_and_environment_takes_precedence(self):
        private = Path(self.env['LOCALAPPDATA']) / 'RuanwenjieGEO'
        private.mkdir(parents=True)
        self.powershell(r'''
param([string]$KeyPath)
$ErrorActionPreference='Stop'
Import-Module (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
$value=ConvertTo-SecureString -String 'fake-key-for-offline-unit-test' -AsPlainText -Force
$encrypted=ConvertFrom-SecureString -SecureString $value
[IO.File]::WriteAllText($KeyPath,$encrypted,[Text.Encoding]::ASCII)
$value.Dispose()
''', private / 'openai-key.dpapi')
        probe = (
            "import json,os; value=os.environ.get('OPENAI_API_KEY'); "
            "print(json.dumps({'dpapi':value=='fake-key-for-offline-unit-test',"
            "'environment':value=='fake-environment-unit-test'}))"
        )
        self.assertEqual(self.launch(probe), {'dpapi': True, 'environment': False})
        self.env['OPENAI_API_KEY'] = 'fake-environment-unit-test'
        (private / 'openai-key.dpapi').write_text('invalid ciphertext', encoding='ascii')
        self.assertEqual(self.launch(probe), {'dpapi': False, 'environment': True})


if __name__ == '__main__':
    unittest.main()
