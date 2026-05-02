from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import asyncio, re, io, logging, time, aiohttp, os, threading, pytz

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ══════════════════════════════════════════
#  CONFIG — fill in your values here
# ══════════════════════════════════════════
API_ID         = int(os.environ.get("API_ID"))
API_HASH       = os.environ.get("API_HASH")
STRING_SESSION = os.environ.get("STRING_SESSION")
BAILEYS_URL    = os.environ.get("BAILEYS_URL")
BAILEYS_SECRET = os.environ.get("BAILEYS_SECRET", "mysecret123")

# ── Amazon bots ──
EXTRAPE_BOT    = "@ExtraPeBot"
DEALSPOUCH_BOT = "@dealspouch_server_bot"
MY_TG_GROUP    = "@finnindeals2"

# ── Flipkart bot ──
FLIPKART_BOT    = "@Flipkart_server_bot"      # ← your FK converter bot
FK_WA_GROUP     = "120363427339438586@g.us"   # ← single WA group for FK deals

# ── Source groups (same for both Amazon + Flipkart) ──
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
    quiet_start = 0 * 60 + 30   # 00:30 IST
    quiet_end   = 8 * 60 + 0    # 08:00 IST
    return quiet_start <= current_minutes < quiet_end

# ══════════════════════════════════════════
#  HEALTH CHECK SERVER
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
    # Amazon
    "amz_deals_found": 0,
    "sent_to_extrape": 0,
    "sent_to_dealspouch": 0,
    "posted_to_tg": 0,
    "sent_to_wa_bulk": 0,
    # Flipkart
    "fk_deals_found": 0,
    "sent_to_fkbot": 0,
    "sent_to_wa_single": 0,
    # Shared
    "ignored": 0,
}

# ══════════════════════════════════════════
#  SHARED STATE
# ══════════════════════════════════════════
amz_pending_media = {}   # Amazon pipeline media
fk_pending_media  = {}   # Flipkart pipeline media

client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

# Cooldowns
last_extrape_handled   = 0
last_dealspouch_handled = 0
last_fkbot_handled     = 0
EXTRAPE_COOLDOWN   = 15
DEALSPOUCH_COOLDOWN = 15
FKBOT_COOLDOWN     = 15

# ══════════════════════════════════════════
#  LINK EXTRACTORS
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

def has_dealspouch_link(text):
    return text and "amaz.dealspouch.com" in text

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

# Bulk — Amazon deals → all TARGETS in index.js
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
                    log.info(f"[WA-BULK] ✅ Queued! Response: {body[:80]}")
            else:
                async with session.post(
                    f"{BAILEYS_URL}/send",
                    json={"text": text, "secret": BAILEYS_SECRET},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    body = await resp.text()
                    log.info(f"[WA-BULK] ✅ Queued! Response: {body[:80]}")
        stats["sent_to_wa_bulk"] += 1
    except Exception as e:
        log.error(f"[WA-BULK] ❌ Failed: {e}")

# Single — Flipkart deals → one specific WA group
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
                    log.info(f"[WA-SINGLE] ✅ Sent! Response: {body[:80]}")
            else:
                async with session.post(
                    f"{BAILEYS_URL}/send-single",
                    json={"text": text, "secret": BAILEYS_SECRET, "target": FK_WA_GROUP},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    body = await resp.text()
                    log.info(f"[WA-SINGLE] ✅ Sent! Response: {body[:80]}")
        stats["sent_to_wa_single"] += 1
    except Exception as e:
        log.error(f"[WA-SINGLE] ❌ Failed: {e}")

# ══════════════════════════════════════════
#  AMAZON PIPELINE
# ══════════════════════════════════════════

# STEP A1: Source group → ExtraPe (Amazon only)
@client.on(events.NewMessage(chats=SOURCE_GROUPS))
async def handle_source_amazon(event):
    text = event.message.text or event.message.caption or ""
    links = extract_amazon_links(text)
    if not links:
        return

    stats["amz_deals_found"] += 1
    log.info(f"[AMZ-SOURCE] 🎯 Deal #{stats['amz_deals_found']} found! {len(links)} link(s)...")

    media_bytes = await download_media_bytes(event.message)
    temp_key = int(asyncio.get_event_loop().time() * 1000)
    amz_pending_media[temp_key] = media_bytes

    sent = await client.send_message(EXTRAPE_BOT, text)
    amz_pending_media[sent.id] = amz_pending_media.pop(temp_key)
    stats["sent_to_extrape"] += 1

# STEP A2: ExtraPe → Dealspouch
@client.on(events.NewMessage(chats=EXTRAPE_BOT))
async def handle_extrape(event):
    global last_extrape_handled
    text = event.message.text or ""
    if not text:
        return

    now = time.time()
    if now - last_extrape_handled < EXTRAPE_COOLDOWN:
        stats["ignored"] += 1
        log.info(f"[EXTRAPE] ⏭️ Duplicate ignored")
        return
    last_extrape_handled = now

    log.info(f"[EXTRAPE] ✅ Converted! Sending to Dealspouch...")

    media_bytes = None
    if amz_pending_media:
        oldest_key = next(iter(amz_pending_media))
        media_bytes = amz_pending_media.pop(oldest_key)

    sent = await client.send_message(DEALSPOUCH_BOT, text)
    amz_pending_media[sent.id] = media_bytes
    stats["sent_to_dealspouch"] += 1

# STEP A3: Dealspouch → TG + WhatsApp bulk
@client.on(events.NewMessage(chats=DEALSPOUCH_BOT))
async def handle_dealspouch(event):
    global last_dealspouch_handled
    text = event.message.text or ""

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
    if amz_pending_media:
        oldest_key = next(iter(amz_pending_media))
        media_bytes = amz_pending_media.pop(oldest_key)

    ist_now = get_ist_now()
    log.info(f"[DEALSPOUCH] ✅ Valid! IST: {ist_now.strftime('%H:%M')} | Quiet={is_quiet_hours()} | Posting to TG + WA...")

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

    # WhatsApp bulk — skip quiet hours
    if is_quiet_hours():
        log.info(f"[WA-BULK] 🌙 Quiet hours ({ist_now.strftime('%H:%M')} IST) — skipping")
    else:
        await send_to_whatsapp_bulk(text, media_bytes)

# ══════════════════════════════════════════
#  FLIPKART PIPELINE
# ══════════════════════════════════════════

# STEP F1: Source group → Flipkart Bot (FK links only)
@client.on(events.NewMessage(chats=SOURCE_GROUPS))
async def handle_source_flipkart(event):
    text = event.message.text or event.message.caption or ""
    links = extract_flipkart_links(text)
    if not links:
        return

    stats["fk_deals_found"] += 1
    log.info(f"[FK-SOURCE] 🛒 FK Deal #{stats['fk_deals_found']} found! {len(links)} link(s)...")

    media_bytes = await download_media_bytes(event.message)
    temp_key = int(asyncio.get_event_loop().time() * 1000) + 1  # +1 avoids key clash with Amazon
    fk_pending_media[temp_key] = media_bytes

    sent = await client.send_message(FLIPKART_BOT, text)
    fk_pending_media[sent.id] = fk_pending_media.pop(temp_key)
    stats["sent_to_fkbot"] += 1
    log.info(f"[FKBOT] 📤 Sent to {FLIPKART_BOT}")

# STEP F2: Flipkart Bot reply → WhatsApp single group
@client.on(events.NewMessage(chats=FLIPKART_BOT))
async def handle_fkbot_reply(event):
    global last_fkbot_handled
    text = event.message.text or ""
    if not text:
        return

    now = time.time()
    if now - last_fkbot_handled < FKBOT_COOLDOWN:
        stats["ignored"] += 1
        log.info(f"[FKBOT] ⏭️ Duplicate ignored (cooldown)")
        return
    last_fkbot_handled = now

    media_bytes = None
    if fk_pending_media:
        oldest_key = next(iter(fk_pending_media))
        media_bytes = fk_pending_media.pop(oldest_key)

    ist_now = get_ist_now()
    log.info(f"[FKBOT] ✅ Reply received | IST: {ist_now.strftime('%H:%M')} | Quiet={is_quiet_hours()}")

    if is_quiet_hours():
        log.info(f"[WA-SINGLE] 🌙 Quiet hours ({ist_now.strftime('%H:%M')} IST) — skipping")
        stats["ignored"] += 1
        return

    await send_to_whatsapp_single(text, media_bytes)

# ══════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════
async def run():
    while True:
        try:
            await client.start()
            me = await client.get_me()
            log.info(f"✅ Logged in as: {me.first_name} (@{me.username})")
            log.info(f"👂 Watching {len(SOURCE_GROUPS)} source group(s) — Amazon + Flipkart")
            log.info(f"🤖 ExtraPe Bot   : {EXTRAPE_BOT}")
            log.info(f"🤖 Dealspouch Bot: {DEALSPOUCH_BOT}")
            log.info(f"🤖 Flipkart Bot  : {FLIPKART_BOT}")
            log.info(f"📢 TG Group      : {MY_TG_GROUP}")
            log.info(f"📲 FK WA Group   : {FK_WA_GROUP}")
            log.info(f"📲 WA Sender     : {BAILEYS_URL or 'NOT SET'}")
            log.info("⏳ Waiting for deals...\n")
            await client.run_until_disconnected()
        except Exception as e:
            log.error(f"Disconnected: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

asyncio.run(run())