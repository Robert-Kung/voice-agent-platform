"""Local connect-mode test agent management.

Spawns `agent.py connect --room <room> --profile <profile>` as a background
subprocess so the admin Try button can test a profile locally without competing
with the deployed Cloud agent.
"""

import asyncio
import logging
import os
import shutil
import sys
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("api.test")

router = APIRouter(prefix="/api/test", tags=["test"])

# room_name → (Process, log_file_handle)
_running: dict[str, tuple[asyncio.subprocess.Process, object]] = {}

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
    if not profile:
        raise HTTPException(status_code=400, detail="profile is required")

    room = body.room or f"test-{profile}-{uuid.uuid4().hex[:8]}"

    # Kill stale process for same room if still alive
    if room in _running:
        old_proc, old_log = _running.pop(room)
        try:
            old_proc.kill()
        except ProcessLookupError:
            pass
        try:
            old_log.close()
        except Exception:
            pass

    os.makedirs(_LOG_DIR, exist_ok=True)
    log_path = os.path.join(_LOG_DIR, f"{room}.log")
    log_file = open(log_path, "w", buffering=1)  # line-buffered

    cmd = _agent_cmd(room, profile)
    logger.info("Spawning test agent: %s  → log=%s", " ".join(cmd), log_path)

    # Force BYO Deepgram for local Try subprocess so it doesn't share the
    # LiveKit Inference STT quota with the deployed Cloud agent (the free plan
    # STT concurrency limit is shared across all projects on the account).
    # Cloud agent never sees this var → stays on inference.STT.
    child_env = {**os.environ, "AGENT_STT_PROVIDER": "deepgram"}

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=_PROJECT_ROOT,
        env=child_env,
        stdout=log_file,
        stderr=asyncio.subprocess.STDOUT,
    )
    _running[room] = (proc, log_file)
    logger.info("Test agent started: room=%s profile=%s pid=%d", room, profile, proc.pid)

    asyncio.ensure_future(_watch(room, proc, log_file))

    return StartResponse(room=room, pid=proc.pid, log_path=log_path)


@router.delete("/stop/{room}")
async def stop_test_agent(room: str):
    entry = _running.pop(room, None)
    if entry is None:
        raise HTTPException(status_code=404, detail="No running test agent for this room")
    proc, log_file = entry
    try:
        proc.kill()
        logger.info("Killed test agent for room=%s", room)
    except ProcessLookupError:
        pass
    try:
        log_file.close()
    except Exception:
        pass
    return {"ok": True}


@router.get("/running")
def list_running():
    alive = {r: p.pid for r, (p, _f) in _running.items() if p.returncode is None}
    return {"running": alive}


async def _watch(room: str, proc: asyncio.subprocess.Process, log_file):
    await proc.wait()
    _running.pop(room, None)
    try:
        log_file.close()
    except Exception:
        pass
    logger.info("Test agent exited: room=%s returncode=%s", room, proc.returncode)
