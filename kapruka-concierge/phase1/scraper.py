"""
phase1/scraper.py
Scrapes structured product data from kapruka.com across all configured categories.

HTML structure (confirmed via inspection):
  Card:       div.catalogueV2Repeater
  Name:       div.catalogueV2heading
  Price:      span.catalogueV2converted  ("RS.6,090")
  Image:      img[src]  (absolute https://static2.kapruka.com/...)
  URL:        a[href*="/buyonline/"]
  Tags:       .ribbon-drop span  |  .thumb-text span
  Schema:     <script type="application/ld+json"> per card

Outputs: phase1/catalog.json
Errors:  phase1/scrape_errors.log
"""

import asyncio
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv()

CATEGORIES: dict[str, str] = {
    "cake":              "https://www.kapruka.com/online/cakes",
    "food-hampers":      "https://www.kapruka.com/online/grocery",
    "flowers":           "https://www.kapruka.com/online/flowers",
    "chocolates":        "https://www.kapruka.com/online/chocolates",
    "fruit-baskets":     "https://www.kapruka.com/online/fruitbaskets",
    "personalised-gifts":"https://www.kapruka.com/online/customizedGifts",
    "electronics":       "https://www.kapruka.com/online/electronics",
    "toys":              "https://www.kapruka.com/online/softtoy",
    "fashion":           "https://www.kapruka.com/online/fashion",
    "beauty":            "https://www.kapruka.com/online/cosmetics",
    "home-and-garden":   "https://www.kapruka.com/online/home_lifestyle",
    "books":             "https://www.kapruka.com/online/books",
}

MAX_PRODUCTS_PER_CATEGORY: int = int(os.getenv("MAX_PRODUCTS_PER_CATEGORY", "200"))
DELAY_MIN: float               = float(os.getenv("SCRAPE_DELAY_MIN", "0.8"))
DELAY_MAX: float               = float(os.getenv("SCRAPE_DELAY_MAX", "2.5"))
DETAIL_PAGES_PER_CATEGORY: int = 30

BASE_DIR = Path(__file__).parent
OUT_FILE = BASE_DIR / "catalog.json"
LOG_FILE = BASE_DIR / "scrape_errors.log"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Kapruka-specific selectors (confirmed)
CARD_SEL      = "div.catalogueV2Repeater"
NAME_SEL      = "div.catalogueV2heading"
PRICE_SEL     = "span.catalogueV2converted"
IMG_SEL       = "img"
LINK_SEL      = "a[href*='/buyonline/']"
BADGE_SEL     = ".ribbon-drop span"
THUMB_SEL     = ".thumb-text span"
JSONLD_SEL    = "script[type='application/ld+json']"
MARKET_PRICE_SEL = ".marketPrice, .market-price, .strikethrough, s, del"

SCROLL_STEP     = 800    # px per scroll
STALL_THRESHOLD = 3      # consecutive no-growth scrolls before stopping
SCROLL_WAIT_MS      = 2000   # ms to wait after each scroll (no networkidle — site never idles)
RETRY_DELAY_S       = 3      # seconds before retry on failure
PAGE_LOAD_WAIT      = 2000   # ms minimum wait after domcontentloaded
CARD_APPEAR_TIMEOUT = 30000  # ms to wait for first card to appear in DOM
DETAIL_PAGE_WAIT    = 2000   # ms to wait on each detail page
DETAIL_CONCURRENCY  = 3      # parallel detail pages per category

LOAD_MORE_SELECTORS = [
    "button:has-text('Load More')",
    "button:has-text('Show More')",
    "a:has-text('Load More')",
    "a:has-text('Show More')",
    ".load-more", "#load-more",
    "[class*='loadmore']", "[class*='load-more']",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def random_delay() -> None:
    await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


def parse_price(raw: str) -> Optional[float]:
    """Strip 'RS.', 'Rs.', commas, whitespace → float."""
    if not raw:
        return None
    cleaned = re.sub(r"[^\d.]", "", raw.replace(",", ""))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def ensure_absolute(url: str, base: str = "https://www.kapruka.com") -> str:
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http"):
        return url
    return urljoin(base, url)


def extract_weight(text: str) -> Optional[int]:
    """Return weight in grams if mentioned in text."""
    if not text:
        return None
    # "1.44 Lbs" → grams
    lbs = re.search(r"(\d+(?:\.\d+)?)\s*lbs?", text, re.IGNORECASE)
    if lbs:
        return int(float(lbs.group(1)) * 453.592)
    kg = re.search(r"(\d+(?:\.\d+)?)\s*kg", text, re.IGNORECASE)
    if kg:
        return int(float(kg.group(1)) * 1000)
    g = re.search(r"(\d+)\s*g(?:ram)?s?", text, re.IGNORECASE)
    if g:
        return int(g.group(1))
    return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_jsonld(raw: str) -> dict:
    """Parse a schema.org JSON-LD blob, return {} on failure."""
    try:
        return json.loads(raw)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Category-page scraping
# ---------------------------------------------------------------------------

async def click_load_more_if_present(page: Page) -> bool:
    for sel in LOAD_MORE_SELECTORS:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(SCROLL_WAIT_MS)
                return True
        except Exception:
            continue
    return False


async def scroll_until_stalled(page: Page) -> None:
    """Scroll down until no new cards appear for STALL_THRESHOLD consecutive scrolls."""
    stalls     = 0
    prev_count = 0

    while True:
        count = await page.locator(CARD_SEL).count()

        if count >= MAX_PRODUCTS_PER_CATEGORY:
            break

        if count == prev_count:
            stalls += 1
        else:
            stalls = 0
        prev_count = count

        if stalls >= STALL_THRESHOLD:
            clicked = await click_load_more_if_present(page)
            if not clicked:
                break
            stalls = 0
            continue

        await page.evaluate(f"window.scrollBy(0, {SCROLL_STEP})")
        await page.wait_for_timeout(SCROLL_WAIT_MS)


async def parse_card(page: Page, card_index: int, category: str) -> dict:
    """
    Extract all fields from the card at the given index.
    Primary source: embedded JSON-LD (clean, structured).
    Fallback: DOM selectors.
    """
    card = page.locator(CARD_SEL).nth(card_index)

    # ---- JSON-LD (most reliable source for name/price/image/url/availability) ----
    jsonld: dict = {}
    try:
        ld_els = card.locator(JSONLD_SEL)
        if await ld_els.count() > 0:
            raw_ld = await ld_els.first.inner_text()
            jsonld = parse_jsonld(raw_ld)
    except Exception:
        pass

    offers = jsonld.get("offers", {})

    # ---- URL ----
    url = jsonld.get("url", "")
    if not url:
        try:
            link = card.locator(LINK_SEL).first
            if await link.count() > 0:
                href = await link.get_attribute("href")
                url = ensure_absolute(href or "")
        except Exception:
            pass

    # ---- Name ----
    name = jsonld.get("name", "").strip()
    if not name:
        try:
            el = card.locator(NAME_SEL).first
            if await el.count() > 0:
                name = (await el.inner_text()).strip()
        except Exception:
            pass

    # ---- Price (current) ----
    price: Optional[float] = None
    raw_price = str(offers.get("price", ""))
    if raw_price:
        price = parse_price(raw_price)
    if price is None:
        try:
            el = card.locator(PRICE_SEL).first
            if await el.count() > 0:
                price = parse_price(await el.inner_text())
        except Exception:
            pass

    # ---- Original / market price ----
    original_price: Optional[float] = None
    try:
        el = card.locator(MARKET_PRICE_SEL).first
        if await el.count() > 0:
            original_price = parse_price(await el.inner_text())
    except Exception:
        pass

    discount_pct: Optional[float] = None
    if price and original_price and original_price > price:
        discount_pct = round((1 - price / original_price) * 100, 1)

    # ---- Image ----
    image_url = ensure_absolute(jsonld.get("image", ""))
    if not image_url or not image_url.startswith("https"):
        try:
            img = card.locator(IMG_SEL).first
            if await img.count() > 0:
                src = (await img.get_attribute("src")) or ""
                image_url = ensure_absolute(src)
        except Exception:
            pass

    # ---- Availability ----
    avail_str = offers.get("availability", "InStock")
    availability = "OutOfStock" not in avail_str and "SoldOut" not in avail_str

    # ---- Tags & weight hint from badges ----
    tags: list[str] = []
    weight_grams: Optional[int] = None

    try:
        badge_els = card.locator(BADGE_SEL)
        for i in range(await badge_els.count()):
            t = (await badge_els.nth(i).inner_text()).strip()
            if t and t not in tags:
                tags.append(t)
    except Exception:
        pass

    try:
        thumb_els = card.locator(THUMB_SEL)
        for i in range(await thumb_els.count()):
            t = (await thumb_els.nth(i).inner_text()).strip()
            if t:
                w = extract_weight(t)
                if w:
                    weight_grams = w
                if t not in tags:
                    tags.append(t)
    except Exception:
        pass

    return {
        "name":           name,
        "price":          price,
        "original_price": original_price,
        "discount_pct":   discount_pct,
        "description":    "",
        "availability":   availability,
        "image_url":      image_url,
        "image_urls":     [image_url] if image_url else [],
        "rating":         None,
        "review_count":   None,
        "tags":           tags,
        "weight_grams":   weight_grams,
        "delivery_note":  "",
        "url":            url,
        "category":       category,
        "scraped_at":     now_iso(),
    }


# ---------------------------------------------------------------------------
# Detail page scraping
# ---------------------------------------------------------------------------

async def scrape_detail_page(page: Page, product: dict) -> dict:
    """Visit product URL and enrich with full description, gallery, ratings, ingredients."""
    url = product.get("url", "")
    if not url:
        return product

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(DETAIL_PAGE_WAIT)

        # ---- Full description ----
        description = ""
        for sel in [
            ".rebrand_delivery_product .description",
            ".product-description",
            "#product-description",
            "[class*='description']",
            ".productDetails",
            "[class*='productDetail']",
            ".detail-desc",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    t = (await el.inner_text()).strip()
                    if len(t) > 30:
                        description = t
                        break
            except Exception:
                pass

        # meta fallbacks
        if not description:
            for meta in ["meta[name='description']", "meta[property='og:description']"]:
                try:
                    el = page.locator(meta).first
                    if await el.count() > 0:
                        c = await el.get_attribute("content")
                        if c and len(c) > 30:
                            description = c.strip()
                            break
                except Exception:
                    pass

        if description:
            product["description"] = description

        # ---- Gallery images (up to 8) ----
        gallery: list[str] = list(product.get("image_urls", []))
        for sel in [
            ".gallery img",
            ".product-gallery img",
            ".thumbnails img",
            ".swiper-slide img",
            "[class*='gallery'] img",
            "[class*='thumb'] img",
            "[class*='zoom'] img",
            ".slick-slide img",
        ]:
            try:
                imgs = page.locator(sel)
                n    = await imgs.count()
                for i in range(n):
                    src = (await imgs.nth(i).get_attribute("src")) or ""
                    src = ensure_absolute(src)
                    if src.startswith("https") and src not in gallery:
                        gallery.append(src)
                if len(gallery) >= 8:
                    break
            except Exception:
                pass

        if gallery:
            product["image_urls"] = gallery[:8]
            product["image_url"]  = gallery[0]

        # ---- Rating ----
        for sel in [
            "[itemprop='ratingValue']",
            ".rating-value",
            ".avg-rating",
            "[class*='rating-value']",
            "[class*='avgRating']",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    txt = (await el.inner_text()).strip()
                    m   = re.search(r"(\d+(?:\.\d+)?)", txt)
                    if m:
                        product["rating"] = float(m.group(1))
                        break
                    val = await el.get_attribute("content")
                    if val:
                        product["rating"] = float(val)
                        break
            except Exception:
                pass

        # ---- Review count ----
        for sel in [
            "[itemprop='reviewCount']",
            ".review-count",
            "[class*='reviewCount']",
            "[class*='numReview']",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    txt = (await el.inner_text()).strip()
                    m   = re.search(r"(\d+)", txt)
                    if m:
                        product["review_count"] = int(m.group(1))
                        break
                    val = await el.get_attribute("content")
                    if val:
                        product["review_count"] = int(val)
                        break
            except Exception:
                pass

        # ---- Ingredients (allergy detection) ----
        ingredients = ""
        for sel in [
            "[class*='ingredient']",
            "[id*='ingredient']",
            "div:has(strong:has-text('Ingredient'))",
            "div:has(b:has-text('Ingredient'))",
            "section:has(h2:has-text('Ingredient'))",
            "section:has(h3:has-text('Ingredient'))",
            "li:has-text('Ingredient')",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    t = (await el.inner_text()).strip()
                    if t:
                        ingredients = t
                        break
            except Exception:
                pass

        if ingredients:
            product["ingredients"] = ingredients

        # ---- Weight ----
        if not product.get("weight_grams"):
            combined = description + " " + ingredients
            w = extract_weight(combined)
            if w:
                product["weight_grams"] = w

            # Scan spec table rows
            for sel in ["table tr", ".spec-row", "[class*='specification'] li", "[class*='attribute'] li"]:
                try:
                    rows = page.locator(sel)
                    for i in range(await rows.count()):
                        row_text = (await rows.nth(i).inner_text()).strip()
                        if re.search(r"weight|gram|kg|lbs?", row_text, re.IGNORECASE):
                            ww = extract_weight(row_text)
                            if ww:
                                product["weight_grams"] = ww
                                break
                except Exception:
                    pass

        # ---- Delivery note ----
        if not product.get("delivery_note"):
            for sel in [
                "[class*='delivery']",
                "[class*='shipping']",
                "[id*='delivery']",
                ".deliveryInfo",
            ]:
                try:
                    el = page.locator(sel).first
                    if await el.count() > 0:
                        t = (await el.inner_text()).strip()
                        if t:
                            product["delivery_note"] = t[:200]
                            break
                except Exception:
                    pass

    except Exception as exc:
        log.error("Detail page error (%s): %s", url, exc)

    return product


# ---------------------------------------------------------------------------
# Category scraper
# ---------------------------------------------------------------------------

async def scrape_category(
    context: BrowserContext,
    category: str,
    cat_url: str,
) -> tuple[list[dict], int, int]:
    """Scrape one category. Returns (products, detail_fetched, failed_detail)."""

    page = await context.new_page()
    products: list[dict] = []

    async def _load() -> bool:
        try:
            await page.goto(cat_url, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(PAGE_LOAD_WAIT)

            # Some categories only lazy-load cards after the first scroll.
            # Do 3 priming scrolls before waiting for the selector.
            for _ in range(3):
                if await page.locator(CARD_SEL).count() > 0:
                    break
                await page.evaluate(f"window.scrollBy(0, {SCROLL_STEP})")
                await page.wait_for_timeout(1500)

            # If still nothing, give it the full timeout
            if await page.locator(CARD_SEL).count() == 0:
                try:
                    await page.wait_for_selector(CARD_SEL, timeout=CARD_APPEAR_TIMEOUT)
                except Exception:
                    pass

            # Scroll back to top so the main scroll loop starts fresh
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(500)
            return True
        except Exception as exc:
            log.error("Category load failed (%s): %s", category, exc)
            return False

    if not await _load():
        log.info("Retrying %s in %ds...", category, RETRY_DELAY_S)
        await asyncio.sleep(RETRY_DELAY_S)
        if not await _load():
            await page.close()
            return [], 0, 0

    # Check cards loaded
    initial = await page.locator(CARD_SEL).count()
    if initial == 0:
        log.warning("[%s] No cards found with selector '%s'", category, CARD_SEL)
        await page.close()
        return [], 0, 0

    log.info("[%s] Initial cards: %d — scrolling for more...", category, initial)

    # Scroll to load more products
    await scroll_until_stalled(page)

    total_cards = min(await page.locator(CARD_SEL).count(), MAX_PRODUCTS_PER_CATEGORY)
    log.info("[%s] Total cards after scroll: %d", category, total_cards)

    # Parse all cards
    for i in range(total_cards):
        try:
            product = await parse_card(page, i, category)
            if product["name"] or product["url"]:
                products.append(product)
        except Exception as exc:
            log.error("[%s] Card %d parse error: %s", category, i, exc)

    await page.close()

    # ---- Detail pages (top DETAIL_PAGES_PER_CATEGORY) concurrently ----
    detail_fetched = 0
    failed_detail  = 0
    sem            = asyncio.Semaphore(DETAIL_CONCURRENCY)

    async def fetch_detail(product: dict, stagger_idx: int) -> tuple[dict, bool]:
        """Fetch one detail page under the semaphore. Returns (product, success)."""
        if not product.get("url"):
            return product, False
        # Stagger launches so all slots don't hit the server simultaneously
        await asyncio.sleep(stagger_idx * 0.5)
        async with sem:
            page = await context.new_page()
            try:
                enriched = await scrape_detail_page(page, product)
                return enriched, True
            except Exception as exc:
                log.error("[%s] Detail error (%s): %s", category, product.get("url"), exc)
                await asyncio.sleep(RETRY_DELAY_S)
                try:
                    enriched = await scrape_detail_page(page, product)
                    return enriched, True
                except Exception as exc2:
                    log.error("[%s] Detail retry failed (%s): %s", category, product.get("url"), exc2)
                    return product, False
            finally:
                await page.close()

    targets  = products[:DETAIL_PAGES_PER_CATEGORY]
    results  = await asyncio.gather(*[fetch_detail(p, i) for i, p in enumerate(targets)])

    for i, (enriched, ok) in enumerate(results):
        products[i] = enriched
        if ok:
            detail_fetched += 1
        else:
            failed_detail += 1

    return products, detail_fetched, failed_detail


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    start = time.time()
    all_products: list[dict] = []
    summary: dict[str, dict] = {}

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(headless=True)
        context: BrowserContext = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            timezone_id="Asia/Colombo",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;"
                    "q=0.9,image/avif,image/webp,*/*;q=0.8"
                ),
            },
        )

        # Block fonts, media — keep images and scripts (needed for JS rendering)
        await context.route(
            "**/*.{mp4,mp3,woff,woff2,ttf,otf,pdf}",
            lambda route, _: route.abort(),
        )

        for category, cat_url in CATEGORIES.items():
            log.info("=" * 60)
            log.info("Scraping: %s -> %s", category, cat_url)
            try:
                products, detail_fetched, failed_detail = await scrape_category(
                    context, category, cat_url
                )
            except Exception as exc:
                log.error("Category %s crashed: %s", category, exc)
                products, detail_fetched, failed_detail = [], 0, 0

            all_products.extend(products)
            summary[category] = {
                "products_found": len(products),
                "detail_fetched": detail_fetched,
                "detail_failed":  failed_detail,
            }
            log.info(
                "[%s] products=%d  detail=%d  failed=%d",
                category, len(products), detail_fetched, failed_detail,
            )
            await random_delay()

        await context.close()
        await browser.close()

    # Save output
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)

    # -----------------------------------------------------------------------
    # Print stats
    # -----------------------------------------------------------------------
    elapsed = time.time() - start

    print("\n" + "=" * 60)
    print("PER-CATEGORY STATS")
    print("=" * 60)
    for cat, s in summary.items():
        print(
            f"  {cat:<22} products={s['products_found']:>4}  "
            f"detail={s['detail_fetched']:>3}  "
            f"failed={s['detail_failed']:>2}"
        )

    total              = len(all_products)
    total_with_images  = sum(1 for p in all_products if p.get("image_url"))
    total_with_ratings = sum(1 for p in all_products if p.get("rating") is not None)
    total_with_ingred  = sum(1 for p in all_products if p.get("ingredients"))

    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)
    print(f"  Total products   : {total}")
    print(f"  With images      : {total_with_images}")
    print(f"  With ratings     : {total_with_ratings}")
    print(f"  With ingredients : {total_with_ingred}")
    print(f"  Runtime          : {elapsed:.1f}s")
    print(f"  Output           : {OUT_FILE}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
