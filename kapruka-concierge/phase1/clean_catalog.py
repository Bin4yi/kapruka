"""
phase1/clean_catalog.py
Removes Cloudflare bot-protection placeholder text from product descriptions
so that ingest.py produces clean, meaningful embeddings.

Run once before (re-)ingesting:
    py phase1/clean_catalog.py
    py phase1/ingest.py
"""

import json
from pathlib import Path

CATALOG_PATH = Path(__file__).parent / "catalog.json"

# Fragments that signal a Cloudflare / bot-protection page instead of real content
BOT_SIGNALS = [
    "security service to protect",
    "verifies you are not a bot",
    "Ray ID",
    "Cloudflare",
    "enable JavaScript",
    "Please enable cookies",
    "DDoS protection",
    "Access denied",
]


def is_bot_text(text: str) -> bool:
    lower = text.lower()
    return any(sig.lower() in lower for sig in BOT_SIGNALS)


def clean_product(product: dict) -> tuple[dict, bool]:
    """Return (cleaned_product, was_changed)."""
    desc = product.get("description", "") or ""
    if desc and is_bot_text(desc):
        p = dict(product)
        p["description"] = ""
        return p, True
    return product, False


def main() -> None:
    with open(CATALOG_PATH, encoding="utf-8") as f:
        products: list[dict] = json.load(f)

    print(f"Loaded {len(products)} products from {CATALOG_PATH}")

    cleaned, changed_count = [], 0
    for p in products:
        cp, changed = clean_product(p)
        cleaned.append(cp)
        if changed:
            changed_count += 1

    print(f"Cleaned {changed_count} / {len(products)} products with bot-protection descriptions.")

    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    print(f"Saved cleaned catalog to {CATALOG_PATH}")
    print("\nNext step: re-embed and re-ingest into Qdrant:")
    print("  py phase1/ingest.py")


if __name__ == "__main__":
    main()
