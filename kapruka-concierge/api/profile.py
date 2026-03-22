"""
api/profile.py
Saves onboarding / preference data from the frontend to ProfileManager.

POST /api/profile
"""

from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from memory.semantic import ProfileManager

router = APIRouter()

_pm: Optional[ProfileManager] = None


def _get_pm() -> ProfileManager:
    global _pm
    if _pm is None:
        _pm = ProfileManager()
    return _pm


class ProfileSaveRequest(BaseModel):
    recipient:   str
    allergies:   list[str] = []
    preferences: list[str] = []
    district:    str        = ""
    budget_lkr:  Optional[float] = None


@router.post("/api/profile")
async def save_profile(body: ProfileSaveRequest) -> JSONResponse:
    pm = _get_pm()
    pm.update_profile(body.recipient, "allergies",   body.allergies)
    pm.update_profile(body.recipient, "preferences", body.preferences)
    if body.district:
        pm.update_profile(body.recipient, "district", body.district)
    if body.budget_lkr is not None:
        pm.update_profile(body.recipient, "budget_lkr", body.budget_lkr)
    return JSONResponse({"ok": True, "recipient": body.recipient})
