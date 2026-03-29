from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings


@dataclass(frozen=True)
class ResolvedPaths:
    """config_data_dir: app data root (config, history, tmp). jobs_root: parent of job_* folders."""

    config_data_dir: Path
    jobs_root: Path
    uploads_dir: Path


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def webui_config_path(data_dir: Path) -> Path:
    return data_dir / "webui_config.json"


def load_webui_config(data_dir: Path) -> dict[str, Any]:
    p = webui_config_path(data_dir)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _folder_or_default(raw: str | None, default: Path) -> Path:
    if raw and str(raw).strip():
        return Path(str(raw).strip()).expanduser().resolve()
    return default.resolve()


def resolve_paths(config_data_dir: Path) -> ResolvedPaths:
    config_data_dir = config_data_dir.resolve()
    wc = load_webui_config(config_data_dir)
    jobs_root = _folder_or_default((wc.get("output_folder") or "").strip() or None, config_data_dir / "jobs")
    uploads_dir = _folder_or_default((wc.get("upload_folder") or "").strip() or None, config_data_dir / "uploads")
    return ResolvedPaths(
        config_data_dir=config_data_dir,
        jobs_root=jobs_root,
        uploads_dir=uploads_dir,
    )


def path_is_writable_dir(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        return os.access(p, os.W_OK)
    except OSError:
        return False


def get_effective_settings() -> Settings:
    s = Settings()
    data_dir = s.resolved_data_dir()
    wc = load_webui_config(data_dir)

    env_py = os.environ.get("ULTRASINGER_PY", "").strip()
    if env_py:
        s = s.model_copy(update={"ultrasinger_py": Path(env_py).expanduser().resolve()})
    else:
        file_py = (wc.get("ultrasinger_py") or "").strip()
        if file_py:
            s = s.model_copy(update={"ultrasinger_py": Path(file_py).expanduser().resolve()})

    env_cookie = os.environ.get("ULTRASINGER_COOKIE_FILE", "").strip()
    if env_cookie:
        s = s.model_copy(update={"cookiefile": Path(env_cookie).expanduser().resolve()})
    py_exe = os.environ.get("PYTHON_EXE", "").strip()
    if py_exe:
        s = s.model_copy(update={"python_exe": py_exe})
    return s


def merge_webui_config(data_dir: Path, updates: dict[str, str | None]) -> None:
    wc = load_webui_config(data_dir)
    for k, v in updates.items():
        if v is None or (isinstance(v, str) and not str(v).strip()):
            wc.pop(k, None)
        else:
            wc[k] = str(v).strip()
    cfg_path = webui_config_path(data_dir)
    if not wc:
        cfg_path.unlink(missing_ok=True)
    else:
        _atomic_write_json(cfg_path, wc)


def server_settings_payload() -> dict[str, Any]:
    base = Settings()
    data_dir = base.resolved_data_dir()
    wc = load_webui_config(data_dir)
    file_raw = (wc.get("ultrasinger_py") or "").strip()
    env_raw = os.environ.get("ULTRASINGER_PY", "").strip()
    env_set = bool(env_raw)
    merged = get_effective_settings()
    p = merged.ultrasinger_py
    exists = bool(p and p.is_file())
    paths = resolve_paths(data_dir)
    of_in = (wc.get("output_folder") or "").strip()
    uf_in = (wc.get("upload_folder") or "").strip()
    return {
        "ultrasinger_py": str(p) if p else None,
        "ultrasinger_py_is_file": exists,
        "ultrasinger_py_input": env_raw if env_set else file_raw,
        "ultrasinger_py_locked_by_env": env_set,
        "data_dir": str(data_dir),
        "output_folder_input": of_in,
        "upload_folder_input": uf_in,
        "output_folder_resolved": str(paths.jobs_root),
        "upload_folder_resolved": str(paths.uploads_dir),
        "output_folder_writable": path_is_writable_dir(paths.jobs_root),
        "upload_folder_writable": path_is_writable_dir(paths.uploads_dir),
    }
