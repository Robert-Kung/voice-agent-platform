"""Tool registry endpoint — exposes available tool names for the admin UI."""

from fastapi import APIRouter

from agent_tools import get_available_tools

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
def list_tools():
    return {"tools": get_available_tools()}
