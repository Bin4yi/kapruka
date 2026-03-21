"""
memory/lt_rag.py
Long-term RAG retrieval from Qdrant using OpenAI embeddings.

Note: SentenceTransformer is NOT used here because this project switched to
OpenAI text-embedding-3-small (sentence-transformers causes DLL failures on
this machine and would conflict with another app using all-MiniLM-L6-v2).
All vectors in the Qdrant collection were produced by text-embedding-3-small,
so queries must use the same model.
"""

import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

load_dotenv()

# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

QDRANT_URL      = os.getenv("QDRANT_URL",      "http://localhost:6333")
QDRANT_API_KEY  = os.getenv("QDRANT_API_KEY",  None)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
COLLECTION_NAME = "kapruka_catalog"

_qdrant_client: Optional[QdrantClient] = None
_openai_client: Optional[OpenAI]       = None


def _qdrant() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(
            url     = QDRANT_URL,
            api_key = QDRANT_API_KEY or None,
            timeout = 30,
        )
    return _qdrant_client


def _openai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


def _embed(text: str) -> list[float]:
    """Embed a single query string."""
    response = _openai().embeddings.create(
        model = EMBEDDING_MODEL,
        input = text[:6000],
    )
    return response.data[0].embedding


def _payload_to_result(hit) -> dict:
    """Convert a Qdrant ScoredPoint to a plain dict with a 'score' key."""
    result = dict(hit.payload or {})
    result["score"] = round(hit.score, 4)
    return result


def _query(vector: list[float], top_k: int, query_filter) -> list:
    """
    Compatibility wrapper: uses query_points() (qdrant-client >= 1.9)
    which replaced the deprecated search() method.
    Returns a flat list of ScoredPoint objects.
    """
    response = _qdrant().query_points(
        collection_name = COLLECTION_NAME,
        query           = vector,
        limit           = top_k,
        query_filter    = query_filter,
        with_payload    = True,
    )
    return response.points


# ---------------------------------------------------------------------------
# Public search functions
# ---------------------------------------------------------------------------

def search(query: str, top_k: int = 8) -> list[dict]:
    """
    Embed query and retrieve top_k most similar products from Qdrant.
    Only returns product_chunk points (not category anchors).
    Each result dict contains the full product payload + 'score'.
    """
    vector = _embed(query)
    hits = _query(
        vector,
        top_k,
        qmodels.Filter(must=[qmodels.FieldCondition(
            key="doc_type", match=qmodels.MatchValue(value="product_chunk"),
        )]),
    )
    # De-duplicate by product URL (multiple chunks can hit for the same product)
    seen: set[str] = set()
    results: list[dict] = []
    for hit in hits:
        payload = _payload_to_result(hit)
        url = payload.get("url", "")
        if url and url in seen:
            continue
        seen.add(url)
        results.append(payload)
    return results


def search_excluding(
    query: str,
    exclude_names: list[str],
    top_k: int = 8,
) -> list[dict]:
    """
    Like search() but filters out products whose names appear in exclude_names.
    Fetches top_k * 4 candidates to ensure enough remain after filtering.
    """
    candidates = search(query, top_k=top_k * 4)
    exclude_set = {n.lower().strip() for n in exclude_names}
    filtered = [
        p for p in candidates
        if p.get("name", "").lower().strip() not in exclude_set
    ]
    return filtered[:top_k]


def search_by_category(
    category: str,
    query: str,
    top_k: int = 5,
) -> list[dict]:
    """
    Retrieve products filtered to a specific category, ranked by embedding
    similarity to query.
    """
    vector = _embed(query)
    hits = _query(
        vector,
        top_k,
        qmodels.Filter(must=[
            qmodels.FieldCondition(key="doc_type", match=qmodels.MatchValue(value="product_chunk")),
            qmodels.FieldCondition(key="category", match=qmodels.MatchValue(value=category)),
        ]),
    )
    seen: set[str] = set()
    results: list[dict] = []
    for hit in hits:
        payload = _payload_to_result(hit)
        url = payload.get("url", "")
        if url and url in seen:
            continue
        seen.add(url)
        results.append(payload)
    return results


def get_category_anchor(category: str) -> Optional[dict]:
    """
    Return the CAG category_anchor payload for a given category, or None.
    Used by the agent to confirm which category best matches user intent.
    """
    hits = _qdrant().scroll(
        collection_name = COLLECTION_NAME,
        scroll_filter   = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key   = "doc_type",
                    match = qmodels.MatchValue(value="category_anchor"),
                ),
                qmodels.FieldCondition(
                    key   = "category",
                    match = qmodels.MatchValue(value=category),
                ),
            ]
        ),
        limit        = 1,
        with_payload = True,
    )
    points = hits[0]
    return dict(points[0].payload) if points else None
