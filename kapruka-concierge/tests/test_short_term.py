"""
Unit tests for memory/short_term.py — no external dependencies.
Run: pytest tests/test_short_term.py -v
"""
import pytest
from memory.short_term import SessionManager


def test_add_and_get_history():
    sm = SessionManager(max_turns=5)
    sm.add_turn("user", "Hello")
    sm.add_turn("assistant", "Hi there")
    history = sm.get_history()
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["content"] == "Hi there"


def test_max_turns_enforced():
    sm = SessionManager(max_turns=3)
    for i in range(5):
        sm.add_turn("user", f"msg {i}")
    assert len(sm) == 3
    # Oldest should have been dropped
    contents = [t["content"] for t in sm.get_history()]
    assert "msg 0" not in contents
    assert "msg 4" in contents


def test_context_window():
    sm = SessionManager(max_turns=10)
    for i in range(8):
        sm.add_turn("user", f"msg {i}")
    window = sm.get_context_window(n=3)
    assert len(window) == 3
    assert window[-1]["content"] == "msg 7"


def test_context_window_smaller_than_history():
    sm = SessionManager(max_turns=10)
    sm.add_turn("user", "only one")
    window = sm.get_context_window(n=5)
    assert len(window) == 1


def test_to_llm_messages_strips_timestamp():
    sm = SessionManager()
    sm.add_turn("user", "test")
    messages = sm.to_llm_messages()
    assert messages == [{"role": "user", "content": "test"}]
    assert "timestamp" not in messages[0]


def test_clear():
    sm = SessionManager()
    sm.add_turn("user", "a")
    sm.add_turn("assistant", "b")
    sm.clear()
    assert len(sm) == 0
    assert sm.get_history() == []


def test_timestamp_present_in_history():
    sm = SessionManager()
    sm.add_turn("user", "hi")
    assert "timestamp" in sm.get_history()[0]


def test_roles_preserved():
    sm = SessionManager(max_turns=10)
    sm.add_turn("system", "You are a gift assistant.")
    sm.add_turn("user", "Find a gift for my wife.")
    sm.add_turn("assistant", "Here are some ideas.")
    msgs = sm.to_llm_messages()
    assert [m["role"] for m in msgs] == ["system", "user", "assistant"]
