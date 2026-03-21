"""
Unit tests for agents/router.py.
Mocks OpenAI — no API calls, no cost.
Run: pytest tests/test_router.py -v
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from agents.router import Router, RouteDecision


def _make_openai_response(intent_data: dict):
    """Build a fake OpenAI response with a tool call."""
    tool_call        = MagicMock()
    tool_call.function.name      = "classify_intent"
    tool_call.function.arguments = json.dumps(intent_data)

    choice           = MagicMock()
    choice.message.tool_calls = [tool_call]
    choice.message.content    = None

    response         = MagicMock()
    response.choices = [choice]
    return response


@pytest.fixture()
def router():
    with patch("agents.router.OpenAI") as MockOpenAI:
        instance = MockOpenAI.return_value
        yield Router(), instance


def _patch_router(instance, intent_data: dict):
    instance.chat.completions.create.return_value = _make_openai_response(intent_data)


class TestRouterClassify:
    def test_search_intent(self, router):
        r, mock = router
        _patch_router(mock, {
            "intent": "search", "confidence": 0.95,
            "extracted_query": "birthday cake for wife", "reasoning": "user wants cake",
            "recipient": "Wife", "category": "cake",
        })
        result = r.classify("I need a birthday cake for my wife")
        assert result.intent          == "search"
        assert result.recipient       == "Wife"
        assert result.category        == "cake"
        assert result.extracted_query == "birthday cake for wife"
        assert result.confidence      == 0.95

    def test_preference_update_intent(self, router):
        r, mock = router
        _patch_router(mock, {
            "intent": "preference_update", "confidence": 0.9,
            "extracted_query": "", "reasoning": "user adding allergy",
            "recipient": "Wife", "preference_key": "allergies",
            "preference_value": "shellfish",
        })
        result = r.classify("My wife is also allergic to shellfish")
        assert result.is_preference_update
        assert result.preference_key   == "allergies"
        assert result.preference_value == "shellfish"

    def test_delivery_check_intent(self, router):
        r, mock = router
        _patch_router(mock, {
            "intent": "delivery_check", "confidence": 0.98,
            "extracted_query": "", "reasoning": "user asking about delivery",
            "district": "Jaffna",
        })
        result = r.classify("Do you deliver to Jaffna?")
        assert result.is_delivery_check
        assert result.district == "Jaffna"

    def test_chitchat_intent(self, router):
        r, mock = router
        _patch_router(mock, {
            "intent": "chitchat", "confidence": 0.99,
            "extracted_query": "", "reasoning": "greeting",
        })
        result = r.classify("Hello!")
        assert result.intent == "chitchat"

    def test_returns_route_decision_dataclass(self, router):
        r, mock = router
        _patch_router(mock, {
            "intent": "search", "confidence": 0.8,
            "extracted_query": "flowers", "reasoning": "flowers query",
        })
        result = r.classify("flowers")
        assert isinstance(result, RouteDecision)

    def test_budget_extracted(self, router):
        r, mock = router
        _patch_router(mock, {
            "intent": "search", "confidence": 0.85,
            "extracted_query": "gift under 3000",
            "reasoning": "search with budget", "budget_lkr": 3000,
        })
        result = r.classify("find a gift under Rs 3000")
        assert result.budget_lkr == 3000

    def test_is_search_property(self, router):
        r, mock = router
        _patch_router(mock, {
            "intent": "search", "confidence": 0.9,
            "extracted_query": "chocolates", "reasoning": "x",
        })
        result = r.classify("chocolates")
        assert result.is_search is True
        assert result.is_preference_update is False
        assert result.is_delivery_check is False
