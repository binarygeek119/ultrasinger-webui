from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ULTRASINGER_WEBUI_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    ultrasinger_py: Path | None = None
    python_exe: str = "python"
    max_concurrent_jobs: int = 1
    job_retention_hours: int = 24
    host: str = "0.0.0.0"
    port: int = 8080
    cookiefile: Path | None = None

    def resolved_data_dir(self) -> Path:
        return self.data_dir.resolve()
