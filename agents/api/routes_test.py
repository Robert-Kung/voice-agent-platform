"""Local connect-mode test agent management.

Spawns `agent.py connect --room <room> --profile <profile>` as a background
subprocess so the admin Try button can test a profile locally without competing
with the deployed Cloud agent.
"""

import asyncio
import logging
import os
import re
import shutil
import sys
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import require_admin

logger = logging.getLogger("api.test")


def _require_test_routes_enabled() -> None:
    """Defence-in-depth gate for the subprocess-spawning test surface.

    These endpoints can fork agent.py, so we want it impossible to expose them
    by accidentally forgetting an env var. Two independent checks are required
    on top of `require_admin`:

    1. ENABLE_TEST_ROUTES must be explicitly set — otherwise we 404 (the routes
       look like they don't exist at all, which is what we want in prod).
    2. ADMIN_API_TOKEN must be configured — otherwise `require_admin` would
       silently no-op (its dev-mode bypass) and leave us unauthenticated.

    api/main.py also gates `include_router(test_router)` on ENABLE_TEST_ROUTES,
    so the router shouldn't even be mounted in prod. This is a belt for that
    suspenders — survives someone editing main.py incorrectly.
    """
    if os.environ.get("ENABLE_TEST_ROUTES", "").strip().lower() not in {"1", "true", "yes", "on"}:
        raise HTTPException(status_code=404, detail="Not found")
    if not os.environ.get("ADMIN_API_TOKEN", "").strip():
        raise HTTPException(
            status_code=503,
            detail="Test routes require ADMIN_API_TOKEN to be configured",
        )


router = APIRouter(
    prefix="/api/test",
    tags=["test"],
    # Order matters: gate first (cheap 404 / 503), then auth.
    dependencies=[Depends(_require_test_routes_enabled), Depends(require_admin)],
)

# Whitelist for room names. Rooms become log filenames and LiveKit grant
# values, so they have to be strictly path/grant-safe.
_ROOM_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Profiles are passed as argv to a subprocess (no shell), looked up by exact
# DB match, and may fall back to `PROFILES_DIR/<name>.yaml`. The only real
# attack here is path traversal in the YAML fallback, so we forbid path
# separators and `..` but allow Chinese / spaces / dots / etc. so the same
# names that work in the admin UI keep working.
_PROFILE_FORBIDDEN = ("/", "\\", "..", "\x00")
_PROFILE_MAX_LEN = 100


def _validate_profile_name(profile: str) -> None:
    if not profile or len(profile) > _PROFILE_MAX_LEN:
        raise HTTPException(status_code=400, detail="Profile name empty or too long")
    if any(token in profile for token in _PROFILE_FORBIDDEN):
        raise HTTPException(status_code=400, detail="Invalid characters in profile name")

# room_name → (Process, log_file_handle).
# All reads/writes go through `_running_lock` to serialize the start/stop/watch
# critical sections — without it, two concurrent /start calls for the same room
# would both pop the stale entry, both spawn, and the second `_running[room] =`
# would overwrite the first, leaking the first process and its log handle.
_running: dict[str, tuple[asyncio.subprocess.Process, object]] = {}
_running_lock = asyncio.Lock()

# Project root (one level up from this file)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Per-room subprocess logs land here; ./data is volume-mounted in docker-compose
# so these files are visible on the host regardless of where the API runs.
_LOG_DIR = os.path.join(_PROJECT_ROOT, "data", "test-agent-logs")


def _agent_cmd(room: str, profile: str) -> list[str]:
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "agent.py", "connect", "--room", room, "--profile", profile]
    return [sys.executable, "agent.py", "connect", "--room", room, "--profile", profile]


class StartRequest(BaseModel):
    profile: str
    room: Optional[str] = None


class StartResponse(BaseModel):
    room: str
    pid: int
    log_path: str


@router.post("/start", response_model=StartResponse)
async def start_test_agent(body: StartRequest):
    profile = body.profile.strip()
    _validate_profile_name(profile)

    # Default room uses pure UUID so the auto-generated value never carries
    # the profile name into a place that requires the strict regex (room is
    # used as a log filename and LiveKit grant — cleaner without user input).
    room = body.room or f"test-{uuid.uuid4().hex}"
    if not _ROOM_NAME_RE.match(room):
        raise HTTPException(status_code=400, detail="Invalid room name")

    os.makedirs(_LOG_DIR, exist_ok=True)
    log_path = os.path.join(_LOG_DIR, f"{room}.log")
    log_file = open(log_path, "w", buffering=1)  # line-buffered

    cmd = _agent_cmd(room, profile)
    logger.info("Spawning test agent: %s  → log=%s", " ".join(cmd), log_path)

    # Force BYO Deepgram for local Try subprocess so it doesn't share the
    # LiveKit Inference STT quota with the deployed Cloud agent (the free plan
    # STT concurrency limit is shared across all projects on the account).
    # Cloud agent never sees this var → stays on inference.STT.
    #
    # Also set AGENT_PROFILE so the LiveKit SDK-spawned child process (which
    # runs entrypoint() in a forked worker) picks up the right profile.
    # The parent subprocess has --profile in sys.argv but child processes
    # spawned by the SDK don't inherit sys.argv — they DO inherit env vars.
    child_env = {**os.environ, "AGENT_STT_PROVIDER": "deepgram", "AGENT_PROFILE": profile}

    # Hold the lock across the full pop-old → spawn-new → record sequence so
    # two concurrent /start calls for the same room can't both spawn (and
    # leak one of the resulting processes).
    async with _running_lock:
        old_entry = _running.pop(room, None)
        if old_entry is not None:
            old_proc, old_log = old_entry
            try:
                old_proc.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(old_proc.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                pass
            try:
                old_log.close()
            except Exception:
                pass

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=_PROJECT_ROOT,
                env=child_env,
                stdout=log_file,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as exc:
            try:
                log_file.close()
            except Exception:
                pass
            logger.exception("Failed to spawn test agent for room=%s", room)
            raise HTTPException(
                status_code=500, detail=f"Failed to spawn test agent: {exc}"
            ) from exc

        _running[room] = (proc, log_file)

    logger.info("Test agent started: room=%s profile=%s pid=%d", room, profile, proc.pid)

    asyncio.ensure_future(_watch(room, proc, log_file))

    return StartResponse(room=room, pid=proc.pid, log_path=log_path)


@router.delete("/stop/{room}")
async def stop_test_agent(room: str):
    if not _ROOM_NAME_RE.match(room):
        raise HTTPException(status_code=400, detail="Invalid room name")
    # Take the entry under the lock; do the actual kill/reap outside so a
    # wedged process can't block other start/stop operations.
    async with _running_lock:
        entry = _running.pop(room, None)
    if entry is None:
        raise HTTPException(status_code=404, detail="No running test agent for this room")
    proc, log_file = entry
    try:
        proc.kill()
        logger.info("Killed test agent for room=%s", room)
    except ProcessLookupError:
        pass
    # Reap the child so it doesn't linger as a zombie. Bound the wait so a
    # wedged process can't hang the request.
    try:
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except (asyncio.TimeoutError, ProcessLookupError):
        pass
    try:
        log_file.close()
    except Exception:
        pass
    return {"ok": True}


@router.get("/running")
def list_running():
    # Sync endpoint — snapshot via list() so a concurrent mutation by a watcher
    # doesn't raise RuntimeError("dictionary changed size during iteration").
    alive = {r: p.pid for r, (p, _f) in list(_running.items()) if p.returncode is None}
    return {"running": alive}


async def _watch(room: str, proc: asyncio.subprocess.Process, log_file):
    await proc.wait()
    # Only evict if the tracked entry is still *our* process. A rapid restart
    # can replace _running[room] with a fresh process before this watcher fires.
    async with _running_lock:
        current = _running.get(room)
        if current is not None and current[0] is proc:
            _running.pop(room, None)
    try:
        log_file.close()
    except Exception:
        pass
    logger.info("Test agent exited: room=%s returncode=%s", room, proc.returncode)
