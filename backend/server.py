"""FacelessForge backend entrypoint."""
from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app.db import init_db, ensure_indexes, close_db
from app.routes import router as api_router
from app.seed import run_seed
from app.system import ensure_ffmpeg_available

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("facelessforge")


# Cached system status set at boot, exposed via /api/admin/diagnostics.
SYSTEM_STATUS: dict = {}


async def _seed_task():
    try:
        await run_seed()
        logger.info("Seed complete")
    except Exception as e:  # noqa: BLE001
        logger.exception("Seed failed: %s", e)


async def _retention_loop():
    """Periodic background cleanup of old render artifacts."""
    from app.retention import run_cleanup_once
    interval = int(os.environ.get("RENDER_RETENTION_INTERVAL_SECONDS", str(60 * 60 * 6)))
    while True:
        try:
            await run_cleanup_once()
        except Exception as e:  # noqa: BLE001
            logger.exception("Retention cleanup failed: %s", e)
        await asyncio.sleep(max(60, interval))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await ensure_indexes()
    # System checks (ffmpeg, ffprobe) — never block startup
    SYSTEM_STATUS.update(ensure_ffmpeg_available())
    # Run seed in background so server starts immediately even if LLM is slow
    asyncio.create_task(_seed_task())
    asyncio.create_task(_retention_loop())
    yield
    close_db()


app = FastAPI(title="FacelessForge API", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "facelessforge"}


app.include_router(api_router)

# Static mount for generated images. Served via /api/static/thumbs/{project_id}/{asset_id}.{ext}
# so it routes through the k8s ingress /api/* rule.
from pathlib import Path as _Path
_STATIC = _Path(__file__).parent / "static"
_STATIC.mkdir(parents=True, exist_ok=True)
app.mount("/api/static", StaticFiles(directory=str(_STATIC)), name="static")

# CORS: production locks to FRONTEND_URL; dev permits localhost + emergent preview regex.
# Wildcard "*" with credentials is unsafe AND violates the CORS spec, so we never use it.
_dev = os.environ.get("DEV_MODE", "false").lower() in ("1", "true", "yes")
_frontend = os.environ.get("FRONTEND_URL")
if _frontend:
    _allow_origins = [o.strip() for o in _frontend.split(",") if o.strip()]
elif _dev:
    # Dev fallback: allow local dev origins
    _allow_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
else:
    _allow_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

# Belt-and-braces: strip wildcard if anyone set it via env in prod
if not _dev:
    _allow_origins = [o for o in _allow_origins if o != "*"]

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_allow_origins,
    allow_origin_regex=r"https://.*\.preview\.emergentagent\.com" if _dev else None,
    allow_methods=["*"],
    allow_headers=["*"],
)
