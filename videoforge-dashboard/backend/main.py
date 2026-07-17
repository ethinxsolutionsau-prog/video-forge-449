"""VideoForge Optimizer — FastAPI backend."""
from __future__ import annotations
import asyncio
import shutil
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .engine import run_pipeline, stage_ingest
from .utils import cleanup_job_files, cleanup_scheduler, get_ffmpeg_version, get_upload_dir
from .websocket import ws_manager

jobs: Dict[str, dict] = {}
job_metadata: Dict[str, dict] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(cleanup_scheduler(interval_minutes=30))
    yield
    cleanup_task.cancel()

app = FastAPI(title="VideoForge Optimizer", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "ffmpeg_version": get_ffmpeg_version()}

@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    import uuid
    job_id = str(uuid.uuid4())[:12]
    upload_dir = get_upload_dir(job_id)
    file_path = upload_dir / (file.filename or "video.mp4")
    content = await file.read()
    file_path.write_bytes(content)
    file_size = len(content)
    try:
        metadata = stage_ingest(str(file_path))
    except Exception:
        metadata = {"duration": 0.0, "width": 0, "height": 0, "fps": 0.0, "video_codec": "unknown", "audio_codec": "unknown", "bitrate": 0}
    jobs[job_id] = {"status": "pending", "file_path": str(file_path), "file_name": file.filename or "video.mp4"}
    job_metadata[job_id] = metadata
    return {
        "job_id": job_id,
        "file_name": file.filename or "video.mp4",
        "file_size": file_size,
        "duration": metadata.get("duration", 0),
        "resolution": f"{metadata.get('width', 0)}x{metadata.get('height', 0)}",
        "video_codec": metadata.get("video_codec", ""),
        "audio_codec": metadata.get("audio_codec", ""),
        "fps": metadata.get("fps", 0),
        "bitrate": metadata.get("bitrate", 0),
    }

@app.post("/api/process/{job_id}")
async def start_processing(job_id: str, config: dict):
    if job_id not in jobs:
        raise HTTPException(404, detail="Job not found")
    if jobs[job_id].get("status") == "running":
        raise HTTPException(409, detail="Job already running")
    jobs[job_id]["status"] = "running"
    file_path = jobs[job_id]["file_path"]
    asyncio.create_task(_run_pipeline_bg(job_id, file_path, config))
    return {"job_id": job_id, "status": "started"}

async def _run_pipeline_bg(job_id: str, file_path: str, config: dict):
    try:
        final_path = await run_pipeline(job_id, file_path, config, ws_manager)
        jobs[job_id]["status"] = "complete"
        jobs[job_id]["final_path"] = final_path
    except Exception as exc:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(exc)

@app.get("/api/progress/{job_id}")
async def get_progress(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, detail="Job not found")
    j = jobs[job_id]
    return {"job_id": job_id, "status": j.get("status"), "download_url": "/api/download/{job_id}" if j.get("status") == "complete" else None}

@app.get("/api/download/{job_id}")
async def download_video(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, detail="Job not found")
    fp = jobs[job_id].get("final_path")
    if not fp or not Path(fp).exists():
        raise HTTPException(404, detail="File not ready")
    return FileResponse(path=fp, filename=f"videoforge_{job_id}.mp4", media_type="video/mp4")

@app.websocket("/ws/progress/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    await ws_manager.connect(job_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except (WebSocketDisconnect, Exception):
        ws_manager.disconnect(job_id, websocket)

@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, detail="Job not found")
    cleanup_job_files(job_id)
    del jobs[job_id]
    job_metadata.pop(job_id, None)
    return {"job_id": job_id, "status": "deleted"}
