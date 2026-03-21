"""
reflection.py  (project root)
Draft → safety-reflect → revise loop for product recommendations.

generate_safe_recommendation() is a *synchronous* function — call it via
asyncio.to_thread() from the async orchestrator so it doesn't block the
event loop.

Flow
----
1. Ask the LLM to draft a product recommendation message.
2. Ask the LLM to safety-check the draft for allergens / unsuitable items.
3. If safe → return the draft.
4. If unsafe → ask the LLM to rewrite, removing the flagged items.
5. Repeat up to MAX_REFLECT_ROUNDS.

A2UI events
-----------
If an asyncio.Queue is passed as event_queue, this function enqueues
dataModelUpdate events so the frontend can show reflection progress.
Each event is a dict ready to serialise as JSONL over SSE.
"""

import asyncio
import json
import os
import time
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MAX_REFLECT_ROUNDS = 3

# ---------------------------------------------------------------------------
# OpenAI client (singleton)
# ---------------------------------------------------------------------------

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


def _model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o")


# ---------------------------------------------------------------------------
# A2UI event helpers
# ---------------------------------------------------------------------------

def _enqueue(event_queue: Optional[asyncio.Queue], event: dict) -> None:
    """Non-blocking enqueue — silently drops if queue is full or absent."""
    if event_queue is None:
        return
    try:
        event_queue.put_nowait(event)
    except asyncio.QueueFull:
        pass


def _data_model_update(surface_id: str, data: dict) -> dict:
    return {
        "type":      "dataModelUpdate",
        "surfaceId": surface_id,
        "data":      data,
    }


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_DRAFT_SYSTEM = """\
You are the Kapruka Gift Concierge recommendation writer.
Given the context below, write a warm, concise product recommendation
(2–4 sentences). Mention product names, prices in LKR, and why each
is a good fit. Do not invent products — only use what is in the context.
"""

_REFLECT_SYSTEM = """\
You are a safety reviewer for Kapruka Gift Concierge.
Check the draft recommendation below for:
  • Products that contain allergens listed in the recipient profile.
  • Products clearly unsuitable for the stated occasion or recipient.

Respond with valid JSON only — no markdown, no explanation:
{
  "safe": true | false,
  "issues": ["issue 1", "issue 2"]   // empty list if safe
}
"""

_REVISE_SYSTEM = """\
You are the Kapruka Gift Concierge recommendation writer.
The safety reviewer found the following issues with the draft:
{issues}

Rewrite the recommendation removing any flagged products and replacing
them with suitable alternatives from the product list in the context.
Keep the warm, concise style (2–4 sentences).
"""


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _draft(context: str) -> str:
    resp = _get_client().chat.completions.create(
        model    = _model(),
        messages = [
            {"role": "system", "content": _DRAFT_SYSTEM},
            {"role": "user",   "content": context},
        ],
        temperature = 0.7,
    )
    return resp.choices[0].message.content or ""


def _reflect(draft: str) -> dict:
    """Returns {"safe": bool, "issues": list[str]}."""
    resp = _get_client().chat.completions.create(
        model    = _model(),
        messages = [
            {"role": "system", "content": _REFLECT_SYSTEM},
            {"role": "user",   "content": draft},
        ],
        temperature = 0.0,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # If parsing fails, assume safe to avoid infinite loops
        return {"safe": True, "issues": []}


def _revise(context: str, draft: str, issues: list[str]) -> str:
    issues_text = "\n".join(f"- {i}" for i in issues)
    system = _REVISE_SYSTEM.format(issues=issues_text)
    resp = _get_client().chat.completions.create(
        model    = _model(),
        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": f"Context:\n{context}\n\nPrevious draft:\n{draft}"},
        ],
        temperature = 0.5,
    )
    return resp.choices[0].message.content or draft


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_safe_recommendation(
    query:         str,
    products:      list[dict],
    recipient:     Optional[str]      = None,
    allergies:     Optional[list[str]] = None,
    budget_lkr:    Optional[float]    = None,
    event_queue:   Optional[asyncio.Queue] = None,
    surface_id:    str                = "chat_surface",
) -> str:
    """
    Generate a recommendation for *products*, then safety-reflect and revise.

    Args:
        query:       Original user search query.
        products:    List of product dicts from CatalogAgent.
        recipient:   Name of the gift recipient.
        allergies:   Known allergens for the recipient.
        budget_lkr:  Budget constraint (for context only — filtering already done).
        event_queue: asyncio.Queue for A2UI dataModelUpdate events.
        surface_id:  Which surface to target in A2UI events.

    Returns:
        Final safe recommendation string.

    Note: This is a *synchronous* function. Call via asyncio.to_thread().
    """
    # Build context block
    context_lines = [f"User request: {query}"]
    if recipient:
        context_lines.append(f"Recipient: {recipient}")
    if budget_lkr:
        context_lines.append(f"Budget: LKR {budget_lkr:,.0f}")
    if allergies:
        context_lines.append(f"Allergens to avoid: {', '.join(allergies)}")

    product_summaries = []
    for p in products[:6]:   # cap to avoid bloating prompt
        name  = p.get("name", "Unknown")
        price = p.get("price")
        desc  = p.get("description", "")[:80]
        tags  = ", ".join(p.get("tags", [])[:4])
        line  = f"- {name}"
        if price:
            line += f" (LKR {price:,})"
        if desc:
            line += f": {desc}"
        if tags:
            line += f" [tags: {tags}]"
        product_summaries.append(line)

    context_lines.append("\nAvailable products:")
    context_lines.extend(product_summaries)
    context = "\n".join(context_lines)

    # Emit: starting draft
    _enqueue(event_queue, _data_model_update(surface_id, {
        "reflection_status": "drafting",
        "round": 0,
    }))

    draft = _draft(context)
    time.sleep(0.3)   # small pause — avoids hammering the API

    for round_num in range(1, MAX_REFLECT_ROUNDS + 1):
        # Emit: reflecting
        _enqueue(event_queue, _data_model_update(surface_id, {
            "reflection_status": "reflecting",
            "round": round_num,
            "draft_preview": draft[:120],
        }))

        result = _reflect(draft)
        time.sleep(0.3)

        if result.get("safe", True):
            _enqueue(event_queue, _data_model_update(surface_id, {
                "reflection_status": "approved",
                "round": round_num,
            }))
            return draft

        issues = result.get("issues", [])
        _enqueue(event_queue, _data_model_update(surface_id, {
            "reflection_status": "revising",
            "round": round_num,
            "issues": issues,
        }))

        draft = _revise(context, draft, issues)
        time.sleep(0.3)

    # Max rounds reached — return the last draft
    _enqueue(event_queue, _data_model_update(surface_id, {
        "reflection_status": "max_rounds_reached",
        "round": MAX_REFLECT_ROUNDS,
    }))
    return draft
