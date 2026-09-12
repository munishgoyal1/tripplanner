"""Bound disposable diagnostic files without touching accounting or trip data."""

import threading
import time

_lock = threading.Lock()
_last_pruned = {}


def schedule_prune(directory, pattern, *, max_bytes, max_age):
    with _lock:
        if time.monotonic() - _last_pruned.get(directory, float("-inf")) < 600:
            return
        _last_pruned[directory] = time.monotonic()

    def run():
        try:
            prune(directory, pattern, max_bytes=max_bytes, max_age=max_age)
        except OSError:
            pass

    threading.Thread(target=run, name="diagnostic-retention", daemon=True).start()


def prune(directory, pattern, *, max_bytes, max_age):
    now = time.time()
    files = []
    for path in directory.glob(pattern):
        if (path.is_symlink() or not path.is_file()
                or not path.resolve().is_relative_to(directory.resolve())):
            continue
        try:
            stat = path.stat()
            if now - stat.st_mtime > max_age:
                path.unlink(missing_ok=True)
            else:
                files.append((stat.st_mtime, stat.st_size, path))
        except FileNotFoundError:
            continue
    total = sum(size for _modified, size, _path in files)
    for _modified, size, path in sorted(files):
        if total <= max_bytes:
            break
        path.unlink(missing_ok=True)
        total -= size
