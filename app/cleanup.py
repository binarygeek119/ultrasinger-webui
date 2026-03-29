from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from app.runtime_settings import ResolvedPaths

log = logging.getLogger(__name__)


def cleanup_old_jobs(paths: ResolvedPaths, retention_hours: int, keep_history_log: bool = True) -> int:
    """
    Remove job folders older than retention_hours under jobs_root.
    Cleans stale files in uploads_dir and tmp bundles under config_data_dir.
    Keeps config_data_dir/history/history.log.
    Returns number of job directories removed.
    """
    jobs_root = paths.jobs_root
    if not jobs_root.is_dir():
        return 0

    cutoff = time.time() - retention_hours * 3600
    removed = 0
    for p in jobs_root.iterdir():
        if not p.is_dir() or not p.name.startswith("job_"):
            continue
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            try:
                shutil.rmtree(p, ignore_errors=False)
                removed += 1
                log.info("cleanup: removed %s", p)
            except OSError as e:
                log.warning("cleanup: failed to remove %s: %s", p, e)

    uploads = paths.uploads_dir
    if uploads.is_dir():
        for f in uploads.iterdir():
            if not f.is_file():
                continue
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink(missing_ok=True)
            except OSError:
                pass

    bundles = paths.config_data_dir / "tmp" / "bundles"
    if bundles.is_dir():
        for f in bundles.iterdir():
            if f.is_file() and f.suffix == ".zip":
                try:
                    if f.stat().st_mtime < cutoff:
                        f.unlink(missing_ok=True)
                except OSError:
                    pass

    _ = keep_history_log
    return removed
