"""Make.com (or any) webhook delivery with exponential-backoff retry.

Called from the render pipeline once a job completes and the output_url has
been confirmed reachable (HTTP 200) on the public CDN. Every attempt is
appended to the render_jobs row's ``webhook_attempts`` array so the full
audit trail is queryable per job:

    [
      { "attempt": 1, "status": "success" | "failure",
        "http_status": 200,
        "error": null | "...",
        "duration_ms": 412,
        "sent_at": "2026-...Z" },
      ...
    ]

The destination URL is read from ``MAKE_WEBHOOK_URL`` (set in
/app/secrets/external_api.env). When unset, the call is a no-op.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("facelessforge.webhooks")

RETRY_DELAYS = [5, 15, 45]  # seconds between attempts (exp backoff)
REQUEST_TIMEOUT = 15.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _verify_output_live(url: str) -> tuple[bool, int]:
    """HEAD the rendered MP4 to confirm it's actually reachable on the CDN
    before notifying downstream consumers. Returns (ok, http_status)."""
    if not url:
        return False, 0
    try:
        timeout = httpx.Timeout(10.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.head(url)
            # Some CDNs return 405 on HEAD but 200 on GET-with-range
            if r.status_code == 200:
                return True, 200
            if r.status_code in (405, 403):
                async with client.stream("GET", url, headers={"Range": "bytes=0-1023"}) as g:
                    return (g.status_code in (200, 206)), g.status_code
            return False, r.status_code
    except Exception as e:  # noqa: BLE001
        logger.warning("output_url HEAD probe failed: %s", e)
        return False, 0


async def _post_once(client: httpx.AsyncClient, url: str, payload: dict,
                     *, attempt: int) -> dict:
    """Single POST attempt. Returns an audit record."""
    started = _now_iso()
    t0 = asyncio.get_event_loop().time()
    try:
        r = await client.post(url, json=payload, timeout=REQUEST_TIMEOUT,
                              headers={"User-Agent": "FacelessForge-Webhook/1.0",
                                       "Content-Type": "application/json"})
        elapsed_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
        success = 200 <= r.status_code < 300
        record = {
            "attempt": attempt,
            "status": "success" if success else "failure",
            "http_status": r.status_code,
            "error": None if success else f"non-2xx response (body: {r.text[:200]})",
            "duration_ms": elapsed_ms,
            "sent_at": started,
        }
        if success:
            logger.info("webhook attempt=%d → %d OK (%dms)", attempt, r.status_code, elapsed_ms)
        else:
            logger.warning("webhook attempt=%d → %d (%s)", attempt, r.status_code, r.text[:120])
        return record
    except Exception as e:  # noqa: BLE001
        elapsed_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
        logger.warning("webhook attempt=%d failed: %s (%dms)", attempt, e, elapsed_ms)
        return {
            "attempt": attempt,
            "status": "failure",
            "http_status": None,
            "error": f"{type(e).__name__}: {str(e)[:200]}",
            "duration_ms": elapsed_ms,
            "sent_at": started,
        }


async def deliver_render_webhook(*, job_id: str, output_url: str, title: str,
                                  topic: str, duration_seconds: int,
                                  voice_id: str, credit_cost: int,
                                  caption: str = "", project_type: str = "",
                                  brand: str = "") -> dict:
    """Deliver the render-complete webhook with 3-retry exponential backoff.

    Returns a dict suitable for storing on the render_jobs row:
        {
          "webhook_url_present": bool,
          "output_verified": bool,
          "output_verified_status": int,
          "delivered": bool,
          "attempts": [ ... ],
          "payload": { ... }
        }
    """
    webhook_url = os.environ.get("MAKE_WEBHOOK_URL", "").strip()
    payload = {
        "job_id": job_id,
        "output_url": output_url,
        "title": title or "",
        "caption": caption or "",
        "type": project_type or "",
        "brand": brand or "",
        "topic": topic or "",
        "duration_seconds": int(duration_seconds or 0),
        "voice_id": voice_id or "",
        "credit_cost": int(credit_cost or 0),
        "rendered_at": _now_iso(),
    }

    if not webhook_url:
        logger.info("webhook skipped: MAKE_WEBHOOK_URL not configured")
        return {
            "webhook_url_present": False,
            "output_verified": False,
            "output_verified_status": 0,
            "delivered": False,
            "attempts": [],
            "payload": payload,
        }

    verified, http_status = await _verify_output_live(output_url)
    if not verified:
        logger.warning("webhook aborted: output_url not reachable (status=%s url=%s)",
                       http_status, output_url[:120])
        return {
            "webhook_url_present": True,
            "output_verified": False,
            "output_verified_status": http_status,
            "delivered": False,
            "attempts": [{
                "attempt": 0,
                "status": "aborted",
                "http_status": http_status,
                "error": "output_url HEAD probe did not return 200",
                "duration_ms": 0,
                "sent_at": _now_iso(),
            }],
            "payload": payload,
        }

    attempts: list[dict] = []
    delivered = False
    async with httpx.AsyncClient() as client:
        for i in range(len(RETRY_DELAYS) + 1):  # 1 initial + 3 retries
            attempt_num = i + 1
            record = await _post_once(client, webhook_url, payload, attempt=attempt_num)
            attempts.append(record)
            if record["status"] == "success":
                delivered = True
                break
            if i < len(RETRY_DELAYS):
                delay = RETRY_DELAYS[i]
                logger.info("webhook backoff: waiting %ds before retry", delay)
                await asyncio.sleep(delay)

    return {
        "webhook_url_present": True,
        "output_verified": True,
        "output_verified_status": http_status,
        "delivered": delivered,
        "attempts": attempts,
        "payload": payload,
    }
