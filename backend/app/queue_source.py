"""Google Sheets queue fetcher.

Reads a published Google Sheets CSV (anyone-with-link → publish to web → CSV)
and returns the next row whose ``status`` column is ``pending``.

Why not the gspread/Google API? The CSV-publish endpoint is rate-limit-friendly,
unauthenticated, and works without OAuth — perfect for read-only queue polling.
Writes back to the sheet (marking a row as ``processing``/``done``) happen via
the Make.com webhook the user already has, NOT from this code.
"""
from __future__ import annotations

import csv
import io
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger("facelessforge.queue")


def _csv_url() -> str:
    return os.environ.get("GOOGLE_SHEET_CSV_URL", "").strip()


async def fetch_pending_rows(*, max_rows: int = 50) -> list[dict]:
    """Return every pending row as a normalised dict. Empty list on any failure.

    Uses the stdlib ``csv`` module so quoted commas inside cells are handled
    correctly (naive ``split(",")`` corrupts any row that has a comma in a
    title or caption).
    """
    url = _csv_url()
    if not url:
        return []
    try:
        timeout = httpx.Timeout(15.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code != 200:
                logger.warning("queue sheet returned HTTP %d for %s", r.status_code, url[:80])
                return []
            text = r.text
    except Exception as e:  # noqa: BLE001
        logger.warning("queue sheet fetch failed: %s", e)
        return []

    if not text.strip():
        return []

    reader = csv.DictReader(io.StringIO(text))
    pending: list[dict] = []
    for raw in reader:
        # Normalise keys (lowercase, strip whitespace)
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        status = row.get("status", "").lower()
        if status != "pending":
            continue
        pending.append(_normalise_row(row))
        if len(pending) >= max_rows:
            break
    return pending


async def fetch_next_pending() -> Optional[dict]:
    """Return the first pending row, or ``None`` if none."""
    rows = await fetch_pending_rows(max_rows=1)
    return rows[0] if rows else None


def _normalise_row(row: dict) -> dict:
    """Map raw CSV columns to the canonical queue-item shape.

    The Make.com sheet schema is ``id,type,topic,brand_name,status`` plus
    optional ``voice_style``, ``niche``, ``platform``, ``target_duration``
    so the user can override any project field directly from the sheet.
    """
    def _i(v: str, default: int) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    return {
        "queue_id": row.get("id") or "",
        "queue_type": row.get("type") or "",
        "queue_brand": row.get("brand_name") or row.get("brand") or "",
        "topic": row.get("topic") or "",
        # Optional overrides (only used if sheet provides them)
        "niche": row.get("niche") or "",
        "voice_style": row.get("voice_style") or "",
        "platform": row.get("platform") or "",
        "target_duration": _i(row.get("target_duration", ""), 0),
        "tone": row.get("tone") or "",
        "audience": row.get("audience") or "",
        "raw": row,
    }
