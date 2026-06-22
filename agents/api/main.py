"""FastAPI main app — agent management platform."""

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.routes_deploy import router as deploy_router
from api.routes_model_defaults import router as model_defaults_router
from api.routes_profiles import router as profiles_router
from api.routes_sessions import router as sessions_router
from api.routes_stats import router as stats_router
from api.routes_test import router as test_router
from api.routes_tools import router as tools_router
from db import session_store
from db.engine import get_session_factory, init_db
from db.migrate import import_yaml_profiles

# Configure `api.*` logging explicitly so every route's logger reaches stdout
# (docker logs) regardless of uvicorn's own handler setup. Uvicorn installs its
# handlers at startup and can overshadow `logging.basicConfig`, so we attach
# a dedicated StreamHandler to the `api` logger and disable propagation.
_log_level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
_api_logger = logging.getLogger("api")
if not _api_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    _api_logger.addHandler(_handler)
_api_logger.setLevel(_log_level)
_api_logger.propagate = False

logger = _api_logger
access_logger = logging.getLogger("api.access")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialized.")

    # Import YAML profiles if profiles table is empty (first run).
    try:
        factory = get_session_factory()
        with factory() as db:
            imported = import_yaml_profiles(db)
        if imported:
            logger.info("Imported %d YAML profile(s) on startup.", imported)
    except Exception:
        logger.exception("YAML profile import failed (non-fatal)")

    # Reconcile orphan running sessions from previous agent crashes.
    # Cutoff configurable via STALE_SESSION_MAX_AGE_HOURS (default 1h).
    try:
        max_age = float(os.environ.get("STALE_SESSION_MAX_AGE_HOURS", "1.0"))
        factory = get_session_factory()
        with factory() as db:
            reconciled = session_store.mark_stale_sessions(db, max_age_hours=max_age)
        if reconciled:
            logger.warning("Reconciled %d stale running session(s) on startup.", reconciled)
    except Exception:
        logger.exception("Stale session reconciliation failed (non-fatal)")

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


@app.middleware("http")
async def _access_log_middleware(request: Request, call_next):
    """Log every request with method, path, status, duration, client IP, and a short
    request id so writes in routes_*.py can be correlated with HTTP responses.

    Health checks on /health are logged at DEBUG to avoid noise in docker logs.
    """
    rid = uuid.uuid4().hex[:8]
    request.state.request_id = rid
    start = time.perf_counter()
    client = request.client.host if request.client else "-"
    path = request.url.path
    method = request.method
    level = logging.DEBUG if path == "/health" else logging.INFO

    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        access_logger.exception(
            "[%s] %s %s from %s → EXCEPTION after %.1fms", rid, method, path, client, elapsed_ms
        )
        raise

    elapsed_ms = (time.perf_counter() - start) * 1000
    status = response.status_code
    # Upgrade 4xx/5xx to WARNING so errors stand out in docker logs.
    if status >= 500:
        level = logging.ERROR
    elif status >= 400:
        level = logging.WARNING
    access_logger.log(
        level,
        "[%s] %s %s from %s → %d in %.1fms",
        rid,
        method,
        path,
        client,
        status,
        elapsed_ms,
    )
    response.headers["X-Request-ID"] = rid
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(profiles_router)
app.include_router(sessions_router)
app.include_router(stats_router)
app.include_router(tools_router)
app.include_router(deploy_router)
app.include_router(model_defaults_router)

# Test router can spawn agent subprocesses on the API host. Only mount it when
# explicitly enabled — never in production. routes_test.py also enforces this
# at request time as a belt-and-suspenders check.
if os.environ.get("ENABLE_TEST_ROUTES", "").strip().lower() in {"1", "true", "yes", "on"}:
    app.include_router(test_router)
    logger.warning("Test router mounted (ENABLE_TEST_ROUTES is set).")
else:
    logger.info("Test router disabled. Set ENABLE_TEST_ROUTES=1 to enable.")
