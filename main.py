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

# CC deals → this WA group (replace with real ID when ready)
CC_WA_GROUP = "120363426468421381@g.us"

# This source group sends CC deals DIRECTLY — no bot conversion needed
CC_DIRECT_GROUP = -1001481951196

SOURCE_GROUPS = [
    -1001493857075,
    -1001412868909,
    -1001389782464,
    -1001480964161,
    CC_DIRECT_GROUP,          # ← added CC direct group
]

# ══════════════════════════════════════════
#  CC DEAL DETECTION
# ══════════════════════════════════════════

# Short-link domains used in CC deals
CC_SHORT_LINK_PATTERNS = re.compile(
    r'https?://(?:'
    r'bilty\.co|'
    r'extp\.in|'
    r'bit\.ly|'
    r'tinyurl\.com|'
    r'clnk\.in|'
    r'isl\.co|'
    r'go\.onelink\.me'
    r')/\S+',
    re.IGNORECASE
)

# Keywords that strongly indicate a CC deal post
CC_KEYWORDS = re.compile(
    r'\b('
    r'credit card|'
    r'lifetime free|'
    r'joining fee|'
    r'annual fee|'
    r'cashback|'
    r'rupay|'
    r'rupay card|'
    r'lounge access|'
    r'airport lounge|'
    r'credit score|'
    r'popcoins|'
    r'upi payment|'
    r'welcome voucher|'
    r'fuel surcharge|'
    r'reward points|'
    r'apply now|'
    r'apply here|'
    r'apply in'
    r')\b',
    re.IGNORECASE
)

def is_cc_deal(text):
    """
    Returns True if text looks like a credit card offer.
    Requires BOTH a short link AND at least one CC keyword,
    OR a strong keyword match alone (≥2 keyword hits).
    """
    if not text:
        return False

    has_short_link = bool(CC_SHORT_LINK_PATTERNS.search(text))
    keyword_hits   = len(CC_KEYWORDS.findall(text))

    if has_short_link and keyword_hits >= 1:
        return True
    if keyword_hits >= 2:          # Strong keyword signal even without known short link
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
# ══════════════════════════════════════════
pending_media = {}

# Store original links we sent to ExtraPe so we can detect echoes
# { sent_message_id: {"links": set, "is_cc": bool} }
sent_links_store = {}

client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

last_extrape_handled    = 0
last_dealspouch_handled = 0
EXTRAPE_COOLDOWN    = 15
DEALSPOUCH_COOLDOWN = 15

# ══════════════════════════════════════════
#  LINK DETECTORS (Amazon / Flipkart)
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
    """
    Returns True if ExtraPe could not convert the link.
    ExtraPe's failure message: "We will not be able to convert these Links: ..."
    """
    if not text:
        return False
    return "will not be able to convert" in text.lower()

# Store original full message text we sent to ExtraPe
# { sent_message_id: original_text }
sent_original_text = {}

def is_echo_of_sent(text):
    """
    Returns True if the links in ExtraPe's reply are the SAME as what we sent.
    This means ExtraPe is echoing our input, not sending the converted reply.
    """
    if not sent_links_store:
        return False
    reply_links = extract_all_links(text)
    if not reply_links:
        return False
    for entry in sent_links_store.values():
        original_links = entry["links"]
        if reply_links & original_links:
            log.info(f"[EXTRAPE] 🔄 Echo detected — same links as sent. Waiting for converted reply...")
            return True
    return False

def get_pending_is_cc():
    """
    Check if the oldest pending ExtraPe request was a CC deal.
    Returns True if it was CC, False otherwise.
    """
    if not sent_links_store:
        return False
    oldest_key = next(iter(sent_links_store))
    return sent_links_store[oldest_key].get("is_cc", False)

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
#
#  CC_DIRECT_GROUP  → CC deal → send directly to CC WA group
#  All other groups → CC deal → ExtraPe bot for conversion
#  All groups       → AMZ/FK  → ExtraPe bot (existing flow)
# ══════════════════════════════════════════
@client.on(events.NewMessage(chats=SOURCE_GROUPS))
async def handle_source(event):
    text = event.message.text or event.message.caption or ""

    amz_links = extract_amazon_links(text)
    fk_links  = extract_flipkart_links(text)
    cc_deal   = is_cc_deal(text)

    # ── Nothing relevant ──
    if not amz_links and not fk_links and not cc_deal:
        return

    stats["deals_found"] += 1
    chat_id = event.chat_id

    # ══════════════════════════
    #  CC DEAL — DIRECT GROUP
    #  No bot conversion needed
    # ══════════════════════════
    if cc_deal and chat_id == CC_DIRECT_GROUP:
        log.info(f"[CC-DIRECT] 💳 CC Deal #{stats['deals_found']} from direct group!")
        media_bytes = await download_media_bytes(event.message)
        log.info(f"[CC-DIRECT] 🖼️ Image: {'yes' if media_bytes else 'no'}")

        ist_now = get_ist_now()
        if is_quiet_hours():
            log.info(f"[CC-DIRECT] 🌙 Quiet hours ({ist_now.strftime('%H:%M')} IST) — skipping")
            stats["ignored"] += 1
        else:
            await send_to_whatsapp_single(text, CC_WA_GROUP, media_bytes)
            stats["cc_sent_direct"] += 1
            log.info(f"[CC-DIRECT] ✅ Sent directly to CC WA group")
        return

    # ══════════════════════════
    #  CC DEAL — OTHER GROUPS
    #  Send to ExtraPe for link conversion
    # ══════════════════════════
    if cc_deal and chat_id != CC_DIRECT_GROUP:
        log.info(f"[CC-EXTRAPE] 💳 CC Deal #{stats['deals_found']} from group {chat_id} → ExtraPe")
        media_bytes = await download_media_bytes(event.message)
        log.info(f"[CC-EXTRAPE] 🖼️ Image: {'yes' if media_bytes else 'no'}")

        temp_key = int(asyncio.get_event_loop().time() * 1000)
        pending_media[temp_key] = media_bytes
        original_links = extract_all_links(text)

        sent = await client.send_message(EXTRAPE_BOT, text)
        pending_media[sent.id] = pending_media.pop(temp_key)

        # Track this as a CC deal so handle_extrape knows where to route
        sent_links_store[sent.id] = {"links": original_links, "is_cc": True}
        sent_original_text[sent.id] = text

        if len(sent_links_store) > 20:
            oldest = next(iter(sent_links_store))
            del sent_links_store[oldest]
            if oldest in sent_original_text:
                del sent_original_text[oldest]

        stats["sent_to_extrape"] += 1
        log.info(f"[CC-EXTRAPE] 📤 Sent to ExtraPe (CC=True, tracking {len(original_links)} link(s))")
        return

    # ══════════════════════════
    #  AMAZON / FLIPKART DEALS
    #  Existing flow unchanged
    # ══════════════════════════
    link_type = "Amazon" if amz_links else "Flipkart"
    log.info(f"[SOURCE] 🎯 {link_type} Deal #{stats['deals_found']} found!")

    media_bytes = await download_media_bytes(event.message)
    log.info(f"[SOURCE] 🖼️ Image: {'yes' if media_bytes else 'no'}")

    temp_key = int(asyncio.get_event_loop().time() * 1000)
    pending_media[temp_key] = media_bytes
    original_links = extract_all_links(text)

    sent = await client.send_message(EXTRAPE_BOT, text)
    pending_media[sent.id] = pending_media.pop(temp_key)

    sent_links_store[sent.id] = {"links": original_links, "is_cc": False}
    sent_original_text[sent.id] = text

    if len(sent_links_store) > 20:
        oldest = next(iter(sent_links_store))
        del sent_links_store[oldest]
        if oldest in sent_original_text:
            del sent_original_text[oldest]

    stats["sent_to_extrape"] += 1
    log.info(f"[EXTRAPE] 📤 Sent to ExtraPe (CC=False, tracking {len(original_links)} original link(s))")

# ══════════════════════════════════════════
#  STEP 2: ExtraPe reply → route by deal type
#
#  ExtraPe sends 2 messages:
#    Message 1 — echo of original input  → SKIP (same links we sent)
#    Message 2 — converted links + image → USE THIS
#
#  If pending deal was CC  → send to CC WA group
#  If Flipkart             → send to FK WA group
#  If Amazon               → send to Dealspouch
# ══════════════════════════════════════════
@client.on(events.NewMessage(chats=EXTRAPE_BOT))
async def handle_extrape(event):
    global last_extrape_handled

    text = event.message.text or event.message.caption or ""
    if not text:
        return

    # ── ExtraPe couldn't convert → forward original to EarnKaro ──
    if is_extrape_failure(text):
        log.info(f"[EXTRAPE] ❌ Conversion failed — forwarding original to EarnKaro")

        # Get the original text we sent to ExtraPe
        original_text = None
        if sent_original_text:
            oldest_key = next(iter(sent_original_text))
            original_text = sent_original_text.pop(oldest_key)

        # Clean up state
        sent_links_store.clear()
        if pending_media:
            oldest_key = next(iter(pending_media))
            pending_media.pop(oldest_key)

        if original_text:
            await client.send_message(EARNKARO_BOT, original_text)
            log.info(f"[EARNKARO] 📤 Forwarded original deal to EarnKaro bot — done, no WA/TG")
            stats["ignored"] += 1   # not sent to WA, just forwarded for manual handling
        else:
            log.warning(f"[EARNKARO] ⚠️ No original text found to forward")
        return

    # ── Skip if ExtraPe is echoing our original input ──
    if is_echo_of_sent(text):
        return

    now = time.time()
    if now - last_extrape_handled < EXTRAPE_COOLDOWN:
        stats["ignored"] += 1
        log.info(f"[EXTRAPE] ⏭️ Duplicate ignored")
        return
    last_extrape_handled = now

    # Was this a CC deal we sent?
    pending_is_cc = get_pending_is_cc()

    # Clear sent_links_store since we got the converted reply
    sent_links_store.clear()
    sent_original_text.clear()

    # Get source image
    media_bytes = None
    if pending_media:
        oldest_key = next(iter(pending_media))
        media_bytes = pending_media.pop(oldest_key)

    # Fallback — try ExtraPe reply image
    if not media_bytes:
        media_bytes = await download_media_bytes(event.message)
        if media_bytes:
            log.info(f"[EXTRAPE] 🖼️ Using image from ExtraPe reply")

    ist_now = get_ist_now()

    # ── CC deal from other groups → CC WA group ──
    # Check both: was it flagged as CC when sent, AND does reply still look like CC
    if pending_is_cc or is_cc_deal(text):
        log.info(f"[EXTRAPE] 💳 CC deal reply → CC WA group | image={'yes' if media_bytes else 'no'}")
        if is_quiet_hours():
            log.info(f"[WA-SINGLE] 🌙 Quiet hours ({ist_now.strftime('%H:%M')} IST) — skipping CC")
            stats["ignored"] += 1
        else:
            await send_to_whatsapp_single(text, CC_WA_GROUP, media_bytes)
            stats["cc_sent_via_extrape"] += 1
        return

    # ── Flipkart → FK WA group ──
    fk_links = extract_flipkart_links(text)
    if fk_links:
        log.info(f"[EXTRAPE] 🛒 FK converted → FK WA group | image={'yes' if media_bytes else 'no'}")
        if is_quiet_hours():
            log.info(f"[WA-SINGLE] 🌙 Quiet hours ({ist_now.strftime('%H:%M')} IST) — skipping FK")
            stats["ignored"] += 1
        else:
            await send_to_whatsapp_single(text, FK_WA_GROUP, media_bytes)
            stats["fk_sent_to_wa"] += 1
        return

    # ── Amazon → Dealspouch ──
    amz_links = extract_amazon_links(text)
    if amz_links:
        log.info(f"[EXTRAPE] ✅ AMZ converted → Dealspouch | image={'yes' if media_bytes else 'no'}")
        sent = await client.send_message(DEALSPOUCH_BOT, text)
        pending_media[sent.id] = media_bytes
        stats["amz_sent_to_dealspouch"] += 1
        return

    log.info(f"[EXTRAPE] ⏭️ No recognisable link in reply — ignored")
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
        log.info(f"[DEALSPOUCH] ⏭️ Ignored — no dealspouch link")
        return

    now = time.time()
    if now - last_dealspouch_handled < DEALSPOUCH_COOLDOWN:
        stats["ignored"] += 1
        log.info(f"[DEALSPOUCH] ⏭️ Duplicate ignored")
        return
    last_dealspouch_handled = now

    media_bytes = None
    if pending_media:
        oldest_key = next(iter(pending_media))
        media_bytes = pending_media.pop(oldest_key)

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