"""
earnkaro_bot.py
────────────────
Sends ONE credit card to WhatsApp every 3.5 hours, looping back to the
first card at the end.

This version NEVER opens a browser and NEVER visits EarnKaro. Everything
it sends was already harvested to disk by earnkaro_harvest.py:

    card_data/cards.json           → title, apply link, benefits, fees
    card_data/images/<Title>.jpg   → the card image

No Playwright, no earnkaro_session.json, no login, no scraping at send
time — so a session expiry or an EarnKaro layout change can never break
a send. It just reads files and posts them.

To add or update cards:
    1. On your PC:  python earnkaro_harvest.py
    2. git add card_data/ && git commit && git push
    3. Railway redeploys and the bot picks up the new cards.txt cache

Commands:
    python earnkaro_bot.py             # the real run — 1 card / 3.5h
    python earnkaro_bot.py --list      # show the send order and what's usable
    python earnkaro_bot.py --preview   # print the next card's message, send nothing
    python earnkaro_bot.py --test-one  # actually send the next card right now
"""

import argparse
import asyncio
import json
import logging
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("earnkaro_bot")

# ══════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════
DATA_DIR = Path(os.environ.get("EARNKARO_DATA_DIR", str(BASE_DIR / "card_data")))
CARDS_JSON = DATA_DIR / "cards.json"
STATE_FILE = Path(os.environ.get("EARNKARO_STATE_FILE", str(BASE_DIR / "earnkaro_send_state.json")))

SEND_INTERVAL_SECONDS = int(os.environ.get("EARNKARO_INTERVAL_SECONDS", 16200))  # 3.5 hours

# Appended right below the apply link on every card message — lives here
# (not in cards.json) so it applies to every card automatically,
# including ones added by a future harvest, without editing the data file.
CC_FOOTER = "For More Such Credit Card Deals Visit - https://www.dealspouch.com/finance"

BAILEYS_URL = os.environ.get("BAILEYS_URL")
BAILEYS_SECRET = os.environ.get("BAILEYS_SECRET", "mysecret123")
WA_GROUPS = [g.strip() for g in os.environ.get("EARNKARO_WA_GROUPS", "").split(",") if g.strip()]
BULK_WA_GROUPS = [g.strip() for g in os.environ.get("EARNKARO_BULK_WA_GROUPS", "").split(",") if g.strip()]

# Cards with no benefits AND no fees are skipped by default. Set this to 1
# if you'd rather send them as title + link only.
SEND_WITHOUT_CONTENT = os.environ.get("EARNKARO_SEND_WITHOUT_CONTENT", "0") == "1"

IST = ZoneInfo("Asia/Kolkata")
ACTIVE_START_HOUR = 8  # quiet hours 1:00 AM – 7:59 AM IST


# ══════════════════════════════════════════
#  CACHE
# ══════════════════════════════════════════
def load_cards() -> list[dict]:
    """Read cards.json and return only the cards that are actually sendable."""
    if not CARDS_JSON.exists():
        log.error(f"[CACHE] {CARDS_JSON} not found — run earnkaro_harvest.py on your PC and commit card_data/")
        return []
    try:
        data = json.loads(CARDS_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        log.error(f"[CACHE] Couldn't parse {CARDS_JSON}: {e}")
        return []

    cards = data.get("cards", [])
    usable, skipped_no_link, skipped_no_content = [], 0, 0

    for c in cards:
        if not c.get("apply_link"):
            skipped_no_link += 1
            continue
        if not c.get("benefits") and not c.get("fees") and not SEND_WITHOUT_CONTENT:
            skipped_no_content += 1
            continue
        usable.append(c)

    log.info(f"[CACHE] {len(usable)} sendable card(s) loaded from {CARDS_JSON.name}")
    if skipped_no_link:
        log.warning(f"[CACHE] {skipped_no_link} card(s) skipped — no apply link")
    if skipped_no_content:
        log.warning(f"[CACHE] {skipped_no_content} card(s) skipped — no benefits/fees "
                    f"(set EARNKARO_SEND_WITHOUT_CONTENT=1 to send them anyway)")
    return usable


# def load_image_bytes(card: dict) -> bytes | None:
#     rel = card.get("image_file")
#     if not rel:
#         return None
#     path = DATA_DIR / rel
#     if not path.exists():
#         log.warning(f"[IMG] Missing image file {path} — sending as text only")
#         return None
#     try:
#         return path.read_bytes()
#     except Exception as e:
#         log.warning(f"[IMG] Couldn't read {path}: {e}")
#         return None

async def get_image_bytes(card: dict) -> bytes | None:
    """Local file first; fall back to the CDN URL saved at harvest time."""
    rel = card.get("image_file")
    if rel:
        path = DATA_DIR / rel
        if path.exists():
            try:
                return path.read_bytes()
            except Exception as e:
                log.warning(f"[IMG] Couldn't read {path}: {e}")

    url = card.get("image_url")
    if not url:
        log.warning(f"[IMG] No local file and no image_url for '{card.get('title')}' — text only")
        return None

    log.info(f"[IMG] No local file — downloading from image_url")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    data = await r.read()
                    if data:
                        return data
                log.warning(f"[IMG] HTTP {r.status} from image_url — text only")
    except Exception as e:
        log.warning(f"[IMG] Download failed ({e}) — text only")
    return None


# ══════════════════════════════════════════
#  STATE
# ══════════════════════════════════════════
def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"queue": [], "last_sent_slug": None, "last_sent_at": None}


def _save_state(state: dict):
    try:
        STATE_FILE.write_text(json.dumps(state))
    except Exception as e:
        log.warning(f"[STATE] Couldn't save state: {e}")


def _next_card(state: dict, cards: list[dict]) -> dict:
    """
    Picks the next card using a "shuffle bag": every card gets sent
    exactly once before any card repeats, and each lap's order is freshly
    randomized — never the same fixed sequence twice.

    This is also what fixes the "starts from card 1 again after every
    redeploy" problem. Railway's filesystem isn't persisted across
    deploys unless you attach a volume — a fresh build gets a brand-new,
    empty container, so EARNKARO_STATE_FILE (this bot's local save-file
    for "which card is next") gets wiped every single time you push code.
    With the old sequential index, "wiped state" meant "index resets to
    0" — always the same first card. With a shuffle bag, "wiped state"
    just means "start a new random lap" — a different, unpredictable
    card each time, exactly what you asked for.
    """
    by_slug = {c.get("slug"): c for c in cards if c.get("slug")}

    # Drop any leftover queued slug for a card that no longer exists
    # (removed since the last harvest), so a stale queue can't crash this.
    queue = [s for s in state.get("queue", []) if s in by_slug]

    if not queue:
        queue = list(by_slug.keys())
        random.shuffle(queue)
        # Don't let a fresh lap immediately repeat the card that just went
        # out at the end of the previous lap.
        if len(queue) > 1 and queue[0] == state.get("last_sent_slug"):
            queue[0], queue[1] = queue[1], queue[0]

    next_slug = queue.pop(0)
    state["queue"] = queue
    return by_slug[next_slug]


# ══════════════════════════════════════════
#  MESSAGE BUILDING  (unchanged format)
# ══════════════════════════════════════════
def build_message(card: dict) -> str:
    lines = [card["title"], ""]
    lines += [f"Card Apply Link : {card.get('apply_link') or '(not found)'}", ""]
    lines += [CC_FOOTER, ""]

    if card.get("fees_heading") or card.get("fees"):
        if card.get("fees_heading"):
            lines += [f"• {card['fees_heading']}"]
        lines += [f"• {f}" for f in card.get("fees", [])]
        lines += [""]

    if card.get("benefits"):
        lines += ["Benefits"]
        lines += [f"• {b}" for b in card["benefits"]]

    return "\n".join(lines).rstrip()


# ══════════════════════════════════════════
#  WHATSAPP SEND  (unchanged — multipart 'text' + file field 'image')
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


async def maybe_bulk_broadcast(text: str, image_bytes: bytes | None):
    """Fan the same card out to the bulk groups, excluding the main card group(s)."""
    if not BULK_WA_GROUPS:
        return
    targets = [g for g in BULK_WA_GROUPS if g not in WA_GROUPS]
    if not targets:
        log.info("[BULK] No bulk targets left after excluding the credit-card group(s)")
        return
    log.info(f"[BULK] Sending to {len(targets)} bulk group(s)")
    await send_to_targets(text, image_bytes, targets)


# ══════════════════════════════════════════
#  SCHEDULE
# ══════════════════════════════════════════
def _seconds_until_next_active_window(now_ist: datetime) -> float:
    wake_at = now_ist.replace(hour=ACTIVE_START_HOUR, minute=0, second=0, microsecond=0)
    if wake_at <= now_ist:
        wake_at += timedelta(days=1)
    return (wake_at - now_ist).total_seconds()


# ══════════════════════════════════════════
#  ONE SEND
# ══════════════════════════════════════════
async def send_one(cards: list[dict], state: dict, dry_run: bool = False) -> bool:
    card = _next_card(state, cards)

    message = build_message(card)
    image_bytes = await get_image_bytes(card)

    log.info(f"[MAIN] Card: {card['title']} "
             f"({len(state['queue'])} left in this random lap, image: {'yes' if image_bytes else 'no'})")

    if dry_run:
        print("\n--- MESSAGE THAT WOULD BE SENT ---")
        print(message)
        print("-----------------------------------")
        print(f"Image: {card.get('image_file') or '(none)'}\n")
        return True

    await send_card_to_whatsapp(message, image_bytes)
    await maybe_bulk_broadcast(message, image_bytes)

    state["last_sent_slug"] = card.get("slug")
    state["last_sent_at"] = datetime.now(IST).isoformat(timespec="seconds")
    _save_state(state)
    return True


# ══════════════════════════════════════════
#  MAIN LOOP
# ══════════════════════════════════════════
async def run(args):
    cards = load_cards()

    if args.list:
        state = _load_state()
        by_slug = {c.get("slug"): c for c in cards if c.get("slug")}
        queue = [s for s in state.get("queue", []) if s in by_slug]
        note = ""
        if not queue:
            queue = list(by_slug.keys())
            random.shuffle(queue)
            note = "  (new lap — this exact order is just a preview; the real send re-shuffles)"
        print(f"\n{len(cards)} sendable card(s) — upcoming random-lap order:{note}\n")
        for i, slug in enumerate(queue):
            c = by_slug[slug]
            marker = " ← NEXT" if i == 0 else ""
            img = "img" if c.get("image_file") else "NO IMG"
            print(f"  {i + 1:>3}. [{img:>6}] {c['title'][:70]}{marker}")
        print()
        return

    if not cards:
        raise SystemExit("No sendable cards — run earnkaro_harvest.py and commit card_data/.")

    state = _load_state()

    if args.preview:
        await send_one(cards, state, dry_run=True)
        return

    if args.test_one:
        await send_one(cards, state)
        print("Sent — check the group to confirm it landed.")
        return

    log.info(f"[MAIN] Offline mode — {len(cards)} card(s) cached, "
             f"one every {SEND_INTERVAL_SECONDS / 3600:.1f}h, active from {ACTIVE_START_HOUR}:00 IST")

    while True:
        try:
            now_ist = datetime.now(IST)
            if now_ist.hour < ACTIVE_START_HOUR:
                sleep_secs = _seconds_until_next_active_window(now_ist)
                log.info(f"[SCHEDULE] Quiet hours (1am–8am IST) — sleeping {sleep_secs / 3600:.1f}h")
                await asyncio.sleep(sleep_secs)
                continue

            # re-read every cycle so a redeploy with new cards is picked up live
            fresh = load_cards()
            if fresh:
                cards = fresh

            await send_one(cards, state)

        except Exception as e:
            log.error(f"[MAIN] Error in this cycle: {e}")

        log.info(f"[MAIN] Sleeping {SEND_INTERVAL_SECONDS}s until the next card")
        await asyncio.sleep(SEND_INTERVAL_SECONDS)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Send cached EarnKaro cards to WhatsApp.")
    p.add_argument("--list", action="store_true", help="show the send order and exit")
    p.add_argument("--preview", action="store_true", help="print the next card's message without sending")
    p.add_argument("--test-one", action="store_true", help="send the next card immediately, then exit")
    asyncio.run(run(p.parse_args()))