from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class InputType(str, Enum):
    url = "url"
    playlist = "playlist"
    upload = "upload"


class ProcessingOptions(BaseModel):
    whisper_compute_type: str = "int8"
    output_audio_format: Literal["original", "mp3", "wav", "ogg", "opus", "flac", "off"] = "original"
    yarg_compatible: bool = False
    delete_workfiles: bool = False


class JobInput(BaseModel):
    type: InputType
    source: str = Field(description="URL or original filename for uploads")


class JobRecord(BaseModel):
    id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    input: JobInput
    options: ProcessingOptions
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    retried_from: str | None = None
    log_rel_path: str = "logs/run.log"


class BundleStatus(BaseModel):
    id: str
    status: Literal["pending", "building", "ready", "failed"]
    message: str | None = None
    filename: str | None = None
