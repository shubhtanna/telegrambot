from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import asyncio, re, io, logging, time, aiohttp, os, threading, pytz

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ── CONFIG ──
API_ID         = int(os.environ.get("API_ID"))
API_HASH       = os.environ.get("API_HASH")
STRING_SESSION = os.environ.get("STRING_SESSION")
BAILEYS_URL    = os.environ.get("BAILEYS_URL")
BAILEYS_SECRET = os.environ.get("BAILEYS_SECRET", "mysecret123")

# ── ADD YOUR VALUES HERE ──
FLIPKART_BOT = "@Flipkart_server_bot"   # e.g. "@Flipkart_server_bot"

SOURCE_GROUPS = [
    -1001493857075,
    -1001412868909,
    -1001389782464,
    -1001480964161,
]

WA_TARGET_GROUP = "120363427339438586@g.us"  # Replace with your WhatsApp group JID

# ── IST Time Helpers ──
def get_ist_now():
    ist = pytz.timezone("Asia/Kolkata")
    return datetime.now(ist)

def is_quiet_hours():
    now = get_ist_now()
    current_minutes = now.hour * 60 + now.minute
    quiet_start = 0 * 60 + 30   # 00:30 IST
    quiet_end   = 8 * 60 + 0    # 08:00 IST
    return quiet_start <= current_minutes < quiet_end

# ── Health check server ──
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Flipkart Bot is running!")
    def log_message(self, *args):
        pass

threading.Thread(
    target=lambda: HTTPServer(("0.0.0.0", 8081), HealthCheck).serve_forever(),
    daemon=True
).start()

# ── Stats ──
stats = {
    "deals_found": 0,
    "sent_to_fkbot": 0,
    "sent_to_wa": 0,
    "ignored": 0,
}

pending_media = {}
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

last_fkbot_handled = 0
FKBOT_COOLDOWN = 15  # seconds

# ── Flipkart link extractor ──
def extract_flipkart_links(text):
    if not text:
        return []
    return re.findall(
        r'https?://(?:www\.)?(?:flipkart\.com|fkrt\.it|dl\.flipkart\.com)[^\s]*',
        text
    )

# ── Download media from message ──
async def download_media_bytes(message):
    try:
        if message.media and isinstance(message.media, (MessageMediaPhoto, MessageMediaDocument)):
            buf = io.BytesIO()
            await client.download_media(message, file=buf)
            return buf.getvalue()
    except Exception as e:
        log.warning(f"Media download failed: {e}")
    return None

# ── Send to ONE WhatsApp group ──
async def send_to_whatsapp(text, image_bytes=None):
    if not BAILEYS_URL:
        log.warning("[WA] BAILEYS_URL not set!")
        return
    try:
        async with aiohttp.ClientSession() as session:
            if image_bytes:
                form = aiohttp.FormData()
                form.add_field("text", text or "")
                form.add_field("secret", BAILEYS_SECRET)
                form.add_field("target", WA_TARGET_GROUP)
                form.add_field("image", image_bytes, filename="deal.jpg", content_type="image/jpeg")
                async with session.post(
                    f"{BAILEYS_URL}/send-single",
                    data=form,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    body = await resp.text()
                    log.info(f"[WA] ✅ Sent! Response: {body[:80]}")
            else:
                async with session.post(
                    f"{BAILEYS_URL}/send-single",
                    json={"text": text, "secret": BAILEYS_SECRET, "target": WA_TARGET_GROUP},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    body = await resp.text()
                    log.info(f"[WA] ✅ Sent! Response: {body[:80]}")
        stats["sent_to_wa"] += 1
    except Exception as e:
        log.error(f"[WA] ❌ Failed: {e}")

# ── STEP 1: Source group → Flipkart Bot ──
@client.on(events.NewMessage(chats=SOURCE_GROUPS))
async def handle_source(event):
    text = event.message.text or event.message.caption or ""
    links = extract_flipkart_links(text)
    if not links:
        return

    stats["deals_found"] += 1
    log.info(f"[SOURCE] 🛒 FK Deal #{stats['deals_found']} found! {len(links)} link(s)...")

    media_bytes = await download_media_bytes(event.message)
    temp_key = int(asyncio.get_event_loop().time() * 1000)
    pending_media[temp_key] = media_bytes

    sent = await client.send_message(FLIPKART_BOT, text)
    pending_media[sent.id] = pending_media.pop(temp_key)
    stats["sent_to_fkbot"] += 1
    log.info(f"[FKBOT] 📤 Sent to {FLIPKART_BOT}")

# ── STEP 2: Flipkart Bot reply → WhatsApp ──
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
    if pending_media:
        oldest_key = next(iter(pending_media))
        media_bytes = pending_media.pop(oldest_key)

    ist_now = get_ist_now()
    log.info(f"[FKBOT] ✅ Reply received | IST: {ist_now.strftime('%H:%M')} | Quiet={is_quiet_hours()}")

    if is_quiet_hours():
        log.info(f"[WA] 🌙 Quiet hours ({ist_now.strftime('%H:%M')} IST) — skipping WhatsApp")
        stats["ignored"] += 1
        return

    await send_to_whatsapp(text, media_bytes)

# ── Main ──
async def run():
    while True:
        try:
            await client.start()
            me = await client.get_me()
            log.info(f"✅ Logged in as: {me.first_name} (@{me.username})")
            log.info(f"👂 Watching {len(SOURCE_GROUPS)} FK source group(s)")
            log.info(f"🤖 FK Bot     : {FLIPKART_BOT}")
            log.info(f"📲 WA Group   : {WA_TARGET_GROUP}")
            log.info(f"📲 WA Sender  : {BAILEYS_URL or 'NOT SET'}")
            log.info("⏳ Waiting for Flipkart deals...\n")
            await client.run_until_disconnected()
        except Exception as e:
            log.error(f"Disconnected: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

asyncio.run(run())