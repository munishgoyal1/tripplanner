"""The sandbox database helper, tested without an emulator."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).parents[1]
SANDBOX_SCRIPT = ROOT / "scripts" / "dev" / "sandbox.ps1"
SEED_SCRIPT = ROOT / "scripts" / "dev" / "sandbox_seed.py"


def _load_seed() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sandbox_seed", SEED_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rename_block(source: str) -> str:
    start = source.index('if ($PSCmdlet.ParameterSetName -eq "Rename")')
    end = source.index('if ($PSCmdlet.ParameterSetName -eq "Merge")', start)
    return source[start:end]


def test_rename_carries_the_sandbox_data_to_the_new_database_name() -> None:
    """A rename changes the name and nothing else, data included."""
    block = _rename_block(SANDBOX_SCRIPT.read_text(encoding="utf-8"))

    assert "sandbox_seed.py" in block
    assert "move --source $oldDatabase --target $newDatabase" in block.replace(
        "$seedScript move", "move"
    )
    assert "seeds $newDatabase fresh" not in block


def test_move_refuses_anything_that_is_not_a_sandbox_database() -> None:
    seed = _load_seed()
    args = seed.build_parser().parse_args(
        ["move", "--source", "tripplanner-prod", "--target", "tripplanner-sbx-1-x"]
    )

    with pytest.raises(SystemExit) as failure:
        args.func(args)

    assert failure.value.code == 2


def test_move_is_a_no_op_when_the_name_did_not_change() -> None:
    seed = _load_seed()
    args = seed.build_parser().parse_args(
        ["move", "--source", "tripplanner-sbx-1-x", "--target", "tripplanner-sbx-1-x"]
    )

    assert args.func(args) == 0
