"""Tool registry endpoint — exposes available tool names for the admin UI."""

import logging

from fastapi import APIRouter

from agent_tools import get_available_tools

logger = logging.getLogger("api.tools")

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
def list_tools():
    tools = get_available_tools()
    logger.info("list tools: %d registered", len(tools))
    return {"tools": tools}
