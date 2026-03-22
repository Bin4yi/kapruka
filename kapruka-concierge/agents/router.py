"""
agents/router.py
Intent router — classifies every user message before dispatching to a specialist.
Pure Python. No frameworks. Uses OpenAI function-calling to force structured output.

Intents:
  search            — wants product recommendations
  preference_update — updating allergies / preferences / budget
  delivery_check    — asking about delivery to a district
  order_history     — asking about past orders
  chitchat          — greetings, thanks, off-topic
  clarification     — too ambiguous to route without a follow-up question
"""

import json
import os
from dataclasses import dataclass, field
from typing import Literal, Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

IntentType = Literal[
    "search",
    "preference_update",
    "delivery_check",
    "order_history",
    "chitchat",
    "clarification",
]

# ---------------------------------------------------------------------------
# OpenAI tool definition — forces structured JSON output via function-calling
# ---------------------------------------------------------------------------
_CLASSIFY_TOOL = {
    "type": "function",
    "function": {
        "name": "classify_intent",
        "description": (
            "Classify the user message intent and extract all relevant entities "
            "for a Sri Lankan gift delivery concierge."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": [
                        "search", "preference_update", "delivery_check",
                        "order_history", "chitchat", "clarification",
                    ],
                    "description": "Primary intent of the message.",
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence score 0.0–1.0 for the chosen intent.",
                },
                "recipient": {
                    "type": "string",
                    "description": (
                        "Who the gift is for, e.g. 'Wife', 'Mother', 'Friend'. "
                        "Null if not mentioned."
                    ),
                },
                "category": {
                    "type": "string",
                    "description": (
                        "Product category hint: cake, flowers, chocolates, "
                        "fruit-baskets, food-hampers, electronics, toys, fashion, "
                        "beauty, home-and-garden, books, personalised-gifts. "
                        "Null if not mentioned."
                    ),
                },
                "budget_lkr": {
                    "type": "number",
                    "description": "Budget in Sri Lankan Rupees if mentioned. Null otherwise.",
                },
                "district": {
                    "type": "string",
                    "description": "Sri Lankan delivery district if mentioned. Null otherwise.",
                },
                "extracted_query": {
                    "type": "string",
                    "description": (
                        "A clean, concise search query derived from the message "
                        "suitable for vector search. Empty string for non-search intents."
                    ),
                },
                "preference_key": {
                    "type": "string",
                    "description": (
                        "For preference_update: which field is being updated — "
                        "'allergies', 'preferences', 'budget_lkr', or 'district'. "
                        "Null otherwise."
                    ),
                },
                "preference_value": {
                    "description": "The new value for the preference being updated. Null otherwise.",
                },
                "reasoning": {
                    "type": "string",
                    "description": "One-sentence explanation of why this intent was chosen.",
                },
            },
            "required": ["intent", "confidence", "extracted_query", "reasoning"],
        },
    },
}

_SYSTEM_PROMPT = """\
You are an intent classifier for Kapruka Gift Concierge, a Sri Lankan online gift delivery service.

Your job is to analyse the user's message (and optionally recent conversation history) and
call classify_intent with the structured result.

Guidelines:
- 'search' if the user wants gift ideas, product recommendations, or is browsing.
- 'preference_update' if the user is telling you about allergies, likes, dislikes, or budget.
- 'delivery_check' if the user asks whether delivery is available to a location.
- 'order_history' if the user asks about PAST PURCHASES on Kapruka (e.g. "what did I buy", "my order status").
- 'chitchat' for greetings, thanks, off-topic messages, OR questions about the current conversation
  session such as "what did I search", "what have I been looking for", "my recent searches",
  "what did I ask before". These refer to THIS conversation, not Kapruka purchase history.
- 'clarification' if the message is too vague to act on without a follow-up.

Always extract any recipient, category, budget (LKR), or district that is mentioned,
even if the primary intent is not 'search'.
"""


# ---------------------------------------------------------------------------
# Data class returned to callers
# ---------------------------------------------------------------------------

@dataclass
class RouteDecision:
    intent:           IntentType
    confidence:       float
    recipient:        Optional[str]   = None
    category:         Optional[str]   = None
    budget_lkr:       Optional[float] = None
    district:         Optional[str]   = None
    extracted_query:  str             = ""
    preference_key:   Optional[str]   = None
    preference_value: object          = None
    reasoning:        str             = ""

    @property
    def is_search(self) -> bool:
        return self.intent == "search"

    @property
    def is_preference_update(self) -> bool:
        return self.intent == "preference_update"

    @property
    def is_delivery_check(self) -> bool:
        return self.intent == "delivery_check"


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class Router:
    def __init__(self, model: Optional[str] = None) -> None:
        self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self._model  = model or os.getenv("OPENAI_MODEL", "gpt-4o")

    def classify(
        self,
        message: str,
        history: Optional[list[dict]] = None,
    ) -> RouteDecision:
        """
        Classify *message* intent and extract entities.

        Args:
            message: The raw user message.
            history: Optional list of prior {role, content} turns for context.

        Returns:
            RouteDecision dataclass.
        """
        messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]

        # Include last 4 turns of history for context (keeps token cost low)
        if history:
            messages.extend(history[-4:])

        messages.append({"role": "user", "content": message})

        response = self._client.chat.completions.create(
            model       = self._model,
            messages    = messages,
            tools       = [_CLASSIFY_TOOL],
            tool_choice = {"type": "function", "function": {"name": "classify_intent"}},
            temperature = 0.0,
        )

        tool_call = response.choices[0].message.tool_calls[0]
        data      = json.loads(tool_call.function.arguments)

        return RouteDecision(
            intent           = data.get("intent",           "clarification"),
            confidence       = float(data.get("confidence", 0.5)),
            recipient        = data.get("recipient"),
            category         = data.get("category"),
            budget_lkr       = data.get("budget_lkr"),
            district         = data.get("district"),
            extracted_query  = data.get("extracted_query",  ""),
            preference_key   = data.get("preference_key"),
            preference_value = data.get("preference_value"),
            reasoning        = data.get("reasoning",        ""),
        )
