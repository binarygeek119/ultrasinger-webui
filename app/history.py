from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path


_lock = threading.Lock()


def append_history_line(data_dir: Path, line: str) -> None:
    hist_dir = data_dir / "history"
    hist_dir.mkdir(parents=True, exist_ok=True)
    log_path = hist_dir / "history.log"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with _lock:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"{ts} | {line}\n")
