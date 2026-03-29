from __future__ import annotations

import json
import logging
import queue
import re
import shutil
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from app.cleanup import cleanup_old_jobs
from app.config import Settings
from app.runtime_settings import resolve_paths
from app.history import append_history_line
from app.models import InputType, JobInput, JobRecord, JobStatus, ProcessingOptions
from app.playlist import expand_playlist
from app.postprocess import run_postprocess
from app.ultrasinger_runner import run_ultrasinger
from app.youtube_util import normalize_youtube_url_for_single_video

log = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _next_job_id(jobs_root: Path) -> str:
    jobs_root.mkdir(parents=True, exist_ok=True)
    max_n = 0
    for p in jobs_root.iterdir():
        if not p.is_dir() or not p.name.startswith("job_"):
            continue
        tail = p.name[4:]
        try:
            max_n = max(max_n, int(tail))
        except ValueError:
            continue
    return f"job_{max_n + 1:04d}"


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _read_job_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _record_to_dict(r: JobRecord) -> dict[str, Any]:
    return json.loads(r.model_dump_json())


def _dict_to_record(d: dict[str, Any]) -> JobRecord:
    return JobRecord.model_validate(d)


class BundleTask:
    def __init__(self) -> None:
        self.status: str = "pending"
        self.message: str | None = None
        self.path: Path | None = None
        self.filename: str | None = None
        self.lock = threading.Lock()


class JobManager:
    def __init__(self, get_settings: Callable[[], Settings]) -> None:
        self._get_settings = get_settings
        s = get_settings()
        self.settings = s
        self.data_dir = s.resolved_data_dir()
        self._queue: queue.Queue[str] = queue.Queue()
        self._bundles: dict[str, BundleTask] = {}
        self._worker_started = False
        self._lock = threading.Lock()

    def _paths(self):
        return resolve_paths(self.data_dir)

    def ensure_layout(self) -> None:
        p = self._paths()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "history").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "tmp" / "bundles").mkdir(parents=True, exist_ok=True)
        p.jobs_root.mkdir(parents=True, exist_ok=True)
        p.uploads_dir.mkdir(parents=True, exist_ok=True)

    def start_background(self) -> None:
        self.ensure_layout()
        cleanup_old_jobs(self._paths(), self.settings.job_retention_hours)
        with self._lock:
            if self._worker_started:
                return
            self._worker_started = True
            for _ in range(max(1, self.settings.max_concurrent_jobs)):
                t = threading.Thread(target=self._worker_loop, daemon=True)
                t.start()
        self._schedule_periodic_cleanup()

    def _schedule_periodic_cleanup(self) -> None:
        def loop() -> None:
            while True:
                time.sleep(24 * 3600)
                try:
                    cleanup_old_jobs(self._paths(), self.settings.job_retention_hours)
                except Exception:
                    log.exception("periodic cleanup failed")

        threading.Thread(target=loop, daemon=True).start()

    def _worker_loop(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                self._execute_job(job_id)
            except Exception:
                log.exception("job %s crashed", job_id)
                self._fail_job(job_id, "Internal error; see server logs.")
            finally:
                self._queue.task_done()

    def _job_dir(self, job_id: str) -> Path:
        return self._paths().jobs_root / job_id

    def _save(self, record: JobRecord) -> None:
        path = self._job_dir(record.id) / "job.json"
        _atomic_write_json(path, _record_to_dict(record))

    def load(self, job_id: str) -> JobRecord | None:
        path = self._job_dir(job_id) / "job.json"
        if not path.is_file():
            return None
        return _dict_to_record(_read_job_json(path))

    def list_jobs(self) -> list[JobRecord]:
        root = self._paths().jobs_root
        if not root.is_dir():
            return []
        out: list[JobRecord] = []
        for p in sorted(root.iterdir(), key=lambda x: x.name, reverse=True):
            if not p.is_dir():
                continue
            rec = self.load(p.name)
            if rec:
                out.append(rec)
        return out

    def create_job_record(
        self,
        inp: JobInput,
        options: ProcessingOptions,
        retried_from: str | None = None,
    ) -> JobRecord:
        jid = _next_job_id(self._paths().jobs_root)
        now = _utc_now()
        rec = JobRecord(
            id=jid,
            status=JobStatus.queued,
            created_at=now,
            updated_at=now,
            input=inp,
            options=options,
            retried_from=retried_from,
        )
        d = self._job_dir(jid)
        (d / "input").mkdir(parents=True, exist_ok=True)
        (d / "work").mkdir(parents=True, exist_ok=True)
        (d / "output").mkdir(parents=True, exist_ok=True)
        (d / "package").mkdir(parents=True, exist_ok=True)
        (d / "logs").mkdir(parents=True, exist_ok=True)
        self._save(rec)
        return rec

    def enqueue(self, job_id: str) -> None:
        self._queue.put(job_id)

    def submit_url(self, url: str, options: ProcessingOptions) -> JobRecord:
        inp = JobInput(type=InputType.url, source=normalize_youtube_url_for_single_video(url.strip()))
        rec = self.create_job_record(inp, options)
        self.enqueue(rec.id)
        return rec

    def submit_playlist(self, playlist_url: str, options: ProcessingOptions) -> list[JobRecord]:
        urls = expand_playlist(playlist_url.strip())
        created: list[JobRecord] = []
        for u in urls:
            inp = JobInput(type=InputType.playlist, source=u)
            rec = self.create_job_record(inp, options)
            created.append(rec)
            self.enqueue(rec.id)
        return created

    def submit_upload(self, saved_path: Path, original_name: str, options: ProcessingOptions) -> JobRecord:
        inp = JobInput(type=InputType.upload, source=original_name)
        rec = self.create_job_record(inp, options)
        dest = self._job_dir(rec.id) / "input" / Path(original_name).name
        shutil.copy2(saved_path, dest)
        self._save(rec)
        self.enqueue(rec.id)
        return rec

    def retry(self, job_id: str) -> JobRecord | None:
        old = self.load(job_id)
        if not old:
            return None
        rec = self.create_job_record(old.input, old.options, retried_from=old.id)
        if old.input.type == InputType.upload:
            src = self._job_dir(old.id) / "input" / Path(old.input.source).name
            if src.is_file():
                dest = self._job_dir(rec.id) / "input" / src.name
                shutil.copy2(src, dest)
        self._save(rec)
        append_history_line(self.data_dir, f"{rec.id} | retry_from | {old.id}")
        self.enqueue(rec.id)
        return rec

    def _update_status(self, job_id: str, status: JobStatus, **extra: Any) -> None:
        rec = self.load(job_id)
        if not rec:
            return
        rec.status = status
        rec.updated_at = _utc_now()
        for k, v in extra.items():
            setattr(rec, k, v)
        self._save(rec)

    def _fail_job(self, job_id: str, message: str) -> None:
        rec = self.load(job_id)
        if rec:
            rec.status = JobStatus.failed
            rec.error = message
            rec.updated_at = _utc_now()
            self._save(rec)
            append_history_line(self.data_dir, f"{job_id} | failed | {message[:200]}")

    def _execute_job(self, job_id: str) -> None:
        rec = self.load(job_id)
        if not rec:
            return
        self._update_status(job_id, JobStatus.running, error=None)
        jd = self._job_dir(job_id)
        work_dir = jd / "work"
        output_dir = jd / "output"
        log_path = jd / "logs" / "run.log"

        if rec.input.type == InputType.upload:
            input_target = str((jd / "input" / Path(rec.input.source).name).resolve())
            if not Path(input_target).is_file():
                self._fail_job(job_id, "Upload missing from job input folder.")
                return
        else:
            input_target = normalize_youtube_url_for_single_video(rec.input.source.strip())

        code, _tail = run_ultrasinger(
            self._get_settings(),
            input_target,
            work_dir,
            rec.options.whisper_compute_type,
            log_path,
        )
        if code != 0:
            self._fail_job(job_id, f"UltraSinger exited with code {code}. Check logs.")
            return

        try:
            meta = run_postprocess(work_dir, output_dir, rec.options, job_id)
        except Exception as e:
            log.exception("postprocess %s", job_id)
            self._fail_job(job_id, f"Post-processing failed: {e}")
            return

        zbase = meta.get("zip_base", job_id)
        zip_name = zbase + ".zip"
        rec.status = JobStatus.completed
        rec.updated_at = _utc_now()
        rec.output = {
            "zip_name": zip_name,
            "zip_base": zbase,
            "files": meta.get("files", []),
            "artist": meta.get("artist"),
            "title": meta.get("title"),
        }
        rec.error = None
        self._save(rec)
        append_history_line(self.data_dir, f"{job_id} | completed | zip={zip_name}")

    def build_job_zip_path(self, job_id: str) -> tuple[Path, str] | None:
        rec = self.load(job_id)
        if not rec or rec.status != JobStatus.completed:
            return None
        jd = self._job_dir(job_id)
        output_dir = jd / "output"
        if not output_dir.is_dir():
            return None
        name = (rec.output or {}).get("zip_name") or f"{job_id}.zip"
        tmp = Path(tempfile.mkdtemp(dir=str(self.data_dir / "tmp"))) / name
        count = 0
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in output_dir.rglob("*"):
                if p.is_file():
                    arc = p.relative_to(output_dir)
                    zf.write(p, arcname=str(arc).replace("\\", "/"))
                    count += 1
        if count == 0:
            try:
                tmp.unlink(missing_ok=True)
                tmp.parent.rmdir()
            except OSError:
                pass
            return None
        return tmp, name

    def start_download_all_bundle(self, job_ids: list[str] | None) -> str:
        bundle_id = uuid4().hex[:16]
        task = BundleTask()
        with task.lock:
            task.status = "building"
            task.message = "Preparing download..."
        self._bundles[bundle_id] = task

        def run() -> None:
            try:
                jobs = self.list_jobs()
                if job_ids is not None:
                    wanted = set(job_ids)
                    jobs = [j for j in jobs if j.id in wanted]
                completed = [j for j in jobs if j.status == JobStatus.completed]
                if not completed:
                    with task.lock:
                        task.status = "failed"
                        task.message = "No completed jobs to download."
                    return
                date_s = _utc_now().strftime("%Y-%m-%d")
                filename = f"ultrasinger_downloads_{date_s}.zip"
                out_path = self.data_dir / "tmp" / "bundles" / f"{bundle_id}.zip"
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for j in completed:
                        od = self._job_dir(j.id) / "output"
                        if not od.is_dir():
                            continue
                        folder = (j.output or {}).get("zip_base") or j.id
                        folder = re.sub(r'[<>:"/\\|?*]', "_", folder)[:120]
                        for p in od.rglob("*"):
                            if p.is_file():
                                arc = Path(folder) / p.relative_to(od)
                                zf.write(p, arcname=str(arc).replace("\\", "/"))
                with task.lock:
                    task.status = "ready"
                    task.path = out_path
                    task.filename = filename
                    task.message = None
            except Exception as e:
                log.exception("bundle %s", bundle_id)
                with task.lock:
                    task.status = "failed"
                    task.message = str(e)

        threading.Thread(target=run, daemon=True).start()
        return bundle_id

    def get_bundle(self, bundle_id: str) -> BundleTask | None:
        return self._bundles.get(bundle_id)

    def read_job_log(self, job_id: str) -> str | None:
        p = self._job_dir(job_id) / "logs" / "run.log"
        if not p.is_file():
            return None
        return p.read_text(encoding="utf-8", errors="replace")
