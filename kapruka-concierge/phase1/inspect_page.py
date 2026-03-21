"""
Quick diagnostic: dumps the inner HTML of a kapruka category page
so we can find the correct CSS selectors for product cards.
"""
import asyncio
import sys
import io
# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from playwright.async_api import async_playwright

URL = "https://www.kapruka.com/online/chocolates"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=USER_AGENT,
                                        viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()

        print(f"Loading {URL} ...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(6000)

        # Scroll all the way to the bottom
        for _ in range(20):
            await page.evaluate("window.scrollBy(0, 800)")
            await page.wait_for_timeout(1200)

        await page.wait_for_timeout(3000)
        print(f"\nCard count after full scroll: {await page.locator('div.catalogueV2Repeater').count()}")

        # --- probe specific kapruka selectors first ---
        kapruka_probes = [
            ".catalogueV2Repeater",
            ".CatalogueV2Design",
            ".itemF",
            ".carousel-itemkk",
            ".rebrand_delivery_product",
            "[class*='catalogue']",
            "[class*='Catalogue']",
            "[class*='rebrand']",
        ]
        print("\n===== KAPRUKA-SPECIFIC SELECTOR PROBE =====")
        for sel in kapruka_probes:
            try:
                n = await page.locator(sel).count()
                if n > 0:
                    print(f"  {sel:<40} -> {n} elements")
                    el = page.locator(sel).first
                    cls = await el.get_attribute("class") or ""
                    tag = await el.evaluate("el => el.tagName.toLowerCase()")
                    inner = (await el.inner_text())[:120].replace("\n", " ")
                    print(f"    tag={tag}  class={cls[:80]}")
                    print(f"    text={inner!r}")
            except Exception as e:
                print(f"  {sel:<40} -> ERROR: {e}")

        # --- probe generic selectors ---
        generic_probes = [
            ".product-card", ".product_item", ".product-item",
            ".prod-item", "li.item", ".card",
            "[class*='product']", "[class*='prod']",
            "div[class*='item']", "div[class*='card']",
            "article", ".shop-item", ".grid-item",
        ]
        print("\n===== GENERIC SELECTOR PROBE =====")
        for sel in generic_probes:
            try:
                n = await page.locator(sel).count()
                if n > 0:
                    print(f"  {sel:<40} -> {n} elements")
                    cls = await page.locator(sel).first.get_attribute("class") or ""
                    print(f"    first class: {cls[:80]}")
            except Exception:
                pass

        # --- find all links matching /buyonline/ pattern (product links) ---
        print("\n===== PRODUCT LINKS (/buyonline/) =====")
        links = await page.evaluate("""
            () => {
                const anchors = document.querySelectorAll('a[href*="/buyonline/"]');
                return [...anchors].slice(0, 10).map(a => ({
                    href: a.href,
                    text: a.innerText.trim().slice(0, 60),
                    parentClass: a.parentElement ? a.parentElement.className : '',
                    grandparentClass: a.parentElement && a.parentElement.parentElement
                        ? a.parentElement.parentElement.className : ''
                }));
            }
        """)
        for link in links:
            print(f"  href={link['href']}")
            print(f"    parent class   : {link['parentClass'][:80]}")
            print(f"    grandparent cls: {link['grandparentClass'][:80]}")
            print()

        # --- dump all unique classes that look like product containers ---
        all_classes = await page.evaluate("""
            () => {
                const els = document.querySelectorAll('*');
                const found = new Set();
                for (const el of els) {
                    for (const cls of el.classList) {
                        if (/product|item|card|prod|gift|shop|catalogue|rebrand|delivery/i.test(cls)) {
                            found.add(el.tagName.toLowerCase() + '.' + cls);
                        }
                    }
                }
                return [...found].slice(0, 80);
            }
        """)
        print("\n===== ALL MATCHING CLASSES =====")
        for c in all_classes:
            print(" ", c)

        # --- dump bottom of page: pagination / load-more buttons ---
        print("\n===== BOTTOM OF PAGE (last 3000 chars of body) =====")
        bottom = await page.evaluate("""
            () => document.body.innerHTML.slice(-3000)
        """)
        print(bottom)

        print("\n===== ALL BUTTONS AND PAGINATION LINKS =====")
        btns = await page.evaluate("""
            () => {
                const els = [...document.querySelectorAll('button, a[href*="page"], [class*="page"], [class*="pagination"], [class*="loadmore"], [class*="load-more"], [class*="showmore"]')];
                return els.slice(0, 30).map(el => ({
                    tag: el.tagName,
                    text: el.innerText.trim().slice(0, 60),
                    cls: el.className,
                    href: el.href || ''
                }));
            }
        """)
        for b in btns:
            if b['text'] or b['cls']:
                print(f"  <{b['tag'].lower()}> text={b['text']!r}  class={b['cls'][:60]}  href={b['href'][:80]}")

        # --- dump the main content area HTML (skip header) ---
        main_html = await page.evaluate("""
            () => {
                // Try to get just the product grid area
                const candidates = [
                    document.querySelector('main'),
                    document.querySelector('#main-content'),
                    document.querySelector('.main-content'),
                    document.querySelector('.CatalogueV2Design'),
                    document.querySelector('[class*="catalogue"]'),
                    document.querySelector('[class*="product-list"]'),
                ];
                for (const el of candidates) {
                    if (el) return el.innerHTML.slice(0, 6000);
                }
                // fallback: body minus the first 3000 chars (skip header)
                return document.body.innerHTML.slice(5000, 11000);
            }
        """)
        print("\n===== MAIN CONTENT HTML (up to 6000 chars) =====")
        print(main_html)

        await browser.close()

asyncio.run(main())
