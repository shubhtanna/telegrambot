from telethon import TelegramClient, events
from telethon.sessions import StringSession
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import asyncio
import re

# ============================================================
API_ID = 37485844                 # ← your api_id
API_HASH = "b59b9b90de1866874af520878519c5ed"              # ← your api_hash
STRING_SESSION = "1BVtsOHQBuwEUbaywqR9-zaVfBTGOK4UI19nM1TGuffHKJ3e19vbYcyJt_Rx5C3m7Frb_ZEd5EHJvYrSWW_C-AAKYOGEO9nL2uzdYkZDbXQtobn0yzplQ9GrbnmP_MPFF4oxYRexKLOnot7DIGDICXldpWfBDUjUEuo-R52E78fQzsJsl01Jz9U1x7nA2iLMNaqfJPOp-Qcb6DVqB_JNVVSWlHfLl9xk0i3VFjhkmUlyJiNLd3nt-yIaKwSHWnG6plScR5tQ8OfOL6bISUY7siMHMr38SjAL7i2gO46dtkw0eEO-2gea3SsAfDahEtw83LVBEzknYDA3wE2xwDXxE6YOYIRfQWcM="        # ← your string session

SOURCE_GROUPS = [
    -1001493857075,     
    -1001412868909,
    -1001389782464
]

EXTRAPE_BOT = "@ExtraPeBot"
DEALSPOUCH_BOT = "@dealspouch_server_bot"
MY_GROUP = "@finnindeals2"
# ============================================================

# Health check server
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running! Alive!")
    def log_message(self, format, *args):
        pass

def run_health_server():
    server = HTTPServer(("0.0.0.0", 8080), HealthCheck)
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

def extract_amazon_links(text):
    if not text:
        return []
    pattern = r'https?://(?:www\.)?(?:amazon\.in|amzn\.in|amzn\.to|amazon\.com)[^\s]*'
    return re.findall(pattern, text)

@client.on(events.NewMessage(chats=SOURCE_GROUPS))
async def handle_source_message(event):
    text = event.message.text or ""
    links = extract_amazon_links(text)
    if links:
        print(f"[+] Found {len(links)} link(s) in source group")
        print(f"    Sending whole message to ExtraPe...")
        # Send WHOLE message to ExtraPe at once
        await client.send_message(EXTRAPE_BOT, text)

@client.on(events.NewMessage(chats=EXTRAPE_BOT))
async def handle_extrape_response(event):
    text = event.message.text or ""
    links = extract_amazon_links(text)
    if links:
        print(f"[+] ExtraPe converted, sending whole message to Dealspouch...")
        # Send ExtraPe converted whole message to Dealspouch at once
        await client.send_message(DEALSPOUCH_BOT, text)

@client.on(events.NewMessage(chats=DEALSPOUCH_BOT))
async def handle_dealspouch_response(event):
    text = event.message.text or ""
    links = extract_amazon_links(text)
    if links:
        print(f"[+] Dealspouch converted, sending to {MY_GROUP}...")
        print(f"    {text[:80]}...")
        # Send Dealspouch converted whole message to your group ONCE
        await client.send_message(MY_GROUP, text)

async def run():
    while True:
        try:
            await client.start()
            print("✅ Bot started successfully!")
            print(f"👂 Source Groups  : {len(SOURCE_GROUPS)} group(s)")
            for g in SOURCE_GROUPS:
                print(f"   → {g}")
            print(f"🤖 ExtraPe Bot    : {EXTRAPE_BOT}")
            print(f"🤖 Dealspouch Bot : {DEALSPOUCH_BOT}")
            print(f"📤 My Group       : {MY_GROUP}")
            print("\n⏳ Waiting for Amazon links...\n")
            await client.run_until_disconnected()
        except Exception as e:
            print(f"❌ Disconnected: {e}")
            print("🔄 Reconnecting in 5 seconds...")
            await asyncio.sleep(5)
            continue

asyncio.run(run())