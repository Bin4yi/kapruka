"""
Unit tests for memory/semantic.py — uses a temp profiles file, no network.
Run: pytest tests/test_semantic.py -v
"""
import json
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

# Point PROFILES_PATH to a temp file before importing ProfileManager
_tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
_SAMPLE_PROFILES = {
    "Wife":   {"allergies": ["nuts"], "preferences": ["flowers"], "district": "Colombo", "order_history": [], "budget_lkr": 5000},
    "Mother": {"allergies": ["gluten"], "preferences": ["tea"],   "district": "Kandy",   "order_history": [], "budget_lkr": 3000},
}
json.dump(_SAMPLE_PROFILES, _tmp)
_tmp.close()

os.environ["PROFILES_PATH"] = _tmp.name

from memory.semantic import ProfileManager  # noqa: E402 (import after env patch)


@pytest.fixture()
def pm(tmp_path):
    """Fresh ProfileManager backed by a temp copy of sample profiles."""
    profiles_file = tmp_path / "profiles.json"
    profiles_file.write_text(json.dumps(_SAMPLE_PROFILES), encoding="utf-8")
    with patch.dict(os.environ, {"PROFILES_PATH": str(profiles_file)}):
        # Re-import so the module picks up the new path
        import importlib
        import memory.semantic as sem_mod
        importlib.reload(sem_mod)
        yield sem_mod.ProfileManager()


def test_get_profile(pm):
    profile = pm.get_profile("Wife")
    assert profile["district"] == "Colombo"
    assert profile["budget_lkr"] == 5000


def test_get_missing_profile_returns_empty(pm):
    assert pm.get_profile("Nobody") == {}


def test_get_allergies(pm):
    assert pm.get_allergies("Wife") == ["nuts"]
    assert pm.get_allergies("Nobody") == []


def test_get_preferences(pm):
    assert "flowers" in pm.get_preferences("Wife")


def test_get_budget(pm):
    assert pm.get_budget("Mother") == 3000.0
    assert pm.get_budget("Nobody") is None


def test_list_recipients(pm):
    recipients = pm.list_recipients()
    assert "Wife" in recipients
    assert "Mother" in recipients


def test_update_profile(pm):
    pm.update_profile("Wife", "budget_lkr", 8000)
    assert pm.get_budget("Wife") == 8000.0


def test_add_allergy_new(pm):
    pm.add_allergy("Wife", "Shellfish")
    allergies = pm.get_allergies("Wife")
    assert "shellfish" in [a.lower() for a in allergies]


def test_add_allergy_no_duplicate(pm):
    pm.add_allergy("Wife", "nuts")
    pm.add_allergy("Wife", "NUTS")
    assert pm.get_allergies("Wife").count("nuts") == 1


def test_add_preference(pm):
    pm.add_preference("Mother", "fruit baskets")
    assert "fruit baskets" in pm.get_preferences("Mother")


def test_add_order(pm):
    order = {"product": "Rose Bouquet", "price": 2500, "date": "2026-03-21"}
    pm.add_order("Wife", order)
    history = pm.get_order_history("Wife")
    assert history[-1]["product"] == "Rose Bouquet"


def test_set_budget(pm):
    pm.set_budget("Wife", 12000)
    assert pm.get_budget("Wife") == 12000.0


def test_save_persists_to_disk(pm, tmp_path):
    pm.add_allergy("Mother", "dairy")
    # Reload from disk to verify persistence
    pm.reload()
    allergies = pm.get_allergies("Mother")
    assert "dairy" in [a.lower() for a in allergies]


def test_new_recipient_created_on_update(pm):
    pm.update_profile("Friend", "budget_lkr", 15000)
    assert pm.get_budget("Friend") == 15000.0
