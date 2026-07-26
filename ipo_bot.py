"""
ipo_bot.py
──────────
Standalone Telegram → WhatsApp forwarder for IPO update messages.

WHY A SEPARATE FILE (not added inside main.py):
  This pipeline watches DIFFERENT source groups, sends to DIFFERENT WhatsApp
  groups, and needs its own approval workflow. Keeping it isolated means a
  crash, restart, or bug here never touches your existing deals automation —
  and you can redeploy/tune this one on its own schedule.
  Deployment notes are at the very bottom of this file.
"""

import asyncio, re, io, logging, time, os, itertools, difflib
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
import aiohttp

# For LOCAL TESTING: reads a .env file in this folder and loads it into
# os.environ, so you don't have to `export` each variable by hand every
# time. In production (Render etc.) you'll set real env vars in the
# dashboard instead, and this call is a harmless no-op if there's no .env.
#
# We point load_dotenv() at THIS file's own folder rather than relying on
# it to find ".env" in your terminal's current directory — that mismatch
# (running `python ipo_bot.py` from a different folder than the .env file
# sits in) is the #1 reason .env "doesn't load".
from pathlib import Path
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent / ".env"
_loaded = load_dotenv(dotenv_path=_ENV_PATH)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ipo_bot")

if _loaded:
    log.info(f"[ENV] Loaded {_ENV_PATH}")
else:
    log.warning(
        f"[ENV] No .env file found at {_ENV_PATH} — "
        "either it's missing, misnamed, or in the wrong folder. "
        "Falling back to real environment variables only."
    )

# ══════════════════════════════════════════
#  CONFIG — all via environment variables, so plugging in real
#  group IDs later needs zero code changes, just env updates.
# ══════════════════════════════════════════
if not os.environ.get("API_ID") or not os.environ.get("API_HASH"):
    raise SystemExit(
        "Missing API_ID / API_HASH. Check that .env exists next to ipo_bot.py, "
        "has no quotes around values, and that python-dotenv is installed "
        "(pip install python-dotenv)."
    )

API_ID         = int(os.environ.get("API_ID"))
API_HASH       = os.environ.get("API_HASH")
# Reuses your existing session by default; set IPO_STRING_SESSION if you'd
# rather log this bot in as a second session (see notes at bottom on why
# that's safer than sharing one session across two running processes).
STRING_SESSION = os.environ.get("IPO_STRING_SESSION", os.environ.get("STRING_SESSION"))


BAILEYS_URL    = os.environ.get("BAILEYS_URL")
BAILEYS_SECRET = os.environ.get("BAILEYS_SECRET", "mysecret123")

# Comma-separated Telegram chat IDs of the IPO groups you're monitoring
# e.g. IPO_SOURCE_GROUPS = "-1001234567890,-1009876543210"
SOURCE_GROUPS = [int(x) for x in os.environ.get("IPO_SOURCE_GROUPS", "").split(",") if x.strip()]

# The Telegram group/chat where uncertain messages get posted for your okay.
# Numeric IDs and @usernames both work.
REVIEW_GROUP = os.environ.get("IPO_REVIEW_GROUP", "")
if REVIEW_GROUP.lstrip("-").isdigit():
    REVIEW_GROUP = int(REVIEW_GROUP)

# Comma-separated WhatsApp group JIDs (your 3 groups go here)
# e.g. IPO_WA_GROUPS = "1203xxxx@g.us,1203yyyy@g.us,1203zzzz@g.us"
IPO_WA_GROUPS = [g.strip() for g in os.environ.get("IPO_WA_GROUPS", "").split(",") if g.strip()]

OUR_GROUP_NAME   = "Ipo Insights India"
OUR_WA_JOIN_LINK = "https://chat.whatsapp.com/FduFNuuOdNv0FuKjRPa7Yh"

client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

# ══════════════════════════════════════════
#  STEP 1 — MESSAGE TYPE CLASSIFIER
#  Shapes pulled straight from your sample file: GMP updates, subscription
#  updates, listing updates, new-IPO announcements, "today's events", polls,
#  allotment notices.
# ══════════════════════════════════════════
IPO_TYPE_PATTERNS = {
    "gmp_update":          re.compile(r'\bGMP\s*Update\b', re.IGNORECASE),
    "subscription_update": re.compile(r'\bSubscription\s*Update\b', re.IGNORECASE),
    "listing_update":      re.compile(r'\bList(?:ed|ing)\b.{0,80}\b(?:NSE|BSE|premium|issue price)\b', re.IGNORECASE | re.DOTALL),
    "ipo_announcement":    re.compile(r'\bIPO\b.{0,120}\b(?:Issue Size|Face Value|Retail Portion|Expected Soon)\b', re.IGNORECASE | re.DOTALL),
    "todays_events":       re.compile(r"Today'?s\s+IPO\s+Events", re.IGNORECASE),
    "allotment":           re.compile(r'\bAllotment\b', re.IGNORECASE),
}

# Content that has no business in an IPO update — anything matching this
# forces a human look, even if it also looks IPO-shaped.
RED_FLAG_PATTERNS = re.compile(
    r'\b(crypto|forex|binary options|betting|casino|personal loan|loan approved|'
    r'work from home|earn\s*\d+.{0,15}(?:day|hour)|paid signal|call now|'
    r'dm for|contact.{0,10}(?:for|@)\s*\+?\d{6,})\b',
    re.IGNORECASE,
)

# General financial-awareness content (tax rules, cash-transaction limits,
# etc.) sometimes gets posted in these same IPO groups. It won't match
# IPO/GMP keywords, but Shubh wants it noticed rather than silently
# dropped — it just always needs his review since the format varies wildly
# and there's no fixed "shape" to trust blindly.
FINANCE_INFO_HINT_RE = re.compile(
    r'\b(income\s*tax|tax\s*notice|tds\b|pan\s*card|cash\s*deposit|cash\s*withdraw(?:al|n)?|'
    r'sebi|demat|kyc|savings\s*account|current\s*account)\b',
    re.IGNORECASE,
)


def classify_ipo_message(text: str) -> str:
    """Returns 'ignore', 'review', or 'auto'."""
    if not text or len(text.strip()) < 15:
        return "ignore"

    has_ipo_kw = bool(re.search(r'\bIPO\b|\bGMP\b', text, re.IGNORECASE))
    has_finance_kw = bool(FINANCE_INFO_HINT_RE.search(text))
    if not has_ipo_kw and not has_finance_kw:
        return "ignore"

    if RED_FLAG_PATTERNS.search(text):
        log.info("[CLASSIFY] Red-flag keyword matched -> review")
        return "review"

    if has_ipo_kw and any(pat.search(text) for pat in IPO_TYPE_PATTERNS.values()):
        return "auto"

    # Either general finance-info content, or IPO-flavored text that doesn't
    # match a known shape — both get a human look rather than auto-sending.
    return "review"


# ══════════════════════════════════════════
#  STEP 2 — CLEANING / REBRANDING
# ══════════════════════════════════════════
WA_LINK_RE = re.compile(r'https?://chat\.whatsapp\.com/\S+', re.IGNORECASE)

SOCIAL_LINK_RE = re.compile(
    r'https?://(?:www\.)?(?:instagram\.com|twitter\.com|x\.com|youtube\.com|youtu\.be|'
    r'facebook\.com|fb\.me|t\.me)/\S+',
    re.IGNORECASE,
)

# Lines that exist only to plug the source's own group/channel
GROUP_LABEL_LINE_RE = re.compile(
    r'^.{0,15}(?:join(?:\s+us)?|group|channel|powered\s+by|source|follow\s+us)\s*[:\-]?\s*.*$',
    re.IGNORECASE | re.MULTILINE,
)

# Mid-sentence brand mentions like "Stay tuned with IPO Ji for complete IPO
# updates" or "Follow XYZ Deals for more updates" — these don't start the
# line the way GROUP_LABEL_LINE_RE expects, so they need their own check.
# We only swap the captured name, keeping the rest of the sentence intact.
THIRD_PARTY_TAGLINE_RE = re.compile(
    r'\b(stay\s+(?:tuned|connected)\s+with|follow|courtesy\s+of|'
    r'brought\s+to\s+you\s+by|presented\s+by|in\s+association\s+with)\s+'
    r'([A-Za-z][\w]*(?:\s+[A-Za-z][\w]*){0,3}?)(\s+for\b|[.,!]|\n|$)',
    re.IGNORECASE,
)


def clean_ipo_message(text: str) -> tuple[str, bool]:
    """
    Returns (cleaned_text, fully_confident).
    fully_confident=False means some branding in the text couldn't be
    confidently swapped out — treat as needing review even if the
    classifier said 'auto'.
    """
    cleaned = text

    # Any WhatsApp invite link that isn't ours -> replace with ours
    cleaned = WA_LINK_RE.sub(OUR_WA_JOIN_LINK, cleaned)

    # Drop social-media promo lines entirely
    cleaned = SOCIAL_LINK_RE.sub('', cleaned)

    # Swap mid-sentence taglines: "Stay tuned with IPO Ji for..." ->
    # "Stay tuned with Ipo Insights India for..."
    def _swap_tagline(m):
        prefix, tail = m.group(1), m.group(3) or ""
        return f"{prefix} {OUR_GROUP_NAME}{tail}"

    cleaned = THIRD_PARTY_TAGLINE_RE.sub(_swap_tagline, cleaned)

    # Swap "Join X / Channel: Y / Powered by Z" lines for our own branding —
    # but leave alone anything that's actually IPO content (e.g. "Join now
    # to apply"), so we don't accidentally delete real information.
    def _swap_label_line(m):
        line = m.group(0)
        if re.search(r'\bIPO\b|\bapply\b|\ballotment\b', line, re.IGNORECASE):
            return line
        return f"Join {OUR_GROUP_NAME}"

    cleaned = GROUP_LABEL_LINE_RE.sub(_swap_label_line, cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()

    # If another group's @handle or t.me link survived the cleanup, don't
    # risk shipping a competitor's branding — flag it instead.
    still_has_other_branding = bool(re.search(r'@\w{4,}|https?://t\.me/\S+', cleaned, re.IGNORECASE))
    return cleaned, not still_has_other_branding


# ══════════════════════════════════════════
#  STEP 3 — DUPLICATE DETECTION
#  Many groups repost the same GMP/subscription update within minutes of
#  each other — same core numbers, but a line added/removed or the wording
#  tweaked. A single character-level similarity ratio is too strict for
#  that (one extra sentence drags the whole-string ratio down even though
#  the actual IPO data is identical), so we also compare on the SET of
#  words/numbers each message contains — order and extra lines don't
#  matter for that, only which words are shared.
# ══════════════════════════════════════════
# ══════════════════════════════════════════
#  STEP 3 — DUPLICATE DETECTION
#  Many groups repost the same update within minutes — same wording, maybe
#  a line added/removed — and that IS a duplicate. But a GMP/subscription
#  update for the SAME IPO with DIFFERENT numbers (e.g. GMP moved ₹12 -> ₹7)
#  is a genuinely new update and must always send, even though almost every
#  label word (QIB, B-HNI, GMP, Total Sub, the company name...) is
#  identical. So word-similarity alone can't decide this — the numbers are
#  checked separately and are decisive: numbers differ -> never a duplicate.
# ══════════════════════════════════════════
DEDUP_WINDOW_SECONDS = 90 * 60
DEDUP_SEQUENCE_THRESHOLD = 0.72   # character-level similarity (word content)
DEDUP_TOKEN_JACCARD_THRESHOLD = 0.60   # shared-words similarity (word content)

_WORD_RE = re.compile(r'[a-z]+')
_NUMBER_RE = re.compile(r'\d+(?:\.\d+)?')

_sent_fingerprints: list[tuple[str, set, tuple, float]] = []  # (norm_text, word_set, numbers, timestamp)


def _normalize_for_dedup(text: str) -> str:
    t = text.lower()
    t = re.sub(r'https?://\S+', '', t)
    t = re.sub(r'[^\w\s.]', '', t)  # keep '.' so decimals like 1.65 survive
    return re.sub(r'\s+', ' ', t).strip()


def _word_set(normalized_text: str) -> set:
    return set(_WORD_RE.findall(normalized_text))


def _numbers(text: str) -> tuple:
    return tuple(sorted(_NUMBER_RE.findall(text)))


def is_duplicate(text: str) -> bool:
    now = time.time()
    while _sent_fingerprints and now - _sent_fingerprints[0][3] > DEDUP_WINDOW_SECONDS:
        _sent_fingerprints.pop(0)

    norm = _normalize_for_dedup(text)
    words = _word_set(norm)
    nums = _numbers(text)

    for old_norm, old_words, old_nums, _ in _sent_fingerprints:
        if nums != old_nums:
            continue  # numbers changed -> genuinely new data, not a duplicate, regardless of wording

        seq_ratio = difflib.SequenceMatcher(None, norm, old_norm).ratio()
        union = words | old_words
        jaccard = (len(words & old_words) / len(union)) if union else 0.0
        if seq_ratio >= DEDUP_SEQUENCE_THRESHOLD or jaccard >= DEDUP_TOKEN_JACCARD_THRESHOLD:
            log.info(f"[DEDUP] Same numbers + matching wording (text={seq_ratio:.0%}, words={jaccard:.0%}) — skipping")
            return True
    return False


def _remember_sent(text: str):
    norm = _normalize_for_dedup(text)
    _sent_fingerprints.append((norm, _word_set(norm), _numbers(text), time.time()))



# ══════════════════════════════════════════
#  STEP 4 — WHATSAPP SENDER
#  Reuses the same Baileys HTTP sender your deals bot already talks to —
#  just posts to each of your 3 IPO groups.
# ══════════════════════════════════════════
async def send_ipo_to_whatsapp(text: str, image_bytes: bytes | None = None):
    if not BAILEYS_URL:
        log.warning("[WA] BAILEYS_URL not set — cannot send")
        return
    if not IPO_WA_GROUPS:
        log.warning("[WA] IPO_WA_GROUPS not configured — cannot send")
        return

    async with aiohttp.ClientSession() as session:
        for target in IPO_WA_GROUPS:
            try:
                if image_bytes:
                    form = aiohttp.FormData()
                    form.add_field("text", text or "")
                    form.add_field("secret", BAILEYS_SECRET)
                    form.add_field("target", target)
                    form.add_field("image", image_bytes, filename="ipo.jpg", content_type="image/jpeg")
                    async with session.post(f"{BAILEYS_URL}/send-single", data=form,
                                             timeout=aiohttp.ClientTimeout(total=30)) as r:
                        body, status = await r.text(), r.status
                else:
                    async with session.post(f"{BAILEYS_URL}/send-single",
                                             json={"text": text, "secret": BAILEYS_SECRET, "target": target},
                                             timeout=aiohttp.ClientTimeout(total=30)) as r:
                        body, status = await r.text(), r.status
                if status == 200:
                    log.info(f"[WA] Sent to {target}")
                else:
                    log.error(f"[WA] HTTP {status} — {body[:120]}")
            except Exception as e:
                log.error(f"[WA] Failed sending to {target}: {e}")
            await asyncio.sleep(2)  # small gap between groups so it doesn't read as a burst/spam


# ══════════════════════════════════════════
#  STEP 5 — REVIEW / APPROVAL QUEUE
#  Uncertain messages get posted into your review group. You confirm by
#  sending/forwarding that same content back into the group — the bot
#  matches it against what's pending and only then sends to WhatsApp.
# ══════════════════════════════════════════
PENDING_TTL_SECONDS = 6 * 60 * 60  # forget an unapproved item after 6 hours
APPROVAL_MATCH_THRESHOLD = 0.75
REVIEW_REQUEST_MARKER = "🔎 IPO REVIEW REQUEST"

_pending_review: dict[int, dict] = {}
_review_id_counter = itertools.count(1)


def _purge_pending():
    now = time.time()
    stale = [k for k, v in _pending_review.items() if now - v["created_at"] > PENDING_TTL_SECONDS]
    for k in stale:
        _pending_review.pop(k, None)


async def send_for_review(cleaned_text: str, media_bytes: bytes | None):
    if not REVIEW_GROUP:
        log.warning("[REVIEW] IPO_REVIEW_GROUP not set — cannot request review")
        return
    _purge_pending()
    review_id = next(_review_id_counter)
    _pending_review[review_id] = {"cleaned": cleaned_text, "media": media_bytes, "created_at": time.time()}

    # Marked with REVIEW_REQUEST_MARKER so handle_review_response can tell
    # "the bot's own notification" apart from "Shubh pasting something" —
    # both arrive from the same Telegram account/session.
    note = f"{REVIEW_REQUEST_MARKER} (#{review_id}) — reply/resend this message here to approve:\n\n{cleaned_text}"
    if media_bytes:
        await client.send_file(REVIEW_GROUP, media_bytes, caption=note)
    else:
        await client.send_message(REVIEW_GROUP, note)
    log.info(f"[REVIEW] Sent #{review_id} for approval")


async def handle_review_response(event):
    text = event.message.text or event.message.caption or ""
    if not text.strip():
        return

    # Ignore the bot's own "needs your check" notifications — otherwise a
    # review request would immediately match/trigger itself.
    if text.startswith(REVIEW_REQUEST_MARKER):
        return

    _purge_pending()
    norm_reply = _normalize_for_dedup(text)
    best_id, best_ratio = None, 0.0
    for review_id, entry in _pending_review.items():
        ratio = difflib.SequenceMatcher(None, norm_reply, _normalize_for_dedup(entry["cleaned"])).ratio()
        if ratio > best_ratio:
            best_ratio, best_id = ratio, review_id

    # Case 1 — this message approves something the bot already asked about.
    # (Unchanged — this is the logic you said is working correctly.)
    if best_id is not None and best_ratio >= APPROVAL_MATCH_THRESHOLD:
        entry = _pending_review.pop(best_id)
        log.info(f"[REVIEW] #{best_id} approved (match={best_ratio:.0%}) — sending to WhatsApp")
        if not is_duplicate(entry["cleaned"]):
            _remember_sent(entry["cleaned"])  # mark BEFORE sending — see dedup race note below
            await send_ipo_to_whatsapp(entry["cleaned"], entry["media"])
        else:
            log.info(f"[REVIEW] #{best_id} approved but turned out to be a duplicate — skipped")
        return

    # Case 2 — NEW: not approving anything pending, so treat it as you
    # manually handing the bot a message to send as-is. Still cleaned
    # (branding/link swap) and still deduped, just skipping the
    # classifier — pasting it here IS your approval.
    log.info(f"[REVIEW] No pending match (best={best_ratio:.0%}) — treating as a direct manual send")
    cleaned, _ = clean_ipo_message(text)
    if is_duplicate(cleaned):
        log.info("[REVIEW] Manual message is a duplicate of something already sent — skipped")
        return
    _remember_sent(cleaned)  # mark BEFORE sending — see dedup race note below
    media = await _download_media(event.message)
    await send_ipo_to_whatsapp(cleaned, media)



# Only listen on the review group if one is actually configured — passing
# an empty filter to Telethon would otherwise match EVERY chat, which we
# don't want.
if REVIEW_GROUP:
    client.add_event_handler(handle_review_response, events.NewMessage(chats=REVIEW_GROUP))
else:
    log.warning("[REVIEW] IPO_REVIEW_GROUP not set — review workflow is disabled")


# ══════════════════════════════════════════
#  STEP 6 — SOURCE GROUPS -> CLASSIFY -> CLEAN -> DEDUP -> SEND / REVIEW
# ══════════════════════════════════════════
async def _download_media(message):
    try:
        if message.media and isinstance(message.media, (MessageMediaPhoto, MessageMediaDocument)):
            buf = io.BytesIO()
            await client.download_media(message, file=buf)
            return buf.getvalue()
    except Exception as e:
        log.warning(f"[MEDIA] download failed: {e}")
    return None


@client.on(events.NewMessage(chats=SOURCE_GROUPS))
async def handle_ipo_source(event):
    if event.message.edit_date:
        return  # ignore edits, only act on new messages

    text = event.message.text or event.message.caption or ""
    verdict = classify_ipo_message(text)
    log.info(f"[IPO] Message from source group {event.chat_id} classified as: {verdict}")
    if verdict == "ignore":
        return

    cleaned, confident = clean_ipo_message(text)

    if is_duplicate(cleaned):
        log.info("[IPO] Duplicate of a recently sent update — skipped")
        return
    _remember_sent(cleaned)  # mark BEFORE any awaits, so a near-simultaneous
                              # repost from another group can't slip past this check

    has_media = bool(
        event.message.media and isinstance(event.message.media, (MessageMediaPhoto, MessageMediaDocument))
    )
    media = await _download_media(event.message)

    # Images can carry another group's watermark or name baked directly
    # into the picture — text cleaning can't touch that, so any message
    # with an image ALWAYS goes to review, no matter how clean the text is.
    if verdict == "auto" and confident and not has_media:
        log.info("[IPO] Matches a known structure, no red flags, no image — sending directly")
        await send_ipo_to_whatsapp(cleaned, media)
    else:
        reason = "has an image, needs your eyes on it first" if has_media else f"needs a look (verdict={verdict}, confident={confident})"
        log.info(f"[IPO] {reason} — routing to review")
        await send_for_review(cleaned, media)


# ══════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════
async def run():
    while True:
        try:
            await client.start()
            me = await client.get_me()
            log.info(f"Logged in as: {me.first_name} (@{me.username})")
            log.info(f"Watching {len(SOURCE_GROUPS)} IPO source group(s): {SOURCE_GROUPS}")
            log.info(f"Review group: {REVIEW_GROUP or 'NOT SET'}")
            log.info(f"WhatsApp targets: {len(IPO_WA_GROUPS)} group(s)")
            log.info(f"WA sender: {BAILEYS_URL or 'NOT SET'}")
            await client.run_until_disconnected()
        except Exception as e:
            log.error(f"Disconnected: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run())

# ══════════════════════════════════════════
#  DEPLOYMENT NOTES
# ══════════════════════════════════════════
# 1. Env vars to set (on your host, or a .env file):
#      API_ID, API_HASH                — same as main.py
#      IPO_STRING_SESSION              — a SECOND session string (recommended,
#                                         see point 2 below); falls back to
#                                         STRING_SESSION if unset
#      BAILEYS_URL, BAILEYS_SECRET     — same WhatsApp sender you already host
#      IPO_SOURCE_GROUPS               — comma-separated chat IDs of the IPO groups
#      IPO_REVIEW_GROUP                — chat ID/@username where you approve doubtful msgs
#      IPO_WA_GROUPS                   — comma-separated WhatsApp group JIDs (your 3 groups)
#
# 2. Run this as its own process, not merged into main.py's run(). Two
#    Telethon clients logged in with the SAME string session at the same
#    time can fight over update delivery. Cheapest fix: generate a second
#    STRING_SESSION for the same Telegram account (log in once more with
#    Telethon's normal login flow) and put it in IPO_STRING_SESSION.
#    If you deploy this on Render like main.py, it just needs to be a
#    second Background Worker service pointed at ipo_bot.py.
#
# 3. No new pip packages needed — telethon and aiohttp are already in your
#    requirements.txt.