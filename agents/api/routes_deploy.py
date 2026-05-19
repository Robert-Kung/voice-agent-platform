"""LiveKit Cloud deployment endpoints.

Shells out to the `lk` CLI and parses the table output.

Read-only:
- GET /status  — `lk agent status` + `lk agent secrets` table parse
- GET /logs    — `lk agent logs` snapshot

Write (long-running):
- POST /deploy         — with profile_id: export only that profile's YAML →
                         `lk agent deploy` → set AGENT_PROFILE=<name> → mark it clean.
                         without profile_id: export all active profiles → deploy →
                         mark them all clean (no secret change).
- POST /switch-profile — if target is clean: fast `lk update-secrets` only (~60s).
                         if target is dirty: routes into /deploy(profile_id) (~5min)
                         because deploy both ships the latest YAML AND flips AGENT_PROFILE.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading
import time as _time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_db, require_admin
from db import profile_store

logger = logging.getLogger("api.deploy")

router = APIRouter(prefix="/api/deploy", tags=["deploy"])

# Run `lk` from repo root so it picks up livekit.toml.
_REPO_ROOT = Path(__file__).resolve().parent.parent

# ── Deploy progress state ────────────────────────────────────
# Prevents concurrent deploys and lets the frontend poll progress.
# The slow `lk agent deploy` runs in a background thread so HTTP requests
# return immediately (avoids Cloudflare 524 timeout on proxied deployments).

_deploy_lock = threading.Lock()   # held for the entire deploy duration
_progress_lock = threading.Lock() # protects _deploy_progress reads/writes

_deploy_progress: dict[str, Any] = {
    "is_deploying": False,
    "profile_name": None,
    "started_at": None,   # float (time.time())
    "phase": None,        # "build" | "activate" | None
    "last_result": None,  # dict with status/error set when deploy finishes
}


def _get_progress() -> dict[str, Any]:
    with _progress_lock:
        state = dict(_deploy_progress)
    elapsed = (_time.time() - state["started_at"]) if state["started_at"] else None
    return {
        "is_deploying": state["is_deploying"],
        "profile_name": state["profile_name"],
        "elapsed_s": round(elapsed, 1) if elapsed is not None else None,
        "phase": state["phase"],
        "last_result": state["last_result"],
    }


_UNSET = object()  # sentinel for "don't update this field"


def _set_progress(
    is_deploying: bool,
    profile_name: object = _UNSET,
    phase: object = _UNSET,
    started_at: object = _UNSET,
    last_result: object = _UNSET,
) -> None:
    with _progress_lock:
        _deploy_progress["is_deploying"] = is_deploying
        if profile_name is not _UNSET:
            _deploy_progress["profile_name"] = profile_name
        if phase is not _UNSET:
            _deploy_progress["phase"] = phase
        if started_at is not _UNSET:
            _deploy_progress["started_at"] = started_at
        if last_result is not _UNSET:
            _deploy_progress["last_result"] = last_result


def _lk_path() -> str:
    """Locate the `lk` CLI or raise 503."""
    path = shutil.which("lk")
    if not path:
        raise HTTPException(
            status_code=503,
            detail="lk CLI not found in PATH. Install from https://docs.livekit.io/cli/",
        )
    return path


def _tail(text: str, lines: int = 8) -> str:
    """Return last `lines` non-empty lines for compact logging."""
    kept = [ln for ln in (text or "").splitlines() if ln.strip()]
    return "\n".join(kept[-lines:])


def _run_lk(args: list[str], timeout: float = 15.0) -> str:
    """Run `lk <args>` and return stdout. Raises HTTPException on failure."""
    cmd = [_lk_path(), *args]
    logger.info("lk exec: %s (timeout=%.0fs)", " ".join(args), timeout)
    try:
        result = subprocess.run(
            cmd,
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.error("lk %s timed out after %.0fs", args, timeout)
        raise HTTPException(status_code=504, detail=f"lk {' '.join(args)} timed out")
    except FileNotFoundError:
        logger.error("lk CLI binary not found in PATH")
        raise HTTPException(status_code=503, detail="lk CLI not available")

    if result.returncode != 0:
        logger.warning(
            "lk %s failed (rc=%s)\nstderr_tail:\n%s\nstdout_tail:\n%s",
            args,
            result.returncode,
            _tail(result.stderr),
            _tail(result.stdout),
        )
        raise HTTPException(
            status_code=502,
            detail=f"lk {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}",
        )
    logger.info("lk %s ok (%d bytes stdout)", args, len(result.stdout))
    return result.stdout


# ── Table parser ────────────────────────────────────────────────
# `lk` output uses box-drawing chars: ┌ ┬ ┐ ├ ┼ ┤ └ ┴ ┘ ─ │
# Data rows start with '│'. Header and separator rows are discarded.

_DATA_ROW = re.compile(r"^\s*│(.+)│\s*$")


def _parse_lk_table(text: str) -> list[dict[str, str]]:
    """Parse an ASCII-box table into list of dicts (header-driven)."""
    rows: list[list[str]] = []
    for line in text.splitlines():
        m = _DATA_ROW.match(line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("│")]
        rows.append(cells)
    if not rows:
        return []
    headers = rows[0]
    return [dict(zip(headers, r)) for r in rows[1:] if len(r) == len(headers)]


# ── Endpoints ───────────────────────────────────────────────────


@router.get("/status")
def get_deploy_status() -> dict[str, Any]:
    """Return current Cloud agent status + configured secret names.

    Values of secrets are NEVER exposed by `lk agent secrets` (by design);
    we only surface the key names and their last-updated timestamps.

    During an active deploy, lk agent status/secrets can be very slow
    (LiveKit Cloud is busy with rollout) and cause upstream proxy timeouts.
    We skip the lk calls and return a deploying sentinel instead.
    """
    if _deploy_progress["is_deploying"]:
        logger.info("deploy/status: skipped (deploy in progress)")
        return {
            "agent": None,
            "secrets": [],
            "raw": {"status": "", "secrets": ""},
            "deploying": True,
        }
    status_out = _run_lk(["agent", "status"])
    secrets_out = _run_lk(["agent", "secrets"])

    status_rows = _parse_lk_table(status_out)
    secret_rows = _parse_lk_table(secrets_out)

    agent: dict[str, Any] | None = status_rows[0] if status_rows else None
    logger.info(
        "deploy/status: agent=%s secrets=%d",
        agent.get("ID") if agent else None,
        len(secret_rows),
    )
    return {
        "agent": agent,
        "secrets": secret_rows,
        "raw": {
            "status": status_out.strip(),
            "secrets": secrets_out.strip(),
        },
    }


@router.get("/logs")
def get_deploy_logs(
    tail: int = Query(200, ge=1, le=2000, description="Max number of recent log lines"),
    log_type: str = Query("deploy", pattern="^(deploy|build)$"),
) -> dict[str, Any]:
    """Return the last N lines of Cloud agent logs.

    `lk agent logs` streams indefinitely, so we cap with a short timeout and
    keep only the trailing `tail` lines.
    """
    logger.info("deploy/logs: log_type=%s tail=%d", log_type, tail)
    try:
        # Short timeout — enough to capture a snapshot of recent logs.
        result = subprocess.run(
            [_lk_path(), "agent", "logs", "--log-type", log_type],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=6.0,
            check=False,
        )
        stdout = result.stdout
    except subprocess.TimeoutExpired as e:
        # Expected: logs command tails forever. Take what we got.
        stdout = (e.stdout or b"").decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
    except FileNotFoundError:
        logger.error("lk CLI binary not found in PATH (deploy/logs)")
        raise HTTPException(status_code=503, detail="lk CLI not available")

    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    returned = lines[-tail:]
    logger.info(
        "deploy/logs returned %d/%d lines (log_type=%s)", len(returned), len(lines), log_type
    )
    return {"lines": returned, "log_type": log_type}


@router.get("/progress")
def get_deploy_progress() -> dict[str, Any]:
    """Return current deploy-in-progress state (non-blocking poll endpoint).

    is_deploying=True means a `lk agent deploy` is currently running.
    elapsed_s counts seconds since the deploy started.
    phase is 'build' (image build + push) or 'activate' (updating AGENT_PROFILE secret).
    """
    return _get_progress()


# ── Write operations ───────────────────────────────────────────


class DeployRequest(BaseModel):
    profile_id: str | None = Field(
        default=None,
        description=(
            "If given, export only that profile's YAML, deploy, and set AGENT_PROFILE "
            "to activate it. If omitted, export ALL active profiles and deploy (no "
            "secret change) — useful as a bulk YAML refresh."
        ),
    )


class SwitchProfileRequest(BaseModel):
    profile_id: str = Field(..., description="DB id of the profile to activate")


def _lk_agent_deploy_blocking(profile_name: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run `lk agent deploy --silent`. Caller must already hold _deploy_lock.

    Raises RuntimeError (not HTTPException) so background threads can catch it cleanly.
    """
    logger.info("lk agent deploy --silent: starting (timeout=1800s)")
    t0 = _time.perf_counter()
    try:
        lk = shutil.which("lk")
        if not lk:
            raise RuntimeError("lk CLI not found in PATH")
        result = subprocess.run(
            [lk, "agent", "deploy", "--silent"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=1800.0,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("lk agent deploy timed out (>30min)")

    elapsed = _time.perf_counter() - t0
    if result.returncode != 0:
        err_text = result.stderr.strip() or result.stdout.strip()
        combined = (result.stdout or "") + (result.stderr or "")

        # "context deadline exceeded" typically fires after a successful build while the
        # CLI waits for the build-cache layer write to LiveKit's registry.  The image
        # itself is already pushed and the agent is rolling out.  Verify via
        # `lk agent status` before treating as a hard failure.
        if "context deadline exceeded" in combined:
            logger.warning(
                "lk agent deploy exited with 'context deadline exceeded' after %.1fs — "
                "build output suggests image was pushed; verifying via lk agent status",
                elapsed,
            )
            _time.sleep(8)  # give Cloud a moment to register the new version
            try:
                lk = shutil.which("lk") or "lk"
                verify = subprocess.run(
                    [lk, "agent", "status"],
                    cwd=str(_REPO_ROOT),
                    capture_output=True, text=True, timeout=20.0, check=False,
                )
                if verify.returncode == 0 and verify.stdout.strip():
                    logger.info(
                        "lk agent status OK after 'context deadline exceeded' — "
                        "treating deploy as successful"
                    )
                    return result
            except Exception as verify_exc:
                logger.warning("lk agent status verify failed: %s", verify_exc)

        logger.warning(
            "lk agent deploy failed (rc=%s) after %.1fs\nstderr_tail:\n%s\nstdout_tail:\n%s",
            result.returncode, elapsed, _tail(result.stderr), _tail(result.stdout),
        )
        raise RuntimeError(
            f"lk agent deploy failed: {err_text}"
        )
    logger.info("lk agent deploy ok in %.1fs\nstdout_tail:\n%s", elapsed, _tail(result.stdout))
    return result


def _lk_set_active_profile_blocking(profile_name: str) -> subprocess.CompletedProcess[str]:
    """update-secrets variant that raises RuntimeError for background threads."""
    logger.info("lk update-secrets AGENT_PROFILE=%s: starting (timeout=120s)", profile_name)
    t0 = _time.perf_counter()
    lk = shutil.which("lk")
    if not lk:
        raise RuntimeError("lk CLI not found in PATH")
    try:
        result = subprocess.run(
            [lk, "--yes", "agent", "update-secrets", "--secrets", f"AGENT_PROFILE={profile_name}"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120.0,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("lk agent update-secrets timed out")

    elapsed = _time.perf_counter() - t0
    if result.returncode != 0:
        logger.warning(
            "update-secrets failed (rc=%s) after %.1fs AGENT_PROFILE=%s",
            result.returncode, elapsed, profile_name,
        )
        raise RuntimeError(
            f"lk update-secrets failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    logger.info("lk update-secrets ok in %.1fs AGENT_PROFILE=%s", elapsed, profile_name)
    return result


def _lk_set_active_profile(profile_name: str) -> subprocess.CompletedProcess[str]:
    """`lk agent update-secrets AGENT_PROFILE=<name>` — for synchronous (fast-path) calls."""
    try:
        return _lk_set_active_profile_blocking(profile_name)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _background_deploy_single(profile_id: str, profile_name: str) -> None:
    """Background thread: lk agent deploy + update-secrets + DB updates for one profile.

    Runs after the HTTP handler has already returned 202. Holds _deploy_lock for
    the full duration and releases it when done (success or failure).
    """
    from db.engine import get_engine
    from sqlalchemy.orm import Session as _Session

    try:
        _set_progress(is_deploying=True, phase="build")
        _lk_agent_deploy_blocking(profile_name=profile_name)

        _set_progress(is_deploying=True, phase="activate")
        _lk_set_active_profile_blocking(profile_name)

        with _Session(get_engine()) as bg_db:
            profile_store.mark_profile_deployed(bg_db, profile_id)
            profile_store.set_live_profile(bg_db, profile_id)

        logger.info("deploy single (bg): ok name=%s", profile_name)
        _set_progress(
            is_deploying=False,
            last_result={"status": "ok", "mode": "single", "active_profile": profile_name},
        )
    except Exception as exc:
        logger.exception("deploy single (bg): failed name=%s", profile_name)
        _set_progress(
            is_deploying=False,
            last_result={"status": "error", "error": str(exc)},
        )
    finally:
        _deploy_lock.release()


def _background_deploy_all(written: list[str]) -> None:
    """Background thread: lk agent deploy + mark all clean (bulk YAML refresh)."""
    from db.engine import get_engine
    from sqlalchemy.orm import Session as _Session

    try:
        _set_progress(is_deploying=True, phase="build")
        _lk_agent_deploy_blocking(profile_name="all")

        with _Session(get_engine()) as bg_db:
            cleaned = profile_store.mark_all_profiles_clean(bg_db)

        logger.info("deploy all (bg): ok exported=%d cleaned=%d", len(written), cleaned)
        _set_progress(
            is_deploying=False,
            last_result={"status": "ok", "mode": "all", "exported_profiles": written, "profiles_marked_clean": cleaned},
        )
    except Exception as exc:
        logger.exception("deploy all (bg): failed")
        _set_progress(
            is_deploying=False,
            last_result={"status": "error", "error": str(exc)},
        )
    finally:
        _deploy_lock.release()


def _start_async_deploy_single(db: Session, profile_id: str) -> dict[str, Any]:
    """Validate + export YAML synchronously, then fire deploy in background thread.

    Returns HTTP 202 payload immediately so the caller's HTTP connection closes
    before Cloudflare's ~100 s proxy timeout.
    """
    profile = profile_store.get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    if not profile.is_active:
        raise HTTPException(status_code=400, detail="Profile is deactivated")

    logger.info(
        "deploy single: begin id=%s name=%s is_dirty=%s is_live=%s",
        profile.id, profile.name, profile.is_dirty, profile.is_live,
    )

    # Acquire lock before spawning thread (non-blocking → 409 if busy)
    acquired = _deploy_lock.acquire(blocking=False)
    if not acquired:
        current = _get_progress()
        raise HTTPException(
            status_code=409,
            detail=f"Deploy already in progress for '{current['profile_name']}' ({current['elapsed_s'] or 0:.0f}s elapsed). Please wait.",
        )

    try:
        profile_store.export_profile_yaml(profile)
    except Exception as exc:
        _deploy_lock.release()
        logger.exception("Failed to export profile %s to YAML", profile.name)
        raise HTTPException(status_code=500, detail=f"YAML export failed: {exc}") from exc

    _set_progress(
        is_deploying=True,
        profile_name=profile.name,
        phase="build",
        started_at=_time.time(),
        last_result=None,
    )
    t = threading.Thread(
        target=_background_deploy_single,
        args=(profile_id, profile.name),
        daemon=True,
        name=f"deploy-{profile.name}",
    )
    t.start()

    return {
        "status": "accepted",
        "mode": "single",
        "exported_profiles": [profile.name],
        "active_profile": profile.name,
    }


def _start_async_deploy_all(db: Session) -> dict[str, Any]:
    """Export all active profiles synchronously, then fire deploy in background thread."""
    acquired = _deploy_lock.acquire(blocking=False)
    if not acquired:
        current = _get_progress()
        raise HTTPException(
            status_code=409,
            detail=f"Deploy already in progress for '{current['profile_name']}' ({current['elapsed_s'] or 0:.0f}s elapsed). Please wait.",
        )

    try:
        written = profile_store.export_all_active_profiles(db)
    except Exception as exc:
        _deploy_lock.release()
        raise HTTPException(status_code=500, detail=f"YAML export failed: {exc}") from exc

    logger.info("Exported %d profiles before deploy: %s", len(written), written)
    _set_progress(
        is_deploying=True,
        profile_name="all",
        phase="build",
        started_at=_time.time(),
        last_result=None,
    )
    t = threading.Thread(
        target=_background_deploy_all,
        args=(written,),
        daemon=True,
        name="deploy-all",
    )
    t.start()

    return {
        "status": "accepted",
        "mode": "all",
        "exported_profiles": written,
    }


@router.post("/deploy", dependencies=[Depends(require_admin)])
def deploy_agent(_body: DeployRequest | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Deploy to LiveKit Cloud.

    With profile_id: ship that profile's latest YAML + set it active (promote).
    Without profile_id: bulk-refresh all active profiles' YAML (no secret change).

    Returns 202 Accepted immediately; poll GET /progress for completion status.
    """
    body = _body or DeployRequest()
    logger.info("POST /deploy: profile_id=%s", body.profile_id)
    if body.profile_id is not None:
        return _start_async_deploy_single(db, body.profile_id)
    return _start_async_deploy_all(db)


@router.post("/switch-profile", dependencies=[Depends(require_admin)])
def switch_active_profile(body: SwitchProfileRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Activate a different profile on the Cloud agent.

    Fast path (profile is clean): flip the AGENT_PROFILE secret (~60s, synchronous).
    Slow path (profile is dirty): YAML export + full image deploy, returns 202
    immediately and runs in background to avoid Cloudflare 524 proxy timeout.
    Poll GET /progress for completion.
    """
    logger.info("POST /switch-profile: profile_id=%s", body.profile_id)
    profile = profile_store.get_profile(db, body.profile_id)
    if profile is None:
        logger.warning("switch-profile 404: id=%s", body.profile_id)
        raise HTTPException(status_code=404, detail="Profile not found")
    if not profile.is_active:
        logger.warning("switch-profile: profile deactivated id=%s name=%s", profile.id, profile.name)
        raise HTTPException(status_code=400, detail="Profile is deactivated")

    if profile.is_dirty:
        logger.info("switch-profile: %s is dirty, routing to async deploy path", profile.name)
        return _start_async_deploy_single(db, body.profile_id)

    logger.info(
        "switch-profile fast path: flipping AGENT_PROFILE → %s (previously live=%s)",
        profile.name, profile.is_live,
    )
    result = _lk_set_active_profile(profile.name)
    profile_store.set_live_profile(db, body.profile_id)
    logger.info("switch-profile ok: AGENT_PROFILE=%s", profile.name)
    return {
        "status": "ok",
        "mode": "secret-only",
        "active_profile": profile.name,
        "stdout": result.stdout.strip(),
    }
