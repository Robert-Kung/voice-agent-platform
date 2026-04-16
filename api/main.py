"""FastAPI main app — agent management platform."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes_profiles import router as profiles_router
from api.routes_sessions import router as sessions_router
from api.routes_stats import router as stats_router
from db.engine import init_db

logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialized.")
    yield


app = FastAPI(
    title="Agent Management Platform",
    description="Profile, session, and stats management for LiveKit voice agents",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend (dev + prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(profiles_router)
app.include_router(sessions_router)
app.include_router(stats_router)
