# from telethon import TelegramClient, events
# from telethon.sessions import StringSession
# from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
# from http.server import HTTPServer, BaseHTTPRequestHandler
# from datetime import datetime
# import asyncio, re, io, logging, time, aiohttp, os, threading, pytz, collections, random

# logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
# log = logging.getLogger(__name__)

# # ══════════════════════════════════════════
# #  CONFIG
# # ══════════════════════════════════════════
# API_ID         = int(os.environ.get("API_ID"))
# API_HASH       = os.environ.get("API_HASH")
# STRING_SESSION = os.environ.get("STRING_SESSION")
# BAILEYS_URL    = os.environ.get("BAILEYS_URL")
# BAILEYS_SECRET = os.environ.get("BAILEYS_SECRET", "mysecret123")

# EXTRAPE_BOT    = "@ExtraPeBot"
# EARNKARO_BOT   = "@ekconverter4bot"
# DEALSPOUCH_BOT = "@dealspouch_server_bot"
# MY_TG_GROUP    = "@finnindeals2"

# FK_WA_GROUP     = "120363427339438586@g.us"
# CC_WA_GROUP     = "120363426468421381@g.us"
# # ── ADD YOUR FASHION AND BEAUTY WA GROUP IDs BELOW ──
# FASHION_WA_GROUP = "120363427489881847@g.us"   # ← replace with real ID
# BEAUTY_WA_GROUP  = "120363425518003162@g.us"    # ← replace with real ID
# CC_DIRECT_GROUP  = -1001481951196


# SOURCE_GROUPS = [
#     -1001493857075,
#     -1001412868909,
#     -1001389782464,
#     CC_DIRECT_GROUP,
# ]

# # ══════════════════════════════════════════
# #  FRESHNESS CHECK
# # ══════════════════════════════════════════
# MAX_DEAL_AGE_MINUTES  = 10
# dealspouch_time_queue = collections.deque()

# # ── Separate queues for fashion and beauty Dealspouch pipelines ──
# fashion_dealspouch_time_queue  = collections.deque()
# beauty_dealspouch_time_queue   = collections.deque()

# # ══════════════════════════════════════════
# #  CC DEAL DETECTION
# # ══════════════════════════════════════════
# CC_SHORT_LINK_PATTERNS = re.compile(
#     r'https?://(?:'
#     r'extp\.in|'
#     r'clnk\.in|'
#     r'isl\.co|'
#     r'go\.onelink\.me|'
#     r'onelink\.me'
#     r')/\S+',
#     re.IGNORECASE
# )

# CC_STRONG_KEYWORDS = re.compile(
#     r'\b('
#     r'credit card|'
#     r'debit card|'
#     r'lifetime free(?: card)?|'
#     r'joining fee(?: waived)?|'
#     r'annual fee(?: waived| nil| zero)?|'
#     r'lounge access|'
#     r'airport lounge|'
#     r'fuel surcharge(?: waiver)?|'
#     r'milestone benefit|'
#     r'welcome bonus|'
#     r'welcome voucher|'
#     r'welcome gift|'
#     r'card apply|'
#     r'apply (?:for )?(?:the )?card|'
#     r'rupay (?:credit |platinum |select )?card|'
#     r'visa (?:credit |platinum |signature )?card|'
#     r'mastercard|'
#     r'credit score(?: check| free)?|'
#     r'popcoins|'
#     r'reward points(?: on card)?'
#     r')\b',
#     re.IGNORECASE
# )

# CC_WEAK_KEYWORDS = re.compile(
#     r'\b('
#     r'apply now|'
#     r'apply here|'
#     r'apply(?: in| online)?|'
#     r'cashback(?: card| offer)?|'
#     r'upi(?: payment| cashback| offer)?|'
#     r'zero fee|'
#     r'no fee|'
#     r'free card|'
#     r'card offer|'
#     r'card benefit|'
#     r'card perks?|'
#     r'card limit|'
#     r'eligib(?:le|ility)|'
#     r'instant approval|'
#     r'pre-?approved|'
#     r'card (?:launch|deal|offer)'
#     r')\b',
#     re.IGNORECASE
# )

# BANK_NAMES = re.compile(
#     r'\b('
#     r'hdfc(?: bank)?|'
#     r'sbi(?: card)?|'
#     r'icici(?: bank)?|'
#     r'axis(?: bank)?|'
#     r'kotak(?: bank| mahindra)?|'
#     r'yes bank|'
#     r'idfc(?: first)?|'
#     r'induslnd(?: bank)?|'
#     r'rbl(?: bank)?|'
#     r'au(?: small finance)?(?: bank)?|'
#     r'bob(?: financial)?|'
#     r'bank of baroda|'
#     r'pnb(?: bank)?|'
#     r'punjab national(?: bank)?|'
#     r'canara(?: bank)?|'
#     r'union bank|'
#     r'federal bank|'
#     r'south indian bank|'
#     r'karnataka bank|'
#     r'hsbc|'
#     r'citibank|'
#     r'standard chartered|'
#     r'american express|'
#     r'amex|'
#     r'bajaj finserv|'
#     r'one card|'
#     r'slice(?: card)?|'
#     r'uni card|'
#     r'fi (?:money|card)|'
#     r'niyo(?: card)?|'
#     r'jupiter(?: card)?|'
#     r'scapia|'
#     r'idbi(?: bank)?'
#     r')\b',
#     re.IGNORECASE
# )

# CC_FALSE_POSITIVE = re.compile(
#     r'(?:'
#     r'amazon\.in/(?:dp|gp)|'
#     r'amzn\.(?:in|to)|'
#     r'flipkart\.com/|'
#     r'fkrt\.\w+|'
#     r'(?:buy|order|shop)(?: now| here| at)?\s*[:\-]?\s*https?://|'
#     r'(?:loot|deal|offer)\s+at\s+₹|'
#     r'after\s+cashback\s+₹|'
#     r'collect\s+cashback\s*[:\-]?\s*https?://'
#     r')',
#     re.IGNORECASE
# )

# def is_cc_deal(text: str) -> bool:
#     if not text:
#         return False
#     if CC_FALSE_POSITIVE.search(text):
#         log.debug("[CC-DETECT] ❌ False-positive guard triggered — not a CC deal")
#         return False
#     if CC_STRONG_KEYWORDS.search(text):
#         log.debug("[CC-DETECT] ✅ Strong CC keyword matched")
#         return True
#     has_bank    = bool(BANK_NAMES.search(text))
#     has_weak    = bool(CC_WEAK_KEYWORDS.search(text))
#     has_cc_link = bool(CC_SHORT_LINK_PATTERNS.search(text))
#     if has_bank and has_weak:
#         log.debug("[CC-DETECT] ✅ Bank name + weak CC keyword matched")
#         return True
#     if has_cc_link and has_weak:
#         log.debug("[CC-DETECT] ✅ CC short link + weak CC keyword matched")
#         return True
#     return False

# def extract_cc_short_links(text):
#     if not text:
#         return []
#     return CC_SHORT_LINK_PATTERNS.findall(text)

# # ══════════════════════════════════════════
# #  FASHION DEAL DETECTION  ← NEW
# # ══════════════════════════════════════════
# FASHION_KEYWORDS = re.compile(
#     r'\b('
#     r'shirt|t-?shirt|shirts|'
#     r'jeans|denim|'
#     r'dress|dresses|'
#     r'kurta|kurti|kurtas|kurtis|'
#     r'sneakers?|'
#     r'footwear|'
#     r'ethnic(?: wear)?|'
#     r'saree|sari|sarees|'
#     r'lehenga|lehnga|lehengha|'
#     r'salwar|churidar|'
#     r'dupatta|'
#     r'palazzo|'
#     r'suit(?: set)?|'
#     r'anarkali|'
#     r'sherwani|'
#     r'trouser|trousers|'
#     r'chinos|'
#     r'shorts|'
#     r'jogger|joggers|'
#     r'track ?pant|'
#     r'sweatshirt|hoodie|'
#     r'jacket|jackets|'
#     r'blazer|'
#     r'coat|overcoat|'
#     r'sandals?|'
#     r'heels?|'
#     r'loafer|loafers|'
#     r'flip.?flop|'
#     r'sports? shoe|'
#     r'running shoe|'
#     r'formal shoe|'
#     r'casual shoe|'
#     r'handbag|hand ?bag|'
#     r'purse|clutch|'
#     r'tote bag|'
#     r'backpack|'
#     r'wallet|'
#     r'belt|belts|'
#     r'watch|watches|'
#     r'sunglasses|'
#     r'top|tops|'
#     r'skirt|skirts|'
#     r'leggings?|'
#     r'innerwear|underwear|lingerie|'
#     r'nightwear|night ?suit|'
#     r'swimwear|swim ?suit|'
#     r'athleisure|'
#     r'co-?ord(?: set)?|'
#     r'western wear|'
#     r'indo-?western|'
#     r'men(?:\'s)? fashion|'
#     r'women(?:\'s)? fashion|'
#     r'kids? fashion|'
#     r'apparel|garment|clothing|'
#     r'myntra|ajio|bewakoof|'
#     r'tata cliq fashion'
#     r')\b',
#     re.IGNORECASE
# )

# def is_fashion_deal(text: str):
#     match = bool(FASHION_KEYWORDS.search(text))
#     print("Fashion:", match, text[:100])
#     return match


# # ══════════════════════════════════════════
# #  BEAUTY DEAL DETECTION  ← NEW
# # ══════════════════════════════════════════
# BEAUTY_KEYWORDS = re.compile(
#     r'\b('
#     r'lipstick|lip ?gloss|lip ?liner|lip ?balm|'
#     r'foundation|concealer|'
#     r'mascara|eyeliner|eye ?shadow|'
#     r'blush|highlighter|contour|'
#     r'primer|setting spray|'
#     r'bb cream|cc cream|'
#     r'makeup|make-?up|cosmetics?|'
#     r'skincare|skin ?care|'
#     r'moisturis(?:er|ing)|moisturizer|'
#     r'serum|face serum|'
#     r'sunscreen|spf|'
#     r'face wash|face ?wash|cleanser|'
#     r'toner|face toner|'
#     r'face mask|sheet mask|'
#     r'exfoliat(?:or|ing)|scrub|'
#     r'eye cream|under.?eye|'
#     r'anti.?aging|anti.?ageing|'
#     r'night cream|day cream|'
#     r'body lotion|body ?butter|'
#     r'shampoo|conditioner|'
#     r'hair oil|hair serum|hair mask|'
#     r'hair color|hair colour|hair dye|'
#     r'hair treatment|'
#     r'dry shampoo|'
#     r'perfume|deo(?:dorant)?|cologne|'
#     r'body wash|shower gel|'
#     r'bath bomb|'
#     r'nail paint|nail polish|nail ?art|'
#     r'lip care|'
#     r'beard oil|beard grooming|'
#     r'face ?pack|'
#     r'vitamin c|hyaluronic|niacinamide|retinol|'
#     r'nykaa|purplle|smashbox|mac cosmetics|'
#     r'lakme|l\'oreal|loreal|maybelline|'
#     r'the ordinary|dot & key|plum|'
#     r'mamaearth|wow skin|forest essentials|'
#     r'biotique|himalaya|'
#     r'beauty|grooming'
#     r')\b',
#     re.IGNORECASE
# )

# def is_beauty_deal(text):
#     match = bool(BEAUTY_KEYWORDS.search(text))
#     print("Beauty:", match, text[:100])
#     return match

# # ══════════════════════════════════════════
# #  NON-AMAZON/FK LINK DETECTOR  ← NEW
# #  (Myntra, Ajio, Nykaa, generic, etc.)
# # ══════════════════════════════════════════
# def extract_non_amz_fk_links(text):
#     if not text:
#         return []
#     all_links = re.findall(r'https?://\S+', text)
#     result = []
#     for link in all_links:
#         is_amz = bool(re.search(r'amazon\.in|amzn\.in|amzn\.to|amazon\.com', link, re.I))
#         is_fk  = bool(re.search(r'flipkart\.com|fkrt\.\w+|dl\.flipkart\.com|bilty\.co', link, re.I))
#         if not is_amz and not is_fk:
#             result.append(link)
#     return result

# # ══════════════════════════════════════════
# #  IST TIME HELPERS
# # ══════════════════════════════════════════
# def get_ist_now():
#     ist = pytz.timezone("Asia/Kolkata")
#     return datetime.now(ist)

# def is_quiet_hours():
#     now = get_ist_now()
#     current_minutes = now.hour * 60 + now.minute
#     quiet_start = 1 * 60 + 0
#     quiet_end   = 8 * 60 + 0
#     return quiet_start <= current_minutes < quiet_end

# # ══════════════════════════════════════════
# #  HEALTH CHECK
# # ══════════════════════════════════════════
# class HealthCheck(BaseHTTPRequestHandler):
#     def do_GET(self):
#         self.send_response(200)
#         self.end_headers()
#         self.wfile.write(b"Bot is running!")
#     def log_message(self, *args):
#         pass

# threading.Thread(
#     target=lambda: HTTPServer(("0.0.0.0", 8080), HealthCheck).serve_forever(),
#     daemon=True
# ).start()

# # ══════════════════════════════════════════
# #  STATS
# # ══════════════════════════════════════════
# stats = {
#     "deals_found": 0,
#     "sent_to_extrape": 0,
#     "fk_sent_to_wa": 0,
#     "cc_sent_direct": 0,
#     "cc_sent_via_extrape": 0,
#     "amz_sent_to_dealspouch": 0,
#     "posted_to_tg": 0,
#     "sent_to_wa_bulk": 0,
#     "ignored": 0,
#     "rate_dropped": 0,
#     "stale_dropped": 0,
#     # ── NEW ──
#     "fashion_sent_to_extrape": 0,
#     "fashion_sent_direct_wa": 0,
#     "fashion_finnin_direct": 0,
#     "beauty_finnin_direct": 0,
#     "beauty_sent_to_extrape": 0,
#     "beauty_sent_direct_wa": 0,
# }

# # ══════════════════════════════════════════
# #  DAILY DEAL COUNTER (random 13 WA invite replacements)
# # ══════════════════════════════════════════
# _daily_counter_date = None
# _daily_deal_count   = 0
# _lucky_deal_slots   = set()

# WA_INVITE_LINK      = "https://tinyurl.com/fhknr97k"
# TG_BOT_FOOTER       = "\n\nTelegram Bot - t.me/Dealspouch_Product_bot"
# LUCKY_DEALS_PER_DAY = 13

# def _refresh_daily_counter():
#     global _daily_counter_date, _daily_deal_count, _lucky_deal_slots
#     today = get_ist_now().date()
#     if _daily_counter_date != today:
#         _daily_counter_date = today
#         _daily_deal_count   = 0
#         _lucky_deal_slots   = set(random.sample(range(1, 61), LUCKY_DEALS_PER_DAY))
#         log.info(f"[DAILY] 🗓️ New day {today} — lucky slots: {sorted(_lucky_deal_slots)}")

# def _is_lucky_deal() -> bool:
#     global _daily_deal_count
#     _refresh_daily_counter()
#     _daily_deal_count += 1
#     lucky = _daily_deal_count in _lucky_deal_slots
#     log.info(f"[DAILY] Deal #{_daily_deal_count} today | lucky={lucky}")
#     return lucky

# # ══════════════════════════════════════════
# #  SHARED STATE
# # ══════════════════════════════════════════
# pending_media          = {}
# sent_links_store       = {}
# sent_original_text     = {}
# dealspouch_media_queue = collections.deque()

# # ── NEW: separate media queues for fashion and beauty ──
# fashion_dealspouch_media_queue = collections.deque()
# beauty_dealspouch_media_queue  = collections.deque()

# client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

# last_dealspouch_handled     = 0
# DEALSPOUCH_COOLDOWN         = 15
# extrape_seen_hashes         = set()
# extrape_processed_reply_ids = set()
# source_seen_hashes          = set()

# # ══════════════════════════════════════════
# #  LINK DETECTORS
# # ══════════════════════════════════════════
# def extract_amazon_links(text):
#     if not text:
#         return []
#     return re.findall(
#         r'https?://(?:www\.)?(?:amazon\.in|amzn\.in|amzn\.to|amazon\.com)[^\s]*',
#         text
#     )

# def extract_flipkart_links_source(text):
#     if not text:
#         return []
#     return re.findall(
#         r'https?://(?:www\.)?(?:flipkart\.com|fkrt\.\w+|dl\.flipkart\.com)[^\s]*',
#         text
#     )

# def extract_flipkart_links(text):
#     if not text:
#         return []
#     return re.findall(
#         r'https?://(?:www\.)?(?:flipkart\.com|fkrt\.\w+|dl\.flipkart\.com|bilty\.co)[^\s]*',
#         text
#     )

# def extract_all_links(text):
#     if not text:
#         return set()
#     return set(re.findall(r'https?://\S+', text))

# def has_dealspouch_link(text):
#     return text and "amaz.dealspouch.com" in text

# def is_extrape_failure(text):
#     if not text:
#         return False
#     return "will not be able to convert" in text.lower()

# def is_echo_of_sent(text):
#     if not sent_links_store:
#         return False
#     reply_links = extract_all_links(text)
#     if not reply_links:
#         return False
#     for entry in sent_links_store.values():
#         if reply_links & entry["links"]:
#             log.info("[EXTRAPE] 🔄 Echo detected — same links as sent. Waiting for converted reply...")
#             return True
#     return False

# def _cleanup_store(msg_id):
#     pending_media.pop(msg_id, None)
#     sent_links_store.pop(msg_id, None)
#     sent_original_text.pop(msg_id, None)

# def _store_deal(sent_msg_id, media_bytes, original_links, is_cc, original_text, deal_type="generic"):
#     pending_media[sent_msg_id]      = media_bytes
#     sent_links_store[sent_msg_id]   = {"links": original_links, "is_cc": is_cc, "deal_type": deal_type}
#     sent_original_text[sent_msg_id] = original_text
#     if len(sent_links_store) > 20:
#         oldest = next(iter(sent_links_store))
#         _cleanup_store(oldest)

# # ══════════════════════════════════════════
# #  QUEUE PURGE HELPER
# # ══════════════════════════════════════════
# def _purge_stale_dealspouch_queue():
#     purged = 0
#     cutoff = time.time() - (MAX_DEAL_AGE_MINUTES * 60)
#     while dealspouch_time_queue and dealspouch_time_queue[0] < cutoff:
#         dealspouch_time_queue.popleft()
#         if dealspouch_media_queue:
#             dealspouch_media_queue.popleft()
#         purged += 1
#     if purged:
#         log.info(
#             f"[QUEUE-PURGE] 🧹 Evicted {purged} stale entry(ies) from Dealspouch queue | "
#             f"remaining={len(dealspouch_time_queue)}"
#         )

# def _purge_stale_fashion_queue():
#     """Purge stale entries from fashion Dealspouch queues."""
#     purged = 0
#     cutoff = time.time() - (MAX_DEAL_AGE_MINUTES * 60)
#     while fashion_dealspouch_time_queue and fashion_dealspouch_time_queue[0] < cutoff:
#         fashion_dealspouch_time_queue.popleft()
#         if fashion_dealspouch_media_queue:
#             fashion_dealspouch_media_queue.popleft()
#         purged += 1
#     if purged:
#         log.info(f"[QUEUE-PURGE] 🧹 Evicted {purged} stale entry(ies) from Fashion Dealspouch queue")

# def _purge_stale_beauty_queue():
#     """Purge stale entries from beauty Dealspouch queues."""
#     purged = 0
#     cutoff = time.time() - (MAX_DEAL_AGE_MINUTES * 60)
#     while beauty_dealspouch_time_queue and beauty_dealspouch_time_queue[0] < cutoff:
#         beauty_dealspouch_time_queue.popleft()
#         if beauty_dealspouch_media_queue:
#             beauty_dealspouch_media_queue.popleft()
#         purged += 1
#     if purged:
#         log.info(f"[QUEUE-PURGE] 🧹 Evicted {purged} stale entry(ies) from Beauty Dealspouch queue")

# # ══════════════════════════════════════════
# #  TEXT SANITIZER
# # ══════════════════════════════════════════
# _FAKE_URL_RE = re.compile(
#     r'https?://(?!'
#     r'(?:[a-z0-9\-]+\.)+[a-z]{2,}'
#     r')\S*',
#     re.IGNORECASE
# )

# def sanitize_text_for_bot(text: str) -> str:
#     if not text:
#         return text
#     cleaned = _FAKE_URL_RE.sub('', text).strip()
#     if cleaned != text:
#         log.info("[SANITIZE] Removed fake URL fragments from text")
#     return cleaned

# # ══════════════════════════════════════════
# #  MEDIA DOWNLOADER
# # ══════════════════════════════════════════
# async def download_media_bytes(message):
#     try:
#         if message.media and isinstance(message.media, (MessageMediaPhoto, MessageMediaDocument)):
#             buf = io.BytesIO()
#             await client.download_media(message, file=buf)
#             return buf.getvalue()
#     except Exception as e:
#         log.warning(f"Media download failed: {e}")
#     return None

# # ══════════════════════════════════════════
# #  WHATSAPP SENDERS
# # ══════════════════════════════════════════
# async def send_to_whatsapp_bulk(text, image_bytes=None):
#     if not BAILEYS_URL:
#         log.warning("[WA-BULK] BAILEYS_URL not set!")
#         return
#     try:
#         async with aiohttp.ClientSession() as session:
#             if image_bytes:
#                 form = aiohttp.FormData()
#                 form.add_field("text", text or "")
#                 form.add_field("secret", BAILEYS_SECRET)
#                 form.add_field("image", image_bytes, filename="deal.jpg", content_type="image/jpeg")
#                 async with session.post(
#                     f"{BAILEYS_URL}/send", data=form,
#                     timeout=aiohttp.ClientTimeout(total=30)
#                 ) as resp:
#                     body = await resp.text()
#                     if resp.status != 200:
#                         log.error(f"[WA-BULK] ❌ HTTP {resp.status} — WA sender may be down! {body[:120]}")
#                         return
#                     log.info(f"[WA-BULK] ✅ Queued! {body[:80]}")
#             else:
#                 async with session.post(
#                     f"{BAILEYS_URL}/send",
#                     json={"text": text, "secret": BAILEYS_SECRET},
#                     timeout=aiohttp.ClientTimeout(total=30)
#                 ) as resp:
#                     body = await resp.text()
#                     if resp.status != 200:
#                         log.error(f"[WA-BULK] ❌ HTTP {resp.status} — WA sender may be down! {body[:120]}")
#                         return
#                     log.info(f"[WA-BULK] ✅ Queued! {body[:80]}")
#         stats["sent_to_wa_bulk"] += 1
#     except Exception as e:
#         log.error(f"[WA-BULK] ❌ Failed: {e}")

# async def send_to_whatsapp_single(text, target_group, image_bytes=None):
#     if not BAILEYS_URL:
#         log.warning("[WA-SINGLE] BAILEYS_URL not set!")
#         return
#     try:
#         async with aiohttp.ClientSession() as session:
#             if image_bytes:
#                 form = aiohttp.FormData()
#                 form.add_field("text", text or "")
#                 form.add_field("secret", BAILEYS_SECRET)
#                 form.add_field("target", target_group)
#                 form.add_field("image", image_bytes, filename="deal.jpg", content_type="image/jpeg")
#                 async with session.post(
#                     f"{BAILEYS_URL}/send-single", data=form,
#                     timeout=aiohttp.ClientTimeout(total=30)
#                 ) as resp:
#                     body = await resp.text()
#                     if resp.status != 200:
#                         log.error(f"[WA-SINGLE] ❌ HTTP {resp.status} — WA sender may be down! {body[:120]}")
#                         return
#                     log.info(f"[WA-SINGLE] ✅ Sent to {target_group}! {body[:80]}")
#             else:
#                 async with session.post(
#                     f"{BAILEYS_URL}/send-single",
#                     json={"text": text, "secret": BAILEYS_SECRET, "target": target_group},
#                     timeout=aiohttp.ClientTimeout(total=30)
#                 ) as resp:
#                     body = await resp.text()
#                     if resp.status != 200:
#                         log.error(f"[WA-SINGLE] ❌ HTTP {resp.status} — WA sender may be down! {body[:120]}")
#                         return
#                     log.info(f"[WA-SINGLE] ✅ Sent to {target_group}! {body[:80]}")
#     except Exception as e:
#         log.error(f"[WA-SINGLE] ❌ Failed: {e}")

# # ══════════════════════════════════════════
# #  STEP 1: Source groups → Route by deal type
# # ══════════════════════════════════════════
# @client.on(events.NewMessage(chats=SOURCE_GROUPS))
# async def handle_source(event):
#     if event.message.edit_date:
#         return

#     text      = event.message.text or event.message.caption or ""
#     amz_links = extract_amazon_links(text)
#     fk_links  = extract_flipkart_links_source(text)
#     cc_deal   = is_cc_deal(text)
#     chat_id   = event.chat_id

#     # ══════════════════════════════════════
#     #  FINNIN DEALS GROUP → Fashion direct to WA  ← NEW
#     # ══════════════════════════════════════
#     if chat_id == -1001481951196:
#         if not is_fashion_deal(text):
#             return
#         log.info(f"[FINNIN] 👗 Fashion deal from Finnin TG group — sending direct to Fashion WA")
#         media_bytes = await download_media_bytes(event.message)
#         if is_quiet_hours():
#             log.info("[FINNIN] 🌙 Quiet hours — skipping")
#             stats["ignored"] += 1
#         else:
#             await send_to_whatsapp_single(text, FASHION_WA_GROUP, media_bytes)
#             stats["fashion_finnin_direct"] += 1
#             log.info("[FINNIN] ✅ Sent directly to Fashion WA group")
#         return

#     if chat_id == -1001481951196:
#         if not is_beauty_deal(text):
#             return
#         log.info(f"[FINNIN] 👗 Beauty deal from Finnin TG group — sending direct to Beauty WA")
#         media_bytes = await download_media_bytes(event.message)
#         if is_quiet_hours():
#             log.info("[FINNIN] 🌙 Quiet hours — skipping")
#             stats["ignored"] += 1
#         else:
#             await send_to_whatsapp_single(text, BEAUTY_WA_GROUP, media_bytes)
#             stats["beauty_finnin_direct"] += 1
#             log.info("[FINNIN] ✅ Sent directly to beauty WA group")
#         return

#     # ══════════════════════════════════════
#     #  FASHION SOURCE GROUP → ExtraPe  ← NEW
#     # ══════════════════════════════════════
#     if chat_id in SOURCE_GROUPS and is_fashion_deal(text):
#         log.info(f"[FASHION-SOURCE] 👗 Fashion deal found → ExtraPe")
#         media_bytes    = await download_media_bytes(event.message)
#         original_links = extract_all_links(text)
#         clean_text     = sanitize_text_for_bot(text)
#         sent = await client.send_message(EXTRAPE_BOT, clean_text)
#         _store_deal(sent.id, media_bytes, original_links, is_cc=False, original_text=clean_text, deal_type="fashion")
#         stats["fashion_sent_to_extrape"] += 1
#         log.info(f"[FASHION-SOURCE] 📤 Sent to ExtraPe (deal_type=fashion, msg_id={sent.id})")
#         return

#     # ══════════════════════════════════════
#     #  BEAUTY SOURCE GROUP → ExtraPe  ← NEW
#     # ══════════════════════════════════════
#     if chat_id in SOURCE_GROUPS and is_beauty_deal(text):
#         log.info(f"[BEAUTY-SOURCE] 💄 Beauty deal found → ExtraPe")
#         media_bytes    = await download_media_bytes(event.message)
#         original_links = extract_all_links(text)
#         clean_text     = sanitize_text_for_bot(text)
#         sent = await client.send_message(EXTRAPE_BOT, clean_text)
#         _store_deal(sent.id, media_bytes, original_links, is_cc=False, original_text=clean_text, deal_type="beauty")
#         stats["beauty_sent_to_extrape"] += 1
#         log.info(f"[BEAUTY-SOURCE] 📤 Sent to ExtraPe (deal_type=beauty, msg_id={sent.id})")
#         return

#     # ── Existing pipelines below (unchanged) ──

#     if not amz_links and not fk_links and not cc_deal:
#         return

#     stats["deals_found"] += 1

#     # ── CC DEAL — DIRECT GROUP ──
#     if cc_deal and chat_id == CC_DIRECT_GROUP:
#         log.info(f"[CC-DIRECT] 💳 CC Deal #{stats['deals_found']} from direct group!")
#         media_bytes = await download_media_bytes(event.message)
#         log.info(f"[CC-DIRECT] 🖼️ Image: {'yes' if media_bytes else 'no'}")
#         if is_quiet_hours():
#             log.info("[CC-DIRECT] 🌙 Quiet hours — skipping")
#             stats["ignored"] += 1
#         else:
#             await send_to_whatsapp_single(text, CC_WA_GROUP, media_bytes)
#             stats["cc_sent_direct"] += 1
#             log.info("[CC-DIRECT] ✅ Sent directly to CC WA group")
#         return

#     # ── Source-level dedup ──
#     all_links_in_msg = sorted(extract_all_links(text))
#     if all_links_in_msg:
#         dedup_key   = hash(tuple(all_links_in_msg))
#         dedup_label = f"links:{all_links_in_msg}"
#     else:
#         normalized  = re.sub(r'\s+', ' ', text.strip().lower())
#         dedup_key   = hash(normalized)
#         dedup_label = "normalized-text"

#     if dedup_key in source_seen_hashes:
#         log.info(f"[SOURCE] ⏭️ Duplicate ({dedup_label}) — already dispatched, skipping")
#         return
#     source_seen_hashes.add(dedup_key)
#     if len(source_seen_hashes) > 500:
#         source_seen_hashes.pop()

#     # ── CC DEAL — OTHER GROUPS → ExtraPe ──
#     if cc_deal and chat_id != CC_DIRECT_GROUP:
#         log.info(f"[CC-EXTRAPE] 💳 CC Deal #{stats['deals_found']} from group {chat_id} → ExtraPe")
#         media_bytes    = await download_media_bytes(event.message)
#         original_links = extract_all_links(text)
#         clean_text     = sanitize_text_for_bot(text)
#         sent = await client.send_message(EXTRAPE_BOT, clean_text)
#         _store_deal(sent.id, media_bytes, original_links, is_cc=True, original_text=clean_text, deal_type="generic")
#         stats["sent_to_extrape"] += 1
#         log.info(f"[CC-EXTRAPE] 📤 Sent to ExtraPe (CC=True, msg_id={sent.id})")
#         return

#     # ── AMAZON / FLIPKART → ExtraPe ──
#     link_type      = "Amazon" if amz_links else "Flipkart"
#     log.info(f"[SOURCE] 🎯 {link_type} Deal #{stats['deals_found']} found!")
#     media_bytes    = await download_media_bytes(event.message)
#     original_links = extract_all_links(text)
#     clean_text     = sanitize_text_for_bot(text)
#     sent = await client.send_message(EXTRAPE_BOT, clean_text)
#     _store_deal(sent.id, media_bytes, original_links, is_cc=False, original_text=clean_text, deal_type="generic")
#     stats["sent_to_extrape"] += 1
#     log.info(f"[EXTRAPE] 📤 Sent to ExtraPe (CC=False, msg_id={sent.id})")

# # ══════════════════════════════════════════
# #  STEP 2: ExtraPe reply → match by reply_to_msg_id
# # ══════════════════════════════════════════
# @client.on(events.NewMessage(chats=EXTRAPE_BOT))
# async def handle_extrape(event):
#     text = event.message.text or event.message.caption or ""
#     if not text:
#         return

#     replied_to_id = None
#     if event.message.reply_to and event.message.reply_to.reply_to_msg_id:
#         replied_to_id = event.message.reply_to.reply_to_msg_id
#         log.info(f"[EXTRAPE] 🔗 Reply to msg_id={replied_to_id}")

#     # ── ExtraPe failure → forward original to EarnKaro ──
#     if is_extrape_failure(text):
#         log.info("[EXTRAPE] ❌ Conversion failed — forwarding original to EarnKaro")
#         original_text = None
#         if replied_to_id and replied_to_id in sent_original_text:
#             original_text = sent_original_text.get(replied_to_id)
#             _cleanup_store(replied_to_id)
#         elif sent_original_text:
#             oldest_key    = next(iter(sent_original_text))
#             original_text = sent_original_text.get(oldest_key)
#             _cleanup_store(oldest_key)
#         if original_text:
#             await client.send_message(EARNKARO_BOT, original_text)
#             log.info("[EARNKARO] 📤 Forwarded original deal to EarnKaro")
#             stats["ignored"] += 1
#         else:
#             log.warning("[EARNKARO] ⚠️ No original text found to forward")
#         return

#     # ── Skip echo of our own input ──
#     if is_echo_of_sent(text):
#         return

#     # ── Skip already-processed reply_to_id ──
#     if replied_to_id and replied_to_id in extrape_processed_reply_ids:
#         log.info(f"[EXTRAPE] ⏭️ reply_to_id={replied_to_id} already processed — skipping duplicate")
#         stats["ignored"] += 1
#         return

#     # ── Dedup by content hash ──
#     msg_hash = hash(text.strip())
#     if msg_hash in extrape_seen_hashes:
#         stats["ignored"] += 1
#         log.info("[EXTRAPE] ⏭️ Exact duplicate content — ignored")
#         return
#     extrape_seen_hashes.add(msg_hash)
#     if len(extrape_seen_hashes) > 50:
#         extrape_seen_hashes.pop()

#     # ══════════════════════════════════════════
#     #  FETCH MEDIA + FLAGS
#     # ══════════════════════════════════════════
#     media_bytes   = None
#     pending_is_cc = False
#     deal_type     = "generic"   # ← NEW: default

#     if replied_to_id and replied_to_id in pending_media:
#         media_bytes   = pending_media.get(replied_to_id)
#         store_entry   = sent_links_store.get(replied_to_id, {})
#         pending_is_cc = store_entry.get("is_cc", False)
#         deal_type     = store_entry.get("deal_type", "generic")   # ← NEW
#         _cleanup_store(replied_to_id)
#         log.info(
#             f"[EXTRAPE] ✅ Matched reply_to_id={replied_to_id} | "
#             f"cc={pending_is_cc} | deal_type={deal_type} | image={'yes' if media_bytes else 'no'}"
#         )
#     else:
#         log.warning(
#             "[EXTRAPE] ⚠️ No reply_to match — will try ExtraPe's own image only"
#         )

#     if not media_bytes:
#         media_bytes = await download_media_bytes(event.message)
#         if media_bytes:
#             log.info("[EXTRAPE] 🖼️ Using ExtraPe reply's own image as fallback")
#         else:
#             log.info("[EXTRAPE] 🖼️ No image available — will send text only")

#     ist_now = get_ist_now()

#     if replied_to_id:
#         extrape_processed_reply_ids.add(replied_to_id)
#         if len(extrape_processed_reply_ids) > 100:
#             extrape_processed_reply_ids.pop()

#     # ══════════════════════════════════════════
#     #  FASHION PIPELINE  ← NEW
#     # ══════════════════════════════════════════
#     if deal_type == "fashion":
#         # if is_quiet_hours():
#         #     log.info(f"[FASHION] 🌙 Quiet hours — skipping fashion deal")
#         #     stats["ignored"] += 1
#         #     return

#         amz_links = extract_amazon_links(text)
#         media_bytes = media_bytes

#         if amz_links:

#             log.info(
#                 "[FASHION] Amazon → Dealspouch queue"
#             )

#             await client.send_message(
#                 DEALSPOUCH_BOT,
#                 text
#             )

#             fashion_dealspouch_media_queue.append(
#                 media_bytes
#             )

#             fashion_dealspouch_time_queue.append(
#                 time.time()
#             )

#         else:

#             log.info(
#                 "[FASHION] Non-AMZ → Fashion WA"
#             )

#             await send_to_whatsapp_single(
#                 text,
#                 FASHION_WA_GROUP,
#                 media_bytes
#             )

#         return

#         # amz_links = extract_amazon_links(text)
#         # fk_links  = extract_flipkart_links(text)
#         # other_links = extract_non_amz_fk_links(text)

#         # if amz_links:
#         #     # Amazon fashion → Dealspouch → Fashion WA group (via handle_dealspouch_fashion)
#         #     log.info(f"[FASHION] ✅ AMZ fashion → Dealspouch | image={'yes' if media_bytes else 'no'}")
#         #     _purge_stale_fashion_queue()
#         #     dealspouch_send_ts = time.time()
#         #     await client.send_message(DEALSPOUCH_BOT, text)
#         #     fashion_dealspouch_media_queue.append(media_bytes)
#         #     fashion_dealspouch_time_queue.append(dealspouch_send_ts)
#         #     if len(fashion_dealspouch_media_queue) > 20:
#         #         fashion_dealspouch_media_queue.popleft()
#         #         fashion_dealspouch_time_queue.popleft()
#         #     stats["fashion_sent_to_extrape"] += 1
#         #     log.info(f"[FASHION] 📤 Queued to Dealspouch | queue={len(fashion_dealspouch_media_queue)}")

#         # elif fk_links or other_links:
#         #     # Non-Amazon fashion (Flipkart, Myntra, Ajio, etc.) → direct to Fashion WA group
#         #     log.info(f"[FASHION] 🛒 Non-AMZ fashion → direct Fashion WA | image={'yes' if media_bytes else 'no'}")
#         #     await send_to_whatsapp_single(text, FASHION_WA_GROUP, media_bytes)
#         #     stats["fashion_sent_direct_wa"] += 1
#         # else:
#         #     log.info("[FASHION] ⏭️ No recognisable link in fashion reply — ignored")
#         #     stats["ignored"] += 1
#         # return

#     # ══════════════════════════════════════════
#     #  BEAUTY PIPELINE  ← NEW
#     # ══════════════════════════════════════════
#     if deal_type == "beauty":
#         # if is_quiet_hours():
#         #     log.info(f"[BEAUTY] 🌙 Quiet hours — skipping beauty deal")
#         #     stats["ignored"] += 1
#         #     return

#         amz_links = extract_amazon_links(text)

#         if amz_links:

#             await client.send_message(
#                 DEALSPOUCH_BOT,
#                 text
#             )

#             beauty_dealspouch_media_queue.append(
#                 media_bytes
#             )

#             beauty_dealspouch_time_queue.append(
#                 time.time()
#             )

#         else:

#             await send_to_whatsapp_single(
#                 text,
#                 BEAUTY_WA_GROUP,
#                 media_bytes
#             )

#         return

#         # amz_links   = extract_amazon_links(text)
#         # fk_links    = extract_flipkart_links(text)
#         # other_links = extract_non_amz_fk_links(text)

#         # if amz_links:
#         #     # Amazon beauty → Dealspouch → Beauty WA group
#         #     log.info(f"[BEAUTY] ✅ AMZ beauty → Dealspouch | image={'yes' if media_bytes else 'no'}")
#         #     _purge_stale_beauty_queue()
#         #     dealspouch_send_ts = time.time()
#         #     await client.send_message(DEALSPOUCH_BOT, text)
#         #     beauty_dealspouch_media_queue.append(media_bytes)
#         #     beauty_dealspouch_time_queue.append(dealspouch_send_ts)
#         #     if len(beauty_dealspouch_media_queue) > 20:
#         #         beauty_dealspouch_media_queue.popleft()
#         #         beauty_dealspouch_time_queue.popleft()
#         #     stats["beauty_sent_to_extrape"] += 1
#         #     log.info(f"[BEAUTY] 📤 Queued to Dealspouch | queue={len(beauty_dealspouch_media_queue)}")

#         # elif fk_links or other_links:
#         #     # Non-Amazon beauty → direct to Beauty WA group
#         #     log.info(f"[BEAUTY] 💄 Non-AMZ beauty → direct Beauty WA | image={'yes' if media_bytes else 'no'}")
#         #     await send_to_whatsapp_single(text, BEAUTY_WA_GROUP, media_bytes)
#         #     stats["beauty_sent_direct_wa"] += 1
#         # else:
#         #     log.info("[BEAUTY] ⏭️ No recognisable link in beauty reply — ignored")
#         #     stats["ignored"] += 1
#         # return

#     # ── CC deal → CC WA group ──
#     if pending_is_cc or is_cc_deal(text):
#         log.info(f"[EXTRAPE] 💳 CC deal → CC WA group | image={'yes' if media_bytes else 'no'}")
#         if is_quiet_hours():
#             log.info(f"[WA-SINGLE] 🌙 Quiet hours ({ist_now.strftime('%H:%M')} IST) — skipping CC")
#             stats["ignored"] += 1
#         else:
#             await send_to_whatsapp_single(text, CC_WA_GROUP, media_bytes)
#             stats["cc_sent_via_extrape"] += 1
#         return

#     # ── Flipkart → FK WA group ──
#     if extract_flipkart_links(text):
#         log.info(f"[EXTRAPE] 🛒 FK converted → FK WA group | image={'yes' if media_bytes else 'no'}")
#         if is_quiet_hours():
#             log.info(f"[WA-SINGLE] 🌙 Quiet hours ({ist_now.strftime('%H:%M')} IST) — skipping FK")
#             stats["ignored"] += 1
#         else:
#             await send_to_whatsapp_single(text, FK_WA_GROUP, media_bytes)
#             stats["fk_sent_to_wa"] += 1
#         return

#     # ── Amazon → Dealspouch ──
#     if extract_amazon_links(text):
#         log.info(f"[EXTRAPE] ✅ AMZ converted → Dealspouch | image={'yes' if media_bytes else 'no'}")
#         _purge_stale_dealspouch_queue()
#         dealspouch_send_ts = time.time()
#         await client.send_message(DEALSPOUCH_BOT, text)
#         dealspouch_media_queue.append(media_bytes)
#         dealspouch_time_queue.append(dealspouch_send_ts)
#         if len(dealspouch_media_queue) > 20:
#             dealspouch_media_queue.popleft()
#             dealspouch_time_queue.popleft()
#         log.info(
#             f"[DEALSPOUCH-QUEUE] 📥 Pushed image={'yes' if media_bytes else 'no'} | "
#             f"ts=now (age clock starts here) | "
#             f"queue size: {len(dealspouch_media_queue)}"
#         )
#         stats["amz_sent_to_dealspouch"] += 1
#         return

#     log.info("[EXTRAPE] ⏭️ No recognisable link in reply — ignored")
#     stats["ignored"] += 1

# # ══════════════════════════════════════════
# #  STEP 3a: Dealspouch → TG + WA bulk  (Amazon generic)
# # ══════════════════════════════════════════
# @client.on(events.NewMessage(chats=DEALSPOUCH_BOT))
# async def handle_dealspouch(event):
#     global last_dealspouch_handled
#     text = event.message.text or event.message.caption or ""

#     if not has_dealspouch_link(text):
#         stats["ignored"] += 1
#         log.info("[DEALSPOUCH] ⏭️ Ignored — no dealspouch link")
#         return

#     now = time.time()
#     if now - last_dealspouch_handled < DEALSPOUCH_COOLDOWN:
#         # ── Check if this is a fashion or beauty reply first before discarding ──
#         # Try fashion queue
#         if fashion_dealspouch_time_queue:
#             log.info("[DEALSPOUCH] ↪️ Cooldown active but fashion queue has entries — routing to fashion handler")
#             await _route_dealspouch_fashion(text)
#             return
#         # Try beauty queue
#         if beauty_dealspouch_time_queue:
#             log.info("[DEALSPOUCH] ↪️ Cooldown active but beauty queue has entries — routing to beauty handler")
#             await _route_dealspouch_beauty(text)
#             return
#         stats["ignored"] += 1
#         log.info("[DEALSPOUCH] ⏭️ Duplicate ignored")
#         return
#     last_dealspouch_handled = now

#     # # ── Check if this reply belongs to fashion or beauty queue first ──
#     # if fashion_dealspouch_time_queue and not dealspouch_time_queue:
#     #     await _route_dealspouch_fashion(text)
#     #     return
#     # if beauty_dealspouch_time_queue and not dealspouch_time_queue:
#     #     await _route_dealspouch_beauty(text)
#     #     return

#     if fashion_dealspouch_time_queue:

#         await _route_dealspouch_fashion(
#             text
#         )

#         return


#     if beauty_dealspouch_time_queue:

#         await _route_dealspouch_beauty(
#             text
#         )

#         return

#     # ── Generic Amazon pipeline ──
#     media_bytes = None
#     if dealspouch_media_queue:
#         media_bytes = dealspouch_media_queue.popleft()
#         log.info(
#             f"[DEALSPOUCH] ✅ Popped from queue | "
#             f"image={'yes' if media_bytes else 'no'} | "
#             f"remaining={len(dealspouch_media_queue)}"
#         )
#     else:
#         # No generic queue entry — try fashion / beauty as fallback
#         if fashion_dealspouch_time_queue:
#             await _route_dealspouch_fashion(text)
#             return
#         if beauty_dealspouch_time_queue:
#             await _route_dealspouch_beauty(text)
#             return
#         log.warning("[DEALSPOUCH] ⚠️ Media queue empty — sending text only")

#     source_ts = None
#     if dealspouch_time_queue:
#         source_ts = dealspouch_time_queue.popleft()
#         age_minutes = (time.time() - source_ts) / 60
#         log.info(
#             f"[FRESHNESS] 🕐 Deal age since Dealspouch send: {age_minutes:.1f} min "
#             f"(max allowed: {MAX_DEAL_AGE_MINUTES} min)"
#         )
#         if age_minutes > MAX_DEAL_AGE_MINUTES:
#             log.info(
#                 f"[FRESHNESS] 🗑️ Dealspouch took {age_minutes:.1f} min to reply — "
#                 f"exceeds {MAX_DEAL_AGE_MINUTES} min limit → DROPPED"
#             )
#             stats["stale_dropped"] += 1
#             return
#     else:
#         log.warning("[FRESHNESS] ⚠️ Time queue empty — skipping freshness check")

#     ist_now = get_ist_now()
#     log.info(f"[DEALSPOUCH] ✅ Fresh deal! IST: {ist_now.strftime('%H:%M')} | image={'yes' if media_bytes else 'no'}")

#     if _is_lucky_deal():
#         text = re.sub(r'https?://amaz\.dealspouch\.com/\S+', WA_INVITE_LINK, text)
#         log.info("[DAILY] 🎯 Lucky deal — replaced dealspouch link with WA invite")

#     text = text + TG_BOT_FOOTER

#     try:
#         if media_bytes:
#             await client.send_file(MY_TG_GROUP, media_bytes, caption=text)
#         else:
#             await client.send_message(MY_TG_GROUP, text)
#         stats["posted_to_tg"] += 1
#         log.info(f"[TG] ✅ Posted to {MY_TG_GROUP}")
#     except Exception as e:
#         log.error(f"[TG] ❌ Failed: {e}")

#     if is_quiet_hours():
#         log.info(f"[WA-BULK] 🌙 Quiet hours ({ist_now.strftime('%H:%M')} IST) — skipping")
#     else:
#         await send_to_whatsapp_bulk(text, media_bytes)

# # ══════════════════════════════════════════
# #  STEP 3b: Dealspouch reply → Fashion WA  ← NEW
# # ══════════════════════════════════════════
# async def _route_dealspouch_fashion(text: str):
#     """Handle a Dealspouch reply that belongs to the fashion pipeline."""
#     media_bytes = None
#     if fashion_dealspouch_media_queue:
#         media_bytes = fashion_dealspouch_media_queue.popleft()
#         log.info(
#             f"[FASHION-DEALSPOUCH] ✅ Popped from fashion queue | "
#             f"image={'yes' if media_bytes else 'no'} | "
#             f"remaining={len(fashion_dealspouch_media_queue)}"
#         )
#     else:
#         log.warning("[FASHION-DEALSPOUCH] ⚠️ Fashion media queue empty — text only")

#     if fashion_dealspouch_time_queue:
#         source_ts   = fashion_dealspouch_time_queue.popleft()
#         age_minutes = (time.time() - source_ts) / 60
#         log.info(f"[FASHION-FRESHNESS] 🕐 Age: {age_minutes:.1f} min (max {MAX_DEAL_AGE_MINUTES})")
#         if age_minutes > MAX_DEAL_AGE_MINUTES:
#             log.info(f"[FASHION-FRESHNESS] 🗑️ Stale ({age_minutes:.1f} min) → DROPPED")
#             stats["stale_dropped"] += 1
#             return
#     else:
#         log.warning("[FASHION-FRESHNESS] ⚠️ Time queue empty — skipping freshness check")

#     if is_quiet_hours():
#         log.info("[FASHION-DEALSPOUCH] 🌙 Quiet hours — skipping")
#         stats["ignored"] += 1
#         return

#     log.info(f"[FASHION-DEALSPOUCH] ✅ Sending to Fashion WA | image={'yes' if media_bytes else 'no'}")
#     await send_to_whatsapp_single(text, FASHION_WA_GROUP, media_bytes)
#     stats["fashion_sent_direct_wa"] += 1

# # ══════════════════════════════════════════
# #  STEP 3c: Dealspouch reply → Beauty WA  ← NEW
# # ══════════════════════════════════════════
# async def _route_dealspouch_beauty(text: str):
#     """Handle a Dealspouch reply that belongs to the beauty pipeline."""
#     media_bytes = None
#     if beauty_dealspouch_media_queue:
#         media_bytes = beauty_dealspouch_media_queue.popleft()
#         log.info(
#             f"[BEAUTY-DEALSPOUCH] ✅ Popped from beauty queue | "
#             f"image={'yes' if media_bytes else 'no'} | "
#             f"remaining={len(beauty_dealspouch_media_queue)}"
#         )
#     else:
#         log.warning("[BEAUTY-DEALSPOUCH] ⚠️ Beauty media queue empty — text only")

#     if beauty_dealspouch_time_queue:
#         source_ts   = beauty_dealspouch_time_queue.popleft()
#         age_minutes = (time.time() - source_ts) / 60
#         log.info(f"[BEAUTY-FRESHNESS] 🕐 Age: {age_minutes:.1f} min (max {MAX_DEAL_AGE_MINUTES})")
#         if age_minutes > MAX_DEAL_AGE_MINUTES:
#             log.info(f"[BEAUTY-FRESHNESS] 🗑️ Stale ({age_minutes:.1f} min) → DROPPED")
#             stats["stale_dropped"] += 1
#             return
#     else:
#         log.warning("[BEAUTY-FRESHNESS] ⚠️ Time queue empty — skipping freshness check")

#     if is_quiet_hours():
#         log.info("[BEAUTY-DEALSPOUCH] 🌙 Quiet hours — skipping")
#         stats["ignored"] += 1
#         return

#     log.info(f"[BEAUTY-DEALSPOUCH] ✅ Sending to Beauty WA | image={'yes' if media_bytes else 'no'}")
#     await send_to_whatsapp_single(text, BEAUTY_WA_GROUP, media_bytes)
#     stats["beauty_sent_direct_wa"] += 1

# # ══════════════════════════════════════════
# #  MAIN
# # ══════════════════════════════════════════
# async def run():
#     while True:
#         try:
#             await client.start()
#             me = await client.get_me()
#             log.info(f"✅ Logged in as: {me.first_name} (@{me.username})")
#             log.info(f"👂 Watching {len(SOURCE_GROUPS)} source group(s)")
#             log.info(f"💳 CC Direct Group    : {CC_DIRECT_GROUP}  ← no bot, rate-limit exempt")
#             log.info(f"🤖 ExtraPe Bot         : {EXTRAPE_BOT}  ← Amazon + Flipkart + CC + Fashion + Beauty")
#             log.info(f"🤖 EarnKaro Bot        : {EARNKARO_BOT}  ← fallback when ExtraPe fails")
#             log.info(f"🤖 Dealspouch Bot      : {DEALSPOUCH_BOT}  ← Amazon (generic + fashion + beauty)")
#             log.info(f"📢 TG Group            : {MY_TG_GROUP}")
#             log.info(f"📲 FK WA Group         : {FK_WA_GROUP}")
#             log.info(f"📲 CC WA Group         : {CC_WA_GROUP}")
#             log.info(f"📲 Fashion WA Group    : {FASHION_WA_GROUP}")
#             log.info(f"📲 Beauty WA Group     : {BEAUTY_WA_GROUP}")
#             log.info(f"📲 WA Sender           : {BAILEYS_URL or 'NOT SET'}")
#             log.info(f"⏱️  Freshness limit     : drop if Dealspouch takes > {MAX_DEAL_AGE_MINUTES} min to reply")
#             log.info(f"🎯 Lucky deals/day     : {LUCKY_DEALS_PER_DAY} (WA invite replaces dealspouch link)")
#             log.info(f"📌 TG Bot Footer       : {TG_BOT_FOOTER.strip()}")
#             log.info("⏳ Waiting for deals...\n")
#             await client.run_until_disconnected()
#         except Exception as e:
#             log.error(f"Disconnected: {e}. Reconnecting in 5s...")
#             await asyncio.sleep(5)

# asyncio.run(run())

# from telethon import TelegramClient, events
# from telethon.sessions import StringSession
# from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
# from http.server import HTTPServer, BaseHTTPRequestHandler
# from datetime import datetime
# import asyncio, re, io, logging, time, aiohttp, os, threading, pytz, collections, random

# logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
# log = logging.getLogger(__name__)

# # ══════════════════════════════════════════
# #  CONFIG
# # ══════════════════════════════════════════
# API_ID         = int(os.environ.get("API_ID"))
# API_HASH       = os.environ.get("API_HASH")
# STRING_SESSION = os.environ.get("STRING_SESSION")
# BAILEYS_URL    = os.environ.get("BAILEYS_URL")
# BAILEYS_SECRET = os.environ.get("BAILEYS_SECRET", "mysecret123")

# EXTRAPE_BOT    = "@ExtraPeBot"
# EARNKARO_BOT   = "@ekconverter4bot"
# DEALSPOUCH_BOT = "@dealspouch_server_bot"
# MY_TG_GROUP    = "@finnindeals2"

# FK_WA_GROUP     = "120363427339438586@g.us"
# CC_WA_GROUP     = "120363426468421381@g.us"
# # ── ADD YOUR FASHION AND BEAUTY WA GROUP IDs BELOW ──
# FASHION_WA_GROUP = "120363427489881847@g.us"   # ← replace with real ID
# BEAUTY_WA_GROUP  = "120363425518003162@g.us"    # ← replace with real ID
# CC_DIRECT_GROUP  = -1001481951196


# SOURCE_GROUPS = [
#     -1001493857075,
#     -1001412868909,
#     -1001389782464,
#     CC_DIRECT_GROUP,
# ]

# # ══════════════════════════════════════════
# #  FRESHNESS CHECK
# # ══════════════════════════════════════════
# MAX_DEAL_AGE_MINUTES  = 10
# dealspouch_time_queue = collections.deque()

# # ── Separate queues for fashion and beauty Dealspouch pipelines ──
# fashion_dealspouch_time_queue  = collections.deque()
# beauty_dealspouch_time_queue   = collections.deque()

# # ══════════════════════════════════════════
# #  CC DEAL DETECTION
# # ══════════════════════════════════════════
# CC_SHORT_LINK_PATTERNS = re.compile(
#     r'https?://(?:'
#     r'extp\.in|'
#     r'clnk\.in|'
#     r'isl\.co|'
#     r'go\.onelink\.me|'
#     r'onelink\.me'
#     r')/\S+',
#     re.IGNORECASE
# )

# CC_STRONG_KEYWORDS = re.compile(
#     r'\b('
#     r'credit card|'
#     r'debit card|'
#     r'lifetime free(?: card)?|'
#     r'joining fee(?: waived)?|'
#     r'annual fee(?: waived| nil| zero)?|'
#     r'lounge access|'
#     r'airport lounge|'
#     r'fuel surcharge(?: waiver)?|'
#     r'milestone benefit|'
#     r'welcome bonus|'
#     r'welcome voucher|'
#     r'welcome gift|'
#     r'card apply|'
#     r'apply (?:for )?(?:the )?card|'
#     r'rupay (?:credit |platinum |select )?card|'
#     r'visa (?:credit |platinum |signature )?card|'
#     r'mastercard|'
#     r'credit score(?: check| free)?|'
#     r'popcoins|'
#     r'reward points(?: on card)?'
#     r')\b',
#     re.IGNORECASE
# )

# CC_WEAK_KEYWORDS = re.compile(
#     r'\b('
#     r'apply now|'
#     r'apply here|'
#     r'apply(?: in| online)?|'
#     r'cashback(?: card| offer)?|'
#     r'upi(?: payment| cashback| offer)?|'
#     r'zero fee|'
#     r'no fee|'
#     r'free card|'
#     r'card offer|'
#     r'card benefit|'
#     r'card perks?|'
#     r'card limit|'
#     r'eligib(?:le|ility)|'
#     r'instant approval|'
#     r'pre-?approved|'
#     r'card (?:launch|deal|offer)'
#     r')\b',
#     re.IGNORECASE
# )

# BANK_NAMES = re.compile(
#     r'\b('
#     r'hdfc(?: bank)?|'
#     r'sbi(?: card)?|'
#     r'icici(?: bank)?|'
#     r'axis(?: bank)?|'
#     r'kotak(?: bank| mahindra)?|'
#     r'yes bank|'
#     r'idfc(?: first)?|'
#     r'induslnd(?: bank)?|'
#     r'rbl(?: bank)?|'
#     r'au(?: small finance)?(?: bank)?|'
#     r'bob(?: financial)?|'
#     r'bank of baroda|'
#     r'pnb(?: bank)?|'
#     r'punjab national(?: bank)?|'
#     r'canara(?: bank)?|'
#     r'union bank|'
#     r'federal bank|'
#     r'south indian bank|'
#     r'karnataka bank|'
#     r'hsbc|'
#     r'citibank|'
#     r'standard chartered|'
#     r'american express|'
#     r'amex|'
#     r'bajaj finserv|'
#     r'one card|'
#     r'slice(?: card)?|'
#     r'uni card|'
#     r'fi (?:money|card)|'
#     r'niyo(?: card)?|'
#     r'jupiter(?: card)?|'
#     r'scapia|'
#     r'idbi(?: bank)?'
#     r')\b',
#     re.IGNORECASE
# )

# CC_FALSE_POSITIVE = re.compile(
#     r'(?:'
#     r'amazon\.in/(?:dp|gp)|'
#     r'amzn\.(?:in|to)|'
#     r'flipkart\.com/|'
#     r'fkrt\.\w+|'
#     r'(?:buy|order|shop)(?: now| here| at)?\s*[:\-]?\s*https?://|'
#     r'(?:loot|deal|offer)\s+at\s+₹|'
#     r'after\s+cashback\s+₹|'
#     r'collect\s+cashback\s*[:\-]?\s*https?://'
#     r')',
#     re.IGNORECASE
# )

# def is_cc_deal(text: str) -> bool:
#     if not text:
#         return False
#     if CC_FALSE_POSITIVE.search(text):
#         log.debug("[CC-DETECT] ❌ False-positive guard triggered — not a CC deal")
#         return False
#     if CC_STRONG_KEYWORDS.search(text):
#         log.debug("[CC-DETECT] ✅ Strong CC keyword matched")
#         return True
#     has_bank    = bool(BANK_NAMES.search(text))
#     has_weak    = bool(CC_WEAK_KEYWORDS.search(text))
#     has_cc_link = bool(CC_SHORT_LINK_PATTERNS.search(text))
#     if has_bank and has_weak:
#         log.debug("[CC-DETECT] ✅ Bank name + weak CC keyword matched")
#         return True
#     if has_cc_link and has_weak:
#         log.debug("[CC-DETECT] ✅ CC short link + weak CC keyword matched")
#         return True
#     return False

# def extract_cc_short_links(text):
#     if not text:
#         return []
#     return CC_SHORT_LINK_PATTERNS.findall(text)

# # ══════════════════════════════════════════
# #  FASHION DEAL DETECTION  ← NEW
# # ══════════════════════════════════════════
# FASHION_KEYWORDS = re.compile(
#     r'\b('
#     r'shirt|t-?shirt|shirts|'
#     r'jeans|denim|'
#     r'dress|dresses|'
#     r'kurta|kurti|kurtas|kurtis|'
#     r'sneakers?|'
#     r'footwear|'
#     r'ethnic(?: wear)?|'
#     r'saree|sari|sarees|'
#     r'lehenga|lehnga|lehengha|'
#     r'salwar|churidar|'
#     r'dupatta|'
#     r'palazzo|'
#     r'suit(?: set)?|'
#     r'anarkali|'
#     r'sherwani|'
#     r'trouser|trousers|'
#     r'chinos|'
#     r'shorts|'
#     r'jogger|joggers|'
#     r'track ?pant|'
#     r'sweatshirt|hoodie|'
#     r'jacket|jackets|'
#     r'blazer|'
#     r'coat|overcoat|'
#     r'sandals?|'
#     r'heels?|'
#     r'loafer|loafers|'
#     r'flip.?flop|'
#     r'sports? shoe|'
#     r'running shoe|'
#     r'formal shoe|'
#     r'casual shoe|'
#     r'handbag|hand ?bag|'
#     r'purse|clutch|'
#     r'tote bag|'
#     r'backpack|'
#     r'wallet|'
#     r'belt|belts|'
#     r'watch|watches|'
#     r'sunglasses|'
#     r'top|tops|'
#     r'skirt|skirts|'
#     r'leggings?|'
#     r'innerwear|underwear|lingerie|'
#     r'nightwear|night ?suit|'
#     r'swimwear|swim ?suit|'
#     r'athleisure|'
#     r'co-?ord(?: set)?|'
#     r'western wear|'
#     r'indo-?western|'
#     r'men(?:\'s)? fashion|'
#     r'women(?:\'s)? fashion|'
#     r'kids? fashion|'
#     r'apparel|garment|clothing|'
#     r'myntra|ajio|bewakoof|'
#     r'tata cliq fashion'
#     r')\b',
#     re.IGNORECASE
# )

# def is_fashion_deal(text: str):
#     match = bool(FASHION_KEYWORDS.search(text))
#     print("Fashion:", match, text[:100])
#     return match


# # ══════════════════════════════════════════
# #  BEAUTY DEAL DETECTION  ← NEW
# # ══════════════════════════════════════════
# BEAUTY_KEYWORDS = re.compile(
#     r'\b('
#     r'lipstick|lip ?gloss|lip ?liner|lip ?balm|'
#     r'foundation|concealer|'
#     r'mascara|eyeliner|eye ?shadow|'
#     r'blush|highlighter|contour|'
#     r'primer|setting spray|'
#     r'bb cream|cc cream|'
#     r'makeup|make-?up|cosmetics?|'
#     r'skincare|skin ?care|'
#     r'moisturis(?:er|ing)|moisturizer|'
#     r'serum|face serum|'
#     r'sunscreen|spf|'
#     r'face wash|face ?wash|cleanser|'
#     r'toner|face toner|'
#     r'face mask|sheet mask|'
#     r'exfoliat(?:or|ing)|scrub|'
#     r'eye cream|under.?eye|'
#     r'anti.?aging|anti.?ageing|'
#     r'night cream|day cream|'
#     r'body lotion|body ?butter|'
#     r'shampoo|conditioner|'
#     r'hair oil|hair serum|hair mask|'
#     r'hair color|hair colour|hair dye|'
#     r'hair treatment|'
#     r'dry shampoo|'
#     r'perfume|deo(?:dorant)?|cologne|'
#     r'body wash|shower gel|'
#     r'bath bomb|'
#     r'nail paint|nail polish|nail ?art|'
#     r'lip care|'
#     r'beard oil|beard grooming|'
#     r'face ?pack|'
#     r'vitamin c|hyaluronic|niacinamide|retinol|'
#     r'nykaa|purplle|smashbox|mac cosmetics|'
#     r'lakme|l\'oreal|loreal|maybelline|'
#     r'the ordinary|dot & key|plum|'
#     r'mamaearth|wow skin|forest essentials|'
#     r'biotique|himalaya|'
#     r'beauty|grooming'
#     r')\b',
#     re.IGNORECASE
# )

# def is_beauty_deal(text):
#     match = bool(BEAUTY_KEYWORDS.search(text))
#     print("Beauty:", match, text[:100])
#     return match

# # ══════════════════════════════════════════
# #  NON-AMAZON/FK LINK DETECTOR  ← NEW
# #  (Myntra, Ajio, Nykaa, generic, etc.)
# # ══════════════════════════════════════════
# def extract_non_amz_fk_links(text):
#     if not text:
#         return []
#     all_links = re.findall(r'https?://\S+', text)
#     result = []
#     for link in all_links:
#         is_amz = bool(re.search(r'amazon\.in|amzn\.in|amzn\.to|amazon\.com', link, re.I))
#         is_fk  = bool(re.search(r'flipkart\.com|fkrt\.\w+|dl\.flipkart\.com|bilty\.co', link, re.I))
#         if not is_amz and not is_fk:
#             result.append(link)
#     return result

# # ══════════════════════════════════════════
# #  IST TIME HELPERS
# # ══════════════════════════════════════════
# def get_ist_now():
#     ist = pytz.timezone("Asia/Kolkata")
#     return datetime.now(ist)

# def is_quiet_hours():
#     now = get_ist_now()
#     current_minutes = now.hour * 60 + now.minute
#     quiet_start = 1 * 60 + 0
#     quiet_end   = 8 * 60 + 0
#     return quiet_start <= current_minutes < quiet_end

# # ══════════════════════════════════════════
# #  HEALTH CHECK
# # ══════════════════════════════════════════
# class HealthCheck(BaseHTTPRequestHandler):
#     def do_GET(self):
#         self.send_response(200)
#         self.end_headers()
#         self.wfile.write(b"Bot is running!")
#     def log_message(self, *args):
#         pass

# threading.Thread(
#     target=lambda: HTTPServer(("0.0.0.0", 8080), HealthCheck).serve_forever(),
#     daemon=True
# ).start()

# # ══════════════════════════════════════════
# #  STATS
# # ══════════════════════════════════════════
# stats = {
#     "deals_found": 0,
#     "sent_to_extrape": 0,
#     "fk_sent_to_wa": 0,
#     "cc_sent_direct": 0,
#     "cc_sent_via_extrape": 0,
#     "amz_sent_to_dealspouch": 0,
#     "posted_to_tg": 0,
#     "sent_to_wa_bulk": 0,
#     "ignored": 0,
#     "rate_dropped": 0,
#     "stale_dropped": 0,
#     # ── NEW ──
#     "fashion_sent_to_extrape": 0,
#     "fashion_sent_direct_wa": 0,
#     "fashion_finnin_direct": 0,
#     "beauty_finnin_direct": 0,
#     "beauty_sent_to_extrape": 0,
#     "beauty_sent_direct_wa": 0,
# }

# # ══════════════════════════════════════════
# #  DAILY DEAL COUNTER (random 13 WA invite replacements)
# # ══════════════════════════════════════════
# _daily_counter_date = None
# _daily_deal_count   = 0
# _lucky_deal_slots   = set()

# WA_INVITE_LINK      = "https://tinyurl.com/fhknr97k"
# TG_BOT_FOOTER       = "\n\nTelegram Bot - t.me/Dealspouch_Product_bot"
# LUCKY_DEALS_PER_DAY = 13

# def _refresh_daily_counter():
#     global _daily_counter_date, _daily_deal_count, _lucky_deal_slots
#     today = get_ist_now().date()
#     if _daily_counter_date != today:
#         _daily_counter_date = today
#         _daily_deal_count   = 0
#         _lucky_deal_slots   = set(random.sample(range(1, 61), LUCKY_DEALS_PER_DAY))
#         log.info(f"[DAILY] 🗓️ New day {today} — lucky slots: {sorted(_lucky_deal_slots)}")

# def _is_lucky_deal() -> bool:
#     global _daily_deal_count
#     _refresh_daily_counter()
#     _daily_deal_count += 1
#     lucky = _daily_deal_count in _lucky_deal_slots
#     log.info(f"[DAILY] Deal #{_daily_deal_count} today | lucky={lucky}")
#     return lucky

# # ══════════════════════════════════════════
# #  SHARED STATE
# # ══════════════════════════════════════════
# pending_media          = {}
# sent_links_store       = {}
# sent_original_text     = {}
# dealspouch_media_queue = collections.deque()

# # ── NEW: separate media queues for fashion and beauty ──
# fashion_dealspouch_media_queue = collections.deque()
# beauty_dealspouch_media_queue  = collections.deque()

# client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

# last_dealspouch_handled     = 0
# DEALSPOUCH_COOLDOWN         = 15
# extrape_seen_hashes         = set()
# extrape_processed_reply_ids = set()
# source_seen_hashes          = set()

# # ══════════════════════════════════════════
# #  LINK DETECTORS
# # ══════════════════════════════════════════
# def extract_amazon_links(text):
#     if not text:
#         return []
#     return re.findall(
#         r'https?://(?:www\.)?(?:amazon\.in|amzn\.in|amzn\.to|amazon\.com)[^\s]*',
#         text
#     )

# def extract_flipkart_links_source(text):
#     if not text:
#         return []
#     return re.findall(
#         r'https?://(?:www\.)?(?:flipkart\.com|fkrt\.\w+|dl\.flipkart\.com)[^\s]*',
#         text
#     )

# def extract_flipkart_links(text):
#     if not text:
#         return []
#     return re.findall(
#         r'https?://(?:www\.)?(?:flipkart\.com|fkrt\.\w+|dl\.flipkart\.com|bilty\.co)[^\s]*',
#         text
#     )

# def extract_all_links(text):
#     if not text:
#         return set()
#     return set(re.findall(r'https?://\S+', text))

# def has_dealspouch_link(text):
#     return text and "amaz.dealspouch.com" in text

# def is_extrape_failure(text):
#     if not text:
#         return False
#     return "will not be able to convert" in text.lower()

# def is_echo_of_sent(text):
#     if not sent_links_store:
#         return False
#     reply_links = extract_all_links(text)
#     if not reply_links:
#         return False
#     for entry in sent_links_store.values():
#         if reply_links & entry["links"]:
#             log.info("[EXTRAPE] 🔄 Echo detected — same links as sent. Waiting for converted reply...")
#             return True
#     return False

# def _cleanup_store(msg_id):
#     pending_media.pop(msg_id, None)
#     sent_links_store.pop(msg_id, None)
#     sent_original_text.pop(msg_id, None)

# def _store_deal(sent_msg_id, media_bytes, original_links, is_cc, original_text, deal_type="generic"):
#     pending_media[sent_msg_id]      = media_bytes
#     sent_links_store[sent_msg_id]   = {"links": original_links, "is_cc": is_cc, "deal_type": deal_type}
#     sent_original_text[sent_msg_id] = original_text
#     if len(sent_links_store) > 20:
#         oldest = next(iter(sent_links_store))
#         _cleanup_store(oldest)

# # ══════════════════════════════════════════
# #  QUEUE PURGE HELPER
# # ══════════════════════════════════════════
# def _purge_stale_dealspouch_queue():
#     purged = 0
#     cutoff = time.time() - (MAX_DEAL_AGE_MINUTES * 60)
#     while dealspouch_time_queue and dealspouch_time_queue[0] < cutoff:
#         dealspouch_time_queue.popleft()
#         if dealspouch_media_queue:
#             dealspouch_media_queue.popleft()
#         purged += 1
#     if purged:
#         log.info(
#             f"[QUEUE-PURGE] 🧹 Evicted {purged} stale entry(ies) from Dealspouch queue | "
#             f"remaining={len(dealspouch_time_queue)}"
#         )

# def _purge_stale_fashion_queue():
#     """Purge stale entries from fashion Dealspouch queues."""
#     purged = 0
#     cutoff = time.time() - (MAX_DEAL_AGE_MINUTES * 60)
#     while fashion_dealspouch_time_queue and fashion_dealspouch_time_queue[0] < cutoff:
#         fashion_dealspouch_time_queue.popleft()
#         if fashion_dealspouch_media_queue:
#             fashion_dealspouch_media_queue.popleft()
#         purged += 1
#     if purged:
#         log.info(f"[QUEUE-PURGE] 🧹 Evicted {purged} stale entry(ies) from Fashion Dealspouch queue")

# def _purge_stale_beauty_queue():
#     """Purge stale entries from beauty Dealspouch queues."""
#     purged = 0
#     cutoff = time.time() - (MAX_DEAL_AGE_MINUTES * 60)
#     while beauty_dealspouch_time_queue and beauty_dealspouch_time_queue[0] < cutoff:
#         beauty_dealspouch_time_queue.popleft()
#         if beauty_dealspouch_media_queue:
#             beauty_dealspouch_media_queue.popleft()
#         purged += 1
#     if purged:
#         log.info(f"[QUEUE-PURGE] 🧹 Evicted {purged} stale entry(ies) from Beauty Dealspouch queue")

# # ══════════════════════════════════════════
# #  TEXT SANITIZER
# # ══════════════════════════════════════════
# _FAKE_URL_RE = re.compile(
#     r'https?://(?!'
#     r'(?:[a-z0-9\-]+\.)+[a-z]{2,}'
#     r')\S*',
#     re.IGNORECASE
# )

# def sanitize_text_for_bot(text: str) -> str:
#     if not text:
#         return text
#     cleaned = _FAKE_URL_RE.sub('', text).strip()
#     if cleaned != text:
#         log.info("[SANITIZE] Removed fake URL fragments from text")
#     return cleaned

# # ══════════════════════════════════════════
# #  MEDIA DOWNLOADER
# # ══════════════════════════════════════════
# async def download_media_bytes(message):
#     try:
#         if message.media and isinstance(message.media, (MessageMediaPhoto, MessageMediaDocument)):
#             buf = io.BytesIO()
#             await client.download_media(message, file=buf)
#             return buf.getvalue()
#     except Exception as e:
#         log.warning(f"Media download failed: {e}")
#     return None

# # ══════════════════════════════════════════
# #  WHATSAPP SENDERS
# # ══════════════════════════════════════════
# async def send_to_whatsapp_bulk(text, image_bytes=None):
#     if not BAILEYS_URL:
#         log.warning("[WA-BULK] BAILEYS_URL not set!")
#         return
#     try:
#         async with aiohttp.ClientSession() as session:
#             if image_bytes:
#                 form = aiohttp.FormData()
#                 form.add_field("text", text or "")
#                 form.add_field("secret", BAILEYS_SECRET)
#                 form.add_field("image", image_bytes, filename="deal.jpg", content_type="image/jpeg")
#                 async with session.post(
#                     f"{BAILEYS_URL}/send", data=form,
#                     timeout=aiohttp.ClientTimeout(total=30)
#                 ) as resp:
#                     body = await resp.text()
#                     if resp.status != 200:
#                         log.error(f"[WA-BULK] ❌ HTTP {resp.status} — WA sender may be down! {body[:120]}")
#                         return
#                     log.info(f"[WA-BULK] ✅ Queued! {body[:80]}")
#             else:
#                 async with session.post(
#                     f"{BAILEYS_URL}/send",
#                     json={"text": text, "secret": BAILEYS_SECRET},
#                     timeout=aiohttp.ClientTimeout(total=30)
#                 ) as resp:
#                     body = await resp.text()
#                     if resp.status != 200:
#                         log.error(f"[WA-BULK] ❌ HTTP {resp.status} — WA sender may be down! {body[:120]}")
#                         return
#                     log.info(f"[WA-BULK] ✅ Queued! {body[:80]}")
#         stats["sent_to_wa_bulk"] += 1
#     except Exception as e:
#         log.error(f"[WA-BULK] ❌ Failed: {e}")

# async def send_to_whatsapp_single(text, target_group, image_bytes=None):
#     if not BAILEYS_URL:
#         log.warning("[WA-SINGLE] BAILEYS_URL not set!")
#         return
#     try:
#         async with aiohttp.ClientSession() as session:
#             if image_bytes:
#                 form = aiohttp.FormData()
#                 form.add_field("text", text or "")
#                 form.add_field("secret", BAILEYS_SECRET)
#                 form.add_field("target", target_group)
#                 form.add_field("image", image_bytes, filename="deal.jpg", content_type="image/jpeg")
#                 async with session.post(
#                     f"{BAILEYS_URL}/send-single", data=form,
#                     timeout=aiohttp.ClientTimeout(total=30)
#                 ) as resp:
#                     body = await resp.text()
#                     if resp.status != 200:
#                         log.error(f"[WA-SINGLE] ❌ HTTP {resp.status} — WA sender may be down! {body[:120]}")
#                         return
#                     log.info(f"[WA-SINGLE] ✅ Sent to {target_group}! {body[:80]}")
#             else:
#                 async with session.post(
#                     f"{BAILEYS_URL}/send-single",
#                     json={"text": text, "secret": BAILEYS_SECRET, "target": target_group},
#                     timeout=aiohttp.ClientTimeout(total=30)
#                 ) as resp:
#                     body = await resp.text()
#                     if resp.status != 200:
#                         log.error(f"[WA-SINGLE] ❌ HTTP {resp.status} — WA sender may be down! {body[:120]}")
#                         return
#                     log.info(f"[WA-SINGLE] ✅ Sent to {target_group}! {body[:80]}")
#     except Exception as e:
#         log.error(f"[WA-SINGLE] ❌ Failed: {e}")

# # ══════════════════════════════════════════
# #  STEP 1: Source groups → Route by deal type
# # ══════════════════════════════════════════
# @client.on(events.NewMessage(chats=SOURCE_GROUPS))
# async def handle_source(event):
#     if event.message.edit_date:
#         return

#     text      = event.message.text or event.message.caption or ""
#     amz_links = extract_amazon_links(text)
#     fk_links  = extract_flipkart_links_source(text)
#     cc_deal   = is_cc_deal(text)
#     chat_id   = event.chat_id

#     # ══════════════════════════════════════
#     #  FINNIN DEALS GROUP → Fashion direct to WA  ← NEW
#     # ══════════════════════════════════════
#     if chat_id == -1001481951196:
#         if not is_fashion_deal(text):
#             return
#         log.info(f"[FINNIN] 👗 Fashion deal from Finnin TG group — sending direct to Fashion WA")
#         media_bytes = await download_media_bytes(event.message)
#         if is_quiet_hours():
#             log.info("[FINNIN] 🌙 Quiet hours — skipping")
#             stats["ignored"] += 1
#         else:
#             await send_to_whatsapp_single(text, FASHION_WA_GROUP, media_bytes)
#             stats["fashion_finnin_direct"] += 1
#             log.info("[FINNIN] ✅ Sent directly to Fashion WA group")
#         return

#     if chat_id == -1001481951196:
#         if not is_beauty_deal(text):
#             return
#         log.info(f"[FINNIN] 👗 Beauty deal from Finnin TG group — sending direct to Beauty WA")
#         media_bytes = await download_media_bytes(event.message)
#         if is_quiet_hours():
#             log.info("[FINNIN] 🌙 Quiet hours — skipping")
#             stats["ignored"] += 1
#         else:
#             await send_to_whatsapp_single(text, BEAUTY_WA_GROUP, media_bytes)
#             stats["beauty_finnin_direct"] += 1
#             log.info("[FINNIN] ✅ Sent directly to beauty WA group")
#         return

#     # ══════════════════════════════════════
#     #  FASHION SOURCE GROUP → ExtraPe  ← NEW
#     # ══════════════════════════════════════
#     if chat_id in SOURCE_GROUPS and is_fashion_deal(text):
#         log.info(f"[FASHION-SOURCE] 👗 Fashion deal found → ExtraPe")
#         media_bytes    = await download_media_bytes(event.message)
#         original_links = extract_all_links(text)
#         clean_text     = sanitize_text_for_bot(text)
#         sent = await client.send_message(EXTRAPE_BOT, clean_text)
#         _store_deal(sent.id, media_bytes, original_links, is_cc=False, original_text=clean_text, deal_type="fashion")
#         stats["fashion_sent_to_extrape"] += 1
#         log.info(f"[FASHION-SOURCE] 📤 Sent to ExtraPe (deal_type=fashion, msg_id={sent.id})")
#         return

#     # ══════════════════════════════════════
#     #  BEAUTY SOURCE GROUP → ExtraPe  ← NEW
#     # ══════════════════════════════════════
#     if chat_id in SOURCE_GROUPS and is_beauty_deal(text):
#         log.info(f"[BEAUTY-SOURCE] 💄 Beauty deal found → ExtraPe")
#         media_bytes    = await download_media_bytes(event.message)
#         original_links = extract_all_links(text)
#         clean_text     = sanitize_text_for_bot(text)
#         sent = await client.send_message(EXTRAPE_BOT, clean_text)
#         _store_deal(sent.id, media_bytes, original_links, is_cc=False, original_text=clean_text, deal_type="beauty")
#         stats["beauty_sent_to_extrape"] += 1
#         log.info(f"[BEAUTY-SOURCE] 📤 Sent to ExtraPe (deal_type=beauty, msg_id={sent.id})")
#         return

#     # ── Existing pipelines below (unchanged) ──

#     if not amz_links and not fk_links and not cc_deal:
#         return

#     stats["deals_found"] += 1

#     # ── CC DEAL — DIRECT GROUP ──
#     if cc_deal and chat_id == CC_DIRECT_GROUP:
#         log.info(f"[CC-DIRECT] 💳 CC Deal #{stats['deals_found']} from direct group!")
#         media_bytes = await download_media_bytes(event.message)
#         log.info(f"[CC-DIRECT] 🖼️ Image: {'yes' if media_bytes else 'no'}")
#         if is_quiet_hours():
#             log.info("[CC-DIRECT] 🌙 Quiet hours — skipping")
#             stats["ignored"] += 1
#         else:
#             await send_to_whatsapp_single(text, CC_WA_GROUP, media_bytes)
#             stats["cc_sent_direct"] += 1
#             log.info("[CC-DIRECT] ✅ Sent directly to CC WA group")
#         return

#     # ── Source-level dedup ──
#     all_links_in_msg = sorted(extract_all_links(text))
#     if all_links_in_msg:
#         dedup_key   = hash(tuple(all_links_in_msg))
#         dedup_label = f"links:{all_links_in_msg}"
#     else:
#         normalized  = re.sub(r'\s+', ' ', text.strip().lower())
#         dedup_key   = hash(normalized)
#         dedup_label = "normalized-text"

#     if dedup_key in source_seen_hashes:
#         log.info(f"[SOURCE] ⏭️ Duplicate ({dedup_label}) — already dispatched, skipping")
#         return
#     source_seen_hashes.add(dedup_key)
#     if len(source_seen_hashes) > 500:
#         source_seen_hashes.pop()

#     # ── CC DEAL — OTHER GROUPS → ExtraPe ──
#     if cc_deal and chat_id != CC_DIRECT_GROUP:
#         log.info(f"[CC-EXTRAPE] 💳 CC Deal #{stats['deals_found']} from group {chat_id} → ExtraPe")
#         media_bytes    = await download_media_bytes(event.message)
#         original_links = extract_all_links(text)
#         clean_text     = sanitize_text_for_bot(text)
#         sent = await client.send_message(EXTRAPE_BOT, clean_text)
#         _store_deal(sent.id, media_bytes, original_links, is_cc=True, original_text=clean_text, deal_type="generic")
#         stats["sent_to_extrape"] += 1
#         log.info(f"[CC-EXTRAPE] 📤 Sent to ExtraPe (CC=True, msg_id={sent.id})")
#         return

#     # ── AMAZON / FLIPKART → ExtraPe ──
#     link_type      = "Amazon" if amz_links else "Flipkart"
#     log.info(f"[SOURCE] 🎯 {link_type} Deal #{stats['deals_found']} found!")
#     media_bytes    = await download_media_bytes(event.message)
#     original_links = extract_all_links(text)
#     clean_text     = sanitize_text_for_bot(text)
#     sent = await client.send_message(EXTRAPE_BOT, clean_text)
#     _store_deal(sent.id, media_bytes, original_links, is_cc=False, original_text=clean_text, deal_type="generic")
#     stats["sent_to_extrape"] += 1
#     log.info(f"[EXTRAPE] 📤 Sent to ExtraPe (CC=False, msg_id={sent.id})")

# # ══════════════════════════════════════════
# #  STEP 2: ExtraPe reply → match by reply_to_msg_id
# # ══════════════════════════════════════════
# @client.on(events.NewMessage(chats=EXTRAPE_BOT))
# async def handle_extrape(event):
#     text = event.message.text or event.message.caption or ""
#     if not text:
#         return

#     replied_to_id = None
#     if event.message.reply_to and event.message.reply_to.reply_to_msg_id:
#         replied_to_id = event.message.reply_to.reply_to_msg_id
#         log.info(f"[EXTRAPE] 🔗 Reply to msg_id={replied_to_id}")

#     # ── ExtraPe failure → forward original to EarnKaro ──
#     if is_extrape_failure(text):
#         log.info("[EXTRAPE] ❌ Conversion failed — forwarding original to EarnKaro")
#         original_text = None
#         if replied_to_id and replied_to_id in sent_original_text:
#             original_text = sent_original_text.get(replied_to_id)
#             _cleanup_store(replied_to_id)
#         elif sent_original_text:
#             oldest_key    = next(iter(sent_original_text))
#             original_text = sent_original_text.get(oldest_key)
#             _cleanup_store(oldest_key)
#         if original_text:
#             await client.send_message(EARNKARO_BOT, original_text)
#             log.info("[EARNKARO] 📤 Forwarded original deal to EarnKaro")
#             stats["ignored"] += 1
#         else:
#             log.warning("[EARNKARO] ⚠️ No original text found to forward")
#         return

#     # ── Skip echo of our own input ──
#     if is_echo_of_sent(text):
#         return

#     # ── Skip already-processed reply_to_id ──
#     if replied_to_id and replied_to_id in extrape_processed_reply_ids:
#         log.info(f"[EXTRAPE] ⏭️ reply_to_id={replied_to_id} already processed — skipping duplicate")
#         stats["ignored"] += 1
#         return

#     # ── Dedup by content hash ──
#     msg_hash = hash(text.strip())
#     if msg_hash in extrape_seen_hashes:
#         stats["ignored"] += 1
#         log.info("[EXTRAPE] ⏭️ Exact duplicate content — ignored")
#         return
#     extrape_seen_hashes.add(msg_hash)
#     if len(extrape_seen_hashes) > 50:
#         extrape_seen_hashes.pop()

#     # ══════════════════════════════════════════
#     #  FETCH MEDIA + FLAGS
#     # ══════════════════════════════════════════
#     media_bytes   = None
#     pending_is_cc = False
#     deal_type     = "generic"   # ← NEW: default

#     if replied_to_id and replied_to_id in pending_media:
#         media_bytes   = pending_media.get(replied_to_id)
#         store_entry   = sent_links_store.get(replied_to_id, {})
#         pending_is_cc = store_entry.get("is_cc", False)
#         deal_type     = store_entry.get("deal_type", "generic")   # ← NEW
#         _cleanup_store(replied_to_id)
#         log.info(
#             f"[EXTRAPE] ✅ Matched reply_to_id={replied_to_id} | "
#             f"cc={pending_is_cc} | deal_type={deal_type} | image={'yes' if media_bytes else 'no'}"
#         )
#     else:
#         log.warning(
#             "[EXTRAPE] ⚠️ No reply_to match — will try ExtraPe's own image only"
#         )

#     if not media_bytes:
#         media_bytes = await download_media_bytes(event.message)
#         if media_bytes:
#             log.info("[EXTRAPE] 🖼️ Using ExtraPe reply's own image as fallback")
#         else:
#             log.info("[EXTRAPE] 🖼️ No image available — will send text only")

#     ist_now = get_ist_now()

#     if replied_to_id:
#         extrape_processed_reply_ids.add(replied_to_id)
#         if len(extrape_processed_reply_ids) > 100:
#             extrape_processed_reply_ids.pop()

#     # ══════════════════════════════════════════
#     #  FASHION PIPELINE  ← NEW
#     # ══════════════════════════════════════════
#     if deal_type == "fashion":

#         amz_links = extract_amazon_links(text)

#         if amz_links:

#             await client.send_message(
#                 DEALSPOUCH_BOT,
#                 text
#             )

#             dealspouch_media_queue.append(
#                 (
#                     media_bytes,
#                     "fashion"
#                 )
#             )

#             dealspouch_time_queue.append(
#                 time.time()
#             )

#         else:

#             await send_to_whatsapp_single(
#                 text,
#                 FASHION_WA_GROUP,
#                 media_bytes
#             )

#         return

#         # amz_links = extract_amazon_links(text)
#         # fk_links  = extract_flipkart_links(text)
#         # other_links = extract_non_amz_fk_links(text)

#         # if amz_links:
#         #     # Amazon fashion → Dealspouch → Fashion WA group (via handle_dealspouch_fashion)
#         #     log.info(f"[FASHION] ✅ AMZ fashion → Dealspouch | image={'yes' if media_bytes else 'no'}")
#         #     _purge_stale_fashion_queue()
#         #     dealspouch_send_ts = time.time()
#         #     await client.send_message(DEALSPOUCH_BOT, text)
#         #     fashion_dealspouch_media_queue.append(media_bytes)
#         #     fashion_dealspouch_time_queue.append(dealspouch_send_ts)
#         #     if len(fashion_dealspouch_media_queue) > 20:
#         #         fashion_dealspouch_media_queue.popleft()
#         #         fashion_dealspouch_time_queue.popleft()
#         #     stats["fashion_sent_to_extrape"] += 1
#         #     log.info(f"[FASHION] 📤 Queued to Dealspouch | queue={len(fashion_dealspouch_media_queue)}")

#         # elif fk_links or other_links:
#         #     # Non-Amazon fashion (Flipkart, Myntra, Ajio, etc.) → direct to Fashion WA group
#         #     log.info(f"[FASHION] 🛒 Non-AMZ fashion → direct Fashion WA | image={'yes' if media_bytes else 'no'}")
#         #     await send_to_whatsapp_single(text, FASHION_WA_GROUP, media_bytes)
#         #     stats["fashion_sent_direct_wa"] += 1
#         # else:
#         #     log.info("[FASHION] ⏭️ No recognisable link in fashion reply — ignored")
#         #     stats["ignored"] += 1
#         # return

#     # ══════════════════════════════════════════
#     #  BEAUTY PIPELINE  ← NEW
#     # ══════════════════════════════════════════
#     if deal_type == "beauty":
#         # if is_quiet_hours():
#         #     log.info(f"[BEAUTY] 🌙 Quiet hours — skipping beauty deal")
#         #     stats["ignored"] += 1
#         #     return

#         amz_links = extract_amazon_links(text)

#         if amz_links:

#             await client.send_message(
#                 DEALSPOUCH_BOT,
#                 text
#             )

#             dealspouch_media_queue.append(
#                 (
#                     media_bytes,
#                     "beauty"
#                 )
#             )

#             dealspouch_time_queue.append(
#                 time.time()
#             )

#         else:

#             await send_to_whatsapp_single(
#                 text,
#                 BEAUTY_WA_GROUP,
#                 media_bytes
#             )

#         return

#         # amz_links   = extract_amazon_links(text)
#         # fk_links    = extract_flipkart_links(text)
#         # other_links = extract_non_amz_fk_links(text)

#         # if amz_links:
#         #     # Amazon beauty → Dealspouch → Beauty WA group
#         #     log.info(f"[BEAUTY] ✅ AMZ beauty → Dealspouch | image={'yes' if media_bytes else 'no'}")
#         #     _purge_stale_beauty_queue()
#         #     dealspouch_send_ts = time.time()
#         #     await client.send_message(DEALSPOUCH_BOT, text)
#         #     beauty_dealspouch_media_queue.append(media_bytes)
#         #     beauty_dealspouch_time_queue.append(dealspouch_send_ts)
#         #     if len(beauty_dealspouch_media_queue) > 20:
#         #         beauty_dealspouch_media_queue.popleft()
#         #         beauty_dealspouch_time_queue.popleft()
#         #     stats["beauty_sent_to_extrape"] += 1
#         #     log.info(f"[BEAUTY] 📤 Queued to Dealspouch | queue={len(beauty_dealspouch_media_queue)}")

#         # elif fk_links or other_links:
#         #     # Non-Amazon beauty → direct to Beauty WA group
#         #     log.info(f"[BEAUTY] 💄 Non-AMZ beauty → direct Beauty WA | image={'yes' if media_bytes else 'no'}")
#         #     await send_to_whatsapp_single(text, BEAUTY_WA_GROUP, media_bytes)
#         #     stats["beauty_sent_direct_wa"] += 1
#         # else:
#         #     log.info("[BEAUTY] ⏭️ No recognisable link in beauty reply — ignored")
#         #     stats["ignored"] += 1
#         # return

#     # ── CC deal → CC WA group ──
#     if pending_is_cc or is_cc_deal(text):
#         log.info(f"[EXTRAPE] 💳 CC deal → CC WA group | image={'yes' if media_bytes else 'no'}")
#         if is_quiet_hours():
#             log.info(f"[WA-SINGLE] 🌙 Quiet hours ({ist_now.strftime('%H:%M')} IST) — skipping CC")
#             stats["ignored"] += 1
#         else:
#             await send_to_whatsapp_single(text, CC_WA_GROUP, media_bytes)
#             stats["cc_sent_via_extrape"] += 1
#         return

#     # ── Flipkart → FK WA group ──
#     if extract_flipkart_links(text):
#         log.info(f"[EXTRAPE] 🛒 FK converted → FK WA group | image={'yes' if media_bytes else 'no'}")
#         if is_quiet_hours():
#             log.info(f"[WA-SINGLE] 🌙 Quiet hours ({ist_now.strftime('%H:%M')} IST) — skipping FK")
#             stats["ignored"] += 1
#         else:
#             await send_to_whatsapp_single(text, FK_WA_GROUP, media_bytes)
#             stats["fk_sent_to_wa"] += 1
#         return

#     # ── Amazon → Dealspouch ──
#     if extract_amazon_links(text):
#         log.info(f"[EXTRAPE] ✅ AMZ converted → Dealspouch | image={'yes' if media_bytes else 'no'}")
#         _purge_stale_dealspouch_queue()
#         dealspouch_send_ts = time.time()
#         await client.send_message(DEALSPOUCH_BOT, text)
#         dealspouch_media_queue.append(media_bytes)
#         dealspouch_time_queue.append(dealspouch_send_ts)
#         if len(dealspouch_media_queue) > 20:
#             dealspouch_media_queue.popleft()
#             dealspouch_time_queue.popleft()
#         log.info(
#             f"[DEALSPOUCH-QUEUE] 📥 Pushed image={'yes' if media_bytes else 'no'} | "
#             f"ts=now (age clock starts here) | "
#             f"queue size: {len(dealspouch_media_queue)}"
#         )
#         stats["amz_sent_to_dealspouch"] += 1
#         return

#     log.info("[EXTRAPE] ⏭️ No recognisable link in reply — ignored")
#     stats["ignored"] += 1

# # ══════════════════════════════════════════
# #  STEP 3a: Dealspouch → TG + WA bulk  (Amazon generic)
# # ══════════════════════════════════════════
# @client.on(events.NewMessage(chats=DEALSPOUCH_BOT))
# async def handle_dealspouch(event):
#     global last_dealspouch_handled
#     text = event.message.text or event.message.caption or ""

#     if not has_dealspouch_link(text):
#         stats["ignored"] += 1
#         log.info("[DEALSPOUCH] ⏭️ Ignored — no dealspouch link")
#         return

#     now = time.time()
#     if now - last_dealspouch_handled < DEALSPOUCH_COOLDOWN:
#         # ── Check if this is a fashion or beauty reply first before discarding ──
#         # Try fashion queue
#         if fashion_dealspouch_time_queue:
#             log.info("[DEALSPOUCH] ↪️ Cooldown active but fashion queue has entries — routing to fashion handler")
#             await _route_dealspouch_fashion(text)
#             # return
#         # Try beauty queue
#         if beauty_dealspouch_time_queue:
#             log.info("[DEALSPOUCH] ↪️ Cooldown active but beauty queue has entries — routing to beauty handler")
#             await _route_dealspouch_beauty(text)
#             # return
#         stats["ignored"] += 1
#         log.info("[DEALSPOUCH] ⏭️ Duplicate ignored")
#         return
#     last_dealspouch_handled = now

#     # # ── Check if this reply belongs to fashion or beauty queue first ──
#     # if fashion_dealspouch_time_queue and not dealspouch_time_queue:
#     #     await _route_dealspouch_fashion(text)
#     #     return
#     # if beauty_dealspouch_time_queue and not dealspouch_time_queue:
#     #     await _route_dealspouch_beauty(text)
#     #     return


#     # ── Generic Amazon pipeline ──
#     media_bytes = None
#     deal_type = "generic"
#     if dealspouch_media_queue:
#         queued = dealspouch_media_queue.popleft()
#         if isinstance(queued, tuple):
#             media_bytes = queued[0]
#             deal_type = queued[1]
#         else:
#             media_bytes = queued
#         log.info(
#             f"[DEALSPOUCH] ✅ Popped from queue | "
#             f"image={'yes' if media_bytes else 'no'} | "
#             f"remaining={len(dealspouch_media_queue)}"
#         )
#     else:
#         # No generic queue entry — try fashion / beauty as fallback
#         if fashion_dealspouch_time_queue:
#             await _route_dealspouch_fashion(text)
#             return
#         if beauty_dealspouch_time_queue:
#             await _route_dealspouch_beauty(text)
#             return
#         log.warning("[DEALSPOUCH] ⚠️ Media queue empty — sending text only")

#     source_ts = None
#     if dealspouch_time_queue:
#         source_ts = dealspouch_time_queue.popleft()
#         age_minutes = (time.time() - source_ts) / 60
#         log.info(
#             f"[FRESHNESS] 🕐 Deal age since Dealspouch send: {age_minutes:.1f} min "
#             f"(max allowed: {MAX_DEAL_AGE_MINUTES} min)"
#         )
#         if age_minutes > MAX_DEAL_AGE_MINUTES:
#             log.info(
#                 f"[FRESHNESS] 🗑️ Dealspouch took {age_minutes:.1f} min to reply — "
#                 f"exceeds {MAX_DEAL_AGE_MINUTES} min limit → DROPPED"
#             )
#             stats["stale_dropped"] += 1
#             return
#     else:
#         log.warning("[FRESHNESS] ⚠️ Time queue empty — skipping freshness check")

#     ist_now = get_ist_now()
#     log.info(f"[DEALSPOUCH] ✅ Fresh deal! IST: {ist_now.strftime('%H:%M')} | image={'yes' if media_bytes else 'no'}")

#     if deal_type == "fashion":
#         log.info("[FASHION] Dealspouch → Fashion WA")
#         await send_to_whatsapp_single(text, FASHION_WA_GROUP, media_bytes)
#         stats["fashion_sent_direct_wa"] += 1
#     elif deal_type == "beauty":
#         log.info("[BEAUTY] Dealspouch → Beauty WA")
#         await send_to_whatsapp_single(text, BEAUTY_WA_GROUP, media_bytes)
#         stats["beauty_sent_direct_wa"] += 1

#     if _is_lucky_deal():
#         text = re.sub(r'https?://amaz\.dealspouch\.com/\S+', WA_INVITE_LINK, text)
#         log.info("[DAILY] 🎯 Lucky deal — replaced dealspouch link with WA invite")

#     text = text + TG_BOT_FOOTER

#     try:
#         if media_bytes:
#             await client.send_file(MY_TG_GROUP, media_bytes, caption=text)
#         else:
#             await client.send_message(MY_TG_GROUP, text)
#         stats["posted_to_tg"] += 1
#         log.info(f"[TG] ✅ Posted to {MY_TG_GROUP}")
#     except Exception as e:
#         log.error(f"[TG] ❌ Failed: {e}")

#     if is_quiet_hours():
#         log.info(f"[WA-BULK] 🌙 Quiet hours ({ist_now.strftime('%H:%M')} IST) — skipping")
#     else:
#         await send_to_whatsapp_bulk(text, media_bytes)

# # ══════════════════════════════════════════
# #  STEP 3b: Dealspouch reply → Fashion WA  ← NEW
# # ══════════════════════════════════════════
# async def _route_dealspouch_fashion(text: str):
#     """Handle a Dealspouch reply that belongs to the fashion pipeline."""
#     media_bytes = None
#     if fashion_dealspouch_media_queue:
#         media_bytes = fashion_dealspouch_media_queue.popleft()
#         log.info(
#             f"[FASHION-DEALSPOUCH] ✅ Popped from fashion queue | "
#             f"image={'yes' if media_bytes else 'no'} | "
#             f"remaining={len(fashion_dealspouch_media_queue)}"
#         )
#     else:
#         log.warning("[FASHION-DEALSPOUCH] ⚠️ Fashion media queue empty — text only")

#     if fashion_dealspouch_time_queue:
#         source_ts   = fashion_dealspouch_time_queue.popleft()
#         age_minutes = (time.time() - source_ts) / 60
#         log.info(f"[FASHION-FRESHNESS] 🕐 Age: {age_minutes:.1f} min (max {MAX_DEAL_AGE_MINUTES})")
#         if age_minutes > MAX_DEAL_AGE_MINUTES:
#             log.info(f"[FASHION-FRESHNESS] 🗑️ Stale ({age_minutes:.1f} min) → DROPPED")
#             stats["stale_dropped"] += 1
#             return
#     else:
#         log.warning("[FASHION-FRESHNESS] ⚠️ Time queue empty — skipping freshness check")

#     if is_quiet_hours():
#         log.info("[FASHION-DEALSPOUCH] 🌙 Quiet hours — skipping")
#         stats["ignored"] += 1
#         return

#     log.info(f"[FASHION-DEALSPOUCH] ✅ Sending to Fashion WA | image={'yes' if media_bytes else 'no'}")
#     await send_to_whatsapp_single(text, FASHION_WA_GROUP, media_bytes)
#     stats["fashion_sent_direct_wa"] += 1

# # ══════════════════════════════════════════
# #  STEP 3c: Dealspouch reply → Beauty WA  ← NEW
# # ══════════════════════════════════════════
# async def _route_dealspouch_beauty(text: str):
#     """Handle a Dealspouch reply that belongs to the beauty pipeline."""
#     media_bytes = None
#     if beauty_dealspouch_media_queue:
#         media_bytes = beauty_dealspouch_media_queue.popleft()
#         log.info(
#             f"[BEAUTY-DEALSPOUCH] ✅ Popped from beauty queue | "
#             f"image={'yes' if media_bytes else 'no'} | "
#             f"remaining={len(beauty_dealspouch_media_queue)}"
#         )
#     else:
#         log.warning("[BEAUTY-DEALSPOUCH] ⚠️ Beauty media queue empty — text only")

#     if beauty_dealspouch_time_queue:
#         source_ts   = beauty_dealspouch_time_queue.popleft()
#         age_minutes = (time.time() - source_ts) / 60
#         log.info(f"[BEAUTY-FRESHNESS] 🕐 Age: {age_minutes:.1f} min (max {MAX_DEAL_AGE_MINUTES})")
#         if age_minutes > MAX_DEAL_AGE_MINUTES:
#             log.info(f"[BEAUTY-FRESHNESS] 🗑️ Stale ({age_minutes:.1f} min) → DROPPED")
#             stats["stale_dropped"] += 1
#             return
#     else:
#         log.warning("[BEAUTY-FRESHNESS] ⚠️ Time queue empty — skipping freshness check")

#     if is_quiet_hours():
#         log.info("[BEAUTY-DEALSPOUCH] 🌙 Quiet hours — skipping")
#         stats["ignored"] += 1
#         return

#     log.info(f"[BEAUTY-DEALSPOUCH] ✅ Sending to Beauty WA | image={'yes' if media_bytes else 'no'}")
#     await send_to_whatsapp_single(text, BEAUTY_WA_GROUP, media_bytes)
#     stats["beauty_sent_direct_wa"] += 1

# # ══════════════════════════════════════════
# #  MAIN
# # ══════════════════════════════════════════
# async def run():
#     while True:
#         try:
#             await client.start()
#             me = await client.get_me()
#             log.info(f"✅ Logged in as: {me.first_name} (@{me.username})")
#             log.info(f"👂 Watching {len(SOURCE_GROUPS)} source group(s)")
#             log.info(f"💳 CC Direct Group    : {CC_DIRECT_GROUP}  ← no bot, rate-limit exempt")
#             log.info(f"🤖 ExtraPe Bot         : {EXTRAPE_BOT}  ← Amazon + Flipkart + CC + Fashion + Beauty")
#             log.info(f"🤖 EarnKaro Bot        : {EARNKARO_BOT}  ← fallback when ExtraPe fails")
#             log.info(f"🤖 Dealspouch Bot      : {DEALSPOUCH_BOT}  ← Amazon (generic + fashion + beauty)")
#             log.info(f"📢 TG Group            : {MY_TG_GROUP}")
#             log.info(f"📲 FK WA Group         : {FK_WA_GROUP}")
#             log.info(f"📲 CC WA Group         : {CC_WA_GROUP}")
#             log.info(f"📲 Fashion WA Group    : {FASHION_WA_GROUP}")
#             log.info(f"📲 Beauty WA Group     : {BEAUTY_WA_GROUP}")
#             log.info(f"📲 WA Sender           : {BAILEYS_URL or 'NOT SET'}")
#             log.info(f"⏱️  Freshness limit     : drop if Dealspouch takes > {MAX_DEAL_AGE_MINUTES} min to reply")
#             log.info(f"🎯 Lucky deals/day     : {LUCKY_DEALS_PER_DAY} (WA invite replaces dealspouch link)")
#             log.info(f"📌 TG Bot Footer       : {TG_BOT_FOOTER.strip()}")
#             log.info("⏳ Waiting for deals...\n")
#             await client.run_until_disconnected()
#         except Exception as e:
#             log.error(f"Disconnected: {e}. Reconnecting in 5s...")
#             await asyncio.sleep(5)

# asyncio.run(run())

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

FK_WA_GROUP      = "120363427339438586@g.us"
CC_WA_GROUP      = "120363426468421381@g.us"
FASHION_WA_GROUP = "120363427489881847@g.us"
BEAUTY_WA_GROUP  = "120363425518003162@g.us"

CC_DIRECT_GROUP = -1001481951196  # also doubles as Finnin TG group

# Generic source groups (Amazon / FK / CC pipeline)
GENERIC_SOURCE_GROUPS = [
    -1001493857075,
    -1001412868909,
    -1001389782464,
    CC_DIRECT_GROUP,
]

# Dedicated fashion / beauty source groups — replace IDs before deploy
FASHION_WA_GROUP = "120363427489881847@g.us"
BEAUTY_WA_GROUP  = "120363425518003162@g.us"    

SOURCE_GROUPS = GENERIC_SOURCE_GROUPS

# ══════════════════════════════════════════
#  FRESHNESS CHECK
#  Unified Dealspouch queue: each entry = (media_bytes, deal_type, timestamp)
# ══════════════════════════════════════════
MAX_DEAL_AGE_MINUTES = 10
dealspouch_queue = collections.deque()

# ══════════════════════════════════════════
#  CC DEAL DETECTION
# ══════════════════════════════════════════
CC_SHORT_LINK_PATTERNS = re.compile(
    r'https?://(?:extp\.in|clnk\.in|isl\.co|go\.onelink\.me|onelink\.me)/\S+',
    re.IGNORECASE
)
CC_STRONG_KEYWORDS = re.compile(
    r'\b(credit card|debit card|lifetime free(?: card)?|joining fee(?: waived)?|'
    r'annual fee(?: waived| nil| zero)?|lounge access|airport lounge|'
    r'fuel surcharge(?: waiver)?|milestone benefit|welcome bonus|welcome voucher|'
    r'welcome gift|card apply|apply (?:for )?(?:the )?card|'
    r'rupay (?:credit |platinum |select )?card|visa (?:credit |platinum |signature )?card|'
    r'mastercard|credit score(?: check| free)?|popcoins|reward points(?: on card)?)\b',
    re.IGNORECASE
)
CC_WEAK_KEYWORDS = re.compile(
    r'\b(apply now|apply here|apply(?: in| online)?|cashback(?: card| offer)?|'
    r'upi(?: payment| cashback| offer)?|zero fee|no fee|free card|card offer|'
    r'card benefit|card perks?|card limit|eligib(?:le|ility)|instant approval|'
    r'pre-?approved|card (?:launch|deal|offer))\b',
    re.IGNORECASE
)
BANK_NAMES = re.compile(
    r'\b(hdfc(?: bank)?|sbi(?: card)?|icici(?: bank)?|axis(?: bank)?|'
    r'kotak(?: bank| mahindra)?|yes bank|idfc(?: first)?|induslnd(?: bank)?|'
    r'rbl(?: bank)?|au(?: small finance)?(?: bank)?|bob(?: financial)?|'
    r'bank of baroda|pnb(?: bank)?|punjab national(?: bank)?|canara(?: bank)?|'
    r'union bank|federal bank|south indian bank|karnataka bank|hsbc|citibank|'
    r'standard chartered|american express|amex|bajaj finserv|one card|'
    r'slice(?: card)?|uni card|fi (?:money|card)|niyo(?: card)?|jupiter(?: card)?|'
    r'scapia|idbi(?: bank)?)\b',
    re.IGNORECASE
)
CC_FALSE_POSITIVE = re.compile(
    r'(?:amazon\.in/(?:dp|gp)|amzn\.(?:in|to)|flipkart\.com/|fkrt\.\w+|'
    r'(?:buy|order|shop)(?: now| here| at)?\s*[:\-]?\s*https?://|'
    r'(?:loot|deal|offer)\s+at\s+₹|after\s+cashback\s+₹|'
    r'collect\s+cashback\s*[:\-]?\s*https?://)',
    re.IGNORECASE
)

def is_cc_deal(text: str) -> bool:
    if not text:
        return False
    if CC_FALSE_POSITIVE.search(text):
        return False
    if CC_STRONG_KEYWORDS.search(text):
        return True
    has_bank    = bool(BANK_NAMES.search(text))
    has_weak    = bool(CC_WEAK_KEYWORDS.search(text))
    has_cc_link = bool(CC_SHORT_LINK_PATTERNS.search(text))
    return (has_bank and has_weak) or (has_cc_link and has_weak)

# ══════════════════════════════════════════
#  FASHION DEAL DETECTION
# ══════════════════════════════════════════
FASHION_KEYWORDS = re.compile(
    r'\b(shirt|t-?shirt|shirts|jeans|denim|dress|dresses|kurta|kurti|kurtas|kurtis|'
    r'sneakers?|footwear|ethnic(?: wear)?|saree|sari|sarees|lehenga|lehnga|lehengha|'
    r'salwar|churidar|dupatta|palazzo|suit(?: set)?|anarkali|sherwani|'
    r'trouser|trousers|chinos|shorts|jogger|joggers|track ?pant|sweatshirt|hoodie|'
    r'jacket|jackets|blazer|coat|overcoat|sandals?|heels?|loafer|loafers|flip.?flop|'
    r'sports? shoe|running shoe|formal shoe|casual shoe|handbag|hand ?bag|'
    r'purse|clutch|tote bag|backpack|wallet|belt|belts|watch|watches|sunglasses|'
    r'top|tops|skirt|skirts|leggings?|innerwear|underwear|lingerie|nightwear|'
    r'night ?suit|swimwear|swim ?suit|athleisure|co-?ord(?: set)?|western wear|'
    r'indo-?western|men(?:\'s)? fashion|women(?:\'s)? fashion|kids? fashion|'
    r'apparel|garment|clothing|myntra|ajio|bewakoof|tata cliq fashion)\b',
    re.IGNORECASE
)

def is_fashion_deal(text: str) -> bool:
    return bool(text) and bool(FASHION_KEYWORDS.search(text))

# ══════════════════════════════════════════
#  BEAUTY DEAL DETECTION
# ══════════════════════════════════════════
BEAUTY_KEYWORDS = re.compile(
    r'\b(lipstick|lip ?gloss|lip ?liner|lip ?balm|foundation|concealer|'
    r'mascara|eyeliner|eye ?shadow|blush|highlighter|contour|primer|setting spray|'
    r'bb cream|cc cream|makeup|make-?up|cosmetics?|skincare|skin ?care|'
    r'moisturis(?:er|ing)|moisturizer|serum|face serum|sunscreen|spf|'
    r'face wash|face ?wash|cleanser|toner|face toner|face mask|sheet mask|'
    r'exfoliat(?:or|ing)|scrub|eye cream|under.?eye|anti.?aging|anti.?ageing|'
    r'night cream|day cream|body lotion|body ?butter|shampoo|conditioner|'
    r'hair oil|hair serum|hair mask|hair color|hair colour|hair dye|hair treatment|'
    r'dry shampoo|perfume|deo(?:dorant)?|cologne|body wash|shower gel|bath bomb|'
    r'nail paint|nail polish|nail ?art|lip care|beard oil|beard grooming|face ?pack|'
    r'vitamin c|hyaluronic|niacinamide|retinol|nykaa|purplle|smashbox|mac cosmetics|'
    r'lakme|l\'oreal|loreal|maybelline|the ordinary|dot & key|plum|mamaearth|'
    r'wow skin|forest essentials|biotique|himalaya|beauty|grooming)\b',
    re.IGNORECASE
)

def is_beauty_deal(text: str) -> bool:
    return bool(text) and bool(BEAUTY_KEYWORDS.search(text))

# ══════════════════════════════════════════
#  IST HELPERS
# ══════════════════════════════════════════
def get_ist_now():
    return datetime.now(pytz.timezone("Asia/Kolkata"))

def is_quiet_hours():
    now = get_ist_now()
    m = now.hour * 60 + now.minute
    return (1 * 60) <= m < (8 * 60)

# ══════════════════════════════════════════
#  HEALTH CHECK
# ══════════════════════════════════════════
class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
        self.wfile.write(b"Bot is running!")
    def log_message(self, *a): pass

threading.Thread(
    target=lambda: HTTPServer(("0.0.0.0", 8080), HealthCheck).serve_forever(),
    daemon=True
).start()

# ══════════════════════════════════════════
#  STATS
# ══════════════════════════════════════════
stats = {
    "deals_found": 0, "sent_to_extrape": 0,
    "fk_sent_to_wa": 0, "cc_sent_direct": 0, "cc_sent_via_extrape": 0,
    "amz_sent_to_dealspouch": 0, "posted_to_tg": 0, "sent_to_wa_bulk": 0,
    "ignored": 0, "rate_dropped": 0, "stale_dropped": 0,
    "fashion_sent_to_extrape": 0, "fashion_sent_direct_wa": 0, "fashion_finnin_direct": 0,
    "beauty_sent_to_extrape": 0,  "beauty_sent_direct_wa": 0,  "beauty_finnin_direct": 0,
}

# ══════════════════════════════════════════
#  DAILY LUCKY DEAL COUNTER
# ══════════════════════════════════════════
_daily_counter_date = None
_daily_deal_count   = 0
_lucky_deal_slots   = set()

WA_INVITE_LINK      = "https://tinyurl.com/fhknr97k"
TG_BOT_FOOTER       = "\n\nTelegram Bot - t.me/Dealspouch_Product_bot"
LUCKY_DEALS_PER_DAY = 13

def _refresh_daily_counter():
    global _daily_counter_date, _daily_deal_count, _lucky_deal_slots
    today = get_ist_now().date()
    if _daily_counter_date != today:
        _daily_counter_date = today
        _daily_deal_count   = 0
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
# ══════════════════════════════════════════
pending_media          = {}   # msg_id → image bytes
sent_links_store       = {}   # msg_id → {links, is_cc, deal_type}
sent_original_text     = {}   # msg_id → original text

client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)

last_dealspouch_handled     = 0
DEALSPOUCH_COOLDOWN         = 15
extrape_seen_hashes         = set()
extrape_processed_reply_ids = set()
source_seen_hashes          = set()

# ══════════════════════════════════════════
#  LINK HELPERS
# ══════════════════════════════════════════
def extract_amazon_links(text):
    if not text: return []
    return re.findall(
        r'https?://(?:www\.)?(?:amazon\.in|amzn\.in|amzn\.to|amazon\.com)[^\s]*', text)

def extract_flipkart_links_source(text):
    if not text: return []
    return re.findall(
        r'https?://(?:www\.)?(?:flipkart\.com|fkrt\.\w+|dl\.flipkart\.com)[^\s]*', text)

def extract_flipkart_links(text):
    if not text: return []
    return re.findall(
        r'https?://(?:www\.)?(?:flipkart\.com|fkrt\.\w+|dl\.flipkart\.com|bilty\.co)[^\s]*', text)

def extract_all_links(text):
    if not text: return set()
    return set(re.findall(r'https?://\S+', text))

def has_dealspouch_link(text):
    return bool(text) and "amaz.dealspouch.com" in text

def is_extrape_failure(text):
    return bool(text) and "will not be able to convert" in text.lower()

def is_echo_of_sent(text):
    if not sent_links_store: return False
    reply_links = extract_all_links(text)
    if not reply_links: return False
    for entry in sent_links_store.values():
        if reply_links & entry["links"]:
            log.info("[EXTRAPE] 🔄 Echo detected — waiting for converted reply...")
            return True
    return False

def _cleanup_store(msg_id):
    pending_media.pop(msg_id, None)
    sent_links_store.pop(msg_id, None)
    sent_original_text.pop(msg_id, None)

def _store_deal(msg_id, media_bytes, links, is_cc, text, deal_type="generic"):
    pending_media[msg_id]      = media_bytes
    sent_links_store[msg_id]   = {"links": links, "is_cc": is_cc, "deal_type": deal_type}
    sent_original_text[msg_id] = text
    if len(sent_links_store) > 20:
        _cleanup_store(next(iter(sent_links_store)))

# ══════════════════════════════════════════
#  QUEUE PURGE
# ══════════════════════════════════════════
def _purge_stale_queue():
    cutoff = time.time() - (MAX_DEAL_AGE_MINUTES * 60)
    purged = 0
    while dealspouch_queue and dealspouch_queue[0][2] < cutoff:
        dealspouch_queue.popleft(); purged += 1
    if purged:
        log.info(f"[QUEUE-PURGE] 🧹 Evicted {purged} stale entries | remaining={len(dealspouch_queue)}")

# ══════════════════════════════════════════
#  TEXT SANITIZER
# ══════════════════════════════════════════
_FAKE_URL_RE = re.compile(
    r'https?://(?!(?:[a-z0-9\-]+\.)+[a-z]{2,})\S*', re.IGNORECASE)

def sanitize_text_for_bot(text: str) -> str:
    if not text: return text
    cleaned = _FAKE_URL_RE.sub('', text).strip()
    if cleaned != text:
        log.info("[SANITIZE] Removed fake URL fragments")
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
        log.warning("[WA-BULK] BAILEYS_URL not set!"); return
    try:
        async with aiohttp.ClientSession() as session:
            if image_bytes:
                form = aiohttp.FormData()
                form.add_field("text", text or "")
                form.add_field("secret", BAILEYS_SECRET)
                form.add_field("image", image_bytes, filename="deal.jpg", content_type="image/jpeg")
                async with session.post(f"{BAILEYS_URL}/send", data=form,
                                        timeout=aiohttp.ClientTimeout(total=30)) as r:
                    body = await r.text()
                    if r.status != 200: log.error(f"[WA-BULK] ❌ HTTP {r.status} {body[:120]}"); return
                    log.info(f"[WA-BULK] ✅ Queued! {body[:80]}")
            else:
                async with session.post(f"{BAILEYS_URL}/send",
                                        json={"text": text, "secret": BAILEYS_SECRET},
                                        timeout=aiohttp.ClientTimeout(total=30)) as r:
                    body = await r.text()
                    if r.status != 200: log.error(f"[WA-BULK] ❌ HTTP {r.status} {body[:120]}"); return
                    log.info(f"[WA-BULK] ✅ Queued! {body[:80]}")
        stats["sent_to_wa_bulk"] += 1
    except Exception as e:
        log.error(f"[WA-BULK] ❌ Failed: {e}")

async def send_to_whatsapp_single(text, target_group, image_bytes=None):
    if not BAILEYS_URL:
        log.warning("[WA-SINGLE] BAILEYS_URL not set!"); return
    try:
        async with aiohttp.ClientSession() as session:
            if image_bytes:
                form = aiohttp.FormData()
                form.add_field("text", text or "")
                form.add_field("secret", BAILEYS_SECRET)
                form.add_field("target", target_group)
                form.add_field("image", image_bytes, filename="deal.jpg", content_type="image/jpeg")
                async with session.post(f"{BAILEYS_URL}/send-single", data=form,
                                        timeout=aiohttp.ClientTimeout(total=30)) as r:
                    body = await r.text()
                    if r.status != 200: log.error(f"[WA-SINGLE] ❌ HTTP {r.status} {body[:120]}"); return
                    log.info(f"[WA-SINGLE] ✅ Sent to {target_group}! {body[:80]}")
            else:
                async with session.post(f"{BAILEYS_URL}/send-single",
                                        json={"text": text, "secret": BAILEYS_SECRET, "target": target_group},
                                        timeout=aiohttp.ClientTimeout(total=30)) as r:
                    body = await r.text()
                    if r.status != 200: log.error(f"[WA-SINGLE] ❌ HTTP {r.status} {body[:120]}"); return
                    log.info(f"[WA-SINGLE] ✅ Sent to {target_group}! {body[:80]}")
    except Exception as e:
        log.error(f"[WA-SINGLE] ❌ Failed: {e}")

# ══════════════════════════════════════════
#  PUSH TO DEALSPOUCH QUEUE
# ══════════════════════════════════════════
async def _send_to_dealspouch(text, media_bytes, deal_type):
    """Send to Dealspouch bot and record in unified queue."""
    _purge_stale_queue()
    await client.send_message(DEALSPOUCH_BOT, text)
    dealspouch_queue.append((media_bytes, deal_type, time.time()))
    if len(dealspouch_queue) > 20:
        dealspouch_queue.popleft()
    log.info(
        f"[DEALSPOUCH-QUEUE] 📥 deal_type={deal_type} | "
        f"image={'yes' if media_bytes else 'no'} | queue={len(dealspouch_queue)}"
    )

# ══════════════════════════════════════════
#  STEP 1 — Source groups → detect & dispatch
# ══════════════════════════════════════════
@client.on(events.NewMessage(chats=SOURCE_GROUPS))
async def handle_source(event):
    if event.message.edit_date:
        return

    text    = event.message.text or event.message.caption or ""
    chat_id = event.chat_id

    # ── FINNIN / CC_DIRECT GROUP ──────────────────────────────────
    # Fashion and beauty deals go directly to their WA groups.
    # CC deals go through the normal CC pipeline below.
    if chat_id == CC_DIRECT_GROUP:
        cc      = is_cc_deal(text)
        fashion = is_fashion_deal(text) and not cc
        beauty  = is_beauty_deal(text) and not cc

        if fashion:
            log.info("[FINNIN] 👗 Fashion deal → Fashion WA direct")
            media_bytes = await download_media_bytes(event.message)
            if is_quiet_hours():
                log.info("[FINNIN] 🌙 Quiet hours — skipping"); stats["ignored"] += 1
            else:
                await send_to_whatsapp_single(text, FASHION_WA_GROUP, media_bytes)
                stats["fashion_finnin_direct"] += 1
                log.info("[FINNIN] ✅ Sent to Fashion WA")
            return

        if beauty:
            log.info("[FINNIN] 💄 Beauty deal → Beauty WA direct")
            media_bytes = await download_media_bytes(event.message)
            if is_quiet_hours():
                log.info("[FINNIN] 🌙 Quiet hours — skipping"); stats["ignored"] += 1
            else:
                await send_to_whatsapp_single(text, BEAUTY_WA_GROUP, media_bytes)
                stats["beauty_finnin_direct"] += 1
                log.info("[FINNIN] ✅ Sent to Beauty WA")
            return

        if cc:
            stats["deals_found"] += 1
            log.info(f"[CC-DIRECT] 💳 CC Deal #{stats['deals_found']}")
            media_bytes = await download_media_bytes(event.message)
            if is_quiet_hours():
                log.info("[CC-DIRECT] 🌙 Quiet hours — skipping"); stats["ignored"] += 1
            else:
                await send_to_whatsapp_single(text, CC_WA_GROUP, media_bytes)
                stats["cc_sent_direct"] += 1
                log.info("[CC-DIRECT] ✅ Sent to CC WA")
            return
        return

    # ── FASHION DEDICATED SOURCE GROUP ───────────────────────────
    if chat_id == GENERIC_SOURCE_GROUPS:
        if not is_fashion_deal(text):
            return
        log.info("[FASHION-SOURCE] 👗 Fashion deal → ExtraPe")
        media_bytes    = await download_media_bytes(event.message)
        original_links = extract_all_links(text)
        clean_text     = sanitize_text_for_bot(text)
        sent = await client.send_message(EXTRAPE_BOT, clean_text)
        _store_deal(sent.id, media_bytes, original_links,
                    is_cc=False, text=clean_text, deal_type="fashion")
        stats["fashion_sent_to_extrape"] += 1
        log.info(f"[FASHION-SOURCE] 📤 Sent to ExtraPe (msg_id={sent.id})")
        return

    # ── BEAUTY DEDICATED SOURCE GROUP ────────────────────────────
    if chat_id == GENERIC_SOURCE_GROUPS:
        if not is_beauty_deal(text):
            return
        log.info("[BEAUTY-SOURCE] 💄 Beauty deal → ExtraPe")
        media_bytes    = await download_media_bytes(event.message)
        original_links = extract_all_links(text)
        clean_text     = sanitize_text_for_bot(text)
        sent = await client.send_message(EXTRAPE_BOT, clean_text)
        _store_deal(sent.id, media_bytes, original_links,
                    is_cc=False, text=clean_text, deal_type="beauty")
        stats["beauty_sent_to_extrape"] += 1
        log.info(f"[BEAUTY-SOURCE] 📤 Sent to ExtraPe (msg_id={sent.id})")
        return

    # ── GENERIC SOURCE GROUPS (Amazon / FK / CC) ─────────────────
    amz_links = extract_amazon_links(text)
    fk_links  = extract_flipkart_links_source(text)
    cc_deal   = is_cc_deal(text)

    if not amz_links and not fk_links and not cc_deal:
        return

    stats["deals_found"] += 1

    # Source-level dedup
    all_links_in_msg = sorted(extract_all_links(text))
    dedup_key = hash(tuple(all_links_in_msg)) if all_links_in_msg \
        else hash(re.sub(r'\s+', ' ', text.strip().lower()))
    if dedup_key in source_seen_hashes:
        log.info("[SOURCE] ⏭️ Duplicate — skipping"); return
    source_seen_hashes.add(dedup_key)
    if len(source_seen_hashes) > 500:
        source_seen_hashes.pop()

    media_bytes    = await download_media_bytes(event.message)
    original_links = extract_all_links(text)
    clean_text     = sanitize_text_for_bot(text)

    if cc_deal:
        log.info(f"[CC-EXTRAPE] 💳 CC Deal #{stats['deals_found']} → ExtraPe")
        sent = await client.send_message(EXTRAPE_BOT, clean_text)
        _store_deal(sent.id, media_bytes, original_links,
                    is_cc=True, text=clean_text, deal_type="generic")
        stats["sent_to_extrape"] += 1
        return

    link_type = "Amazon" if amz_links else "Flipkart"
    log.info(f"[SOURCE] 🎯 {link_type} Deal #{stats['deals_found']} found!")
    sent = await client.send_message(EXTRAPE_BOT, clean_text)
    _store_deal(sent.id, media_bytes, original_links,
                is_cc=False, text=clean_text, deal_type="generic")
    stats["sent_to_extrape"] += 1
    log.info(f"[EXTRAPE] 📤 Sent to ExtraPe (msg_id={sent.id})")

# ══════════════════════════════════════════
#  STEP 2 — ExtraPe reply → route by deal_type
#
#  FASHION / BEAUTY flows:
#  ┌─ Amazon link  → Dealspouch → (Step 3 handles WA + TG + bulk)
#  ├─ Flipkart link → Fashion/Beauty WA  +  FK WA group
#  └─ Other link   → Fashion/Beauty WA only
#     ExtraPe fail → EarnKaro (all deal types)
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

    # ── ExtraPe failure → EarnKaro (all types) ───────────────────
    if is_extrape_failure(text):
        log.info("[EXTRAPE] ❌ Conversion failed → EarnKaro")
        original_text = None
        if replied_to_id and replied_to_id in sent_original_text:
            original_text = sent_original_text[replied_to_id]
            _cleanup_store(replied_to_id)
        elif sent_original_text:
            oldest = next(iter(sent_original_text))
            original_text = sent_original_text[oldest]
            _cleanup_store(oldest)
        if original_text:
            await client.send_message(EARNKARO_BOT, original_text)
            log.info("[EARNKARO] 📤 Forwarded to EarnKaro")
            stats["ignored"] += 1
        else:
            log.warning("[EARNKARO] ⚠️ No original text found")
        return

    if is_echo_of_sent(text):
        return

    if replied_to_id and replied_to_id in extrape_processed_reply_ids:
        log.info(f"[EXTRAPE] ⏭️ reply_to_id={replied_to_id} already processed")
        stats["ignored"] += 1
        return

    msg_hash = hash(text.strip())
    if msg_hash in extrape_seen_hashes:
        log.info("[EXTRAPE] ⏭️ Exact duplicate — ignored")
        stats["ignored"] += 1
        return
    extrape_seen_hashes.add(msg_hash)
    if len(extrape_seen_hashes) > 50:
        extrape_seen_hashes.pop()

    # Recover media + metadata from store
    media_bytes   = None
    pending_is_cc = False
    deal_type     = "generic"

    if replied_to_id and replied_to_id in pending_media:
        media_bytes   = pending_media[replied_to_id]
        entry         = sent_links_store.get(replied_to_id, {})
        pending_is_cc = entry.get("is_cc", False)
        deal_type     = entry.get("deal_type", "generic")
        _cleanup_store(replied_to_id)
        log.info(
            f"[EXTRAPE] ✅ Matched id={replied_to_id} | "
            f"deal_type={deal_type} | image={'yes' if media_bytes else 'no'}"
        )
    else:
        log.warning("[EXTRAPE] ⚠️ No reply_to match — using ExtraPe's own image if any")

    # Fallback to ExtraPe's own attached image
    if not media_bytes:
        media_bytes = await download_media_bytes(event.message)
        log.info(f"[EXTRAPE] 🖼️ Fallback image: {'yes' if media_bytes else 'no'}")

    ist_now = get_ist_now()

    if replied_to_id:
        extrape_processed_reply_ids.add(replied_to_id)
        if len(extrape_processed_reply_ids) > 100:
            extrape_processed_reply_ids.pop()

    # ════════════════════════════════════════════════════════════
    #  FASHION PIPELINE
    #  Amazon  → Dealspouch queue → Step 3 → Fashion WA + TG + bulk
    #  Flipkart → Fashion WA + FK WA group
    #  Other   → Fashion WA only
    # ════════════════════════════════════════════════════════════
    if deal_type == "fashion":
        wa_group = FASHION_WA_GROUP
        label    = "👗 FASHION"

        if extract_amazon_links(text):
            log.info(f"[{label}] AMZ → Dealspouch queue")
            await _send_to_dealspouch(text, media_bytes, "fashion")
            stats["fashion_sent_to_extrape"] += 1

        elif extract_flipkart_links(text):
            log.info(f"[{label}] FK → Fashion WA + FK WA | image={'yes' if media_bytes else 'no'}")
            if is_quiet_hours():
                log.info(f"[{label}] 🌙 Quiet hours — skipping"); stats["ignored"] += 1
            else:
                await send_to_whatsapp_single(text, wa_group, media_bytes)       # Fashion WA
                await send_to_whatsapp_single(text, FK_WA_GROUP, media_bytes)    # FK WA group
                stats["fashion_sent_direct_wa"] += 1
                stats["fk_sent_to_wa"] += 1

        else:
            # Other platforms (Myntra, Ajio, etc.) — ExtraPe may or may not convert
            log.info(f"[{label}] Other → Fashion WA | image={'yes' if media_bytes else 'no'}")
            if is_quiet_hours():
                log.info(f"[{label}] 🌙 Quiet hours — skipping"); stats["ignored"] += 1
            else:
                await send_to_whatsapp_single(text, wa_group, media_bytes)
                stats["fashion_sent_direct_wa"] += 1
        return

    # ════════════════════════════════════════════════════════════
    #  BEAUTY PIPELINE
    #  Amazon  → Dealspouch queue → Step 3 → Beauty WA + TG + bulk
    #  Flipkart → Beauty WA + FK WA group
    #  Other   → Beauty WA only
    # ════════════════════════════════════════════════════════════
    if deal_type == "beauty":
        wa_group = BEAUTY_WA_GROUP
        label    = "💄 BEAUTY"

        if extract_amazon_links(text):
            log.info(f"[{label}] AMZ → Dealspouch queue")
            await _send_to_dealspouch(text, media_bytes, "beauty")
            stats["beauty_sent_to_extrape"] += 1

        elif extract_flipkart_links(text):
            log.info(f"[{label}] FK → Beauty WA + FK WA | image={'yes' if media_bytes else 'no'}")
            if is_quiet_hours():
                log.info(f"[{label}] 🌙 Quiet hours — skipping"); stats["ignored"] += 1
            else:
                await send_to_whatsapp_single(text, wa_group, media_bytes)       # Beauty WA
                await send_to_whatsapp_single(text, FK_WA_GROUP, media_bytes)    # FK WA group
                stats["beauty_sent_direct_wa"] += 1
                stats["fk_sent_to_wa"] += 1

        else:
            log.info(f"[{label}] Other → Beauty WA | image={'yes' if media_bytes else 'no'}")
            if is_quiet_hours():
                log.info(f"[{label}] 🌙 Quiet hours — skipping"); stats["ignored"] += 1
            else:
                await send_to_whatsapp_single(text, wa_group, media_bytes)
                stats["beauty_sent_direct_wa"] += 1
        return

    # ════════════════════════════════════════════════════════════
    #  GENERIC PIPELINE (unchanged)
    # ════════════════════════════════════════════════════════════
    if pending_is_cc or is_cc_deal(text):
        log.info(f"[EXTRAPE] 💳 CC → CC WA | image={'yes' if media_bytes else 'no'}")
        if is_quiet_hours():
            log.info(f"[WA-SINGLE] 🌙 Quiet hours ({ist_now.strftime('%H:%M')}) — skipping CC")
            stats["ignored"] += 1
        else:
            await send_to_whatsapp_single(text, CC_WA_GROUP, media_bytes)
            stats["cc_sent_via_extrape"] += 1
        return

    if extract_flipkart_links(text):
        log.info(f"[EXTRAPE] 🛒 FK → FK WA | image={'yes' if media_bytes else 'no'}")
        if is_quiet_hours():
            log.info(f"[WA-SINGLE] 🌙 Quiet hours ({ist_now.strftime('%H:%M')}) — skipping FK")
            stats["ignored"] += 1
        else:
            await send_to_whatsapp_single(text, FK_WA_GROUP, media_bytes)
            stats["fk_sent_to_wa"] += 1
        return

    if extract_amazon_links(text):
        log.info(f"[EXTRAPE] ✅ AMZ → Dealspouch | image={'yes' if media_bytes else 'no'}")
        await _send_to_dealspouch(text, media_bytes, "generic")
        stats["amz_sent_to_dealspouch"] += 1
        return

    log.info("[EXTRAPE] ⏭️ No recognisable link — ignored")
    stats["ignored"] += 1

# ══════════════════════════════════════════
#  STEP 3 — Dealspouch reply → route by deal_type
#
#  fashion → Fashion WA  + TG  + main WA bulk
#  beauty  → Beauty WA   + TG  + main WA bulk
#  generic → TG + main WA bulk  (original behaviour)
# ══════════════════════════════════════════
@client.on(events.NewMessage(chats=DEALSPOUCH_BOT))
async def handle_dealspouch(event):
    global last_dealspouch_handled
    text = event.message.text or event.message.caption or ""

    if not has_dealspouch_link(text):
        stats["ignored"] += 1
        log.info("[DEALSPOUCH] ⏭️ No dealspouch link — ignored")
        return

    now = time.time()
    if now - last_dealspouch_handled < DEALSPOUCH_COOLDOWN:
        stats["ignored"] += 1
        log.info("[DEALSPOUCH] ⏭️ Cooldown — duplicate ignored")
        return
    last_dealspouch_handled = now

    # Pop oldest entry
    if not dealspouch_queue:
        log.warning("[DEALSPOUCH] ⚠️ Queue empty — text-only generic fallback")
        media_bytes = None
        deal_type   = "generic"
        age_minutes = 0.0
    else:
        media_bytes, deal_type, ts = dealspouch_queue.popleft()
        age_minutes = (time.time() - ts) / 60
        log.info(
            f"[DEALSPOUCH] ✅ Popped | deal_type={deal_type} | "
            f"image={'yes' if media_bytes else 'no'} | "
            f"age={age_minutes:.1f} min | remaining={len(dealspouch_queue)}"
        )

    # Freshness check
    if age_minutes > MAX_DEAL_AGE_MINUTES:
        log.info(f"[FRESHNESS] 🗑️ Stale ({age_minutes:.1f} min) → DROPPED")
        stats["stale_dropped"] += 1
        return

    ist_now = get_ist_now()
    log.info(f"[DEALSPOUCH] ✅ Fresh | IST: {ist_now.strftime('%H:%M')} | deal_type={deal_type}")

    # ── Pick the specialty WA group (fashion / beauty) ──────────
    specialty_wa = None
    if deal_type == "fashion":
        specialty_wa = FASHION_WA_GROUP
        log.info(f"[FASHION-DEALSPOUCH] 👗 Will send to Fashion WA + TG + bulk")
    elif deal_type == "beauty":
        specialty_wa = BEAUTY_WA_GROUP
        log.info(f"[BEAUTY-DEALSPOUCH] 💄 Will send to Beauty WA + TG + bulk")

    # ── Specialty WA first (fashion / beauty) ───────────────────
    if specialty_wa:
        if is_quiet_hours():
            log.info(f"[DEALSPOUCH] 🌙 Quiet hours — skipping specialty WA send")
            stats["ignored"] += 1
        else:
            await send_to_whatsapp_single(text, specialty_wa, media_bytes)
            if deal_type == "fashion":
                stats["fashion_sent_direct_wa"] += 1
            else:
                stats["beauty_sent_direct_wa"] += 1

    # ── Lucky deal link swap (generic only — keeps specialty WA clean) ──
    tg_text = text
    if deal_type == "generic" and _is_lucky_deal():
        tg_text = re.sub(r'https?://amaz\.dealspouch\.com/\S+', WA_INVITE_LINK, tg_text)
        log.info("[DAILY] 🎯 Lucky deal — replaced dealspouch link with WA invite")

    tg_text = tg_text + TG_BOT_FOOTER

    # ── Post to Telegram (all types) ────────────────────────────
    try:
        if media_bytes:
            await client.send_file(MY_TG_GROUP, media_bytes, caption=tg_text)
        else:
            await client.send_message(MY_TG_GROUP, tg_text)
        stats["posted_to_tg"] += 1
        log.info(f"[TG] ✅ Posted to {MY_TG_GROUP}")
    except Exception as e:
        log.error(f"[TG] ❌ Failed: {e}")

    # ── Main WA bulk (all types, respects quiet hours) ──────────
    if is_quiet_hours():
        log.info(f"[WA-BULK] 🌙 Quiet hours ({ist_now.strftime('%H:%M')}) — skipping bulk")
    else:
        await send_to_whatsapp_bulk(tg_text, media_bytes)

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
            log.info(f"💳 CC / Finnin Group  : {CC_DIRECT_GROUP}")
            # log.info(f"👗 Fashion Source     : {FASHION_SOURCE_GROUP}")
            # log.info(f"💄 Beauty Source      : {BEAUTY_SOURCE_GROUP}")
            log.info(f"🤖 ExtraPe Bot        : {EXTRAPE_BOT}")
            log.info(f"🤖 EarnKaro Bot       : {EARNKARO_BOT}")
            log.info(f"🤖 Dealspouch Bot     : {DEALSPOUCH_BOT}")
            log.info(f"📢 TG Group           : {MY_TG_GROUP}")
            log.info(f"📲 FK WA Group        : {FK_WA_GROUP}")
            log.info(f"📲 CC WA Group        : {CC_WA_GROUP}")
            log.info(f"📲 Fashion WA Group   : {FASHION_WA_GROUP}")
            log.info(f"📲 Beauty WA Group    : {BEAUTY_WA_GROUP}")
            log.info(f"📲 WA Sender          : {BAILEYS_URL or 'NOT SET'}")
            log.info(f"⏱️  Freshness limit    : {MAX_DEAL_AGE_MINUTES} min")
            log.info(f"🎯 Lucky deals / day  : {LUCKY_DEALS_PER_DAY}")
            log.info("─" * 55)
            log.info("FASHION / BEAUTY FLOWS:")
            log.info("  Amazon  → ExtraPe → Dealspouch → WA + TG + bulk")
            log.info("  Flipkart → ExtraPe → Fashion/Beauty WA + FK WA")
            log.info("  Other   → ExtraPe → Fashion/Beauty WA only")
            log.info("  Fail    → EarnKaro")
            log.info("─" * 55)
            log.info("⏳ Waiting for deals...\n")
            await client.run_until_disconnected()
        except Exception as e:
            log.error(f"Disconnected: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

asyncio.run(run())
