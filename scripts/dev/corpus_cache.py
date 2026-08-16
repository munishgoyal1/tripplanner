"""Save the corpus's place grounding to the repository, or put it back.

    corpus_cache.py --save                     # sandbox 2 -> corpus/places.json
    corpus_cache.py --restore --database ...   # corpus/places.json -> a sandbox
    corpus_cache.py                            # what is stored, and where

Saving merges rather than replaces, so running it from one lane never discards
what another lane warmed.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

# The cache tools talk to the emulator directly, so an inherited COSMOS_* pointing
# at a hosted account must not be able to influence them.
for _name in ("COSMOS_ENDPOINT", "COSMOS_KEY", "COSMOS_DATABASE", "COSMOS_EMULATOR"):
    os.environ.pop(_name, None)

from tripplanner.validation import place_cache, runner  # noqa: E402
from tripplanner.validation.emulator import (  # noqa: E402
    EmulatorUnreachableError,
    list_sandbox_databases,
)

DEFAULT_DATABASE = "tripplanner-sbx-2-auto-validation"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", action="store_true", help="database -> corpus/places.json")
    parser.add_argument("--restore", action="store_true", help="corpus/places.json -> database")
    parser.add_argument("--database", default="", help=f"defaults to {DEFAULT_DATABASE}")
    parser.add_argument("--all", action="store_true", help="with --save, read every sandbox")
    args = parser.parse_args(argv)

    path = place_cache.cache_path(runner.corpus_root(REPO_ROOT))
    stored = place_cache.load(path)

    if args.save:
        try:
            databases = list_sandbox_databases() if args.all else [
                args.database or DEFAULT_DATABASE
            ]
        except EmulatorUnreachableError as error:
            print(f"Emulator unreachable: {error}", file=sys.stderr)
            return 2
        merged = stored
        for database in databases:
            try:
                found = place_cache.collect(database)
            except (EmulatorUnreachableError, ValueError) as error:
                print(f"  skipped {database}: {error}", file=sys.stderr)
                continue
            print(f"  read {database}: {len(found)} place(s)")
            merged = place_cache.merge(merged, found)
        added = len(merged) - len(stored)
        place_cache.save(path, merged)
        print(f"Saved {len(merged)} place(s) to {path.name} ({added:+d}).")
        return 0

    if args.restore:
        if not stored:
            print(f"Nothing stored in {path.name} yet; run --save first.", file=sys.stderr)
            return 2
        database = args.database or DEFAULT_DATABASE
        try:
            written = place_cache.restore(database, stored)
        except (EmulatorUnreachableError, ValueError) as error:
            print(f"Could not restore: {error}", file=sys.stderr)
            return 2
        print(f"Restored {written} place(s) into {database}.")
        return 0

    print(f"{path}")
    print(f"  stored: {len(stored)} place(s)")
    try:
        for database in list_sandbox_databases():
            live = place_cache.collect(database)
            missing = len(set(live) - set(stored))
            print(f"  {database}: {len(live)} cached, {missing} not yet saved")
    except EmulatorUnreachableError as error:
        print(f"  emulator unreachable: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
