from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.config import Settings

log = logging.getLogger(__name__)


def build_ultrasinger_command(
    settings: Settings,
    input_target: str,
    work_dir: Path,
    whisper_compute_type: str,
) -> list[str]:
    if not settings.ultrasinger_py or not settings.ultrasinger_py.is_file():
        raise FileNotFoundError(
            "UltraSinger script not configured. Set ULTRASINGER_PY to the path of UltraSinger.py."
        )
    work_dir.mkdir(parents=True, exist_ok=True)
    cmd: list[str] = [
        settings.python_exe,
        str(settings.ultrasinger_py),
        "-i",
        input_target,
        "-o",
        str(work_dir),
        "--whisper_compute_type",
        whisper_compute_type,
    ]
    if settings.cookiefile and settings.cookiefile.is_file():
        cmd.extend(["--cookiefile", str(settings.cookiefile)])
    return cmd


def run_ultrasinger(
    settings: Settings,
    input_target: str,
    work_dir: Path,
    whisper_compute_type: str,
    log_path: Path,
) -> tuple[int, str]:
    cmd = build_ultrasinger_command(settings, input_target, work_dir, whisper_compute_type, log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as lf:
        lf.write(f"$ {' '.join(cmd)}\n\n")
        lf.flush()
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(settings.ultrasinger_py.parent),
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            lf.write(line)
            lf.flush()
        code = proc.wait()
    return code, log_path.read_text(encoding="utf-8", errors="replace")[-8000:]
