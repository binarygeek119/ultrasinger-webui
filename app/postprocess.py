from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

from app.models import ProcessingOptions

log = logging.getLogger(__name__)

AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".opus", ".flac", ".m4a", ".aac", ".webm"}
VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".mov", ".avi"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def _is_workfile(path: Path) -> bool:
    name = path.name.lower()
    if name.endswith(".mid"):
        return True
    if "[instrumental]" in name or "[vocals]" in name:
        return True
    stem = path.stem.lower()
    if path.suffix.lower() in AUDIO_EXTS:
        if "instrumental" in stem or "vocals" in stem or stem.endswith("(vocals)") or stem.endswith("(instrumental)"):
            return True
    return False


def _collect_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file():
            out.append(p)
    return out


def _pick_main_txt(files: list[Path]) -> Path | None:
    txts = [
        f
        for f in files
        if f.suffix.lower() == ".txt" and not f.name.lower().startswith("readme")
    ]
    if not txts:
        return None
    for t in txts:
        try:
            head = t.read_text(encoding="utf-8", errors="ignore")[:6000]
            if "#ARTIST" in head or "#TITLE" in head or ": " in head and "F " in head:
                return t
        except OSError:
            continue
    return txts[0]


def _pick_main_audio(files: list[Path]) -> Path | None:
    candidates: list[Path] = []
    for f in files:
        if f.suffix.lower() not in AUDIO_EXTS:
            continue
        if _is_workfile(f):
            continue
        candidates.append(f)
    if not candidates:
        return None
    try:
        return max(candidates, key=lambda p: p.stat().st_size)
    except OSError:
        return candidates[0]


def _pick_video(files: list[Path]) -> Path | None:
    vids = [f for f in files if f.suffix.lower() in VIDEO_EXTS]
    if not vids:
        return None
    try:
        return max(vids, key=lambda p: p.stat().st_size)
    except OSError:
        return vids[0]


def _pick_cover(files: list[Path]) -> Path | None:
    for f in files:
        n = f.name.lower()
        if n.startswith("cover.") and f.suffix.lower() in IMAGE_EXTS:
            return f
    imgs = [f for f in files if f.suffix.lower() in IMAGE_EXTS]
    return imgs[0] if imgs else None


def _parse_meta(txt_path: Path) -> tuple[str | None, str | None]:
    artist = title = None
    try:
        lines = txt_path.read_text(encoding="utf-8", errors="ignore").splitlines()[:120]
    except OSError:
        return None, None
    for line in lines:
        if line.upper().startswith("#ARTIST"):
            artist = line.split(":", 1)[-1].strip()
        elif line.upper().startswith("#TITLE"):
            title = line.split(":", 1)[-1].strip()
    return artist, title


def _safe_zip_base(artist: str | None, title: str | None, fallback: str) -> str:
    parts = []
    if artist:
        parts.append(artist)
    if title:
        parts.append(title)
    base = " - ".join(parts) if parts else fallback
    base = re.sub(r'[<>:"/\\|?*]', "_", base).strip()
    base = base[:180] or fallback
    return base


def _ffmpeg_convert(src: Path, dst: Path) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    fmt = dst.suffix.lower().lstrip(".")
    if fmt == "mp3":
        args = ["-codec:a", "libmp3lame", "-q:a", "2"]
    elif fmt == "wav":
        args = ["-codec:a", "pcm_s16le"]
    elif fmt == "ogg":
        args = ["-codec:a", "libvorbis", "-q:a", "5"]
    elif fmt == "opus":
        args = ["-codec:a", "libopus", "-b:a", "128k"]
    elif fmt == "flac":
        args = ["-codec:a", "flac"]
    else:
        shutil.copy2(src, dst)
        return True
    cmd = ["ffmpeg", "-y", "-i", str(src), *args, str(dst)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, check=False)
        if r.returncode != 0:
            log.error("ffmpeg failed: %s", r.stderr[-500:] if r.stderr else r.returncode)
            return False
        return True
    except FileNotFoundError:
        log.error("ffmpeg not found in PATH")
        return False
    except subprocess.TimeoutExpired:
        return False


def _ensure_cover_jpg(src: Path, dst: Path) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() in {".jpg", ".jpeg"}:
        shutil.copy2(src, dst)
        return True
    cmd = ["ffmpeg", "-y", "-i", str(src), "-q:v", "2", str(dst)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
        return r.returncode == 0 and dst.is_file()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        shutil.copy2(src, dst.with_suffix(src.suffix))
        return False


def run_postprocess(
    work_dir: Path,
    output_dir: Path,
    options: ProcessingOptions,
    job_fallback_name: str,
) -> dict:
    """
    Read UltraSinger outputs from work_dir, apply renaming/conversion into output_dir.
    Returns metadata dict: zip_base, files (relative paths), workfiles_kept bool
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    files = _collect_files(work_dir)
    main_txt = _pick_main_txt(files)
    main_audio = _pick_main_audio(files)
    video = _pick_video(files)
    cover = _pick_cover(files)

    artist, title = (None, None)
    if main_txt:
        artist, title = _parse_meta(main_txt)
    zip_base = _safe_zip_base(artist, title, job_fallback_name)

    workfile_paths = [f for f in files if _is_workfile(f)]
    if options.delete_workfiles:
        for wf in workfile_paths:
            try:
                wf.unlink(missing_ok=True)
            except OSError:
                pass
        workfile_paths = []

    rel_outputs: list[str] = []

    txt_name = "notes.txt" if options.yarg_compatible else "song.txt"
    if main_txt:
        shutil.copy2(main_txt, output_dir / txt_name)
        rel_outputs.append(txt_name)

    audio_fmt = options.output_audio_format
    if main_audio and audio_fmt != "off":
        ext = main_audio.suffix.lower().lstrip(".")
        if audio_fmt != "original":
            ext = audio_fmt
        audio_out = ("guitar" if options.yarg_compatible else "song") + f".{ext}"
        dest = output_dir / audio_out
        if audio_fmt == "original":
            shutil.copy2(main_audio, dest)
        else:
            if not _ffmpeg_convert(main_audio, dest):
                shutil.copy2(main_audio, output_dir / (("guitar" if options.yarg_compatible else "song") + main_audio.suffix.lower()))
                audio_out = ("guitar" if options.yarg_compatible else "song") + main_audio.suffix.lower()
        rel_outputs.append(audio_out)

    if video:
        vname = "background" if options.yarg_compatible else "video"
        vout = f"{vname}{video.suffix.lower()}"
        shutil.copy2(video, output_dir / vout)
        rel_outputs.append(vout)

    if cover:
        cdest = output_dir / "cover.jpg"
        if cover.suffix.lower() in {".jpg", ".jpeg"}:
            shutil.copy2(cover, cdest)
        else:
            _ensure_cover_jpg(cover, cdest)
        if cdest.is_file():
            rel_outputs.append("cover.jpg")

    if not options.delete_workfiles and workfile_paths:
        wf_dir = output_dir / "workfiles"
        wf_dir.mkdir(parents=True, exist_ok=True)
        for wf in workfile_paths:
            if not wf.is_file():
                continue
            target = wf_dir / wf.name
            n = 1
            while target.exists():
                target = wf_dir / f"{wf.stem}_{n}{wf.suffix}"
                n += 1
            try:
                shutil.copy2(wf, target)
                rel_outputs.append(str(target.relative_to(output_dir)))
            except OSError:
                pass

    return {
        "zip_base": zip_base,
        "files": rel_outputs,
        "artist": artist,
        "title": title,
    }
