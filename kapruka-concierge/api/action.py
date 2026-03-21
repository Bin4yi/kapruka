"""
api/action.py
Handles client-to-server A2UI userAction messages.

POST /action
Body: {
  "userAction": {
    "name": str,
    "surfaceId": str,
    "sourceComponentId": str,
    "timestamp": str,          # ISO 8601
    "context": { ... }         # resolved data bindings from the component
  }
}

Supported actions
-----------------
  send_message      — user submitted a chat message
  change_recipient  — user switched the active recipient in the UI
  select_product    — user clicked a product card

Unknown actions return 422 with {"error": "unknown_action"}.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any, Optional

router = APIRouter()


class UserAction(BaseModel):
    name:              str
    surfaceId:         str          = ""
    sourceComponentId: str          = ""
    timestamp:         str          = ""
    context:           dict[str, Any] = {}


class ActionRequest(BaseModel):
    userAction: UserAction


@router.post("/action")
async def handle_action(body: ActionRequest) -> JSONResponse:
    """
    Receive a userAction from the frontend and return an acknowledgement.

    The frontend uses the response to update its local state (e.g. set the
    active session_id or navigate to a product page) without waiting for a
    full SSE stream.
    """
    action = body.userAction

    if action.name == "send_message":
        return JSONResponse({
            "ok":        True,
            "session_id": action.context.get("session_id", "default"),
        })

    if action.name == "change_recipient":
        return JSONResponse({
            "ok":       True,
            "recipient": action.context.get("recipient", ""),
        })

    if action.name == "select_product":
        return JSONResponse({
            "ok":          True,
            "product_url": action.context.get("url", ""),
        })

    return JSONResponse({"error": "unknown_action"}, status_code=422)
