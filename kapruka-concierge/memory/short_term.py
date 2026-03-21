"""
memory/short_term.py
In-memory conversation history for one agent session.
"""

from datetime import datetime, timezone
from typing import Optional


class SessionManager:
    def __init__(self, max_turns: int = 10) -> None:
        self._max_turns = max_turns
        self._turns: list[dict] = []

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_turn(self, role: str, content: str) -> None:
        """Append a turn and drop the oldest if over max_turns."""
        self._turns.append({
            "role":      role,
            "content":   content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(self._turns) > self._max_turns:
            self._turns.pop(0)

    def clear(self) -> None:
        self._turns.clear()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_history(self) -> list[dict]:
        """Full turn list including timestamps."""
        return list(self._turns)

    def get_context_window(self, n: int = 5) -> list[dict]:
        """Most recent n turns."""
        return list(self._turns[-n:])

    def to_llm_messages(self) -> list[dict]:
        """
        Strip timestamps — returns [{role, content}] ready for the
        OpenAI chat completions API (messages parameter).
        """
        return [{"role": t["role"], "content": t["content"]} for t in self._turns]

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._turns)

    def __repr__(self) -> str:
        return f"SessionManager(turns={len(self._turns)}, max={self._max_turns})"
