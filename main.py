from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import asyncio, re, io, logging, time, aiohttp, os, threading, pytz, collections, random

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ══════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════
API_ID         = int(os.environ.get("API_ID"))
API_HASH       = os.environ.get("API_HASH")
STRING_SESSION = os.environ.get("STRING_SESSION")
BAILEYS_URL    = os.environ.get("BAILEYS_URL")
BAILEYS_SECRET = os.environ.get("BAILEYS_SECRET", "mysecret123")

EXTRAPE_BOT    = "@ExtraPeBot"
EARNKARO_BOT   = "@ekconverter4bot"
DEALSPOUCH_BOT = "@dealspouch_server_bot"
MY_TG_GROUP    = "@finnindeals2"

FK_WA_GROUP     = "120363427339438586@g.us"
CC_WA_GROUP     = "120363426468421381@g.us"
CC_DIRECT_GROUP = -1001481951196

SOURCE_GROUPS = [
    -1001493857075,
    -1001412868909,
    -1001389782464,
    CC_DIRECT_GROUP,
]

# ══════════════════════════════════════════
#  OPTION 1 — RATE LIMIT AT SOURCE
#
#  Max deals allowed into the pipeline per hour.
#  Once this limit is hit, new deals are dropped until the next hour window.
#  Resets automatically every hour based on IST time.
#
#  Tune MAX_DEALS_PER_HOUR to match your expected volume.
#  e.g. if ~60 deals/hour arrive and you want ~20 sent → set 20
# ══════════════════════════════════════════
MAX_DEALS_PER_HOUR  = 20        # ← adjust this to your liking
_rate_hour_window   = None      # which IST hour window is active
_rate_hour_count    = 0         # how many deals accepted this hour

def _is_rate_allowed() -> bool:
    """
    Returns True if this deal is within the hourly cap.
    Resets counter automatically when the IST hour changes.
    """
    global _rate_hour_window, _rate_hour_count
    now  = get_ist_now()
    # Use date+hour as the window key so it resets every new hour
    window = (now.date(), now.hour)
    if _rate_hour_window != window:
        _rate_hour_window = window
        _rate_hour_count  = 0
        log.info(f"[RATE] 🕐 New hour window {window} — counter reset")
    if _rate_hour_count >= MAX_DEALS_PER_HOUR:
        log.info(
            f"[RATE] 🚫 Hourly cap reached ({_rate_hour_count}/{MAX_DEALS_PER_HOUR}) "
            f"— deal dropped"
        )
        return False
    _rate_hour_count += 1
    log.info(f"[RATE] ✅ Deal accepted ({_rate_hour_count}/{MAX_DEALS_PER_HOUR} this hour)")
    return True

# ══════════════════════════════════════════
#  OPTION 2 — FRESHNESS CHECK
#
#  Maximum age (in minutes) a deal is allowed to be when it reaches
#  handle_dealspouch(). If the Dealspouch reply arrives too late
#  (queue was backed up), the deal is silently dropped.
#
#  We track the IST timestamp when each deal was first seen at source,
#  keyed by sent_msg_id. handle_dealspouch pops FIFO timestamps to match.
#
#  Tune MAX_DEAL_AGE_MINUTES to your audience's tolerance.
#  e.g. 30 = drop any deal older than 30 minutes
# ══════════════════════════════════════════
MAX_DEAL_AGE_MINUTES  = 30      # ← adjust this to your liking
dealspouch_time_queue = collections.deque()   # FIFO of source timestamps (float epoch)

# ══════════════════════════════════════════
#  CC DEAL DETECTION
# ══════════════════════════════════════════
CC_SHORT_LINK_PATTERNS = re.compile(
    r'https?://(?:'
    r'extp\.in|'
    r'clnk\.in|'
    r'isl\.co|'
    r'go\.onelink\.me|'
    r'onelink\.me'
    r')/\S+',
    re.IGNORECASE
)

CC_STRONG_KEYWORDS = re.compile(
    r'\b('
    r'credit card|'
    r'debit card|'
    r'lifetime free(?: card)?|'
    r'joining fee(?: waived)?|'
    r'annual fee(?: waived| nil| zero)?|'
    r'lounge access|'
    r'airport lounge|'
    r'fuel surcharge(?: waiver)?|'
    r'milestone benefit|'
    r'welcome bonus|'
    r'welcome voucher|'
    r'welcome gift|'
    r'card apply|'
    r'apply (?:for )?(?:the )?card|'
    r'rupay (?:credit |platinum |select )?card|'
    r'visa (?:credit |platinum |signature )?card|'
    r'mastercard|'
    r'credit score(?: check| free)?|'
    r'popcoins|'
    r'reward points(?: on card)?'
    r')\b',
    re.IGNORECASE
)

CC_WEAK_KEYWORDS = re.compile(
    r'\b('
    r'apply now|'
    r'apply here|'
    r'apply(?: in| online)?|'
    r'cashback(?: card| offer)?|'
    r'upi(?: payment| cashback| offer)?|'
    r'zero fee|'
    r'no fee|'
    r'free card|'
    r'card offer|'
    r'card benefit|'
    r'card perks?|'
    r'card limit|'
    r'eligib(?:le|ility)|'
    r'instant approval|'
    r'pre-?approved|'
    r'card (?:launch|deal|offer)'
    r')\b',
    re.IGNORECASE
)

BANK_NAMES = re.compile(
    r'\b('
    r'hdfc(?: bank)?|'
    r'sbi(?: card)?|'
    r'icici(?: bank)?|'
    r'axis(?: bank)?|'
    r'kotak(?: bank| mahindra)?|'
    r'yes bank|'
    r'idfc(?: first)?|'
    r'induslnd(?: bank)?|'
    r'rbl(?: bank)?|'
    r'au(?: small finance)?(?: bank)?|'
    r'bob(?: financial)?|'
    r'bank of baroda|'
    r'pnb(?: bank)?|'
    r'punjab national(?: bank)?|'
    r'canara(?: bank)?|'
    r'union bank|'
    r'federal bank|'
    r'south indian bank|'
    r'karnataka bank|'
    r'hsbc|'
    r'citibank|'
    r'standard chartered|'
    r'american express|'
    r'amex|'
    r'bajaj finserv|'
    r'one card|'
    r'slice(?: card)?|'
    r'uni card|'
    r'fi (?:money|card)|'
    r'niyo(?: card)?|'
    r'jupiter(?: card)?|'
    r'scapia|'
    r'idbi(?: bank)?'
    r')\b',
    re.IGNORECASE
)

CC_FALSE_POSITIVE = re.compile(
    r'(?:'
    r'amazon\.in/(?:dp|gp)|'
    r'amzn\.(?:in|to)|'
    r'flipkart\.com/|'
    r'fkrt\.\w+|'
    r'(?:buy|order|shop)(?: now| here| at)?\s*[:\-]?\s*https?://|'
    r'(?:loot|deal|offer)\s+at\s+₹|'
    r'after\s+cashback\s+₹|'
    r'collect\s+cashback\s*[:\-]?\s*https?://'
    r')',
    re.IGNORECASE
)

def is_cc_deal(text: str) -> bool:
    if not text:
        return False
    if CC_FALSE_POSITIVE.search(text):
        log.debug("[CC-DETECT] ❌ False-positive guard triggered — not a CC deal")
        return False
    if CC_STRONG_KEYWORDS.search(text):
        log.debug("[CC-DETECT] ✅ Strong CC keyword matched")
        return True
    has_bank    = bool(BANK_NAMES.search(text))
    has_weak    = bool(CC_WEAK_KEYWORDS.search(text))
    has_cc_link = bool(CC_SHORT_LINK_PATTERNS.search(text))
    if has_bank and has_weak:
        log.debug("[CC-DETECT] ✅ Bank name + weak CC keyword matched")
        return True
    if has_cc_link and has_weak:
        log.debug("[CC-DETECT] ✅ CC short link + weak CC keyword matched")
        return True
    return False

def extract_cc_short_links(text):
    if not text:
        return []
    return CC_SHORT_LINK_PATTERNS.findall(text)

# ══════════════════════════════════════════
#  IST TIME HELPERS
# ══════════════════════════════════════════
def get_ist_now():
    ist = pytz.timezone("Asia/Kolkata")
    return datetime.now(ist)

def is_quiet_hours():
    now = get_ist_now()
    current_minutes = now.hour * 60 + now.minute
    quiet_start = 1 * 60 + 0
    quiet_end   = 8 * 60 + 0
    return quiet_start <= current_minutes < quiet_end

# ══════════════════════════════════════════
#  HEALTH CHECK
# ══════════════════════════════════════════
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    def log_message(self, *args):
        pass

threading.Thread(
    target=lambda: HTTPServer(("0.0.0.0", 8080), HealthCheck).serve_forever(),
    daemon=True
).start()

# ══════════════════════════════════════════
#  STATS
# ══════════════════════════════════════════
stats = {
    "deals_found": 0,
    "sent_to_extrape": 0,
    "fk_sent_to_wa": 0,
    "cc_sent_direct": 0,
    "cc_sent_via_extrape": 0,
    "amz_sent_to_dealspouch": 0,
    "posted_to_tg": 0,
    "sent_to_wa_bulk": 0,
    "ignored": 0,
    "rate_dropped": 0,
    "stale_dropped": 0,
}

# ══════════════════════════════════════════
#  DAILY DEAL COUNTER (random 13 WA invite replacements)
# ══════════════════════════════════════════
_daily_counter_date = None
_daily_deal_count   = 0
_lucky_deal_slots   = set()

WA_INVITE_LINK      = "https://tinyurl.com/fhknr97k"
TG_BOT_FOOTER       = "\n\nTelegram Bot - t.me/Dealspouch_Product_bot"
LUCKY_DEALS_PER_DAY = 13        # ← updated from 10 to 13

def _refresh_daily_counter():
    global _daily_counter_date, _daily_deal_count, _lucky_deal_slots
    today = get_ist_now().date()
    if _daily_counter_date != today:
        _daily_counter_date = today
        _daily_deal_count   = 0
        # Sample from first 60 deals expected today
        # Increase range if you expect more than 60 Amazon deals/day
        _lucky_deal_slots   = set(random.sample(range(1, 61), LUCKY_DEALS_PER_DAY))
        log.info(f"[DAILY] 🗓️ New day {today} — lucky slots: {sorted(_lucky_deal_slots)}")

def _is_lucky_deal() -> bool:
    global _daily_deal_count
    _refresh_daily_counter()
    _daily_deal_count += 1
    lucky = _daily_deal_count in _lucky_deal_slots
    log.info(f"[DAILY] Deal #{_daily_deal_count} today | lucky={lucky}")
    return lucky

# ══════════════════════════════════════════
#  SHARED STATE
#
#  pending_media          : { sent_msg_id → image_bytes | None }
#  sent_links_store       : { sent_msg_id → {"links": set, "is_cc": bool} }
#  sent_original_text     : { sent_msg_id → original_text }
#
#  dealspouch_media_queue : FIFO deque of image_bytes|None
#  dealspouch_time_queue  : FIFO deque of source timestamps (for freshness check)
#
#  IMAGE INTEGRITY: Never pop oldest on reply_to mismatch.
#  FRESHNESS:       Drop deals older than MAX_DEAL_AGE_MINUTES at send time.
# ══════════════════════════════════════════
pending_media          = {}
sent_links_store       = {}
sent_original_text     = {}
dealspouch_media_queue = collections.deque()

client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

last_dealspouch_handled     = 0
DEALSPOUCH_COOLDOWN         = 15
extrape_seen_hashes         = set()
extrape_processed_reply_ids = set()
source_seen_hashes          = set()

# ══════════════════════════════════════════
#  LINK DETECTORS
# ══════════════════════════════════════════
def extract_amazon_links(text):
    if not text:
        return []
    return re.findall(
        r'https?://(?:www\.)?(?:amazon\.in|amzn\.in|amzn\.to|amazon\.com)[^\s]*',
        text
    )

def extract_flipkart_links_source(text):
    if not text:
        return []
    return re.findall(
        r'https?://(?:www\.)?(?:flipkart\.com|fkrt\.\w+|dl\.flipkart\.com)[^\s]*',
        text
    )

def extract_flipkart_links(text):
    if not text:
        return []
    return re.findall(
        r'https?://(?:www\.)?(?:flipkart\.com|fkrt\.\w+|dl\.flipkart\.com|bilty\.co)[^\s]*',
        text
    )

def extract_all_links(text):
    if not text:
        return set()
    return set(re.findall(r'https?://\S+', text))

def has_dealspouch_link(text):
    return text and "amaz.dealspouch.com" in text

def is_extrape_failure(text):
    if not text:
        return False
    return "will not be able to convert" in text.lower()

def is_echo_of_sent(text):
    if not sent_links_store:
        return False
    reply_links = extract_all_links(text)
    if not reply_links:
        return False
    for entry in sent_links_store.values():
        if reply_links & entry["links"]:
            log.info("[EXTRAPE] 🔄 Echo detected — same links as sent. Waiting for converted reply...")
            return True
    return False

def _cleanup_store(msg_id):
    pending_media.pop(msg_id, None)
    sent_links_store.pop(msg_id, None)
    sent_original_text.pop(msg_id, None)

def _store_deal(sent_msg_id, media_bytes, original_links, is_cc, original_text):
    pending_media[sent_msg_id]      = media_bytes
    sent_links_store[sent_msg_id]   = {"links": original_links, "is_cc": is_cc}
    sent_original_text[sent_msg_id] = original_text
    if len(sent_links_store) > 20:
        oldest = next(iter(sent_links_store))
        _cleanup_store(oldest)

# ══════════════════════════════════════════
#  TEXT SANITIZER
# ══════════════════════════════════════════
_FAKE_URL_RE = re.compile(
    r'https?://(?!'
    r'(?:[a-z0-9\-]+\.)+[a-z]{2,}'
    r')\S*',
    re.IGNORECASE
)

def sanitize_text_for_bot(text: str) -> str:
    if not text:
        return text
    cleaned = _FAKE_URL_RE.sub('', text).strip()
    if cleaned != text:
        log.info("[SANITIZE] Removed fake URL fragments from text")
    return cleaned

# ══════════════════════════════════════════
#  MEDIA DOWNLOADER
# ══════════════════════════════════════════
async def download_media_bytes(message):
    try:
        if message.media and isinstance(message.media, (MessageMediaPhoto, MessageMediaDocument)):
            buf = io.BytesIO()
            await client.download_media(message, file=buf)
            return buf.getvalue()
    except Exception as e:
        log.warning(f"Media download failed: {e}")
    return None

# ══════════════════════════════════════════
#  WHATSAPP SENDERS
# ══════════════════════════════════════════
async def send_to_whatsapp_bulk(text, image_bytes=None):
    if not BAILEYS_URL:
        log.warning("[WA-BULK] BAILEYS_URL not set!")
        return
    try:
        async with aiohttp.ClientSession() as session:
            if image_bytes:
                form = aiohttp.FormData()
                form.add_field("text", text or "")
                form.add_field("secret", BAILEYS_SECRET)
                form.add_field("image", image_bytes, filename="deal.jpg", content_type="image/jpeg")
                async with session.post(
                    f"{BAILEYS_URL}/send", data=form,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        log.error(f"[WA-BULK] ❌ HTTP {resp.status} — WA sender may be down! {body[:120]}")
                        return
                    log.info(f"[WA-BULK] ✅ Queued! {body[:80]}")
            else:
                async with session.post(
                    f"{BAILEYS_URL}/send",
                    json={"text": text, "secret": BAILEYS_SECRET},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        log.error(f"[WA-BULK] ❌ HTTP {resp.status} — WA sender may be down! {body[:120]}")
                        return
                    log.info(f"[WA-BULK] ✅ Queued! {body[:80]}")
        stats["sent_to_wa_bulk"] += 1
    except Exception as e:
        log.error(f"[WA-BULK] ❌ Failed: {e}")

async def send_to_whatsapp_single(text, target_group, image_bytes=None):
    if not BAILEYS_URL:
        log.warning("[WA-SINGLE] BAILEYS_URL not set!")
        return
    try:
        async with aiohttp.ClientSession() as session:
            if image_bytes:
                form = aiohttp.FormData()
                form.add_field("text", text or "")
                form.add_field("secret", BAILEYS_SECRET)
                form.add_field("target", target_group)
                form.add_field("image", image_bytes, filename="deal.jpg", content_type="image/jpeg")
                async with session.post(
                    f"{BAILEYS_URL}/send-single", data=form,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        log.error(f"[WA-SINGLE] ❌ HTTP {resp.status} — WA sender may be down! {body[:120]}")
                        return
                    log.info(f"[WA-SINGLE] ✅ Sent to {target_group}! {body[:80]}")
            else:
                async with session.post(
                    f"{BAILEYS_URL}/send-single",
                    json={"text": text, "secret": BAILEYS_SECRET, "target": target_group},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        log.error(f"[WA-SINGLE] ❌ HTTP {resp.status} — WA sender may be down! {body[:120]}")
                        return
                    log.info(f"[WA-SINGLE] ✅ Sent to {target_group}! {body[:80]}")
    except Exception as e:
        log.error(f"[WA-SINGLE] ❌ Failed: {e}")

# ══════════════════════════════════════════
#  STEP 1: Source groups → Route by deal type
#
#  RATE LIMIT applied here — before any processing.
#  CC_DIRECT_GROUP deals are exempt from rate limit
#  (CC deals are low volume and time-sensitive).
# ══════════════════════════════════════════
@client.on(events.NewMessage(chats=SOURCE_GROUPS))
async def handle_source(event):
    if event.message.edit_date:
        return

    text      = event.message.text or event.message.caption or ""
    amz_links = extract_amazon_links(text)
    fk_links  = extract_flipkart_links_source(text)
    cc_deal   = is_cc_deal(text)

    if not amz_links and not fk_links and not cc_deal:
        return

    stats["deals_found"] += 1
    chat_id = event.chat_id

    # ── CC DEAL — DIRECT GROUP (exempt from rate limit, straight to WA) ──
    if cc_deal and chat_id == CC_DIRECT_GROUP:
        log.info(f"[CC-DIRECT] 💳 CC Deal #{stats['deals_found']} from direct group!")
        media_bytes = await download_media_bytes(event.message)
        log.info(f"[CC-DIRECT] 🖼️ Image: {'yes' if media_bytes else 'no'}")
        if is_quiet_hours():
            log.info("[CC-DIRECT] 🌙 Quiet hours — skipping")
            stats["ignored"] += 1
        else:
            await send_to_whatsapp_single(text, CC_WA_GROUP, media_bytes)
            stats["cc_sent_direct"] += 1
            log.info("[CC-DIRECT] ✅ Sent directly to CC WA group")
        return

    # ── Source-level dedup ──
    all_links_in_msg = sorted(extract_all_links(text))
    if all_links_in_msg:
        dedup_key   = hash(tuple(all_links_in_msg))
        dedup_label = f"links:{all_links_in_msg}"
    else:
        normalized  = re.sub(r'\s+', ' ', text.strip().lower())
        dedup_key   = hash(normalized)
        dedup_label = "normalized-text"

    if dedup_key in source_seen_hashes:
        log.info(f"[SOURCE] ⏭️ Duplicate ({dedup_label}) — already dispatched, skipping")
        return
    source_seen_hashes.add(dedup_key)
    if len(source_seen_hashes) > 500:
        source_seen_hashes.pop()

    # ── OPTION 1: Rate limit check (after dedup, before processing) ──
    # CC deals from other groups are also exempt — they are rare and valuable.
    if not cc_deal and not _is_rate_allowed():
        stats["rate_dropped"] += 1
        return

    # Record source timestamp for freshness check later (Amazon deals only)
    # We push this into dealspouch_time_queue alongside media in handle_extrape
    source_ts = time.time()

    # ── CC DEAL — OTHER GROUPS → ExtraPe ──
    if cc_deal and chat_id != CC_DIRECT_GROUP:
        log.info(f"[CC-EXTRAPE] 💳 CC Deal #{stats['deals_found']} from group {chat_id} → ExtraPe")
        media_bytes    = await download_media_bytes(event.message)
        original_links = extract_all_links(text)
        clean_text     = sanitize_text_for_bot(text)
        sent = await client.send_message(EXTRAPE_BOT, clean_text)
        _store_deal(sent.id, media_bytes, original_links, is_cc=True, original_text=clean_text)
        # Store source timestamp on the deal so we can check freshness later
        sent_links_store[sent.id]["source_ts"] = source_ts
        stats["sent_to_extrape"] += 1
        log.info(f"[CC-EXTRAPE] 📤 Sent to ExtraPe (CC=True, msg_id={sent.id})")
        return

    # ── AMAZON / FLIPKART → ExtraPe ──
    link_type      = "Amazon" if amz_links else "Flipkart"
    log.info(f"[SOURCE] 🎯 {link_type} Deal #{stats['deals_found']} found!")
    media_bytes    = await download_media_bytes(event.message)
    original_links = extract_all_links(text)
    clean_text     = sanitize_text_for_bot(text)
    sent = await client.send_message(EXTRAPE_BOT, clean_text)
    _store_deal(sent.id, media_bytes, original_links, is_cc=False, original_text=clean_text)
    # Store source timestamp on the deal
    sent_links_store[sent.id]["source_ts"] = source_ts
    stats["sent_to_extrape"] += 1
    log.info(f"[EXTRAPE] 📤 Sent to ExtraPe (CC=False, msg_id={sent.id})")

# ══════════════════════════════════════════
#  STEP 2: ExtraPe reply → match by reply_to_msg_id
# ══════════════════════════════════════════
@client.on(events.NewMessage(chats=EXTRAPE_BOT))
async def handle_extrape(event):
    text = event.message.text or event.message.caption or ""
    if not text:
        return

    replied_to_id = None
    if event.message.reply_to and event.message.reply_to.reply_to_msg_id:
        replied_to_id = event.message.reply_to.reply_to_msg_id
        log.info(f"[EXTRAPE] 🔗 Reply to msg_id={replied_to_id}")

    # ── ExtraPe failure → forward original to EarnKaro ──
    if is_extrape_failure(text):
        log.info("[EXTRAPE] ❌ Conversion failed — forwarding original to EarnKaro")
        original_text = None
        if replied_to_id and replied_to_id in sent_original_text:
            original_text = sent_original_text.get(replied_to_id)
            _cleanup_store(replied_to_id)
        elif sent_original_text:
            oldest_key    = next(iter(sent_original_text))
            original_text = sent_original_text.get(oldest_key)
            _cleanup_store(oldest_key)
        if original_text:
            await client.send_message(EARNKARO_BOT, original_text)
            log.info("[EARNKARO] 📤 Forwarded original deal to EarnKaro")
            stats["ignored"] += 1
        else:
            log.warning("[EARNKARO] ⚠️ No original text found to forward")
        return

    # ── Skip echo of our own input ──
    if is_echo_of_sent(text):
        return

    # ── Skip already-processed reply_to_id ──
    if replied_to_id and replied_to_id in extrape_processed_reply_ids:
        log.info(f"[EXTRAPE] ⏭️ reply_to_id={replied_to_id} already processed — skipping duplicate")
        stats["ignored"] += 1
        return

    # ── Dedup by content hash ──
    msg_hash = hash(text.strip())
    if msg_hash in extrape_seen_hashes:
        stats["ignored"] += 1
        log.info("[EXTRAPE] ⏭️ Exact duplicate content — ignored")
        return
    extrape_seen_hashes.add(msg_hash)
    if len(extrape_seen_hashes) > 50:
        extrape_seen_hashes.pop()

    # ══════════════════════════════════════════
    #  FETCH MEDIA + CC FLAG + SOURCE TIMESTAMP
    #
    #  IMAGE INTEGRITY: Never pop oldest on reply_to mismatch.
    #  FRESHNESS: Carry source_ts forward into dealspouch queues.
    # ══════════════════════════════════════════
    media_bytes   = None
    pending_is_cc = False
    source_ts     = time.time()   # fallback: use now (conservative — won't be stale)

    if replied_to_id and replied_to_id in pending_media:
        # ✅ Exact match
        media_bytes   = pending_media.get(replied_to_id)
        store_entry   = sent_links_store.get(replied_to_id, {})
        pending_is_cc = store_entry.get("is_cc", False)
        source_ts     = store_entry.get("source_ts", time.time())
        _cleanup_store(replied_to_id)
        log.info(
            f"[EXTRAPE] ✅ Matched reply_to_id={replied_to_id} | "
            f"cc={pending_is_cc} | image={'yes' if media_bytes else 'no'} | "
            f"age={(time.time()-source_ts)/60:.1f}min"
        )
    else:
        # ❌ No match — DO NOT pop oldest (prevents image mismatch)
        log.warning(
            "[EXTRAPE] ⚠️ No reply_to match — will try ExtraPe's own image only"
        )

    # ── Fallback: ExtraPe reply's own attached image (safe, deal-specific) ──
    if not media_bytes:
        media_bytes = await download_media_bytes(event.message)
        if media_bytes:
            log.info("[EXTRAPE] 🖼️ Using ExtraPe reply's own image as fallback")
        else:
            log.info("[EXTRAPE] 🖼️ No image available — will send text only")

    ist_now = get_ist_now()

    # ── Mark reply_to_id as processed ──
    if replied_to_id:
        extrape_processed_reply_ids.add(replied_to_id)
        if len(extrape_processed_reply_ids) > 100:
            extrape_processed_reply_ids.pop()

    # ── CC deal → CC WA group ──
    if pending_is_cc or is_cc_deal(text):
        log.info(f"[EXTRAPE] 💳 CC deal → CC WA group | image={'yes' if media_bytes else 'no'}")
        if is_quiet_hours():
            log.info(f"[WA-SINGLE] 🌙 Quiet hours ({ist_now.strftime('%H:%M')} IST) — skipping CC")
            stats["ignored"] += 1
        else:
            await send_to_whatsapp_single(text, CC_WA_GROUP, media_bytes)
            stats["cc_sent_via_extrape"] += 1
        return

    # ── Flipkart → FK WA group ──
    if extract_flipkart_links(text):
        log.info(f"[EXTRAPE] 🛒 FK converted → FK WA group | image={'yes' if media_bytes else 'no'}")
        if is_quiet_hours():
            log.info(f"[WA-SINGLE] 🌙 Quiet hours ({ist_now.strftime('%H:%M')} IST) — skipping FK")
            stats["ignored"] += 1
        else:
            await send_to_whatsapp_single(text, FK_WA_GROUP, media_bytes)
            stats["fk_sent_to_wa"] += 1
        return

    # ── Amazon → Dealspouch ──
    if extract_amazon_links(text):
        log.info(f"[EXTRAPE] ✅ AMZ converted → Dealspouch | image={'yes' if media_bytes else 'no'}")
        await client.send_message(DEALSPOUCH_BOT, text)

        # Push image + timestamp together (both FIFOs stay in sync)
        dealspouch_media_queue.append(media_bytes)
        dealspouch_time_queue.append(source_ts)
        if len(dealspouch_media_queue) > 20:
            dealspouch_media_queue.popleft()
            dealspouch_time_queue.popleft()
        log.info(
            f"[DEALSPOUCH-QUEUE] 📥 Pushed image={'yes' if media_bytes else 'no'} | "
            f"age={(time.time()-source_ts)/60:.1f}min | "
            f"queue size: {len(dealspouch_media_queue)}"
        )
        stats["amz_sent_to_dealspouch"] += 1
        return

    log.info("[EXTRAPE] ⏭️ No recognisable link in reply — ignored")
    stats["ignored"] += 1

# ══════════════════════════════════════════
#  STEP 3: Dealspouch → TG + WA bulk  (Amazon only)
#
#  OPTION 2 — FRESHNESS CHECK applied here.
#  We pop the source timestamp from dealspouch_time_queue (FIFO, in sync
#  with dealspouch_media_queue). If the deal is older than
#  MAX_DEAL_AGE_MINUTES, it is dropped silently — never sent to TG or WA.
# ══════════════════════════════════════════
@client.on(events.NewMessage(chats=DEALSPOUCH_BOT))
async def handle_dealspouch(event):
    global last_dealspouch_handled
    text = event.message.text or event.message.caption or ""

    if not has_dealspouch_link(text):
        stats["ignored"] += 1
        log.info("[DEALSPOUCH] ⏭️ Ignored — no dealspouch link")
        return

    now = time.time()
    if now - last_dealspouch_handled < DEALSPOUCH_COOLDOWN:
        stats["ignored"] += 1
        log.info("[DEALSPOUCH] ⏭️ Duplicate ignored")
        return
    last_dealspouch_handled = now

    # ✅ Pop image from FIFO queue
    media_bytes = None
    if dealspouch_media_queue:
        media_bytes = dealspouch_media_queue.popleft()
        log.info(
            f"[DEALSPOUCH] ✅ Popped from queue | "
            f"image={'yes' if media_bytes else 'no'} | "
            f"remaining={len(dealspouch_media_queue)}"
        )
    else:
        log.warning("[DEALSPOUCH] ⚠️ Media queue empty — sending text only")

    # ── OPTION 2: Freshness check — pop matching timestamp ──
    source_ts = None
    if dealspouch_time_queue:
        source_ts = dealspouch_time_queue.popleft()
        age_minutes = (time.time() - source_ts) / 60
        log.info(f"[FRESHNESS] 🕐 Deal age: {age_minutes:.1f} min (max allowed: {MAX_DEAL_AGE_MINUTES} min)")
        if age_minutes > MAX_DEAL_AGE_MINUTES:
            log.info(
                f"[FRESHNESS] 🗑️ Deal is {age_minutes:.1f} min old — "
                f"exceeds {MAX_DEAL_AGE_MINUTES} min limit → DROPPED"
            )
            stats["stale_dropped"] += 1
            return
    else:
        log.warning("[FRESHNESS] ⚠️ Time queue empty — skipping freshness check")

    ist_now = get_ist_now()
    log.info(f"[DEALSPOUCH] ✅ Fresh deal! IST: {ist_now.strftime('%H:%M')} | image={'yes' if media_bytes else 'no'}")

    # ── Lucky deal: replace dealspouch link with WA invite ──
    if _is_lucky_deal():
        text = re.sub(r'https?://amaz\.dealspouch\.com/\S+', WA_INVITE_LINK, text)
        log.info("[DAILY] 🎯 Lucky deal — replaced dealspouch link with WA invite")

    # ── Append TG bot footer to every Amazon deal ──
    text = text + TG_BOT_FOOTER

    # Always post to Telegram
    try:
        if media_bytes:
            await client.send_file(MY_TG_GROUP, media_bytes, caption=text)
        else:
            await client.send_message(MY_TG_GROUP, text)
        stats["posted_to_tg"] += 1
        log.info(f"[TG] ✅ Posted to {MY_TG_GROUP}")
    except Exception as e:
        log.error(f"[TG] ❌ Failed: {e}")

    if is_quiet_hours():
        log.info(f"[WA-BULK] 🌙 Quiet hours ({ist_now.strftime('%H:%M')} IST) — skipping")
    else:
        await send_to_whatsapp_bulk(text, media_bytes)

# ══════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════
async def run():
    while True:
        try:
            await client.start()
            me = await client.get_me()
            log.info(f"✅ Logged in as: {me.first_name} (@{me.username})")
            log.info(f"👂 Watching {len(SOURCE_GROUPS)} source group(s)")
            log.info(f"💳 CC Direct Group : {CC_DIRECT_GROUP}  ← no bot, rate-limit exempt")
            log.info(f"🤖 ExtraPe Bot     : {EXTRAPE_BOT}  ← Amazon + Flipkart + CC (other groups)")
            log.info(f"🤖 EarnKaro Bot    : {EARNKARO_BOT}  ← fallback when ExtraPe fails")
            log.info(f"🤖 Dealspouch Bot  : {DEALSPOUCH_BOT}  ← Amazon only")
            log.info(f"📢 TG Group        : {MY_TG_GROUP}")
            log.info(f"📲 FK WA Group     : {FK_WA_GROUP}")
            log.info(f"📲 CC WA Group     : {CC_WA_GROUP}")
            log.info(f"📲 WA Sender       : {BAILEYS_URL or 'NOT SET'}")
            log.info(f"🚦 Rate limit      : {MAX_DEALS_PER_HOUR} Amazon/FK deals per hour (CC exempt)")
            log.info(f"⏱️  Freshness limit : drop Amazon deals older than {MAX_DEAL_AGE_MINUTES} min")
            log.info(f"🎯 Lucky deals/day : {LUCKY_DEALS_PER_DAY} (WA invite replaces dealspouch link)")
            log.info(f"📌 TG Bot Footer   : {TG_BOT_FOOTER.strip()}")
            log.info("⏳ Waiting for deals...\n")
            await client.run_until_disconnected()
        except Exception as e:
            log.error(f"Disconnected: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

asyncio.run(run())
