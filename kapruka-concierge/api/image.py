"""
api/image.py
Image proxy with local disk cache.

GET /api/image?url={encoded_image_url}

Fetches the remote image on behalf of the frontend (bypasses hotlink
restrictions), caches it by URL-hash in IMAGE_CACHE_DIR, and returns
it with a one-day Cache-Control header.

Falls back to a 1×1 transparent PNG on any fetch error.
"""

import hashlib
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter
from fastapi.responses import Response

load_dotenv()

router = APIRouter(prefix="")

_CACHE_DIR = Path(os.getenv("IMAGE_CACHE_DIR", "image_cache"))
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 1×1 transparent PNG (67 bytes)
_FALLBACK_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KaprukaConcierge/1.0)",
    "Referer":    "https://www.kapruka.com/",
    "Accept":     "image/webp,image/jpeg,image/*",
}

_CACHE_CONTROL = "public, max-age=86400"


def _cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode()).hexdigest()
    return _CACHE_DIR / digest


@router.get("/api/image")
async def proxy_image(url: str) -> Response:
    """Proxy a remote image URL, caching the result on disk."""
    if not url:
        return Response(content=_FALLBACK_PNG, media_type="image/png",
                        headers={"Cache-Control": _CACHE_CONTROL})

    cache_file = _cache_path(url)
    meta_file  = cache_file.with_suffix(".meta")

    # Serve from cache if present
    if cache_file.exists() and meta_file.exists():
        content_type = meta_file.read_text(encoding="utf-8").strip()
        return Response(
            content=cache_file.read_bytes(),
            media_type=content_type,
            headers={"Cache-Control": _CACHE_CONTROL},
        )

    # Fetch from origin
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers=_HEADERS)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        body = resp.content

        # Persist to cache
        cache_file.write_bytes(body)
        meta_file.write_text(content_type, encoding="utf-8")

        return Response(
            content=body,
            media_type=content_type,
            headers={"Cache-Control": _CACHE_CONTROL},
        )

    except Exception:
        return Response(
            content=_FALLBACK_PNG,
            media_type="image/png",
            headers={"Cache-Control": _CACHE_CONTROL},
        )
