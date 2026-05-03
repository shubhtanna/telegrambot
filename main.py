from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import asyncio, re, io, logging, time, aiohttp, os, threading, pytz

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

# FK deals → this ONE WA group only
FK_WA_GROUP = "120363427339438586@g.us"

# CC deals → this WA group
CC_WA_GROUP = "120363426468421381@g.us"

# This source group sends CC deals DIRECTLY — no bot conversion needed
CC_DIRECT_GROUP = -1001481951196

SOURCE_GROUPS = [
    -1001493857075,
    -1001412868909,
    -1001389782464,
    -1001480964161,
    CC_DIRECT_GROUP,
]

# ══════════════════════════════════════════
#  CC DEAL DETECTION  (v2 — smart multi-signal)
#
#  A message is a CC deal ONLY when it is clearly about
#  applying for / getting a credit card — NOT just a product
#  deal that mentions "cashback" or "bank offer".
#
#  Logic:
#    HARD BLOCK  → always false  (amazon/flipkart product buy links)
#    STRONG HIT  → any 1 strong keyword alone → true
#    BANK + WEAK → bank name  + ≥1 weak CC keyword → true
#    SHORT + WEAK→ CC short link + ≥1 weak CC keyword → true
#    else        → false
# ══════════════════════════════════════════

# Short-link domains used by CC affiliate programmes
CC_SHORT_LINK_PATTERNS = re.compile(
    r'https?://(?:'
    r'bilty\.co|'
    r'extp\.in|'
    r'clnk\.in|'
    r'isl\.co|'
    r'go\.onelink\.me|'
    r'onelink\.me'
    r')/\S+',
    re.IGNORECASE
)

# ── STRONG signals — these alone confirm a CC deal ──
# (card-apply / card-offer language, never used for product deals)
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

# ── WEAK signals — only meaningful alongside a bank name or CC short link ──
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

# ── All major Indian banks & NBFCs that issue credit cards ──
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

# ── FALSE-POSITIVE GUARD ──
# These patterns signal a plain product/shopping deal — never a CC deal.
# If matched, is_cc_deal() returns False even if CC keywords are present.
# e.g. "After Cashback ₹xxx  Buy: amazon.in/..."  →  product cashback offer
CC_FALSE_POSITIVE = re.compile(
    r'(?:'
    r'amazon\.in/(?:dp|gp)|'        # Amazon product link
    r'amzn\.(?:in|to)|'             # Amazon short link
    r'flipkart\.com/|'              # Flipkart product link
    r'fkrt\.\w+|'                   # Flipkart short link
    r'(?:buy|order|shop)(?: now| here| at)?\s*[:\-]?\s*https?://|'  # "Buy: <link>"
    r'(?:loot|deal|offer)\s+at\s+₹|'   # "LOOT at ₹xxx"
    r'after\s+cashback\s+₹|'           # "After Cashback ₹xxx"
    r'collect\s+cashback\s*[:\-]?\s*https?://'  # "Collect Cashback: <link>"
    r')',
    re.IGNORECASE
)

def is_cc_deal(text: str) -> bool:
    """
    Returns True ONLY for genuine credit card apply / card-offer deals.
    Product deals with cashback/bank-offer language are rejected.
    """
    if not text:
        return False

    # ── 1. Hard block — looks like a product shopping deal ──
    if CC_FALSE_POSITIVE.search(text):
        log.debug("[CC-DETECT] ❌ False-positive guard triggered — not a CC deal")
        return False

    # ── 2. Strong keyword alone → definite CC deal ──
    if CC_STRONG_KEYWORDS.search(text):
        log.debug("[CC-DETECT] ✅ Strong CC keyword matched")
        return True

    # ── 3. Bank name + weak CC keyword → CC deal ──
    has_bank = bool(BANK_NAMES.search(text))
    has_weak = bool(CC_WEAK_KEYWORDS.search(text))
    has_cc_link = bool(CC_SHORT_LINK_PATTERNS.search(text))

    if has_bank and has_weak:
        log.debug("[CC-DETECT] ✅ Bank name + weak CC keyword matched")
        return True

    # ── 4. CC short link + weak CC keyword → CC deal ──
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
    quiet_start = 0 * 60 + 30
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
}

# ══════════════════════════════════════════
#  SHARED STATE
#
#  pending_media      : { sent_msg_id → image_bytes | None }
#  sent_links_store   : { sent_msg_id → {"links": set, "is_cc": bool} }
#  sent_original_text : { sent_msg_id → original_text }
#
#  KEY FIX: All three dicts are keyed by the message ID we sent to ExtraPe.
#  When ExtraPe replies, it replies_to that same message ID, so we can
#  look up the EXACT media/metadata for that deal — no more mismatches!
# ══════════════════════════════════════════
pending_media      = {}
sent_links_store   = {}
sent_original_text = {}

client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

last_extrape_handled    = 0
last_dealspouch_handled = 0
EXTRAPE_COOLDOWN    = 15
DEALSPOUCH_COOLDOWN = 15

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

def extract_flipkart_links(text):
    if not text:
        return []
    return re.findall(
        r'https?://(?:www\.)?(?:flipkart\.com|fkrt\.\w+|dl\.flipkart\.com)[^\s]*',
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
    """
    Returns True if ExtraPe is just echoing our original input back.
    We detect this by checking if the reply's links overlap with what we sent.
    """
    if not sent_links_store:
        return False
    reply_links = extract_all_links(text)
    if not reply_links:
        return False
    for entry in sent_links_store.values():
        original_links = entry["links"]
        if reply_links & original_links:
            log.info("[EXTRAPE] 🔄 Echo detected — same links as sent. Waiting for converted reply...")
            return True
    return False

def _cleanup_store(msg_id):
    """Remove a deal's state from all tracking dicts."""
    pending_media.pop(msg_id, None)
    sent_links_store.pop(msg_id, None)
    sent_original_text.pop(msg_id, None)

def _store_deal(sent_msg_id, media_bytes, original_links, is_cc, original_text):
    """Save deal state keyed by the message ID we sent to ExtraPe."""
    pending_media[sent_msg_id]      = media_bytes
    sent_links_store[sent_msg_id]   = {"links": original_links, "is_cc": is_cc}
    sent_original_text[sent_msg_id] = original_text

    # Keep stores bounded
    if len(sent_links_store) > 20:
        oldest = next(iter(sent_links_store))
        _cleanup_store(oldest)

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
    """Send to ALL WA groups (bulk broadcast)."""
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
                    log.info(f"[WA-BULK] ✅ Queued! {body[:80]}")
            else:
                async with session.post(
                    f"{BAILEYS_URL}/send",
                    json={"text": text, "secret": BAILEYS_SECRET},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    body = await resp.text()
                    log.info(f"[WA-BULK] ✅ Queued! {body[:80]}")
        stats["sent_to_wa_bulk"] += 1
    except Exception as e:
        log.error(f"[WA-BULK] ❌ Failed: {e}")

async def send_to_whatsapp_single(text, target_group, image_bytes=None):
    """Send to ONE specific WA group."""
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
                    log.info(f"[WA-SINGLE] ✅ Sent to {target_group}! {body[:80]}")
            else:
                async with session.post(
                    f"{BAILEYS_URL}/send-single",
                    json={"text": text, "secret": BAILEYS_SECRET, "target": target_group},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    body = await resp.text()
                    log.info(f"[WA-SINGLE] ✅ Sent to {target_group}! {body[:80]}")
    except Exception as e:
        log.error(f"[WA-SINGLE] ❌ Failed: {e}")

# ══════════════════════════════════════════
#  STEP 1: Source groups → Route by deal type
# ══════════════════════════════════════════
@client.on(events.NewMessage(chats=SOURCE_GROUPS))
async def handle_source(event):
    text = event.message.text or event.message.caption or ""

    amz_links = extract_amazon_links(text)
    fk_links  = extract_flipkart_links(text)
    cc_deal   = is_cc_deal(text)

    if not amz_links and not fk_links and not cc_deal:
        return

    stats["deals_found"] += 1
    chat_id = event.chat_id

    # ══════════════════════════
    #  CC DEAL — DIRECT GROUP
    # ══════════════════════════
    if cc_deal and chat_id == CC_DIRECT_GROUP:
        log.info(f"[CC-DIRECT] 💳 CC Deal #{stats['deals_found']} from direct group!")
        media_bytes = await download_media_bytes(event.message)
        log.info(f"[CC-DIRECT] 🖼️ Image: {'yes' if media_bytes else 'no'}")

        if is_quiet_hours():
            log.info(f"[CC-DIRECT] 🌙 Quiet hours — skipping")
            stats["ignored"] += 1
        else:
            await send_to_whatsapp_single(text, CC_WA_GROUP, media_bytes)
            stats["cc_sent_direct"] += 1
            log.info("[CC-DIRECT] ✅ Sent directly to CC WA group")
        return

    # ══════════════════════════
    #  CC DEAL — OTHER GROUPS → ExtraPe
    # ══════════════════════════
    if cc_deal and chat_id != CC_DIRECT_GROUP:
        log.info(f"[CC-EXTRAPE] 💳 CC Deal #{stats['deals_found']} from group {chat_id} → ExtraPe")
        media_bytes    = await download_media_bytes(event.message)
        original_links = extract_all_links(text)

        sent = await client.send_message(EXTRAPE_BOT, text)
        _store_deal(sent.id, media_bytes, original_links, is_cc=True, original_text=text)

        stats["sent_to_extrape"] += 1
        log.info(f"[CC-EXTRAPE] 📤 Sent to ExtraPe (CC=True, msg_id={sent.id})")
        return

    # ══════════════════════════
    #  AMAZON / FLIPKART → ExtraPe
    # ══════════════════════════
    link_type = "Amazon" if amz_links else "Flipkart"
    log.info(f"[SOURCE] 🎯 {link_type} Deal #{stats['deals_found']} found!")

    media_bytes    = await download_media_bytes(event.message)
    original_links = extract_all_links(text)

    sent = await client.send_message(EXTRAPE_BOT, text)
    _store_deal(sent.id, media_bytes, original_links, is_cc=False, original_text=text)

    stats["sent_to_extrape"] += 1
    log.info(f"[EXTRAPE] 📤 Sent to ExtraPe (CC=False, msg_id={sent.id})")

# ══════════════════════════════════════════
#  STEP 2: ExtraPe reply → match by reply_to_msg_id
#
#  THE KEY FIX:
#  ExtraPe always replies_to the message we sent it.
#  We use that reply_to_msg_id to look up the EXACT media/metadata
#  for that specific deal — completely eliminating image mismatches.
#
#  ExtraPe sends 2 messages per deal:
#    Message 1 — echo of our input  → detected by is_echo_of_sent() → SKIP
#    Message 2 — converted links    → USE THIS
# ══════════════════════════════════════════
@client.on(events.NewMessage(chats=EXTRAPE_BOT))
async def handle_extrape(event):
    global last_extrape_handled

    text = event.message.text or event.message.caption or ""
    if not text:
        return

    # ── Resolve which original deal this reply belongs to ──
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
            # Fallback: grab oldest
            oldest_key = next(iter(sent_original_text))
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

    now = time.time()
    if now - last_extrape_handled < EXTRAPE_COOLDOWN:
        stats["ignored"] += 1
        log.info("[EXTRAPE] ⏭️ Duplicate ignored")
        return
    last_extrape_handled = now

    # ══════════════════════════════════════════
    #  FETCH MEDIA + CC FLAG — matched by reply_to_id
    #  This is the core fix: we look up the specific deal
    #  that ExtraPe is replying to, not just the "oldest" one.
    # ══════════════════════════════════════════
    media_bytes    = None
    pending_is_cc  = False

    if replied_to_id and replied_to_id in pending_media:
        # ✅ Exact match — use this deal's media and metadata
        media_bytes   = pending_media.get(replied_to_id)
        pending_is_cc = sent_links_store.get(replied_to_id, {}).get("is_cc", False)
        _cleanup_store(replied_to_id)
        log.info(f"[EXTRAPE] ✅ Matched deal media by reply_to_id={replied_to_id} | image={'yes' if media_bytes else 'no'}")
    else:
        # ⚠️ Fallback — ExtraPe didn't reply_to (rare), pop oldest
        log.warning("[EXTRAPE] ⚠️ No reply_to match — falling back to oldest pending deal")
        if pending_media:
            oldest_key    = next(iter(pending_media))
            media_bytes   = pending_media.get(oldest_key)
            pending_is_cc = sent_links_store.get(oldest_key, {}).get("is_cc", False)
            _cleanup_store(oldest_key)

    # ── Fallback: try ExtraPe reply's own image ──
    if not media_bytes:
        media_bytes = await download_media_bytes(event.message)
        if media_bytes:
            log.info("[EXTRAPE] 🖼️ No source image — using ExtraPe reply image as fallback")
        else:
            log.info("[EXTRAPE] 🖼️ No image available for this deal")

    ist_now = get_ist_now()

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
        sent = await client.send_message(DEALSPOUCH_BOT, text)
        # Store media keyed by Dealspouch message ID for Step 3
        pending_media[sent.id] = media_bytes
        stats["amz_sent_to_dealspouch"] += 1
        return

    log.info("[EXTRAPE] ⏭️ No recognisable link in reply — ignored")
    stats["ignored"] += 1

# ══════════════════════════════════════════
#  STEP 3: Dealspouch → TG + WA bulk
#  (Amazon only — unchanged)
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

    # Dealspouch also replies_to the message we sent it — use same matching pattern
    replied_to_id = None
    if event.message.reply_to and event.message.reply_to.reply_to_msg_id:
        replied_to_id = event.message.reply_to.reply_to_msg_id

    media_bytes = None
    if replied_to_id and replied_to_id in pending_media:
        media_bytes = pending_media.pop(replied_to_id)
        log.info(f"[DEALSPOUCH] ✅ Matched media by reply_to_id={replied_to_id}")
    elif pending_media:
        oldest_key  = next(iter(pending_media))
        media_bytes = pending_media.pop(oldest_key)
        log.warning("[DEALSPOUCH] ⚠️ Fallback to oldest pending media")

    ist_now = get_ist_now()
    log.info(f"[DEALSPOUCH] ✅ Valid! IST: {ist_now.strftime('%H:%M')} | image={'yes' if media_bytes else 'no'}")

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
            log.info(f"💳 CC Direct Group: {CC_DIRECT_GROUP}  ← no bot")
            log.info(f"🤖 ExtraPe Bot   : {EXTRAPE_BOT}  ← Amazon + Flipkart + CC (other groups)")
            log.info(f"🤖 EarnKaro Bot  : {EARNKARO_BOT}  ← fallback when ExtraPe fails")
            log.info(f"🤖 Dealspouch Bot: {DEALSPOUCH_BOT}  ← Amazon only")
            log.info(f"📢 TG Group      : {MY_TG_GROUP}")
            log.info(f"📲 FK WA Group   : {FK_WA_GROUP}")
            log.info(f"📲 CC WA Group   : {CC_WA_GROUP}")
            log.info(f"📲 WA Sender     : {BAILEYS_URL or 'NOT SET'}")
            log.info("⏳ Waiting for deals...\n")
            await client.run_until_disconnected()
        except Exception as e:
            log.error(f"Disconnected: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

asyncio.run(run())