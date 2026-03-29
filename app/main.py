from __future__ import annotations

import json
import logging
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import Settings
from app.job_manager import JobManager
from app.models import JobRecord, ProcessingOptions
from app.runtime_settings import get_effective_settings, merge_webui_config, resolve_paths, server_settings_payload

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

_job_manager: JobManager | None = None


def manager() -> JobManager:
    assert _job_manager is not None
    return _job_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _job_manager
    s = get_effective_settings()
    _job_manager = JobManager(get_effective_settings)
    _job_manager.start_background()
    rp = resolve_paths(s.resolved_data_dir())
    log.info(
        "UltraSinger WebUI data dir: %s | jobs: %s | uploads: %s",
        s.resolved_data_dir(),
        rp.jobs_root,
        rp.uploads_dir,
    )
    yield
    _job_manager = None


app = FastAPI(title="UltraSinger WebUI", lifespan=lifespan)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class JobOptionsBody(BaseModel):
    whisper_compute_type: str = "int8"
    output_audio_format: str = "original"
    yarg_compatible: bool = False
    delete_workfiles: bool = False


class UrlJobBody(BaseModel):
    url: str
    options: JobOptionsBody = Field(default_factory=JobOptionsBody)


class PlaylistJobBody(BaseModel):
    playlist_url: str
    options: JobOptionsBody = Field(default_factory=JobOptionsBody)


class BundleStartBody(BaseModel):
    job_ids: list[str] | None = None


class ServerSettingsBody(BaseModel):
    ultrasinger_py: str | None = None
    output_folder: str | None = None
    upload_folder: str | None = None


def _opts(body: JobOptionsBody) -> ProcessingOptions:
    fmt = body.output_audio_format
    allowed = {"original", "mp3", "wav", "ogg", "opus", "flac", "off"}
    if fmt not in allowed:
        fmt = "original"
    return ProcessingOptions(
        whisper_compute_type=body.whisper_compute_type or "int8",
        output_audio_format=fmt,  # type: ignore[arg-type]
        yarg_compatible=body.yarg_compatible,
        delete_workfiles=body.delete_workfiles,
    )


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    index = STATIC_DIR / "index.html"
    if not index.is_file():
        return "<p>Missing static/index.html</p>"
    return index.read_text(encoding="utf-8")


@app.get("/api/health")
async def health() -> dict:
    s = get_effective_settings()
    ok = bool(s.ultrasinger_py and s.ultrasinger_py.is_file())
    return {
        "ok": True,
        "ultrasinger_configured": ok,
        "data_dir": str(s.resolved_data_dir()),
    }


@app.get("/api/settings")
async def get_server_settings() -> dict:
    return server_settings_payload()


@app.put("/api/settings")
async def put_server_settings(body: ServerSettingsBody) -> dict:
    base = Settings()
    data_dir = base.resolved_data_dir()
    updates: dict[str, str | None] = {
        "output_folder": body.output_folder,
        "upload_folder": body.upload_folder,
    }
    if not os.environ.get("ULTRASINGER_PY", "").strip():
        updates["ultrasinger_py"] = body.ultrasinger_py
    merge_webui_config(data_dir, updates)
    return server_settings_payload()


@app.post("/api/jobs/url")
async def create_url_job(body: UrlJobBody) -> dict:
    opts = _opts(body.options)
    rec = manager().submit_url(body.url, opts)
    return {"job": _job_json(rec)}


@app.post("/api/jobs/playlist")
async def create_playlist_jobs(body: PlaylistJobBody) -> dict:
    opts = _opts(body.options)
    recs = manager().submit_playlist(body.playlist_url, opts)
    return {"jobs": [_job_json(r) for r in recs], "count": len(recs)}


@app.post("/api/jobs/upload")
async def create_upload_job(
    file: UploadFile = File(...),
    whisper_compute_type: str = Form("int8"),
    output_audio_format: str = Form("original"),
    yarg_compatible: str = Form("false"),
    delete_workfiles: str = Form("false"),
) -> dict:
    name = file.filename or "upload.bin"
    suffix = Path(name).suffix.lower()
    allowed = {".mp3", ".wav", ".aac", ".ogg", ".opus", ".flac", ".m4a", ".webm", ".mp4", ".mkv", ".avi"}
    if suffix not in allowed:
        raise HTTPException(400, f"Unsupported file type {suffix!r}")
    up_dir = resolve_paths(get_effective_settings().resolved_data_dir()).uploads_dir
    up_dir.mkdir(parents=True, exist_ok=True)
    tmp = up_dir / f"up_{os.urandom(8).hex()}{suffix}"
    try:
        with tmp.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        body = JobOptionsBody(
            whisper_compute_type=whisper_compute_type,
            output_audio_format=output_audio_format,
            yarg_compatible=yarg_compatible.lower() in ("1", "true", "yes", "on"),
            delete_workfiles=delete_workfiles.lower() in ("1", "true", "yes", "on"),
        )
        rec = manager().submit_upload(tmp, name, _opts(body))
    finally:
        tmp.unlink(missing_ok=True)
    return {"job": _job_json(rec)}


def _job_json(rec: JobRecord) -> dict:
    return json.loads(rec.model_dump_json())


@app.get("/api/jobs")
async def list_jobs() -> dict:
    jobs = manager().list_jobs()
    return {"jobs": [json.loads(j.model_dump_json()) for j in jobs]}


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    rec = manager().load(job_id)
    if not rec:
        raise HTTPException(404, "Job not found")
    return {"job": json.loads(rec.model_dump_json())}


@app.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str) -> dict:
    rec = manager().retry(job_id)
    if not rec:
        raise HTTPException(404, "Job not found")
    return {"job": json.loads(rec.model_dump_json())}


@app.get("/api/jobs/{job_id}/download")
async def download_job(job_id: str, background_tasks: BackgroundTasks) -> FileResponse:
    built = manager().build_job_zip_path(job_id)
    if not built:
        raise HTTPException(404, "Job not ready or not found")
    path, name = built

    def _cleanup() -> None:
        try:
            path.unlink(missing_ok=True)
            path.parent.rmdir()
        except OSError:
            pass

    background_tasks.add_task(_cleanup)
    return FileResponse(path, filename=name, media_type="application/zip")


@app.post("/api/bundles/start")
async def bundle_start(body: BundleStartBody) -> dict:
    bid = manager().start_download_all_bundle(body.job_ids)
    return {"bundle_id": bid}


@app.get("/api/bundles/{bundle_id}")
async def bundle_status(bundle_id: str) -> dict:
    t = manager().get_bundle(bundle_id)
    if not t:
        raise HTTPException(404, "Bundle not found")
    with t.lock:
        st = t.status
        msg = t.message
        fn = t.filename
    return {
        "bundle_id": bundle_id,
        "status": st,
        "message": msg,
        "filename": fn,
        "ready": st == "ready",
    }


@app.get("/api/bundles/{bundle_id}/download")
async def bundle_download(bundle_id: str, background_tasks: BackgroundTasks) -> FileResponse:
    t = manager().get_bundle(bundle_id)
    if not t:
        raise HTTPException(404, "Bundle not found")
    with t.lock:
        if t.status != "ready" or not t.path or not t.path.is_file():
            raise HTTPException(409, "Bundle not ready")
        path = t.path
        name = t.filename or path.name

    def _rm() -> None:
        path.unlink(missing_ok=True)

    background_tasks.add_task(_rm)
    return FileResponse(path, filename=name, media_type="application/zip")


@app.get("/api/jobs/{job_id}/log")
async def job_log(job_id: str) -> PlainTextResponse:
    text = manager().read_job_log(job_id)
    if text is None:
        raise HTTPException(404, "Log not found")
    return PlainTextResponse(text)


def main() -> None:
    import uvicorn

    s = get_effective_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=False)


if __name__ == "__main__":
    main()