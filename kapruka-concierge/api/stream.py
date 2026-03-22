"""
api/stream.py
Server-Sent Events endpoint — streams A2UI JSONL events to the frontend.

GET /stream?session_id={id}&message={text}&recipient={name}

Protocol
--------
Each event is emitted as:
    data: {json}\n\n

The sequence for every request:
  1. Reset all surfaces (clear previous state, show thinking indicator).
  2. Iterate orchestrator.process(session_id, message) — each yielded dict
     is a complete A2UI event (surfaceUpdate / dataModelUpdate /
     beginRendering / deleteSurface).
  3. Emit a comment ": done" to signal stream end.

Session management
------------------
One KaprukaConciergeOrchestrator instance per session_id (stateless
orchestrator, so sharing is safe — sessions differ only in SessionManager
context which is managed inside the orchestrator module).
"""

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from orchestrator import KaprukaConciergeOrchestrator

router = APIRouter()

# session_id → KaprukaConciergeOrchestrator
_sessions: dict[str, KaprukaConciergeOrchestrator] = {}


def _get_orchestrator(session_id: str) -> KaprukaConciergeOrchestrator:
    if session_id not in _sessions:
        _sessions[session_id] = KaprukaConciergeOrchestrator()
    return _sessions[session_id]


# ---------------------------------------------------------------------------
# Reset events — sent before every pipeline run to clear stale UI state
# ---------------------------------------------------------------------------

def _reset_events() -> list[dict]:
    """
    Return a list of A2UI dataModelUpdate events that reset every surface
    to its 'idle / thinking' state before the new pipeline starts.
    """
    return [
        # agent_surface — clear previous route and set all phases to idle
        {
            "type":      "dataModelUpdate",
            "surfaceId": "agent_surface",
            "data": {
                "status":     "idle",
                "intent":     "",
                "recipient":  "",
                "confidence": None,
            },
        },
        # chat_surface — show thinking indicator, clear previous response
        {
            "type":      "dataModelUpdate",
            "surfaceId": "chat_surface",
            "data": {
                "thinking":       True,
                "thinking_label": "Thinking...",
                "response":       "",
            },
        },
        # gallery_surface — clear products array
        {
            "type":      "dataModelUpdate",
            "surfaceId": "gallery_surface",
            "data": {"products": []},
        },
        # notification_surface — hide toast
        {
            "type":      "dataModelUpdate",
            "surfaceId": "notification_surface",
            "data": {"toast_visible": False, "toast_text": ""},
        },
        # memory_surface — deactivate all chips
        {
            "type":      "dataModelUpdate",
            "surfaceId": "memory_surface",
            "data": {"st_active": False, "lt_active": False, "sem_active": False},
        },
    ]


# ---------------------------------------------------------------------------
# SSE generator
# ---------------------------------------------------------------------------

async def _sse_generator(
    session_id: str,
    message:    str,
    recipient:  str,
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields raw SSE-formatted strings.
    Each A2UI event → 'data: {json}\n\n'
    """
    # 1. Reset surfaces
    for event in _reset_events():
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0)   # yield control to the event loop

    # 2. Run pipeline
    orchestrator = _get_orchestrator(session_id)

    # Inject recipient into the message context if supplied
    full_message = message
    if recipient:
        # Prepend recipient hint — orchestrator/router will pick it up
        full_message = f"[Recipient: {recipient}] {message}"

    try:
        async for event in orchestrator.process(session_id, full_message):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.05)

    except Exception as exc:
        # Surface the error as a chat message rather than a broken stream
        error_event = {
            "type":      "dataModelUpdate",
            "surfaceId": "chat_surface",
            "data": {
                "thinking": False,
                "response": f"Sorry, something went wrong: {exc}",
            },
        }
        yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

    # 3. End-of-stream sentinel (SSE comment — ignored by clients)
    yield ": done\n\n"


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("/stream")
async def stream(
    session_id: str = "default",
    message:    str = "",
    recipient:  str = "",
) -> StreamingResponse:
    """
    Stream A2UI events for a single user message over SSE.

    Query params
    ------------
    session_id  Opaque identifier for the conversation session.
    message     The user's message text.
    recipient   Optional gift recipient name (e.g. "Wife").
    """
    return StreamingResponse(
        _sse_generator(session_id, message, recipient),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable Nginx buffering if present
        },
    )
