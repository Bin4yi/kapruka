"""
Smoke test: verifies catalog.json and cag_cache.json are well-formed.
No network required — just checks the files on disk.

Run: pytest tests/test_ingest_smoke.py -v
"""
import json
from pathlib import Path

BASE = Path(__file__).parent.parent / "phase1"
CATALOG   = BASE / "catalog.json"
CAG_CACHE = BASE / "cag_cache.json"


def test_catalog_exists():
    assert CATALOG.exists(), f"{CATALOG} not found — run phase1/scraper.py first"


def test_catalog_not_empty():
    with open(CATALOG, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list)
    assert len(data) > 0, "catalog.json is empty"


def test_catalog_product_fields():
    with open(CATALOG, encoding="utf-8") as f:
        data = json.load(f)
    required = {"name", "price", "url", "image_url", "category", "scraped_at"}
    for product in data[:10]:
        missing = required - product.keys()
        assert not missing, f"Product missing fields: {missing}\n{product}"


def test_catalog_prices_are_numeric_or_none():
    with open(CATALOG, encoding="utf-8") as f:
        data = json.load(f)
    for p in data:
        price = p.get("price")
        assert price is None or isinstance(price, (int, float)), \
            f"Bad price type: {price!r} in {p.get('name')}"


def test_catalog_image_urls_absolute():
    with open(CATALOG, encoding="utf-8") as f:
        data = json.load(f)
    for p in data:
        url = p.get("image_url", "")
        if url:
            assert url.startswith("https://"), \
                f"Non-absolute image_url: {url!r} in {p.get('name')}"


def test_catalog_categories_known():
    expected = {
        "cake", "food-hampers", "flowers", "chocolates", "fruit-baskets",
        "personalised-gifts", "electronics", "toys", "fashion", "beauty",
        "home-and-garden", "books",
    }
    with open(CATALOG, encoding="utf-8") as f:
        data = json.load(f)
    found = {p.get("category") for p in data}
    unknown = found - expected
    assert not unknown, f"Unexpected categories found: {unknown}"


def test_cag_cache_exists():
    assert CAG_CACHE.exists(), \
        f"{CAG_CACHE} not found — run phase1/ingest.py first"


def test_cag_cache_structure():
    with open(CAG_CACHE, encoding="utf-8") as f:
        cache = json.load(f)
    assert isinstance(cache, dict)
    assert len(cache) > 0
    for cat, products in cache.items():
        assert isinstance(products, list), f"Category {cat!r} value is not a list"
        for p in products:
            assert "name" in p, f"Product in {cat!r} missing 'name'"
            assert "url"  in p, f"Product in {cat!r} missing 'url'"
