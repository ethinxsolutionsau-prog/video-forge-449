"""ETHINX-style automation loop around FacelessForge's existing endpoints.

`run_auto_render(project_id, user)` takes a project that already has script + scenes +
metadata + a selected thumbnail (post-scenes / post-metadata state) and drives it to a
completed MP4 by repeatedly consulting the render preflight as the single source of
truth.

At every iteration the worker:
  1. Reads preflight via `render_service.validate_prerequisites`.
  2. If `ok == true` → calls `render_service.queue_render` and returns the job.
  3. Otherwise inspects which specific checklist items are failing and runs the matching
     remediation: auto-attach stock assets, generate + auto-select a full-script
     voiceover, or fail fast with a clearly-logged blocker for items it cannot
     auto-remediate (script/scenes/metadata/thumbnail).
  4. Re-reads preflight and loops, capped at 4 iterations to prevent infinite cycles.

Every decision is logged to the `facelessforge.auto_render` logger so the path is
traceable end-to-end without enabling debug mode.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from . import render as render_service
from . import tts as tts_service
from .db import get_db
from .models import AutoAttachRequest

logger = logging.getLogger("facelessforge.auto_render")

MAX_ITERATIONS = 4


def _now():
    return datetime.now(timezone.utc)


async def _load_state(db, project_id: str) -> tuple[dict, dict, list, dict, list]:
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    script = await db.scripts.find_one({"project_id": project_id}, {"_id": 0})
    scenes = await db.scenes.find({"project_id": project_id}, {"_id": 0}).sort("scene_number", 1).to_list(500)
    metadata = await db.metadata_packages.find_one({"project_id": project_id}, {"_id": 0})
    assets = await db.assets.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    return project, script, scenes, metadata, assets


def _checklist_failures(preflight: dict) -> set[str]:
    return {item["key"] for item in (preflight.get("checklist") or []) if not item.get("ok")}


# ---------------- Remediations ----------------

async def _remediate_scene_assets(project_id: str, user: dict) -> dict:
    """Run the existing /auto-attach-assets handler in-process."""
    from .routes import auto_attach_assets  # local import to avoid cycles

    body = AutoAttachRequest(replace_existing=False, media_type="both")
    result = await auto_attach_assets(project_id=project_id, body=body, user=user)
    return {
        "attached": result.get("attached"),
        "total": result.get("total"),
        "skipped": result.get("skipped"),
        "failed": result.get("failed"),
        "mock": result.get("mock"),
    }


async def _remediate_voiceover(project_id: str) -> dict:
    """Generate a full-script voiceover and auto-select it."""
    db = get_db()
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    script = await db.scripts.find_one({"project_id": project_id}, {"_id": 0})
    if not project or not script or not script.get("full_script", "").strip():
        raise HTTPException(status_code=400, detail="Cannot generate voiceover: missing script")

    text = script["full_script"].strip()
    voice = project.get("voice_style") or "narrator"
    asset_id = str(uuid.uuid4())

    payload = await tts_service.generate_voiceover(
        text=text, voice_style=voice, project_id=project_id,
        asset_id=asset_id, scene_id=None, name_suffix="(Auto)",
    )
    payload["text_excerpt"] = text[:240]
    payload["created_at"] = _now()
    payload["updated_at"] = _now()
    payload["status"] = "selected"

    await db.assets.update_many(
        {
            "project_id": project_id,
            "asset_type": "voiceover_audio",
            "scene_id": None,
            "status": "selected",
        },
        {"$set": {"status": "generated", "updated_at": _now()}},
    )
    await db.assets.insert_one(dict(payload))

    project_set: dict[str, Any] = {
        "selected_voiceover_asset_id": asset_id,
        "updated_at": _now(),
    }
    if not payload.get("mock"):
        cost = float(payload.get("cost_estimate") or 0)
        if cost:
            project_set["estimated_cost"] = float(project.get("estimated_cost", 0)) + cost
    await db.projects.update_one({"id": project_id}, {"$set": project_set})

    return {
        "asset_id": asset_id,
        "mock": payload.get("mock"),
        "duration": payload.get("duration"),
        "provider": payload.get("provider"),
    }


# ---------------- Main loop ----------------

async def run_auto_render(project_id: str, user: dict) -> dict:
    """Drive the project to a queued render job using preflight as the gate."""
    db = get_db()
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.get("user_id") and project["user_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    if user.get("role") == "viewer":
        raise HTTPException(status_code=403, detail="Viewer cannot start renders")

    decisions: list[dict] = []
    logger.info("auto-render START project=%s requested_by=%s", project_id, user.get("id"))

    for iteration in range(1, MAX_ITERATIONS + 1):
        project, script, scenes, metadata, assets = await _load_state(db, project_id)
        preflight = render_service.validate_prerequisites(project, script, scenes, metadata, assets)
        logger.info(
            "auto-render iter=%d ok=%s issues=%s coverage=%s",
            iteration, preflight["ok"], preflight.get("issues"),
            preflight.get("scene_coverage"),
        )
        decisions.append({
            "iteration": iteration,
            "preflight_ok": preflight["ok"],
            "issues": list(preflight.get("issues") or []),
            "scene_coverage": preflight.get("scene_coverage"),
        })

        if preflight["ok"]:
            logger.info("auto-render preflight GREEN — queueing render")
            try:
                job = await render_service.queue_render(project_id, requested_by=user["id"])
            except RuntimeError as e:
                logger.warning("auto-render queue_render rejected: %s", e)
                raise HTTPException(status_code=409, detail=str(e))
            logger.info("auto-render QUEUED job=%s status=%s", job.get("id"), job.get("status"))
            return {"ok": True, "job": job, "decisions": decisions}

        failures = _checklist_failures(preflight)
        logger.info("auto-render failures=%s — choosing remediation", sorted(failures))

        # Items we cannot auto-remediate must already exist before invocation.
        hard_blockers = failures - {"voiceover", "scene_assets"}
        if hard_blockers:
            logger.warning("auto-render HARD blocker=%s — cannot continue", sorted(hard_blockers))
            raise HTTPException(status_code=400, detail={
                "message": "Auto-render aborted — required steps are not auto-remediable",
                "blockers": sorted(hard_blockers),
                "hint": "Ensure script, scenes, metadata, and a selected thumbnail exist first.",
                "decisions": decisions,
            })

        # Fix in priority order: stock first (faster), then voiceover (heavier).
        if "scene_assets" in failures:
            logger.info("auto-render remediating scene_assets")
            summary = await _remediate_scene_assets(project_id, user)
            logger.info("auto-render scene_assets summary=%s", summary)
            decisions[-1]["remediation"] = {"type": "scene_assets", "summary": summary}
            continue

        if "voiceover" in failures:
            logger.info("auto-render remediating voiceover")
            summary = await _remediate_voiceover(project_id)
            logger.info("auto-render voiceover summary=%s", summary)
            decisions[-1]["remediation"] = {"type": "voiceover", "summary": summary}
            continue

    logger.error("auto-render exhausted %d iterations", MAX_ITERATIONS)
    raise HTTPException(status_code=500, detail={
        "message": "Auto-render exhausted iteration budget",
        "decisions": decisions,
    })
