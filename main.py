from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import (
    MessageMediaPhoto,
    MessageMediaDocument,
    MessageEntityTextUrl,
    MessageEntityStrike,
    MessageEntityBold,
    MessageEntityItalic,
    MessageEntityCode,
)
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import asyncio, re, io, logging, time, aiohttp, os, threading, pytz, collections, random, json, itertools

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

CC_DIRECT_GROUP = -1001481951196

# Fashion/beauty are detected from the SAME source groups — no separate group needed
SOURCE_GROUPS = [
    -1001493857075,
    -1001412868909,
    -1001389782464,
    CC_DIRECT_GROUP,
]

# ══════════════════════════════════════════
#  FRESHNESS CHECK
#  Unified queue entry = (media_bytes, deal_type, timestamp)
# ══════════════════════════════════════════
MAX_DEAL_AGE_MINUTES = 10
dealspouch_queue = collections.deque()

# Pending mapping window for ExtraPe replies.
PENDING_STORE_MAX = 200
PENDING_TTL_SECONDS = 30 * 60

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
    if not text: return False
    if CC_FALSE_POSITIVE.search(text): return False
    if CC_STRONG_KEYWORDS.search(text): return True
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
    r"indo-?western|men(?:['’]?s)? fashion|women(?:['’]?s)? fashion|womens?|mens?|kids? fashion|"
    r'apparel|garment|clothing)\b',
    re.IGNORECASE
)

def is_fashion_deal(text: str) -> bool:
    return bool(text) and bool(FASHION_KEYWORDS.search(_normalize_category_text(text)))

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
    return bool(text) and bool(BEAUTY_KEYWORDS.search(_normalize_category_text(text)))

def classify_special_deal(text: str) -> str:
    if is_fashion_deal(text):
        return "fashion"
    if is_beauty_deal(text):
        return "beauty"
    return "generic"

# ══════════════════════════════════════════
#  PRICE-ALERT POST DETECTION  ← NEW
#
#  These come from the Dealspouch price-alert bot and land directly
#  in the Telegram group. Signature:
#    • photo attached
#    • CTA "Read the full deal" (a hyperlink ENTITY, not inline text)
#    • price line: ₹new ₹old (NN% off)
#    • dealspouch.com URL hidden inside the CTA entity
#
#  These skip ExtraPe / Dealspouch entirely and go straight to the
#  main WhatsApp bulk endpoint.
# ══════════════════════════════════════════
PRICE_ALERT_TG_GROUP = MY_TG_GROUP          # "@finnindeals2"

PRICE_ALERT_CTA = re.compile(r'read the full (?:deal|blog)|shop now', re.IGNORECASE)
PRICE_ALERT_PRICE = re.compile(
    r'₹\s*[\d,]+(?:\.\d+)?\s*₹\s*[\d,]+(?:\.\d+)?[^\n]{0,25}?\(\s*\d{1,3}\s*%\s*off\s*\)',
    re.IGNORECASE
)
PRICE_ALERT_LINK = re.compile(r'https?://(?:www\.)?dealspouch\.com/\S+', re.IGNORECASE)

# Our own reposts into @finnindeals2 carry the footer — never re-ingest them
OUR_REPOST_MARKERS = ("t.me/Dealspouch_Product_bot", "dealspouch.com/price-alert")

price_alert_seen = set()

def extract_entity_urls(message):
    """Pull hidden URLs out of hyperlink entities — raw_text does NOT contain them."""
    urls = []
    for ent in (message.entities or []):
        if isinstance(ent, MessageEntityTextUrl) and ent.url:
            urls.append(ent.url)
    return urls

# ── Telegram formatting → WhatsApp markdown ──────────────────────
#  Telegram carries the MRP strikethrough as a MessageEntityStrike;
#  raw_text throws that away, so ₹1,499.00 arrives on WhatsApp plain.
#  WhatsApp renders ~text~ as strikethrough, *bold*, _italic_.
#
#  Telegram entity offsets are in UTF-16 code units, NOT Python
#  characters — an emoji counts as 2. Every offset here is worked
#  in UTF-16 units or the markers land in the wrong place.
_WA_MARKERS = {
    MessageEntityStrike: "~",
    MessageEntityBold:   "*",
    MessageEntityItalic: "_",
    MessageEntityCode:   "```",
}
_U16_SPACE = " ".encode("utf-16-le")

def _tg_entities_to_whatsapp(message) -> str:
    text = (message.raw_text or message.text or "").strip()
    if not text:
        return ""
    ents = [e for e in (message.entities or []) if type(e) in _WA_MARKERS]
    if not ents:
        return text

    data  = text.encode("utf-16-le")
    units = [data[i:i + 2] for i in range(0, len(data), 2)]
    inserts = collections.defaultdict(list)

    for e in ents:
        mark  = _WA_MARKERS[type(e)]
        start = max(0, e.offset)
        end   = min(len(units), e.offset + e.length)
        # WhatsApp will not render a span padded with spaces — tighten it
        while start < end and units[start] == _U16_SPACE:
            start += 1
        while end > start and units[end - 1] == _U16_SPACE:
            end -= 1
        if end <= start:
            continue
        inserts[start].append(("open", mark))
        inserts[end].append(("close", mark))

    out = []
    for i in range(len(units) + 1):
        if i in inserts:
            # close before open so nested spans don't cross
            for _, mark in sorted(inserts[i], key=lambda x: 0 if x[0] == "close" else 1):
                out.append(mark.encode("utf-16-le"))
        if i < len(units):
            out.append(units[i])

    formatted = b"".join(out).decode("utf-16-le")
    log.info(f"[PRICE-ALERT] ✏️ Applied {len(ents)} formatting entity(ies) for WhatsApp")
    return formatted

def is_price_alert_post(message, text: str) -> bool:
    if not text:
        return False
    if any(m in text for m in OUR_REPOST_MARKERS):
        return False                                   # our own repost — ignore
    blob      = text + " " + " ".join(extract_entity_urls(message))
    has_cta   = bool(PRICE_ALERT_CTA.search(blob))
    has_price = bool(PRICE_ALERT_PRICE.search(blob))
    has_link  = bool(PRICE_ALERT_LINK.search(blob))
    return (has_cta and (has_price or has_link)) or (has_price and has_link)

def build_price_alert_text(message) -> str:
    """WhatsApp-formatted body + any URL that only existed as a hyperlink entity."""
    body = _tg_entities_to_whatsapp(message)
    for u in extract_entity_urls(message):
        if u not in body:
            body += f"\n👉 {u}"
    return body

# Dealspouch alerts sometimes carry an explicit "📁 Category: ..." line —
# that is the most reliable signal. Otherwise fall back to the product
# TITLE line only. Never classify on the whole body: the CTA, footer and
# price lines drag in false hits ("Top", "Watch", "Plum", "Beauty" etc).
PRICE_ALERT_CATEGORY_LINE = re.compile(r'category\s*[:\-]\s*(.+)', re.IGNORECASE)

def price_alert_category(text: str) -> str:
    """Return 'fashion' | 'beauty' | 'generic' for a price-alert post."""
    if not text:
        return "generic"

    m = PRICE_ALERT_CATEGORY_LINE.search(text)
    if m:
        cat = classify_special_deal(m.group(1).strip())
        log.info(f"[PRICE-ALERT] 📁 Category line found → {cat}")
        if cat != "generic":
            return cat

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if PRICE_ALERT_CTA.search(line) or line.startswith("₹") or line.startswith("http"):
            continue
        cat = classify_special_deal(line)          # title line only
        log.info(f"[PRICE-ALERT] 🏷️ Title classify → {cat} | {line[:70]}")
        return cat

    return "generic"

# ══════════════════════════════════════════
#  IST HELPERS
# ══════════════════════════════════════════
def get_ist_now():
    return datetime.now(pytz.timezone("Asia/Kolkata"))

_quiet_open_date   = None
_quiet_open_minute = 7 * 60
QUIET_CLOSE_MINUTE = 30             # fallback default: 12:30 AM

def _get_daily_open_minute():
    """Pick a random wake-up time between 7:00–8:00 AM IST, once per day."""
    global _quiet_open_date, _quiet_open_minute
    today = get_ist_now().date()
    if _quiet_open_date != today:
        _quiet_open_date   = today
        _quiet_open_minute = random.randint(7 * 60, 8 * 60)
        log.info(
            f"[QUIET] 🌅 Today's wake-up time: "
            f"{_quiet_open_minute // 60:02d}:{_quiet_open_minute % 60:02d} IST"
        )
    return _quiet_open_minute

def is_quiet_hours():
    now = get_ist_now()
    m = now.hour * 60 + now.minute
    open_minute = _get_daily_open_minute()
    return QUIET_CLOSE_MINUTE <= m < open_minute   # closes sharp 12:30 AM, opens 7:00–8:00 AM (random daily)

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
    "price_alert_sent": 0, "price_alert_fashion": 0, "price_alert_beauty": 0,   # ← NEW
}

# ══════════════════════════════════════════
#  DAILY LUCKY DEAL COUNTER
# ══════════════════════════════════════════
# Temporarily OFF, per your request. This doesn't delete the feature —
# it just gates it behind an env var, so turning it back on later is a
# Railway dashboard change (set LUCKY_DEALS_ENABLED=1), not a code push.
# Default here is "0" (off) so it stays off until you flip it.
LUCKY_DEALS_ENABLED = os.environ.get("LUCKY_DEALS_ENABLED", "0") == "1"

LUCKY_DEALS_PER_DAY = 18
_daily_counter_date = None
_daily_deal_count   = 0
_lucky_deal_slots   = set()

# ── Lucky links: 3 different links, each appears 6 times (6+6+6=18 per day) ──
LUCKY_DEAL_LINKS    = [
    "https://tinyurl.com/z95n7px4",      # Link 1
    "https://tinyurl.com/yu75d4sc",      # Link 2
    "https://tinyurl.com/3f5wun5n"       # Link 3
]
_lucky_link_pool    = []               # Pool of randomized links (6 of each)
_lucky_link_index   = 0                # Current position in pool
WA_INVITE_LINK      = "https://tinyurl.com/fhknr97k"
CC_WA_FOOTER = "\n\nFor More Such Credit Card Deals Visit - https://www.dealspouch.com/finance"
TG_BOT_FOOTER = (
    # "\n\n🔔 Price Tracker - https://www.dealspouch.com/price-alert"
    # "\n🌐 Dealspouch Website - https://www.dealspouch.com/"
    # "\n🤖 Telegram Bot - https://t.me/Dealspouch_Product_bot"
)

def _refresh_daily_counter():
    global _daily_counter_date, _daily_deal_count, _lucky_deal_slots, _lucky_link_pool, _lucky_link_index
    today = get_ist_now().date()
    if _daily_counter_date != today:
        _daily_counter_date = today
        _daily_deal_count   = 0
        _lucky_deal_slots   = set(random.sample(range(1, 61), LUCKY_DEALS_PER_DAY))
        # ── Randomize link pool: each link 6 times, shuffled ──
        _lucky_link_pool = LUCKY_DEAL_LINKS * 6
        random.shuffle(_lucky_link_pool)
        _lucky_link_index = 0
        log.info(f"[DAILY] 🗓️ New day {today} — lucky slots: {sorted(_lucky_deal_slots)} | link pool randomized")

def _is_lucky_deal() -> bool:
    global _daily_deal_count
    _refresh_daily_counter()
    _daily_deal_count += 1
    lucky = _daily_deal_count in _lucky_deal_slots
    log.info(f"[DAILY] Deal #{_daily_deal_count} today | lucky={lucky}")
    return lucky

def _get_lucky_link() -> str:
    """Get next random lucky link (each link appears 6 times but in random order)."""
    global _lucky_link_index, _lucky_link_pool
    _refresh_daily_counter()
    if not _lucky_link_pool or _lucky_link_index >= len(_lucky_link_pool):
        _lucky_link_pool = LUCKY_DEAL_LINKS * 6
        random.shuffle(_lucky_link_pool)
        _lucky_link_index = 0
    link = _lucky_link_pool[_lucky_link_index]
    _lucky_link_index += 1
    return link

# ══════════════════════════════════════════
#  SHARED STATE
# ══════════════════════════════════════════
pending_media      = {}   # msg_id → image bytes
sent_links_store   = {}   # msg_id → {links, is_cc, deal_type}
sent_original_text = {}   # msg_id → original text

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
    if not text:
        return False
    lowered = text.lower()
    return (
        "dealspouch" in lowered
        or "amaz.dealspouch.com" in lowered
        or "www.dealspouch.com" in lowered
    )

def is_extrape_failure(text):
    if not text:
        return False
    lowered = text.lower()
    failure_markers = (
        "will not be able to convert",
        "unable to convert",
        "cannot convert",
        "can't convert",
        "conversion failed",
        "failed to convert",
        "not supported",
        "invalid link",
    )
    return any(marker in lowered for marker in failure_markers)

def _normalize_text(text: str) -> str:
    return re.sub(r'\s+', ' ', (text or '').strip().lower())

def _normalize_category_text(text: str) -> str:
    if not text:
        return ""
    normalized = text.lower()
    normalized = normalized.replace("’", "'").replace("‘", "'")
    normalized = normalized.replace("–", "-").replace("—", "-")
    return re.sub(r'\s+', ' ', normalized).strip()

def _trace(stage: str, **fields):
    compact = " | ".join(f"{k}={v}" for k, v in fields.items())
    log.info(f"[TRACE:{stage}] {compact}")

def is_echo_of_sent(text):
    if not sent_original_text:
        return False
    norm_reply = _normalize_text(text)
    if not norm_reply:
        return False
    for original in sent_original_text.values():
        if _normalize_text(original) == norm_reply:
            log.info("[EXTRAPE] 🔄 Exact echo of our source message — waiting for converted reply")
            return True
    return False

def _cleanup_store(msg_id):
    pending_media.pop(msg_id, None)
    sent_links_store.pop(msg_id, None)
    sent_original_text.pop(msg_id, None)

def _purge_old_pending_store():
    now = time.time()
    stale_ids = []
    for msg_id, entry in sent_links_store.items():
        created_at = entry.get("created_at", now)
        if now - created_at > PENDING_TTL_SECONDS:
            stale_ids.append(msg_id)
    for msg_id in stale_ids:
        _cleanup_store(msg_id)
    if stale_ids:
        log.info(f"[STORE] 🧹 Purged {len(stale_ids)} stale pending mappings")

def _match_pending_by_links(reply_text: str):
    reply_links = extract_all_links(reply_text)
    if not reply_links:
        return None

    best_id = None
    best_score = (-1, -1.0)
    for msg_id, entry in sent_links_store.items():
        original_links = entry.get("links") or set()
        overlap_count = len(reply_links & original_links)
        if overlap_count <= 0:
            continue
        created_at = float(entry.get("created_at", 0.0))
        score = (overlap_count, created_at)
        if score > best_score:
            best_score = score
            best_id = msg_id

    return best_id

def _store_deal(msg_id, media_bytes, links, is_cc, text, deal_type="generic"):
    _purge_old_pending_store()
    pending_media[msg_id]      = media_bytes
    sent_links_store[msg_id]   = {
        "links": links,
        "is_cc": is_cc,
        "deal_type": deal_type,
        "created_at": time.time(),
    }
    sent_original_text[msg_id] = text
    if len(sent_links_store) > PENDING_STORE_MAX:
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
#  PRODUCT IMAGE FETCH (fallback when no image was captured)
# ══════════════════════════════════════════
_IMG_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

async def fetch_product_image_bytes(link: str) -> bytes | None:
    """
    Follow a (possibly shortened) product link to its landing page and scrape
    the main product image, then download it as bytes. Used as a fallback when
    the source post itself had no photo attached.
    """
    if not link:
        return None
    try:
        async with aiohttp.ClientSession(headers=_IMG_FETCH_HEADERS) as session:
            async with session.get(
                link, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=12)
            ) as resp:
                if resp.status != 200:
                    log.warning(f"[IMG-FETCH] ⚠️ Landing page HTTP {resp.status} for {link}")
                    return None
                html = await resp.text(errors="ignore")

            img_url = None

            # 1) Amazon: data-a-dynamic-image carries a JSON map of {url: [w,h]} — pick highest-res
            m = re.search(r'data-a-dynamic-image="([^"]+)"', html)
            if m:
                try:
                    raw = m.group(1).replace("&quot;", '"')
                    data = json.loads(raw)
                    if data:
                        img_url = max(
                            data.items(),
                            key=lambda kv: (kv[1][0] * kv[1][1]) if isinstance(kv[1], list) and len(kv[1]) == 2 else 0
                        )[0]
                except Exception:
                    img_url = None

            # 2) Amazon: hiRes field in inline JSON
            if not img_url:
                m = re.search(r'"hiRes":"(https[^"]+?)"', html)
                if m:
                    img_url = m.group(1).replace("\\/", "/")

            # 3) Generic: og:image meta tag (works for Amazon, Flipkart, most sites)
            if not img_url:
                m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
                if m:
                    img_url = m.group(1)

            if not img_url:
                log.info(f"[IMG-FETCH] ❌ No image found on landing page for {link}")
                return None

            async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=12)) as img_resp:
                if img_resp.status == 200:
                    data = await img_resp.read()
                    if data and len(data) > 500:
                        return data
    except Exception as e:
        log.warning(f"[IMG-FETCH] ⚠️ Failed to fetch product image from {link}: {e}")
    return None

# ══════════════════════════════════════════
#  WHATSAPP SEND QUEUE (anti-detection + freshness-priority)
#  WhatsApp flags accounts that fire many messages in quick
#  succession, so every send goes through one background worker
#  with a randomized human-like gap between sends.
#  IMPORTANT: this is a PRIORITY queue, not FIFO — whenever the
#  worker is ready to send, it always picks the MOST RECENTLY
#  QUEUED job first. The backlog can grow as large as needed;
#  older jobs simply wait longer while fresh ones keep cutting in.
#  Jobs that age past WA_QUEUE_MAX_AGE_MINUTES are dropped instead
#  of sent — a deal that's sat 20+ minutes is stale/likely gone,
#  so sending it late does more harm than skipping it.
# ══════════════════════════════════════════
WA_MIN_GAP_SECONDS      = int(os.environ.get("WA_MIN_GAP_SECONDS", 8))
WA_MAX_GAP_SECONDS      = int(os.environ.get("WA_MAX_GAP_SECONDS", 20))
WA_QUEUE_MAX_AGE_MINUTES = int(os.environ.get("WA_QUEUE_MAX_AGE_MINUTES", 15))

_wa_hour_window_start = time.time()
_wa_hour_count        = 0
WA_MAX_PER_HOUR       = int(os.environ.get("WA_MAX_PER_HOUR", 60))

_wa_seq_counter    = itertools.count()
_wa_priority_queue: "asyncio.PriorityQueue" = None   # created lazily inside the running loop
_wa_worker_started = False
_wa_last_send_time = 0.0

def _wa_hourly_cap_ok() -> bool:
    """Soft safety valve — drop sends past the hourly cap rather than risk a ban spike."""
    global _wa_hour_window_start, _wa_hour_count
    now = time.time()
    if now - _wa_hour_window_start > 3600:
        _wa_hour_window_start = now
        _wa_hour_count = 0
    if _wa_hour_count >= WA_MAX_PER_HOUR:
        log.warning(f"[WA-QUEUE] 🛑 Hourly cap ({WA_MAX_PER_HOUR}) reached — dropping this send")
        return False
    _wa_hour_count += 1
    return True

async def _wa_sender_worker():
    """Runs forever. Always pulls the newest queued job first (priority = -sequence)."""
    global _wa_last_send_time
    while True:
        neg_seq, queued_at, job = await _wa_priority_queue.get()
        backlog = _wa_priority_queue.qsize()

        age_minutes = (time.time() - queued_at) / 60
        if age_minutes > WA_QUEUE_MAX_AGE_MINUTES:
            log.info(
                f"[WA-QUEUE] 🗑️ Dropping stale job (seq={-neg_seq}, "
                f"waited {age_minutes:.1f} min > {WA_QUEUE_MAX_AGE_MINUTES} min cap)"
            )
            _wa_priority_queue.task_done()
            continue

        if backlog:
            log.info(f"[WA-QUEUE] 📬 Sending newest job (seq={-neg_seq}) — {backlog} older job(s) still waiting")

        now = time.time()
        remaining = WA_MIN_GAP_SECONDS - (now - _wa_last_send_time)
        jitter = random.uniform(0, max(0, WA_MAX_GAP_SECONDS - WA_MIN_GAP_SECONDS))
        delay = max(0.0, remaining) + jitter
        if delay > 0:
            await asyncio.sleep(delay)
        _wa_last_send_time = time.time()

        try:
            await job()
        except Exception as e:
            log.error(f"[WA-QUEUE] ❌ Job failed: {e}")
        finally:
            _wa_priority_queue.task_done()

def _ensure_wa_worker_started():
    global _wa_priority_queue, _wa_worker_started
    if _wa_priority_queue is None:
        _wa_priority_queue = asyncio.PriorityQueue()
    if not _wa_worker_started:
        _wa_worker_started = True
        asyncio.create_task(_wa_sender_worker())
        log.info("[WA-QUEUE] 🚀 Background sender worker started")

async def _enqueue_wa_job(job):
    """Push a send job in; it jumps ahead of anything already waiting."""
    _ensure_wa_worker_started()
    seq = next(_wa_seq_counter)
    await _wa_priority_queue.put((-seq, time.time(), job))
    log.info(f"[WA-QUEUE] 📥 Job queued (seq={seq}) | backlog={_wa_priority_queue.qsize()}")

# ══════════════════════════════════════════
#  WHATSAPP SENDERS
# ══════════════════════════════════════════
async def send_to_whatsapp_bulk(text, image_bytes=None):
    if not BAILEYS_URL:
        log.warning("[WA-BULK] BAILEYS_URL not set!"); return
    if not _wa_hourly_cap_ok():
        return

    async def _job():
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
                        if r.status != 200:
                            log.error(f"[WA-BULK] ❌ HTTP {r.status} {body[:120]}"); return
                        log.info(f"[WA-BULK] ✅ Queued! {body[:80]}")
                else:
                    async with session.post(f"{BAILEYS_URL}/send",
                                            json={"text": text, "secret": BAILEYS_SECRET},
                                            timeout=aiohttp.ClientTimeout(total=30)) as r:
                        body = await r.text()
                        if r.status != 200:
                            log.error(f"[WA-BULK] ❌ HTTP {r.status} {body[:120]}"); return
                        log.info(f"[WA-BULK] ✅ Queued! {body[:80]}")
            stats["sent_to_wa_bulk"] += 1
        except Exception as e:
            log.error(f"[WA-BULK] ❌ Failed: {e}")

    await _enqueue_wa_job(_job)

async def send_to_whatsapp_single(text, target_group, image_bytes=None):
    if not BAILEYS_URL:
        log.warning("[WA-SINGLE] BAILEYS_URL not set!"); return
    if not _wa_hourly_cap_ok():
        return

    async def _job():
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
                        if r.status != 200:
                            log.error(f"[WA-SINGLE] ❌ HTTP {r.status} {body[:120]}"); return
                        log.info(f"[WA-SINGLE] ✅ Sent to {target_group}! {body[:80]}")
                else:
                    async with session.post(f"{BAILEYS_URL}/send-single",
                                            json={"text": text, "secret": BAILEYS_SECRET, "target": target_group},
                                            timeout=aiohttp.ClientTimeout(total=30)) as r:
                        body = await r.text()
                        if r.status != 200:
                            log.error(f"[WA-SINGLE] ❌ HTTP {r.status} {body[:120]}"); return
                        log.info(f"[WA-SINGLE] ✅ Sent to {target_group}! {body[:80]}")
        except Exception as e:
            log.error(f"[WA-SINGLE] ❌ Failed: {e}")

    await _enqueue_wa_job(_job)

# ══════════════════════════════════════════
#  PUSH TO DEALSPOUCH QUEUE
# ══════════════════════════════════════════
async def _send_to_dealspouch(text, media_bytes, deal_type):
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
#  PRICE-ALERT DISPATCH  ← NEW
#  Straight to the main WhatsApp bulk endpoint only.
#  No ExtraPe, no Dealspouch, no TG repost, no category groups.
# ══════════════════════════════════════════
async def _dispatch_price_alert(message):
    text = build_price_alert_text(message)

    # Dedup — the same alert can reach us twice (edit / re-forward)
    key = hash(_normalize_text(text))
    if key in price_alert_seen:
        log.info("[PRICE-ALERT] ⏭️ Duplicate — skipping")
        _trace("PRICE-ALERT", action="duplicate")
        return
    price_alert_seen.add(key)
    if len(price_alert_seen) > 300:
        price_alert_seen.pop()

    media_bytes = await download_media_bytes(message)
    if not media_bytes:
        link = next(iter(extract_entity_urls(message)), None) \
               or next(iter(extract_all_links(text)), None)
        if link:
            log.info("[PRICE-ALERT] 🔎 No photo attached — scraping product image")
            media_bytes = await fetch_product_image_bytes(link)

    if is_quiet_hours():
        log.info("[PRICE-ALERT] 🌙 Quiet hours — skipping")
        stats["ignored"] += 1
        _trace("PRICE-ALERT", action="skipped_quiet")
        return

    log.info(f"[PRICE-ALERT] 📣 → WA bulk | image={'yes' if media_bytes else 'no'}")
    await send_to_whatsapp_bulk(text, media_bytes)
    stats["price_alert_sent"] += 1
    _trace("PRICE-ALERT", action="wa_bulk", image="yes" if media_bytes else "no")

    # ── Category add-on: fashion / beauty products also go to their group ──
    category = price_alert_category(text)
    if category == "fashion":
        log.info("[PRICE-ALERT] 👗 Fashion product → Fashion WA too")
        await send_to_whatsapp_single(text, FASHION_WA_GROUP, media_bytes)
        stats["price_alert_fashion"] += 1
        _trace("PRICE-ALERT", action="wa_single", target=FASHION_WA_GROUP, category=category)
    elif category == "beauty":
        log.info("[PRICE-ALERT] 💄 Beauty product → Beauty WA too")
        await send_to_whatsapp_single(text, BEAUTY_WA_GROUP, media_bytes)
        stats["price_alert_beauty"] += 1
        _trace("PRICE-ALERT", action="wa_single", target=BEAUTY_WA_GROUP, category=category)
    else:
        log.info("[PRICE-ALERT] 📦 Generic product → bulk only")

# ══════════════════════════════════════════
#  STEP 1 — Source groups → detect & dispatch
#
#  Priority order inside each message:
#  0. Price-alert post → WA bulk direct (no ExtraPe/Dealspouch)   ← NEW
#  1. CC deal          → ExtraPe (deal_type=generic, is_cc=True)
#  2. Fashion deal     → ExtraPe (deal_type=fashion)
#  3. Beauty deal      → ExtraPe (deal_type=beauty)
#  4. Amazon/FK        → ExtraPe (deal_type=generic)
#
#  CC_DIRECT_GROUP: fashion/beauty go direct to WA (no ExtraPe)
#                   CC goes direct to CC WA (no ExtraPe)
# ══════════════════════════════════════════
@client.on(events.NewMessage(chats=SOURCE_GROUPS))
async def handle_source(event):
    if event.message.edit_date:
        return

    text    = event.message.text or event.message.caption or ""
    chat_id = event.chat_id

    # ── CC_DIRECT_GROUP (Finnin): direct sends, no ExtraPe ───────
    if chat_id == CC_DIRECT_GROUP:
        # Price-alert post lands here too (screenshot chat = -1001481951196)
        if is_price_alert_post(event.message, text):
            log.info("[PRICE-ALERT] 🔔 Detected in Finnin Deals → WA bulk")
            await _dispatch_price_alert(event.message)
            return

        cc      = is_cc_deal(text)
        fashion = is_fashion_deal(text) and not cc
        beauty  = is_beauty_deal(text) and not cc

        if fashion:
            log.info("[FINNIN] 👗 Fashion → Fashion WA direct")
            media_bytes = await download_media_bytes(event.message)
            if is_quiet_hours():
                log.info("[FINNIN] 🌙 Quiet hours — skipping"); stats["ignored"] += 1
                _trace("SOURCE", route="finnin_fashion", action="skipped_quiet", chat=chat_id)
            else:
                await send_to_whatsapp_single(text, FASHION_WA_GROUP, media_bytes)
                stats["fashion_finnin_direct"] += 1
                log.info("[FINNIN] ✅ Sent to Fashion WA")
                _trace("SOURCE", route="finnin_fashion", action="wa_single", target=FASHION_WA_GROUP, chat=chat_id)
            return

        if beauty:
            log.info("[FINNIN] 💄 Beauty → Beauty WA direct")
            media_bytes = await download_media_bytes(event.message)
            if is_quiet_hours():
                log.info("[FINNIN] 🌙 Quiet hours — skipping"); stats["ignored"] += 1
                _trace("SOURCE", route="finnin_beauty", action="skipped_quiet", chat=chat_id)
            else:
                await send_to_whatsapp_single(text, BEAUTY_WA_GROUP, media_bytes)
                stats["beauty_finnin_direct"] += 1
                log.info("[FINNIN] ✅ Sent to Beauty WA")
                _trace("SOURCE", route="finnin_beauty", action="wa_single", target=BEAUTY_WA_GROUP, chat=chat_id)
            return

        if cc:
            stats["deals_found"] += 1
            log.info(f"[CC-DIRECT] 💳 CC Deal #{stats['deals_found']}")
            media_bytes = await download_media_bytes(event.message)
            if is_quiet_hours():
                log.info("[CC-DIRECT] 🌙 Quiet hours — skipping"); stats["ignored"] += 1
                _trace("SOURCE", route="finnin_cc", action="skipped_quiet", chat=chat_id)
            else:
                await send_to_whatsapp_single(text + CC_WA_FOOTER, CC_WA_GROUP, media_bytes)
                stats["cc_sent_direct"] += 1
                log.info("[CC-DIRECT] ✅ Sent to CC WA")
                _trace("SOURCE", route="finnin_cc", action="wa_single", target=CC_WA_GROUP, chat=chat_id)
            return
        return

    # ── ALL OTHER SOURCE GROUPS ───────────────────────────────────
    amz_links = extract_amazon_links(text)
    fk_links  = extract_flipkart_links_source(text)
    cc_deal   = is_cc_deal(text)
    fashion   = is_fashion_deal(text) and not cc_deal
    beauty    = is_beauty_deal(text) and not cc_deal

    if not amz_links and not fk_links and not cc_deal and not fashion and not beauty:
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

    # Priority 1: CC
    if cc_deal:
        log.info(f"[CC-EXTRAPE] 💳 CC Deal #{stats['deals_found']} → ExtraPe")
        sent = await client.send_message(EXTRAPE_BOT, clean_text)
        _store_deal(sent.id, media_bytes, original_links,
                    is_cc=True, text=clean_text, deal_type="generic")
        stats["sent_to_extrape"] += 1
        log.info(f"[CC-EXTRAPE] 📤 Sent to ExtraPe (msg_id={sent.id})")
        _trace("SOURCE", route="cc_to_extrape", action="dispatch", msg_id=sent.id, chat=chat_id)
        return

    # Priority 2: Fashion
    if fashion:
        log.info(f"[FASHION-SOURCE] 👗 Fashion Deal #{stats['deals_found']} → ExtraPe")
        sent = await client.send_message(EXTRAPE_BOT, clean_text)
        _store_deal(sent.id, media_bytes, original_links,
                    is_cc=False, text=clean_text, deal_type="fashion")
        stats["fashion_sent_to_extrape"] += 1
        log.info(f"[FASHION-SOURCE] 📤 Sent to ExtraPe (msg_id={sent.id})")
        _trace("SOURCE", route="fashion_to_extrape", action="dispatch", msg_id=sent.id, chat=chat_id)
        return

    # Priority 3: Beauty
    if beauty:
        log.info(f"[BEAUTY-SOURCE] 💄 Beauty Deal #{stats['deals_found']} → ExtraPe")
        sent = await client.send_message(EXTRAPE_BOT, clean_text)
        _store_deal(sent.id, media_bytes, original_links,
                    is_cc=False, text=clean_text, deal_type="beauty")
        stats["beauty_sent_to_extrape"] += 1
        log.info(f"[BEAUTY-SOURCE] 📤 Sent to ExtraPe (msg_id={sent.id})")
        _trace("SOURCE", route="beauty_to_extrape", action="dispatch", msg_id=sent.id, chat=chat_id)
        return

    # Priority 4: Generic Amazon / Flipkart
    link_type = "Amazon" if amz_links else "Flipkart"
    log.info(f"[SOURCE] 🎯 {link_type} Deal #{stats['deals_found']} found!")
    sent = await client.send_message(EXTRAPE_BOT, clean_text)
    _store_deal(sent.id, media_bytes, original_links,
                is_cc=False, text=clean_text, deal_type="generic")
    stats["sent_to_extrape"] += 1
    log.info(f"[EXTRAPE] 📤 Sent to ExtraPe (msg_id={sent.id})")
    _trace("SOURCE", route="generic_to_extrape", action="dispatch", msg_id=sent.id, chat=chat_id)

# ══════════════════════════════════════════
#  STEP 1b — PRICE-ALERT GROUP (@finnindeals2) → WA bulk  ← NEW
#
#  event.out guard is critical: this bot posts its own converted
#  deals into @finnindeals2, and that footer contains a
#  dealspouch.com/price-alert URL. Without the guard every deal
#  we post would loop straight back into the pipeline.
# ══════════════════════════════════════════
@client.on(events.NewMessage(chats=PRICE_ALERT_TG_GROUP))
async def handle_price_alert_group(event):
    if event.out or event.message.edit_date:
        return
    msg  = event.message
    text = msg.text or msg.caption or ""
    if not is_price_alert_post(msg, text):
        return
    log.info("[PRICE-ALERT] 🔔 Detected in @finnindeals2 → WA bulk")
    await _dispatch_price_alert(msg)

# ══════════════════════════════════════════
#  STEP 2 — ExtraPe reply → route by deal_type
#
#  FASHION:
#    Amazon  → Dealspouch queue → Step 3 → Fashion WA + TG + bulk
#    Flipkart → Fashion WA + FK WA group
#    Other   → Fashion WA only
#    Fail    → EarnKaro
#
#  BEAUTY:
#    Amazon  → Dealspouch queue → Step 3 → Beauty WA + TG + bulk
#    Flipkart → Beauty WA + FK WA group
#    Other   → Beauty WA only
#    Fail    → EarnKaro
#
#  GENERIC:
#    CC      → CC WA
#    FK      → FK WA
#    Amazon  → Dealspouch queue → Step 3 → TG + bulk
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

    _purge_old_pending_store()

    # ── ExtraPe failure → EarnKaro (all deal types) ──────────────
    if is_extrape_failure(text):
        log.info("[EXTRAPE] ❌ Conversion failed → EarnKaro")
        original_text = None
        if replied_to_id and replied_to_id in sent_original_text:
            original_text = sent_original_text[replied_to_id]
            _cleanup_store(replied_to_id)
        else:
            matched_id = _match_pending_by_links(text)
            if matched_id and matched_id in sent_original_text:
                original_text = sent_original_text[matched_id]
                _cleanup_store(matched_id)
        if not original_text and sent_original_text:
            oldest = next(iter(sent_original_text))
            original_text = sent_original_text[oldest]
            _cleanup_store(oldest)
        if original_text:
            await client.send_message(EARNKARO_BOT, original_text)
            log.info("[EARNKARO] 📤 Forwarded to EarnKaro")
            stats["ignored"] += 1
            _trace("EXTRAPE", route="failure_to_earnkaro", action="dispatch", target=EARNKARO_BOT)
        else:
            log.warning("[EARNKARO] ⚠️ No original text found")
            _trace("EXTRAPE", route="failure_to_earnkaro", action="missing_original")
        return

    if is_echo_of_sent(text):
        _trace("EXTRAPE", route="echo", action="ignored")
        return

    if replied_to_id and replied_to_id in extrape_processed_reply_ids:
        log.info(f"[EXTRAPE] ⏭️ reply_to_id={replied_to_id} already processed")
        stats["ignored"] += 1
        _trace("EXTRAPE", route="duplicate_reply_id", action="ignored", reply_to=replied_to_id)
        return

    msg_hash = hash(text.strip())
    if msg_hash in extrape_seen_hashes:
        log.info("[EXTRAPE] ⏭️ Exact duplicate — ignored")
        stats["ignored"] += 1
        _trace("EXTRAPE", route="duplicate_text", action="ignored")
        return
    extrape_seen_hashes.add(msg_hash)
    if len(extrape_seen_hashes) > 50:
        extrape_seen_hashes.pop()

    # Recover media + metadata from store
    media_bytes   = None
    pending_is_cc = False
    deal_type     = "generic"
    matched_id    = None
    source_is_amazon = False
    source_is_flipkart = False

    if replied_to_id and replied_to_id in pending_media:
        matched_id = replied_to_id
    if not matched_id:
        matched_id = _match_pending_by_links(text)

    # CRITICAL FIX: Check sent_links_store (main deal store), not just pending_media (image cache)
    # If no image exists, matched_id won't be in pending_media, so source_is_amazon stays False
    if matched_id and matched_id in sent_links_store:
        media_bytes   = pending_media.get(matched_id)  # May be None if no image
        entry         = sent_links_store[matched_id]
        pending_is_cc = entry.get("is_cc", False)
        deal_type     = entry.get("deal_type", "generic")
        source_links  = entry.get("links") or set()
        source_text   = " ".join(sorted(source_links))
        source_is_amazon   = bool(extract_amazon_links(source_text))
        source_is_flipkart = bool(extract_flipkart_links_source(source_text))
        _trace("EXTRAPE", action="matched_found", matched=matched_id, source_is_amazon=source_is_amazon, deal_type=deal_type)
        _cleanup_store(matched_id)
        log.info(
            f"[EXTRAPE] ✅ Matched id={matched_id} | "
            f"deal_type={deal_type} | image={'yes' if media_bytes else 'no'}"
        )
        if replied_to_id is None:
            log.info("[EXTRAPE] 🧭 Correlated by link-overlap fallback (no reply_to)")
    else:
        log.warning("[EXTRAPE] ⚠️ No pending match — using ExtraPe's own image and fallback routing")

    if not media_bytes:
        media_bytes = await download_media_bytes(event.message)
        log.info(f"[EXTRAPE] 🖼️ Fallback image: {'yes' if media_bytes else 'no'}")

    ist_now = get_ist_now()

    if replied_to_id:
        extrape_processed_reply_ids.add(replied_to_id)
        if len(extrape_processed_reply_ids) > 100:
            extrape_processed_reply_ids.pop()
    if matched_id and matched_id != replied_to_id:
        extrape_processed_reply_ids.add(matched_id)
        if len(extrape_processed_reply_ids) > 100:
            extrape_processed_reply_ids.pop()

    if deal_type == "generic" and not pending_is_cc:
        inferred_deal_type = classify_special_deal(text)
        if inferred_deal_type != "generic":
            deal_type = inferred_deal_type
            log.warning(f"[EXTRAPE] 🧩 Fallback inferred deal_type={deal_type} from converted text")
        elif source_is_flipkart:
            log.info("[EXTRAPE] 🛒 Flipkart link — keeping deal_type=generic (will route by link type)")

    # ════════════════════════════════════════════════════════════
    #  FASHION PIPELINE
    # ════════════════════════════════════════════════════════════
    if deal_type == "fashion":
        log.info(f"[FASHION] ▶ Routing converted message | image={'yes' if media_bytes else 'no'}")
        if source_is_amazon or extract_amazon_links(text):
            # Amazon fashion → Dealspouch → Step 3 sends Fashion WA + TG + bulk
            log.info(f"[FASHION] ✅ AMZ → Dealspouch | image={'yes' if media_bytes else 'no'}")
            await _send_to_dealspouch(text, media_bytes, "fashion")
            stats["fashion_sent_to_extrape"] += 1
            _trace("EXTRAPE", route="fashion_amz_to_dealspouch", action="dispatch", matched=matched_id)

        elif source_is_flipkart or extract_flipkart_links(text):
            # Flipkart fashion → Fashion WA + FK WA group
            log.info(f"[FASHION] 🛒 FK → Fashion WA + FK WA | image={'yes' if media_bytes else 'no'}")
            if is_quiet_hours():
                log.info("[FASHION] 🌙 Quiet hours — skipping"); stats["ignored"] += 1
                _trace("EXTRAPE", route="fashion_fk", action="skipped_quiet")
            else:
                await send_to_whatsapp_single(text, FASHION_WA_GROUP, media_bytes)
                await send_to_whatsapp_single(text, FK_WA_GROUP, media_bytes)
                stats["fashion_sent_direct_wa"] += 1
                stats["fk_sent_to_wa"] += 1
                _trace("EXTRAPE", route="fashion_fk", action="wa_dual", targets=f"{FASHION_WA_GROUP},{FK_WA_GROUP}")

        else:
            # Other platforms (Myntra, Ajio, etc.) → Fashion WA only
            log.info(f"[FASHION] 🌐 Other → Fashion WA only | image={'yes' if media_bytes else 'no'}")
            if is_quiet_hours():
                log.info("[FASHION] 🌙 Quiet hours — skipping"); stats["ignored"] += 1
                _trace("EXTRAPE", route="fashion_other", action="skipped_quiet")
            else:
                await send_to_whatsapp_single(text, FASHION_WA_GROUP, media_bytes)
                stats["fashion_sent_direct_wa"] += 1
                _trace("EXTRAPE", route="fashion_other", action="wa_single", target=FASHION_WA_GROUP)
        return

    # ════════════════════════════════════════════════════════════
    #  BEAUTY PIPELINE
    # ════════════════════════════════════════════════════════════
    if deal_type == "beauty":
        log.info(f"[BEAUTY] ▶ Routing converted message | image={'yes' if media_bytes else 'no'}")
        if source_is_amazon or extract_amazon_links(text):
            # Amazon beauty → Dealspouch → Step 3 sends Beauty WA + TG + bulk
            log.info(f"[BEAUTY] ✅ AMZ → Dealspouch | image={'yes' if media_bytes else 'no'}")
            await _send_to_dealspouch(text, media_bytes, "beauty")
            stats["beauty_sent_to_extrape"] += 1
            _trace("EXTRAPE", route="beauty_amz_to_dealspouch", action="dispatch", matched=matched_id)

        elif source_is_flipkart or extract_flipkart_links(text):
            # Flipkart beauty → Beauty WA + FK WA group
            log.info(f"[BEAUTY] 🛒 FK → Beauty WA + FK WA | image={'yes' if media_bytes else 'no'}")
            if is_quiet_hours():
                log.info("[BEAUTY] 🌙 Quiet hours — skipping"); stats["ignored"] += 1
                _trace("EXTRAPE", route="beauty_fk", action="skipped_quiet")
            else:
                await send_to_whatsapp_single(text, BEAUTY_WA_GROUP, media_bytes)
                await send_to_whatsapp_single(text, FK_WA_GROUP, media_bytes)
                stats["beauty_sent_direct_wa"] += 1
                stats["fk_sent_to_wa"] += 1
                _trace("EXTRAPE", route="beauty_fk", action="wa_dual", targets=f"{BEAUTY_WA_GROUP},{FK_WA_GROUP}")

        else:
            # Other platforms (Nykaa, Purplle, etc.) → Beauty WA only
            log.info(f"[BEAUTY] 🌐 Other → Beauty WA only | image={'yes' if media_bytes else 'no'}")
            if is_quiet_hours():
                log.info("[BEAUTY] 🌙 Quiet hours — skipping"); stats["ignored"] += 1
                _trace("EXTRAPE", route="beauty_other", action="skipped_quiet")
            else:
                await send_to_whatsapp_single(text, BEAUTY_WA_GROUP, media_bytes)
                stats["beauty_sent_direct_wa"] += 1
                _trace("EXTRAPE", route="beauty_other", action="wa_single", target=BEAUTY_WA_GROUP)
        return

    # ════════════════════════════════════════════════════════════
    #  GENERIC PIPELINE (unchanged original behaviour)
    # ════════════════════════════════════════════════════════════
    if pending_is_cc or is_cc_deal(text):
        log.info(f"[EXTRAPE] 💳 CC → CC WA | image={'yes' if media_bytes else 'no'}")
        if is_quiet_hours():
            log.info(f"[WA-SINGLE] 🌙 Quiet hours ({ist_now.strftime('%H:%M')}) — skipping CC")
            stats["ignored"] += 1
            _trace("EXTRAPE", route="generic_cc", action="skipped_quiet")
        else:
            await send_to_whatsapp_single(text + CC_WA_FOOTER, CC_WA_GROUP, media_bytes)
            stats["cc_sent_via_extrape"] += 1
            _trace("EXTRAPE", route="generic_cc", action="wa_single", target=CC_WA_GROUP)
        return

    if extract_flipkart_links(text):
        log.info(f"[EXTRAPE] 🛒 FK → FK WA | image={'yes' if media_bytes else 'no'}")
        if is_quiet_hours():
            log.info(f"[WA-SINGLE] 🌙 Quiet hours ({ist_now.strftime('%H:%M')}) — skipping FK")
            stats["ignored"] += 1
            _trace("EXTRAPE", route="generic_fk", action="skipped_quiet")
        else:
            await send_to_whatsapp_single(text, FK_WA_GROUP, media_bytes)
            stats["fk_sent_to_wa"] += 1
            _trace("EXTRAPE", route="generic_fk", action="wa_single", target=FK_WA_GROUP)
        return

    if source_is_amazon or extract_amazon_links(text):
        log.info(f"[EXTRAPE] ✅ AMZ → Dealspouch | image={'yes' if media_bytes else 'no'}")
        await _send_to_dealspouch(text, media_bytes, "generic")
        stats["amz_sent_to_dealspouch"] += 1
        _trace("EXTRAPE", route="generic_amz_to_dealspouch", action="dispatch", matched=matched_id)
        return

    log.info("[EXTRAPE] ⏭️ No recognisable link — ignored")
    stats["ignored"] += 1
    _trace("EXTRAPE", route="no_link", action="ignored")

# ══════════════════════════════════════════
#  STEP 3 — Dealspouch reply → route by deal_type
#
#  fashion → Fashion WA  then  TG + main WA bulk
#  beauty  → Beauty WA   then  TG + main WA bulk
#  generic → TG + main WA bulk only (original behaviour)
# ══════════════════════════════════════════
@client.on(events.NewMessage(chats=DEALSPOUCH_BOT))
async def handle_dealspouch(event):
    global last_dealspouch_handled
    text = event.message.text or event.message.caption or ""

    if not has_dealspouch_link(text):
        if not dealspouch_queue:
            stats["ignored"] += 1
            log.info("[DEALSPOUCH] ⏭️ No dealspouch link and no pending queue — ignored")
            _trace("DEALSPOUCH", route="no_dealspouch_link", action="ignored")
            return
        log.warning("[DEALSPOUCH] ⚠️ No dealspouch link in reply, but pending queue exists — continuing")
        _trace("DEALSPOUCH", route="no_dealspouch_link", action="continue_with_queue")

    now = time.time()
    if now - last_dealspouch_handled < DEALSPOUCH_COOLDOWN:
        stats["ignored"] += 1
        log.info("[DEALSPOUCH] ⏭️ Cooldown — duplicate ignored")
        _trace("DEALSPOUCH", route="cooldown", action="ignored")
        return
    last_dealspouch_handled = now

    # Pop oldest entry from unified queue
    if not dealspouch_queue:
        log.warning("[DEALSPOUCH] ⚠️ Queue empty — text-only generic fallback")
        media_bytes = None
        deal_type   = "generic"
        age_minutes = 0.0
    else:
        media_bytes, deal_type, ts = dealspouch_queue.popleft()
        log.info(f"[DEBUG] deal_type={deal_type}")
        log.info(f"[DEBUG] Fashion group={FASHION_WA_GROUP}")
        log.info(f"[DEBUG] Beauty group={BEAUTY_WA_GROUP}")
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
        _trace("DEALSPOUCH", route="stale", action="dropped", age_min=f"{age_minutes:.1f}")
        return

    ist_now = get_ist_now()
    log.info(f"[DEALSPOUCH] ✅ Fresh | IST: {ist_now.strftime('%H:%M')} | deal_type={deal_type}")

    # ── Step 1a: No image captured from source? Fetch one from the product page ──
    if not media_bytes:
        link_match = re.search(r'https?://amaz\.dealspouch\.com/\S+', text)
        if link_match:
            log.info("[IMG-FETCH] 🔎 No image in queue — fetching product image from landing page")
            media_bytes = await fetch_product_image_bytes(link_match.group(0))
            log.info(f"[IMG-FETCH] {'✅ Got image' if media_bytes else '❌ Still no image — will post text-only'}")

    # ── Step 1: Send to specialty WA first (fashion / beauty) ────
    if deal_type == "fashion":
        log.info("[DEBUG] Entered fashion block")
        if is_quiet_hours():
            log.info("[FASHION-DEALSPOUCH] 🌙 Quiet hours — skipping Fashion WA")
            stats["ignored"] += 1
            _trace("DEALSPOUCH", route="fashion", action="skipped_quiet")
        else:
            log.info(f"[FASHION-DEALSPOUCH] 👗 → Fashion WA | image={'yes' if media_bytes else 'no'}")
            await send_to_whatsapp_single(text, FASHION_WA_GROUP, media_bytes)
            stats["fashion_sent_direct_wa"] += 1
            _trace("DEALSPOUCH", route="fashion", action="wa_single", target=FASHION_WA_GROUP)

    elif deal_type == "beauty":
        log.info("[DEBUG] Entered beauty block")
        if is_quiet_hours():
            log.info("[BEAUTY-DEALSPOUCH] 🌙 Quiet hours — skipping Beauty WA")
            stats["ignored"] += 1
            _trace("DEALSPOUCH", route="beauty", action="skipped_quiet")
        else:
            log.info(f"[BEAUTY-DEALSPOUCH] 💄 → Beauty WA | image={'yes' if media_bytes else 'no'}")
            await send_to_whatsapp_single(text, BEAUTY_WA_GROUP, media_bytes)
            stats["beauty_sent_direct_wa"] += 1
            _trace("DEALSPOUCH", route="beauty", action="wa_single", target=BEAUTY_WA_GROUP)

    # ── Step 2: Lucky deal swap (generic only) ───────────────────
    tg_text = text
    if LUCKY_DEALS_ENABLED and deal_type == "generic" and _is_lucky_deal():
        lucky_link = _get_lucky_link()
        tg_text = re.sub(r'https?://amaz\.dealspouch\.com/\S+', lucky_link, tg_text, count=1)
        log.info(f"[DAILY] 🎯 Lucky deal #{_daily_deal_count} — replaced dealspouch link with {lucky_link}")

    tg_text = tg_text + TG_BOT_FOOTER

    # ── Step 3: Post to TG (all types) ───────────────────────────
    try:
        if media_bytes:
            await client.send_file(MY_TG_GROUP, media_bytes, caption=tg_text)
        else:
            await client.send_message(MY_TG_GROUP, tg_text)
        stats["posted_to_tg"] += 1
        log.info(f"[TG] ✅ Posted to {MY_TG_GROUP}")
        _trace("DEALSPOUCH", route=deal_type, action="tg_post", target=MY_TG_GROUP)
    except Exception as e:
        log.error(f"[TG] ❌ Failed: {e}")
        _trace("DEALSPOUCH", route=deal_type, action="tg_error")

    # ── Step 4: Main WA bulk (all types, quiet hours respected) ──
    if is_quiet_hours():
        log.info(f"[WA-BULK] 🌙 Quiet hours ({ist_now.strftime('%H:%M')}) — skipping bulk")
        _trace("DEALSPOUCH", route=deal_type, action="bulk_skipped_quiet")
    else:
        await send_to_whatsapp_bulk(tg_text, media_bytes)
        _trace("DEALSPOUCH", route=deal_type, action="bulk_send")

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
            log.info(f"🤖 ExtraPe Bot        : {EXTRAPE_BOT}")
            log.info(f"🤖 EarnKaro Bot       : {EARNKARO_BOT}")
            log.info(f"🤖 Dealspouch Bot     : {DEALSPOUCH_BOT}")
            log.info(f"📢 TG Group           : {MY_TG_GROUP}")
            log.info(f"🔔 Price-alert watch  : {PRICE_ALERT_TG_GROUP} + {CC_DIRECT_GROUP} → WA bulk only")
            log.info(f"📲 FK WA Group        : {FK_WA_GROUP}")
            log.info(f"📲 CC WA Group        : {CC_WA_GROUP}")
            log.info(f"📲 Fashion WA Group   : {FASHION_WA_GROUP}")
            log.info(f"📲 Beauty WA Group    : {BEAUTY_WA_GROUP}")
            log.info(f"📲 WA Sender          : {BAILEYS_URL or 'NOT SET'}")
            log.info(f"⏱️  Freshness limit    : {MAX_DEAL_AGE_MINUTES} min")
            log.info(f"🎯 Lucky deals       : {'ON — ' + str(LUCKY_DEALS_PER_DAY) + '/day' if LUCKY_DEALS_ENABLED else 'OFF (temporarily disabled)'}")
            log.info("─" * 55)
            log.info("PRICE-ALERT FLOW (Dealspouch price alert bot posts):")
            log.info("  Detected → WA bulk (no ExtraPe, no Dealspouch, no TG)")
            log.info("  + Fashion/Beauty product → also that category WA group")
            log.info("─" * 55)
            log.info("FASHION / BEAUTY FLOWS (detected from all source groups):")
            log.info("  Amazon   → ExtraPe → Dealspouch → Fashion/Beauty WA + TG + bulk")
            log.info("  Flipkart → ExtraPe → Fashion/Beauty WA + FK WA group")
            log.info("  Other    → ExtraPe → Fashion/Beauty WA only")
            log.info("  Fail     → EarnKaro")
            log.info("─" * 55)
            log.info("⏳ Waiting for deals...\n")
            await client.run_until_disconnected()
        except Exception as e:
            log.error(f"Disconnected: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

asyncio.run(run())