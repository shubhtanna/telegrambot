"""
earnkaro_bot.py
────────────────
Cycles through EarnKaro's Finance Deals listing (credit cards) and posts
ONE card to WhatsApp every hour, looping back to the first card once it
reaches the end.

CARD LINKS FILE (card_links.txt, next to this script):
    <exact card title> | <real affiliate link>
One per line. Checked FIRST for every card's apply link — only falls
back to scraping the COPY LINK button if a title isn't listed yet.
Re-read on every card, so you can keep adding lines while the bot runs.

REQUIRES a logged-in EarnKaro session first — run
earnkaro_login_setup.py ONCE (on your own computer) to create
earnkaro_session.json, then upload that file next to this one.

Setup:
    pip install playwright aiohttp python-dotenv
    playwright install chromium
    python earnkaro_login_setup.py      # once, to create the session file
    python earnkaro_bot.py --discover   # sanity-check: list found cards, no sending
    python earnkaro_bot.py --test-one   # send just the first card, to check format
    python earnkaro_bot.py              # the real run — 1 card/hour, looping
"""

import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs
from zoneinfo import ZoneInfo

import aiohttp
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("earnkaro_bot")

# ══════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════
LISTING_URL = os.environ.get("EARNKARO_LISTING_URL", "https://earnkaro.com/top-selling-products/finance-deals")
SESSION_FILE = Path(os.environ.get("EARNKARO_SESSION_FILE", str(Path(__file__).resolve().parent / "earnkaro_session.json")))
STATE_FILE = Path(os.environ.get("EARNKARO_STATE_FILE", str(Path(__file__).resolve().parent / "earnkaro_state.json")))
CARD_LINKS_FILE = Path(os.environ.get("EARNKARO_CARD_LINKS_FILE", str(Path(__file__).resolve().parent / "card_links.txt")))
SEND_INTERVAL_SECONDS = int(os.environ.get("EARNKARO_INTERVAL_SECONDS", 12600))  # 3.5 hours default
DEBUG_DUMP_DIR = Path(os.environ.get("EARNKARO_DEBUG_DIR", str(Path(__file__).resolve().parent / "debug_dumps")))

BAILEYS_URL = os.environ.get("BAILEYS_URL")
BAILEYS_SECRET = os.environ.get("BAILEYS_SECRET", "mysecret123")
WA_GROUPS = [g.strip() for g in os.environ.get("EARNKARO_WA_GROUPS", "").split(",") if g.strip()]

# Twice a day, whatever card just went to the credit-card group (WA_GROUPS)
# ALSO gets broadcast to every other deal group — but never Flipkart,
# Fashion, or Beauty groups, since a credit card offer doesn't fit those.
# List every group you want in the broad broadcast EXCEPT those three
# categories here. The credit-card group(s) in EARNKARO_WA_GROUPS are
# automatically excluded from this list in code below (even if you
# accidentally include them here) — so it can never post there twice.
BULK_WA_GROUPS = [g.strip() for g in os.environ.get("EARNKARO_BULK_WA_GROUPS", "").split(",") if g.strip()]

IST = ZoneInfo("Asia/Kolkata")
ACTIVE_START_HOUR = 8  # 8:00 AM IST — quiet hours run from 1:00 AM to 7:59 AM
# 10:00–15:00 and 18:00–23:59 IST — each fires exactly once per day, the
# first time the main loop's regular tick lands inside that window.
BULK_WINDOWS = {
    "morning": (10, 15),
    "evening": (18, 24),
}

FEES_HEADING_RE = re.compile(r'\bFEES\b.{0,30}\bCHARGES\b', re.IGNORECASE)
STOP_SECTION_RE = re.compile(
    r'\b(DOCUMENTS\s+NEEDED|ELIGIBILITY\s+CRITERIA|NOT\s+GETTING\s+SALES|'
    r'IMPORTANT\s+T\s*&\s*Cs?|SIMILAR\s+PRODUCTS|ABOUT\s+EARNKARO|CONNECT\s+WITH\s+US|'
    r'DOWNLOAD\s+APP|COPYRIGHT\s+\d{4}|WHY\s+PROMOTE\s+THIS\s+DEAL)\b',
    re.IGNORECASE,
)
APPLY_LINK_RE = re.compile(r'Card\s+apply\s+link\s*:?\s*(https?://\S+)', re.IGNORECASE)
SHORT_LINK_FALLBACK_RE = re.compile(r'https?://(?:bitli\.in|ekaro\.in|bitly\.co|earnkaro\.com/r)/\S+', re.IGNORECASE)

NOISE_LINE_RE = re.compile(
    r'^(copy\s*link|apply\s*now|share|whatsapp|facebook|twitter|telegram|copy|'
    r'home|login|sign\s*up|menu|search|back\s+to\s+top|product\s+highlights)$',
    re.IGNORECASE,
)

GENERIC_IMAGE_RE = re.compile(r'ek_og_image|logo|icon|sprite|avatar|favicon', re.IGNORECASE)


def _is_noise_line(line: str) -> bool:
    if NOISE_LINE_RE.match(line):
        return True
    if line.count("->") >= 2:
        return True
    return False


def _normalize_title(t: str) -> str:
    t = t.lower().strip()
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t


# ══════════════════════════════════════════
#  CARD LINKS FILE (title -> link lookup)
# ══════════════════════════════════════════
def _load_card_link_map() -> dict:
    link_map = {}
    if not CARD_LINKS_FILE.exists():
        return link_map
    try:
        for line in CARD_LINKS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "|" not in line:
                continue
            title_part, link_part = line.split("|", 1)
            title_part, link_part = title_part.strip(), link_part.strip()
            if title_part and link_part.startswith("http"):
                link_map[_normalize_title(title_part)] = link_part
    except Exception as e:
        log.warning(f"[LINKS] Couldn't read {CARD_LINKS_FILE}: {e}")
    return link_map


def _lookup_manual_link(title: str, link_map: dict) -> str | None:
    if not title or not link_map:
        return None
    norm = _normalize_title(title)
    if norm in link_map:
        return link_map[norm]
    for stored_title, link in link_map.items():
        if norm in stored_title or stored_title in norm:
            return link
    return None


def _looks_like_heading(line: str) -> bool:
    if len(line) > 100 or line.endswith((".", ",", ";")):
        return False
    words = line.split()
    if not (1 <= len(words) <= 16):
        return False
    return line.isupper() and any(c.isalpha() for c in line)


# ══════════════════════════════════════════
#  STATE
# ══════════════════════════════════════════
def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"index": 0}


def _save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state))


# ══════════════════════════════════════════
#  SCRAPING — LISTING PAGE
# ══════════════════════════════════════════
async def get_card_links(page) -> list[str]:
    await page.goto(LISTING_URL, wait_until="networkidle")
    await page.wait_for_timeout(1500)

    def _matching_links(hrefs: list[str]) -> set:
        return {
            h for h in hrefs
            if h and h.startswith("/") and re.search(r'/[A-Za-z]+\d+-[\w-]+$', h)
        }

    previous_count = -1
    stable_reads = 0
    for attempt in range(25):
        hrefs = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
        current_links = _matching_links(hrefs)
        log.info(f"[SCRAPE] Scroll attempt {attempt + 1}: {len(current_links)} card link(s) so far")

        if len(current_links) == previous_count:
            stable_reads += 1
            if stable_reads >= 2:
                break
        else:
            stable_reads = 0
        previous_count = len(current_links)

        for label in ("Load More", "View More", "Show More"):
            btn = await page.query_selector(f"text={label}")
            if btn:
                try:
                    await btn.click()
                    await page.wait_for_timeout(800)
                except Exception:
                    pass

        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1200)
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

    hrefs = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
    card_links = ["https://earnkaro.com" + h for h in _matching_links(hrefs)]
    log.info(f"[SCRAPE] Found {len(card_links)} card link(s) on the listing page")
    return card_links


# ══════════════════════════════════════════
#  SCRAPING — LINK (fallback only, used when title isn't in card_links.txt)
# ══════════════════════════════════════════
async def _get_link_via_copy_button(page, url_for_debug: str) -> str | None:
    try:
        el = await page.query_selector("[data-clipboard-text]")
        if el:
            val = await el.get_attribute("data-clipboard-text")
            if val and val.startswith("http"):
                return val

        el = await page.query_selector("[data-clipboard-target]")
        if el:
            target_sel = await el.get_attribute("data-clipboard-target")
            if target_sel:
                try:
                    val = await page.eval_on_selector(target_sel, "el => el.value || el.textContent || ''")
                    val = (val or "").strip()
                    if val.startswith("http"):
                        return val
                except Exception:
                    pass

        share_btn = await page.query_selector("text=/share\\s*now/i")
        if share_btn:
            href = await share_btn.evaluate("el => el.getAttribute('href') || el.closest('a')?.getAttribute('href')")
            if href:
                try:
                    qs = parse_qs(urlparse(href).query)
                    text_param = qs.get("text", [""])[0]
                    m = SHORT_LINK_FALLBACK_RE.search(unquote(text_param))
                    if m:
                        return m.group(0)
                except Exception:
                    pass

        btn = None
        for pattern in (r'^copy\s*link$', r'copy', r'apply\s*now'):
            btn = await page.query_selector(f"text=/{pattern}/i")
            if btn:
                break
        if not btn:
            btn = await page.query_selector('[aria-label*="copy" i], [title*="copy" i]')

        if btn:
            await page.bring_to_front()
            await btn.click()
            await page.wait_for_timeout(500)

            try:
                toast_text = await page.inner_text("body")
                m = SHORT_LINK_FALLBACK_RE.search(toast_text)
                if m:
                    return m.group(0)
            except Exception:
                pass

            try:
                link = (await page.evaluate("() => navigator.clipboard.readText()") or "").strip()
                if link.startswith("http"):
                    return link
            except Exception as e:
                log.info(f"[SCRAPE] Clipboard API read blocked ({e}) — trying paste simulation")

            pasted = await _read_clipboard_via_paste(page)
            if pasted:
                return pasted

            try:
                values = await page.eval_on_selector_all("input, textarea", "els => els.map(e => e.value).filter(Boolean)")
                for v in values:
                    if v.strip().startswith("http"):
                        return v.strip()
            except Exception:
                pass

            try:
                href = await btn.evaluate(
                    "el => el.getAttribute('href') || el.closest('a')?.getAttribute('href') "
                    "|| el.getAttribute('data-link') || el.getAttribute('data-url')"
                )
                if href and href.startswith("http"):
                    return href
            except Exception:
                pass

            try:
                outer_html = await btn.evaluate("el => el.outerHTML")
                _dump_debug_text(url_for_debug + "__COPYBTN", outer_html)
            except Exception:
                pass
        else:
            log.warning("[SCRAPE] No copy/apply/share button found on this page")

        html = await page.content()
        m = SHORT_LINK_FALLBACK_RE.search(html)
        if m:
            return m.group(0)

        log.warning("[SCRAPE] Couldn't find the link via any method")
    except Exception as e:
        log.warning(f"[SCRAPE] Couldn't get link via copy button: {e}")
    return None


async def _read_clipboard_via_paste(page) -> str | None:
    try:
        await page.evaluate("""() => {
            let el = document.getElementById('__ek_paste_target__');
            if (!el) {
                el = document.createElement('textarea');
                el.id = '__ek_paste_target__';
                el.style.position = 'fixed';
                el.style.top = '-1000px';
                el.style.left = '-1000px';
                document.body.appendChild(el);
            }
            el.value = '';
            el.focus();
        }""")
        await page.click("#__ek_paste_target__")
        await page.keyboard.press("Control+v")
        await page.wait_for_timeout(200)
        value = await page.eval_on_selector("#__ek_paste_target__", "el => el.value")
        await page.evaluate("""() => {
            const el = document.getElementById('__ek_paste_target__');
            if (el) el.remove();
        }""")
        value = (value or "").strip()
        return value if value.startswith("http") else None
    except Exception as e:
        log.info(f"[SCRAPE] Paste-simulation read failed: {e}")
        return None


# ══════════════════════════════════════════
#  SCRAPING — IMAGE (fully automatic — no manual file needed)
# ══════════════════════════════════════════
async def _find_main_image(page) -> str | None:
    try:
        await page.wait_for_function(
            "() => Array.from(document.querySelectorAll('img')).some(i => i.naturalWidth > 50)",
            timeout=4000,
        )
    except Exception:
        pass

    try:
        imgs = await page.evaluate("""
            () => Array.from(document.querySelectorAll('img')).map(img => ({
                src: img.currentSrc || img.src,
                area: (img.naturalWidth || 0) * (img.naturalHeight || 0)
            })).filter(i => i.src)
        """)
    except Exception:
        imgs = []

    candidates = [i for i in imgs if i["area"] > 0 and not GENERIC_IMAGE_RE.search(i["src"])]
    if candidates:
        return max(candidates, key=lambda i: i["area"])["src"]

    try:
        og = await page.get_attribute('meta[property="og:image"]', "content")
        if og and not GENERIC_IMAGE_RE.search(og):
            return og
    except Exception:
        pass

    return None


# ══════════════════════════════════════════
#  SCRAPING — CARD PAGE
# ══════════════════════════════════════════
async def scrape_card(page, url: str) -> dict | None:
    await page.goto(url, wait_until="networkidle")
    await page.wait_for_timeout(1200)

    title = ""
    h1 = await page.query_selector("h1, h2")
    if h1:
        title = (await h1.inner_text()).strip()
    if not title:
        title = await page.title()

    image_url = await _find_main_image(page)
    full_text = await page.inner_text("body")

    # LINK — card_links.txt first, scraping is only a fallback
    link_map = _load_card_link_map()
    apply_link = _lookup_manual_link(title, link_map)
    if apply_link:
        log.info(f"[LINKS] Using manual link from {CARD_LINKS_FILE.name} for: {title}")
    else:
        apply_link = await _get_link_via_copy_button(page, url)
        if not apply_link:
            apply_link = _extract_apply_link(full_text)
            if apply_link:
                log.info("[SCRAPE] Used text-scan fallback for the apply link")
        if not apply_link:
            log.warning(f'[LINKS] Not in {CARD_LINKS_FILE.name} yet — add this line: {title} | <paste link here>')

    benefits, fees, fees_heading = _extract_sections(full_text, title)

    if not benefits and not fees:
        log.warning(f"[SCRAPE] Couldn't find Benefits/Fees sections on {url} — dumping debug text")
        _dump_debug_text(url, full_text)
        return None

    return {
        "url": url,
        "title": title,
        "image_url": image_url,
        "benefits": benefits,
        "fees": fees,
        "fees_heading": fees_heading,
        "apply_link": apply_link,
    }


def _dump_debug_text(url: str, content: str):
    try:
        DEBUG_DUMP_DIR.mkdir(exist_ok=True)
        safe_name = re.sub(r'[^\w-]', '_', url.rsplit("/", 1)[-1])[:100]
        out = DEBUG_DUMP_DIR / f"{safe_name}.txt"
        out.write_text(content)
        log.info(f"[SCRAPE] Debug dump written to {out}")
    except Exception as e:
        log.warning(f"[SCRAPE] Couldn't write debug dump: {e}")


def _extract_sections(full_text: str, title: str) -> tuple[list[str], list[str], str | None]:
    lines = [l.strip() for l in full_text.splitlines() if l.strip()]

    start_idx = 0
    if title:
        for i, line in enumerate(lines):
            if title[:30] and title[:30] in line:
                start_idx = i + 1
                break

    benefits, fees = [], []
    fees_heading = None
    mode = None

    for line in lines[start_idx:]:
        if _is_noise_line(line):
            continue
        if APPLY_LINK_RE.search(line) or SHORT_LINK_FALLBACK_RE.search(line):
            continue

        if STOP_SECTION_RE.search(line):
            if mode == "fees":
                break
            mode = None
            continue

        if FEES_HEADING_RE.search(line):
            mode = "fees"
            fees_heading = line
            continue

        if _looks_like_heading(line):
            if mode is None:
                mode = "benefits"
            elif mode == "benefits":
                mode = "fees"
                fees_heading = line
            continue

        if mode == "benefits":
            benefits.append(line)
        elif mode == "fees":
            fees.append(line)

    return benefits, fees, fees_heading


def _extract_apply_link(full_text: str) -> str | None:
    m = APPLY_LINK_RE.search(full_text)
    if m:
        return m.group(1)
    m = SHORT_LINK_FALLBACK_RE.search(full_text)
    return m.group(0) if m else None


# ══════════════════════════════════════════
#  MESSAGE BUILDING
# ══════════════════════════════════════════
def build_message(card: dict) -> str:
    lines = [card["title"], ""]
    lines += [f"Card Apply Link : {card['apply_link'] or '(not found)'}", ""]
    if card["benefits"]:
        lines += ["Benefits"]
        lines += [f"• {b}" for b in card["benefits"]]
        lines += [""]
    if card["fees_heading"] or card["fees"]:
        if card["fees_heading"]:
            lines += [f"• {card['fees_heading']}"]
        lines += [f"• {f}" for f in card["fees"]]
    return "\n".join(lines).rstrip()


# ══════════════════════════════════════════
#  WHATSAPP SEND — matches /send-single exactly:
#  multipart field 'text' + file field 'image' (upload.single('image'))
# ══════════════════════════════════════════
async def download_image(url: str | None) -> bytes | None:
    if not url:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    return await r.read()
    except Exception as e:
        log.warning(f"[IMG] Failed to download card image: {e}")
    return None


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
                    form.add_field("image", image_bytes, filename="card.jpg", content_type="image/jpeg")
                async with session.post(f"{BAILEYS_URL}/send-single", data=form,
                                         timeout=aiohttp.ClientTimeout(total=30)) as r:
                    status, body = r.status, await r.text()
                log.info(f"[WA] {'Sent' if status == 200 else 'FAILED'} to {target} ({status}: {body[:80]})")
            except Exception as e:
                log.error(f"[WA] Error sending to {target}: {e}")
            await asyncio.sleep(2)


async def send_card_to_whatsapp(text: str, image_bytes: bytes | None):
    if not BAILEYS_URL or not WA_GROUPS:
        log.warning("[WA] BAILEYS_URL / EARNKARO_WA_GROUPS not configured — cannot send")
        return
    await send_to_targets(text, image_bytes, WA_GROUPS)


def _current_bulk_window(now_ist: datetime) -> str | None:
    h = now_ist.hour
    for name, (start, end) in BULK_WINDOWS.items():
        if start <= h < end:
            return name
    return None


def _seconds_until_next_active_window(now_ist: datetime) -> float:
    wake_at = now_ist.replace(hour=ACTIVE_START_HOUR, minute=0, second=0, microsecond=0)
    if wake_at <= now_ist:
        wake_at += timedelta(days=1)
    return (wake_at - now_ist).total_seconds()


async def maybe_bulk_broadcast(state: dict, text: str, image_bytes: bytes | None):
    """Twice a day (once 10am-3pm IST, once 6pm-midnight IST), broadcast
    whatever card just went to the credit-card group to every other deal
    group too — excluding Flipkart/Fashion/Beauty (never in BULK_WA_GROUPS
    to begin with) and excluding the credit-card group itself (removed
    here even if it was accidentally left in BULK_WA_GROUPS), so it never
    posts there twice."""
    if not BULK_WA_GROUPS:
        return

    now_ist = datetime.now(IST)
    window = _current_bulk_window(now_ist)
    if not window:
        return

    today_str = now_ist.date().isoformat()
    state_key = f"bulk_{window}_date"
    if state.get(state_key) == today_str:
        return  # already done for this window today

    targets = [g for g in BULK_WA_GROUPS if g not in WA_GROUPS]
    if not targets:
        log.info(f"[BULK] {window} window — no targets left after excluding the credit-card group(s)")
    else:
        log.info(f"[BULK] {window.capitalize()} broadcast window — sending to {len(targets)} group(s)")
        await send_to_targets(text, image_bytes, targets)

    state[state_key] = today_str
    _save_state(state)


# ══════════════════════════════════════════
#  MAIN LOOP — 1 card every hour, looping back to card 1 at the end
# ══════════════════════════════════════════
async def run(discover_only: bool = False, test_one: bool = False):
    if not SESSION_FILE.exists():
        raise SystemExit(
            f"No session file at {SESSION_FILE}. Run earnkaro_login_setup.py once first "
            "to log in and save your EarnKaro session."
        )

    state = _load_state()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=str(SESSION_FILE))
        await context.grant_permissions(["clipboard-read", "clipboard-write"], origin="https://earnkaro.com")
        page = await context.new_page()

        if discover_only:
            links = await get_card_links(page)
            print(f"\nFound {len(links)} card link(s):")
            for l in links:
                print(" ", l)
            await browser.close()
            return

        if test_one:
            card_links = await get_card_links(page)
            if not card_links:
                print("No card links found — run --discover first to debug that.")
                await browser.close()
                return
            url = card_links[0]
            print(f"\nTesting card 1/{len(card_links)}: {url}")
            card = await scrape_card(page, url)
            if not card:
                print(f"Scrape failed — check {DEBUG_DUMP_DIR} for the raw page text dump.")
                await browser.close()
                return
            message = build_message(card)
            print("\n--- MESSAGE THAT WOULD BE SENT ---")
            print(message)
            print("-----------------------------------")
            image_bytes = await download_image(card["image_url"])
            print(f"Image downloaded: {'yes' if image_bytes else 'no'} (url: {card['image_url']})")
            await send_card_to_whatsapp(message, image_bytes)
            print("Sent (check EARNKARO_WA_GROUPS to confirm it landed).")
            await browser.close()
            return

        while True:
            try:
                now_ist = datetime.now(IST)
                if now_ist.hour < ACTIVE_START_HOUR:
                    sleep_secs = _seconds_until_next_active_window(now_ist)
                    log.info(f"[SCHEDULE] Outside active hours (1am-8am IST) — sleeping {sleep_secs/3600:.1f}h until 8am")
                    await asyncio.sleep(sleep_secs)
                    continue

                card_links = await get_card_links(page)
                if not card_links:
                    log.error("[MAIN] No card links found — check EARNKARO_LISTING_URL and that the session is still valid")
                    await asyncio.sleep(SEND_INTERVAL_SECONDS)
                    continue

                idx = state["index"] % len(card_links)
                url = card_links[idx]
                log.info(f"[MAIN] Card {idx + 1}/{len(card_links)}: {url}")

                card = await scrape_card(page, url)
                if card:
                    message = build_message(card)
                    image_bytes = await download_image(card["image_url"])
                    await send_card_to_whatsapp(message, image_bytes)
                    await maybe_bulk_broadcast(state, message, image_bytes)
                else:
                    log.warning("[MAIN] Skipped this card due to a scrape issue — advancing to the next one anyway")

                state["index"] = (idx + 1) % len(card_links)
                _save_state(state)

            except Exception as e:
                log.error(f"[MAIN] Error in this cycle: {e}")

            log.info(f"[MAIN] Sleeping {SEND_INTERVAL_SECONDS}s until the next card")
            await asyncio.sleep(SEND_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run(discover_only="--discover" in sys.argv, test_one="--test-one" in sys.argv))