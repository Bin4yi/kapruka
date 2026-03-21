"""
agents/logistics_agent.py
Logistics Specialist — delivery feasibility for Sri Lankan districts.
Pure Python. No frameworks.

Provides two layers:
  1. check_delivery(district)  — pure function, rapidfuzz match, always available.
  2. LogisticsAgent.run(message, recipient_profile)
     — LLM-powered agent that parses district from natural language,
       calls check_delivery as a tool, and returns a conversational response
       with structured delivery info.
"""

import json
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from rapidfuzz import fuzz, process

load_dotenv()

# ---------------------------------------------------------------------------
# District data
# ---------------------------------------------------------------------------

DISTRICT_TIERS: dict[str, list[str]] = {
    "FULL": [
        "Colombo", "Kandy", "Galle", "Negombo", "Matara", "Ratnapura",
        "Kurunegala", "Kalutara", "Panadura", "Moratuwa", "Kotte",
        "Dehiwala", "Nugegoda", "Maharagama", "Kaduwela",
    ],
    "LIMITED": [
        "Jaffna", "Anuradhapura", "Trincomalee", "Batticaloa",
        "Vavuniya", "Polonnaruwa", "Badulla", "Monaragala", "Ampara",
    ],
}

_DISTRICT_LOOKUP: dict[str, str] = {
    d.lower(): tier
    for tier, districts in DISTRICT_TIERS.items()
    for d in districts
}
_ALL_DISTRICTS: list[str] = list(_DISTRICT_LOOKUP.keys())
_FUZZY_THRESHOLD           = 80


# ---------------------------------------------------------------------------
# Core delivery check (pure function — no LLM, no I/O)
# ---------------------------------------------------------------------------

def check_delivery(district: str) -> dict:
    """
    Check delivery feasibility for a district string (typo-tolerant).

    Returns:
        {feasible, tier, district_matched, estimated_days, cutoff_time, message}
    """
    if not district or not district.strip():
        return _unknown("No district provided.")

    match = process.extractOne(
        district.strip().lower(),
        _ALL_DISTRICTS,
        scorer      = fuzz.WRatio,
        score_cutoff= _FUZZY_THRESHOLD,
    )
    if match is None:
        return _unknown(
            f"'{district}' is not a recognised delivery district. "
            "Please check the spelling or contact Kapruka support."
        )

    matched_lower, _score, _ = match
    tier      = _DISTRICT_LOOKUP[matched_lower]
    canonical = _canonical(matched_lower)

    if tier == "FULL":
        return {
            "feasible":         True,
            "tier":             "FULL",
            "district_matched": canonical,
            "estimated_days":   2,
            "cutoff_time":      "2 PM",
            "message": (
                f"Delivery to {canonical} is available. "
                "Orders placed before 2 PM are typically delivered within 2 business days."
            ),
        }
    return {
        "feasible":         True,
        "tier":             "LIMITED",
        "district_matched": canonical,
        "estimated_days":   5,
        "cutoff_time":      "12 PM",
        "message": (
            f"Delivery to {canonical} is available with limited coverage. "
            "Orders placed before 12 PM are typically delivered within 5 business days."
        ),
    }


def list_serviceable_districts() -> dict[str, list[str]]:
    return {tier: list(districts) for tier, districts in DISTRICT_TIERS.items()}


# ---------------------------------------------------------------------------
# Tool schema for LogisticsAgent
# ---------------------------------------------------------------------------

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_delivery_feasibility",
            "description": (
                "Check whether Kapruka can deliver to a Sri Lankan district "
                "and return estimated delivery time and order cutoff."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "district": {
                        "type": "string",
                        "description": "The delivery district name (may contain typos).",
                    },
                },
                "required": ["district"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_all_districts",
            "description": "Return all districts Kapruka services, grouped by tier.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _execute_tool(name: str, args: dict) -> dict:
    if name == "check_delivery_feasibility":
        return check_delivery(args.get("district", ""))
    if name == "list_all_districts":
        return list_serviceable_districts()
    return {"error": f"Unknown tool: {name}"}


# ---------------------------------------------------------------------------
# Response dataclass
# ---------------------------------------------------------------------------

@dataclass
class LogisticsResponse:
    message:          str
    feasible:         Optional[bool]  = None
    tier:             Optional[str]   = None
    district_matched: Optional[str]   = None
    estimated_days:   Optional[int]   = None
    cutoff_time:      Optional[str]   = None


# ---------------------------------------------------------------------------
# LogisticsAgent
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the Logistics Specialist for Kapruka Gift Concierge, a Sri Lankan online gift delivery service.

Your job is to answer delivery-related questions clearly and helpfully.

Guidelines:
- Use the check_delivery_feasibility tool to look up any district the user mentions.
- If the user doesn't specify a district, ask them which district they need delivery to.
- If delivery is not available, apologise and suggest they contact Kapruka support.
- Quote the estimated delivery days and order cutoff time from the tool result.
- If the recipient's district is already known from their profile, proactively check it.
- Be concise, warm, and direct. One short paragraph is usually enough.
"""


class LogisticsAgent:
    MAX_TOOL_ROUNDS = 4

    def __init__(self, model: Optional[str] = None) -> None:
        self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self._model  = model or os.getenv("OPENAI_MODEL", "gpt-4o")

    def run(
        self,
        message:          str,
        recipient:        Optional[str]  = None,
        district_hint:    Optional[str]  = None,
        history:          Optional[list[dict]] = None,
    ) -> LogisticsResponse:
        """
        Run the logistics tool-use loop.

        Args:
            message:       User's delivery-related question.
            recipient:     Name of recipient (for context in the reply).
            district_hint: District extracted by the router (may be None).
            history:       Prior conversation turns.
        """
        context_parts = []
        if recipient:
            context_parts.append(f"Recipient: {recipient}")
        if district_hint:
            context_parts.append(f"Delivery district mentioned: {district_hint}")

        user_content = (
            "\n".join(context_parts) + "\n\n" + message
            if context_parts else message
        )

        messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]
        if history:
            messages.extend(history[-4:])
        messages.append({"role": "user", "content": user_content})

        last_delivery_result: dict = {}

        for _ in range(self.MAX_TOOL_ROUNDS):
            response      = self._client.chat.completions.create(
                model     = self._model,
                messages  = messages,
                tools     = _TOOLS,
            )
            assistant_msg = response.choices[0].message

            if not assistant_msg.tool_calls:
                return LogisticsResponse(
                    message          = assistant_msg.content or "",
                    feasible         = last_delivery_result.get("feasible"),
                    tier             = last_delivery_result.get("tier"),
                    district_matched = last_delivery_result.get("district_matched"),
                    estimated_days   = last_delivery_result.get("estimated_days"),
                    cutoff_time      = last_delivery_result.get("cutoff_time"),
                )

            messages.append(assistant_msg)

            for tc in assistant_msg.tool_calls:
                fn_args = json.loads(tc.function.arguments)
                result  = _execute_tool(tc.function.name, fn_args)

                if tc.function.name == "check_delivery_feasibility":
                    last_delivery_result = result

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      json.dumps(result, ensure_ascii=False),
                })

        return LogisticsResponse(message="I couldn't determine delivery feasibility. Please try again.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _canonical(lower_name: str) -> str:
    for districts in DISTRICT_TIERS.values():
        for d in districts:
            if d.lower() == lower_name:
                return d
    return lower_name.title()


def _unknown(message: str) -> dict:
    return {
        "feasible":         False,
        "tier":             "UNKNOWN",
        "district_matched": None,
        "estimated_days":   None,
        "cutoff_time":      None,
        "message":          message,
    }
