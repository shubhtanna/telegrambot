from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from http.server import HTTPServer, BaseHTTPRequestHandler
import asyncio, re, io, logging, time, aiohttp, os, threading

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ── CONFIG — Railway environment variables se aayega ──
# ── CONFIG — Railway environment variables ──
API_ID         = int(os.environ.get("API_ID"))
API_HASH       = os.environ.get("API_HASH")
STRING_SESSION = os.environ.get("STRING_SESSION")
BAILEYS_URL    = os.environ.get("BAILEYS_URL")
BAILEYS_SECRET = os.environ.get("BAILEYS_SECRET", "mysecret123")

SOURCE_GROUPS = [
    -1001493857075,
    -1001412868909,
    -1001389782464,
]

EXTRAPE_BOT    = "@ExtraPeBot"
DEALSPOUCH_BOT = "@dealspouch_server_bot"
MY_TG_GROUP    = "@finnindeals2"

# ── Health check server (Railway ke liye) ──
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

# ── Stats ──
stats = {
    "deals_found": 0,
    "sent_to_extrape": 0,
    "sent_to_dealspouch": 0,
    "posted_to_tg": 0,
    "sent_to_wa": 0,
    "ignored": 0,
}

pending_media = {}
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

last_extrape_handled = 0
last_dealspouch_handled = 0
EXTRAPE_COOLDOWN = 15
DEALSPOUCH_COOLDOWN = 15

def extract_amazon_links(text):
    if not text:
        return []
    return re.findall(
        r'https?://(?:www\.)?(?:amazon\.in|amzn\.in|amzn\.to|amazon\.com)[^\s]*',
        text
    )

def has_dealspouch_link(text):
    return text and "amaz.dealspouch.com" in text

async def download_media_bytes(message):
    try:
        if message.media and isinstance(message.media, (MessageMediaPhoto, MessageMediaDocument)):
            buf = io.BytesIO()
            await client.download_media(message, file=buf)
            return buf.getvalue()
    except Exception as e:
        log.warning(f"Media download failed: {e}")
    return None

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
                form.add_field("image", image_bytes, filename="deal.jpg", content_type="image/jpeg")
                async with session.post(
                    f"{BAILEYS_URL}/send",
                    data=form,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    body = await resp.text()
                    log.info(f"[WA] ✅ Queued! Response: {body[:80]}")
            else:
                async with session.post(
                    f"{BAILEYS_URL}/send",
                    json={"text": text, "secret": BAILEYS_SECRET},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    body = await resp.text()
                    log.info(f"[WA] ✅ Queued! Response: {body[:80]}")
        stats["sent_to_wa"] += 1
    except Exception as e:
        log.error(f"[WA] ❌ Failed: {e}")

# ── STEP 1: Source group → ExtraPe ──
@client.on(events.NewMessage(chats=SOURCE_GROUPS))
async def handle_source(event):
    text = event.message.text or event.message.caption or ""
    links = extract_amazon_links(text)
    if not links:
        return

    stats["deals_found"] += 1
    log.info(f"[SOURCE] 🎯 Deal #{stats['deals_found']} found! {len(links)} link(s)...")

    media_bytes = await download_media_bytes(event.message)
    temp_key = int(asyncio.get_event_loop().time() * 1000)
    pending_media[temp_key] = media_bytes

    sent = await client.send_message(EXTRAPE_BOT, text)
    pending_media[sent.id] = pending_media.pop(temp_key)
    stats["sent_to_extrape"] += 1

# ── STEP 2: ExtraPe → Dealspouch ──
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
    if pending_media:
        oldest_key = next(iter(pending_media))
        media_bytes = pending_media.pop(oldest_key)

    sent = await client.send_message(DEALSPOUCH_BOT, text)
    pending_media[sent.id] = media_bytes
    stats["sent_to_dealspouch"] += 1

# ── STEP 3: Dealspouch → TG + WhatsApp ──
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
    if pending_media:
        oldest_key = next(iter(pending_media))
        media_bytes = pending_media.pop(oldest_key)

    log.info(f"[DEALSPOUCH] ✅ Valid! Posting to TG + WhatsApp...")

    try:
        if media_bytes:
            await client.send_file(MY_TG_GROUP, media_bytes, caption=text)
        else:
            await client.send_message(MY_TG_GROUP, text)
        stats["posted_to_tg"] += 1
        log.info(f"[TG] ✅ Posted to {MY_TG_GROUP}")
    except Exception as e:
        log.error(f"[TG] ❌ Failed: {e}")

    await send_to_whatsapp(text, media_bytes)

# ── Main ──
async def run():
    while True:
        try:
            await client.start()
            me = await client.get_me()
            log.info(f"✅ Logged in as: {me.first_name} (@{me.username})")
            log.info(f"👂 Watching {len(SOURCE_GROUPS)} source group(s)")
            log.info(f"📲 WA Sender: {BAILEYS_URL or 'NOT SET'}")
            log.info("⏳ Waiting for deals...\n")
            await client.run_until_disconnected()
        except Exception as e:
            log.error(f"Disconnected: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

asyncio.run(run())