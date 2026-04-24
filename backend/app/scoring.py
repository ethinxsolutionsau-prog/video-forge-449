"""Quality scoring, status transitions, export helpers."""
from typing import Optional


STATUSES = [
    "DRAFT",
    "SCRIPT_GENERATED",
    "SCENES_GENERATED",
    "METADATA_GENERATED",
    "ASSETS_READY",
    "READY_TO_RENDER",
    "COMPLETED",
    "FAILED",
]


def quality_score(*, project: dict, script: Optional[dict], scenes: list,
                  metadata: Optional[dict], render_job: Optional[dict]) -> int:
    s = 0
    if script and script.get("full_script"):
        s += 20
    if script and script.get("hook_option_one") and script.get("hook_option_two") and script.get("hook_option_three"):
        s += 10
    if scenes and len(scenes) > 0:
        s += 20
    if metadata:
        s += 15
    if metadata and len(metadata.get("title_options") or []) >= 10:
        s += 10
    if scenes and all(sc.get("caption_text") for sc in scenes):
        s += 10
    if script and script.get("cta_block"):
        s += 5
    if 30 <= int(project.get("target_duration", 0)) <= 3600:
        s += 5
    if not (render_job and render_job.get("status") == "FAILED"):
        s += 5
    return min(s, 100)


def quality_label(score: int) -> str:
    if score <= 39:
        return "Poor"
    if score <= 69:
        return "Needs Work"
    if score <= 89:
        return "Good"
    return "Publish Ready"


def compute_project_status(*, has_script: bool, has_scenes: bool, has_metadata: bool,
                           has_assets: bool, render_status: Optional[str]) -> str:
    if render_status == "COMPLETED":
        return "COMPLETED"
    if render_status == "FAILED":
        return "FAILED"
    if has_script and has_scenes and has_metadata and has_assets:
        return "READY_TO_RENDER"
    if has_script and has_scenes and has_metadata:
        return "ASSETS_READY" if has_assets else "METADATA_GENERATED"
    if has_script and has_scenes:
        return "SCENES_GENERATED"
    if has_script:
        return "SCRIPT_GENERATED"
    return "DRAFT"


def scenes_to_csv(scenes: list) -> str:
    lines = ["scene_number,start_time,end_time,narration,visual_direction,asset_type,search_terms,caption,status"]
    for sc in sorted(scenes, key=lambda x: x["scene_number"]):
        search = ";".join(sc.get("search_terms") or [])
        def esc(v): return '"' + str(v).replace('"', '""') + '"'
        lines.append(",".join([
            str(sc["scene_number"]), str(sc["start_time"]), str(sc["end_time"]),
            esc(sc.get("narration_text", "")),
            esc(sc.get("visual_direction", "")),
            esc(sc.get("asset_type", "")),
            esc(search),
            esc(sc.get("caption_text", "")),
            esc(sc.get("status", "")),
        ]))
    return "\n".join(lines)
