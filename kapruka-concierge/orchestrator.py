"""
orchestrator.py  (project root)
KaprukaConciergeOrchestrator — async pipeline that ties all agents together.
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from dotenv import load_dotenv
from openai import OpenAI

from agents.catalog_agent import CatalogAgent, enrich_for_display
from agents.logistics_agent import LogisticsAgent
from agents.router import RouteDecision
from memory.semantic import ProfileManager
from memory.short_term import SessionManager
from router import (
    SEARCH_CATALOG, UPDATE_PREFERENCE, CHECK_LOGISTICS,
    ORDER_HISTORY, CHITCHAT, CLARIFICATION,
    classify_intent,
)
from reflection import generate_safe_recommendation

load_dotenv()


def _dm(surface_id: str, data: dict) -> dict:
    return {"type": "dataModelUpdate", "surfaceId": surface_id, "data": data}


def _br(surface_id: str) -> dict:
    return {"type": "beginRendering", "surfaceId": surface_id}


# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

_profile_manager: Optional[ProfileManager] = None
_catalog_agent:   Optional[CatalogAgent]   = None
_logistics_agent: Optional[LogisticsAgent] = None
_openai_client:   Optional[OpenAI]         = None


def _pm() -> ProfileManager:
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = ProfileManager()
    return _profile_manager


def _catalog() -> CatalogAgent:
    global _catalog_agent
    if _catalog_agent is None:
        _catalog_agent = CatalogAgent()
    return _catalog_agent


def _logistics() -> LogisticsAgent:
    global _logistics_agent
    if _logistics_agent is None:
        _logistics_agent = LogisticsAgent()
    return _logistics_agent


def _oai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


def _oai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o")


# ---------------------------------------------------------------------------
# Session registry
# ---------------------------------------------------------------------------

_sessions: dict[str, SessionManager] = {}


def _get_session(session_id: str) -> SessionManager:
    if session_id not in _sessions:
        _sessions[session_id] = SessionManager(max_turns=10)
    return _sessions[session_id]


def _map_products_to_gallery(products: list[dict]) -> dict:
    """Map up to 6 products into a products array for the A2UI ProductGallery widget."""
    return {
        "products": [
            {
                "name":   p.get("name", ""),
                "price":  p.get("price"),
                "image":  p.get("image_url", "") or (p.get("image_urls") or [""])[0],
                "rating": p.get("rating"),
                "tags":   (p.get("tags") or [])[:3],
                "url":    p.get("url", ""),
                "safe":   True,
            }
            for p in products[:6]
        ]
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class KaprukaConciergeOrchestrator:

    async def process(self, session_id: str, message: str) -> AsyncGenerator[dict, None]:
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=256)
        session = _get_session(session_id)

        session.add_turn("user", message)
        history = session.to_llm_messages()

        # Phase 1: Routing
        yield _dm("agent_surface", {"ph_r": "active", "ph_s": "idle", "ph_ref": "idle", "ph_d": "idle"})

        intent, decision = await asyncio.to_thread(classify_intent, message, history)

        yield _dm("agent_surface", {
            "ph_r":      "done",
            "route":     intent,
            "recipient": decision.recipient or "",
            "confidence":round(decision.confidence, 2),
        })

        if intent == SEARCH_CATALOG:
            async for event in self._handle_search(decision, session, queue):
                yield event
        elif intent == UPDATE_PREFERENCE:
            async for event in self._handle_preference(decision):
                yield event
        elif intent == CHECK_LOGISTICS:
            async for event in self._handle_logistics(message, decision, session):
                yield event
        elif intent == ORDER_HISTORY:
            async for event in self._handle_order_history():
                yield event
        elif intent == CHITCHAT:
            async for event in self._handle_chitchat(message, session):
                yield event
        else:
            async for event in self._handle_clarification():
                yield event

    # ------------------------------------------------------------------
    # SEARCH_CATALOG
    # ------------------------------------------------------------------

    async def _handle_search(
        self, decision: RouteDecision, session: SessionManager, queue: asyncio.Queue
    ) -> AsyncGenerator[dict, None]:
        recipient = decision.recipient
        allergies = _pm().get_allergies(recipient) if recipient else []
        budget    = decision.budget_lkr or (_pm().get_budget(recipient) if recipient else None)

        # Memory chips active
        yield _dm("memory_surface", {"sem_active": True, "lt_active": True})

        # Phase 2: Searching
        yield _dm("agent_surface", {"ph_s": "active"})

        catalog_resp = await asyncio.to_thread(
            _catalog().run,
            query           = decision.extracted_query or decision.reasoning,
            recipient       = recipient,
            profile_manager = _pm(),
            history         = session.to_llm_messages(),
            category_hint   = decision.category,
            budget_lkr      = budget,
        )

        products = catalog_resp.products

        yield _dm("agent_surface", {"ph_s": "done", "ph_ref": "active"})

        # Populate gallery
        if products:
            yield _dm("gallery_surface", _map_products_to_gallery(products))
            # Put top product on agent panel
            p0 = products[0]
            yield _dm("agent_surface", {
                "prod_name":     p0.get("name", ""),
                "prod_price":    str(int(p0["price"])) if p0.get("price") else "",
                "prod_image":    p0.get("image_url", "") or (p0.get("image_urls") or [""])[0],
                "prod_safe":     True,
                "prod_tags":     p0.get("tags", [])[:4],
                "prod_reason":   "",
                "prod_rating":   str(p0["rating"]) if p0.get("rating") else "",
                "prod_reviews":  str(p0.get("review_count") or ""),
                "prod_discount": "",
                "prod_delivery": p0.get("delivery_note", ""),
            })

        # Phase 3: Reflection
        yield _dm("agent_surface", {"rf1": "active", "rf1_active": True})

        final_message = await asyncio.to_thread(
            generate_safe_recommendation,
            query       = decision.extracted_query or decision.reasoning,
            products    = products,
            recipient   = recipient,
            allergies   = allergies,
            budget_lkr  = budget,
            event_queue = queue,
            surface_id  = "agent_surface",
        )

        # Drain reflection events
        while not queue.empty():
            yield queue.get_nowait()

        yield _dm("agent_surface", {
            "ph_ref": "done", "ph_d": "done",
            "rf1": "done", "rf2": "done", "rf3": "done",
            "prod_safe": True,
        })

        # *** KEY FIX: use "response" not "message" ***
        yield _dm("chat_surface", {"response": final_message, "thinking": False})
        yield _br("chat_surface")

        session.add_turn("assistant", final_message)

        # Deactivate memory chips
        yield _dm("memory_surface", {"sem_active": False, "lt_active": False})

    # ------------------------------------------------------------------
    # UPDATE_PREFERENCE
    # ------------------------------------------------------------------

    async def _handle_preference(self, decision: RouteDecision) -> AsyncGenerator[dict, None]:
        recipient = decision.recipient
        key       = decision.preference_key
        value     = decision.preference_value

        if not recipient or not key:
            note = "I didn't catch who the preference is for. Could you clarify?"
            yield _dm("chat_surface", {"response": note, "thinking": False})
            return

        pm = _pm()
        if key == "allergies" and isinstance(value, str):
            pm.add_allergy(recipient, value)
            note = f"Got it — noted that {recipient} is allergic to {value}."
        elif key == "budget_lkr":
            try:
                bv = float(value)
                pm.get_profile(recipient)["budget_lkr"] = bv
                pm._save()
                note = f"Budget for {recipient} updated to LKR {bv:,.0f}."
            except (TypeError, ValueError):
                note = "I couldn't parse that budget. Please use a number."
        elif key == "district":
            pm.get_profile(recipient)["district"] = str(value)
            pm._save()
            note = f"Delivery district for {recipient} set to {value}."
        else:
            prefs = pm.get_profile(recipient).setdefault("preferences", [])
            if value and str(value) not in prefs:
                prefs.append(str(value)); pm._save()
            note = f"Preference noted for {recipient}: {value}."

        yield _dm("memory_surface", {"sem_active": True})
        yield _dm("notification_surface", {"toast_text": note, "toast_visible": True})
        yield _dm("chat_surface",        {"response": note, "thinking": False})
        yield _br("chat_surface")

        await asyncio.sleep(0.1)
        yield _dm("memory_surface", {"sem_active": False})

    # ------------------------------------------------------------------
    # CHECK_LOGISTICS
    # ------------------------------------------------------------------

    async def _handle_logistics(
        self, message: str, decision: RouteDecision, session: SessionManager
    ) -> AsyncGenerator[dict, None]:
        yield _dm("agent_surface", {"ph_s": "active"})

        logistics_resp = await asyncio.to_thread(
            _logistics().run,
            message       = message,
            recipient     = decision.recipient,
            district_hint = decision.district,
            history       = session.to_llm_messages(),
        )

        yield _dm("agent_surface", {"ph_s": "done", "ph_d": "done"})

        if logistics_resp.district_matched:
            yield _dm("agent_surface", {
                "delivery_feasible": logistics_resp.feasible,
                "delivery_district": logistics_resp.district_matched,
                "delivery_days":     f"{logistics_resp.estimated_days}d" if logistics_resp.estimated_days else "",
            })

        yield _dm("chat_surface", {"response": logistics_resp.message, "thinking": False})
        yield _br("chat_surface")

        session.add_turn("assistant", logistics_resp.message)

    # ------------------------------------------------------------------
    # ORDER_HISTORY / CHITCHAT / CLARIFICATION
    # ------------------------------------------------------------------

    async def _handle_order_history(self) -> AsyncGenerator[dict, None]:
        reply = "I can't access your Kapruka purchase history directly — visit kapruka.com/myorders to see your past orders.\n\nIf you meant your recent searches in this conversation, just ask \"what did I search?\" and I'll recap them for you."
        yield _dm("agent_surface", {"ph_d": "done"})
        yield _dm("chat_surface", {"response": reply, "thinking": False})
        yield _br("chat_surface")

    async def _handle_chitchat(
        self, message: str, session: SessionManager
    ) -> AsyncGenerator[dict, None]:
        history = session.to_llm_messages()

        # Detect session-history questions and answer from short-term memory directly
        _session_keywords = (
            "recent search", "recent searches", "what did i search",
            "what have i searched", "what did i ask", "what did i look for",
            "my searches", "previous search", "search history",
        )
        if any(kw in message.lower() for kw in _session_keywords):
            import re as _re
            past_queries = []
            for t in session.get_history():
                if t["role"] != "user":
                    continue
                # Strip injected [Recipient: X] prefix added by stream.py
                content = _re.sub(r"^\[Recipient:[^\]]+\]\s*", "", t["content"]).strip()
                # Skip other session-history queries (including this one)
                if any(kw in content.lower() for kw in _session_keywords):
                    continue
                if content:
                    past_queries.append(content)
            if past_queries:
                items = "\n".join(f"  • {q}" for q in past_queries[-5:])
                reply = f"Here's what you've searched in this session:\n{items}"
            else:
                reply = "You haven't searched for anything else in this session yet. What gift can I help you find?"
            yield _dm("agent_surface", {"ph_d": "done"})
            yield _dm("memory_surface", {"st_active": True})
            yield _dm("chat_surface", {"response": reply, "thinking": False})
            yield _br("chat_surface")
            session.add_turn("assistant", reply)
            await asyncio.sleep(0.1)
            yield _dm("memory_surface", {"st_active": False})
            return

        resp_obj = await asyncio.to_thread(
            _oai().chat.completions.create,
            model    = _oai_model(),
            messages = [
                {"role": "system", "content":
                    "You are the Kapruka Gift Concierge for a Sri Lankan online gift delivery service. "
                    "Be warm, friendly, and very concise (1-2 sentences max). "
                    "If greeted, greet back and offer to help find a gift."},
                *history[-4:],
                {"role": "user", "content": message},
            ],
            temperature = 0.8,
        )
        reply = resp_obj.choices[0].message.content or "Hello! How can I help you find the perfect gift today?"
        yield _dm("agent_surface", {"ph_d": "done"})
        yield _dm("chat_surface", {"response": reply, "thinking": False})
        yield _br("chat_surface")
        session.add_turn("assistant", reply)

    async def _handle_clarification(self) -> AsyncGenerator[dict, None]:
        reply = "I'd love to help! Could you give me a bit more detail? Who's the gift for, what's the occasion, or do you have a budget in mind?"
        yield _dm("agent_surface", {"ph_d": "done"})
        yield _dm("chat_surface", {"response": reply, "thinking": False})
        yield _br("chat_surface")
