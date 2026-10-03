import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
PWSH = shutil.which("pwsh")
pytestmark = pytest.mark.skipif(
    not PWSH, reason="PowerShell is required for migration behavior tests"
)
COMMON = ROOT / "infra/migration/common.ps1"


def run_ps(code):
    return subprocess.run([PWSH, "-NoProfile", "-Command", code], capture_output=True, text=True)


def quote(path):
    return "'" + str(path).replace("'", "''") + "'"


@pytest.mark.parametrize(
    "config",
    [
        "@{}",
        "@{preserveSource=$true;deleteSourceResourceGroupsOnRetire=$true}",
        "@{preserveSource=$false;deleteSourceResourceGroupsOnRetire=$false}",
    ],
)
def test_retirement_refuses_missing_or_conflicting_authorization(config):
    result = run_ps(f". {quote(COMMON)}; Assert-SourceRetirementAllowed ([pscustomobject]{config})")
    assert result.returncode != 0
    assert "Source preservation" in result.stderr


def test_manifest_change_rejects_stale_resume(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"target":"first"}')
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    command = f". {quote(COMMON)}; Assert-MigrationManifest {quote(config)} {quote(evidence)}"
    assert run_ps(command).returncode == 0
    config.write_text('{"target":"second"}')
    result = run_ps(command)
    assert result.returncode != 0
    assert "configuration changed" in result.stderr


def test_preserve_guard_runs_before_azure_access(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"azure":{"preserveSource":true,"cosmosDatabases":["tripplanner-prod"]}}')
    script = ROOT / "infra/migration/azure/Invoke-AzureMigration.ps1"
    result = run_ps(
        f"& {quote(script)} -ConfigPath {quote(config)} -Phase retire "
        f"-RunId test -EvidenceDirectory {quote(tmp_path)}"
    )
    assert result.returncode != 0
    assert "Source preservation" in result.stderr
    assert "login" not in result.stderr


def test_one_click_entrypoint_parses():
    script = ROOT / "infra/migration/Invoke-OneClickMigration.ps1"
    result = run_ps(
        "$tokens=$null; $parseErrors=$null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile({quote(script)}, "
        "[ref]$tokens, [ref]$parseErrors) | Out-Null; "
        "if ($parseErrors.Count) { throw ($parseErrors | Out-String) }"
    )
    assert result.returncode == 0, result.stderr


def test_command_selects_source_cache_and_restores_callers_cache():
    result = run_ps(f"""
. {quote(COMMON)}
$env:AZURE_CONFIG_DIR='original-cache'
$env:TRIPPLANNER_MIGRATION_SOURCE_SUBSCRIPTION='source-sub'
$env:TRIPPLANNER_MIGRATION_SOURCE_AZURE_CONFIG_DIR='source-cache'
$env:TRIPPLANNER_MIGRATION_TARGET_SUBSCRIPTION='target-sub'
$env:TRIPPLANNER_MIGRATION_TARGET_AZURE_CONFIG_DIR='target-cache'
function az {{ $global:LASTEXITCODE=0; Write-Output $env:AZURE_CONFIG_DIR }}
$arguments=@('resource','list','--subscription','source-sub')
$selected=Invoke-CheckedCommand az $arguments test -Capture
if ($selected -ne 'source-cache') {{ throw "Wrong source cache: $selected" }}
if ($env:AZURE_CONFIG_DIR -ne 'original-cache') {{ throw 'Caller cache leaked' }}
$url='https://management.azure.com/subscriptions/target-sub/resourceGroups/test'
$selected=Invoke-CheckedCommand az @('rest','--url',$url) test -Capture
if ($selected -ne 'target-cache') {{ throw "Wrong target cache: $selected" }}
""")
    assert result.returncode == 0, result.stderr
