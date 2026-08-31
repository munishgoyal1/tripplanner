from __future__ import annotations

from pathlib import Path


def test_owner_quality_launchers_are_consolidated_in_one_folder() -> None:
    root = Path(__file__).parents[1]

    for platform, suffix in (("mac", ".command"), ("win", ".cmd")):
        user_root = root / "scripts" / platform / "user"
        quality = user_root / "quality"

        assert not (user_root / "debug").exists()
        for name in (
            "Capture-Screens",
            "Clear-TripRecorder",
            "Maintain-TripRecorder",
            "Restore-TripRecorder",
            "Show-TripRecorder",
        ):
            assert (quality / f"{name}{suffix}").is_file()


def test_primary_master_launchers_are_named_and_wired_consistently() -> None:
    root = Path(__file__).parents[1]
    run_script = (root / "scripts" / "dev" / "run-latest-master.ps1").read_text(encoding="utf-8")
    mac_launcher = (
        root / "scripts" / "mac" / "user" / "run" / "Run-Latest-Master.command"
    ).read_text(encoding="utf-8")
    windows_launcher = (
        root / "scripts" / "win" / "user" / "run" / "Run-Latest-Master.cmd"
    ).read_text(encoding="utf-8")

    assert 'branch -ne "master"' in run_script
    assert "fetch -q origin master" in run_script
    assert "merge --ff-only origin/master" in run_script
    assert "run-latest-master.ps1" in mac_launcher
    assert "run-latest-master.ps1" in windows_launcher
    assert not (root / "scripts" / "dev" / "run-latest.ps1").exists()


def test_google_places_control_has_cross_platform_owner_launchers() -> None:
    root = Path(__file__).parents[1]
    script_name = "set-google-places-access.ps1"
    mac_launcher = (
        root / "scripts" / "mac" / "user" / "google" / "Google-Places-Control.command"
    ).read_text(encoding="utf-8")
    windows_launcher = (
        root / "scripts" / "win" / "user" / "google" / "Google-Places-Control.cmd"
    ).read_text(encoding="utf-8")

    assert script_name in mac_launcher
    assert script_name in windows_launcher


def test_google_maps_control_has_cross_platform_owner_launchers() -> None:
    root = Path(__file__).parents[1]
    script_name = "set-google-maps-access.ps1"
    mac_launcher = (
        root / "scripts" / "mac" / "user" / "google" / "Google-Maps-Control.command"
    ).read_text(encoding="utf-8")
    windows_launcher = (
        root / "scripts" / "win" / "user" / "google" / "Google-Maps-Control.cmd"
    ).read_text(encoding="utf-8")

    assert script_name in mac_launcher
    assert script_name in windows_launcher


def test_common_runtime_config_has_safe_cross_platform_owner_launchers() -> None:
    root = Path(__file__).parents[1]
    orchestrator = (root / "scripts" / "dev" / "apply-runtime-config.ps1").read_text(
        encoding="utf-8"
    )
    google_handler = (
        root / "infra" / "azure" / "set-google-runtime-access.ps1"
    ).read_text(encoding="utf-8")
    launchers = (
        root / "scripts" / "mac" / "user" / "runtime" / "Apply-Runtime-Config.command",
        root / "scripts" / "win" / "user" / "runtime" / "Apply-Runtime-Config.cmd",
    )

    assert 'ValidateSet("status", "apply", "help", "?")' in orchestrator
    assert 'ValidateSet("all", "canary", "prod")' in orchestrator
    assert "APPROVE_RUNTIME_CONFIG" in orchestrator
    assert "set-google-runtime-access.ps1" in orchestrator
    assert "Show-RuntimeConfigHelp" in orchestrator
    assert "if ($Action -in @(\"help\", \"?\"))" in orchestrator
    assert "APPROVE_GOOGLE_MAPS_SPEND" in orchestrator
    assert "APPROVE_GOOGLE_PLACES_SPEND" in orchestrator

    assert 'ValidateSet("status", "apply", "enable", "disable", "on", "off", "help", "?")' in google_handler
    assert "Show-GoogleRuntimeHelp" in google_handler
    assert "munishgoyal1@gmail.com" in google_handler
    assert "Visual Studio Enterprise Subscription" in google_handler
    assert "az containerapp update" in google_handler
    assert "--image" not in google_handler
    assert '"ENABLE_GOOGLE_MAPS=$desiredMaps"' in google_handler
    assert '"ENABLE_GOOGLE_PLACES=$desiredPlaces"' in google_handler
    assert "$after.image -ne $before.image" in google_handler
    assert "$after.latest -ne $after.ready" in google_handler
    assert "$_.latestRevision -eq $true" in google_handler
    assert "if (-not $runtimeInSync)" in google_handler
    assert "Runtime flags already match; no revision created." in google_handler
    update_index = google_handler.index("az containerapp update")
    assert google_handler.index("if ($mapsEnabled) { & $mapsControl apply", 0, update_index) >= 0
    assert google_handler.index("if ($placesEnabled) { & $placesControl apply", 0, update_index) >= 0
    assert google_handler.index("if (-not $mapsEnabled) { & $mapsControl apply", update_index) >= 0
    assert google_handler.index("if (-not $placesEnabled) { & $placesControl apply", update_index) >= 0
    for launcher_path in launchers:
        launcher = launcher_path.read_text(encoding="utf-8")
        assert "apply-runtime-config.ps1" in launcher
        assert "show-launcher-help.ps1" in launcher
        assert "apply-runtime-config" in launcher
        assert '"?"' in launcher
        assert '"help"' in launcher


def test_azure_services_control_has_cross_platform_owner_launchers() -> None:
    root = Path(__file__).parents[1]
    script_name = "set-azure-services-access.ps1"
    mac_launcher = (
        root / "scripts" / "mac" / "user" / "azure" / "Azure-Services-Control.command"
    ).read_text(encoding="utf-8")
    windows_launcher = (
        root / "scripts" / "win" / "user" / "azure" / "Azure-Services-Control.cmd"
    ).read_text(encoding="utf-8")

    assert script_name in mac_launcher
    assert script_name in windows_launcher


def test_unified_emergency_control_has_safe_cross_platform_owner_launchers() -> None:
    root = Path(__file__).parents[1]
    script = (root / "scripts" / "dev" / "emergency-control.ps1").read_text(
        encoding="utf-8"
    )
    mac_launcher = (
        root / "scripts" / "mac" / "user" / "emergency" / "Emergency-Control.command"
    ).read_text(encoding="utf-8")
    windows_launcher = (
        root / "scripts" / "win" / "user" / "emergency" / "Emergency-Control.cmd"
    ).read_text(encoding="utf-8")

    assert '[string]$Action = "status"' in script
    assert 'ValidateSet("all", "google", "azure", "local", "canary", "prod")' in script
    assert '$providerScope = if ($Target -in' in script
    assert '$environment = if ($Target -in' in script
    assert "set-azure-services-access.ps1" in script
    assert "set-google-maps-access.ps1" in script
    assert "set-google-places-access.ps1" in script
    assert "APPROVE_AZURE_DISABLE" not in script
    assert "APPROVE_AZURE_SPEND" in script
    assert "APPROVE_GOOGLE_MAPS_SPEND" in script
    assert "APPROVE_GOOGLE_PLACES_SPEND" in script
    assert script.index('Name = "Azure services"') < script.index('Name = "Google Maps"')
    for launcher in (mac_launcher, windows_launcher):
        assert "emergency-control.ps1" in launcher
        assert "show-launcher-help.ps1" in launcher
        assert "emergency-control" in launcher


def test_emergency_bringdown_has_safe_cross_platform_owner_launchers() -> None:
    root = Path(__file__).parents[1]
    script = (root / "scripts" / "dev" / "emergency-bringdown.ps1").read_text(
        encoding="utf-8"
    )
    azure_control = (
        root / "infra" / "azure" / "set-azure-services-access.ps1"
    ).read_text(encoding="utf-8")
    launchers = (
        root / "scripts" / "mac" / "user" / "emergency" / "Emergency-Bringdown.command",
        root / "scripts" / "win" / "user" / "emergency" / "Emergency-Bringdown.cmd",
    )

    assert '[string]$Action = "status"' in script
    assert 'ValidateSet("all", "canary", "prod")' in script
    assert "APPROVE_AZURE_SPEND" in script
    assert "-ServingOnly" in script
    assert "APPROVE_AZURE_DISABLE" not in script
    assert "[switch]$ServingOnly" in azure_control
    assert '(-not $ServingOnly -or $_.name -in @("canary", "prod"))' in azure_control
    for launcher_path in launchers:
        launcher = launcher_path.read_text(encoding="utf-8")
        assert "emergency-bringdown.ps1" in launcher
        assert "show-launcher-help.ps1" in launcher
        assert "emergency-bringdown" in launcher


def test_sync_launcher_defaults_to_all_and_accepts_one_sandbox() -> None:
    root = Path(__file__).parents[1]
    sync_script = (root / "scripts" / "dev" / "sync-sbxs-from-master.ps1").read_text(
        encoding="utf-8"
    )
    mac_launcher = (
        root / "scripts" / "mac" / "user" / "sync" / "Sync-Sbxs-FromMaster.command"
    ).read_text(encoding="utf-8")
    windows_launcher = (
        root / "scripts" / "win" / "user" / "sync" / "Sync-Sbxs-FromMaster.cmd"
    ).read_text(encoding="utf-8")

    assert '[string]$Sandbox = ""' in sync_script
    assert "fetch -q origin master" in sync_script
    assert "merge --ff-only origin/master" in sync_script
    assert "if ($Sandbox)" in sync_script
    assert "$targets = $registered" in sync_script
    assert "sync-sbxs-from-master.ps1" in mac_launcher
    assert "sync-sbxs-from-master.ps1" in windows_launcher
    assert not (root / "scripts" / "dev" / "sync-latest.ps1").exists()
    assert not (root / "scripts" / "dev" / "all-worktrees-sync.ps1").exists()


def test_categorized_owner_launchers_have_cross_platform_help() -> None:
    root = Path(__file__).parents[1]
    groups = {
        "sync": (
            "Full-2Way-Sync",
            "Resolve-All-Recorded-Conflicts",
            "Sync-Across-MasterSbx",
            "Sync-Sbxs-FromMaster",
        ),
        "run": ("Run-Latest-Master", "Start-Dev-Spa"),
        "azure": ("Azure-Services-Control",),
        "google": ("Google-Maps-Control", "Google-Places-Control"),
        "runtime": ("Apply-Runtime-Config",),
    }

    for platform, suffix in (("mac", ".command"), ("win", ".cmd")):
        user_root = root / "scripts" / platform / "user"
        for group, launchers in groups.items():
            for launcher in launchers:
                path = user_root / group / f"{launcher}{suffix}"
                content = path.read_text(encoding="utf-8")
                assert "show-launcher-help.ps1" in content
                assert '"?"' in content
                assert '"help"' in content
                assert not (user_root / f"{launcher}{suffix}").exists()


def test_sync_recovers_pending_conflicts_without_manual_steps() -> None:
    root = Path(__file__).parents[1]
    sync_script = (root / "scripts" / "dev" / "sync-sbxs-from-master.ps1").read_text(
        encoding="utf-8"
    )

    assert "resolve-sandbox-conflicts.ps1" in sync_script
    # Retry on git state, not on the error text the launcher rewraps.
    assert "--diff-filter=U" in sync_script
    assert "function Test-SandboxConflictPending" in sync_script
    assert "conflicts still need manual resolution" in sync_script
    # One retry only, and only after the conflict is genuinely gone.
    assert sync_script.count("& $resolverScript") == 1


def test_sandbox_scripts_share_one_reference_resolver() -> None:
    root = Path(__file__).parents[1]
    lib = (root / "scripts" / "dev" / "lib" / "sandbox-registry.ps1").read_text(encoding="utf-8")
    resolver = (root / "scripts" / "dev" / "resolve-sandbox-conflicts.ps1").read_text(
        encoding="utf-8"
    )
    sandbox = (root / "scripts" / "dev" / "sandbox.ps1").read_text(encoding="utf-8")

    assert "function Get-PrimaryRepositoryRoot" in lib
    assert "rev-parse --path-format=absolute --git-common-dir" in lib
    assert "function Select-SandboxEntry" in lib
    assert '$Reference -match "^\\d+$"' in lib
    for script in (resolver, sandbox):
        assert "lib/sandbox-registry.ps1" in script
        assert "Select-SandboxEntry" in script
    assert "Get-PrimaryRepositoryRoot -RepositoryRoot $checkoutRoot" in resolver
    # The duplicated registry lookup the resolver used to carry is gone.
    assert "([int]$_.slot + 1)" not in resolver
    assert "was not uniquely found" not in resolver


def test_discard_publishes_only_retained_corpus_files() -> None:
    root = Path(__file__).parents[1]
    sandbox = (root / "scripts" / "dev" / "sandbox.ps1").read_text(encoding="utf-8")

    assert "function Publish-RetainedSandboxCorpus" in sandbox
    assert '"corpus/lane-trips/$($Entry.database).json"' in sandbox
    assert '"corpus/places.json"' in sandbox
    assert "git -C $scriptRepoRoot add -- @paths" in sandbox
    assert 'commit -m "Preserve discarded $($Entry.slug) corpus" -- @paths' in sandbox
    assert "push origin $Base" in sandbox
    assert "Publish-RetainedSandboxCorpus -Entry $entry -Base $BaseBranch" in sandbox


def test_corpus_build_publishes_all_generated_artifacts() -> None:
    root = Path(__file__).parents[1]
    builder = (root / "scripts" / "dev" / "build-corpus.ps1").read_text(encoding="utf-8")

    assert "function Publish-GeneratedCorpus" in builder
    for path in (
        '"corpus/manifest.json"',
        '"corpus/spend-ledger.json"',
        '"corpus/places.json"',
        '"corpus/trips"',
    ):
        assert path in builder
    assert "git -C $repoRoot commit -m \"Preserve generated corpus\" -- @paths" in builder
    assert 'git -C $repoRoot push origin "HEAD:$branch"' in builder
    assert "if (-not $dryRun)" in builder
    assert "Publish-GeneratedCorpus" in builder


def test_dev_stack_overrides_inherited_google_keys_with_local_env() -> None:
    root = Path(__file__).parents[1]
    launcher = (root / "scripts" / "dev" / "dev-spa.ps1").read_text(encoding="utf-8")

    assert 'foreach ($name in @("GOOGLE_MAPS_BROWSER_KEY", "GOOGLE_PLACES_API_KEY"))' in launcher
    assert "Get-DotEnvValue -Name $name" in launcher
    assert "SetEnvironmentVariable($name, $localValue, \"Process\")" in launcher


def test_sandbox_runs_and_audits_refresh_primary_environment() -> None:
    root = Path(__file__).parents[1]
    sandbox = (root / "scripts" / "dev" / "sandbox.ps1").read_text(encoding="utf-8")
    audit = (root / "scripts" / "dev" / "trip-audit.ps1").read_text(encoding="utf-8")

    assert "function Copy-PrimaryEnvironment" in sandbox
    assert sandbox.count("Copy-PrimaryEnvironment -WorktreeRoot") == 2
    assert 'Join-Path $primaryRoot ".env"' in sandbox
    assert "rev-parse --git-common-dir" in audit
    assert 'Join-Path $primaryRoot ".env"' in audit
    assert 'Join-Path $repoRoot ".env"' in audit
    assert "Copy-Item -LiteralPath $sourceEnv" in audit


def _merge_block(sandbox_script: str) -> str:
    start = sandbox_script.index('if ($PSCmdlet.ParameterSetName -eq "Merge")')
    end = sandbox_script.index('if ($PSCmdlet.ParameterSetName -eq "Promote")', start)
    return sandbox_script[start:end]


def _code_lines(block: str) -> str:
    return "\n".join(line for line in block.splitlines() if not line.strip().startswith("#"))


def test_merge_lands_sandbox_work_without_discarding_it() -> None:
    root = Path(__file__).parents[1]
    sandbox_script = (root / "scripts" / "dev" / "sandbox.ps1").read_text(encoding="utf-8")
    block = _merge_block(sandbox_script)
    code = _code_lines(block)

    assert '[Parameter(Mandatory = $true, ParameterSetName = "Merge")]' in sandbox_script
    # Same gates as promotion.
    assert "Invoke-SandboxValidation" in code
    assert "gh pr merge $prNumber --merge" in code
    # The sandbox survives: no discard, no promotion record, no lab state change.
    assert "-Discard" not in code
    assert "Save-SandboxPromotion" not in code
    assert "Write-SandboxLabVersion" not in code
    assert "--delete-branch" not in code
    # The base branch must provably contain the merged commit.
    assert "merge-base --is-ancestor $mergedHead" in code
    # And the sandbox is brought back onto the new base.
    assert code.count("Invoke-SandboxUpdateWithRecovery") == 2


def test_merge_recovers_conflicts_and_refreshes_the_base() -> None:
    root = Path(__file__).parents[1]
    sandbox_script = (root / "scripts" / "dev" / "sandbox.ps1").read_text(encoding="utf-8")
    block = _merge_block(sandbox_script)
    code = _code_lines(block)

    assert "function Invoke-SandboxUpdateWithRecovery" in sandbox_script
    # Merge refreshes the base before syncing, and again after the PR lands.
    assert "Sync-PrimaryCheckout -Base $BaseBranch -RequireExact" in code
    assert "fetch latest $BaseBranch" in code
    assert code.count("Invoke-SandboxUpdateWithRecovery") == 2
    # Raw updates that would bypass recovery are gone from the merge path.
    assert "-Update $slug" not in code

    helper_start = sandbox_script.index("function Invoke-SandboxUpdateWithRecovery")
    helper = sandbox_script[helper_start : sandbox_script.index("\n}", helper_start)]
    assert "resolve-sandbox-conflicts.ps1" in helper
    # Recover only when a conflict is genuinely pending.
    assert "Get-SandboxUnmergedFiles" in helper
    assert helper.count("resolve-sandbox-conflicts.ps1") == 1


def test_merge_launchers_exist_for_both_platforms() -> None:
    root = Path(__file__).parents[1]
    mac_launcher = root / "scripts" / "mac" / "user" / "sandbox" / "Merge-Sandbox.command"
    windows_launcher = root / "scripts" / "win" / "user" / "sandbox" / "Merge-Sandbox.cmd"

    assert "sandbox.ps1" in mac_launcher.read_text(encoding="utf-8")
    assert "-Merge" in mac_launcher.read_text(encoding="utf-8")
    assert "-Merge" in windows_launcher.read_text(encoding="utf-8")


def _rename_block(sandbox_script: str) -> str:
    start = sandbox_script.index('if ($PSCmdlet.ParameterSetName -eq "Rename")')
    end = sandbox_script.index('if ($PSCmdlet.ParameterSetName -eq "Merge")', start)
    return sandbox_script[start:end]


def test_rename_keeps_the_number_and_renames_every_derived_name() -> None:
    root = Path(__file__).parents[1]
    sandbox_script = (root / "scripts" / "dev" / "sandbox.ps1").read_text(encoding="utf-8")
    block = _rename_block(sandbox_script)

    assert '[Parameter(Mandatory = $true, ParameterSetName = "Rename")]' in sandbox_script
    # The number comes from the sandbox, so a name given without one keeps it.
    assert '$newSlug = "$number-$newShortName"' in block
    # A number may be repeated but never reassigned: it owns the ports.
    assert 'if ($NewName -match "^(\\d+)-")' in block
    assert "Renaming cannot move it to" in block
    # Branch, worktree, and database follow the slug.
    assert '$newBranch = "sandbox/$newSlug"' in block
    assert '"sbx-$newSlug"' in block
    assert '$newDatabase = "tripplanner-sbx-$newSlug"' in block
    assert '"worktree", "move"' in block
    assert '"branch", "-m"' in block
    assert "Save-Registry" in block


def test_rename_refuses_unsafe_states_and_publishes_before_deleting() -> None:
    root = Path(__file__).parents[1]
    sandbox_script = (root / "scripts" / "dev" / "sandbox.ps1").read_text(encoding="utf-8")
    block = _rename_block(sandbox_script)

    assert "already covers" in block
    assert "Test-SandboxEndpoint" in block
    assert "is serving. Stop it first" in block
    assert "Get-SandboxUnmergedFiles" in block
    # The new branch is published before the old one is removed.
    assert block.index("push -u origin") < block.index("push origin --delete")


def test_rename_launchers_exist_for_both_platforms() -> None:
    root = Path(__file__).parents[1]
    mac_launcher = (
        root / "scripts" / "mac" / "user" / "sandbox" / "Rename-Sandbox.command"
    ).read_text(encoding="utf-8")
    windows_launcher = (
        root / "scripts" / "win" / "user" / "sandbox" / "Rename-Sandbox.cmd"
    ).read_text(
        encoding="utf-8"
    )

    assert "sandbox.ps1" in mac_launcher
    assert "-Rename" in mac_launcher
    assert "-Rename" in windows_launcher


def test_github_cli_is_resolved_instead_of_trusting_path() -> None:
    root = Path(__file__).parents[1]
    lib = (root / "scripts" / "dev" / "lib" / "gh-cli.ps1").read_text(encoding="utf-8")
    sandbox_script = (root / "scripts" / "dev" / "sandbox.ps1").read_text(encoding="utf-8")

    assert "function Resolve-GhCli" in lib
    assert "/opt/homebrew/bin/gh" in lib
    assert "lib/gh-cli.ps1" in sandbox_script
    # A Finder double-click has no Homebrew bin on PATH, so no bare-name lookup
    # may remain in the merge or promote paths.
    assert "& gh " not in sandbox_script
    assert "Get-Command gh " not in sandbox_script


def test_sync_across_is_gated_by_a_typed_approval() -> None:
    root = Path(__file__).parents[1]
    script = (root / "scripts" / "dev" / "sync-across-master-sbx.ps1").read_text(encoding="utf-8")

    assert '$approvalPhrase = "APPROVE_SANDBOX_TO_MASTER"' in script
    assert "Read-Host" in script
    assert "if ($approval -ne $approvalPhrase)" in script

    # Nothing may merge before the gate is passed.
    approval = script.index("$approval = Read-Host")
    merge_call = script.index("& $sandboxScript -Merge")
    assert approval < merge_call
    # The owner sees the exact commits before being asked to approve.
    assert script.index("commit(s) to merge") < approval


def test_sync_across_refuses_half_baked_sandboxes() -> None:
    root = Path(__file__).parents[1]
    script = (root / "scripts" / "dev" / "sync-across-master-sbx.ps1").read_text(encoding="utf-8")

    assert "has uncommitted changes" in script
    assert "has unresolved conflicts" in script
    assert "needs every sandbox to be committed and conflict-free" in script
    # Preflight rejects before the plan is offered for approval.
    preflight = script.index("needs every sandbox to be committed")
    assert preflight < script.index("$approval = Read-Host")


def test_sync_across_reuses_merge_gates_and_refreshes_sandboxes() -> None:
    root = Path(__file__).parents[1]
    script = (root / "scripts" / "dev" / "sync-across-master-sbx.ps1").read_text(encoding="utf-8")

    # Sandbox work reaches master only through the gated -Merge verb.
    assert "& $sandboxScript -Merge" in script
    assert "-SkipValidation" not in script
    # Every sandbox ends on the resulting base, and that is verified.
    assert "sync-sbxs-from-master.ps1" in script
    assert "merge-base --is-ancestor $baseHead HEAD" in script


def test_sync_across_launchers_exist_for_both_platforms() -> None:
    root = Path(__file__).parents[1]
    mac_launcher = (
        root / "scripts" / "mac" / "user" / "sync" / "Sync-Across-MasterSbx.command"
    ).read_text(encoding="utf-8")
    windows_launcher = (
        root / "scripts" / "win" / "user" / "sync" / "Sync-Across-MasterSbx.cmd"
    ).read_text(encoding="utf-8")

    assert "sync-across-master-sbx.ps1" in mac_launcher
    assert "sync-across-master-sbx.ps1" in windows_launcher


def test_both_sync_commands_default_to_all_and_accept_one_sandbox() -> None:
    root = Path(__file__).parents[1]
    one_way = (root / "scripts" / "dev" / "sync-sbxs-from-master.ps1").read_text(encoding="utf-8")
    two_way = (root / "scripts" / "dev" / "sync-across-master-sbx.ps1").read_text(encoding="utf-8")

    for script in (one_way, two_way):
        assert '[string]$Sandbox = ""' in script
    assert "if ($Sandbox)" in one_way
    # The two-way script also accepts an explicit "all" value alongside omission.
    assert '-not $Sandbox -or $Sandbox.Trim().ToLowerInvariant() -eq "all"' in two_way
    # The two-way run narrows only what it merges; the closing refresh and the
    # ancestry check still cover every registered sandbox.
    assert "Select-SandboxEntry -Entries $registered -Reference $Sandbox" in two_way
    assert "foreach ($entry in $targets)" in two_way
    assert "foreach ($entry in $registered)" in two_way
    assert not (root / "scripts" / "dev" / "sync-latest-from-remote-master.ps1").exists()
    assert not (root / "scripts" / "dev" / "sync-two-way.ps1").exists()


def test_full_sync_keeps_active_worktrees_visible() -> None:
    root = Path(__file__).parents[1]
    full_sync = (root / "scripts" / "dev" / "full-2way-sync.ps1").read_text(encoding="utf-8")
    sandbox = (root / "scripts" / "dev" / "sandbox.ps1").read_text(encoding="utf-8")
    update = sandbox[
        sandbox.index('if ($PSCmdlet.ParameterSetName -eq "Update")') : sandbox.index(
            'if ($PSCmdlet.ParameterSetName -eq "Rename")'
        )
    ]

    assert "Push-LaneStash" not in full_sync
    assert "stash push" not in full_sync
    assert "publication deferred" in full_sync
    assert "-AllowDirtyPrimary" in full_sync
    assert "local work in progress overlaps the new origin/$BaseBranch" in full_sync
    assert "Merge-IntoVisibleWorktree" in update
    assert "stash" not in update.lower()
    assert "merge-tree --write-tree --quiet" in sandbox
    assert "SANDBOX_WIP_OVERLAP" in sandbox
    assert "its worktree was left untouched" in sandbox


def test_full_sync_defaults_to_all_local_branches_with_sbx_compatibility_scope() -> None:
    root = Path(__file__).parents[1]
    full_sync = (root / "scripts" / "dev" / "full-2way-sync.ps1").read_text(encoding="utf-8")

    assert '[string]$Scope = "all"' in full_sync
    assert '$Scope -eq "sbx"' in full_sync
    assert 'worktree", "list", "--porcelain"' in full_sync
    assert '"refs/heads"' in full_sync
    assert "Get-SandboxRegistry" in full_sync


def test_full_sync_auto_resolves_sandbox_multiagent_and_standalone_conflicts() -> None:
    root = Path(__file__).parents[1]
    full_sync = (root / "scripts" / "dev" / "full-2way-sync.ps1").read_text(encoding="utf-8")
    resolver = (root / "scripts" / "dev" / "resolve-sandbox-conflicts.ps1").read_text(
        encoding="utf-8"
    )

    assert 'ParameterSetName = "Worktree"' in resolver
    assert "[string]$WorkingDirectory" in resolver
    assert "& git -C $worktree rerere" in resolver
    assert resolver.count("exit 0") == 2
    assert "-WorkingDirectory $workingDirectory" in full_sync
    assert "-Kind $entry.kind" in full_sync
    assert "function Test-MergePending" in full_sync
    assert "Test-MergePending -WorkingDirectory $WorkingDirectory" in full_sync
    assert "function Update-PrimaryCheckout" in full_sync
    assert '"Fast-forward primary checkout to origin/$BaseBranch"' in full_sync
    assert full_sync.count('& git -C $primaryRoot merge --ff-only "origin/$BaseBranch"') == 1
    assert "merge --abort" in full_sync
    should_process = full_sync.index('"Merge origin/$BaseBranch into branch lane"')
    branch_merge = full_sync.index('merge --no-edit "origin/$BaseBranch"')
    assert should_process < branch_merge
    assert full_sync.index("& $resolverScript -WorkingDirectory") < full_sync.index(
        "& git -C $workingDirectory merge --abort"
    )


def test_owner_can_resolve_recorded_conflicts_across_all_worktrees() -> None:
    root = Path(__file__).parents[1]
    resolver = (
        root / "scripts" / "dev" / "resolve-all-recorded-conflicts.ps1"
    ).read_text(encoding="utf-8")
    mac_launcher = (
        root / "scripts" / "mac" / "user" / "sync" / "Resolve-All-Recorded-Conflicts.command"
    ).read_text(encoding="utf-8")
    windows_launcher = (
        root / "scripts" / "win" / "user" / "sync" / "Resolve-All-Recorded-Conflicts.cmd"
    ).read_text(encoding="utf-8")

    assert "worktree list --porcelain" in resolver
    assert "Get-SandboxRegistry" in resolver
    assert "Test-PendingMerge" in resolver
    assert "--diff-filter=U" in resolver
    assert "MERGE_HEAD" in resolver
    assert "resolve-sandbox-conflicts.ps1" in resolver
    assert "-WorkingDirectory $path" in resolver
    assert "-Sandbox $sandboxByWorktree[$path].slug" in resolver
    assert "pending-conflict-" in resolver
    assert "foreach ($worktree in @(Get-AttachedWorktrees))" in resolver
    assert "Still requires manual resolution" in resolver
    assert "merge --abort" not in resolver
    assert "git push" not in resolver
    assert "git fetch" not in resolver
    assert "resolve-all-recorded-conflicts.ps1" in mac_launcher
    assert "resolve-all-recorded-conflicts.ps1" in windows_launcher
