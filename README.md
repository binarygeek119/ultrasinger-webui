# UltraSinger WebUI

A browser-based companion for **[UltraSinger](https://github.com/rakuri255/UltraSinger)**. It does not modify UltraSinger: the WebUI queues work, runs `UltraSinger.py` as a subprocess, handles uploads, optional playlist expansion, post-processing (ffmpeg, YARG naming, workfiles), on-demand ZIP downloads, job history, and cleanup.

**This repository was written entirely with AI coding tools** (no hand-authored baseline). Treat it as a starting point: review the code, run your own tests, and verify behavior before relying on it for anything important.

## Features

- Submit jobs from a **single URL**, **playlist** (via [yt-dlp](https://github.com/yt-dlp/yt-dlp)), or **file upload**
- **Settings** page: UltraSinger path, optional job output / upload directories, Whisper compute type, audio format, YARG mode, workfile handling (stored in `data/webui_config.json` and browser localStorage as appropriate)
- **Jobs / history**, **retry** failed jobs, **downloads** (per job or bundle)
- Automatic cleanup of old job folders (configurable retention)

## Requirements

- **Python** 3.10+ (3.12 recommended)
- **[UltraSinger](https://github.com/rakuri255/UltraSinger)** installed and runnable on the same machine (or in a custom Docker image you build on top of this one)
- **[ffmpeg](https://ffmpeg.org/)** on `PATH` (audio conversion and thumbnails)
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** on `PATH` for playlist expansion (optional; also listed in `requirements.txt`)

## Quick start

```bash
git clone <your-fork-or-repo-url>
cd ultrasinger-webui
pip install -r requirements.txt
```

Set the path to UltraSinger (examples):

```bash
# Linux / macOS
export ULTRASINGER_PY="/home/you/UltraSinger/UltraSinger.py"

# Windows (PowerShell)
$env:ULTRASINGER_PY = "D:\UltraSinger\UltraSinger.py"
```

Run the server from the project root:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Or:

```bash
python -m app.main
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080).

## Configuration

### Environment variables

| Variable | Description |
|----------|-------------|
| `ULTRASINGER_PY` | Path to `UltraSinger.py`. If set, overrides the path saved in the WebUI settings file. |
| `ULTRASINGER_WEBUI_DATA_DIR` | App data root (default: `data`). Holds `webui_config.json`, `history/`, `jobs/` (unless overridden), `tmp/`, etc. |
| `ULTRASINGER_WEBUI_MAX_CONCURRENT_JOBS` | Parallel workers (default: `1`). |
| `ULTRASINGER_WEBUI_JOB_RETENTION_HOURS` | Delete old job folders / uploads on schedule (default: `24`). |
| `PYTHON_EXE` | Interpreter used to launch UltraSinger (default: `python`). |
| `ULTRASINGER_COOKIE_FILE` | Optional cookies file for yt-dlp / UltraSinger (`--cookiefile`). |

You can also use a `.env` file in the project directory for `ULTRASINGER_WEBUI_*` settings (see `app/config.py`).

### Paths in the UI

Under **Settings**, you can set:

- **UltraSinger.py** path (persisted in `data/webui_config.json` unless `ULTRASINGER_PY` is set)
- **Output folder** (parent of `job_0001`, …) and **upload folder** (temporary uploads); defaults are `{data_dir}/jobs` and `{data_dir}/uploads`

## Docker

**Maintainer note:** The Docker setup here layers this WebUI on top of the official UltraSinger container image. **I have not run or verified it myself** — expect to debug build/runtime issues. After the container is up, you still need to **finish setup in the WebUI** (open **Settings**, confirm paths, Whisper options, folders, etc.); defaults in `docker-compose.yml` / the Dockerfile may not match your host or a future base image.

The [`Dockerfile`](Dockerfile) uses the official UltraSinger image as its base:

`ghcr.io/rakuri255/ultrasinger:sha-4155efd`

That base includes **UltraSinger**, **ffmpeg**, **Python 3.12**, **CUDA 12.8** runtime, and the PyTorch/CUDA stack from upstream. This image adds the WebUI (FastAPI, uvicorn, yt-dlp, etc.) on top. Defaults inside the container:

- `ULTRASINGER_PY=/app/UltraSinger/UltraSinger.py`
- `PYTHON_EXE=python3.12`
- `ULTRASINGER_WEBUI_DATA_DIR=/data`

```bash
docker compose build
docker compose up -d
```

For **NVIDIA GPU** inside the container, install the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) and uncomment the `deploy.resources.reservations.devices` block in [`docker-compose.yml`](docker-compose.yml) (or use `docker run --gpus all`).

To pin a different UltraSinger image tag, change the `FROM` line in the Dockerfile.

## API

The SPA uses JSON endpoints under `/api/`, including:

- `GET /api/health` — liveness and whether UltraSinger path resolves to a file
- `GET` / `PUT /api/settings` — server-side settings payload
- `POST /api/jobs/url`, `/api/jobs/playlist`, `/api/jobs/upload`
- `GET /api/jobs`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/retry`
- `GET /api/jobs/{id}/download`, `GET /api/jobs/{id}/log`
- `POST /api/bundles/start` and related bundle download endpoints

## License

Specify your license in this repository. UltraSinger has its own license; see the [UltraSinger repository](https://github.com/rakuri255/UltraSinger).
