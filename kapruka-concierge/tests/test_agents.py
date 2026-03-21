"""
Unit tests for agents/catalog_agent.py and agents/logistics_agent.py.
No external services needed.
Run: pytest tests/test_agents.py -v
"""
import pytest
from agents.logistics_agent import check_delivery, list_serviceable_districts
from agents.catalog_agent import enrich_for_display


# ---------------------------------------------------------------------------
# logistics_agent tests
# ---------------------------------------------------------------------------

class TestCheckDelivery:
    def test_full_tier_exact(self):
        r = check_delivery("Colombo")
        assert r["feasible"]         is True
        assert r["tier"]             == "FULL"
        assert r["district_matched"] == "Colombo"
        assert r["estimated_days"]   == 2
        assert r["cutoff_time"]      == "2 PM"

    def test_limited_tier_exact(self):
        r = check_delivery("Jaffna")
        assert r["feasible"]         is True
        assert r["tier"]             == "LIMITED"
        assert r["estimated_days"]   == 5
        assert r["cutoff_time"]      == "12 PM"

    def test_fuzzy_match_typo(self):
        r = check_delivery("Colomboo")   # one extra 'o'
        assert r["feasible"] is True
        assert r["district_matched"] == "Colombo"

    def test_fuzzy_match_case_insensitive(self):
        r = check_delivery("kandy")
        assert r["feasible"] is True
        assert r["district_matched"] == "Kandy"

    def test_fuzzy_match_partial(self):
        r = check_delivery("Nugegod")   # missing last letter
        assert r["feasible"] is True
        assert r["district_matched"] == "Nugegoda"

    def test_unknown_district(self):
        r = check_delivery("Narnia")
        assert r["feasible"]         is False
        assert r["tier"]             == "UNKNOWN"
        assert r["district_matched"] is None
        assert r["estimated_days"]   is None

    def test_empty_string(self):
        r = check_delivery("")
        assert r["feasible"] is False
        assert r["tier"]     == "UNKNOWN"

    def test_whitespace_only(self):
        r = check_delivery("   ")
        assert r["feasible"] is False

    def test_message_present(self):
        r = check_delivery("Galle")
        assert isinstance(r["message"], str)
        assert len(r["message"]) > 0

    def test_list_serviceable_districts(self):
        tiers = list_serviceable_districts()
        assert "FULL"    in tiers
        assert "LIMITED" in tiers
        assert "Colombo" in tiers["FULL"]
        assert "Jaffna"  in tiers["LIMITED"]

    def test_all_full_districts_resolve(self):
        from agents.logistics_agent import DISTRICT_TIERS
        for d in DISTRICT_TIERS["FULL"]:
            r = check_delivery(d)
            assert r["tier"] == "FULL", f"{d} should be FULL"

    def test_all_limited_districts_resolve(self):
        from agents.logistics_agent import DISTRICT_TIERS
        for d in DISTRICT_TIERS["LIMITED"]:
            r = check_delivery(d)
            assert r["tier"] == "LIMITED", f"{d} should be LIMITED"


# ---------------------------------------------------------------------------
# catalog_agent enrich_for_display tests
# ---------------------------------------------------------------------------

class TestEnrichForDisplay:
    def _minimal_product(self, **kwargs) -> dict:
        base = {"name": "Test Product", "price": 1000.0, "url": "https://example.com", "category": "cake"}
        base.update(kwargs)
        return base

    def test_adds_missing_image_url(self):
        products = enrich_for_display([self._minimal_product()])
        assert products[0]["image_url"] == ""

    def test_preserves_existing_image_url(self):
        url = "https://static2.kapruka.com/img.jpg"
        products = enrich_for_display([self._minimal_product(image_url=url)])
        assert products[0]["image_url"] == url

    def test_adds_none_for_rating(self):
        products = enrich_for_display([self._minimal_product()])
        assert products[0]["rating"] is None

    def test_adds_empty_list_for_tags(self):
        products = enrich_for_display([self._minimal_product()])
        assert products[0]["tags"] == []

    def test_preserves_existing_tags(self):
        products = enrich_for_display([self._minimal_product(tags=["Best Seller"])])
        assert products[0]["tags"] == ["Best Seller"]

    def test_image_urls_built_from_image_url(self):
        url = "https://static2.kapruka.com/img.jpg"
        products = enrich_for_display([self._minimal_product(image_url=url)])
        assert products[0]["image_urls"] == [url]

    def test_image_urls_empty_when_no_image(self):
        products = enrich_for_display([self._minimal_product()])
        assert products[0]["image_urls"] == []

    def test_image_urls_invalid_type_reset(self):
        products = enrich_for_display([self._minimal_product(image_urls="not-a-list")])
        assert isinstance(products[0]["image_urls"], list)

    def test_does_not_mutate_input(self):
        original = self._minimal_product()
        original_copy = dict(original)
        enrich_for_display([original])
        assert original == original_copy

    def test_all_required_fields_present(self):
        products = enrich_for_display([self._minimal_product()])
        required = {"image_url", "rating", "review_count", "discount_pct",
                    "tags", "delivery_note", "ingredients", "description",
                    "original_price", "weight_grams", "image_urls"}
        for field in required:
            assert field in products[0], f"Missing field: {field}"

    def test_empty_list_returns_empty_list(self):
        assert enrich_for_display([]) == []

    def test_multiple_products_all_enriched(self):
        prods = [self._minimal_product(name=f"P{i}") for i in range(5)]
        enriched = enrich_for_display(prods)
        assert len(enriched) == 5
        for p in enriched:
            assert "rating" in p
