"""
phase1/image_proxy_cache.py
Utility for routing product images through the FastAPI image proxy endpoint.

All kapruka.com CDN image URLs are rewritten to:
    /api/image?url={percent_encoded_original_url}

The FastAPI handler at api/routes/image.py fetches the image, caches it
locally under IMAGE_CACHE_DIR, and re-serves it — avoiding CORS errors and
CDN hotlink protection that would block the frontend from loading images
directly.
"""

import hashlib
import os
from pathlib import Path
from urllib.parse import quote, urlparse

from dotenv import load_dotenv

load_dotenv()

IMAGE_CACHE_DIR = Path(os.getenv("IMAGE_CACHE_DIR", "image_cache"))

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def proxy_url(original_url: str) -> str:
    """
    Convert a direct CDN image URL to the local proxy path.

    Example:
        https://static2.kapruka.com/product-image/.../cake.jpg
        ->  /api/image?url=https%3A%2F%2Fstatic2.kapruka.com%2F...%2Fcake.jpg
    """
    if not original_url:
        return ""
    return f"/api/image?url={quote(original_url, safe='')}"


def cache_path(original_url: str) -> Path:
    """
    Deterministic local path for a cached image.
    Uses a SHA-256 hash of the URL + the original file extension.

    Example:
        https://static2.kapruka.com/.../1742029856271_cupies.jpg
        ->  image_cache/a3f9c1.jpg
    """
    parsed    = urlparse(original_url)
    ext       = Path(parsed.path).suffix or ".jpg"
    url_hash  = hashlib.sha256(original_url.encode()).hexdigest()[:12]
    IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return IMAGE_CACHE_DIR / f"{url_hash}{ext}"


def is_cached(original_url: str) -> bool:
    """Return True if the image is already in the local cache."""
    return cache_path(original_url).exists()


def rewrite_product_images(product: dict) -> dict:
    """
    Return a shallow copy of *product* with all image URLs rewritten to
    proxy URLs. Safe to call on the full product payload dict.
    """
    out = dict(product)
    if out.get("image_url"):
        out["image_url"] = proxy_url(out["image_url"])
    if out.get("image_urls"):
        out["image_urls"] = [proxy_url(u) for u in out["image_urls"] if u]
    return out


# ---------------------------------------------------------------------------
# Bulk rewrite helpers (used by ingest / agent)
# ---------------------------------------------------------------------------

def rewrite_catalog(products: list[dict]) -> list[dict]:
    """Rewrite image URLs for an entire list of product dicts."""
    return [rewrite_product_images(p) for p in products]
