#!/usr/bin/env python3
"""
Scrapes Amazon Fresh Cut Flowers BSR top 30 using headless Chromium + stealth.
Outputs a JSON dict of {product_name: rank} for:
  - All known Stargazer ASINs (any rank they appear at)
  - All items at rank 1-30 with a derived product name for unknown ASINs
"""

import json
import re
import sys
import time
import random
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

BSR_URL = "https://www.amazon.com/Best-Sellers-Fresh-Cut-Flowers/zgbs/grocery/12902901"

ASIN_TO_PRODUCT = {
    # ── Stargazer Barn — all tracked ASINs ──────────────────────────────────
    "B08BXRHRXV": "Stargazer-Wildflower",
    "B08BXRHRL8": "Stargazer-Pink/White Lilies",
    "B08BXRQ4XM": "Stargazer-Red Royale",
    "B07YMKC6NF": "Stargazer Barn - 15 stem Rainbow Tulips",
    "B07MGJ266C": "Stargazer Barn - 30 stem Rainbow Tulips",
    "B07TRP9TVX": "Stargazer-Pretty in Pink",
    "B07SGR2K3Q": "Stargazer-Sunrise Lilies",
    "B07VRYHH5K": "Stargazer-Sunrise Lilies",        # alt ASIN
    "B07KWKGPKZ": "Stargazer-Holiday Bouquet",
    "B07KWTRYJB": "Stargazer-Holiday Bouquet",        # alt ASIN
    "B07H196JDZ": "Stargazer-Holiday Bouquet",        # seasonal alt
    "B07H15GPZG": "Stargazer-10 Sunflowers",
    "B07MMNRKCT": "Stargazer-Sunflower Fields",
    "B07KWH1QFV": "Stargazer-Lets Celebrate",
    "B07GZJXZLH": "Stargazer-Blooming Cheer",
    "B07N6JT9ZX": "Stargazer-Blooming Cheer 2",
    "B07KWV7JK3": "Stargazer-24 Red Roses",
    "B07GZH9789": "Stargazer-12 Rainbow Roses",
    "B08BXRKJ6V": "Stargazer-Rose Lily",
    "B07M7XWW4Z": "Stargazer-Royal Protea",
    "B07GZXM7X7": "Stargazer-15 Pink Tulips",
    "B08BXPPX68": "Stargazer-24 Rainbow Roses",
    "B08BXP6K1Z": "Stargazer-Just Peachy",
    "B07N28T3LD": "Stargazer-20 Ranunculus",
    "B08BXQZBNF": "Stargazer-40 Ranunculus",
    "B084CXD1BT": "Stargazer-12 Red Roses",
    "B08LRB7B46": "Stargazer-Rainbow Royale",
    "B07KWSRRGM": "Stargazer-White Royale",
    "B07H15GR4Q": "Stargazer-15 Orange Tulips",
    "B0CL5G4PQZ": "Stargazer-Best Regards Lily",

    # ── Known competitors ────────────────────────────────────────────────────
    "B074JJ84FG": "Benchmark-Rose/Alstroe Var",
    "B074JHFQJC": "Benchmark-Rose/Alstroe Var",       # alt ASIN
}

# Brand detection for unknown ASINs found in top 30
BRAND_PATTERNS = [
    ("Benchmark Bouquets", "Benchmark"),
    ("KaBloom", "KaBloom"),
    ("Aquarossa", "Aquarossa"),
    ("BloomsyBox", "BloomsyBox"),
    ("Lucky You", "Lucky You"),
    ("Whole Foods Market", "Whole Foods"),
    ("Whole Foods", "Whole Foods"),
    ("eFlower", "eFlower"),
    ("GlobalRose", "GlobalRose"),
    ("Arabella", "Arabella"),
    ("Jtoder", "Jtoder"),
    ("From You Flowers", "From You Flowers"),
    ("BestFlower", "BestFlower"),
    ("Epicflowers", "Epicflowers"),
    ("Benchmark", "Benchmark"),
]

# Extracts rank, ASIN, and title for every badge item on the BSR page
EXTRACT_JS = """
() => {
    const badges = document.querySelectorAll('.zg-bdg-text');
    const results = {};
    badges.forEach(badge => {
        const rank = parseInt(badge.textContent.replace('#','').trim());
        if (!rank) return;
        let card = badge.closest('[data-p13n-asin-metadata]')
                   || badge.closest('.zg-item-immersion')
                   || badge.closest('li');
        let asin = null, title = '';
        if (card) {
            const link = card.querySelector('a[href*="/dp/"]');
            if (link) {
                const m = link.href.match(/\\/dp\\/([A-Z0-9]{10})/);
                if (m) asin = m[1];
            }
            const asinAttr = card.getAttribute('data-p13n-asin-metadata');
            if (asinAttr) {
                try { const j = JSON.parse(asinAttr); asin = asin || j.asin; } catch(e) {}
            }
            const sels = [
                '[class*="p13n-sc-truncate"]',
                '[class*="line-clamp"]',
                '.p13n-sc-truncated',
                'span[title]',
                'a[title]',
            ];
            for (const sel of sels) {
                const el = card.querySelector(sel);
                if (el) {
                    const t = el.getAttribute('title') || el.textContent || '';
                    if (t.trim()) { title = t.replace(/\\s+/g, ' ').trim(); break; }
                }
            }
        }
        if (asin && rank && !results[asin]) results[asin] = {rank, title};
    });
    return results;
}
"""


def product_name_from_title(asin, title):
    """Derive a Brand-Description product name from an Amazon listing title."""
    if not title:
        return f"Unknown-{asin[:8]}"
    for pattern, brand in BRAND_PATTERNS:
        if pattern.lower() in title.lower():
            rest = re.sub(re.escape(pattern), '', title, flags=re.IGNORECASE)
            rest = re.sub(r'^[\s,|\-]+', '', rest).strip()
            descriptor = rest[:35].strip()
            return f"{brand}-{descriptor}" if descriptor else brand
    return title[:45].strip()


def scrape(max_retries=3):
    for attempt in range(1, max_retries + 1):
        print(f"Attempt {attempt}/{max_retries}...", file=sys.stderr)
        try:
            result = _try_scrape()
            if result and len(result) >= 15:
                return result
            print(f"  Only got {len(result)} results, retrying...", file=sys.stderr)
        except Exception as e:
            print(f"  Error: {e}", file=sys.stderr)
        time.sleep(random.uniform(4, 8))
    return {}


def _try_scrape():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/Los_Angeles",
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        page.goto(BSR_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(3, 5))

        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        time.sleep(random.uniform(1, 2))
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(random.uniform(1, 2))

        raw = page.evaluate(EXTRACT_JS)
        browser.close()
        return raw


def main():
    print("Scraping Amazon BSR...", file=sys.stderr)
    raw = scrape()

    if not raw:
        print("ERROR: Failed to scrape any results after retries.", file=sys.stderr)
        sys.exit(1)

    print(f"Scraped {len(raw)} ASINs from the BSR page.", file=sys.stderr)

    product_ranks = {}
    new_top30 = []

    for asin, info in raw.items():
        rank = info["rank"]
        title = info.get("title", "")
        product = ASIN_TO_PRODUCT.get(asin)

        if product:
            # Known ASIN — track regardless of rank (captures all Stargazer products)
            if product not in product_ranks or rank < product_ranks[product]:
                product_ranks[product] = rank
        elif rank <= 30:
            # Unknown ASIN in top 30 — derive a name and track it
            name = product_name_from_title(asin, title)
            if name not in product_ranks or rank < product_ranks[name]:
                product_ranks[name] = rank
            new_top30.append((rank, asin, name))

    if new_top30:
        print("Unknown ASINs in top 30 (auto-named from page title):", file=sys.stderr)
        for rank, asin, name in sorted(new_top30):
            print(f"  #{rank}: {asin} → \"{name}\"", file=sys.stderr)

    print(json.dumps(product_ranks))


if __name__ == "__main__":
    main()
