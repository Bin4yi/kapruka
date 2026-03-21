"""
Unit tests for router.py, reflection.py, and orchestrator.py.
All OpenAI calls are mocked — no API cost, no network.
Run: pytest tests/test_orchestration.py -v
"""
import asyncio
import csv
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _openai_response(content: str):
    """Fake OpenAI chat completion with plain text content."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _tool_response(fn_name: str, args: dict):
    """Fake OpenAI chat completion with a single tool call."""
    tc = MagicMock()
    tc.function.name = fn_name
    tc.function.arguments = json.dumps(args)
    tc.id = "tc_test"

    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]

    choice = MagicMock()
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _classify_response(intent_data: dict):
    """Fake router classify_intent OpenAI response."""
    tc = MagicMock()
    tc.function.name = "classify_intent"
    tc.function.arguments = json.dumps(intent_data)

    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]

    choice = MagicMock()
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ============================================================================
# router.py tests
# ============================================================================

class TestRouterModule:
    """Tests for the project-root router.py (not agents/router.py)."""

    def test_returns_search_catalog_constant(self, tmp_path):
        from agents.router import RouteDecision
        import router as root_router

        fake_decision = RouteDecision(
            intent="search", confidence=0.95,
            extracted_query="cake", reasoning="user wants cake",
        )
        with patch.object(root_router, "_get_router") as mock_get:
            mock_instance = MagicMock()
            mock_instance.classify.return_value = fake_decision
            mock_get.return_value = mock_instance

            # Override metrics path to tmp
            root_router._METRICS_PATH = tmp_path / "metrics.csv"
            root_router._router = None  # reset singleton

            intent, decision = root_router.classify_intent("I want a cake")

        assert intent == root_router.SEARCH_CATALOG
        assert decision.intent == "search"

    def test_returns_update_preference_constant(self, tmp_path):
        from agents.router import RouteDecision
        import router as root_router

        fake_decision = RouteDecision(
            intent="preference_update", confidence=0.9,
            extracted_query="", reasoning="allergy update",
            preference_key="allergies", preference_value="nuts",
            recipient="Wife",
        )
        with patch.object(root_router, "_get_router") as mock_get:
            mock_instance = MagicMock()
            mock_instance.classify.return_value = fake_decision
            mock_get.return_value = mock_instance

            root_router._METRICS_PATH = tmp_path / "metrics.csv"
            root_router._router = None

            intent, decision = root_router.classify_intent("Wife is allergic to nuts")

        assert intent == root_router.UPDATE_PREFERENCE

    def test_returns_check_logistics_constant(self, tmp_path):
        from agents.router import RouteDecision
        import router as root_router

        fake_decision = RouteDecision(
            intent="delivery_check", confidence=0.98,
            extracted_query="", reasoning="delivery query",
            district="Kandy",
        )
        with patch.object(root_router, "_get_router") as mock_get:
            mock_instance = MagicMock()
            mock_instance.classify.return_value = fake_decision
            mock_get.return_value = mock_instance

            root_router._METRICS_PATH = tmp_path / "metrics.csv"
            root_router._router = None

            intent, _ = root_router.classify_intent("Do you deliver to Kandy?")

        assert intent == root_router.CHECK_LOGISTICS

    def test_metrics_written_to_csv(self, tmp_path):
        from agents.router import RouteDecision
        import router as root_router

        fake_decision = RouteDecision(
            intent="chitchat", confidence=0.99,
            extracted_query="", reasoning="greeting",
        )
        metrics_file = tmp_path / "metrics.csv"

        with patch.object(root_router, "_get_router") as mock_get:
            mock_instance = MagicMock()
            mock_instance.classify.return_value = fake_decision
            mock_get.return_value = mock_instance

            root_router._METRICS_PATH = metrics_file
            root_router._router = None

            root_router.classify_intent("Hello!")

        assert metrics_file.exists()
        rows = list(csv.DictReader(metrics_file.open()))
        assert len(rows) == 1
        assert rows[0]["intent"] == root_router.CHITCHAT

    def test_unknown_intent_falls_back_to_clarification(self, tmp_path):
        from agents.router import RouteDecision
        import router as root_router

        fake_decision = RouteDecision(
            intent="clarification", confidence=0.4,
            extracted_query="", reasoning="unclear",
        )
        with patch.object(root_router, "_get_router") as mock_get:
            mock_instance = MagicMock()
            mock_instance.classify.return_value = fake_decision
            mock_get.return_value = mock_instance

            root_router._METRICS_PATH = tmp_path / "m.csv"
            root_router._router = None

            intent, _ = root_router.classify_intent("hmm")

        assert intent == root_router.CLARIFICATION


# ============================================================================
# reflection.py tests
# ============================================================================

class TestReflection:

    def _products(self):
        return [
            {"name": "Chocolate Fudge Cake", "price": 2500,
             "description": "Rich chocolate cake", "tags": ["chocolate", "cake"]},
            {"name": "Fruit Basket", "price": 1800,
             "description": "Fresh seasonal fruits", "tags": ["fruit", "healthy"]},
        ]

    def test_returns_string(self):
        import reflection

        with patch.object(reflection, "_get_client") as mock_get:
            client = MagicMock()
            mock_get.return_value = client

            # Draft call
            client.chat.completions.create.side_effect = [
                _openai_response("Here are some lovely gifts for your wife!"),
                # Reflect call — safe
                _openai_response('{"safe": true, "issues": []}'),
            ]

            result = reflection.generate_safe_recommendation(
                query="gift for wife",
                products=self._products(),
                recipient="Wife",
            )

        assert isinstance(result, str)
        assert len(result) > 0

    def test_safe_draft_returned_without_revision(self):
        import reflection

        with patch.object(reflection, "_get_client") as mock_get:
            client = MagicMock()
            mock_get.return_value = client

            client.chat.completions.create.side_effect = [
                _openai_response("Great gifts here!"),
                _openai_response('{"safe": true, "issues": []}'),
            ]

            with patch("reflection.time") as mock_time:
                mock_time.sleep = MagicMock()
                result = reflection.generate_safe_recommendation(
                    query="flowers for mum", products=self._products(),
                )

            # Only 2 LLM calls — draft + one reflect
            assert client.chat.completions.create.call_count == 2

    def test_unsafe_draft_triggers_revision(self):
        import reflection

        with patch.object(reflection, "_get_client") as mock_get:
            client = MagicMock()
            mock_get.return_value = client

            client.chat.completions.create.side_effect = [
                _openai_response("Try the peanut brittle!"),         # draft
                _openai_response('{"safe": false, "issues": ["contains peanuts — allergen"]}'),  # reflect
                _openai_response("Try the fruit basket instead!"),   # revise
                _openai_response('{"safe": true, "issues": []}'),    # reflect again
            ]

            with patch("reflection.time") as mock_time:
                mock_time.sleep = MagicMock()
                result = reflection.generate_safe_recommendation(
                    query="gift",
                    products=self._products(),
                    allergies=["peanuts"],
                )

            assert "fruit basket" in result.lower()
            assert client.chat.completions.create.call_count == 4

    def test_emits_events_to_queue(self):
        import reflection

        q = asyncio.Queue()

        with patch.object(reflection, "_get_client") as mock_get:
            client = MagicMock()
            mock_get.return_value = client

            client.chat.completions.create.side_effect = [
                _openai_response("Great choice!"),
                _openai_response('{"safe": true, "issues": []}'),
            ]

            with patch("reflection.time") as mock_time:
                mock_time.sleep = MagicMock()
                reflection.generate_safe_recommendation(
                    query="cake", products=self._products(),
                    event_queue=q, surface_id="chat_surface",
                )

        events = []
        while not q.empty():
            events.append(q.get_nowait())

        types = [e["type"] for e in events]
        assert "dataModelUpdate" in types
        surface_ids = {e["surfaceId"] for e in events}
        assert "chat_surface" in surface_ids

    def test_invalid_reflect_json_treated_as_safe(self):
        import reflection

        with patch.object(reflection, "_get_client") as mock_get:
            client = MagicMock()
            mock_get.return_value = client

            client.chat.completions.create.side_effect = [
                _openai_response("Nice gifts!"),
                _openai_response("Sorry, I cannot evaluate that."),  # invalid JSON
            ]

            with patch("reflection.time") as mock_time:
                mock_time.sleep = MagicMock()
                result = reflection.generate_safe_recommendation(
                    query="test", products=self._products(),
                )

        assert isinstance(result, str)

    def test_max_rounds_returns_last_draft(self):
        import reflection

        with patch.object(reflection, "_get_client") as mock_get:
            client = MagicMock()
            mock_get.return_value = client

            # Always unsafe — forces MAX_REFLECT_ROUNDS iterations
            unsafe = _openai_response('{"safe": false, "issues": ["issue"]}')
            responses = [_openai_response("Draft")] + [unsafe, _openai_response("Revised")] * 5
            client.chat.completions.create.side_effect = responses

            with patch("reflection.time") as mock_time:
                mock_time.sleep = MagicMock()
                result = reflection.generate_safe_recommendation(
                    query="test", products=self._products(),
                )

        assert isinstance(result, str)


# ============================================================================
# orchestrator.py tests
# ============================================================================

class TestOrchestrator:

    def _collect(self, gen):
        """Collect all events from an async generator."""
        async def _run():
            events = []
            async for event in gen:
                events.append(event)
            return events
        return asyncio.run(_run())

    def _make_orchestrator_with_mocks(self):
        """Return orchestrator with all external calls patched."""
        import orchestrator
        orch = orchestrator.KaprukaConciergeOrchestrator()
        return orch

    def test_search_pipeline_emits_gallery_and_chat(self, tmp_path):
        import orchestrator
        import router as root_router
        from agents.router import RouteDecision
        from agents.catalog_agent import CatalogResponse

        fake_decision = RouteDecision(
            intent="search", confidence=0.9,
            extracted_query="cake for wife", reasoning="search",
            recipient="Wife", category="cake",
        )
        fake_catalog = CatalogResponse(
            message="Here are some cakes!",
            products=[{"name": "Chocolate Cake", "price": 2000, "url": "http://x.com/1"}],
        )

        with patch.object(root_router, "_get_router") as mock_router_get, \
             patch.object(orchestrator, "_catalog") as mock_cat_fn, \
             patch.object(orchestrator, "_pm") as mock_pm_fn, \
             patch("reflection.time") as mock_time, \
             patch("reflection._get_client") as mock_ref_client:

            # Router
            root_router._METRICS_PATH = tmp_path / "m.csv"
            root_router._router = None
            mock_router_inst = MagicMock()
            mock_router_inst.classify.return_value = fake_decision
            mock_router_get.return_value = mock_router_inst

            # Profile manager
            pm = MagicMock()
            pm.get_allergies.return_value = []
            pm.get_budget.return_value = None
            mock_pm_fn.return_value = pm

            # Catalog agent
            cat = MagicMock()
            cat.run.return_value = fake_catalog
            mock_cat_fn.return_value = cat

            # Reflection
            mock_time.sleep = MagicMock()
            ref_client = MagicMock()
            mock_ref_client.return_value = ref_client
            ref_client.chat.completions.create.side_effect = [
                _openai_response("The Chocolate Cake is perfect for your wife!"),
                _openai_response('{"safe": true, "issues": []}'),
            ]

            orch = orchestrator.KaprukaConciergeOrchestrator()
            events = self._collect(orch.process("sess1", "I want a cake for my wife"))

        types = [e["type"] for e in events]
        surface_ids = [e.get("surfaceId") for e in events]

        assert "gallery_surface" in surface_ids
        assert "chat_surface" in surface_ids
        assert "beginRendering" in types

    def test_preference_update_saves_allergy(self, tmp_path):
        import orchestrator
        import router as root_router
        from agents.router import RouteDecision

        fake_decision = RouteDecision(
            intent="preference_update", confidence=0.9,
            extracted_query="", reasoning="allergy",
            recipient="Wife", preference_key="allergies",
            preference_value="shellfish",
        )

        with patch.object(root_router, "_get_router") as mock_router_get, \
             patch.object(orchestrator, "_pm") as mock_pm_fn:

            root_router._METRICS_PATH = tmp_path / "m.csv"
            root_router._router = None
            mock_router_inst = MagicMock()
            mock_router_inst.classify.return_value = fake_decision
            mock_router_get.return_value = mock_router_inst

            pm = MagicMock()
            mock_pm_fn.return_value = pm

            orch = orchestrator.KaprukaConciergeOrchestrator()
            events = self._collect(orch.process("sess2", "Wife is allergic to shellfish"))

        pm.add_allergy.assert_called_once_with("Wife", "shellfish")
        surface_ids = [e.get("surfaceId") for e in events]
        assert "notification_surface" in surface_ids
        assert "memory_surface" in surface_ids

    def test_logistics_check_emits_notification(self, tmp_path):
        import orchestrator
        import router as root_router
        from agents.router import RouteDecision
        from agents.logistics_agent import LogisticsResponse

        fake_decision = RouteDecision(
            intent="delivery_check", confidence=0.98,
            extracted_query="", reasoning="delivery",
            district="Jaffna",
        )
        fake_logistics = LogisticsResponse(
            message="Delivery to Jaffna is available with limited coverage.",
            feasible=True, tier="LIMITED",
            district_matched="Jaffna",
            estimated_days=5, cutoff_time="12 PM",
        )

        with patch.object(root_router, "_get_router") as mock_router_get, \
             patch.object(orchestrator, "_logistics") as mock_log_fn:

            root_router._METRICS_PATH = tmp_path / "m.csv"
            root_router._router = None
            mock_router_inst = MagicMock()
            mock_router_inst.classify.return_value = fake_decision
            mock_router_get.return_value = mock_router_inst

            log = MagicMock()
            log.run.return_value = fake_logistics
            mock_log_fn.return_value = log

            orch = orchestrator.KaprukaConciergeOrchestrator()
            events = self._collect(orch.process("sess3", "Do you deliver to Jaffna?"))

        surface_ids = [e.get("surfaceId") for e in events]
        assert "chat_surface" in surface_ids
        assert "notification_surface" in surface_ids

        notif_data = next(
            e["data"] for e in events
            if e.get("type") == "dataModelUpdate" and e.get("surfaceId") == "notification_surface"
        )
        assert notif_data["tier"] == "LIMITED"
        assert notif_data["estimated_days"] == 5

    def test_chitchat_emits_chat_surface(self, tmp_path):
        import orchestrator
        import router as root_router
        from agents.router import RouteDecision

        fake_decision = RouteDecision(
            intent="chitchat", confidence=0.99,
            extracted_query="", reasoning="greeting",
        )

        with patch.object(root_router, "_get_router") as mock_router_get, \
             patch.object(orchestrator, "_oai") as mock_oai_fn, \
             patch.object(orchestrator, "_oai_model", return_value="gpt-4o"):

            root_router._METRICS_PATH = tmp_path / "m.csv"
            root_router._router = None
            mock_router_inst = MagicMock()
            mock_router_inst.classify.return_value = fake_decision
            mock_router_get.return_value = mock_router_inst

            oai = MagicMock()
            oai.chat.completions.create.return_value = _openai_response(
                "Hello! How can I help you find the perfect gift?"
            )
            mock_oai_fn.return_value = oai

            orch = orchestrator.KaprukaConciergeOrchestrator()
            events = self._collect(orch.process("sess4", "Hello!"))

        surface_ids = [e.get("surfaceId") for e in events]
        assert "chat_surface" in surface_ids

        chat_data = next(
            e["data"] for e in events
            if e.get("type") == "dataModelUpdate" and e.get("surfaceId") == "chat_surface"
        )
        assert "Hello" in chat_data["message"] or len(chat_data["message"]) > 0

    def test_clarification_emits_chat_surface(self, tmp_path):
        import orchestrator
        import router as root_router
        from agents.router import RouteDecision

        fake_decision = RouteDecision(
            intent="clarification", confidence=0.4,
            extracted_query="", reasoning="unclear",
        )

        with patch.object(root_router, "_get_router") as mock_router_get:
            root_router._METRICS_PATH = tmp_path / "m.csv"
            root_router._router = None
            mock_router_inst = MagicMock()
            mock_router_inst.classify.return_value = fake_decision
            mock_router_get.return_value = mock_router_inst

            orch = orchestrator.KaprukaConciergeOrchestrator()
            events = self._collect(orch.process("sess5", "umm"))

        surface_ids = [e.get("surfaceId") for e in events]
        assert "chat_surface" in surface_ids

    def test_all_events_have_type_and_surface_id(self, tmp_path):
        import orchestrator
        import router as root_router
        from agents.router import RouteDecision

        fake_decision = RouteDecision(
            intent="clarification", confidence=0.3,
            extracted_query="", reasoning="vague",
        )

        with patch.object(root_router, "_get_router") as mock_router_get:
            root_router._METRICS_PATH = tmp_path / "m.csv"
            root_router._router = None
            mock_router_inst = MagicMock()
            mock_router_inst.classify.return_value = fake_decision
            mock_router_get.return_value = mock_router_inst

            orch = orchestrator.KaprukaConciergeOrchestrator()
            events = self._collect(orch.process("sess6", "?"))

        for e in events:
            assert "type" in e, f"Missing 'type' in event: {e}"
            assert "surfaceId" in e, f"Missing 'surfaceId' in event: {e}"

    def test_agent_surface_always_emitted(self, tmp_path):
        import orchestrator
        import router as root_router
        from agents.router import RouteDecision

        fake_decision = RouteDecision(
            intent="chitchat", confidence=0.9,
            extracted_query="", reasoning="greeting",
        )

        with patch.object(root_router, "_get_router") as mock_router_get, \
             patch.object(orchestrator, "_oai") as mock_oai_fn, \
             patch.object(orchestrator, "_oai_model", return_value="gpt-4o"):

            root_router._METRICS_PATH = tmp_path / "m.csv"
            root_router._router = None
            mock_router_inst = MagicMock()
            mock_router_inst.classify.return_value = fake_decision
            mock_router_get.return_value = mock_router_inst

            oai = MagicMock()
            oai.chat.completions.create.return_value = _openai_response("Hi!")
            mock_oai_fn.return_value = oai

            orch = orchestrator.KaprukaConciergeOrchestrator()
            events = self._collect(orch.process("sess7", "Hi"))

        agent_events = [e for e in events if e.get("surfaceId") == "agent_surface"]
        assert len(agent_events) >= 1

    def test_order_history_stub_emits_chat(self, tmp_path):
        import orchestrator
        import router as root_router
        from agents.router import RouteDecision

        fake_decision = RouteDecision(
            intent="order_history", confidence=0.88,
            extracted_query="", reasoning="order query",
        )

        with patch.object(root_router, "_get_router") as mock_router_get:
            root_router._METRICS_PATH = tmp_path / "m.csv"
            root_router._router = None
            mock_router_inst = MagicMock()
            mock_router_inst.classify.return_value = fake_decision
            mock_router_get.return_value = mock_router_inst

            orch = orchestrator.KaprukaConciergeOrchestrator()
            events = self._collect(orch.process("sess8", "Show my past orders"))

        surface_ids = [e.get("surfaceId") for e in events]
        assert "chat_surface" in surface_ids
