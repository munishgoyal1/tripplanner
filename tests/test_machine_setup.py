from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def shell_probe(tmp_path, body, executables=None):
    if os.name == "nt":
        pytest.skip("macOS Bash installer probes require a POSIX host")
    source = (ROOT / 'scripts/setup-dev-machine-macos.sh').read_text()
    helpers = source[source.index('resolve_python313()'):source.index('ensure_tool azure-cli')]
    for name, script in (executables or {}).items():
        path = tmp_path / name
        path.write_text('#!/bin/bash\n' + script)
        path.chmod(0o755)
    return subprocess.run(
        ['/bin/bash', '-c', 'set -eu\nskip_tool_install=false\n'
         'assert_command() { command -v "$1" >/dev/null; }\n' + helpers + body],
        env={**os.environ, 'PATH': str(tmp_path)}, capture_output=True, text=True,
    )


def test_existing_cli_does_not_invoke_homebrew(tmp_path):
    result = shell_probe(tmp_path, 'ensure_tool node node formula', {'node': 'exit 0'})
    assert result.returncode == 0, result.stderr
    assert '[ok] node' in result.stdout
    assert '[install]' not in result.stdout


def test_python313_under_generic_name_is_reused(tmp_path):
    result = shell_probe(tmp_path, 'ensure_tool python@3.13 python3.13 formula',
                         {'python3': 'exit 0'})
    assert result.returncode == 0, result.stderr
    assert '[ok] Python 3.13' in result.stdout


def test_wrong_python_minor_fails_without_install_when_disabled(tmp_path):
    result = shell_probe(tmp_path,
                         'skip_tool_install=true; ensure_tool python@3.13 python3.13 formula',
                         {'python3': 'exit 1'})
    assert result.returncode != 0
    assert '--skip-tool-install was supplied' in result.stderr


def test_registered_but_unlinked_package_is_not_reinstalled(tmp_path):
    result = shell_probe(tmp_path, 'ensure_tool node node formula', {'brew': 'exit 0'})
    assert result.returncode != 0
    assert 'already installed' in result.stderr
    assert '[install]' not in result.stdout


def test_missing_tool_installs_once_then_skips(tmp_path):
    result = shell_probe(tmp_path, 'ensure_tool node node formula; ensure_tool node node formula', {
        'brew': '''if [[ "$1" == list ]]; then exit 1; fi
[[ "$1 $2 $3" == 'install --formula node' ]] || exit 9
[[ "$HOMEBREW_NO_INSTALL_UPGRADE" == 1 ]] || exit 8
printf '#!/bin/bash\\nexit 0\\n' > "$PATH/node"
/bin/chmod +x "$PATH/node"
''',
    })
    assert result.returncode == 0, result.stderr
    assert result.stdout.count('[install] node') == 1
    assert result.stdout.count('[ok] node') == 1


def run_powershell(script):
    pwsh = shutil.which('pwsh')
    if not pwsh:
        pytest.skip('PowerShell 7 is required for setup probes')
    result = subprocess.run([pwsh, '-NoProfile', '-Command', script], cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def test_powershell_setup_files_parse():
    run_powershell('''
$ErrorActionPreference = 'Stop'
foreach ($file in @('scripts/setup-dev-machine.ps1', 'devconfigs/Apply-DevConfigs.ps1',
                    'scripts/dev/lib/setup-tool-detection.ps1')) {
    $tokens = $null; $errors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile(
        (Join-Path (Get-Location) $file), [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw ($errors | Out-String) }
}
''')


@pytest.mark.parametrize('exit_code,allowed', [(0, False), (-1978335212, True), (1, False)])
def test_windows_package_lookup_fails_closed(exit_code, allowed):
    result = run_powershell(f'''
. ./scripts/dev/lib/setup-tool-detection.ps1
function winget {{ $global:LASTEXITCODE = {exit_code} }}
try {{ Assert-SetupPackageMissing 'Test.Package'; Write-Output 'allowed' }}
catch {{ Write-Output 'blocked' }}
''')
    assert result.stdout.strip() == ('allowed' if allowed else 'blocked')


def test_extensions_installed_as_dependencies_are_not_reinstalled():
    run_powershell(r'''
$ErrorActionPreference = 'Stop'
$script:PSScriptRoot = Join-Path (Get-Location) 'devconfigs'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $PSScriptRoot 'Apply-DevConfigs.ps1'), [ref]$tokens, [ref]$errors)
$fn = $ast.Find({ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -eq 'Install-VsCodeExtensions'
}, $true)
Invoke-Expression $fn.Extent.Text
$script:installed = @('existing.extension')
$script:installs = @()
function global:code {
    $global:LASTEXITCODE = 0
    switch ($args[0]) {
        '--list-extensions' { $script:installed }
        '--locate-extension' {
            if ($args[1] -eq 'bundled.extension') { '/bundled/path' }
        }
        '--install-extension' {
            $script:installs += $args[1]
            $script:installed += @($args[1], 'dependency.extension')
        }
    }
}
# Resolve-VsCodeCli ordinarily accepts only an Application; replace just that
# dependency in the function under test, leaving extension decisions executable.
$definition = $fn.Extent.Text -replace
    '\$code = Resolve-VsCodeCli', '$code = "code"'
$definition = $definition -replace '\. \(Join-Path \$PSScriptRoot[^\r\n]+', ''
$definition = $definition.Replace('function Install-VsCodeExtensions {',
    'function Install-VsCodeExtensions { [CmdletBinding(SupportsShouldProcess=$true)]')
Invoke-Expression $definition
$manifest = [IO.Path]::GetTempFileName()
try {
    Set-Content $manifest @('existing.extension', 'bundled.extension',
        'parent.extension', 'dependency.extension')
    Install-VsCodeExtensions $manifest
    Install-VsCodeExtensions $manifest
    if (($script:installs -join ',') -ne 'parent.extension') {
        throw "Unexpected installs: $script:installs"
    }
} finally { Remove-Item $manifest }
''')
