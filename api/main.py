"""FastAPI main app — agent management platform."""

import logging
import os
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

# CORS — allow frontend origins.
# NOTE: browsers reject `Access-Control-Allow-Origin: *` together with
# `Access-Control-Allow-Credentials: true`. Since the admin UI currently does
# not send cookies / auth headers, we default `allow_credentials=False` which
# lets us keep the permissive `*` wildcard. If auth is added later, replace `*`
# with an explicit origin list (or set via ADMIN_API_CORS_ORIGINS env var).
_cors_env = os.environ.get("ADMIN_API_CORS_ORIGINS", "").strip()
if _cors_env:
    _cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
    _allow_credentials = True
else:
    _cors_origins = ["*"]
    _allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(profiles_router)
app.include_router(sessions_router)
app.include_router(stats_router)
