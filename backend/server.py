"""FacelessForge backend entrypoint."""
from dotenv import load_dotenv
load_dotenv()

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.db import init_db, ensure_indexes, close_db
from app.routes import router as api_router
from app.seed import run_seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("facelessforge")


async def _seed_task():
    try:
        await run_seed()
        logger.info("Seed complete")
    except Exception as e:  # noqa: BLE001
        logger.exception("Seed failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await ensure_indexes()
    # Run seed in background so server starts immediately even if LLM is slow
    asyncio.create_task(_seed_task())
    yield
    close_db()


app = FastAPI(title="FacelessForge API", lifespan=lifespan)


@app.get("/api/health")
async def health():
    return {"ok": True, "service": "facelessforge"}


app.include_router(api_router)

cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
