"""
memory/semantic.py
Recipient profile management — loads, queries, and persists profiles.json.
All writes are thread-safe via FileLock.
"""

import json
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from filelock import FileLock

load_dotenv()

_PROFILES_PATH = Path(os.getenv("PROFILES_PATH", "recipient_profiles.json"))
_LOCK_PATH     = _PROFILES_PATH.with_suffix(".lock")


def _load_profiles() -> dict:
    if not _PROFILES_PATH.exists():
        return {}
    with open(_PROFILES_PATH, encoding="utf-8") as f:
        return json.load(f)


class ProfileManager:
    def __init__(self) -> None:
        self._profiles: dict = _load_profiles()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_profile(self, recipient: str) -> dict:
        """Return the full profile dict for *recipient*, or {} if not found."""
        return dict(self._profiles.get(recipient, {}))

    def list_recipients(self) -> list[str]:
        return list(self._profiles.keys())

    def get_allergies(self, recipient: str) -> list[str]:
        return list(self._profiles.get(recipient, {}).get("allergies", []))

    def get_preferences(self, recipient: str) -> list[str]:
        return list(self._profiles.get(recipient, {}).get("preferences", []))

    def get_budget(self, recipient: str) -> Optional[float]:
        raw = self._profiles.get(recipient, {}).get("budget_lkr")
        return float(raw) if raw is not None else None

    def get_district(self, recipient: str) -> str:
        return self._profiles.get(recipient, {}).get("district", "")

    def get_order_history(self, recipient: str) -> list:
        return list(self._profiles.get(recipient, {}).get("order_history", []))

    # ------------------------------------------------------------------
    # Writes (all go through _save for consistency)
    # ------------------------------------------------------------------

    def update_profile(self, recipient: str, key: str, value: Any) -> None:
        """Set an arbitrary top-level key on a recipient's profile."""
        if recipient not in self._profiles:
            self._profiles[recipient] = {}
        self._profiles[recipient][key] = value
        self._save()

    def add_allergy(self, recipient: str, allergen: str) -> None:
        if recipient not in self._profiles:
            self._profiles[recipient] = {}
        allergies: list = self._profiles[recipient].setdefault("allergies", [])
        allergen = allergen.strip().lower()
        if allergen not in [a.lower() for a in allergies]:
            allergies.append(allergen)
            self._save()

    def add_preference(self, recipient: str, preference: str) -> None:
        if recipient not in self._profiles:
            self._profiles[recipient] = {}
        prefs: list = self._profiles[recipient].setdefault("preferences", [])
        if preference not in prefs:
            prefs.append(preference)
            self._save()

    def add_order(self, recipient: str, order: dict) -> None:
        """Append an order to the recipient's order history."""
        if recipient not in self._profiles:
            self._profiles[recipient] = {}
        history: list = self._profiles[recipient].setdefault("order_history", [])
        history.append(order)
        self._save()

    def set_budget(self, recipient: str, budget_lkr: float) -> None:
        self.update_profile(recipient, "budget_lkr", budget_lkr)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        """Thread-safe write of the full profiles dict back to disk."""
        with FileLock(str(_LOCK_PATH)):
            with open(_PROFILES_PATH, "w", encoding="utf-8") as f:
                json.dump(self._profiles, f, ensure_ascii=False, indent=2)

    def reload(self) -> None:
        """Re-read profiles from disk (if modified externally)."""
        self._profiles = _load_profiles()

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"ProfileManager(recipients={self.list_recipients()})"
