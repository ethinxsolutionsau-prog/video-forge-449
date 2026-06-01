"""Auto-process queue items into rendered videos.

This orchestrator runs the full FacelessForge generation chain server-side
for projects created from the Google Sheets queue:

    script → scenes → auto-attach assets → thumbnail (auto-select)
           → voiceover (auto-select) → enqueue render

Each step uses the same service functions the HTTP endpoints call, so the
behaviour is identical to a user clicking through the UI manually.

Updates ``projects.queue_status`` at each transition:
    pending → processing → completed | failed
On failure, ``projects.queue_error`` is set with a short reason code.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from . import generation as gen
from . import stock as stock_service
from . import render as render_service
from .db import get_db
from .tts import generate_voiceover, SUPPORTED_STYLES

logger = logging.getLogger("facelessforge.queue_worker")


def _now():
    return datetime.now(timezone.utc)


async def _mark(project_id: str, **patch) -> None:
    db = get_db()
    patch["updated_at"] = _now()
    await db.projects.update_one({"id": project_id}, {"$set": patch})


async def run_pipeline(project_id: str, *, requested_by: str) -> dict:
    """Run the full chain. Returns a summary dict.

    Always returns; never raises. Failures are recorded on the project row.
    """
    db = get_db()
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        return {"ok": False, "step": "load_project", "error": "project_not_found"}

    steps: list[dict] = []

    def _ok(step: str, detail: dict | None = None) -> None:
        steps.append({"step": step, "ok": True, "detail": detail or {}})

    async def _fail(step: str, code: str, detail: str = "") -> dict:
        logger.warning("queue project=%s step=%s failed code=%s detail=%s",
                       project_id, step, code, detail[:200])
        await _mark(project_id,
                    queue_status="failed",
                    queue_error=code,
                    queue_error_detail=detail[:500],
                    queue_failed_step=step,
                    queue_completed_at=_now())
        steps.append({"step": step, "ok": False, "error": code, "detail": detail[:200]})
        return {"ok": False, "step": step, "error": code, "steps": steps}

    await _mark(project_id,
                queue_status="processing",
                queue_started_at=_now(),
                status="DRAFT")

    # --- 1. Script ---
    try:
        script = await gen.generate_script(project)
        await db.scripts.replace_one({"project_id": project_id},
                                     {**script, "project_id": project_id, "updated_at": _now()},
                                     upsert=True)
        _ok("generate_script", {"length": len(script.get("full_script", ""))})
    except Exception as e:  # noqa: BLE001
        return await _fail("generate_script", _classify(e), str(e))

    # --- 2. Scenes ---
    try:
        scenes = await gen.generate_scenes(project, script["full_script"])
        await db.scenes.delete_many({"project_id": project_id})
        if scenes:
            await db.scenes.insert_many(
                [{**s, "project_id": project_id, "created_at": _now()} for s in scenes]
            )
        _ok("generate_scenes", {"count": len(scenes)})
    except Exception as e:  # noqa: BLE001
        return await _fail("generate_scenes", _classify(e), str(e))

    # --- 3. Auto-attach stock assets ---
    try:
        attached = await _auto_attach(project_id, project)
        _ok("auto_attach_assets", attached)
    except Exception as e:  # noqa: BLE001
        return await _fail("auto_attach_assets", _classify(e), str(e))

    # --- 4. Thumbnail briefs + images (auto-select first image) ---
    try:
        from . import thumbnail_images as thumb_images
        # 4a) Generate concept briefs (text)
        briefs = await gen.generate_thumbnails(project)
        brief_asset_id = None
        if briefs:
            brief = briefs[0]
            brief_asset_id = f"thumb-brief-{project_id[:8]}"
            await db.assets.insert_one({
                "id": brief_asset_id,
                "project_id": project_id,
                "asset_type": "thumbnail_concept",
                "brief": brief,
                "status": "selected",
                "created_at": _now(),
            })
        # 4b) Generate at least one image variant for the brief
        generated = []
        if briefs:
            generated = await thumb_images.generate_thumbnail_images(
                project, briefs[0], variants=1, project_id=project_id,
            )
        if generated:
            for g in generated:
                g["brief_asset_id"] = brief_asset_id
                g["created_at"] = _now()
                g["updated_at"] = _now()
            await db.assets.insert_many([dict(g) for g in generated])
            await db.projects.update_one(
                {"id": project_id},
                {"$set": {"selected_thumbnail_asset_id": generated[0]["id"],
                          "updated_at": _now()}},
            )
        _ok("generate_thumbnails", {"briefs": len(briefs), "images": len(generated)})
    except Exception as e:  # noqa: BLE001
        return await _fail("generate_thumbnails", _classify(e), str(e))

    # --- 5. Voiceover (full-script, auto-select) ---
    try:
        style = project.get("voice_style") if project.get("voice_style") in SUPPORTED_STYLES else "narrator"
        vo = await generate_voiceover(
            text=script["full_script"],
            voice_style=style,
            project_id=project_id,
        )
        await db.assets.insert_one({**vo, "status": "selected", "created_at": _now()})
        await db.projects.update_one(
            {"id": project_id},
            {"$set": {"selected_voiceover_asset_id": vo["id"], "updated_at": _now()}},
        )
        _ok("generate_voiceover", {"duration": vo.get("duration"), "source": vo.get("source")})
    except Exception as e:  # noqa: BLE001
        return await _fail("generate_voiceover", _classify(e), str(e))

    # --- 6. Enqueue render (background worker takes over) ---
    try:
        job = await render_service.queue_render(project_id=project_id,
                                                requested_by=requested_by)
        await _mark(project_id, queue_render_job_id=job["id"])
        _ok("queue_render", {"job_id": job["id"]})
    except Exception as e:  # noqa: BLE001
        return await _fail("queue_render", _classify(e), str(e))

    return {"ok": True, "project_id": project_id, "steps": steps,
            "render_job_id": job["id"]}


async def _auto_attach(project_id: str, project: dict) -> dict:
    """Internal mirror of the /auto-attach-assets endpoint."""
    db = get_db()
    scenes = await db.scenes.find({"project_id": project_id}, {"_id": 0}).sort("scene_number", 1).to_list(500)
    if not scenes:
        return {"attached": 0, "reason": "no_scenes"}
    # Try to derive a visual tone once
    visual_tone = project.get("visual_tone") or ""
    if not visual_tone:
        try:
            from .visual_query import derive_visual_tone
            script_doc = await db.scripts.find_one({"project_id": project_id}, {"_id": 0})
            full_text = (script_doc or {}).get("full_script") or project.get("topic") or ""
            visual_tone = await derive_visual_tone(full_text)
            if visual_tone:
                await db.projects.update_one({"id": project_id},
                                             {"$set": {"visual_tone": visual_tone}})
        except Exception:  # noqa: BLE001
            visual_tone = ""

    from .visual_query import build_scene_query
    attached = 0
    failed = 0
    for scene in scenes:
        query = build_scene_query(scene)
        try:
            result = await stock_service.search_stock(
                query, "videos", per_page=8, visual_tone=visual_tone or None,
            )
            top = (result.get("results") or [None])[0]
            if not top:
                failed += 1
                continue
            await db.assets.insert_one({
                "id": top["external_id"] + "_" + scene["id"][:8],
                "project_id": project_id,
                "scene_id": scene["id"],
                "asset_type": top.get("media_type", "stock_video"),
                "source": top.get("source"),
                "external_id": top.get("external_id"),
                "title": top.get("title"),
                "preview_url": top.get("preview_url"),
                "download_url": top.get("download_url"),
                "source_url": top.get("source_url"),
                "duration": top.get("duration"),
                "width": top.get("width"),
                "height": top.get("height"),
                "query": query,
                "status": "selected",
                "created_at": _now(),
            })
            attached += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("auto-attach scene=%s failed: %s", scene.get("scene_number"), e)
            failed += 1
    return {"attached": attached, "failed": failed, "scenes": len(scenes),
            "visual_tone": visual_tone}


def _classify(exc: Exception) -> str:
    """Return a short error code suitable for queue_error."""
    msg = str(exc).lower()
    if "budget" in msg or "exceeded" in msg or "quota" in msg:
        return "llm_budget_exceeded"
    if "rate" in msg and "limit" in msg:
        return "rate_limited"
    if "elevenlabs" in msg:
        return "tts_failed"
    if "pexels" in msg:
        return "stock_failed"
    return f"{type(exc).__name__}"
