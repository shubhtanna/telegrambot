from telethon import TelegramClient, events
from telethon.sessions import StringSession
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import asyncio
import re

# ============================================================
# FILL IN YOUR DETAILS
# ============================================================
API_ID = 37485844                 # ← your api_id
API_HASH = "b59b9b90de1866874af520878519c5ed"              # ← your api_hash
STRING_SESSION = "1BVtsOGgBuxckDhS1glEpDBxOmdjmY202iRQLZkUNW20wN2jRWF3ykveglBVpoQWGpDIEEMXlXWZfQ0sjIMwyg2dpQ3Pzm4k-PT_OIBu8PqiutrnrRB5cW9D0ddV-m0PFjS__k4d3QKWSTvP68G4Bez2FU2lxAAA0zY8KudG_i0jizMlSGMGF3gEuZZ7LhdoSroUe4hdLt4U-9l57B0cSuN_8V9RfzPwztaWoQikLIhEMW9ZMT0_b8S322jCpHHvyACMK-JFCZlbw9iwSYyul_6a4wakVyk1jpbcFZP0vlLSquEXb0tv7INVfPRxMGuWtsaY99FiavSCujckJ5k5bgz0C40Vlzgg="        # ← your string session

SOURCE_GROUPS = [
    -1001493857075,     
    -1001412868909,
    -1001389782464
]

CONVERTER_BOT = "@ExtraPeBot"
DESTINATION_GROUP = "@dealspouch_server_bot"
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

# Telegram client
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
client._last_full_message = ""

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
        print(f"[+] Amazon message found in group: {event.chat_id}")
        print(f"    Message: {text[:60]}...")
        client._last_full_message = text
        for link in links:
            print(f"    Sending to converter bot: {link}")
            await client.send_message(CONVERTER_BOT, link)
            await asyncio.sleep(2)

@client.on(events.NewMessage(chats=CONVERTER_BOT))
async def handle_bot_response(event):
    text = event.message.text or ""
    affiliate_links = extract_amazon_links(text)
    if affiliate_links:
        full_msg = getattr(client, '_last_full_message', '')
        for link in affiliate_links:
            if full_msg:
                new_msg = re.sub(
                    r'https?://(?:www\.)?(?:amazon\.in|amzn\.in|amzn\.to|amazon\.com)[^\s]*',
                    link,
                    full_msg
                )
            else:
                new_msg = link

            # Step 1 - Send to Dealspouch
            print(f"[+] Forwarding to Dealspouch...")
            await client.send_message(DESTINATION_GROUP, new_msg)
            await asyncio.sleep(1)

            # Step 2 - Also send to your own group
            print(f"[+] Forwarding to @finnindeals2...")
            await client.send_message(MY_GROUP, new_msg)
            await asyncio.sleep(1)

        client._last_full_message = ""
    elif text:
        print(f"[Bot replied]: {text}")

async def run():
    while True:
        try:
            await client.start()
            print("✅ Bot started successfully!")
            print(f"👂 Listening on  : {len(SOURCE_GROUPS)} group(s)")
            for g in SOURCE_GROUPS:
                print(f"   → {g}")
            print(f"🤖 Converter Bot : {CONVERTER_BOT}")
            print(f"📤 Dealspouch    : {DESTINATION_GROUP}")
            print(f"📤 My Group      : {MY_GROUP}")
            print("\n⏳ Waiting for Amazon links...\n")
            await client.run_until_disconnected()
        except Exception as e:
            print(f"❌ Disconnected: {e}")
            print("🔄 Reconnecting in 5 seconds...")
            await asyncio.sleep(5)
            continue

asyncio.run(run())