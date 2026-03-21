"""
phase1/ingest.py
Embed catalog.json with OpenAI embeddings and upsert into Qdrant.

RAG Strategy:
  Sliding Window Chunking
    Products with long primary text are split into overlapping windows.
    Each chunk becomes a separate Qdrant point that carries the full product
    payload, so any chunk hit at query time returns the complete product.

  CAG — Cache-Augmented Generation
    After ingestion, one "category_anchor" vector per category is stored in
    Qdrant (mean of all product embeddings in that category). The agent uses
    these anchors to identify the closest category before drilling into products.

    A companion file phase1/cag_cache.json maps each category to its top-N
    products — loaded by the agent at startup for zero-latency responses to
    common category-level queries (no Qdrant round-trip needed).
"""

import json
import os
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv()

OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL  = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
QDRANT_URL       = os.getenv("QDRANT_URL",      "http://localhost:6333")
QDRANT_API_KEY   = os.getenv("QDRANT_API_KEY",  None)

COLLECTION_NAME  = "kapruka_catalog"
BATCH_SIZE       = 50    # Qdrant upsert batch size
EMBED_BATCH_SIZE = 100   # OpenAI embedding batch size (max 2048 inputs per call)
CAG_TOP_N        = 20    # products per category in cag_cache.json

# Sliding-window params (words)
CHUNK_SIZE    = 60
CHUNK_OVERLAP = 20
MIN_CHUNK     = 10

# OpenAI embedding dimensions per model
VECTOR_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

BASE_DIR      = Path(__file__).parent
CATALOG_PATH  = BASE_DIR / "catalog.json"
CAG_CACHE_PATH = BASE_DIR / "cag_cache.json"

# ---------------------------------------------------------------------------
# Module-level OpenAI client
# ---------------------------------------------------------------------------
_openai_client: Optional[OpenAI] = None

def get_openai() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of strings using OpenAI in batches.
    Returns embeddings in the same order as input.
    """
    client = get_openai()
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        # Truncate to avoid token limit (8191 tokens for text-embedding-3-small)
        batch = [t[:6000] for t in batch]
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        # Response items are sorted by index
        sorted_data = sorted(response.data, key=lambda x: x.index)
        all_embeddings.extend([item.embedding for item in sorted_data])
        # Respect rate limits
        if i + EMBED_BATCH_SIZE < len(texts):
            time.sleep(0.3)

    return all_embeddings


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def build_primary_text(product: dict) -> str:
    parts = [
        product.get("name", ""),
        product.get("category", ""),
        product.get("description", "")[:400],
        " ".join(product.get("tags", [])),
        product.get("ingredients", "")[:200],
    ]
    return " ".join(p.strip() for p in parts if p.strip())


def sliding_window_chunks(text: str) -> list[str]:
    words = text.split()
    if len(words) <= CHUNK_SIZE:
        return [text]
    chunks = []
    start  = 0
    while start < len(words):
        end   = start + CHUNK_SIZE
        chunk = " ".join(words[start:end])
        if len(chunk.split()) >= MIN_CHUNK:
            chunks.append(chunk)
        if end >= len(words):
            break
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks or [text]


def make_chunk_text(product: dict, chunk: str) -> str:
    prefix = f"{product.get('name', '')} [{product.get('category', '')}]"
    return f"{prefix} {chunk}"


# ---------------------------------------------------------------------------
# Qdrant helpers
# ---------------------------------------------------------------------------

def build_point(
    product: dict,
    embedding: list[float],
    chunk_index: int,
    total_chunks: int,
    doc_type: str = "product_chunk",
) -> qmodels.PointStruct:
    return qmodels.PointStruct(
        id      = str(uuid.uuid4()),
        vector  = embedding,
        payload = {
            **product,
            "chunk_index":  chunk_index,
            "total_chunks": total_chunks,
            "doc_type":     doc_type,
        },
    )


def build_anchor_point(
    category: str,
    anchor_embedding: list[float],
    product_count: int,
    sample_names: list[str],
) -> qmodels.PointStruct:
    return qmodels.PointStruct(
        id      = str(uuid.uuid4()),
        vector  = anchor_embedding,
        payload = {
            "doc_type":      "category_anchor",
            "category":      category,
            "product_count": product_count,
            "sample_names":  sample_names[:5],
        },
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # ---- Load catalog ----
    with open(CATALOG_PATH, encoding="utf-8") as f:
        products: list[dict] = json.load(f)
    print(f"Loaded {len(products)} products from {CATALOG_PATH}")
    print(f"Embedding model : {EMBEDDING_MODEL}")
    vector_dim = VECTOR_DIMS.get(EMBEDDING_MODEL, 1536)
    print(f"Vector dimension: {vector_dim}\n")

    # ---- Init Qdrant ----
    client = QdrantClient(
        url     = QDRANT_URL,
        api_key = QDRANT_API_KEY or None,
        timeout = 60,
    )
    # Delete if exists, then create fresh
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in existing:
        client.delete_collection(COLLECTION_NAME)
    client.create_collection(
        collection_name = COLLECTION_NAME,
        vectors_config  = qmodels.VectorParams(
            size     = vector_dim,
            distance = qmodels.Distance.COSINE,
        ),
    )
    print(f"Collection '{COLLECTION_NAME}' recreated.\n")

    # ---- Build (text, product, chunk_index, total_chunks) tuples ----
    print("Preparing chunks with sliding-window strategy...")
    chunk_texts:    list[str]  = []
    chunk_meta:     list[tuple[dict, int, int]] = []  # (product, chunk_idx, total)
    cat_chunk_idx:  dict[str, list[int]]        = defaultdict(list)  # cat -> indices into chunk_texts

    for product in products:
        primary   = build_primary_text(product)
        chunks    = sliding_window_chunks(primary)
        total     = len(chunks)
        category  = product.get("category", "unknown")

        for idx, chunk in enumerate(chunks):
            text = make_chunk_text(product, chunk)
            cat_chunk_idx[category].append(len(chunk_texts))
            chunk_texts.append(text)
            chunk_meta.append((product, idx, total))

    print(f"Total chunks to embed: {len(chunk_texts)} "
          f"(from {len(products)} products)\n")

    # ---- Embed all chunks ----
    print("Embedding chunks via OpenAI API...")
    all_embeddings = embed_texts(chunk_texts)
    print(f"Embeddings received: {len(all_embeddings)}\n")

    # ---- Build Qdrant product points ----
    product_points: list[qmodels.PointStruct] = []
    for (product, chunk_idx, total), emb in zip(chunk_meta, all_embeddings):
        product_points.append(build_point(product, emb, chunk_idx, total))

    # ---- Build CAG category anchor points ----
    print("Building CAG category anchor vectors...")
    anchor_points: list[qmodels.PointStruct] = []
    cat_products:  dict[str, list[dict]] = defaultdict(list)

    for product in products:
        cat_products[product.get("category", "unknown")].append(product)

    for category, indices in cat_chunk_idx.items():
        # Average the first-chunk embeddings for all products in this category
        cat_embs = [all_embeddings[i] for i in indices]
        n = len(cat_embs)
        anchor_emb = [sum(col) / n for col in zip(*cat_embs)]
        sample_names = [p.get("name", "") for p in cat_products[category][:5]]
        anchor_points.append(
            build_anchor_point(category, anchor_emb, len(cat_products[category]), sample_names)
        )
        print(f"  Anchor: {category:<25} ({len(cat_products[category])} products, "
              f"{n} chunk embeddings averaged)")

    all_points = product_points + anchor_points
    print(f"\nTotal points to upsert: {len(all_points)}\n")

    # ---- Batch upsert ----
    total_pts = len(all_points)
    for batch_start in range(0, total_pts, BATCH_SIZE):
        batch = all_points[batch_start : batch_start + BATCH_SIZE]
        client.upsert(collection_name=COLLECTION_NAME, points=batch)
        print(f"  Ingested {min(batch_start + BATCH_SIZE, total_pts)}/{total_pts}...")

    # ---- Write CAG warm-up cache ----
    cag_cache = {cat: prods[:CAG_TOP_N] for cat, prods in cat_products.items()}
    with open(CAG_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cag_cache, f, ensure_ascii=False, indent=2)
    total_cached = sum(len(v) for v in cag_cache.values())
    print(f"\nCAG cache -> {CAG_CACHE_PATH} "
          f"({total_cached} products, {len(cag_cache)} categories)")

    # ---- Stats ----
    total_vectors    = client.count(COLLECTION_NAME).count
    with_images      = sum(1 for p in products if p.get("image_url"))
    with_ratings     = sum(1 for p in products if p.get("rating") is not None)
    with_ingredients = sum(1 for p in products if p.get("ingredients"))
    cat_counts       = Counter(p.get("category", "?") for p in products)

    print("\n" + "=" * 56)
    print("INGESTION COMPLETE")
    print("=" * 56)
    print(f"  Total products            : {len(products)}")
    print(f"  Total vectors in Qdrant   : {total_vectors}")
    print(f"  Vector dimension          : {vector_dim}")
    print(f"  Products with images      : {with_images}")
    print(f"  Products with ratings     : {with_ratings}")
    print(f"  Products with ingredients : {with_ingredients}")
    print(f"\n  Top categories by count:")
    for cat, cnt in cat_counts.most_common(5):
        print(f"    {cat:<25} {cnt}")
    print("=" * 56)


if __name__ == "__main__":
    main()
