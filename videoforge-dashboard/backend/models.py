from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


def generate_job_id() -> str:
    return str(uuid.uuid4())[:12]


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    ERROR = "error"


class JobState:
    def __init__(self, job_id: str, status: JobStatus, metadata: dict):
        self.job_id = job_id
        self.status = status
        self.metadata = metadata
        self.current_stage: str = ""
        self.stage_progress: int = 0
        self.message: str = ""
        self.download_url: Optional[str] = None
        self.completed_at: Optional[datetime] = None
        self.error_message: Optional[str] = None


class HealthResponse:
    status: str
    ffmpeg_version: str

    def __init__(self, status: str, ffmpeg_version: str):
        self.status = status
        self.ffmpeg_version = ffmpeg_version


class UploadResponse:
    job_id: str
    file_name: str
    file_size: int
    duration: float
    resolution: str
    video_codec: str
    audio_codec: str
    fps: float
    bitrate: int

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class ProcessConfig:
    stages: Dict[str, Any]

    def __init__(self, stages: dict):
        self.stages = stages


class StageConfig:
    enabled: bool
    options: Dict[str, Any]

    def __init__(self, enabled: bool = True, options: Optional[dict] = None):
        self.enabled = enabled
        self.options = options or {}
