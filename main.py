from telethon import TelegramClient, events
from telethon.sessions import StringSession
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import asyncio
import re

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

# ================= HEALTH SERVER =================
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

# ================= TELEGRAM CLIENT =================
client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

# ================= STORAGE =================
pending_messages = {}
# structure:
# {
#   original_msg_id: {
#       "text": "...",
#       "links": [...],
#       "converted_links": []
#   },
#   extrape_msg_id: original_msg_id
# }

# ================= UTIL =================
def extract_amazon_links(text):
    if not text:
        return []
    pattern = r'https?://(?:www\.)?(?:amazon\.in|amzn\.in|amzn\.to|amazon\.com)[^\s]*'
    return re.findall(pattern, text)

# ================= SOURCE HANDLER =================
@client.on(events.NewMessage(chats=SOURCE_GROUPS))
async def handle_source_message(event):
    text = event.message.text or ""
    links = extract_amazon_links(text)

    if not links:
        return

    print(f"\n[+] New message with {len(links)} link(s) from source")

    # store original message
    pending_messages[event.id] = {
        "text": text,
        "links": links,
        "converted_links": []
    }

    # send each link to ExtraPe bot
    for link in links:
        msg = await client.send_message(CONVERTER_BOT, link)
        pending_messages[msg.id] = event.id  # map reply → original
        await asyncio.sleep(2)

# ================= EXTRAPE HANDLER =================
@client.on(events.NewMessage(chats=CONVERTER_BOT))
async def handle_extrape_response(event):
    text = event.message.text or ""
    links = extract_amazon_links(text)

    if not links or not event.reply_to_msg_id:
        return

    original_id = pending_messages.get(event.reply_to_msg_id)

    if not original_id:
        return

    data = pending_messages.get(original_id)
    if not data:
        return

    converted_link = links[0]
    data["converted_links"].append(converted_link)

    print(f"[+] ExtraPe converted link received ({len(data['converted_links'])}/{len(data['links'])})")

    # when all links are converted
    if len(data["converted_links"]) == len(data["links"]):
        final_text = data["text"]

        # replace links one-by-one
        for old, new in zip(data["links"], data["converted_links"]):
            final_text = final_text.replace(old, new, 1)

        print("[+] Sending FINAL message to Dealspouch...")
        msg = await client.send_message(DESTINATION_GROUP, final_text)

        # map Dealspouch reply
        pending_messages[msg.id] = original_id

        # cleanup ExtraPe mappings
        for key in list(pending_messages.keys()):
            if pending_messages.get(key) == original_id and key != original_id:
                pending_messages.pop(key, None)

# ================= DEALSPOUCH HANDLER =================
@client.on(events.NewMessage(chats=DESTINATION_GROUP))
async def handle_dealspouch_response(event):
    text = event.message.text or ""
    links = extract_amazon_links(text)

    if not links or not event.reply_to_msg_id:
        return

    original_id = pending_messages.get(event.reply_to_msg_id)
    if not original_id:
        return

    print("[+] Final converted message received → forwarding to MY_GROUP")

    await client.send_message(MY_GROUP, text)
    await asyncio.sleep(1)

    # final cleanup
    pending_messages.pop(original_id, None)
    pending_messages.pop(event.reply_to_msg_id, None)

# ================= MAIN LOOP =================
async def run():
    while True:
        try:
            await client.start()

            print("✅ Bot started successfully!")
            print(f"👂 Listening on {len(SOURCE_GROUPS)} group(s)")
            print(f"🤖 ExtraPe Bot   : {CONVERTER_BOT}")
            print(f"🤖 Dealspouch    : {DESTINATION_GROUP}")
            print(f"📤 Final Group   : {MY_GROUP}")
            print("\n⏳ Waiting for messages...\n")

            await client.run_until_disconnected()

        except Exception as e:
            print(f"❌ Error: {e}")
            print("🔄 Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

asyncio.run(run())