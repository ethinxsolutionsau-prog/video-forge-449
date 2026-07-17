"""Video processing engine — ffmpeg pipeline for VideoForge Optimizer."""
from __future__ import annotations
import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

TEMP_DIR = Path("/tmp/videoforge")

def _run_ffmpeg(cmd: list[str], description: str = "ffmpeg") -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        err = result.stderr[-2000:] if result.stderr else "unknown error"
        raise RuntimeError(f"{description} failed: {err}")

def _run_ffprobe(input_path: str) -> dict:
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", input_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return json.loads(result.stdout)

def _parse_fps(avg_frame_rate: str) -> float:
    try:
        if "/" in avg_frame_rate:
            num, den = avg_frame_rate.split("/")
            return round(float(num) / float(den), 2)
        return float(avg_frame_rate)
    except (ValueError, ZeroDivisionError):
        return 0.0

def _get_video_stream(probe_data: dict) -> Optional[dict]:
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    return None

def _get_audio_stream(probe_data: dict) -> Optional[dict]:
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") == "audio":
            return stream
    return None

# ---------------------------------------------------------------------------
# Stage 1: Smart Ingest
# ---------------------------------------------------------------------------
def stage_ingest(input_path: str, options: dict | None = None) -> dict:
    probe = _run_ffprobe(input_path)
    vstream = _get_video_stream(probe)
    astream = _get_audio_stream(probe)
    fmt = probe.get("format", {})
    return {
        "duration": float(vstream.get("duration", fmt.get("duration", 0)) or 0),
        "width": int(vstream.get("width", 0) or 0),
        "height": int(vstream.get("height", 0) or 0),
        "fps": _parse_fps(vstream.get("avg_frame_rate", "0") or "0"),
        "video_codec": vstream.get("codec_name", "unknown") if vstream else "none",
        "audio_codec": astream.get("codec_name", "unknown") if astream else "none",
        "bitrate": int(fmt.get("bit_rate", 0) or 0),
        "audio_bitrate": int(astream.get("bit_rate", 0) or 0) if astream else 0,
    }

# ---------------------------------------------------------------------------
# Stage 2: Audio Cleanup
# ---------------------------------------------------------------------------
def stage_audio(input_path: str, output_path: str, options: dict) -> str:
    filters = []
    if options.get("silence"):
        filters.append("silenceremove=stop_periods=-1:stop_duration=0.5:stop_threshold=-50dB")
    if options.get("noise"):
        filters.append("highpass=f=80,lowpass=f=15000,afftdn=nf=-25")
    if options.get("normalize"):
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")
    audio_filter = ",".join(filters) if filters else "anull"
    cmd = ["ffmpeg", "-y", "-i", input_path, "-af", audio_filter, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", output_path]
    _run_ffmpeg(cmd, "stage_audio")
    return output_path

# ---------------------------------------------------------------------------
# Stage 3: Visual Enhancement
# ---------------------------------------------------------------------------
def stage_visual(input_path: str, output_path: str, options: dict) -> str:
    filters = []
    if options.get("colorgrade"):
        filters.append("eq=contrast=1.05:brightness=0.02:saturation=1.1")
    if options.get("stabilize"):
        filters.append("deshake")
    if options.get("faceenhance"):
        filters.append("unsharp=3:3:1.5:3:3:0.5")
    if options.get("bgremove"):
        filters.append("chromakey=0x00FF00:0.1:0.2")
    video_filter = ",".join(filters) if filters else "null"
    cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", video_filter, "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-c:a", "copy", "-movflags", "+faststart", output_path]
    _run_ffmpeg(cmd, "stage_visual")
    return output_path

# ---------------------------------------------------------------------------
# Stage 4: Auto Edit
# ---------------------------------------------------------------------------
def stage_edit(input_path: str, output_path: str, options: dict) -> str:
    pace = int(options.get("pace", 3))
    target_fps_map = {1: 24, 2: 25, 3: 30, 4: 48, 5: 60}
    target_fps = target_fps_map.get(pace, 30)
    cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", f"fps={target_fps}", "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-c:a", "copy", "-movflags", "+faststart", output_path]
    _run_ffmpeg(cmd, "stage_edit")
    return output_path

# ---------------------------------------------------------------------------
# Stage 5: Text & Graphics
# ---------------------------------------------------------------------------
def stage_text(input_path: str, output_path: str, options: dict) -> str:
    subtitle_path = options.get("subtitles", "")
    if subtitle_path and isinstance(subtitle_path, str) and os.path.exists(subtitle_path):
        style = "force_style='FontName=Arial,FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2'"
        cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", f"subtitles={subtitle_path}:{style}", "-c:a", "copy", "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-movflags", "+faststart", output_path]
        _run_ffmpeg(cmd, "stage_text")
        return output_path
    shutil.copy(input_path, output_path)
    return output_path

# ---------------------------------------------------------------------------
# Stage 6: Voice & Music
# ---------------------------------------------------------------------------
def stage_voice(input_path: str, output_path: str, options: dict) -> str:
    bgmusic = options.get("bgmusic", False)
    music_path = options.get("music_path", "")
    if bgmusic and music_path and isinstance(music_path, str) and os.path.exists(music_path):
        duck_db = float(options.get("ducking", -18))
        vol = 10 ** (duck_db / 20)
        fc = f"[1:a]volume={vol:.3f}[music];[0:a][music]amix=inputs=2:duration=longest:normalize=0[aout]"
        cmd = ["ffmpeg", "-y", "-i", input_path, "-i", music_path, "-filter_complex", fc, "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", output_path]
        _run_ffmpeg(cmd, "stage_voice")
        return output_path
    shutil.copy(input_path, output_path)
    return output_path

# ---------------------------------------------------------------------------
# Stage 7: Final Polish
# ---------------------------------------------------------------------------
def stage_polish(input_path: str, output_path: str, options: dict) -> str:
    filters = []
    if options.get("platformcrop"):
        crop = options.get("aspect_ratio", "16:9")
        if crop == "9:16":
            filters.append("crop=ih*9/16:ih:(iw-ih*9/16)/2:0")
        elif crop == "1:1":
            filters.append("crop=ih:ih:(iw-ih)/2:0")
        elif crop == "16:9":
            filters.append("crop=iw:iw*9/16:0:(ih-iw*9/16)/2")
        elif crop == "4:5":
            filters.append("crop=ih*4/5:ih:(iw-ih*4/5)/2:0")
    if options.get("introoutro"):
        filters.append("tpad=start_duration=2:start_mode=black")
        filters.append("tpad=stop_duration=2:stop_mode=black")
    if options.get("watermark"):
        text = options.get("watermark_text", "VideoForge")
        filters.append(f"drawtext=text='{text}':fontsize=18:fontcolor=white@0.5:x=w-tw-20:y=h-th-20")
    if options.get("endcard"):
        etext = options.get("endcard_text", "Subscribe for more")
        probe = _run_ffprobe(input_path)
        duration = float(probe.get("format", {}).get("duration", 0) or 0)
        et = max(0, duration - 3) if duration > 3 else 0
        filters.append(f"drawtext=text='{etext}':fontsize=36:fontcolor=white:x=(w-tw)/2:y=(h-th)/2:enable='gte(t,{et:.1f})'")
    if filters:
        vf = ",".join(filters)
        cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-c:a", "copy", "-movflags", "+faststart", output_path]
        _run_ffmpeg(cmd, "stage_polish")
        return output_path
    shutil.copy(input_path, output_path)
    return output_path

# ---------------------------------------------------------------------------
# Stage 8: Smart Export
# ---------------------------------------------------------------------------
def stage_export(input_path: str, output_path: str, options: dict) -> str:
    resolution = options.get("resolution", "1080p")
    format_code = options.get("format", "h264")
    height_map = {"1080p": 1080, "1440p": 1440, "4K": 2160, "720p": 720}
    target_h = height_map.get(resolution, 1080)
    if format_code == "h265":
        vcodec, pix_fmt, extra = "libx265", "yuv420p", ["-tag:v", "hvc1"]
    elif format_code == "webm":
        vcodec, pix_fmt, extra = "libvpx-vp9", "yuv420p", ["-deadline", "good", "-cpu-used", "2"]
    elif format_code == "prores":
        vcodec, pix_fmt, extra = "prores_ks", "yuv422p10le", ["-profile:v", "3"]
    else:
        vcodec, pix_fmt, extra = "libx264", "yuv420p", ["-preset", "medium", "-crf", "22"]
    cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", f"scale=-2:{target_h}:flags=lanczos", "-c:v", vcodec, "-pix_fmt", pix_fmt, *extra, "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", output_path]
    _run_ffmpeg(cmd, "stage_export")
    return output_path

# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------
STAGE_ORDER = [
    ("ingest", stage_ingest),
    ("audio", stage_audio),
    ("visual", stage_visual),
    ("edit", stage_edit),
    ("text", stage_text),
    ("voice", stage_voice),
    ("polish", stage_polish),
    ("export", stage_export),
]

async def run_pipeline(job_id: str, input_path: str, config: dict, ws_manager: Any) -> str:
    from .websocket import ws_manager as global_ws
    if ws_manager is None:
        ws_manager = global_ws
    current = input_path
    for stage_id, stage_func in STAGE_ORDER:
        stage_config = config.get(stage_id, {})
        enabled = stage_config.get("enabled", True) if isinstance(stage_config, dict) else bool(stage_config)
        stage_options = stage_config.get("options", {}) if isinstance(stage_config, dict) else {}
        if not enabled:
            await ws_manager.send_progress(job_id, stage_id, "skipped", 100, f"{stage_id} skipped")
            continue
        await ws_manager.send_progress(job_id, stage_id, "processing", 0, f"Starting {stage_id}...")
        try:
            if stage_id == "ingest":
                metadata = stage_func(current, stage_options)
                await ws_manager.send_progress(job_id, stage_id, "complete", 100, "Ingest complete")
                continue
            out_path = str(TEMP_DIR / "processing" / job_id / f"{stage_id}_out.mp4")
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            result = stage_func(current, out_path, stage_options)
            if result and result != current:
                current = result
            await ws_manager.send_progress(job_id, stage_id, "complete", 100, f"{stage_id} complete")
        except Exception as exc:
            await ws_manager.send_progress(job_id, stage_id, "error", 0, str(exc))
            await ws_manager.send_error(job_id, str(exc))
            raise
    final_path = f"/tmp/videoforge_{job_id}_final.mp4"
    shutil.copy(current, final_path)
    await ws_manager.send_complete(job_id, f"/api/download/{job_id}")
    return final_path
