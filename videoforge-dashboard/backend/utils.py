"""Utilities for VideoForge Optimizer backend."""
import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("videoforge")
logging.basicConfig(level=logging.INFO)

TEMP_DIR = Path("/tmp/videoforge")


def get_ffmpeg_version() -> str:
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
        return result.stdout.splitlines()[0].replace("ffmpeg version ", "").split()[0] if result.stdout else "unknown"
    except Exception:
        return "not installed"


def get_upload_dir(job_id: str) -> Path:
    d = TEMP_DIR / "uploads" / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_output_path(job_id: str, stage_id: str) -> str:
    d = TEMP_DIR / "processing" / job_id
    d.mkdir(parents=True, exist_ok=True)
    return str(d / f"{stage_id}_out.mp4")


def get_final_path(job_id: str) -> Path:
    d = TEMP_DIR / "processed"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{job_id}_final.mp4"


def cleanup_job_files(job_id: str):
    for subdir in ["uploads", "processing"]:
        p = TEMP_DIR / subdir / job_id
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
    final = get_final_path(job_id)
    if final.exists():
        final.unlink()


def cleanup_scheduler(interval_minutes: int = 30):
    import asyncio
    from datetime import datetime, timedelta
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            cutoff = datetime.now() - timedelta(hours=2)
            for subdir in ["uploads", "processing", "processed"]:
                base = TEMP_DIR / subdir
                if not base.exists():
                    continue
                for item in base.iterdir():
                    if item.is_dir() and datetime.fromtimestamp(item.stat().st_mtime) < cutoff:
                        shutil.rmtree(item, ignore_errors=True)
                        logger.info("Cleaned up old temp dir: %s", item)
        except Exception as e:
            logger.warning("Cleanup error: %s", e)
