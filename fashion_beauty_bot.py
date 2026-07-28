"""
fashion_beauty_bot.py
──────────────────────
Every INTERVAL_SECONDS (default 45 min): picks ONE random product from
all_products_card_links.txt (title | link — no earnkaro.com login needed,
these are direct retailer short-links). Visits the link using a real
Chrome channel with anti-bot-detection tweaks, confirms the page actually
resolved to a definite "in stock" or "out of stock" state (skips and
retries with a different random product otherwise — keeps retrying
indefinitely, never gives up for the whole cycle), classifies the title
as fashion / beauty / other, and fetches platform + price + image + the
LIVE title from that page.

Title handling: the file's title is trusted UNLESS it diverges too much
(<70% similarity) from what the live page actually shows — in which case
the live title is used instead, since the file can occasionally have a
stale/misaligned title for a given link.

Routing:
    fashion -> FASHION_WA_GROUP_ID + bulk groups
    beauty  -> BEAUTY_WA_GROUP_ID  + bulk groups
    other   -> bulk groups only (no single group)

Bulk broadcast only fires every 2nd tick (hourly, when INTERVAL_SECONDS
is at its normal 1800s setting). Active 8am-12am IST.

>>> EDIT THESE TWO BEFORE RUNNING <
"""
FASHION_WA_GROUP_ID = "120363427489881847@g.us"
BEAUTY_WA_GROUP_ID = "120363425518003162@g.us"

import asyncio
import difflib
import json
import logging
import os
import random
import re
from datetime import datetime, timedelta, time
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import aiohttp
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("fashion_beauty_bot")

# ══════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════
LINKS_FILE = Path(os.environ.get("EARNKARO_ALL_PRODUCTS_FILE", str(Path(__file__).resolve().parent / "product_links.txt")))
STATE_FILE = Path(os.environ.get("EARNKARO_FB_STATE_FILE", str(Path(__file__).resolve().parent / "fashion_beauty_state.json")))
# Default gap between deals is 45 minutes; can still be overridden via env.
INTERVAL_SECONDS = int(os.environ.get("EARNKARO_FB_INTERVAL_SECONDS", 45 * 60))
DEBUG_DUMP_DIR = Path(os.environ.get("EARNKARO_DEBUG_DIR", str(Path(__file__).resolve().parent / "debug_dumps")))

BAILEYS_URL = os.environ.get("BAILEYS_URL")
BAILEYS_SECRET = os.environ.get("BAILEYS_SECRET", "mysecret123")
BULK_WA_GROUPS = [g.strip() for g in os.environ.get("EARNKARO_BULK_WA_GROUPS", "").split(",") if g.strip()]

IST = ZoneInfo("Asia/Kolkata")
ACTIVE_START_HOUR = 8  # 8:00 AM
ACTIVE_END_TIME = time(0, 30)  # 12:30 AM

PLATFORM_DOMAIN_MAP = {
    "myntra.com": "Myntra", "flipkart.com": "Flipkart", "amazon.in": "Amazon",
    "amazon.com": "Amazon", "ajio.com": "Ajio", "nykaa.com": "Nykaa",
    "nykaafashion.com": "Nykaa Fashion", "meesho.com": "Meesho",
    "tatacliq.com": "Tata Cliq", "snapdeal.com": "Snapdeal", "shopsy.in": "Shopsy",
    "firstcry.com": "FirstCry", "purplle.com": "Purplle", "limeroad.com": "Limeroad",
}

GENERIC_IMAGE_RE = re.compile(r'logo|icon|sprite|placeholder|loading|favicon|blank\.(png|gif)', re.IGNORECASE)

OUT_OF_STOCK_RE = re.compile(
    r'(out\s*of\s*stock|currently\s*unavailable|sold\s*out|no\s*longer\s*available|'
    r'product\s*unavailable|item\s*unavailable|page\s*not\s*found|404\s*error|'
    r"we\s*can.?t\s*find\s*(this|that)\s*page|this\s*page\s*(isn.?t|is\s*not)\s*available|"
    r'oops.{0,20}(not\s*found|page)|coming\s*soon|this\s*product\s*is\s*no\s*longer|'
    r'link\s*(has\s*)?expired|invalid\s*(link|url)|notify\s*me\s*when\s*available)',
    re.IGNORECASE,
)

JUNK_TITLE_RE = re.compile(
    r'(video (was |is )?not found|please enable javascript|loading\.\.\.|'
    r'access denied|page not found|something went wrong|error occurred)',
    re.IGNORECASE,
)

# Keyword-based classification — title-only, since the combined file has
# no per-category metadata.
FASHION_KEYWORDS = [
    "t-shirt", "tshirt", "shirt", "kurta", "kurti", "jeans", "saree", "sari",
    "dress", "top", "shorts", "sandals", "shoe", "shoes", "sneaker", "sliders",
    "flip-flop", "flip flop", "loafer", "clog", "mule", "pump", "oxford",
    "derby", "bra", "jacket", "sweatshirt", "sweater", "pullover", "cardigan",
    "hoodie", "palazzo", "trouser", "culottes", "chinos", "blazer", "skirt",
    "legging", "sunglasses", "watch", "jewellery", "jewelry", "earring",
    "jhumka", "bangle", "necklace", "mangalsutra", "tikka", "bag", "handbag",
    "sling bag", "tote", "dungaree", "lehenga", "choli", "pathani", "anarkali",
    "gown", "sock", "cap ", "polo", "pyjama", "vest", "coat", "overcoat",
    "sherwani", "bikini", "swimwear", "romper", "jumpsuit", "salwar",
]
BEAUTY_KEYWORDS = [
    "soap", "shampoo", "conditioner", "cream", "lotion", "serum", "sunscreen",
    "perfume", "deodorant", "body spray", "lipstick", "lip color", "lip colour",
    "lip balm", "nail enamel", "nail polish", "nail cutter", "hair oil",
    "face wash", "face mask", "face scrub", "body wash", "moisturiser",
    "moisturizer", "epilator", "trimmer", "hair straightener", "hair dryer",
    "kajal", "eyeliner", "eyeshadow", "eye shadow", "foundation", "concealer",
    "body scrub", "body lotion", "essential oil", "sanitizer", "cologne",
    "eau de toilette", "eau de parfum", " edt ", "fragrance", "anti dandruff",
    "anti-dandruff", "tan removal", "body polish", "primer", "hair clipper",
    "shaver", "beard", "body mist", "gift kit", "powder", "blush", "hair color",
    "hair colour", "kohl", "body gel", "hand cleaner", "hair growth",
    "curling iron", "hair curler", "crimper", "makeup", "cosmetic", "mascara",
]


def _classify(title: str) -> str:
    t = title.lower()
    if any(kw in t for kw in BEAUTY_KEYWORDS):
        return "beauty"
    if any(kw in t for kw in FASHION_KEYWORDS):
        return "fashion"
    return "other"


def _normalize_title(t: str) -> str:
    t = t.lower().strip()
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t


def _title_similarity(a: str, b: str) -> float:
    """0.0-1.0 similarity between two titles, normalized the same way as
    the credit-card bot's title matching (lowercase, punctuation stripped)."""
    return difflib.SequenceMatcher(None, _normalize_title(a), _normalize_title(b)).ratio()


# ══════════════════════════════════════════
#  STATE
# ══════════════════════════════════════════
def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"tick_count": 0}


def _save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state))


# ══════════════════════════════════════════
#  LOADING PRODUCTS
# ══════════════════════════════════════════
def _load_all_products() -> list[dict]:
    products = []
    if not LINKS_FILE.exists():
        log.error(f"[LOAD] {LINKS_FILE} doesn't exist")
        return products
    for line in LINKS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        title = parts[0] if len(parts) > 0 else None
        link = parts[1] if len(parts) > 1 else None
        if title and link and link.startswith("http"):
            products.append({"title": title, "link": link})
    return products


# ══════════════════════════════════════════
#  LIVE FETCH — visit the link, confirm stock, get title/platform/price/image
# ══════════════════════════════════════════
def _platform_from_domain(final_url: str) -> str | None:
    try:
        host = urlparse(final_url).netloc.lower()
        host = host[4:] if host.startswith("www.") else host
        for domain, name in PLATFORM_DOMAIN_MAP.items():
            if host == domain or host.endswith("." + domain):
                return name
        return host or None
    except Exception:
        return None


async def _extract_price_jsonld(page) -> str | None:
    try:
        scripts = await page.eval_on_selector_all(
            'script[type="application/ld+json"]', "els => els.map(e => e.textContent)"
        )
    except Exception:
        return None

    def _find_price(obj):
        if isinstance(obj, dict):
            offers = obj.get("offers")
            if isinstance(offers, dict) and offers.get("price"):
                return str(offers["price"]), offers.get("priceCurrency", "")
            if isinstance(offers, list):
                for o in offers:
                    if isinstance(o, dict) and o.get("price"):
                        return str(o["price"]), o.get("priceCurrency", "")
            if obj.get("price"):
                return str(obj["price"]), obj.get("priceCurrency", "")
            for v in obj.values():
                result = _find_price(v)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = _find_price(item)
                if result:
                    return result
        return None

    for raw in scripts:
        try:
            data = json.loads(raw)
        except Exception:
            continue
        result = _find_price(data)
        if result:
            price, currency = result
            symbol = "₹" if currency in ("INR", "") else currency
            return f"{symbol}{price}"
    return None


async def _extract_price_fallback(page, body_text: str) -> str | None:
    try:
        for prop in ("product:price:amount", "og:price:amount"):
            val = await page.get_attribute(f'meta[property="{prop}"]', "content")
            if val:
                return f"₹{val}"
    except Exception:
        pass
    amounts = re.findall(r'₹\s?[\d,]+(?:\.\d+)?', body_text)
    return amounts[0] if amounts else None


async def _extract_image(page) -> str | None:
    """Real product images first, filtered by both minimum size AND
    aspect ratio (rejects wide/short promotional banner strips, which
    otherwise can win purely on raw pixel area). og:image (a small
    social-preview thumbnail on most sites) is only a last resort."""
    try:
        await page.wait_for_function(
            "() => Array.from(document.querySelectorAll('img')).some(i => i.naturalWidth > 300)",
            timeout=5000,
        )
    except Exception:
        pass

    try:
        imgs = await page.evaluate("""
            () => Array.from(document.querySelectorAll('img')).map(img => ({
                src: img.currentSrc || img.src,
                w: img.naturalWidth || 0,
                h: img.naturalHeight || 0
            })).filter(i => i.src)
        """)
        candidates = []
        for i in imgs:
            area = i["w"] * i["h"]
            if area < 90000 or GENERIC_IMAGE_RE.search(i["src"]):
                continue
            aspect = i["w"] / i["h"] if i["h"] else 0
            if not (0.5 <= aspect <= 1.6):
                continue
            candidates.append({"src": i["src"], "area": area})
        if candidates:
            return max(candidates, key=lambda c: c["area"])["src"]
    except Exception:
        pass

    try:
        og_image = await page.get_attribute('meta[property="og:image"]', "content")
        if og_image and not GENERIC_IMAGE_RE.search(og_image):
            return og_image
    except Exception:
        pass

    return None


async def _extract_live_title(page) -> str | None:
    """og:title first — curated specifically for the product, far less
    likely to accidentally pick up an unrelated widget's error text than
    a bare h1/h2 selector. Falls back to headings, then <title>, always
    filtering out known junk text (broken video-widget errors, etc.)."""
    try:
        og_title = await page.get_attribute('meta[property="og:title"]', "content")
        if og_title and not JUNK_TITLE_RE.search(og_title):
            return og_title.strip()
    except Exception:
        pass

    try:
        headings = await page.query_selector_all("h1, h2")
        for h in headings:
            text = (await h.inner_text()).strip()
            if text and len(text) > 3 and not JUNK_TITLE_RE.search(text):
                return text
    except Exception:
        pass

    try:
        title = (await page.title()).strip()
        if title and not JUNK_TITLE_RE.search(title):
            return title
    except Exception:
        pass

    return None


async def visit_and_check(page, link: str, _is_retry: bool = False) -> dict | None:
    """Returns None if the page is out of stock/unavailable/broken/couldn't
    be confirmed either way (caller should try a different product).
    Otherwise returns title/platform/price/image — all read live from the
    actual page."""
    try:
        response = await page.goto(link, wait_until="domcontentloaded", timeout=25000)
    except Exception as e:
        log.warning(f"[VISIT] Couldn't load {link}: {e}")
        if not _is_retry:
            await asyncio.sleep(5)
            return await visit_and_check(page, link, _is_retry=True)
        return None

    # Wait for the page to definitively show either a buyable or
    # not-buyable state. If neither appears in time, treat as inconclusive
    # and skip — do NOT assume "available" just because we couldn't confirm.
    try:
        await page.wait_for_function(
            """() => {
                const t = document.body.innerText.toLowerCase();
                return t.includes('add to bag') || t.includes('add to cart')
                    || t.includes('out of stock') || t.includes('notify me');
            }""",
            timeout=15000,
        )
    except Exception:
        log.info(f"[STOCK] Couldn't confirm stock status in time (still loading?) — skipping to be safe: {link}")
        return None

    await page.wait_for_timeout(500)

    if page.url.startswith("chrome-error://") or not response:
        log.info(f"[STOCK] Link failed to resolve to a real page ({page.url}) — treating as unavailable: {link}")
        return None

    if response.status >= 400:
        log.info(f"[STOCK] HTTP {response.status} for {link} — treating as unavailable")
        return None

    try:
        body_text = await page.inner_text("body")
    except Exception:
        body_text = ""

    if OUT_OF_STOCK_RE.search(body_text):
        log.info(f"[STOCK] Unavailable/out-of-stock indicator found — skipping {link}")
        return None

    live_title = await _extract_live_title(page)

    final_url = page.url
    platform = _platform_from_domain(final_url)
    price = await _extract_price_jsonld(page)
    if not price:
        price = await _extract_price_fallback(page, body_text)
    image_url = await _extract_image(page)

    if not price and not image_url:
        try:
            DEBUG_DUMP_DIR.mkdir(exist_ok=True)
            safe_name = re.sub(r'[^\w-]', '_', urlparse(final_url).path)[:100] or "product"
            (DEBUG_DUMP_DIR / f"{safe_name}.txt").write_text(body_text)
            log.warning(f"[VISIT] Price+image both missing for {final_url} — debug dump saved")
        except Exception:
            pass

    return {"title": live_title, "platform": platform, "price": price, "image_url": image_url}


async def pick_valid_product(page, all_products: list[dict]) -> tuple[dict, dict]:
    """Keeps trying different random products until one is actually
    available — no cap. If every product gets tried without success,
    starts a fresh pass rather than giving up. Small randomized pause
    between attempts so traffic doesn't look like a scraper hammering
    the site as fast as possible."""
    tried = set()
    attempt = 0
    while True:
        attempt += 1
        if len(tried) >= len(all_products):
            log.warning(f"[PICK] Went through all {len(all_products)} products without finding one available — starting a fresh pass")
            tried.clear()

        remaining = [i for i in range(len(all_products)) if i not in tried]
        idx = random.choice(remaining)
        tried.add(idx)
        product = all_products[idx]

        log.info(f"[PICK] Attempt {attempt}: {product['title']}")
        await asyncio.sleep(random.uniform(2, 5))
        details = await visit_and_check(page, product["link"])
        if details is not None:
            return product, details

        if attempt % 10 == 0:
            log.warning(f"[PICK] Still searching after {attempt} attempts — every one so far was unavailable/out of stock/broken")


async def download_image(url: str | None) -> bytes | None:
    if not url:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    return await r.read()
    except Exception as e:
        log.warning(f"[IMG] Failed to download product image: {e}")
    return None


# ══════════════════════════════════════════
#  MESSAGE BUILDING
# ══════════════════════════════════════════
def build_message(title: str, platform: str | None, price: str | None, link: str) -> str:
    return (
        f"Platform - {platform or '(not found)'}\n"
        f"Title - {title}\n"
        f"Price - {price or '(not found)'}\n"
        f"Link : {link}"
    )


# ══════════════════════════════════════════
#  WHATSAPP SEND — matches /send-single: multipart 'text' + file 'image'
# ══════════════════════════════════════════
async def send_to_targets(text: str, image_bytes: bytes | None, targets: list[str]):
    if not BAILEYS_URL or not targets:
        return
    async with aiohttp.ClientSession() as session:
        for target in targets:
            try:
                form = aiohttp.FormData()
                form.add_field("text", text)
                form.add_field("secret", BAILEYS_SECRET)
                form.add_field("target", target)
                if image_bytes:
                    form.add_field("image", image_bytes, filename="product.jpg", content_type="image/jpeg")
                async with session.post(f"{BAILEYS_URL}/send-single", data=form,
                                         timeout=aiohttp.ClientTimeout(total=30)) as r:
                    status, body = r.status, await r.text()
                log.info(f"[WA] {'Sent' if status == 200 else 'FAILED'} to {target} ({status}: {body[:80]})")
            except Exception as e:
                log.error(f"[WA] Error sending to {target}: {e}")
            await asyncio.sleep(2)


# ══════════════════════════════════════════
#  SCHEDULE
# ══════════════════════════════════════════
def _is_within_active_window(now_ist: datetime) -> bool:
    current_time = now_ist.time()
    return current_time >= time(ACTIVE_START_HOUR, 0) or current_time < ACTIVE_END_TIME


def _seconds_until_next_active_window(now_ist: datetime) -> float:
    wake_at = now_ist.replace(hour=ACTIVE_START_HOUR, minute=0, second=0, microsecond=0)
    if wake_at <= now_ist:
        wake_at += timedelta(days=1)
    return (wake_at - now_ist).total_seconds()


async def run():
    if not BAILEYS_URL:
        raise SystemExit("BAILEYS_URL not configured — check your .env")
    if "PASTE_" in FASHION_WA_GROUP_ID or "PASTE_" in BEAUTY_WA_GROUP_ID:
        log.warning("[CONFIG] FASHION_WA_GROUP_ID / BEAUTY_WA_GROUP_ID still contain placeholder text — edit them at the top of this file")

    state = _load_state()
    tick_count = state.get("tick_count", 0)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            extra_http_headers={
                "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                "sec-ch-ua-full-version-list": '"Chromium";v="124.0.6367.207", "Google Chrome";v="124.0.6367.207", "Not-A.Brand";v="99.0.0.0"',
                "sec-ch-ua-platform": '"Windows"',
            },
        )
        page = await context.new_page()

        while True:
            now_ist = datetime.now(IST)

            if not _is_within_active_window(now_ist):
                sleep_secs = _seconds_until_next_active_window(now_ist)
                log.info(f"[SCHEDULE] Outside active hours (8:00 AM-12:30 AM IST) — sleeping {sleep_secs/3600:.1f}h until 8:00 AM")
                await asyncio.sleep(sleep_secs)
                continue

            all_products = _load_all_products()
            if not all_products:
                log.error(f"[MAIN] No products loaded from {LINKS_FILE} — retrying next interval")
                await asyncio.sleep(INTERVAL_SECONDS)
                continue

            product, details = await pick_valid_product(page, all_products)

            file_title = product["title"]
            live_title = details.get("title")
            if live_title:
                similarity = _title_similarity(file_title, live_title)
                if similarity >= 0.70:
                    final_title = file_title
                    log.info(f"[TITLE] Match ({similarity:.0%}) — keeping file title: {file_title}")
                else:
                    final_title = live_title
                    log.info(f"[TITLE] Mismatch ({similarity:.0%}) — using live title instead. "
                              f"file='{file_title}' live='{live_title}'")
            else:
                final_title = file_title
                log.info(f"[TITLE] Couldn't read a live title — keeping file title: {file_title}")

            category = _classify(final_title)
            log.info(f"[MAIN] {final_title} -> category={category} platform={details['platform']} price={details['price']}")

            message = build_message(final_title, details["platform"], details["price"], product["link"])
            image_bytes = await download_image(details["image_url"])

            single_group_used = None
            if category == "fashion":
                await send_to_targets(message, image_bytes, [FASHION_WA_GROUP_ID])
                single_group_used = FASHION_WA_GROUP_ID
            elif category == "beauty":
                await send_to_targets(message, image_bytes, [BEAUTY_WA_GROUP_ID])
                single_group_used = BEAUTY_WA_GROUP_ID
            # "other" -> no single group

            tick_count += 1
            if tick_count % 2 == 0:  # every 2nd tick = every 1 hour (at normal 1800s interval)
                bulk_targets = [g for g in BULK_WA_GROUPS if g != single_group_used]
                if bulk_targets:
                    log.info(f"[BULK] Hourly broadcast ({category}) — sending to {len(bulk_targets)} group(s)")
                    await send_to_targets(message, image_bytes, bulk_targets)

            state["tick_count"] = tick_count
            _save_state(state)

            log.info(f"[MAIN] Sleeping {INTERVAL_SECONDS}s until the next product")
            await asyncio.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run())