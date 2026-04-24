"""LLM-based generation with deterministic fallback.

Produces structured JSON outputs for:
  - Script (3 hooks + selected + full script + retention beats + CTA)
  - Scene plan (list of scenes with timing)
  - Metadata package (titles, description, tags, hashtags, chapters, pinned comment)
  - Thumbnail concepts (3 briefs)

If the LLM fails or EMERGENT_LLM_KEY is missing, falls back to deterministic generation
so the app stays usable in any environment.
"""
from __future__ import annotations

import os
import json
import re
import uuid
import random
from typing import Optional


def _llm_available() -> bool:
    return bool(os.environ.get("EMERGENT_LLM_KEY"))


async def _llm_json(system: str, user: str, session_id: str) -> Optional[dict]:
    """Call the LLM and parse a JSON object from its response."""
    if not _llm_available():
        return None
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=os.environ["EMERGENT_LLM_KEY"],
            session_id=session_id,
            system_message=system,
        ).with_model(
            os.environ.get("LLM_PROVIDER", "openai"),
            os.environ.get("LLM_MODEL", "gpt-5.2"),
        )
        resp = await chat.send_message(UserMessage(text=user))
        if not resp:
            return None
        text = resp.strip()
        # Strip markdown code fence if present
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*", "", text).rstrip("`").strip()
        # Extract first {...} block
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        return json.loads(m.group(0))
    except Exception as e:  # noqa: BLE001
        print(f"[llm] generation failed, using fallback: {e}")
        return None


# ------------------------------ SCRIPT ------------------------------

SCRIPT_SYSTEM = (
    "You are a senior YouTube scriptwriter specialised in faceless, high-retention videos. "
    "Always respond with strict JSON, no commentary. All text in English."
)


async def generate_script(project: dict) -> dict:
    target_dur = int(project.get("target_duration", 300))
    # Roughly 150 wpm narration
    target_words = max(120, int(target_dur / 60 * 150))

    user = f"""Generate a faceless YouTube script as JSON with this exact shape:
{{
  "hook_option_one": "...",
  "hook_option_two": "...",
  "hook_option_three": "...",
  "selected_hook": "...",
  "full_script": "...",
  "retention_beats": ["...","...","..."],
  "cta_block": "..."
}}

Constraints:
- Niche: {project['niche']}
- Topic: {project['topic']}
- Audience: {project['audience']}
- Tone: {project['tone']}
- Target duration: {target_dur}s (~{target_words} words)
- CTA goal: {project.get('cta_goal','subscribe')}
- Monetisation intent: {project.get('monetisation_intent','ads + affiliate')}
- 3 distinct hooks (<= 2 sentences each, max retention opening)
- full_script: continuous narration paragraphs separated by blank lines, no speaker labels
- retention_beats: list of 4-8 pattern interrupts (one sentence each) spaced ~30-45s
- cta_block: 2-3 sentences asking the viewer to take the CTA goal action
- DO NOT use emojis."""

    data = await _llm_json(SCRIPT_SYSTEM, user, f"script-{project['id']}")
    if not data:
        data = _fallback_script(project, target_words)

    full = data.get("full_script", "")
    word_count = len(re.findall(r"\b\w+\b", full))
    estimated = int(word_count / 2.5)  # ~150 wpm -> 2.5 wps
    return {
        "hook_option_one": data.get("hook_option_one", "").strip(),
        "hook_option_two": data.get("hook_option_two", "").strip(),
        "hook_option_three": data.get("hook_option_three", "").strip(),
        "selected_hook": (data.get("selected_hook") or data.get("hook_option_one", "")).strip(),
        "full_script": full.strip(),
        "retention_beats": [str(x) for x in (data.get("retention_beats") or [])][:10],
        "cta_block": data.get("cta_block", "").strip(),
        "word_count": word_count,
        "estimated_duration": estimated,
    }


def _fallback_script(project: dict, target_words: int) -> dict:
    n = project["niche"]; t = project["topic"]; a = project["audience"]
    tone = project["tone"]; cta = project.get("cta_goal", "subscribe")

    hook1 = f"What if everything you thought you knew about {t.lower()} was wrong?"
    hook2 = f"In the next {max(1, project['target_duration'] // 60)} minutes, you'll learn the one thing about {t.lower()} nobody tells {a.lower()}."
    hook3 = f"Three years ago, a quiet corner of {n} changed forever because of {t.lower()}. Here's what happened."

    para_bank = [
        f"Most people never stop to ask where this actually began. But for anyone inside {n}, the signal was obvious.",
        f"The key detail is simple: the system rewards consistency, and {t} is the clearest example of that in action right now.",
        f"Here's why this matters for {a}: the rules have shifted, and the old playbook is losing leverage fast.",
        f"If you want the {tone.lower()} version, it's this: follow the pattern, ignore the noise, and keep shipping.",
        f"This is the part most creators miss. The opportunity isn't in the spike, it's in the compounding edge.",
        f"The takeaway is direct. If you're serious about {n}, this is the exact frame to use from now on.",
    ]
    # Build a script long enough
    script_chunks = [hook1]
    i = 0
    while sum(len(c.split()) for c in script_chunks) < target_words:
        script_chunks.append(para_bank[i % len(para_bank)])
        i += 1
    full_script = "\n\n".join(script_chunks)

    return {
        "hook_option_one": hook1,
        "hook_option_two": hook2,
        "hook_option_three": hook3,
        "selected_hook": hook1,
        "full_script": full_script,
        "retention_beats": [
            "Pattern interrupt: surprising statistic",
            "Pattern interrupt: quick contrast shot",
            "Pattern interrupt: direct question to viewer",
            "Pattern interrupt: open loop for next section",
            "Pattern interrupt: rapid montage beat",
        ],
        "cta_block": (
            f"If this was useful, {cta} so you don't miss the next one. "
            f"The next video goes even deeper on {t.lower()}, and you don't want to watch everyone else first."
        ),
    }


# ------------------------------ SCENES ------------------------------

SCENES_SYSTEM = (
    "You are a video director planning timestamped scenes for a faceless YouTube video. "
    "Return strict JSON only."
)


async def generate_scenes(project: dict, script_text: str) -> list[dict]:
    target_dur = int(project.get("target_duration", 300))
    scene_count = max(6, min(18, target_dur // 25))

    user = f"""Break this narration into {scene_count} timestamped scenes covering 0..{target_dur}s.
Return JSON: {{"scenes": [ {{ "scene_number": 1, "start_time": 0, "end_time": 20, "narration_text": "...", "visual_direction": "...", "asset_type": "b_roll|stock_footage|motion_graphic|archival|text_card", "search_terms": ["..."], "image_prompt": "...", "caption_text": "..." }} ]}}
Visual style: {project.get('visual_style','cinematic b-roll')}
Niche: {project['niche']}
Topic: {project['topic']}

Script:
---
{script_text[:6000]}
---

Rules:
- Scenes are contiguous, no gaps, no overlap
- caption_text = short viewer-facing caption (<= 12 words)
- search_terms: 3-5 concrete stock footage queries
- image_prompt: one sentence describing a still for this scene"""

    data = await _llm_json(SCENES_SYSTEM, user, f"scenes-{project['id']}")
    if data and isinstance(data.get("scenes"), list) and data["scenes"]:
        scenes = data["scenes"]
    else:
        scenes = _fallback_scenes(project, script_text, scene_count)

    # Normalise
    out = []
    for idx, sc in enumerate(scenes, start=1):
        out.append({
            "id": str(uuid.uuid4()),
            "scene_number": int(sc.get("scene_number", idx)),
            "start_time": int(sc.get("start_time", (idx - 1) * (target_dur // scene_count))),
            "end_time": int(sc.get("end_time", idx * (target_dur // scene_count))),
            "narration_text": str(sc.get("narration_text", "")).strip(),
            "visual_direction": str(sc.get("visual_direction", "")).strip(),
            "asset_type": str(sc.get("asset_type", "b_roll")).strip(),
            "search_terms": list(sc.get("search_terms") or [])[:6],
            "image_prompt": str(sc.get("image_prompt", "")).strip(),
            "caption_text": str(sc.get("caption_text", "")).strip(),
            "status": "planned",
        })
    return out


def _fallback_scenes(project: dict, script_text: str, scene_count: int) -> list[dict]:
    target_dur = int(project.get("target_duration", 300))
    step = max(1, target_dur // scene_count)
    paragraphs = [p.strip() for p in script_text.split("\n\n") if p.strip()]
    scenes = []
    for i in range(scene_count):
        narr = paragraphs[i % len(paragraphs)] if paragraphs else f"Scene {i+1} narration for {project['topic']}."
        caption = narr.split(".")[0][:80]
        scenes.append({
            "scene_number": i + 1,
            "start_time": i * step,
            "end_time": min(target_dur, (i + 1) * step),
            "narration_text": narr,
            "visual_direction": f"Cinematic b-roll illustrating {project['topic'].lower()} with slow push-in",
            "asset_type": random.choice(["b_roll", "stock_footage", "motion_graphic", "text_card"]),
            "search_terms": [project["niche"], project["topic"], f"{project['niche']} b-roll", "macro detail"],
            "image_prompt": f"Cinematic still, {project.get('visual_style','moody')}, depicting {project['topic'].lower()}, 16:9",
            "caption_text": caption,
        })
    return scenes


# ------------------------------ METADATA ------------------------------

META_SYSTEM = (
    "You are a YouTube SEO strategist. Output strict JSON only, optimised for CTR and retention."
)


async def generate_metadata(project: dict, script_text: str, scenes: list[dict]) -> dict:
    chapter_hint = "\n".join(f"- {sc['start_time']}s: {sc.get('caption_text') or sc.get('narration_text','')[:60]}" for sc in scenes[:12])
    user = f"""Create a YouTube metadata package as JSON:
{{
  "title_options": ["10 distinct clickable titles"],
  "selected_title": "best of those 10",
  "description": "SEO-optimised description with timestamps and affiliate disclaimer line",
  "tags": ["20-30 tags"],
  "hashtags": ["3-5 hashtags with # prefix"],
  "chapters": [{{"timestamp": "0:00", "title": "Intro"}}, ...],
  "pinned_comment": "short engaging comment to pin"
}}

Niche: {project['niche']}
Topic: {project['topic']}
Audience: {project['audience']}
Tone: {project['tone']}
CTA goal: {project.get('cta_goal','subscribe')}

Scene chapter hints:
{chapter_hint}
"""
    data = await _llm_json(META_SYSTEM, user, f"meta-{project['id']}")
    if not data:
        data = _fallback_metadata(project, scenes)

    titles = [t for t in (data.get("title_options") or []) if t][:14]
    while len(titles) < 10:
        titles.append(f"{project['topic']} — {project['niche']} deep dive #{len(titles)+1}")
    tags = [t.strip().lstrip("#") for t in (data.get("tags") or []) if t][:35]
    hashtags = [h if h.startswith("#") else f"#{h.lstrip('#')}" for h in (data.get("hashtags") or []) if h][:8]
    chapters = data.get("chapters") or []
    # Normalise chapters
    norm_chapters = []
    for ch in chapters:
        if isinstance(ch, dict) and ch.get("title"):
            norm_chapters.append({"timestamp": str(ch.get("timestamp", "0:00")), "title": str(ch["title"])})
    if not norm_chapters:
        for sc in scenes[:8]:
            mm = sc["start_time"] // 60
            ss = sc["start_time"] % 60
            norm_chapters.append({"timestamp": f"{mm}:{ss:02d}", "title": (sc.get("caption_text") or f"Part {sc['scene_number']}")[:50]})

    return {
        "title_options": titles[:12],
        "selected_title": (data.get("selected_title") or titles[0]),
        "description": (data.get("description") or "").strip(),
        "tags": tags,
        "hashtags": hashtags,
        "chapters": norm_chapters,
        "pinned_comment": (data.get("pinned_comment") or "").strip(),
    }


def _fallback_metadata(project: dict, scenes: list[dict]) -> dict:
    t = project["topic"]; n = project["niche"]; a = project["audience"]
    titles = [
        f"The Untold Truth About {t}",
        f"Why {t} Is Quietly Changing {n}",
        f"{t}: What Nobody Tells {a}",
        f"I Studied {t} For 30 Days — Here's What I Found",
        f"The {t} Playbook (2026 Edition)",
        f"{t} Explained In Under {max(3, project['target_duration']//60)} Minutes",
        f"Stop Ignoring {t} — Here's Why",
        f"The Hidden Side Of {t} In {n}",
        f"{t}: The One Framework That Actually Works",
        f"Everything Wrong With {t} (And How To Fix It)",
    ]
    description = (
        f"In this video we break down {t} for {a} — what it is, why it matters, "
        f"and exactly how to use it inside {n}.\n\n"
        "Chapters below. Full script, research notes, and resources linked.\n\n"
        "Disclosure: some links may be affiliate. We only recommend things we'd use ourselves."
    )
    tags = [n, t, f"{n} tutorial", f"{t} explained", "faceless youtube", "2026"] + [w for w in t.split()][:10]
    hashtags = [f"#{n.replace(' ','')}", f"#{t.replace(' ','')[:20]}", "#FacelessYouTube"]
    chapters = []
    for sc in scenes[:8]:
        mm = sc["start_time"] // 60
        ss = sc["start_time"] % 60
        chapters.append({"timestamp": f"{mm}:{ss:02d}", "title": (sc.get("caption_text") or f"Part {sc['scene_number']}")[:50]})
    return {
        "title_options": titles,
        "selected_title": titles[0],
        "description": description,
        "tags": tags,
        "hashtags": hashtags,
        "chapters": chapters,
        "pinned_comment": f"If you're new here and you care about {n.lower()}, start with this one. What should I break down next?",
    }


# ------------------------------ THUMBNAILS ------------------------------

THUMB_SYSTEM = "You are a YouTube thumbnail director. Output strict JSON only."


async def generate_thumbnails(project: dict) -> list[dict]:
    user = f"""Create 3 distinct faceless-YouTube thumbnail concepts as JSON:
{{"concepts": [{{"thumbnail_title_text":"<=5 words","visual_composition":"...","emotion_angle":"...","background_idea":"...","subject_focal_point":"...","colour_direction":"...","click_trigger":"...","image_prompt":"..."}}]}}
Niche: {project['niche']}
Topic: {project['topic']}
Visual style: {project.get('visual_style','cinematic')}
Tone: {project['tone']}"""
    data = await _llm_json(THUMB_SYSTEM, user, f"thumb-{project['id']}")
    concepts = (data or {}).get("concepts") or []
    if not concepts:
        concepts = _fallback_thumbnails(project)
    out = []
    for c in concepts[:3]:
        out.append({
            "thumbnail_title_text": str(c.get("thumbnail_title_text", "")),
            "visual_composition": str(c.get("visual_composition", "")),
            "emotion_angle": str(c.get("emotion_angle", "")),
            "background_idea": str(c.get("background_idea", "")),
            "subject_focal_point": str(c.get("subject_focal_point", "")),
            "colour_direction": str(c.get("colour_direction", "")),
            "click_trigger": str(c.get("click_trigger", "")),
            "image_prompt": str(c.get("image_prompt", "")),
        })
    while len(out) < 3:
        out.append(_fallback_thumbnails(project)[len(out)])
    return out


def _fallback_thumbnails(project: dict) -> list[dict]:
    t = project["topic"]; n = project["niche"]
    base = [
        {
            "thumbnail_title_text": f"{t.upper()[:20]}?",
            "visual_composition": "Rule of thirds, subject on left, bold text right, 16:9",
            "emotion_angle": "Curious shock",
            "background_idea": f"High-contrast close-up relating to {n.lower()}, slight vignette",
            "subject_focal_point": f"Iconic symbol of {t.lower()}",
            "colour_direction": "Matte black + electric cyan accent + signal green pop",
            "click_trigger": "Contradiction — implies common belief is wrong",
            "image_prompt": f"Cinematic dark still, matte black background, neon cyan accent light on a symbol representing {t.lower()}, 16:9, ultra-sharp, moody",
        },
        {
            "thumbnail_title_text": f"DON'T MISS THIS",
            "visual_composition": "Center-framed subject, big serif text above",
            "emotion_angle": "Urgency",
            "background_idea": f"Dark cinematic room with red rim light tied to {n.lower()}",
            "subject_focal_point": f"Key object from {t.lower()}",
            "colour_direction": "Black + blood red + paper white",
            "click_trigger": "FOMO",
            "image_prompt": f"Moody cinematic still of {t.lower()} subject, red rim light, shallow depth of field, 16:9",
        },
        {
            "thumbnail_title_text": f"{n.upper()[:16]} SHIFT",
            "visual_composition": "Split composition — before/after halves",
            "emotion_angle": "Revelation",
            "background_idea": "Gradient-free split: left half desaturated, right half neon-lit",
            "subject_focal_point": f"Transformation of {t.lower()}",
            "colour_direction": "Grayscale left, deep purple + cyan right",
            "click_trigger": "Transformation bias",
            "image_prompt": f"Split-frame photo, left desaturated, right neon purple and cyan, subject is {t.lower()}, 16:9, photoreal",
        },
    ]
    return base
