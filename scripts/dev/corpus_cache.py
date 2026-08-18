"""Save the corpus's place grounding to the repository, or put it back.

    corpus_cache.py --save                     # sandbox 2 -> corpus/places.json
    corpus_cache.py --restore --database ...   # stored places -> a sandbox
    corpus_cache.py --sync --database ...      # a sandbox <-> the central dump
    corpus_cache.py                            # what is stored, and where

Saving merges rather than replaces, so running it from one lane never discards
what another lane warmed.

There are two durable copies. ``corpus/places.json`` is the reviewable one in
git, written only by ``--save``. ``tripplanner-cache`` is an emulator database
written by ``--sync`` on every stack start, promotion and discard; nothing reads
it at request time, so it can be updated as often as we like without touching a
tracked file.
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

from tripplanner.validation import lane_trips, place_cache, runner  # noqa: E402
from tripplanner.validation.emulator import (  # noqa: E402
    EmulatorUnreachableError,
    list_sandbox_databases,
)

DEFAULT_DATABASE = "tripplanner-sbx-2-auto-validation"


def _cache_databases() -> list[str]:
    """Every local database allowed to hold cache, primary and central included.

    ``list_sandbox_databases`` answers a deliberately narrower question, so the
    primary development database -- which is never discarded, and therefore only
    ever fills by hand -- would otherwise never be swept by --all.
    """
    return [
        place_cache.PRIMARY_DATABASE,
        place_cache.CENTRAL_DATABASE,
        *list_sandbox_databases(),
    ]


#: Neither of these is a lane, so neither has lane trips to snapshot.
_NOT_LANES = frozenset({place_cache.PRIMARY_DATABASE, place_cache.CENTRAL_DATABASE})


def _stored_and_central(stored: dict) -> dict:
    """The widest warm copy available: the git file, with the dump layered on top."""
    try:
        central = place_cache.collect(place_cache.CENTRAL_DATABASE)
    except (EmulatorUnreachableError, ValueError):
        return stored
    return place_cache.merge(stored, central)


def _sync(database: str, stored: dict) -> int:
    """Push a lane's places into the central dump, and warm the lane if it is empty.

    Runs on every stack start, promotion and discard, so it must be cheap when
    there is nothing to do: only entries the dump does not already hold, or holds
    an older copy of, are written.
    """
    central = place_cache.collect(place_cache.CENTRAL_DATABASE)
    if not central and stored:
        # An emulator that was wiped leaves the dump empty; the git file rebuilds it.
        place_cache.restore(place_cache.CENTRAL_DATABASE, stored)
        central = stored

    live = place_cache.collect(database)
    pushed = 0
    if live:
        outgoing = place_cache.delta(central, live)
        if outgoing:
            pushed = place_cache.restore(place_cache.CENTRAL_DATABASE, outgoing)
            central = place_cache.merge(central, outgoing)
    print(f"  {database} -> {place_cache.CENTRAL_DATABASE}: {pushed} new place(s)")

    if live or not central:
        return 0
    warmed = place_cache.restore(database, place_cache.merge(stored, central))
    print(f"  {place_cache.CENTRAL_DATABASE} -> {database}: warmed {warmed} place(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", action="store_true", help="database -> corpus/places.json")
    parser.add_argument("--restore", action="store_true", help="stored places -> database")
    parser.add_argument(
        "--sync",
        action="store_true",
        help=f"database -> {place_cache.CENTRAL_DATABASE}, and back when the database is empty",
    )
    parser.add_argument("--database", default="", help=f"defaults to {DEFAULT_DATABASE}")
    parser.add_argument("--all", action="store_true", help="with --save, read every sandbox")
    parser.add_argument(
        "--if-empty",
        action="store_true",
        help="with --restore, do nothing when the target already holds places",
    )
    args = parser.parse_args(argv)

    path = place_cache.cache_path(runner.corpus_root(REPO_ROOT))
    stored = place_cache.load(path)

    if args.save:
        try:
            databases = _cache_databases() if args.all else [
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
            # Lane snapshots are per-sandbox by definition; the primary checkout
            # is not a lane and its trips are the owner's own.
            trips = 0
            if database not in _NOT_LANES:
                try:
                    trips = lane_trips.save(runner.corpus_root(REPO_ROOT), database)
                except (EmulatorUnreachableError, ValueError, OSError) as error:
                    print(f"  could not save trips for {database}: {error}", file=sys.stderr)
            print(f"  read {database}: {len(found)} place(s), {trips} trip(s)")
            merged = place_cache.merge(merged, found)
        added = len(merged) - len(stored)
        place_cache.save(path, merged)
        print(f"Saved {len(merged)} place(s) to {path.name} ({added:+d}).")
        return 0

    if args.sync:
        database = args.database or DEFAULT_DATABASE
        try:
            return _sync(database, stored)
        except (EmulatorUnreachableError, ValueError) as error:
            print(f"Could not sync {database}: {error}", file=sys.stderr)
            return 2

    if args.restore:
        source = _stored_and_central(stored)
        if not source:
            print(f"Nothing stored in {path.name} yet; run --save first.", file=sys.stderr)
            return 2
        database = args.database or DEFAULT_DATABASE
        if args.if_empty:
            try:
                already = place_cache.collect(database)
            except (EmulatorUnreachableError, ValueError) as error:
                print(f"Could not read {database}: {error}", file=sys.stderr)
                return 2
            if already:
                print(f"{database} already holds {len(already)} place(s); leaving it alone.")
                return 0
        try:
            written = place_cache.restore(database, source)
        except (EmulatorUnreachableError, ValueError) as error:
            print(f"Could not restore: {error}", file=sys.stderr)
            return 2
        print(f"Restored {written} place(s) into {database}.")
        return 0

    print(f"{path}")
    print(f"  stored: {len(stored)} place(s)")
    try:
        for database in _cache_databases():
            live = place_cache.collect(database)
            missing = len(set(live) - set(stored))
            print(f"  {database}: {len(live)} cached, {missing} not yet saved")
    except EmulatorUnreachableError as error:
        print(f"  emulator unreachable: {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
