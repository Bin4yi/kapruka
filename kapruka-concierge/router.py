"""
router.py  (project root)
Thin orchestration wrapper around agents.router.Router.

classify_intent(message, history) -> one of:
    SEARCH_CATALOG | UPDATE_PREFERENCE | CHECK_LOGISTICS |
    ORDER_HISTORY  | CHITCHAT         | CLARIFICATION

Also logs every classification to metrics.csv.
"""

import csv
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from agents.router import Router, RouteDecision

load_dotenv()

# ---------------------------------------------------------------------------
# Intent constants
# ---------------------------------------------------------------------------

SEARCH_CATALOG   = "SEARCH_CATALOG"
UPDATE_PREFERENCE = "UPDATE_PREFERENCE"
CHECK_LOGISTICS  = "CHECK_LOGISTICS"
ORDER_HISTORY    = "ORDER_HISTORY"
CHITCHAT         = "CHITCHAT"
CLARIFICATION    = "CLARIFICATION"

_INTENT_MAP = {
    "search":           SEARCH_CATALOG,
    "preference_update": UPDATE_PREFERENCE,
    "delivery_check":   CHECK_LOGISTICS,
    "order_history":    ORDER_HISTORY,
    "chitchat":         CHITCHAT,
    "clarification":    CLARIFICATION,
}

# ---------------------------------------------------------------------------
# Metrics logging
# ---------------------------------------------------------------------------

_METRICS_PATH = Path(os.getenv("METRICS_PATH", "metrics.csv"))
_METRICS_HEADER = [
    "timestamp_utc", "intent", "confidence", "recipient",
    "category", "budget_lkr", "district", "latency_ms",
]


def _log_metric(decision: RouteDecision, latency_ms: float) -> None:
    write_header = not _METRICS_PATH.exists()
    try:
        _METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _METRICS_PATH.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_METRICS_HEADER)
            if write_header:
                writer.writeheader()
            writer.writerow({
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "intent":        _INTENT_MAP.get(decision.intent, decision.intent),
                "confidence":    round(decision.confidence, 4),
                "recipient":     decision.recipient or "",
                "category":      decision.category or "",
                "budget_lkr":    decision.budget_lkr or "",
                "district":      decision.district or "",
                "latency_ms":    round(latency_ms, 1),
            })
    except Exception:
        pass   # never crash the pipeline because of metrics


# ---------------------------------------------------------------------------
# Module-level Router singleton
# ---------------------------------------------------------------------------

_router: Optional[Router] = None


def _get_router() -> Router:
    global _router
    if _router is None:
        _router = Router()
    return _router


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_intent(
    message: str,
    history: Optional[list[dict]] = None,
) -> tuple[str, RouteDecision]:
    """
    Classify *message* and return (intent_constant, RouteDecision).

    intent_constant is one of the module-level constants:
        SEARCH_CATALOG, UPDATE_PREFERENCE, CHECK_LOGISTICS,
        ORDER_HISTORY, CHITCHAT, CLARIFICATION

    RouteDecision carries all extracted entities (recipient, category,
    budget_lkr, district, extracted_query, preference_key, preference_value).
    """
    t0 = time.monotonic()
    decision = _get_router().classify(message, history=history)
    latency_ms = (time.monotonic() - t0) * 1000

    _log_metric(decision, latency_ms)

    intent_const = _INTENT_MAP.get(decision.intent, CLARIFICATION)
    return intent_const, decision
