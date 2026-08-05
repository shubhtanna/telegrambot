"""
earnkaro_harvest.py
───────────────────
RUN THIS ON YOUR OWN COMPUTER — not on Railway.

Visits every EarnKaro card page ONCE and saves everything to disk, so
earnkaro_bot.py never has to open a browser or log in again.

What it writes (all inside card_data/, next to this script):

    card_data/cards.json          → title, apply link, benefits, fees, image filename
    card_data/images/<Title>.jpg  → the card image, filename = the card title
    card_data/raw_text/<Title>.txt → the full raw page text (so you can fix a
                                     badly-parsed card by hand without re-scraping)

card_links.txt stays the input file — it is where the apply links come
from, and its line order decides the order the bot sends cards in.

Workflow:
    1. python earnkaro_harvest.py          (on your PC)
    2. git add card_data/ && git commit && git push
    3. Railway redeploys — earnkaro_bot.py now reads card_data/ only

Railway's disk is wiped on every redeploy, which is why the harvest runs
locally and the results get committed to the repo.

Commands:
    python earnkaro_harvest.py                 # incremental — only new cards
    python earnkaro_harvest.py --refresh       # re-harvest all (keeps hand-edited ones)
    python earnkaro_harvest.py --refresh --force   # re-harvest absolutely everything
    python earnkaro_harvest.py --only "Scapia"     # just cards matching this text
    python earnkaro_harvest.py --discover          # list card pages found, save nothing

Requires the logged-in session file (earnkaro_session.json) that
earnkaro_login_setup.py creates.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs
from zoneinfo import ZoneInfo

import aiohttp
from playwright.async_api import async_playwright
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("earnkaro_harvest")

# ══════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════
LISTING_URL = os.environ.get("EARNKARO_LISTING_URL", "https://earnkaro.com/top-selling-products/finance-deals")
SESSION_FILE = Path(os.environ.get("EARNKARO_SESSION_FILE", str(BASE_DIR / "earnkaro_session.json")))
CARD_LINKS_FILE = Path(os.environ.get("EARNKARO_CARD_LINKS_FILE", str(BASE_DIR / "card_links.txt")))

DATA_DIR = Path(os.environ.get("EARNKARO_DATA_DIR", str(BASE_DIR / "card_data")))
CARDS_JSON = DATA_DIR / "cards.json"
IMAGES_DIR = DATA_DIR / "images"
RAW_TEXT_DIR = DATA_DIR / "raw_text"

IST = ZoneInfo("Asia/Kolkata")

# ── parsing patterns (same rules the old bot used) ──
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


# ══════════════════════════════════════════
#  SMALL HELPERS
# ══════════════════════════════════════════
def _normalize_title(t: str) -> str:
    t = (t or "").lower().strip()
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t


def _safe_filename(title: str, max_len: int = 90) -> str:
    """Turn a card title into a readable, filesystem-safe filename stem."""
    name = re.sub(r'[^\w\s-]', '', title or "").strip()
    name = re.sub(r'\s+', '_', name)
    name = re.sub(r'_+', '_', name).strip('_')
    return (name[:max_len].rstrip('_') or "untitled")


def _is_noise_line(line: str) -> bool:
    if NOISE_LINE_RE.match(line):
        return True
    if line.count("->") >= 2:
        return True
    return False


def _looks_like_heading(line: str) -> bool:
    if len(line) > 100 or line.endswith((".", ",", ";")):
        return False
    words = line.split()
    if not (1 <= len(words) <= 16):
        return False
    return line.isupper() and any(c.isalpha() for c in line)


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
#  card_links.txt  →  ordered link pool
#  Duplicate titles are handed out in order, so the two "PayZapp"
#  lines end up on two different cards instead of colliding.
# ══════════════════════════════════════════
def _split_link_line(line: str) -> tuple[str, str] | None:
    """Split "title | link" on the LAST pipe, so titles that themselves
    contain a pipe still parse. The old bot used split('|', 1), which
    silently dropped lines like:
        Indusind Tiger Credit Card - LIFETIME FREE | No Joining or Annual Fees | https://...
    """
    parts = line.split("|")
    for i in range(len(parts) - 1, 0, -1):
        link = parts[i].strip()
        title = "|".join(parts[:i]).strip()
        if title and link.startswith("http"):
            return title, link
    return None


class LinkPool:
    def __init__(self, path: Path):
        self.entries: list[dict] = []
        self._by_title: dict[str, list[int]] = {}
        self._load(path)

    def _load(self, path: Path):
        if not path.exists():
            log.warning(f"[LINKS] {path} not found — cards will be saved without apply links")
            return
        for order, raw in enumerate(path.read_text(encoding="utf-8").splitlines()):
            line = raw.strip()
            if not line or line.startswith("#") or "|" not in line:
                continue
            parsed = _split_link_line(line)
            if not parsed:
                log.warning(f"[LINKS] Couldn't parse line {order + 1}: {line[:80]}")
                continue
            title_part, link_part = parsed
            idx = len(self.entries)
            self.entries.append({
                "order": order,
                "title": title_part,
                "norm": _normalize_title(title_part),
                "link": link_part,
                "used_by": None,
            })
            self._by_title.setdefault(_normalize_title(title_part), []).append(idx)

        dupes = {t: len(v) for t, v in self._by_title.items() if len(v) > 1}
        if dupes:
            log.info(f"[LINKS] {len(dupes)} title(s) appear more than once — links will be assigned in file order")
        log.info(f"[LINKS] Loaded {len(self.entries)} link(s) from {path.name}")

    def claim(self, page_title: str) -> dict | None:
        """Return the next unused link entry whose title matches this page."""
        norm = _normalize_title(page_title)
        if not norm:
            return None

        # 1. exact title match, first unused one
        for idx in self._by_title.get(norm, []):
            if self.entries[idx]["used_by"] is None:
                return self.entries[idx]

        # 2. substring match, first unused one
        for e in self.entries:
            if e["used_by"] is not None:
                continue
            if norm in e["norm"] or e["norm"] in norm:
                return e

        # 3. already-used exact match (a card page repeated on the listing)
        for idx in self._by_title.get(norm, []):
            return self.entries[idx]

        return None

    def unused(self) -> list[dict]:
        return [e for e in self.entries if e["used_by"] is None]


# ══════════════════════════════════════════
#  SCRAPING — LISTING PAGE
# ══════════════════════════════════════════
async def get_card_links(page) -> list[str]:
    await page.goto(LISTING_URL, wait_until="networkidle")
    await page.wait_for_timeout(1500)

    def _matching(hrefs: list[str]) -> set:
        return {h for h in hrefs if h and h.startswith("/") and re.search(r'/[A-Za-z]+\d+-[\w-]+$', h)}

    ordered: list[str] = []
    seen: set = set()
    previous_count = -1
    stable_reads = 0

    for attempt in range(25):
        hrefs = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
        for h in hrefs:
            if h and h.startswith("/") and re.search(r'/[A-Za-z]+\d+-[\w-]+$', h) and h not in seen:
                seen.add(h)
                ordered.append(h)

        log.info(f"[SCRAPE] Scroll attempt {attempt + 1}: {len(ordered)} card link(s) so far")

        if len(ordered) == previous_count:
            stable_reads += 1
            if stable_reads >= 2:
                break
        else:
            stable_reads = 0
        previous_count = len(ordered)

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

    links = ["https://earnkaro.com" + h for h in ordered]
    log.info(f"[SCRAPE] Found {len(links)} card page(s) on the listing")
    return links


# ══════════════════════════════════════════
#  SCRAPING — LINK FALLBACK (only if title not in card_links.txt)
# ══════════════════════════════════════════
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


async def _get_link_via_copy_button(page) -> str | None:
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
                    m = SHORT_LINK_FALLBACK_RE.search(unquote(qs.get("text", [""])[0]))
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
                m = SHORT_LINK_FALLBACK_RE.search(await page.inner_text("body"))
                if m:
                    return m.group(0)
            except Exception:
                pass

            try:
                link = (await page.evaluate("() => navigator.clipboard.readText()") or "").strip()
                if link.startswith("http"):
                    return link
            except Exception:
                pass

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

        html = await page.content()
        m = SHORT_LINK_FALLBACK_RE.search(html)
        if m:
            return m.group(0)
    except Exception as e:
        log.warning(f"[SCRAPE] Copy-button link lookup failed: {e}")
    return None


# ══════════════════════════════════════════
#  SCRAPING — IMAGE
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


async def download_and_save_image(url: str | None, stem: str) -> str | None:
    """Download the card image and save it as images/<Card_Title>.<ext>."""
    if not url:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as r:
                if r.status != 200:
                    log.warning(f"[IMG] HTTP {r.status} for {url[:80]}")
                    return None
                data = await r.read()
                ctype = (r.headers.get("Content-Type") or "").lower()
    except Exception as e:
        log.warning(f"[IMG] Download failed: {e}")
        return None

    if not data:
        return None

    ext = ".jpg"
    path_ext = Path(urlparse(url).path).suffix.lower()
    if path_ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ext = ".jpg" if path_ext == ".jpeg" else path_ext
    elif "png" in ctype:
        ext = ".png"
    elif "webp" in ctype:
        ext = ".webp"

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    # remove any older extension for the same card so we don't leave duplicates
    for old in IMAGES_DIR.glob(f"{stem}.*"):
        try:
            old.unlink()
        except Exception:
            pass

    out = IMAGES_DIR / f"{stem}{ext}"
    out.write_bytes(data)
    log.info(f"[IMG] Saved {out.name} ({len(data) // 1024} KB)")
    return f"images/{out.name}"


# ══════════════════════════════════════════
#  SCRAPING — ONE CARD PAGE
# ══════════════════════════════════════════
async def harvest_card(page, url: str, pool: LinkPool) -> dict | None:
    await page.goto(url, wait_until="networkidle")
    await page.wait_for_timeout(1200)

    title = ""
    h1 = await page.query_selector("h1, h2")
    if h1:
        title = (await h1.inner_text()).strip()
    if not title:
        title = await page.title()
    if not title:
        log.warning(f"[CARD] No title found on {url} — skipping")
        return None

    full_text = await page.inner_text("body")
    image_url = await _find_main_image(page)
    benefits, fees, fees_heading = _extract_sections(full_text, title)

    # ── apply link: card_links.txt first, scraping only as a fallback ──
    entry = pool.claim(title)
    if entry:
        apply_link = entry["link"]
        link_order = entry["order"]
        link_source = "card_links.txt"
        entry["used_by"] = title
    else:
        apply_link = await _get_link_via_copy_button(page) or _extract_apply_link(full_text)
        link_order = None
        link_source = "scraped" if apply_link else None
        if apply_link:
            log.info(f'[LINKS] Scraped a link for an unlisted card — consider adding:\n    {title} | {apply_link}')
        else:
            log.warning(f'[LINKS] No link at all for: {title}')

    stem = _safe_filename(title)
    image_file = await download_and_save_image(image_url, stem)

    RAW_TEXT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        (RAW_TEXT_DIR / f"{stem}.txt").write_text(full_text, encoding="utf-8")
    except Exception as e:
        log.warning(f"[RAW] Couldn't save raw text: {e}")

    if not benefits and not fees:
        log.warning(f"[CARD] No benefits/fees parsed for '{title}' — raw text saved, fix it by hand in cards.json")

    return {
        "slug": stem,
        "title": title,
        "apply_link": apply_link,
        "link_source": link_source,
        "link_order": link_order,
        "source_url": url,
        "image_url": image_url,
        "image_file": image_file,
        "benefits": benefits,
        "fees_heading": fees_heading,
        "fees": fees,
        "raw_text_file": f"raw_text/{stem}.txt",
        "harvested_at": datetime.now(IST).isoformat(timespec="seconds"),
        "manual_edit": False,
    }


# ══════════════════════════════════════════
#  CACHE FILE
# ══════════════════════════════════════════
def load_cache() -> dict:
    if CARDS_JSON.exists():
        try:
            return json.loads(CARDS_JSON.read_text(encoding="utf-8"))
        except Exception as e:
            log.error(f"[CACHE] {CARDS_JSON} is unreadable ({e}) — starting a fresh one")
    return {"version": 1, "generated_at": None, "cards": []}


def save_cache(cache: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # card_links.txt order decides send order; unlisted cards go to the back
    cache["cards"].sort(key=lambda c: (c.get("link_order") is None,
                                       c.get("link_order") if c.get("link_order") is not None else 0,
                                       c.get("title", "")))
    cache["generated_at"] = datetime.now(IST).isoformat(timespec="seconds")
    CARDS_JSON.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(f"[CACHE] Wrote {len(cache['cards'])} card(s) to {CARDS_JSON}")


# ══════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════
async def run(args):
    if not SESSION_FILE.exists():
        raise SystemExit(
            f"No session file at {SESSION_FILE}.\n"
            "Run  python earnkaro_login_setup.py  once on this computer first."
        )

    cache = load_cache()
    by_url = {c["source_url"]: c for c in cache["cards"] if c.get("source_url")}
    pool = LinkPool(CARD_LINKS_FILE)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.headful)
        context = await browser.new_context(storage_state=str(SESSION_FILE))
        await context.grant_permissions(["clipboard-read", "clipboard-write"], origin="https://earnkaro.com")
        page = await context.new_page()

        try:
            urls = await get_card_links(page)
            if not urls:
                raise SystemExit("No card pages found — check EARNKARO_LISTING_URL and that the session is still valid.")

            if args.discover:
                print(f"\nFound {len(urls)} card page(s):")
                for u in urls:
                    marker = "  [cached]" if u in by_url else ""
                    print(f"  {u}{marker}")
                return

            todo = []
            for u in urls:
                existing = by_url.get(u)
                if existing and not args.refresh:
                    continue
                if existing and args.refresh and existing.get("manual_edit") and not args.force:
                    log.info(f"[SKIP] Hand-edited, leaving alone: {existing['title']}")
                    continue
                todo.append(u)

            if args.only:
                needle = args.only.lower()
                todo = [u for u in todo
                        if needle in u.lower()
                        or needle in (by_url.get(u, {}).get("title", "").lower())]

            # links already claimed by cached cards shouldn't be handed out twice
            for c in cache["cards"]:
                if c.get("source_url") in todo:
                    continue
                if c.get("link_order") is not None:
                    for e in pool.entries:
                        if e["order"] == c["link_order"]:
                            e["used_by"] = c["title"]

            if not todo:
                log.info("[MAIN] Nothing to harvest — cache is already up to date.")
                save_cache(cache)
                return

            log.info(f"[MAIN] Harvesting {len(todo)} card page(s)...")
            ok = fail = 0

            for i, url in enumerate(todo, 1):
                log.info(f"[MAIN] ── {i}/{len(todo)} ── {url}")
                try:
                    card = await harvest_card(page, url, pool)
                except Exception as e:
                    log.error(f"[MAIN] Failed on {url}: {e}")
                    card = None

                if not card:
                    fail += 1
                    continue

                old = by_url.get(url)
                if old:
                    cache["cards"] = [c for c in cache["cards"] if c.get("source_url") != url]
                cache["cards"].append(card)
                by_url[url] = card
                ok += 1

                if i % 5 == 0:
                    save_cache(cache)  # checkpoint, so a crash never loses everything

                await asyncio.sleep(1.5)

            save_cache(cache)

            # ── report ──
            print("\n" + "═" * 60)
            print(f"  Harvested OK : {ok}")
            print(f"  Failed       : {fail}")
            print(f"  Cache total  : {len(cache['cards'])} card(s)")
            no_link = [c["title"] for c in cache["cards"] if not c.get("apply_link")]
            no_content = [c["title"] for c in cache["cards"] if not c.get("benefits") and not c.get("fees")]
            no_image = [c["title"] for c in cache["cards"] if not c.get("image_file")]
            if no_link:
                print(f"\n  {len(no_link)} card(s) with NO apply link — the bot will skip these:")
                for t in no_link:
                    print(f"    · {t}")
            if no_content:
                print(f"\n  {len(no_content)} card(s) with NO benefits/fees parsed — check card_data/raw_text/:")
                for t in no_content:
                    print(f"    · {t}")
            if no_image:
                print(f"\n  {len(no_image)} card(s) with NO image (they'll send as text only):")
                for t in no_image:
                    print(f"    · {t}")
            leftovers = pool.unused()
            if leftovers:
                print(f"\n  {len(leftovers)} line(s) in card_links.txt never matched a card page:")
                for e in leftovers:
                    print(f"    · {e['title'][:70]}")
            print("\n  Next: git add card_data/ && git commit -m 'card cache' && git push")
            print("═" * 60 + "\n")

        finally:
            await browser.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Build the offline EarnKaro card cache.")
    p.add_argument("--refresh", action="store_true", help="re-harvest cards already in the cache")
    p.add_argument("--force", action="store_true", help="with --refresh, also overwrite hand-edited cards")
    p.add_argument("--only", metavar="TEXT", help="only harvest cards whose title/URL contains TEXT")
    p.add_argument("--discover", action="store_true", help="list the card pages found and exit")
    p.add_argument("--headful", action="store_true", help="show the browser window (useful for debugging)")
    asyncio.run(run(p.parse_args()))