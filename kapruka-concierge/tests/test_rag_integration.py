"""
Integration smoke tests for memory/lt_rag.py.
Requires: Qdrant running on localhost:6333  AND  catalog already ingested.

Run: pytest tests/test_rag_integration.py -v -m integration
Skip if services unavailable: pytest tests/test_rag_integration.py -v -m integration --ignore-glob="*integration*"
"""
import pytest

# Mark every test in this file as requiring live services
pytestmark = pytest.mark.integration


def _qdrant_available() -> bool:
    try:
        from qdrant_client import QdrantClient
        c = QdrantClient(url="http://localhost:6333", timeout=3)
        c.get_collections()
        return True
    except Exception:
        return False


skip_if_no_qdrant = pytest.mark.skipif(
    not _qdrant_available(),
    reason="Qdrant not running on localhost:6333",
)


@skip_if_no_qdrant
def test_search_returns_results():
    from memory.lt_rag import search
    results = search("birthday cake for wife", top_k=5)
    assert len(results) > 0


@skip_if_no_qdrant
def test_search_result_has_required_fields():
    from memory.lt_rag import search
    results = search("chocolate gift", top_k=3)
    for r in results:
        assert "name"      in r, "Missing 'name'"
        assert "price"     in r, "Missing 'price'"
        assert "url"       in r, "Missing 'url'"
        assert "image_url" in r, "Missing 'image_url'"
        assert "score"     in r, "Missing 'score'"


@skip_if_no_qdrant
def test_search_score_is_between_0_and_1():
    from memory.lt_rag import search
    results = search("flowers for mother", top_k=5)
    for r in results:
        assert 0.0 <= r["score"] <= 1.0


@skip_if_no_qdrant
def test_search_no_duplicate_urls():
    from memory.lt_rag import search
    results = search("gift", top_k=8)
    urls = [r.get("url") for r in results if r.get("url")]
    assert len(urls) == len(set(urls)), "Duplicate product URLs in results"


@skip_if_no_qdrant
def test_search_excluding_filters_correctly():
    from memory.lt_rag import search, search_excluding
    base = search("chocolate", top_k=3)
    exclude = [r["name"] for r in base[:2]]
    filtered = search_excluding("chocolate", exclude_names=exclude, top_k=5)
    result_names = [r["name"] for r in filtered]
    for ex in exclude:
        assert ex not in result_names


@skip_if_no_qdrant
def test_search_by_category_respects_filter():
    from memory.lt_rag import search_by_category
    results = search_by_category("cake", "birthday celebration", top_k=5)
    for r in results:
        assert r.get("category") == "cake", f"Unexpected category: {r.get('category')}"


@skip_if_no_qdrant
def test_search_by_category_unknown_returns_empty_or_small():
    from memory.lt_rag import search_by_category
    results = search_by_category("nonexistent_cat_xyz", "anything", top_k=5)
    assert isinstance(results, list)


@skip_if_no_qdrant
def test_get_category_anchor_exists():
    from memory.lt_rag import get_category_anchor
    anchor = get_category_anchor("cake")
    assert anchor is not None
    assert anchor.get("doc_type") == "category_anchor"
    assert anchor.get("category") == "cake"


@skip_if_no_qdrant
def test_get_category_anchor_missing_returns_none():
    from memory.lt_rag import get_category_anchor
    anchor = get_category_anchor("does_not_exist")
    assert anchor is None
