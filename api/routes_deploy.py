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
    """
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


def _lk_agent_deploy() -> subprocess.CompletedProcess[str]:
    """Run `lk agent deploy --silent` with generous timeout. Raises HTTPException on failure."""
    import time as _time

    logger.info("lk agent deploy --silent: starting (timeout=900s)")
    t0 = _time.perf_counter()
    try:
        result = subprocess.run(
            [_lk_path(), "agent", "deploy", "--silent"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=900.0,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.error("lk agent deploy timed out after 15min")
        raise HTTPException(status_code=504, detail="lk agent deploy timed out (>15min)")
    except FileNotFoundError:
        logger.error("lk CLI binary not found (agent deploy)")
        raise HTTPException(status_code=503, detail="lk CLI not available")

    elapsed = _time.perf_counter() - t0
    if result.returncode != 0:
        logger.warning(
            "lk agent deploy failed (rc=%s) after %.1fs\nstderr_tail:\n%s\nstdout_tail:\n%s",
            result.returncode,
            elapsed,
            _tail(result.stderr),
            _tail(result.stdout),
        )
        raise HTTPException(
            status_code=502,
            detail=f"lk agent deploy failed: {result.stderr.strip() or result.stdout.strip()}",
        )
    logger.info("lk agent deploy ok in %.1fs\nstdout_tail:\n%s", elapsed, _tail(result.stdout))
    return result


def _lk_set_active_profile(profile_name: str) -> subprocess.CompletedProcess[str]:
    """`lk agent update-secrets --overwrite AGENT_PROFILE=<name>`. Raises on failure."""
    import time as _time

    logger.info("lk update-secrets AGENT_PROFILE=%s: starting (timeout=120s)", profile_name)
    t0 = _time.perf_counter()
    try:
        result = subprocess.run(
            [
                _lk_path(),
                "--yes",
                "agent",
                "update-secrets",
                "--overwrite",
                "--secrets",
                f"AGENT_PROFILE={profile_name}",
            ],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120.0,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.error("lk agent update-secrets timed out (AGENT_PROFILE=%s)", profile_name)
        raise HTTPException(status_code=504, detail="lk agent update-secrets timed out")
    except FileNotFoundError:
        logger.error("lk CLI binary not found (update-secrets)")
        raise HTTPException(status_code=503, detail="lk CLI not available")

    elapsed = _time.perf_counter() - t0
    if result.returncode != 0:
        logger.warning(
            "update-secrets failed (rc=%s) after %.1fs AGENT_PROFILE=%s\nstderr_tail:\n%s\nstdout_tail:\n%s",
            result.returncode,
            elapsed,
            profile_name,
            _tail(result.stderr),
            _tail(result.stdout),
        )
        raise HTTPException(
            status_code=502,
            detail=f"lk update-secrets failed: {result.stderr.strip() or result.stdout.strip()}",
        )
    logger.info(
        "lk update-secrets ok in %.1fs AGENT_PROFILE=%s", elapsed, profile_name
    )
    return result


def _deploy_single_profile(db: Session, profile_id: str) -> dict[str, Any]:
    """Export one profile's YAML → `lk agent deploy` → set AGENT_PROFILE=<name> → mark clean.

    This is the "promote this profile to active" operation: one call ships its
    latest config AND makes it the running profile.
    """
    profile = profile_store.get_profile(db, profile_id)
    if profile is None:
        logger.warning("deploy single: profile 404 id=%s", profile_id)
        raise HTTPException(status_code=404, detail="Profile not found")
    if not profile.is_active:
        logger.warning("deploy single: profile deactivated id=%s name=%s", profile_id, profile.name)
        raise HTTPException(status_code=400, detail="Profile is deactivated")

    logger.info(
        "deploy single: begin id=%s name=%s is_dirty=%s is_live=%s",
        profile.id,
        profile.name,
        profile.is_dirty,
        profile.is_live,
    )
    try:
        profile_store.export_profile_yaml(profile)
    except Exception as e:
        logger.exception("Failed to export profile %s to YAML", profile.name)
        raise HTTPException(status_code=500, detail=f"YAML export failed: {e}")

    deploy_result = _lk_agent_deploy()
    secret_result = _lk_set_active_profile(profile.name)
    profile_store.mark_profile_deployed(db, profile_id)
    profile_store.set_live_profile(db, profile_id)
    logger.info(
        "deploy single: ok name=%s (marked clean, set live)",
        profile.name,
    )

    return {
        "status": "ok",
        "mode": "single",
        "exported_profiles": [profile.name],
        "active_profile": profile.name,
        "stdout": {
            "deploy": deploy_result.stdout.strip(),
            "set_active": secret_result.stdout.strip(),
        },
    }


def _deploy_all_profiles(db: Session) -> dict[str, Any]:
    """Export every active profile → `lk agent deploy` → mark all clean.

    Does NOT change AGENT_PROFILE — this is a bulk YAML sync, not a switch.
    """
    try:
        written = profile_store.export_all_active_profiles(db)
    except Exception as e:
        logger.exception("Failed to export profiles to YAML before deploy")
        raise HTTPException(status_code=500, detail=f"YAML export failed: {e}")

    logger.info("Exported %d profiles before deploy: %s", len(written), written)
    deploy_result = _lk_agent_deploy()
    cleaned = profile_store.mark_all_profiles_clean(db)
    logger.info("deploy all: ok exported=%d cleaned=%d", len(written), cleaned)

    return {
        "status": "ok",
        "mode": "all",
        "exported_profiles": written,
        "profiles_marked_clean": cleaned,
        "stdout": {"deploy": deploy_result.stdout.strip()},
    }


@router.post("/deploy", dependencies=[Depends(require_admin)])
def deploy_agent(_body: DeployRequest | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Deploy to LiveKit Cloud.

    With profile_id: ship that profile's latest YAML + set it active (promote).
    Without profile_id: bulk-refresh all active profiles' YAML (no secret change).

    Long-running: image rebuild + upload typically takes 3–6 minutes.
    """
    body = _body or DeployRequest()
    logger.info("POST /deploy: profile_id=%s", body.profile_id)
    if body.profile_id is not None:
        return _deploy_single_profile(db, body.profile_id)
    return _deploy_all_profiles(db)


@router.post("/switch-profile", dependencies=[Depends(require_admin)])
def switch_active_profile(body: SwitchProfileRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Activate a different profile on the Cloud agent.

    Fast path (profile is clean): just flip the AGENT_PROFILE secret (~60s).
    Slow path (profile is dirty): routes into deploy(profile_id) because the
    deployed image's baked YAML is stale — deploy both ships the latest YAML
    AND sets AGENT_PROFILE in one operation.
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
        logger.info("switch-profile: %s is dirty, routing to full deploy path", profile.name)
        return _deploy_single_profile(db, body.profile_id)

    logger.info(
        "switch-profile fast path: flipping AGENT_PROFILE → %s (previously live=%s)",
        profile.name,
        profile.is_live,
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
