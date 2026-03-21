"""
agents/catalog_agent.py
Catalog Specialist — tool-use agent for RAG-based product search.
Pure Python. No frameworks. Implements a full OpenAI tool-calling loop.

Tools available to the LLM:
  search_catalog            full semantic search
  search_catalog_by_category  category-scoped semantic search
  filter_by_budget          drop products above budget
  filter_safe_for_recipient remove products containing known allergens

The agent loop runs until the model stops calling tools, then returns a
structured CatalogResponse with matched products and a conversational message.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

from memory.lt_rag import search, search_excluding, search_by_category as _rag_by_cat
from memory.semantic import ProfileManager

load_dotenv()

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": (
                "Perform a semantic search across the entire Kapruka product catalog. "
                "Use for broad queries or when category is unknown."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language search query.",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default 8).",
                        "default": 8,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_catalog_by_category",
            "description": (
                "Search within a specific product category. "
                "Use when the user has mentioned a category or when a previous "
                "broad search suggests a clear category."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": (
                            "Category slug: cake, flowers, chocolates, fruit-baskets, "
                            "food-hampers, electronics, toys, fashion, beauty, "
                            "home-and-garden, books, personalised-gifts."
                        ),
                    },
                    "query": {"type": "string", "description": "Search query within category."},
                    "top_k": {"type": "integer", "default": 5},
                },
                "required": ["category", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_by_budget",
            "description": "Remove products whose price exceeds the given budget.",
            "parameters": {
                "type": "object",
                "properties": {
                    "products": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of product dicts from a previous search.",
                    },
                    "budget_lkr": {
                        "type": "number",
                        "description": "Maximum price in Sri Lankan Rupees.",
                    },
                },
                "required": ["products", "budget_lkr"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_safe_for_recipient",
            "description": (
                "Remove products that contain allergens known to affect the recipient. "
                "Checks product name, description, tags, and ingredients fields."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "products": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "allergens": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of allergen strings to check against.",
                    },
                },
                "required": ["products", "allergens"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Tool implementations (pure Python)
# ---------------------------------------------------------------------------

def _tool_search_catalog(query: str, top_k: int = 8) -> list[dict]:
    return search(query, top_k=top_k)


def _tool_search_catalog_by_category(
    category: str, query: str, top_k: int = 5
) -> list[dict]:
    return _rag_by_cat(category, query, top_k=top_k)


def _tool_filter_by_budget(products: list[dict], budget_lkr: float) -> list[dict]:
    return [p for p in products if (p.get("price") or 0) <= budget_lkr]


def _tool_filter_safe_for_recipient(
    products: list[dict], allergens: list[str]
) -> list[dict]:
    if not allergens:
        return products
    lower_allergens = [a.lower() for a in allergens]

    def _contains_allergen(product: dict) -> bool:
        haystack = " ".join([
            product.get("name",        ""),
            product.get("description", ""),
            product.get("ingredients", ""),
            " ".join(product.get("tags", [])),
        ]).lower()
        return any(allergen in haystack for allergen in lower_allergens)

    return [p for p in products if not _contains_allergen(p)]


_TOOL_DISPATCH = {
    "search_catalog":             _tool_search_catalog,
    "search_catalog_by_category": _tool_search_catalog_by_category,
    "filter_by_budget":           _tool_filter_by_budget,
    "filter_safe_for_recipient":  _tool_filter_safe_for_recipient,
}


def _execute_tool(name: str, args: dict) -> object:
    fn = _TOOL_DISPATCH.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return fn(**args)
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Display enrichment
# ---------------------------------------------------------------------------

def enrich_for_display(products: list[dict]) -> list[dict]:
    """Ensure every product dict has the fields the frontend expects."""
    enriched = []
    for raw in products:
        p = dict(raw)
        p.setdefault("image_url",      "")
        p.setdefault("rating",         None)
        p.setdefault("review_count",   None)
        p.setdefault("discount_pct",   None)
        p.setdefault("tags",           [])
        p.setdefault("delivery_note",  "")
        p.setdefault("ingredients",    "")
        p.setdefault("description",    "")
        p.setdefault("original_price", None)
        p.setdefault("weight_grams",   None)
        if not isinstance(p.get("image_urls"), list):
            p["image_urls"] = [p["image_url"]] if p["image_url"] else []
        enriched.append(p)
    return enriched


# ---------------------------------------------------------------------------
# Response dataclass
# ---------------------------------------------------------------------------

@dataclass
class CatalogResponse:
    message:        str
    products:       list[dict]         = field(default_factory=list)
    tool_calls_made: list[str]         = field(default_factory=list)
    follow_up:      Optional[str]      = None


# ---------------------------------------------------------------------------
# CatalogAgent
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the Catalog Specialist for Kapruka Gift Concierge, a Sri Lankan online gift delivery service.

Your job is to find the best gift products for the user by calling the available search and
filter tools. Follow this strategy:

1. Start with search_catalog or search_catalog_by_category based on what the user wants.
2. If the recipient has a budget, always call filter_by_budget on the results.
3. If the recipient has known allergens, always call filter_safe_for_recipient.
4. Aim to present 3–5 well-matched products. If the first search returns fewer than 3
   suitable products, try a second search with a different query or broader terms.
5. Present products clearly: name, price (in LKR), a brief reason why it's a good fit,
   and whether it's in stock.
6. Be warm, concise, and helpful. Address the recipient by name if known.
7. Never invent products or prices — only recommend what the tools return.
"""


class CatalogAgent:
    MAX_TOOL_ROUNDS = 6   # prevent infinite loops

    def __init__(self, model: Optional[str] = None) -> None:
        self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self._model  = model or os.getenv("OPENAI_MODEL", "gpt-4o")

    def run(
        self,
        query:            str,
        recipient:        Optional[str]      = None,
        profile_manager:  Optional[ProfileManager] = None,
        history:          Optional[list[dict]]     = None,
        category_hint:    Optional[str]      = None,
        budget_lkr:       Optional[float]    = None,
    ) -> CatalogResponse:
        """
        Run the catalog tool-use loop and return a CatalogResponse.

        Args:
            query:           User's search intent.
            recipient:       Name of the gift recipient (e.g. "Wife").
            profile_manager: ProfileManager instance for allergy / budget lookup.
            history:         Prior conversation turns [{role, content}].
            category_hint:   Optional category slug from the router.
            budget_lkr:      Budget override (router may have extracted this).
        """
        # ---- Resolve recipient context ----
        allergies: list[str] = []
        effective_budget     = budget_lkr

        if recipient and profile_manager:
            profile          = profile_manager.get_profile(recipient)
            allergies        = profile_manager.get_allergies(recipient)
            if effective_budget is None:
                effective_budget = profile_manager.get_budget(recipient)

        # ---- Build context preamble ----
        context_lines = []
        if recipient:
            context_lines.append(f"Recipient: {recipient}")
        if effective_budget:
            context_lines.append(f"Budget: LKR {effective_budget:,.0f}")
        if allergies:
            context_lines.append(f"Known allergens: {', '.join(allergies)}")
        if category_hint:
            context_lines.append(f"Category hint from router: {category_hint}")

        context_block = "\n".join(context_lines)
        user_content  = f"{context_block}\n\nUser request: {query}" if context_block else query

        # ---- Assemble message thread ----
        messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]
        if history:
            messages.extend(history[-6:])
        messages.append({"role": "user", "content": user_content})

        # ---- Tool-use loop ----
        tool_calls_made: list[str] = []
        all_products:    list[dict] = []

        for _ in range(self.MAX_TOOL_ROUNDS):
            response     = self._client.chat.completions.create(
                model    = self._model,
                messages = messages,
                tools    = _TOOLS,
            )
            assistant_msg = response.choices[0].message

            if not assistant_msg.tool_calls:
                # Final text response — collect any products accumulated
                return CatalogResponse(
                    message         = assistant_msg.content or "",
                    products        = enrich_for_display(all_products),
                    tool_calls_made = tool_calls_made,
                )

            # Execute tool calls
            messages.append(assistant_msg)

            for tc in assistant_msg.tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments)

                result = _execute_tool(fn_name, fn_args)
                tool_calls_made.append(fn_name)

                # Accumulate product results
                if isinstance(result, list) and result and isinstance(result[0], dict):
                    # Merge without duplicating by URL
                    seen_urls = {p.get("url") for p in all_products}
                    for p in result:
                        if p.get("url") not in seen_urls:
                            all_products.append(p)
                            seen_urls.add(p.get("url"))

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      json.dumps(result, ensure_ascii=False),
                })

        # Max rounds reached — return what we have
        return CatalogResponse(
            message         = "Here are the best matches I found:",
            products        = enrich_for_display(all_products),
            tool_calls_made = tool_calls_made,
        )


# ---------------------------------------------------------------------------
# Module-level convenience functions (backward compat + direct use)
# ---------------------------------------------------------------------------

def search_products(query: str, top_k: int = 8) -> list[dict]:
    return search(query, top_k=top_k)


def search_safe_products(
    query: str, exclude_names: list[str], top_k: int = 8
) -> list[dict]:
    return search_excluding(query, exclude_names=exclude_names, top_k=top_k)


def search_by_category(category: str, query: str, top_k: int = 5) -> list[dict]:
    return _rag_by_cat(category, query, top_k=top_k)
