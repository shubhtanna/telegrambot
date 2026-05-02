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
DEALSPOUCH_BOT = "@dealspouch_server_bot"
MY_TG_GROUP    = "@finnindeals2"

# FK deals → this ONE WA group only
FK_WA_GROUP = "120363427339438586@g.us"

SOURCE_GROUPS = [
    -1001493857075,
    -1001412868909,
    -1001389782464,
    -1001480964161,
]

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
# { sent_message_id: set_of_original_links }
sent_links_store = {}

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
    # Check against all recently sent link sets
    for original_links in sent_links_store.values():
        # If ANY link in reply matches original sent links — it's an echo
        if reply_links & original_links:
            log.info(f"[EXTRAPE] 🔄 Echo detected — same links as sent. Waiting for converted reply...")
            return True
    return False

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

async def send_to_whatsapp_single(text, image_bytes=None):
    if not BAILEYS_URL:
        log.warning("[WA-SINGLE] BAILEYS_URL not set!")
        return
    try:
        async with aiohttp.ClientSession() as session:
            if image_bytes:
                form = aiohttp.FormData()
                form.add_field("text", text or "")
                form.add_field("secret", BAILEYS_SECRET)
                form.add_field("target", FK_WA_GROUP)
                form.add_field("image", image_bytes, filename="deal.jpg", content_type="image/jpeg")
                async with session.post(
                    f"{BAILEYS_URL}/send-single", data=form,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    body = await resp.text()
                    log.info(f"[WA-SINGLE] ✅ Sent! {body[:80]}")
            else:
                async with session.post(
                    f"{BAILEYS_URL}/send-single",
                    json={"text": text, "secret": BAILEYS_SECRET, "target": FK_WA_GROUP},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    body = await resp.text()
                    log.info(f"[WA-SINGLE] ✅ Sent! {body[:80]}")
        stats["fk_sent_to_wa"] += 1
    except Exception as e:
        log.error(f"[WA-SINGLE] ❌ Failed: {e}")

# ══════════════════════════════════════════
#  STEP 1: Source groups → ExtraPe
# ══════════════════════════════════════════
@client.on(events.NewMessage(chats=SOURCE_GROUPS))
async def handle_source(event):
    text = event.message.text or event.message.caption or ""

    amz_links = extract_amazon_links(text)
    fk_links  = extract_flipkart_links(text)

    if not amz_links and not fk_links:
        return

    stats["deals_found"] += 1
    link_type = "Amazon" if amz_links else "Flipkart"
    log.info(f"[SOURCE] 🎯 {link_type} Deal #{stats['deals_found']} found!")

    media_bytes = await download_media_bytes(event.message)
    log.info(f"[SOURCE] 🖼️ Image: {'yes' if media_bytes else 'no'}")

    temp_key = int(asyncio.get_event_loop().time() * 1000)
    pending_media[temp_key] = media_bytes

    # Store original links so we can detect ExtraPe echoes
    original_links = extract_all_links(text)

    sent = await client.send_message(EXTRAPE_BOT, text)
    pending_media[sent.id] = pending_media.pop(temp_key)

    # Save original links keyed by sent message id
    sent_links_store[sent.id] = original_links

    # Keep sent_links_store small — max 20 entries
    if len(sent_links_store) > 20:
        oldest = next(iter(sent_links_store))
        del sent_links_store[oldest]

    stats["sent_to_extrape"] += 1
    log.info(f"[EXTRAPE] 📤 Sent to ExtraPe (tracking {len(original_links)} original link(s))")

# ══════════════════════════════════════════
#  STEP 2: ExtraPe reply → route by link type
#
#  ExtraPe sends 2 messages:
#    Message 1 — echo of original input  → SKIP (same links we sent)
#    Message 2 — converted links + image → USE THIS
# ══════════════════════════════════════════
@client.on(events.NewMessage(chats=EXTRAPE_BOT))
async def handle_extrape(event):
    text = event.message.text or event.message.caption or ""
    log.info(f"[EXTRAPE-DEBUG] out={event.message.out} | text={text[:80]}")
    global last_extrape_handled

    text = event.message.text or event.message.caption or ""
    if not text:
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

    # Clear sent_links_store since we got the converted reply
    sent_links_store.clear()

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

    # ── Flipkart → single WA group ──
    fk_links = extract_flipkart_links(text)
    if fk_links:
        log.info(f"[EXTRAPE] 🛒 FK converted → 1 WA group | image={'yes' if media_bytes else 'no'}")
        if is_quiet_hours():
            log.info(f"[WA-SINGLE] 🌙 Quiet hours ({ist_now.strftime('%H:%M')} IST) — skipping")
            stats["ignored"] += 1
        else:
            await send_to_whatsapp_single(text, media_bytes)
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
            log.info(f"🤖 ExtraPe Bot   : {EXTRAPE_BOT}  ← Amazon + Flipkart")
            log.info(f"🤖 Dealspouch Bot: {DEALSPOUCH_BOT}  ← Amazon only")
            log.info(f"📢 TG Group      : {MY_TG_GROUP}")
            log.info(f"📲 FK WA Group   : {FK_WA_GROUP}  ← Flipkart 1 group")
            log.info(f"📲 WA Sender     : {BAILEYS_URL or 'NOT SET'}")
            log.info("⏳ Waiting for deals...\n")
            await client.run_until_disconnected()
        except Exception as e:
            log.error(f"Disconnected: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

asyncio.run(run())